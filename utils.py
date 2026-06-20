import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from app_info import APP_NAME
from logger import get_logger

log = get_logger("erp.utils")

# catbox/litterbox reject some non-browser User-Agents, so uploads use a
# browser-like UA. 0x0 accepts anything; keeping it uniform avoids three copies.
_UPLOAD_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _detect_image_format(data: bytes) -> tuple[str, str]:
    """Return (content_type, filename_ext) from image magic bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return "image/jpeg", "jpg"  # fallback


def _multipart_post(
    url: str,
    fields: dict,
    file_field: str,
    file_bytes: bytes,
    content_type: str,
    filename: str,
    validate: Callable[[str], bool],
) -> Optional[str]:
    """POST a multipart/form-data request with one file part.

    Returns the response body (a URL) if it is non-empty and passes ``validate``,
    otherwise None. ``fields`` are extra text form fields sent before the file.
    """
    boundary = b"----EternalRP" + os.urandom(8).hex().encode()
    parts = []
    for name, value in fields.items():
        parts.append(
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="' + name.encode() + b'"\r\n\r\n'
            + value.encode() + b"\r\n"
        )
    parts.append(
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="' + file_field.encode()
        + b'"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n"
        + file_bytes + b"\r\n"
    )
    parts.append(b"--" + boundary + b"--\r\n")

    req = urllib.request.Request(url, data=b"".join(parts), method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary.decode())
    req.add_header("User-Agent", _UPLOAD_USER_AGENT)
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = resp.read().decode().strip()
    if result and validate(result):
        return result
    return None


def _valid_url(url: str, must_contain: str = "") -> bool:
    return url.startswith("http") and len(url) < 500 and (must_contain in url)


# Cover-art upload hosts, tried in order. Expiring hosts come first so that
# "now playing" artwork is not permanently published; permanent catbox.moe is
# only the last-resort fallback.
_UPLOAD_HOSTS = (
    {
        "name": "litterbox.catbox.moe",
        "url": "https://litterbox.catbox.moe/resources/internals/api.php",
        "fields": {"reqtype": "fileupload", "time": "24h"},
        "file_field": "fileToUpload",
        # Litterbox serves uploads from litter.catbox.moe (NOT "litterbox").
        "validate": lambda u: _valid_url(u, "litter."),
    },
    {
        "name": "0x0.st",
        "url": "https://0x0.st",
        "fields": {"expires": "24"},
        "file_field": "file",
        "validate": lambda u: _valid_url(u, "0x0.st"),
    },
    {
        "name": "catbox.moe",
        "url": "https://catbox.moe/user/api.php",
        "fields": {"reqtype": "fileupload"},
        "file_field": "fileToUpload",
        "validate": lambda u: _valid_url(u, "catbox.moe"),
    },
)


def upload_cover_art(thumbnail_bytes: bytes) -> Optional[str]:
    """Upload image bytes to a public host and return the URL, or None.

    Tries expiring hosts first (litterbox 24h, then 0x0 24h) and falls back to
    the permanent catbox.moe only if both fail.
    """
    if not thumbnail_bytes or len(thumbnail_bytes) > 20 * 1024 * 1024:
        return None
    content_type, ext = _detect_image_format(thumbnail_bytes)
    filename = f"cover.{ext}"

    for host in _UPLOAD_HOSTS:
        try:
            url = _multipart_post(
                host["url"],
                host["fields"],
                host["file_field"],
                thumbnail_bytes,
                content_type,
                filename,
                host["validate"],
            )
            if url:
                log.debug("Cover uploaded via %s: %s", host["name"], url)
                return url
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200] if e.fp else ""
            log.debug("%s upload HTTP %d: %s", host["name"], e.code, body or str(e))
        except Exception as e:
            log.debug("%s upload failed: %s", host["name"], e)

    log.warning("Cover art upload failed (all hosts tried)")
    return None


def _encode_within(text: str, max_encoded_len: int) -> str:
    """Return the longest urllib.parse.quote() prefix of ``text`` whose *encoded*
    length does not exceed ``max_encoded_len`` (so multibyte chars never overflow)."""
    if max_encoded_len <= 0 or not text:
        return ""
    encoded = ""
    for ch in text:
        piece = urllib.parse.quote(ch, safe="")
        if len(encoded) + len(piece) > max_encoded_len:
            break
        encoded += piece
    return encoded


_JOIN_FALLBACK = "eternalrp://sync?track=Unknown&artist=&pos=0"


def build_join_secret(track: str, artist: str = "", position_sec: int = 0) -> str:
    """Build a Discord join secret that fits the 128-char limit safely.

    Budgets by URL-*encoded* length (not character count) so multibyte titles —
    emoji, CJK — don't silently collapse to "Unknown". The artist is trimmed
    before the title, since the title matters more for matching.
    """
    safe_track = (track or "Unknown Track").strip() or "Unknown Track"
    safe_artist = (artist or "").strip()
    safe_pos = max(0, int(position_sec or 0))

    # Fixed overhead of the URI frame around the two encoded values.
    frame_len = len("eternalrp://sync?track=&artist=&pos=") + len(str(safe_pos))
    budget = 128 - frame_len
    if budget <= 0:
        return _JOIN_FALLBACK

    # Reserve up to a third of the budget for the artist; the title keeps the rest.
    encoded_artist = _encode_within(safe_artist, budget // 3)
    encoded_track = _encode_within(safe_track, budget - len(encoded_artist))
    if not encoded_track:
        return _JOIN_FALLBACK

    return (
        f"eternalrp://sync?track={encoded_track}"
        f"&artist={encoded_artist}&pos={safe_pos}"
    )


def parse_join_secret(uri: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse an eternalrp:// URI into track details."""
    if not uri or not uri.startswith("eternalrp://"):
        return None, "invalid_scheme"

    payload = uri[len("eternalrp://"):]
    if "?" not in payload:
        legacy_track = urllib.parse.unquote(payload.replace("/", "").strip())
        if legacy_track:
            return {
                "track": legacy_track,
                "artist": "",
                "position_sec": 0,
            }, None
        return None, "missing_track"

    _, query = payload.split("?", 1)
    params = urllib.parse.parse_qs(query, keep_blank_values=True)

    track = urllib.parse.unquote((params.get("track") or [""])[0]).strip()
    artist = urllib.parse.unquote((params.get("artist") or [""])[0]).strip()
    raw_pos = (params.get("pos") or ["0"])[0]

    try:
        position_sec = max(0, int(raw_pos))
    except (TypeError, ValueError):
        return None, "invalid_position"

    if not track:
        return None, "missing_track"

    return {
        "track": track,
        "artist": artist,
        "position_sec": position_sec,
    }, None


def register_uri_scheme(exe_path: Optional[str] = None, silent: bool = False) -> bool:
    """Register the eternalrp:// protocol handler for the current Windows user."""
    try:
        import winreg
    except ImportError:
        if not silent:
            print("Registry access requires Windows.", file=sys.stderr)
        return False

    cmd = os.path.abspath(exe_path or sys.executable)
    command = f'"{cmd}" "%1"'

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Classes\eternalrp") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f"URL:{APP_NAME}")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Classes\eternalrp\shell\open\command",
        ) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
        return True
    except OSError as e:
        log.warning("URI registration failed: %s", e)
        if not silent:
            print(f"URI registration failed: {e}", file=sys.stderr)
        return False


def register_discord_launch(client_id: str, exe_path: Optional[str] = None,
                            silent: bool = False) -> bool:
    """Register discord-{client_id}:// protocol so Discord can launch the app on Join.

    This is the mechanism Discord uses when a user clicks "Join" on someone's
    Rich Presence.  Discord opens ``discord-{client_id}://join/{secret}`` and
    the OS launches the registered command with the URL as an argument.

    Written to HKCU (no admin required).
    """
    try:
        import winreg
    except ImportError:
        return False

    cmd = os.path.abspath(exe_path or sys.executable)
    command = f'"{cmd}" "%1"'
    protocol = f"discord-{client_id}"

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Classes\{protocol}") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:Run EternalRichPresence")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Classes\{protocol}\shell\open\command"
        ) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
        return True
    except OSError as e:
        log.warning("Discord protocol registration failed: %s", e)
        if not silent:
            print(f"Discord protocol registration failed: {e}", file=sys.stderr)
        return False

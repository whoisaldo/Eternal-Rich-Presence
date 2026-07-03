# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from app_info import (
    APP_NAME,
    DEFAULT_ASSET_KEY,
    DEFAULT_SPOTIFY_REDIRECT_URI,
    config_path,
)
from logger import get_logger

log = get_logger("erp.utils")

# ---------------------------------------------------------------------------
# config.py rendering — the ONE place that knows the full key set.
# Three hand-maintained templates (config.example.py, main's default writer,
# the setup GUI's writer) previously drifted apart: the GUI silently dropped
# the privacy toggles on every save. Every writer now goes through here.
# ---------------------------------------------------------------------------

_CONFIG_DEFAULTS = {
    "CLIENT_ID": "",
    "ASSET_KEY": DEFAULT_ASSET_KEY,
    "SPOTIFY_CLIENT_ID": "",
    "SPOTIFY_CLIENT_SECRET": "",
    "SPOTIFY_REDIRECT_URI": DEFAULT_SPOTIFY_REDIRECT_URI,
    "AUTO_ACCEPT_JOIN_REQUESTS": True,
    "COVER_ART_UPLOAD": True,
}


def render_config(
    client_id: str,
    asset_key: str = DEFAULT_ASSET_KEY,
    spotify_client_id: str = "",
    spotify_client_secret: str = "",
    spotify_redirect_uri: str = DEFAULT_SPOTIFY_REDIRECT_URI,
    auto_accept_join_requests: bool = True,
    cover_art_upload: bool = True,
) -> str:
    """Render the canonical config.py contents.

    Values are emitted with ``repr()`` so a quote/backslash/newline in any
    user-facing field becomes a safe Python literal instead of corrupting the
    file (a project guardrail).
    """
    redirect = str(spotify_redirect_uri).strip() or DEFAULT_SPOTIFY_REDIRECT_URI
    return (
        "# Discord application Client ID (uses built-in if set).\n"
        f"CLIENT_ID = {str(client_id).strip()!r}\n"
        "\n"
        "# Rich Presence art asset key (Dev Portal > Rich Presence > Art Assets).\n"
        f"ASSET_KEY = {(str(asset_key).strip() or DEFAULT_ASSET_KEY)!r}\n"
        "\n"
        "# Spotify Web API credentials (leave empty to disable Spotify).\n"
        f"SPOTIFY_CLIENT_ID = {str(spotify_client_id).strip()!r}\n"
        f"SPOTIFY_CLIENT_SECRET = {str(spotify_client_secret).strip()!r}\n"
        f"SPOTIFY_REDIRECT_URI = {redirect!r}\n"
        "\n"
        '# Privacy: auto-accept Discord "Listen Along" join requests.\n'
        "# Set to False to ignore join requests from people who click Join.\n"
        f"AUTO_ACCEPT_JOIN_REQUESTS = {bool(auto_accept_join_requests)!r}\n"
        "\n"
        "# Privacy: upload album art to a public host so Discord can show it.\n"
        "# Set to False to use the static app icon instead.\n"
        f"COVER_ART_UPLOAD = {bool(cover_art_upload)!r}\n"
    )


def read_config_values(path: Optional[str] = None) -> dict:
    """Tolerantly read config.py, returning defaults for anything missing or
    broken. Used to preserve settings (e.g. the privacy toggles) across
    rewrites and to prefill the setup GUI."""
    values = dict(_CONFIG_DEFAULTS)
    path = path or config_path()
    if not os.path.isfile(path):
        return values
    ns: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            exec(compile(f.read(), path, "exec"), ns)
    except Exception as e:
        log.warning("config.py could not be read (%s); using defaults", e)
        return values
    for key, default in _CONFIG_DEFAULTS.items():
        if key in ns and ns[key] is not None:
            values[key] = bool(ns[key]) if isinstance(default, bool) else str(ns[key])
    return values


def write_config_file(content: str, path: Optional[str] = None) -> str:
    """Atomically write config.py (temp file + rename), returning its path.

    A crash mid-write must never leave a truncated config.py behind."""
    path = path or config_path()
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)
    return path


def resource_path(name: str) -> Optional[str]:
    """Locate a bundled resource: PyInstaller _MEIPASS first, then beside the
    exe, then the source tree. Returns None if the file doesn't exist."""
    if getattr(sys, "frozen", False):
        meipass = os.path.join(getattr(sys, "_MEIPASS", ""), name)
        if os.path.isfile(meipass):
            return meipass
        beside = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), name)
        if os.path.isfile(beside):
            return beside
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    return src if os.path.isfile(src) else None


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
    timeout: float = 10.0,
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
            b'Content-Disposition: form-data; name="'
            + name.encode()
            + b'"\r\n\r\n'
            + value.encode()
            + b"\r\n"
        )
    parts.append(
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="'
        + file_field.encode()
        + b'"; filename="'
        + filename.encode()
        + b'"\r\n'
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + file_bytes + b"\r\n"
    )
    parts.append(b"--" + boundary + b"--\r\n")

    req = urllib.request.Request(url, data=b"".join(parts), method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary.decode())
    req.add_header("User-Agent", _UPLOAD_USER_AGENT)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # The response should be one short URL; cap the read so a misbehaving
        # host can't balloon memory.
        result = resp.read(1024).decode(errors="replace").strip()
    if result and validate(result):
        return result
    return None


def _valid_url(url: str, must_contain: str = "") -> bool:
    return url.startswith(("http://", "https://")) and len(url) < 500 and (must_contain in url)


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
            # Short per-host timeout: this runs on the poll thread, and three
            # dead hosts at 10s each used to stall presence updates for ~30s.
            url = _multipart_post(
                host["url"],
                host["fields"],
                host["file_field"],
                thumbnail_bytes,
                content_type,
                filename,
                host["validate"],
                timeout=6.0,
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
        # errors="replace": a lone UTF-16 surrogate in provider metadata must
        # degrade to "?" instead of raising UnicodeEncodeError and killing the
        # presence update for the whole track.
        piece = urllib.parse.quote(ch, safe="", errors="replace")
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

    return f"eternalrp://sync?track={encoded_track}&artist={encoded_artist}&pos={safe_pos}"


def parse_join_secret(uri: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse an eternalrp:// URI into track details."""
    if not uri or not uri.startswith("eternalrp://"):
        return None, "invalid_scheme"

    payload = uri[len("eternalrp://") :]
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
    # parse_qs already percent-decodes values; decoding a second time corrupted
    # titles containing literal %XX sequences ("100%25 off" became "100% off").
    params = urllib.parse.parse_qs(query, keep_blank_values=True)

    track = ((params.get("track") or [""])[0]).strip()
    artist = ((params.get("artist") or [""])[0]).strip()
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


def _protocol_command(exe_path: Optional[str] = None) -> str:
    """Build the shell command a protocol handler should invoke.

    When running from source, the interpreter alone would swallow the URI
    (python.exe would try to execute it as a script), so the entry script is
    included — mirroring how _restart_self relaunches the app."""
    if exe_path:
        return f'"{os.path.abspath(exe_path)}" "%1"'
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}" "%1"'
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{os.path.abspath(sys.executable)}" "{script}" "%1"'


def _register_protocol(protocol: str, exe_path: Optional[str], silent: bool) -> bool:
    """Register a URL protocol handler under HKCU (no admin required)."""
    try:
        import winreg
    except ImportError:
        if not silent:
            print("Registry access requires Windows.", file=sys.stderr)
        return False

    command = _protocol_command(exe_path)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Classes\{protocol}") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f"URL:{APP_NAME}")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Classes\{protocol}\shell\open\command"
        ) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
        return True
    except OSError as e:
        log.warning("%s:// registration failed: %s", protocol, e)
        if not silent:
            print(f"{protocol}:// registration failed: {e}", file=sys.stderr)
        return False


def register_uri_scheme(exe_path: Optional[str] = None, silent: bool = False) -> bool:
    """Register the eternalrp:// protocol handler for the current Windows user."""
    return _register_protocol("eternalrp", exe_path, silent)


def register_discord_launch(
    client_id: str, exe_path: Optional[str] = None, silent: bool = False
) -> bool:
    """Register discord-{client_id}:// protocol so Discord can launch the app on Join.

    This is the mechanism Discord uses when a user clicks "Join" on someone's
    Rich Presence.  Discord opens ``discord-{client_id}://join/{secret}`` and
    the OS launches the registered command with the URL as an argument.
    """
    return _register_protocol(f"discord-{client_id}", exe_path, silent)

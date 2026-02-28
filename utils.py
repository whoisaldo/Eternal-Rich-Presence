import os
import sys
import urllib.request
from typing import Optional


def app_dir() -> str:
    """Absolute path to the application directory (handles PyInstaller frozen builds)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def upload_cover_to_catbox(thumbnail_bytes: bytes) -> Optional[str]:
    """Upload image bytes to catbox.moe (anonymous). Returns the public URL or None."""
    if not thumbnail_bytes or len(thumbnail_bytes) > 20 * 1024 * 1024:
        return None
    boundary = b"----EternalRP" + os.urandom(8).hex().encode()
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
        b"fileupload\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="fileToUpload"; filename="cover.jpg"\r\n'
        b"Content-Type: image/jpeg\r\n\r\n"
        + thumbnail_bytes + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    try:
        req = urllib.request.Request(
            "https://catbox.moe/user/api.php",
            data=body,
            method="POST",
        )
        req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary.decode())
        with urllib.request.urlopen(req, timeout=10) as resp:
            url = resp.read().decode().strip()
            if url and "catbox.moe" in url and url.startswith("http") and len(url) < 500:
                return url
    except Exception:
        pass
    return None


def register_uri_scheme(exe_path: str = None, silent: bool = False) -> bool:
    """Register the eternalrp:// protocol handler in the Windows Registry (requires admin)."""
    try:
        import winreg
    except ImportError:
        if not silent:
            print("Registry access requires Windows.", file=sys.stderr)
        return False

    cmd = os.path.abspath(exe_path or sys.executable)
    command = f'"{cmd}" "%1"'

    try:
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, "eternalrp") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:Eternal Rich Presence")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r"eternalrp\shell\open\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
        return True
    except OSError as e:
        if not silent:
            print(f"URI registration failed (try running as Administrator): {e}", file=sys.stderr)
        return False


def register_discord_launch(client_id: str, exe_path: str = None, silent: bool = False) -> bool:
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
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f"URL:Run EternalRichPresence")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Classes\{protocol}\shell\open\command"
        ) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
        return True
    except OSError as e:
        if not silent:
            print(f"Discord protocol registration failed: {e}", file=sys.stderr)
        return False

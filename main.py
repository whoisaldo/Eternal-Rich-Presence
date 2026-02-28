"""
EternalRichPresence — Discord Rich Presence bridge for Apple Music and Spotify.

Host mode broadcasts your current track with live cover art and a Listen Along
invite via a system tray app. Listener mode handles eternalrp:// URIs to sync
playback on the receiving end.
"""

import atexit
import ctypes
import os
import sys
import threading
import time
import urllib.parse

# --noconsole builds set stdout/stderr to None; redirect to devnull so prints
# don't crash the process.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

_app_dir = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
if _app_dir and _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

from logger import get_logger, LOG_PATH

log = get_logger("erp.main")

_ICON_NAME = "Apple_Music_Icon.png"


def _create_default_config():
    """Write a starter config.py next to the exe/script if one doesn't exist."""
    cfg_path = os.path.join(_app_dir, "config.py")
    if os.path.isfile(cfg_path):
        return
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(
                '# Paste your Discord application Client ID below.\n'
                'CLIENT_ID = "YOUR_DISCORD_CLIENT_ID"\n'
                '\n'
                'ASSET_KEY = "apple_music"\n'
                '\n'
                '# Optional: Spotify credentials (leave empty to disable).\n'
                'SPOTIFY_CLIENT_ID = ""\n'
                'SPOTIFY_CLIENT_SECRET = ""\n'
                'SPOTIFY_REDIRECT_URI = "http://localhost:8888/callback"\n'
            )
        log.info("Created default config.py at %s", cfg_path)
    except Exception as e:
        log.error("Failed to create config.py: %s", e)


def _msgbox(text: str, title: str = "EternalRichPresence", info: bool = False):
    """Show a native Windows message box (works even with --noconsole)."""
    if info:
        log.info("MSGBOX: %s", text)
    else:
        log.error("MSGBOX: %s", text)
    try:
        MB_SETFOREGROUND = 0x00010000
        MB_TASKMODAL = 0x00002000
        flags = (0x40 if info else 0x10) | MB_SETFOREGROUND | MB_TASKMODAL
        ctypes.windll.user32.MessageBoxW(0, text, title, flags)
    except Exception:
        pass


def _icon_path():
    """Resolve the tray icon image, checking PyInstaller bundle first."""
    if getattr(sys, "frozen", False):
        meipass = os.path.join(getattr(sys, "_MEIPASS", ""), _ICON_NAME)
        if os.path.isfile(meipass):
            return meipass
        beside_exe = os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), _ICON_NAME
        )
        if os.path.isfile(beside_exe):
            return beside_exe
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), _ICON_NAME)
    if os.path.isfile(src):
        return src
    return None


def _load_tray_icon():
    from PIL import Image
    path = _icon_path()
    if path:
        try:
            return Image.open(path)
        except Exception:
            log.warning("Could not load tray icon from %s", path)
    return Image.new("RGB", (64, 64), (252, 60, 68))


def run_listener_mode(uri: str) -> int:
    """
    Parse an eternalrp:// URI and attempt to start playback on the listener's
    device. Tries Spotify first (if configured), then opens an Apple Music search.
    """
    track_name = "Unknown Track"
    artist_name = ""
    position_sec = 0

    if uri.startswith("eternalrp://"):
        rest = uri[len("eternalrp://"):]
        if "?" in rest:
            _, qs = rest.split("?", 1)
            params = urllib.parse.parse_qs(qs)
            if "track" in params and params["track"]:
                track_name = urllib.parse.unquote(params["track"][0])
            if "artist" in params and params["artist"]:
                artist_name = urllib.parse.unquote(params["artist"][0])
            if "pos" in params and params["pos"]:
                try:
                    position_sec = int(params["pos"][0])
                except (ValueError, TypeError):
                    position_sec = 0
        else:
            track_name = urllib.parse.unquote(
                rest.replace("/", "").strip() or "Unknown Track"
            )

    display = f"{track_name} by {artist_name}" if artist_name else track_name
    log.info("[SYNC] Attempting to join %s at %ds", display, position_sec)

    position_ms = position_sec * 1000

    try:
        from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            from providers.spotify import SpotifyProvider
            sp = SpotifyProvider(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
            if sp.search_and_play(track_name, artist_name, position_ms=position_ms):
                log.info("Playback started on Spotify: %s at %ds", display, position_sec)
                return 0
            err = sp.last_error or ""
            if err == "no_active_device":
                _msgbox(
                    "Spotify is open but idle.\n\n"
                    "Please press Play on any song in your Spotify\n"
                    "app first, then try Listen Along again.",
                    "Listen Along — No Active Device",
                    info=True,
                )
            elif err == "premium_required":
                _msgbox(
                    "Listen Along requires a Spotify Premium account\n"
                    "to control playback remotely.\n\n"
                    "Falling back to Apple Music search.",
                    "Listen Along — Premium Required",
                    info=True,
                )
            elif err == "server_error":
                _msgbox(
                    "Spotify's servers are temporarily unavailable.\n"
                    "Please try again in a moment.",
                    "Listen Along — Spotify Error",
                    info=True,
                )
            else:
                log.debug("Spotify join failed (reason: %s)", err)
            log.debug("Spotify search_and_play returned False, falling back to Apple Music")
    except Exception:
        log.debug("Spotify sync unavailable, falling back to Apple Music", exc_info=True)

    search_query = f"{track_name} {artist_name}".strip()
    if search_query and search_query != "Unknown Track":
        search_url = (
            "https://music.apple.com/search?term="
            + urllib.parse.quote(search_query, safe="")
        )
        try:
            import webbrowser
            webbrowser.open(search_url)
            log.info("Opened Apple Music search fallback: %s", search_url)
        except Exception:
            log.info("Search manually: %s", search_url)

    return 0


def run_host_mode() -> int:
    """
    Poll music providers, update Discord Rich Presence, and sit in the system
    tray until the user exits.  Priority: Apple Music > Spotify.
    """
    log.info("Starting host mode")

    # --- validate / create config first ---
    needs_setup = False
    try:
        from config import CLIENT_ID
        if not CLIENT_ID or CLIENT_ID == "YOUR_DISCORD_CLIENT_ID":
            needs_setup = True
    except ImportError:
        needs_setup = True

    if needs_setup:
        log.info("Config missing or incomplete — launching setup GUI")
        try:
            from setup_gui import run_setup_gui
            if not run_setup_gui():
                log.info("Setup cancelled by user")
                return 1
            import importlib
            if "config" in sys.modules:
                importlib.reload(sys.modules["config"])
            from config import CLIENT_ID
            if not CLIENT_ID or CLIENT_ID == "YOUR_DISCORD_CLIENT_ID":
                _msgbox("Discord Client ID is still not set. Please try again.")
                return 1
        except Exception as e:
            log.error("Setup GUI failed: %s", e)
            _create_default_config()
            _msgbox(
                "Could not open the setup window.\n\n"
                "A config.py has been created next to the app.\n"
                "Open it in Notepad, paste your Discord CLIENT_ID, "
                "save, and launch again."
            )
            return 1

    # --- load providers ---
    try:
        from providers.apple_music import AppleMusicProvider
    except Exception as e:
        log.exception("Failed to load Apple Music provider")
        _msgbox(f"Failed to load Apple Music provider:\n{e}")
        return 1

    from manager import ProviderManager

    provider_list = [AppleMusicProvider()]

    try:
        from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            from providers.spotify import SpotifyProvider
            try:
                from config import SPOTIFY_REDIRECT_URI
            except ImportError:
                SPOTIFY_REDIRECT_URI = ""
            redirect = SPOTIFY_REDIRECT_URI or "http://localhost:8888/callback"
            provider_list.append(
                SpotifyProvider(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, redirect)
            )
            log.info("Spotify provider loaded")
    except (ImportError, Exception):
        log.debug("Spotify provider not loaded", exc_info=True)

    mgr = ProviderManager(provider_list)

    try:
        from config import ASSET_KEY
    except ImportError:
        ASSET_KEY = "apple_music"

    from presence import DiscordPresence

    dp = DiscordPresence(CLIENT_ID, asset_key=(ASSET_KEY or "apple_music").strip())

    def _cleanup():
        dp.disconnect()

    atexit.register(_cleanup)

    # --- Discord event listener (receives ACTIVITY_JOIN from Discord) ---
    evt_listener = None
    try:
        from discord_events import DiscordEventListener

        def _on_join_event(secret: str):
            log.info("ACTIVITY_JOIN received via event listener: %s", secret)
            threading.Thread(
                target=run_listener_mode,
                args=(secret,),
                daemon=True,
            ).start()

        evt_listener = DiscordEventListener(CLIENT_ID, _on_join_event)
        evt_listener.start()
        log.info("Discord event listener started")
    except Exception as e:
        log.warning("Discord event listener failed to start: %s", e)

    # --- background poll loop ---
    stop_event = threading.Event()
    paused = threading.Event()
    interval = 5

    def _poll_loop():
        while not stop_event.is_set():
            if not paused.is_set():
                try:
                    if dp._rpc is None:
                        try:
                            dp.connect()
                            log.info("Connected to Discord RPC")
                        except Exception as e:
                            log.debug("Discord RPC connect retry failed: %s", e)

                    if dp._rpc is not None:
                        t = mgr.get_now_playing()
                        if t is None:
                            dp.clear()
                        else:
                            name = mgr.active_provider.name if mgr.active_provider else ""
                            dp.update(t, name)
                        if tray:
                            if t:
                                src = mgr.active_provider.name if mgr.active_provider else "?"
                                tip = f"EternalRichPresence | {src}\n{t.title} — {t.artist}"
                            else:
                                tip = "EternalRichPresence | Idle"
                            tray.title = tip[:127]
                except Exception as e:
                    dp._rpc = None
                    log.warning("Poll error (will retry): %s", e)
            stop_event.wait(interval)

    poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    poll_thread.start()

    # --- system tray ---
    tray = None

    import signal

    def _sigint_handler(_sig, _frame):
        stop_event.set()
        if tray:
            try:
                tray.stop()
            except Exception:
                pass

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        import pystray

        icon_image = _load_tray_icon()

        def _now_playing_label(_item):
            t = dp.current_track
            if paused.is_set():
                return "Paused"
            if t is None:
                return "No track playing"
            label = t.title
            if t.artist and t.artist != "Unknown Artist":
                label += f" — {t.artist}"
            return label

        def _provider_label(_item):
            p = mgr.active_provider
            return f"Source: {p.name}" if p else "Source: —"

        def _discord_status_label(_item):
            return "Discord: Connected" if dp._rpc is not None else "Discord: Disconnected"

        def on_toggle(_icon, _item):
            if paused.is_set():
                paused.clear()
                log.info("Resumed")
            else:
                paused.set()
                dp.clear()
                log.info("Paused")

        def on_reconnect(_icon, _item):
            log.info("Manual reconnect requested")
            try:
                dp.clear()
                dp.disconnect()
                dp.connect()
                paused.clear()
                log.info("Reconnected to Discord RPC")
            except Exception as e:
                log.error("Reconnect failed: %s", e)
                _msgbox(f"Reconnect failed:\n{e}")

        def on_open_log(_icon, _item):
            log.info("Opening log file: %s", LOG_PATH)
            try:
                os.startfile(LOG_PATH)
            except Exception:
                _msgbox(f"Log file:\n{LOG_PATH}")

        def on_copy_log_path(_icon, _item):
            try:
                import subprocess
                subprocess.run(
                    ["clip"], input=LOG_PATH.encode(), check=True, creationflags=0x08000000
                )
            except Exception:
                _msgbox(f"Log path:\n{LOG_PATH}")

        def on_about(_icon, _item):
            _msgbox(
                "EternalRichPresence  v1.0\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Created by Ali Younes (@whoisaldo)\n\n"
                "Discord Rich Presence bridge for\n"
                "Apple Music and Spotify — with live\n"
                "cover art and Listen Along.\n\n"
                "Official repo:\n"
                "github.com/whoisaldo/Eternal-Rich-Presence\n\n"
                "Contact: Aliyounes@eternalreverse.com\n\n"
                "© 2026 Ali Younes. All rights reserved.",
                "About EternalRichPresence",
                info=True,
            )

        def on_exit(icon, _item):
            log.info("Exit requested")
            stop_event.set()
            icon.stop()

        def _build_listen_link():
            """Build the current Listen Along link from dp state."""
            t = dp.current_track
            if t is None:
                return None
            import urllib.parse as _up
            pos = int(t.position_sec) if t.position_sec is not None else 0
            safe_t = _up.quote(t.title[:80], safe="")
            safe_a = _up.quote(t.artist[:40], safe="")
            return f"eternalrp://sync?track={safe_t}&artist={safe_a}&pos={pos}"

        def on_copy_listen_link(_icon, _item):
            link = _build_listen_link()
            if link is None:
                _msgbox(
                    "No track is currently playing.\n"
                    "Start playing music first.",
                    "Listen Along",
                    info=True,
                )
                return
            try:
                import subprocess
                subprocess.run(
                    ["clip"], input=link.encode(), check=True, creationflags=0x08000000
                )
                log.info("Listen Along link copied: %s", link)
            except Exception:
                _msgbox(f"Listen Along link:\n{link}", info=True)

        def on_log_join_secret(_icon, _item):
            link = _build_listen_link()
            if link is None:
                log.info("[DEBUG] No track playing — no join_secret to show")
                return
            log.info("[DEBUG] Current join_secret: %s", link)

        debug_menu = pystray.Menu(
            pystray.MenuItem(_discord_status_label, lambda: None, enabled=False),
            pystray.MenuItem(
                lambda _item: f"Log: {os.path.basename(LOG_PATH)}", lambda: None, enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Log Join Secret", on_log_join_secret),
            pystray.MenuItem("Open Log File", on_open_log),
            pystray.MenuItem("Copy Log Path", on_copy_log_path),
        )

        menu = pystray.Menu(
            pystray.MenuItem("About EternalRichPresence", on_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_now_playing_label, lambda: None, enabled=False),
            pystray.MenuItem(_provider_label, lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Copy Listen Along Link", on_copy_listen_link),
            pystray.MenuItem(
                lambda _item: "Resume" if paused.is_set() else "Pause",
                on_toggle,
            ),
            pystray.MenuItem("Reconnect to Discord", on_reconnect),
            pystray.MenuItem("Debug", debug_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", on_exit),
        )

        tray = pystray.Icon(
            "EternalRichPresence", icon_image, "EternalRichPresence", menu
        )
        log.info("System tray started")
        tray.run()
    except Exception as e:
        log.exception("System tray failed")
        _msgbox(
            f"System tray failed to start:\n{e}\n\n"
            "Falling back to console mode (Ctrl+C to quit)."
        )
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    # --- teardown ---
    log.info("Shutting down")
    stop_event.set()
    if evt_listener:
        evt_listener.stop()
    poll_thread.join(timeout=10)
    atexit.unregister(_cleanup)
    dp.disconnect()

    return 0


def _clear_presence() -> int:
    """Connect to Discord RPC and forcibly clear any stuck activity."""
    try:
        from config import CLIENT_ID
    except ImportError:
        _msgbox("config.py with CLIENT_ID required.")
        return 1
    if not CLIENT_ID or CLIENT_ID == "YOUR_DISCORD_CLIENT_ID":
        _msgbox("Set CLIENT_ID in config.py.")
        return 1
    try:
        from pypresence import Presence
    except ImportError:
        _msgbox("pypresence is missing. Reinstall or rebuild the app.")
        return 1

    rpc = Presence(CLIENT_ID)
    try:
        rpc.connect()
        rpc.clear(pid=os.getpid())
        try:
            rpc.clear(pid=0)
        except Exception:
            pass
        try:
            rpc.update(state="", details="", pid=os.getpid())
            time.sleep(0.3)
            rpc.clear(pid=os.getpid())
        except Exception:
            pass
        log.info("Rich Presence cleared")
    except Exception as e:
        log.error("Could not clear: %s", e)
        _msgbox(f"Could not clear (is Discord running?):\n{e}")
        return 1
    finally:
        try:
            rpc.close()
        except Exception:
            pass
    return 0


_BANNER = r"""
  _____ _                        _
 | ____| |_ ___ _ __ _ __   __ _| |
 |  _| | __/ _ \ '__| '_ \ / _` | |
 | |___| ||  __/ |  | | | | (_| | |
 |_____|_| \___|_|  |_| |_|\__,_|_|
  ____  _      _       ____
 |  _ \(_) ___| |__   |  _ \ _ __ ___  ___  ___ _ __   ___ ___
 | |_) | |/ __| '_ \  | |_) | '__/ _ \/ __|/ _ \ '_ \ / __/ _ \
 |  _ <| | (__| | | | |  __/| | |  __/\__ \  __/ | | | (_|  __/
 |_| \_\_|\___|_| |_| |_|   |_|  \___||___/\___|_| |_|\___\___|

       by Ali Younes (@whoisaldo)
       https://github.com/whoisaldo/Eternal-Rich-Presence
"""


def main():
    if not getattr(sys, "frozen", False):
        print(_BANNER)
    log.info("EternalRichPresence starting (frozen=%s, dir=%s)", getattr(sys, "frozen", False), _app_dir)
    args = sys.argv[1:]

    try:
        from utils import register_uri_scheme
        if register_uri_scheme(silent=True):
            log.info("eternalrp:// protocol registered successfully")
        else:
            log.warning("eternalrp:// registration failed — Listen Along needs a one-time Admin run")
            print("[!] eternalrp:// registration failed. Run as Administrator once to enable Listen Along.")
    except Exception as e:
        log.warning("eternalrp:// registration error: %s", e)
        print(f"[!] eternalrp:// registration error: {e}")

    try:
        from config import CLIENT_ID as _cid
        if _cid and _cid != "YOUR_DISCORD_CLIENT_ID":
            from utils import register_discord_launch
            if register_discord_launch(_cid, silent=True):
                log.info("discord-%s:// protocol registered successfully", _cid)
            else:
                log.warning("discord-%s:// registration failed", _cid)
                print(f"[!] discord-{_cid}:// registration failed. Listen Along may not work.")
    except Exception as e:
        log.warning("Discord protocol registration error: %s", e)
        print(f"[!] Discord protocol registration error: {e}")

    if "--register-uri" in args:
        from utils import register_uri_scheme as _reg
        ok = _reg()
        msg = "URI scheme registered." if ok else "URI scheme registration failed (try Administrator)."
        log.info(msg)
        print(msg)
        return 0 if ok else 1

    if "--clear" in args:
        return _clear_presence()

    for a in args:
        if a.startswith("eternalrp://"):
            return run_listener_mode(a)
        secret = _extract_discord_join(a)
        if secret:
            return run_listener_mode(secret)

    return run_host_mode()


def _extract_discord_join(arg: str) -> str:
    """Parse ``discord-{client_id}://join/{secret}`` into the raw join secret."""
    if not arg.startswith("discord-"):
        return ""
    try:
        rest = arg.split("://", 1)
        if len(rest) < 2:
            return ""
        path = rest[1]
        if path.startswith("join/"):
            secret = urllib.parse.unquote(path[5:])
        else:
            secret = urllib.parse.unquote(path.lstrip("/"))
        if secret.startswith("eternalrp://") or ("track=" in secret):
            return secret if secret.startswith("eternalrp://") else f"eternalrp://sync?{secret}"
        return ""
    except Exception:
        return ""


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _elevate():
    """Re-launch the current process with UAC admin prompt."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = " ".join(sys.argv[1:])
    else:
        exe = sys.executable
        params = f'"{os.path.abspath(__file__)}" ' + " ".join(sys.argv[1:])
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params.strip(), None, 1
        )
    except Exception as e:
        log.error("UAC elevation failed: %s", e)


if __name__ == "__main__":
    if not _is_admin():
        _elevate()
        sys.exit(0)
    try:
        sys.exit(main())
    except Exception as _fatal:
        log.critical("Fatal crash", exc_info=True)
        _msgbox(f"EternalRichPresence crashed:\n\n{_fatal}")
        sys.exit(1)

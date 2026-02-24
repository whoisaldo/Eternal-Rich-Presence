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
        flags = 0x40 if info else 0x10
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

    if uri.startswith("eternalrp://"):
        rest = uri[len("eternalrp://"):]
        if "?" in rest:
            _, qs = rest.split("?", 1)
            params = urllib.parse.parse_qs(qs)
            if "track" in params and params["track"]:
                track_name = urllib.parse.unquote(params["track"][0])
            if "artist" in params and params["artist"]:
                artist_name = urllib.parse.unquote(params["artist"][0])
        else:
            track_name = urllib.parse.unquote(
                rest.replace("/", "").strip() or "Unknown Track"
            )

    display = f"{track_name} by {artist_name}" if artist_name else track_name
    log.info("[LISTEN ALONG] Syncing to: %s", display)

    try:
        from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            from providers.spotify import SpotifyProvider
            sp = SpotifyProvider(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
            if sp.search_and_play(track_name, artist_name):
                log.info("Playback started on Spotify: %s", display)
                return 0
    except (ImportError, Exception):
        log.debug("Spotify sync unavailable", exc_info=True)

    search_query = f"{track_name} {artist_name}".strip()
    if search_query and search_query != "Unknown Track":
        search_url = (
            "https://music.apple.com/search?term="
            + urllib.parse.quote(search_query, safe="")
        )
        try:
            import webbrowser
            webbrowser.open(search_url)
            log.info("Opened Apple Music search: %s", search_url)
        except Exception:
            log.info("Search manually: %s", search_url)

    return 0


def run_host_mode() -> int:
    """
    Poll music providers, update Discord Rich Presence, and sit in the system
    tray until the user exits.  Priority: Apple Music > Spotify.
    """
    log.info("Starting host mode")

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
        from config import CLIENT_ID
    except ImportError:
        _create_default_config()
        _msgbox(
            "First run: config.py has been created next to the app.\n\n"
            "Open config.py in Notepad, paste your Discord CLIENT_ID, "
            "save, and launch again."
        )
        return 1
    if not CLIENT_ID or CLIENT_ID == "YOUR_DISCORD_CLIENT_ID":
        _msgbox(
            "CLIENT_ID is not set.\n\n"
            "Open config.py (next to the app) and paste your Discord "
            "application Client ID."
        )
        return 1

    try:
        from config import ASSET_KEY
    except ImportError:
        ASSET_KEY = "apple_music"

    from presence import DiscordPresence

    dp = DiscordPresence(CLIENT_ID, asset_key=(ASSET_KEY or "apple_music").strip())

    def _cleanup():
        dp.disconnect()

    atexit.register(_cleanup)

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
                            tip = "EternalRichPresence"
                            if t:
                                tip = f"{t.title} — {t.artist}"[:63]
                            tray.title = tip
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
                "EternalRichPresence\n\n"
                "Created by Ali Younes (@whoisaldo)\n\n"
                "A bridge for Apple Music and Spotify\n"
                "Discord Rich Presence.\n\n"
                "https://github.com/whoisaldo/Eternal-Rich-Presence\n"
                "Aliyounes@eternalreverse.com",
                "About EternalRichPresence",
                info=True,
            )

        def on_exit(icon, _item):
            log.info("Exit requested")
            stop_event.set()
            icon.stop()

        debug_menu = pystray.Menu(
            pystray.MenuItem(_discord_status_label, lambda: None, enabled=False),
            pystray.MenuItem(
                lambda _item: f"Log: {os.path.basename(LOG_PATH)}", lambda: None, enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Log File", on_open_log),
            pystray.MenuItem("Copy Log Path", on_copy_log_path),
        )

        menu = pystray.Menu(
            pystray.MenuItem("About EternalRichPresence", on_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_now_playing_label, lambda: None, enabled=False),
            pystray.MenuItem(_provider_label, lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _item: "Resume" if paused.is_set() else "Pause",
                on_toggle,
            ),
            pystray.MenuItem("Reconnect to Discord", on_reconnect),
            pystray.MenuItem("Debug", pystray.Menu(
                pystray.MenuItem(_discord_status_label, lambda: None, enabled=False),
                pystray.MenuItem(
                    lambda _item: f"Log: {os.path.basename(LOG_PATH)}",
                    lambda: None, enabled=False,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open Log File", on_open_log),
                pystray.MenuItem("Copy Log Path", on_copy_log_path),
            )),
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


def main():
    log.info("EternalRichPresence starting (frozen=%s, dir=%s)", getattr(sys, "frozen", False), _app_dir)
    args = sys.argv[1:]

    try:
        from utils import register_uri_scheme
        register_uri_scheme(silent=True)
    except Exception:
        pass

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

    return run_host_mode()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as _fatal:
        log.critical("Fatal crash", exc_info=True)
        _msgbox(f"EternalRichPresence crashed:\n\n{_fatal}")
        sys.exit(1)

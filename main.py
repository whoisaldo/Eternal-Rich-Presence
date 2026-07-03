# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""
EternalRichPresence — Discord Rich Presence bridge for Apple Music and Spotify.

Host mode broadcasts your current track with live cover art and a Listen Along
invite via a system tray app. Listener mode handles eternalrp:// URIs to sync
playback on the receiving end.
"""

import atexit
import ctypes
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

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

from typing import TYPE_CHECKING, Optional

from app_info import (
    APP_AUTHOR,
    APP_NAME,
    APP_REPO_URL,
    APP_SUPPORT_EMAIL,
    APP_VERSION_DISPLAY,
    DEFAULT_ASSET_KEY,
    DEFAULT_SPOTIFY_REDIRECT_URI,
    EMBEDDED_CLIENT_ID,
    PLACEHOLDER_CLIENT_ID,
)
from logger import LOG_PATH, get_logger

if TYPE_CHECKING:
    from PIL import Image

log = get_logger("erp.main")

_ICON_NAME = "Apple_Music_Icon.png"
_OWN_CONSOLE_ENV = "ETERNALRP_OWN_CONSOLE"


def _create_default_config() -> None:
    """Write a starter config.py next to the exe/script if one doesn't exist."""
    cfg_path = os.path.join(_app_dir, "config.py")
    if os.path.isfile(cfg_path):
        return
    try:
        cid = EMBEDDED_CLIENT_ID or PLACEHOLDER_CLIENT_ID
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(
                "# Discord application Client ID (uses built-in if set).\n"
                f'CLIENT_ID = "{cid}"\n'
                "\n"
                f'ASSET_KEY = "{DEFAULT_ASSET_KEY}"\n'
                "\n"
                "# Optional: Spotify credentials (leave empty to disable).\n"
                'SPOTIFY_CLIENT_ID = ""\n'
                'SPOTIFY_CLIENT_SECRET = ""\n'
                f'SPOTIFY_REDIRECT_URI = "{DEFAULT_SPOTIFY_REDIRECT_URI}"\n'
                "\n"
                '# Privacy: auto-accept Discord "Listen Along" join requests.\n'
                "# Set to False to ignore join requests from people who click Join.\n"
                "AUTO_ACCEPT_JOIN_REQUESTS = True\n"
                "\n"
                "# Privacy: upload album art to a public host so Discord can show it.\n"
                "# Set to False to use the static app icon instead.\n"
                "COVER_ART_UPLOAD = True\n"
            )
        log.info("Created default config.py at %s", cfg_path)
    except Exception as e:
        log.error("Failed to create config.py: %s", e)


def _msgbox(text: str, title: str = APP_NAME, info: bool = False) -> None:
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
    except Exception as e:
        log.warning("MessageBox failed: %s", e)


def _icon_path() -> Optional[str]:
    """Resolve the tray icon image, checking PyInstaller bundle first."""
    if getattr(sys, "frozen", False):
        meipass = os.path.join(getattr(sys, "_MEIPASS", ""), _ICON_NAME)
        if os.path.isfile(meipass):
            return meipass
        beside_exe = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), _ICON_NAME)
        if os.path.isfile(beside_exe):
            return beside_exe
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), _ICON_NAME)
    if os.path.isfile(src):
        return src
    return None


def _load_tray_icon() -> "Image.Image":
    from PIL import Image

    path = _icon_path()
    if path:
        try:
            return Image.open(path)
        except Exception as e:
            log.warning("Could not load tray icon from %s: %s", path, e)
    return Image.new("RGB", (64, 64), (252, 60, 68))


def _open_apple_music_search(track_name: str, artist_name: str) -> bool:
    search_query = f"{track_name} {artist_name}".strip()
    if not search_query or search_query == "Unknown Track":
        return False

    search_url = "https://music.apple.com/search?term=" + urllib.parse.quote(search_query, safe="")
    try:
        opened = webbrowser.open(search_url)
        if opened:
            log.info("Opened Apple Music search fallback: %s", search_url)
        else:
            log.warning("Browser declined Apple Music fallback URL: %s", search_url)
        return bool(opened)
    except Exception as e:
        log.warning("Could not open browser for Apple Music search: %s — use: %s", e, search_url)
        return False


def _restart_self() -> None:
    if getattr(sys, "frozen", False):
        args = [sys.executable]
    else:
        args = [sys.executable, os.path.abspath(__file__)]
    subprocess.Popen(args, close_fds=True)


def _config_path() -> str:
    return os.path.join(_app_dir, "config.py")


def _open_path(path: str) -> None:
    os.startfile(path)


def _print_debug_paths() -> None:
    print(f"app_dir={_app_dir}")
    print(f"config={_config_path()}")
    print(f"log={LOG_PATH}")


def _should_spawn_new_console(args: list[str]) -> bool:
    """When launched from `python main.py`, move into a dedicated console window."""
    if os.name != "nt" or getattr(sys, "frozen", False):
        return False
    if os.environ.get(_OWN_CONSOLE_ENV) == "1":
        return False
    return not args


def _spawn_in_new_console(args: list[str]) -> int:
    env = os.environ.copy()
    env[_OWN_CONSOLE_ENV] = "1"
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), *args],
        cwd=_app_dir,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010),
        close_fds=False,
    )
    return 0


def _config_bool(name: str, default: bool = True) -> bool:
    """Read a boolean setting from config.py, returning ``default`` if unset."""
    try:
        import config

        return bool(getattr(config, name, default))
    except Exception:
        return default


def _build_spotify_provider():
    """Construct a SpotifyProvider from config, or None if unconfigured.

    Shared by host mode and listener mode so the Spotify bootstrap (creds,
    redirect default, provider construction) lives in exactly one place.
    """
    try:
        from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    except ImportError:
        return None
    if not (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET):
        return None
    try:
        from config import SPOTIFY_REDIRECT_URI
    except ImportError:
        SPOTIFY_REDIRECT_URI = DEFAULT_SPOTIFY_REDIRECT_URI
    redirect = SPOTIFY_REDIRECT_URI or DEFAULT_SPOTIFY_REDIRECT_URI
    from providers.spotify import SpotifyProvider

    return SpotifyProvider(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, redirect)


def run_listener_mode(uri: str) -> int:
    """
    Parse an eternalrp:// URI and attempt to start playback on the listener's
    device. Tries Spotify first (if configured), then opens an Apple Music search.
    """
    from utils import parse_join_secret

    parsed, error = parse_join_secret(uri)
    if error:
        _msgbox(
            "This Listen Along link is invalid or incomplete.\n\n"
            "Ask your friend to copy a fresh link and try again.",
            "Listen Along",
            info=True,
        )
        return 1

    track_name = parsed["track"]
    artist_name = parsed["artist"]
    position_sec = parsed["position_sec"]

    display = f"{track_name} by {artist_name}" if artist_name else track_name
    log.info("[SYNC] Attempting to join %s at %ds", display, position_sec)

    position_ms = position_sec * 1000

    try:
        sp = _build_spotify_provider()
        if sp is not None:
            if sp.search_and_play(track_name, artist_name, position_ms=position_ms):
                log.info("Playback started on Spotify: %s at %ds", display, position_sec)
                return 0
            err = sp.last_error or ""
            # Transient Spotify states (no active device / server error) tell the
            # user to retry Spotify, so don't also open an Apple Music search.
            if err == "no_active_device":
                _msgbox(
                    "Spotify is open but idle.\n\n"
                    "Please press Play on any song in your Spotify\n"
                    "app first, then try Listen Along again.",
                    "Listen Along — No Active Device",
                    info=True,
                )
                return 1
            elif err == "server_error":
                _msgbox(
                    "Spotify's servers are temporarily unavailable.\nPlease try again in a moment.",
                    "Listen Along — Spotify Error",
                    info=True,
                )
                return 1
            elif err == "premium_required":
                _msgbox(
                    "Listen Along requires a Spotify Premium account\n"
                    "to control playback remotely.\n\n"
                    "Falling back to Apple Music search.",
                    "Listen Along — Premium Required",
                    info=True,
                )
            elif err == "no_match":
                _msgbox(
                    "We couldn't find the exact Spotify track for this invite.\n\n"
                    "Opening an Apple Music search instead.",
                    "Listen Along — Track Not Found",
                    info=True,
                )
            elif err == "init_failed":
                _msgbox(
                    "Spotify isn't ready on this device yet.\n\n"
                    "Opening an Apple Music search instead.",
                    "Listen Along — Spotify Setup Needed",
                    info=True,
                )
            else:
                log.debug("Spotify join failed (reason: %s)", err)
            log.debug("Spotify search_and_play returned False, falling back to Apple Music")
    except Exception as e:
        log.warning("Spotify sync unavailable (falling back to Apple Music): %s", e, exc_info=True)

    if _open_apple_music_search(track_name, artist_name):
        return 0

    _msgbox(
        f"We couldn't start playback automatically.\n\nSearch for this track manually:\n{display}",
        "Listen Along",
        info=True,
    )
    return 1


def run_host_mode() -> int:
    """
    Poll music providers, update Discord Rich Presence, and sit in the system
    tray until the user exits.
    """
    log.info("Starting host mode")

    setup_completed = False
    cfg_path = _config_path()

    # Zero-config first run: if we ship an embedded Client ID and no config
    # exists yet, write one so the setup GUI can be skipped.
    if EMBEDDED_CLIENT_ID and not os.path.isfile(cfg_path):
        _create_default_config()
        if "config" in sys.modules:
            import importlib

            importlib.reload(sys.modules["config"])
        log.info("Created config with embedded Discord Client ID")

    # Resolve and validate CLIENT_ID on a live path: a missing config, or one
    # still holding the placeholder, must trigger the setup GUI. (Previously this
    # check was unreachable, so a placeholder config silently failed to connect.)
    try:
        from config import CLIENT_ID

        needs_setup = not CLIENT_ID or CLIENT_ID == PLACEHOLDER_CLIENT_ID
    except ImportError:
        needs_setup = True

    if needs_setup:
        log.info("Config missing or incomplete — launching setup GUI")
        try:
            from setup_gui import run_setup_gui

            if not run_setup_gui():
                log.info("Setup cancelled by user")
                return 1
            setup_completed = True
            import importlib

            if "config" in sys.modules:
                importlib.reload(sys.modules["config"])
            from config import CLIENT_ID

            if not CLIENT_ID or CLIENT_ID == PLACEHOLDER_CLIENT_ID:
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

    from manager import ProviderManager

    provider_list = []

    try:
        spotify_provider = _build_spotify_provider()
        if spotify_provider is not None:
            provider_list.append(spotify_provider)
            log.info("Spotify provider loaded")
    except Exception:
        log.warning("Spotify provider not loaded", exc_info=True)

    try:
        from providers.apple_music import AppleMusicProvider

        provider_list.append(AppleMusicProvider())
        log.info("Apple Music provider loaded")
    except Exception:
        log.warning("Apple Music provider not loaded", exc_info=True)

    if not provider_list:
        _msgbox(
            "EternalRichPresence couldn't start either music provider.\n\n"
            "Open the setup window or reinstall the app and try again."
        )
        return 1

    mgr = ProviderManager(provider_list)

    try:
        from config import ASSET_KEY
    except ImportError:
        ASSET_KEY = DEFAULT_ASSET_KEY

    from presence import DiscordConnectionError, DiscordPresence

    dp = DiscordPresence(
        CLIENT_ID,
        asset_key=(ASSET_KEY or DEFAULT_ASSET_KEY).strip(),
        cover_upload=_config_bool("COVER_ART_UPLOAD", True),
    )

    def _cleanup():
        dp.disconnect()

    atexit.register(_cleanup)

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

        evt_listener = DiscordEventListener(
            CLIENT_ID,
            _on_join_event,
            auto_accept=_config_bool("AUTO_ACCEPT_JOIN_REQUESTS", True),
        )
        evt_listener.start()
        log.info("Discord event listener started")
    except Exception as e:
        log.warning("Discord event listener failed to start: %s", e)

    stop_event = threading.Event()
    paused = threading.Event()
    interval = 5
    tray = None

    def _refresh_tray_title(current_track=None):
        if tray is None:
            return
        if paused.is_set():
            tip = f"{APP_NAME} | Paused"
        elif current_track:
            src = mgr.active_provider.name if mgr.active_provider else "Music"
            tip = f"{APP_NAME} | {src}\n{current_track.title} — {current_track.artist}"
        elif mgr.state == "paused":
            tip = f"{APP_NAME} | Playback paused"
        elif mgr.state == "error":
            tip = f"{APP_NAME} | {mgr.status_detail}"
        else:
            tip = f"{APP_NAME} | Idle"
        tray.title = tip[:127]

    def _poll_loop():
        while not stop_event.is_set():
            if not paused.is_set():
                try:
                    if not dp.is_connected:
                        try:
                            dp.connect()
                            log.info("Connected to Discord RPC")
                        except Exception as e:
                            log.debug("Discord RPC connect retry failed: %s", e)

                    t = mgr.get_now_playing()
                    if dp.is_connected:
                        if t is None:
                            dp.clear()
                        else:
                            name = mgr.active_provider.name if mgr.active_provider else ""
                            dp.update(t, name)
                            if paused.is_set():
                                # Pause raced the in-flight update; undo it so
                                # the presence doesn't stay stuck visible.
                                dp.clear()
                    _refresh_tray_title(t)
                except DiscordConnectionError as e:
                    log.warning("Discord connection dropped, retrying: %s", e)
                except Exception as e:
                    log.warning("Poll error (will retry): %s", e, exc_info=True)
            stop_event.wait(interval)

    poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    poll_thread.start()

    import signal

    def _sigint_handler(_sig, _frame):
        stop_event.set()
        if tray:
            try:
                tray.stop()
            except Exception as e:
                log.debug("Tray stop on SIGINT: %s", e)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        import pystray

        icon_image = _load_tray_icon()

        def _status_label(_item):
            if paused.is_set():
                return "Status: Paused"
            if mgr.state == "error":
                return "Status: Needs attention"
            if mgr.state == "paused":
                return "Status: Playback paused"
            if mgr.state == "playing":
                return "Status: Live"
            return "Status: Waiting for music"

        def _now_playing_label(_item):
            t = dp.current_track
            if paused.is_set():
                return "Paused"
            if mgr.state == "error":
                return mgr.status_detail
            if mgr.state == "paused":
                return "Playback paused"
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
            return "Discord: Connected" if dp.is_connected else "Discord: Disconnected"

        def _details_label(_item):
            return mgr.status_detail

        def on_toggle(_icon, _item):
            if paused.is_set():
                paused.clear()
                log.info("Resumed")
            else:
                paused.set()
                dp.clear()
                log.info("Paused")
            _refresh_tray_title()

        def on_reconnect(_icon, _item):
            log.info("Manual reconnect requested")
            try:
                dp.clear()
                dp.disconnect()
                dp.connect()
                # Deliberately does NOT resume a paused session: a user who
                # paused broadcasting for privacy keeps that choice.
                log.info("Reconnected to Discord RPC")
            except Exception as e:
                log.error("Reconnect failed: %s", e)
                _msgbox(
                    "Discord couldn't be reached right now.\n\n"
                    "Make sure Discord is open, then try again.",
                    "Reconnect to Discord",
                )

        def on_open_log(_icon, _item):
            log.info("Opening log file: %s", LOG_PATH)
            try:
                os.startfile(LOG_PATH)
            except Exception as e:
                log.warning("Could not open log file: %s", e)
                _msgbox(f"Log file:\n{LOG_PATH}")

        def on_open_setup(_icon, _item):
            try:
                from setup_gui import run_setup_gui

                if run_setup_gui():
                    _msgbox(
                        "Your settings were saved.\n\n"
                        "EternalRichPresence will restart now so everything refreshes cleanly.",
                        "Settings Saved",
                        info=True,
                    )
                    _restart_self()
                    stop_event.set()
                    _icon.stop()
            except Exception as e:
                log.error("Could not open setup window: %s", e, exc_info=True)
                _msgbox(
                    "The setup window couldn't be opened.\n\n"
                    f"Check the log file for details:\n{LOG_PATH}"
                )

        def on_open_config(_icon, _item):
            try:
                if not os.path.isfile(_config_path()):
                    _create_default_config()
                _open_path(_config_path())
            except Exception as e:
                log.error("Could not open config file: %s", e, exc_info=True)
                _msgbox(f"The config file couldn't be opened.\n\nPath:\n{_config_path()}")

        def on_open_app_folder(_icon, _item):
            try:
                _open_path(_app_dir)
            except Exception as e:
                log.error("Could not open app folder: %s", e, exc_info=True)
                _msgbox(f"The app folder couldn't be opened.\n\nPath:\n{_app_dir}")

        def on_repair_listen_along(_icon, _item):
            try:
                from utils import register_discord_launch, register_uri_scheme

                ok_uri = register_uri_scheme()
                ok_discord = register_discord_launch(CLIENT_ID)
                if ok_uri and ok_discord:
                    _msgbox(
                        "Listen Along links are ready for this Windows account.",
                        "Repair Listen Along",
                        info=True,
                    )
                else:
                    _msgbox(
                        "Some link handlers could not be refreshed.\n\n"
                        "Open Dev > Open Log File for details.",
                        "Repair Listen Along",
                    )
            except Exception as e:
                log.error("Listen Along repair failed: %s", e, exc_info=True)
                _msgbox(
                    f"Listen Along repair failed.\n\nCheck the log file for details:\n{LOG_PATH}"
                )

        def on_copy_log_path(_icon, _item):
            try:
                subprocess.run(
                    ["clip"], input=LOG_PATH.encode(), check=True, creationflags=0x08000000
                )
                log.debug("Log path copied to clipboard")
            except Exception as e:
                log.warning("Clipboard copy failed: %s", e)
                _msgbox(f"Log path:\n{LOG_PATH}")

        def on_help(_icon, _item):
            webbrowser.open(APP_REPO_URL)

        def on_print_paths(_icon, _item):
            log.info("App directory: %s", _app_dir)
            log.info("Config path: %s", _config_path())
            log.info("Log path: %s", LOG_PATH)
            _print_debug_paths()

        def on_about(_icon, _item):
            _msgbox(
                f"{APP_NAME}  v{APP_VERSION_DISPLAY}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Created by {APP_AUTHOR}\n\n"
                "Discord Rich Presence bridge for\n"
                "Apple Music and Spotify — with live\n"
                "cover art and Listen Along.\n\n"
                "Official repo:\n"
                "github.com/whoisaldo/Eternal-Rich-Presence\n\n"
                f"Contact: {APP_SUPPORT_EMAIL}\n\n"
                "© 2026 Ali Younes — licensed under GPL-3.0-or-later.",
                f"About {APP_NAME}",
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
            pos = int(t.position_sec) if t.position_sec is not None else 0
            from utils import build_join_secret

            return build_join_secret(t.title, t.artist, pos)

        def on_copy_listen_link(_icon, _item):
            link = _build_listen_link()
            if link is None:
                _msgbox(
                    "No track is currently playing.\nStart playing music first.",
                    "Listen Along",
                    info=True,
                )
                return
            try:
                subprocess.run(["clip"], input=link.encode(), check=True, creationflags=0x08000000)
                log.info("Listen Along link copied: %s", link)
            except Exception as e:
                log.warning("Clipboard copy failed: %s — showing link in dialog", e)
                _msgbox(f"Listen Along link:\n{link}", info=True)

        def on_log_join_secret(_icon, _item):
            link = _build_listen_link()
            if link is None:
                log.info("[DEBUG] No track playing — no join_secret to show")
                return
            log.info("[DEBUG] Current join_secret: %s", link)

        dev_menu = pystray.Menu(
            pystray.MenuItem(_discord_status_label, lambda: None, enabled=False),
            pystray.MenuItem(_details_label, lambda: None, enabled=False),
            pystray.MenuItem(
                lambda _item: f"Log: {os.path.basename(LOG_PATH)}",
                lambda: None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Setup", on_open_setup),
            pystray.MenuItem("Open Config File", on_open_config),
            pystray.MenuItem("Open App Folder", on_open_app_folder),
            pystray.MenuItem("Print Paths To Console", on_print_paths),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Log Join Secret", on_log_join_secret),
            pystray.MenuItem("Open Log File", on_open_log),
            pystray.MenuItem("Copy Log Path", on_copy_log_path),
        )

        menu = pystray.Menu(
            pystray.MenuItem(f"About {APP_NAME}", on_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_status_label, lambda: None, enabled=False),
            pystray.MenuItem(_now_playing_label, lambda: None, enabled=False),
            pystray.MenuItem(_provider_label, lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Copy Listen Along Link", on_copy_listen_link),
            pystray.MenuItem("Repair Listen Along", on_repair_listen_along),
            pystray.MenuItem(
                lambda _item: "Resume" if paused.is_set() else "Pause",
                on_toggle,
            ),
            pystray.MenuItem("Reconnect to Discord", on_reconnect),
            pystray.MenuItem("Help", on_help),
            pystray.MenuItem("Dev", dev_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", on_exit),
        )

        tray = pystray.Icon(APP_NAME, icon_image, APP_NAME, menu)
        log.info("System tray started")
        _refresh_tray_title()
        if setup_completed:
            _msgbox(
                "Setup is complete.\n\n"
                "EternalRichPresence is now running in your system tray.\n"
                "Right-click the tray icon any time for controls or troubleshooting.",
                "Setup Complete",
                info=True,
            )
        tray.run()
    except Exception as e:
        log.exception("System tray failed")
        _msgbox(
            f"System tray failed to start:\n{e}\n\nFalling back to console mode (Ctrl+C to quit)."
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
    if not CLIENT_ID or CLIENT_ID == PLACEHOLDER_CLIENT_ID:
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
        except Exception as e:
            log.debug("clear(pid=0) failed (non-fatal): %s", e)
        try:
            rpc.update(state="", details="", pid=os.getpid())
            time.sleep(0.3)
            rpc.clear(pid=os.getpid())
        except Exception as e:
            log.debug("Interim clear failed (non-fatal): %s", e)
        log.info("Rich Presence cleared")
    except Exception as e:
        log.error("Could not clear presence: %s", e, exc_info=True)
        _msgbox(f"Could not clear (is Discord running?):\n{e}")
        return 1
    finally:
        try:
            rpc.close()
        except Exception as e:
            log.debug("RPC close: %s", e)
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


def main() -> int:
    if not getattr(sys, "frozen", False):
        print(_BANNER)
    log.info("%s starting (frozen=%s, dir=%s)", APP_NAME, getattr(sys, "frozen", False), _app_dir)
    args = sys.argv[1:]

    if _should_spawn_new_console(args):
        log.info("Re-launching in a dedicated console window")
        return _spawn_in_new_console(args)

    try:
        from utils import register_uri_scheme

        if register_uri_scheme(silent=True):
            log.info("eternalrp:// protocol registered successfully")
        else:
            log.warning("eternalrp:// registration failed for the current Windows user")
    except Exception as e:
        log.warning("eternalrp:// registration error: %s", e)

    try:
        from config import CLIENT_ID as _cid

        if _cid and _cid != PLACEHOLDER_CLIENT_ID:
            from utils import register_discord_launch

            if register_discord_launch(_cid, silent=True):
                log.info("discord-%s:// protocol registered successfully", _cid)
            else:
                log.warning("discord-%s:// registration failed", _cid)
    except Exception as e:
        log.warning("Discord protocol registration error: %s", e)

    if "--register-uri" in args:
        from utils import register_uri_scheme as _reg

        ok = _reg()
        msg = (
            "Listen Along link registration is ready for this Windows account."
            if ok
            else "Listen Along link registration failed."
        )
        log.info(msg)
        _msgbox(msg, "Listen Along Registration", info=ok)
        return 0 if ok else 1

    if "--setup" in args:
        from setup_gui import run_setup_gui

        return 0 if run_setup_gui() else 1

    if "--open-config" in args:
        if not os.path.isfile(_config_path()):
            _create_default_config()
        _open_path(_config_path())
        return 0

    if "--open-log" in args:
        _open_path(LOG_PATH)
        return 0

    if "--print-paths" in args:
        _print_debug_paths()
        return 0

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
    except Exception as e:
        log.debug("_extract_discord_join failed for %r: %s", arg[:80] if arg else "", e)
        return ""


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as _fatal:
        log.critical("Fatal crash", exc_info=True)
        _msgbox(f"{APP_NAME} crashed:\n\n{_fatal}")
        sys.exit(1)

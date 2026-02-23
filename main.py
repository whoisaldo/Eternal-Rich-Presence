"""
EternalRichPresence - Mock "Listen Along" status for Apple Music via Discord Rich Presence.
Dual-mode: Host (iTunes COM + Discord RPC) or Listener (eternalrp:// URI handler).
"""

import asyncio
import atexit
import hashlib
import os
import sys
import time
import urllib.parse
import urllib.request

# Set in host mode so atexit can clear presence when script exits (any reason)
_host_rpc = None

# Ensure config.py is loaded from the app directory (script dir or exe dir when frozen)
_app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
if _app_dir and _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)


def _upload_cover_to_catbox(thumbnail_bytes):
    """Upload cover art to catbox.moe (anonymous, no API key). Returns public URL or None."""
    if not thumbnail_bytes or len(thumbnail_bytes) > 20 * 1024 * 1024:  # 20MB limit
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
            if url and "catbox.moe" in url and (url.startswith("https://") or url.startswith("http://")) and len(url) < 500:
                return url
    except Exception:
        pass
    return None


def register_uri_scheme(exe_path=None):
    """
    Register the eternalrp:// URI scheme in the Windows Registry.
    HKEY_CLASSES_ROOT\\eternalrp -> command runs sys.executable (or given exe_path) with %1.
    Requires administrator privileges to write to HKCR.
    """
    try:
        import winreg
    except ImportError:
        print("Registry access requires Python on Windows with standard library.", file=sys.stderr)
        return False

    cmd = exe_path or sys.executable
    # Ensure %1 is passed so the handler receives the full eternalrp://... URI
    command = f'"{cmd}" "%1"'

    try:
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, "eternalrp") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:Eternal Rich Presence")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r"eternalrp\shell\open\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command)
        return True
    except OSError as e:
        print(f"Failed to register URI scheme (try running as Administrator): {e}", file=sys.stderr)
        return False


def run_listener_mode(uri):
    """
    Listener mode: parse eternalrp:// URI, display sync info, and attempt to
    open the track in the default browser (Apple Music search) for listen-along.
    URI format: eternalrp://sync?track=<Track>&artist=<Artist>
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
            track_name = urllib.parse.unquote(rest.replace("/", "").strip() or "Unknown Track")

    if artist_name:
        display = f"{track_name} by {artist_name}"
    else:
        display = track_name

    print(f"[LISTEN ALONG] Now syncing to: {display}")

    search_query = f"{track_name} {artist_name}".strip()
    if search_query and search_query != "Unknown Track":
        search_url = "https://music.apple.com/search?term=" + urllib.parse.quote(search_query, safe="")
        try:
            import webbrowser
            webbrowser.open(search_url)
            print(f"Opened Apple Music search: {search_url}")
        except Exception:
            print(f"Search manually: {search_url}")
    return 0


def _get_now_playing_smtc():
    """
    Get now-playing from Windows System Media Transport Controls (works with
    Apple Music app, Spotify, etc.). Returns (details, state, position_sec, thumbnail_bytes, error_msg).
    thumbnail_bytes is cover art when available; error_msg is set when no data could be read.
    """
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
    except ImportError:
        return None, None, None, None, "winrt-Windows.Media.Control not installed. Run: pip install winrt-Windows.Media.Control"

    async def _fetch():
        err = None
        try:
            manager = await MediaManager.request_async()
            session = manager.get_current_session()
            sessions_to_try = [session] if session else []
            if not sessions_to_try:
                try:
                    all_sessions = manager.get_sessions()
                    if all_sessions:
                        sessions_to_try = list(all_sessions)
                except Exception:
                    pass
            for s in sessions_to_try:
                if s is None:
                    continue
                try:
                    props = await s.try_get_media_properties_async()
                    if not props:
                        continue
                    title = (props.title or "Unknown").strip() or "Unknown"
                    artist = (props.artist or "Unknown Artist").strip() or "Unknown Artist"
                    pos_sec = None
                    try:
                        timeline = s.get_timeline_properties()
                        if timeline:
                            pos = getattr(timeline, "position", None)
                            if pos is not None and hasattr(pos, "total_seconds"):
                                pos_sec = int(pos.total_seconds())
                    except Exception:
                        pass
                    # Try to read cover art thumbnail
                    thumbnail_bytes = None
                    try:
                        thumb_ref = getattr(props, "thumbnail", None)
                        if thumb_ref is not None:
                            from winrt.windows.storage.streams import Buffer, InputStreamOptions
                            stream = await thumb_ref.open_read_async()
                            buf = Buffer(2 * 1024 * 1024)
                            await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
                            n = getattr(buf, "length", buf.capacity)
                            thumbnail_bytes = bytes(bytearray(buf)[:n])
                    except Exception:
                        pass
                    return title, artist, pos_sec, thumbnail_bytes, None
                except Exception:
                    continue
            if not sessions_to_try:
                err = "No media sessions found. Play a song in Apple Music (or another app) and try again."
            else:
                err = "No session had track info. Try pausing and resuming playback."
            return None, None, None, None, err
        except Exception as e:
            return None, None, None, None, str(e)

    try:
        return asyncio.run(_fetch())
    except Exception as e:
        return None, None, None, None, str(e)


def run_host_mode():
    """
    Host mode: poll iTunes (COM) or Windows SMTC every 5s and update Discord RPC
    with party_id and join_secret (eternalrp://sync?track=...).
    Tries iTunes first; if unavailable (e.g. Apple Music app), uses system media.
    """
    itunes = None
    try:
        import win32com.client
    except ImportError:
        pass  # will use SMTC only
    else:
        try:
            itunes = win32com.client.Dispatch("iTunes.Application")
            # Quick touch to see if it's actually usable (e.g. old iTunes)
            _ = itunes.CurrentTrack
        except Exception:
            itunes = None

    if itunes is None:
        # Use Windows System Media Transport Controls (Apple Music app, Spotify, etc.)
        name, artist, pos, _thumb, smtc_err = _get_now_playing_smtc()
        if name is None and artist is None:
            print("Could not connect to iTunes (legacy app).", file=sys.stderr)
            if smtc_err:
                print(smtc_err, file=sys.stderr)
            else:
                print(
                    "Start Apple Music (or another player), play something, then run again.",
                    file=sys.stderr,
                )
            return 1
        print("Using Windows system media (Apple Music / current player).", file=sys.stderr)
        use_smtc = True
    else:
        use_smtc = False

    try:
        from pypresence import Presence
    except ImportError:
        print("Host mode requires pypresence (pip install pypresence).", file=sys.stderr)
        return 1

    try:
        from config import CLIENT_ID
    except ImportError:
        print("Create config.py with CLIENT_ID from Discord Developer Portal.", file=sys.stderr)
        return 1

    if not CLIENT_ID or CLIENT_ID == "YOUR_DISCORD_CLIENT_ID":
        print("Set your Discord CLIENT_ID in config.py.", file=sys.stderr)
        return 1

    try:
        from config import ASSET_KEY
    except ImportError:
        ASSET_KEY = "apple_music"
    large_image_value = (ASSET_KEY or "apple_music").strip()

    rpc = Presence(CLIENT_ID)
    try:
        rpc.connect()
    except Exception as e:
        print(f"Discord RPC connect failed (is Discord running?): {e}", file=sys.stderr)
        return 1

    global _host_rpc
    _host_rpc = rpc
    _clear_on_exit_registered = False

    def _clear_on_exit():
        global _host_rpc
        if _host_rpc is not None:
            try:
                _host_rpc.clear(pid=os.getpid())
                time.sleep(0.5)
                _host_rpc.close()
            except Exception:
                pass
            _host_rpc = None

    atexit.register(_clear_on_exit)
    _clear_on_exit_registered = True

    party_id = "eternal-session-1"
    interval = 5  # Poll every 5s so Discord timer and song stay in sync
    last_track_key = None
    last_cover_thumb_hash = None
    cached_cover_url = None

    try:
        while True:
            try:
                have_cover = False
                cover_url = None
                if use_smtc:
                    name, artist, pos, thumbnail_bytes, _ = _get_now_playing_smtc()
                    if thumbnail_bytes:
                        thumb_hash = hashlib.sha1(thumbnail_bytes).hexdigest()
                        if thumb_hash != last_cover_thumb_hash:
                            last_cover_thumb_hash = thumb_hash
                            cached_cover_url = _upload_cover_to_catbox(thumbnail_bytes)
                        cover_url = cached_cover_url
                        have_cover = bool(cover_url)
                    else:
                        last_cover_thumb_hash = None
                        cached_cover_url = None
                    if name is None and artist is None:
                        state = "No track"
                        details = "Apple Music"
                        join_secret = "eternalrp://sync?track=&artist="
                        pos_sec = None
                    else:
                        state = f"by {artist}"
                        details = name or "Unknown"
                        safe_track = urllib.parse.quote(details, safe="")
                        safe_artist = urllib.parse.quote(artist or "", safe="")
                        join_secret = f"eternalrp://sync?track={safe_track}&artist={safe_artist}"
                        pos_sec = pos
                else:
                    track = itunes.CurrentTrack
                    if track is None:
                        state = "No track"
                        details = "Apple Music"
                        join_secret = "eternalrp://sync?track=&artist="
                        pos_sec = None
                    else:
                        name = getattr(track, "Name", None) or "Unknown"
                        artist = getattr(track, "Artist", None) or "Unknown Artist"
                        pos_sec = getattr(itunes, "PlayerPosition", 0) or 0
                        state = f"by {artist}"
                        details = name
                        safe_track = urllib.parse.quote(name, safe="")
                        safe_artist = urllib.parse.quote(artist, safe="")
                        join_secret = f"eternalrp://sync?track={safe_track}&artist={safe_artist}"

                update_kw = dict(
                    state=state,
                    details=details,
                    party_id=party_id,
                    party_size=[1, 2],
                    join=join_secret,
                    start=int(time.time() - int(pos_sec)) if pos_sec is not None else None,
                )
                if have_cover and cover_url:
                    update_kw["large_image"] = cover_url
                else:
                    update_kw["large_image"] = large_image_value
                if details and details != "Apple Music":
                    update_kw["large_text"] = details

                track_key = f"{details}|{state}"
                if track_key != last_track_key:
                    last_track_key = track_key
                    if details == "Apple Music" and state == "No track":
                        print("Now playing: (nothing)")
                    else:
                        artist_part = state[3:] if state.startswith("by ") else state
                        print(f"Now playing: {details} — {artist_part}")

                # Clear then set every time so Discord always shows current song and timer
                try:
                    rpc.clear()
                except Exception:
                    pass
                rpc.update(**update_kw)
            except Exception as e:
                print(f"Update error: {e}", file=sys.stderr)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        if _clear_on_exit_registered:
            atexit.unregister(_clear_on_exit)
        # Clear presence on exit (same process that set it) so Discord removes it
        try:
            rpc.clear(pid=os.getpid())
            time.sleep(0.5)
        except Exception:
            pass
        try:
            rpc.close()
        except Exception:
            pass
        _host_rpc = None
    return 0


def _clear_presence():
    """Connect to Discord RPC and clear current presence (removes stuck activity)."""
    try:
        from config import CLIENT_ID
    except ImportError:
        print("config.py with CLIENT_ID required.", file=sys.stderr)
        return 1
    if not CLIENT_ID or CLIENT_ID == "YOUR_DISCORD_CLIENT_ID":
        print("Set CLIENT_ID in config.py.", file=sys.stderr)
        return 1
    try:
        from pypresence import Presence
    except ImportError:
        print("pypresence required: pip install pypresence", file=sys.stderr)
        return 1
    rpc = Presence(CLIENT_ID)
    try:
        rpc.connect()
        # Clear for current process
        rpc.clear(pid=os.getpid())
        # Clear for pid 0 in case Discord uses it for "active" activity
        try:
            rpc.clear(pid=0)
        except Exception:
            pass
        # Overwrite with empty-looking activity then clear again (helps with stuck display)
        try:
            rpc.update(state="", details="", pid=os.getpid())
            time.sleep(0.3)
            rpc.clear(pid=os.getpid())
        except Exception:
            pass
        print("Rich Presence cleared. If it persists, quit Discord from the system tray and reopen.")
    except Exception as e:
        print(f"Could not clear (is Discord running?): {e}", file=sys.stderr)
        return 1
    finally:
        try:
            rpc.close()
        except Exception:
            pass
    return 0


def main():
    args = sys.argv[1:]
    # Register URI scheme and exit (e.g. main.py --register-uri)
    if "--register-uri" in args:
        ok = register_uri_scheme()
        return 0 if ok else 1
    # Clear stuck Rich Presence (e.g. main.py --clear)
    if "--clear" in args:
        return _clear_presence()
    # Listener mode: any argument starting with eternalrp://
    for a in args:
        if a.startswith("eternalrp://"):
            return run_listener_mode(a)
    # Host mode: no relevant args
    return run_host_mode()


if __name__ == "__main__":
    sys.exit(main())

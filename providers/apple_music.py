import asyncio
import sys
import threading
from typing import Optional

from logger import get_logger
from .base import BaseProvider, TrackInfo

log = get_logger("erp.apple_music")

# winrt on Python 3.13 fires "Event loop is closed" from a native callback
# after asyncio.run() has already returned the data.  Suppress via every
# hook Python exposes for unhandled/unraisable exceptions.
_orig_threading_hook = threading.excepthook
_orig_unraisable_hook = sys.unraisablehook


def _quiet_threading_hook(args):
    if args.exc_type is RuntimeError and "Event loop is closed" in str(args.exc_value):
        return
    _orig_threading_hook(args)


def _quiet_unraisable_hook(unraisable):
    if isinstance(unraisable.exc_value, RuntimeError) and "Event loop is closed" in str(unraisable.exc_value):
        return
    _orig_unraisable_hook(unraisable)


threading.excepthook = _quiet_threading_hook
sys.unraisablehook = _quiet_unraisable_hook


class AppleMusicProvider(BaseProvider):
    """
    Reads now-playing via iTunes COM automation (legacy desktop app)
    or Windows SMTC (modern Apple Music / any system player).
    """

    def __init__(self):
        self._itunes = None
        self._use_smtc = False
        self._init_source()

    @property
    def name(self) -> str:
        return "Apple Music"

    def _init_source(self):
        try:
            import win32com.client
            self._itunes = win32com.client.Dispatch("iTunes.Application")
            _ = self._itunes.CurrentTrack
            log.debug("Using iTunes COM")
        except Exception:
            self._itunes = None
            self._use_smtc = True
            log.debug("iTunes COM unavailable, using SMTC")

    def is_available(self) -> bool:
        if self._itunes is not None:
            try:
                _ = self._itunes.CurrentTrack
                return True
            except Exception:
                return False
        return self._poll_smtc() is not None

    def get_now_playing(self) -> Optional[TrackInfo]:
        if self._itunes is not None:
            return self._poll_itunes()
        return self._poll_smtc()

    def _poll_itunes(self) -> Optional[TrackInfo]:
        try:
            track = self._itunes.CurrentTrack
            if track is None:
                return None
            return TrackInfo(
                title=getattr(track, "Name", None) or "Unknown",
                artist=getattr(track, "Artist", None) or "Unknown Artist",
                album=getattr(track, "Album", None) or "",
                position_sec=getattr(self._itunes, "PlayerPosition", 0) or 0,
            )
        except Exception:
            return None

    def _poll_smtc(self) -> Optional[TrackInfo]:
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            )
        except ImportError:
            return None

        async def _fetch():
            try:
                manager = await MediaManager.request_async()
                session = manager.get_current_session()
                sessions = [session] if session else []
                if not sessions:
                    try:
                        all_s = manager.get_sessions()
                        if all_s:
                            sessions = list(all_s)
                    except Exception:
                        pass

                for s in sessions:
                    if s is None:
                        continue
                    try:
                        props = await s.try_get_media_properties_async()
                        if not props:
                            continue

                        title = (props.title or "Unknown").strip() or "Unknown"
                        artist = (props.artist or "Unknown Artist").strip() or "Unknown Artist"
                        album = (getattr(props, "album_title", "") or "").strip()

                        pos_sec = None
                        try:
                            timeline = s.get_timeline_properties()
                            if timeline:
                                pos = getattr(timeline, "position", None)
                                if pos is not None and hasattr(pos, "total_seconds"):
                                    pos_sec = int(pos.total_seconds())
                        except Exception:
                            pass

                        thumbnail_bytes = await self._read_thumbnail(props)

                        return TrackInfo(
                            title=title,
                            artist=artist,
                            album=album,
                            position_sec=pos_sec,
                            cover_art=thumbnail_bytes,
                        )
                    except Exception:
                        continue
                return None
            except Exception:
                return None

        result = [None]

        def _run_in_thread():
            try:
                result[0] = asyncio.run(_fetch())
            except Exception as e:
                log.debug("SMTC fetch error: %s", e)

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        t.join(timeout=15)
        return result[0]

    @staticmethod
    async def _read_thumbnail(props) -> bytes | None:
        """Read cover art with a short timeout; returns None on any failure."""
        try:
            thumb_ref = getattr(props, "thumbnail", None)
            if thumb_ref is None:
                return None

            async def _do_read():
                from winrt.windows.storage.streams import Buffer, InputStreamOptions
                stream = await thumb_ref.open_read_async()
                buf = Buffer(2 * 1024 * 1024)
                await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
                n = getattr(buf, "length", buf.capacity)
                return bytes(bytearray(buf)[:n])

            return await asyncio.wait_for(_do_read(), timeout=3)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            return None

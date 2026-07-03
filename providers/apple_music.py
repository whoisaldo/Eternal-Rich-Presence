# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

import asyncio
import concurrent.futures
import threading
import time
from datetime import datetime
from typing import Optional

from logger import get_logger

from .base import BaseProvider, TrackInfo

log = get_logger("erp.apple_music")

_WIN_EPOCH_OFFSET = 116444736000000000  # 100ns ticks between 1601-01-01 and 1970-01-01

_PLAYBACK_PLAYING = 4
_PLAYBACK_PAUSED = 5


def _looks_like_apple_source(app_id: str) -> bool:
    norm = (app_id or "").lower()
    return "itunes" in norm or "applemusic" in norm or "apple music" in norm


def _smtc_elapsed_since_update(timeline) -> float:
    """Return seconds elapsed since SMTC last updated the timeline snapshot.

    SMTC freezes ``position`` at the moment of the last state change.
    We compensate by adding wall-clock time that has passed since then.

    Depending on the pywinrt version, ``last_updated_time`` projects either as
    a timezone-aware ``datetime`` (current releases) or as a struct exposing
    FILETIME ticks via ``universal_time`` (older releases) — handle both, or
    the compensation silently returns 0 and the position freezes.
    """
    try:
        lut = getattr(timeline, "last_updated_time", None)
        if lut is None:
            return 0.0
        if isinstance(lut, datetime):
            updated_unix = lut.timestamp()
        else:
            filetime = getattr(lut, "universal_time", None)
            if filetime is None or filetime == 0:
                return 0.0
            updated_unix = (filetime - _WIN_EPOCH_OFFSET) / 10_000_000
        return max(0.0, time.time() - updated_unix)
    except Exception as e:
        log.debug("_smtc_elapsed_since_update: %s", e)
        return 0.0


class AppleMusicProvider(BaseProvider):
    """
    Reads now-playing via iTunes COM automation (legacy desktop app)
    or Windows SMTC (modern Apple Music / any system player).
    """

    _ITUNES_REPROBE_INTERVAL = 30.0

    def __init__(self):
        self._itunes = None
        self._itunes_retry_at = 0.0
        self._com_initialized = False
        self._loop = None
        self._loop_thread = None
        self._last_smtc = None
        self._thumb_cache = (None, None)  # (track key, bytes)

    @property
    def name(self) -> str:
        return "Apple Music"

    def _get_itunes(self):
        """Attach to a *running* iTunes instance, never launching one.

        Runs lazily on the polling thread so the COM proxy lives in the
        apartment of the thread that actually uses it — creating it on the
        main thread made every cross-thread call fail silently. GetActiveObject
        only attaches to an existing process; Dispatch would boot iTunes.exe on
        every app start for anyone who merely has it installed.
        """
        now = time.monotonic()
        if now < self._itunes_retry_at:
            return None
        try:
            import pythoncom
            import win32com.client
        except ImportError:
            self._itunes_retry_at = float("inf")
            return None
        try:
            if not self._com_initialized:
                pythoncom.CoInitialize()
                self._com_initialized = True
            itunes = win32com.client.GetActiveObject("iTunes.Application")
            _ = itunes.CurrentTrack
            log.debug("Attached to running iTunes via COM")
            return itunes
        except Exception as e:
            log.debug("iTunes COM not available (%s); re-probing later", e)
            self._itunes_retry_at = now + self._ITUNES_REPROBE_INTERVAL
            return None

    def get_now_playing(self) -> Optional[TrackInfo]:
        # iTunes COM first (richer data for legacy users), SMTC otherwise. A
        # dead or absent iTunes falls straight through to SMTC in the same
        # poll instead of blanking the presence until an app restart.
        track = self._poll_itunes()
        if track is not None:
            return track
        return self._poll_smtc()

    def _poll_itunes(self) -> Optional[TrackInfo]:
        if self._itunes is None:
            self._itunes = self._get_itunes()
        if self._itunes is None:
            return None
        try:
            track = self._itunes.CurrentTrack
            if track is None:
                return None
            state = int(getattr(self._itunes, "PlayerState", 0) or 0)
            return TrackInfo(
                title=getattr(track, "Name", None) or "Unknown",
                artist=getattr(track, "Artist", None) or "Unknown Artist",
                album=getattr(track, "Album", None) or "",
                position_sec=getattr(self._itunes, "PlayerPosition", 0) or 0,
                is_playing=(state == 1),
            )
        except Exception as e:
            # iTunes quit or the COM link died: drop the handle so SMTC takes
            # over on this very poll, and re-probe for iTunes later.
            log.debug("iTunes COM poll failed (%s); falling back to SMTC", e)
            self._itunes = None
            self._itunes_retry_at = time.monotonic() + self._ITUNES_REPROBE_INTERVAL
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
                # Always enumerate every session: when another app (browser
                # video, a game) owns the "current" session, the playing Apple
                # Music session only shows up in the full list. The current
                # session goes first for priority; seen_ids dedups it below.
                sessions = []
                try:
                    all_s = manager.get_sessions()
                    if all_s:
                        sessions = list(all_s)
                except Exception as e:
                    log.debug("SMTC get_sessions: %s", e)
                current = manager.get_current_session()
                if current is not None:
                    sessions.insert(0, current)

                paused_candidate = None
                seen_ids = set()

                for s in sessions:
                    if s is None:
                        continue
                    try:
                        app_id = str(getattr(s, "source_app_user_model_id", "") or "")
                        if app_id in seen_ids:
                            continue
                        seen_ids.add(app_id)
                        if not _looks_like_apple_source(app_id):
                            continue

                        playback_info = s.get_playback_info()
                        playback_status = getattr(playback_info, "playback_status", None)
                        try:
                            playback_status_value = int(playback_status)
                        except Exception:
                            playback_status_value = None

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
                                    raw_sec = pos.total_seconds()
                                    # Only compensate while playing: a paused
                                    # track's position must not keep advancing.
                                    elapsed = 0.0
                                    if playback_status_value == _PLAYBACK_PLAYING:
                                        elapsed = _smtc_elapsed_since_update(timeline)
                                    pos_sec = int(raw_sec + elapsed)
                        except Exception as e:
                            log.debug("SMTC timeline/position: %s", e)

                        # Re-reading the (up to 2 MiB) thumbnail stream every
                        # poll is wasted work while the track is unchanged.
                        cache_key = (app_id, title, artist, album)
                        if self._thumb_cache[0] == cache_key:
                            thumbnail_bytes = self._thumb_cache[1]
                        else:
                            thumbnail_bytes = await self._read_thumbnail(props)
                            if thumbnail_bytes is not None:
                                self._thumb_cache = (cache_key, thumbnail_bytes)

                        track_info = TrackInfo(
                            title=title,
                            artist=artist,
                            album=album,
                            position_sec=pos_sec,
                            cover_art=thumbnail_bytes,
                            is_playing=(playback_status_value == _PLAYBACK_PLAYING),
                        )
                        if playback_status_value == _PLAYBACK_PLAYING:
                            return track_info
                        if playback_status_value == _PLAYBACK_PAUSED and paused_candidate is None:
                            paused_candidate = track_info
                    except Exception as e:
                        log.debug("SMTC session props: %s", e)
                        continue
                return paused_candidate
            except Exception as e:
                log.debug("SMTC _fetch: %s", e)
                return None

        # One persistent loop thread services every SMTC fetch. Building and
        # tearing down an event loop per 5s poll was constant churn and made
        # winrt's native callbacks fire "Event loop is closed" errors (which
        # used to be papered over by monkeypatching the global exception
        # hooks). A hung fetch just times out here and queues behind.
        try:
            loop = self._ensure_loop()
        except Exception as e:
            log.debug("SMTC loop unavailable: %s", e)
            return None
        future = asyncio.run_coroutine_threadsafe(_fetch(), loop)
        try:
            result = future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            future.cancel()
            log.debug("SMTC fetch exceeded 5s; returning last known state")
            return self._last_smtc
        except Exception as e:
            log.debug("SMTC fetch error: %s", e)
            return None
        self._last_smtc = result
        return result

    def _ensure_loop(self):
        thread_alive = self._loop_thread is not None and self._loop_thread.is_alive()
        if self._loop is not None and thread_alive:
            return self._loop
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="smtc-loop"
        )
        self._loop_thread.start()
        return self._loop

    @staticmethod
    async def _read_thumbnail(props) -> Optional[bytes]:
        """Read cover art with a short timeout; returns None on any failure."""
        try:
            thumb_ref = getattr(props, "thumbnail", None)
            if thumb_ref is None:
                return None

            async def _do_read():
                from winrt.windows.storage.streams import Buffer, InputStreamOptions

                stream = await thumb_ref.open_read_async()
                try:
                    buf = Buffer(2 * 1024 * 1024)
                    await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
                    n = getattr(buf, "length", buf.capacity)
                    return bytes(bytearray(buf)[:n])
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass

            return await asyncio.wait_for(_do_read(), timeout=3)
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            log.debug("Thumbnail read timeout/cancel: %s", e)
            return None
        except Exception as e:
            log.debug("Thumbnail read failed: %s", e)
            return None

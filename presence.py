# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

import hashlib
import os
import threading
import time
import uuid
from typing import Optional

from logger import get_logger
from providers.base import TrackInfo
from utils import build_join_secret, upload_cover_art

log = get_logger("erp.presence")

# Discord rejects activity strings outside 2..128 characters. Overlong fields
# used to bounce the whole payload, which looked like a dead connection and
# caused reconnect churn for the entire track.
_FIELD_MIN = 2
_FIELD_MAX = 128
# U+2800 (Braille blank): renders blank but is not whitespace, so Discord
# neither trims nor rejects a padded field. Lets a real 1-char title ("X")
# display as itself instead of being replaced with "Unknown".
_PAD_CHAR = "⠀"


def _fit_field(text: str) -> str:
    """Clamp ``text`` into Discord's 2..128 char window for activity strings."""
    text = (text or "").strip() or "Unknown"
    if len(text) < _FIELD_MIN:
        text += _PAD_CHAR * (_FIELD_MIN - len(text))
    return text[:_FIELD_MAX]


class DiscordConnectionError(RuntimeError):
    """Raised when Discord RPC needs to be reconnected."""


class DiscordPresence:
    """Manages the Discord Rich Presence connection and per-track updates.

    Public methods are safe to call from both the poll thread and the tray
    callback thread: a re-entrant lock serializes all RPC access, so e.g. a
    Pause click cannot interleave with an in-flight update.
    """

    _REFRESH_INTERVAL = 30
    _SEEK_THRESHOLD = 5
    _UPLOAD_RETRY_INTERVAL = 60
    # litterbox/0x0 uploads expire after 24h; refresh comfortably before that
    # so long sessions never hand Discord a dead image URL.
    _COVER_URL_TTL = 23 * 3600
    _COVER_CACHE_MAX = 32
    # Discord activity type 2 renders "Listening to ..." with a progress bar.
    _ACTIVITY_LISTENING = 2

    def __init__(
        self,
        client_id: str,
        asset_key: str = "apple_music",
        cover_upload: bool = True,
        rpc_factory=None,
    ):
        self._client_id = client_id
        self._asset_key = asset_key
        self._cover_upload = cover_upload
        # Test seam: builds the underlying RPC client (defaults to pypresence).
        self._rpc_factory = rpc_factory
        self._rpc = None
        self._lock = threading.RLock()
        self._cleared = True
        # Unique per process: a shared literal party id would make every
        # installation of the app look like the same Discord party.
        self._party_id = f"eternal-{uuid.uuid4().hex[:12]}"
        self._last_track_key: Optional[str] = None
        self._last_cover_url_sent: Optional[str] = None
        # sha1 -> (url, uploaded_at): alternating albums no longer re-upload
        # identical art, and entries expire with the host's 24h URL lifetime.
        self._cover_cache: dict = {}
        self._cover_fail_at: dict = {}
        self._last_update_time: float = 0.0
        self._locked_start: Optional[int] = None
        self._supports_activity_type = True
        self.current_track: Optional[TrackInfo] = None

    def set_cover_upload(self, enabled: bool) -> None:
        """Live-apply the COVER_ART_UPLOAD privacy toggle from the tray."""
        self._cover_upload = bool(enabled)

    @property
    def is_connected(self) -> bool:
        return self._rpc is not None

    def _make_rpc(self):
        if self._rpc_factory is not None:
            return self._rpc_factory(self._client_id)
        from pypresence import Presence

        return Presence(self._client_id)

    def connect(self):
        with self._lock:
            if self._rpc is not None:
                return
            # Publish the handle only after the handshake succeeds, so a failed
            # connect never leaves a half-initialized client behind.
            rpc = self._make_rpc()
            rpc.connect()
            self._rpc = rpc
            self._cleared = True
            # Discord dropped the activity along with the old connection, so
            # the debounce caches no longer reflect its state: force a resend.
            self._reset_send_state()
            log.debug("RPC handshake complete")

    def _reset_send_state(self):
        self._last_track_key = None
        self._last_cover_url_sent = None
        self._last_update_time = 0.0
        self._locked_start = None

    def disconnect(self):
        with self._lock:
            rpc, self._rpc = self._rpc, None
            if rpc is None:
                return
            try:
                rpc.clear(pid=os.getpid())
                time.sleep(0.5)
            except Exception as e:
                log.debug("RPC disconnect clear: %s", e)
            try:
                rpc.close()
            except Exception as e:
                log.debug("RPC disconnect close: %s", e)
            self._reset_send_state()
            log.debug("RPC disconnected")

    def _drop_connection(self):
        """Discard a connection whose pipe is already dead (no clear attempt)."""
        with self._lock:
            rpc, self._rpc = self._rpc, None
            if rpc is None:
                return
            try:
                rpc.close()
            except Exception as e:
                log.debug("RPC close after drop: %s", e)
            self._reset_send_state()

    def update(self, track: TrackInfo, provider_name: str = ""):
        # Resolve (and possibly upload) cover art before taking the lock, so a
        # slow upload can't stall tray actions like Pause or Reconnect.
        cover_url = self._resolve_cover(track.cover_art)

        title_raw = (track.title or "").strip() or "Unknown"
        artist_raw = (track.artist or "").strip() or "Unknown Artist"
        details = _fit_field(title_raw)
        state = _fit_field(f"by {artist_raw}")
        large_text = _fit_field(track.album or title_raw)
        # Album included: a same-titled track from a different album must
        # refresh large_text instead of riding the debounce.
        track_key = f"{details}|{state}|{large_text}"

        now = time.time()
        pos = int(track.position_sec) if track.position_sec is not None else 0
        computed_start = int(now - pos) if track.position_sec is not None else None

        with self._lock:
            if self._rpc is None:
                raise DiscordConnectionError("Discord RPC is not connected")
            self.current_track = track

            track_changed = track_key != self._last_track_key
            seeked = False
            if not track_changed and computed_start is not None:
                if self._locked_start is None:
                    # First poll with a usable position: adopt it so the
                    # elapsed timer isn't missing for the rest of the track.
                    seeked = True
                elif abs(computed_start - self._locked_start) > self._SEEK_THRESHOLD:
                    seeked = True
            locked_start = computed_start if (track_changed or seeked) else self._locked_start

            cover_changed = cover_url != self._last_cover_url_sent
            stale = (now - self._last_update_time) >= self._REFRESH_INTERVAL
            if not (track_changed or seeked or cover_changed or stale):
                return

            # The join secret carries the raw title/artist (not the padded
            # display strings) so the listener's search matches the real track.
            join_secret = build_join_secret(title_raw, artist_raw, pos)

            update_kw = dict(
                state=state,
                details=details,
                party_id=self._party_id,
                # One open slot is required for Discord to render the Join
                # button; the "1 of 2" count itself is cosmetic.
                party_size=[1, 2],
                join=join_secret,
                start=locked_start,
                large_image=cover_url if cover_url else self._asset_key,
                large_text=large_text,
            )
            if self._supports_activity_type:
                update_kw["activity_type"] = self._ACTIVITY_LISTENING
            if locked_start is not None and track.duration_sec:
                # With an end timestamp Discord shows a real progress bar.
                update_kw["end"] = locked_start + int(track.duration_sec)
            # Discord only renders small_text when a small_image accompanies it.
            if provider_name and cover_url:
                update_kw["small_image"] = self._asset_key
                update_kw["small_text"] = provider_name

            try:
                try:
                    self._rpc.update(**update_kw)
                except TypeError:
                    # Installed pypresence predates activity_type support;
                    # degrade to the classic "Playing" card once, permanently.
                    if "activity_type" not in update_kw:
                        raise
                    update_kw.pop("activity_type")
                    self._supports_activity_type = False
                    log.info("pypresence lacks activity_type; presence shows as 'Playing'")
                    self._rpc.update(**update_kw)
            except Exception as e:
                log.error("Discord RPC update failed: %s (track=%s)", e, details, exc_info=True)
                self._drop_connection()
                raise DiscordConnectionError(str(e)) from e

            # Commit debounce state only after Discord accepted the payload, so
            # a failed send is retried next poll instead of suppressed for 30s.
            if track_changed:
                log.info("Now playing: %s — %s", details, artist_raw)
            self._last_track_key = track_key
            self._locked_start = locked_start
            self._last_cover_url_sent = cover_url
            self._last_update_time = now
            self._cleared = False

    def clear(self):
        with self._lock:
            # Nulling _last_track_key is what guarantees the next update() for
            # the same track re-fires; the cover caches are intentionally left
            # so a resume of identical art doesn't trigger a redundant upload.
            self.current_track = None
            self._last_track_key = None
            self._locked_start = None
            if self._rpc is None or self._cleared:
                return
            try:
                self._rpc.clear(pid=os.getpid())
                self._cleared = True
            except Exception as e:
                # A failed clear means the pipe is gone. Drop the handle so the
                # poll loop reconnects instead of showing Connected forever.
                log.debug("RPC clear failed, dropping connection: %s", e)
                self._drop_connection()

    def _resolve_cover(self, cover_art: Optional[bytes]) -> Optional[str]:
        if not self._cover_upload:
            return None
        if not cover_art:
            # Transient missing bytes (e.g. an SMTC thumbnail read timeout):
            # keep the cache so identical art isn't re-uploaded when it returns.
            return None
        thumb_hash = hashlib.sha1(cover_art).hexdigest()
        now = time.time()

        cached = self._cover_cache.get(thumb_hash)
        if cached is not None and (now - cached[1]) < self._COVER_URL_TTL:
            return cached[0]
        if now < self._cover_fail_at.get(thumb_hash, 0.0):
            return None

        url = upload_cover_art(cover_art)
        if url:
            self._cover_cache[thumb_hash] = (url, now)
            self._cover_fail_at.pop(thumb_hash, None)
            if len(self._cover_cache) > self._COVER_CACHE_MAX:
                oldest = min(self._cover_cache, key=lambda h: self._cover_cache[h][1])
                del self._cover_cache[oldest]
            log.debug("Cover art uploaded: %s", url)
            return url
        # Don't hammer dead hosts every poll, but do retry eventually instead
        # of losing art for the whole album.
        self._cover_fail_at[thumb_hash] = now + self._UPLOAD_RETRY_INTERVAL
        log.warning(
            "Cover art upload failed (hash %s); retrying in %ds",
            thumb_hash[:8],
            self._UPLOAD_RETRY_INTERVAL,
        )
        return None

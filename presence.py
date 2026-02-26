import hashlib
import os
import time
import urllib.parse
from typing import Optional

from logger import get_logger
from providers.base import TrackInfo
from utils import upload_cover_to_catbox

log = get_logger("erp.presence")


class DiscordPresence:
    """Manages the Discord Rich Presence connection and per-track updates."""

    def __init__(self, client_id: str, asset_key: str = "apple_music"):
        self._client_id = client_id
        self._asset_key = asset_key
        self._rpc = None
        self._last_track_key: Optional[str] = None
        self._last_cover_hash: Optional[str] = None
        self._last_cover_url_sent: Optional[str] = None
        self._cached_cover_url: Optional[str] = None
        self._last_update_time: float = 0.0
        self._locked_start: Optional[int] = None
        self.current_track: Optional[TrackInfo] = None

    def connect(self):
        from pypresence import Presence
        self._rpc = Presence(self._client_id)
        self._rpc.connect()
        log.debug("RPC handshake complete")

    def disconnect(self):
        if self._rpc is None:
            return
        try:
            self._rpc.clear(pid=os.getpid())
            time.sleep(0.5)
            self._rpc.close()
        except Exception:
            pass
        self._rpc = None
        log.debug("RPC disconnected")

    _REFRESH_INTERVAL = 30
    _SEEK_THRESHOLD = 5

    def update(self, track: TrackInfo, provider_name: str = ""):
        if self._rpc is None:
            return

        cover_url = self._resolve_cover(track.cover_art)

        title = track.title if len(track.title) >= 2 else "Unknown"
        artist = track.artist if len(track.artist) >= 2 else "Unknown Artist"
        state = f"by {artist}"
        details = title

        track_key = f"{details}|{state}"
        self.current_track = track

        now = time.time()
        pos = int(track.position_sec) if track.position_sec is not None else 0
        computed_start = int(now - pos) if track.position_sec is not None else None

        track_changed = track_key != self._last_track_key

        seeked = False
        if not track_changed and self._locked_start is not None and computed_start is not None:
            drift = abs(computed_start - self._locked_start)
            if drift > self._SEEK_THRESHOLD:
                seeked = True

        if track_changed or seeked:
            self._locked_start = computed_start

        cover_changed = cover_url != self._last_cover_url_sent
        stale = (now - self._last_update_time) >= self._REFRESH_INTERVAL

        if not (track_changed or seeked or cover_changed or stale):
            return

        safe_track = urllib.parse.quote(details[:50], safe="")
        safe_artist = urllib.parse.quote(artist[:30], safe="")
        join_secret = f"eternalrp://sync?track={safe_track}&artist={safe_artist}&pos={pos}"
        if len(join_secret) > 128:
            join_secret = join_secret[:128]

        update_kw = dict(
            state=state,
            details=details,
            party_id="eternal-session-1",
            party_size=[1, 2],
            join=join_secret,
            start=self._locked_start,
        )

        update_kw["large_image"] = cover_url if cover_url else self._asset_key
        update_kw["large_text"] = track.album or details

        if track_changed:
            self._last_track_key = track_key
            log.info("Now playing: %s \u2014 %s", details, artist)

        self._last_cover_url_sent = cover_url
        self._last_update_time = now
        self._rpc.update(**update_kw)

    def clear(self):
        if self._rpc is None:
            return
        try:
            self._rpc.clear(pid=os.getpid())
        except Exception:
            pass
        self._last_track_key = None
        self._locked_start = None

    def _resolve_cover(self, cover_art: Optional[bytes]) -> Optional[str]:
        if not cover_art:
            self._last_cover_hash = None
            self._cached_cover_url = None
            return None
        thumb_hash = hashlib.sha1(cover_art).hexdigest()
        if thumb_hash != self._last_cover_hash:
            self._last_cover_hash = thumb_hash
            self._cached_cover_url = upload_cover_to_catbox(cover_art)
            if self._cached_cover_url:
                log.debug("Cover art uploaded: %s", self._cached_cover_url)
            else:
                log.debug("Cover art upload failed (hash %s)", thumb_hash[:8])
        return self._cached_cover_url

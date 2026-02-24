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
        self._cached_cover_url: Optional[str] = None
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

    def update(self, track: TrackInfo, provider_name: str = ""):
        if self._rpc is None:
            return

        cover_url = self._resolve_cover(track.cover_art)

        title = track.title if len(track.title) >= 2 else "Unknown"
        artist = track.artist if len(track.artist) >= 2 else "Unknown Artist"
        state = f"by {artist}"
        details = title
        safe_track = urllib.parse.quote(details[:50], safe="")
        safe_artist = urllib.parse.quote(artist[:30], safe="")
        join_secret = f"eternalrp://sync?track={safe_track}&artist={safe_artist}"
        if len(join_secret) > 128:
            join_secret = join_secret[:128]

        update_kw = dict(
            state=state,
            details=details,
            party_id="eternal-session-1",
            party_size=[1, 2],
            join=join_secret,
            start=int(time.time() - track.position_sec) if track.position_sec is not None else None,
        )

        update_kw["large_image"] = cover_url if cover_url else self._asset_key
        update_kw["large_text"] = track.album or details

        self.current_track = track

        track_key = f"{details}|{state}"
        if track_key != self._last_track_key:
            self._last_track_key = track_key
            log.info("Now playing: %s \u2014 %s", details, artist)

        try:
            self._rpc.clear()
        except Exception:
            pass
        self._rpc.update(**update_kw)

    def clear(self):
        if self._rpc is None:
            return
        try:
            self._rpc.clear(pid=os.getpid())
        except Exception:
            pass
        self._last_track_key = None

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

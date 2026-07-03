# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

import os
import re
import tempfile
import threading
import time
import urllib.request
from typing import Optional

from app_info import APP_NAME, DEFAULT_SPOTIFY_REDIRECT_URI
from logger import get_logger

from .base import BaseProvider, TrackInfo

log = get_logger("erp.spotify")


class SpotifyProvider(BaseProvider):
    """
    Reads now-playing from the Spotify Web API via spotipy + OAuth2.
    Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in config.
    """

    SCOPES = "user-read-currently-playing user-read-playback-state user-modify-playback-state"
    LATENCY_OFFSET_MS = 1500

    def __init__(
        self, client_id: str, client_secret: str, redirect_uri: str = DEFAULT_SPOTIFY_REDIRECT_URI
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._sp = None
        self._last_album_id: Optional[str] = None
        self._cached_cover: Optional[bytes] = None
        self._failed_album_id: Optional[str] = None
        self._cover_retry_at: float = 0.0
        self.last_error: Optional[str] = None
        self._init_client()

    # Bound spotipy's transport so a flaky network or a 429 storm can't stall
    # the shared poll thread for long stretches.
    _CLIENT_KW = {"requests_timeout": 10, "retries": 1, "status_retries": 1}
    _COVER_RETRY_INTERVAL = 60.0

    @property
    def name(self) -> str:
        return "Spotify"

    def _token_cache_path(self) -> str:
        # Prefer a per-user location (not synced by OneDrive, not next to a
        # possibly shared exe). The token is a secret, so never fall back to
        # the app dir — use the per-user temp dir if LOCALAPPDATA is unusable.
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            cache_dir = os.path.join(base, APP_NAME)
            try:
                os.makedirs(cache_dir, exist_ok=True)
                return os.path.join(cache_dir, ".spotify_token_cache")
            except OSError as e:
                log.debug("LOCALAPPDATA cache dir unavailable: %s", e)
        fallback_dir = os.path.join(tempfile.gettempdir(), APP_NAME)
        os.makedirs(fallback_dir, exist_ok=True)
        return os.path.join(fallback_dir, ".spotify_token_cache")

    def _init_client(self):
        if not self._client_id or not self._client_secret:
            self.last_error = "not_configured"
            return
        try:
            import spotipy
            from spotipy.cache_handler import CacheFileHandler
            from spotipy.oauth2 import SpotifyOAuth

            auth = SpotifyOAuth(
                client_id=self._client_id,
                client_secret=self._client_secret,
                redirect_uri=self._redirect_uri,
                scope=self.SCOPES,
                cache_handler=CacheFileHandler(cache_path=self._token_cache_path()),
                open_browser=True,
            )
            cached = None
            try:
                cached = auth.validate_token(auth.cache_handler.get_cached_token())
            except Exception as e:
                log.debug("Spotify cached-token validation failed: %s", e)
            if cached:
                self._sp = spotipy.Spotify(auth_manager=auth, **self._CLIENT_KW)
                self.last_error = None
                log.debug("Spotify client initialized from cached token")
                return
            # No usable token yet. The interactive browser flow blocks until
            # the user finishes it, so never run it on the caller's thread
            # (the poll loop would freeze and take Apple Music down with it) —
            # authorize on a daemon worker and come online when it completes.
            self.last_error = "auth_pending"
            threading.Thread(
                target=self._interactive_auth,
                args=(auth,),
                daemon=True,
                name="spotify-oauth",
            ).start()
        except Exception as e:
            self._sp = None
            self.last_error = "init_failed"
            log.warning("Spotify init failed: %s", e)

    def _interactive_auth(self, auth):
        try:
            import spotipy

            log.info("Spotify authorization required — complete the sign-in in your browser")
            token = auth.get_access_token(as_dict=False)
            if token:
                self._sp = spotipy.Spotify(auth_manager=auth, **self._CLIENT_KW)
                self.last_error = None
                log.info("Spotify authorized")
            else:
                self.last_error = "init_failed"
        except Exception as e:
            self.last_error = "init_failed"
            log.warning("Spotify interactive authorization failed: %s", e)

    def get_now_playing(self) -> Optional[TrackInfo]:
        if self._sp is None:
            return None
        try:
            current = self._sp.current_playback()
            if not current or not current.get("item"):
                return None

            item = current["item"]
            title = item.get("name", "Unknown")
            artists = item.get("artists", [])
            artist = artists[0]["name"] if artists else "Unknown Artist"

            album_info = item.get("album", {})
            album = album_info.get("name", "")

            progress_ms = current.get("progress_ms", 0) or 0
            pos_sec = progress_ms // 1000

            cover_art = self._fetch_cover(album_info)
            is_playing = bool(current.get("is_playing"))

            return TrackInfo(
                title=title,
                artist=artist,
                album=album,
                position_sec=pos_sec,
                cover_art=cover_art,
                is_playing=is_playing,
            )
        except Exception as e:
            log.debug("Spotify get_now_playing: %s", e)
            return None

    def _fetch_cover(self, album_info: dict) -> Optional[bytes]:
        album_id = album_info.get("id", "")
        if album_id and album_id == self._last_album_id:
            return self._cached_cover
        # A transient CDN failure used to be cached as "no art" for the whole
        # album; retry after a backoff instead of hammering it every poll.
        now = time.monotonic()
        if album_id and album_id == self._failed_album_id and now < self._cover_retry_at:
            return None

        data = None
        images = album_info.get("images", [])
        if images:
            # images[] is sorted largest-first; the ~300px rendition is plenty
            # for Discord's render and quarters the download + re-upload.
            img_url = (images[1] if len(images) > 1 else images[0]).get("url", "")
            if img_url:
                try:
                    with urllib.request.urlopen(img_url, timeout=5) as resp:
                        data = resp.read()
                except Exception as e:
                    log.debug("Spotify cover fetch failed: %s", e)

        if data is not None:
            self._last_album_id = album_id
            self._cached_cover = data
            self._failed_album_id = None
            return data
        self._failed_album_id = album_id
        self._cover_retry_at = now + self._COVER_RETRY_INTERVAL
        return None

    def search_and_play(self, track: str, artist: str = "", position_ms: int = 0) -> bool:
        """Search for a track on Spotify and start playback on the active device.

        Args:
            track: Track title to search for.
            artist: Artist name for a more precise search.
            position_ms: Playback offset so the listener starts at the same
                         second as the host.
        """
        if self._sp is None:
            log.debug("search_and_play: Spotify client not initialised")
            self.last_error = "init_failed"
            return False
        if not (track or "").strip():
            self.last_error = "invalid_track"
            return False
        try:
            self.last_error = None
            matched = self._search_track(track, artist)
            if matched is None:
                log.debug("search_and_play: no match found for %r by %r", track, artist)
                self.last_error = "no_match"
                return False

            playback_kw = {"uris": [matched["uri"]]}
            adjusted_ms = max(0, position_ms + self.LATENCY_OFFSET_MS)
            duration_ms = matched.get("duration_ms") or 0
            if duration_ms and adjusted_ms >= duration_ms:
                # The host is at/past the end by the time the join lands;
                # start at the top instead of seeking beyond the track.
                adjusted_ms = 0
            if adjusted_ms:
                playback_kw["position_ms"] = adjusted_ms

            try:
                self._sp.start_playback(**playback_kw)
            except Exception as e:
                code = getattr(e, "http_status", None)
                reason = getattr(e, "msg", str(e))
                if code == 404:
                    log.debug("search_and_play: HTTP 404 — no active device (%s)", reason)
                    self.last_error = "no_active_device"
                elif code == 403:
                    log.debug("search_and_play: HTTP 403 — Premium required (%s)", reason)
                    self.last_error = "premium_required"
                elif code in (500, 502, 503, 504):
                    log.debug("search_and_play: HTTP %d — Spotify server error (%s)", code, reason)
                    self.last_error = "server_error"
                else:
                    err = str(e).lower()
                    if "no active device" in err or "player command failed" in err:
                        self.last_error = "no_active_device"
                    else:
                        self.last_error = f"playback_error_{code or 'unknown'}"
                    log.debug("search_and_play: playback failed (HTTP %s) — %s", code, reason)
                return False

            self.last_error = None
            log.info(
                "Spotify playback started: %s (offset %d ms)",
                matched.get("name", track),
                adjusted_ms,
            )
            return True
        except Exception as e:
            log.warning("search_and_play failed: %s", e, exc_info=True)
            self.last_error = "unexpected_error"
            return False

    def _search_track(self, track: str, artist: str) -> Optional[dict]:
        """Search Spotify with structured query first, then plain-text fallback."""
        norm_track = self._normalize(track) or track.lower().strip()
        norm_artist = self._normalize(artist) if artist else ""

        structured = f"track:{track}"
        if artist:
            structured += f" artist:{artist}"
        results = self._sp.search(q=structured, type="track", limit=5)
        items = results.get("tracks", {}).get("items", [])
        if items:
            matched = self._fuzzy_pick(items, track, artist)
            if matched:
                return matched
            log.debug("Structured search had %d results but no fuzzy match", len(items))

        plain = f"{norm_track} {norm_artist}".strip()
        log.debug("Falling back to plain search: %r", plain)
        results = self._sp.search(q=plain, type="track", limit=10)
        items = results.get("tracks", {}).get("items", [])
        if items:
            matched = self._fuzzy_pick(items, track, artist)
            if matched:
                return matched
        return None

    # The \b after each alternation stops prefix hits on ordinary words:
    # without it "… - Liverpool Sessions" stripped at "Live(rpool)" and
    # "… - Versions of Me" stripped at "Version(s)".
    _STRIP_SUFFIXES = re.compile(
        r"\s*[\-–—]\s*(single|deluxe|remaster(ed)?(\s*\d{4})?|bonus\s*track|"
        r"expanded|anniversary|live|remix|version|edition|"
        r"explicit|clean|mono|stereo|radio\s*edit|acoustic|"
        r"original\s*mix|extended|instrumental|interlude|skit)\b"
        r".*$",
        re.IGNORECASE,
    )
    _PAREN_NOISE = re.compile(
        r"\s*[\(\[](?:remaster(ed)?(\s*\d{4})?|deluxe(\s*edition)?|"
        r"single|bonus|expanded|anniversary(\s*edition)?|"
        r"live|remix|feat\.?[^)\]]*|ft\.?[^)\]]*|with\s+[^)\]]*|"
        r"version|edition|explicit|clean|mono|stereo|"
        r"radio\s*edit|acoustic|original\s*mix|extended|"
        r"instrumental|from\s+[^)\]]*|prod\.?\s*[^)\]]*)\b[^)\]]*[\)\]]",
        re.IGNORECASE,
    )

    @classmethod
    def _normalize(cls, text: str) -> str:
        """Strip common suffixes/parenthetical noise for fuzzy comparison."""
        text = cls._PAREN_NOISE.sub("", text)
        text = cls._STRIP_SUFFIXES.sub("", text)
        return text.strip().lower()

    @classmethod
    def _fuzzy_pick(cls, items: list, track: str, artist: str) -> Optional[dict]:
        """Return the first search result whose title or artist partially
        matches the input, or ``None`` if nothing is close enough."""
        # A noise-only title ("(Live)") normalizes to "", and "" is a substring
        # of everything — which used to match an arbitrary track. Fall back to
        # the raw title, and refuse to match on nothing at all.
        track_norm = cls._normalize(track) or track.lower().strip()
        if not track_norm:
            return None
        artist_low = artist.lower().strip() if artist else ""
        for item in items:
            name_norm = cls._normalize(item.get("name", ""))
            item_artists = " ".join(a.get("name", "") for a in item.get("artists", [])).lower()
            title_ok = track_norm in name_norm or name_norm in track_norm
            artist_ok = not artist_low or artist_low in item_artists or item_artists in artist_low
            if title_ok and artist_ok:
                return item
        return None

# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

import os
import re
import urllib.request
from typing import Optional

from app_info import APP_NAME, DEFAULT_SPOTIFY_REDIRECT_URI, app_root
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
        self.last_error: Optional[str] = None
        self._init_client()

    @property
    def name(self) -> str:
        return "Spotify"

    def _token_cache_path(self) -> str:
        # Prefer a per-user location (not synced by OneDrive, not next to a
        # possibly shared exe); fall back to the app root if unavailable.
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            cache_dir = os.path.join(base, APP_NAME)
            try:
                os.makedirs(cache_dir, exist_ok=True)
                return os.path.join(cache_dir, ".spotify_token_cache")
            except OSError as e:
                log.debug("LOCALAPPDATA cache dir unavailable: %s", e)
        return os.path.join(app_root(), ".spotify_token_cache")

    def _init_client(self):
        if not self._client_id or not self._client_secret:
            self.last_error = "not_configured"
            return
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth

            auth = SpotifyOAuth(
                client_id=self._client_id,
                client_secret=self._client_secret,
                redirect_uri=self._redirect_uri,
                scope=self.SCOPES,
                cache_path=self._token_cache_path(),
                open_browser=True,
            )
            self._sp = spotipy.Spotify(auth_manager=auth)
            self.last_error = None
            log.debug("Spotify client initialized")
        except Exception as e:
            self._sp = None
            self.last_error = "init_failed"
            log.warning("Spotify init failed: %s", e)

    def is_available(self) -> bool:
        if self._sp is None:
            return False
        try:
            current = self._sp.current_playback()
            return current is not None and current.get("is_playing", False)
        except Exception as e:
            log.debug("Spotify is_available: %s", e)
            return False

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

        self._last_album_id = album_id
        self._cached_cover = None

        images = album_info.get("images", [])
        if images:
            img_url = images[0].get("url", "")
            if img_url:
                try:
                    with urllib.request.urlopen(img_url, timeout=5) as resp:
                        self._cached_cover = resp.read()
                except Exception as e:
                    log.debug("Spotify cover fetch failed: %s", e)
        return self._cached_cover

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
            if adjusted_ms > 0:
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
                elif code == 502 or code == 503:
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
        norm_track = self._normalize(track)
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

    _STRIP_SUFFIXES = re.compile(
        r"\s*[\-–—]\s*(single|deluxe|remaster(ed)?(\s*\d{4})?|bonus\s*track|"
        r"expanded|anniversary|live|remix|version|edition|"
        r"explicit|clean|mono|stereo|radio\s*edit|acoustic|"
        r"original\s*mix|extended|instrumental|interlude|skit)"
        r".*$",
        re.IGNORECASE,
    )
    _PAREN_NOISE = re.compile(
        r"\s*[\(\[](?:remaster(ed)?(\s*\d{4})?|deluxe(\s*edition)?|"
        r"single|bonus|expanded|anniversary(\s*edition)?|"
        r"live|remix|feat\.?[^)\]]*|ft\.?[^)\]]*|with\s+[^)\]]*|"
        r"version|edition|explicit|clean|mono|stereo|"
        r"radio\s*edit|acoustic|original\s*mix|extended|"
        r"instrumental|from\s+[^)\]]*|prod\.?\s*[^)\]]*)[^)\]]*[\)\]]",
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
        track_norm = cls._normalize(track)
        artist_low = artist.lower().strip() if artist else ""
        for item in items:
            name_norm = cls._normalize(item.get("name", ""))
            item_artists = " ".join(a.get("name", "") for a in item.get("artists", [])).lower()
            title_ok = track_norm in name_norm or name_norm in track_norm
            artist_ok = not artist_low or artist_low in item_artists or item_artists in artist_low
            if title_ok and artist_ok:
                return item
        return None

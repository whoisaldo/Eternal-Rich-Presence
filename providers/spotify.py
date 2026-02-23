import os
import sys
import urllib.request
from typing import Optional

from .base import BaseProvider, TrackInfo


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SpotifyProvider(BaseProvider):
    """
    Reads now-playing from the Spotify Web API via spotipy + OAuth2.
    Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in config.
    """

    SCOPES = "user-read-currently-playing user-read-playback-state user-modify-playback-state"

    def __init__(self, client_id: str, client_secret: str,
                 redirect_uri: str = "http://localhost:8888/callback"):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._sp = None
        self._last_album_id: Optional[str] = None
        self._cached_cover: Optional[bytes] = None
        self._init_client()

    @property
    def name(self) -> str:
        return "Spotify"

    def _token_cache_path(self) -> str:
        return os.path.join(_app_dir(), ".spotify_token_cache")

    def _init_client(self):
        if not self._client_id or not self._client_secret:
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
        except Exception:
            self._sp = None

    def is_available(self) -> bool:
        if self._sp is None:
            return False
        try:
            current = self._sp.current_playback()
            return current is not None and current.get("is_playing", False)
        except Exception:
            return False

    def get_now_playing(self) -> Optional[TrackInfo]:
        if self._sp is None:
            return None
        try:
            current = self._sp.currently_playing()
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
            is_playing = current.get("is_playing", True)

            return TrackInfo(
                title=title,
                artist=artist,
                album=album,
                position_sec=pos_sec,
                cover_art=cover_art,
                is_playing=is_playing,
            )
        except Exception:
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
                except Exception:
                    pass
        return self._cached_cover

    def search_and_play(self, track: str, artist: str = "") -> bool:
        """Search for a track on Spotify and start playback on the active device."""
        if self._sp is None:
            return False
        try:
            query = f"track:{track}"
            if artist:
                query += f" artist:{artist}"
            results = self._sp.search(q=query, type="track", limit=1)
            tracks = results.get("tracks", {}).get("items", [])
            if not tracks:
                return False
            self._sp.start_playback(uris=[tracks[0]["uri"]])
            return True
        except Exception:
            return False

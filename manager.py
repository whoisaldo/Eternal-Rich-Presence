from typing import List, Optional

from providers.base import BaseProvider, TrackInfo


class ProviderManager:
    """Tries music providers in priority order, returning the first active result."""

    def __init__(self, providers: List[BaseProvider]):
        self._providers = providers
        self._active: Optional[BaseProvider] = None

    @property
    def active_provider(self) -> Optional[BaseProvider]:
        return self._active

    def get_now_playing(self) -> Optional[TrackInfo]:
        for provider in self._providers:
            try:
                track = provider.get_now_playing()
                if track is not None:
                    self._active = provider
                    return track
            except Exception:
                continue
        self._active = None
        return None

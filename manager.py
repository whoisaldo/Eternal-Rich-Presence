from typing import Optional

from logger import get_logger
from providers.base import BaseProvider, TrackInfo

log = get_logger("erp.manager")


class ProviderManager:
    """Tries music providers in priority order, returning the first active result."""

    def __init__(self, providers: list[BaseProvider]):
        self._providers = providers
        self._active: Optional[BaseProvider] = None
        self._state = "idle"
        self._status_detail = "Waiting for music"
        self._last_error: Optional[str] = None

    @property
    def active_provider(self) -> Optional[BaseProvider]:
        return self._active

    @property
    def state(self) -> str:
        return self._state

    @property
    def status_detail(self) -> str:
        return self._status_detail

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def get_now_playing(self) -> Optional[TrackInfo]:
        paused_provider: Optional[BaseProvider] = None
        provider_errors: list[tuple[str, str]] = []

        for provider in self._providers:
            try:
                track = provider.get_now_playing()
                if track is None:
                    continue
                if track.is_playing:
                    self._active = provider
                    self._state = "playing"
                    self._status_detail = f"Playing from {provider.name}"
                    self._last_error = None
                    return track
                if paused_provider is None:
                    paused_provider = provider
            except Exception as e:
                provider_errors.append((provider.name, str(e)))
                log.warning(
                    "Provider %s failed while checking playback",
                    provider.name,
                    exc_info=True,
                )
                continue

        if paused_provider is not None:
            self._active = paused_provider
            self._state = "paused"
            self._status_detail = f"Playback is paused in {paused_provider.name}"
            self._last_error = None
            return None

        self._active = None
        if provider_errors:
            provider_name, error_text = provider_errors[0]
            self._state = "error"
            self._status_detail = f"{provider_name} is unavailable"
            self._last_error = f"{provider_name}: {error_text}"
        else:
            self._state = "idle"
            self._status_detail = "Waiting for music"
            self._last_error = None
        return None

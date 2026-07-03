# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

import time
from dataclasses import replace
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
        # Last playing track and when it was seen, for the one-cycle grace.
        self._last_playing: Optional[tuple[TrackInfo, float]] = None
        self._grace_used = False

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
            except Exception as e:
                provider_errors.append((provider.name, str(e)))
                log.warning(
                    "Provider %s failed while checking playback",
                    provider.name,
                    exc_info=True,
                )
                grace = self._grace_track(provider)
                if grace is not None:
                    return grace
                continue
            if track is None:
                continue
            if track.is_playing:
                self._active = provider
                self._state = "playing"
                self._status_detail = f"Playing from {provider.name}"
                self._last_error = None
                self._last_playing = (track, time.monotonic())
                self._grace_used = False
                return track
            if paused_provider is None:
                paused_provider = provider

        self._last_playing = None
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

    def _grace_track(self, provider: BaseProvider) -> Optional[TrackInfo]:
        """One-cycle grace: when the active provider throws once, keep showing
        the last playing track (position advanced) instead of blanking the
        presence for a transient hiccup. A second consecutive failure falls
        through to the normal error handling."""
        if provider is not self._active or self._grace_used or self._last_playing is None:
            return None
        self._grace_used = True
        track, seen_at = self._last_playing
        if track.position_sec is not None:
            elapsed = time.monotonic() - seen_at
            track = replace(track, position_sec=int(track.position_sec + elapsed))
        log.debug("Provider %s hiccuped; reusing last track for one poll", provider.name)
        return track

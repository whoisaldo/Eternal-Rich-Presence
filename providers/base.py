# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrackInfo:
    """Normalized track metadata returned by any music provider."""

    title: str = "Unknown"
    artist: str = "Unknown Artist"
    album: str = ""
    position_sec: Optional[int] = None
    cover_art: Optional[bytes] = None
    is_playing: bool = True


class BaseProvider(ABC):
    """Interface that every music provider must implement."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool:
        # Reserved extension point. Currently unused — ProviderManager drives
        # provider selection entirely off get_now_playing().
        ...

    @abstractmethod
    def get_now_playing(self) -> Optional[TrackInfo]: ...

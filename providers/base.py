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
    def name(self) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def get_now_playing(self) -> Optional[TrackInfo]:
        ...

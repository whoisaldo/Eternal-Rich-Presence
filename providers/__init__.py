# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

from .apple_music import AppleMusicProvider
from .base import BaseProvider, TrackInfo
from .spotify import SpotifyProvider

__all__ = ["BaseProvider", "TrackInfo", "AppleMusicProvider", "SpotifyProvider"]

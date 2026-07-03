# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Tests for the pure Apple Music helpers: AUMID source matching and the SMTC
position compensation under both pywinrt projections of last_updated_time."""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.apple_music import (  # noqa: E402
    _WIN_EPOCH_OFFSET,
    _looks_like_apple_source,
    _smtc_elapsed_since_update,
)


class Timeline:
    def __init__(self, lut):
        self.last_updated_time = lut


def test_looks_like_apple_source():
    assert _looks_like_apple_source("AppleInc.AppleMusicWin_nzyj5cx40ttqa!App")
    assert _looks_like_apple_source("iTunes.exe")
    assert _looks_like_apple_source("Apple Music")
    assert not _looks_like_apple_source("Spotify.exe")
    assert not _looks_like_apple_source("Chrome_1234")
    assert not _looks_like_apple_source("")
    assert not _looks_like_apple_source(None)


def test_elapsed_with_datetime_projection():
    # Current pywinrt projects DateTime as a timezone-aware datetime — the
    # old universal_time-only code silently returned 0.0 here.
    tl = Timeline(datetime.now(timezone.utc) - timedelta(seconds=10))
    assert 9.0 <= _smtc_elapsed_since_update(tl) <= 13.0


def test_elapsed_with_filetime_projection():
    class FileTime:
        universal_time = int((time.time() - 10) * 10_000_000) + _WIN_EPOCH_OFFSET

    assert 9.0 <= _smtc_elapsed_since_update(Timeline(FileTime())) <= 13.0


def test_elapsed_never_negative():
    tl = Timeline(datetime.now(timezone.utc) + timedelta(seconds=60))  # clock skew
    assert _smtc_elapsed_since_update(tl) == 0.0


def test_elapsed_degrades_to_zero():
    assert _smtc_elapsed_since_update(Timeline(None)) == 0.0
    assert _smtc_elapsed_since_update(object()) == 0.0

    class WeirdFileTime:
        universal_time = 0

    assert _smtc_elapsed_since_update(Timeline(WeirdFileTime())) == 0.0

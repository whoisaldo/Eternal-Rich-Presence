# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Tests for main.py's pure helpers: adaptive poll cadence and the
discord-{client_id}://join/{secret} launch-argument parser."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (  # noqa: E402
    IDLE_POLL_INTERVAL_SEC,
    POLL_INTERVAL_SEC,
    _extract_discord_join,
    _next_poll_interval,
)


def test_poll_interval_stays_fast_while_active():
    assert _next_poll_interval("playing", 0) == POLL_INTERVAL_SEC
    assert _next_poll_interval("paused", 100) == POLL_INTERVAL_SEC
    assert _next_poll_interval("error", 100) == POLL_INTERVAL_SEC


def test_poll_interval_backs_off_after_sustained_idle():
    assert _next_poll_interval("idle", 0) == POLL_INTERVAL_SEC
    assert _next_poll_interval("idle", 23) == POLL_INTERVAL_SEC
    assert _next_poll_interval("idle", 24) == IDLE_POLL_INTERVAL_SEC
    assert _next_poll_interval("idle", 500) == IDLE_POLL_INTERVAL_SEC


def test_extract_join_with_encoded_eternalrp_uri():
    secret = "eternalrp%3A%2F%2Fsync%3Ftrack%3DSong%26artist%3DQueen%26pos%3D42"
    out = _extract_discord_join(f"discord-123://join/{secret}")
    assert out == "eternalrp://sync?track=Song&artist=Queen&pos=42"


def test_extract_join_wraps_bare_query_secret():
    out = _extract_discord_join("discord-123://join/track%3DSong%26artist%3D%26pos%3D0")
    assert out == "eternalrp://sync?track=Song&artist=&pos=0"


def test_extract_join_rejects_foreign_args():
    assert _extract_discord_join("https://example.com") == ""
    assert _extract_discord_join("--setup") == ""
    assert _extract_discord_join("discord-123://join/gibberish") == ""
    assert _extract_discord_join("discord-123://") == ""
    assert _extract_discord_join("") == ""

# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Tests for ProviderManager priority, paused/idle/error transitions, and the
one-cycle grace that keeps a transient provider hiccup from blanking the
presence."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manager import ProviderManager  # noqa: E402
from providers.base import BaseProvider, TrackInfo  # noqa: E402


class FakeProvider(BaseProvider):
    """Provider that replays a scripted sequence of results/exceptions."""

    def __init__(self, name, script):
        self._name = name
        self.script = list(script)

    @property
    def name(self):
        return self._name

    def get_now_playing(self):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def playing(title="Song", pos=10):
    return TrackInfo(title=title, position_sec=pos, is_playing=True)


def paused(title="Song"):
    return TrackInfo(title=title, is_playing=False)


def test_first_playing_provider_wins():
    a = FakeProvider("A", [playing("a-song")])
    b = FakeProvider("B", [playing("b-song")])
    mgr = ProviderManager([a, b])
    track = mgr.get_now_playing()
    assert track.title == "a-song"
    assert mgr.active_provider is a
    assert mgr.state == "playing"


def test_falls_through_idle_provider():
    a = FakeProvider("A", [None])
    b = FakeProvider("B", [playing("b-song")])
    mgr = ProviderManager([a, b])
    assert mgr.get_now_playing().title == "b-song"
    assert mgr.active_provider is b


def test_paused_provider_reports_paused_state():
    a = FakeProvider("A", [paused()])
    b = FakeProvider("B", [None])
    mgr = ProviderManager([a, b])
    assert mgr.get_now_playing() is None
    assert mgr.state == "paused"
    assert "A" in mgr.status_detail


def test_cold_error_reports_error_state():
    a = FakeProvider("A", [RuntimeError("boom")])
    b = FakeProvider("B", [None])
    mgr = ProviderManager([a, b])
    assert mgr.get_now_playing() is None
    assert mgr.state == "error"
    assert mgr.status_detail == "A is unavailable"


def test_transient_error_gets_one_cycle_grace():
    a = FakeProvider("A", [playing(pos=10), RuntimeError("hiccup"), RuntimeError("hiccup")])
    b = FakeProvider("B", [None, None, None])
    mgr = ProviderManager([a, b])

    assert mgr.get_now_playing().title == "Song"

    # First failure: last track is kept (position advanced), state stays live.
    grace = mgr.get_now_playing()
    assert grace is not None
    assert grace.title == "Song"
    assert grace.position_sec >= 10
    assert mgr.state == "playing"

    # Second consecutive failure: real error surfaces.
    assert mgr.get_now_playing() is None
    assert mgr.state == "error"


def test_recovery_rearms_grace():
    a = FakeProvider("A", [playing(), RuntimeError("x"), playing(), RuntimeError("x")])
    mgr = ProviderManager([a])
    assert mgr.get_now_playing() is not None
    assert mgr.get_now_playing() is not None  # grace
    assert mgr.get_now_playing() is not None  # recovered
    assert mgr.get_now_playing() is not None  # grace again
    assert mgr.state == "playing"


def test_pause_clears_grace_target():
    a = FakeProvider("A", [playing(), paused(), RuntimeError("x")])
    mgr = ProviderManager([a])
    assert mgr.get_now_playing() is not None
    assert mgr.get_now_playing() is None  # paused clears the remembered track
    assert mgr.get_now_playing() is None  # error, no grace from stale state
    assert mgr.state == "error"

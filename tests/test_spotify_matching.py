# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Tests for SpotifyProvider's pure title normalization and fuzzy matching —
the logic that decides which track a Listen Along join actually plays."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.spotify import SpotifyProvider  # noqa: E402

norm = SpotifyProvider._normalize


def item(name, *artists):
    return {"name": name, "artists": [{"name": a} for a in artists]}


def test_strips_common_noise():
    assert norm("Song Title - Single") == "song title"
    assert norm("Song Title (Remastered 2011)") == "song title"
    assert norm("Track (feat. Someone)") == "track"
    assert norm("Track - Live") == "track"
    assert norm("Alive - Extended") == "alive"


def test_word_boundaries_protect_real_titles():
    # "live" must not prefix-match "Liverpool", nor "version" "Versions".
    assert norm("Song - Liverpool Sessions") == "song - liverpool sessions"
    assert norm("Anthem - Versions of Me") == "anthem - versions of me"
    assert norm("Tune (Liverpool Mix)") == "tune (liverpool mix)"


def test_fuzzy_pick_requires_title_overlap():
    items = [item("Some Other Song", "X")]
    assert SpotifyProvider._fuzzy_pick(items, "My Track", "") is None


def test_fuzzy_pick_matches_normalized_title_and_artist():
    items = [item("My Track (Remastered)", "Queen")]
    assert SpotifyProvider._fuzzy_pick(items, "My Track", "Queen") is items[0]


def test_fuzzy_pick_rejects_wrong_artist():
    items = [item("My Track", "Someone Else Entirely")]
    assert SpotifyProvider._fuzzy_pick(items, "My Track", "Queen") is None


def test_noise_only_title_cannot_match_arbitrary_track():
    # "(Live)" normalizes to "" and the empty string is a substring of
    # everything — this used to play a random search result for the listener.
    items = [item("Random Song", "X")]
    assert SpotifyProvider._fuzzy_pick(items, "(Live)", "") is None

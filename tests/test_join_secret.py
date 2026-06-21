# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Smoke tests for the pure, dependency-free Listen Along join-secret helpers.

Run with `pytest` (or `python tests/test_join_secret.py`). These cover only the
dependency-free helpers in utils.py; the Windows COM / winrt / Discord IPC paths
are not unit-tested here as they require a live Windows + Discord environment.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import build_join_secret, parse_join_secret  # noqa: E402


def test_round_trip_ascii():
    secret = build_join_secret("Bohemian Rhapsody", "Queen", 42)
    parsed, err = parse_join_secret(secret)
    assert err is None
    assert parsed["track"] == "Bohemian Rhapsody"
    assert parsed["artist"] == "Queen"
    assert parsed["position_sec"] == 42


def test_length_capped_at_128():
    secret = build_join_secret("Z" * 200, "Y" * 200, 123456)
    assert len(secret) <= 128


def test_multibyte_title_not_lost():
    # Emoji/CJK titles must not collapse to the Unknown fallback.
    secret = build_join_secret("日本語の曲名", "アーティスト", 10)
    assert len(secret) <= 128
    assert "track=Unknown" not in secret
    parsed, err = parse_join_secret(secret)
    assert err is None
    assert parsed["track"]


def test_emoji_heavy_title_stays_valid():
    secret = build_join_secret("😀" * 30, "", 0)
    assert len(secret) <= 128
    parsed, err = parse_join_secret(secret)
    assert err is None


def test_invalid_scheme():
    parsed, err = parse_join_secret("https://example.com")
    assert parsed is None
    assert err == "invalid_scheme"


def test_missing_track():
    parsed, err = parse_join_secret("eternalrp://sync?track=&artist=x&pos=0")
    assert parsed is None
    assert err == "missing_track"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")

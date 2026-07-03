# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Tests for DiscordPresence's pure decision logic (clamping, debounce, seek,
reconnect resend, cover-upload backoff) using a fake RPC client — no Discord,
no network, no Windows APIs."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import presence as presence_mod  # noqa: E402
from presence import DiscordConnectionError, DiscordPresence, _fit_field  # noqa: E402
from providers.base import TrackInfo  # noqa: E402

PAD = "⠀"  # U+2800, the pad char used for 1-char fields


class FakeRPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.updates = []
        self.clears = 0
        self.fail_update = False
        self.fail_clear = False

    def connect(self):
        pass

    def close(self):
        pass

    def clear(self, pid=None):
        if self.fail_clear:
            raise OSError("pipe broken")
        self.clears += 1

    def update(self, **kw):
        if self.fail_update:
            raise OSError("pipe broken")
        self.updates.append(kw)


class RPCFactory:
    def __init__(self):
        self.instances = []

    def __call__(self, client_id):
        rpc = FakeRPC(client_id)
        self.instances.append(rpc)
        return rpc

    @property
    def last(self):
        return self.instances[-1]


def make_dp(cover_upload=False):
    factory = RPCFactory()
    dp = DiscordPresence("123", cover_upload=cover_upload, rpc_factory=factory)
    dp.connect()
    return dp, factory


def track(title="Song Title", artist="Artist", album="Album", pos=10, cover=None):
    return TrackInfo(title=title, artist=artist, album=album, position_sec=pos, cover_art=cover)


def test_fit_field_bounds():
    assert _fit_field("T" * 300) == "T" * 128
    assert _fit_field("X") == "X" + PAD
    assert _fit_field("") == "Unknown"
    assert _fit_field("   ") == "Unknown"
    assert _fit_field("OK") == "OK"


def test_long_fields_clamped_to_discord_limit():
    dp, factory = make_dp()
    dp.update(track(title="T" * 300, artist="A" * 300, album="B" * 300))
    kw = factory.last.updates[-1]
    assert len(kw["details"]) == 128
    assert len(kw["state"]) == 128
    assert len(kw["large_text"]) == 128


def test_one_char_title_preserved_not_unknown():
    dp, factory = make_dp()
    dp.update(track(title="X", artist="V"))
    kw = factory.last.updates[-1]
    assert kw["details"] == "X" + PAD
    assert kw["state"] == "by V"
    # The join secret carries the raw title, not the padded display string.
    assert "track=X&" in kw["join"]


def test_same_track_debounced():
    dp, factory = make_dp()
    dp.update(track())
    dp.update(track())
    assert len(factory.last.updates) == 1


def test_seek_triggers_resend_with_new_start():
    dp, factory = make_dp()
    dp.update(track(pos=10))
    dp.update(track(pos=100))
    updates = factory.last.updates
    assert len(updates) == 2
    assert updates[1]["start"] != updates[0]["start"]


def test_stale_presence_refreshes():
    dp, factory = make_dp()
    dp.update(track())
    dp._last_update_time -= dp._REFRESH_INTERVAL + 1
    dp.update(track())
    assert len(factory.last.updates) == 2


def test_start_backfilled_when_position_appears():
    dp, factory = make_dp()
    dp.update(track(pos=None))
    assert factory.last.updates[-1]["start"] is None
    dp.update(track(pos=5))
    assert factory.last.updates[-1]["start"] is not None


def test_reconnect_resends_current_track():
    dp, factory = make_dp()
    dp.update(track())
    factory.last.fail_clear = True  # dead pipe: disconnect drops it silently
    dp.disconnect()
    dp.connect()
    dp.update(track())
    assert len(factory.last.updates) == 1  # fresh client got the resend


def test_failed_send_is_retried_not_suppressed():
    dp, factory = make_dp()
    factory.last.fail_update = True
    with pytest.raises(DiscordConnectionError):
        dp.update(track())
    assert not dp.is_connected
    dp.connect()
    dp.update(track())
    assert len(factory.last.updates) == 1


def test_clear_detects_dead_pipe():
    dp, factory = make_dp()
    dp.update(track())
    factory.last.fail_clear = True
    dp.clear()
    assert not dp.is_connected


def test_clear_skipped_when_nothing_shown():
    dp, factory = make_dp()
    dp.clear()
    assert factory.last.clears == 0


def test_update_after_clear_resends_same_track():
    dp, factory = make_dp()
    dp.update(track())
    dp.clear()
    dp.update(track())
    assert len(factory.last.updates) == 2


def test_connect_failure_leaves_disconnected():
    class BoomFactory:
        def __call__(self, client_id):
            rpc = FakeRPC(client_id)
            rpc.connect = self._boom
            return rpc

        @staticmethod
        def _boom():
            raise OSError("no discord")

    dp = DiscordPresence("123", cover_upload=False, rpc_factory=BoomFactory())
    with pytest.raises(OSError):
        dp.connect()
    assert not dp.is_connected
    with pytest.raises(DiscordConnectionError):
        dp.update(track())


def test_small_image_paired_with_cover(monkeypatch):
    monkeypatch.setattr(presence_mod, "upload_cover_art", lambda b: "https://litter.example/a.jpg")
    factory = RPCFactory()
    dp = DiscordPresence("123", cover_upload=True, rpc_factory=factory)
    dp.connect()
    dp.update(track(cover=b"img-bytes"), "Spotify")
    kw = factory.last.updates[-1]
    assert kw["large_image"] == "https://litter.example/a.jpg"
    assert kw["small_image"] == "apple_music"
    assert kw["small_text"] == "Spotify"


def test_no_small_text_without_cover():
    dp, factory = make_dp()
    dp.update(track(), "Spotify")
    kw = factory.last.updates[-1]
    assert kw["large_image"] == "apple_music"
    assert "small_text" not in kw and "small_image" not in kw


def test_upload_failure_backs_off_then_retries(monkeypatch):
    calls = []
    result = {"url": None}
    monkeypatch.setattr(
        presence_mod, "upload_cover_art", lambda b: calls.append(1) or result["url"]
    )
    factory = RPCFactory()
    dp = DiscordPresence("123", cover_upload=True, rpc_factory=factory)
    dp.connect()

    dp.update(track(cover=b"img"))
    assert len(calls) == 1
    assert factory.last.updates[-1]["large_image"] == "apple_music"  # fallback

    # Within the backoff window: no re-upload attempt even though a poll fires.
    result["url"] = "https://litter.example/b.jpg"
    dp._last_update_time = 0  # force a stale resend
    dp.update(track(cover=b"img"))
    assert len(calls) == 1

    # After the backoff window: retried and the real URL goes out.
    dp._cover_retry_at = 0
    dp._last_update_time = 0
    dp.update(track(cover=b"img"))
    assert len(calls) == 2
    assert factory.last.updates[-1]["large_image"] == "https://litter.example/b.jpg"


def test_transient_missing_cover_keeps_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(
        presence_mod,
        "upload_cover_art",
        lambda b: calls.append(1) or "https://litter.example/c.jpg",
    )
    factory = RPCFactory()
    dp = DiscordPresence("123", cover_upload=True, rpc_factory=factory)
    dp.connect()
    dp.update(track(cover=b"img"))
    dp._last_update_time = 0
    dp.update(track(cover=None))  # e.g. one failed SMTC thumbnail read
    dp._last_update_time = 0
    dp.update(track(cover=b"img"))  # identical bytes return
    assert len(calls) == 1  # no redundant re-upload

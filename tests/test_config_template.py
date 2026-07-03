# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Tests for the canonical config.py template: repr-escaping of garbage input
(a named project guardrail), privacy-toggle preservation across GUI rewrites,
and key parity with config.example.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (  # noqa: E402
    _CONFIG_DEFAULTS,
    read_config_values,
    render_config,
    write_config_file,
)

NASTY = "va\"l\\ue\n#'tricky"
UNICODE = "曲🎵 — ünïcode"


def test_garbage_input_round_trips_safely(tmp_path):
    path = str(tmp_path / "config.py")
    content = render_config(
        client_id=NASTY,
        asset_key=UNICODE,
        spotify_client_id=NASTY,
        spotify_client_secret=NASTY,
        spotify_redirect_uri=NASTY,
        auto_accept_join_requests=False,
        cover_art_upload=False,
    )
    write_config_file(content, path)
    vals = read_config_values(path)
    assert vals["CLIENT_ID"] == NASTY
    assert vals["ASSET_KEY"] == UNICODE
    assert vals["SPOTIFY_CLIENT_SECRET"] == NASTY
    assert vals["AUTO_ACCEPT_JOIN_REQUESTS"] is False
    assert vals["COVER_ART_UPLOAD"] is False


def test_missing_file_returns_defaults(tmp_path):
    vals = read_config_values(str(tmp_path / "nope.py"))
    assert vals == _CONFIG_DEFAULTS
    assert vals["AUTO_ACCEPT_JOIN_REQUESTS"] is True
    assert vals["COVER_ART_UPLOAD"] is True


def test_broken_config_returns_defaults(tmp_path):
    path = str(tmp_path / "config.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write('CLIENT_ID = "unterminated\n')
    assert read_config_values(path) == _CONFIG_DEFAULTS


def test_non_string_values_coerced(tmp_path):
    path = str(tmp_path / "config.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("CLIENT_ID = 12345\nCOVER_ART_UPLOAD = 0\n")
    vals = read_config_values(path)
    assert vals["CLIENT_ID"] == "12345"
    assert vals["COVER_ART_UPLOAD"] is False


def test_atomic_write_leaves_no_temp_file(tmp_path):
    path = str(tmp_path / "config.py")
    write_config_file(render_config(client_id="1"), path)
    assert os.listdir(str(tmp_path)) == ["config.py"]


def test_gui_writer_preserves_privacy_toggles(tmp_path):
    pytest.importorskip("tkinter")
    from setup_gui import _write_config

    path = str(tmp_path / "config.py")
    write_config_file(
        render_config(client_id="1", auto_accept_join_requests=False, cover_art_upload=False),
        path,
    )
    _write_config("999", "apple_music", "sid", "sec", "", cfg_path=path)
    vals = read_config_values(path)
    assert vals["CLIENT_ID"] == "999"
    assert vals["AUTO_ACCEPT_JOIN_REQUESTS"] is False  # was silently reset before
    assert vals["COVER_ART_UPLOAD"] is False
    assert vals["SPOTIFY_REDIRECT_URI"] == _CONFIG_DEFAULTS["SPOTIFY_REDIRECT_URI"]


def test_example_config_matches_canonical_keys():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    example = os.path.join(repo_root, "config.example.py")
    ns: dict = {}
    with open(example, encoding="utf-8") as f:
        exec(compile(f.read(), example, "exec"), ns)
    public = {k for k in ns if k.isupper()}
    assert public == set(_CONFIG_DEFAULTS), "config.example.py drifted from render_config"

# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

"""Tests for the protocol-handler command builder: source-mode runs must
include the entry script (bare python.exe swallowed the URI and broke every
Listen Along link registered from a dev checkout)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (  # noqa: E402
    _detect_image_format,
    _encode_within,
    _protocol_command,
    _valid_url,
    is_autostart_enabled,
    set_autostart,
    unregister_protocols,
)


def test_source_mode_includes_entry_script():
    cmd = _protocol_command()
    assert cmd.endswith(' "%1"')
    assert "main.py" in cmd
    assert sys.executable in cmd


def test_frozen_mode_uses_bare_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cmd = _protocol_command()
    assert "main.py" not in cmd
    assert cmd == f'"{os.path.abspath(sys.executable)}" "%1"'


def test_explicit_exe_path_wins():
    exe = os.path.abspath("/opt/EternalRichPresence.exe")
    assert _protocol_command(exe) == f'"{exe}" "%1"'


def test_detect_image_format_magic_bytes():
    assert _detect_image_format(b"\xff\xd8\xff\xe0rest") == ("image/jpeg", "jpg")
    assert _detect_image_format(b"\x89PNG\r\n\x1a\n" + b"0" * 8) == ("image/png", "png")
    assert _detect_image_format(b"GIF89a" + b"0" * 8) == ("image/gif", "gif")
    assert _detect_image_format(b"RIFF1234WEBP") == ("image/webp", "webp")
    # Short/empty buffers fall back instead of crashing.
    assert _detect_image_format(b"") == ("image/jpeg", "jpg")
    assert _detect_image_format(b"ab") == ("image/jpeg", "jpg")


def test_valid_url_requires_http_scheme():
    assert _valid_url("https://litter.catbox.moe/x.jpg", "litter.")
    assert _valid_url("http://0x0.st/abc", "0x0.st")
    assert not _valid_url("httpfoo://evil.example", "")
    assert not _valid_url("ftp://files.example/x", "")
    assert not _valid_url("https://" + "a" * 600, "")


def test_registry_helpers_degrade_gracefully_off_windows():
    if sys.platform == "win32":
        return  # exercised for real on the Windows CI job
    assert set_autostart(True) is False
    assert is_autostart_enabled() is False
    assert unregister_protocols("123") is False


def test_encode_within_budget_boundaries():
    assert _encode_within("ab", 10) == "ab"
    assert _encode_within("", 10) == ""
    assert _encode_within("ab", 0) == ""
    # é encodes to %C3%A9 (6 chars): a multibyte char that would straddle the
    # budget is dropped whole, never emitted as a mangled half-escape.
    assert _encode_within("é", 2) == ""
    assert _encode_within("aé", 7) == "a%C3%A9"
    assert _encode_within("aé", 6) == "a"

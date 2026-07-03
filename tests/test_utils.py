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

from utils import _protocol_command  # noqa: E402


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

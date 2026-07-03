# EternalRichPresence — Discord Rich Presence for Apple Music & Spotify
# Copyright (C) 2026 Ali Younes (@whoisaldo)
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. See <https://www.gnu.org/licenses/> for details.

import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler

from app_info import APP_NAME, app_root


def _is_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        # pid-unique: two instances probing at once (double-clicked Join
        # links) must not race on the same file and misjudge the directory.
        probe_path = os.path.join(path, f".erp_write_test.{os.getpid()}")
        with open(probe_path, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe_path)
        return True
    except OSError:
        return False


def _log_dir() -> str:
    preferred = [
        app_root(),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), APP_NAME),
        os.path.join(tempfile.gettempdir(), APP_NAME),
    ]
    for path in preferred:
        if path and _is_writable_dir(path):
            return path
    return app_root()


LOG_DIR = _log_dir()
LOG_PATH = os.path.join(LOG_DIR, "eternalrp.log")

_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _configure_base_logger() -> logging.Logger:
    base = logging.getLogger("erp")
    if base.handlers:
        return base

    base.setLevel(logging.DEBUG)

    try:
        fh = RotatingFileHandler(
            LOG_PATH,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_fmt)
        base.addHandler(fh)
    except OSError:
        fallback_path = os.path.join(tempfile.gettempdir(), "eternalrp.log")
        globals()["LOG_PATH"] = fallback_path
        fh = RotatingFileHandler(
            fallback_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=1,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_fmt)
        base.addHandler(fh)

    stream = sys.stderr if sys.stderr is not None else open(os.devnull, "w")
    ch = logging.StreamHandler(stream)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    base.addHandler(ch)
    base.propagate = False
    return base


def get_log_path() -> str:
    """The log file actually in use.

    Prefer this over ``from logger import LOG_PATH``: the by-value import goes
    stale if handler setup falls back to the temp-dir path at runtime.
    """
    return LOG_PATH


def get_logger(name: str = "erp") -> logging.Logger:
    _configure_base_logger()
    return logging.getLogger(name)

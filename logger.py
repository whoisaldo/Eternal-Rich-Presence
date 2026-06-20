import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler

from app_info import APP_NAME, app_root


def _is_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe_path = os.path.join(path, ".erp_write_test")
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


def get_logger(name: str = "erp") -> logging.Logger:
    _configure_base_logger()
    return logging.getLogger(name)

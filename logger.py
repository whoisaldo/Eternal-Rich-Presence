import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def _log_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


LOG_PATH = os.path.join(_log_dir(), "eternalrp.log")

_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str = "erp") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log

    log.setLevel(logging.DEBUG)

    fh = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_fmt)
    log.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(ch)

    return log

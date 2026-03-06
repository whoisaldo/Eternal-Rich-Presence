"""
Standalone Discord IPC event listener for ACTIVITY_JOIN.

Opens its own named-pipe connection to Discord (separate from pypresence)
so we can receive join events when a friend clicks "Join" on the host's
Rich Presence.  Runs in a daemon thread.

pypresence's Presence class is send-only — it cannot receive events.
This module fills that gap using raw Windows named-pipe I/O.
"""

import ctypes
import ctypes.wintypes
import json
import os
import struct
import threading
import time
from typing import Callable, Optional

from logger import get_logger

log = get_logger("erp.discord_events")

_GENERIC_RW = 0xC0000000
_OPEN_EXISTING = 3

_kernel32 = ctypes.windll.kernel32
_CreateFileW = _kernel32.CreateFileW
_CreateFileW.restype = ctypes.wintypes.HANDLE
_ReadFile = _kernel32.ReadFile
_WriteFile = _kernel32.WriteFile
_CloseHandle = _kernel32.CloseHandle
_PeekNamedPipe = _kernel32.PeekNamedPipe

_INVALID_HANDLE = ctypes.wintypes.HANDLE(-1).value


def _is_valid_handle(h) -> bool:
    return h is not None and h != 0 and h != _INVALID_HANDLE


def _open_pipe() -> Optional[int]:
    """Connect to the first available Discord IPC pipe."""
    for i in range(10):
        path = f"\\\\.\\pipe\\discord-ipc-{i}"
        try:
            handle = _CreateFileW(
                path, _GENERIC_RW, 0, None, _OPEN_EXISTING, 0, None
            )
        except OSError as e:
            log.debug("Pipe %d unavailable: %s", i, e)
            continue
        if _is_valid_handle(handle):
            log.debug("Connected to Discord pipe %d", i)
            return handle
    return None


def _write(handle: int, op: int, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    header = struct.pack("<II", op, len(data))
    buf = header + data
    written = ctypes.wintypes.DWORD(0)
    if not _WriteFile(handle, buf, len(buf), ctypes.byref(written), None):
        raise _PipeBroken("WriteFile failed")


class _PipeBroken(Exception):
    """Raised when the Discord IPC pipe is no longer readable."""


def _read(handle: int, timeout_ms: int = 5000) -> Optional[dict]:
    """Blocking read of a single RPC frame with timeout.

    Returns the parsed JSON dict, ``None`` on timeout, or raises
    ``_PipeBroken`` if the pipe has been closed by Discord.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    peek_failures = 0
    while time.monotonic() < deadline:
        avail = ctypes.wintypes.DWORD(0)
        ok = _PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None)
        if not ok:
            peek_failures += 1
            if peek_failures > 3:
                raise _PipeBroken("PeekNamedPipe failed repeatedly")
            time.sleep(0.1)
            continue
        peek_failures = 0
        if avail.value >= 8:
            break
        time.sleep(0.05)
    else:
        return None

    header_buf = ctypes.create_string_buffer(8)
    read_n = ctypes.wintypes.DWORD(0)
    if not _ReadFile(handle, header_buf, 8, ctypes.byref(read_n), None):
        raise _PipeBroken("ReadFile header failed")
    if read_n.value < 8:
        raise _PipeBroken("Short header read")
    op, length = struct.unpack("<II", header_buf.raw)

    if length > 1024 * 1024:
        raise _PipeBroken(f"Implausible frame length: {length}")

    body_buf = ctypes.create_string_buffer(length)
    if not _ReadFile(handle, body_buf, length, ctypes.byref(read_n), None):
        raise _PipeBroken("ReadFile body failed")
    try:
        return json.loads(body_buf.raw[: read_n.value].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warning("Invalid RPC frame JSON: %s", e)
        raise _PipeBroken("Invalid JSON in RPC frame")


class DiscordEventListener:
    """Listens for ACTIVITY_JOIN events on a dedicated Discord IPC connection."""

    def __init__(self, client_id: str, on_join: Callable[[str], None]):
        self._client_id = client_id
        self._on_join = on_join
        self._handle: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="discord-events")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._handle is not None:
            try:
                _CloseHandle(self._handle)
            except Exception as e:
                log.debug("CloseHandle on stop: %s", e)
            self._handle = None

    def _run(self):
        while not self._stop.is_set():
            try:
                self._handle = _open_pipe()
                if self._handle is None:
                    log.debug("No Discord pipe found, retrying in 10s")
                    self._stop.wait(10)
                    continue

                self._handshake()
                self._subscribe()
                self._event_loop()
            except Exception as e:
                log.warning("Event listener error (will retry): %s", e, exc_info=True)
            finally:
                if self._handle is not None:
                    try:
                        _CloseHandle(self._handle)
                    except Exception as e:
                        log.debug("CloseHandle in finally: %s", e)
                    self._handle = None
            if not self._stop.is_set():
                self._stop.wait(5)

    def _handshake(self):
        _write(self._handle, 0, {"v": 1, "client_id": self._client_id})
        resp = _read(self._handle, timeout_ms=5000)
        if resp is None:
            raise ConnectionError("Handshake timeout")
        log.debug("Event listener handshake OK")

    def _subscribe(self):
        _write(self._handle, 1, {
            "cmd": "SUBSCRIBE", "evt": "ACTIVITY_JOIN",
            "nonce": os.urandom(4).hex(),
        })
        _read(self._handle, timeout_ms=3000)

        _write(self._handle, 1, {
            "cmd": "SUBSCRIBE", "evt": "ACTIVITY_JOIN_REQUEST",
            "nonce": os.urandom(4).hex(),
        })
        _read(self._handle, timeout_ms=3000)
        log.debug("Subscribed to join events")

    def _event_loop(self):
        while not self._stop.is_set():
            try:
                data = _read(self._handle, timeout_ms=2000)
            except _PipeBroken as e:
                log.debug("Event pipe broken, will reconnect: %s", e)
                return

            if data is None:
                continue

            evt = data.get("evt")
            if evt == "ACTIVITY_JOIN":
                secret = data.get("data", {}).get("secret", "")
                log.info("ACTIVITY_JOIN received: %s", secret)
                if secret:
                    try:
                        self._on_join(secret)
                    except Exception as e:
                        log.error("Join handler error: %s", e)

            elif evt == "ACTIVITY_JOIN_REQUEST":
                user = data.get("data", {}).get("user", {})
                uid = user.get("id", "")
                uname = user.get("username", "?")
                log.info("Auto-accepting join from %s", uname)
                if uid:
                    try:
                        _write(self._handle, 1, {
                            "cmd": "SEND_ACTIVITY_JOIN_INVITE",
                            "args": {"user_id": uid},
                            "nonce": os.urandom(4).hex(),
                        })
                    except Exception as e:
                        log.debug("SEND_ACTIVITY_JOIN_INVITE failed: %s", e)

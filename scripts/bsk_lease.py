#!/usr/bin/env python3
"""Cross-process lease for one BrowserSkill (`bsk`) session.

A `bsk` session executes one command at a time: a second concurrent command is rejected with
`exit_code 4` / `data.reason: "session_busy"` and is never dispatched. Every process that shares a
session therefore has to take turns, and "process" here means a different agent, terminal or script
— so the turn-taking has to live outside the process.

The lease is a directory created with `mkdir` (atomic everywhere) plus an `owner.json` naming the
holder. An owner that dies mid-command must not wedge the session forever, so the holder refreshes a
heartbeat while it works and a waiter may break the lease only when the heartbeat is stale **and**
the owning process is gone. Release removes the directory only while the token inside it is still
ours, so a lease that was broken and re-taken by somebody else is never deleted by the old owner.

    from bsk_lease import SessionLease
    with SessionLease(session_id):
        subprocess.run(["bsk", "evaluate", ...])
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

DEFAULT_ROOT = Path(tempfile.gettempdir()) / "teibto-bsk-lease"
HEARTBEAT_SECONDS = 5.0
# Three missed heartbeats before a waiter even looks at whether the owner is alive.
STALE_AFTER_SECONDS = 20.0
DEFAULT_WAIT_SECONDS = 300.0


class LeaseTimeout(RuntimeError):
    """The session stayed busy for the whole wait window."""


def _pid_alive(pid: int) -> bool:
    """Is this process id still running? Never signals the process.

    `os.kill(pid, 0)` is a liveness probe on POSIX only — on Windows `os.kill` terminates the
    target, so liveness there goes through OpenProcess/WaitForSingleObject instead.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        SYNCHRONIZE, ERROR_ACCESS_DENIED, WAIT_TIMEOUT = 0x00100000, 5, 0x00000102
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            # Access denied means the process exists under another token; treat it as alive.
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


class SessionLease:
    """Mutual exclusion over one `bsk` session id, shared by every process on this machine."""

    def __init__(self, session_id: str, *, root: Path | str | None = None,
                 wait: float = DEFAULT_WAIT_SECONDS, stale_after: float = STALE_AFTER_SECONDS,
                 heartbeat: float = HEARTBEAT_SECONDS) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        self.session_id = str(session_id)
        self.root = Path(root or os.environ.get("TEIBTO_BSK_LEASE_DIR") or DEFAULT_ROOT)
        self.path = self.root / f"{self.session_id}.lease"
        self.owner_file = self.path / "owner.json"
        self.wait = float(wait)
        self.stale_after = float(stale_after)
        self.heartbeat = float(heartbeat)
        self.token = uuid.uuid4().hex
        self.waited_ms = 0.0
        self.broke_stale_lease = False
        self._stop = threading.Event()
        self._beat: threading.Thread | None = None

    # -- owner bookkeeping -------------------------------------------------------------------
    def _write_owner(self) -> None:
        """Written once, right after the directory is ours. The heartbeat is the directory's own
        mtime, so a late heartbeat can never overwrite the next holder's owner file."""
        payload = {"pid": os.getpid(), "token": self.token, "host": socket.gethostname(),
                   "session": self.session_id, "since": time.time()}
        self.owner_file.write_text(json.dumps(payload), encoding="utf-8")

    def _read_owner(self) -> dict | None:
        try:
            return json.loads(self.owner_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None                        # missing, or caught mid-write

    def _age(self) -> float:
        """Seconds since the holder last proved it was working (heartbeat touches the directory)."""
        try:
            return time.time() - self.path.stat().st_mtime
        except OSError:
            return float("inf")                # the directory vanished: nothing to wait for

    def _owner_is_gone(self) -> bool:
        """May a waiter take this lease? Only a stale heartbeat AND a dead owner qualify.

        The cheap mtime check comes first on purpose: a waiter that opened `owner.json` on every
        poll would keep the holder from deleting it (Windows refuses to unlink an open file), and
        the lease would outlive its owner.
        """
        if self._age() <= self.stale_after:
            return False
        owner = self._read_owner()
        if owner is None:
            return True                        # stale and nameless: nobody is coming back for it
        if owner.get("host") != socket.gethostname():
            return False                       # another machine's pid says nothing about liveness
        return not _pid_alive(int(owner.get("pid") or 0))

    def _break(self, *, patience: float = 2.0) -> bool:
        """Remove the lease directory. A reader holding `owner.json` open makes the first attempt
        fail on Windows, so this retries briefly instead of leaking the lease."""
        deadline = time.monotonic() + patience
        while True:
            try:
                self.owner_file.unlink()
            except OSError:
                pass                           # missing, or momentarily open in a waiter
            try:
                self.path.rmdir()
                return True
            except FileNotFoundError:
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.02)

    # -- lifecycle ---------------------------------------------------------------------------
    def acquire(self) -> "SessionLease":
        self.root.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        deadline = started + self.wait
        while True:
            try:
                self.path.mkdir()
            except FileExistsError:
                if self._owner_is_gone():
                    self.broke_stale_lease = True
                    self._break()
                    continue
            except OSError:
                # Windows keeps a directory another process is deleting in a pending-delete state:
                # mkdir then fails with a sharing/permission error, not FileExistsError. Transient.
                pass
            else:
                self._write_owner()
                self.waited_ms = round((time.monotonic() - started) * 1000, 3)
                self._stop.clear()
                self._beat = threading.Thread(target=self._heartbeat_loop, daemon=True)
                self._beat.start()
                return self
            if time.monotonic() >= deadline:
                held_by = (self._read_owner() or {}).get("pid", "unknown")
                raise LeaseTimeout(
                    f"bsk session {self.session_id} stayed busy for {self.wait:.0f}s "
                    f"(held by pid {held_by})")
            time.sleep(0.05)

    def _heartbeat_loop(self) -> None:
        """Keep the lease directory's mtime fresh so waiters can tell a working holder from a dead
        one. A touch that lands late, after this lease was released, only delays somebody else's
        stale-break for a moment — it can never take a lease away from its new holder."""
        while not self._stop.wait(self.heartbeat):
            owner = self._read_owner()
            if not owner or owner.get("token") != self.token:
                return                         # somebody else owns it now; stop touching it
            try:
                os.utime(self.path, None)
            except OSError:
                return

    def release(self) -> None:
        self._stop.set()
        if self._beat is not None:
            self._beat.join(timeout=1.0)
            self._beat = None
        owner = self._read_owner()
        if owner is not None and owner.get("token") != self.token:
            return                             # broken and re-taken: not ours to remove
        self._break()

    def __enter__(self) -> "SessionLease":
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()

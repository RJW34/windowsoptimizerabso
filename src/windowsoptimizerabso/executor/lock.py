"""Process-wide execution lock.

Two executors applying plans at once would interleave their captures and mutations: A captures a
value, B changes it, A applies and then "rolls back" to a state that was never really A's to
restore. The journal cannot untangle that afterwards, so it is prevented instead (defect CORE-013).

The lock is an exclusively-created file holding the owning PID and a timestamp. Exclusive creation
(``O_CREAT | O_EXCL``) is atomic on both Windows and POSIX, which is what makes this a lock rather
than a check-then-act race.

A crashed process leaves its lock file behind, so the holder is probed: if the PID is not alive the
lock is stale and may be broken. That check is deliberately conservative -- an unreadable or
malformed lock file is treated as held, not as stale.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Optional


class LockError(RuntimeError):
    """The execution lock could not be acquired."""


class LockHeld(LockError):
    """Another process holds the lock."""

    def __init__(self, message: str, *, owner_pid: Optional[int] = None) -> None:
        super().__init__(message)
        self.owner_pid = owner_pid


def _process_is_alive(pid: int) -> bool:
    """Whether a PID currently exists.

    A recycled PID would read as alive, which is the safe direction to be wrong in: the lock stays
    held and the second executor refuses, rather than two executors running at once.
    """
    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover - exercised on Windows
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The process exists and belongs to someone else.
        return True
    return True


class ExecutionLock:
    """Context manager holding the single-executor lock.

    Usage::

        with ExecutionLock(path):
            ...  # only one process at a time reaches here
    """

    def __init__(self, path: Path, *, break_stale: bool = True) -> None:
        self.path = Path(path)
        self.break_stale = break_stale
        self._acquired = False

    def acquire(self) -> "ExecutionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._create()
        except FileExistsError:
            owner = self._read_owner()
            if owner is None:
                raise LockHeld(
                    f"execution lock {self.path} exists but could not be read. Treating it as "
                    "held; remove it manually if you are certain no executor is running."
                ) from None
            pid = owner.get("pid", -1)
            if _process_is_alive(int(pid)):
                raise LockHeld(
                    f"another executor (pid {pid}, started {owner.get('acquired_at')}) is already "
                    "applying a plan. Concurrent apply is refused: interleaved captures cannot be "
                    "rolled back correctly.",
                    owner_pid=int(pid),
                ) from None
            if not self.break_stale:
                raise LockHeld(
                    f"execution lock {self.path} was left by pid {pid}, which is no longer running",
                    owner_pid=int(pid),
                ) from None
            # Stale: the owner died. Break it and retry once. A second failure means someone else
            # won the race, and they keep it.
            self.path.unlink(missing_ok=True)
            try:
                self._create()
            except FileExistsError:
                raise LockHeld(
                    "another executor acquired the lock while a stale one was being cleared"
                ) from None
        self._acquired = True
        return self

    def release(self) -> None:
        if self._acquired:
            self.path.unlink(missing_ok=True)
            self._acquired = False

    @property
    def held(self) -> bool:
        return self._acquired

    def _create(self) -> None:
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            payload = json.dumps({
                "pid": os.getpid(),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            })
            os.write(descriptor, payload.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _read_owner(self) -> Optional[dict]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) and "pid" in data else None

    def __enter__(self) -> "ExecutionLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.release()

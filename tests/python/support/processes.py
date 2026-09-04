"""Waiting on processes that are not our children.

A daemon suite kills the workers it finds in ``daemon status`` and then removes the
temp directory they logged into. Those workers are the daemon's children, not the
test's, so ``wait()`` is unavailable and the kill returns before the process is gone.
Windows refuses to delete a file a live process still holds, so the cleanup has to
wait for the pids to disappear -- explicitly, not by retrying the delete.
"""

from __future__ import annotations

import os
import time


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_exit(pids, *, timeout: float = 15.0) -> list[int]:
    """Block until every pid is gone or ``timeout`` elapses; returns the survivors."""
    remaining = [int(p) for p in pids]
    deadline = time.monotonic() + timeout
    while remaining and time.monotonic() < deadline:
        remaining = [p for p in remaining if pid_alive(p)]
        if remaining:
            time.sleep(0.1)
    return remaining

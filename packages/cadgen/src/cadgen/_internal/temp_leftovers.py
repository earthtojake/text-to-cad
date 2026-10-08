"""cadgen's scratch in the system temporary folder, and the sweep that removes
what a killed process left there.

Three kinds of scratch live in ``tempfile.gettempdir()``, each named after the
process that owns it:

- ``cadgen-views/<pid>/``: a process's served views (``store.view.views_root``),
  removed when it exits;
- ``cadgen-view-<pid>-*/``: one exported view (``store.view.export_view``),
  removed by the call that made it;
- ``cadgen-trace-<pid>-*.log``: a build's file-trace log
  (``_internal.filetrace``), removed when its capture closes.

A process that is killed removes none of them, and a view holds a copy of
every component it shows, so a killed worker can leave hundreds of megabytes.
:func:`sweep` removes the scratch of every process that is gone, and the
scratch an older cadgen named without a pid once it is older than
:data:`UNNAMED_AGE_SECONDS`. It never removes a live process's: a pid it
cannot judge counts as alive, and a pid reused by another process keeps its
leftovers until that process ends. A folder is first renamed
``cadgen-swept-<sweeper pid>-<name>`` and then deleted, so a sweep killed
midway leaves it condemned rather than half there with a fresh mtime, and the
next sweep finishes it once that sweeper is gone. A daemon worker sweeps once
as it starts (``daemon.worker.serve``), on a thread of its own, so a job never
waits for it.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

VIEWS_DIRNAME = "cadgen-views"
VIEW_PREFIX = "cadgen-view-"
TRACE_PREFIX = "cadgen-trace-"
TRACE_SUFFIX = ".log"
SWEPT_PREFIX = "cadgen-swept-"
#: How old scratch named without a pid (an older cadgen's) must be before a
#: sweep takes it. A view lives for one export, a trace log for one build body.
UNNAMED_AGE_SECONDS = 24 * 3600

_OWNED = re.compile(r"^(\d+)-")


def owned_prefix(prefix: str) -> str:
    """``prefix`` with this process's pid: what a sweep reads ownership from."""
    return f"{prefix}{os.getpid()}-"


def pid_alive(pid: int) -> bool:
    """False only when no process has this pid; anything it cannot tell is alive."""
    if pid <= 0 or pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _windows_pid_alive(pid: int) -> bool:
    # os.kill on Windows terminates; ask the kernel instead. A process that
    # cannot be opened for another reason (access) exists.
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such process
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _owner(rest: str) -> int | None:
    match = _OWNED.match(rest)
    return int(match.group(1)) if match else None


def _abandoned(entry: os.DirEntry, owner: int | None, now: float) -> bool:
    if owner is not None:
        return not pid_alive(owner)
    try:
        return now - entry.stat(follow_symlinks=False).st_mtime > UNNAMED_AGE_SECONDS
    except OSError:
        return False


def _remove(entry: os.DirEntry, root: Path) -> bool:
    try:
        if entry.is_dir(follow_symlinks=False):
            condemned = root / f"{SWEPT_PREFIX}{os.getpid()}-{entry.name}"
            os.rename(entry.path, condemned)
            shutil.rmtree(condemned, ignore_errors=True)
        else:
            os.unlink(entry.path)
    except OSError:
        return False
    return True


def sweep(root: str | os.PathLike[str] | None = None, *, now: float | None = None) -> list[str]:
    """Remove the scratch of processes that are gone; returns what it removed."""
    root = Path(root) if root is not None else Path(tempfile.gettempdir())
    now = time.time() if now is None else now
    removed: list[str] = []
    try:
        with os.scandir(root / VIEWS_DIRNAME) as entries:
            served = [entry for entry in entries if entry.name.isdigit() and entry.is_dir(follow_symlinks=False)]
    except OSError:
        served = []
    for entry in served:
        if not pid_alive(int(entry.name)) and _remove(entry, root):
            removed.append(entry.path)
    try:
        with os.scandir(root) as entries:
            candidates = [entry for entry in entries
                          if entry.name.startswith((VIEW_PREFIX, TRACE_PREFIX, SWEPT_PREFIX))]
    except OSError:
        candidates = []
    for entry in candidates:
        if entry.name.startswith(SWEPT_PREFIX):
            # Condemned by a sweep that did not finish: finish it once that sweeper is gone.
            owner = _owner(entry.name[len(SWEPT_PREFIX):])
            if owner is not None and entry.is_dir(follow_symlinks=False) and not pid_alive(owner):
                shutil.rmtree(entry.path, ignore_errors=True)
                removed.append(entry.path)
            continue
        if entry.name.startswith(VIEW_PREFIX):
            if not entry.is_dir(follow_symlinks=False):
                continue
            owner = _owner(entry.name[len(VIEW_PREFIX):])
        else:
            if not entry.name.endswith(TRACE_SUFFIX) or not entry.is_file(follow_symlinks=False):
                continue
            owner = _owner(entry.name[len(TRACE_PREFIX):])
        if _abandoned(entry, owner, now) and _remove(entry, root):
            removed.append(entry.path)
    return removed


def sweep_in_background() -> threading.Thread:
    """:func:`sweep` on a daemon thread; a failure is never a worker's problem."""

    def run() -> None:
        try:
            sweep()
        except Exception:  # noqa: BLE001 - scratch cleanup never fails a worker
            pass

    thread = threading.Thread(target=run, name="cadgen-temp-sweep", daemon=True)
    thread.start()
    return thread

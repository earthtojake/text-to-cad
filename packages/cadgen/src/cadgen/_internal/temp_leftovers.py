"""cadgen's scratch, and the sweeps that remove what a killed process left.

Four kinds of scratch live in ``tempfile.gettempdir()``, each named after the
process that owns it:

- ``cadgen-views/<pid>/``: a process's served views (``store.view.views_root``),
  removed when it exits;
- ``cadgen-view-<pid>-*/``: one exported view (``store.view.export_view``),
  removed by the call that made it;
- ``cadgen-trace-<pid>-*.log``: a build's file-trace log
  (``_internal.filetrace``), removed when its capture closes;
- ``cadgen-step-import-<pid>-*``: the private copy of a STEP document the
  kernel parses (``_internal.step_scene_package``), removed when the parse ends.

A process that is killed removes none of them, a view holds a copy of every
component it shows and an import copy the whole document, so a killed worker
can leave hundreds of megabytes. A job whose caller left ends by its worker
being killed, so this is a routine path, not a crash's.
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

One more kind lives beside a build's output rather than in the temp folder:
the folder a build saves its STEP in before publishing it
(``.cadgen-stage-<pid>-<host>-<stem>-*/``, :func:`stage_prefix`), a full copy
of the document. A build runs :func:`sweep_stages` on its output's folder
before it stages there, which removes the staging folders of this machine's
builds that are gone. The host is in the name because an output's folder can
be shared between machines, where a pid says nothing: another machine's
staging folder is never judged.
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

from cadgen._internal.atomic_replace import STAGE_PREFIX

VIEWS_DIRNAME = "cadgen-views"
VIEW_PREFIX = "cadgen-view-"
TRACE_PREFIX = "cadgen-trace-"
TRACE_SUFFIX = ".log"
STEP_IMPORT_PREFIX = "cadgen-step-import-"
SWEPT_PREFIX = "cadgen-swept-"
#: How old scratch named without a pid (an older cadgen's) must be before a
#: sweep takes it. A view lives for one export, a trace log for one build body,
#: an import copy for one parse, a staging folder for one build's save.
UNNAMED_AGE_SECONDS = 24 * 3600

_OWNED = re.compile(r"^(\d+)-")
_STAGE_OWNED = re.compile(r"^(\d+)-([0-9a-f]{8})-")


def owned_prefix(prefix: str) -> str:
    """``prefix`` with this process's pid: what a sweep reads ownership from."""
    return f"{prefix}{os.getpid()}-"


@functools.lru_cache(maxsize=1)
def _host() -> str:
    """This machine, in eight hex digits: whose pids a staging folder's name speaks of."""
    return hashlib.sha256(socket.gethostname().encode("utf-8", "replace")).hexdigest()[:8]


def stage_prefix(stem: str) -> str:
    """What this process's STEP staging folder for an output named ``stem`` starts with."""
    return f"{STAGE_PREFIX}{os.getpid()}-{_host()}-{stem}-"


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
                          if entry.name.startswith((VIEW_PREFIX, TRACE_PREFIX, STEP_IMPORT_PREFIX, SWEPT_PREFIX))]
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
        elif entry.name.startswith(STEP_IMPORT_PREFIX):
            if not entry.is_file(follow_symlinks=False):
                continue
            owner = _owner(entry.name[len(STEP_IMPORT_PREFIX):])
        else:
            if not entry.name.endswith(TRACE_SUFFIX) or not entry.is_file(follow_symlinks=False):
                continue
            owner = _owner(entry.name[len(TRACE_PREFIX):])
        if _abandoned(entry, owner, now) and _remove(entry, root):
            removed.append(entry.path)
    return removed


def sweep_stages(folder: str | os.PathLike[str], *, now: float | None = None) -> list[str]:
    """Remove the STEP staging folders in ``folder`` whose builds, on this machine, are gone.

    One named by a live pid, or by another machine, stays; one an older cadgen
    named without a pid goes once it is :data:`UNNAMED_AGE_SECONDS` old. A
    removal that stops midway leaves the rest under the same dead owner's name
    for the next sweep. Never raises: a build's staging is not this sweep's to fail.
    """
    now = time.time() if now is None else now
    removed: list[str] = []
    try:
        with os.scandir(folder) as entries:
            candidates = [entry for entry in entries
                          if entry.name.startswith(STAGE_PREFIX) and entry.is_dir(follow_symlinks=False)]
    except OSError:
        return removed
    for entry in candidates:
        owned = _STAGE_OWNED.match(entry.name[len(STAGE_PREFIX):])
        if owned is not None and owned.group(2) != _host():
            continue
        if _abandoned(entry, int(owned.group(1)) if owned else None, now):
            shutil.rmtree(entry.path, ignore_errors=True)
            if not os.path.lexists(entry.path):
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

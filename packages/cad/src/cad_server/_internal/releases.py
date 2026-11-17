"""BRIDGE-ONLY: the release folders of 0.10.0 to 0.11.11, and whether a process runs from a folder.

``<state>/releases/<version>`` is where 0.11.11 and earlier installed a release: its core in a virtual environment,
made by uv, its marker (``cad-release.json``) written last. Those releases' updaters make one for the release they
move to (an updater of 0.11.10 runs that folder's ``cad setup --engine-update``: ``cad_server.cli.setup``). Nothing of
cad removes one by itself: ``cad cache prune`` does, when asked, but the one ``installations/current`` names and any a
process runs from (``running``).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from cad_server._internal import base  # noqa: F401 - a release folder's Python is ``base.interpreter``'s

__all__ = ["FOLDER", "MARKER", "SCHEMA", "console", "processes", "root", "running"]

FOLDER = "releases"
MARKER = "cad-release.json"
SCHEMA = "cad release/1"


def root() -> Path:
    """The releases' folder: ``releases`` in the state folder."""
    from cad.engine.places import state_dir

    return Path(state_dir()) / FOLDER


def console(env: Path) -> Path:
    """The ``cad`` command of the environment at ``env``."""
    return env / ("Scripts/cad.exe" if os.name == "nt" else "bin/cad")


def running(folder: Path | str, *, besides: int | None = None, asking: int | None = None) -> bool:
    """Whether a process runs from ``folder`` (``processes``; ``besides`` and ``asking`` as there). True when that
    cannot be asked: a folder is kept rather than taken from under a process."""
    found = processes(folder, besides=besides, asking=asking)
    return found is None or bool(found)


def processes(folder: Path | str, *, besides: int | None = None, asking: int | None = None) -> list[int] | None:
    """The ids of the processes that run from ``folder``, in order: what a message names. On POSIX, one started by
    its Python or its command names it on its command line (``ps``), as written or by a link to it -- each path on
    the line read with its folder resolved, as ``folder`` is, so a worker started by an alias of an environment's
    Python counts. On Windows, one whose program is in it (``_windows_rows``): a virtual environment's
    ``python.exe`` is a launcher that waits for the interpreter it starts, so an environment's process is seen
    for as long as it runs. ``besides``: a process that does not count, nor its descendants (a version's server and
    its workers, asked before the server is stopped), nor, on Windows, the launchers in ``folder`` that started it and
    wait for it (the process a server names is the interpreter its environment's ``python.exe`` started: on POSIX
    there is no such process, the environment's Python is the interpreter). ``asking``: a process that does not
    count, nor its ancestors (the one asking, which may run from the folder it removes, and the launchers that started
    it: ``cad uninstall`` typed in a terminal runs from the version it removes). None when that cannot be asked on
    POSIX; on Windows, where the system will not list its processes, none: there a folder is renamed aside before it
    is removed, which the system refuses for a file in use (``versions.clean``, ``legacy.remove``)."""
    windows = os.name == "nt"
    rows = _windows_rows() if windows else _ps_rows()
    if rows is None:
        return [] if windows else None
    inside = {os.path.normcase(os.path.abspath(folder)).rstrip("\\/") + os.sep,
              os.path.normcase(os.path.realpath(folder)).rstrip("\\/") + os.sep}

    def in_folder(image: str) -> bool:  # Windows: a program's full path
        return bool(image) and any(os.path.normcase(image).startswith(each) for each in inside)

    parents = {pid: parent for pid, parent, _command in rows}
    spared: set[int] = set()
    if besides is not None:
        spared.add(besides)
        grew = True
        while grew:
            grew = False
            for pid, parent, _command in rows:
                if parent in spared and pid not in spared:
                    spared.add(pid)
                    grew = True
        if windows:
            images = {pid: image for pid, _parent, image in rows}
            launcher = parents.get(besides)
            while launcher is not None and launcher not in spared and in_folder(images.get(launcher, "")):
                spared.add(launcher)
                launcher = parents.get(launcher)
    if asking is not None:
        pid: int | None = asking
        while pid is not None and pid not in spared:
            spared.add(pid)
            pid = parents.get(pid)
    if windows:
        return sorted(pid for pid, _parent, image in rows if pid not in spared and in_folder(image))
    named = os.path.realpath(folder).rstrip(os.sep) + os.sep
    plain = os.path.abspath(folder).rstrip(os.sep) + os.sep
    resolved: dict[str, str] = {}

    def within(word: str) -> bool:
        # Its folder resolved, not the word itself: a venv's python is a link out of its environment.
        head, tail = os.path.split(word)
        if head not in resolved:
            resolved[head] = os.path.realpath(head)
        return (os.path.join(resolved[head], tail) + os.sep).startswith(named)

    return sorted(pid for pid, _parent, line in rows if pid not in spared and (
        named in line or plain in line or any(word.startswith(os.sep) and within(word) for word in line.split())))


def _ps_rows() -> list[tuple[int, int, str]] | None:
    """Every process as ``ps`` lists it: its id, its parent's and its command line; None when ``ps`` cannot say."""
    try:
        listed = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if listed.returncode != 0:
        return None
    rows: list[tuple[int, int, str]] = []
    for line in listed.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


def _windows_rows() -> list[tuple[int, int, str]] | None:
    """Every process on Windows: its id, its parent's (``CreateToolhelp32Snapshot``) and its program's full path
    (``QueryFullProcessImageNameW``; empty for one this user may not open, another user's or the system's). None
    when the system cannot be asked. Windows keeps no command line another process can read without reading its
    memory, so a program's path is what is matched."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (ImportError, OSError, AttributeError):
        return None

    class Entry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    snapshot_all, query_limited = 0x00000002, 0x1000  # TH32CS_SNAPPROCESS, PROCESS_QUERY_LIMITED_INFORMATION
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.argtypes = kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
    kernel32.Process32FirstW.restype = kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD))
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snapshot = kernel32.CreateToolhelp32Snapshot(snapshot_all, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:  # INVALID_HANDLE_VALUE
        return None
    rows: list[tuple[int, int, str]] = []
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            rows.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID), ""))
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    if not rows:
        return None
    named: list[tuple[int, int, str]] = []
    buffer = ctypes.create_unicode_buffer(32768)
    for pid, parent, _image in rows:
        image = ""
        handle = kernel32.OpenProcess(query_limited, False, pid) if pid else None
        if handle:
            try:
                size = wintypes.DWORD(len(buffer))
                if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    image = buffer.value
            finally:
                kernel32.CloseHandle(handle)
        named.append((pid, parent, image))
    return named

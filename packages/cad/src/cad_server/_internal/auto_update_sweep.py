"""What cad's update does on Windows before an installer changes cad's environment, and what it puts back after: the
installer's bin ``cad.exe`` moved aside (``aside``) and put there again (``command_back``), and every process running
from the environment stopped (``stop_environment``, by Windows' own calls, ``Windows``). On Windows a file a process
has open or loaded cannot be deleted, and an installer that meets one stops midway.

Two processes use it: the update's worker (``auto_update_helper``), which imports it, and the repairer
(``auto_update_repair``), which runs outside the environment by the Python it was made from and finds this file copied
beside it. So it imports the standard library alone (ctypes only on Windows, as it asks), and names nothing of cad's.
Each step writes what it did to ``log``, anything with a ``write(text)``.
"""

import contextlib
import os
import re
import shutil
import time
from pathlib import Path

WINDOWS = os.name == "nt"
# The name the installer's bin ``cad.exe`` is given as it is moved aside (``aside``), in its folder: a new ``cad`` fails
# at once meanwhile, rather than open the files being replaced; and the files of that name the server's tidying removes
# (``auto_update.tidy``), one a process still ran then.
ASIDE = ".cad-{pid}.exe.old"
# How long the processes stopped are waited for until they are gone, each round, and how many times they are looked
# for, until none is left.
END_SECONDS, ROUNDS = 15.0, 5


def own_command(prefix, windows=WINDOWS):
    """The environment's own ``cad`` command at ``prefix`` (``Scripts/cad.exe``, ``bin/cad``)."""
    return Path(prefix) / ("Scripts/cad.exe" if windows else "bin/cad")


def aside(command, log):
    """``command`` (the installer's bin ``cad.exe``) renamed beside itself (``ASIDE``): Windows lets a running program
    be renamed, never deleted. Where it was moved, or None (none there, or the rename refused: the installer then
    meets it, and goes on)."""
    moved = command.with_name(ASIDE.format(pid=os.getpid()))
    try:
        os.replace(command, moved)
    except FileNotFoundError:
        return None
    except OSError as error:
        log.write(f"{command} could not be moved aside: {type(error).__name__}: {error}")
        return None
    log.write(f"{command} moved aside to {moved.name}")
    return moved


def command_back(command, moved, prefix, log, windows=WINDOWS):
    """The installer's bin ``cad`` at ``command`` again where the installer left none -- on Windows the environment's
    own (``Scripts/cad.exe``) copied there, as pipx exposes it and uv's is the same program, elsewhere a link to its
    ``bin/cad`` as uv and pipx make one; else the one moved aside (``moved``) put back --; then the one moved aside
    removed where it can be (a process may run it still: the server's next tidying removes it). What is left of it
    there, or None."""
    if not os.path.lexists(command):
        try:
            own = own_command(prefix, windows)
            if windows:
                shutil.copy2(own, command)
                log.write(f"{command} copied from the environment's own")
            else:
                if not own.is_file():
                    raise FileNotFoundError(own)
                os.symlink(own, command)
                log.write(f"{command} linked to the environment's own")
        except OSError:
            if moved is not None:
                with contextlib.suppress(OSError):
                    os.replace(moved, command)
                    log.write(f"{command} put back as it was")
                    return None
    if moved is not None:
        try:
            os.unlink(moved)
        except OSError:
            return moved if os.path.lexists(moved) else None
    return None


def lineage(pid, table):
    """``pid`` and each process that started it, as far as ``table`` (``Windows.processes``) knows them: the processes
    ending which ends ``pid`` (a ``cad.exe``, the environment's ``python.exe``, each ends the Python under it)."""
    found = set()
    while pid and pid in table and pid not in found:
        found.add(pid)
        pid = table[pid][0]
    if pid:
        found.add(pid)
    return found


def running_from(image, prefix, command):
    """Whether a process whose program is ``image`` runs from the environment at ``prefix``: its program inside it, or
    the installer's bin ``cad.exe`` (``command``), or one moved aside beside it (``ASIDE``)."""
    if not image:
        return False
    path = os.path.normcase(os.path.abspath(image))
    inside = os.path.normcase(os.path.abspath(prefix)).rstrip("\\/") + os.sep
    if path.startswith(inside):
        return True
    if command is None:
        return False
    if path == os.path.normcase(os.path.abspath(command)):
        return True
    folder, name = os.path.split(path)
    return folder == os.path.normcase(os.path.abspath(Path(command).parent)) \
        and re.fullmatch(r"\.cad-\d+\.exe\.old", name) is not None


def stop_environment(prefix, command, spare, log, system=None, seconds=END_SECONDS, rounds=ROUNDS):
    """On Windows, every process running from the environment at ``prefix`` (``running_from``) stopped -- but this
    process and each process in ``spare``, with those that started them (``lineage``) -- and waited for until it is
    gone, with the processes each started directly (the Python a launcher started, which ends with it: killing a
    ``cad.exe`` takes its Python down in milliseconds), ``seconds`` at most; then looked for again, until none is left,
    ``rounds`` looks at most. As Scoop finds what to stop before it updates an app. Each written to the log. Never
    raises. ``system``: Windows' process calls (``Windows``; a test's stand-in)."""
    try:
        system = system or Windows()
        for _round in range(rounds):
            table = system.processes()
            kept = set()
            for pid in (os.getpid(), *spare):
                kept |= lineage(pid, table)
            ending = sorted(pid for pid, (_parent, image) in table.items()
                            if pid not in kept and running_from(image, prefix, command))
            if not ending:
                return
            watched = sorted(pid for pid, (parent, _image) in table.items()
                             if parent in ending and pid not in kept and pid not in ending)
            left = system.end(ending, watched, seconds)
            log.write("stopped the processes running from cad's environment: "
                      + ", ".join(f"{pid} ({table[pid][1]})" for pid in ending)
                      + (f"; still there after {seconds:g} s: {', '.join(map(str, left))}" if left else ""))
    except Exception as error:  # noqa: BLE001 - the install goes on, and says what it met
        log.write(f"the processes running from cad's environment could not be stopped: {type(error).__name__}: {error}")


def running(pids, prefix, command, system=None):
    """On Windows, which of ``pids`` run from the environment at ``prefix`` now (``running_from``); elsewhere, and where
    Windows cannot be asked, none."""
    if not WINDOWS and system is None:
        return []
    try:
        table = (system or Windows()).processes()
    except Exception:  # noqa: BLE001 - what cannot be seen is not waited for: the sweep stops it
        return []
    return sorted(pid for pid in pids if pid in table and running_from(table[pid][1], prefix, command))


class Windows:
    """Windows' own calls for ``stop_environment``, by ctypes: the processes (a Toolhelp snapshot, each program's path
    by ``QueryFullProcessImageNameW``) and their end (``TerminateProcess``, ``WaitForSingleObject``)."""

    SNAPPROCESS, QUERY, TERMINATE, SYNCHRONIZE = 0x2, 0x1000, 0x0001, 0x00100000

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        kernel = self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class Entry(ctypes.Structure):  # PROCESSENTRY32W
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]

        self.Entry = Entry
        for name, arguments, result in (
                ("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
                ("Process32FirstW", [wintypes.HANDLE, ctypes.POINTER(Entry)], wintypes.BOOL),
                ("Process32NextW", [wintypes.HANDLE, ctypes.POINTER(Entry)], wintypes.BOOL),
                ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
                ("QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
                ("TerminateProcess", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
                ("WaitForSingleObject", [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
                ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL)):
            function = getattr(kernel, name)
            function.argtypes, function.restype = arguments, result

    def processes(self):
        """``{pid: (parent pid, its program's path or None)}`` of every process now."""
        kernel, ctypes = self.kernel, self.ctypes
        snapshot = kernel.CreateToolhelp32Snapshot(self.SNAPPROCESS, 0)
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        table = {}
        try:
            entry = self.Entry()
            entry.dwSize = ctypes.sizeof(self.Entry)
            more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                table[entry.th32ProcessID] = (entry.th32ParentProcessID, None)
                more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        return {pid: (parent, self.image(pid)) for pid, (parent, _none) in table.items()}

    def image(self, pid):
        kernel, ctypes = self.kernel, self.ctypes
        handle = kernel.OpenProcess(self.QUERY, False, pid)
        if not handle:
            return None
        try:
            size = self.wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            return buffer.value if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else None
        finally:
            kernel.CloseHandle(handle)

    def end(self, ending, watched, seconds):
        """Each of ``ending`` terminated, then it and each of ``watched`` waited for, ``seconds`` in all: the pids still
        there."""
        kernel, handles = self.kernel, {}
        for pid in ending:
            handle = kernel.OpenProcess(self.TERMINATE | self.SYNCHRONIZE, False, pid)
            if handle:
                kernel.TerminateProcess(handle, 1)
                handles[pid] = handle
        for pid in watched:
            handle = kernel.OpenProcess(self.SYNCHRONIZE, False, pid)
            if handle:
                handles[pid] = handle
        deadline, left = time.monotonic() + seconds, []
        for pid, handle in handles.items():
            wait = max(0, int((deadline - time.monotonic()) * 1000))
            if kernel.WaitForSingleObject(handle, wait) != 0:
                left.append(pid)
            kernel.CloseHandle(handle)
        return left

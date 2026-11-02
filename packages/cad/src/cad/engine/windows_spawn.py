"""The engine's spawn pools on Windows, when their processes run another environment than the engine's
(the base: ``serve._spawn_in``).

A virtual environment's ``python.exe`` on Windows is a launcher that starts the real interpreter as a
child of its own, and ``multiprocessing`` hands a spawned process the handles of its queues by
duplicating them into the process it started: the launcher, which never passes them on, so the pool's
processes die unheard. CPython starts its own environment's processes by the real interpreter, told
the environment by ``__PYVENV_LAUNCHER__``, for that reason (bpo-35797); ``Popen`` here is
``multiprocessing.popen_spawn_win32.Popen``'s start, for another environment than this process's.

Imported on Windows alone, by the engine as it makes a pool and by each pool process as it reads the
process object it was handed (``Process``, which is why the classes live at a module's top level).
"""

from __future__ import annotations

import multiprocessing.context as contexts
import multiprocessing.popen_spawn_win32 as win32  # pyrefly: ignore[missing-import]
import multiprocessing.spawn as spawn
import os
from multiprocessing import reduction, util
from subprocess import STARTF_FORCEOFFFEEDBACK, STARTUPINFO  # pyrefly: ignore[missing-module-attribute]
from typing import Any

import _winapi  # pyrefly: ignore[missing-import]
import msvcrt  # pyrefly: ignore[missing-import]

__all__ = ["Context", "Popen", "Process", "context"]

# The environment the pools' processes run (``context``): its own ``python.exe``, and the real
# interpreter behind it.
_LAUNCH: tuple[str, str] | None = None


class Popen(win32.Popen):
    """A pool process started by the real interpreter, told the environment it runs."""

    def __init__(self, process_obj: Any) -> None:  # noqa: D107 - win32.Popen's, the interpreter and its environment aside
        assert _LAUNCH is not None, "context() first"
        venv, real = _LAUNCH
        prep_data = spawn.get_preparation_data(process_obj._name)
        rhandle, whandle = _winapi.CreatePipe(None, 0)
        wfd = msvcrt.open_osfhandle(whandle, 0)
        cmd = spawn.get_command_line(parent_pid=os.getpid(), pipe_handle=rhandle)
        cmd[0] = real
        env = {**os.environ, "__PYVENV_LAUNCHER__": venv}
        line = " ".join('"%s"' % part for part in cmd)
        with open(wfd, "wb", closefd=True) as to_child:
            try:
                hp, ht, pid, _tid = _winapi.CreateProcess(real, line, None, None, False, 0, env, None,
                                                           STARTUPINFO(dwFlags=STARTF_FORCEOFFFEEDBACK))
                _winapi.CloseHandle(ht)
            except BaseException:
                _winapi.CloseHandle(rhandle)
                raise
            self.pid = pid
            self.returncode = None
            self._handle = hp
            self.sentinel = int(hp)
            self.finalizer = util.Finalize(self, win32._close_handles, (self.sentinel, int(rhandle)))
            contexts.set_spawning_popen(self)
            try:
                reduction.dump(prep_data, to_child)
                reduction.dump(process_obj, to_child)
            finally:
                contexts.set_spawning_popen(None)


class Process(contexts.SpawnProcess):
    """A pool process that ``Popen`` starts."""

    @staticmethod
    def _Popen(process_obj: Any) -> Any:  # noqa: N802 - multiprocessing's name
        return Popen(process_obj)


class Context(contexts.SpawnContext):
    """The spawn context whose processes ``Popen`` starts."""

    Process = Process


def context(venv: str, real: str) -> Context:
    """The spawn context whose processes run the environment of ``venv`` (its ``python.exe``) by its
    real interpreter, ``real``."""
    global _LAUNCH
    _LAUNCH = (venv, real)
    return Context()

"""On Windows every process the engine starts has a console of its own and no window (#597): the
daemon (``client._spawn``, ``cad server start``'s) a process group of its own too, never no console at all,
started by the environment's own Python with none of the command's streams, so ``cad.exe`` exits with the
command and an update can replace it (``uv tool install`` fails while one runs); and each warm
worker, STEP reader and render process windowless; what they start in turn (the meshing and
reading pools) shares their windowless console. No CI machine shows a window, so the flags handed
to ``subprocess.Popen`` are read under a patched ``os.name``: the engine's, where its processes
are started (``places.windowless``, ``places.detached``), as pathlib reads the real one."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from cad.engine import client, places, reader
from cad_server.engine import daemon  # noqa: F401 - the kernel environment as the daemon names it (places.KERNEL)
from cad_server.engine.services import RENDER, WORKER
from cad_server.engine.supervisor import Process

# Windows' values: ``subprocess`` names them on Windows alone.
NO_WINDOW, NEW_GROUP, DETACHED_PROCESS = 0x08000000, 0x00000200, 0x00000008


class Started(Exception):
    """What the patched ``Popen`` raises: the process is never started."""


class _Os:
    """``os`` with another ``name``."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, attribute: str) -> Any:
        return getattr(os, attribute)


class WindowsConsoleTest(unittest.TestCase):
    def popen(self, start: Callable[[], Any], name: str = "nt") -> dict[str, Any]:
        """The keyword arguments ``start`` hands ``Popen`` where ``os.name`` is ``name``."""
        with mock.patch.object(places, "os", _Os(name)), \
                mock.patch.object(subprocess, "Popen", side_effect=Started) as popen:
            with self.assertRaises(Started):
                start()
        [call] = popen.call_args_list
        return call.kwargs

    def test_every_process_the_engine_starts_on_windows_is_windowless(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="windowless-"))
        self.addCleanup(os.rmdir, folder)
        script = str(folder / "model.py")
        for name, start in (("worker", lambda: Process.start(WORKER, script, script, dict(os.environ))),
                            ("reader", lambda: reader.Reader()._start()),
                            ("render process", lambda: Process.start(RENDER, "part", str(folder / "part.xbf"),
                                                                     dict(os.environ)))):
            with self.subTest(process=name):
                self.assertEqual(self.popen(start)["creationflags"], NO_WINDOW)
                self.assertNotIn("creationflags", self.popen(start, "posix"))  # POSIX takes no creation flags
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(folder)}):
            started = self.popen(lambda: client._spawn(None))
            self.assertEqual(started["creationflags"], NO_WINDOW | NEW_GROUP)
            self.assertFalse(started["creationflags"] & DETACHED_PROCESS, "no console at all gives each child a window")
            self.assertNotIn("start_new_session", started)
            self.assertEqual({key: value for key, value in self.popen(lambda: client._spawn(None), "posix").items()
                              if key in ("creationflags", "start_new_session")}, {"start_new_session": True})
            self.assertEqual([started[name] for name in ("stdin", "stdout", "stderr")], [subprocess.DEVNULL] * 3,
                             "none of the command's streams: nothing holds the command, or its cad.exe, open")
            with mock.patch.object(subprocess, "Popen", side_effect=Started) as popen, self.assertRaises(Started):
                client._spawn(4321)
            self.assertEqual(popen.call_args.args[0], [sys.executable, "-P", "-m", "cad_server._internal.engine_daemon",
                                                       "--port", "4321"], "the environment's Python, never cad.exe")


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()

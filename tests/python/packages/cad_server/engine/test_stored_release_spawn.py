"""A process of the environment is started with the environment's interpreter and no ``PYTHONPATH`` to the release
cad's update keeps beside the installed one: it takes that release by itself as it starts, by the same pointer, and so
holds its mark (``places.handed``). Handed the folder on ``PYTHONPATH``, it would import the release beside the
environment's own packages and hold nothing, and the store could remove the release under it. A source tree outside
the environment is still handed, as before: nothing else would find it.

The server a command starts (``client._spawn``) and a kernel process the server starts in its own environment
(``supervisor.Process.start``), each read from the arguments handed to a patched ``Popen``: nothing is started.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from cad.engine import client, places
from cad_server.engine.services import WORKER
from cad_server.engine.supervisor import Process


class Started(Exception):
    """What the patched ``Popen`` raises: the process is never started."""


class StoredReleaseSpawnTest(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="stored-spawn-")
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name).resolve()
        # All outside this environment (``sys.prefix``): releases in the state folder's store, a checkout, a folder.
        self.release, self.source, self.other, self.kept = (str(root / name) for name in
                                                            ("1.0.1-tag", "src", "1.0.0-tag", "kept"))
        for folder in (self.release, self.source, self.other, self.kept):
            os.mkdir(folder)
        self.enterContext(mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(root / "engine")}))
        os.environ.pop("PYTHONPATH", None)

    def started(self, start: Callable[[], Any], root: str, stored: str | None) -> str | None:
        """The ``PYTHONPATH`` ``start`` hands the process it starts where the engine's folder is ``root`` and the
        release this process runs is ``stored``."""
        with mock.patch.object(places, "engine_root", return_value=root), \
                mock.patch.object(places, "stored", return_value=stored), \
                mock.patch.object(subprocess, "Popen", side_effect=Started) as popen:
            with self.assertRaises(Started):
                start()
        return popen.call_args.kwargs["env"].get("PYTHONPATH")

    def check(self, start: Callable[[], Any]) -> None:
        self.assertIsNone(self.started(start, self.release, self.release),
                          "the stored release this process runs: taken by the pointer, never handed")
        self.assertEqual(self.started(start, self.source, None), self.source, "a source tree: handed")
        self.assertEqual(self.started(start, self.source, self.other), self.source,
                         "a source tree, from a process that runs a stored release: handed all the same")
        with mock.patch.dict(os.environ, {"PYTHONPATH": self.kept}):
            self.assertEqual(self.started(start, self.release, self.release), self.kept, "a caller's own path stays")
            self.assertEqual(self.started(start, self.source, None), os.pathsep.join((self.source, self.kept)))

    def test_the_server_a_command_starts(self) -> None:
        self.check(lambda: client._spawn(None))

    def test_a_kernel_process_the_server_starts_in_its_own_environment(self) -> None:
        own = {"python": "python", "prefix": "prefix", "path": None, "own": True}
        with mock.patch.object(places, "kernel", return_value=own):
            script = str(Path(self.source) / "model.py")
            self.check(lambda: Process.start(WORKER, script, script, dict(os.environ)))


if __name__ == "__main__":
    unittest.main()

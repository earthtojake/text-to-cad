"""The stdio transport reaches the device's server on its own (``cad_mcp.engine``): it starts the current
installation's, whatever release it is itself; on a device with none current it registers one first -- the
server its own environment carries, else its own release's, installed by uvx -- and with none at all it says
how to install one. Nothing is started for real: ``Popen`` and ``run`` are stood in for."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cad_mcp
from cad_mcp import engine


class Started(Exception):
    """What the stood-in ``Popen`` raises: nothing starts."""


class StartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="shim-engine-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = self.root / "state"
        self.elsewhere = self.root / "elsewhere"
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.root / "engine"),
                                               "CAD_CACHE_DIR": str(self.root / "cache"),
                                               "PYTHONPATH": "/a/checkout/src", "DO_NOT_TRACK": "1"})
        patched.start()
        self.addCleanup(patched.stop)

    def installed(self, version: str = "9.9.9") -> dict:
        """An installation registered and current, its Python and console script there."""
        bin_ = self.elsewhere / "bin"
        bin_.mkdir(parents=True, exist_ok=True)
        python, console = bin_ / "python", bin_ / "cadgen"
        for path in (python, console):
            path.write_text("", encoding="utf-8")
        record = {"version": version, "python": str(python), "cadgen": str(console), "prefix": str(self.elsewhere)}
        folder = self.state / "installations"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{version}.json").write_text(json.dumps(record), encoding="utf-8")
        (folder / "current").write_text(version, encoding="utf-8")
        return record

    def started(self) -> tuple[list[str], dict]:
        with mock.patch.object(subprocess, "Popen", side_effect=Started) as popen, self.assertRaises(Started):
            engine._start()
        [call] = popen.call_args_list
        return call.args[0], call.kwargs

    def test_the_current_installation_s_server_starts_with_its_own_python(self) -> None:
        record = self.installed()
        with mock.patch.object(engine, "register") as registered:
            argv, options = self.started()
        registered.assert_not_called()
        self.assertEqual(argv, [record["python"], "-P", "-m", engine.DAEMON_MODULE])
        env = options["env"]
        self.assertNotIn("PYTHONPATH", env, "another installation imports its own server")
        self.assertNotIn("DO_NOT_TRACK", env, "a switch of this process's alone")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1", "nothing written beside a library")

    def test_a_device_with_none_current_registers_one_first(self) -> None:
        with mock.patch.object(engine, "register", side_effect=lambda: self.installed("1.2.3")) as registered:
            argv, _options = self.started()
        registered.assert_called_once()
        self.assertEqual(argv[0], str(self.elsewhere / "bin" / "python"))

    def test_registering_runs_the_server_here_else_installs_this_release_with_uvx(self) -> None:
        with mock.patch.object(engine.importlib.util, "find_spec", return_value=object()), \
                mock.patch.object(subprocess, "run") as ran:
            engine.register()
        self.assertEqual(ran.call_args.args[0], [sys.executable, "-P", "-m", engine.REGISTER])
        with mock.patch.object(engine.importlib.util, "find_spec", return_value=None), \
                mock.patch.object(subprocess, "run") as ran:
            engine.register()
        self.assertEqual(ran.call_args.args[0], [*engine.LAUNCHER, f"{engine.SERVER}=={cad_mcp.__version__}", "python",
                                                 "-P", "-m", engine.REGISTER])
        for name in ("stdin", "stdout", "stderr"):
            self.assertEqual(ran.call_args.kwargs[name], subprocess.DEVNULL, "its words are nobody's here")

    def test_with_no_server_anywhere_it_says_how_to_install_one(self) -> None:
        with mock.patch.object(engine, "register"), \
                mock.patch.object(engine.importlib.util, "find_spec", return_value=None), \
                self.assertRaisesRegex(ConnectionError, "run the install command"):
            engine._start()


if __name__ == "__main__":
    unittest.main()

"""A helper the engine or a server it runs launches by name is found in PATH's absolute folders
alone and run by its absolute path: an empty, '.' or relative PATH entry would resolve against the
working folder, which the person never chose for it (and the engine's daemon stands in its own,
private folder, never the shared temporary one)."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.engine import client, daemon, executables


@unittest.skipIf(os.name == "nt", "a POSIX PATH and executable bits")
class FindTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="executables-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "node_modules" / ".bin").mkdir(parents=True)
        (self.folder / "bin").mkdir()
        for planted in (self.folder / "helper", self.folder / "node_modules" / ".bin" / "helper"):
            planted.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            planted.chmod(0o755)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.folder)

    def test_an_empty_dot_or_relative_path_entry_is_never_searched(self) -> None:
        for path in ("/usr/bin:/bin:", ":/usr/bin", ".:/usr/bin", "node_modules/.bin:/usr/bin", "bin/../:/usr/bin"):
            with self.subTest(path=path), mock.patch.dict(os.environ, {"PATH": path}):
                self.assertIsNone(executables.find("helper"))

    def test_a_helper_in_an_absolute_folder_is_found_by_its_absolute_path(self) -> None:
        real = self.folder / "bin" / "helper"
        real.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        real.chmod(0o644)  # not executable: passed over
        with mock.patch.dict(os.environ, {"PATH": f".:{self.folder / 'bin'}"}):
            self.assertIsNone(executables.find("helper"))
            real.chmod(real.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(executables.find("helper"), str(real))
        with self.assertRaises(ValueError):
            executables.find("bin/helper")


@unittest.skipIf(os.name == "nt", "the daemon's private folder is a POSIX one")
class DaemonWorkingFolderTest(unittest.TestCase):
    def test_the_daemon_stands_in_its_own_folder_never_the_shared_one_above_it(self) -> None:
        engine = Path(tempfile.mkdtemp(prefix="eng-")).resolve()
        self.addCleanup(shutil.rmtree, engine, True)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(engine)}), \
                mock.patch.object(client.subprocess, "Popen") as started:
            client._start()
        self.assertEqual(started.call_args.kwargs["cwd"], str(engine))
        self.assertIsNone(daemon.folder_refusal(engine))

    def test_an_idle_worker_stands_in_the_engine_s_folder_and_never_one_others_can_write(self) -> None:
        from cadgen.engine import worker

        engine = Path(tempfile.mkdtemp(prefix="eng-")).resolve()
        self.addCleanup(shutil.rmtree, engine, True)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(engine)}):
            self.assertEqual(worker._neutral_folder(), str(engine))
            engine.chmod(0o777)
            self.assertEqual(worker._neutral_folder(), tempfile.gettempdir())


if __name__ == "__main__":
    unittest.main()

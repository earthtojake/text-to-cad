"""Whose folders a process uses (``cad.engine.places``): a process of an installed version reads and writes
under ``versions/<version>/`` and reaches its own engine folder; a process with no version -- this suite's
own, under ``CAD_STATE_DIR``, ``CAD_ENGINE_DIR`` and ``CAD_CACHE_DIR`` -- keeps the layout of 0.11.10 and earlier. Every
folder is a temporary device's; a version is faked by its code marker alone."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import client, places

X = "0.12.0"


class Device(unittest.TestCase):
    """A private device: its state, engines and cache folders, none of them a real one."""

    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="version-folders-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state, self.engines, self.cache = self.root / "state", self.root / "engines", self.root / "cache"
        environment = {"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.engines),
                       "CAD_CACHE_DIR": str(self.cache), "CAD_INSTALLATION_VERSION": ""}
        for patch in (mock.patch.dict(os.environ, environment), mock.patch.object(places, "HOME", None)):
            patch.start()
            self.addCleanup(patch.stop)
        places._versioned.cache_clear()
        self.addCleanup(places._versioned.cache_clear)

    def installed(self, name: str = X, prefix: Path | None = None) -> dict:
        """Version ``name`` present: its code marker, naming a server environment (in its code, else
        ``prefix``) whose Python and console script are there."""
        code = self.state / "versions" / name / "code"
        prefix = prefix or code / "server"
        (prefix / "bin").mkdir(parents=True, exist_ok=True)
        for script in ("python", "cad"):
            (prefix / "bin" / script).write_text("", encoding="utf-8")
        record = {"schema": places.VERSION_SCHEMA, "version": name, "python": str(prefix / "bin" / "python"),
                  "cad": str(prefix / "bin" / "cad"), "prefix": str(prefix)}
        code.mkdir(parents=True, exist_ok=True, mode=0o700)
        (code / places.VERSION_MARKER).write_text(json.dumps(record), encoding="utf-8")
        places._versioned.cache_clear()
        return record

    def running_in(self, prefix: Path):
        return mock.patch.object(sys, "prefix", str(prefix))


class WhichVersionTest(Device):
    def test_a_process_has_a_version_by_its_name_its_code_folder_or_a_marker_naming_it(self) -> None:
        self.assertIsNone(places.versioned(), "a test's private device: no version")
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            self.assertIsNone(places.versioned(), "told a name no version holds: none, as in 0.11.10 and earlier")
        self.installed()
        cases = [
            ("told its name", {"CAD_INSTALLATION_VERSION": X}, sys.prefix, X),
            ("runs from its code", {}, self.state / "versions" / X / "code" / "server", X),
            ("runs from its kernel", {}, self.state / "versions" / X / "code" / "base" / "0123456789abcdef", X),
            ("runs from its data", {}, self.state / "versions" / X / "data", None),
            ("runs elsewhere, told nothing", {}, self.root / "elsewhere", None),
            ("told a name that is no version", {"CAD_INSTALLATION_VERSION": "../x"}, sys.prefix, None),
        ]
        for label, environment, prefix, expected in cases:
            with self.subTest(label), mock.patch.dict(os.environ, environment), self.running_in(prefix):
                self.assertEqual(places.versioned(), expected)

    def test_a_development_install_s_checkout_is_its_version_by_the_marker_naming_it(self) -> None:
        checkout = self.root / "checkout" / ".venv"
        self.installed("0.12.0-dev.20261113120000", prefix=checkout)
        with self.running_in(checkout):
            self.assertEqual(places.versioned(), "0.12.0-dev.20261113120000")
        with mock.patch.object(places, "HOME", {"prefix": str(checkout), "executable": "", "root": ""}), \
                self.running_in(self.root / "an extras environment"):
            self.assertEqual(places.versioned(), "0.12.0-dev.20261113120000", "a kernel process, by its home")

    def test_a_name_that_is_no_version_names_no_folder(self) -> None:
        for name in ("..", "../x", "x", "", "0/../.."):
            with self.subTest(name), self.assertRaises(ValueError):
                places.version_dir(name)
            with self.subTest(name), self.assertRaises(ValueError):
                places.engine_dir(name)
            self.assertIsNone(places.version_record(name))


class PathTableTest(Device):
    """Every path rule, for a version named X and for no version."""

    def table(self) -> dict[str, Path | str | None]:
        return {"state": places.state_dir(), "data": places.data_dir(), "cache": places.cache_dir(),
                "engine": places.engine_dir(), "door": places.door_path(), "lock": places.lock_path(),
                "failed": places.failure_path(), "pycache": Path(places.pycache() or ""),
                "installation": places.installation()}

    def test_no_version_keeps_the_layout_before_0_12(self) -> None:
        self.installed()  # another version present changes nothing for a process that is not it
        from cad.engine.previous import version

        tag = places.bytecode_tag()
        self.assertEqual(self.table(), {
            "state": self.state, "data": self.state, "cache": self.cache, "engine": self.engines,
            "door": self.engines / "engine.door", "lock": self.engines / "engine.lock",
            "failed": self.engines / "engine.failed", "pycache": self.cache / "pycache" / tag,
            "installation": version()})
        self.assertEqual((places.legacy_cache_dir(), places.engines_dir()), (self.cache, self.engines))

    def test_a_version_keeps_everything_in_its_folder_and_its_engine_folder(self) -> None:
        self.installed()
        version = self.state / "versions" / X
        with self.running_in(version / "code" / "server"):
            self.assertEqual(self.table(), {
                "state": self.state, "data": version / "data", "cache": version / "data" / "cache",
                "engine": self.engines / X, "door": self.engines / X / "engine.door",
                "lock": self.engines / X / "engine.lock", "failed": self.engines / X / "engine.failed",
                "pycache": version / "code" / "pycache", "installation": X})
            self.assertEqual(places.legacy_cache_dir(), self.cache, "CAD_CACHE_DIR names the layout of 0.11.10 and earlier alone")
            self.assertEqual(places.engines_dir(), self.engines, "the flat door's folder")
            if os.name != "nt":  # Windows has no mode bits: the folder is the user's by its profile folder's ACL
                self.assertEqual(stat.S_IMODE((version / "code" / "pycache").stat().st_mode), 0o700)
        # Any version's folders by name, whatever this process is.
        self.assertEqual((places.code_dir("0.11.99"), places.data_dir("0.11.99"), places.cache_dir("0.11.99"),
                          places.engine_dir("0.11.99")),
                         (self.state / "versions" / "0.11.99" / "code", self.state / "versions" / "0.11.99" / "data",
                          self.state / "versions" / "0.11.99" / "data" / "cache", self.engines / "0.11.99"))

    def test_a_version_s_engine_folder_and_the_one_above_it_are_this_user_s_alone(self) -> None:
        self.installed()
        with self.running_in(self.state / "versions" / X / "code" / "server"):
            held = places.lock()
            self.addCleanup(held.close)
        # On POSIX by its mode (``places.make_engine_dir``, ``folder_refusal``); Windows has no mode bits to set or read
        # (a folder reads 0o777): there it is the user's by where it is, inside their profile, as every folder of the
        # engine's is (``places.default_engine_dir``), and nothing checks it.
        for folder in (self.engines, self.engines / X):
            self.assertTrue(folder.is_dir(), folder)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700, folder)
        self.assertTrue((self.engines / X / "engine.lock").is_file())
        self.assertFalse((self.engines / "engine.lock").exists(), "the flat lock is not this version's")


class StartTest(Device):
    """A client starts its own version's server, never the current installation's."""

    def current(self) -> dict:
        """Another installation current, as in 0.11.10 and earlier: what a process with no version starts."""
        prefix = self.root / "current"
        (prefix / "bin").mkdir(parents=True)
        for script in ("python", "cad"):
            (prefix / "bin" / script).write_text("", encoding="utf-8")
        record = {"version": "0.11.10", "python": str(prefix / "bin" / "python"), "cad": str(prefix / "bin" / "cad"),
                  "prefix": str(prefix)}
        (self.state / "installations").mkdir(parents=True, exist_ok=True)
        (self.state / "installations" / "0.11.10.json").write_text(json.dumps(record), encoding="utf-8")
        (self.state / "installations" / "current").write_text("0.11.10", encoding="utf-8")
        return record

    def started(self) -> list[str]:
        with mock.patch.object(subprocess, "Popen", side_effect=RuntimeError("started")) as popen, \
                self.assertRaisesRegex(RuntimeError, "started"):
            client._start()
        return popen.call_args.args[0]

    def test_a_version_starts_its_own_server_and_no_version_the_current_one(self) -> None:
        current = self.current()
        self.assertEqual(self.started()[0], current["python"], "no version: the current installation's")
        mine = self.installed()
        with self.running_in(self.root / "a model's own environment"), \
                mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}):
            self.assertEqual(self.started()[0], mine["python"], "its own version's, never the current one")

    def test_a_version_whose_server_is_gone_starts_nothing_else(self) -> None:
        self.current()
        mine = self.installed()
        os.unlink(mine["python"])
        with mock.patch.dict(os.environ, {"CAD_INSTALLATION_VERSION": X}), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("a server was started")):
            self.assertIsNone(places.engine())
            with self.assertRaises(ConnectionError):
                client._start()


if __name__ == "__main__":
    unittest.main()

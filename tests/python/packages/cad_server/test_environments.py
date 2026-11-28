"""The core and the base, end to end, with the real uv: an installation of the server alone (this
checkout's server and library, editable, without the library's build123d extra) runs a model -- ``cadgen
run`` makes the base once, with no uv in it, the
script and its worker run there, and so do the engine's documents worker and meshing pool, while the
engine's daemon runs the core.

uv is reached through a wrapper where uv's installer puts it (``UV_INSTALL_DIR``) that logs what it is
asked. The engine is this file's own (the runner's ``CAD_ENGINE_DIR``), the core registered as its state folder's current installation,
started by the core's ``cad server start`` -- with the core's Python -- and stopped by its ``cad stop``. The fake-uv
contracts (keys, commands, refusals) are test_base.py's.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support import engine_daemon, uv_cache
from tests.python.support.paths import LIBRARY, add_sources

add_sources()

from cad_server._internal import base  # noqa: E402

MODEL = """\
import sys
from pathlib import Path

import build123d as bd
from cad import xbf


@xbf("XBF/part.xbf")
def part():
    Path(__file__).with_name("worker.txt").write_text(sys.prefix, encoding="utf-8")
    return bd.Box(4, 5, 6)


if __name__ == "__main__":
    part()
    print("CALLER " + sys.prefix)
"""


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


def _uv() -> str:
    from cad_server._internal.base import find_uv

    return find_uv()


class CoreAndBaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="cadgen-environments-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        real = _uv()
        # The core: this checkout's server and library, editable, with their required dependencies and nothing
        # of the kernel.
        cls.core = cls.root / "core"
        subprocess.run([real, "venv", "--no-project", "--python", sys.executable, str(cls.core)], check=True,
                       capture_output=True)
        subprocess.run([real, "pip", "install", "--python", str(base.interpreter(cls.core)), "--link-mode",
                        "hardlink", "-e", str(LIBRARY)], check=True, capture_output=True)
        # The device's current installation, as setup registers it: the engine every client starts.
        assert engine_daemon.register(os.environ["CAD_STATE_DIR"], str(base.interpreter(cls.core)), str(cls.core))
        # uv's cache holding what the base's offline install reads, warmed before uv is counted: an environment
        # synced from a lock leaves it without, and the base would then ask uv a second time, from the network.
        uv_cache.warm(cls.root)
        # A uv where uv's installer puts it (``UV_INSTALL_DIR``, the first place cad looks: ``base.find_uv``) that
        # writes a line of what it is asked, then runs the real one. Elsewhere than Windows: there cad runs no batch
        # file as uv, and the real one is found (``asked`` says nothing).
        folder, cls.log = cls.root / "bin", cls.root / "uv.log"
        folder.mkdir()
        if os.name != "nt":
            wrapper = folder / "uv"
            wrapper.write_text(f"#!/bin/sh\necho \"$1\" >> '{cls.log}'\nexec '{real}' \"$@\"\n", encoding="utf-8")
            wrapper.chmod(0o755)
        environ = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        cls.env = engine_daemon.watched({**environ, "UV_INSTALL_DIR": str(folder),
                                         "PATH": os.pathsep.join((os.path.dirname(real), os.environ["PATH"])),
                                         "CAD_VIEWER_WARM": "0"}, cls.addClassCleanup, started=False)
        cls.cadgen = str(cls.core / ("Scripts/cad.exe" if os.name == "nt" else "bin/cad"))
        # The core's server in place of the file's, which this interpreter's start started.
        from cad.engine import api

        api.stop()
        subprocess.run([cls.cadgen, "server", "start"], env=cls.env, check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run([cls.cadgen, "stop"], env=cls.env, capture_output=True))

    def run_cadgen(self, *args: str, cwd: Path) -> subprocess.CompletedProcess:
        return engine_daemon.run([self.cadgen, *args], env=self.env, cwd=str(cwd))

    def asked(self, expected: list[str]) -> list[str]:
        """What uv was asked, where the wrapper counts it (not on Windows: ``expected`` then)."""
        if os.name == "nt":
            return expected
        return self.log.read_text(encoding="utf-8").split() if self.log.exists() else []

    @staticmethod
    def caller(done: subprocess.CompletedProcess) -> Path:
        lines = [line for line in done.stdout.splitlines() if line.startswith("CALLER ")]
        assert len(lines) == 1, (done.stdout, done.stderr)
        return Path(lines[0][len("CALLER "):]).resolve()

    def test_a_model_and_the_engines_kernel_processes_run_in_the_base_the_engine_in_the_core(self) -> None:
        cache = Path(os.environ["CAD_CACHE_DIR"]).resolve()
        self.assertNotEqual(subprocess.run([str(base.interpreter(self.core)), "-c", "import build123d"],
                                           env=self.env, capture_output=True).returncode, 0, "the core has no kernel")
        project = self.root / "project"
        project.mkdir()
        (project / "model.py").write_text(MODEL, encoding="utf-8")
        first = self.run_cadgen("run", "model.py", cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        made = self.caller(first)
        self.assertEqual(made.parent, cache / base.BASE)
        self.assertIn("cad run: making the CAD kernel environment, once: cad[build123d] ", first.stderr)
        self.assertEqual(Path((project / "worker.txt").read_text(encoding="utf-8")).resolve(), made,
                         "the model's worker runs in the base")
        self.assertEqual(self.asked(["venv", "pip"]), ["venv", "pip"])
        # The base holds no uv: neither its package nor its binary.
        python = base.interpreter(made)
        probe = subprocess.run([str(python), "-c", "import importlib.util, sys; "
                                "sys.exit(importlib.util.find_spec('uv') is not None)"], env=self.env, capture_output=True)
        self.assertEqual(probe.returncode, 0, "no uv package in the base")
        self.assertFalse([path.name for path in python.parent.iterdir() if path.stem == "uv"], "no uv binary there")
        self.assertTrue(list(python.parent.parent.glob("**/cad-*.dist-info")), "cad itself installed there")
        again = self.run_cadgen("run", "model.py", cwd=project)
        self.assertEqual((again.returncode, self.caller(again)), (0, made), again.stderr)
        self.assertEqual(self.asked(["venv", "pip"]), ["venv", "pip"], "made once: nothing asked of uv again")
        status = json.loads(self.run_cadgen("status", "--json", cwd=project).stdout)
        self.assertEqual(Path(status["prefix"]).resolve(), self.core.resolve(), "the engine runs the core")

        # The engine's own kernel processes: the documents worker exports a file, the pool measures it.
        exported = self.run_cadgen("xbf", "export", "XBF/part.xbf", "out.stl", cwd=project)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertGreater((project / "out.stl").stat().st_size, 0)
        inspected = self.run_cadgen("xbf", "inspect", "XBF/part.xbf", "--json", cwd=project)
        self.assertEqual(inspected.returncode, 0, inspected.stdout + inspected.stderr)  # --json says a failure on stdout
        self.assertAlmostEqual(json.loads(inspected.stdout)["summary"]["volume"], 120.0, places=3)


if __name__ == "__main__":
    unittest.main()

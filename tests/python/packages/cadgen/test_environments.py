"""The core and the base, end to end, with the real uv: an installation of cadgen's core alone (this
checkout, editable, without its kernel extra) runs a model -- ``cadgen run`` makes the base once, the
script and its worker run there, and so do the engine's documents worker and meshing pool, while the
engine's daemon runs the core.

uv is reached through a wrapper first on PATH that logs what it is asked. The engine is this file's
own (the runner's ``CADGEN_ENGINE_DIR``), started by ``cadgen run`` with the core's Python and stopped
by the core's ``cadgen stop``. The fake-uv contracts (keys, commands, refusals) are test_base.py's.
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

from tests.python.support import engine_daemon
from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import base  # noqa: E402

MODEL = """\
import sys
from pathlib import Path

import build123d as bd
from cadgen import xbf


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
    found = shutil.which("uv")
    if found is None:
        from uv import find_uv_bin  # cadgen's own dependency

        found = find_uv_bin()
    return found


class CoreAndBaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="cadgen-environments-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        real = _uv()
        # The core: this checkout's cadgen, editable, with its required dependencies and nothing of the kernel.
        cls.core = cls.root / "core"
        subprocess.run([real, "venv", "--no-project", "--python", sys.executable, str(cls.core)], check=True,
                       capture_output=True)
        subprocess.run([real, "pip", "install", "--python", str(base.interpreter(cls.core)), "--link-mode",
                        "hardlink", "-e", str(REPO_ROOT / "packages" / "cadgen")], check=True, capture_output=True)
        # A uv first on PATH that writes a line of what it is asked, then runs the real one.
        folder, cls.log = cls.root / "bin", cls.root / "uv.log"
        folder.mkdir()
        if os.name == "nt":
            (folder / "uv.bat").write_text(f'@echo off\r\necho %1>>"{cls.log}"\r\n"{real}" %*\r\n'
                                           "exit /b %errorlevel%\r\n", encoding="utf-8")
        else:
            wrapper = folder / "uv"
            wrapper.write_text(f"#!/bin/sh\necho \"$1\" >> '{cls.log}'\nexec '{real}' \"$@\"\n", encoding="utf-8")
            wrapper.chmod(0o755)
        environ = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        cls.env = engine_daemon.watched({**environ, "PATH": os.pathsep.join((str(folder), os.environ["PATH"])),
                                         "CADGEN_VIEWER_WARM": "0"}, cls.addClassCleanup)
        cls.cadgen = str(cls.core / ("Scripts/cadgen.exe" if os.name == "nt" else "bin/cadgen"))
        cls.addClassCleanup(lambda: subprocess.run([cls.cadgen, "stop"], env=cls.env, capture_output=True))

    def run_cadgen(self, *args: str, cwd: Path) -> subprocess.CompletedProcess:
        return engine_daemon.run([self.cadgen, *args], env=self.env, cwd=str(cwd))

    def asked(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").split() if self.log.exists() else []

    @staticmethod
    def caller(done: subprocess.CompletedProcess) -> Path:
        lines = [line for line in done.stdout.splitlines() if line.startswith("CALLER ")]
        assert len(lines) == 1, (done.stdout, done.stderr)
        return Path(lines[0][len("CALLER "):]).resolve()

    def test_a_model_and_the_engines_kernel_processes_run_in_the_base_the_engine_in_the_core(self) -> None:
        cache = Path(os.environ["CADGEN_CACHE_DIR"]).resolve()
        self.assertNotEqual(subprocess.run([str(base.interpreter(self.core)), "-c", "import build123d"],
                                           env=self.env, capture_output=True).returncode, 0, "the core has no kernel")
        project = self.root / "project"
        project.mkdir()
        (project / "model.py").write_text(MODEL, encoding="utf-8")
        first = self.run_cadgen("run", "model.py", cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        made = self.caller(first)
        self.assertEqual(made.parent, cache / base.BASE)
        self.assertIn("cadgen run: making the CAD kernel environment, once: cadgen[kernel] ", first.stderr)
        self.assertEqual(Path((project / "worker.txt").read_text(encoding="utf-8")).resolve(), made,
                         "the model's worker runs in the base")
        self.assertEqual(self.asked(), ["venv", "pip"])
        again = self.run_cadgen("run", "model.py", cwd=project)
        self.assertEqual((again.returncode, self.caller(again)), (0, made), again.stderr)
        self.assertEqual(self.asked(), ["venv", "pip"], "made once: nothing asked of uv again")
        status = json.loads(self.run_cadgen("status", "--json", cwd=project).stdout)
        self.assertEqual(Path(status["prefix"]).resolve(), self.core.resolve(), "the engine runs the core")

        # The engine's own kernel processes: the documents worker exports a file, the pool measures it.
        exported = self.run_cadgen("export", "XBF/part.xbf", "out.stl", cwd=project)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertGreater((project / "out.stl").stat().st_size, 0)
        inspected = self.run_cadgen("inspect", "XBF/part.xbf", "--json", cwd=project)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertAlmostEqual(json.loads(inspected.stdout)["summary"]["volume"], 120.0, places=3)


if __name__ == "__main__":
    unittest.main()

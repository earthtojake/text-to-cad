"""A script run with a Python of its own -- a venv's, ``uv run``'s, a plain ``python model.py`` -- is built
by a warm worker running that Python, so the packages of its environment import in its worker
(``Daemon.caller``); one whose worker contract is not the server's is refused in one line before any
worker starts (``contract.refusal``)."""

from __future__ import annotations

import os
import re
import shutil
import site
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import LIBRARY, add_sources

add_sources()

from cad.engine import client, contract  # noqa: E402

# The script: its own package imported as its module loads -- in the worker too, which loads the
# script afresh -- and the kernel in the body alone, so the script's own process never loads it.
SCRIPT = """
import ownpackage
from cad import model


@model
def plate():
    import build123d as bd

    return bd.Box(ownpackage.WIDTH, 10, 2)


if __name__ == "__main__":
    plate()
"""


class OwnPythonTest(unittest.TestCase):
    def setUp(self) -> None:
        # An engine, state and cache of this test's own, its state registering this interpreter as the
        # current installation: the server whose engine runs this checkout's code.
        engine_daemon.isolate(self.addCleanup)
        self.folder = Path(tempfile.mkdtemp(prefix="own-python-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        # A Python of its own: a virtual environment with this checkout's library, the kernel this
        # interpreter has (its site-packages after the environment's own, as an installation reuses the
        # kernel: scripts/test/test-installed.sh), and a package no environment of the server's has.
        venv = self.folder / "venv"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True)
        self.python = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        purelib = Path(subprocess.run([self.python, "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                      check=True, capture_output=True, text=True).stdout.strip())
        (purelib / "_cad_source.pth").write_text(f"{LIBRARY / 'src'}\n", encoding="utf-8")
        (purelib / "zz_kernel.pth").write_text(f"{site.getsitepackages()[0]}\n", encoding="utf-8")
        (purelib / "ownpackage").mkdir()
        (purelib / "ownpackage" / "__init__.py").write_text("WIDTH = 42\n", encoding="utf-8")
        self.project = self.folder / "project"
        self.project.mkdir()
        (self.project / "plate.py").write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        # The engine started by this process, as the registered installation starts it (this checkout's).
        self.assertTrue(client.request({"op": "pid"}).get("ok"))

    def workers(self) -> list[dict]:
        return client.request({"op": "status"}, start=False)["workers"]

    def test_a_script_run_with_its_own_python_is_built_by_a_warm_worker_of_that_python(self) -> None:
        env = engine_daemon.watched({key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                                    self.addCleanup)
        for run in ("cold", "warm"):
            done = engine_daemon.run([self.python, "plate.py"], env=env, cwd=self.project)
            self.assertEqual(done.returncode, 0, f"{done.stdout}\n{done.stderr}")
            self.assertRegex(done.stdout, r"bounds 42\D+10\D+2 mm", "the body read its environment's package")
        self.assertIn("took plate.py::plate warm", done.stdout, "the worker stays warm, its memo with it")
        [worker] = self.workers()
        self.assertEqual((Path(worker["script"]).name, worker["python"], worker["builds"]),
                         ("plate.py", self.python, 2), "one worker, running the script's own Python")
        self.assertNotIn("cad-server is", done.stderr, "one release: no update notice")

    def test_a_contract_the_server_does_not_speak_is_refused_in_one_line_before_any_worker_starts(self) -> None:
        forged = {"executable": self.python, "prefix": str(self.folder / "venv"), "release": "0.0.1",
                  "contract": {**contract.CONTRACT, "protocol": 0}}
        answer = client.request({"op": "build", "script": str(self.project / "plate.py"), "cwd": str(self.project),
                                 "env": dict(os.environ), "interpreter": forged})
        self.assertEqual(answer, {"failed": f"cad here is 0.0.1, worker contract 0 ({contract.CONTRACT['format']}, "
                                            f"{contract.CONTRACT['kernel']}); cad-server {contract.release()} speaks "
                                            f"{contract.spelled(contract.CONTRACT)}: update the cad package in this "
                                            f"environment to {contract.release()}"})
        self.assertEqual(self.workers(), [], "refused before any worker started")
        self.assertIsNone(re.search(r"\n", answer["failed"]))


if __name__ == "__main__":
    unittest.main()

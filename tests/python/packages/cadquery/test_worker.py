"""Real CadQuery under ``@model``: the CadQuery worker the daemon keeps, warm between runs.

``cad run script.py`` in the environment of ``cad[cadquery]`` sends each ``@model`` call as a build order whose
contract names CadQuery's kernel; the daemon (this file's own engine, the kernel on OCP 8.0) starts the
CadQuery worker in that Python (``cad.cadquery._worker``), which runs the function under the CadQuery memo and
answers a portable description; the daemon's documents worker makes the document, which the daemon holds,
serves and exports under the model's ordinary id. A second run of the same script is warm: every kernel
call hits, nothing misses, and the id is the one the first run printed. Runs in the ``cadquery`` job;
anywhere the environment cannot be made it says why it skips.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import cadquery_env, engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()

from cad.engine.ids import model_id  # noqa: E402

MODELS = """
import cadquery as cq
from cad import model


@model
def plate():
    return cq.Workplane("XY").box(40, 20, 6).faces(">Z").workplane().hole(8).edges("|Z").fillet(2)


@model
def bracket():
    found = cq.Assembly(name="bracket")
    found.add(plate().shape, name="plate", color=cq.Color(0.3, 0.5, 0.8))   # a child's value, composed
    found.add(cq.Workplane("XY").cylinder(10, 2), name="peg", loc=cq.Location(cq.Vector(10, 0, 8)))
    return found


if __name__ == "__main__":
    plate()
    bracket()
"""

WRONG = """
from cad import model, step


@model
def nothing():
    return 42


@step("out.step")
def declared():
    import cadquery as cq
    return cq.Workplane("XY").box(1, 1, 1)


if __name__ == "__main__":
    import sys
    for found in (nothing, declared):
        try:
            found()
        except Exception as error:
            print("REFUSED " + str(error), file=sys.stderr)
"""


class Worker(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="cadquery-worker-")))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC)}, cls.addClassCleanup)
        (cls.folder / "models.py").write_text(textwrap.dedent(MODELS), encoding="utf-8")
        (cls.folder / "wrong.py").write_text(textwrap.dedent(WRONG), encoding="utf-8")

    def cli(self, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", *args], cwd=self.folder, env=self.env)

    @staticmethod
    def line(text: str, model: str) -> str:
        found = re.search(rf"^(built {re.escape(model)} .*)$", text, re.M)
        return found.group(1) if found else ""

    def test_a_model_s_second_run_is_warm_in_the_cadquery_worker_and_its_document_is_the_engine_s(self) -> None:
        first = self.cli("run", "models.py")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        said = first.stdout + first.stderr
        plate = self.line(said, "models.py::plate")
        self.assertRegex(plate, r"^built models\.py::plate cold in [\d.]+s: bodies 1 run; \d+ misses, 0 hits", plate)
        misses = int(re.search(r"(\d+) misses", plate).group(1))
        self.assertGreater(misses, 3, "the plate's kernel calls ran")
        self.assertIn(f"id: {model_id(self.folder / 'models.py', 'plate')}", said)
        self.assertIn(f"id: {model_id(self.folder / 'models.py', 'bracket')}", said)
        self.assertIn("view: http", said)
        self.assertRegex(said, r"parts 2 · bounds 40 × 20 × 16 mm", "the delta under the bracket's line: the document is the engine's")
        # Warm: the same worker, every call a hit, nothing run again in the kernel.
        second = self.cli("run", "models.py")
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        warm = self.line(second.stdout + second.stderr, "models.py::plate")
        self.assertRegex(warm, rf"^built models\.py::plate warm in [\d.]+s: bodies 1 run; 0 misses, {misses} hits", warm)
        # The document is the engine's: exported by its id, with the assembly's names and placement.
        ident = model_id(self.folder / "models.py", "bracket")
        out = self.folder / "bracket.step"
        exported = self.cli("model", "export", ident, str(out))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        text = out.read_text(encoding="utf-8", errors="replace")
        for name in ("bracket", "plate", "peg"):
            self.assertIn(f"'{name}'", text)
        inspected = self.cli("model", "inspect", ident)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIn("cadquery", inspected.stdout, "the document's closure names CadQuery's build")

    def test_an_edit_reruns_what_reads_it_and_the_worker_stays_warm_for_the_rest(self) -> None:
        edited = self.folder / "edited"
        edited.mkdir(exist_ok=True)
        script = edited / "models.py"
        script.write_text(textwrap.dedent(MODELS), encoding="utf-8")
        first = self.cli("run", str(script))
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        script.write_text(textwrap.dedent(MODELS).replace("box(40, 20, 6)", "box(50, 20, 6)"), encoding="utf-8")
        second = self.cli("run", str(script))
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        said = second.stdout + second.stderr
        plate = self.line(said, "edited/models.py::plate")
        self.assertRegex(plate, r"warm in [\d.]+s: bodies 1 run; \d+ misses, \d+ hits", plate)
        self.assertGreater(int(re.search(r"(\d+) misses", plate).group(1)), 0, "the box and what reads it ran")
        bracket = self.line(said, "edited/models.py::bracket")
        self.assertGreater(int(re.search(r"(\d+) hits", bracket).group(1)), 0, "the peg's chain was kept")
        self.assertIn("bounds 50 × 20 × 16 mm", said)

    def test_a_body_that_returns_no_cadquery_value_or_declares_a_file_is_refused_by_name(self) -> None:
        done = self.cli("run", "wrong.py")
        said = done.stdout + done.stderr
        self.assertIn("returned int; a model document is made of a CadQuery Workplane, Shape, Sketch or Assembly", said)
        self.assertIn("declared is declared by @step: a CadQuery model declares no file", said)


if __name__ == "__main__":
    unittest.main()

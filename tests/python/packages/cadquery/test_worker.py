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

# A body that imports a helper inside itself and reads a data file: both are its revision's.
READING = """
import json
import pathlib

import cadquery as cq
from cad import model


@model
def sized():
    import helper                                                   # imported inside the body
    params = json.loads(pathlib.Path(__file__).with_name("params.json").read_text(encoding="utf-8"))
    return cq.Workplane("XY").box(params["width"], 20, helper.THICKNESS)


if __name__ == "__main__":
    sized()
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

    def test_an_edited_data_file_or_body_imported_module_is_another_revision_the_cache_keeps(self) -> None:
        folder = self.folder / "reading"
        folder.mkdir(exist_ok=True)
        (folder / "reading.py").write_text(textwrap.dedent(READING), encoding="utf-8")
        (folder / "helper.py").write_text("THICKNESS = 6\n", encoding="utf-8")
        (folder / "params.json").write_text('{"width": 40}\n', encoding="utf-8")
        ident = model_id(folder / "reading.py", "sized")

        def size_from_cache() -> list[float]:
            # The engine restarted: the document comes from the cache alone, as a restart serves it.
            self.assertEqual(self.cli("stop").returncode, 0)
            out = folder / f"{os.urandom(3).hex()}.step"
            exported = self.cli("model", "export", ident, str(out))
            self.assertEqual(exported.returncode, 0, exported.stderr)
            from cad import step

            box = step.read(out).bounding_box()
            return [round(box.size.X, 3), round(box.size.Y, 3), round(box.size.Z, 3)]

        first = self.cli("run", str(folder / "reading.py"))
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertIn("bounds 40 × 20 × 6 mm", first.stdout + first.stderr)
        self.assertEqual(size_from_cache(), [40.0, 20.0, 6.0])
        (folder / "params.json").write_text('{"width": 50}\n', encoding="utf-8")
        second = self.cli("run", str(folder / "reading.py"))
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        self.assertIn("bounds 50 × 20 × 6 mm", second.stdout + second.stderr)
        self.assertEqual(size_from_cache(), [50.0, 20.0, 6.0], "the edited data file is another revision")
        (folder / "helper.py").write_text("THICKNESS = 8\n", encoding="utf-8")
        third = self.cli("run", str(folder / "reading.py"))
        self.assertEqual(third.returncode, 0, third.stderr + third.stdout)
        self.assertIn("bounds 50 × 20 × 8 mm", third.stdout + third.stderr)
        self.assertEqual(size_from_cache(), [50.0, 20.0, 8.0], "the edited module imported inside the body too")


class WorkerAtOneSlot(unittest.TestCase):
    """With one worker slot (``CAD_ENGINE_WORKERS=1``), a CadQuery build still completes: the CadQuery worker
    is let go before its reports are embodied through the documents worker's lease, so the lease never waits
    on the build that holds it. An engine of its own, started with the cap (the file's engine is the other
    class's, started without it), its cache folder -- with the environment of ``cad[cadquery]`` it makes --
    under the script's folder, which the worker must take for the libraries', never the script's own modules."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="cadquery-one-slot-")))
        cls.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.addClassCleanup(shutil.rmtree, cls.engine, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_WORKERS": "1",
                                         "CAD_ENGINE_DIR": str(cls.engine), "CAD_STATE_DIR": str(cls.folder / "state"),
                                         "CAD_CACHE_DIR": str(cls.folder / "cache")}, cls.addClassCleanup)
        cls.addClassCleanup(cls.cli, "stop")
        engine_daemon.register(cls.folder / "state")  # this interpreter as the installation its engine runs
        (cls.folder / "models.py").write_text(textwrap.dedent(MODELS), encoding="utf-8")

    @classmethod
    def cli(cls, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", *args], cwd=cls.folder, env=cls.env)

    def test_a_build_completes_and_its_document_is_held_with_one_slot(self) -> None:
        done = self.cli("run", "models.py")
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        said = done.stdout + done.stderr
        self.assertRegex(said, r"^built models\.py::plate cold in", said)
        self.assertIn("bounds 40 × 20 × 16 mm", said)
        out = self.folder / "bracket.glb"
        exported = self.cli("model", "export", model_id(self.folder / "models.py", "bracket"), str(out))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertTrue(out.is_file())
        again = self.cli("run", "models.py")
        self.assertEqual(again.returncode, 0, again.stderr + again.stdout)


if __name__ == "__main__":
    unittest.main()

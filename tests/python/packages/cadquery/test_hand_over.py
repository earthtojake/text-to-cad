"""Real CadQuery, handed over to the engine: ``model(value, name=...)`` from the environment of ``cad[cadquery]``.

A CadQuery program runs in the environment of the cadquery integration (CadQuery on its own OCP, 7.9, and the
library's core: ``tests/python/support/cadquery_env.py``), hands a Workplane and an Assembly over to this
file's own engine (the test runner's: the kernel on OCP 8.0), which makes their documents, serves them and
exports them; ``cad run`` picks the integration from the script's import and runs the same. No build123d is
imported in the CadQuery program, and no CadQuery in the engine. Runs in the ``cadquery`` job; anywhere the
environment cannot be made it says why it skips.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import cadquery_env, engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()

from cad.engine.ids import derived_id  # noqa: E402

BRACKET = """
import json
import sys

import cadquery as cq
from cad import model


def plate():
    return cq.Workplane("XY").box(40, 20, 6).faces(">Z").workplane().hole(8)


def bracket():
    found = cq.Assembly(name="bracket")
    found.add(plate(), name="plate", color=cq.Color(0.3, 0.5, 0.8))
    found.add(cq.Workplane("XY").cylinder(10, 2), name="peg", loc=cq.Location(cq.Vector(10, 0, 8)),
              color=cq.Color("red"))
    return found


if __name__ == "__main__":
    one = model(plate(), name="plate")
    two = model(bracket(), name="bracket")
    print("RESULT " + json.dumps({"plate": one.id, "bracket": two.id, "url": two.url,
                                  "kernel": sorted(name for name in ("build123d", "OCP", "cadquery") if name in sys.modules)}))
"""


class HandOver(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="cadquery-hand-over-")))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC)}, cls.addClassCleanup)
        (cls.folder / "bracket.py").write_text(textwrap.dedent(BRACKET), encoding="utf-8")

    def cli(self, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", *args], cwd=self.folder, env=self.env)

    def test_a_cadquery_program_s_values_are_documents_served_and_exported_by_the_engine(self) -> None:
        done = engine_daemon.run([cadquery_env.python(self), "bracket.py"], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout.rsplit("RESULT ", 1)[1])
        self.assertEqual(found["kernel"], ["OCP", "cadquery"], "CadQuery's OCP alone: no build123d in the program")
        self.assertEqual((found["plate"], found["bracket"]),
                         (derived_id(self.folder / "bracket.py", "plate"), derived_id(self.folder / "bracket.py", "bracket")))
        self.assertIn("bracket: handed over (", done.stdout)
        self.assertTrue(found["url"].split("?")[0].endswith(f"/{found['bracket']}"), found["url"])
        out = self.folder / "out"
        exported = self.cli("model", "export", found["bracket"], str(out / "bracket.step"), str(out / "bracket.glb"))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        text = (out / "bracket.step").read_text(encoding="utf-8", errors="replace")
        for name in ("bracket", "plate", "peg"):
            self.assertIn(f"'{name}'", text)
        from cad import step

        tree = step.read(out / "bracket.step")
        box = tree.bounding_box()
        self.assertEqual([round(value, 3) for value in (box.size.X, box.size.Y, box.size.Z)], [40.0, 20.0, 16.0],
                         "the plate (z -3..3) and the 10 mm peg centred at z 8 (3..13), placed as the assembly placed it")
        self.assertEqual(sorted(child.label for child in tree.children), ["peg", "plate"])
        self.assertTrue((out / "bracket.glb").is_file())

    def test_cad_run_gives_the_program_the_cadquery_integration_from_its_import(self) -> None:
        done = self.cli("run", "bracket.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("plate: handed over (", done.stdout)
        self.assertIn(f"id: {derived_id(self.folder / 'bracket.py', 'bracket')}", done.stdout)
        self.assertIn("view: http", done.stdout)


if __name__ == "__main__":
    unittest.main()

"""A saved document's names are the labels its author wrote.

Its root was once named after its file, which put a name nobody wrote among the part
labels: in ``arm.step`` the root also answered to ``#arm``, so a clip on the beam
labelled ``arm`` moved the whole model, and the label the author gave the root, like a
single part's own label, resolved to nothing.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

MODELS = """
import cadgen
from cadgen import build123d as bd
from cadgen import step


def lift(t, m):
    m.get("#arm").translate((0, 0, 10 * t))


@step(out="arm.step", animation={"lift": cadgen.clip(lift, duration=1, fps=2)})
def arm():
    base = bd.Box(40, 40, 10)
    base.label = "base"
    beam = bd.Pos(0, 0, 30) * bd.Box(10, 10, 50)
    beam.label = "arm"
    return bd.Compound(children=[base, beam], label="arm_assembly")


@step(out="rig.step")
def rig():
    base = bd.Box(40, 40, 10)
    base.label = "base"
    post = bd.Pos(0, 0, 30) * bd.Box(10, 10, 50)
    post.label = "rig"
    return bd.Compound(children=[base, post])


@step(out="plate.step")
def plate():
    body = bd.Box(30, 20, 4)
    body.label = "plate_body"
    return body
"""

CELL = """
from pathlib import Path

from cadgen import build123d as bd
from cadgen import read_step, step


@step(out="cell.step")
def cell():
    table = bd.Box(200, 100, 5)
    table.label = "table"
    return bd.Compound(children=[table, bd.Pos(60, 0, 5) * read_step(Path(__file__).parent / "rig.step")], label="cell")
"""


class DocumentNamesTests(unittest.TestCase):
    def setUp(self) -> None:
        roots = IsolatedCadRoots(self, prefix="document-names-")
        temp = roots.temporary_cad_directory(prefix="document-names-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def _build(self, name: str, source: str, *models: str) -> None:
        from cadgen.catalog import StepImportOptions
        from cadgen.generation import generate_step_targets

        script = self.root / name
        script.write_text(source, encoding="utf-8")
        targets = [f"{script}::{model}" for model in models] or [str(script)]
        self.assertEqual(0, generate_step_targets(
            targets, step_options=StepImportOptions(), force=True, verbose=False,
        ))

    def test_every_name_is_an_authored_label(self) -> None:
        from cadgen import read_scene
        from cadgen._internal.source_sidecar import read_source_sidecar

        self._build("models.py", MODELS, "arm", "rig", "plate")

        # The root answers to its label, and `#arm` to the beam alone, in the clip too.
        arm = read_scene(self.root / "arm.step")
        self.assertEqual("arm_assembly", arm.roots[0].label)
        self.assertEqual(("#o1", "#o1.2"), (arm.resolve("#arm_assembly").ref, arm.resolve("#arm").ref))
        (track,) = read_source_sidecar(self.root / "arm.step")["animation"]["clips"][0]["tracks"]
        self.assertEqual(["o1.2"], track["targets"])

        # Unlabelled, a root has no name, so a part named like its file keeps its own.
        rig = read_scene(self.root / "rig.step")
        self.assertEqual("o1", rig.roots[0].label)
        self.assertEqual("#o1.2", rig.resolve("#rig").ref)

        # A single part keeps its own label, not its file's.
        plate = read_scene(self.root / "plate.step")
        self.assertEqual(["plate_body"], [leaf.label for leaf in plate.leaves()])
        self.assertEqual("#o1.1", plate.resolve("#plate_body").ref)

        # A document read into another model is named for its place there: the unnamed
        # root's id belonged to its own file.
        self._build("cell.py", CELL)
        cell = read_scene(self.root / "cell.step")
        self.assertEqual("o1.2", cell.resolve("#o1.2").label)
        self.assertEqual("#o1.2.2", cell.resolve("#rig").ref)


if __name__ == "__main__":
    unittest.main()

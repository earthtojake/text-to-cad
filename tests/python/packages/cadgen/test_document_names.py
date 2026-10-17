"""A saved document's names are the labels its author wrote.

Its root was once named after its file, which put a name nobody wrote among the part
labels: in ``arm.step`` the root also answered to ``#arm``, so a clip on the beam
labelled ``arm`` moved the whole model, and the label the author gave the root, like a
single part's own label, resolved to nothing. An unlabelled root is ``model``, an
unlabelled part ``part``: names no author writes, so they answer for nothing authored.
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
        from cadgen.generation import generate_step_targets

        script = self.root / name
        script.write_text(source, encoding="utf-8")
        targets = [f"{script}::{model}" for model in models] or [str(script)]
        self.assertEqual(0, generate_step_targets(
            targets, force=True, verbose=False,
        ))

    def test_every_name_is_an_authored_label(self) -> None:
        from cadgen import read_scene
        from cadgen._internal.source_sidecar import read_source_sidecar

        self._build("models.py", MODELS, "arm", "rig", "plate")

        def leaf(scene, label):
            (found,) = [occurrence for occurrence in scene.leaves() if occurrence.label == label]
            return found

        # The root answers to its label, and `#arm` to the beam alone, in the clip too.
        arm = read_scene(self.root / "arm.step")
        self.assertEqual("arm_assembly", arm.roots[0].label)
        beam = leaf(arm, "arm")
        self.assertNotEqual(arm.roots[0].ref, beam.ref)
        self.assertEqual((arm.roots[0].ref, beam.ref), (arm.resolve("#arm_assembly").ref, arm.resolve("#arm").ref))
        (track,) = read_source_sidecar(self.root / "arm.step")["animation"]["clips"][0]["tracks"]
        self.assertEqual([beam.ref[1:]], track["targets"])

        # Unlabelled, a root is `model`, so a part named like its file keeps its own.
        rig = read_scene(self.root / "rig.step")
        self.assertEqual("model", rig.roots[0].label)
        self.assertEqual(leaf(rig, "rig").ref, rig.resolve("#rig").ref)

        # A single part keeps its own label, not its file's.
        plate = read_scene(self.root / "plate.step")
        self.assertEqual(["plate_body"], [occurrence.label for occurrence in plate.leaves()])
        self.assertEqual(next(plate.leaves()).ref, plate.resolve("#plate_body").ref)

        # A document read into another model is named for its place there: the unnamed
        # root's name was never the file's, so `#rig` still means the post alone.
        self._build("cell.py", CELL)
        cell = read_scene(self.root / "cell.step")
        (linked,) = [child for child in cell.roots[0].children if child.label != "table"]
        self.assertEqual("model", linked.label)
        self.assertEqual(leaf(cell, "rig").ref, cell.resolve("#rig").ref)
        self.assertIn(leaf(cell, "rig"), linked.children)


if __name__ == "__main__":
    unittest.main()

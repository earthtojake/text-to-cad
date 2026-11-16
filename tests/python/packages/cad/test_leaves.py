"""``cad.build123d.leaves``: a STEP's leaves placed where they stand, out of the read tree, on its B-rep.

A two-level STEP (a robot holding an arm, turned and raised, holding a body and a pin) is read with
``step.read``; each leaf comes back placed in the file's frame, with its label, colour and path, no
parent, sharing its ``TShape`` with the tree's leaf, and the tree is left as it was."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path


class Leaves(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="cad-leaves-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_a_read_step_s_leaves_are_placed_alone_on_the_tree_s_brep(self) -> None:
        import build123d as bd

        from cad import step
        from cad.build123d import leaves

        body = bd.Box(10, 10, 10)
        body.label, body.color = "body", bd.Color(1, 0, 0)
        pin = bd.Pos(20, 0, 0) * bd.Cylinder(2, 10)
        pin.label = "pin"
        arm = bd.Compound(children=[body, pin], label="arm")
        arm.location = bd.Location((0, 0, 50), (0, 0, 90))
        path = self.folder / "robot.step"
        bd.export_step(bd.Compound(children=[arm], label="robot"), str(path))

        tree = step.read(path)
        nodes = len(tree.descendants)
        found = leaves(tree, paths=True)
        self.assertEqual([("robot", "arm", "body"), ("robot", "arm", "pin")], [where for where, _leaf in found])
        centres = {leaf.label: leaf.bounding_box().center() for _where, leaf in found}
        self.assertAlmostEqual(0.0, (centres["body"] - bd.Vector(0, 0, 50)).length, places=6)
        self.assertAlmostEqual(0.0, (centres["pin"] - bd.Vector(0, 20, 50)).length, places=6)  # turned with the arm
        originals = {node.label: node for node in tree.leaves}
        for _where, leaf in found:
            original = originals[leaf.label]
            self.assertIsNone(leaf.parent)
            self.assertIsNot(leaf, original)
            self.assertTrue(leaf.wrapped.IsPartner(original.wrapped), "the same B-rep, placed")
            self.assertIsNotNone(original.parent, "the tree keeps its leaf")
        self.assertEqual(found[0][1].color, originals["body"].color)
        self.assertEqual(nodes, len(tree.descendants))
        self.assertEqual([leaf.label for leaf in leaves(tree)], ["body", "pin"])


if __name__ == "__main__":
    unittest.main()

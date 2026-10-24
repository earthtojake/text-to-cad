"""A document's assembly is read in work proportional to the file, or refused. A sub-assembly
shared by several components is walked once per component, so a small file can name an
exponential tree; a component that refers to its own assembly names an endless one. Covers
document.Loaded's walk and reader.assemble, which share the bounds."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine import document, reader  # noqa: E402


def shared_assembly(k: int, n: int, *, cycle: bool = False):
    """A document of one box and ``n`` assembly levels, each of ``k`` components that all refer
    to the level below (``k**n`` placements of the box); ``cycle`` also makes the top level hold
    itself, under one root."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    doc = document._new_document()
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    below = shapes.AddShape(BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(), False)
    for level in range(n):
        assembly = shapes.NewShape()
        for at in range(k):
            move = gp_Trsf()
            move.SetTranslation(gp_Vec(2.0 * at * k ** level, 0.0, 0.0))
            shapes.AddComponent(assembly, below, TopLoc_Location(move))
        below = assembly
    if cycle:
        shapes.AddComponent(below, below, TopLoc_Location())
        root = shapes.NewShape()
        shapes.AddComponent(root, below, TopLoc_Location())
    else:
        shapes.UpdateAssemblies()
    return doc


class LoadedWalkBoundsTest(unittest.TestCase):
    def test_a_small_shared_assembly_reads_every_placement(self):
        loaded = document.Loaded(Path("shared.step"), shared_assembly(2, 3))
        self.assertEqual(len(loaded.instances), 8)
        self.assertEqual(len(loaded.prototypes), 1)

    def test_a_tree_past_the_occurrence_bound_is_refused(self):
        with mock.patch.object(document, "MAX_OCCURRENCES", 1000):
            with self.assertRaisesRegex(ValueError, "more than 1000 occurrences"):
                document.Loaded(Path("shared.step"), shared_assembly(4, 6))  # 5461 occurrences

    def test_an_assembly_that_contains_itself_is_refused(self):
        with self.assertRaisesRegex(ValueError, "contains itself"):
            document.Loaded(Path("cycle.step"), shared_assembly(2, 2, cycle=True))

    def test_a_tree_past_the_depth_bound_is_refused(self):
        with mock.patch.object(document, "MAX_ASSEMBLY_DEPTH", 4):
            with self.assertRaisesRegex(ValueError, "deeper than 4 levels"):
                document.Loaded(Path("deep.step"), shared_assembly(1, 6))


class AssembleBoundsTest(unittest.TestCase):
    def test_a_small_shared_assembly_builds(self):
        header, shapes, locations = reader.describe(shared_assembly(2, 3), True)
        self.assertIsNotNone(reader.assemble(header, shapes, locations))

    def test_a_tree_past_the_occurrence_bound_is_refused(self):
        header, shapes, locations = reader.describe(shared_assembly(4, 6), True)
        with mock.patch.object(document, "MAX_OCCURRENCES", 1000):
            with self.assertRaisesRegex(ValueError, "more than 1000 occurrences"):
                reader.assemble(header, shapes, locations)

    def test_an_assembly_that_contains_itself_is_refused(self):
        header, shapes, locations = reader.describe(shared_assembly(2, 2, cycle=True), True)
        with self.assertRaisesRegex(ValueError, "contains itself"):
            reader.assemble(header, shapes, locations)


if __name__ == "__main__":
    unittest.main()

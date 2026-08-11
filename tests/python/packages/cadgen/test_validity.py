"""cadgen.validity: per-solid topology, closure, and orientation checking."""

import unittest

from build123d import Box, Compound, Pos, Shell, Solid
from OCP.TopoDS import TopoDS

from cadgen.validity import (
    REASON_NON_POSITIVE_VOLUME,
    REASON_NO_SOLID,
    REASON_OPEN_SHELL,
    check_occurrence_shape,
)


def reversed_box(size=10):
    """A solid with inverted orientation: valid topology, negative volume."""
    return Solid(TopoDS.Solid_s(Box(size, size, size).solids()[0].wrapped.Reversed()))


class CheckOccurrenceShapeTest(unittest.TestCase):
    def test_a_closed_positive_solid_passes(self):
        result = check_occurrence_shape(Box(40, 30, 20).wrapped)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["solidCount"], 1)
        self.assertAlmostEqual(result["volumes"][0], 24000.0, delta=1.0)

    def test_an_open_shell_is_reported_as_not_closed(self):
        # Five of six faces: watertight-looking to `refs --facts`, which reports
        # "ok": true and faceCount 5 for exactly this shape.
        result = check_occurrence_shape(Shell(Box(40, 30, 20).faces()[1:]).wrapped)
        self.assertIn(REASON_OPEN_SHELL, result["reasons"])

    def test_an_open_shell_passes_when_surfaces_are_intended(self):
        result = check_occurrence_shape(
            Shell(Box(40, 30, 20).faces()[1:]).wrapped, allow_open=True
        )
        self.assertEqual(result["reasons"], [])

    def test_a_negative_volume_solid_is_reported(self):
        # BRepCheck_Analyzer returns True here -- only the volume sign catches it.
        result = check_occurrence_shape(reversed_box().wrapped)
        self.assertIn(REASON_NON_POSITIVE_VOLUME, result["reasons"])
        self.assertLess(result["volumes"][0], 0.0)

    def test_an_inverted_member_inside_a_compound_is_not_masked_by_cancellation(self):
        # The regression pin for aggregate cancellation: +1000 and -1000 sum to
        # zero, so anything reading a compound's total volume sees nothing wrong.
        compound = Compound([Box(10, 10, 10), Pos(30, 0, 0) * reversed_box()])
        result = check_occurrence_shape(compound.wrapped)
        self.assertIn(REASON_NON_POSITIVE_VOLUME, result["reasons"])
        self.assertEqual(result["solidCount"], 2)

    def test_two_disjoint_sound_solids_do_not_false_positive(self):
        compound = Compound([Box(10, 10, 10), Pos(30, 0, 0) * Box(10, 10, 10)])
        result = check_occurrence_shape(compound.wrapped)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["solidCount"], 2)

    def test_a_shape_with_no_solid_is_reported(self):
        result = check_occurrence_shape(Shell(Box(40, 30, 20).faces()[1:]).wrapped)
        self.assertIn(REASON_NO_SOLID, result["reasons"])

    def test_min_volume_threshold_is_respected(self):
        result = check_occurrence_shape(Box(1, 1, 1).wrapped, min_volume=10.0)
        self.assertIn(REASON_NON_POSITIVE_VOLUME, result["reasons"])

    def test_self_intersection_check_can_be_skipped(self):
        result = check_occurrence_shape(
            Box(40, 30, 20).wrapped, check_self_intersection=False
        )
        self.assertEqual(result["reasons"], [])


if __name__ == "__main__":
    unittest.main()

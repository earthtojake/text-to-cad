"""Exact pairwise overlap, without assembly policy or hidden thresholds."""
import unittest
from unittest import mock

from build123d import Compound, Pos, Solid
from cadgen.geometry import GeometryError, overlap_volume


class OverlapVolumeTests(unittest.TestCase):
    def setUp(self):
        self.a = Solid.make_box(10, 10, 10)

    def test_disjoint_touching_partial_coincident_and_contained(self):
        for b, expected in [
            (Pos(20, 0, 0) * self.a, 0),
            (Pos(10, 0, 0) * self.a, 0),
            (Pos(5, 0, 0) * self.a, 500),
            (self.a, 1000),
            (Pos(1, 1, 1) * Solid.make_box(2, 2, 2), 8),
        ]:
            with self.subTest(expected=expected):
                self.assertAlmostEqual(overlap_volume(self.a, b), expected, places=6)

    def test_overlapping_bounding_boxes_do_not_imply_interference(self):
        self.assertEqual(overlap_volume(Solid.make_sphere(5), Pos(8, 8, 0) * Solid.make_sphere(5)), 0)

    def test_thin_overlap_has_no_design_threshold(self):
        self.assertAlmostEqual(overlap_volume(self.a, Pos(9.99999, 0, 0) * self.a), .001, places=6)

    def test_compounds_are_not_silently_treated_as_one_solid(self):
        with self.assertRaises(TypeError):
            overlap_volume(Compound([self.a]), self.a)

    def test_negative_orientation_is_not_reported_as_zero(self):
        from OCP.TopoDS import TopoDS
        reversed_solid = Solid(TopoDS.Solid_s(self.a.wrapped.Reversed()))
        with self.assertRaisesRegex(ValueError, "positively oriented"):
            overlap_volume(reversed_solid, self.a)

    def test_failed_boolean_is_not_reported_as_zero(self):
        boolean = mock.Mock()
        boolean.IsDone.return_value = False
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Common", return_value=boolean):
            with self.assertRaisesRegex(GeometryError, "did not complete"):
                overlap_volume(self.a, self.a)

    def test_boolean_inputs_have_independent_native_topology(self):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        seen = []
        def common(left, right):
            seen.extend((left, right))
            return BRepAlgoAPI_Common(left, right)
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Common", side_effect=common):
            overlap_volume(self.a, self.a)
        self.assertFalse(seen[0].IsPartner(self.a.wrapped))
        self.assertFalse(seen[1].IsPartner(self.a.wrapped))
        self.assertFalse(seen[0].IsPartner(seen[1]))
        self.assertAlmostEqual(self.a.volume, 1000)

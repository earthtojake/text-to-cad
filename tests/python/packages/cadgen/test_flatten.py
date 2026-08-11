"""Tests for the shared flat-pattern helpers in cadgen.flatten."""

import unittest

from cadgen import flatten


class OffsetTests(unittest.TestCase):
    def test_offset_closed_points_grows_profile(self) -> None:
        rings = flatten.offset_closed_points([(0, 0), (40, 0), (40, 20), (0, 20)], 1.5)

        self.assertEqual(1, len(rings))
        xs = [point[0] for point in rings[0]]
        ys = [point[1] for point in rings[0]]
        self.assertAlmostEqual(-1.5, min(xs))
        self.assertAlmostEqual(41.5, max(xs))
        self.assertAlmostEqual(-1.5, min(ys))
        self.assertAlmostEqual(21.5, max(ys))

    def test_offset_closed_points_shrinks_profile(self) -> None:
        rings = flatten.offset_closed_points([(0, 0), (40, 0), (40, 20), (0, 20)], -2.0)

        self.assertEqual(1, len(rings))
        xs = [point[0] for point in rings[0]]
        self.assertAlmostEqual(2.0, min(xs))
        self.assertAlmostEqual(38.0, max(xs))

    def test_offset_zero_is_identity(self) -> None:
        from shapely.geometry import Polygon

        polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        self.assertIs(polygon, flatten.offset_geometry(polygon, 0.0))

    def test_offset_that_erases_profile_raises(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "empty DXF geometry"):
            flatten.offset_closed_points([(0, 0), (4, 0), (4, 4), (0, 4)], -3.0)

    def test_clean_closed_polyline_points_drops_micron_duplicates(self) -> None:
        points = [(0.0, 0.0), (0.001, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.002)]

        cleaned = flatten.clean_closed_polyline_points(points)

        self.assertEqual([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], cleaned)


if __name__ == "__main__":
    unittest.main()

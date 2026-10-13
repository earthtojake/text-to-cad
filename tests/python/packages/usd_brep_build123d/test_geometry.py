"""Placements match build123d's: rotation order, named planes, derived axes, location grids.

Every solid the package builds is placed by these values, so a convention that drifts
(intrinsic vs extrinsic angles, a plane's x direction) moves geometry without failing.
"""

from __future__ import annotations

import unittest

import numpy as np

from tests.python.packages.usd_brep_build123d.parity import requires_usd_brep


def b3d_matrix(location) -> np.ndarray:
    trsf = location.wrapped.Transformation()
    M = np.eye(4)
    M[:3] = [[trsf.Value(i, j) for j in range(1, 5)] for i in range(1, 4)]
    return M


@requires_usd_brep
class PlacementParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build123d
        import usd_brep_build123d

        cls.bd, cls.ub = build123d, usd_brep_build123d

    def assertSameLocation(self, expected, actual):
        np.testing.assert_allclose(actual.M, b3d_matrix(expected), atol=1e-12)

    def test_locations_and_rotations(self):
        bd, ub = self.bd, self.ub
        self.assertSameLocation(bd.Location((1, 2, 3), (30, 40, 50)), ub.Location((1, 2, 3), (30, 40, 50)))
        self.assertSameLocation(bd.Location((1, 2, 3), (0, 1, 1), 35), ub.Location((1, 2, 3), (0, 1, 1), 35))
        self.assertSameLocation(bd.Rot(10, -20, 70) * bd.Pos(4, 5, 6), ub.Rot(10, -20, 70) * ub.Pos(4, 5, 6))
        self.assertAlmostEqual((ub.Location((0, 0, 0), (10, 20, 30)).orientation - ub.Vector(10, 20, 30)).length, 0, places=9)

    def test_planes(self):
        bd, ub = self.bd, self.ub
        for name in ("XY", "YZ", "ZX", "XZ", "YX", "ZY", "front", "back", "left", "right", "top", "bottom", "isometric"):
            with self.subTest(plane=name):
                self.assertSameLocation(getattr(bd.Plane, name).location, getattr(ub.Plane, name).location)
        self.assertSameLocation(bd.Plane.XZ.rotated((10, 0, 90)).location, ub.Plane.XZ.rotated((10, 0, 90)).location)
        self.assertSameLocation(bd.Plane.YZ.offset(3).location, ub.Plane.YZ.offset(3).location)
        # a plane given only its normal takes OpenCascade's x direction
        for normal in ((1, 2, 3), (0, 0, -1), (0.2, -1, 0.1)):
            with self.subTest(normal=normal):
                self.assertSameLocation(bd.Plane((1, 1, 1), z_dir=normal).location, ub.Plane((1, 1, 1), z_dir=normal).location)

    def test_location_grids(self):
        bd, ub = self.bd, self.ub
        for b3d_grid, ub_grid in (
            (lambda: bd.PolarLocations(7, 5, start_angle=15), lambda: ub.PolarLocations(7, 5, start_angle=15)),
            (lambda: bd.PolarLocations(4, 3, rotate=False, angular_range=90, endpoint=True),
             lambda: ub.PolarLocations(4, 3, rotate=False, angular_range=90, endpoint=True)),
            (lambda: bd.GridLocations(3, 2, 4, 3, align=(bd.Align.MIN, bd.Align.MAX)),
             lambda: ub.GridLocations(3, 2, 4, 3, align=(ub.Align.MIN, ub.Align.MAX))),
        ):
            expected, actual = b3d_grid(), ub_grid()
            self.assertEqual(len(expected.local_locations), len(actual.local_locations))
            for e, a in zip(expected.local_locations, actual.local_locations):
                self.assertSameLocation(e, a)


if __name__ == "__main__":
    unittest.main()

"""``cad.cadjoint.solid``: a cadjoint field as one build123d solid of planar faces.

Each assertion is a fact of the construction: the clevis bracket (``fixtures/clevis_bracket.py``) is drawn
120 x 60 x 52, the space-frame node (``fixtures/space_frame_node.py``) is cut by a 40 mm ball, a box of
half-sizes 150 x 40 x 5 is 300 x 80 x 10 -- so a solid that disagrees is wrong, not merely different
from a recorded run. And each field that makes no part -- clipped, empty, unbounded, shattered, too
fine for the grid -- is refused, in one line naming the fix, before any solid is made of it.
"""

from __future__ import annotations

import math
import runpy
import unittest
from pathlib import Path

import numpy as np
from OCP.BRepCheck import BRepCheck_Analyzer

from cad.cadjoint import solid

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _scene(name: str):
    return runpy.run_path(str(FIXTURES / f"{name}.py"), run_name="__fixture__")["scene"]


def _size(shape) -> tuple[float, float, float]:
    size = shape.bounding_box().size
    return (size.X, size.Y, size.Z)


class ExamplesTest(unittest.TestCase):
    """The two documented parts at a 1 mm cell, each made once for the class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.clevis_scene = _scene("clevis_bracket")
        cls.clevis = solid(cls.clevis_scene, cell=1.0)
        cls.node = solid(_scene("space_frame_node"), cell=1.0)

    def test_the_clevis_bracket_is_one_valid_solid_holding_its_drawn_envelope(self) -> None:
        import build123d as bd

        self.assertIsInstance(self.clevis, bd.Solid)
        self.assertTrue(BRepCheck_Analyzer(self.clevis.wrapped).IsValid())
        self.assertTrue(all(face.geom_type == bd.GeomType.PLANE for face in self.clevis.faces()[:50]))
        # Width: the root blend under each rib foot reaches 0.15 mm past the plate edge (measured on the
        # field); length and height do not move.
        length, width, height = _size(self.clevis)
        self.assertAlmostEqual(length, 120.0, delta=0.15)
        self.assertAlmostEqual(width, 60.0 + 2 * 0.15, delta=0.2)
        self.assertAlmostEqual(height, 52.0, delta=0.15)

    def test_the_clevis_bracket_s_volume_is_the_field_s(self) -> None:
        from cadjoint.meshing.bounds import fit_bounds
        from cadjoint.sdf import volume

        origin, extent = fit_bounds(self.clevis_scene)
        # cadjoint's own estimate, a smoothed count of the field's inside on a grid: within a few per cent.
        estimate = float(volume(self.clevis_scene, bounds=origin, size=extent, resolution=200, epsilon=0.05))
        self.assertAlmostEqual(self.clevis.volume, estimate, delta=0.03 * estimate)

    def test_the_space_frame_node_is_one_open_shell_inside_its_cutting_ball(self) -> None:
        self.assertTrue(BRepCheck_Analyzer(self.node.wrapped).IsValid())
        self.assertEqual(len(self.node.solids()), 1)
        points = np.array([tuple(vertex) for vertex in self.node.vertices()])
        # The ball of radius 40 bounds everything; the up tube's 2 mm wall (radii 9 to 11) meets it at
        # z = sqrt(40^2 - 9^2).
        self.assertLess(np.linalg.norm(points, axis=1).max(), 40.0 + 0.3)
        self.assertAlmostEqual(points[:, 2].max(), math.sqrt(40.0**2 - 9.0**2), delta=0.3)


class MeasuredTest(unittest.TestCase):
    def test_a_plain_box_is_its_size(self) -> None:
        from cadjoint.construction import Solid

        made = solid(Solid.box(size=(20.0, 10.0, 3.0), name="block"), cell=1.0)
        for measured, expected in zip(_size(made), (40.0, 20.0, 6.0)):
            self.assertAlmostEqual(measured, expected, delta=0.05)
        self.assertAlmostEqual(made.volume, 40 * 20 * 6, delta=40 * 20 * 6 * 1e-3)

    def test_a_part_hundreds_of_millimetres_across_is_fitted_whole(self) -> None:
        from cadjoint.construction import Solid

        made = solid(Solid.box(size=(150.0, 40.0, 5.0), position=(0, 0, 5.0), name="bar"), cell=2.0)
        for measured, expected in zip(_size(made), (300.0, 80.0, 10.0)):
            self.assertAlmostEqual(measured, expected, delta=0.1)
        self.assertAlmostEqual(made.bounding_box().min.Z, 0.0, delta=0.05)

    def test_bounds_that_hold_the_part_replace_the_fit(self) -> None:
        from cadjoint.construction import Solid

        made = solid(Solid.sphere(radius=10.0, name="ball"), cell=1.0, bounds=((-12, -12, -12), (12, 12, 12)))
        for measured in _size(made):
            self.assertAlmostEqual(measured, 20.0, delta=0.1)


class RefusedTest(unittest.TestCase):
    def test_bounds_that_cut_through_the_part_are_refused_as_clipped(self) -> None:
        from cadjoint.construction import Solid

        with self.assertRaisesRegex(ValueError, "part of the field lies on or beyond the bounds"):
            solid(Solid.sphere(radius=10.0, name="ball"), cell=1.0, bounds=((-5, -5, -5), (15, 15, 15)))

    def test_bounds_wholly_inside_the_part_hold_no_surface(self) -> None:
        # No surface crosses such a box, so the extractor's own boundary warning never fires; the field is asked.
        from cadjoint.construction import Solid

        with self.assertRaisesRegex(ValueError, "lies wholly inside the part"):
            solid(Solid.sphere(radius=10.0, name="ball"), cell=1.0, bounds=((-5, -5, -5), (5, 5, 5)))

    def test_an_unbounded_field_is_refused_naming_the_way_out(self) -> None:
        from cadjoint.sdf import Plane

        with self.assertRaisesRegex(ValueError, "empty or unbounded .*intersect it with a solid around the part"):
            solid(Plane(0.0), cell=1.0)

    def test_a_wall_thinner_than_the_cells_is_refused_as_several_bodies(self) -> None:
        # A 0.2 mm shell sampled at 1 mm falls apart into fragments.
        from cadjoint.construction import Solid
        from cadjoint.sdf import Shell

        with self.assertRaisesRegex(ValueError, r"separate bodies: a wall or bridge is thinner than about two cells \(2 mm\)"):
            solid(Shell(Solid.sphere(radius=30.0, name="ball"), 0.2), cell=1.0)

    def test_a_cell_too_fine_for_the_grid_is_refused_naming_the_cell_that_fits(self) -> None:
        from cadjoint.construction import Solid

        # The fit holds the 300 mm bar with a margin of its scan's cells, so the cell that fits is a little
        # over 300 / 512 mm.
        with self.assertRaisesRegex(ValueError, r"along x, \d+ cells of 0.5 mm, and an axis takes at most 512: use a "
                                                r"cell of 0\.6\d* mm or more, or intersect the field with a box"):
            solid(Solid.box(size=(150.0, 40.0, 5.0), name="bar"), cell=0.5)

    def test_what_is_no_field_or_no_cell_is_refused(self) -> None:
        from cadjoint.construction import Solid

        import build123d as bd

        with self.assertRaisesRegex(TypeError, r"takes a cadjoint field .*, not build123d\."):
            solid(bd.Box(1, 1, 1), cell=1.0)
        for cell in (0, -1.0, float("nan"), "1", True):
            with self.subTest(cell=cell), self.assertRaisesRegex(ValueError, "cell is the sampling cell"):
                solid(Solid.sphere(radius=10.0, name="ball"), cell=cell)
        with self.assertRaisesRegex(ValueError, "x0 < x1"):
            solid(Solid.sphere(radius=10.0, name="ball"), cell=1.0, bounds=((5, 0, 0), (0, 1, 1)))


class PinnedReleaseTest(unittest.TestCase):
    def test_a_revolve_profile_closed_along_the_axis_shells_like_a_mirrored_one(self) -> None:
        """cadjoint#50, fixed in the pinned release: an edge along the axis is interior, not a surface.

        Shelled, a cup is hollow, so the point on its axis halfway up lies in the cavity, as a mirrored
        profile's does; before the fix the axis was a surface and the shell put material there."""
        from cadjoint.construction import PolygonProfile, SketchPlane, revolve
        from cadjoint.sdf import Shell

        def on_axis(points: list[tuple[float, float]]) -> float:
            profile = PolygonProfile(points, plane=SketchPlane(origin=(0, 0, 0), normal=(0, 1, 0)), name="cup")
            return float(Shell(revolve(profile), 2.0)(np.array([[0.0, 0.0, 25.0]], dtype=np.float32))[0])

        closed = on_axis([(0, 0), (30, 0), (40, 50), (0, 50)])
        mirrored = on_axis([(-30, 0), (30, 0), (40, 50), (-40, 50)])
        self.assertGreater(closed, 20.0)
        self.assertAlmostEqual(closed, mirrored, delta=1e-3)


if __name__ == "__main__":
    unittest.main()

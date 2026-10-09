"""A section is OCCT's cut of the exact BREP: circles are circles, lines are lines.

``cadgen._internal.brep_section`` cuts one component; these cut tiny build123d
shapes whose sections are known in closed form and compare the records to the
analytic answer -- a radius, a centre, a sweep, a rectangle's corners -- rather
than to a picture. Only a solid has material to fill: a plane that merely
touches one, a sheet's cut and a curve lying in the plane fill nothing.
"""

from __future__ import annotations

import math
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Compound, Edge, GeomType, Shell, Solid, Wire  # noqa: E402

from cadgen._internal.brep_section import section_loops  # noqa: E402

TOLERANCE = 1e-9


def cut(shape, normal, offset):
    return section_loops(shape.wrapped, normal=normal, offset=offset)["loops"]


class BrepSectionTests(unittest.TestCase):
    def setUp(self) -> None:
        # Radius 10, height 30, on the XY plane: the axis is +Z through the origin.
        self.cylinder = Solid.make_cylinder(10, 30)

    def test_a_cut_across_the_axis_is_one_exact_circle(self) -> None:
        loops = cut(self.cylinder, (0.0, 0.0, 1.0), 10.0)
        self.assertEqual(1, len(loops))
        self.assertTrue(loops[0]["closed"] and loops[0]["filled"])
        [edge] = loops[0]["edges"]
        arc = edge["arc"]
        self.assertAlmostEqual(10.0, arc["radius"], delta=TOLERANCE)
        for got, want in zip(arc["center"], (0.0, 0.0, 10.0)):
            self.assertAlmostEqual(want, got, delta=TOLERANCE)
        self.assertAlmostEqual(1.0, abs(arc["axis"][2]), delta=TOLERANCE)
        self.assertAlmostEqual(2 * math.pi, abs(arc["sweep"]), delta=TOLERANCE)
        start = arc["start"]
        self.assertAlmostEqual(10.0, math.hypot(start[0], start[1]), delta=TOLERANCE)
        self.assertAlmostEqual(10.0, start[2], delta=TOLERANCE)

    def test_a_cut_through_the_axis_is_the_exact_rectangle(self) -> None:
        loops = cut(self.cylinder, (0.0, 1.0, 0.0), 0.0)
        self.assertEqual(1, len(loops))
        self.assertTrue(loops[0]["closed"])
        edges = loops[0]["edges"]
        self.assertEqual(4, len(edges))
        self.assertTrue(all("line" in edge for edge in edges), edges)
        corners = {tuple(round(value, 9) + 0.0 for value in point) for edge in edges for point in edge["line"]}
        self.assertEqual({(-10.0, 0.0, 0.0), (-10.0, 0.0, 30.0), (10.0, 0.0, 30.0), (10.0, 0.0, 0.0)}, corners)
        # The loop is walked in order: each edge starts where the last one ended.
        for previous, following in zip(edges, edges[1:] + edges[:1]):
            self.assertLess(math.dist(previous["line"][1], following["line"][0]), 1e-7)

    def test_a_tube_cuts_to_its_two_exact_rings(self) -> None:
        tube = Solid.make_cylinder(10, 20) - Solid.make_cylinder(6, 20)
        loops = cut(tube, (0.0, 0.0, 1.0), 5.0)
        radii = sorted(edge["arc"]["radius"] for loop in loops for edge in loop["edges"])
        self.assertEqual(2, len(loops))
        self.assertAlmostEqual(6.0, radii[0], delta=TOLERANCE)
        self.assertAlmostEqual(10.0, radii[1], delta=TOLERANCE)

    def test_an_oblique_cut_samples_its_ellipse_on_the_surface_and_the_plane(self) -> None:
        normal = (0.0, 0.6, 0.8)
        loops = cut(self.cylinder, normal, 12.0)
        points = [point for loop in loops for edge in loop["edges"] for point in edge.get("points", [])]
        self.assertGreater(len(points), 16, loops)
        for point in points:
            self.assertAlmostEqual(10.0, math.hypot(point[0], point[1]), delta=1e-6)
            self.assertAlmostEqual(12.0, sum(a * b for a, b in zip(normal, point)), delta=1e-6)

    def test_a_plane_that_misses_cuts_nothing(self) -> None:
        self.assertEqual([], cut(self.cylinder, (0.0, 0.0, 1.0), 31.0))


class SectionMaterialTests(unittest.TestCase):
    """A section is the material the plane cuts: only a solid's cut is filled."""

    def test_a_solids_cut_is_its_material_and_a_tangent_touch_cuts_none(self) -> None:
        # A ring of major radius 10 and minor radius 3 about Z: its mid-plane cuts the annulus
        # between radii 7 and 13; the plane Z=3 only touches its top along the circle r=10,
        # where there is no material to fill (the disc inside that circle is the ring's hole).
        ring = Solid.make_torus(10, 3)
        loops = cut(ring, (0.0, 0.0, 1.0), 0.0)
        self.assertEqual([True, True], [loop["filled"] and loop["closed"] for loop in loops])
        radii = sorted(edge["arc"]["radius"] for loop in loops for edge in loop["edges"])
        self.assertEqual(2, len(radii), loops)
        self.assertAlmostEqual(7.0, radii[0], delta=TOLERANCE)
        self.assertAlmostEqual(13.0, radii[1], delta=TOLERANCE)
        self.assertEqual([], cut(ring, (0.0, 0.0, 1.0), 3.0))
        # The same along a cylinder's side: the plane x=10 touches it along a line.
        self.assertEqual([], cut(Solid.make_cylinder(10, 30), (1.0, 0.0, 0.0), 10.0))

    def test_a_face_lying_in_the_plane_is_material_in_the_plane(self) -> None:
        # A box standing on Z=0, cut at its floor: the closed solid meets the plane in its whole
        # bottom face, which is what the section shows.
        [loop] = cut(Solid.make_box(20, 10, 5), (0.0, 0.0, 1.0), 0.0)
        self.assertTrue(loop["filled"])
        corners = {tuple(round(value, 9) + 0.0 for value in edge["line"][0]) for edge in loop["edges"]}
        self.assertEqual({(0.0, 0.0, 0.0), (20.0, 0.0, 0.0), (20.0, 10.0, 0.0), (0.0, 10.0, 0.0)}, corners)

    def test_a_sheet_is_cut_along_curves_that_are_never_filled(self) -> None:
        # A tube's side alone, no caps and no solid: cut across, a closed circle with nothing in it.
        [side] = [face for face in Solid.make_cylinder(10, 30).faces() if face.geom_type == GeomType.CYLINDER]
        [loop] = cut(Shell([side]), (0.0, 0.0, 1.0), 10.0)
        self.assertEqual((True, False), (loop["closed"], loop["filled"]))
        self.assertAlmostEqual(10.0, loop["edges"][0]["arc"]["radius"], delta=TOLERANCE)

    def test_curves_are_no_material_even_lying_in_the_plane(self) -> None:
        curves = Compound([Wire.make_circle(5), Edge.make_line((0, 0, 0), (10, 0, 0))])
        self.assertEqual([], cut(curves, (0.0, 0.0, 1.0), 0.0))


if __name__ == "__main__":
    unittest.main()

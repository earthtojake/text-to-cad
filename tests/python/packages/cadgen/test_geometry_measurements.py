"""Measurement contracts tested against analytic geometry."""
import unittest
from unittest import mock

from build123d import Compound, Pos, Rot, Solid, Vector, Vertex
from cadgen.geometry import GeometryError, closest_points, mass_properties


class ClosestPointsTests(unittest.TestCase):
    def test_vertices_and_separated_solids_have_witnesses_in_world_frame(self):
        a, b = Vertex(1, 2, 3), Vertex(4, 6, 3)
        result = closest_points(a, b)
        self.assertAlmostEqual(result.distance, 5)
        self.assertLess((result.point_a - Vector(1, 2, 3)).length, 1e-8)
        self.assertLess((result.point_b - Vector(4, 6, 3)).length, 1e-8)
        a = Solid.make_box(2, 3, 4)
        result = closest_points(a, Pos(10, 0, 0) * a)
        self.assertAlmostEqual(result.distance, 8)
        self.assertAlmostEqual((result.point_b - result.point_a).length, result.distance)

    def test_contact_overlap_and_containment_are_zero(self):
        a = Solid.make_box(10, 10, 10)
        for b in (Pos(10, 0, 0) * a, Pos(5, 0, 0) * a, Pos(2, 2, 2) * Solid.make_box(1, 1, 1)):
            self.assertAlmostEqual(closest_points(a, b).distance, 0)
        # Surface distance is a different query, even with nested solids.
        b = Pos(2, 2, 2) * Solid.make_box(1, 1, 1)
        self.assertAlmostEqual(closest_points(a.shell(), b.shell()).distance, 2)

    def test_nonempty_surface_without_vertices_is_measurable(self):
        from build123d import Face
        self.assertAlmostEqual(closest_points(Face.make_plane(), Vertex(0, 0, 5)).distance, 5)

    def test_compound_containment_counts_solid_interiors_in_both_orders(self):
        outer = Solid.make_box(10, 10, 10)
        inner = Pos(2, 2, 2) * Solid.make_box(1, 1, 1)
        for a in (outer, Compound([outer]), Compound([Compound([outer]), Vertex(30, 0, 0)])):
            for b in (inner, Compound([inner])):
                for left, right in ((a, b), (b, a)):
                    with self.subTest(left=type(left).__name__, right=type(right).__name__):
                        result = closest_points(left, right)
                        self.assertEqual(result.distance, 0)
                        self.assertLess((result.point_a - result.point_b).length, 1e-8)
                        self.assertTrue(outer.is_inside(result.point_a))
                        self.assertTrue(inner.is_inside(result.point_b))

    def test_nested_compound_locations_and_disconnected_members(self):
        outer = Solid.make_box(10, 10, 10)
        frame = Pos(100, -50, 12) * Rot(0, 0, 30)
        a = frame * Compound([Compound([outer]), Pos(50, 0, 0) * outer])
        b = frame * Compound([Pos(2, 2, 2) * Solid.make_box(1, 1, 1)])
        self.assertEqual(closest_points(a, b).distance, 0)
        c = frame * Compound([Pos(70, 0, 0) * Solid.make_box(1, 1, 1)])
        result = closest_points(a, c)
        self.assertAlmostEqual(result.distance, 10)
        self.assertAlmostEqual((result.point_a - result.point_b).length, 10)

    def test_compounds_preserve_loose_geometry_and_shell_boundaries(self):
        from build123d import Edge, Face

        far = Pos(100, 100, 100) * Solid.make_box(1, 1, 1)
        for loose in (Vertex(0, 0, 0), Edge.make_line((-2, 0, 0), (2, 0, 0)), Face.make_plane()):
            for a, b in ((Compound([far, loose]), Vertex(0, 0, 5)),
                         (Vertex(0, 0, 5), Compound([far, loose]))):
                self.assertAlmostEqual(closest_points(a, b).distance, 5)
        outer = Solid.make_box(10, 10, 10)
        inner = Pos(2, 2, 2) * Solid.make_box(1, 1, 1)
        self.assertAlmostEqual(closest_points(Compound([outer.shell()]), Compound([inner.shell()])).distance, 2)

    def test_a_solid_cavity_is_not_containment(self):
        outer = Solid.make_box(10, 10, 10)
        hollow = (outer - Pos(2, 2, 2) * Solid.make_box(6, 6, 6)).solids()[0]
        inner = Pos(4, 4, 4) * Solid.make_box(1, 1, 1)
        for a, b in ((Compound([hollow]), inner), (inner, Compound([hollow]))):
            self.assertAlmostEqual(closest_points(a, b).distance, 2)

    def test_empty_or_failed_queries_do_not_return_a_distance(self):
        with self.assertRaises(ValueError):
            closest_points(Compound(), Vertex(0, 0, 0))
        query = mock.Mock()
        query.IsDone.return_value = False
        with mock.patch("OCP.BRepExtrema.BRepExtrema_DistShapeShape", return_value=query):
            with self.assertRaises(GeometryError):
                closest_points(Vertex(0, 0, 0), Vertex(1, 1, 1))


class MassPropertiesTests(unittest.TestCase):
    def test_density_volume_and_centroidal_inertia(self):
        props = mass_properties([(Solid.make_box(2, 4, 6), 3)])
        self.assertAlmostEqual(props.volume, 48)
        self.assertAlmostEqual(props.mass, 144)
        self.assertLess((props.center_of_mass - Vector(1, 2, 3)).length, 1e-8)
        for i, expected in enumerate((624, 480, 240)):
            self.assertAlmostEqual(props.inertia[i][i], expected)
        self.assertAlmostEqual(props.inertia[0][1], 0)

    def test_rotation_changes_tensor_axes_but_translation_does_not(self):
        body = Solid.make_box(2, 4, 6)
        props = mass_properties([(Pos(100, 30, -8) * Rot(0, 0, 45) * body, 3)])
        self.assertAlmostEqual(props.inertia[0][0], 552)
        self.assertAlmostEqual(props.inertia[1][1], 552)
        self.assertAlmostEqual(props.inertia[0][1], 72)
        self.assertAlmostEqual(props.inertia[1][0], 72)
        self.assertAlmostEqual(props.inertia[2][2], 240)

    def test_parallel_axis_and_mixed_density(self):
        body = Solid.make_box(2, 2, 2)
        props = mass_properties([(body, 1), (Pos(6, 0, 0) * body, 2)])
        self.assertAlmostEqual(props.volume, 16)
        self.assertAlmostEqual(props.mass, 24)
        self.assertLess((props.center_of_mass - Vector(5, 1, 1)).length, 1e-8)
        self.assertAlmostEqual(props.inertia[0][0], 16)
        self.assertAlmostEqual(props.inertia[1][1], 208)
        self.assertAlmostEqual(props.inertia[2][2], 208)
        self.assertAlmostEqual(mass_properties([(body, 1), (body, 1)]).mass, 16)

    def test_invalid_inputs_are_not_laundered(self):
        body = Solid.make_box(1, 1, 1)
        for density in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(density=density), self.assertRaises(ValueError):
                mass_properties([(body, density)])
        with self.assertRaises(ValueError):
            mass_properties([])
        with self.assertRaises(TypeError):
            mass_properties([(Compound([body]), 1)])

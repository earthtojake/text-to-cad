"""Independent native geometry diagnostics; no automatic assembly verdict."""
import unittest
from unittest import mock

from build123d import Compound, Pos, Shell, Solid
from OCP.TopoDS import TopoDS
from cadgen.geometry import GeometryError, boundary_edges, self_intersections, topology_errors


class GeometryDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.box = Solid.make_box(10, 10, 10)

    def test_open_shell_and_reversed_solid_are_not_topology_errors(self):
        self.assertEqual(topology_errors(self.box), ())
        opened = Shell(self.box.faces()[1:])
        self.assertEqual(topology_errors(opened), ())
        reversed_solid = Solid(TopoDS.Solid_s(self.box.wrapped.Reversed()))
        self.assertEqual(topology_errors(reversed_solid), ())
        self.assertLess(reversed_solid.volume, 0)

    def test_open_solid_reports_native_fault_and_entities(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Solid
        wrapped, builder = TopoDS_Solid(), BRep_Builder()
        builder.MakeSolid(wrapped)
        builder.Add(wrapped, Shell(self.box.faces()[1:]).wrapped)
        broken = Solid(wrapped)
        issues = topology_errors(broken)
        self.assertTrue(issues)
        self.assertTrue(all(issue.code.startswith("BRepCheck_") and issue.entities for issue in issues))
        self.assertTrue(any("NotClosed" in issue.code or "Unorientable" in issue.code for issue in issues))

    def test_free_edges_exclude_closed_shell_seams(self):
        self.assertEqual(boundary_edges(self.box.shell()), ())
        self.assertEqual(boundary_edges(Solid.make_cylinder(5, 10).shell()), ())
        opened = Shell(self.box.faces()[1:])
        free = boundary_edges(opened)
        self.assertEqual(len(free), 4)
        self.assertAlmostEqual(sum(edge.length for edge in free), 40)
        self.assertFalse(free[0].wrapped.IsPartner(opened.edges()[0].wrapped))

    def test_boundary_check_requires_a_shell(self):
        with self.assertRaises(TypeError):
            boundary_edges(self.box)

    def test_self_intersections_return_localized_entities(self):
        self.assertEqual(self_intersections(self.box), ())
        self.assertEqual(self_intersections(Compound([self.box, Pos(20, 0, 0) * self.box])), ())
        issues = self_intersections(Compound([self.box, Pos(5, 0, 0) * self.box]))
        self.assertTrue(issues)
        self.assertTrue(all(i.code == "BOPAlgo_SelfIntersect" and i.entities for i in issues))
        self.assertTrue(any(entity.shape_type != "Compound" for i in issues for entity in i.entities))

    def test_checker_failure_and_inconclusive_result_raise(self):
        checker = mock.Mock()
        checker.HasErrors.return_value = True
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", return_value=checker):
            with self.assertRaises(GeometryError):
                self_intersections(self.box)
        checker.HasErrors.return_value = False
        checker.IsValid.return_value = False
        checker.Result.return_value = []
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", return_value=checker):
            with self.assertRaises(GeometryError):
                self_intersections(self.box)

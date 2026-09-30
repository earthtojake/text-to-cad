"""Independent native geometry diagnostics; no automatic assembly verdict."""
import unittest
from unittest import mock

from build123d import Compound, Pos, Shell, Solid, Wire
from OCP.TopoDS import TopoDS
from cadgen.geometry import GeometryError, boundary_edges, is_sound, self_intersections, topology_errors


def _open_solid():
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Solid
    wrapped, builder = TopoDS_Solid(), BRep_Builder()
    builder.MakeSolid(wrapped)
    builder.Add(wrapped, Shell(Solid.make_box(10, 10, 10).faces()[1:]).wrapped)
    return Solid(wrapped)


def _overlapping_boxes():
    box = Solid.make_box(10, 10, 10)
    return Compound([box, Pos(5, 0, 0) * box])


class _Results(list):
    """An OCCT list stand-in: sized, iterable."""

    def Size(self):
        return len(self)


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
        issues = topology_errors(_open_solid())
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

    def test_self_intersections_return_localized_owned_entities(self):
        self.assertEqual(self_intersections(self.box), ())
        self.assertEqual(self_intersections(Compound([self.box, Pos(20, 0, 0) * self.box])), ())
        source = _overlapping_boxes()
        issues = self_intersections(source)
        self.assertTrue(issues)
        self.assertTrue(all(i.code == "BOPAlgo_SelfIntersect" and i.entities for i in issues))
        self.assertTrue(any(entity.shape_type != "Compound" for i in issues for entity in i.entities))
        # The entities are owned copies: none shares topology with the caller's shape.
        self.assertFalse(any(entity.wrapped.IsPartner(face.wrapped)
                             for i in issues for entity in i.entities for face in source.faces()))

    def test_checker_failure_and_inconclusive_result_raise(self):
        checker = mock.Mock()
        checker.HasErrors.return_value = True
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", return_value=checker):
            with self.assertRaises(GeometryError):
                self_intersections(self.box)
        checker.HasErrors.return_value = False
        checker.IsValid.return_value = False
        from OCP.BOPAlgo import BOPAlgo_ListOfCheckResult
        checker.Result.return_value = BOPAlgo_ListOfCheckResult()
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", return_value=checker):
            with self.assertRaisesRegex(GeometryError, "without diagnostics"):
                self_intersections(self.box)

    def test_self_intersection_check_runs_the_kernel_once(self):
        # BRepAlgoAPI_Check(shape, bTestSE, bTestSI) performs the check in its
        # constructor; a further Perform() repeats the whole boolean analysis.
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Check as real_check
        performs = []

        class Counted:
            def __init__(self, *args):
                self._checker = real_check(*args)

            def Perform(self, *args):
                performs.append(args)
                return self._checker.Perform(*args)

            def __getattr__(self, name):
                return getattr(self._checker, name)

        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", Counted):
            issues = self_intersections(_overlapping_boxes())
        self.assertEqual(performs, [])
        self.assertTrue(issues)
        self.assertTrue(all(i.code == "BOPAlgo_SelfIntersect" and i.entities for i in issues))


class IsSoundTests(unittest.TestCase):
    """``is_sound``: the boolean kernel's argument check, a pass/fail verdict."""

    CHECKER = "OCP.BRepAlgoAPI.BRepAlgoAPI_Check"

    def test_verdicts_match_the_kernel(self):
        self.assertIs(is_sound(Solid.make_box(10, 10, 10)), True)
        self.assertIs(is_sound(_overlapping_boxes()), False)   # BRepCheck-valid, self-intersecting
        self.assertIs(is_sound(_open_solid()), False)          # BRepCheck-invalid

    def test_null_and_empty_shapes_are_not_sound(self):
        # A gate in a model body must not crash on an empty intermediate: the
        # boolean kernel rejects it as an argument (BOPAlgo_BadType), a verdict.
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Shell, TopoDS_Solid, TopoDS_Wire

        def empty(topods, make):
            make(topods)
            return topods

        builder = BRep_Builder()
        null = Solid()
        null.wrapped = TopoDS_Solid()  # a null native shape
        shapes = (Solid(), null, Compound([]), Solid(empty(TopoDS_Solid(), builder.MakeSolid)),
                  Shell(empty(TopoDS_Shell(), builder.MakeShell)), Wire(empty(TopoDS_Wire(), builder.MakeWire)))
        self.assertEqual([is_sound(shape) for shape in shapes], [False] * len(shapes))

    def test_failed_and_inconclusive_checks_raise(self):
        from OCP.BOPAlgo import BOPAlgo_CheckStatus
        box = Solid.make_box(10, 10, 10)
        checker = mock.Mock()
        checker.HasErrors.return_value = True
        with mock.patch(self.CHECKER, return_value=checker):
            with self.assertRaisesRegex(GeometryError, "checker failed"):
                is_sound(box)
        checker.HasErrors.return_value = False
        for status in (BOPAlgo_CheckStatus.BOPAlgo_CheckUnknown, BOPAlgo_CheckStatus.BOPAlgo_OperationAborted):
            result = mock.Mock()
            result.GetCheckStatus.return_value = status
            checker.Result.return_value = _Results([result])
            with self.subTest(status=status.name), mock.patch(self.CHECKER, return_value=checker):
                with self.assertRaisesRegex(GeometryError, "inconclusive"):
                    is_sound(box)


class OcctListIterationTests(unittest.TestCase):
    def test_items_never_exhausts_the_binding_iterator(self):
        # Exhausting a pybind iterator over an OCCT list unwinds a C++
        # exception (milliseconds each on macOS); _items takes Size() elements.
        from cadgen.geometry import _items

        class Guarded:
            def __init__(self, values):
                self.values = values

            def Size(self):
                return len(self.values)

            def __iter__(self):
                yield from self.values
                raise AssertionError("iterated past Size()")

        self.assertEqual(_items(Guarded(["a", "b"])), ["a", "b"])
        self.assertEqual(_items(Guarded([])), [])

    def test_items_match_full_iteration_of_real_checker_lists(self):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
        from cadgen.geometry import _items
        checker = BRepAlgoAPI_Check(_overlapping_boxes().wrapped, False, True)
        results = list(checker.Result())
        self.assertTrue(results)
        self.assertEqual(len(_items(checker.Result())), len(results))
        for result in results:
            for faulty in (result.GetFaultyShapes1(), result.GetFaultyShapes2()):
                expected = list(faulty)
                got = _items(faulty)
                self.assertEqual(len(got), len(expected))
                self.assertTrue(all(a.IsEqual(b) for a, b in zip(got, expected)))


if __name__ == "__main__":
    unittest.main()

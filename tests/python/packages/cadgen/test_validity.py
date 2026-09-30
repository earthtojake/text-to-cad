"""Independent native geometry diagnostics; no automatic assembly verdict."""
import os
import tempfile
import unittest
from unittest import mock

from build123d import Compound, Pos, Rot, Shell, Solid, Wire
from OCP.TopoDS import TopoDS
from cadgen._internal import op_memo
from cadgen.geometry import (GeometryError, boundary_edges, is_sound, is_valid, self_intersections,
                             topology_errors)


class _FreshStore(unittest.TestCase):
    """Each test gets its own store and an empty RAM tier, so verdicts reused
    from another test (or an earlier run) can never answer for this one."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": tmp.name, "CADGEN_OP_MEMO": "1"})
        env.start()
        self.addCleanup(env.stop)
        op_memo.clear()
        self.addCleanup(op_memo.clear)


class GeometryDiagnosticsTests(_FreshStore):
    def setUp(self):
        super().setUp()
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

        overlapping = Compound([self.box, Pos(5, 0, 0) * self.box])
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", Counted):
            issues = self_intersections(overlapping)
        self.assertEqual(performs, [])
        self.assertTrue(issues)
        self.assertTrue(all(i.code == "BOPAlgo_SelfIntersect" and i.entities for i in issues))


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


def _describe(issues):
    """Everything a verdict says: codes, and each entity's kind, orientation,
    placement and vertices, plus which entities are the same sub-shape."""
    entities = [entity for issue in issues for entity in issue.entities]
    def entity(shape):
        trsf = shape.wrapped.Location().Transformation()
        return (type(shape).__name__, int(shape.wrapped.Orientation()),
                tuple(round(trsf.Value(r, c), 9) for r in (1, 2, 3) for c in (1, 2, 3, 4)),
                tuple(tuple(round(x, 9) for x in v) for v in shape.vertices()))
    shared = tuple(tuple(a.wrapped.IsSame(b.wrapped) for b in entities) for a in entities)
    return tuple((issue.code, tuple(entity(s) for s in issue.entities)) for issue in issues), shared


class _Counting:
    """Count constructions of an OCCT checker class while delegating to it."""

    def __init__(self, real):
        self.real, self.calls = real, 0

    def __call__(self, *args):
        self.calls += 1
        return self.real(*args)


class ReusedVerdictTests(_FreshStore):
    def _uncached(self, check, make):
        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0"}):
            return check(make())

    def _assert_reused(self, check, make, target):
        module, name = target.rsplit(".", 1)
        import importlib
        counter = _Counting(getattr(importlib.import_module(module), name))
        expected = _describe(self._uncached(check, make))
        with mock.patch(target, counter):
            first = check(make())
            self.assertEqual(counter.calls, 1)
            second = check(make())          # warm: the RAM tier
            op_memo.clear()
            third = check(make())           # a fresh process: the disk tier
        self.assertEqual(counter.calls, 1)
        for verdict in (first, second, third):
            self.assertEqual(_describe(verdict), expected)
        return first, second

    def test_self_intersection_verdict_is_reused_exactly(self):
        first, second = self._assert_reused(
            self_intersections, _overlapping_boxes, "OCP.BRepAlgoAPI.BRepAlgoAPI_Check")
        self.assertTrue(first)
        # Every answer owns its entities: a reused verdict shares no topology
        # with an earlier answer or with the caller's shape.
        self.assertFalse(first[0].entities[0].wrapped.IsPartner(second[0].entities[0].wrapped))
        source = _overlapping_boxes()
        self.assertFalse(any(second[0].entities[0].wrapped.IsPartner(f.wrapped) for f in source.faces()))

    def test_clean_self_intersection_verdict_is_reused(self):
        self._assert_reused(self_intersections, lambda: Solid.make_box(10, 10, 10),
                            "OCP.BRepAlgoAPI.BRepAlgoAPI_Check")

    def test_topology_verdict_is_reused_exactly(self):
        first, _ = self._assert_reused(topology_errors, _open_solid, "OCP.BRepCheck.BRepCheck_Analyzer")
        self.assertTrue(first)
        self._assert_reused(topology_errors, lambda: Solid.make_box(10, 10, 10),
                            "OCP.BRepCheck.BRepCheck_Analyzer")

    def test_placement_and_orientation_are_part_of_the_key(self):
        counter = _Counting(__import__("OCP.BRepAlgoAPI", fromlist=["x"]).BRepAlgoAPI_Check)
        box = Solid.make_box(10, 10, 10)
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", counter):
            self_intersections(box)
            self_intersections(Pos(1, 0, 0) * box)
            self_intersections(Rot(0, 0, 90) * box)
            self_intersections(Solid(TopoDS.Solid_s(box.wrapped.Reversed())))
        self.assertEqual(counter.calls, 4)

    def test_failures_are_not_reused(self):
        checker = mock.Mock()
        checker.HasErrors.return_value = True
        box = Solid.make_box(10, 10, 10)
        with mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", return_value=checker):
            with self.assertRaises(GeometryError):
                self_intersections(box)
        self.assertEqual(self_intersections(box), ())

    def test_disabled_memo_runs_every_check(self):
        counter = _Counting(__import__("OCP.BRepAlgoAPI", fromlist=["x"]).BRepAlgoAPI_Check)
        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0"}), \
                mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", counter):
            self_intersections(_overlapping_boxes())
            self_intersections(_overlapping_boxes())
        self.assertEqual(counter.calls, 2)

    def test_unaddressable_entities_are_rechecked_not_reused(self):
        counter = _Counting(__import__("OCP.BRepAlgoAPI", fromlist=["x"]).BRepAlgoAPI_Check)
        expected = _describe(self._uncached(self_intersections, _overlapping_boxes))
        with mock.patch("cadgen.geometry._encode", return_value=None), \
                mock.patch("OCP.BRepAlgoAPI.BRepAlgoAPI_Check", counter):
            first = self_intersections(_overlapping_boxes())
            second = self_intersections(_overlapping_boxes())
        self.assertEqual(counter.calls, 2)
        self.assertEqual(_describe(first), expected)
        self.assertEqual(_describe(second), expected)


class _Results(list):
    """An OCCT list stand-in: sized, iterable."""

    def Size(self):
        return len(self)


class CheckVerdictTests(_FreshStore):
    """``is_valid``/``is_sound``: the same answer as the kernel, stored once,
    answered from RAM and disk. build123d's own ``Shape.is_valid`` is not
    interposed on: a caller that wants a stored verdict asks for one."""

    ANALYZER = "OCP.BRepCheck.BRepCheck_Analyzer"
    CHECKER = "OCP.BRepAlgoAPI.BRepAlgoAPI_Check"

    def setUp(self):
        super().setUp()
        op_memo.install()

    def _uncached(self, check, shape):
        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0"}):
            return check(shape)

    def test_verdicts_match_the_kernel(self):
        cases = ((Solid.make_box(10, 10, 10), True, True),
                 (_overlapping_boxes(), True, False),
                 (_open_solid(), False, False))
        for shape, valid, sound in cases:
            for check, expected in ((is_valid, valid), (is_sound, sound)):
                self.assertIs(self._uncached(check, shape), expected)
                self.assertIs(check(shape), expected)   # a miss
                self.assertIs(check(shape), expected)   # a RAM hit
                op_memo.clear()
                self.assertIs(check(shape), expected)   # a disk hit

    def _assert_stored_once(self, check, make, target):
        import importlib
        module, name = target.rsplit(".", 1)
        counter = _Counting(getattr(importlib.import_module(module), name))
        expected = self._uncached(check, make())
        with mock.patch(target, counter):
            self.assertIs(check(make()), expected)
            self.assertIs(check(make()), expected)      # warm: the RAM tier
            op_memo.clear()
            self.assertIs(check(make()), expected)      # a fresh process: the disk tier
        self.assertEqual(counter.calls, 1)

    def test_is_valid_verdict_is_stored_once(self):
        self._assert_stored_once(is_valid, _open_solid, self.ANALYZER)
        self._assert_stored_once(is_valid, lambda: Solid.make_box(10, 10, 10), self.ANALYZER)

    def test_is_sound_verdict_is_stored_once(self):
        self._assert_stored_once(is_sound, _overlapping_boxes, self.CHECKER)
        self._assert_stored_once(is_sound, lambda: Solid.make_box(10, 10, 10), self.CHECKER)

    def test_shape_is_valid_is_build123d_own(self):
        from build123d.topology import Shape
        self.assertFalse(getattr(Shape.__dict__["is_valid"], "__op_memo__", False))

    def test_placement_and_orientation_are_part_of_the_verdict_key(self):
        import importlib
        counter = _Counting(importlib.import_module("OCP.BRepAlgoAPI").BRepAlgoAPI_Check)
        box = Solid.make_box(10, 10, 10)
        with mock.patch(self.CHECKER, counter):
            is_sound(box)
            is_sound(Pos(1, 0, 0) * box)
            is_sound(Rot(0, 0, 90) * box)
            is_sound(Solid(TopoDS.Solid_s(box.wrapped.Reversed())))
        self.assertEqual(counter.calls, 4)

    def test_failed_and_inconclusive_checks_are_not_stored(self):
        from OCP.BOPAlgo import BOPAlgo_CheckStatus
        box = Solid.make_box(10, 10, 10)
        checker = mock.Mock()
        checker.HasErrors.return_value = True
        with mock.patch(self.CHECKER, return_value=checker):
            with self.assertRaisesRegex(GeometryError, "checker failed"):
                is_sound(box)
        checker.HasErrors.return_value = False
        unknown = mock.Mock()
        unknown.GetCheckStatus.return_value = BOPAlgo_CheckStatus.BOPAlgo_CheckUnknown
        checker.Result.return_value = _Results([unknown])
        with mock.patch(self.CHECKER, return_value=checker):
            with self.assertRaisesRegex(GeometryError, "inconclusive"):
                is_sound(box)
        analyzer = mock.Mock()
        analyzer.IsValid.side_effect = RuntimeError("kernel")
        with mock.patch(self.ANALYZER, return_value=analyzer):
            with self.assertRaisesRegex(GeometryError, "kernel"):
                is_valid(box)
        # Nothing was stored: the real kernel answers now.
        import importlib
        counter = _Counting(importlib.import_module("OCP.BRepAlgoAPI").BRepAlgoAPI_Check)
        with mock.patch(self.CHECKER, counter):
            self.assertTrue(is_sound(box))
        self.assertEqual(counter.calls, 1)
        counter = _Counting(importlib.import_module("OCP.BRepCheck").BRepCheck_Analyzer)
        with mock.patch(self.ANALYZER, counter):
            self.assertTrue(is_valid(box))
        self.assertEqual(counter.calls, 1)

    def test_disabled_memo_runs_every_check(self):
        import importlib
        analyzer = _Counting(importlib.import_module("OCP.BRepCheck").BRepCheck_Analyzer)
        checker = _Counting(importlib.import_module("OCP.BRepAlgoAPI").BRepAlgoAPI_Check)
        digests = _Counting(op_memo._tshape_digest)
        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0"}), \
                mock.patch(self.ANALYZER, analyzer), \
                mock.patch(self.CHECKER, checker), mock.patch("cadgen._internal.op_memo._tshape_digest", digests):
            for _ in range(2):
                box = Solid.make_box(10, 10, 10)
                self.assertTrue(is_valid(box))
                self.assertTrue(is_sound(box))
        self.assertEqual((analyzer.calls, checker.calls, digests.calls), (2, 2, 0))


class VerdictScopeTests(_FreshStore):
    """Where ``is_valid``/``is_sound`` answer without a key. A null or empty
    shape gets build123d's own answer, never ``ValueError``: model code gates
    empty intermediates. A shape without faces or with few edges is checked
    directly: its key's BREP digest plus the store write cost more than the
    check (a sweep of every face and edge of a 406-face plate went from 0.36 s
    to 0.90 s cold and wrote 1,618 index entries)."""

    def _index_entries(self):
        from pathlib import Path
        entries = Path(os.environ["CADGEN_CACHE_DIR"]) / "index" / "op"
        return sorted(p.name for p in entries.glob("*")) if entries.is_dir() else []

    def test_null_and_empty_shapes_answer_like_build123d(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Shell, TopoDS_Solid, TopoDS_Wire

        def empty(topods, make):
            make(topods)
            return topods

        builder = BRep_Builder()
        shapes = (Solid(), Compound([]), Solid(empty(TopoDS_Solid(), builder.MakeSolid)),
                  Shell(empty(TopoDS_Shell(), builder.MakeShell)), Wire(empty(TopoDS_Wire(), builder.MakeWire)))
        null = Solid()
        null.wrapped = TopoDS_Solid()  # a null native shape, where build123d's property asserts
        digests = _Counting(op_memo._tshape_digest)
        with mock.patch("cadgen._internal.op_memo._tshape_digest", digests):
            self.assertEqual([is_valid(shape) for shape in shapes], [True, True, True, False, False])
            self.assertEqual([is_valid(shape) for shape in shapes], [shape.is_valid for shape in shapes])
            self.assertIs(is_valid(null), True)
            # The boolean kernel rejects an empty argument (BOPAlgo_BadType): a verdict, not an error.
            self.assertEqual([is_sound(shape) for shape in (*shapes, null)], [False] * 6)
        self.assertEqual(digests.calls, 0)
        self.assertEqual(self._index_entries(), [])

    def test_small_shapes_are_checked_without_a_key(self):
        box = Solid.make_box(10, 10, 10)
        checks = (is_valid, is_sound, topology_errors, self_intersections)
        digests = _Counting(op_memo._tshape_digest)
        with mock.patch("cadgen._internal.op_memo._tshape_digest", digests):
            for shape in (box.vertices()[0], box.edges()[0], box.wires()[0], box.faces()[0]):
                for check in checks:
                    uncached = self._uncached(check, shape)
                    self.assertEqual(check(shape), uncached)
            self.assertEqual((digests.calls, self._index_entries()), (0, []))
            for check in checks:  # a solid is worth its key
                check(box)
        self.assertEqual(digests.calls, len(checks))
        self.assertEqual(len(self._index_entries()), len(checks))

    def _uncached(self, check, shape):
        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0"}):
            return check(shape)


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

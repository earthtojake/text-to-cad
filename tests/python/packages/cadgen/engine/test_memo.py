"""The kernel memo as the engine holds it: a hit is the first run's objects, booleans
leave their inputs alone and write their own p-curves, a hit's restore costs what
changed, a container registers at its children's cost, a maker a model runs is a call."""

from __future__ import annotations

import io
import os
import unittest
from unittest import mock

from cadgen.engine.kernel import memo


def _delta(before: dict, after: dict) -> dict:
    return {key: after[key] - before.get(key, 0) for key in after if key in ("hits", "misses", "unkeyable",
                                                                             "unreplayable", "errors")}


def _run(function, *args, program=None, model=None):
    before = memo.stats()
    with memo.run(None, program=program, model=model) as run:
        result = function(*args)
    return result, _delta(before, memo.stats()), run


def _bytes(shape) -> bytes:
    from OCP.BinTools import BinTools

    stream = io.BytesIO()
    BinTools.Write_s(shape, stream)
    return stream.getvalue()


def _counted(cls, name):
    """Count the runs of an OCCT class's own method ``name`` (the class the memo's subclass
    wraps): what an answered query never calls."""
    original = getattr(cls, name)
    calls = []

    def counting(self, *args):
        calls.append(1)
        return original(self, *args)

    return mock.patch.object(cls, name, counting), calls


class MemoCase(unittest.TestCase):
    def setUp(self) -> None:
        memo.install()
        memo.clear()
        self.addCleanup(memo.clear)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CADGEN_ENGINE_MEMO", None)


class HitTest(MemoCase):
    @staticmethod
    def _model(radius=1.0):
        from build123d import Solid, fillet

        box = Solid.make_box(4, 4, 4)
        hole = Solid.make_cylinder(radius, 10)
        cut = box - hole
        return box, cut, fillet(cut.edges().filter_by(lambda e: e.length > 3.9), 0.4)

    def test_a_hit_is_the_first_run_s_objects(self) -> None:
        (box, cut, rounded), cold, run = _run(self._model)
        self.assertEqual((cold["hits"], cold["unkeyable"], cold["errors"]), (0, 0, 0))
        (box2, cut2, rounded2), hot, _ = _run(self._model)
        self.assertEqual(hot["misses"], 0)
        self.assertIs(box2, box)
        self.assertIs(cut2, cut)
        # build123d's fillet() wraps what the hit hands back: the same geometry.
        self.assertTrue(rounded2.wrapped.TShape() == rounded.wrapped.TShape())
        self.assertEqual(run.tally["misses"], cold["misses"])

    def test_every_miss_makes_its_downstream_miss(self) -> None:
        (_box, cut, rounded), _, _ = _run(self._model)
        (box2, cut2, rounded2), hot, _ = _run(self._model, 1.2)
        self.assertIsNot(cut2, cut)
        self.assertIsNot(rounded2, rounded)
        self.assertGreaterEqual(hot["misses"], 3)

    def test_with_hits_off_every_call_runs(self) -> None:
        (box, _cut, _rounded), _, _ = _run(self._model)
        os.environ["CADGEN_ENGINE_MEMO"] = "0"
        (box2, _cut2, _rounded2), hot, _ = _run(self._model)
        self.assertEqual(hot["hits"], 0)
        self.assertIsNot(box2, box)


class BooleanTest(MemoCase):
    def test_a_boolean_leaves_its_inputs_and_writes_its_own_pcurves(self) -> None:
        from build123d import Location, Polygon, Rectangle, extrude
        from OCP.BRep import BRep_Tool
        from OCP.Geom import Geom_Plane
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS
        from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher, IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

        from cadgen.engine.kernel.history import listed

        def edges(shape):
            found = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
            TopExp.MapShapes_s(shape.wrapped, TopAbs_EDGE, found)
            return [found.FindKey(ordinal) for ordinal in range(1, found.Extent() + 1)]

        def model():
            # Extrusions: their sides are planes with no p-curve stored.
            plate = extrude(Rectangle(20, 20), 4)
            rib = extrude(Polygon((0, 0), (6, 0), (6, 3), (0, 6), align=None), 6).moved(Location((0, 0, 4)))
            given = {edge.TShape(): edge.TShape().Curves().Extent() for shape in (plate, rib) for edge in edges(shape)}
            return given, plate.fuse(rib)

        (given, result), _, _ = _run(model)
        self.assertEqual({tshape: tshape.Curves().Extent() for tshape in given}, given,
                         "the boolean writes into no edge it was given")
        made = [edge for edge in edges(result) if edge.TShape() not in given]
        self.assertTrue(made)
        ancestors = IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapesAndAncestors_s(result.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
        for edge in made:
            faces = {face.TShape(): face for face in listed(ancestors.FindFromKey(edge))}
            planes = sum(isinstance(BRep_Tool.Surface_s(TopoDS.Face(face)), Geom_Plane) for face in faces.values())
            self.assertGreater(planes, 0)
            self.assertGreaterEqual(edge.TShape().Curves().Extent(), 1 + planes, "its curve on each plane it bounds")


class RestoreCostTest(MemoCase):
    """A hit's restore costs the rows later operations left on its result, never the
    result's size: a moved copy of a nested compound is handed back without a walk."""

    @staticmethod
    def _nested(extruding=False):
        from build123d import Compound, Pos, Solid, Vector

        inner = Compound(children=[Solid.make_box(1, 2, 3), Pos(5, 0, 0) * Solid.make_cylinder(1, 2)])
        outer = Compound(children=[inner, Pos(0, 5, 0) * Solid.make_sphere(1)])
        placed = outer.moved(Pos(10, 0, 0))
        if extruding:
            Solid.extrude(placed.children[0].children[0].faces()[0], Vector(0, 0, -1))
        return Compound(children=[placed]), placed

    @staticmethod
    def _nodes(shape):
        pending, found = [shape], []
        while pending:
            node = pending.pop()
            found.append(node)
            pending.extend(node.children)
        return found

    def test_a_hit_reads_its_rows_not_its_sub_shapes(self) -> None:
        (assembly, placed), cold, _ = _run(self._nested)
        self.assertEqual((cold["hits"], cold["unkeyable"], cold["errors"]), (0, 0, 0))
        copies = {node.wrapped.TShape() for node in self._nodes(placed)[1:]}
        self.assertEqual(len(copies), 4)
        walked: list = []
        mapped = memo._mapped

        def walking(handle):
            walked.append(handle.TShape())
            return mapped(handle)

        with mock.patch.object(memo, "_mapped", side_effect=walking):
            (assembly2, placed2), hot, _ = _run(self._nested)
        self.assertEqual((hot["misses"], hot["errors"]), (0, 0))
        self.assertIs(placed2, placed)
        self.assertFalse(copies & set(walked), "no node of the moved copy is walked on a hit")
        self.assertEqual(_bytes(assembly2.wrapped), _bytes(assembly.wrapped))

    def test_a_hit_still_undoes_what_a_later_operation_did_below_a_moved_copy(self) -> None:
        (_assembly, placed), _, _ = _run(self._nested)
        leaf = placed.children[0].children[0]
        fresh = _bytes(leaf.wrapped)
        (_assembly, placed2), extruded, _ = _run(self._nested, True)
        self.assertIs(placed2, placed)
        self.assertEqual(extruded["misses"], 1, "the extrusion alone")
        self.assertNotEqual(_bytes(leaf.wrapped), fresh)
        (_assembly, placed3), again, _ = _run(self._nested)
        self.assertIs(placed3, placed)
        self.assertEqual(again["misses"], 0)
        self.assertEqual(_bytes(leaf.wrapped), fresh, "with the extrusion edited out, the copy is as moved")


class RegistrationCostTest(MemoCase):
    def test_a_container_of_registered_parts_registers_its_children_alone(self) -> None:
        from build123d import Compound, Pos, Solid

        walked: list = []
        mapped = memo._mapped

        def walking(handle):
            found = mapped(handle)
            walked.extend(found[1])
            return found

        def model():
            parts = [Solid.make_box(1, 2, 3), Pos(5, 0, 0) * Solid.make_cylinder(1, 2),
                     Pos(0, 5, 0) * Solid.make_sphere(1)]
            inner = Compound(children=parts[:2])
            walked.clear()
            with mock.patch.object(memo, "_mapped", side_effect=walking):
                assembly = Compound(children=[inner, parts[2]])
            return parts, inner, assembly, list(walked)

        (parts, inner, assembly, walked), cold, _ = _run(model)
        self.assertEqual((cold["unkeyable"], cold["errors"]), (0, 0))
        below = {sub for part in parts for sub in mapped(part.wrapped)[1]} - {p.wrapped.TShape() for p in parts}
        self.assertTrue(below)
        self.assertFalse(below & set(walked), "the parts' sub-shapes are mapped already: not walked again")
        self.assertTrue(all(memo._SUBS.get(sub) is memo._REGISTRY[part.wrapped.TShape()]
                            for part in parts for sub in mapped(part.wrapped)[1]))
        self.assertIs(memo._SUBS.get(assembly.wrapped.TShape()), memo._REGISTRY[assembly.wrapped.TShape()])


class CastTest(MemoCase):
    def test_a_shape_cast_out_of_a_compound_is_keyed_by_the_root_holding_it(self) -> None:
        # Intersecting a compound casts its solids afresh, with no ancestor to name them
        # by; so does bd.scale, which hands back its result out of a compound.
        import build123d as bd

        def model():
            # Algebra parts are compounds: the solid inside one is no operation's result.
            shell = bd.Sphere(5) - bd.Pos(0, 0, -4) * bd.Box(20, 20, 4)
            grown = bd.scale(shell, by=1.05)
            tool = bd.Pos(4, 0, 0) * bd.Box(4, 2, 2)
            cast = list(shell)[0]
            # A face whose topo_parent does not hold it: named by the root holding its TShape.
            stray = (bd.Box(3, 3, 3) - bd.Cylinder(1, 8)).faces().sort_by(bd.Axis.Z)[-1]
            stray.topo_parent = tool
            return (grown & tool) - shell, cast & tool, bd.Solid.extrude(stray, bd.Vector(0, 0, 1))

        (visor, rounded, _stray), cold, _ = _run(model)
        self.assertEqual((cold["unkeyable"], cold["errors"]), (0, 0))
        (visor2, rounded2, _stray2), hot, run = _run(model)
        self.assertEqual((hot["misses"], hot["unkeyable"]), (0, 0))
        self.assertEqual(run.tally["uncached"], 0)
        # build123d wraps what the hits hand back: the same geometry.
        self.assertTrue(visor2.wrapped.TShape() == visor.wrapped.TShape())
        self.assertTrue(rounded2.wrapped.TShape() == rounded.wrapped.TShape())

    def test_a_text_fused_with_another_sketch_is_keyed(self) -> None:
        # The fuse hands its first face -- one of the text's compound -- the sketch's own
        # attributes, topo_parent None among them: the root holding the face names it.
        import build123d as bd

        def model():
            return bd.extrude(bd.Text("A", 5) + bd.Pos(10, 0, 0) * bd.Rectangle(1, 2), amount=1)

        first, cold, run = _run(model)
        self.assertEqual((cold["unkeyable"], run.tally["uncached"]), (0, 0))
        again, hot, run = _run(model)
        self.assertEqual((hot["misses"], hot["unkeyable"], run.tally["uncached"]), (0, 0, 0))
        self.assertTrue(again.wrapped.TShape() == first.wrapped.TShape())


class RetentionTest(MemoCase):
    @staticmethod
    def _model(radius):
        from build123d import Solid

        return Solid.make_box(4, 4, 4) - Solid.make_cylinder(radius, 10)

    def test_the_memo_keeps_what_the_last_runs_used_however_many_calls_they_made(self) -> None:
        _run(self._model, 1.0)
        for radius in [1.0 + i / 10 for i in range(1, memo.RUNS_KEPT)]:
            _run(self._model, radius)
        _, revert, _ = _run(self._model, 1.0)
        self.assertEqual(revert["misses"], 0, "used within the last runs: kept")
        for radius in [2.0 + i / 10 for i in range(memo.RUNS_KEPT + 1)]:
            _run(self._model, radius)
        _, gone, _ = _run(self._model, 1.0)
        self.assertEqual(gone["misses"], 2, "unused for longer: forgotten (the cylinder and the cut)")
        # What is held is what those runs made: the box, and a cylinder and a cut per radius.
        self.assertLessEqual(memo.stats()["entries"], 2 * memo.RUNS_KEPT + 1 + memo.RUNS_KEPT)

    def test_a_programs_pass_over_more_models_than_the_runs_kept_is_one_run(self) -> None:
        # A script building a robot and its links: each model's next run finds what this one used.
        radii = [1.0 + i / 10 for i in range(memo.RUNS_KEPT + 2)]
        for i, radius in enumerate(radii):
            _run(self._model, radius, program="first", model=f"link_{i}")
        for i, radius in enumerate(radii):
            _, again, _ = _run(self._model, radius, program="second", model=f"link_{i}")
            self.assertEqual(again["misses"], 0, f"link_{i}: kept across the program's pass")

    def test_a_program_building_one_model_again_begins_another_pass(self) -> None:
        # An edit loop in one process: each build of the model is a run of its own.
        _run(self._model, 1.0, program="loop", model="part")
        for radius in [2.0 + i / 10 for i in range(memo.RUNS_KEPT + 1)]:
            _run(self._model, radius, program="loop", model="part")
        _, gone, _ = _run(self._model, 1.0, program="loop", model="part")
        self.assertEqual(gone["misses"], 2, "unused for longer than the runs kept: forgotten")


class QueryTest(MemoCase):
    def test_a_bounding_box_of_a_shape_the_memo_handed_back_is_not_measured_again(self) -> None:
        from build123d import Pos, Solid, geometry

        def model(length):
            part = Pos(1, 2, 3) * (Solid.make_box(length, 4, 4) - Solid.make_cylinder(1, 10))
            box = part.bounding_box()
            return tuple(box.min) + tuple(box.max)

        cold, _, _ = _run(model, 4.0)
        measured = mock.patch.object(geometry.BRepBndLib, "AddOptimal_s", wraps=geometry.BRepBndLib.AddOptimal_s)
        with measured as add:
            warm, _, _ = _run(model, 4.0)
            self.assertEqual(add.call_count, 0, "the same shape: its box is kept")
            self.assertEqual(warm, cold)
            edited, _, _ = _run(model, 5.0)
            self.assertEqual(add.call_count, 1, "a new shape is measured")
        self.assertAlmostEqual(edited[3] - edited[0], 5.0, places=5)

    @staticmethod
    def _part(radius):
        from build123d import Solid

        return Solid.make_box(10, 10, 10) - Solid.make_cylinder(radius, 20)

    def test_a_bop_check_of_a_shape_the_memo_handed_back_is_not_run_again(self) -> None:
        from OCP import BRepAlgoAPI

        own = BRepAlgoAPI.BRepAlgoAPI_Check.__kernel_memo_class__

        def model(radius, fuzzy=None):
            part = self._part(radius)
            check = BRepAlgoAPI.BRepAlgoAPI_Check()
            if fuzzy is not None:
                check.SetFuzzyValue(fuzzy)
            check.SetData(part.wrapped)
            check.Perform()
            return BRepAlgoAPI.BRepAlgoAPI_Check(part.wrapped).IsValid(), check.IsValid(), part

        counted, runs = _counted(own, "Perform")
        with counted:
            (cold, _, part), _, cold_run = _run(model, 3.0)
            self.assertEqual((len(runs), cold_run.tally["queries_answered"]), (1, 1), "one key, asked twice")
            (warm, warm_set, again), _, warm_run = _run(model, 3.0)
            self.assertIs(again, part)
            self.assertEqual((len(runs), warm_run.tally["queries_answered"]), (1, 2), "the same shape: answered")
            _run(model, 3.0, 1e-3)
            self.assertEqual(len(runs), 2, "another fuzzy value is another key")
            _run(model, 3.0, 1e-3)
            self.assertEqual(len(runs), 2)
            _run(model, 3.5)
            self.assertEqual(len(runs), 3, "a new shape is checked")
        self.assertEqual((warm, warm_set), (cold, cold))
        self.assertEqual(warm, own(part.wrapped).IsValid(), "the kept verdict is a fresh check's")

    def test_a_check_of_a_shape_made_past_the_memo_runs_every_time(self) -> None:
        from OCP import BRepAlgoAPI

        own = BRepAlgoAPI.BRepAlgoAPI_Check.__kernel_memo_class__
        part = self._part(3.0)  # outside a run: no operation of the memo made it
        counted, runs = _counted(own, "Perform")
        with counted:
            for _ in range(2):
                verdict, _, run = _run(lambda: BRepAlgoAPI.BRepAlgoAPI_Check(part.wrapped).IsValid())
                self.assertEqual(run.tally["queries_answered"], 0)
        self.assertEqual(len(runs), 2)
        self.assertTrue(verdict)

    def test_an_answered_check_asked_for_more_runs_as_it_was_given(self) -> None:
        from OCP import BRepAlgoAPI

        own = BRepAlgoAPI.BRepAlgoAPI_Check.__kernel_memo_class__

        def model():
            part = self._part(3.0)
            check = BRepAlgoAPI.BRepAlgoAPI_Check(part.wrapped)
            check.SetFuzzyValue(0.5)  # after its run: not what it ran with
            return check.IsValid(), check.Result().Size(), check.FuzzyValue()

        counted, runs = _counted(own, "Perform")
        with counted:
            cold, _, _ = _run(model)
            warm, _, _ = _run(model)
        self.assertEqual(warm, cold)
        self.assertEqual(len(runs), 2, "Result() runs the check the memo answered")

    def test_validity_is_answered_by_geometry_whatever_the_shape_is_labelled(self) -> None:
        from build123d.topology import shape_core

        def model(label):
            part = self._part(3.0)
            part.label = label
            return part.is_valid, part.is_manifold, part

        counted, runs = _counted(shape_core.BRepCheck_Analyzer, "IsValid")
        with counted:
            (valid, manifold, part), _, cold = _run(model, "a")
            self.assertEqual((len(runs), cold.tally["queries_run"]), (1, 2))
            (again, again_manifold, _), _, warm = _run(model, "b")
            self.assertEqual((len(runs), warm.tally["queries_answered"]), (1, 2), "a label is no input of a query")
        self.assertEqual((again, again_manifold), (valid, manifold))
        part.label = "c"
        self.assertEqual((valid, manifold), (part.is_valid, part.is_manifold), "outside a run: a fresh answer")

    def test_an_analyzer_s_run_is_keyed_by_its_settings(self) -> None:
        from OCP import BRepCheck

        own = BRepCheck.BRepCheck_Analyzer.__kernel_memo_class__

        def model(exact):
            part = self._part(3.0)
            return BRepCheck.BRepCheck_Analyzer(part.wrapped, True, False, exact).IsValid(), part

        counted, runs = _counted(own, "Init")
        with counted:
            (cold, part), _, _ = _run(model, False)
            (warm, _), _, run = _run(model, False)
            self.assertEqual((len(runs), run.tally["queries_answered"]), (1, 1))
            _run(model, True)
            self.assertEqual(len(runs), 2, "the exact method is another key")
        self.assertEqual(warm, cold)
        self.assertEqual(warm, own(part.wrapped).IsValid())
        loose = self._part(3.0)
        with counted:
            for _ in range(2):
                _run(lambda: BRepCheck.BRepCheck_Analyzer(loose.wrapped).IsValid())
        self.assertEqual(len(runs), 4, "a shape made past the memo is analysed every time")

    def test_the_volume_of_an_interference_is_answered_once_its_common_is_a_hit(self) -> None:
        from build123d import Pos, Solid
        from build123d.topology import Shape
        from OCP.TopAbs import TopAbs_SOLID

        def model(gap):
            a = Solid.make_box(10, 10, 10)
            b = Pos(10 - gap, 2, 2) * Solid.make_box(5, 5, 5)
            common = a & b
            return [solid.volume for solid in common.solids()], common

        measured = Shape.shape_properties_LUT[TopAbs_SOLID]
        runs = []
        counted = mock.patch.dict(Shape.shape_properties_LUT,
                                  {TopAbs_SOLID: lambda *args: (runs.append(1), measured(*args))[1]})
        with counted:
            (cold, common), _, _ = _run(model, 1.0)
            (warm, again), hot, run = _run(model, 1.0)
            self.assertIs(again, common)
            self.assertEqual((len(runs), hot["misses"], run.tally["queries_answered"]), (1, 0, 1))
            edited, _, _ = _run(model, 2.0)
            self.assertEqual(len(runs), 2, "another common is measured")
        self.assertEqual(warm, cold)
        self.assertEqual(warm, [solid.volume for solid in common.solids()], "a fresh volume of the same solid")
        self.assertAlmostEqual(edited[0][0], 2 * 5 * 5, places=6)

    def test_mass_properties_are_answered_as_new_values_keyed_by_their_arguments(self) -> None:
        from build123d import CenterOf

        def model(center_of):
            part = self._part(3.0)
            return part.center(center_of), part.area, part.edges()[0].length, part.matrix_of_inertia, part

        (centre, area, length, inertia, part), _, cold = _run(model, CenterOf.MASS)
        self.assertEqual(cold.tally["queries_run"], 4)
        centre.X = 1e9  # the model's own Vector: what was kept is not it
        inertia[0][0] = -1.0
        (again, area2, length2, inertia2, _), _, warm = _run(model, CenterOf.MASS)
        self.assertEqual((warm.tally["queries_run"], warm.tally["queries_answered"]), (0, 4))
        self.assertIsNot(again, centre)
        fresh = part.center(CenterOf.MASS)  # outside a run: computed
        self.assertEqual(tuple(again), tuple(fresh))
        self.assertEqual((area2, length2, inertia2), (part.area, part.edges()[0].length, part.matrix_of_inertia))
        (boxed, *_), _, other = _run(model, CenterOf.BOUNDING_BOX)
        self.assertEqual(other.tally["queries_answered"], 3, "another argument is another key")
        self.assertEqual(tuple(boxed), tuple(part.center(CenterOf.BOUNDING_BOX)))

    def test_a_volume_of_a_shape_made_past_the_memo_is_measured_every_time(self) -> None:
        part = self._part(3.0)
        for _ in range(2):
            volume, _, run = _run(lambda: part.volume)
            self.assertEqual((run.tally["queries_run"], run.tally["queries_answered"]), (1, 0))
        self.assertEqual(volume, part.volume)

    def test_a_clearance_of_shapes_the_memo_handed_back_is_answered(self) -> None:
        from build123d import Pos, Solid
        from OCP import BRepExtrema

        own = BRepExtrema.BRepExtrema_DistShapeShape.__kernel_memo_class__

        def model(gap, deflection=None):
            a = Solid.make_box(10, 10, 10)
            b = Pos(10 + gap, 0, 0) * Solid.make_sphere(3)
            found = BRepExtrema.BRepExtrema_DistShapeShape(a.wrapped, b.wrapped) if deflection is None else (
                BRepExtrema.BRepExtrema_DistShapeShape(a.wrapped, b.wrapped, deflection))
            found.Perform()
            return a.distance_to(b), a.distance_to((20 + gap, 5, 5)), found.Value() if found.IsDone() else None, a, b

        counted, runs = _counted(own, "Perform")
        with counted:
            (to_b, to_point, direct, a, b), _, cold = _run(model, 5.0)
            self.assertEqual((len(runs), cold.tally["queries_answered"]), (3, 1), "a second Perform is answered")
            (*warm, _a, _b), _, run = _run(model, 5.0)
            self.assertEqual((len(runs), run.tally["queries_answered"]), (3, 4))
            _run(model, 5.0, 1e-3)
            self.assertEqual(len(runs), 4, "another deflection is another key")
            _run(model, 6.0)
            self.assertEqual(len(runs), 7, "another shape is measured")
        self.assertEqual(warm, [to_b, to_point, direct])
        self.assertEqual((to_b, to_point), (a.distance_to(b), a.distance_to((25.0, 5, 5))))
        self.assertEqual(direct, own(a.wrapped, b.wrapped).Value())
        self.assertAlmostEqual(direct, 2.0, places=6)

    def test_an_answered_distance_asked_for_its_points_runs_as_it_was_given(self) -> None:
        from build123d import Pos, Solid
        from OCP import BRepExtrema

        own = BRepExtrema.BRepExtrema_DistShapeShape.__kernel_memo_class__

        def model():
            a, b = Solid.make_box(10, 10, 10), Pos(15, 2, 3) * Solid.make_sphere(3)
            found = BRepExtrema.BRepExtrema_DistShapeShape()
            found.LoadS1(a.wrapped)
            found.LoadS2(b.wrapped)
            done = found.Perform()
            point = found.PointOnShape1(1)
            return done, found.Value(), (point.X(), point.Y(), point.Z())

        counted, runs = _counted(own, "Perform")
        with counted:
            cold, _, _ = _run(model)
            warm, _, _ = _run(model)
        self.assertEqual(warm, cold)
        self.assertEqual(len(runs), 2, "a point is no answer the memo keeps: asking one runs it")
        loose_a, loose_b = Solid.make_box(1, 1, 1), Pos(3, 0, 0) * Solid.make_box(1, 1, 1)
        with counted:
            for _ in range(2):
                _run(lambda: loose_a.distance_to(loose_b))
        self.assertEqual(len(runs), 4, "a distance of shapes made past the memo is measured every time")

    def test_a_point_test_is_answered_per_point_and_tolerance(self) -> None:
        from build123d.topology import three_d

        def model(points, tolerance=1e-6):
            part = self._part(3.0)
            return [part.is_inside(point, tolerance) for point in points], part

        points = [(4, 4, 0), (0, 0, 0), (4, 4, 5), (20, 0, 0)]
        counted, runs = _counted(three_d.BRepClass3d_SolidClassifier, "Perform")
        with counted:
            (cold, part), _, _ = _run(model, points)
            (warm, _), _, run = _run(model, points)
            self.assertEqual((len(runs), run.tally["queries_answered"]), (4, 4))
            _run(model, points[:1], 0.1)
            self.assertEqual(len(runs), 5, "another tolerance is another key")
            _run(model, [(4, 4, 1)])
            self.assertEqual(len(runs), 6, "another point is another key")
        self.assertEqual(warm, cold)
        self.assertEqual(cold, [True, False, True, False])
        self.assertEqual(warm, [part.is_inside(point) for point in points], "a fresh test of the same solid")


class VertexTest(MemoCase):
    def test_a_point_placed_by_a_model_is_keyed(self) -> None:
        import build123d as bd

        def model():
            return tuple(bd.Vertex(1, 2, 3).moved(bd.Location((5, 0, 0), (0, 0, 1), 30)).center())

        cold, _, _ = _run(model)
        warm, hot, run = _run(model)
        self.assertEqual(run.tally["uncached"], 0, "the vertex is made by a keyed construction")
        self.assertEqual(hot["misses"], 0)
        self.assertEqual(warm, cold)


class ConfigurationTest(MemoCase):
    def test_an_operation_on_a_configured_assembly_is_keyed_by_its_configurations(self) -> None:
        import build123d as bd

        from cadgen.engine import mechanism

        self.assertEqual(memo.CONFIGURATIONS, mechanism.CONFIGURATIONS)

        def model(angle):
            assembly = bd.Compound(children=[bd.Solid.make_box(1, 2, 3)], label="arm")
            mechanism.mechanism_state(assembly, "open", hinge=angle)
            placed = assembly.moved(bd.Location((5, 0, 0)))
            return placed.__dict__.get(mechanism.CONFIGURATIONS)

        first, _, _ = _run(model, 10.0)
        self.assertEqual(first["open"]["hinge"], (10.0,))
        edited, delta, _ = _run(model, 20.0)
        self.assertEqual(edited["open"]["hinge"], (20.0,), "the placement carries the edited configuration")
        self.assertGreater(delta["misses"], 0)


class MakerTest(MemoCase):
    def test_a_maker_s_run_is_counted_as_the_model_s_call(self) -> None:
        from build123d import Solid
        from OCP.ShapeFix import ShapeFix_Shape

        def model(asking=False):
            box = Solid.make_box(1, 2, 3)
            fix = ShapeFix_Shape(box.wrapped)
            if asking:
                fix.FixSolidTool()
            fix.Perform()
            return Solid(fix.Shape())

        _, cold, cold_run = _run(model)
        self.assertEqual({k: cold_run.tally[k] for k in ("hits", "misses", "uncached")}, {"hits": 0, "misses": 2, "uncached": 0})
        _, hot, hot_run = _run(model)
        self.assertEqual({k: hot_run.tally[k] for k in ("hits", "misses", "uncached")}, {"hits": 2, "misses": 0, "uncached": 0})
        _, _, plain_run = _run(model, True)
        self.assertEqual({k: plain_run.tally[k] for k in ("hits", "misses", "uncached")}, {"hits": 1, "misses": 0, "uncached": 1})


class FileTest(MemoCase):
    def test_a_file_read_is_keyed_by_its_bytes_and_held(self) -> None:
        import tempfile
        from pathlib import Path

        import build123d as bd

        from cadgen.engine.model import read_step

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "box.step"
            bd.export_step(bd.Compound(children=[bd.Solid.make_box(1, 2, 3)]), str(path))
            first, cold, _ = _run(read_step, path)
            again, hot, _ = _run(read_step, path)
            self.assertIs(again, first, "parsed once and held")
            self.assertEqual(hot["misses"], 0)
            bd.export_step(bd.Compound(children=[bd.Solid.make_box(2, 2, 3)]), str(path))
            os.utime(path, ns=(1, 1))
            changed, edited, _ = _run(read_step, path)
            self.assertIsNot(changed, first)
            self.assertEqual(edited["misses"], 1)


if __name__ == "__main__":
    unittest.main()

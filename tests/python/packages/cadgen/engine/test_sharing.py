"""A placement shares its geometry: build123d's ``moved``, ``located`` and copies hand
back new objects on the same TShapes, a maker that changes its input in place is given a
copy of a placed shape, a file read again from one site shares the first decode, and the
document places one prototype as often as the geometry is placed -- split where the
paint on its faces differs -- with every placement's element names its prototype's."""

from __future__ import annotations

import copy
import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from cadgen.engine import build as engine_build
from cadgen.engine import document
from cadgen.engine.kernel import memo


def _nodes(shape):
    pending, found = [shape], []
    while pending:
        node = pending.pop()
        found.append(node)
        pending.extend(reversed(node.children))
    return found


class MemoCase(unittest.TestCase):
    def setUp(self) -> None:
        memo.install()
        memo.clear()
        self.addCleanup(memo.clear)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CADGEN_ENGINE_MEMO", None)


class PlacementTest(MemoCase):
    @staticmethod
    def _assembly():
        import build123d as bd

        box = bd.Box(1, 2, 3)
        box.label, box.color = "box", bd.Color(1, 0, 0)
        pin = bd.Pos(5, 0, 0) * bd.Cylinder(1, 2)
        pin.label = "pin"
        inner = bd.Compound(children=[box, pin], label="inner")
        ball = bd.Pos(0, 5, 0) * bd.Sphere(1)
        ball.label = "ball"
        return bd.Compound(children=[inner, ball], label="outer")

    def test_moved_located_and_copies_are_new_objects_on_the_same_tshapes(self) -> None:
        import build123d as bd

        def model():
            outer = self._assembly()
            return outer, [outer.moved(bd.Location((10, 0, 0))), outer.located(bd.Location((0, 10, 0))),
                           copy.copy(outer), copy.deepcopy(outer), outer.children[0].children[1].moved(bd.Pos(0, 0, 3))]

        with memo.run(None):
            outer, placements = model()
        sources = _nodes(outer)
        for placed in placements[:4]:
            nodes = _nodes(placed)
            self.assertEqual([type(node) for node in nodes], [type(node) for node in sources])
            self.assertEqual([node.label for node in nodes], [node.label for node in sources])
            for node, source in zip(nodes, sources):
                self.assertIsNot(node, source)
                self.assertTrue(node.wrapped.TShape() == source.wrapped.TShape(), node.label)
                self.assertEqual(node.wrapped.Orientation(), source.wrapped.Orientation())
            self.assertEqual(tuple(nodes[2].color), tuple(sources[2].color))
        moved, located = placements[:2]
        self.assertAlmostEqual(moved.center().X - outer.center().X, 10.0, places=6)
        self.assertAlmostEqual(located.location.position.Y, 10.0, places=6)
        # Children stay where they stand in their parent, as build123d keeps them.
        self.assertEqual(moved.children[1].location, outer.children[1].location)
        lone = placements[4]
        self.assertTrue(lone.wrapped.TShape() == outer.children[0].children[1].wrapped.TShape())
        self.assertAlmostEqual(lone.center().Z - outer.children[0].children[1].center().Z, 3.0, places=6)
        # What a placement holds of its own -- its label, its colour -- stays its own.
        moved.children[1].label = "moved ball"
        moved.children[1].color = bd.Color(0, 0, 1)
        self.assertEqual(outer.children[1].label, "ball")
        self.assertIsNone(outer.children[1]._color)


class CopyOnWriteTest(MemoCase):
    @staticmethod
    def _model():
        import build123d as bd
        from OCP.BRep import BRep_Builder
        from OCP.ShapeFix import ShapeFix_Shape
        from OCP.TopoDS import TopoDS

        box = bd.Solid.make_box(1, 1, 1)
        builder = BRep_Builder()
        for edge in box.edges():  # what ShapeFix_Shape fixes in the shape it is given, in place
            builder.SameParameter(TopoDS.Edge(edge.wrapped), False)
        first = box.moved(bd.Location((5, 0, 0)))
        second = box.moved(bd.Location((10, 0, 0)))
        fixer = ShapeFix_Shape(first.wrapped)
        fixer.Perform()
        return first, second, bd.Solid(fixer.Shape())

    @staticmethod
    def _flags(shape) -> set:
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS

        return {BRep_Tool.SameParameter_s(TopoDS.Edge(edge.wrapped)) for edge in shape.edges()}

    def test_a_maker_that_changes_its_input_in_place_is_given_a_copy_of_a_placed_shape(self) -> None:
        before = memo.stats()["copied_on_write"]
        with memo.run(None):
            first, second, fixed = self._model()
        self.assertEqual(memo.stats()["copied_on_write"] - before, 1)
        self.assertTrue(first.wrapped.TShape() == second.wrapped.TShape())
        self.assertEqual(self._flags(fixed), {True}, "the fix ran")
        self.assertEqual(self._flags(second), {False}, "and left the other placement as it was")

    def test_without_the_copy_the_fix_changes_every_placement(self) -> None:
        memo.clear()
        with mock.patch.object(memo, "_IN_PLACE", frozenset()), memo.run(None):
            _first, second, fixed = self._model()
        self.assertEqual(self._flags(fixed), {True})
        self.assertEqual(self._flags(second), {True}, "the hazard the copy guards against is real")


class OnePlaceTest(MemoCase):
    """OCCT's unify chains the edges it merges by their vertices' TShapes, whatever place each stands
    at, and a prism's two caps are one face's edges and vertices placed twice: a unify that fails on
    such a shape -- build123d's, after each boolean and in ``clean``, or a model's own -- is made
    again on a copy whose every sub-shape stands at one place, with its settings; one that succeeds
    is the kernel's, untouched."""

    @staticmethod
    def _ear():
        # A sheet-metal ear, as tom2's link profiles make one: an outline with rounded corners,
        # extruded to the gauge.
        import build123d as bd

        outline = [(0, 0), (30, 0), (30, 12), (22, 12), (22, 8), (8, 8), (8, 12), (0, 12)]
        face = bd.Face(bd.Wire.make_polygon([(x, 15, z) for x, z in outline], close=True))
        face = face.fillet_2d(1.0, [vertex for vertex in face.vertices() if abs(vertex.center().Z - 12) < 1e-6])
        return bd.Solid.extrude(face, (0, 2.032, 0))

    def test_a_unify_failing_on_a_shape_placed_twice_is_made_again_on_a_copy_with_its_settings(self) -> None:
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

        ear = self._ear()
        self.assertTrue(memo._placed_twice(ear.wrapped), "a prism's caps: one TShape at two places")
        original = getattr(ShapeUpgrade_UnifySameDomain, "__kernel_memo_class__", ShapeUpgrade_UnifySameDomain).__mro__[1]
        given = []

        tolerances = []

        class Chaining(original):  # the kernel's failure on such a shape, every time it meets one
            def Build(self, *args):  # noqa: N802
                given.append(self.Shape())
                if memo._placed_twice(self.Shape()):
                    raise RuntimeError("Courbes non jointives")
                return super().Build(*args)

            def SetLinearTolerance(self, value):  # noqa: N802
                tolerances.append(value)
                return super().SetLinearTolerance(value)

        unify = memo._one_place(Chaining)(ear.wrapped, True, True, True)
        unify.SetLinearTolerance(1e-5)
        before = memo.stats()["copied_apart"]
        unify.Build()
        self.assertEqual(memo.stats()["copied_apart"] - before, 1)
        self.assertEqual(len(given), 2, "made again once")
        self.assertFalse(memo._placed_twice(unify.Shape()))
        self.assertEqual(tolerances, [1e-5, 1e-5], "with the settings it was given")
        self.assertTrue(memo._placed_twice(ear.wrapped), "the shape it was given stays as it was")
        with self.assertRaisesRegex(RuntimeError, "Courbes"):  # one whose shape is at one place: as it failed
            failing = memo._one_place(type("Always", (original,), {"Build": lambda self: (_ for _ in ()).throw(
                RuntimeError("Courbes non jointives"))}))(unify.Shape(), True, True, True)
            failing.Build()

    def test_build123d_s_and_a_model_s_unify_run_on_the_kernel_s_shape_where_they_succeed(self) -> None:
        import build123d as bd
        from build123d.topology import shape_core
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

        self.assertTrue(getattr(shape_core.ShapeUpgrade_UnifySameDomain, "__kernel_one_place__", False))
        self.assertTrue(issubclass(ShapeUpgrade_UnifySameDomain, shape_core.ShapeUpgrade_UnifySameDomain.__mro__[1]))
        before = memo.stats()["copied_apart"]
        with memo.run(None):
            ear = self._ear()
            fused = ear.fuse(bd.Solid.make_box(20, 2.032, 6, bd.Plane(origin=(25, 15, -2)))).clean()
            unify = ShapeUpgrade_UnifySameDomain(ear.wrapped, True, True, True)
            unify.Build()
        self.assertEqual(memo.stats()["copied_apart"], before, "nothing failed: nothing copied")
        self.assertTrue(fused.is_valid)
        self.assertAlmostEqual(fused.volume, ear.volume + 20 * 2.032 * 6 - 5 * 2.032 * 4, places=6)
        self.assertTrue(memo._placed_twice(unify.Shape()), "the kernel's own result, its caps as it made them")


MODEL = """
from pathlib import Path

import build123d as bd
from cadgen.engine import paint, read_step, xbf
from bd_materials import FinishedMaterial
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties

BOUGHT = Path(__file__).parent / "bought.step"
PAIR = Path(__file__).parent / "pair.step"
RED = FinishedMaterial(RangeMaterial(name='Red', density=1000), pbr=PbrProperties.create('Red', color="#010000"))
BLUE = FinishedMaterial(RangeMaterial(name='Blue', density=1000), pbr=PbrProperties.create('Blue', color="#000001"))


def screw():
    return read_step(BOUGHT)


def bracket():
    plate = bd.Box(10, 6, 2) - bd.Cylinder(1, 5)
    plate.label = "plate"
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(2, 6)
    peg.label = "peg"
    return bd.Compound(children=[plate, peg], label="bracket")


@xbf("XBF/placed.xbf")
def placed():
    held = bracket()
    left = held.moved(bd.Location((0, 20, 0)))
    left.label = "left"
    right = held.moved(bd.Location((0, -20, 0)))
    right.label = "right"
    return bd.Compound(children=[held, left, right], label="placed")


@xbf("XBF/painted.xbf")
def painted():
    plate = bd.Box(10, 6, 2)
    plate.label = "plate"
    red = plate.moved(bd.Location((0, 20, 0)))
    red.label = "red"
    paint(red, red.faces().sort_by(bd.Axis.Z)[-1], RED)
    blue = plate.moved(bd.Location((0, 40, 0)))
    blue.label = "blue"
    paint(blue, blue.faces().sort_by(bd.Axis.Z)[-1], BLUE)
    again = plate.moved(bd.Location((0, 60, 0)))
    again.label = "again"
    paint(again, again.faces().sort_by(bd.Axis.Z)[-1], BLUE)
    return bd.Compound(children=[plate, red, blue, again], label="painted")


@xbf("XBF/labelled.xbf")
def labelled():
    held = bracket()
    left = held.moved(bd.Location((0, 20, 0)))
    left.label = "left"
    right = held.moved(bd.Location((0, -20, 0)))
    right.label = "right"
    stand = bd.Compound(children=[left, right], label="stand")  # each placement's label handed on
    grown = right.children[0] + bd.Pos(0, 0, 2) * bd.Box(2, 2, 2)
    grown.label = "grown"
    return bd.Compound(children=[held, stand, grown], label="labelled")


@xbf("XBF/kit.xbf")
def kit():
    bought = read_step(PAIR)
    first, second = bought.children
    first.label = "first"
    held = bd.Compound(children=[first], label="held")  # the label of one part of the read handed on
    grown = second + bd.Pos(0, 0, 4) * bd.Box(1, 1, 1)
    return bd.Compound(children=[held, grown], label="kit")


def peg():
    return bd.Cylinder(2, 6) - bd.Pos(0, 0, 3) * bd.Box(1, 1, 1)


@xbf("XBF/built.xbf")
def built():
    placed = []
    for x in (0, 10):
        part = peg()  # one construction made twice, named alike
        placed.append(part.moved(bd.Location((x, 0, 0))))
    other = peg()  # the same geometry, named apart
    return bd.Compound(children=[*placed, other.moved(bd.Location((20, 0, 0)))], label="built")


@xbf("XBF/screws.xbf")
def screws():
    placed = []
    for x in (0, 10):
        part = screw()  # one site, read twice
        placed.append(part.moved(bd.Location((x, 0, 0))))
    other = read_step(BOUGHT)  # another site: another feature, named apart
    return bd.Compound(children=[*placed, other.moved(bd.Location((20, 0, 0)))], label="screws")
"""


class DocumentTest(unittest.TestCase):
    def setUp(self) -> None:
        import build123d as bd

        self.folder = Path(tempfile.mkdtemp(prefix="engine-sharing-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))
        self.script = self.folder / "sharing.py"
        self.script.write_text(textwrap.dedent(MODEL), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))
        bd.export_step(bd.Compound(children=[bd.Solid.make_cylinder(1, 6)]), str(self.folder / "bought.step"))
        pair = [bd.Solid.make_box(2, 2, 2), bd.Pos(5, 0, 0) * bd.Solid.make_cylinder(1, 3)]
        bd.export_step(bd.Compound(children=pair), str(self.folder / "pair.step"))
        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        self.addCleanup(memo.clear)

    def build(self, *functions: str) -> dict[str, dict]:
        reports = engine_build.build(self.script, list(functions) or None, cwd=self.folder)
        found = {report["model"].rsplit("::", 1)[-1]: report for report in reports}
        self.assertTrue(all(report["ok"] for report in found.values()), found)
        return found

    def names(self, loaded) -> dict[str, tuple]:
        return {"/".join(instance.path): (loaded.prototypes[instance.prototype].face_names,
                                          loaded.prototypes[instance.prototype].edge_names,
                                          loaded.prototypes[instance.prototype].vertex_names)
                for instance in loaded.instances}

    def test_a_part_placed_three_times_is_one_prototype_and_its_names(self) -> None:
        self.build("placed")
        loaded = document.load(self.folder / "XBF/placed.xbf")
        self.assertEqual(len(loaded.prototypes), 2, "the plate and the peg, each placed three times")
        self.assertEqual([instance.prototype for instance in loaded.instances], [0, 1] * 3)
        names = self.names(loaded)
        self.assertEqual(names["placed/left/plate"], names["placed/bracket/plate"])
        self.assertEqual(names["placed/right/peg"], names["placed/bracket/peg"])
        faces = loaded.prototypes[0].face_names.values()
        self.assertTrue(faces and all(name.startswith("f:bracket.plate") for name in faces), faces)

    def test_a_cold_and_a_warm_document_are_the_same_bytes(self) -> None:
        self.build()
        cold = {name: (self.folder / f"XBF/{name}.xbf").read_bytes() for name in ("placed", "painted", "built", "screws")}
        for name in cold:
            (self.folder / f"XBF/{name}.xbf").unlink()
        self.build()
        warm = {name: (self.folder / f"XBF/{name}.xbf").read_bytes() for name in cold}
        self.assertEqual(warm, cold)
        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        for name in cold:
            (self.folder / f"XBF/{name}.xbf").unlink()
        self.build()
        self.assertEqual({name: (self.folder / f"XBF/{name}.xbf").read_bytes() for name in cold}, cold)

    def test_placements_painted_apart_are_prototypes_apart(self) -> None:
        self.build("painted")
        loaded = document.load(self.folder / "XBF/painted.xbf")
        prototypes = [loaded.prototypes[instance.prototype] for instance in loaded.instances]
        self.assertEqual([instance.prototype for instance in loaded.instances], [0, 1, 2, 2],
                         "bare, red and blue are three; the second blue is the first blue placed again")
        self.assertEqual(prototypes[0].face_materials, {})
        self.assertEqual({m.name for m in prototypes[1].face_materials.values()}, {"Red"})
        self.assertEqual({m.name for m in prototypes[2].face_materials.values()}, {"Blue"})
        self.assertEqual(len({p.key for p in prototypes}), 1, "one geometry")
        self.assertEqual(len({tuple(p.face_names.items()) for p in prototypes}), 1, "one geometry's names")
        import build123d as bd

        for prototype in prototypes[1:3]:
            # The paint sits on the face it was given, in each prototype's own topology.
            (ordinal,) = prototype.face_materials
            top = max(bd.Solid(prototype.shape).faces(), key=lambda face: face.center().Z)
            self.assertEqual(bd.Solid(prototype.shape).faces()[ordinal - 1].center().Z, top.center().Z)

    def test_two_labelled_placements_are_named_as_their_prototype_and_rename_nothing(self) -> None:
        self.build("labelled")
        loaded = document.load(self.folder / "XBF/labelled.xbf")
        names = self.names(loaded)
        for placed in ("labelled/stand/left/plate", "labelled/stand/right/plate"):
            self.assertEqual(names[placed], names["labelled/bracket/plate"], placed)
        self.assertEqual(names["labelled/stand/right/peg"], names["labelled/bracket/peg"])
        grown = loaded.prototypes[loaded.instances[-1].prototype]
        faces = list(grown.face_names.values())
        # The plate's own label names what is made of it; the placements' labels name nothing.
        self.assertTrue(any(name.startswith("f:plate.") for name in faces), faces)
        self.assertFalse([name for name in faces if "left" in name or "right" in name],
                         "a placement's label names the occurrence, never what is made of the shape it shares")

    def test_a_label_on_one_part_of_a_read_names_nothing_made_of_another(self) -> None:
        self.build("kit")
        loaded = document.load(self.folder / "XBF/kit.xbf")
        grown = loaded.prototypes[loaded.instances[-1].prototype]
        faces = list(grown.face_names.values())
        # The second part's own name in the file names what is made of it; the first's label, nothing of it.
        self.assertTrue(any(name.startswith("f:SOLID.") for name in faces), faces)
        self.assertFalse([name for name in faces if "first" in name], faces)

    def test_one_geometry_made_twice_and_named_alike_is_one_prototype(self) -> None:
        report = self.build("built")["built"]
        self.assertEqual(report["parts"], 2)
        loaded = document.load(self.folder / "XBF/built.xbf")
        self.assertEqual([instance.prototype for instance in loaded.instances], [0, 0, 1])
        first, other = loaded.prototypes
        self.assertEqual(first.key, other.key, "one geometry")
        self.assertNotEqual(first.face_names, other.face_names, "named apart, so prototypes apart")
        self.assertTrue(all(name.startswith("f:built.part") for name in first.face_names.values()), first.face_names)

    def test_a_file_read_again_from_one_site_shares_the_first_decode(self) -> None:
        before = memo.stats()["shared_reads"]
        report = self.build("screws")["screws"]
        self.assertEqual(memo.stats()["shared_reads"] - before, 1, report)
        loaded = document.load(self.folder / "XBF/screws.xbf")
        self.assertEqual([instance.prototype for instance in loaded.instances], [0, 0, 1],
                         "the helper's two reads are one part; the read of another site is its own")
        self.assertNotEqual(loaded.prototypes[0].face_names, loaded.prototypes[1].face_names)
        warm = self.build("screws")["screws"]
        self.assertEqual(warm["memo"]["misses"], 0)
        self.assertEqual([i.prototype for i in document.load(self.folder / "XBF/screws.xbf").instances], [0, 0, 1])


if __name__ == "__main__":
    unittest.main()

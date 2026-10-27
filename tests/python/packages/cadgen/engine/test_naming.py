"""Element names as FreeCAD's topological naming keeps them: a face keeps its name unless
the feature history that made it changed. A feature is named by the author's name for its
result (the variable or attribute it is assigned to), so an edit renames only what it
touches."""

from __future__ import annotations

import json
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
from cadgen.engine.kernel.trace import folded_atoms
from cadgen.engine.refs import ELEMENT_NAME

# The viewer's ref grammar's shared cases (read, never imported: the engine stands alone).
PARITY = Path(__file__).resolve().parents[5] / "packages/core/src/lib/cadRefs.parity.json"

BLOCK = """
import build123d as bd
from cadgen.engine import xbf


def peg(z):
    return bd.Pos(0, 0, z) * bd.Cylinder(1, 30)


@xbf("XBF/block.xbf")
def block():
    body = bd.Box(30, 20, 10)
{insert}    {relief} = body - bd.Pos(8, 0, 0) * bd.Cylinder(3, 30)
    final = {relief} - peg(0)
    final = final - bd.Pos(-12, 0, 0) * bd.Cylinder(1, 30)
    a, b = bd.Pos(0, 0, 5) * bd.Box(2, 2, 2), bd.Pos(9, 0, 5) * bd.Box(2, 2, 2)
    return final + a + b
"""


PAIR = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/pair.xbf")
def pair():
    fork = bd.Box(20, 10, 10)
    trial = bd.fillet(fork.edges().filter_by(bd.Axis.X), 1)  # an attempt the model throws away
{insert}    fork = fork - bd.Pos(0, 0, 5) * bd.Cylinder(3, 4)
{append}    fork.label = "fork"
    twin = fork.mirror(bd.Plane.YZ).moved(bd.Location((40, 0, 0)))
    twin.label = "twin"
    return bd.Compound(children=[fork, twin])
"""


# A reassignment chain, a helper returning what it makes unassigned among its steps.
CHAIN = """
import build123d as bd
from cadgen.engine import xbf


def _bore(radius, x):
    return bd.Pos(x, 0, 0) * bd.Cylinder(radius, 30)


@xbf("XBF/chain.xbf")
def chain():
    plate = bd.Box(40, 20, 10)
    plate = plate - _bore(2, -12)
{insert}    plate = plate - _bore({radius}, 12)
    plate = plate - bd.Pos(0, 6, 0) * bd.Box(4, 4, 30)
    return plate
"""


BAKED = """
import build123d as bd
from build123d.topology.shape_core import downcast
from cadgen.engine import xbf

OFFSET = {offset}


def bake(shape, kind):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_GTransform, BRepBuilderAPI_Transform
    from OCP.gp import gp_GTrsf
    from OCP.TopLoc import TopLoc_Location

    occt = shape.wrapped
    if kind == "copy":
        made = BRepBuilderAPI_Copy(occt)
    elif kind == "gtransform":
        made = BRepBuilderAPI_GTransform(occt.Located(TopLoc_Location()), gp_GTrsf(occt.Location().Transformation()),
                                         True)
    else:
        made = BRepBuilderAPI_Transform(occt.Located(TopLoc_Location()), occt.Location().Transformation(), True)
    return bd.Solid(downcast(made.Shape()))


@xbf("XBF/wheel.xbf")
def wheel():
    hub = bd.Cylinder(10, 5) - bd.Cylinder(3, 10)
    return bake(bd.Pos(30, 0, 0) * hub, "transform")


@xbf("XBF/baked.xbf")
def baked():
    hub = bd.Cylinder(10, 5) - bd.Cylinder(4, 10)
    copied = bake(hub, "copy")
    stretched = bake(bd.Pos(0, 30, 0) * hub, "gtransform")
    return bd.Compound(children=[wheel().shape.moved(bd.Location((0, 0, OFFSET))), copied.moved(bd.Location((60, 0, 0))),
                                 stretched])
"""


# The model that writes the STEP is a script of its own: a model reads no file its own build
# writes, a sibling's included.
SOURCE = """
import build123d as bd
from cadgen.engine import step, xbf


@xbf("XBF/source.xbf")
@step("source.step")
def source():
    plate = bd.Box(20, 10, 2) - bd.Cylinder(2, 10)
    plate.label = "plate"
    peg = bd.Pos(30, 0, 0) * bd.Cylinder(3, 8)
    peg.label = "peg"
    return bd.Compound(children=[plate, peg])
"""


IMPORTS = """
from pathlib import Path

import build123d as bd
from cadgen.engine import read_step, xbf

HERE = Path(__file__).parent


@xbf("XBF/imported.xbf")
def imported():
    bought = read_step(HERE / "{file}")
    return bd.Compound(children=[child.moved(bd.Location((0, 0, {lift}))) for child in bought.children])
"""


class NamingCase(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-naming-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

    def names(self, text: str, name: str = "block", part: int = 0, **fields: str) -> dict[str, list[str]]:
        """Build ``text`` (formatted with ``fields``) and read one part's names."""
        script = self.folder / f"{name}.py"
        script.write_text(textwrap.dedent(text.format(**fields)), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        reports = engine_build.build(script, [name], cwd=self.folder)
        self.assertTrue(all(report["ok"] for report in reports), reports)
        loaded = document.load(self.folder / f"XBF/{name}.xbf")
        for each in loaded.prototypes:
            # Every name the engine writes is a reference the viewer's grammar parses.
            for text in [*each.face_names.values(), *each.edge_names.values(), *each.vertex_names.values()]:
                self.assertIsNotNone(ELEMENT_NAME.fullmatch(text), text)
        prototype = loaded.prototypes[part]
        return {"faces": [prototype.face_names[k] for k in sorted(prototype.face_names)],
                "edges": [prototype.edge_names[k] for k in sorted(prototype.edge_names)]}

    def derivations(self, names: dict[str, list[str]], name: str = "block", part: int = 0) -> dict[str, list[str]]:
        """``names`` with every folded atom spelled out, from the table the build holds of
        the part (in the worker's memory: nothing but the xbf is written)."""
        key = document.load(self.folder / f"XBF/{name}.xbf").prototypes[part].key
        table = next(named.names["table"] for named in reversed(engine_build._PARTS.values()) if named.key == key)

        def spelled(text: str) -> str:
            for atom in folded_atoms(text):
                text = text.replace(atom, spelled(table[atom]))
            return text

        return {kind: [spelled(text) for text in texts] for kind, texts in names.items()}


class AssignedNamesTest(NamingCase):
    def test_a_feature_is_named_by_the_target_its_result_is_assigned_to(self) -> None:
        faces = self.derivations(self.names(BLOCK, insert="", relief="relief"))["faces"]
        text = "\n".join(faces)
        # The box: the first assignment to ``body``; the cut: ``relief``; the cylinder it
        # cut with, made in the same statement: ``relief_make_cylinder1``.
        self.assertIn("f:block.body.", text)
        self.assertIn(";M:block.relief", text)
        self.assertIn("f:block.relief_make_cylinder1.", text)
        # The first assignment to ``final`` is ``final``; a reassignment is the target and
        # its statement's tag, six letters of its skeleton.
        self.assertRegex(text, r";M:block\.final(;|\n|$)")
        self.assertRegex(text, r";M:block\.final_[a-p]{6}(;|\n|$)")
        # A helper's call in its return expression (``peg``'s cylinder) is named by the
        # assignment its result flows into, ``final``'s.
        self.assertIn("f:block.final_make_cylinder1.", text)
        self.assertNotIn("f:peg.", text)
        # A call whose result nothing assigns is its function's and operation's.
        self.assertIn(";M:block.fuse1", text)
        # A tuple target names each of its values.
        self.assertIn("f:block.a.", text)
        self.assertIn("f:block.b.", text)

    def test_inserting_a_feature_renames_only_what_it_touches(self) -> None:
        before = self.derivations(self.names(BLOCK, insert="", relief="relief"))
        hole = "    body = body - bd.Pos(-6, 5, 0) * bd.Cylinder(1.5, 30)\n"
        after = self.derivations(self.names(BLOCK, insert=hole, relief="relief"))
        # The new hole cuts the box's top and bottom: those two faces take its step and are
        # renamed. Every other face -- the relief's, the peg's, the second cut's, the small
        # boxes' -- keeps its name, though the cuts after it are later calls of ``cut``.
        lost = set(before["faces"]) - set(after["faces"])
        self.assertEqual({name.split(";")[0] for name in lost}, {"f:block.body.5", "f:block.body.6"})
        self.assertEqual(len(set(after["faces"]) - set(before["faces"])), 3)  # those two, and the hole's
        # An edge is renamed only where it is made from one of them (a later cut's rim on
        # the top face): its derivation starts at that face.
        lost_edges = set(before["edges"]) - set(after["edges"])
        self.assertTrue(lost_edges)
        self.assertEqual({name.split(";")[0][2:] for name in lost_edges}, {"block.body.5", "block.body.6"})

    def test_a_reassignment_is_its_skeleton_and_a_helper_s_call_its_caller_s(self) -> None:
        before = self.derivations(self.names(CHAIN, name="chain", insert="", radius=3), name="chain")
        names = "\n".join(before["faces"])
        self.assertRegex(names, r"(?m)^f:chain\.plate\.1$")  # the first assignment: the target
        self.assertRegex(names, r"(?m);M:chain\.plate_([a-p]{6});M:chain\.plate_\1(2);M:chain\.plate_[a-p]{6}$")
        # ``_bore`` returns its cylinder unassigned: named by the caller's assignment.
        self.assertRegex(names, r"f:chain\.plate_[a-p]{6}2_make_cylinder1\.1")
        self.assertNotIn("_bore.", names)
        # A dimension edit -- a literal -- keeps every name.
        self.assertEqual(self.derivations(self.names(CHAIN, name="chain", insert="", radius=3.5), name="chain"), before)
        # A step of another shape inserted into the chain, through the helper too: it
        # renames the faces it cuts (the top and the bottom) and nothing else -- not the
        # reassignments after it, not the cylinder the helper makes for the next one.
        hole = "    plate = plate - _bore(1, 0).moved(bd.Location((0, -6, 0)))\n"
        after = self.derivations(self.names(CHAIN, name="chain", insert=hole, radius=3), name="chain")
        lost = set(before["faces"]) - set(after["faces"])
        self.assertEqual({name.split(";")[0] for name in lost}, {"f:chain.plate.5", "f:chain.plate.6"})
        self.assertEqual(len(set(after["faces"]) - set(before["faces"])), 3)  # those two, and the hole's
        lost_edges = set(before["edges"]) - set(after["edges"])
        self.assertEqual({name.split(";")[0] for name in lost_edges}, {"e:chain.plate.5", "e:chain.plate.6"})

    def test_a_child_model_names_its_own_result_whatever_its_caller_assigns(self) -> None:
        # A child's body is called by the engine, not by its caller's code: what it returns
        # is named in the child, as when it is built alone.
        child = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/peg.xbf")
def peg():
    return bd.Cylinder(2, 10)


@xbf("XBF/stand.xbf")
def stand():
    post = peg().shape
    return bd.Compound(children=[post, bd.Pos(10, 0, 0) * bd.Box(2, 2, 2)])
"""
        alone = self.names(child, name="peg")["faces"]
        self.assertTrue(alone and all(name.startswith("f:peg.") for name in alone), alone)
        self.names(child, name="stand")
        placed = [[p.face_names[k] for k in sorted(p.face_names)] for p in document.load(self.folder / "XBF/stand.xbf").prototypes]
        self.assertIn(alone, placed)

    def test_renaming_a_variable_renames_exactly_that_feature(self) -> None:
        # A warm build: every call hits and hands back the same shapes, and the part is
        # still named again, since the code its names come from changed.
        before = self.derivations(self.names(BLOCK, insert="", relief="relief"))
        after = self.derivations(self.names(BLOCK, insert="", relief="arch"))
        for kind in ("faces", "edges"):
            self.assertNotEqual(before[kind], after[kind])
            self.assertEqual([name.replace("block.relief", "block.arch") for name in before[kind]], after[kind])

    def test_a_name_holds_no_line_so_moving_the_code_renames_nothing(self) -> None:
        # Names are the tie to code: the function and the author's name for the feature.
        # Every line moves down and the build runs cold -- every call made again -- and
        # every element keeps its name; the file holds no line, and the script's path only in
        # its build closure (a pointer, beside the model's other pointers and digests).
        before = self.derivations(self.names(BLOCK, insert="", relief="relief"))
        memo.clear()
        engine_build._PARTS.clear()
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_BODIES": "0"}):
            after = self.derivations(self.names("# moved\n\n\n" + BLOCK, insert="", relief="relief"))
        self.assertEqual(before, after)
        from cadgen.engine import previous

        raw = (self.folder / "XBF/block.xbf").read_bytes()
        self.assertNotIn(b"block.py", raw.replace(previous.scan(self.folder / "XBF/block.xbf")[1].encode(), b""))


class LabelTest(NamingCase):
    def test_a_label_names_the_feature_that_first_made_the_labelled_shape(self) -> None:
        def both(insert: str = "", append: str = "") -> list[dict[str, list[str]]]:
            fields = {"name": "pair", "insert": insert, "append": append}
            found = [self.names(PAIR, part=0, **fields)]
            found.append(self.names(PAIR, part=1, **fields))
            return [self.derivations(names, "pair", part) for part, names in enumerate(found)]

        direct, twin = both()
        # The twin is made of the labelled shape after it was labelled: the label names the
        # feature that first made it, the box -- through the fillet the model tried on it
        # and threw away -- never the cut that last did.
        self.assertTrue(any(name.startswith("f:fork.") for name in twin["faces"]), twin["faces"])
        self.assertFalse(any(name.startswith("f:fork.") for name in direct["faces"]))
        hole = "    fork = fork - bd.Pos(6, 0, 0) * bd.Cylinder(1, 30)\n"
        for edit in ({"append": hole}, {"insert": hole}):
            direct_after, twin_after = both(**edit)
            # A cut appended, or inserted, takes the label over from nothing: the twin loses
            # exactly the names the direct part does.
            lost_direct = set(direct["faces"]) - set(direct_after["faces"])
            lost_twin = set(twin["faces"]) - set(twin_after["faces"])
            self.assertTrue(lost_direct, edit)
            self.assertEqual(len(lost_twin), len(lost_direct), (edit, lost_twin, lost_direct))


class RawMakerTest(NamingCase):
    def parts(self, offset: int) -> list[dict[str, list[str]]]:
        return [self.derivations(self.names(BAKED, name="baked", part=part, offset=offset), "baked", part)
                for part in range(3)]

    def assert_named_from_the_hub(self, parts: list[dict[str, list[str]]]) -> None:
        wheel, copied, stretched = parts
        for names, step in ((wheel, ";M:bake.made"), (copied, None), (stretched, ";M:bake.made")):
            # Every face and edge named, from the hub's own names: a placement or a copy
            # made past build123d keeps them, a transformation with its step.
            self.assertTrue(names["faces"] and names["edges"])
            for name in names["faces"] + names["edges"]:
                self.assertRegex(name, r"^[fe]:(wheel|baked)\.hub")
                if step is not None:
                    self.assertIn(step, name)
                else:
                    self.assertNotIn("bake.", name)

    def test_a_shape_placed_or_copied_by_a_raw_maker_keeps_its_names(self) -> None:
        first = self.parts(0)
        self.assert_named_from_the_hub(first)
        # A build that runs the root again and replays the child keeps every name, the
        # child's replayed transformation included.
        engine_build._PARTS.clear()
        self.assertEqual(self.parts(5), first)

    def test_a_maker_that_reports_nothing_names_by_ordinal(self) -> None:
        composed = memo._history

        def silent(feature, makers):
            return None if feature.op in ("transform", "gtransform", "copy") else composed(feature, makers)

        with mock.patch.object(memo, "_history", silent):
            self.assert_named_from_the_hub(self.parts(0))


PLACED = """
import build123d as bd
from build123d.topology.shape_core import downcast
from cadgen.engine import xbf


@xbf("XBF/placed.xbf")
def placed():
    plate = bd.Box(10, 6, 2) - bd.Cylinder(1, 5)
    plate.label = "plate"
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(2, 6)
    peg.label = "peg"
    inner = bd.Compound(children=[plate, peg], label="inner")
    pin = bd.Pos(0, 20, 0) * bd.Cylinder(1, 6)
    pin.label = "pin"
    assembly = bd.Compound(children=[inner, pin], label="assembly")
    # build123d's ``moved`` copies an assembly's parts; built again from them, the copies
    # are the parts, which no call returned itself.
    moved = assembly.moved(bd.Location((0, 0, 5)))
    kids = list(moved.children)
    moved.children = ()
    return bd.Compound(children=kids, label="rebuilt")


@xbf("XBF/unified.xbf")
def unified():
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    block = bd.Box(10, 6, 2) + bd.Pos(5, 0, 0) * bd.Box(10, 6, 2)
    merged = ShapeUpgrade_UnifySameDomain(block.wrapped, True, True, True)
    merged.Build()
    return bd.Solid(downcast(merged.Shape()))
"""


class PlacedPartsTest(NamingCase):
    def assert_named_from_their_own_features(self, parts: list[dict[str, list[str]]]) -> None:
        for names in parts:
            self.assertTrue(names["faces"])
            for name in names["faces"] + names["edges"]:
                self.assertNotIn(".moved", name.split(";")[0], name)
                self.assertRegex(name, r"^[fe]:(placed\.)?(plate|peg|pin)")

    def test_a_part_an_assembly_s_copy_holds_is_named_there(self) -> None:
        self.assert_named_from_their_own_features([self.names(PLACED, name="placed", part=part) for part in range(3)])

    def test_a_placement_that_copies_an_assembly_s_parts_never_names_them_its_own(self) -> None:
        from cadgen.engine.kernel import history as kernel_history

        composed = kernel_history.compose

        def unreported(inputs, results, records):
            # As when the makers' account of the parts an assembly's placement copies is lost.
            found = composed(inputs, results, records)
            if len(results) > 2:
                found = kernel_history.History()
            return found

        with mock.patch.object(kernel_history, "compose", unreported):
            self.assert_named_from_their_own_features(
                [self.names(PLACED, name="placed", part=part) for part in range(3)])

    def test_a_shape_a_model_unifies_itself_is_named(self) -> None:
        names = self.names(PLACED, name="unified")
        self.assertTrue(names["faces"])
        self.assertTrue(all(name.startswith("f:unified.block") for name in names["faces"]), names["faces"])


class ImportedNamesTest(NamingCase):
    def parts(self, name: str, text: str = IMPORTS, **fields: str) -> list[dict[str, list[str]]]:
        found = []
        for part in range(2):
            found.append(self.names(text, name=name, part=part, **fields))
        return found

    def test_an_imported_element_is_named_within_its_own_product(self) -> None:
        import build123d as bd

        plate = bd.Box(20, 10, 2) - bd.Cylinder(2, 10)
        plate.label = "plate"
        peg = bd.Pos(30, 0, 0) * bd.Cylinder(3, 8)
        peg.label = "peg"
        bd.export_step(bd.Compound(children=[plate, peg]), str(self.folder / "plain.step"))
        first = self.parts("imported", file="plain.step", lift=0)
        for names, faces in zip(first, (7, 3)):
            # A file that names no element: each part's elements by their ordinals in its
            # own product, 1 to its count -- never numbered across the file -- and the
            # placements made of them claim none.
            self.assertEqual(len(names["faces"]), faces)
            ordinals = sorted(int(name.rsplit(".", 1)[1]) for name in names["faces"])
            self.assertEqual(ordinals, list(range(1, faces + 1)), names["faces"])
            self.assertTrue(all(name.startswith("f:imported.bought.") for name in names["faces"]), names["faces"])
        # Placed elsewhere, each keeps every name.
        engine_build._PARTS.clear()
        self.assertEqual(self.parts("imported", file="plain.step", lift=7), first)
        # A file that names every face 'NONE' (the schema's empty name) names none of them.
        text = (self.folder / "plain.step").read_text(encoding="utf-8")
        (self.folder / "none.step").write_text(text.replace("ADVANCED_FACE(''", "ADVANCED_FACE('NONE'"),
                                               encoding="utf-8")
        self.assertIn("ADVANCED_FACE('NONE'", (self.folder / "none.step").read_text(encoding="utf-8"))
        self.assertEqual(self.parts("imported", file="none.step", lift=0), first)

    def test_an_imported_element_the_file_names_keeps_that_name(self) -> None:
        # The engine's own STEP names every face: read back, each keeps its name.
        written = self.parts("source", SOURCE)
        read = self.parts("imported", file="source.step", lift=0)
        for source, imported in zip(written, read):
            self.assertEqual(sorted(imported["faces"]), sorted(source["faces"]))


class GrammarTest(unittest.TestCase):
    def test_the_engine_reads_element_names_as_the_viewer_s_grammar_does(self) -> None:
        cases = json.loads(PARITY.read_text(encoding="utf-8"))["elementNameCases"]
        self.assertTrue(cases["names"] and cases["notNames"])
        for element in cases["names"]:
            self.assertIsNotNone(ELEMENT_NAME.fullmatch(element), element)
        for text in cases["notNames"]:
            self.assertIsNone(ELEMENT_NAME.fullmatch(text), text)


class VertexNamesTest(NamingCase):
    def test_every_vertex_is_named_in_the_document_and_its_structure(self) -> None:
        self.names(BLOCK, insert="", relief="relief")
        path = self.folder / "XBF/block.xbf"
        loaded = document.load(path)
        prototype = loaded.prototypes[0]
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

        vertices = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(prototype.shape, TopAbs_VERTEX, vertices)
        self.assertEqual(sorted(prototype.vertex_names), list(range(1, vertices.Extent() + 1)))
        self.assertTrue(all(name.startswith("v:block.") for name in prototype.vertex_names.values()))
        # Read back from the file's labels, and made from the build's tree in memory alike.
        read = loaded.structure()["prototypes"][0]["vertexNames"]
        self.assertEqual(read, {str(k): v for k, v in sorted(prototype.vertex_names.items())})
        self.assertEqual(document.tree_structure(document.saved(path), path)["prototypes"][0]["vertexNames"], read)


# Pieces of one shape handed on in an order the process picks: the string hash, which
# PYTHONHASHSEED sets, stands in for the heap, which orders a boolean's or a text's pieces.
SHUFFLED = """
import build123d as bd
from cadgen.engine import xbf

SPOTS = sorted([(0, 0), (3, 0), (6, 1), (9, 0), (12, 2)], key=lambda spot: hash(str(spot)))


@xbf("XBF/grid.xbf")
def grid():
    cell = bd.Rectangle(1, 2)
    sk = bd.Sketch() + [bd.Pos(*spot) * cell for spot in SPOTS]
    return bd.extrude(sk, amount=1)
"""


class RunOrderTest(unittest.TestCase):
    def test_two_cold_builds_name_every_element_alike_whatever_order_the_pieces_come_in(self) -> None:
        import subprocess
        import sys

        from OCP.BRep import BRep_Tool
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

        folder = Path(tempfile.mkdtemp(prefix="engine-run-order-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        (folder / "grid.py").write_text(textwrap.dedent(SHUFFLED), encoding="utf-8")
        src = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"

        def where(element, kind) -> tuple:
            if kind == TopAbs_VERTEX:
                return tuple(round(value, 4) for value in BRep_Tool.Pnt_s(TopoDS.Vertex(element)).Coord())
            props = GProp_GProps()
            (BRepGProp.SurfaceProperties_s if kind == TopAbs_FACE else BRepGProp.LinearProperties_s)(element, props)
            return tuple(round(value, 4) for value in props.CentreOfMass().Coord())

        def named(seed: str) -> dict:
            # A cold build in a process of its own: no daemon, no memo carried over.
            env = {**os.environ, "PYTHONPATH": str(src), "PYTHONHASHSEED": seed,
                   "CADGEN_ENGINE_DIR": str(folder / "engine")}
            done = subprocess.run([sys.executable, "-B", "-c", "import grid; grid.grid.build(daemon=False)"],
                                  cwd=folder, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            prototype = document.load(folder / "XBF/grid.xbf").prototypes[0]
            found = {}
            for kind, names in ((TopAbs_FACE, prototype.face_names), (TopAbs_EDGE, prototype.edge_names),
                                (TopAbs_VERTEX, prototype.vertex_names)):
                elements = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
                TopExp.MapShapes_s(prototype.shape, kind, elements)
                for ordinal, name in names.items():
                    found[(int(kind), where(elements.FindKey(ordinal), kind))] = name
            return found

        # Seeds 1 and 2 hand the cells over in different orders; each element keeps its name.
        first, second = named("1"), named("2")
        self.assertEqual(len(first), 5 * (6 + 12 + 8))
        self.assertEqual(first, second)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()

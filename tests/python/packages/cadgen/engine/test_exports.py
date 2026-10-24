"""Exports: a document translated to STEP, GLB, STL, 3MF and xbf by one writer
(``export.translate``), whether a decorator declares the file or ``cadgen export`` asks
for it. The STEP reads back through the engine's own reader with its names, colours,
materials and instance tree; the meshes are parsed and counted; a posed model's STEP is the
same bytes in every process; a build keeps a file its document did not change, writes only
the files its flags select, and code built from text writes the files its flags name."""

from __future__ import annotations

import json
import os
import shutil
import struct
import tempfile
import textwrap
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

import numpy as np

from cadgen.engine import api, document, export, materials, mesh
from cadgen.engine import build as engine_build
from cadgen.engine.export import ExportRefused, Source, translate

BOARD = """
import build123d as bd
from cadgen.ap242 import mechanism_state
from cadgen.engine import glb, materials, paint, step, stl, threemf, xbf


@xbf("XBF/peg.xbf")
def peg():
    peg = bd.Cylinder(2, 10)
    peg.color = bd.Color(0.9, 0.2, 0.1)
    return peg


@xbf("XBF/board.xbf")
@step("board.step")
@glb("board.glb")
@stl("board.stl")
@threemf("board.3mf")
def board():
    plate = bd.Pos(0, -20, 0) * bd.Box(30, 10, 2)
    plate.color = bd.Color(0.2, 0.3, 0.9)
    plate = paint(plate, plate.faces().sort_by(bd.Axis.Z)[-1], "#ff0000")
    plate = paint(plate, plate.faces().sort_by(bd.Axis.Z)[0], materials.steel)
    plate.material = materials.aluminium
    plate.label = "plate"
    pegs = [peg().shape.moved(bd.Location((x, 0, 0))) for x in (-10, 0, 10)]
    for index, placed in enumerate(pegs):
        placed.label = f"peg{{index}}"
    rack = bd.Compound(children=pegs, label="rack").moved(bd.Location((0, 0, {lift})))
    base = bd.Box(10, 10, 2)
    base.label = "base"
    lid = bd.Box(10, 10, 1, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    lid.label = "lid"
    bd.RevoluteJoint("flap", base, axis=bd.Axis((5, 0, 1), (0, 1, 0)), angular_range=(0, 90))
    bd.RigidJoint("mount", lid, bd.Location())
    base.joints["flap"].connect_to(lid.joints["mount"], angle=0)
    hinge = bd.Compound(children=[base, lid], label="hinge")
    mechanism_state(hinge, "open", flap=60)
    return bd.Compound(children=[plate, rack, hinge], label="board")
"""


# Six parts, each its own colour, a painted face and a material, and three instances of a
# seventh: a colour presentation per styled shape, which OCCT's writer keeps in a map.
KIT = """
import build123d as bd
from cadgen.engine import materials, paint, xbf


@xbf("XBF/kit.xbf")
def kit():
    looks = [(0.9, 0.2, 0.1), (0.1, 0.8, 0.2), (0.2, 0.3, 0.9), (0.7, 0.7, 0.1), (0.5, 0.1, 0.6), (0.1, 0.5, 0.5)]
    parts = []
    for index, rgb in enumerate(looks):
        part = bd.Pos(index * 20, 0, 0) * bd.Box(10, 10, 4 + index)
        part.color = bd.Color(*rgb)
        part = paint(part, part.faces().sort_by(bd.Axis.Z)[-1], bd.Color(rgb[2], rgb[0], rgb[1]))
        part.material = (materials.aluminium, materials.steel)[index % 2]
        part.label = f"part{index}"
        parts.append(part)
    peg = bd.Cylinder(2, 10)
    peg.color = bd.Color(0.3, 0.6, 0.6)
    pegs = [peg.moved(bd.Location((x, 30, 0))) for x in (0, 10, 20)]
    for index, placed in enumerate(pegs):
        placed.label = f"peg{index}"
    return bd.Compound(children=[*parts, bd.Compound(children=pegs, label="rack")], label="kit")
"""
# A STEP written in a process of its own: its colour presentations' order is the map's there.
EXPORT = """
import sys
from pathlib import Path
from cadgen.engine.export import translate
translate(Path(sys.argv[1]), None, Path(sys.argv[2]))
"""
# Three hinges of one base and one lid, each placed apart, each lid on a joint of its own: a
# sub-assembly repeated, posed three ways by a model of its own.
HINGES = """
import build123d as bd
from cadgen.ap242 import mechanism_state, posed
from cadgen.engine import xbf

PLATE = bd.Box(10, 10, 2)
PLATE.color = bd.Color(0.2, 0.3, 0.9)
LEAF = bd.Box(10, 10, 1, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
LEAF.color = bd.Color(0.9, 0.2, 0.1)


def hinge(index):
    base = PLATE.moved(bd.Location((index * 20, 0, 0)))
    base.label = "base"
    lid = LEAF.moved(bd.Location())
    lid.label = "lid"
    bd.RevoluteJoint(f"flap{index}", base, axis=bd.Axis((index * 20 + 5, 0, 1), (0, 1, 0)), angular_range=(0, 90))
    bd.RigidJoint("mount", lid, bd.Location())
    base.joints[f"flap{index}"].connect_to(lid.joints["mount"], angle=0)
    return bd.Compound(children=[base, lid], label="hinge")


@xbf("XBF/hinges.xbf")
def hinges():
    row = bd.Compound(children=[hinge(0), hinge(1), hinge(2)], label="hinges")
    mechanism_state(row, "open", flap0=30, flap1=60, flap2=90)
    return row


@xbf("XBF/hinges_open.xbf")
def hinges_open():
    return posed(hinges().shape, "open")
"""


def _glb_json(path: Path) -> dict:
    data = path.read_bytes()
    length, kind = struct.unpack_from("<I4s", data, 12)
    assert kind == b"JSON"
    return json.loads(data[20:20 + length])


def _facts(loaded: document.Loaded, prototype: document.Prototype) -> dict[str, dict]:
    """Each named element of a part by where it is (a face's centroid, an edge's midpoint, a
    vertex's point, rounded): names compared by geometry, not by the reader's ordinals."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    def where(kind: int, shape) -> tuple:
        if kind == TopAbs_FACE:
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(shape, props)
            point = props.CentreOfMass()
        elif kind == TopAbs_EDGE:
            curve = BRepAdaptor_Curve(TopoDS.Edge_s(shape))
            point = curve.Value((curve.FirstParameter() + curve.LastParameter()) / 2)
        else:
            point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(shape))
        return tuple(round(value, 4) for value in (point.X(), point.Y(), point.Z()))

    found = {}
    for kind, names, label in ((TopAbs_FACE, prototype.face_names, "faces"),
                               (TopAbs_EDGE, prototype.edge_names, "edges"),
                               (TopAbs_VERTEX, prototype.vertex_names, "vertices")):
        mapped = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(prototype.shape, kind, mapped)
        found[label] = {where(kind, mapped.FindKey(ordinal)): name for ordinal, name in names.items()}
    return found


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-exports-")).resolve()
        cls.script = cls.folder / "board.py"
        cls.script.write_text(textwrap.dedent(BOARD.format(lift=6)), encoding="utf-8")
        reports = engine_build.build(cls.script, ["board"], cwd=cls.folder)
        assert reports[-1]["ok"], reports
        cls.report = reports[-1]
        cls.xbf = cls.folder / "XBF/board.xbf"
        cls.loaded = document.Loaded(cls.xbf)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_the_build_writes_the_xbf_first_then_every_declared_file(self) -> None:
        self.assertEqual(list(self.report["files"]), [str(self.xbf)] + [str(self.folder / name) for name in (
            "board.step", "board.glb", "board.stl", "board.3mf")])
        self.assertTrue(all(row["written"] for row in self.report["files"].values()))

    def test_a_step_reads_back_with_its_names_colours_materials_and_tree(self) -> None:
        step = document.Loaded(self.folder / "board.step")
        built, read = self.loaded.structure(), step.structure()

        def names(node: dict) -> list:
            return [node["name"], [names(child) for child in node.get("children", [])]]

        self.assertEqual(names(read["tree"]), names(built["tree"]), "the instance tree and every name")
        self.assertEqual([i["path"] for i in read["instances"]], [i["path"] for i in built["instances"]])
        for one, two in zip(read["instances"], built["instances"]):
            np.testing.assert_allclose(one["matrix"], two["matrix"], atol=1e-9)
        self.assertEqual([i["prototype"] for i in read["instances"]], [i["prototype"] for i in built["instances"]],
                         "a part placed three times is one product placed three times")
        ours = {p.name: p for p in self.loaded.prototypes}
        theirs = {p.name: p for p in step.prototypes}
        self.assertEqual(set(theirs), set(ours))
        for name, prototype in ours.items():
            other = theirs[name]
            self.assertEqual(other.color, prototype.color, name)
            # Every face, edge and vertex keeps its element name, on the same element.
            self.assertEqual(_facts(step, other), _facts(self.loaded, prototype), name)
            self.assertTrue(prototype.face_names and prototype.edge_names, name)
        plate, read_plate = ours["plate"], theirs["plate"]
        self.assertEqual((read_plate.material.name, read_plate.material.density),
                         (plate.material.name, plate.material.density), "a material's name and density")
        # A painted colour is a face's colour in the STEP as in the xbf.
        red = [rgba for rgba in plate.face_colors.values() if rgba == (1.0, 0.0, 0.0, 1.0)]
        self.assertEqual(red, [rgba for rgba in read_plate.face_colors.values() if rgba == (1.0, 0.0, 0.0, 1.0)])
        # What OCCT's STEP writer drops: the PBR look (metallic, roughness), a face's material
        # (its colour stays), and the mechanism.
        self.assertEqual(plate.material.metallic, 1.0)
        self.assertEqual(read_plate.material.metallic, 0.0)
        self.assertEqual(len(plate.face_materials), 1)
        self.assertEqual(read_plate.face_materials, {})
        [ordinal] = plate.face_materials
        self.assertEqual(read_plate.face_colors[ordinal][:3], plate.face_colors.get(ordinal, plate.face_materials[
            ordinal].color)[:3])
        self.assertIn("kinematics", built)
        self.assertNotIn("kinematics", read)

    def test_glb_holds_a_mesh_per_part_a_node_per_placement_and_paints_apart(self) -> None:
        gltf = _glb_json(self.folder / "board.glb")
        placed = [node for node in gltf["nodes"] if "mesh" in node]
        self.assertEqual(sorted(node["name"] for node in placed),
                         ["hinge/base", "hinge/lid", "plate", "rack/peg0", "rack/peg1", "rack/peg2"])
        self.assertEqual(len(gltf["meshes"]), 4, "the peg placed three times is one mesh")
        plate = next(entry for entry in gltf["meshes"] if entry["name"] == "plate")
        looks = [gltf["materials"][primitive["material"]] for primitive in plate["primitives"]]
        self.assertEqual(len(looks), 3, "the part's own look, a painted colour and a painted material")
        by_name = {look.get("name"): look for look in looks}
        self.assertEqual(by_name[materials.aluminium.name]["pbrMetallicRoughness"]["metallicFactor"], 1.0)
        self.assertIn(materials.steel.name, by_name)
        self.assertIn([1.0, 0.0, 0.0, 1.0], [look["pbrMetallicRoughness"]["baseColorFactor"] for look in looks])
        rack = next(node for node in placed if node["name"] == "rack/peg0")
        self.assertEqual(rack["matrix"][12:15], [-10.0, 0.0, 6.0])
        self.assertEqual({gltf["accessors"][primitive["indices"]]["componentType"] for entry in gltf["meshes"]
                          for primitive in entry["primitives"]}, {5123}, "a small mesh is indexed in 16 bits")
        # The root shows the document's Z-up millimetres in glTF's Y-up metres.
        root = gltf["nodes"][gltf["scenes"][0]["nodes"][0]]
        self.assertEqual(root["scale"], [0.001, 0.001, 0.001])
        np.testing.assert_allclose(root["rotation"], [-0.5 ** 0.5, 0, 0, 0.5 ** 0.5])

    def test_3mf_holds_an_object_per_part_an_item_per_placement_and_its_looks(self) -> None:
        with zipfile.ZipFile(self.folder / "board.3mf") as archive:
            model = ElementTree.fromstring(archive.read("3D/3dmodel.model"))
        core = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
        extension = "{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}"
        objects = model.findall(f"{core}resources/{core}object")
        self.assertEqual(sorted(entry.get("name") for entry in objects), ["base", "lid", "peg0", "plate"])
        self.assertEqual(len(model.findall(f"{core}build/{core}item")), 6)
        bases = model.findall(f"{core}resources/{core}basematerials/{core}base")
        metallic = model.findall(f"{core}resources/{extension}pbmetallicdisplayproperties/{extension}pbmetallic")
        self.assertEqual(len(metallic), len(bases), "one display property per base material")
        self.assertIn(materials.aluminium.name, [base.get("name") for base in bases])
        plate = next(entry for entry in objects if entry.get("name") == "plate")
        painted = [t for t in plate.iter(f"{core}triangle") if t.get("p1") is not None]
        self.assertEqual(len(painted), 4, "the two painted faces' triangles name their own looks")

    def test_a_3mf_is_the_same_bytes_whatever_the_clock(self) -> None:
        # zipfile stamps an entry with ``time.localtime()``: two clocks a day apart.
        written = []
        for seconds in (1_700_000_000, 1_700_086_403):
            out = self.folder / f"clock-{seconds}.3mf"
            with mock.patch("time.localtime", return_value=time.gmtime(seconds)):
                translate(self.xbf, None, out)
            written.append(out.read_bytes())
        self.assertEqual(written[0], written[1])
        with zipfile.ZipFile(self.folder / "clock-1700000000.3mf") as archive:
            self.assertEqual({entry.date_time for entry in archive.infolist()}, {export.ZIP_DATE})

    def test_stl_holds_every_placed_triangle(self) -> None:
        data = (self.folder / "board.stl").read_bytes()
        count = struct.unpack_from("<I", data, 80)[0]
        view = Source.read(self.xbf).view()
        held = export.mesh.meshes(view)
        self.assertEqual(count, sum(held[placed.prototype].triangles for placed in view.placements))
        self.assertEqual(len(data), 84 + 50 * count)

    def test_what_is_no_document_or_no_new_one_is_refused_by_name(self) -> None:
        with self.assertRaisesRegex(ExportRefused, "not written from another xbf"):
            translate(self.xbf, None, self.folder / "again.xbf")
        with self.assertRaisesRegex(ExportRefused, "is a mesh"):
            translate(self.folder / "board.glb", None, self.folder / "back.step")
        with self.assertRaisesRegex(ExportRefused, "an export is one of"):
            translate(self.xbf, None, self.folder / "board.obj")

    def test_the_export_verb_answers_in_json_and_a_failure_is_its_envelope(self) -> None:
        import contextlib
        import io

        from cadgen.engine import cli

        def run(*argv: str) -> tuple[int, str, str]:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = cli.main(list(argv))
            return status, out.getvalue(), err.getvalue()

        status, out, err = run("export", str(self.xbf), str(self.folder / "json.stl"), "--json")
        self.assertEqual(status, 0, err)
        found = json.loads(out)
        self.assertEqual((found["ok"], found["source"], [(row["path"], row["kind"]) for row in found["files"]]),
                         (True, str(self.xbf), [(str(self.folder / "json.stl"), "stl")]))
        self.assertEqual(found["files"][0]["bytes"], (self.folder / "json.stl").stat().st_size)
        # Refused: under --json, its envelope on stdout and exit 1; else its words on stderr, exit 2.
        status, out, err = run("export", str(self.xbf), str(self.folder / "board.obj"), "--json")
        self.assertEqual((status, json.loads(out)["ok"], err), (1, False, ""))
        self.assertIn("an export is one of", json.loads(out)["error"])
        status, out, err = run("export", str(self.xbf), str(self.folder / "board.obj"))
        self.assertEqual((status, out), (2, ""))
        self.assertIn("an export is one of", err)

    def test_a_step_becomes_an_xbf(self) -> None:
        out = self.folder / "from-step.xbf"
        translate(self.folder / "board.step", None, out)
        loaded = document.Loaded(out)
        self.assertEqual(sorted(p.name for p in loaded.prototypes), sorted(p.name for p in self.loaded.prototypes))
        self.assertTrue(all(len(p.key) == 32 for p in loaded.prototypes), "keyed by geometry, as a build keys a part")
        plate = next(p for p in loaded.prototypes if p.name == "plate")
        self.assertEqual(sorted(plate.face_names.values()),
                         sorted(next(p for p in self.loaded.prototypes if p.name == "plate").face_names.values()))

    def test_every_mesh_comes_from_the_one_cache(self) -> None:
        from cadgen.engine.serve import MESHES

        keys = {p.key for p in self.loaded.prototypes}
        self.assertTrue(keys <= set(MESHES.keys()), "the build's exports left their meshes in the process's cache")
        with mock.patch.object(mesh, "mesh_shape", side_effect=AssertionError("meshed again")):
            translate(self.xbf, None, self.folder / "again.stl")
            translate(self.xbf, None, self.folder / "again.3mf")


class BuildFilesTest(unittest.TestCase):
    """What a build writes: what its decorators declare (law 10), and nothing else."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-files-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def files(self) -> set[str]:
        return {path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()}

    def write(self, name: str, text: str) -> Path:
        script = self.folder / name
        script.write_text(textwrap.dedent(text), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        return script

    def test_an_unchanged_document_keeps_its_files(self) -> None:
        script = self.write("board.py", BOARD.format(lift=6))
        engine_build.build(script, ["board"], cwd=self.folder)
        stats = {path: os.stat(self.folder / path).st_mtime_ns for path in self.files() if path != "board.py"}
        [report] = engine_build.build(script, ["board"], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        self.assertFalse(any(row["written"] for row in report["files"].values()), report["files"])
        self.assertEqual({path: os.stat(self.folder / path).st_mtime_ns for path in stats}, stats)
        # A file removed is written again, and only it.
        (self.folder / "board.stl").unlink()
        [report] = engine_build.build(script, ["board"], cwd=self.folder)
        self.assertEqual([Path(path).name for path, row in report["files"].items() if row["written"]], ["board.stl"])

    def test_a_derived_decorator_alone_writes_its_one_file(self) -> None:
        script = self.write("solo.py", """
            import build123d as bd
            from cadgen.engine import step


            @step("solo.step")
            def solo():
                return bd.Box(1, 2, 3)
        """)
        [report] = engine_build.build(script, None, cwd=self.folder)
        self.assertTrue(report["ok"], report)
        self.assertEqual(self.files(), {"solo.py", "solo.step"})

    def test_a_decorator_takes_out_alone_and_a_file_shows_the_joints_pose(self) -> None:
        import cadgen.engine
        from cadgen.engine import model
        from cadgen.engine.model import glb, step, xbf

        with self.assertRaisesRegex(TypeError, "unexpected keyword argument.*material"):
            step("a.step", material="steel")
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument.*pose"):
            step("a.step", pose="open")
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument.*out2"):
            xbf(out2="a.xbf")
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument.*animate"):
            glb("a.glb", animate={"flap": (0, 90)})
        self.assertFalse(hasattr(model, "snapshot"), "a picture is the snapshot verb's, never a declaration")
        self.assertNotIn("snapshot", cadgen.engine.__all__)
        # As built is where the joints connect the parts: lid at 30 degrees in every file.
        script = self.write("hinged.py", BOARD.format(lift=6).replace("connect_to(lid.joints[\"mount\"], angle=0)",
                                                                      "connect_to(lid.joints[\"mount\"], angle=30)"))
        [report] = engine_build.build(script, ["board"], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        built = document.Loaded(self.folder / "XBF/board.xbf").structure()
        self.assertEqual(built["kinematics"]["asBuilt"], {"flap": 30.0})
        self.assertIn("open", built["kinematics"]["configurations"], "a configuration names a preset")

        def lid(structure: dict) -> list[float]:
            return [round(v, 6) for v in next(i for i in structure["instances"] if i["path"].endswith("/lid"))["matrix"]]

        self.assertEqual(lid(document.Loaded(self.folder / "board.step").structure()), lid(built),
                         "the STEP shows the lid where its joint put it, not at a configuration")

    def test_an_export_of_a_model_builds_it_then_writes(self) -> None:
        import importlib.util

        script = self.write("board.py", BOARD.format(lift=6))
        out = self.folder / "made/board.stl"
        # A script is never a source, whatever names it: refused as any file that is no document.
        for named in (script, f"{script}::board"):
            with self.assertRaisesRegex(ExportRefused, "is no document"):
                api.export(named, out, daemon=False)
        self.assertFalse(out.exists())
        spec = importlib.util.spec_from_file_location("board_script", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        written = api.export(module.board, out, self.folder / "made/rack.3mf", daemon=False)
        self.assertEqual([row.path for row in written], [out, self.folder / "made/rack.3mf"])
        self.assertTrue(out.is_file())
        self.assertIn("XBF/board.xbf", self.files(), "the model's document was built")
        self.assertIn("board.step", self.files(), "a model that runs writes every file it declares")


class StepTest(unittest.TestCase):
    """A STEP's colours and names read as the file means them."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-step-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def write(self, result, name: str) -> Path:
        from cadgen.engine.export.step import write_document

        path = self.folder / f"{name}.step"
        tree = result if isinstance(result, document.Tree) else document.collect(result, name)
        write_document(document.to_xcaf(tree), path)
        return path

    def test_a_colour_written_to_step_reads_back_as_written(self) -> None:
        import build123d as bd

        part = bd.Box(4, 4, 4)
        part.label = "grey"
        part.color = bd.Color(0.58, 0.62, 0.66)
        read = document.read_step_shape(self.write(bd.Compound(children=[part], label="one"), "one"))
        found = read if read.label == "grey" else next(node for node in read.children if node.label == "grey")
        for got, want in zip(tuple(found.color), (0.58, 0.62, 0.66, 1.0)):
            self.assertAlmostEqual(got, want, delta=1e-6)

    def test_a_placeholder_occurrence_name_is_its_product_s_and_escapes_read_as_text(self) -> None:
        import build123d as bd

        board = bd.Box(4, 4, 1)
        board.label = "Board"
        boss = bd.Pos(10, 0, 0) * bd.Cylinder(1, 2)
        boss.label = "凸台-拉伸4"
        tree = document.collect(bd.Compound(children=[board, boss], label="hat"), "hat")
        tree.root.components[0].name = "=>[0:1:1:2]"  # as OCCT names an occurrence its file left unnamed
        step = self.write(tree, "hat")
        self.assertIn("=>[0:1:1:2]", step.read_text(encoding="utf-8"))
        self.assertEqual([i.path[-1] for i in document.Loaded(step).instances], ["Board", "凸台-拉伸4"])
        self.assertEqual([child.label for child in document.read_step_shape(step).children], ["Board", "凸台-拉伸4"])
        text = step.read_text(encoding="utf-8")
        for escaped in (r"\X2\51F853F0\X0\-\X2\62C94F38\X0\4", r"\\X2\\51F853F0\\X0\\-\\X2\\62C94F38\\X0\\4"):
            path = self.folder / "escaped.step"
            path.write_text(text.replace("凸台-拉伸4", escaped), encoding="utf-8")
            self.assertEqual(document.Loaded(path).instances[-1].path[-1], "凸台-拉伸4", escaped)
            self.assertEqual(document.Loaded(path).prototypes[-1].name, "凸台-拉伸4", escaped)
        self.assertEqual(document.step_name("caf\\X\\E9 \\X4\\0001F600\\X0\\"), "café 😀")


    def test_a_step_is_the_same_bytes_in_every_process_and_on_every_day(self) -> None:
        import subprocess
        import sys

        from cadgen.engine.export.step import WRITTEN_STAMP

        (self.folder / "kit.py").write_text(textwrap.dedent(KIT), encoding="utf-8")
        (report,) = engine_build.build(self.folder / "kit.py", ["kit"], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        written = []
        # Twenty-six hours apart: the two processes' local dates always differ.
        for zone in ("Etc/GMT+12", "Etc/GMT-14"):
            out = self.folder / f"kit-{zone.replace('/', '-')}.step"
            done = subprocess.run([sys.executable, "-c", EXPORT, str(self.folder / "XBF/kit.xbf"), str(out)],
                                  env={**os.environ, "TZ": zone}, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            written.append(out)
        first, second = (path.read_bytes() for path in written)
        self.assertEqual(first, second)
        self.assertIn(f"'{WRITTEN_STAMP}'".encode(), first[:1024])
        self.assertEqual(first.count(b"MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION"), 7)
        # Reordered, every presentation still styles its own shape: the xbf's looks read back.
        looks = {p.name: (p.color, p.material and p.material.name) for p in document.Loaded(written[0]).prototypes}
        built = {p.name: (p.color, p.material and p.material.name)
                 for p in document.Loaded(self.folder / "XBF/kit.xbf").prototypes}
        self.assertEqual(sorted(looks), [*(f"part{i}" for i in range(6)), "peg0"])
        self.assertEqual(looks, built)

    def test_a_step_written_again_in_one_process_is_a_fresh_process_s_bytes(self) -> None:
        # The kernel numbers assembly occurrences on from every STEP the process wrote before: a
        # warm worker's export is numbered as a fresh process's all the same.
        import re
        import subprocess
        import sys

        (self.folder / "kit.py").write_text(textwrap.dedent(KIT), encoding="utf-8")
        (report,) = engine_build.build(self.folder / "kit.py", ["kit"], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        xbf = self.folder / "XBF/kit.xbf"
        here = []
        for at in range(2):
            out = self.folder / f"here-{at}.step"
            translate(xbf, None, out)
            here.append(out.read_bytes())
        fresh = self.folder / "fresh.step"
        done = subprocess.run([sys.executable, "-c", EXPORT, str(xbf), str(fresh)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(here[0], here[1])
        self.assertEqual(here[0], fresh.read_bytes())
        ids = re.findall(rb"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('(\d+)'", here[1])
        self.assertEqual(ids, [b"%d" % number for number in range(1, len(ids) + 1)])
        self.assertGreater(len(ids), 3)

    def test_the_presentations_are_settled_in_the_file_whatever_order_the_writer_left(self) -> None:
        # Two writes of one document whose presentations came out in either order, numbered
        # either way: the file's tail is renumbered where it stands, and what is quoted is text.
        from cadgen.engine.export.step import _settle

        head = ("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1 = SHAPE_REPRESENTATION('',(#2,#3),#4);\n"
                "#2 = MANIFOLD_SOLID_BREP('a',#9);\n#3 = MANIFOLD_SOLID_BREP('b',#9);\n#4 = ( REPRESENTATION_CONTEXT\n"
                "('Context #1','3D') );\n")
        red = ["MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION('',(\n    #{si}),#4);",
               "STYLED_ITEM('color',(#{psa}),#2);", "PRESENTATION_STYLE_ASSIGNMENT((#{rgb}));", "COLOUR_RGB('red #1',1.,0.,0.);"]
        blue = [line.replace("#2);", "#3);").replace("red #1", "blue").replace("1.,0.,0.", "0.,0.,1.") for line in red]

        def written(first: list[str], second: list[str], at: int) -> Path:
            lines = []
            for block in (first, second):
                numbers = dict(zip(("mdgpr", "si", "psa", "rgb"), range(at, at + 4)))
                lines += [f"#{numbers['mdgpr'] + offset} = " + text.format(**numbers)
                          for offset, text in enumerate(block)]
                at += 4
            path = self.folder / f"tail-{len(list(self.folder.iterdir()))}.step"
            path.write_bytes((head + "\n".join(lines) + "\nENDSEC;\nEND-ISO-10303-21;\n").encode())
            return path

        one, other = written(red, blue, 5), written(blue, red, 5)
        self.assertNotEqual(one.read_bytes(), other.read_bytes())
        for path in (one, other):
            _settle(path)
        self.assertEqual(one.read_bytes(), other.read_bytes())
        text = one.read_text(encoding="ascii")
        self.assertEqual(text[:len(head)], head)
        # Red styles #2, which the shapes number first: its presentation comes first, its colour
        # follows it, and the quoted '#1' is the colour's name still.
        self.assertIn("#5 = MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION('',(\n    #6),#4);", text)
        self.assertIn("#6 = STYLED_ITEM('color',(#7),#2);", text)
        self.assertIn("#8 = COLOUR_RGB('red #1',1.,0.,0.);", text)
        self.assertIn("#10 = STYLED_ITEM('color',(#11),#3);", text)

    def test_a_posed_step_of_repeated_sub_assemblies_is_the_same_bytes_in_every_process(self) -> None:
        import subprocess
        import sys

        from cadgen.engine import mechanism

        (self.folder / "hinges.py").write_text(textwrap.dedent(HINGES), encoding="utf-8")
        (report,) = engine_build.build(self.folder / "hinges.py", ["hinges_open"], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        xbf = self.folder / "XBF/hinges.xbf"
        written = []
        for seed in ("1", "2"):
            out = self.folder / f"open-{seed}.step"
            done = subprocess.run([sys.executable, "-c", EXPORT, str(self.folder / "XBF/hinges_open.xbf"), str(out)],
                                  env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            written.append(out)
        first, second = (path.read_bytes() for path in written)
        self.assertEqual(first, second)
        # Each hinge's lid stands where the sampler poses the hinges' own, read back from the file.
        structure = document.Loaded(xbf).structure()
        values, _named = mechanism.resolve(structure["kinematics"], "open")
        posed = mechanism.posed_instances(structure, values)
        read = document.Loaded(written[0])
        lids = [at for at, instance in enumerate(structure["instances"]) if instance["path"].endswith("lid")]
        found = [instance.matrix for instance in read.instances if instance.path[-1] == "lid"]
        self.assertEqual(len(lids), 3)
        self.assertEqual(len(found), 3)
        for at, matrix in zip(lids, found):
            np.testing.assert_allclose(matrix, posed[at], atol=1e-6)


if __name__ == "__main__":
    unittest.main()

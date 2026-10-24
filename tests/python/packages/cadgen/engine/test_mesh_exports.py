"""Mesh to mesh: a GLB, an STL or a 3MF exported to either of the other two (``export/mesh_file.py``).

Each fixture is a few triangles written here by hand: a 10 mm cube as a binary STL, a 3MF of two
named, coloured objects (one placed twice), a GLB of two named meshes in two materials. Each pair
converts; the cube is 10 mm in every file (0.01 in a GLB's numbers); names and colours survive
GLB to 3MF and back; a mesh is never made B-rep; and a conversion loads no CAD kernel."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from functools import partial
from pathlib import Path
from unittest import mock

import numpy as np

from cadgen.engine import api, export
from cadgen.engine.export import ExportRefused, Source, translate

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"

CORNERS = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10]],
                   float)
FACES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6],
         [3, 0, 4], [3, 4, 7]]


def stl(path: Path, scale: float = 1.0) -> Path:
    data = bytearray(b"cube".ljust(80, b" ")) + struct.pack("<I", len(FACES))
    for face in FACES:
        data += struct.pack("<3f", 0, 0, 0) + b"".join(struct.pack("<3f", *(CORNERS[i] * scale)) for i in face) + b"\0\0"
    path.write_bytes(bytes(data))
    return path


def threemf(path: Path, unit: str = "millimeter", side: float = 10.0) -> Path:
    """Two objects: a red ``block`` (the cube, ``side`` on a side) placed twice, and a blue ``tile`` (two triangles)."""
    vertices = "".join(f'<vertex x="{x * side / 10:g}" y="{y * side / 10:g}" z="{z * side / 10:g}"/>' for x, y, z in CORNERS)
    triangles = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in FACES)
    model = (f'<?xml version="1.0" encoding="UTF-8"?><model unit="{unit}" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
             '<basematerials id="1"><base name="red" displaycolor="#FF0000FF"/><base name="blue" displaycolor="#0000FFFF"/>'
             '</basematerials>'
             f'<object id="2" type="model" name="block" pid="1" pindex="0"><mesh><vertices>{vertices}</vertices>'
             f'<triangles>{triangles}</triangles></mesh></object>'
             '<object id="3" type="model" name="tile" pid="1" pindex="1"><mesh><vertices>'
             '<vertex x="0" y="0" z="0"/><vertex x="5" y="0" z="0"/><vertex x="5" y="5" z="0"/><vertex x="0" y="5" z="0"/>'
             '</vertices><triangles><triangle v1="0" v2="1" v3="2"/><triangle v1="0" v2="2" v3="3"/></triangles></mesh></object>'
             '</resources><build><item objectid="2"/><item objectid="2" transform="1 0 0 0 1 0 0 0 1 20 0 0"/>'
             '<item objectid="3" transform="1 0 0 0 1 0 0 0 1 0 20 0"/></build></model>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("3D/3dmodel.model", model)
    return path


def glb(path: Path) -> Path:
    """Two meshes in glTF's Y-up metres: ``block`` (the cube, red) and ``tile`` (green), each a node."""
    blob = bytearray()
    views, accessors = [], []

    def add(array: np.ndarray, kind: str, component: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": array.nbytes})
        blob.extend(array.tobytes())
        accessors.append({"bufferView": len(views) - 1, "componentType": component, "count": len(array), "type": kind})
        return len(accessors) - 1

    # The cube's CAD Z-up millimetres as glTF's Y-up metres: (x, y, z) -> (x, z, -y) / 1000.
    cube = np.array([[x, z, -y] for x, y, z in CORNERS], "<f4") / 1000
    tile = np.array([[0, 0, 0], [0.005, 0, 0], [0.005, 0, -0.005]], "<f4")
    meshes = [{"name": "block", "primitives": [{"attributes": {"POSITION": add(cube, "VEC3", 5126)},
                                                "indices": add(np.array(FACES, "<u2").reshape(-1), "SCALAR", 5123),
                                                "material": 0}]},
              {"name": "tile", "primitives": [{"attributes": {"POSITION": add(tile, "VEC3", 5126)}, "material": 1}]}]
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0, 1]}],
                "nodes": [{"name": "block", "mesh": 0}, {"name": "tile", "mesh": 1, "translation": [0.0, 0.0, -0.02]}],
                "meshes": meshes, "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}],
                "materials": [{"name": "red paint", "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1],
                                                                             "metallicFactor": 0.0, "roughnessFactor": 0.5}},
                              {"name": "green paint", "pbrMetallicRoughness": {"baseColorFactor": [0, 1, 0, 1],
                                                                               "metallicFactor": 0.0}}]}
    text = json.dumps(document).encode()
    text += b" " * (-len(text) % 4)
    while len(blob) % 4:
        blob.append(0)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 28 + len(text) + len(blob)) + struct.pack("<II", len(text), 0x4E4F534A)
                     + text + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))
    return path


def placed(path: Path) -> list[tuple[str, np.ndarray, np.ndarray, tuple | None]]:
    """Each placement of a mesh file as it reads back: its part's name, its box (millimetres) and
    its part's colour (or the first painted face's)."""
    source = Source.read(path)
    view = source.view()
    held = export.mesh.meshes(view)
    found = []
    for item in view.placements:
        prototype = view.prototypes[item.prototype]
        points = export.mesh.placed_points(held[item.prototype].positions, item.matrix)
        color = prototype.get("color") or next(iter((prototype.get("faceColors") or {}).values()), None)
        found.append((prototype["name"], points.min(axis=0), points.max(axis=0), None if color is None else tuple(color)))
    return found


def glb_json(path: Path) -> dict:
    data = path.read_bytes()
    return json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])


class MeshExportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="mesh-exports-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)


class EveryPairConverts(MeshExportTestCase):
    def test_a_10_mm_cube_is_10_mm_in_every_pair_and_0_01_in_a_glb(self) -> None:
        sources = {".stl": stl(self.folder / "cube.stl")}
        sources[".3mf"] = self.folder / "from-stl.3mf"
        sources[".glb"] = self.folder / "from-stl.glb"
        translate(sources[".stl"], None, sources[".3mf"])
        translate(sources[".stl"], None, sources[".glb"])
        for suffix, source in sources.items():
            for other in sources:
                if other == suffix:
                    continue
                out = self.folder / f"{source.stem}-{suffix[1:]}{other}"
                translate(source, None, out)
                (_name, low, high, _color), = placed(out)
                np.testing.assert_allclose(low, [0, 0, 0], atol=1e-5, err_msg=out.name)
                np.testing.assert_allclose(high, [10, 10, 10], atol=1e-5, err_msg=out.name)
                if other == ".glb":
                    found = glb_json(out)
                    extent = np.array(found["accessors"][0]["max"]) - found["accessors"][0]["min"]
                    np.testing.assert_allclose(extent * found["nodes"][0]["scale"], [0.01] * 3, atol=1e-8)
                if other == ".3mf":
                    with zipfile.ZipFile(out) as archive:
                        self.assertIn('unit="millimeter"', archive.read("3D/3dmodel.model").decode())

    def test_a_glb_indexes_a_mesh_in_16_bits_up_to_65535_vertices_and_in_32_past_them(self) -> None:
        # 22,000 triangles apart from each other: 66,000 vertices, past what 16 bits index.
        corners = np.arange(22_000, dtype="<f4")[:, None, None] * np.array([1, 0, 0], "<f4") + np.array(
            [[0, 0, 0], [0.5, 0, 0], [0, 0.5, 0]], "<f4")
        rows = np.zeros(22_000, dtype=[("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])
        rows["corners"] = corners
        many = self.folder / "many.stl"
        many.write_bytes(b"many".ljust(80, b" ") + struct.pack("<I", len(rows)) + rows.tobytes())
        for source, kind in ((stl(self.folder / "cube.stl"), 5123), (many, 5125)):
            out = self.folder / f"{source.stem}.glb"
            translate(source, None, out)
            found = glb_json(out)
            [primitive] = [entry for mesh in found["meshes"] for entry in mesh["primitives"]]
            self.assertEqual(found["accessors"][primitive["indices"]]["componentType"], kind, source.name)
            vertices = found["accessors"][primitive["attributes"]["POSITION"]]["count"]
            self.assertEqual(vertices > 65535, kind == 5125, vertices)
            again = self.folder / f"{source.stem}-again.stl"
            translate(out, None, again)
            self.assertEqual(struct.unpack_from("<I", again.read_bytes(), 80)[0], {5123: 12, 5125: 22_000}[kind],
                             "every triangle reads back")

    def test_a_3mf_in_inches_is_made_millimetres_and_an_unknown_unit_is_refused(self) -> None:
        inches = threemf(self.folder / "inch.3mf", unit="inch", side=10 / 25.4)
        translate(inches, None, self.folder / "inch.stl")
        (_name, low, high, _color), = placed(self.folder / "inch.stl")
        # The block 10 mm, placed again 20 inches along X; the 5-inch tile 20 inches along Y.
        np.testing.assert_allclose([low, high], [[0, 0, 0], [508 + 10, 508 + 127, 10]], atol=1e-3)
        np.testing.assert_allclose(placed(inches)[0][2] - placed(inches)[0][1], [10, 10, 10], atol=1e-4)
        with self.assertRaisesRegex(ExportRefused, 'model unit "cubit" is not one the 3MF specification defines'):
            translate(threemf(self.folder / "cubit.3mf", unit="cubit"), None, self.folder / "cubit.stl")
        self.assertFalse((self.folder / "cubit.stl").exists())

    def test_a_glb_is_read_y_up_metres_as_z_up_millimetres(self) -> None:
        translate(glb(self.folder / "parts.glb"), None, self.folder / "parts.stl")
        corners = Source.read(self.folder / "parts.stl")
        points = next(iter(corners.meshes.values())).positions
        # The cube where it is in CAD (0..10 on every axis), the tile 20 mm along Y, flat on Z = 0.
        np.testing.assert_allclose(points.min(axis=0), [0, 0, 0], atol=1e-5)
        np.testing.assert_allclose(points.max(axis=0), [10, 25, 10], atol=1e-5)

    def test_glb_and_stl_from_3mf_hold_every_placed_triangle(self) -> None:
        source = threemf(self.folder / "kit.3mf")
        translate(source, None, self.folder / "kit.stl")
        data = (self.folder / "kit.stl").read_bytes()
        self.assertEqual(struct.unpack_from("<I", data, 80)[0], 12 + 12 + 2, "one soup of every placed triangle")
        translate(source, None, self.folder / "kit.glb")
        found = glb_json(self.folder / "kit.glb")
        self.assertEqual(sorted(node["name"] for node in found["nodes"][1:]), ["block", "block", "tile"])
        self.assertTrue(all("NORMAL" in primitive["attributes"] for mesh in found["meshes"] for primitive in mesh["primitives"]),
                        "a mesh of a format with no normals is given the viewer's")


class NamesAndColoursSurvive(MeshExportTestCase):
    def test_glb_to_3mf_and_back_keeps_names_placements_and_colours(self) -> None:
        source = glb(self.folder / "parts.glb")
        translate(source, None, self.folder / "parts.3mf")
        translate(self.folder / "parts.3mf", None, self.folder / "again.glb")
        before, middle, after = (placed(path) for path in (source, self.folder / "parts.3mf", self.folder / "again.glb"))
        self.assertEqual([row[0] for row in before], ["block", "tile"])
        for row in (middle, after):
            self.assertEqual([found[0] for found in row], ["block", "tile"])
            for (_name, low, high, color), (_n, low2, high2, color2) in zip(before, row):
                np.testing.assert_allclose(low2, low, atol=1e-4)
                np.testing.assert_allclose(high2, high, atol=1e-4)
                np.testing.assert_allclose(color2, color, atol=2e-3)  # an 8-bit sRGB 3MF colour between
        with zipfile.ZipFile(self.folder / "parts.3mf") as archive:
            model = archive.read("3D/3dmodel.model").decode()
        self.assertIn('name="red paint"', model)
        self.assertIn('displaycolor="#00FF00FF"', model)

    def test_3mf_to_glb_and_back_keeps_objects_build_items_and_colours(self) -> None:
        source = threemf(self.folder / "kit.3mf")
        translate(source, None, self.folder / "kit.glb")
        translate(self.folder / "kit.glb", None, self.folder / "again.3mf")
        before, after = placed(source), placed(self.folder / "again.3mf")
        self.assertEqual([row[0] for row in after], ["block", "block", "tile"])
        for (name, low, high, color), (name2, low2, high2, color2) in zip(before, after):
            self.assertEqual(name2, name)
            np.testing.assert_allclose(low2, low, atol=1e-4)
            np.testing.assert_allclose(high2, high, atol=1e-4)
            np.testing.assert_allclose(color2, color, atol=2e-3)
        self.assertEqual(sorted({tuple(round(c, 3) for c in row[3]) for row in after}), [(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 0.0, 1.0)])


class WhatIsRefused(MeshExportTestCase):
    def test_a_mesh_makes_no_b_rep_and_no_file_of_its_own_kind(self) -> None:
        cube = stl(self.folder / "cube.stl")
        for destination, words in (("cube.step", "cube.stl is a mesh: it has no B-rep, and no STEP export is made from one"),
                                   ("cube.xbf", "no xbf export is made from one"),
                                   ("cube.dxf", "no DXF export is made from one"),
                                   ("again.stl", "an STL is not written from another STL")):
            with self.assertRaisesRegex(ExportRefused, words):
                translate(cube, None, self.folder / destination)
        with self.assertRaisesRegex(ExportRefused, "is a mesh: it has no B-rep"):
            translate(glb(self.folder / "parts.glb"), None, self.folder / "parts.xbf")

    def test_every_destination_is_checked_before_any_is_written(self) -> None:
        cube = stl(self.folder / "cube.stl")
        with self.assertRaisesRegex(ExportRefused, "no STEP export is made from one"):
            api.export(cube, self.folder / "cube.glb", self.folder / "cube.step", daemon=False)
        self.assertFalse((self.folder / "cube.glb").exists())
        from cadgen.engine.worker import _export

        with self.assertRaisesRegex(ExportRefused, "no STEP export is made from one"):
            _export({"source": {"path": str(cube)}, "destinations": [str(self.folder / "cube.3mf"),
                                                                     str(self.folder / "cube.step")]}, lambda _text: None)
        self.assertFalse((self.folder / "cube.3mf").exists())

    def test_an_accessor_reads_only_the_bytes_its_buffer_view_holds(self) -> None:
        # A POSITION accessor whose bufferView stride or count would reach past the file's own
        # buffer is refused, rather than reading whatever bytes follow it in memory.
        from cadgen.engine.formats import gltf as gltf_reader

        def one_triangle(stride: int | None, count: int) -> Path:
            positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], "<f4")
            blob = positions.tobytes()
            view = {"buffer": 0, "byteOffset": 0, "byteLength": len(blob)}
            if stride is not None:
                view["byteStride"] = stride
            doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
                   "nodes": [{"name": "m", "mesh": 0}],
                   "meshes": [{"name": "m", "primitives": [{"attributes": {"POSITION": 0}}]}],
                   "accessors": [{"bufferView": 0, "componentType": 5126, "count": count, "type": "VEC3"}],
                   "bufferViews": [view], "buffers": [{"byteLength": len(blob)}]}
            text = json.dumps(doc).encode()
            text += b" " * (-len(text) % 4)
            path = self.folder / "poke.glb"
            path.write_bytes(struct.pack("<III", 0x46546C67, 2, 28 + len(text) + len(blob))
                             + struct.pack("<II", len(text), 0x4E4F534A) + text
                             + struct.pack("<II", len(blob), 0x004E4942) + blob)
            return path

        # A matching stride reads the three real vertices.
        self.assertEqual(len(gltf_reader.read_gltf(one_triangle(12, 3)).parts[0].points), 3)
        # A stride wider than the element, or a count past the buffer, is refused by name.
        for stride, count in ((4096, 3), (16, 3), (12, 64)):
            with self.assertRaisesRegex(gltf_reader.GltfError, "does not hold"):
                gltf_reader.read_gltf(one_triangle(stride, count))

    def test_a_compressed_glb_is_refused_by_name(self) -> None:
        path = self.folder / "squeezed.glb"
        text = json.dumps({"asset": {"version": "2.0"}, "extensionsUsed": ["KHR_draco_mesh_compression"]}).encode()
        text += b" " * (-len(text) % 4)
        path.write_bytes(struct.pack("<III", 0x46546C67, 2, 20 + len(text)) + struct.pack("<II", len(text), 0x4E4F534A) + text)
        with self.assertRaisesRegex(ExportRefused, r"squeezed.glb is compressed \(KHR_draco_mesh_compression\)"):
            translate(path, None, self.folder / "squeezed.stl")


class TheVerbAndTheViewer(MeshExportTestCase):
    def test_export_in_process_writes_each_destination_from_one_read(self) -> None:
        written = api.export(stl(self.folder / "cube.stl"), self.folder / "cube.3mf", self.folder / "cube.glb", daemon=False)
        self.assertEqual([(row.path.name, row.kind) for row in written], [("cube.3mf", "threemf"), ("cube.glb", "glb")])
        self.assertTrue(all(row.bytes == row.path.stat().st_size for row in written))

    def test_a_mesh_page_offers_the_other_two_mesh_kinds_alone(self) -> None:
        from cadgen.engine.export.viewer import check, options

        source = Source.read(glb(self.folder / "parts.glb"))
        self.assertEqual([row["format"] for row in options(source)], ["stl", "threemf"])
        stat = (self.folder / "parts.glb").stat()
        check(source, {"version": f"{stat.st_mtime_ns}-{stat.st_size}"})  # the displayed revision is the file's


class ItStaysOffTheKernel(unittest.TestCase):
    def test_converting_every_pair_imports_no_cad_kernel(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="mesh-kernel-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        stl(folder / "cube.stl")
        glb(folder / "parts.glb")
        threemf(folder / "kit.3mf")
        code = ("import sys\n"
                "from pathlib import Path\n"
                "from cadgen.engine.api import export\n"
                f"folder = Path({str(folder)!r})\n"
                "for source, targets in (('cube.stl', ('a.3mf', 'a.glb')), ('parts.glb', ('b.stl', 'b.3mf')),\n"
                "                        ('kit.3mf', ('c.stl', 'c.glb'))):\n"
                "    export(folder / source, *(folder / target for target in targets), daemon=False)\n"
                "print(','.join(name for name in ('OCP', 'build123d', 'ezdxf') if name in sys.modules))\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "", "a mesh conversion must not wake the kernel")
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ["a.3mf", "a.glb", "b.3mf", "b.stl", "c.glb", "c.stl", "cube.stl", "kit.3mf", "parts.glb"])


class TheAgentOperation(MeshExportTestCase):
    def test_cad_export_takes_a_mesh_source_under_the_same_rules(self) -> None:
        from cadgen.jobs import TERMINAL
        from cadgen.mcp.operations import DESCRIPTIONS, Operations

        self.assertIn("A mesh source (.glb/.stl/.3mf) exports to the other two mesh kinds only", DESCRIPTIONS["cad_export"])
        cube = stl(self.folder / "cube.stl")
        jobs = Operations()

        def finish(answer: dict) -> dict:
            with jobs.changed:
                self.assertTrue(jobs.changed.wait_for(lambda: jobs.jobs[answer["id"]]["state"] in TERMINAL, timeout=60))
            return jobs.get(answer["id"])

        with mock.patch("cadgen.engine.api.export", partial(api.export, daemon=False)):
            done = finish(jobs.call("cad_export", {"requestId": "mesh-export-request-1", "source": str(cube),
                                                   "destinations": [str(self.folder / "cube.3mf")]}))
            refused = finish(jobs.call("cad_export", {"requestId": "mesh-export-request-2", "source": str(cube),
                                                      "destinations": [str(self.folder / "cube.step")]}))
        self.assertEqual(done["state"], "succeeded", done)
        self.assertEqual(done["result"]["files"][0]["path"], str(self.folder / "cube.3mf"))
        self.assertEqual(refused["state"], "failed")
        self.assertIn("no STEP export is made from one", json.dumps(refused))


if __name__ == "__main__":
    unittest.main()

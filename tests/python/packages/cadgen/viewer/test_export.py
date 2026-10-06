"""``cadgen viewer export``: a folder's CAD files recorded as a static copy of the viewer's API.

The fixture is one small project -- a STEP part and a STEP assembly seeded into a private store
without the kernel (``seed_result``), a DXF written by ezdxf, a hand-written STL and a URDF naming
it -- exported once for the class. Every assertion reads the export: what it names, what it
records for each file, and that nothing of this machine's paths is in it. The pool's compile and
surface jobs have their own suites; here the store is already complete, so the export does no
native work at all.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import ezdxf

from tests.python.support.paths import add_repo_path
from tests.python.support.store_fixtures import seed_result
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")
from cadgen.viewer import export as export_module  # noqa: E402
from cadgen.viewer.export import EXPORT_SCHEMA, ExportError, export_views, main  # noqa: E402

STL = """solid tetra
facet normal 0 0 -1
 outer loop
  vertex 0 0 0
  vertex 10 0 0
  vertex 0 10 0
 endloop
endfacet
endsolid tetra
"""
URDF = """<?xml version="1.0"?>
<robot name="smoke">
  <link name="base"><visual><geometry><mesh filename="../meshes/tetra.stl"/></geometry></visual></link>
  <link name="arm"><visual><geometry><mesh filename="package://elsewhere/arm.stl"/></geometry></visual></link>
  <joint name="shoulder" type="fixed"><parent link="base"/><child link="arm"/></joint>
</robot>
"""


class ExportFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = generated_cad_directory(prefix="viewer-export-")
        cls.base = Path(cls.tmp.name)
        cls.root = cls.base / "project"
        cls.env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(cls.base / "store"), "CADGEN_DAEMON": "0"})
        cls.env.start()
        for folder in ("src", "STEP", "DXF", "meshes", "robots", ".hidden", "node_modules"):
            (cls.root / folder).mkdir(parents=True)
        (cls.root / "src" / "bracket.py").write_text("print('model')\n", encoding="utf-8")
        (cls.root / ".hidden" / "secret.step").write_text("ISO-10303-21; hidden\n", encoding="utf-8")
        (cls.root / "node_modules" / "dep.stl").write_text(STL, encoding="utf-8")
        cls.part = cls.root / "STEP" / "bracket.step"
        cls.part.write_text("ISO-10303-21; part\n", encoding="utf-8")
        cls.part_tree = seed_result(cls.part, {"label": "bracket"})
        cls.assembly = cls.root / "STEP" / "pair.step"
        cls.assembly.write_text("ISO-10303-21; pair\n", encoding="utf-8")
        cls.assembly_tree = seed_result(cls.assembly, {"label": "pair", "components": {"left": {}, "right": {}}})
        (cls.root / "STEP" / "pair.step.json").write_text(json.dumps({
            "schemaVersion": 9, "documentHash": hashlib.sha256(cls.assembly.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        document = ezdxf.new()
        document.modelspace().add_lwpolyline([(0, 0), (20, 0), (20, 12), (0, 12)], close=True, dxfattribs={"layer": "OUTLINE"})
        document.saveas(str(cls.root / "DXF" / "plate.dxf"))
        (cls.root / "meshes" / "tetra.stl").write_text(STL, encoding="utf-8")
        (cls.root / "robots" / "arm.urdf").write_text(URDF, encoding="utf-8")
        cls.out = cls.base / "export"
        cls.result = export_views(str(cls.root), str(cls.out))
        cls.index = json.loads((cls.out / "export.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.env.stop()
        cls.tmp.cleanup()

    def object_bytes(self, entry: dict) -> bytes:
        data = (self.out / "objects" / entry["object"]).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), entry["object"])
        self.assertEqual(len(data), entry["bytes"])
        return data

    def test_names_every_file_and_views_every_cad_file_outside_hidden_and_build_folders(self) -> None:
        self.assertEqual(self.index["schema"], EXPORT_SCHEMA)
        self.assertEqual(self.index["views"], ["/DXF/plate.dxf", "/STEP/bracket.step", "/STEP/pair.step", "/meshes/tetra.stl", "/robots/arm.urdf"])
        self.assertEqual(self.result["views"], self.index["views"])
        self.assertEqual([(item["path"], item["kind"]) for item in self.index["files"]], [
            ("/DXF/plate.dxf", "dxf"), ("/STEP/bracket.step", "step"), ("/STEP/pair.step", "step"),
            ("/STEP/pair.step.json", "other"), ("/meshes/tetra.stl", "stl"), ("/robots/arm.urdf", "urdf"), ("/src/bracket.py", "other"),
        ])
        script = next(item for item in self.index["files"] if item["path"] == "/src/bracket.py")
        self.assertEqual(script["sha256"], hashlib.sha256(b"print('model')\n").hexdigest())
        self.assertEqual(script["bytes"], len(b"print('model')\n"))
        self.assertEqual(self.result["objects"], len(os.listdir(self.out / "objects")))
        self.assertEqual(self.result["bytes"], sum(os.path.getsize(self.out / "objects" / name) for name in os.listdir(self.out / "objects")))

    def test_records_what_the_viewer_answers_with_every_path_virtual(self) -> None:
        routes = self.index["routes"]
        self.assertEqual(routes["/__cad/server"][""]["start"], "/")
        self.assertFalse(routes["/__cad/server"][""]["autoReload"])
        self.assertEqual(routes["/__cad/catalog"][""]["entries"], [])
        row = routes["/__cad/catalog"]["/STEP/pair.step"]["entries"][0]
        self.assertEqual(row["file"], "/STEP/pair.step")
        self.assertEqual(row["kind"], "assembly")
        self.assertEqual(row["hash"], self.assembly_tree)
        self.assertTrue(row["url"].startswith(f"/__cad/store?file={self.assembly_tree}&documentHash="))
        self.assertEqual(routes["/__cad/artifact"]["/STEP/pair.step"], {"state": "compiled"})
        preview = routes["/__cad/preview"]["/STEP/pair.step"]
        self.assertEqual((preview["file"], preview["output"], preview["state"]), ("/STEP/pair.step", "/STEP/pair.step", "disconnected"))
        self.assertNotIn("feedCursor", preview)
        self.assertEqual(routes["/__cad/catalog"]["/robots/arm.urdf"]["entries"][0]["url"], "/__cad/asset?file=%2Frobots%2Farm.urdf&v=" + routes["/__cad/catalog"]["/robots/arm.urdf"]["entries"][0]["url"].split("&v=")[1])
        self.assertEqual(routes["/__cad/drawing"]["/DXF/plate.dxf"]["layers"][0]["name"], "OUTLINE")
        text = json.dumps(self.index)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(str(self.root.resolve()), text)

    def test_a_step_is_recorded_with_its_surfaces_so_the_client_never_asks_for_them(self) -> None:
        store = self.index["routes"]["/__cad/store"]
        descriptor = json.loads(self.object_bytes(store[f"/{self.assembly_tree}/assembly.json"]))
        self.assertEqual(descriptor["tree"], self.assembly_tree)
        self.assertEqual(len(descriptor["components"]), 2)
        for cid, component in descriptor["components"].items():
            self.assertEqual(component["surf"], f"components/{cid}.surf")
            entry = store[f"/{self.assembly_tree}/components/{cid}.surf"]
            self.assertEqual(entry["object"], component["surfaceObject"])
            self.assertEqual(entry["type"], "application/octet-stream")
            self.assertEqual(store[component["surfaceObject"]], entry)
            self.assertTrue(self.object_bytes(entry))
        part = json.loads(self.object_bytes(store[f"/{self.part_tree}/assembly.json"]))
        self.assertEqual(len(part["components"]), 1)

    def test_every_byte_the_client_fetches_is_an_object(self) -> None:
        asset = self.index["routes"]["/__cad/asset"]
        self.assertEqual(self.object_bytes(asset["/meshes/tetra.stl"]), STL.encode("utf-8"))
        self.assertEqual(asset["/meshes/tetra.stl"]["type"], "model/stl")
        self.assertEqual(asset["/STEP/bracket.step"]["type"], "application/step")
        self.assertEqual(self.object_bytes(asset["/robots/arm.urdf"]), URDF.encode("utf-8"))
        self.assertEqual(asset["/DXF/plate.dxf"]["type"], "application/dxf")
        # A sidecar the viewer serves beside its STEP, and nothing the viewer does not serve.
        self.assertIn("/STEP/pair.step.json", asset)
        self.assertNotIn("/src/bracket.py", asset)
        self.assertNotIn("/node_modules/dep.stl", asset)

    def test_a_named_file_alone_and_refusals(self) -> None:
        out = self.base / "one"
        result = export_views(str(self.root), str(out), ["DXF/plate.dxf"])
        self.assertEqual(result["views"], ["/DXF/plate.dxf"])
        index = json.loads((out / "export.json").read_text(encoding="utf-8"))
        self.assertEqual(list(index["routes"]["/__cad/catalog"]), ["", "/DXF/plate.dxf"])
        self.assertEqual(len(index["files"]), len(self.index["files"]))
        with self.assertRaisesRegex(ExportError, "outside"):
            export_views(str(self.root), str(out), [str(self.base / "elsewhere.step")])
        with self.assertRaisesRegex(ExportError, "not a CAD file"):
            export_views(str(self.root), str(out), ["src/bracket.py"])
        with self.assertRaisesRegex(ExportError, "no such file"):
            export_views(str(self.root), str(out), ["STEP/missing.step"])
        with self.assertRaisesRegex(ExportError, "nothing to export"):
            export_views(str(self.root / "src"), str(out))

    def test_the_command_prints_one_json_line_and_fails_loudly(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main([str(self.root), "--out", str(self.base / "cli"), "--file", "meshes/tetra.stl", "--json"])
        self.assertEqual(code, 0)
        line = json.loads(stdout.getvalue())
        self.assertEqual((line["ok"], line["views"], line["objects"]), (True, ["/meshes/tetra.stl"], 1))
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([str(self.root / "src"), "--out", str(self.base / "cli")])
        self.assertEqual(code, 1)
        self.assertIn("nothing to export", stderr.getvalue())
        self.assertEqual(export_module.DEFAULT_PROG, "cadgen viewer export")

"""Open in's Blender script (``cad_server/_internal/open_in_blender.py``) inside the real bpy.

A person's Blender is started as ``blender --python <script> -- <file>`` (``apps.open_file``); here a driver beside a
copy of the script sets ``sys.argv`` the way Blender leaves it and runs the script, under ``cad run``, which runs it in
the blender integration's environment (bpy 5.2.3 on Python 3.13), each time from the factory startup
scene. A two-node GLB and a one-triangle STL, written here, are each imported, the startup scene's cube, light and
camera removed and the imported root selected and active; an STL named ``Cube`` keeps its name; a path with spaces,
quotes, non-ASCII and a leading dash is read as it is. What it cannot open -- a 3MF, a file that is not there, a GLB
the importer refuses -- leaves the startup scene as it was and says why in the text block ``Open in Blender``. The
operators the script chooses from are the ones this bpy lists, never an attribute (there for any name). The suite is
the blender job's alone (``scripts/test/test-blender.sh``). Never reads ``models/``."""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

add_sources()

from cad_server._internal import apps, base, extras  # noqa: E402

TIMEOUT = 840.0  # the making of bpy's environment, the first time, downloads about 430 MB on Linux

STL = "solid {0}\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid {0}\n"
ODD = "-lead \u00fcber 'q' \"d\".stl"  # opened by its relative path: an argument that starts with a dash

DRIVER = '''
import importlib.util
import json
import runpy
import sys
from pathlib import Path

import bpy

here = Path(__file__).resolve().parent
script = str(here / "open_in_blender.py")
said = {}
for name in json.loads((here / "cases.json").read_text(encoding="utf-8")):
    bpy.ops.wm.read_factory_settings(use_empty=False)  # Blender as it starts: the cube, light and camera
    sys.argv = ["blender", "--python", script, "--", name]
    runpy.run_path(script, run_name="__main__")
    layer = bpy.context.view_layer
    text = bpy.data.texts.get("Open in Blender")
    said[name] = {"objects": sorted(obj.name for obj in bpy.context.scene.objects),
                  "selected": sorted(obj.name for obj in bpy.context.selected_objects),
                  "active": layer.objects.active.name if layer.objects.active else None,
                  "meshes": sorted(mesh.name for mesh in bpy.data.meshes),
                  "cameras": len(bpy.data.cameras), "lights": len(bpy.data.lights),
                  "text": text.as_string() if text else None}
spec = importlib.util.spec_from_file_location("open_in_blender", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.bpy = bpy
said["operators"] = sorted(module.operators(bpy.ops, ("wm", "import_mesh", "import_scene")) &
                           {"wm.stl_import", "import_mesh.stl", "import_scene.gltf", "wm.no_such_importer"})
said["any attribute"] = hasattr(bpy.ops.wm, "no_such_importer")
module.dialog("one\\ntwo")
said["dialog"] = sorted(module.operators(bpy.ops, ("open_in_blender",)))
print("OPENED " + json.dumps(said))
'''


def glb() -> bytes:
    """A GLB of a root node ``part`` holding ``part/face``, one triangle."""
    points = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
                "nodes": [{"name": "part", "children": [1]}, {"name": "part/face", "mesh": 0}],
                "meshes": [{"name": "face", "primitives": [{"attributes": {"POSITION": 0}}]}],
                "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                               "min": [0, 0, 0], "max": [1, 1, 0]}],
                "bufferViews": [{"buffer": 0, "byteLength": len(points)}], "buffers": [{"byteLength": len(points)}]}
    text = json.dumps(document).encode()
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(points), 0x004E4942) + points
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def _built_here() -> bool:
    try:
        extras.supported(("blender",), base.Installation.here().arch)
    except extras.Refused:
        return False
    return True


@unittest.skipUnless(_built_here(), "bpy has no build for this platform (an Intel Mac, Linux arm64)")
class OpenInBlenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.project = Path(tempfile.mkdtemp(prefix="open-in-blender-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.project, True)
        env = engine_daemon.watched({**os.environ}, cls.addClassCleanup)
        shutil.copy(apps.BLENDER_SCRIPT, cls.project / "open_in_blender.py")
        (cls.project / "driver.py").write_text(textwrap.dedent(DRIVER), encoding="utf-8")
        (cls.project / "part.glb").write_bytes(glb())
        (cls.project / "tri.stl").write_text(STL.format("tri"), encoding="utf-8")
        (cls.project / "Cube.stl").write_text(STL.format("Cube"), encoding="utf-8")
        (cls.project / ODD).write_text(STL.format("odd"), encoding="utf-8")
        (cls.project / "part.3mf").write_bytes(b"PK")
        (cls.project / "broken.glb").write_bytes(b"glTF" + b"\xff" * 16)
        cls.cases = {"glb": str(cls.project / "part.glb"), "stl": str(cls.project / "tri.stl"),
                     "cube": str(cls.project / "Cube.stl"), "odd": ODD, "3mf": str(cls.project / "part.3mf"),
                     "missing": str(cls.project / "gone.glb"), "broken": str(cls.project / "broken.glb")}
        (cls.project / "cases.json").write_text(json.dumps(list(cls.cases.values())), encoding="utf-8")
        cls.run_ = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", "driver.py"], env=env,
                                     cwd=cls.project, timeout=TIMEOUT)
        found = re.findall(r"^OPENED (.*)$", cls.run_.stdout, re.M)
        cls.said = json.loads(found[-1]) if cls.run_.returncode == 0 and found else None

    def setUp(self) -> None:
        self.assertIsNotNone(self.said, f"the driver failed:\n{self.run_.stdout[-4000:]}\n{self.run_.stderr[-4000:]}")

    def opened(self, case: str) -> dict:
        return self.said[self.cases[case]]

    def test_a_glb_is_imported_the_startup_scenes_objects_removed_its_root_selected(self) -> None:
        self.assertEqual(self.opened("glb"), {"objects": ["part", "part/face"], "selected": ["part"], "active": "part",
                                              "meshes": ["face"], "cameras": 0, "lights": 0, "text": None})

    def test_an_stl_is_imported_the_same_way(self) -> None:
        self.assertEqual(self.opened("stl"), {"objects": ["tri"], "selected": ["tri"], "active": "tri",
                                              "meshes": ["tri"], "cameras": 0, "lights": 0, "text": None})

    def test_a_models_name_is_its_own_though_the_startup_scene_held_it(self) -> None:
        # The startup cube is "Cube" and its mesh "Cube": they are set aside while the import runs, so an STL named
        # Cube is "Cube", not "Cube.001".
        self.assertEqual(self.opened("cube"), {"objects": ["Cube"], "selected": ["Cube"], "active": "Cube",
                                               "meshes": ["Cube"], "cameras": 0, "lights": 0, "text": None})

    def test_a_path_is_read_as_it_is_spaces_quotes_non_ascii_and_a_leading_dash(self) -> None:
        name = os.path.splitext(ODD)[0]
        self.assertEqual(self.opened("odd"), {"objects": [name], "selected": [name], "active": name,
                                              "meshes": [name], "cameras": 0, "lights": 0, "text": None})

    def assert_refused(self, case: str, why: str) -> None:
        said = self.opened(case)
        # The startup scene as Blender started it, and the reason in the file, where Blender shows it.
        self.assertEqual({key: said[key] for key in ("objects", "meshes", "cameras", "lights")},
                         {"objects": ["Camera", "Cube", "Light"], "meshes": ["Cube"], "cameras": 1, "lights": 1})
        self.assertTrue(said["text"].startswith("Open in Blender did not open the file.\n"), said["text"])
        self.assertIn(why, said["text"])
        self.assertIn("open_in_blender: Open in Blender did not open the file.", self.run_.stderr + self.run_.stdout)

    def test_a_file_it_does_not_import_leaves_the_startup_scene_and_says_why(self) -> None:
        self.assert_refused("3mf", f"{self.cases['3mf']} is not a GLB, glTF or STL file.")

    def test_a_file_that_is_not_there_leaves_the_startup_scene_and_says_why(self) -> None:
        self.assert_refused("missing", f"{self.cases['missing']} is not there.")

    def test_a_file_the_importer_refuses_leaves_the_startup_scene_and_says_why(self) -> None:
        self.assert_refused("broken", f"Blender could not import {self.cases['broken']}:\n")

    def test_the_importers_are_the_ones_this_blender_lists(self) -> None:
        # bpy 5.2.3 has the built-in STL importer and no STL add-on; any attribute of bpy.ops.wm is there, so an
        # attribute is never the test.
        self.assertEqual(self.said["operators"], ["import_scene.gltf", "wm.stl_import"])
        self.assertTrue(self.said["any attribute"])

    def test_the_dialog_that_says_why_registers_in_this_blender(self) -> None:
        self.assertEqual(self.said["dialog"], ["open_in_blender.said"])


if __name__ == "__main__":
    unittest.main()

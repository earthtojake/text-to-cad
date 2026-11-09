"""Open in's Blender script (``cad_server/_internal/open_in_blender.py``) inside the real bpy.

A person's Blender is started as ``blender --python <script> -- <file>`` (``apps.open_file``); here a driver beside a
copy of the script sets ``sys.argv`` the way Blender leaves it and runs the script, under ``cad run``, which runs it in
the blender integration's environment (bpy 5.2.3 on Python 3.13, without cad). A two-node GLB and a one-triangle STL,
written here, are each imported into the startup scene emptied of its cube, light and camera, the imported root
selected and active; a 3MF, which it does not import, leaves the scene as it was. The suite is the blender job's alone
(``scripts/test/test-blender.sh``). Never reads ``models/``."""

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

from cad.registry import INTEGRATIONS  # noqa: E402
from cad_server._internal import apps, base, extras  # noqa: E402

TIMEOUT = 840.0  # the making of bpy's environment, the first time, downloads about 430 MB on Linux

DRIVER = '''
import json
import runpy
import sys
from pathlib import Path

import bpy

script = str(Path(__file__).resolve().parent / "open_in_blender.py")
said = {}
for name in sys.argv[1:]:
    sys.argv = ["blender", "--background", "--python", script, "--", name]
    runpy.run_path(script, run_name="__main__")
    layer = bpy.context.view_layer
    said[Path(name).suffix] = {"objects": sorted(obj.name for obj in bpy.context.scene.objects),
                               "selected": sorted(obj.name for obj in bpy.context.selected_objects),
                               "active": layer.objects.active.name if layer.objects.active else None,
                               "cameras": len(bpy.data.cameras), "lights": len(bpy.data.lights)}
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
        extras.supported(INTEGRATIONS["blender"], base.Installation.here().arch)
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
        (cls.project / "tri.stl").write_text("solid tri\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\n"
                                             "vertex 0 1 0\nendloop\nendfacet\nendsolid tri\n", encoding="utf-8")
        (cls.project / "part.3mf").write_bytes(b"PK")
        cls.run_ = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", "driver.py",
                                      str(cls.project / "part.3mf"), str(cls.project / "part.glb"),
                                      str(cls.project / "tri.stl")], env=env, cwd=cls.project, timeout=TIMEOUT)
        found = re.findall(r"^OPENED (.*)$", cls.run_.stdout, re.M)
        cls.said = json.loads(found[-1]) if cls.run_.returncode == 0 and found else None

    def setUp(self) -> None:
        self.assertIsNotNone(self.said, f"the driver failed:\n{self.run_.stdout[-4000:]}\n{self.run_.stderr[-4000:]}")

    def test_a_glb_is_imported_into_the_emptied_startup_scene_its_root_selected(self) -> None:
        self.assertEqual(self.said[".glb"], {"objects": ["part", "part/face"], "selected": ["part"], "active": "part",
                                             "cameras": 0, "lights": 0})

    def test_an_stl_is_imported_the_same_way(self) -> None:
        self.assertEqual(self.said[".stl"], {"objects": ["tri"], "selected": ["tri"], "active": "tri",
                                             "cameras": 0, "lights": 0})

    def test_a_file_it_does_not_import_leaves_the_startup_scene(self) -> None:
        self.assertEqual(self.said[".3mf"]["objects"], ["Camera", "Cube", "Light"])
        self.assertIn("is not a GLB, glTF or STL file here", self.run_.stderr + self.run_.stdout)


if __name__ == "__main__":
    unittest.main()

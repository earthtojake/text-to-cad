"""``cad.mujoco.spec``: a document as a ``mujoco.MjSpec`` -- an MJCF path read as it is; a STEP, an xbf and a
build123d shape described and written as the MJCF export writes them; a scene attaching one, compiling and
saved to a file that MuJoCo reads back with every mesh found, whether the meshes went to a folder the caller
named or to the engine's cache, which keeps one folder per content; and what is no document refused by name.
Each in a fresh temporary folder, the cache one of its own."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import textwrap
import unittest
import warnings
from pathlib import Path
from unittest import mock

import mujoco
import numpy as np

from cad.engine import api
from cad.engine.model import model as declared
from cad.mujoco import spec

# A base and an arm on an elbow about +Y through (40, 0, 20) mm, connected at 30 degrees, raised by a
# state to 90; its xbf keeps the mechanism, its STEP the parts alone.
HINGE = """
import build123d as bd
from cad.build123d import mechanism_state
from cad.engine import step, xbf


@xbf("XBF/hinge.xbf")
@step(out="hinge.step")
def hinge():
    base = bd.Box(100, 60, 20)
    base.label = "base"
    arm = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("mount", arm, bd.Location())
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=30)
    root = bd.Compound(children=[base, arm], label="hinge")
    mechanism_state(root, "raised", elbow=90)
    return root
"""

# A model whose body takes its child's spec, inside the build: the child's handle holds its shape here.
INSIDE = """
import json
from pathlib import Path

import build123d as bd
from cad.engine import model
from cad.mujoco import spec


@model
def finger():
    shape = bd.Box(30, 10, 10)
    shape.label = "finger"
    return shape


@model
def hand():
    made = spec(finger()).compile()
    Path("inside.json").write_text(json.dumps([made.nbody, made.ngeom]), encoding="utf-8")
    return bd.Box(80, 60, 10)
"""


class SpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="mujoco-spec-")).resolve()
        cls.models = cls.root / "models"
        cls.models.mkdir()
        (cls.models / "hinge.py").write_text(textwrap.dedent(HINGE), encoding="utf-8")
        api.build_script(cls.models / "hinge.py", daemon=False)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="scene-", dir=self.root)).resolve()
        self.cache = self.folder / "cache"
        patched = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.cache)})
        patched.start()
        self.addCleanup(patched.stop)
        here = os.getcwd()
        os.chdir(self.folder)
        self.addCleanup(os.chdir, here)

    def scene(self, child: mujoco.MjSpec, prefix: str = "hinge/") -> mujoco.MjSpec:
        """A scene with a floor and ``child`` attached above it, saved and read back by MuJoCo."""
        scene = mujoco.MjSpec()
        scene.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[1, 1, 0.1])
        frame = scene.worldbody.add_frame(pos=[0.5, 0, 0.1])
        with warnings.catch_warnings():
            # MuJoCo says the scene keeps its own integrator over the fragment's implicitfast.
            warnings.filterwarnings("ignore", "Attach conflict", UserWarning)
            scene.attach(child, prefix=prefix, frame=frame)
            scene.compile()
        scene.to_file("scene.xml")
        return scene

    def test_an_mjcf_path_is_read_as_it_is(self) -> None:
        out = self.folder / "robot" / "hinge.xml"
        api.export(self.models / "XBF/hinge.xbf", out, daemon=False, progress=False)
        made = spec(out)
        self.assertEqual(made.meshdir, "assets")
        model = made.compile()
        self.assertEqual(model.joint("elbow").type, mujoco.mjtJoint.mjJNT_HINGE)
        self.assertEqual(model.nkey, 1)
        with self.assertRaisesRegex(ValueError, "its meshes are its files"):
            spec(out, tolerance=0.1)

    def test_an_xbf_attaches_and_a_saved_scene_finds_its_meshes_in_the_cache(self) -> None:
        made = spec(self.models / "XBF/hinge.xbf")
        folders = list((self.cache / "mjcf").iterdir())
        self.assertEqual(len(folders), 1)
        # The spec names each mesh by its absolute path in the cache: the files outlive the call.
        files = [Path(mesh.file) for mesh in made.meshes]
        self.assertEqual(sorted(path.name for path in files), ["hinge_arm.stl", "hinge_base.stl"])
        self.assertTrue(all(path.is_absolute() and path.is_file() and path.parent == folders[0] / "assets"
                            for path in files))
        self.scene(made)
        model = mujoco.MjModel.from_xml_path(str(self.folder / "scene.xml"))
        self.assertEqual(model.nmesh, 2)
        # Its classes and its keys came with it, prefixed.
        self.assertEqual(model.geom("hinge/arm").group, 2)
        self.assertEqual(model.geom("hinge/arm_collision").group, 3)
        np.testing.assert_allclose(model.key("hinge/raised").qpos, [np.radians(60)], atol=1e-5)  # as MuJoCo saves it
        # The same document lands in the same folder, files untouched; another (its STEP, no joints) in its own.
        stamps = {path: path.stat().st_mtime_ns for path in folders[0].rglob("*")}
        spec(self.models / "XBF/hinge.xbf", tolerance=0.05)  # a box meshes the same at any tolerance
        self.assertEqual({path: path.stat().st_mtime_ns for path in folders[0].rglob("*")}, stamps)
        spec(self.models / "hinge.step")
        self.assertEqual(len(list((self.cache / "mjcf").iterdir())), 2)

    def test_a_step_with_assets_named_writes_them_there_and_the_scene_beside_them_moves_with_them(self) -> None:
        made = spec(self.models / "hinge.step", assets="assets")
        # A STEP carries no mechanism: its parts hang from the world, fixed.
        self.assertEqual(made.compile().njnt, 0)
        self.assertEqual(sorted(mesh.file for mesh in made.meshes), ["assets/hinge_arm.stl", "assets/hinge_base.stl"])
        self.assertTrue((self.folder / "assets" / "hinge.xml").is_file())
        self.scene(made)
        moved = self.root / f"{self.folder.name}-moved"
        shutil.copytree(self.folder, moved, ignore=shutil.ignore_patterns("cache"))
        model = mujoco.MjModel.from_xml_path(str(moved / "scene.xml"))
        self.assertEqual(model.nmesh, 2)

    def test_a_build123d_shape_is_described_here_and_what_is_no_document_is_refused_by_name(self) -> None:
        import build123d as bd

        box = bd.Box(100, 50, 20)
        box.label = "block"
        model = spec(box).compile()
        self.assertEqual((model.nbody, model.njnt, model.nmesh), (2, 0, 1))
        np.testing.assert_allclose(model.geom_rbound.max(), np.linalg.norm([0.05, 0.025, 0.01]), rtol=1e-6)

        # Inside a build, a child's handle is its shape, described here.
        (self.folder / "hand.py").write_text(textwrap.dedent(INSIDE), encoding="utf-8")
        api.build_script(self.folder / "hand.py", ["hand"], daemon=False)
        self.assertEqual(json.loads((self.folder / "inside.json").read_text(encoding="utf-8")), [2, 2])

        @declared
        def block():
            return bd.Box(1, 1, 1)

        for thing, words in ((block, "call it"), (self.folder / "part.stl", "is a mesh"),
                             (self.folder / "notes.txt", "spec reads an MJCF"), (42, "not int")):
            with self.subTest(thing=thing), self.assertRaisesRegex((TypeError, ValueError), words):
                spec(thing)


if __name__ == "__main__":
    unittest.main()

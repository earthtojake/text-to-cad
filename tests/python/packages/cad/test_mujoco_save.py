"""A MuJoCo function (``cad.mujoco``): a robot's spec made with ``spec``, the simulator's choices made on it in
MuJoCo's own API and by the helpers that find a part by its label path (``collisions``, ``fit``), and the spec
written by ``save`` as a folder that travels. The toy hinge a person writes -- a model and a MuJoCo function, two
files -- run as written; a capsule fitted to the arm equal to the one a collision declared on the model writes; the
saved folder loaded after it is moved; the spec handed to ``save`` still attachable after it; the meshes a
previous save wrote and this one does not name removed, and nothing else; ``scene.xml`` written once and never
over, and none beside a spec with a floor of its own; a body weighed by its collision told so once; and what is
no spec, no part, two parts or no solid refused by name. Each in a fresh temporary folder, its
cache a folder of its own."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import warnings
from pathlib import Path
from unittest import mock

import mujoco
import numpy as np

from cad.mujoco import collisions, fit, save, spec

# The toy of the MuJoCo function's design: a model with only the hardware's facts, and a MuJoCo function with the
# simulator's choices, which saves the robot's file.
MODEL = """
import build123d as bd
from bd_materials import metals
from cad import model
from cad.build123d import frame, limits, mass, mechanism_state, point_mass


@model
def hinge():
    return made()


def made():
    base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    base.material = arm.material = metals.aluminum()

    elbow = bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, -1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("elbow", arm, elbow.location)
    elbow.connect_to(arm.joints["elbow"], angle=0)

    frame(arm, "tool", bd.Pos(120, 0, 5))
    point_mass(base, 60, bd.Pos(0, 0, 10), name="motor")
    mass(base, 400)

    assembly = bd.Compound(children=[base, arm], label="hinge")
    limits(assembly, "elbow", effort=2, velocity=1.5)
    mechanism_state(assembly, "open", elbow=90)
    return assembly
"""

FUNCTION = """
import mujoco
from cad.mujoco import collisions, fit, save, spec

from hinge import hinge


def hinge_mujoco() -> mujoco.MjSpec:
    s = spec(hinge())

    elbow = s.joint("elbow")
    elbow.armature = 0.002
    elbow.damping = [0.1, 0, 0]

    fit(s, "arm", "capsule")
    for geom in collisions(s, "arm"):
        geom.friction = [0.9, 0.005, 0.0001]

    servo = s.add_actuator(name="elbow", target="elbow", trntype=mujoco.mjtTrn.mjTRN_JOINT)
    servo.set_to_position(kp=10, kv=1, inheritrange=True)
    s.add_key(name="reach", qpos=[1.0], ctrl=[1.0])
    return s


if __name__ == "__main__":
    save(hinge_mujoco(), "mujoco/hinge.xml")
"""

# What ``collision(arm, "capsule")`` on the model writes for the toy's arm today (the MJCF export's geom
# ``arm_collision``): its size, its place and its turn in the arm's body.
CAPSULE = {"size": (0.01, 0.05, 0.0), "pos": (-0.005, 0.06, 0.0), "quat": (0.5, -0.5, -0.5, -0.5)}


def _png_1x1() -> bytes:
    """A one-pixel RGBA PNG: what a texture is to MuJoCo."""
    import struct
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixel = zlib.compress(b"\x00" + bytes((200, 40, 40, 255)))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixel) + chunk(b"IEND", b"")


class MuJoCoFunctionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="mujoco-save-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        (self.folder / "hinge.py").write_text(textwrap.dedent(MODEL), encoding="utf-8")
        (self.folder / "hinge_mujoco.py").write_text(textwrap.dedent(FUNCTION), encoding="utf-8")
        cache = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)
        here = os.getcwd()
        os.chdir(self.folder)
        self.addCleanup(os.chdir, here)

    def hinge(self) -> mujoco.MjSpec:
        """The toy's robot as a spec, made here from its shape (the model's body undecorated)."""
        import importlib.util

        found = importlib.util.spec_from_file_location("toy_hinge", self.folder / "hinge.py")
        module = importlib.util.module_from_spec(found)
        found.loader.exec_module(module)
        return spec(module.made())

    def saved(self, made: mujoco.MjSpec, path: str | Path) -> str:
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            save(made, path)
        return said.getvalue()

    def assert_capsule(self, geom: object) -> None:
        self.assertEqual(geom.type, mujoco.mjtGeom.mjGEOM_CAPSULE)
        for key, wanted in CAPSULE.items():
            np.testing.assert_allclose(np.asarray(getattr(geom, key), dtype=float), wanted, atol=1e-6, err_msg=key)

    def test_the_toy_runs_as_written_and_its_folder_loads_after_it_is_moved(self) -> None:
        run = subprocess.run([sys.executable, "hinge_mujoco.py"], cwd=self.folder, capture_output=True, text=True,
                             timeout=600)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        out = self.folder / "mujoco" / "hinge.xml"
        self.assertIn(f"wrote {out}", run.stdout)
        self.assertNotIn("warning:", run.stdout, "the toy is healthy")
        self.assertEqual(sorted(path.name for path in (out.parent / "assets").iterdir()),
                         [".hinge.xml.meshes", "hinge_arm.stl", "hinge_base.stl"])
        moved = Path(tempfile.mkdtemp(prefix="moved-", dir=self.folder)) / "robot"
        shutil.move(out.parent, moved)
        model = mujoco.MjModel.from_xml_path(str(moved / "hinge.xml"))
        self.assertEqual((model.nmesh, model.nu, model.nkey), (2, 1, 2))
        self.assert_capsule(model.geom("arm_collision"))
        np.testing.assert_allclose(model.geom("arm_collision").friction, [0.9, 0.005, 0.0001])
        np.testing.assert_allclose((model.dof_armature[0], model.dof_damping[0]), (0.002, 0.1))
        np.testing.assert_allclose(model.jnt_actfrcrange[0], (-2, 2))
        # Started at the key the function added, the servo holds the arm there under gravity.
        data = mujoco.MjData(model)
        mujoco.mj_resetDataKeyframe(model, data, model.key("reach").id)
        for _step in range(2000):
            mujoco.mj_step(model, data)
        self.assertAlmostEqual(float(data.qpos[0]), 1.0, delta=0.01)
        self.assertEqual(mujoco.MjModel.from_xml_path(str(moved / "scene.xml")).nmesh, 2)

    def test_fit_makes_the_declared_capsule_and_collisions_finds_a_part_by_its_label_path(self) -> None:
        made = self.hinge()
        [mesh] = collisions(made, "hinge/arm")
        self.assertEqual((mesh.name, mesh.type), ("arm_collision", mujoco.mjtGeom.mjGEOM_MESH))
        mesh.friction = [0.7, 0.005, 0.0001]
        [geom] = fit(made, "arm", "capsule")
        self.assert_capsule(geom)
        # The geom in the mesh's place keeps its name, its class and its contact settings; no mesh is left on it.
        self.assertEqual((geom.name, geom.meshname, geom.classname.name), ("arm_collision", "", "collision"))
        np.testing.assert_allclose(geom.friction, [0.7, 0.005, 0.0001])
        self.assertEqual([found.name for found in collisions(made, "arm")], ["arm_collision"])
        self.assertEqual(len(made.geoms), 4)
        model = made.compile()
        self.assert_capsule(model.geom("arm_collision"))
        # A box and a sphere replace it again, fitted to the same solid.
        [box] = fit(made, "arm", "box")
        np.testing.assert_allclose(sorted(box.size), [0.005, 0.01, 0.06], atol=1e-9)
        [ball] = fit(made, "arm", "sphere")
        self.assertAlmostEqual(float(ball.size[0]), float(np.linalg.norm([0.06, 0.01, 0.005])), places=9)
        self.assertEqual(len(made.geoms), 4)

    def test_what_names_no_spec_no_part_two_parts_or_no_solid_is_refused_by_name(self) -> None:
        import build123d as bd

        from cad.engine.describe import fit as kernel_fit
        from cad.engine.description import DescriptionError

        wheels = []
        for side in ("left", "right"):
            wheel = bd.Cylinder(30, 10)
            wheel.label = "wheel"
            wheels.append(bd.Compound(children=[wheel], label=side))
        made = spec(bd.Compound(children=wheels, label="cart"))
        with self.assertRaisesRegex(ValueError, r"'wheel' names 2 parts of cart: cart/left/wheel, cart/right/wheel; "
                                                r"name one by its path"):
            fit(made, "wheel", "cylinder")
        self.assertEqual([geom.name for geom in collisions(made, "right/wheel")], ["wheel_collision_2"])
        with self.assertRaisesRegex(ValueError, r"cart has no part 'whel'; its parts: cart/left/wheel, "
                                                r"cart/right/wheel"):
            collisions(made, "whel")
        with self.assertRaisesRegex(ValueError, "a primitive is one of box, sphere, cylinder, capsule; "
                                                r"decompose\(spec, part\) cuts"):
            fit(made, "left/wheel", "decomposed")
        with self.assertRaisesRegex(ValueError, "not made by cad.mujoco.spec"):
            collisions(made.copy(), "left/wheel")
        with self.assertRaisesRegex(TypeError, "takes the mujoco.MjSpec cad.mujoco.spec made, not str"):
            fit("robot.xml", "arm", "box")
        with self.assertRaisesRegex(TypeError, "save writes a mujoco.MjSpec .*, not dict"):
            save({"model": "hinge"}, "robot.xml")
        # Read from an MJCF, a spec has meshes and no solids: no primitive is fitted to one.
        self.saved(made, "cart/cart.xml")
        read = spec(self.folder / "cart" / "cart.xml")
        self.assertEqual(sorted(geom.name for geom in collisions(read, "wheel")),
                         ["wheel_collision", "wheel_collision_2"])
        with self.assertRaisesRegex(ValueError, "this spec was read from an MJCF, which holds meshes and no solids"):
            fit(read, "wheel", "cylinder")
        # A part read from a mesh file has no solid either, refused as a declared collision is.
        with self.assertRaisesRegex(DescriptionError, "part 'scan' is a mesh: no box is fitted to it without its B-rep"):
            kernel_fit(None, "scan", "box")

    def test_save_copies_the_spec_and_removes_only_the_meshes_its_last_save_wrote(self) -> None:
        made = self.hinge()
        grid = self.folder / "textures" / "grid.png"
        grid.parent.mkdir()
        grid.write_bytes(_png_1x1())
        made.add_texture(name="grid", type=mujoco.mjtTexture.mjTEXTURE_2D, file=str(grid))
        made.add_material(name="checker", textures=["", "grid"])
        out = self.folder / "robot" / "hinge.xml"
        said = self.saved(made, "robot/hinge.xml")  # relative: the working directory's
        self.assertIn("wrote scene.xml beside it", said)
        self.assertTrue(said.endswith(f"wrote {out}\n"), said)
        assets = out.parent / "assets"
        self.assertEqual(sorted(path.name for path in assets.iterdir()),
                         [".hinge.xml.meshes", "grid.png", "hinge_arm.stl", "hinge_base.stl"])
        # A file of the person's in the folder, and a scene they edited, are theirs: never removed or written over.
        (assets / "floor.png").write_bytes(_png_1x1())
        (out.parent / "scene.xml").write_text("<mujoco/>\n", encoding="utf-8")
        # Saved again with the base gone: its mesh, which the last save wrote, goes; nothing else does.
        made.delete(made.geom("base"))
        made.delete(made.geom("base_collision"))
        made.delete(made.mesh("base"))
        said = self.saved(made, out)
        self.assertIn("removed 1 mesh from assets/ that the last save of hinge.xml wrote", said)
        self.assertNotIn("scene.xml", said)
        self.assertEqual(sorted(path.name for path in assets.iterdir()),
                         [".hinge.xml.meshes", "floor.png", "grid.png", "hinge_arm.stl"])
        self.assertEqual((out.parent / "scene.xml").read_text(encoding="utf-8"), "<mujoco/>\n")
        self.assertIn('meshdir="assets" texturedir="assets"', out.read_text(encoding="utf-8"))
        moved = self.folder / "elsewhere"
        shutil.move(out.parent, moved)
        model = mujoco.MjModel.from_xml_path(str(moved / "hinge.xml"))
        self.assertEqual((model.nmesh, model.ntex), (1, 1))
        # The spec handed in still names its files where they are: a scene attaches and compiles it after.
        self.assertTrue(all(Path(mesh.file).is_absolute() for mesh in made.meshes))
        scene = mujoco.MjSpec()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "Attach conflict", UserWarning)
            scene.attach(made, prefix="hinge/", frame=scene.worldbody.add_frame())
            self.assertEqual(scene.compile().nmesh, 1)

    def test_a_body_weighed_by_its_collision_is_told_once_that_the_choice_sets_its_mass(self) -> None:
        import build123d as bd

        block = bd.Box(40, 20, 10)
        block.label = "block"  # no material: no density, so no <inertial>
        made = spec(block)
        with self.assertWarnsRegex(UserWarning, r"body 'block' has no <inertial>, so MuJoCo weighs it from its geoms: "
                                                r"the collision just chosen for it \('block_collision'\) now sets its "
                                                r"mass and inertia. Give its parts a material with a density, or "
                                                r"declare mass\(\) on the model") as caught:
            fit(made, "block", "box")
        self.assertEqual(caught.filename, __file__, "said at the call in the MuJoCo function")
        with warnings.catch_warnings(record=True) as again:
            warnings.simplefilter("always")
            fit(made, "block", "capsule")
        self.assertEqual(again, [], "once per body")

    def test_a_spec_with_a_floor_of_its_own_is_a_scene_and_gets_no_scene_beside_it(self) -> None:
        made = self.hinge()
        made.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[1, 1, 0.1])
        said = self.saved(made, "pick/pick.xml")
        self.assertNotIn("scene.xml", said)
        self.assertEqual(sorted(path.name for path in (self.folder / "pick").iterdir()), ["assets", "pick.xml"])

    def test_a_spec_mujoco_refuses_is_refused_in_its_words_and_nothing_is_written(self) -> None:
        made = self.hinge()
        made.geom("arm").meshname = "missing"
        with self.assertRaisesRegex(ValueError, "missing"):
            save(made, "broken/hinge.xml")
        self.assertEqual(list((self.folder / "broken").iterdir()), [])


if __name__ == "__main__":
    unittest.main()

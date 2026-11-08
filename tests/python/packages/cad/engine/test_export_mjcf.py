"""MJCF as an export of every document (``export/mjcf.py``): a robot description written as Menagerie lays
a robot out -- the exact text of a small hand-built one, its meshes binary STLs in metres beside it, the
same bytes written twice, and MuJoCo compiling it to the bodies, masses and keys it describes; a loop
refused by name, and a mesh file refused as a source; and a jointed model built by the engine and
exported to ``.xml``, its bodies standing where the mechanism puts its links, as built and at a state."""

from __future__ import annotations

import math
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

import mujoco
import numpy as np

from cad.engine import api, document, mechanism
from cad.engine.description import Collision, Description, Geometry, Inertial, Joint, Link, Mesh, Pose, Visual
from cad.engine.export import ExportRefused, kind_of, refused
from cad.engine.export.mjcf import write_description


def _frame(x: float = 0, y: float = 0, z: float = 0, about: str | None = None, angle: float = 0.0) -> np.ndarray:
    found = np.eye(4)
    found[:3, 3] = (x, y, z)
    c, s = math.cos(angle), math.sin(angle)
    if about == "x":
        found[1:3, 1:3] = [[c, -s], [s, c]]
    elif about == "y":
        found[0, 0], found[0, 2], found[2, 0], found[2, 2] = c, s, -s, c
    return found


# A shoulder 0.2 m up whose axis is the world's -Y (its frame turned a quarter about X), an arm on it
# 0.3 m long, and a finger at the arm's tip whose knuckle follows the shoulder at half its angle plus 0.1.
SHOULDER = _frame(0, 0, 0.2, "x", -math.pi / 2)
TIP = _frame(0.3, 0, 0)


def arm(loops: tuple[str, ...] = ()) -> Description:
    tetrahedron = Mesh("k1", "link", np.array([[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0], [0, 0, 0.1]], np.float32),
                       np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], np.uint32))
    red = (0.9, 0.1, 0.1, 1.0)
    world = Link("world", np.eye(4), visuals=[
        Visual("base", Geometry("box", _frame(0, 0, 0.05), size=(0.4, 0.2, 0.1)), (0.5, 0.5, 0.5, 1.0), "steel")])
    upper = Link("arm", SHOULDER,
                 visuals=[Visual("arm", Geometry("mesh", np.eye(4), mesh="k1"), red, "paint")],
                 collisions=[Collision("arm", Geometry("capsule", _frame(0.15, 0, 0, "y", math.pi / 2),
                                                       size=(0.02, 0.3)))],
                 inertial=Inertial(2.0, np.array([0.15, 0.0, 0.0]), np.diag([0.001, 0.016, 0.016])),
                 frames={"tip": TIP})
    finger = Link("finger", SHOULDER @ TIP,
                  visuals=[Visual("finger", Geometry("mesh", np.eye(4), mesh="k1"), red, "paint")],
                  inertial=Inertial(0.5, np.array([0.05, 0.0, 0.0]),
                                    np.array([[2e-4, 1e-5, 0], [1e-5, 4e-4, 0], [0, 0, 5e-4]])))
    joints = [Joint("shoulder", "revolute", "world", "arm", SHOULDER, limits=((-1.0, 1.5),), as_built=(0.0,)),
              Joint("knuckle", "revolute", "arm", "finger", TIP, limits=((-0.5, 0.75),), as_built=(0.0,),
                    follows=("shoulder", 0.5, 0.1))]
    return Description("arm", [world, upper, finger], joints, meshes={"k1": tetrahedron},
                       poses=[Pose("raised", {"shoulder": 1.2})], loops=loops)


GOLDEN = """\
<mujoco model="arm">
  <compiler angle="radian" meshdir="assets" autolimits="true"/>

  <option integrator="implicitfast"/>

  <default>
    <default class="arm">
      <default class="visual">
        <geom contype="0" conaffinity="0" group="2"/>
      </default>
      <default class="collision">
        <geom group="3"/>
      </default>
    </default>
  </default>

  <asset>
    <material name="steel" rgba="0.5 0.5 0.5 1"/>
    <material name="paint" rgba="0.9 0.1 0.1 1"/>
    <mesh name="link" file="arm_link.stl"/>
  </asset>

  <worldbody>
    <geom class="visual" type="box" size="0.2 0.1 0.05" name="base" material="steel" pos="0 0 0.05"/>
    <body name="arm" childclass="arm" pos="0 0 0.2" quat="0.707106781 -0.707106781 0 0">
      <inertial pos="0.15 0 0" mass="2" diaginertia="0.001 0.016 0.016"/>
      <joint name="shoulder" type="hinge" axis="0 0 1" range="-1 1.5"/>
      <geom class="visual" type="mesh" mesh="link" name="arm" material="paint"/>
      <geom class="collision" type="capsule" size="0.02 0.15" name="arm_collision" pos="0.15 0 0" \
quat="0.707106781 0 0.707106781 0"/>
      <site name="tip" pos="0.3 0 0"/>
      <body name="finger" pos="0.3 0 0">
        <inertial pos="0.05 0 0" quat="0.999689584 0 0 -0.0249145848" mass="0.5" \
diaginertia="0.000199501244 0.000400498756 0.0005"/>
        <joint name="knuckle" type="hinge" axis="0 0 1" range="-0.5 0.75"/>
        <geom class="visual" type="mesh" mesh="link" name="finger" material="paint"/>
      </body>
    </body>
  </worldbody>

  <equality>
    <joint joint1="knuckle" joint2="shoulder" polycoef="0.1 0.5 0 0 0"/>
  </equality>

  <keyframe>
    <key name="raised" qpos="1.2 0.7"/>
  </keyframe>
</mujoco>
"""


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="export-mjcf-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)


class HandBuiltTest(_Folder):
    def test_a_description_is_written_as_menagerie_lays_a_robot_out_and_compiles_to_what_it_describes(self) -> None:
        path = self.folder / "arm.xml"
        written = write_description(arm(), path)
        self.assertEqual(written, [path, self.folder / "assets" / "arm_link.stl"])
        self.assertEqual(path.read_text(encoding="utf-8"), GOLDEN)
        # The mesh: a binary STL in metres, its header naming it, its triangles in order, normals from the corners.
        data = (self.folder / "assets" / "arm_link.stl").read_bytes()
        self.assertEqual(data[:80].rstrip(), b"arm/link")
        self.assertEqual(len(data), 84 + 4 * 50)
        rows = np.frombuffer(data[84:], dtype=np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)),
                                                         ("attribute", "<u2")]))
        np.testing.assert_allclose(rows["corners"][3], [[0.1, 0, 0], [0, 0.1, 0], [0, 0, 0.1]], atol=1e-7)
        np.testing.assert_allclose(rows["normal"][0], [0, 0, -1], atol=1e-7)
        # Written again, elsewhere and in place: the same bytes, and in place nothing moved.
        again = self.folder / "again" / "arm.xml"
        write_description(arm(), again)
        self.assertEqual(again.read_bytes(), path.read_bytes())
        self.assertEqual((again.parent / "assets" / "arm_link.stl").read_bytes(), data)
        before = path.stat().st_mtime_ns, (self.folder / "assets" / "arm_link.stl").stat().st_mtime_ns
        write_description(arm(), path)
        self.assertEqual((path.stat().st_mtime_ns, (self.folder / "assets" / "arm_link.stl").stat().st_mtime_ns),
                         before)

        model = mujoco.MjModel.from_xml_path(str(path))
        self.assertEqual((model.nbody, model.njnt, model.ngeom, model.nkey, model.neq, model.nsite),
                         (3, 2, 4, 1, 1, 1))
        np.testing.assert_allclose(model.body_mass, [0, 2.0, 0.5])
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        description = arm()
        for link in description.links[1:]:
            body = model.body(link.name).id
            np.testing.assert_allclose(data.xpos[body], link.frame[:3, 3], atol=1e-9)
            np.testing.assert_allclose(data.xmat[body].reshape(3, 3), link.frame[:3, :3], atol=1e-8)
        np.testing.assert_allclose(data.site("tip").xpos, (SHOULDER @ TIP)[:3, 3], atol=1e-9)
        # The key: the shoulder at 1.2, the knuckle where the coupling puts it.
        np.testing.assert_allclose(model.key("raised").qpos, [1.2, 0.5 * 1.2 + 0.1])
        mujoco.mj_resetDataKeyframe(model, data, model.key("raised").id)
        mujoco.mj_forward(model, data)
        turned = SHOULDER @ _rotation_z(1.2)
        np.testing.assert_allclose(data.xpos[model.body("finger").id], (turned @ TIP)[:3, 3], atol=1e-9)

    def test_a_loop_is_refused_by_name_and_nothing_is_written(self) -> None:
        with self.assertRaisesRegex(ExportRefused, "loop through shoulder"):
            write_description(arm(loops=("shoulder",)), self.folder / "arm.xml")
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_xml_and_mjcf_are_the_kind_and_a_mesh_file_is_no_source_of_one(self) -> None:
        self.assertEqual((kind_of("robot.xml"), kind_of("robot.MJCF")), ("mjcf", "mjcf"))
        self.assertEqual(refused("part.stl", "robot.xml"),
                         "part.stl is a mesh: it has no B-rep, and no MJCF export is made from one")
        (self.folder / "part.glb").write_bytes(b"glTF")  # refused by its suffix, before it is read
        with self.assertRaisesRegex(ExportRefused, "no MJCF export is made from one"):
            api.export(self.folder / "part.glb", self.folder / "robot.xml", daemon=False, progress=False)
        self.assertFalse((self.folder / "robot.xml").exists())


def _rotation_z(angle: float) -> np.ndarray:
    found = np.eye(4)
    c, s = math.cos(angle), math.sin(angle)
    found[:2, :2] = [[c, -s], [s, c]]
    return found


# The hinge of ``test_kinematics``: a base and an arm on an elbow about +Y through (40, 0, 20) mm,
# connected at 30 degrees, with a state raising it to 90.
HINGE = """
import build123d as bd
from cad.build123d import mechanism_state
from cad.engine import xbf


@xbf("XBF/hinge.xbf")
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
    mechanism_state(root, "flat", elbow=0)
    return root
"""


class EngineTest(_Folder):
    def test_a_built_hinge_exports_to_an_mjcf_whose_bodies_move_as_its_links_do(self) -> None:
        (self.folder / "hinge.py").write_text(textwrap.dedent(HINGE), encoding="utf-8")
        api.build_script(self.folder / "hinge.py", daemon=False)
        xbf = self.folder / "XBF/hinge.xbf"
        out = self.folder / "robot" / "hinge.xml"
        [written] = api.export(xbf, out, daemon=False, progress=False)
        self.assertEqual(written.kind, "mjcf")
        self.assertTrue(any((out.parent / "assets").glob("*.stl")))
        model = mujoco.MjModel.from_xml_path(str(out))
        self.assertEqual(model.joint("elbow").type, mujoco.mjtJoint.mjJNT_HINGE)
        # Limits around the as-built 30 degrees.
        np.testing.assert_allclose(model.jnt_range[model.joint("elbow").id], np.radians([-40, 90]), atol=1e-9)
        data = mujoco.MjData(model)
        kinematics = document.Loaded(xbf).structure()["kinematics"]
        names = [link["name"] for link in kinematics["links"]]
        built = mechanism.link_worlds(kinematics, {"elbow": (30.0,)})
        # As built, the arm's body is its joint's frame: on the elbow's axis, its Z the axis (+Y).
        mujoco.mj_forward(model, data)
        arm = model.body("arm").id
        np.testing.assert_allclose(data.xmat[arm].reshape(3, 3)[:, 2], [0, 1, 0], atol=1e-9)
        np.testing.assert_allclose(data.xpos[arm][[0, 2]], [0.04, 0.02], atol=1e-9)
        rest = {name: _metres(data.xpos[model.body(name).id], data.xmat[model.body(name).id]) for name in names}
        # At each state, every body moved from where it stood as its link moved from where it was built.
        for state, degrees in (("raised", 90.0), ("flat", 0.0)):
            mujoco.mj_resetDataKeyframe(model, data, model.key(state).id)
            mujoco.mj_forward(model, data)
            np.testing.assert_allclose(data.qpos, [math.radians(degrees - 30)], atol=1e-9)
            posed = mechanism.link_worlds(kinematics, {"elbow": (degrees,)})
            for at, name in enumerate(names):
                body = model.body(name).id
                moved = _metres(data.xpos[body], data.xmat[body]) @ np.linalg.inv(rest[name])
                expected = posed[at] @ np.linalg.inv(built[at])
                expected[:3, 3] *= 0.001
                np.testing.assert_allclose(moved, expected, atol=1e-9, err_msg=f"{name} at {state}")


def _metres(position: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    found = np.eye(4)
    found[:3, :3] = np.asarray(rotation).reshape(3, 3)
    found[:3, 3] = position
    return found


if __name__ == "__main__":
    unittest.main()

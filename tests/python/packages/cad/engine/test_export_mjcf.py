"""MJCF as an export of every document (``export/mjcf.py``): a robot description written as Menagerie lays
a robot out -- the exact text of a small hand-built one, its meshes binary STLs in metres beside it, the
same bytes written twice, and MuJoCo compiling it to the bodies, masses and keys it describes; a body
fixed to its link, a body and a joint of one name, a drive's effort, a joint's armature, damping and
frictionloss and a part's contact friction, and the contact pairs excluded, a
link resting on a ground welded to the world and a declared pair, which MuJoCo then leaves out; a loop of
slides alone refused by name, and a mesh file refused as a source; and models built by the engine and
exported to ``.xml``: a four-bar whose loop two connects close as built and hold closed as it falls, two
slides a pinion of no part couples as one control, a hinge whose bodies stand where the mechanism puts
its links, as built and at a state, and a free arm taken at a state, a freejoint in the scene written beside it
once, its bodies at qpos 0 where the mechanism puts its links there."""

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
from cad.engine.description import (Closure, Collision, Description, Geometry, Inertial, Joint, Link, Mesh, Pose,
                                    Visual)
from cad.engine.export import ExportRefused, ExportWarning, kind_of, refused
from cad.engine.describe import describe
from cad.engine.export import Source
from cad.engine.export.mjcf import rendered, write_description
from cad.mujoco import spec


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


def arm(closures: tuple[Closure, ...] = ()) -> Description:
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
                       poses=[Pose("raised", {"shoulder": 1.2})], closures=list(closures))


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


# A two-joint arm whose base is free, its zero taken at its home state.
TWO = """
import build123d as bd
from bd_materials import metals
from cad.build123d import free, mechanism_state
from cad.engine import xbf


@xbf("XBF/two.xbf")
def two():
    plate = bd.Box(100, 60, 20)
    plate.label = "plate"
    upper = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    upper.label = "upper"
    fore = bd.Box(80, 16, 8, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    fore.label = "fore"
    for part in (plate, upper, fore):
        part.material = metals.aluminum()
    bd.RevoluteJoint("shoulder", plate, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("shoulder", upper, bd.Location())
    plate.joints["shoulder"].connect_to(upper.joints["shoulder"], angle=0)
    bd.RevoluteJoint("elbow", upper, axis=bd.Axis((120, 0, 10), (0, 1, 0)), angular_range=(-90, 90))
    bd.RigidJoint("elbow", fore, bd.Location())
    upper.joints["elbow"].connect_to(fore.joints["elbow"], angle=0)
    root = free(bd.Compound(children=[plate, upper, fore], label="two"))
    mechanism_state(root, "home", shoulder=30, elbow=45)
    return mechanism_state(root, "up", shoulder=90)
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

    def test_a_loop_of_slides_alone_is_refused_by_name_and_nothing_is_written(self) -> None:
        slide = Closure("rail", "prismatic", "world", "finger", SHOULDER, np.linalg.inv(SHOULDER @ TIP) @ SHOULDER,
                        loop=("shoulder", "knuckle", "rail"))
        with self.assertRaisesRegex(ExportRefused, "joint 'rail' closes the loop through shoulder, knuckle, rail and "
                                                   "slides, and MuJoCo has no slide equality"):
            write_description(arm((slide,)), self.folder / "arm.xml")
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_xml_and_mjcf_are_the_kind_and_a_mesh_file_is_no_source_of_one(self) -> None:
        self.assertEqual((kind_of("robot.xml"), kind_of("robot.MJCF")), ("mjcf", "mjcf"))
        self.assertEqual(refused("part.stl", "robot.xml"),
                         "part.stl is a mesh: it has no B-rep, and no MJCF export is made from one")
        (self.folder / "part.glb").write_bytes(b"glTF")  # refused by its suffix, before it is read
        with self.assertRaisesRegex(ExportRefused, "no MJCF export is made from one"):
            api.export(self.folder / "part.glb", self.folder / "robot.xml", daemon=False, progress=False)
        self.assertFalse((self.folder / "robot.xml").exists())


def jointed() -> Description:
    """A base fixed to the world, an arm sunk 1 cm into its top on a joint named as the arm is, with its drive's
    limits, a camera kept a body of its own on the arm, and a hand clear of them on a wrist, excluded from
    the base by declaration."""
    def box(name: str, z: float, size: tuple[float, ...]) -> list[Collision]:
        return [Collision(name, Geometry("box", _frame(0, 0, z), size=size))]

    mass = Inertial(0.1, np.zeros(3), np.diag([1e-4, 1e-4, 1e-4]))
    base = Link("base", np.eye(4), collisions=box("base", 0.05, (0.2, 0.2, 0.1)), inertial=mass)
    arm = Link("arm", _frame(0, 0, 0.1), collisions=box("arm", 0.14, (0.05, 0.05, 0.3)), inertial=mass)
    camera = Link("camera", _frame(0, 0, 0.4), collisions=[Collision("camera", Geometry("sphere", np.eye(4),
                                                                                        size=(0.02,)))])
    hand = Link("hand", _frame(0, 0, 0.45), collisions=box("hand", 0.06, (0.05, 0.05, 0.1)), inertial=mass)
    joints = [Joint("rig", "fixed", "world", "base", np.eye(4)),
              Joint("arm", "revolute", "base", "arm", arm.frame, limits=((-1.0, 1.0),), as_built=(0.0,),
                    effort=12.5, velocity=3.0),
              Joint("camera", "fixed", "arm", "camera", _frame(0, 0, 0.3)),
              Joint("wrist", "continuous", "arm", "hand", _frame(0, 0, 0.35), limits=((None, None),), as_built=(0.0,))]
    return Description("rig", [Link("world", np.eye(4)), base, arm, camera, hand], joints,
                       excludes=(("base", "hand"),))


class ContactTest(_Folder):
    def test_a_body_its_names_its_effort_and_the_pairs_that_touch_at_rest_are_written_as_mujoco_reads_them(self) -> None:
        path = self.folder / "rig.xml"
        write_description(jointed(), path)
        text = path.read_text(encoding="utf-8")
        self.assertIn('<joint name="arm" type="hinge" axis="0 0 1" range="-1 1" actuatorfrcrange="-12.5 12.5"/>', text)
        # The arm sits in the base, which is welded to the world (MuJoCo's filterparent passes them); the hand is
        # clear of the arm and the camera, and excluded from the base as declared.
        self.assertIn('  <contact>\n    <exclude body1="base" body2="arm"/>\n    <exclude body1="base" body2="hand"/>\n'
                      '  </contact>', text)
        model = mujoco.MjModel.from_xml_path(str(path))
        self.assertEqual((model.body("arm").name, model.joint("arm").name), ("arm", "arm"))  # a namespace each
        self.assertEqual(model.body("camera").jntnum[0], 0)  # fixed to the arm, a body of its own
        self.assertEqual(model.body("camera").parentid[0], model.body("arm").id)
        np.testing.assert_allclose(model.jnt_actfrcrange[model.joint("arm").id], [-12.5, 12.5])
        self.assertEqual(model.nexclude, 2)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        self.assertEqual(data.ncon, 0)
        # Without the exclusions, the arm and the base are in contact at rest.
        bare = mujoco.MjModel.from_xml_string(text[:text.index("  <contact>")] + text[text.index("</contact>") + 11:])
        data = mujoco.MjData(bare)
        mujoco.mj_forward(bare, data)
        self.assertGreater(data.ncon, 0)

    def test_a_joint_s_dynamics_and_a_part_s_contact_friction_are_written_as_mujoco_reads_them(self) -> None:
        description = jointed()
        arm = description.joints[1]
        arm.armature, arm.damping, arm.friction = 0.012, 0.5, 0.2
        base = description.link("base")
        base.collisions[0] = Collision("base", base.collisions[0].geometry, (0.9,))
        hand = description.link("hand")
        hand.collisions[0] = Collision("hand", hand.collisions[0].geometry, (1.2, 0.01, 0.001))
        path = self.folder / "rig.xml"
        write_description(description, path)
        text = path.read_text(encoding="utf-8")
        self.assertIn('<joint name="arm" type="hinge" axis="0 0 1" range="-1 1" actuatorfrcrange="-12.5 12.5" '
                      'armature="0.012" damping="0.5" frictionloss="0.2"/>', text)
        self.assertIn('<joint name="wrist" type="hinge" axis="0 0 1"/>', text)  # none declared: none written
        model = mujoco.MjModel.from_xml_path(str(path))
        dof = model.jnt_dofadr[model.joint("arm").id]
        self.assertEqual((model.dof_armature[dof], model.dof_damping[dof], model.dof_frictionloss[dof]), (0.012, 0.5, 0.2))
        # The sliding coefficient alone keeps MuJoCo's torsional and rolling; three are written as given; a part
        # that declares none has MuJoCo's default.
        np.testing.assert_allclose(model.geom("base").friction, [0.9, 0.005, 0.0001])
        np.testing.assert_allclose(model.geom("hand").friction, [1.2, 0.01, 0.001])
        np.testing.assert_allclose(model.geom("arm").friction, [1, 0.005, 0.0001])

    def test_the_contact_rule_measures_convex_shapes_exactly(self) -> None:
        from cad.engine.export.contact import TOUCH, _distance, _shape

        def placed(kind: str, x: float, size: tuple[float, ...], turned: float = 0.0) -> object:
            return _shape(Description("d", [], []), Geometry(kind, np.eye(4), size=size),
                          _frame(x, 0, 0) @ _rotation_z(turned))[2]

        self.assertAlmostEqual(_distance(placed("sphere", 0, (1,)), placed("sphere", 3, (1,))), 1.0, places=9)
        self.assertAlmostEqual(_distance(placed("box", 0, (2, 2, 2)), placed("box", 3, (2, 2, 2), math.pi / 4)),
                               2 - math.sqrt(2), places=9)
        self.assertEqual(_distance(placed("capsule", 0, (0.5, 2)), placed("cylinder", 0.9, (0.5, 1))), 0.0)
        self.assertLessEqual(_distance(placed("box", 0, (1, 1, 1)), placed("box", 1, (1, 1, 1))), TOUCH)


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


# A four-bar in the XZ plane, its hinges along +Y: three hinges connected at 0, the loop's last, rocker to
# coupler, paired by label.
FOUR_BAR = """
import math

import build123d as bd
from bd_materials import metals
from cad.engine import xbf

A, B, C, D = (0, 0), (15, 26), (55, 50), (80, 0)  # mm, in the XZ plane


def bar(name, start, end, y):
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    turn = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    part = bd.Location((start[0], y, start[1]), (0, -turn, 0)) * bd.Box(
        length, 6, 4, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
    part.label = name
    part.material = metals.aluminum()
    return part


def hinge(name, holder, child, at, connect=True):
    joint = bd.RevoluteJoint(name, holder, axis=bd.Axis((at[0], 0, at[1]), (0, 1, 0)), angular_range=(-360, 360))
    bd.RigidJoint(name, child, joint.location)
    if connect:
        joint.connect_to(child.joints[name], angle=0)


@xbf("XBF/four_bar.xbf")
def four_bar():
    base = bd.Pos(40, -20, -10) * bd.Box(100, 10, 10)
    base.label = "base"
    base.material = metals.aluminum()
    crank, coupler, rocker = bar("crank", A, B, 0), bar("coupler", B, C, 8), bar("rocker", D, C, 0)
    hinge("a", base, crank, A)
    hinge("b", crank, coupler, B)
    hinge("d", base, rocker, D)
    hinge("c", rocker, coupler, C, connect=False)
    return bd.Compound(children=[base, crank, coupler, rocker], label="four_bar")
"""

# Two fingers on slides out of a palm, coupled through a pinion that holds no part (a reference axis).
GRIPPER = """
import build123d as bd
from bd_materials import metals
from cad.build123d import mechanism_state, rack_and_pinion_pair
from cad.engine import xbf


@xbf("XBF/gripper.xbf")
def gripper():
    palm = bd.Box(80, 20, 20)
    palm.label = "palm"
    fingers = []
    for side, x, out in (("left", -30, -1), ("right", 30, 1)):
        finger = bd.Pos(x, 0, 25) * bd.Box(8, 16, 30)
        finger.label = side
        finger.material = metals.aluminum()
        slide = bd.LinearJoint(side, palm, axis=bd.Axis((x, 0, 10), (out, 0, 0)), linear_range=(0, 30))
        bd.RigidJoint(side, finger, bd.Location((x, 0, 10)))
        slide.connect_to(finger.joints[side], position=0)
        fingers.append(finger)
    bd.RevoluteJoint("pinion", palm, axis=bd.Axis((0, 0, 10), (0, 1, 0)), angular_range=(-360, 360))
    gripper = bd.Compound(children=[palm, *fingers], label="gripper")
    rack_and_pinion_pair(gripper, "grip", pinion=1, left=0.15, right=0.15)
    return mechanism_state(gripper, "open", grip=100)
"""


# A vendor's cable: grey, one end face painted red, as a STEP colours a wire's faces; converted to an xbf as the
# vendor-STEP workflow does and read by a model that gives every part a material (a vendor's are often wrong), which
# build123d's setter gives its colour too.
VENDOR = """
import build123d as bd
from cad.engine import paint, step


@step("vendor.step")
def vendor():
    cable = bd.Box(20, 4, 4)
    cable.color = "#808080"
    cable = paint(cable, cable.faces().sort_by(bd.Axis.X)[-1], "#cc1100")
    cable.label = "cable"
    return bd.Compound(children=[cable], label="vendor")
"""

PAINTED = """
from pathlib import Path

import build123d as bd
from bd_materials import plastics
from cad import xbf as xbf_file
from cad.build123d import leaves
from cad.engine import xbf


@xbf("XBF/painted.xbf")
def painted():
    parts = leaves(xbf_file.read(Path(__file__).parent / "vendor.xbf"))
    for part in parts:
        part.material = plastics.pe()
    return bd.Compound(children=parts, label="painted")
"""


# A vendor's wire: white, its long face painted red, swept along a curve as a STEP's cable is, which the engine's
# tessellation folds by 16 to 45 degrees from triangle to triangle all along it.
WIRE = """
import build123d as bd
from cad.engine import paint, xbf


@xbf("XBF/wire.xbf")
def wire():
    block = bd.Box(40, 40, 40)
    block.label = "block"
    block.color = "#808080"
    path = bd.Spline((-40, 0, 21), (0, 15, 24), (40, 0, 21))
    cable = bd.sweep(bd.Plane(origin=path @ 0, z_dir=path % 0) * bd.Circle(0.6), path)
    cable.color = "#ffffff"
    cable = paint(cable, cable.faces().sort_by(bd.SortBy.AREA)[-1], "#cc1100")
    cable.label = "wire"
    return bd.Compound(children=[block, cable], label="wire")
"""


class MaterialNameTest(unittest.TestCase):
    def test_a_material_in_a_second_colour_is_named_for_the_colour_not_numbered(self) -> None:
        from cad.engine.export.mjcf import _Names, material_name

        names = _Names()
        white, grey = (0.965, 0.965, 0.953, 1.0), (0.627, 0.627, 0.627, 1.0)
        self.assertEqual([material_name(names, "Steel", white), material_name(names, "Steel", grey),
                          material_name(names, "Steel", (0.627, 0.627, 0.627, 0.5)),
                          material_name(names, "PLA", grey)],
                         ["Steel", "Steel_a0a0a0", "Steel_a0a0a080", "PLA"])


class EngineTest(_Folder):
    def built(self, name: str, source: str) -> Path:
        (self.folder / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")
        api.build_script(self.folder / f"{name}.py", daemon=False)
        return self.folder / f"XBF/{name}.xbf"

    def test_a_four_bar_closes_its_loop_with_two_connects_that_hold_it_closed_as_it_falls(self) -> None:
        xbf = self.built("four_bar", FOUR_BAR)
        out = self.folder / "robot" / "four_bar.xml"
        api.export(xbf, out, daemon=False, progress=False)
        with self.assertWarnsRegex(ExportWarning, "joint 'c' closes a loop as an equality, which holds no range"):
            rendered(describe(Source.read(xbf).view()))
        model = mujoco.MjModel.from_xml_path(str(out))
        # The tree's three hinges, and the loop's last pair two connects of sites on the rocker and the coupler.
        self.assertEqual([model.joint(at).name for at in range(model.njnt)], ["a", "b", "d"])
        self.assertEqual([(model.equality(at).name, int(model.eq_type[at]), int(model.eq_objtype[at]))
                          for at in range(model.neq)],
                         [("c", mujoco.mjtEq.mjEQ_CONNECT, mujoco.mjtObj.mjOBJ_SITE),
                          ("c/axis", mujoco.mjtEq.mjEQ_CONNECT, mujoco.mjtObj.mjOBJ_SITE)])
        self.assertEqual([(equality.name, equality.objtype) for equality in spec(xbf).equalities],
                         [("c", mujoco.mjtObj.mjOBJ_SITE), ("c/axis", mujoco.mjtObj.mjOBJ_SITE)])
        data = mujoco.MjData(model)

        def gap() -> float:
            return max(float(np.linalg.norm(data.site(f"c/1{end}").xpos - data.site(f"c/2{end}").xpos))
                       for end in ("", "_axis"))

        mujoco.mj_forward(model, data)
        self.assertLess(gap(), 1e-9, "closed as built")
        np.testing.assert_allclose(data.site("c/1").xpos, [0.055, 0, 0.05], atol=1e-9)
        # Under gravity the linkage swings and the loop holds, within MuJoCo's default soft constraint (a few
        # millimetres while it whips round, a tenth of one once it hangs); open, it parts by centimetres.
        worst = {}
        for active in (1, 0):
            mujoco.mj_resetData(model, data)
            data.eq_active[:] = active
            worst[active] = 0.0
            for _step in range(400):
                mujoco.mj_step(model, data)
                worst[active] = max(worst[active], gap())
            if active:
                self.assertGreater(abs(data.qpos[0]), math.radians(20), "the crank swung")
                self.assertLess(gap(), 1e-3)
        self.assertLess(worst[1], 1e-2)
        self.assertGreater(worst[0], 10 * worst[1])

    def test_a_part_whose_faces_are_painted_is_drawn_a_geom_per_look_as_the_viewer_draws_it(self) -> None:
        import xml.etree.ElementTree as ET

        from cad.engine.export.mesh import groups, meshes

        (self.folder / "vendor.py").write_text(textwrap.dedent(VENDOR), encoding="utf-8")
        api.build_script(self.folder / "vendor.py", daemon=False)
        api.export(self.folder / "vendor.step", self.folder / "vendor.xbf", daemon=False, progress=False)
        xbf = self.built("painted", PAINTED)
        view = Source.read(xbf).view()
        # The viewer draws the painted face red over the part, whose own colour is its material's now.
        [prototype] = view.prototypes
        [(own, _), (paint, _)] = sorted(groups(meshes(view)[0], prototype), key=lambda look: look[0][1] is None)
        self.assertEqual(round(paint[0][0], 3), round(0.6038, 3))  # #cc1100, linear
        out = self.folder / "robot" / "painted.xml"
        api.export(xbf, out, daemon=False, progress=False)
        geoms = {geom.get("name"): geom for geom in ET.parse(out).iter("geom") if geom.get("class") == "visual"}
        self.assertEqual(sorted(geoms), ["cable", "cable_paint1"])
        red, white = [0.8, 0.0667, 0.0, 1.0], [1.0, 1.0, 1.0, 1.0]  # #cc1100, and PE's white, in sRGB

        def rgba(text: str) -> list[float]:
            return [round(float(value), 3) for value in text.split()]

        self.assertEqual(rgba(geoms["cable_paint1"].get("rgba")), [round(value, 3) for value in red])
        materials = {material.get("name"): material.get("rgba") for material in ET.parse(out).iter("material")}
        self.assertEqual(rgba(materials[geoms["cable"].get("material")]), white)
        # Each look an open surface, a shell to MuJoCo and drawn unweighed; the part whole collides.
        model = mujoco.MjModel.from_xml_path(str(out))
        self.assertEqual(model.nmesh, 3)
        self.assertEqual({geoms[name].get("mass") for name in geoms}, {"0"})
        self.assertEqual(sorted(mesh.get("inertia") or "" for mesh in ET.parse(out).iter("mesh")), ["", "shell", "shell"])
        # The URDF draws the same two looks.
        urdf = self.folder / "description" / "painted.urdf"
        api.export(xbf, urdf, daemon=False, progress=False)
        root = ET.parse(urdf).getroot()
        colours = {material.get("name"): material.find("color").get("rgba") for material in root.findall("material")}
        visuals = {visual.get("name"): rgba(colours[visual.find("material").get("name")])
                   for visual in root.iter("visual")}
        self.assertEqual(visuals, {"cable": white, "cable_paint1": [round(value, 3) for value in red]})

    def test_a_painted_wire_is_its_paint_in_mujoco_and_in_the_still(self) -> None:
        from PIL import Image

        from cad.engine.snapshot import snapshot

        xbf = self.built("wire", WIRE)
        out = self.folder / "robot" / "wire.xml"
        api.export(xbf, out, daemon=False, progress=False)
        # MuJoCo compiles the paint's colour on the paint's geom, no material over it.
        model = mujoco.MjModel.from_xml_path(str(out))
        paint = model.geom("wire_paint1")
        self.assertEqual(-1, int(model.geom_matid[paint.id]))
        np.testing.assert_allclose(model.geom_rgba[paint.id], [0.8, 0.0667, 0.0, 1.0], atol=1e-3)

        # The still draws the wire red, as the viewer draws a robot's link meshes: faces alone. Its triangles'
        # folds, lines a pixel apart along a 1.2 mm wire, hid half the red under them.
        def red(display: dict[str, str]) -> int:
            png = self.folder / f"{display['mode']}.png"
            snapshot(out, png, daemon=False, size=(800, 600), display=display)
            pixels = np.asarray(Image.open(png).convert("RGB")).astype(int)
            return int(((pixels[..., 0] > 120) & (pixels[..., 1] < 80) & (pixels[..., 2] < 80)).sum())

        shaded = red({"mode": "shaded"})
        self.assertGreater(shaded, 1000)
        self.assertGreaterEqual(red({"mode": "solid"}), 0.95 * shaded)

    def test_two_slides_a_pinion_couples_are_one_control_and_the_pinion_no_body(self) -> None:
        xbf = self.built("gripper", GRIPPER)
        out = self.folder / "robot" / "gripper.xml"
        api.export(xbf, out, daemon=False, progress=False)
        text = out.read_text(encoding="utf-8")
        self.assertIn('<joint joint1="right" joint2="left" polycoef="0 1 0 0 0"/>', text)
        self.assertNotIn("pinion", text)
        model = mujoco.MjModel.from_xml_path(str(out))
        self.assertEqual(([model.body(at).name for at in range(model.nbody)], model.njnt),
                         (["world", "palm", "left", "right"], 2))
        np.testing.assert_allclose(model.key("open").qpos, [0.015, 0.015], atol=1e-12)
        data = mujoco.MjData(model)
        data.qpos[:] = (0.01, 0.0)
        for _step in range(200):
            mujoco.mj_step(model, data)
        self.assertAlmostEqual(data.qpos[1], data.qpos[0], delta=1e-4)

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

    def test_a_free_base_at_its_zero_state_is_a_freejoint_whose_scene_is_written_once(self) -> None:
        xbf = self.built("two", TWO)
        out = self.folder / "robot" / "two.xml"
        told: list[str] = []
        [written] = api.export(xbf, out, zero="home", daemon=False, progress=False, log=told.append)
        self.assertEqual((written.robot["base"], written.robot["zero"], written.robot["links"]),
                         ("free", "home", ["plate", "upper", "fore"]))
        self.assertIn("two.xml: wrote scene.xml beside it: a floor and a light around the robot, yours to edit (an "
                      "export never writes over it)", told)
        # The scene includes the robot and compiles: a free base (seven values) and the two hinges, ranged
        # around home, every key holding the base where it stands.
        model = mujoco.MjModel.from_xml_path(str(out.parent / "scene.xml"))
        self.assertEqual((model.nq, model.njnt, model.joint("two").type), (9, 3, mujoco.mjtJoint.mjJNT_FREE))
        np.testing.assert_allclose(model.jnt_range[model.joint("shoulder").id], np.radians([-40, 90]), atol=1e-9)
        np.testing.assert_allclose(model.jnt_range[model.joint("elbow").id], np.radians([-135, 45]), atol=1e-9)
        np.testing.assert_allclose(model.key("home").qpos, [0, 0, 0, 1, 0, 0, 0, 0, 0], atol=1e-12)
        np.testing.assert_allclose(model.key("up").qpos[7:], np.radians([60, -45]), atol=1e-9)
        self.assertIn(model.geom("floor").id, range(model.ngeom))
        # At qpos 0 every body stands where the mechanism puts its link at home.
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        kinematics = document.Loaded(xbf).structure()["kinematics"]
        built = mechanism.link_worlds(kinematics, {"shoulder": (0.0,), "elbow": (0.0,)})
        posed = mechanism.link_worlds(kinematics, {"shoulder": (30.0,), "elbow": (45.0,)})
        for at, link in enumerate(kinematics["links"]):
            body = model.body(link["name"]).id
            moved = posed[at] @ np.linalg.inv(built[at])
            moved[:3, 3] *= 0.001
            frame = _metres(data.xpos[body], data.xmat[body])
            unposed = describe(Source.read(xbf).view()).link(link["name"]).frame
            np.testing.assert_allclose(frame, moved @ unposed, atol=1e-9, err_msg=link["name"])
        # Free, the base drops as its limp arm folds onto the floor (bolted, it would stay at the origin), and it
        # rests on the floor, nowhere through it.
        for _step in range(1000):
            mujoco.mj_step(model, data)
        self.assertLess(float(data.qpos[2]), -0.01)
        floor = float(model.geom("floor").pos[2])
        self.assertGreater(min(float(data.geom_xpos[at][2]) for at in range(model.ngeom)
                               if model.geom_group[at] == 3), floor - 0.03)
        # Exported again, the scene is the person's, kept without a word; one that includes another robot is
        # said, once.
        scene = out.parent / "scene.xml"
        scene.write_text(scene.read_text(encoding="utf-8") + "<!-- mine -->\n", encoding="utf-8")
        told.clear()
        api.export(xbf, out, zero="home", daemon=False, progress=False, log=told.append)
        self.assertFalse([line for line in told if "scene.xml" in line], told)
        self.assertTrue(scene.read_text(encoding="utf-8").endswith("<!-- mine -->\n"))
        other = out.parent / "other.xml"
        api.export(xbf, other, zero="home", daemon=False, progress=False, log=told.append)
        self.assertEqual([line for line in told if "scene.xml" in line],
                         ["other.xml: the existing scene.xml beside it includes no other.xml, so it shows another "
                          "robot: it is yours to edit, and an export never writes over it"])
        self.assertTrue(scene.read_text(encoding="utf-8").endswith("<!-- mine -->\n"))
        with self.assertRaisesRegex(ExportRefused, "two.stl: a zero state poses a robot description"):
            api.export(xbf, self.folder / "two.stl", zero="home", daemon=False, progress=False)


def _metres(position: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    found = np.eye(4)
    found[:3, :3] = np.asarray(rotation).reshape(3, 3)
    found[:3, 3] = position
    return found


if __name__ == "__main__":
    unittest.main()

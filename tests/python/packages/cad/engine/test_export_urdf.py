"""URDF as an export of every document (``export/urdf.py``): a robot description written as ROS reads one --
the exact text of a small hand-built one, its meshes MJCF's bytes beside it, the same bytes written twice,
the repository's own URDF check passing it and the stills reading its links where the description has them;
a ground holding nothing giving way to its fixed child, a cylindrical joint as a turn and a slide, a ball and
a loop refused by name; and a jointed model built by the engine and exported to ``.urdf``, its links moving
as the mechanism moves them."""

from __future__ import annotations

import math
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

from cad import urdf
from cad.engine import api, document, mechanism
from cad.engine.description import Collision, Description, Geometry, Inertial, Joint, Link, Mesh, Pose, Visual
from cad.engine.export import ExportRefused, kind_of, refused
from cad.engine.export import mjcf
from cad.engine.export.urdf import write_description
from cad.engine.formats.robot import read_robot, read_urdf


def _frame(x: float = 0, y: float = 0, z: float = 0, about: str | None = None, angle: float = 0.0) -> np.ndarray:
    found = np.eye(4)
    found[:3, 3] = (x, y, z)
    c, s = math.cos(angle), math.sin(angle)
    if about == "x":
        found[1:3, 1:3] = [[c, -s], [s, c]]
    elif about == "y":
        found[0, 0], found[0, 2], found[2, 0], found[2, 2] = c, s, -s, c
    elif about == "z":
        found[:2, :2] = [[c, -s], [s, c]]
    return found


# test_export_mjcf's arm: a shoulder 0.2 m up whose axis is the world's -Y, an arm on it 0.3 m long with a
# capsule collision and a named tip, and a finger at the tip whose knuckle follows the shoulder.
SHOULDER = _frame(0, 0, 0.2, "x", -math.pi / 2)
TIP = _frame(0.3, 0, 0)


def arm(loops: tuple[str, ...] = (), shoulder: str = "revolute") -> Description:
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
    limits = ((-1.0, 1.5),) if shoulder == "revolute" else ((-1.0, 1.0),) * 3
    joints = [Joint("shoulder", shoulder, "world", "arm", SHOULDER, limits=limits, as_built=(0.0,) * len(limits)),
              Joint("knuckle", "revolute", "arm", "finger", TIP, limits=((-0.5, 0.75),), as_built=(0.0,),
                    follows=("shoulder", 0.5, 0.1))]
    return Description("arm", [world, upper, finger], joints, meshes={"k1": tetrahedron},
                       poses=[Pose("raised", {"shoulder": 1.2})], loops=loops)


GOLDEN = """\
<?xml version="1.0" encoding="utf-8"?>
<robot name="arm">
  <material name="steel">
    <color rgba="0.5 0.5 0.5 1"/>
  </material>
  <material name="paint">
    <color rgba="0.9 0.1 0.1 1"/>
  </material>

  <link name="world">
    <visual name="base">
      <origin xyz="0 0 0.05" rpy="0 0 0"/>
      <geometry>
        <box size="0.4 0.2 0.1"/>
      </geometry>
      <material name="steel"/>
    </visual>
  </link>

  <joint name="shoulder" type="revolute">
    <origin xyz="0 0 0.2" rpy="-1.57079633 0 0"/>
    <parent link="world"/>
    <child link="arm"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1" upper="1.5" effort="0" velocity="0"/>
  </joint>

  <link name="arm">
    <inertial>
      <origin xyz="0.15 0 0" rpy="0 0 0"/>
      <mass value="2"/>
      <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.016" iyz="0" izz="0.016"/>
    </inertial>
    <visual name="arm">
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry>
        <mesh filename="meshes/arm_link.stl" scale="1 1 1"/>
      </geometry>
      <material name="paint"/>
    </visual>
    <collision name="arm">
      <origin xyz="0.15 0 0" rpy="0 1.57079633 0"/>
      <geometry>
        <cylinder radius="0.02" length="0.3"/>
      </geometry>
    </collision>
    <collision name="arm_top">
      <origin xyz="0.3 0 0" rpy="0 1.57079633 0"/>
      <geometry>
        <sphere radius="0.02"/>
      </geometry>
    </collision>
    <collision name="arm_bottom">
      <origin xyz="0 0 0" rpy="0 1.57079633 0"/>
      <geometry>
        <sphere radius="0.02"/>
      </geometry>
    </collision>
  </link>

  <joint name="tip_joint" type="fixed">
    <origin xyz="0.3 0 0" rpy="0 0 0"/>
    <parent link="arm"/>
    <child link="tip"/>
  </joint>

  <link name="tip"/>

  <joint name="knuckle" type="revolute">
    <origin xyz="0.3 0 0" rpy="0 0 0"/>
    <parent link="arm"/>
    <child link="finger"/>
    <axis xyz="0 0 1"/>
    <limit lower="-0.5" upper="0.75" effort="0" velocity="0"/>
    <mimic joint="shoulder" multiplier="0.5" offset="0.1"/>
  </joint>

  <link name="finger">
    <inertial>
      <origin xyz="0.05 0 0" rpy="0 0 0"/>
      <mass value="0.5"/>
      <inertia ixx="0.0002" ixy="1e-05" ixz="0" iyy="0.0004" iyz="0" izz="0.0005"/>
    </inertial>
    <visual name="finger">
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry>
        <mesh filename="meshes/arm_link.stl" scale="1 1 1"/>
      </geometry>
      <material name="paint"/>
    </visual>
  </link>
</robot>
"""


def rig() -> Description:
    """A ground holding nothing, a base fixed to it turned and off its origin, a post fixed to it too, and
    on the base a slider on a cylindrical joint (a turn with no range, a slide ranged at one end) whose joint
    has the slider's name."""
    block = Visual("block", Geometry("box", np.eye(4), size=(0.1, 0.1, 0.1)), (0.2, 0.4, 0.6, 1.0))
    base = Link("base", _frame(0.1, 0, 0, "z", 0.5), visuals=[block])
    post = Link("post", _frame(0, 0.2, 0), visuals=[block])
    slider = Link("slider", base.frame @ _frame(0, 0, 0.05), visuals=[block],
                  inertial=Inertial(0.1, np.zeros(3), np.diag([1e-4, 1e-4, 1e-4])))
    joints = [Joint("rig", "fixed", "world", "base", base.frame),
              Joint("mount", "fixed", "world", "post", post.frame),
              Joint("slider", "cylindrical", "base", "slider", _frame(0, 0, 0.05),
                    limits=((None, None), (0.0, None)), as_built=(0.0, 0.0))]
    return Description("rig", [Link("world", np.eye(4)), base, post, slider], joints)


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="export-urdf-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def assertValid(self, path: Path, **options) -> None:
        checked = urdf.validate(path, **options)
        self.assertTrue(checked.ok, "\n".join(f"{f.severity} {f.code}: {f.message}" for f in checked.findings))
        self.assertEqual([f.code for f in checked.findings if f.severity != "info"], [],
                         "\n".join(f"{f.severity} {f.code}: {f.message}" for f in checked.findings))


class HandBuiltTest(_Folder):
    def test_a_description_is_written_as_ros_reads_a_robot_and_the_stills_read_it_where_it_stands(self) -> None:
        path = self.folder / "arm.urdf"
        written = write_description(arm(), path)
        self.assertEqual(written, [path, self.folder / "meshes" / "arm_link.stl"])
        self.assertEqual(path.read_text(encoding="utf-8"), GOLDEN)
        # The mesh: MJCF's bytes, one writer of them. Written again, elsewhere and in place: the same bytes,
        # and in place nothing moved.
        data = (self.folder / "meshes" / "arm_link.stl").read_bytes()
        self.assertEqual(data, mjcf.rendered(arm())[1]["arm_link.stl"])
        again = self.folder / "again" / "arm.urdf"
        write_description(arm(), again)
        self.assertEqual((again.read_bytes(), (again.parent / "meshes" / "arm_link.stl").read_bytes()),
                         (path.read_bytes(), data))
        before = path.stat().st_mtime_ns, (self.folder / "meshes" / "arm_link.stl").stat().st_mtime_ns
        write_description(arm(), path)
        self.assertEqual((path.stat().st_mtime_ns, (self.folder / "meshes" / "arm_link.stl").stat().st_mtime_ns),
                         before)

        self.assertValid(path)
        robot = read_urdf(path)
        self.assertEqual((robot.root, sorted(robot.links)), ("world", ["arm", "finger", "tip", "world"]))
        for link in arm().links:
            np.testing.assert_allclose(robot.links[link.name][:3, 3], link.frame[:3, 3], atol=1e-9)
            np.testing.assert_allclose(robot.links[link.name][:3, :3], link.frame[:3, :3], atol=1e-8)
        np.testing.assert_allclose(robot.links["tip"][:3, 3], (SHOULDER @ TIP)[:3, 3], atol=1e-9)
        self.assertEqual(next(j for j in robot.joints if j.name == "knuckle").mimic, ("shoulder", 0.5, 0.1))
        # Posed, the finger follows the shoulder through its mimic.
        values, _ = robot.values({"shoulder": math.degrees(1.2)})
        finger = robot.placements(values)["finger"]
        expected = SHOULDER @ _frame(about="z", angle=1.2) @ TIP @ _frame(about="z", angle=0.5 * 1.2 + 0.1)
        np.testing.assert_allclose(finger[:3, 3], 1000 * expected[:3, 3], atol=1e-6)

    def test_a_package_names_the_meshes_as_ros_resolves_them(self) -> None:
        path = self.folder / "arm_description" / "arm.urdf"
        write_description(arm(), path, package="arm_description")
        self.assertIn('filename="package://arm_description/meshes/arm_link.stl"', path.read_text(encoding="utf-8"))
        self.assertValid(path, packages={"arm_description": path.parent})
        self.assertEqual(read_urdf(path).visuals["arm"][0].mesh[1], path.parent / "meshes" / "arm_link.stl")

    def test_a_ground_holding_nothing_gives_way_to_its_fixed_child_and_a_cylindrical_joint_is_two(self) -> None:
        path = self.folder / "rig.urdf"
        write_description(rig(), path)
        checked = urdf.validate(path)
        self.assertTrue(checked.ok, [f.message for f in checked.findings])
        robot = read_urdf(path)
        # The base is the root, where the file's space is; the joint that fixed it is not written, and the post
        # hangs from the base where it stood.
        self.assertEqual(robot.root, "base")
        self.assertEqual([(j.name, j.type, j.parent, j.child) for j in robot.joints],
                         [("mount", "fixed", "base", "post"), ("slider_2", "continuous", "base", "slider_2_turn"),
                          ("slider_2_slide", "prismatic", "slider_2_turn", "slider")])
        description = rig()
        space = np.linalg.inv(description.link("base").frame)
        for name in ("base", "post", "slider"):
            np.testing.assert_allclose(robot.links[name], space @ description.link(name).frame, atol=1e-8)
        slide = robot.joints[2]
        self.assertEqual((slide.lower, slide.upper), (0.0, 1e16))  # the open end: SDFormat's word for none

    def test_a_ball_and_a_loop_are_refused_by_name_and_nothing_is_written(self) -> None:
        with self.assertRaisesRegex(ExportRefused, "joint 'shoulder' is spherical, and URDF has no ball joint"):
            write_description(arm(shoulder="spherical"), self.folder / "arm.urdf")
        with self.assertRaisesRegex(ExportRefused, "loop through shoulder"):
            write_description(arm(loops=("shoulder",)), self.folder / "arm.urdf")
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_urdf_is_the_kind_and_a_mesh_file_is_no_source_of_one(self) -> None:
        self.assertEqual(kind_of("robot.URDF"), "urdf")
        self.assertEqual(refused("part.stl", "robot.urdf"),
                         "part.stl is a mesh: it has no B-rep, and no URDF export is made from one")


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
    def test_a_built_hinge_exports_to_a_urdf_whose_links_move_as_its_mechanism_does(self) -> None:
        (self.folder / "hinge.py").write_text(textwrap.dedent(HINGE), encoding="utf-8")
        api.build_script(self.folder / "hinge.py", daemon=False)
        xbf = self.folder / "XBF/hinge.xbf"
        out = self.folder / "robot" / "hinge.urdf"
        [written] = api.export(xbf, out, daemon=False, progress=False)
        self.assertEqual(written.kind, "urdf")
        self.assertTrue(urdf.validate(out).ok)
        robot = read_robot(out)
        elbow = next(joint for joint in robot.joints if joint.name == "elbow")
        # Its range around the as-built 30 degrees, its axis the world's +Y.
        np.testing.assert_allclose((elbow.lower, elbow.upper), np.radians([-40, 90]), atol=1e-8)
        np.testing.assert_allclose(elbow.axis, [0, 1, 0], atol=1e-8)
        kinematics = document.Loaded(xbf).structure()["kinematics"]
        names = [link["name"] for link in kinematics["links"]]
        built = mechanism.link_worlds(kinematics, {"elbow": (30.0,)})
        space = built[names.index(robot.root)]  # the file's space: its root's frame, the ground's
        rest = robot.placements(robot.values(None)[0])
        # At each state, every link moved from where it stood as the mechanism moves it.
        for state, degrees in (("raised", 90.0), ("flat", 0.0)):
            posed = mechanism.link_worlds(kinematics, {"elbow": (degrees,)})
            placed = robot.placements(robot.values({"elbow": degrees - 30})[0])
            for at, name in enumerate(names):
                moved = space @ placed[name] @ np.linalg.inv(rest[name]) @ np.linalg.inv(space)
                np.testing.assert_allclose(moved, posed[at] @ np.linalg.inv(built[at]), atol=1e-6,
                                           err_msg=f"{name} at {state}")


if __name__ == "__main__":
    unittest.main()

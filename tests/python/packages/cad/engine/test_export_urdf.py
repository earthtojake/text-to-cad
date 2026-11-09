"""URDF as an export of every document (``export/urdf.py``): a robot description written as ROS reads one --
the exact text of a small hand-built one, its meshes MJCF's bytes beside it, the same bytes written twice,
the repository's own URDF check passing it and the stills reading its links where the description has them;
a ground holding nothing giving way to its fixed child, a cylindrical joint as a turn and a slide, a link
and a joint keeping one name and a name repeated in its kind renamed and said, a joint's damping and
friction as its dynamics and its armature and a part's contact friction not written and said in a line
a kind, a ball refused by name, a joint that closes a loop left out and said; a root with an inertia, or standing off the
world's frame, hung from an empty ``base_link`` there and a free base the root; a root part turned in its
placement standing where the MJCF stands it; and a jointed model built by the engine and exported to ``.urdf``, its
links moving as the mechanism moves them, and a free arm taken at a state, its links at zero where the
mechanism puts them there."""

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
from cad.engine.description import (Closure, Collision, Description, Geometry, Inertial, Joint, Link, Mesh, Pose,
                                    Visual)
from cad.engine.export import ExportRefused, ExportWarning, kind_of, refused
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


def arm(closures: tuple[Closure, ...] = (), shoulder: str = "revolute") -> Description:
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
    joints = [Joint("shoulder", shoulder, "world", "arm", SHOULDER, limits=limits, as_built=(0.0,) * len(limits),
                    effort=12.5, velocity=3.0),
              Joint("knuckle", "revolute", "arm", "finger", TIP, limits=((-0.5, 0.75),), as_built=(0.0,),
                    follows=("shoulder", 0.5, 0.1))]
    return Description("arm", [world, upper, finger], joints, meshes={"k1": tetrahedron},
                       poses=[Pose("raised", {"shoulder": 1.2})], closures=list(closures))


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
    <limit lower="-1" upper="1.5" effort="12.5" velocity="3"/>
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
        # The slider link and its joint share a name: legal, said at export as the validator warns of it.
        with self.assertWarnsRegex(ExportWarning, r"^1 name held by a link and a joint both: slider \(legal URDF; "
                                                  r"cad urdf validate warns of it, joint_link_name_collision"):
            write_description(rig(), path)
        checked = urdf.validate(path)
        self.assertTrue(checked.ok, [f.message for f in checked.findings])
        self.assertIn("joint_link_name_collision", {finding.code for finding in checked.findings})
        robot = read_urdf(path)
        # The base takes the ground's place; the joint that fixed it is not written, and the post hangs from the base
        # where it stood. The base stands turned and off the world's origin, so an empty base_link roots it there:
        # the file's space is the world's, every link where the description stands it.
        self.assertEqual(robot.root, "base_link")
        self.assertEqual([(j.name, j.type, j.parent, j.child) for j in robot.joints],
                         [("base_link_joint", "fixed", "base_link", "base"), ("mount", "fixed", "base", "post"),
                          ("slider", "continuous", "base", "slider_turn"),
                          ("slider_slide", "prismatic", "slider_turn", "slider")])
        description = rig()
        for name in ("base", "post", "slider"):
            np.testing.assert_allclose(robot.links[name], description.link(name).frame, atol=1e-8)
        slide = robot.joints[3]
        self.assertEqual((slide.lower, slide.upper), (0.0, 1e16))  # the open end: SDFormat's word for none

    def test_a_root_with_an_inertia_hangs_from_an_empty_base_link_and_a_free_base_is_the_root(self) -> None:
        from dataclasses import replace

        weight = Inertial(1.0, np.zeros(3), np.diag([1e-3, 1e-3, 1e-3]))
        for named, empty in (("base", "base_link"), ("base_link", "base_footprint")):
            description = rig()
            base = description.link("base")
            base.inertial, base.name = weight, named
            description.joints = [replace(joint, parent=named) if joint.parent == "base" else
                                  replace(joint, child=named) if joint.child == "base" else joint
                                  for joint in description.joints]
            path = self.folder / f"{named}.urdf"
            write_description(description, path)
            checked = urdf.validate(path)
            self.assertTrue(checked.ok, [finding.message for finding in checked.findings])
            robot = read_urdf(path)
            # KDL takes no inertia on the root: an empty link before it, where the base stands; the description's
            # names kept, and a base named base_link under REP 105's base_footprint.
            self.assertEqual((robot.root, robot.joints[0].name, robot.joints[0].parent, robot.joints[0].child),
                             (empty, f"{empty}_joint", empty, named))
            np.testing.assert_allclose(robot.links[named], base.frame, atol=1e-12)
        # A free base all the ground holds is the root (behind the empty link that stands it where it starts), its
        # floating joint unwritten; beside a bolted post the
        # ground stays the root and the free base is written fixed to it, and said.
        description = rig()
        description.joints[0].kind = "floating"
        alone = replace(description, links=[link for link in description.links if link.name != "post"],
                        joints=[joint for joint in description.joints if joint.name != "mount"])
        write_description(alone, self.folder / "alone.urdf")
        self.assertEqual((read_urdf(self.folder / "alone.urdf").root, "rig" in {j.name for j in
                          read_urdf(self.folder / "alone.urdf").joints}), ("base_link", False))
        with self.assertWarnsRegex(ExportWarning, "link 'base' is free, and a URDF has one root: it is written fixed "
                                                  "to 'world'"):
            write_description(description, self.folder / "beside.urdf")
        robot = read_urdf(self.folder / "beside.urdf")
        self.assertEqual((robot.root, next(j.type for j in robot.joints if j.name == "rig")), ("world", "fixed"))

    def test_a_name_repeated_in_its_kind_is_renamed_and_said(self) -> None:
        # The rig's slider link keeps its name beside its joint (above); a frame named as a link is not a link's.
        description = rig()
        description.link("post").frames["base"] = np.eye(4)
        path = self.folder / "rig.urdf"
        with self.assertWarnsRegex(ExportWarning, "link 'base' is written 'base_2': another link holds its name"):
            write_description(description, path)
        self.assertEqual(sorted(read_urdf(path).links), ["base", "base_2", "base_link", "post", "slider",
                                                         "slider_turn"])

    def test_a_joint_s_damping_and_friction_are_its_dynamics_and_what_urdf_cannot_say_is_said(self) -> None:
        description = arm()
        shoulder, knuckle = description.joints
        shoulder.armature, shoulder.damping, shoulder.friction = 0.012, 0.5, 0.2
        knuckle.armature = 0.003
        # The knuckle bounds its effort and gives no speed: URDF requires one, so it is written 0, and said.
        knuckle.effort, knuckle.velocity = 7.0, None
        upper = description.link("arm")
        geometry = upper.collisions[0].geometry
        # Two hulls of one part: the part is named once.
        upper.collisions[:] = [Collision(f"arm_hull{at}", geometry, (0.9,), part="arm") for at in range(2)]
        path = self.folder / "arm.urdf"
        with self.assertWarns(ExportWarning) as said:
            write_description(description, path)
        # A line a kind, naming every joint or part that declares it.
        self.assertEqual([str(warning.message) for warning in said.warnings],
                         ["armature of 2 joints not written (a URDF has none; an MJCF carries it): shoulder, knuckle",
                          "contact friction of 1 part not written (a URDF has none; an MJCF carries it): arm",
                          "velocity of 1 joint written 0 (each declares an effort and no velocity, and a ROS controller "
                          "reads 0 as none allowed: give limits(..., velocity=) where the hardware's is known): "
                          "knuckle"])
        text = path.read_text(encoding="utf-8")
        self.assertIn('<dynamics damping="0.5" friction="0.2"/>', text)
        self.assertEqual(text.count("<dynamics"), 1)  # the knuckle declares none
        self.assertIn('effort="7" velocity="0"/>', text)

    def test_a_ball_is_refused_by_name_and_nothing_is_written(self) -> None:
        with self.assertRaisesRegex(ExportRefused, "joint 'shoulder' is spherical, and URDF has no ball joint"):
            write_description(arm(shoulder="spherical"), self.folder / "arm.urdf")
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_a_joint_that_closes_a_loop_is_left_out_and_said_and_the_tree_written(self) -> None:
        strut = Closure("strut", "revolute", "world", "finger", SHOULDER @ TIP, np.eye(4), loop=("shoulder", "knuckle",
                                                                                                "strut"))
        path = self.folder / "arm.urdf"
        with self.assertWarnsRegex(ExportWarning, "URDF cannot close a loop: joint 'strut' is left out; the MJCF "
                                                  "closes it"):
            write_description(arm((strut,)), path)
        self.assertEqual(path.read_text(encoding="utf-8"), GOLDEN)

    def test_urdf_is_the_kind_and_a_mesh_file_is_no_source_of_one(self) -> None:
        self.assertEqual(kind_of("robot.URDF"), "urdf")
        self.assertEqual(refused("part.stl", "robot.urdf"),
                         "part.stl is a mesh: it has no B-rep, and no URDF export is made from one")
        # SDF is read (the viewer, the stills, `cad sdf validate`) but never written: an export to one is
        # refused as any unknown suffix is, before anything is described.
        with self.assertRaisesRegex(ExportRefused, r"^robot\.sdf: an export is one of .*\.urdf$"):
            kind_of("robot.sdf")


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


# A hinge whose base part is turned a quarter about X in its placement: the root link's frame, the base's own,
# is turned in the world.
TURNED = """
import build123d as bd
from bd_materials import metals
from cad.engine import xbf


@xbf("XBF/turned.xbf")
def turned():
    base = bd.Pos(0, 38, 0) * bd.Rot(90, 0, 0) * bd.Box(100, 20, 60)
    base.label = "base"
    arm = bd.Pos(40, 38, 30) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    for part in (base, arm):
        part.material = metals.aluminum()
    elbow = bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 38, 30), (0, -1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("elbow", arm, elbow.location)
    elbow.connect_to(arm.joints["elbow"], angle=0)
    return bd.Compound(children=[base, arm], label="turned")
"""


class EngineTest(_Folder):
    def test_a_turned_root_part_stands_where_the_mjcf_stands_it(self) -> None:
        (self.folder / "turned.py").write_text(textwrap.dedent(TURNED), encoding="utf-8")
        api.build_script(self.folder / "turned.py", daemon=False)
        xbf = self.folder / "XBF/turned.xbf"
        api.export(xbf, self.folder / "mjcf" / "turned.xml", daemon=False, progress=False)
        api.export(xbf, self.folder / "urdf" / "turned.urdf", daemon=False, progress=False)
        mjcf_robot, urdf_robot = read_robot(self.folder / "mjcf" / "turned.xml"), read_robot(self.folder / "urdf" / "turned.urdf")
        # The URDF roots at an empty link at the world's frame, and every link of the MJCF stands where the URDF
        # stands it, at zero and with the hinge turned.
        self.assertEqual(urdf_robot.root, "base_link")
        np.testing.assert_allclose(urdf_robot.placements(urdf_robot.values(None)[0])["base"][:3, :3],
                                   [[1, 0, 0], [0, 0, -1], [0, 1, 0]], atol=1e-6)
        for values in (None, {"elbow": 40}):
            built = mjcf_robot.placements(mjcf_robot.values(values)[0])
            placed = urdf_robot.placements(urdf_robot.values(values)[0])
            for name in ("base", "arm"):
                np.testing.assert_allclose(placed[name], built[name], atol=1e-6, err_msg=f"{name} at {values}")


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

    def test_a_free_arm_taken_at_a_state_stands_at_zero_where_the_as_built_one_stands_there(self) -> None:
        (self.folder / "two.py").write_text(textwrap.dedent(TWO), encoding="utf-8")
        api.build_script(self.folder / "two.py", daemon=False)
        xbf = self.folder / "XBF/two.xbf"
        built, zeroed = self.folder / "built" / "two.urdf", self.folder / "home" / "two.urdf"
        api.export(xbf, built, daemon=False, progress=False)
        [written] = api.export(xbf, zeroed, zero="home", daemon=False, progress=False)
        self.assertEqual((written.robot["zero"], written.robot["base"]), ("home", "free"))
        self.assertFalse((zeroed.parent / "scene.xml").exists(), "a scene is an MJCF's")
        self.assertTrue(urdf.validate(zeroed).ok)
        then, now = read_robot(built), read_robot(zeroed)
        # The free base is the root, an empty base_link before it (the plate has an inertia), no world joint.
        self.assertEqual((now.root, [joint.name for joint in now.joints]), ("base_link", ["base_link_joint", "shoulder",
                                                                                           "elbow"]))
        at_home = then.placements(then.values({"shoulder": 30, "elbow": 45})[0])
        at_zero = now.placements(now.values(None)[0])
        for name in ("plate", "upper", "fore"):
            np.testing.assert_allclose(at_zero[name], at_home[name], atol=1e-6, err_msg=name)
        elbow = {(joint.name): joint for joint in now.joints}["elbow"]
        np.testing.assert_allclose((elbow.lower, elbow.upper), np.radians([-135, 45]), atol=1e-8)


if __name__ == "__main__":
    unittest.main()

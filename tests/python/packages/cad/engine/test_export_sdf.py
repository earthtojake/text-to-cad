"""SDF as an export of every document (``export/sdf.py``): a robot description written as an SDFormat 1.9
model -- the exact text of a small hand-built one, its meshes MJCF's bytes beside it, the same bytes written
twice, the repository's own SDF check passing it and the stills reading its links where the description has
them; a ground holding nothing giving way to its fixed child, which the world holds, a cylindrical joint as a
turn and a slide, a ball as SDFormat's, and a loop refused by name; and a jointed model built by the engine
and exported to ``.sdf``, its links moving as the mechanism moves them."""

from __future__ import annotations

import math
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

from cad import sdf
from cad.engine import api, document, mechanism
from cad.engine.description import Collision, Description, Geometry, Inertial, Joint, Link, Mesh, Pose, Visual
from cad.engine.export import ExportRefused, kind_of, refused
from cad.engine.export import mjcf
from cad.engine.export.sdf import write_description
from cad.engine.formats.robot import read_robot, read_sdf


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
<sdf version="1.9">
  <model name="arm">
    <link name="ground">
      <pose relative_to="__model__">0 0 0 0 0 0</pose>
      <visual name="base">
        <pose>0 0 0.05 0 0 0</pose>
        <geometry>
          <box>
            <size>0.4 0.2 0.1</size>
          </box>
        </geometry>
        <material>
          <ambient>0.5 0.5 0.5 1</ambient>
          <diffuse>0.5 0.5 0.5 1</diffuse>
        </material>
      </visual>
    </link>
    <joint name="world_joint" type="fixed">
      <parent>world</parent>
      <child>ground</child>
    </joint>
    <joint name="shoulder" type="revolute">
      <pose relative_to="arm">0 0 0 0 0 0</pose>
      <parent>ground</parent>
      <child>arm</child>
      <axis>
        <xyz>0 0 1</xyz>
        <limit>
          <lower>-1</lower>
          <upper>1.5</upper>
        </limit>
      </axis>
    </joint>
    <link name="arm">
      <pose relative_to="__model__">0 0 0.2 -1.57079633 0 0</pose>
      <inertial>
        <pose>0.15 0 0 0 0 0</pose>
        <mass>2</mass>
        <inertia>
          <ixx>0.001</ixx>
          <ixy>0</ixy>
          <ixz>0</ixz>
          <iyy>0.016</iyy>
          <iyz>0</iyz>
          <izz>0.016</izz>
        </inertia>
      </inertial>
      <visual name="arm">
        <geometry>
          <mesh>
            <uri>meshes/arm_link.stl</uri>
            <scale>1 1 1</scale>
          </mesh>
        </geometry>
        <material>
          <ambient>0.9 0.1 0.1 1</ambient>
          <diffuse>0.9 0.1 0.1 1</diffuse>
        </material>
      </visual>
      <collision name="arm">
        <pose>0.15 0 0 0 1.57079633 0</pose>
        <geometry>
          <capsule>
            <radius>0.02</radius>
            <length>0.3</length>
          </capsule>
        </geometry>
      </collision>
    </link>
    <frame name="tip" attached_to="arm">
      <pose relative_to="arm">0.3 0 0 0 0 0</pose>
    </frame>
    <joint name="knuckle" type="revolute">
      <!-- follows shoulder: knuckle = 0.5 * shoulder + 0.1 (SDFormat 1.9 has no mimic: a simulator \
couples them itself) -->
      <pose relative_to="finger">0 0 0 0 0 0</pose>
      <parent>arm</parent>
      <child>finger</child>
      <axis>
        <xyz>0 0 1</xyz>
        <limit>
          <lower>-0.5</lower>
          <upper>0.75</upper>
        </limit>
      </axis>
    </joint>
    <link name="finger">
      <pose relative_to="__model__">0.3 0 0.2 -1.57079633 0 0</pose>
      <inertial>
        <pose>0.05 0 0 0 0 0</pose>
        <mass>0.5</mass>
        <inertia>
          <ixx>0.0002</ixx>
          <ixy>1e-05</ixy>
          <ixz>0</ixz>
          <iyy>0.0004</iyy>
          <iyz>0</iyz>
          <izz>0.0005</izz>
        </inertia>
      </inertial>
      <visual name="finger">
        <geometry>
          <mesh>
            <uri>meshes/arm_link.stl</uri>
            <scale>1 1 1</scale>
          </mesh>
        </geometry>
        <material>
          <ambient>0.9 0.1 0.1 1</ambient>
          <diffuse>0.9 0.1 0.1 1</diffuse>
        </material>
      </visual>
    </link>
  </model>
</sdf>
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
        self.folder = Path(tempfile.mkdtemp(prefix="export-sdf-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def assertValid(self, path: Path) -> None:
        checked = sdf.validate(path, gz_check="never")
        said = "\n".join(f"{f.severity} {f.code}: {f.message}" for f in checked.findings)
        self.assertTrue(checked.ok, said)
        self.assertEqual([f.code for f in checked.findings if f.severity != "info"], [], said)


class HandBuiltTest(_Folder):
    def test_a_description_is_written_as_sdformat_lays_a_model_out_and_the_stills_read_it_where_it_stands(self) -> None:
        path = self.folder / "arm.sdf"
        written = write_description(arm(), path)
        self.assertEqual(written, [path, self.folder / "meshes" / "arm_link.stl"])
        self.assertEqual(path.read_text(encoding="utf-8"), GOLDEN)
        # The mesh: MJCF's bytes, one writer of them. Written again, elsewhere and in place: the same bytes,
        # and in place nothing moved.
        data = (self.folder / "meshes" / "arm_link.stl").read_bytes()
        self.assertEqual(data, mjcf.rendered(arm())[1]["arm_link.stl"])
        again = self.folder / "again" / "arm.sdf"
        write_description(arm(), again)
        self.assertEqual((again.read_bytes(), (again.parent / "meshes" / "arm_link.stl").read_bytes()),
                         (path.read_bytes(), data))
        before = path.stat().st_mtime_ns, (self.folder / "meshes" / "arm_link.stl").stat().st_mtime_ns
        write_description(arm(), path)
        self.assertEqual((path.stat().st_mtime_ns, (self.folder / "meshes" / "arm_link.stl").stat().st_mtime_ns),
                         before)

        self.assertValid(path)
        robot = read_sdf(path)
        # Every link where the description has it, in the model's space; the ground is SDFormat's ``ground``.
        self.assertEqual((robot.root, sorted(robot.links)), ("ground", ["arm", "finger", "ground"]))
        for link in arm().links:
            placed = robot.links["ground" if link.name == "world" else link.name]
            np.testing.assert_allclose(placed[:3, 3], link.frame[:3, 3], atol=1e-9)
            np.testing.assert_allclose(placed[:3, :3], link.frame[:3, :3], atol=1e-8)
        knuckle = next(joint for joint in robot.joints if joint.name == "knuckle")
        np.testing.assert_allclose(knuckle.frame, SHOULDER @ TIP, atol=1e-8)
        np.testing.assert_allclose(knuckle.axis, (SHOULDER @ TIP)[:3, 2], atol=1e-8)

    def test_a_ground_holding_nothing_gives_way_to_its_fixed_child_which_the_world_holds(self) -> None:
        path = self.folder / "rig.sdf"
        write_description(rig(), path)
        self.assertValid(path)
        text = path.read_text(encoding="utf-8")
        self.assertIn('<joint name="rig" type="fixed">\n      <parent>world</parent>\n      <child>base</child>', text)
        robot = read_sdf(path)
        self.assertEqual(robot.root, "base")
        # The slider's joint yields its name to the slider: links and joints share SDFormat's frame graph.
        self.assertEqual([(j.name, j.type, j.parent, j.child) for j in robot.joints],
                         [("mount", "fixed", "base", "post"), ("slider_2", "continuous", "base", "slider_2_turn"),
                          ("slider_2_slide", "prismatic", "slider_2_turn", "slider")])
        for link in rig().links[1:]:
            np.testing.assert_allclose(robot.links[link.name], link.frame, atol=1e-8)

    def test_a_ball_is_sdformats_and_a_loop_is_refused_by_name(self) -> None:
        path = self.folder / "arm.sdf"
        write_description(arm(shoulder="spherical"), path)
        self.assertIn('<joint name="shoulder" type="ball">', path.read_text(encoding="utf-8"))
        self.assertValid(path)
        loop = self.folder / "loop"
        with self.assertRaisesRegex(ExportRefused, "loop through shoulder"):
            write_description(arm(loops=("shoulder",)), loop / "arm.sdf")
        self.assertFalse(loop.exists())

    def test_sdf_is_the_kind_and_a_mesh_file_is_no_source_of_one(self) -> None:
        self.assertEqual(kind_of("robot.SDF"), "sdf")
        self.assertEqual(refused("part.3mf", "robot.sdf"),
                         "part.3mf is a mesh: it has no B-rep, and no SDF export is made from one")


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
    def test_a_built_hinge_exports_to_an_sdf_whose_links_move_as_its_mechanism_does(self) -> None:
        (self.folder / "hinge.py").write_text(textwrap.dedent(HINGE), encoding="utf-8")
        api.build_script(self.folder / "hinge.py", daemon=False)
        xbf = self.folder / "XBF/hinge.xbf"
        out = self.folder / "robot" / "hinge.sdf"
        [written] = api.export(xbf, out, daemon=False, progress=False)
        self.assertEqual(written.kind, "sdf")
        self.assertTrue(sdf.validate(out, gz_check="never").ok)
        robot = read_robot(out)
        elbow = next(joint for joint in robot.joints if joint.name == "elbow")
        # Its range around the as-built 30 degrees; as built, the arm's frame is the elbow's, on its axis (+Y).
        np.testing.assert_allclose((elbow.lower, elbow.upper), np.radians([-40, 90]), atol=1e-8)
        np.testing.assert_allclose(robot.links["arm"][:3, 2], [0, 1, 0], atol=1e-8)
        np.testing.assert_allclose(robot.links["arm"][[0, 2], 3], [0.04, 0.02], atol=1e-9)
        kinematics = document.Loaded(xbf).structure()["kinematics"]
        names = [link["name"] for link in kinematics["links"]]
        built = mechanism.link_worlds(kinematics, {"elbow": (30.0,)})
        rest = robot.placements(robot.values(None)[0])
        # At each state, every link moved from where it stood as the mechanism moves it: the model's space is the
        # document's.
        for state, degrees in (("raised", 90.0), ("flat", 0.0)):
            posed = mechanism.link_worlds(kinematics, {"elbow": (degrees,)})
            placed = robot.placements(robot.values({"elbow": degrees - 30})[0])
            for at, name in enumerate(names):
                moved = placed[name] @ np.linalg.inv(rest[name])
                np.testing.assert_allclose(moved, posed[at] @ np.linalg.inv(built[at]), atol=1e-6,
                                           err_msg=f"{name} at {state}")


if __name__ == "__main__":
    unittest.main()

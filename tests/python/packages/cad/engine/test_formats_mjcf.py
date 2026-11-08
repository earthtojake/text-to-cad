"""An MJCF as the stills draw it (`engine/formats/robot.py` `read_mjcf`, over the mjcf type's own reader,
`cad.mjcf._source`): its bodies the links, its hinge and slide the joints, the geoms of groups 0 to 2 the
visuals (a box, a capsule by ``fromto``, a sphere, a binary STL, an OBJ) and its keyframe a pose by its
name; placed as the URDF reader places the same robot written as a URDF, and drawn as one still.

The fixtures are made here, small, in a folder of the test's own.
"""

from __future__ import annotations

import math
import shutil
import struct
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

from cad.engine import formats
from cad.engine.render import context
from tests.python.support import opengl

MJCF = """\
<mujoco model="rig">
  <compiler angle="degree" meshdir="meshes"/>
  <asset>
    <mesh name="tet" file="tet.stl" scale="0.001 0.001 0.001"/>
    <mesh file="cube.obj"/>
    <material name="red" rgba="1 0 0 1"/>
  </asset>
  <worldbody>
    <geom name="floor" type="box" size="0.2 0.2 0.01" pos="0 0 -0.01"/>
    <body name="base" pos="0 0 0.1">
      <geom name="post" type="capsule" fromto="0 0 0 0 0 0.1" size="0.01"/>
      <geom name="hull" type="box" size="0.05 0.05 0.05" group="3"/>
      <body name="arm" pos="0 0 0.1">
        <joint name="shoulder" type="hinge" axis="0 1 0" range="-90 90"/>
        <geom name="ball" type="sphere" size="0.02" pos="0.1 0 0" material="red"/>
        <geom name="tip" type="mesh" mesh="tet"/>
        <body name="slider" pos="0.1 0 0">
          <joint name="reach" type="slide" axis="1 0 0" range="0 0.05"/>
          <geom name="block" type="mesh" mesh="cube"/>
        </body>
      </body>
    </body>
  </worldbody>
  <keyframe><key name="raised" qpos="-1.5707963267948966 0.02"/></keyframe>
</mujoco>
"""

# The same robot as a URDF: the URDF reader's placements are the ones the MJCF's must equal.
URDF = """\
<robot name="rig">
  <link name="world"/>
  <link name="base"/>
  <link name="arm"/>
  <link name="slider"/>
  <joint name="base_fixed" type="fixed"><parent link="world"/><child link="base"/><origin xyz="0 0 0.1"/></joint>
  <joint name="shoulder" type="revolute"><parent link="base"/><child link="arm"/><origin xyz="0 0 0.1"/>
    <axis xyz="0 1 0"/><limit lower="-1.5707963267948966" upper="1.5707963267948966"/></joint>
  <joint name="reach" type="prismatic"><parent link="arm"/><child link="slider"/><origin xyz="0.1 0 0"/>
    <axis xyz="1 0 0"/><limit lower="0" upper="0.05"/></joint>
</robot>
"""

# A 20 mm cube centred on its origin, in metres: quads (fanned), v/vt/vn faces and negative indices.
CUBE_OBJ = """\
# a cube
mtllib cube.mtl
v -0.01 -0.01 -0.01
v 0.01 -0.01 -0.01
v 0.01 0.01 -0.01
v -0.01 0.01 -0.01
v -0.01 -0.01 0.01
v 0.01 -0.01 0.01
v 0.01 0.01 0.01
v -0.01 0.01 0.01
vt 0 0
vn 0 0 1
usemtl grey
f 1/1/1 4/1/1 3/1/1 2/1/1
f 5//1 6//1 7//1 8//1
f -8 -7 -3 -4
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""


def write_tetrahedron(path: Path) -> Path:
    """A binary STL of one tetrahedron, 10 mm on a side along each axis (its numbers millimetres)."""
    corners = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], float)
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    facets = np.zeros(len(faces), [("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])
    facets["corners"] = [[corners[a], corners[b], corners[c]] for a, b, c in faces]
    path.write_bytes(b"\0" * 80 + struct.pack("<I", len(faces)) + facets.tobytes())
    return path


class MjcfRobotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-formats-mjcf-")).resolve()
        (cls.folder / "meshes").mkdir()
        write_tetrahedron(cls.folder / "meshes" / "tet.stl")
        (cls.folder / "meshes" / "cube.obj").write_text(CUBE_OBJ, encoding="utf-8")
        cls.path = cls.folder / "rig.xml"
        cls.path.write_text(MJCF, encoding="utf-8")
        (cls.folder / "rig.urdf").write_text(URDF, encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_the_bodies_are_links_and_the_visual_geoms_their_visuals(self) -> None:
        from cad.engine.formats.robot import read_robot

        robot = read_robot(self.path)
        self.assertEqual((robot.kind, robot.name, robot.root), ("mjcf", "rig", "world"))
        self.assertEqual(list(robot.links), ["world", "base", "arm", "slider"])
        np.testing.assert_allclose(robot.links["arm"][:3, 3], (0, 0, 0.2), atol=1e-12)
        self.assertEqual([(joint.name, joint.type, joint.parent, joint.child) for joint in robot.joints],
                         [("base", "fixed", "world", "base"), ("shoulder", "revolute", "base", "arm"),
                          ("reach", "prismatic", "arm", "slider")])
        shoulder = robot.joints[1]
        np.testing.assert_allclose(shoulder.axis, (0, 1, 0), atol=1e-12)
        self.assertAlmostEqual(shoulder.lower, -math.pi / 2)
        self.assertAlmostEqual(robot.joints[2].upper, 0.05)
        meshes = {link: [visual.mesh for visual in visuals] for link, visuals in robot.visuals.items()}
        self.assertEqual(meshes["world"], [("box", (0.4, 0.4, 0.02))])
        self.assertEqual(meshes["base"], [("capsule", (0.01, 0.1))], "the group-3 hull is a collision geom")
        self.assertEqual(meshes["arm"][0], ("sphere", (0.02,)))
        self.assertEqual(meshes["arm"][1], ("file", self.folder / "meshes" / "tet.stl", (0.001, 0.001, 0.001)))
        self.assertEqual(meshes["slider"], [("file", self.folder / "meshes" / "cube.obj", (1.0, 1.0, 1.0))])
        np.testing.assert_allclose(robot.visuals["base"][0].local[:3, 3], (0, 0, 0.05), atol=1e-12)  # fromto's middle
        self.assertEqual(robot.visuals["arm"][0].color, "#ff0000")
        self.assertEqual({key: sorted(values) for key, values in robot.poses.items()}, {"raised": ["reach", "shoulder"]})
        self.assertAlmostEqual(robot.poses["raised"]["shoulder"], -90.0)
        self.assertEqual({path.name for path in robot.files}, {"rig.xml", "tet.stl", "cube.obj"})

    def test_a_keyframe_poses_it_by_name_as_the_urdf_reader_poses_the_same_robot(self) -> None:
        from cad.engine.formats.robot import read_robot

        mjcf, urdf = read_robot(self.path), read_robot(self.folder / "rig.urdf")
        values, named = mjcf.values("raised")
        self.assertEqual(named, "raised")
        placed, reference = mjcf.placements(values), urdf.placements(urdf.values({"shoulder": -90, "reach": 0.02})[0])
        for link in ("base", "arm", "slider"):
            with self.subTest(link=link):
                np.testing.assert_allclose(placed[link], reference[link], atol=1e-9)
        # By hand: the arm turned -90 degrees about y points its x up, so the slider rises 0.1 m and slides 0.02 m.
        np.testing.assert_allclose(placed["slider"][:3, 3], (0, 0, 320), atol=1e-6)
        with self.assertRaisesRegex(ValueError, "no keyframe 'lowered'; its keyframes: raised"):
            mjcf.values("lowered")

    def test_the_stills_hold_a_part_per_visual_placed_at_its_pose(self) -> None:
        found = formats.read(self.path)
        self.assertEqual(found.kind, "mjcf")
        self.assertEqual(len(found.structure["prototypes"]), 5)
        self.assertEqual([instance["visual"] for instance in found.structure["instances"]],
                         ["world:v1", "base:v1", "arm:v1", "arm:v2", "slider:v1"])
        self.assertEqual(found.structure["millimetresPerUnit"], 1000.0)
        cube = found.structure["prototypes"][4]
        self.assertEqual(cube["name"], "cube")
        posed = found.pose(found.structure, "raised")
        block = np.array(posed["instances"][4]["matrix"]).reshape(4, 4).T
        np.testing.assert_allclose(block[:3, 3], (0, 0, 320), atol=1e-6)
        self.assertEqual(posed["kinematics"]["pose"]["configuration"], "raised")
        self.assertIn(str(self.folder / "meshes" / "cube.obj"), found.files)

    def test_an_mjcf_the_reader_refuses_is_refused_with_its_errors(self) -> None:
        bad = self.folder / "bad.mjcf"
        bad.write_text('<mujoco><worldbody><geom type="mesh" mesh="nothing"/></worldbody></mujoco>', encoding="utf-8")
        with self.assertRaisesRegex(formats.FormatError, r"bad\.mjcf cannot be read as an MJCF:\n.*nothing"):
            formats.read(bad)

    def test_a_snapshot_at_a_keyframe_is_a_picture(self) -> None:
        from cad.engine.snapshot import snapshot

        opengl.require(context.available())
        out = self.folder / "raised.png"
        snapshot(self.path, out, pose="raised", size=(160, 120), daemon=False)
        data = out.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(data), 1000)


class ObjTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-formats-obj-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def write(self, text: str) -> Path:
        path = self.folder / "part.obj"
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def test_quads_are_fanned_and_a_negative_index_counts_from_the_end(self) -> None:
        from cad.engine.formats.obj import read_obj

        points, triangles = read_obj(self.write(CUBE_OBJ))
        self.assertEqual(points.shape, (8, 3))
        self.assertEqual(triangles.shape, (12, 3))
        self.assertEqual(triangles[0].tolist(), [0, 3, 2])  # 1/1/1 4/1/1 3/1/1: the vertex of v/vt/vn
        self.assertEqual(triangles[4].tolist(), [0, 1, 5])  # f -8 -7 -3 -4 after eight vertices

    def test_what_is_no_triangle_mesh_is_refused_by_name(self) -> None:
        from cad.engine.formats.obj import ObjError, read_obj

        for text, why in (("v 0 0 0\n", "has no faces"), ("v 0 0 0\nv 1 0 0\nf 1 2\n", "fewer than three"),
                          ("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 4\n", "names a vertex it does not have"),
                          ("v 0 0 0\nf 0 1 2\n", "index of 0"), ("v 0 0 x\n", "not three numbers")):
            with self.subTest(text=text), self.assertRaisesRegex(ObjError, why):
                read_obj(self.write(text))

    def test_an_obj_link_mesh_is_a_part_in_millimetres_by_the_description_s_scale(self) -> None:
        from cad.engine.formats.robot import _mesh_parts

        path = self.write(CUBE_OBJ)
        [(part, placement)] = _mesh_parts(("file", path, (2.0, 2.0, 2.0)), "", "a visual")
        np.testing.assert_array_equal(placement, np.eye(4))
        positions = np.asarray(part.mesh.positions).reshape(-1, 3)
        np.testing.assert_allclose(positions.max(axis=0) - positions.min(axis=0), (40, 40, 40), atol=1e-4)
        self.assertEqual(len(part.mesh.edges), 12, "a cube's lines are its twelve folds, as an STL's are")


def setUpModule() -> None:
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()

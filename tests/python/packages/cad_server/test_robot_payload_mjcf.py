"""``cad_server.robot_payload`` for an MJCF: MuJoCo's XML resolved into the robot view's payload.

Every model here is written into a fresh temporary workspace: nothing reads the sample corpus. One
model holds every case -- a compiler in degrees with a mesh folder, a default class, an include, a
free root, a hinge with a range and a slide with none, a box, a capsule by ``fromto``, a sphere, an
STL and an OBJ mesh, a collision geom in group 3 and a keyframe -- and the cases pin what each
becomes: links, joints and controls, the visuals drawn and the one not, the OBJ served as a GLB by
its digest, the keyframe in control units, and an ``.xml`` that is no MJCF refused by name. The
scanner's half: a ``package.xml`` is no catalog row, an MJCF ``.xml`` is.
"""

from __future__ import annotations

import json
import math
import os
import struct
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cad/src")

from cad_server import robot_payload  # noqa: E402
from cad_server.robot_payload import (RobotReadError, locate_robot_payload, prepare_robot_description,  # noqa: E402
                                      primitive_glb_bytes, read_robot_description, robot_control_values,
                                      robot_payload_bytes)
from cad_server.viewer.robots import robot_response  # noqa: E402
from cad_server.viewer.scanner import catalog_entry, is_catalog_file, is_served_cad_asset  # noqa: E402

SCENE = """<mujoco model="rig">
  <compiler angle="degree" meshdir="meshes"/>
  <include file="assets.xml"/>
  <default>
    <default class="arm"><geom rgba="0.8 0.2 0.2 1"/><joint damping="1"/></default>
  </default>
  <worldbody>
    <body name="base" pos="0 0 0.1">
      <freejoint name="float"/>
      <geom name="base_box" type="box" size="0.1 0.1 0.05"/>
      <geom name="base_hull" type="box" size="0.1 0.1 0.05" group="3"/>
      <body name="arm" pos="0 0 0.1" childclass="arm">
        <joint name="shoulder" type="hinge" axis="0 1 0" range="-90 90"/>
        <geom name="arm_bar" type="capsule" fromto="0 0 0 0.3 0 0" size="0.02"/>
        <geom name="arm_mesh" type="mesh" mesh="tetra"/>
        <body name="slider" pos="0.3 0 0">
          <joint name="extend" type="slide" axis="1 0 0"/>
          <geom name="tip" type="sphere" size="0.03"/>
          <geom name="cube" type="mesh" mesh="cube"/>
        </body>
      </body>
    </body>
  </worldbody>
  <keyframe><key name="home" qpos="0 0 0.1 1 0 0 0 0.5 0.02"/></keyframe>
</mujoco>
"""
ASSETS = """<mujoco>
  <asset>
    <mesh name="tetra" file="tetra.stl" scale="0.001 0.001 0.001"/>
    <mesh file="cube.obj" scale="{scale}"/>
  </asset>
</mujoco>
"""
CUBE_OBJ = "\n".join(
    [f"v {x} {y} {z}" for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    + ["f 1 3 4 2", "f 5 6 8 7", "f 1 2 6 5", "f 3 7 8 4", "f 1 5 7 3", "f 2 4 8 6"]
) + "\n"


def tetrahedron_stl() -> bytes:
    """A binary STL of four triangles: a tetrahedron, in millimetres."""
    corners = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (0.0, 0.0, 10.0)]
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    body = b"".join(struct.pack("<12fH", 0.0, 0.0, 0.0, *corners[a], *corners[b], *corners[c], 0) for a, b, c in faces)
    return b"\0" * 80 + struct.pack("<I", len(faces)) + body


def translation(placement: list[float]) -> list[float]:
    return [round(placement[index], 9) + 0.0 for index in (3, 7, 11)]


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        folder = temporary_directory(prefix="robot-payload-mjcf-")
        self.addCleanup(folder.cleanup)
        self.root = Path(os.path.realpath(folder.name))
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        (self.root / "meshes").mkdir()
        (self.root / "meshes" / "tetra.stl").write_bytes(tetrahedron_stl())
        (self.root / "meshes" / "cube.obj").write_text(CUBE_OBJ, encoding="utf-8")
        self.write("assets.xml", ASSETS.format(scale="0.01 0.01 0.01"))
        self.scene = self.write("scene.xml", SCENE)

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path


class MjcfPayload(_Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.payload = read_robot_description(self.scene)
        self.visuals = {visual["label"]: visual for visual in self.payload["visuals"]}
        self.joints = {joint["name"]: joint for joint in self.payload["joints"]}

    def test_bodies_are_links_under_the_world_and_the_free_root_is_fixed(self) -> None:
        payload = self.payload
        self.assertEqual((payload["schemaVersion"], payload["kind"], payload["name"], payload["root"]), (2, "mjcf", "rig", "world"))
        self.assertEqual([link["name"] for link in payload["links"]], ["world", "base", "arm", "slider"])
        self.assertEqual(translation(next(link for link in payload["links"] if link["name"] == "arm")["placement"]), [0.0, 0.0, 0.2])
        self.assertEqual({name: joint["type"] for name, joint in self.joints.items()},
                         {"float": "fixed", "shoulder": "revolute", "extend": "prismatic"})
        self.assertEqual(self.joints["float"]["mjcfType"], "free")
        self.assertEqual([(joint["id"], joint["kind"]) for joint in payload["articulation"]["joints"]],
                         [("float", "fixed"), ("shoulder", "revolute"), ("extend", "slider")])

    def test_controls_are_the_hinge_at_its_range_and_the_slide_unbounded(self) -> None:
        articulation = self.payload["articulation"]
        controls = {control["id"]: control for control in articulation["controls"]}
        self.assertEqual(set(controls), {"shoulder", "extend"})
        self.assertEqual((controls["shoulder"]["unit"], controls["shoulder"]["min"], controls["shoulder"]["max"]), ("deg", -90.0, 90.0))
        # A slide with no range has no limits, as a continuous joint has none: the page slides it a metre about zero.
        self.assertEqual((controls["extend"]["unit"], controls["extend"]["min"], controls["extend"]["max"]), ("m", None, None))
        self.assertEqual(articulation["opening"], {"shoulder": 0.0, "extend": 0.0}, "the model opens at qpos0")
        self.assertEqual(robot_control_values(self.payload, {"extend": 3.0})["extend"], 3.0)

    def test_the_keyframe_is_a_pose_in_control_units(self) -> None:
        home = self.payload["articulation"]["poses"]["home"]
        self.assertAlmostEqual(home["shoulder"], math.degrees(0.5), places=9)
        self.assertAlmostEqual(home["extend"], 0.02, places=12)
        self.assertNotIn("float", home)

    def test_drawn_geoms_are_visuals_and_the_collision_geom_is_not(self) -> None:
        self.assertEqual(set(self.visuals), {"base_box", "arm_bar", "arm_mesh", "tip", "cube"})
        base = next(link for link in self.payload["links"] if link["name"] == "base")
        self.assertEqual([facts["name"] for facts in base["collisions"]], ["base_hull"])
        self.assertEqual(base["collisions"][0]["group"], 3)
        box_facts = base["visuals"][0]
        self.assertEqual((box_facts["type"], box_facts["group"], box_facts["size"], box_facts["alpha"]), ("box", 0, [0.1, 0.1, 0.05], 1.0))
        # The capsule by fromto: centred halfway along it, its axis along the arm, coloured by its class.
        bar = self.visuals["arm_bar"]
        self.assertEqual(translation(bar["placement"]), [0.15, 0.0, 0.2])
        self.assertEqual(bar["color"], "#cc3333")
        z_axis = [bar["placement"][index] / 0.001 for index in (2, 6, 10)]
        self.assertEqual([round(abs(value), 9) for value in z_axis], [1.0, 0.0, 0.0])
        self.assertTrue(all(visual["mesh"]["format"] == "glb" and visual["mesh"].get("object")
                            for name, visual in self.visuals.items() if name in ("base_box", "arm_bar", "tip")))

    def test_an_stl_is_its_file_and_an_obj_a_glb_by_its_digest(self) -> None:
        stl = self.visuals["arm_mesh"]
        self.assertEqual(stl["mesh"], {"format": "stl", "path": str(self.root / "meshes" / "tetra.stl")})
        self.assertAlmostEqual(stl["placement"][0], 0.001, places=12)  # the mesh scale, millimetres to metres
        cube = self.visuals["cube"]
        self.assertEqual(cube["mesh"]["format"], "glb")
        # The GLB holds the OBJ's numbers; the placement carries the page's GLB unit and the mesh scale.
        self.assertAlmostEqual(cube["placement"][0], 0.001 * 0.01, places=15)
        located = locate_robot_payload(self.payload, file_url=lambda path: f"file:{Path(path).name}",
                                       object_url=lambda digest: f"/api/v1/documents/mjcf/x/parts/{digest}")
        located_cube = next(visual for visual in located["visuals"] if visual["label"] == "cube")
        self.assertEqual(located_cube["mesh"], {"format": "glb", "url": f"/api/v1/documents/mjcf/x/parts/{cube['mesh']['object']}"})
        status, body, content_type = robot_response(str(self.scene), cube["mesh"]["object"], api="/api/v1/documents/mjcf/x")
        self.assertEqual((status, content_type, body[:4]), (200, "model/gltf-binary", b"glTF"))
        self.assertEqual(body, primitive_glb_bytes(cube["mesh"]["object"]))

    def test_preparation_meshes_nothing(self) -> None:
        with mock.patch.dict("sys.modules", {"cad_server._internal.primitive_mesh": None}):
            prepared = prepare_robot_description(self.scene)
        self.assertEqual(sum("_obj" in visual["mesh"] for visual in prepared["visuals"]), 1)
        self.assertNotIn("_obj", json.dumps(self.payload))

    def test_an_edited_include_is_read_again(self) -> None:
        first = json.loads(robot_payload_bytes(self.scene))
        with mock.patch.object(robot_payload, "read_robot_description", side_effect=AssertionError("read twice")):
            self.assertEqual(json.loads(robot_payload_bytes(self.scene)), first)
        self.write("assets.xml", ASSETS.format(scale="0.02 0.02 0.02"))
        cube = next(visual for visual in json.loads(robot_payload_bytes(self.scene))["visuals"] if visual["label"] == "cube")
        self.assertAlmostEqual(cube["placement"][0], 0.001 * 0.02, places=15)


class MjcfRefusals(_Workspace):
    def test_an_xml_that_is_no_mjcf_is_refused_by_name(self) -> None:
        robot = self.write("robot.xml", '<?xml version="1.0"?>\n<robot name="r"><link name="base"/></robot>\n')
        with self.assertRaisesRegex(RobotReadError, r"robot\.xml is not an MJCF: .*<mujoco>"):
            prepare_robot_description(robot)

    def test_a_missing_include_is_refused_in_the_reader_s_words(self) -> None:
        (self.root / "assets.xml").unlink()
        with self.assertRaisesRegex(RobotReadError, "assets.xml"):
            prepare_robot_description(self.scene)


class MjcfCatalog(_Workspace):
    def test_only_an_mjcf_xml_is_a_catalog_file(self) -> None:
        package = self.write("package.xml", '<?xml version="1.0"?>\n<package format="3"><name>rig</name></package>\n')
        self.assertFalse(is_catalog_file(str(package)))
        self.assertIsNone(catalog_entry(str(package)))
        self.assertFalse(is_served_cad_asset(str(package)))
        self.assertTrue(is_catalog_file(str(self.scene)))
        self.assertTrue(is_served_cad_asset(str(self.scene)))
        self.assertEqual(catalog_entry(str(self.scene))["file"], str(self.scene).replace(os.sep, "/"))
        self.assertTrue(is_catalog_file(str(self.write("arm.mjcf", SCENE))))


if __name__ == "__main__":
    unittest.main()

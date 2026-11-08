"""A URDF and an SDF are each read once, in the engine (``cad.engine.urdf_source``, ``cad.engine.sdf_source``,
the one articulation of ``cad.engine.robot_model``), and the viewer's payload (``cad_server.robot_payload``)
and the stills (``cad.engine.formats.robot``) are two views of that read: every link frame at rest, and every
joint -- its type, its links, its anchor, its axis, its range -- is the engine's in each.

The fixtures are made here, small, in a folder of the test's own.
"""

from __future__ import annotations

import math
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from cad.engine import sdf_source, urdf_source
from cad.engine.formats.robot import read_robot
from cad_server.robot_payload import prepare_robot_description

# A turret, an arm on a tilted shoulder, a slide on it with a mimic twin, a tool fixed to the slide, and
# a link mesh: rpy origins all the way down, an axis that is no unit vector.
URDF = """<?xml version="1.0"?>
<robot name="rig">
  <link name="base"><visual><origin xyz="0 0 0.01"/><geometry><box size="0.3 0.2 0.02"/></geometry></visual></link>
  <link name="turret"><visual><geometry><mesh filename="meshes/tet.stl" scale="0.001 0.001 0.001"/></geometry></visual></link>
  <link name="arm"><visual><origin xyz="0.06 0 0" rpy="0 1.5707963 0"/><geometry><cylinder radius="0.01" length="0.12"/></geometry></visual></link>
  <link name="slider"><visual><geometry><sphere radius="0.015"/></geometry></visual></link>
  <link name="twin"/>
  <link name="tool"/>
  <joint name="spin" type="continuous"><parent link="base"/><child link="turret"/><origin xyz="0.05 -0.02 0.02" rpy="0 0 0.3"/><axis xyz="0 0 1"/></joint>
  <joint name="lift" type="revolute"><parent link="turret"/><child link="arm"/><origin xyz="0 0 0.06" rpy="0.2 -0.1 0"/><axis xyz="0 1 0.2"/><limit lower="-1.2" upper="1.4" effort="1" velocity="1"/></joint>
  <joint name="reach" type="prismatic"><parent link="arm"/><child link="slider"/><origin xyz="0.12 0 0" rpy="0 0 0.5"/><axis xyz="1 0 0"/><limit lower="-0.02" upper="0.05" effort="1" velocity="1"/></joint>
  <joint name="mirror" type="prismatic"><parent link="arm"/><child link="twin"/><origin xyz="0.08 0 0.015"/><axis xyz="1 0 0"/><limit lower="-0.05" upper="0.02" effort="1" velocity="1"/><mimic joint="reach" multiplier="-1"/></joint>
  <joint name="mount" type="fixed"><parent link="slider"/><child link="tool"/><origin xyz="0.02 0.01 0" rpy="0.4 0 0.2"/></joint>
</robot>
"""

# A post, an arm placed relative to a frame of the model, and a nested hand whose link is named by
# scope: a joint whose pose is its child's, an axis expressed in the model's frame.
SDF = """<?xml version="1.0"?>
<sdf version="1.9">
  <model name="rig">
    <pose>0 0 0.1 0 0 0.2</pose>
    <frame name="shelf"><pose>1 0 0.5 0 0 0</pose></frame>
    <link name="post"><visual name="v"><geometry><box><size>0.1 0.1 0.1</size></box></geometry></visual></link>
    <link name="arm"><pose relative_to="shelf">0 0 0 0 0 1.5707963267948966</pose>
      <visual name="v"><pose>0.2 0 0 0 0 0</pose><geometry><capsule><radius>0.02</radius><length>0.3</length></capsule></geometry></visual></link>
    <joint name="swing" type="revolute"><parent>post</parent><child>arm</child>
      <axis><xyz expressed_in="__model__">0 0 1</xyz><limit><lower>-2</lower><upper>2</upper></limit></axis></joint>
    <model name="hand"><pose relative_to="arm">0.4 0 0 0.3 0 0</pose>
      <link name="palm"><visual name="v"><geometry><sphere><radius>0.03</radius></sphere></geometry></visual></link>
    </model>
    <joint name="wrist" type="prismatic"><pose>0 0 0.01 0 0 0</pose><parent>arm</parent><child>hand::palm</child>
      <axis><xyz>0 1 0</xyz><limit><lower>0</lower><upper>0.1</upper></limit></axis></joint>
  </model>
</sdf>
"""


def _stl(path: Path) -> None:
    """A tetrahedron, millimetres, as ASCII STL."""
    corners = [(0, 0, 0), (40, 0, 0), (0, 40, 0), (0, 0, 40)]
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    facets = "".join("facet normal 0 0 0\nouter loop\n" + "".join(f"vertex {x} {y} {z}\n" for x, y, z in
                                                                  (corners[i] for i in face)) + "endloop\nendfacet\n"
                     for face in faces)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"solid tet\n{facets}endsolid tet\n", encoding="ascii")


class OneSourceTwoViews(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="robot-sources-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        _stl(self.folder / "meshes" / "tet.stl")

    def write(self, name: str, text: str) -> Path:
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def assert_one_source(self, path: Path, articulation) -> None:
        payload = prepare_robot_description(path)
        robot = read_robot(path)
        engine = {name: np.asarray(frame, float) for name, frame in articulation.links.items()}
        self.assertEqual([link["name"] for link in payload["links"]], list(engine))
        self.assertEqual(list(robot.links), list(engine))
        for link in payload["links"]:
            with self.subTest(link=link["name"]):
                np.testing.assert_allclose(np.asarray(link["placement"]).reshape(4, 4), engine[link["name"]], atol=1e-9)
                np.testing.assert_allclose(robot.links[link["name"]], engine[link["name"]], atol=1e-12)
        # The stills place every link where the engine does at the opening pose (their millimetres).
        opened = robot.placements(robot.opening())
        for name, frame in engine.items():
            moved = opened[name].copy()
            moved[:3, 3] /= 1000
            np.testing.assert_allclose(moved, frame, atol=1e-9, err_msg=name)

        rows = {row["id"]: row for row in payload["articulation"]["joints"]}
        facts = {joint["name"]: joint for joint in payload["joints"]}
        stills = {joint.name: joint for joint in robot.joints}
        for joint in articulation.joints:
            with self.subTest(joint=joint.name):
                row, fact = rows[joint.name], facts[joint.name]
                self.assertEqual((fact["type"], fact["parent"], fact["child"]), (joint.type, joint.parent, joint.child))
                if joint.parent:  # a joint to the world holds its child where it is, in the stills
                    held = stills[joint.name]
                    self.assertEqual((held.type, held.parent, held.child, held.mimic), (joint.type, joint.parent, joint.child,
                                                                                        joint.mimic))
                    np.testing.assert_allclose(held.frame, np.asarray(joint.frame, float), atol=1e-12)
                    self.assertEqual((held.lower, held.upper), (joint.lower, joint.upper))
                if joint.type == "fixed":
                    self.assertEqual(row["kind"], "fixed")
                    continue
                np.testing.assert_allclose(row["origin"], [joint.frame[i][3] for i in range(3)], atol=1e-9)
                np.testing.assert_allclose(row["axis"], joint.axis, atol=1e-9)
                np.testing.assert_allclose(stills[joint.name].axis, joint.axis, atol=1e-12)
                self.assertAlmostEqual(np.linalg.norm(joint.axis), 1.0)
                control = next((control for control in payload["articulation"]["controls"] if control["id"] == joint.name), None)
                if control is not None and joint.lower is not None:
                    unit = 180 / math.pi if joint.type in ("revolute", "continuous") else 1.0
                    self.assertAlmostEqual(control["min"], joint.lower * unit)
                    self.assertAlmostEqual(control["max"], joint.upper * unit)

    def test_a_urdf_is_one_read_the_payload_and_the_stills_view(self) -> None:
        path = self.write("rig.urdf", URDF)
        articulation = urdf_source.read_urdf(path)
        self.assertEqual(articulation.root, "base")
        self.assertEqual(articulation.joints[3].mimic, ("reach", -1.0, 0.0))
        (turret,) = articulation.visuals["turret"]
        self.assertEqual(turret.shape, ("file", (self.folder / "meshes" / "tet.stl").resolve(), [0.001, 0.001, 0.001]))
        self.assert_one_source(path, articulation)

    def test_an_sdf_is_one_read_the_payload_and_the_stills_view(self) -> None:
        path = self.write("rig.sdf", SDF)
        articulation = sdf_source.read_sdf(path)
        self.assertEqual(list(articulation.links), ["post", "arm", "hand::palm"])
        self.assertEqual([(joint.name, joint.parent, joint.child) for joint in articulation.joints],
                         [("swing", "post", "arm"), ("wrist", "arm", "hand::palm")])
        self.assertEqual(articulation.visuals["arm"][0].shape, ("capsule", {"radius": 0.02, "length": 0.3}))
        self.assert_one_source(path, articulation)


if __name__ == "__main__":
    unittest.main()

"""``cadgen.robot_payload``: a robot description resolved into what a page plays and draws.

Every description here is written into a fresh temporary workspace with a store of its own:
nothing reads the sample corpus. Each case holds one contract -- the articulation a URDF's
joints become (its rows, limits, mimic terms, handles and opening), the rest placements an
SDF's frame graph resolves to, an SRDF's poses, cadgen's primitive meshes in the store, the
cache, and every refusal with the sentence it says.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import struct
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import robot_payload  # noqa: E402
from cadgen.articulation import joint_matrices, joint_values  # noqa: E402
from cadgen.robot_payload import (  # noqa: E402
    FOUR_BAR_CURVE_TOLERANCE_DEG,
    ROBOT_PAYLOAD_SCHEMA_VERSION,
    RobotReadError,
    four_bar_input_angle,
    locate_robot_payload,
    read_robot_description,
    robot_control_values,
    robot_payload_bytes,
)
from cadgen.store.objects import object_path, read_verified_object  # noqa: E402
from cadgen.tessellation_policy import DEFAULT_TESSELLATION  # noqa: E402


def box(size: str, xyz: str = "0 0 0", rgba: str = "") -> str:
    material = f'<material name="m"><color rgba="{rgba}"/></material>' if rgba else ""
    return f'<visual><origin xyz="{xyz}"/><geometry><box size="{size}"/></geometry>{material}</visual>'


def limit(lower: float, upper: float) -> str:
    return f'<limit lower="{lower}" upper="{upper}" effort="1" velocity="1"/>'


# base -(shoulder, revolute Y, 0.2 up)-> upper_arm; base -(lift, prismatic Z)-> carriage -(grip,
# prismatic Y)-> finger_left and -(grip_mirror = -grip)-> finger_right; base -(spin, continuous,
# a wheel on its own axis)-> wheel; a fixed camera mount.
ARM_URDF = f"""<?xml version="1.0"?>
<robot name="arm">
  <material name="steel"><color rgba="0.5 0.5 0.55 1"/></material>
  <link name="base">{box('0.4 0.4 0.1', '0 0 0.05', '0.3 0.3 0.35 1')}
    <inertial><mass value="2.5"/><origin xyz="0 0 0.05"/><inertia ixx="0.01" ixy="0" ixz="0" iyy="0.02" iyz="0" izz="0.03"/></inertial>
    <collision><geometry><cylinder radius="0.2" length="0.1"/></geometry></collision></link>
  <link name="upper_arm"><visual><origin xyz="0.25 0 0" rpy="0 0 0.3"/><geometry><box size="0.5 0.08 0.08"/></geometry><material name="steel"/></visual></link>
  <link name="carriage">{box('0.1 0.1 0.1')}</link>
  <link name="camera"/>
  <link name="finger_left">{box('0.02 0.02 0.08', '0 0 0.09')}</link>
  <link name="finger_right">{box('0.02 0.02 0.08', '0 0 0.09')}</link>
  <link name="wheel"><visual><geometry><cylinder radius="0.3" length="0.1"/></geometry></visual></link>
  <joint name="shoulder" type="revolute"><parent link="base"/><child link="upper_arm"/><origin xyz="0 0 0.2"/><axis xyz="0 1 0"/>{limit(-1.5708, 1.5708)}</joint>
  <joint name="lift" type="prismatic"><parent link="base"/><child link="carriage"/><origin xyz="-0.15 0.15 0.15"/><axis xyz="0 0 1"/>{limit(0, 0.3)}</joint>
  <joint name="camera_mount" type="fixed"><parent link="base"/><child link="camera"/><origin xyz="0.15 -0.15 0.13" rpy="0 0.5 0"/></joint>
  <joint name="grip" type="prismatic"><parent link="carriage"/><child link="finger_left"/><origin xyz="0 0.01 0"/><axis xyz="0 1 0"/>{limit(0, 0.04)}</joint>
  <joint name="grip_mirror" type="prismatic"><parent link="carriage"/><child link="finger_right"/><origin xyz="0 -0.01 0"/><axis xyz="0 1 0"/>{limit(-0.04, 0)}<mimic joint="grip" multiplier="-1"/></joint>
  <joint name="spin" type="continuous"><parent link="base"/><child link="wheel"/><origin xyz="0 2 0" rpy="1.5708 0 0"/><axis xyz="0 0 1"/></joint>
</robot>
"""
ARM_SRDF = """<?xml version="1.0"?>
<robot name="arm">
  <group name="arm"><joint name="shoulder"/><joint name="lift"/></group>
  <group name="gripper"><joint name="grip"/></group>
  <end_effector name="tool" parent_link="carriage" group="gripper" parent_group="arm"/>
  <group_state name="home" group="arm"><joint name="shoulder" value="-0.5"/><joint name="lift" value="0.1"/></group_state>
  <group_state name="raised" group="arm"><joint name="shoulder" value="-1.0"/><joint name="lift" value="0.2"/></group_state>
</robot>
"""
# An SDF joint posed relative to a link, its child posed relative to the joint (so the joint frame
# and the child frame differ), a frame attached to the child, and a sphere posed relative to it.
SWING_SDF = """<?xml version="1.0"?>
<sdf version="1.9"><world name="lab"><light name="sun" type="directional"/><model name="swing">
  <link name="base"><visual name="v"><pose>0 0 0.05 0 0 0</pose><geometry><box><size>0.4 0.4 0.1</size></box></geometry>
    <material><diffuse>0.1 0.8 0.1 1</diffuse></material></visual></link>
  <link name="arm"><pose relative_to="hinge">0.05 0 0 0 0 0</pose><visual name="v"><pose>0.25 0 0 0 0 0</pose><geometry><box><size>0.5 0.08 0.06</size></box></geometry></visual></link>
  <frame name="tip" attached_to="arm"><pose>0.5 0 0 0 0 0</pose></frame>
  <link name="ball"><pose relative_to="tip">0 0 0.1 0 0 0</pose><visual name="v"><geometry><sphere><radius>0.04</radius></sphere></geometry></visual>
    <collision name="c"><geometry><plane><size>1 1</size></plane></geometry></collision></link>
  <joint name="hinge" type="revolute"><pose relative_to="base">0 0 0.2 0 0 0</pose><parent>base</parent><child>arm</child><axis><xyz>0 1 0</xyz><limit><lower>-1.2</lower><upper>1.2</upper></limit></axis></joint>
  <joint name="mount" type="fixed"><parent>tip</parent><child>ball</child></joint>
</model></world></sdf>
"""

# A model nested in the model, and one nested in that: arm stands on the base, its elbow posed on its
# upper link and its lower link on the elbow, a wrist frame on the lower link, the hand on that frame;
# the rig's shoulder attaches arm by its scoped link name.
NESTED_SDF = """<?xml version="1.0"?>
<sdf version="1.9"><model name="rig">
  <link name="base"><visual name="v"><geometry><box><size>0.4 0.4 0.02</size></box></geometry></visual></link>
  <model name="arm">
    <pose relative_to="base">0.1 0 0.05 0 0 0</pose>
    <link name="upper"><pose>0 0 0.05 0 0 0</pose><visual name="v"><geometry><box><size>0.02 0.02 0.1</size></box></geometry></visual></link>
    <link name="lower"><pose relative_to="elbow">0 0 0.05 0 0 0</pose><visual name="v"><geometry><cylinder><radius>0.01</radius><length>0.1</length></cylinder></geometry></visual></link>
    <frame name="wrist" attached_to="lower"><pose>0 0 0.05 0 0 0</pose></frame>
    <joint name="elbow" type="revolute"><pose relative_to="upper">0 0 0.05 0 0 0</pose><parent>upper</parent><child>lower</child>
      <axis><xyz expressed_in="__model__">0 1 0</xyz><limit><lower>-1.6</lower><upper>1.6</upper></limit></axis></joint>
    <model name="hand">
      <pose relative_to="wrist">0 0 0.01 0 0 0</pose>
      <link name="palm"><visual name="v"><geometry><sphere><radius>0.02</radius></sphere></geometry></visual></link>
    </model>
    <joint name="wrist_mount" type="fixed"><parent>wrist</parent><child>hand::palm</child></joint>
  </model>
  <joint name="shoulder" type="revolute"><parent>base</parent><child>arm::upper</child><axis><xyz>0 0 1</xyz></axis></joint>
</model></sdf>
"""


# A crank-rocker four-bar (the browser fixture, `packages/ui/src/renderers/robot/__fixtures__/linkage.urdf`):
# the ground runs 0.2 m along +x from the crank's pivot to the rocker's; the rocker (0.08 m, the driver)
# drives the crank (0.05 m) through a 0.2 m coupler. At zero the rocker points straight up and the crank
# 87.4 degrees from the ground: the branch the coupler closes on.
LINKAGE_ZERO = 1.5253680280265103
LINKAGE = {"input_length": 0.05, "ground_length": 0.2, "output_length": 0.08, "coupler_length": 0.2,
           "input_zero": LINKAGE_ZERO, "output_zero": math.pi / 2, "branch": 0}
# The same lengths with the crank driving (a Grashof crank-rocker: the 0.05 m crank turns full circles,
# the 0.08 m rocker oscillates), so the derived joint is the rocker and the driver turns without limits.
# At zero the crank points straight up; the rocker then sits at this angle from the ground.
WIPER_ZERO = 1.5425679797000098
WIPER = {"input_length": 0.08, "ground_length": 0.2, "output_length": 0.05, "coupler_length": 0.2,
         "input_zero": WIPER_ZERO, "output_zero": math.pi / 2, "branch": 0}


def four_bar_urdf(four_bar=LINKAGE, *, driver_type="revolute", driver_limit=(-0.5, 0.5), crank_limit=(-1.5, 1.5), crank_type="revolute",
                  driver_origin='xyz="0.2 0 0" rpy="0 0 1.5707963267948966"', driver_axis="0 0 1", element=None, extra_links="", extra_joints=""):
    """A four-bar as `linkage.urdf` writes one: a ground, the driver's link and the crank's."""
    numbers = four_bar if element is None else {**four_bar, **element}
    attributes = " ".join(f'{key}="{numbers[key]!r}"' for key in ("input_length", "ground_length", "output_length", "coupler_length", "input_zero", "output_zero"))
    limit = f'<limit lower="{driver_limit[0]}" upper="{driver_limit[1]}" effort="1" velocity="1"/>' if driver_type == "revolute" else ""
    crank_limits = f'<limit lower="{crank_limit[0]}" upper="{crank_limit[1]}" effort="1" velocity="1"/>' if crank_type == "revolute" else ""
    return f"""<robot name="linkage" xmlns:tcad="https://text-to-cad.dev/urdf">
  <link name="ground">{box('0.26 0.02 0.01', '0.1 0 -0.01')}</link>
  <link name="rocker"><visual name="rocker_arm"><origin xyz="0.04 0 0"/><geometry><box size="0.08 0.015 0.01"/></geometry></visual></link>
  <link name="crank">{box('0.05 0.015 0.01', '0.025 0 0')}</link>{extra_links}
  <joint name="output_joint" type="{driver_type}"><parent link="ground"/><child link="rocker"/><origin {driver_origin}/><axis xyz="{driver_axis}"/>{limit}</joint>
  <joint name="input_joint" type="{crank_type}"><parent link="ground"/><child link="crank"/><origin xyz="0 0 0" rpy="0 0 {numbers['input_zero']!r}"/><axis xyz="0 0 1"/>{crank_limits}
    <tcad:four_bar driver="output_joint" {attributes}/></joint>{extra_joints}
</robot>"""


def transform(matrix: list[list[float]], point) -> list[float]:
    return [round(sum(matrix[i][j] * v for j, v in enumerate((*point, 1.0))), 6) + 0.0 for i in range(3)]


def degrees(radians: float) -> float:
    """A radian value as the payload writes it: in degrees, rounded as every emitted number is."""
    return round(math.degrees(radians), 12)


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = IsolatedCadRoots(self, prefix="robot-payload-")
        self.root = self.roots.cad_root

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class UrdfArticulation(_Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.payload = read_robot_description(self.write("arm.urdf", ARM_URDF))
        self.articulation = self.payload["articulation"]

    def test_controls_are_the_driven_joints_in_their_units_at_their_limits(self) -> None:
        self.assertEqual(self.payload["schemaVersion"], ROBOT_PAYLOAD_SCHEMA_VERSION)
        self.assertEqual((self.payload["kind"], self.payload["name"], self.payload["root"]), ("urdf", "arm", "base"))
        controls = {control["id"]: control for control in self.articulation["controls"]}
        self.assertEqual(list(controls), ["shoulder", "lift", "grip", "spin"], "no fixed joint, no mimic follower")
        self.assertAlmostEqual(controls["shoulder"]["min"], math.degrees(-1.5708))
        self.assertEqual((controls["shoulder"]["unit"], controls["lift"]["unit"]), ("deg", "m"))
        self.assertEqual((controls["lift"]["min"], controls["lift"]["max"]), (0.0, 0.3))
        self.assertEqual((controls["spin"]["min"], controls["spin"]["max"]), (None, None), "a continuous joint is unbounded")
        self.assertEqual(self.articulation["opening"], {"shoulder": 0.0, "lift": 0.0, "grip": 0.0, "spin": 0.0})
        self.assertEqual(self.articulation["poses"], {})

    def test_joints_are_rows_over_the_controls_in_rest_space_parents_first(self) -> None:
        joints = {joint["id"]: joint for joint in self.articulation["joints"]}
        self.assertEqual([joint["id"] for joint in self.articulation["joints"]],
                         ["shoulder", "lift", "camera_mount", "grip", "grip_mirror", "spin"])
        self.assertEqual(joints["shoulder"], {"id": "shoulder", "parent": None, "kind": "revolute", "origin": [0.0, 0.0, 0.2],
                                              "axis": [0.0, 1.0, 0.0], "turn": {"bias": 0.0, "terms": [["shoulder", 1.0]]}})
        self.assertEqual(joints["camera_mount"], {"id": "camera_mount", "parent": None, "kind": "fixed"})
        self.assertEqual(joints["grip"]["parent"], "lift")
        self.assertEqual(joints["grip"]["origin"], [-0.15, 0.16, 0.15], "a joint's origin is where its frame is at rest")
        # A mimic follower is its leader's row, scaled: one value moves both.
        self.assertEqual(joints["grip_mirror"]["travel"], {"bias": -0.0, "terms": [["grip", -1.0]]})
        # The wheel's axis is the joint frame's Z, which the mount's roll turned onto -Y.
        self.assertEqual([round(v, 4) + 0.0 for v in joints["spin"]["axis"]], [0.0, -1.0, 0.0])
        self.assertEqual(self.articulation["carries"], {"shoulder": ["upper_arm"], "lift": ["carriage"], "camera_mount": ["camera"],
                                                        "grip": ["finger_left"], "grip_mirror": ["finger_right"], "spin": ["wheel"]})

    def test_handles_are_the_moving_rows_and_a_follower_writes_its_leader(self) -> None:
        handles = {handle["id"]: handle for handle in self.articulation["handles"]}
        self.assertEqual(list(handles), ["shoulder", "lift", "grip", "grip_mirror", "spin"])
        self.assertEqual((handles["grip_mirror"]["control"], handles["grip_mirror"]["weight"], handles["grip_mirror"]["dof"]), ("grip", -1.0, "travel"))
        self.assertEqual((handles["grip_mirror"]["min"], handles["grip_mirror"]["max"], handles["grip_mirror"]["unit"]), (-0.04, 0.0, "m"))
        self.assertEqual((handles["shoulder"]["control"], handles["shoulder"]["weight"], handles["shoulder"]["unit"]), ("shoulder", 1.0, "deg"))

    def test_the_reference_evaluator_moves_the_carried_links(self) -> None:
        deltas = joint_matrices(self.articulation, {"grip": 0.03, "lift": 0.2, "shoulder": 90})
        self.assertEqual(transform(deltas["grip_mirror"], (0, 0, 0)), [0.0, -0.03, 0.2], "the follower rides the lift and mirrors the grip")
        self.assertEqual(transform(deltas["shoulder"], (1.0, 0, 0.2)), [0.0, 0.0, -0.8], "a quarter turn about +Y at the shoulder")
        self.assertEqual(transform(deltas["camera_mount"], (1, 2, 3)), [1.0, 2.0, 3.0], "a fixed joint carries only its parent's motion")

    def test_visuals_are_placed_in_rest_space_and_primitives_are_store_meshes(self) -> None:
        visuals = {visual["id"]: visual for visual in self.payload["visuals"]}
        self.assertEqual(list(visuals), ["base:v1", "upper_arm:v1", "carriage:v1", "finger_left:v1", "finger_right:v1", "wheel:v1"])
        base = visuals["base:v1"]
        self.assertEqual((base["link"], base["label"], base["color"], base["mesh"]["format"]), ("base", "box", "#4d4d59", "glb"))
        # A primitive is meshed in metres and drawn in millimetres: its placement scales by 0.001.
        self.assertEqual([round(v, 6) for v in base["placement"]], [0.001, 0, 0, 0, 0, 0.001, 0, 0, 0, 0, 0.001, 0.05, 0, 0, 0, 1])
        self.assertEqual(visuals["upper_arm:v1"]["color"], "#80808c", "a named material's colour")
        self.assertAlmostEqual(visuals["upper_arm:v1"]["placement"][3], 0.25)
        self.assertAlmostEqual(visuals["upper_arm:v1"]["placement"][11], 0.2, msg="the link frame carries its visual")
        for visual in visuals.values():
            data = read_verified_object(visual["mesh"]["object"])
            self.assertEqual(struct.unpack("<I", data[:4])[0], 0x46546C67, "a GLB object in the store")
        self.assertEqual(visuals["finger_left:v1"]["mesh"]["object"], visuals["finger_right:v1"]["mesh"]["object"], "one shape, one object")
        # The wheel's cylinder takes the segments the display ladder's standard rung gives it.
        document = json.loads(read_verified_object(visuals["wheel:v1"]["mesh"]["object"])[20:20 + struct.unpack("<I", read_verified_object(visuals["wheel:v1"]["mesh"]["object"])[12:16])[0]])
        self.assertNotIn("materials", document, "no material: the description's colour or the viewer's surface paints it")
        self.assertEqual(document["nodes"][0]["extras"]["cadUpAxis"], "y")
        from cadgen._internal.primitive_mesh import primitive_segments
        segments = primitive_segments(0.3, math.sqrt(2 * 0.6 ** 2 + 0.1 ** 2))
        self.assertGreater(segments, 2 * math.pi / DEFAULT_TESSELLATION["angleTolerance"] - 1)
        self.assertEqual(document["accessors"][0]["count"], 2 * segments + 2 * (segments + 1))

    def test_links_and_joints_carry_what_the_description_says(self) -> None:
        links = {link["name"]: link for link in self.payload["links"]}
        self.assertEqual([link["name"] for link in self.payload["links"]], ["base", "upper_arm", "carriage", "camera", "finger_left", "finger_right", "wheel"])
        self.assertEqual(links["base"]["inertial"], {"mass": 2.5, "origin": {"xyz": [0.0, 0.0, 0.05], "rpy": [0.0, 0.0, 0.0]},
                                                     "inertia": {"ixx": 0.01, "ixy": 0.0, "ixz": 0.0, "iyy": 0.02, "iyz": 0.0, "izz": 0.03}})
        self.assertEqual(links["base"]["collisions"], [{"name": "", "type": "cylinder", "filename": "", "radius": 0.2, "length": 0.1,
                                                        "origin": {"xyz": [0.0, 0.0, 0.0], "rpy": [0.0, 0.0, 0.0]}}])
        self.assertEqual(links["upper_arm"]["visuals"][0]["materialName"], "steel")
        self.assertEqual(links["camera"]["placement"][3], 0.15)
        joints = {joint["name"]: joint for joint in self.payload["joints"]}
        self.assertEqual(joints["shoulder"]["limit"], {"lower": -1.5708, "upper": 1.5708, "effort": 1.0, "velocity": 1.0})
        self.assertEqual(joints["grip_mirror"]["mimic"], {"joint": "grip", "multiplier": -1.0, "offset": 0.0})
        self.assertEqual((joints["camera_mount"]["axis"], joints["camera_mount"]["origin"]["rpy"]), (None, [0.0, 0.5, 0.0]))

    def test_a_visual_is_labelled_by_its_own_name_and_by_its_geometry_without_one(self) -> None:
        (self.root / "meshes").mkdir()
        (self.root / "meshes" / "bucket.stl").write_bytes(b"solid a\nendsolid a\n")
        urdf = ('<robot name="bucket_robot"><link name="bucket">'
                '<visual name="shell"><geometry><mesh filename="meshes/bucket.stl"/></geometry></visual>'
                '<visual name="  lip "><geometry><box size="0.1 0.1 0.01"/></geometry></visual>'
                '<visual><geometry><mesh filename="meshes/bucket.stl"/></geometry></visual>'
                '<visual name=""><geometry><cylinder radius="0.01" length="0.2"/></geometry></visual>'
                '</link></robot>')
        payload = read_robot_description(self.write("bucket.urdf", urdf))
        self.assertEqual([(visual["id"], visual["label"]) for visual in payload["visuals"]],
                         [("bucket:v1", "shell"), ("bucket:v2", "lip"), ("bucket:v3", "bucket.stl"), ("bucket:v4", "cylinder")])
        self.assertEqual([fact["name"] for fact in payload["links"][0]["visuals"]], ["shell", "lip", "", ""], "the facts keep the name as written")

    def test_a_mimic_chain_with_an_offset_across_units_is_one_affine_row(self) -> None:
        urdf = """<robot name="chain"><link name="a"/><link name="b"/><link name="c"/><link name="d"/>
          <joint name="lead" type="prismatic"><parent link="a"/><child link="b"/><axis xyz="1 0 0"/><limit lower="0" upper="1" effort="1" velocity="1"/></joint>
          <joint name="turn" type="revolute"><parent link="b"/><child link="c"/><axis xyz="0 0 1"/><limit lower="-3" upper="3" effort="1" velocity="1"/><mimic joint="lead" multiplier="2" offset="0.5"/></joint>
          <joint name="again" type="revolute"><parent link="c"/><child link="d"/><axis xyz="0 0 1"/><limit lower="-3" upper="3" effort="1" velocity="1"/><mimic joint="turn" multiplier="-1" offset="0.1"/></joint>
        </robot>"""
        articulation = read_robot_description(self.write("chain.urdf", urdf))["articulation"]
        joints = {joint["id"]: joint for joint in articulation["joints"]}
        # turn (rad) = 2 * lead (m) + 0.5; its row is degrees: 2 * 180/pi per metre, 0.5 rad of bias.
        self.assertEqual(joints["turn"]["turn"]["terms"], [["lead", degrees(2)]])
        self.assertAlmostEqual(joints["turn"]["turn"]["bias"], math.degrees(0.5))
        # again (rad) = -turn (rad) + 0.1 = -2 * lead - 0.4: the chain collapses onto the one control.
        self.assertEqual(joints["again"]["turn"]["terms"], [["lead", degrees(-2)]])
        self.assertAlmostEqual(joints["again"]["turn"]["bias"], math.degrees(-0.4))
        self.assertEqual([control["id"] for control in articulation["controls"]], ["lead"])


class FourBar(_Workspace):
    """``<tcad:four_bar>``: the crank of a planar four-bar linkage, derived from its driver. cadgen
    closes the linkage: it checks the geometry, samples the crank's angle over the driver's whole
    range from the closed form into a curve on the crank's row, and refuses what cannot close."""

    def setUp(self) -> None:
        super().setUp()
        self.payload = read_robot_description(self.write("linkage.urdf", four_bar_urdf()))
        self.articulation = self.payload["articulation"]
        self.crank = {joint["id"]: joint for joint in self.articulation["joints"]}["input_joint"]

    def test_the_crank_is_a_curve_over_its_driver_with_no_control_and_no_handle(self) -> None:
        self.assertEqual([control["id"] for control in self.articulation["controls"]], ["output_joint"], "the crank is derived, never set")
        self.assertEqual([handle["id"] for handle in self.articulation["handles"]], ["output_joint"], "and has no knob: its driver's moves it")
        row = self.crank["turn"]
        self.assertEqual((row["bias"], row["terms"]), (0.0, []))
        curve = row["curve"]
        self.assertEqual(curve["driver"], {"bias": 0.0, "terms": [["output_joint", 1.0]]}, "over the driver's row, in its degrees")
        self.assertNotIn("period", curve, "a limited driver: held beyond its range, which the door refuses anyway")
        self.assertEqual(curve["input"], sorted(curve["input"]))
        self.assertEqual((round(curve["input"][0], 4), round(curve["input"][-1], 4)), (round(math.degrees(-0.5), 4), round(math.degrees(0.5), 4)),
                         "the driver's whole operating range")
        self.assertEqual(curve["output"][curve["input"].index(0.0)], 0.0, "the zero pose is a key at exactly zero: the robot as written")
        self.assertEqual(self.articulation["carries"], {"output_joint": ["rocker"], "input_joint": ["crank"]})
        facts = {joint["name"]: joint for joint in self.payload["joints"]}
        self.assertEqual(facts["input_joint"]["fourBar"], {"driver": "output_joint", "inputLength": 0.05, "groundLength": 0.2, "outputLength": 0.08,
                                                            "couplerLength": 0.2, "inputZero": LINKAGE_ZERO, "outputZero": math.pi / 2})
        self.assertEqual((facts["input_joint"]["mimic"], facts["output_joint"]["fourBar"]), (None, None))
        self.assertEqual([visual["label"] for visual in self.payload["visuals"]], ["box", "rocker_arm", "box"])

    def test_the_curve_closes_the_linkage_within_the_tolerance_it_names(self) -> None:
        # The page interpolates the keys linearly: at every driver angle the crank it plays is within
        # the named tolerance of the closed form, and the coupler it implies spans its own length.
        import random
        draw = random.Random(584)
        worst = 0.0
        for _ in range(5000):
            driver = draw.uniform(-0.5, 0.5)
            exact = math.degrees(four_bar_input_angle(LINKAGE, driver))
            played = joint_values(self.articulation, {"output_joint": math.degrees(driver)})["input_joint"]["turn"]
            worst = max(worst, abs(played - exact))
            crank = LINKAGE_ZERO + math.radians(played)
            pin = (0.05 * math.cos(crank), 0.05 * math.sin(crank))
            rocker = math.pi / 2 + driver
            output_pin = (0.2 + 0.08 * math.cos(rocker), 0.08 * math.sin(rocker))
            self.assertLess(abs(math.dist(pin, output_pin) - 0.2), 1e-5, f"the coupler does not close at driver {math.degrees(driver):.3f} deg")
        self.assertLessEqual(worst, FOUR_BAR_CURVE_TOLERANCE_DEG)
        self.assertGreater(worst, FOUR_BAR_CURVE_TOLERANCE_DEG / 10, "the sampling is as sparse as the tolerance allows, not denser")
        self.assertLess(len(self.crank["turn"]["curve"]["input"]), 200, "a few keys per degree, not 720 fixed samples")

    def test_a_parallelogram_turns_with_its_driver_and_a_continuous_driver_turns_one_period(self) -> None:
        # Crank = rocker, coupler = ground, both straight up at zero: the crank turns exactly with the driver.
        parallelogram = {**LINKAGE, "input_length": 0.08, "input_zero": math.pi / 2}
        articulation = read_robot_description(self.write("parallelogram.urdf", four_bar_urdf(parallelogram)))["articulation"]
        curve = {joint["id"]: joint for joint in articulation["joints"]}["input_joint"]["turn"]["curve"]
        for x, y in zip(curve["input"], curve["output"]):
            self.assertAlmostEqual(x, y, places=9)
        # The crank drives: a full turn is its range, and the curve is one period the player folds into.
        wiper = read_robot_description(self.write("wiper.urdf", four_bar_urdf(WIPER, driver_type="continuous")))["articulation"]
        self.assertEqual(wiper["controls"][0]["min"], None)
        curve = {joint["id"]: joint for joint in wiper["joints"]}["input_joint"]["turn"]["curve"]
        self.assertEqual((curve["period"], curve["input"][0], curve["input"][-1]), (360.0, -180.0, 180.0))
        self.assertAlmostEqual(curve["output"][0], curve["output"][-1], places=9, msg="the seam meets itself")
        at = lambda degrees: joint_values(wiper, {"output_joint": degrees})["input_joint"]["turn"]
        self.assertAlmostEqual(at(400), at(40), places=9)
        self.assertAlmostEqual(at(-200), at(160), places=9)
        self.assertAlmostEqual(at(40), math.degrees(four_bar_input_angle(WIPER, math.radians(40))), delta=FOUR_BAR_CURVE_TOLERANCE_DEG)

    def test_a_mimic_of_the_crank_follows_the_curve_scaled(self) -> None:
        urdf = four_bar_urdf(extra_links='<link name="pointer"/>',
                             extra_joints='<joint name="pointer_joint" type="revolute"><parent link="ground"/><child link="pointer"/><axis xyz="0 0 1"/>'
                                          '<limit lower="-3" upper="3" effort="1" velocity="1"/><mimic joint="input_joint" multiplier="2" offset="0.1"/></joint>')
        payload = read_robot_description(self.write("pointer.urdf", urdf))
        articulation = payload["articulation"]
        self.assertEqual([control["id"] for control in articulation["controls"]], ["output_joint"])
        # A value of its own is refused with the control the chain ends at, past the crank it mimics.
        with self.assertRaisesRegex(RobotReadError, "jointValues\\[pointer_joint\\]: joint 'pointer_joint' mimics 'input_joint', which is the crank of a "
                                                    "four-bar linkage \\(tcad:four_bar\\) driven by 'output_joint', so it is posed by the value of "
                                                    "'output_joint'; set jointValues\\[output_joint\\] instead"):
            robot_control_values(payload, {"pointer_joint": 10})
        self.assertEqual([handle["id"] for handle in articulation["handles"]], ["output_joint"], "a mimic of a curve has no inverse to write through")
        rows = joint_values(articulation, {"output_joint": 15})
        self.assertAlmostEqual(rows["pointer_joint"]["turn"], 2 * rows["input_joint"]["turn"] + math.degrees(0.1), places=9)
        # The follower is held to its own limits over the driver's range, as the crank is: nothing clamps it later.
        with self.assertRaisesRegex(RobotReadError, "joint 'pointer_joint' mimics 'input_joint', the crank of a four-bar linkage, and reaches "
                                                    "-110.875 to 100.767 deg over its driver's range, outside its own limits \\[-57.2958, 57.2958\\] deg"):
            read_robot_description(self.write("narrow.urdf", urdf.replace('lower="-3" upper="3"', 'lower="-1" upper="1"')))

    def test_what_cannot_close_is_refused_in_words(self) -> None:
        cases = [
            ("a full turn of a rocker", four_bar_urdf(driver_type="continuous"), "the range \\[-180, 180\\] deg of its driver 'output_joint' includes angles where the linkage cannot close"),
            ("a wider range than closes", four_bar_urdf(driver_limit=(-0.9, 0.9)), "includes angles where the linkage cannot close; narrow the driver's limits"),
            ("an opposed axis", four_bar_urdf(driver_axis="0 0 -1"), "must turn about parallel, same-direction axes"),
            ("the wrong ground length", four_bar_urdf(element={"ground_length": 0.25}), "declares ground_length 0.25, but its pivot and the pivot of its driver 'output_joint' are 0.2 metres apart; set ground_length to that distance"),
            ("pivots off the plane", four_bar_urdf(driver_origin='xyz="0.2 0 0.01" rpy="0 0 1.5707963267948966"'), "are not coplanar"),
            ("crank limits that do not hold the derived range", four_bar_urdf(crank_limit=(-0.1, 0.1)), "derives -58.3025 to 47.5186 deg .* outside its own limits \\[-5.72958, 5.72958\\] deg"),
            ("zero angles off the branch", four_bar_urdf(element={"input_zero": 0.3}),
             "zero angles do not describe an assembly branch the lengths close at: at the zero pose \\(its driver 'output_joint' at 0 deg\\) "
             "the coupler closes the crank at .* deg from the ground line, not at input_zero 17.1887 deg; set input_zero"),
            # The pin sits 0.2154 m from the crank's pivot, nearer than a 0.05 m crank on a 0.3 m coupler reaches.
            ("lengths that cannot close as written", four_bar_urdf(element={"coupler_length": 0.3}),
             "cannot close at the zero pose \\(its driver 'output_joint' at 0 deg\\): the output pin is 0.215407 m from the input pivot, "
             "outside the 0.25 to 0.35 m that input_length 0.05 and coupler_length 0.3 reach; correct the lengths"),
        ]
        for label, urdf, pattern in cases:
            with self.subTest(label), self.assertRaisesRegex(RobotReadError, f"linkage.urdf joint 'input_joint' tcad:four_bar.*{pattern}"):
                read_robot_description(self.write("linkage.urdf", urdf))
        # A continuous crank is held to no limits, so its derived range is never refused.
        read_robot_description(self.write("free.urdf", four_bar_urdf(crank_type="continuous")))

    def test_joint_values_refuse_the_crank_by_name_and_the_driver_outside_the_solved_range(self) -> None:
        self.assertEqual(robot_control_values(self.payload, {"output_joint": 20}), {"output_joint": 20.0})
        with self.assertRaisesRegex(RobotReadError, "jointValues\\[input_joint\\]: joint 'input_joint' is the crank of a four-bar linkage \\(tcad:four_bar\\) "
                                                    "driven by 'output_joint', so it is posed by the value of 'output_joint'; set jointValues\\[output_joint\\] instead"):
            robot_control_values(self.payload, {"input_joint": 10})
        with self.assertRaisesRegex(RobotReadError, "jointValues\\[output_joint\\] = 40 deg is outside the limits \\[-28.6479, 28.6479\\] deg of joint 'output_joint'"):
            robot_control_values(self.payload, {"output_joint": 40})


class SdfArticulation(_Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.payload = read_robot_description(self.write("swing.sdf", SWING_SDF))

    def test_the_frame_graph_places_every_link_and_joint_in_rest_space(self) -> None:
        links = {link["name"]: link for link in self.payload["links"]}
        self.assertEqual((self.payload["kind"], self.payload["name"], self.payload["root"]), ("sdf", "swing", "base"))
        self.assertEqual(links["arm"]["placement"][3::4][:3], [0.05, 0.0, 0.2], "posed relative to the hinge, which is 0.2 above the base")
        self.assertEqual([round(v, 6) for v in links["ball"]["placement"][3::4][:3]], [0.55, 0.0, 0.3], "through the frame attached to the arm")
        joints = {joint["id"]: joint for joint in self.payload["articulation"]["joints"]}
        self.assertEqual(joints["hinge"]["origin"], [0.0, 0.0, 0.2])
        self.assertEqual(joints["hinge"]["parent"], None, "the base is the root: its joint hangs from nothing")
        self.assertEqual(joints["mount"], {"id": "mount", "parent": "hinge", "kind": "fixed"}, "a joint whose parent is a frame rides that frame's link")
        self.assertEqual(self.payload["articulation"]["carries"], {"hinge": ["arm"], "mount": ["ball"]})
        controls = self.payload["articulation"]["controls"]
        self.assertEqual([(c["id"], round(c["min"], 4), round(c["max"], 4)) for c in controls], [("hinge", round(math.degrees(-1.2), 4), round(math.degrees(1.2), 4))])
        # The arm's origin, 0.05 along the hinge's X, dips as the hinge turns 40 degrees about +Y.
        delta = joint_matrices(self.payload["articulation"], {"hinge": 40})["hinge"]
        self.assertEqual(transform(delta, (0.05, 0, 0.2)), [round(0.05 * math.cos(math.radians(40)), 6), 0.0, round(0.2 - 0.05 * math.sin(math.radians(40)), 6)])

    def test_visuals_colours_collisions_and_the_document_record(self) -> None:
        visuals = {visual["id"]: visual for visual in self.payload["visuals"]}
        self.assertEqual(visuals["base:v1"]["color"], "#1acc1a", "an SDF <diffuse>")
        self.assertEqual(visuals["arm:v1"]["placement"][3], 0.3, "the visual's pose in the link, the link's in the world")
        self.assertEqual(visuals["ball:v1"]["label"], "sphere")
        links = {link["name"]: link for link in self.payload["links"]}
        self.assertEqual(links["ball"]["collisions"][0]["type"], "plane", "an undrawn collision is described, never refused")
        self.assertEqual(self.payload["sdf"]["documentKind"], "world")
        self.assertEqual((self.payload["sdf"]["worldName"], self.payload["sdf"]["modelName"], self.payload["sdf"]["rootLink"]), ("lab", "swing", "base"))
        self.assertEqual((self.payload["sdf"]["linkCount"], self.payload["sdf"]["jointCount"], self.payload["sdf"]["frameCount"]), (3, 2, 1))
        self.assertEqual(self.payload["sdf"]["staticMetadata"]["lights"], [{"id": "light:1", "name": "sun", "type": "directional"}])
        self.assertEqual(self.payload["srdf"], None)

    def test_a_joint_on_the_world_and_links_that_float_free(self) -> None:
        sdf = """<sdf version="1.9"><model name="pair">
          <link name="post"><pose>1 0 0 0 0 0</pose><visual name="v"><geometry><capsule><radius>0.1</radius><length>1</length></capsule></geometry></visual></link>
          <link name="loose"><pose>0 2 0 0 0 0</pose><visual name="v"><geometry><box><size>1 1 1</size></box></geometry></visual></link>
          <joint name="turn" type="revolute"><parent>world</parent><child>post</child><axis><xyz>0 0 1</xyz></axis></joint>
        </model></sdf>"""
        payload = read_robot_description(self.write("pair.sdf", sdf))
        self.assertEqual(payload["root"], "loose", "the post hangs from the world through its joint; the loose link is the root")
        self.assertEqual(payload["sdf"]["rootLinks"], ["loose"])
        articulation = payload["articulation"]
        self.assertEqual(articulation["joints"][0]["origin"], [1.0, 0.0, 0.0], "a joint on the world sits at its child's pose")
        self.assertEqual(articulation["joints"][0]["parent"], None)
        two_roots = read_robot_description(self.write("free.sdf", sdf.replace("<joint", "<!--").replace("</joint>", "-->")))
        self.assertEqual((two_roots["root"], two_roots["sdf"]["rootLinks"]), ("", ["post", "loose"]), "two free links: no single root")
        self.assertEqual(articulation["controls"][0]["min"], None, "an SDF joint with no <limit> is unbounded")
        self.assertEqual([visual["label"] for visual in payload["visuals"]], ["capsule", "box"])


class SdfNestedModels(_Workspace):
    """A model nested in the model (SDFormat 1.6+) is part of the robot: its links, frames and
    joints resolve in its own namespace under scoped names (``arm::elbow``), its pose in the model
    it is nested in, and a joint outside it attaches to its links by scoped name."""

    def setUp(self) -> None:
        super().setUp()
        self.payload = read_robot_description(self.write("rig.sdf", NESTED_SDF))

    def test_every_nested_link_and_joint_is_placed_in_rest_space(self) -> None:
        placed = {link["name"]: [round(v, 6) + 0.0 for v in link["placement"][3::4][:3]] for link in self.payload["links"]}
        self.assertEqual(placed, {"base": [0.0, 0.0, 0.0], "arm::upper": [0.1, 0.0, 0.1], "arm::lower": [0.1, 0.0, 0.2],
                                  "arm::hand::palm": [0.1, 0.0, 0.26]},
                         "arm sits on the base, its links in arm's frame, hand on arm's wrist frame")
        self.assertEqual([visual["id"] for visual in self.payload["visuals"]], ["base:v1", "arm::upper:v1", "arm::lower:v1", "arm::hand::palm:v1"])
        articulation = self.payload["articulation"]
        joints = {joint["id"]: joint for joint in articulation["joints"]}
        self.assertEqual(list(joints), ["shoulder", "arm::elbow", "arm::wrist_mount"], "parents first, across the namespaces")
        self.assertEqual((joints["arm::elbow"]["origin"], joints["arm::elbow"]["axis"], joints["arm::elbow"]["parent"]),
                         ([0.1, 0.0, 0.15], [0.0, 1.0, 0.0], "shoulder"))
        self.assertEqual(joints["arm::wrist_mount"]["parent"], "arm::elbow", "a joint on a frame rides the frame's link")
        self.assertEqual(articulation["carries"], {"shoulder": ["arm::upper"], "arm::elbow": ["arm::lower"], "arm::wrist_mount": ["arm::hand::palm"]})
        self.assertEqual((self.payload["root"], self.payload["sdf"]["linkCount"], self.payload["sdf"]["jointCount"], self.payload["sdf"]["frameCount"]),
                         ("base", 4, 3, 1))
        # A quarter turn of the elbow about +Y swings the hand 0.11 m above it out along +X.
        delta = joint_matrices(articulation, {"arm::elbow": 90})["arm::wrist_mount"]
        self.assertEqual(transform(delta, (0.1, 0, 0.26)), [0.21, 0.0, 0.15])

    def test_a_scoped_name_is_what_a_job_sets_and_what_a_refusal_says(self) -> None:
        self.assertEqual([control["id"] for control in self.payload["articulation"]["controls"]], ["shoulder", "arm::elbow"])
        self.assertEqual(robot_control_values(self.payload, {"arm::elbow": 30}), {"shoulder": 0.0, "arm::elbow": 30.0})
        with self.assertRaisesRegex(RobotReadError, "jointValues\\[arm::wrist_mount\\]: joint 'arm::wrist_mount' is fixed"):
            robot_control_values(self.payload, {"arm::wrist_mount": 1})
        with self.assertRaisesRegex(RobotReadError, "Unknown joint\\(s\\): elbow. This SDF declares: arm::elbow, shoulder"):
            robot_control_values(self.payload, {"elbow": 30})
        with self.assertRaisesRegex(RobotReadError, "SDF model 'rig' refers to frame 'arm::nope', which it does not declare"):
            read_robot_description(self.write("nope.sdf", NESTED_SDF.replace("<child>arm::upper</child>", "<child>arm::nope</child>")))
        # A name a model declares is that element, even where it is the model's own name too.
        named = read_robot_description(self.write("box.sdf", """<sdf version="1.9"><model name="box"><pose>0 0 5 0 0 0</pose>
          <link name="box"><pose>1 0 0 0 0 0</pose></link><link name="lid"><pose relative_to="box">0 0 1 0 0 0</pose></link></model></sdf>"""))
        self.assertEqual([(link["name"], link["placement"][3::4][:3]) for link in named["links"]], [("box", [1.0, 0.0, 5.0]), ("lid", [1.0, 0.0, 6.0])])
        with self.assertRaisesRegex(RobotReadError, "placed.sdf model 'arm' is placed by its placement_frame, which the viewer does not place by; "
                                                    "drop placement_frame and pose the model's own frame"):
            read_robot_description(self.write("placed.sdf", NESTED_SDF.replace('<model name="arm">', '<model name="arm" placement_frame="upper">')))


class SrdfArticulation(_Workspace):
    def test_group_states_are_poses_and_home_is_the_opening(self) -> None:
        self.write("arm.urdf", ARM_URDF)
        payload = read_robot_description(self.write("arm.srdf", ARM_SRDF))
        articulation = payload["articulation"]
        self.assertEqual(payload["kind"], "srdf")
        self.assertEqual(articulation["poses"], {"arm/home": {"shoulder": degrees(-0.5), "lift": 0.1},
                                                 "arm/raised": {"shoulder": degrees(-1.0), "lift": 0.2}})
        self.assertEqual(articulation["opening"], {"shoulder": degrees(-0.5), "lift": 0.1, "grip": 0.0, "spin": 0.0})
        self.assertEqual(payload["srdf"]["groupStates"], [{"id": "arm/home", "name": "home", "group": "arm"}, {"id": "arm/raised", "name": "raised", "group": "arm"}])
        self.assertEqual(payload["srdf"]["endEffectors"], [{"name": "tool", "parentLink": "carriage", "group": "gripper", "parentGroup": "arm", "link": "carriage"}])
        self.assertEqual(payload["srdf"]["groupsByLink"], {"upper_arm": ["arm"], "carriage": ["arm"], "finger_left": ["gripper"]})
        self.assertEqual(robot_control_values(payload, None), articulation["opening"])

    def test_an_srdf_with_no_urdf_beside_it_says_what_it_looked_for(self) -> None:
        self.write("other.urdf", "<robot name='crane'><link name='l'/></robot>")
        with self.assertRaises(RobotReadError) as caught:
            read_robot_description(self.write("lonely.srdf", "<robot name='nobody'><group name='g'><link name='l'/></group></robot>"))
        message = str(caught.exception)
        for expected in ("lonely.srdf has no paired URDF", "<robot name='nobody'>", "other.urdf (robot 'crane')", "cadgen srdf validate"):
            self.assertIn(expected, message)


class Refusals(_Workspace):
    def test_a_mesh_the_page_cannot_draw_or_reach_is_refused_by_name(self) -> None:
        (self.root / "meshes").mkdir()
        (self.root / "meshes" / "a.stl").write_bytes(b"solid a\nendsolid a\n")
        (self.root / "meshes" / "a.dae").write_bytes(b"<COLLADA/>")
        cases = [
            ('<mesh filename="meshes/a.dae"/>', "a .dae the viewer cannot draw: export the link as one of .3mf, .glb, .stl"),
            ('<mesh filename="package://robot/meshes/a.stl"/>', "a package this cannot resolve"),
            ('<mesh filename="https://example.test/a.stl"/>', "which is not a local file"),
            ('<mesh filename="meshes/gone.stl"/>', "references missing mesh file"),
        ]
        for geometry, expected in cases:
            with self.subTest(geometry=geometry):
                path = self.write("robot.urdf", f'<robot name="r"><link name="base"><visual><geometry>{geometry}</geometry></visual></link></robot>')
                with self.assertRaisesRegex(RobotReadError, expected):
                    read_robot_description(path)
        payload = read_robot_description(self.write("robot.urdf", '<robot name="r"><link name="base"><visual><geometry><mesh filename="meshes/a.stl" scale="0.001 0.001 0.001"/></geometry></visual></link></robot>'))
        visual = payload["visuals"][0]
        self.assertEqual((visual["mesh"]["format"], visual["mesh"]["path"], visual["label"]), ("stl", str((self.root / "meshes" / "a.stl").resolve()), "a.stl"))
        self.assertEqual(visual["placement"][0], 0.001, "the mesh scale is in the placement")
        self.assertEqual(payload["links"][0]["visuals"][0]["path"], visual["mesh"]["path"])

    def test_a_mesh_lands_in_metres_as_its_format_defines_it(self) -> None:
        # One 0.05 x 0.22 x 0.05 m box, written as each format holds it: an STL in metres with no
        # scale, an STL and a 3MF in millimetres with scale 0.001, and a GLB, which glTF defines in
        # metres, with none. The page decodes a GLB into millimetres and an STL or a 3MF as written
        # (packages/core glbMeshData), so the placement times what the page decodes is where the
        # box's corner is drawn: the same point for every one, through either door.
        decoded = {"stl": 1.0, "3mf": 1.0, "glb": 1000.0}
        corner = (0.025, 0.11, 0.025)
        cases = [("metres.stl", "", 1.0), ("millimetres.stl", "0.001 0.001 0.001", 1000.0),
                 ("millimetres.3mf", "0.001 0.001 0.001", 1000.0), ("metres.glb", "", 1.0)]
        for name, _scale, _unit in cases:
            (self.root / name).write_bytes(b"solid a\nendsolid a\n")
        for name, scale, unit in cases:
            urdf_scale = f' scale="{scale}"' if scale else ""
            sdf_scale = f"<scale>{scale}</scale>" if scale else ""
            urdf = (f'<robot name="r"><link name="arm"><visual><origin xyz="0 0 0.11"/><geometry><mesh filename="{name}"{urdf_scale}/>'
                    '</geometry></visual></link></robot>')
            sdf = (f'<sdf version="1.9"><model name="r"><link name="arm"><visual name="v"><pose>0 0 0.11 0 0 0</pose><geometry><mesh>'
                   f'<uri>{name}</uri>{sdf_scale}</mesh></geometry></visual></link></model></sdf>')
            for door, text in (("urdf", urdf), ("sdf", sdf)):
                with self.subTest(mesh=name, door=door):
                    visual = read_robot_description(self.write(f"r.{door}", text))["visuals"][0]
                    placement = [visual["placement"][row * 4:row * 4 + 4] for row in range(4)]
                    drawn = transform(placement, [decoded[visual["mesh"]["format"]] * unit * value for value in corner])
                    self.assertEqual(drawn, [0.025, 0.11, 0.135])

    def test_every_undrawable_sdf_visual_is_named_at_once(self) -> None:
        # A plane is valid SDF the page has no mesh for; a shape the validator does not know is its finding.
        sdf = """<sdf version="1.9"><model name="rig">
          <link name="plate"><visual name="v"><geometry><box><size>1 1 1</size></box></geometry></visual></link>
          <link name="ground"><visual name="v"><geometry><plane><size>10 10</size></plane></geometry></visual></link>
          <link name="wall"><visual name="v"><geometry><plane><size>10 10</size></plane></geometry></visual></link>
        </model></sdf>"""
        with self.assertRaises(RobotReadError) as caught:
            read_robot_description(self.write("rig.sdf", sdf))
        message = str(caught.exception)
        self.assertIn("link 'ground' visual 1 uses <plane> geometry, which the viewer cannot draw", message)
        self.assertIn("link 'wall' visual 1 uses <plane> geometry", message)
        self.assertIn("Supported: box, capsule, cylinder, sphere, mesh", message)
        with self.assertRaisesRegex(RobotReadError, r"invalid_geometry_shape at /sdf/model\[@name='rig'\]/link\[@name='dome'\]"):
            read_robot_description(self.write("dome.sdf", sdf.replace(
                "<plane><size>10 10</size></plane></geometry></visual></link>\n          <link name=\"wall\">",
                "<ellipsoid><radii>1 2 3</radii></ellipsoid></geometry></visual></link>\n          <link name=\"wall\">", 1).replace("ground", "dome")))

    def test_the_validators_errors_are_the_refusal(self) -> None:
        with self.assertRaisesRegex(RobotReadError, "must define at least one link"):
            read_robot_description(self.write("empty.urdf", "<robot name='r'/>"))
        with self.assertRaisesRegex(RobotReadError, "could not be parsed as SDF XML"):
            read_robot_description(self.write("broken.sdf", "not xml"))
        with self.assertRaisesRegex(RobotReadError, "is not a robot description"):
            read_robot_description(self.write("part.step", "ISO-10303-21;"))

    def test_joint_values_are_held_to_the_articulation(self) -> None:
        payload = read_robot_description(self.write("arm.urdf", ARM_URDF))
        self.assertEqual(robot_control_values(payload, {"grip": 0.02, "spin": 720}), {"shoulder": 0.0, "lift": 0.0, "grip": 0.02, "spin": 720.0})
        self.assertEqual(robot_control_values(payload, {"shoulder": math.degrees(1.5708)})["shoulder"], math.degrees(1.5708), "the limit itself passes")
        refused = [
            ({"nope": 1}, "Unknown joint\\(s\\): nope. This URDF declares: grip, lift, shoulder, spin"),
            ({"camera_mount": 1}, "joint 'camera_mount' is fixed, so it has no value to set; drop it"),
            ({"grip_mirror": 0.01}, "joint 'grip_mirror' mimics 'grip' \\(grip_mirror = -1 × grip\\), so it is posed by the value of 'grip'; set jointValues\\[grip\\] instead"),
            ({"grip": 0.05}, "jointValues\\[grip\\] = 0.05 m is outside the limits \\[0, 0.04\\] m of joint 'grip'; pass a value within them"),
            ({"shoulder": "10"}, "must be a number"),
            ([1], "must be an object"),
        ]
        for request, pattern in refused:
            with self.subTest(request=request), self.assertRaisesRegex(RobotReadError, pattern):
                robot_control_values(payload, request)

    def test_a_follower_down_a_mimic_chain_names_the_control_its_chain_ends_at(self) -> None:
        urdf = f"""<robot name="m"><link name="base"/><link name="a"/><link name="b"/><link name="c"/><link name="d"/>
          <joint name="ja" type="revolute"><parent link="base"/><child link="a"/><axis xyz="0 0 1"/>{limit(-1, 1)}</joint>
          <joint name="jb" type="revolute"><parent link="a"/><child link="b"/><axis xyz="0 0 1"/>{limit(-1.5, 2.5)}<mimic joint="ja" multiplier="2" offset="0.1"/></joint>
          <joint name="jc" type="revolute"><parent link="b"/><child link="c"/><axis xyz="0 0 1"/>{limit(-0.6, 0.6)}<mimic joint="jb" multiplier="-0.5"/></joint>
          <joint name="jd" type="prismatic"><parent link="base"/><child link="d"/><axis xyz="0 0 1"/>{limit(0, 0.05)}<mimic joint="ja" multiplier="0.02" offset="0.02"/></joint>
        </robot>"""
        payload = read_robot_description(self.write("m.urdf", urdf))
        # jc = -0.5 * (2 * ja + 0.1) = -ja - 0.05 rad: in the controls' degrees, -1 x ja - 2.86479.
        refused = [
            ({"jc": 10}, "jointValues[jc]: joint 'jc' mimics 'jb', which mimics 'ja' (jc = -1 × ja - 2.86479 deg), so it is posed by the value of 'ja'; "
                         "set jointValues[ja] instead"),
            ({"jd": 0.03}, "jointValues[jd]: joint 'jd' mimics 'ja' (jd = 0.000349066 × ja + 0.02 m), so it is posed by the value of 'ja'; "
                           "set jointValues[ja] instead"),
            ({"ja": 40}, "jointValues[ja] = 40 deg puts joint 'jc', which mimics 'jb', which mimics 'ja', at -42.8648 deg, outside its limits "
                         "[-34.3775, 34.3775] deg; pass a value that keeps it within them"),
        ]
        for request, message in refused:
            with self.subTest(request=request), self.assertRaises(RobotReadError) as caught:
                robot_control_values(payload, request)
            self.assertEqual(str(caught.exception), message)
        self.assertEqual(robot_control_values(payload, {"ja": 10}), {"ja": 10.0}, "the joint the refusal names is one a value poses")

    def test_a_leader_may_not_push_its_follower_past_the_followers_limits(self) -> None:
        urdf = """<robot name="g"><link name="a"/><link name="b"/><link name="c"/>
          <joint name="lead" type="revolute"><parent link="a"/><child link="b"/><axis xyz="0 0 1"/><limit lower="-1" upper="1" effort="1" velocity="1"/></joint>
          <joint name="follow" type="revolute"><parent link="a"/><child link="c"/><axis xyz="0 0 1"/><limit lower="0" upper="0.5" effort="1" velocity="1"/><mimic joint="lead"/></joint>
        </robot>"""
        payload = read_robot_description(self.write("g.urdf", urdf))
        self.assertEqual(robot_control_values(payload, {"lead": 20})["lead"], 20.0)
        with self.assertRaisesRegex(RobotReadError, "jointValues\\[lead\\] = 40 deg puts joint 'follow', which mimics 'lead', at 40 deg, outside its limits \\[0, 28.6479\\] deg"):
            robot_control_values(payload, {"lead": 40})
        with self.assertRaisesRegex(RobotReadError, "at -5 deg, outside its limits"):
            robot_control_values(payload, {"lead": -5})


class TheStoreCachesThePayload(_Workspace):
    def test_unchanged_bytes_read_one_object_and_changed_bytes_read_again(self) -> None:
        path = self.write("arm.urdf", ARM_URDF)
        first = robot_payload_bytes(path)
        with mock.patch.object(robot_payload, "read_robot_description", side_effect=AssertionError("read twice")):
            self.assertEqual(robot_payload_bytes(path), first)
        payload = json.loads(first)
        self.assertEqual(payload["kind"], "urdf")
        # A sweep that took a primitive's object: a rebuild meshes it again under the same hash.
        digest = payload["visuals"][0]["mesh"]["object"]
        os.remove(object_path(digest))
        self.assertEqual(json.loads(robot_payload_bytes(path, rebuild=True))["visuals"][0]["mesh"]["object"], digest)
        self.assertTrue(object_path(digest).is_file())
        path.write_text(ARM_URDF.replace('limit lower="0" upper="0.3"', 'limit lower="0" upper="0.6"'), encoding="utf-8")
        changed = json.loads(robot_payload_bytes(path))
        self.assertEqual({control["id"]: control["max"] for control in changed["articulation"]["controls"]}["lift"], 0.6)

    def test_an_srdf_s_key_covers_its_paired_urdf(self) -> None:
        urdf = self.write("arm.urdf", ARM_URDF)
        srdf = self.write("arm.srdf", ARM_SRDF)
        opening = json.loads(robot_payload_bytes(srdf))["articulation"]["opening"]
        self.assertEqual(opening["lift"], 0.1)
        urdf.write_text(ARM_URDF.replace('limit lower="0" upper="0.3"', 'limit lower="0" upper="0.6"'), encoding="utf-8")
        self.assertEqual({c["id"]: c["max"] for c in json.loads(robot_payload_bytes(srdf))["articulation"]["controls"]}["lift"], 0.6)

    def test_locating_names_each_mesh_by_the_hosts_url(self) -> None:
        (self.root / "a.stl").write_bytes(b"solid a\nendsolid a\n")
        payload = read_robot_description(self.write("r.urdf", (
            '<robot name="r"><link name="base"><visual><geometry><mesh filename="a.stl"/></geometry></visual>'
            '<visual><geometry><sphere radius="0.1"/></geometry></visual></link></robot>')))
        located = locate_robot_payload(payload, file_url=lambda path: f"file:{Path(path).name}", object_url=lambda digest: f"object:{digest[:6]}")
        self.assertEqual([visual["mesh"] for visual in located["visuals"]],
                         [{"format": "stl", "url": "file:a.stl"}, {"format": "glb", "url": f"object:{payload['visuals'][1]['mesh']['object'][:6]}"}])
        self.assertIn("path", payload["visuals"][0]["mesh"], "the source payload is untouched")


class TheBrowserFixturesAreCurrent(unittest.TestCase):
    """The robot renderer's browser suite serves the payloads cadgen resolved for its fixture
    descriptions (``packages/ui/src/renderers/robot/__fixtures__``), committed so that suite needs
    no Python. They are held to a fresh read here: a change to the payload shape, to a description
    or to how a primitive is meshed regenerates them (``make_fixtures.py``)."""

    FIXTURES = REPO_ROOT / "packages" / "ui" / "src" / "renderers" / "robot" / "__fixtures__"

    def test_the_committed_payloads_refusals_and_meshes_are_what_cadgen_reads_now(self) -> None:
        roots = IsolatedCadRoots(self, prefix="robot-fixtures-")
        spec = importlib.util.spec_from_file_location("robot_fixtures", self.FIXTURES / "make_fixtures.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        payloads, refusals, meshes = module.fixture_payloads(roots.cache_dir)
        self.assertEqual(set(payloads) | set(refusals), set(module.DESCRIPTIONS))
        regenerate = "regenerate with packages/ui/src/renderers/robot/__fixtures__/make_fixtures.py"
        for name, payload in payloads.items():
            committed = self.FIXTURES / f"{Path(name).stem}.{Path(name).suffix[1:]}.robot.json"
            self.assertEqual(json.loads(committed.read_text(encoding="utf-8")), payload, f"{committed.name} is stale: {regenerate}")
        self.assertEqual(json.loads((self.FIXTURES / "refusals.json").read_text(encoding="utf-8")), refusals,
                         f"refusals.json is stale: {regenerate}")
        primitives = self.FIXTURES / "primitives"
        self.assertEqual(sorted(path.name for path in primitives.iterdir()), sorted(f"{digest}.glb" for digest in meshes),
                         f"primitives/ is stale: {regenerate}")
        for digest, data in meshes.items():
            self.assertEqual((primitives / f"{digest}.glb").read_bytes(), data, f"primitives/{digest}.glb is stale: {regenerate}")


if __name__ == "__main__":
    unittest.main()

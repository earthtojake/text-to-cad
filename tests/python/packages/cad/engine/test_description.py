"""A document described as a robot (``describe``, ``description.py``): the hinge's links, joint,
limits, as-built value and pose in SI, each box's mass, centre and inertia from its aluminium; the
description's frames composed at zero and at a state placing every part where the mechanism's
forward kinematics does, a pair followed backwards and a chain with a slide too; a coupling written
on the joints that follow; a part's collision and named frames, declared on the part and round-tripped
through the xbf and through a warm build; a part kept a body of its own, an exclusion and a joint's drive
limits and dynamics, declared, described and round-tripped through the xbf, and refused where they are
wrong; limits on a joint an assembly holds (a link of several parts) described and round-tripped, and one no
pair takes warned; a declared mass scaling its solids with point masses and nested masses, a part's contact friction,
and a mass that cannot be made refused; a turned link's inertia in its own frame, as the description, the
MJCF and the URDF write it; a model with no mechanism a link per top-level part; a loop a tree and the closure
its last pair, two frames that coincide as built, one closing at a slide moved to its nearest turn, and a
state moving it left out; a pinion that holds no part no link, its racks following the first; a part with no
density warned, one whose density is not positive refused; a free base floating and a declared link name, both
round-tripped through the xbf and refused where they name no link rightly; and a description taken at a
mechanism state, its bodies posed there and its joints, limits and states counted from it."""

from __future__ import annotations

import math
import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from cad.engine import build as engine_build
from cad.engine import document, mechanism
from cad.engine.describe import describe
from cad.engine.description import DescriptionError
from cad.engine.export import Source

HINGE = """
import build123d as bd
from bd_materials import metals
from cad.build123d import collision, frame, mechanism_state
from cad.engine import xbf


@xbf("XBF/hinge.xbf")
def hinge():
    base = bd.Box(100, 60, 20)
    base.label = "base"
    base.material = metals.aluminum()
    arm = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    arm.material = metals.aluminum()
    {declare}
    bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("mount", arm, bd.Location())
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=30)
    root = bd.Compound(children=[base, arm], label="hinge")
    mechanism_state(root, "open", elbow=90)
    return root
"""

# The same hinge with its revolute joint on the arm and the rigid one on the base: the base stays
# put, so its pair runs from the arm (link 1) to the ground (link 2), backwards from the ground.
BACKWARDS = """
import build123d as bd
from cad.build123d import mechanism_state
from cad.engine import xbf


@xbf("XBF/backwards.xbf")
def backwards():
    base = bd.Box(100, 60, 20)
    base.label = "base"
    arm = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    bd.RevoluteJoint("elbow", arm, axis=bd.Axis((10, 0, 5), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("seat", base, bd.Plane(origin=(40, 0, 20), z_dir=(0, 1, 0)).location)
    base.joints["seat"].connect_to(arm.joints["elbow"], angle=30)
    root = bd.Compound(children=[base, arm], label="backwards")
    mechanism_state(root, "open", elbow=90)
    return root
"""

# A slide, a part fixed to what it carries, and a turn after it.
LIFT = """
import build123d as bd
from cad.build123d import mechanism_state
from cad.engine import xbf


@xbf("XBF/lift.xbf")
def lift():
    base = bd.Box(80, 80, 10)
    base.label = "base"
    carriage = bd.Box(30, 30, 10)
    carriage.label = "carriage"
    clamp = bd.Box(10, 30, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
    clamp.label = "clamp"
    arm = bd.Box(5, 40, 5, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.CENTER))
    arm.label = "arm"
    bd.LinearJoint("lift", base, axis=bd.Axis((0, 0, 5), (0, 0, 1)), linear_range=(10, 90))
    bd.RigidJoint("bore", carriage, bd.Location())
    base.joints["lift"].connect_to(carriage.joints["bore"], position=40)
    bd.RigidJoint("side", carriage, bd.Location((15, 0, 0)))
    bd.RigidJoint("back", clamp, bd.Location())
    carriage.joints["side"].connect_to(clamp.joints["back"])
    bd.RevoluteJoint("wrist", clamp, axis=bd.Axis((10, 0, 0), (1, 0, 0)), angular_range=(-90, 90))
    bd.RigidJoint("hub", arm, bd.Location())
    clamp.joints["wrist"].connect_to(arm.joints["hub"], angle=20)
    root = bd.Compound(children=[base, carriage, clamp, arm], label="lift")
    mechanism_state(root, "top", lift=90, wrist=45)
    return root
"""

# Three bones curled together by one gear coupling, and a state at half of it.
FINGER = """
import build123d as bd
from cad.build123d import gear_pair, mechanism_state
from cad.engine import xbf

CURL = {"knuckle": 90, "middle": 100, "tip": 70}


@xbf("XBF/finger.xbf")
def finger():
    bones, x = [], 0
    for name, length in (("palm", 30), ("proximal", 40), ("medial", 25), ("distal", 20)):
        bone = bd.Pos(x, 0, 0) * bd.Box(length, 16, 12, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
        bone.label = name
        bones.append(bone)
        x += length
    for joint, parent, child in zip(CURL, bones, bones[1:]):
        knuckle = bd.Axis(child.location.position, (0, 1, 0))
        bd.RevoluteJoint(joint, parent, axis=knuckle, angular_range=(0, CURL[joint]))
        bd.RigidJoint(joint, child, bd.Plane(origin=knuckle.position, z_dir=knuckle.direction).location)
        parent.joints[joint].connect_to(child.joints[joint], angle=0)
    root = bd.Compound(children=bones, label="finger")
    gear_pair(root, "curl", **CURL)
    return mechanism_state(root, "half", curl=0.5)
"""

# Two parts placed apart, no joint: one with a material, one with none.
PAIR = """
import build123d as bd
from bd_materials import metals
from cad.engine import xbf


@xbf("XBF/pair.xbf")
def pair():
    left = bd.Box(10, 20, 30)
    left.label = "left"
    left.material = metals.aluminum()
    right = bd.Pos(50, 0, 0) * bd.Rot(0, 0, 90) * bd.Box(10, 20, 30)
    right.label = "right"
    return bd.Compound(children=[left, right], label="pair")
"""

# Two revolute joints on one axis between the same two parts: a loop.
LOOP = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/loop.xbf")
def loop():
    base = bd.Box(100, 60, 20)
    base.label = "base"
    arm = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    axis = bd.Axis((40, 0, 20), (0, 1, 0))
    bd.RevoluteJoint("near", base, axis=axis)
    bd.RevoluteJoint("far", base, axis=axis)
    bd.RigidJoint("near", arm, bd.Location())
    bd.RigidJoint("far", arm, bd.Location())
    base.joints["near"].connect_to(arm.joints["near"], angle=30)
    return bd.Compound(children=[base, arm], label="loop")
"""

# A four-bar in the XZ plane, its hinges along +Y: the crank, the coupler and the rocker each built where it
# stands, three hinges connected at 0 and the loop's last, rocker to coupler, paired by label.
FOUR_BAR = """
import math

import build123d as bd
from bd_materials import metals
from cad.build123d import mechanism_state
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
    root = bd.Compound(children=[base, crank, coupler, rocker], label="four_bar")
    return mechanism_state(root, "swung", a=20)
"""

# An oscillating cylinder: a crank on the base, a rod on the crank, a cylinder hinged to the base that the
# rod slides in, the slide paired last by label, so the loop closes at a slide.
CYLINDER = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/cylinder.xbf")
def cylinder():
    base = bd.Box(140, 10, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MAX))
    base.label = "base"
    crank = bd.Box(10, 6, 40, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    crank.label = "crank"
    rod = bd.Pos(0, 8, 40) * bd.Box(80, 6, 4, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
    rod.label = "rod"
    barrel = bd.Pos(110, 16, 4) * bd.Box(30, 8, 8)
    barrel.label = "barrel"
    for name, holder, child, at in (("a", base, crank, (0, 0, 0)), ("b", crank, rod, (0, 0, 40)),
                                    ("c", base, barrel, (120, 0, 0))):
        joint = bd.RevoluteJoint(name, holder, axis=bd.Axis(at, (0, 1, 0)), angular_range=(-90, 90))
        bd.RigidJoint(name, child, joint.location)
        joint.connect_to(child.joints[name], angle=0)
    along = bd.Axis((120, 0, 0), (-3, 0, 1))  # from the barrel's hinge towards the rod's
    slide = bd.LinearJoint("s", barrel, axis=along, linear_range=(-50, 50))
    bd.RigidJoint("s", rod, bd.Location(along.position))
    return bd.Compound(children=[base, crank, rod, barrel], label="cylinder")
"""

# A gripper whose two slides one pinion couples, the pinion a reference axis on the palm (no part).
GRIPPER = """
import build123d as bd
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
        slide = bd.LinearJoint(side, palm, axis=bd.Axis((x, 0, 10), (out, 0, 0)), linear_range=(0, 30))
        bd.RigidJoint(side, finger, bd.Location((x, 0, 10)))
        slide.connect_to(finger.joints[side], position=0)
        fingers.append(finger)
    bd.RevoluteJoint("pinion", palm, axis=bd.Axis((0, 0, 10), (0, 1, 0)), angular_range=(-360, 360))
    gripper = bd.Compound(children=[palm, *fingers], label="gripper")
    rack_and_pinion_pair(gripper, "grip", pinion=1, left=0.15, right=0.3)
    return mechanism_state(gripper, "open", grip=100)
"""

# A part whose material weighs nothing.
WEIGHTLESS = """
import build123d as bd
from bd_materials import FinishedMaterial
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties
from cad.engine import xbf


@xbf("XBF/foam.xbf")
def foam():
    block = bd.Box(10, 10, 10)
    block.label = "block"
    block.material = FinishedMaterial(RangeMaterial(name="foam", density=0),
                                      pbr=PbrProperties.create("foam", color="#808080"))
    return block
"""


def _aluminium() -> float:
    from bd_materials import metals

    return float(metals.aluminum().material.density)


def _motion(kind: str, value: Any) -> np.ndarray:
    """A joint's motion, composed here as the contract says: a turn about Z, a slide along Z."""
    found = np.eye(4)
    if kind in ("revolute", "continuous"):
        c, s = math.cos(value), math.sin(value)
        found[:2, :2] = [[c, -s], [s, c]]
    elif kind == "prismatic":
        found[2, 3] = value
    return found


def _frames_at(description: Any, values: dict[str, float]) -> dict[str, np.ndarray]:
    """Every link's frame with the joints at ``values`` around zero (a follower from its leader),
    composed from the root down."""
    frames = {description.root.name: description.root.frame}
    by_name = {joint.name: joint for joint in description.joints}
    for joint in description.joints:
        value = values.get(joint.name, 0.0)
        if joint.follows is not None:
            leader, ratio, offset = joint.follows
            value = ratio * values.get(by_name[leader].name, 0.0) + offset
        frames[joint.child] = frames[joint.parent] @ joint.origin @ _motion(joint.kind, value)
    return frames


def _metres(matrix: np.ndarray) -> np.ndarray:
    found = np.array(matrix, dtype=float)
    found[:3, 3] *= 0.001
    return found


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-description-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def build(self, name: str, source: str) -> Path:
        script = self.folder / f"{name}.py"
        script.write_text(textwrap.dedent(source), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, [name], cwd=self.folder)[0]
        self.assertTrue(report["ok"], report)
        return self.folder / f"XBF/{name}.xbf"

    def described(self, name: str, source: str, **options: Any) -> tuple[Any, dict[str, Any]]:
        found = Source.read(self.build(name, source))
        return describe(found.view(), **options), found.structure

    def assert_placed_as_the_mechanism_places(self, description: Any, structure: dict[str, Any]) -> None:
        """At zero and at each state, every part where ``mechanism.link_worlds`` puts it, to a nanometre."""
        kinematics = structure["kinematics"]
        owner = {index: at for at, link in enumerate(kinematics["links"]) for index in link["instances"]}
        as_built = {label: (value,) if isinstance(value, float) else tuple(value)
                    for label, value in kinematics["asBuilt"].items()}
        rest = mechanism.link_worlds(kinematics, as_built)
        states = [({}, as_built)] + [
            (pose.values, mechanism.resolve(kinematics, pose.name)[0]) for pose in description.poses]
        for values, pair_values in states:
            worlds = mechanism.link_worlds(kinematics, pair_values)
            frames = _frames_at(description, values)
            for link in description.links[1:]:
                for index, visual in zip(link.parts, link.visuals):
                    built = np.array(structure["instances"][index]["matrix"]).reshape(4, 4).T
                    expected = _metres(worlds[owner[index]] @ np.linalg.inv(rest[owner[index]]) @ built)
                    np.testing.assert_allclose(frames[link.name] @ visual.geometry.placement, expected,
                                               rtol=0, atol=1e-9, err_msg=f"{visual.name} at {values}")


class HingeTest(_Folder):
    def test_the_hinge_is_two_links_a_revolute_joint_and_its_masses_in_si(self) -> None:
        description, structure = self.described("hinge", HINGE.format(declare="pass"))
        self.assertEqual([link.name for link in description.links], ["world", "base", "arm"])
        fixed, elbow = description.joints
        self.assertEqual((fixed.name, fixed.kind, fixed.parent, fixed.child), ("hinge", "fixed", "world", "base"))
        np.testing.assert_allclose(fixed.origin, np.eye(4), atol=1e-12)
        self.assertEqual((elbow.name, elbow.kind, elbow.parent, elbow.child), ("elbow", "revolute", "base", "arm"))
        # Its frame: on the axis through (40, 0, 20) mm along +Y, turned by the as-built 30 degrees.
        np.testing.assert_allclose(elbow.origin[:3, 3], [0.04, 0, 0.02], atol=1e-12)
        np.testing.assert_allclose(elbow.axis, [0, 1, 0], atol=1e-12)
        np.testing.assert_allclose(elbow.limits, [(math.radians(-10 - 30), math.radians(120 - 30))], atol=1e-12)
        np.testing.assert_allclose(elbow.as_built, [math.radians(30)], atol=1e-12)
        self.assertEqual([pose.name for pose in description.poses], ["open"])
        self.assertAlmostEqual(description.poses[0].values["elbow"], math.radians(60), places=12)
        # The child's frame is its joint's, in the model's space.
        base, arm = description.links[1:]
        np.testing.assert_allclose(arm.frame, base.frame @ elbow.origin, atol=1e-12)
        # Each box's mass is its volume at aluminium's density, about its centre, in its link's frame.
        density = _aluminium()
        for link, (a, b, c), centre in ((base, (0.1, 0.06, 0.02), (0, 0, 0)), (arm, (0.12, 0.02, 0.01), (0.06, 0, 0.005))):
            mass = a * b * c * density
            self.assertAlmostEqual(link.inertial.mass, mass, delta=1e-9)
            np.testing.assert_allclose(link.inertial.center, centre, atol=1e-9)
            np.testing.assert_allclose(link.inertial.inertia, np.diag([mass / 12 * (b * b + c * c), mass / 12 * (a * a + c * c),
                                                                       mass / 12 * (a * a + b * b)]), atol=1e-9)
        # Every part's mesh once, in metres; every visual a mesh of it, in its link's frame.
        self.assertEqual(sorted(mesh.name for mesh in description.meshes.values()), ["arm", "base"])
        arm_mesh = next(mesh for mesh in description.meshes.values() if mesh.name == "arm")
        np.testing.assert_allclose(arm_mesh.positions.max(axis=0), [0.12, 0.01, 0.01], atol=1e-7)
        self.assertEqual([visual.name for visual in arm.visuals], ["arm"])
        np.testing.assert_allclose(arm.visuals[0].geometry.placement, np.eye(4), atol=1e-12)
        self.assertEqual(arm.collisions[0].geometry.kind, "mesh")
        self.assertEqual(description.warnings, ())
        self.assert_placed_as_the_mechanism_places(description, structure)

    def test_a_pair_followed_backwards_and_a_chain_with_a_slide_place_as_the_mechanism_does(self) -> None:
        for name, source in (("backwards", BACKWARDS), ("lift", LIFT)):
            description, structure = self.described(name, source)
            self.assert_placed_as_the_mechanism_places(description, structure)
        # The lift's: its slide in metres around the 40 mm it was built at, the clamp one link with the carriage.
        lift, wrist = (joint for joint in description.joints if joint.kind != "fixed")
        self.assertEqual((lift.kind, wrist.kind, wrist.parent, wrist.child), ("prismatic", "revolute", "carriage", "arm"))
        np.testing.assert_allclose(lift.limits, [(-0.03, 0.05)], atol=1e-12)
        np.testing.assert_allclose(lift.as_built, [0.04], atol=1e-12)
        top = description.poses[0].values
        np.testing.assert_allclose([top["lift"], top["wrist"]], [0.05, math.radians(25)], atol=1e-12)

    def test_a_coupling_is_written_on_the_joints_that_follow(self) -> None:
        description, structure = self.described("finger", FINGER)
        joints = {joint.name: joint for joint in description.joints}
        self.assertIsNone(joints["knuckle"].follows)
        self.assertEqual(joints["middle"].follows[0], "knuckle")
        self.assertAlmostEqual(joints["middle"].follows[1], 100 / 90, places=12)
        self.assertEqual((joints["tip"].follows[0], joints["tip"].follows[2]), ("knuckle", 0.0))
        self.assertAlmostEqual(joints["tip"].follows[1], 70 / 90, places=12)
        self.assertEqual([joint.name for joint in description.controls()], ["knuckle"])
        half = description.poses[0].values
        self.assertAlmostEqual(half["knuckle"], math.radians(45), places=12)
        self.assertAlmostEqual(half["tip"], math.radians(35), places=12)
        self.assert_placed_as_the_mechanism_places(description, structure)


class DeclarationsTest(_Folder):
    def test_a_part_s_collision_and_frames_are_described_and_round_trip_through_the_xbf(self) -> None:
        declare = """collision(base, "box")
    collision(arm, "capsule")
    frame(arm, "tool", bd.Pos(120, 0, 5))"""
        description, _structure = self.described("hinge", HINGE.format(declare=declare))
        base, arm = description.links[1:]
        (box,) = base.collisions
        self.assertEqual(box.geometry.kind, "box")
        self.assertEqual(sorted(box.geometry.size), sorted([0.1, 0.06, 0.02]))
        np.testing.assert_allclose(box.geometry.placement[:3, 3], [0, 0, 0], atol=1e-9)
        (capsule,) = arm.collisions
        self.assertEqual(capsule.geometry.kind, "capsule")
        np.testing.assert_allclose(capsule.geometry.size, [0.01, 0.1], atol=1e-9)  # 120 mm less a 10 mm radius each end
        np.testing.assert_allclose(capsule.geometry.placement[:3, 3], [0.06, 0, 0.005], atol=1e-9)
        np.testing.assert_allclose(abs(capsule.geometry.placement[:3, 2]), [1, 0, 0], atol=1e-9)  # along the arm
        np.testing.assert_allclose(arm.frames["tool"][:3, 3], [0.12, 0, 0.005], atol=1e-12)
        # A part's own declaration stands whatever the default.
        bare = describe(Source.read(self.folder / "XBF/hinge.xbf").view(), collision_default="none")
        self.assertEqual([c.geometry.kind for link in bare.links for c in link.collisions], ["box", "capsule"])
        # The structure carries them, the same from the file as from the build's tree.
        path = self.folder / "XBF/hinge.xbf"
        loaded = document.Loaded(path).structure()
        self.assertEqual(loaded["prototypes"], document.tree_structure(document.saved(path), path)["prototypes"])
        by_name = {prototype["name"]: prototype for prototype in loaded["prototypes"]}
        self.assertEqual((by_name["base"]["collision"], by_name["base"]["frames"]), ("box", {}))
        self.assertEqual(by_name["arm"]["collision"], "capsule")
        np.testing.assert_allclose(np.array(by_name["arm"]["frames"]["tool"]).reshape(4, 4).T[:3, 3], [120, 0, 5])
        # A shape rebuilt from the document (a handle's ``.shape``, a child's in another process) carries them
        # too, as it carries its material: the collision as the word, each frame as a Location the harvest
        # reads again, so describing that shape says the same.
        rebuilt = Source.read(path).shape()
        parts = {leaf.label: leaf for leaf in rebuilt.leaves} if hasattr(rebuilt, "leaves") else \
            {child.label: child for child in rebuilt.children}
        self.assertEqual(parts["base"].__dict__.get("_collision"), "box")
        self.assertEqual(parts["arm"].__dict__.get("_collision"), "capsule")
        tool = parts["arm"].__dict__["_frames"]["tool"]
        np.testing.assert_allclose(tuple(tool.position), [120, 0, 5], atol=1e-9)
        self.assertEqual(list(document._frames({"tool": tool}, "arm")["tool"]), list(by_name["arm"]["frames"]["tool"]))

    def test_a_part_that_declares_none_collides_as_nothing_and_a_wrong_declaration_is_refused(self) -> None:
        import build123d as bd

        from cad.build123d import collision, frame

        description, _structure = self.described("hinge", HINGE.format(declare='collision(arm, "none")'))
        self.assertEqual(description.link("arm").collisions, [])
        # The base declares none: the default's primitive, fitted to its 100 x 60 x 20 mm box.
        xbf = self.folder / "XBF/hinge.xbf"
        for kind, size in (("sphere", (math.sqrt(0.05 ** 2 + 0.03 ** 2 + 0.01 ** 2),)), ("cylinder", (0.03, 0.1)),
                           ("capsule", (0.03, 0.04))):
            (fitted,) = describe(Source.read(xbf).view(), collision_default=kind).link("base").collisions
            self.assertEqual(fitted.geometry.kind, kind)
            np.testing.assert_allclose(fitted.geometry.size, size, atol=1e-9)
            np.testing.assert_allclose(fitted.geometry.placement[:3, 3], [0, 0, 0], atol=1e-9)
        self.assertEqual(describe(Source.read(xbf).view(), collision_default="none").link("base").collisions, [])
        with self.assertRaisesRegex(ValueError, "collision 'cone' is none of mesh, box"):
            collision(bd.Box(1, 1, 1), "cone")
        with self.assertRaisesRegex(TypeError, "Location"):
            frame(bd.Box(1, 1, 1), "tip", (1, 2, 3))
        with self.assertRaisesRegex(ValueError, "collision_default 'hull'"):
            describe(Source.read(self.folder / "XBF/hinge.xbf").view(), collision_default="hull")


# A camera fastened to the arm's tip, kept a body of its own, excluded from the base; the elbow named as
# its arm is, with its drive's limits.
BODIES = """
import build123d as bd
from bd_materials import metals
from cad.build123d import body, exclude, limits
from cad.engine import xbf


@xbf("XBF/bodies.xbf")
def bodies():
    base = bd.Box(100, 60, 20)
    base.label = "base"
    arm = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    cam = bd.Box(10, 10, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    cam.label = "cam"
    for part in (base, arm, cam):
        part.material = metals.aluminum()
    bd.RevoluteJoint("arm", base, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("arm", arm, bd.Location())
    base.joints["arm"].connect_to(arm.joints["arm"], angle=30)
    bd.RigidJoint("tip", arm, bd.Location((120, 0, 0)))
    bd.RigidJoint("seat", cam, bd.Location())
    arm.joints["tip"].connect_to(cam.joints["seat"])
    body(cam, "camera")
    exclude(cam, "base")
    root = bd.Compound(children=[base, arm, cam], label="bodies")
    return limits(root, "arm", effort=27, velocity=6.28, armature=0.012, damping=0.5, friction=0)
"""


class BodiesTest(_Folder):
    def test_a_body_an_exclusion_and_drive_limits_are_described_and_round_trip_through_the_xbf(self) -> None:
        description, structure = self.described("bodies", BODIES)
        self.assertEqual([link.name for link in description.links], ["world", "base", "arm", "camera"])
        self.assertEqual([(joint.name, joint.kind, joint.parent, joint.child) for joint in description.joints],
                         [("bodies", "fixed", "world", "base"), ("arm", "revolute", "base", "arm"),
                          ("camera", "fixed", "arm", "camera")])
        arm, camera = description.link("arm"), description.link("camera")
        # The camera is a body of its own where the part stands, with its own mass; the arm's is its own alone.
        index = next(at for at, instance in enumerate(structure["instances"]) if instance["path"].endswith("/cam"))
        np.testing.assert_allclose(camera.frame, _metres(np.array(structure["instances"][index]["matrix"]).reshape(4, 4).T),
                                   atol=1e-12)
        self.assertEqual(([v.name for v in arm.visuals], [v.name for v in camera.visuals]), (["arm"], ["cam"]))
        self.assertAlmostEqual(camera.inertial.mass, 1e-6 * _aluminium(), delta=1e-12)
        self.assertAlmostEqual(arm.inertial.mass, 0.12 * 0.02 * 0.01 * _aluminium(), delta=1e-9)
        elbow = description.joints[1]
        self.assertEqual((elbow.effort, elbow.velocity, elbow.armature, elbow.damping, elbow.friction),
                         (27.0, 6.28, 0.012, 0.5, 0.0))
        self.assertEqual(description.excludes, (("base", "camera"),))
        self.assertEqual(description.warnings, ())
        # The structure carries them, the same from the file as from the build's tree, and a shape rebuilt from
        # the document carries them as the model gave them.
        path = self.folder / "XBF/bodies.xbf"
        loaded = document.Loaded(path).structure()
        self.assertEqual(loaded["prototypes"], document.tree_structure(document.saved(path), path)["prototypes"])
        by_name = {prototype["name"]: prototype for prototype in loaded["prototypes"]}
        self.assertEqual((by_name["cam"]["body"], by_name["cam"]["exclude"]), ("camera", ["base"]))
        drive = {"effort": 27.0, "velocity": 6.28, "armature": 0.012, "damping": 0.5, "friction": 0.0}
        self.assertEqual(by_name["base"]["drives"], {"arm": drive})
        self.assertNotIn("body", by_name["arm"])
        rebuilt = {child.label: child for child in Source.read(path).shape().children}
        self.assertEqual((rebuilt["cam"].__dict__["_body"], rebuilt["cam"].__dict__["_exclude"]), ("camera", ("base",)))
        self.assertEqual(rebuilt["base"].__dict__["_drives"], {"arm": drive})

    def test_a_wrong_body_exclusion_or_limit_is_refused_by_name(self) -> None:
        import build123d as bd

        from cad.build123d import body, exclude, limits

        part = bd.Box(1, 1, 1)
        part.label = "part"
        assembly = bd.Compound(children=[part], label="assembly")
        with self.assertRaisesRegex(ValueError, "body: assembly is an assembly"):
            body(assembly)
        with self.assertRaisesRegex(ValueError, "'part' with itself"):
            exclude(part, "part")
        with self.assertRaisesRegex(ValueError, "no revolute or linear joint 'elbow' on assembly"):
            limits(assembly, "elbow", effort=1)
        bd.BallJoint("wrist", part)
        with self.assertRaisesRegex(ValueError, "a BallJoint moves two values or three"):
            limits(assembly, "wrist", effort=1)
        bd.RevoluteJoint("elbow", part)
        with self.assertRaisesRegex(ValueError, "effort is a positive number, not 0"):
            limits(assembly, "elbow", effort=0)
        with self.assertRaisesRegex(ValueError, "damping is a non-negative number, not -1"):
            limits(assembly, "elbow", damping=-1)
        with self.assertRaisesRegex(ValueError, "give effort, velocity, armature, damping or friction"):
            limits(assembly, "elbow")
        with self.assertRaisesRegex(DescriptionError, "part 'cam' excludes 'nothing', which names no part"):
            self.described("bodies", BODIES.replace('exclude(cam, "base")', 'exclude(cam, "nothing")'))


# The hinge's links each a compound of parts, the moving joint on the base's compound: limits declared on the
# assembly above reach it, and a limit on a joint no pair takes is warned.
LINKED = """
import build123d as bd
from bd_materials import metals
from cad.build123d import limits
from cad.engine import xbf


@xbf("XBF/linked.xbf")
def linked():
    base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base_part", "arm_part"
    base.material = arm.material = metals.aluminum()
    lower = bd.Compound(children=[base], label="lower")
    upper = bd.Compound(children=[arm], label="upper")
    elbow = bd.RevoluteJoint("elbow", lower, axis=bd.Axis((40, 0, 20), (0, -1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("elbow", upper, elbow.location)
    elbow.connect_to(upper.joints["elbow"], angle=0)
    bd.RevoluteJoint("spare", lower, axis=bd.Axis((0, 0, 0), (0, 0, 1)))
    limits(lower, "spare", effort=1)
    root = bd.Compound(children=[lower, upper], label="linked")
    return limits(root, "elbow", effort=2, velocity=3, damping=0.1)
"""


class CompoundLinkTest(_Folder):
    def test_limits_on_a_joint_an_assembly_holds_are_described_and_round_trip_and_an_unpaired_one_warned(self) -> None:
        description, _structure = self.described("linked", LINKED)
        elbow = next(joint for joint in description.joints if joint.name == "elbow")
        self.assertEqual((elbow.effort, elbow.velocity, elbow.damping), (2.0, 3.0, 0.1))
        self.assertEqual(description.warnings, ("'lower' limits joint 'spare', which is no joint of the description: "
                                                "the limits are left out",))
        # A shape rebuilt from the document carries them on the compound that holds the joint, as the model gave them.
        rebuilt = {child.label: child for child in Source.read(self.folder / "XBF/linked.xbf").shape().children}
        self.assertEqual(rebuilt["lower"].__dict__["_drives"],
                         {"elbow": {"effort": 2.0, "velocity": 3.0, "damping": 0.1}, "spare": {"effort": 1.0}})
        self.assertNotIn("_drives", rebuilt["lower"].children[0].__dict__)


# A filled housing with no material, declared to weigh 350 g with a 200 g motor inside it; a hand of
# 120 g whose finger, two pads of aluminium and brass, weighs 50 g; contact friction on the hand and its
# own on one pad.
MASSES = """
import build123d as bd
from bd_materials import metals
from cad.build123d import friction, mass, point_mass
from cad.engine import xbf


@xbf("XBF/masses.xbf")
def masses():
    housing = bd.Box(40, 20, 10)
    housing.label = "housing"
    point_mass(housing, 200, bd.Pos(10, 0, 0), name="motor")
    mass(housing, {housing})
    palm = bd.Pos(100, 0, 0) * bd.Box(20, 20, 10)
    palm.label = "palm"
    pad_a = bd.Pos(130, 0, 0) * bd.Box(10, 10, 10)
    pad_a.label = "pad_a"
    pad_b = bd.Pos(130, 20, 0) * bd.Box(10, 10, 10)
    pad_b.label = "pad_b"
    palm.material = pad_a.material = metals.aluminum()
    pad_b.material = metals.brass()
    friction(pad_b, (1.2, 0.01, 0.001))
    finger = mass(bd.Compound(children=[pad_a, pad_b], label="finger"), 50)
    hand = mass(bd.Compound(children=[palm, finger], label="hand"), {hand})
    friction(hand, 0.9)
    return bd.Compound(children=[housing, hand], label="masses")
"""


def _box(mass: float, a: float, b: float, c: float) -> np.ndarray:
    return np.diag([mass / 12 * (b * b + c * c), mass / 12 * (a * a + c * c), mass / 12 * (a * a + b * b)])


def _moved(inertia: np.ndarray, mass: float, offset: Any) -> np.ndarray:
    offset = np.asarray(offset, dtype=float)
    return inertia + mass * (float(offset @ offset) * np.eye(3) - np.outer(offset, offset))


class MassTest(_Folder):
    def test_a_declared_mass_scales_its_solids_point_masses_count_towards_it_and_inner_ones_fix_theirs(self) -> None:
        from bd_materials import metals

        description, structure = self.described("masses", MASSES.format(housing=350, hand=120))
        self.assertEqual([link.name for link in description.links], ["world", "housing", "hand"])
        # The housing: 150 g of uniform box about its centre and the 200 g motor 10 mm along X.
        housing = description.link("housing").inertial
        self.assertAlmostEqual(housing.mass, 0.35, delta=1e-12)
        centre = np.array([0.2 * 0.01 / 0.35, 0, 0])
        np.testing.assert_allclose(housing.center, centre, atol=1e-12)
        expected = _moved(_box(0.15, 0.04, 0.02, 0.01), 0.15, -centre) + _moved(np.zeros((3, 3)), 0.2,
                                                                                  np.array([0.01, 0, 0]) - centre)
        np.testing.assert_allclose(housing.inertia, expected, atol=1e-12)
        # The hand: its finger's 50 g split between the pads as aluminium is to brass, the palm the other 70 g.
        aluminium, brass = float(metals.aluminum().material.density), float(metals.brass().material.density)
        pad_a, pad_b = 0.05 * aluminium / (aluminium + brass), 0.05 * brass / (aluminium + brass)
        hand = description.link("hand")
        self.assertAlmostEqual(hand.inertial.mass, 0.12, delta=1e-12)
        centre = (pad_a * np.array([0.03, 0, 0]) + pad_b * np.array([0.03, 0.02, 0])) / 0.12
        np.testing.assert_allclose(hand.inertial.center, centre, atol=1e-12)
        expected = (_moved(_box(0.07, 0.02, 0.02, 0.01), 0.07, -centre)
                    + _moved(_box(pad_a, 0.01, 0.01, 0.01), pad_a, np.array([0.03, 0, 0]) - centre)
                    + _moved(_box(pad_b, 0.01, 0.01, 0.01), pad_b, np.array([0.03, 0.02, 0]) - centre))
        np.testing.assert_allclose(hand.inertial.inertia, expected, atol=1e-12)
        # Friction: the hand's on every part below it, the pad's own over it; the housing declares none.
        self.assertEqual([(c.name, c.friction) for c in hand.collisions],
                         [("palm", (0.9,)), ("pad_a", (0.9,)), ("pad_b", (1.2, 0.01, 0.001))])
        self.assertEqual(description.link("housing").collisions[0].friction, ())
        self.assertEqual(description.warnings, ())
        # The structure carries each mass on the parts below it, levels above them; a shape rebuilt from the
        # document puts each back on the node that declared it.
        path = self.folder / "XBF/masses.xbf"
        loaded = document.Loaded(path).structure()
        self.assertEqual(loaded["prototypes"], document.tree_structure(document.saved(path), path)["prototypes"])
        by_name = {prototype["name"]: prototype for prototype in loaded["prototypes"]}
        self.assertEqual((by_name["palm"]["mass"], by_name["pad_b"]["mass"]), ([[1, 120.0]], [[2, 120.0], [1, 50.0]]))
        self.assertEqual(by_name["housing"]["pointMasses"]["motor"]["grams"], 200.0)
        self.assertEqual(by_name["pad_a"]["friction"], [0.9])
        rebuilt = Source.read(path).shape()
        nodes = {node.label: node for node in [rebuilt, *rebuilt.descendants]}
        self.assertEqual({label: node.__dict__.get("_mass") for label, node in nodes.items()},
                         {"masses": None, "housing": 350.0, "hand": 120.0, "palm": None, "finger": 50.0,
                          "pad_a": None, "pad_b": None})
        self.assertEqual(nodes["housing"].__dict__["_points"]["motor"][0], 200.0)

    def test_a_mass_its_lumps_or_its_inner_masses_cannot_make_is_refused_by_name(self) -> None:
        import build123d as bd

        from cad.build123d import friction, mass, point_mass

        for housing, hand, said in ((150, 120, "'housing', declared to weigh 150 g, holds point masses and inner "
                                                "masses of 200 g"),
                                    (350, 40, "'hand', declared to weigh 40 g, holds point masses and inner masses "
                                              "of 50 g")):
            with self.assertRaisesRegex(DescriptionError, said):
                self.described("masses", MASSES.format(housing=housing, hand=hand))
        part = bd.Box(1, 1, 1)
        part.label = "part"
        with self.assertRaisesRegex(ValueError, "mass of part: grams is a positive number, not 0"):
            mass(part, 0)
        with self.assertRaisesRegex(ValueError, "an assembly; put the point mass on the part"):
            point_mass(bd.Compound(children=[part], label="assembly"), 10, bd.Location())
        with self.assertRaisesRegex(ValueError, "is no body's"):
            point_mass(part, 10, bd.Location(), inertia=(1, 0, 0))
        with self.assertRaisesRegex(ValueError, "one coefficient, or three"):
            friction(part, (1, 2))


# A slab of aluminium turned off every axis, in a link whose frame is an anchor (no material) turned
# another way: its inertia in the link frame is ``R I R^T`` with ``R`` the slab's turn seen from the anchor.
TURNED = """
import build123d as bd
from bd_materials import metals
from cad.engine import xbf


@xbf("XBF/turned.xbf")
def turned():
    anchor = bd.Location((5, -10, 20), (0, 0, 1), 90) * bd.Box(4, 4, 4)
    anchor.label = "anchor"
    slab = bd.Location((30, 15, -5), (1, 2, 3), 40) * bd.Box(60, 20, 10)
    slab.label = "slab"
    slab.material = metals.aluminum()
    return bd.Compound(children=[bd.Compound(children=[anchor, slab], label="rig")], label="turned")
"""


def _turn(axis: Any, degrees: float) -> np.ndarray:
    """Rodrigues: a turn of ``degrees`` about ``axis``."""
    k = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    angle = math.radians(degrees)
    return np.eye(3) + math.sin(angle) * cross + (1 - math.cos(angle)) * cross @ cross


class InertiaRotationTest(_Folder):
    def test_a_turned_link_s_inertia_is_written_in_its_own_frame_in_each_format(self) -> None:
        import xml.etree.ElementTree as ET

        import mujoco

        from cad.engine.export import mjcf, urdf

        description, _structure = self.described("turned", TURNED)
        anchor, slab = _turn((0, 0, 1), 90), _turn((1, 2, 3), 40)
        turn = anchor.T @ slab
        mass = 0.06 * 0.02 * 0.01 * _aluminium()
        expected = turn @ _box(mass, 0.06, 0.02, 0.01) @ turn.T
        centre = anchor.T @ (np.array([0.03, 0.015, -0.005]) - np.array([0.005, -0.01, 0.02]))
        self.assertGreater(abs(expected[0, 1]) + abs(expected[0, 2]) + abs(expected[1, 2]), 1e-7)  # truly off-axis
        link = description.link("rig")
        np.testing.assert_allclose(link.frame[:3, :3], anchor, atol=1e-12)
        np.testing.assert_allclose(link.inertial.inertia, expected, rtol=0, atol=1e-12)
        np.testing.assert_allclose(link.inertial.center, centre, atol=1e-12)
        # MJCF: principal moments on a quat in the body frame, as MuJoCo compiles them.
        out = self.folder / "mjcf/turned.xml"
        mjcf.write_description(description, out)
        model = mujoco.MjModel.from_xml_path(str(out))
        body = model.body("rig")
        axes = np.zeros(9)
        mujoco.mju_quat2Mat(axes, body.iquat)
        axes = axes.reshape(3, 3)
        np.testing.assert_allclose(axes @ np.diag(body.inertia) @ axes.T, expected, rtol=0, atol=1e-11)
        np.testing.assert_allclose(body.ipos, centre, atol=1e-9)
        # URDF: the six terms about the centre, rpy zero, in the link frame.
        out = self.folder / "urdf/turned.urdf"
        urdf.write_description(description, out)
        (written,) = ET.parse(out).getroot().iter("inertial")
        self.assertEqual(written.find("origin").get("rpy"), "0 0 0")
        np.testing.assert_allclose([float(v) for v in written.find("origin").get("xyz").split()], centre, atol=1e-9)
        terms = {key: float(value) for key, value in written.find("inertia").attrib.items()}
        tensor = np.array([[terms["ixx"], terms["ixy"], terms["ixz"]], [terms["ixy"], terms["iyy"], terms["iyz"]],
                           [terms["ixz"], terms["iyz"], terms["izz"]]])
        np.testing.assert_allclose(tensor, expected, rtol=1e-8, atol=1e-14)


# A declared part moved after its declarations: an edit of one rebuilds what the memo hands back.
MOVED = """
import build123d as bd
from cad.build123d import collision, frame, free, link, mass
from cad.engine import xbf


@xbf("XBF/moved.xbf")
def moved():
    block = bd.Box(10, 20, 30)
    block.label = "block"
    collision(block, "{kind}")
    frame(block, "tip", bd.Pos({at}, 0, 15))
    mass(block, {at} * 10)
    link(block, "{name}")
    {free}
    return bd.Compound(children=[block.moved(bd.Pos(50, 0, 0))], label="moved")
"""


class WarmEditTest(_Folder):
    def test_an_edit_of_a_declaration_reaches_the_document_through_a_warm_build(self) -> None:
        for kind, at, name, floats in (("box", 5, "alpha", False), ("sphere", 7, "alpha", True),
                                       ("sphere", 7, "beta", True), ("sphere", 7, "beta", False)):
            source = MOVED.format(kind=kind, at=at, name=name, free="free(block)" if floats else "pass")
            path = self.build("moved", source)
            (prototype,) = document.Loaded(path).structure()["prototypes"]
            self.assertEqual(prototype["collision"], kind)
            self.assertEqual(prototype["frames"]["tip"][12:15], [at, 0, 15])
            self.assertEqual(prototype["mass"], [[0, at * 10.0]])
            self.assertEqual((prototype["link"], prototype.get("free")), ([[0, name]], [0] if floats else None))


class UnjointedTest(_Folder):
    def test_with_no_mechanism_each_top_level_part_is_a_link_hung_fixed_from_the_world(self) -> None:
        description, structure = self.described("pair", PAIR)
        self.assertEqual([link.name for link in description.links], ["world", "left", "right"])
        self.assertEqual([(joint.kind, joint.parent, joint.child) for joint in description.joints],
                         [("fixed", "world", "left"), ("fixed", "world", "right")])
        right = description.link("right")
        np.testing.assert_allclose(right.frame, _metres(np.array(structure["instances"][1]["matrix"]).reshape(4, 4).T),
                                   atol=1e-12)
        np.testing.assert_allclose(description.joints[1].origin, right.frame, atol=1e-12)
        # A part with no density has no inertial, and the description says so by its link's name.
        self.assertIsNotNone(description.link("left").inertial)
        self.assertIsNone(right.inertial)
        self.assertTrue(any("'right'" in warning and "density" in warning for warning in description.warnings),
                        description.warnings)
        self.assertEqual(description.poses, [])

    def test_a_density_that_is_not_positive_is_refused(self) -> None:
        with self.assertRaisesRegex(DescriptionError, "'block'.*'foam'.*not positive"):
            self.described("foam", WEIGHTLESS)


class LoopTest(_Folder):
    def test_a_loop_is_a_tree_and_the_closure_its_last_pair_whose_frames_coincide_as_built(self) -> None:
        description, structure = self.described("four_bar", FOUR_BAR)
        self.assertEqual([(joint.name, joint.parent, joint.child) for joint in description.joints],
                         [("four_bar", "world", "base"), ("a", "base", "crank"), ("d", "base", "rocker"),
                          ("b", "crank", "coupler")])
        [closure] = description.closures
        self.assertEqual((closure.name, closure.kind, closure.parent, closure.child, closure.loop),
                         ("c", "revolute", "rocker", "coupler", ("d", "c", "b", "a")))
        # Its two frames are one place as built: on the hinge at C, its Z the axis (+Y).
        here = description.link("rocker").frame @ closure.origin
        there = description.link("coupler").frame @ closure.frame
        np.testing.assert_allclose(here, there, atol=1e-12)
        np.testing.assert_allclose(here[:3, 3], [0.055, 0, 0.05], atol=1e-9)
        np.testing.assert_allclose(here[:3, 2], [0, 1, 0], atol=1e-12)
        self.assert_placed_as_the_mechanism_places(description, {
            **structure, "kinematics": {**structure["kinematics"], "configurations": {}}})
        # A state moving a joint of the loop has no pose without a solver: left out, and said.
        self.assertEqual(description.poses, [])
        self.assertIn("mechanism state 'swung' moves joint 'a', which is in a loop and has no pose without a solver: "
                      "the description leaves the state out", description.warnings)
        # A joint stop sweep moves one joint alone, which no joint of a loop does.
        from cad.engine.ranges import sweep

        self.assertEqual({stops.joint: (stops.swept, stops.why) for stops in sweep(description)}, {
            name: (False, "it is in the loop through d, c, b, a, which moves as a whole: no joint of it moves alone")
            for name in ("a", "d", "b")})
        # Two hinges on one axis between the same two parts are a loop too: the second a closure.
        description, _structure = self.described("loop", LOOP)
        self.assertEqual([joint.name for joint in description.joints], ["loop", "near"])
        self.assertEqual([(c.name, c.parent, c.child, c.loop) for c in description.closures],
                         [("far", "base", "arm", ("far", "near"))])

    def test_a_loop_closing_at_a_slide_closes_at_its_nearest_turn_instead(self) -> None:
        description, _structure = self.described("cylinder", CYLINDER)
        [closure] = description.closures
        self.assertEqual((closure.name, closure.kind, closure.parent, closure.child), ("c", "revolute", "base", "barrel"))
        self.assertEqual([(joint.name, joint.kind, joint.parent, joint.child) for joint in description.joints[1:]],
                         [("a", "revolute", "base", "crank"), ("b", "revolute", "crank", "rod"),
                          ("s", "prismatic", "rod", "barrel")])
        np.testing.assert_allclose(description.link("base").frame @ closure.origin,
                                   description.link("barrel").frame @ closure.frame, atol=1e-12)


class VirtualPinionTest(_Folder):
    def test_a_pinion_that_holds_no_part_is_no_link_and_its_racks_follow_the_first(self) -> None:
        description, _structure = self.described("gripper", GRIPPER)
        self.assertEqual([link.name for link in description.links], ["world", "palm", "left", "right"])
        self.assertEqual([(joint.name, joint.kind, joint.follows) for joint in description.joints],
                         [("gripper", "fixed", None), ("left", "prismatic", None),
                          ("right", "prismatic", ("left", 2.0, 0.0))])
        self.assertEqual([joint.name for joint in description.controls()], ["left"])
        self.assertEqual(description.poses[0].name, "open")
        np.testing.assert_allclose([description.poses[0].values[name] for name in ("left", "right")], [0.015, 0.03],
                                   atol=1e-12)
        self.assertNotIn("pinion", description.poses[0].values)
        self.assertFalse([warning for warning in description.warnings if "pinion" in warning], description.warnings)


# A two-joint arm on a plate: its base named, the whole free, and two states to take the zero at.
TWO = """
import build123d as bd
from bd_materials import metals
from cad.build123d import free, link, mechanism_state
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
    {declare}
    root = bd.Compound(children=[plate, upper, fore], label="two")
    {root}
    mechanism_state(root, "home", shoulder=30, elbow=45)
    mechanism_state(root, "up", shoulder=90)
    return root
"""


class BaseAndZeroTest(_Folder):
    def test_a_free_base_floats_a_link_takes_its_declared_name_and_both_round_trip_through_the_xbf(self) -> None:
        description, _structure = self.described("two", TWO.format(declare='link(plate, "base_link")',
                                                                   root="free(root)"))
        self.assertEqual([link.name for link in description.links], ["world", "base_link", "upper", "fore"])
        self.assertEqual([(joint.name, joint.kind, joint.parent) for joint in description.joints],
                         [("two", "floating", "world"), ("shoulder", "revolute", "base_link"),
                          ("elbow", "revolute", "upper")])
        self.assertEqual([joint.name for joint in description.controls()], ["shoulder", "elbow"])
        self.assertEqual(description.summary("mjcf")["base"], "free")
        # The document keeps them on the parts, levels above each, and a shape rebuilt from it on their nodes.
        path = self.folder / "XBF/two.xbf"
        by_name = {prototype["name"]: prototype for prototype in document.Loaded(path).structure()["prototypes"]}
        self.assertEqual((by_name["plate"]["free"], by_name["plate"]["link"], by_name["fore"]["free"]),
                         ([1], [[0, "base_link"]], [1]))
        rebuilt = Source.read(path).shape()
        self.assertTrue(rebuilt.__dict__["_free"])
        self.assertEqual({child.label: child.__dict__.get("_link") for child in rebuilt.children},
                         {"plate": "base_link", "upper": None, "fore": None})

    def test_a_name_or_a_free_node_that_names_no_link_rightly_is_refused_by_name(self) -> None:
        with self.assertRaisesRegex(DescriptionError, "link name 'arm' is declared on parts of two links, 'upper' and "
                                                      "'fore'"):
            self.described("two", TWO.format(declare='link(upper, "arm"); link(fore, "arm")', root="pass"))
        with self.assertRaisesRegex(DescriptionError, "'world', which is the ground's name"):
            self.described("two", TWO.format(declare='link(plate, "world")', root="pass"))
        with self.assertRaisesRegex(DescriptionError, "'fore' is declared free, and none of its parts is in a link hung "
                                                      "from the world: part 'fore' is in link 'fore', which hangs from "
                                                      "'upper' by joint 'elbow'"):
            self.described("two", TWO.format(declare="free(fore)", root="pass"))
        with self.assertRaisesRegex(DescriptionError, "link 'pair' holds parts declared to be link 'a' and link 'b'"):
            self.described("pair", PAIR.replace("from cad.engine import xbf", "from cad.build123d import link\n"
                                                "from cad.engine import xbf").replace(
                '    return bd.Compound(children=[left, right], label="pair")',
                '    link(left, "a"); link(right, "b")\n'
                '    return bd.Compound(children=[bd.Compound(children=[left, right], label="pair")], label="top")'))

    def test_taken_at_a_state_every_body_stands_there_and_the_joints_count_from_it(self) -> None:
        source = TWO.format(declare="pass", root="pass")
        built, structure = self.described("two", source)
        found = describe(Source.read(self.folder / "XBF/two.xbf").view(), zero="home")
        home = next(pose for pose in built.poses if pose.name == "home").values
        # At zero, each link where the as-built description puts it at the state, which is where the mechanism
        # puts its parts there.
        posed = _frames_at(built, home)
        for link in found.links:
            np.testing.assert_allclose(link.frame, posed[link.name], atol=1e-12, err_msg=link.name)
        self.assertEqual(found.zero, "home")
        for name, at in (("shoulder", math.radians(30)), ("elbow", math.radians(45))):
            before, after = (next(joint for joint in each.joints if joint.name == name) for each in (built, found))
            np.testing.assert_allclose(after.limits, [(before.limits[0][0] - at, before.limits[0][1] - at)], atol=1e-12)
            np.testing.assert_allclose(after.as_built, [at], atol=1e-12)
        # The other states around it: up is the shoulder at 90 and the elbow as built.
        poses = {pose.name: pose.values for pose in found.poses}
        np.testing.assert_allclose([poses["home"]["shoulder"], poses["home"]["elbow"]], [0, 0], atol=1e-12)
        np.testing.assert_allclose([poses["up"]["shoulder"], poses["up"]["elbow"]],
                                   [math.radians(60), math.radians(-45)], atol=1e-12)
        self.assert_placed_as_the_mechanism_places(built, structure)
        with self.assertRaisesRegex(DescriptionError, "no mechanism state 'rest': the states are 'home', 'up'"):
            describe(Source.read(self.folder / "XBF/two.xbf").view(), zero="rest")
        with self.assertRaisesRegex(DescriptionError, "no mechanism state 'home': the document has no mechanism"):
            self.described("pair", PAIR, zero="home")


if __name__ == "__main__":
    unittest.main()

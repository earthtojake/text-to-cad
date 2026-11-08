"""A document described as a robot (``describe``, ``description.py``): the hinge's links, joint,
limits, as-built value and pose in SI, each box's mass, centre and inertia from its aluminium; the
description's frames composed at zero and at a state placing every part where the mechanism's
forward kinematics does, a pair followed backwards and a chain with a slide too; a coupling written
on the joints that follow; a part's collision and named frames, declared on the part and round-tripped
through the xbf and through a warm build; a model with no mechanism a link per top-level part; a loop described and refused;
a part with no density warned, one whose density is not positive refused."""

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


# A declared part moved after its declarations: an edit of one rebuilds what the memo hands back.
MOVED = """
import build123d as bd
from cad.build123d import collision, frame
from cad.engine import xbf


@xbf("XBF/moved.xbf")
def moved():
    block = bd.Box(10, 20, 30)
    block.label = "block"
    collision(block, "{kind}")
    frame(block, "tip", bd.Pos({at}, 0, 15))
    return bd.Compound(children=[block.moved(bd.Pos(50, 0, 0))], label="moved")
"""


class WarmEditTest(_Folder):
    def test_an_edit_of_a_declaration_reaches_the_document_through_a_warm_build(self) -> None:
        for kind, at in (("box", 5), ("sphere", 7), ("box", 5)):
            path = self.build("moved", MOVED.format(kind=kind, at=at))
            (prototype,) = document.Loaded(path).structure()["prototypes"]
            self.assertEqual(prototype["collision"], kind)
            self.assertEqual(prototype["frames"]["tip"][12:15], [at, 0, 15])


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

    def test_a_loop_is_described_and_refused_and_a_density_that_is_not_positive_refused(self) -> None:
        description, _structure = self.described("loop", LOOP)
        self.assertEqual(set(description.loops), {"near", "far"})
        self.assertEqual([joint.child for joint in description.joints], ["base", "arm", "arm"])
        with self.assertRaisesRegex(DescriptionError, "loop through"):
            description.check()
        with self.assertRaisesRegex(DescriptionError, "'block'.*'foam'.*not positive"):
            self.described("foam", WEIGHTLESS)


if __name__ == "__main__":
    unittest.main()

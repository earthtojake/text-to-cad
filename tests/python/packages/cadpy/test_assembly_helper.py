from __future__ import annotations

import sys
import types
import unittest
from contextlib import contextmanager

from cadpy.assembly import AssemblyHelper, MateTarget, label_shape, semantic_label, target


class FakeLocation:
    def __init__(self, value):
        self.value = value

    def __mul__(self, other):
        return FakeLocation(("mul", self.value, other.value))


class FakePart:
    def __init__(self):
        self.joints = {}
        self.label = None


class FakeJoint:
    def __init__(self, *, label, to_part, joint_location=None, **options):
        self.label = label
        self.to_part = to_part
        self.location = joint_location
        self.options = options
        self.connections = []
        to_part.joints[label] = self

    def connect_to(self, other, **options):
        self.connections.append((other, options))


class FakeCompound:
    def __init__(self, *, label, children):
        self.label = label
        self.children = tuple(children)


@contextmanager
def fake_build123d():
    module = types.SimpleNamespace(
        BallJoint=FakeJoint,
        Compound=FakeCompound,
        CylindricalJoint=FakeJoint,
        LinearJoint=FakeJoint,
        Location=FakeLocation,
        RevoluteJoint=FakeJoint,
        RigidJoint=FakeJoint,
    )
    original = sys.modules.get("build123d")
    sys.modules["build123d"] = module
    try:
        yield module
    finally:
        if original is None:
            sys.modules.pop("build123d", None)
        else:
            sys.modules["build123d"] = original


class AssemblyHelperTests(unittest.TestCase):
    def test_semantic_label_normalizes_tokens(self) -> None:
        self.assertEqual(
            "component:base_plate:left_side",
            semantic_label("component", "base plate", "left:side"),
        )

    def test_label_shape_sets_native_label_and_color(self) -> None:
        shape = types.SimpleNamespace()
        color = object()

        returned = label_shape(shape, "feature", "m3 standoff", "front left", color=color)

        self.assertIs(returned, shape)
        self.assertEqual("feature:m3_standoff:front_left", shape.label)
        self.assertIs(color, shape.color)

    def test_helper_connects_fixed_joint_to_moving_joint(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("enclosure")
            base = assembly.add(FakePart(), "base")
            lid = assembly.add(FakePart(), "lid")
            base_frame = assembly.rigid_frame(base, "lid_seat", FakeLocation("base_frame"))
            lid_frame = assembly.rigid_frame(lid, "underside", FakeLocation("lid_frame"))

            relation = assembly.face_to_face(base_frame, lid_frame)

        fixed_joint = base.joints["mate:lid_seat"]
        moving_joint = lid.joints["mate:underside"]
        self.assertEqual("face_to_face", relation.relation)
        self.assertEqual("mate:lid_seat", relation.fixed)
        self.assertEqual("mate:underside", relation.moving)
        self.assertEqual([(moving_joint, {})], fixed_joint.connections)

    def test_helper_accepts_existing_native_joint_labels(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("hinge")
            frame = FakePart()
            leaf = FakePart()
            fixed_joint = FakeJoint(
                label="hinge_axis",
                to_part=frame,
                joint_location=FakeLocation("frame_axis"),
            )
            moving_joint = FakeJoint(
                label="leaf_axis",
                to_part=leaf,
                joint_location=FakeLocation("leaf_axis"),
            )

            relation = assembly.revolute(
                (frame, "hinge_axis"),
                (leaf, "leaf_axis"),
                angle=45,
            )

        self.assertEqual("revolute", relation.relation)
        self.assertEqual({"angle": 45}, relation.parameters)
        self.assertEqual([(moving_joint, {"angle": 45})], fixed_joint.connections)

    def test_axis_frames_use_native_joint_axis_argument(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("hinge")
            frame = FakePart()

            frame_target = assembly.revolute_frame(
                frame,
                "hinge_axis",
                "Axis.Z",
                angular_range=(-90, 90),
            )

        self.assertEqual(MateTarget(frame, "mate:hinge_axis"), frame_target)
        joint = frame.joints["mate:hinge_axis"]
        self.assertIsNone(joint.location)
        self.assertEqual({"axis": "Axis.Z", "angular_range": (-90, 90)}, joint.options)

    def test_offset_target_creates_temporary_native_joint(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("offset")
            base = FakePart()
            lid = FakePart()
            base_frame = assembly.rigid_frame(base, "seat", FakeLocation("base"))
            lid_frame = assembly.rigid_frame(lid, "underside", FakeLocation("lid"))

            relation = assembly.face_to_face(base_frame, lid_frame, offset=0.5)

        offset_joint = base.joints["mate_target:mate_seat:offset"]
        self.assertIsInstance(offset_joint.location, FakeLocation)
        self.assertEqual(("mul", "base", (0.0, 0.0, 0.5)), offset_joint.location.value)
        self.assertEqual("mate_target:mate_seat:offset", relation.fixed)

    def test_build_returns_labeled_compound(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("robot arm")
            base = assembly.add(FakePart(), "base")
            arm = assembly.add(FakePart(), "arm")

            compound = assembly.build()

        self.assertEqual("assembly:robot_arm", compound.label)
        self.assertEqual((base, arm), compound.children)

    def test_target_tuple_is_available_for_call_sites(self) -> None:
        part = object()

        self.assertEqual(MateTarget(part, "axis"), target(part, "axis"))


if __name__ == "__main__":
    unittest.main()

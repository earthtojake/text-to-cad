from __future__ import annotations

import sys
import types
import unittest
from contextlib import contextmanager

from cadpy.assembly import AssemblyHelper, MateTarget, label_shape, label_text, target
from cadpy.step_export import _collect_assembly_mates


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
    def test_label_text_normalizes_tokens(self) -> None:
        self.assertEqual(
            "base_plate:left_side",
            label_text("base plate", "left:side"),
        )

    def test_label_shape_sets_native_label_and_color(self) -> None:
        shape = types.SimpleNamespace()
        color = object()

        returned = label_shape(shape, "m3 standoff", "front left", color=color)

        self.assertIs(returned, shape)
        self.assertEqual("m3_standoff:front_left", shape.label)
        self.assertIs(color, shape.color)

    def test_helper_connects_fixed_joint_to_moving_joint(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("enclosure")
            base = assembly.add(FakePart(), "base")
            lid = assembly.add(FakePart(), "lid")
            base_frame = assembly.rigid_frame(base, "lid_seat", FakeLocation("base_frame"))
            lid_frame = assembly.rigid_frame(lid, "underside", FakeLocation("lid_frame"))

            relation = assembly.face_to_face(base_frame, lid_frame)

        fixed_joint = base.joints["lid_seat"]
        moving_joint = lid.joints["underside"]
        self.assertEqual("face_to_face", relation.relation)
        self.assertEqual("lid_seat", relation.fixed)
        self.assertEqual("underside", relation.moving)
        self.assertEqual({"part": "base", "frame": "lid_seat"}, relation.fixed_endpoint)
        self.assertEqual({"part": "lid", "frame": "underside"}, relation.moving_endpoint)
        self.assertEqual([(moving_joint, {})], fixed_joint.connections)

    def test_build_records_mate_endpoint_payloads(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("enclosure")
            base = assembly.add(FakePart(), "base")
            lid = assembly.add(FakePart(), "lid")
            base_frame = assembly.rigid_frame(base, "lid_seat", FakeLocation("base_frame"))
            lid_frame = assembly.rigid_frame(lid, "underside", FakeLocation("lid_frame"))

            assembly.face_to_face(base_frame, lid_frame, label="lid_mate")
            compound = assembly.build()

        self.assertEqual(
            [
                {
                    "id": "m1",
                    "label": "m1",
                    "sourceLabel": "lid_mate",
                    "type": "face_to_face",
                    "relation": "face_to_face",
                    "fixed": "lid_seat",
                    "moving": "underside",
                    "parameters": {},
                    "fixedEndpoint": {"part": "base", "frame": "lid_seat"},
                    "movingEndpoint": {"part": "lid", "frame": "underside"},
                }
            ],
            compound.assembly_mates,
        )

    def test_export_collection_renumbers_mates_globally(self) -> None:
        with fake_build123d():
            first = AssemblyHelper("first")
            first_base = first.add(FakePart(), "first_base")
            first_lid = first.add(FakePart(), "first_lid")
            first_base_frame = first.rigid_frame(first_base, "seat", FakeLocation("first_base"))
            first_lid_frame = first.rigid_frame(first_lid, "underside", FakeLocation("first_lid"))
            first.face_to_face(first_base_frame, first_lid_frame, label="first_mate")
            first_compound = first.build()

            second = AssemblyHelper("second")
            second_base = second.add(FakePart(), "second_base")
            second_lid = second.add(FakePart(), "second_lid")
            second_base_frame = second.rigid_frame(second_base, "seat", FakeLocation("second_base"))
            second_lid_frame = second.rigid_frame(second_lid, "underside", FakeLocation("second_lid"))
            second.face_to_face(second_base_frame, second_lid_frame, label="second_mate")
            second_compound = second.build()

            root = FakeCompound(label="root", children=[first_compound, second_compound])

        mates = _collect_assembly_mates(root)

        self.assertEqual(["m1", "m2"], [mate["id"] for mate in mates])
        self.assertEqual(["m1", "m2"], [mate["label"] for mate in mates])
        self.assertEqual(["first_mate", "second_mate"], [mate["sourceLabel"] for mate in mates])

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

        self.assertEqual(MateTarget(frame, "hinge_axis"), frame_target)
        joint = frame.joints["hinge_axis"]
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

        offset_joint = base.joints["seat:offset"]
        self.assertIsInstance(offset_joint.location, FakeLocation)
        self.assertEqual(("mul", "base", (0.0, 0.0, 0.5)), offset_joint.location.value)
        self.assertEqual("seat:offset", relation.fixed)

    def test_build_returns_labeled_compound(self) -> None:
        with fake_build123d():
            assembly = AssemblyHelper("robot arm")
            base = assembly.add(FakePart(), "base")
            arm = assembly.add(FakePart(), "arm")

            compound = assembly.build()

        self.assertEqual("robot_arm", compound.label)
        self.assertEqual((base, arm), compound.children)

    def test_target_tuple_is_available_for_call_sites(self) -> None:
        part = object()

        self.assertEqual(MateTarget(part, "axis"), target(part, "axis"))


if __name__ == "__main__":
    unittest.main()

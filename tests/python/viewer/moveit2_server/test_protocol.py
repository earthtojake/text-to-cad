from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.python.support.paths import add_repo_path

add_repo_path("viewer/moveit2_server")

from moveit2_server.dispatcher import dispatch
from moveit2_server.protocol import (
    MotionProtocolError,
    normalize_joint_values,
    normalize_motion_target,
    normalize_request,
)


def moveit2_context() -> dict[str, object]:
    return {
        "command": {
            "planningGroup": "arm",
            "jointNames": ["shoulder", "elbow"],
            "endEffectors": [
                {
                    "name": "tool",
                    "link": "tool_link",
                    "frame": "base_link",
                    "planningGroup": "arm",
                    "jointNames": ["shoulder", "elbow"],
                    "positionTolerance": 0.002,
                }
            ],
            "ik": {"timeout": 0.05, "attempts": 1, "tolerance": 0.002},
            "planner": {
                "pipeline": "ompl",
                "plannerId": "RRTConnectkConfigDefault",
                "planningTime": 1.0,
                "maxVelocityScalingFactor": 1.0,
                "maxAccelerationScalingFactor": 1.0,
            },
        },
    }


class FakeMoveIt2Adapter:
    def solve_pose(self, request: object) -> dict[str, object]:
        return {"jointValuesByNameDeg": {"shoulder": 11}}

    def plan_to_pose(self, request: object) -> dict[str, object]:
        return {
            "jointValuesByNameDeg": {"shoulder": 11},
            "trajectory": {"jointNames": ["shoulder", "elbow"], "points": []},
        }


class MoveIt2ProtocolTests(unittest.TestCase):
    def test_normalizes_joint_values(self) -> None:
        self.assertEqual(normalize_joint_values({"shoulder": "12.5"}), {"shoulder": 12.5})
        with self.assertRaisesRegex(MotionProtocolError, "empty joint names"):
            normalize_joint_values({"": 1})

    def test_normalizes_request_with_moveit2_context(self) -> None:
        request = normalize_request(
            {
                "id": "abc",
                "type": "srdf.solvePose",
                "payload": {
                    "file": "robot.srdf",
                    "target": {
                        "endEffector": "tool",
                        "frame": "base_link",
                        "xyz": [0.1, 0.0, 0.2],
                    },
                },
            },
            context=moveit2_context(),
        )

        self.assertEqual(request.id, "abc")
        self.assertEqual(request.protocol_version, 1)
        self.assertEqual(request.command["planningGroup"], "arm")

    def test_normalizes_target_orientation(self) -> None:
        target = normalize_motion_target({
            "target": {
                "endEffector": "tool",
                "frame": "base_link",
                "xyz": [0, 0, 0],
                "quat_xyzw": [0, 0, 0, 2],
            }
        })

        self.assertEqual(target["orientationMode"], "quat_xyzw")
        self.assertEqual(target["quat_xyzw"], (0.0, 0.0, 0.0, 1.0))

        with self.assertRaisesRegex(MotionProtocolError, "exactly one"):
            normalize_motion_target({
                "target": {
                    "endEffector": "tool",
                    "frame": "base_link",
                    "xyz": [0, 0, 0],
                    "quat_xyzw": [0, 0, 0, 1],
                    "rpy": [0, 0, 0],
                }
            })

    def test_dispatch_uses_moveit2_adapter_for_solve_and_plan(self) -> None:
        request = normalize_request(
            {
                "id": "abc",
                "type": "srdf.planToPose",
                "payload": {
                    "startJointValuesByNameDeg": {"shoulder": 10},
                    "target": {
                        "endEffector": "tool",
                        "frame": "base_link",
                        "xyz": [0.1, 0.0, 0.2],
                    },
                },
            },
            context=moveit2_context(),
        )

        with patch("moveit2_server.dispatcher._adapter", return_value=FakeMoveIt2Adapter()):
            result = dispatch(request)

        self.assertEqual(result["jointValuesByNameDeg"]["shoulder"], 11)
        self.assertEqual(result["trajectory"]["jointNames"], ["shoulder", "elbow"])


if __name__ == "__main__":
    unittest.main()

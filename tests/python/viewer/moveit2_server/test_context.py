from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.python.support.paths import add_repo_path

add_repo_path("viewer/moveit2_server")

from moveit2_server.context import build_moveit2_context
from moveit2_server.protocol import MotionProtocolError
from moveit2_server.server import handle_message


def write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_sample_robot(repo_root: Path, urdf_ref: str = "robot.urdf", srdf_ref: str = "robot.srdf") -> None:
    urdf_path = repo_root / urdf_ref
    srdf_path = repo_root / srdf_ref
    write_file(
        urdf_path,
        """
        <robot name="robot">
          <link name="base_link"/>
          <link name="wrist_link"/>
          <link name="tool_link"/>
          <joint name="shoulder" type="revolute">
            <parent link="base_link"/>
            <child link="wrist_link"/>
            <limit lower="-1" upper="1" effort="1" velocity="1"/>
          </joint>
          <joint name="wrist_tool" type="fixed">
            <parent link="wrist_link"/>
            <child link="tool_link"/>
          </joint>
        </robot>
        """,
    )
    relative_urdf_ref = Path(os.path.relpath(urdf_path, srdf_path.parent)).as_posix()
    write_file(
        srdf_path,
        f"""
        <robot name="robot" xmlns:tcad="https://text-to-cad.dev/srdf">
          <tcad:urdf path="{relative_urdf_ref}"/>
          <group name="arm">
            <joint name="shoulder"/>
          </group>
          <group name="tool_group">
            <link name="tool_link"/>
          </group>
          <end_effector name="tool" parent_link="wrist_link" group="tool_group" parent_group="arm"/>
          <group_state name="home" group="arm">
            <joint name="shoulder" value="0"/>
          </group_state>
        </robot>
        """,
    )


def sample_payload() -> dict[str, object]:
    return {
        "dir": "",
        "file": "robot.srdf",
        "startJointValuesByNameDeg": {"shoulder": 10},
        "target": {
            "endEffector": "tool",
            "frame": "base_link",
            "xyz": [0.1, 0.0, 0.2],
        },
        "moveit2": {
            "planningGroup": "arm",
            "endEffector": "tool",
            "targetFrame": "base_link",
            "ik": {"timeout": 0.2, "attempts": 3, "tolerance": 0.01},
            "planning": {
                "pipeline": "ompl",
                "plannerId": "RRTConnectkConfigDefault",
                "planningTime": 2.0,
                "maxVelocityScalingFactor": 0.5,
                "maxAccelerationScalingFactor": 0.25,
            },
        },
    }


class MoveIt2ContextTests(unittest.TestCase):
    def test_builds_context_from_srdf_file_and_request_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            write_sample_robot(repo_root)

            context = build_moveit2_context(
                repo_root=repo_root,
                dir="",
                file="robot.srdf",
                type="srdf.planToPose",
                payload=sample_payload(),
            )

            self.assertEqual(context["file"], "robot.srdf")
            self.assertEqual(context["command"]["planningGroup"], "arm")
            self.assertEqual(context["command"]["endEffectors"][0]["link"], "tool_link")
            self.assertTrue(context["command"]["ik"]["positionOnly"])
            self.assertEqual(context["command"]["endEffectors"][0]["positionTolerance"], 0.01)
            self.assertEqual(context["command"]["ik"]["attempts"], 3)
            self.assertEqual(context["command"]["planner"]["planningTime"], 2.0)
            self.assertIn("robot.srdf", context["modelAssetHash"])
            self.assertEqual(Path(str(context["urdfPath"])).resolve(), (repo_root / "robot.urdf").resolve())

    def test_chain_planning_group_uses_chain_joints_not_all_active_joints(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            write_file(
                repo_root / "robot.urdf",
                """
                <robot name="robot">
                  <link name="base_link"/>
                  <link name="shoulder_link"/>
                  <link name="wrist_link"/>
                  <link name="tool_link"/>
                  <link name="finger_link"/>
                  <joint name="shoulder" type="revolute">
                    <parent link="base_link"/>
                    <child link="shoulder_link"/>
                  </joint>
                  <joint name="elbow" type="revolute">
                    <parent link="shoulder_link"/>
                    <child link="wrist_link"/>
                  </joint>
                  <joint name="wrist_tool" type="fixed">
                    <parent link="wrist_link"/>
                    <child link="tool_link"/>
                  </joint>
                  <joint name="gripper" type="revolute">
                    <parent link="tool_link"/>
                    <child link="finger_link"/>
                  </joint>
                </robot>
                """,
            )
            write_file(
                repo_root / "robot.srdf",
                """
                <robot name="robot" xmlns:tcad="https://text-to-cad.dev/srdf">
                  <tcad:urdf path="robot.urdf"/>
                  <group name="arm">
                    <chain base_link="base_link" tip_link="tool_link"/>
                  </group>
                  <group name="gripper">
                    <joint name="gripper"/>
                    <link name="finger_link"/>
                  </group>
                  <end_effector name="tool" parent_link="tool_link" group="gripper" parent_group="arm"/>
                </robot>
                """,
            )

            context = build_moveit2_context(
                repo_root=repo_root,
                dir="",
                file="robot.srdf",
                type="srdf.solvePose",
                payload=sample_payload(),
            )

            self.assertEqual(context["command"]["jointNames"], ["shoulder", "elbow"])
            self.assertEqual(context["command"]["endEffectors"][0]["jointNames"], ["shoulder", "elbow"])

    def test_accepts_orientation_and_explicit_target_link(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            write_sample_robot(repo_root)
            payload = sample_payload()
            payload["target"]["quat_xyzw"] = [0, 0, 0, 2]
            payload["moveit2"]["targetLink"] = "tool_link"
            payload["moveit2"]["ik"]["positionOnly"] = False

            context = build_moveit2_context(
                repo_root=repo_root,
                dir="",
                file="robot.srdf",
                type="srdf.solvePose",
                payload=payload,
            )

            self.assertFalse(context["command"]["ik"]["positionOnly"])
            self.assertEqual(context["command"]["endEffectors"][0]["link"], "tool_link")

    def test_rejects_group_state_joint_outside_group_or_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            write_sample_robot(repo_root)
            srdf_path = repo_root / "robot.srdf"
            srdf_path.write_text(
                srdf_path.read_text(encoding="utf-8").replace(
                    '<joint name="shoulder" value="0"/>',
                    '<joint name="shoulder" value="2"/>',
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MotionProtocolError, "above its URDF upper limit"):
                build_moveit2_context(
                    repo_root=repo_root,
                    dir="",
                    file="robot.srdf",
                    type="srdf.solvePose",
                    payload=sample_payload(),
                )

    def test_accepts_repo_relative_file_ref_with_catalog_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            write_sample_robot(repo_root, "workspace/robot.urdf", "workspace/robot.srdf")
            payload = sample_payload()
            payload["dir"] = "workspace"
            payload["file"] = "workspace/robot.srdf"

            context = build_moveit2_context(
                repo_root=repo_root,
                dir="workspace",
                file="workspace/robot.srdf",
                type="srdf.solvePose",
                payload=payload,
            )

            self.assertEqual(context["dir"], "workspace")
            self.assertEqual(context["file"], "robot.srdf")
            self.assertEqual(Path(str(context["srdfPath"])).resolve(), (repo_root / "workspace/robot.srdf").resolve())

    def test_handle_message_uses_moveit2_context(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            write_sample_robot(repo_root)
            message = {"id": "req-1", "type": "srdf.solvePose", "payload": sample_payload()}

            with patch("moveit2_server.server.dispatch", return_value={"jointValuesByNameDeg": {"shoulder": 11}}):
                response = asyncio.run(handle_message(json.dumps(message), repo_root=repo_root))

            payload = json.loads(response)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["result"]["jointValuesByNameDeg"]["shoulder"], 11)

    def test_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(MotionProtocolError, "file must stay inside"):
                build_moveit2_context(
                    repo_root=Path(tempdir),
                    dir="",
                    file="../robot.srdf",
                    type="srdf.solvePose",
                    payload=sample_payload(),
                )

    def test_rejects_unknown_planning_group_from_request(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            write_sample_robot(repo_root)
            payload = sample_payload()
            payload["moveit2"]["planningGroup"] = "missing"

            with self.assertRaisesRegex(MotionProtocolError, "Selected planning group"):
                build_moveit2_context(
                    repo_root=repo_root,
                    dir="",
                    file="robot.srdf",
                    type="srdf.planToPose",
                    payload=payload,
                )


if __name__ == "__main__":
    unittest.main()

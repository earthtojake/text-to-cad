from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("viewer/moveit2_server")

from moveit2_server.moveit_py import (
    MoveItPyAdapter,
    _joint_state_seed,
    _native_start_joint_values,
    _robot_description_for_moveit,
)


class MoveItPyAdapterHelperTests(unittest.TestCase):
    def test_robot_description_rewrites_relative_meshes_to_file_uris(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            urdf_path = root / "robot.urdf"
            urdf_path.write_text(
                """
                <robot name="robot">
                  <link name="base">
                    <visual>
                      <geometry>
                        <mesh filename="STL/base.stl" />
                      </geometry>
                    </visual>
                  </link>
                </robot>
                """,
                encoding="utf-8",
            )

            description = _robot_description_for_moveit(urdf_path)

            self.assertIn((root / "STL/base.stl").resolve().as_uri(), description)
            self.assertNotIn('filename="STL/base.stl"', description)

    def test_config_dict_builds_moveit2_config_from_srdf_and_request_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            urdf_path = root / "robot.urdf"
            urdf_path.write_text('<robot name="robot"><link name="base" /></robot>', encoding="utf-8")
            srdf_path = root / "robot.srdf"
            srdf_path.write_text('<robot name="robot" />', encoding="utf-8")
            request = SimpleNamespace(
                context={
                    "urdfPath": str(urdf_path),
                    "srdfPath": str(srdf_path),
                    "srdf": {
                        "planningGroups": [
                            {"name": "arm", "jointNames": ["shoulder"]},
                            {"name": "arm_with_gripper", "subgroups": ["arm", "gripper"]},
                        ]
                    },
                },
                command={
                    "ik": {"timeout": 0.2, "attempts": 3},
                    "planner": {
                        "pipeline": "ompl",
                        "plannerId": "RRTConnectkConfigDefault",
                        "planningTime": 2.0,
                        "maxVelocityScalingFactor": 0.5,
                        "maxAccelerationScalingFactor": 0.25,
                    },
                },
            )

            config = MoveItPyAdapter()._config_dict(request)

            self.assertEqual(config["robot_description_semantic"], '<robot name="robot" />')
            self.assertEqual(config["robot_description_kinematics"]["arm"]["kinematics_solver_timeout"], 0.2)
            self.assertTrue(config["robot_description_kinematics"]["arm"]["position_only_ik"])
            self.assertNotIn("arm_with_gripper", config["robot_description_kinematics"])
            self.assertEqual(config["planning_pipelines"]["pipeline_names"], ["ompl"])
            self.assertEqual(config["plan_request_params"]["planning_attempts"], 3)
            self.assertEqual(config["plan_request_params"]["max_velocity_scaling_factor"], 0.5)
            self.assertIsNot(config["plan_request_params"], config["ompl_rrtc"]["plan_request_params"])
            self.assertEqual(config["ompl_rrtc"]["plan_request_params"]["planning_attempts"], 3)
            self.assertEqual(config["planning_scene_monitor_options"]["wait_for_initial_state_timeout"], 5.0)

    def test_joint_state_seed_includes_all_active_urdf_joints(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            urdf_path = Path(tempdir) / "robot.urdf"
            urdf_path.write_text(
                """
                <robot name="robot">
                  <joint name="fixed_base" type="fixed" />
                  <joint name="shoulder" type="revolute" />
                  <joint name="slide" type="prismatic" />
                </robot>
                """,
                encoding="utf-8",
            )
            request = SimpleNamespace(
                context={"urdfPath": str(urdf_path)},
                payload={"startJointValuesByNameDeg": {"shoulder": 90, "slide": 0.25}},
                command={
                    "planningGroup": "arm",
                    "jointNames": ["shoulder"],
                },
            )

            names, positions = _joint_state_seed(request)

            self.assertEqual(names, ["shoulder", "slide"])
            self.assertAlmostEqual(positions[0], 1.5707963267948966)
            self.assertEqual(positions[1], 0.25)

    def test_legacy_start_joint_values_only_convert_angular_joints(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            urdf_path = Path(tempdir) / "robot.urdf"
            urdf_path.write_text(
                """
                <robot name="robot">
                  <joint name="shoulder" type="revolute" />
                  <joint name="slide" type="prismatic" />
                </robot>
                """,
                encoding="utf-8",
            )
            request = SimpleNamespace(
                context={"urdfPath": str(urdf_path)},
                payload={"startJointValuesByNameDeg": {"shoulder": 90, "slide": 0.25}},
                command={"jointNames": ["shoulder", "slide"]},
            )

            values = _native_start_joint_values(request)

            self.assertAlmostEqual(values["shoulder"], 1.5707963267948966)
            self.assertEqual(values["slide"], 0.25)

    def test_serializes_robot_trajectory_messages_with_fallback_timing(self) -> None:
        class Duration:
            sec = 0
            nanosec = 0

        class Point:
            def __init__(self, positions: list[float]) -> None:
                self.time_from_start = Duration()
                self.positions = positions

        class JointTrajectory:
            joint_names = ["shoulder", "elbow"]
            points = [Point([0.0, 0.0]), Point([1.5707963267948966, 0.0])]

        class RobotTrajectoryMsg:
            joint_trajectory = JointTrajectory()

        class RobotTrajectory:
            def get_robot_trajectory_msg(self) -> RobotTrajectoryMsg:
                return RobotTrajectoryMsg()

        request = SimpleNamespace(context={}, payload={}, command={"jointNames": ["shoulder", "elbow"]})
        serialized = MoveItPyAdapter()._serialize_trajectory(RobotTrajectory(), ["shoulder", "elbow"], request)

        self.assertEqual(serialized["jointNames"], ["shoulder", "elbow"])
        self.assertEqual(serialized["points"][0]["timeFromStartSec"], 0.0)
        self.assertGreater(serialized["points"][1]["timeFromStartSec"], 0.0)
        self.assertAlmostEqual(serialized["points"][1]["positions"][0], 1.5707963267948966)
        self.assertAlmostEqual(serialized["points"][1]["positionsDeg"][0], 90.0)


if __name__ == "__main__":
    unittest.main()


class MoveItPyCacheTests(unittest.TestCase):
    """The warm-instance cache is bounded LRU: heavyweight ROS nodes cannot be allowed
    to accumulate one per model for the life of the server."""

    def _adapter(self, limit: int) -> MoveItPyAdapter:
        adapter = MoveItPyAdapter()
        adapter.CACHE_LIMIT = limit
        return adapter

    class _FakeMoveIt:
        instances: list["MoveItPyCacheTests._FakeMoveIt"] = []

        def __init__(self, name: str) -> None:
            self.name = name
            self.shutdown_calls = 0

        def shutdown(self) -> None:
            self.shutdown_calls += 1

    def tearDown(self) -> None:
        MoveItPyCacheTests._FakeMoveIt.instances.clear()

    def test_cache_sheds_the_least_recently_used_instance_beyond_the_limit(self) -> None:
        adapter = self._adapter(2)
        first = self._FakeMoveIt("a")
        second = self._FakeMoveIt("b")
        third = self._FakeMoveIt("c")

        adapter._store_moveit("a", first)
        adapter._store_moveit("b", second)
        adapter._store_moveit("c", third)

        self.assertIsNone(adapter._cached_moveit("a"), "oldest instance must be evicted")
        self.assertEqual(first.shutdown_calls, 1, "an evicted ROS node must be shut down")
        self.assertIs(adapter._cached_moveit("b"), second)
        self.assertIs(adapter._cached_moveit("c"), third)

    def test_a_cache_hit_refreshes_recency(self) -> None:
        adapter = self._adapter(2)
        first = self._FakeMoveIt("a")
        second = self._FakeMoveIt("b")

        adapter._store_moveit("a", first)
        adapter._store_moveit("b", second)
        # Touching "a" makes "b" the least recently used.
        self.assertIs(adapter._cached_moveit("a"), first)
        third = self._FakeMoveIt("c")
        adapter._store_moveit("c", third)

        self.assertIs(adapter._cached_moveit("a"), first)
        self.assertIsNone(adapter._cached_moveit("b"))
        self.assertEqual(second.shutdown_calls, 1)

    def test_an_eviction_shutdown_failure_is_swallowed(self) -> None:
        adapter = self._adapter(1)
        broken = self._FakeMoveIt("broken")

        def explode() -> None:
            raise RuntimeError("node already gone")

        broken.shutdown = explode  # type: ignore[method-assign]
        adapter._store_moveit("broken", broken)
        survivor = self._FakeMoveIt("survivor")
        adapter._store_moveit("survivor", survivor)

        self.assertIsNone(adapter._cached_moveit("broken"), "eviction must proceed past the failure")
        self.assertIs(adapter._cached_moveit("survivor"), survivor)

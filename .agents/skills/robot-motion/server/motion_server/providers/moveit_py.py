from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any
import xml.etree.ElementTree as ET

from motion_server.protocol import (
    MotionProtocolError,
    normalize_joint_values,
    normalize_motion_target,
)


def _deg_to_rad(value: float) -> float:
    return (float(value) * math.pi) / 180.0


def _rad_to_deg(value: float) -> float:
    return (float(value) * 180.0) / math.pi


def _solve_command(request: Any) -> dict[str, Any]:
    if request.type == "urdf.solvePose":
        return request.command
    return (
        request.context.get("motionConfig", {})
        .get("commands", {})
        .get("urdf.solvePose", {})
    )


def _target_end_effector_name(request: Any) -> str:
    target = request.payload.get("target") if isinstance(request.payload, dict) else None
    if not isinstance(target, dict):
        return ""
    return str(target.get("endEffector") or "").strip()


def _selected_end_effector(request: Any) -> dict[str, Any]:
    command = _solve_command(request)
    end_effectors = command.get("endEffectors", [])
    target_name = _target_end_effector_name(request)
    if target_name:
        for end_effector in end_effectors:
            if str(end_effector.get("name", "")).strip() == target_name:
                return end_effector
        raise MotionProtocolError(f"Unknown end effector {target_name}")
    for end_effector in end_effectors:
        return end_effector
    raise MotionProtocolError("moveit_py command endEffectors must be non-empty")


def _joint_names(request: Any) -> list[str]:
    command = _solve_command(request)
    end_effector = _selected_end_effector(request)
    joint_names = [
        str(name).strip()
        for name in end_effector.get("jointNames", command.get("jointNames", []))
        if str(name).strip()
    ]
    if not joint_names:
        raise MotionProtocolError("moveit_py command jointNames must be non-empty")
    return joint_names


def _end_effector(request: Any, name: str) -> dict[str, Any]:
    end_effector = _selected_end_effector(request)
    if str(end_effector.get("name", "")).strip() == name:
        return end_effector
    raise MotionProtocolError(f"Unknown end effector {name}")


def _planning_group(request: Any) -> str:
    command = _solve_command(request)
    end_effector = _selected_end_effector(request)
    planning_group = str(
        end_effector.get("planningGroup")
        or command.get("planningGroup")
        or request.command.get("planningGroup")
        or ""
    ).strip()
    if not planning_group:
        raise MotionProtocolError("moveit_py command planningGroup must be non-empty")
    return planning_group


def _read_yaml_file(file_path: Path) -> dict[str, Any]:
    if not file_path.is_file():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("moveit_py provider requires PyYAML to load MoveIt configuration sidecars.") from exc
    payload = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"MoveIt configuration sidecar must be a YAML object: {file_path}")
    return payload


def _robot_description_for_moveit(urdf_path: Path) -> str:
    """Return URDF XML with relative mesh paths rewritten as file URIs."""
    try:
        tree = ET.parse(urdf_path)
    except ET.ParseError:
        return urdf_path.read_text(encoding="utf-8")
    root = tree.getroot()
    changed = False
    for mesh in root.findall(".//mesh"):
        filename = str(mesh.get("filename") or "").strip()
        if not filename or "://" in filename or filename.startswith("package:"):
            continue
        path = Path(filename)
        if not path.is_absolute():
            path = urdf_path.parent / path
        mesh.set("filename", path.resolve().as_uri())
        changed = True
    if not changed:
        return urdf_path.read_text(encoding="utf-8")
    return ET.tostring(root, encoding="unicode")


def _active_urdf_joints(urdf_path: Path) -> list[tuple[str, str]]:
    try:
        root = ET.parse(urdf_path).getroot()
    except ET.ParseError:
        return []
    joints: list[tuple[str, str]] = []
    for joint in root.findall("joint"):
        name = str(joint.get("name") or "").strip()
        joint_type = str(joint.get("type") or "").strip()
        if name and joint_type != "fixed":
            joints.append((name, joint_type))
    return joints


def _joint_state_seed(request: Any) -> tuple[list[str], list[float]]:
    urdf_path = Path(str(request.context.get("urdfPath") or ""))
    joint_values = normalize_joint_values(request.payload.get("startJointValuesByNameDeg"))
    joints = _active_urdf_joints(urdf_path)
    if not joints:
        joints = [(name, "revolute") for name in _joint_names(request)]
    names: list[str] = []
    positions: list[float] = []
    for name, joint_type in joints:
        names.append(name)
        value = joint_values.get(name, 0.0)
        positions.append(float(value) if joint_type == "prismatic" else _deg_to_rad(value))
    return names, positions


class _JointStateSeeder:
    def __init__(self, request: Any, *, duration_sec: float = 8.0, rate_hz: float = 30.0) -> None:
        self._request = request
        self._duration_sec = duration_sec
        self._rate_hz = rate_hz
        self._process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        names, positions = _joint_state_seed(self._request)
        if not names:
            return
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "motion_server.joint_state_seed",
                "--names",
                json.dumps(names),
                "--positions",
                json.dumps(positions),
                "--duration",
                str(self._duration_sec),
                "--rate",
                str(self._rate_hz),
            ],
            stdout=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if not self._process or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=1.0)


class MoveItPyProvider:
    """MoveIt 2 adapter used by the local ROS 2 motion server."""

    def __init__(self) -> None:
        self._moveit_by_key: dict[str, Any] = {}

    def _config_dict(self, request: Any) -> dict[str, Any]:
        urdf_path = Path(str(request.context.get("urdfPath") or ""))
        sidecar_dir = Path(str(request.context.get("sidecarDir") or ""))
        if not urdf_path.is_file():
            raise RuntimeError(f"URDF file does not exist: {urdf_path}")
        config: dict[str, Any] = {
            "robot_description": _robot_description_for_moveit(urdf_path),
        }
        srdf_path = sidecar_dir / "moveit2_robot.srdf"
        if srdf_path.is_file():
            config["robot_description_semantic"] = srdf_path.read_text(encoding="utf-8")
        kinematics_path = sidecar_dir / "moveit2_kinematics.yaml"
        if kinematics_path.is_file():
            config["robot_description_kinematics"] = _read_yaml_file(kinematics_path)
        for sidecar_name in ("moveit2_planning_pipelines.yaml", "moveit2_py.yaml"):
            config.update(_read_yaml_file(sidecar_dir / sidecar_name))
        ompl_config = config.setdefault("ompl", {})
        if isinstance(ompl_config, dict):
            ompl_config.setdefault("planning_plugin", "ompl_interface/OMPLPlanner")
            ompl_config.setdefault("planning_plugins", ["ompl_interface/OMPLPlanner"])
            ompl_config.setdefault("request_adapters", [
                "default_planning_request_adapters/ResolveConstraintFrames",
                "default_planning_request_adapters/ValidateWorkspaceBounds",
                "default_planning_request_adapters/CheckStartStateBounds",
                "default_planning_request_adapters/CheckStartStateCollision",
            ])
            ompl_config.setdefault("start_state_max_bounds_error", 0.1)
        planning_scene_monitor_options = config.setdefault("planning_scene_monitor_options", {})
        if isinstance(planning_scene_monitor_options, dict):
            current_timeout = float(planning_scene_monitor_options.get("wait_for_initial_state_timeout") or 0.0)
            planning_scene_monitor_options["wait_for_initial_state_timeout"] = max(current_timeout, 5.0)
        return config

    def _moveit(self, request: Any) -> Any:
        try:
            import rclpy
            from moveit.planning import MoveItPy
        except ImportError as exc:
            raise RuntimeError(
                "moveit_py provider requires a ROS 2 environment with rclpy and moveit_py. "
                f"Current interpreter: {sys.executable}. Start motion_server from a RoboStack/ROS shell."
            ) from exc

        cache_key = str(request.context.get("explorerMetadataHash") or request.context.get("urdfPath") or "")
        if cache_key in self._moveit_by_key:
            return self._moveit_by_key[cache_key]

        if not rclpy.ok():
            rclpy.init(args=None)
        node_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:10] if cache_key else "default"
        config = self._config_dict(request)
        joint_state_seeder = _JointStateSeeder(request)
        joint_state_seeder.start()
        try:
            try:
                moveit = MoveItPy(
                    node_name=f"motion_server_{node_hash}",
                    config_dict=config,
                )
            except TypeError:
                # Older bindings do not expose config_dict; they require equivalent
                # ROS parameters to be supplied by the launch environment.
                moveit = MoveItPy(node_name=f"motion_server_{node_hash}")
        finally:
            joint_state_seeder.stop()
        self._moveit_by_key[cache_key] = moveit
        return moveit

    def _planning_component(self, request: Any, planning_group: str) -> Any:
        return self._moveit(request).get_planning_component(planning_group)

    def _robot_state(self, request: Any) -> Any:
        try:
            from moveit.core.robot_state import RobotState
        except ImportError as exc:
            raise RuntimeError(
                f"moveit_py provider could not import RobotState for {sys.executable}. "
                "Start motion_server from a RoboStack/ROS shell."
            ) from exc

        robot_state = RobotState(self._moveit(request).get_robot_model())
        joint_values = normalize_joint_values(request.payload.get("startJointValuesByNameDeg"))
        joint_names = _joint_names(request)
        radians = [_deg_to_rad(joint_values.get(name, 0.0)) for name in joint_names]
        planning_group = _planning_group(request)
        if hasattr(robot_state, "set_joint_group_positions"):
            robot_state.set_joint_group_positions(planning_group, radians)
        elif hasattr(robot_state, "set_joint_positions"):
            robot_state.set_joint_positions(joint_names, radians)
        else:
            raise RuntimeError("moveit_py RobotState does not expose a supported joint setter")
        return robot_state

    def _pose_stamped(self, request: Any) -> tuple[Any, dict[str, Any]]:
        try:
            from geometry_msgs.msg import PoseStamped
        except ImportError as exc:
            raise RuntimeError(
                f"moveit_py provider could not import geometry_msgs.msg.PoseStamped for {sys.executable}. "
                "Start motion_server from a RoboStack/ROS shell."
            ) from exc

        target = normalize_motion_target(request.payload)
        end_effector = _end_effector(request, target["endEffector"])
        pose = PoseStamped()
        pose.header.frame_id = target["frame"]
        pose.pose.position.x = target["xyz"][0]
        pose.pose.position.y = target["xyz"][1]
        pose.pose.position.z = target["xyz"][2]
        pose.pose.orientation.w = 1.0
        return pose, end_effector

    def _position_goal_constraints(self, target_pose: Any, end_effector: dict[str, Any]) -> list[Any]:
        try:
            from geometry_msgs.msg import Pose
            from moveit_msgs.msg import Constraints, PositionConstraint
            from shape_msgs.msg import SolidPrimitive
        except ImportError as exc:
            raise RuntimeError(
                f"moveit_py provider could not import MoveIt position constraint messages for {sys.executable}. "
                "Start motion_server from a RoboStack/ROS shell."
            ) from exc

        sphere = SolidPrimitive()
        sphere.type = SolidPrimitive.SPHERE
        sphere.dimensions = [float(end_effector.get("positionTolerance") or 0.002)]

        center = Pose()
        center.orientation.w = 1.0
        center.position.x = target_pose.pose.position.x
        center.position.y = target_pose.pose.position.y
        center.position.z = target_pose.pose.position.z

        position_constraint = PositionConstraint()
        position_constraint.header.frame_id = target_pose.header.frame_id
        position_constraint.link_name = str(end_effector.get("link") or "")
        position_constraint.constraint_region.primitives.append(sphere)
        position_constraint.constraint_region.primitive_poses.append(center)
        position_constraint.weight = 1.0

        constraints = Constraints()
        constraints.name = f"{position_constraint.link_name}_position_goal"
        constraints.position_constraints.append(position_constraint)
        return [constraints]

    def _joint_values_from_state(self, robot_state: Any, request: Any) -> dict[str, float]:
        joint_names = _joint_names(request)
        planning_group = _planning_group(request)
        if hasattr(robot_state, "get_joint_group_positions"):
            values_rad = robot_state.get_joint_group_positions(planning_group)
        elif hasattr(robot_state, "get_joint_positions"):
            values_rad = robot_state.get_joint_positions(joint_names)
        else:
            raise RuntimeError("moveit_py RobotState does not expose a supported joint getter")
        return {
            joint_name: _rad_to_deg(values_rad[index])
            for index, joint_name in enumerate(joint_names)
            if index < len(values_rad)
        }

    def solve_pose(self, request: Any) -> dict[str, Any]:
        robot_state = self._robot_state(request)
        target_pose, end_effector = self._pose_stamped(request)
        planning_group = _planning_group(request)

        if not hasattr(robot_state, "set_from_ik"):
            raise RuntimeError("moveit_py RobotState does not expose set_from_ik")
        ok = robot_state.set_from_ik(
            planning_group,
            target_pose.pose,
            end_effector.get("link"),
        )
        if not ok:
            return {
                "ok": False,
                "message": "MoveIt did not find a pose solution",
            }
        return {
            "jointValuesByNameDeg": self._joint_values_from_state(robot_state, request),
            "residual": {"position": 0.0},
        }

    def _serialize_trajectory(self, trajectory: Any, joint_names: list[str]) -> dict[str, Any]:
        if hasattr(trajectory, "get_robot_trajectory_msg"):
            trajectory = trajectory.get_robot_trajectory_msg()
        joint_trajectory = getattr(trajectory, "joint_trajectory", trajectory)
        source_joint_names = list(getattr(joint_trajectory, "joint_names", []) or joint_names)
        points = []
        for point in getattr(joint_trajectory, "points", []) or []:
            duration = getattr(point, "time_from_start", None)
            seconds = float(getattr(duration, "sec", 0)) + (float(getattr(duration, "nanosec", 0)) / 1_000_000_000)
            positions_by_name = {
                name: _rad_to_deg(point.positions[index])
                for index, name in enumerate(source_joint_names)
                if index < len(getattr(point, "positions", []))
            }
            points.append({
                "timeFromStartSec": seconds,
                "positionsDeg": [positions_by_name.get(name, 0.0) for name in joint_names],
            })
        if len(points) > 1 and all(point["timeFromStartSec"] <= 0.0 for point in points):
            total_joint_delta = 0.0
            for previous, current in zip(points, points[1:], strict=False):
                total_joint_delta += sum(
                    abs(current["positionsDeg"][index] - previous["positionsDeg"][index])
                    for index in range(min(len(previous["positionsDeg"]), len(current["positionsDeg"])))
                )
            total_duration = min(max(total_joint_delta / 240.0, 0.75), 4.0)
            step_duration = total_duration / float(len(points) - 1)
            for index, point in enumerate(points):
                point["timeFromStartSec"] = index * step_duration
        return {
            "jointNames": joint_names,
            "points": points,
        }

    def plan_to_pose(self, request: Any) -> dict[str, Any]:
        target_pose, end_effector = self._pose_stamped(request)
        planning_group = _planning_group(request)
        planning_component = self._planning_component(request, planning_group)
        start_state = self._robot_state(request)
        planning_component.set_start_state(robot_state=start_state)
        try:
            planning_component.set_goal_state(
                motion_plan_constraints=self._position_goal_constraints(target_pose, end_effector),
            )
        except TypeError:
            planning_component.set_goal_state(
                pose_stamped_msg=target_pose,
                pose_link=end_effector.get("link"),
            )

        plan_result = planning_component.plan()
        if not plan_result:
            return {
                "ok": False,
                "message": "MoveIt planning did not find a trajectory",
            }
        trajectory = self._serialize_trajectory(plan_result.trajectory, _joint_names(request))
        final_joint_values: dict[str, float] = {}
        if trajectory["points"]:
            final_joint_values = dict(zip(
                trajectory["jointNames"],
                trajectory["points"][-1]["positionsDeg"],
                strict=False,
            ))
        return {
            "jointValuesByNameDeg": final_joint_values,
            "trajectory": trajectory,
            "residual": {"position": 0.0},
        }

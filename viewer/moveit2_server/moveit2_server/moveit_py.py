from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from collections import OrderedDict
from pathlib import Path
import subprocess
import sys
from typing import Any
import xml.etree.ElementTree as ET

from moveit2_server.protocol import (
    MotionProtocolError,
    normalize_joint_values,
    normalize_motion_target,
)


def _deg_to_rad(value: float) -> float:
    return (float(value) * math.pi) / 180.0


def _rad_to_deg(value: float) -> float:
    return (float(value) * 180.0) / math.pi


def _solve_command(request: Any) -> dict[str, Any]:
    return request.command


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
    except (OSError, ET.ParseError):
        return []
    joints: list[tuple[str, str]] = []
    for joint in root.findall("joint"):
        name = str(joint.get("name") or "").strip()
        joint_type = str(joint.get("type") or "").strip()
        if name and joint_type != "fixed":
            joints.append((name, joint_type))
    return joints


def _urdf_joint_types(urdf_path: Path) -> dict[str, str]:
    try:
        root = ET.parse(urdf_path).getroot()
    except (OSError, ET.ParseError):
        return {}
    joint_types: dict[str, str] = {}
    for joint in root.findall("joint"):
        name = str(joint.get("name") or "").strip()
        joint_type = str(joint.get("type") or "").strip()
        if name:
            joint_types[name] = joint_type
    return joint_types


def _joint_types_for_request(request: Any) -> dict[str, str]:
    urdf_path = Path(str(request.context.get("urdfPath") or ""))
    joint_types = _urdf_joint_types(urdf_path)
    if joint_types:
        return joint_types
    command = _solve_command(request)
    fallback_names = [str(name).strip() for name in command.get("jointNames", []) if str(name).strip()]
    if not fallback_names:
        fallback_names = _joint_names(request)
    return {name: "revolute" for name in fallback_names}


def _native_start_joint_values(request: Any, joint_types: dict[str, str] | None = None) -> dict[str, float]:
    joint_types = joint_types or _joint_types_for_request(request)
    payload = request.payload if isinstance(request.payload, dict) else {}
    if "startJointValuesByName" in payload:
        return normalize_joint_values(payload.get("startJointValuesByName"), label="startJointValuesByName")
    legacy_values = normalize_joint_values(payload.get("startJointValuesByNameDeg"), label="startJointValuesByNameDeg")
    return {
        name: float(value) if str(joint_types.get(name) or "").strip() == "prismatic" else _deg_to_rad(value)
        for name, value in legacy_values.items()
    }


def _native_to_legacy_joint_value(value: float, joint_type: str) -> float:
    return float(value) if str(joint_type or "").strip() == "prismatic" else _rad_to_deg(value)


def _native_to_legacy_joint_values(values: dict[str, float], joint_types: dict[str, str]) -> dict[str, float]:
    return {
        name: _native_to_legacy_joint_value(value, str(joint_types.get(name) or "revolute"))
        for name, value in values.items()
    }


def _moveit2_groups(request: Any) -> list[dict[str, Any]]:
    srdf = request.context.get("srdf", {}) if isinstance(request.context, dict) else {}
    groups = srdf.get("planningGroups", []) if isinstance(srdf, dict) else []
    return [group for group in groups if isinstance(group, dict)]


def _supports_kdl_kinematics(group: dict[str, Any]) -> bool:
    if group.get("subgroups"):
        return False
    return bool(group.get("jointNames") or group.get("chains"))


def _kinematics_config(request: Any) -> dict[str, Any]:
    ik = request.command.get("ik", {}) if isinstance(request.command, dict) else {}
    return {
        str(group.get("name")): {
            "kinematics_solver": "kdl_kinematics_plugin/KDLKinematicsPlugin",
            "kinematics_solver_search_resolution": 0.005,
            "kinematics_solver_timeout": float(ik.get("timeout") or 0.05),
            "position_only_ik": bool(ik.get("positionOnly", True)),
        }
        for group in _moveit2_groups(request)
        if str(group.get("name") or "").strip() and _supports_kdl_kinematics(group)
    }


def _planning_pipeline_config(request: Any) -> dict[str, Any]:
    planner = request.command.get("planner", {}) if isinstance(request.command, dict) else {}
    pipeline = str(planner.get("pipeline") or "ompl")
    planner_id = str(planner.get("plannerId") or "RRTConnectkConfigDefault")
    planning_time = float(planner.get("planningTime") or 1.0)
    def request_params() -> dict[str, Any]:
        return {
            "planning_attempts": int(request.command.get("ik", {}).get("attempts") or 1),
            "planning_pipeline": pipeline,
            "planner_id": planner_id,
            "planning_time": planning_time,
            "max_velocity_scaling_factor": float(planner.get("maxVelocityScalingFactor") or 1.0),
            "max_acceleration_scaling_factor": float(planner.get("maxAccelerationScalingFactor") or 1.0),
        }

    return {
        "planning_pipelines": {
            "pipeline_names": [pipeline],
        },
        pipeline: {
            "planning_plugin": "ompl_interface/OMPLPlanner",
            "planning_plugins": ["ompl_interface/OMPLPlanner"],
            "request_adapters": [
                "default_planning_request_adapters/ResolveConstraintFrames",
                "default_planning_request_adapters/ValidateWorkspaceBounds",
                "default_planning_request_adapters/CheckStartStateBounds",
                "default_planning_request_adapters/CheckStartStateCollision",
            ],
            "start_state_max_bounds_error": 0.1,
        },
        "plan_request_params": request_params(),
        "ompl_rrtc": {
            "plan_request_params": request_params(),
        },
    }


def _joint_state_seed(request: Any) -> tuple[list[str], list[float]]:
    urdf_path = Path(str(request.context.get("urdfPath") or ""))
    joint_types = _joint_types_for_request(request)
    joint_values = _native_start_joint_values(request, joint_types)
    joints = _active_urdf_joints(urdf_path)
    if not joints:
        joints = [(name, "revolute") for name in _joint_names(request)]
    names: list[str] = []
    positions: list[float] = []
    for name, joint_type in joints:
        names.append(name)
        del joint_type
        positions.append(float(joint_values.get(name, 0.0)))
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
                "moveit2_server.joint_state_seed",
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


class MoveItPyAdapter:
    """MoveIt 2 adapter used by the local ROS 2 MoveIt2 server."""

    # Warm MoveItPy instances are heavyweight (a ROS node plus planning context per
    # model), so the cache is bounded: at most this many distinct models stay warm,
    # least-recently-used first out. Each model still pays its own first-touch cost;
    # the bound just stops an unbounded crawl across many robots.
    CACHE_LIMIT = max(1, int(os.environ.get("MOVEIT_PY_ADAPTER_CACHE", "5")))

    def __init__(self) -> None:
        self._moveit_by_key: OrderedDict[str, Any] = OrderedDict()

    def _config_dict(self, request: Any) -> dict[str, Any]:
        urdf_path = Path(str(request.context.get("urdfPath") or ""))
        srdf_path = Path(str(request.context.get("srdfPath") or ""))
        if not urdf_path.is_file():
            raise RuntimeError(f"URDF file does not exist: {urdf_path}")
        config: dict[str, Any] = {
            "robot_description": _robot_description_for_moveit(urdf_path),
            "robot_description_kinematics": _kinematics_config(request),
        }
        if srdf_path.is_file():
            config["robot_description_semantic"] = srdf_path.read_text(encoding="utf-8")
        config.update(_planning_pipeline_config(request))
        config["planning_scene_monitor_options"] = {
            "name": "planning_scene_monitor",
            "robot_description": "robot_description",
            "joint_state_topic": "/joint_states",
            "attached_collision_object_topic": "/moveit_cpp/planning_scene_monitor",
            "publish_planning_scene_topic": "/moveit_cpp/publish_planning_scene",
            "monitored_planning_scene_topic": "/moveit_cpp/monitored_planning_scene",
            "wait_for_initial_state_timeout": 5.0,
        }
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
                "moveit_py adapter requires a ROS 2 environment with rclpy and moveit_py. "
                f"Current interpreter: {sys.executable}. Start moveit2_server from a RoboStack/ROS shell."
            ) from exc

        cache_key = str(request.context.get("modelAssetHash") or request.context.get("urdfPath") or "")
        cached = self._cached_moveit(cache_key)
        if cached is not None:
            return cached

        if not rclpy.ok():
            rclpy.init(args=None)
        node_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:10] if cache_key else "default"
        config = self._config_dict(request)
        joint_state_seeder = _JointStateSeeder(request)
        joint_state_seeder.start()
        try:
            try:
                moveit = MoveItPy(
                    node_name=f"moveit2_server_{node_hash}",
                    config_dict=config,
                )
            except TypeError:
                # Older bindings do not expose config_dict; they require equivalent
                # ROS parameters to be supplied by the launch environment.
                moveit = MoveItPy(node_name=f"moveit2_server_{node_hash}")
        finally:
            joint_state_seeder.stop()
        self._store_moveit(cache_key, moveit)
        return moveit

    def _cached_moveit(self, cache_key: str) -> Any | None:
        """The warm instance for ``cache_key``, refreshing its recency, or None."""
        moveit = self._moveit_by_key.get(cache_key)
        if moveit is not None:
            self._moveit_by_key.move_to_end(cache_key)
        return moveit

    def _store_moveit(self, cache_key: str, moveit: Any) -> None:
        """Insert a built instance and shed the least-recently-used ones beyond the
        bound. Eviction shuts each instance down best-effort -- it is a ROS node with
        native state, so letting it be garbage-collected silently would leak the node."""
        self._moveit_by_key[cache_key] = moveit
        self._moveit_by_key.move_to_end(cache_key)
        while len(self._moveit_by_key) > self.CACHE_LIMIT:
            _, evicted = self._moveit_by_key.popitem(last=False)
            shutdown = getattr(evicted, "shutdown", None)
            if callable(shutdown):
                with contextlib.suppress(Exception):
                    shutdown()

    def _planning_component(self, request: Any, planning_group: str) -> Any:
        return self._moveit(request).get_planning_component(planning_group)

    def _robot_state(self, request: Any) -> Any:
        try:
            from moveit.core.robot_state import RobotState
        except ImportError as exc:
            raise RuntimeError(
                f"moveit_py adapter could not import RobotState for {sys.executable}. "
                "Start moveit2_server from a RoboStack/ROS shell."
            ) from exc

        robot_state = RobotState(self._moveit(request).get_robot_model())
        joint_values = _native_start_joint_values(request)
        joint_names = _joint_names(request)
        positions = [float(joint_values.get(name, 0.0)) for name in joint_names]
        planning_group = _planning_group(request)
        if hasattr(robot_state, "set_joint_group_positions"):
            robot_state.set_joint_group_positions(planning_group, positions)
        elif hasattr(robot_state, "set_joint_positions"):
            robot_state.set_joint_positions(joint_names, positions)
        else:
            raise RuntimeError("moveit_py RobotState does not expose a supported joint setter")
        return robot_state

    def _pose_stamped(self, request: Any) -> tuple[Any, dict[str, Any]]:
        try:
            from geometry_msgs.msg import PoseStamped
        except ImportError as exc:
            raise RuntimeError(
                f"moveit_py adapter could not import geometry_msgs.msg.PoseStamped for {sys.executable}. "
                "Start moveit2_server from a RoboStack/ROS shell."
            ) from exc

        target = normalize_motion_target(request.payload)
        end_effector = _end_effector(request, target["endEffector"])
        pose = PoseStamped()
        pose.header.frame_id = target["frame"]
        pose.pose.position.x = target["xyz"][0]
        pose.pose.position.y = target["xyz"][1]
        pose.pose.position.z = target["xyz"][2]
        quat_xyzw = target.get("quat_xyzw") or (0.0, 0.0, 0.0, 1.0)
        pose.pose.orientation.x = quat_xyzw[0]
        pose.pose.orientation.y = quat_xyzw[1]
        pose.pose.orientation.z = quat_xyzw[2]
        pose.pose.orientation.w = quat_xyzw[3]
        return pose, end_effector

    def _position_only_ik(self, request: Any) -> bool:
        ik = request.command.get("ik", {}) if isinstance(request.command, dict) else {}
        return bool(ik.get("positionOnly", True))

    def _position_goal_constraints(self, target_pose: Any, end_effector: dict[str, Any]) -> list[Any]:
        try:
            from geometry_msgs.msg import Pose
            from moveit_msgs.msg import Constraints, PositionConstraint
            from shape_msgs.msg import SolidPrimitive
        except ImportError as exc:
            raise RuntimeError(
                f"moveit_py adapter could not import MoveIt position constraint messages for {sys.executable}. "
                "Start moveit2_server from a RoboStack/ROS shell."
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
            values = robot_state.get_joint_group_positions(planning_group)
        elif hasattr(robot_state, "get_joint_positions"):
            values = robot_state.get_joint_positions(joint_names)
        else:
            raise RuntimeError("moveit_py RobotState does not expose a supported joint getter")
        return {
            joint_name: float(values[index])
            for index, joint_name in enumerate(joint_names)
            if index < len(values)
        }

    def solve_pose(self, request: Any) -> dict[str, Any]:
        robot_state = self._robot_state(request)
        target_pose, end_effector = self._pose_stamped(request)
        planning_group = _planning_group(request)

        if not hasattr(robot_state, "set_from_ik"):
            raise RuntimeError("moveit_py RobotState does not expose set_from_ik")
        ik = request.command.get("ik", {}) if isinstance(request.command, dict) else {}
        timeout = float(ik.get("timeout") or 0.05)
        attempts = int(ik.get("attempts") or 1)
        try:
            ok = robot_state.set_from_ik(planning_group, target_pose.pose, end_effector.get("link"), timeout, attempts)
        except TypeError:
            try:
                ok = robot_state.set_from_ik(planning_group, target_pose.pose, end_effector.get("link"), timeout)
            except TypeError:
                ok = robot_state.set_from_ik(planning_group, target_pose.pose, end_effector.get("link"))
        if not ok:
            return {
                "ok": False,
                "message": "MoveIt did not find a pose solution",
            }
        joint_values = self._joint_values_from_state(robot_state, request)
        joint_types = _joint_types_for_request(request)
        return {
            "jointValuesByName": joint_values,
            "jointValuesByNameDeg": _native_to_legacy_joint_values(joint_values, joint_types),
            "positionOnly": self._position_only_ik(request),
            "residual": {"position": 0.0},
        }

    def _serialize_trajectory(self, trajectory: Any, joint_names: list[str], request: Any) -> dict[str, Any]:
        if hasattr(trajectory, "get_robot_trajectory_msg"):
            trajectory = trajectory.get_robot_trajectory_msg()
        joint_trajectory = getattr(trajectory, "joint_trajectory", trajectory)
        source_joint_names = list(getattr(joint_trajectory, "joint_names", []) or joint_names)
        joint_types = _joint_types_for_request(request)
        points = []
        for point in getattr(joint_trajectory, "points", []) or []:
            duration = getattr(point, "time_from_start", None)
            seconds = float(getattr(duration, "sec", 0)) + (float(getattr(duration, "nanosec", 0)) / 1_000_000_000)
            positions_by_name = {
                name: float(point.positions[index])
                for index, name in enumerate(source_joint_names)
                if index < len(getattr(point, "positions", []))
            }
            native_positions = [positions_by_name.get(name, 0.0) for name in joint_names]
            legacy_positions = [
                _native_to_legacy_joint_value(positions_by_name.get(name, 0.0), str(joint_types.get(name) or "revolute"))
                for name in joint_names
            ]
            points.append({
                "timeFromStartSec": seconds,
                "positions": native_positions,
                "positionsDeg": legacy_positions,
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
        if self._position_only_ik(request):
            try:
                planning_component.set_goal_state(
                    motion_plan_constraints=self._position_goal_constraints(target_pose, end_effector),
                )
            except TypeError:
                planning_component.set_goal_state(
                    pose_stamped_msg=target_pose,
                    pose_link=end_effector.get("link"),
                )
        else:
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
        joint_names = _joint_names(request)
        trajectory = self._serialize_trajectory(plan_result.trajectory, joint_names, request)
        final_joint_values: dict[str, float] = {}
        final_joint_values_legacy: dict[str, float] = {}
        if trajectory["points"]:
            final_joint_values = dict(zip(
                trajectory["jointNames"],
                trajectory["points"][-1]["positions"],
                strict=False,
            ))
            final_joint_values_legacy = dict(zip(
                trajectory["jointNames"],
                trajectory["points"][-1]["positionsDeg"],
                strict=False,
            ))
        return {
            "jointValuesByName": final_joint_values,
            "jointValuesByNameDeg": final_joint_values_legacy,
            "trajectory": trajectory,
            "positionOnly": self._position_only_ik(request),
            "residual": {"position": 0.0},
        }

from __future__ import annotations

from math import isfinite
import posixpath
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from moveit2_server.protocol import MotionProtocolError, SUPPORTED_REQUEST_TYPES
from moveit2_server.srdf_source import SrdfSource, read_srdf_source


DEFAULT_CAD_DIRECTORY = ""
DEFAULT_IK_TIMEOUT = 0.05
DEFAULT_IK_ATTEMPTS = 1
DEFAULT_POSITION_TOLERANCE = 0.002
DEFAULT_PLANNING_PIPELINE = "ompl"
DEFAULT_PLANNER_ID = "RRTConnectkConfigDefault"
DEFAULT_PLANNING_TIME = 1.0


def _plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def _path_is_inside(child_path: Path, parent_path: Path) -> bool:
    try:
        child_path.resolve().relative_to(parent_path.resolve())
        return True
    except ValueError:
        return False


def _file_version(file_path: Path) -> str:
    try:
        stats = file_path.stat()
    except FileNotFoundError:
        return ""
    if not stats.st_mode:
        return ""
    return f"{stats.st_size:x}-{stats.st_mtime_ns:x}"


def _combined_version(paths: list[Path]) -> str:
    return "|".join(f"{path.name}:{_file_version(path)}" for path in paths)


def _normalize_relative_path(value: Any, *, label: str, suffix: str | None = None) -> str:
    raw_value = str(value or "").strip().replace("\\", "/").lstrip("/")
    normalized = posixpath.normpath(raw_value)
    if not raw_value or normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise MotionProtocolError(f"{label} must stay inside the repository: {raw_value or '(missing)'}")
    if suffix and not normalized.lower().endswith(suffix):
        raise MotionProtocolError(f"{label} must end in {suffix}: {normalized}")
    return normalized


def normalize_cad_directory(value: Any = DEFAULT_CAD_DIRECTORY) -> str:
    if value is None:
        value = DEFAULT_CAD_DIRECTORY
    raw_value = str(value).strip()
    if not raw_value:
        return ""
    return _normalize_relative_path(raw_value, label="dir")


def normalize_file_ref(value: Any) -> str:
    return _normalize_relative_path(value, label="file", suffix=".srdf")


def _file_ref_relative_to_cad_dir(file_ref: str, *, cad_dir: str, cad_root: Path) -> str:
    if not cad_dir:
        return file_ref
    prefix = f"{cad_dir.rstrip('/')}/"
    if not file_ref.startswith(prefix):
        return file_ref
    scan_relative_ref = file_ref[len(prefix):]
    if scan_relative_ref and not (cad_root / file_ref).is_file() and (cad_root / scan_relative_ref).is_file():
        return scan_relative_ref
    return file_ref


def _resolve_srdf_urdf_path(srdf_source: SrdfSource, *, srdf_path: Path, repo_root: Path) -> Path:
    # An SRDF pairs with the same-directory URDF whose root <robot name>
    # matches; the directory sits inside the repository by construction.
    del repo_root
    robot_name = str(srdf_source.robot_name or "").strip()
    matches = [
        candidate
        for candidate in sorted(srdf_path.parent.glob("*.urdf"))
        if _urdf_root_name(candidate) == robot_name
    ]
    if not matches:
        raise MotionProtocolError(
            f"no .urdf in {srdf_path.parent} declares robot name {robot_name!r}; "
            "an SRDF pairs with the same-folder URDF whose robot name matches"
        )
    if len(matches) > 1:
        raise MotionProtocolError(
            f"multiple .urdf files in {srdf_path.parent} declare robot name {robot_name!r}: "
            f"{[str(match) for match in matches]!r}"
        )
    return matches[0]


def _urdf_root_name(urdf_path: Path) -> str | None:
    try:
        for _event, element in ET.iterparse(str(urdf_path), events=("start",)):
            if element.tag != "robot":
                return None
            return str(element.attrib.get("name") or "").strip()
    except (OSError, ET.ParseError):
        return None
    return None


def _urdf_robot(urdf_path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(urdf_path).getroot()
    except FileNotFoundError as exc:
        raise MotionProtocolError(f"URDF file does not exist: {urdf_path}") from exc
    except ET.ParseError as exc:
        raise MotionProtocolError(f"URDF file is invalid XML: {urdf_path}") from exc
    if root.tag != "robot":
        raise MotionProtocolError("URDF root must be <robot>")
    links = {
        str(link.get("name") or "").strip()
        for link in root.findall("link")
        if str(link.get("name") or "").strip()
    }
    joints: dict[str, dict[str, str]] = {}
    for joint in root.findall("joint"):
        name = str(joint.get("name") or "").strip()
        if not name:
            continue
        parent_element = joint.find("parent")
        child_element = joint.find("child")
        joint_type = str(joint.get("type") or "").strip()
        limit_element = joint.find("limit")
        lower = _optional_finite_float(limit_element.get("lower") if limit_element is not None else None)
        upper = _optional_finite_float(limit_element.get("upper") if limit_element is not None else None)
        joints[name] = {
            "type": joint_type,
            "parent": str(parent_element.get("link") if parent_element is not None else "").strip(),
            "child": str(child_element.get("link") if child_element is not None else "").strip(),
            "lower": lower if joint_type in {"revolute", "prismatic"} else None,
            "upper": upper if joint_type in {"revolute", "prismatic"} else None,
            "mimic": joint.find("mimic") is not None,
        }
    return {
        "name": str(root.get("name") or "").strip(),
        "links": links,
        "joints": joints,
    }


def _optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _active_joint_names(robot: dict[str, Any]) -> list[str]:
    joints = robot.get("joints")
    if not isinstance(joints, dict):
        return []
    return [
        str(name)
        for name, joint in joints.items()
        if isinstance(joint, dict) and str(joint.get("type") or "").strip() != "fixed" and not bool(joint.get("mimic"))
    ]


def _all_joint_names_for_chain(robot: dict[str, Any], *, base_link: str, tip_link: str) -> list[str]:
    if not base_link or not tip_link:
        return []
    if base_link == tip_link:
        return []
    joints = robot.get("joints")
    if not isinstance(joints, dict):
        return []
    by_parent: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for raw_name, raw_joint in joints.items():
        if not isinstance(raw_joint, dict):
            continue
        parent = str(raw_joint.get("parent") or "").strip()
        child = str(raw_joint.get("child") or "").strip()
        if parent and child:
            by_parent.setdefault(parent, []).append((str(raw_name), raw_joint))

    stack: list[tuple[str, list[tuple[str, dict[str, Any]]]]] = [(base_link, [])]
    visited: set[str] = set()
    while stack:
        link_name, path = stack.pop()
        if link_name == tip_link:
            return [joint_name for joint_name, _joint in path]
        if link_name in visited:
            continue
        visited.add(link_name)
        for joint_name, joint in reversed(by_parent.get(link_name, [])):
            child = str(joint.get("child") or "").strip()
            if child:
                stack.append((child, [*path, (joint_name, joint)]))
    return []


def _joint_names_for_chain(robot: dict[str, Any], *, base_link: str, tip_link: str) -> list[str]:
    joints = robot.get("joints")
    if not isinstance(joints, dict):
        return []
    names: list[str] = []
    for joint_name in _all_joint_names_for_chain(robot, base_link=base_link, tip_link=tip_link):
        joint = joints.get(joint_name)
        if isinstance(joint, dict) and str(joint.get("type") or "").strip() != "fixed" and not bool(joint.get("mimic")):
            names.append(joint_name)
    return names


def _append_unique(target: list[str], values: list[str]) -> None:
    seen = set(target)
    for value in values:
        if value not in seen:
            target.append(value)
            seen.add(value)


def _joint_names_for_group(
    group: dict[str, Any],
    *,
    robot: dict[str, Any],
    groups_by_name: dict[str, dict[str, Any]],
    visited: set[str] | None = None,
) -> list[str]:
    explicit_joint_names = list(group.get("jointNames") or [])
    if explicit_joint_names:
        joints = robot.get("joints")
        if not isinstance(joints, dict):
            return []
        return [
            str(name)
            for name in explicit_joint_names
            if isinstance(joints.get(str(name)), dict)
            and str(joints[str(name)].get("type") or "").strip() != "fixed"
            and not bool(joints[str(name)].get("mimic"))
        ]

    names: list[str] = []
    for chain in group.get("chains") or []:
        if not isinstance(chain, dict):
            continue
        _append_unique(
            names,
            _joint_names_for_chain(
                robot,
                base_link=str(chain.get("baseLink") or "").strip(),
                tip_link=str(chain.get("tipLink") or "").strip(),
            ),
        )

    if visited is None:
        visited = set()
    group_name = str(group.get("name") or "").strip()
    if group_name:
        visited.add(group_name)
    for subgroup_name in group.get("subgroups") or []:
        subgroup_key = str(subgroup_name or "").strip()
        if not subgroup_key or subgroup_key in visited:
            continue
        subgroup = groups_by_name.get(subgroup_key)
        if subgroup is not None:
            _append_unique(
                names,
                _joint_names_for_group(
                    subgroup,
                    robot=robot,
                    groups_by_name=groups_by_name,
                    visited=visited,
                ),
            )

    return names


def _positive_float(value: Any, *, label: str, default: float) -> float:
    if value is None:
        value = default
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise MotionProtocolError(f"{label} must be positive") from exc
    if numeric <= 0:
        raise MotionProtocolError(f"{label} must be positive")
    return numeric


def _positive_int(value: Any, *, label: str, default: int) -> int:
    if value is None:
        value = default
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise MotionProtocolError(f"{label} must be a positive integer") from exc
    if numeric <= 0:
        raise MotionProtocolError(f"{label} must be a positive integer")
    return numeric


def _scaling(value: Any, *, label: str, default: float) -> float:
    if value is None:
        value = default
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise MotionProtocolError(f"{label} must be between 0 and 1") from exc
    if numeric <= 0 or numeric > 1:
        raise MotionProtocolError(f"{label} must be between 0 and 1")
    return numeric


def _boolean(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _string(value: Any, *, label: str, default: str = "") -> str:
    normalized = str(value if value is not None else default).strip()
    if not normalized:
        raise MotionProtocolError(f"{label} is required")
    return normalized


def _optional_object(value: Any, *, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not _plain_object(value):
        raise MotionProtocolError(f"{label} must be an object")
    return value


def _validate_srdf_inventory(metadata: dict[str, Any], *, robot: dict[str, Any]) -> dict[str, Any]:
    if str(metadata.get("robotName") or "").strip() != str(robot.get("name") or "").strip():
        raise MotionProtocolError("SRDF robotName must match the paired URDF robot name")

    link_names = robot.get("links")
    joint_payload = robot.get("joints")
    if not isinstance(link_names, set) or not isinstance(joint_payload, dict):
        raise MotionProtocolError("URDF robot inventory is invalid")
    joint_names = set(joint_payload)

    groups = _validate_planning_groups(metadata.get("planningGroups"), link_names=link_names, joint_names=joint_names)
    group_by_name = {group["name"]: group for group in groups}
    end_effectors = _validate_end_effectors(
        metadata.get("endEffectors"),
        link_names=link_names,
        groups=group_by_name,
        robot=robot,
    )
    group_states = _validate_group_states(metadata.get("groupStates"), groups=group_by_name, robot=robot)
    disabled_pairs = _validate_disabled_pairs(metadata.get("disabledCollisionPairs"), link_names=link_names)
    return {
        **metadata,
        "planningGroups": groups,
        "endEffectors": end_effectors,
        "groupStates": group_states,
        "disabledCollisionPairs": disabled_pairs,
    }


def _group_tip_link(group: Any) -> str:
    if isinstance(group, dict):
        link_names = group.get("linkNames")
        if isinstance(link_names, list) and link_names:
            return str(link_names[-1])
        chains = group.get("chains")
        if isinstance(chains, list) and chains:
            chain = chains[-1]
            if isinstance(chain, dict):
                return str(chain.get("tipLink") or "")
        return ""
    link_names = getattr(group, "link_names", ())
    if link_names:
        return str(link_names[-1])
    chains = getattr(group, "chains", ())
    if chains:
        return str(getattr(chains[-1], "tip_link", "") or "")
    return ""


def _end_effector_link(end_effector: Any, groups_by_name: dict[str, Any]) -> str:
    group_name = str(getattr(end_effector, "group", "") or "")
    group = groups_by_name.get(group_name)
    if group is not None:
        group_tip = _group_tip_link(group)
        if group_tip:
            return group_tip
    return ""


def _srdf_inventory_from_source(srdf_source: SrdfSource, *, srdf_path: Path, urdf_path: Path) -> dict[str, Any]:
    groups_by_name = {group.name: group for group in srdf_source.planning_groups}
    return {
        "urdf": str(urdf_path),
        "srdf": str(srdf_path),
        "robotName": srdf_source.robot_name,
        "planningGroups": [
            {
                "name": group.name,
                "jointNames": list(group.joint_names),
                "linkNames": list(group.link_names),
                "chains": [
                    {"baseLink": chain.base_link, "tipLink": chain.tip_link}
                    for chain in group.chains
                ],
                "subgroups": list(group.subgroups),
            }
            for group in srdf_source.planning_groups
        ],
        "endEffectors": [
            {
                "name": end_effector.name,
                "link": _end_effector_link(end_effector, groups_by_name) or end_effector.parent_link,
                "parentLink": end_effector.parent_link,
                "group": end_effector.group,
                "parentGroup": end_effector.parent_group,
            }
            for end_effector in srdf_source.end_effectors
        ],
        "groupStates": [
            {
                "name": group_state.name,
                "group": group_state.group,
                "jointValuesByName": group_state.joint_values_by_name,
            }
            for group_state in srdf_source.group_states
        ],
        "disabledCollisionPairs": [
            {
                "link1": pair.link1,
                "link2": pair.link2,
                "reason": pair.reason,
                "source": pair.source,
            }
            for pair in srdf_source.disabled_collision_pairs
        ],
    }


def _validate_planning_groups(value: Any, *, link_names: set[str], joint_names: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise MotionProtocolError("SRDF planningGroups must be a non-empty array")
    groups: list[dict[str, Any]] = []
    seen = set()
    for raw_group in value:
        if not _plain_object(raw_group):
            raise MotionProtocolError("SRDF planning group must be an object")
        name = _string(raw_group.get("name"), label="SRDF planning group name")
        if name in seen:
            raise MotionProtocolError(f"Duplicate SRDF planning group {name}")
        seen.add(name)
        group_joint_names = _validate_names(raw_group.get("jointNames"), allowed=joint_names, label=f"SRDF planning group {name} jointNames")
        group_link_names = _validate_names(raw_group.get("linkNames"), allowed=link_names, label=f"SRDF planning group {name} linkNames")
        chains = raw_group.get("chains") if isinstance(raw_group.get("chains"), list) else []
        normalized_chains: list[dict[str, str]] = []
        for raw_chain in chains:
            if not _plain_object(raw_chain):
                raise MotionProtocolError(f"SRDF planning group {name} chains must contain objects")
            base_link = _string(raw_chain.get("baseLink"), label=f"SRDF planning group {name} chain baseLink")
            tip_link = _string(raw_chain.get("tipLink"), label=f"SRDF planning group {name} chain tipLink")
            if base_link not in link_names or tip_link not in link_names:
                raise MotionProtocolError(f"SRDF planning group {name} chain references missing URDF link")
            normalized_chains.append({"baseLink": base_link, "tipLink": tip_link})
        subgroups = [str(group).strip() for group in raw_group.get("subgroups", []) if str(group).strip()]
        groups.append({
            "name": name,
            "jointNames": group_joint_names,
            "linkNames": group_link_names,
            "chains": normalized_chains,
            "subgroups": subgroups,
        })
    group_names = {group["name"] for group in groups}
    for group in groups:
        for subgroup in group["subgroups"]:
            if subgroup not in group_names:
                raise MotionProtocolError(f"SRDF planning group {group['name']} references missing subgroup {subgroup}")
    return groups


def _validate_names(value: Any, *, allowed: set[str], label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MotionProtocolError(f"{label} must be an array")
    names: list[str] = []
    seen = set()
    for raw_name in value:
        name = str(raw_name or "").strip()
        if not name:
            raise MotionProtocolError(f"{label} cannot include empty names")
        if name in seen:
            raise MotionProtocolError(f"{label} includes duplicate {name}")
        if name not in allowed:
            raise MotionProtocolError(f"{label} references missing name {name}")
        seen.add(name)
        names.append(name)
    return names


def _link_names_for_group(
    group: dict[str, Any],
    *,
    robot: dict[str, Any],
    groups_by_name: dict[str, dict[str, Any]],
    visited: set[str] | None = None,
) -> set[str]:
    links = set(str(link) for link in group.get("linkNames", []) if str(link))
    joints = robot.get("joints")
    if not isinstance(joints, dict):
        return links

    def add_joint_links(joint_name: str) -> None:
        joint = joints.get(joint_name)
        if not isinstance(joint, dict):
            return
        child = str(joint.get("child") or "").strip()
        if child:
            links.add(child)

    for joint_name in group.get("jointNames", []):
        add_joint_links(str(joint_name))
    for chain in group.get("chains", []):
        if not isinstance(chain, dict):
            continue
        base_link = str(chain.get("baseLink") or "").strip()
        tip_link = str(chain.get("tipLink") or "").strip()
        if tip_link:
            links.add(tip_link)
        for joint_name in _all_joint_names_for_chain(robot, base_link=base_link, tip_link=tip_link):
            add_joint_links(joint_name)

    if visited is None:
        visited = set()
    group_name = str(group.get("name") or "").strip()
    if group_name:
        visited.add(group_name)
    for subgroup_name in group.get("subgroups", []):
        subgroup_key = str(subgroup_name or "").strip()
        if not subgroup_key or subgroup_key in visited:
            continue
        subgroup = groups_by_name.get(subgroup_key)
        if subgroup is not None:
            links.update(_link_names_for_group(subgroup, robot=robot, groups_by_name=groups_by_name, visited=visited))
    links.discard("")
    return links


def _joint_adjacent_to_any_link(robot: dict[str, Any], parent_link: str, child_links: set[str]) -> bool:
    joints = robot.get("joints")
    if not isinstance(joints, dict):
        return False
    for joint in joints.values():
        if not isinstance(joint, dict):
            continue
        parent = str(joint.get("parent") or "").strip()
        child = str(joint.get("child") or "").strip()
        if (parent == parent_link and child in child_links) or (child == parent_link and parent in child_links):
            return True
    return False


def _validate_end_effectors(
    value: Any,
    *,
    link_names: set[str],
    groups: dict[str, dict[str, Any]],
    robot: dict[str, Any],
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MotionProtocolError("SRDF endEffectors must be an array")
    end_effectors: list[dict[str, Any]] = []
    seen = set()
    for raw_end_effector in value:
        if not _plain_object(raw_end_effector):
            raise MotionProtocolError("SRDF end effector must be an object")
        name = _string(raw_end_effector.get("name"), label="SRDF end effector name")
        if name in seen:
            raise MotionProtocolError(f"Duplicate SRDF end effector {name}")
        seen.add(name)
        parent_link = _string(raw_end_effector.get("parentLink"), label=f"SRDF end effector {name} parentLink")
        if parent_link not in link_names:
            raise MotionProtocolError(f"SRDF end effector {name} references missing parentLink {parent_link}")
        group_name = _string(raw_end_effector.get("group"), label=f"SRDF end effector {name} group")
        if group_name not in groups:
            raise MotionProtocolError(f"SRDF end effector {name} references missing group {group_name}")
        parent_group = str(raw_end_effector.get("parentGroup") or "").strip()
        if parent_group and parent_group not in groups:
            raise MotionProtocolError(f"SRDF end effector {name} references missing parentGroup {parent_group}")
        link = str(raw_end_effector.get("link") or _group_tip_link(groups[group_name]) or parent_link).strip()
        if link not in link_names:
            raise MotionProtocolError(f"SRDF end effector {name} references missing link {link}")
        end_effector_links = _link_names_for_group(groups[group_name], robot=robot, groups_by_name=groups)
        if parent_group:
            parent_group_links = _link_names_for_group(groups[parent_group], robot=robot, groups_by_name=groups)
            overlap = sorted(end_effector_links & parent_group_links)
            if overlap:
                raise MotionProtocolError(f"SRDF end effector {name} group shares link(s) with parentGroup: {overlap}")
            if parent_link not in parent_group_links:
                raise MotionProtocolError(
                    f"SRDF end effector {name} parentLink {parent_link} is not in parentGroup {parent_group}"
                )
        if end_effector_links and parent_link not in end_effector_links and not _joint_adjacent_to_any_link(
            robot,
            parent_link,
            end_effector_links,
        ):
            raise MotionProtocolError(f"SRDF end effector {name} parentLink is not adjacent to its group")
        end_effectors.append({
            "name": name,
            "link": link,
            "parentLink": parent_link,
            "group": group_name,
            "parentGroup": parent_group,
        })
    return end_effectors


def _validate_group_state_joint_value(state_name: str, joint_name: str, value: float, joint: dict[str, Any]) -> None:
    joint_type = str(joint.get("type") or "").strip()
    if joint_type == "fixed":
        raise MotionProtocolError(f"SRDF group state {state_name} cannot set fixed joint {joint_name}")
    if bool(joint.get("mimic")):
        raise MotionProtocolError(f"SRDF group state {state_name} cannot set mimic joint {joint_name}")
    if joint_type == "continuous":
        return
    lower = joint.get("lower")
    upper = joint.get("upper")
    if isinstance(lower, float) and value < lower:
        raise MotionProtocolError(f"SRDF group state {state_name} joint {joint_name} is below its URDF lower limit")
    if isinstance(upper, float) and value > upper:
        raise MotionProtocolError(f"SRDF group state {state_name} joint {joint_name} is above its URDF upper limit")


def _validate_group_states(value: Any, *, groups: dict[str, dict[str, Any]], robot: dict[str, Any]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MotionProtocolError("SRDF groupStates must be an array")
    states: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    joint_payload = robot.get("joints")
    if not isinstance(joint_payload, dict):
        raise MotionProtocolError("URDF robot inventory is invalid")
    for raw_state in value:
        if not _plain_object(raw_state):
            raise MotionProtocolError("SRDF group state must be an object")
        name = _string(raw_state.get("name"), label="SRDF group state name")
        group = _string(raw_state.get("group"), label=f"SRDF group state {name} group")
        state_key = f"{group}/{name}"
        if state_key in seen_keys:
            raise MotionProtocolError(f"Duplicate SRDF group state {state_key}")
        seen_keys.add(state_key)
        if group not in groups:
            raise MotionProtocolError(f"SRDF group state {name} references missing group {group}")
        group_joint_names = set(_joint_names_for_group(groups[group], robot=robot, groups_by_name=groups))
        joint_values = raw_state.get("jointValuesByName")
        legacy_joint_values = raw_state.get("jointValuesByNameRad")
        if joint_values is None and legacy_joint_values is not None:
            joint_values = legacy_joint_values
        if not _plain_object(joint_values):
            raise MotionProtocolError(f"SRDF group state {name} jointValuesByName must be an object")
        parsed_values: dict[str, float] = {}
        for raw_joint_name, raw_value in joint_values.items():
            joint_name = str(raw_joint_name or "").strip()
            joint = joint_payload.get(joint_name)
            if not isinstance(joint, dict):
                raise MotionProtocolError(f"SRDF group state {name} references missing joint {joint_name}")
            if joint_name not in group_joint_names:
                raise MotionProtocolError(f"SRDF group state {name} joint {joint_name} is not in group {group}")
            try:
                parsed_value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise MotionProtocolError(f"SRDF group state {name} joint {joint_name} must be numeric") from exc
            if not isfinite(parsed_value):
                raise MotionProtocolError(f"SRDF group state {name} joint {joint_name} must be finite")
            _validate_group_state_joint_value(name, joint_name, parsed_value, joint)
            parsed_values[joint_name] = parsed_value
        states.append({"name": name, "group": group, "jointValuesByName": parsed_values, "jointValuesByNameRad": parsed_values})
    return states


def _validate_disabled_pairs(value: Any, *, link_names: set[str]) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MotionProtocolError("SRDF disabledCollisionPairs must be an array")
    pairs: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_pair in value:
        if not _plain_object(raw_pair):
            raise MotionProtocolError("SRDF disabled collision pair must be an object")
        link1 = _string(raw_pair.get("link1"), label="SRDF disabled collision link1")
        link2 = _string(raw_pair.get("link2"), label="SRDF disabled collision link2")
        if link1 == link2:
            raise MotionProtocolError("SRDF disabled collision pair cannot repeat the same link")
        if link1 not in link_names or link2 not in link_names:
            raise MotionProtocolError("SRDF disabled collision pair references missing URDF link")
        pair_key = "/".join(sorted((link1, link2)))
        if pair_key in seen:
            raise MotionProtocolError(f"Duplicate SRDF disabled collision pair {pair_key}")
        seen.add(pair_key)
        reason = str(raw_pair.get("reason") or "").strip()
        if not reason:
            raise MotionProtocolError(f"SRDF disabled collision pair {pair_key} requires a reason")
        pairs.append({
            "link1": link1,
            "link2": link2,
            "reason": reason,
            "source": str(raw_pair.get("source") or "manual").strip(),
        })
    return pairs


def _moveit_settings(payload: Any) -> dict[str, Any]:
    if not _plain_object(payload):
        return {}
    return _optional_object(payload.get("moveit2"), label="moveit2")


def _target_payload(payload: Any) -> dict[str, Any]:
    if not _plain_object(payload):
        return {}
    return _optional_object(payload.get("target"), label="target")


def _find_group(metadata: dict[str, Any], name: str) -> dict[str, Any]:
    for group in metadata.get("planningGroups", []):
        if str(group.get("name") or "") == name:
            return group
    raise MotionProtocolError(f"Selected planning group {name} is not defined by the SRDF")


def _find_end_effector(metadata: dict[str, Any], name: str) -> dict[str, Any]:
    for end_effector in metadata.get("endEffectors", []):
        if str(end_effector.get("name") or "") == name:
            return end_effector
    raise MotionProtocolError(f"Selected end effector {name} is not defined by the SRDF")


def _default_end_effector(metadata: dict[str, Any], planning_group_name: str) -> dict[str, Any] | None:
    end_effectors = list(metadata.get("endEffectors", []))
    for end_effector in end_effectors:
        if str(end_effector.get("parentGroup") or "") == planning_group_name:
            return end_effector
    return end_effectors[0] if end_effectors else None


def _build_command(
    *,
    command_name: str,
    payload: Any,
    metadata: dict[str, Any],
    robot: dict[str, Any],
) -> dict[str, Any]:
    moveit2 = _moveit_settings(payload)
    target = _target_payload(payload)
    default_group = metadata["planningGroups"][0]
    planning_group_name = _string(
        moveit2.get("planningGroup"),
        label="moveit2.planningGroup",
        default=str(default_group.get("name") or ""),
    )
    planning_group = _find_group(metadata, planning_group_name)

    default_end_effector = _default_end_effector(metadata, planning_group_name)
    selected_end_effector_name = str(moveit2.get("endEffector") or target.get("endEffector") or "").strip()
    selected_end_effector = _find_end_effector(metadata, selected_end_effector_name) if selected_end_effector_name else default_end_effector
    if selected_end_effector is None:
        raise MotionProtocolError("SRDF must define an end effector for MoveIt2 pose requests")

    robot_links = robot.get("links")
    if not isinstance(robot_links, set):
        raise MotionProtocolError("URDF robot inventory is invalid")
    target_frame = _string(
        moveit2.get("targetFrame") or target.get("frame"),
        label="moveit2.targetFrame",
        default=next(iter(sorted(robot_links)), ""),
    )
    if target_frame not in robot_links:
        raise MotionProtocolError(f"moveit2.targetFrame references missing URDF link {target_frame}")

    ik = _optional_object(moveit2.get("ik"), label="moveit2.ik")
    planning = _optional_object(moveit2.get("planning"), label="moveit2.planning")
    target_has_orientation = "quat_xyzw" in target or "rpy" in target
    position_only_ik = _boolean(ik.get("positionOnly"), default=not target_has_orientation)
    if not target_has_orientation and not position_only_ik:
        raise MotionProtocolError("target orientation is required when moveit2.ik.positionOnly is false")
    groups_by_name = {
        str(group.get("name") or ""): group
        for group in metadata.get("planningGroups", [])
        if isinstance(group, dict) and str(group.get("name") or "")
    }
    joint_names = _joint_names_for_group(planning_group, robot=robot, groups_by_name=groups_by_name)
    target_link = _string(
        moveit2.get("targetLink") or target.get("targetLink") or target.get("link"),
        label="moveit2.targetLink",
        default=str(selected_end_effector.get("link") or ""),
    )
    if target_link not in robot_links:
        raise MotionProtocolError(f"moveit2.targetLink references missing URDF link {target_link}")
    command = {
        "planningGroup": planning_group_name,
        "jointNames": joint_names,
        "endEffectors": [
            {
                "name": selected_end_effector["name"],
                "link": target_link,
                "inferredLink": selected_end_effector["link"],
                "frame": target_frame,
                "planningGroup": planning_group_name,
                "jointNames": joint_names,
                "positionTolerance": _positive_float(
                    ik.get("tolerance", moveit2.get("positionTolerance")),
                    label="moveit2.ik.tolerance",
                    default=DEFAULT_POSITION_TOLERANCE,
                ),
            }
        ],
        "ik": {
            "timeout": _positive_float(ik.get("timeout"), label="moveit2.ik.timeout", default=DEFAULT_IK_TIMEOUT),
            "attempts": _positive_int(ik.get("attempts"), label="moveit2.ik.attempts", default=DEFAULT_IK_ATTEMPTS),
            "positionOnly": position_only_ik,
            "tolerance": _positive_float(
                ik.get("tolerance", moveit2.get("positionTolerance")),
                label="moveit2.ik.tolerance",
                default=DEFAULT_POSITION_TOLERANCE,
            ),
        },
        "planner": {
            "pipeline": _string(planning.get("pipeline"), label="moveit2.planning.pipeline", default=DEFAULT_PLANNING_PIPELINE),
            "plannerId": _string(planning.get("plannerId"), label="moveit2.planning.plannerId", default=DEFAULT_PLANNER_ID),
            "planningTime": _positive_float(planning.get("planningTime"), label="moveit2.planning.planningTime", default=DEFAULT_PLANNING_TIME),
            "maxVelocityScalingFactor": _scaling(
                planning.get("maxVelocityScalingFactor"),
                label="moveit2.planning.maxVelocityScalingFactor",
                default=1.0,
            ),
            "maxAccelerationScalingFactor": _scaling(
                planning.get("maxAccelerationScalingFactor"),
                label="moveit2.planning.maxAccelerationScalingFactor",
                default=1.0,
            ),
        },
    }
    if command_name not in SUPPORTED_REQUEST_TYPES:
        raise MotionProtocolError(f"Unsupported request type {command_name}")
    return command


def build_moveit2_context(
    *,
    repo_root: str | Path,
    dir: Any = DEFAULT_CAD_DIRECTORY,
    file: Any,
    type: Any,
    payload: Any = None,
) -> dict[str, Any]:
    command_name = str(type or "").strip()
    if command_name not in SUPPORTED_REQUEST_TYPES:
        raise MotionProtocolError(f"Unsupported request type {command_name or '(missing)'}")
    resolved_repo_root = Path(repo_root).resolve()
    cad_dir = normalize_cad_directory(dir)
    file_ref = normalize_file_ref(file)
    cad_root = (resolved_repo_root / cad_dir).resolve()
    if not _path_is_inside(cad_root, resolved_repo_root):
        raise MotionProtocolError(f"dir must stay inside the repository: {cad_dir}")
    file_ref = _file_ref_relative_to_cad_dir(file_ref, cad_dir=cad_dir, cad_root=cad_root)
    srdf_path = (cad_root / file_ref).resolve()
    if not _path_is_inside(srdf_path, cad_root):
        root_label = cad_dir or "the repository"
        raise MotionProtocolError(f"file must stay inside {root_label}: {file_ref}")
    if not srdf_path.is_file():
        raise MotionProtocolError(f"SRDF file does not exist: {file_ref}")

    try:
        srdf_source = read_srdf_source(srdf_path)
    except Exception as exc:
        raise MotionProtocolError(str(exc)) from exc
    urdf_path = _resolve_srdf_urdf_path(srdf_source, srdf_path=srdf_path, repo_root=resolved_repo_root)
    robot = _urdf_robot(urdf_path)
    inventory_payload = _srdf_inventory_from_source(srdf_source, srdf_path=srdf_path, urdf_path=urdf_path)
    srdf_inventory = _validate_srdf_inventory(inventory_payload, robot=robot)
    command = _build_command(command_name=command_name, payload=payload, metadata=srdf_inventory, robot=robot)
    version_paths = [urdf_path, srdf_path]
    return {
        "repoRoot": str(resolved_repo_root),
        "dir": cad_dir,
        "file": file_ref,
        "urdfPath": str(urdf_path),
        "srdfPath": str(srdf_path),
        "modelAssetHash": _combined_version(version_paths),
        "commandName": command_name,
        "command": command,
        "srdf": srdf_inventory,
    }

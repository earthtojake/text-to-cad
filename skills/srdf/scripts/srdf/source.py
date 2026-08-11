from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal
import xml.etree.ElementTree as ET

from srdf.findings import ValidationResult, format_findings

SRDF_SUFFIX = ".srdf"

VIRTUAL_JOINT_TYPES = {"fixed", "floating", "planar"}
# MoveIt2 SRDF elements; unknown siblings are typo suspects.
KNOWN_ROBOT_CHILDREN = {
    "group",
    "group_state",
    "end_effector",
    "virtual_joint",
    "passive_joint",
    "disable_collisions",
    "enable_collisions",
    "disable_default_collisions",
    "link_sphere_approximation",
    "joint_property",
}
KNOWN_GROUP_CHILDREN = {"joint", "link", "chain", "group"}
_UNKNOWN_ELEMENT_HINT = "Unknown elements are silently ignored by MoveIt; check for typos."


class SrdfSourceError(ValueError):
    pass


@dataclass(frozen=True)
class SrdfChain:
    base_link: str
    tip_link: str


@dataclass(frozen=True)
class SrdfPlanningGroup:
    name: str
    joint_names: tuple[str, ...]
    link_names: tuple[str, ...]
    chains: tuple[SrdfChain, ...]
    subgroups: tuple[str, ...]


@dataclass(frozen=True)
class SrdfVirtualJoint:
    name: str
    joint_type: str
    parent_frame: str
    child_link: str


@dataclass(frozen=True)
class SrdfEndEffector:
    name: str
    parent_link: str
    group: str
    parent_group: str


@dataclass(frozen=True)
class SrdfGroupState:
    name: str
    group: str
    joint_values_by_name: dict[str, float]


@dataclass(frozen=True)
class SrdfDisabledCollisionPair:
    link1: str
    link2: str
    reason: str
    source: Literal["adjacent", "sampled", "manual", "setup_assistant", "assumed"] = "manual"


@dataclass(frozen=True)
class SrdfSource:
    file_ref: str
    source_path: Path
    robot_name: str
    planning_groups: tuple[SrdfPlanningGroup, ...]
    end_effectors: tuple[SrdfEndEffector, ...]
    group_states: tuple[SrdfGroupState, ...]
    disabled_collision_pairs: tuple[SrdfDisabledCollisionPair, ...]
    virtual_joints: tuple[SrdfVirtualJoint, ...] = ()
    passive_joints: tuple[str, ...] = ()


def file_ref_from_srdf_path(srdf_path: Path) -> str:
    resolved = srdf_path.resolve()
    if resolved.suffix.lower() != SRDF_SUFFIX:
        raise SrdfSourceError(f"{resolved} is not an SRDF source file")
    return _relative_to_repo(resolved)


def read_srdf_source(srdf_path: Path) -> SrdfSource:
    """Compatibility wrapper: raise on the first structural validation error."""
    source, result = parse_srdf_file(srdf_path)
    if result.errors:
        raise SrdfSourceError(format_findings(result.errors))
    assert source is not None
    return source


def parse_srdf_xml(xml_text: str, *, source_path: Path) -> SrdfSource:
    source, result = parse_srdf_text(xml_text, source_path=source_path)
    if result.errors:
        raise SrdfSourceError(format_findings(result.errors))
    assert source is not None
    return source


def parse_srdf_file(srdf_path: Path) -> tuple[SrdfSource | None, ValidationResult]:
    result = ValidationResult()
    resolved_path = srdf_path.resolve()
    if resolved_path.suffix.lower() != SRDF_SUFFIX:
        result.add("error", "invalid_target", f"{resolved_path} is not an SRDF source file", path="/")
        return None, result
    try:
        xml_text = resolved_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.add("error", "unreadable_file", f"{_relative_to_repo(resolved_path)} could not be read: {exc}", path="/")
        return None, result
    return parse_srdf_text(xml_text, source_path=resolved_path)


def parse_srdf_text(xml_text: str, *, source_path: Path) -> tuple[SrdfSource | None, ValidationResult]:
    result = ValidationResult()
    resolved_path = source_path.resolve()
    display = _relative_to_repo(resolved_path)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        result.add("error", "invalid_xml", f"{display} could not be parsed as SRDF XML: {exc}", path="/")
        return None, result
    return _parse_srdf_root(root, source_path=resolved_path, result=result)


def _parse_srdf_root(
    root: ET.Element,
    *,
    source_path: Path,
    result: ValidationResult,
) -> tuple[SrdfSource | None, ValidationResult]:
    display = _relative_to_repo(source_path)
    if root.tag != "robot":
        result.add("error", "invalid_root", f"{display} root element must be <robot>", path="/")
        return None, result
    robot_name = str(root.attrib.get("name") or "").strip()
    if not robot_name:
        result.add("error", "missing_robot_name", f"{display} robot name is required", path="/robot")

    _warn_unknown_children(root, result)

    planning_groups: list[SrdfPlanningGroup] = []
    group_names: list[str] = []
    for group_element in root.findall("group"):
        name = str(group_element.attrib.get("name") or "").strip()
        group_path = f"/robot/group[@name='{name}']" if name else "/robot/group"
        if not name:
            result.add("error", "missing_group_name", f"{display} group name is required", path=group_path)
            continue
        group_names.append(name)
        for child in list(group_element):
            if (
                isinstance(child.tag, str)
                and "}" not in child.tag
                and ":" not in child.tag
                and child.tag not in KNOWN_GROUP_CHILDREN
            ):
                result.add(
                    "warning",
                    "unknown_element",
                    f"unknown element <{child.tag}> under {group_path}",
                    path=f"{group_path}/{child.tag}",
                    hint=_UNKNOWN_ELEMENT_HINT,
                )
        planning_groups.append(
            SrdfPlanningGroup(
                name=name,
                joint_names=_child_names(group_element, "joint"),
                link_names=_child_names(group_element, "link"),
                chains=tuple(
                    SrdfChain(
                        base_link=str(chain.attrib.get("base_link") or "").strip(),
                        tip_link=str(chain.attrib.get("tip_link") or "").strip(),
                    )
                    for chain in group_element.findall("chain")
                ),
                subgroups=_child_names(group_element, "group"),
            )
        )
    _report_duplicates(group_names, result, display, label="group")

    virtual_joints: list[SrdfVirtualJoint] = []
    virtual_joint_names: list[str] = []
    for element in root.findall("virtual_joint"):
        name = str(element.attrib.get("name") or "").strip()
        vj_path = f"/robot/virtual_joint[@name='{name}']" if name else "/robot/virtual_joint"
        if not name:
            result.add("error", "missing_virtual_joint_name", f"{display} virtual_joint name is required", path=vj_path)
            continue
        virtual_joint_names.append(name)
        joint_type = str(element.attrib.get("type") or "").strip().lower()
        if joint_type not in VIRTUAL_JOINT_TYPES:
            result.add(
                "error",
                "invalid_virtual_joint_type",
                f"{display} virtual_joint {name!r} type must be one of: " + ", ".join(sorted(VIRTUAL_JOINT_TYPES)),
                path=vj_path,
            )
        parent_frame = str(element.attrib.get("parent_frame") or "").strip()
        child_link = str(element.attrib.get("child_link") or "").strip()
        if not parent_frame:
            result.add(
                "error",
                "missing_parent_frame",
                f"{display} virtual_joint {name!r} requires parent_frame",
                path=vj_path,
            )
        if not child_link:
            result.add(
                "error",
                "missing_child_link",
                f"{display} virtual_joint {name!r} requires child_link",
                path=vj_path,
            )
        virtual_joints.append(
            SrdfVirtualJoint(name=name, joint_type=joint_type, parent_frame=parent_frame, child_link=child_link)
        )
    _report_duplicates(virtual_joint_names, result, display, label="virtual_joint")

    passive_joints: list[str] = []
    for element in root.findall("passive_joint"):
        name = str(element.attrib.get("name") or "").strip()
        if not name:
            result.add(
                "error",
                "missing_passive_joint_name",
                f"{display} passive_joint name is required",
                path="/robot/passive_joint",
            )
            continue
        passive_joints.append(name)
    _report_duplicates(passive_joints, result, display, label="passive_joint")

    end_effectors: list[SrdfEndEffector] = []
    end_effector_names: list[str] = []
    for element in root.findall("end_effector"):
        name = str(element.attrib.get("name") or "").strip()
        if not name:
            result.add(
                "error",
                "missing_end_effector_name",
                f"{display} end_effector name is required",
                path="/robot/end_effector",
            )
            continue
        end_effector_names.append(name)
        end_effectors.append(
            SrdfEndEffector(
                name=name,
                parent_link=str(element.attrib.get("parent_link") or "").strip(),
                group=str(element.attrib.get("group") or "").strip(),
                parent_group=str(element.attrib.get("parent_group") or "").strip(),
            )
        )
    _report_duplicates(end_effector_names, result, display, label="end_effector")

    group_states: list[SrdfGroupState] = []
    group_state_keys: list[str] = []
    for element in root.findall("group_state"):
        name = str(element.attrib.get("name") or "").strip()
        group = str(element.attrib.get("group") or "").strip()
        state_path = f"/robot/group_state[@name='{name}']" if name else "/robot/group_state"
        if not name or not group:
            result.add(
                "error",
                "missing_group_state_identity",
                f"{display} group_state requires name and group",
                path=state_path,
            )
            continue
        group_state_keys.append(f"{group}/{name}")
        joint_values: dict[str, float] = {}
        joint_names: list[str] = []
        for joint_element in element.findall("joint"):
            joint_name = str(joint_element.attrib.get("name") or "").strip()
            if not joint_name:
                result.add(
                    "error",
                    "missing_group_state_joint_name",
                    f"{display} group_state joint name is required",
                    path=state_path,
                )
                continue
            joint_names.append(joint_name)
            try:
                joint_value = float(joint_element.attrib.get("value"))
            except (TypeError, ValueError):
                result.add(
                    "error",
                    "invalid_group_state_value",
                    f"{display} group_state {name!r} joint {joint_name!r} value must be numeric",
                    path=state_path,
                )
                continue
            if not isfinite(joint_value):
                result.add(
                    "error",
                    "nonfinite_group_state_value",
                    f"{display} group_state {name!r} joint {joint_name!r} value must be finite",
                    path=state_path,
                )
                continue
            joint_values[joint_name] = joint_value
        _report_duplicates(joint_names, result, display, label=f"group_state {name!r} joint")
        group_states.append(SrdfGroupState(name=name, group=group, joint_values_by_name=joint_values))
    _report_duplicates(group_state_keys, result, display, label="group_state")

    disabled_pairs: list[SrdfDisabledCollisionPair] = []
    pair_keys: list[str] = []
    for element in root.findall("disable_collisions"):
        link1 = str(element.attrib.get("link1") or "").strip()
        link2 = str(element.attrib.get("link2") or "").strip()
        pair_path = "/robot/disable_collisions"
        if not link1 or not link2:
            result.add(
                "error",
                "missing_collision_pair_links",
                f"{display} disable_collisions requires link1 and link2",
                path=pair_path,
            )
            continue
        if link1 == link2:
            result.add(
                "error",
                "self_collision_pair",
                f"{display} disable_collisions cannot repeat the same link",
                path=pair_path,
            )
            continue
        reason = str(element.attrib.get("reason") or "").strip()
        if not reason:
            result.add(
                "error",
                "missing_collision_pair_reason",
                f"{display} disable_collisions for {link1!r}/{link2!r} requires a reason",
                path=pair_path,
            )
            continue
        pair_key = "/".join(sorted((link1, link2)))
        pair_keys.append(pair_key)
        disabled_pairs.append(
            SrdfDisabledCollisionPair(
                link1=link1,
                link2=link2,
                reason=reason,
                source=_disabled_collision_source(reason),
            )
        )
    _report_duplicates(pair_keys, result, display, label="disable_collisions")

    if result.errors:
        return None, result

    source = SrdfSource(
        file_ref=_relative_to_repo(source_path),
        source_path=source_path.resolve(),
        robot_name=robot_name,
        planning_groups=tuple(planning_groups),
        end_effectors=tuple(end_effectors),
        group_states=tuple(group_states),
        disabled_collision_pairs=tuple(disabled_pairs),
        virtual_joints=tuple(virtual_joints),
        passive_joints=tuple(passive_joints),
    )
    return source, result


def _warn_unknown_children(root: ET.Element, result: ValidationResult) -> None:
    for child in list(root):
        if not isinstance(child.tag, str):
            continue
        tag = child.tag
        if "}" in tag or ":" in tag:
            # The retired tcad:/explorer: urdf link element deserves a specific
            # nudge; other namespaced extensions pass through.
            if _local_name(tag) == "urdf":
                result.add(
                    "warning",
                    "deprecated_urdf_link",
                    "the <tcad:urdf>/<explorer:urdf> metadata element is no longer used and is ignored",
                    path="/robot",
                    hint="SRDF pairs with the same-folder URDF whose robot name matches; remove the element.",
                )
            continue
        if tag not in KNOWN_ROBOT_CHILDREN:
            result.add(
                "warning",
                "unknown_element",
                f"unknown element <{tag}> under /robot",
                path=f"/robot/{tag}",
                hint=_UNKNOWN_ELEMENT_HINT,
            )


def _local_name(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1].split(":", 1)[-1]


def _child_names(element: ET.Element, tag: str) -> tuple[str, ...]:
    names: list[str] = []
    for child in element.findall(tag):
        name = str(child.attrib.get("name") or "").strip()
        if name:
            names.append(name)
    return tuple(names)


def _report_duplicates(names: list[str], result: ValidationResult, display: str, *, label: str) -> None:
    seen = set()
    duplicates = []
    for name in names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        result.add(
            "error",
            "duplicate_name",
            f"{display} has duplicate {label} name(s): {sorted(set(duplicates))!r}",
            path="/robot",
        )


def _disabled_collision_source(
    reason: str,
) -> Literal["adjacent", "sampled", "manual", "setup_assistant", "assumed"]:
    normalized = str(reason or "").strip().lower()
    if "adjacent" in normalized:
        return "adjacent"
    if any(token in normalized for token in ("never", "always", "sample", "default")):
        return "sampled"
    if "setup" in normalized or "assistant" in normalized:
        return "setup_assistant"
    if "assum" in normalized:
        return "assumed"
    return "manual"


def _relative_to_repo(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal
import xml.etree.ElementTree as ET


SRDF_SUFFIX = ".srdf"


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


def read_srdf_source(srdf_path: Path) -> SrdfSource:
    resolved_path = srdf_path.resolve()
    if resolved_path.suffix.lower() != SRDF_SUFFIX:
        raise SrdfSourceError(f"{resolved_path} is not an SRDF source file")
    try:
        root = ET.fromstring(resolved_path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise SrdfSourceError(f"{_relative_to_repo(resolved_path)} could not be parsed as SRDF XML") from exc
    return parse_srdf_root(root, source_path=resolved_path)


def parse_srdf_root(root: ET.Element, *, source_path: Path) -> SrdfSource:
    if root.tag != "robot":
        raise SrdfSourceError(f"{_relative_to_repo(source_path)} root element must be <robot>")
    robot_name = str(root.attrib.get("name") or "").strip()
    if not robot_name:
        raise SrdfSourceError(f"{_relative_to_repo(source_path)} robot name is required")

    planning_groups: list[SrdfPlanningGroup] = []
    group_names: list[str] = []
    for group_element in root.findall("group"):
        name = str(group_element.attrib.get("name") or "").strip()
        if not name:
            raise SrdfSourceError(f"{_relative_to_repo(source_path)} group name is required")
        group_names.append(name)
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
    _raise_on_duplicates(group_names, source_path=source_path, label="group")

    end_effectors: list[SrdfEndEffector] = []
    end_effector_names: list[str] = []
    for element in root.findall("end_effector"):
        name = str(element.attrib.get("name") or "").strip()
        if not name:
            raise SrdfSourceError(f"{_relative_to_repo(source_path)} end_effector name is required")
        end_effector_names.append(name)
        end_effectors.append(
            SrdfEndEffector(
                name=name,
                parent_link=str(element.attrib.get("parent_link") or "").strip(),
                group=str(element.attrib.get("group") or "").strip(),
                parent_group=str(element.attrib.get("parent_group") or "").strip(),
            )
        )
    _raise_on_duplicates(end_effector_names, source_path=source_path, label="end_effector")

    group_states: list[SrdfGroupState] = []
    group_state_keys: list[str] = []
    for element in root.findall("group_state"):
        name = str(element.attrib.get("name") or "").strip()
        group = str(element.attrib.get("group") or "").strip()
        if not name or not group:
            raise SrdfSourceError(f"{_relative_to_repo(source_path)} group_state requires name and group")
        group_state_keys.append(f"{group}/{name}")
        joint_values: dict[str, float] = {}
        joint_names: list[str] = []
        for joint_element in element.findall("joint"):
            joint_name = str(joint_element.attrib.get("name") or "").strip()
            if not joint_name:
                raise SrdfSourceError(f"{_relative_to_repo(source_path)} group_state joint name is required")
            joint_names.append(joint_name)
            try:
                joint_value = float(joint_element.attrib.get("value"))
            except (TypeError, ValueError) as exc:
                raise SrdfSourceError(
                    f"{_relative_to_repo(source_path)} group_state {name!r} joint {joint_name!r} value must be numeric"
                ) from exc
            if not isfinite(joint_value):
                raise SrdfSourceError(
                    f"{_relative_to_repo(source_path)} group_state {name!r} joint {joint_name!r} value must be finite"
                )
            joint_values[joint_name] = joint_value
        _raise_on_duplicates(joint_names, source_path=source_path, label=f"group_state {name!r} joint")
        group_states.append(SrdfGroupState(name=name, group=group, joint_values_by_name=joint_values))
    _raise_on_duplicates(group_state_keys, source_path=source_path, label="group_state")

    disabled_pairs: list[SrdfDisabledCollisionPair] = []
    pair_keys: list[str] = []
    for element in root.findall("disable_collisions"):
        link1 = str(element.attrib.get("link1") or "").strip()
        link2 = str(element.attrib.get("link2") or "").strip()
        if not link1 or not link2:
            raise SrdfSourceError(f"{_relative_to_repo(source_path)} disable_collisions requires link1 and link2")
        if link1 == link2:
            raise SrdfSourceError(f"{_relative_to_repo(source_path)} disable_collisions cannot repeat the same link")
        reason = str(element.attrib.get("reason") or "").strip()
        if not reason:
            raise SrdfSourceError(
                f"{_relative_to_repo(source_path)} disable_collisions for {link1!r}/{link2!r} requires a reason"
            )
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
    _raise_on_duplicates(pair_keys, source_path=source_path, label="disable_collisions")

    return SrdfSource(
        file_ref=_relative_to_repo(source_path.resolve()),
        source_path=source_path.resolve(),
        robot_name=robot_name,
        planning_groups=tuple(planning_groups),
        end_effectors=tuple(end_effectors),
        group_states=tuple(group_states),
        disabled_collision_pairs=tuple(disabled_pairs),
    )




def _child_names(element: ET.Element, tag: str) -> tuple[str, ...]:
    names: list[str] = []
    for child in element.findall(tag):
        name = str(child.attrib.get("name") or "").strip()
        if name:
            names.append(name)
    return tuple(names)


def _raise_on_duplicates(names: list[str], *, source_path: Path, label: str) -> None:
    seen = set()
    duplicates = []
    for name in names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise SrdfSourceError(
            f"{_relative_to_repo(source_path)} has duplicate {label} name(s): {sorted(set(duplicates))!r}"
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

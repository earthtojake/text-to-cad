from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from math import isfinite
from pathlib import Path
import xml.etree.ElementTree as ET

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR))

from srdf.findings import ValidationResult
from srdf.source import SrdfPlanningGroup, SrdfSource, parse_srdf_file

SRDF_SUFFIX = ".srdf"
URDF_SUFFIX = ".urdf"
MANUAL_PAIR_WARNING_THRESHOLD = 25


def validate_srdf_targets(
    targets: Sequence[str],
    *,
    strict: bool = False,
    output_format: str = "text",
) -> int:
    target_paths = [_resolve_target_path(target) for target in targets]
    reports: list[dict[str, object]] = []
    failed = False
    for target_path in target_paths:
        report = _validate_target(target_path, strict=strict, output_format=output_format)
        reports.append(report)
        if not report["ok"]:
            failed = True
    if output_format == "json":
        print(json.dumps({"files": reports}, indent=2))
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/validate",
        description="Validate explicit MoveIt2 SRDF targets against their paired URDF.",
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="Explicit .srdf file to validate.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation warnings as failures.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output format: human-readable text (default) or a JSON findings document.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Narrate each target and its timing on stderr.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.verbose:
        # Narration goes to stderr; the findings document on stdout stays exactly the same
        # so `--verbose` never changes what a caller parses.
        for target in args.targets:
            print(f"[srdf] validating {target}", file=sys.stderr)
    return validate_srdf_targets(args.targets, strict=args.strict, output_format=args.output_format)


def _resolve_target_path(raw_target: object) -> Path:
    value = str(raw_target or "").strip()
    if not value:
        raise ValueError("srdf target must be a non-empty path")
    target_path = Path(value).expanduser()
    return target_path.resolve() if target_path.is_absolute() else (Path.cwd() / target_path).resolve()


def _validate_target(target_path: Path, *, strict: bool, output_format: str) -> dict[str, object]:
    display = _display_path(target_path)
    text_mode = output_format == "text"
    if target_path.suffix.lower() != SRDF_SUFFIX:
        return _report_precheck_failure(display, "target must be a .srdf file", text_mode)
    if not target_path.is_file():
        return _report_precheck_failure(display, "file not found", text_mode)

    srdf_source, result = parse_srdf_file(target_path)
    urdf_path: Path | None = None
    if srdf_source is not None:
        urdf_path = _resolve_paired_urdf(srdf_source.robot_name, srdf_dir=target_path.parent, result=result)
        if urdf_path is not None:
            urdf_robot = _read_urdf_robot(urdf_path, result)
            if urdf_robot is not None:
                _validate_srdf_against_urdf(srdf_source, urdf_robot=urdf_robot, result=result)

    result = result.deduplicated()
    ok = _report_findings(display, result, strict=strict, text_mode=text_mode)
    summary = ""
    if srdf_source is not None and urdf_path is not None:
        summary = _summary_line(display, srdf_source, urdf_path)
    if text_mode and ok and summary:
        print(summary)
    return {
        "path": display,
        "ok": ok,
        "summary": summary,
        "findings": [finding.to_dict() for finding in result.all_findings()],
    }


def _report_precheck_failure(display: str, message: str, text_mode: bool) -> dict[str, object]:
    if text_mode:
        print(f"FAIL {display}: {message}", file=sys.stderr)
    return {
        "path": display,
        "ok": False,
        "summary": "",
        "findings": [{"severity": "error", "code": "invalid_target", "message": message}],
    }


def _report_findings(display: str, result: ValidationResult, *, strict: bool, text_mode: bool) -> bool:
    if text_mode:
        for finding in result.all_findings():
            print(finding.format(), file=sys.stderr)
    blocking = len(result.errors) + (len(result.warnings) if strict else 0)
    if blocking:
        if text_mode:
            print(f"FAIL {display}: {blocking} blocking finding(s)", file=sys.stderr)
        return False
    return True


def _summary_line(display: str, srdf_source: SrdfSource, urdf_path: Path) -> str:
    return (
        f"OK {display}: robot {srdf_source.robot_name!r}, urdf {_display_path(urdf_path)}, "
        f"{len(srdf_source.planning_groups)} groups, {len(srdf_source.end_effectors)} end effectors, "
        f"{len(srdf_source.group_states)} group states, "
        f"{len(srdf_source.disabled_collision_pairs)} disabled collision pairs, "
        f"{len(srdf_source.virtual_joints)} virtual joints"
    )


def find_paired_urdf(robot_name: str, srdf_dir: Path) -> tuple[Path | None, list[Path]]:
    """Resolve the URDF paired with an SRDF: the same-directory URDF whose
    root <robot name> matches. Returns (paired path or None, all matches)."""
    matches: list[Path] = []
    for candidate in sorted(srdf_dir.glob("*" + URDF_SUFFIX)):
        if _urdf_root_name(candidate) == robot_name:
            matches.append(candidate)
    return (matches[0] if len(matches) == 1 else None), matches


def _urdf_root_name(urdf_path: Path) -> str | None:
    try:
        for _event, element in ET.iterparse(str(urdf_path), events=("start",)):
            if element.tag != "robot":
                return None
            return str(element.attrib.get("name") or "").strip()
    except (OSError, ET.ParseError):
        return None
    return None


def _resolve_paired_urdf(robot_name: str, *, srdf_dir: Path, result: ValidationResult) -> Path | None:
    if not robot_name:
        return None
    urdf_path, matches = find_paired_urdf(robot_name, srdf_dir)
    if urdf_path is not None:
        return urdf_path
    if not matches:
        result.add(
            "error",
            "no_paired_urdf",
            f"no .urdf in {_display_path(srdf_dir)} declares robot name {robot_name!r}",
            path="/robot",
            hint="An SRDF pairs with the same-folder URDF whose <robot name> matches; "
            "colocate the URDF and make the names identical.",
        )
        return None
    result.add(
        "error",
        "ambiguous_paired_urdf",
        f"multiple .urdf files in {_display_path(srdf_dir)} declare robot name {robot_name!r}: "
        f"{[_display_path(match) for match in matches]!r}",
        path="/robot",
        hint="Exactly one URDF per robot name per folder; rename or move the extras.",
    )
    return None


def _read_urdf_robot(urdf_path: Path, result: ValidationResult) -> dict[str, object] | None:
    try:
        root = ET.parse(urdf_path).getroot()
    except (OSError, ET.ParseError):
        result.add("error", "invalid_paired_urdf", f"URDF is invalid XML: {_display_path(urdf_path)}", path="/robot")
        return None
    if root.tag != "robot":
        result.add("error", "invalid_paired_urdf", "URDF root must be <robot>", path="/robot")
        return None
    robot_name = str(root.get("name") or "").strip()
    if not robot_name:
        result.add("error", "invalid_paired_urdf", "URDF robot name is required", path="/robot")
        return None
    links = {
        str(link.get("name") or "").strip()
        for link in root.findall("link")
        if str(link.get("name") or "").strip()
    }
    joints: dict[str, dict[str, object]] = {}
    child_links: list[str] = []
    for joint in root.findall("joint"):
        name = str(joint.get("name") or "").strip()
        if not name:
            continue
        parent_element = joint.find("parent")
        child_element = joint.find("child")
        joint_type = str(joint.get("type") or "").strip()
        lower: float | None = None
        upper: float | None = None
        limit_element = joint.find("limit")
        if limit_element is not None and joint_type in {"revolute", "prismatic"}:
            lower = _optional_finite_float(limit_element.get("lower"))
            upper = _optional_finite_float(limit_element.get("upper"))
        child_link = str(child_element.get("link") if child_element is not None else "").strip()
        child_links.append(child_link)
        joints[name] = {
            "type": joint_type,
            "parent": str(parent_element.get("link") if parent_element is not None else "").strip(),
            "child": child_link,
            "lower": lower,
            "upper": upper,
            "mimic": joint.find("mimic") is not None,
        }
    # Chain-path and adjacency checks assume a well-formed tree; surface it if not.
    roots = [link for link in links if link not in set(child_links)]
    if len(roots) != 1 or len(set(child_links)) != len([c for c in child_links if c]):
        result.add(
            "warning",
            "paired_urdf_not_a_tree",
            f"paired URDF {_display_path(urdf_path)} is not a single-rooted tree; "
            "chain and adjacency checks may be unreliable",
            path="/robot",
            hint="Validate the URDF with the URDF skill validator first.",
        )
    return {"name": robot_name, "links": links, "joints": joints}


def _validate_srdf_against_urdf(
    srdf_source: SrdfSource,
    *,
    urdf_robot: dict[str, object],
    result: ValidationResult,
) -> None:
    links = urdf_robot["links"]
    joints = urdf_robot["joints"]
    assert isinstance(links, set)
    assert isinstance(joints, dict)
    group_names = {group.name for group in srdf_source.planning_groups}
    groups_by_name: dict[str, SrdfPlanningGroup] = {group.name: group for group in srdf_source.planning_groups}
    if not group_names:
        result.add("error", "no_planning_groups", "SRDF must define at least one planning group", path="/robot")

    for group in srdf_source.planning_groups:
        group_path = f"/robot/group[@name='{group.name}']"
        if not group.joint_names and not group.link_names and not group.chains and not group.subgroups:
            result.add(
                "error",
                "empty_group",
                f"SRDF planning group {group.name!r} must define joints, links, chains, or subgroups",
                path=group_path,
            )
        _check_names_exist(group.joint_names, set(joints), result, label=f"planning group {group.name!r} joint", path=group_path)
        _check_names_exist(group.link_names, links, result, label=f"planning group {group.name!r} link", path=group_path)
        _check_names_exist(group.subgroups, group_names, result, label=f"planning group {group.name!r} subgroup", path=group_path)
        for chain in group.chains:
            chain_ok = True
            if chain.base_link not in links:
                result.add(
                    "error",
                    "missing_chain_link",
                    f"planning group {group.name!r} chain references missing base_link {chain.base_link!r}",
                    path=f"{group_path}/chain",
                )
                chain_ok = False
            if chain.tip_link not in links:
                result.add(
                    "error",
                    "missing_chain_link",
                    f"planning group {group.name!r} chain references missing tip_link {chain.tip_link!r}",
                    path=f"{group_path}/chain",
                )
                chain_ok = False
            if chain_ok and not _joint_path_for_chain(urdf_robot, base_link=chain.base_link, tip_link=chain.tip_link):
                result.add(
                    "error",
                    "chain_not_a_path",
                    f"planning group {group.name!r} chain {chain.base_link!r} -> {chain.tip_link!r} "
                    "is not a parent-to-child path in the URDF tree",
                    path=f"{group_path}/chain",
                )
    _check_subgroup_cycles(groups_by_name, result)

    for virtual_joint in srdf_source.virtual_joints:
        vj_path = f"/robot/virtual_joint[@name='{virtual_joint.name}']"
        if virtual_joint.child_link and virtual_joint.child_link not in links:
            result.add(
                "error",
                "missing_virtual_joint_child",
                f"virtual_joint {virtual_joint.name!r} references missing child_link {virtual_joint.child_link!r}",
                path=vj_path,
            )
        if virtual_joint.name in joints:
            result.add(
                "warning",
                "virtual_joint_name_collision",
                f"virtual_joint {virtual_joint.name!r} shares a name with a URDF joint",
                path=vj_path,
            )

    passive_joint_set = set(srdf_source.passive_joints)
    for passive_joint in srdf_source.passive_joints:
        if passive_joint not in joints:
            result.add(
                "error",
                "missing_passive_joint",
                f"passive_joint references missing URDF joint {passive_joint!r}",
                path="/robot/passive_joint",
            )

    for end_effector in srdf_source.end_effectors:
        ee_path = f"/robot/end_effector[@name='{end_effector.name}']"
        if end_effector.parent_link not in links:
            result.add(
                "error",
                "missing_end_effector_parent_link",
                f"end_effector {end_effector.name!r} references missing parent_link {end_effector.parent_link!r}",
                path=ee_path,
            )
        if end_effector.group not in group_names:
            result.add(
                "error",
                "missing_end_effector_group",
                f"end_effector {end_effector.name!r} references missing group {end_effector.group!r}",
                path=ee_path,
            )
        if end_effector.parent_group and end_effector.parent_group not in group_names:
            result.add(
                "error",
                "missing_end_effector_parent_group",
                f"end_effector {end_effector.name!r} references missing parent_group {end_effector.parent_group!r}",
                path=ee_path,
            )
        _validate_end_effector_topology(
            end_effector,
            groups_by_name=groups_by_name,
            urdf_robot=urdf_robot,
            result=result,
            path=ee_path,
        )

    for group_state in srdf_source.group_states:
        state_path = f"/robot/group_state[@name='{group_state.name}']"
        if group_state.group not in group_names:
            result.add(
                "error",
                "missing_group_state_group",
                f"group_state {group_state.name!r} references missing group {group_state.group!r}",
                path=state_path,
            )
            continue
        group_joint_names = _joint_names_for_group(
            groups_by_name[group_state.group],
            urdf_robot=urdf_robot,
            groups_by_name=groups_by_name,
        )
        group_joint_set = set(group_joint_names)
        for joint_name, value in group_state.joint_values_by_name.items():
            if joint_name not in joints:
                result.add(
                    "error",
                    "missing_group_state_joint",
                    f"group_state {group_state.name!r} joint references missing name {joint_name!r}",
                    path=state_path,
                )
                continue
            if joint_name in passive_joint_set:
                result.add(
                    "error",
                    "group_state_sets_passive_joint",
                    f"group_state {group_state.name!r} cannot set passive joint {joint_name!r}",
                    path=state_path,
                )
                continue
            # Fixed/mimic joints are never planning variables; report that
            # specifically before the (derived) group-membership check.
            if not _validate_group_state_joint_kind(group_state.name, joint_name, joints[joint_name], result, state_path):
                continue
            if joint_name not in group_joint_set:
                result.add(
                    "error",
                    "group_state_joint_not_in_group",
                    f"group_state {group_state.name!r} joint {joint_name!r} is not in group {group_state.group!r}",
                    path=state_path,
                )
                continue
            _validate_group_state_joint_value(group_state.name, joint_name, value, joints[joint_name], result, state_path)
        missing_joints = [name for name in group_joint_names if name not in group_state.joint_values_by_name]
        if missing_joints and group_state.joint_values_by_name:
            result.add(
                "warning",
                "incomplete_group_state",
                f"group_state {group_state.name!r} omits group joint(s): {missing_joints!r}",
                path=state_path,
                hint="MoveIt fills omitted joints from the current state, which is rarely intended for a named pose.",
            )

    manual_count = 0
    for pair in srdf_source.disabled_collision_pairs:
        pair_path = "/robot/disable_collisions"
        _check_names_exist((pair.link1, pair.link2), links, result, label="disable_collisions link", path=pair_path)
        if pair.source == "manual":
            manual_count += 1
        if pair.source == "adjacent" and pair.link1 in links and pair.link2 in links:
            if not _links_are_adjacent(urdf_robot, pair.link1, pair.link2):
                result.add(
                    "warning",
                    "adjacent_reason_mismatch",
                    f"disable_collisions {pair.link1!r}/{pair.link2!r} claims reason {pair.reason!r} "
                    "but the links are not joined by any URDF joint",
                    path=pair_path,
                    hint="Use a truthful reason (Never/Default/Manual: ...) or fix the pair.",
                )
    if manual_count >= MANUAL_PAIR_WARNING_THRESHOLD:
        result.add(
            "warning",
            "many_manual_disabled_pairs",
            f"SRDF contains {manual_count} manually reasoned disabled collision pairs; "
            "prefer sampled/setup-assistant provenance.",
            path="/robot",
        )


def _check_subgroup_cycles(groups_by_name: dict[str, SrdfPlanningGroup], result: ValidationResult) -> None:
    visited: set[str] = set()

    def visit(name: str, stack: tuple[str, ...]) -> None:
        if name in stack:
            cycle = [*stack[stack.index(name):], name]
            result.add(
                "error",
                "subgroup_cycle",
                f"planning subgroups form a cycle: {' -> '.join(cycle)}",
                path=f"/robot/group[@name='{name}']",
            )
            return
        if name in visited:
            return
        visited.add(name)
        group = groups_by_name.get(name)
        if group is None:
            return
        for subgroup in group.subgroups:
            visit(subgroup, (*stack, name))

    for name in groups_by_name:
        visit(name, ())


def _links_are_adjacent(urdf_robot: dict[str, object], link1: str, link2: str) -> bool:
    joints = urdf_robot.get("joints")
    if not isinstance(joints, dict):
        return False
    for joint in joints.values():
        if not isinstance(joint, dict):
            continue
        parent = str(joint.get("parent") or "").strip()
        child = str(joint.get("child") or "").strip()
        if {parent, child} == {link1, link2}:
            return True
    return False


def _optional_finite_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _joint_path_for_chain(urdf_robot: dict[str, object], *, base_link: str, tip_link: str) -> list[str]:
    if not base_link or not tip_link or base_link == tip_link:
        return []
    joints = urdf_robot.get("joints")
    if not isinstance(joints, dict):
        return []
    by_parent: dict[str, list[tuple[str, dict[str, object]]]] = {}
    for joint_name, joint in joints.items():
        if not isinstance(joint, dict):
            continue
        parent = str(joint.get("parent") or "").strip()
        child = str(joint.get("child") or "").strip()
        if parent and child:
            by_parent.setdefault(parent, []).append((str(joint_name), joint))

    stack: list[tuple[str, list[str]]] = [(base_link, [])]
    visited: set[str] = set()
    while stack:
        link_name, path = stack.pop()
        if link_name == tip_link:
            return path
        if link_name in visited:
            continue
        visited.add(link_name)
        for joint_name, joint in reversed(by_parent.get(link_name, [])):
            child = str(joint.get("child") or "").strip()
            if child:
                stack.append((child, [*path, joint_name]))
    return []


def _joint_names_for_group(
    group: SrdfPlanningGroup,
    *,
    urdf_robot: dict[str, object],
    groups_by_name: dict[str, SrdfPlanningGroup],
    visited: set[str] | None = None,
) -> list[str]:
    names: list[str] = []
    joints = urdf_robot.get("joints")
    if not isinstance(joints, dict):
        return names

    for joint_name in group.joint_names:
        joint = joints.get(joint_name)
        if isinstance(joint, dict) and str(joint.get("type") or "") != "fixed" and not bool(joint.get("mimic")):
            _append_unique(names, [joint_name])

    for chain in group.chains:
        chain_joint_names = []
        for joint_name in _joint_path_for_chain(urdf_robot, base_link=chain.base_link, tip_link=chain.tip_link):
            joint = joints.get(joint_name)
            if isinstance(joint, dict) and str(joint.get("type") or "") != "fixed" and not bool(joint.get("mimic")):
                chain_joint_names.append(joint_name)
        _append_unique(names, chain_joint_names)

    if visited is None:
        visited = set()
    if group.name:
        visited.add(group.name)
    for subgroup_name in group.subgroups:
        subgroup_key = str(subgroup_name or "").strip()
        if not subgroup_key or subgroup_key in visited:
            continue
        subgroup = groups_by_name.get(subgroup_key)
        if subgroup is not None:
            _append_unique(
                names,
                _joint_names_for_group(subgroup, urdf_robot=urdf_robot, groups_by_name=groups_by_name, visited=visited),
            )
    return names


def _link_names_for_group(
    group: SrdfPlanningGroup,
    *,
    urdf_robot: dict[str, object],
    groups_by_name: dict[str, SrdfPlanningGroup],
    visited: set[str] | None = None,
) -> set[str]:
    links = set(group.link_names)
    joints = urdf_robot.get("joints")
    if not isinstance(joints, dict):
        return links

    def add_joint_links(joint_name: str) -> None:
        joint = joints.get(joint_name)
        if not isinstance(joint, dict):
            return
        child = str(joint.get("child") or "").strip()
        if child:
            links.add(child)

    for joint_name in group.joint_names:
        add_joint_links(str(joint_name))
    for chain in group.chains:
        links.add(chain.tip_link)
        for joint_name in _joint_path_for_chain(urdf_robot, base_link=chain.base_link, tip_link=chain.tip_link):
            add_joint_links(joint_name)

    if visited is None:
        visited = set()
    if group.name:
        visited.add(group.name)
    for subgroup_name in group.subgroups:
        subgroup_key = str(subgroup_name or "").strip()
        if not subgroup_key or subgroup_key in visited:
            continue
        subgroup = groups_by_name.get(subgroup_key)
        if subgroup is not None:
            links.update(
                _link_names_for_group(subgroup, urdf_robot=urdf_robot, groups_by_name=groups_by_name, visited=visited)
            )
    links.discard("")
    return links


def _joint_adjacent_to_any_link(urdf_robot: dict[str, object], parent_link: str, child_links: set[str]) -> bool:
    joints = urdf_robot.get("joints")
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


def _validate_end_effector_topology(
    end_effector: object,
    *,
    groups_by_name: dict[str, SrdfPlanningGroup],
    urdf_robot: dict[str, object],
    result: ValidationResult,
    path: str,
) -> None:
    group_name = str(getattr(end_effector, "group", "") or "")
    parent_group_name = str(getattr(end_effector, "parent_group", "") or "")
    parent_link = str(getattr(end_effector, "parent_link", "") or "")
    if not group_name or group_name not in groups_by_name:
        return

    end_effector_links = _link_names_for_group(
        groups_by_name[group_name],
        urdf_robot=urdf_robot,
        groups_by_name=groups_by_name,
    )
    if parent_group_name and parent_group_name in groups_by_name:
        parent_group_links = _link_names_for_group(
            groups_by_name[parent_group_name],
            urdf_robot=urdf_robot,
            groups_by_name=groups_by_name,
        )
        overlap = sorted(end_effector_links & parent_group_links)
        if overlap:
            result.add(
                "error",
                "end_effector_group_overlap",
                f"end_effector {getattr(end_effector, 'name', '')!r} group shares link(s) with parent_group: {overlap!r}",
                path=path,
            )
        if parent_link and parent_link not in parent_group_links:
            result.add(
                "error",
                "end_effector_parent_link_outside_parent_group",
                f"end_effector {getattr(end_effector, 'name', '')!r} parent_link {parent_link!r} "
                f"is not in parent_group {parent_group_name!r}",
                path=path,
            )
    if end_effector_links and parent_link not in end_effector_links and not _joint_adjacent_to_any_link(
        urdf_robot,
        parent_link,
        end_effector_links,
    ):
        result.add(
            "error",
            "end_effector_parent_link_not_adjacent",
            f"end_effector {getattr(end_effector, 'name', '')!r} parent_link {parent_link!r} is not adjacent to its group",
            path=path,
        )


def _validate_group_state_joint_kind(
    state_name: str,
    joint_name: str,
    joint: object,
    result: ValidationResult,
    state_path: str,
) -> bool:
    if not isinstance(joint, dict):
        return True
    if str(joint.get("type") or "").strip() == "fixed":
        result.add(
            "error",
            "group_state_sets_fixed_joint",
            f"group_state {state_name!r} cannot set fixed joint {joint_name!r}",
            path=state_path,
        )
        return False
    if bool(joint.get("mimic")):
        result.add(
            "error",
            "group_state_sets_mimic_joint",
            f"group_state {state_name!r} cannot set mimic joint {joint_name!r}",
            path=state_path,
        )
        return False
    return True


def _validate_group_state_joint_value(
    state_name: str,
    joint_name: str,
    value: float,
    joint: object,
    result: ValidationResult,
    state_path: str,
) -> None:
    if not isinstance(joint, dict):
        return
    joint_type = str(joint.get("type") or "").strip()
    if joint_type == "continuous":
        return
    lower = joint.get("lower")
    upper = joint.get("upper")
    if isinstance(lower, float) and value < lower:
        result.add(
            "error",
            "group_state_below_limit",
            f"group_state {state_name!r} joint {joint_name!r} is below its URDF lower limit",
            path=state_path,
        )
    if isinstance(upper, float) and value > upper:
        result.add(
            "error",
            "group_state_above_limit",
            f"group_state {state_name!r} joint {joint_name!r} is above its URDF upper limit",
            path=state_path,
        )


def _append_unique(target: list[str], values: list[str]) -> None:
    seen = set(target)
    for value in values:
        if value not in seen:
            target.append(value)
            seen.add(value)


def _check_names_exist(
    names: object,
    allowed: set[str],
    result: ValidationResult,
    *,
    label: str,
    path: str,
) -> None:
    for name in names:
        if name not in allowed:
            result.add(
                "error",
                "missing_name_reference",
                f"{label} references missing name {name!r}",
                path=path,
            )


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

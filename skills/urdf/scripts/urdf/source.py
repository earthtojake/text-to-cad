from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from urdf.findings import ValidationResult, format_findings

URDF_SUFFIX = ".urdf"
SUPPORTED_JOINT_TYPES = {"fixed", "continuous", "revolute", "prismatic"}
SUPPORTED_GEOMETRY_TAGS = {"box", "cylinder", "mesh", "sphere"}
KNOWN_MESH_SUFFIXES = {".stl", ".dae", ".obj", ".3mf", ".glb", ".gltf", ".ply"}

# Elements consumers commonly attach to URDF; unknown siblings are typo suspects.
KNOWN_ROBOT_CHILDREN = {"link", "joint", "material", "transmission", "gazebo", "ros2_control", "sensor"}
KNOWN_LINK_CHILDREN = {"inertial", "visual", "collision"}
KNOWN_JOINT_CHILDREN = {
    "origin", "parent", "child", "axis", "limit", "dynamics", "mimic", "calibration", "safety_controller",
}
KNOWN_VISUAL_CHILDREN = {"origin", "geometry", "material"}
KNOWN_COLLISION_CHILDREN = {"origin", "geometry"}
KNOWN_INERTIAL_CHILDREN = {"origin", "mass", "inertia"}

_UNKNOWN_ELEMENT_HINT = "Unknown elements are silently ignored by consumers; check for typos."
_INERTIA_KEYS = ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")
_AXIS_UNIT_TOLERANCE = 1e-3


class UrdfSourceError(ValueError):
    pass


class UrdfSourceWarning(UserWarning):
    pass


class MeshUriKind(Enum):
    LOCAL_RELATIVE = "local_relative"
    LOCAL_ABSOLUTE = "local_absolute"
    PACKAGE = "package"
    REMOTE = "remote"


@dataclass(frozen=True)
class MeshReference:
    uri: str
    kind: MeshUriKind
    path: Path | None = None
    package_name: str | None = None
    package_path: PurePosixPath | None = None


@dataclass(frozen=True)
class UrdfJoint:
    name: str
    joint_type: str
    parent_link: str
    child_link: str
    # Native URDF units: radians for revolute, meters for prismatic.
    # Fixed joints carry (0.0, 0.0); continuous joints carry (None, None).
    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class UrdfSource:
    file_ref: str
    source_path: Path
    robot_name: str
    root_link: str
    links: tuple[str, ...]
    joints: tuple[UrdfJoint, ...]
    mesh_paths: tuple[Path, ...]
    visual_mesh_paths: tuple[Path, ...] = ()
    collision_mesh_paths: tuple[Path, ...] = ()
    total_mass: float = 0.0


def file_ref_from_urdf_path(urdf_path: Path) -> str:
    resolved = urdf_path.resolve()
    if resolved.suffix.lower() != URDF_SUFFIX:
        raise UrdfSourceError(f"{resolved} is not a URDF source file")
    return _relative_to_repo(resolved)


def read_urdf_source(urdf_path: Path, *, package_map: dict[str, Path] | None = None) -> UrdfSource:
    """Compatibility wrapper: raise on the first validation error, warn on warnings."""
    source, result = validate_urdf_file(urdf_path, package_map=package_map)
    for finding in result.deduplicated().warnings:
        warnings.warn(finding.message, UrdfSourceWarning, stacklevel=2)
    if result.errors:
        raise UrdfSourceError(format_findings(result.errors))
    assert source is not None
    return source


def validate_urdf_file(
    urdf_path: Path,
    *,
    package_map: dict[str, Path] | None = None,
) -> tuple[UrdfSource | None, ValidationResult]:
    result = ValidationResult()
    resolved_path = urdf_path.resolve()
    if resolved_path.suffix.lower() != URDF_SUFFIX:
        result.add("error", "invalid_target", f"{resolved_path} is not a URDF source file", path="/")
        return None, result
    try:
        xml_text = resolved_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.add("error", "unreadable_file", f"{_relative_to_repo(resolved_path)} could not be read: {exc}", path="/")
        return None, result
    return validate_urdf_xml(xml_text, source_path=resolved_path, package_map=package_map)


def validate_urdf_xml(
    xml_text: str,
    *,
    source_path: Path,
    package_map: dict[str, Path] | None = None,
) -> tuple[UrdfSource | None, ValidationResult]:
    result = ValidationResult()
    resolved_path = source_path.resolve()
    display = _relative_to_repo(resolved_path)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        result.add(
            "error",
            "invalid_xml",
            f"{display} could not be parsed as URDF XML: {exc}",
            path="/",
        )
        return None, result

    if root.tag != "robot":
        result.add("error", "invalid_root", f"{display} root element must be <robot>", path="/")
        return None, result
    robot_name = str(root.attrib.get("name") or "").strip()
    if not robot_name:
        result.add("error", "missing_robot_name", f"{display} robot name is required", path="/robot")

    _warn_unknown_children(root, KNOWN_ROBOT_CHILDREN, result, "/robot")

    material_names = _collect_material_definitions(root)

    # --- links ---
    link_names: list[str] = []
    for link_element in root.findall("link"):
        name = str(link_element.attrib.get("name") or "").strip()
        if not name:
            result.add("error", "missing_link_name", f"{display} link name is required", path="/robot/link")
            continue
        link_names.append(name)
    if not link_names:
        result.add("error", "no_links", f"{display} must define at least one link", path="/robot")
    _report_duplicates(link_names, result, display, label="link", code="duplicate_link_name")
    link_name_set = set(link_names)

    total_mass = 0.0
    visual_mesh_paths: list[Path] = []
    collision_mesh_paths: list[Path] = []
    for link_element in root.findall("link"):
        link_name = str(link_element.attrib.get("name") or "").strip()
        link_path = f"/robot/link[@name='{link_name}']"
        _warn_unknown_children(link_element, KNOWN_LINK_CHILDREN, result, link_path)
        total_mass += _validate_link_inertials(link_element, result, display, link_path)
        visual_mesh_paths.extend(
            _validate_link_geometry(
                link_element,
                element_name="visual",
                result=result,
                display=display,
                link_path=link_path,
                source_path=resolved_path,
                package_map=package_map,
                material_names=material_names,
            )
        )
        collision_mesh_paths.extend(
            _validate_link_geometry(
                link_element,
                element_name="collision",
                result=result,
                display=display,
                link_path=link_path,
                source_path=resolved_path,
                package_map=package_map,
                material_names=material_names,
            )
        )

    # --- joints ---
    joints: list[UrdfJoint] = []
    joint_names: list[str] = []
    joint_types_by_name: dict[str, str] = {}
    mimic_targets_by_joint: dict[str, str] = {}
    parent_by_child: dict[str, str] = {}
    children: set[str] = set()
    joints_by_parent: dict[str, list[str]] = {}
    structural_error = bool(result.errors)

    for joint_element in root.findall("joint"):
        name = str(joint_element.attrib.get("name") or "").strip()
        joint_path = f"/robot/joint[@name='{name}']" if name else "/robot/joint"
        if not name:
            result.add("error", "missing_joint_name", f"{display} joint name is required", path=joint_path)
            structural_error = True
            continue
        joint_names.append(name)
        _warn_unknown_children(joint_element, KNOWN_JOINT_CHILDREN, result, joint_path)

        joint_type = str(joint_element.attrib.get("type") or "").strip().lower()
        if joint_type not in SUPPORTED_JOINT_TYPES:
            result.add(
                "error",
                "unsupported_joint_type",
                f"{display} joint {name!r} uses unsupported type {joint_type!r}",
                path=joint_path,
            )
        joint_types_by_name[name] = joint_type

        _validate_origin(
            joint_element.find("origin"),
            result,
            display,
            label=f"joint {name!r} origin",
            path=f"{joint_path}/origin",
        )
        _validate_joint_axis(joint_element, joint_type=joint_type, result=result, display=display, joint_path=joint_path)

        parent_element = joint_element.find("parent")
        child_element = joint_element.find("child")
        parent_link = str(parent_element.attrib.get("link") if parent_element is not None else "").strip()
        child_link = str(child_element.attrib.get("link") if child_element is not None else "").strip()
        if not parent_link or not child_link:
            result.add(
                "error",
                "missing_joint_parent_child",
                f"{display} joint {name!r} must define parent and child links",
                path=joint_path,
            )
            structural_error = True
        else:
            if parent_link not in link_name_set:
                result.add(
                    "error",
                    "missing_parent_link",
                    f"{display} joint {name!r} references missing parent link {parent_link!r}",
                    path=f"{joint_path}/parent",
                )
                structural_error = True
            if child_link not in link_name_set:
                result.add(
                    "error",
                    "missing_child_link",
                    f"{display} joint {name!r} references missing child link {child_link!r}",
                    path=f"{joint_path}/child",
                )
                structural_error = True
            if child_link in parent_by_child:
                result.add(
                    "error",
                    "multiple_parents",
                    f"{display} link {child_link!r} has multiple parents",
                    path=joint_path,
                )
                structural_error = True
            elif child_link in link_name_set:
                parent_by_child[child_link] = parent_link
                children.add(child_link)
                if parent_link in link_name_set:
                    joints_by_parent.setdefault(parent_link, []).append(child_link)

        lower, upper = _validate_joint_limits(joint_element, joint_type=joint_type, result=result, display=display, joint_path=joint_path)
        _validate_joint_dynamics(joint_element, result, display, joint_path)
        mimic_target = _validate_mimic(joint_element, result, display, joint_path, joint_name=name)
        if mimic_target:
            mimic_targets_by_joint[name] = mimic_target
        joints.append(
            UrdfJoint(
                name=name,
                joint_type=joint_type,
                parent_link=parent_link,
                child_link=child_link,
                lower=lower,
                upper=upper,
            )
        )

    _report_duplicates(joint_names, result, display, label="joint", code="duplicate_joint_name")
    if set(joint_names) & set(link_names):
        shared = sorted(set(joint_names) & set(link_names))
        result.add(
            "warning",
            "joint_link_name_collision",
            f"{display} joint and link names collide: {shared!r}",
            path="/robot",
            hint="Legal URDF, but URDF-to-SDF conversion creates a frame per joint and per link, which then collide.",
        )
    _validate_mimic_graph(mimic_targets_by_joint, joint_types_by_name, result, display)
    _warn_movable_links_without_inertial(root, joints, result, display)

    # --- tree checks (only meaningful when the structure above resolved) ---
    root_link = ""
    if link_names and not structural_error and not _has_duplicates(link_names) and not _has_duplicates(joint_names):
        root_candidates = [link_name for link_name in link_names if link_name not in children]
        if len(root_candidates) != 1:
            result.add(
                "error",
                "not_a_tree",
                f"{display} must form a single rooted tree; found roots {root_candidates!r}",
                path="/robot",
            )
        else:
            root_link = root_candidates[0]
            visited: set[str] = set()
            visiting: set[str] = set()
            cycle = False

            def visit(link_name: str) -> None:
                nonlocal cycle
                if link_name in visited or cycle:
                    return
                if link_name in visiting:
                    cycle = True
                    return
                visiting.add(link_name)
                for child_link in joints_by_parent.get(link_name, ()):
                    visit(child_link)
                visiting.discard(link_name)
                visited.add(link_name)

            visit(root_link)
            if cycle:
                result.add("error", "joint_graph_cycle", f"{display} joint graph contains a cycle", path="/robot")
            elif visited != link_name_set:
                missing_links = sorted(link_name_set - visited)
                result.add(
                    "error",
                    "disconnected_links",
                    f"{display} leaves links disconnected from the root: {missing_links!r}",
                    path="/robot",
                )
            if len(joints) != len(link_names) - 1:
                result.add(
                    "error",
                    "wrong_joint_count",
                    f"{display} must form a tree with exactly links-1 joints",
                    path="/robot",
                )

    if result.errors:
        return None, result

    source = UrdfSource(
        file_ref=_relative_to_repo(resolved_path),
        source_path=resolved_path,
        robot_name=robot_name,
        root_link=root_link,
        links=tuple(link_names),
        joints=tuple(joints),
        mesh_paths=tuple(visual_mesh_paths + collision_mesh_paths),
        visual_mesh_paths=tuple(visual_mesh_paths),
        collision_mesh_paths=tuple(collision_mesh_paths),
        total_mass=total_mass,
    )
    return source, result


# --- materials ---
def _collect_material_definitions(root: ET.Element) -> set[str]:
    names: set[str] = set()
    for material_element in root.iter("material"):
        name = str(material_element.attrib.get("name") or "").strip()
        has_definition = material_element.find("color") is not None or material_element.find("texture") is not None
        if name and has_definition:
            names.add(name)
    return names


# --- inertials ---
def _validate_link_inertials(
    link_element: ET.Element,
    result: ValidationResult,
    display: str,
    link_path: str,
) -> float:
    link_name = str(link_element.attrib.get("name") or "").strip()
    inertial_elements = link_element.findall("inertial")
    if len(inertial_elements) > 1:
        result.add(
            "error",
            "duplicate_inertial",
            f"{display} link {link_name!r} defines multiple <inertial> blocks",
            path=f"{link_path}/inertial",
        )
    if not inertial_elements:
        return 0.0
    inertial_element = inertial_elements[0]
    inertial_path = f"{link_path}/inertial"
    _warn_unknown_children(inertial_element, KNOWN_INERTIAL_CHILDREN, result, inertial_path)
    _validate_origin(
        inertial_element.find("origin"),
        result,
        display,
        label=f"link {link_name!r} inertial origin",
        path=f"{inertial_path}/origin",
    )
    mass = 0.0
    mass_element = inertial_element.find("mass")
    if mass_element is None:
        result.add(
            "error",
            "missing_mass",
            f"{display} link {link_name!r} inertial requires <mass>",
            path=inertial_path,
        )
    else:
        parsed_mass = _float_attr(mass_element, "value", result, display, label=f"link {link_name!r} inertial mass", path=inertial_path)
        if parsed_mass is not None:
            if parsed_mass <= 0.0:
                result.add(
                    "error",
                    "nonpositive_mass",
                    f"{display} link {link_name!r} inertial mass must be positive",
                    path=inertial_path,
                )
            else:
                mass = parsed_mass

    inertia_element = inertial_element.find("inertia")
    if inertia_element is None:
        result.add(
            "error",
            "missing_inertia",
            f"{display} link {link_name!r} inertial requires <inertia>",
            path=inertial_path,
        )
        return mass
    values: dict[str, float] = {}
    for key in _INERTIA_KEYS:
        parsed = _float_attr(inertia_element, key, result, display, label=f"link {link_name!r} inertia {key}", path=f"{inertial_path}/inertia")
        if parsed is None:
            return mass
        values[key] = parsed
    _validate_inertia_tensor(link_name, values, result, display, path=f"{inertial_path}/inertia")
    return mass


def _validate_inertia_tensor(
    link_name: str,
    values: dict[str, float],
    result: ValidationResult,
    display: str,
    *,
    path: str,
) -> None:
    if values["ixx"] <= 0.0 or values["iyy"] <= 0.0 or values["izz"] <= 0.0:
        result.add(
            "error",
            "nonpositive_inertia_diagonal",
            f"{display} link {link_name!r} inertia diagonal values must be positive",
            path=path,
        )
        return
    eigenvalues = symmetric_inertia_eigenvalues(values)
    scale = max(abs(value) for value in values.values())
    # The closed-form eigensolver is accurate to ~1e-8 relative; keep the
    # gate far above that but far below any physically meaningful violation.
    tolerance = scale * 1e-6 + 1e-12
    if any(value < -tolerance for value in eigenvalues):
        result.add(
            "error",
            "inertia_not_psd",
            f"{display} link {link_name!r} inertia tensor is not positive semidefinite",
            path=path,
            hint="Check the off-diagonal terms; the tensor may be expressed in the wrong frame.",
        )
        return
    low, mid, high = sorted(eigenvalues)
    if low + mid + tolerance < high:
        # Warning, not error: real-world exported URDFs violate this often and
        # Gazebo/libsdformat load them with a warning. --strict promotes it.
        result.add(
            "warning",
            "inertia_triangle_inequality",
            f"{display} link {link_name!r} inertia violates triangle inequalities",
            path=path,
            hint="Principal moments must satisfy l1 + l2 >= l3 for a physical rigid body.",
        )


def symmetric_inertia_eigenvalues(values: dict[str, float]) -> tuple[float, float, float]:
    """Closed-form eigenvalues of the symmetric 3x3 inertia tensor."""
    ixx, iyy, izz = values["ixx"], values["iyy"], values["izz"]
    ixy, ixz, iyz = values["ixy"], values["ixz"], values["iyz"]
    p1 = ixy * ixy + ixz * ixz + iyz * iyz
    if p1 == 0.0:
        return ixx, iyy, izz
    q = (ixx + iyy + izz) / 3.0
    p2 = (ixx - q) ** 2 + (iyy - q) ** 2 + (izz - q) ** 2 + 2.0 * p1
    p = math.sqrt(p2 / 6.0)
    if p == 0.0:
        return q, q, q
    b_xx, b_yy, b_zz = (ixx - q) / p, (iyy - q) / p, (izz - q) / p
    b_xy, b_xz, b_yz = ixy / p, ixz / p, iyz / p
    det_b = (
        b_xx * (b_yy * b_zz - b_yz * b_yz)
        - b_xy * (b_xy * b_zz - b_yz * b_xz)
        + b_xz * (b_xy * b_yz - b_yy * b_xz)
    )
    r = max(-1.0, min(1.0, det_b / 2.0))
    phi = math.acos(r) / 3.0
    eig1 = q + 2.0 * p * math.cos(phi)
    eig3 = q + 2.0 * p * math.cos(phi + (2.0 * math.pi / 3.0))
    eig2 = 3.0 * q - eig1 - eig3
    return eig1, eig2, eig3


def _warn_movable_links_without_inertial(
    root: ET.Element,
    joints: list[UrdfJoint],
    result: ValidationResult,
    display: str,
) -> None:
    movable_children = {joint.child_link for joint in joints if joint.joint_type in {"revolute", "continuous", "prismatic"}}
    for link_element in root.findall("link"):
        link_name = str(link_element.attrib.get("name") or "").strip()
        if link_name not in movable_children:
            continue
        has_geometry = link_element.find("visual") is not None or link_element.find("collision") is not None
        if has_geometry and link_element.find("inertial") is None:
            result.add(
                "warning",
                "missing_inertial",
                f"{display} movable link {link_name!r} has geometry but no inertial data",
                path=f"/robot/link[@name='{link_name}']",
                hint="Simulation and dynamics consumers need an inertial block; see references/inertials.md.",
            )


# --- geometry ---
def _validate_link_geometry(
    link_element: ET.Element,
    *,
    element_name: str,
    result: ValidationResult,
    display: str,
    link_path: str,
    source_path: Path,
    package_map: dict[str, Path] | None,
    material_names: set[str],
) -> list[Path]:
    mesh_paths: list[Path] = []
    link_name = str(link_element.attrib.get("name") or "").strip()
    known_children = KNOWN_VISUAL_CHILDREN if element_name == "visual" else KNOWN_COLLISION_CHILDREN
    for geometry_owner in link_element.findall(element_name):
        owner_path = f"{link_path}/{element_name}"
        _warn_unknown_children(geometry_owner, known_children, result, owner_path)
        _validate_origin(
            geometry_owner.find("origin"),
            result,
            display,
            label=f"link {link_name!r} {element_name} origin",
            path=f"{owner_path}/origin",
        )
        if element_name == "visual":
            _validate_material_reference(geometry_owner, material_names, result, display, owner_path)
        geometry_element = geometry_owner.find("geometry")
        if geometry_element is None:
            result.add(
                "error",
                "missing_geometry",
                f"{display} link {link_name!r} {element_name} requires <geometry>",
                path=owner_path,
            )
            continue
        geometry_child = _validate_geometry_element(
            geometry_element,
            result,
            display,
            label=f"link {link_name!r} {element_name} geometry",
            path=f"{owner_path}/geometry",
        )
        if geometry_child is None or geometry_child.tag != "mesh":
            continue
        mesh_path = _validate_mesh_reference(
            geometry_child,
            result=result,
            display=display,
            source_path=source_path,
            package_map=package_map,
            path=f"{owner_path}/geometry/mesh",
        )
        if mesh_path is not None:
            mesh_paths.append(mesh_path)
    return mesh_paths


def _validate_material_reference(
    visual_element: ET.Element,
    material_names: set[str],
    result: ValidationResult,
    display: str,
    owner_path: str,
) -> None:
    material_element = visual_element.find("material")
    if material_element is None:
        return
    has_definition = material_element.find("color") is not None or material_element.find("texture") is not None
    name = str(material_element.attrib.get("name") or "").strip()
    if has_definition or not name:
        return
    if name not in material_names:
        result.add(
            "warning",
            "dangling_material",
            f"{display} references undefined material {name!r}",
            path=f"{owner_path}/material",
            hint="Define the material at the robot root with a <color> or <texture>, or inline.",
        )


def _validate_geometry_element(
    geometry_element: ET.Element,
    result: ValidationResult,
    display: str,
    *,
    label: str,
    path: str,
) -> ET.Element | None:
    geometry_children = list(geometry_element)
    if len(geometry_children) != 1:
        supported = ", ".join(sorted(SUPPORTED_GEOMETRY_TAGS))
        result.add(
            "error",
            "invalid_geometry_count",
            f"{display} {label} must define exactly one geometry element: {supported}",
            path=path,
        )
        return None
    geometry_child = geometry_children[0]
    if geometry_child.tag not in SUPPORTED_GEOMETRY_TAGS:
        supported = ", ".join(sorted(SUPPORTED_GEOMETRY_TAGS))
        result.add(
            "error",
            "unsupported_geometry",
            f"{display} {label} must use one of: {supported}",
            path=path,
        )
        return None
    if geometry_child.tag == "box":
        _positive_vector_attr(geometry_child, "size", 3, result, display, label=f"{label} box size", path=f"{path}/box")
    elif geometry_child.tag == "cylinder":
        _positive_float_attr(geometry_child, "radius", result, display, label=f"{label} cylinder radius", path=f"{path}/cylinder")
        _positive_float_attr(geometry_child, "length", result, display, label=f"{label} cylinder length", path=f"{path}/cylinder")
    elif geometry_child.tag == "sphere":
        _positive_float_attr(geometry_child, "radius", result, display, label=f"{label} sphere radius", path=f"{path}/sphere")
    return geometry_child


def _validate_mesh_reference(
    mesh_element: ET.Element,
    *,
    result: ValidationResult,
    display: str,
    source_path: Path,
    package_map: dict[str, Path] | None,
    path: str,
) -> Path | None:
    filename = str(mesh_element.attrib.get("filename") or "").strip()
    if not filename:
        result.add("error", "missing_mesh_filename", f"{display} mesh filename is required", path=path)
        return None
    try:
        mesh_ref = classify_mesh_uri(filename)
    except UrdfSourceError as exc:
        result.add("error", "invalid_mesh_uri", f"{display} {exc}", path=path)
        return None
    _validate_mesh_scale(mesh_element, result, display, filename=filename, path=path)
    suffix = PurePosixPath(urlparse(filename).path or filename).suffix.lower()
    if suffix and suffix not in KNOWN_MESH_SUFFIXES:
        result.add(
            "warning",
            "unknown_mesh_extension",
            f"{display} mesh {filename!r} uses uncommon extension {suffix!r}",
            path=path,
            hint="Consumers commonly support: " + ", ".join(sorted(KNOWN_MESH_SUFFIXES)),
        )
    mesh_path = resolve_mesh_uri(filename, package_map=package_map)
    if mesh_path is None:
        if mesh_ref.kind == MeshUriKind.PACKAGE:
            message = f"WARN: {filename} syntax is valid but was not resolved."
        else:
            message = f"WARN: {filename} is not a local mesh URI and was not resolved."
        result.add("warning", "unresolved_mesh_uri", f"{display} {message}", path=path)
        return None
    if mesh_ref.kind == MeshUriKind.LOCAL_RELATIVE:
        mesh_path = (source_path.parent / mesh_path).resolve()
    if not mesh_path.is_file():
        result.add(
            "error",
            "missing_mesh_file",
            f"{display} references missing mesh file: {filename!r}",
            path=path,
        )
        return None
    return mesh_path


def _validate_mesh_scale(
    mesh_element: ET.Element,
    result: ValidationResult,
    display: str,
    *,
    filename: str,
    path: str,
) -> None:
    if "scale" not in mesh_element.attrib:
        return
    values = _vector_attr(mesh_element, "scale", 3, result, display, label=f"mesh {filename!r} scale", path=path)
    if values is None:
        return
    if any(value == 0.0 for value in values):
        result.add(
            "error",
            "zero_mesh_scale",
            f"{display} mesh {filename!r} scale values must be nonzero",
            path=path,
        )
        return
    if any(value < 0.0 for value in values):
        result.add(
            "warning",
            "negative_mesh_scale",
            f"{display} mesh {filename!r} uses negative scale (mirroring); "
            "consumer support varies and triangle winding flips.",
            path=path,
        )


# --- joints ---
def _validate_joint_axis(
    joint_element: ET.Element,
    *,
    joint_type: str,
    result: ValidationResult,
    display: str,
    joint_path: str,
) -> None:
    joint_name = joint_element.attrib.get("name", "")
    axis_element = joint_element.find("axis")
    if axis_element is None:
        if joint_type in {"revolute", "continuous", "prismatic"}:
            result.add(
                "warning",
                "implicit_joint_axis",
                f"{display} {joint_type} joint {joint_name!r} omits <axis> and defaults to (1, 0, 0)",
                path=joint_path,
                hint="Declare the axis explicitly; the spec default is easy to misread.",
            )
        return
    axis = _vector_attr(axis_element, "xyz", 3, result, display, label=f"joint {joint_name!r} axis", path=f"{joint_path}/axis")
    if axis is None:
        return
    if joint_type != "fixed" and all(component == 0.0 for component in axis):
        result.add(
            "error",
            "zero_joint_axis",
            f"{display} joint {joint_name!r} axis must be nonzero",
            path=f"{joint_path}/axis",
        )
        return
    norm = math.sqrt(sum(component * component for component in axis))
    if norm > 0.0 and abs(norm - 1.0) > _AXIS_UNIT_TOLERANCE:
        result.add(
            "warning",
            "non_unit_joint_axis",
            f"{display} joint {joint_name!r} axis length is {norm:.6g}, not 1",
            path=f"{joint_path}/axis",
        )


def _validate_joint_limits(
    joint_element: ET.Element,
    *,
    joint_type: str,
    result: ValidationResult,
    display: str,
    joint_path: str,
) -> tuple[float | None, float | None]:
    joint_name = joint_element.attrib.get("name", "")
    limit_element = joint_element.find("limit")
    limit_path = f"{joint_path}/limit"

    if joint_type == "fixed":
        if limit_element is not None:
            result.add(
                "warning",
                "fixed_joint_limits",
                f"{display} fixed joint {joint_name!r} declares a <limit> that consumers ignore",
                path=limit_path,
            )
        return 0.0, 0.0

    if joint_type == "continuous":
        if limit_element is not None:
            if "lower" in limit_element.attrib or "upper" in limit_element.attrib:
                result.add(
                    "warning",
                    "continuous_position_limits",
                    f"{display} continuous joint {joint_name!r} declares position limits that consumers ignore",
                    path=limit_path,
                    hint="Use type=\"revolute\" if the joint genuinely has position limits.",
                )
            _validate_effort_velocity(limit_element, joint_type, joint_name, result, display, limit_path)
        return None, None

    if joint_type not in {"revolute", "prismatic"}:
        return None, None

    if limit_element is None:
        result.add(
            "error",
            "missing_joint_limit",
            f"{display} {joint_type} joint {joint_name!r} requires <limit>",
            path=joint_path,
        )
        return None, None
    if "lower" not in limit_element.attrib or "upper" not in limit_element.attrib:
        result.add(
            "error",
            "missing_limit_bounds",
            f"{display} {joint_type} joint {joint_name!r} requires lower and upper limits",
            path=limit_path,
        )
        return None, None
    try:
        lower = float(limit_element.attrib["lower"])
        upper = float(limit_element.attrib["upper"])
    except ValueError:
        result.add(
            "error",
            "invalid_limit_bounds",
            f"{display} {joint_type} joint {joint_name!r} has invalid limits",
            path=limit_path,
        )
        return None, None
    if not isfinite(lower) or not isfinite(upper):
        result.add(
            "error",
            "nonfinite_limit_bounds",
            f"{display} {joint_type} joint {joint_name!r} limits must be finite",
            path=limit_path,
        )
        return None, None
    if lower > upper:
        result.add(
            "error",
            "reversed_limit_bounds",
            f"{display} {joint_type} joint {joint_name!r} lower limit exceeds upper limit",
            path=limit_path,
        )
        return None, None
    _validate_effort_velocity(limit_element, joint_type, joint_name, result, display, limit_path)
    return lower, upper


def _validate_effort_velocity(
    limit_element: ET.Element,
    joint_type: str,
    joint_name: str,
    result: ValidationResult,
    display: str,
    limit_path: str,
) -> None:
    for attr_name in ("effort", "velocity"):
        if attr_name not in limit_element.attrib:
            if joint_type in {"revolute", "prismatic"}:
                result.add(
                    "warning",
                    f"missing_{attr_name}",
                    f"{display} {joint_type} joint {joint_name!r} limit omits {attr_name!r}",
                    path=limit_path,
                    hint="The URDF schema requires effort and velocity; simulators misbehave without them.",
                )
            continue
        value = _float_attr(
            limit_element,
            attr_name,
            result,
            display,
            label=f"{joint_type} joint {joint_name!r} {attr_name} limit",
            path=limit_path,
        )
        if value is not None and value < 0.0:
            result.add(
                "error",
                f"negative_{attr_name}",
                f"{display} {joint_type} joint {joint_name!r} {attr_name} limit must be non-negative",
                path=limit_path,
            )


def _validate_joint_dynamics(
    joint_element: ET.Element,
    result: ValidationResult,
    display: str,
    joint_path: str,
) -> None:
    dynamics_element = joint_element.find("dynamics")
    if dynamics_element is None:
        return
    joint_name = joint_element.attrib.get("name", "")
    for attr_name in ("damping", "friction"):
        if attr_name not in dynamics_element.attrib:
            continue
        value = _float_attr(
            dynamics_element,
            attr_name,
            result,
            display,
            label=f"joint {joint_name!r} dynamics {attr_name}",
            path=f"{joint_path}/dynamics",
        )
        if value is not None and value < 0.0:
            result.add(
                "error",
                f"negative_{attr_name}",
                f"{display} joint {joint_name!r} dynamics {attr_name} must be non-negative",
                path=f"{joint_path}/dynamics",
            )


def _validate_mimic(
    joint_element: ET.Element,
    result: ValidationResult,
    display: str,
    joint_path: str,
    *,
    joint_name: str,
) -> str | None:
    mimic_element = joint_element.find("mimic")
    if mimic_element is None:
        return None
    mimic_path = f"{joint_path}/mimic"
    target = str(mimic_element.attrib.get("joint") or "").strip()
    if not target:
        result.add(
            "error",
            "missing_mimic_joint",
            f"{display} joint {joint_name!r} mimic requires a 'joint' attribute",
            path=mimic_path,
        )
        target = None
    elif target == joint_name:
        result.add(
            "error",
            "self_mimic",
            f"{display} joint {joint_name!r} cannot mimic itself",
            path=mimic_path,
        )
        target = None
    for attr_name in ("multiplier", "offset"):
        if attr_name in mimic_element.attrib:
            _float_attr(
                mimic_element,
                attr_name,
                result,
                display,
                label=f"joint {joint_name!r} mimic {attr_name}",
                path=mimic_path,
            )
    return target


def _validate_mimic_graph(
    mimic_targets_by_joint: dict[str, str],
    joint_types_by_name: dict[str, str],
    result: ValidationResult,
    display: str,
) -> None:
    for joint_name, target in mimic_targets_by_joint.items():
        joint_path = f"/robot/joint[@name='{joint_name}']/mimic"
        if target not in joint_types_by_name:
            result.add(
                "error",
                "missing_mimic_target",
                f"{display} joint {joint_name!r} mimics missing joint {target!r}",
                path=joint_path,
            )
            continue
        if joint_types_by_name.get(target) == "fixed":
            result.add(
                "error",
                "mimic_of_fixed_joint",
                f"{display} joint {joint_name!r} mimics fixed joint {target!r}",
                path=joint_path,
            )
    # cycle detection over the mimic graph
    for start in mimic_targets_by_joint:
        seen = {start}
        current = mimic_targets_by_joint.get(start)
        while current is not None:
            if current in seen:
                result.add(
                    "error",
                    "mimic_cycle",
                    f"{display} mimic joints form a cycle involving {start!r}",
                    path=f"/robot/joint[@name='{start}']/mimic",
                )
                break
            seen.add(current)
            current = mimic_targets_by_joint.get(current)


# --- generic attribute helpers ---
def _validate_origin(
    origin_element: ET.Element | None,
    result: ValidationResult,
    display: str,
    *,
    label: str,
    path: str,
) -> None:
    if origin_element is None:
        return
    if "xyz" in origin_element.attrib:
        _vector_attr(origin_element, "xyz", 3, result, display, label=f"{label} xyz", path=path)
    if "rpy" in origin_element.attrib:
        _vector_attr(origin_element, "rpy", 3, result, display, label=f"{label} rpy", path=path)


def _float_attr(
    element: ET.Element,
    attr_name: str,
    result: ValidationResult,
    display: str,
    *,
    label: str,
    path: str,
) -> float | None:
    if attr_name not in element.attrib:
        result.add("error", "missing_attribute", f"{display} {label} requires {attr_name!r}", path=path)
        return None
    try:
        parsed = float(element.attrib[attr_name])
    except ValueError:
        result.add("error", "invalid_number", f"{display} {label} is invalid", path=path)
        return None
    if not isfinite(parsed):
        result.add("error", "nonfinite_number", f"{display} {label} must be finite", path=path)
        return None
    return parsed


def _positive_float_attr(
    element: ET.Element,
    attr_name: str,
    result: ValidationResult,
    display: str,
    *,
    label: str,
    path: str,
) -> float | None:
    value = _float_attr(element, attr_name, result, display, label=label, path=path)
    if value is None:
        return None
    if value <= 0.0:
        result.add("error", "nonpositive_dimension", f"{display} {label} must be positive", path=path)
        return None
    return value


def _vector_attr(
    element: ET.Element,
    attr_name: str,
    expected_count: int,
    result: ValidationResult,
    display: str,
    *,
    label: str,
    path: str,
) -> tuple[float, ...] | None:
    if attr_name not in element.attrib:
        result.add("error", "missing_attribute", f"{display} {label} requires {attr_name!r}", path=path)
        return None
    raw_parts = element.attrib[attr_name].split()
    if len(raw_parts) != expected_count:
        result.add(
            "error",
            "wrong_vector_size",
            f"{display} {label} must have {expected_count} values",
            path=path,
        )
        return None
    try:
        values = tuple(float(part) for part in raw_parts)
    except ValueError:
        result.add("error", "invalid_number", f"{display} {label} is invalid", path=path)
        return None
    if not all(isfinite(value) for value in values):
        result.add("error", "nonfinite_number", f"{display} {label} values must be finite", path=path)
        return None
    return values


def _positive_vector_attr(
    element: ET.Element,
    attr_name: str,
    expected_count: int,
    result: ValidationResult,
    display: str,
    *,
    label: str,
    path: str,
) -> tuple[float, ...] | None:
    values = _vector_attr(element, attr_name, expected_count, result, display, label=label, path=path)
    if values is None:
        return None
    if any(value <= 0.0 for value in values):
        result.add("error", "nonpositive_dimension", f"{display} {label} values must be positive", path=path)
        return None
    return values


def _warn_unknown_children(
    element: ET.Element,
    known_children: set[str],
    result: ValidationResult,
    path: str,
) -> None:
    for child in list(element):
        tag = str(child.tag)
        if not isinstance(child.tag, str):
            continue  # comments / processing instructions
        if "}" in tag or ":" in tag:
            continue  # namespaced extensions (gazebo, tcad, ...) pass through
        if tag not in known_children:
            result.add(
                "warning",
                "unknown_element",
                f"unknown element <{tag}> under {path}",
                path=f"{path}/{tag}",
                hint=_UNKNOWN_ELEMENT_HINT,
            )


def _report_duplicates(
    values: list[str],
    result: ValidationResult,
    display: str,
    *,
    label: str,
    code: str,
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
            continue
        seen.add(value)
    if duplicates:
        duplicate_text = ", ".join(repr(item) for item in sorted(duplicates))
        result.add(
            "error",
            code,
            f"{display} {label} names contain duplicates {duplicate_text}",
            path="/robot",
        )


def _has_duplicates(values: list[str]) -> bool:
    return len(values) != len(set(values))


# --- mesh URI helpers ---
def _is_rooted(path: Path) -> bool:
    """Does this path start from a root, rather than from wherever we happen to be?

    ``is_absolute()`` is the obvious call and is wrong on Windows for the shape URDF files
    are full of: "/opt/ros/share/robot/meshes/base.stl" has a root and no drive, which makes
    it drive-RELATIVE there, so is_absolute() is False. Classifying it LOCAL_RELATIVE would
    then resolve it against some unrelated base directory and silently produce a path the
    author never wrote. A rooted path is not a relative path on any platform; on Windows it
    means "from the root of the current drive", which is exactly what resolve() gives back.
    """
    return path.is_absolute() or bool(path.root)


def classify_mesh_uri(uri: str) -> MeshReference:
    value = str(uri or "").strip()
    parsed = urlparse(value)

    if parsed.scheme == "package":
        package_name = unquote(parsed.netloc).strip()
        package_path = PurePosixPath(unquote(parsed.path).lstrip("/"))
        if not package_name or package_path.as_posix() == "." or ".." in package_path.parts:
            raise UrdfSourceError(f"package mesh URI is invalid: {uri!r}")
        return MeshReference(
            uri=value,
            kind=MeshUriKind.PACKAGE,
            package_name=package_name,
            package_path=package_path,
        )

    if parsed.scheme == "file":
        file_path = Path(unquote(parsed.path))
        if _is_rooted(file_path):
            return MeshReference(uri=value, kind=MeshUriKind.LOCAL_ABSOLUTE, path=file_path.resolve())
        return MeshReference(uri=value, kind=MeshUriKind.LOCAL_RELATIVE, path=file_path)

    if parsed.scheme:
        return MeshReference(uri=value, kind=MeshUriKind.REMOTE)

    local_path = Path(value)
    if _is_rooted(local_path):
        return MeshReference(uri=value, kind=MeshUriKind.LOCAL_ABSOLUTE, path=local_path.resolve())
    return MeshReference(uri=value, kind=MeshUriKind.LOCAL_RELATIVE, path=local_path)


def resolve_mesh_uri(uri: str, package_map: dict[str, Path] | None = None) -> Path | None:
    mesh_ref = classify_mesh_uri(uri)
    if mesh_ref.kind in {MeshUriKind.LOCAL_RELATIVE, MeshUriKind.LOCAL_ABSOLUTE}:
        return mesh_ref.path
    if mesh_ref.kind == MeshUriKind.PACKAGE:
        package_root = (package_map or {}).get(str(mesh_ref.package_name))
        if package_root is None or mesh_ref.package_path is None:
            return None
        return (Path(package_root).expanduser() / Path(*mesh_ref.package_path.parts)).resolve()
    return None


def _relative_to_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()

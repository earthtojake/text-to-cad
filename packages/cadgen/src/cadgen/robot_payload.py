"""A robot description resolved into what a page plays and draws.

A URDF, an SDF, or an SRDF with the URDF it plans for, becomes ONE payload: the robot's
articulation in the format a STEP's kinematics take (``cadgen.articulation``: controls per
movable joint, joints in their rest frames with affine rows over the controls, which link
each joint carries, what a drag writes, the named poses and the opening pose), the list of
visuals to draw (each with its rest placement, its colour and the mesh it draws), and what
the description says about its links and joints, as written, for a person reading it back.
The page builds a scene from the visual list and plays the articulation; it parses no XML,
resolves no frame, meshes no shape and decides no limit.

The payload::

    {
      "schemaVersion": 1,
      "kind": "urdf" | "sdf" | "srdf",
      "name": the robot's (an SDF model's) name,
      "root": the root link; "" for an SDF model whose links float free,
      "articulation": the articulation (``cadgen.articulation``), whose ``carries`` name links,
      "links": [{"name", "placement", "visuals": [facts], "collisions": [facts], "inertial"}],
      "joints": [{"name", "type", "parent", "child", "axis", "origin", "limit", "mimic"}],
      "visuals": [{"id", "link", "label", "placement", "color", "mesh": {"format", ...}}],
      "srdf": the planning semantics the SRDF declares, or null,
      "sdf": what an SDF says about itself beyond its links and joints, or null,
    }

- ``placement`` is a row-major 4x4 in the robot's REST space (the description as written,
  every joint at zero): a link's is its frame, a visual's its mesh's -- the link frame, the
  visual's origin and the mesh's scale composed, so the page sets it on a mesh and nothing
  else. A link's visuals sit under the joint that carries the link; the joint's delta
  (``articulation.joint_matrices``) moves them.
- A control is a joint a person or a job sets: revolute and continuous joints in DEGREES,
  prismatic joints in METRES, each at its declared limits (a continuous joint has none). A
  mimic follower is not a control: its row is its leader's, scaled and offset, so one value
  moves both. ``poses`` are an SRDF's group states (``<group>/<name>``), ``opening`` every
  control at rest with the SRDF's ``home`` state(s) over it.
- A visual's mesh is the file it names (``format`` the page's decoder: stl, 3mf or glb) or,
  for a box, cylinder, sphere or capsule, a GLB cadgen meshed at the standard rung of the
  display ladder and stored as an object (``_internal.primitive_mesh``). The payload names
  a file by its absolute path (``path``) and a primitive by its object hash (``object``);
  the host that serves it mints each one's ``url`` (:func:`locate_robot_payload`).
- Refusals are the validators' (``cadgen.urdf_source``, ``cadgen.sdf_validation``,
  ``cadgen.srdf_validation``) plus what the page cannot draw: a mesh in a format it has no
  decoder for, a shape it has no mesh for, a mesh it cannot reach. Every refusal is a
  :class:`RobotReadError` saying what to change.

The payload is derived data, cached in the store's ``robot`` index keyed by the
description's path and bytes and its paired URDF's bytes (``cadgen.store.robots``), so a
second read of an unchanged description reads one object.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from cadgen.articulation import ARTICULATION_SCHEMA_VERSION
from cadgen.findings import FindingsReport, format_findings
from cadgen.tessellation_policy import DEFAULT_TESSELLATION
from cadgen.xml_common import children, display_path, local_name

__all__ = [
    "DRAWABLE_MESH_FORMATS",
    "ROBOT_PAYLOAD_SCHEMA_VERSION",
    "ROBOT_SUFFIXES",
    "RobotReadError",
    "locate_robot_payload",
    "paired_urdf_for_srdf",
    "read_robot_description",
    "robot_control_values",
    "robot_payload",
    "robot_payload_bytes",
    "robot_payload_scheme",
]

ROBOT_PAYLOAD_SCHEMA_VERSION = 1
ROBOT_SUFFIXES = (".urdf", ".srdf", ".sdf")
#: The mesh files the page decodes, by suffix: what a link mesh may be.
DRAWABLE_MESH_FORMATS = {".stl": "stl", ".3mf": "3mf", ".glb": "glb"}
#: The shapes cadgen meshes for a visual (``_internal.primitive_mesh``).
DRAWABLE_SHAPES = ("box", "capsule", "cylinder", "sphere")
# The page draws a GLB in millimetres; a primitive is meshed in metres.
_PRIMITIVE_SCALE = 0.001
_IDENTITY = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
_SDF_MODEL_FRAME = "__model__"
_SDF_WORLD_FRAME = "world"
_SDF_EXTERNAL_SCHEMES = {"model", "package", "http", "https", "fuel"}
_MOVING = ("revolute", "continuous", "prismatic")
_ANGULAR = ("revolute", "continuous")


class RobotReadError(ValueError):
    """A description this cannot resolve, and what to change."""


# --- small matrices (row-major 4x4 lists) ------------------------------------------------


def _multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _translation(x: float, y: float, z: float) -> list[list[float]]:
    return [[1.0, 0.0, 0.0, x], [0.0, 1.0, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]]


def _scale(x: float, y: float, z: float) -> list[list[float]]:
    return [[x, 0.0, 0.0, 0.0], [0.0, y, 0.0, 0.0], [0.0, 0.0, z, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _rpy(roll: float, pitch: float, yaw: float) -> list[list[float]]:
    sr, cr, sp, cp, sy, cy = math.sin(roll), math.cos(roll), math.sin(pitch), math.cos(pitch), math.sin(yaw), math.cos(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, 0.0],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, 0.0],
        [-sp, cp * sr, cp * cr, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _pose(xyz, rpy) -> list[list[float]]:
    return _multiply(_translation(*xyz), _rpy(*rpy))


def _invert_rigid(m: list[list[float]]) -> list[list[float]]:
    r = [[m[i][j] for j in range(3)] for i in range(3)]
    t = [m[0][3], m[1][3], m[2][3]]
    return [
        [r[0][0], r[1][0], r[2][0], -(r[0][0] * t[0] + r[1][0] * t[1] + r[2][0] * t[2])],
        [r[0][1], r[1][1], r[2][1], -(r[0][1] * t[0] + r[1][1] * t[1] + r[2][1] * t[2])],
        [r[0][2], r[1][2], r[2][2], -(r[0][2] * t[0] + r[1][2] * t[1] + r[2][2] * t[2])],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _rotate(m: list[list[float]], v) -> list[float]:
    return [m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3)]


def _unit(v) -> list[float] | None:
    length = math.hypot(v[0], v[1], v[2])
    if not math.isfinite(length) or length < 1e-12:
        return None
    return [v[0] / length, v[1] / length, v[2] / length]


# Emitted numbers are rounded past any display accuracy and short of a float's last bits, so
# one description resolves to one payload on every platform's libm (the fixtures the browser
# suite serves are compared byte for byte against a fresh read).
_DECIMALS = 12


def _number(value: float) -> float:
    return round(float(value), _DECIMALS) + 0.0


def _flat(m: list[list[float]]) -> list[float]:
    return [_number(value) for row in m for value in row]


# --- numbers from XML ----------------------------------------------------------------------


def _numbers(text: object, count: int, *, where: str, default: list[float] | None = None) -> list[float]:
    raw = str(text or "").split()
    if not raw and default is not None:
        return list(default)
    try:
        values = [float(part) for part in raw]
    except ValueError:
        values = []
    if len(values) != count or not all(math.isfinite(value) for value in values):
        raise RobotReadError(f"{where} must be {count} numbers, not {str(text or '').strip()!r}")
    return values


def _optional_number(element: ET.Element | None, name: str) -> float | None:
    text = element.attrib.get(name) if element is not None else None
    try:
        value = float(text) if text is not None and str(text).strip() else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) else None


def _optional_numbers(text: object, count: int) -> list[float] | None:
    try:
        values = [float(part) for part in str(text or "").split()]
    except ValueError:
        return None
    return values if len(values) == count and all(math.isfinite(v) for v in values) else None


def _hex(rgb: list[float]) -> str:
    # Half rounds up, as a GLB's colour bytes are written (a channel is never negative here).
    return "#" + "".join(f"{int(max(0.0, min(1.0, channel)) * 255 + 0.5):02x}" for channel in rgb[:3])


def _described_origin(xyz: list[float] | None, rpy: list[float] | None) -> dict[str, list[float]]:
    return {"xyz": list(xyz or [0.0, 0.0, 0.0]), "rpy": list(rpy or [0.0, 0.0, 0.0])}


# --- the intermediate description ------------------------------------------------------------


class _Visual:
    __slots__ = ("id", "label", "local", "color", "mesh", "facts")

    def __init__(self, visual_id: str, label: str, local: list[list[float]], color: str, mesh: dict, facts: dict) -> None:
        self.id, self.label, self.local, self.color, self.mesh, self.facts = visual_id, label, local, color, mesh, facts


class _Link:
    __slots__ = ("name", "placement", "visuals", "collisions", "inertial")

    def __init__(self, name: str) -> None:
        self.name = name
        self.placement: list[list[float]] = _IDENTITY
        self.visuals: list[_Visual] = []
        self.collisions: list[dict] = []
        self.inertial: dict | None = None


class _Joint:
    __slots__ = ("name", "type", "parent", "child", "frame", "axis", "lower", "upper", "mimic", "facts")

    def __init__(self, name: str, joint_type: str, parent: str, child: str) -> None:
        self.name, self.type, self.parent, self.child = name, joint_type, parent, child
        self.frame: list[list[float]] = _IDENTITY  # the joint's rest frame in the robot's space
        self.axis: list[float] | None = None  # unit, in the robot's rest space
        self.lower: float | None = None  # native units: radians or metres
        self.upper: float | None = None
        self.mimic: tuple[str, float, float] | None = None  # (leader, multiplier, offset)
        self.facts: dict = {}


class _Description:
    def __init__(self, kind: str, name: str) -> None:
        self.kind, self.name = kind, name
        self.links: list[_Link] = []
        self.joints: list[_Joint] = []
        self.root = ""
        self.poses: dict[str, dict[str, float]] = {}  # group states, in control units
        self.home: dict[str, float] = {}
        self.srdf: dict | None = None
        self.sdf: dict | None = None


# --- meshes --------------------------------------------------------------------------------


def _drawable_format(reference: str, *, where: str) -> str:
    suffix = PurePosixPath(urlparse(reference).path or reference).suffix.lower()
    if suffix not in DRAWABLE_MESH_FORMATS:
        formats = ", ".join(sorted(DRAWABLE_MESH_FORMATS))
        raise RobotReadError(
            f"{where} names {reference!r}, a {suffix or 'file with no extension'} the viewer cannot draw: "
            f"export the link as one of {formats} and name that file"
        )
    return DRAWABLE_MESH_FORMATS[suffix]


def _primitive_mesh(shape: str, dimensions: dict) -> dict:
    """The store object of a primitive's mesh, meshed and published on first sight."""
    from cadgen._internal.primitive_mesh import primitive_glb
    from cadgen.store.objects import put_object

    return {"format": "glb", "object": put_object(primitive_glb(shape, dimensions))}


# --- URDF ------------------------------------------------------------------------------------


def _urdf_geometry_facts(geometry: ET.Element | None) -> dict:
    mesh = geometry.find("mesh") if geometry is not None else None
    if mesh is not None:
        return {"type": "mesh", "filename": str(mesh.attrib.get("filename") or "").strip(),
                "scale": _optional_numbers(mesh.attrib.get("scale"), 3)}
    for shape in ("box", "cylinder", "sphere"):
        element = geometry.find(shape) if geometry is not None else None
        if element is not None:
            facts: dict = {"type": shape, "filename": ""}
            if shape == "box":
                facts["size"] = _optional_numbers(element.attrib.get("size"), 3)
            else:
                facts["radius"] = _optional_number(element, "radius")
                if shape == "cylinder":
                    facts["length"] = _optional_number(element, "length")
            return facts
    return {"type": "unknown", "filename": ""}


def _urdf_shape_facts(element: ET.Element) -> dict:
    origin = element.find("origin")
    return {
        "name": str(element.attrib.get("name") or "").strip(),
        **_urdf_geometry_facts(element.find("geometry")),
        "origin": _described_origin(
            _optional_numbers(origin.attrib.get("xyz") if origin is not None else None, 3),
            _optional_numbers(origin.attrib.get("rpy") if origin is not None else None, 3),
        ),
    }


def _urdf_origin(element: ET.Element | None, *, where: str) -> list[list[float]]:
    if element is None:
        return _IDENTITY
    xyz = _numbers(element.attrib.get("xyz"), 3, where=f"{where} origin xyz", default=[0.0, 0.0, 0.0])
    rpy = _numbers(element.attrib.get("rpy"), 3, where=f"{where} origin rpy", default=[0.0, 0.0, 0.0])
    return _pose(xyz, rpy)


def _urdf_material_color(material: ET.Element | None, named: dict[str, str]) -> tuple[str, str]:
    """``(colour, material name)``: an inline ``<color>`` wins, else the named material's."""
    if material is None:
        return "", ""
    name = str(material.attrib.get("name") or "").strip()
    color = material.find("color")
    rgba = _optional_numbers(color.attrib.get("rgba") if color is not None else None, 4)
    if rgba is not None:
        return _hex(rgba), name
    return named.get(name, ""), name


def _resolve_urdf_mesh(filename: str, *, source_path: Path, package_map: dict[str, Path] | None, where: str) -> dict:
    from cadgen.urdf_source import MeshUriKind, classify_mesh_uri, resolve_mesh_uri

    try:
        reference = classify_mesh_uri(filename)
    except ValueError as exc:
        raise RobotReadError(f"{where}: {exc}") from None
    fmt = _drawable_format(filename, where=where)
    if reference.kind is MeshUriKind.REMOTE:
        raise RobotReadError(
            f"{where} names {filename!r}, which is not a local file: the viewer draws the meshes beside "
            "the description; copy the file next to it and name it by a relative path"
        )
    path = resolve_mesh_uri(filename, package_map=package_map)
    if path is None:
        raise RobotReadError(
            f"{where} names {filename!r}, a package this cannot resolve: name the mesh by a path relative "
            "to the description instead (the viewer resolves no package://)"
        )
    if reference.kind is MeshUriKind.LOCAL_RELATIVE:
        path = (source_path.parent / path).resolve()
    if not path.is_file():
        raise RobotReadError(f"{where} names {filename!r}, and no file is at {path}")
    return {"format": fmt, "path": str(path)}


def _read_urdf(path: Path, *, package_map: dict[str, Path] | None = None) -> _Description:
    from cadgen.urdf_source import validate_urdf_file

    source, findings = validate_urdf_file(path, package_map=package_map)
    if findings.errors or source is None:
        raise RobotReadError(format_findings(findings.errors))
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise RobotReadError(f"{display_path(path)} could not be read: {exc}") from None
    display = display_path(path)
    description = _Description("urdf", source.robot_name)
    named_colors: dict[str, str] = {}
    for material in root.findall("material"):
        name = str(material.attrib.get("name") or "").strip()
        color = material.find("color")
        rgba = _optional_numbers(color.attrib.get("rgba") if color is not None else None, 4)
        if name and rgba is not None:
            named_colors[name] = _hex(rgba)

    links: dict[str, _Link] = {}
    undrawable: list[str] = []  # every visual the page cannot draw, named together
    for link_element in root.findall("link"):
        link = _Link(str(link_element.attrib.get("name") or "").strip())
        for index, visual_element in enumerate(link_element.findall("visual"), start=1):
            where = f"{display} link {link.name!r} visual {index}"
            geometry = visual_element.find("geometry")
            facts = _urdf_shape_facts(visual_element)
            color, material_name = _urdf_material_color(visual_element.find("material"), named_colors)
            facts["color"], facts["materialName"] = color, material_name
            local = _urdf_origin(visual_element.find("origin"), where=where)
            mesh_element = geometry.find("mesh") if geometry is not None else None
            try:
                if mesh_element is not None:
                    filename = str(mesh_element.attrib.get("filename") or "").strip()
                    mesh = _resolve_urdf_mesh(filename, source_path=path, package_map=package_map, where=where)
                    scale = _numbers(mesh_element.attrib.get("scale"), 3, where=f"{where} mesh scale", default=[1.0, 1.0, 1.0])
                    facts["path"] = mesh["path"]
                    label = PurePosixPath(filename).name or "mesh"
                    local = _multiply(local, _scale(*scale))
                else:
                    shape = facts["type"]
                    if shape not in DRAWABLE_SHAPES:
                        raise RobotReadError(f"{where} uses geometry the viewer cannot draw; give it a mesh, box, cylinder or sphere")
                    dimensions = {key: facts[key] for key in ("size", "radius", "length") if facts.get(key) is not None}
                    mesh = _primitive_mesh(shape, dimensions)
                    label = shape
                    local = _multiply(local, _scale(_PRIMITIVE_SCALE, _PRIMITIVE_SCALE, _PRIMITIVE_SCALE))
            except RobotReadError as exc:
                undrawable.append(str(exc))
                continue
            link.visuals.append(_Visual(f"{link.name}:v{index}", label, local, color, mesh, facts))
        link.collisions = [_urdf_shape_facts(element) for element in link_element.findall("collision")]
        inertial = link_element.find("inertial")
        if inertial is not None:
            origin = inertial.find("origin")
            inertia_element = inertial.find("inertia")
            inertia = {key: _optional_number(inertia_element, key) for key in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")}
            link.inertial = {
                "mass": _optional_number(inertial.find("mass"), "value"),
                "origin": _described_origin(
                    _optional_numbers(origin.attrib.get("xyz") if origin is not None else None, 3),
                    _optional_numbers(origin.attrib.get("rpy") if origin is not None else None, 3),
                ),
                "inertia": inertia if all(value is not None for value in inertia.values()) else None,
            }
        links[link.name] = link
        description.links.append(link)
    if undrawable:
        raise RobotReadError("; ".join(undrawable))

    joints_by_name: dict[str, _Joint] = {}
    for joint_element in root.findall("joint"):
        name = str(joint_element.attrib.get("name") or "").strip()
        declared = next(joint for joint in source.joints if joint.name == name)
        joint = _Joint(name, declared.joint_type, declared.parent_link, declared.child_link)
        where = f"{display} joint {name!r}"
        origin_element = joint_element.find("origin")
        axis_element = joint_element.find("axis")
        axis = _numbers(axis_element.attrib.get("xyz") if axis_element is not None else None, 3,
                        where=f"{where} axis", default=[1.0, 0.0, 0.0])
        joint.lower, joint.upper = declared.lower, declared.upper
        if joint.type == "continuous":
            joint.lower = joint.upper = None
        mimic_element = joint_element.find("mimic")
        if mimic_element is not None:
            leader = str(mimic_element.attrib.get("joint") or "").strip()
            multiplier = _optional_number(mimic_element, "multiplier")
            offset = _optional_number(mimic_element, "offset")
            joint.mimic = (leader, 1.0 if multiplier is None else multiplier, 0.0 if offset is None else offset)
        limit_element = joint_element.find("limit")
        limit = {key: _optional_number(limit_element, key) for key in ("lower", "upper", "effort", "velocity")}
        joint.facts = {
            "name": name, "type": joint.type, "parent": joint.parent, "child": joint.child,
            "axis": None if joint.type == "fixed" else list(axis),
            "origin": _described_origin(
                _optional_numbers(origin_element.attrib.get("xyz") if origin_element is not None else None, 3),
                _optional_numbers(origin_element.attrib.get("rpy") if origin_element is not None else None, 3),
            ),
            "limit": {key: value for key, value in limit.items() if value is not None} if limit_element is not None else None,
            "mimic": {"joint": joint.mimic[0], "multiplier": joint.mimic[1], "offset": joint.mimic[2]} if joint.mimic else None,
        }
        joint.facts["_origin"] = _urdf_origin(origin_element, where=where)
        joint.facts["_axis"] = axis
        joints_by_name[name] = joint
        description.joints.append(joint)

    # Rest placements: the root at the origin, every child link's frame its joint's frame.
    description.root = source.root_link
    by_parent: dict[str, list[_Joint]] = {}
    for joint in description.joints:
        by_parent.setdefault(joint.parent, []).append(joint)
    pending = [source.root_link]
    while pending:
        parent_name = pending.pop(0)
        parent = links[parent_name]
        for joint in by_parent.get(parent_name, ()):
            joint.frame = _multiply(parent.placement, joint.facts.pop("_origin"))
            axis = joint.facts.pop("_axis")
            joint.axis = None if joint.type == "fixed" else _unit(_rotate(joint.frame, axis))
            if joint.type != "fixed" and joint.axis is None:
                raise RobotReadError(f"{display} joint {joint.name!r} axis must be nonzero")
            links[joint.child].placement = joint.frame
            pending.append(joint.child)
    return description


# --- SDF -------------------------------------------------------------------------------------


def _sdf_text(parent: ET.Element, tag: str) -> str:
    found = children(parent, tag)
    return str(found[0].text or "").strip() if found else ""


def _sdf_first(parent: ET.Element, tag: str) -> ET.Element | None:
    found = children(parent, tag)
    return found[0] if found else None


def _sdf_pose(element: ET.Element, *, where: str) -> tuple[bool, str, list[float], list[list[float]]]:
    """``(declared, relative_to, values, transform)`` of an element's ``<pose>``."""
    pose = _sdf_first(element, "pose")
    if pose is None:
        return False, "", [0.0] * 6, _IDENTITY
    rotation_format = str(pose.attrib.get("rotation_format") or "euler_rpy").strip().lower()
    if rotation_format != "euler_rpy":
        raise RobotReadError(f"{where} pose uses rotation_format {rotation_format!r}; the viewer reads euler_rpy")
    values = _numbers(pose.text, 6, where=f"{where} pose", default=[0.0] * 6)
    if str(pose.attrib.get("degrees") or "").strip().lower() in ("1", "true", "yes", "on"):
        values[3:] = [math.radians(value) for value in values[3:]]
    return True, str(pose.attrib.get("relative_to") or "").strip(), values, _pose(values[:3], values[3:])


class _SdfFrames:
    """The model's frame graph: links, frames and joints to their rest transforms in the
    model's world, by the SDFormat 1.7+ rules (``relative_to``, ``attached_to``, a joint's
    pose relative to its child, a frame's to what it is attached to)."""

    def __init__(self, model_name: str, model_world: list[list[float]]) -> None:
        self.model_name = model_name
        self.nodes: dict[str, dict] = {
            _SDF_WORLD_FRAME: {"kind": "world", "world": _IDENTITY},
            _SDF_MODEL_FRAME: {"kind": "model", "world": model_world},
        }
        self.links: set[str] = set()

    def normalize(self, name: str, default: str) -> str:
        text = str(name or "").strip()
        if not text:
            return default
        if text in (self.model_name, _SDF_MODEL_FRAME):
            return _SDF_MODEL_FRAME
        return text

    def add(self, name: str, node: dict) -> None:
        if name in self.nodes:
            raise RobotReadError(f"SDF model {self.model_name!r} names {name!r} twice: links, frames and joints share one namespace")
        self.nodes[name] = node

    def world(self, name: str, default: str = _SDF_MODEL_FRAME, resolving: tuple[str, ...] = ()) -> list[list[float]]:
        key = self.normalize(name, default)
        node = self.nodes.get(key)
        if node is None:
            raise RobotReadError(f"SDF model {self.model_name!r} refers to frame {key!r}, which it does not declare")
        if "world" in node:
            return node["world"]
        if key in resolving:
            raise RobotReadError(f"SDF model {self.model_name!r} frame graph cycles at {key!r}")
        relative = self.normalize(node["relative_to"], node["default"])
        node["world"] = _multiply(self.world(relative, _SDF_MODEL_FRAME, (*resolving, key)), node["pose"])
        return node["world"]

    def attached_link(self, name: str, resolving: tuple[str, ...] = ()) -> str:
        key = self.normalize(name, _SDF_MODEL_FRAME)
        if key in self.links:
            return key
        if key in (_SDF_MODEL_FRAME, _SDF_WORLD_FRAME):
            return ""
        node = self.nodes.get(key)
        if node is None:
            raise RobotReadError(f"SDF model {self.model_name!r} refers to frame {key!r}, which it does not declare")
        if key in resolving:
            raise RobotReadError(f"SDF model {self.model_name!r} attached_to graph cycles at {key!r}")
        if node["kind"] == "frame":
            return self.attached_link(node["attached"], (*resolving, key))
        if node["kind"] == "joint":
            return self.attached_link(node["child"], (*resolving, key))
        return ""


def _sdf_shape_facts(owner: ET.Element, *, where: str) -> dict:
    geometry = _sdf_first(owner, "geometry")
    declared, _relative, values, _transform = _sdf_pose(owner, where=where)
    facts: dict = {"name": str(owner.attrib.get("name") or "").strip(), "type": "unknown", "filename": "",
                   "origin": _described_origin(values[:3], values[3:])}
    shapes = [child for child in list(geometry) if isinstance(child.tag, str)] if geometry is not None else []
    shape = shapes[0] if shapes else None
    if shape is None:
        facts["type"] = "missing"
        return facts
    kind = local_name(shape.tag)
    facts["type"] = kind
    if kind == "mesh":
        facts["filename"] = _sdf_text(shape, "uri")
        facts["scale"] = _optional_numbers(_sdf_text(shape, "scale"), 3)
    elif kind == "box":
        facts["size"] = _optional_numbers(_sdf_text(shape, "size"), 3)
    elif kind in ("cylinder", "sphere", "capsule"):
        facts["radius"] = _optional_numbers(_sdf_text(shape, "radius"), 1)
        facts["radius"] = facts["radius"][0] if facts["radius"] else None
        if kind != "sphere":
            length = _optional_numbers(_sdf_text(shape, "length"), 1)
            facts["length"] = length[0] if length else None
    return facts


def _sdf_color(owner: ET.Element) -> str:
    material = _sdf_first(owner, "material")
    if material is None:
        return ""
    for tag in ("diffuse", "ambient"):
        raw = _sdf_text(material, tag).split()
        if len(raw) in (3, 4):
            values = _optional_numbers(" ".join(raw), len(raw))
            if values is not None:
                return _hex(values)
    return ""


def _sdf_model(root: ET.Element, *, display: str) -> tuple[str, str, ET.Element]:
    """``(document kind, world name, the model element)``: the one model a document renders."""
    models = children(root, "model")
    if len(models) == 1:
        return "model", "", models[0]
    if len(models) > 1:
        raise RobotReadError(f"{display} holds {len(models)} top-level models; the viewer renders one direct <model>")
    worlds = children(root, "world")
    if len(worlds) != 1:
        raise RobotReadError(f"{display} must hold one direct <model>, or one <world> holding one direct <model>")
    world_models = children(worlds[0], "model")
    if len(world_models) != 1:
        raise RobotReadError(f"{display} world holds {len(world_models)} models; the viewer renders a world with exactly one direct <model>")
    return "world", str(worlds[0].attrib.get("name") or "").strip(), world_models[0]


def _sdf_metadata(root: ET.Element) -> dict:
    def attributes(element: ET.Element, names: tuple[str, ...]) -> dict:
        return {name: str(element.attrib.get(name) or "").strip() for name in names if str(element.attrib.get(name) or "").strip()}

    def descendants(tag: str) -> list[ET.Element]:
        return [element for element in root.iter() if isinstance(element.tag, str) and local_name(element.tag) == tag]

    nested = 0
    parents = {child: parent for parent in root.iter() for child in parent}
    for model in descendants("model"):
        parent = parents.get(model)
        if parent is not None and local_name(parent.tag) == "model":
            nested += 1
    return {
        "includes": [{"id": f"include:{index}", "uri": _sdf_text(element, "uri"), "name": _sdf_text(element, "name")}
                     for index, element in enumerate(descendants("include"), start=1)],
        "plugins": [{"id": f"plugin:{index}", **attributes(element, ("name", "filename"))}
                    for index, element in enumerate(descendants("plugin"), start=1)],
        "sensors": [{"id": f"sensor:{index}", **attributes(element, ("name", "type"))}
                    for index, element in enumerate(descendants("sensor"), start=1)],
        "lights": [{"id": f"light:{index}", **attributes(element, ("name", "type"))}
                   for index, element in enumerate(descendants("light"), start=1)],
        "physics": [{"id": f"physics:{index}", **attributes(element, ("name", "type", "default"))}
                    for index, element in enumerate(descendants("physics"), start=1)],
        "nestedModelCount": nested,
    }


def _resolve_sdf_mesh(uri: str, *, base_dir: Path, where: str) -> dict:
    parsed = urlparse(uri)
    if parsed.scheme in _SDF_EXTERNAL_SCHEMES or (parsed.scheme and parsed.scheme != "file"):
        raise RobotReadError(
            f"{where} names {uri!r}, which is not a local file: the viewer draws the meshes beside the "
            "description; copy the file next to it and name it by a relative path"
        )
    fmt = _drawable_format(uri, where=where)
    path = Path(unquote(parsed.path)).resolve() if parsed.scheme == "file" else (base_dir / uri).resolve()
    if not path.is_file():
        raise RobotReadError(f"{where} names {uri!r}, and no file is at {path}")
    return {"format": fmt, "path": str(path)}


def _read_sdf(path: Path) -> _Description:
    from cadgen.sdf_source import SdfSourceError
    from cadgen.sdf_validation import raise_for_validation_errors, validate_sdf_root

    display = display_path(path)
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise RobotReadError(f"{display} could not be parsed as SDF XML: {exc}") from None
    try:
        raise_for_validation_errors(validate_sdf_root(root, source_path=path, base_dir=path.parent))
    except SdfSourceError as exc:
        raise RobotReadError(str(exc)) from None
    if local_name(root.tag) != "sdf":
        raise RobotReadError(f"{display} root element must be <sdf>")
    version = str(root.attrib.get("version") or "").strip()
    document_kind, world_name, model = _sdf_model(root, display=display)
    model_name = str(model.attrib.get("name") or "").strip()
    description = _Description("sdf", model_name)
    _declared, relative_to, _values, model_world = _sdf_pose(model, where=f"{display} model {model_name!r}")
    if relative_to and relative_to != _SDF_WORLD_FRAME:
        raise RobotReadError(f"{display} model {model_name!r} pose is relative_to {relative_to!r}; the viewer places a model in the world")
    frames = _SdfFrames(model_name, model_world)

    link_elements = children(model, "link")
    for link_element in link_elements:
        name = str(link_element.attrib.get("name") or "").strip()
        _declared, relative_to, _values, transform = _sdf_pose(link_element, where=f"{display} link {name!r}")
        frames.links.add(name)
        frames.add(name, {"kind": "link", "pose": transform, "relative_to": relative_to, "default": _SDF_MODEL_FRAME})
    frame_elements = children(model, "frame")
    for frame_element in frame_elements:
        name = str(frame_element.attrib.get("name") or "").strip()
        attached = frames.normalize(frame_element.attrib.get("attached_to"), _SDF_MODEL_FRAME)
        _declared, relative_to, _values, transform = _sdf_pose(frame_element, where=f"{display} frame {name!r}")
        frames.add(name, {"kind": "frame", "pose": transform, "relative_to": relative_to, "default": attached, "attached": attached})
    joint_elements = children(model, "joint")
    raw_joints: list[dict] = []
    for joint_element in joint_elements:
        name = str(joint_element.attrib.get("name") or "").strip()
        joint_type = str(joint_element.attrib.get("type") or "").strip().lower()
        if joint_type not in (*_MOVING, "fixed"):
            raise RobotReadError(f"{display} joint {name!r} is a {joint_type!r} joint; the viewer poses fixed, revolute, continuous and prismatic joints")
        parent_frame = frames.normalize(_sdf_text(joint_element, "parent"), "")
        child_frame = frames.normalize(_sdf_text(joint_element, "child"), "")
        _declared, relative_to, values, transform = _sdf_pose(joint_element, where=f"{display} joint {name!r}")
        frames.add(name, {"kind": "joint", "pose": transform, "relative_to": relative_to, "default": child_frame, "child": child_frame})
        axis_element = _sdf_first(joint_element, "axis")
        xyz_element = _sdf_first(axis_element, "xyz") if axis_element is not None else None
        axis = _numbers(xyz_element.text if xyz_element is not None else None, 3, where=f"{display} joint {name!r} axis", default=[0.0, 0.0, 1.0])
        expressed_in = str((xyz_element.attrib.get("expressed_in") if xyz_element is not None else None)
                           or (axis_element.attrib.get("expressed_in") if axis_element is not None else None) or "").strip()
        limit_element = _sdf_first(axis_element, "limit") if axis_element is not None else None
        limit: dict = {}
        for key in ("lower", "upper", "effort", "velocity"):
            value = _optional_numbers(_sdf_text(limit_element, key), 1) if limit_element is not None else None
            if value is not None:
                limit[key] = value[0]
        raw_joints.append({"name": name, "type": joint_type, "parent": parent_frame, "child": child_frame, "axis": axis,
                           "expressed_in": expressed_in, "limit": limit, "declared_limit": limit_element is not None,
                           "pose": values})

    links: dict[str, _Link] = {}
    undrawable: list[str] = []  # every visual the page cannot draw, named together
    for link_element in link_elements:
        link = _Link(str(link_element.attrib.get("name") or "").strip())
        link.placement = frames.world(link.name)
        inverse = _invert_rigid(link.placement)
        for index, visual_element in enumerate(children(link_element, "visual"), start=1):
            where = f"{display} link {link.name!r} visual {index}"
            facts = _sdf_shape_facts(visual_element, where=where)
            color = _sdf_color(visual_element)
            facts["color"], facts["materialName"] = color, ""
            _declared, relative_to, _values, pose = _sdf_pose(visual_element, where=where)
            local = _multiply(inverse, _multiply(frames.world(relative_to, link.name), pose))
            kind = facts["type"]
            try:
                if kind == "mesh":
                    uri = facts["filename"]
                    if not uri:
                        raise RobotReadError(f"{where} is a <mesh> with no <uri>, so there is nothing to load")
                    mesh = _resolve_sdf_mesh(uri, base_dir=path.parent, where=where)
                    facts["path"] = mesh["path"]
                    scale = _numbers(_sdf_text(_sdf_first(_sdf_first(visual_element, "geometry"), "mesh"), "scale"), 3,
                                     where=f"{where} mesh scale", default=[1.0, 1.0, 1.0])
                    local = _multiply(local, _scale(*scale))
                    label = PurePosixPath(uri).name or "mesh"
                elif kind in DRAWABLE_SHAPES:
                    dimensions = {key: facts[key] for key in ("size", "radius", "length") if facts.get(key) is not None}
                    if (kind == "box" and "size" not in dimensions) or (kind != "box" and "radius" not in dimensions) \
                            or (kind in ("cylinder", "capsule") and "length" not in dimensions):
                        raise RobotReadError(f"{where} is a <{kind}> with missing or non-positive dimensions; give it positive dimensions")
                    mesh = _primitive_mesh(kind, dimensions)
                    local = _multiply(local, _scale(_PRIMITIVE_SCALE, _PRIMITIVE_SCALE, _PRIMITIVE_SCALE))
                    label = kind
                else:
                    what = "has no <geometry>" if kind == "missing" else f"uses <{kind}> geometry, which the viewer cannot draw"
                    raise RobotReadError(f"{where} {what}. Supported: {', '.join(DRAWABLE_SHAPES)}, mesh. "
                                         "Replace it with one of those, or reference a mesh file.")
            except RobotReadError as exc:
                undrawable.append(str(exc))
                continue
            link.visuals.append(_Visual(f"{link.name}:v{index}", label, local, color, mesh, facts))
        link.collisions = [_sdf_shape_facts(element, where=f"{display} link {link.name!r} collision {index}")
                           for index, element in enumerate(children(link_element, "collision"), start=1)]
        links[link.name] = link
        description.links.append(link)
    if undrawable:
        raise RobotReadError("; ".join(undrawable))

    children_of: set[str] = set()
    for raw in raw_joints:
        parent_link = frames.attached_link(raw["parent"]) if raw["parent"] else ""
        child_link = frames.attached_link(raw["child"]) if raw["child"] else ""
        if not child_link:
            raise RobotReadError(f"{display} joint {raw['name']!r} child {raw['child']!r} is not attached to a link")
        if parent_link == child_link:
            raise RobotReadError(f"{display} joint {raw['name']!r} must connect different parent and child frames, not {child_link!r}")
        if child_link in children_of:
            raise RobotReadError(f"{display} link {child_link!r} has multiple parents")
        children_of.add(child_link)
        joint = _Joint(raw["name"], raw["type"], parent_link, child_link)
        joint.frame = frames.world(raw["name"])
        if joint.type != "fixed":
            axis_frame = frames.world(raw["expressed_in"], raw["name"])
            joint.axis = _unit(_rotate(axis_frame, raw["axis"]))
            if joint.axis is None:
                raise RobotReadError(f"{display} joint {raw['name']!r} axis must be nonzero")
            if joint.type != "continuous":
                joint.lower, joint.upper = raw["limit"].get("lower"), raw["limit"].get("upper")
        joint.facts = {
            "name": joint.name, "type": joint.type, "parent": parent_link, "child": child_link,
            "axis": None if joint.type == "fixed" else list(raw["axis"]),
            "origin": _described_origin(raw["pose"][:3], raw["pose"][3:]),
            "limit": raw["limit"] if raw["declared_limit"] else None,
            "mimic": None,
        }
        description.joints.append(joint)
    roots = [link.name for link in description.links if link.name not in children_of]
    description.root = roots[0] if len(roots) == 1 else ""
    description.sdf = {
        "version": version,
        "documentKind": document_kind,
        "worldName": world_name,
        "modelName": model_name,
        "rootLink": description.root,
        "rootLinks": roots,
        "frameCount": len(frame_elements),
        "linkCount": len(link_elements),
        "jointCount": len(joint_elements),
        "staticMetadata": _sdf_metadata(root),
    }
    return description


# --- SRDF ------------------------------------------------------------------------------------


def _robot_name_of(description: Path) -> str | None:
    """The root ``<robot name>`` of a URDF or SRDF, or None when it cannot be read."""
    try:
        for _event, element in ET.iterparse(str(description), events=("start",)):
            if local_name(element.tag) != "robot":
                return None
            return str(element.attrib.get("name") or "").strip() or None
    except (OSError, ET.ParseError):
        return None
    return None


def paired_urdf_for_srdf(srdf_path: Path) -> Path:
    """The URDF whose robot an SRDF plans for, or a refusal naming the search.

    An SRDF carries planning semantics only. It pairs with the same-folder ``.urdf``
    whose ``<robot name>`` matches -- the rule ``cadgen srdf validate`` and the CAD Viewer
    use -- and exactly one may match.
    """
    from cadgen.srdf_validation import find_paired_urdf

    folder = srdf_path.parent
    robot_name = _robot_name_of(srdf_path)
    rule = (
        "An SRDF renders the geometry of the same-folder .urdf whose <robot name> "
        "matches its own, and exactly one may match (check with `cadgen srdf validate`)."
    )
    if not robot_name:
        raise RobotReadError(f"{srdf_path.name} has no readable <robot name>, so its URDF cannot be found. {rule}")
    paired, matches = find_paired_urdf(robot_name, folder)
    if paired is not None:
        return paired
    if matches:
        raise RobotReadError(
            f"{srdf_path.name} is ambiguous: {len(matches)} .urdf files in {folder} declare "
            f"<robot name={robot_name!r}> ({', '.join(match.name for match in matches)}). {rule}"
        )
    try:
        candidates = sorted(entry for entry in folder.iterdir() if entry.suffix.lower() == ".urdf" and entry.is_file())
    except OSError:
        candidates = []
    found = (
        "; it holds " + ", ".join(
            f"{candidate.name} (robot {(_robot_name_of(candidate) or 'unreadable')!r})" for candidate in candidates[:6]
        ) + (f" and {len(candidates) - 6} more" if len(candidates) > 6 else "")
        if candidates
        else "; it holds no .urdf files"
    )
    raise RobotReadError(
        f"{srdf_path.name} has no paired URDF: no .urdf in {folder} declares <robot name={robot_name!r}>{found}. {rule}"
    )


def _read_srdf(path: Path, *, package_map: dict[str, Path] | None = None) -> _Description:
    from cadgen.srdf_source import parse_srdf_file
    from cadgen.srdf_validation import _link_names_for_group, read_urdf_robot, validate_srdf_against_urdf

    source, findings = parse_srdf_file(path)
    if findings.errors or source is None:
        raise RobotReadError(format_findings(findings.errors))
    urdf_path = paired_urdf_for_srdf(path)
    robot = read_urdf_robot(urdf_path, findings)
    if robot is None:
        raise RobotReadError(format_findings(findings.errors or findings.warnings))
    validate_srdf_against_urdf(source, urdf_robot=robot, result=findings)
    if findings.errors:
        raise RobotReadError(format_findings(findings.errors))
    description = _read_urdf(urdf_path, package_map=package_map)
    description.kind = "srdf"
    joints = {joint.name: joint for joint in description.joints}
    groups_by_name = {group.name: group for group in source.planning_groups}

    def control_units(joint_name: str, value: float) -> float:
        joint = joints.get(joint_name)
        return math.degrees(value) if joint is not None and joint.type in _ANGULAR else value

    states: list[dict] = []
    for state in source.group_states:
        state_id = f"{state.group}/{state.name}"
        values = {name: control_units(name, value) for name, value in state.joint_values_by_name.items()
                  if name in joints and joints[name].type in _MOVING and joints[name].mimic is None}
        description.poses[state_id] = values
        states.append({"id": state_id, "name": state.name, "group": state.group})
        if state.name.strip().lower() == "home":
            description.home.update(values)

    def tip_link(group_name: str) -> str:
        group = groups_by_name.get(group_name)
        if group is None:
            return ""
        if group.link_names:
            return group.link_names[-1]
        if group.chains:
            return group.chains[-1].tip_link
        return ""

    groups_by_link: dict[str, list[str]] = {}
    for group in source.planning_groups:
        for link_name in sorted(_link_names_for_group(group, urdf_robot=robot, groups_by_name=groups_by_name)):
            groups_by_link.setdefault(link_name, []).append(group.name)
    description.srdf = {
        "planningGroups": [
            {"name": group.name, "jointNames": list(group.joint_names), "linkNames": list(group.link_names),
             "chains": [{"baseLink": chain.base_link, "tipLink": chain.tip_link} for chain in group.chains],
             "subgroups": list(group.subgroups)}
            for group in source.planning_groups
        ],
        "endEffectors": [
            {"name": effector.name, "parentLink": effector.parent_link, "group": effector.group,
             "parentGroup": effector.parent_group, "link": tip_link(effector.group) or effector.parent_link}
            for effector in source.end_effectors
        ],
        "groupStates": states,
        "disabledCollisionPairs": [
            {"link1": pair.link1, "link2": pair.link2, "reason": pair.reason, "source": pair.source}
            for pair in source.disabled_collision_pairs
        ],
        "groupsByLink": groups_by_link,
    }
    return description


# --- the articulation --------------------------------------------------------------------------


def _tree_order(joints: list[_Joint]) -> list[_Joint]:
    """Parents first, declaration order otherwise."""
    by_child = {joint.child: joint for joint in joints}
    ordered: list[_Joint] = []
    placed: set[str] = set()

    def place(joint: _Joint, trail: tuple[str, ...]) -> None:
        if joint.name in placed:
            return
        if joint.name in trail:
            raise RobotReadError(f"joint graph contains a cycle at {joint.name!r}")
        parent = by_child.get(joint.parent)
        if parent is not None:
            place(parent, (*trail, joint.name))
        placed.add(joint.name)
        ordered.append(joint)

    for joint in joints:
        place(joint, ())
    return ordered


def _articulation(description: _Description) -> dict[str, Any]:
    joints = _tree_order(description.joints)
    by_name = {joint.name: joint for joint in joints}
    by_child = {joint.child: joint for joint in joints}

    def unit_of(joint: _Joint) -> str:
        return "deg" if joint.type in _ANGULAR else "m"

    def limits_of(joint: _Joint) -> tuple[float | None, float | None]:
        if joint.type in _ANGULAR:
            return (None if joint.lower is None else math.degrees(joint.lower),
                    None if joint.upper is None else math.degrees(joint.upper))
        return joint.lower, joint.upper

    def rounded(value: float | None) -> float | None:
        return None if value is None else _number(value)

    controls = []
    for joint in joints:
        if joint.type in _MOVING and joint.mimic is None:
            lower, upper = limits_of(joint)
            controls.append({"id": joint.name, "label": joint.name, "unit": unit_of(joint), "min": rounded(lower), "max": rounded(upper), "default": 0.0})
    control_ids = {control["id"] for control in controls}

    # A joint's value in its native unit (radians or metres) as an affine form over the
    # controls, in the controls' units: a driven joint is its own control, a follower its
    # leader's form scaled and offset. The mimic graph is acyclic (the validator refuses a cycle).
    forms: dict[str, tuple[float, dict[str, float]]] = {}

    def native_form(joint: _Joint) -> tuple[float, dict[str, float]]:
        if joint.name in forms:
            return forms[joint.name]
        if joint.mimic is None:
            form = (0.0, {joint.name: (math.pi / 180.0 if joint.type in _ANGULAR else 1.0)})
        else:
            leader_name, multiplier, offset = joint.mimic
            leader = by_name.get(leader_name)
            if leader is None or leader.type not in _MOVING:
                raise RobotReadError(f"joint {joint.name!r} mimics {leader_name!r}, which is not a moving joint")
            bias, weights = native_form(leader)
            form = (multiplier * bias + offset, {key: multiplier * weight for key, weight in weights.items()})
        forms[joint.name] = form
        return form

    def row_of(joint: _Joint) -> dict[str, Any]:
        if joint.mimic is None:
            return {"bias": 0.0, "terms": [[joint.name, 1.0]]}
        bias, weights = native_form(joint)
        convert = 180.0 / math.pi if joint.type in _ANGULAR else 1.0
        terms = []
        for control, weight in weights.items():
            leader = by_name[control]
            # Both angular or both linear: the unit conversions cancel exactly.
            same = (leader.type in _ANGULAR) == (joint.type in _ANGULAR)
            terms.append([control, weight * (180.0 / math.pi) if same and joint.type in _ANGULAR else weight * convert])
        return {"bias": bias * convert, "terms": terms}

    out_joints = []
    handles = []
    for joint in joints:
        entry: dict[str, Any] = {"id": joint.name, "parent": by_child[joint.parent].name if joint.parent in by_child else None,
                                 "kind": "fixed" if joint.type == "fixed" else ("slider" if joint.type == "prismatic" else "revolute")}
        if joint.type != "fixed":
            entry["origin"] = [_number(joint.frame[i][3]) for i in range(3)]
            entry["axis"] = [_number(value) for value in (joint.axis or [0.0, 0.0, 1.0])]
            dof = "turn" if joint.type in _ANGULAR else "travel"
            row = row_of(joint)
            row = {"bias": _number(row["bias"]), "terms": [[control, _number(weight)] for control, weight in row["terms"]]}
            entry[dof] = row
            lower, upper = limits_of(joint)
            # The one term's control is what a drag writes: a follower drives its leader.
            control, weight = row["terms"][0][0], row["terms"][0][1]
            handles.append({"id": joint.name, "joint": joint.name, "dof": dof, "control": control, "weight": weight,
                            "label": joint.name, "unit": unit_of(joint), "min": rounded(lower), "max": rounded(upper)})
        out_joints.append(entry)

    opening = {control["id"]: 0.0 for control in controls}
    opening.update({name: _number(value) for name, value in description.home.items() if name in control_ids})
    return {
        "schemaVersion": ARTICULATION_SCHEMA_VERSION,
        "controls": controls,
        "joints": out_joints,
        "carries": {joint.name: [joint.child] for joint in joints},
        "handles": handles,
        "poses": {name: {control: _number(value) for control, value in values.items() if control in control_ids}
                  for name, values in description.poses.items()},
        "opening": opening,
    }


# --- the payload -------------------------------------------------------------------------------


def _payload(description: _Description) -> dict[str, Any]:
    visuals = []
    for link in description.links:
        for visual in link.visuals:
            visuals.append({
                "id": visual.id, "link": link.name, "label": visual.label,
                "placement": _flat(_multiply(link.placement, visual.local)),
                "color": visual.color, "mesh": dict(visual.mesh),
            })
    return {
        "schemaVersion": ROBOT_PAYLOAD_SCHEMA_VERSION,
        "kind": description.kind,
        "name": description.name,
        "root": description.root,
        "articulation": _articulation(description),
        "links": [{"name": link.name, "placement": _flat(link.placement),
                   "visuals": [visual.facts for visual in link.visuals], "collisions": link.collisions,
                   "inertial": link.inertial} for link in description.links],
        "joints": [joint.facts for joint in description.joints],
        "visuals": visuals,
        "srdf": description.srdf,
        "sdf": description.sdf,
    }


def read_robot_description(path: Path | str, *, package_map: dict[str, Path] | None = None) -> dict[str, Any]:
    """The payload of the description at ``path`` (``.urdf``, ``.sdf`` or ``.srdf``), read
    now: validated through its format's validator, its frames resolved, its primitives meshed
    into the store. ``RobotReadError`` names what to change."""
    resolved = Path(path).expanduser().resolve()
    kind = resolved.suffix.lower()
    if kind not in ROBOT_SUFFIXES:
        raise RobotReadError(f"{resolved.name} is not a robot description: one of {', '.join(ROBOT_SUFFIXES)}")
    if not resolved.is_file():
        raise RobotReadError(f"no file is at {resolved}")
    if kind == ".urdf":
        description = _read_urdf(resolved, package_map=package_map)
    elif kind == ".sdf":
        description = _read_sdf(resolved)
    else:
        description = _read_srdf(resolved, package_map=package_map)
    return _payload(description)


def robot_payload_scheme() -> str:
    """What the payload's shape and its primitive meshes depend on, hashed into the index key."""
    return f"robot-payload-{ROBOT_PAYLOAD_SCHEMA_VERSION}-articulation-{ARTICULATION_SCHEMA_VERSION}-" \
           + json.dumps(DEFAULT_TESSELLATION, sort_keys=True)


def encode_robot_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mesh_objects(payload: Mapping[str, Any]) -> list[str]:
    return [str(visual["mesh"]["object"]) for visual in payload.get("visuals") or [] if visual.get("mesh", {}).get("object")]


def robot_payload_bytes(path: Path | str, *, rebuild: bool = False) -> bytes:
    """The payload's bytes: the store's cached ones for an unchanged description (and, for an
    SRDF, an unchanged paired URDF), else read now and published. ``rebuild`` reads now
    regardless, for a host whose cached payload names an object a sweep took."""
    from cadgen.store import robots

    resolved = Path(path).expanduser().resolve()
    if resolved.suffix.lower() not in ROBOT_SUFFIXES:
        raise RobotReadError(f"{resolved.name} is not a robot description: one of {', '.join(ROBOT_SUFFIXES)}")
    if not resolved.is_file():
        raise RobotReadError(f"no file is at {resolved}")
    paired = paired_urdf_for_srdf(resolved) if resolved.suffix.lower() == ".srdf" else None
    try:
        key = robots.robot_input_key(str(resolved), _file_hash(resolved), _file_hash(paired) if paired else None,
                                     scheme=robot_payload_scheme())
    except OSError as exc:
        raise RobotReadError(f"{resolved} could not be read: {exc}") from None
    if not rebuild:
        cached = robots.read(key)
        if cached is not None:
            return cached
    payload = read_robot_description(resolved)
    data = encode_robot_payload(payload)
    robots.write(key, data, meshes=_mesh_objects(payload))
    return data


def robot_payload(path: Path | str) -> dict[str, Any]:
    """:func:`robot_payload_bytes`, decoded."""
    return json.loads(robot_payload_bytes(path).decode("utf-8"))


def locate_robot_payload(
    payload: Mapping[str, Any], *, file_url: Callable[[str], str], object_url: Callable[[str], str],
) -> dict[str, Any]:
    """The payload as a host serves it: every visual's mesh named by the URL that host answers
    for it -- ``file_url(absolute path)`` for a mesh file, ``object_url(hash)`` for a primitive."""
    located = copy.deepcopy(dict(payload))
    for visual in located.get("visuals") or []:
        mesh = dict(visual.get("mesh") or {})
        if mesh.get("object"):
            visual["mesh"] = {"format": mesh.get("format", "glb"), "url": object_url(str(mesh["object"]))}
        else:
            visual["mesh"] = {"format": mesh.get("format", ""), "url": file_url(str(mesh.get("path") or ""))}
    return located


# --- a job's control vector --------------------------------------------------------------------


def _format(value: float) -> str:
    return f"{value:g}"


def robot_control_values(payload: Mapping[str, Any], request: object) -> dict[str, float]:
    """The full control vector a ``jointValues`` request means: every control, the ones the
    request names at their values and the rest at the opening. A value for a joint that is not
    a control is refused by name (a fixed joint has no value; a mimic follower is set through its
    leader), as is a value outside a control's limits and a leader value that puts a follower
    outside the follower's own limits."""
    articulation = payload.get("articulation") or {}
    controls = {str(control["id"]): control for control in articulation.get("controls") or []}
    rows = {str(joint["id"]): joint for joint in articulation.get("joints") or []}
    kind = str(payload.get("kind") or "robot").upper()
    values = {name: float(control.get("default") or 0.0) for name, control in controls.items()}
    values.update({name: float(value) for name, value in (articulation.get("opening") or {}).items() if name in values})
    if request is None:
        return values
    if not isinstance(request, Mapping):
        raise RobotReadError("jointValues must be an object of joint name to value")
    for name, value in request.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise RobotReadError(f"jointValues[{name}] must be a number (degrees, or metres for a prismatic joint)")
    unknown = sorted(str(name) for name in request if str(name) not in controls and str(name) not in rows)
    if unknown:
        raise RobotReadError(
            f"Unknown joint(s): {', '.join(unknown)}. This {kind} declares: {', '.join(sorted(controls)) or '(none)'}"
        )
    for name, value in request.items():
        name = str(name)
        if name not in controls:
            joint = rows[name]
            if joint.get("kind") == "fixed":
                raise RobotReadError(f"jointValues[{name}]: joint {name!r} is fixed, so it has no value to set; drop it")
            row = joint.get("turn") or joint.get("travel") or {}
            (leader, weight), bias = (row.get("terms") or [[name, 1.0]])[0], float(row.get("bias") or 0.0)
            raise RobotReadError(
                f"jointValues[{name}]: joint {name!r} mimics {leader!r} ({name} = {_format(float(weight))} × {leader}"
                f"{f' + {_format(bias)}' if bias else ''}), so it is posed by {leader!r}'s value; set jointValues[{leader}] instead"
            )
        control = controls[name]
        lo, hi, unit = control.get("min"), control.get("max"), str(control.get("unit") or "")
        if lo is not None and hi is not None:
            # Degrees converted from radians carry rounding: a value written as the limit itself must pass.
            tolerance = 1e-9 * max(1.0, abs(float(lo)), abs(float(hi)))
            if not float(lo) - tolerance <= float(value) <= float(hi) + tolerance:
                raise RobotReadError(
                    f"jointValues[{name}] = {_format(float(value))} {unit} is outside joint {name!r}'s "
                    f"limits [{_format(float(lo))}, {_format(float(hi))}] {unit}; pass a value within them"
                )
        values[name] = float(value)
    # A leader's value puts each follower somewhere: refuse one that lands outside the follower's limits.
    for handle in articulation.get("handles") or []:
        joint_id = str(handle.get("id") or "")
        if joint_id in controls or handle.get("min") is None or handle.get("max") is None:
            continue
        row = rows.get(joint_id, {}).get(str(handle.get("dof") or "turn")) or {}
        value = float(row.get("bias") or 0.0) + sum(float(weight) * values.get(str(control), 0.0) for control, weight in row.get("terms") or [])
        lo, hi, unit = float(handle["min"]), float(handle["max"]), str(handle.get("unit") or "")
        tolerance = 1e-9 * max(1.0, abs(lo), abs(hi))
        if not lo - tolerance <= value <= hi + tolerance:
            leader = str(handle.get("control") or "")
            if leader not in request:
                continue
            raise RobotReadError(
                f"jointValues[{leader}] = {_format(values[leader])} {unit} puts joint {joint_id!r}, which mimics "
                f"{leader!r}, at {_format(value)} {unit}, outside its limits [{_format(lo)}, {_format(hi)}] {unit}; "
                f"pass a value that keeps it within them"
            )
    return values

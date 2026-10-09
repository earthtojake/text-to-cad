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
      "schemaVersion": 2,
      "kind": "urdf" | "sdf" | "srdf",
      "name": the robot's (an SDF model's) name,
      "root": the root link; "" for an SDF model whose links float free,
      "articulation": the articulation (``cadgen.articulation``), whose ``carries`` name links,
      "links": [{"name", "placement", "visuals": [facts], "collisions": [facts], "inertial"}],
      "joints": [{"name", "type", "parent", "child", "axis", "origin", "limit", "mimic", "fourBar"}],
      "visuals": [{"id", "link", "label", "placement", "color", "mesh": {"format", ...}}],
      "srdf": the planning semantics the SRDF declares, or null,
      "sdf": what an SDF says about itself beyond its links and joints, or null,
    }

- ``placement`` is a row-major 4x4 in the robot's REST space (the description as written,
  every joint at zero): a link's is its frame, a visual's its mesh's -- the link frame, the
  visual's origin and the mesh's scale composed, so the page sets it on a mesh and nothing
  else. A link's visuals sit under the joint that carries the link; the joint's delta
  (``articulation.joint_matrices``) moves them. A visual's ``id`` is ``<link>:v<n>`` and its
  ``label`` what a row calls it: the ``name`` the description gave it, else its geometry (the
  mesh file's name, or ``box``, ``cylinder``, ``sphere``, ``capsule``).
- A control is a joint a person or a job sets: revolute and continuous joints in DEGREES,
  prismatic joints in METRES, each at its declared limits (a continuous joint has none). A
  mimic follower is not a control: its row is its leader's, scaled and offset, so one value
  moves both. ``poses`` are an SRDF's group states (``<group>/<name>``), ``opening`` every
  control at rest with the SRDF's ``home`` state(s) over it.
- A URDF joint carrying ``<tcad:four_bar>`` (the urdf skill's authoring contract: the input
  crank of a planar four-bar linkage, derived from the ``driver`` joint on the same ground
  link) is not a control either, and has no handle: its row is a ``curve`` over the driver's
  row (``cadgen.articulation``), sampled here from the linkage's closed form over the
  driver's whole operating range -- its declared limits, or one turn for a continuous driver
  -- densely enough that the page's linear interpolation stays within
  ``FOUR_BAR_CURVE_TOLERANCE_DEG``. The linkage's geometry (one ground link, parallel axes,
  pivots ``ground_length`` apart, the range reachable, the derived range within the joint's
  limits) is checked here, and refused in words; the page solves nothing.
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
    "FOUR_BAR_CURVE_TOLERANCE_DEG",
    "ROBOT_PAYLOAD_SCHEMA_VERSION",
    "ROBOT_SUFFIXES",
    "RobotReadError",
    "four_bar_input_angle",
    "locate_robot_payload",
    "paired_urdf_for_srdf",
    "read_robot_description",
    "robot_control_values",
    "robot_payload",
    "robot_payload_bytes",
    "robot_payload_scheme",
]

ROBOT_PAYLOAD_SCHEMA_VERSION = 2
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

#: The interpolation error a four-bar curve is sampled down to, in degrees of the derived
#: joint: the page plays the curve linearly between its keys, and cadgen halves every
#: interval whose midpoint it misses by more than this (to ``_FOUR_BAR_MAX_KEYS`` keys). On a
#: crank of length L the pin then lands within L * 1.7e-4 of the exact closure -- 17 µm on a
#: 100 mm crank, under a screen pixel at any zoom that shows the crank whole.
FOUR_BAR_CURVE_TOLERANCE_DEG = 0.01
_FOUR_BAR_INITIAL_INTERVALS = 64
_FOUR_BAR_MAX_KEYS = 2049
# The closed form's tolerances, as the urdf skill's authoring contract has them.
_FOUR_BAR_INTERSECTION_TOLERANCE = 1e-12
_FOUR_BAR_AXIS_ALIGNMENT_TOLERANCE = 1e-9
_FOUR_BAR_GEOMETRY_ABSOLUTE_TOLERANCE_M = 1e-9
_FOUR_BAR_GEOMETRY_RELATIVE_TOLERANCE = 1e-8
_FOUR_BAR_JOINT_LIMIT_TOLERANCE_DEG = 1e-6
_FOUR_BAR_ZERO_POSE_TOLERANCE_RAD = 1e-7


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
    __slots__ = ("name", "type", "parent", "child", "frame", "axis", "lower", "upper", "mimic", "four_bar", "facts")

    def __init__(self, name: str, joint_type: str, parent: str, child: str) -> None:
        self.name, self.type, self.parent, self.child = name, joint_type, parent, child
        self.frame: list[list[float]] = _IDENTITY  # the joint's rest frame in the robot's space
        self.axis: list[float] | None = None  # unit, in the robot's rest space
        self.lower: float | None = None  # native units: radians or metres
        self.upper: float | None = None
        self.mimic: tuple[str, float, float] | None = None  # (leader, multiplier, offset)
        self.four_bar: dict[str, Any] | None = None  # the <tcad:four_bar> element's numbers and driver
        self.facts: dict = {}


class _Description:
    def __init__(self, kind: str, name: str, display: str = "") -> None:
        self.kind, self.name, self.display = kind, name, display
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


def _four_bar_element(joint_element: ET.Element) -> dict[str, Any] | None:
    """The joint's ``<tcad:four_bar>`` as numbers, or None. The validator refused one with a
    length that is not positive, a zero angle that is not a number, or no driver."""
    from cadgen.urdf_source import FOUR_BAR_LENGTHS, FOUR_BAR_TAG, FOUR_BAR_ZEROS

    element = joint_element.find(FOUR_BAR_TAG)
    if element is None:
        return None
    numbers = {name: _optional_number(element, name) for name in (*FOUR_BAR_LENGTHS, *FOUR_BAR_ZEROS)}
    return {"driver": str(element.attrib.get("driver") or "").strip(),
            **{name: (0.0 if value is None else value) for name, value in numbers.items()}}


def _four_bar_facts(four_bar: dict[str, Any] | None) -> dict[str, Any] | None:
    if four_bar is None:
        return None
    return {"driver": four_bar["driver"], "inputLength": four_bar["input_length"], "groundLength": four_bar["ground_length"],
            "outputLength": four_bar["output_length"], "couplerLength": four_bar["coupler_length"],
            "inputZero": four_bar["input_zero"], "outputZero": four_bar["output_zero"]}


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
    description = _Description("urdf", source.robot_name, display)
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
            # The visual's own name is what its author called it, and what tells several visuals
            # of one link apart; without one, it is named for its geometry.
            link.visuals.append(_Visual(f"{link.name}:v{index}", facts["name"] or label, local, color, mesh, facts))
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
        joint.four_bar = _four_bar_element(joint_element)
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
            "fourBar": _four_bar_facts(joint.four_bar),
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
    description = _Description("sdf", model_name, display)
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
            "fourBar": None,
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


# --- the four-bar linkage --------------------------------------------------------------------
#
# The planar four-bar the urdf skill's authoring contract describes: the ground link runs from
# the input pivot (the derived joint's) to the output pivot (the driver's), ``ground_length``
# apart along the x axis of a plane whose normal is the joints' shared axis; ``input_zero`` and
# ``output_zero`` are the crank's and the rocker's angles from that x axis when both joints are
# at zero. The coupler closes the loop between the two pins, so the crank's angle at a driver
# angle is a circle-circle intersection: two candidates, of which the one the zero pose
# describes (the ``branch``) is the linkage as assembled.


def _wrap_angle(value: float) -> float:
    """``value`` in (-pi, pi]."""
    wrapped = (value + math.pi) % (2.0 * math.pi) - math.pi
    return math.pi if wrapped == -math.pi and value > 0 else wrapped


def _four_bar_candidates(four_bar: Mapping[str, float], driver_rad: float) -> tuple[float, float]:
    """The crank's two possible angles (radians from the ground direction) at a driver angle."""
    output_angle = four_bar["output_zero"] + driver_rad
    pin_x = four_bar["ground_length"] + four_bar["output_length"] * math.cos(output_angle)
    pin_y = four_bar["output_length"] * math.sin(output_angle)
    distance = math.hypot(pin_x, pin_y)
    crank, coupler = four_bar["input_length"], four_bar["coupler_length"]
    if distance <= _FOUR_BAR_INTERSECTION_TOLERANCE:
        raise RobotReadError("the output pin coincides with the input pivot")
    if distance < abs(crank - coupler) - _FOUR_BAR_INTERSECTION_TOLERANCE or distance > crank + coupler + _FOUR_BAR_INTERSECTION_TOLERANCE:
        raise RobotReadError("the lengths cannot close at this driver angle")
    along = (crank * crank - coupler * coupler + distance * distance) / (2.0 * distance)
    height = math.sqrt(max(0.0, crank * crank - along * along))
    unit_x, unit_y = pin_x / distance, pin_y / distance
    base_x, base_y = along * unit_x, along * unit_y
    return (math.atan2(base_y + height * unit_x, base_x - height * unit_y),
            math.atan2(base_y - height * unit_x, base_x + height * unit_y))


def four_bar_input_angle(four_bar: Mapping[str, float], driver_rad: float) -> float:
    """The derived joint's value (radians, in (-pi, pi]) at a driver angle, on the assembly
    branch ``four_bar["branch"]`` (0 or 1: the candidate the zero angles describe). The
    closed form every key of a four-bar curve is sampled from; ``RobotReadError`` where the
    linkage cannot close."""
    candidates = _four_bar_candidates(four_bar, driver_rad)
    return _wrap_angle(candidates[1 if four_bar.get("branch") == 1 else 0] - four_bar["input_zero"])


def _four_bar_branch(four_bar: Mapping[str, float]) -> int:
    first, second = _four_bar_candidates(four_bar, 0.0)
    errors = (abs(_wrap_angle(first - four_bar["input_zero"])), abs(_wrap_angle(second - four_bar["input_zero"])))
    return 0 if errors[0] <= errors[1] else 1


def _four_bar_geometry(joint: _Joint, driver: _Joint, *, where: str) -> None:
    """One ground link, parallel same-direction axes, coplanar pivots ``ground_length`` apart:
    what the joint frames must say for the planar closed form to describe them."""
    assert joint.four_bar is not None
    if joint.parent != driver.parent:
        raise RobotReadError(f"{where} and its driver {driver.name!r} must share one ground link (parents {joint.parent!r} and {driver.parent!r})")
    if joint.axis is None or driver.axis is None:
        raise RobotReadError(f"{where} and its driver {driver.name!r} must both turn about an axis")
    alignment = sum(a * b for a, b in zip(joint.axis, driver.axis))
    if alignment < 1.0 - _FOUR_BAR_AXIS_ALIGNMENT_TOLERANCE:
        raise RobotReadError(f"{where} and its driver {driver.name!r} must turn about parallel, same-direction axes")
    delta = [driver.frame[i][3] - joint.frame[i][3] for i in range(3)]
    axial = sum(d * a for d, a in zip(delta, joint.axis))
    planar = math.hypot(*(d - axial * a for d, a in zip(delta, joint.axis)))
    expected = joint.four_bar["ground_length"]
    tolerance = _FOUR_BAR_GEOMETRY_ABSOLUTE_TOLERANCE_M + _FOUR_BAR_GEOMETRY_RELATIVE_TOLERANCE * max(abs(planar), abs(expected))
    if abs(axial) > tolerance:
        raise RobotReadError(f"{where}: its pivot and its driver {driver.name!r}'s are not coplanar ({axial:g} m apart along the axis)")
    if abs(planar - expected) > tolerance:
        raise RobotReadError(f"{where} declares ground_length {expected:g}, but its pivot and its driver {driver.name!r}'s are {planar:g} metres apart")


def _range_contains_periodic(lower: float, upper: float, target: float) -> bool:
    first = math.ceil((lower - target) / (2.0 * math.pi))
    return target + first * 2.0 * math.pi <= upper + _FOUR_BAR_INTERSECTION_TOLERANCE


def _four_bar_reachable(four_bar: Mapping[str, float], lower_rad: float, upper_rad: float, *, where: str, driver: str) -> None:
    """The whole driver range closes: the output pin's distance from the input pivot stays
    within the crank's and the coupler's reach, checked in closed form over the range."""
    low, high = four_bar["output_zero"] + lower_rad, four_bar["output_zero"] + upper_rad
    ends = (math.cos(low), math.cos(high))
    cos_min = -1.0 if _range_contains_periodic(low, high, math.pi) else min(ends)
    cos_max = 1.0 if _range_contains_periodic(low, high, 0.0) else max(ends)
    base = four_bar["ground_length"] ** 2 + four_bar["output_length"] ** 2
    scale = 2.0 * four_bar["ground_length"] * four_bar["output_length"]
    nearest = math.sqrt(max(0.0, base + scale * cos_min))
    farthest = math.sqrt(max(0.0, base + scale * cos_max))
    reach_min = abs(four_bar["input_length"] - four_bar["coupler_length"])
    reach_max = four_bar["input_length"] + four_bar["coupler_length"]
    if (nearest <= _FOUR_BAR_INTERSECTION_TOLERANCE or nearest < reach_min - _FOUR_BAR_INTERSECTION_TOLERANCE
            or farthest > reach_max + _FOUR_BAR_INTERSECTION_TOLERANCE):
        raise RobotReadError(
            f"{where}: its driver {driver!r}'s range [{math.degrees(lower_rad):g}, {math.degrees(upper_rad):g}] deg includes angles "
            "where the linkage cannot close; narrow the driver's limits or correct the lengths"
        )


def _four_bar_curve(joint: _Joint, driver: _Joint, *, where: str) -> dict[str, Any]:
    """The derived joint's value over the driver's whole operating range, sampled from the
    closed form: ``{"input": driver degrees ascending, "output": derived radians, "period"?}``.
    Every interval the page's linear interpolation would miss by more than
    ``FOUR_BAR_CURVE_TOLERANCE_DEG`` at its midpoint is halved, up to ``_FOUR_BAR_MAX_KEYS``
    keys; the output is unwrapped into one continuous branch, so no interval crosses the
    (-pi, pi] seam. A derived joint with limits must stay within them over the range."""
    four_bar = joint.four_bar
    assert four_bar is not None
    if driver.type == "continuous" or driver.lower is None or driver.upper is None:
        lower, upper, period = -math.pi, math.pi, 360.0
    else:
        lower, upper, period = driver.lower, driver.upper, None
    if upper < lower:
        raise RobotReadError(f"{where}: its driver {driver.name!r} has no operating range (limit lower {lower:g} > upper {upper:g})")
    _four_bar_reachable(four_bar, lower, upper, where=where, driver=driver.name)

    def sample(x: float) -> float:
        try:
            return four_bar_input_angle(four_bar, x)
        except RobotReadError as exc:
            raise RobotReadError(f"{where} cannot close at driver angle {math.degrees(x):g} deg: {exc}") from None

    def near(value: float, reference: float) -> float:
        """``value`` plus the turn count that brings it within half a turn of ``reference``."""
        return value + 2.0 * math.pi * round((reference - value) / (2.0 * math.pi))

    keys: dict[float, float] = {}
    grid = [lower + (upper - lower) * index / _FOUR_BAR_INITIAL_INTERVALS for index in range(_FOUR_BAR_INITIAL_INTERVALS + 1)]
    if lower < 0.0 < upper:
        grid.append(0.0)  # the zero pose is a key, so the robot as written is exactly q = 0
    for x in grid:
        keys[x] = sample(x)
    tolerance = math.radians(FOUR_BAR_CURVE_TOLERANCE_DEG)

    def refine(x0: float, x1: float, depth: int) -> None:
        if len(keys) >= _FOUR_BAR_MAX_KEYS or depth == 0:
            return
        y0, y1 = keys[x0], keys[x1]
        xm = (x0 + x1) / 2.0
        ym = sample(xm)
        if abs(near(ym, y0) - (y0 + near(y1, y0)) / 2.0) <= tolerance:
            return
        keys[xm] = ym
        refine(x0, xm, depth - 1)
        refine(xm, x1, depth - 1)

    ordered = sorted(keys)
    depth = max(1, math.ceil(math.log2(_FOUR_BAR_MAX_KEYS / _FOUR_BAR_INITIAL_INTERVALS)))
    for x0, x1 in zip(ordered, ordered[1:]):
        refine(x0, x1, depth)

    ordered = sorted(keys)
    wrapped = [keys[x] for x in ordered]
    if joint.type != "continuous" and joint.lower is not None and joint.upper is not None:
        low_deg, high_deg = math.degrees(min(wrapped)), math.degrees(max(wrapped))
        if low_deg < math.degrees(joint.lower) - _FOUR_BAR_JOINT_LIMIT_TOLERANCE_DEG or high_deg > math.degrees(joint.upper) + _FOUR_BAR_JOINT_LIMIT_TOLERANCE_DEG:
            raise RobotReadError(
                f"{where} derives {low_deg:g} to {high_deg:g} deg over its driver {driver.name!r}'s range, outside its own limits "
                f"[{math.degrees(joint.lower):g}, {math.degrees(joint.upper):g}] deg; widen them to contain the derived range"
            )
    unwrapped: list[float] = []
    for value in wrapped:
        unwrapped.append(value if not unwrapped else near(value, unwrapped[-1]))
    if 0.0 in keys:
        unwrapped[ordered.index(0.0)] = 0.0
    curve: dict[str, Any] = {"input": [math.degrees(x) for x in ordered], "output": unwrapped}
    if period is not None:
        curve["period"] = period
    return curve


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
        if joint.type in _MOVING and joint.mimic is None and joint.four_bar is None:
            lower, upper = limits_of(joint)
            controls.append({"id": joint.name, "label": joint.name, "unit": unit_of(joint), "min": rounded(lower), "max": rounded(upper), "default": 0.0})
    control_ids = {control["id"] for control in controls}

    # A joint's value in its native unit (radians or metres) as an affine form over the
    # controls, in the controls' units, plus a curve: a driven joint is its own control, a
    # follower its leader's form scaled and offset, a four-bar's crank a curve over its driver's
    # row. The mimic graph is acyclic (the validator refuses a cycle, a four-bar's driver edge
    # included).
    forms: dict[str, tuple[float, dict[str, float], dict[str, Any] | None]] = {}

    def native_form(joint: _Joint) -> tuple[float, dict[str, float], dict[str, Any] | None]:
        if joint.name in forms:
            return forms[joint.name]
        if joint.four_bar is not None:
            where = f"{description.display} joint {joint.name!r} tcad:four_bar"
            driver = by_name.get(joint.four_bar["driver"])
            if driver is None or driver.type not in _ANGULAR:
                raise RobotReadError(f"{where} driver {joint.four_bar['driver']!r} is not a revolute or continuous joint")
            if joint.type not in _ANGULAR:
                raise RobotReadError(f"{where} needs a revolute or continuous joint, not {joint.type!r}")
            _four_bar_geometry(joint, driver, where=where)
            four_bar = {**joint.four_bar}
            four_bar["branch"] = _four_bar_branch(four_bar)
            if abs(four_bar_input_angle(four_bar, 0.0)) > _FOUR_BAR_ZERO_POSE_TOLERANCE_RAD:
                raise RobotReadError(f"{where} zero angles do not describe an assembly branch the lengths close at")
            joint.four_bar = four_bar
            form = (0.0, {}, {"driver": row_of(driver), **_four_bar_curve(joint, driver, where=where)})
        elif joint.mimic is None:
            form = (0.0, {joint.name: (math.pi / 180.0 if joint.type in _ANGULAR else 1.0)}, None)
        else:
            leader_name, multiplier, offset = joint.mimic
            leader = by_name.get(leader_name)
            if leader is None or leader.type not in _MOVING:
                raise RobotReadError(f"joint {joint.name!r} mimics {leader_name!r}, which is not a moving joint")
            bias, weights, curve = native_form(leader)
            scaled = None if curve is None else {**curve, "output": [multiplier * value for value in curve["output"]]}
            form = (multiplier * bias + offset, {key: multiplier * weight for key, weight in weights.items()}, scaled)
            if scaled is not None and joint.type != "continuous" and joint.lower is not None and joint.upper is not None:
                # A follower of a crank is where the scaled curve puts it over the driver's whole range
                # (a crank's form has no affine part): held to its own limits here, as the crank is to
                # its, since nothing clamps it later.
                low, high = min(scaled["output"]) + form[0], max(scaled["output"]) + form[0]
                tolerance = math.radians(_FOUR_BAR_JOINT_LIMIT_TOLERANCE_DEG)
                if low < joint.lower - tolerance or high > joint.upper + tolerance:
                    raise RobotReadError(
                        f"{description.display} joint {joint.name!r} mimics {leader_name!r}, the crank of a four-bar linkage, and reaches "
                        f"{math.degrees(low):g} to {math.degrees(high):g} deg over its driver's range, outside its own limits "
                        f"[{math.degrees(joint.lower):g}, {math.degrees(joint.upper):g}] deg; widen them to contain that range"
                    )
        forms[joint.name] = form
        return form

    def row_of(joint: _Joint) -> dict[str, Any]:
        if joint.mimic is None and joint.four_bar is None:
            return {"bias": 0.0, "terms": [[joint.name, 1.0]]}
        bias, weights, curve = native_form(joint)
        convert = 180.0 / math.pi if joint.type in _ANGULAR else 1.0
        terms = []
        for control, weight in weights.items():
            leader = by_name[control]
            # Both angular or both linear: the unit conversions cancel exactly.
            same = (leader.type in _ANGULAR) == (joint.type in _ANGULAR)
            terms.append([control, weight * (180.0 / math.pi) if same and joint.type in _ANGULAR else weight * convert])
        row: dict[str, Any] = {"bias": bias * convert, "terms": terms}
        if curve is not None:
            row["curve"] = {**curve, "output": [value * convert for value in curve["output"]]}
        return row

    def emitted(row: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"bias": _number(row["bias"]), "terms": [[control, _number(weight)] for control, weight in row["terms"]]}
        if "curve" in row:
            curve = row["curve"]
            out["curve"] = {"driver": emitted(curve["driver"]), "input": [_number(x) for x in curve["input"]],
                            "output": [_number(y) for y in curve["output"]]}
            if curve.get("period") is not None:
                out["curve"]["period"] = _number(curve["period"])
        return out

    out_joints = []
    handles = []
    for joint in joints:
        entry: dict[str, Any] = {"id": joint.name, "parent": by_child[joint.parent].name if joint.parent in by_child else None,
                                 "kind": "fixed" if joint.type == "fixed" else ("slider" if joint.type == "prismatic" else "revolute")}
        if joint.type != "fixed":
            entry["origin"] = [_number(joint.frame[i][3]) for i in range(3)]
            entry["axis"] = [_number(value) for value in (joint.axis or [0.0, 0.0, 1.0])]
            dof = "turn" if joint.type in _ANGULAR else "travel"
            row = emitted(row_of(joint))
            entry[dof] = row
            lower, upper = limits_of(joint)
            # The one term's control is what a drag writes: a follower drives its leader. A row
            # that follows a curve (a four-bar's crank, or a mimic of one) has no inverse to write
            # through, so it has no handle: its driver's knob moves it.
            if row["terms"] and "curve" not in row:
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
    leader; a four-bar's crank through its driver), as is a value outside a control's limits --
    which, for a four-bar's driver, is the range the linkage was solved over -- and a leader
    value that puts a follower outside the follower's own limits."""
    articulation = payload.get("articulation") or {}
    controls = {str(control["id"]): control for control in articulation.get("controls") or []}
    rows = {str(joint["id"]): joint for joint in articulation.get("joints") or []}
    facts_by_name = {str(joint.get("name")): joint for joint in payload.get("joints") or [] if isinstance(joint, Mapping)}
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
            facts = facts_by_name.get(name) or {}
            four_bar = facts.get("fourBar")
            if isinstance(four_bar, Mapping) and four_bar.get("driver"):
                driver = str(four_bar["driver"])
                raise RobotReadError(
                    f"jointValues[{name}]: joint {name!r} is the crank of a four-bar linkage (tcad:four_bar) driven by {driver!r}, "
                    f"so it is posed by {driver!r}'s value; set jointValues[{driver}] instead"
                )
            row = joint.get("turn") or joint.get("travel") or {}
            terms, bias = row.get("terms") or [], float(row.get("bias") or 0.0)
            leader = str((facts.get("mimic") or {}).get("joint") or (terms[0][0] if terms else name))
            formula = f" ({name} = {_format(float(terms[0][1]))} × {leader}{f' + {_format(bias)}' if bias else ''})" if terms else ""
            raise RobotReadError(
                f"jointValues[{name}]: joint {name!r} mimics {leader!r}{formula}, so it is posed by {leader!r}'s value; "
                f"set jointValues[{leader}] instead"
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

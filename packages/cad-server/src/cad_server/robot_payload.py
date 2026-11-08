"""A robot description resolved into what a page plays and draws.

A URDF, an SDF, an MJCF (MuJoCo's XML), or an SRDF with the URDF it plans for, becomes ONE payload: the robot's
articulation (below: controls per movable joint, joints in their rest frames with affine
rows over the controls, which link each joint carries, what a drag writes, the named poses
and the opening pose), the list of visuals to draw (each with its rest placement, its colour
and the mesh it draws), and what the description says about its links and joints, as
written, for a person reading it back. The page builds a scene from the visual list and
plays the articulation; it parses no XML, resolves no frame, meshes no shape and decides no
limit.

The description is read once, in the engine -- a URDF and an SRDF's group states over it by
``cad.engine.urdf_source``, an SDF by ``cad.engine.sdf_source``, an MJCF by ``cad.engine.mjcf_source``,
each into ``cad.engine.robot_model``'s articulation (every link's frame at rest, its visuals, its joints
with their mimics and four-bars, its named poses, the facts as written) -- and the payload is the
page's view of that read, as the OCCT stills (``cad.engine.formats.robot``) are theirs: it turns each
visual into a mesh the page decodes, carries the mesh's scale in its placement, rounds every number
and adds the articulation's rows. Where the payload and the stills have read a detail differently, the
payload's ``Dialect`` keeps the viewer's (``_URDF``, ``_SDF``).

The articulation (``ARTICULATION_SCHEMA_VERSION``) is played with closed-form arithmetic and
nothing else::

    {
      "schemaVersion": 2,
      "controls": [{"id", "label", "unit", "min", "max", "default"}],
      "joints":   [{"id", "parent", "kind", "origin", "axis",
                    "turn": {"bias", "terms", "curve"?}, "travel": {"bias", "terms", "curve"?}}],
      "carries":  {joint id: [link, ...]},
      "handles":  [{"id", "joint", "dof", "control", "weight", "label", "unit", "min", "max"}],
      "poses":    {name: {control id: value}},
      "opening":  {control id: value},
    }

``joints`` are listed parents first, each ``origin`` and ``axis`` (unit) in REST space, its
motion a displacement about that axis from rest carried by its parent joint's motion;
``turn`` (degrees) and ``travel`` (metres) are affine rows over the controls (``bias +
sum(weight * control)``), and a row may carry a ``curve``: a sampled function of another
row's value (``driver``, ``input`` ascending, ``output``; linear between keys, held beyond,
``period`` folding a driver that turns without limits). A ``fixed`` joint has no row.
``carries`` names the links each joint moves, every link under exactly one joint. ``handles``
are what a drag takes hold of: the control a gesture writes and its weight in the row.

The payload::

    {
      "schemaVersion": 2,
      "kind": "urdf" | "sdf" | "srdf" | "mjcf",
      "name": the robot's (an SDF model's) name,
      "root": the root link; "" for an SDF model whose links float free,
      "articulation": the articulation (above), whose ``carries`` name links,
      "links": [{"name", "placement", "visuals": [facts], "collisions": [facts], "inertial"}],
      "joints": [{"name", "type", "parent", "child", "axis", "origin", "limit", "mimic", "fourBar"}],
      "visuals": [{"id", "link", "label", "placement", "color", "mesh": {"format", ...}}],
      "srdf": the planning semantics the SRDF declares, or null,
      "sdf": what an SDF says about itself beyond its links and joints, or null,
    }

- ``placement`` is a row-major 4x4 in the robot's REST space (the description as written,
  every joint at zero): a link's is its frame, a visual's its mesh's -- the link frame, the
  visual's origin and the mesh's scale composed, so the page sets it on a mesh and nothing
  else. A link's visuals sit under the joint that carries the link, and the joint's delta
  moves them. A visual's ``id`` is ``<link>:v<n>`` and its
  ``label`` what a row calls it: the ``name`` the description gave it, else its geometry (the
  mesh file's name, or ``box``, ``cylinder``, ``sphere``, ``capsule``).
- An SDF model's nested models (SDFormat 1.6+) are part of the robot: their links, frames
  and joints are named by scope (``arm::elbow``, ``arm::hand::palm``), a name written in a
  nested model resolves in that model's namespace, a nested model is posed in the model it is
  nested in and attached to its ``canonical_link`` (else its first link), and a joint outside
  it names its links by scoped name. A model placed by ``placement_frame`` is refused.
- An MJCF (``cad.mjcf._source``) is its bodies as links under ``world`` (its root), a body with
  several joints a chain of links at the body's frame; its visuals are the geoms MuJoCo's viewer
  draws by default (groups 0 to 2), its collisions the rest (their facts as written: type, group,
  MuJoCo's sizes, material, alpha); a free or ball joint is fixed where it is authored; a hinge
  with no range is continuous and a slide with no range a control with ``min`` and ``max`` null,
  as a continuous joint's are (the page gives either one turn or one metre to slide over); its
  keyframes are ``poses``, each control's zero the joint's ``ref``; and it opens at ``qpos0``, as
  MuJoCo does (``opening`` every control at zero). A joint MuJoCo leaves unnamed is named
  ``<link>:joint``.
- A control is a joint a person or a job sets: revolute and continuous joints in DEGREES,
  prismatic joints in METRES, each at its declared limits (a continuous joint has none). A
  mimic follower is not a control: its row is its leader's, scaled and offset, so one value
  moves both. ``poses`` are an SRDF's group states (``<group>/<name>``), ``opening`` every
  control at rest with the SRDF's ``home`` state(s) over it.
- A URDF joint carrying ``<tcad:four_bar>`` (the robot-simulation skill's four-bar reference: the input
  crank of a planar four-bar linkage, derived from the ``driver`` joint on the same ground
  link) is not a control either, and has no handle: its row is a ``curve`` over the driver's
  row, sampled here from the linkage's closed form over the
  driver's whole operating range -- its declared limits, or one turn for a continuous driver
  -- densely enough that the page's linear interpolation stays within
  ``FOUR_BAR_CURVE_TOLERANCE_DEG``. The linkage's geometry (one ground link, parallel axes,
  pivots ``ground_length`` apart, the range reachable, the derived range within the joint's
  limits) is checked here, and refused in words; the page solves nothing.
- A visual's mesh is the file it names (``format`` the page's decoder: stl, 3mf or glb) or,
  for a box, cylinder, sphere or capsule, a GLB cadgen meshed (``_internal.primitive_mesh``)
  and holds by the sha256 of its bytes. An MJCF's OBJ, which the page has no decoder for, is
  held the same way: its triangles written as a GLB of the numbers the file holds, the mesh
  scale left in the placement as an STL's is (``0.001`` times the scale). The payload names
  a file by its absolute path (``path``) and a primitive by that digest (``object``);
  the host that serves it mints each one's ``url`` (:func:`locate_robot_payload`). A mesh
  lands in the robot's metres as its format defines it: a GLB is metres by the glTF spec,
  so one authored in metres needs no mesh scale, while an STL or a 3MF is drawn as the
  numbers it holds, which the mesh scale converts (``0.001`` for millimetres). The placement
  carries the conversion from the page's decoded unit (a GLB decodes into millimetres).
- Refusals are the validators' (``cad.urdf._source``, ``cad.sdf._validation``,
  ``cad.srdf._validation``, the MJCF reader ``cad.mjcf._source``, and an ``.xml`` whose root is
  not ``<mujoco>``), the engine reader's in the viewer's words (an SDF model the viewer does not
  place, a joint it does not pose, a frame graph that does not resolve), plus what the page cannot
  draw: a mesh in a format it has no decoder for, a shape it has no mesh for, a mesh it cannot
  reach. Every refusal is a :class:`RobotReadError` saying what to change.

The payload is derived data, held in this process's memory keyed by the description's path
and bytes and its paired URDF's bytes, or an MJCF's includes' and OBJ meshes' (``robot_payload_bytes``), so a second read of an
unchanged description parses nothing; a primitive's mesh is held beside it by the digest of
its bytes (``primitive_glb_bytes``). Nothing is written to disk.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
from collections import OrderedDict
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from cad.engine import mesh_uri, sdf_source, urdf_source
from cad.engine.robot_model import Dialect, SourceError
from cad.engine.robot_model import hex_color as _hex
from cad.engine.urdf_source import TCAD_NAMESPACE
from cad._internal.findings import format_findings
from cad._internal.xml_common import display_path, local_name
from cad.registry import DOCUMENT_TYPES

__all__ = [
    "DRAWABLE_MESH_FORMATS",
    "FOUR_BAR_CURVE_TOLERANCE_DEG",
    "ROBOT_PAYLOAD_SCHEMA_VERSION",
    "ROBOT_SUFFIXES",
    "RobotReadError",
    "four_bar_input_angle",
    "locate_robot_payload",
    "paired_urdf_for_srdf",
    "prepare_robot_description",
    "primitive_glb_bytes",
    "read_robot_description",
    "resolve_robot_primitives",
    "robot_control_values",
    "robot_payload_bytes",
    "robot_payload_scheme",
]

ROBOT_PAYLOAD_SCHEMA_VERSION = 2
# The articulation's own schema (the ``articulation`` block's ``schemaVersion``), which the page
# plays: controls, joints as affine rows (a sampled curve where one follows its driver), carries,
# handles, poses.
ARTICULATION_SCHEMA_VERSION = 2
# Raised when the same description resolves to a different payload of the same shape (2: a
# GLB link mesh in metres, an SDF's nested models) (``robot_payload_scheme``).
_RESOLUTION_REVISION = 2
# How many payloads, and how many primitive meshes, this process holds: the least recently read
# go first. A payload whose mesh went is read again (``robot_payload_bytes(rebuild=True)``).
PAYLOADS_HELD = 16
MESHES_HELD = 256
# Every document type viewed as a robot (``cad.registry``): a URDF, an SRDF, an SDF and an MJCF
# (``.xml`` and ``.mjcf``; an ``.xml`` is one only when its root is ``<mujoco>``).
ROBOT_SUFFIXES = tuple(extension for entry in DOCUMENT_TYPES.values() if entry.view == "robot"
                       for extension in entry.extensions)
_MJCF_SUFFIXES = tuple(DOCUMENT_TYPES["mjcf"].extensions)
#: The mesh files the page decodes, by suffix: what a link mesh may be.
DRAWABLE_MESH_FORMATS = {".stl": "stl", ".3mf": "3mf", ".glb": "glb"}
#: The shapes cadgen meshes for a visual (``_internal.primitive_mesh``).
DRAWABLE_SHAPES = ("box", "capsule", "cylinder", "sphere")
# What a visual's placement multiplies a decoded mesh by, by format, so the mesh lands in the
# robot's metres. glTF is metres by its spec and the page decodes a GLB into millimetres (the
# CAD Viewer's scene unit), so every GLB -- a link's mesh file and a primitive cadgen meshed
# alike -- carries 0.001. An STL has no unit and the page does not read a 3MF's: both are
# drawn as the numbers they hold, which the description's mesh scale converts to metres.
_DECODED_TO_METRES = {"glb": 0.001, "stl": 1.0, "3mf": 1.0}


def _mesh_scale(fmt: str, scale: list[float] | None = None) -> list[list[float]]:
    """The scale a visual's placement ends in: the description's mesh scale, if any, on the
    decoded mesh's own unit conversion to metres."""
    unit = _DECODED_TO_METRES[fmt]
    return _scale(*(unit * value for value in (scale or [1.0, 1.0, 1.0])))
_IDENTITY = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
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
# The closed form's tolerances, as the robot-simulation skill's four-bar reference has them.
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


def _scale(x: float, y: float, z: float) -> list[list[float]]:
    return [[x, 0.0, 0.0, 0.0], [0.0, y, 0.0, 0.0], [0.0, 0.0, z, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _invert_rigid(m: list[list[float]]) -> list[list[float]]:
    r = [[m[i][j] for j in range(3)] for i in range(3)]
    t = [m[0][3], m[1][3], m[2][3]]
    return [
        [r[0][0], r[1][0], r[2][0], -(r[0][0] * t[0] + r[1][0] * t[1] + r[2][0] * t[2])],
        [r[0][1], r[1][1], r[2][1], -(r[0][1] * t[0] + r[1][1] * t[1] + r[2][1] * t[2])],
        [r[0][2], r[1][2], r[2][2], -(r[0][2] * t[0] + r[1][2] * t[1] + r[2][2] * t[2])],
        [0.0, 0.0, 0.0, 1.0],
    ]


# Emitted numbers are rounded past any display accuracy and short of a float's last bits, so
# one description resolves to one payload on every platform's libm (the fixtures the browser
# suite serves are compared byte for byte against a fresh read).
_DECIMALS = 12


def _number(value: float) -> float:
    return round(float(value), _DECIMALS) + 0.0


def _flat(m: list[list[float]]) -> list[float]:
    return [_number(value) for row in m for value in row]


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


_LOCK = threading.Lock()
_PAYLOADS: OrderedDict[tuple, bytes] = OrderedDict()
_MESHES: OrderedDict[str, bytes] = OrderedDict()


def _held(table: OrderedDict, key: Any, value: Any, limit: int) -> None:
    with _LOCK:
        table[key] = value
        table.move_to_end(key)
        while len(table) > limit:
            table.popitem(last=False)


def primitive_glb_bytes(digest: str) -> bytes | None:
    """The GLB of a primitive this process meshed, by the sha256 of its bytes (what a payload's
    ``mesh.object`` names), or ``None`` when it holds no such mesh."""
    key = str(digest or "").strip().lower()
    with _LOCK:
        found = _MESHES.get(key)
        if found is not None:
            _MESHES.move_to_end(key)
        return found


def _primitive_mesh(shape: str, dimensions: dict) -> dict:
    """A primitive's mesh, meshed on first sight and held by the digest of its bytes."""
    from cad_server._internal.primitive_mesh import primitive_glb

    data = primitive_glb(shape, dimensions)
    digest = hashlib.sha256(data).hexdigest()
    _held(_MESHES, digest, data, MESHES_HELD)
    return {"format": "glb", "object": digest}


def _primitive_descriptor(shape: str, dimensions: dict) -> dict:
    """A prepared visual's mesh request, internal until resolution meshes its GLB."""
    return {"format": "glb", "_primitive": {"shape": shape, "dimensions": dimensions}}


# --- URDF, SDF and SRDF (the engine's readers: cad.engine.urdf_source, sdf_source) ----------------------
#
# The description is read once, in the engine, into its articulation; this is the page's view of it:
# each visual's mesh as the page decodes one (or a primitive cadgen meshes), its placement carrying the
# mesh's scale to metres, the facts as written. Where the viewer and the stills have read a detail
# differently, the payload's dialect keeps the viewer's: its words for a refusal (the page shows them),
# a pose's ``degrees`` true by any of SDFormat's boolean words, a nested model with no link of its own
# attached through its first nested model, a model relative to anything but the world, a
# ``placement_frame`` and a link two joints carry refused, a URDF's colours and four-bar numbers read
# leniently where its validator says nothing of them.

_WORDS = {
    "numbers": "{where} must be {count} numbers, not {written!r}",
    "axis_zero": "{file} joint {joint!r} axis must be nonzero",
    "rgba": None, "four_bar_many": None, "four_bar_number": None, "four_bar_lengths": None,
}
_URDF = Dialect(words={**_WORDS, "xml": "{file} could not be read: {error}"}, display=display_path)
_SDF = Dialect(
    words={
        **_WORDS,
        "xml": "{file} could not be parsed as SDF XML: {error}",
        "sdf_root": "{file} root element must be <sdf>",
        "sdf_models": "{file} holds {count} top-level models; the viewer renders one direct <model>",
        "sdf_worlds": "{file} must hold one direct <model>, or one <world> holding one direct <model>",
        "sdf_world_models": "{file} world holds {count} models; the viewer renders a world with exactly one direct <model>",
        "rotation_format": "{where} pose uses rotation_format {format!r}; the viewer reads euler_rpy",
        "model_relative": "{file} model {model!r} pose is relative_to {relative!r}; the viewer places a model in the world",
        "placement_frame": "{where} is placed by its placement_frame, which the viewer does not place by; "
                           "drop placement_frame and pose the model's own frame",
        "frame_twice": "SDF model {model!r} names {key!r} twice: links, frames, joints and nested models share one namespace",
        "frame_cycle": "SDF model {model!r} frame graph cycles at {key!r}",
        "attached_cycle": "SDF model {model!r} attached_to graph cycles at {key!r}",
        "sdf_joint_type": "{file} joint {joint!r} is a {kind!r} joint; the viewer poses fixed, revolute, continuous and "
                          "prismatic joints",
        "sdf_scale": "{where} mesh scale must be 3 numbers, not {written!r}",
        "joint_unattached": "{file} joint {joint!r} child {child!r} is not attached to a link",
        "joint_same": "{file} joint {joint!r} must connect different parent and child frames, not {link!r}",
    },
    display=display_path,
)


def _read(reader: Callable[..., Any], path: Path, dialect: Dialect, **options: Any) -> Any:
    try:
        return reader(path, dialect, **options)
    except SourceError as exc:
        raise RobotReadError(str(exc)) from None


def _mesh_file(visual: Any, *, where: str, base_dir: Path, format_first: bool) -> dict:
    """A visual's mesh file as the page decodes one: ``{format, path}``, refused by name where the page
    has no decoder for it (``format_first``: a URDF's says so before it says the file is not local), the
    reference names no local file, or no file is there."""
    reference, path = visual.reference, visual.shape[1]
    fmt = _drawable_format(reference, where=where) if format_first else ""
    if mesh_uri.scheme(reference) == "package":
        fmt = fmt or _drawable_format(reference, where=where)
        if path is None:
            try:
                mesh_uri.package_file(reference, base_dir, where)
            except mesh_uri.PackageError as exc:
                raise RobotReadError(str(exc)) from None
    elif path is None:
        raise RobotReadError(
            f"{where} names {reference!r}, which is not a local file: the viewer draws the meshes beside "
            "the description; copy the file next to it and name it by a relative path"
        )
    fmt = fmt or _drawable_format(reference, where=where)
    if not path.is_file():
        raise RobotReadError(f"{where} names {reference!r}, and no file is at {path}")
    return {"format": fmt, "path": str(path)}


def _sdf_primitive(where: str, kind: str, dimensions: Mapping[str, Any]) -> None:
    """An SDF visual's primitive has the dimensions a GLB is meshed from."""
    if (kind == "box" and "size" not in dimensions) or (kind != "box" and "radius" not in dimensions) \
            or (kind in ("cylinder", "capsule") and "length" not in dimensions):
        raise RobotReadError(f"{where} is a <{kind}> with missing or non-positive dimensions; give it positive dimensions")


def _described(kind: str, articulation: Any, display: str) -> _Description:
    """The engine's articulation of a URDF (or an SRDF's) or an SDF as the page takes it: each visual's
    mesh the page's (every visual the page cannot draw named together), each placement carrying its
    mesh's scale to metres, the facts as written."""
    description = _Description(kind, articulation.name, display)
    description.root = articulation.root
    base_dir = Path(articulation.sources[-1]).parent
    undrawable: list[str] = []  # every visual the page cannot draw, named together
    for name, placement in articulation.links.items():
        link = _Link(name)
        link.placement = placement
        for index, visual in enumerate(articulation.visuals.get(name, ()), start=1):
            where = f"{display} link {name!r} visual {index}"
            shape = visual.shape
            try:
                if shape[0] == "file":
                    if kind == "sdf" and not visual.reference:
                        raise RobotReadError(f"{where} is a <mesh> with no <uri>, so there is nothing to load")
                    mesh = _mesh_file(visual, where=where, base_dir=base_dir, format_first=kind != "sdf")
                    local = _multiply(visual.local, _mesh_scale(mesh["format"], shape[2]))
                    label = PurePosixPath(visual.reference).name or "mesh"
                elif shape[0] in DRAWABLE_SHAPES:
                    if kind == "sdf":
                        _sdf_primitive(where, shape[0], shape[1])
                    mesh = _primitive_descriptor(shape[0], dict(shape[1]))
                    local = _multiply(visual.local, _mesh_scale(mesh["format"]))
                    label = shape[0]
                elif kind != "sdf":
                    raise RobotReadError(f"{where} uses geometry the viewer cannot draw; give it a mesh, box, cylinder or sphere")
                else:
                    what = "has no <geometry>" if shape[0] == "missing" else f"uses <{shape[0]}> geometry, which the viewer cannot draw"
                    raise RobotReadError(f"{where} {what}. Supported: {', '.join(DRAWABLE_SHAPES)}, mesh. "
                                         "Replace it with one of those, or reference a mesh file.")
            except RobotReadError as exc:
                undrawable.append(str(exc))
                continue
            # A URDF visual's own name is what its author called it, and what tells several visuals of
            # one link apart; without one, it is named for its geometry. An SDF's is named for its geometry.
            if kind != "sdf":
                label = visual.facts["name"] or label
            link.visuals.append(_Visual(visual.id, label, local, visual.color, mesh, visual.facts))
        link.collisions = articulation.collisions.get(name, [])
        link.inertial = articulation.inertials.get(name)
        description.links.append(link)
    if undrawable:
        raise RobotReadError("; ".join(undrawable))
    for linked in articulation.joints:
        joint = _Joint(linked.name, linked.type, linked.parent, linked.child)
        joint.frame, joint.axis, joint.lower, joint.upper = linked.frame, linked.axis, linked.lower, linked.upper
        joint.mimic = linked.mimic
        # The urdf skill's four-bar, in its own namespace; an element of that name in any other is no linkage.
        four_bar = linked.four_bar
        if four_bar is not None and four_bar.get("namespace") == TCAD_NAMESPACE:
            joint.four_bar = four_bar
        joint.facts = dict(linked.facts or {})
        if kind != "sdf":
            joint.facts["mimic"] = ({"joint": joint.mimic[0], "multiplier": joint.mimic[1], "offset": joint.mimic[2]}
                                    if joint.mimic else None)
            joint.facts["fourBar"] = _four_bar_facts(joint.four_bar)
        description.joints.append(joint)
    description.sdf = articulation.sdf
    return description


def _four_bar_facts(four_bar: dict[str, Any] | None) -> dict[str, Any] | None:
    if four_bar is None:
        return None
    return {"driver": four_bar["driver"], "inputLength": four_bar["input_length"], "groundLength": four_bar["ground_length"],
            "outputLength": four_bar["output_length"], "couplerLength": four_bar["coupler_length"],
            "inputZero": four_bar["input_zero"], "outputZero": four_bar["output_zero"]}


def _validated_urdf(path: Path) -> None:
    from cad.urdf._source import validate_urdf_file

    source, findings = validate_urdf_file(path)
    if findings.errors or source is None:
        raise RobotReadError(format_findings(findings.errors))


def _read_urdf(path: Path) -> _Description:
    _validated_urdf(path)
    return _described("urdf", _read(urdf_source.read_urdf, path, _URDF), display_path(path))


def _read_sdf(path: Path) -> _Description:
    from cad.sdf._source import SdfSourceError
    from cad.sdf._validation import raise_for_validation_errors, validate_sdf_root

    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise RobotReadError(f"{display_path(path)} could not be parsed as SDF XML: {exc}") from None
    try:
        raise_for_validation_errors(validate_sdf_root(root, source_path=path, base_dir=path.parent))
    except SdfSourceError as exc:
        raise RobotReadError(str(exc)) from None
    return _described("sdf", _read(sdf_source.read_sdf, path, _SDF), display_path(path))


# --- MJCF ------------------------------------------------------------------------------------


def _matrix_origin(m: list[list[float]]) -> dict[str, list[float]]:
    """A rigid placement as a person reads one back: ``xyz`` and URDF's ``rpy`` (fixed X, Y, Z)."""
    pitch = math.asin(max(-1.0, min(1.0, -m[2][0])))
    if abs(math.cos(pitch)) > 1e-9:
        roll, yaw = math.atan2(m[2][1], m[2][2]), math.atan2(m[1][0], m[0][0])
    else:  # gimbal lock: the roll is folded into the yaw
        roll, yaw = 0.0, math.atan2(-m[0][1], m[1][1])
    return {"xyz": [_number(m[i][3]) for i in range(3)], "rpy": [_number(roll), _number(pitch), _number(yaw)]}


def _mjcf_geom_facts(geom, mesh_asset=None) -> dict:
    """A geom as written: its name, its MuJoCo type, group and sizes (MuJoCo's own half-sizes), its
    material, colour and alpha, its placement in its body, and the mesh file it names."""
    facts: dict = {
        "name": geom.name, "type": geom.type, "filename": "", "origin": _matrix_origin(geom.local),
        "group": geom.group, "size": [_number(value) for value in geom.size],
        "color": _hex(list(geom.rgba)), "alpha": _number(geom.rgba[3]),
        "material": geom.material or "", "materialName": geom.material or "",
    }
    if geom.type == "mesh":
        facts["mesh"] = geom.mesh or ""
        if mesh_asset is not None and mesh_asset.file is not None:
            facts["filename"] = mesh_asset.file.name
            facts["path"] = str(mesh_asset.file)
            facts["scale"] = [_number(value) for value in mesh_asset.scale]
    return facts


# The files an MJCF's payload was read from beside the model's own (its includes, and the OBJ
# meshes its GLBs are made of), by the model's path: part of the key its payload is held under, so
# an edited include or OBJ is read again (``robot_payload_bytes``).
_DEPENDENCIES: OrderedDict[str, tuple[str, ...]] = OrderedDict()


def _obj_descriptor(path: Path) -> dict:
    """A prepared OBJ visual's mesh request, internal until resolution writes its GLB."""
    return {"format": "glb", "_obj": {"path": str(path)}}


def _obj_mesh(path: str) -> dict:
    """An OBJ's mesh as the page decodes one: its triangles written as a GLB (the numbers the file
    holds; the visual's placement carries its scale) and held by the digest of its bytes."""
    from cad.engine.formats.obj import read_obj
    from cad_server._internal.primitive_mesh import triangles_glb

    try:
        points, triangles = read_obj(Path(path))
        data = triangles_glb(points, triangles)
    except (OSError, ValueError) as exc:
        raise RobotReadError(f"{display_path(Path(path))} could not be read as an OBJ mesh: {exc}") from None
    digest = hashlib.sha256(data).hexdigest()
    _held(_MESHES, digest, data, MESHES_HELD)
    return {"format": "glb", "object": digest}


def _read_mjcf(path: Path) -> _Description:
    """An MJCF as the robot view takes one (``cad.mjcf._source``): a link per body (a body with
    several joints a chain of links), the world its root, the drawn geoms (groups 0 to 2) its
    visuals and the rest its collisions, a free or ball joint fixed where it is authored, a joint
    with no range unbounded (a hinge continuous, a slide with ``min`` and ``max`` null), the
    keyframes its poses, and the model opening at ``qpos0`` as MuJoCo's does."""
    from cad.mjcf._source import DRAWN_GROUPS, articulate, is_mjcf_file, read_mjcf

    display = display_path(path)
    if path.suffix.lower() == ".xml" and not is_mjcf_file(path):
        raise RobotReadError(
            f"{display} is not an MJCF: an .xml is read as a robot only when its root element is <mujoco>; "
            "open a MuJoCo model, or name a URDF .urdf and an SDF .sdf"
        )
    model, findings = read_mjcf(path)
    if findings.errors or model is None:
        raise RobotReadError(format_findings(findings.errors))
    articulation = articulate(model)
    description = _Description("mjcf", model.name, display)
    description.root = articulation.root

    # A joint MuJoCo leaves unnamed is named for the link it moves, so every row has an id.
    taken = {joint.name for joint in articulation.joints if joint.name}
    names: dict[int, str] = {}
    for index, linked in enumerate(articulation.joints):
        if linked.name:
            names[index] = linked.name
            continue
        base = f"{linked.child}:joint"
        candidate, suffix = base, 2
        while candidate in taken:
            candidate, suffix = f"{base}{suffix}", suffix + 1
        taken.add(candidate)
        names[index] = candidate

    dependencies = [str(file) for file in model.files if Path(file) != path]
    links: dict[str, _Link] = {}
    for name, rest in articulation.links.items():
        link = _Link(name)
        link.placement = [list(map(float, row)) for row in rest]
        for visual in articulation.visuals.get(name, ()):
            geom = visual.geom
            asset = model.meshes.get(geom.mesh or "") if geom.type == "mesh" else None
            facts = _mjcf_geom_facts(geom, asset)
            local = [list(map(float, row)) for row in visual.local]
            shape = visual.shape
            if shape[0] == "file":
                file, scale = Path(shape[1]), [float(value) for value in shape[2]]
                if file.suffix.lower() == ".obj":
                    mesh = _obj_descriptor(file)
                    dependencies.append(str(file))
                else:
                    mesh = {"format": _drawable_format(file.name, where=f"{display} geom {visual.label!r}"), "path": str(file)}
                local = _multiply(local, _mesh_scale(mesh["format"], scale))
            else:
                mesh = _primitive_descriptor(shape[0], dict(shape[1]))
                local = _multiply(local, _mesh_scale(mesh["format"]))
            link.visuals.append(_Visual(visual.id, visual.label, local, visual.color, mesh, facts))
        body = model.bodies.get(name)
        if body is not None:
            # MuJoCo's collision geoms by convention: the groups its viewer hides by default.
            link.collisions = [_mjcf_geom_facts(geom, model.meshes.get(geom.mesh or "") if geom.type == "mesh" else None)
                               for geom in body.geoms if geom.group not in DRAWN_GROUPS]
        inertial = articulation.inertials.get(name)
        if inertial is not None:
            link.inertial = {"mass": inertial.get("mass"), "origin": _matrix_origin(inertial["origin"]),
                             "inertia": inertial.get("inertia")}
        links[name] = link
        description.links.append(link)

    for index, linked in enumerate(articulation.joints):
        joint = _Joint(names[index], linked.type, linked.parent, linked.child)
        joint.frame = [list(map(float, row)) for row in linked.frame]
        joint.axis = None if linked.type == "fixed" else (list(linked.axis) if linked.axis is not None else None)
        if linked.type != "fixed" and joint.axis is None:
            raise RobotReadError(f"{display} joint {joint.name!r} axis must be nonzero")
        joint.lower, joint.upper = linked.lower, linked.upper
        joint.mimic = linked.mimic
        source = linked.source
        parent = links.get(linked.parent)
        origin = _multiply(_invert_rigid(parent.placement), joint.frame) if parent is not None else joint.frame
        limit = None
        if source is not None and source.range is not None and linked.type != "fixed":
            limit = {"lower": _number(source.range[0]), "upper": _number(source.range[1])}
        joint.facts = {
            "name": joint.name, "type": joint.type, "parent": joint.parent, "child": joint.child,
            "axis": None if joint.type == "fixed" or source is None else [_number(value) for value in source.axis],
            "origin": _matrix_origin(origin),
            "limit": limit,
            "mimic": {"joint": joint.mimic[0], "multiplier": joint.mimic[1], "offset": joint.mimic[2]} if joint.mimic else None,
            "fourBar": None,
            # MuJoCo's own: the joint's type (a free or ball joint is drawn fixed), ``ref`` (the
            # authored position a control's zero is) and the range as written, around ``ref``.
            "mjcfType": source.type if source is not None else None,
            "ref": _number(source.ref) if source is not None else None,
        }
        description.joints.append(joint)

    description.poses = {key: dict(values) for key, values in articulation.poses.items()}
    _held(_DEPENDENCIES, str(path), tuple(dict.fromkeys(dependencies)), PAYLOADS_HELD * 4)
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
    whose ``<robot name>`` matches -- the rule ``cad srdf validate`` and the CAD Viewer
    use -- and exactly one may match.
    """
    from cad.srdf._validation import find_paired_urdf

    folder = srdf_path.parent
    robot_name = _robot_name_of(srdf_path)
    rule = (
        "An SRDF renders the geometry of the same-folder .urdf whose <robot name> "
        "matches its own, and exactly one may match (check with `cad srdf validate`)."
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


def _read_srdf(path: Path) -> _Description:
    from cad.srdf._source import parse_srdf_file
    from cad.srdf._validation import _link_names_for_group, read_urdf_robot, validate_srdf_against_urdf

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
    _validated_urdf(urdf_path)
    # The group states are the engine's poses (each control's value in its unit) and its home the opening.
    articulation = _read(urdf_source.read_srdf, path, _URDF, urdf=urdf_path)
    description = _described("urdf", articulation, display_path(urdf_path))
    description.kind = "srdf"
    description.poses, description.home = articulation.poses, articulation.home
    groups_by_name = {group.name: group for group in source.planning_groups}
    states = [{"id": f"{state.group}/{state.name}", "name": state.name, "group": state.group} for state in source.group_states]

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
# The planar four-bar the robot-simulation skill's four-bar reference describes: the ground link runs from
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
    """The crank's two possible angles (radians from the ground direction) at a driver angle.
    ``RobotReadError`` says why the coupler cannot reach, for a caller to place in its sentence."""
    output_angle = four_bar["output_zero"] + driver_rad
    pin_x = four_bar["ground_length"] + four_bar["output_length"] * math.cos(output_angle)
    pin_y = four_bar["output_length"] * math.sin(output_angle)
    distance = math.hypot(pin_x, pin_y)
    crank, coupler = four_bar["input_length"], four_bar["coupler_length"]
    if distance <= _FOUR_BAR_INTERSECTION_TOLERANCE:
        raise RobotReadError("the output pin coincides with the input pivot")
    if distance < abs(crank - coupler) - _FOUR_BAR_INTERSECTION_TOLERANCE or distance > crank + coupler + _FOUR_BAR_INTERSECTION_TOLERANCE:
        raise RobotReadError(
            f"the output pin is {distance:g} m from the input pivot, outside the {abs(crank - coupler):g} to {crank + coupler:g} m "
            f"that input_length {crank:g} and coupler_length {coupler:g} reach"
        )
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
        raise RobotReadError(
            f"{where}: its pivot and the pivot of its driver {driver.name!r} are not coplanar ({axial:g} m apart along the axis); "
            "place both joints' origins in one plane normal to the axis"
        )
    if abs(planar - expected) > tolerance:
        raise RobotReadError(
            f"{where} declares ground_length {expected:g}, but its pivot and the pivot of its driver {driver.name!r} are {planar:g} metres apart; "
            "set ground_length to that distance, or move the joints' origins"
        )


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
            f"{where}: the range [{math.degrees(lower_rad):g}, {math.degrees(upper_rad):g}] deg of its driver {driver!r} includes angles "
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
            raise RobotReadError(
                f"{where} cannot close with its driver {driver.name!r} at {math.degrees(x):g} deg: {exc}; "
                "narrow the driver's limits or correct the lengths"
            ) from None

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
                f"{where} derives {low_deg:g} to {high_deg:g} deg over the range of its driver {driver.name!r}, outside its own limits "
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
            zero_pose = f"at the zero pose (its driver {driver.name!r} at 0 deg)"
            try:
                four_bar["branch"] = _four_bar_branch(four_bar)
            except RobotReadError as exc:
                raise RobotReadError(f"{where} cannot close {zero_pose}: {exc}; correct the lengths so the linkage closes as written") from None
            if abs(four_bar_input_angle(four_bar, 0.0)) > _FOUR_BAR_ZERO_POSE_TOLERANCE_RAD:
                closes = " or ".join(f"{math.degrees(angle):g}" for angle in _four_bar_candidates(four_bar, 0.0))
                raise RobotReadError(
                    f"{where} zero angles do not describe an assembly branch the lengths close at: {zero_pose} the coupler closes "
                    f"the crank at {closes} deg from the ground line, not at input_zero {math.degrees(four_bar['input_zero']):g} deg; "
                    "set input_zero to the angle of the branch the linkage is assembled on"
                )
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


def prepare_robot_description(path: Path | str) -> dict[str, Any]:
    """Validate and resolve a description's frames and articulation without meshing or writing.

    The result is internal prepared data: primitive visual meshes remain descriptors until
    :func:`resolve_robot_primitives`. ``robot_control_values`` can validate a request against
    it before the caller clears any output or starts geometry work.
    """
    resolved = Path(path).expanduser().resolve()
    kind = resolved.suffix.lower()
    if kind not in ROBOT_SUFFIXES:
        raise RobotReadError(f"{resolved.name} is not a robot description: one of {', '.join(ROBOT_SUFFIXES)}")
    if not resolved.is_file():
        raise RobotReadError(f"no file is at {resolved}")
    if kind == ".urdf":
        description = _read_urdf(resolved)
    elif kind == ".sdf":
        description = _read_sdf(resolved)
    elif kind in _MJCF_SUFFIXES:
        description = _read_mjcf(resolved)
    else:
        description = _read_srdf(resolved)
    return _payload(description)


def resolve_robot_primitives(prepared: Mapping[str, Any]) -> dict[str, Any]:
    """Mesh the prepared description's primitives, each held by the digest of its GLB.

    Return the wire payload without changing the prepared data. Mesh files, placements and
    articulation already came from the description's one preparation path.
    """
    payload = copy.deepcopy(dict(prepared))
    for visual in payload.get("visuals") or []:
        primitive = visual["mesh"].get("_primitive")
        if primitive is not None:
            visual["mesh"] = _primitive_mesh(primitive["shape"], primitive["dimensions"])
        obj = visual["mesh"].get("_obj")
        if obj is not None:
            visual["mesh"] = _obj_mesh(obj["path"])
    return payload


def read_robot_description(path: Path | str) -> dict[str, Any]:
    """The validated description's payload, with its primitive meshes held as GLBs.

    ``RobotReadError`` names what to change. Request-only callers can prepare and validate
    controls first, then resolve primitives once the whole request has been accepted.
    """
    return resolve_robot_primitives(prepare_robot_description(path))


def robot_payload_scheme() -> str:
    """What the payload's shape, its resolution and its primitive meshes depend on: part of the
    key a payload is held under."""
    from cad_server._internal.primitive_mesh import ANGLE, CHORD

    return (f"robot-payload-{ROBOT_PAYLOAD_SCHEMA_VERSION}-resolution-{_RESOLUTION_REVISION}-"
            f"articulation-{ARTICULATION_SCHEMA_VERSION}-chord-{CHORD}-angle-{ANGLE}")


def encode_robot_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dependency_hash(path: str) -> str:
    """A dependency's hash, or ``""`` for one that is gone (its absence is then the change)."""
    try:
        return _file_hash(Path(path))
    except OSError:
        return ""


def robot_payload_bytes(path: Path | str, *, rebuild: bool = False) -> bytes:
    """The payload's bytes: the ones this process holds for an unchanged description (and, for an
    SRDF, an unchanged paired URDF), else read now and held. ``rebuild`` reads now regardless, for
    a host whose held payload names a mesh this process no longer holds."""
    resolved = Path(path).expanduser().resolve()
    if resolved.suffix.lower() not in ROBOT_SUFFIXES:
        raise RobotReadError(f"{resolved.name} is not a robot description: one of {', '.join(ROBOT_SUFFIXES)}")
    if not resolved.is_file():
        raise RobotReadError(f"no file is at {resolved}")
    paired = paired_urdf_for_srdf(resolved) if resolved.suffix.lower() == ".srdf" else None

    def key_now() -> tuple:
        with _LOCK:
            # An MJCF's includes and OBJ meshes, as its last read found them: an edit to one is a new key.
            dependencies = _DEPENDENCIES.get(str(resolved), ())
        try:
            return (str(resolved), _file_hash(resolved), _file_hash(paired) if paired else None,
                    tuple((dependency, _dependency_hash(dependency)) for dependency in dependencies), robot_payload_scheme())
        except OSError as exc:
            raise RobotReadError(f"{resolved} could not be read: {exc}") from None

    if not rebuild:
        key = key_now()
        with _LOCK:
            cached = _PAYLOADS.get(key)
            if cached is not None:
                _PAYLOADS.move_to_end(key)
                return cached
    data = encode_robot_payload(read_robot_description(resolved))
    # Keyed after the read, by the dependencies that read found.
    _held(_PAYLOADS, key_now(), data, PAYLOADS_HELD)
    return data


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


def _plus(value: float) -> str:
    """A term added to a formula, its sign the operator: `` + 2`` or `` - 2``."""
    return f" - {_format(-value)}" if value < 0 else f" + {_format(value)}"


def robot_control_values(payload: Mapping[str, Any], request: object) -> dict[str, float]:
    """The full control vector a ``jointValues`` request means: every control, the ones the
    request names at their values and the rest at the opening. A value for a joint that is not
    a control is refused by name (a fixed joint has no value; a mimic follower is set through the
    control its chain of leaders ends at; a four-bar's crank through its driver), as is a value
    outside a control's limits -- which, for a four-bar's driver, is the range the linkage was
    solved over -- and a leader value that puts a follower outside the follower's own limits."""
    articulation = payload.get("articulation") or {}
    controls = {str(control["id"]): control for control in articulation.get("controls") or []}
    rows = {str(joint["id"]): joint for joint in articulation.get("joints") or []}
    facts_by_name = {str(joint.get("name")): joint for joint in payload.get("joints") or [] if isinstance(joint, Mapping)}
    kind = str(payload.get("kind") or "robot").upper()

    def driven_by(name: str) -> tuple[str, str]:
        """``(the control that poses joint name, how the joint follows it)``: the chain of mimic
        leaders and four-bar drivers from the joint to the control it ends at."""
        steps: list[str] = []
        current, seen = name, {name}
        while current not in controls:
            facts = facts_by_name.get(current) or {}
            four_bar, mimic = facts.get("fourBar"), facts.get("mimic")
            if isinstance(four_bar, Mapping) and four_bar.get("driver"):
                current = str(four_bar["driver"])
                steps.append(f"is the crank of a four-bar linkage (tcad:four_bar) driven by {current!r}")
            elif isinstance(mimic, Mapping) and mimic.get("joint"):
                current = str(mimic["joint"])
                steps.append(f"mimics {current!r}")
            else:
                break
            if current in seen:
                break
            seen.add(current)
        return current, ", which ".join(steps)

    def unit_of(name: str) -> str:
        return "m" if (facts_by_name.get(name) or {}).get("type") == "prismatic" else "deg"
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
            root, chain = driven_by(name)
            # A follower's row is affine in the control its chain ends at: say how it follows, in
            # that control's terms. A row on a curve (a crank, or a mimic of one) has no such form.
            row = joint.get("turn") or joint.get("travel") or {}
            terms, bias = row.get("terms") or [], float(row.get("bias") or 0.0)
            formula = ""
            if len(terms) == 1 and str(terms[0][0]) == root and "curve" not in row:
                offset = f"{_plus(bias)} {unit_of(name)}" if bias else ""
                formula = f" ({name} = {_format(float(terms[0][1]))} × {root}{offset})"
            raise RobotReadError(
                f"jointValues[{name}]: joint {name!r} {chain}{formula}, so it is posed by the value of {root!r}; "
                f"set jointValues[{root}] instead"
            )
        control = controls[name]
        lo, hi, unit = control.get("min"), control.get("max"), str(control.get("unit") or "")
        if lo is not None and hi is not None:
            # Degrees converted from radians carry rounding: a value written as the limit itself must pass.
            tolerance = 1e-9 * max(1.0, abs(float(lo)), abs(float(hi)))
            if not float(lo) - tolerance <= float(value) <= float(hi) + tolerance:
                raise RobotReadError(
                    f"jointValues[{name}] = {_format(float(value))} {unit} is outside the limits "
                    f"[{_format(float(lo))}, {_format(float(hi))}] {unit} of joint {name!r}; pass a value within them"
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
            leader_unit = str(controls[leader].get("unit") or "")
            raise RobotReadError(
                f"jointValues[{leader}] = {_format(values[leader])} {leader_unit} puts joint {joint_id!r}, which {driven_by(joint_id)[1]}, "
                f"at {_format(value)} {unit}, outside its limits [{_format(lo)}, {_format(hi)}] {unit}; "
                f"pass a value that keeps it within them"
            )
    return values

"""An MJCF model (MuJoCo's XML) read into what a robot is to the viewer and the stills: bodies
placed at rest in the model's space, each with its geoms, joints and inertial, the mesh assets
they name, and the keyframes.

In the engine, as ``mesh_uri`` is, because every reader of an MJCF reads it here: the stills
(``formats/robot.py``), the viewer's robot payload (the server's) and the type's own check
(``cad.mjcf``, which re-exports it as ``cad.mjcf._source`` and turns its findings into the
validation family's). The engine stands alone, so this imports nothing of the packages but the
engine; the standard library alone (the validation family's rule, ``tests/python/global
/test_robot_modules_stdlib_pure.py``): ElementTree and arithmetic on 4x4 matrices as lists.
MuJoCo itself is the ``mujoco`` integration's (``cad.mujoco``), which compiles the model for
``cad mjcf validate --compile``; reading here needs nothing installed, as reading a URDF does, so
the CAD Viewer and ``cad mjcf snapshot`` open an MJCF on any device.

**What is read**, as MuJoCo's compiler reads it where the two agree:

- ``<include file>`` anywhere, relative to the MAIN file's folder, each file once, its root
  element discarded and its children spliced in;
- ``<compiler angle eulerseq meshdir assetdir texturedir strippath autolimits>``: degrees unless
  it says radians, ``xyz`` intrinsic Euler unless it says otherwise;
- ``<default class>`` nested, each tag's attributes inherited down, resolved for an element by its
  ``class``, else the nearest body's ``childclass``, else ``main``;
- ``<asset>``: ``<mesh name file scale>`` (``name`` the file's stem unless given) and ``<material
  name rgba>``;
- ``<worldbody>`` and its ``<body name pos quat|euler|axisangle|xyaxes|zaxis childclass>`` tree,
  ``<frame>`` groups (a pure transform on what they hold), ``<inertial>``, ``<geom type size fromto
  pos quat ... rgba material mesh group>`` (groups 0 to 2 drawn, as MuJoCo's viewer draws them by
  default; 3 and up are a model's collision geoms and are not visuals), ``<joint type axis pos range
  limited ref>`` and ``<freejoint>``;
- ``<equality><joint joint1 joint2 polycoef>``: a linear coupling as a mimic;
- ``<keyframe><key name qpos>``: each a pose of the model's hinge and slide joints.

**What is refused, by name** (an error): a root that is not ``<mujoco>``, no ``<worldbody>``, an
include that is not there or is included twice, a class, a mesh or a material no asset declares, a
mesh file that is not there or is no STL, OBJ or MSH, a geom's or a joint's type outside MuJoCo's,
a wrong count of numbers, two orientations on one element, an inverted range, a zero axis, a
zero-length ``fromto``, a duplicate body, joint or geom name.

**What is read as less than MuJoCo makes of it** (a warning or an info, never silent): a ``ball``
joint (a warning) or a ``free`` joint (an info: a floating base is how a legged robot is authored)
-- the body is drawn where it is authored and is not posable; a plane without a size (an info: a
scene's floor, which the viewer's grid stands in for), a heightfield, an SDF geom, an ellipsoid, a
mesh given inline or as MSH (none drawn, the geom skipped), ``<replicate>``, ``<attach>``,
``<flexcomp>``, ``<flex>`` and ``<composite>`` (the compiler's own expansions, read as nothing), a
key whose ``qpos`` is the wrong length. No texture is drawn: a geom of a textured material is
MuJoCo's plain grey. For the model exactly as MuJoCo compiles it, ``cad mjcf validate --compile
required``.

**Units and frames**: metres and radians in every number here, whatever the file's ``angle``;
a control's zero is the joint's ``ref``, as MuJoCo's ``qpos0`` is, so the model opens as
authored and a range is around it. A body with several joints is articulated as a chain of
one-joint links (``articulate``), the joints applied in their order about the body's frame, as
MuJoCo's kinematics composes them.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

__all__ = ["ARTICULATED", "Articulation", "Finding", "Findings", "GEOM_TYPES", "JOINT_TYPES", "LinkJoint",
           "MESH_SUFFIXES", "MJCF_SUFFIXES", "MjcfBody", "MjcfError", "MjcfGeom", "MjcfJoint", "MjcfMesh", "MjcfModel",
           "Visual", "articulate", "is_mjcf_file", "read_mjcf"]

Matrix = list[list[float]]

MJCF_SUFFIXES = (".xml", ".mjcf")
GEOM_TYPES = ("plane", "hfield", "sphere", "capsule", "ellipsoid", "cylinder", "box", "mesh", "sdf")
JOINT_TYPES = ("free", "ball", "slide", "hinge")
#: The mesh files MuJoCo loads (``<mesh file>``), by suffix. STL and OBJ are drawn; MSH, MuJoCo's own binary, is not.
MESH_SUFFIXES = (".stl", ".obj", ".msh")
DRAWN_MESH_SUFFIXES = (".stl", ".obj")
#: The geom groups drawn as visuals: MuJoCo's viewer shows 0 to 2 by default, and a model's
#: collision geoms sit in 3 and up by convention (menagerie's do).
DRAWN_GROUPS = (0, 1, 2)
#: Elements MuJoCo's compiler expands into bodies and geoms; reading them is the compiler's.
COMPILE_ONLY = ("replicate", "attach", "flexcomp", "flex", "composite")
#: The shapes drawn as primitives, with MuJoCo's sizes read into the viewer's (full box sizes, a
#: radius and a full length).
PRIMITIVES = ("sphere", "capsule", "cylinder", "box", "plane")
#: How a body's joints become the viewer's: a hinge turns (``revolute``; ``continuous`` without a
#: range), a slide slides (``prismatic``), a ball or a free joint is drawn where it is and does not move.
ARTICULATED = {"hinge": "revolute", "slide": "prismatic", "ball": "fixed", "free": "fixed"}
_DEFAULT_RGBA = (0.5, 0.5, 0.5, 1.0)
_ORIENTATIONS = ("quat", "euler", "axisangle", "xyaxes", "zaxis")
_EPSILON = 1e-12
#: The tags a default class carries attributes for, of those read here.
_DEFAULTED = ("geom", "joint", "mesh", "material", "body")


class MjcfError(ValueError):
    """The model cannot be read as an MJCF, said in the findings' words."""


@dataclass(frozen=True)
class Finding:
    """One thing the reader found: its severity (``error``, ``warning``, ``info``), a stable code, the
    message, where in the model, and a hint. The validation family's finding, spelled for the engine,
    which imports nothing of the library beyond itself; ``cad.mjcf`` turns these into its own."""

    severity: str
    code: str
    message: str
    path: str | None = None
    hint: str | None = None

    def format(self) -> str:
        location = f" at {self.path}" if self.path else ""
        hint = f" Hint: {self.hint}" if self.hint else ""
        return f"{self.severity}: {self.code}{location}: {self.message}{hint}"


@dataclass
class Findings:
    """What one read found, by severity."""

    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    infos: list[Finding] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str, *, path: str | None = None, hint: str | None = None) -> Finding:
        finding = Finding(severity, code, message, path, hint)
        {"error": self.errors, "warning": self.warnings}.get(severity, self.infos).append(finding)
        return finding

    def all_findings(self) -> list[Finding]:
        return [*self.errors, *self.warnings, *self.infos]

    def formatted(self, findings: list[Finding] | None = None) -> str:
        return "\n".join(finding.format() for finding in (self.errors if findings is None else findings))


def display_path(path: Path) -> str:
    """How a file is named in a finding: relative to the working folder when it is under it, else absolute."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def local_name(tag: object) -> str:
    """An ElementTree tag without its ``{namespace}`` prefix."""
    return str(tag).rsplit("}", 1)[-1]


def children(parent: ET.Element, tag_name: str) -> list[ET.Element]:
    """The child elements named ``tag_name`` (comments and processing instructions never match)."""
    return [child for child in list(parent) if local_name(child.tag) == tag_name]


# --- matrices ----------------------------------------------------------------------------------


def identity() -> Matrix:
    return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def multiply(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[row][k] * b[k][col] for k in range(4)) for col in range(4)] for row in range(4)]


def translation(xyz: list[float]) -> Matrix:
    out = identity()
    out[0][3], out[1][3], out[2][3] = float(xyz[0]), float(xyz[1]), float(xyz[2])
    return out


def _with_rotation(rotation: list[list[float]], xyz: list[float] | None = None) -> Matrix:
    out = identity()
    for row in range(3):
        out[row][:3] = [float(value) for value in rotation[row]]
        if xyz is not None:
            out[row][3] = float(xyz[row])
    return out


def rotate(matrix: Matrix, vector: list[float]) -> list[float]:
    """``vector`` turned by ``matrix``'s rotation (no translation)."""
    return [sum(matrix[row][k] * vector[k] for k in range(3)) for row in range(3)]


def transform(matrix: Matrix, point: list[float]) -> list[float]:
    return [sum(matrix[row][k] * point[k] for k in range(3)) + matrix[row][3] for row in range(3)]


def _norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _unit(vector: list[float]) -> list[float] | None:
    length = _norm(vector)
    return None if length < _EPSILON else [value / length for value in vector]


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def quaternion_matrix(wxyz: list[float]) -> list[list[float]]:
    """MuJoCo's quaternion, ``w x y z``, as a rotation (normalised here as the compiler normalises it)."""
    unit = _unit([float(value) for value in wxyz])
    if unit is None:
        raise ValueError("a quaternion of zero length")
    w, x, y, z = unit
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def axis_angle_matrix(axis: list[float], angle: float) -> list[list[float]]:
    unit = _unit(axis)
    if unit is None:
        raise ValueError("an axis of zero length")
    x, y, z = unit
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


def _matmul3(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[row][k] * b[k][col] for k in range(3)) for col in range(3)] for row in range(3)]


def euler_matrix(angles: list[float], sequence: str) -> list[list[float]]:
    """MuJoCo's Euler angles (radians) in ``eulerseq``: a lowercase letter turns about the moving
    frame's axis (intrinsic), an uppercase one about the fixed frame's (extrinsic)."""
    if len(sequence) != 3 or any(letter.lower() not in "xyz" for letter in sequence):
        raise ValueError(f"eulerseq must be three of x, y, z (either case), not {sequence!r}")
    axes = {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}
    rotation = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    for letter, angle in zip(sequence, angles, strict=True):
        step = axis_angle_matrix(axes[letter.lower()], angle)
        rotation = _matmul3(rotation, step) if letter.islower() else _matmul3(step, rotation)
    return rotation


def z_axis_matrix(zaxis: list[float]) -> list[list[float]]:
    """The least rotation taking Z to ``zaxis`` (MuJoCo's ``zaxis``)."""
    unit = _unit(zaxis)
    if unit is None:
        raise ValueError("a zaxis of zero length")
    z = [0.0, 0.0, 1.0]
    axis = _cross(z, unit)
    dot = max(-1.0, min(1.0, unit[2]))
    if _norm(axis) < _EPSILON:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]] if dot > 0 else \
            [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]]
    return axis_angle_matrix(axis, math.acos(dot))


def xy_axes_matrix(xyaxes: list[float]) -> list[list[float]]:
    x = _unit(xyaxes[:3])
    if x is None:
        raise ValueError("an xyaxes whose X is of zero length")
    y_raw = xyaxes[3:]
    dot = sum(a * b for a, b in zip(x, y_raw, strict=True))
    y = _unit([value - dot * axis for value, axis in zip(y_raw, x, strict=True)])
    if y is None:
        raise ValueError("an xyaxes whose Y lies along its X")
    z = _cross(x, y)
    return [[x[0], y[0], z[0]], [x[1], y[1], z[1]], [x[2], y[2], z[2]]]


# --- the model ---------------------------------------------------------------------------------


@dataclass
class MjcfMesh:
    """A ``<mesh>`` asset: its name, its file (resolved by the compiler's rules; None for one given
    inline), its suffix and its scale."""

    name: str
    file: Path | None
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)

    @property
    def suffix(self) -> str:
        return self.file.suffix.lower() if self.file is not None else ""

    @property
    def drawn(self) -> bool:
        return self.file is not None and self.suffix in DRAWN_MESH_SUFFIXES


@dataclass
class MjcfGeom:
    """A ``<geom>``: its type, MuJoCo's own sizes (half-sizes, radii and half-lengths, in metres), its
    placement in its body's frame, its colour, its group and, for a mesh, the asset it names."""

    name: str
    body: str
    type: str
    size: list[float]
    local: Matrix
    rgba: tuple[float, float, float, float]
    group: int = 0
    mesh: str | None = None
    material: str | None = None
    where: str = ""

    @property
    def drawn(self) -> bool:
        """Whether the viewer draws it: a visual group, and a shape or a mesh it can make."""
        return self.group in DRAWN_GROUPS and self.visual() is not None

    def visual(self) -> tuple | None:
        """The viewer's shape of it -- ``("box"|"cylinder"|"sphere"|"capsule", {dimensions})`` in the viewer's
        full sizes, or ``("mesh", name)`` -- None for a geom no view draws (a heightfield, an SDF, an
        ellipsoid, an unbounded plane)."""
        size = self.size
        if self.type == "sphere" and size:
            return ("sphere", {"radius": size[0]})
        if self.type == "capsule" and len(size) >= 2:
            return ("capsule", {"radius": size[0], "length": 2 * size[1]})
        if self.type == "cylinder" and len(size) >= 2:
            return ("cylinder", {"radius": size[0], "length": 2 * size[1]})
        if self.type == "box" and len(size) >= 3:
            return ("box", {"size": [2 * size[0], 2 * size[1], 2 * size[2]]})
        if self.type == "plane" and len(size) >= 2 and size[0] > 0 and size[1] > 0:
            # A plane has one side; it is drawn as the thinnest box the viewer shows, its top at the plane.
            return ("box", {"size": [2 * size[0], 2 * size[1], PLANE_THICKNESS]})
        if self.type == "mesh" and self.mesh:
            return ("mesh", self.mesh)
        return None


#: A plane's drawn thickness (metres): a visible slab whose top face is the plane.
PLANE_THICKNESS = 0.002


@dataclass
class MjcfJoint:
    """A ``<joint>`` of a body: its type, its anchor and axis in the body's frame, its range in radians
    or metres around ``ref`` (None: unlimited) and ``ref``, the authored position its zero is."""

    name: str
    body: str
    type: str
    pos: list[float]
    axis: list[float]
    range: tuple[float, float] | None
    ref: float = 0.0
    where: str = ""


@dataclass
class MjcfBody:
    """A body: its parent (None for the world), its frame in its parent's and in the model's space at rest
    (metres), its joints in their order, its geoms and its inertial, as read."""

    name: str
    parent: str | None
    local: Matrix
    rest: Matrix
    joints: list[MjcfJoint] = field(default_factory=list)
    geoms: list[MjcfGeom] = field(default_factory=list)
    inertial: dict[str, Any] | None = None
    where: str = ""


@dataclass
class MjcfModel:
    """One MJCF as read: its name, its main file and every file read with it, its compiler settings, its
    bodies in tree order (``world`` first), its mesh and material assets, its couplings and its keyframes."""

    name: str
    path: Path
    files: list[Path]
    compiler: dict[str, str]
    bodies: dict[str, MjcfBody]
    meshes: dict[str, MjcfMesh]
    materials: dict[str, tuple[float, float, float, float]]
    couplings: list[tuple[str, str, float, float]] = field(default_factory=list)  # follower, leader, multiplier, offset
    keyframes: dict[str, dict[str, float]] = field(default_factory=dict)  # key name: joint name -> radians or metres
    #: The element kinds the compiler expands that this reader passed over, each named once.
    compile_only: list[str] = field(default_factory=list)

    @property
    def joints(self) -> list[MjcfJoint]:
        return [joint for body in self.bodies.values() for joint in body.joints]

    @property
    def geoms(self) -> list[MjcfGeom]:
        return [geom for body in self.bodies.values() for geom in body.geoms]

    def mesh_files(self) -> list[Path]:
        """Every mesh file a drawn geom names, once each, in order."""
        seen: list[Path] = []
        for geom in self.geoms:
            mesh = self.meshes.get(geom.mesh or "")
            if mesh is not None and mesh.file is not None and mesh.file not in seen:
                seen.append(mesh.file)
        return seen


# --- the reader --------------------------------------------------------------------------------


def is_mjcf_file(path: Path) -> bool:
    """Whether ``path`` is an MJCF: a ``.mjcf``, or a ``.xml`` whose root element is ``<mujoco>`` (read
    from its first bytes, so a folder of XML files is told apart without parsing each). False for a file
    that is not there."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".mjcf":
        return True
    if suffix != ".xml":
        return False
    try:
        with open(path, "rb") as handle:
            head = handle.read(4096)
    except OSError:
        return False
    return _root_tag(head) == "mujoco"


def _root_tag(head: bytes) -> str | None:
    """The first element's name in ``head``, past the declaration, comments and a doctype."""
    text = head.decode("utf-8", errors="replace")
    index = 0
    while True:
        start = text.find("<", index)
        if start < 0:
            return None
        if text.startswith("<?", start):
            end = text.find("?>", start)
        elif text.startswith("<!--", start):
            end = text.find("-->", start)
        elif text.startswith("<!", start):
            end = text.find(">", start)
        else:
            name = ""
            for char in text[start + 1:]:
                if char.isspace() or char in "/>":
                    break
                name += char
            return name.rsplit(":", 1)[-1] or None
        if end < 0:
            return None
        index = end + 1


class _Reader:
    """One read of one model: the findings it adds as it goes, and the model when the file is one."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.base = path.parent
        self.display = display_path(path)
        self.findings = Findings()
        self.files: list[Path] = [path]
        self.compiler: dict[str, str] = {}
        self.defaults: dict[str, dict[str, dict[str, str]]] = {"main": {}}
        self.meshes: dict[str, MjcfMesh] = {}
        self.materials: dict[str, tuple[float, float, float, float]] = {}
        #: The materials with a texture: the viewer draws no texture, so a geom of one is MuJoCo's plain grey
        #: rather than the material's tint (white, on a textured material, means "no tint").
        self.textured: set[str] = set()
        self.bodies: dict[str, MjcfBody] = {}
        self.joint_names: set[str] = set()
        self.geom_names: set[str] = set()
        self.compile_only: list[str] = []
        self.unnamed = 0

    # --- findings ---

    def error(self, code: str, message: str, *, where: str = "", hint: str | None = None) -> None:
        self.findings.add("error", code, message, path=where or self.display, hint=hint)

    def warning(self, code: str, message: str, *, where: str = "", hint: str | None = None) -> None:
        self.findings.add("warning", code, message, path=where or self.display, hint=hint)

    def info(self, code: str, message: str, *, where: str = "") -> None:
        self.findings.add("info", code, message, path=where or self.display)

    # --- the document and its includes ---

    def parse(self) -> ET.Element | None:
        try:
            root = ET.parse(self.path).getroot()
        except ET.ParseError as exc:
            self.error("invalid_xml", f"{self.display} is not well-formed XML: {exc}")
            return None
        except (OSError, UnicodeDecodeError) as exc:
            self.error("unreadable_file", f"{self.display} could not be read: {exc}")
            return None
        if local_name(root.tag) != "mujoco":
            self.error("not_mjcf", f"{self.display} is not an MJCF: its root element is <{local_name(root.tag)}>, "
                                   f"not <mujoco>")
            return None
        self._expand_includes(root, {self.path.resolve()})
        return root

    def _expand_includes(self, element: ET.Element, seen: set[Path]) -> None:
        index = 0
        while index < len(element):
            child = element[index]
            if local_name(child.tag) != "include":
                self._expand_includes(child, seen)
                index += 1
                continue
            name = str(child.attrib.get("file") or "").strip()
            where = f"{self.display} <include>"
            element.remove(child)
            if not name:
                self.error("include_without_file", "<include> names no file", where=where)
                continue
            target = (self.base / name).resolve()
            if target in seen:
                self.error("include_repeated", f"{name} is included twice; MuJoCo includes a file once", where=where)
                continue
            if not target.is_file():
                self.error("include_not_found", f"included file {name} is not there (MuJoCo resolves an include "
                                                f"against the main file's folder, {self.base.name or '.'})",
                           where=where)
                continue
            seen.add(target)
            self.files.append(target)
            try:
                included = ET.parse(target).getroot()
            except (ET.ParseError, OSError, UnicodeDecodeError) as exc:
                self.error("include_invalid", f"included file {name} could not be read: {exc}", where=where)
                continue
            for offset, grandchild in enumerate(list(included)):
                element.insert(index + offset, grandchild)
            # The spliced children may hold includes of their own; the loop reaches them next.

    # --- numbers ---

    def numbers(self, text: Any, count: int | None, *, where: str, name: str) -> list[float] | None:
        """``text`` as ``count`` floats (any number, for None); None, with an error, for anything else."""
        if text is None:
            return None
        try:
            values = [float(piece) for piece in str(text).replace(",", " ").split()]
        except ValueError:
            self.error("bad_number", f"{name}={str(text)!r} is not a list of numbers", where=where)
            return None
        if count is not None and len(values) != count:
            self.error("bad_number_count", f"{name} wants {count} numbers, not {len(values)} ({str(text)!r})",
                       where=where)
            return None
        return values

    def angle(self, value: float) -> float:
        """A file angle in radians: degrees unless ``<compiler angle="radian">``."""
        return value if self.compiler.get("angle", "degree") == "radian" else math.radians(value)

    # --- defaults ---

    def read_defaults(self, root: ET.Element) -> None:
        for default in children(root, "default"):
            self._read_default(default, parent="main", top=True)

    def _read_default(self, element: ET.Element, *, parent: str, top: bool) -> None:
        name = str(element.attrib.get("class") or "").strip()
        if not name:
            if not top:
                self.error("default_without_class", "a nested <default> needs a class name",
                           where=f"{self.display} <default>")
                return
            name = "main"
        if name != "main" and name in self.defaults:
            self.error("duplicate_default_class", f"default class {name!r} is declared twice",
                       where=f"{self.display} <default class={name!r}>")
        inherited = {tag: dict(attributes) for tag, attributes in self.defaults.get(parent, {}).items()}
        for child in list(element):
            tag = local_name(child.tag)
            if tag == "default":
                continue
            if tag in _DEFAULTED or True:  # every tag's attributes are kept; only _DEFAULTED are read later
                merged = dict(inherited.get(tag, {}))
                merged.update({key: value for key, value in child.attrib.items() if key != "class"})
                inherited[tag] = merged
        self.defaults[name] = inherited
        for child in children(element, "default"):
            self._read_default(child, parent=name, top=False)

    def attributes(self, element: ET.Element, tag: str, childclass: str, *, where: str) -> dict[str, str]:
        """``element``'s attributes over its class's defaults for ``tag`` (its ``class``, else ``childclass``)."""
        name = str(element.attrib.get("class") or "").strip() or childclass or "main"
        defaults = self.defaults.get(name)
        if defaults is None:
            self.error("unknown_default_class", f"class {name!r} is no <default> of the model", where=where)
            defaults = self.defaults["main"]
        merged = dict(defaults.get(tag, {}))
        merged.update(element.attrib)
        return merged

    # --- the compiler and the assets ---

    def read_compiler(self, root: ET.Element) -> None:
        for compiler in children(root, "compiler"):
            self.compiler.update({key: str(value).strip() for key, value in compiler.attrib.items()})
        angle = self.compiler.get("angle", "degree")
        if angle not in ("degree", "radian"):
            self.error("bad_compiler_angle", f"<compiler angle={angle!r}> is neither degree nor radian")
            self.compiler["angle"] = "degree"
        sequence = self.compiler.get("eulerseq", "xyz")
        try:
            euler_matrix([0.0, 0.0, 0.0], sequence)
        except ValueError as exc:
            self.error("bad_compiler_eulerseq", str(exc))
            self.compiler["eulerseq"] = "xyz"

    def asset_path(self, file: str, *, kind: str) -> Path:
        """A mesh or texture file by the compiler's rules: ``strippath`` keeps its name alone; an absolute
        path stands; else it is under ``meshdir`` (or ``texturedir``), itself under the main file's folder
        unless absolute; ``assetdir`` names both."""
        name = os.path.basename(file) if self.compiler.get("strippath", "false").lower() == "true" else file
        folder = self.compiler.get(f"{kind}dir") or self.compiler.get("assetdir") or ""
        path = Path(name)
        if path.is_absolute():
            return path
        base = Path(folder) if folder and Path(folder).is_absolute() else self.base / folder
        return (base / path).resolve()

    def read_assets(self, root: ET.Element) -> None:
        for asset in children(root, "asset"):
            for mesh in children(asset, "mesh"):
                where = f"{self.display} <mesh>"
                attributes = self.attributes(mesh, "mesh", "", where=where)
                file = str(attributes.get("file") or "").strip()
                name = str(attributes.get("name") or "").strip() or (Path(file).stem if file else "")
                where = f"{self.display} <mesh name={name!r}>"
                if not name:
                    self.error("mesh_without_name", "a <mesh> given inline needs a name", where=where)
                    continue
                if name in self.meshes:
                    self.error("duplicate_mesh_name", f"mesh {name!r} is declared twice", where=where)
                scale = self.numbers(attributes.get("scale"), 3, where=where, name="scale") or [1.0, 1.0, 1.0]
                if not file:
                    self.meshes[name] = MjcfMesh(name, None, tuple(scale))
                    self.warning("mesh_not_drawn", f"mesh {name!r} is given inline (vertex), which the viewer does not "
                                                   f"draw; a geom of it is skipped", where=where)
                    continue
                path = self.asset_path(file, kind="mesh")
                if path.suffix.lower() not in MESH_SUFFIXES:
                    self.error("mesh_format_unknown", f"mesh {name!r} names {file}, which is no STL, OBJ or MSH",
                               where=where)
                elif not path.is_file():
                    self.error("mesh_file_not_found", f"mesh {name!r} names {file}, which is not there ({path})",
                               where=where)
                elif path.suffix.lower() == ".msh":
                    self.warning("mesh_not_drawn", f"mesh {name!r} is an MSH (MuJoCo's binary), which the viewer does "
                                                   f"not draw; a geom of it is skipped", where=where)
                self.meshes[name] = MjcfMesh(name, path, tuple(scale))
            for material in children(asset, "material"):
                attributes = self.attributes(material, "material", "", where=f"{self.display} <material>")
                name = str(attributes.get("name") or "").strip()
                where = f"{self.display} <material name={name!r}>"
                if not name:
                    self.error("material_without_name", "a <material> needs a name", where=where)
                    continue
                rgba = self.numbers(attributes.get("rgba"), 4, where=where, name="rgba")
                self.materials[name] = tuple(rgba) if rgba else (1.0, 1.0, 1.0, 1.0)
                if str(attributes.get("texture") or "").strip():
                    self.textured.add(name)

    # --- orientation ---

    def orientation(self, attributes: dict[str, str], *, where: str) -> list[list[float]]:
        """The rotation one of ``quat``, ``euler``, ``axisangle``, ``xyaxes`` or ``zaxis`` gives; identity for
        none; an error, and the first, for several."""
        given = [name for name in _ORIENTATIONS if attributes.get(name) is not None]
        if len(given) > 1:
            self.error("several_orientations", f"{', '.join(given)} together: an element takes one orientation",
                       where=where)
        if not given:
            return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        name = given[0]
        counts = {"quat": 4, "euler": 3, "axisangle": 4, "xyaxes": 6, "zaxis": 3}
        values = self.numbers(attributes[name], counts[name], where=where, name=name)
        if values is None:
            return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        try:
            if name == "quat":
                return quaternion_matrix(values)
            if name == "euler":
                return euler_matrix([self.angle(value) for value in values], self.compiler.get("eulerseq", "xyz"))
            if name == "axisangle":
                return axis_angle_matrix(values[:3], self.angle(values[3]))
            if name == "xyaxes":
                return xy_axes_matrix(values)
            return z_axis_matrix(values)
        except ValueError as exc:
            self.error("bad_orientation", f"{name}: {exc}", where=where)
            return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

    def placement(self, attributes: dict[str, str], *, where: str) -> Matrix:
        pos = self.numbers(attributes.get("pos"), 3, where=where, name="pos") or [0.0, 0.0, 0.0]
        return _with_rotation(self.orientation(attributes, where=where), pos)

    # --- bodies ---

    def read_worldbody(self, root: ET.Element) -> None:
        worlds = children(root, "worldbody")
        if not worlds:
            self.error("missing_worldbody", f"{self.display} has no <worldbody>")
            return
        # Several <worldbody> elements (a scene's own and its include's) are one: MuJoCo merges every
        # repeated top-level section, as the assets, defaults and keyframes above are merged here.
        world = MjcfBody("world", None, identity(), identity(), where=f"{self.display} <worldbody>")
        self.bodies["world"] = world
        for element in worlds:
            self._read_body_children(element, world, identity(), childclass="")

    def _body_name(self, element: ET.Element, *, where: str) -> str:
        name = str(element.attrib.get("name") or "").strip()
        if not name:
            # MuJoCo allows an unnamed body; the viewer needs a name for every link, so one is made as
            # MuJoCo's own tools print one: body + its index in reading order.
            self.unnamed += 1
            name = f"body{len(self.bodies)}"
            while name in self.bodies:
                name += "_"
            return name
        if name in self.bodies:
            self.error("duplicate_body_name", f"body {name!r} is declared twice", where=where)
            suffix = 2
            while f"{name}#{suffix}" in self.bodies:
                suffix += 1
            name = f"{name}#{suffix}"
        return name

    def _read_body_children(self, element: ET.Element, body: MjcfBody, frame: Matrix, *, childclass: str) -> None:
        """What ``element`` holds, in ``body``: ``frame`` is the transform ``<frame>`` groups above it apply
        in the body's own frame (identity for the body element itself)."""
        for child in list(element):
            tag = local_name(child.tag)
            if tag == "body":
                self._read_body(child, body, frame, childclass=childclass)
            elif tag == "frame":
                where = f"{body.where} <frame>"
                inner = multiply(frame, self.placement(child.attrib, where=where))
                self._read_body_children(child, body, inner, childclass=str(child.attrib.get("childclass") or
                                                                             "").strip() or childclass)
            elif tag == "geom":
                self._read_geom(child, body, frame, childclass=childclass)
            elif tag in ("joint", "freejoint"):
                self._read_joint(child, body, frame, childclass=childclass, free=tag == "freejoint")
            elif tag == "inertial":
                body.inertial = self._read_inertial(child, body, frame)
            elif tag in COMPILE_ONLY:
                if tag not in self.compile_only:
                    self.compile_only.append(tag)
                    self.warning("compile_only_element",
                                 f"<{tag}> is expanded by MuJoCo's compiler and read as nothing here: what it makes "
                                 f"is not drawn", where=f"{body.where} <{tag}>",
                                 hint="cad mjcf validate --compile required checks the model as MuJoCo compiles it")
            # site, camera, light, plugin, attach: nothing the viewer draws or poses.

    def _read_body(self, element: ET.Element, parent: MjcfBody, frame: Matrix, *, childclass: str) -> None:
        name = self._body_name(element, where=f"{self.display} <body>")
        where = f"{self.display} body {name!r}"
        attributes = self.attributes(element, "body", childclass, where=where) if element.attrib.get("class") else \
            {**self.defaults.get(childclass or "main", {}).get("body", {}), **element.attrib}
        local = multiply(frame, self.placement(attributes, where=where))
        body = MjcfBody(name, parent.name, local, multiply(parent.rest, local), where=where)
        self.bodies[name] = body
        own_class = str(element.attrib.get("childclass") or "").strip() or childclass
        self._read_body_children(element, body, identity(), childclass=own_class)

    def _read_inertial(self, element: ET.Element, body: MjcfBody, frame: Matrix) -> dict[str, Any]:
        where = f"{body.where} <inertial>"
        local = multiply(frame, self.placement(element.attrib, where=where))
        mass = self.numbers(element.attrib.get("mass"), 1, where=where, name="mass")
        diagonal = self.numbers(element.attrib.get("diaginertia"), 3, where=where, name="diaginertia")
        full = self.numbers(element.attrib.get("fullinertia"), 6, where=where, name="fullinertia")
        inertia = None
        if diagonal:
            inertia = {"ixx": diagonal[0], "iyy": diagonal[1], "izz": diagonal[2], "ixy": 0.0, "ixz": 0.0, "iyz": 0.0}
        elif full:
            inertia = {"ixx": full[0], "iyy": full[1], "izz": full[2], "ixy": full[3], "ixz": full[4], "iyz": full[5]}
        if mass is None:
            self.error("inertial_without_mass", "<inertial> needs a mass", where=where)
        return {"mass": mass[0] if mass else None, "origin": local, "inertia": inertia}

    def _read_geom(self, element: ET.Element, body: MjcfBody, frame: Matrix, *, childclass: str) -> None:
        name = str(element.attrib.get("name") or "").strip()
        where = f"{body.where} geom {name!r}" if name else f"{body.where} geom {len(body.geoms) + 1}"
        if name:
            if name in self.geom_names:
                self.error("duplicate_geom_name", f"geom {name!r} is declared twice", where=where)
            self.geom_names.add(name)
        attributes = self.attributes(element, "geom", childclass, where=where)
        kind = str(attributes.get("type") or "sphere").strip()
        if kind not in GEOM_TYPES:
            self.error("unknown_geom_type", f"geom type {kind!r} is none of {', '.join(GEOM_TYPES)}", where=where)
            return
        size = self.numbers(attributes.get("size"), None, where=where, name="size") or []
        local = multiply(frame, self.placement(attributes, where=where))
        fromto = self.numbers(attributes.get("fromto"), 6, where=where, name="fromto")
        if fromto is not None:
            if kind not in ("capsule", "cylinder", "box", "ellipsoid"):
                self.error("fromto_on_shape", f"fromto is for a capsule, cylinder, box or ellipsoid, not a {kind}",
                           where=where)
                return
            start, end = fromto[:3], fromto[3:]
            axis = [b - a for a, b in zip(start, end, strict=True)]
            length = _norm(axis)
            if length < _EPSILON:
                self.error("fromto_degenerate", "fromto's two points coincide", where=where)
                return
            middle = [(a + b) / 2 for a, b in zip(start, end, strict=True)]
            # MuJoCo's compiler points the geom's Z from the second point back to the first (mjuu_z2quat on
            # the segment); matched, so a box placed by fromto keeps its x and y where MuJoCo puts them.
            local = multiply(frame, _with_rotation(z_axis_matrix([-value for value in axis]), middle))
            half = length / 2
            size = [size[0] if size else 0.0, half] if kind in ("capsule", "cylinder") else \
                [size[0] if size else 0.0, size[1] if len(size) > 1 else 0.0, half]
        needed = {"sphere": 1, "capsule": 2, "cylinder": 2, "box": 3, "ellipsoid": 3, "plane": 2, "hfield": 0,
                  "sdf": 0, "mesh": 0}[kind]
        if len(size) < needed:
            self.error("geom_size", f"a {kind} needs {needed} size value{'s' if needed > 1 else ''}"
                                    f"{' (or fromto)' if kind in ('capsule', 'cylinder', 'box', 'ellipsoid') else ''}"
                                    f", not {len(size)}", where=where)
            return
        if any(value < 0 for value in size[:needed]) or (needed and all(value <= 0 for value in size[:needed])
                                                         and kind != "plane"):
            self.error("geom_size", f"a {kind}'s size must be positive, not {size[:needed]}", where=where)
            return
        mesh = str(attributes.get("mesh") or "").strip() or None
        if kind == "mesh":
            if not mesh:
                self.error("mesh_geom_without_mesh", "a mesh geom names no mesh asset", where=where)
                return
            if mesh not in self.meshes:
                self.error("mesh_asset_unknown", f"mesh {mesh!r} is no <mesh> of the model's <asset>", where=where)
                return
        elif mesh and mesh not in self.meshes:
            self.error("mesh_asset_unknown", f"mesh {mesh!r} is no <mesh> of the model's <asset>", where=where)
            return
        material = str(attributes.get("material") or "").strip() or None
        rgba = self.numbers(attributes.get("rgba"), 4, where=where, name="rgba")
        colour: tuple[float, float, float, float] = _DEFAULT_RGBA
        if material is not None:
            if material not in self.materials:
                self.error("material_unknown", f"material {material!r} is no <material> of the model's <asset>",
                           where=where)
                return
            colour = _DEFAULT_RGBA if material in self.textured else self.materials[material]
        if rgba is not None and (material is None or element.attrib.get("rgba") is not None):
            colour = (rgba[0], rgba[1], rgba[2], rgba[3])
        group_values = self.numbers(attributes.get("group"), 1, where=where, name="group")
        group = int(group_values[0]) if group_values else 0
        geom = MjcfGeom(name, body.name, kind, size, local, colour, group, mesh, material, where)
        body.geoms.append(geom)
        if group in DRAWN_GROUPS and geom.visual() is None:
            if kind == "plane":
                # Every scene's floor: an unbounded plane, which the viewer's grid stands in for. An info, so
                # --strict does not fail a scene for its floor.
                self.info("geom_not_drawn", "an unbounded plane (a size of 0) is not drawn by the viewer; its grid "
                                            "stands in for the floor", where=where)
                return
            what = {"hfield": "a heightfield", "sdf": "an SDF geom", "ellipsoid": "an ellipsoid"}.get(kind, f"a {kind}")
            self.warning("geom_not_drawn", f"{what} is not drawn by the viewer; the geom is skipped", where=where)

    def _read_joint(self, element: ET.Element, body: MjcfBody, frame: Matrix, *, childclass: str, free: bool) -> None:
        name = str(element.attrib.get("name") or "").strip()
        where = f"{body.where} joint {name!r}" if name else f"{body.where} joint {len(body.joints) + 1}"
        if body.parent is None:
            self.error("joint_in_worldbody", "a joint belongs to a body, not to <worldbody>", where=where)
            return
        if name:
            if name in self.joint_names:
                self.error("duplicate_joint_name", f"joint {name!r} is declared twice", where=where)
            self.joint_names.add(name)
        attributes = {"type": "free", **element.attrib} if free else self.attributes(element, "joint", childclass,
                                                                                   where=where)
        kind = str(attributes.get("type") or "hinge").strip()
        if kind not in JOINT_TYPES:
            self.error("unknown_joint_type", f"joint type {kind!r} is none of {', '.join(JOINT_TYPES)}", where=where)
            return
        pos = self.numbers(attributes.get("pos"), 3, where=where, name="pos") or [0.0, 0.0, 0.0]
        axis = self.numbers(attributes.get("axis"), 3, where=where, name="axis") or [0.0, 0.0, 1.0]
        if kind in ("hinge", "slide") and _unit(axis) is None:
            self.error("axis_zero", "a joint's axis cannot be of zero length", where=where)
            return
        angular = kind == "hinge"
        ref_values = self.numbers(attributes.get("ref"), 1, where=where, name="ref")
        ref = (self.angle(ref_values[0]) if angular else ref_values[0]) if ref_values else 0.0
        joint_range: tuple[float, float] | None = None
        values = self.numbers(attributes.get("range"), 2, where=where, name="range")
        limited = str(attributes.get("limited") or "auto").strip().lower()
        autolimits = self.compiler.get("autolimits", "true").lower() == "true"
        if values is not None and kind in ("hinge", "slide"):
            low, high = (self.angle(values[0]), self.angle(values[1])) if angular else (values[0], values[1])
            if low > high:
                self.error("range_inverted", f"range {values} runs backwards", where=where)
                return
            if limited == "true" or (limited == "auto" and autolimits):
                joint_range = (low, high)
            elif limited == "auto" and not autolimits:
                self.warning("range_unlimited", "a range with limited=\"auto\" and autolimits=\"false\" limits "
                                                "nothing; the joint is read as unlimited", where=where)
        elif limited == "true" and kind in ("hinge", "slide"):
            self.error("limited_without_range", "limited=\"true\" with no range", where=where)
            return
        if kind == "free":
            # The usual floating base of a legged robot or a loose object: drawn where it is authored, an info.
            self.info("joint_not_posable", f"a free joint is not posable in the viewer: body {body.name!r} is drawn "
                                           f"where it is authored", where=where)
        elif kind == "ball":
            self.warning("joint_not_posable", f"a ball joint is not posable in the viewer: body {body.name!r} is "
                                              f"drawn where it is authored", where=where)
        frame_pos = transform(frame, pos)
        frame_axis = rotate(frame, axis)
        body.joints.append(MjcfJoint(name, body.name, kind, frame_pos, frame_axis, joint_range, ref, where))

    # --- couplings and keyframes ---

    def read_equalities(self, root: ET.Element) -> list[tuple[str, str, float, float]]:
        couplings: list[tuple[str, str, float, float]] = []
        for equality in children(root, "equality"):
            for joint in children(equality, "joint"):
                where = f"{self.display} <equality><joint>"
                follower = str(joint.attrib.get("joint1") or "").strip()
                leader = str(joint.attrib.get("joint2") or "").strip()
                if not follower or not leader:
                    continue  # a joint1 alone holds a joint at a value: no coupling
                for name in (follower, leader):
                    if name not in self.joint_names:
                        self.error("equality_unknown_joint", f"<equality><joint> names joint {name!r}, which the model "
                                                             f"has not", where=where)
                        break
                else:
                    polycoef = self.numbers(joint.attrib.get("polycoef"), None, where=where, name="polycoef") or [0.0, 1.0]
                    polycoef = (polycoef + [0.0] * 5)[:5]
                    if any(abs(value) > _EPSILON for value in polycoef[2:]):
                        self.info("equality_not_linear", f"the coupling of {follower!r} to {leader!r} is a polynomial "
                                                         f"the viewer does not follow; {follower!r} is a control of its own",
                                  where=where)
                        continue
                    couplings.append((follower, leader, polycoef[1], polycoef[0]))
        return couplings

    def read_keyframes(self, root: ET.Element) -> dict[str, dict[str, float]]:
        # qpos is laid out in the joints' tree order: a free joint 7, a ball 4, a hinge or a slide 1.
        layout: list[tuple[MjcfJoint, int]] = []
        address = 0
        for body in self.bodies.values():
            for joint in body.joints:
                layout.append((joint, address))
                address += {"free": 7, "ball": 4}.get(joint.type, 1)
        keyframes: dict[str, dict[str, float]] = {}
        for keyframe in children(root, "keyframe"):
            for index, key in enumerate(children(keyframe, "key")):
                name = str(key.attrib.get("name") or "").strip() or f"key{index}"
                where = f"{self.display} <key name={name!r}>"
                values = self.numbers(key.attrib.get("qpos"), None, where=where, name="qpos")
                if values is None:
                    continue
                if len(values) != address:
                    self.warning("keyframe_length", f"key {name!r} gives {len(values)} qpos values; the model's joints "
                                                    f"take {address}; the key is not a pose", where=where)
                    continue
                pose = {joint.name: values[at] for joint, at in layout if joint.type in ("hinge", "slide") and joint.name}
                keyframes[name] = pose
        return keyframes

    # --- the model ---

    def read(self) -> MjcfModel | None:
        root = self.parse()
        if root is None:
            return None
        self.read_compiler(root)
        self.read_defaults(root)
        self.read_assets(root)
        self.read_worldbody(root)
        couplings = self.read_equalities(root)
        keyframes = self.read_keyframes(root)
        if self.findings.errors:
            return None
        name = str(root.attrib.get("model") or "").strip() or self.path.stem
        return MjcfModel(name, self.path, self.files, dict(self.compiler), self.bodies, self.meshes, self.materials,
                         couplings, keyframes, list(self.compile_only))


def read_mjcf(path: Path) -> tuple[MjcfModel | None, Findings]:
    """``path`` read as an MJCF: the model and every finding; the model None where an error stops the read
    (the findings say which)."""
    reader = _Reader(Path(path))
    return reader.read(), reader.findings


# --- the viewer's articulation ---------------------------------------------------------------------


@dataclass
class Visual:
    """A link's visual as the viewer and the stills take one: its placement in its link's frame, its shape --
    ``("box"|"cylinder"|"sphere"|"capsule", dimensions)`` in full sizes or ``("file", path, scale)`` -- its
    colour (``#rrggbb``), its alpha and the name a row calls it."""

    id: str
    link: str
    local: Matrix
    shape: tuple
    color: str
    alpha: float
    label: str
    geom: MjcfGeom


@dataclass
class LinkJoint:
    """A joint between two links as the viewer poses one: ``fixed``, ``revolute``, ``continuous`` or
    ``prismatic``; its frame (the anchor, at rest, in the model's space) and axis (a unit vector there); its
    range in radians or metres around zero (None: unbounded); the leader it follows, if any."""

    name: str
    type: str
    parent: str
    child: str
    frame: Matrix
    axis: list[float] | None
    lower: float | None
    upper: float | None
    mimic: tuple[str, float, float] | None = None
    source: MjcfJoint | None = None


@dataclass
class Articulation:
    """The model as a tree of links: each link's rest frame, its visuals, the joints in parents-first order,
    the poses (keyframes, in the viewer's control units: degrees for a turn, metres for a slide) and the
    inertials, by link."""

    root: str
    links: dict[str, Matrix]
    visuals: dict[str, list[Visual]]
    joints: list[LinkJoint]
    poses: dict[str, dict[str, float]]
    inertials: dict[str, dict[str, Any]]


def _hex(rgba: tuple[float, ...]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(float(value) * 255))):02x}" for value in rgba[:3])


def articulate(model: MjcfModel) -> Articulation:
    """The model as the viewer poses it. A body is a link; a body with one hinge or slide hangs from its parent
    by that joint; one with several is a chain, a link per joint, each at the body's frame, the joints applied in
    their order (MuJoCo's composition); one with none, or with a ball or free joint alone, hangs fixed."""
    links: dict[str, Matrix] = {}
    visuals: dict[str, list[Visual]] = {}
    joints: list[LinkJoint] = []
    inertials: dict[str, dict[str, Any]] = {}
    taken: set[str] = {joint.name for joint in model.joints if joint.name}

    def unique(name: str) -> str:
        candidate = name
        suffix = 2
        while candidate in taken:
            candidate = f"{name}#{suffix}"
            suffix += 1
        taken.add(candidate)
        return candidate

    for body in model.bodies.values():
        links[body.name] = body.rest
        visuals[body.name] = []
        if body.inertial is not None:
            inertials[body.name] = body.inertial
        for index, geom in enumerate(body.geoms, start=1):
            if not geom.drawn:
                continue
            visual = geom.visual()
            assert visual is not None
            if visual[0] == "mesh":
                mesh = model.meshes[visual[1]]
                if not mesh.drawn:
                    continue
                assert mesh.file is not None
                shape: tuple = ("file", mesh.file, mesh.scale)
                label = geom.name or mesh.file.name
            else:
                shape = visual
                label = geom.name or geom.type
            local = geom.local
            if geom.type == "plane":
                # The slab hangs below the plane: its top face is the plane itself.
                local = multiply(geom.local, translation([0.0, 0.0, -PLANE_THICKNESS / 2]))
            visuals[body.name].append(Visual(f"{body.name}:v{index}", body.name, local, shape, _hex(geom.rgba),
                                             float(geom.rgba[3]), label, geom))
        if body.parent is None:
            continue
        moving = [joint for joint in body.joints]
        if not moving:
            joints.append(LinkJoint(unique(body.name), "fixed", body.parent, body.name, body.rest, None, None, None))
            continue
        parent = body.parent
        for position, joint in enumerate(moving):
            last = position == len(moving) - 1
            child = body.name if last else f"{body.name}/{joint.name or position + 1}"
            if not last:
                links[child] = body.rest
                visuals[child] = []
            kind = ARTICULATED[joint.type]
            if kind == "revolute" and joint.range is None:
                kind = "continuous"
            frame = multiply(body.rest, translation(joint.pos))
            axis = _unit(rotate(body.rest, joint.axis)) if kind != "fixed" else None
            lower = upper = None
            if joint.range is not None and kind in ("revolute", "prismatic"):
                lower, upper = joint.range[0] - joint.ref, joint.range[1] - joint.ref
            # An unnamed joint (MuJoCo allows one) is named for its body and its place, as the chain's links are.
            name = joint.name or unique(f"{body.name}/joint{position + 1}")
            joints.append(LinkJoint(name, kind, parent, child, frame, axis, lower, upper, source=joint))
            parent = child

    by_name = {joint.name: joint for joint in joints}
    for follower, leader, multiplier, offset in model.couplings:
        if follower in by_name and leader in by_name and by_name[follower].type in ("revolute", "continuous",
                                                                                     "prismatic"):
            # MuJoCo's constraint is on qpos; the viewer's control is around ref: follower - ref_f = m (leader -
            # ref_l) + c, so the offset carries both refs.
            source_f, source_l = by_name[follower].source, by_name[leader].source
            ref_f = source_f.ref if source_f else 0.0
            ref_l = source_l.ref if source_l else 0.0
            by_name[follower].mimic = (leader, multiplier, offset + multiplier * ref_l - ref_f)

    poses: dict[str, dict[str, float]] = {}
    for key, values in model.keyframes.items():
        pose: dict[str, float] = {}
        for joint_name, value in values.items():
            joint = by_name.get(joint_name)
            if joint is None or joint.source is None or joint.type == "fixed" or joint.mimic is not None:
                continue
            control = value - joint.source.ref
            pose[joint_name] = math.degrees(control) if joint.type in ("revolute", "continuous") else control
        poses[key] = pose
    return Articulation("world", links, visuals, joints, poses, inertials)

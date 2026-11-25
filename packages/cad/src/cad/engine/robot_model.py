"""A robot description as its readers articulate it: a tree of links, each placed at rest, with the
visuals drawn on it and the joints between them -- what the engine's readers of a robot
description make (``urdf_source``: a URDF and an SRDF's group states over it)
and what the viewer's payload (the server's ``robot_payload``) and the
stills (``formats/robot.py``) each take a view of. A description is read once, here; the two views
translate shapes and units, and decide what each can draw.

**The articulation** (``Articulation``): each link's rest frame in the description's space (the
description as written, every joint at zero), a 4x4 of lists in
metres; each link's visuals (``Visual``: its placement in its link's frame, its shape -- ``("box",
{"size"})``, ``("cylinder", {"radius", "length"})``, ``("sphere", {"radius"})`` in full sizes,
``("file", path, scale)`` for a mesh file, the path None where the reference names no local file,
``("unknown",)`` for geometry that is none of these -- its colour, the name a row calls it); the joints (``LinkJoint``: fixed, revolute, continuous
or prismatic, the anchor frame and the unit axis at rest, the range in radians or metres, the leader a
mimic follows, a four-bar's numbers as written); the named poses in control units (degrees for a turn,
metres for a slide) and an SRDF's ``home``. A URDF's links, joints, visuals and
collisions also carry their facts as written (``facts``: what the payload shows a person reading the
description back), read when the reader's ``Dialect`` asks for them.

**Dialects.** The viewer's payload and the stills read robots for years with readers of their own,
and the two disagreed on a few details; each disagreement is kept here, named, rather than settled in
passing: ``Dialect`` holds how one consumer words a refusal (``words``, by code: a word of None reads
leniently what the other refuses). The standard library alone
(the validation family's rule, ``tests/python/global/test_robot_modules_stdlib_pure.py``): ElementTree
and arithmetic on 4x4 matrices as lists, in one order of operations, so every view of a read is the
same numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
import xml.etree.ElementTree as ET

__all__ = ["ANGULAR", "Articulation", "Dialect", "LinkJoint", "MOVING", "Matrix", "SourceError", "Visual",
           "WORDS"]

Matrix = list[list[float]]

MOVING = ("revolute", "continuous", "prismatic")
ANGULAR = ("revolute", "continuous")

#: Every refusal a reader of a URDF or an SRDF makes, by code, in words of its own; a consumer's
#: ``Dialect`` says any of them its own way. Each is formatted with the fields its refusal names, and
#: ``file`` (the description as the dialect names it).
WORDS: dict[str, str] = {
    "xml": "{file} could not be read as XML: {error}",
    "numbers": "{where} must be {count} numbers, not {text!r}",
    "axis_zero": "{file} joint {joint!r} axis must not be zero",
    # URDF
    "urdf_root": "{file}: a URDF's root element is <robot>",
    "link_name": "{file}: every link has a name of its own ({name!r})",
    "urdf_joint_type": "{file} joint {joint!r} is a {kind} joint; a robot's joints are fixed, revolute, continuous "
                       "and prismatic",
    "joint_links": "{file} joint {joint!r} joins links the robot does not have ({parent!r}, {child!r})",
    "limit_missing": "{file} joint {joint!r}: a {kind} joint declares a <limit>",
    "rgba": "{where} must be 4 numbers, not {text!r}",
    "four_bar_many": "{file} joint {joint!r} declares more than one tcad:four_bar",
    "four_bar_number": "{file} joint {joint!r} tcad:four_bar must declare {key} as a number",
    "four_bar_lengths": "{file} joint {joint!r} tcad:four_bar needs a driver and positive lengths",
    "tree_parents": "{file}: link {link!r} has more than one parent joint",
    "tree_roots": "{file}: the links must form one tree; its roots are {roots}",
    "tree_cycle": "{file}: the joints make a cycle at {link!r}",
    "tree_loose": "{file}: links {links} hang from no joint of the tree",
    # SRDF
    "srdf_name": "{file} has no <robot name>, so its URDF cannot be found: {rule}",
    "srdf_pair": "{file}: {found} .urdf in {folder} declare <robot name={name!r}>: {rule}",
}


class SourceError(ValueError):
    """A description its reader cannot articulate, in the words of the reader's dialect: ``code`` names
    the refusal (``WORDS``) and ``fields`` what it names."""

    def __init__(self, message: str, code: str, fields: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.code, self.fields = code, dict(fields)


def _name(path: Path) -> str:
    return path.name


@dataclass(frozen=True)
class Dialect:
    """How one consumer reads a description where the viewer's payload and the stills have read it
    differently: its refusals' ``words`` by code over ``WORDS`` (a word of None: not refused, what it
    names read leniently), how a refusal names the file (``display``), and whether the facts as written
    are read at all (``facts``: the payload shows them; the stills draw no fact)."""

    words: Mapping[str, str | None] = field(default_factory=dict)
    display: Callable[[Path], str] = _name
    facts: bool = True

    def refuses(self, code: str) -> bool:
        return self.words.get(code, WORDS[code]) is not None

    def error(self, code: str, **fields: Any) -> SourceError:
        template = self.words.get(code, WORDS[code])
        assert template is not None, f"{code} is not refused in this dialect"
        return SourceError(template.format(**fields), code, fields)


# --- the articulation ---------------------------------------------------------------------------


@dataclass
class Visual:
    """A link's visual as the viewer and the stills take one: its placement in its link's frame, its shape --
    ``("box"|"cylinder"|"sphere", dimensions)`` in full sizes, ``("file", path, scale)`` or ``("unknown",)`` -- its
    colour (``#rrggbb``), its alpha and the name a row calls it; a URDF's mesh reference as written
    (``reference``), colour as written (``rgba``) and facts (``facts``)."""

    id: str
    link: str
    local: Matrix
    shape: tuple
    color: str
    alpha: float
    label: str
    reference: str = ""
    rgba: tuple[float, ...] | None = None
    facts: dict[str, Any] | None = None


@dataclass
class LinkJoint:
    """A joint between two links as the viewer poses one: ``fixed``, ``revolute``, ``continuous`` or
    ``prismatic``; its frame (the anchor, at rest, in the model's space) and axis (a unit vector there); its
    range in radians or metres around zero (None: unbounded); the leader it follows, if any;
    a URDF's ``<tcad:four_bar>`` as written (``four_bar``: its ``driver``, lengths and zero
    angles, the element's ``namespace``); its facts as written (``facts``)."""

    name: str
    type: str
    parent: str
    child: str
    frame: Matrix
    axis: list[float] | None
    lower: float | None
    upper: float | None
    mimic: tuple[str, float, float] | None = None
    four_bar: dict[str, Any] | None = None
    facts: dict[str, Any] | None = None


@dataclass
class Articulation:
    """The model as a tree of links: each link's rest frame, its visuals, the joints (as declared), the poses (in the viewer's control units: degrees for a turn, metres
    for a slide) and the inertials, by link; the description's ``name``, an SRDF's ``home`` state, each
    link's collisions as written and the description files read (``sources``)."""

    root: str
    links: dict[str, Matrix]
    visuals: dict[str, list[Visual]]
    joints: list[LinkJoint]
    poses: dict[str, dict[str, float]]
    inertials: dict[str, dict[str, Any]]
    name: str = ""
    home: dict[str, float] = field(default_factory=dict)
    collisions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sources: list[Path] = field(default_factory=list)


# --- matrices (row-major 4x4 lists) -----------------------------------------------------------------


IDENTITY: Matrix = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def multiply(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def translation(x: float, y: float, z: float) -> Matrix:
    return [[1.0, 0.0, 0.0, x], [0.0, 1.0, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]]


def rpy(roll: float, pitch: float, yaw: float) -> Matrix:
    """URDF's fixed-axis roll, pitch, yaw: ``Rz(yaw) Ry(pitch) Rx(roll)``."""
    sr, cr, sp, cp, sy, cy = math.sin(roll), math.cos(roll), math.sin(pitch), math.cos(pitch), math.sin(yaw), math.cos(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, 0.0],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, 0.0],
        [-sp, cp * sr, cp * cr, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def pose(xyz: Any, angles: Any) -> Matrix:
    return multiply(translation(*xyz), rpy(*angles))


def rotate(m: Matrix, v: Any) -> list[float]:
    return [m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3)]


def unit(v: Any) -> list[float] | None:
    length = math.hypot(v[0], v[1], v[2])
    if not math.isfinite(length) or length < 1e-12:
        return None
    return [v[0] / length, v[1] / length, v[2] / length]


# --- XML and numbers -----------------------------------------------------------------------------


def local_name(tag: Any) -> str:
    """An ElementTree tag without its ``{namespace}`` prefix; "" for a comment's or an instruction's."""
    return str(tag).rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def children(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [child for child in (element if element is not None else []) if local_name(child.tag) == name]


def first(element: ET.Element | None, name: str) -> ET.Element | None:
    found = children(element, name)
    return found[0] if found else None


def parse(path: Path, dialect: Dialect) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise dialect.error("xml", file=dialect.display(path), error=error) from None


def numbers(raw: Any, count: int, where: str, dialect: Dialect, *, default: list[float] | None = None,
            code: str = "numbers") -> list[float] | None:
    """``count`` finite numbers written in ``raw`` (``default`` when nothing is), else refused by
    ``code`` -- or None, where the dialect reads that code leniently."""
    found = optional_numbers(raw, count)
    if found is None and not str(raw or "").split() and default is not None:
        return list(default)
    if found is None and dialect.refuses(code):
        raise dialect.error(code, where=where, count=count, text=raw, written=str(raw or "").strip())
    return found


def optional_numbers(raw: Any, count: int) -> list[float] | None:
    try:
        values = [float(part) for part in str(raw or "").split()]
    except ValueError:
        return None
    return values if len(values) == count and all(math.isfinite(value) for value in values) else None


def optional_number(element: ET.Element | None, name: str) -> float | None:
    raw = element.attrib.get(name) if element is not None else None
    try:
        value = float(raw) if raw is not None and str(raw).strip() else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) else None


def hex_color(rgb: Any) -> str:
    """``#rrggbb`` of a colour's numbers, each clamped to 0..1, half rounding up (as a GLB's colour
    bytes are written; a channel is never negative here)."""
    return "#" + "".join(f"{int(max(0.0, min(1.0, channel)) * 255 + 0.5):02x}" for channel in list(rgb)[:3])


def described_origin(xyz: list[float] | None, angles: list[float] | None) -> dict[str, list[float]]:
    """A placement as a description writes it: ``xyz`` and ``rpy``, zero where it writes none."""
    return {"xyz": list(xyz or [0.0, 0.0, 0.0]), "rpy": list(angles or [0.0, 0.0, 0.0])}

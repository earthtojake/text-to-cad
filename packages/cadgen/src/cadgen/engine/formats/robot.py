"""A robot description -- a URDF, an SDF, or an SRDF with the URDF it plans for -- as the stills
hold it: every link visual's mesh a part, placed where its link stands at the pose asked, by
forward kinematics ported from the viewer's (``@text-to-cad/core`` ``lib/urdf/kinematics.js``
and ``fourBarCoupling.js``) and held to a golden its own code made.

**Reading** (the standard library's XML): a URDF's links and their visuals (origin, ``<mesh
filename scale>`` or a box, cylinder or sphere, the material's ``rgba`` inline or by name), its
joints (fixed, revolute, continuous, prismatic: origin, axis, limits, ``<mimic>``, and the urdf
skill's ``<tcad:four_bar>``); an SDF's one model (or a world's one model) with its nested models,
frames and poses resolved by the SDFormat rules (``relative_to``, ``attached_to``, a joint's pose
relative to its child, an axis ``expressed_in``), visual materials' diffuse colour and capsules
too; an SRDF's group states, over the same-folder URDF whose ``<robot name>`` is its own. Every
frame is placed at rest in the robot's space (the description as written, every joint at zero),
in metres, as the viewer's payload places them (``cadgen.robot_payload``).

**Posing**: a control is a revolute or continuous joint (degrees) or a prismatic one (metres);
a mimic joint follows its leader (``multiplier * leader + offset`` in radians or metres) and a
four-bar input its driver (the planar linkage's closed form, on the branch its zero angles
describe). A link moves with every joint above it: each joint turns its subtree about its axis
through its origin (or slides it along the axis), from the root down. The robot opens as the
viewer opens it -- every control at zero, an SRDF's ``home`` group state over that -- and
``--pose`` names a group state (``group/name``, or a name only one group has) or gives joint
values over the opening pose; an unknown joint, a joint that is not a control and a value past
its limits are refused by name.

**Meshes**: a link mesh is an STL or a 3MF (its numbers as they are, which the description's
mesh scale makes metres) or a GLB (metres), each drawn as the stills draw that file; a box,
cylinder, sphere or capsule is made by the kernel and meshed as a part is (``mesh.py``). The
robot is drawn in millimetres. A ``package://NAME/REST`` mesh is REST in the ROS package the
description is in: the nearest folder at or above it named NAME, or holding a ``package.xml``
that names it (``package_file``, which the viewer's robot payload resolves by too). A description
naming a mesh in any other format (OBJ, DAE), a package no folder above it is, or a file that is
not there, is refused by name.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

import numpy as np

from cadgen.engine.formats import Foreign, FormatError, Part, Placed, assemble, files_of

__all__ = ["Robot", "RobotError", "package_file", "package_root", "read_robot", "robot_file"]

MOVING = ("revolute", "continuous", "prismatic")
ANGULAR = ("revolute", "continuous")
DRAWABLE = (".stl", ".3mf", ".glb")
PRIMITIVES = ("box", "cylinder", "sphere", "capsule")
FOUR_BAR_NAMESPACE = "https://text-to-cad.dev/urdf"
FOUR_BAR_LENGTHS = ("input_length", "ground_length", "output_length", "coupler_length")
LIMIT_TOLERANCE = 1e-6  # degrees or metres a value may pass a limit by: its own rounding
_INTERSECTION_TOLERANCE = 1e-12


class RobotError(FormatError):
    """What a description says that the stills cannot draw or pose, by name."""


# --- transforms --------------------------------------------------------------------------------


def translation(x: float, y: float, z: float) -> np.ndarray:
    matrix = np.eye(4)
    matrix[:3, 3] = (x, y, z)
    return matrix


def rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """URDF's fixed-axis roll, pitch, yaw: ``Rz(yaw) Ry(pitch) Rx(roll)``, as ``kinematics.js``."""
    sr, cr, sp, cp, sy, cy = (math.sin(roll), math.cos(roll), math.sin(pitch), math.cos(pitch), math.sin(yaw),
                              math.cos(yaw))
    matrix = np.eye(4)
    matrix[:3, :3] = [[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                      [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                      [-sp, cp * sr, cp * cr]]
    return matrix


def pose(xyz: Any, angles: Any) -> np.ndarray:
    return translation(*xyz) @ rpy(*angles)


def axis_angle(axis: Any, angle: float) -> np.ndarray:
    """A turn of ``angle`` radians about the unit ``axis``, as ``kinematics.js``'s ``axisAngleTransform``."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    matrix = np.eye(4)
    matrix[:3, :3] = [[c + x * x * t, x * y * t - z * s, x * z * t + y * s],
                      [y * x * t + z * s, c + y * y * t, y * z * t - x * s],
                      [z * x * t - y * s, z * y * t + x * s, c + z * z * t]]
    return matrix


def _unit(vector: Any) -> np.ndarray | None:
    vector = np.asarray(vector, float)
    length = float(np.linalg.norm(vector))
    return None if length <= 1e-12 else vector / length


# --- the description ---------------------------------------------------------------------------


@dataclass
class Visual:
    """A link visual: its placement in its link's frame (metres, rigid), its mesh -- a file
    (``("file", path, scale)``) or a shape (``(kind, dimensions)``) -- its colour (``#rrggbb``,
    sRGB, or "") and the name a row calls it."""

    local: np.ndarray
    mesh: tuple
    color: str
    label: str


@dataclass
class Joint:
    name: str
    type: str
    parent: str
    child: str
    frame: np.ndarray = field(default_factory=lambda: np.eye(4))  # at rest, in the robot's space
    axis: np.ndarray | None = None  # a unit vector in the robot's space at rest
    lower: float | None = None  # native: radians or metres
    upper: float | None = None
    mimic: tuple[str, float, float] | None = None  # leader, multiplier, offset
    four_bar: dict[str, Any] | None = None


@dataclass
class Robot:
    kind: str
    name: str
    root: str
    links: dict[str, np.ndarray]  # each link's frame at rest, in the robot's space (metres)
    visuals: dict[str, list[Visual]]
    joints: list[Joint]
    poses: dict[str, dict[str, float]] = field(default_factory=dict)  # group/name: control values
    home: dict[str, float] = field(default_factory=dict)
    files: list[Path] = field(default_factory=list)

    # --- controls and values ---

    def unit(self, joint: Joint) -> float:
        """Degrees per native unit: a turn's values are degrees, a slide's metres."""
        return 180 / math.pi if joint.type in ANGULAR else 1.0

    def controls(self) -> dict[str, Joint]:
        return {joint.name: joint for joint in self.joints
                if joint.type in MOVING and joint.mimic is None and joint.four_bar is None}

    def opening(self) -> dict[str, float]:
        """Where the viewer opens the robot: every control at zero, an SRDF's home over that."""
        return {**{name: 0.0 for name in self.controls()}, **self.home}

    def values(self, asked: Any) -> tuple[dict[str, float], str | None]:
        """The controls' values for ``asked``: None (the opening pose), a group state's name, or
        ``{joint: value}`` over the opening pose. Refused by name: an unknown state or joint, a
        joint that is no control, a value that is no number or past its limits."""
        values, named = self.opening(), None
        if asked is None:
            return values, None
        if isinstance(asked, str):
            if asked in self.poses:
                named = asked
            else:
                found = [key for key in self.poses if key.split("/", 1)[-1] == asked]
                if len(found) != 1:
                    states = ", ".join(sorted(self.poses)) or "none"
                    raise ValueError(f"{self.name} has {'no group state' if not found else 'several group states'} "
                                     f"{asked!r}{'' if not found else ' (' + ', '.join(found) + ')'}; its group states: {states}")
                named = found[0]
            asked = self.poses[named]
        if not isinstance(asked, dict):
            raise ValueError("a pose is a group state's name or {joint: value}")
        controls = self.controls()
        by_name = {joint.name: joint for joint in self.joints}
        for name, value in asked.items():
            joint = by_name.get(name)
            if joint is None:
                raise ValueError(f"{self.name} has no joint {name!r}; its joints: {', '.join(sorted(controls)) or 'none'}")
            if name not in controls:
                why = (f"follows {joint.mimic[0]!r}" if joint.mimic else f"follows its driver {joint.four_bar['driver']!r}"
                       if joint.four_bar else "is fixed")
                raise ValueError(f"joint {name!r} {why}: pose {', '.join(sorted(controls)) or 'nothing'}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"joint {name!r} takes a number ({'degrees' if joint.type in ANGULAR else 'metres'}), not {value!r}")
            if joint.type != "continuous" and joint.lower is not None and joint.upper is not None:
                low, high = joint.lower * self.unit(joint), joint.upper * self.unit(joint)
                if not low - LIMIT_TOLERANCE <= value <= high + LIMIT_TOLERANCE:
                    raise ValueError(f"joint {name!r} at {value:g} is past its limits {low:g} to {high:g} "
                                     f"{'degrees' if joint.type in ANGULAR else 'metres'}")
            values[name] = float(value)
        return values, named

    def native(self, values: dict[str, float]) -> dict[str, float]:
        """Every moving joint's value in radians or metres: the controls', and their followers'."""
        by_name = {joint.name: joint for joint in self.joints}
        found: dict[str, float] = {}

        def value(joint: Joint, trail: tuple[str, ...] = ()) -> float:
            if joint.name in found:
                return found[joint.name]
            if joint.name in trail:
                raise RobotError(f"{self.name}: joint {joint.name!r} follows itself")
            if joint.mimic is not None:
                leader = by_name[joint.mimic[0]]
                result = joint.mimic[1] * value(leader, (*trail, joint.name)) + joint.mimic[2]
            elif joint.four_bar is not None:
                result = four_bar_angle(joint.four_bar, value(by_name[joint.four_bar["driver"]], (*trail, joint.name)))
            else:
                result = float(values.get(joint.name, 0.0)) / self.unit(joint)
            if joint.mimic is not None and joint.type != "continuous" and joint.lower is not None:
                result = min(max(result, joint.lower), joint.upper)  # a follower is clamped, as the viewer clamps it
            found[joint.name] = result
            return result

        for joint in self.joints:
            if joint.type in MOVING:
                value(joint)
        return found

    def placements(self, values: dict[str, float]) -> dict[str, np.ndarray]:
        """Each link's frame at ``values`` (controls), in millimetres: every joint above it turning
        its subtree about its axis through its origin, or sliding it, from the root down."""
        native = self.native(values)
        moved: dict[str, np.ndarray] = {self.root: np.eye(4)}
        children: dict[str, list[Joint]] = {}
        for joint in self.joints:
            children.setdefault(joint.parent, []).append(joint)
        pending = [self.root]
        while pending:
            parent = pending.pop(0)
            for joint in children.get(parent, ()):
                motion = np.eye(4)
                if joint.type in ANGULAR:
                    origin = joint.frame[:3, 3]
                    motion = translation(*origin) @ axis_angle(joint.axis, native[joint.name]) @ translation(*-origin)
                elif joint.type == "prismatic":
                    motion = translation(*(joint.axis * native[joint.name]))
                moved[joint.child] = moved[parent] @ motion
                pending.append(joint.child)
        millimetres = np.diag([1000.0, 1000.0, 1000.0, 1.0])
        return {name: millimetres @ moved.get(name, np.eye(4)) @ rest @ np.linalg.inv(millimetres)
                for name, rest in self.links.items()}


def four_bar_angle(four_bar: dict[str, Any], driver: float) -> float:
    """The four-bar input joint's angle (radians, in (-pi, pi]) at its driver's (``fourBarCoupling.js``'s
    ``solveFourBarCoupling``): the crank's pin where the coupler from the output pin closes the
    loop, on the configured branch."""
    first, second = _four_bar_candidates(four_bar, driver)
    angle = (second if four_bar.get("branch") == 1 else first) - four_bar["input_zero"]
    wrapped = (angle + math.pi) % (2 * math.pi) - math.pi
    return math.pi if wrapped == -math.pi and angle > 0 else wrapped


def _four_bar_candidates(four_bar: dict[str, Any], driver: float) -> tuple[float, float]:
    output = four_bar["output_zero"] + driver
    pin_x = four_bar["ground_length"] + four_bar["output_length"] * math.cos(output)
    pin_y = four_bar["output_length"] * math.sin(output)
    distance = math.hypot(pin_x, pin_y)
    crank, coupler = four_bar["input_length"], four_bar["coupler_length"]
    if distance <= _INTERSECTION_TOLERANCE or not abs(crank - coupler) - _INTERSECTION_TOLERANCE <= distance \
            <= crank + coupler + _INTERSECTION_TOLERANCE:
        raise ValueError(f"the four-bar linkage of {four_bar.get('joint', 'a joint')!r} cannot close at driver angle "
                         f"{math.degrees(driver):g} degrees")
    along = (crank * crank - coupler * coupler + distance * distance) / (2 * distance)
    height = math.sqrt(max(0.0, crank * crank - along * along))
    unit_x, unit_y = pin_x / distance, pin_y / distance
    base_x, base_y = along * unit_x, along * unit_y
    return (math.atan2(base_y + height * unit_x, base_x - height * unit_y),
            math.atan2(base_y - height * unit_x, base_x + height * unit_y))


def _branch(four_bar: dict[str, Any]) -> int:
    first, second = _four_bar_candidates(four_bar, 0.0)

    def error(angle: float) -> float:
        return abs((angle - four_bar["input_zero"] + math.pi) % (2 * math.pi) - math.pi)

    return 0 if error(first) <= error(second) else 1


# --- XML ---------------------------------------------------------------------------------------


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [child for child in (element if element is not None else []) if _local(child.tag) == name]


def _first(element: ET.Element | None, name: str) -> ET.Element | None:
    found = _children(element, name)
    return found[0] if found else None


def _text(element: ET.Element | None, name: str) -> str:
    found = _first(element, name)
    return str(found.text or "").strip() if found is not None else ""


def _numbers(text: Any, count: int, where: str, default: list[float] | None = None) -> list[float]:
    raw = str(text or "").split()
    if not raw and default is not None:
        return list(default)
    try:
        values = [float(value) for value in raw]
    except ValueError:
        values = []
    if len(values) != count or not all(math.isfinite(value) for value in values):
        raise RobotError(f"{where} must be {count} numbers, not {text!r}")
    return values


def _hex(values: list[float]) -> str:
    return "#" + "".join(f"{round(min(max(value, 0.0), 1.0) * 255):02x}" for value in values[:3])


def _parse(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise RobotError(f"{path.name} could not be read as XML: {error}") from None


def _package_name(manifest: Path) -> str | None:
    """The name a ROS package manifest (``package.xml``) gives its package, or None."""
    try:
        name = ET.parse(manifest).getroot().find("name")
    except (OSError, ET.ParseError):
        return None
    if name is None:
        return None
    return str(name.text or "").strip() or None


def package_root(name: str, base: Path) -> Path | None:
    """ROS package ``name``'s folder for a description in ``base``: the nearest folder at or above
    ``base`` that is named ``name``, or that holds a ``package.xml`` naming it, ROS's own mark of a
    package's root; None when none is."""
    for folder in (base, *base.parents):
        if folder.name == name:
            return folder
        manifest = folder / "package.xml"
        if manifest.is_file() and _package_name(manifest) == name:
            return folder
    return None


def package_file(reference: str, base: Path, where: str) -> Path:
    """``package://NAME/REST``, named by a description in ``base``: REST in package NAME's folder
    (``package_root``), never above it. Refused by name (``where`` names what names it) when no
    folder holds the description as its package, and when REST climbs out of it."""
    parsed = urlparse(reference)
    name, rest = unquote(parsed.netloc).strip(), unquote(parsed.path).lstrip("/")
    base = Path(base).resolve()
    root = package_root(name, base) if name and rest else None
    if root is None:
        raise RobotError(f"{where} names {reference!r}: no folder named {name!r}, nor one holding a package.xml that "
                         f"names it, holds {base}, so its package cannot be found. Keep the description inside its "
                         "package folder, or name the mesh by a path relative to the description")
    found = (root / rest).resolve()
    if root not in found.parents:
        raise RobotError(f"{where} names {reference!r}, which climbs out of its package, {root}")
    return found


def _mesh_file(reference: str, base: Path, where: str) -> Path:
    """A visual's mesh file: a path relative to the description, an absolute one, file://, or a
    file of the ROS package the description is in (``package://``, ``package_file``)."""
    parsed = urlparse(reference)
    if parsed.scheme == "package":
        found = package_file(reference, base, where)
        if found.suffix.lower() not in DRAWABLE:
            raise RobotError(f"{where} names {found.name}: the stills draw STL, 3MF and GLB link meshes, not "
                             f"{found.suffix or 'this'} files")
        if not found.is_file():
            raise RobotError(f"{where} names {reference!r}, and no file is at {found}")
        return found
    if parsed.scheme not in ("", "file") and not (len(parsed.scheme) == 1 and os.name == "nt"):
        raise RobotError(f"{where} names {reference!r}, which is not a local file: copy it beside the description "
                         "and name it by a relative path")
    found = Path(unquote(parsed.path)) if parsed.scheme == "file" else Path(reference)
    found = (found if found.is_absolute() else base / found).resolve()
    if found.suffix.lower() not in DRAWABLE:
        raise RobotError(f"{where} names {found.name}: the stills draw STL, 3MF and GLB link meshes, not "
                         f"{found.suffix or 'this'} files")
    if not found.is_file():
        raise RobotError(f"{where} names {reference!r}, and no file is at {found}")
    return found


# --- URDF ---------------------------------------------------------------------------------------


def _urdf_origin(element: ET.Element | None, where: str) -> np.ndarray:
    if element is None:
        return np.eye(4)
    return pose(_numbers(element.get("xyz"), 3, f"{where} origin xyz", [0.0, 0.0, 0.0]),
                _numbers(element.get("rpy"), 3, f"{where} origin rpy", [0.0, 0.0, 0.0]))


def _urdf_shape(geometry: ET.Element | None, base: Path, where: str) -> tuple:
    mesh = _first(geometry, "mesh")
    if mesh is not None:
        filename = str(mesh.get("filename") or "").strip()
        if not filename:
            raise RobotError(f"{where} is a <mesh> with no filename")
        return ("file", _mesh_file(filename, base, where),
                tuple(_numbers(mesh.get("scale"), 3, f"{where} mesh scale", [1.0, 1.0, 1.0])))
    box = _first(geometry, "box")
    if box is not None:
        size = _numbers(box.get("size"), 3, f"{where} box size")
        return ("box", tuple(size))
    cylinder = _first(geometry, "cylinder")
    if cylinder is not None:
        return ("cylinder", (float(cylinder.get("radius") or 0), float(cylinder.get("length") or 0)))
    sphere = _first(geometry, "sphere")
    if sphere is not None:
        return ("sphere", (float(sphere.get("radius") or 0),))
    raise RobotError(f"{where} uses geometry the stills cannot draw; give it a mesh, box, cylinder or sphere")


def _four_bar(joint: ET.Element, name: str, where: str) -> dict[str, Any] | None:
    elements = [child for child in joint if _local(child.tag) == "four_bar"]
    if not elements:
        return None
    if len(elements) > 1:
        raise RobotError(f"{where} declares more than one tcad:four_bar")
    element = elements[0]
    found: dict[str, Any] = {"joint": name, "driver": str(element.get("driver") or "").strip()}
    for key in (*FOUR_BAR_LENGTHS, "input_zero", "output_zero"):
        try:
            found[key] = float(element.get(key))
        except (TypeError, ValueError):
            raise RobotError(f"{where} tcad:four_bar must declare {key} as a number") from None
    if not found["driver"] or any(found[key] <= 0 for key in FOUR_BAR_LENGTHS):
        raise RobotError(f"{where} tcad:four_bar needs a driver and positive lengths")
    found["branch"] = _branch(found)
    return found


def read_urdf(path: Path) -> Robot:
    root = _parse(path)
    if _local(root.tag) != "robot":
        raise RobotError(f"{path.name}: a URDF's root element is <robot>")
    name = str(root.get("name") or "").strip() or path.stem
    named: dict[str, str] = {}
    for material in _children(root, "material"):
        colour = _first(material, "color")
        if material.get("name") and colour is not None and colour.get("rgba"):
            named[str(material.get("name")).strip()] = _hex(_numbers(colour.get("rgba"), 4, f"{path.name} material"))
    links: dict[str, np.ndarray] = {}
    visuals: dict[str, list[Visual]] = {}
    files: list[Path] = [path]
    for link in _children(root, "link"):
        link_name = str(link.get("name") or "").strip()
        if not link_name or link_name in links:
            raise RobotError(f"{path.name}: every link has a name of its own ({link_name!r})")
        links[link_name] = np.eye(4)
        visuals[link_name] = []
        for index, visual in enumerate(_children(link, "visual"), 1):
            where = f"{path.name} link {link_name!r} visual {index}"
            mesh = _urdf_shape(_first(visual, "geometry"), path.parent, where)
            if mesh[0] == "file":
                files.append(mesh[1])
            material = _first(visual, "material")
            colour = ""
            if material is not None:
                inline = _first(material, "color")
                if inline is not None and inline.get("rgba"):
                    colour = _hex(_numbers(inline.get("rgba"), 4, f"{where} material"))
                else:
                    colour = named.get(str(material.get("name") or "").strip(), "")
            label = str(visual.get("name") or "").strip() or (mesh[1].name if mesh[0] == "file" else mesh[0])
            visuals[link_name].append(Visual(_urdf_origin(_first(visual, "origin"), where), mesh, colour, label))
    joints: list[Joint] = []
    for element in _children(root, "joint"):
        joint_name = str(element.get("name") or "").strip()
        where = f"{path.name} joint {joint_name!r}"
        kind = str(element.get("type") or "").strip().lower()
        if kind not in (*MOVING, "fixed"):
            raise RobotError(f"{where} is a {kind or 'typeless'} joint; the stills pose fixed, revolute, continuous "
                             "and prismatic joints")
        parent, child = (str(getattr(_first(element, tag), "attrib", {}).get("link") or "").strip() for tag in ("parent", "child"))
        if parent not in links or child not in links:
            raise RobotError(f"{where} joins links the robot does not have ({parent!r}, {child!r})")
        joint = Joint(joint_name, kind, parent, child, frame=_urdf_origin(_first(element, "origin"), where))
        axis = _first(element, "axis")
        joint.axis = None if kind == "fixed" else _unit(_numbers(axis.get("xyz") if axis is not None else None, 3,
                                                                  f"{where} axis", [1.0, 0.0, 0.0]))
        if kind != "fixed" and joint.axis is None:
            raise RobotError(f"{where} axis must not be zero")
        limit = _first(element, "limit")
        if kind in ("revolute", "prismatic"):
            if limit is None:
                raise RobotError(f"{where}: a {kind} joint declares a <limit>")
            joint.lower, joint.upper = (_numbers(limit.get(key), 1, f"{where} limit {key}")[0] for key in ("lower", "upper"))
        mimic = _first(element, "mimic")
        if mimic is not None:
            joint.mimic = (str(mimic.get("joint") or "").strip(), float(mimic.get("multiplier") or 1.0),
                           float(mimic.get("offset") or 0.0))
        joint.four_bar = _four_bar(element, joint_name, where)
        joints.append(joint)
    root_link = _tree(path.name, links, joints)
    # Each joint's frame and axis, and each link's frame, at rest in the robot's space.
    by_parent: dict[str, list[Joint]] = {}
    for joint in joints:
        by_parent.setdefault(joint.parent, []).append(joint)
    pending = [root_link]
    while pending:
        parent = pending.pop(0)
        for joint in by_parent.get(parent, ()):
            joint.frame = links[parent] @ joint.frame
            if joint.axis is not None:
                joint.axis = _unit(joint.frame[:3, :3] @ joint.axis)
            links[joint.child] = joint.frame
            pending.append(joint.child)
    robot = Robot("urdf", name, root_link, links, visuals, joints, files=files)
    _followers(robot, path.name)
    return robot


def _tree(name: str, links: dict[str, np.ndarray], joints: list[Joint]) -> str:
    """The root link of a tree of links, refused by name when they are not one."""
    children: set[str] = set()
    for joint in joints:
        if joint.child in children:
            raise RobotError(f"{name}: link {joint.child!r} has more than one parent joint")
        children.add(joint.child)
    roots = [link for link in links if link not in children]
    if len(roots) != 1:
        raise RobotError(f"{name}: the links must form one tree; its roots are {', '.join(roots) or 'none'}")
    reached, pending = set(), [roots[0]]
    by_parent: dict[str, list[str]] = {}
    for joint in joints:
        by_parent.setdefault(joint.parent, []).append(joint.child)
    while pending:
        link = pending.pop()
        if link in reached:
            raise RobotError(f"{name}: the joints make a cycle at {link!r}")
        reached.add(link)
        pending.extend(by_parent.get(link, ()))
    if len(reached) != len(links):
        raise RobotError(f"{name}: links {', '.join(sorted(set(links) - reached))} hang from no joint of the tree")
    return roots[0]


def _followers(robot: Robot, name: str) -> None:
    """A mimic's leader and a four-bar's driver are joints of the robot that move."""
    by_name = {joint.name: joint for joint in robot.joints}
    for joint in robot.joints:
        leader = joint.mimic[0] if joint.mimic else joint.four_bar["driver"] if joint.four_bar else None
        if leader is not None and (leader not in by_name or by_name[leader].type not in MOVING):
            raise RobotError(f"{name} joint {joint.name!r} follows {leader!r}, which is no moving joint of the robot")


# --- SDF (SDFormat's frame semantics, as cadgen.robot_payload resolves them) ----------------------------------


class _Scope:
    """One model's namespace: the top-level model's (no prefix, its frame ``__model__``) or a nested
    model's (``arm::``, its frame the node ``arm``)."""

    def __init__(self, model: ET.Element, prefix: str, frame: str) -> None:
        self.name, self.prefix, self.frame = str(model.get("name") or "").strip(), prefix, frame
        self.declared = {str(element.get("name") or "").strip()
                         for tag in ("link", "frame", "joint", "model") for element in _children(model, tag)}

    def own(self, element: ET.Element) -> str:
        return self.prefix + str(element.get("name") or "").strip()

    def key(self, name: Any, default: str) -> str:
        text = str(name or "").strip()
        if not text:
            return default
        if text in self.declared:
            return self.prefix + text
        if text == "world":
            return "world"
        if text in (self.name, "__model__"):
            return self.frame
        return self.prefix + text


class _Frames:
    def __init__(self, model: str, world: np.ndarray) -> None:
        self.model = model
        self.nodes: dict[str, dict[str, Any]] = {"world": {"kind": "world", "world": np.eye(4)},
                                                 "__model__": {"kind": "model", "world": world, "canonical": ""}}
        self.links: set[str] = set()

    def add(self, key: str, node: dict[str, Any]) -> None:
        if key in self.nodes:
            raise RobotError(f"SDF model {self.model!r} names {key!r} twice")
        self.nodes[key] = node

    def world(self, key: str, trail: tuple[str, ...] = ()) -> np.ndarray:
        node = self.nodes.get(key)
        if node is None:
            raise RobotError(f"SDF model {self.model!r} refers to frame {key!r}, which it does not declare")
        if "world" not in node:
            if key in trail:
                raise RobotError(f"SDF model {self.model!r}: its frames cycle at {key!r}")
            node["world"] = self.world(node["relative_to"], (*trail, key)) @ node["pose"]
        return node["world"]

    def attached(self, key: str, trail: tuple[str, ...] = ()) -> str:
        if key in self.links:
            return key
        node = self.nodes.get(key)
        if key == "world" or node is None or key in trail:
            return ""
        follow = {"frame": node.get("attached"), "joint": node.get("child"), "model": node.get("canonical")}.get(node["kind"])
        return self.attached(follow, (*trail, key)) if follow else ""


def _sdf_pose(element: ET.Element, where: str) -> tuple[str, np.ndarray]:
    found = _first(element, "pose")
    if found is None:
        return "", np.eye(4)
    if str(found.get("rotation_format") or "euler_rpy").strip().lower() != "euler_rpy":
        raise RobotError(f"{where} pose is not euler_rpy, the one rotation format the stills read")
    values = _numbers(found.text, 6, f"{where} pose", [0.0] * 6)
    if str(found.get("degrees") or "").strip().lower() in ("1", "true"):
        values[3:] = [math.radians(value) for value in values[3:]]
    return str(found.get("relative_to") or "").strip(), pose(values[:3], values[3:])


def _sdf_shape(owner: ET.Element, base: Path, where: str) -> tuple:
    geometry = _first(owner, "geometry")
    shape = next((child for child in (geometry if geometry is not None else []) if isinstance(child.tag, str)), None)
    kind = _local(shape.tag) if shape is not None else "nothing"
    if kind == "mesh":
        uri = _text(shape, "uri")
        if not uri:
            raise RobotError(f"{where} is a <mesh> with no <uri>")
        return ("file", _mesh_file(uri, base, where), tuple(_numbers(_text(shape, "scale"), 3, f"{where} scale",
                                                                     [1.0, 1.0, 1.0])))
    if kind == "box":
        return ("box", tuple(_numbers(_text(shape, "size"), 3, f"{where} box size")))
    if kind in ("cylinder", "capsule"):
        return (kind, (float(_text(shape, "radius") or 0), float(_text(shape, "length") or 0)))
    if kind == "sphere":
        return ("sphere", (float(_text(shape, "radius") or 0),))
    raise RobotError(f"{where} uses {kind} geometry; the stills draw a mesh, box, cylinder, sphere or capsule")


def _sdf_color(owner: ET.Element) -> str:
    material = _first(owner, "material")
    for tag in ("diffuse", "ambient"):
        values = _text(material, tag).split()
        if len(values) in (3, 4):
            try:
                return _hex([float(value) for value in values])
            except ValueError:
                continue
    return ""


def read_sdf(path: Path) -> Robot:
    root = _parse(path)
    if _local(root.tag) != "sdf":
        raise RobotError(f"{path.name}: an SDF's root element is <sdf>")
    models = _children(root, "model")
    if not models:
        worlds = _children(root, "world")
        models = _children(worlds[0], "model") if len(worlds) == 1 else []
    if len(models) != 1:
        raise RobotError(f"{path.name} must hold one <model>, or one <world> holding one <model>")
    model = models[0]
    name = str(model.get("name") or "").strip() or path.stem
    _relative, world = _sdf_pose(model, f"{path.name} model {name!r}")
    frames = _Frames(name, world)
    link_elements: list[tuple[str, ET.Element, _Scope]] = []
    raw: list[dict[str, Any]] = []

    def collect(element: ET.Element, scope: _Scope) -> None:
        for link in _children(element, "link"):
            key = scope.own(link)
            relative, transform = _sdf_pose(link, f"{path.name} link {key!r}")
            frames.links.add(key)
            frames.add(key, {"kind": "link", "pose": transform, "relative_to": scope.key(relative, scope.frame)})
            link_elements.append((key, link, scope))
        for frame in _children(element, "frame"):
            key = scope.own(frame)
            attached = scope.key(frame.get("attached_to"), scope.frame)
            relative, transform = _sdf_pose(frame, f"{path.name} frame {key!r}")
            frames.add(key, {"kind": "frame", "pose": transform, "relative_to": scope.key(relative, attached),
                             "attached": attached})
        for nested in _children(element, "model"):
            key = scope.own(nested)
            relative, transform = _sdf_pose(nested, f"{path.name} model {key!r}")
            inner = _Scope(nested, f"{key}::", key)
            canonical = str(nested.get("canonical_link") or "").strip()
            first = _first(nested, "link")
            frames.add(key, {"kind": "model", "pose": transform, "relative_to": scope.key(relative, scope.frame),
                             "canonical": inner.key(canonical, "") if canonical else inner.own(first) if first is not None
                             else ""})
            collect(nested, inner)
        for joint in _children(element, "joint"):
            key = scope.own(joint)
            kind = str(joint.get("type") or "").strip().lower()
            if kind not in (*MOVING, "fixed"):
                raise RobotError(f"{path.name} joint {key!r} is a {kind!r} joint; the stills pose fixed, revolute, "
                                 "continuous and prismatic joints")
            child = scope.key(_text(joint, "child"), "")
            relative, transform = _sdf_pose(joint, f"{path.name} joint {key!r}")
            frames.add(key, {"kind": "joint", "pose": transform, "relative_to": scope.key(relative, child), "child": child})
            axis = _first(joint, "axis")
            xyz = _first(axis, "xyz")
            limit = _first(axis, "limit")
            raw.append({"name": key, "type": kind, "parent": scope.key(_text(joint, "parent"), ""), "child": child,
                        "axis": _numbers(xyz.text if xyz is not None else None, 3, f"{path.name} joint {key!r} axis",
                                         [0.0, 0.0, 1.0]),
                        "expressed": scope.key((xyz.get("expressed_in") if xyz is not None else None)
                                               or (axis.get("expressed_in") if axis is not None else None), key),
                        "lower": _text(limit, "lower"), "upper": _text(limit, "upper")})

    collect(model, _Scope(model, "", "__model__"))
    links = {key: frames.world(key) for key, _element, _scope in link_elements}
    visuals: dict[str, list[Visual]] = {}
    files = [path]
    for key, element, scope in link_elements:
        inverse = np.linalg.inv(links[key])
        visuals[key] = []
        for index, visual in enumerate(_children(element, "visual"), 1):
            where = f"{path.name} link {key!r} visual {index}"
            mesh = _sdf_shape(visual, path.parent, where)
            if mesh[0] == "file":
                files.append(mesh[1])
            relative, transform = _sdf_pose(visual, where)
            local = inverse @ frames.world(scope.key(relative, key)) @ transform
            label = str(visual.get("name") or "").strip() or (mesh[1].name if mesh[0] == "file" else mesh[0])
            visuals[key].append(Visual(local, mesh, _sdf_color(visual), label))
    joints = []
    for item in raw:
        parent = frames.attached(item["parent"]) if item["parent"] else ""
        child = frames.attached(item["child"]) if item["child"] else ""
        if not child or child == parent:
            raise RobotError(f"{path.name} joint {item['name']!r} joins no two links")
        joint = Joint(item["name"], item["type"], parent or "", child, frame=frames.world(item["name"]))
        if joint.type != "fixed":
            joint.axis = _unit(frames.world(item["expressed"])[:3, :3] @ np.asarray(item["axis"], float))
            if joint.axis is None:
                raise RobotError(f"{path.name} joint {item['name']!r} axis must not be zero")
            if joint.type != "continuous" and item["lower"] and item["upper"]:
                joint.lower, joint.upper = float(item["lower"]), float(item["upper"])
        joints.append(joint)
    # A joint to the world holds its child where it is: the world is no link to move.
    joints = [joint for joint in joints if joint.parent]
    root_link = _tree(path.name, links, joints)
    return Robot("sdf", name, root_link, links, visuals, joints, files=files)


# --- SRDF ---------------------------------------------------------------------------------------


def read_srdf(path: Path) -> Robot:
    root = _parse(path)
    name = str(root.get("name") or "").strip()
    rule = "an SRDF draws the same-folder .urdf whose <robot name> is its own, and exactly one may be"
    if _local(root.tag) != "robot" or not name:
        raise RobotError(f"{path.name} has no <robot name>, so its URDF cannot be found: {rule}")
    matches = []
    # Each file once: on a case-insensitive file system (Windows, macOS) both patterns find it.
    candidates = {os.path.normcase(str(found.resolve())): found
                  for found in sorted(path.parent.glob("*.urdf")) + sorted(path.parent.glob("*.URDF"))}
    for candidate in candidates.values():
        try:
            for _event, element in ET.iterparse(str(candidate), events=("start",)):
                if _local(element.tag) == "robot" and str(element.get("name") or "").strip() == name:
                    matches.append(candidate)
                break
        except (OSError, ET.ParseError):
            continue
    if len(matches) != 1:
        raise RobotError(f"{path.name}: {'no' if not matches else len(matches)} .urdf in {path.parent} "
                         f"declare <robot name={name!r}>: {rule}")
    robot = read_urdf(matches[0])
    robot.kind, robot.files = "srdf", [path, *robot.files]
    by_name = {joint.name: joint for joint in robot.joints}
    for state in _children(root, "group_state"):
        key = f"{str(state.get('group') or '').strip()}/{str(state.get('name') or '').strip()}"
        values = {}
        for joint in _children(state, "joint"):
            joint_name = str(joint.get("name") or "").strip()
            found = by_name.get(joint_name)
            if found is None or found.type not in MOVING or found.mimic is not None or found.four_bar is not None:
                continue
            values[joint_name] = _numbers(joint.get("value"), 1, f"{path.name} group state {key!r} joint {joint_name!r}")[0] \
                * robot.unit(found)
        robot.poses[key] = values
        if str(state.get("name") or "").strip().lower() == "home":
            robot.home.update(values)
    return robot


def read_robot(path: Path) -> Robot:
    suffix = Path(path).suffix.lower()
    return read_urdf(path) if suffix == ".urdf" else read_sdf(path) if suffix == ".sdf" else read_srdf(path)


# --- meshes and the structure -------------------------------------------------------------------


def _primitive(kind: str, dimensions: tuple, where: str) -> Any:
    """A box, cylinder, sphere or capsule (metres) as a part, centred on its frame as URDF and SDF
    centre them (a cylinder and a capsule along Z), in millimetres, meshed as a part is; its lines
    the edges where its faces fold (the viewer draws a primitive as a mesh: its rims, no seam and
    no tangent join)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    from cadgen.engine.mesh import SEAM, TANGENT, Mesh, mesh_shape

    size = [1000.0 * float(value) for value in dimensions]
    if any(value <= 0 for value in size):
        raise RobotError(f"{where} is a {kind} with a dimension that is not positive")
    if kind == "box":
        shape = BRepPrimAPI_MakeBox(gp_Pnt(*(-value / 2 for value in size)), *size).Shape()
    elif kind == "sphere":
        shape = BRepPrimAPI_MakeSphere(size[0]).Shape()
    else:
        radius, length = size
        shape = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -length / 2), gp_Dir(0, 0, 1)), radius, length).Shape()
        if kind == "capsule":
            for z in (-length / 2, length / 2):
                shape = BRepAlgoAPI_Fuse(shape, BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, z), radius).Shape()).Shape()
    meshed = mesh_shape(shape, parallel=False)
    folds = ~np.isin(meshed.edges[:, 3], [SEAM, TANGENT])
    return Mesh(meshed.positions, meshed.normals, meshed.indices, meshed.faces, meshed.edges[folds],
                meshed.edge_points, meshed.vertices)


def _mesh_parts(mesh: tuple, colour: str, where: str) -> list[tuple[Part, np.ndarray]]:
    """A visual's mesh as parts, each with its placement in the visual's frame (millimetres)."""
    from cadgen.engine.formats.meshes import mesh_part

    if mesh[0] != "file":
        return [(Part(mesh[0], _primitive(mesh[0], mesh[1], where)), np.eye(4))]
    source, scale = mesh[1], np.asarray(mesh[2], float)
    uniform = float(np.cbrt(abs(np.prod(scale)))) or 1.0
    if not np.allclose(scale, uniform):
        raise RobotError(f"{where} scales its mesh unevenly ({' '.join(f'{value:g}' for value in scale)}); "
                         "the stills scale a link mesh alike along every axis")
    suffix = source.suffix.lower()
    if suffix == ".stl":
        from cadgen.engine.formats.stl import read_stl

        corners = read_stl(source)
        points = corners.reshape(-1, 3)
        return [(mesh_part(source.stem, points, np.arange(len(points)).reshape(-1, 3), scale=1000.0 * uniform), np.eye(4))]
    if suffix == ".3mf":
        from cadgen.engine.formats.threemf import ThreeMfError, read_3mf

        try:
            model = read_3mf(source)
        except ThreeMfError as error:
            raise RobotError(str(error)) from None
        made: dict[int, Part] = {}
        found = []
        for part_index, matrix, _at in model.placed:
            part = model.parts[part_index]
            if part_index not in made:
                made[part_index] = mesh_part(part.name, part.points, part.triangles, scale=1000.0 * uniform,
                                             paints=None if colour else part.paints, palette=model.paints)
            placed = np.asarray(matrix, float).copy()
            placed[:3, 3] *= 1000.0 * uniform
            found.append((made[part_index], placed))
        return found
    from cadgen.engine.formats.glb import read_glb

    parts, placed, _tree, _warnings = read_glb(source)
    found = []
    for item in placed:
        part = parts[item.part]
        if uniform != 1.0:
            part = Part(part.name, _scaled(part.mesh, uniform), part.color, part.face_colors, part.material,
                        part.face_materials, part.uvs, part.textures)
        matrix = item.matrix.copy()
        matrix[:3, 3] *= uniform
        found.append((part, matrix))
    return found


def _scaled(mesh: Any, factor: float) -> Any:
    from cadgen.engine.mesh import Mesh

    return Mesh(mesh.positions * np.float32(factor), mesh.normals, mesh.indices, mesh.faces, mesh.edges,
                mesh.edge_points * np.float32(factor), mesh.vertices)


def _linear(colour: str) -> tuple[float, float, float, float]:
    channels = [int(colour[at:at + 2], 16) / 255 for at in (1, 3, 5)]
    return tuple(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 6) for c in channels) + (1.0,)


def robot_file(path: Path) -> Foreign:
    """The robot at ``path`` as the stills hold it: a part per link mesh (shared by every visual of
    one file, scale and colour), an instance per visual placed at the opening pose, each link's
    visuals one colour of the Parts palette; ``pose`` places them at another."""
    path = Path(path)
    robot = read_robot(path)
    parts: list[Part] = []
    made: dict[tuple, list[tuple[int, np.ndarray]]] = {}
    visuals: list[tuple[str, np.ndarray, str, str]] = []  # link, placement in the link's frame (mm), path, colour
    rows: list[tuple[int, int]] = []  # each instance: its part, its visual
    # Each instance's visual as the viewer names it (``robot_payload``: ``link:v1``), and its place
    # among the visual's objects when it draws several (the viewer's ``link:v1/object/0``): what a
    # view of the robot says it hid (``selection.hide``), which the stills leave out alike.
    named: list[tuple[str, int | None]] = []
    to_mm = np.diag([1000.0, 1000.0, 1000.0, 1.0])
    links = list(robot.links)
    tree_links: dict[str, dict[str, Any]] = {}
    for link in links:
        for index, visual in enumerate(robot.visuals.get(link, ()), 1):
            where = f"{path.name} link {link!r} visual {index}"
            key = (visual.mesh, visual.color)
            if key not in made:
                made[key] = []
                for part, placement in _mesh_parts(visual.mesh, visual.color, where):
                    made[key].append((len(parts), placement))
                    parts.append(part)
            local = to_mm @ visual.local @ np.linalg.inv(to_mm)
            for at, (part, placement) in enumerate(made[key]):
                visuals.append((link, local @ placement, f"{robot.name}/{link}/{visual.label}", visual.color))
                rows.append((part, len(visuals) - 1))
                named.append((f"{link}:v{index}", at if len(made[key]) > 1 else None))
    if not rows:
        raise RobotError(f"{path.name}: no link of {robot.name} has a visual to draw")

    def instances(values: dict[str, float]) -> list[Placed]:
        frames = robot.placements(values)
        return [Placed(part, frames[visuals[at][0]] @ visuals[at][1], visuals[at][2],
                       _linear(visuals[at][3]) if visuals[at][3] else None, links.index(visuals[at][0]), *named[at])
                for part, at in rows]

    opening, _named = robot.values(None)
    placed = instances(opening)
    for at, item in enumerate(placed):
        link = visuals[rows[at][1]][0]
        node = tree_links.setdefault(link, {"name": link, "children": []})
        node["children"].append({"name": item.path.rsplit("/", 1)[-1], "prototype": item.part, "instance": at})
    tree = {"name": robot.name, "children": [tree_links[link] for link in links if link in tree_links]}

    def posed(structure: dict[str, Any], asked: Any) -> dict[str, Any]:
        values, named = robot.values(asked)
        moved = instances(values)
        found = dict(structure)
        found["instances"] = [{**instance, "matrix": [float(v) for v in item.matrix.T.reshape(-1)]}
                              for instance, item in zip(structure["instances"], moved)]
        found["kinematics"] = {"pose": {"values": {name: round(value, 9) for name, value in values.items()},
                                        "configuration": named}}
        return found

    return assemble(robot.kind, path, robot.name, parts, placed, tree, files_of(robot.files), pose=posed)

"""URDF: a document as a ROS robot description, written from its robot description (``description.py``).

``write(view, path)`` describes the document (``describe``) and writes it; ``write_description``
writes a description it is handed. The file is one URDF at ``path`` and its meshes beside it,
binary STLs in metres in ``<path.parent>/<meshes>/``, each named ``<model>_<mesh>.stl``, the bytes
MJCF's writer makes of them (``export/mjcf.py``: one file per prototype, the same description the
same bytes), staged and moved into place as it moves its own. A mesh is named by the relative path
``<meshes>/<file>.stl``, which every URDF reader resolves beside the file, or, given ``package``,
by ``package://<package>/<meshes>/<file>.stl``, which ROS resolves when the URDF stands at the
root of that package. Nothing here imports the kernel: the writer is text and numpy (law 3).

**The tree.** URDF has no ground: its root link is where the robot's space is. The description's
ground (its first link, ``world``) is the root only where it holds something (a visual, a
collision, a mass); otherwise the first link hung from it by a ``fixed`` joint is the root, the
``base_link`` of a ROS robot under the name it has, and that joint is not written: the file's space
is that link's frame, and every other joint from the ground hangs from it, its origin carried into
that frame (``rooted``, which the SDF writer roots its tree by too). A ground that holds nothing and
has no fixed child stays, an empty root link, as a ROS ``world`` link is.

**Links.** Each link's frame is its joint's (the description's rule, and URDF's), so a visual's
and a collision's ``<origin>`` is its placement in the link frame, and a link's ``<inertial>`` is
its centre (``rpy`` zero) with its mass and the tensor about the centre in the link frame's axes, as
the description holds it; a link with no mass is given no ``<inertial>`` (the URDF validator warns
of a moving one: a simulator wants one, a viewer does not). A shape is a ``<mesh>`` (its ``scale``
the geometry's) or a primitive in URDF's full sizes: a ``<box size>``, a ``<sphere radius>``, a
``<cylinder radius length>``; a capsule, which URDF has no word for, is its cylinder and a sphere at
each end, three elements named ``<name>``, ``<name>_top`` and ``<name>_bottom``. A visual's colour
is a ``<material>`` declared once at the top and named in the visual: one per material name and
colour (a part with no material is ``color``), a repeat given ``_2``, ``_3``. A named frame is a
link of its own with nothing in it, hung from its link by a ``fixed`` joint ``<frame>_joint``, as a
ROS ``tool0`` is.

**Joints.** A joint's ``<origin>`` is its frame in the parent link's (``xyz``, and ``rpy`` the
fixed-axis roll, pitch and yaw of its turn), its ``<axis>`` that frame's Z, ``0 0 1``, since URDF
reads the axis in the joint frame. A revolute joint is ``revolute`` with its range, a continuous
one ``continuous`` with none; a prismatic one ``prismatic``; a cylindrical one two joints with a
massless link between them: ``<name>`` the turn (revolute or continuous) to ``<name>_turn``, then
``<name>_slide`` the slide to the child, as MJCF's writer orders its hinge and slide. A
``<limit>`` carries ``effort="0" velocity="0"``, which URDF requires and the description does not
know: a consumer that drives the joint sets them. A bound the description leaves open is written
``1e16`` (SDFormat's own word for none), since URDF ranges a revolute and a prismatic joint at both
ends. A spherical joint is refused by name: URDF has no ball (export an SDF or an MJCF, which do).
A coupling is a ``<mimic>`` on the follower (``multiplier`` its ratio, ``offset`` its offset), its
leader a joint that moves. URDF has no named states: the description's poses are not written (an
SRDF's group states are where ROS keeps them). A loop is refused by name, as every robot format
refuses one.

**Names.** URDF names are any text, but ROS tooling reads ``[A-Za-z0-9_]``: every other character
is ``_``, and a name already held is given ``_2``, ``_3``: links and joints share one namespace
(Gazebo reads a URDF as SDFormat, whose frame graph names both; the description's links are named
first), materials have their own. Numbers are
MJCF's writer's: nine significant digits at most, ``-0`` as ``0``, a length or an angle within 1e-12
of zero as zero.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

import numpy as np

from cad.engine.description import Description, DescriptionError, Geometry, Inertial, Joint, Link
from cad.engine.export import ExportRefused
from cad.engine.export.mjcf import SNAP, _Names, _number, _numbers, _stem, _stl, place

__all__ = ["UNBOUNDED", "rendered", "rooted", "write", "write_description"]

#: A bound the description leaves open, written where URDF wants one: SDFormat's word for no limit.
UNBOUNDED = 1e16


def write(view: Any, path: Path) -> None:
    """The export ``Kind``'s writer: ``view``'s document described and written to ``path``."""
    from cad.engine.describe import describe

    write_description(describe(view), path)


def write_description(description: Description, path: Any, *, meshes: str = "meshes",
                      package: str | None = None) -> list[Path]:
    """Write ``description`` as a URDF at ``path`` and its meshes in ``<path.parent>/<meshes>``, each
    named ``package://<package>/<meshes>/...`` where ``package`` is given; the files it holds, the URDF
    first."""
    path = Path(path)
    text, files = rendered(description, meshes, package)
    return place(path, text, files, meshes)


def rendered(description: Description, meshes: str = "meshes",
             package: str | None = None) -> tuple[str, dict[str, bytes]]:
    """``description`` as URDF text and its mesh files' bytes by file name, nothing written."""
    checked(description, "URDF")
    for joint in description.joints:
        if joint.kind == "spherical":
            raise ExportRefused(f"{description.name}: joint {joint.name!r} is spherical, and URDF has no ball joint: "
                                "no URDF is written of it (an SDF or an MJCF has one)")
    return _Writer(description, meshes, package).render()


def checked(description: Description, label: str) -> None:
    """A description a tree format writes, or refused by name: a loop, a broken tree."""
    if description.loops:
        raise ExportRefused(f"{description.name}: the mechanism has a loop through {', '.join(description.loops)}, "
                            f"and {label} writes a tree: no {label} is written of it")
    try:
        description.check()
    except DescriptionError as error:
        raise ExportRefused(f"{description.name}: {error}") from error


def rooted(description: Description) -> tuple[Link, list[Joint], Joint | None]:
    """The tree a format with no ground writes (the module's **The tree**): its root link, its joints
    parents first, and the fixed joint the root hung from the ground by, which is not written (None
    where the ground is the root). The description is not changed."""
    ground = description.root
    if ground.visuals or ground.collisions or ground.inertial is not None:
        return ground, list(description.joints), None
    dropped = next((joint for joint in description.joints
                    if joint.parent == ground.name and joint.kind == "fixed"), None)
    if dropped is None:
        return ground, list(description.joints), None
    carried = np.linalg.inv(np.asarray(dropped.origin, dtype=float))
    base = description.link(dropped.child)
    frames = dict(base.frames)
    for name, placed in ground.frames.items():  # the ground's named frames, now on the root
        wanted, at = name, 1
        while wanted in frames:
            at += 1
            wanted = f"{name}_{at}"
        frames[wanted] = carried @ np.asarray(placed, dtype=float)
    joints = []
    for joint in description.joints:
        if joint is dropped:
            continue
        if joint.parent == ground.name:
            joint = replace(joint, parent=base.name, origin=carried @ np.asarray(joint.origin, dtype=float))
        joints.append(joint)
    return replace(base, frames=frames), joints, dropped


# --- pieces the SDF writer shares ---------------------------------------------------------------------


def name_of(text: str, fallback: str) -> str:
    """A name as ROS tooling reads one: letters, digits and ``_``, the rest ``_``."""
    return re.sub(r"[^A-Za-z0-9_]", "_", str(text)) or fallback


class Xml:
    """An element laid out as the robot files here are: two spaces a level, its attributes in
    order, its text on its own line with it, a comment child (a ``str``) a line of its own."""

    def __init__(self, tag: str, attributes: Iterable[tuple[str, str | None]] = (), text: str | None = None):
        self.tag = tag
        self.attributes = [(key, value) for key, value in attributes if value is not None]
        self.text = text
        self.children: list[Xml | str] = []

    def add(self, tag: str, attributes: Iterable[tuple[str, str | None]] = (), text: str | None = None) -> Xml:
        child = Xml(tag, attributes, text)
        self.children.append(child)
        return child

    def lines(self, depth: int = 0) -> list[str]:
        indent = "  " * depth
        opened = indent + "<" + self.tag + "".join(f' {key}="{escape(value, {chr(34): "&quot;"})}"'
                                                    for key, value in self.attributes)
        if self.text is not None:
            return [f"{opened}>{escape(self.text)}</{self.tag}>"]
        if not self.children:
            return [opened + "/>"]
        found = [opened + ">"]
        for child in self.children:
            if isinstance(child, str):
                found.append(f"{indent}  <!-- {child.replace('--', '- -')} -->")
            else:
                found.extend(child.lines(depth + 1))
        return found + [f"{indent}</{self.tag}>"]


def rpy(matrix: Any) -> tuple[float, float, float]:
    """A rotation's fixed-axis roll, pitch and yaw (``Rz(yaw) @ Ry(pitch) @ Rx(roll)``), as URDF's
    ``rpy`` and SDFormat's pose read them; at a pitch of a quarter turn, the roll is zero."""
    r = np.array(np.asarray(matrix, dtype=float)[:3, :3])
    r[np.abs(r) < SNAP] = 0.0
    pitch = math.atan2(-r[2, 0], math.hypot(r[0, 0], r[1, 0]))
    if math.hypot(r[0, 0], r[1, 0]) < SNAP:
        return 0.0, pitch, math.atan2(-r[0, 1], r[1, 1])
    return math.atan2(r[2, 1], r[2, 2]), pitch, math.atan2(r[1, 0], r[0, 0])


def shaped(geometry: Geometry) -> list[tuple[str, np.ndarray, Geometry]]:
    """A shape as formats without a capsule write it: ``(suffix, placement, geometry)`` for each piece, a
    capsule its cylinder and a sphere at each end of it along its Z (``_top`` at +Z)."""
    placement = np.asarray(geometry.placement, dtype=float)
    if geometry.kind != "capsule":
        return [("", placement, geometry)]
    radius, length = (float(value) for value in geometry.size[:2])
    found = [("", placement, Geometry("cylinder", placement, size=(radius, length)))]
    for suffix, z in (("_top", length / 2), ("_bottom", -length / 2)):
        end = np.eye(4)
        end[2, 3] = z
        found.append((suffix, placement @ end, Geometry("sphere", placement @ end, size=(radius,))))
    return found


def inertia_terms(inertial: Inertial) -> list[tuple[str, str]]:
    """The six terms of a link's tensor about its centre, ``ixx ixy ixz iyy iyz izz``: symmetric, a term
    within 1e-12 of the largest of zero (the rounding of a product of frames) written as zero."""
    tensor = np.asarray(inertial.inertia, dtype=float)
    tensor = (tensor + tensor.T) / 2
    scale = float(np.abs(tensor).max()) if tensor.size else 0.0
    terms = (("ixx", 0, 0), ("ixy", 0, 1), ("ixz", 0, 2), ("iyy", 1, 1), ("iyz", 1, 2), ("izz", 2, 2))
    return [(key, _number(0.0 if abs(tensor[i, j]) <= SNAP * scale else tensor[i, j], snap=0)) for key, i, j in terms]


class MeshFiles:
    """Each mesh a description's geometry names, as a file: ``<model>_<mesh>.stl``, once per mesh
    however many links place it, its bytes MJCF's writer's."""

    def __init__(self, description: Description) -> None:
        self.description = description
        self.named = _Names()
        self.files: dict[str, bytes] = {}
        self.by_key: dict[str, str] = {}

    def __call__(self, key: str) -> str:
        found = self.by_key.get(key)
        if found is None:
            mesh = self.description.meshes[key]
            found = self.by_key[key] = self.named(f"{_stem(self.description.name)}_{_stem(mesh.name)}") + ".stl"
            self.files[found] = _stl(f"{self.description.name}/{mesh.name}", mesh.positions, mesh.triangles)
        return found


def bounds(joint: Joint, index: int) -> tuple[float | None, float | None]:
    """A joint's range of its ``index``-th value, None where it is open."""
    return joint.limits[index] if index < len(joint.limits) else (None, None)


# --- the rendering ---------------------------------------------------------------------------------


def _origin(matrix: Any) -> list[tuple[str, str]]:
    matrix = np.asarray(matrix, dtype=float)
    return [("xyz", _numbers(matrix[:3, 3])), ("rpy", _numbers(rpy(matrix)))]


class _Writer:
    def __init__(self, description: Description, meshes: str, package: str | None) -> None:
        self.description = description
        self.prefix = f"package://{package}/{meshes}" if package else meshes
        self.root, self.joints, _dropped = rooted(description)
        self.children: dict[str, list[Joint]] = {}
        for joint in self.joints:
            self.children.setdefault(joint.parent, []).append(joint)
        # Links and joints share one namespace: Gazebo reads a URDF as SDFormat, whose frame graph names both.
        self.names = _Names()
        self.material_names = _Names()
        self.links: dict[str, str] = {}
        self.joint_of: dict[str, str] = {}
        self.kinds = {joint.name: joint.kind for joint in self.joints}
        self.materials: dict[tuple[str, str], str] = {}
        self.material_rows: list[Xml] = []
        self.files = MeshFiles(description)
        # The description's own links are named first, then its joints, each in tree order; what the writer
        # adds (a cylindrical joint's link and slide, a named frame's link and joint) after, as it is written.
        order, pending = [], [self.root.name]
        while pending:
            name = pending.pop(0)
            order.append(name)
            pending.extend(joint.child for joint in self.children.get(name, ()))
        for name in order:
            self.links[name] = self.names(name_of(name, "link"))
        for name in order:
            for joint in self.children.get(name, ()):
                self.joint_of[joint.name] = self.names(name_of(joint.name, "joint"))

    def render(self) -> tuple[str, dict[str, bytes]]:
        body: list[Xml] = []
        self._subtree(body, self.root)
        sections = self.material_rows + body
        lines = ['<?xml version="1.0" encoding="utf-8"?>',
                 f'<robot name="{escape(name_of(self.description.name, "robot"))}">']
        for at, section in enumerate(sections):
            if at and (section.tag != "material" or sections[at - 1].tag != "material"):
                lines.append("")
            lines.extend(section.lines(1))
        lines.append("</robot>")
        return "\n".join(lines) + "\n", self.files.files

    def _subtree(self, body: list[Xml], link: Link) -> None:
        body.append(self._link(self.links[link.name], link))
        for name, placed in link.frames.items():
            frame = self.names(name_of(name, "frame"))
            joint = Xml("joint", [("name", self.names(f"{frame}_joint")), ("type", "fixed")])
            joint.add("origin", _origin(placed))
            joint.add("parent", [("link", self.links[link.name])])
            joint.add("child", [("link", frame)])
            body.extend([joint, Xml("link", [("name", frame)])])
        for joint in self.children.get(link.name, ()):
            child = self.description.link(joint.child)
            self._joint(body, joint)
            self._subtree(body, child)

    def _joint(self, body: list[Xml], joint: Joint) -> None:
        name, parent, child = self.joint_of[joint.name], self.links[joint.parent], self.links[joint.child]
        if joint.kind == "cylindrical":
            turned = self.names(f"{name}_turn")
            body.append(self._element(joint, name, self._turn(joint), parent, turned, joint.origin, 0))
            body.append(Xml("link", [("name", turned)]))
            slide = self.names(f"{name}_slide")
            body.append(self._element(joint, slide, "prismatic", turned, child, np.eye(4), 1, mimic=False))
            return
        kind = self._turn(joint) if joint.kind == "revolute" else joint.kind
        body.append(self._element(joint, name, kind, parent, child, joint.origin, 0))

    @staticmethod
    def _turn(joint: Joint) -> str:
        return "continuous" if bounds(joint, 0) == (None, None) else "revolute"

    def _element(self, joint: Joint, name: str, kind: str, parent: str, child: str, origin: Any, index: int, *,
                 mimic: bool = True) -> Xml:
        element = Xml("joint", [("name", name), ("type", kind)])
        element.add("origin", _origin(origin))
        element.add("parent", [("link", parent)])
        element.add("child", [("link", child)])
        if kind != "fixed":
            element.add("axis", [("xyz", "0 0 1")])
        if kind in ("revolute", "prismatic"):
            lower, upper = bounds(joint, index)
            element.add("limit", [("lower", _number(-UNBOUNDED if lower is None else lower)),
                                  ("upper", _number(UNBOUNDED if upper is None else upper)),
                                  ("effort", "0"), ("velocity", "0")])
        if mimic and joint.follows is not None:
            leader, ratio, offset = joint.follows
            if self.kinds.get(leader) not in ("revolute", "continuous", "prismatic", "cylindrical"):
                raise ExportRefused(f"{self.description.name}: joint {joint.name!r} follows {leader!r}, and a URDF "
                                    "mimic follows a joint that moves: "
                                    + (f"{leader!r} is a {self.kinds[leader]} joint" if leader in self.kinds
                                       else f"{leader!r} is no joint here"))
            element.add("mimic", [("joint", self.joint_of[leader]), ("multiplier", _number(ratio, snap=0)),
                                  ("offset", _number(offset))])
        return element

    def _link(self, name: str, link: Link) -> Xml:
        element = Xml("link", [("name", name)])
        if link.inertial is not None:
            inertial = element.add("inertial")
            inertial.add("origin", [("xyz", _numbers(link.inertial.center)), ("rpy", "0 0 0")])
            inertial.add("mass", [("value", _number(link.inertial.mass, snap=0))])
            inertial.add("inertia", inertia_terms(link.inertial))
        visuals, collisions = _Names(), _Names()
        for visual in link.visuals:
            wanted = name_of(visual.name, "visual")
            material = self._material(visual.material, tuple(float(value) for value in visual.color))
            for suffix, placement, geometry in shaped(visual.geometry):
                piece = element.add("visual", [("name", visuals(wanted + suffix))])
                piece.add("origin", _origin(placement))
                piece.add("geometry").children.append(self._shape(geometry))
                piece.add("material", [("name", material)])
        for collision in link.collisions:
            wanted = name_of(collision.name, "collision")
            for suffix, placement, geometry in shaped(collision.geometry):
                piece = element.add("collision", [("name", collisions(wanted + suffix))])
                piece.add("origin", _origin(placement))
                piece.add("geometry").children.append(self._shape(geometry))
        return element

    def _shape(self, geometry: Geometry) -> Xml:
        size = [float(value) for value in geometry.size]
        if geometry.kind == "mesh":
            file = self.files(str(geometry.mesh))
            return Xml("mesh", [("filename", f"{self.prefix}/{file}"),
                                ("scale", _numbers((float(geometry.scale),) * 3, snap=0))])
        if geometry.kind == "box":
            return Xml("box", [("size", _numbers(size[:3]))])
        if geometry.kind == "sphere":
            return Xml("sphere", [("radius", _number(size[0]))])
        if geometry.kind == "cylinder":
            return Xml("cylinder", [("radius", _number(size[0])), ("length", _number(size[1]))])
        raise ExportRefused(f"{self.description.name}: no URDF geometry is a {geometry.kind!r}")

    def _material(self, name: str | None, rgba: tuple[float, ...]) -> str:
        key = (name or "", _numbers(rgba, snap=0))
        found = self.materials.get(key)
        if found is None:
            found = self.materials[key] = self.material_names(name_of(name, "color") if name else "color")
            material = Xml("material", [("name", found)])
            material.add("color", [("rgba", key[1])])
            self.material_rows.append(material)
        return found

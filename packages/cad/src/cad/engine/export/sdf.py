"""SDF: a document as an SDFormat 1.9 model (Gazebo's), written from its robot description (``description.py``).

``write(view, path)`` describes the document (``describe``) and writes it; ``write_description``
writes a description it is handed. The file is one ``<sdf version="1.9">`` holding one ``<model>`` at
``path``, and its meshes beside it, binary STLs in metres in ``<path.parent>/<meshes>/``, the files
and bytes the URDF writer makes of them (``export/urdf.py``, ``MeshFiles``), staged and moved into
place as MJCF's writer moves its own. A mesh is named by the relative URI ``<meshes>/<file>.stl``,
which SDFormat resolves beside the file, as the SDF validator and the stills do. Nothing here
imports the kernel: the writer is text and numpy (law 3).

**The tree** is the URDF writer's (``urdf.rooted``): the ground is a link only where it holds
something, else its first fixed child is the root. SDFormat has a world of its own, so the root is
fixed to it by a ``fixed`` joint whose parent is ``world`` (named for the joint the root hung from
the ground by, else ``world_joint``): the model stands where the document built it and a scene can
free it by dropping that one joint. ``world`` names SDFormat's world frame and ``__model__`` the
model's, so a ground written as a link is named ``ground``.

**Frames.** Every link's ``<pose>`` is its frame at the as-built state in the model frame
(``relative_to="__model__"``): the description's frames as they are, so nothing composes on the way
out. A joint's frame is its child's (the description's rule), so its ``<pose>`` is the identity
``relative_to`` the child, and its ``<axis><xyz>`` is ``0 0 1`` in that joint frame, SDFormat's
default frame for it. A visual's, a collision's and the inertial's ``<pose>`` is in the link frame
(written where it is not the identity). A named frame is a ``<frame>`` attached to its link, posed
``relative_to`` it.

**Links.** A link's ``<inertial>`` is its centre, mass and tensor about the centre in the link
frame's axes; a link with no mass is given none, which SDFormat reads as its default (one
kilogram, a unit tensor): the description has no mass to give it, and the cylindrical joint's link
between its two joints has none either. A shape is a ``<mesh>`` (its ``<scale>`` the geometry's) or
a primitive in SDFormat's full sizes, ``<box><size>``, ``<sphere><radius>``, ``<cylinder>`` and
``<capsule>`` (``<radius>``, ``<length>`` the length of its cylinder, as ``describe`` fits it): SDF
has a capsule. A visual's colour is its ``<material>``'s ``<ambient>`` and ``<diffuse>``.

**Joints.** A revolute joint is ``revolute`` with its ``<limit>`` (a bound the description leaves open
not written: SDFormat's default is none), a continuous one ``continuous``, a prismatic one
``prismatic``, a spherical one ``ball``, a fixed one ``fixed``; a cylindrical one two joints with a
link between them, as the URDF writer writes it (``<name>`` the turn to ``<name>_turn``, then
``<name>_slide``). SDFormat 1.9 has no mimic (a ``gearbox`` is a different joint), so a coupling is
said in a comment on its follower and not enforced: a simulator that wants it couples the two
itself. SDFormat has no named states either: the description's poses are not written. A loop is
refused by name, as every robot format refuses one.

**Names.** As the URDF writer's: ``[A-Za-z0-9_]``, the rest ``_``, a repeat given ``_2``, ``_3``;
links, joints and frames share one namespace, as SDFormat's frame graph does, and visuals and
collisions are unique within their link.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cad.engine.description import Description, Geometry, Joint, Link
from cad.engine.export import ExportRefused
from cad.engine.export.mjcf import _Names, _number, _numbers, place
from cad.engine.export.urdf import MeshFiles, Xml, bounds, checked, inertia_terms, name_of, rooted, rpy

__all__ = ["VERSION", "rendered", "write", "write_description"]

#: The SDFormat version written.
VERSION = "1.9"
#: Names SDFormat's frame graph keeps for itself.
RESERVED = ("world", "__model__")


def write(view: Any, path: Path) -> None:
    """The export ``Kind``'s writer: ``view``'s document described and written to ``path``."""
    from cad.engine.describe import describe

    write_description(describe(view), path)


def write_description(description: Description, path: Any, *, meshes: str = "meshes") -> list[Path]:
    """Write ``description`` as an SDF at ``path`` and its meshes in ``<path.parent>/<meshes>``; the files
    it holds, the SDF first."""
    path = Path(path)
    text, files = rendered(description, meshes)
    return place(path, text, files, meshes)


def rendered(description: Description, meshes: str = "meshes") -> tuple[str, dict[str, bytes]]:
    """``description`` as SDF text and its mesh files' bytes by file name, nothing written."""
    checked(description, "SDF")
    return _Writer(description, meshes).render()


def _pose(matrix: Any) -> str:
    matrix = np.asarray(matrix, dtype=float)
    return _numbers([*matrix[:3, 3], *rpy(matrix)])


class _Writer:
    def __init__(self, description: Description, meshes: str) -> None:
        self.description = description
        self.meshes = meshes
        self.root, self.joints, self.dropped = rooted(description)
        self.children: dict[str, list[Joint]] = {}
        for joint in self.joints:
            self.children.setdefault(joint.parent, []).append(joint)
        self.names = _Names()
        self.names.taken.update(RESERVED)
        self.files = MeshFiles(description)
        # The description's links and joints are named first, in tree order, the root after the other links
        # so a ground written as a link is ``ground`` only where no link of the model is; what the writer
        # adds (the world joint, a cylindrical joint's link and slide, a frame) is named as it is written.
        self.links: dict[str, str] = {}
        self.joint_of: dict[str, str] = {}
        order, pending = [], [self.root.name]
        while pending:
            name = pending.pop(0)
            order.append(name)
            for joint in self.children.get(name, ()):
                pending.append(joint.child)
        for name in order[1:]:
            self.links[name] = self.names(name_of(name, "link"))
        wanted = name_of(self.root.name, "link")
        self.links[self.root.name] = self.names("ground" if wanted in RESERVED else wanted)
        for name in order:
            for joint in self.children.get(name, ()):
                self.joint_of[joint.name] = self.names(name_of(joint.name, "joint"))

    def render(self) -> tuple[str, dict[str, bytes]]:
        model = Xml("model", [("name", name_of(self.description.name, "model"))])
        root = self.links[self.root.name]
        model.children.append(self._link(root, self.root, self.root.frame))
        fixed = model.add("joint", [("name", self.names(name_of(self.dropped.name, "joint") if self.dropped
                                                        else "world_joint")), ("type", "fixed")])
        fixed.add("parent", text="world")
        fixed.add("child", text=root)
        self._frames(model, self.root)
        self._subtree(model, self.root)
        lines = ['<?xml version="1.0" encoding="utf-8"?>', f'<sdf version="{VERSION}">']
        lines.extend(model.lines(1))
        lines.append("</sdf>")
        return "\n".join(lines) + "\n", self.files.files

    def _subtree(self, model: Xml, link: Link) -> None:
        for joint in self.children.get(link.name, ()):
            child = self.description.link(joint.child)
            self._joint(model, joint, child)
            model.children.append(self._link(self.links[child.name], child, child.frame))
            self._frames(model, child)
            self._subtree(model, child)

    def _frames(self, model: Xml, link: Link) -> None:
        owner = self.links[link.name]
        for name, placed in link.frames.items():
            frame = model.add("frame", [("name", self.names(name_of(name, "frame"))), ("attached_to", owner)])
            frame.add("pose", [("relative_to", owner)], text=_pose(placed))

    def _joint(self, model: Xml, joint: Joint, child: Link) -> None:
        name, parent, child_name = self.joint_of[joint.name], self.links[joint.parent], self.links[child.name]
        if joint.kind == "cylindrical":
            turned = self.names(f"{name}_turn")
            turn = "continuous" if bounds(joint, 0) == (None, None) else "revolute"
            model.children.append(self._element(joint, name, turn, parent, turned, 0))
            model.children.append(self._link(turned, Link(turned, child.frame), child.frame))
            model.children.append(self._element(joint, self.names(f"{name}_slide"), "prismatic", turned, child_name,
                                                1, coupled=False))
            return
        kind = {"spherical": "ball"}.get(joint.kind, joint.kind)
        if kind == "revolute" and bounds(joint, 0) == (None, None):
            kind = "continuous"
        model.children.append(self._element(joint, name, kind, parent, child_name, 0))

    def _element(self, joint: Joint, name: str, kind: str, parent: str, child: str, index: int, *,
                 coupled: bool = True) -> Xml:
        element = Xml("joint", [("name", name), ("type", kind)])
        if coupled and joint.follows is not None:
            leader, ratio, offset = joint.follows
            said = self.joint_of.get(leader, leader)
            element.children.append(f"follows {said}: {name} = {_number(ratio, snap=0)} * {said} + {_number(offset)} "
                                    f"(SDFormat {VERSION} has no mimic: a simulator couples them itself)")
        element.add("pose", [("relative_to", child)], text="0 0 0 0 0 0")
        element.add("parent", text=parent)
        element.add("child", text=child)
        if kind in ("revolute", "continuous", "prismatic"):
            axis = element.add("axis")
            axis.add("xyz", text="0 0 1")
            lower, upper = bounds(joint, index)
            if kind != "continuous" and (lower is not None or upper is not None):
                limit = axis.add("limit")
                if lower is not None:
                    limit.add("lower", text=_number(lower))
                if upper is not None:
                    limit.add("upper", text=_number(upper))
        return element

    def _link(self, name: str, link: Link, frame: Any) -> Xml:
        element = Xml("link", [("name", name)])
        element.add("pose", [("relative_to", "__model__")], text=_pose(frame))
        if link.inertial is not None:
            inertial = element.add("inertial")
            inertial.add("pose", text=_numbers([*link.inertial.center, 0, 0, 0]))
            inertial.add("mass", text=_number(link.inertial.mass, snap=0))
            inertia = inertial.add("inertia")
            for key, value in inertia_terms(link.inertial):
                inertia.add(key, text=value)
        visuals, collisions = _Names(), _Names()
        for visual in link.visuals:
            piece = element.add("visual", [("name", visuals(name_of(visual.name, "visual")))])
            self._placed(piece, visual.geometry)
            rgba = _numbers([float(value) for value in visual.color], snap=0)
            material = piece.add("material")
            material.add("ambient", text=rgba)
            material.add("diffuse", text=rgba)
        for collision in link.collisions:
            piece = element.add("collision", [("name", collisions(name_of(collision.name, "collision")))])
            self._placed(piece, collision.geometry)
        return element

    def _placed(self, piece: Xml, geometry: Geometry) -> None:
        placement = _pose(geometry.placement)
        if placement != "0 0 0 0 0 0":
            piece.add("pose", text=placement)
        piece.add("geometry").children.append(self._shape(geometry))

    def _shape(self, geometry: Geometry) -> Xml:
        size = [float(value) for value in geometry.size]
        if geometry.kind == "mesh":
            shape = Xml("mesh")
            shape.add("uri", text=f"{self.meshes}/{self.files(str(geometry.mesh))}")
            shape.add("scale", text=_numbers((float(geometry.scale),) * 3, snap=0))
            return shape
        if geometry.kind == "box":
            shape = Xml("box")
            shape.add("size", text=_numbers(size[:3]))
            return shape
        if geometry.kind == "sphere":
            shape = Xml("sphere")
            shape.add("radius", text=_number(size[0]))
            return shape
        if geometry.kind in ("cylinder", "capsule"):
            shape = Xml(geometry.kind)
            shape.add("radius", text=_number(size[0]))
            shape.add("length", text=_number(size[1]))
            return shape
        raise ExportRefused(f"{self.description.name}: no SDF geometry is a {geometry.kind!r}")


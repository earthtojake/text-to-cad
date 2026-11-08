"""A robot description: what a simulator or ROS needs of a document, in their units, the one
form every robot format is written from.

A document holds parts with materials, their placements, and a mechanism (``mechanism.py``:
links, pairs, couplings, states). A simulator wants the same facts as a tree of rigid bodies:
each with its mass, centre and inertia, its visual meshes, its collision shapes and its named
frames; joints between them with axes, limits and couplings; named poses. ``describe`` builds
that tree from a document (``description_of``, the engine's half that needs the kernel: mass
properties and collision fits), and the writers of each format serialise it (``export/mjcf.py``,
``export/urdf.py``, ``export/sdf.py``) without touching the kernel. Nothing in a description
names a format: no MuJoCo group, no ROS package, no Gazebo frame rule; those are each writer's
reading of it.

**Units and frames.** Everything here is SI: metres, kilograms, radians, kg*m^2. The document's
millimetres and degrees are converted once, in ``describe``. Every frame is taken at the AS-BUILT
state (``mechanism.as_built``: the pose every file of the model shows), which is every joint's
zero here: a joint's ``as_built`` value is recorded, and its ``lower``/``upper`` are around zero,
so a writer that wants the authored range back adds it (MJCF's ``ref`` is zero because the body is
authored where it stands; URDF's zero is the same pose). A joint's ``origin`` is its frame in the
PARENT link's frame, its axis that frame's Z, as AP242 pairs have it (the pair's ``frames[0]`` on
link 1, turned or slid by the as-built value). A jointed link's ``frame`` IS its joint's frame in
the model's space, as URDF has it, so ``child.frame == parent.frame @ joint.origin`` at zero, and
the link's geometry, inertial and named frames are expressed in that frame (the part's own
placement composed with the pair's ``frames[1]``, which is where the child's frame stands in the
part); a link no pair moves keeps its first part's placement as its frame; the ground is the
model's space. Colours are sRGB in 0..1 with alpha, as the formats write them (the document's are
linear).

**Mass.** A link's ``inertial`` sums its parts' solids at their materials' densities: mass, centre
of mass in the link frame, and the inertia tensor about that centre in the link frame's axes. A
link whose parts have no density has ``inertial`` None: a writer says so (MuJoCo computes one
from the geoms; URDF needs one, so the URDF writer refuses by name unless told to guess). A part
whose material names a density that is not positive is refused by name.

**Geometry.** A ``Mesh`` is one prototype's triangles in the prototype's own frame, in metres:
positions ``(n, 3)`` float32 and triangles ``(m, 3)`` uint32, with the key the document knows it
by, so a writer writes each prototype once however many links place it. A visual is a mesh, with
its colour; a collision is what the part's ``collision`` declaration asked for
(``cad.build123d.collision``): the mesh itself (a simulator hulls it; the default), a ``box``, a
``sphere``, a ``cylinder`` or a ``capsule`` fitted to the part by the kernel (an oriented bounding
box, its axis the longest side), or none. Named frames (``cad.build123d.frame``) are kept on their
link, in the link's frame, for a writer's sites or fixed frames.

**Joints.** A pair becomes a joint of ``kind`` ``revolute`` (a range) or ``continuous`` (none),
``prismatic`` (a slide, ranged or not), ``cylindrical`` (a turn and a slide on one axis: two
values), or ``spherical`` (three angles); a part no pair moves hangs from the ground, or from the
link it is below in the tree, by a ``fixed`` joint. The ground is the first link, named ``world``
unless the model names it. A coupling is written on the joint that follows: ``follows =
(leader, ratio, offset)`` meaning ``value = ratio * leader + offset`` around zero, which is what
URDF's ``<mimic>`` and MuJoCo's ``<equality><joint>`` say; a coupling of more than two joints is
a chain of followers from its first. A mechanism with a loop is described with its pairs and
``loops`` naming them, and every writer refuses it (no format here solves a loop).

**Poses.** The mechanism's named states, each as ``{joint: value}`` around zero, in radians or
metres (a cylindrical or spherical joint's value is a tuple). Configuration sequences are not
here: a GLB bakes them; a simulator plays its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = ["COLLISIONS", "Collision", "Description", "DescriptionError", "Geometry", "Inertial", "Joint", "Link",
           "Mesh", "Pose", "Visual"]

#: What a part's collision may be (``cad.build123d.collision``): the mesh itself, a fitted primitive, or none.
COLLISIONS = ("mesh", "box", "sphere", "cylinder", "capsule", "none")
#: The joint kinds, in the words URDF uses where it has one; ``cylindrical`` and ``spherical`` are AP242's.
JOINT_KINDS = ("fixed", "revolute", "continuous", "prismatic", "cylindrical", "spherical")

Matrix = np.ndarray  # a 4x4 float64 rigid transform, row-major, metres


class DescriptionError(ValueError):
    """A document that cannot be described as a robot, said by name (a loop, a density that is not
    positive, a part that is no solid where a mass is needed)."""


@dataclass(frozen=True)
class Mesh:
    """One prototype's triangles, in its own frame, in metres."""

    key: str  # the document's geometry key: one mesh per key however many links place it
    name: str  # the prototype's name, a writer's file stem (made unique by the writer)
    positions: np.ndarray  # (n, 3) float32, metres
    triangles: np.ndarray  # (m, 3) uint32
    normals: np.ndarray | None = None  # (n, 3) float32, where the tessellation has them


@dataclass(frozen=True)
class Geometry:
    """A shape placed in a link's frame: a mesh (``mesh`` the key of one of ``Description.meshes``, ``scale``
    its uniform scale, 1 for a mesh written in metres) or a primitive in full sizes: a ``box``'s
    ``size`` is (x, y, z); a ``sphere``'s (radius,); a ``cylinder``'s and a ``capsule``'s (radius, length)
    along the placement's Z."""

    kind: str  # "mesh" | "box" | "sphere" | "cylinder" | "capsule"
    placement: Matrix
    mesh: str | None = None
    scale: float = 1.0
    size: tuple[float, ...] = ()


@dataclass(frozen=True)
class Visual:
    name: str
    geometry: Geometry
    color: tuple[float, float, float, float]  # sRGB, 0..1
    material: str | None = None  # the material's name, where the part has one


@dataclass(frozen=True)
class Collision:
    name: str
    geometry: Geometry


@dataclass(frozen=True)
class Inertial:
    mass: float  # kg
    center: np.ndarray  # (3,) metres, in the link frame
    inertia: np.ndarray  # (3, 3) kg*m^2 about ``center``, in the link frame's axes


@dataclass
class Link:
    name: str
    frame: Matrix  # in the model's space at the as-built state
    visuals: list[Visual] = field(default_factory=list)
    collisions: list[Collision] = field(default_factory=list)
    inertial: Inertial | None = None
    frames: dict[str, Matrix] = field(default_factory=dict)  # named frames in the link frame (sites)
    parts: tuple[int, ...] = ()  # the document's instance indices this link places (provenance)


@dataclass
class Joint:
    name: str
    kind: str  # one of JOINT_KINDS
    parent: str
    child: str
    origin: Matrix  # the joint frame in the parent link's frame at zero; its Z is the axis
    #: Per value (one, or two for cylindrical: turn then slide, three for spherical): the range around zero in
    #: radians or metres, None where unlimited.
    limits: tuple[tuple[float | None, float | None], ...] = ()
    as_built: tuple[float, ...] = ()  # the authored value(s) that zero stands for, radians or metres
    follows: tuple[str, float, float] | None = None  # (leader joint, ratio, offset): value = ratio * leader + offset

    def __post_init__(self) -> None:
        if self.kind not in JOINT_KINDS:
            raise ValueError(f"joint {self.name!r}: kind {self.kind!r} is none of {', '.join(JOINT_KINDS)}")

    @property
    def axis(self) -> np.ndarray:
        """The joint's axis in the parent link's frame: its frame's Z."""
        return np.asarray(self.origin, dtype=float)[:3, 2].copy()

    @property
    def lower(self) -> float | None:
        return self.limits[0][0] if self.limits else None

    @property
    def upper(self) -> float | None:
        return self.limits[0][1] if self.limits else None


@dataclass(frozen=True)
class Pose:
    name: str
    values: dict[str, float | tuple[float, ...]]  # joint name -> value(s) around zero


@dataclass
class Description:
    """A document as a robot: links in tree order (the ground first), joints parents-first, the meshes the
    links' geometry names, the poses, and the mechanism's loops (every writer refuses a description with one)."""

    name: str
    links: list[Link]
    joints: list[Joint]
    meshes: dict[str, Mesh] = field(default_factory=dict)
    poses: list[Pose] = field(default_factory=list)
    loops: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()  # what the description could not carry, said once each

    @property
    def root(self) -> Link:
        return self.links[0]

    def link(self, name: str) -> Link:
        found = next((link for link in self.links if link.name == name), None)
        if found is None:
            raise KeyError(name)
        return found

    def children(self, name: str) -> list[Joint]:
        return [joint for joint in self.joints if joint.parent == name]

    def controls(self) -> list[Joint]:
        """The joints a person or a controller moves: not fixed, not following another."""
        return [joint for joint in self.joints if joint.kind != "fixed" and joint.follows is None]

    def check(self) -> None:
        """The tree's invariants, raised by name: one root, every joint between known links, every child
        placed by one joint, meshes the geometry names present, no loop. A loop is said first: its
        closing joint places a link a second time."""
        if self.loops:
            raise DescriptionError(f"the mechanism has a loop through {', '.join(self.loops)}: no robot format "
                                   f"writes one")
        names = [link.name for link in self.links]
        if len(set(names)) != len(names):
            raise DescriptionError(f"link names repeat: {sorted({n for n in names if names.count(n) > 1})}")
        known = set(names)
        placed: dict[str, str] = {}
        for joint in self.joints:
            for end in (joint.parent, joint.child):
                if end not in known:
                    raise DescriptionError(f"joint {joint.name!r} names link {end!r}, which there is not")
            if joint.child in placed:
                raise DescriptionError(f"link {joint.child!r} is placed by two joints: {placed[joint.child]!r} and "
                                       f"{joint.name!r}")
            placed[joint.child] = joint.name
        for link in self.links[1:]:
            if link.name not in placed:
                raise DescriptionError(f"link {link.name!r} hangs from nothing: no joint places it")
        if self.root.name in placed:
            raise DescriptionError(f"the root link {self.root.name!r} is placed by joint {placed[self.root.name]!r}")
        for link in self.links:
            for geometry in [v.geometry for v in link.visuals] + [c.geometry for c in link.collisions]:
                if geometry.kind == "mesh" and geometry.mesh not in self.meshes:
                    raise DescriptionError(f"link {link.name!r} names mesh {geometry.mesh!r}, which there is not")


def srgb(linear: tuple[float, ...] | None, default: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)) -> tuple[float, float, float, float]:
    """A document colour (linear RGBA) as the formats write it (sRGB)."""
    if not linear:
        return default

    def channel(value: float) -> float:
        value = max(0.0, min(1.0, float(value)))
        return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055

    r, g, b = (channel(v) for v in linear[:3])
    return (r, g, b, float(linear[3]) if len(linear) > 3 else 1.0)


def column_major(values: Any) -> Matrix:
    """A structure matrix (16 floats, column-major, millimetres) as a row-major 4x4 in metres."""
    matrix = np.asarray(values, dtype=float).reshape(4, 4).T.copy()
    matrix[:3, 3] *= 0.001
    return matrix

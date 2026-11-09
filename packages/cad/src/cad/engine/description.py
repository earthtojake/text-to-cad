"""A robot description: what a simulator or ROS needs of a document, in their units, the one
form every robot format is written from.

A document holds parts with materials, their placements, and a mechanism (``mechanism.py``:
links, pairs, couplings, states). A simulator wants the same facts as a tree of rigid bodies:
each with its mass, centre and inertia, its visual meshes, its collision shapes and its named
frames; joints between them with axes, limits and couplings; named poses. ``describe`` builds
that tree from a document (``description_of``, the engine's half that needs the kernel: mass
properties and collision fits), and the writers of each format serialise it (``export/mjcf.py``,
``export/urdf.py``) without touching the kernel. Nothing in a description
names a format: no MuJoCo group, no ROS package; those are each writer's
reading of it.

**Units and frames.** Everything here is SI: metres, kilograms, radians, kg*m^2. The document's
millimetres and degrees are converted once, in ``describe``. Every frame is taken at the ZERO state,
every joint's zero here: the AS-BUILT state (``mechanism.as_built``: the pose every file of the model
shows), or the mechanism state a description is asked to be zero at (``describe``'s ``zero``, the
description's ``zero`` its name), where every body stands as that state poses it and each joint's value
there is its zero. A joint's ``as_built`` value is the authored value its zero stands for (the state's,
given a ``zero``), and its ``lower``/``upper`` are around zero,
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

**Mass.** A link's ``inertial`` sums its parts' solids at their materials' densities, and their
point masses (``cad.build123d.point_mass``): mass, centre of mass in the link frame, and the inertia
tensor about that centre in the link frame's axes. A part or an assembly declared to weigh so much
(``cad.build123d.mass``) has its solids scaled alike to make up that total, its point masses
included (``describe``'s **Mass**). A link whose parts have no density and no declared mass has
``inertial`` None, and each writer does what its format does
with a link that has none: MuJoCo computes one from the geoms, and a URDF link goes without and its
validator warns. A part whose material names a density that
is not positive is refused by name.

**Geometry.** A ``Mesh`` is one prototype's triangles in the prototype's own frame, in metres:
positions ``(n, 3)`` float32 and triangles ``(m, 3)`` uint32, with the key the document knows it
by, so a writer writes each prototype once however many links place it. A visual is a mesh, with
its colour; a collision is what the part's ``collision`` declaration asked for
(``cad.build123d.collision``): the mesh itself (a simulator hulls it; the default), a ``box``, a
``sphere``, a ``cylinder`` or a ``capsule`` fitted to the part by the kernel (an oriented bounding
box, its axis the longest side), the convex hulls CoACD cuts the part's mesh into (``decomposed``: a
collision per hull, each a mesh of its own, ``<part>_hull<i>``, its ``part`` the part's name), or
none; its ``friction`` is the part's contact friction
(``cad.build123d.friction``: sliding, or sliding, torsional and rolling), empty where it declares
none and a simulator's default applies. Named frames (``cad.build123d.frame``) are kept on their
link, in the link's frame, for a writer's sites or fixed frames. A part declared a body
(``cad.build123d.body``) is a link of its own, at its own placement, hung by a ``fixed`` joint of its
name from the link it would have merged into, with its own mass, geometry and frames.

**Joints.** A pair becomes a joint of ``kind`` ``revolute`` (a range) or ``continuous`` (none),
``prismatic`` (a slide, ranged or not), ``cylindrical`` (a turn and a slide on one axis: two
values), or ``spherical`` (three angles); a part no pair moves hangs from the ground, or from the
link it is below in the tree, by a ``fixed`` joint. The ground is the first link, named ``world``
unless the model names it. A link hung from the ground that floats (``cad.build123d.free``: a robot's
base not bolted to the world) hangs by a ``floating`` joint, URDF's word: six values, no axis and no
limits, its zero the link's frame; no pose names it, and nothing follows or leads it. A coupling is written on the joint that follows: ``follows =
(leader, ratio, offset)`` meaning ``value = ratio * leader + offset`` around zero, which is what
URDF's ``<mimic>`` and MuJoCo's ``<equality><joint>`` say; a coupling of more than two joints is
a chain of followers from its first. A virtual pinion (``mechanism``'s: a ``rack_and_pinion_pair``'s
first joint that holds no part) is no link and no joint here: its link carries nothing a simulator
needs, so its racks follow the first of them, by the ratio of their ratios, and that rack is the
coupling's control. A joint's ``effort`` and ``velocity`` are its drive's bounds
(``cad.build123d.limits``): N*m and rad/s for a turn, N and m/s for a slide, None where the model
gives none; its ``armature`` (kg*m^2, kg), ``damping`` (N*m*s/rad, N*s/m) and ``friction`` (N*m, N)
are the joint's own dynamics, None where the model gives none.

**Loops.** A mechanism whose pairs close a loop is a tree and its ``closures``: the tree is the pairs
followed from the ground, breadth first, in the mechanism's pair order, and each pair that reaches a
link the tree already holds is a ``Closure``, not a joint -- the loop's last pair to be reached, which is
the pair an author pairs by label once the rest are connected. A closure that would be a slide (a
prismatic or cylindrical pair) is moved to the loop's revolute or ball pair nearest it, so a writer can
close the loop with point constraints, and the slide is a joint of the tree. A closure's two frames, one
on each link, coincide as built (``describe`` refuses one that does not, by name), so the loop is closed
at zero; a writer that can close it does (MJCF), one that cannot leaves it open and says so (URDF).

**Contacts.** ``excludes`` are the link pairs a model says never collide (``cad.build123d.exclude``),
each pair once, in link order; what a writer finds touching at rest is its own (``export/contact.py``).

**Poses.** The mechanism's named states, each as ``{joint: value}`` around zero, in radians or
metres (a cylindrical or spherical joint's value is a tuple); taken at a ``zero`` state, every other
state is around that one, and the zero state's own pose is every value at zero. Configuration sequences are not
here: a GLB bakes them; a simulator plays its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = ["COLLISIONS", "Closure", "Collision", "Description", "DescriptionError", "Geometry", "Inertial", "Joint",
           "Link", "Mesh", "Pose", "Visual"]

#: What a part's collision may be (``cad.build123d.collision``): the mesh itself, a fitted primitive, the
#: convex hulls of a decomposition of its mesh, or none.
COLLISIONS = ("mesh", "box", "sphere", "cylinder", "capsule", "decomposed", "none")
#: The joint kinds, in the words URDF uses where it has one; ``cylindrical`` and ``spherical`` are AP242's.
JOINT_KINDS = ("fixed", "revolute", "continuous", "prismatic", "cylindrical", "spherical", "floating")
#: The joints a closure may be: a slide is kept a joint of the tree where its loop has a turn or a ball.
CLOSURE_KINDS = ("revolute", "continuous", "prismatic", "cylindrical", "spherical")

Matrix = np.ndarray  # a 4x4 float64 rigid transform, row-major, metres


class DescriptionError(ValueError):
    """A document that cannot be described as a robot, said by name (a loop that does not close as built, a
    density that is not positive, a mass its parts cannot carry)."""


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
    friction: tuple[float, ...] = ()  # (sliding,) or (sliding, torsional, rolling); () where none is declared
    part: str = ""  # the part it is one hull of (a decomposition: ``name`` is ``<part>_hull<i>``); "" where ``name`` is

    @property
    def of(self) -> str:
        """The name of the part this collides for: its own, or the part it is one hull of."""
        return self.part or self.name


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
    effort: float | None = None  # the drive's bound: N*m for a turn, N for a slide; None where unbounded
    velocity: float | None = None  # rad/s for a turn, m/s for a slide; None where unbounded
    armature: float | None = None  # the rotor's reflected inertia: kg*m^2 for a turn, kg for a slide
    damping: float | None = None  # N*m*s/rad for a turn, N*s/m for a slide
    friction: float | None = None  # the drive's dry friction: N*m for a turn, N for a slide

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


@dataclass
class Closure:
    """A pair the tree leaves out to close a loop (the module's **Loops**): a joint from ``parent`` to
    ``child``, both links of the tree, whose frame is ``origin`` in the parent's frame and ``frame`` in the
    child's, the two the same place in the model's space as built; its Z is the axis. ``loop`` names the
    loop's joints, this one among them, from the ground's side."""

    name: str
    kind: str  # one of CLOSURE_KINDS
    parent: str
    child: str
    origin: Matrix  # the joint frame in the parent link's frame at zero
    frame: Matrix  # the same frame in the child link's frame
    limits: tuple[tuple[float | None, float | None], ...] = ()  # as a Joint's: around zero, SI
    as_built: tuple[float, ...] = ()
    loop: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in CLOSURE_KINDS:
            raise ValueError(f"closure {self.name!r}: kind {self.kind!r} is none of {', '.join(CLOSURE_KINDS)}")


@dataclass(frozen=True)
class Pose:
    name: str
    values: dict[str, float | tuple[float, ...]]  # joint name -> value(s) around zero


@dataclass
class Description:
    """A document as a robot: links in tree order (the ground first), joints parents-first, the meshes the
    links' geometry names, the poses, the link pairs that never collide, and the joints that close the
    mechanism's loops (``closures``: the module's **Loops**), which the tree leaves out."""

    name: str
    links: list[Link]
    joints: list[Joint]
    meshes: dict[str, Mesh] = field(default_factory=dict)
    poses: list[Pose] = field(default_factory=list)
    closures: list[Closure] = field(default_factory=list)
    warnings: tuple[str, ...] = ()  # what the description could not carry, said once each
    excludes: tuple[tuple[str, str], ...] = ()  # link pairs that never collide (``cad.build123d.exclude``)
    zero: str | None = None  # the mechanism state every joint's zero is at; None for the as-built state

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

    def summary(self, kind: str) -> dict[str, Any]:
        """What the description holds, as an export of ``kind`` (``mjcf``, ``urdf``) says it (``said.robot``):
        its links but the ground (the robot's own), its joints but those it hangs from the ground by, whether
        its base floats, its couplings (``[follower, leader, ratio]``), closures, total mass (kg, None where no
        link has one) and the links with none, named frames, collisions by kind (a decomposed part's hulls are
        ``hull``), exclusions, poses, its zero state and its warnings. JSON's types alone."""
        ground = self.root
        mounts = {joint.name for joint in self.joints if joint.parent == ground.name}
        links = [link for link in self.links if link is not ground or link.visuals or link.collisions
                 or link.inertial is not None]
        joints: dict[str, list[str]] = {}
        for joint in self.joints:
            if joint.name not in mounts:
                joints.setdefault(joint.kind, []).append(joint.name)
        collisions: dict[str, int] = {}
        for link in links:
            for collision in link.collisions:
                kind_of = "hull" if collision.part else collision.geometry.kind
                collisions[kind_of] = collisions.get(kind_of, 0) + 1
        weighed = [link.inertial.mass for link in links if link.inertial is not None]
        return {"kind": kind, "name": self.name, "links": [link.name for link in links], "joints": joints,
                "base": "free" if any(joint.kind == "floating" for joint in self.joints) else "fixed",
                "couplings": [[joint.name, joint.follows[0], float(joint.follows[1])] for joint in self.joints
                              if joint.follows is not None],
                "closures": [closure.name for closure in self.closures],
                "mass": float(sum(weighed)) if weighed else None,
                "massless": [link.name for link in links if link.inertial is None and link.parts],
                "frames": [name for link in links for name in link.frames],
                "collisions": collisions, "excludes": [list(pair) for pair in self.excludes],
                "poses": [pose.name for pose in self.poses], "zero": self.zero, "warnings": list(self.warnings)}

    def controls(self) -> list[Joint]:
        """The joints a person or a controller moves: not fixed, not floating, not following another."""
        return [joint for joint in self.joints if joint.kind not in ("fixed", "floating") and joint.follows is None]

    def check(self) -> None:
        """The tree's invariants, raised by name: one root, every joint between known links, every child
        placed by one joint, meshes the geometry names present, and each closure between two links of the
        tree, named as no joint is."""
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
        for joint in self.joints:
            if joint.kind == "floating" and joint.parent != self.root.name:
                raise DescriptionError(f"joint {joint.name!r} floats, and a link floats from the ground alone, not "
                                       f"from {joint.parent!r}")
        for link in self.links:
            for geometry in [v.geometry for v in link.visuals] + [c.geometry for c in link.collisions]:
                if geometry.kind == "mesh" and geometry.mesh not in self.meshes:
                    raise DescriptionError(f"link {link.name!r} names mesh {geometry.mesh!r}, which there is not")
        for pair in self.excludes:
            for end in pair:
                if end not in known:
                    raise DescriptionError(f"an exclusion names link {end!r}, which there is not")
        joints = {joint.name for joint in self.joints}
        for closure in self.closures:
            for end in (closure.parent, closure.child):
                if end not in known:
                    raise DescriptionError(f"closure {closure.name!r} names link {end!r}, which there is not")
            if closure.parent == closure.child:
                raise DescriptionError(f"closure {closure.name!r} joins link {closure.parent!r} to itself")
            if closure.name in joints:
                raise DescriptionError(f"closure {closure.name!r} is named as a joint is")
            joints.add(closure.name)


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

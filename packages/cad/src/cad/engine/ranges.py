"""A mechanism's joint stops found from its geometry: each joint turned or slid alone until its parts meet.

``sweep(description)`` takes a document described as a robot (``describe``, ``description.py``: links at
the as-built state, every joint at zero) and, for each joint a person moves (``Description.controls``:
not fixed, following no other), moves it alone from zero -- the joints that follow it with it, every
other joint at zero -- one ``step`` at a time each way. Its **stop** each way is the first pose where
what it moves meets what holds it: its child link (with every link fixed to it) against its parent link
(with every link fixed to that), a stop whatever the other joints do, which is what its range declares.
Its **clash** each way, where one comes first, is the first pose where anything it moves (its child's
subtree, and the subtrees its followers move) meets any other link, the other joints as built: a
self-collision of that pose, said beside the stop, never in place of it. A turning joint is swept a full
turn each way (one clear a full turn has no stop); a sliding one as far as the whole document's extent.
A cylindrical or spherical joint, two or three values, is not swept, nor is a joint of a loop
(``Description.closures``), which moves only with the rest of its loop.

**The test is on surfaces**, the way the parts would meet: each part's own surface (``geometry="parts"``,
the default: its mesh, as the viewer draws it), or what it declares a simulator collides it as
(``"collision"``: the primitive fitted to it where it declares one, its hulls where it is decomposed, else
its mesh), with a part declared
``collision(part, "none")`` taking no part either way (a fastener seated in the hole it holds, a servo's
internals), is sampled to points ``0.6 * clearance`` apart; the still side's points mark a grid of
``clearance`` cells; the moving side's points, moved, are looked up in it. So two surfaces within about
``clearance`` count as touching: the margin a part's tolerance takes anyway. Two parts meet where their
pair's count rises ``STOP`` points over its count at zero, at that pose and the next (a graze past a
corner, over it at one pose alone, is no contact); a pair of links the model says never collide
(``Description.excludes``) never meets. The stop reported each way is the last clear pose and the two
parts that met one step past it. Where two parts of one link meet (a part split in two on its cut, a screw
in its hole), that surface is inside the link and is not tested.

**A pair near at zero** is measured, not counted: each pair's gap at zero is the least distance between
its two sides' samples (an exact search of the cells around each, ``_Cells``, out to the grid's reach, ``REACH`` clearances). A pair under
``TOUCHING`` of the clearance apart touches (a horn on its servo, a part on the bearing it turns on): it
keeps its count as it turns about the shared axis, and the count rule holds for it. A pair farther apart
but within the reach is near: a count of its points within the clearance changes with every hundredth of
a millimetre its gap changes by and with how the grid's cells fall, so it would stop wherever the gap
narrows a hair (0.42 to 0.35 mm), and a finer clearance only moves that stop. Its gap is tracked
instead, and it meets where the gap closes to touching, at that pose and the next: under ``TOUCHING`` of the
clearance, the bound a pair touching at zero is under, and under ``CLOSED`` of its own gap at zero (a
pair resting just past that bound meets only once it has closed by half). Each joint's near pairs are reported with their gap at zero and at
each stop (``JointStops.near``), and a stop one of them makes says so (``Contact.near``).

Units are the document's: degrees and millimetres, values around the as-built pose (zero), with the
joint's own values beside (``as_built`` plus them), which is what its range declares. Nothing here
reads or writes a file, and nothing changes the document.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

__all__ = ["CLOSED", "GEOMETRY", "Contact", "JointStops", "Near", "REACH", "STOP", "TOUCHING", "sweep"]

#: Sample points of new contact over a pair's count at zero that make a stop: about 15 mm^2 of surface at
#: the default clearance (a sample per 0.36 mm^2), more than a turn's aliasing on the grid.
STOP = 40
#: Sample spacing, as a share of the clearance.
SPACING = 0.6
#: A pair whose gap at zero is under this share of the clearance touches as built: the count rule holds for it.
TOUCHING = 0.2
#: How far, in clearances, a pair at zero is measured: two points in one grid cell are at most this far apart.
REACH = math.sqrt(3)
#: A pair near at zero meets where its gap is under ``TOUCHING`` of the clearance and under this share of its gap
#: at zero.
CLOSED = 0.5
#: A full turn, in degrees: a turning joint clear this far each way has no stop.
TURN = 360.0
SWEPT = ("revolute", "continuous", "prismatic")
#: What a sweep tests: each colliding part's own surface (``parts``), or what each part declares a simulator
#: collides it as (``collision``: a fitted box, cylinder, ... where it declares one).
GEOMETRY = ("parts", "collision")


@dataclass(frozen=True)
class Contact:
    """Two parts that met: the moving one (on the swept side) and the still one, each by its part's name (an
    anonymous one by its path from its nearest named ancestor, ``shown``) and its link's, and the pose, in the
    joint's unit around zero, where they did. ``near`` is the pair's gap at zero, in mm, where they were near
    then (the module's **A pair near at zero**), and ``gap`` theirs where they met; both None for any other
    pair."""

    moving: str
    moving_link: str
    still: str
    still_link: str
    at: float
    near: float | None = None
    gap: float | None = None


@dataclass(frozen=True)
class Near:
    """A pair near at zero (the module's **A pair near at zero**): the moving part and the still one, as a
    ``Contact`` names them, ``rest`` their gap at zero in mm, and ``lower`` and ``upper`` their gap at each
    stop (the last clear pose); None where that way has no stop or they are over the reach apart there."""

    moving: str
    moving_link: str
    still: str
    still_link: str
    rest: float
    lower: float | None = None
    upper: float | None = None


@dataclass
class JointStops:
    """One joint's stops each way, in its unit (``deg`` or ``mm``) around the as-built pose: ``lower`` and
    ``upper`` the last clear poses before what the joint moves meets what holds it (its child link, and what
    is fixed to it, against its parent link and what is fixed to that: a stop whatever the other joints do),
    None where it is clear all the way (a full turn, or the document's extent for a slide), each with the
    contact one step past it; ``lower_clash`` and ``upper_clash`` a contact of anything it moves with any
    other link first, before that stop, in this pose of the other joints (the as-built one); ``swept`` False
    (and ``why``) for a joint this does not sweep."""

    joint: str
    kind: str
    unit: str
    as_built: float
    lower: float | None = None
    upper: float | None = None
    lower_contact: Contact | None = None
    upper_contact: Contact | None = None
    lower_clash: Contact | None = None
    upper_clash: Contact | None = None
    declared: tuple[float | None, float | None] | None = None  # its range now, around zero
    swept: bool = True
    why: str = ""
    resting: list[tuple[str, str]] = field(default_factory=list)  # part pairs touching at zero (moving, still)
    near: list[Near] = field(default_factory=list)  # part pairs near at zero, with their gaps


#: Sample points past which the sampling is said as it starts whatever ``told`` hears: tens of seconds and gigabytes.
SAMPLED_LONG = 20_000_000
#: Seconds past which a joint's sweep is said as it starts and as it ends (``sweep``'s ``progress``): a fine step or
#: clearance on a vendor STEP's thousands of faces takes minutes a joint.
LONG = 15.0


def sweep(description: Any, *, step: float = 1.0, clearance: float = 1.0, geometry: str = "parts",
          told: Callable[[str], None] | None = None,
          progress: Callable[[str], None] | None = None) -> list[JointStops]:
    """Each controlled joint's stops (see the module docstring): ``step`` degrees for a turning joint and
    millimetres for a sliding one, ``clearance`` millimetres, ``geometry`` what is tested (``GEOMETRY``);
    ``told`` hears a line per joint as it is done. ``progress`` hears, of a joint whose sweep may take more
    than ``LONG`` seconds (its first pose's time times its poses, a full turn each way at most), a line as
    it starts saying about how long, and one as it ends."""
    if geometry not in GEOMETRY:
        raise ValueError(f"geometry {geometry!r} is none of {', '.join(GEOMETRY)}")
    return _Sweep(description, step, clearance, told or (lambda _line: None), geometry,
                  progress or (lambda _line: None)).run()


def _tested(link: Any, geometry: str) -> list[tuple[str, Any]]:
    """A link's tested shapes, each with its part's name as a message names it (``description.shown``: an anonymous
    ``SOLID`` by its path from its nearest named ancestor): ``parts``, the part itself (its visual mesh) for each part
    that collides at all; ``collision``, what each declares (``Link.collisions``), a decomposed part's hulls each
    under the part's name. A link's collisions are its visuals' subsequence, in order, the parts declared ``none``
    left out and a decomposed part's hulls one after another."""
    from cad.engine.description import shown

    found, at = [], 0
    for visual in link.visuals:
        name = shown(visual.path) if getattr(visual, "path", "") else visual.name
        if at < len(link.collisions) and link.collisions[at].of == visual.name:
            if geometry != "collision":
                found.append((name, visual.geometry))
            while at < len(link.collisions) and link.collisions[at].of == visual.name:
                if geometry == "collision":
                    found.append((name, link.collisions[at].geometry))
                at += 1
    return found


# --- geometry ----------------------------------------------------------------------------------


def _box(size: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
    half = np.asarray(size[:3], dtype=float) / 2
    corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=float) * half
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                      [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return corners, faces


def _revolved(profile: list[tuple[float, float]], segments: int = 32) -> tuple[np.ndarray, np.ndarray]:
    """A surface of revolution about Z: ``profile`` (radius, z) points, first and last on the axis or not."""
    angles = np.linspace(0.0, 2 * math.pi, segments, endpoint=False)
    rings = [np.stack([radius * np.cos(angles), radius * np.sin(angles), np.full(segments, z)], axis=1)
             for radius, z in profile]
    vertices = np.vstack(rings)
    faces = []
    for ring in range(len(profile) - 1):
        a, b = ring * segments, (ring + 1) * segments
        for at in range(segments):
            nxt = (at + 1) % segments
            faces += [[a + at, a + nxt, b + nxt], [a + at, b + nxt, b + at]]
    for ring, z in ((0, profile[0]), (len(profile) - 1, profile[-1])):
        if z[0] > 0:  # a flat cap
            centre = len(vertices)
            vertices = np.vstack([vertices, [[0.0, 0.0, z[1]]]])
            start = ring * segments
            faces += [[centre, start + at, start + (at + 1) % segments] for at in range(segments)]
    return vertices, np.asarray(faces)


def _primitive(kind: str, size: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
    """A fitted primitive (``description.Geometry``) as triangles in its own frame, metres."""
    if kind == "box":
        return _box(size)
    if kind == "sphere":
        radius = size[0]
        return _revolved([(radius * math.sin(t), -radius * math.cos(t)) for t in np.linspace(0, math.pi, 17)])
    radius, length = size[0], size[1]
    if kind == "cylinder":
        return _revolved([(radius, -length / 2), (radius, length / 2)])
    # A capsule: the cylinder and a half sphere on each end.
    bottom = [(radius * math.sin(t), -length / 2 - radius * math.cos(t)) for t in np.linspace(0, math.pi / 2, 9)]
    top = [(radius * math.cos(t), length / 2 + radius * math.sin(t)) for t in np.linspace(0, math.pi / 2, 9)]
    return _revolved(bottom + top)


def _area(vertices: np.ndarray, faces: np.ndarray) -> float:
    if not len(faces):
        return 0.0
    a, b, c = (vertices[faces[:, i]] for i in range(3))
    return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())


def _count(number: int) -> str:
    """A count as a person reads it: 8,200, 3.1 million."""
    return f"{number / 1e6:.2g} million" if number >= 1_000_000 else f"{number:,}"


def _samples(vertices: np.ndarray, faces: np.ndarray, spacing: float, seed: int) -> np.ndarray:
    """A surface as points about ``spacing`` apart (its vertices and random points by area), one seed each."""
    if not len(faces):
        return vertices.copy()
    a, b, c = (vertices[faces[:, i]] for i in range(3))
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = float(areas.sum())
    count = int(total / spacing ** 2)
    if count <= 0 or total <= 0:
        return vertices[np.unique(faces)]
    rng = np.random.default_rng(seed)
    picked = rng.choice(len(faces), size=count, p=areas / total)
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    inside = a[picked] + u[:, None] * (b[picked] - a[picked]) + v[:, None] * (c[picked] - a[picked])
    return np.vstack([vertices[np.unique(faces)], inside])


def _outside(points: np.ndarray, owners: np.ndarray, cell: float) -> np.ndarray:
    """Which of a link's surface samples are its outside: not within about a cell of another part of the same
    link. Two parts of one link meet where it holds them together -- a part split in two meets its other half
    on the cut, a screw its hole -- and that surface is inside the link, where no other link reaches."""
    if len(np.unique(owners)) < 2:
        return np.ones(len(points), dtype=bool)
    cells = np.floor((points - points.min(axis=0)) / cell).astype(np.int64) + 1
    shape = cells.max(axis=0) + 2
    keys = (cells[:, 0] * shape[1] + cells[:, 1]) * shape[2] + cells[:, 2]
    pairs = np.unique(np.stack([keys, owners], axis=1), axis=0)
    occupied, first, counts = np.unique(pairs[:, 0], return_index=True, return_counts=True)
    first_owner = pairs[first, 1]
    keep = np.ones(len(points), dtype=bool)
    for offset in ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        near = keys + (offset[0] * shape[1] + offset[1]) * shape[2] + offset[2]
        at = np.clip(np.searchsorted(occupied, near), 0, len(occupied) - 1)
        there = occupied[at] == near
        other = there & ((counts[at] > 1) | (first_owner[at] != owners))
        keep &= ~other
    return keep


# --- the sweep -----------------------------------------------------------------------------------


class _Grid:
    """The still side's surface points as occupied cells, each the part it came from: a coarse dense mask
    first (most moving points are nowhere near), then the sorted cell keys."""

    def __init__(self, points: np.ndarray, owners: np.ndarray, pitch: float) -> None:
        self.pitch = pitch
        self.empty = not len(points)
        if self.empty:
            return
        self.low = points.min(axis=0) - pitch
        cells = np.floor((points - self.low) / pitch).astype(np.int64)
        self.shape = cells.max(axis=0) + 2
        keys = self._key(cells)
        self.keys, first = np.unique(keys, return_index=True)
        self.owners = owners[first]
        cells_total = float(np.prod(self.shape.astype(float)))
        self.factor = max(8, int(math.ceil((cells_total / 16e6) ** (1 / 3))))
        self.coarse_shape = self.shape // self.factor + 1
        self.coarse = np.zeros(tuple(self.coarse_shape), dtype=bool)
        coarse = cells // self.factor
        self.coarse[coarse[:, 0], coarse[:, 1], coarse[:, 2]] = True

    def _key(self, cells: np.ndarray) -> np.ndarray:
        return (cells[:, 0] * self.shape[1] + cells[:, 1]) * self.shape[2] + cells[:, 2]

    def hits(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The indices of ``points`` that fall in an occupied cell, and the still part of each."""
        if self.empty or not len(points):
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        cells = np.floor((points - self.low) / self.pitch).astype(np.int64)
        inside = np.flatnonzero(np.all((cells >= 0) & (cells < self.shape), axis=1))
        cells = cells[inside]
        coarse = cells // self.factor
        near = self.coarse[coarse[:, 0], coarse[:, 1], coarse[:, 2]]
        inside, cells = inside[near], cells[near]
        keys = self._key(cells)
        at = np.searchsorted(self.keys, keys)
        at[at >= len(self.keys)] = 0
        found = self.keys[at] == keys
        return inside[found], self.owners[at[found]]


class _Reach:
    """Where a joint's still side is, seen along its motion: each still point's (distance from the axis, height
    along it) for a turn, its (x, y) across the axis for a slide, as cells of the pitch, each grown by one."""

    def __init__(self, points: np.ndarray, pitch: float, turning: bool) -> None:
        self.pitch, self.turning = pitch, turning
        found = self._cells(points)
        grown = np.vstack([found + (a, b) for a in (-1, 0, 1) for b in (-1, 0, 1)]) if len(found) else found
        self.keys = np.unique(self._key(grown)) if len(grown) else np.zeros(0, dtype=np.int64)

    def _cells(self, points: np.ndarray) -> np.ndarray:
        if self.turning:
            plane = np.stack([np.hypot(points[:, 0], points[:, 1]), points[:, 2]], axis=1)
        else:
            plane = points[:, :2]
        return np.floor(plane / self.pitch).astype(np.int64)

    @staticmethod
    def _key(cells: np.ndarray) -> np.ndarray:
        return cells[:, 0] * 4_000_003 + cells[:, 1]

    def near(self, points: np.ndarray) -> np.ndarray:
        """Which of ``points`` (in the joint's frame at zero) pass a still point's cell as the joint moves."""
        if not len(self.keys) or not len(points):
            return np.zeros(len(points), dtype=bool)
        keys = self._key(self._cells(points))
        at = np.clip(np.searchsorted(self.keys, keys), 0, len(self.keys) - 1)
        return self.keys[at] == keys


class _Sweep:
    def __init__(self, description: Any, step: float, clearance: float, told: Callable[[str], None],
                 geometry_of: str = "parts", progress: Callable[[str], None] = lambda _line: None) -> None:
        self.description = description
        self.progress = progress
        self.clearance = float(clearance)
        self.place = ""  # which joint of how many is swept, as ``progress`` says it
        self.long = False  # whether the joint swept now was said to be long
        self.step = float(step)
        self.pitch = float(clearance) * 1e-3  # metres
        self.told = told
        self.joints = {joint.name: joint for joint in description.joints}
        self.excluded = {frozenset(pair) for pair in (getattr(description, "excludes", None) or ())}
        # Each joint of a loop, and the loop's joints: a loop moves as a whole, so none of them moves alone.
        self.looped = {label: closure.loop for closure in (getattr(description, "closures", None) or ())
                       for label in closure.loop}
        # Every part's surface samples in its link's frame, and which part each point is.
        self.parts: list[tuple[str, str]] = []  # (part, link) by part index
        self.points: dict[str, np.ndarray] = {}
        self.owners: dict[str, np.ndarray] = {}
        spacing = SPACING * self.pitch
        surfaces = []
        for link in description.links:
            for name, geometry in _tested(link, geometry_of):
                if geometry.kind == "mesh":
                    mesh = description.meshes[geometry.mesh]
                    vertices = np.asarray(mesh.positions, dtype=np.float64).reshape(-1, 3) * float(geometry.scale)
                    faces = np.asarray(mesh.triangles, dtype=np.int64).reshape(-1, 3)
                else:
                    vertices, faces = _primitive(geometry.kind, tuple(geometry.size))
                placement = np.asarray(geometry.placement, dtype=float)
                surfaces.append((link.name, name, vertices @ placement[:3, :3].T + placement[:3, 3], faces))
        # Said before it starts: at a fine clearance the sampling alone takes minutes, before any joint is swept.
        estimate = int(sum(_area(vertices, faces) for _link, _name, vertices, faces in surfaces) / spacing ** 2)
        said = (f"sampling {len(surfaces)} part surface{'s' if len(surfaces) != 1 else ''} every "
                f"{spacing * 1000:.2g} mm: about {_count(estimate)} points")
        if estimate > SAMPLED_LONG:
            self.progress(said + " (a coarser --clearance is faster)")
        else:
            self.told(said)
        by_link: dict[str, list[tuple[str, np.ndarray, np.ndarray]]] = {}
        for link_name, name, vertices, faces in surfaces:
            by_link.setdefault(link_name, []).append((name, vertices, faces))
        for link in description.links:
            found, owners = [], []
            for name, vertices, faces in by_link.get(link.name, ()):
                index = len(self.parts)
                self.parts.append((name, link.name))
                sampled = _samples(vertices, faces, spacing, seed=index)
                found.append(sampled)
                owners.append(np.full(len(sampled), index, dtype=np.int64))
            if found:
                points, owners = np.vstack(found), np.concatenate(owners)
                keep = _outside(points, owners, spacing)
                self.points[link.name], self.owners[link.name] = points[keep], owners[keep]

    # --- forward kinematics ---

    def frames(self, values: dict[str, float]) -> dict[str, np.ndarray]:
        """Every link's frame with ``values`` (radians, metres) on the joints named, a follower from its leader
        (``value = ratio * leader + offset``), every other joint at zero."""
        from cad.engine.describe import motion

        found = {self.description.root.name: np.asarray(self.description.root.frame, dtype=float)}
        for joint in self.description.joints:
            count = {"cylindrical": 2, "spherical": 3}.get(joint.kind, 1)
            value = values.get(joint.name, 0.0)
            if joint.follows is not None:
                leader, ratio, offset = joint.follows
                value = ratio * self._value(leader, values) + offset
            value_tuple = (float(value),) + (0.0,) * (count - 1)
            found[joint.child] = found[joint.parent] @ np.asarray(joint.origin, dtype=float) @ motion(joint.kind,
                                                                                                     value_tuple)
        return found

    def _value(self, name: str, values: dict[str, float]) -> float:
        joint = self.joints.get(name)
        if joint is not None and joint.follows is not None:
            leader, ratio, offset = joint.follows
            return ratio * self._value(leader, values) + offset
        return values.get(name, 0.0)

    def moved_by(self, name: str) -> set[str]:
        """The links ``name`` moves: its child's subtree, and the subtrees of the joints that follow it."""
        followers = [joint for joint in self.description.joints
                     if joint.name == name or self._leads(name, joint)]
        found = {joint.child for joint in followers}
        changed = True
        while changed:
            changed = False
            for joint in self.description.joints:
                if joint.parent in found and joint.child not in found:
                    found.add(joint.child)
                    changed = True
        return found

    def rigid(self, name: str) -> set[str]:
        """``name`` and every link fixed to it (by ``fixed`` joints either way): what moves as one with it."""
        found, changed = {name}, True
        while changed:
            changed = False
            for joint in self.description.joints:
                if joint.kind == "fixed" and (joint.parent in found) != (joint.child in found):
                    found |= {joint.parent, joint.child}
                    changed = True
        return found

    def _leads(self, name: str, joint: Any) -> bool:
        seen = set()
        while joint.follows is not None and joint.name not in seen:
            seen.add(joint.name)
            if joint.follows[0] == name:
                return True
            joint = self.joints.get(joint.follows[0])
            if joint is None:
                return False
        return False

    # --- one joint ---

    def run(self) -> list[JointStops]:
        found = []
        controls = list(self.description.controls())
        for at, joint in enumerate(controls, 1):
            started = time.perf_counter()
            self.place, self.long = f"{at} of {len(controls)}", False
            stops = self.joint(joint)
            found.append(stops)
            seconds = time.perf_counter() - started
            self.told(f"{joint.name}: {_said(stops)} ({seconds:.1f} s)")
            if self.long:
                self.progress(f"{joint.name} swept in {_duration(seconds)}")
        return found

    def joint(self, joint: Any) -> JointStops:
        turning = joint.kind != "prismatic"
        unit, scale = ("deg", 180.0 / math.pi) if turning else ("mm", 1000.0)
        as_built = float(joint.as_built[0]) * scale if joint.as_built else 0.0
        declared = None
        if joint.limits:
            low, high = joint.limits[0]
            declared = (None if low is None else low * scale, None if high is None else high * scale)
        stops = JointStops(joint.name, joint.kind, unit, as_built, declared=declared)
        if joint.kind not in SWEPT:
            stops.swept, stops.why = False, f"a {joint.kind} joint has {2 if joint.kind == 'cylindrical' else 3} values"
            return stops
        if joint.name in self.looped:
            stops.swept, stops.why = False, (f"it is in the loop through {', '.join(self.looped[joint.name])}, which "
                                             "moves as a whole: no joint of it moves alone")
            return stops
        moving = self.moved_by(joint.name)
        mover_links = [name for name in self.points if name in moving]
        still_links = [name for name in self.points if name not in moving]
        if not mover_links:
            stops.swept, stops.why = False, "the parts it moves have no collision geometry"
            return stops
        rest = self.frames({})
        still = [self.points[name] @ rest[name][:3, :3].T + rest[name][:3, 3] for name in still_links]
        grid = _Grid(np.vstack(still) if still else np.zeros((0, 3)),
                     np.concatenate([self.owners[name] for name in still_links]) if still else np.zeros(0, np.int64),
                     self.pitch)
        local = [self.points[name] for name in mover_links]
        movers = [self.owners[name] for name in mover_links]
        if not any(other.follows is not None and self._leads(joint.name, other) for other in self.description.joints):
            # Alone, the joint moves its points on circles about its axis (or lines along it): one whose circle
            # passes no still point's never meets one, and is left out of every pose.
            axis = rest[joint.parent] @ np.asarray(joint.origin, dtype=float)
            inverse = np.linalg.inv(axis)
            still_axial = np.vstack(still) @ inverse[:3, :3].T + inverse[:3, 3] if still else np.zeros((0, 3))
            reachable = _Reach(still_axial, self.pitch, turning)
            kept = [reachable.near((points @ rest[name][:3, :3].T + rest[name][:3, 3]) @ inverse[:3, :3].T
                                   + inverse[:3, 3]) for name, points in zip(mover_links, local)]
            local = [points[keep] for points, keep in zip(local, kept)]
            movers = [owners[keep] for owners, keep in zip(movers, kept)]
        movers = np.concatenate(movers)
        link_of = {index: link for index, (_part, link) in enumerate(self.parts)}
        still_points = np.vstack(still) if still else np.zeros((0, 3))
        still_owners = (np.concatenate([self.owners[name] for name in still_links]) if still
                        else np.zeros(0, np.int64))

        def placed_at(value: float) -> np.ndarray:
            frames = self.frames({joint.name: value})
            return np.vstack([points @ frames[name][:3, :3].T + frames[name][:3, 3]
                              for name, points in zip(mover_links, local)])

        def counted(placed: np.ndarray) -> dict[tuple[int, int], int]:
            at, owners = grid.hits(placed)
            if not len(at):
                return {}
            codes = movers[at] * len(self.parts) + owners
            unique, counts = np.unique(codes, return_counts=True)
            return {(int(code) // len(self.parts), int(code) % len(self.parts)): int(count)
                    for code, count in zip(unique, counts)
                    if frozenset((link_of[int(code) // len(self.parts)], link_of[int(code) % len(self.parts)]))
                    not in self.excluded}

        started = time.perf_counter()
        resting_points = placed_at(0.0)
        zero = counted(resting_points)
        rest_gaps = _gaps_at_rest(resting_points, movers, still_points, still_owners, REACH * self.pitch,
                                  lambda pair: frozenset((link_of[pair[0]], link_of[pair[1]])) in self.excluded)
        posed = time.perf_counter() - started
        # The module's **A pair near at zero**: a pair touching keeps the count rule; a near one is measured.
        near = {pair: gap for pair, gap in rest_gaps.items() if gap >= TOUCHING * self.clearance}
        trees = _Trees(still_points, still_owners)
        moved_by_part = {part: np.flatnonzero(movers == part) for part in {pair[0] for pair in near}}

        # A near pair meets under its own bound (the module's **A pair near at zero**): a pose looks only that far, and the gaps a stop
        # reports are measured at the stop's pose alone, out to the reach.
        bound = {pair: min(TOUCHING * self.clearance, CLOSED * rest_gap) * 1e-3 for pair, rest_gap in near.items()}

        def closed(placed: np.ndarray) -> set[tuple[int, int]]:
            """The near pairs closed to touching at a pose."""
            return {pair for pair in near if trees.gap(pair[1], placed[moved_by_part[pair[0]]], bound[pair]) is not None}

        def gaps(placed: np.ndarray) -> dict[tuple[int, int], float | None]:
            """Each near pair's gap at a pose, in mm: None where it is over the reach apart."""
            return {pair: trees.gap(pair[1], placed[moved_by_part[pair[0]]], REACH * self.pitch) for pair in near}

        stops.resting = sorted({(self.parts[a][0], self.parts[b][0]) for a, b in zero if (a, b) not in near})
        step = self.step / scale  # radians or metres
        if turning:
            reach = math.radians(TURN)
        else:
            everything = np.vstack([points @ rest[name][:3, :3].T + rest[name][:3, 3]
                                    for name, points in self.points.items()])
            reach = float(np.linalg.norm(everything.max(axis=0) - everything.min(axis=0))) + step
        count = int(math.ceil(reach / step - 1e-9))
        most = posed * 2 * count  # a full turn (or the document's extent) each way: a stop ends it sooner
        if most > LONG:
            self.long = True
            self.progress(f"sweeping {joint.name} ({self.place}): up to about {_duration(most)} at {self.step:g} "
                          f"{unit} a step and {self.clearance:g} mm clearance (a coarser --step or --clearance is "
                          "faster)")
        else:
            self.told(f"sweeping {joint.name} ({self.place})")
        child_side, parent_side = self.rigid(joint.child) & moving, self.rigid(joint.parent) - moving

        def contact_at(pair: tuple[int, int], value: float, gap: float | None) -> Contact:
            moving_part, still_part = self.parts[pair[0]], self.parts[pair[1]]
            return Contact(moving_part[0], moving_part[1], still_part[0], still_part[1], round(value * scale, 6),
                           near=None if pair not in near else round(near[pair], 4),
                           gap=None if pair not in near or gap is None else round(gap, 4))

        def gap_at(pair: tuple[int, int], value: float) -> float | None:
            return gaps(placed_at(value)).get(pair) if pair in near else None

        at_stop: dict[int, dict[tuple[int, int], float | None]] = {}
        for sign in (-1, 1):
            if sign == 1 and turning and stops.lower_contact is None and stops.lower_clash is None:
                break  # nothing met a full turn one way: nothing meets the other way either
            before: dict[tuple[int, int], int] = {}
            closed_before: set[tuple[int, int]] = set()
            stop: tuple[float, Contact] | None = None
            clash: Contact | None = None
            for k in range(1, count + 1):
                value = sign * k * step
                placed = placed_at(value)
                over = {pair: number - zero.get(pair, 0) for pair, number in counted(placed).items()
                        if pair not in near}
                closed_now = closed(placed) if near else set()
                # A contact is a pair over STOP (a near pair: its gap closed to touching) at a pose and the next: a
                # graze over it at one pose alone is none.
                met = sorted((pair for pair, number in over.items() if number > STOP and before.get(pair, 0) > STOP),
                             key=lambda pair: -before[pair])
                met += sorted(closed_now & closed_before)
                own = [pair for pair in met if link_of[pair[0]] in child_side and link_of[pair[1]] in parent_side]
                if met and clash is None and not own:
                    clash = contact_at(met[0], value - sign * step, gap_at(met[0], value - sign * step))
                if own:
                    stop = (round((value - 2 * sign * step) * scale, 6),
                            contact_at(own[0], value - sign * step, gap_at(own[0], value - sign * step)))
                    at_stop[sign] = gaps(placed_at(value - 2 * sign * step)) if near else {}
                    break
                before, closed_before = over, closed_now
            if sign < 0:
                stops.lower, stops.lower_contact = stop if stop is not None else (None, None)
                stops.lower_clash = clash
            else:
                stops.upper, stops.upper_contact = stop if stop is not None else (None, None)
                stops.upper_clash = clash

        def rounded(gap: float | None) -> float | None:
            return None if gap is None else round(gap, 4)

        stops.near = [Near(self.parts[a][0], self.parts[a][1], self.parts[b][0], self.parts[b][1], round(gap, 4),
                           rounded(at_stop[-1][(a, b)]) if -1 in at_stop else None,
                           rounded(at_stop[1][(a, b)]) if 1 in at_stop else None)
                      for (a, b), gap in sorted(near.items(), key=lambda item: item[1])]
        return stops


def _gaps_at_rest(points: np.ndarray, owners: np.ndarray, still: np.ndarray, still_owners: np.ndarray, reach: float,
                  excluded: Callable[[tuple[int, int]], bool]) -> dict[tuple[int, int], float]:
    """Each (moving part, still part) pair's least distance at zero, in mm, between their samples, for the pairs
    within ``reach`` metres (``_Cells``)."""
    if not len(points) or not len(still):
        return {}
    found = _Cells(still, reach).least_by_pair(points, owners, still_owners)
    return {pair: gap * 1000.0 for pair, gap in found.items() if not excluded(pair)}


#: The 27 cells around a cell, itself among them.
_AROUND = tuple((x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1))


class _Cells:
    """Points hashed into cubic cells of a size: every point within that distance of a query point lies in one of
    the 27 cells around the query's, so the least distance out to it is an exact search of those cells alone (numpy:
    the engine's libraries hold no KD-tree). ``dilated`` files each point in its 27 cells at once, so a query looks
    up its own cell alone: 27 times the memory, for the one part a near pair is tested against at every pose."""

    #: Query points looked up at once: their candidate pairs, some tens a point, held in memory together.
    CHUNK = 20_000

    def __init__(self, points: np.ndarray, size: float, dilated: bool = False) -> None:
        self.size = float(size)
        self.low = points.min(axis=0) - 2 * self.size
        cells = np.floor((points - self.low) / self.size).astype(np.int64)
        self.shape = cells.max(axis=0) + 3
        self.offsets: tuple[tuple[int, int, int], ...] = ((0, 0, 0),) if dilated else _AROUND
        held = np.arange(len(points))
        if dilated:
            cells = np.concatenate([cells + offset for offset in _AROUND])
            held = np.tile(held, len(_AROUND))
        keys = self._key(cells)
        order = np.argsort(keys, kind="stable")
        self.keys, self.order = keys[order], held[order]
        self.points = points

    def _key(self, cells: np.ndarray) -> np.ndarray:
        return (cells[:, 0] * self.shape[1] + cells[:, 1]) * self.shape[2] + cells[:, 2]

    def pairs(self, query: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Each (query index, held index, distance) within the size, the held index into the points as given."""
        found_query, found_held, found_distance = [], [], []
        for first in range(0, len(query), self.CHUNK):
            block = query[first:first + self.CHUNK]
            cells = np.floor((block - self.low) / self.size).astype(np.int64)
            for offset in self.offsets:
                near = cells + offset
                inside = np.flatnonzero(np.all((near >= 0) & (near < self.shape), axis=1))
                if not len(inside):
                    continue
                keys = self._key(near[inside])
                lo, hi = np.searchsorted(self.keys, keys, "left"), np.searchsorted(self.keys, keys, "right")
                counts = hi - lo
                if not counts.any():
                    continue
                asking = np.repeat(inside, counts)
                at = np.repeat(lo - np.cumsum(counts) + counts, counts) + np.arange(int(counts.sum()))
                held = self.order[at]
                distance = np.linalg.norm(block[asking] - self.points[held], axis=1)
                close = distance < self.size
                found_query.append(asking[close] + first)
                found_held.append(held[close])
                found_distance.append(distance[close])
        if not found_query:
            empty = np.zeros(0, dtype=np.int64)
            return empty, empty, np.zeros(0)
        return np.concatenate(found_query), np.concatenate(found_held), np.concatenate(found_distance)

    def least(self, query: np.ndarray) -> float | None:
        """The least distance from ``query`` to the points, in metres; None over the size."""
        _asking, _held, distance = self.pairs(query)
        return float(distance.min()) if len(distance) else None

    def least_by_pair(self, query: np.ndarray, owners: np.ndarray, held_owners: np.ndarray
                      ) -> dict[tuple[int, int], float]:
        """The least distance, in metres, of each (query owner, held owner) pair within the size."""
        asking, held, distance = self.pairs(query)
        if not len(asking):
            return {}
        width = int(held_owners.max()) + 1
        codes = owners[asking].astype(np.int64) * width + held_owners[held]
        order = np.argsort(codes, kind="stable")
        codes, distance = codes[order], distance[order]
        unique, first = np.unique(codes, return_index=True)
        return {(int(code) // width, int(code) % width): float(gap)
                for code, gap in zip(unique, np.minimum.reduceat(distance, first))}


class _Trees:
    """Each still part's samples hashed in cells of each size asked (``_Cells``), and their box, made as a near pair
    first asks."""

    def __init__(self, points: np.ndarray, owners: np.ndarray) -> None:
        self.points, self.owners = points, owners
        self.boxes: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self.cells: dict[tuple[int, float], _Cells] = {}

    def gap(self, part: int, points: np.ndarray, reach: float) -> float | None:
        """The least distance from ``points`` to the still ``part``'s samples, in mm; None over ``reach`` metres. Only
        the points inside the part's box grown by ``reach`` are looked up: a pose's few, of a part beside it."""
        box = self.boxes.get(part)
        if box is None:
            mine = self.points[self.owners == part]
            box = self.boxes[part] = (mine, mine.min(axis=0), mine.max(axis=0))
        mine, low, high = box
        points = points[np.all((points >= low - reach) & (points <= high + reach), axis=1)]
        if not len(points):
            return None
        cells = self.cells.get((part, reach))
        if cells is None:
            cells = self.cells[(part, reach)] = _Cells(mine, reach, dilated=True)
        least = cells.least(points)
        return None if least is None else least * 1000.0


def _duration(seconds: float) -> str:
    """A span as a person reads it: seconds below two minutes, else minutes."""
    return f"{seconds:.0f} s" if seconds < 120 else f"{seconds / 60:.0f} min"


def closing(contact: Any) -> str:
    """A pair near as built that met, said by its gap closing (``Contact.near``): ``, closed to 0.18 from 0.42 mm
    as built``; nothing for any other pair."""
    if contact.near is None:
        return ""
    if contact.gap is None:
        return f", closed from {contact.near:.2f} mm as built"
    return f", closed to {contact.gap:.2f} from {contact.near:.2f} mm as built"


def _said(stops: JointStops) -> str:
    if not stops.swept:
        return f"not swept: {stops.why}"

    def end(value: float | None, contact: Contact | None, clash: Contact | None) -> str:
        said = "clear" if contact is None else \
            f"{value:+g} {stops.unit} ({contact.moving} meets {contact.still} at {contact.at:+g}{closing(contact)})"
        if clash is not None:
            said += f", {clash.moving} meeting {clash.still} at {clash.at:+g} as the others stand"
        return said

    return (f"lower {end(stops.lower, stops.lower_contact, stops.lower_clash)}, "
            f"upper {end(stops.upper, stops.upper_contact, stops.upper_clash)}")

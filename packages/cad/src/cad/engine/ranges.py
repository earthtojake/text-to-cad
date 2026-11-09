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
its mesh), with a part declared ``collision(part, "none")`` taking no part either way (a fastener seated in
the hole it holds, a servo's internals), and two parts declared ``exclude(a, b)`` never meeting each other
(``Description.part_excludes``: those two alone, not the rest of their links). On the collision geometry the
sweep is the simulator's: the link pairs the MJCF never collides (``export.contact.never``: MuJoCo's own
filter of a body and its parent, the pairs touching as built, the pairs declared) never meet, so a joint whose
child is filtered against its parent has no stop there, as MuJoCo has none, and its clashes are what it hits.
Each surface is sampled so
that every point of it is within ``RESOLUTION`` of a sample (``_samples``), the same samples whatever the
clearance. A **gap** is the least distance between two sides' samples: never under the true distance
between the two meshes, and at most ``2 * RESOLUTION`` over it (each side's nearest point is within
``RESOLUTION`` of a sample).

**Where two parts meet** is one rule for every pair, read against the as-built pose, in two halves:

- **Their gap closes:** it is under the pair's bound, ``min(clearance, CLOSED * (gap as built -
  RESOLUTION))``: under the clearance, and under half what it was as built. A pair apart as built meets
  where it comes within the clearance; one near it (a jaw 0.4 mm from its servo's cover) only where its gap
  halves, not where it narrows a hair. A pair whose true gap does not narrow never meets so unless it stood
  under ``RESOLUTION`` apart: its gap now is at least its true gap, which is at least its gap as built less
  ``2 * RESOLUTION``.
- **Their contact grows:** more than ``STOP`` of the moving part's samples (``STOP_AREA`` of surface) come
  within ``RESOLUTION`` of the still part, each one that stood ``2 * RESOLUTION`` or more from it as built.
  This is how a pair touching as built meets (a horn on its servo, a part on the bearing it turns on, a
  carriage on its rail), whose bound is nothing (its gap as built is under ``RESOLUTION``): where more of
  it comes into contact, not where it slides along what it touches. A sample counted truly came nearer:
  its gap now is at least its true gap, and its gap as built at most ``RESOLUTION`` over its true one.

Two parts meet where either holds at a pose and the next (a graze past a corner, at one pose alone, is no
contact). The stop reported each way is the last clear pose and the two parts that met one step past it,
with their gap there (``Contact.gap``) and, for a pair within the clearance as built, that gap too
(``Contact.near``). Where two parts of one link meet (a part split in two on its cut, a screw in its hole),
that surface is inside the link and is not tested.

**A smaller clearance never narrows a range.** The samples, every gap and every count are the same
whatever the clearance (a gap as built is measured over every sample: ``placed_at``), the contact half
does not read the clearance, and a pair's bound only falls with it: what meets at a clearance meets at
every larger one, so each stop at a smaller clearance is at or past the stop at a larger one. A clearance
under ``RESOLUTION`` is refused (``_internal.ranges``): the samples resolve no finer. Each joint's pairs
within the clearance as built are reported with their gap as built and at each stop (``JointStops.near``;
the ones under ``RESOLUTION``, touching as far as the samples tell, are ``JointStops.resting``).

**What a pose costs.** Only the moving samples that may come within the clearance are measured: a joint
alone moves each on a circle or a line, so one whose path passes no still point's that near is left out
(``_Reach``); at each pose the rest are placed by cluster (``_Clusters``), each cluster only where a coarse
mask of the still side says it may be that near (``_Occupied``); each sample left is looked up against
each still part it may be near, only as far as its pair's bound or ``RESOLUTION`` (``_Cells``, at halves
of the clearance).

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

__all__ = ["CLOSED", "GEOMETRY", "RESOLUTION", "Contact", "JointStops", "Near", "sweep", "unknown"]

#: Every point of a tested surface is within this many millimetres of one of its samples, at any clearance: a gap
#: is measured to within twice it, and a clearance under it is refused.
RESOLUTION = 0.3
#: Two parts close where their gap is under this share of their gap as built (less ``RESOLUTION``), as well as
#: under the clearance.
CLOSED = 0.5
#: The surface, in mm^2, of a moving part's samples that come within ``RESOLUTION`` of a still part from
#: ``2 * RESOLUTION`` or more as built where the two meet however near they stood (``STOP`` samples, at one a
#: ``RESOLUTION`` squared): a contact grown, not a corner grazed.
STOP_AREA = 15.0
STOP = int(STOP_AREA / RESOLUTION ** 2)
#: How many times a still part's samples are hashed at half the size again, for samples whose bound is that small.
LEVELS = 4
#: The size, in mm, of the cells a moving link's samples are clustered in, and how many cells of the still side's
#: coarse mask a cluster's reach spans: a pose places only the clusters that mask passes (``_Clusters``).
CLUSTER = 3.0
GROWN = 3
#: A full turn, in degrees: a turning joint clear this far each way has no stop.
TURN = 360.0
SWEPT = ("revolute", "continuous", "prismatic")
#: What a sweep tests: each colliding part's own surface (``parts``), or what each part declares a simulator
#: collides it as (``collision``: a fitted box, cylinder, ... where it declares one).
GEOMETRY = ("parts", "collision")


@dataclass(frozen=True)
class Contact:
    """Two parts that met: the moving one (on the swept side) and the still one, each by its part's name (an
    anonymous one by its path from its nearest named ancestor, ``shown``) and its link's, the pose, in the
    joint's unit around zero, where they did, and ``gap`` their gap there, in mm. ``near`` is their gap as
    built, in mm, where it was within the clearance (the module's **Where two parts meet**); None for any other
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
    """A pair within the clearance as built, apart by ``RESOLUTION`` or more: the moving part and the still one,
    as a ``Contact`` names them, ``rest`` their gap as built in mm, and ``lower`` and ``upper`` their gap at each
    stop (the last clear pose); None where that way has no stop or they are farther apart there than the
    sweep looks."""

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
    resting: list[tuple[str, str]] = field(default_factory=list)  # part pairs under RESOLUTION as built (moving, still)
    near: list[Near] = field(default_factory=list)  # the other part pairs within the clearance as built, with gaps


#: Sample points past which the sampling is said as it starts whatever ``told`` hears: tens of seconds and gigabytes.
SAMPLED_LONG = 20_000_000
#: Seconds past which a joint's sweep is said as it starts and as it ends (``sweep``'s ``progress``): a fine step or
#: clearance on a vendor STEP's thousands of faces takes minutes a joint.
LONG = 15.0


def sweep(description: Any, *, step: float = 1.0, clearance: float = RESOLUTION, geometry: str = "parts",
          joints: tuple[str, ...] = (), told: Callable[[str], None] | None = None,
          progress: Callable[[str], None] | None = None) -> list[JointStops]:
    """Each controlled joint's stops (see the module docstring), or only those ``joints`` names, in the
    description's order: ``step`` degrees for a turning joint and millimetres for a sliding one,
    ``clearance`` millimetres (at least ``RESOLUTION``, and that by default), ``geometry`` what is tested
    (``GEOMETRY``); ``told`` hears a line per joint as it is done. ``progress`` hears, of a joint whose sweep
    may take more than ``LONG`` seconds (its first pose's time times its poses, a full turn each way at most),
    a line as it starts saying about how long, and one as it ends. A name in ``joints`` that is no control
    (``Description.controls``) is refused, naming the controls."""
    if geometry not in GEOMETRY:
        raise ValueError(f"geometry {geometry!r} is none of {', '.join(GEOMETRY)}")
    if not clearance >= RESOLUTION:
        raise ValueError(f"clearance {clearance:g} mm is under the sweep's resolution, {RESOLUTION:g} mm")
    unknown(description, joints)
    return _Sweep(description, step, clearance, told or (lambda _line: None), geometry,
                  progress or (lambda _line: None), tuple(joints)).run()


def unknown(description: Any, joints: tuple[str, ...]) -> None:
    """Refuse a joint name the sweep moves no joint by, naming the ones it does (``Description.controls``)."""
    controls = [joint.name for joint in description.controls()]
    missing = [name for name in joints if name not in controls]
    if missing:
        raise ValueError(f"{', '.join(repr(name) for name in missing)} {'is' if len(missing) == 1 else 'are'} "
                         f"no joint the sweep moves; its joints: {', '.join(controls) or 'none'}")


def _tested(link: Any, geometry: str) -> list[tuple[str, str, Any]]:
    """A link's tested shapes, each with its part's name as a message names it (``description.shown``: an anonymous
    ``SOLID`` by its path from its nearest named ancestor) and its occurrence path (``Visual.path``; its name where it
    has none): ``parts``, the part itself (its visual mesh) for each part that collides at all; ``collision``, what
    each declares (``Link.collisions``), a decomposed part's hulls each under the part's name. A link's collisions
    are its visuals' subsequence, in order, the parts declared ``none`` left out and a decomposed part's hulls one
    after another."""
    from cad.engine.description import shown

    found, at = [], 0
    for visual in link.visuals:
        path = getattr(visual, "path", "") or ""
        name = shown(path) if path else visual.name
        if at < len(link.collisions) and link.collisions[at].of == visual.name:
            if geometry != "collision":
                found.append((name, path or visual.name, visual.geometry))
            while at < len(link.collisions) and link.collisions[at].of == visual.name:
                if geometry == "collision":
                    found.append((name, path or visual.name, link.collisions[at].geometry))
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


def _samples(vertices: np.ndarray, faces: np.ndarray, resolution: float) -> np.ndarray:
    """A surface as points such that every point of it is within ``resolution`` of one: each triangle in rows
    parallel to its longest edge AB, ``across = resolution / sqrt(2)`` apart from AB to its apex C, each row's
    points ``along = resolution * sqrt(2)`` apart at most, both its ends among them.

    The bound: with AB the longest edge, the angles at A and B are acute, so the triangle's cross-section parallel
    to AB only shrinks towards C; a point P of it lies between two rows, and its foot on the row below (at most
    ``across`` away) lies on that row, within ``along / 2`` of one of its points: ``sqrt(across^2 + (along/2)^2)``,
    which is ``resolution``. A triangle smaller than the spacing is its three corners."""
    if not len(faces):
        return vertices.copy()
    along, across = resolution * math.sqrt(2.0), resolution / math.sqrt(2.0)
    corners = vertices[faces]  # (faces, 3, 3)
    edges = np.stack([np.linalg.norm(corners[:, (at + 1) % 3] - corners[:, at], axis=1) for at in range(3)], axis=1)
    longest = edges.argmax(axis=1)
    index = np.arange(len(faces))
    a, b, c = corners[index, longest], corners[index, (longest + 1) % 3], corners[index, (longest + 2) % 3]
    length = edges[index, longest]
    doubled = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    height = np.divide(doubled, length, out=np.zeros_like(length), where=length > 0)
    rows = np.maximum(1, np.ceil(height / across - 1e-9)).astype(np.int64)  # intervals from AB to C
    triangle = np.repeat(index, rows + 1)
    row = np.arange(len(triangle)) - np.repeat(np.cumsum(rows + 1) - (rows + 1), rows + 1)
    share = row / rows[triangle]  # 0 on AB, 1 at C
    spans = np.maximum(1, np.ceil(length[triangle] * (1 - share) / along - 1e-9)).astype(np.int64)
    spans[row == rows[triangle]] = 0  # the apex: one point
    point_row = np.repeat(np.arange(len(triangle)), spans + 1)
    on_row = (np.arange(len(point_row)) - np.repeat(np.cumsum(spans + 1) - (spans + 1), spans + 1)) \
        / np.maximum(spans[point_row], 1)
    at, up = triangle[point_row], share[point_row][:, None]
    start, end = a[at] + up * (c[at] - a[at]), b[at] + up * (c[at] - b[at])
    return start + on_row[:, None] * (end - start)


def _outside(points: np.ndarray, owners: np.ndarray, cell: float) -> np.ndarray:
    """Which of a link's surface samples are its outside: not within about a cell of another part of the same
    link. Two parts of one link meet where it holds them together -- a part split in two meets its other half
    on the cut, a screw its hole -- and that surface is inside the link, where no other link reaches."""
    if len(np.unique(owners)) < 2:
        return np.ones(len(points), dtype=bool)
    cells = np.floor((points - points.min(axis=0)) / cell).astype(np.int64) + 1
    shape = cells.max(axis=0) + 2
    keys = (cells[:, 0] * shape[1] + cells[:, 1]) * shape[2] + cells[:, 2]
    span = int(owners.max()) + 1
    pairs = np.unique(keys * span + owners)  # each (cell, part) once, by cell
    occupied, first, counts = np.unique(pairs // span, return_index=True, return_counts=True)
    first_owner = pairs[first] % span
    keep = np.ones(len(points), dtype=bool)
    for offset in ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        near = keys + (offset[0] * shape[1] + offset[1]) * shape[2] + offset[2]
        at = np.clip(np.searchsorted(occupied, near), 0, len(occupied) - 1)
        there = occupied[at] == near
        other = there & ((counts[at] > 1) | (first_owner[at] != owners))
        keep &= ~other
    return keep


# --- the sweep -----------------------------------------------------------------------------------


class _Occupied:
    """Where the still side is, as a mask of cubic cells at least ``size`` across, each occupied cell grown by
    ``grown`` cells each way and marked with the still parts in it (a bit per part, ``bit``; parts share bits past
    the mask's width): a point within ``grown * size`` of a still point lies in a cell the mask marks with that
    point's part (two points that near are at most ``grown`` cells apart along each axis), so the rest of a pose's
    points are passed over at a lookup each."""

    #: Cells the mask may hold: past it the cells are made coarser, never finer than ``size``.
    BUDGET = 8_000_000

    def __init__(self, points: np.ndarray, owners: np.ndarray, size: float, grown: int = 1) -> None:
        self.empty = not len(points)
        parts = np.unique(owners)
        width = next(bits for bits in (8, 16, 32, 64) if bits >= min(64, len(parts)))
        self.dtype = {8: np.uint8, 16: np.uint16, 32: np.uint32, 64: np.uint64}[width]
        self.bits = {int(part): self.dtype(1 << (at % width)) for at, part in enumerate(parts.tolist())}
        if self.empty:
            return
        extent = points.max(axis=0) - points.min(axis=0)
        self.cell = float(size)
        cells = float(np.prod(extent / self.cell + 2 * grown + 1))
        if cells > self.BUDGET:
            self.cell *= (cells / self.BUDGET) ** (1 / 3)
        self.low = points.min(axis=0) - grown * self.cell
        at = np.floor((points - self.low) / self.cell).astype(np.int64)
        self.shape = at.max(axis=0) + grown + 1
        mask = np.zeros(tuple(int(n) for n in self.shape), dtype=self.dtype)
        flat = mask.reshape(-1)
        keys = (at[:, 0] * self.shape[1] + at[:, 1]) * self.shape[2] + at[:, 2]
        span = int(owners.max()) + 1
        marked = np.unique(keys * span + owners)  # each (cell, part) once
        cell_of, part_of = marked // span, marked % span
        for part in parts.tolist():
            flat[cell_of[part_of == part]] |= self.bits[int(part)]
        for axis in range(3):  # grown by ``grown`` cells each way, an axis at a time
            for _time in range(grown):
                widened = mask.copy()
                ahead = [slice(None)] * 3
                behind = [slice(None)] * 3
                ahead[axis], behind[axis] = slice(1, None), slice(None, -1)
                widened[tuple(ahead)] |= mask[tuple(behind)]
                widened[tuple(behind)] |= mask[tuple(ahead)]
                mask = widened
        self.mask = mask

    def bit(self, part: int) -> Any:
        """The bit that marks ``part``'s cells (no bit, 0, for a part not on the still side)."""
        return self.bits.get(part, self.dtype(0))

    def near(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The indices of ``points`` that may be within the size of a still point, and the parts' bits there."""
        if self.empty or not len(points):
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=self.dtype)
        at = np.floor((points - self.low) / self.cell).astype(np.int64)
        inside = np.flatnonzero(np.all((at >= 0) & (at < self.shape), axis=1))
        at = at[inside]
        bits = self.mask[at[:, 0], at[:, 1], at[:, 2]]
        some = bits != 0
        return inside[some], bits[some]


class _Clusters:
    """A joint's moving samples clustered by link in cubic cells of their link's frame, each cluster's centre and the
    radius every cluster lies within: at a pose, a cluster whose centre is over ``radius + clearance`` from every
    still point holds no sample within the clearance of one, so only the clusters a coarse mask passes are placed."""

    def __init__(self, local: list[np.ndarray], size: float) -> None:
        keys, centres, links = [], [], []
        self.radius = 0.0  # the farthest any sample lies from its cluster's centre
        for link, points in enumerate(local):
            if not len(points):
                continue
            cells = np.floor(points / size).astype(np.int64)
            cells -= cells.min(axis=0)
            span = cells.max(axis=0) + 1
            flat = (cells[:, 0] * span[1] + cells[:, 1]) * span[2] + cells[:, 2]
            unique, inverse = np.unique(flat, return_inverse=True)
            keys.append(inverse.reshape(-1) + sum(len(found) for found in centres))
            sums = np.zeros((len(unique), 3))
            np.add.at(sums, inverse.reshape(-1), points)
            mean = sums / np.bincount(inverse.reshape(-1))[:, None]  # each cluster's mean
            self.radius = max(self.radius, float(np.linalg.norm(points - mean[inverse.reshape(-1)], axis=1).max()))
            centres.append(mean)
            links.append(np.full(len(unique), link))
        everything = np.concatenate(keys) if keys else np.zeros(0, dtype=np.int64)
        self.order = np.argsort(everything, kind="stable")  # samples, by cluster
        counts = np.bincount(everything, minlength=sum(len(found) for found in centres))
        self.start = np.cumsum(counts) - counts
        self.counts = counts
        self.centres = np.vstack(centres) if centres else np.zeros((0, 3))
        self.links = np.concatenate(links) if links else np.zeros(0, dtype=np.int64)
        self.points = np.vstack(local) if local else np.zeros((0, 3))
        # The clusters are each link's in turn, so a link's clusters, and their samples by cluster, run together.
        self.link_clusters = np.searchsorted(self.links, np.arange(len(local) + 1))
        self.sorted_points = self.points[self.order]

    def placed(self, frames: list[np.ndarray], coarse: "_Occupied") -> tuple[np.ndarray, np.ndarray]:
        """The samples of the clusters the coarse mask passes at a pose (each link at ``frames``): their indices
        among the joint's moving samples, and where they are."""
        if not len(self.centres):
            return np.zeros(0, dtype=np.int64), np.zeros((0, 3))
        centres = np.empty_like(self.centres)
        bounds = self.link_clusters
        for link, frame in enumerate(frames):
            mine = slice(bounds[link], bounds[link + 1])
            centres[mine] = self.centres[mine] @ frame[:3, :3].T + frame[:3, 3]
        near, _bits = coarse.near(centres)
        if not len(near):
            return np.zeros(0, dtype=np.int64), np.zeros((0, 3))
        counts = self.counts[near]
        at = np.repeat(self.start[near] - np.cumsum(counts) + counts, counts) + np.arange(int(counts.sum()))
        placed = np.empty((len(at), 3))
        # ``near`` is sorted, so its samples are each link's in turn: placed a link at a time.
        ends = np.searchsorted(near, bounds)
        upto = np.concatenate([[0], np.cumsum(counts)])
        for link, frame in enumerate(frames):
            mine = slice(int(upto[ends[link]]), int(upto[ends[link + 1]]))
            placed[mine] = self.sorted_points[at[mine]] @ frame[:3, :3].T + frame[:3, 3]
        return self.order[at], placed


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
        """Which of ``points`` (in the joint's frame at zero) pass within the pitch of a still point as the joint
        moves: its circle (or line) and the still point's are that near in the plane, so the two can be."""
        if not len(self.keys) or not len(points):
            return np.zeros(len(points), dtype=bool)
        keys = self._key(self._cells(points))
        at = np.clip(np.searchsorted(self.keys, keys), 0, len(self.keys) - 1)
        return self.keys[at] == keys


class _Sweep:
    def __init__(self, description: Any, step: float, clearance: float, told: Callable[[str], None],
                 geometry_of: str = "parts", progress: Callable[[str], None] = lambda _line: None,
                 only: tuple[str, ...] = ()) -> None:
        self.description = description
        self.only = only
        self.progress = progress
        self.clearance = float(clearance)
        self.place = ""  # which joint of how many is swept, as ``progress`` says it
        self.long = False  # whether the joint swept now was said to be long
        self.step = float(step)
        self.pitch = float(clearance) * 1e-3  # metres
        self.resolution = RESOLUTION * 1e-3  # metres
        self.told = told
        self.joints = {joint.name: joint for joint in description.joints}
        # Each joint of a loop, and the loop's joints: a loop moves as a whole, so none of them moves alone.
        self.looped = {label: closure.loop for closure in (getattr(description, "closures", None) or ())
                       for label in closure.loop}
        # Every part's surface samples in its link's frame, and which part each point is.
        self.parts: list[tuple[str, str]] = []  # (part, link) by part index
        paths: list[str] = []
        self.points: dict[str, np.ndarray] = {}
        self.owners: dict[str, np.ndarray] = {}
        surfaces = []
        for link in description.links:
            for name, path, geometry in _tested(link, geometry_of):
                if geometry.kind == "mesh":
                    mesh = description.meshes[geometry.mesh]
                    vertices = np.asarray(mesh.positions, dtype=np.float64).reshape(-1, 3) * float(geometry.scale)
                    faces = np.asarray(mesh.triangles, dtype=np.int64).reshape(-1, 3)
                else:
                    vertices, faces = _primitive(geometry.kind, tuple(geometry.size))
                placement = np.asarray(geometry.placement, dtype=float)
                surfaces.append((link.name, name, path, vertices @ placement[:3, :3].T + placement[:3, 3], faces))
        # Said before it starts: on a vendor STEP the sampling alone takes seconds, before any joint is swept.
        estimate = int(sum(_area(vertices, faces) for *_named, vertices, faces in surfaces)
                       / self.resolution ** 2)
        said = (f"sampling {len(surfaces)} part surface{'s' if len(surfaces) != 1 else ''} to within "
                f"{RESOLUTION:g} mm: about {_count(estimate)} points")
        if estimate > SAMPLED_LONG:
            self.progress(said)
        else:
            self.told(said)
        by_link: dict[str, list[tuple[str, str, np.ndarray, np.ndarray]]] = {}
        for link_name, name, path, vertices, faces in surfaces:
            by_link.setdefault(link_name, []).append((name, path, vertices, faces))
        for link in description.links:
            found, owners = [], []
            for name, path, vertices, faces in by_link.get(link.name, ()):
                index = len(self.parts)
                self.parts.append((name, link.name))
                paths.append(path)
                sampled = _samples(vertices, faces, self.resolution)
                found.append(sampled)
                owners.append(np.full(len(sampled), index, dtype=np.int64))
            if found:
                points, owners = np.vstack(found), np.concatenate(owners)
                keep = _outside(points, owners, self.resolution * math.sqrt(2.0))
                self.points[link.name], self.owners[link.name] = points[keep], owners[keep]
        self.hashed: dict[tuple[int, float], _Cells] = {}  # each part's samples as built, by cell size (``_hashed``)
        self.as_built: dict[int, np.ndarray] | None = None
        # The part pairs set aside (``exclude(a, b)``), by part index: a part's hulls are each that part.
        self.excluded = np.zeros((len(self.parts), len(self.parts)), dtype=bool)
        by_path: dict[str, list[int]] = {}
        for index, path in enumerate(paths):
            by_path.setdefault(path, []).append(index)
        for first, second in getattr(description, "part_excludes", None) or ():
            for a in by_path.get(first, ()):
                for b in by_path.get(second, ()):
                    self.excluded[a, b] = self.excluded[b, a] = True
        if geometry_of == "collision":
            # The simulator's own stops: the link pairs the MJCF never collides set aside whole (``never``).
            from cad.engine.export.contact import never

            by_link: dict[str, list[int]] = {}
            for index, (_part, link_name) in enumerate(self.parts):
                by_link.setdefault(link_name, []).append(index)
            for pair in never(description):
                first, second = sorted(pair)
                rows, columns = by_link.get(first, []), by_link.get(second, [])
                if rows and columns:
                    self.excluded[np.ix_(rows, columns)] = True
                    self.excluded[np.ix_(columns, rows)] = True

    def _hashed(self, part: int, size: float) -> _Cells:
        """A part's samples where it stands as built, hashed in cells of ``size`` metres: the same for every joint
        that holds the part still (every joint's sweep starts from the as-built frames), made once."""
        found = self.hashed.get((part, size))
        if found is None:
            if self.as_built is None:
                frames = self.frames({})
                self.as_built = {}
                for link, points in self.points.items():
                    placed = points @ frames[link][:3, :3].T + frames[link][:3, 3]
                    owners = self.owners[link]
                    for index in np.unique(owners):
                        self.as_built[int(index)] = placed[owners == index]
            found = self.hashed[(part, size)] = _Cells(self.as_built[part], size)
        return found

    def _pair_least(self, query: np.ndarray, query_parts: np.ndarray, still: np.ndarray, owners: np.ndarray,
                    size: float, width: int) -> tuple[np.ndarray, np.ndarray]:
        """Each (query part, still part) pair's least distance under ``size`` metres, the still side ``still`` (its
        samples' ``owners``) at its as-built place: their codes (``moving * width + still``), sorted, and the
        distances. Each query point is looked up only against the parts a mask says may be that near, first within
        ``RESOLUTION`` and then, for a pair not settled yet (a pair's least is settled once any of its points is
        that near), twice as far, out to ``size``: exact, at a fraction of the distances."""
        empty = np.zeros(0, dtype=np.int64)
        if not len(still) or not len(query):
            return empty, np.zeros(0)
        mask = self._mask(still, owners, size)
        nearby, bits = mask.near(query)
        codes, distances = [], []
        for part in np.unique(owners).tolist():
            asking = nearby[(bits & mask.bit(part)) != 0]
            reach = self.resolution
            while len(asking):
                asked, _held, apart = self._hashed(part, reach).pairs(query[asking])
                if len(asked):
                    codes.append(query_parts[asking[asked]] * width + part)
                    distances.append(apart)
                if reach >= size:
                    break
                # A pair with a point this near is settled: its least is under any farther one's.
                asking = asking[~np.isin(query_parts[asking], query_parts[asking[asked]])]
                reach = min(size, 2 * reach)
        if not codes:
            return empty, np.zeros(0)
        return _least(np.concatenate(codes), np.concatenate(distances))

    def _near_parts(self, query: np.ndarray, still: np.ndarray, owners: np.ndarray, size: float
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Each (query index, still part, distance) under ``size``, the still side as ``_pair_least`` has it."""
        empty = np.zeros(0, dtype=np.int64)
        if not len(still) or not len(query):
            return empty, empty, np.zeros(0)
        mask = self._mask(still, owners, size)
        nearby, bits = mask.near(query)
        found_query, found_part, found_distance = [], [], []
        for part in np.unique(owners).tolist():
            asking = nearby[(bits & mask.bit(part)) != 0]
            if not len(asking):
                continue
            asked, _held, apart = self._hashed(part, size).pairs(query[asking])
            found_query.append(asking[asked])
            found_part.append(np.full(len(asked), part, dtype=np.int64))
            found_distance.append(apart)
        if not found_query:
            return empty, empty, np.zeros(0)
        return np.concatenate(found_query), np.concatenate(found_part), np.concatenate(found_distance)

    def _mask(self, still: np.ndarray, owners: np.ndarray, size: float) -> _Occupied:
        """The still side's mask at ``size``, made once a joint (``masks``)."""
        found = self.masks.get(size)
        if found is None:
            found = self.masks[size] = _Occupied(still, owners, size)
        return found

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
        controls = [joint for joint in self.description.controls() if not self.only or joint.name in self.only]
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
        self.masks: dict[float, _Occupied] = {}  # the still side's masks at a size, this joint's (``_pair_least``)
        rest = self.frames({})
        still = [self.points[name] @ rest[name][:3, :3].T + rest[name][:3, 3] for name in still_links]
        still_points = np.vstack(still) if still else np.zeros((0, 3))
        still_owners = (np.concatenate([self.owners[name] for name in still_links]) if still
                        else np.zeros(0, np.int64))
        local = [self.points[name] for name in mover_links]
        movers = [self.owners[name] for name in mover_links]
        clearance = self.pitch
        # Every moving sample, for what is measured as built and at a stop: a pair's gap is its least over all of
        # them, whatever the clearance (the module's **A smaller clearance never narrows a range**).
        whole = [points for points in local]
        whole_movers = np.concatenate(movers)
        kept_index = np.arange(len(whole_movers))  # each sample a pose places, by its index among ``whole``
        if not any(other.follows is not None and self._leads(joint.name, other) for other in self.description.joints):
            # Alone, the joint moves its points on circles about its axis (or lines along it): one whose circle
            # passes no still point's within the clearance never comes within it, and is left out of every pose.
            axis = rest[joint.parent] @ np.asarray(joint.origin, dtype=float)
            inverse = np.linalg.inv(axis)
            still_axial = still_points @ inverse[:3, :3].T + inverse[:3, 3]
            reachable = _Reach(still_axial, clearance, turning)
            kept = [reachable.near((points @ rest[name][:3, :3].T + rest[name][:3, 3]) @ inverse[:3, :3].T
                                   + inverse[:3, 3]) for name, points in zip(mover_links, local)]
            local = [points[keep] for points, keep in zip(local, kept)]
            movers = [owners[keep] for owners, keep in zip(movers, kept)]
            kept_index = kept_index[np.concatenate(kept)]
        movers = np.concatenate(movers)
        width = len(self.parts)
        excluded = self.excluded

        def placed_at(value: float) -> np.ndarray:
            """Every moving sample (``whole``) at a pose."""
            frames = self.frames({joint.name: value})
            return np.vstack([points @ frames[name][:3, :3].T + frames[name][:3, 3]
                              for name, points in zip(mover_links, whole)])

        # Each sample's gap as built to each still part, out to where it bounds its pair's closing: past
        # ``clearance / CLOSED + RESOLUTION`` the bound is the clearance.
        looked = clearance / CLOSED + self.resolution
        resting_points = placed_at(0.0)
        pair_codes, pair_rest = self._pair_least(resting_points, whole_movers, still_points, still_owners, looked,
                                                 width)
        # Each sample within ``2 * RESOLUTION`` of a still part as built, by ``sample * width + part``: it counts
        # towards no contact of that part's (the module's **Their contact grows**).
        asked, held_part, _apart = self._near_parts(resting_points, still_points, still_owners, 2 * self.resolution)
        standing = np.unique(asked * width + held_part)
        rest_gaps = {(int(code) // width, int(code) % width): float(gap) * 1000.0
                     for code, gap in zip(pair_codes, pair_rest)
                     if not excluded[int(code) // width, int(code) % width]}
        # Each pair's bound (the clearance where it was over ``looked`` apart as built): the module's **Where two
        # parts meet**.
        bound = np.full((width, width), clearance)
        bound[pair_codes // width, pair_codes % width] = np.minimum(clearance, CLOSED * (pair_rest - self.resolution))
        close = {pair: gap for pair, gap in rest_gaps.items() if gap < self.clearance}  # within the clearance as built
        occupied = _Occupied(still_points, still_owners, clearance)
        # Each still part's samples, hashed at the clearance, at halves of it and at ``RESOLUTION`` (``_hashed``):
        # a sample is looked up against a part only where it may close on it, and only as far as its bound.
        of_part = [int(part) for part in np.unique(still_owners)]

        sizes = np.asarray(sorted({clearance / 2 ** level for level in range(LEVELS + 1)} | {self.resolution}))
        sizes = sizes[sizes >= self.resolution]
        child_side, parent_side = self.rigid(joint.child) & moving, self.rigid(joint.parent) - moving
        own_movers = np.array([link in child_side for _part, link in self.parts], dtype=bool)

        clusters = _Clusters(local, CLUSTER * 1e-3)
        coarse = _Occupied(still_points, still_owners, (clusters.radius + clearance) / GROWN, grown=GROWN)

        def met_at(value: float, own: bool = False) -> dict[tuple[int, int], float]:
            """The part pairs met at a pose, each with its gap there in mm: a sample of the moving part closes on the
            still one (the module's **Where two parts meet**); ``own``, only the child's side's on the parent's
            (once a clash is found, the stop is all a sweep looks for). Only the clusters that may come within the
            clearance of a still point are placed (``_Clusters``)."""
            frames = self.frames({joint.name: value})
            moved = [frames[name] for name in mover_links]
            indices, placed = clusters.placed(moved, coarse)
            local_at, bits = occupied.near(placed)
            candidates, placed = indices[local_at], placed[local_at]
            if own:
                keep = own_movers[movers[candidates]]
                candidates, bits, placed = candidates[keep], bits[keep], placed[keep]
            if not len(candidates):
                return {}
            moving_part = movers[candidates]
            found: dict[tuple[int, int], float] = {}
            for part in of_part:
                if own and self.parts[part][1] not in parent_side:
                    continue
                asking = (bits & occupied.bit(part)) != 0
                asking &= ~excluded[moving_part, part]
                if not asking.any():
                    continue
                sample, where, of = candidates[asking], placed[asking], moving_part[asking]
                # Looked up as far as its pair's bound, or ``RESOLUTION`` where it may count towards a contact (it
                # stood farther from the part as built), whichever is farther; not at all where neither can be.
                code = kept_index[sample] * width + part
                stood = np.zeros(len(code), dtype=bool)
                if len(standing):
                    at = np.clip(np.searchsorted(standing, code), 0, len(standing) - 1)
                    stood = standing[at] == code
                reach = np.where(stood, bound[of, part], np.maximum(bound[of, part], self.resolution))
                looking = reach > 0
                if not looking.any():
                    continue
                sample, where, of, reach, stood = (sample[looking], where[looking], of[looking], reach[looking],
                                                   stood[looking])
                levels = np.searchsorted(sizes, reach * (1 - 1e-12))  # the smallest size at or over each reach
                asked_parts, apart_parts = [], []
                for level in np.unique(levels):
                    at_level = np.flatnonzero(levels == level)
                    asked, _held, apart = self._hashed(part, float(sizes[level])).pairs(where[at_level])
                    asked_parts.append(at_level[asked])
                    apart_parts.append(apart)
                asked, apart = np.concatenate(asked_parts), np.concatenate(apart_parts)
                if not len(asked):
                    continue
                each, least = _least(asked, apart)  # each sample's gap to the part
                of_each = of[each]
                closes = least < bound[of_each, part]
                touches = np.bincount(of_each[(least < self.resolution) & ~stood[each]], minlength=width)
                grown = np.flatnonzero(touches > STOP)
                met = set(np.unique(of_each[closes]).tolist()) | set(grown.tolist())
                if not met:
                    continue
                pairs, gaps = _least(of_each, least)
                for moving_index, gap in zip(pairs.tolist(), gaps.tolist()):
                    if moving_index in met:
                        found[(moving_index, part)] = gap * 1000.0
            return found

        def gaps_at(placed: np.ndarray, pairs: list[tuple[int, int]]) -> dict[tuple[int, int], float | None]:
            """Each of ``pairs``' gap at a pose, in mm: None where it is over ``looked`` apart."""
            if not pairs:
                return {}
            wanted = np.flatnonzero(np.isin(whole_movers, [pair[0] for pair in pairs]))
            codes, least = self._pair_least(placed[wanted], whole_movers[wanted], still_points, still_owners, looked,
                                            width)
            found = {(int(code) // width, int(code) % width): float(gap) * 1000.0 for code, gap in zip(codes, least)}
            return {pair: found.get(pair) for pair in pairs}

        stops.resting = sorted({(self.parts[a][0], self.parts[b][0]) for (a, b), gap in close.items()
                                if gap < RESOLUTION})
        near = sorted(((pair, gap) for pair, gap in close.items() if gap >= RESOLUTION), key=lambda item: item[1])
        step = self.step / scale  # radians or metres
        if turning:
            reach = math.radians(TURN)
        else:
            everything = np.vstack([points @ rest[name][:3, :3].T + rest[name][:3, 3]
                                    for name, points in self.points.items()])
            reach = float(np.linalg.norm(everything.max(axis=0) - everything.min(axis=0))) + step
        count = int(math.ceil(reach / step - 1e-9))
        timed = time.perf_counter()
        met_at(step)
        posed = time.perf_counter() - timed
        most = posed * 2 * count  # a full turn (or the document's extent) each way: a stop ends it sooner
        if most > LONG:
            self.long = True
            self.progress(f"sweeping {joint.name} ({self.place}): up to about {_duration(most)} at {self.step:g} "
                          f"{unit} a step and {self.clearance:g} mm clearance (a coarser --step is faster)")
        else:
            self.told(f"sweeping {joint.name} ({self.place})")

        def contact_at(pair: tuple[int, int], value: float, gap: float) -> Contact:
            moving_part, still_part = self.parts[pair[0]], self.parts[pair[1]]
            rested = close.get(pair)
            return Contact(moving_part[0], moving_part[1], still_part[0], still_part[1], round(value * scale, 6),
                           near=None if rested is None else round(rested, 4), gap=round(gap, 4))

        at_stop: dict[int, dict[tuple[int, int], float | None]] = {}
        for sign in (-1, 1):
            if sign == 1 and turning and stops.lower_contact is None and stops.lower_clash is None:
                break  # nothing met a full turn one way: nothing meets the other way either
            before: dict[tuple[int, int], float] = {}
            stop: tuple[float, Contact] | None = None
            clash: Contact | None = None
            for k in range(1, count + 1):
                value = sign * k * step
                now = met_at(value, own=clash is not None)
                # A contact is a pair met at a pose and the next: a graze at one pose alone is none.
                met = sorted((pair for pair in now if pair in before), key=lambda pair: (before[pair], pair))
                own = [pair for pair in met if self.parts[pair[0]][1] in child_side
                       and self.parts[pair[1]][1] in parent_side]
                if met and clash is None and not own:
                    clash = contact_at(met[0], value - sign * step, before[met[0]])
                if own:
                    stop = (round((value - 2 * sign * step) * scale, 6),
                            contact_at(own[0], value - sign * step, before[own[0]]))
                    at_stop[sign] = gaps_at(placed_at(value - 2 * sign * step), [pair for pair, _gap in near])
                    break
                before = now
            if sign < 0:
                stops.lower, stops.lower_contact = stop if stop is not None else (None, None)
                stops.lower_clash = clash
            else:
                stops.upper, stops.upper_contact = stop if stop is not None else (None, None)
                stops.upper_clash = clash

        def rounded(gap: float | None) -> float | None:
            return None if gap is None else round(gap, 4)

        stops.near = [Near(self.parts[a][0], self.parts[a][1], self.parts[b][0], self.parts[b][1], round(gap, 4),
                           rounded(at_stop[-1].get((a, b))) if -1 in at_stop else None,
                           rounded(at_stop[1].get((a, b))) if 1 in at_stop else None)
                      for (a, b), gap in near]
        return stops


def _least(codes: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The distinct ``codes``, sorted, and the least of ``values`` for each."""
    if not len(codes):
        return np.zeros(0, dtype=np.int64), np.zeros(0)
    order = np.argsort(codes, kind="stable")
    codes, values = codes[order], values[order]
    unique, first = np.unique(codes, return_index=True)
    return unique, np.minimum.reduceat(values, first)


#: The 27 cells around a cell, itself among them.
_AROUND = tuple((x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1))


class _Cells:
    """Points hashed into cubic cells of a size: every point within that distance of a query point lies in one of
    the 27 cells around the query's, so the points within it are an exact search of those cells alone (numpy: the
    engine's libraries hold no KD-tree)."""

    #: Query points looked up at once: their candidate pairs, some tens a point, held in memory together.
    CHUNK = 20_000

    def __init__(self, points: np.ndarray, size: float) -> None:
        self.size = float(size)
        self.low = points.min(axis=0) - 2 * self.size
        cells = np.floor((points - self.low) / self.size).astype(np.int64)
        self.shape = cells.max(axis=0) + 3
        keys = self._key(cells)
        self.order = np.argsort(keys, kind="stable")
        self.keys = keys[self.order]
        self.points = points
        # Every cell with a point in the 27 around it, so a query far from every point is passed over at one lookup.
        occupied = np.unique(self.keys)
        steps = np.array([self._key(np.array([offset]))[0] - self._key(np.zeros((1, 3), dtype=np.int64))[0]
                          for offset in _AROUND])
        self.around = np.unique((occupied[:, None] + steps[None, :]).reshape(-1))

    def _key(self, cells: np.ndarray) -> np.ndarray:
        return (cells[:, 0] * self.shape[1] + cells[:, 1]) * self.shape[2] + cells[:, 2]

    def pairs(self, query: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Each (query index, held index, distance) under the size, the held index into the points as given."""
        found_query, found_held, found_distance = [], [], []
        of_query = np.floor((query - self.low) / self.size).astype(np.int64)
        inside = np.all((of_query >= 1) & (of_query < self.shape - 1), axis=1)
        keys = self._key(of_query)
        at = np.clip(np.searchsorted(self.around, keys), 0, len(self.around) - 1)
        kept = np.flatnonzero(inside & (self.around[at] == keys))
        for first in range(0, len(kept), self.CHUNK):
            chosen = kept[first:first + self.CHUNK]
            block, cells = query[chosen], of_query[chosen]
            for offset in _AROUND:
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
                found_query.append(chosen[asking[close]])
                found_held.append(held[close])
                found_distance.append(distance[close])
        if not found_query:
            empty = np.zeros(0, dtype=np.int64)
            return empty, empty, np.zeros(0)
        return np.concatenate(found_query), np.concatenate(found_held), np.concatenate(found_distance)


def _duration(seconds: float) -> str:
    """A span as a person reads it: seconds below two minutes, else minutes."""
    return f"{seconds:.0f} s" if seconds < 120 else f"{seconds / 60:.0f} min"


def closing(contact: Any) -> str:
    """A pair within the clearance as built that met, said by its gap (``Contact.near``): ``, closed to 0.18 from
    0.42 mm as built``, or ``, touching as built`` for one under ``RESOLUTION`` then; nothing for any other pair."""
    if contact.near is None:
        return ""
    if contact.near < RESOLUTION:
        return ", touching as built"
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

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
``clearance`` count as touching: the margin a part's tolerance takes anyway. A pair of parts already
touching at zero (a horn on its servo, a part on the bearing it turns on) keeps its count as it turns
about the shared axis, so two parts meet where their pair's count rises ``STOP`` points over its count at
zero, at that pose and the next (a graze past a corner, over it at one pose alone, is no contact); a pair
of links the model says never collide (``Description.excludes``) never meets. The stop reported each way
is the last clear pose and the two parts that met one step past it. Where two parts of one link meet (a
part split in two on its cut, a screw in its hole), that surface is inside the link and is not tested.

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

__all__ = ["GEOMETRY", "Contact", "JointStops", "STOP", "sweep"]

#: Sample points of new contact over a pair's count at zero that make a stop: about 15 mm^2 of surface at
#: the default clearance (a sample per 0.36 mm^2), more than a turn's aliasing on the grid.
STOP = 40
#: Sample spacing, as a share of the clearance.
SPACING = 0.6
#: A full turn, in degrees: a turning joint clear this far each way has no stop.
TURN = 360.0
SWEPT = ("revolute", "continuous", "prismatic")
#: What a sweep tests: each colliding part's own surface (``parts``), or what each part declares a simulator
#: collides it as (``collision``: a fitted box, cylinder, ... where it declares one).
GEOMETRY = ("parts", "collision")


@dataclass(frozen=True)
class Contact:
    """Two parts that met: the moving one (on the swept side) and the still one, each by its part's name and
    its link's, and the pose, in the joint's unit around zero, where they did."""

    moving: str
    moving_link: str
    still: str
    still_link: str
    at: float


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


def sweep(description: Any, *, step: float = 1.0, clearance: float = 1.0, geometry: str = "parts",
          told: Callable[[str], None] | None = None) -> list[JointStops]:
    """Each controlled joint's stops (see the module docstring): ``step`` degrees for a turning joint and
    millimetres for a sliding one, ``clearance`` millimetres, ``geometry`` what is tested (``GEOMETRY``);
    ``told`` hears a line per joint as it is done."""
    if geometry not in GEOMETRY:
        raise ValueError(f"geometry {geometry!r} is none of {', '.join(GEOMETRY)}")
    return _Sweep(description, step, clearance, told or (lambda _line: None), geometry).run()


def _tested(link: Any, geometry: str) -> list[tuple[str, Any]]:
    """A link's tested shapes, each with its part's name: ``parts``, the part itself (its visual mesh) for each
    part that collides at all; ``collision``, what each declares (``Link.collisions``), a decomposed part's hulls
    each under the part's name. A link's collisions are its visuals' subsequence, in order, the parts declared
    ``none`` left out and a decomposed part's hulls one after another."""
    if geometry == "collision":
        return [(collision.of, collision.geometry) for collision in link.collisions]
    found, at = [], 0
    for visual in link.visuals:
        if at < len(link.collisions) and link.collisions[at].of == visual.name:
            found.append((visual.name, visual.geometry))
            while at < len(link.collisions) and link.collisions[at].of == visual.name:
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
                 geometry_of: str = "parts") -> None:
        self.description = description
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
        for link in description.links:
            found, owners = [], []
            for name, geometry in _tested(link, geometry_of):
                if geometry.kind == "mesh":
                    mesh = description.meshes[geometry.mesh]
                    vertices = np.asarray(mesh.positions, dtype=np.float64).reshape(-1, 3) * float(geometry.scale)
                    faces = np.asarray(mesh.triangles, dtype=np.int64).reshape(-1, 3)
                else:
                    vertices, faces = _primitive(geometry.kind, tuple(geometry.size))
                placement = np.asarray(geometry.placement, dtype=float)
                vertices = vertices @ placement[:3, :3].T + placement[:3, 3]
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
        for joint in self.description.controls():
            started = time.perf_counter()
            stops = self.joint(joint)
            found.append(stops)
            self.told(f"{joint.name}: {_said(stops)} ({time.perf_counter() - started:.1f} s)")
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

        def pairs(value: float) -> dict[tuple[int, int], int]:
            frames = self.frames({joint.name: value})
            placed = np.vstack([points @ frames[name][:3, :3].T + frames[name][:3, 3]
                                for name, points in zip(mover_links, local)])
            at, owners = grid.hits(placed)
            if not len(at):
                return {}
            codes = movers[at] * len(self.parts) + owners
            unique, counts = np.unique(codes, return_counts=True)
            return {(int(code) // len(self.parts), int(code) % len(self.parts)): int(count)
                    for code, count in zip(unique, counts)
                    if frozenset((link_of[int(code) // len(self.parts)], link_of[int(code) % len(self.parts)]))
                    not in self.excluded}

        zero = pairs(0.0)
        stops.resting = sorted({(self.parts[a][0], self.parts[b][0]) for a, b in zero})
        step = self.step / scale  # radians or metres
        if turning:
            reach = math.radians(TURN)
        else:
            everything = np.vstack([points @ rest[name][:3, :3].T + rest[name][:3, 3]
                                    for name, points in self.points.items()])
            reach = float(np.linalg.norm(everything.max(axis=0) - everything.min(axis=0))) + step
        count = int(math.ceil(reach / step - 1e-9))
        child_side, parent_side = self.rigid(joint.child) & moving, self.rigid(joint.parent) - moving

        def contact_at(pair: tuple[int, int], value: float) -> Contact:
            moving_part, still_part = self.parts[pair[0]], self.parts[pair[1]]
            return Contact(moving_part[0], moving_part[1], still_part[0], still_part[1], round(value * scale, 6))

        for sign in (-1, 1):
            if sign == 1 and turning and stops.lower_contact is None and stops.lower_clash is None:
                break  # nothing met a full turn one way: nothing meets the other way either
            before: dict[tuple[int, int], int] = {}
            stop: tuple[float, Contact] | None = None
            clash: Contact | None = None
            for k in range(1, count + 1):
                value = sign * k * step
                over = {pair: number - zero.get(pair, 0) for pair, number in pairs(value).items()}
                # A contact is a pair over STOP at a pose and the next: a graze over it at one pose alone is none.
                met = sorted((pair for pair, number in over.items() if number > STOP and before.get(pair, 0) > STOP),
                             key=lambda pair: -before[pair])
                own = [pair for pair in met if link_of[pair[0]] in child_side and link_of[pair[1]] in parent_side]
                if met and clash is None and not own:
                    clash = contact_at(met[0], value - sign * step)
                if own:
                    stop = (round((value - 2 * sign * step) * scale, 6), contact_at(own[0], value - sign * step))
                    break
                before = over
            if sign < 0:
                stops.lower, stops.lower_contact = stop if stop is not None else (None, None)
                stops.lower_clash = clash
            else:
                stops.upper, stops.upper_contact = stop if stop is not None else (None, None)
                stops.upper_clash = clash
        return stops


def _said(stops: JointStops) -> str:
    if not stops.swept:
        return f"not swept: {stops.why}"

    def end(value: float | None, contact: Contact | None, clash: Contact | None) -> str:
        said = "clear" if contact is None else \
            f"{value:+g} {stops.unit} ({contact.moving} meets {contact.still} at {contact.at:+g})"
        if clash is not None:
            said += f", {clash.moving} meeting {clash.still} at {clash.at:+g} as the others stand"
        return said

    return (f"lower {end(stops.lower, stops.lower_contact, stops.lower_clash)}, "
            f"upper {end(stops.upper, stops.upper_contact, stops.upper_clash)}")

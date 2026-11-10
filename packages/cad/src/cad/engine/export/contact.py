"""Which jointed bodies touch at rest: the contact pairs a simulator that filters by pair should exclude.

A simulator collides a link's collision geometry as convex shapes (MuJoCo hulls a mesh), so two links
whose hulls overlap where the model is built start in contact: a revolute link nested in its parent's
pocket, a bearing face on a bearing face. MuJoCo filters a body's contacts with its parent
(``filterparent``) except where the parent is welded to the world, which is where a robot's first joint
is; so the MJCF writer excludes every such pair itself (``export/mjcf.py``), and this is its rule.

**The rule.** For every joint that moves, a joint that closes a loop (``Description.closures``) among
them, the bodies welded to its parent (joined to it by fixed joints
alone, the world's included) and those welded to its child: each pair of them, one from each side, whose
collision geometries overlap or come within ``TOUCH`` of each other with every joint at zero (the
description's zero state, its frames). A floating joint (a free base, ``cad.build123d.free``) is no
joint of a mechanism: a free body resting on a bolted one must collide with it, so no pair across it
is excluded, and its base is welded to nothing, so MuJoCo's ``filterparent`` filters its children's
contacts with it itself. A mesh is its convex hull, a primitive itself, as MuJoCo
collides them. The test is exact for convex shapes: the distance between two of them by GJK over their
support functions, after their axis-aligned boxes (grown by ``TOUCH``) are found to meet. A pair GJK
does not settle in ``ITERATIONS`` steps is counted as touching, so the rule errs towards an exclusion.
Pairs come in joint order, then the closures', each once. Text and numpy alone (law 3), the same description the same pairs.
"""

from __future__ import annotations

import itertools
from typing import Callable

import numpy as np

from cad.engine.description import Description, Geometry, Link

__all__ = ["ITERATIONS", "TOUCH", "touching"]

#: Two shapes this near (metres) touch: a tessellation's rounding of faces that meet.
TOUCH = 1e-5
#: The GJK steps a pair is given before it counts as touching.
ITERATIONS = 64

Support = Callable[[np.ndarray], np.ndarray]


def touching(description: Description) -> list[tuple[str, str]]:
    """The body pairs that touch at rest across a joint that moves (the module's **The rule**), by link name."""
    welded = _welds(description)
    shapes: dict[str, list[tuple[np.ndarray, np.ndarray, Support]]] = {}
    found: list[tuple[str, str]] = []
    seen: set[frozenset[str]] = set()
    moving = [(joint.parent, joint.child) for joint in description.joints if joint.kind not in ("fixed", "floating")]
    for ends in moving + [(closure.parent, closure.child) for closure in description.closures]:
        for parent, child in itertools.product(welded[ends[0]], welded[ends[1]]):
            key = frozenset((parent, child))
            if parent == child or key in seen:
                continue
            ours = shapes.setdefault(parent, _shapes(description, description.link(parent)))
            theirs = shapes.setdefault(child, _shapes(description, description.link(child)))
            if any(_near(a, b) for a in ours for b in theirs):
                seen.add(key)
                found.append((parent, child))
    return found


def _welds(description: Description) -> dict[str, list[str]]:
    """Each link's weld: the links fixed joints alone join it to, itself first, then in link order."""
    neighbours: dict[str, set[str]] = {link.name: set() for link in description.links}
    for joint in description.joints:
        if joint.kind == "fixed":
            neighbours[joint.parent].add(joint.child)
            neighbours[joint.child].add(joint.parent)
    order = {link.name: at for at, link in enumerate(description.links)}
    found: dict[str, list[str]] = {}
    for name in neighbours:
        reached, pending = {name}, [name]
        while pending:
            for other in neighbours[pending.pop()]:
                if other not in reached:
                    reached.add(other)
                    pending.append(other)
        found[name] = [name, *sorted(reached - {name}, key=order.__getitem__)]
    return found


def _shapes(description: Description, link: Link) -> list[tuple[np.ndarray, np.ndarray, Support]]:
    """A link's collision geometries in the model's space: each its box (low, high) and its support function."""
    frame = np.asarray(link.frame, dtype=float)
    return [_shape(description, collision.geometry, frame @ np.asarray(collision.geometry.placement, dtype=float))
            for collision in link.collisions]


def _shape(description: Description, geometry: Geometry, placed: np.ndarray) -> tuple[np.ndarray, np.ndarray, Support]:
    rotation, centre = placed[:3, :3], placed[:3, 3]
    size = [float(value) for value in geometry.size]
    if geometry.kind == "mesh":
        mesh = description.meshes[str(geometry.mesh)]
        points = np.asarray(mesh.positions, dtype=float).reshape(-1, 3) * float(geometry.scale) @ rotation.T + centre
        if not len(points):
            points = centre.reshape(1, 3)
        return points.min(axis=0), points.max(axis=0), lambda d: points[int(np.argmax(points @ d))]

    def local(d: np.ndarray) -> np.ndarray:
        return rotation.T @ d

    if geometry.kind == "box":
        half = np.array(size[:3]) / 2

        def support(d: np.ndarray) -> np.ndarray:
            return centre + rotation @ (np.where(local(d) >= 0, 1.0, -1.0) * half)
    elif geometry.kind == "sphere":
        radius = size[0]

        def support(d: np.ndarray) -> np.ndarray:
            return centre + radius * _unit(d)
    elif geometry.kind == "cylinder":
        radius, half_length = size[0], size[1] / 2

        def support(d: np.ndarray) -> np.ndarray:
            turned = local(d)
            across = np.array([turned[0], turned[1], 0.0])
            return centre + rotation @ (radius * _unit(across) + [0.0, 0.0, half_length if turned[2] >= 0 else -half_length])
    elif geometry.kind == "capsule":
        radius, half_length = size[0], size[1] / 2

        def support(d: np.ndarray) -> np.ndarray:
            end = rotation @ [0.0, 0.0, half_length if local(d)[2] >= 0 else -half_length]
            return centre + end + radius * _unit(d)
    else:
        raise ValueError(f"no contact test for a {geometry.kind!r}")
    axes = np.eye(3)
    low = np.array([support(-axis)[at] for at, axis in enumerate(axes)])
    high = np.array([support(axis)[at] for at, axis in enumerate(axes)])
    return low, high, support


def _unit(d: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(d))
    return d / length if length > 0 else np.zeros(3)


def _near(a: tuple[np.ndarray, np.ndarray, Support], b: tuple[np.ndarray, np.ndarray, Support]) -> bool:
    """Whether two convex shapes are within ``TOUCH``: their boxes first, then GJK's distance."""
    if np.any(a[0] > b[1] + TOUCH) or np.any(b[0] > a[1] + TOUCH):
        return False
    return _distance(a[2], b[2], enough=TOUCH) <= TOUCH


def _distance(a: Support, b: Support, enough: float | None = None) -> float:
    """The distance between two convex shapes by their supports (GJK on their Minkowski difference
    ``a - b``): 0 where they overlap; past ``ITERATIONS`` steps, 0. Given ``enough``, a lower bound on it
    once that bound passes ``enough``: a plane parts them by more."""

    def support(d: np.ndarray) -> np.ndarray:
        return a(d) - b(-d)

    simplex = [support(np.array([1.0, 0.0, 0.0]))]
    v = simplex[0]
    for _step in range(ITERATIONS):
        squared = float(v @ v)
        if squared <= 1e-24:
            return 0.0
        w = support(-v)
        gap = float(v @ w)
        if enough is not None and gap > enough * squared ** 0.5:  # a plane parts them by more than enough
            return gap / squared ** 0.5
        if squared - gap <= 1e-12 * squared:  # converged: v is the closest point
            return squared ** 0.5
        if any(np.allclose(w, held, rtol=0, atol=1e-15) for held in simplex):
            return squared ** 0.5
        simplex, v = _closest(simplex + [w])
    return 0.0


def _closest(points: list[np.ndarray]) -> tuple[list[np.ndarray], np.ndarray]:
    """The point of the hull of ``points`` (four at most) nearest the origin, and the fewest of them it is
    on: every face of the simplex tried, the nearest one whose barycentric weights are all positive."""
    best: tuple[float, int, list[np.ndarray], np.ndarray] | None = None
    for count in range(1, len(points) + 1):
        for chosen in itertools.combinations(range(len(points)), count):
            held = [points[at] for at in chosen]
            base = held[0]
            if count == 1:
                weights, found = np.array([1.0]), base
            else:
                edges = np.stack([point - base for point in held[1:]], axis=1)
                solved = np.linalg.lstsq(edges, -base, rcond=None)[0]
                weights = np.concatenate([[1.0 - solved.sum()], solved])
                found = base + edges @ solved
            if np.any(weights < -1e-12):
                continue
            distance = float(found @ found)
            if best is None or distance < best[0] - 1e-24 or (abs(distance - best[0]) <= 1e-24 and count < best[1]):
                best = (distance, count, held, found)
    assert best is not None
    return best[2], best[3]

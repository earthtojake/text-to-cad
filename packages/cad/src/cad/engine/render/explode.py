"""Explode: where each instance of a document stands when its parts are moved apart, as the viewer
moves them. A port, operation for operation, of the viewer's layout (``@text-to-cad/core``
``lib/viewer/explodedView.js``) and of the records an xbf scene hands it (``lib/xbf/xbfScene.js``
through ``lib/viewer/sceneExplode.js``), so a still and the viewer explode a document alike, and no
node runs at render time.

The records, as the xbf scene makes them: one per instance the document's tree holds, its id the
instance's place in that tree (``o1.2.3``, the root ``o1``), in that order (numbers compared as
numbers); its box the part's -- every node, edge point and vertex of its mesh (``part_box``) --
placed by the instance's matrix (three's ``Box3.applyMatrix4``: the box of the eight placed
corners). The bloom's centre is the box of every placed instance (the scene's ``bounds``). The
scene hands the layout no hierarchy, so every instance is a sibling of every other: one level.

The layout, as ``computeExplodedViewLayout`` and ``applyExplodedViewProgress`` compute it: each level
of the tree moves its child groups radially out of its parent's centre (the assembled offset times
1.5 plus the child's radius times 0.45, by 0.8 less a level down), concentric children telescope
along their longest axis, overlapping siblings are pushed further out along their own ray, and the
levels play over overlapping windows of the 0..1 amount, each smoothstepped. An offset of 1e-6 or
less is none. The arithmetic is the JavaScript's, in its order, and ``Math.hypot`` is V8's
(``js_hypot``), so the same records give the same doubles. One golden made by the viewer's own scene
(``@text-to-cad/core``'s ``lib/xbf/__fixtures__/explode.json``) holds both renderers to one layout.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

__all__ = ["Layout", "Record", "instance_records", "js_hypot", "layout", "moved", "offsets", "part_box", "placed_box",
           "tree_paths"]

EPSILON = 1e-6
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
MAX_LEVELS = 3
RADIAL_SPREAD = 1.5
RADIAL_CLEARANCE = 0.45
LEVEL_FALLOFF = 0.8
CONCENTRIC_THRESHOLD = 0.05
WINDOW_OVERLAP = 0.5
SEPARATION_MARGIN = 0.05
MAX_SEPARATION_PASSES = 10

Vector = tuple[float, float, float]
Bounds = tuple[Vector, Vector]


def js_hypot(*values: float) -> float:
    """``Math.hypot`` as V8 computes it: each value over the largest, their squares summed with
    Kahan's compensation, the root times the largest. Python's ``math.hypot`` rounds otherwise."""
    if any(math.isinf(value) for value in values):
        return math.inf
    if any(math.isnan(value) for value in values):
        return math.nan
    absolute = [abs(value) for value in values]
    largest = max(absolute, default=0.0)
    if largest == 0:
        return 0.0
    total = compensation = 0.0
    for value in absolute:
        n = value / largest
        summand = n * n - compensation
        preliminary = total + summand
        compensation = (preliminary - total) - summand
        total = preliminary
    return math.sqrt(total) * largest


@dataclass
class Record:
    """One thing that moves: its id (its place in the tree), its box where it stands (None: it
    draws nothing, so it does not move), and what the caller knows it by."""

    part_id: str
    bounds: Bounds | None
    key: Any = None


@dataclass
class _Entry:
    record: Record
    index: int
    part_id: str
    segments: list[str]
    bounds: Bounds


@dataclass
class _Node:
    key: str
    entries: list[_Entry]
    bounds: Bounds | None
    center: list[float]
    radius: float
    order: int
    children: list["_Node"] = field(default_factory=list)


@dataclass
class Layout:
    """What ``layout`` found: per moved record, its contributions (a vector and the window of the
    amount it plays over); every record that can move; how many levels move."""

    entries: list[tuple[Record, list[tuple[Vector, tuple[float, float]]]]]
    records: list[Record]
    levels: int


# --- bounds ----------------------------------------------------------------------------------


def _center(bounds: Bounds | None, fallback: Iterable[float] = (0.0, 0.0, 0.0)) -> list[float]:
    if bounds is None:
        return list(fallback)
    low, high = bounds
    return [(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2]


def _size(bounds: Bounds | None, axis: int) -> float:
    if bounds is None:
        return 0.0
    return max(bounds[1][axis] - bounds[0][axis], 0.0)


def _radius(bounds: Bounds | None) -> float:
    x, y, z = _size(bounds, 0), _size(bounds, 1), _size(bounds, 2)
    return math.sqrt(x * x + y * y + z * z) / 2


def _merge(every: Iterable[Bounds | None]) -> Bounds | None:
    low, high = [math.inf] * 3, [-math.inf] * 3
    count = 0
    for bounds in every:
        if bounds is None:
            continue
        count += 1
        for axis in range(3):
            low[axis] = min(low[axis], bounds[0][axis])
            high[axis] = max(high[axis], bounds[1][axis])
    if count and all(math.isfinite(value) for value in low + high):
        return (low[0], low[1], low[2]), (high[0], high[1], high[2])
    return None


# --- the tree --------------------------------------------------------------------------------


def _common_prefix(segment_lists: list[list[str]]) -> int:
    """The path every record shares, less one node, so something is left to tell them apart."""
    paths = [segments for segments in segment_lists if segments]
    if not paths:
        return 0
    shortest = min(len(segments) for segments in paths)
    length = 0
    while length < shortest and all(segments[length] == paths[0][length] for segments in paths):
        length += 1
    return min(length, shortest - 1)


def _groups(entries: list[_Entry], depth: int) -> list[tuple[str, list[_Entry], int]]:
    """The entries by the next node of their path; one whose path ends here a group of its own."""
    groups: dict[str, tuple[str, list[_Entry], int]] = {}
    for entry in entries:
        deeper = len(entry.segments) > depth
        key = "/".join(entry.segments[:depth + 1]) if deeper else entry.part_id
        if key not in groups:
            groups[key] = (key, [], depth + 1 if deeper else depth)
        groups[key][1].append(entry)
    return list(groups.values())


def _node(key: str, entries: list[_Entry], depth: int, levels_left: int) -> _Node:
    bounds = _merge(entry.bounds for entry in entries)
    node = _Node(key, entries, bounds, _center(bounds), _radius(bounds), min(entry.index for entry in entries))
    if levels_left <= 0 or len(entries) < 2:
        return node
    # A chain of single children (a wrapper occurrence) spends no level.
    groups = _groups(entries, depth)
    deeper = depth
    while len(groups) == 1 and groups[0][2] > deeper:
        deeper = groups[0][2]
        groups = _groups(entries, deeper)
    if len(groups) < 2:
        return node
    node.children = sorted((_node(group_key, members, group_depth, levels_left - 1)
                            for group_key, members, group_depth in groups), key=lambda child: child.order)
    return node


# --- the layout ------------------------------------------------------------------------------


def _scale(vector: Iterable[float], scalar: float) -> list[float]:
    x, y, z = vector
    return [x * scalar, y * scalar, z * scalar]


def _fan(axis: int, rank: int) -> list[float]:
    """Tied concentric children fan out at golden angles across their long axis."""
    angle = rank * GOLDEN_ANGLE
    direction = [0.0, 0.0, 0.0]
    first, second = [other for other in (0, 1, 2) if other != axis]
    direction[first] = math.cos(angle)
    direction[second] = math.sin(angle)
    return direction


def _radial(node: _Node, child: _Node, level: int, concentric: list[int]) -> list[float] | None:
    """A child's move away from its parent's centre, or None for the core that stays."""
    falloff = LEVEL_FALLOFF ** (level - 1)
    relative = [child.center[0] - node.center[0], child.center[1] - node.center[1], child.center[2] - node.center[2]]
    distance = js_hypot(*relative)
    if not distance <= max(node.radius * CONCENTRIC_THRESHOLD, EPSILON):
        direction = _scale(relative, 1 / distance)
        return _scale(direction, (distance * RADIAL_SPREAD + child.radius * RADIAL_CLEARANCE) * falloff)
    if concentric[0] == 0:
        concentric[0] += 1
        return None  # the largest concentric child anchors as the core
    rank = concentric[0]
    concentric[0] += 1
    extents = [_size(child.bounds, 0), _size(child.bounds, 1), _size(child.bounds, 2)]
    axis = extents.index(max(extents))
    sign = 1 if rank % 2 == 1 else -1
    step = math.ceil(rank / 2)
    magnitude = (_size(node.bounds, axis) + extents[axis]) * 0.55 * step * (LEVEL_FALLOFF ** (level - 1))
    if magnitude <= EPSILON:
        return _scale(_fan(axis, rank), max(child.radius, EPSILON))
    direction = [0.0, 0.0, 0.0]
    direction[axis] = sign
    return _scale(direction, magnitude)


def _relax(node: _Node, vectors: dict[int, list[float] | None]) -> None:
    """Siblings that still overlap: the outer mover pushed out along its own ray until they clear.

    ``relaxSiblingOverlaps``'s sweep, pair after pair in its order, each push seen by the pairs
    after it. Which pairs of a row overlap is asked of numpy for the whole row at once (the same
    additions, minimums and subtractions, so the same doubles), and asked again after a push moves
    the row's own child: a flat document of hundreds of instances is hundreds of thousands of pairs
    a pass."""
    children = node.children
    count = len(children)
    if count < 2:
        return
    gap = max(node.radius * SEPARATION_MARGIN, EPSILON)
    moving = np.array([bool(vectors.get(id(child))) for child in children])
    shift = np.array([vectors.get(id(child)) or (0.0, 0.0, 0.0) for child in children], np.float64)
    rest_low = np.array([child.bounds[0] for child in children], np.float64)
    rest_high = np.array([child.bounds[1] for child in children], np.float64)
    low, high = rest_low + shift, rest_high + shift  # each box where its vector moves it
    for _pass in range(MAX_SEPARATION_PASSES):
        pushed = False
        for i in range(count - 1):
            after = i + 1
            while after < count:
                overlaps = np.minimum(high[i], high[after:]) - np.maximum(low[i], low[after:])
                found = np.flatnonzero((overlaps > 0).all(1) & (moving[i] | moving[after:]))
                if not len(found):
                    break
                j = after + int(found[0])
                overlap = [float(value) for value in overlaps[found[0]]]
                after = j + 1
                a, b = children[i], children[j]
                va, vb = vectors.get(id(a)), vectors.get(id(b))
                target = j if not va else (i if not vb else (i if js_hypot(*va) >= js_hypot(*vb) else j))
                vector = vectors[id(children[target])]
                length = js_hypot(*vector)
                if length <= EPSILON:
                    continue
                unit = _scale(vector, 1 / length)
                travel = math.inf
                for axis in range(3):
                    if abs(unit[axis]) > 0.25:
                        travel = min(travel, (overlap[axis] + gap) / abs(unit[axis]))
                if not math.isfinite(travel):
                    continue
                push = _scale(unit, travel)
                moved = [vector[0] + push[0], vector[1] + push[1], vector[2] + push[2]]
                vectors[id(children[target])] = moved
                low[target], high[target] = rest_low[target] + moved, rest_high[target] + moved
                pushed = True
        if not pushed:
            return


def _windows(levels: int) -> list[tuple[float, float]]:
    """Each level's share of the amount, half of it shared with the next level's."""
    if levels <= 1:
        return [(0.0, 1.0)]
    span = 1 / (1 + (levels - 1) * (1 - WINDOW_OVERLAP))
    found = []
    for index in range(levels):
        start = index * span * (1 - WINDOW_OVERLAP)
        found.append((start, min(start + span, 1.0)))
    return found


def layout(records: list[Record], model_bounds: Bounds | None = None,
           hierarchy: dict[str, list[str]] | None = None) -> Layout:
    """``computeExplodedViewLayout``: ``records`` in their order, ``model_bounds`` the centre the
    top level blooms from, ``hierarchy`` each record's path of node ids (root first), or None:
    every record a sibling, as an xbf scene asks."""
    movable = [record for record in records if record.part_id.strip() and record.part_id.strip() != "__model__"]
    empty = Layout([], movable, 0)
    if len(movable) < 2:
        return empty
    entries = []
    for index, record in enumerate(movable):
        if record.bounds is None:
            continue
        path = (hierarchy or {}).get(record.part_id.strip())
        segments = [str(node).strip() for node in path if str(node).strip()] if isinstance(path, list) else []
        entries.append(_Entry(record, index, record.part_id.strip(), segments, record.bounds))
    if len(entries) < 2:
        return empty
    root = _node("", entries, _common_prefix([entry.segments for entry in entries]), MAX_LEVELS)
    if not root.children:
        return empty
    if model_bounds is not None:
        root.bounds = model_bounds
        root.center = _center(model_bounds, root.center)
        root.radius = _radius(model_bounds)
    contributions: dict[int, tuple[Record, list[tuple[list[float], int]]]] = {}
    levels = 0
    queue = deque([(root, 1)])
    while queue:
        node, level = queue.popleft()
        concentric = [0]
        vectors: dict[int, list[float] | None] = {}
        for child in sorted(node.children, key=lambda child: -child.radius):  # the largest concentric one anchors
            vectors[id(child)] = _radial(node, child, level, concentric)
        _relax(node, vectors)
        for child in node.children:
            vector = vectors.get(id(child))
            if vector:
                levels = max(levels, level)
                for entry in child.entries:
                    contributions.setdefault(id(entry.record), (entry.record, []))[1].append((vector, level))
            if child.children:
                queue.append((child, level + 1))
    if not levels:
        return empty
    windows = _windows(levels)
    return Layout([(record, [((vector[0], vector[1], vector[2]), windows[min(level, levels) - 1])
                             for vector, level in found]) for record, found in contributions.values()], movable, levels)


def _progress(window: tuple[float, float], amount: float) -> float:
    start, end = window
    t = min(max((min(max(amount, 0.0), 1.0) - start) / max(end - start, EPSILON), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def moved(found: Layout, amount: float) -> dict[Any, Vector]:
    """``applyExplodedViewProgress``: each moved record's offset at ``amount`` (0..1), by its key;
    a record whose offset is 1e-6 or less is not moved, and not listed."""
    offsets: dict[Any, Vector] = {}
    for record, contributions in found.entries:
        offset = [0.0, 0.0, 0.0]
        for vector, window in contributions:
            local = _progress(window, amount)
            if local <= EPSILON:
                continue
            offset[0] += vector[0] * local
            offset[1] += vector[1] * local
            offset[2] += vector[2] * local
        if js_hypot(*offset) > EPSILON:
            offsets[record.key] = (offset[0], offset[1], offset[2])
    return offsets


# --- an xbf scene's records ------------------------------------------------------------------


def tree_paths(tree: dict[str, Any]) -> dict[int, str]:
    """Each instance's place in the document's tree: ``o1``, its children ``o1.1``, ``o1.2``, ..."""
    found: dict[int, str] = {}

    def walk(node: dict[str, Any], path: str) -> None:
        if isinstance(node.get("instance"), int):
            found[node["instance"]] = path
        for at, child in enumerate(node.get("children") or []):
            walk(child, f"{path}.{at + 1}")

    walk(tree or {}, "o1")
    return found


def part_box(mesh: Any) -> tuple[np.ndarray, np.ndarray] | None:
    """A part's box as the xbf scene measures it: every node, edge point and vertex of its mesh
    (``mesh.Mesh``); None for a part with none."""
    every = [np.asarray(mesh.positions, np.float64).reshape(-1, 3), np.asarray(mesh.edge_points, np.float64).reshape(-1, 3),
             np.asarray(mesh.vertices, np.float64).reshape(-1, 4)[:, 1:4]]
    every = [points for points in every if len(points)]
    if not every:
        return None
    points = np.concatenate(every)
    return points.min(0), points.max(0)


def placed_box(box: tuple[np.ndarray, np.ndarray], matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """three's ``Box3.applyMatrix4``: the box's eight corners placed, and their box."""
    low, high = box
    corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    placed = corners @ matrix[:3, :3].T + matrix[:3, 3]
    return placed.min(0), placed.max(0)


def _placed(box: tuple[Any, Any], matrix: np.ndarray) -> Bounds:
    """``placed_box`` in three's own order of operations (``Vector3.applyMatrix4``), in doubles."""
    m = [[float(value) for value in row] for row in matrix[:3]]
    low, high = [float(value) for value in box[0]], [float(value) for value in box[1]]
    placed = []
    for x in (low[0], high[0]):
        for y in (low[1], high[1]):
            for z in (low[2], high[2]):
                placed.append([m[row][0] * x + m[row][1] * y + m[row][2] * z + m[row][3] for row in range(3)])
    return ((min(p[0] for p in placed), min(p[1] for p in placed), min(p[2] for p in placed)),
            (max(p[0] for p in placed), max(p[1] for p in placed), max(p[2] for p in placed)))


def instance_records(structure: dict[str, Any], boxes: list[Any], matrices: list[np.ndarray]) -> tuple[list[Record], Bounds]:
    """The xbf scene's records -- one per instance its tree holds, in tree order, each keyed by its
    instance's index -- and the box of every placed instance, the bloom's centre. ``boxes``: each
    prototype's ``part_box`` (by prototype index; None for one that draws nothing); ``matrices``:
    each instance's 4x4 placement."""
    paths = tree_paths(structure.get("tree") or {})
    placed = {index: _placed(boxes[instance["prototype"]], matrices[index])
              for index, instance in enumerate(structure["instances"]) if boxes[instance["prototype"]] is not None}
    order = sorted((index for index in range(len(structure["instances"])) if index in paths),
                   key=lambda index: [int(part) for part in paths[index][1:].split(".")])
    records = [Record(paths[index], placed[index], index) for index in order if index in placed]
    rest = _merge(placed.values()) or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return records, rest


def offsets(structure: dict[str, Any], meshes: list[Any], matrices: list[np.ndarray], amount: float) -> dict[int, np.ndarray]:
    """Each moved instance's offset in world millimetres at ``amount`` (0..1), by instance index:
    the viewer's Explode of an xbf scene. ``meshes``: each prototype's ``mesh.Mesh``, by index."""
    records, rest = instance_records(structure, [part_box(mesh) for mesh in meshes], matrices)
    return {index: np.array(offset, float) for index, offset in moved(layout(records, rest), amount).items()}

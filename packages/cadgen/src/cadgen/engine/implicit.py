"""Implicit solids: a field sampled on a grid, contoured, and made B-rep (the engine's **Implicit
solids**).

``solid(field, bounds, cell)`` is geometry a model's body makes, as ``bd.Box`` is: a build123d
``Solid`` (a ``Compound`` of solids where the field holds several bodies) whose faces are the
planar triangles of the field's zero surface. A field is any callable from points to values --
``field(points)``, ``points`` an ``(N, 3)`` float64 array in millimetres, answering ``N`` values,
negative inside -- so the kernel that writes it is the author's (numpy, JAX, any library the
model's environment holds); the engine imports none. It is evaluated where the body runs, in the
model's worker, never in the engine's server.

The contour is marching tetrahedra on the grid's Freudenthal split (six tetrahedra a cell, every
cell split alike, so neighbours share their faces' diagonals): its surface is closed and
manifold by construction -- every triangle edge is two triangles' -- and no two triangles cross,
since each lies in its own tetrahedron. Each vertex is then moved along its grid edge to where
the field itself crosses zero (``refine``), not where the line between the edge's two samples
does, so the surface is on the field's zero set wherever it has a vertex: a blend or a thin
wall's middle bends the field inside an edge, and the line can be most of the edge off. The
slivers a surface passing at a sample leaves around it are collapsed (``collapse``). Each
connected surface is a shell: one whose volume is positive bounds a body, a negative one a void,
given to the innermost body around it. An edge where two triangles meet within the engine's
angular deflection (``mesh_format.ANGULAR``, the angle the engine tessellates a curved face to)
is coded G1, as an edge between faces of one smooth surface: a pick grows over the surface as a
tangent group, and the viewer and the stills draw such an edge as they draw a tangent one. A
sharper edge stays a feature edge.

What it refuses, by name, before any B-rep (law 17): bounds that clip the part (a sample on the
grid's boundary inside), an empty field, a field answering the wrong shape or a value that is
not finite, a grid past ``MAX_SAMPLES``, a feature or gap thinner than the cell -- the field is
sampled again at every cell's centre, and a centre whose sign differs from all eight corners of
its cell is a wall or a gap the grid cannot resolve -- and a surface the field's crossings fold
over inside a tetrahedron. Detail finer than the cell that changes no sign the samples see (a
ripple on a surface) is not in the B-rep: the cell is the resolution the author asked for.

The B-rep is one operation of the memo, keyed by the surface's digest (its vertices and
triangles), so a body run again with a field that makes the same surface makes no B-rep and keeps
every name; the field itself is the body's code, which the body's key covers.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Callable

import numpy as np

from cadgen.engine.mesh_format import ANGULAR

__all__ = ["CHUNK", "MAX_SAMPLES", "solid"]

# Points per call of the field: every call but a grid smaller than one is this long (the last
# padded with its own last point), so a tracing kernel (JAX's jit) traces the field once.
CHUNK = 1 << 18
# The most samples a grid may hold (a float64 each, as many again at the cells' centres).
MAX_SAMPLES = 1 << 25
# How near a crossing may come to a sample, as a fraction of the edge: a crossing at a sample
# would make a triangle of no area, and the field there is no more exact than the clamp.
CLAMP = 1e-3
# Edges shorter than this fraction of the cell are collapsed (``collapse``): the slivers a surface
# passing at or near a sample leaves around it, whose normals are the grid's, not the surface's.
SHORT = 0.05
# Steps of the root finding that moves each vertex to the field's own crossing on its edge
# (``refine``): the Illinois method gains about 1.4 digits a step.
REFINE = 8

# The Freudenthal split: each tetrahedron a chain from corner 000 to 111, one axis at a time.
_ORDERS = ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
# A tetrahedron edge, by the offset from its lower sample to its upper: an edge of the grid is
# its lower sample's flat index times seven plus the offset's index here.
_OFFSETS = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1))
_OFFSET = {offset: index for index, offset in enumerate(_OFFSETS)}

_SURFACES: dict[str, tuple] = {}
_MADE: Any = None


def _tetrahedra() -> list[tuple[tuple[int, int, int], ...]]:
    found = []
    for order in _ORDERS:
        corners = [(0, 0, 0)]
        for axis in order:
            corner = list(corners[-1])
            corner[axis] = 1
            corners.append(tuple(corner))
        found.append(tuple(corners))
    return found


def _bounds(bounds: Any) -> tuple[np.ndarray, np.ndarray]:
    """``bounds`` as its low and high corners: a build123d ``BoundBox``, or two points."""
    low = getattr(bounds, "min", None)
    high = getattr(bounds, "max", None)
    if low is None or high is None:
        try:
            low, high = bounds
        except (TypeError, ValueError):
            raise ValueError(f"bounds is a BoundBox or two points ((x0, y0, z0), (x1, y1, z1)), not {bounds!r}") from None
    try:
        low, high = (np.array([float(value) for value in point], dtype=np.float64) for point in (low, high))
    except (TypeError, ValueError):
        raise ValueError(f"bounds is a BoundBox or two points ((x0, y0, z0), (x1, y1, z1)), not {bounds!r}") from None
    if low.shape != (3,) or high.shape != (3,) or not (np.isfinite(low).all() and np.isfinite(high).all()):
        raise ValueError(f"bounds is two points of three finite coordinates, not {bounds!r}")
    if not (high > low).all():
        raise ValueError(f"bounds' second point must exceed its first on every axis: {tuple(low)} to {tuple(high)}")
    return low, high


def _sample(field: Callable[[Any], Any], origin: np.ndarray, cell: float, counts: tuple[int, int, int]) -> np.ndarray:
    """The field at every point of the grid ``origin + (i, j, k) * cell``, as an array of
    ``counts`` (``_evaluate``)."""
    total = int(np.prod(counts))
    return _evaluate(field, total, lambda index: origin + np.stack(np.unravel_index(index, counts), axis=1) * cell
                     ).reshape(counts)


def _evaluate(field: Callable[[Any], Any], total: int, points_of: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """The field at ``total`` points, ``points_of(indices)`` making each chunk's: called with
    ``CHUNK`` points at a time (fewer only when there are fewer in all), the last chunk padded
    with its own last point, and every answer checked (one finite number a point)."""
    values = np.empty(total, dtype=np.float64)
    size = min(total, CHUNK)
    for start in range(0, total, size):
        index = np.arange(start, min(start + size, total))
        if len(index) < size:
            index = np.concatenate([index, np.full(size - len(index), index[-1])])
        points = points_of(index)
        answer = field(np.ascontiguousarray(points, dtype=np.float64))
        try:
            answer = np.asarray(answer, dtype=np.float64)
        except (TypeError, ValueError):
            raise ValueError(f"the field answered {type(answer).__name__}, not an array of numbers") from None
        if answer.shape != (size,):
            raise ValueError(f"the field answered an array of shape {answer.shape} for {size} points: it answers "
                             f"one value a point, shape ({size},)")
        bad = ~np.isfinite(answer)
        if bad.any():
            at = points[int(np.argmax(bad))]
            raise ValueError(f"the field is {answer[int(np.argmax(bad))]} at {_point(at)}: every value must be finite")
        stop = min(start + size, total)
        values[start:stop] = answer[:stop - start]
    return values


def _point(point: Any) -> str:
    return "(" + ", ".join(f"{float(value):g}" for value in point) + ")"


def _refuse_clipped(values: np.ndarray, origin: np.ndarray, cell: float) -> None:
    """A sample on the grid's boundary inside: the bounds cut the part, and its surface would
    be open there."""
    for axis, name in enumerate("xyz"):
        for end in (0, -1):
            face = np.take(values, end, axis=axis)
            inside = face < 0
            if inside.any():
                where = list(np.unravel_index(int(np.argmax(inside)), face.shape))
                where.insert(axis, end % values.shape[axis])
                at = origin + np.array(where) * cell
                side = "low" if end == 0 else "high"
                raise ValueError(f"the field is inside at the bounds' {side} {name} face, at {_point(at)} "
                                 f"({int(inside.sum())} samples there): the bounds cut the part; give bounds "
                                 "that hold it with a cell to spare")


def _refuse_unresolved(values: np.ndarray, centres: np.ndarray, origin: np.ndarray, cell: float) -> None:
    """A cell whose centre's sign differs from all eight of its corners: a wall, a feature or a
    gap thinner than the cell passes between the samples, and the contour would drop it."""
    inside = values < 0
    corners = [inside[i:i + inside.shape[0] - 1, j:j + inside.shape[1] - 1, k:k + inside.shape[2] - 1]
               for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    every = np.logical_and.reduce(corners)
    none = ~np.logical_or.reduce(corners)
    centre = centres < 0
    for found, what in ((none & centre, "inside while its eight corners are outside: a wall or a feature thinner "
                                         "than the cell"),
                        (every & ~centre, "outside while its eight corners are inside: a gap or a hole thinner "
                                          "than the cell")):
        if found.any():
            at = origin + (np.array(np.unravel_index(int(np.argmax(found)), found.shape)) + 0.5) * cell
            raise ValueError(f"the field at the cell centre {_point(at)} is {what} ({cell:g} mm; "
                             f"{int(found.sum())} such cells): give a smaller cell")


def solid(field: Callable[[Any], Any], bounds: Any, cell: float) -> Any:
    """The solid inside the zero surface of ``field`` (negative inside), sampled every ``cell``
    millimetres over ``bounds`` (a ``BoundBox`` or two points): a ``Solid`` of planar
    triangles, or a ``Compound`` of solids for a field of several bodies. Refused by name for
    bounds that cut the part, an empty field, a field answering anything but one finite value a
    point, a wall or a gap thinner than the cell, a surface that folds inside a cell, and a grid
    past ``MAX_SAMPLES`` (see the module)."""
    global _MADE
    if not callable(field):
        raise ValueError(f"field is a function of points, not {type(field).__name__}")
    low, high = _bounds(bounds)
    try:
        cell = float(cell)
    except (TypeError, ValueError):
        raise ValueError(f"cell is a length in millimetres, not {cell!r}") from None
    if not (math.isfinite(cell) and cell > 0):
        raise ValueError(f"cell is a positive length in millimetres, not {cell!r}")
    counts = tuple(int(value) for value in np.ceil((high - low) / cell - 1e-9).astype(np.int64) + 1)
    for axis, count in zip("xyz", counts):
        if count < 3:
            raise ValueError(f"the bounds are {(count - 1) * cell:g} mm on {axis}, under two cells of {cell:g} mm: "
                             "the part needs a cell of space on every side")
    total = math.prod(counts) + math.prod(count - 1 for count in counts)
    if total > MAX_SAMPLES * 2:
        raise ValueError(f"a {cell:g} mm cell over these bounds is a grid of {counts[0]} x {counts[1]} x {counts[2]} "
                         f"samples, past the {MAX_SAMPLES:,} the engine samples: give a larger cell or smaller bounds")
    values = _sample(field, low, cell, counts)
    _refuse_clipped(values, low, cell)
    centres = _sample(field, low + cell / 2, cell, tuple(count - 1 for count in counts))
    _refuse_unresolved(values, centres, low, cell)
    del centres
    if not (values < 0).any():
        raise ValueError(f"the field is nowhere inside the bounds at a {cell:g} mm cell: it holds no solid there "
                         "(the field is negative inside)")
    vertices, triangles = surface(field, values, low, cell)
    digest = hashlib.blake2b(digest_size=20)
    digest.update(np.ascontiguousarray(vertices, dtype="<f8").tobytes())
    digest.update(np.ascontiguousarray(triangles, dtype="<i8").tobytes())
    key = digest.hexdigest()
    if _MADE is None:
        from cadgen.engine.kernel.memo import wrap_function

        _MADE = wrap_function("implicit_solid", _made)
    _SURFACES[key] = (vertices, triangles)
    try:
        return _MADE(key)
    finally:
        _SURFACES.pop(key, None)


def _made(key: str) -> Any:
    """The B-rep of the surface ``solid`` keyed (``_SURFACES``): one operation of the memo."""
    return brep(*_SURFACES[key])


def surface(field: Callable[[Any], Any], values: np.ndarray, origin: np.ndarray,
            cell: float) -> tuple[np.ndarray, np.ndarray]:
    """The closed triangle surface of the field sampled as ``values``: contoured
    (``contour``), each vertex moved along its grid edge to where the field itself crosses zero
    (``refine``), and its slivers collapsed (``collapse``)."""
    triangles, quads, lower, upper, below, above = crossings(values, origin, cell)
    vertices = refine(field, lower, upper, below, above)
    triangles = np.concatenate([triangles, split(vertices, quads)])
    _refuse_folded(vertices, triangles, lower, upper, below, cell)
    return collapse(vertices, triangles, SHORT * cell)


def _refuse_folded(vertices: np.ndarray, triangles: np.ndarray, lower: np.ndarray, upper: np.ndarray,
                   below: np.ndarray, cell: float) -> None:
    """A triangle the field's crossings turned over: the field bends so hard inside one
    tetrahedron that its section folds, as no surface the cell resolves does."""
    outward = np.where((below < 0)[:, None], upper - lower, lower - upper)
    a, b, c = (vertices[triangles[:, corner]] for corner in range(3))
    folded = (np.cross(b - a, c - a) * outward[triangles].sum(axis=1)).sum(axis=1) < 0
    if folded.any():
        at = (a + b + c)[int(np.argmax(folded))] / 3
        raise ValueError(f"the field bends inside a cell at {_point(at)} so far that the surface folds there "
                         f"({int(folded.sum())} triangles; {cell:g} mm cell): give a smaller cell")


def refine(field: Callable[[Any], Any], lower: np.ndarray, upper: np.ndarray, below: np.ndarray,
           above: np.ndarray) -> np.ndarray:
    """Where the field crosses zero on each edge from ``lower`` (its value ``below``) to
    ``upper`` (``above``), the two of opposite signs: ``REFINE`` steps of the Illinois method
    (false position that halves a stale end's value), every step one evaluation of the field at
    every edge's guess, so the vertex is the field's own crossing rather than the line's between two
    samples -- where the field bends inside an edge (a thin wall's middle, a blend), the line
    can be most of the edge off. Each stays on its edge, ``CLAMP`` from its ends: the contour's
    topology, and each triangle inside its tetrahedron, are the samples'."""
    # The bracket [a, b] along each edge, its ends' values of opposite sides (inside is
    # negative; zero is outside, as the contour counts it).
    a, b = np.zeros(len(lower)), np.ones(len(lower))
    fa, fb = below.astype(np.float64).copy(), above.astype(np.float64).copy()
    moved = np.zeros(len(lower), dtype=np.int8)  # the end the last step moved: -1 a, +1 b
    span = upper - lower

    def guess() -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            at = (a * fb - b * fa) / (fb - fa)
        return np.clip(np.where(np.isfinite(at), at, (a + b) / 2), a, b)

    for _ in range(REFINE):
        at = guess()
        value = _evaluate(field, len(at), lambda index: lower[index] + at[index, None] * span[index])
        with_a = (value < 0) == (fa < 0)
        # An end left in place twice running has its value halved (Illinois): no stall.
        fb = np.where(with_a & (moved == -1), fb / 2, fb)
        fa = np.where(~with_a & (moved == 1), fa / 2, fa)
        a, fa = np.where(with_a, at, a), np.where(with_a, value, fa)
        b, fb = np.where(with_a, b, at), np.where(with_a, fb, value)
        moved = np.where(with_a, -1, 1).astype(np.int8)
    at = np.clip(guess(), CLAMP, 1 - CLAMP)
    return lower + at[:, None] * span


def collapse(vertices: np.ndarray, triangles: np.ndarray, shortest: float,
             passes: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """``triangles`` with every edge shorter than ``shortest`` collapsed, its second vertex into
    its first, which stays where it is (a crossing of the field), and the vertices no triangle
    holds any more dropped. A collapse is made only where it keeps the surface a closed
    manifold -- the edge's two ends share exactly the two neighbours of its two triangles (the
    link condition), and neither end is a corner of a tetrahedron's worth of triangles -- and
    turns no triangle over. Shortest first, in the order of the edges' lengths and then their
    vertices, so the same surface collapses the same way."""
    pairs = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    pairs = np.unique(pairs, axis=0)
    lengths = np.linalg.norm(vertices[pairs[:, 0]] - vertices[pairs[:, 1]], axis=1)
    short = lengths < shortest
    if not short.any():
        return vertices, triangles
    candidates = pairs[short][np.lexsort((pairs[short][:, 1], pairs[short][:, 0], lengths[short]))].tolist()
    rows = triangles.tolist()
    alive = [True] * len(rows)
    flat = triangles.reshape(-1)
    order = np.argsort(flat, kind="stable")
    starts = np.searchsorted(flat[order], np.arange(len(vertices) + 1)).tolist()
    order = (order // 3).tolist()
    fans: dict[int, set[int]] = {}
    gone: set[int] = set()
    points = vertices.tolist()

    def fan(vertex: int) -> set[int]:
        found = fans.get(vertex)
        if found is None:
            found = fans[vertex] = set(order[starts[vertex]:starts[vertex + 1]])
        return found

    def ring(vertex: int) -> set[int]:
        return {other for face in fan(vertex) for other in rows[face] if other != vertex}

    def normal(a: int, b: int, c: int) -> tuple[float, float, float]:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points[a], points[b], points[c]
        ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
        return uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx

    for keep, lose in candidates:
        if keep in gone or lose in gone:
            continue
        kept, lost = fan(keep), fan(lose)
        shared = kept & lost
        if len(shared) != 2:
            continue
        around, other = ring(keep), ring(lose)
        if len(around & other) != 2 or len(around | other) <= 4:
            continue
        moved = lost - shared
        turned = False
        for face in moved:
            before = normal(*rows[face])
            after = normal(*(keep if corner == lose else corner for corner in rows[face]))
            if sum(x * y for x, y in zip(before, after)) <= 0:
                turned = True
                break
        if turned:
            continue
        for face in shared:
            alive[face] = False
            for corner in rows[face]:
                fan(corner).discard(face)
        for face in moved:
            rows[face] = [keep if corner == lose else corner for corner in rows[face]]
            kept.add(face)
        gone.add(lose)
        fans.pop(lose, None)
    if not gone:
        return vertices, triangles
    left = np.array([row for row, live in zip(rows, alive) if live], dtype=np.int64).reshape(-1, 3)
    used, left = np.unique(left, return_inverse=True)
    # A collapse can leave an edge short that was not (a neighbour of the lost vertex now
    # meeting the kept one): the next pass takes it.
    return collapse(vertices[used], left.reshape(-1, 3), shortest, passes - 1) if passes > 1 else \
        (vertices[used], left.reshape(-1, 3))


def contour(values: np.ndarray, origin: np.ndarray, cell: float) -> tuple[np.ndarray, np.ndarray]:
    """The zero surface of sampled ``values`` (negative inside; zero is outside): its vertices
    (V x 3, millimetres) and triangles (T x 3 rows of vertex indices), each wound outward, toward
    the positive side. Each vertex is on one edge of the grid, where the line between its two
    samples crosses zero (``crossings``; ``refine`` asks the field instead)."""
    triangles, quads, lower, upper, below, above = crossings(values, origin, cell)
    at = np.clip(below / (below - above), CLAMP, 1 - CLAMP)
    vertices = lower + at[:, None] * (upper - lower)
    return vertices, np.concatenate([triangles, split(vertices, quads)])


def split(vertices: np.ndarray, quads: np.ndarray) -> np.ndarray:
    """Each quad (Q x 4, a cycle wound outward) as two triangles, across whichever diagonal
    leaves them flatter -- the larger cosine between their normals; the first diagonal on a tie.
    A quad's diagonal runs inside its tetrahedron, so either is the quad's alone."""
    if not len(quads):
        return np.zeros((0, 3), dtype=np.int64)
    p = [vertices[quads[:, corner]] for corner in range(4)]

    def cosine(a, b, c, d, e, f) -> np.ndarray:
        first, second = np.cross(b - a, c - a), np.cross(e - d, f - d)
        size = np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1)
        return (first * second).sum(axis=1) / np.where(size > 0, size, 1.0) - (size == 0) * 2.0

    across = cosine(p[1], p[3], p[0], p[3], p[1], p[2]) > cosine(p[0], p[1], p[2], p[0], p[2], p[3])
    one = np.where(across[:, None], quads[:, [0, 1, 3]], quads[:, [0, 1, 2]])
    two = np.where(across[:, None], quads[:, [1, 2, 3]], quads[:, [0, 2, 3]])
    return np.concatenate([one, two])


def crossings(values: np.ndarray, origin: np.ndarray,
              cell: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The contour's polygons over its vertices, one a grid edge the surface crosses: the
    triangles (T x 3) and quads (Q x 4, a cycle) a tetrahedron's section is, each wound outward;
    each edge's ends (``lower`` and ``upper``, V x 3 millimetres) and the values there
    (``below``, ``above``: one negative, the other not)."""
    shape = values.shape
    inside = values < 0
    corners = [inside[i:i + shape[0] - 1, j:j + shape[1] - 1, k:k + shape[2] - 1]
               for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    crossed = np.logical_or.reduce(corners) & ~np.logical_and.reduce(corners)
    cells = np.nonzero(crossed)
    del corners, crossed
    found: list[np.ndarray] = []
    fours: list[np.ndarray] = []
    for tetrahedron in _tetrahedra():
        samples = [tuple(cells[axis] + corner[axis] for axis in range(3)) for corner in tetrahedron]
        flat = [np.ravel_multi_index(sample, shape) for sample in samples]
        code = sum(inside[sample].astype(np.int64) << bit for bit, sample in enumerate(samples))

        def edge(a: int, b: int, chosen: np.ndarray, tetrahedron=tetrahedron, flat=flat) -> np.ndarray:
            low, high = (a, b) if tetrahedron[a] < tetrahedron[b] else (b, a)
            offset = tuple(int(u) - int(v) for u, v in zip(tetrahedron[high], tetrahedron[low]))
            return flat[low][chosen] * 7 + _OFFSET[offset]

        for case in range(1, 15):
            chosen = np.nonzero(code == case)[0]
            if not len(chosen):
                continue
            ins = [corner for corner in range(4) if case >> corner & 1]
            outs = [corner for corner in range(4) if not case >> corner & 1]
            if len(ins) == 1 or len(outs) == 1:
                lone = ins[0] if len(ins) == 1 else outs[0]
                found.append(np.stack([edge(lone, other, chosen) for other in range(4) if other != lone], axis=1))
            else:
                (i, j), (k, m) = ins, outs
                # A cycle: ik-im on face ikm, im-jm on ijm, jm-jk on jkm, jk-ik on ijk.
                fours.append(np.stack([edge(i, k, chosen), edge(i, m, chosen), edge(j, m, chosen),
                                       edge(j, k, chosen)], axis=1))
    threes = np.concatenate(found) if found else np.zeros((0, 3), dtype=np.int64)
    fours = np.concatenate(fours) if fours else np.zeros((0, 4), dtype=np.int64)
    edges, inverse = np.unique(np.concatenate([threes.reshape(-1), fours.reshape(-1)]), return_inverse=True)
    triangles, quads = inverse[:threes.size].reshape(-1, 3), inverse[threes.size:].reshape(-1, 4)
    lower = np.stack(np.unravel_index(edges // 7, shape), axis=1)
    upper = lower + np.array(_OFFSETS)[edges % 7]
    below, above = values.reshape(-1)[edges // 7], values[tuple(upper.T)]
    # Wound by the samples' own section, the plane where the line through each edge's samples
    # crosses zero (a triangle's or a quad's corners all on it): outward is from an edge's inside
    # sample toward its outside one, and a polygon's edges agree on the side, so their sum is a
    # direction off that plane on the outside. The winding is the polygon's for good, wherever
    # ``refine`` then moves its corners along their edges.
    at = np.clip(below / (below - above), CLAMP, 1 - CLAMP)
    vertices = lower + at[:, None] * (upper - lower)
    outward = np.where((below < 0)[:, None], upper - lower, lower - upper).astype(np.float64)
    a, b, c = (vertices[triangles[:, corner]] for corner in range(3))
    flip = (np.cross(b - a, c - a) * outward[triangles].sum(axis=1)).sum(axis=1) < 0
    triangles[flip] = triangles[flip][:, ::-1]
    p = [vertices[quads[:, corner]] for corner in range(4)]
    flip = (np.cross(p[2] - p[0], p[3] - p[1]) * outward[quads].sum(axis=1)).sum(axis=1) < 0
    quads[flip] = quads[flip][:, ::-1]
    return triangles, quads, origin + lower * cell, origin + upper * cell, below, above


def _components(triangles: np.ndarray, count: int) -> np.ndarray:
    """Each vertex's connected surface, as the least vertex index in it."""
    label = np.arange(count)
    pairs = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    while True:
        least = np.minimum(label[pairs[:, 0]], label[pairs[:, 1]])
        merged = label.copy()
        np.minimum.at(merged, pairs[:, 0], least)
        np.minimum.at(merged, pairs[:, 1], least)
        merged = merged[merged]
        if np.array_equal(merged, label):
            return label
        label = merged


def _volume(vertices: np.ndarray, triangles: np.ndarray) -> float:
    a, b, c = (vertices[triangles[:, corner]] for corner in range(3))
    return float((a * np.cross(b, c)).sum() / 6)


def _contains(vertices: np.ndarray, triangles: np.ndarray, point: np.ndarray) -> bool:
    """Whether ``point`` is inside the closed surface ``triangles``: the parity of the
    triangles a ray along +x from it crosses (a ray skewed off the grid's planes)."""
    direction = np.array([1.0, 1e-3 * math.sqrt(2), 1e-3 * math.sqrt(3)])
    a, b, c = (vertices[triangles[:, corner]] for corner in range(3))
    ab, ac = b - a, c - a
    p = np.cross(direction, ac)
    det = (ab * p).sum(axis=1)
    ok = np.abs(det) > 1e-15
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = point - a
    u = (s * p).sum(axis=1) * inv
    q = np.cross(s, ab)
    v = (q @ direction) * inv
    t = (ac * q).sum(axis=1) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
    return bool(hit.sum() % 2)


def brep(vertices: np.ndarray, triangles: np.ndarray) -> Any:
    """The B-rep of a closed, outward-wound triangle surface: a planar face a triangle, one
    shell a connected surface, a solid each body with its voids; edges within the angular
    deflection coded G1 (see the module)."""
    import build123d as bd
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Solid

    label = _components(triangles, len(vertices))
    surfaces = label[triangles[:, 0]]
    shells, bodies, voids = [], [], []
    for index, root in enumerate(np.unique(surfaces)):
        mine = triangles[surfaces == root]
        volume = _volume(vertices, mine)
        shells.append(mine)
        (bodies if volume > 0 else voids).append((index, abs(volume)))
    held: dict[int, list[int]] = {body: [] for body, _volume in bodies}
    for void, _size in voids:
        point = vertices[shells[void][0, 0]]
        around = [(size, body) for body, size in bodies if _contains(vertices, shells[body], point)]
        if not around:
            raise RuntimeError("the contour holds a void inside no body: an engine error, never a field's")
        held[min(around)[1]].append(void)
    builder = BRep_Builder()
    solids = []
    for body, _size in sorted(bodies, key=lambda found: -found[1]):
        made = TopoDS_Solid()
        builder.MakeSolid(made)
        for index in (body, *held[body]):
            builder.Add(made, _shell(vertices, shells[index], builder))
        solids.append(made)
    if len(solids) == 1:
        return bd.Solid(solids[0])
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for made in solids:
        builder.Add(compound, made)
    return bd.Compound(compound)


def _shell(vertices: np.ndarray, triangles: np.ndarray, builder: Any) -> Any:
    """One closed surface as a shell of planar faces, a triangle each in order, its edges
    shared; an edge within the angular deflection coded G1."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeShapeOnMesh
    from OCP.GeomAbs import GeomAbs_G1
    from OCP.gp import gp_Pnt
    from OCP.Poly import Poly_Triangle, Poly_Triangulation
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS, TopoDS_Shell
    from OCP.collections import (IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher,
                                 IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher)

    used, local = np.unique(triangles, return_inverse=True)
    local = local.reshape(-1, 3)
    mesh = Poly_Triangulation(len(used), len(local), False)
    for at, point in enumerate(vertices[used].tolist(), 1):
        mesh.SetNode(at, gp_Pnt(*point))
    for at, (a, b, c) in enumerate((local + 1).tolist(), 1):
        mesh.SetTriangle(at, Poly_Triangle(a, b, c))
    maker = BRepBuilderAPI_MakeShapeOnMesh(mesh)
    maker.Build()
    faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(maker.Shape(), TopAbs_FACE, faces)
    if faces.Extent() != len(local):
        raise RuntimeError(f"OCCT made {faces.Extent()} faces of {len(local)} triangles: an engine error, never a field's")
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    for ordinal in range(1, faces.Extent() + 1):
        builder.Add(shell, faces.FindKey(ordinal))
    shell.Closed(True)
    a, b, c = (vertices[used][local[:, corner]] for corner in range(3))
    normals = np.cross(b - a, c - a)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    ancestors = IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapesAndAncestors_s(shell, TopAbs_EDGE, TopAbs_FACE, ancestors)
    pairs = []
    for ordinal in range(1, ancestors.Extent() + 1):
        around = ancestors.FindFromIndex(ordinal)
        pairs.append((faces.FindIndex(around.First()) - 1, faces.FindIndex(around.Last()) - 1))
    pairs = np.array(pairs, dtype=np.int64).reshape(-1, 2)
    smooth = (normals[pairs[:, 0]] * normals[pairs[:, 1]]).sum(axis=1) >= math.cos(ANGULAR)
    for ordinal in np.nonzero(smooth)[0].tolist():
        around = ancestors.FindFromIndex(ordinal + 1)
        builder.Continuity(TopoDS.Edge(ancestors.FindKey(ordinal + 1)), TopoDS.Face(around.First()),
                           TopoDS.Face(around.Last()), GeomAbs_G1)
    return shell

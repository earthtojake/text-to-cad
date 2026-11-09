"""The mesh a manufacturing check measures: read, made millimetres and cleaned for 3D printing
(``_printing``), the one process a mesh is checked for.

An STL is triangle soup: each triangle carries its own corners, and an exporter's tessellation leaves
triangles of no area where it collapsed a chord, and cracks no wider than its chord tolerance where two
faces' tessellations do not meet. Read as written, such a part is open and of several bodies, its volume
unknown and its cracks gaps. Cleaned:

- **welded**: corners at one place are one vertex (``merge_vertices``), so the triangles share edges;
- **collapsed triangles dropped**: a triangle two of whose corners became one vertex has no area and no
  edge of its own -- each of its edges is a neighbour's -- so dropping it never opens the shell (dropping a
  zero-area triangle of three distinct corners would: its edges are its neighbours' only partners);
- **slivers dropped**: a triangle of next to no area (``SLIVER_AREA`` of the diagonal squared) on an edge more
  than two triangles use -- an exporter's collapsed chord left doubled or fanned over an edge, its copies
  wound against each other -- is dropped where the edges it uses stay used twice (or not at all): never
  one that would leave an edge used once, which would open the shell;
- **zero-area pieces dropped**: a connected piece whose triangles hold no area is an exporter's debris,
  never a body;
- **folds laid flat**: two triangles side by side in one plane whose normals oppose (``FOLD_DOT``) are a fan
  the exporter folded back over itself (a fan from a far corner wrapping a hub's arc): each wound against its
  neighbours, it reads as a ceiling over its own face and a knife edge at the fold. The planar region the
  fold is in is triangulated again from its boundary -- the edges its triangles leave once their windings
  cancel -- so its triangles cover it once each, wound as the region faces; the boundary and every
  neighbour stay as they were, and a region that does not come out with the same area and boundary is left
  as read. A mesh with no fold is not changed;
- **cracks closed**: a hole in the surface whose boundary lies within ``CRACK_FRACTION`` of the part's
  diagonal of one straight line (a sliver the tessellation left open) is filled by a fan of triangles
  wound as its neighbours are. A wider hole is the part's own opening: it stays open, and the check says
  the mesh is not watertight.

Watertightness is judged per body (``closure``): which bodies are open, and the volume of the closed ones.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

__all__ = ["CRACK_FRACTION", "FOLD_DOT", "SLIVER_AREA", "clean", "closure", "facts", "load", "prepared"]

#: A boundary loop whose corners all lie within this fraction of the part's diagonal of the line through its
#: two farthest corners is a crack of the tessellation, not an opening: a chord tolerance's width (a 117 mm
#: plate's export left cracks 0.08 mm wide; its 6 mm holes' rims are far wider).
CRACK_FRACTION = 2e-3
#: A loop of more corners than this is no sliver crack.
CRACK_MAX_CORNERS = 64
#: A triangle under this share of the diagonal squared is a sliver (a 111 mm gear's 3MF: 1.7e-9 to 8.5e-9,
#: its smallest real triangle 3.2e-6).
SLIVER_AREA = 1e-8
#: Slivers joined by their edges are settled together while there are at most this many of them.
SLIVER_GROUP = 12
#: Two triangles sharing an edge whose normals' dot is under this, the far corner of each in the other's plane
#: (``FOLD_PLANE`` of the diagonal), are folded over each other: one plane, wound both ways.
FOLD_DOT = -0.999
FOLD_PLANE = 1e-5


def load(path: str, units: str = "mm") -> trimesh.Trimesh:
    """The mesh file at ``path`` (an STL), made millimetres and cleaned (``prepared``)."""
    mesh = trimesh.load(path, force="mesh", process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    return prepared(mesh, units)


def prepared(mesh: trimesh.Trimesh, units: str = "mm") -> trimesh.Trimesh:
    """``mesh`` (changed in place: hand it a copy) scaled from ``units`` to millimetres and cleaned."""
    from cad._internal.manufacturing import UNITS_MM

    if units not in UNITS_MM:
        raise ValueError(f"units is one of {', '.join(sorted(UNITS_MM))}, not {units!r}")
    factor = UNITS_MM[units]
    if factor != 1.0:
        mesh.apply_scale(factor)
    clean(mesh)
    mesh.metadata["source_units"] = units
    return mesh


def clean(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """``mesh`` welded, its collapsed triangles and zero-area pieces dropped and its cracks closed, in place
    (the module's docstring). What it did is in ``mesh.metadata``: ``degenerate_faces_dropped``,
    ``debris_faces_dropped``, ``folds_laid_flat`` (the planar regions triangulated again), ``cracks_closed``."""
    before = int(len(mesh.faces))
    mesh.merge_vertices()
    faces = np.asarray(mesh.faces)
    collapsed = (faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 0] == faces[:, 2])
    if collapsed.any():
        mesh.update_faces(~collapsed)
    slivers = _drop_slivers(mesh)
    debris = 0
    if len(mesh.faces):
        areas = np.asarray(mesh.area_faces)
        floor = 1e-9 * max(float(areas.sum()), 1.0)
        pieces = trimesh.graph.connected_components(mesh.face_adjacency, nodes=np.arange(len(mesh.faces)),
                                                    min_len=1)
        drop = np.zeros(len(mesh.faces), dtype=bool)
        for piece in pieces:
            piece = np.asarray(piece, dtype=int)
            if float(areas[piece].sum()) <= floor:
                drop[piece] = True
        debris = int(drop.sum())
        if debris:
            mesh.update_faces(~drop)
    mesh.remove_unreferenced_vertices()
    folds = _unfold(mesh)
    cracks = _close_cracks(mesh)
    mesh.metadata["folds_laid_flat"] = folds
    mesh.metadata["degenerate_faces_dropped"] = int(collapsed.sum()) + slivers
    mesh.metadata["debris_faces_dropped"] = debris
    mesh.metadata["cracks_closed"] = cracks
    mesh.metadata["faces_read"] = before
    return mesh


def _drop_slivers(mesh: trimesh.Trimesh) -> int:
    """Drop the slivers (``SLIVER_AREA``) on edges more than two triangles use, in place, where the drop leaves
    each edge they use run once each way or not at all; the number dropped. One at a time first, smallest
    first: a sliver each of whose edges more than two triangles use, another of them running it the sliver's
    way (recounted after each). Then each group of the rest joined by their edges, at most ``SLIVER_GROUP``:
    the most of it whose drop leaves every edge it uses run once each way or not at all."""
    faces = np.asarray(mesh.faces)
    if not len(faces):
        return 0
    diagonal = float(np.linalg.norm(mesh.extents)) or 1.0
    areas = np.asarray(mesh.area_faces)
    directed = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    _unique, inverse = np.unique(np.sort(directed, axis=1), axis=0, return_inverse=True)
    edges = inverse.ravel().reshape(3, -1).T  # per face, its three edges' indices
    ways = (directed[:, 0] < directed[:, 1]).reshape(3, -1).T  # per face, which way it runs each
    runs = np.zeros((int(edges.max()) + 1, 2), dtype=int)  # per edge, its uses each way
    np.add.at(runs, (edges.ravel(), ways.ravel().astype(int)), 1)
    total = runs.sum(axis=1)
    slivers = [int(i) for i in np.argsort(areas) if areas[i] < SLIVER_AREA * diagonal ** 2 and (total[edges[i]] > 2).any()]
    if not slivers:
        return 0
    keep = np.ones(len(faces), dtype=bool)

    def drop(face: int) -> None:
        keep[face] = False
        np.subtract.at(runs, (edges[face], ways[face].astype(int)), 1)

    changed = True
    while changed:
        changed = False
        for face in slivers:
            if keep[face] and (runs[edges[face]].sum(axis=1) > 2).all() and \
                    (runs[edges[face], ways[face].astype(int)] > 1).all():
                drop(face)
                changed = True
    left = [face for face in slivers if keep[face] and (runs[edges[face]].sum(axis=1) > 2).any()]
    if left:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components

        rows = np.repeat(np.arange(len(left)), 3)
        graph = coo_matrix((np.ones(len(rows)), (rows, len(left) + edges[left].ravel())),
                           shape=(len(left) + len(runs),) * 2)
        _n, labels = connected_components(graph, directed=False)
        for label in np.unique(labels[:len(left)]):
            group = [left[at] for at in np.flatnonzero(labels[:len(left)] == label)]
            if len(group) > SLIVER_GROUP:
                continue
            touched = np.unique(edges[group])
            best, most = 0, 0
            for chosen in range(1, 1 << len(group)):
                after = runs.copy()
                for at, face in enumerate(group):
                    if chosen >> at & 1:
                        np.subtract.at(after, (edges[face], ways[face].astype(int)), 1)
                left_runs = after[touched]
                if (left_runs[:, 0] == left_runs[:, 1]).all() and (left_runs[:, 0] <= 1).all() and \
                        bin(chosen).count("1") > most:
                    best, most = chosen, bin(chosen).count("1")
            for at, face in enumerate(group):
                if best >> at & 1:
                    drop(face)
    dropped = int((~keep).sum())
    if dropped:
        mesh.update_faces(keep)
    return dropped


def _unfold(mesh: trimesh.Trimesh) -> int:
    """Triangulate again, in place, each planar region holding a fold (``FOLD_DOT``): the number of regions."""
    if len(mesh.faces) < 2:
        return 0
    normals = np.asarray(mesh.face_normals)
    pairs = np.asarray(mesh.face_adjacency)
    if not len(pairs):
        return 0
    dots = np.einsum("ij,ij->i", normals[pairs[:, 0]], normals[pairs[:, 1]])
    candidates = np.flatnonzero(dots < FOLD_DOT)
    if not len(candidates):
        return 0
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces)
    tolerance = FOLD_PLANE * (float(np.linalg.norm(mesh.extents)) or 1.0)
    shared = np.asarray(mesh.face_adjacency_edges)
    unshared = np.asarray(mesh.face_adjacency_unshared)
    neighbours: dict[int, list[int]] = {}
    for a, b in pairs:
        neighbours.setdefault(int(a), []).append(int(b))
        neighbours.setdefault(int(b), []).append(int(a))
    done = np.zeros(len(faces), dtype=bool)
    replaced: list[tuple[np.ndarray, np.ndarray]] = []
    for k in candidates:
        a, b = (int(f) for f in pairs[k])
        if done[a] or done[b]:
            continue
        origin, normal = vertices[shared[k, 0]], normals[a]
        if abs(float((vertices[unshared[k, 1]] - origin) @ normal)) > tolerance:
            continue  # a knife edge's two flanks, not one plane
        region, frontier = {a, b}, [a, b]
        while frontier:
            face = frontier.pop()
            for other in neighbours.get(face, ()):
                if other in region or done[other] or abs(float(normals[other] @ normal)) < -FOLD_DOT:
                    continue
                if np.all(np.abs((vertices[faces[other]] - origin) @ normal) <= tolerance):
                    region.add(other)
                    frontier.append(other)
        chosen = np.fromiter(sorted(region), dtype=int)
        done[chosen] = True
        made = _flat(vertices, faces[chosen])
        if made is not None:
            replaced.append((chosen, made))
    if not replaced:
        return 0
    keep = np.ones(len(faces), dtype=bool)
    for chosen, _made in replaced:
        keep[chosen] = False
    mesh.faces = np.concatenate([faces[keep]] + [made.astype(faces.dtype) for _chosen, made in replaced])
    return len(replaced)


def _flat(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray | None:
    """The planar region ``triangles`` cover (counted with their windings) triangulated again from its
    boundary, wound as the region faces; None where its boundary is no set of simple loops or the new
    triangles do not cover the region's area once."""
    corners = vertices[triangles]
    area = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]).sum(axis=0) / 2.0
    size = float(np.linalg.norm(area))
    if not size > 0:
        return None
    normal = area / size
    net: dict[tuple[int, int], int] = {}
    for tri in triangles:
        for i, j in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key, way = ((int(i), int(j)), 1) if i < j else ((int(j), int(i)), -1)
            net[key] = net.get(key, 0) + way
    following: dict[int, int] = {}
    for (i, j), count in net.items():
        if count == 0:
            continue
        if abs(count) != 1:
            return None
        start, end = (i, j) if count == 1 else (j, i)
        if start in following:
            return None  # a corner two loops pass through
        following[start] = end
    loops: list[list[int]] = []
    seen: set[int] = set()
    for start in following:
        if start in seen:
            continue
        loop, at = [], start
        while at not in seen:
            seen.add(at)
            loop.append(at)
            at = following.get(at, -1)
            if at < 0:
                return None
        if at != start or len(loop) < 3:
            return None
        loops.append(loop)
    seed = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(normal, seed)
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    flat = np.stack([vertices @ u, vertices @ v], axis=1)

    def signed(loop: list[int]) -> float:
        p = flat[loop]
        return float((p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]).sum() / 2.0)

    outers = [loop for loop in loops if signed(loop) > 0]
    holes = [loop for loop in loops if signed(loop) <= 0]
    if not outers:
        return None
    owned: dict[int, list[list[int]]] = {k: [] for k in range(len(outers))}
    for hole in holes:
        point = flat[hole[0]]
        inside = [k for k, outer in enumerate(outers) if _contains(flat[outer], point)]
        if not inside:
            return None
        owned[min(inside, key=lambda k: abs(signed(outers[k])))].append(hole)
    made: list[list[int]] = []
    for k, outer in enumerate(outers):
        polygon = list(outer)
        for hole in sorted(owned[k], key=lambda h: -float(flat[h, 0].max())):
            polygon = _bridge(polygon, hole, flat)
            if polygon is None:
                return None
        clipped = _clip(polygon, flat)
        if clipped is None:
            return None
        made.extend(clipped)
    result = np.asarray(made, dtype=int).reshape(-1, 3)
    new = vertices[result]
    cross = np.cross(new[:, 1] - new[:, 0], new[:, 2] - new[:, 0]) @ normal / 2.0
    if (cross < -1e-9 * size).any() or abs(float(cross.sum()) - size) > 1e-6 * size:
        return None
    return result


def _contains(polygon: np.ndarray, point: np.ndarray) -> bool:
    """Whether ``point`` lies inside the 2D ``polygon`` (even-odd)."""
    x, y = float(point[0]), float(point[1])
    a, b = polygon, np.roll(polygon, -1, axis=0)
    crosses = (a[:, 1] > y) != (b[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        at = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    return bool((crosses & (x < at)).sum() % 2)


def _bridge(outer: list[int], hole: list[int], flat: np.ndarray) -> list[int] | None:
    """``outer`` (counter-clockwise) and ``hole`` (clockwise, inside it) as one loop, joined by a cut from the
    hole's rightmost corner to a corner of the outer loop it sees (Eberly's bridge)."""
    m = max(range(len(hole)), key=lambda k: (flat[hole[k], 0], -flat[hole[k], 1]))
    mx, my = flat[hole[m]]
    best, edge = math.inf, None
    for k in range(len(outer)):
        a, b = flat[outer[k]], flat[outer[(k + 1) % len(outer)]]
        if (a[1] > my) == (b[1] > my) and not (a[1] == my or b[1] == my):
            continue
        if a[1] == b[1]:
            x = min(a[0], b[0])
        else:
            x = a[0] + (my - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        if mx <= x < best:
            best, edge = x, k
    if edge is None:
        return None
    k0, k1 = edge, (edge + 1) % len(outer)
    pick = k0 if flat[outer[k0], 0] >= flat[outer[k1], 0] else k1
    hit = np.array([best, my])
    corner = flat[outer[pick]]
    # a corner of the outer loop inside the triangle (hole corner, hit, picked corner) is nearer the cut: the
    # one at the least angle to the ray is seen from the hole's corner
    tri = np.array([[mx, my], hit, corner])
    angle = math.inf
    for k, index in enumerate(outer):
        p = flat[index]
        if k == pick or p[0] < mx:
            continue
        if _in_triangle(p[None], *tri, strict=False)[0]:
            off = math.atan2(abs(p[1] - my), p[0] - mx)
            if off < angle or (off == angle and p[0] < flat[outer[pick], 0]):
                angle, pick = off, k
    # a corner an earlier bridge reached is in the loop twice or more: the cut leaves from the copy whose
    # wedge (between the loop's edges into and out of it) the cut runs into, or the loop crosses itself there
    copies = [k for k, index in enumerate(outer) if index == outer[pick]]
    if len(copies) > 1:
        corner = flat[outer[pick]]
        toward = float(np.arctan2(my - corner[1], mx - corner[0]))
        for k in copies:
            after, before = flat[outer[(k + 1) % len(outer)]], flat[outer[k - 1]]
            start = float(np.arctan2(after[1] - corner[1], after[0] - corner[0]))
            span = (float(np.arctan2(before[1] - corner[1], before[0] - corner[0])) - start) % (2 * math.pi)
            if 0.0 < (toward - start) % (2 * math.pi) < span:
                pick = k
                break
    return outer[:pick + 1] + hole[m:] + hole[:m + 1] + outer[pick:]


def _in_triangle(points: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray, strict: bool = True) -> np.ndarray:
    """Which ``points`` lie inside the triangle: strictly inside a counter-clockwise one, or (not ``strict``)
    inside or on either way round."""
    def side(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> np.ndarray:
        return (q[0] - p[0]) * (r[:, 1] - p[1]) - (q[1] - p[1]) * (r[:, 0] - p[0])

    s1, s2, s3 = side(a, b, points), side(b, c, points), side(c, a, points)
    if strict:
        return (s1 > 0) & (s2 > 0) & (s3 > 0)
    return ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))


def _cuts(points: np.ndarray, a: np.ndarray, c: np.ndarray, ends: tuple[int, int]) -> bool:
    """Whether the segment ``a``-``c`` crosses an edge of the loop ``points`` other than those at its two ends'
    positions: a corner a bridge reaches twice has edges a test of points alone does not see."""
    p, q = points, np.roll(points, -1, axis=0)

    def side(u: np.ndarray, w: np.ndarray, r: np.ndarray) -> np.ndarray:
        return np.sign((w[0] - u[0]) * (r[:, 1] - u[1]) - (w[1] - u[1]) * (r[:, 0] - u[0]))

    first = side(a, c, p) * side(a, c, q) < 0
    second = np.sign((q[:, 0] - p[:, 0]) * (a[1] - p[:, 1]) - (q[:, 1] - p[:, 1]) * (a[0] - p[:, 0])) * \
        np.sign((q[:, 0] - p[:, 0]) * (c[1] - p[:, 1]) - (q[:, 1] - p[:, 1]) * (c[0] - p[:, 0])) < 0
    crossing = first & second
    n = len(points)
    for end in ends:
        crossing[end] = crossing[(end - 1) % n] = False
    return bool(crossing.any())


def _clip(polygon: list[int], flat: np.ndarray) -> list[list[int]] | None:
    """A simple counter-clockwise loop (its corners may repeat where a bridge runs both ways) cut into
    triangles by ear clipping; None where no ear is left to cut."""
    ring = list(polygon)
    out: list[list[int]] = []
    at = 0
    while len(ring) > 3:
        n = len(ring)
        points = flat[ring]
        cut = False
        for collinear in (False, True):
            for step in range(n):
                k = (at + step) % n
                i0, i1, i2 = (k - 1) % n, k, (k + 1) % n
                a, b, c = points[i0], points[i1], points[i2]
                turn = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
                scale = max(float(np.abs(b - a).max()), float(np.abs(c - b).max()), 1e-300) ** 2
                if turn < -1e-12 * scale or (turn <= 1e-12 * scale and not collinear):
                    continue
                rest = np.ones(n, dtype=bool)
                rest[[i0, i1, i2]] = False
                corners = (np.all(points == a, axis=1) | np.all(points == b, axis=1) | np.all(points == c, axis=1))
                rest &= ~corners
                if turn > 1e-12 * scale and (_in_triangle(points[rest], a, b, c, strict=False).any()
                                             or _cuts(points, a, c, (i0, i2))):
                    continue
                out.append([ring[i0], ring[i1], ring[i2]])
                del ring[i1]
                at = i1 % len(ring)
                cut = True
                break
            if cut:
                break
        if not cut:
            return None
    out.append(list(ring))
    return out


def _close_cracks(mesh: trimesh.Trimesh) -> int:
    """Fill each boundary loop of ``mesh`` that is a crack (``CRACK_FRACTION``), wound as its neighbours;
    the number filled."""
    if not len(mesh.faces) or mesh.is_watertight:
        return 0
    faces = np.asarray(mesh.faces)
    directed = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    _unique, inverse, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    once = counts[inverse.ravel()] == 1
    if not once.any():
        return 0
    # The fill runs each boundary edge the other way from the face that holds it.
    nxt: dict[int, int] = {}
    shared: set[int] = set()  # a corner two loops share: no loop through it is a simple crack
    for a, b in directed[once]:
        if int(b) in nxt:
            shared.add(int(b))
        nxt[int(b)] = int(a)
    diagonal = float(np.linalg.norm(mesh.extents)) or 1.0
    tolerance = CRACK_FRACTION * diagonal
    vertices = np.asarray(mesh.vertices)
    added: list[list[int]] = []
    seen: set[int] = set()
    closed = 0
    for start in list(nxt):
        if start in seen or start in shared:
            continue
        loop = [start]
        seen.add(start)
        at = nxt[start]
        while at != start and at in nxt and at not in seen and at not in shared and len(loop) <= CRACK_MAX_CORNERS:
            loop.append(at)
            seen.add(at)
            at = nxt[at]
        if at != start or len(loop) < 3 or len(loop) > CRACK_MAX_CORNERS:
            continue
        if _width(vertices[loop]) > tolerance:
            continue
        added.extend([loop[0], loop[i], loop[i + 1]] for i in range(1, len(loop) - 1))
        closed += 1
    if added:
        mesh.faces = np.concatenate([faces, np.asarray(added, dtype=faces.dtype)])
    return closed


def _width(points: np.ndarray) -> float:
    """How far ``points`` lie at most from the line through their two farthest-apart."""
    gaps = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    i, j = np.unravel_index(int(np.argmax(gaps)), gaps.shape)
    span = points[j] - points[i]
    length = float(np.linalg.norm(span))
    if length == 0.0:
        return 0.0
    offsets = points - points[i]
    return float(np.max(np.linalg.norm(np.cross(offsets, span / length), axis=1)))


def closure(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """Watertightness judged per body: ``watertight`` (every body closed), ``open_body_count``,
    ``open_bodies`` (each open body's ``xyz``, its box's centre, ``boundary_edges`` and ``area_mm2``, at most
    8) and ``closed_volume_mm3`` (the closed bodies' volume, None where none is closed).

    A body is open where one of its edges is used an odd number of times in the whole mesh: a boundary. Two
    bodies sharing a face (a two-material print, two solids touching) use that face's edges four times, so
    each is closed, and the face's two copies, wound against each other, cancel in the volume. No repair:
    trimesh's would close an opening and hide it."""
    if mesh.is_watertight:
        return {"watertight": True, "open_body_count": 0, "open_bodies": [],
                "closed_volume_mm3": round(abs(float(mesh.volume)), 1)}
    faces = np.asarray(mesh.faces)
    if not len(faces):
        return {"watertight": False, "open_body_count": 0, "open_bodies": [], "closed_volume_mm3": None}
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _unique, inverse, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    odd = (counts[inverse.ravel()] % 2 == 1).reshape(3, -1).T  # per face, per edge
    pieces = trimesh.graph.connected_components(mesh.face_adjacency, nodes=np.arange(len(faces)), min_len=1)
    triangles = np.asarray(mesh.triangles, dtype=float)
    opened, closed_faces = [], []
    for piece in pieces:
        piece = np.asarray(piece, dtype=int)
        boundary = int(odd[piece].sum())
        if not boundary:
            closed_faces.append(piece)
            continue
        corners = triangles[piece].reshape(-1, 3)
        opened.append({"xyz": [round(float(v), 4) for v in (corners.min(axis=0) + corners.max(axis=0)) / 2],
                       "boundary_edges": boundary, "area_mm2": round(float(mesh.area_faces[piece].sum()), 3)})
    opened.sort(key=lambda item: -item["area_mm2"])
    volume = None
    if closed_faces:
        shut = triangles[np.concatenate(closed_faces)]
        volume = round(abs(float(np.einsum("ij,ij->i", shut[:, 0], np.cross(shut[:, 1], shut[:, 2])).sum()) / 6.0), 1)
    return {"watertight": not opened, "open_body_count": len(opened), "open_bodies": opened[:8],
            "closed_volume_mm3": volume}


def facts(mesh: trimesh.Trimesh) -> dict[str, Any]:
    """The mesh facts printing reports of its closure (``closure``): ``watertight``, ``volume_mm3`` (the
    closed bodies'), the open bodies where any is, and what cleaning it took."""
    closed = closure(mesh)
    found: dict[str, Any] = {"watertight": closed["watertight"], "volume_mm3": closed["closed_volume_mm3"]}
    if closed["open_body_count"]:
        found.update(open_body_count=closed["open_body_count"], open_bodies=closed["open_bodies"])
    for key in ("degenerate_faces_dropped", "folds_laid_flat", "cracks_closed"):
        if mesh.metadata.get(key):
            found[key] = int(mesh.metadata[key])
    return found

"""The mesh a manufacturing check measures: read, made millimetres and cleaned the one way both processes
measure it (``_molding``, ``_printing``).

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
- **cracks closed**: a hole in the surface whose boundary lies within ``CRACK_FRACTION`` of the part's
  diagonal of one straight line (a sliver the tessellation left open) is filled by a fan of triangles
  wound as its neighbours are. A wider hole is the part's own opening: it stays open, and the check says
  the mesh is not watertight.

Watertightness is judged per body (``closure``): which bodies are open, and the volume of the closed ones.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import trimesh

__all__ = ["CRACK_FRACTION", "SLIVER_AREA", "clean", "closure", "facts", "load", "prepared"]

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
    ``debris_faces_dropped``, ``cracks_closed``."""
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
    cracks = _close_cracks(mesh)
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
    for a, b in directed[once]:
        if int(b) in nxt:  # a corner two loops share: no simple crack
            return 0
        nxt[int(b)] = int(a)
    diagonal = float(np.linalg.norm(mesh.extents)) or 1.0
    tolerance = CRACK_FRACTION * diagonal
    vertices = np.asarray(mesh.vertices)
    added: list[list[int]] = []
    seen: set[int] = set()
    closed = 0
    for start in list(nxt):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        at = nxt[start]
        while at != start and at in nxt and at not in seen and len(loop) <= CRACK_MAX_CORNERS:
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
    """The mesh facts both processes report of its closure (``closure``): ``watertight``, ``volume_mm3`` (the
    closed bodies'), the open bodies where any is, and what cleaning it took."""
    closed = closure(mesh)
    found: dict[str, Any] = {"watertight": closed["watertight"], "volume_mm3": closed["closed_volume_mm3"]}
    if closed["open_body_count"]:
        found.update(open_body_count=closed["open_body_count"], open_bodies=closed["open_bodies"])
    for key in ("degenerate_faces_dropped", "cracks_closed"):
        if mesh.metadata.get(key):
            found[key] = int(mesh.metadata[key])
    return found

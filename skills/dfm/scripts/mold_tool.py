#!/usr/bin/env python3
"""Fact-only injection-molding geometry measurements for mesh files.

Reports measurements as JSON. It never emits pass/fail, verdicts, or
moldability statuses; comparisons against resin, texture and tooling limits
belong to the skill workflow using `references/injection-molding.md`.

Requires: trimesh, numpy, rtree (pip install -r requirements.txt)

Usage:
    python mold_tool.py measure <mesh> --pull z [--units mm] [--wall-limit 45] [--zero-tol 0.05]
    python mold_tool.py pulls <mesh> [--units mm] [--wall-limit 45] [--zero-tol 0.05]

`measure` reports three fact families for one pull axis: draft, undercut
candidates, and projection. `pulls` repeats the draft and undercut summaries
for x, y, z and the mesh's own principal axes. Wall thickness is NOT measured
here; use `$dfam-check`'s `measure` for it, and ignore its `max_mm`, which
reads a plate's length rather than its thickness.

Draft is measured per triangle as the angle between the face and the pull
axis: 0 means the face is parallel to the pull (no draft), 90 means it is
perpendicular to it (a top or bottom face). Faces at or above `--wall-limit`
from the pull axis are not counted as walls. Curved faces are read per facet,
so the reported draft of a cylinder or cone is the facet's draft, not an
analytic value, and a curved face merely TANGENT to the pull is reported apart
from a flat zero-draft wall because its area is a tessellation artifact.
Which mold half forms a face, whether a parting line makes it an undercut, and
side actions are not determined here. The undercut family is a straight-pull
occlusion test: a face whose withdrawal ray is blocked by the part itself is
reported as a candidate.

If a fact family fails, the report carries `"partial": true`, names the family
in `partial_sections`, and the command exits 2, so neither a JSON reader nor a
shell caller can take a partial report for a complete one.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import trimesh

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_BINS_DEG = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
#: Length units a mesh file may carry, as a factor to millimetres. STL, OBJ,
#: PLY and 3MF are unitless in practice, so the caller states which one.
_UNITS_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
#: The occlusion test casts one ray per triangle and counts the WHOLE triangle,
#: so a CAD-coarse mesh rounds an undercut to its nearest triangle. Faces are
#: split to at most this fraction of the bounding-box diagonal before casting.
_PROBE_EDGE_FRACTION = 1 / 150
#: and never past this many probe faces, so a big mesh stays measurable.
_PROBE_FACE_BUDGET = 200_000
#: The silhouette raster is sized to the part, not to a fixed millimetre count,
#: and capped, so a part exported in metres does not print 0.0 and a 2 m panel
#: does not allocate gigabytes.
_RASTER_CELLS_ACROSS = 2000
_RASTER_CELL_BUDGET = 8_000_000


def _load(path: str, units: str = "mm") -> trimesh.Trimesh:
    """Read a mesh, scale it to millimetres, and drop degenerate faces.

    A zero-area triangle -- build123d exports a couple on any sphere -- makes
    trimesh's face normal NaN, and a NaN then reaches the report as a bare
    `NaN` token that strict JSON parsers reject.
    """
    mesh = trimesh.load(path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    factor = _UNITS_MM[units]
    if factor != 1.0:
        mesh.apply_scale(factor)
    degenerate = int(len(mesh.faces)) - int(mesh.nondegenerate_faces().sum())
    if degenerate:
        mesh.update_faces(mesh.nondegenerate_faces())
    mesh.metadata["degenerate_faces_dropped"] = degenerate
    mesh.metadata["source_units"] = units
    return mesh


def _pull_vector(spec: str) -> np.ndarray:
    """`z`, `+z`, `-y`, or `x,y,z` components, normalised."""
    text = (spec or "").strip().lower()
    if not text:
        raise ValueError("pull is empty; give an axis name (z, -y) or three comma-separated components")
    sign = 1.0
    if text[:1] in "+-":
        sign = -1.0 if text[0] == "-" else 1.0
        text = text[1:]
    if not text:
        raise ValueError(f"pull has a sign and no axis, got {spec!r}")
    if text in _AXES:
        vec = np.array(_AXES[text], dtype=float) * sign
    else:
        try:
            parts = [float(v) for v in text.split(",")]
        except ValueError as exc:
            raise ValueError(f"pull must be an axis name or three comma-separated components, got {spec!r}") from exc
        if len(parts) != 3:
            raise ValueError(f"pull must be an axis name or three comma-separated components, got {spec!r}")
        vec = np.array(parts, dtype=float) * sign
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(norm) or norm == 0.0:
        raise ValueError("pull vector has zero length")
    return vec / norm


def _mesh_facts(mesh: trimesh.Trimesh) -> dict:
    facts = {
        "bbox_mm": [round(float(v), 2) for v in mesh.extents],
        "triangle_count": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "body_count": int(mesh.body_count),
        "surface_area_mm2": round(float(mesh.area), 1),
        "volume_mm3": round(float(abs(mesh.volume)), 1) if mesh.is_volume else None,
        "source_units": mesh.metadata.get("source_units", "mm"),
    }
    dropped = int(mesh.metadata.get("degenerate_faces_dropped", 0))
    if dropped:
        facts["degenerate_faces_dropped"] = dropped
    if facts["body_count"] > 1:
        facts["note"] = (
            f"{facts['body_count']} separate bodies: this file is an assembly or a split export, "
            "not one molded part. Each family is measured per body; nothing here treats one body "
            "as an obstruction for another."
        )
    return facts


def _bulk(groups: list, coverage: float = 0.95) -> list:
    """The largest pooled faces that together cover `coverage` of the area.

    The tail this drops is the sliver tail: single facets at the tip of a
    fillet or along a chamfer, whose area and angle are properties of the
    export, not of the part.
    """
    ranked = sorted(groups, key=lambda g: -g["area_mm2"])
    total = sum(g["area_mm2"] for g in ranked)
    kept: list = []
    accumulated = 0.0
    for group in ranked:
        kept.append(group)
        accumulated += group["area_mm2"]
        if total and accumulated >= coverage * total:
            break
    return kept or ranked


def _tangent_faces(mesh: trimesh.Trimesh, along: np.ndarray, zero_tol: float,
                   smooth_deg: float = 45.0) -> np.ndarray:
    """Per face: is it a facet on a curved face that is merely TANGENT to the pull?

    A sphere is parallel to the pull along a LINE, and a tessellation turns
    that line into a band of facets whose area is a property of the export --
    261 mm2 coarse, 67 mm2 fine, for the same sphere. A cylinder's wall, by
    contrast, is parallel to the pull over its whole area and is a real
    zero-draft wall.

    What separates them is what the surface does on either side: at a tangent
    line it passes THROUGH parallel, so the face has smoothly-joined
    neighbours leaning both ways. Across a sharp edge (a box corner, a cap)
    the surface is a different face, so only smooth joins are followed.
    """
    tangent = np.zeros(len(mesh.faces), dtype=bool)
    adjacency = mesh.face_adjacency
    if not len(adjacency):
        return tangent
    smooth = np.degrees(mesh.face_adjacency_angles) < smooth_deg
    pairs = adjacency[smooth]
    if not len(pairs):
        return tangent
    tol = float(np.sin(np.radians(zero_tol)))
    left, right = pairs[:, 0], pairs[:, 1]
    above = np.zeros(len(mesh.faces), dtype=bool)
    below = np.zeros(len(mesh.faces), dtype=bool)
    np.logical_or.at(above, left, along[right] > tol)
    np.logical_or.at(above, right, along[left] > tol)
    np.logical_or.at(below, left, along[right] < -tol)
    np.logical_or.at(below, right, along[left] < -tol)
    # A tangent band can be two triangles wide -- a uv sphere's equator quad is
    # one coplanar pair, and each triangle of it sees only one side. Coplanar
    # neighbours are one face of the model, so they share the verdict.
    for facet in mesh.facets:
        if len(facet) < 2:
            continue
        if above[facet].any():
            above[facet] = True
        if below[facet].any():
            below[facet] = True
    return above & below


def _draft_facts(mesh: trimesh.Trimesh, pull: np.ndarray, wall_limit: float, zero_tol: float) -> dict:
    """Per-face draft relative to one pull axis, pooled over wall faces."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    centers = mesh.triangles_center

    along = normals @ pull
    # Rounded to the three decimals the report prints, so a wall built at
    # 2.000 deg that reads 1.99999 bins as 2-3deg like its printed value.
    draft = np.round(np.degrees(np.arcsin(np.clip(np.abs(along), 0.0, 1.0))), 3)
    walls = draft < wall_limit
    total_area = float(areas.sum())
    wall_area = float(areas[walls].sum())

    hist = {}
    edges = _BINS_DEG + [wall_limit]
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi <= lo:
            continue
        sel = walls & (draft >= lo) & (draft < hi)
        area = float(areas[sel].sum())
        if area > 0:
            hist[f"{lo:g}-{hi:g}deg"] = round(area, 2)

    zero = walls & (draft < zero_tol)
    tangent = _tangent_faces(mesh, along, zero_tol)
    flat_zero = zero & ~tangent
    tangent_zero = zero & tangent
    zero_groups = _pooled_faces(mesh, flat_zero, pull, along)
    drafted = walls & ~zero
    drafted_area = float(areas[drafted].sum())
    drafted_mean = float((draft[drafted] * areas[drafted]).sum() / drafted_area) if drafted_area else None

    # Which way each wall opens, by area. A part whose walls open both ways
    # along one pull needs two mold halves to release them, and that split is
    # not visible from a per-face listing.
    opening = {}
    for label, sel in (("+pull", walls & (along > 0) & ~zero),
                       ("-pull", walls & (along < 0) & ~zero),
                       ("none", zero)):
        opening[label] = round(float(areas[sel].sum()), 2)

    result = {
        "pull_axis": [round(float(v), 4) for v in pull],
        "wall_limit_deg": wall_limit,
        "zero_tol_deg": zero_tol,
        "wall_area_mm2": round(wall_area, 2),
        "wall_area_pct_of_surface": round(100 * wall_area / total_area, 1) if total_area else 0.0,
        "non_wall_area_mm2": round(total_area - wall_area, 2),
        "wall_draft_histogram_mm2": hist,
        "wall_area_by_opening_mm2": opening,
        "zero_draft_wall_area_mm2": round(float(areas[flat_zero].sum()), 2),
        "zero_draft_face_count": int(flat_zero.sum()),
        "zero_draft_tangent_area_mm2": round(float(areas[tangent_zero].sum()), 2),
        "zero_draft_tangent_note": (
            "facets on a CURVED face that happens to run parallel to the pull. A curved face is "
            "tangent to the pull along a line, not over an area, so this figure scales with the "
            "tessellation and is not a zero-draft wall."
        ),
        "drafted_wall_area_mm2": round(drafted_area, 2),
        "drafted_wall_mean_draft_deg": round(drafted_mean, 3) if drafted_mean is not None else None,
        "largest_zero_draft_faces": zero_groups,
        "method": (
            "per-triangle angle to the pull axis; curved faces read per facet; "
            "faces at or above wall_limit_deg from the pull are not walls"
        ),
    }
    if walls.any():
        pooled = _pooled_faces(mesh, walls, pull, along, limit=None, draft=draft)
        # The lowest draft over POOLED faces, ignoring the sliver tail. Read
        # from one triangle the figure moves with the mesh -- an injection tray
        # read 0.97 deg on one export and 0.60 on another, both off 0.05 mm2
        # facets. Pooling by normal and dropping the smallest faces that
        # together make up 5% of the wall area leaves the walls a mold sees.
        bulk = _bulk(pooled)
        floor = max(1.0, 0.001 * float(mesh.area))
        # Both filters: the coverage set drops the fragmented tail, the floor
        # drops a sliver that is large enough to survive it -- a corner blend's
        # 0.07 mm2 patch read 1.3 deg on a wall built at 2. On a body with no
        # face above the floor at all (a finely tessellated sphere) the
        # coverage set stands alone, and near-zero is then the honest answer.
        significant = [g for g in bulk if g["area_mm2"] >= floor] or bulk
        worst = min(significant, key=lambda g: g["draft_deg"])
        result["min_wall_draft"] = {
            "draft_deg": worst["draft_deg"],
            "area_mm2": worst["area_mm2"],
            "location_xyz": worst["centroid_xyz"],
            "opens_toward": worst["opens_toward"],
            "method": (f"area-weighted over faces pooled by normal, over the largest 95% of wall "
                           f"area and above {round(floor, 2)} mm2"),
        }
        i = int(np.argmin(np.where(walls, draft, np.inf)))
        result["min_facet_draft"] = {
            "draft_deg": round(float(draft[i]), 3),
            "area_mm2": round(float(areas[i]), 4),
            "location_xyz": [round(float(v), 2) for v in centers[i]],
            "note": "one triangle; use min_wall_draft for a figure that does not move with the mesh",
        }
        result["lowest_draft_wall_faces"] = [
            {"draft_deg": g["draft_deg"], "area_mm2": g["area_mm2"],
             "location_xyz": g["centroid_xyz"], "opens_toward": g["opens_toward"]}
            for g in sorted(pooled, key=lambda g: g["draft_deg"])[:8]
        ]
    else:
        result["note"] = "no wall faces below wall_limit_deg for this pull axis"
    return result


def _opens(along: float, zero_tol: float) -> str:
    """Which way a face's outward normal leans along the pull axis.

    A wall that leans toward +pull is formed by, and released from, the mold
    half on that side only if the parting line puts it there. This is the
    lean, not the mold assignment.
    """
    if abs(np.degrees(np.arcsin(min(abs(float(along)), 1.0)))) < zero_tol:
        return "none"
    return "+pull" if along > 0 else "-pull"


def _pooled_faces(mesh: trimesh.Trimesh, sel: np.ndarray, pull: np.ndarray, along: np.ndarray,
                  limit: int | None = 8, draft: np.ndarray | None = None) -> list:
    """Pool selected triangles that share a normal into one reported face.

    Triangles of one planar wall share a normal, so pooling by rounded normal
    reports the wall once with its total area. Two parallel walls facing the
    same way (a rib and a boss side, say) pool together as well; the pooled
    extent along the pull axis and the centroid are reported so the agent can
    tell one face from several.
    """
    if not sel.any():
        return []
    normals = mesh.face_normals[sel]
    areas = mesh.area_faces[sel]
    centers = mesh.triangles_center[sel]
    leans = along[sel]
    drafts = draft[sel] if draft is not None else np.zeros(len(areas))
    vertex_heights = mesh.triangles[sel] @ pull  # (n, 3): each corner along the pull
    keys = np.round(normals, 3)
    groups: dict = {}
    for k, a, c, hs, lean, dg in zip(map(tuple, keys), areas, centers, vertex_heights, leans, drafts):
        g = groups.setdefault(k, {"area": 0.0, "moment": np.zeros(3), "hmin": np.inf, "hmax": -np.inf,
                                  "count": 0, "lean": float(lean), "draft": 0.0})
        g["area"] += float(a)
        g["moment"] += c * float(a)
        g["hmin"] = min(g["hmin"], float(hs.min()))
        g["hmax"] = max(g["hmax"], float(hs.max()))
        g["draft"] += float(dg) * float(a)
        g["count"] += 1
    ranked = sorted(groups.items(), key=lambda kv: -kv[1]["area"])
    if limit is not None:
        ranked = ranked[:limit]
    return [
        {
            "normal": [round(float(v), 3) for v in k],
            "area_mm2": round(g["area"], 2),
            "centroid_xyz": [round(float(v), 2) for v in (g["moment"] / g["area"])],
            "extent_along_pull_mm": round(g["hmax"] - g["hmin"], 2),
            "triangle_count": int(g["count"]),
            "draft_deg": round(g["draft"] / g["area"], 3) if g["area"] else 0.0,
            "opens_toward": _opens(g["lean"], 0.05),
        }
        for k, g in ranked
    ]


def _scale_hint(mesh: trimesh.Trimesh) -> dict:
    """Flag meshes whose declared units are probably not the real ones."""
    diag = float(np.linalg.norm(mesh.extents))
    units = mesh.metadata.get("source_units", "mm")
    suspect = bool(np.isfinite(diag) and (diag < 1.0 or diag > 5_000.0))
    if suspect:
        note = (
            f"read as {units}, giving a {round(diag, 3)} mm bounding-box diagonal, which is outside "
            "the range of an injection-molded part. Pass --units with the file's real units."
        )
    else:
        note = f"read as {units}; bounding box consistent with an injection-molded part"
    return {
        "declared_units": units,
        "bbox_diagonal_mm": round(diag, 4),
        "units_suspect": suspect,
        "note": note,
    }


def _probe_mesh(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, float]:
    """The mesh split fine enough that one ray per triangle resolves a feature.

    The occlusion test counts a whole triangle as blocked or free, so on a
    CAD-coarse export a shelf over a plate is rounded to the plate's two
    triangles. Splitting to a maximum edge first makes the counted area follow
    the feature instead of the tessellation; the rays are still cast against
    the original mesh, whose surface is identical.
    """
    diag = float(np.linalg.norm(mesh.extents))
    if not np.isfinite(diag) or diag <= 0 or not len(mesh.faces):
        return mesh, 0.0
    triangles = mesh.triangles
    longest = np.linalg.norm(triangles - np.roll(triangles, 1, axis=1), axis=2).max(axis=1)

    def output_faces(edge: float) -> float:
        # subdivide_to_size quarters a face per pass, so a face needs
        # ceil(log2(longest / edge)) passes and becomes 4 to that power.
        passes = np.ceil(np.log2(np.maximum(longest / edge, 1.0)))
        return float(np.power(4.0, passes).sum())

    edge = diag * _PROBE_EDGE_FRACTION
    # Coarsen until the split mesh is one a ray cast per face can finish on.
    for _ in range(16):
        if edge <= 0 or not np.isfinite(edge) or output_faces(edge) <= _PROBE_FACE_BUDGET:
            break
        edge *= 2.0
    if edge <= 0 or not np.isfinite(edge):
        return mesh, 0.0
    probe = mesh.subdivide_to_size(edge)
    return probe, edge


def _undercut_facts(mesh: trimesh.Trimesh, pull: np.ndarray, zero_tol: float) -> dict:
    """Straight-pull occlusion test for every face.

    A face whose outward normal leans toward +pull is formed by the mold half
    that withdraws toward +pull, so a ray from that face along +pull must
    leave the part without hitting it again. A face leaning toward -pull is
    tested along -pull. A zero-draft wall belongs to either half, so it is a
    candidate only when BOTH directions are blocked (a trapped slot). Blocked
    faces are undercut candidates for a straight two-half tool: a side action,
    a different parting line, or a different pull may still resolve them, and
    that judgement is not made here.

    A file with several bodies is an assembly, not one molded part, so each
    body is tested against ITSELF. A lid sitting over a base is not an
    undercut in the base.
    """
    bodies = mesh.split(only_watertight=False) if mesh.body_count > 1 else [mesh]
    if not len(bodies):
        bodies = [mesh]
    per_body = []
    total_candidate = 0.0
    total_leaning = 0.0
    total_trapped = 0.0
    total_area = 0.0
    total_faces = 0
    pooled: list = []
    probe_edge = 0.0
    for index, body in enumerate(bodies):
        probe, probe_edge = _probe_mesh(body)
        normals = probe.face_normals
        areas = probe.area_faces
        centers = probe.triangles_center
        along = normals @ pull
        lean_deg = np.degrees(np.arcsin(np.clip(np.abs(along), 0.0, 1.0)))
        zero = lean_deg < zero_tol
        eps = 1e-3 * max(float(np.linalg.norm(body.extents)), 1.0)

        def blocked(direction_sign: np.ndarray, sel: np.ndarray) -> np.ndarray:
            out = np.zeros(len(centers), dtype=bool)
            if not sel.any():
                return out
            idx = np.where(sel)[0]
            dirs = np.outer(direction_sign[idx], pull)
            origins = centers[idx] + normals[idx] * eps + dirs * eps
            out[idx] = body.ray.intersects_any(ray_origins=origins, ray_directions=dirs)
            return out

        leaning = ~zero
        sign = np.where(along >= 0, 1.0, -1.0)
        blocked_lean = blocked(sign, leaning)
        blocked_plus = blocked(np.ones(len(centers)), zero)
        blocked_minus = blocked(-np.ones(len(centers)), zero)
        trapped = zero & blocked_plus & blocked_minus
        candidates = blocked_lean | trapped
        body_area = float(areas.sum())
        total_area += body_area
        total_candidate += float(areas[candidates].sum())
        total_leaning += float(areas[blocked_lean].sum())
        total_trapped += float(areas[trapped].sum())
        total_faces += int(candidates.sum())
        pooled += _pooled_faces(probe, candidates, pull, along)
        per_body.append({
            "body": index,
            "candidate_area_mm2": round(float(areas[candidates].sum()), 2),
            "surface_area_mm2": round(body_area, 2),
        })
    result = {
        "pull_axis": [round(float(v), 4) for v in pull],
        "method": (
            "straight two-half pull; faces split to at most "
            f"{round(probe_edge, 3)} mm before casting; ray from each face along its withdrawal "
            "direction; zero-draft walls need both directions blocked; each connected body is "
            "tested against itself"
        ),
        "candidate_area_mm2": round(total_candidate, 2),
        "candidate_area_pct_of_surface": round(100 * total_candidate / total_area, 2) if total_area else 0.0,
        "candidate_face_count": total_faces,
        "leaning_blocked_area_mm2": round(total_leaning, 2),
        "trapped_zero_draft_area_mm2": round(total_trapped, 2),
        "largest_candidate_faces": sorted(pooled, key=lambda g: -g["area_mm2"])[:8],
    }
    if len(bodies) > 1:
        result["body_count"] = len(bodies)
        result["per_body"] = per_body
        result["note"] = (
            "several bodies: measured per body. An assembly STL is not one molded part, and no "
            "body shadows another here."
        )
    return result


def _projection_facts(mesh: trimesh.Trimesh, pull: np.ndarray) -> dict:
    """Silhouette area along the pull, rasterised on a grid.

    Front-facing area over-counts wherever features overlap in projection,
    so the silhouette is rasterised instead. The raster is sized to the part
    rather than fixed in millimetres -- a fixed 0.25 mm grid prints 0.0 for a
    part exported in metres and allocates gigabytes for a 2 m panel -- and
    capped, so the reported resolution is what to read the figure against.
    """
    p = pull / np.linalg.norm(pull)
    helper = np.array([1.0, 0.0, 0.0]) if abs(p[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(p, helper); u /= np.linalg.norm(u)
    v = np.cross(p, u)
    pts = mesh.vertices @ np.stack([u, v], axis=1)
    span = pts.max(axis=0) - pts.min(axis=0)
    resolution_mm = float(max(span.max(), 1e-9)) / _RASTER_CELLS_ACROSS
    lo = pts.min(axis=0) - resolution_mm
    hi = pts.max(axis=0) + resolution_mm
    size = np.maximum(np.ceil((hi - lo) / resolution_mm).astype(int), 1)
    if size.prod() > _RASTER_CELL_BUDGET:
        resolution_mm = float(np.sqrt((hi - lo).prod() / _RASTER_CELL_BUDGET))
        size = np.maximum(np.ceil((hi - lo) / resolution_mm).astype(int), 1)
    grid = np.zeros((size[1], size[0]), dtype=bool)
    tri = (pts[mesh.faces] - lo) / resolution_mm
    for a, b, c in tri:
        x0 = max(0, int(np.floor(min(a[0], b[0], c[0])))); x1 = min(size[0] - 1, int(np.ceil(max(a[0], b[0], c[0]))))
        y0 = max(0, int(np.floor(min(a[1], b[1], c[1])))); y1 = min(size[1] - 1, int(np.ceil(max(a[1], b[1], c[1]))))
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12 or x1 < x0 or y1 < y0:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        xx = xx + 0.5; yy = yy + 0.5
        w0 = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / den
        w1 = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / den
        w2 = 1 - w0 - w1
        grid[y0:y1 + 1, x0:x1 + 1] |= (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
    heights = mesh.vertices @ p
    return {
        "pull_axis": [round(float(v), 4) for v in p],
        "projected_area_mm2": round(float(grid.sum()) * resolution_mm ** 2, 1),
        "raster_resolution_mm": round(resolution_mm, 6),
        "depth_along_pull_mm": round(float(heights.max() - heights.min()), 3),
        "volume_mm3": round(float(abs(mesh.volume)), 1) if mesh.is_volume else None,
    }


def _pull_candidates(mesh: trimesh.Trimesh) -> list[tuple[str, np.ndarray]]:
    """The three axes, plus the mesh's own principal axes.

    A part modelled off-axis has no good pull among x, y and z, and reading a
    2 degree draft as 12 under `--pull z` looks like a measurement, not a
    mismatch. Its principal axes are where its own draft was built.
    """
    candidates = [(name, np.array(axis, dtype=float)) for name, axis in _AXES.items()]
    try:
        vectors = np.asarray(mesh.principal_inertia_vectors, dtype=float)
    except Exception:  # noqa: BLE001 - a degenerate mesh has no inertia frame
        return candidates
    for index, vector in enumerate(vectors):
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm == 0.0:
            continue
        unit = vector / norm
        # Skip one that is already an axis to within a degree.
        if any(abs(abs(float(unit @ axis)) - 1.0) < 1.5e-4 for _name, axis in candidates[:3]):
            continue
        candidates.append((f"principal{index}", unit))
    return candidates


def _pull_facts(mesh: trimesh.Trimesh, wall_limit: float, zero_tol: float) -> dict:
    """Draft pooled for each candidate pull.

    Draft magnitude does not change when the pull flips sign (only the lean
    does), so +x and -x are one candidate.
    """
    candidates = []
    for name, axis in _pull_candidates(mesh):
        facts = _draft_facts(mesh, axis, wall_limit, zero_tol)
        undercuts = _safe(_undercut_facts, mesh, axis, zero_tol)
        candidates.append({
            "pull": name,
            "axis": [round(float(v), 4) for v in axis],
            "undercut_candidate_area_mm2": undercuts.get("candidate_area_mm2"),
            "wall_area_mm2": facts["wall_area_mm2"],
            "zero_draft_wall_area_mm2": facts["zero_draft_wall_area_mm2"],
            "wall_area_below_1deg_mm2": round(sum(
                v for k, v in facts["wall_draft_histogram_mm2"].items()
                if float(k.split("-")[1].rstrip("deg")) <= 1.0), 2),
            "min_wall_draft_deg": facts.get("min_wall_draft", {}).get("draft_deg"),
        })
    return {
        "wall_limit_deg": wall_limit,
        "zero_tol_deg": zero_tol,
        "note": (
            "draft magnitude is the same for +axis and -axis pulls; the lean direction differs. "
            "principal* are the mesh's own principal axes: when a part was modelled off-axis, its "
            "draft was built about one of those, not about x, y or z."
        ),
        "candidates": candidates,
    }


def _safe(fn, *args) -> dict:
    """Run one fact family, degrading to an error field instead of a traceback."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - report it, never propagate
        detail = f"{type(exc).__name__}: {exc}".splitlines()[0]
        return {"error": detail[:300]}


def _mark_partial(report: dict) -> bool:
    """Flag a report whose families did not all measure.

    A family that failed leaves an `error` field where its facts should be.
    Without this, the report reads as complete and the command exits 0, so a
    dead family becomes a silent "no findings".
    """
    failed = sorted(key for key, value in report.items()
                    if isinstance(value, dict) and "error" in value)
    report["partial"] = bool(failed)
    if failed:
        report["partial_sections"] = failed
    return bool(failed)


def _normalise_argv(argv: list[str]) -> list[str]:
    """Let `--pull -z` through argparse, which reads `-z` as an option."""
    out: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--pull" and index + 1 < len(argv) and argv[index + 1].startswith("-"):
            out.append(f"--pull={argv[index + 1]}")
            index += 2
            continue
        out.append(token)
        index += 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("measure", help="draft, undercut and projection facts for one pull axis")
    m.add_argument("mesh")
    m.add_argument("--pull", default="z", help="axis name (z, -y, or --pull=-z) or x,y,z components")
    m.add_argument("--units", default="mm", choices=sorted(_UNITS_MM), help="the mesh file's length units")
    m.add_argument("--wall-limit", type=float, default=45.0)
    m.add_argument("--zero-tol", type=float, default=0.05)

    p = sub.add_parser("pulls", help="draft and undercut summaries for x, y, z and the principal axes")
    p.add_argument("mesh")
    p.add_argument("--units", default="mm", choices=sorted(_UNITS_MM), help="the mesh file's length units")
    p.add_argument("--wall-limit", type=float, default=45.0)
    p.add_argument("--zero-tol", type=float, default=0.05)

    args = ap.parse_args(_normalise_argv(list(sys.argv[1:] if argv is None else argv)))

    try:
        mesh = _load(args.mesh, args.units)
    except Exception as e:
        print(json.dumps({"error": f"failed to load mesh: {e}"}))
        return 1

    if args.command == "measure":
        try:
            pull = _pull_vector(args.pull)
        except ValueError as e:
            print(json.dumps({"error": str(e)}))
            return 1
        report = {
            "file": args.mesh,
            "mesh": _safe(_mesh_facts, mesh),
            "scale": _safe(_scale_hint, mesh),
            "draft": _safe(_draft_facts, mesh, pull, args.wall_limit, args.zero_tol),
            "undercuts": _safe(_undercut_facts, mesh, pull, args.zero_tol),
            "projection": _safe(_projection_facts, mesh, pull),
        }
    else:
        report = {
            "file": args.mesh,
            "mesh": _safe(_mesh_facts, mesh),
            "scale": _safe(_scale_hint, mesh),
            "pulls": _safe(_pull_facts, mesh, args.wall_limit, args.zero_tol),
        }

    partial = _mark_partial(report)
    # allow_nan=False: a NaN is not JSON, and a report a parser rejects is worse
    # than one that says it failed.
    print(json.dumps(report, indent=2, allow_nan=False))
    return 2 if partial else 0


if __name__ == "__main__":
    sys.exit(main())

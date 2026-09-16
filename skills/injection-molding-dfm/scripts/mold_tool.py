#!/usr/bin/env python3
"""Fact-only injection-molding geometry measurements for mesh files.

Reports measurements as JSON. It never emits pass/fail, verdicts, or
moldability statuses; comparisons against resin, texture and tooling limits
belong to the skill workflow using `references/process-review.md`.

Requires: trimesh, numpy, rtree (pip install -r requirements.txt)

Usage:
    python mold_tool.py measure <mesh> --pull z [--samples 2000] [--wall-limit 45] [--zero-tol 0.05]
    python mold_tool.py pulls <mesh> [--wall-limit 45] [--zero-tol 0.05]

`measure` reports four fact families for one pull axis: draft, wall thickness,
undercut candidates, and projection. `pulls` repeats the draft and undercut
summaries for x, y and z pulls.

Draft is measured per triangle as the angle between the face and the pull
axis: 0 means the face is parallel to the pull (no draft), 90 means it is
perpendicular to it (a top or bottom face). Faces at or above `--wall-limit`
from the pull axis are not counted as walls. Curved faces are read per facet,
so the reported draft of a cylinder or cone is the facet's draft, not an
analytic value. Which mold half forms a face, whether a parting line makes it
an undercut for a given parting line, and side actions are not determined
here. The undercut family is a straight-pull occlusion test: a face whose
withdrawal ray is blocked by the part itself is reported as a candidate.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import trimesh

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_BINS_DEG = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]


def _load(path: str) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    return mesh


def _pull_vector(spec: str) -> np.ndarray:
    """`z`, `+z`, `-y`, or `x,y,z` components, normalised."""
    text = spec.strip().lower()
    sign = 1.0
    if text[:1] in "+-":
        sign = -1.0 if text[0] == "-" else 1.0
        text = text[1:]
    if text in _AXES:
        vec = np.array(_AXES[text], dtype=float) * sign
    else:
        parts = [float(v) for v in text.split(",")]
        if len(parts) != 3:
            raise ValueError(f"pull must be an axis name or three comma-separated components, got {spec!r}")
        vec = np.array(parts, dtype=float) * sign
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(norm) or norm == 0.0:
        raise ValueError("pull vector has zero length")
    return vec / norm


def _mesh_facts(mesh: trimesh.Trimesh) -> dict:
    return {
        "bbox_mm": [round(float(v), 2) for v in mesh.extents],
        "triangle_count": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "body_count": int(mesh.body_count),
        "surface_area_mm2": round(float(mesh.area), 1),
        "volume_mm3": round(float(abs(mesh.volume)), 1) if mesh.is_volume else None,
    }


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
    zero_groups = _pooled_faces(mesh, zero, pull, along)
    drafted = walls & ~zero
    drafted_area = float(areas[drafted].sum())
    drafted_mean = float((draft[drafted] * areas[drafted]).sum() / drafted_area) if drafted_area else None

    result = {
        "pull_axis": [round(float(v), 4) for v in pull],
        "wall_limit_deg": wall_limit,
        "zero_tol_deg": zero_tol,
        "wall_area_mm2": round(wall_area, 2),
        "wall_area_pct_of_surface": round(100 * wall_area / total_area, 1) if total_area else 0.0,
        "non_wall_area_mm2": round(total_area - wall_area, 2),
        "wall_draft_histogram_mm2": hist,
        "zero_draft_wall_area_mm2": round(float(areas[zero].sum()), 2),
        "zero_draft_face_count": int(zero.sum()),
        "drafted_wall_area_mm2": round(drafted_area, 2),
        "drafted_wall_mean_draft_deg": round(drafted_mean, 3) if drafted_mean is not None else None,
        "largest_zero_draft_faces": zero_groups,
        "method": (
            "per-triangle angle to the pull axis; curved faces read per facet; "
            "faces at or above wall_limit_deg from the pull are not walls"
        ),
    }
    if walls.any():
        i = int(np.argmin(np.where(walls, draft, np.inf)))
        result["min_wall_draft"] = {
            "draft_deg": round(float(draft[i]), 3),
            "location_xyz": [round(float(v), 2) for v in centers[i]],
            "opens_toward": _opens(along[i], zero_tol),
        }
        ranked = np.argsort(np.where(walls, draft, np.inf))
        result["lowest_draft_wall_faces"] = [
            {
                "draft_deg": round(float(draft[j]), 3),
                "area_mm2": round(float(areas[j]), 2),
                "location_xyz": [round(float(v), 2) for v in centers[j]],
                "opens_toward": _opens(along[j], zero_tol),
            }
            for j in ranked[:8]
            if walls[j]
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


def _pooled_faces(mesh: trimesh.Trimesh, sel: np.ndarray, pull: np.ndarray, along: np.ndarray) -> list:
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
    vertex_heights = mesh.triangles[sel] @ pull  # (n, 3): each corner along the pull
    keys = np.round(normals, 3)
    groups: dict = {}
    for k, a, c, hs in zip(map(tuple, keys), areas, centers, vertex_heights):
        g = groups.setdefault(k, {"area": 0.0, "moment": np.zeros(3), "hmin": np.inf, "hmax": -np.inf, "count": 0})
        g["area"] += float(a)
        g["moment"] += c * float(a)
        g["hmin"] = min(g["hmin"], float(hs.min()))
        g["hmax"] = max(g["hmax"], float(hs.max()))
        g["count"] += 1
    ranked = sorted(groups.items(), key=lambda kv: -kv[1]["area"])[:8]
    return [
        {
            "normal": [round(float(v), 3) for v in k],
            "area_mm2": round(g["area"], 2),
            "centroid_xyz": [round(float(v), 2) for v in (g["moment"] / g["area"])],
            "extent_along_pull_mm": round(g["hmax"] - g["hmin"], 2),
            "triangle_count": int(g["count"]),
        }
        for k, g in ranked
    ]


def _scale_hint(mesh: trimesh.Trimesh) -> dict:
    """Flag meshes whose units are probably not millimetres."""
    diag = float(np.linalg.norm(mesh.extents))
    suspect = bool(np.isfinite(diag) and diag < 1.0)
    return {
        "bbox_diagonal_mm": round(diag, 4),
        "units_suspect": suspect,
        "note": (
            "bbox diagonal under 1 mm; source is probably in meters or inches. "
            "Rescale to millimetres before comparing anything to a limit."
        ) if suspect else "bbox consistent with millimetre units",
    }


def _cone_directions(normals: np.ndarray, half_angle_deg: float = 25.0, count: int = 8) -> np.ndarray:
    """For each inward normal, that direction plus `count` directions tilted by
    `half_angle_deg` around it. Shape (n, count + 1, 3)."""
    n = normals / np.linalg.norm(normals, axis=1, keepdims=True)
    helper = np.where(np.abs(n[:, :1]) < 0.9, np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 1.0, 0.0]]))
    u = np.cross(n, helper); u /= np.linalg.norm(u, axis=1, keepdims=True)
    v = np.cross(n, u)
    tilt = np.radians(half_angle_deg)
    az = np.linspace(0.0, 2 * np.pi, count, endpoint=False)
    ring = (np.cos(tilt) * n[:, None, :]
            + np.sin(tilt) * (np.cos(az)[None, :, None] * u[:, None, :] + np.sin(az)[None, :, None] * v[:, None, :]))
    return np.concatenate([n[:, None, :], ring], axis=1)


def _wall_facts(mesh: trimesh.Trimesh, samples: int, seed: int = 42) -> dict:
    """Ray-cast thickness field, one connected body at a time.

    A single ray along the inward normal reads the wrong thing wherever it can
    skim along a wall instead of across it: from a hole bore it crosses the
    whole plate, from a wall end it runs the wall's length. Each sample casts
    a cone of rays (the normal plus eight tilted 25 degrees) and keeps the
    shortest hit, which reads the local wall. Molding cares about both tails:
    thin walls that will not fill and thick junctions that sink, so the
    thickest samples are reported with the thinnest, plus their ratio to the
    median.
    """
    bodies = mesh.split(only_watertight=False)
    if len(bodies) <= 1:
        bodies = [mesh]
    areas = np.array([float(b.area) for b in bodies])
    if not np.isfinite(areas).all() or areas.sum() <= 0.0:
        return {"samples_valid": 0, "note": "no positive face area; thickness not measured"}
    share = areas / areas.sum()
    pooled, pooled_origins, per_body = [], [], []
    for i, (body, frac) in enumerate(zip(bodies, share)):
        rng = np.random.default_rng(seed + i)
        n = max(min(int(round(samples * frac)), len(body.faces)), 1)
        face_idx = rng.choice(len(body.faces), size=n, p=body.area_faces / float(body.area_faces.sum()))
        centers = body.triangles_center[face_idx]
        cone = _cone_directions(-body.face_normals[face_idx])  # (n, 9, 3)
        k = cone.shape[1]
        origins = np.repeat(centers, k, axis=0) + cone.reshape(-1, 3) * 1e-4
        directions = cone.reshape(-1, 3)
        locations, ray_ids, _ = body.ray.intersects_location(
            ray_origins=origins, ray_directions=directions, multiple_hits=False)
        diag = float(np.linalg.norm(body.extents))
        best = np.full(n, np.inf)
        if len(ray_ids):
            dist = np.linalg.norm(locations - origins[ray_ids], axis=1)
            ok = (dist > 1e-3) & (dist < diag)
            np.minimum.at(best, ray_ids[ok] // k, dist[ok])
        valid = np.isfinite(best)
        thickness = best[valid]
        per_body.append({
            "body": i,
            "samples_valid": int(len(thickness)),
            "min_mm": round(float(thickness.min()), 3) if len(thickness) else None,
            "median_mm": round(float(np.median(thickness)), 3) if len(thickness) else None,
            "max_mm": round(float(thickness.max()), 3) if len(thickness) else None,
        })
        if len(thickness):
            pooled.append(thickness)
            pooled_origins.append(centers[valid])
    if not pooled:
        return {"samples_valid": 0, "error": "no valid thickness samples", "per_body": per_body}
    thickness = np.concatenate(pooled)
    origins = np.concatenate(pooled_origins)
    median = float(np.median(thickness))
    thin_idx = np.argsort(thickness)[:8]
    thick_idx = np.argsort(-thickness)[:8]
    return {
        "method": "shortest hit of a 9-ray cone (normal + 8 at 25 deg) cast inward from area-weighted sampled faces; per body",
        "body_count": len(bodies),
        "samples_valid": int(len(thickness)),
        "min_mm": round(float(thickness.min()), 3),
        "p05_mm": round(float(np.percentile(thickness, 5)), 3),
        "median_mm": round(median, 3),
        "p95_mm": round(float(np.percentile(thickness, 95)), 3),
        "max_mm": round(float(thickness.max()), 3),
        "p95_to_median_ratio": round(float(np.percentile(thickness, 95)) / median, 2) if median else None,
        "max_to_median_ratio": round(float(thickness.max()) / median, 2) if median else None,
        "per_body": per_body,
        "thinnest_samples": [
            {"location_xyz": [round(float(v), 2) for v in origins[i]], "thickness_mm": round(float(thickness[i]), 3)}
            for i in thin_idx
        ],
        "thickest_samples": [
            {"location_xyz": [round(float(v), 2) for v in origins[i]], "thickness_mm": round(float(thickness[i]), 3)}
            for i in thick_idx
        ],
    }


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
    """
    normals = mesh.face_normals
    areas = mesh.area_faces
    centers = mesh.triangles_center
    along = normals @ pull
    lean_deg = np.degrees(np.arcsin(np.clip(np.abs(along), 0.0, 1.0)))
    zero = lean_deg < zero_tol
    eps = 1e-3 * max(float(np.linalg.norm(mesh.extents)), 1.0)

    def blocked(direction_sign: np.ndarray, sel: np.ndarray) -> np.ndarray:
        out = np.zeros(len(centers), dtype=bool)
        if not sel.any():
            return out
        idx = np.where(sel)[0]
        dirs = np.outer(direction_sign[idx], pull)
        origins = centers[idx] + normals[idx] * eps + dirs * eps
        out[idx] = mesh.ray.intersects_any(ray_origins=origins, ray_directions=dirs)
        return out

    leaning = ~zero
    sign = np.where(along >= 0, 1.0, -1.0)
    blocked_lean = blocked(sign, leaning)
    blocked_plus = blocked(np.ones(len(centers)), zero)
    blocked_minus = blocked(-np.ones(len(centers)), zero)
    trapped = zero & blocked_plus & blocked_minus
    candidates = blocked_lean | trapped
    total_area = float(areas.sum())
    return {
        "pull_axis": [round(float(v), 4) for v in pull],
        "method": "straight two-half pull; ray from each face along its withdrawal direction; zero-draft walls need both directions blocked",
        "candidate_area_mm2": round(float(areas[candidates].sum()), 2),
        "candidate_area_pct_of_surface": round(100 * float(areas[candidates].sum()) / total_area, 2) if total_area else 0.0,
        "candidate_face_count": int(candidates.sum()),
        "leaning_blocked_area_mm2": round(float(areas[blocked_lean].sum()), 2),
        "trapped_zero_draft_area_mm2": round(float(areas[trapped].sum()), 2),
        "largest_candidate_faces": _pooled_faces(mesh, candidates, pull, along),
    }


def _projection_facts(mesh: trimesh.Trimesh, pull: np.ndarray, resolution_mm: float = 0.25) -> dict:
    """Silhouette area along the pull, rasterised on a grid.

    Front-facing area over-counts wherever features overlap in projection,
    so the silhouette is rasterised instead. Resolution is reported; the
    figure is a count of covered cells, accurate to about one cell ring.
    """
    p = pull / np.linalg.norm(pull)
    helper = np.array([1.0, 0.0, 0.0]) if abs(p[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(p, helper); u /= np.linalg.norm(u)
    v = np.cross(p, u)
    pts = mesh.vertices @ np.stack([u, v], axis=1)
    lo = pts.min(axis=0) - resolution_mm
    hi = pts.max(axis=0) + resolution_mm
    size = np.maximum(np.ceil((hi - lo) / resolution_mm).astype(int), 1)
    if size.prod() > 25_000_000:
        resolution_mm = float(np.sqrt((hi - lo).prod() / 25_000_000))
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
        "raster_resolution_mm": round(resolution_mm, 4),
        "depth_along_pull_mm": round(float(heights.max() - heights.min()), 3),
        "volume_mm3": round(float(abs(mesh.volume)), 1) if mesh.is_volume else None,
    }


def _pull_facts(mesh: trimesh.Trimesh, wall_limit: float, zero_tol: float) -> dict:
    """Draft pooled for the three axis pulls.

    Draft magnitude does not change when the pull flips sign (only the lean
    does), so +x and -x are one candidate.
    """
    candidates = []
    for name, axis in _AXES.items():
        facts = _draft_facts(mesh, np.array(axis), wall_limit, zero_tol)
        undercuts = _safe(_undercut_facts, mesh, np.array(axis), zero_tol)
        candidates.append({
            "pull": name,
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
        "note": "draft magnitude is the same for +axis and -axis pulls; the lean direction differs",
        "candidates": candidates,
    }


def _safe(fn, *args) -> dict:
    """Run one fact family, degrading to an error field instead of a traceback."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - report it, never propagate
        detail = f"{type(exc).__name__}: {exc}".splitlines()[0]
        return {"error": detail[:300]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("measure", help="draft, wall, undercut and projection facts for one pull axis")
    m.add_argument("mesh")
    m.add_argument("--pull", default="z", help="axis name (z, -y) or x,y,z components")
    m.add_argument("--samples", type=int, default=2000, help="thickness ray samples")
    m.add_argument("--wall-limit", type=float, default=45.0)
    m.add_argument("--zero-tol", type=float, default=0.05)

    p = sub.add_parser("pulls", help="draft and undercut summaries for x, y and z pulls")
    p.add_argument("mesh")
    p.add_argument("--wall-limit", type=float, default=45.0)
    p.add_argument("--zero-tol", type=float, default=0.05)

    args = ap.parse_args()

    try:
        mesh = _load(args.mesh)
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
            "wall_thickness": _safe(_wall_facts, mesh, args.samples),
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

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fact-only draft-angle measurements for mesh files.

Reports measurements as JSON. It never emits pass/fail, verdicts, or
moldability statuses; comparisons against resin, texture and tooling limits
belong to the skill workflow using `references/process-review.md`.

Requires: trimesh, numpy (pip install -r requirements.txt)

Usage:
    python draft_tool.py measure <mesh> --pull z [--wall-limit 45] [--zero-tol 0.05]
    python draft_tool.py pulls <mesh> [--wall-limit 45] [--zero-tol 0.05]

Draft is measured per triangle as the angle between the face and the pull
axis: 0 means the face is parallel to the pull (no draft), 90 means it is
perpendicular to it (a top or bottom face). Faces at or above `--wall-limit`
from the pull axis are not counted as walls. Curved faces are read per facet,
so the reported draft of a cylinder or cone is the facet's draft, not an
analytic value. Which mold half forms a face, whether a parting line makes it
an undercut, and the full withdrawal path are not determined here.
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
        "surface_area_mm2": round(float(mesh.area), 1),
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


def _pull_facts(mesh: trimesh.Trimesh, wall_limit: float, zero_tol: float) -> dict:
    """Draft pooled for the three axis pulls.

    Draft magnitude does not change when the pull flips sign (only the lean
    does), so +x and -x are one candidate.
    """
    candidates = []
    for name, axis in _AXES.items():
        facts = _draft_facts(mesh, np.array(axis), wall_limit, zero_tol)
        candidates.append({
            "pull": name,
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

    m = sub.add_parser("measure", help="draft facts for one pull axis")
    m.add_argument("mesh")
    m.add_argument("--pull", default="z", help="axis name (z, -y) or x,y,z components")
    m.add_argument("--wall-limit", type=float, default=45.0)
    m.add_argument("--zero-tol", type=float, default=0.05)

    p = sub.add_parser("pulls", help="draft facts pooled for x, y and z pulls")
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
            "draft": _safe(_draft_facts, mesh, pull, args.wall_limit, args.zero_tol),
        }
    else:
        report = {
            "file": args.mesh,
            "mesh": _safe(_mesh_facts, mesh),
            "pulls": _safe(_pull_facts, mesh, args.wall_limit, args.zero_tol),
        }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

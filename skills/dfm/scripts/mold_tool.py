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
#: so a part exported in metres does not print 0.0 and a 2 m panel does not
#: allocate gigabytes. The longer span sets the cell, so the grid never exceeds
#: this many cells squared.
_RASTER_CELLS_ACROSS = 2000
#: Cells per scanline band while filling one triangle, so the barycentric
#: temporaries stay small next to the raster instead of a multiple of it.
_RASTER_ROW_CELLS = 250_000


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
    """`z`, `+z`, `-y`, or `x,y,z` components, normalised.

    A leading sign belongs to an AXIS NAME only. `-1,0,1` is a vector whose
    first component is negative, not the negation of `1,0,1`: reading the sign
    as global turns it into `(-1,0,-1)` and measures a different axis than the
    one asked for.
    """
    text = (spec or "").strip().lower()
    if not text:
        raise ValueError("pull is empty; give an axis name (z, -y) or three comma-separated components")
    named = text[1:] if text[:1] in "+-" else text
    if named in _AXES:
        sign = -1.0 if text[:1] == "-" else 1.0
        vec = np.array(_AXES[named], dtype=float) * sign
    else:
        try:
            parts = [float(v) for v in text.split(",")]
        except ValueError as exc:
            raise ValueError(f"pull must be an axis name or three comma-separated components, got {spec!r}") from exc
        if len(parts) != 3:
            raise ValueError(f"pull must be an axis name or three comma-separated components, got {spec!r}")
        vec = np.array(parts, dtype=float)
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(norm) or norm == 0.0:
        raise ValueError("pull vector has zero length")
    return vec / norm + 0.0  # + 0.0 so a negated axis prints 0.0, not -0.0


def _shells(mesh: trimesh.Trimesh) -> tuple[list, int]:
    """Connected shells split into solid bodies and sealed internal voids.

    `mesh.body_count` counts connected shells, and a cored part -- the standard
    molding fix for a thick section -- is ONE body with a second shell inside
    it. Coring out a boss must not make the part read as an assembly. A shell's
    normals point away from the material, so a void's enclose their own region
    inside out and its signed volume is negative; a solid body's is positive.
    """
    if mesh.body_count <= 1:
        return [mesh], 0
    parts = list(mesh.split(only_watertight=False))
    if not parts:
        return [mesh], 0
    solids, voids = [], 0
    for part in parts:
        try:
            signed = float(part.volume)
        except Exception:  # noqa: BLE001 - an open shell has no signed volume
            signed = 0.0
        if part.is_watertight and signed < 0.0:
            voids += 1
        else:
            solids.append(part)
    return (solids or parts), voids


def _mesh_facts(mesh: trimesh.Trimesh) -> dict:
    solids, voids = _shells(mesh)
    facts = {
        "bbox_mm": [round(float(v), 2) for v in mesh.extents],
        "triangle_count": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "body_count": len(solids),
        "surface_area_mm2": round(float(mesh.area), 1),
        "volume_mm3": round(float(abs(mesh.volume)), 1) if mesh.is_volume else None,
        "source_units": mesh.metadata.get("source_units", "mm"),
    }
    dropped = int(mesh.metadata.get("degenerate_faces_dropped", 0))
    if dropped:
        facts["degenerate_faces_dropped"] = dropped
    if voids:
        facts["internal_void_count"] = voids
        facts["internal_void_note"] = (
            f"{voids} sealed internal shell(s), counted as part of one body, not as separate "
            "bodies: a cored-out section is one molded part. Nothing here measures a sealed "
            "void's own walls, and no tool reaches inside one."
        )
    if facts["body_count"] > 1:
        facts["note"] = (
            f"{facts['body_count']} separate bodies: this file is an assembly or a split export, "
            "not one molded part. Each family is measured per body; nothing here treats one body "
            "as an obstruction for another."
        )
    return facts


def _tangent_faces(mesh: trimesh.Trimesh, pull: np.ndarray, along: np.ndarray, zero_tol: float,
                   smooth_deg: float = 45.0, taller_than_its_bounds: float = 3.0) -> np.ndarray:
    """Per face: is it a facet on a curved face that is merely TANGENT to the pull?

    A sphere is parallel to the pull along a LINE, and a tessellation turns
    that line into a band of facets whose area is a property of the export --
    261 mm2 coarse, 67 mm2 fine, for the same sphere. A cylinder's wall, by
    contrast, is parallel to the pull over its whole area and is a real
    zero-draft wall.

    What separates them is what the surface does on either side: at a tangent
    line it passes THROUGH parallel, so the region has smoothly-joined
    neighbours leaning both ways. Across a sharp edge (a box corner, a cap)
    the surface is a different face, so only smooth joins are followed.

    That test alone is not enough, because a fillet joins a wall smoothly too:
    a flange rim with a radius top and bottom has leaning neighbours both ways
    and is still a real zero-draft wall. What separates those is SIZE: a band
    standing in for a tangent line is one step of the same sweep as the facets
    bounding it, so it reaches about as far along the pull as they do, where a
    wall reaches many times further.

    The unit that gets measured is the whole zero-draft REGION -- every
    zero-draft face reachable through smooth joins -- not one triangle of it.
    A flat wall is split into rows by nothing but the export's tolerance, and
    read a row at a time a real 2 mm rim shrinks to the size of the fillet
    facet beside it and files itself as tessellation. Pooled, the ratios
    measured over the fixtures are 0.85 for a sphere's equator against 4.5 for
    a 1 mm rim, 9 for a 2 mm rim at two tessellations and 22 for a 7 mm flange
    rim, so the cut between them needs no tuning.
    """
    tangent = np.zeros(len(mesh.faces), dtype=bool)
    adjacency = mesh.face_adjacency
    if not len(adjacency):
        return tangent
    tol = float(np.sin(np.radians(zero_tol)))
    zero = np.abs(along) <= tol
    if not zero.any():
        return tangent
    smooth = np.degrees(mesh.face_adjacency_angles) < smooth_deg
    pairs = adjacency[smooth]
    if not len(pairs):
        return tangent
    left, right = pairs[:, 0], pairs[:, 1]

    regions = trimesh.graph.connected_components(
        pairs[zero[left] & zero[right]], nodes=np.where(zero)[0], min_len=1)
    if not len(regions):
        return tangent
    owner = np.full(len(mesh.faces), -1, dtype=np.int64)
    for index, region in enumerate(regions):
        owner[region] = index

    reach = mesh.triangles @ pull
    face_height = reach.max(axis=1) - reach.min(axis=1)
    height = np.array([float(reach[region].max() - reach[region].min()) for region in regions])
    above = np.zeros(len(regions), dtype=bool)
    below = np.zeros(len(regions), dtype=bool)
    # The SHORTEST leaning neighbour, not the tallest: the bound stands in for
    # one step of the sweep at the crossing, and a mesher is free to put one
    # long skinny triangle anywhere along a region's border -- on one export of
    # a 2 mm rim a single fillet triangle spanning the whole 1 mm radius spoke
    # for the sweep and ate the wall. If ANY smooth leaning neighbour is much
    # shorter than the region, the surface is not turning at the region's scale.
    bound = np.full(len(regions), np.inf)
    for near, far in ((left, right), (right, left)):
        sel = (owner[near] >= 0) & (np.abs(along[far]) > tol)
        if not sel.any():
            continue
        index = owner[near][sel]
        np.logical_or.at(above, index, along[far][sel] > tol)
        np.logical_or.at(below, index, along[far][sel] < -tol)
        np.minimum.at(bound, index, face_height[far][sel])
    bound[~np.isfinite(bound)] = 0.0
    verdict = above & below & (height <= taller_than_its_bounds * np.maximum(bound, 1e-9))
    tangent[owner >= 0] = verdict[owner[owner >= 0]]
    return tangent


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
    tangent = _tangent_faces(mesh, pull, along, zero_tol)
    curved = _curved_faces(mesh)
    flat_zero = zero & ~tangent
    tangent_zero = zero & tangent
    zero_groups = _pooled_faces(mesh, flat_zero, pull, along, zero_tol=zero_tol, curved=curved)
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
        # Tangent bands are excluded here for the same reason they are excluded
        # from the zero-draft wall area: where a fillet sweeps THROUGH parallel
        # its crossing facet is not a wall at any draft, and read as one it made
        # this figure move with the mesh (0.308 deg coarse against 2.000 fine on
        # the same 2 deg wall) -- the defect min_wall_draft exists to avoid.
        pooled = _pooled_faces(mesh, walls & ~tangent, pull, along, limit=None, draft=draft,
                               zero_tol=zero_tol, curved=curved)
        # The lowest draft over POOLED faces, ignoring the sliver tail. Read
        # from one triangle the figure moves with the mesh -- an injection tray
        # read 0.97 deg on one export and 0.60 on another, both off 0.05 mm2
        # facets. Pooling by normal and dropping faces below an ABSOLUTE area
        # floor leaves the walls a mold sees.
        floor = max(1.0, 0.001 * float(mesh.area))
        # The floor is absolute on purpose. A coverage fraction -- the largest
        # faces making up 95% of wall area -- looks like the same filter and is
        # not: on a 200x150x100 tray it dropped a 1,600 mm2 dead-vertical boss
        # wall off the end of the list and reported the part drafted throughout,
        # while zero_draft_wall_area_mm2 in the same report said 3,360. A wall
        # that clears the floor is a wall whatever else the part carries.
        # On a body with no face above the floor at all (a finely tessellated
        # sphere) every pooled face stands, and near-zero is the honest answer.
        significant = [g for g in pooled if g["area_mm2"] >= floor] or pooled
        worst = min(significant, key=lambda g: g["draft_deg"])
        result["min_wall_draft"] = {
            "draft_deg": worst["draft_deg"],
            "area_mm2": worst["area_mm2"],
            "location_xyz": worst["centroid_xyz"],
            "opens_toward": worst["opens_toward"],
            "surface": worst["surface"],
            "method": (f"area-weighted over faces pooled by normal, above {round(floor, 2)} mm2 "
                       "(0.1% of surface area), tangent bands excluded"),
        }
        # Only where the reading CLAIMS draft. A curved wall reading zero is
        # already at the worst case, and the chord cannot be hiding draft below
        # none.
        if worst["surface"] == "curved" and worst["draft_deg"] > zero_tol:
            result["min_wall_draft"]["reading_note"] = (
                "this came off a CURVED face, where a facet is a chord and a chord tilts less than "
                "the surface it cuts, so the figure is a LOWER BOUND that rises with mesh density "
                "-- one 3.000 deg conic wall read 0.46, 0.68 and 1.91 deg at three tessellations. "
                "Quote it as 'at least', or re-export finer before citing it against a limit. A "
                "flat face carries the surface's own normal and needs no such allowance."
            )
        i = int(np.argmin(np.where(walls, draft, np.inf)))
        result["min_facet_draft"] = {
            "draft_deg": round(float(draft[i]), 3),
            "area_mm2": round(float(areas[i]), 4),
            "location_xyz": [round(float(v), 2) for v in centers[i]],
            "note": "one triangle; use min_wall_draft for a figure that does not move with the mesh",
        }
        result["lowest_draft_wall_faces"] = [
            {"draft_deg": g["draft_deg"], "area_mm2": g["area_mm2"], "surface": g["surface"],
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


def _curved_faces(mesh: trimesh.Trimesh, smooth_deg: float = 45.0,
                  coplanar_deg: float = 0.01) -> np.ndarray:
    """Per face: does it lie on a CURVED surface rather than a planar one?

    A face pooled out of a planar wall carries the surface's own normal, so its
    draft is exact. A facet on a curved face is a chord, and a chord tilts less
    than the surface it cuts: the same 3 degree conic wall reads 0.46, 0.68 and
    1.91 degrees at three tessellations, all of them low. That is a property of
    reading a mesh, not something a finer rule recovers, so the reading says
    which kind of face it came from instead of pretending the two are alike.
    """
    curved = np.zeros(len(mesh.faces), dtype=bool)
    adjacency = mesh.face_adjacency
    if not len(adjacency):
        return curved
    angles = np.degrees(mesh.face_adjacency_angles)
    # Smoothly joined AND not coplanar: two triangles of one flat wall join at
    # 0 degrees, a cylinder's neighbouring facets at the tessellation step. The
    # cut is 0.01 deg because a lofted planar wall reads 1.2e-6 deg of float
    # noise across its own diagonal, against 2.86 deg for a plain cylinder.
    turning = adjacency[(angles < smooth_deg) & (angles > coplanar_deg)]
    if len(turning):
        curved[turning.ravel()] = True
    return curved


def _pooled_faces(mesh: trimesh.Trimesh, sel: np.ndarray, pull: np.ndarray, along: np.ndarray,
                  limit: int | None = 8, draft: np.ndarray | None = None,
                  zero_tol: float = 0.05, curved: np.ndarray | None = None) -> list:
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
    bends = curved[sel] if curved is not None else np.zeros(len(areas), dtype=bool)
    vertex_heights = mesh.triangles[sel] @ pull  # (n, 3): each corner along the pull
    keys = np.round(normals, 3)
    groups: dict = {}
    for k, a, c, hs, lean, dg, bend in zip(map(tuple, keys), areas, centers, vertex_heights,
                                           leans, drafts, bends):
        g = groups.setdefault(k, {"area": 0.0, "moment": np.zeros(3), "hmin": np.inf, "hmax": -np.inf,
                                  "count": 0, "lean": float(lean), "draft": 0.0, "curved": False})
        g["area"] += float(a)
        g["moment"] += c * float(a)
        g["hmin"] = min(g["hmin"], float(hs.min()))
        g["hmax"] = max(g["hmax"], float(hs.max()))
        g["draft"] += float(dg) * float(a)
        g["count"] += 1
        g["curved"] = g["curved"] or bool(bend)
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
            "surface": "curved" if g["curved"] else "flat",
            "opens_toward": _opens(g["lean"], zero_tol),
        }
        for k, g in ranked
    ]


def _scale_hint(mesh: trimesh.Trimesh) -> dict:
    """Flag meshes whose declared units are probably not the real ones.

    A mesh file carries no units, so this cannot be verified, only doubted: a
    4 x 3 x 2 part is a plausible envelope in millimetres, in centimetres and in
    inches, and reading an inch file as millimetres shrinks it 25x without
    leaving the range a molded part can occupy. The envelope under every unit
    is therefore reported next to the flag, so the doubt is the reader's to
    settle rather than a threshold's.
    """
    extents = np.asarray(mesh.extents, dtype=float)
    diag = float(np.linalg.norm(extents))
    units = mesh.metadata.get("source_units", "mm")
    factor = _UNITS_MM[units]
    suspect = bool(np.isfinite(diag) and (diag < 10.0 or diag > 2_000.0))
    if suspect:
        note = (
            f"read as {units}, giving a {round(diag, 3)} mm bounding-box diagonal, which is outside "
            "the usual range of an injection-molded part. Pass --units with the file's real units."
        )
    else:
        note = (
            f"read as {units}; bounding box is a plausible molded-part envelope. A mesh file states "
            "no units, so this is not a check that the declared units are right -- compare "
            "bbox_mm_if_units against the part you expect."
        )
    return {
        "declared_units": units,
        "bbox_diagonal_mm": round(diag, 4),
        "units_suspect": suspect,
        "bbox_mm_if_units": {
            name: [round(float(v) * scale / factor, 2) for v in extents]
            for name, scale in _UNITS_MM.items()
        },
        "note": note,
    }


def _probe_mesh(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, float, str | None]:
    """The mesh split fine enough that one ray per triangle resolves a feature.

    The occlusion test counts a whole triangle as blocked or free, so on a
    CAD-coarse export a shelf over a plate is rounded to the plate's two
    triangles. Splitting to a maximum edge first makes the counted area follow
    the feature instead of the tessellation; the rays are still cast against
    the original mesh, whose surface is identical.

    Returns the probe mesh, the edge it was split to, and -- when the face
    budget stopped the split short -- what that cost. A mesh already over
    budget cannot be refined at all, and saying so beats reporting a probe edge
    hundreds of times the size of the part as though it were a resolution.
    """
    diag = float(np.linalg.norm(mesh.extents))
    if not np.isfinite(diag) or diag <= 0 or not len(mesh.faces):
        return mesh, 0.0, None
    triangles = mesh.triangles
    longest = np.linalg.norm(triangles - np.roll(triangles, 1, axis=1), axis=2).max(axis=1)

    def output_faces(edge: float) -> float:
        # subdivide_to_size quarters a face per pass, so a face needs
        # ceil(log2(longest / edge)) passes and becomes 4 to that power.
        passes = np.ceil(np.log2(np.maximum(longest / edge, 1.0)))
        return float(np.power(4.0, passes).sum())

    target = diag * _PROBE_EDGE_FRACTION
    edge = target
    # Coarsen until the split mesh is one a ray cast per face can finish on.
    for _ in range(16):
        if edge <= 0 or not np.isfinite(edge):
            break
        if output_faces(edge) <= _PROBE_FACE_BUDGET:
            break
        coarser = edge * 2.0
        if output_faces(coarser) >= float(len(mesh.faces)) > _PROBE_FACE_BUDGET:
            # Already over budget unsplit: doubling the edge cannot help, and
            # running the doubling out reports an edge hundreds of times the
            # part's own size as if it were the resolution achieved.
            have = float(longest.max())
            unsplit = (
                f"the mesh carries {len(mesh.faces)} faces, over the {_PROBE_FACE_BUDGET} probe "
                f"budget, so faces were NOT split before casting. Its longest edge is "
                f"{round(have, 3)} mm against the {round(target, 3)} mm this wanted")
            return mesh, have, (
                f"{unsplit}, so undercut area follows the tessellation here: a feature smaller "
                "than that edge rounds to its nearest triangle. Re-export nearer "
                f"{round(target, 3)} mm and rerun."
                if have > target else
                f"{unsplit} -- already finer, so nothing was lost; the budget only stopped this "
                "from splitting further.")
        edge = coarser
    if edge <= 0 or not np.isfinite(edge):
        return mesh, 0.0, None
    probe = mesh.subdivide_to_size(edge)
    note = None
    if edge > target * 1.5:
        note = (f"faces were split to {round(edge, 3)} mm, not the {round(target, 3)} mm this "
                f"wanted, to stay under the {_PROBE_FACE_BUDGET} probe-face budget: a feature "
                "smaller than the split edge still rounds to its nearest triangle.")
    return probe, edge, note


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
    bodies, _voids = _shells(mesh)
    if len(bodies) == 1:
        # One body: cast against the whole mesh, sealed voids included, so a
        # cored section is measured as the part it belongs to.
        bodies = [mesh]
    per_body = []
    total_candidate = 0.0
    total_leaning = 0.0
    total_trapped = 0.0
    total_area = 0.0
    total_faces = 0
    pooled: list = []
    probe_edge = 0.0
    probe_notes: list[str] = []
    for index, body in enumerate(bodies):
        probe, probe_edge, probe_note = _probe_mesh(body)
        if probe_note and probe_note not in probe_notes:
            probe_notes.append(probe_note)
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
        pooled += _pooled_faces(probe, candidates, pull, along, zero_tol=zero_tol)
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
    if probe_notes:
        result["probe_resolution_note"] = " ".join(probe_notes)
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
    # Sized from the longer span, so the grid is at most _RASTER_CELLS_ACROSS
    # squared cells whatever the part's aspect ratio -- there is no second cap
    # to reach.
    size = np.maximum(np.ceil((hi - lo) / resolution_mm).astype(int), 1)
    grid = np.zeros((size[1], size[0]), dtype=bool)
    tri = (pts[mesh.faces] - lo) / resolution_mm
    for a, b, c in tri:
        x0 = max(0, int(np.floor(min(a[0], b[0], c[0])))); x1 = min(size[0] - 1, int(np.ceil(max(a[0], b[0], c[0]))))
        y0 = max(0, int(np.floor(min(a[1], b[1], c[1])))); y1 = min(size[1] - 1, int(np.ceil(max(a[1], b[1], c[1]))))
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12 or x1 < x0 or y1 < y0:
            continue
        width = x1 - x0 + 1
        xx = (np.arange(x0, x1 + 1, dtype=np.float32) + 0.5)[None, :]
        # A triangle covering half a big panel has a full-raster bounding box,
        # and three float64 barycentric planes over it cost 24 bytes a cell
        # against the grid's 1. Rows are done in bands, one plane at a time, so
        # the peak stays a small multiple of the raster itself.
        band = max(1, int(_RASTER_ROW_CELLS // width))
        for r0 in range(y0, y1 + 1, band):
            r1 = min(y1, r0 + band - 1)
            yy = (np.arange(r0, r1 + 1, dtype=np.float32) + 0.5)[:, None]
            w0 = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / den
            w1 = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / den
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & ((w0 + w1) <= 1 + 1e-6)
            grid[r0:r1 + 1, x0:x1 + 1] |= inside
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
        facts = _safe(_draft_facts, mesh, axis, wall_limit, zero_tol)
        undercuts = _safe(_undercut_facts, mesh, axis, zero_tol)
        if "error" in facts or "error" in undercuts:
            # Keeping only the numbers discards the one field that says a family
            # did not measure, and `pulls` is the verb an agent runs FIRST to
            # choose a pull: a null candidate area that reads as "no undercuts"
            # is exactly the silent "no findings" the partial machinery exists
            # to stop. The error travels with the candidate it belongs to.
            candidates.append({
                "pull": name,
                "axis": [round(float(v), 4) for v in axis],
                "error": "; ".join(part["error"] for part in (facts, undercuts) if "error" in part),
            })
            continue
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


def _has_error(value) -> bool:
    """Is there an `error` field anywhere under this value?

    Scanning only the top level missed a family that failed INSIDE another --
    `pulls` runs the undercut test once per candidate axis, and a report whose
    every candidate had failed still exited 0 and read as complete.
    """
    if isinstance(value, dict):
        return "error" in value or any(_has_error(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_error(v) for v in value)
    return False


def _mark_partial(report: dict) -> bool:
    """Flag a report whose families did not all measure.

    A family that failed leaves an `error` field where its facts should be.
    Without this, the report reads as complete and the command exits 0, so a
    dead family becomes a silent "no findings".
    """
    failed = sorted(key for key, value in report.items() if _has_error(value))
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


class _Parser(argparse.ArgumentParser):
    """A usage error exits 1, not argparse's 2.

    Exit 2 means "the report you are holding is partial" here, and a caller
    that branches on it would read a misspelled flag as a measured part with a
    failed family.
    """

    def error(self, message: str):  # noqa: D102 - argparse's own contract
        print(json.dumps({"error": f"usage: {message}", "usage": self.format_usage().strip()}))
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    ap = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True, parser_class=_Parser)

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
    # than one that says it failed. A NaN that survives everything upstream is a
    # failure to report, not a traceback to print: the header promises JSON on
    # stdout for every outcome.
    try:
        text = json.dumps(report, indent=2, allow_nan=False)
    except ValueError as exc:
        print(json.dumps({
            "file": args.mesh,
            "error": f"a measurement was not a finite number, so the report is not JSON: {exc}",
            "partial": True,
        }))
        return 1
    print(text)
    return 2 if partial else 0


if __name__ == "__main__":
    sys.exit(main())

"""3D printing's measurements of a triangle mesh, with trimesh: the families exact geometry has
(``cad.build123d._dfm_printing``) where a mesh can answer them, each item at ``x, y, z``.

- ``mesh`` (closure, bodies, volume) and ``scale``;
- ``overhangs``: the down-facing triangles under the angle limit off the plate, as connected regions,
  each with its angle, area, height and kind (a slope, a bridge or cantilever over walls, a round on the
  plate's edge); ``bridges``: the regions walls carry, their span or reach;
- ``wall_thickness``: rays into the material, per body; ``gaps``: rays out of it to a facing wall of the
  same body; ``clearances``: the least distance between bodies;
- ``trapped_volumes``: cavities from a voxel field (``cad._internal.meshops_printing``) and their openings;
- ``knife_edges``: sharp convex creases (under 45 deg) chained into edges;
- ``build_volume``, ``bed``, ``stair_stepping``, ``support_volume`` (a raster's column fill), ``sections``;
  the candidate orientations ranked (``orientations``).

A mesh has no cylinders an axis names: holes, pins and embossed details are measured on exact geometry
alone, so their rules say "not measured" of a mesh rather than pass it.

Facts, never verdicts: nothing here compares a figure against a process's limit.
``cad.<type>.dfm(..., process="printing")`` turns the report into findings
(``cad.trimesh._check``); ``cad.trimesh.printing`` and ``cad.trimesh.orientations``
hand it back as data.

``angle_limit`` only parameterises which faces are *counted* in the
support-area aggregates; per-face angles are always reported so a reader can
re-bin against any process limit. A family that fails leaves an ``error`` field
where its facts would be, and the report says so (``partial``,
``partial_sections``): a report missing wall thickness reads differently from one
whose part has no thin walls.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import trimesh

from cad._internal import meshops_printing as mo

#: Items a family lists, at most (worst first).
CAP = 300
#: A flat overhang is under this many degrees from horizontal.
FLAT_DEG = 5.0
#: Gaps are reported up to this width, mm.
GAP_CEILING = 3.0
#: A shallow slope stair-steps: above flat and under this many degrees from horizontal.
SHALLOW_DEG = 20.0
#: Clearances between bodies are reported up to this distance, mm.
CLEARANCE_REACH = 5.0


def _options(options: dict | None, angle_limit: float) -> dict:
    """The options a mesh is measured with: those given, the type side's defaults for the rest."""
    from cad._internal.dfm import printing as rules

    resolved = {"technology": "fdm", "build_volume": None, "angle_limit": angle_limit, "layer_height": None,
                "rules": "generic"}
    resolved.update({key: value for key, value in (options or {}).items() if value is not None})
    resolved["angle_limit"] = angle_limit
    resolved["layer"] = rules.layer_height(resolved)
    return resolved


def _r(value, digits: int = 4):
    return None if value is None or not np.isfinite(value) else round(float(value), digits)


def _p(point) -> list:
    return [round(float(v), 4) for v in point]


def _components(mesh: trimesh.Trimesh, mask: np.ndarray) -> list[np.ndarray]:
    """The connected regions (by shared edges) of the triangles ``mask`` selects."""
    chosen = np.flatnonzero(mask)
    if not len(chosen):
        return []
    pairs = mesh.face_adjacency
    keep = mask[pairs[:, 0]] & mask[pairs[:, 1]]
    return [np.asarray(c, dtype=int) for c in
            trimesh.graph.connected_components(pairs[keep], nodes=chosen, min_len=1)]


def _bodies(mesh: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    """The mesh's parts: its connected bodies, but a closed one turned inside out (a void's shell, which a
    solid's cavity is) and slivers of no area worth a thousandth of the whole."""
    found = []
    total = float(mesh.area) or 1.0
    for body in mesh.split(only_watertight=False):
        if body.is_watertight and float(body.volume) < 0:
            continue
        if not body.is_watertight and float(body.area) < 1e-3 * total:
            continue
        found.append(body)
    return found


def _cluster(points: np.ndarray, values: np.ndarray, cell: float) -> list[tuple[float, np.ndarray, int]]:
    """The smallest value in each cube of side ``cell`` with its point and the samples it stands for."""
    keys = np.floor(points / cell).astype(np.int64)
    order = np.lexsort((values, keys[:, 2], keys[:, 1], keys[:, 0]))
    keys, values, points = keys[order], values[order], points[order]
    first = np.ones(len(keys), dtype=bool)
    first[1:] = np.any(keys[1:] != keys[:-1], axis=1)
    starts = np.flatnonzero(first)
    counts = np.diff(np.append(starts, len(keys)))
    return [(float(values[i]), points[i], int(n)) for i, n in zip(starts, counts)]


def _load(path: str) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    return mesh


def _mesh_facts(mesh: trimesh.Trimesh) -> dict:
    return {
        "bbox_mm": [round(float(v), 2) for v in mesh.extents],
        "volume_mm3": round(float(abs(mesh.volume)), 1) if mesh.is_volume else None,
        "surface_area_mm2": round(float(mesh.area), 1),
        "triangle_count": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "euler_number": int(mesh.euler_number),
        "body_count": int(mesh.body_count),
    }


def _overhang_facts(mesh: trimesh.Trimesh, angle_limit: float, layer: float = 0.2, regions: bool = True) -> dict:
    """Face angles measured from horizontal: 0 = flat ceiling, 90 = vertical. The counted triangles as
    connected regions (``items``), each a slope, a bridge or cantilever over the walls that carry it, a
    flat ceiling nothing carries, or a round on the plate's edge."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    centers = mesh.triangles_center

    down = normals[:, 2] < -1e-6
    surface_angle = 90.0 - np.degrees(np.arcsin(np.clip(-normals[:, 2], 0, 1)))

    z_min = mesh.bounds[0][2]
    on_plate = centers[:, 2] < (z_min + 0.1)

    counted = down & ~on_plate & (surface_angle < angle_limit)
    total_area = float(areas.sum())

    # angle histogram of down-facing, off-plate faces (10° bins)
    off_plate_down = down & ~on_plate
    hist = {}
    if off_plate_down.any():
        bins = np.arange(0, 100, 10)
        idx = np.digitize(surface_angle[off_plate_down], bins) - 1
        for b in range(len(bins) - 1):
            area = float(areas[off_plate_down][idx == b].sum())
            if area > 0:
                hist[f"{bins[b]}-{bins[b+1]}deg"] = round(area, 2)

    worst = []
    if counted.any():
        w_idx = np.where(counted)[0]
        order = w_idx[np.argsort(-areas[w_idx])][:8]
        worst = [
            {
                "location_xyz": [round(float(v), 2) for v in centers[i]],
                "surface_angle_deg": round(float(surface_angle[i]), 1),
                "area_mm2": round(float(areas[i]), 2),
            }
            for i in order
        ]

    items = _overhang_regions(mesh, counted, surface_angle, z_min, max(1.0, 5 * layer)) if regions else []
    excluded = sum(item["area_below_limit_mm2"] for item in items if item["kind"] in ("plate_edge", "bridge"))
    return {
        "items": sorted(items, key=lambda item: (item["angle_deg"], -item["area_mm2"]))[:CAP],
        "count": len(items),
        "angle_limit_used_deg": angle_limit,
        "supported_area_excluded_mm2": round(float(excluded), 2),
        "down_facing_area_below_limit_mm2": round(float(areas[counted].sum()), 2),
        "down_facing_area_below_limit_pct": round(
            100 * float(areas[counted].sum()) / total_area, 1) if total_area else 0.0,
        "face_count_below_limit": int(counted.sum()),
        "down_facing_angle_histogram_mm2": hist,
        "largest_faces_below_limit": worst,
    }


def _overhang_regions(mesh: trimesh.Trimesh, counted: np.ndarray, tilt: np.ndarray, z_min: float,
                      plate_band: float) -> list[dict]:
    """Each connected region of ``counted`` triangles: its steepest angle, area, height, and what carries it
    -- the walls below its boundary (a bridge held from opposite sides, a cantilever from one)."""
    if not counted.any():
        return []
    centers, areas, vertices = mesh.triangles_center, mesh.area_faces, mesh.vertices
    pairs, shared = mesh.face_adjacency, mesh.face_adjacency_edges
    tol = 1e-3 * max(1.0, float(np.linalg.norm(mesh.extents)) * 1e-3)
    items = []
    for region in _components(mesh, counted):
        inside = np.zeros(len(mesh.faces), dtype=bool)
        inside[region] = True
        edge = inside[pairs[:, 0]] != inside[pairs[:, 1]]
        outer = np.where(inside[pairs[edge, 0]], pairs[edge, 1], pairs[edge, 0])
        mids = vertices[shared[edge]].mean(axis=1)
        carries = centers[outer, 2] < mids[:, 2] - tol
        a, b = vertices[shared[edge][carries, 0]], vertices[shared[edge][carries, 1]]
        tri = vertices[mesh.faces[region]]
        points = mo.spread_points(tri, cap=3000)
        flat = bool(tilt[region].max() < FLAT_DEG)
        size = float(np.linalg.norm(tri.reshape(-1, 3).max(axis=0) - tri.reshape(-1, 3).min(axis=0)))
        spread = mo.span(points, a, b, inside=mo.in_triangles_xy(tri) if len(region) <= 2000 else None,
                         refine=size / 40.0)
        heights = centers[region, 2] - z_min
        touches = float(vertices[mesh.faces[region]][:, :, 2].min()) <= z_min + 0.1
        if spread["kind"] == "bridge":
            kind = "bridge"
        elif touches and float(heights.max()) <= plate_band:
            kind = "plate_edge"
        elif flat:
            kind = "cantilever" if spread["kind"] == "cantilever" else "ceiling"
        else:
            kind = "slope"
        worst = region[int(tilt[region].argmin())]
        area = float(areas[region].sum())
        items.append({"xyz": _p(centers[worst]), "angle_deg": _r(float(tilt[region].min()), 3),
                      "area_mm2": _r(area, 3), "area_below_limit_mm2": _r(area, 3),
                      "height_mm": _r(float(heights.min()), 3), "max_height_mm": _r(float(heights.max()), 3),
                      "kind": kind, "flat": flat, "length_mm": _r(spread["length_mm"]),
                      "reach_mm": _r(spread["reach_mm"]), "supporting_edges": int(carries.sum())})
    return items


def _bridge_facts(overhangs: dict) -> dict:
    """The overhang regions walls carry, or that are flat: their span or reach."""
    if "error" in overhangs:
        return {"error": overhangs["error"]}
    items = [{key: item[key] for key in ("xyz", "kind", "length_mm", "reach_mm", "supporting_edges", "area_mm2",
                                         "height_mm", "angle_deg")}
             for item in overhangs.get("items") or () if item["kind"] in ("bridge", "cantilever", "ceiling")]
    items.sort(key=lambda item: -(item["length_mm"] or 0.0))
    bridges = [item["length_mm"] for item in items if item["kind"] == "bridge" and item["length_mm"] is not None]
    return {"items": items[:CAP], "count": len(items), "flat_within_deg": FLAT_DEG,
            "bridge_count": len(bridges), "longest_bridge_mm": max(bridges, default=None),
            "method": "regions of down-facing triangles under the angle limit; carried where the triangle across "
                      "their edge descends (a wall below); span from the region's points to those edges"}


#: Triangles a mesh has, at most, for every one to get a ray of its own (a small feature's few triangles
#: would otherwise draw no sample of an area-weighted budget).
COVER = 20000


def _cover(mesh: trimesh.Trimesh, inward: bool, reach: float | None = None) -> tuple[np.ndarray, ...]:
    """One ray from every triangle's centre (``COVER`` of them, by area, on a larger mesh), into the material
    (``inward``) or out of it: each ray's length to a face that looks back at it, its origin, its face's
    normal and the triangle it landed on. Rays that meet nothing, or a face square to them, are dropped."""
    count = len(mesh.faces)
    if count == 0 or not float(mesh.area_faces.sum()) > 0:
        return np.zeros(0), np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    if count > COVER:
        total = float(mesh.area_faces.sum()) or 1.0
        faces = np.random.default_rng(3).choice(count, size=COVER, p=mesh.area_faces / total)
    else:
        faces = np.arange(count)
    normals = mesh.face_normals[faces]
    directions = -normals if inward else normals
    origins = mesh.triangles_center[faces] + directions * 1e-4
    locations, rays, hit = mesh.ray.intersects_location(ray_origins=origins, ray_directions=directions,
                                                        multiple_hits=False)
    if not len(rays):
        return np.zeros(0), np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    length = np.linalg.norm(np.asarray(locations).reshape(-1, 3) - origins[rays], axis=1)
    # a wall's far face looks away from the ray; one square to it (a corner) does not, one under KNIFE_DEG
    # off parallel (a knife edge's other face) does, as the exact path counts it
    square = float(np.cos(np.radians(mo.KNIFE_DEG)))
    facing = np.einsum("ij,ij->i", mesh.face_normals[hit], directions[rays]) > square if inward else \
        np.einsum("ij,ij->i", mesh.face_normals[hit], directions[rays]) < -0.5
    keep = (length > 1e-3) & facing & (length < (reach or float(np.linalg.norm(mesh.extents))))
    return length[keep], origins[rays][keep], normals[rays][keep], faces[rays][keep], hit[keep]


def _wall_items(thickness: np.ndarray, origins: np.ndarray, cell: float) -> list[dict]:
    """The thickness field as items: the thinnest sample in each cube of side ``cell`` (whether a mesh's
    wall is joined on two sides is not known: ``supported`` None)."""
    found = _cluster(origins, thickness, cell)
    found.sort(key=lambda row: row[0])
    return [{"xyz": _p(point), "thickness_mm": _r(value), "samples": count, "supported": None}
            for value, point, count in found[:CAP]]


def _wall_facts(mesh: trimesh.Trimesh, samples: int, seed: int = 42, keep: dict | None = None) -> dict:
    """Ray-cast thickness field, measured one connected body at a time.

    Cast against a whole assembly, a ray leaving one body can cross a mating
    clearance and land on its neighbour, which records the fit gap as a wall.
    A tight-clearance assembly then reports a wall-thickness violation that no
    single part actually has. Splitting first makes that impossible, because
    each body is only ever measured against itself.
    """
    bodies = mesh.split(only_watertight=False)
    cell = max(2.0, float(np.linalg.norm(mesh.extents)) / 40.0)
    if len(bodies) <= 1:
        facts = _wall_facts_single(mesh, samples, seed)
        if "_thickness" in facts:
            extra = _cover(mesh, inward=True)
            t = np.concatenate([facts["_thickness"], extra[0]])
            o = np.vstack([facts["_origins"], extra[1]])
            facts["items"] = _wall_items(t, o, cell)
            if keep is not None:
                keep.update(thickness=t, origins=o, normals=np.vstack([facts["_normals"], extra[2]]))
        for key in [key for key in facts if key.startswith("_")]:
            facts.pop(key)
        return facts

    areas = np.array([float(b.area) for b in bodies])
    if not np.isfinite(areas).all() or areas.sum() <= 0.0:
        return {
            "samples": 0,
            "note": "no positive face area; mesh is degenerate, thickness not measured",
        }

    # Split the sample budget by surface area so a large body is not measured
    # at the same resolution as a small one, with a floor so small bodies are
    # still sampled at all.
    share = areas / areas.sum()
    pooled: list = []
    pooled_origins: list = []
    pooled_normals: list = []
    covered: list = []
    per_body: list = []
    for i, (body, frac) in enumerate(zip(bodies, share)):
        budget = max(int(round(samples * frac)), 64)
        facts = _wall_facts_single(body, budget, seed + i)
        per_body.append({
            "body": i,
            "min_mm": facts.get("min_mm"),
            "p05_mm": facts.get("p05_mm"),
            "median_mm": facts.get("median_mm"),
            "samples_valid": facts.get("samples_valid", 0),
        })
        if "_thickness" in facts:
            pooled.append(facts["_thickness"])
            pooled_origins.append(facts["_origins"])
            pooled_normals.append(facts["_normals"])
            extra = _cover(body, inward=True)
            covered.append(extra[:3])

    if not pooled:
        return {
            "error": "no valid thickness samples",
            "body_count": len(bodies),
            "per_body": per_body,
        }

    thickness = np.concatenate(pooled)
    origins = np.concatenate(pooled_origins)
    every_t = np.concatenate([thickness, *[c[0] for c in covered]])
    every_o = np.vstack([origins, *[c[1] for c in covered]])
    if keep is not None:
        keep.update(thickness=every_t, origins=every_o,
                    normals=np.vstack([np.concatenate(pooled_normals), *[c[2] for c in covered]]))
    thin_idx = np.argsort(thickness)[:8]

    return {
        "items": _wall_items(every_t, every_o, cell),
        "body_count": len(bodies),
        "measured_per_body": True,
        "samples_valid": int(len(thickness)),
        "min_mm": round(float(thickness.min()), 3),
        "p05_mm": round(float(np.percentile(thickness, 5)), 3),
        "p25_mm": round(float(np.percentile(thickness, 25)), 3),
        "median_mm": round(float(np.median(thickness)), 3),
        "max_mm": round(float(thickness.max()), 3),
        "per_body": per_body,
        "thinnest_samples": [
            {
                "location_xyz": [round(float(v), 2) for v in origins[i]],
                "thickness_mm": round(float(thickness[i]), 3),
            }
            for i in thin_idx
        ],
    }


def _wall_facts_single(mesh: trimesh.Trimesh, samples: int, seed: int = 42) -> dict:
    """Ray-cast thickness field for ONE connected body."""
    rng = np.random.default_rng(seed)
    n = min(samples, max(len(mesh.faces), 1))

    # Area weighting needs a positive total. A mesh of only degenerate faces
    # has none, and is not something a thickness field can describe - say so
    # rather than dividing by zero inside rng.choice.
    total_area = float(mesh.area_faces.sum())
    if not np.isfinite(total_area) or total_area <= 0.0:
        return {
            "samples": 0,
            "note": "no positive face area; mesh is degenerate, thickness not measured",
        }

    face_idx = rng.choice(len(mesh.faces), size=n,
                          p=mesh.area_faces / total_area)

    origins = mesh.triangles_center[face_idx]
    directions = -mesh.face_normals[face_idx]
    origins = origins + directions * 1e-4

    locations, ray_ids, hit_tri = mesh.ray.intersects_location(
        ray_origins=origins, ray_directions=directions, multiple_hits=False)

    if len(ray_ids) == 0:
        return {"error": "ray casting produced no hits", "samples_requested": n}

    thickness = np.linalg.norm(locations - origins[ray_ids], axis=1)
    diag = float(np.linalg.norm(mesh.extents))
    # a wall's two faces look away from each other; a ray that lands on a face meeting its own at a corner
    # (KNIFE_DEG or more between them) measures the corner, not a wall -- a knife edge's sliver is counted
    opposing = np.einsum("ij,ij->i", mesh.face_normals[hit_tri], directions[ray_ids]) > \
        float(np.cos(np.radians(mo.KNIFE_DEG)))
    valid = (thickness > 1e-3) & (thickness < diag) & opposing
    thickness = thickness[valid]

    if len(thickness) == 0:
        return {"error": "no valid thickness samples", "samples_requested": n}

    hit_origins = origins[ray_ids][valid]
    thin_idx = np.argsort(thickness)[:8]

    return {
        "samples_valid": int(len(thickness)),
        "min_mm": round(float(thickness.min()), 3),
        "p05_mm": round(float(np.percentile(thickness, 5)), 3),
        "p25_mm": round(float(np.percentile(thickness, 25)), 3),
        "median_mm": round(float(np.median(thickness)), 3),
        "max_mm": round(float(thickness.max()), 3),
        "thinnest_samples": [
            {
                "location_xyz": [round(float(v), 2) for v in hit_origins[i]],
                "thickness_mm": round(float(thickness[i]), 3),
            }
            for i in thin_idx
        ],
        # Underscore keys are internal: _wall_facts pools them across bodies
        # and strips them before anything is printed. They are numpy arrays
        # and would not survive json.dumps.
        "_thickness": thickness,
        "_origins": hit_origins,
        "_normals": -directions[ray_ids][valid],
    }


def _support_volume_facts(mesh: trimesh.Trimesh, angle_limit: float) -> dict:
    """The column fill under every down-facing surface under the angle limit, down to the part or the plate,
    from a raster of the mesh along Z, and the part's volume (its convex hull's where the mesh is open)."""
    V, F = np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int)
    held = mo.support(V, F, angle_limit, mo.raster_pitch(mesh.extents), plate_z=float(V[:, 2].min()))
    support_vol = held["volume_mm3"]
    part_vol = float(abs(mesh.volume)) if mesh.is_volume else float(mesh.convex_hull.volume)

    return {
        "angle_limit_used_deg": angle_limit,
        "estimated_support_volume_mm3": round(support_vol, 1),
        "part_volume_mm3": round(part_vol, 1),
        "support_to_part_ratio_pct": round(
            100 * support_vol / part_vol, 1) if part_vol else 0.0,
        "support_contact_mm2": round(held["contact_area_mm2"], 2),
        "pitch_mm": round(held["pitch_mm"], 4),
        "method": "column fill under every down-facing surface under the angle limit, down to the part or the "
                  "plate, from a raster of the mesh along Z",
    }


def _orientation_facts(mesh: trimesh.Trimesh, angle_limit: float, technology: str = "fdm",
                       machine: dict | None = None) -> dict:
    """The six axis-aligned orientations: support volume and contact, build height, bed contact, overhang
    and shallow-slope area, the build-volume fit, ranked by the weighting ``mo.WEIGHTS`` states."""
    from cad._internal.dfm import printing as rules

    V, F = np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int)
    rows = mo.orientation_rows(V, F, mo.ROTATIONS, angle_limit, mo.raster_pitch(mesh.extents), SHALLOW_DEG)
    volume = np.array((machine or rules.machine_volume({"technology": technology}))["volume_mm"], dtype=float)
    for row in rows:
        m = mesh.copy()
        m.vertices = V @ np.array(row["rotation"]).T
        ov = _overhang_facts(m, angle_limit, regions=False)
        row["support_area_mm2"] = ov["down_facing_area_below_limit_mm2"]
        row["support_area_pct"] = ov["down_facing_area_below_limit_pct"]
        box = np.array(row["bbox_mm"])
        xy = max(float(sorted(box[:2])[k]) / float(sorted(volume[:2])[k]) for k in range(2))
        row["fill_ratio"] = round(max(xy, float(box[2]) / float(volume[2])), 4)
        row["fits"] = bool(row["fill_ratio"] <= 1.0 + 1e-9)
    weights = mo.WEIGHTS["powder" if technology in rules.POWDER else "support"]
    rows = mo.ranked(rows, weights)
    return {
        "angle_limit_used_deg": angle_limit,
        # Percentages are of total surface area, which is rotation-invariant.
        # That makes them comparable between candidates but not a measure of
        # plate coverage - rank on support_area_mm2, read pct as a signal.
        "pct_denominator": "total surface area",
        "weights": weights,
        "ranking": "each figure over the largest any candidate has, weighted, summed: lowest first",
        "best": rows[0]["orientation"] if rows else None,
        "candidates": rows,
    }


def _gap_facts(mesh: trimesh.Trimesh, samples: int) -> dict:
    """Rays out of the material from every triangle of each body to a wall of the same body that faces back
    (not a triangle sharing a corner with it): the narrow slots, per cube the narrowest."""
    points, widths = [], []
    for body in _bodies(mesh):
        width, origins, _, faces, hit = _cover(body, inward=False, reach=GAP_CEILING)
        if not len(width):
            continue
        shared = (body.faces[faces][:, :, None] == body.faces[hit][:, None, :]).any(axis=(1, 2))
        points.append(origins[~shared])
        widths.append(width[~shared])
    items = []
    if points and sum(len(p) for p in points):
        cell = max(2.0, float(np.linalg.norm(mesh.extents)) / 40.0)
        found = _cluster(np.vstack(points), np.concatenate(widths), cell)
        found.sort(key=lambda row: row[0])
        items = [{"xyz": _p(point), "gap_mm": _r(value), "samples": count} for value, point, count in found[:CAP]]
    return {"items": items, "count": len(items), "reported_below_mm": GAP_CEILING,
            "min_mm": items[0]["gap_mm"] if items else None,
            "method": "a ray out of the material from every triangle to a facing wall of the same body (holes read "
                      "as gaps on a mesh)"}


def _clearance_facts(mesh: trimesh.Trimesh) -> dict:
    """The least distance between each pair of bodies (vertices and triangle centres of each to the other's
    surface, both ways), within ``CLEARANCE_REACH``."""
    bodies = _bodies(mesh)
    items = []
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            a, b = bodies[i], bodies[j]
            lo, hi = np.maximum(a.bounds[0], b.bounds[0]), np.minimum(a.bounds[1], b.bounds[1])
            if float(np.max(lo - hi)) > CLEARANCE_REACH:
                continue
            best = (np.inf, None)
            for one, other in ((a, b), (b, a)):
                probes = np.vstack([one.vertices, one.triangles_center])
                near = np.all((probes >= other.bounds[0] - CLEARANCE_REACH) & (probes <= other.bounds[1] + CLEARANCE_REACH), axis=1)
                if not near.any():
                    continue
                closest, distance, _ = trimesh.proximity.closest_point(other, probes[near])
                k = int(distance.argmin())
                if distance[k] < best[0]:
                    best = (float(distance[k]), (probes[near][k] + closest[k]) / 2.0)
            if best[1] is None or best[0] > CLEARANCE_REACH:
                continue
            overlap = bool(b.is_watertight and b.contains(a.vertices[:2000]).any()) or bool(
                a.is_watertight and a.contains(b.vertices[:2000]).any())
            kind = "overlap" if overlap else ("contact" if best[0] <= 1e-6 else "gap")
            items.append({"xyz": _p(best[1]), "distance_mm": _r(0.0 if overlap else best[0], 5), "kind": kind,
                          "bodies": [i, j]})
    items.sort(key=lambda item: item["distance_mm"])
    return {"items": items[:CAP], "count": len(items), "body_count": len(bodies), "reported_below_mm": CLEARANCE_REACH,
            "min_mm": items[0]["distance_mm"] if items else None,
            "method": "closest points of each body's vertices and triangle centres on the other's surface"}


class _Field:
    """The mesh's voxel field and cavities, made once for the families that read them."""

    def __init__(self, mesh: trimesh.Trimesh) -> None:
        V, F = np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int)
        self.pitch, self.ball = mo.field_pitch(mesh.extents)
        self.grid = mo.voxels(V, F, self.pitch, pad=mo.ball_pad(self.ball, self.pitch))
        self.cavities, self.labels = mo.cavities(self.grid, self.ball)


def _trapped_facts(field: _Field, walls: dict) -> dict:
    """The cavities of the voxel field: volume, sealed or not, openings (estimated from the largest ball
    through each), the thinnest wall round each (the wall samples whose outside lies in it)."""
    grid, labels = field.grid, field.labels
    near = {}
    if walls.get("thickness") is not None:
        probes = walls["origins"] + walls["normals"] * (0.75 * grid.pitch + 1e-4)
        marks = labels[grid.index(probes)]
        for k in np.unique(marks[marks >= 0]):
            near[int(k)] = float(walls["thickness"][marks == k].min())
    items = []
    for k, cavity in enumerate(field.cavities):
        diameters = sorted(float(opening["diameter_mm"]) for opening in cavity.openings)
        items.append({"xyz": _p(cavity.centroid), "volume_mm3": _r(cavity.volume_mm3, 2),
                      "sealed": bool(cavity.sealed and not diameters), "exact": False, "escape_holes": len(diameters),
                      "escape_hole_diameters_mm": [_r(d, 3) for d in diameters],
                      "min_escape_hole_mm": _r(diameters[0], 3) if diameters else None,
                      "min_wall_mm": _r(near.get(k), 4)})
    items.sort(key=lambda item: (item["escape_holes"], -(item["volume_mm3"] or 0)))
    return {"items": items[:CAP], "count": len(items), "sealed_count": sum(1 for item in items if item["sealed"]),
            "trapped_volume_mm3": _r(sum(item["volume_mm3"] or 0 for item in items), 2),
            "pitch_mm": _r(field.pitch, 4), "ball_radius_mm": _r(field.ball, 3),
            "method": "air a ball cannot reach from outside, from a voxel field; openings and their widths estimated "
                      "to a voxel"}


def _section_facts(field: _Field) -> dict:
    found = mo.sections(field.grid)
    items = []
    if found["thickness_mm"] is not None:
        items.append({"xyz": _p(found["center"]), "thickness_mm": _r(found["thickness_mm"], 3),
                      "at_least": found["at_least"], "pitch_mm": _r(field.pitch, 4)})
    report = {"items": items, "count": len(items), "max_thickness_mm": items[0]["thickness_mm"] if items else None,
              "measured_up_to_mm": 12.0,
              "method": "the largest ball the material holds, from the voxel field (to a voxel)"}
    if found.get("max_cross_section_mm2") is not None:
        report.update(max_cross_section_mm2=_r(found["max_cross_section_mm2"], 2),
                      max_cross_section_z_mm=_r(found["max_cross_section_z"] - float(field.grid.origin[2]) -
                                                mo.ball_pad(field.ball, field.pitch) * field.pitch, 4),
                      largest_section_change_mm2=_r(found["largest_section_change_mm2"], 2))
    return report


def _bed_facts(mesh: trimesh.Trimesh) -> dict:
    """What rests on the plate: the flat down-facing triangles at the lowest point, their area and extent."""
    normals, areas = mesh.face_normals, mesh.area_faces
    z = mesh.vertices[mesh.faces][:, :, 2]
    zmin = float(mesh.bounds[0][2])
    tol = max(1e-4, 1e-6 * float(np.linalg.norm(mesh.extents)))
    contact = (normals[:, 2] < -0.9999) & (z.max(axis=1) <= zmin + tol)
    items = []
    for region in _components(mesh, contact):
        points = mesh.vertices[np.unique(mesh.faces[region])]
        extent = points.max(axis=0) - points.min(axis=0)
        items.append({"xyz": _p(points.mean(axis=0)), "area_mm2": _r(float(areas[region].sum()), 3),
                      "length_mm": _r(float(extent[:2].max()), 4)})
    items.sort(key=lambda item: -item["area_mm2"])
    footprint = mesh.extents[:2]
    points = mesh.vertices[np.unique(mesh.faces[contact])] if contact.any() else np.zeros((0, 3))
    length = float((points.max(axis=0) - points.min(axis=0))[:2].max()) if len(points) else 0.0
    area = float(areas[contact].sum())
    return {"items": items[:CAP], "count": len(items), "contact_area_mm2": _r(area, 3),
            "footprint_mm": _p(footprint), "footprint_area_mm2": _r(float(footprint[0] * footprint[1]), 3),
            "contact_ratio": _r(area / float(footprint[0] * footprint[1]), 4) if footprint.prod() > 0 else None,
            "contact_length_mm": _r(length, 4), "holes_on_plate": None}


def _stair_facts(mesh: trimesh.Trimesh, layer: float) -> dict:
    """The shallow slopes that stair-step: above flat (0.5 deg) and under ``SHALLOW_DEG`` from horizontal, by
    angle and as connected regions with their cusp height (layer cos angle) and step width (layer / tan)."""
    tilt = mo.angles(mesh.face_normals)
    areas = mesh.area_faces
    edges = [0.5, 5.0, 10.0, 15.0, SHALLOW_DEG]
    shallow = (tilt > edges[0]) & (tilt < SHALLOW_DEG)
    items = []
    for region in _components(mesh, shallow):
        mean = float(np.average(tilt[region], weights=np.maximum(areas[region], 1e-12)))
        items.append({"xyz": _p(mesh.triangles_center[region].mean(axis=0)), "angle_deg": _r(mean, 3),
                      "area_mm2": _r(float(areas[region].sum()), 3),
                      "cusp_mm": _r(layer * np.cos(np.radians(mean)), 4),
                      "step_width_mm": _r(layer / np.tan(np.radians(mean)), 4),
                      "facing": "up" if float(mesh.face_normals[region, 2].mean()) > 0 else "down"})
    items.sort(key=lambda item: -item["area_mm2"])
    return {"items": items[:CAP], "count": len(items), "layer_height_mm": layer, "shallow_below_deg": SHALLOW_DEG,
            "area_by_angle_mm2": {f"{edges[k]:g}-{edges[k + 1]:g}deg":
                                  _r(float(areas[shallow & (tilt >= edges[k]) & (tilt < edges[k + 1])].sum()), 2)
                                  for k in range(4)},
            "area_mm2": _r(float(areas[shallow].sum()), 2)}


def _knife_facts(mesh: trimesh.Trimesh, options: dict) -> dict:
    """The sharp convex creases between triangles whose material angle is under ``KNIFE_DEG``, chained into
    edges where they share corners: each chain's length, least angle and thin depth (as the exact path's)."""
    from cad._internal.dfm import printing as rules

    minimum = rules.wall_minimum(options)
    material = 180.0 - np.degrees(mesh.face_adjacency_angles)
    sharp = mesh.face_adjacency_convex & (material < mo.KNIFE_DEG)
    items = []
    if sharp.any():
        pairs = mesh.face_adjacency_edges[sharp]
        angle = material[sharp]
        chains = trimesh.graph.connected_components(pairs, min_len=1)
        chain_of = np.full(len(mesh.vertices), -1)
        for k, chain in enumerate(chains):
            chain_of[np.asarray(chain, dtype=int)] = k
        owner = chain_of[pairs[:, 0]]
        lengths = np.linalg.norm(mesh.vertices[pairs[:, 0]] - mesh.vertices[pairs[:, 1]], axis=1)
        for k in np.unique(owner):
            mine = owner == k
            least = float(angle[mine].min())
            length = float(lengths[mine].sum())
            middle = mesh.vertices[pairs[mine]].reshape(-1, 3).mean(axis=0)
            depth = mo.thin_depth(minimum, least)
            items.append({"xyz": _p(middle), "angle_deg": _r(least, 3), "length_mm": _r(length, 4),
                          "thickness_mm": 0.0, "thin_depth_mm": _r(depth, 4),
                          "thin_area_mm2": _r(depth * length if depth else None, 4)})
    items.sort(key=lambda item: item["angle_deg"])
    return {"items": items[:CAP], "count": len(items), "knife_below_deg": mo.KNIFE_DEG, "min_wall_mm": minimum,
            "length_mm": _r(sum(item["length_mm"] for item in items), 4),
            "method": "convex creases between triangles whose material angle is under knife_below_deg, chained by "
                      "shared corners"}


def _build_volume_facts(mesh: trimesh.Trimesh, options: dict) -> dict:
    from cad._internal.dfm import printing as rules

    return mo.build_fit(mesh.bounds[0], mesh.bounds[1], rules.machine_volume(options))


def _safe(fn, *args) -> dict:
    """Run one fact family, degrading to an error field instead of a traceback.

    measure assembles every family before printing, so one throwing family
    used to cost the user the facts that did compute: a planar mesh dies in
    convex_hull and took the whole report with it. Each family now fails on
    its own and the rest still reach the caller as JSON.
    """
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - report it, never propagate
        detail = f"{type(exc).__name__}: {exc}".splitlines()[0]
        return {"error": detail[:300]}


def _mark_partial(report: dict) -> bool:
    """Say, in the report, that a fact family did not compute.

    Degrading one family instead of the whole run is deliberate (`_safe`), but a
    caller must be able to SEE it: a report missing wall thickness because scipy
    is not installed reads exactly like one from a part with no thin walls. The
    families that failed are named in `partial_sections`, and the check fails on
    each of them (an error finding), so neither a JSON reader nor a shell caller
    can take a partial report for a complete one.
    """
    failed = sorted(
        name for name, value in report.items()
        if isinstance(value, dict) and "error" in value
    )
    report["partial"] = bool(failed)
    if failed:
        report["partial_sections"] = failed
    return bool(failed)


def _scale_hint(mesh: trimesh.Trimesh) -> dict:
    """Flag meshes whose units are probably not millimetres.

    A meters-scale export measures a bbox like 0.05 x 0.02 x 0.04, which sits
    under the 0.1 mm on-plate tolerance: every down-facing face reads as
    resting on the plate, so overhangs and support both come back 0.0 and the
    part looks like a flawless print. Give the workflow something measured to
    branch on rather than asking the agent to eyeball the bounding box.
    """
    diag = float(np.linalg.norm(mesh.extents))
    suspect = bool(np.isfinite(diag) and diag < 1.0)
    return {
        "bbox_diagonal_mm": round(diag, 4),
        "units_suspect": suspect,
        "note": (
            "bbox diagonal under 1 mm; source is probably in meters or inches. "
            "Rescale to millimetres before trusting overhang, support or "
            "thickness numbers."
        ) if suspect else "bbox consistent with millimetre units",
    }


def measure(mesh: trimesh.Trimesh, samples: int, angle_limit: float, options: dict | None = None) -> dict:
    """Every family: the mesh, its scale, overhangs and bridges, wall thickness, gaps, clearances between
    bodies, trapped volumes, the build volume, bed contact, stair-stepping, support volume and sections.
    ``options``: the check's (``technology``, ``layer_height``, ``build_volume``, ``rules``)."""
    resolved = _options(options, angle_limit)
    kept: dict = {}
    report = {
        "technology": resolved["technology"],
        "mesh": _safe(_mesh_facts, mesh),
        "scale": _safe(_scale_hint, mesh),
        "overhangs": _safe(_overhang_facts, mesh, angle_limit, resolved["layer"]),
        "wall_thickness": _safe(_wall_facts, mesh, samples, 42, kept),
        "gaps": _safe(_gap_facts, mesh, samples),
        "clearances": _safe(_clearance_facts, mesh),
        "build_volume": _safe(_build_volume_facts, mesh, resolved),
        "bed": _safe(_bed_facts, mesh),
        "knife_edges": _safe(_knife_facts, mesh, resolved),
        "stair_stepping": _safe(_stair_facts, mesh, resolved["layer"]),
        "support_volume": _safe(_support_volume_facts, mesh, angle_limit),
    }
    report["bridges"] = _bridge_facts(report["overhangs"])
    try:
        field = _Field(mesh)
    except Exception as exc:  # noqa: BLE001 - both families say so
        failed = {"error": f"{type(exc).__name__}: {exc}".splitlines()[0][:300]}
        report["trapped_volumes"], report["sections"] = failed, dict(failed)
    else:
        report["trapped_volumes"] = _safe(_trapped_facts, field, kept)
        report["sections"] = _safe(_section_facts, field)
    _mark_partial(report)
    return report


def orientations(mesh: trimesh.Trimesh, angle_limit: float, options: dict | None = None) -> dict:
    """Its scale and the six axis-aligned candidate orientations ranked."""
    from cad._internal.dfm import printing as rules

    resolved = _options(options, angle_limit)
    report = {
        "scale": _safe(_scale_hint, mesh),
        "orientations": _safe(_orientation_facts, mesh, angle_limit, resolved["technology"],
                              rules.machine_volume(resolved)),
    }
    _mark_partial(report)
    return report

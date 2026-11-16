"""3D printing's measurements of a triangle mesh, with trimesh: the families exact geometry has
(``cad.build123d._dfm_printing``) where a mesh can answer them, each item at ``x, y, z``.

- ``mesh`` (closure, bodies, volume) and ``scale``;
- ``overhangs``: the down-facing triangles under the angle limit off the plate, as connected regions,
  each with its angle, area, height and kind (a slope, a bridge or cantilever over walls, a round on the
  plate's edge); ``bridges``: the regions walls carry, their span or reach;
- ``wall_thickness``: rays into the material, per body (and one from every triangle on a mesh of at most
  ``COVER_MAX_TRIANGLES``); ``gaps``: rays out of it to a facing wall of the same body (under ``GAP_DEFECT_MM``,
  faces on faces: the mesh's ``overlap``); ``clearances``: the least distance between bodies;
- ``trapped_volumes``: cavities from a voxel field (``cad._internal.meshops_printing``) and their openings;
- ``knife_edges``: sharp convex creases (under 45 deg, at least 2: a sharper one is a fold of the tessellation)
  chained into edges, however short;
- ``build_volume``, ``bed``, ``stair_stepping``, ``support_volume`` (a raster's column fill), ``sections``;
  the candidate orientations ranked (``orientations``).

A mesh has no cylinders an axis names: its round holes up to the gaps' reach are the gaps whose rays cross one
(``holes``), a pin is one of its walls, and pins' own minima and embossed details are measured on exact geometry
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

import math
from typing import Any

import numpy as np
import trimesh

from cad._internal import meshops_printing as mo
from cad._internal.dfm._common import units_doubt
from cad.trimesh import _mesh

#: Items a family lists, at most (worst first).
CAP = 300
#: A flat overhang is under this many degrees from horizontal.
FLAT_DEG = 5.0
#: Gaps are reported up to this width, mm.
GAP_CEILING = 3.0
#: A mesh's "gap" narrower than this, mm, is faces lying on faces -- doubled or overlapping triangles, the mesh's
#: defect (a 0.005 mm one on an exporter's mounting plate) -- said once, never a slot: every published minimum
#: gap is 0.3 mm or more.
GAP_DEFECT_MM = 0.05
#: A shallow slope stair-steps: above flat and under this many degrees from horizontal.
SHALLOW_DEG = 20.0
#: A gap sampled under this width, mm, is refined to the least about its narrowest ray (``_least_wall``), the
#: ``REFINE_READ`` narrowest of a mesh: every published minimum gap is under 1 mm.
REFINE_GAP_MM = 2.0
#: Clearances between bodies are reported up to this distance, mm.
CLEARANCE_REACH = 5.0


def _options(options: dict | None, angle_limit: float) -> dict:
    """The options a mesh is measured with: those given, the type side's defaults for the rest."""
    from cad._internal.dfm import printing as rules

    resolved = {"technology": "fdm", "build_volume": None, "angle_limit": angle_limit, "layer_height": None}
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


#: Triangles joined by an edge whose normals turn under this many degrees are one face of the part: a face's
#: tessellation turns by its angular deflection (a few degrees), a feature edge further. The walls are one item
#: per face and the face across, and a gap ray landing on a face beside its own meets it at their shared edge,
#: as the exact path reads both (``_dfm_printing``).
FACE_DEG = 30.0


def _regions(mesh: trimesh.Trimesh) -> tuple[np.ndarray, set[tuple[int, int]]]:
    """Each triangle's face of the part (``FACE_DEG``), and the pairs of faces that share an edge (made once a
    mesh)."""
    found = getattr(mesh, "_cad_regions", None)
    if found is None or len(found[0]) != len(mesh.faces):
        found = mesh._cad_regions = _regions_of(mesh)
    return found


def _smooth(mesh: trimesh.Trimesh) -> mo.Smooth:
    """The surface the mesh stands for (``meshops_printing.Smooth``: the smoothed normals at every triangle's
    corners), made once a mesh: what gives every comparison of a triangle's angle with a limit its tolerance --
    an overhang's, a wall's far face at 45 deg, a knife edge's 45 deg."""
    found = getattr(mesh, "_cad_smooth", None)
    if found is None or len(found.noise) != len(mesh.faces):
        found = mesh._cad_smooth = mo.smooth(np.asarray(mesh.vertices, dtype=float),
                                             np.asarray(mesh.faces, dtype=int), FACE_DEG)
    return found


def _regions_of(mesh: trimesh.Trimesh) -> tuple[np.ndarray, set[tuple[int, int]]]:
    count = len(mesh.faces)
    labels = np.arange(count)
    pairs = np.asarray(mesh.face_adjacency)
    if not len(pairs):
        return labels, set()
    smooth = np.asarray(mesh.face_adjacency_angles) < np.radians(FACE_DEG)
    for k, component in enumerate(trimesh.graph.connected_components(pairs[smooth], nodes=np.arange(count),
                                                                     min_len=1)):
        labels[np.asarray(component, dtype=int)] = count + k
    a, b = labels[pairs[~smooth, 0]], labels[pairs[~smooth, 1]]
    beside = {(int(x), int(y)) for x, y in zip(np.minimum(a, b), np.maximum(a, b)) if x != y}
    return labels, beside


def _load(path: str, units: str = "mm") -> trimesh.Trimesh:
    """Read a mesh file, made millimetres and cleaned as every check's mesh is (``_mesh.load``)."""
    return _mesh.load(path, units)


def _bodies(mesh: trimesh.Trimesh) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """The mesh's bodies, each solid with the sealed voids inside it, and the voids' own shells.

    A body is a connected piece of the surface, split with no repair: an opening stays open, as ``_mesh.closure``
    judges it (an edge used an odd number of times). Two bodies sharing a face use its edges four times, so the
    split leaves each without it and the face's copies over as pieces of their own: a piece no edge of which
    is a boundary is closed, so its holes are faces another body shares, and are filled; a piece that fills to
    no volume is such a face's copy, no body. A piece of next to no area (``_mesh.SLIVER_AREA``) is never a body.
    A shell's normals point away from its material, so a sealed void's signed volume is negative and a
    solid's positive: a cavity a part encloses -- a groove that
    does not reach the surface -- is that part's, and its walls are measured with it, never as a body
    of its own. A void goes with the smallest solid that holds a corner of its shell, else with the largest. An
    open sliver of no
    area worth a thousandth of the whole (an exporter's stray facets) is no body: a ray from one measured
    a wall the part has not."""
    faces = np.asarray(mesh.faces)
    pieces = trimesh.graph.connected_components(mesh.face_adjacency, nodes=np.arange(len(faces)), min_len=1)
    if len(pieces) <= 1:
        return [mesh], []
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _unique, inverse, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    odd = (counts[inverse.ravel()] % 2 == 1).reshape(3, -1).T.any(axis=1)
    diagonal = max(1.0, float(np.linalg.norm(mesh.extents)))
    areas = np.asarray(mesh.area_faces)
    parts = []
    for piece in pieces:
        piece = np.asarray(piece, dtype=int)
        if float(areas[piece].sum()) <= _mesh.SLIVER_AREA * diagonal ** 2:
            continue
        part = trimesh.Trimesh(mesh.vertices, faces[piece], process=False)
        part.remove_unreferenced_vertices()
        if not odd[piece].any() and not part.is_watertight:
            trimesh.repair.fill_holes(part)
            if part.is_watertight and abs(float(part.volume)) <= 1e-9 * diagonal ** 3:
                continue  # a shared face's copy
        parts.append(part)
    if len(parts) <= 1:
        return parts or [mesh], []
    total = float(mesh.area) or 1.0
    solids, voids = [], []
    for part in parts:
        try:
            signed = float(part.volume)
        except Exception:  # noqa: BLE001 - an open shell has no signed volume
            signed = 0.0
        if part.is_watertight and signed < 0.0:
            voids.append(part)
        elif part.is_watertight or float(part.area) >= 1e-3 * total:
            solids.append(part)
    if not solids:
        return parts, []
    held: list[list[trimesh.Trimesh]] = [[solid] for solid in solids]
    for void in voids:
        # the solid its shell lies in -- the smallest that holds a corner of it: a captive ball at the centre of a
        # hollow shell holds the void's centre, never its shell
        corner = np.asarray(void.vertices[:1], dtype=float)
        within = [at for at, solid in enumerate(solids) if solid.is_watertight and _inside(solid, corner)[0]]
        holder = min(within, key=lambda at: abs(float(solids[at].volume))) if within else \
            max(range(len(solids)), key=lambda at: solids[at].area)
        held[holder].append(void)
    return [group[0] if len(group) == 1 else trimesh.util.concatenate(group) for group in held], voids


def _mesh_facts(mesh: trimesh.Trimesh, split: tuple[list[trimesh.Trimesh], list] | None = None) -> dict:
    """The mesh as a whole; ``body_count`` None where its bodies could not be split (the wall family then
    says why)."""
    facts: dict = {
        "bbox_mm": [round(float(v), 2) for v in mesh.extents],
        "surface_area_mm2": round(float(mesh.area), 1),
        "triangle_count": int(len(mesh.faces)),
        **_mesh.facts(mesh),
        "euler_number": int(mesh.euler_number),
        "body_count": None,
    }
    try:
        bodies, voids = split if split is not None else _bodies(mesh)
    except Exception:  # noqa: BLE001 - a split that fails is the wall family's error, in its own words
        return facts
    facts["body_count"] = len(bodies)
    if voids:
        facts["internal_void_count"] = len(voids)
    # a closed body whose surface passes through itself (the validity the exact path's kernel checks): more
    # than a stray line of a raster up through it enters material it is already in
    crossed = []
    for index, body in enumerate(bodies):
        if not body.is_watertight:
            continue
        lines, of, place = mo.doubled(np.asarray(body.vertices, dtype=float), np.asarray(body.faces, dtype=int))
        if lines > max(2, of // 500):
            crossed.append({"body": index, "columns": lines, "of": of, "xyz": _p(place)})
    if crossed:
        facts["self_intersecting"] = crossed
    return facts


def _at_limit(mesh: trimesh.Trimesh, angle_limit: float, turned: np.ndarray | None = None) -> np.ndarray:
    """The triangles (a mask) that read under ``angle_limit`` from horizontal and are at it within the mesh's
    accuracy, the mesh turned by the rotation ``turned`` where given: those of each region of down-facing
    triangles under the limit (joined by their edges) none of which is under it by more than its own tolerance
    (``Smooth.slopes``: how far the mesh's chords turn from the surface there). A 45 deg cone's triangles read
    44.3 to 45.4 deg, and every patch of them under 45 is the cone's 45; a round's rows run on down to 0 deg, and
    all of it under the limit is an overhang, its rows just under the limit too."""
    surface = _smooth(mesh)
    normals = surface.normals if turned is None else surface.normals @ turned.T
    tilt = mo.angles(normals)
    # off the plate, as the overhangs are counted: what rests on it is no overhang, and joins no region of them
    height = mesh.triangles_center[:, 2] if turned is None else mesh.triangles_center @ turned[2]
    lowest = float(mesh.bounds[0][2] if turned is None else (mesh.vertices @ turned[2]).min())
    under = (normals[:, 2] < -1e-6) & (tilt < angle_limit - mo.ANGLE_EPS) & ~(height < lowest + 0.1)
    near = under.copy()
    clear = under & (tilt < angle_limit - mo.ANGLE_EPS - surface.slopes(turned))
    for region in _components(mesh, under) if clear.any() else ():
        if clear[region].any():
            near[region] = False
    return near


def _overhang_facts(mesh: trimesh.Trimesh, angle_limit: float, layer: float = 0.2, regions: bool = True,
                    reach_floor: float = mo.OVERHANG_REACH_MM, near: np.ndarray | None = None) -> dict:
    """Face angles measured from horizontal: 0 = flat ceiling, 90 = vertical. The counted triangles as
    connected regions (``items``), each a slope, a bridge or cantilever over the walls that carry it, a
    flat ceiling nothing carries, or a round on the plate's edge. A region whose every triangle is under the
    limit by no more than the mesh's own accuracy is at the limit, no overhang (``_at_limit``; ``near``, where the
    caller turned the mesh): its area is ``at_limit_area_mm2``."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    centers = mesh.triangles_center

    down = normals[:, 2] < -1e-6
    surface_angle = 90.0 - np.degrees(np.arcsin(np.clip(-normals[:, 2], 0, 1)))

    z_min = mesh.bounds[0][2]
    on_plate = centers[:, 2] < (z_min + 0.1)

    near = _at_limit(mesh, angle_limit) if near is None else near
    counted = down & ~on_plate & (surface_angle < angle_limit - mo.ANGLE_EPS) & ~near
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

    # one underside is one region: its triangles under the limit, joined through the down-facing triangles
    # within ``OVERHANG_JOIN`` of them (a scan's noise breaks one underside into hundreds of islands)
    band = counted.copy()
    pairs = np.asarray(mesh.face_adjacency)
    for _ring in range(OVERHANG_JOIN if regions and len(pairs) else 0):
        beside = np.zeros(len(band), dtype=bool)
        beside[pairs[band[pairs[:, 0]], 1]] = True
        beside[pairs[band[pairs[:, 1]], 0]] = True
        band |= beside & down & ~on_plate
    items = _overhang_regions(mesh, counted, band, surface_angle, z_min, max(1.0, 5 * layer), reach_floor) \
        if regions else []
    unread = sum(1 for item in items if item.pop("_unread", False))
    # The headline is the exact path's: the regions that need support, a bridge, a round on the plate's edge and a
    # region under the floors aside (they are listed, counted false, and no rule judges them).
    headline = counted
    if regions:
        headline = np.zeros(len(mesh.faces), dtype=bool)
        for item in items:
            if item["counted"] and item["kind"] != "bridge":
                headline[item["_faces"]] = True
    for item in items:
        item.pop("_faces", None)
    worst = []
    if headline.any():
        w_idx = np.where(headline)[0]
        order = w_idx[np.argsort(-areas[w_idx])][:8]
        worst = [
            {
                "location_xyz": [round(float(v), 2) for v in centers[i]],
                "surface_angle_deg": round(float(surface_angle[i]), 1),
                "area_mm2": round(float(areas[i]), 2),
            }
            for i in order
        ]

    excluded = sum(item["area_below_limit_mm2"] for item in items if item["kind"] in ("plate_edge", "bridge"))
    return {
        "items": sorted(items, key=lambda item: (item["angle_deg"], -item["area_mm2"]))[:CAP],
        "count": len(items),
        "angle_limit_used_deg": angle_limit,
        "supported_area_excluded_mm2": round(float(excluded), 2),
        "down_facing_area_below_limit_mm2": round(float(areas[headline].sum()), 2),
        "down_facing_area_below_limit_pct": round(
            100 * float(areas[headline].sum()) / total_area, 1) if total_area else 0.0,
        "face_count_below_limit": int(headline.sum()),
        "down_facing_angle_histogram_mm2": hist,
        "largest_faces_below_limit": worst,
        "area_floor_mm2": mo.OVERHANG_AREA_MM2, "reach_floor_mm": reach_floor,
        # under the limit by no more than the mesh's own angular deflection there: at the limit, not judged
        "at_limit_area_mm2": round(float(areas[near].sum()), 2),
        # flat regions whose span the family's budget (``SPAN_PAIRS``) did not reach: not measured
        **({"spans_not_measured": unread} if unread else {}),
        # how far those triangles' angles may be off the surface's (``Smooth.slopes``): at most ``CHORD_CAP_DEG``
        "at_limit_tolerance_deg": round(float(_smooth(mesh).slopes()[near].max()), 4) if regions and near.any() else 0.0,
        "method": "regions of down-facing triangles under the angle limit off the plate (but a region none of whose "
                  "triangles is under it by more than the mesh's chords turn from the surface there: at the limit), "
                  f"those within {OVERHANG_JOIN} down-facing triangles of each other one region; "
                  "one under area_floor_mm2, "
                  "or a cantilever reaching under reach_floor_mm (the nozzle given, else one bead), is listed with "
                  "counted false and judged by no rule: text-to-cad's own floors, no guide states them; the "
                  "down-facing area counts the regions that need support (bridges and plate-edge rounds aside), "
                  "as on exact geometry",
    }


#: Overhang regions with at most twice this many down-facing triangles between them are one region (one
#: underside, one finding): a scanned sphere's underside read as 47 regions of 1 mm2 or more, at 3 as one.
OVERHANG_JOIN = 3
#: Point-to-support distances the overhang regions' spans get, at most, the largest regions first (3000 points a
#: region against at most ``SPAN_SUPPORTS`` of its supporting edges): what bounds the family's time on a mesh of
#: thousands of flat regions. A region past it has no span (``spans_not_measured``).
SPAN_PAIRS = 100_000_000
SPAN_SUPPORTS = 4000


def _overhang_regions(mesh: trimesh.Trimesh, counted: np.ndarray, band: np.ndarray, tilt: np.ndarray,
                      z_min: float, plate_band: float, reach_floor: float = mo.OVERHANG_REACH_MM) -> list[dict]:
    """Each region of ``counted`` triangles -- those joined by their edges, or through the triangles of
    ``band`` (the down-facing triangles beside them) --: its steepest angle, area, height, and what carries it -- the
    walls below its boundary (a bridge held from opposite sides, a cantilever from one). A flat region's or an
    arch's span is read (``meshops_printing.span``), the largest regions first, within ``SPAN_PAIRS``; a
    region too small to need support, or a slope, has none to read."""
    if not counted.any():
        return []
    centers, areas, vertices = np.asarray(mesh.triangles_center), np.asarray(mesh.area_faces), np.asarray(mesh.vertices)
    faces, normals = np.asarray(mesh.faces), np.asarray(mesh.face_normals)
    pairs, shared = np.asarray(mesh.face_adjacency), np.asarray(mesh.face_adjacency_edges)
    tol = 1e-3 * max(1.0, float(np.linalg.norm(mesh.extents)) * 1e-3)
    # each counted triangle's region; the others' -1
    label = np.full(len(faces), -1)
    for k, component in enumerate(_components(mesh, counted | band)):
        label[component] = k
    label[~counted] = -1
    # every edge between a region and what lies beside it, with the triangle beside: grouped by region
    a, b = pairs[:, 0], pairs[:, 1]
    edge = label[a] != label[b]
    inner = np.concatenate([a[edge & (label[a] >= 0)], b[edge & (label[b] >= 0)]])
    outer = np.concatenate([b[edge & (label[a] >= 0)], a[edge & (label[b] >= 0)]])
    ends = np.concatenate([shared[edge & (label[a] >= 0)], shared[edge & (label[b] >= 0)]])
    by_edge = np.argsort(label[inner], kind="stable")
    inner, outer, ends = inner[by_edge], outer[by_edge], ends[by_edge]
    edge_at = np.searchsorted(label[inner], np.arange(int(label.max()) + 2))
    members = np.flatnonzero(label >= 0)
    members = members[np.argsort(label[members], kind="stable")]
    face_at = np.searchsorted(label[members], np.arange(int(label.max()) + 2))
    regions = [members[face_at[k]:face_at[k + 1]] for k in range(int(label.max()) + 1) if face_at[k + 1] > face_at[k]]
    regions.sort(key=lambda region: -float(areas[region].sum()))
    items, spent = [], 0
    for region in regions:
        k = int(label[region[0]])
        beside, rim = outer[edge_at[k]:edge_at[k + 1]], ends[edge_at[k]:edge_at[k + 1]]
        mids = vertices[rim].mean(axis=1)
        carries = centers[beside, 2] < mids[:, 2] - tol
        tri = vertices[faces[region]]
        area = float(areas[region].sum())
        flat = bool(tilt[region].max() < FLAT_DEG)
        heights = centers[region, 2] - z_min
        # on the plate's edge: the region reaches the plate, or runs on into down-facing triangles that do (a
        # round's lowest row, on the plate, is no overhang and is not in the region) -- as the exact path reads a
        # round whose face touches the plate
        lowest = vertices[faces[beside[normals[beside, 2] < -1e-6]]][:, :, 2]
        touches = float(tri[:, :, 2].min()) <= z_min + 0.1 or (lowest.size > 0 and float(lowest.min()) <= z_min + 0.1)
        # what carries it is read where a verdict can turn on it: a flat region, or an arch (curved one way: a
        # hole's crown), large enough to need support
        spread: dict = {"kind": None, "length_mm": None, "reach_mm": None}
        unread = False
        if area >= mo.OVERHANG_AREA_MM2 and (flat or _arch(normals[region], areas[region])):
            starts, stops = vertices[rim[carries, 0]], vertices[rim[carries, 1]]
            if len(starts) > SPAN_SUPPORTS:  # a boundary of more edges than are read: every n-th of them
                some = np.linspace(0, len(starts) - 1, SPAN_SUPPORTS).round().astype(int)
                starts, stops = starts[some], stops[some]
            points = mo.spread_points(tri, cap=3000)
            if spent + len(points) * max(1, len(starts)) > SPAN_PAIRS:
                unread = True
            else:
                spent += len(points) * max(1, len(starts))
                size = float(np.linalg.norm(tri.reshape(-1, 3).max(axis=0) - tri.reshape(-1, 3).min(axis=0)))
                spread = mo.span(points, starts, stops, inside=mo.in_triangles_xy(tri) if len(region) <= 2000 else None,
                                 refine=size / 40.0)
        # carried on both sides, a flat region or an arch is a bridge of its span (every layer of a hole's crown
        # but the last stands on the one below); a dome (curved both ways: a hollow sphere's top) is a slope by
        # its least angle, as the exact path reads a curved face
        if spread["kind"] == "bridge":
            kind = "bridge"
        elif touches and float(heights.max()) <= plate_band:
            kind = "plate_edge"
        elif flat:
            kind = "cantilever" if spread["kind"] == "cantilever" else "ceiling"
        else:
            kind = "slope"
        worst = region[int(tilt[region].argmin())]
        # too small to need support: under the area floor, or a cantilever shorter than a bead is wide
        big = kind != "plate_edge" and area >= mo.OVERHANG_AREA_MM2 and not (
            kind == "cantilever" and spread["reach_mm"] is not None and spread["reach_mm"] < reach_floor)
        items.append({"xyz": _p(centers[worst]), "angle_deg": _r(float(tilt[region].min()), mo.JUDGED),
                      "area_mm2": _r(area, 3), "area_below_limit_mm2": _r(area, 3),
                      "height_mm": _r(float(heights.min()), 3), "max_height_mm": _r(float(heights.max()), 3),
                      "kind": kind, "flat": flat, "length_mm": _r(spread["length_mm"], mo.JUDGED),
                      "reach_mm": _r(spread["reach_mm"]), "supporting_edges": int(carries.sum()), "counted": bool(big),
                      "_faces": region, "_unread": unread and kind != "plate_edge"})
    return items


def _arch(normals: np.ndarray, areas: np.ndarray) -> bool:
    """Whether a region of these triangles curves one way alone (an arch, a cylinder's part: its normals are all
    square to its axis, so they lie in one plane through the origin) rather than both (a dome, whose normals
    fill a cone) or not at all (a plane, tilted: no arch): of the three spreads of its normals, the least under
    a tenth of the next, and that next no noise (a thousandth of the first)."""
    spread = np.linalg.svd(normals * np.sqrt(np.maximum(areas, 0.0))[:, None], compute_uv=False)
    return bool(len(spread) == 3 and spread[1] > 1e-3 * spread[0] and spread[2] < 0.1 * spread[1])


def _bridge_facts(overhangs: dict) -> dict:
    """The overhang regions walls carry, or that are flat: their span or reach."""
    if "error" in overhangs:
        return {"error": overhangs["error"]}
    items = [{key: item[key] for key in ("xyz", "kind", "length_mm", "reach_mm", "supporting_edges", "area_mm2",
                                         "height_mm", "angle_deg")}
             for item in overhangs.get("items") or () if item["kind"] in ("bridge", "cantilever", "ceiling")]
    items.sort(key=lambda item: -(item["length_mm"] or 0.0))
    bridges = [item["length_mm"] for item in items if item["kind"] == "bridge" and item["length_mm"] is not None]
    unread = overhangs.get("spans_not_measured")
    return {"items": items[:CAP], "count": len(items), "flat_within_deg": FLAT_DEG,
            "bridge_count": len(bridges), "longest_bridge_mm": max(bridges, default=None),
            **({"spans_not_measured": unread} if unread else {}),
            "method": "regions of down-facing triangles under the angle limit; carried where the triangle across "
                      "their edge descends (a wall below); span from the region's points to those edges"}


#: How far along its ray a ray's origin is nudged off its own triangle, so it does not hit it: every length is
#: measured from the surface, the nudge added back (a 2 mm wall reads 2, not 1.9999).
NUDGE = 1e-4
#: Triangles a mesh has, at most, for every one to get a ray of its own (a small feature's few triangles
#: would otherwise draw no sample of an area-weighted budget): the gaps' rays.
COVER = 20000
#: The walls add a ray from every triangle (``_cover``) to their random ones on a mesh of at most this many
#: triangles, and on a larger one cast the random rays alone. Measured on 60 real meshes against their exact
#: B-reps: the pass cost 26 times the wall family's time (343.6 s against 13.2 s), found 3 thin places the random
#: rays missed and 9 that are not there (a triangle's centre on a fine fillet strip lands on its neighbour);
#: on the 10 meshes of at most 5000 triangles it found the macropad knob's 0.27 mm web, which 2000 random rays
#: miss, and no false one, for 3.7 s in all. 20000 random rays instead were no better (8 false fails).
COVER_MAX_TRIANGLES = 5000
def _facing(mesh: trimesh.Trimesh, started: np.ndarray, landed: np.ndarray, origins: np.ndarray,
            locations: np.ndarray) -> np.ndarray:
    """Which wall rays' far faces look back along them: the triangle a ray ``landed`` on (at ``locations``)
    turned within KNIFE_DEG of the ray -- the inward normal of the triangle it ``started`` on, at ``origins`` --
    a face turned exactly that far (a 45-degree gusset's) at the limit, not past it, as the exact path compares
    it. The angle is read off the two triangles and, again, off the surface's smoothed normals at the ray's two
    ends (``Smooth.at``), and is at the limit within their difference (``Smooth.within``): the mesh of a 45 deg
    cone's rim reads its far face at 44.3 to 45.7 deg, and every one of them is at 45."""
    surface = _smooth(mesh)
    V, F = np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int)

    def turn(near: np.ndarray, far: np.ndarray) -> np.ndarray:
        return np.degrees(np.arccos(np.clip(-np.einsum("ij,ij->i", near, far), -1.0, 1.0)))

    read = turn(mesh.face_normals[started], mesh.face_normals[landed])
    smoothed = turn(surface.at(started, origins, V, F), surface.at(landed, locations, V, F))
    return read <= mo.KNIFE_DEG + mo.ANGLE_EPS + surface.within(read, smoothed, started) + surface.noise[landed]


#: A gap's far wall looks back across it: its normal within ``KNIFE_DEG`` of the ray's way back, as a wall's far
#: face is turned (``_facing``) and as the exact path reads a slot. Two flanks further apart than that -- a
#: thread's 60 deg V -- are a notch, no slot.
_LOOKS_BACK = math.cos(math.radians(mo.KNIFE_DEG + mo.ANGLE_EPS))
#: A ray starts on (or lands on) a knife edge's flank when that triangle's normal is within this many degrees of
#: the flank's (the triangle by the crease on either side): the knife's sliver is a ray within its thin depth that
#: starts or lands on a flank, and any other ray there (a fin beside the knife, across itself) measures a wall.
FLANK_DEG = 20.0
#: Convex creases of material up to this many degrees are chained, and a chain whose angle (its creases' median
#: by length) is under ``KNIFE_DEG`` is a knife edge: a curved knife's triangles scatter about its angle (an exact
#: 41 deg edge of a finger tip meshes as creases of 4 to 58 deg), and the creases under 45 alone break it into
#: pieces whose gaps leave its sliver to the walls (0.036 mm "walls" where the exact path finds 0.89).
CREASE_DEG = 60.0


class _Knife:
    """A knife edge of a mesh: its creases as segments, their two flanks' normals, its material angle (the
    creases' median by length), length and thin depth (``meshops_printing.thin_depth``) at that angle, and each
    crease's own thin depth (``depths``: at the angle of the creases around it, ``_local_angles``) -- an edge whose
    angle runs from 25 to 60 deg is as thin as its 25 deg tip there, deeper than its median says."""

    __slots__ = ("starts", "ends", "left", "right", "angle", "length", "depth", "depths", "slack")

    def __init__(self, starts, ends, left, right, angle: float, length: float, depth: float | None,
                 depths: np.ndarray | None = None, slack: float = 0.0) -> None:
        self.starts, self.ends, self.left, self.right = starts, ends, left, right
        self.angle, self.length, self.depth = angle, length, depth
        self.depths = depths if depths is not None else np.full(len(starts), depth or 0.0)
        #: how far its angle may be off the edge's it stands for, degrees (``_crease_slack``)
        self.slack = slack

    @property
    def knife(self) -> bool:
        """Under 45 deg by more than its slack: a knife edge."""
        return self.angle < mo.KNIFE_DEG - mo.ANGLE_EPS - self.slack

    @property
    def over(self) -> bool:
        """Over 45 deg by more than its slack: no knife, and a ray counts as its sliver only from one flank onto
        the other."""
        return self.angle > mo.KNIFE_DEG + mo.ANGLE_EPS + self.slack


#: Creases a chain has, at most, for each to be read against those around it (``_local_angles``: a pass over the
#: chain a crease).
LOCAL_CREASES = 4000


def _local_angles(starts: np.ndarray, ends: np.ndarray, angles: np.ndarray, lengths: np.ndarray,
                  window: float) -> np.ndarray:
    """Each crease's angle as the creases around it read it: the length-weighted median of those whose middles lie
    within ``window`` of its own -- one triangle's crease scatters (an exact 41 deg edge meshes as creases of 4 to
    58 deg), the run of them along the edge does not."""
    middles = (starts + ends) / 2.0
    found = np.empty(len(angles))
    if len(angles) > LOCAL_CREASES:  # a chain of more creases than are read one by one: its own angle all along
        order = np.argsort(angles)
        weight = np.cumsum(lengths[order])
        found[:] = angles[order][min(int(np.searchsorted(weight, weight[-1] / 2.0)), len(order) - 1)]
        return found
    for k in range(len(angles)):
        near = np.flatnonzero(np.linalg.norm(middles - middles[k], axis=1) <= window)
        order = near[np.argsort(angles[near])]
        weight = np.cumsum(lengths[order])
        found[k] = angles[order][min(int(np.searchsorted(weight, weight[-1] / 2.0)), len(order) - 1)]
    return found


def _crease_slack(mesh: trimesh.Trimesh, corners: np.ndarray, sides: np.ndarray, angle: np.ndarray) -> np.ndarray:
    """How far each crease's material ``angle`` (read off its two triangles' own normals, ``sides``) may be off
    the edge's it stands for, degrees: the same angle read off the two faces' smoothed normals at each of the
    crease's two ``corners``, and the difference taken as ``Smooth.within`` takes it."""
    surface, faces = _smooth(mesh), np.asarray(mesh.faces)
    smoothed = np.empty((len(corners), 2))
    for k in range(2):
        normals = [surface.corners[sides[:, side], np.argmax(faces[sides[:, side]] == corners[:, k, None], axis=1)]
                   for side in range(2)]
        smoothed[:, k] = 180.0 - np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", *normals), -1.0, 1.0)))
    return surface.within(angle, smoothed, sides[:, 0]) + surface.noise[sides[:, 1]]


def _knife_chains(mesh: trimesh.Trimesh, minimum: float | None) -> list[_Knife]:
    """The sharp edges: convex creases (material angle under ``CREASE_DEG``, at least ``FOLD_DEG``: a sharper
    one is a fold of the tessellation) chained by shared corners, each chain with its angle (its creases' median
    by length, as the exact path reads an edge at its middle) and how far that may be off (``slack``: its
    creases' median ``_crease_slack``), however short it is: the tip of a 1 mm plate, the corner of an engraved
    letter 0.6 mm deep, is an edge as short as the plate is thick, and a knife as exact geometry reads it. A
    chain under ``KNIFE_DEG`` by more than its slack is a knife (``_Knife.knife``); every
    chain is a zone whose own sliver the walls leave alone (``_outside_knives``), so a tip at the limit, or a
    curved one whose chords read either side of it, is neither a knife nor a thin wall."""
    material = 180.0 - np.degrees(mesh.face_adjacency_angles)
    sharp = mesh.face_adjacency_convex & (material < CREASE_DEG) & (material >= mo.FOLD_DEG)
    if not sharp.any():
        return []
    pairs, sides, angle = mesh.face_adjacency_edges[sharp], mesh.face_adjacency[sharp], material[sharp]
    slack = _crease_slack(mesh, pairs, sides, angle)
    chain_of = np.full(len(mesh.vertices), -1)
    for k, chain in enumerate(trimesh.graph.connected_components(pairs, min_len=1)):
        chain_of[np.asarray(chain, dtype=int)] = k
    owner = chain_of[pairs[:, 0]]
    lengths = np.linalg.norm(mesh.vertices[pairs[:, 0]] - mesh.vertices[pairs[:, 1]], axis=1)
    found = []
    by_chain = np.argsort(owner, kind="stable")
    cuts = np.flatnonzero(np.diff(owner[by_chain])) + 1
    for mine in np.split(by_chain, cuts):
        length = float(lengths[mine].sum())
        # its least crease would make a curved knife far deeper than it is (and than it is long)
        order = np.argsort(angle[mine])
        weight = np.cumsum(lengths[mine][order])
        middle = min(int(np.searchsorted(weight, weight[-1] / 2.0)), len(order) - 1)
        typical = float(angle[mine][order][middle])
        depth = mo.thin_depth(minimum, typical)
        starts, ends = mesh.vertices[pairs[mine, 0]], mesh.vertices[pairs[mine, 1]]
        depths = None
        if depth is not None:
            # each crease its own depth, at the angle of the creases within the knife's depth of it
            local = _local_angles(starts, ends, angle[mine], lengths[mine], max(depth, 2.0 * float(np.median(lengths[mine]))))
            depths = np.array([mo.thin_depth(minimum, a) or 0.0 for a in local])
        found.append(_Knife(starts, ends, mesh.face_normals[sides[mine, 0]], mesh.face_normals[sides[mine, 1]],
                            typical, length, depth, depths, float(np.median(slack[mine]))))
    return found


def _knife_zones(mesh: trimesh.Trimesh, options: dict) -> list[_Knife]:
    """The knife edges, each with its thin depth against the rules' unsupported-wall minimum: the sliver
    the knife family reports, which the walls leave to it, as the exact path does
    (``_dfm_printing._knife_zones``)."""
    from cad._internal.dfm import printing as rules

    return _knife_chains(mesh, rules.wall_minimum(options))


def _outside_knives(points: np.ndarray, normals: np.ndarray, zones: list[_Knife],
                    landed: np.ndarray | None = None) -> np.ndarray:
    """Which rays (from ``points``, on faces of outward ``normals``, landing on faces of outward ``landed``)
    measure a wall rather than a knife's sliver: all but those within a knife's thin depth that start or land on
    one of its two flanks (``FLANK_DEG``) -- the sliver from either flank, or from a face that meets them at the
    knife's end across to one. The sliver is real and reported once, by the knife family; a ray near the knife
    between two other faces -- a fin beside it, across itself -- is a wall's."""
    keep = np.ones(len(points), dtype=bool)
    flank = float(np.cos(np.radians(FLANK_DEG)))
    for knife in zones:
        if not knife.depth:
            continue
        reach = float(knife.depths.max())
        lo = np.minimum(knife.starts.min(axis=0), knife.ends.min(axis=0)) - reach
        hi = np.maximum(knife.starts.max(axis=0), knife.ends.max(axis=0)) + reach
        near = np.flatnonzero(keep & np.all((points >= lo) & (points <= hi), axis=1))
        if not len(near):
            continue
        distance, segment = mo.nearest_segments(points[near], knife.starts, knife.ends)
        on = [(np.einsum("ij,ij->i", faces[near], knife.left[segment]) > flank) |
              (np.einsum("ij,ij->i", faces[near], knife.right[segment]) > flank)
              for faces in (normals, landed) if faces is not None]
        # a knife's sliver (or a tip's at its limit) is every ray in its depth from or onto a flank; past the
        # limit, a ray from one flank onto the other alone, as the exact path reads a curved tip
        flanking = np.logical_and.reduce(on) if knife.over and len(on) == 2 else np.logical_or.reduce(on)
        # within some crease's own depth (a curved knife is as thin as its sharpest stretch there)
        within = mo.past_segments(points[near], knife.starts, knife.ends, knife.depths) <= 1e-6
        keep[near] &= ~((within | (distance <= knife.depth + 1e-6)) & flanking)
    return keep


def _caster(mesh: trimesh.Trimesh) -> mo.Caster:
    """The mesh's rays (``meshops_printing.Caster``), made once a mesh: numpy alone, in bounded memory. trimesh's
    own ray engine without embree tests a ray against every triangle whose box its *box* crosses: a 330 000
    triangle sphere's 2000 wall rays held gigabytes and took a minute, and 1.3 million triangles ran out of
    memory."""
    found = getattr(mesh, "_cad_caster", None)
    if found is None or found.count != len(mesh.faces):
        found = mo.Caster(np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int))
        mesh._cad_caster = found
    return found


def _first_hits(mesh: trimesh.Trimesh, origins: np.ndarray, directions: np.ndarray,
                reach: float | None = None) -> tuple[np.ndarray, ...]:
    """Each ray's first hit on ``mesh`` (within ``reach``): where, which ray, which triangle -- of the rays
    that hit."""
    distance, hit = _caster(mesh).first(origins, directions, reach)
    rays = np.flatnonzero(hit >= 0)
    return origins[rays] + directions[rays] * distance[rays, None], rays, hit[rays]


def _inside(body: trimesh.Trimesh, points: np.ndarray) -> np.ndarray:
    """Which ``points`` lie in the closed ``body``'s material (``Caster.inside``)."""
    return _caster(body).inside(points)


def _cover(mesh: trimesh.Trimesh, inward: bool, reach: float | None = None,
           zones: list[_Knife] | None = None) -> tuple[np.ndarray, ...]:
    """One ray from every triangle's centre (``COVER`` of them, by area, on a larger mesh), into the material
    (``inward``) or out of it: each ray's length to a face that looks back at it, its origin, its face's
    normal and the triangle it landed on. Rays that meet nothing, or a face square to them, are dropped, as
    are rays from a knife edge's flanks inside its thin depth (``zones``: the knife family's sliver)."""
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
    origins = mesh.triangles_center[faces] + directions * NUDGE
    locations, rays, hit = _first_hits(mesh, origins, directions, reach)
    if not len(rays):
        return np.zeros(0), np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    # measured from the surface: the origin was nudged 1e-4 along the ray off its own triangle
    length = np.linalg.norm(np.asarray(locations).reshape(-1, 3) - origins[rays], axis=1) + NUDGE
    # a wall's far face looks away from the ray; one square to it (a corner) does not, one under KNIFE_DEG
    # off parallel (a knife edge's other face) does, as the exact path counts it
    facing = _facing(mesh, faces[rays], hit, origins[rays], np.asarray(locations).reshape(-1, 3)) if inward else \
        np.einsum("ij,ij->i", mesh.face_normals[hit], directions[rays]) < -_LOOKS_BACK
    keep = (length > 1e-3) & facing & (length < (reach or float(np.linalg.norm(mesh.extents))))
    if zones:
        keep &= _outside_knives(origins[rays], normals[rays], zones, mesh.face_normals[hit])
    return length[keep], origins[rays][keep], normals[rays][keep], faces[rays][keep], hit[keep]


#: Two triangles meeting at under this many degrees are one curved surface's chords (a sharper crease is the
#: part's own edge): where a surface's offset from its chords is read (``_surface_offset``).
CHORD_DEG = 30.0


def _surface_offset(mesh: trimesh.Trimesh, triangles: np.ndarray, points: np.ndarray) -> np.ndarray:
    """How far the curved surface a mesh stands for lies off each point of its triangle, along the triangle's
    outward normal (signed: outward of the chord positive, a convex surface's): the point's Phong projection onto
    its triangle's corners' tangent planes (by their vertex normals), halved -- exact to second order at a chord's
    middle (a chord turned theta on radius R stands R theta^2 / 8 off its arc). Each corner's normal is that of
    the faces about it that turn from the triangle's own by under ``CHORD_DEG`` (its surface's, not an edge's
    other side: a tube's side strips reach both its rims)."""
    if not len(triangles):
        return np.zeros(0)
    corners = mesh.faces[triangles]
    v = mesh.vertices[corners]
    face = mesh.face_normals[triangles]
    around = mesh.vertex_faces[corners]  # (n, 3, k), -1 padded
    present = around >= 0
    their = mesh.face_normals[np.where(present, around, 0)] * (mesh.area_faces[np.where(present, around, 0)])[..., None]
    alike = present & (np.einsum("ikmj,ij->ikm", mesh.face_normals[np.where(present, around, 0)], face)
                       > math.cos(math.radians(CHORD_DEG)))
    n = (their * alike[..., None]).sum(axis=2)
    n = n / np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-300)
    smooth = np.ones(len(triangles), dtype=bool)
    # barycentric coordinates of each point in its triangle's plane
    e0, e1 = v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]
    rel = points - v[:, 0]
    d00, d01, d11 = (np.einsum("ij,ij->i", e0, e0), np.einsum("ij,ij->i", e0, e1), np.einsum("ij,ij->i", e1, e1))
    d20, d21 = np.einsum("ij,ij->i", rel, e0), np.einsum("ij,ij->i", rel, e1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) > 1e-300, d00 * d11 - d01 * d01, 1.0)
    b1 = (d11 * d20 - d01 * d21) / den
    b2 = (d00 * d21 - d01 * d20) / den
    weights = np.stack([1.0 - b1 - b2, b1, b2], axis=1)
    projected = points[:, None, :] - np.einsum("ikj,ikj->ik", points[:, None, :] - v, n)[:, :, None] * n
    phong = np.einsum("ik,ikj->ij", weights, projected)
    return np.where(smooth, 0.5 * np.einsum("ij,ij->i", phong - points, face), 0.0)


#: Walls of a body, the thinnest first, whose support is read (``_wall_items``): each costs a few hundred rays.
SUPPORT_READ = 24
#: Walls of a body, the thinnest first, refined to the least about their thinnest sample (``_least_wall``: a few
#: hundred rays each): a lattice has thousands of faces under twice the minimum.
REFINE_READ = 200


def _cast(mesh: trimesh.Trimesh):
    """``meshops_printing.wall_support``'s rays on ``mesh``: each ray's distance to the surface and the normal of
    the triangle it lands on."""
    caster = _caster(mesh)

    def cast(origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        distance, hit = caster.first(origins, directions)
        normals = np.zeros((len(distance), 3))
        normals[hit >= 0] = caster.normals_of(hit[hit >= 0])
        return distance, normals

    return cast


def _least_wall(mesh: trimesh.Trimesh, point: np.ndarray, face: int, value: float, step: float,
                zones: list[_Knife] | None = None, across_gap: Any = None) -> tuple[float, np.ndarray, int, int] | None:
    """The least wall about a sampled one: from the sample's place on the surface, ``step`` across it eight
    ways -- each put back on the surface and read by a ray into the material, as the samples are -- to the
    thinnest, the step halved where none is thinner. The random rays land a few a face, and read the skin over a
    round cavity, thinnest at one point, thicker than it is; exact geometry refines its listed walls to their
    least distance alike. A place in a knife edge's own sliver (``zones``) is no wall's, as no sample's there is.
    The thickness, its place, its triangle and the one across; None where none is thinner.

    With ``across_gap`` the least gap about a sampled one, alike: each ray out of the material, to a wall that
    looks back (``_LOOKS_BACK``) and that ``across_gap(from triangles, onto triangles)`` says is no face beside
    the ray's own."""
    caster, normals = _caster(mesh), mesh.face_normals
    best: tuple[float, np.ndarray, int, int] | None = None
    at, tri, least = np.asarray(point, dtype=float), int(face), float(value)
    turn = np.linspace(0.0, 2.0 * math.pi, 8, endpoint=False)
    floor = 1e-3 * step
    for _move in range(40):
        n = normals[tri]
        seed = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = np.cross(n, seed)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        tried = at + step * (np.cos(turn)[:, None] * u + np.sin(turn)[:, None] * v)
        drop, onto = caster.first(tried + n * step, np.broadcast_to(-n, tried.shape), 2.0 * step)
        on = np.flatnonzero(onto >= 0)
        better = False
        if len(on):
            landed, inward = tried[on] + n * (step - drop[on])[:, None], -normals[onto[on]]
            if across_gap is not None:
                inward = -inward  # a gap's rays leave the material
            origin = landed + inward * NUDGE
            length, across = caster.first(origin, inward, GAP_CEILING if across_gap is not None else None)
            met = np.flatnonzero(across >= 0)
            if len(met):
                reach = origin[met] + inward[met] * length[met][:, None]
                if across_gap is not None:
                    walls = (np.einsum("ij,ij->i", normals[across[met]], inward[met]) < -_LOOKS_BACK) & \
                        across_gap(onto[on][met], across[met])
                else:
                    walls = _facing(mesh, onto[on][met], across[met], origin[met], reach)
                if zones:
                    walls &= _outside_knives(origin[met], normals[onto[on][met]], zones, normals[across[met]])
                thick = np.where(walls, length[met] + NUDGE, np.inf)
                k = int(np.argmin(thick))
                if thick[k] < least - 1e-9:
                    at, tri, least = landed[met][k], int(onto[on][met][k]), float(thick[k])
                    best, better = (least, at, tri, int(across[met][k])), True
        if not better:
            step /= 2.0
            if step < floor:
                break
    return best


def _wall_items(thickness: np.ndarray, origins: np.ndarray, faces: np.ndarray, hits: np.ndarray,
                labels: np.ndarray, mesh: trimesh.Trimesh | None = None, judged_below: float | None = None,
                zones: list[_Knife] | None = None) -> list[dict]:
    """The thickness field as items: each face's thinnest sample (``_regions``: ``labels``, per triangle), a face
    and the face its thinnest ray lands on one item -- a wall is read from both its sides, and is one wall --,
    as the exact path lists them. A wall under ``judged_below`` (the rules' unsupported-wall minimum: the only
    walls a verdict can turn on) has its support read off the wall itself, as the exact path reads it
    (``meshops_printing.wall_support``: ``supported``, ``joined_sides``), the ``SUPPORT_READ`` thinnest of a
    body; any other says ``supported`` None. One sampled under twice ``judged_below`` is first refined to the
    least wall about its thinnest sample (``_least_wall``: ``refined`` true), the ``REFINE_READ`` thinnest of a body. Each has how far its thinnest ray's
    length may be off the wall the mesh stands for (``chord_mm``):
    the surfaces' offsets from the chords at its two ends (``_surface_offset``), each along its ray, summed with
    their signs -- a tube's two rows of chords, one convex and one concave, cancel where they lie alike.
    Unsorted and uncapped: ``_wall_ranked`` ranks every body's together."""
    if not len(thickness):
        return []
    own, across = labels[faces], labels[hits]
    order = np.lexsort((thickness, own))
    if mesh is not None:
        inward = -mesh.face_normals[faces]
        landing = origins + inward * thickness[:, None]
        error = _surface_offset(mesh, faces, origins) + _surface_offset(mesh, hits, landing)
        chords = np.abs(error)[order]
    else:
        chords = np.zeros(len(order))
    own, across, values, points = own[order], across[order], thickness[order], origins[order]
    first = np.ones(len(own), dtype=bool)
    first[1:] = own[1:] != own[:-1]
    starts = np.flatnonzero(first)
    counts = np.diff(np.append(starts, len(own)))
    rows = sorted(zip(values[starts], starts, counts), key=lambda row: row[0])
    seen: set[tuple[int, int]] = set()
    items = []
    tried = read = 0  # the walls refined, and those whose support was read, so far
    for value, at, count in rows:
        pair = (int(min(own[at], across[at])), int(max(own[at], across[at])))
        if pair in seen:
            continue
        seen.add(pair)
        item = {"xyz": _p(points[at]), "thickness_mm": _r(float(value), mo.JUDGED), "samples": int(count),
                "supported": None, "sampled": True, "chord_mm": _r(float(chords[at]), 6)}
        place, face, far = points[at], int(faces[order][at]), int(hits[order][at])
        if mesh is not None and judged_below is not None and value < 2.0 * judged_below and tried < REFINE_READ:
            tried += 1
            least = _least_wall(mesh, place + mesh.face_normals[face] * NUDGE, face, float(value),
                                math.sqrt(float(mesh.area) / len(thickness)), zones)
            if least is not None:
                value, place, face, far = least
                inward = -mesh.face_normals[face]
                chord = abs(float((_surface_offset(mesh, np.array([face]), place[None]) +
                                   _surface_offset(mesh, np.array([far]), (place + inward * value)[None]))[0]))
                item.update(xyz=_p(place), thickness_mm=_r(float(value), mo.JUDGED), chord_mm=_r(chord, 6), refined=True)
        if mesh is not None and judged_below is not None and value < judged_below and read < SUPPORT_READ:
            read += 1
            found = mo.wall_support(_cast(mesh), place, mesh.face_normals[face], float(value))
            item.update(supported=found["supported"], joined_sides=found["joined_sides"],
                        free_fraction=found["free_fraction"])
        if mesh is not None:
            # a skin in the layer plane, laid layer on layer: by its two faces, whichever it was read from
            item["lying"] = mo.lying(mesh.face_normals[face], mesh.face_normals[far])
        items.append(item)
    return items


def _least_of(stats: dict, items: list[dict]) -> dict:
    """``stats`` with its least the thinner of the rays' and a refined item's: the summary never reads thicker
    than a finding."""
    refined = [item["thickness_mm"] for item in items if item.get("refined")]
    return {**stats, "min_mm": round(min([stats["min_mm"], *refined]), 3)}


def _wall_ranked(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda item: item["thickness_mm"])[:CAP]


def _wall_stats(thickness: np.ndarray, origins: np.ndarray) -> dict:
    """The thickness field's figures, over every ray that measured a wall: the summary reads the rays the items
    are made of, so it never says a thinner place is not there."""
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
                "location_xyz": [round(float(v), 2) for v in origins[i]],
                "thickness_mm": round(float(thickness[i]), 3),
            }
            for i in thin_idx
        ],
    }


def _wall_method(cover: bool, samples: int) -> str:
    return (f"{samples} rays into the material from points drawn at random over the surface"
            + (", and one from every triangle's centre" if cover else
               f"; no ray from every triangle (the mesh has more than {COVER_MAX_TRIANGLES} triangles)")
            + ", per body: each ray's length to a face turned toward it (within 45 deg); none within a knife edge's "
              "thin depth that starts or lands on its flanks")


def _wall_facts(mesh: trimesh.Trimesh, samples: int, seed: int = 42, keep: dict | None = None,
                split: tuple[list[trimesh.Trimesh], list] | None = None,
                zones: list[_Knife] | None = None, judged_below: float | None = None) -> dict:
    """Ray-cast thickness field, measured one connected body at a time.

    Cast against a whole assembly, a ray leaving one body can cross a mating
    clearance and land on its neighbour, which records the fit gap as a wall.
    A tight-clearance assembly then reports a wall-thickness violation that no
    single part actually has. Splitting first makes that impossible, because
    each body is only ever measured against itself -- with the sealed voids it
    holds (``_bodies``, or ``split``, the bodies split once for every family), so
    the skin over a cavity is one of its walls. A ray from a knife edge's flanks
    inside its thin depth (``zones``) measures the knife's sliver, the knife
    family's alone. On a mesh of at most ``COVER_MAX_TRIANGLES`` triangles every
    triangle adds a ray (``cover``); the figures and the items are of the same rays,
    an item per face of the part and the face across (``_wall_items``).
    """
    bodies, _voids = split if split is not None else _bodies(mesh)
    cover = len(mesh.faces) <= COVER_MAX_TRIANGLES

    def rays(body: trimesh.Trimesh, budget: int, at: int) -> dict:
        found = _wall_facts_single(body, budget, at, zones)
        if "_thickness" in found and cover:
            extra = _cover(body, inward=True, zones=zones)
            found["_thickness"] = np.concatenate([found["_thickness"], extra[0]])
            found["_origins"] = np.vstack([found["_origins"], extra[1]])
            found["_normals"] = np.vstack([found["_normals"], extra[2]])
            found["_faces"] = np.concatenate([found["_faces"], extra[3]])
            found["_hits"] = np.concatenate([found["_hits"], extra[4]])
        if "_thickness" in found:
            found["_items"] = _wall_items(found["_thickness"], found["_origins"], found["_faces"], found["_hits"],
                                          _regions(body)[0], body, judged_below, zones)
            # how far each ray's length may be off the wall the mesh stands for (``_wall_items``: ``chord_mm``)
            landing = found["_origins"] - found["_normals"] * found["_thickness"][:, None]
            found["_chords"] = np.abs(_surface_offset(body, found["_faces"], found["_origins"]) +
                                      _surface_offset(body, found["_hits"], landing))
        return found

    if len(bodies) <= 1:
        facts = rays(mesh, samples, seed)
        if "_thickness" in facts:
            t, o = facts["_thickness"], facts["_origins"]
            if keep is not None:
                keep.update(thickness=t, origins=o, normals=facts["_normals"], chords=facts["_chords"])
            facts = {**_least_of(_wall_stats(t, o), facts["_items"]), "items": _wall_ranked(facts["_items"])}
            facts.update(cover=cover, method=_wall_method(cover, samples))
        return {key: value for key, value in facts.items() if not key.startswith("_")}

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
    pooled_chords: list = []
    pooled_items: list = []
    per_body: list = []
    for i, (body, frac) in enumerate(zip(bodies, share)):
        budget = max(int(round(samples * frac)), 64)
        facts = rays(body, budget, seed + i)
        row = {"body": i, "min_mm": None, "p05_mm": None, "median_mm": None, "samples_valid": 0}
        if "_thickness" in facts:
            stats = _wall_stats(facts["_thickness"], facts["_origins"])
            row.update({key: stats[key] for key in ("min_mm", "p05_mm", "median_mm", "samples_valid")})
            pooled.append(facts["_thickness"])
            pooled_origins.append(facts["_origins"])
            pooled_normals.append(facts["_normals"])
            pooled_chords.append(facts["_chords"])
            pooled_items.extend(facts["_items"])
        per_body.append(row)

    if not pooled:
        return {
            "error": "no valid thickness samples",
            "body_count": len(bodies),
            "per_body": per_body,
        }

    thickness = np.concatenate(pooled)
    origins = np.concatenate(pooled_origins)
    if keep is not None:
        keep.update(thickness=thickness, origins=origins, normals=np.concatenate(pooled_normals),
                    chords=np.concatenate(pooled_chords))
    return {
        "items": _wall_ranked(pooled_items),
        "body_count": len(bodies),
        "measured_per_body": True,
        **_least_of(_wall_stats(thickness, origins), pooled_items),
        "per_body": per_body,
        "cover": cover,
        "method": _wall_method(cover, samples),
    }


def _wall_facts_single(mesh: trimesh.Trimesh, samples: int, seed: int = 42,
                       zones: list[_Knife] | None = None) -> dict:
    """Ray-cast thickness field for ONE connected body: ``samples`` rays, each from a point drawn at random over
    the surface (a triangle by its area, then anywhere on it), straight in along that face's normal to the face it
    leaves through. The points are the surface's, not the tessellation's: a coarse mesh and a fine one of the same
    part are sampled alike. A ray counts when it leaves through a face turned away from its own (at least
    ``KNIFE_DEG`` off parallel, as the exact path counts it): a wall's other side, or a knife edge's; one started by
    a convex edge leaves through the edge's neighbour after a hair, which is no wall."""
    n = max(int(samples), 1)

    # Area weighting needs a positive total. A mesh of only degenerate faces
    # has none, and is not something a thickness field can describe - say so
    # rather than dividing by zero in the sampling.
    total_area = float(mesh.area_faces.sum())
    if not np.isfinite(total_area) or total_area <= 0.0:
        return {
            "samples": 0,
            "note": "no positive face area; mesh is degenerate, thickness not measured",
        }

    origins, face_idx = trimesh.sample.sample_surface(mesh, n, seed=seed)
    directions = -mesh.face_normals[face_idx]
    origins = origins + directions * NUDGE

    locations, ray_ids, hit_tri = _first_hits(mesh, origins, directions)

    if len(ray_ids) == 0:
        return {"error": "ray casting produced no hits", "samples_requested": n}

    thickness = np.linalg.norm(locations - origins[ray_ids], axis=1) + NUDGE  # from the surface, not the nudge
    diag = float(np.linalg.norm(mesh.extents))
    # a wall's two faces look away from each other; a ray that lands on a face meeting its own at a corner
    # (KNIFE_DEG or more between them) measures the corner, not a wall -- a knife edge's sliver is counted,
    # but for rays from inside a knife's thin depth, which the knife family reports once
    opposing = _facing(mesh, face_idx[ray_ids], hit_tri, origins[ray_ids], locations)
    valid = (thickness > 1e-3) & (thickness < diag) & opposing
    if zones:
        valid &= _outside_knives(origins[ray_ids], -directions[ray_ids], zones, mesh.face_normals[hit_tri])
    thickness = thickness[valid]

    if len(thickness) == 0:
        return {"error": "no valid thickness samples", "samples_requested": n}

    # Underscore keys are internal: _wall_facts adds the triangles' rays, pools them across bodies, reads its
    # figures from them and strips them before anything is printed (numpy arrays would not survive json.dumps).
    return {
        "_thickness": thickness,
        "_origins": origins[ray_ids][valid],
        "_normals": -directions[ray_ids][valid],
        "_faces": face_idx[ray_ids][valid],
        "_hits": hit_tri[valid],
    }


def _support_volume_facts(mesh: trimesh.Trimesh, angle_limit: float) -> dict:
    """The column fill under every down-facing surface under the angle limit, down to the part or the plate,
    from a raster of the mesh along Z, and the part's volume (its convex hull's where the mesh is open)."""
    V, F = np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int)
    held = mo.support(V, F, angle_limit, mo.raster_pitch(mesh.extents), plate_z=float(V[:, 2].min()),
                      skip=_at_limit(mesh, angle_limit))
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
    rows = mo.orientation_rows(V, F, mo.ROTATIONS, angle_limit, mo.raster_pitch(mesh.extents), SHALLOW_DEG,
                               at_limit=lambda R: _at_limit(mesh, angle_limit, R))
    volume = np.array((machine or rules.machine_volume({"technology": technology}))["volume_mm"], dtype=float)
    for row in rows:
        m = mesh.copy()
        m.vertices = V @ np.array(row["rotation"]).T
        ov = _overhang_facts(m, angle_limit, regions=False, near=_at_limit(mesh, angle_limit, np.array(row["rotation"])))
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


def _round_hole(origins: np.ndarray, normals: np.ndarray, width: np.ndarray) -> tuple[float, np.ndarray, np.ndarray] | None:
    """The round hole a gap's rays cross (its diameter, a point on its axis and the axis), or None where they
    cross no round hole: rays all as
    long (within 5 %), looking across one axis from all round it (no arc of 110 deg without one: a hole's wall
    is at least 250 deg of its circle, as on exact geometry) and meeting on it (their middles on one line: an
    annular groove's lie on a circle). A mesh's hole is a polygon inside the hole's circle: a ray from one of
    its sides reads the polygon's width, the circle's less the chords' sag, which is given back (the sides
    turn by the least angle between two rays' directions that are not one side's)."""
    if len(width) < 6 or float(width.max()) > 1.05 * float(width.min()) + 1e-3:
        return None
    _, spread, axes = np.linalg.svd(normals, full_matrices=False)
    if spread[2] > 0.1 * spread[1]:
        return None  # the rays look every way, not across one axis
    axis = axes[2]
    turn = np.sort(np.arctan2(normals @ axes[1], normals @ axes[0]))
    steps = np.diff(np.append(turn, turn[0] + 2.0 * math.pi))
    if float(steps.max()) > math.radians(110.0):
        return None
    middles = origins + normals * (width / 2.0)[:, None]
    off = middles - middles.mean(axis=0)
    off -= np.outer(off @ axis, axis)
    if float(np.linalg.norm(off, axis=1).max()) > 0.1 * float(np.median(width)):
        return None  # an annular groove, a slot round a post: its rays do not meet on an axis
    side = steps[steps > math.radians(0.5)]
    diameter = float(np.median(width)) / math.cos(min(float(side.min()) if len(side) else 0.0, math.radians(60.0)) / 2.0)
    return diameter, middles.mean(axis=0), axis


def _gap_facts(mesh: trimesh.Trimesh, samples: int, split: tuple[list[trimesh.Trimesh], list] | None = None) -> dict:
    """Rays out of the material from every triangle of each body to a wall of the same body that faces back
    (within ``KNIFE_DEG``, as on exact geometry: a V groove wider than that is a notch, no slot; not a triangle
    sharing a corner with it, nor a face of the part sharing an edge with its own: ``_regions``):
    the narrow slots, one item a slot -- the faces of the part its rays join, and the faces beside them that
    have such rays too, are one gap (a slot's two walls; a hole's wall, whatever its chords), its narrowest ray
    the item, as the exact path lists a pair of faces once. A gap whose rays cross a round hole (``_round_hole``)
    is no slot but a hole, as on exact geometry: a mesh holds no cylinder, and its holes up to the gaps' reach
    are read here (``holes``, which ``measure`` makes the family of)."""
    found: list[tuple[float, np.ndarray, int]] = []
    holes: list[dict] = []
    defects: list[tuple[float, np.ndarray]] = []
    bodies, _voids = split if split is not None else _bodies(mesh)
    refined = 0
    for body in bodies:
        width, origins, normals, faces, hit = _cover(body, inward=False, reach=GAP_CEILING)
        if not len(width):
            continue
        labels, beside = _regions(body)

        def apart(start: np.ndarray, landed: np.ndarray, body: trimesh.Trimesh = body, labels: np.ndarray = labels,
                  beside: set = beside) -> np.ndarray:
            """Which rays (from triangles ``start`` onto ``landed``) cross a gap: not onto a triangle sharing a
            corner with their own, nor onto a face beside their own (sharing an edge with it: the gap closes to
            nothing at the crease -- an acute corner inside a letter --, its angle, no slot; the exact path
            skips it alike)."""
            corner = (body.faces[start][:, :, None] == body.faces[landed][:, None, :]).any(axis=(1, 2))
            near = np.fromiter(((int(min(x, y)), int(max(x, y))) in beside
                                for x, y in zip(labels[start], labels[landed])), dtype=bool, count=len(start))
            return ~corner & ~near

        shared = ~apart(faces, hit)
        own, other = labels[faces], labels[hit]
        # under GAP_DEFECT_MM the "gap" is faces lying on faces (doubled or overlapping triangles): the mesh's
        # defect, said once (``overlap``), no slot a printer would close
        defect = ~shared & (width < GAP_DEFECT_MM)
        defects += [(float(w), o) for w, o in zip(width[defect], origins[defect])]
        keep = ~shared & ~defect
        width, origins, normals, own, other, faces = (width[keep], origins[keep], normals[keep], own[keep],
                                                      other[keep], faces[keep])
        if not len(width):
            continue
        group = {int(label): int(label) for label in np.unique(np.concatenate([own, other]))}

        def root(label: int) -> int:
            while group[label] != label:
                group[label] = group[group[label]]
                label = group[label]
            return label

        for a, b in [*zip(own.tolist(), other.tolist()), *((a, b) for a, b in beside if a in group and b in group)]:
            group[root(a)] = root(b)
        gap = np.fromiter((root(label) for label in own.tolist()), dtype=np.int64, count=len(own))
        for which in np.unique(gap):
            mine = np.flatnonzero(gap == which)
            at = mine[int(np.argmin(width[mine]))]
            least, place = float(width[at]), origins[at]
            hole = _round_hole(origins[mine], normals[mine], width[mine])
            if hole is not None:
                tilt = math.degrees(math.acos(min(1.0, abs(float(hole[2][2])))))
                holes.append({"xyz": _p(hole[1]), "diameter_mm": _r(hole[0], mo.JUDGED), "axis": _p(hole[2]),
                              "orientation": "vertical" if tilt < 10.0 else "horizontal" if tilt > 80.0 else "inclined",
                              "teardrop": False, "samples": int(len(mine))})
                continue
            if least < REFINE_GAP_MM and refined < REFINE_READ:
                # a slot's narrowest is seldom under a triangle's centre: the least about it, as a wall's
                refined += 1
                nearer = _least_wall(body, place - normals[at] * NUDGE, int(faces[at]), least,
                                     math.sqrt(float(body.area) / max(1, len(body.faces))), across_gap=apart)
                if nearer is not None:
                    least, place = nearer[0], nearer[1]
            found.append((least, place, int(len(mine))))
    overlap = None
    if defects:
        least = min(defects, key=lambda row: row[0])
        overlap = {"xyz": _p(least[1]), "gap_mm": _r(least[0], 5), "samples": len(defects)}
    found.sort(key=lambda row: row[0])
    items = [{"xyz": _p(point), "gap_mm": _r(value, mo.JUDGED), "samples": count} for value, point, count in found[:CAP]]
    holes.sort(key=lambda item: item["diameter_mm"])
    return {"items": items, "count": len(found), "reported_below_mm": GAP_CEILING, "_holes": holes,
            "min_mm": items[0]["gap_mm"] if items else None, "overlap": overlap, "defect_below_mm": GAP_DEFECT_MM,
            "method": "a ray out of the material from every triangle to a wall of the same body that looks back "
                      "(within 45 deg), not a face beside its own, one item a slot: the faces its rays join, "
                      "its narrowest refined to the least about it; a gap whose rays cross a round hole is a "
                      f"hole (holes), no gap; under {GAP_DEFECT_MM:g} mm, faces lying on faces: the mesh's "
                      "defect (overlap), no gap"}


def _some(points: np.ndarray, most: int = 2000) -> np.ndarray:
    """At most ``most`` of ``points``, spread over them all."""
    points = np.asarray(points, dtype=float)
    return points if len(points) <= most else points[np.linspace(0, len(points) - 1, most).round().astype(int)]


#: The spacing of the points a body is read as for its clearances: its area over this many -- a triangle with
#: a side over twice that gets a grid of them (those triangles ``CLEARANCE_POINTS`` between them), any other
#: its centre alone. What bounds the family's memory: a point a triangle and these.
CLEARANCE_POINTS = 30_000
#: Point-triangle distances one body gets against another, at most: what bounds the family's time (a few
#: seconds a pair of bodies). Past it the least distance found stands with how much less it may be.
CLEARANCE_PAIRS = 3_000_000
#: A pair of bodies whose points stay this far apart (less what their points leave uncovered) is above every
#: published clearance (all under 1 mm): its distance is the points', with that margin (as the exact path's).
CLEARANCE_EXACT_BELOW = 1.5


class _Cloud:
    """A body as points for its clearances: every triangle's centre, and across each triangle with a side
    over twice the points' spacing (``CLEARANCE_POINTS``) a grid of them -- each point its triangle's own, in a
    tree --, so no place on a triangle is farther than ``cover`` from one of that triangle's points; and its
    ``probes``, the places its distance to another body is read at: those points and its corners."""

    def __init__(self, body: trimesh.Trimesh) -> None:
        from scipy.spatial import cKDTree

        self.triangles = np.asarray(body.triangles, dtype=float)
        longest = np.linalg.norm(self.triangles - np.roll(self.triangles, 1, axis=1), axis=2).max(axis=1)
        big = longest > 2.0 * math.sqrt(float(body.area) / CLEARANCE_POINTS)
        points, owner = [self.triangles.mean(axis=1)], [np.arange(len(self.triangles))]
        # a triangle's farthest place from its centre is a corner: two thirds of a median, under its longest side
        self.cover = 0.67 * float(longest[~big].max()) if (~big).any() else 0.0
        if big.any():
            grid, of = mo.spread_points(self.triangles[big], cap=CLEARANCE_POINTS, owners=True)
            points.append(grid)
            owner.append(np.flatnonzero(big)[of])
            # the grid's rows and points lie a spacing apart (a sixtieth of a triangle's longest side where that
            # is more): no place is farther than their diagonal's half from one
            area = float(np.asarray(body.area_faces)[big].sum())
            self.cover = max(self.cover, 0.75 * max(math.sqrt(area / CLEARANCE_POINTS), float(longest[big].max()) / 60.0))
        self.points, self.owner = np.vstack(points), np.concatenate(owner)
        self.probes = np.vstack([np.asarray(body.vertices, dtype=float), self.points])
        self.tree = cKDTree(self.points)


def _least_between(one: _Cloud, other: _Cloud, reach: float) -> tuple[float, np.ndarray, float] | None:
    """The least distance from ``one``'s probes to ``other``'s surface within ``reach``: the distance, the
    middle of its two ends, and how much less it may be (0 where it is the least). Each probe's nearest of
    the other's points bounds its distance to the surface from above and (less the other's ``cover``) from
    below; where that could be under ``CLEARANCE_EXACT_BELOW``, the probes that could hold the least are
    measured against the triangles near them, exactly, the nearest first, until none left could be nearer or
    ``CLEARANCE_PAIRS`` distances are spent -- then the least found stands, and the bound of the probes not
    measured says how much less it may be. None where no probe comes within reach."""
    from scipy.spatial import cKDTree

    rough, nearest = other.tree.query(one.probes, distance_upper_bound=reach + other.cover)
    order = np.argsort(rough)
    order = order[np.isfinite(rough[order])]
    if not len(order):
        return None
    first = order[0]
    best, ends = float(rough[first]), (one.probes[first], other.points[nearest[first]])
    if best - other.cover > CLEARANCE_EXACT_BELOW:
        return best, (ends[0] + ends[1]) / 2.0, other.cover
    spent, at, block = 0, 0, 256
    while at < len(order) and rough[order[at]] - other.cover <= best:
        probes = order[at:at + block]
        # the other's points within the least so far (and its cover) of each: their triangles
        near = cKDTree(one.probes[probes]).sparse_distance_matrix(other.tree, best + other.cover, output_type="ndarray")
        pair = np.unique(near["i"].astype(np.int64) * len(other.triangles) + other.owner[near["j"]])
        if spent + len(pair) > CLEARANCE_PAIRS:
            if block <= 16:
                break  # the budget is spent: the probes from here on are not measured
            block //= 4
            continue
        at, block, spent = at + len(probes), min(2 * block, 8192), spent + len(pair)
        which, triangle = pair // len(other.triangles), pair % len(other.triangles)
        for begin in range(0, len(pair), 200_000):
            rows = slice(begin, begin + 200_000)
            start = one.probes[probes[which[rows]]]
            closest = trimesh.triangles.closest_point(other.triangles[triangle[rows]], start)
            distance = np.linalg.norm(closest - start, axis=1)
            k = int(distance.argmin())
            if distance[k] < best:
                best, ends = float(distance[k]), (start[k], closest[k])
    # what the probes not measured could still hold
    left = float(rough[order[at]] - other.cover) if at < len(order) else math.inf
    return best, (ends[0] + ends[1]) / 2.0, best - max(0.0, min(best, left))


def _clearance_facts(mesh: trimesh.Trimesh, split: tuple[list[trimesh.Trimesh], list] | None = None) -> dict:
    """The least distance between each pair of bodies within ``CLEARANCE_REACH`` (``_least_between``, both
    ways), a pair that pass through each other (``overlap``) and a body that lies wholly in another's material
    (``overlap`` with ``inside``: the body). Bounded: each body is read as points (``_Cloud``: a few a triangle)
    and a pair gets at most ``CLEARANCE_PAIRS`` exact distances each way; a distance the budget cut short says
    so (``exact`` false, ``uncertainty_mm``: how much less it may be)."""
    bodies, _voids = split if split is not None else _bodies(mesh)
    items = []
    clouds: dict[int, _Cloud] = {}

    def cloud(at: int) -> _Cloud:
        if at not in clouds:
            clouds[at] = _Cloud(bodies[at])
        return clouds[at]

    hair = 1e-4 * float(np.linalg.norm(mesh.extents))
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            a, b = bodies[i], bodies[j]
            lo, hi = np.maximum(a.bounds[0], b.bounds[0]), np.minimum(a.bounds[1], b.bounds[1])
            if float(np.max(lo - hi)) > CLEARANCE_REACH:
                continue
            # one body's corners inside the other's material: they pass through each other, or (every corner)
            # one lies wholly in the other -- read before any distance: a body deep inside another is far from
            # its surface. A void's shell is its solid's own, never a body here; each corner is read a hair
            # inside its own body, so bodies that only touch -- along a face, an edge -- share no inside
            a_in_b = _inside(b, _some(a.vertices - a.vertex_normals * hair)) if b.is_watertight else np.zeros(1, dtype=bool)
            b_in_a = _inside(a, _some(b.vertices - b.vertex_normals * hair)) if a.is_watertight else np.zeros(1, dtype=bool)
            if a_in_b.any() or b_in_a.any():
                inside = i if a_in_b.all() else j if b_in_a.all() else None
                held = bodies[inside] if inside is not None else None
                items.append({"xyz": _p(held.bounds.mean(axis=0) if held is not None else (lo + hi) / 2.0),
                              "distance_mm": 0.0, "kind": "overlap", "bodies": [i, j], "exact": True,
                              **({"inside": inside, "inside_volume_mm3": _r(abs(float(held.volume)), 2)}
                                 if held is not None else {})})
                continue
            found = [got for got in (_least_between(cloud(i), cloud(j), CLEARANCE_REACH),
                                     _least_between(cloud(j), cloud(i), CLEARANCE_REACH)) if got is not None]
            if not found:
                continue
            distance, middle, _ = min(found, key=lambda got: got[0])
            if distance > CLEARANCE_REACH:
                continue
            # how much less it may be: the most either way's unmeasured points allow
            slack = max(distance - (got[0] - got[2]) for got in found)
            items.append({"xyz": _p(middle), "distance_mm": _r(distance, mo.JUDGED),
                          "kind": "contact" if distance <= 1e-6 else "gap", "bodies": [i, j],
                          "exact": bool(slack <= 1e-9), "uncertainty_mm": _r(max(0.0, slack), 4)})
    items.sort(key=lambda item: item["distance_mm"])
    return {"items": items[:CAP], "count": len(items), "body_count": len(bodies), "reported_below_mm": CLEARANCE_REACH,
            "min_mm": items[0]["distance_mm"] if items else None,
            "budget": {"distances_per_pair": CLEARANCE_PAIRS, "exact_below_mm": CLEARANCE_EXACT_BELOW},
            "method": "each body's corners and points across its triangles; a point's nearest of the other body's "
                      "points bounds its distance to that body, and the points that could hold the least are "
                      "measured against the triangles near them exactly (where the bodies may come within "
                      "exact_below_mm; distances_per_pair at most each way: past it exact is false and "
                      "uncertainty_mm says how much less the distance may be); bodies that pass through each "
                      "other, or one inside another, are overlap"}


class _Field:
    """The mesh's voxel field and cavities, made once for the families that read them."""

    def __init__(self, mesh: trimesh.Trimesh) -> None:
        V, F = np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int)
        self.pitch, self.ball = mo.field_pitch(mesh.extents)
        self.grid = mo.voxels(V, F, self.pitch, pad=mo.ball_pad(self.ball, self.pitch))
        self.cavities, self.labels = mo.cavities(self.grid, self.ball, caster=_caster(mesh))


def _trapped_facts(field: _Field, walls: dict, open_mesh: bool = False,
                   voids: list[trimesh.Trimesh] | None = None) -> dict:
    """The cavities: those of the voxel field (``meshops_printing.cavities``: air wider than its way out,
    whatever its shape), each with its volume, its openings -- every throat measured on the triangles -- and the
    thinnest wall round it (the wall samples whose outside lies in it); and every sealed void's own shell
    (``voids``, from ``_bodies``), exactly, as exact geometry reads a solid's inner shells: its volume the
    shell's, whatever its size (a void under the field's voxels is found by its shell alone). On a mesh with an
    open body (``open_mesh``) a cavity's openings may be the mesh's own holes, no escape hole: its openings are
    not measured (None), never read as escape holes or as none."""
    grid, labels = field.grid, field.labels
    near: dict[int, tuple[float, float]] = {}
    if walls.get("thickness") is not None:
        probes = walls["origins"] + walls["normals"] * (0.75 * grid.pitch + 1e-4)
        marks = labels[grid.index(probes)]
        for k in np.unique(marks[marks >= 0]):
            mine = np.flatnonzero(marks == k)
            thinnest = mine[int(walls["thickness"][mine].argmin())]
            near[int(k)] = (float(walls["thickness"][thinnest]), float(walls["chords"][thinnest]))
    items = [mo.trapped_item(cavity, grid.pitch) for cavity in field.cavities]
    for k, item in enumerate(items):
        # the thinnest wall round it, and how far that ray's length may be off the wall the mesh stands for
        wall, chord = near.get(k, (None, None))
        item.update(xyz=_p(item["xyz"]), min_wall_mm=_r(wall, mo.JUDGED), min_wall_chord_mm=_r(chord, 6))
    for void in voids or ():
        # a void's triangles face its own air: the voxel cavity just off them, if the field holds one
        some = np.linspace(0, len(void.faces) - 1, min(len(void.faces), 24)).round().astype(int)
        k = mo.cavity_at(grid, labels, void.triangles_center[some], void.face_normals[some])
        exact = {"xyz": _p(void.center_mass if void.is_volume else void.bounds.mean(axis=0)),
                 "volume_mm3": _r(abs(float(void.volume)), 2), **mo.SEALED_EXACT}
        if k is None:
            items.append({**exact, "min_wall_mm": None})
        else:
            items[k].update(exact)
    if open_mesh:
        for item in items:
            item.update(sealed=None, escape_holes=None, escape_hole_diameters_mm=None, min_escape_hole_mm=None,
                        escape_hole_uncertainty_mm=None)
    items.sort(key=lambda item: (item["escape_holes"] if item["escape_holes"] is not None else -1,
                                 -(item["volume_mm3"] or 0)))
    note = {"openings_not_measured": "the mesh has an open body: a cavity's openings may be its holes, not escape "
                                     "holes, and are not measured"} if open_mesh else {}
    return {**note, "items": items[:CAP], "count": len(items),
            "sealed_count": sum(1 for item in items if item["sealed"]),
            "trapped_volume_mm3": _r(sum(item["volume_mm3"] or 0 for item in items), 2),
            "pitch_mm": _r(field.pitch, 4), "ball_radius_mm": _r(field.ball, 3), "method": mo.TRAPPED_METHOD}


def _section_facts(field: _Field) -> dict:
    found = mo.sections(field.grid)
    items = []
    if found["thickness_mm"] is not None:
        items.append({"xyz": _p(found["center"]), "thickness_mm": _r(found["thickness_mm"], mo.JUDGED),
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
    normals, centers = np.asarray(mesh.face_normals), np.asarray(mesh.triangles_center)  # read once: a mesh's
    tilt = mo.angles(normals)                                                             # arrays are hashed a read
    areas = np.asarray(mesh.area_faces)
    edges = [0.5, 5.0, 10.0, 15.0, SHALLOW_DEG]
    shallow = (tilt > edges[0]) & (tilt < SHALLOW_DEG)
    items = []
    # the largest CAP regions are listed: a scan's shallow surface is thousands of them
    regions = sorted(_components(mesh, shallow), key=lambda region: -float(areas[region].sum()))
    for region in regions[:CAP]:
        mean = float(np.average(tilt[region], weights=np.maximum(areas[region], 1e-12)))
        items.append({"xyz": _p(centers[region].mean(axis=0)), "angle_deg": _r(mean, 3),
                      "area_mm2": _r(float(areas[region].sum()), 3),
                      "cusp_mm": _r(layer * np.cos(np.radians(mean)), 4),
                      "step_width_mm": _r(layer / np.tan(np.radians(mean)), 4),
                      "facing": "up" if float(normals[region, 2].mean()) > 0 else "down"})
    return {"items": items, "count": len(regions), "layer_height_mm": layer, "shallow_below_deg": SHALLOW_DEG,
            "area_by_angle_mm2": {f"{edges[k]:g}-{edges[k + 1]:g}deg":
                                  _r(float(areas[shallow & (tilt >= edges[k]) & (tilt < edges[k + 1])].sum()), 2)
                                  for k in range(4)},
            "area_mm2": _r(float(areas[shallow].sum()), 2)}


def _knife_facts(mesh: trimesh.Trimesh, options: dict, zones: list[_Knife] | None = None) -> dict:
    """The knife edges (``_knife_chains``; ``zones``, the walls' own, where made): each chain's length, angle
    (its creases' median by length) and thin depth (as the exact path's)."""
    from cad._internal.dfm import printing as rules

    minimum = rules.wall_minimum(options)
    items = []
    chains = zones if zones is not None else _knife_chains(mesh, minimum)
    near = [knife for knife in chains if not knife.knife and not knife.over and knife.slack > 1e-3]
    for knife in chains:
        if not knife.knife:
            continue  # at the limit within its slack, or over it: the walls' zone, no knife
        middle = np.vstack([knife.starts, knife.ends]).mean(axis=0)
        items.append({"xyz": _p(middle), "angle_deg": _r(knife.angle, 3), "length_mm": _r(knife.length, 4),
                      "thickness_mm": 0.0, "thin_depth_mm": _r(knife.depth, 4),
                      "thin_area_mm2": _r(knife.depth * knife.length if knife.depth else None, 4)})
    items.sort(key=lambda item: item["angle_deg"])
    return {"items": items[:CAP], "count": len(items), "knife_below_deg": mo.KNIFE_DEG, "min_wall_mm": minimum,
            "fold_below_deg": mo.FOLD_DEG, "length_mm": _r(sum(item["length_mm"] for item in items), 4),
            # edges within the mesh's own angular deflection of 45 deg: at the limit, not judged
            "at_limit_count": len(near), "at_limit_length_mm": _r(sum(knife.length for knife in near), 4),
            "at_limit_tolerance_deg": _r(max((knife.slack for knife in near), default=0.0), 4),
            "method": f"convex creases between triangles of material under {CREASE_DEG:g} deg, chained by shared "
                      "corners, a chain a knife where its angle (its creases' median by length) is under "
                      "knife_below_deg, however short; a crease under fold_below_deg is a fold of the "
                      "tessellation, no knife"}


def _build_volume_facts(mesh: trimesh.Trimesh, options: dict) -> dict:
    from cad._internal.dfm import printing as rules

    return mo.build_fit(mesh.bounds[0], mesh.bounds[1], rules.machine_volume(options),
                        np.asarray(mesh.vertices, dtype=float))


def _wall_minimum(options: dict) -> float | None:
    from cad._internal.dfm import printing as rules

    return rules.wall_minimum(options)


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
    """Flag meshes whose units are probably not millimetres (``_common.units_doubt``: the test every process
    and source takes). A metres export reads 0.05 x 0.02 x 0.04, under the 0.1 mm on-plate tolerance: every
    down-facing face reads as resting on the plate, and the part looks like a flawless print."""
    diag = float(np.linalg.norm(mesh.extents))
    units = mesh.metadata.get("source_units", "mm")
    return {"bbox_diagonal_mm": round(diag, 4), **units_doubt(diag, f"read as {units}, it is")}


def measure(mesh: trimesh.Trimesh, samples: int, angle_limit: float, options: dict | None = None) -> dict:
    """Every family: the mesh, its scale, overhangs and bridges, wall thickness, gaps, clearances between
    bodies, trapped volumes, the build volume, bed contact, stair-stepping, support volume and sections.
    ``options``: the check's (``technology``, ``layer_height``, ``build_volume``)."""
    resolved = _options(options, angle_limit)
    kept: dict = {}
    try:  # the bodies, split once for the families that read them
        split = _bodies(mesh)
    except Exception:  # noqa: BLE001 - each family then fails in its own words
        split = None
    try:  # the knife edges' slivers, which the walls leave to the knife family
        zones = _knife_zones(mesh, resolved)
    except Exception:  # noqa: BLE001 - the knife family says so; the walls then count every ray
        zones = None
    report = {
        "technology": resolved["technology"],
        "mesh": _safe(_mesh_facts, mesh, split),
        "scale": _safe(_scale_hint, mesh),
        "overhangs": _safe(_overhang_facts, mesh, angle_limit, resolved["layer"], True,
                           float(resolved.get("nozzle") or mo.OVERHANG_REACH_MM)),
        "wall_thickness": _safe(_wall_facts, mesh, samples, 42, kept, split, zones, _wall_minimum(resolved)),
        "gaps": _safe(_gap_facts, mesh, samples, split),
        "clearances": _safe(_clearance_facts, mesh, split),
        "build_volume": _safe(_build_volume_facts, mesh, resolved),
        "bed": _safe(_bed_facts, mesh),
        "knife_edges": _safe(_knife_facts, mesh, resolved, zones),
        "stair_stepping": _safe(_stair_facts, mesh, resolved["layer"]),
        "support_volume": _safe(_support_volume_facts, mesh, angle_limit),
    }
    report["bridges"] = _bridge_facts(report["overhangs"])
    # A mesh holds no cylinder: its round holes are the gaps whose rays cross one, up to the gaps' reach -- past
    # every published minimum hole (1.5 mm at most). A larger hole is read as what it is to a printer: its crown
    # an overhang, a bridge of its span.
    found = report["gaps"].pop("_holes", None)
    report["holes"] = {"error": report["gaps"]["error"]} if "error" in report["gaps"] else {
        "items": (found or [])[:CAP], "count": len(found or []), "read_below_mm": GAP_CEILING,
        "method": "the gaps whose rays cross a round hole: all as long (within 5 %), from all round one axis (no "
                  "arc of 110 deg without one) and meeting on it; the diameter the rays', with the sag of the "
                  "hole's chords given back. Holes over read_below_mm across are not read as holes: their "
                  "crowns are overhangs and bridges"}
    # a body wholly inside another's material adds nothing to the part: its volume is counted once
    nested = {item["inside"]: item for item in report["clearances"].get("items") or () if item.get("inside") is not None}
    if nested and isinstance(report["mesh"].get("volume_mm3"), (int, float)):
        report["mesh"]["volume_mm3"] = round(report["mesh"]["volume_mm3"] - sum(
            item["inside_volume_mm3"] or 0.0 for item in nested.values()), 1)
        report["mesh"]["bodies_inside_another"] = len(nested)
    try:
        field = _Field(mesh)
    except Exception as exc:  # noqa: BLE001 - both families say so
        failed = {"error": f"{type(exc).__name__}: {exc}".splitlines()[0][:300]}
        report["trapped_volumes"], report["sections"] = failed, dict(failed)
    else:
        open_mesh = isinstance(report.get("mesh"), dict) and report["mesh"].get("watertight") is False
        report["trapped_volumes"] = _safe(_trapped_facts, field, kept, open_mesh, split[1] if split else None)
        report["sections"] = _safe(_section_facts, field)
    # What a mesh does not hold: no cylinder's axis, no face to read a pin or a raised detail by. Their rules
    # judge nothing here, and the result says so (``rules``' ``not_measured``). A pin is a wall to a mesh, and
    # the wall rules judge it.
    report["not_measured"] = {family: "a mesh holds no axis or face to read them by" for family in ("pins", "details")}
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

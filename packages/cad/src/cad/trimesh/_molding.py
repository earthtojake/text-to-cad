"""Injection molding's measurements of a triangle mesh, with trimesh: draft, undercut
candidates and projected area along one pull, and the candidate pulls ranked.

Facts, never verdicts: nothing here compares a figure against a resin's, a
texture's or a tool's limit. ``cad.<type>.dfm(..., process="molding")`` turns
the report into findings (``cad.trimesh._check``); ``cad.trimesh.molding`` and
``cad.trimesh.pulls`` hand it back as data.

Draft is measured per triangle as the angle between the face and the pull
axis: 0 means the face is parallel to the pull (no draft), 90 means it is
perpendicular to it (a top or bottom face). Faces at or above ``wall_limit``
from the pull axis are not counted as walls. A flat face is pooled by normal
and read exactly; a CURVED face is pooled by the surface it lies on and read at
the 5th percentile of that surface's area, because a facet of a curved face is
a chord and chords scatter -- ``spread_deg`` reports that scatter and bounds how
far low the reading can be. A curved face merely TANGENT to the pull is
reported apart from a flat zero-draft wall because its area is a tessellation
artifact. Which mold half forms a face, whether a parting line makes it an
undercut, and side actions are not determined here. The undercut family is a
straight-pull occlusion test: a face whose withdrawal ray is blocked by the
part itself is reported as a candidate. Wall thickness is not measured here: it
is 3D printing's family (``_printing``).

A family that fails leaves an ``error`` field where its facts would be, and the
report says so (``partial``, ``partial_sections``), so a report missing a family
never reads as one whose part had nothing to find.
"""

from __future__ import annotations

import numpy as np
import trimesh

from cad._internal import meshops_molding as ops

# Length units a mesh file may carry, as a factor to millimetres: an STL is unitless, so the caller
# states which one (the check's one table).
from cad._internal.manufacturing import UNITS_MM as _UNITS_MM

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_BINS_DEG = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
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
    """Read a mesh file and prepare it as ``_prepared`` does."""
    mesh = trimesh.load(path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    return _prepared(mesh, units)


def _prepared(mesh: trimesh.Trimesh, units: str = "mm") -> trimesh.Trimesh:
    """Scale a mesh to millimetres and drop degenerate faces.

    A zero-area triangle -- build123d exports a couple on any sphere -- makes
    trimesh's face normal NaN, and a NaN then reaches the report as a bare
    `NaN` token that strict JSON parsers reject.
    """
    if units not in _UNITS_MM:
        raise ValueError(f"units is one of {', '.join(sorted(_UNITS_MM))}, not {units!r}")
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
    """`z`, `+z`, `-y`, or `x,y,z` components, normalised (``meshops_molding.pull_vector``).

    A leading sign belongs to an AXIS NAME only. `-1,0,1` is a vector whose
    first component is negative, not the negation of `1,0,1`: reading the sign
    as global turns it into `(-1,0,-1)` and measures a different axis than the
    one asked for.
    """
    return ops.pull_vector(spec)


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
    # repair=False: the default repairs each piece through networkx, which the library does not require.
    parts = list(mesh.split(only_watertight=False, repair=False))
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
                   smooth_deg: float = 45.0, taller_than_its_bounds: float = 3.0,
                   crosses_across: float = 0.6) -> np.ndarray:
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

    # Size alone is not enough either, because a mesher is free to build a wall
    # out of triangles that each span its whole height: OCCT fans a small bore,
    # so every facet reaches the full depth and the region is no taller than the
    # facets bounding it. A real tangent line is a CROSSING -- the surface passes
    # through parallel, so the leaning neighbours sit on either side of the
    # region ALONG the pull. Around a fanned bore they sit beside it, spanning
    # the same depth, and the two groups have the same centre. Measured: a
    # sphere's band separates by 0.89 to 1.67 of its own height, the tray's
    # 4.5 mm bores by 0.33.
    up_sum = np.zeros(len(regions))
    up_count = np.zeros(len(regions))
    down_sum = np.zeros(len(regions))
    down_count = np.zeros(len(regions))
    center = mesh.triangles_center @ pull
    for near, far in ((left, right), (right, left)):
        sel = (owner[near] >= 0) & (np.abs(along[far]) > tol)
        if not sel.any():
            continue
        index = owner[near][sel]
        lean, where = along[far][sel], center[far][sel]
        np.add.at(up_sum, index[lean > tol], where[lean > tol])
        np.add.at(up_count, index[lean > tol], 1.0)
        np.add.at(down_sum, index[lean < -tol], where[lean < -tol])
        np.add.at(down_count, index[lean < -tol], 1.0)
    crossing = np.zeros(len(regions))
    both = (up_count > 0) & (down_count > 0)
    crossing[both] = np.abs(up_sum[both] / up_count[both] - down_sum[both] / down_count[both])

    verdict = (above & below
               & (height <= taller_than_its_bounds * np.maximum(bound, 1e-9))
               & (crossing >= crosses_across * np.maximum(height, 1e-9)))
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
            "per-triangle angle to the pull axis; flat faces pooled by normal, curved faces "
            "pooled by surface and read at the 5th percentile of their area; "
            "faces at or above wall_limit_deg from the pull are not walls"
        ),
    }
    if walls.any():
        # Tangent bands are excluded here for the same reason they are excluded
        # from the zero-draft wall area: where a fillet sweeps THROUGH parallel
        # its crossing facet is not a wall at any draft, and read as one it made
        # this figure move with the mesh (0.308 deg coarse against 2.000 fine on
        # the same 2 deg wall) -- the defect min_wall_draft exists to avoid.
        # Flat faces pool by normal, which is exact for them: every facet of a
        # planar wall carries the surface's own normal. Curved faces pool by the
        # SURFACE, because a facet of one is a chord and a chord tilts less than
        # what it cuts -- read per normal, a 3 degree cone became 318 separate
        # "faces" and the lowest chord among them was reported as the part's
        # minimum.
        measurable = walls & ~tangent
        pooled = (_pooled_faces(mesh, measurable & ~curved, pull, along, limit=None, draft=draft,
                                zero_tol=zero_tol, curved=curved)
                  + _surface_faces(mesh, measurable & curved, pull, along, draft, zero_tol))
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
            "method": (
                f"flat faces pooled by normal and read exactly; curved faces pooled by SURFACE and "
                f"read at the 5th percentile of their area; both above {round(floor, 2)} mm2 "
                "(0.1% of surface area), tangent bands excluded"),
        }
        if worst["surface"] == "curved":
            result["min_wall_draft"]["spread_deg"] = worst["spread_deg"]
            # A curved face is read from chords, and chords scatter. Over the
            # surface that scatter cancels; what it leaves is a figure whose
            # trustworthiness the spread states. A flat face has no such term,
            # and a reading of zero needs no allowance -- it is already the worst
            # case, and no chord hides draft below none.
            if worst["spread_deg"] > 1.0 and worst["draft_deg"] > zero_tol:
                result["min_wall_draft"]["reading_note"] = (
                    f"this came off a CURVED face whose draft varies by {worst['spread_deg']} deg "
                    "across it, so it is one figure for a face that does not have one: the 5th "
                    "percentile of its area, with area_mm2 the whole face's. On a face whose draft "
                    "SHOULD be uniform -- a conic wall, a drafted bore -- that spread is the "
                    "export's tessellation rather than the part, because a facet is a chord and a "
                    "chord tilts less than the surface it cuts; one 3.000 deg cone settled at 2.85 "
                    "once its facets agreed to within half a degree and read 0.56 when they "
                    "scattered over ten. Re-export finer before citing this against a limit."
                )
        i = int(np.argmin(np.where(walls, draft, np.inf)))
        result["min_facet_draft"] = {
            "draft_deg": round(float(draft[i]), 3),
            "area_mm2": round(float(areas[i]), 4),
            "location_xyz": [round(float(v), 2) for v in centers[i]],
            "note": "one triangle; use min_wall_draft for a figure that does not move with the mesh",
        }
        for g in pooled:
            g.pop("_members", None)
        result["lowest_draft_wall_faces"] = [
            {"draft_deg": g["draft_deg"], "area_mm2": g["area_mm2"], "surface": g["surface"],
             **({"spread_deg": g["spread_deg"]} if "spread_deg" in g else {}),
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


def _surface_faces(mesh: trimesh.Trimesh, sel: np.ndarray, pull: np.ndarray, along: np.ndarray,
                   draft: np.ndarray, zero_tol: float, smooth_deg: float = 45.0,
                   quantile: float = 0.05) -> list:
    """Pool a CURVED face's facets by the surface they lie on, not by their normals.

    A facet of a curved face is a chord, and pooling by rounded normal gives
    each chord a face of its own: one 3 degree cone came back as 318 "faces" of
    10 to 60 mm2 apiece, and the lowest of them -- an outlier the mesher happened
    to leave -- was reported as the part's minimum wall draft at 1.9 degrees.
    The surface is one face. Pooled as one, the same cone reads 2.98 at every
    tessellation from 76 facets to 1778.

    What is reported for it is the draft at the `quantile` of its area, lowest
    first, not the mean and not the minimum. The mean would bury a real
    low-draft band on a surface whose draft varies -- a sphere's wall near its
    equator -- and the minimum is the chord outlier all over again. At 5% of
    area the figure matches the old one exactly wherever the old one was right
    (a sphere reads 2.467 and 4.221 as before, every zero-draft wall reads 0.0)
    and drops the outliers where it was not.

    `spread_deg` is the same quantile from the other end minus this one: on a
    surface whose facets should agree it is the tessellation's own scatter, and
    a large value says the export is too coarse to read this face from.
    """
    groups: list = []
    if not sel.any():
        return groups
    adjacency = mesh.face_adjacency
    if not len(adjacency):
        return groups
    smooth = adjacency[np.degrees(mesh.face_adjacency_angles) < smooth_deg]
    if len(smooth):
        left, right = smooth[:, 0], smooth[:, 1]
        smooth = smooth[sel[left] & sel[right]]
    areas = mesh.area_faces
    centers = mesh.triangles_center
    heights = mesh.triangles @ pull
    for surface in trimesh.graph.connected_components(smooth, nodes=np.where(sel)[0], min_len=1):
        area = float(areas[surface].sum())
        if area <= 0:
            continue
        order = surface[np.argsort(draft[surface])]
        share = np.cumsum(areas[order]) / area
        low = float(draft[order][int(np.searchsorted(share, quantile))])
        high = float(draft[order][min(int(np.searchsorted(share, 1.0 - quantile)), len(order) - 1)])
        weight = areas[surface]
        groups.append({
            "normal": [round(float(v), 3) for v in
                       (mesh.face_normals[surface] * weight[:, None]).sum(axis=0) / area],
            "area_mm2": round(area, 2),
            "centroid_xyz": [round(float(v), 2) for v in
                             (centers[surface] * weight[:, None]).sum(axis=0) / area],
            "extent_along_pull_mm": round(float(heights[surface].max() - heights[surface].min()), 2),
            "triangle_count": int(len(surface)),
            "draft_deg": round(low, 3),
            "spread_deg": round(high - low, 3),
            "surface": "curved",
            "opens_toward": _opens(float(np.average(along[surface], weights=weight)), zero_tol),
            "_members": surface,
        })
    return groups


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
            "the usual range of an injection-molded part. Give the file's real units (--units)."
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


def _smoothed(mesh: trimesh.Trimesh, diag: float) -> np.ndarray:
    """Each facet's normal averaged (by area) with the facets within ``_SMOOTHING`` of the part's size whose
    own normals lie within 20 deg of it: the surface's direction, not one facet's noise."""
    normals = mesh.face_normals
    total = normals * mesh.area_faces[:, None]
    try:
        from scipy.spatial import cKDTree

        pairs = cKDTree(mesh.triangles_center).query_pairs(_SMOOTHING * diag, output_type="ndarray")
    except Exception:  # noqa: BLE001 - no scipy: the raw normals
        return normals
    if len(pairs):
        pairs = pairs[np.einsum("ij,ij->i", normals[pairs[:, 0]], normals[pairs[:, 1]]) > np.cos(np.radians(20.0))]
        np.add.at(total, pairs[:, 0], normals[pairs[:, 1]] * mesh.area_faces[pairs[:, 1], None])
        np.add.at(total, pairs[:, 1], normals[pairs[:, 0]] * mesh.area_faces[pairs[:, 0], None])
    size = np.linalg.norm(total, axis=1)
    return total / np.where(size > 0, size, 1.0)[:, None]


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
    features: list = []
    probe_edge = 0.0
    probe_notes: list[str] = []
    for index, body in enumerate(bodies):
        probe, probe_edge, probe_note = _probe_mesh(body)
        if probe_note and probe_note not in probe_notes:
            probe_notes.append(probe_note)
        normals = probe.face_normals
        areas = probe.area_faces
        centers = probe.triangles_center
        # Which way a facet opens is read from its normal averaged over the facets about it that face the
        # same way (``_smoothed``): vertex noise tilts single facets of a 3 degree wall past zero.
        along = _smoothed(probe, float(np.linalg.norm(body.extents))) @ pull
        lean_deg = np.degrees(np.arcsin(np.clip(np.abs(along), 0.0, 1.0)))
        # A facet leaning under half a degree is taken as zero draft (both ways tried): a mesh's vertex noise
        # tilts a straight bore's facets about that much, and a bore is not trapped by its own floor.
        zero = lean_deg < max(zero_tol, _NOISE_DEG)
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
        features += _undercut_features(body, probe, candidates, pull, zero_tol, eps, max(probe_edge, eps))
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
    features.sort(key=lambda item: -item["trapped_area_mm2"])
    releases = [item["release"] for item in features]
    result.update({
        "undercut_count": len(features),
        "external_count": sum(1 for item in features if item["kind"] == "external"),
        "internal_count": sum(1 for item in features if item["kind"] == "internal"),
        "side_action_count": sum(item["side_action_count"] for item in features),
        "lifter_count": releases.count("lifter"),
        "collapsible_core_count": releases.count("collapsible_core"),
        "unreleasable_count": releases.count("none"),
        "items": features[:300],
    })
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
            # did not measure, and `pulls` is what an agent runs FIRST to
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
    every candidate had failed still passed and read as complete.
    """
    if isinstance(value, dict):
        return "error" in value or any(_has_error(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_error(v) for v in value)
    return False


def _mark_partial(report: dict) -> bool:
    """Flag a report whose families did not all measure.

    A family that failed leaves an `error` field where its facts should be.
    Without this, the report reads as complete and the check passes, so a
    dead family becomes a silent "no findings".
    """
    failed = sorted(key for key, value in report.items() if _has_error(value))
    report["partial"] = bool(failed)
    if failed:
        report["partial_sections"] = failed
    return bool(failed)


def measure(mesh: trimesh.Trimesh, pull: np.ndarray, wall_limit: float, zero_tol: float) -> dict:
    """Every family for one pull: the mesh, its scale, draft, undercuts, projection, and the families it
    shares with exact geometry -- thickness, ribs, bosses, corners, parting and envelope."""
    report = {
        "mesh": _safe(_mesh_facts, mesh),
        "scale": _safe(_scale_hint, mesh),
        "draft": _safe(_draft_facts, mesh, pull, wall_limit, zero_tol),
        "undercuts": _safe(_undercut_facts, mesh, pull, zero_tol),
        "projection": _safe(_projection_facts, mesh, pull),
    }
    _shared_families(mesh, pull, wall_limit, zero_tol, report)
    report["notes"] = list(_MESH_NOTES)
    _mark_partial(report)
    return report


#: What a mesh cannot say that exact geometry does.
_MESH_NOTES = (
    "a mesh has no faces: every item is placed at x, y, z, a 'face' is a region of triangles joined across "
    "edges turning under 20 deg",
    "a curved face's draft is read off its chords (low by up to its spread_deg); exact geometry reads a cylinder's "
    "or cone's exactly",
    "fillet radii are not read: a filleted corner or rib root joins its faces into one region, so corners lists "
    "sharp internal corners only and ribs only those meeting their base at a sharp edge",
    "bosses are found only with their axis along the pull",
)


def pulls(mesh: trimesh.Trimesh, wall_limit: float, zero_tol: float) -> dict:
    """The mesh, its scale and the candidate pulls ranked: x, y, z and its principal axes."""
    report = {
        "mesh": _safe(_mesh_facts, mesh),
        "scale": _safe(_scale_hint, mesh),
        "pulls": _safe(_pull_facts, mesh, wall_limit, zero_tol),
    }
    _mark_partial(report)
    return report


# --- the families a mesh shares with exact geometry (``meshops_molding``) ---------------------------------
#
# A mesh has no faces a ref names, so every item here is placed at x, y, z; and it has no surfaces, so a
# "face" is a REGION: triangles joined across edges that turn less than _SMOOTH_DEG (a box's side, a boss's
# whole cylinder; a fillet joins the faces it blends into one region).

_SMOOTH_DEG = 20.0
#: A region whose corners lie this close to one plane (as a share of the part's size) is flat.
_FLAT_FIT = 3e-4
#: Facet normals are averaged over a patch this size (a share of the part's size) before draft is read.
_SMOOTHING = 5e-3
_SLIVER = 2e-4
#: A facet leaning less than this either way is taken as square to the pull where a lean's sign matters
#: (a split face, a silhouette): a mesh's own noise tilts facets by about this much.
_NOISE_DEG = 0.5
#: A concave edge turning this much is a sharp internal corner: a square one turns 90, and a fillet
#: exported coarsely enough to turn 45 a facet (two facets round a quarter) is not one.
_CORNER_TURN_DEG = 60.0
_THICKNESS_SAMPLES = 2400
_THICK_RATIO = 1.5


def _cast(mesh: trimesh.Trimesh):
    """``cast(origins, directions)``: the distance to the first triangle each ray meets, inf for none."""
    def cast(origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        found = np.full(len(origins), np.inf)
        if not len(origins):
            return found
        locations, index_ray, _index_tri = mesh.ray.intersects_location(
            ray_origins=origins, ray_directions=directions, multiple_hits=False)
        if len(index_ray):
            found[index_ray] = np.linalg.norm(locations - origins[index_ray], axis=1)
        return found
    return cast


def _xyz(point) -> list:
    return [round(float(v), 3) + 0.0 for v in point]


def _clusters(points: np.ndarray, reach: float) -> list[np.ndarray]:
    """Points grouped where they lie within ``reach`` of one another."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree

    if not len(points):
        return []
    pairs = cKDTree(points).query_pairs(reach, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(points), len(points)))
    count, labels = connected_components(graph, directed=False)
    return [np.nonzero(labels == label)[0] for label in range(count)]


def _undercut_features(body: trimesh.Trimesh, probe: trimesh.Trimesh, candidates: np.ndarray, pull: np.ndarray,
                       zero_tol: float, eps: float, edge: float) -> list:
    """The candidate triangles grouped into features (within 1.5 probe edges of one another), each with
    what releases it (``meshops_molding.classify_undercut`` against the body's own rays)."""
    index = np.nonzero(candidates)[0]
    if not len(index):
        return []
    centers, normals, areas = probe.triangles_center[index], probe.face_normals[index], probe.area_faces[index]
    cast = _cast(body)
    diag = float(np.linalg.norm(body.extents)) or 1.0
    found = []
    # A cluster this small (2e-4 of the body's surface) is a ray grazing a corner between two facets, not a
    # feature: the corpus's artifacts are 0.01-0.03 mm2 on a 12000 mm2 tray.
    least = 2e-4 * float(body.area)
    for group in _clusters(centers, 1.5 * edge):
        area = float(areas[group].sum())
        if area <= least:
            continue
        # Each triangle's centre and three points toward its corners: a long facet down a bore is read
        # along its length (the slide's stroke is the farthest point's).
        corners = probe.triangles[index[group]]
        spread = [centers[group]] + [(4.0 * corners[:, k] + corners[:, (k + 1) % 3] + corners[:, (k + 2) % 3]) / 6.0
                                     for k in range(3)]
        points = np.vstack(spread) + np.tile(normals[group], (4, 1)) * eps
        release = ops.classify_undercut(points, np.tile(normals[group], (4, 1)), pull, cast, scale=diag,
                                        zero_tol_deg=zero_tol)
        side = np.asarray(release["vectors"][0]) if release["vectors"] else ops.basis(pull)[0]
        across = np.cross(pull, side)
        across /= np.linalg.norm(across) or 1.0
        heights, widths = centers[group] @ pull, centers[group] @ across
        if release["release"] == "side_action" and (release["stroke_mm"] or 0.0) <= 2.0 * eps:
            continue  # freed by no travel at all: blocked only by the surface it was cast from
        found.append({
            "trapped_area_mm2": round(area, 2), "xyz": _xyz((centers[group] * areas[group, None]).sum(0) / area),
            "kind": release["kind"], "release": release["release"], "side_actions": release["directions"],
            "side_action_count": len(release["directions"]) if release["release"] == "side_action" else 0,
            "angled": any(release["angled"]),
            "stroke_mm": round(release["stroke_mm"], 3) if release["stroke_mm"] is not None else None,
            "height_mm": round(float(np.ptp(heights)), 3), "width_mm": round(float(np.ptp(widths)), 3),
            "triangle_count": int(len(group))})
    return found


class _Regions:
    """A mesh's regions (see above), their adjacency and its kind (concave, convex) across sharp edges."""

    def __init__(self, mesh: trimesh.Trimesh) -> None:
        self.mesh = mesh
        adjacency = mesh.face_adjacency
        angles = np.degrees(mesh.face_adjacency_angles) if len(adjacency) else np.zeros(0)
        smooth = adjacency[angles < _SMOOTH_DEG] if len(adjacency) else np.zeros((0, 2), dtype=int)
        self.label = trimesh.graph.connected_component_labels(smooth, node_count=len(mesh.faces))
        self.count = int(self.label.max()) + 1 if len(self.label) else 0
        self.areas = np.bincount(self.label, weights=mesh.area_faces, minlength=self.count)
        sharp = angles >= _SMOOTH_DEG
        convex = mesh.face_adjacency_convex if len(adjacency) else np.zeros(0, dtype=bool)
        self.links: dict[int, dict[int, dict]] = {}
        if len(adjacency):
            edges = mesh.face_adjacency_edges
            for (fa, fb), concave, angle, edge in zip(adjacency[sharp], ~convex[sharp], angles[sharp], edges[sharp]):
                a, b = int(self.label[fa]), int(self.label[fb])
                if a == b:
                    continue
                for x, y, far in ((a, b, fb), (b, a, fa)):
                    link = self.links.setdefault(x, {}).setdefault(y, {"concave": 0.0, "convex": 0.0, "turn": 0.0,
                                                                        "angle": 0.0, "points": [], "far": []})
                    link["far"].append(int(far))  # the triangles on y's side of the edge
                    length = float(np.linalg.norm(mesh.vertices[edge[0]] - mesh.vertices[edge[1]]))
                    link["concave" if concave else "convex"] += length
                    # the turn across the link, weighted by length: one sliver's crease does not make a corner
                    link["turn"] += float(angle) * length
                    link["angle"] = link["turn"] / max(link["concave"] + link["convex"], 1e-12)
                    link["points"].append(mesh.vertices[edge].mean(axis=0))
        normals = mesh.face_normals
        order = np.argsort(self.label, kind="stable")
        bounds = np.searchsorted(self.label[order], np.arange(self.count + 1))
        self._members = [order[bounds[i]:bounds[i + 1]] for i in range(self.count)]
        self.normal = np.zeros((self.count, 3))
        np.add.at(self.normal, self.label, normals * mesh.area_faces[:, None])
        size = np.linalg.norm(self.normal, axis=1)
        self.normal = self.normal / np.where(size > 0, size, 1.0)[:, None]
        spread = np.ones(self.count)
        np.minimum.at(spread, self.label, np.einsum("ij,ij->i", normals, self.normal[self.label]))
        self.centroid = np.zeros((self.count, 3))
        np.add.at(self.centroid, self.label, mesh.triangles_center * mesh.area_faces[:, None])
        self.centroid /= np.where(self.areas > 0, self.areas, 1.0)[:, None]
        # Flat: its facets agree to a degree, or its corners lie on one plane to _FLAT_FIT of the part's size
        # (a flat face whose vertices carry noise has facets that disagree but corners that do not). A flat
        # region's normal is its plane's.
        diag = max(float(np.linalg.norm(mesh.extents)), 1e-9)
        #: A region smaller than this (a share of the surface) is a sliver the exporter, or vertex noise, left
        #: between faces -- one skinny triangle whose normal is anyone's -- not a face of the part.
        self.sliver = _SLIVER * float(mesh.area)
        self.planar = spread > np.cos(np.radians(1.0))
        self.width = np.zeros(self.count)
        for region in range(self.count):
            verts = self.vertices(region)
            if len(verts) >= 3:
                centre = verts.mean(axis=0)
                _u, sigma, vt = np.linalg.svd(verts - centre, full_matrices=False)
                fit = vt[-1]
                residual = float(np.abs((verts - centre) @ fit).max())
                # Only a plane its corners pin down in both directions: a strip of facets one wide (a fillet's
                # band) has no second span to fit across, and its facets' mean normal is the better reading.
                spans = sigma[1] >= 0.2 * sigma[0] if len(sigma) > 1 else False
                if spans and residual <= _FLAT_FIT * diag and \
                        abs(float(fit @ self.normal[region])) > np.cos(np.radians(10.0)):
                    self.planar[region] = True
                    self.normal[region] = fit if float(fit @ self.normal[region]) > 0 else -fit
                span = 2.0 * float(np.linalg.norm(verts - centre, axis=1).max())
                self.width[region] = float(self.areas[region]) / span if span > 0 else 0.0
        # Each facet's normal averaged (by area) over its region's facets within _SMOOTHING of the part's size:
        # noise on a curved face's vertices tilts single facets, not the surface, and a mean over a patch
        # that small leaves a cone's or a fillet's own turn as it was.
        smooth_normals = normals * mesh.area_faces[:, None]
        centers = mesh.triangles_center
        try:
            from scipy.spatial import cKDTree

            pairs = cKDTree(centers).query_pairs(_SMOOTHING * diag, output_type="ndarray")
        except Exception:  # noqa: BLE001 - no scipy: each facet with its smooth neighbours alone
            pairs = smooth
        if len(pairs):
            pairs = pairs[self.label[pairs[:, 0]] == self.label[pairs[:, 1]]]
            np.add.at(smooth_normals, pairs[:, 0], normals[pairs[:, 1]] * mesh.area_faces[pairs[:, 1], None])
            np.add.at(smooth_normals, pairs[:, 1], normals[pairs[:, 0]] * mesh.area_faces[pairs[:, 0], None])
        length = np.linalg.norm(smooth_normals, axis=1)
        self.facet_normal = smooth_normals / np.where(length > 0, length, 1.0)[:, None]
        flat = self.planar[self.label]
        self.facet_normal[flat] = self.normal[self.label[flat]]

    def coplanar(self, a: int, b: int) -> bool:
        if a == b:
            return True
        if not (self.planar[a] and self.planar[b]) or float(self.normal[a] @ self.normal[b]) < np.cos(np.radians(0.5)):
            return False
        scale = max(float(np.linalg.norm(self.mesh.extents)), 1.0)
        return abs(float((self.centroid[b] - self.centroid[a]) @ self.normal[a])) < 1e-4 * scale

    def faces(self, region: int) -> np.ndarray:
        return self._members[region]

    def root_plane(self, region: int, base: int) -> tuple[np.ndarray, np.ndarray] | None:
        """The plane ``region`` stands on where it meets ``base``: the base's own if it is flat, else that of
        the base's triangles along the edge between them, if they lie flat (a floor filleted to its walls
        elsewhere is one curved region, flat where a rib stands on it). (normal, a point on it), or None."""
        if self.planar[base]:
            return self.normal[base], self.centroid[base]
        far = np.unique(self.links.get(region, {}).get(base, {}).get("far", []))
        if not len(far):
            return None
        normals, areas = self.mesh.face_normals[far], self.mesh.area_faces[far]
        mean = (normals * areas[:, None]).sum(axis=0)
        mean /= np.linalg.norm(mean) or 1.0
        if float((normals @ mean).min()) < np.cos(np.radians(1.0)):
            return None
        return mean, (self.mesh.triangles_center[far] * areas[:, None]).sum(axis=0) / max(float(areas.sum()), 1e-12)

    def concave_neighbours(self, region: int) -> list[int]:
        return [other for other, link in self.links.get(region, {}).items() if link["concave"] > link["convex"]]

    def convex_neighbours(self, region: int) -> set[int]:
        return {other for other, link in self.links.get(region, {}).items() if link["convex"] >= link["concave"]}

    def vertices(self, region: int) -> np.ndarray:
        return self.mesh.vertices[np.unique(self.mesh.faces[self.faces(region)])]


def _transition(change: dict) -> dict:
    """One region's steepest change of wall (``ops.transitions``) as an item: where it is and what it steps."""
    (a, b), (ta, tb) = change["points"], change["thickness"]
    if ta > tb:
        (a, b), (ta, tb) = (b, a), (tb, ta)
    return {"transition_ratio": round(float(change["ratio"]), 3), "min_mm": round(float(ta), 3),
            "max_mm": round(float(tb), 3), "change_mm": round(float(tb - ta), 3),
            "length_mm": round(float(np.linalg.norm(np.asarray(b) - np.asarray(a))), 3),
            "xyz": _xyz((np.asarray(a) + np.asarray(b)) / 2.0), "at_xyz": [_xyz(a), _xyz(b)]}


def _thickness_mesh(mesh: trimesh.Trimesh, regions: _Regions) -> dict:
    count = _THICKNESS_SAMPLES
    # Deterministic and even (``meshops_molding.even_points``): no rejection sampling, whose yield moves
    # with the platform's tessellation.
    points, faces, weights = ops.even_points(mesh.vertices, mesh.faces, count)
    normals = mesh.face_normals[faces]
    spacing = np.full(len(points), float(np.sqrt(float(mesh.area) / max(len(points), 1))))
    diag = float(np.linalg.norm(mesh.extents)) or 1.0
    eps = min(max(1e-4 * diag, 1e-5), 0.01)
    ray = _cast(mesh)(points - normals * eps, -normals) + eps
    owner = regions.label[faces]
    # A point is never held by its own region: across a curved region's chords the ball would be held by
    # the next facet's crease (exact geometry has none there); the ray straight through bounds it instead.
    values, bound = ops.ball_thickness(points, normals, ray, mesh.vertices, mesh.faces, others=points,
                                       point_face=owner, triangle_face=regions.label, others_face=owner)
    # Held round an edge: bounded by a face across a convex edge of its own, or by any face not looking
    # back at it (a far wall faces the point, within 60 deg; a face round an outside edge stands square to
    # it) -- the second holds where noise has cut the faces between into slivers.
    facing = np.einsum("ij,ij->i", mesh.face_normals[np.maximum(bound, 0)], normals)
    held = np.array([b >= 0 and (int(regions.label[b]) in regions.convex_neighbours(int(o)) or f > -0.5)
                     for b, o, f in zip(bound, owner, facing)], dtype=bool)
    finite = np.isfinite(values)
    clean = finite & ~held
    if clean.any() and weights[clean].sum() >= 0.5 * weights[finite].sum():
        nominal = ops.weighted_median(values[clean], weights[clean])
    else:
        nominal = ops.weighted_median(values, weights)
    per: dict[int, dict] = {}
    for region in np.unique(owner[finite]):
        mine = (owner == region) & finite
        v, w, tidy = values[mine], weights[mine], clean[mine]
        # Narrow: a region the ball cannot sit on -- most of its points held by a face round a convex edge,
        # a sliver, or the region narrower (its area over its span) than twice the widest ball it holds (a
        # fillet's strip, a corner's patch, a rib's top, a block's side). Its reading is the edge's.
        narrow = (float(w[tidy].sum()) < 0.3 * float(w.sum()) or regions.areas[region] < regions.sliver
                  or float(regions.width[region]) < 2.0 * float(v.max()))
        median = low = float(v.max()) if narrow or not tidy.any() else ops.weighted_median(v[tidy], w[tidy])
        if not narrow and tidy.any():
            low = ops.weighted_quantile(v[tidy], w[tidy], 0.1)
        top = int(np.argmax(v))
        per[int(region)] = {"median": median, "low": low, "max": float(v[top]), "at": points[mine][top],
                            "narrow": narrow}
    nearest = ops.nearest_broad_all(list(range(regions.count)), lambda r: list(regions.links.get(r, {})),
                                    lambda r: r in per and not per[r]["narrow"])
    for region, face in per.items():
        if face["narrow"]:
            # It takes the wall of the broad regions nearest it; where none is near, its own widest reading.
            near = nearest.get(region, [])
            if near:
                face["median"] = face["low"] = float(np.median([per[o]["median"] for o in near]))
                face["max"] = max(face["max"], face["median"])
    if per:
        # The nominal wall: the area median of the regions' own walls (a narrow region's from its neighbours).
        nominal = ops.weighted_median(np.array([face["median"] for face in per.values()]),
                                      np.array([float(regions.areas[region]) for region in per]))
    items, sections, steps = [], [], []
    found = ops.transitions(points, values, owner, ~held, spacing, nominal) if nominal else {}
    for region, face in per.items():
        if not nominal:
            break
        item = {"thickness_mm": round(face["median"], 3), "min_mm": round(face["low"], 3),
                "max_mm": round(face["max"], 3), "nominal_mm": round(nominal, 3),
                "ratio_to_nominal": round(face["max"] / nominal, 3), "thin_ratio": round(face["median"] / nominal, 3),
                "area_mm2": round(float(regions.areas[region]), 2), "xyz": _xyz(face["at"])}
        if region in found:
            steps.append(_transition(found[region]))
        items.append(item)
        if face["max"] > _THICK_RATIO * nominal:
            sections.append({"thickness_mm": item["max_mm"], "ratio_to_nominal": item["ratio_to_nominal"],
                             "xyz": item["xyz"]})
    sections.sort(key=lambda section: -section["ratio_to_nominal"])
    thin = sorted(items, key=lambda item: item["thickness_mm"])[:100]
    thick = sorted(items, key=lambda item: -item["ratio_to_nominal"])[:100]
    steps.sort(key=lambda step: step["transition_ratio"])
    chosen, seen = [], set()
    for item in thin + thick:
        if id(item) not in seen:
            seen.add(id(item))
            chosen.append(item)
    return {
        "_per": {region: face["median"] for region, face in per.items()},
        "_transitions": {"count": len(steps), "items": steps[:300], "method": (
            "per region, the steepest change of the rolling-ball wall between two of its points within four sample "
            "spacings whose walls differ by half the nominal or more: transition_ratio is their distance over the "
            "change; the item stands between them (xyz), min_mm and max_mm the two walls, at_xyz each one's point")},
        "nominal_mm": round(nominal, 3) if nominal else None,
        "min_mm": round(min(i["thickness_mm"] for i in items), 3) if items else None,
        "min_point_mm": round(min(i["min_mm"] for i in items), 3) if items else None,
        "max_mm": round(max(i["max_mm"] for i in items), 3) if items else None,
        "median_mm": round(ops.weighted_median(values, weights), 3) if finite.any() else None,
        "ratio_max_nominal": round(max(i["max_mm"] for i in items) / nominal, 3) if items and nominal else None,
        "thick_ratio_reported": _THICK_RATIO, "thick_sections": sections[:20], "thick_section_count": len(sections),
        "sample_count": int(finite.sum()), "region_count": len(items), "items": chosen,
        "method": ("rolling ball on the mesh: at points spread evenly over the triangles, the diameter of the "
                   "largest ball touching the surface there that no triangle cuts into, never more than the ray "
                   "straight through; per region (triangles joined across edges under 20 deg) the area median, "
                   "10th percentile and most. Exact for flat walls; a curved wall is read off its chords"),
    }


def _ribs_mesh(mesh: trimesh.Trimesh, regions: _Regions, pull: np.ndarray, wall_of, nominal: float | None,
               used: set) -> list:
    """Ribs on a mesh: two opposite flat regions whose rays into the material come out of one another, both
    meeting one flat base region at a sharp concave edge (a filleted root joins them all into one region:
    not found here)."""
    cast = _cast(mesh)
    diag = float(np.linalg.norm(mesh.extents)) or 1.0
    eps = min(max(1e-4 * diag, 1e-5), 0.01)
    items, seen = [], set()
    for a in range(regions.count):
        if not regions.planar[a]:
            continue
        na = regions.normal[a]
        planes_a = {base: plane for base in regions.concave_neighbours(a)
                    if (plane := regions.root_plane(a, base)) is not None
                    and abs(float(plane[0] @ na)) < np.sin(np.radians(20.0))}
        if not planes_a:
            continue
        scale = max(float(np.linalg.norm(mesh.extents)), 1.0)

        def same(p: tuple[np.ndarray, np.ndarray], q: tuple[np.ndarray, np.ndarray]) -> bool:
            # One plane either side of the rib: a thousandth of the part apart at most (a floor's triangles
            # either side, each tilted by the vertices' noise, need not share a plane to a tighter figure).
            return float(p[0] @ q[0]) >= np.cos(np.radians(0.5)) and abs(float((q[1] - p[1]) @ p[0])) < 1e-3 * scale
        tris = regions.faces(a)
        centers = mesh.triangles_center[tris]
        locations, index_ray, index_tri = mesh.ray.intersects_location(
            ray_origins=centers - mesh.face_normals[tris] * eps, ray_directions=-mesh.face_normals[tris],
            multiple_hits=False)
        if not len(index_ray):
            continue
        hit_region = regions.label[index_tri]
        distance = np.linalg.norm(locations - centers[index_ray], axis=1)
        for b in np.unique(hit_region):
            b = int(b)
            if b == a or (min(a, b), max(a, b)) in seen or not regions.planar[b]:
                continue
            if float(regions.normal[b] @ na) > -np.cos(np.radians(12.0)):
                continue
            if (hit_region == b).sum() < 0.5 * len(tris):
                continue
            planes_b = [plane for other in regions.concave_neighbours(b)
                        if (plane := regions.root_plane(b, other)) is not None]
            common = [base for base, plane in planes_a.items() if any(same(plane, other) for other in planes_b)]
            if not common:
                continue

            def standing(base: int) -> float:
                normal, origin = planes_a[base]
                return float(((regions.vertices(a) - origin) @ normal).max())

            base = min(common, key=standing)
            height = standing(base)
            across = distance[hit_region == b]
            root, tip = float(across.max()), float(across.min())
            along = np.cross(planes_a[base][0], na)
            along /= np.linalg.norm(along) or 1.0
            length = float(np.ptp(regions.vertices(a) @ along))
            if root <= 0 or height < root or length < 1.5 * root:
                continue
            seen.add((min(a, b), max(a, b)))
            used.update({a, b})
            wall = wall_of(base) or nominal
            gaps = []
            for side in (a, b):
                own = regions.faces(side)
                gap = cast(mesh.triangles_center[own] + mesh.face_normals[own] * eps, mesh.face_normals[own])
                finite = gap[np.isfinite(gap)]
                if len(finite) >= 0.5 * len(own):
                    gaps.append(float(np.median(finite)))
            gap = min(gaps) if gaps else None
            lean = abs(float(na @ pull))
            items.append({
                "thickness_mm": round(root, 3), "tip_thickness_mm": round(tip, 3), "height_mm": round(height, 3),
                "length_mm": round(length, 3), "wall_mm": round(wall, 3) if wall else None,
                "thickness_ratio": round(root / wall, 3) if wall else None,
                "height_ratio": round(height / wall, 3) if wall else None,
                "height_to_thickness": round(height / root, 3), "base_fillet_mm": 0.0, "base_fillet_ratio": 0.0,
                "base_fillet_wall_ratio": 0.0, "draft_deg": round(float(np.degrees(np.arcsin(min(1.0, lean)))), 3),
                "gap_mm": round(gap, 3) if gap is not None else None,
                "gap_to_thickness": round(gap / root, 3) if gap is not None else None,
                "gap_to_wall": round(gap / wall, 3) if gap is not None and wall else None,
                "xyz": _xyz(regions.centroid[a])})
    return items


def _circle(points: np.ndarray) -> tuple[np.ndarray, float, float]:
    """A least-squares circle through 2D points: centre, radius and the RMS misfit."""
    x, y = points[:, 0], points[:, 1]
    a = np.column_stack([x, y, np.ones(len(x))])
    rhs = x * x + y * y
    solution, *_ = np.linalg.lstsq(a, rhs, rcond=None)
    centre = solution[:2] / 2.0
    radius = float(np.sqrt(max(solution[2] + centre @ centre, 0.0)))
    misfit = float(np.sqrt(np.mean((np.linalg.norm(points - centre, axis=1) - radius) ** 2)))
    return centre, radius, misfit


def _bosses_mesh(mesh: trimesh.Trimesh, regions: _Regions, pull: np.ndarray, wall_of, nominal: float | None,
                 used: set) -> list:
    """Bosses on a mesh whose axis runs along the pull: a convex curved region whose normals all lie square to
    the pull, a circle round it, standing on a flat region square to the pull at a sharp concave edge; its
    hole, a concave such region on the same axis inside it."""
    u, v = ops.basis(pull)
    cylinders = []
    for region in range(regions.count):
        if regions.planar[region]:
            continue
        tris = regions.faces(region)
        if len(tris) < 6 or np.abs(mesh.face_normals[tris] @ pull).max() > np.sin(np.radians(3.0)):
            continue
        verts = regions.vertices(region)
        flat = np.column_stack([verts @ u, verts @ v])
        centre, radius, misfit = _circle(flat)
        if radius <= 0 or misfit > 0.02 * radius:
            continue
        centers = np.column_stack([mesh.triangles_center[tris] @ u, mesh.triangles_center[tris] @ v])
        normals = np.column_stack([mesh.face_normals[tris] @ u, mesh.face_normals[tris] @ v])
        convex = float(np.mean(np.einsum("ij,ij->i", centers - centre, normals))) > 0
        heights = verts @ pull
        cylinders.append({"region": region, "centre": centre, "radius": radius, "convex": convex,
                          "low": float(heights.min()), "high": float(heights.max())})
    items = []
    for boss in (c for c in cylinders if c["convex"]):
        bases = [b for b in regions.concave_neighbours(boss["region"])
                 if regions.planar[b] and abs(float(regions.normal[b] @ pull)) > np.cos(np.radians(5.0))]
        if not bases:
            continue
        base = bases[0]
        level = float(regions.centroid[base] @ pull)
        up = float(regions.normal[base] @ pull) > 0
        height = (boss["high"] - level) if up else (level - boss["low"])
        if height <= 0:
            continue
        holes = [c for c in cylinders if not c["convex"] and c["radius"] < boss["radius"]
                 and np.linalg.norm(c["centre"] - boss["centre"]) < 0.02 * boss["radius"]]
        hole = max(holes, key=lambda c: c["radius"]) if holes else None
        used.update({boss["region"], *(([hole["region"]]) if hole else [])})
        wall_ref = wall_of(base) or nominal
        wall = boss["radius"] - hole["radius"] if hole else 2 * boss["radius"]
        floor = None
        if hole:
            floor = (hole["low"] - level) if up else (level - hole["high"])
        centre3 = boss["centre"][0] * u + boss["centre"][1] * v + pull * (level + (height / 2 if up else -height / 2))
        items.append({"od_mm": round(2 * boss["radius"], 3), "id_mm": round(2 * hole["radius"], 3) if hole else None,
                      "hollow": hole is not None, "boss_wall_mm": round(wall, 3),
                      "wall_mm": round(wall_ref, 3) if wall_ref else None,
                      "wall_ratio": round(wall / wall_ref, 3) if wall_ref else None,
                      "od_to_id": round(boss["radius"] / hole["radius"], 3) if hole else None,
                      "height_mm": round(height, 3), "height_to_od": round(height / (2 * boss["radius"]), 3),
                      "base_fillet_mm": 0.0, "hole_floor_above_base_mm": round(max(floor, 0.0), 3) if hole else None,
                      "xyz": _xyz(centre3)})
    return items


def _corners_mesh(mesh: trimesh.Trimesh, regions: _Regions, wall_of, nominal: float | None, used: set) -> list:
    """Sharp internal corners on a mesh: regions meeting at a concave edge turning ``_CORNER_TURN_DEG`` or more
    (a filleted corner joins its faces into one region, or its facets each turn less, and is not listed: a
    mesh's fillet radius is not read)."""
    items = []
    least = regions.sliver
    for a, links in regions.links.items():
        for b, link in links.items():
            if a >= b or link["concave"] <= link["convex"] or link["angle"] < _CORNER_TURN_DEG or a in used or b in used:
                continue
            if min(regions.areas[a], regions.areas[b]) < least:
                continue
            walls = [w for w in (wall_of(a), wall_of(b)) if w]
            wall = min(walls) if walls else nominal
            points = np.array(link["points"])
            items.append({"radius_mm": 0.0, "sharp": True, "angle_deg": round(180.0 + link["angle"], 2),
                          "length_mm": round(link["concave"], 3), "wall_mm": round(wall, 3) if wall else None,
                          "ratio_to_wall": 0.0, "xyz": _xyz(points[len(points) // 2])})
    return items


def _parting_mesh(mesh: trimesh.Trimesh, regions: _Regions, pull: np.ndarray, zero_tol: float, wall_limit: float,
                  trapped: np.ndarray | None) -> dict:
    """The parting (``meshops_molding.parting``) on a mesh: silhouette edges between triangles opening either
    way, zero-draft regions and curved regions turning through the pull, those near the projected outline."""
    u, v = ops.basis(pull)
    flat = np.column_stack([mesh.vertices @ u, mesh.vertices @ v])
    projection = ops.raster(flat, mesh.faces)
    heights = mesh.vertices @ pull
    top, bottom = float(heights.max()), float(heights.min())
    tolerance = max(1e-3 * (top - bottom), 0.01)
    tol = np.sin(np.radians(max(zero_tol, _NOISE_DEG)))
    along = regions.facet_normal @ pull
    sign = np.where(along > tol, 1, np.where(along < -tol, -1, 0))
    skip = trapped if trapped is not None else np.zeros(len(mesh.faces), dtype=bool)
    elements = []
    adjacency = mesh.face_adjacency
    if len(adjacency):
        opposite = (sign[adjacency[:, 0]] * sign[adjacency[:, 1]] < 0) & ~skip[adjacency[:, 0]] & ~skip[adjacency[:, 1]]
        edges = mesh.face_adjacency_edges[opposite]
        if len(edges):
            mids = mesh.vertices[edges].mean(axis=1)
            near = ops.near_outline(projection, np.column_stack([mids @ u, mids @ v]), 3.0)
            for (va, vb), keep in zip(edges, near):
                if keep:
                    ha, hb = float(heights[va]), float(heights[vb])
                    elements.append({"kind": "edge", "low": min(ha, hb), "high": max(ha, hb),
                                     "weight": float(np.linalg.norm(mesh.vertices[va] - mesh.vertices[vb])),
                                     "xyz": _xyz((mesh.vertices[va] + mesh.vertices[vb]) / 2)})
    for region in range(regions.count):
        tris = regions.faces(region)
        if skip[tris].any():
            continue
        signs = sign[tris]
        drafts = np.degrees(np.arcsin(np.clip(np.abs(along[tris]), 0, 1)))
        if drafts.min() >= wall_limit:
            continue
        verts = regions.vertices(region)
        if not ops.near_outline(projection, np.column_stack([verts @ u, verts @ v]), 3.0).any():
            continue
        if (signs == 0).all():
            hv = verts @ pull
            elements.append({"kind": "wall", "low": float(hv.min()), "high": float(hv.max()),
                             "weight": float(regions.areas[region]), "xyz": _xyz(regions.centroid[region])})
        elif (signs > 0).any() and (signs < 0).any() and not regions.planar[region]:
            turning = tris[np.argsort(np.abs(along[tris]))[: max(2, len(tris) // 10)]]
            ht = mesh.triangles_center[turning] @ pull
            elements.append({"kind": "turn", "low": float(ht.min()), "high": float(ht.max()),
                             "weight": float(regions.areas[region]), "xyz": _xyz(regions.centroid[region])})
    found = ops.parting(elements, top, bottom, max(tolerance, 2 * projection["cell"]))
    off = {id(element) for element in found["off_plane"]}
    items = [{"kind": e["kind"], "low_mm": round(e["low"], 4), "high_mm": round(e["high"], 4),
              "on_plane": id(e) not in off, "xyz": e["xyz"]} for e in elements]
    items.sort(key=lambda item: item["on_plane"])
    depth = max(found["depth_above"], found["depth_below"])
    return {"pull_axis": [round(float(x), 4) for x in pull], "flat_parting_possible": found["flat"],
            "parting_plane_height_mm": round(found["height"], 4),
            "parting_plane_range_mm": [round(x, 4) for x in found["range"]] if found["range"] else None,
            "depth_above_mm": round(found["depth_above"], 3), "depth_below_mm": round(found["depth_below"], 3),
            "depth_from_parting_mm": round(depth, 3), "silhouette_count": len(items),
            "off_plane_count": len(found["off_plane"]), "tolerance_mm": round(tolerance, 4), "items": items[:300],
            "method": ("silhouette edges between triangles opening either way along the pull, zero-draft regions and "
                       "curved regions turning through it, near the projected outline (a mesh's: a curved face's "
                       "turn is read off its chords)"),
            "_span": [float(np.ptp(flat[:, 0])), float(np.ptp(flat[:, 1]))]}


def _shared_families(mesh: trimesh.Trimesh, pull: np.ndarray, wall_limit: float, zero_tol: float,
                     report: dict) -> None:
    """thickness, ribs, bosses, corners, parting and envelope on a mesh, into ``report``."""
    regions = _safe(_Regions, mesh)
    if isinstance(regions, dict):
        for name in ("thickness", "transitions", "ribs", "bosses", "corners", "parting", "envelope"):
            report[name] = dict(regions)
        return
    draft = report.get("draft")
    if isinstance(draft, dict) and "error" not in draft:
        items = _safe(_draft_items, mesh, regions, pull, wall_limit, zero_tol)
        if isinstance(items, dict):
            report["draft"] = items
        else:
            draft["items"] = items
            draft["wall_face_count"] = len(items)
    thickness = _safe(_thickness_mesh, mesh, regions)
    walls: dict[int, float] = thickness.pop("_per", {}) if isinstance(thickness, dict) else {}
    steps = thickness.pop("_transitions", None)
    report["thickness"] = thickness
    report["transitions"] = steps if steps is not None else dict(thickness)
    nominal = thickness.get("nominal_mm")

    def wall_of(region: int):
        return walls.get(region)

    used: set = set()
    report["ribs"] = _safe(lambda: _family(_ribs_mesh(mesh, regions, pull, wall_of, nominal, used),
                                           "thickness_ratio"))
    report["bosses"] = _safe(lambda: _family(_bosses_mesh(mesh, regions, pull, wall_of, nominal, used), "wall_ratio"))
    report["corners"] = _safe(lambda: _family(_corners_mesh(mesh, regions, wall_of, nominal, used), "ratio_to_wall",
                                              low=True))
    parting = _safe(_parting_mesh, mesh, regions, pull, zero_tol, wall_limit, _trapped_regions(mesh, regions, pull,
                                                                                               zero_tol))
    span = parting.pop("_span", None) if isinstance(parting, dict) else None
    report["parting"] = parting
    projection = report.get("projection") or {}
    if span is not None and "error" not in projection:
        report["envelope"] = {"items": [{"span_major_mm": round(max(span), 3), "span_minor_mm": round(min(span), 3),
                                         "depth_along_pull_mm": projection.get("depth_along_pull_mm"),
                                         "depth_from_parting_mm": parting.get("depth_from_parting_mm"),
                                         "volume_mm3": projection.get("volume_mm3")}],
                              "method": "spans of the mesh's projection on the parting plane, its depth along the "
                                        "pull and the farther of its depths either side of the parting plane"}
    else:
        report["envelope"] = {"error": "the projection or the parting was not measured"}


def _draft_items(mesh: trimesh.Trimesh, regions: _Regions, pull: np.ndarray, wall_limit: float,
                 zero_tol: float) -> list:
    """The draft per region, the rules' items: a flat region's exactly (its normal), a curved one's at the 5th
    percentile of its wall facets' area (its chords scatter: ``spread_deg``), tangent bands left out; ``opens``
    as the region leans, ``split`` where it leans both ways (the parting line crosses it). Facets are read by
    their smoothed normals (``_Regions.facet_normal``) and a lean counts past half a degree, so vertex noise
    does not tilt a wall."""
    along = regions.facet_normal @ pull
    draft = np.round(np.degrees(np.arcsin(np.clip(np.abs(along), 0.0, 1.0))), 3)
    tangent = _tangent_faces(mesh, pull, mesh.face_normals @ pull, zero_tol)
    tol = float(np.sin(np.radians(max(zero_tol, _NOISE_DEG))))
    areas = mesh.area_faces
    reach = mesh.triangles @ pull
    items = []
    for region in range(regions.count):
        if regions.areas[region] < regions.sliver:
            continue  # a sliver the exporter (or noise) left between faces: no face of the part
        tris = regions.faces(region)
        wall = tris[(draft[tris] < wall_limit) & ~tangent[tris]]
        if not len(wall):
            continue
        weight = areas[wall]
        total = float(weight.sum())
        if total <= 0:
            continue
        order = wall[np.argsort(draft[wall])]
        share = np.cumsum(areas[order]) / total
        low = float(draft[order][min(int(np.searchsorted(share, 0.05)), len(order) - 1)])
        high = float(draft[order][min(int(np.searchsorted(share, 0.95)), len(order) - 1)])
        lean = along[wall]
        up, down = float(weight[lean > tol].sum()) / total, float(weight[lean < -tol].sum()) / total
        curved = not bool(regions.planar[region])
        opens = ("split" if curved and up > 0.05 and down > 0.05 else
                 "none" if low < zero_tol and not curved else
                 "+pull" if up >= down and up > 0 else "-pull" if down > 0 else "none")
        if not curved:
            low = high = float(np.degrees(np.arcsin(min(1.0, abs(float(regions.normal[region] @ pull))))))
            low = round(low, 3)
            opens = "none" if low < zero_tol else ("+pull" if float(regions.normal[region] @ pull) > 0 else "-pull")
        centre = (mesh.triangles_center[wall] * weight[:, None]).sum(axis=0) / total
        items.append({"draft_deg": round(low, 3), "area_mm2": round(total, 2), "opens": opens,
                      "surface": "curved" if curved else "flat",
                      "depth_mm": round(float(reach[wall].max() - reach[wall].min()), 3), "xyz": _xyz(centre),
                      **({"spread_deg": round(high - low, 3)} if curved else {})})
    items.sort(key=lambda item: (item["draft_deg"], -item["area_mm2"]))
    return items[:300]


def _trapped_regions(mesh: trimesh.Trimesh, regions: _Regions, pull: np.ndarray, zero_tol: float) -> np.ndarray:
    """Per triangle: does it lie in a region mostly blocked along the way it opens (an undercut's: a slide
    forms it, and the parting line runs round it)?"""
    along = regions.facet_normal @ pull
    tol = np.sin(np.radians(max(zero_tol, _NOISE_DEG)))
    eps = 1e-3 * max(float(np.linalg.norm(mesh.extents)), 1.0)
    origins = mesh.triangles_center + mesh.face_normals * eps
    sign = np.where(along >= 0, 1.0, -1.0)
    blocked = mesh.ray.intersects_any(ray_origins=origins, ray_directions=np.outer(sign, pull))
    zero = np.abs(along) <= tol
    if zero.any():
        index = np.nonzero(zero & blocked)[0]
        blocked[index] = mesh.ray.intersects_any(ray_origins=origins[index], ray_directions=np.outer(-sign[index], pull))
    share = np.bincount(regions.label, weights=mesh.area_faces * blocked, minlength=regions.count)
    trapped = share > 0.3 * np.maximum(regions.areas, 1e-12)
    return trapped[regions.label]


def _family(items: list, key: str, low: bool = False) -> dict:
    items.sort(key=lambda item: (item.get(key) if item.get(key) is not None else np.inf) * (1 if low else -1))
    return {"count": len(items), "items": items[:300]}

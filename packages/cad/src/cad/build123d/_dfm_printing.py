"""3D printing's measurements of exact geometry (``cad._internal.dfm.printing`` says what they are for).

The document stands on the plate as a whole: its lowest point is the plate, Z up. Every face is sampled
(``_dfm_brep.samples``: points on the surface, their outward normals, their share of the area) and the
families are measured on the B-rep, each item at the ref of the face that names it:

- ``solid``: each part's validity (the kernel's checks), closure, solids, inner shells, volume;
- ``overhangs``: each down-facing face's angle from horizontal (a plane's exactly, a curved face's over
  its samples), its area under the angle limit, its height, and what kind of overhang it is (a slope, a
  flat ceiling a bridge or cantilever carries, a hole's arch, a round on the plate's edge);
- ``bridges``: each flat ceiling's span between the walls that carry it (a bridge) or reach past the
  one that does (a cantilever), from its supporting edges (concave, the wall below);
- ``wall_thickness``: exact rays into the material from every sample; per face the thinnest, whether the
  wall is joined on two or more sides (supported) or fewer;
- ``gaps``: exact rays out of the material: per face the narrowest slot to another face of the part;
- ``holes`` and ``pins``: concave and convex cylinders round an axis (at least 250 degrees of it), their
  diameter, depth or height, orientation, a horizontal hole's teardrop top, through or blind;
- ``details``: embossed and engraved steps (a side face between two parallel faces), height and width;
- ``clearances``: the exact minimum distance between distinct parts (BRepExtrema), contact and overlap;
- ``trapped_volumes``: cavities -- every solid's inner shells, exactly, and from a voxel field the air
  a ball cannot reach from outside -- each with its volume, escape holes (the holes from it to outside,
  exactly), the wall around it;
- ``build_volume``, ``bed``, ``stair_stepping``, ``support_volume`` (a raster of the triangulation),
  ``sections`` (thickest walls, cross-sections), ``scale``; with ``candidates`` the orientations ranked.

OCP, build123d and numpy alone; each family fails on its own (``{"error": ...}``, ``partial_sections``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from cad._internal import meshops_printing as mo
from cad._internal.dfm import printing as rules
from cad.build123d import _dfm_brep as brep

__all__ = ["measure"]

#: Items a family lists, at most (worst first); the rest are counted.
CAP = 300
#: A flat ceiling is under this many degrees from horizontal.
FLAT_DEG = 5.0
#: A cylinder round an axis by at least this many degrees is a hole or a pin (a fillet is 90, a slot's end 180).
ROUND_DEG = 250.0
#: Gaps are reported up to this width, mm (every published minimum is under 1 mm).
GAP_CEILING = 3.0
#: Embossed and engraved steps are this high at most, mm.
DETAIL_CEILING = 2.0
#: A shallow slope stair-steps: above flat and under this many degrees from horizontal.
SHALLOW_DEG = 20.0


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), digits)


def _xyz(point: Any) -> list[float]:
    return [round(float(value), 4) for value in point]


def _safe(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return fn()
    except Exception as error:  # noqa: BLE001 - one family failing never loses the rest
        detail = f"{type(error).__name__}: {error}".splitlines()[0]
        return {"error": detail[:300]}


def _capped(items: list[dict[str, Any]], key: Callable[[dict[str, Any]], Any]) -> tuple[list[dict[str, Any]], int]:
    items.sort(key=key)
    return items[:CAP], len(items)


# --- the faces ----------------------------------------------------------------------------------------------


@dataclass
class FaceInfo:
    part: int
    ordinal: int
    face: Any
    surface: brep.Surface
    area: float
    zmin: float
    zmax: float
    samples: list[brep.Sample] = field(default_factory=list)
    box: Any = None                        # the face's box (the kernel's quick one, on its triangulation)
    coverage_deg: float = 0.0              # a cylinder's angle round its axis
    group: int | None = None               # its hole or pin
    thickness: list[tuple[float, int, int]] = field(default_factory=list)  # (mm, sample index, hit ordinal)
    gap: list[tuple[float, int, int]] = field(default_factory=list)


@dataclass
class Round:
    """A hole (concave) or pin (convex): cylinder faces round one axis."""

    part: int
    faces: list[int]
    concave: bool
    radius: float
    axis: np.ndarray
    origin: np.ndarray
    coverage_deg: float
    lo: float = 0.0
    hi: float = 0.0


class Context:
    """What every family reads: the parts, their faces sampled, their edges, rays, the plate."""

    def __init__(self, document: brep.Document, options: dict[str, Any]) -> None:
        self.document = document
        self.options = options
        self.technology = options["technology"]
        self.angle_limit = rules.angle_limit(options)
        self.layer = rules.layer_height(options)
        self.parts = document.parts
        self.faces: list[list[FaceInfo]] = []
        self.rounds: list[Round] = []
        self._rays: dict[int, brep.Rays] = {}
        self._edges: dict[int, list[brep.Edge]] = {}
        self._adjacent: dict[int, dict[int, list[brep.Edge]]] = {}
        self._mesh: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self._grids: dict[int, Any] = {}
        total = sum(float(face.area) for part in self.parts for face in part.faces()) or 1.0
        budget = int(options.get("samples") or 2000)
        for index, part in enumerate(self.parts):
            infos = []
            for ordinal, face in enumerate(part.faces(), start=1):
                # the kernel's quick box (an optimal one costs seconds on a spline): a first for the
                # sampling's deflection, then again on the triangulation the sampling made, which is tight
                rough = face.bounding_box(optimal=False)
                area = float(face.area)
                count = int(min(400, max(4, round(budget * area / total))))
                deflection = max(1e-3, 0.02 * max(rough.size.X, rough.size.Y, rough.size.Z))
                samples = brep.samples(face, count, deflection) if area > 0 else []
                box = face.bounding_box(optimal=False)
                info = FaceInfo(index, ordinal, face, brep.surface(face), area, float(box.min.Z), float(box.max.Z))
                info.box = box
                info.samples = samples
                if info.surface.kind == "cylinder":
                    from OCP.BRepTools import BRepTools

                    umin, umax, _, _ = BRepTools.UVBounds_s(face.wrapped)
                    info.coverage_deg = math.degrees(umax - umin)
                infos.append(info)
            self.faces.append(infos)
            self._group_rounds(index)
        # the document's box from points on its surface -- every vertex, every sample, every node of the faces'
        # triangulations -- not from a box the kernel pads with each face's tolerance: the plate is its lowest
        V, _, _ = self.mesh()
        points = [V] + [np.array([s.point for s in info.samples]) for infos in self.faces for info in infos
                        if info.samples]
        every = np.vstack(points)
        self.lo, self.hi = every.min(axis=0), every.max(axis=0)
        self.z0 = float(self.lo[2])
        self.diag = float(np.linalg.norm(self.hi - self.lo))
        self.tol = max(1e-4, 1e-6 * self.diag)

    # the part's pieces, made on first use
    def rays(self, part: int) -> brep.Rays:
        if part not in self._rays:
            self._rays[part] = brep.Rays(self.parts[part].shape)
        return self._rays[part]

    def edges(self, part: int) -> list[brep.Edge]:
        if part not in self._edges:
            self._edges[part] = brep.edges(self.parts[part])
            adjacent: dict[int, dict[int, list[brep.Edge]]] = {}
            for edge in self._edges[part]:
                a, b = edge.faces
                adjacent.setdefault(a, {}).setdefault(b, []).append(edge)
                adjacent.setdefault(b, {}).setdefault(a, []).append(edge)
            self._adjacent[part] = adjacent
        return self._edges[part]

    def adjacent(self, part: int, ordinal: int) -> dict[int, list[brep.Edge]]:
        self.edges(part)
        return self._adjacent[part].get(ordinal, {})

    def info(self, part: int, ordinal: int) -> FaceInfo:
        return self.faces[part][ordinal - 1]

    def ref(self, part: int, ordinal: int) -> str:
        return self.parts[part].ref("face", ordinal)

    def on_plate(self, z: float) -> bool:
        return z <= self.z0 + self.tol

    def _group_rounds(self, part: int) -> None:
        for info in self.faces[part]:
            s = info.surface
            if s.kind != "cylinder" or s.concave is None or s.radius is None:
                continue
            axis = np.array(s.axis, dtype=float)
            axis = axis if (axis[2], axis[1], axis[0]) >= (0, 0, 0) else -axis
            origin = np.array(s.origin, dtype=float)
            for index, other in enumerate(self.rounds):
                if other.part != part or other.concave != s.concave or abs(other.radius - s.radius) > 1e-4:
                    continue
                if abs(abs(float(other.axis @ axis)) - 1.0) > 1e-6:
                    continue
                offset = origin - other.origin
                if np.linalg.norm(offset - other.axis * float(offset @ other.axis)) > 1e-4:
                    continue
                other.faces.append(info.ordinal)
                other.coverage_deg += info.coverage_deg
                info.group = index
                break
            else:
                info.group = len(self.rounds)
                self.rounds.append(Round(part, [info.ordinal], bool(s.concave), float(s.radius), axis, origin,
                                         info.coverage_deg))
        for group in self.rounds:
            if group.part != part:
                continue
            along = []
            for ordinal in group.faces:
                face = self.info(part, ordinal).face
                points = [np.array([v.X, v.Y, v.Z]) for v in face.vertices()]
                points += [sample.point for sample in self.info(part, ordinal).samples]
                along += [float((point - group.origin) @ group.axis) for point in points]
            group.lo, group.hi = (min(along), max(along)) if along else (0.0, 0.0)

    def rounds_of(self, concave: bool) -> list[tuple[int, Round]]:
        return [(index, group) for index, group in enumerate(self.rounds)
                if group.concave == concave and group.coverage_deg >= ROUND_DEG]

    def mesh(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Every part triangulated together: vertices, triangles, and each triangle's owner (part << 20 |
        face ordinal)."""
        if self._mesh is None:
            size = max(float(np.linalg.norm([p.shape.bounding_box(optimal=False).size.X,
                                             p.shape.bounding_box(optimal=False).size.Y,
                                             p.shape.bounding_box(optimal=False).size.Z])) for p in self.parts)
            deflection = min(0.25, max(0.005, 5e-4 * size))
            Vs, Fs, Os, offset = [], [], [], 0
            for index, part in enumerate(self.parts):
                V, F, O = brep.triangles(part.shape, deflection)
                Vs.append(V)
                Fs.append(F + offset)
                Os.append(O + (index << 20))
                offset += len(V)
            self._mesh = (np.vstack(Vs), np.vstack(Fs).astype(int), np.concatenate(Os).astype(int))
        return self._mesh

    def owner_ref(self, owner: int) -> str:
        return self.ref(owner >> 20, owner & 0xFFFFF)

    def measure_rays(self) -> None:
        """Every sample's wall (a ray into the material) and gap (a ray out of it, up to ``GAP_CEILING``)."""
        if getattr(self, "_rayed", False):
            return
        self._rayed = True
        for part, infos in enumerate(self.faces):
            rays = self.rays(part)
            shape = self.parts[part]
            for info in infos:
                adjacent = self.adjacent(part, info.ordinal)
                for k, sample in enumerate(info.samples):
                    hit = rays.first(sample.point, -sample.normal, skip=1e-5)
                    if hit is not None:
                        other = shape.face_ordinal(hit[1])
                        acute = any(not edge.concave and not edge.smooth for edge in adjacent.get(other, ()))
                        if not acute:
                            info.thickness.append((hit[0], k, other))
                    hit = rays.first(sample.point, sample.normal, skip=1e-5, end=GAP_CEILING)
                    if hit is not None:
                        other = shape.face_ordinal(hit[1])
                        same = other == info.ordinal or other in adjacent or (
                            info.group is not None and self.info(part, other).group == info.group)
                        if not same:
                            info.gap.append((hit[0], k, other))


# --- families -------------------------------------------------------------------------------------------------


def _solid(ctx: Context) -> dict[str, Any]:
    from OCP.BRep import BRep_Tool
    from OCP.BRepClass3d import BRepClass3d
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer

    from cad.build123d import _geometry

    items = []
    for index, part in enumerate(ctx.parts):
        solids = part.solids()
        inner = closed = 0
        shells = 0
        for solid in solids:
            outer = BRepClass3d.OuterShell_s(solid.wrapped)
            explorer = TopExp_Explorer(solid.wrapped, TopAbs_SHELL)
            while explorer.More():
                shell = explorer.Current()
                shells += 1
                closed += int(BRep_Tool.IsClosed_s(shell))
                if not shell.IsSame(outer):
                    inner += 1
                explorer.Next()
        if not solids:
            explorer = TopExp_Explorer(part.shape.wrapped, TopAbs_SHELL)
            while explorer.More():
                shells += 1
                closed += int(BRep_Tool.IsClosed_s(explorer.Current()))
                explorer.Next()
        issues: list[str] = []
        try:
            sound: bool | None = bool(_geometry.is_sound(part.shape))
            if not sound:
                issues = sorted({issue.code for issue in _geometry.topology_errors(part.shape)}) or ["boolean check"]
        except Exception:  # noqa: BLE001 - a check the kernel cannot finish is no verdict
            sound = None
        items.append({"part": part.name or part.owner or f"part {index + 1}", "location": ctx.ref(index, 1),
                      "xyz": _xyz(part.shape.bounding_box(optimal=False).center()), "solids": len(solids), "shells": shells,
                      "closed": bool(solids) and closed == shells, "inner_shells": inner, "sound": sound,
                      "issues": issues, "volume_mm3": _r(float(part.shape.volume), 3),
                      "area_mm2": _r(float(part.shape.area), 3), "occurrences": part.occurrences})
    return {"items": items, "part_count": len(items), "body_count": sum(item["solids"] for item in items),
            "volume_mm3": _r(sum(item["volume_mm3"] or 0.0 for item in items), 3),
            "watertight": all(item["closed"] for item in items),
            "sound": None if any(item["sound"] is None for item in items) else all(item["sound"] for item in items),
            "bbox_mm": _xyz(ctx.hi - ctx.lo)}


def _overhangs(ctx: Context) -> dict[str, Any]:
    limit = ctx.angle_limit
    total_area = sum(info.area for infos in ctx.faces for info in infos) or 1.0
    bridges = {(item["part"], item["ordinal"]): item["kind"] for item in _flat_ceilings(ctx)}
    plate_band = max(1.0, 5 * ctx.layer)
    items, histogram, below_total = [], np.zeros(9), 0.0
    for infos in ctx.faces:
        for info in infos:
            down = [s for s in info.samples if s.normal[2] < -1e-9 and not ctx.on_plate(float(s.point[2]))]
            if not down:
                continue
            if info.surface.kind == "plane" and info.surface.normal is not None:
                angle = math.degrees(math.acos(min(1.0, -info.surface.normal[2])))
                angles = np.full(len(down), angle)
            else:
                angles = np.degrees(np.arccos(np.clip([-s.normal[2] for s in down], -1.0, 1.0)))
            if angles.min() >= 89.9:
                continue
            area = np.array([s.area for s in down])
            scale = info.area / max(sum(s.area for s in info.samples), 1e-12)
            area = area * scale
            under = angles < limit
            heights = np.array([float(s.point[2]) - ctx.z0 for s in down])
            for value, share in zip(angles, area):
                histogram[min(8, int(value // 10))] += share
            worst = int(angles.argmin())
            kind = "slope"
            if info.group is not None and ctx.rounds[info.group].coverage_deg >= ROUND_DEG and \
                    ctx.rounds[info.group].concave:
                kind = "hole"
            elif (info.part, info.ordinal) in bridges:
                kind = bridges[(info.part, info.ordinal)]
            elif ctx.on_plate(info.zmin) and (not under.any() or heights[under].max() <= plate_band):
                kind = "plate_edge"
            below = float(area[under].sum())
            if kind not in ("hole", "plate_edge", "bridge"):
                below_total += below
            items.append({"location": ctx.ref(info.part, info.ordinal), "xyz": _xyz(down[worst].point),
                          "angle_deg": _r(float(angles.min()), 3), "area_mm2": _r(float(area.sum()), 3),
                          "area_below_limit_mm2": _r(below, 3), "height_mm": _r(float(heights.min()), 3),
                          "max_height_mm": _r(float(heights.max()), 3), "kind": kind, "surface": info.surface.kind})
    counted = [item for item in items if item["kind"] not in ("hole", "plate_edge", "bridge")
               and (item["area_below_limit_mm2"] or 0) > 0]
    largest = sorted(counted, key=lambda item: -(item["area_below_limit_mm2"] or 0))[:8]
    items, count = _capped(items, lambda item: (item["angle_deg"], -(item["area_mm2"] or 0)))
    bins = {f"{10 * k}-{10 * k + 10}deg": _r(float(v), 2) for k, v in enumerate(histogram) if v > 0}
    return {"items": items, "count": count, "angle_limit_used_deg": limit,
            "down_facing_area_below_limit_mm2": _r(below_total, 2),
            "down_facing_area_below_limit_pct": _r(100.0 * below_total / total_area, 1),
            "face_count_below_limit": len(counted), "down_facing_angle_histogram_mm2": bins,
            "largest_faces_below_limit": [{"location": item["location"], "location_xyz": item["xyz"],
                                           "surface_angle_deg": item["angle_deg"],
                                           "area_mm2": item["area_below_limit_mm2"]} for item in largest],
            "plate_band_mm": plate_band}


def _edge_points(edge: Any, step: float) -> np.ndarray:
    count = max(2, int(math.ceil(float(edge.length) / step)) + 1)
    return np.array([[p.X, p.Y, p.Z] for p in (edge.position_at(t) for t in np.linspace(0.0, 1.0, count))])


def _flat_ceilings(ctx: Context) -> list[dict[str, Any]]:
    if hasattr(ctx, "_ceilings"):
        return ctx._ceilings  # type: ignore[attr-defined]
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    found = []
    cos_flat = math.cos(math.radians(FLAT_DEG))
    for part, infos in enumerate(ctx.faces):
        edges = ctx.parts[part].edges()
        for info in infos:
            n = info.surface.normal
            if info.surface.kind != "plane" or n is None or not n[2] < -cos_flat or ctx.on_plate(info.zmin):
                continue
            starts, ends, supported = [], [], 0
            z = info.zmax
            box = info.box
            step = max(1e-3, min(0.5, 0.01 * max(box.size.X, box.size.Y)))
            for other, shared in ctx.adjacent(part, info.ordinal).items():
                neighbour = ctx.info(part, other)
                for edge in shared:
                    carries = edge.concave or (edge.smooth and neighbour.surface.concave is True)
                    if not carries or not neighbour.zmin < edge.midpoint[2] - ctx.tol:
                        continue
                    supported += 1
                    points = _edge_points(edges[edge.ordinal - 1], step)
                    starts.append(points[:-1])
                    ends.append(points[1:])
            points = np.array([s.point for s in brep.samples(info.face, 600)])
            face = info.face.wrapped

            def inside(candidates: np.ndarray, face: Any = face) -> np.ndarray:
                keep = []
                for point in candidates:
                    state = BRepClass_FaceClassifier(face, gp_Pnt(*map(float, point)), 1e-6).State()
                    keep.append(state in (TopAbs_IN, TopAbs_ON))
                return np.array(keep, dtype=bool)

            a = np.vstack(starts) if starts else np.zeros((0, 3))
            b = np.vstack(ends) if ends else np.zeros((0, 3))
            spread = mo.span(points, a, b, inside=inside, refine=2.0 * step)
            kind = {"bridge": "bridge", "cantilever": "cantilever"}.get(spread["kind"], "ceiling")
            found.append({"part": part, "ordinal": info.ordinal, "kind": kind,
                          "length_mm": _r(spread["length_mm"], 4), "reach_mm": _r(spread["reach_mm"], 4),
                          "supporting_edges": supported, "area_mm2": _r(info.area, 3),
                          "height_mm": _r(z - ctx.z0, 4), "angle_deg": _r(math.degrees(math.acos(min(1.0, -n[2]))), 3),
                          "location": ctx.ref(part, info.ordinal),
                          "xyz": _xyz(spread["xyz"] or info.samples[0].point)})
    ctx._ceilings = found  # type: ignore[attr-defined]
    return found


def _bridges(ctx: Context) -> dict[str, Any]:
    items = [{key: value for key, value in item.items() if key not in ("part", "ordinal")} for item in _flat_ceilings(ctx)]
    if ctx.technology in ("fdm", "sla") and ctx.angle_limit > 0:
        # a horizontal round hole's arch is bridged where it is under the angle limit: a chord of d sin(limit)
        for item in _round_items(ctx, True):
            if item["orientation"] == "horizontal" and not item["teardrop"]:
                chord = item["diameter_mm"] * math.sin(math.radians(ctx.angle_limit))
                items.append({"kind": "bridge", "length_mm": _r(chord, 4), "reach_mm": _r(chord / 2.0, 4),
                              "supporting_edges": 0, "arch": True, "diameter_mm": item["diameter_mm"],
                              "location": item["location"], "xyz": item["xyz"]})
    items, count = _capped(items, lambda item: -(item["length_mm"] or 0.0))
    return {"items": items, "count": count, "flat_within_deg": FLAT_DEG,
            "bridge_count": sum(1 for item in items if item["kind"] == "bridge"),
            "longest_bridge_mm": max((item["length_mm"] for item in items if item["kind"] == "bridge"), default=None)}


def _connections(ctx: Context, part: int, ordinal: int) -> int:
    """The sides a face is joined to the part by: its concave edges (and smooth ones into a concave round);
    a closed ring (a tube's face) counts as joined all round."""
    if ctx.info(part, ordinal).coverage_deg >= 355.0:
        return 2
    count = 0
    for other, shared in ctx.adjacent(part, ordinal).items():
        neighbour = ctx.info(part, other)
        count += sum(1 for edge in shared if edge.concave or (edge.smooth and neighbour.surface.concave is True))
    return count


def _walls(ctx: Context) -> dict[str, Any]:
    ctx.measure_rays()
    items, every, where = [], [], []
    for part, infos in enumerate(ctx.faces):
        for info in infos:
            pin = info.group is not None and not ctx.rounds[info.group].concave and \
                ctx.rounds[info.group].coverage_deg >= ROUND_DEG
            if not info.thickness or pin:  # a pin's thickness is its diameter: the pins' rules judge it
                continue
            values = np.array([t for t, _, _ in info.thickness])
            thinnest = info.thickness[int(values.argmin())]
            every.extend(values.tolist())
            where.extend((float(t), info.samples[k].point) for t, k, _ in info.thickness)
            joined = max(_connections(ctx, part, info.ordinal), _connections(ctx, part, thinnest[2]))
            items.append({"location": ctx.ref(part, info.ordinal), "xyz": _xyz(info.samples[thinnest[1]].point),
                          "thickness_mm": _r(thinnest[0], 4), "median_mm": _r(float(np.median(values)), 4),
                          "opposite": ctx.ref(part, thinnest[2]), "faces": [ctx.ref(part, thinnest[2])],
                          "supported": joined >= 2, "joined_sides": joined, "samples": len(values)})
    if not every:
        return {"items": [], "samples_valid": 0, "note": "no ray met a wall: the shape is open or empty"}
    field_ = np.array(every)
    seen, unique = set(), []
    for item in sorted(items, key=lambda item: item["thickness_mm"]):
        pair = tuple(sorted((item["location"], item["opposite"])))
        if pair not in seen:
            seen.add(pair)
            unique.append(item)
    items, count = _capped(unique, lambda item: item["thickness_mm"])
    thinnest = sorted(where, key=lambda pair: pair[0])[:8]
    return {"items": items, "count": count, "samples_valid": int(len(field_)),
            "min_mm": _r(float(field_.min()), 4), "p05_mm": _r(float(np.percentile(field_, 5)), 4),
            "p25_mm": _r(float(np.percentile(field_, 25)), 4), "median_mm": _r(float(np.median(field_)), 4),
            "max_mm": _r(float(field_.max()), 4), "method": "exact rays into the material from samples on every face",
            "thinnest_samples": [{"location_xyz": _xyz(point), "thickness_mm": _r(value, 4)} for value, point in thinnest]}


def _gaps(ctx: Context) -> dict[str, Any]:
    ctx.measure_rays()
    items = []
    for part, infos in enumerate(ctx.faces):
        for info in infos:
            if not info.gap:
                continue
            width, k, other = min(info.gap)
            items.append({"location": ctx.ref(part, info.ordinal), "xyz": _xyz(info.samples[k].point),
                          "gap_mm": _r(width, 4), "faces": [ctx.ref(part, other)]})
    # a slot is seen from both its walls: keep each pair once
    seen, unique = set(), []
    for item in sorted(items, key=lambda item: item["gap_mm"]):
        pair = tuple(sorted((item["location"], item["faces"][0])))
        if pair in seen:
            continue
        seen.add(pair)
        unique.append(item)
    unique, count = _capped(unique, lambda item: item["gap_mm"])
    return {"items": unique, "count": count, "reported_below_mm": GAP_CEILING,
            "min_mm": unique[0]["gap_mm"] if unique else None,
            "method": "exact rays out of the material from samples on every face, to another face of the same part "
                      "(not a neighbour, not the same hole)"}


def _orientation(axis: np.ndarray) -> str:
    tilt = math.degrees(math.acos(min(1.0, abs(float(axis[2])))))
    return "vertical" if tilt < 10.0 else "horizontal" if tilt > 80.0 else "inclined"


def _round_items(ctx: Context, concave: bool) -> list[dict[str, Any]]:
    from cad.build123d._dfm_brep import inside

    items = []
    for index, group in ctx.rounds_of(concave):
        part = group.part
        largest = max(group.faces, key=lambda ordinal: ctx.info(part, ordinal).area)
        center = group.origin + group.axis * (0.5 * (group.lo + group.hi))
        length = group.hi - group.lo
        item = {"location": ctx.ref(part, largest), "xyz": _xyz(center), "diameter_mm": _r(2.0 * group.radius, 4),
                "orientation": _orientation(group.axis), "axis": _xyz(group.axis),
                "coverage_deg": _r(min(360.0, group.coverage_deg), 2),
                "faces": [ctx.ref(part, ordinal) for ordinal in group.faces if ordinal != largest]}
        if concave:
            item["depth_mm"] = _r(length, 4)
            ends = [group.origin + group.axis * (group.lo - 1e-3 * max(1.0, group.radius)),
                    group.origin + group.axis * (group.hi + 1e-3 * max(1.0, group.radius))]
            solids = ctx.parts[part].solids() or [ctx.parts[part].shape]
            closed = [any(inside(solid, [end])[0] for solid in solids) for end in ends]
            item["through"] = not any(closed)
            item["channel"] = bool(length >= 5.0 * 2.0 * group.radius)
            up = np.array([0.0, 0.0, 1.0]) - group.axis * float(group.axis[2])
            top = 1.0
            if np.linalg.norm(up) > 1e-9 and group.coverage_deg < 355.0:
                up /= np.linalg.norm(up)
                radial = []
                for ordinal in group.faces:
                    for sample in ctx.info(part, ordinal).samples:
                        rel = sample.point - group.origin
                        rel = rel - group.axis * float(rel @ group.axis)
                        radial.append(float(rel @ up) / (np.linalg.norm(rel) or 1.0))
                top = max(radial, default=1.0)
            item["teardrop"] = bool(item["orientation"] == "horizontal" and top < math.cos(math.radians(15.0)))
            item["low_z_mm"] = _r(min(ctx.info(part, ordinal).zmin for ordinal in group.faces) - ctx.z0, 4)
        else:
            item["height_mm"] = _r(length, 4)
            item["aspect_ratio"] = _r(length / (2.0 * group.radius), 3)
        items.append(item)
    return items


def _holes(ctx: Context) -> dict[str, Any]:
    items, count = _capped(_round_items(ctx, True), lambda item: item["diameter_mm"])
    return {"items": items, "count": count, "round_deg": ROUND_DEG,
            "horizontal_count": sum(1 for item in items if item["orientation"] == "horizontal")}


def _pins(ctx: Context) -> dict[str, Any]:
    items, count = _capped(_round_items(ctx, False), lambda item: item["diameter_mm"])
    return {"items": items, "count": count, "round_deg": ROUND_DEG}


def _details(ctx: Context) -> dict[str, Any]:
    ctx.measure_rays()
    found: dict[tuple[int, int, str], dict[str, Any]] = {}
    for part, infos in enumerate(ctx.faces):
        for side in infos:
            ns = side.surface.normal
            if side.surface.kind != "plane" or ns is None:
                continue
            tops, bottoms = [], []
            for other, shared in ctx.adjacent(part, side.ordinal).items():
                neighbour = ctx.info(part, other)
                if neighbour.surface.kind != "plane" or neighbour.surface.normal is None:
                    continue
                if abs(float(np.dot(neighbour.surface.normal, ns))) > 0.2:
                    continue
                for edge in shared:
                    if edge.smooth:
                        continue
                    (bottoms if edge.concave else tops).append(neighbour)
            for top in tops:
                for bottom in bottoms:
                    nt, nb = np.array(top.surface.normal), np.array(bottom.surface.normal)
                    if float(nt @ nb) < 0.999:
                        continue
                    height = float((np.array(top.surface.origin) - np.array(bottom.surface.origin)) @ nt)
                    if not 1e-6 < height <= DETAIL_CEILING:
                        continue
                    emboss = top.area < bottom.area
                    region = top if emboss else bottom
                    widths = [t for t, _, _ in side.thickness] if emboss else [g for g, _, _ in side.gap]
                    width = min(widths) if widths else None
                    key = (part, region.ordinal, "emboss" if emboss else "engrave")
                    item = found.get(key)
                    if item is None:
                        found[key] = item = {"location": ctx.ref(part, region.ordinal),
                                             "xyz": _xyz(side.samples[0].point if side.samples else [0, 0, 0]),
                                             "kind": key[2], "height_mm": _r(height, 4), "width_mm": _r(width, 4),
                                             "faces": []}
                    item["height_mm"] = _r(min(item["height_mm"], height), 4)
                    if width is not None and (item["width_mm"] is None or width < item["width_mm"]):
                        item["width_mm"] = _r(width, 4)
                    if ctx.ref(part, side.ordinal) not in item["faces"]:
                        item["faces"].append(ctx.ref(part, side.ordinal))
    items, count = _capped(list(found.values()), lambda item: (item["height_mm"], item["width_mm"] or 0.0))
    for item in items:
        item["faces"] = item["faces"][:12]
    return {"items": items, "count": count, "step_ceiling_mm": DETAIL_CEILING}


def _face_at(ctx: Context, part: int, point: np.ndarray) -> int:
    """The ordinal of the face of ``part`` nearest ``point``."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, point))).Vertex()
    best, found = math.inf, 1
    for info in ctx.faces[part]:
        box = info.box
        lower = max(0.0, box.min.X - point[0], point[0] - box.max.X, box.min.Y - point[1], point[1] - box.max.Y,
                    box.min.Z - point[2], point[2] - box.max.Z)
        if lower > best:
            continue
        query = BRepExtrema_DistShapeShape(vertex, info.face.wrapped)
        if query.IsDone() and query.Value() < best:
            best, found = float(query.Value()), info.ordinal
    return found


def _clearances(ctx: Context) -> dict[str, Any]:
    from cad.build123d import _geometry

    items, reach = [], 5.0
    boxes = [part.shape.bounding_box(optimal=False) for part in ctx.parts]
    for a in range(len(ctx.parts)):
        for b in range(a + 1, len(ctx.parts)):
            ba, bb = boxes[a], boxes[b]
            gap = max(0.0, ba.min.X - bb.max.X, bb.min.X - ba.max.X, ba.min.Y - bb.max.Y, bb.min.Y - ba.max.Y,
                      ba.min.Z - bb.max.Z, bb.min.Z - ba.max.Z)
            if gap > reach:
                continue
            closest = _geometry.closest_points(ctx.parts[a].shape, ctx.parts[b].shape)
            if closest.distance > reach:
                continue
            pa = np.array([closest.point_a.X, closest.point_a.Y, closest.point_a.Z])
            pb = np.array([closest.point_b.X, closest.point_b.Y, closest.point_b.Z])
            overlap = None
            if closest.distance <= 1e-6:
                try:
                    overlap = float(_geometry.overlap_volume(ctx.parts[a].shape, ctx.parts[b].shape))
                except Exception:  # noqa: BLE001 - a boolean that fails leaves the overlap unmeasured
                    overlap = None
            kind = "gap" if closest.distance > 1e-6 else ("overlap" if (overlap or 0) > 1e-6 else "contact")
            items.append({"location": ctx.ref(a, _face_at(ctx, a, pa)), "xyz": _xyz((pa + pb) / 2.0),
                          "distance_mm": _r(closest.distance, 5), "kind": kind, "overlap_mm3": _r(overlap, 4),
                          "faces": [ctx.ref(b, _face_at(ctx, b, pb))],
                          "parts": [ctx.parts[a].name or ctx.parts[a].owner, ctx.parts[b].name or ctx.parts[b].owner]})
    items, count = _capped(items, lambda item: item["distance_mm"])
    return {"items": items, "count": count, "part_count": len(ctx.parts), "reported_below_mm": reach,
            "min_mm": items[0]["distance_mm"] if items else None,
            "method": "exact minimum distance between each pair of parts (BRepExtrema)"}


def _grid(ctx: Context, part: int) -> tuple[Any, list[mo.Cavity], np.ndarray, float] | None:
    """The part's voxel field, its cavities and labels, and the probing ball's radius."""
    if part in ctx._grids:
        return ctx._grids[part]
    shape = ctx.parts[part].shape
    box = shape.bounding_box(optimal=False)
    size = np.array([box.size.X, box.size.Y, box.size.Z])
    if size.min() <= 0:
        ctx._grids[part] = None
        return None
    pitch, ball = mo.field_pitch(size)
    V, F, O = ctx.mesh()
    own = (O >> 20) == part
    used = np.unique(F[own])
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    grid = mo.voxels(V[used], remap[F[own]], pitch, pad=mo.ball_pad(ball, pitch))
    found, labels = mo.cavities(grid, ball)
    ctx._grids[part] = (grid, found, labels, ball)
    return ctx._grids[part]


def _inner_shells(ctx: Context, part: int) -> list[dict[str, Any]]:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.BRepClass3d import BRepClass3d
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    found = []
    for solid in ctx.parts[part].solids():
        outer = BRepClass3d.OuterShell_s(solid.wrapped)
        shells = TopExp_Explorer(solid.wrapped, TopAbs_SHELL)
        while shells.More():
            shell = shells.Current()
            shells.Next()
            if shell.IsSame(outer):
                continue
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(BRepBuilderAPI_MakeSolid(TopoDS.Shell(shell)).Solid(), props)
            faces = []
            explorer = TopExp_Explorer(shell, TopAbs_FACE)
            while explorer.More():
                ordinal = ctx.parts[part].face_ordinal(explorer.Current())
                if ordinal:
                    faces.append(ordinal)
                explorer.Next()
            center = props.CentreOfMass()
            found.append({"volume_mm3": abs(float(props.Mass())), "faces": sorted(set(faces)),
                          "centroid": np.array([center.X(), center.Y(), center.Z()])})
    return found


def _trapped(ctx: Context) -> dict[str, Any]:
    ctx.measure_rays()
    items, pitches, balls = [], [], []
    for part in range(len(ctx.parts)):
        made = _grid(ctx, part)
        exact = _inner_shells(ctx, part)
        if made is None:
            continue
        grid, found, labels, ball = made
        pitches.append(grid.pitch)
        balls.append(ball)

        def label(point: np.ndarray, grid: Any = grid, labels: np.ndarray = labels) -> int:
            return int(labels[grid.index(np.asarray(point))[0]])

        cavities: list[dict[str, Any]] = []
        for k, cavity in enumerate(found):
            cavities.append({"k": k, "volume_mm3": cavity.volume_mm3, "sealed": cavity.sealed, "exact": False,
                             "centroid": cavity.centroid, "faces": [], "openings": cavity.openings, "holes": []})
        # every inner shell is a sealed cavity, measured exactly; it replaces the voxels' reading of it
        for shell in exact:
            k = None
            for ordinal in shell["faces"]:
                info = ctx.info(part, ordinal)
                for sample in info.samples[:6]:
                    probe = label(sample.point + sample.normal * 0.75 * grid.pitch)
                    if probe >= 0:
                        k = probe
                        break
                if k is not None:
                    break
            entry = next((c for c in cavities if c["k"] == k), None) if k is not None else None
            if entry is None:
                entry = {"k": None, "openings": [], "holes": []}
                cavities.append(entry)
            entry.update(volume_mm3=shell["volume_mm3"], sealed=True, exact=True, centroid=shell["centroid"],
                         faces=shell["faces"])
        # escape holes: the holes with one end in the cavity and the other outside
        for index, group in ctx.rounds_of(True):
            if group.part != part:
                continue
            reach = 1.5 * grid.pitch + 1e-3
            ends = [group.origin + group.axis * (group.lo - reach), group.origin + group.axis * (group.hi + reach)]
            marks = [label(end) for end in ends]
            for cavity in cavities:
                if cavity["k"] is not None and cavity["k"] in marks and any(m in (-1,) for m in marks):
                    cavity["holes"].append(group)
        for cavity in cavities:
            walls = []
            if cavity["k"] is not None:
                for info in ctx.faces[part]:
                    for t, k, _ in info.thickness:
                        sample = info.samples[k]
                        if label(sample.point + sample.normal * 0.75 * grid.pitch) == cavity["k"]:
                            walls.append((t, info.ordinal))
            for ordinal in cavity["faces"]:
                walls += [(t, ordinal) for t, _, _ in ctx.info(part, ordinal).thickness]
            diameters = sorted(2.0 * group.radius for group in cavity["holes"])
            # voxel openings no hole explains: an opening of another shape, its width estimated
            for opening in cavity["openings"]:
                explained = False
                for group in cavity["holes"]:
                    rel = opening["xyz"] - group.origin
                    off = np.linalg.norm(rel - group.axis * float(rel @ group.axis))
                    explained |= bool(off <= group.radius + 2.0 * grid.pitch)
                if not explained:
                    diameters.append(float(opening["diameter_mm"]))
            diameters.sort()
            thinnest = min(walls) if walls else None
            location = (ctx.ref(part, thinnest[1]) if thinnest else
                        ctx.ref(part, cavity["faces"][0]) if cavity["faces"] else ctx.ref(part, 1))
            items.append({"location": location, "xyz": _xyz(cavity["centroid"]),
                          "volume_mm3": _r(cavity["volume_mm3"], 2), "sealed": bool(cavity["sealed"] and not diameters),
                          "exact": cavity["exact"], "escape_holes": len(diameters),
                          "escape_hole_diameters_mm": [_r(d, 4) for d in diameters],
                          "min_escape_hole_mm": _r(diameters[0], 4) if diameters else None,
                          "min_wall_mm": _r(thinnest[0], 4) if thinnest else None,
                          "faces": [ctx.ref(part, ordinal) for ordinal in cavity["faces"][:12]]})
    items, count = _capped(items, lambda item: (item["escape_holes"], -(item["volume_mm3"] or 0)))
    return {"items": items, "count": count, "sealed_count": sum(1 for item in items if item["sealed"]),
            "trapped_volume_mm3": _r(sum(item["volume_mm3"] or 0 for item in items), 2),
            "pitch_mm": _r(max(pitches), 4) if pitches else None, "ball_radius_mm": _r(max(balls), 3) if balls else None,
            "method": "inner shells exactly; air a ball cannot reach from outside, from a voxel field; escape holes the "
                      "exact holes from a cavity to outside, other openings estimated from the voxels"}


def _build_volume(ctx: Context) -> dict[str, Any]:
    return mo.build_fit(ctx.lo, ctx.hi, rules.machine_volume(ctx.options))


def _bed(ctx: Context) -> dict[str, Any]:
    items, contact, xs, ys = [], 0.0, [], []
    sharp = 0.0
    for part, infos in enumerate(ctx.faces):
        for info in infos:
            n = info.surface.normal
            if info.surface.kind != "plane" or n is None or n[2] > -0.9999 or not ctx.on_plate(info.zmax):
                continue
            box = info.box
            contact += info.area
            xs += [box.min.X, box.max.X]
            ys += [box.min.Y, box.max.Y]
            for other, shared in ctx.adjacent(part, info.ordinal).items():
                sharp += sum(edge.length for edge in shared if not edge.concave and not edge.smooth
                             and abs(edge.angle_deg - 90.0) < 1.0)
            items.append({"location": ctx.ref(part, info.ordinal), "xyz": _xyz(box.center()),
                          "area_mm2": _r(info.area, 3), "length_mm": _r(max(box.size.X, box.size.Y), 4)})
    holes = sum(1 for _, group in ctx.rounds_of(True) if _orientation(group.axis) == "vertical"
                and min(ctx.info(group.part, o).zmin for o in group.faces) <= ctx.z0 + ctx.tol)
    footprint = (ctx.hi - ctx.lo)[:2]
    items.sort(key=lambda item: -item["area_mm2"])
    return {"items": items[:CAP], "count": len(items), "contact_area_mm2": _r(contact, 3),
            "footprint_mm": _xyz(footprint), "footprint_area_mm2": _r(float(footprint[0] * footprint[1]), 3),
            "contact_ratio": _r(contact / float(footprint[0] * footprint[1]), 4) if footprint.prod() > 0 else None,
            "contact_length_mm": _r(max(max(xs) - min(xs), max(ys) - min(ys)), 4) if xs else 0.0,
            "sharp_bottom_edges_mm": _r(sharp, 3), "holes_on_plate": holes}


def _stairs(ctx: Context) -> dict[str, Any]:
    items, bins = [], np.zeros(4)
    edges = [0.5, 5.0, 10.0, 15.0, SHALLOW_DEG]
    for part, infos in enumerate(ctx.faces):
        for info in infos:
            if not info.samples:
                continue
            tilt = np.degrees(np.arccos(np.clip([abs(float(s.normal[2])) for s in info.samples], 0.0, 1.0)))
            shallow = (tilt > edges[0]) & (tilt < SHALLOW_DEG)
            if not shallow.any():
                continue
            scale = info.area / max(sum(s.area for s in info.samples), 1e-12)
            area = np.array([s.area for s in info.samples]) * scale
            for k in range(4):
                bins[k] += float(area[shallow & (tilt >= edges[k]) & (tilt < edges[k + 1])].sum())
            mean = float(np.average(tilt[shallow], weights=area[shallow]))
            up = float(np.average([s.normal[2] for s, keep in zip(info.samples, shallow) if keep])) > 0
            items.append({"location": ctx.ref(part, info.ordinal), "xyz": _xyz(info.samples[int(np.flatnonzero(shallow)[0])].point),
                          "angle_deg": _r(mean, 3), "area_mm2": _r(float(area[shallow].sum()), 3),
                          "cusp_mm": _r(ctx.layer * math.cos(math.radians(mean)), 4),
                          "step_width_mm": _r(ctx.layer / math.tan(math.radians(mean)), 4),
                          "facing": "up" if up else "down"})
    items, count = _capped(items, lambda item: -item["area_mm2"])
    return {"items": items, "count": count, "layer_height_mm": ctx.layer, "shallow_below_deg": SHALLOW_DEG,
            "area_by_angle_mm2": {f"{edges[k]:g}-{edges[k + 1]:g}deg": _r(float(bins[k]), 2) for k in range(4)},
            "area_mm2": _r(float(bins.sum()), 2)}


def _pitch(ctx: Context) -> float:
    return mo.raster_pitch(ctx.hi - ctx.lo)


def _cosmetic(ctx: Context) -> set[int]:
    """The faces a support mark spoils, as owners: each part's faces of 5% of its area or more, holes aside."""
    chosen = set()
    for part, infos in enumerate(ctx.faces):
        total = sum(info.area for info in infos) or 1.0
        for info in infos:
            hole = info.group is not None and ctx.rounds[info.group].concave
            if info.area >= 0.05 * total and not hole:
                chosen.add((part << 20) | info.ordinal)
    return chosen


def _support(ctx: Context) -> dict[str, Any]:
    V, F, O = ctx.mesh()
    held = mo.support(V, F, ctx.angle_limit, _pitch(ctx), plate_z=ctx.z0, owners=O)
    volume = sum(float(part.shape.volume) for part in ctx.parts)
    cosmetic = _cosmetic(ctx)
    items = [{"location": ctx.owner_ref(owner), "contact_mm2": _r(area, 3), "cosmetic": owner in cosmetic}
             for owner, area in held["per_owner_mm2"].items()]
    items, count = _capped(items, lambda item: -item["contact_mm2"])
    return {"items": items, "count": count, "angle_limit_used_deg": ctx.angle_limit,
            "estimated_support_volume_mm3": _r(held["volume_mm3"], 2), "part_volume_mm3": _r(volume, 2),
            "support_to_part_ratio_pct": _r(100.0 * held["volume_mm3"] / volume, 2) if volume > 0 else None,
            "support_contact_mm2": _r(held["contact_area_mm2"], 2),
            "support_contact_cosmetic_mm2": _r(sum(i["contact_mm2"] for i in items if i["cosmetic"]), 2),
            "pitch_mm": _r(held["pitch_mm"], 4),
            "method": "column fill under every down-facing surface under the angle limit, down to the part or the "
                      "plate, from a raster of the triangulation along Z"}


def _sections(ctx: Context) -> dict[str, Any]:
    """The thickest sections -- the largest ball each part's material holds, from its voxel field -- and the
    cross-sections layer by layer (residual stress in metal follows a large flat section)."""
    items: list[dict[str, Any]] = []
    best: dict[str, Any] = {}
    for part in range(len(ctx.parts)):
        made = _grid(ctx, part)
        if made is None:
            continue
        found = mo.sections(made[0])
        if found["thickness_mm"] is not None:
            items.append({"location": ctx.ref(part, _face_at(ctx, part, found["center"])), "xyz": _xyz(found["center"]),
                          "thickness_mm": _r(found["thickness_mm"], 3), "at_least": found["at_least"],
                          "pitch_mm": _r(made[0].pitch, 4)})
        if found.get("max_cross_section_mm2", 0) > best.get("max_cross_section_mm2", -1):
            best = found
    items.sort(key=lambda item: -item["thickness_mm"])
    report: dict[str, Any] = {"items": items, "count": len(items),
                              "max_thickness_mm": items[0]["thickness_mm"] if items else None, "measured_up_to_mm": 12.0,
                              "method": "the largest ball each part's material holds, from its voxel field (to a "
                                        "voxel); thicker than measured_up_to_mm reads at_least"}
    if best.get("max_cross_section_mm2") is not None:
        report.update(max_cross_section_mm2=_r(best["max_cross_section_mm2"], 2),
                      max_cross_section_z_mm=_r(best["max_cross_section_z"] - ctx.z0, 4),
                      largest_section_change_mm2=_r(best["largest_section_change_mm2"], 2))
    return report


def _scale(ctx: Context) -> dict[str, Any]:
    suspect = bool(ctx.diag < 1.0)
    return {"bbox_diagonal_mm": _r(ctx.diag, 4), "units_suspect": suspect,
            "note": ("bbox diagonal under 1 mm; the model is probably in metres or inches drawn as millimetres"
                     if suspect else "bbox consistent with millimetre units")}


def _orientations(ctx: Context) -> dict[str, Any]:
    V, F, O = ctx.mesh()
    candidates = dict(mo.ROTATIONS)
    # each of the largest flat faces laid on the plate, where no axis orientation already lays it
    planes = sorted((info for infos in ctx.faces for info in infos if info.surface.kind == "plane"),
                    key=lambda info: -info.area)
    for info in planes:
        n = np.array(info.surface.normal)
        if np.max(np.abs(n)) > 0.9999 or any(np.allclose(R @ n, [0, 0, -1], atol=1e-4) for R in candidates.values()):
            continue
        candidates[f"face_down:{ctx.ref(info.part, info.ordinal)}"] = mo.down_to(n)
        if len(candidates) >= 10:
            break
    rows = mo.orientation_rows(V, F, candidates, ctx.angle_limit, _pitch(ctx), SHALLOW_DEG, owners=O,
                               cosmetic=_cosmetic(ctx))
    volume = np.array(rules.machine_volume(ctx.options)["volume_mm"])
    for row in rows:
        box = np.array(row["bbox_mm"])
        xy = max(float(sorted(box[:2])[k]) / float(sorted(volume[:2])[k]) for k in range(2))
        row["fill_ratio"] = _r(max(xy, float(box[2]) / float(volume[2])), 4)
        row["fits"] = bool(row["fill_ratio"] <= 1.0 + 1e-9)
        row["support_area_mm2"] = row["overhang_area_mm2"]
    weights = mo.WEIGHTS["powder" if ctx.technology in rules.POWDER else "support"]
    rows = mo.ranked(rows, weights)
    return {"angle_limit_used_deg": ctx.angle_limit, "weights": weights, "candidates": rows,
            "best": rows[0]["orientation"] if rows else None,
            "ranking": "each figure over the largest any candidate has, weighted, summed: lowest first"}


FAMILIES: tuple[tuple[str, Callable[[Context], dict[str, Any]]], ...] = (
    ("solid", _solid), ("scale", _scale), ("overhangs", _overhangs), ("bridges", _bridges),
    ("wall_thickness", _walls), ("gaps", _gaps), ("holes", _holes), ("pins", _pins), ("details", _details),
    ("clearances", _clearances), ("trapped_volumes", _trapped), ("build_volume", _build_volume), ("bed", _bed),
    ("stair_stepping", _stairs), ("support_volume", _support), ("sections", _sections),
)


def measure(document: brep.Document, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The printing report of ``document``: facts alone, every family's ``items`` at a ref."""
    from cad._internal.dfm import Unmeasured

    if not document.parts:
        raise Unmeasured("not_measured", "the document has no parts to print")
    ctx = Context(document, options)
    report: dict[str, Any] = {"technology": ctx.technology}
    if candidates:
        report["scale"] = _safe(lambda: _scale(ctx))
        report["orientations"] = _safe(lambda: _orientations(ctx))
    else:
        for name, family in FAMILIES:
            report[name] = _safe(lambda family=family: family(ctx))
    failed = sorted(name for name, value in report.items() if isinstance(value, dict) and "error" in value)
    report["partial"] = bool(failed)
    if failed:
        report["partial_sections"] = failed
    return report

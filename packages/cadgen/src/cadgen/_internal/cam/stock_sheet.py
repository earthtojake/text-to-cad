"""The sheet stock simulator (laser, plasma, waterjet, wire EDM): the sheet as a 2D shape minus every kerf it cut.

A beam, a jet or a wire goes through the whole thickness wherever it cuts, so the stock is a flat shape (shapely,
part XY) extruded between the sheet's bottom and top. :meth:`SheetSim.cut` sweeps each operation's cutting moves
(feeds, plunges and arcs, sampled within the tolerance) with a disc of the cut's width and takes the swept area away;
the width is the operation's ``kerf_mm`` (its plan meta: a beam's kerf, a wire's diameter plus twice its spark gap),
else the tool's. Rapids cut nothing. Only setups that look along Z are simulated (:meth:`SheetSim.supports`).

What it reports:

* :meth:`SheetSim.mesh` the sheet now (skeleton, parts and slugs that are still there), extruded;
* :meth:`SheetSim.material_left`: for each part the operation meant to cut, the piece of sheet that holds it (with
  its microjoints broken, as a person breaks them out) minus the part: inside corners the cut could not reach, a hole
  that was not cut, a sliver between two cuts, or a skeleton still joined to a part that was never cut free;
* :func:`analyse` (also used by the planners on their own paths): which parts fall free, which are held by
  microjoints, which are not cut free, and how many slugs (scraps inside a part's outline) drop out.

Stdlib at import (the engine imports it only to simulate); numpy and shapely inside.
"""

from __future__ import annotations

from cadgen._internal.cam.stock import MaterialLeft, SimReport

__all__ = ["SheetSim", "analyse", "swept", "cutting_runs"]

#: Excess smaller than this (mm²) is the polygonal offset's own noise.
_NOISE_MM2 = 1e-3


def cutting_runs(toolpath, *, tolerance: float):
    """The toolpath's cutting moves as runs of (M, 3) WCS points, in order (a run starts where its first cutting move
    starts)."""
    import numpy as np

    from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, FEED, PLUNGE

    if not len(toolpath):
        return []
    samples = toolpath.sample(max(tolerance, 0.005))
    cutting = np.isin(samples.kind, (FEED, PLUNGE, ARC_CW, ARC_CCW))
    cutting[0] = False
    runs = []
    k = 1
    n = len(cutting)
    while k < n:
        if not cutting[k]:
            k += 1
            continue
        start = k
        while k < n and cutting[k]:
            k += 1
        runs.append(samples.points[start - 1:k])
    return runs


def swept(runs_xy, width: float):
    """The area a cut of ``width`` takes along runs of (M, 2) points: round-ended buffers of each run."""
    import numpy as np
    import shapely

    pieces = []
    radius = width / 2.0
    for run in runs_xy:
        run = np.asarray(run, dtype=float)[:, :2]
        keep = np.concatenate([[True], np.linalg.norm(np.diff(run, axis=0), axis=1) > 1e-9])
        run = run[keep]
        geometry = shapely.Point(run[0]) if len(run) == 1 else shapely.LineString(run)
        pieces.append(geometry.buffer(radius, quad_segs=8))
    return shapely.union_all(pieces) if pieces else shapely.Polygon()


def analyse(sheet, removed, design, *, tolerance: float, breaks=()) -> dict:
    """Which ``design`` parts fall free of ``sheet`` minus ``removed``: ``free``, ``held`` (free once the
    microjoint ``breaks`` (shapely shapes) are broken out), ``not_free``, each a list of part indices; ``slugs``
    (scraps inside a part's outline that drop) and ``excess`` (per part, the material its piece holds beyond the
    part, with the breaks broken: a polygon)."""
    import shapely

    from cadgen._internal.cam.geom2d import polygons_of

    left = shapely.difference(sheet, removed)
    broken = shapely.difference(left, shapely.union_all(list(breaks))) if breaks else left
    pieces = polygons_of(left)
    broken_pieces = polygons_of(broken)
    tree = shapely.STRtree(pieces) if pieces else None
    broken_tree = shapely.STRtree(broken_pieces) if broken_pieces else None
    out = {"parts": len(design), "free": [], "held": [], "not_free": [], "slugs": 0, "excess": []}

    def owner(polygon, candidates, index_tree):
        if index_tree is None:
            return None
        best, area = None, 0.0
        for j in index_tree.query(polygon):
            a = candidates[int(j)].intersection(polygon).area
            if a > area:
                best, area = candidates[int(j)], a
        return best

    def is_just(piece, polygon) -> bool:
        extra = shapely.difference(piece, polygon.buffer(max(tolerance, 0.01)))
        return extra.area <= max(1.0, 0.01 * polygon.area)

    for index, polygon in enumerate(design):
        piece = owner(polygon, pieces, tree)
        broken_piece = owner(polygon, broken_pieces, broken_tree)
        if piece is not None and is_just(piece, polygon):
            out["free"].append(index)
        elif broken_piece is not None and is_just(broken_piece, polygon):
            out["held"].append(index)
        else:
            out["not_free"].append(index)
        excess = shapely.difference(broken_piece, polygon.buffer(max(tolerance, 1e-4))) if broken_piece is not None \
            else shapely.Polygon()
        out["excess"].append(excess)
    outlines = [shapely.Polygon(p.exterior) for p in design]
    union = shapely.union_all(design) if design else shapely.Polygon()
    for piece in pieces:
        # Bits smaller than a square millimetre (between a lead-in and a lead-out) are dust, not slugs.
        if piece.area < 1.0 or piece.intersection(union).area > 0.01 * piece.area:
            continue
        probe = piece.representative_point()
        if any(outline.contains(probe) for outline in outlines):
            out["slugs"] += 1
    return out


def _extrude(polygons, z0: float, z1: float):
    """A closed mesh of shapely polygons between heights ``z0`` and ``z1``."""
    import numpy as np
    import shapely
    from shapely.geometry.polygon import orient

    vertices, triangles = [], []
    offset = 0
    for polygon in polygons:
        tris = shapely.get_parts(shapely.constrained_delaunay_triangles(polygon))
        if len(tris):
            corners = np.asarray([np.asarray(t.exterior.coords)[:3] for t in tris])
            e1, e2 = corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]
            ccw = (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 0
            corners[~ccw] = corners[~ccw][:, [0, 2, 1]]
            for z, flip in ((z1, False), (z0, True)):
                ordered = corners[:, [0, 2, 1]] if flip else corners
                pts = np.concatenate([ordered.reshape(-1, 2), np.full((len(ordered) * 3, 1), z)], axis=1)
                vertices.append(pts)
                triangles.append(np.arange(len(pts)).reshape(-1, 3) + offset)
                offset += len(pts)
        oriented = orient(polygon, 1.0)
        for ring in (oriented.exterior, *oriented.interiors):
            coords = np.asarray(ring.coords)[:, :2]
            a, b = coords[:-1], coords[1:]
            m = len(a)
            if not m:
                continue
            quads = np.stack([np.column_stack([a, np.full(m, z0)]), np.column_stack([b, np.full(m, z0)]),
                              np.column_stack([b, np.full(m, z1)]), np.column_stack([a, np.full(m, z1)])], axis=1)
            vertices.append(quads.reshape(-1, 3))
            base = offset + 4 * np.arange(m)[:, None]
            triangles.append(np.vstack([base + [0, 1, 2], base + [0, 2, 3]]))
            offset += 4 * m
    if not vertices:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.vstack(vertices), np.vstack(triangles).astype(np.int64)


class SheetSim:
    kind = "sheet"

    def __init__(self, stock, part=None, *, cell_mm: float = 1.0, tolerance_mm: float = 0.01):
        import shapely

        low, high = stock.bounds_min, stock.bounds_max
        self.z0, self.z1 = float(low[2]), float(high[2])
        self.thickness = self.z1 - self.z0
        self.sheet = shapely.box(low[0], low[1], high[0], high[1])
        self.tolerance = float(tolerance_mm)
        self.removed = shapely.Polygon()
        self.breaks: list = []
        self.part = part
        self._design = None
        #: What the operations meant to free: ``all`` (parts), ``outside`` (their outlines), ``holes`` (a die's
        #: openings; the plate is the part). From each op's meta ``sheet_cuts``.
        self.modes: set[str] = set()

    def supports(self, wcs) -> str | None:
        axis = wcs.tool_axis
        if abs(abs(axis[2]) - 1.0) < 1e-9:
            return None
        return (f"the sheet simulator cuts through the sheet's thickness only; setup '{wcs.setup_id}' does not look "
                "along Z, so its cuts are not simulated")

    def area(self) -> float:
        return float(self.sheet.difference(self.removed).area)

    def volume(self) -> float:
        return self.area() * self.thickness

    def cut(self, toolpath, tools: dict, wcs) -> SimReport:
        import shapely

        report = SimReport(setup=wcs.setup_id)
        reason = self.supports(wcs)
        if reason:
            report.skipped = reason
            return report
        for op in toolpath.ops:
            tool = tools.get(op.tool) if op.tool else None
            width = op.meta.get("kerf_mm")
            if width is None and tool is not None:
                width = tool.kerf_mm if tool.type == "beam" else tool.diameter_mm
            if not width or op.end <= op.start:
                continue
            runs = [wcs.from_wcs(run)[:, :2] for run in cutting_runs(toolpath.slice(op.start, op.end),
                                                                     tolerance=self.tolerance)]
            before = self.area()
            self.removed = shapely.union_all([self.removed, swept(runs, float(width))])
            report.removed_mm3_by_op[op.index] = (before - self.area()) * self.thickness
            self.modes.add(op.meta.get("sheet_cuts", "all"))
            self._design = None
            for x, y, r in op.meta.get("tab_breaks", ()):
                centre = wcs.from_wcs([[x, y, 0.0]])[0]
                self.breaks.append(shapely.Point(centre[0], centre[1]).buffer(r, quad_segs=8))
        return report

    def design(self, part=None):
        """What the sheet was cut for, in part XY: the parts (a DXF's profiles, or a plate's section halfway up);
        their outlines when only outsides were cut; the plate with its openings when only holes were."""
        if self._design is None:
            import shapely

            part = part or self.part
            if part is None:
                profiles = []
            elif part.kind == "dxf":
                profiles = list(part.profiles)
            else:
                import numpy as np

                from cadgen._internal.cam.geom2d import Sections, polygons_of

                vertices = np.asarray(part.vertices)
                mid = float((vertices[:, 2].min() + vertices[:, 2].max()) / 2.0)
                profiles = polygons_of(Sections(vertices, part.triangles).at(mid))
            if self.modes == {"outside"}:
                profiles = [shapely.Polygon(p.exterior) for p in profiles]
            elif self.modes == {"holes"}:
                openings = [shapely.Polygon(ring) for p in profiles for ring in p.interiors]
                plate = shapely.difference(self.sheet, shapely.union_all(openings)) if openings else self.sheet
                profiles = [plate]
            self._design = profiles
        return self._design

    def pieces(self, part=None) -> dict:
        """:func:`analyse` of the sheet now against the parts."""
        return analyse(self.sheet, self.removed, self.design(part), tolerance=self.tolerance, breaks=self.breaks)

    def material_left(self, part, *, stock_to_leave_mm: float, tolerance_mm: float) -> MaterialLeft | None:
        import numpy as np
        import shapely
        from shapely.ops import polylabel

        from cadgen._internal.cam.geom2d import polygons_of

        design = self.design(part)
        if not design or self.removed.is_empty:
            return None
        report = self.pieces(part)
        allowance = stock_to_leave_mm + max(0.05, tolerance_mm)
        spots = []
        for polygon, excess in zip(design, report["excess"]):
            for piece in polygons_of(excess):
                if piece.area < _NOISE_MM2:
                    continue
                # How far the leftover stands off the part: its vertices, and its middle (an uncut hole's
                # boundary is the part's own edge, its middle is not).
                coords = np.asarray(piece.exterior.coords)[:, :2]
                middle = polylabel(piece, max(tolerance_mm, 0.01))
                reach = float(max(shapely.distance(shapely.points(coords), polygon).max(),
                                  shapely.distance(middle, polygon)))
                if reach > allowance:
                    spots.append((piece, reach))
        if not spots:
            return MaterialLeft(0.0, 0.0, 0.0, None)
        area = float(sum(piece.area for piece, _ in spots))
        worst, reach = max(spots, key=lambda item: item[1])
        c = worst.representative_point()
        bounds = shapely.union_all([piece for piece, _ in spots]).bounds
        return MaterialLeft(volume_mm3=area * self.thickness, area_mm2=area, max_mm=reach,
                            at=(float(c.x), float(c.y), self.z1),
                            bounds_min=(bounds[0], bounds[1], self.z0), bounds_max=(bounds[2], bounds[3], self.z1))

    def mesh(self):
        from cadgen._internal.cam.geom2d import polygons_of

        return _extrude(polygons_of(self.sheet.difference(self.removed)), self.z0, self.z1)

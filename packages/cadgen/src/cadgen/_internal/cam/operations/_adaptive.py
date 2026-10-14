"""Adaptive clearing, shared by ``adaptive`` (2.5D) and ``adaptive_3d``: one level at a time, the tool's radial
engagement held to the stepover, and the tool kept where material stands.

An operation hands each level as ``area``, where the tool's centre may go at that height (in tool-centre space: the
region to clear shrunk by the radius, or kept a radius off the part), with the part's section there. The material is
the stock as it stands before the operation (:meth:`~cadgen._internal.cam.milling3d.StockNow.standing`, every earlier
operation and setup replayed, the part and its stock to leave taken out). Where the tool's circle touches none of it
the level is already clear (``air``); where it touches some is what the level cuts (``todo``). A level with nothing to
cut is skipped, and so is a connected piece of ``area`` with nothing in it.

How a piece is cleared (in tool-centre space):

* it starts from the air in it: the cleared area is first the positions where the tool touches nothing (beside the
  stock, over what an earlier operation or a shallower level already cut). Where a piece has no air, it is entered by a
  helix at its most open point (the centre of its largest inscribed circle; radius up to ``0.75`` of the tool radius at
  ``ramp_angle_deg``), or, where it is too narrow for that, a ramp along its outline (else a plunge, counted);
* it then grows the cleared area in steps of the stepover: each new boundary is the cleared area offset by the
  stepover and clipped to the piece, so no point of a new pass is more than one stepover from where the tool has
  already been, or from where it would touch nothing: that caps the radial engagement at the stepover, walls
  included. Only the stretches of each boundary that reach new material are cut (climb by default);
* the stretches are cut in dependency order, not step by step: one may go once every stretch of an earlier step
  within twice the tool's radius is cut (everything its tool circle can reach that an earlier step cleared is then
  cut), the nearest such one next, so the tool carries one side of a pocket on before it crosses to the other. Between
  stretches it feeds at depth through bands already cut whole, else lifts; a stretch that starts in the air is come
  down to straight, any other ramped into along itself, or come down to straight where the level is cut all round.

What the radius cannot reach goes to the ``corner_radius`` check as in a pocket; what is cut at full width (round a
piece too narrow for a helix) is counted in ``full_slot_mm``. :meth:`Clearing.finish` writes the facts, builds the
path and measures its air (:mod:`cadgen._internal.cam.air`).
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["Clearing", "check_stepover"]

#: An adaptive clear's stepover when the job gives none, as a share of the tool's diameter.
DEFAULT_STEPOVER = 0.15
#: How far a link through cleared space lifts off the floor (mm), never above the level above: the tool crosses
#: clear of the floor's last skin at the machine's top feed, not at the cutting feed (a micro-lift).
LINK_LIFT_MM = 0.2


def check_stepover(spec, tool) -> None:
    """Refuse a stepover past half the diameter: an adaptive clear's stepover is its engagement."""
    stepover = spec.stepover_mm if spec.stepover_mm is not None else (
        (spec.stepover if spec.stepover is not None else DEFAULT_STEPOVER) * tool.diameter_mm)
    if stepover > 0.5 * tool.diameter_mm + 1e-9:
        raise CamJobError(f"{spec.where}: an adaptive clear's stepover is its engagement; keep it at most half the "
                          f"tool's diameter ({0.5 * tool.diameter_mm:g} mm), 0.1 to 0.2 is usual")


def default_stepdown(ctx) -> float:
    """Twice the material's step down (deep and light, as adaptive clearing runs), within the flutes."""
    import math

    from cadgen._internal.cam.feeds import default_stepdown as material_stepdown

    if ctx.spec.stepdown_mm is not None:
        return float(ctx.spec.stepdown_mm)
    return min(ctx.tool.flute_length_mm or math.inf, 2.0 * material_stepdown(ctx.material, ctx.tool))


class Clearing:
    """One operation's adaptive clearing, level by level from the stock top down, on its own builder."""

    def __init__(self, ctx, *, feeds_kind: str, climb: bool, ramp_angle_deg: float):
        from cadgen._internal.cam.milling3d import StockNow, fine_cell

        self.ctx = ctx
        self.b = ctx.builder()
        self.stepover = ctx.stepover(DEFAULT_STEPOVER)
        self.feeds = ctx.feeds(feeds_kind, stepover_mm=self.stepover)
        self.climb = climb
        self.angle = ramp_angle_deg
        self.r = ctx.tool.radius
        self.tol = ctx.tolerance_mm
        self.heights = ctx.heights
        self.eps = max(3.0 * self.tol, 0.05 * self.stepover)
        machine = ctx.machine
        # A link crosses at the machine's top feed (its rapid rate where it gives none), never slower than the cut.
        self.link_feed = max(self.feeds.feed_mm_min, machine.max_feed_mm_min or machine.rapid_mm_min or 0.0)
        self.stock_now = StockNow(ctx, cell=fine_cell(self.r))
        # Where the level above left the tool free to come down from, and how high it was.
        self.z_prev = ctx.heights.stock_top
        self.previous_area = None
        self.entries = {"helix": 0, "ramp": 0, "plunge": 0, "air": 0}
        self.passes = self.narrow = self.levels = self.skipped = 0
        self.full_slot = 0.0
        self._cut_lines: list = []

    # --- a level -------------------------------------------------------------------------------------------------

    def level(self, area, z: float, *, part=None, leave: float = 0.0) -> None:
        """Clear ``area`` (tool-centre space) at ``z`` where stock stands, ``part`` (its section here) and ``leave``
        on it taken out; a level with nothing to cut is skipped."""
        import shapely

        from cadgen._internal.cam import geom2d, linking

        standing = self.stock_now.standing(z, part=part, leave=leave)
        reach = geom2d.offset(standing, self.r, tolerance=self.tol) if not standing.is_empty else standing
        todo = area.intersection(reach) if not reach.is_empty and not area.is_empty else shapely.Polygon()
        if todo.is_empty or todo.area < 1e-6:
            self.skipped += 1
        else:
            self.levels += 1
            air = area.difference(reach) if not reach.is_empty else area
            pieces = [piece for piece in geom2d.polygons_of(area) if piece.intersection(todo).area >= 1e-6]
            for piece in linking.order_nearest(pieces, self.b.pos, key=lambda p: (p.centroid.x, p.centroid.y)):
                self._clear(piece, air.intersection(piece), air, z)
                self.b.rapid(z=min(self.heights.retract, z + 1.0))
        self.previous_area = area
        self.z_prev = z

    def finish(self, meta: dict, *, nothing_left: str):
        """The toolpath, up at the clearance height, with its facts and air report written into ``meta``."""
        from cadgen._internal.cam.air import air_report

        self.b.rapid(z=self.heights.clearance)
        meta.update({"entries": {k: v for k, v in self.entries.items() if v}, "passes": self.passes,
                     "full_slot_mm": round(self.full_slot, 3), "levels": self.levels})
        if self.skipped:
            meta["levels_already_clear"] = self.skipped
        if self.entries["plunge"]:
            meta["plunges"] = self.entries["plunge"]
        if self.narrow:
            meta["note"] = (f"{self.narrow} piece(s) too narrow for a helix entry were ramped in along their outline at "
                            "full width")
        if not self.levels:
            meta["note"] = f"nothing left to clear: the stock as it stands is already clear down to {nothing_left}"
        path = self.b.build()
        meta.update(air_report(self.ctx, path, stock_now=self.stock_now))
        return path

    def _z_from(self, point) -> float:
        """Where the tool may come down to before it cuts at ``point``: the level above where it cut there, else the
        stock top."""
        import shapely

        above = self.previous_area is not None and self.previous_area.buffer(1e-6).contains(shapely.Point(point))
        return self.z_prev if above else self.heights.stock_top

    def _enter(self, paths, z_from: float, z: float) -> None:
        """Down from ``z_from`` to ``z`` by a ramp along the first of ``paths`` long enough, else straight (counted)."""
        from cadgen._internal.cam.operations._milling2d import ramp_along

        for path in paths:
            if ramp_along(self.b, path, z_from, z, angle_deg=self.angle, f=self.feeds.ramp_mm_min):
                self.entries["ramp"] += 1
                return
        self.b.feed(z=z_from, f=self.feeds.ramp_mm_min)
        self.b.plunge(z=z, f=self.feeds.plunge_mm_min)
        self.entries["plunge"] += 1

    def _clear(self, piece, seed, air, z: float) -> None:
        """Clear one connected piece at level ``z``, from the air in it (``seed``) or from an entry."""
        import numpy as np
        import shapely

        from cadgen._internal.cam import geom2d, linking
        from cadgen._internal.cam.operations._milling2d import rotate_to_nearest
        from cadgen._internal.cam.operations.pocket import _travel

        b, r, tol, feeds = self.b, self.r, self.tol, self.feeds
        self._cut_lines = []
        if not seed.is_empty and seed.area >= 1e-6:
            cleared = seed
        else:
            circle = shapely.maximum_inscribed_circle(piece, tolerance=max(tol, 0.01))
            coords = np.asarray(circle.coords)
            centre = (float(coords[0][0]), float(coords[0][1]))
            inscribed = float(np.hypot(*(coords[1] - coords[0]))) if len(coords) > 1 else 0.0
            helix_r = min(0.75 * r, 0.9 * inscribed)
            start = (centre[0] + helix_r, centre[1])
            z_from = self._z_from(start)
            if helix_r >= 0.1 * r:
                _travel(b, start, z_from, self.heights, None, None)
                linking.helix(b, centre, helix_r, z_from, z, angle_deg=self.angle, f=feeds.ramp_mm_min,
                              clockwise=not self.climb)
                self.entries["helix"] += 1
                circle = shapely.Point(centre).buffer(helix_r, quad_segs=geom2d.quad_segs(max(helix_r, tol), tol))
                self._cut_lines = [circle.exterior]
                cleared = circle.intersection(piece)
            else:
                self.narrow += 1
                ring = rotate_to_nearest(geom2d.rings(piece, climb=self.climb)[0], b.pos)
                _travel(b, (float(ring[0][0]), float(ring[0][1])), z_from, self.heights, None, None)
                self._enter([ring], z_from, z)
                b.polyline(np.column_stack([ring[1:], np.full(len(ring) - 1, z)]), f=feeds.feed_mm_min)
                # Round a piece too narrow for a helix the tool cuts its full width.
                self.full_slot += float(shapely.LineString(ring).length)
                cleared = piece.intersection(shapely.LineString(ring).buffer(min(self.stepover, r) * 0.5))
                self._cut_lines = [shapely.LineString(ring)]
        runs, bands = self._grow(piece, cleared)
        self._schedule(runs, bands, cleared, z, air.buffer(self.eps) if not air.is_empty else air)

    # --- growing the cleared area, then cutting it in a good order ---------------------------------------------------

    def _grow(self, piece, cleared):
        """Every stretch that clears ``piece`` from ``cleared``, step by step, and the new band of each step.

        Each stretch is a dict: ``kind``, ``points``, ``ring`` (its ring's points), ``step``, ``line`` and ``before``
        (the area cleared before its step). Each band is ``[polygon, stretches bordering it]``: the material a step
        clears between its stretches and the area cleared before it, cut once they all are."""
        import shapely

        from cadgen._internal.cam import geom2d

        tol = self.tol
        runs: list[dict] = []
        bands: list[list] = []
        for step in range(20000):
            grown = geom2d.offset(cleared, self.stepover, tolerance=tol).intersection(piece)
            grown = shapely.union_all([p for p in geom2d.polygons_of(grown) if p.intersects(cleared)])
            grown = grown.simplify(tol * 0.5).intersection(piece)
            new = grown.difference(cleared) if not grown.is_empty else grown
            if new.is_empty or new.area < 1e-3:
                break
            first = len(runs)
            for ring in geom2d.rings(grown, climb=self.climb):
                for kind, points, whole in self._new_runs(ring, cleared):
                    line = shapely.LineString(points) if len(points) > 1 else shapely.Point(points[0])
                    runs.append({"kind": kind, "points": points, "ring": whole, "step": step, "line": line,
                                 "before": cleared})
            for polygon in geom2d.polygons_of(new):
                members = {i for i in range(first, len(runs)) if runs[i]["line"].distance(polygon) <= self.eps}
                bands.append([polygon, members])
            # Bounded: the union keeps every near-coincident edge along the piece's boundary step after step.
            cleared = shapely.union_all([cleared, grown]).simplify(tol * 0.1)
        return runs, bands

    def _schedule(self, runs, bands, start, z: float, air) -> None:
        """Cut ``runs`` (from :meth:`_grow`), the nearest one the tool may cut next each time (see the module's
        docstring)."""
        import numpy as np
        import shapely

        if not runs:
            return
        reach = 2.0 * self.r + self.eps
        tree = shapely.STRtree([run["line"] for run in runs])
        waiting = [0] * len(runs)
        dependents: list[list[int]] = [[] for _ in runs]
        for i, run in enumerate(runs):
            for j in tree.query(run["line"], predicate="dwithin", distance=reach):
                if runs[int(j)]["step"] < run["step"]:
                    waiting[i] += 1
                    dependents[int(j)].append(i)
        of_run: list[list[int]] = [[] for _ in runs]
        left = []
        done = start
        for k, (polygon, members) in enumerate(bands):
            left.append(len(members))
            for i in members:
                of_run[i].append(k)
            if not members:
                done = shapely.union_all([done, polygon])
        ready = {i for i, count in enumerate(waiting) if count == 0}
        while ready:
            here = np.asarray(self.b.pos[:2])
            i = min(ready, key=lambda k: _distance_to_start(runs[k], here))
            ready.discard(i)
            run = runs[i]
            points = self._spiral(run["points"], run["before"]) if run["kind"] == "loop" else run["points"]
            self._cut(points, z, done, [bands[k][0] for k in of_run[i]], air, run["ring"])
            for k in of_run[i]:
                left[k] -= 1
                if left[k] == 0:
                    done = shapely.union_all([done, bands[k][0]])
            for j in dependents[i]:
                waiting[j] -= 1
                if waiting[j] == 0:
                    ready.add(j)

    # --- the stretches of a boundary that reach new material --------------------------------------------------------

    def _new_runs(self, ring, cleared) -> list:
        """The stretches of ``ring`` off ``cleared``, each ``(kind, points, the ring's points)``: ``"loop"`` for a
        ring wholly in new material (entered anywhere, by a spiral off the cleared edge), else ``"open"`` per stretch,
        widened by one point at either end so it starts and ends on cleared."""
        import numpy as np
        import shapely

        line = shapely.segmentize(shapely.LineString(ring), max(0.05, self.stepover / 2.0))
        points = np.asarray(line.coords)[:-1]
        if len(points) < 3:
            return []
        new = shapely.distance(shapely.points(points), cleared) > self.eps
        if not new.any():
            return []
        if new.all():
            return [("loop", points, points)]
        n = len(points)
        runs, current = [], []
        first = int(np.argmin(new))         # a cleared point to start the walk from
        order = np.roll(np.arange(n), -first)
        for index in order:
            if new[index]:
                if not current:
                    current.append((index - 1) % n)
                current.append(index)
            elif current:
                current.append(index)
                runs.append(("open", points[current], points))
                current = []
        if current:
            current.append(order[0])
            runs.append(("open", points[current], points))
        return runs

    def _spiral(self, points, cleared):
        """A ring wholly in new material (the first round an entry), started nearest the tool: spiral out onto it
        from the cleared edge over its first stretch, so the engagement grows from nothing, then once round it."""
        import numpy as np
        import shapely

        b = self.b
        k = int(np.argmin(np.hypot(points[:, 0] - b.pos[0], points[:, 1] - b.pos[1])))
        loop = np.vstack([points[k:], points[:k], points[k:k + 1]])
        along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(loop, axis=0).T))])
        stretch = min(along[-1] / 4.0, max(3.0 * self.stepover, along[-1] / 8.0))
        q = max(1, int(np.searchsorted(along, stretch)))
        edge = cleared.boundary
        spiral = []
        for i in range(q + 1):
            t = along[i] / along[q]
            on_edge = edge.interpolate(edge.project(shapely.Point(loop[i])))
            spiral.append((1.0 - t) * np.array([on_edge.x, on_edge.y]) + t * loop[i])
        return np.vstack([np.asarray(spiral), loop[q + 1:], loop[1:q + 1]])

    # --- getting there and cutting --------------------------------------------------------------------------------

    def _cut(self, run, z: float, done, own_bands, air, ring) -> None:
        """To the start of ``run`` and along it at ``z``. At depth the tool steps at most a stepover into its own
        band, or feeds through bands already cut whole (``done``); otherwise it comes back from the retract plane:
        straight down where the start is in the air, else ramped into along the stretch itself."""
        import math

        import numpy as np
        import shapely

        b, heights, feeds, r = self.b, self.heights, self.feeds, self.r
        target = (float(run[0][0]), float(run[0][1]))
        step = shapely.LineString([b.pos[:2], target])
        down = abs(b.pos[2] - z) < 1e-9
        if down and step.length <= 1.5 * self.stepover and _within(step, [done, *own_bands], 1e-6):
            # A step of at most a stepover into the new band (onto the first ring round an entry).
            b.feed(x=target[0], y=target[1], z=z, f=feeds.ramp_mm_min)
        elif down and (step.length < 1e-9 or _within(step, [done], self.eps + 1e-6)):
            lift = min(LINK_LIFT_MM, max(0.0, self.z_prev - z) / 2.0)
            run_in = lift / math.tan(math.radians(self.angle))
            if lift > 0.0 and step.length > max(2.0 * self.stepover, 2.0 * run_in):
                # Through cut bands: up off the floor, across at the top feed, and back down along the link's end no
                # steeper than the ramp, as the run's start meets the material.
                t = 1.0 - run_in / step.length
                b.feed(z=z + lift, f=feeds.feed_mm_min)
                b.feed(x=b.pos[0] + t * (target[0] - b.pos[0]), y=b.pos[1] + t * (target[1] - b.pos[1]), z=z + lift,
                       f=self.link_feed)
                b.feed(x=target[0], y=target[1], z=z, f=feeds.feed_mm_min)
            else:
                b.feed(x=target[0], y=target[1], z=z, f=feeds.feed_mm_min)
        else:
            b.rapid(z=heights.retract)
            b.rapid(x=target[0], y=target[1])
            point = shapely.Point(target)
            if not air.is_empty and air.contains(point):
                # Nothing stands round the tool here at this level, nor above it: straight down through air.
                if z + 1.0 < heights.retract:
                    b.rapid(z=z + 1.0)
                b.feed(z=z, f=feeds.plunge_mm_min)
                self.entries["air"] += 1
            else:
                z_from = self._z_from(target)
                if z_from + 1.0 < heights.retract:
                    b.rapid(z=z_from + 1.0)
                circle = point.buffer(r * 0.999, quad_segs=16)
                near = [line for line in self._cut_lines if line.distance(point) <= 2.0 * r]
                if near and circle.difference(shapely.union_all([line.buffer(r, quad_segs=16)
                                                                 for line in near])).area < 1e-3:
                    # This level is cut all round the tool there already: straight down through air.
                    b.feed(z=z, f=feeds.plunge_mm_min)
                else:
                    k = int(np.argmin(np.hypot(ring[:, 0] - target[0], ring[:, 1] - target[1])))
                    self._enter([run, np.vstack([[target], ring[k:], ring[:k + 1]])], z_from, z)
        b.polyline(np.column_stack([run[1:], np.full(len(run) - 1, z)]), f=feeds.feed_mm_min)
        self._cut_lines.append(shapely.LineString(run) if len(run) > 1 else shapely.Point(run[0]))
        self.passes += 1


def _within(line, regions, pad: float) -> bool:
    """Whether ``line`` lies within the union of ``regions`` grown by ``pad``: each is cut down to a box round the
    line first, so the growing is local, not the whole region's every time."""
    import shapely

    # The box grown from the line's bounds, never a zero-width box grown (a link straight along x or y has one).
    margin = 2.0 * pad + 1e-6
    x0, y0, x1, y1 = line.bounds
    box = shapely.box(x0 - margin, y0 - margin, x1 + margin, y1 + margin)
    local = shapely.union_all([region.intersection(box) for region in regions if not region.is_empty])
    return not local.is_empty and line.within(local.buffer(pad))


def _distance_to_start(run, here) -> float:
    """How far the tool is from where it would start ``run``: its first point, or a loop's nearest."""
    import numpy as np

    points = run["points"]
    if run["kind"] == "loop":
        return float(np.min(np.hypot(points[:, 0] - here[0], points[:, 1] - here[1])))
    return float(np.hypot(points[0][0] - here[0], points[0][1] - here[1]))

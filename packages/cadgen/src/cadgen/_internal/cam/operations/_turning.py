"""What every turning operation shares: the base class, the lathe's heights and the stock as it stands.

A turning operation works in the setup's WCS half-plane (x = radius, z axial, chuck side negative; shapely ``(x,
y)`` = ``(x, z)``) and emits IR moves with ``y = 0`` on a lathe toolpath. Its moves are the tool's controlled point
(:mod:`~cadgen._internal.cam.turn_profile`), so the path is nose-radius compensated and posts write it with G40.

:class:`Lathe` gathers, for one operation: the part's turned :class:`~cadgen._internal.cam.turn_profile.TurnProfile`,
the bar (radius, front and back in WCS), the safe heights (``z_clear``: the setup's clearance in front of the bar;
``x_clear``: the bar's radius plus the clearance; ``approach``: the setup's retract distance), the stock as it
stands before the operation (:meth:`Lathe.material`, the lathe simulator run over everything planned before it),
the forbidden region of a tool (:meth:`Lathe.forbidden`: the part grown by the reflected tool and an allowance, the
region the controlled point may not enter) and the feeds (constant surface speed and feed per revolution).

Every operation starts where the last one left the tool (in front of the bar at ``z_clear``), and ends at
``(x_clear, z_clear)``: it leaves the material radially first (out on the OD, in towards the axis in a bore), then
axially. Each one records its tool's role for the simulator and the gouge check in ``meta["lathe"]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cadgen._internal.cam.job_errors import CamJobError, choice, read_number
from cadgen._internal.cam.operations.base import Operation

__all__ = ["BIG", "Lathe", "TurnOperation", "lathe"]

BIG = 1e5
#: Keys every turning operation takes beyond the shared ones.
TURN_KEYS = ("css_m_min", "feed_mm_rev")
SIDES = ("od", "id")


class TurnOperation(Operation):
    family = "Turning"
    machines = ("lathe",)
    status = "full"
    #: The tool role(s) it cuts with (``turn_profile.tool_shape``).
    feeds_kind = "turn_rough"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        job, setup = ctx.job, ctx.setup
        where = spec.where
        stock = job.stock
        if stock.kind != "cylinder":
            raise CamJobError(f"{where}: a lathe turns bar stock; set stock to {{\"kind\": \"cylinder\", "
                              f"\"diameter_mm\": .., \"length_mm\": ..}}")
        orientation = setup.orientation
        if isinstance(orientation, str) and orientation[1].lower() != stock.axis:
            raise CamJobError(f"{where}: setup '{setup.id}' turns about the part's {orientation[1]} (orientation "
                              f"{orientation}) but the bar runs along {stock.axis}; set stock.axis to "
                              f"\"{orientation[1].lower()}\" or the orientation to +{stock.axis.upper()}")
        if setup.origin == "stock-top-corner":
            raise CamJobError(f"{where}: a lathe's work zero sits on the spindle axis; setup '{setup.id}' uses "
                              "origin stock-top-corner: use stock-top-center (or part-top-center on a round part)")
        if spec.tool is not None:
            tool = job.tool(spec.tool)
            if tool.type == "turn" and tool.side == "left":
                raise CamJobError(f"{where}: {tool.id} is a left-hand turning tool (it cuts towards the tailstock); "
                                  "this cadgen turns towards the chuck: use a right-hand or neutral tool")
        params = dict(params)
        params["css_m_min"] = read_number(spec.extra, "css_m_min", where)
        params["feed_mm_rev"] = read_number(spec.extra, "feed_mm_rev", where, maximum=5.0)
        return params

    @staticmethod
    def side(spec, default: str = "od") -> str:
        return choice(spec.extra.get("side", default), SIDES, f"{spec.where}.side")

    @staticmethod
    def flag(spec, key: str, default: bool) -> bool:
        value = spec.extra.get(key, default)
        if not isinstance(value, bool):
            raise CamJobError(f"{spec.where}.{key} must be true or false")
        return value

    @staticmethod
    def z_list(spec, key: str) -> tuple[float, ...]:
        raw = spec.extra.get(key)
        if raw is None:
            return ()
        values = raw if isinstance(raw, list) else [raw]
        out = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise CamJobError(f"{spec.where}.{key} must be a z position (WCS mm) or a list of them, not {raw!r}")
            out.append(float(value))
        return tuple(out)

    def summary(self, ctx, params) -> str:
        name = f" ({ctx.spec.name})" if ctx.spec.name else ""
        what = ctx.meta.get("what", "")
        tool = f" with {ctx.tool.id} {ctx.tool.plain}" if ctx.tool is not None else ""
        return f"{self.plain}{name}{(' ' + what) if what else ''}{tool}"


@dataclass
class Lathe:
    ctx: Any
    profile: Any
    bar_radius: float
    bar_front: float
    bar_back: float
    z_clear: float
    x_clear: float
    approach: float
    _material: Any = field(default=None, repr=False)

    # --- the stock as it stands ------------------------------------------------------------------------

    def material(self):
        """The bar's half-section before this operation, in this setup's WCS (shapely x = radius, y = z)."""
        if self._material is None:
            import shapely

            from cadgen._internal.cam.stock_lathe import LatheSim

            ctx = self.ctx
            sim = LatheSim(ctx.stock, ctx.part, tolerance_mm=ctx.tolerance_mm)
            tools = {tool.id: tool for tool in ctx.job.tools}
            for wcs, path in ctx.history:
                if sim.supports(wcs) is None:
                    sim.cut(path, tools, wcs)
            frame = sim._frame(ctx.wcs)
            s, c = frame
            # t = s z + c  ->  z = s (t - c)
            self._material = shapely.affinity.affine_transform(sim.material, [1.0, 0.0, 0.0, s, 0.0, -s * c])
        return self._material

    def front(self, x_low: float = 0.0, x_high: float = BIG) -> float | None:
        """The front (highest z) of the material between two radii, or None when there is none."""
        import shapely

        piece = shapely.intersection(self.material(), shapely.box(x_low, -BIG, x_high, BIG))
        if piece.is_empty or piece.area < 1e-9:
            return None
        return float(piece.bounds[3])

    def top(self, z_low: float = -BIG, z_high: float = BIG) -> float | None:
        """The largest radius of material between two heights."""
        import shapely

        piece = shapely.intersection(self.material(), shapely.box(0.0, z_low, BIG, z_high))
        if piece.is_empty or piece.area < 1e-9:
            return None
        return float(piece.bounds[2])

    def hole(self, z_low: float, z_high: float) -> float:
        """The radius of the free hole on the axis between two heights (0 when the material reaches the axis)."""
        import shapely

        piece = shapely.intersection(self.material(), shapely.box(0.0, z_low, BIG, z_high))
        if piece.is_empty or piece.area < 1e-9:
            return BIG
        return float(piece.bounds[0])

    # --- the part ----------------------------------------------------------------------------------------

    def target(self, *, beyond: float):
        """The part's turned section, its back end carried ``beyond`` mm further back (so the tool clears the
        part-off line), and the bar behind that (towards the chuck): what no tool may cut."""
        import shapely

        p = self.profile
        z_back = p.z_back
        outer = float(p.r_out(z_back + 1e-6)[0])
        inner = float(p.r_in(z_back + 1e-6)[0])
        pieces = [p.region, shapely.box(0.0, -BIG, BIG, z_back - beyond)]
        if beyond > 0:
            pieces.append(shapely.box(inner, z_back - beyond, outer, z_back + 1e-6))
        return shapely.union_all(pieces)

    def forbidden(self, target, shapes, *, allowance_x: float = 0.0, allowance_z: float = 0.0):
        """Where the controlled point may not go: ``target`` grown by an elliptical allowance and the reflected
        tool."""
        import numpy as np
        import shapely

        from cadgen._internal.cam.turn_profile import minkowski

        if allowance_x > 0 or allowance_z > 0:
            angles = np.linspace(0.0, 2 * math.pi, 24, endpoint=False)
            allow = np.column_stack([allowance_x * np.cos(angles), allowance_z * np.sin(angles)])
        else:
            allow = np.zeros((1, 2))
        combined = []
        for shape in shapes:
            points = (allow[:, None, :] - np.asarray(shape)[None, :, :]).reshape(-1, 2)
            hull = shapely.MultiPoint(points).convex_hull
            combined.append(np.asarray(hull.exterior.coords)[:-1] if hull.geom_type == "Polygon" else points)
        return minkowski(target, combined)

    # --- feeds -------------------------------------------------------------------------------------------

    def feeds(self, kind: str, diameter: float, params: dict, *, pitch_mm: float | None = None):
        from cadgen._internal.cam.feeds import for_turn

        ctx = self.ctx
        chosen = for_turn(ctx.material, ctx.tool, kind, ctx.machine, diameter_mm=diameter, feed=ctx.spec.feed,
                          speed=ctx.spec.speed, feed_mm_rev=params.get("feed_mm_rev"),
                          css_m_min=params.get("css_m_min"), pitch_mm=pitch_mm)
        ctx.chosen_feeds.append(chosen)
        return chosen

    # --- moves -------------------------------------------------------------------------------------------

    def builder(self):
        from cadgen._internal.cam.ir import ToolpathBuilder

        ctx = self.ctx
        start = ctx.start
        return ToolpathBuilder((float(start[0]), 0.0, float(start[2])), op=ctx.index, lathe=True)

    def begin(self, b) -> None:
        """From wherever the last operation left the tool: out in front of the bar."""
        if b.pos[2] < self.z_clear - 1e-9:
            b.rapid(z=self.z_clear)

    def home(self, b) -> None:
        """Out in front of the bar, then out past its radius: ``(x_clear, z_clear)``. The tool must already be clear
        of material radially."""
        b.rapid(z=self.z_clear)
        b.rapid(x=self.x_clear)


def lathe(ctx) -> Lathe:
    from cadgen._internal.cam.turn_profile import bar_in_wcs, check_coaxial, read_profile

    check_coaxial(ctx.stock, ctx.wcs, ctx.spec.where)
    profile = read_profile(ctx.part, ctx.wcs, tolerance_mm=ctx.tolerance_mm, where=ctx.spec.where)
    radius, front, back = bar_in_wcs(ctx.stock, ctx.wcs)
    # The off-axis note once per setup: on its first operation.
    first = not any(path.ops and path.ops[0].setup == ctx.setup.id for _, path in ctx.history)
    if profile.note and first:
        ctx.meta["note"] = profile.note
    return Lathe(ctx=ctx, profile=profile, bar_radius=radius, bar_front=front, bar_back=back,
                 z_clear=float(ctx.heights.clearance), x_clear=radius + ctx.setup.clearance_mm,
                 approach=float(ctx.setup.retract_mm))


def note(ctx, text: str) -> None:
    """Add a sentence to the operation's note (the run prints it as a warning)."""
    ctx.meta["note"] = f"{ctx.meta['note']}; {text}" if ctx.meta.get("note") else text


# --- paths in the half-plane ---------------------------------------------------------------------------

def first_hit(forbidden, x: float, z_from: float) -> float:
    """Going towards the chuck from ``z_from`` at radius ``x``: the highest z where the controlled point would enter
    ``forbidden`` (``z_from`` itself when it starts inside, -BIG when it never does)."""
    import shapely

    hit = shapely.intersection(shapely.LineString([(x, z_from), (x, -BIG)]), forbidden)
    if hit.is_empty:
        return -BIG
    return float(hit.bounds[3])


def profile_path(forbidden, *, side: str, z_high: float, z_low: float, keep, tolerance: float):
    """The controlled point's path along the edge of ``forbidden`` (its OD for ``side`` od, its bore for id) from
    ``z_high`` down to ``z_low``: the first unbroken run of points ``keep(x, z)`` accepts, simplified within
    ``tolerance``. An (N, 2) array of (x, z); empty when nothing is left."""
    import numpy as np

    from cadgen._internal.cam.turn_profile import envelope, simplify_path

    curve = envelope(forbidden, side="max" if side == "od" else "min", z_low=z_low, z_high=z_high)
    out = []
    for x, z in curve:
        if not math.isfinite(x) or not keep(x, z):
            if out and math.isfinite(x):
                # Run on along the last straight piece as far as it is still kept.
                (xa, za), good, bad = out[-1], 0.0, 1.0
                for _ in range(30):
                    mid = (good + bad) / 2.0
                    if keep(xa + mid * (x - xa), za + mid * (z - za)):
                        good = mid
                    else:
                        bad = mid
                if good > 1e-6:
                    out.append((xa + good * (x - xa), za + good * (z - za)))
            if out:
                break
            continue
        out.append((float(x), float(z)))
    if len(out) < 2:
        return np.zeros((0, 2))
    return simplify_path(np.asarray(out), tolerance)


def monotonic(path, side: str) -> bool:
    """Whether a profile only ever goes back (towards the chuck) and out (od) or in (id): what a G71 accepts."""
    import numpy as np

    if len(path) < 2:
        return False
    dx, dz = np.diff(path[:, 0]), np.diff(path[:, 1])
    out = dx >= -1e-6 if side == "od" else dx <= 1e-6
    return bool(np.all(dz <= 1e-6) and np.all(out))


def feed_path(b, path, f: float) -> None:
    for x, z in path:
        b.feed(x=float(x), z=float(z), f=f)


def unreached(lt, path, shapes, *, side: str, allowance: float) -> list:
    """The pieces of material between the bar's profile and the part that a tool following ``path`` (with
    everything outward of it, od, or inward of it, id, already cut) leaves: grooves and undercuts it cannot reach.
    A list of shapely polygons over 0.05 mm²."""
    import shapely

    from cadgen._internal.cam.turn_profile import sweep

    p = lt.profile
    if len(path) < 2:
        return []
    (x0, _), (x1, z1) = path[0], path[-1]
    import numpy as np

    under = shapely.make_valid(shapely.Polygon([(0.0, p.z_front), *map(tuple, np.nan_to_num(p.od)), (0.0, p.z_back)]))
    if side == "od":
        ring = [(x0, BIG), *map(tuple, path), (BIG, z1), (BIG, BIG)]
        candidates = shapely.difference(shapely.box(0.0, p.z_back, p.r_max, p.z_front), under)
    else:
        ring = [(0.0, BIG), (x0, BIG), *map(tuple, path), (x1, z1), (0.0, z1)]
        candidates = shapely.make_valid(shapely.Polygon([(0.0, p.z_front), *map(tuple, np.nan_to_num(p.bore)),
                                                         (0.0, p.z_back)]))
    cut = shapely.union(shapely.make_valid(shapely.Polygon(ring)), sweep(path, shapes))
    left = shapely.difference(shapely.difference(candidates, p.region.buffer(allowance + 0.05)), cut.buffer(0.05))
    return [g for g in shapely.get_parts(left) if g.area > 0.05]


def swept_by(toolpath, shapes):
    """The region a toolpath's cutting moves sweep with a tool of ``shapes`` (WCS half-plane), rapids left out."""
    import numpy as np
    import shapely

    from cadgen._internal.cam.ir import DWELL, RAPID
    from cadgen._internal.cam.turn_profile import sweep

    if not len(toolpath.moves):
        return shapely.Polygon()
    positions = toolpath.positions()[:, [0, 2]]
    kinds = toolpath.moves["kind"]
    pieces, run = [], []
    for i, kind in enumerate(kinds):
        if kind == DWELL:
            continue
        if kind == RAPID:
            if len(run) > 1:
                pieces.append(sweep(np.asarray(run), shapes))
            run = []
            continue
        if not run:
            run = [positions[i]]
        run.append(positions[i + 1])
    if len(run) > 1:
        pieces.append(sweep(np.asarray(run), shapes))
    return shapely.union_all(pieces) if pieces else shapely.Polygon()


def levels(forbidden, *, start: float, far: float, doc: float, z_start: float, front: float,
           clip: float = 1.0) -> list[float]:
    """Roughing pass radii from the stock's edge ``start`` towards ``far`` (the axis for an outside rough, the bore's
    widest for a bore), ``doc`` apart, the last as close to the part as a pass can still run in from the front
    (further than ``clip`` past it: a pass that only clips the part's front corner is not one)."""
    sign = 1.0 if far > start else -1.0

    def passable(x: float) -> bool:
        return first_hit(forbidden, x, z_start) < front - clip

    if not passable(start + sign * 1e-3):
        return []
    low, high = start + sign * 1e-3, far
    if passable(high):
        limit = high
    else:
        for _ in range(48):
            mid = (low + high) / 2.0
            if passable(mid):
                low = mid
            else:
                high = mid
        limit = low
    out = []
    x = start
    while True:
        x += sign * doc
        if sign * (x - limit) >= -1e-9:
            break
        out.append(x)
    if not out or abs(out[-1] - limit) > 0.02:
        out.append(limit)
    return out

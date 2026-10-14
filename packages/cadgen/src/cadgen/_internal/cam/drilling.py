"""What the ``drill`` operation plans with: holes read in a setup's WCS, their order, tool tips and threads.

* :class:`Hole`: one hole to drill, in WCS mm: its centre ``x, y``, its ``top`` (where the hole opens on the part:
  the top of its counterbore or countersink), its ``bottom`` (a blind hole's floor, a through hole's exit; ``None``
  for a point the job gave), its diameter (``None`` for a point), whether it goes through, the length of the drill
  point its model draws below its floor (``point_mm``, 0 for a flat floor), its countersink's diameter, and its
  counterbore's diameter and depth with the end it opens at in this setup (``counterbore_far``: at the hole's
  bottom, a back counterbore of a through hole; else at its top, the end the tool comes in by).
* :func:`holes_from_faces`, :func:`holes_matching` and :func:`holes_from_points` resolve an operation's ``faces``,
  ``holes`` filter or ``points``. A face hole whose axis is not the setup's Z is refused in one sentence that names
  the setup (or the orientation) that would reach it; one along it whose opening the part covers from this side
  (a hole in the floor of a cave) is a :class:`~cadgen._internal.cam.job_errors.PlanError` ``unreachable``, and
  ``holes`` leaves such holes out and counts them.
* :func:`tip_length`: how far a tool's point reaches below its full diameter (a drill's 118° point, a spot drill's
  cone, a tap's lead).
* :func:`order_shortest`: nearest neighbour, then 2-opt, an open path from a fixed start.
* :data:`METRIC_THREADS` and :func:`thread_for_hole`: ISO metric threads (coarse and fine pitches) and the hole
  sizes they are drawn at (the tap drill, ``D - P``, or the nominal size for a drawn-to-size thread).

Stdlib at import; numpy and shapely inside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.cam.job_errors import CamJobError, PlanError

__all__ = ["Hole", "MAX_TWO_OPT", "METRIC_THREADS", "holes_from_faces", "holes_from_points", "holes_matching",
           "order_shortest", "path_length", "spot_depth", "tap_problems", "thread_for_hole", "tip_length", "top_at"]

#: ISO metric threads: nominal diameter -> (coarse pitch, fine pitches).
METRIC_THREADS: dict[float, tuple[float, tuple[float, ...]]] = {
    1.6: (0.35, ()), 2.0: (0.4, ()), 2.5: (0.45, ()), 3.0: (0.5, ()), 3.5: (0.6, ()), 4.0: (0.7, ()),
    5.0: (0.8, ()), 6.0: (1.0, (0.75,)), 8.0: (1.25, (1.0, 0.75)), 10.0: (1.5, (1.25, 1.0, 0.75)),
    12.0: (1.75, (1.5, 1.25, 1.0)), 14.0: (2.0, (1.5, 1.25)), 16.0: (2.0, (1.5,)), 18.0: (2.5, (2.0, 1.5)),
    20.0: (2.5, (2.0, 1.5)), 22.0: (2.5, (2.0, 1.5)), 24.0: (3.0, (2.0, 1.5)), 27.0: (3.0, (2.0,)),
    30.0: (3.5, (2.0,)),
}
#: Past this many holes the order is nearest-first only (2-opt is quadratic per pass).
MAX_TWO_OPT = 3000
#: How far an axis may lean off the setup's Z and still be drilled from it (cosine of 0.1°).
_ALIGNED = math.cos(math.radians(0.1))


@dataclass(frozen=True)
class Hole:
    x: float
    y: float
    top: float
    bottom: float | None
    diameter: float | None
    through: bool = False
    #: How far the drill point the model draws reaches below ``bottom`` (0: a flat floor, or not blind).
    point_mm: float = 0.0
    #: The countersink's diameter at the opening, when the hole has one.
    countersink: float | None = None
    #: The counterbore's diameter and depth, when the hole has one, and whether it opens at the hole's bottom in this
    #: setup (a back counterbore on the far side of a through hole) rather than at its top.
    counterbore: float | None = None
    counterbore_depth: float | None = None
    counterbore_far: bool = False
    faces: tuple[str, ...] = ()
    label: str = ""

    @property
    def depth(self) -> float | None:
        return None if self.bottom is None else self.top - self.bottom

    @property
    def point_drawn(self) -> bool:
        return self.point_mm > 0.0

    @property
    def deepest(self) -> float | None:
        """The lowest point of a blind hole (its drawn point's tip, else its floor); None for a through hole or a
        point."""
        return None if self.bottom is None or self.through else self.bottom - self.point_mm


def _g(value: float) -> str:
    return f"{round(float(value), 3):g}"


def _word(vector) -> str:
    from cadgen._internal.cam.features import axis_word

    return axis_word(vector) or "(" + ", ".join(f"{v:.2f}" for v in vector) + ")"


def _setup_axis(setup):
    from cadgen._internal.cam.wcs import rotation_for

    return rotation_for(setup.orientation)[2]


def _in_setup(ctx, hole: dict) -> tuple[Hole | None, bool]:
    """The hole in the setup's WCS, or None when its axis is not the setup's Z (or a through hole's -Z); and whether
    the end it is drilled from is reached (nothing of the part covers it along the axis)."""
    from cadgen._internal.cam.features import direction_word

    wcs = ctx.wcs
    axis = wcs.vectors_to_wcs([hole["axis"]])[0]
    opening, bottom = wcs.to_wcs([hole["center_mm"], hole["bottom_mm"]])
    if axis[2] >= _ALIGNED:
        top_point, low_point = opening, bottom
        way = hole["axis"]
    elif hole["through"] and axis[2] <= -_ALIGNED:
        top_point, low_point = bottom, opening
        way = [-v for v in hole["axis"]]
    else:
        return None, False
    reached = direction_word(way) in hole.get("reach", ())
    sink = hole.get("countersink")
    bore = hole.get("counterbore")
    far = bore is not None and _counterbore_far(ctx, hole, float(top_point[2]), float(low_point[2]))
    return Hole(x=float(top_point[0]), y=float(top_point[1]), top=float(top_point[2]), bottom=float(low_point[2]),
                diameter=float(hole["diameter_mm"]), through=bool(hole["through"]),
                point_mm=float(hole.get("point_mm", 0.0)), countersink=float(sink["diameter_mm"]) if sink else None,
                counterbore=float(bore["diameter_mm"]) if bore else None,
                counterbore_depth=float(bore["depth_mm"]) if bore else None, counterbore_far=far,
                faces=tuple(hole["faces"]),
                label=hole["faces"][0] if hole["faces"] else f"({_g(top_point[0])}, {_g(top_point[1])})"), reached


def _counterbore_far(ctx, hole: dict, top: float, bottom: float) -> bool:
    """Whether a hole's counterbore opens at its bottom in this setup (WCS z ``top`` over ``bottom``): its wall (the
    hole's face of the counterbore's diameter) sits in the lower half of the hole. A blind hole's counterbore is at its
    opening, always."""
    if not hole["through"]:
        return False
    radius = float(hole["counterbore"]["diameter_mm"]) / 2.0
    for ref in hole["faces"]:
        info = ctx.part.face(ref)
        if info.surface == "cylinder" and info.radius_mm is not None and abs(float(info.radius_mm) - radius) < 1e-3:
            z = float(ctx.wcs.to_wcs([info.center_mm])[0][2])
            return z < (top + bottom) / 2.0
    return False


def _covered_sentence(ctx, hole: dict) -> str:
    """Why a hole along the setup's Z cannot be drilled from it: the part covers its opening; and what would."""
    import numpy as np

    from cadgen._internal.cam.features import direction_word

    axis = np.asarray(hole["axis"], dtype=float)
    ways = [axis] + ([-axis] if hole["through"] else [])
    reached = [way for way in ways if direction_word(way) in hole.get("reach", ())]
    kind = "through" if hole["through"] else "blind"
    head = (f"is a Ø{_g(hole['diameter_mm'])} x {_g(hole['depth_mm'])} {kind} hole whose opening the part covers "
            f"along setup '{ctx.setup.id}''s Z: the tool would come down through the part to reach it")
    for setup in ctx.job.setups:
        if setup.id == ctx.setup.id:
            continue
        tool_axis = np.asarray(_setup_axis(setup), dtype=float)
        if any(float(tool_axis @ way) >= _ALIGNED for way in reached):
            return f"{head}; drill it in setup '{setup.id}', whose tool comes from {_word(tool_axis)}"
    if reached:
        return f"{head}; add a setup with \"orientation\": \"{direction_word(reached[0])}\" for it"
    return f"{head}; nothing reaches it along its axis, so mill or drill it before the part over it is there"


def _reach_sentence(ctx, hole: dict) -> str:
    """Which setup would drill ``hole``: one of the job's, else the orientation to add."""
    import numpy as np

    axis = np.asarray(hole["axis"], dtype=float)
    ways = [axis] + ([-axis] if hole["through"] else [])
    for setup in ctx.job.setups:
        if setup.id == ctx.setup.id:
            continue
        tool_axis = np.asarray(_setup_axis(setup), dtype=float)
        if any(float(tool_axis @ way) >= _ALIGNED for way in ways):
            return f"drill it in setup '{setup.id}', whose tool comes from {_word(tool_axis)}"
    words = [_word(way) for way in ways]
    if all(word.startswith(("+", "-")) for word in words):
        return "add a setup with \"orientation\": " + " or ".join(f"\"{word}\"" for word in words) + " for it"
    return f"add a setup tilted (\"orientation\": {{\"a_deg\": .., \"c_deg\": ..}}) so its +Z runs along {words[0]}"


def _own_axis(ctx) -> str:
    orientation = ctx.setup.orientation
    return orientation if isinstance(orientation, str) else _word(ctx.wcs.tool_axis)


def _part_holes(ctx) -> list[dict]:
    from cadgen._internal.cam.features import holes

    # features.holes() asks OCCT's classifier about every hole: once per part, however many drill ops ask.
    cache = getattr(ctx.part, "_drill_holes", None)
    if cache is None:
        cache = holes(ctx.part)
        ctx.part._drill_holes = cache
    return cache


def holes_from_faces(ctx, refs, where: str) -> list[Hole]:
    """The holes whose walls ``refs`` name (two halves of one hole are one hole), in the order first named."""
    found: list[Hole] = []
    seen: set[int] = set()
    holes = _part_holes(ctx)
    for ref in refs:
        info = ctx.part.face(ref, where=f"{where}.faces")
        # Any face of a hole names it: its walls, its counterbore's wall and shoulder, its countersink, its floor.
        index = next((k for k, hole in enumerate(holes) if info.ref in hole["faces"]), None)
        if index is None:
            what = ("a round outside wall" if info.surface == "cylinder" and not info.hole
                    else f"a {info.surface}" if info.surface != "cylinder" else "a round wall that is no hole")
            raise CamJobError(f"{where}.faces: {ref} is {what}, not a hole wall; a drill names the walls of its holes "
                              "(cadgen cam features lists them under holes), or use \"holes\": \"all\"")
        if index in seen:
            continue
        seen.add(index)
        hole = holes[index]
        placed, reached = _in_setup(ctx, hole)
        if placed is None:
            kind = "through" if hole["through"] else "blind"
            raise CamJobError(
                f"{where}.faces: {ref} is a Ø{_g(hole['diameter_mm'])} x {_g(hole['depth_mm'])} {kind} hole along "
                f"{hole['axis_word']}, but setup '{ctx.setup.id}' drills along {_own_axis(ctx)}; "
                + _reach_sentence(ctx, hole))
        if not reached:
            raise PlanError("unreachable", f"{where}.faces: {ref} {_covered_sentence(ctx, hole)}")
        found.append(placed)
    return found


def holes_matching(ctx, selector, where: str) -> tuple[list[Hole], int, int]:
    """The part's holes this setup can drill that pass ``selector`` (``"all"`` or ``{"diameter_mm", "tolerance_mm"}``),
    how many matching holes run along another axis (left for another setup), and how many run along this one but
    open under the part (covered: left out, since a tool would come down through the part)."""
    holes = _part_holes(ctx)
    diameter = tolerance = None
    if isinstance(selector, dict):
        diameter, tolerance = selector["diameter_mm"], selector["tolerance_mm"]
    found, elsewhere, covered = [], 0, 0
    for hole in holes:
        if diameter is not None and abs(hole["diameter_mm"] - diameter) > tolerance + 1e-9:
            continue
        placed, reached = _in_setup(ctx, hole)
        if placed is None:
            elsewhere += 1
        elif not reached:
            covered += 1
        else:
            found.append(placed)
    if not found and covered:
        want = "hole" if diameter is None else f"Ø{_g(diameter)} ±{_g(tolerance)} hole"
        raise PlanError("unreachable", f"{where}.holes: every {want} along setup '{ctx.setup.id}''s Z "
                        f"({_own_axis(ctx)}) opens under the part ({covered} of them), so no tool reaches one from "
                        "this setup")
    if not found:
        sizes = sorted({(round(h["diameter_mm"], 3), h["axis_word"]) for h in holes})
        listing = ", ".join(f"Ø{_g(d)} along {w}" for d, w in sizes) or "none"
        want = "no hole" if diameter is None else f"no Ø{_g(diameter)} ±{_g(tolerance)} hole"
        raise CamJobError(f"{where}.holes: {want} runs along setup '{ctx.setup.id}''s Z ({_own_axis(ctx)}); the part's "
                          f"holes are {listing}")
    return found, elsewhere, covered


def top_at(ctx, x: float, y: float, radius: float) -> float | None:
    """The part's highest point over a disk of ``radius`` about (x, y), WCS; None when the part is not there."""
    import numpy as np

    vertices, triangles = ctx.mesh
    vertices = np.asarray(vertices)
    near = np.hypot(vertices[:, 0] - x, vertices[:, 1] - y) <= radius + 1e-6
    best = float(vertices[near, 2].max()) if near.any() else -math.inf
    tri = vertices[np.asarray(triangles)]
    lo, hi = tri[:, :, :2].min(axis=1), tri[:, :, :2].max(axis=1)
    candidates = np.nonzero((lo[:, 0] <= x) & (hi[:, 0] >= x) & (lo[:, 1] <= y) & (hi[:, 1] >= y))[0]
    for t in candidates:
        a, b, c = tri[t]
        det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(det) < 1e-12:
            continue
        w1 = ((x - a[0]) * (c[1] - a[1]) - (y - a[1]) * (c[0] - a[0])) / det
        w2 = ((b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])) / det
        if w1 >= -1e-9 and w2 >= -1e-9 and w1 + w2 <= 1 + 1e-9:
            best = max(best, float(a[2] + w1 * (b[2] - a[2]) + w2 * (c[2] - a[2])))
    return None if best == -math.inf else best


def holes_from_points(ctx, points, top_z: float | None) -> list[Hole]:
    """Holes at the job's ``points`` (WCS x, y): their top is ``top_z``, else the part's top there, else the stock's."""
    out = []
    for x, y in points:
        top = top_z
        if top is None:
            top = top_at(ctx, x, y, ctx.tool.radius)
            if top is None:
                top = ctx.heights.stock_top
        out.append(Hole(x=float(x), y=float(y), top=float(top), bottom=None, diameter=None,
                        label=f"({_g(x)}, {_g(y)})"))
    return out


def tip_length(tool) -> float:
    """How far below its full diameter the tool's point reaches: a drill's or a spot drill's cone, a chamfer mill's
    cone below its widest point, a tap's lead (three pitches, a plug tap); 0 for flat-ended tools."""
    if tool.type == "drill":
        return tool.radius / math.tan(math.radians(tool.point_angle / 2.0))
    if tool.type in ("spot", "chamfer"):
        angle = tool.angle_deg or 90.0
        return max(0.0, tool.radius - tool.tip_diameter_mm / 2.0) / math.tan(math.radians(angle / 2.0))
    if tool.type == "tap":
        return 3.0 * tool.pitch_mm
    return 0.0


def spot_depth(tool, diameter: float) -> float:
    """How deep a pointed tool goes for its cone to be ``diameter`` wide at the top."""
    if tool.type == "drill":
        half = math.radians(tool.point_angle / 2.0)
        tip = 0.0
    else:
        half = math.radians((tool.angle_deg or 90.0) / 2.0)
        tip = tool.tip_diameter_mm / 2.0
    return max(0.0, diameter / 2.0 - tip) / math.tan(half)


def path_length(start, points) -> float:
    import numpy as np

    pts = np.vstack([np.asarray(start, dtype=float)[None, :2], np.asarray(points, dtype=float)[:, :2]])
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


def order_shortest(points, start, *, max_two_opt: int = MAX_TWO_OPT,
                   max_passes: int = 60) -> tuple[list[int], bool]:
    """An order to visit ``points`` ((N, 2)) from ``start`` (x, y): nearest neighbour, then 2-opt on the open path
    (the start fixed, the end free). Returns ``(order, improved by 2-opt)``; past ``max_two_opt`` points it keeps
    the nearest-neighbour order."""
    import numpy as np

    pts = np.asarray(points, dtype=float)[:, :2]
    n = len(pts)
    if n <= 1:
        return list(range(n)), False
    here = np.asarray(start, dtype=float)[:2]
    left = np.ones(n, dtype=bool)
    order = []
    for _ in range(n):
        distance = np.where(left, np.hypot(pts[:, 0] - here[0], pts[:, 1] - here[1]), np.inf)
        k = int(np.argmin(distance))
        order.append(k)
        left[k] = False
        here = pts[k]
    if n < 3 or n > max_two_opt:
        return order, False
    route = np.vstack([np.asarray(start, dtype=float)[None, :2], pts[order]])
    index = np.array([-1] + order)
    improved = False
    for _ in range(max_passes):
        changed = False
        m = len(route)
        for i in range(1, m - 1):
            # Reverse route[i..j]: edges (i-1, i) and (j, j+1) become (i-1, j) and (i, j+1); j+1 past the end is free.
            j = np.arange(i + 1, m)
            a, b = route[i - 1], route[i]
            c = route[j]
            d_old = np.hypot(*(a - b)) + np.where(j + 1 < m, np.hypot(*(c - route[np.minimum(j + 1, m - 1)]).T), 0.0)
            d_new = np.hypot(*(a - c).T) + np.where(j + 1 < m, np.hypot(*(b - route[np.minimum(j + 1, m - 1)]).T), 0.0)
            gain = d_old - d_new
            k = int(np.argmax(gain))
            if gain[k] > 1e-9:
                jj = int(j[k])
                route[i:jj + 1] = route[i:jj + 1][::-1].copy()
                index[i:jj + 1] = index[i:jj + 1][::-1].copy()
                changed = improved = True
        if not changed:
            break
    return [int(v) for v in index[1:]], improved


def thread_for_hole(diameter: float) -> list[str]:
    """The metric threads a hole of ``diameter`` is drawn for: at the tap drill (``D - P``) or at the nominal size."""
    out = []
    for nominal, (coarse, fine) in METRIC_THREADS.items():
        for pitch in (coarse, *fine):
            if abs(diameter - (nominal - pitch)) <= 0.05:
                out.append(f"M{_g(nominal)}x{_g(pitch)} (tap drill)")
        if abs(diameter - nominal) <= 0.05:
            out.append(f"M{_g(nominal)} (drawn at the thread size)")
    return out


def tap_problems(tool, hole_diameter: float | None) -> list[str]:
    """Plain sentences for what is wrong with ``tool`` (a tap) for its hole, or ``[]``."""
    out = []
    nominal, pitch = tool.diameter_mm, tool.pitch_mm
    standard = METRIC_THREADS.get(round(nominal, 3))
    if standard is not None and not any(abs(pitch - p) < 1e-6 for p in (standard[0], *standard[1])):
        pitches = " or ".join(_g(p) for p in (standard[0], *standard[1]))
        out.append(f"M{_g(nominal)} threads have a pitch of {pitches}, but {tool.id} is a {_g(pitch)} mm pitch tap")
    if hole_diameter is not None:
        drill = nominal - pitch
        if abs(hole_diameter - drill) > max(0.1, 0.1 * pitch) + 1e-9 and abs(hole_diameter - nominal) > 0.05:
            looks = thread_for_hole(hole_diameter)
            like = f" (Ø{_g(hole_diameter)} is drawn for {looks[0]})" if looks else ""
            out.append(f"{tool.id} ({tool.plain}) needs a Ø{_g(drill)} tap-drill hole (or one drawn at "
                       f"Ø{_g(nominal)}, the thread size), but this hole is Ø{_g(hole_diameter)}{like}")
    return out

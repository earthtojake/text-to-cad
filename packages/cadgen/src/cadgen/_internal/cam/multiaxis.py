"""Multi-axis kinematics: rotary positions, tool axes, and the IR contract for moves that carry A, B, C.

**The rotary convention.** A setup's 3+2 orientation ``{"a_deg", "b_deg", "c_deg"}`` and every move's ``a b c``
columns are rotations of the part (on the table) in machine coordinates, right-handed, in degrees:
``R(a, b, c) = Rx(a) · Ry(b) · Rz(c)`` (C about Z first, then B about Y, then A about X) maps part directions to
machine directions, and the tool always points along machine +Z. So the tool axis, written in part coordinates, is
``R(abc)^T · ẑ``: ``(sin a sin c, sin a cos c, cos a)`` on an A+C trunnion, ``(-sin b cos c, sin b sin c, cos b)``
on a B+C head, ``(0, sin a, cos a)`` on a 4th axis. A post whose machine turns the other way negates the angles.

**Which axes a machine has** (:func:`rotary_axes`): a ``mill4`` turns A (about X); a ``mill5`` with kinematics
``ac_trunnion`` (the default) tilts A and turns C; ``bc_head`` tilts B and turns C. ``machine.rotary_limits_deg``
(``{"a": [-120, 120]}``) bounds them: a 3+2 orientation outside them, or one the kinematics cannot reach, is a
teaching error (:func:`check_orientation`); a continuous move outside them is a ``travel`` finding.

**Indexed (3+2) setups.** On a mill4 or mill5 every setup is a rotary position: a fixed orientation (``+Y``, ``-Z``,
...) the rotary axes can reach becomes one (:func:`orientation_rotary`; a mill4's ``+X``/``-X`` cannot, and stay a
re-fixture by hand), and its WCS is the rotated frame. Every move of the setup carries the setup's rotary position
(:func:`hold_rotary`, called by the run as each operation is placed), so a post writes ``A.. C..`` once, then cuts
in three axes: rotate, then cut. The operator sets the work offset with the part indexed.

**Continuous moves** (``rotary``, ``swarf``, ``surface_normal``) write ``x y z`` as the tool tip in the setup's WCS,
fixed to the part (the frame a controller's tool-centre-point mode programs in: LinuxCNC/Fanuc G43.4, Haas G234,
Siemens TRAORI), with ``a b c`` the rotary positions that tilt the tool. Moves between two rows are straight in that
frame, so planners chop rotations finely enough that the chord stays within the job's tolerance. The tool axis of
any move is :func:`tool_axes` of its ``a b c``: ``R_s^T · R(abc_s) · R(abc)^T · ẑ`` in part coordinates, with
``R_s`` the setup's WCS rotation and ``abc_s`` its rotary position (for an indexed setup this is just
``R(abc)^T · ẑ``). A post without tool-centre-point control converts with :func:`machine_positions` (rotary table
kinematics about a pivot the job's stock sets: :func:`pivot_part`).

Also here: :class:`PointCloud` (a dense, bucketed sample of a mesh's surface) and :func:`drop_along`, the sampled
drop-cutter every multi-axis planner and its gouge and holder checks use: a tool of any profile lowered along its
own axis onto the sampled surface. Stdlib at import; numpy inside.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError

__all__ = [
    "MoveList", "PointCloud", "check_orientation", "holder_intrusion", "intrusion_findings", "drop_along", "hold_rotary", "machine_positions", "orientation_rotary",
    "pivot_part", "rotary_axes", "solve_abc", "surface_points", "tool_axes", "tool_intrusion", "unit_axes",
]

#: The part direction each fixed orientation brings to the tool (+Z of the WCS).
_DIRECTIONS = {"+Z": (0.0, 0.0, 1.0), "-Z": (0.0, 0.0, -1.0), "+X": (1.0, 0.0, 0.0), "-X": (-1.0, 0.0, 0.0),
               "+Y": (0.0, 1.0, 0.0), "-Y": (0.0, -1.0, 0.0)}


def rotary_axes(machine) -> tuple[str, ...]:
    """The rotary axes a machine turns, lower case: ``("a",)``, ``("a", "c")``, ``("b", "c")`` or ``()``."""
    kind = getattr(machine, "kind", None)
    if kind == "mill4":
        return ("a",)
    if kind == "mill5":
        return ("b", "c") if getattr(machine, "kinematics", None) == "bc_head" else ("a", "c")
    return ()


def _axis_of(abc: dict) -> tuple[float, float, float]:
    """``R(abc)^T · ẑ`` (the tool axis in the mounted part's frame) for degrees ``{"a": .., "b": .., "c": ..}``."""
    a, b, c = (math.radians(abc.get(k, 0.0)) for k in "abc")
    sa, ca, sb, cb, sc, cc = math.sin(a), math.cos(a), math.sin(b), math.cos(b), math.sin(c), math.cos(c)
    return (-ca * sb * cc + sa * sc, ca * sb * sc + sa * cc, ca * cb)


def _limits_text(machine, axis: str) -> str:
    lo, hi = machine.rotary_limits_deg[axis]
    return f"{lo:g}..{hi:g}"


def _within(machine, axis: str, value: float) -> bool:
    limits = getattr(machine, "rotary_limits_deg", None) or {}
    if axis not in limits:
        return True
    lo, hi = limits[axis]
    return lo - 1e-9 <= value <= hi + 1e-9


def _solutions(direction, axes: tuple[str, ...], previous: dict | None = None) -> list[dict]:
    """Every rotary position (degrees) that brings part direction ``direction`` to the tool, nearest ``previous``
    first; empty when the kinematics cannot reach it."""
    x, y, z = direction
    norm = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / norm, y / norm, z / norm
    previous = previous or {}
    out: list[dict] = []
    if axes == ("a",):
        if abs(x) > 1e-6:
            return []
        a = math.degrees(math.atan2(y, z))
        out = [{"a": a}]
    elif axes in (("a", "c"), ("b", "c")):
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, z))))
        if math.hypot(x, y) < 1e-9:
            c = previous.get("c", 0.0)
        elif axes == ("a", "c"):
            c = math.degrees(math.atan2(x, y))
        else:
            c = math.degrees(math.atan2(y, -x))
        first = axes[0]
        out = [{first: tilt, "c": c}, {first: -tilt, "c": c + 180.0 if c <= 0 else c - 180.0}]
        if abs(tilt) < 1e-9:
            out = out[:1]
    # Each turning axis unwound to the turn nearest the previous position.
    for solution in out:
        for axis, value in list(solution.items()):
            if axis in previous:
                solution[axis] = value + 360.0 * round((previous[axis] - value) / 360.0)
    if previous:
        out.sort(key=lambda s: sum(abs(s[k] - previous.get(k, 0.0)) for k in s))
    return out


def orientation_rotary(orientation, machine) -> dict | None:
    """The rotary position (``{"a_deg": .., "c_deg": ..}``) of a setup on a mill4/mill5, every axis of the machine
    named; ``None`` for a machine without rotary axes or a fixed orientation its axes cannot reach (a re-fixture)."""
    axes = rotary_axes(machine)
    if not axes:
        return None
    if isinstance(orientation, dict):
        return {f"{axis}_deg": float(orientation.get(f"{axis}_deg", 0.0)) for axis in axes}
    for solution in _solutions(_DIRECTIONS[orientation], axes, {axis: 0.0 for axis in axes}):
        rounded = {axis: round(value, 9) + 0.0 for axis, value in solution.items()}
        if all(_within(machine, axis, value) for axis, value in rounded.items()):
            return {f"{axis}_deg": value for axis, value in rounded.items()}
    return None


def check_orientation(orientation: dict, machine, where: str) -> dict:
    """A 3+2 ``orientation`` the machine's rotary axes can reach, or the teaching error. Returns it with every axis
    of the machine named (``{"a_deg": 30.0, "c_deg": 0.0}``)."""
    axes = rotary_axes(machine)
    named = [key[0] for key, value in orientation.items() if value]
    extra = [axis for axis in named if axis not in axes]
    if extra:
        what = {"a": "A (about X)", "a,c": "A and C", "b,c": "B and C"}[",".join(axes)]
        use = " and ".join(f"{axis}_deg" for axis in axes)
        raise CamJobError(f"{where}: this {machine.kind} turns only {what}, so {extra[0]}_deg cannot be reached; "
                          f"use {use}" + (", or a mill5 for a compound tilt" if machine.kind == "mill4" else ""))
    out = {f"{axis}_deg": float(orientation.get(f"{axis}_deg", 0.0)) for axis in axes}
    for axis in axes:
        value = out[f"{axis}_deg"]
        if not _within(machine, axis, value):
            hint = ""
            if len(axes) == 2:
                tilt, turn = axes
                other = {tilt: -out[f"{tilt}_deg"], turn: out[f"{turn}_deg"] + (180.0 if out[f"{turn}_deg"] <= 0
                                                                               else -180.0)}
                if all(_within(machine, k, v) for k, v in other.items()):
                    hint = (f"; the same tilt is {tilt}_deg {other[tilt]:g} with {turn}_deg {other[turn]:g}, "
                            "which it can reach")
            raise CamJobError(f"{where}: {axis}_deg {value:g} is outside the machine's {axis.upper()} range "
                              f"{_limits_text(machine, axis)} (machine.rotary_limits_deg){hint or '; tilt less, or re-fixture the part'}")
    return out


def solve_abc(directions, machine, *, wcs=None, previous: dict | None = None):
    """Rotary positions (N, 3) degrees, columns a, b, c, that bring each part direction (N, 3) to the tool,
    continuous from ``previous`` (``{"a": .., "c": ..}``); rows the kinematics cannot reach (or only outside
    ``rotary_limits_deg``) are NaN. ``wcs`` is the setup (a re-fixtured part turns the directions first)."""
    import numpy as np

    axes = rotary_axes(machine)
    directions = np.asarray(directions, dtype=float).reshape(-1, 3)
    if wcs is not None:
        directions = directions @ _setup_rotation(wcs)
    out = np.full((len(directions), 3), np.nan)
    state = dict(previous or {axis: 0.0 for axis in axes})
    for row, direction in enumerate(directions):
        for solution in _solutions(tuple(direction), axes, state):
            if all(_within(machine, axis, value) for axis, value in solution.items()):
                out[row] = [solution.get("a", 0.0), solution.get("b", 0.0), solution.get("c", 0.0)]
                state = solution
                break
    return out


def unit_axes(abc):
    """``R(abc)^T · ẑ`` for rows of degrees (N, 3): the tool axis in the mounted part's frame."""
    import numpy as np

    abc = np.radians(np.asarray(abc, dtype=float).reshape(-1, 3))
    sa, ca = np.sin(abc[:, 0]), np.cos(abc[:, 0])
    sb, cb = np.sin(abc[:, 1]), np.cos(abc[:, 1])
    sc, cc = np.sin(abc[:, 2]), np.cos(abc[:, 2])
    return np.column_stack([-ca * sb * cc + sa * sc, ca * sb * sc + sa * cc, ca * cb])


def _setup_rotation(wcs):
    """``R_s^T · R(abc_s)``: from the mounted part's frame to part coordinates."""
    import numpy as np

    from cadgen._internal.cam.wcs import rotation_for

    setup = {f"{axis}_deg": value for axis, value in wcs.rotary_deg}
    return np.asarray(wcs.rotation).T @ np.asarray(rotation_for(setup))


def tool_axes(abc, wcs, *, rotary: bool = True):
    """The tool axis (N, 3), part coordinates, for moves at rotary positions ``abc`` (N, 3) degrees in setup
    ``wcs``; ``rotary`` false (a toolpath that turns no axis) gives the setup's fixed axis."""
    import numpy as np

    abc = np.asarray(abc, dtype=float).reshape(-1, 3)
    if not rotary:
        return np.tile(np.asarray(wcs.tool_axis, dtype=float), (len(abc), 1))
    return unit_axes(abc) @ _setup_rotation(wcs).T


def path_axes(toolpath, wcs, move_index):
    """The tool axis (part coordinates) at the end of each move in ``move_index`` (-1: the start, which holds the
    setup's position)."""
    import numpy as np

    move_index = np.asarray(move_index, dtype=np.int64)
    rotary = bool(toolpath.rotary) or bool(wcs.rotary_deg)
    if not rotary or not len(toolpath.moves):
        return tool_axes(np.zeros((len(move_index), 3)), wcs, rotary=False)
    moves = toolpath.moves
    abc = np.column_stack([moves["a"], moves["b"], moves["c"]])
    setup = dict(wcs.rotary_deg)
    start = np.array([setup.get("a", 0.0), setup.get("b", 0.0), setup.get("c", 0.0)])
    rows = np.where(move_index[:, None] >= 0, abc[np.maximum(move_index, 0)], start[None, :])
    return tool_axes(rows, wcs)


def hold_rotary(path, tail, wcs):
    """One operation's path and its tail (the climb to clearance the run adds) joined, every move carrying a rotary
    position: an operation that turns no axis gets the setup's position on every move; the tail holds where a
    continuous operation left the axes. A setup without rotary axes passes through unchanged."""
    from cadgen._internal.cam.ir import Toolpath, concat

    joined = concat([path, tail])
    setup = dict(wcs.rotary_deg)
    if not setup and not path.rotary:
        return joined
    moves = joined.moves.copy()
    n = len(path.moves)
    if not path.rotary:
        for axis, value in setup.items():
            moves[axis] = value
    elif n:
        for axis in "abc":
            moves[axis][n:] = moves[axis][n - 1]
    rotary = tuple(dict.fromkeys([*setup, *path.rotary]))
    return Toolpath(moves, joined.events, joined.ops, start=joined.start, rotary=rotary, lathe=joined.lathe)


def pivot_part(stock) -> tuple[float, float, float]:
    """Where the rotary axes cross, in part mm, as the job sets it: a cylinder stock's axis at its centre, else the
    stock's centre (the part is mounted centred on the rotary)."""
    if getattr(stock, "cylinder", None):
        return tuple(float(v) for v in stock.cylinder["center"])
    low, high = stock.bounds_min, stock.bounds_max
    return tuple((float(a) + float(b)) / 2.0 for a, b in zip(low, high))


def machine_positions(toolpath, wcs, pivot_part_mm):
    """``x y z`` (N, 3) for a post without tool-centre-point control: each move's tip turned by its rotary position
    about the pivot (rotary-table kinematics, the WCS origin unchanged), so the machine's linear axes put the tip
    where the part has turned to. Rows of a move at the setup's own rotary position are its WCS ``x y z``."""
    import numpy as np

    from cadgen._internal.cam.wcs import rotation_for

    moves = toolpath.moves
    tips = np.column_stack([moves["x"], moves["y"], moves["z"]])
    if not len(moves) or not (toolpath.rotary or wcs.rotary_deg):
        return tips
    pivot = wcs.to_wcs([pivot_part_mm])[0]
    setup_r = np.asarray(rotation_for({f"{k}_deg": v for k, v in wcs.rotary_deg}))
    out = np.empty_like(tips)
    for row in range(len(moves)):
        r = np.asarray(rotation_for({"a_deg": float(moves["a"][row]), "b_deg": float(moves["b"][row]),
                                     "c_deg": float(moves["c"][row])}))
        # The part turned from the setup's position to this move's: R(abc) · R(abc_s)^T, about the pivot.
        out[row] = pivot + (tips[row] - pivot) @ (r @ setup_r.T).T
    return out


# --- the sampled surface ---------------------------------------------------------------------------------

def surface_points(vertices, triangles, spacing: float):
    """Points on a mesh's surface about ``spacing`` apart (its corners and edges included): ``(points (M, 3), triangle
    index (M,))``. Each triangle is walked from the corner opposite its shortest edge in rows ``spacing`` apart, each
    row split ``spacing`` apart, so a long sliver costs its area, not its length squared."""
    import numpy as np

    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64)
    if not len(triangles):
        return np.zeros((0, 3)), np.zeros(0, dtype=np.int64)
    tri = vertices[triangles]
    # Corner A opposite the shortest edge, B and C the ends of that edge.
    lengths = np.linalg.norm(tri[:, [1, 2, 0]] - tri[:, [2, 0, 1]], axis=2)   # edge opposite corner 0, 1, 2
    apex = np.argmin(lengths, axis=1)
    rows = np.arange(len(tri))
    a = tri[rows, apex]
    b = tri[rows, (apex + 1) % 3]
    c = tri[rows, (apex + 2) % 3]
    spacing = max(spacing, 1e-6)
    n_long = np.clip(np.ceil(np.maximum(np.linalg.norm(b - a, axis=1), np.linalg.norm(c - a, axis=1)) / spacing),
                     1, 4000).astype(np.int64)
    n_base = np.clip(np.ceil(np.linalg.norm(c - b, axis=1) / spacing), 1, 4000).astype(np.int64)
    points, owners = [], []
    for long_, base in np.unique(np.column_stack([n_long, n_base]), axis=0):
        index = np.nonzero((n_long == long_) & (n_base == base))[0]
        s_rows = np.arange(long_ + 1) / long_
        widths = np.maximum(1, np.ceil(s_rows * base)).astype(np.int64)
        s = np.repeat(s_rows, widths + 1)
        t = np.concatenate([np.arange(w + 1) / w for w in widths])
        pa, pb, pc = a[index], b[index], c[index]
        grid = pa[:, None] + s[None, :, None] * ((pb - pa)[:, None] + t[None, :, None] * (pc - pb)[:, None])
        points.append(grid.reshape(-1, 3))
        owners.append(np.repeat(index, len(s)))
    return np.vstack(points), np.concatenate(owners)


class PointCloud:
    """Points bucketed on a cubic grid for box queries (:meth:`near`)."""

    def __init__(self, points, cell: float):
        import numpy as np

        self.points = np.asarray(points, dtype=float).reshape(-1, 3)
        self.cell = float(max(cell, 1e-3))
        if not len(self.points):
            self.low = np.zeros(3)
            self.shape = np.ones(3, dtype=np.int64)
            self.keys = np.zeros(0, dtype=np.int64)
            self.starts = self.ends = np.zeros(0, dtype=np.int64)
            return
        self.low = self.points.min(axis=0) - 1e-6
        index = np.floor((self.points - self.low) / self.cell).astype(np.int64)
        self.shape = index.max(axis=0) + 1
        keys = (index[:, 0] * self.shape[1] + index[:, 1]) * self.shape[2] + index[:, 2]
        order = np.argsort(keys, kind="stable")
        self.points = self.points[order]
        self.order = order
        keys = keys[order]
        self.keys, self.starts = np.unique(keys, return_index=True)
        self.ends = np.append(self.starts[1:], len(keys))

    def near(self, low, high):
        """Indices (into :attr:`points`) of the points in buckets overlapping the box ``[low, high]``."""
        import numpy as np

        if not len(self.keys):
            return np.zeros(0, dtype=np.int64)
        lo = np.maximum(np.floor((np.asarray(low) - self.low) / self.cell).astype(np.int64), 0)
        hi = np.minimum(np.floor((np.asarray(high) - self.low) / self.cell).astype(np.int64), self.shape - 1)
        if np.any(hi < lo):
            return np.zeros(0, dtype=np.int64)
        i, j, k = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1), np.arange(lo[2], hi[2] + 1),
                              indexing="ij")
        keys = ((i * self.shape[1] + j) * self.shape[2] + k).ravel()
        at = np.searchsorted(self.keys, keys)
        valid = at < len(self.keys)
        at, keys = at[valid], keys[valid]
        at = at[self.keys[at] == keys]
        if not len(at):
            return np.zeros(0, dtype=np.int64)
        starts, ends = self.starts[at], self.ends[at]
        counts = ends - starts
        return np.repeat(starts - np.cumsum(counts) + counts, counts) + np.arange(int(counts.sum()))


def _pairs_in_boxes(cloud: "PointCloud", lows, highs, budget: int = 2_000_000):
    """(placement, point) pairs for the points bucketed in each box ``[lows[n], highs[n]]``, in chunks:
    yields ``(placement indices, point indices)``."""
    import numpy as np

    lows = np.asarray(lows, dtype=float).reshape(-1, 3)
    highs = np.asarray(highs, dtype=float).reshape(-1, 3)
    if not len(cloud.keys) or not len(lows):
        return
    lo = np.maximum(np.floor((lows - cloud.low) / cloud.cell).astype(np.int64), 0)
    hi = np.minimum(np.floor((highs - cloud.low) / cloud.cell).astype(np.int64), cloud.shape - 1)
    size = np.maximum(hi - lo + 1, 0)
    cells = size.prod(axis=1)
    per_point = max(1.0, len(cloud.points) / max(1, len(cloud.keys)))
    start = 0
    while start < len(lows):
        cum = np.cumsum(cells[start:] * per_point)
        stop = start + max(1, int(np.searchsorted(cum, budget)))
        rows = np.arange(start, stop)
        start = stop
        n = cells[rows]
        if not n.sum():
            continue
        owner = np.repeat(rows, n)
        within = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
        sy, sz = size[owner, 1], size[owner, 2]
        i = lo[owner, 0] + within // (sy * sz)
        j = lo[owner, 1] + (within // sz) % sy
        k = lo[owner, 2] + within % sz
        keys = (i * cloud.shape[1] + j) * cloud.shape[2] + k
        at = np.searchsorted(cloud.keys, keys)
        valid = at < len(cloud.keys)
        valid[valid] = cloud.keys[at[valid]] == keys[valid]
        owner, at = owner[valid], at[valid]
        counts = cloud.ends[at] - cloud.starts[at]
        total = int(counts.sum())
        if not total:
            continue
        points = np.repeat(cloud.starts[at] - np.cumsum(counts) + counts, counts) + np.arange(total)
        yield np.repeat(owner, counts), points


def _frame(points, tip, axis):
    """Heights along ``axis`` above ``tip`` and distances from the axis line, for points (M, 3)."""
    import numpy as np

    rel = points - tip
    h = rel @ axis
    d = np.linalg.norm(rel - h[:, None] * axis[None, :], axis=1)
    return h, d


def _pair_frame(cloud, owner, index, tips, axes):
    import numpy as np

    rel = cloud.points[index] - tips[owner]
    h = np.einsum("ij,ij->i", rel, axes[owner])
    d = np.linalg.norm(rel - h[:, None] * axes[owner], axis=1)
    return h, d


def _boxes(tips, axes, start, end, radius):
    import numpy as np

    a = tips + np.asarray(start)[..., None] * axes
    b = tips + np.asarray(end)[..., None] * axes
    return np.minimum(a, b) - radius, np.maximum(a, b) + radius


def drop_along(cloud: PointCloud, tips, axes, tool, *, above: float, below: float):
    """For each placement (tip (N, 3), unit axis (N, 3)), how far the tool may move down its axis until it touches the
    sampled surface: ``s`` (N,), the tip's final place being ``tip - s · axis``. Points from ``below`` mm under the
    tip to ``above`` mm over it count; ``s`` is negative when the tool must rise to clear a point, ``inf`` when no
    point is under the cutter within ``below``."""
    import numpy as np

    tips = np.asarray(tips, dtype=float).reshape(-1, 3)
    axes = np.asarray(axes, dtype=float).reshape(-1, 3)
    r = tool.radius
    out = np.full(len(tips), np.inf)
    lows, highs = _boxes(tips, axes, -below, above, r)
    for owner, index in _pairs_in_boxes(cloud, lows, highs):
        h, d = _pair_frame(cloud, owner, index, tips, axes)
        keep = (d <= r) & (h >= -below) & (h <= above)
        if keep.any():
            np.minimum.at(out, owner[keep], tool.height_at(d[keep]) - h[keep])
    return out


def tool_intrusion(cloud: PointCloud, tips, axes, tool, *, tolerance: float, length: float | None = None,
                   shrink: float = 0.0):
    """How far the sampled surface enters each placed tool's cutter (shrunk by ``shrink`` sideways), from its tip to
    ``length`` (default the flutes): the worst ``(depth (N,), point (N, 3))`` per placement, depth 0 when clear.
    Points within ``tolerance`` of the cutter's surface do not count."""
    import numpy as np

    tips = np.asarray(tips, dtype=float).reshape(-1, 3)
    axes = np.asarray(axes, dtype=float).reshape(-1, 3)
    length = tool.flute_length_mm if length is None else length
    r = max(0.0, tool.radius - shrink)
    depth = np.zeros(len(tips))
    where = np.full((len(tips), 3), np.nan)
    lows, highs = _boxes(tips, axes, 0.0, length, r)
    for owner, index in _pairs_in_boxes(cloud, lows, highs):
        h, d = _pair_frame(cloud, owner, index, tips, axes)
        inside = (d < r) & (h > 0) & (h < length)
        if not inside.any():
            continue
        owner, index, h, d = owner[inside], index[inside], h[inside], d[inside]
        floor = tool.height_at(np.minimum(d, tool.radius))
        dig = np.minimum(np.minimum(h - floor, r - d), length - h)
        bad = dig > tolerance
        if not bad.any():
            continue
        owner, index, dig = owner[bad], index[bad], dig[bad]
        order = np.lexsort((dig, owner))
        last = np.r_[owner[order][1:] != owner[order][:-1], True]
        rows, best = owner[order][last], order[last]
        better = dig[best] > depth[rows]
        depth[rows[better]] = dig[best][better]
        where[rows[better]] = cloud.points[index[best][better]]
    return depth, where


def holder_intrusion(cloud: PointCloud, tips, axes, tool, *, clearance: float = 0.0):
    """How far the sampled surface enters the shank (flutes' top to the stickout) or the holder (above the stickout,
    ``holder_length_mm`` long) of each placed tool: ``(depth (N,), point (N, 3))``."""
    import numpy as np

    tips = np.asarray(tips, dtype=float).reshape(-1, 3)
    axes = np.asarray(axes, dtype=float).reshape(-1, 3)
    holder = tool.holder
    pieces = [(tool.flute_length_mm, holder.stickout_mm, holder.shank_diameter_mm / 2.0)]
    if holder.holder_diameter_mm:
        pieces.append((holder.stickout_mm, holder.stickout_mm + holder.holder_length_mm, holder.holder_diameter_mm / 2))
    depth = np.zeros(len(tips))
    where = np.full((len(tips), 3), np.nan)
    for start, end, radius in pieces:
        if end <= start:
            continue
        lows, highs = _boxes(tips, axes, start, end, radius)
        for owner, index in _pairs_in_boxes(cloud, lows, highs):
            h, d = _pair_frame(cloud, owner, index, tips, axes)
            inside = (h > start) & (h < end) & (d < radius - clearance)
            if not inside.any():
                continue
            owner, index, dig = owner[inside], index[inside], radius - d[inside]
            order = np.lexsort((dig, owner))
            last = np.r_[owner[order][1:] != owner[order][:-1], True]
            rows, best = owner[order][last], order[last]
            better = dig[best] > depth[rows]
            depth[rows[better]] = dig[best][better]
            where[rows[better]] = cloud.points[index[best][better]]
    return depth, where

class MoveList:
    """Moves that set ``x y z`` and ``a b c`` together (the IR rows a multi-axis planner writes), built into a
    :class:`~cadgen._internal.cam.ir.Toolpath` naming the machine's rotary axes. Motion of neither is dropped."""

    def __init__(self, start, abc, axes: tuple[str, ...], *, op: int = 0):
        self.start = tuple(float(v) for v in start)
        self.pos = list(self.start)
        self.abc = [float(v) for v in abc]
        self.axes = tuple(axes)
        self.op = op
        self.rows: list[tuple] = []

    def go(self, kind: int, xyz, abc=None, *, f: float = 0.0) -> None:
        xyz = [float(v) for v in xyz]
        abc = self.abc if abc is None else [float(v) for v in abc]
        if xyz == self.pos and abc == self.abc:
            return
        self.rows.append((kind, *xyz, *abc, float(f), 0.0, 0.0, 0.0, 0, 0.0, self.op))
        self.pos, self.abc = xyz, abc

    def polyline(self, kind: int, xyz, abc, *, f: float = 0.0) -> None:
        for point, angles in zip(xyz, abc):
            self.go(kind, point, angles, f=f)

    def build(self):
        import numpy as np

        from cadgen._internal.cam.ir import MOVE_DTYPE, Toolpath

        moves = np.array(self.rows, dtype=MOVE_DTYPE) if self.rows else np.zeros(0, dtype=MOVE_DTYPE)
        return Toolpath(moves, (), (), start=self.start, rotary=self.axes)


def intrusion_findings(ctx, summary: str, depth, where, *, check: str = "gouge") -> list[dict]:
    """One finding for an operation whose placed tool (``check="gouge"``: its cutter; ``"holder_collision"``: its
    shank or holder) enters the sampled part surface: ``depth`` (N,) per placement, ``where`` (N, 3) part mm."""
    import numpy as np

    from cadgen._internal.cam.checks.base import finding, xyz

    depth = np.asarray(depth, dtype=float)
    bad = depth > 0
    if not bad.any():
        return []
    k = int(np.argmax(depth))
    if check == "gouge":
        head = f"{summary} cuts into the part: up to {float(depth[k]):.2f} mm at {int(bad.sum())} move(s)"
        advice = ("the tool's placement or tilt leaves the cutter inside the part: use a smaller stepover or "
                  "sample_mm, a smaller tool, more stock to leave, or name only the faces it can reach")
        kind = "gouge_multiaxis"
    else:
        head = (f"{summary}: the shank or holder hits the part, up to {float(depth[k]):.2f} mm at {int(bad.sum())} "
                "move(s)")
        advice = "use a longer stickout or a slimmer holder, tilt the tool more (max_tilt_deg), or cut from another setup"
        kind = "holder_multiaxis"
    return [finding(check, "error", kind, head, advice,
                    [{"setup": ctx.setup.id, "operation": ctx.index, "depth_mm": round(float(depth[k]), 3),
                      "count": int(bad.sum()), "at": xyz(where[k])}])]

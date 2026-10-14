"""``rotary``: a 4th-axis wrap, the part turned about its X axis while the tool stays radial (lite).

The rotary axis is the part's X through the stock's centre line (a cylinder stock's own axis; a ``"cylinder"`` stock
along ``"x"`` is the usual bar). At every (X, angle) of a grid the tool, pointing at the axis, is dropped radially
onto the part (:func:`radial_drop`: exact vertex/edge/facet contact through the drop-cutter, held
``stock_to_leave_mm`` off); the radius it stops at is the finish surface.

* ``mode: "finish"`` (default) rides that surface: ``passes: "around"`` (default) turns A continuously, one ring per
  X step (``stepover``), alternating direction; ``passes: "along"`` runs along X at one angle, then indexes A by the
  stepover measured round the part's largest radius.
* ``mode: "rough"`` clears the stock in radial levels ``stepdown_mm`` apart, each pass at the level or the finish
  surface, whichever is further out; only passes with material at that level are cut. Each group of passes is entered
  by a ramp along its first pass (from the level above down to this one), then the pass is cut back at full depth.

Between groups the tool lifts radially to the retract radius (stock radius + ``retract_mm``) and turns or moves
there; it starts and ends at the clearance radius over the setup's angle. Moves are written as the tip in the part's
frame with A (or the machine's rotary axes) setting the tool radial (``multiaxis``), angles chopped so a chord
strays less than the tolerance. Every cutting move is gouge-checked against the same surface sample.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, choice, number_list, read_number
from cadgen._internal.cam.operations.base import Operation

__all__ = ["RotaryOp", "radial_drop"]

#: Most surface samples the drop reads; a bigger part samples coarser and says so.
MAX_SAMPLES = 1_200_000


def _exact_drop():
    """The drop-cutter (exact vertex, edge and facet contact), when this cadgen has it."""
    import importlib.util

    if importlib.util.find_spec("cadgen._internal.cam.dropcutter") is None:
        return None
    from cadgen._internal.cam import dropcutter

    return dropcutter


def radial_drop(points, centre_yz, xs, thetas, tool, *, mesh=None, leave: float = 0.0):
    """Tip radius (len(xs), len(thetas)) of a tool pointing at the X axis through ``centre_yz`` at each X and angle
    (degrees; 0 is +Z, 90 is +Y), held ``leave`` off the part; NaN where nothing is under the cutter.

    With ``mesh`` (vertices, triangles) and the drop-cutter in this cadgen, each angle's drop is exact: the triangles
    within the cutter's reach of that angle's radial plane, turned so the tool comes down their +Z, dropped on at
    every X. Otherwise the tool is dropped onto ``points`` (M, 3), a dense sample of the surface (every cutter
    profile through ``tool.height_at``; ``leave`` added after)."""
    import numpy as np

    xs = np.asarray(xs, dtype=float)
    r = tool.radius
    out = np.full((len(xs), len(thetas)), np.nan)
    exact = _exact_drop() if mesh is not None else None
    if exact is not None:
        vertices = np.asarray(mesh[0], dtype=float)
        triangles = np.asarray(mesh[1], dtype=np.int64)
        qy = vertices[:, 1] - centre_yz[0]
        qz = vertices[:, 2] - centre_yz[1]
        reach = r + leave + 1e-6
        for j, theta in enumerate(np.radians(np.asarray(thetas, dtype=float))):
            st, ct = math.sin(theta), math.cos(theta)
            s = qy * st + qz * ct
            t = qy * ct - qz * st
            ts, ss = t[triangles], s[triangles]
            near = (ts.min(axis=1) <= reach) & (ts.max(axis=1) >= -reach) & (ss.max(axis=1) > -reach)
            if not near.any():
                continue
            sub = triangles[near]
            used, local = np.unique(sub, return_inverse=True)
            frame = np.column_stack([vertices[used, 0], t[used], s[used]])
            z = exact.drop(np.column_stack([xs, np.zeros(len(xs))]), tool, (frame, local.reshape(-1, 3)),
                           leave=leave)
            out[:, j] = np.where(np.isfinite(z) & (z > 0.0), z, np.nan)
        return out
    points = np.asarray(points, dtype=float)
    qy = points[:, 1] - centre_yz[0]
    qz = points[:, 2] - centre_yz[1]
    order = np.argsort(points[:, 0], kind="stable")
    px, qy, qz = points[order, 0], qy[order], qz[order]
    for j, theta in enumerate(np.radians(np.asarray(thetas, dtype=float))):
        st, ct = math.sin(theta), math.cos(theta)
        s = qy * st + qz * ct            # along the tool axis (out from the X axis)
        t = qy * ct - qz * st            # across it, round the part
        near = (np.abs(t) <= r) & (s > -r)
        if not near.any():
            continue
        x_near, s_near, t_near = px[near], s[near], t[near]
        lo = np.searchsorted(x_near, xs - r, side="left")
        hi = np.searchsorted(x_near, xs + r, side="right")
        counts = hi - lo
        total = int(counts.sum())
        if not total:
            continue
        owner = np.repeat(np.arange(len(xs)), counts)
        index = np.repeat(lo - np.cumsum(counts) + counts, counts) + np.arange(total)
        d = np.hypot(x_near[index] - xs[owner], t_near[index])
        inside = d <= r
        value = np.where(inside, s_near[index] - tool.height_at(np.minimum(d, r)), -np.inf)
        best = np.full(len(xs), -np.inf)
        np.maximum.at(best, owner, value)
        out[:, j] = np.where(np.isfinite(best) & (best > 0.0), best + leave, np.nan)
    return out


class RotaryOp(Operation):
    name = "rotary"
    plain = "4th-axis wrap"
    family = "Multi-axis"
    machines = ("mill4", "mill5")
    status = "lite"
    limits = (
        "Wraps about the part's X axis through the stock's centre line; the part must be mounted on that axis.",
        "The tool is dropped radially onto the part's tessellation (exact contact through the drop-cutter; without it, "
        "onto a dense sample of the surface); the gouge check reads a dense sample of the surface.",
        "Undercuts the radial direction cannot see (a face that overhangs along X) are left.",
        "Roughing cuts every pass that has material at a level, riding the finish surface where there is none, so "
        "it air-cuts over finished areas.",
        "Moves are the tool tip in the part's frame with A turning (tool-centre-point style); a controller without "
        "TCP needs the post to convert them (multi-axis.md).",
    )
    keys = ("mode", "passes", "x_range_mm", "angle_range_deg", "sample_mm")
    tool_types = ("ball", "flat", "bull")
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        params = {
            "mode": choice(extra.get("mode", "finish"), ("finish", "rough"), f"{spec.where}.mode"),
            "passes": choice(extra.get("passes", "around"), ("around", "along"), f"{spec.where}.passes"),
            "x_range": None, "angles": (0.0, 360.0),
            "sample_mm": read_number(extra, "sample_mm", spec.where, default=0.5, minimum=0.02, maximum=10.0),
        }
        if "x_range_mm" in extra:
            low, high = number_list(extra["x_range_mm"], f"{spec.where}.x_range_mm", length=2)
            if high <= low:
                raise CamJobError(f"{spec.where}.x_range_mm must be [start, end] along the part's X with end more "
                                  "than start")
            params["x_range"] = (low, high)
        if "angle_range_deg" in extra:
            low, high = number_list(extra["angle_range_deg"], f"{spec.where}.angle_range_deg", length=2)
            if not 0 < high - low <= 360:
                raise CamJobError(f"{spec.where}.angle_range_deg must be [from, to] with to more than from and at most "
                                  "360 degrees apart")
            params["angles"] = (low, high)
        if ctx.job.stock.kind == "cylinder" and ctx.job.stock.axis != "x":
            raise CamJobError(f"{spec.where}: a rotary wrap turns the part about its X axis; the stock cylinder runs "
                              f"along {ctx.job.stock.axis}. Give the stock \"axis\": \"x\" (and model the part along X)")
        return params

    def summary(self, ctx, params) -> str:
        base = super().summary(ctx, params)
        return f"{base}, {params['mode']} {params['passes']}"

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam.ir import FEED, PLUNGE, RAPID
        from cadgen._internal.cam.multiaxis import (
            MoveList, PointCloud, intrusion_findings, pivot_part, rotary_axes, solve_abc, surface_points, tool_axes,
            tool_intrusion,
        )

        tool = ctx.tool
        r = tool.radius
        tol = ctx.tolerance_mm
        leave = ctx.spec.stock_to_leave_mm
        wcs = ctx.wcs
        axes = rotary_axes(ctx.machine)
        rough = params["mode"] == "rough"
        around = params["passes"] == "around"
        pivot = np.asarray(pivot_part(ctx.stock), dtype=float)
        yc, zc = float(pivot[1]), float(pivot[2])
        stock_v = np.asarray(ctx.stock.vertices, dtype=float)
        r_stock = float(np.hypot(stock_v[:, 1] - yc, stock_v[:, 2] - zc).max())
        r_clear = r_stock + ctx.setup.clearance_mm
        r_retract = r_stock + ctx.setup.retract_mm
        part_v = np.asarray(ctx.part.vertices, dtype=float)
        x0, x1 = params["x_range"] or (float(part_v[:, 0].min()), float(part_v[:, 0].max()))
        a0, a1 = params["angles"]
        full = abs((a1 - a0) - 360.0) < 1e-9

        # The sampled surface.
        tri = part_v[np.asarray(ctx.part.triangles)]
        area = float(np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum() / 2.0)
        spacing = min(0.25, max(0.03, r / 6.0))
        wanted = spacing
        while area / (spacing * spacing) * 0.6 > MAX_SAMPLES:
            spacing *= 1.25
        if spacing > wanted:
            ctx.meta.setdefault("adapted", []).append({
                "step": "surface_sample", "words": f"{self.name}: part surface sampled every {spacing:.3g} mm, not "
                f"{wanted:.3g} mm, to fit {MAX_SAMPLES:,} samples",
                "accuracy": f"the tool may sit up to about {spacing * spacing / (8 * max(r, 1e-3)):.3g} mm into the "
                            "part between samples"})
        points, _ = surface_points(ctx.part.vertices, ctx.part.triangles, spacing)

        # The grid of X and angle, and the finish surface on it.
        stepover = ctx.stepover(0.4 if rough else 0.1)
        sample = params["sample_mm"]
        r_part = float(np.hypot(points[:, 1] - yc, points[:, 2] - zc).max()) if len(points) else r_stock
        chord = 2.0 * math.degrees(math.acos(max(-1.0, 1.0 - tol / max(r_clear, 1e-6))))
        if around:
            dx = stepover
            dtheta = min(math.degrees(sample / max(r_stock, 1e-6)), chord)
        else:
            dx = sample
            dtheta = min(math.degrees(stepover / max(r_part, 1e-6)), chord)
        nx = max(2, int(math.ceil((x1 - x0) / dx - 1e-9)) + 1)
        nt = max(2, int(math.ceil((a1 - a0) / dtheta - 1e-9)) + 1)
        xs = np.linspace(x0, x1, nx)
        thetas = np.linspace(a0, a1, nt)
        drop = radial_drop(points, (yc, zc), xs, thetas, tool, mesh=(ctx.part.vertices, ctx.part.triangles),
                           leave=leave)
        finish = np.where(np.isnan(drop), r_stock, np.minimum(drop, r_stock))
        if not np.isfinite(drop).any():
            raise CamJobError(f"{ctx.spec.where}: the tool finds no part surface to wrap between X {x0:g} and {x1:g}; "
                              "check x_range_mm and that the part lies along X through the stock's centre line")

        def theta_dir(theta_deg):
            t = np.radians(np.asarray(theta_deg, dtype=float))
            return np.column_stack([np.zeros_like(t), np.sin(t), np.cos(t)])

        def tip(x, theta_deg, rho):
            x = np.asarray(x, dtype=float)
            d = theta_dir(theta_deg)
            return np.column_stack([x, yc + rho * d[:, 1], zc + rho * d[:, 2]])

        # Passes: each a run of (x, theta, rho) the tool cuts, with its entry ramp when it opens a group.
        feeds = ctx.feeds("rough" if rough else "finish", stepover_mm=stepover)
        passes: list[dict] = []

        def pass_of(index: int, reverse: bool, rho_row):
            if around:
                x = np.full(nt, xs[index])
                theta = thetas.copy()
            else:
                x = xs.copy()
                theta = np.full(nx, thetas[index])
            rho = np.asarray(rho_row, dtype=float)
            if reverse:
                x, theta, rho = x[::-1], theta[::-1], rho[::-1]
            return x, theta, rho

        count = nx if around else (nt - 1 if full else nt)
        if not rough:
            for k in range(count):
                row = finish[k] if around else finish[:, k]
                x, theta, rho = pass_of(k, k % 2 == 1, row)
                passes.append({"x": x, "theta": theta, "rho": rho, "group": 0, "ramp_from": None, "level": -np.inf})
            levels = []
        else:
            stepdown = ctx.stepdown()
            bottom = float(finish.min())
            levels = []
            level = r_stock
            while level - stepdown > bottom + 1e-6:
                level -= stepdown
                levels.append(level)
            levels.append(bottom)
            above = r_stock
            group = 0
            for level in levels:
                previous = None
                flip = False
                for k in range(count):
                    row = finish[k] if around else finish[:, k]
                    if not (row < above - 1e-6).any():
                        previous = None
                        continue
                    target = np.maximum(row, level)
                    if previous is None:
                        group += 1
                        flip = False
                        # Ramp from the level above down to this one along the pass, then cut it back at depth.
                        x, theta, rho = pass_of(k, False, target)
                        ramp = above + (level - above) * np.linspace(0.0, 1.0, len(rho))
                        passes.append({"x": x, "theta": theta, "rho": np.maximum(ramp, rho), "group": group,
                                       "ramp_from": above, "level": level})
                        flip = True
                    x, theta, rho = pass_of(k, flip, target)
                    passes.append({"x": x, "theta": theta, "rho": rho, "group": group, "ramp_from": None,
                                   "level": level})
                    flip = not flip
                    previous = k
                above = level

        # Split any segment whose straight chord would sink into the finish surface.
        inserted = _refine(passes, lambda xm, tm: _drop_pairs(points, (yc, zc), xm, tm, tool, ctx, leave, r_stock),
                           tol)
        if inserted:
            ctx.meta["refined"] = inserted

        # Moves, in the part's frame; rotary positions solved once over the whole sequence.
        setup = dict(wcs.rotary_deg)
        setup_axis = tool_axes([[setup.get(a, 0.0) for a in "abc"]], wcs, rotary=bool(setup))[0]
        theta_home = math.degrees(math.atan2(setup_axis[1], setup_axis[2]))
        sequence: list[tuple] = []        # (kind, part points (N, 3), directions (N, 3), feed)

        def add(kind, points_p, dirs, f=0.0):
            sequence.append((kind, np.asarray(points_p, dtype=float).reshape(-1, 3),
                             np.asarray(dirs, dtype=float).reshape(-1, 3), f))

        def turn(x, theta_from, theta_to, rho, kind=RAPID, f=0.0, step=10.0):
            if abs(theta_to - theta_from) < 1e-9:
                return
            n = max(1, int(math.ceil(abs(theta_to - theta_from) / step)))
            th = np.linspace(theta_from, theta_to, n + 1)[1:]
            add(kind, tip(np.full(n, x), th, np.full(n, rho)), theta_dir(th), f)

        start = wcs.from_wcs([ctx.start])[0]
        state = {"x": float(start[0]), "theta": theta_home, "rho": None}
        add(RAPID, tip([x0 if passes else state["x"]], [theta_home], [r_clear]), theta_dir([theta_home]))
        state.update(x=float(x0), rho=r_clear)
        plunges = 0
        last_group = None
        for p in passes:
            x, theta, rho = p["x"], p["theta"], p["rho"]
            joined = (p["group"] == last_group and state["rho"] is not None and state["rho"] < r_retract - 1e-9)
            if joined:
                # A step to the next pass at this level: out to the higher of the two, across, down.
                high = max(state["rho"], float(rho[0]))
                if high > state["rho"] + 1e-9:
                    add(FEED, tip([state["x"]], [state["theta"]], [high]), theta_dir([state["theta"]]),
                        feeds.feed_mm_min)
                add(FEED, tip([x[0]], [theta[0]], [high]), theta_dir([theta[0]]), feeds.feed_mm_min)
            else:
                # Out to the retract radius, over, and down.
                if state["rho"] is not None and state["rho"] < r_retract - 1e-9:
                    add(RAPID, tip([state["x"]], [state["theta"]], [r_retract]), theta_dir([state["theta"]]))
                    state["rho"] = r_retract
                travel = state["rho"] if state["rho"] is not None else r_clear
                if abs(x[0] - state["x"]) > 1e-9:
                    add(RAPID, tip([x[0]], [state["theta"]], [travel]), theta_dir([state["theta"]]))
                turn(float(x[0]), state["theta"], float(theta[0]), travel)
                add(RAPID, tip([x[0]], [theta[0]], [r_retract]), theta_dir([theta[0]]))
                entry = float(rho[0])           # a ramp pass starts at the level above (or the surface)
                if rough and p["ramp_from"] is None:
                    plunges += 1
                add(PLUNGE, tip([x[0]], [theta[0]], [entry]), theta_dir([theta[0]]), feeds.plunge_mm_min)
            f = feeds.ramp_mm_min if p["ramp_from"] is not None else feeds.feed_mm_min
            add(FEED, tip(x, theta, rho), theta_dir(theta), f)
            state.update(x=float(x[-1]), theta=float(theta[-1]), rho=float(rho[-1]))
            last_group = p["group"]
        # Out, and back round to the setup's angle at the clearance radius (unwinding every turn the wrap made).
        add(RAPID, tip([state["x"]], [state["theta"]], [r_clear]), theta_dir([state["theta"]]))
        turn(state["x"], state["theta"], theta_home, r_clear)

        # Solve A (and the machine's other axes) for every point, continuous through the sequence.
        all_dirs = np.vstack([d for _, _, d, _ in sequence])
        abc = solve_abc(all_dirs, ctx.machine, wcs=wcs, previous={a: setup.get(a, 0.0) for a in axes})
        if np.isnan(abc).any():
            raise CamJobError(f"{ctx.spec.where}: this {ctx.machine.kind}'s rotary axes cannot point the tool at the X "
                              "axis all the way round (check machine.rotary_limits_deg, the setup's orientation, or "
                              "narrow angle_range_deg)")
        moves = MoveList(ctx.start, [setup.get(a, 0.0) for a in "abc"], axes, op=ctx.index)
        row = 0
        for kind, pts, dirs, f in sequence:
            n = len(pts)
            moves.polyline(kind, wcs.to_wcs(pts), abc[row:row + n], f=f)
            row += n
        path = moves.build()

        # Gouge check: the tool at the middle of every cutting move, against the same surface sample.
        cloud = PointCloud(points, max(r, 1.0))
        cut = np.isin(path.moves["kind"], (FEED, PLUNGE))
        findings = []
        if cut.any():
            pos = path.positions()
            index = np.nonzero(cut)[0]
            mids_w = (pos[index] + pos[index + 1]) / 2.0
            abc_m = (np.column_stack([path.moves[a][index] for a in "abc"]) +
                     np.column_stack([np.r_[setup.get(a, 0.0), path.moves[a]][index] for a in "abc"])) / 2.0
            mids = wcs.from_wcs(mids_w)
            dirs = tool_axes(abc_m, wcs)
            # The tip's end of the cutter: the drop held the whole column clear, so only chords near the tip can dig.
            depth, where = tool_intrusion(cloud, mids, dirs, tool, tolerance=max(0.02, 2 * tol),
                                          length=min(tool.flute_length_mm, 2.0 * r + 1.0))
            findings = intrusion_findings(ctx, self.summary(ctx, params), depth, where)
        ctx.meta.update({"passes": len(passes), "levels": len(levels) if rough else 1, "stock_to_leave": leave,
                         "rotary": {"axis": "x", "pivot_part_mm": [round(float(v), 4) for v in pivot],
                                    "stock_radius_mm": round(r_stock, 4), "tcp": True},
                         "bottom_z": round(float(finish.min()), 4)})
        if plunges:
            ctx.meta["plunges"] = plunges
        if findings:
            ctx.meta.setdefault("findings", []).extend(findings)
        return path


def _drop_pairs(points, centre_yz, xs, thetas, tool, ctx, leave: float, r_stock: float):
    """The finish radius at each (x, angle) pair, grouped by angle (one drop per distinct angle)."""
    import numpy as np

    xs, thetas = np.asarray(xs, dtype=float), np.asarray(thetas, dtype=float)
    out = np.full(len(xs), r_stock)
    keys = np.round(thetas, 9)
    for theta in np.unique(keys):
        pick = keys == theta
        rho = radial_drop(points, centre_yz, xs[pick], [float(theta)], tool,
                          mesh=(ctx.part.vertices, ctx.part.triangles), leave=leave)[:, 0]
        out[pick] = np.where(np.isnan(rho), r_stock, np.minimum(rho, r_stock))
    return out


def _refine(passes, drop, tolerance: float, rounds: int = 8) -> int:
    """Split every pass segment whose straight chord (the tip moves straight between two rows) would sink more than
    ``tolerance`` below the finish surface at its middle; repeated ``rounds`` times. Returns the points added."""
    import numpy as np

    added = 0
    pending = [np.ones(max(0, len(p["x"]) - 1), dtype=bool) for p in passes]
    for _ in range(rounds):
        mids, owners = [], []
        for k, (p, flag) in enumerate(zip(passes, pending)):
            index = np.nonzero(flag)[0]
            if len(index):
                mids.append(np.column_stack([(p["x"][index] + p["x"][index + 1]) / 2,
                                             (p["theta"][index] + p["theta"][index + 1]) / 2, index]))
                owners.append(np.full(len(index), k))
        if not mids:
            break
        mids = np.vstack(mids)
        owners = np.concatenate(owners)
        rho_mid = drop(mids[:, 0], mids[:, 1])
        next_pending = []
        for k, p in enumerate(passes):
            pick = owners == k
            if not pick.any():
                next_pending.append(np.zeros(max(0, len(p["x"]) - 1), dtype=bool))
                continue
            index = mids[pick, 2].astype(np.int64)
            half = np.radians(np.abs(p["theta"][index + 1] - p["theta"][index])) / 2.0
            chord = (p["rho"][index] + p["rho"][index + 1]) / 2.0 * np.cos(half)
            # Where the tip must be at the middle: on the surface, at the pass's level, or on its ramp.
            want = np.maximum(rho_mid[pick], p["level"])
            if p["ramp_from"] is not None:
                want = np.maximum(want, (p["rho"][index] + p["rho"][index + 1]) / 2.0)
            need = want - chord > tolerance
            if not need.any():
                next_pending.append(np.zeros(len(p["x"]) - 1, dtype=bool))
                continue
            at = index[need] + 1
            p["x"] = np.insert(p["x"], at, mids[pick, 0][need])
            p["theta"] = np.insert(p["theta"], at, mids[pick, 1][need])
            p["rho"] = np.insert(p["rho"], at, want[need])
            added += int(need.sum())
            # The two halves of each split segment are checked next round.
            flags = np.zeros(len(p["x"]) - 1, dtype=bool)
            new_at = at + np.arange(len(at))
            flags[new_at - 1] = True
            flags[np.minimum(new_at, len(flags) - 1)] = True
            next_pending.append(flags)
        pending = next_pending
    return added

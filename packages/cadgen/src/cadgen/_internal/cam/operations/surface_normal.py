"""``surface_normal``: a 5-axis finish, a ball end mill raster over named faces with its axis along the surface normal
(lite).

Name the faces to finish (``faces``). Raster lines ``stepover`` apart run across them at ``angle_deg`` in the setup's
XY (zig-zag); along each line, every ``sample_mm``, the line is cast down onto the named faces (the highest hit), and
the surface normal there is the face's own, smoothed across its triangles. The ball's centre sits ``radius`` plus
``stock_to_leave_mm`` out along that normal, so the ball touches the surface whatever the tilt; the tool's axis is
the normal leaned by ``lead_deg`` (its top forward along the cut, negative back) and ``tilt_deg`` (its top to the
right of the cut), smoothed along the line over ``smooth`` samples and kept within ``max_tilt_deg`` (default 30) of
the setup's tool direction.

Each placement is then checked against a dense sample of the whole part: where the cutter or the shank above it would
cut into the part (a concave corner, a neighbouring wall), the tool rises up its own axis until it clears, and the
shank and holder are tested for collisions (``holder_collision``). Lines are linked by a rapid lift up the tool's axis
(the rotary axes held, so a turn never starts in the cut) and a short hop when the next line starts near, else by the
clearance height. Undercut spots (a normal facing down) are skipped.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, read_number
from cadgen._internal.cam.operations.base import Operation

__all__ = ["SurfaceNormalOp", "cast_down"]


def cast_down(vertices, triangles, xy):
    """Each point (N, 2) cast straight down onto a mesh (vertices in the frame the points are in): the highest hit's
    ``(z (N,), triangle (N,), barycentric weights (N, 3))``; z NaN and triangle -1 where it misses."""
    import numpy as np

    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64)
    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    z = np.full(len(xy), -np.inf)
    owner = np.full(len(xy), -1, dtype=np.int64)
    weights = np.zeros((len(xy), 3))
    if not len(xy) or not len(triangles):
        return np.full(len(xy), np.nan), owner, weights
    cell = max(1e-3, float(np.sqrt(np.ptp(xy[:, 0]) * np.ptp(xy[:, 1]) / len(xy))) if len(xy) > 1 else 1.0)
    origin = xy.min(axis=0)
    key = np.floor((xy - origin) / cell).astype(np.int64)
    width = int(key[:, 1].max()) + 1
    flat = key[:, 0] * width + key[:, 1]
    order = np.argsort(flat, kind="stable")
    sorted_keys = flat[order]
    tri = vertices[triangles]
    lo = np.floor((tri[:, :, :2].min(axis=1) - origin) / cell).astype(np.int64)
    hi = np.floor((tri[:, :, :2].max(axis=1) - origin) / cell).astype(np.int64)
    rows = int(key[:, 0].max()) + 1
    for t in range(len(tri)):
        if hi[t, 0] < 0 or hi[t, 1] < 0 or lo[t, 0] >= rows or lo[t, 1] >= width:
            continue
        i0, j0 = max(lo[t, 0], 0), max(lo[t, 1], 0)
        i1, j1 = min(hi[t, 0], rows - 1), min(hi[t, 1], width - 1)
        candidates = []
        for i in range(i0, i1 + 1):
            a = np.searchsorted(sorted_keys, i * width + j0, side="left")
            b = np.searchsorted(sorted_keys, i * width + j1, side="right")
            if b > a:
                candidates.append(order[a:b])
        if not candidates:
            continue
        pick = np.concatenate(candidates)
        a, b, c = tri[t]
        det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(det) < 1e-14:
            continue
        px, py = xy[pick, 0], xy[pick, 1]
        w1 = ((px - a[0]) * (c[1] - a[1]) - (py - a[1]) * (c[0] - a[0])) / det
        w2 = ((b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])) / det
        w0 = 1.0 - w1 - w2
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        height = w0 * a[2] + w1 * b[2] + w2 * c[2]
        better = inside & (height > z[pick])
        hit = pick[better]
        z[hit] = height[better]
        owner[hit] = t
        weights[hit] = np.column_stack([w0, w1, w2])[better]
    z[owner < 0] = np.nan
    return z, owner, weights


def vertex_normals(vertices, triangles):
    """Area-weighted vertex normals of a mesh (only its own triangles), unit length."""
    import numpy as np

    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64)
    tri = vertices[triangles]
    face = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    out = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(out, triangles[:, k], face)
    norm = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norm > 1e-12, norm, 1.0)


def _rotate_toward(axes, target, limit_rad):
    """Each unit axis (N, 3) turned toward ``target`` (3,) so it is at most ``limit_rad`` from it."""
    import numpy as np

    cos = np.clip(axes @ target, -1.0, 1.0)
    angle = np.arccos(cos)
    over = angle > limit_rad
    if not over.any():
        return axes
    side = axes[over] - cos[over, None] * target
    side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-12)
    out = axes.copy()
    out[over] = math.cos(limit_rad) * target + math.sin(limit_rad) * side
    return out


class SurfaceNormalOp(Operation):
    name = "surface_normal"
    plain = "5-axis finish"
    family = "Multi-axis"
    machines = ("mill5",)
    status = "lite"
    limits = (
        "Ball end mills only: the ball touches the surface at the same point whatever the tilt, so leaning the axis "
        "never moves the contact.",
        "The raster is cast straight down the setup's tool direction, so a face's undercut spots (normal facing "
        "down) are skipped; finish them from another setup.",
        "Where the cutter or shank would cut into the part the tool rises up its own axis instead of re-tilting, "
        "which leaves material there (and the gouge check reads a dense sample of the surface).",
        "Where the axis passes near the setup's tool direction (the rotary pole) C can swing fast; it is not "
        "smoothed or avoided, so a lead_deg or tilt_deg of a few degrees keeps the tool off the pole.",
        "Moves are the tool tip in the part's frame with A/B/C tilting the tool (tool-centre-point style).",
    )
    keys = ("angle_deg", "lead_deg", "tilt_deg", "max_tilt_deg", "smooth", "sample_mm")
    common_keys = ("feed", "speed", "stepover", "stepover_mm", "stock_to_leave_mm")
    tool_types = ("ball",)
    takes_faces = True
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if not spec.faces:
            raise CamJobError(f"{spec.where}: a surface_normal names the faces it finishes (\"faces\": [\"#o1.f7\"]); "
                              "cadgen cam features lists them")
        extra = spec.extra
        smooth = extra.get("smooth", 5)
        if isinstance(smooth, bool) or not isinstance(smooth, int) or not 1 <= smooth <= 101:
            raise CamJobError(f"{spec.where}.smooth must be a whole number of samples from 1 (no smoothing) to 101")
        return {
            "angle_deg": read_number(extra, "angle_deg", spec.where, default=0.0, minimum=-360.0, maximum=360.0),
            "lead_deg": read_number(extra, "lead_deg", spec.where, default=0.0, minimum=-60.0, maximum=60.0),
            "tilt_deg": read_number(extra, "tilt_deg", spec.where, default=0.0, minimum=-60.0, maximum=60.0),
            "max_tilt_deg": read_number(extra, "max_tilt_deg", spec.where, default=30.0, minimum=0.0, maximum=90.0),
            "smooth": smooth,
            "sample_mm": read_number(extra, "sample_mm", spec.where, default=0.5, minimum=0.02, maximum=20.0),
        }

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam.ir import FEED, RAPID
        from cadgen._internal.cam.multiaxis import (
            MoveList, PointCloud, drop_along, holder_intrusion, intrusion_findings, rotary_axes, solve_abc,
            surface_points, tool_intrusion,
        )

        tool, wcs = ctx.tool, ctx.wcs
        r = tool.radius
        tol = ctx.tolerance_mm
        leave = ctx.spec.stock_to_leave_mm
        axes_names = rotary_axes(ctx.machine)
        setup = dict(wcs.rotary_deg)
        setup_abc = [setup.get(a, 0.0) for a in "abc"]
        stepover = ctx.stepover(0.1)
        sample = params["sample_mm"]
        feeds = ctx.feeds("finish", stepover_mm=stepover)

        # The named faces in WCS, turned so the raster runs along X'.
        vertices_w, _ = ctx.mesh
        vertices_w = np.asarray(vertices_w, dtype=float)
        triangles = np.vstack([ctx.face_triangles(ref) for ref in ctx.spec.faces])
        normals_w = vertex_normals(vertices_w, triangles)
        angle = math.radians(params["angle_deg"])
        ca, sa = math.cos(angle), math.sin(angle)
        turn = np.array([[ca, sa, 0.0], [-sa, ca, 0.0], [0.0, 0.0, 1.0]])        # WCS -> raster frame
        local = vertices_w @ turn.T
        used = np.unique(triangles)
        x0, x1 = local[used, 0].min(), local[used, 0].max()
        y0, y1 = local[used, 1].min(), local[used, 1].max()
        lines = max(1, int(math.ceil((y1 - y0) / stepover - 1e-9)) + 1)
        along = max(2, int(math.ceil((x1 - x0) / sample)) + 1)
        ys = np.linspace(y0, y1, lines) if lines > 1 else np.array([(y0 + y1) / 2])
        xs = np.linspace(x0, x1, along)
        gx, gy = np.meshgrid(xs, ys)               # (lines, along)
        z, owner, weights = cast_down(local, triangles, np.column_stack([gx.ravel(), gy.ravel()]))
        hit = owner >= 0
        normal = np.zeros((len(z), 3))
        if hit.any():
            corners = triangles[owner[hit]]
            normal[hit] = np.einsum("ij,ijk->ik", weights[hit], normals_w[corners])
            normal[hit] /= np.maximum(np.linalg.norm(normal[hit], axis=1, keepdims=True), 1e-12)
        facing = hit & (normal[:, 2] > 1e-3)
        skipped = int((hit & ~facing).sum())
        contact_local = np.column_stack([gx.ravel(), gy.ravel(), z])
        contact = contact_local @ turn                  # back to WCS (rows: raster -> WCS)
        up = np.array([0.0, 0.0, 1.0])
        limit = math.radians(params["max_tilt_deg"])
        travel_x = turn[0]                              # the raster's +X' in WCS

        points, _ = surface_points(ctx.part.vertices, ctx.part.triangles, min(0.25, max(0.05, r / 6.0)))
        cloud = PointCloud(wcs.to_wcs(points), max(r, 1.0))
        runs = []
        clamped = 0
        lifted = 0.0
        for k in range(lines):
            row = slice(k * along, (k + 1) * along)
            ok = facing[row]
            edges = np.flatnonzero(np.diff(np.r_[0, ok.astype(int), 0]))
            forward = k % 2 == 0
            pieces = []
            for a, b in zip(edges[::2], edges[1::2]):
                if b - a < 1:
                    continue
                p = contact[row][a:b]
                n = normal[row][a:b]
                direction = travel_x if forward else -travel_x
                if not forward:
                    p, n = p[::-1], n[::-1]
                centre = p + (r + leave) * n
                # Lead along the cut and tilt across it, in the tangent plane.
                t = direction - (n @ direction)[:, None] * n
                t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
                side = np.cross(t, n)                   # to the right of the cut
                lead, tilt = math.radians(params["lead_deg"]), math.radians(params["tilt_deg"])
                axis = n * math.cos(lead) + t * math.sin(lead)
                axis = axis * math.cos(tilt) + side * math.sin(tilt)
                axis /= np.linalg.norm(axis, axis=1, keepdims=True)
                before = np.arccos(np.clip(axis @ up, -1.0, 1.0)) > limit + 1e-9
                axis = _rotate_toward(axis, up, limit)
                if params["smooth"] > 1 and len(axis) > 2:
                    width = min(params["smooth"], len(axis))
                    kernel = np.ones(width) / width
                    padded = np.pad(axis, ((width // 2, width - 1 - width // 2), (0, 0)), mode="edge")
                    axis = np.column_stack([np.convolve(padded[:, c], kernel, mode="valid") for c in range(3)])
                    axis /= np.linalg.norm(axis, axis=1, keepdims=True)
                    axis = _rotate_toward(axis, up, limit)
                clamped += int(before.sum())
                tips = centre - r * axis
                # Clear the rest of the part: up the tool's axis where the cutter or shank would cut in.
                s = drop_along(cloud, tips, axis, tool, above=tool.flute_length_mm, below=r)
                rise = np.where(np.isfinite(s), np.maximum(0.0, -s - tol), 0.0)
                lifted = max(lifted, float(rise.max()) if len(rise) else 0.0)
                tips = tips + rise[:, None] * axis
                pieces.append((tips, axis))
            runs.extend(pieces if forward else pieces[::-1])
        if not runs:
            raise CamJobError(f"{ctx.spec.where}: the raster finds no face of {', '.join(ctx.spec.faces)} facing the "
                              f"tool in setup '{ctx.setup.id}'; name faces seen from above, or tilt the setup")

        # Moves (WCS), then the rotary positions for every one.
        sequence = []
        clearance = ctx.heights.clearance
        hop = ctx.setup.retract_mm

        def add(kind, pts, dirs, f=0.0):
            sequence.append((kind, np.asarray(pts, dtype=float).reshape(-1, 3),
                             np.asarray(dirs, dtype=float).reshape(-1, 3), f))

        def above(point, d):
            return point + max(0.0, clearance - point[2]) / max(d[2], 0.05) * d

        position = np.asarray(ctx.start, dtype=float)
        axis_now = up
        for index, (tips, axis) in enumerate(runs):
            start, a0 = tips[0], axis[0]
            near = start + hop * a0
            distance = float(np.linalg.norm(near - position))
            if index and distance <= max(4.0 * stepover, 2.0 * hop) and position[2] < clearance - 1e-9:
                add(RAPID, near, a0)                   # a short hop between neighbouring lines
            else:
                high = above(start, a0)
                over = np.array([high[0], high[1], max(clearance, position[2])])
                add(RAPID, [position[0], position[1], max(clearance, position[2])], axis_now)
                add(RAPID, over, axis_now)
                add(RAPID, over, a0)
                add(RAPID, high, a0)
                add(RAPID, near, a0)
            add(FEED, start, a0, feeds.plunge_mm_min)
            add(FEED, tips, axis, feeds.feed_mm_min)
            # Out of the cut up the tool's own axis, the rotary axes held, so any turn that follows starts in the
            # air (a turn straight out of a cut would swing the tool through the part: the posts refuse it).
            position = tips[-1] + hop * axis[-1]
            add(RAPID, position, axis[-1])
            axis_now = axis[-1]
        high = above(position, axis_now)
        add(RAPID, high, axis_now)
        add(RAPID, high, up)

        world = [(kind, wcs.from_wcs(pts), wcs.vectors_from_wcs(dirs), f) for kind, pts, dirs, f in sequence]
        all_dirs = np.vstack([d for _, _, d, _ in world])
        abc = solve_abc(all_dirs, ctx.machine, wcs=wcs, previous={a: setup.get(a, 0.0) for a in axes_names})
        if np.isnan(abc).any():
            raise CamJobError(f"{ctx.spec.where}: this mill5's rotary axes cannot tilt the tool to the surface normal of "
                              f"{', '.join(ctx.spec.faces)} within max_tilt_deg {params['max_tilt_deg']:g} (check "
                              "machine.rotary_limits_deg, or lower max_tilt_deg)")
        moves = MoveList(ctx.start, setup_abc, axes_names, op=ctx.index)
        row = 0
        for kind, pts, _, f in sequence:
            moves.polyline(kind, pts, abc[row:row + len(pts)], f=f)
            row += len(pts)
        path = moves.build()

        # Gouge (after the rise) and holder, against the sampled part.
        tips_all = np.vstack([t for t, _ in runs])
        axes_all = np.vstack([a for _, a in runs])
        summary = self.summary(ctx, params)
        found = []
        depth, where = tool_intrusion(cloud, tips_all, axes_all, tool, tolerance=max(0.02, 2 * tol))
        found += intrusion_findings(ctx, summary, depth, wcs.from_wcs(np.nan_to_num(where)) if len(where) else where)
        depth, where = holder_intrusion(cloud, tips_all, axes_all, tool, clearance=max(0.02, 2 * tol))
        found += intrusion_findings(ctx, summary, depth, wcs.from_wcs(np.nan_to_num(where)) if len(where) else where,
                                    check="holder_collision")
        if found:
            ctx.meta.setdefault("findings", []).extend(found)
        tilt = np.degrees(np.arccos(np.clip(axes_all @ up, -1.0, 1.0)))
        ctx.meta.update({"passes": len(runs), "stock_to_leave": leave, "max_tilt_deg": round(float(tilt.max()), 3)})
        notes = []
        if clamped:
            ctx.meta["clamped"] = clamped
            notes.append(f"{clamped} sample(s) held to max_tilt_deg {params['max_tilt_deg']:g}")
        if skipped:
            notes.append(f"{skipped} undercut sample(s) skipped")
        if lifted > tol:
            ctx.meta["lifted_mm"] = round(lifted, 3)
            notes.append(f"rose up to {lifted:.2f} mm off the surface where the part was in the way")
        if notes:
            ctx.meta["note"] = "; ".join(notes)
        return path

"""``helix_bore`` (Helix bore): mill round holes by helical interpolation, posted as G2/G3 arcs with Z.

What it bores: ``faces``: hole walls (cylinders; any face of a hole names the whole hole, ``cadgen cam features``
lists them), opening toward the tool in this setup; or ``holes``: ``[{"center": [x, y], "diameter_mm": d,
"bottom_z": z, "top_z": z}, ...]`` in the setup's WCS (``top_z`` defaults to the part's top). A blind hole is bored
to its bottom (plus ``stock_to_leave_mm``), a through hole to its bottom less ``through_mm`` (default 0).

How: the tool's centre circles at the hole's radius less its own (and the stock to leave); a hole wider than twice
the tool is bored from the inside out, each circle a stepover (default 0.4 of the diameter) bigger, so no core is
left standing. Each circle is a helix from the top of the material down to the bottom at ``pitch_mm`` per turn,
then one flat circle at the bottom; the tool then moves to the hole's centre and leaves. The pitch defaults, per
circle, to 0.2 of the tool's diameter (or ``stepdown_mm``, when given) or less, so the helix at the tool's centre is
no steeper than ``ramp_angle_deg`` (default 3); a ``pitch_mm`` steeper than that on a hole's smallest circle is
refused (``unreachable``, naming the largest pitch allowed). The feed is the table's at the cutting edge: the
centre's feed is scaled by its circle's radius over the edge's (``rho / (rho + r)``), never under a quarter. Climb (counter-clockwise,
G3) by default (``direction``). A tool not smaller than the hole is refused (``tool_too_large``); a hole with no depth
under the material's top is ``empty_operation``.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, PlanError, check_keys, choice, number_list, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation

__all__ = ["HelixBoreOp"]

#: The least share of the feed the tool's centre runs at round an internal arc (a small circle in a big tool).
_ARC_FEED_FLOOR = 0.25


class HelixBoreOp(Operation):
    name = "helix_bore"
    plain = "Helix bore"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("holes", "pitch_mm", "ramp_angle_deg", "through_mm", "direction")
    tool_types = ("flat", "bull", "ball")
    takes_faces = True
    feeds_kind = "rough"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        where = spec.where
        if bool(spec.faces) == ("holes" in extra):
            raise CamJobError(f"{where}: a helix bore needs the hole walls (\"faces\": [\"#o1.f8\"]) or \"holes\" "
                              "([{\"center\": [x, y], \"diameter_mm\": d, \"bottom_z\": z}]), one of them")
        holes = []
        if "holes" in extra:
            raw = extra["holes"]
            if not isinstance(raw, list) or not raw:
                raise CamJobError(f"{where}.holes must be a list like [{{\"center\": [x, y], \"diameter_mm\": 12, "
                                  "\"bottom_z\": -10}]")
            for i, hole in enumerate(raw):
                at = f"{where}.holes[{i}]"
                if not isinstance(hole, dict):
                    raise CamJobError(f"{at} must be {{\"center\": [x, y], \"diameter_mm\": d, \"bottom_z\": z}}")
                check_keys(hole, ("center", "diameter_mm", "bottom_z", "top_z"), at)
                for key in ("center", "diameter_mm", "bottom_z"):
                    if key not in hole:
                        raise CamJobError(f"{at} needs \"{key}\"")
                holes.append({"center": number_list(hole["center"], f"{at}.center", length=2),
                              "diameter_mm": read_number(hole, "diameter_mm", at),
                              "bottom_z": read_number(hole, "bottom_z", at, minimum=-1e6),
                              "top_z": read_number(hole, "top_z", at, minimum=-1e6)})
        return {
            "holes": holes,
            "pitch_mm": read_number(extra, "pitch_mm", where),
            "ramp_angle_deg": read_number(extra, "ramp_angle_deg", where, default=3.0, maximum=45.0),
            "through_mm": read_number(extra, "through_mm", where, default=0.0, minimum=0.0),
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{where}.direction") == "climb",
        }

    def _holes(self, ctx, params):
        from cadgen._internal.cam.operations._milling2d import HoleTarget, hole_targets

        if ctx.spec.faces:
            return hole_targets(ctx, ctx.spec.faces, where=f"{ctx.spec.where}.faces")
        top = ctx.heights.part_top
        return [HoleTarget(ref=f"hole {i + 1}", centre=hole["center"], diameter_mm=hole["diameter_mm"],
                           top_z=hole["top_z"] if hole["top_z"] is not None else top, bottom_z=hole["bottom_z"],
                           hole=True, through=hole["bottom_z"] <= ctx.heights.part_bottom + 1e-6)
                for i, hole in enumerate(params["holes"])]

    def plan(self, ctx, params):
        from cadgen._internal.cam import linking
        from cadgen._internal.cam.operations._milling2d import helix_arcs, lift_and_go

        tool = ctx.tool
        r = tool.radius
        tol = ctx.tolerance_mm
        heights = ctx.heights
        leave = ctx.spec.stock_to_leave_mm
        holes = self._holes(ctx, params)
        stepover = ctx.stepover(0.4)
        feeds = ctx.feeds(self.feeds_kind, stepover_mm=stepover)
        # A step down the job gives caps the default pitch too (the depth one turn takes).
        stepdown = ctx.spec.stepdown_mm if ctx.spec.stepdown_mm is not None else math.inf
        sense = 1.0 if params["climb"] else -1.0     # counter-clockwise for climb round a hole's wall
        b = ctx.builder()
        circles = 0
        turns = 0.0
        pitches: list[float] = []
        holes = linking.order_nearest(holes, b.pos, key=lambda h: h.centre)
        for hole in holes:
            final = hole.diameter_mm / 2.0 - leave - r
            if final <= max(tol, 0.01):
                raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id} ({tool.plain}) is not smaller than "
                                f"the Ø{hole.diameter_mm:g} hole {hole.ref} (less the stock to leave); use a smaller "
                                "tool, or drill it")
            radii = [final]
            while radii[-1] > r * 0.95 + 1e-9:
                radii.append(radii[-1] - stepover)
            radii = [max(rho, min(final, 0.5 * r)) for rho in reversed(radii)]
            radii = sorted(set(round(rho, 6) for rho in radii))
            # Down from the top of the material over the hole: the stock top when it opens on the part's top.
            z_top = heights.stock_top if hole.top_z >= heights.part_top - 1e-6 else hole.top_z
            z_end = hole.bottom_z - params["through_mm"] if hole.through else hole.bottom_z + leave
            if z_end >= z_top - 1e-6:
                raise PlanError("empty_operation", f"{ctx.spec.where}: the hole {hole.ref} has no depth to bore under "
                                f"the material's top in setup '{ctx.setup.id}', so the bore cuts nothing")
            slope = math.tan(math.radians(params["ramp_angle_deg"]))
            steepest = math.floor(2 * math.pi * radii[0] * slope * 1e4) / 1e4
            if params["pitch_mm"] is not None and params["pitch_mm"] > steepest + 1e-9:
                angle = math.degrees(math.atan(params["pitch_mm"] / (2 * math.pi * radii[0])))
                raise PlanError("unreachable", f"{ctx.spec.where}.pitch_mm: {params['pitch_mm']:g} mm per turn round "
                                f"the {2 * radii[0]:.3g} mm circle {tool.id}'s centre runs in {hole.ref} is a "
                                f"{angle:.3g} degree helix, steeper than the {params['ramp_angle_deg']:g} degrees "
                                f"ramp_angle_deg lets the tool go down into material; give pitch_mm {steepest:g} or "
                                "less, or a larger ramp_angle_deg")
            cx, cy = hole.centre
            for k, rho in enumerate(radii):
                pitch = params["pitch_mm"] or max(1e-3, math.floor(min(0.2 * tool.diameter_mm, stepdown,
                                                                        2 * math.pi * rho * slope) * 1e4) / 1e4)
                # The table's feed at the cutting edge: the centre runs a smaller circle than the edge does.
                scale = max(_ARC_FEED_FLOOR, min(1.0, rho / (rho + r)))
                if k == 0:
                    lift_and_go(b, (cx + rho, cy), heights)
                else:
                    # Up the bore just cut, out to the next circle over the top of the material.
                    b.feed(x=cx, y=cy, f=feeds.feed_mm_min)
                    b.rapid(z=min(heights.retract, z_top + 1.0))
                    b.feed(x=cx + rho, y=cy, f=feeds.feed_mm_min)
                b.feed(z=z_top, f=feeds.ramp_mm_min)
                depth = z_top - z_end
                sweep = sense * 2 * math.pi * depth / pitch
                helix_arcs(b, (cx, cy), rho, 0.0, sweep, z_end, f=max(1.0, round(feeds.ramp_mm_min * scale)))
                end_angle = sweep
                helix_arcs(b, (cx, cy), rho, end_angle, sense * 2 * math.pi, z_end,
                           f=max(1.0, round(feeds.feed_mm_min * scale)))
                pitches.append(pitch)
                circles += 1
                turns += depth / pitch
            b.feed(x=cx, y=cy, f=feeds.feed_mm_min)
            b.rapid(z=heights.retract)
        b.rapid(z=heights.clearance)
        ctx.meta.update({"holes": len(holes), "passes": circles, "turns": round(turns, 2),
                         "pitch_mm": round(min(pitches), 4) if pitches else None, "stock_to_leave": leave})
        return b.build()

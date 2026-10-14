"""``thread_mill`` (Thread mill): mill a thread in a hole or on a boss by helical interpolation, posted as arcs.

What it threads: ``faces``: a hole wall (an internal thread in a tap-sized hole: any face of the hole names it) or
the outside of a round boss (an external thread), along the setup's Z. ``thread``: ``internal`` or ``external``
(default: what the face is).

The thread: ``pitch_mm`` (default the tool's); ``major_diameter_mm``, the nominal size. For a hole it defaults to the
tap drill plus the pitch (an ISO metric tap drill is the size less the pitch: Ø5 at 1 mm is M6), snapped to the
nearest 0.5 mm within 0.15; for a boss, the boss's diameter. An internal thread is cut out to the major diameter,
an external one in to the ISO minor diameter (``major - 1.22687 x pitch``). ``depth_mm`` is the thread's length from
the top (default: a through hole's or a boss's whole length, a blind hole's depth less two pitches). ``hand``:
``right`` (default) or ``left``.

How: the tool (a ``thread_mill``) steps in on a tangent half-circle lead from the hole's centre (from outside a
boss), follows a helix of one pitch per turn over the thread's length, and leaves on a half-circle lead. ``form``:
``single`` (default; a single-point tool: the helix covers the whole length) or ``multi`` (a multi-form tool whose
``flute_length_mm`` of teeth covers that much of the thread in each turn: one turn, plus a turn per pitch the
thread is longer than the teeth; it must be the tool's own pitch). ``passes`` (default 1, 2 from 1.5 mm pitch)
splits the thread's depth into radial passes. ``direction`` ``climb`` (default) or ``conventional``: for a right-hand
internal thread, climb runs counter-clockwise from the bottom up; external climb runs clockwise from the top down.
The feed is the table's at the cutting edge, scaled to the tool's centre (slower inside a hole, never under a quarter
of it; faster round a boss).

Refused, as plan errors on the operation: a thread mill not smaller than its hole (``tool_too_large``) and a
``depth_mm`` longer than the hole or down to a blind hole's bottom (``too_deep``). Each internal thread records the
hole it needs made first in ``meta["needs_holes"]`` (``[x, y, z_top, z_bottom, diameter_mm]`` per hole, WCS; z_bottom
is the thread's bottom), for the check that an earlier operation made it.

The modelled hole is the tap drill, so the thread cuts beyond it by design: the ``gouge`` check does not judge this
operation. Drill or bore the hole first.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, PlanError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation

__all__ = ["ThreadMillOp", "nominal_major"]

#: The least share of the feed the tool's centre runs at round an internal arc (a small hole for the tool).
_ARC_FEED_FLOOR = 0.25
#: ISO 68-1: an external thread's minor diameter is ``major - 1.22687 x pitch``.
_EXTERNAL_MINOR = 1.22687


def nominal_major(hole_diameter: float, pitch: float) -> float:
    """The thread size a tap-drill hole is for: the hole plus the pitch, snapped to the nearest 0.5 mm when within
    0.15 mm (Ø5 at 1 mm: M6; Ø6.8 at 1.25: M8; Ø10.2 at 1.75: M12)."""
    size = hole_diameter + pitch
    snapped = round(size * 2.0) / 2.0
    return snapped if abs(snapped - size) <= 0.15 else size


class ThreadMillOp(Operation):
    name = "thread_mill"
    plain = "Thread mill"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("thread", "pitch_mm", "major_diameter_mm", "depth_mm", "hand", "form", "passes", "direction")
    common_keys = ("feed", "speed")
    tool_types = ("thread_mill",)
    takes_faces = True
    feeds_kind = "thread_mill"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if not spec.faces:
            raise CamJobError(f"{spec.where}: a thread mill needs a hole wall or a boss to thread "
                              "(\"faces\": [\"#o1.f7\"]; cadgen cam features lists the holes)")
        extra = spec.extra
        where = spec.where
        tool = ctx.job.tool(spec.tool)
        params = {
            "thread": choice(extra["thread"], ("internal", "external"), f"{where}.thread") if "thread" in extra else None,
            "pitch_mm": read_number(extra, "pitch_mm", where, default=tool.pitch_mm),
            "major_diameter_mm": read_number(extra, "major_diameter_mm", where),
            "depth_mm": read_number(extra, "depth_mm", where),
            "hand": choice(extra.get("hand", "right"), ("right", "left"), f"{where}.hand"),
            "form": choice(extra.get("form", "single"), ("single", "multi"), f"{where}.form"),
            "passes": extra.get("passes"),
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{where}.direction") == "climb",
        }
        passes = params["passes"]
        if passes is not None and (isinstance(passes, bool) or not isinstance(passes, int) or not 1 <= passes <= 10):
            raise CamJobError(f"{where}.passes must be a whole number from 1 to 10 (radial passes)")
        if params["form"] == "multi" and abs(params["pitch_mm"] - tool.pitch_mm) > 1e-6:
            raise CamJobError(f"{where}: a multi-form thread mill cuts only its own pitch ({tool.pitch_mm:g} mm); use "
                              f"form single or a tool with a {params['pitch_mm']:g} mm pitch")
        return params

    def plan(self, ctx, params):
        from cadgen._internal.cam import linking
        from cadgen._internal.cam.operations._milling2d import hole_targets

        tool = ctx.tool
        r = tool.radius
        pitch = params["pitch_mm"]
        targets = hole_targets(ctx, ctx.spec.faces, where=f"{ctx.spec.where}.faces", bosses_ok=True)
        feeds = ctx.feeds(self.feeds_kind)
        b = ctx.builder()
        sizes = []
        needs: list[list[float]] = []
        turns_total = 0.0
        targets = linking.order_nearest(targets, b.pos, key=lambda t: t.centre)
        for target in targets:
            internal = target.hole
            if params["thread"] is not None and (params["thread"] == "internal") != internal:
                raise CamJobError(f"{ctx.spec.where}.thread: {target.ref} is "
                                  f"{'a hole' if internal else 'a boss'}, so its thread is "
                                  f"{'internal' if internal else 'external'}; leave \"thread\" out or name the other face")
            major = params["major_diameter_mm"] or (nominal_major(target.diameter_mm, pitch) if internal
                                                    else target.diameter_mm)
            if internal:
                if major <= target.diameter_mm + 1e-6:
                    raise CamJobError(f"{ctx.spec.where}: an M{major:g} thread is not bigger than the Ø"
                                      f"{target.diameter_mm:g} hole {target.ref}; give major_diameter_mm")
                if tool.diameter_mm >= target.diameter_mm - 1e-6:
                    raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id} ({tool.plain}, "
                                    f"Ø{tool.diameter_mm:g}) does not fit the Ø{target.diameter_mm:g} hole "
                                    f"{target.ref}; a thread mill must be smaller than the hole")
                start_rho, final_rho = target.diameter_mm / 2.0 - r, major / 2.0 - r
            else:
                minor = major - 2.0 * 0.5 * _EXTERNAL_MINOR * pitch
                start_rho, final_rho = target.diameter_mm / 2.0 + r, minor / 2.0 + r
            length = params["depth_mm"]
            full = target.top_z - target.bottom_z
            if length is None:
                length = full if (target.through or not internal) else max(pitch, full - 2.0 * pitch)
            if length > full + 1e-6:
                raise PlanError("too_deep", f"{ctx.spec.where}.depth_mm ({length:g}) is longer than {target.ref} "
                                f"({full:.3g} mm); give a depth_mm of at most {full:.3g}")
            if internal and target.through is False and length > full - 1e-6:
                raise PlanError("too_deep", f"{ctx.spec.where}.depth_mm reaches the bottom of the blind hole "
                                f"{target.ref}; leave room for the tool's tip (a pitch or two)")
            passes = params["passes"] or (2 if pitch >= 1.5 else 1)
            radii = [start_rho + (final_rho - start_rho) * (k + 1) / passes for k in range(passes)]
            if internal:
                # The hole this thread needs made first (the assumes_prepared_hole check reads it), WCS.
                needs.append([round(float(target.centre[0]), 4), round(float(target.centre[1]), 4),
                              round(float(target.top_z), 4), round(float(target.top_z - length), 4),
                              round(float(target.diameter_mm), 4)])
            turns = self._thread(ctx, params, b, target, radii, length, internal, feeds)
            turns_total += turns
            sizes.append(f"M{major:g}x{pitch:g} {'internal' if internal else 'external'}")
        b.rapid(z=ctx.heights.clearance)
        ctx.meta.update({"threads": sizes, "passes": len(targets) * (params["passes"] or (2 if pitch >= 1.5 else 1)),
                         "turns": round(turns_total, 2), "pitch_mm": pitch, "no_gouge_check": True,
                         "note_level": "info",
                         "note": f"mills {', '.join(sorted(set(sizes)))} beyond the modelled hole or boss (not judged "
                                 "by the gouge check)"})
        if needs:
            ctx.meta["needs_holes"] = needs
        return b.build()

    def _thread(self, ctx, params, b, target, radii, length, internal, feeds) -> float:
        """Every radial pass of one thread. Returns the helix turns cut."""
        from cadgen._internal.cam.operations._milling2d import helix_arcs, lift_and_go

        tool = ctx.tool
        r = tool.radius
        pitch = params["pitch_mm"]
        heights = ctx.heights
        cx, cy = target.centre
        # Rotation: climb runs counter-clockwise round a hole's wall, clockwise round a boss.
        ccw = internal == params["climb"]
        # A right-hand thread rises as it turns counter-clockwise (seen from +Z); a left-hand one falls.
        up = ccw == (params["hand"] == "right")
        sense = 1.0 if ccw else -1.0
        z_top = target.top_z
        z_bottom = z_top - length
        if params["form"] == "multi":
            travel = max(pitch, length - tool.flute_length_mm + pitch)
            low, high = z_bottom, min(z_top, z_bottom + travel)
        else:
            low, high = z_bottom, z_top
        travel = high - low
        sweep = sense * 2.0 * math.pi * travel / pitch
        z_start, z_end = (low, high) if up else (high, low)
        lead = 0.5 * r
        turns = 0.0
        for k, rho in enumerate(radii):
            periphery = rho + r if internal else max(1e-3, rho - r)
            scale = rho / periphery
            f = max(1.0, round(feeds.feed_mm_min * (max(_ARC_FEED_FLOOR, scale) if internal else scale)))
            if internal:
                approach = (cx, cy)
                if k == 0:
                    lift_and_go(b, approach, heights)
                b.feed(x=cx, y=cy, f=f)
                b.feed(z=z_start, f=feeds.plunge_mm_min)
                # A half circle from the centre, tangent to the helix where it meets it.
                b.arc(cx + rho, cy, z_start, centre=(cx + rho / 2.0, cy, 0.0), clockwise=not ccw, f=f)
            else:
                # Down beside the boss, a lead's width clear of it, by the retract plane (never across the boss).
                outside = (cx + rho + 2.0 * lead, cy)
                lift_and_go(b, outside, heights)
                b.feed(z=z_start, f=feeds.plunge_mm_min)
                b.arc(cx + rho, cy, z_start, centre=(cx + rho + lead, cy, 0.0), clockwise=ccw, f=f)
            helix_arcs(b, (cx, cy), rho, 0.0, sweep, z_end, f=f)
            turns += abs(sweep) / (2.0 * math.pi)
            ex, ey = cx + rho * math.cos(sweep), cy + rho * math.sin(sweep)
            if internal:
                b.arc(cx, cy, z_end, centre=((cx + ex) / 2.0, (cy + ey) / 2.0, 0.0), clockwise=not ccw, f=f)
            else:
                ux, uy = math.cos(sweep), math.sin(sweep)
                b.arc(ex + 2.0 * lead * ux, ey + 2.0 * lead * uy, z_end,
                      centre=(ex + lead * ux, ey + lead * uy, 0.0), clockwise=ccw, f=f)
        b.rapid(z=heights.retract)
        return turns

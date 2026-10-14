"""``turn_thread``: single-point thread a cylinder, outside (``side: "od"``) or in a bore (``"id"``), in passes of
decreasing depth.

Which thread: ``faces`` names the threaded cylinder (an outside thread's major diameter, a bore's minor diameter):
the thread runs along it, from its front end back to its back end. Without a face, give ``z_start_mm`` (the
thread's front end), ``z_end_mm`` (its back end) and ``major_diameter_mm`` (od) or ``minor_diameter_mm`` (id).

Own keys: ``side`` (``od``/``id``), ``pitch_mm`` (default the tool's), ``major_diameter_mm``, ``minor_diameter_mm``,
``depth_mm`` (radial; default the ISO 60° basic depth, 0.6134 x pitch outside, 0.5413 x pitch in a bore, or half the
difference of the diameters given), ``z_start_mm``, ``z_end_mm``, ``lead_in_mm`` (run-up in front of the thread so
the axis is up to speed; default three pitches, at least 2 mm), ``infeed`` (``flank``, the default: each pass shifts
along the trailing flank at 29.5° so only the leading edge cuts; ``radial``; ``alternate``: flanks in turn),
``passes`` (cutting passes; default from ``first_depth_mm``), ``first_depth_mm`` (default 0.3 or a third of the
depth), ``min_depth_mm`` (the smallest a pass may take; default 0.03), ``spring_passes`` (at full depth; default 1).
A thread runs at a constant rpm (the job's ``speed`` sets it), its feed one pitch a revolution.

Each pass's depth is the thread's depth times the square root of its share (equal chip area a pass). The toolpath
carries a ``thread`` cycle event (G76's numbers, and every pass) so a post emits G76, or G32/G33 passes; the
expansion's threading moves are spindle-synchronised and must never be posted as plain feeds. The stock simulator
does not cut the helical groove (it is not a body of revolution); the run checks the thread can run out into a
groove or past the part's end rather than into a shoulder.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, choice, read_number
from cadgen._internal.cam.operations._turning import BIG, TurnOperation, lathe

__all__ = ["TurnThreadOp", "thread_depths"]

INFEEDS = ("flank", "radial", "alternate")
FLANK_DEG = 29.5


class TurnThreadOp(TurnOperation):
    name = "turn_thread"
    plain = "Thread"
    keys = ("side", "pitch_mm", "major_diameter_mm", "minor_diameter_mm", "depth_mm", "z_start_mm", "z_end_mm",
            "lead_in_mm", "infeed", "passes", "first_depth_mm", "min_depth_mm", "spring_passes")
    common_keys = ("speed",)
    tool_types = ("thread",)
    takes_faces = True
    feeds_kind = "thread"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        extra, where = spec.extra, spec.where
        for key in ("passes", "spring_passes"):
            value = extra.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 60
                                      or (key == "passes" and value < 1)):
                raise CamJobError(f"{where}.{key} must be a whole number ({'1' if key == 'passes' else '0'} to 60)")
        params.update(
            side=self.side(spec), pitch_mm=read_number(extra, "pitch_mm", where),
            major_diameter_mm=read_number(extra, "major_diameter_mm", where),
            minor_diameter_mm=read_number(extra, "minor_diameter_mm", where),
            depth_mm=read_number(extra, "depth_mm", where),
            z_start_mm=read_number(extra, "z_start_mm", where, minimum=-1e6),
            z_end_mm=read_number(extra, "z_end_mm", where, minimum=-1e6),
            lead_in_mm=read_number(extra, "lead_in_mm", where, minimum=0.0),
            infeed=choice(extra.get("infeed", "flank"), INFEEDS, f"{where}.infeed"),
            passes=extra.get("passes"), first_depth_mm=read_number(extra, "first_depth_mm", where),
            min_depth_mm=read_number(extra, "min_depth_mm", where, default=0.03),
            spring_passes=extra.get("spring_passes", 1),
        )
        tool = ctx.job.tool(spec.tool)
        if not (params["pitch_mm"] or tool.pitch_mm):
            raise CamJobError(f"{where}: a thread needs its pitch: pitch_mm on the operation or on {tool.id}")
        if not spec.faces and (params["z_start_mm"] is None or params["z_end_mm"] is None):
            raise CamJobError(f"{where}: name the threaded cylinder (faces: [\"#o1.f4\"]) or give z_start_mm and "
                              "z_end_mm with its diameter")
        if params["z_start_mm"] is not None and params["z_end_mm"] is not None \
                and params["z_end_mm"] >= params["z_start_mm"]:
            raise CamJobError(f"{where}: z_end_mm must be behind z_start_mm (towards the chuck, smaller Z)")
        return params

    def plan(self, ctx, params):
        lt = lathe(ctx)
        tool = ctx.tool
        inside = params["side"] == "id"
        pitch = params["pitch_mm"] or tool.pitch_mm
        crest, z_high, z_low = _where(ctx, lt, params, inside)
        if params["depth_mm"]:
            depth = params["depth_mm"]
        elif not inside and params["minor_diameter_mm"] and crest:
            depth = crest - params["minor_diameter_mm"] / 2.0
        elif inside and params["major_diameter_mm"] and crest:
            depth = params["major_diameter_mm"] / 2.0 - crest
        else:
            depth = (0.5413 if inside else 0.6134) * pitch
        if depth <= 0:
            raise CamJobError(f"{ctx.spec.where}: the thread's depth comes out at {depth:.3g} mm; check its diameters")
        root = crest + depth if inside else crest - depth
        flank = depth * math.tan(math.radians(30.0))
        p = lt.profile
        # The thread must run out into a groove or off the part, not into a shoulder.
        probe = [z_low - flank - 0.3 + 0.05 * k for k in range(int((flank + 0.3) / 0.05) + 1)]
        if not inside:
            beyond = p.r_out(probe)
            blocked = beyond[beyond == beyond]
            if len(blocked) and float(blocked.max()) > root + 0.05:
                raise CamJobError(f"{ctx.spec.where}: the thread runs into a shoulder at Z{z_low:.4g}; end it short "
                                  "(z_end_mm) or give it a relief groove to run out into")
        else:
            beyond = p.r_in(probe)
            if len(beyond) and float(beyond.min()) < root - 0.05:
                raise CamJobError(f"{ctx.spec.where}: the thread runs into the bore's end at Z{z_low:.4g}; end it "
                                  "short (z_end_mm) or give it an undercut to run out into")
        lead_in = params["lead_in_mm"] if params["lead_in_mm"] is not None else max(2.0, 3.0 * pitch)
        z_start = z_high + lead_in
        if not inside:
            # The insert runs up from the front at the crest: everything there must already be turned down to it.
            standing = lt.top(z_low, BIG)
            if standing is not None and standing > crest + 0.05:
                raise CamJobError(f"{ctx.spec.where}: material stands at Ø{2 * standing:.4g} in front of or on the "
                                  f"thread (Ø{2 * crest:.4g} at Z{z_high:.4g}..{z_low:.4g}); turn it to the thread's "
                                  "diameter first (turn_rough, turn_finish), or thread from the other end")
            x_clear = crest + 1.0
        else:
            hole = lt.hole(z_low, BIG)
            if hole >= BIG or hole < 0.5:
                raise CamJobError(f"{ctx.spec.where}: an inside thread needs its bore open first (turn_drill, "
                                  "turn_rough side id)")
            x_clear = max(0.0, min(crest, hole) - 1.0)
        depths = thread_depths(depth, passes=params["passes"], first=params["first_depth_mm"],
                               minimum=params["min_depth_mm"])
        shifts = _shifts(depths, params["infeed"], depth)
        spring = int(params["spring_passes"])
        sign = 1.0 if inside else -1.0
        passes = [(crest + sign * d, z_start + s) for d, s in zip(depths, shifts)]
        passes += [passes[-1]] * spring
        feeds = lt.feeds("thread", 2.0 * crest, params, pitch_mm=pitch)
        f = feeds.feed_mm_min
        role = "thread_id" if inside else "thread"
        ctx.meta["lathe"] = {"role": role}
        b = lt.builder()
        lt.begin(b)
        b.rapid(x=x_clear)
        b.rapid(z=z_start)
        cycle = b.begin_cycle(
            cycle="thread", external=not inside, z_start=round(z_start, 4), z_end=round(z_low, 4),
            x_clear=round(x_clear, 4), x_crest=round(crest, 4), depth_mm=round(depth, 4), pitch_mm=pitch,
            first_depth_mm=round(depths[0], 4), min_depth_mm=params["min_depth_mm"],
            finish_mm=round(depths[-1] - (depths[-2] if len(depths) > 1 else 0.0), 4), spring_passes=spring,
            infeed=params["infeed"], infeed_deg=0.0 if params["infeed"] == "radial" else FLANK_DEG, angle_deg=60.0,
            taper_mm=0.0, passes=len(depths), rpm=feeds.rpm, feed=f,
            pass_list=[[round(x, 4), round(z, 4)] for x, z in passes])
        for x, z in passes:
            b.rapid(z=z)
            b.rapid(x=x)
            b.feed(z=z_low, f=f)
            b.rapid(x=x_clear)
            b.rapid(z=z_start)
        b.end_cycle(cycle)
        major = crest if not inside else crest + depth
        whole = abs(2 * major - round(2 * major)) < 1e-6
        name = f"M{2 * major:g}x{pitch:g}" if whole else f"Ø{2 * major:.4g}x{pitch:g}"
        ctx.meta.update({"passes": len(passes), "what": f"{name} {'inside' if inside else 'outside'} "
                         f"Z{z_high:.4g}..{z_low:.4g}", "depth_mm": round(depth, 4), "pitch_mm": pitch,
                         "bottom_z": round(z_low, 4)})
        if inside:
            b.rapid(z=lt.z_clear)
        lt.home(b)
        return b.build()


def thread_depths(depth: float, *, passes=None, first=None, minimum: float = 0.03) -> list[float]:
    """Cumulative radial depths, one a cutting pass, the last the full depth: ``depth x sqrt(k / n)`` (an even chip
    area a pass), no pass taking less than ``minimum``."""
    if passes is None:
        first = first or min(0.3, depth / 3.0)
        passes = max(3, min(40, int(math.ceil((depth / first) ** 2))))
    out: list[float] = []
    for k in range(1, int(passes) + 1):
        d = depth * math.sqrt(k / passes)
        if out and d - out[-1] < minimum and k < passes:
            continue
        if out and d - out[-1] < minimum:
            out[-1] = depth
            continue
        out.append(d)
    out[-1] = depth
    return out


def _shifts(depths, infeed: str, depth: float) -> list[float]:
    """Each pass's start shift along Z: the trailing flank at 29.5° (towards the chuck as it goes deeper)."""
    t = math.tan(math.radians(FLANK_DEG))
    if infeed == "radial":
        return [0.0] * len(depths)
    if infeed == "flank":
        return [-d * t for d in depths]
    out = []
    for k, d in enumerate(depths):
        room = (depth - d) * math.tan(math.radians(30.0))
        out.append(0.0 if k == len(depths) - 1 else (-1.0 if k % 2 == 0 else 1.0) * min(d * t / 2.0, room))
    return out


def _where(ctx, lt, params, inside: bool) -> tuple[float, float, float]:
    """``(crest radius, front z, back z)`` of the thread in WCS."""
    import numpy as np

    crest = None
    z_high = params["z_start_mm"]
    z_low = params["z_end_mm"]
    if ctx.spec.faces:
        if len(ctx.spec.faces) != 1:
            raise CamJobError(f"{ctx.spec.where}.faces: name one threaded cylinder per turn_thread")
        ref = ctx.spec.faces[0]
        info = ctx.face(ref)
        if info.surface != "cylinder" or info.axis is None:
            raise CamJobError(f"{ctx.spec.where}.faces: {ref} is a {info.surface}; a thread runs along a cylinder")
        axis = np.asarray(ctx.wcs.vectors_to_wcs([info.axis])[0])
        if abs(abs(axis[2]) - 1.0) > 1e-6:
            raise CamJobError(f"{ctx.spec.where}.faces: {ref} does not run along the spindle axis")
        if bool(info.hole) != inside:
            raise CamJobError(f"{ctx.spec.where}.faces: {ref} is {'a bore' if info.hole else 'an outside cylinder'}; "
                              f"set side to \"{'id' if info.hole else 'od'}\"")
        crest = info.radius_mm
        low, high = info.bounds
        corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
        zs = ctx.wcs.to_wcs(corners)[:, 2]
        z_high = float(zs.max()) if z_high is None else z_high
        z_low = float(zs.min()) if z_low is None else z_low
    if not inside and params["major_diameter_mm"]:
        crest = params["major_diameter_mm"] / 2.0
    if inside and params["minor_diameter_mm"]:
        crest = params["minor_diameter_mm"] / 2.0
    if crest is None:
        raise CamJobError(f"{ctx.spec.where}: give the thread's {'minor' if inside else 'major'}_diameter_mm (or name "
                          "its cylinder in faces)")
    return float(crest), float(z_high), float(z_low)

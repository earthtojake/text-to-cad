"""Feeds and speeds: a material table and the rules that turn it into a spindle speed and a feed for one tool.

**Every number here is a starting point, and the Results say so.** They are deliberately on the conservative side of
the ranges tool vendors publish for carbide end mills on a rigid hobby-to-light-industrial machine (Harvey/Helical,
Kennametal, Sandvik and Onsrud catalogue tables, which give surface speed per material and chip load per tooth
against diameter): aluminium 6061 is published at roughly 300-1000 m/min and 0.025-0.08 mm/tooth at 6 mm, so the
table says 250 m/min and 0.04 mm; 1018 steel at roughly 100-200 m/min and 0.02-0.05 mm, so 120 and 0.03; stainless
304 at 60-120 m/min, so 80; titanium Ti-6Al-4V at 40-70 m/min, so 50; plastics and woods at the low end of a router
chart's chip loads. High-speed steel runs at about a third of carbide's surface speed. A job's ``feed``/``speed``
override wins over all of it; a machine's ``max_rpm``/``max_feed_mm_min`` clamps it (and its ``min_rpm`` raises a
slower speed), and a clamp is reported.

The rules (:func:`for_op`):

* spindle ``rpm = 1000 * Vc / (pi * D)``, scaled per operation (drills 0.6, spot 0.8, reamers 0.5, taps 0.06 (an
  HSS tap's speed, at most 1000 rpm), thread mills 0.8), rounded to 10 rpm, then held to the machine's maximum
  (a whole rpm at or under ``max_rpm``: the rounding never lifts it past);
* milling feed ``= rpm * flutes * fz``, with ``fz`` the table's chip load at 6 mm scaled along
  :data:`CHIPLOAD_CURVE` by the diameter (interpolated between its diameters, in proportion to the diameter under
  1 mm so a 0.5 mm cutter takes half a 1 mm one's chip, held past 20 mm); a full-width slot takes 0.75x, an
  engraver and a thread mill (its whole thread form is in the cut) 0.5x; a light radial stepover gets radial chip
  thinning ``D / (2 sqrt(D ae - ae^2))``, capped at 2x;
* drilling feed ``= rpm * f``, ``f`` per revolution proportional to the diameter; tapping ``= rpm * pitch`` exactly,
  and a tap the machine's feed limit slows turns a whole rpm (``floor(max_feed / pitch)``) so the two still agree;
* plunge at 0.3x the feed worked out from the plain chip load (chip thinning is a side cut's: a plunge takes a
  full-width chip whatever the stepover) and ramp at 0.5x the milling feed; the default step down is a fraction of
  the diameter per material (half the diameter in aluminium, a quarter in steel).

A material is a table row by name (or an alias, :data:`MATERIAL_ALIASES`), a table row with some of its numbers
overridden by the job, or the job's own numbers. A job's chip load is one number for every tool, or one per tool
diameter (``{"3": 0.02, "6": 0.04}``) interpolated the way the curve is. An operation's ``feed``/``speed``/``plunge``
override wins over the computed numbers and is still held to the machine's limits.

Cutting processes (laser, plasma, waterjet) have a speed table per material and thickness (:func:`for_cut`), also
starting points: a 1-2 kW fibre laser, a 45 A air plasma, a 50 hp abrasive waterjet. Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

__all__ = ["CHIPLOAD_CURVE", "CUT_SPEEDS", "Feeds", "MATERIALS", "MATERIAL_ALIASES", "OP_KINDS", "chipload_at",
           "default_stepdown", "for_cut", "for_op"]

#: Per material: plain name, carbide surface speed (m/min), carbide chip load per tooth at 6 mm (mm), drill feed per
#: revolution per mm of diameter (mm/rev/mm), and the default step down as a fraction of the diameter.
MATERIALS: dict[str, dict] = {
    "aluminum-6061": {"plain": "aluminium 6061", "vc": 250.0, "fz6": 0.040, "drill": 0.020, "stepdown": 0.5},
    "aluminum-7075": {"plain": "aluminium 7075", "vc": 220.0, "fz6": 0.040, "drill": 0.020, "stepdown": 0.5},
    "steel-1018": {"plain": "mild steel 1018", "vc": 120.0, "fz6": 0.030, "drill": 0.015, "stepdown": 0.25},
    "stainless-304": {"plain": "stainless 304", "vc": 80.0, "fz6": 0.025, "drill": 0.012, "stepdown": 0.2},
    "tool-steel": {"plain": "tool steel (annealed)", "vc": 70.0, "fz6": 0.020, "drill": 0.010, "stepdown": 0.15},
    "titanium-6al4v": {"plain": "titanium Ti-6Al-4V", "vc": 50.0, "fz6": 0.025, "drill": 0.010, "stepdown": 0.15},
    "brass": {"plain": "brass", "vc": 200.0, "fz6": 0.050, "drill": 0.025, "stepdown": 0.5},
    "copper": {"plain": "copper", "vc": 150.0, "fz6": 0.035, "drill": 0.020, "stepdown": 0.3},
    "delrin": {"plain": "Delrin (acetal)", "vc": 300.0, "fz6": 0.080, "drill": 0.030, "stepdown": 0.75},
    "acrylic": {"plain": "acrylic", "vc": 250.0, "fz6": 0.060, "drill": 0.025, "stepdown": 0.5},
    "hdpe": {"plain": "HDPE", "vc": 300.0, "fz6": 0.100, "drill": 0.040, "stepdown": 1.0},
    "nylon": {"plain": "nylon", "vc": 250.0, "fz6": 0.080, "drill": 0.030, "stepdown": 0.75},
    "mdf": {"plain": "MDF", "vc": 400.0, "fz6": 0.100, "drill": 0.040, "stepdown": 1.0},
    "hardwood": {"plain": "hardwood", "vc": 400.0, "fz6": 0.080, "drill": 0.030, "stepdown": 0.75},
    "plywood": {"plain": "plywood", "vc": 400.0, "fz6": 0.090, "drill": 0.030, "stepdown": 0.75},
    "carbon-fiber": {"plain": "carbon fibre", "vc": 150.0, "fz6": 0.030, "drill": 0.010, "stepdown": 0.25},
    "foam": {"plain": "foam", "vc": 500.0, "fz6": 0.200, "drill": 0.050, "stepdown": 2.0},
}
#: Other names a job may give a table material: the job's material then is the canonical row, by its own name.
MATERIAL_ALIASES: dict[str, str] = {"mild-steel": "steel-1018", "acetal": "delrin"}

#: The chip load per tooth against the tool's diameter (mm), as a multiple of the table's 6 mm number. Its shape is
#: the vendors' charts' (Harvey/Helical, Kennametal: chip load grows about in proportion to the diameter, then flattens
#: as the cutter's rigidity, not its size, sets the chip): the median of a dozen materials' published rows, held to
#: the lower side. Under the first diameter it falls in proportion (a 0.5 mm cutter takes half a 1 mm one's chip);
#: past the last it holds rather than extrapolating.
CHIPLOAD_CURVE: tuple[tuple[float, float], ...] = (
    (1.0, 0.2), (3.0, 0.5), (6.0, 1.0), (10.0, 1.5), (12.0, 1.75), (20.0, 2.5))

#: The operation kinds the rules know: what a planner asks feeds for.
OP_KINDS = ("rough", "slot", "finish", "face", "drill", "spot", "ream", "bore", "tap", "thread_mill", "engrave")
_RPM_SCALE = {"drill": 0.6, "spot": 0.8, "ream": 0.5, "bore": 0.7, "tap": 0.06, "thread_mill": 0.8, "engrave": 1.0}
#: A tap is fed at rpm x pitch, so its spindle stays slow whatever the table says: a floating holder or a hobby
#: spindle reversing at the hole's bottom overshoots past this.
_TAP_MAX_RPM = 1000.0
_HSS = 0.35
#: Spindle speed when the job's material table cannot set one (a lathe or cutting tool asks for_cut instead).
_FALLBACK_RPM = 10000.0


@dataclass(frozen=True)
class Feeds:
    """What a planner cuts at. ``clamped`` names each limit the machine imposed; ``source`` says whether the numbers
    are the table's (``table``), the job's (``job``) or both (``mixed``)."""

    rpm: float
    feed_mm_min: float
    plunge_mm_min: float
    ramp_mm_min: float
    chipload_mm: float | None
    surface_m_min: float | None
    clamped: tuple[str, ...] = ()
    source: str = "table"
    note: str = "a starting point: adjust to the machine, the tool and what you hear"
    #: A lathe's: constant surface speed (m/min; None at a constant rpm), its rpm clamp, and the feed per revolution
    #: (``feed_mm_min`` is it times ``rpm``, the speed the times assume). :func:`for_turn` sets them.
    css_m_min: float | None = None
    max_rpm: float | None = None
    feed_mm_rev: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def chipload_at(bands, diameter_mm: float) -> float:
    """A value of ``bands`` (``((diameter mm, value), ...)``, smallest first) at a tool diameter: interpolated
    linearly between two diameters, in proportion to the diameter under the first, held past the last."""
    first_d, first_v = bands[0]
    if diameter_mm <= first_d:
        return first_v * diameter_mm / first_d
    for (d0, v0), (d1, v1) in zip(bands, bands[1:]):
        if diameter_mm <= d1:
            return v0 + (v1 - v0) * (diameter_mm - d0) / (d1 - d0)
    return bands[-1][1]


def _material_numbers(material) -> dict:
    """The material's numbers: its table row (by name) with the job's overrides, or the job's own."""
    if material.table:
        numbers = dict(MATERIALS[material.name])
    else:
        numbers = {"plain": material.plain, "vc": None, "fz6": None, "drill": None, "stepdown": 0.5}
    if material.surface_m_min is not None:
        numbers["vc"] = material.surface_m_min
    # One chip load is the 6 mm tool's, as the table's is (scaled along the curve); one per diameter is the job's own.
    if isinstance(material.chipload_mm, (int, float)):
        numbers["fz6"] = float(material.chipload_mm)
    elif material.chipload_mm is not None:
        numbers["chipload"] = material.chipload_mm
    if material.drill_mm_per_rev is not None:
        numbers["drill"] = material.drill_mm_per_rev
    if material.stepdown_fraction is not None:
        numbers["stepdown"] = material.stepdown_fraction
    return numbers


def _chipload(numbers: dict, diameter: float) -> float:
    """The chip load per tooth for a cutter of ``diameter``: the job's per diameter (interpolated), else the 6 mm
    number (the table's or the job's) along :data:`CHIPLOAD_CURVE`."""
    stated = numbers.get("chipload")
    if stated is None:
        return numbers["fz6"] * chipload_at(CHIPLOAD_CURVE, diameter)
    return chipload_at(stated, diameter)


def default_stepdown(material, tool) -> float:
    """The default axial step for roughing: the material's fraction of the diameter, never past the flutes."""
    numbers = _material_numbers(material)
    return max(0.05, min(tool.flute_length_mm or math.inf, numbers["stepdown"] * tool.diameter_mm))


def _chip_thinning(diameter: float, stepover_mm: float | None) -> float:
    if not stepover_mm or stepover_mm >= diameter / 2.0:
        return 1.0
    engaged = math.sqrt(max(1e-12, diameter * stepover_mm - stepover_mm ** 2))
    return min(2.0, diameter / (2.0 * engaged))


def _round_rpm(rpm: float) -> float:
    return float(max(10.0, round(rpm / 10.0) * 10.0))


#: The hole makers' feeds kinds: a speed raised past the table burns their point first.
HOLE_KINDS = ("drill", "spot", "ream", "bore")
#: How far past the table's surface speed a machine's slowest spindle speed may raise a hole maker, or any tool in a
#: metal, before the plan refuses it.
RAISE_LIMIT = 1.3


def for_op(material, tool, kind: str, machine, *, stepover_mm: float | None = None, feed: float | None = None,
           speed: float | None = None, plunge: float | None = None) -> Feeds:
    """The spindle speed and feeds for ``tool`` doing an operation of ``kind`` (:data:`OP_KINDS`) in ``material`` on
    ``machine``; ``feed``/``speed``/``plunge`` are the job's overrides (mm/min, rpm, mm/min). A tap's plunge is its
    feed, rpm x pitch, whatever ``plunge`` says."""
    if kind not in OP_KINDS:
        raise ValueError(f"unknown feeds kind {kind!r}; one of {', '.join(OP_KINDS)}")
    numbers = _material_numbers(material)
    diameter = max(tool.diameter_mm, 0.1)
    # Taps: the scale is already an HSS tap's surface speed (about 15 m/min in 6061, 7 in mild steel, 5 in 304),
    # whatever the tool's material says (tools default to carbide; few taps are).
    if kind == "tap":
        vc = numbers["vc"] * _RPM_SCALE["tap"]
    else:
        vc = numbers["vc"] * (_HSS if tool.material == "hss" else 1.0) * _RPM_SCALE.get(kind, 1.0)
    clamped: list[str] = []
    rpm = float(speed) if speed is not None else 1000.0 * vc / (math.pi * diameter)
    if kind == "tap" and speed is None:
        rpm = min(rpm, _TAP_MAX_RPM)
    if speed is None:
        rpm = _round_rpm(rpm)
    # Held after the rounding, to a whole rpm the machine can turn: rounding never lifts it past max_rpm.
    if machine.max_rpm is not None and rpm > machine.max_rpm:
        limit = float(math.floor(machine.max_rpm))
        clamped.append(f"spindle {rpm:.0f} rpm clamped to the machine's {limit:.0f} rpm")
        rpm = limit
    # A spindle cannot turn slower than its slowest (a router's): raised to it, the feed with it (the chip load kept,
    # the surface speed past the table's), and said. Never a tap (its feed is rpm x pitch: a router spindle cannot tap),
    # and not far past the table for a hole maker or in a metal, where that speed burns the tool.
    slowest = machine.min_rpm
    if slowest is not None and rpm < slowest:
        from cadgen._internal.cam.job_errors import CamJobError

        floor = float(math.ceil(slowest))
        if kind == "tap":
            raise CamJobError(f"{tool.id} ({tool.plain}) taps at about {rpm:.0f} rpm, but this machine's spindle turns "
                              f"no slower than {floor:.0f} rpm (machine.min_rpm): no tap runs that fast. Mill the "
                              "thread (thread_mill) or tap it by hand")
        metal = not material.table or material.name in METALS
        if speed is None and floor > RAISE_LIMIT * rpm and (kind in HOLE_KINDS or metal):
            smaller = ("mill the hole with a smaller end mill (circular)" if kind in HOLE_KINDS
                       else "use a smaller tool (it wants more rpm)")
            raise CamJobError(f"{tool.id} ({tool.plain}) wants about {rpm:.0f} rpm in {numbers['plain']}, but this "
                              f"machine's spindle turns no slower than {floor:.0f} rpm (machine.min_rpm): "
                              f"{floor / rpm:.1f} times the surface speed burns it. {smaller.capitalize()}, use a "
                              "machine whose spindle turns slower, or state the operation's speed where the tool "
                              "maker's chart allows it")
        clamped.append(f"spindle {rpm:.0f} rpm raised to the machine's slowest, {floor:.0f} rpm (a faster surface "
                       "speed than the table's)")
        rpm = floor
    chipload = None
    if kind == "tap":
        cut = rpm * tool.pitch_mm
        plunge_f = cut
    elif kind in ("drill", "spot", "ream", "bore"):
        per_rev = (numbers["drill"] * diameter if numbers.get("drill") is not None
                   else 2.0 * _chipload(numbers, diameter))
        if kind == "ream":
            per_rev *= 2.0
        if kind == "spot":
            per_rev *= 0.5
        if tool.material == "hss":
            per_rev *= 0.8
        chipload = per_rev
        cut = rpm * per_rev
        plunge_f = cut
    else:
        fz = _chipload(numbers, diameter)
        if kind == "slot":
            fz *= 0.75
        if kind in ("engrave", "thread_mill"):
            fz *= 0.5
        # A plunge takes a full-width chip whatever the stepover: it is worked out before the thinning.
        plunge_f = 0.3 * rpm * max(1, tool.flutes) * fz
        fz *= _chip_thinning(diameter, stepover_mm)
        chipload = fz
        cut = rpm * max(1, tool.flutes) * fz
    ramp = 0.5 * cut if kind not in ("drill", "spot", "ream", "bore", "tap") else cut
    if feed is not None:
        scale = float(feed) / cut if cut > 0 else 1.0
        cut, plunge_f, ramp = float(feed), plunge_f * scale, ramp * scale
    if plunge is not None and kind != "tap":
        plunge_f = float(plunge)
    limit = machine.max_feed_mm_min
    if limit is not None and kind == "tap" and cut > limit:
        slower = float(math.floor(limit / tool.pitch_mm))
        if slower < 1:
            from cadgen._internal.cam.job_errors import CamJobError

            raise CamJobError(f"a {tool.pitch_mm:g} mm pitch tap feeds {tool.pitch_mm:g} mm/min at 1 rpm, more than "
                              f"the machine's {limit:g} mm/min; raise machine.max_feed_mm_min")
        clamped.append(f"a tap must feed at rpm x pitch ({cut:.0f} mm/min), more than the machine's {limit:.0f} "
                       f"mm/min: the spindle was slowed to {slower:.0f} rpm to match")
        rpm = slower
        cut = plunge_f = ramp = rpm * tool.pitch_mm
    elif limit is not None:
        if cut > limit:
            clamped.append(f"feed {cut:.0f} mm/min clamped to the machine's {limit:.0f} mm/min")
            ratio = limit / cut
            cut, ramp = limit, ramp * ratio
            if plunge is None:
                plunge_f *= ratio
        if plunge_f > limit:
            clamped.append(f"plunge {plunge_f:.0f} mm/min clamped to the machine's {limit:.0f} mm/min")
            plunge_f = limit
    given = [v is not None for v in (feed, speed, plunge)]
    source = "job" if (feed is not None and speed is not None) else "mixed" if any(given) else "table"
    if kind != "tap":
        cut, plunge_f, ramp = (float(max(1.0, round(v))) for v in (cut, plunge_f, ramp))
    return Feeds(rpm=round(rpm, 3), feed_mm_min=round(cut, 3), plunge_mm_min=round(plunge_f, 3),
                 ramp_mm_min=round(ramp, 3), chipload_mm=None if chipload is None else round(chipload, 5),
                 surface_m_min=round(math.pi * diameter * rpm / 1000.0, 1), clamped=tuple(clamped), source=source)


#: Cutting speed (mm/min) against thickness (mm), per process and material: starting points for a 1-2 kW fibre
#: laser (a CO2 for the non-metals), a 45 A air plasma and a 50 hp abrasive waterjet, interpolated log-linearly.
CUT_SPEEDS: dict[str, dict[str, tuple[tuple[float, float], ...]]] = {
    "laser": {
        "steel-1018": ((1.0, 10000.0), (3.0, 3000.0), (6.0, 1200.0), (10.0, 600.0)),
        "stainless-304": ((1.0, 9000.0), (3.0, 2000.0), (6.0, 700.0)),
        "aluminum-6061": ((1.0, 8000.0), (3.0, 1500.0), (6.0, 500.0)),
        "acrylic": ((3.0, 1500.0), (6.0, 600.0), (10.0, 300.0)),
        "plywood": ((3.0, 1200.0), (6.0, 500.0)),
        "mdf": ((3.0, 1100.0), (6.0, 450.0)),
        "hardwood": ((3.0, 900.0), (6.0, 400.0)),
    },
    "plasma": {
        "steel-1018": ((1.5, 6000.0), (3.0, 3500.0), (6.0, 1800.0), (10.0, 900.0), (16.0, 450.0)),
        "stainless-304": ((1.5, 5000.0), (3.0, 2800.0), (6.0, 1300.0), (10.0, 650.0)),
        "aluminum-6061": ((1.5, 6500.0), (3.0, 4000.0), (6.0, 2000.0), (10.0, 1000.0)),
    },
    "waterjet": {
        "steel-1018": ((3.0, 600.0), (6.0, 300.0), (12.0, 140.0), (25.0, 60.0)),
        "stainless-304": ((3.0, 500.0), (6.0, 250.0), (12.0, 110.0)),
        "aluminum-6061": ((3.0, 1400.0), (6.0, 700.0), (12.0, 330.0), (25.0, 150.0)),
        "titanium-6al4v": ((3.0, 450.0), (6.0, 220.0), (12.0, 100.0)),
        "acrylic": ((3.0, 2500.0), (6.0, 1300.0), (12.0, 600.0)),
        "carbon-fiber": ((3.0, 1500.0), (6.0, 700.0)),
    },
}


def for_cut(material, process: str, thickness_mm: float) -> float | None:
    """A starting cutting speed (mm/min) for ``process`` through ``thickness_mm`` of ``material``, or ``None`` when
    the table has no row for it (the job then names its own ``feed``)."""
    rows = CUT_SPEEDS.get(process, {}).get(getattr(material, "name", material))
    if not rows or thickness_mm <= 0:
        return None
    xs = [math.log(t) for t, _ in rows]
    ys = [math.log(v) for _, v in rows]
    x = math.log(thickness_mm)
    if x <= xs[0]:
        return float(round(math.exp(ys[0])))
    if x >= xs[-1]:
        # Past the table: the last row's slope carries on, which is conservative (speed falls with thickness).
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2]) if len(xs) > 1 else -1.0
        return float(round(math.exp(ys[-1] + slope * (x - xs[-1]))))
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            f = (x - xs[i]) / (xs[i + 1] - xs[i])
            return float(round(math.exp(ys[i] + f * (ys[i + 1] - ys[i]))))
    return None


# --- cutting processes per machine (the ``cut`` and ``wire_edm`` operations) -----------------------------------
#
# Starting points again, for a sane first program: the rows of CUT_SPEEDS (and CUT_SPEEDS_EXTRA) are for a reference
# machine, and :func:`cut_feeds` scales them to the job's machine:
#
# * laser: metals are a fibre source's rows at 1500 W (a CO2 cuts metal about half as fast per watt: its reference
#   is 3000 W, and under 500 W it does not cut metal), everything else a CO2's at 100 W (a diode's too, from the
#   same rows); speed scales about linearly with power (``machine.power_w``, 0.05x to 4x);
# * plasma: the rows are a 45 A air plasma's; another current (``machine.amps``) cuts thickness t about as fast as
#   45 A cuts t x 45 / amps (an equivalent thickness);
# * waterjet: the rows are an abrasive jet's at quality 3 (of 1 separation .. 5 finest); quality scales speed
#   (2.0, 1.4, 1.0, 0.75, 0.6x), and a pure-water jet (``machine.abrasive`` false) has its own rows for soft stock;
# * wire EDM: a removal rate in mm²/min for a 0.25 mm brass wire's main cut; the feed is the rate over the
#   thickness, and skims run faster (3x, 5x, 8x).
#
# Pierce times grow with thickness (a waterjet's with how slowly it cuts). Every number is a starting point.

#: The materials a fibre laser's rows (and a plasma) cut: metals.
METALS = ("aluminum-6061", "aluminum-7075", "steel-1018", "stainless-304", "tool-steel", "titanium-6al4v", "brass",
          "copper")
#: More rows for the reference machines, beside CUT_SPEEDS's.
CUT_SPEEDS_EXTRA: dict[str, dict[str, tuple[tuple[float, float], ...]]] = {
    "laser": {
        "brass": ((1.0, 6000.0), (3.0, 1000.0)),
        "aluminum-7075": ((1.0, 7000.0), (3.0, 1300.0), (6.0, 450.0)),
        "delrin": ((3.0, 900.0), (6.0, 400.0)),
        "foam": ((5.0, 3000.0), (20.0, 800.0)),
    },
    "plasma": {
        "aluminum-7075": ((1.5, 6000.0), (3.0, 3700.0), (6.0, 1800.0), (10.0, 900.0)),
        "tool-steel": ((1.5, 5000.0), (3.0, 3000.0), (6.0, 1500.0), (10.0, 750.0)),
        "copper": ((1.5, 4000.0), (3.0, 2200.0), (6.0, 1000.0)),
        "brass": ((1.5, 4500.0), (3.0, 2500.0), (6.0, 1200.0)),
    },
    "waterjet": {
        "aluminum-7075": ((3.0, 1300.0), (6.0, 650.0), (12.0, 300.0), (25.0, 140.0)),
        "tool-steel": ((3.0, 450.0), (6.0, 220.0), (12.0, 100.0)),
        "brass": ((3.0, 700.0), (6.0, 350.0), (12.0, 160.0)),
        "copper": ((3.0, 600.0), (6.0, 300.0), (12.0, 140.0)),
        "delrin": ((3.0, 2000.0), (6.0, 1000.0), (12.0, 450.0)),
        "hdpe": ((3.0, 2500.0), (6.0, 1300.0), (12.0, 600.0)),
        "hardwood": ((6.0, 1500.0), (12.0, 700.0)),
    },
}
#: A pure-water jet's rows (no abrasive): soft stock only.
WATERJET_PURE: dict[str, tuple[tuple[float, float], ...]] = {
    "foam": ((10.0, 10000.0), (50.0, 3000.0)),
    "hdpe": ((1.5, 2500.0), (3.0, 1000.0)),
    "nylon": ((1.5, 2000.0), (3.0, 800.0)),
}
LASER_REFERENCE_W = {"fiber": 1500.0, "co2": 100.0, "diode": 100.0}
_CO2_METAL_REFERENCE_W = 3000.0
PLASMA_REFERENCE_A = 45.0
WATERJET_QUALITY = {1: 2.0, 2: 1.4, 3: 1.0, 4: 0.75, 5: 0.6}
#: Wire EDM main-cut removal rate (mm²/min) for a 0.25 mm brass wire; skims run at these multiples of its feed.
WIRE_RATE_MM2_MIN = {"steel-1018": 150.0, "tool-steel": 120.0, "stainless-304": 120.0, "aluminum-6061": 300.0,
                     "aluminum-7075": 280.0, "titanium-6al4v": 80.0, "copper": 100.0, "brass": 250.0}
WIRE_SKIM_FACTORS = (3.0, 5.0, 8.0, 10.0)


def _interpolate(rows, thickness_mm: float) -> float:
    xs = [math.log(t) for t, _ in rows]
    ys = [math.log(v) for _, v in rows]
    x = math.log(thickness_mm)
    if len(xs) == 1 or x <= xs[0]:
        return math.exp(ys[0])
    if x >= xs[-1]:
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return math.exp(ys[-1] + slope * (x - xs[-1]))
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            f = (x - xs[i]) / (xs[i + 1] - xs[i])
            return math.exp(ys[i] + f * (ys[i + 1] - ys[i]))
    return math.exp(ys[-1])


def _cut_rows(process: str, name: str):
    return CUT_SPEEDS.get(process, {}).get(name) or CUT_SPEEDS_EXTRA.get(process, {}).get(name)


def laser_source(material, machine) -> str:
    """The laser's source: the machine's, else fibre for a metal and CO2 for anything else."""
    name = getattr(material, "name", material)
    return getattr(machine, "laser_source", None) or ("fiber" if name in METALS else "co2")


@dataclass(frozen=True)
class CutSpeed:
    """A cutting process's starting speed: ``speed_mm_min`` (None when no row fits: ``why`` says so), the reference
    it was scaled from, and plain notes (an extrapolated thickness, a clamp)."""

    speed_mm_min: float | None
    reference: str
    why: str = ""
    notes: tuple[str, ...] = ()
    table_max_mm: float | None = None


def cut_speed(material, machine, thickness_mm: float, *, quality: int = 3) -> CutSpeed:
    """The starting cutting speed for ``machine`` (laser, plasma, waterjet) through ``thickness_mm`` of
    ``material`` (a job Material or its name), scaled from the reference machine's rows (see above)."""
    name = getattr(material, "name", material)
    process = machine.kind
    metal = name in METALS
    notes: list[str] = []
    if process == "laser":
        source = laser_source(name, machine)
        power = getattr(machine, "power_w", None) or LASER_REFERENCE_W[source]
        if metal and source == "diode":
            return CutSpeed(None, "", "a diode laser does not cut metal; use a fibre laser, a plasma or a waterjet")
        if metal and source == "co2" and power < 500:
            return CutSpeed(None, "", f"a {power:g} W CO2 laser does not cut metal (it takes about 500 W and up); use "
                            "a fibre laser, a plasma or a waterjet")
        if not metal and source == "fiber":
            return CutSpeed(None, "", f"the table has fibre-laser rows for metals only, not {name}; a fibre laser "
                            "passes through clear acrylic and chars wood. Use a CO2 laser, or give the cut a feed")
        reference = _CO2_METAL_REFERENCE_W if (metal and source == "co2") else LASER_REFERENCE_W[source]
        rows = _cut_rows("laser", name)
        scale = min(4.0, max(0.05, power / reference))
        words = f"a {reference:g} W {'CO2' if source == 'diode' else source} laser's rows, scaled to {power:g} W"
    elif process == "plasma":
        if not metal:
            return CutSpeed(None, "", f"a plasma cuts conductive metal only, not {name}; use a laser, a waterjet or "
                            "a router")
        amps = getattr(machine, "amps", None) or PLASMA_REFERENCE_A
        rows = _cut_rows("plasma", name)
        scale = 1.0
        thickness_mm = thickness_mm * PLASMA_REFERENCE_A / amps
        words = f"a {PLASMA_REFERENCE_A:g} A air plasma, scaled to {amps:g} A"
    elif process == "waterjet":
        if quality not in WATERJET_QUALITY:
            raise ValueError(f"waterjet quality {quality!r} is not 1..5")
        if getattr(machine, "abrasive", True):
            rows = _cut_rows("waterjet", name)
            words = f"an abrasive waterjet at quality {quality}"
        else:
            if metal:
                return CutSpeed(None, "", "pure water does not cut metal; set machine.abrasive true")
            rows = WATERJET_PURE.get(name)
            words = f"a pure-water jet at quality {quality}"
        scale = WATERJET_QUALITY[quality]
    else:
        raise ValueError(f"cut_speed is for laser, plasma and waterjet machines, not {process!r}")
    if not rows:
        return CutSpeed(None, "", f"the {process} table has no row for {name}; give the cut its own feed (mm/min)")
    table_max = rows[-1][0]
    if thickness_mm > table_max * 1.0001:
        notes.append(f"{thickness_mm:g} mm is past the table's thickest {name} row ({table_max:g} mm"
                     + (" at the equivalent thickness for this current" if process == "plasma" else "")
                     + "): the speed is extrapolated; check the machine can cut it at all")
    speed = _interpolate(rows, max(thickness_mm, 0.05)) * scale
    return CutSpeed(float(round(speed)), words, notes=tuple(notes), table_max_mm=table_max)


def pierce_seconds(machine, thickness_mm: float, *, reference_speed_mm_min: float | None = None,
                   source: str = "") -> float:
    """A starting pierce time (s): the beam or jet held still on until it is through ``thickness_mm``."""
    t = max(0.0, float(thickness_mm))
    kind = machine.kind
    if kind == "laser":
        if source == "diode":
            return round(0.5 + 0.2 * t, 2)
        return round(0.1 + 0.15 * t, 2) if source == "fiber" else round(0.05 + 0.05 * t, 2)
    if kind == "plasma":
        return round(0.1 + 0.08 * t, 2)
    if kind == "waterjet":
        speed = reference_speed_mm_min or 300.0
        return round(1.0 + 120.0 * t / speed, 1)
    return 0.0


def wire_speeds(material, thickness_mm: float, passes: int) -> list[float] | None:
    """Wire EDM feeds (mm/min) for the main cut and each skim through ``thickness_mm``, or None when the table has
    no rate for the material."""
    rate = WIRE_RATE_MM2_MIN.get(getattr(material, "name", material))
    if rate is None:
        return None
    main = rate / max(thickness_mm, 0.5)
    return [round(main, 2)] + [round(main * WIRE_SKIM_FACTORS[min(k, len(WIRE_SKIM_FACTORS) - 1)], 2)
                               for k in range(max(0, passes - 1))]


# --- turning ---------------------------------------------------------------------------------------------

#: Per material, a carbide turning insert's starting numbers (Sandvik/Kennametal general turning tables, held to the
#: conservative end for a light lathe): surface speed (m/min), roughing and finishing feed per revolution (mm/rev)
#: and the roughing depth of cut (mm, radial).
TURNING: dict[str, dict] = {
    "aluminum-6061": {"vc": 300.0, "rough": 0.25, "finish": 0.10, "doc": 2.0},
    "aluminum-7075": {"vc": 270.0, "rough": 0.25, "finish": 0.10, "doc": 2.0},
    "steel-1018": {"vc": 180.0, "rough": 0.25, "finish": 0.10, "doc": 1.5},
    "stainless-304": {"vc": 130.0, "rough": 0.20, "finish": 0.08, "doc": 1.0},
    "tool-steel": {"vc": 100.0, "rough": 0.20, "finish": 0.08, "doc": 1.0},
    "titanium-6al4v": {"vc": 50.0, "rough": 0.15, "finish": 0.08, "doc": 0.8},
    "brass": {"vc": 220.0, "rough": 0.20, "finish": 0.08, "doc": 1.5},
    "copper": {"vc": 160.0, "rough": 0.15, "finish": 0.08, "doc": 1.0},
    "delrin": {"vc": 250.0, "rough": 0.20, "finish": 0.10, "doc": 2.0},
    "acrylic": {"vc": 150.0, "rough": 0.15, "finish": 0.08, "doc": 1.0},
    "hdpe": {"vc": 200.0, "rough": 0.25, "finish": 0.10, "doc": 2.0},
    "nylon": {"vc": 200.0, "rough": 0.20, "finish": 0.10, "doc": 1.5},
    "mdf": {"vc": 300.0, "rough": 0.20, "finish": 0.10, "doc": 1.5},
    "hardwood": {"vc": 300.0, "rough": 0.20, "finish": 0.10, "doc": 1.5},
    "plywood": {"vc": 300.0, "rough": 0.20, "finish": 0.10, "doc": 1.0},
    "carbon-fiber": {"vc": 100.0, "rough": 0.10, "finish": 0.05, "doc": 0.5},
    "foam": {"vc": 300.0, "rough": 0.30, "finish": 0.15, "doc": 3.0},
}
#: The turning kinds :func:`for_turn` knows, each a surface speed factor and the feed it starts from.
TURN_KINDS = {"turn_rough": (1.0, "rough"), "turn_finish": (1.2, "finish"), "turn_face": (1.0, "face"),
              "groove": (0.7, "groove"), "partoff": (0.6, "partoff"), "thread": (0.5, "thread")}
#: The spindle cap for constant surface speed when the job names no ``machine.max_rpm`` (a G50/G92 clamp is always
#: posted: CSS near the centre would otherwise run away).
LATHE_MAX_RPM = 3000.0


def _turning_numbers(material) -> dict:
    """The turning row by name (its surface speed the job's when it overrides one), or the job's own speed."""
    if material.table:
        numbers = dict(TURNING[material.name])
        if material.surface_m_min is not None:
            numbers["vc"] = material.surface_m_min
        return numbers
    return {"vc": material.surface_m_min, "rough": 0.2, "finish": 0.08, "doc": 1.0}


def turn_depth_of_cut(material, *, inside: bool = False) -> float:
    """The default roughing depth of cut (mm, radial): the table's, 0.6 of it in a bore."""
    return round(_turning_numbers(material)["doc"] * (0.6 if inside else 1.0), 3)


def for_turn(material, tool, kind: str, machine, *, diameter_mm: float, feed: float | None = None,
             speed: float | None = None, feed_mm_rev: float | None = None, css_m_min: float | None = None,
             pitch_mm: float | None = None) -> Feeds:
    """A lathe operation's spindle and feed (:data:`TURN_KINDS`): constant surface speed with the machine's rpm cap
    (``rpm`` is the speed at ``diameter_mm``, the one the times assume) and a feed per revolution. A thread runs at a
    constant rpm (the spindle must not change speed along a thread) with the feed one pitch a revolution. Overrides:
    ``speed`` (rpm, constant), ``css_m_min``, ``feed_mm_rev``, ``feed`` (mm/min at that rpm)."""
    if kind not in TURN_KINDS:
        raise ValueError(f"unknown turning kind {kind!r}; one of {', '.join(TURN_KINDS)}")
    numbers = _turning_numbers(material)
    factor, feed_kind = TURN_KINDS[kind]
    vc = float(css_m_min) if css_m_min is not None else numbers["vc"] * factor * (_HSS if tool.material == "hss" else 1.0)
    cap = float(machine.max_rpm) if machine.max_rpm is not None else LATHE_MAX_RPM
    clamped: list[str] = []
    note = "a starting point: adjust to the machine, the insert and the chips"
    diameter = max(float(diameter_mm), 0.5)
    constant = kind == "thread" or speed is not None
    wanted = float(speed) if speed is not None else 1000.0 * vc / (math.pi * diameter)
    rpm = min(wanted, cap)
    if wanted > cap + 1e-9:
        if machine.max_rpm is not None:
            clamped.append(f"{vc:.0f} m/min at Ø{diameter:g} wants {wanted:.0f} rpm, clamped to the machine's "
                           f"{cap:.0f} rpm")
        else:
            note += f"; the spindle is capped at {cap:.0f} rpm (the job names no machine.max_rpm)"
    if speed is None:
        rpm = _round_rpm(rpm)
    if kind == "thread":
        per_rev = float(pitch_mm or tool.pitch_mm)
    elif feed_mm_rev is not None:
        per_rev = float(feed_mm_rev)
    else:
        rough, finish = numbers["rough"], numbers["finish"]
        per_rev = {"rough": rough, "finish": finish, "face": 0.8 * rough,
                   "groove": min(0.12, max(0.02, 0.25 * rough)),
                   "partoff": min(0.1, max(0.02, 0.2 * rough))}[feed_kind]
        if feed_kind == "finish" and tool.nose_radius_mm > 0:
            # A finishing feed past half the nose radius leaves a rough, scalloped surface.
            per_rev = min(per_rev, 0.5 * tool.nose_radius_mm)
    if feed is not None and kind != "thread":
        per_rev = float(feed) / rpm
    cut = per_rev * rpm
    if machine.max_feed_mm_min is not None and cut > machine.max_feed_mm_min:
        if kind == "thread":
            clamped.append(f"a thread must feed at rpm x pitch ({cut:.0f} mm/min), more than the machine's "
                           f"{machine.max_feed_mm_min:.0f} mm/min: the spindle was slowed to match")
            rpm = machine.max_feed_mm_min / per_rev
        else:
            clamped.append(f"feed {cut:.0f} mm/min clamped to the machine's {machine.max_feed_mm_min:.0f} mm/min")
            per_rev = machine.max_feed_mm_min / rpm
        cut = per_rev * rpm
    source = "job" if (feed is not None or feed_mm_rev is not None) and (speed is not None or css_m_min is not None) \
        else "mixed" if any(v is not None for v in (feed, speed, feed_mm_rev, css_m_min)) else "table"
    return Feeds(rpm=round(rpm, 3), feed_mm_min=round(cut, 3), plunge_mm_min=round(cut, 3), ramp_mm_min=round(cut, 3),
                 chipload_mm=round(per_rev, 5), surface_m_min=round(math.pi * diameter * rpm / 1000.0, 1),
                 clamped=tuple(clamped), source=source, note=note,
                 css_m_min=None if constant else round(vc, 2), max_rpm=cap, feed_mm_rev=round(per_rev, 5))

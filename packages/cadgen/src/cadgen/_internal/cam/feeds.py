"""Feeds and speeds: a material table and the rules that turn it into a spindle speed and feeds for one tool.

FreeCAD cuts at what its tool controller says and says nothing itself (its default is 0 rpm and 0 mm/min), so every
operation's numbers come from here and go to FreeCAD with the operation.

**Every number here is a starting point, and the Results say so.** They are on the conservative side of the ranges
tool vendors publish for carbide end mills on a rigid hobby-to-light-industrial machine (Harvey/Helical, Kennametal,
Sandvik and Onsrud tables, which give surface speed per material and chip load per tooth against diameter):
aluminium 6061 is published at roughly 300-1000 m/min and 0.025-0.08 mm/tooth at 6 mm, so the table says 250 m/min
and 0.04 mm; 1018 steel at roughly 100-200 m/min and 0.02-0.05 mm, so 120 and 0.03. An operation's
``feed``/``speed``/``plunge_mm_min`` wins over all of it; the machine's ``max_rpm``/``max_feed_mm_min`` clamps it,
its ``min_rpm`` raises a slower speed, and either is reported.

The rules (:func:`for_op`):

* spindle ``rpm = 1000 * Vc / (pi * D)`` (a drill at 0.6 of it), rounded to 10 rpm, then held to the machine;
* milling feed ``= rpm * flutes * fz``, ``fz`` the table's 6 mm chip load scaled along :data:`CHIPLOAD_CURVE` by
  the diameter, and a light radial stepover gets radial chip thinning ``D / (2 sqrt(D ae - ae^2))``, capped at 2x;
* drilling feed ``= rpm * f``, ``f`` per revolution in proportion to the diameter;
* plunge at 0.3x the plain-chip feed (a plunge takes a full-width chip whatever the stepover); the default step down
  is a fraction of the diameter per material (half in aluminium, a quarter in steel).

Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["CHIPLOAD_CURVE", "Feeds", "MATERIALS", "MATERIAL_ALIASES", "OP_KINDS", "chipload_at", "default_stepdown",
           "for_op"]

#: Per material: plain name, carbide surface speed (m/min), carbide chip load per tooth at 6 mm (mm), drill feed per
#: revolution per mm of diameter (mm/rev/mm), and the default step down as a fraction of the diameter.
MATERIALS: dict[str, dict] = {
    "aluminum-6061": {"plain": "aluminium 6061", "vc": 250.0, "fz6": 0.040, "drill": 0.020, "stepdown": 0.5},
    "aluminum-7075": {"plain": "aluminium 7075", "vc": 220.0, "fz6": 0.040, "drill": 0.020, "stepdown": 0.5},
    "steel-1018": {"plain": "mild steel 1018", "vc": 120.0, "fz6": 0.030, "drill": 0.015, "stepdown": 0.25},
    "stainless-304": {"plain": "stainless 304", "vc": 80.0, "fz6": 0.025, "drill": 0.012, "stepdown": 0.2},
    "brass": {"plain": "brass", "vc": 200.0, "fz6": 0.050, "drill": 0.025, "stepdown": 0.5},
    "delrin": {"plain": "Delrin (acetal)", "vc": 300.0, "fz6": 0.080, "drill": 0.030, "stepdown": 0.75},
    "acrylic": {"plain": "acrylic", "vc": 250.0, "fz6": 0.060, "drill": 0.025, "stepdown": 0.5},
    "hdpe": {"plain": "HDPE", "vc": 300.0, "fz6": 0.100, "drill": 0.040, "stepdown": 1.0},
    "mdf": {"plain": "MDF", "vc": 400.0, "fz6": 0.100, "drill": 0.040, "stepdown": 1.0},
    "hardwood": {"plain": "hardwood", "vc": 400.0, "fz6": 0.080, "drill": 0.030, "stepdown": 0.75},
    "plywood": {"plain": "plywood", "vc": 400.0, "fz6": 0.090, "drill": 0.030, "stepdown": 0.75},
}
#: Other names a job may give a table material: the job's material then is the canonical row, by its own name.
MATERIAL_ALIASES: dict[str, str] = {"mild-steel": "steel-1018", "acetal": "delrin"}

#: The chip load per tooth against the tool's diameter (mm), as a multiple of the table's 6 mm number: the shape of
#: the vendors' charts (it grows about in proportion to the diameter, then flattens). Under the first diameter it
#: falls in proportion; past the last it holds.
CHIPLOAD_CURVE: tuple[tuple[float, float], ...] = (
    (1.0, 0.2), (3.0, 0.5), (6.0, 1.0), (10.0, 1.5), (12.0, 1.75), (20.0, 2.5))

#: What an operation asks feeds for.
OP_KINDS = ("rough", "finish", "face", "drill")
_DRILL_RPM = 0.6


@dataclass(frozen=True)
class Feeds:
    """What an operation cuts at. ``clamped`` names each limit the machine imposed."""

    rpm: float
    feed_mm_min: float
    plunge_mm_min: float
    clamped: tuple[str, ...] = ()


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
    if material.chipload_mm is not None:
        numbers["fz6"] = material.chipload_mm
    if material.drill_mm_per_rev is not None:
        numbers["drill"] = material.drill_mm_per_rev
    if material.stepdown_fraction is not None:
        numbers["stepdown"] = material.stepdown_fraction
    return numbers


def default_stepdown(material, tool) -> float:
    """The default axial step: the material's fraction of the diameter, never past the flutes."""
    return max(0.05, min(tool.flute_length_mm, _material_numbers(material)["stepdown"] * tool.diameter_mm))


def _chip_thinning(diameter: float, stepover_mm: float | None) -> float:
    if not stepover_mm or stepover_mm >= diameter / 2.0:
        return 1.0
    engaged = math.sqrt(max(1e-12, diameter * stepover_mm - stepover_mm ** 2))
    return min(2.0, diameter / (2.0 * engaged))


def for_op(material, tool, kind: str, machine, *, stepover_mm: float | None = None, feed: float | None = None,
           speed: float | None = None, plunge: float | None = None) -> Feeds:
    """The spindle speed and feeds for ``tool`` doing an operation of ``kind`` (:data:`OP_KINDS`) in ``material`` on
    ``machine``; ``feed``/``speed``/``plunge`` are the job's overrides (mm/min, rpm, mm/min)."""
    if kind not in OP_KINDS:
        raise ValueError(f"unknown feeds kind {kind!r}; one of {', '.join(OP_KINDS)}")
    numbers = _material_numbers(material)
    diameter = tool.diameter_mm
    clamped: list[str] = []
    if speed is not None:
        rpm = float(speed)
    else:
        vc = numbers["vc"] * (_DRILL_RPM if kind == "drill" else 1.0)
        rpm = float(max(10.0, round(1000.0 * vc / (math.pi * diameter) / 10.0) * 10.0))
    if machine.max_rpm is not None and rpm > machine.max_rpm:
        limit = float(math.floor(machine.max_rpm))
        clamped.append(f"spindle {rpm:.0f} rpm clamped to the machine's {limit:.0f} rpm")
        rpm = limit
    if machine.min_rpm is not None and rpm < machine.min_rpm:
        floor = float(math.ceil(machine.min_rpm))
        if speed is None and kind == "drill" and floor > 1.3 * rpm:
            raise CamJobError(f"{tool.id} ({tool.plain}) wants about {rpm:.0f} rpm in {numbers['plain']}, but this "
                              f"machine's spindle turns no slower than {floor:.0f} rpm (machine.min_rpm): that speed "
                              "burns a drill's point. Pocket the hole with a smaller end mill, or state the "
                              "operation's speed where the drill maker's chart allows it")
        clamped.append(f"spindle {rpm:.0f} rpm raised to the machine's slowest, {floor:.0f} rpm")
        rpm = floor
    if kind == "drill":
        if numbers["drill"] is None:
            raise CamJobError(f"{tool.id} drills {numbers['plain']}, and the job's material gives no drilling feed: add "
                              "material.drill_mm_per_rev (the feed per revolution per mm of drill diameter) from the "
                              "drill maker's chart")
        chipload = numbers["drill"] * diameter
        cut = plunge_f = rpm * chipload
    else:
        fz = numbers["fz6"] * chipload_at(CHIPLOAD_CURVE, diameter)
        plunge_f = 0.3 * rpm * tool.flutes * fz
        chipload = fz * _chip_thinning(diameter, stepover_mm)
        cut = rpm * tool.flutes * chipload
    if feed is not None:
        plunge_f *= float(feed) / cut
        cut = float(feed)
    if plunge is not None:
        plunge_f = float(plunge)
    limit = machine.max_feed_mm_min
    if limit is not None:
        if cut > limit:
            clamped.append(f"feed {cut:.0f} mm/min clamped to the machine's {limit:.0f} mm/min")
            plunge_f, cut = (plunge_f * limit / cut if plunge is None else plunge_f), limit
        if plunge_f > limit:
            clamped.append(f"plunge {plunge_f:.0f} mm/min clamped to the machine's {limit:.0f} mm/min")
            plunge_f = limit
    return Feeds(rpm=round(rpm, 3), feed_mm_min=float(max(1.0, round(cut))), plunge_mm_min=float(max(1.0, round(plunge_f))),
                 clamped=tuple(clamped))

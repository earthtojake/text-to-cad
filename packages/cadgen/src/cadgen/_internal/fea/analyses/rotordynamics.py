"""Spinning (lite): a shaft and its discs spinning on bearings, their whirl, critical speeds and spinning stress.

The part (or a bonded assembly of parts) spins about the study's axis
(``spin.axis``) and sits in ``bearings``. Tier 3, lite. What it solves:

- **The rotor line** (:mod:`cadgen._internal.fea.rotor`): the CAD cut into
  sections along the axis, each sliced exactly from the solid (its mass,
  bending stiffness, and rotary and polar inertia), as Timoshenko shaft
  elements. A run of sections much wider than the shaft either side is a disc:
  lumped at its mass centre (rigid, the default) or kept as its own sections
  (``"disc_model": "flexible"``). The study may add discs the CAD leaves out.
  Each bearing is a spring and a damper along the two axes across the spin
  (``kxx``, ``kyy``, cross terms, each a number or a table over speed), or
  rigid, or clamped. Gyroscopic terms are in.
- **The Campbell diagram**: the forward and backward whirl frequencies against
  speed, from rest past the top operating speed, and each whirl's log decrement.
- **Critical speeds**: where a whirl crosses an order line (once per
  revolution unless the check asks for others), found to a part in 10^9.
- **Unbalance response**: the orbit an unbalance (``g_mm`` at a face or a
  station) drives at each speed, its amplitude and phase; peaks at the
  criticals. With none in the study, a balance grade G2.5 (ISO 21940-11)
  unbalance at the heaviest disc at the top speed, said as such.
- **The spinning solid**: the centrifugal stress at the top speed (a body
  load ρΩ²r on the part's own mesh, held by nothing: inertia relief and six
  pinned DOF, so the stress is the spin's alone); with ``spin.solid_modes``,
  the solid's frequencies at rest and spinning (stress stiffening and spin
  softening, in the rotating frame) with its bearing faces held.

Checks: ``critical_speed`` (every critical kept ``margin_percent`` clear of the
operating speeds), ``stability`` (the smallest log decrement over the operating
speeds, at least ``min_log_dec``) and ``stress`` (the spinning stress against
yield). Its series is the whirl shape at each critical speed (an orbit: real and
imaginary parts, which the viewer's Whirl turns through). The ladder:
``reduce_modes`` (the rotor projected on its slowest bending shapes), then
``iterative`` and ``local_refine`` for the solid. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "BearingInput", "DiscInput", "RotordynamicsAnalysis", "RotordynamicsInputs", "UnbalanceInput", "critical_check",
    "orbit_text", "rpm_text", "stability_check", "whirl_words",
]

_TWO_PI = 2.0 * math.pi
#: The coefficient names a bearing takes, in :class:`rotor.Bearing`'s field order: springs N/mm, dampers N s/mm,
#: along e1 (x) and e2 (y) across the spin.
COEFFICIENTS = ("kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx")
#: Elements along the rotor (more where its sections change, and at each station a study names).
ROTOR_ELEMENTS = 40
#: Whirl curves per direction a study finds when it says none (``modes``), and the most it may ask for.
DEFAULT_CURVES, MAX_CURVES = 4, 12
#: Speeds the Campbell diagram is solved at, and the unbalance response.
CAMPBELL_SPEEDS, RESPONSE_SPEEDS = 61, 241
#: The Campbell sweep reaches this multiple of the top operating speed when the study names none.
SWEEP_FACTOR = 1.5
#: The default unbalance's balance grade, mm/s (ISO 21940-11 G2.5: turbines, compressors, machine-tool spindles).
DEFAULT_GRADE_MM_S = 2.5
#: A log decrement this close to zero is no damping at all (an undamped rotor), not a growing whirl.
UNDAMPED = 1e-7
#: The stress check is close within its margin; the stability check within (min_log_dec, 0].
_STABLE_CLOSE_AT = 0.9
#: Dense eigen cost per evaluation (seconds per state size cubed), and evaluations per run, for the ladder's estimate.
EIG_SECONDS_PER_CUBE, EVALUATIONS = 2e-9, 140
_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
LIMITS = (
    "Linear bearings: each a spring and a damper (it may change with speed); no fluid-film nonlinearity",
    "Bending whirl only: no torsional or axial vibration, and no torsional-lateral coupling",
    "A round rotor line: each section's bending stiffness is the mean of its two directions",
    "A rigid disc adds its mass and inertia; the shaft through it bends like the shaft beside it",
    "The spinning stress is linear: the spin's load on the undeformed part",
)


def rpm_text(rpm: float) -> str:
    """A speed as a sentence says it: "12,400 rpm" (three figures from 1,000 up), "850 rpm", "4.5 rpm"."""
    if rpm >= 1000:
        digits = 3 - int(math.floor(math.log10(rpm))) - 1
        return f"{round(rpm, digits):,.0f} rpm"
    return f"{rpm:.0f} rpm" if rpm >= 10 else f"{rpm:.2g} rpm"


def _rpm(omega: float) -> float:
    return omega * 60.0 / _TWO_PI


def _omega(rpm: float) -> float:
    return rpm * _TWO_PI / 60.0


def orbit_text(mm: float) -> str:
    """An orbit's size as a sentence says it: "4.2 µm" under a millimetre, "6.9 mm" from one up."""
    return f"{mm * 1000:.3g} µm" if mm < 1 else f"{mm:.3g} mm"


# -- the study ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BearingInput:
    faces: tuple[str, ...] = ()
    at_mm: float | None = None
    #: Each coefficient given: a number, or a table ((rpm, value), ...).
    coefficients: tuple[tuple[str, Any], ...] = ()
    rigid: bool = False
    clamped: bool = False

    def value(self, name: str):
        return dict(self.coefficients).get(name, 0.0)


@dataclass(frozen=True)
class DiscInput:
    at_mm: float
    mass_kg: float
    polar_kg_mm2: float
    diametral_kg_mm2: float


@dataclass(frozen=True)
class UnbalanceInput:
    g_mm: float
    faces: tuple[str, ...] = ()
    at_mm: float | None = None
    phase_deg: float = 0.0


@dataclass(frozen=True)
class RotordynamicsInputs(Inputs):
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    #: "X", "Y" or "Z", or "" for a vector axis.
    axis_name: str = "Z"
    through_mm: tuple[float, float, float] | None = None
    #: The operating speed range, rpm (low may be 0; one speed is (n, n)).
    rpm: tuple[float, float] = (0.0, 0.0)
    sweep_rpm: float | None = None
    bearings: tuple[BearingInput, ...] = ()
    discs: tuple[DiscInput, ...] = ()
    disc_model: str = "rigid"
    unbalance: tuple[UnbalanceInput, ...] = ()
    #: Whirl curves per direction (forward, backward) the Campbell diagram tracks.
    modes: int = DEFAULT_CURVES
    solid_modes: int = 0
    #: The study's checks, parsed (critical_speed, stability, stress), else the defaults.
    checks: tuple[dict, ...] = ()

    @property
    def orders(self) -> tuple[float, ...]:
        found = {1.0}
        for check in self.checks:
            if check.get("kind") == "critical_speed":
                found |= set(check.get("orders", (1.0,)))
        return tuple(sorted(found))

    @property
    def margin(self) -> float:
        """The largest separation a critical_speed check asks for, as a fraction."""
        return max((check.get("margin_percent", 15.0) for check in self.checks if check.get("kind") == "critical_speed"),
                   default=15.0) / 100.0

    @property
    def sweep_top_rpm(self) -> float:
        """The Campbell sweep's top: the study's, else 1.5 x the top speed; never short of the margin a check needs."""
        top = self.rpm[1]
        wanted = self.sweep_rpm if self.sweep_rpm is not None else SWEEP_FACTOR * top
        return max(wanted, 1.1 * (1.0 + self.margin) * top)

    @property
    def bearing_faces(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ref for bearing in self.bearings for ref in bearing.faces))


def _where_on_axis(entry: dict, where: str) -> tuple[tuple[str, ...], float | None]:
    """A bearing's or an unbalance's place: ``faces`` (its station is their centre along the axis) or ``at_mm``."""
    has_faces, has_at = "faces" in entry, "at_mm" in entry
    if has_faces == has_at:
        raise ValueError(f"{where}: give where it is as faces (like [\"#o1.f3\"]: its place along the spin axis is the "
                         "faces' centre) or at_mm (the position along the spin axis, in the part's coordinates), one of them")
    if has_faces:
        return kinds.faces(entry, where=where), None
    return (), kinds.number(entry["at_mm"], where=f"{where}.at_mm")


def _coefficient(value: Any, where: str):
    """A bearing coefficient: a number (N/mm or N s/mm), or a table [[rpm, value], ...] over speed."""
    if isinstance(value, list):
        if len(value) < 2 or not all(isinstance(row, list) and len(row) == 2 for row in value):
            raise ValueError(f"{where}: a number, or a table over speed as [[rpm, value], [rpm, value], ...] (two rows or more)")
        rows = tuple((kinds.number(row[0], where=f"{where} rpm"), kinds.number(row[1], where=where)) for row in value)
        speeds = [row[0] for row in rows]
        if any(b <= a for a, b in zip(speeds, speeds[1:])) or speeds[0] < 0:
            raise ValueError(f"{where}: the table's speeds must climb from 0 rpm or more, got {speeds}")
        return rows
    return kinds.number(value, where=where)


def _bearing(entry: Any, index: int) -> BearingInput:
    where = f"bearings[{index}]"
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"faces\": [\"#o1.f3\"], \"k\": 20000, \"c\": 5}}")
    allowed = {"faces", "at_mm", "k", "c", "rigid", "clamped", "label", *COEFFICIENTS}
    unknown = set(entry) - allowed
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a bearing takes {sorted(allowed)}")
    faces, at = _where_on_axis(entry, where)
    flags = {}
    for flag in ("rigid", "clamped"):
        if flag in entry:
            if not isinstance(entry[flag], bool):
                raise ValueError(f"{where}.{flag}: true or false, got {kinds.json_text(entry[flag])}")
            flags[flag] = entry[flag]
    springs = [key for key in ("k", "c", *COEFFICIENTS) if key in entry]
    if (flags.get("rigid") or flags.get("clamped")) and springs:
        raise ValueError(f"{where}: a rigid or clamped bearing holds the shaft still; it takes no springs or dampers "
                         f"({', '.join(springs)})")
    coefficients: dict[str, Any] = {}
    for short, pair in (("k", ("kxx", "kyy")), ("c", ("cxx", "cyy"))):
        if short in entry:
            if any(name in entry for name in pair):
                raise ValueError(f"{where}.{short}: {short} sets {pair[0]} and {pair[1]} alike; give it or them, not both")
            value = _coefficient(entry[short], f"{where}.{short}")
            coefficients.update({pair[0]: value, pair[1]: value})
    for name in COEFFICIENTS:
        if name in entry:
            coefficients[name] = _coefficient(entry[name], f"{where}.{name}")
    if not (flags.get("rigid") or flags.get("clamped")):
        for name in ("kxx", "kyy"):
            value = coefficients.get(name)
            low = min(row[1] for row in value) if isinstance(value, tuple) else value
            if value is None or not low > 0:
                raise ValueError(f"{where}: a bearing needs its stiffness across the shaft, k (N/mm, both directions) or "
                                 "kxx and kyy, above 0; or \"rigid\": true for a stiff ball bearing on a stiff housing")
        for name in ("cxx", "cyy"):
            value = coefficients.get(name, 0.0)
            low = min(row[1] for row in value) if isinstance(value, tuple) else value
            if low < 0:
                raise ValueError(f"{where}.{name}: a damper takes energy out; 0 or more N s/mm, got {low:g}")
    return BearingInput(faces, at, tuple(sorted(coefficients.items())), flags.get("rigid", False), flags.get("clamped", False))


def _disc(entry: Any, index: int) -> DiscInput:
    where = f"discs[{index}]"
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"at_mm\": 150, \"mass_kg\": 2.5, \"polar_kg_mm2\": 3000, "
                         "\"diametral_kg_mm2\": 1600}}")
    allowed = {"at_mm", "mass_kg", "polar_kg_mm2", "diametral_kg_mm2", "label"}
    unknown = set(entry) - allowed
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; an added disc takes {sorted(allowed)} (discs in the "
                         "CAD are found by themselves)")
    for key in ("at_mm", "mass_kg"):
        if key not in entry:
            raise ValueError(f"{where}.{key}: an added disc needs its place along the spin axis (at_mm) and its mass (mass_kg)")
    mass = kinds.number(entry["mass_kg"], where=f"{where}.mass_kg", positive=True)
    polar = kinds.number(entry.get("polar_kg_mm2", 0.0), where=f"{where}.polar_kg_mm2")
    diametral = kinds.number(entry.get("diametral_kg_mm2", polar / 2.0), where=f"{where}.diametral_kg_mm2")
    if polar < 0 or diametral < 0:
        raise ValueError(f"{where}: an inertia is 0 or more kg mm²")
    return DiscInput(kinds.number(entry["at_mm"], where=f"{where}.at_mm"), mass, polar, diametral)


def _unbalance(entry: Any, index: int) -> UnbalanceInput:
    where = f"unbalance[{index}]"
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"faces\": [\"#o1.f5\"], \"g_mm\": 50}}")
    allowed = {"faces", "at_mm", "g_mm", "phase_deg", "label"}
    unknown = set(entry) - allowed
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; an unbalance takes {sorted(allowed)}")
    if "g_mm" not in entry:
        raise ValueError(f"{where}.g_mm: the unbalance's size, grams times millimetres off the axis (like 50)")
    faces, at = _where_on_axis(entry, where)
    return UnbalanceInput(kinds.number(entry["g_mm"], where=f"{where}.g_mm", positive=True), faces, at,
                          kinds.number(entry.get("phase_deg", 0.0), where=f"{where}.phase_deg"))


def _spin(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("spin: how it spins, like {\"axis\": \"Z\", \"rpm\": [0, 12000]} (the operating speeds, rpm)")
    allowed = {"axis", "rpm", "sweep_rpm", "through_mm", "solid_modes"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"spin: unknown keys {sorted(unknown)}; spin takes {sorted(allowed)}")
    axis = raw.get("axis", "Z")
    if isinstance(axis, str) and axis.strip().upper() in _AXES:
        name = axis.strip().upper()
        unit = _AXES[name]
    elif isinstance(axis, list) and len(axis) == 3:
        values = [kinds.number(v, where="spin.axis") for v in axis]
        size = math.sqrt(sum(v * v for v in values))
        if size == 0:
            raise ValueError("spin.axis: the axis is zero; give \"X\", \"Y\", \"Z\" or a direction like [0, 0, 1]")
        unit = tuple(v / size for v in values)
        name = next((key for key, value in _AXES.items() if all(abs(a - b) < 1e-12 for a, b in zip(value, unit))), "")
    else:
        raise ValueError(f"spin.axis: \"X\", \"Y\", \"Z\" or a direction like [0, 0, 1], got {kinds.json_text(axis)}")
    if "rpm" not in raw:
        raise ValueError("spin.rpm: the operating speeds, [low, high] in rpm (like [0, 12000]), or the one speed it runs at")
    speeds = raw["rpm"]
    if isinstance(speeds, (int, float)) and not isinstance(speeds, bool):
        speeds = [speeds, speeds]
    if not isinstance(speeds, list) or len(speeds) != 2:
        raise ValueError("spin.rpm: the operating speeds as [low, high] in rpm, like [0, 12000]")
    low, high = (kinds.number(value, where="spin.rpm") for value in speeds)
    if low < 0 or high < low or not high > 0:
        raise ValueError(f"spin.rpm: low ({low:g}) must be 0 or more and no more than high ({high:g}), and high above 0")
    out: dict[str, Any] = {"axis": unit, "axis_name": name, "rpm": (low, high)}
    if raw.get("sweep_rpm") is not None:
        sweep = kinds.number(raw["sweep_rpm"], where="spin.sweep_rpm", positive=True)
        if sweep < high:
            raise ValueError(f"spin.sweep_rpm: the Campbell diagram's top speed must reach the top operating speed ({high:g}), "
                             f"got {sweep:g}")
        out["sweep_rpm"] = sweep
    if raw.get("through_mm") is not None:
        point = raw["through_mm"]
        if not isinstance(point, list) or len(point) != 3:
            raise ValueError("spin.through_mm: a point the spin axis passes through, [x, y, z] in mm")
        out["through_mm"] = tuple(kinds.number(v, where="spin.through_mm") for v in point)
    if "solid_modes" in raw:
        count = raw["solid_modes"]
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 12:
            raise ValueError(f"spin.solid_modes: how many of the solid's own modes to find at rest and spinning, 0 to 12, "
                             f"got {kinds.json_text(count)}")
        out["solid_modes"] = count
    return out


def _parsed_checks(document: dict) -> tuple[dict, ...]:
    """The study's checks of this analysis's kinds, parsed (a malformed one is left for the study's own parse)."""
    view = document.get("view")
    entries = view.get("checks") if isinstance(view, dict) else None
    specs = {spec.kind: spec for spec in RotordynamicsAnalysis.checks}
    found = []
    for index, entry in enumerate(entries if isinstance(entries, list) else ()):
        if isinstance(entry, dict) and entry.get("kind") in specs:
            try:
                found.append(specs[entry["kind"]].parse(entry, f"view.checks[{index}]"))
            except ValueError:
                continue
    return tuple(found) if found else tuple(dict(check) for check in RotordynamicsAnalysis.default_checks)


# -- the checks --------------------------------------------------------------------------------------------


def critical_check(check: dict, criticals: list[dict], operating: tuple[float, float], sweep_top: float) -> dict:
    """A critical_speed check judged on the criticals found (each ``rpm``, ``forward``, ``order``, ``mode``,
    ``frame``): the one nearest the operating range, its separation against ``margin_percent``. Inside the
    range fails; within the margin is close. ``value`` is its speed, ``limit`` the operating edge it is
    measured from (the top speed when inside) and ``reference`` the other edge. No critical in the sweep
    passes, its value the sweep's top (no critical up to it)."""
    low, high = operating
    margin = float(check.get("margin_percent", 15.0))
    orders = tuple(check.get("orders", (1.0,)))
    judged = [c for c in criticals if (c["forward"] or check.get("backward")) and any(abs(c["order"] - o) < 1e-9 for o in orders)]
    label = check.get("label") or kinds.CRITICAL_SPEED.default_label
    close_at = 1.0 / (1.0 + margin / 100.0)
    base = {"kind": "critical_speed", "label": label, "unit": "rpm", "close_at": round(close_at, 6),
            "required_percent": margin, "range_rpm": [low, high], "orders": list(orders)}

    def separation(rpm: float) -> float:
        if low <= rpm <= high:
            return -100.0 * min(rpm - low, high - rpm) / high
        if rpm > high:
            return 100.0 * (rpm - high) / high
        return 100.0 * (low - rpm) / low

    if not judged:
        sep = separation(sweep_top) if sweep_top > high else 0.0
        return {**base, "value": round(sweep_top, 3), "limit": high, "reference": low, "ratio": round(1.0 / (1.0 + sep / 100.0), 6),
                "status": "passes", "separation_percent": round(sep, 3), "none_below_rpm": round(sweep_top, 3)}
    nearest = min(judged, key=lambda c: separation(c["rpm"]))
    rpm = nearest["rpm"]
    sep = separation(rpm)
    inside = low <= rpm <= high
    if inside:
        edge, other, ratio, status = high, low, 1.0 + abs(sep) / 100.0 + 1e-6, "fails"
    else:
        edge, other = (high, low) if rpm > high else (low, high)
        ratio = 1.0 / (1.0 + sep / 100.0)
        status = "close" if sep < margin else "passes"
    judged_check = {**base, "value": round(rpm, 3), "limit": edge, "reference": other, "ratio": round(ratio, 6), "status": status,
                    "separation_percent": round(sep, 3), "whirl": "forward" if nearest["forward"] else "backward",
                    "order": nearest["order"], "mode": nearest["mode"]}
    if nearest.get("frame") is not None:
        judged_check["at"] = {"frame": nearest["frame"], "value": round(rpm, 3), "unit": "rpm"}
    return judged_check


def whirl_words(entry: dict) -> str:
    """A whirl mode counted in plain order among those whirling the same way: "1st forward whirl", "2nd backward whirl"."""
    mode = int(entry["mode"])
    suffix = "th" if 10 <= mode % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(mode % 10, "th")
    return f"{mode}{suffix} {entry['whirl']} whirl"


def stability_check(check: dict, lowest: dict | None, *, damped: bool = True) -> dict:
    """A stability check judged on the smallest log decrement over the operating speeds (``lowest``: ``value``,
    ``rpm``, ``forward``, ``mode``): under 0 fails (a whirl that grows), under ``min_log_dec`` is close. A rotor
    with no damper and no cross-coupled spring (``damped`` False) neither grows nor dies away: it passes at 0,
    ``undamped``, and its finding asks for the bearings' dampers."""
    need = float(check.get("min_log_dec", 0.1))
    label = check.get("label") or kinds.STABILITY.default_label
    base = {"kind": "stability", "label": label, "limit": need, "unit": "", "close_at": _STABLE_CLOSE_AT}
    if lowest is None:
        return {**base, "value": need, "ratio": 0.0, "status": "passes", "whirl_modes": 0}
    delta = lowest["value"]
    if abs(delta) < UNDAMPED:
        delta = 0.0
    if delta == 0.0 and not damped:
        # No mode named: the viewer's line says it is undamped, neither growing nor dying away.
        return {**base, "value": 0.0, "ratio": 0.0, "status": "passes", "undamped": True, "rpm": round(lowest["rpm"], 3)}
    if delta < 0:
        ratio, status = 1.0 + min(-delta, 1e3) + 1e-6, "fails"
    elif delta < need:
        ratio, status = 1.0 - (1.0 - _STABLE_CLOSE_AT) * delta / need, "close"
    else:
        ratio, status = _STABLE_CLOSE_AT * need / delta, "passes"
    return {**base, "value": round(delta, 6), "ratio": round(ratio, 6), "status": status, "rpm": round(lowest["rpm"], 3),
            "whirl": "forward" if lowest["forward"] else "backward", "mode": lowest["mode"]}


# -- the analysis ------------------------------------------------------------------------------------------


class RotordynamicsAnalysis:
    name: ClassVar[str] = "rotordynamics"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Spinning"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"spin", "bearings", "discs", "disc_model", "unbalance", "modes"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"density"})
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    # The spinning stress colours the part; each critical's whirl shape (its real part, the imaginary part beside it as
    # displacement_im for the Whirl routine) deforms it.
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress (spinning at the top speed)", "MPa"),
        FieldSpec("whirl", "_DISPLACEMENT", "whirl orbit", "mm", 3, 1000.0, per_frame=True),
    )
    checks: ClassVar[tuple] = (kinds.CRITICAL_SPEED, kinds.STABILITY, kinds.STRESS)
    default_checks: ClassVar[tuple[dict, ...]] = (
        {"kind": "critical_speed", "margin_percent": 15.0}, {"kind": "stability", "min_log_dec": 0.1}, {"kind": "stress"},
    )
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold", "mode")
    default_controls: ClassVar[dict[str, dict]] = {
        "mode": {"drives": "mode", "type": "enum", "options": None},
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "whirl"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("reduce_modes", "iterative", "local_refine")
    noun: ClassVar[str] = "this spin"
    governing_word: ClassVar[str] = "the spinning stress"

    # -- parse -------------------------------------------------------------------------------------------

    def parse(self, document: dict) -> RotordynamicsInputs:
        if "spin" not in document:
            raise ValueError("spin: a rotordynamics study needs how it spins, like {\"axis\": \"Z\", \"rpm\": [0, 12000]}")
        spin = _spin(document["spin"])
        raw = document.get("bearings")
        if not isinstance(raw, list) or not raw:
            raise ValueError("bearings: a rotor needs the bearings it runs in, like [{\"faces\": [\"#o1.f3\"], \"rigid\": true}, "
                             "{\"faces\": [\"#o1.f9\"], \"k\": 20000, \"c\": 5}] (springs N/mm, dampers N s/mm)")
        bearings = tuple(_bearing(entry, i) for i, entry in enumerate(raw))
        discs_raw = document.get("discs", [])
        if not isinstance(discs_raw, list):
            raise ValueError("discs: a list of discs the CAD leaves out, each {\"at_mm\", \"mass_kg\", \"polar_kg_mm2\", "
                             "\"diametral_kg_mm2\"}")
        discs = tuple(_disc(entry, i) for i, entry in enumerate(discs_raw))
        model = document.get("disc_model", "rigid")
        if model not in ("rigid", "flexible"):
            raise ValueError(f"disc_model: \"rigid\" (a disc found in the CAD lumped at its centre) or \"flexible\" (kept as its "
                             f"own sections), got {kinds.json_text(model)}")
        unbalance_raw = document.get("unbalance", [])
        if isinstance(unbalance_raw, dict):
            unbalance_raw = [unbalance_raw]
        if not isinstance(unbalance_raw, list):
            raise ValueError("unbalance: a list like [{\"faces\": [\"#o1.f5\"], \"g_mm\": 50}]")
        unbalance = tuple(_unbalance(entry, i) for i, entry in enumerate(unbalance_raw))
        modes = document.get("modes", DEFAULT_CURVES)
        if isinstance(modes, bool) or not isinstance(modes, int) or not 1 <= modes <= MAX_CURVES:
            raise ValueError(f"modes: how many whirl curves to track each way (forward and backward), 1 to {MAX_CURVES}, "
                             f"got {kinds.json_text(modes)}")
        solid_modes = spin.get("solid_modes", 0)
        if solid_modes and not any(bearing.faces for bearing in bearings):
            raise ValueError("spin.solid_modes: the solid's own modes are found held at its bearing faces; give at least one "
                             "bearing by faces")
        refs = tuple(dict.fromkeys([*(ref for b in bearings for ref in b.faces), *(ref for u in unbalance for ref in u.faces)]))
        anchors = tuple(dict.fromkeys(ref for b in bearings for ref in b.faces))
        return RotordynamicsInputs(
            refs, anchors, False, axis=spin["axis"], axis_name=spin["axis_name"], through_mm=spin.get("through_mm"),
            rpm=spin["rpm"], sweep_rpm=spin.get("sweep_rpm"), bearings=bearings, discs=discs, disc_model=model,
            unbalance=unbalance, modes=modes, solid_modes=solid_modes, checks=_parsed_checks(document),
        )

    # -- the ladder ----------------------------------------------------------------------------------------

    def _rotor_cost(self, ctx: SolveContext, inputs: RotordynamicsInputs):
        planned = getattr(getattr(ctx, "plan", None), "modes", None)
        nodes = int(ROTOR_ELEMENTS * 1.15) + 2 * len(inputs.bearings) + len(inputs.discs) + len(inputs.unbalance) + 1
        state = 2 * (planned if planned else 4 * nodes)
        seconds = EIG_SECONDS_PER_CUBE * state ** 3 * (EVALUATIONS + 6 * inputs.modes)
        return seconds, 16.0 * 8 * state * state

    def estimate(self, ctx: SolveContext, inputs: RotordynamicsInputs):
        """The spinning-stress solve on the plan's mesh (:func:`fit.solid_estimate`), the solid's modes when asked
        (:func:`modal.eigen_estimate`, at rest and spinning), and the rotor line's dense eigen solves."""
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.modal import eigen_estimate

        seconds, memory = self._rotor_cost(ctx, inputs)
        if inputs.solid_modes:
            base = eigen_estimate(ctx, inputs.solid_modes + 2, static_solves=1)
            base = fit.Estimate(base.dofs, base.memory_bytes, base.seconds * 2.0)
        else:
            base = fit.solid_estimate(ctx)
        return fit.Estimate(base.dofs, int(base.memory_bytes + memory), float(base.seconds + seconds))

    def apply(self, rung, ctx: SolveContext, inputs: RotordynamicsInputs):
        """``reduce_modes``: the rotor line projected on its slowest bending shapes (its whirl, criticals and
        response then cost almost nothing). ``iterative`` and ``local_refine`` the shared way, for the solid."""
        from cadgen._internal.fea import fit

        if rung == "reduce_modes":
            if ctx.plan.modes is not None:
                return None
            keep = max(4 * inputs.modes + 12, 24)
            before = self.estimate(ctx, inputs)
            ctx.plan.modes = keep
            after = self.estimate(ctx, inputs)
            if after.seconds >= 0.95 * before.seconds:
                ctx.plan.modes = None
                return None
            return fit.Step("reduce_modes", f"Found the rotor's whirl from its {keep} slowest bending shapes, to finish sooner",
                            None, None, detail={"kept_shapes": keep})
        return fit.apply_generic(rung, self, ctx, inputs)

    def governing(self, result: AnalysisResult) -> tuple["np.ndarray", float]:
        """What local_refine's two passes follow and compare: the spinning stress, and its peak."""
        field = result.fields["von_mises"]
        return field, float(field.max())

    def settle_steps(self, result: AnalysisResult, steps: list) -> list:
        """reduce_modes said again with what it cost: the first whirl frequency against the full rotor's."""
        from cadgen._internal.fea import fit

        return fit.settle_step(steps, "reduce_modes", result.scalars.get("reduce_settled"))

    # -- solve ---------------------------------------------------------------------------------------------

    def _parts(self, ctx: SolveContext):
        if ctx.assembly is not None:
            return [(part.shape, material) for part, material in zip(ctx.assembly.parts, ctx.assembly.materials)]
        shape = getattr(ctx.geometry, "shape", None)
        if shape is None:
            raise ValueError("rotordynamics needs the part's shape to cut the rotor line from")
        return [(shape, ctx.materials[0])]

    @staticmethod
    def _breakpoints(parts, frame) -> list[float]:
        """Every vertex of the parts, as a position along the axis: where the CAD's sections can change."""
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        found = set()
        for shape, _ in parts:
            explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
            while explorer.More():
                point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(explorer.Current()))
                found.add(round(frame.s((point.X(), point.Y(), point.Z())), 9))
                explorer.Next()
        return sorted(found)

    @staticmethod
    def _centre(parts) -> tuple[float, float, float]:
        """The parts' mass centre: the default point the spin axis passes through."""
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        total, moment = 0.0, [0.0, 0.0, 0.0]
        for shape, material in parts:
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, props)
            mass = float(props.Mass()) * max(material.density, 1e-30)
            centre = props.CentreOfMass()
            total += mass
            for c, value in enumerate((centre.X(), centre.Y(), centre.Z())):
                moment[c] += mass * value
        return tuple(m / total for m in moment) if total > 0 else (0.0, 0.0, 0.0)  # type: ignore[return-value]

    def _station(self, ctx: SolveContext, frame, faces: tuple[str, ...], at: float | None) -> float:
        if at is not None:
            return float(at)
        import numpy as np

        centres = [ctx.volume.faces[ctx.ordinal_of[ref]] for ref in faces]
        area = sum(face.area for face in centres)
        point = sum(np.array(face.center) * face.area for face in centres) / area if area > 0 else np.array(centres[0].center)
        return frame.s(point)

    def solve(self, ctx: SolveContext, inputs: RotordynamicsInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import rotor as rd

        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        parts = self._parts(ctx)
        origin = inputs.through_mm or self._centre(parts)
        frame = rd.frame_of(inputs.axis, origin)
        a, e1, e2, o = (np.array(v, dtype=float) for v in (frame.a, frame.e1, frame.e2, frame.origin))
        nodes = np.asarray(ctx.volume.nodes, dtype=float)
        s_nodes = nodes @ a
        rel = nodes - o
        across = rel - np.outer(rel @ a, a)
        radius = float(np.linalg.norm(across, axis=1).max()) * 1.05 + 1.0
        extent = (float(s_nodes.min()), float(s_nodes.max()))
        length = extent[1] - extent[0]

        def on_rotor(s: float, where: str) -> float:
            if not extent[0] - 1e-6 * length <= s <= extent[1] + 1e-6 * length:
                raise ValueError(f"{where}: {s:.4g} mm along the spin axis is off the rotor, which runs from {extent[0]:.4g} "
                                 f"to {extent[1]:.4g} mm")
            return min(max(s, extent[0]), extent[1])

        bearing_s = [on_rotor(self._station(ctx, frame, b.faces, b.at_mm), f"bearings[{i}]") for i, b in enumerate(inputs.bearings)]
        unbalance_s = [on_rotor(self._station(ctx, frame, u.faces, u.at_mm), f"unbalance[{i}]") for i, u in enumerate(inputs.unbalance)]
        added = [rd.FoundDisc(on_rotor(d.at_mm, f"discs[{i}]"), on_rotor(d.at_mm, f"discs[{i}]"), on_rotor(d.at_mm, f"discs[{i}]"),
                              d.mass_kg * 1e-3, d.diametral_kg_mm2 * 1e-3, d.polar_kg_mm2 * 1e-3, "study")
                 for i, d in enumerate(inputs.discs)]
        line = rd.build_line(parts, frame, extent, radius, breakpoints=self._breakpoints(parts, frame),
                             stations=[*bearing_s, *unbalance_s, *(d.centre for d in added)], elements=ROTOR_ELEMENTS,
                             disc_model=inputs.disc_model, added=added, log=ctx.log)
        # An unbalance inside a lumped disc acts at the disc's centre, where its mass is.
        for k, s in enumerate(unbalance_s):
            for lo, hi in line.lumped:
                if lo - 1e-9 <= s <= hi + 1e-9:
                    unbalance_s[k] = next(d.centre for d in line.discs if d.s0 == lo and d.s1 == hi)
        bearings = []
        for b, s in zip(inputs.bearings, bearing_s):
            bearings.append(rd.Bearing(line.node_at(s), *(b.value(name) for name in COEFFICIENTS),
                                       rigid=b.rigid, clamped=b.clamped))
        rotor = rd.Rotor(line.rotor.stations, line.rotor.elements, line.rotor.discs, tuple(bearings))
        timings["rotor_line_s"] = time.perf_counter() - started

        # -- the whirl --------------------------------------------------------------------------------------
        started = time.perf_counter()
        basis = None
        planned = getattr(getattr(ctx, "plan", None), "modes", None)
        if planned:
            basis = rd.modal_basis(rotor, planned, rpm=0.5 * (inputs.rpm[0] + inputs.rpm[1]))
            if basis is None:
                warnings.append("the rotor line is too small to project; its whirl was solved in full")
        system = rd.System.of(rotor, basis)
        sweep_top = _omega(inputs.sweep_top_rpm)
        # A whirl slower than a millionth of the sweep's top is a rigid-body motion (a tilt nothing holds), not a mode.
        scale = sweep_top
        speeds = np.linspace(0.0, sweep_top, CAMPBELL_SPEEDS)
        chart = rd.campbell(system, speeds, inputs.modes, scale=scale)
        # A crossing at a standstill is a rigid-body motion's, not a critical speed.
        found = [c for c in rd.critical_speeds(system, chart, inputs.orders, scale=scale) if c.omega > 1e-3 * sweep_top]
        timings["campbell_s"] = time.perf_counter() - started
        reduce_settled = None
        if basis is not None:
            full = rd.System.of(rotor)
            top = _omega(inputs.rpm[1])
            exact = rd.whirl(full, top, scale=scale)
            approx = rd.whirl(system, top, scale=scale)
            if exact and approx:
                moved = 100.0 * abs(approx[0].omega - exact[0].omega) / exact[0].omega
                said = f"{moved:.2f}%" if moved >= 0.005 else "under 0.01%"
                reduce_settled = {"accuracy": f"the first whirl frequency moved {said} against the full rotor at "
                                              f"{rpm_text(inputs.rpm[1])}", "accuracy_pct": moved,
                                  "detail": {"kept_shapes": int(basis.shape[1])}}

        # The criticals in words, and the frames: each critical's whirl shape, else the whirls at the top speed.
        frames_cap = int(getattr(getattr(ctx, "budget", None), "max_frames", 24) or 24)
        criticals = []
        for c in found:
            criticals.append({"rpm": c.rpm, "order": c.order, "forward": c.forward, "mode": c.mode,
                              "frequency_Hz": c.whirl.frequency_Hz, "log_decrement": c.whirl.log_decrement,
                              "frame": None, "shape": c.whirl.shape})
        # Frames: the forward criticals once per revolution first (the ones an unbalance drives), then the rest.
        shown = sorted(criticals, key=lambda c: (c["order"] != 1.0, not c["forward"], c["rpm"]))
        frames: list[dict] = []
        for c in shown[:frames_cap]:
            c["frame"] = len(frames)
            frames.append({"label": f"Critical · {rpm_text(c['rpm'])} · {'forward' if c['forward'] else 'backward'}"
                           + ("" if c["order"] == 1.0 else f" ({c['order']:g}×)"),
                           "shape": c["shape"], "rpm": c["rpm"]})
        if not frames:
            top = _omega(inputs.rpm[1])
            for w in rd.whirl(system, top, scale=scale)[:min(frames_cap, 2 * inputs.modes)]:
                frames.append({"label": f"{'Forward' if w.forward else 'Backward'} · {_hz(w.frequency_Hz)} at {rpm_text(inputs.rpm[1])}",
                               "shape": w.shape, "rpm": inputs.rpm[1]})
        if not frames:
            warnings.append("the rotor has no whirl mode it can be drawn in: every bearing holds it still")

        # Stability: the smallest log decrement over the operating speeds.
        low, high = inputs.rpm
        operating = [i for i, speed in enumerate(speeds) if _omega(low) - 1e-9 <= speed <= _omega(high) + 1e-9]
        extra = [_omega(low), _omega(high)]
        lowest = None
        for forward, decs in ((True, chart.forward_log_dec), (False, chart.backward_log_dec)):
            for i in operating:
                for j in range(decs.shape[1]):
                    if np.isfinite(decs[i, j]) and (lowest is None or decs[i, j] < lowest["value"]):
                        lowest = {"value": float(decs[i, j]), "rpm": _rpm(float(speeds[i])), "forward": forward, "mode": j + 1}
        for speed in extra:
            modes = rd.whirl(system, max(speed, 1e-6), scale=scale)
            for direction in (True, False):
                for j, w in enumerate([w for w in modes if w.forward == direction][:inputs.modes]):
                    if lowest is None or w.log_decrement < lowest["value"]:
                        lowest = {"value": w.log_decrement, "rpm": _rpm(speed), "forward": direction, "mode": j + 1}

        # -- unbalance -----------------------------------------------------------------------------------------
        started = time.perf_counter()
        unbalances, default_unbalance = self._unbalances(inputs, line, unbalance_s, rotor)
        grid = np.linspace(0.0, sweep_top, RESPONSE_SPEEDS)[1:]
        near = [c["rpm"] for c in criticals]
        if near:
            grid = np.unique(np.concatenate([grid, *[_omega(r) * (1.0 + np.array([-0.01, -0.003, 0.003, 0.01])) for r in near]]))
            grid = grid[(grid > 0) & (grid <= sweep_top)]
        response = rd.unbalance_response(system, [(node, U, phase) for node, U, phase, _ in unbalances], grid)
        timings["unbalance_s"] = time.perf_counter() - started
        largest = response.amplitude.max(axis=1)
        peak_index = int(np.argmax(largest))
        at_unbalance = response.amplitude[:, unbalances[0][0]]
        top_omega = _omega(high)
        at_top = rd.unbalance_response(system, [(node, U, phase) for node, U, phase, _ in unbalances], [top_omega])

        # -- the spinning solid --------------------------------------------------------------------------------
        started = time.perf_counter()
        vm, solid_warnings, sigma, solid_how = self._spin_stress(ctx, frame, top_omega)
        warnings.extend(solid_warnings)
        timings["spin_stress_s"] = time.perf_counter() - started
        solid_modes = None
        if inputs.solid_modes:
            started = time.perf_counter()
            solid_modes = self._solid_modes(ctx, inputs, frame, top_omega, sigma, warnings)
            timings["solid_modes_s"] = time.perf_counter() - started

        # -- onto the part's mesh ---------------------------------------------------------------------------------
        space = ctx.space
        locations = np.asarray(space.dof_locations, dtype=float)
        re_frames, im_frames = [], []
        for item in frames:
            re, im = self._on_mesh(locations, rotor.stations, item["shape"], frame)
            re_frames.append(re)
            im_frames.append(im)
        if not re_frames:
            re_frames, im_frames = [np.zeros_like(locations)], [np.zeros_like(locations)]
            frames = [{"label": "No whirl", "rpm": high}]
        series = Series(kind="mode", unit="rpm", default=0, frames=[
            SeriesFrame(value=float(i + 1), label=item["label"], attributes={
                "whirl": "_DISPLACEMENT" if i == 0 else f"_WHIRL_F{i}",
                "mode_shape": "_DISPLACEMENT" if i == 0 else f"_WHIRL_F{i}",
                "displacement_im": f"_DISPLACEMENT_IM_F{i}",
            })
            for i, item in enumerate(frames)
        ])

        rpm_axis = [round(_rpm(float(speed)), 4) for speed in speeds]

        def listed(values) -> list:
            return [None if not np.isfinite(v) else round(float(v), 6) for v in values]

        curves: dict[str, dict] = {}
        for j in range(inputs.modes):
            curves[f"forward_{j + 1}_Hz"] = {"x": rpm_axis, "x_unit": "rpm", "y": listed(chart.forward[:, j] / _TWO_PI), "y_unit": "Hz"}
            curves[f"backward_{j + 1}_Hz"] = {"x": rpm_axis, "x_unit": "rpm", "y": listed(chart.backward[:, j] / _TWO_PI), "y_unit": "Hz"}
            curves[f"forward_{j + 1}_log_dec"] = {"x": rpm_axis, "x_unit": "rpm", "y": listed(chart.forward_log_dec[:, j]), "y_unit": ""}
            curves[f"backward_{j + 1}_log_dec"] = {"x": rpm_axis, "x_unit": "rpm", "y": listed(chart.backward_log_dec[:, j]), "y_unit": ""}
        for order in inputs.orders:
            curves[f"order_{order:g}x_Hz"] = {"x": rpm_axis, "x_unit": "rpm", "y": [round(order * r / 60.0, 6) for r in rpm_axis], "y_unit": "Hz"}
        response_rpm = [round(_rpm(float(speed)), 4) for speed in grid]
        curves["unbalance_amplitude_mm"] = {"x": response_rpm, "x_unit": "rpm", "y": [round(float(v), 9) for v in largest], "y_unit": "mm"}
        curves["unbalance_amplitude_at_unbalance_mm"] = {"x": response_rpm, "x_unit": "rpm",
                                                         "y": [round(float(v), 9) for v in at_unbalance], "y_unit": "mm"}
        curves["unbalance_phase_deg"] = {"x": response_rpm, "x_unit": "rpm",
                                         "y": [round(float(v), 4) for v in response.phase[:, unbalances[0][0]]], "y_unit": "°"}

        materials = list(ctx.materials)
        stations = rotor.stations
        bearings_out = []
        for b, s, entry in zip(rotor.bearings, bearing_s, inputs.bearings):
            k, c = b.matrices(high)
            bearings_out.append({"at_mm": round(stations[b.node], 4), "faces": list(entry.faces), "rigid": b.rigid, "clamped": b.clamped,
                                 "kxx": k[0][0], "kyy": k[1][1], "kxy": k[0][1], "kyx": k[1][0],
                                 "cxx": c[0][0], "cyy": c[1][1], "cxy": c[0][1], "cyx": c[1][0],
                                 "speed_dependent": b.speed_dependent})
        discs_out = [{"at_mm": round(d.centre, 4), "from_mm": round(d.s0, 4), "to_mm": round(d.s1, 4),
                      "mass_kg": d.mass * 1000.0, "polar_kg_mm2": d.polar * 1000.0, "diametral_kg_mm2": d.diametral * 1000.0,
                      "source": d.source, "lumped": d.source == "study" or inputs.disc_model == "rigid"} for d in line.discs]
        node_of = {i: stations[i] for i in range(len(stations))}
        magnitude = [np.linalg.norm(re, axis=1) for re in re_frames]
        return AnalysisResult(
            dof_locations=space.dof_locations,
            vertices=space.vertices,
            tets=space.tets,
            boundary_quadratic=space.boundary_quadratic,
            element_dofs=space.element_dofs,
            fields={"von_mises": vm, "whirl": re_frames[0]},
            deformation=re_frames[0],
            series=series,
            frame_fields={"whirl": re_frames, "displacement_im": im_frames},
            curves=curves,
            scalars={
                "frame_axis": {"origin": [float(c) for c in frame.origin], "axis": [float(c) for c in frame.a],
                               "e1": [float(c) for c in frame.e1], "e2": [float(c) for c in frame.e2]},
                "axis_name": inputs.axis_name,
                "operating_rpm": [low, high],
                "sweep_rpm": inputs.sweep_top_rpm,
                "rotor_length_mm": length,
                "rotor_mass_kg": rotor.mass * 1000.0,
                "rotor_elements": len(rotor.elements),
                "stations_mm": list(stations),
                "bearings": bearings_out,
                "discs": discs_out,
                "criticals": [{k: v for k, v in c.items() if k != "shape"} for c in criticals],
                "lowest_log_dec": lowest,
                # Any damper or cross-coupled spring: without one, every whirl's log decrement is 0 and nothing is judged.
                "damped": any(b.value(name) != 0.0 for b in inputs.bearings for name in ("cxx", "cyy", "cxy", "cyx", "kxy", "kyx")),
                "unbalance": [{"at_mm": round(node_of[node], 4), "g_mm": U * 1e6, "phase_deg": math.degrees(phase), "default": dflt}
                              for node, U, phase, dflt in unbalances],
                "default_unbalance": default_unbalance,
                "unbalance_peak_mm": float(largest[peak_index]),
                "unbalance_peak_rpm": _rpm(float(grid[peak_index])),
                "unbalance_at_top_mm": float(at_top.amplitude[0].max()),
                "unbalance_at_top_at_unbalance_mm": float(at_top.amplitude[0, unbalances[0][0]]),
                "solid_modes": solid_modes,
                "magnitudes": magnitude,
                "reduce_settled": reduce_settled,
                "margin": float(getattr(ctx.study, "margin", 2.0) or 2.0),
                "yields": [m.yield_strength for m in materials],
                "node_domain": self._node_domain(space),
                "analysis_warnings": list(warnings),
                "parts": None if ctx.assembly is None else [
                    {"ref": part.ref, "name": name, "material": material.name}
                    for part, name, material in zip(ctx.assembly.parts, ctx.assembly.names, ctx.assembly.materials)
                ],
            },
            dofs=int(space.dofs),
            solver="dense state-space eigen (rotor line)" + ("" if basis is None else f", {basis.shape[1]} shapes")
                   + f"; spinning stress: {solid_how}",
            timings=timings,
            warnings=warnings,
        )

    @staticmethod
    def _node_domain(space):
        """Each scalar DOF's part (an assembly), from the elements around it; None for one part."""
        import numpy as np

        if space.domain is None:
            return None
        domain = np.zeros(space.scalar_count, dtype=int)
        domain[space.scalar.element_dofs] = np.asarray(space.domain)[None, :]
        return domain

    def _unbalances(self, inputs: RotordynamicsInputs, line, unbalance_s: list[float], rotor):
        """((node, U t·mm, phase rad, default), ...), and the default's words when the study gave none."""
        if inputs.unbalance:
            return [(line.node_at(s), u.g_mm * 1e-6, math.radians(u.phase_deg), False)
                    for u, s in zip(inputs.unbalance, unbalance_s)], None
        heaviest = max(line.discs, key=lambda d: d.mass, default=None)
        if heaviest is not None:
            node = line.node_at(heaviest.centre)
        else:
            stations = rotor.stations
            centre = sum(0.5 * (stations[i] + stations[i + 1]) * e.mass * e.length for i, e in enumerate(rotor.elements))
            centre /= max(sum(e.mass * e.length for e in rotor.elements), 1e-30)
            node = line.node_at(centre)
        top = _omega(inputs.rpm[1])
        U = rotor.mass * DEFAULT_GRADE_MM_S / top          # t·mm: the rotor's mass times its permissible offset e = G/Ω
        words = {"grade": "G2.5", "g_mm": U * 1e6, "at_mm": rotor.stations[node],
                 "at": "the heaviest disc" if heaviest is not None else "the rotor's mass centre"}
        return [(node, U, 0.0, True)], words

    @staticmethod
    def _on_mesh(locations: "np.ndarray", stations, shape: "np.ndarray", frame):
        """A whirl shape on the part's mesh: each point moves with its section (across, and along the axis as the
        section turns), real and imaginary parts, scaled so its largest motion is 1 mm."""
        import numpy as np

        from cadgen._internal.fea import rotor as rd

        a, e1, e2, o = (np.array(v, dtype=float) for v in (frame.a, frame.e1, frame.e2, frame.origin))
        s = locations @ a
        rel = locations - o
        x1, x2 = rel @ e1, rel @ e2
        per_node = np.stack([shape[0::4], shape[1::4], shape[2::4], shape[3::4]], axis=1)
        values = rd.interpolate(stations, per_node, s)
        u, bu, v, bv = values[:, 0], values[:, 1], values[:, 2], values[:, 3]
        w = -(bu * x1 + bv * x2)
        motion = u[:, None] * e1 + v[:, None] * e2 + w[:, None] * a
        size = float(np.sqrt((np.abs(motion) ** 2).sum(axis=1)).max())
        if size > 0:
            motion = motion / size
        return motion.real.copy(), motion.imag.copy()

    def _spin_stress(self, ctx: SolveContext, frame, omega: float):
        """The von Mises stress of the part spinning at ``omega`` (rad/s), per scalar DOF, its warnings, and the
        stress at the quadrature points (the solid modes' prestress), and how it was solved. The part is held by nothing: the load is made
        self-balanced (inertia relief), six DOF are pinned to stop it drifting, so the stress is the spin's alone."""
        import numpy as np
        from skfem import LinearForm, asm

        from cadgen._internal.fea import operators
        from cadgen._internal.fea.analyses.modal import materials_of

        space = ctx.space
        warnings: list[str] = []
        materials = materials_of(ctx)
        K = operators.stiffness(space, materials)
        M = operators.mass(space, materials)
        rho = operators.domain_values(space, [m.density for m in ctx.materials])
        rho = rho if not isinstance(rho, float) else np.full(space.basis.dx.shape, rho)
        o, a = np.array(frame.origin, dtype=float), np.array(frame.a, dtype=float)

        @LinearForm
        def centrifugal(v, w):
            d = [w.x[c] - o[c] for c in range(3)]
            along = d[0] * a[0] + d[1] * a[1] + d[2] * a[2]
            return w["rho"] * omega ** 2 * sum((d[c] - along * a[c]) * v[c] for c in range(3))

        f = asm(centrifugal, space.basis, rho=rho)
        R = operators.rigid_body_modes(space.locations, space.component)
        MR = M @ R
        f = f - MR @ np.linalg.solve(R.T @ MR, R.T @ f)          # inertia relief: what is left balances itself
        fixed = self._pins(space, R)
        free = np.setdiff1d(np.arange(space.dofs), fixed)
        plan = getattr(ctx, "plan", None)
        method = {"direct": "direct", "iterative": "iterative", "matrix_free": "iterative"}.get(getattr(plan, "solver", "direct"))
        u = np.zeros(space.dofs)
        u[free], how = operators.solve_spd(K, f, free, space.locations, space.component, warnings, method=method)
        sigma = operators.stress(space, materials, u)
        vm_q = operators.von_mises(sigma)
        if space.domain is None:
            vm = np.maximum(space.scalar.project(vm_q), 0.0)
        else:
            vm = np.zeros(space.scalar_count)
            for index in np.unique(space.domain):
                vm = np.maximum(vm, self._project_part(space, vm_q, np.asarray(space.domain) == index))
        return vm, warnings, sigma, how

    @staticmethod
    def _pins(space, R) -> "np.ndarray":
        """Six DOF that hold the part's six rigid motions and no more: at three corners far apart, the six rows of the
        rigid-body modes a pivoted QR chooses."""
        import numpy as np
        import scipy.linalg as la

        corners = np.arange(space.vertices)
        points = space.dof_locations[corners]
        centre = points.mean(axis=0)
        first = corners[int(np.argmax(np.linalg.norm(points - centre, axis=1)))]
        second = corners[int(np.argmax(np.linalg.norm(points - space.dof_locations[first], axis=1)))]
        line = space.dof_locations[second] - space.dof_locations[first]
        line /= max(np.linalg.norm(line), 1e-30)
        offset = points - space.dof_locations[first]
        off_line = np.linalg.norm(offset - np.outer(offset @ line, line), axis=1)
        third = corners[int(np.argmax(off_line))]
        candidates = np.concatenate([space.basis.nodal_dofs[:, node] for node in (first, second, third)])
        _, _, pivots = la.qr(R[candidates].T, pivoting=True)
        return np.sort(candidates[pivots[:6]])

    @staticmethod
    def _project_part(space, field, rows) -> "np.ndarray":
        """The L2 projection of a quadrature-point field onto the scalar basis over one part's elements."""
        import numpy as np
        import scipy.sparse.linalg as spla
        from skfem import Basis, BilinearForm, LinearForm, asm

        scalar = space.scalar
        elements = np.flatnonzero(rows)
        own = Basis(scalar.mesh, scalar.elem, elements=elements, quadrature=scalar.quadrature, dofs=scalar.dofs)
        used = np.unique(own.element_dofs)

        @BilinearForm
        def mass(u, v, w):
            return u * v

        @LinearForm
        def moment(v, w):
            return w["field"] * v

        Mp = asm(mass, own).tocsr()[used][:, used]
        b = asm(moment, own, field=field[elements])[used]
        out = np.zeros(scalar.N)
        out[used] = np.maximum(spla.spsolve(Mp.tocsc(), b), 0.0)
        return out

    def _solid_modes(self, ctx: SolveContext, inputs: RotordynamicsInputs, frame, omega: float, sigma, warnings: list[str]):
        """The solid's own lowest modes held at its bearing faces, at rest and spinning at ``omega``: the spinning
        ones with the spin's stress stiffening and its spin softening (K + Kσ − Ω²M⊥), in the rotating frame."""
        import numpy as np
        from skfem import BilinearForm, asm

        from cadgen._internal.fea import eigen, operators
        from cadgen._internal.fea.analyses.modal import held_supports, materials_of
        from cadgen._internal.fea.study import Fixture

        space = ctx.space
        materials = materials_of(ctx)
        K = operators.stiffness(space, materials)
        M = operators.mass(space, materials)
        rho = operators.domain_values(space, [m.density for m in ctx.materials])
        rho = rho if not isinstance(rho, float) else np.full(space.basis.dx.shape, rho)
        a = np.array(frame.a, dtype=float)

        @BilinearForm
        def across(u, v, w):
            along_u = u[0] * a[0] + u[1] * a[1] + u[2] * a[2]
            along_v = v[0] * a[0] + v[1] * a[1] + v[2] * a[2]
            return w["rho"] * (u[0] * v[0] + u[1] * v[1] + u[2] * v[2] - along_u * along_v)

        Mp = asm(across, space.basis, rho=rho)
        Kg = operators.geometric_stiffness(space, sigma)
        held = held_supports(space, (Fixture(inputs.bearing_faces),), ctx.ordinal_of)
        free = np.setdiff1d(np.arange(space.dofs), held.fixed)
        count = inputs.solid_modes
        Mff = M[free][:, free].tocsr()
        rest = eigen.shift_invert(K[free][:, free].tocsr(), Mff, count, 0.0)
        spinning = eigen.shift_invert((K + Kg - omega ** 2 * Mp)[free][:, free].tocsr(), Mff, count, 0.0)
        out = []
        for i in range(min(len(rest.values), len(spinning.values))):
            at_rest, spun = rest.values[i], spinning.values[i]
            out.append({"mode": i + 1, "at_rest_Hz": math.sqrt(max(at_rest, 0.0)) / _TWO_PI,
                        "spinning_Hz": math.sqrt(max(spun, 0.0)) / _TWO_PI, "softened_through": bool(spun < 0)})
            if spun < 0:
                warnings.append(f"the solid's mode {i + 1} has no stiffness left at the top speed: spin softening outruns it")
        return out

    # -- checks, findings ------------------------------------------------------------------------------------

    def _stress_check(self, result: AnalysisResult, check: dict, ctx: SolveContext) -> dict:
        import numpy as np

        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.static import peak_face

        vm = result.fields["von_mises"]
        node = int(np.argmax(vm))
        peak = float(vm[node])
        yields = result.scalars["yields"]
        domains = result.scalars["node_domain"]
        yield_MPa = yields[0] if domains is None or len(yields) == 1 else yields[int(domains[node])]
        at = tuple(float(c) for c in result.dof_locations[node])
        solved = checks.Solved(
            material_name="", yield_MPa=yield_MPa, peak_MPa=peak, peak_gauss_MPa=peak, peak_at=at,
            peak_face=peak_face(ctx.volume, result, node, set()), fixed_faces=(), max_displacement_mm=0.0,
            displacement_at=at, bbox_diagonal_mm=0.0, margin=result.scalars["margin"], coarser_peak_MPa=None, part="",
        )
        return checks.stress_check(solved, label=check.get("label") or "Spin stress")

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: RotordynamicsInputs) -> dict:
        scalars = result.scalars
        kind = check["kind"]
        if kind == "critical_speed":
            judged = critical_check(check, scalars["criticals"], tuple(scalars["operating_rpm"]), scalars["sweep_rpm"])
            frame = judged.get("at", {}).get("frame")
            magnitude = scalars["magnitudes"][frame if frame is not None and frame < len(scalars["magnitudes"]) else 0]
            from cadgen._internal.fea.analyses.modal import where_moves

            judged["where"] = where_moves(ctx, result, magnitude, index)
            return judged
        if kind == "stability":
            judged = stability_check(check, scalars["lowest_log_dec"], damped=scalars["damped"])
            judged["where"] = {"ref": None, "at": None}
            return judged
        return self._stress_check(result, check, ctx)

    def needs_finer(self, result: AnalysisResult, inputs: RotordynamicsInputs, check_results: list[dict]) -> bool:
        """Solve once more finer when the spinning stress is close to its limit."""
        if check_results:
            return any(check["kind"] == "stress" and check["status"] == "close" for check in check_results)
        if not any(check.get("kind") == "stress" for check in inputs.checks):
            return False
        vm = result.fields["von_mises"]
        node = int(vm.argmax())
        yields, domains = result.scalars["yields"], result.scalars["node_domain"]
        yield_MPa = yields[0] if domains is None or len(yields) == 1 else yields[int(domains[node])]
        if not yield_MPa:
            return False
        ratio = float(vm[node]) / yield_MPa
        return 1.0 / result.scalars["margin"] < ratio <= 1.0

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        return {"from_size_mm": round(size_mm, 4), "from_max_von_mises_MPa": round(float(result.fields["von_mises"].max()), 4),
                "size_mm": round(finer_mm, 4), "max_von_mises_MPa": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        refined["max_von_mises_MPa"] = round(float(finer.fields["von_mises"].max()), 4)
        finer.scalars["coarser_peak_MPa"] = float(coarse.fields["von_mises"].max())
        return finer

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: RotordynamicsInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.analyses.modal import finding

        scalars = result.scalars
        whole = "The assembly" if assembly else "The rotor"
        low, high = scalars["operating_rpm"]
        span = f"{rpm_text(low)}–{rpm_text(high)}" if low > 0 else f"up to {rpm_text(high)}"
        found: list[dict] = []
        for check in check_results:
            status = check["status"]
            if check["kind"] == "critical_speed" and "mode" in check and status in ("fails", "close"):
                which = whirl_words(check)
                at = rpm_text(check["value"])
                if status == "fails":
                    sentence = f"{whole} runs at a critical speed: {which} meets the spin at {at}, inside its {span} operating range"
                else:
                    side = "above" if check["value"] > check["limit"] else "below"
                    sentence = (f"{whole} runs close to a critical speed: {which} meets the spin at {at}, "
                                f"{abs(check['separation_percent']):.0f}% {side} the {rpm_text(check['limit'])} "
                                f"{'top' if side == 'above' else 'lowest'} speed, under the {check['required_percent']:g}% asked ({check['label']})")
                found.append(finding("error" if status == "fails" else "warning",
                                     "critical_speed_inside" if status == "fails" else "critical_speed_close", sentence,
                                     "a critical speed is where a whirl's natural frequency meets the spin: the unbalance drives it "
                                     "at resonance and the orbit grows",
                                     [{"text": check["label"], **check["where"]}]))
            elif check["kind"] == "stability" and check.get("undamped"):
                found.append(finding("info", "undamped_whirl",
                                     f"No damping is modelled, so {whole.lower()}'s whirl neither dies away nor grows; give the "
                                     "bearings' dampers (c, or cxx and cyy) to judge its stability",
                                     "rigid bearings and springs alone take no energy out of a whirl: its log decrement is 0", []))
            elif check["kind"] == "stability" and status in ("fails", "close"):
                if status == "fails":
                    sentence = (f"{whole} is unstable: {whirl_words(check)} grows at {rpm_text(check['rpm'])} "
                                f"(log decrement {check['value']:.3g})")
                    kind = "unstable_whirl"
                else:
                    sentence = (f"{whole}'s {whirl_words(check)} is barely damped at {rpm_text(check['rpm'])}: "
                                f"log decrement {check['value']:.3g}, under the {check['limit']:g} asked ({check['label']})")
                    kind = "barely_damped_whirl"
                found.append(finding("error" if status == "fails" else "warning", kind, sentence,
                                     "the log decrement is how much a whirl's orbit shrinks each turn (as a natural log); "
                                     "below 0 it grows", []))
            elif check["kind"] == "stress" and status in ("fails", "close"):
                factor = check["limit"] / check["value"] if check["value"] > 0 else math.inf
                sentence = (f"Spinning at {rpm_text(high)}, the part is stressed to {check['value']:.4g} MPa, "
                            + ("past its yield" if status == "fails" else f"a safety factor of {math.floor(factor * 100) / 100:g}, "
                               f"under the {check.get('margin', 2):g} asked") + f" ({check['label']})")
                found.append(finding("error" if status == "fails" else "warning",
                                     "spin_stress_over_yield" if status == "fails" else "spin_stress_close", sentence,
                                     "the centrifugal load ρΩ²r grows with the square of the speed",
                                     [{"text": check["label"], **check["where"]}]))
        criticals = scalars["criticals"]
        forward = [c for c in criticals if c["forward"] and c["order"] == 1.0]
        if forward:
            found.append(finding("info", "critical_speeds",
                                 "Critical speeds (forward, once per revolution): " + ", ".join(rpm_text(c["rpm"]) for c in forward),
                                 "where a forward whirl meets the 1× line of the Campbell diagram; an unbalance drives each", []))
        else:
            found.append(finding("info", "no_critical_speed", f"No forward critical speed up to {rpm_text(scalars['sweep_rpm'])}",
                                 "no forward whirl meets the 1× line in the sweep", []))
        default = scalars.get("default_unbalance")
        if default:
            found.append(finding("info", "default_unbalance",
                                 f"No unbalance was given: used balance grade G2.5 at {default['at']}, {default['g_mm']:.3g} g·mm",
                                 "ISO 21940-11's G2.5 (turbines, compressors, spindles): the permissible offset is 2.5 mm/s "
                                 "over the top speed", []))
        if scalars["unbalance_peak_mm"] <= 0:
            found.append(finding("info", "rotor_held_still", "The bearings hold the rotor line still: no whirl and no orbit",
                                 "every bearing is clamped, so the line has nothing left to whirl in", []))
        else:
            found.append(finding("info", "unbalance_peak",
                                 f"The unbalance's orbit peaks at {orbit_text(scalars['unbalance_peak_mm'])} at "
                                 f"{rpm_text(scalars['unbalance_peak_rpm'])}; at the top speed it is "
                                 f"{orbit_text(scalars['unbalance_at_top_mm'])}",
                                 "the largest radius of the orbit anywhere along the rotor", []))
        for item in scalars.get("solid_modes") or []:
            found.append(finding("info", "solid_mode_spinning",
                                 f"The solid's mode {item['mode']} is {_hz(item['at_rest_Hz'])} at rest and "
                                 f"{_hz(item['spinning_Hz'])} spinning at {rpm_text(high)}",
                                 "stress stiffening raises a spinning blade's or disc's frequency; spin softening lowers it", []))
        coarser = scalars.get("coarser_peak_MPa")
        if coarser:
            now = float(result.fields["von_mises"].max())
            moved = abs(now - coarser) / now if now > 0 else 0.0
            found.append(finding("warning" if moved > 0.05 else "info", "mesh_not_converged" if moved > 0.05 else "mesh_converged",
                                 f"The spinning stress moved {moved * 100:.1f} % on a finer mesh",
                                 "the stress was close to its limit, so the part was solved again finer; the finer answer is the one reported", []))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written ---------------------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        from cadgen._internal.fea.outputs import auto_deformation_scale

        return requested or auto_deformation_scale(1.0, bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: RotordynamicsInputs, check_results: list[dict]) -> dict:
        import numpy as np

        scalars = result.scalars
        vm = result.fields["von_mises"]
        node = int(np.argmax(vm))
        peak = float(vm[node])
        yields, domains = scalars["yields"], scalars["node_domain"]
        yield_MPa = yields[0] if domains is None or len(yields) == 1 else yields[int(domains[node])]
        factor = None if not peak or not yield_MPa else math.floor(yield_MPa / peak * 1000) / 1000

        def r(value, digits=4):
            return None if value is None else round(float(value), digits)

        lowest = scalars["lowest_log_dec"]
        summary: dict[str, Any] = {
            "spin": {"axis": scalars["axis_name"] or [round(c, 6) for c in scalars["frame_axis"]["axis"]],
                     "operating_rpm": list(scalars["operating_rpm"]), "sweep_rpm": r(scalars["sweep_rpm"], 3),
                     "through_mm": [round(c, 4) for c in scalars["frame_axis"]["origin"]]},
            "rotor": {"length_mm": r(scalars["rotor_length_mm"]), "mass_kg": r(scalars["rotor_mass_kg"], 6),
                      "elements": scalars["rotor_elements"], "disc_model": inputs.disc_model},
            "bearings": [{key: (r(value, 6) if isinstance(value, float) else value) for key, value in b.items()} for b in scalars["bearings"]],
            "discs": [{key: (r(value, 6) if isinstance(value, float) else value) for key, value in d.items()} for d in scalars["discs"]],
            "critical_speeds": [
                {"rpm": r(c["rpm"], 3), "order": c["order"], "whirl": "forward" if c["forward"] else "backward", "mode": c["mode"],
                 "frequency_Hz": r(c["frequency_Hz"]), "log_decrement": r(c["log_decrement"], 6), "frame": c["frame"]}
                for c in scalars["criticals"]
            ],
            "first_critical_rpm": next((r(c["rpm"], 3) for c in scalars["criticals"] if c["forward"] and c["order"] == 1.0), None),
            "lowest_log_decrement": None if lowest is None else {
                "value": r(0.0 if abs(lowest["value"]) < UNDAMPED else lowest["value"], 6), "rpm": r(lowest["rpm"], 3),
                "whirl": "forward" if lowest["forward"] else "backward", "mode": lowest["mode"]},
            "unbalance": [{key: (r(value, 6) if isinstance(value, float) else value) for key, value in u.items()} for u in scalars["unbalance"]],
            "unbalance_peak_um": r(scalars["unbalance_peak_mm"] * 1000.0, 4),
            "unbalance_peak_rpm": r(scalars["unbalance_peak_rpm"], 3),
            "unbalance_at_top_um": r(scalars["unbalance_at_top_mm"] * 1000.0, 4),
            "max_von_mises_MPa": r(peak),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[node]],
            "yield_MPa": yield_MPa,
            "safety_factor": factor,
            "deformation_scale": scalars["deformation_scale"],
        }
        if scalars.get("default_unbalance"):
            summary["default_unbalance"] = {key: (r(value, 6) if isinstance(value, float) else value)
                                            for key, value in scalars["default_unbalance"].items()}
        if scalars.get("solid_modes"):
            summary["solid_modes"] = [{"mode": m["mode"], "at_rest_Hz": r(m["at_rest_Hz"]), "spinning_Hz": r(m["spinning_Hz"])}
                                      for m in scalars["solid_modes"]]
        if scalars.get("parts"):
            summary["parts"] = scalars["parts"]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} spinning"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        # Every whirl shape is scaled to a largest motion of 1 mm, so one range holds across the frames.
        return {"von_mises": (0.0, summary["max_von_mises_MPa"]), "whirl": (0.0, 1.0)}

    def extras_head(self, summary: dict) -> dict:
        return {"first_critical_rpm": summary["first_critical_rpm"], "safety_factor": summary["safety_factor"]}

    def extras_assembly(self, summary: dict) -> dict:
        return {"parts": summary.get("parts", [])}

    def study_echo(self, inputs: RotordynamicsInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        def coefficient(value):
            return [list(row) for row in value] if isinstance(value, tuple) else value

        bearings = []
        for b in inputs.bearings:
            entry: dict[str, Any] = {"faces": bare(b.faces)} if b.faces else {"at_mm": b.at_mm}
            if b.rigid:
                entry["rigid"] = True
            if b.clamped:
                entry["clamped"] = True
            entry.update({name: coefficient(value) for name, value in b.coefficients})
            bearings.append(entry)
        echo: dict[str, Any] = {
            "spin": {"axis": inputs.axis_name or list(inputs.axis), "rpm": list(inputs.rpm), "sweep_rpm": inputs.sweep_top_rpm},
            "bearings": bearings,
            "disc_model": inputs.disc_model,
            "modes_requested": inputs.modes,
        }
        if inputs.discs:
            echo["discs"] = [{"at_mm": d.at_mm, "mass_kg": d.mass_kg, "polar_kg_mm2": d.polar_kg_mm2,
                              "diametral_kg_mm2": d.diametral_kg_mm2} for d in inputs.discs]
        if inputs.unbalance:
            echo["unbalance"] = [{**({"faces": bare(u.faces)} if u.faces else {"at_mm": u.at_mm}), "g_mm": u.g_mm,
                                  "phase_deg": u.phase_deg} for u in inputs.unbalance]
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        spin = summary.get("spin", {})
        low, high = spin.get("operating_rpm", [0, 0])
        axis = spin.get("axis")
        lines = [f"spins {rpm_text(low) if low else '0'} to {rpm_text(high)} about {axis if isinstance(axis, str) else axis}"]
        forward = [c for c in summary.get("critical_speeds", []) if c["whirl"] == "forward" and c["order"] == 1]
        if forward:
            lines.append("critical speeds " + ", ".join(rpm_text(c["rpm"]) for c in forward))
        else:
            lines.append(f"no forward critical speed up to {rpm_text(spin.get('sweep_rpm') or high)}")
        lowest = summary.get("lowest_log_decrement")
        if lowest:
            lines.append(f"lowest log decrement {lowest['value']:.3g} ({whirl_words(lowest)} at "
                         f"{rpm_text(lowest['rpm'])})")
        if summary.get("unbalance_peak_um"):
            lines.append(f"unbalance orbit peaks at {orbit_text(summary['unbalance_peak_um'] / 1000.0)} at "
                         f"{rpm_text(summary['unbalance_peak_rpm'])}")
        if summary.get("max_von_mises_MPa") is not None:
            factor = summary.get("safety_factor")
            lines.append(f"spinning stress {summary['max_von_mises_MPa']:.4g} MPa at {rpm_text(high)}"
                         + (f", safety factor {factor:g}" if factor is not None else ""))
        return lines


def _hz(f: float) -> str:
    from cadgen._internal.fea.analyses.modal import hz_text

    return hz_text(f)

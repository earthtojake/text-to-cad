"""Drop (estimate): what a drop does to a part, as an equivalent steady load. Tier 2.

A part dropped from ``height_mm`` that stops over ``stop_mm`` decelerates at
G = h / d (constant deceleration from v² = 2 g h). One that stops in
``impact_ms`` along a half-sine pulse peaks at a = π v / (2 τ), v = √(2 g h).
The faces that hit (``onto``) are held fixed; the part travels along their mean
outward normal (or ``direction``), and the rest of it is loaded by its own
inertia, G g toward those faces. That is exactly a static study with an
``acceleration`` body load of G g pointing away from the floor, and the solve
is that study's (:class:`StaticAnalysis`), so every number a static result
carries a drop result carries too.

It is an estimate, never an impact simulation: no stress wave, no rebound, no
floor beyond the faces held. Every output says so: the summary, the CLI lines,
``extras.analysis.estimate`` and a finding. The impact analysis simulates the
impact. Stdlib only at import.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, SolveContext
from cadgen._internal.fea.analyses.static import G0_MM_S2, StaticAnalysis, StaticInputs
from cadgen._internal.fea.study import Fixture, Load

__all__ = ["DropAnalysis", "DropInputs", "drop_g", "estimate_line"]

DROP_KEYS = frozenset({"height_mm", "onto", "stop_mm", "impact_ms", "direction", "dynamic"})
#: A direction component this close to zero is zero, so a face along an axis drops exactly along it.
_SNAP = 1e-9
NOT_IMPACT = "not an impact simulation (analysis impact simulates the impact)"


@dataclass(frozen=True)
class DropInputs(StaticInputs):
    height_mm: float = 0.0
    onto: tuple[str, ...] = ()
    stop_mm: float | None = None
    impact_ms: float | None = None
    #: The travel direction the study gave (unit), else ``None``: the solve takes the landing faces' mean outward normal.
    direction: tuple[float, float, float] | None = None
    #: The equivalent deceleration, in g.
    G: float = 0.0
    #: What the solve resolved (the travel direction), for the echo and the summary: written once, by ``solve``.
    resolved: dict = field(default_factory=dict, compare=False, hash=False)


def drop_g(height_mm: float, *, stop_mm: float | None = None, impact_ms: float | None = None) -> float:
    """The equivalent deceleration in g: h / d for a constant stop, π v / (2 τ) / g for a half-sine one."""
    if stop_mm is not None:
        return height_mm / stop_mm
    speed = math.sqrt(2.0 * G0_MM_S2 * height_mm)  # mm/s
    return math.pi * speed / (2.0 * impact_ms / 1000.0) / G0_MM_S2


def _figure(value: float) -> str:
    """Three significant figures, whole numbers from 100 up: 500, 694, 2.5."""
    return f"{value:.3g}" if abs(value) < 100 else f"{value:.0f}"


def _factor(value: float | None) -> str:
    from cadgen._internal.fea.checks import safety_factor_text

    return "n/a" if value is None else safety_factor_text(value)


def height_words(height_mm: float) -> str:
    return f"{_figure(height_mm / 1000)} m" if height_mm >= 1000 else f"{_figure(height_mm)} mm"


def stop_words(stop_mm: float | None, impact_ms: float | None) -> str:
    return f"stopping in {_figure(stop_mm)} mm" if stop_mm is not None else f"stopping in {_figure(impact_ms)} ms (half-sine)"


def estimate_line(height_mm: float, G: float, *, stop_mm: float | None = None, impact_ms: float | None = None) -> str:
    """The sentence every drop result carries: what was assumed, the load it became, and what it is not."""
    peak = "peak " if stop_mm is None else ""
    return (f"Estimate: {height_words(height_mm)} drop {stop_words(stop_mm, impact_ms)}, {_figure(G)} g {peak}equivalent "
            f"static load; {NOT_IMPACT}")


def _drop(document: dict) -> dict:
    raw = document.get("drop")
    where = "drop"
    if not isinstance(raw, dict):
        raise ValueError('study.drop: expected an object like {"height_mm": 1000, "onto": ["#o1.f5"], "stop_mm": 2}')
    unknown = set(raw) - DROP_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a drop takes {sorted(DROP_KEYS)}")
    if raw.get("dynamic", False) is not False:
        if raw["dynamic"] is True:
            raise ValueError(
                f"{where}.dynamic: the dynamic check (a transient run with the half-sine pulse) is coming, not in this cadgen "
                "yet; leave dynamic out for the estimate"
            )
        raise ValueError(f"{where}.dynamic: true or false, got {kinds.json_text(raw['dynamic'])}")
    if "height_mm" not in raw:
        raise ValueError(f"{where}.height_mm: how far it falls, in mm (1000 for 1 m)")
    height = kinds.number(raw["height_mm"], where=f"{where}.height_mm", positive=True)
    if "onto" not in raw:
        raise ValueError(f'{where}.onto: the faces that hit the floor, like ["#o1.f5"]; they are held while the rest is loaded')
    onto = kinds.faces({"faces": raw["onto"]}, where=f"{where}.onto")
    given = [key for key in ("stop_mm", "impact_ms") if key in raw]
    if len(given) != 1:
        raise ValueError(
            f"{where}: give how it stops, exactly one of stop_mm (the distance it takes to stop, constant deceleration) "
            "or impact_ms (how long the impact lasts, a half-sine pulse)"
        )
    stop = kinds.number(raw["stop_mm"], where=f"{where}.stop_mm", positive=True) if "stop_mm" in raw else None
    impact = kinds.number(raw["impact_ms"], where=f"{where}.impact_ms", positive=True) if "impact_ms" in raw else None
    direction = None
    if "direction" in raw:
        vector = raw["direction"]
        if not isinstance(vector, list) or len(vector) != 3:
            raise ValueError(f"{where}.direction: the way it falls as [x, y, z], like [0, 0, -1] for straight down")
        components = [kinds.number(c, where=f"{where}.direction") for c in vector]
        size = math.sqrt(sum(c * c for c in components))
        if not size > 0:
            raise ValueError(f"{where}.direction: the direction is zero")
        direction = tuple(c / size for c in components)
    return {"height_mm": height, "onto": onto, "stop_mm": stop, "impact_ms": impact, "direction": direction}


def _outward_normal(volume, ordinals: list[int]) -> tuple[float, float, float]:
    """The area-weighted mean outward normal of the boundary triangles on faces ``ordinals``, not normalised.

    Each triangle is turned outward by the tetrahedron it bounds: its fourth corner is inside.
    """
    import numpy as np

    rows = np.isin(volume.boundary_ordinal, ordinals)
    triangles = volume.boundary[rows][:, :3].astype(np.int64)
    corners = volume.tets[:, :4].astype(np.int64)
    count = int(volume.nodes.shape[0])
    sides = ((1, 2, 3, 0), (0, 2, 3, 1), (0, 1, 3, 2), (0, 1, 2, 3))

    def key(triples):
        ordered = np.sort(triples, axis=1)
        return (ordered[:, 0] * count + ordered[:, 1]) * count + ordered[:, 2]

    tet_keys = np.concatenate([key(corners[:, list(side[:3])]) for side in sides])
    opposite = np.concatenate([corners[:, side[3]] for side in sides])
    order = np.argsort(tet_keys, kind="stable")
    wanted = key(triangles)
    found = order[np.searchsorted(tet_keys[order], wanted)]
    inside = volume.nodes[opposite[found]]
    a, b, c = (volume.nodes[triangles[:, i]] for i in range(3))
    normals = 0.5 * np.cross(b - a, c - a)  # area-weighted
    flip = np.einsum("ij,ij->i", normals, inside - a) > 0
    normals[flip] *= -1.0
    total = normals.sum(axis=0)
    return tuple(float(c) for c in total)


def _unit(vector) -> tuple[float, float, float]:
    size = math.sqrt(sum(c * c for c in vector))
    unit = [c / size for c in vector]
    # A face along an axis falls exactly along it, so a drop and its static twin are the same study.
    unit = [0.0 if abs(c) < _SNAP else c for c in unit]
    size = math.sqrt(sum(c * c for c in unit))
    return tuple(c / size for c in unit)  # type: ignore[return-value]


class DropAnalysis(StaticAnalysis):
    name: ClassVar[str] = "drop"
    tier: ClassVar[int] = 2
    word: ClassVar[str] = "Drop (estimate)"
    estimate_only: ClassVar[bool] = True
    limits: ClassVar[tuple[str, ...]] = (
        "An estimate: the drop becomes one equivalent steady load (G g on the whole part, the landing faces held), "
        f"{NOT_IMPACT}.",
        "No stress wave, rebound, floor stiffness or damage: the stopping distance or time you assume sets the answer.",
    )
    study_keys: ClassVar[frozenset[str]] = frozenset({"drop"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"density"})
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "stress", "label": "Drop"},)
    noun: ClassVar[str] = "this drop"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> DropInputs:
        drop = _drop(document)
        G = drop_g(drop["height_mm"], stop_mm=drop["stop_mm"], impact_ms=drop["impact_ms"])
        onto = drop["onto"]
        loads: tuple[Load, ...] = ()
        if drop["direction"] is not None:
            loads = (Load((), "acceleration", vector_g=tuple(-G * c + 0.0 for c in drop["direction"])),)
        return DropInputs(
            onto, onto, True, fixtures=(Fixture(onto),), loads=loads, material_needs=frozenset({"density"}),
            G=G, **drop,
        )

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: DropInputs) -> AnalysisResult:
        """The static solve of the equivalent load: the landing faces held, G g on the whole part toward them."""
        if inputs.direction is not None:
            travel = inputs.direction
        else:
            normal = _outward_normal(ctx.volume, sorted({ctx.ordinal_of[ref] for ref in inputs.onto}))
            if math.sqrt(sum(c * c for c in normal)) < 1e-6 * sum(fp.area for fp in ctx.volume.faces.values()):
                raise ValueError(
                    "drop.onto: the landing faces face opposite ways, so there is no one way it falls; "
                    "give drop.direction, like [0, 0, -1] for straight down"
                )
            travel = _unit(normal)
        inputs.resolved["direction"] = travel
        vector_g = tuple(-inputs.G * c + 0.0 for c in travel)  # + 0.0: no "-0.0" in the echo
        inputs.resolved["vector_g"] = vector_g
        solved = dataclasses.replace(inputs, loads=(Load((), "acceleration", vector_g=vector_g),))
        result = super().solve(ctx, solved)
        result.scalars["drop"] = {"direction": travel, "vector_g": vector_g}
        return result

    # -- judging and findings ------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: DropInputs) -> dict:
        if check["kind"] == "stress" and not check.get("label"):
            check = {**check, "label": "Drop"}
        return super().judge(check, index, ctx, result, inputs)

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: DropInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        found = super().findings(ctx, result, inputs, check_results, assembly=assembly)
        assumed = (f"the {_figure(inputs.stop_mm)} mm stopping distance" if inputs.stop_mm is not None
                   else f"the {_figure(inputs.impact_ms)} ms impact")
        found.append({
            "check": "fea",
            "severity": "info",
            "type": "drop_estimate",
            "summary": (f"This is an estimate of a {height_words(inputs.height_mm)} drop as a steady {_figure(inputs.G)} g load, "
                        f"not an impact simulation: {assumed} sets the answer, so say what you assumed"),
            "description": estimate_line(inputs.height_mm, inputs.G, stop_mm=inputs.stop_mm, impact_ms=inputs.impact_ms),
            "items": [],
        })
        return sorted(found, key=lambda finding: finding["severity"] != "error")

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: DropInputs, check_results: list[dict]) -> dict:
        summary = super().summary(result, inputs, check_results)
        checks = summary.pop("checks")
        resolved = result.scalars["drop"]
        summary["estimate"] = True
        summary["estimate_line"] = estimate_line(inputs.height_mm, inputs.G, stop_mm=inputs.stop_mm, impact_ms=inputs.impact_ms)
        summary["drop"] = {
            "height_mm": inputs.height_mm,
            **({"stop_mm": inputs.stop_mm} if inputs.stop_mm is not None else {"impact_ms": inputs.impact_ms}),
            "impact_speed_m_s": round(math.sqrt(2.0 * G0_MM_S2 * inputs.height_mm) / 1000.0, 4),
            "G": round(inputs.G, 4),
            "direction": [round(c, 6) for c in resolved["direction"]],
            "acceleration_g": [round(c, 4) for c in resolved["vector_g"]],
        }
        summary["checks"] = checks
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} drop (estimate)"

    def study_echo(self, inputs: DropInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        vector_g = inputs.resolved.get("vector_g")
        echoed = dataclasses.replace(
            inputs, loads=() if vector_g is None else (Load((), "acceleration", vector_g=vector_g),)
        )
        echo = super().study_echo(echoed, bare)
        direction = inputs.resolved.get("direction", inputs.direction)
        echo["drop"] = {
            "height_mm": inputs.height_mm,
            "onto": bare(inputs.onto),
            **({"stop_mm": inputs.stop_mm} if inputs.stop_mm is not None else {"impact_ms": inputs.impact_ms}),
            **({} if direction is None else {"direction": [float(c) for c in direction]}),
            "G": round(inputs.G, 4),
        }
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        drop = summary["drop"]
        lines = [
            summary["estimate_line"],
            f"impact speed {drop['impact_speed_m_s']} m/s, equivalent load {drop['G']} g along {drop['acceleration_g']} "
            f"(falling along {drop['direction']})",
            f"max von Mises {summary.get('max_von_mises_MPa')} MPa (Gauss {summary.get('max_von_mises_gauss_MPa')} MPa), "
            f"yield {summary.get('yield_MPa')} MPa, safety factor {_factor(summary.get('safety_factor'))} (estimate)",
            f"max displacement {summary.get('max_displacement_mm')} mm at {summary.get('max_displacement_at_mm')}",
            f"applied {summary.get('applied_force_N')} N, reactions {summary.get('reaction_force_N')} N",
        ]
        return lines

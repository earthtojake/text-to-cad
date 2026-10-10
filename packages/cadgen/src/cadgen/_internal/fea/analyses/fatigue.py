"""Fatigue life: how many cycles of a load the part survives, and its fatigue safety factor. Tier 1, a post-process.

The load comes from another analysis solved first on the same mesh. Today that
is ``static``: one load case, repeated (``fatigue.from: "static"``), cycling
fully reversed (R = -1), from zero (R = 0) or at a stress ratio R. The
``harmonic`` and ``random_vibration`` sources are coming.

The method, per node, on the source's von Mises stress σ (Shigley, chapter 6):

- amplitude σa = σ (1 - R) / 2 and mean σm = σ (1 + R) / 2;
- the endurance strength Se = ka · kf · Se', with Se' the material's fatigue
  strength at N_e cycles, ka the Marin surface factor a · Sut^b (Shigley table
  6-2, from ``surface``) and kf an optional ``factor`` for the other Marin
  factors;
- the Basquin S-N line S = A · N^b through (1e3, 0.9 Sut) and (N_e, Se); past
  N_e the strength stays Se (aluminium has no endurance limit: its strength at
  5e8 cycles is where the data ends);
- the modified Goodman line σa / Sf(N) + σm / Sut = 1 / n for the fatigue
  safety factor n at the cycles needed, and the life N where n = 1 (the
  equivalent fully reversed stress σar = σa / (1 - σm / Sut) on the S-N line).

Fields: ``life`` (log10 cycles, at most N_e: past it the data says nothing
more) and ``fatigue_factor`` (n at the study's cycles, at most
:data:`FACTOR_CAP`). The ``fatigue`` check judges n at its cycles against its
margin. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, SolveContext
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs
from cadgen._internal.fea.materials import NONE_REASONS, Material, material_from_spec

__all__ = [
    "FACTOR_CAP", "FatigueAnalysis", "FatigueInputs", "LOW_CYCLES", "SNCurve", "SURFACE_FACTORS", "goodman_factor",
    "marin_surface", "sn_curve", "stress_ratio",
]

#: Marin surface factor ka = a · Sut^b, Sut in MPa (Shigley's Mechanical Engineering Design, table 6-2).
SURFACE_FACTORS: dict[str, tuple[float, float]] = {
    "ground": (1.58, -0.085),
    "machined": (4.51, -0.265),
    "cold_drawn": (4.51, -0.265),
    "hot_rolled": (57.7, -0.718),
    "as_forged": (272.0, -0.995),
}
#: A polished surface is the test specimen's own: no reduction.
SURFACES = ("polished", *SURFACE_FACTORS)
#: The start of the S-N line: 0.9 Sut at a thousand cycles. Below it is low-cycle fatigue.
LOW_CYCLES = 1e3
LOW_CYCLE_FRACTION = 0.9
#: The fatigue factor where no stress reaches a node, and the most a field or a check says.
FACTOR_CAP = 100.0
LOADINGS = ("fully_reversed", "zero_based")
SOURCES = ("static", "harmonic", "random_vibration")
FATIGUE_KEYS = frozenset({"from", "loading", "cycles", "surface", "factor", "dwell_s", "duration_s"})
DEFAULT_CYCLES = 1e6
#: Materials whose fatigue data is quoted this far out have no endurance limit (aluminium, copper alloys):
#: a life asked for past their data is judged at its last strength, which may overstate it.
NO_ENDURANCE_LIMIT_FROM = 1e8


def marin_surface(surface: str, uts: float) -> float:
    """The Marin surface factor ka for ``surface`` and an ultimate strength in MPa, at most 1."""
    if surface == "polished":
        return 1.0
    a, b = SURFACE_FACTORS[surface]
    return min(1.0, a * uts ** b)


def stress_ratio(loading: str | float) -> float:
    """R = σmin / σmax: fully reversed -1, from zero 0, else the number given."""
    return {"fully_reversed": -1.0, "zero_based": 0.0}.get(loading, loading)  # type: ignore[arg-type]


@dataclass(frozen=True)
class SNCurve:
    """One material's S-N line: Basquin S = A · N^b from (1e3, 0.9 Sut) to (N_e, Se), flat at Se past N_e."""

    uts: float
    #: The corrected endurance strength Se = ka · kf · Se', MPa.
    endurance: float
    endurance_cycles: float
    #: Se' as the material gives it, and the factors that corrected it.
    raw_endurance: float
    surface_factor: float
    factor: float
    A: float
    b: float

    def strength(self, cycles):
        """The fully reversed strength Sf at ``cycles`` (a number or an array): the line, Se past N_e, at most Sut."""
        import numpy as np

        n = np.minimum(np.asarray(cycles, dtype=float), self.endurance_cycles)
        return np.minimum(self.A * n ** self.b, self.uts)

    def life(self, sigma_ar):
        """Cycles to failure at a fully reversed stress (a number or an array), at most N_e (``runout``) and at least 1."""
        import numpy as np

        sigma = np.asarray(sigma_ar, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            cycles = np.where(sigma > 0, (np.maximum(sigma, 1e-300) / self.A) ** (1.0 / self.b), np.inf)
        cycles = np.where(sigma <= self.endurance, self.endurance_cycles, cycles)
        return np.clip(cycles, 1.0, self.endurance_cycles)

    def as_dict(self) -> dict:
        return {
            "uts_MPa": self.uts,
            "endurance_MPa": self.raw_endurance,
            "endurance_cycles": self.endurance_cycles,
            "surface_factor": round(self.surface_factor, 4),
            "factor": self.factor,
            "corrected_endurance_MPa": round(self.endurance, 4),
            "basquin_A_MPa": round(self.A, 4),
            "basquin_b": round(self.b, 6),
        }


def sn_curve(material: Material, *, surface: str = "machined", factor: float = 1.0) -> SNCurve:
    """The material's S-N line, its endurance strength corrected by the Marin surface factor and ``factor``."""
    uts, raw, cycles = material.uts, material.endurance, material.endurance_cycles
    ka = marin_surface(surface, uts)
    endurance = ka * factor * raw
    top = LOW_CYCLE_FRACTION * uts
    if not cycles > LOW_CYCLES:
        raise ValueError(f"material: the fatigue strength of {material.name} must be quoted past {LOW_CYCLES:.0e} cycles, "
                         f"got {cycles:g}")
    if not endurance < top:
        raise ValueError(f"material: the fatigue strength of {material.name} ({endurance:g} MPa after its factors) must be "
                         f"below 0.9 × its ultimate strength ({top:g} MPa)")
    b = math.log10(endurance / top) / math.log10(cycles / LOW_CYCLES)
    A = top / LOW_CYCLES ** b
    return SNCurve(uts, endurance, cycles, raw, ka, factor, A, b)


def goodman_factor(amplitude, mean, strength, uts):
    """The modified Goodman safety factor n: σa / Sf + σm / Sut = 1 / n (numbers or arrays); at most FACTOR_CAP."""
    import numpy as np

    use = np.asarray(amplitude, dtype=float) / strength + np.asarray(mean, dtype=float) / uts
    with np.errstate(divide="ignore"):
        return np.minimum(np.where(use > 0, 1.0 / np.maximum(use, 1e-300), FACTOR_CAP), FACTOR_CAP)


@dataclass(frozen=True)
class FatigueInputs(StaticInputs):
    source: str = "static"
    #: "fully_reversed", "zero_based" or "ratio" (with ``ratio``).
    loading: str = "fully_reversed"
    ratio: float = -1.0
    cycles: float = DEFAULT_CYCLES
    surface: str = "machined"
    factor: float = 1.0

    @property
    def amplitude_share(self) -> float:
        return (1.0 - self.ratio) / 2.0

    @property
    def mean_share(self) -> float:
        return (1.0 + self.ratio) / 2.0


def _fatigue_block(document: dict) -> dict:
    raw = document.get("fatigue")
    where = "fatigue"
    if not isinstance(raw, dict):
        raise ValueError('study.fatigue: expected an object like {"from": "static", "loading": "fully_reversed", "cycles": 1e6}')
    unknown = set(raw) - FATIGUE_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; fatigue takes {sorted(FATIGUE_KEYS)}")
    source = raw.get("from", "static")
    if source not in SOURCES:
        raise ValueError(f"{where}.from: {kinds.json_text(source)} is not one of {list(SOURCES)}")
    if source != "static":
        raise ValueError(
            f"{where}.from: fatigue from a {source.replace('_', ' ')} run is coming, not in this cadgen yet; "
            'use "static" (one load case, repeated)'
        )
    for key in ("dwell_s", "duration_s"):
        if key in raw:
            owner = "harmonic" if key == "dwell_s" else "random_vibration"
            raise ValueError(f"{where}.{key}: goes with from {owner}, which is coming; a static source repeats its load case")
    loading = raw.get("loading", "fully_reversed")
    if isinstance(loading, dict):
        if set(loading) != {"ratio"}:
            raise ValueError(f'{where}.loading: a stress ratio as {{"ratio": R}}, like {{"ratio": 0.1}}')
        ratio = kinds.number(loading["ratio"], where=f"{where}.loading.ratio")
        if not -1.0 <= ratio < 1.0:
            raise ValueError(f"{where}.loading.ratio: R = lowest / highest stress, from -1 (fully reversed) up to but "
                             f"not 1 (a steady load does not fatigue), got {ratio:g}")
        loading_name = "ratio"
    elif loading in LOADINGS:
        loading_name, ratio = loading, stress_ratio(loading)
    else:
        raise ValueError(f'{where}.loading: {kinds.json_text(loading)} is not one of {list(LOADINGS)} or {{"ratio": R}}')
    cycles = kinds.number(raw["cycles"], where=f"{where}.cycles", positive=True) if "cycles" in raw else DEFAULT_CYCLES
    if cycles < 1:
        raise ValueError(f"{where}.cycles: at least one cycle, got {cycles:g}")
    surface = raw.get("surface", "machined")
    if surface not in SURFACES:
        raise ValueError(f"{where}.surface: {kinds.json_text(surface)} is not one of {list(SURFACES)}")
    factor = kinds.number(raw["factor"], where=f"{where}.factor", positive=True) if "factor" in raw else 1.0
    if factor > 1:
        raise ValueError(f"{where}.factor: the other Marin factors (size, load, temperature, reliability) multiplied, "
                         f"from 0 to 1, got {factor:g}")
    return {"source": source, "loading": loading_name, "ratio": ratio, "cycles": cycles, "surface": surface, "factor": factor}


def _require_fatigue_data(spec: Any, where: str) -> None:
    """A plain error for a material with no fatigue data (a polymer), naming the keys that give it."""
    material = material_from_spec(spec)
    if material.uts is None:
        raise ValueError(f'{where}: fatigue studies need the ultimate tensile strength, and {material.name} has none; '
                         f'add uts_MPa to the material object, like {{"name": "{material.name}", "uts_MPa": 400}}')
    if material.endurance is None or material.endurance_cycles is None:
        key = next((k for k, value in _TABLE_KEYS.items() if value == material.name), None)
        reason = NONE_REASONS.get((key, "endurance")) if key else None
        why = f" ({reason})" if reason else ""
        raise ValueError(
            f"{where}: {material.name} has no fatigue data{why}; add fatigue_strength_MPa and fatigue_cycles to the "
            f'material object, like {{"name": "{material.name}", "fatigue_strength_MPa": 12, "fatigue_cycles": 1e6}}'
        )


def _table_keys() -> dict[str, str]:
    from cadgen._internal.fea.materials import MATERIALS

    return {key: material.name for key, material in MATERIALS.items()}


_TABLE_KEYS = _table_keys()


def _cycles_words(cycles: float) -> str:
    """5e5 as "500,000"; 2.1e6 as "2.1 million"; 1e9 as "1 billion"; past a thousand billion in scientific notation."""
    if cycles >= 1e12:
        return f"{cycles:.2g}"
    if cycles >= 1e9:
        return f"{cycles / 1e9:.3g} billion"
    if cycles >= 1e6:
        return f"{cycles / 1e6:.3g} million"
    return f"{round(cycles):,}"


def _floored(value: float) -> float:
    return math.floor(value * 1000) / 1000


class FatigueAnalysis(StaticAnalysis):
    name: ClassVar[str] = "fatigue"
    tier: ClassVar[int] = 1
    word: ClassVar[str] = "Fatigue life"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = ()
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "fatigue"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"uts", "endurance", "endurance_cycles"})
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("life", "_LIFE", "fatigue life", "log10 cycles"),
        FieldSpec("fatigue_factor", "_FATIGUE_FACTOR", "fatigue safety factor", ""),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = (kinds.FATIGUE,)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "fatigue", "margin": 1.5},)
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["life", "fatigue_factor", "displacement"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ("static",)
    # Its source's ladder: the static solve is the one that is fitted.
    ladder: ClassVar[tuple[str, ...]] = StaticAnalysis.ladder
    noun: ClassVar[str] = "this load"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> FatigueInputs:
        block = _fatigue_block(document)
        if "material" in document:
            _require_fatigue_data(document["material"], "material")
        for name, entry in (document.get("parts") or {}).items() if isinstance(document.get("parts"), dict) else ():
            if isinstance(entry, dict) and "material" in entry:
                _require_fatigue_data(entry["material"], f"parts[{name!r}].material")
        static = StaticAnalysis.parse(self, document)
        return FatigueInputs(
            static.face_refs, static.anchor_refs, True, fixtures=static.fixtures, loads=static.loads,
            material_needs=static.material_needs, **block,
        )

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: FatigueInputs) -> AnalysisResult:
        """Life and fatigue factor at every node from the static source's von Mises stress, per part's material."""
        import numpy as np

        source = ctx.upstream.get("static")
        if source is None:  # called on its own: solve the source here, on the same space
            source = StaticAnalysis.solve(self, ctx, StaticInputs(
                inputs.face_refs, inputs.anchor_refs, True, fixtures=inputs.fixtures, loads=inputs.loads,
                material_needs=inputs.material_needs,
            ))
        stress = source.fields["von_mises"]
        nodes = len(stress)
        per_part = source.fields_by_part.get("von_mises")
        curves = [sn_curve(material, surface=inputs.surface, factor=inputs.factor) for material in ctx.materials]
        if per_part is None or ctx.volume.domain is None:
            groups = [(np.arange(nodes), stress, 0)]
        else:
            groups = []
            for index in range(len(ctx.materials)):
                own = np.unique(source.element_dofs[ctx.volume.domain == index])
                groups.append((own, per_part[index], index))
        factor, life, governing = _nodal(groups, curves, inputs, inputs.cycles, nodes)
        result = AnalysisResult(
            dof_locations=source.dof_locations,
            vertices=source.vertices,
            tets=source.tets,
            boundary_quadratic=source.boundary_quadratic,
            element_dofs=source.element_dofs,
            fields={"life": np.log10(life), "fatigue_factor": factor, "displacement": source.fields["displacement"],
                    "von_mises": stress},
            deformation=source.deformation,
            scalars={**source.scalars, "curves": curves, "groups": groups, "life_cycles": life, "governing": governing},
            reactions=list(source.reactions),
            applied=tuple(source.applied),
            dofs=source.dofs,
            solver=source.solver,
            timings=dict(source.timings),
            warnings=list(source.warnings),
            solved=source.solved,
        )
        return result

    def _at(self, result: AnalysisResult, inputs: FatigueInputs, cycles: float):
        """The fatigue factor at ``cycles`` at every node, each part's stress against its own material."""
        curves = result.scalars["curves"]
        return _nodal(result.scalars["groups"], curves, inputs, cycles, len(result.fields["von_mises"]))[0]

    # -- the automatic finer solve: when the answer is close to failing, as static's ------------------

    def needs_finer(self, result: AnalysisResult, inputs: FatigueInputs, check_results: list[dict]) -> bool:
        from cadgen._internal.fea import checks

        return float(result.fields["fatigue_factor"].min()) < checks.RESOLVE_BELOW

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: FatigueInputs) -> dict:
        """The fatigue factor n at the check's cycles (else the study's) at the worst node, against its margin.

        ``ratio`` is 1 / n and ``close_at`` 1 / margin, so it fails under n = 1 and is close under the margin.
        ``life`` is the worst node's life in cycles where it is within the material's data (left out past it).
        """
        import numpy as np

        cycles = float(check.get("cycles", inputs.cycles))
        margin = float(check.get("margin", 1.5))
        factor = self._at(result, inputs, cycles)
        peak = kinds.field_max_over(
            1.0 / factor, (), boundary=result.boundary_quadratic, boundary_ordinal=ctx.volume.boundary_ordinal,
            locations=result.dof_locations, face_ref=ctx.volume.faces, ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
        )
        n = float(factor[peak.node])
        life = result.scalars["life_cycles"]
        worst = int(np.argmin(life))
        runout = life[worst] >= max(curve.endurance_cycles for curve in result.scalars["curves"])
        status = "fails" if n < 1 else "close" if n < margin else "passes"
        return {
            "kind": "fatigue",
            "label": check.get("label") or "Fatigue life",
            "value": _floored(n),
            "limit": margin,
            "unit": "",
            "ratio": round(1.0 / n, 6),
            "close_at": round(1.0 / margin, 6),
            "margin": margin,
            "status": status,
            "where": {"ref": peak.ref, "at": [round(c, 3) for c in peak.at]},
            "need": cycles,
            **({} if runout else {"life": float(f"{life[worst]:.4g}")}),
        }

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: FatigueInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        """The source's strength findings (it yields, the mesh, a peak at a clamp), then fatigue's own, in plain words."""
        found = [finding for finding in super().findings(ctx, result, inputs, check_results, assembly=assembly)
                 if finding["type"] != "low_margin"]
        curves = result.scalars["curves"]
        for index, check in enumerate(ctx.study.checks if ctx.study is not None else self.default_checks):
            judged = self.judge(check, index, ctx, result, inputs)
            item = [{"text": "the shortest fatigue life", **judged["where"]}]
            needs = _cycles_words(judged["need"])
            lasts = f"about {_cycles_words(judged['life'])} cycles" if "life" in judged else None
            if judged["status"] == "fails":
                found.append(_finding(
                    "error", "wears_out",
                    f"It wears out {'in ' + lasts if lasts else 'too soon'}, short of the {needs} cycles it needs "
                    f"(fatigue safety factor {judged['value']:.2f})",
                    f"modified Goodman factor {judged['value']:.3f} at {judged['need']:.3g} cycles, {inputs.loading.replace('_', ' ')} loading",
                    item))
            elif judged["status"] == "close":
                found.append(_finding(
                    "warning", "low_fatigue_margin",
                    f"It lasts the {needs} cycles it needs, but only with a fatigue safety factor of {judged['value']:.2f}, "
                    f"under the {judged['margin']:g} margin",
                    f"modified Goodman factor {judged['value']:.3f} at {judged['need']:.3g} cycles", item))
            beyond = [curve for curve in curves if judged["need"] > curve.endurance_cycles]
            if beyond:
                curve = beyond[0]
                no_limit = curve.endurance_cycles >= NO_ENDURANCE_LIMIT_FROM
                found.append(_finding(
                    "warning" if no_limit else "info", "past_fatigue_data",
                    f"The {needs} cycles asked for are past the material's fatigue data ({_cycles_words(curve.endurance_cycles)} "
                    "cycles); it is judged at the strength there"
                    + (", which may overstate it: this material has no endurance limit and keeps weakening"
                       if no_limit else ", its endurance limit"),
                    f"fatigue strength {curve.endurance:.4g} MPa at {curve.endurance_cycles:.3g} cycles", []))
        if float(result.scalars["life_cycles"].min()) < LOW_CYCLES:
            found.append(_finding(
                "warning", "low_cycle_fatigue",
                "It fails in under 1,000 cycles: that is low-cycle fatigue, which this stress-life estimate extrapolates "
                "and does not model; treat the life as a rough figure and reduce the stress",
                f"shortest life {float(result.scalars['life_cycles'].min()):.3g} cycles", []))
        return sorted(found, key=lambda finding: finding["severity"] != "error")

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: FatigueInputs, check_results: list[dict]) -> dict:
        import numpy as np

        base = super().summary(result, inputs, check_results)
        checks = base.pop("checks")
        stress = result.fields["von_mises"]
        peak = int(stress.argmax())
        factor = result.fields["fatigue_factor"]
        life = result.scalars["life_cycles"]
        curves = result.scalars["curves"]
        worst = int(np.argmin(factor))
        curve = curves[int(result.scalars["governing"][worst])]
        runout = float(life.min()) >= max(c.endurance_cycles for c in curves)
        summary = {
            "source": inputs.source,
            "loading": inputs.loading,
            "stress_ratio": inputs.ratio,
            "cycles": inputs.cycles,
            "surface": inputs.surface,
            "max_von_mises_MPa": base["max_von_mises_MPa"],
            "max_von_mises_at_mm": base["max_von_mises_at_mm"],
            "stress_amplitude_MPa": round(inputs.amplitude_share * float(stress[peak]), 4),
            "mean_stress_MPa": round(inputs.mean_share * float(stress[peak]), 4),
            "min_fatigue_factor": _floored(float(factor[worst])),
            "min_fatigue_factor_at_mm": [round(float(c), 3) for c in result.dof_locations[worst]],
            "min_life_cycles": None if runout else float(f"{float(life.min()):.4g}"),
            "life_beyond_cycles": curve.endurance_cycles if runout else None,
            "sn": curve.as_dict(),
            **{key: base[key] for key in ("yield_MPa", "safety_factor", "max_displacement_mm", "max_displacement_at_mm",
                                          "applied_force_N", "reaction_force_N", "deformation_scale")},
        }
        for key in ("weakest_part", "parts"):
            if key in base:
                summary[key] = base[key]
        summary["checks"] = checks
        return summary

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        life = result.fields["life"]
        factor = result.fields["fatigue_factor"]
        return {
            "life": (round(float(life.min()), 6), round(float(life.max()), 6)),
            "fatigue_factor": (round(float(factor.min()), 6), round(float(factor.max()), 6)),
            "displacement": (0.0, summary["max_displacement_mm"]),
        }

    def extras_name(self, stem: str) -> str:
        return f"{stem} fatigue life"

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {key: summary[key] for key in ("weakest_part",) if key in summary}

    def study_echo(self, inputs: FatigueInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = super().study_echo(inputs, bare)
        echo["fatigue"] = {
            "from": inputs.source, "loading": inputs.loading, "stress_ratio": inputs.ratio, "cycles": inputs.cycles,
            "surface": inputs.surface, "factor": inputs.factor,
        }
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        sn = summary["sn"]
        loading = summary["loading"].replace("_", " ") if summary["loading"] != "ratio" else f"stress ratio R = {summary['stress_ratio']:g}"
        life = (f"shortest life {_cycles_words(summary['min_life_cycles'])} cycles" if summary["min_life_cycles"] is not None
                else f"life past {_cycles_words(summary['life_beyond_cycles'])} cycles everywhere (beyond the material's data)")
        return [
            f"fatigue from {summary['source']}, {loading}: peak von Mises {summary['max_von_mises_MPa']} MPa, "
            f"amplitude {summary['stress_amplitude_MPa']} MPa, mean {summary['mean_stress_MPa']} MPa",
            f"S-N line: UTS {sn['uts_MPa']:g} MPa; fatigue strength {sn['endurance_MPa']:g} MPa at {sn['endurance_cycles']:.3g} cycles "
            f"x surface {sn['surface_factor']:g} ({summary['surface'].replace('_', ' ')}) x factor {sn['factor']:g} "
            f"= {sn['corrected_endurance_MPa']:g} MPa; from 0.9 UTS at 1000 cycles",
            f"fatigue safety factor {summary['min_fatigue_factor']} at {summary['cycles']:.3g} cycles (modified Goodman); {life}",
            f"max displacement {summary['max_displacement_mm']} mm at the load's peak",
        ]


def _nodal(groups, curves, inputs: FatigueInputs, cycles: float, nodes: int):
    """Per node: the fatigue factor at ``cycles`` (at most FACTOR_CAP), the life in cycles (at most N_e) and the
    index of the material that governs it. ``groups`` are (nodes, their stress, material index) per part; a node
    on a joint takes the worse of its parts."""
    import numpy as np

    life = np.full(nodes, np.inf)
    factor = np.full(nodes, np.inf)
    governing = np.zeros(nodes, dtype=np.int64)
    for own, sigma, index in groups:
        curve = curves[index]
        amplitude, mean = inputs.amplitude_share * sigma[own], inputs.mean_share * sigma[own]
        n = goodman_factor(amplitude, mean, curve.strength(cycles), curve.uts)
        with np.errstate(divide="ignore", invalid="ignore"):
            equivalent = np.where(mean < curve.uts, amplitude / np.maximum(1.0 - mean / curve.uts, 1e-300), np.inf)
        worse = n < factor[own]
        governing[own[worse]] = index
        factor[own] = np.minimum(factor[own], n)
        life[own] = np.minimum(life[own], curve.life(equivalent))
    factor = np.where(np.isfinite(factor), factor, FACTOR_CAP)
    life = np.where(np.isfinite(life), life, max(curve.endurance_cycles for curve in curves))
    return factor, life, governing


def _finding(severity: str, kind: str, summary: str, description: str, items: list[dict]) -> dict:
    return {"check": "fea", "severity": severity, "type": kind, "summary": summary, "description": description, "items": items}

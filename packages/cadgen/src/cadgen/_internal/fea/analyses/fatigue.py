"""Fatigue life: how many cycles of a load the part survives, and its fatigue safety factor. Tier 1, a post-process.

The load comes from another analysis solved first on the same mesh
(``fatigue.from``), whose own study keys sit at the top level:

- ``static``: one load case, repeated ``cycles`` times, cycling fully reversed
  (R = -1), from zero (R = 0) or at a stress ratio R;
- ``harmonic``: a dwell of ``dwell_s`` seconds at the sweep's peak frequency f
  (the frame where the von Mises stress is highest), so the cycles are
  f × dwell_s, Goodman on that frame's stress, which swings about zero (fully
  reversed);
- ``random_vibration``: Steinberg's three-band method with Miner's rule over
  ``duration_s`` seconds: 68.3 % of the cycles at the 1σ (RMS) von Mises
  stress, 27.1 % at 2σ and 4.33 % at 3σ, the cycles counted at each node's
  zero-crossing rate ν0+ (random_vibration's ``stress_zero_crossing_Hz``), so
  the damage is ν0+ · duration_s · Σ p_k / N(k σ). The fatigue factor is how
  many times the stress may grow before that damage reaches 1, and the
  life 1 / (Σ p_k / N(k σ)) cycles. A stress at or under the endurance limit
  does no damage; a material with no endurance limit (aluminium, its data
  quoted past 1e8 cycles) keeps weakening along its Basquin line.

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
from cadgen._internal.fea.analyses.harmonic import HarmonicAnalysis
from cadgen._internal.fea.analyses.random_vibration import RandomVibrationAnalysis
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs
from cadgen._internal.fea.materials import NONE_REASONS, Material, material_from_spec

__all__ = [
    "FACTOR_CAP", "FatigueAnalysis", "FatigueInputs", "LOW_CYCLES", "SNCurve", "STEINBERG", "SURFACE_FACTORS",
    "goodman_factor", "marin_surface", "miner_life", "sn_curve", "steinberg_damage", "steinberg_factor", "stress_ratio",
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
#: Each source's own study keys (top level) and the fatigue key that says how long it runs.
SOURCE_KEYS: dict[str, frozenset[str]] = {
    "static": StaticAnalysis.study_keys,
    "harmonic": HarmonicAnalysis.study_keys,
    "random_vibration": RandomVibrationAnalysis.study_keys,
}
DURATION_KEY = {"harmonic": "dwell_s", "random_vibration": "duration_s"}
#: Steinberg's three bands of a Gaussian response: (multiple of the RMS stress, share of the cycles).
STEINBERG: tuple[tuple[float, float], ...] = ((1.0, 0.683), (2.0, 0.271), (3.0, 0.0433))
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


def miner_life(curve: "SNCurve", stress):
    """Cycles to failure at a fully reversed stress (a number or an array), for Miner's sum: the Basquin line,
    at least 1 cycle. A stress at or under the endurance strength of a material that has an endurance limit does
    no damage (infinite life); one with none (its data quoted past :data:`NO_ENDURANCE_LIMIT_FROM` cycles) keeps
    weakening along the line past its last data point."""
    import numpy as np

    sigma = np.asarray(stress, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        cycles = np.where(sigma > 0, (np.maximum(sigma, 1e-300) / curve.A) ** (1.0 / curve.b), np.inf)
    if curve.endurance_cycles < NO_ENDURANCE_LIMIT_FROM:
        cycles = np.where(sigma <= curve.endurance, np.inf, cycles)
    return np.maximum(cycles, 1.0)


def steinberg_damage(curve: "SNCurve", rms):
    """Miner damage per cycle of a Gaussian response at an RMS (1σ) stress, Steinberg's three bands:
    Σ p_k / N(k σ) over (1σ, 68.3 %), (2σ, 27.1 %), (3σ, 4.33 %)."""
    import numpy as np

    sigma = np.asarray(rms, dtype=float)
    return sum(share / miner_life(curve, k * sigma) for k, share in STEINBERG)


def steinberg_factor(curve: "SNCurve", rms, cycles):
    """The fatigue factor n of a Gaussian response at an RMS stress over ``cycles`` (numbers or arrays): the stress
    may grow n times before Miner's damage, cycles × :func:`steinberg_damage` (n σ), reaches 1. On the Basquin line
    alone that is n = (cycles · D(σ))^b; past an endurance limit it is found by bisection. At most FACTOR_CAP (no
    stress, or too few cycles to wear it out at any stress)."""
    import numpy as np

    sigma, count = np.broadcast_arrays(np.asarray(rms, dtype=float), np.asarray(cycles, dtype=float))
    low, high = np.full(sigma.shape, 1e-6), np.full(sigma.shape, FACTOR_CAP)
    for _ in range(100):  # the damage grows with n: halve the bracket in log n
        middle = np.sqrt(low * high)
        over = count * steinberg_damage(curve, sigma * middle) > 1.0
        low, high = np.where(over, low, middle), np.where(over, middle, high)
    return np.where(sigma > 0, np.minimum(np.sqrt(low * high), FACTOR_CAP), FACTOR_CAP)


def goodman_factor(amplitude, mean, strength, uts):
    """The modified Goodman safety factor n: σa / Sf + σm / Sut = 1 / n (numbers or arrays); at most FACTOR_CAP."""
    import numpy as np

    use = np.asarray(amplitude, dtype=float) / strength + np.asarray(mean, dtype=float) / uts
    with np.errstate(divide="ignore"):
        return np.minimum(np.where(use > 0, 1.0 / np.maximum(use, 1e-300), FACTOR_CAP), FACTOR_CAP)


@dataclass(frozen=True)
class FatigueInputs(StaticInputs):
    source: str = "static"
    #: "fully_reversed", "zero_based" or "ratio" (with ``ratio``); a vibration source is fully reversed.
    loading: str = "fully_reversed"
    ratio: float = -1.0
    #: The cycles needed (static); a vibration source counts its own after the solve (``None``).
    cycles: float | None = DEFAULT_CYCLES
    surface: str = "machined"
    factor: float = 1.0
    #: harmonic: the seconds it dwells at the peak frequency; random_vibration: the seconds it is shaken.
    dwell_s: float | None = None
    duration_s: float | None = None
    #: A vibration source's own parsed inputs (its analysis's ``parse`` of the same study).
    source_inputs: Any = None

    @property
    def seconds(self) -> float | None:
        return self.dwell_s if self.source == "harmonic" else self.duration_s

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
    for key, owner in (("dwell_s", "harmonic"), ("duration_s", "random_vibration")):
        if key in raw and source != owner:
            how = "repeats its load case for cycles" if source == "static" else f"is shaken for {DURATION_KEY[source]}"
            raise ValueError(f"{where}.{key}: goes with from {owner}; a {source.replace('_', ' ')} source {how}")
    if source != "static":
        return _vibration_block(raw, source, where)
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


def _vibration_block(raw: dict, source: str, where: str) -> dict:
    """A harmonic or random_vibration source: how long it is shaken; its stress swings about zero, its cycles its own."""
    key = DURATION_KEY[source]
    counted = "the peak frequency × dwell_s" if source == "harmonic" else "its zero-crossing rate × duration_s"
    if key not in raw:
        raise ValueError(f'{where}.{key}: how long it is shaken, in seconds, like {{"from": "{source}", "{key}": 3600}}; '
                         f"the cycles are {counted}")
    seconds = kinds.number(raw[key], where=f"{where}.{key}", positive=True)
    if "cycles" in raw:
        raise ValueError(f"{where}.cycles: a {source.replace('_', ' ')} source counts its own cycles ({counted}); "
                         f"give {key} instead (a check's cycles may still ask for more)")
    if "loading" in raw and raw["loading"] != "fully_reversed":
        raise ValueError(f"{where}.loading: a vibration's stress swings about zero, so it is fully reversed; leave loading out")
    surface = raw.get("surface", "machined")
    if surface not in SURFACES:
        raise ValueError(f"{where}.surface: {kinds.json_text(surface)} is not one of {list(SURFACES)}")
    factor = kinds.number(raw["factor"], where=f"{where}.factor", positive=True) if "factor" in raw else 1.0
    if factor > 1:
        raise ValueError(f"{where}.factor: the other Marin factors (size, load, temperature, reliability) multiplied, "
                         f"from 0 to 1, got {factor:g}")
    return {"source": source, "loading": "fully_reversed", "ratio": -1.0, "cycles": None, "surface": surface,
            "factor": factor, key: seconds}


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
    # Its own block, and every source's keys (each study is checked against its own source's in parse).
    study_keys: ClassVar[frozenset[str]] = frozenset({"fatigue"}).union(*SOURCE_KEYS.values())
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
    # The default source's; a study's own is its `fatigue.from` (upstream_for).
    upstream: ClassVar[tuple[str, ...]] = ("static",)
    # Its source's ladder: the source's solve is the one that is fitted. Every source's rungs, in each one's order;
    # a rung its source does not take is skipped (apply), so a static source climbs static's ladder as before.
    ladder: ClassVar[tuple[str, ...]] = (
        "reduce_modes", "frequency_grid", "iterative", "local_refine", "defeature", "linear_elements", "idealise", "symmetry",
    )
    noun: ClassVar[str] = "this load"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> FatigueInputs:
        block = _fatigue_block(document)
        if "material" in document:
            _require_fatigue_data(document["material"], "material")
        for name, entry in (document.get("parts") or {}).items() if isinstance(document.get("parts"), dict) else ():
            if isinstance(entry, dict) and "material" in entry:
                _require_fatigue_data(entry["material"], f"parts[{name!r}].material")
        source = block["source"]
        own = SOURCE_KEYS[source]
        stray = sorted((set(document) & self.study_keys) - own - {"fatigue"})
        if stray:
            raise ValueError(f"study: {stray} go with another fatigue source; fatigue from {source} takes "
                             f"{', '.join(sorted(own | {'fatigue'}))}")
        if source == "static":
            static = StaticAnalysis.parse(self, document)
            return FatigueInputs(
                static.face_refs, static.anchor_refs, True, fixtures=static.fixtures, loads=static.loads,
                material_needs=static.material_needs, **block,
            )
        analysis = _source_analysis(source)
        inputs = analysis.parse({key: value for key, value in document.items() if key != "fatigue"})
        return FatigueInputs(
            inputs.face_refs, inputs.anchor_refs, inputs.requires_anchor, fixtures=inputs.fixtures,
            loads=tuple(getattr(inputs, "loads", ())), material_needs=frozenset(analysis.material_needs),
            source_inputs=inputs, **block,
        )

    def upstream_for(self, inputs: FatigueInputs) -> tuple[str, ...]:
        """The analysis solved first on the same mesh: the study's own source."""
        return (inputs.source,)

    # -- the ladder: the source's -------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: FatigueInputs):
        if inputs.source == "static":
            return StaticAnalysis.estimate(self, ctx, inputs)
        return _source_analysis(inputs.source).estimate(ctx, inputs.source_inputs)

    def apply(self, rung, ctx: SolveContext, inputs: FatigueInputs):
        if inputs.source == "static":
            return StaticAnalysis.apply(self, rung, ctx, inputs) if rung in StaticAnalysis.ladder else None
        analysis = _source_analysis(inputs.source)
        return analysis.apply(rung, ctx, inputs.source_inputs) if rung in analysis.ladder else None

    def governing(self, result: AnalysisResult):
        if result.scalars.get("fatigue_source", "static") == "static":
            return StaticAnalysis.governing(self, result)
        stress = result.fields["von_mises"]
        return stress, float(stress.max())

    def settle_steps(self, result: AnalysisResult, steps: list) -> list:
        """A vibration source's steps, said once its solve knows what it did (the modes it kept)."""
        source = result.scalars.get("fatigue_source", "static")
        if source == "static":
            return list(steps)
        return _source_analysis(source).settle_steps(result, steps)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: FatigueInputs) -> AnalysisResult:
        """Life and fatigue factor at every node from the source's von Mises stress, per part's material."""
        import numpy as np

        if inputs.source != "static":
            return self._solve_vibration(ctx, inputs)
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

    def _solve_vibration(self, ctx: SolveContext, inputs: FatigueInputs) -> AnalysisResult:
        """harmonic: Goodman on the peak frame's stress (fully reversed) at f × dwell_s cycles. random_vibration:
        Steinberg's three bands and Miner's rule over duration_s at each node's zero-crossing rate."""
        import numpy as np

        analysis = _source_analysis(inputs.source)
        source = ctx.upstream.get(inputs.source)
        if source is None:  # called on its own: solve the source here, on the same space
            source = analysis.solve(ctx, inputs.source_inputs)
            ctx.upstream[inputs.source] = source
        curves = [sn_curve(material, surface=inputs.surface, factor=inputs.factor) for material in ctx.materials]
        extra: dict[str, Any] = {"fatigue_source": inputs.source}
        fields: dict[str, Any] = {}
        deformation = None
        if inputs.source == "harmonic":
            frames = source.scalars["stress_frames"]
            frame = max(range(len(frames)), key=lambda i: float(frames[i].max()))
            stress = np.asarray(frames[frame], dtype=float)
            peak_Hz = float(source.scalars["frame_Hz"][frame])
            need = peak_Hz * inputs.dwell_s
            groups = _groups(ctx, source, stress)
            factor, life, governing = _nodal(groups, curves, inputs, need, len(stress))
            deformation = _widest_phase(source.frame_fields["displacement"][frame], source.frame_fields["displacement_im"][frame])
            fields["displacement"] = deformation
            extra.update({"peak_frame": frame, "peak_Hz": peak_Hz, "need_cycles": need})
        else:
            stress = np.asarray(source.fields["von_mises_rms"], dtype=float)
            rate = np.asarray(source.scalars["stress_zero_crossing_Hz"], dtype=float)
            rate_at_peak = float(source.scalars["zero_crossing_Hz"])
            groups = _groups(ctx, source, stress)
            factor, life, governing = _random_nodal(groups, curves, rate * inputs.duration_s, len(stress))
            extra.update({"zero_crossing_rate": rate, "zero_crossing_Hz": rate_at_peak,
                          "need_cycles": rate_at_peak * inputs.duration_s})
        return AnalysisResult(
            dof_locations=source.dof_locations,
            vertices=source.vertices,
            tets=source.tets,
            boundary_quadratic=source.boundary_quadratic,
            element_dofs=source.element_dofs,
            fields={"life": np.log10(life), "fatigue_factor": factor, **fields, "von_mises": stress},
            deformation=deformation,
            scalars={**source.scalars, **extra, "curves": curves, "groups": groups, "life_cycles": life,
                     "governing": governing, "source_summary": source.scalars.get("summary")},
            reactions=list(source.reactions),
            applied=tuple(source.applied),
            dofs=source.dofs,
            solver=source.solver,
            timings=dict(source.timings),
            warnings=list(source.warnings),
        )

    def _need(self, result: AnalysisResult, inputs: FatigueInputs) -> float:
        """The cycles the study needs: its own (static), or f × dwell_s, or ν0+ × duration_s at the peak (vibration)."""
        return inputs.cycles if inputs.source == "static" else float(result.scalars["need_cycles"])

    def _at(self, result: AnalysisResult, inputs: FatigueInputs, cycles: float | None):
        """The fatigue factor at ``cycles`` at every node, each part's stress against its own material. A random
        source with no cycles given counts each node's own (its zero-crossing rate × duration_s)."""
        curves = result.scalars["curves"]
        nodes = len(result.fields["von_mises"])
        if inputs.source == "random_vibration":
            import numpy as np

            counts = result.scalars["zero_crossing_rate"] * inputs.duration_s if cycles is None else np.full(nodes, cycles)
            return _random_nodal(result.scalars["groups"], curves, counts, nodes)[0]
        return _nodal(result.scalars["groups"], curves, inputs, self._need(result, inputs) if cycles is None else cycles, nodes)[0]

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        if result.scalars.get("fatigue_source", "static") == "static":
            return StaticAnalysis.refined_record(self, result, size_mm, finer_mm, assembly=assembly)
        return {"from_size_mm": round(size_mm, 4), "from_max_von_mises_MPa": round(float(result.fields["von_mises"].max()), 4),
                "size_mm": round(finer_mm, 4), "max_von_mises_MPa": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        if finer.scalars.get("fatigue_source", "static") == "static":
            return StaticAnalysis.merge_finer(self, coarse, finer, refined)
        refined["max_von_mises_MPa"] = round(float(finer.fields["von_mises"].max()), 4)
        finer.scalars["coarser_peak_MPa"] = float(coarse.fields["von_mises"].max())
        return finer

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

        given = check.get("cycles")
        cycles = float(given) if given is not None else self._need(result, inputs)
        margin = float(check.get("margin", 1.5))
        factor = self._at(result, inputs, None if given is None else cycles)
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
                 if finding["type"] != "low_margin"] if inputs.source == "static" else []
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
                    f"{_method_words(inputs)} factor {judged['value']:.3f} at {judged['need']:.3g} cycles, "
                    f"{inputs.loading.replace('_', ' ')} loading",
                    item))
            elif judged["status"] == "close":
                found.append(_finding(
                    "warning", "low_fatigue_margin",
                    f"It lasts the {needs} cycles it needs, but only with a fatigue safety factor of {judged['value']:.2f}, "
                    f"under the {judged['margin']:g} margin",
                    f"{_method_words(inputs)} factor {judged['value']:.3f} at {judged['need']:.3g} cycles", item))
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

        if inputs.source != "static":
            return self._vibration_summary(result, inputs, check_results)
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

    def _vibration_summary(self, result: AnalysisResult, inputs: FatigueInputs, check_results: list[dict]) -> dict:
        """A vibration source's: the stress it swings by, how long and how fast, the factor and the life."""
        import numpy as np

        stress = result.fields["von_mises"]
        peak = int(stress.argmax())
        factor = result.fields["fatigue_factor"]
        life = result.scalars["life_cycles"]
        curves = result.scalars["curves"]
        worst = int(np.argmin(factor))
        curve = curves[int(result.scalars["governing"][worst])]
        runout = float(life.min()) >= max(c.endurance_cycles for c in curves)
        summary: dict[str, Any] = {
            "source": inputs.source,
            "loading": "fully_reversed",
            "stress_ratio": -1.0,
            "cycles": float(f"{self._need(result, inputs):.6g}"),
            "surface": inputs.surface,
        }
        if inputs.source == "harmonic":
            summary.update({
                "method": "goodman",
                "dwell_s": inputs.dwell_s,
                "peak_Hz": round(result.scalars["peak_Hz"], 4),
                "max_von_mises_MPa": round(float(stress[peak]), 4),
                "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[peak]],
                "stress_amplitude_MPa": round(float(stress[peak]), 4),
                "mean_stress_MPa": 0.0,
            })
        else:
            summary.update({
                "method": "steinberg_miner",
                "duration_s": inputs.duration_s,
                "zero_crossing_Hz": round(result.scalars["zero_crossing_Hz"], 4),
                "max_von_mises_rms_MPa": round(float(stress[peak]), 4),
                "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[peak]],
                "bands": [{"sigma": k, "share": share} for k, share in STEINBERG],
            })
        summary.update({
            "min_fatigue_factor": _floored(float(factor[worst])),
            "min_fatigue_factor_at_mm": [round(float(c), 3) for c in result.dof_locations[worst]],
            "min_life_cycles": None if runout else float(f"{float(life.min()):.4g}"),
            "life_beyond_cycles": curve.endurance_cycles if runout else None,
            "sn": curve.as_dict(),
        })
        if "displacement" in result.fields:
            summary["max_displacement_mm"] = round(float(np.linalg.norm(result.fields["displacement"], axis=1).max()), 6)
            summary["deformation_scale"] = result.scalars.get("deformation_scale")
        summary["checks"] = check_results
        return summary

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        if "displacement" not in result.fields:  # a random response has no shape to deform by
            return None
        return StaticAnalysis.deformation_scale(self, result, bbox_diagonal, requested)

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        life = result.fields["life"]
        factor = result.fields["fatigue_factor"]
        ranges = {
            "life": (round(float(life.min()), 6), round(float(life.max()), 6)),
            "fatigue_factor": (round(float(factor.min()), 6), round(float(factor.max()), 6)),
        }
        if "displacement" in result.fields:
            ranges["displacement"] = (0.0, summary["max_displacement_mm"])
        return ranges

    def extras_name(self, stem: str) -> str:
        return f"{stem} fatigue life"

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {key: summary[key] for key in ("weakest_part",) if key in summary}

    def study_echo(self, inputs: FatigueInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        if inputs.source != "static":
            echo = _source_analysis(inputs.source).study_echo(inputs.source_inputs, bare)
            key = DURATION_KEY[inputs.source]
            echo["fatigue"] = {"from": inputs.source, "loading": inputs.loading, "stress_ratio": inputs.ratio,
                               key: getattr(inputs, key), "surface": inputs.surface, "factor": inputs.factor}
            return echo
        echo = super().study_echo(inputs, bare)
        echo["fatigue"] = {
            "from": inputs.source, "loading": inputs.loading, "stress_ratio": inputs.ratio, "cycles": inputs.cycles,
            "surface": inputs.surface, "factor": inputs.factor,
        }
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        if summary["source"] != "static":
            return _vibration_lines(summary)
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


def _source_analysis(name: str):
    from cadgen._internal.fea.analyses import get_analysis

    return get_analysis(name)


def _widest_phase(re, im):
    """The frame's motion at the moment of its cycle it moves most: re·cos φ − im·sin φ at the φ that maximises
    its size (at a resonance the motion is nearly all imaginary, so the real part alone would show nothing)."""
    import numpy as np

    a, b, c = float((re * re).sum()), float((re * im).sum()), float((im * im).sum())
    phi = 0.5 * math.atan2(-2.0 * b, a - c)
    return np.cos(phi) * re - np.sin(phi) * im


def _groups(ctx: SolveContext, source: AnalysisResult, stress) -> list:
    """(nodes, their stress, material index) per part: one group for a single material."""
    import numpy as np

    if len(ctx.materials) == 1 or ctx.volume is None or ctx.volume.domain is None:
        return [(np.arange(len(stress)), stress, 0)]
    return [(np.unique(source.element_dofs[ctx.volume.domain == index]), stress, index) for index in range(len(ctx.materials))]


def _method_words(inputs: FatigueInputs) -> str:
    return "Steinberg-Miner" if inputs.source == "random_vibration" else "modified Goodman"


def _vibration_lines(summary: dict) -> list[str]:
    sn = summary["sn"]
    life = (f"shortest life {_cycles_words(summary['min_life_cycles'])} cycles" if summary["min_life_cycles"] is not None
            else f"life past {_cycles_words(summary['life_beyond_cycles'])} cycles everywhere (beyond the material's data)")
    if summary["source"] == "harmonic":
        head = (f"fatigue from harmonic, a {summary['dwell_s']:g} s dwell at {summary['peak_Hz']:g} Hz "
                f"({_cycles_words(summary['cycles'])} cycles): stress swinging {summary['stress_amplitude_MPa']} MPa "
                "about zero (fully reversed)")
        method = f"fatigue safety factor {summary['min_fatigue_factor']} at {summary['cycles']:.3g} cycles (modified Goodman); {life}"
    else:
        head = (f"fatigue from random_vibration, {summary['duration_s']:g} s at {summary['zero_crossing_Hz']:g} Hz zero "
                f"crossings ({_cycles_words(summary['cycles'])} cycles): {summary['max_von_mises_rms_MPa']} MPa rms; "
                "Steinberg bands 68.3% at 1σ, 27.1% at 2σ, 4.33% at 3σ")
        method = f"fatigue safety factor {summary['min_fatigue_factor']} over the shake (Miner's rule); {life}"
    return [
        head,
        f"S-N line: UTS {sn['uts_MPa']:g} MPa; fatigue strength {sn['endurance_MPa']:g} MPa at {sn['endurance_cycles']:.3g} cycles "
        f"x surface {sn['surface_factor']:g} ({summary['surface'].replace('_', ' ')}) x factor {sn['factor']:g} "
        f"= {sn['corrected_endurance_MPa']:g} MPa; from 0.9 UTS at 1000 cycles",
        method,
    ]


def _random_nodal(groups, curves, cycles, nodes: int):
    """Per node, for a random response's RMS stress: the Steinberg-Miner fatigue factor over ``cycles`` (per node),
    the life in cycles (1 / the damage per cycle, at most N_e) and the material that governs it."""
    import numpy as np

    life = np.full(nodes, np.inf)
    factor = np.full(nodes, np.inf)
    governing = np.zeros(nodes, dtype=np.int64)
    counts = np.broadcast_to(np.asarray(cycles, dtype=float), (nodes,))
    for own, sigma, index in groups:
        curve = curves[index]
        n = steinberg_factor(curve, sigma[own], counts[own])
        damage = steinberg_damage(curve, sigma[own])
        with np.errstate(divide="ignore"):
            lasts = np.where(damage > 0, 1.0 / np.maximum(damage, 1e-300), np.inf)
        worse = n < factor[own]
        governing[own[worse]] = index
        factor[own] = np.minimum(factor[own], n)
        life[own] = np.minimum(life[own], lasts)
    beyond = max(curve.endurance_cycles for curve in curves)
    factor = np.where(np.isfinite(factor), factor, FACTOR_CAP)
    life = np.clip(np.where(np.isfinite(life), life, beyond), 1.0, beyond)
    return factor, life, governing


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

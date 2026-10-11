"""Piezo (lite): coupled electro-mechanical parts, actuators, sensors and buzzers. Tier 3.

Linear piezoelectricity in the stress-charge form (piezo_ops.py): the
displacement and the voltage solved together, each piezo part with its
material's c^E, e and eps^S turned to its poling direction. The study names a
``solve``:

- ``static`` (the default): electrodes held at a voltage drive the part
  (actuation: displacement and stress), and forces or pressures press it; an
  open electrode floats, one voltage over its faces with no net charge, so a
  force on a sensor makes a voltage there (sensing). Numbers: each electrode's
  voltage and charge, the capacitance between the held electrodes (with no
  load), the largest displacement, stress and field. Checks: ``stress``,
  ``displacement`` and ``voltage`` (an open electrode's signal against the
  least it must make).
- ``resonance``: the natural frequencies with the electrodes shorted
  (resonance, fr) and open (anti-resonance, fa: every electrode not at 0 V
  floats), paired mode by mode, and each mode's effective coupling
  k_eff² = (fa² − fr²) / fa²; with the blocked (clamped) capacitance. Fixtures
  are optional (a free part's rigid-body motions are left out). Check:
  ``frequency``.
- ``harmonic``: the electrodes' voltages (amplitudes) and any loads at each
  frequency of ``sweep_Hz``, with a loss ``damping_ratio``: the displacement,
  the current into the driven electrode and its admittance, an open
  electrode's voltage, frame by frame. Checks: ``stress``, ``displacement``,
  ``voltage`` (at the sweep's worst).

A conducting part (a brass shim) is one voltage throughout, held when an
electrode is on it; a dielectric part (a plastic, with its permittivity) carries
field but no coupling; any other part only stiffness and mass. Limits: linear,
small signal; no depolarisation, hysteresis or heating. Ladder: iterative
(static: MINRES with block multigrid), local_refine, symmetry (static and
harmonic, about a plane along every poling direction) and reduce_modes (fewer
modes, or the sweep by modes). Stdlib at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext

__all__ = ["LIMITS", "PiezoAnalysis", "PiezoInputs", "SOLVES", "farads_text", "hertz_text"]

SOLVES = ("static", "resonance", "harmonic")
LIMITS = (
    "Linear, small signal: room-temperature constants at low field; no depolarisation, hysteresis, ageing or "
    "self-heating, so a field near the coercive field (about 1 kV/mm for soft PZT), a large stress or a hot part "
    "departs from it.",
)
#: The checks each solve judges.
SOLVE_CHECKS = {"static": ("stress", "displacement", "voltage"), "resonance": ("frequency",),
                "harmonic": ("stress", "displacement", "voltage")}
#: A mode under this frequency, or under 1 % of the first elastic one, is a rigid-body motion.
RIGID_HZ, RIGID_FRACTION = 0.5, 0.01
#: A check is close within 10 % of its limit.
CLOSE_AT = 0.9
#: The sweep's own points (log spaced), before the points around each resonance.
POINTS = 60
#: Phases at which a frame's stress is sampled for its peak over the cycle.
PHASES = 8
MAX_MODES = 30
_TWO_PI = 2.0 * math.pi

_FIELD_SPECS = {
    "static": (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
        FieldSpec("potential", "_POTENTIAL", "voltage", "V", signed=True),
        FieldSpec("electric_field", "_ELECTRIC_FIELD", "electric field", "kV/mm"),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
    ),
    "resonance": (
        FieldSpec("mode_shape", "_DISPLACEMENT", "mode shape", "mm", 3, 1000.0, per_frame=True),
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress (mode shape scaled to 1 mm)", "MPa", per_frame=True),
        FieldSpec("potential", "_POTENTIAL", "voltage (mode shape scaled to 1 mm)", "V", signed=True, per_frame=True),
    ),
    "harmonic": (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress (peak over the cycle)", "MPa", per_frame=True),
        FieldSpec("potential", "_POTENTIAL", "voltage amplitude", "V", per_frame=True),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0, per_frame=True),
    ),
}


def hertz_text(f: float) -> str:
    """A frequency as a person says it: "850 Hz", "15.8 kHz", "2.04 MHz"."""
    for scale, unit in ((1e6, "MHz"), (1e3, "kHz")):
        if f >= scale:
            return f"{f / scale:.3g} {unit}"
    return f"{f:.3g} Hz"


def farads_text(farads: float) -> str:
    """A capacitance as a datasheet writes it: "4.7 nF", "220 pF", "1.2 µF"."""
    for scale, unit in ((1e-6, "µF"), (1e-9, "nF"), (1e-12, "pF")):
        if abs(farads) >= scale:
            return f"{farads / scale:.3g} {unit}"
    return f"{farads * 1e15:.3g} fF"


@dataclass(frozen=True)
class ElectrodeSpec:
    name: str
    faces: tuple[str, ...]
    #: Held at this voltage (an amplitude in a sweep), or ``None``: open, floating.
    volts: float | None


@dataclass(frozen=True)
class PiezoInputs(Inputs):
    solve: str = "static"
    electrodes: tuple[ElectrodeSpec, ...] = ()
    fixtures: tuple = ()
    loads: tuple = ()
    modes: int = 6
    sweep_Hz: tuple[float, float] | None = None
    damping_ratio: float = 0.01
    points: int = POINTS
    checks: tuple = ()
    material_needs: frozenset[str] = frozenset()
    #: What the solve resolved (each piezo part's poling), written once by ``solve`` for the study's echo.
    resolved: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def open(self) -> tuple[ElectrodeSpec, ...]:
        return tuple(e for e in self.electrodes if e.volts is None)

    @property
    def held(self) -> tuple[ElectrodeSpec, ...]:
        return tuple(e for e in self.electrodes if e.volts is not None)


# -- parse --------------------------------------------------------------------------------------------


def _known(entry: dict, keys: set[str], where: str, words: str) -> None:
    unknown = set(entry) - keys
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; {words}")


def _electrodes(document: dict) -> tuple[ElectrodeSpec, ...]:
    raw = document.get("electrodes")
    example = '[{"faces": ["#o1.f6"], "V": 100, "name": "top"}, {"faces": ["#o1.f5"], "V": 0, "name": "ground"}]'
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"electrodes: a piezo study needs its electrodes, the faces painted with metal, like {example} "
                         '(an open one, the sensing side, is {"faces": [...], "open": true})')
    out = []
    for index, entry in enumerate(raw):
        where = f"electrodes[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected an object like {{\"faces\": [\"#o1.f6\"], \"V\": 100}}")
        _known(entry, {"faces", "V", "open", "name"}, where,
               "an electrode takes faces, V (held at a voltage) or open (true: it floats) and an optional name")
        is_open = entry.get("open", False)
        if not isinstance(is_open, bool):
            raise ValueError(f"{where}.open: true (the electrode floats: nothing is connected) or false")
        if is_open == ("V" in entry):
            raise ValueError(f"{where}: give V (the voltage it is held at; 0 is ground) or \"open\": true (it floats, "
                             "as a sensor's output does), one of the two")
        volts = None if is_open else kinds.number(entry["V"], where=f"{where}.V")
        name = kinds.text(entry, "name", where=where).get("name") or (f"open {index + 1}" if volts is None else f"{volts:g} V")
        out.append(ElectrodeSpec(name, kinds.faces(entry, where=where), volts))
    names = [e.name for e in out]
    if len(set(names)) != len(names):
        raise ValueError("electrodes: two are named the same; give each a 'name' of its own")
    return tuple(out)


def _checks_of(document: dict) -> list[tuple[int, dict]]:
    view = document.get("view")
    checks = view.get("checks") if isinstance(view, dict) else None
    return [(i, c) for i, c in enumerate(checks) if isinstance(c, dict)] if isinstance(checks, list) else []


def _materials_of(document: dict) -> list:
    from cadgen._internal.fea.materials import material_from_spec

    found = []
    if "material" in document:
        found.append(material_from_spec(document["material"]))
    parts = document.get("parts")
    if isinstance(parts, dict):
        found += [material_from_spec(entry["material"]) for entry in parts.values() if isinstance(entry, dict) and "material" in entry]
    return found


def parse_document(document: dict) -> PiezoInputs:
    from cadgen._internal.fea.study import parse_fixtures, parse_loads

    solve = document.get("solve", "static")
    if solve not in SOLVES:
        raise ValueError(f"solve: {kinds.json_text(solve)} is not one of {list(SOLVES)}: static (a voltage moves it, or a "
                         "force makes a voltage), resonance (its frequencies shorted and open, and the coupling) or harmonic "
                         "(driven over a band of frequencies: displacement, current, admittance)")
    allowed = {"static": {"fixtures", "loads"}, "resonance": {"fixtures", "modes"},
               "harmonic": {"fixtures", "loads", "sweep_Hz", "damping_ratio", "points", "modes"}}[solve]
    own = {"fixtures", "loads", "modes", "sweep_Hz", "damping_ratio", "points"}
    if stray := sorted((set(document) & own) - allowed):
        raise ValueError(f"study: {', '.join(stray)} {'is' if len(stray) == 1 else 'are'} not for a {solve} piezo study; "
                         f"it takes electrodes, {', '.join(sorted(allowed))}")
    electrodes = _electrodes(document)
    held = [e for e in electrodes if e.volts is not None]
    fixtures: tuple = ()
    loads: tuple = ()
    modes = 6
    sweep = None
    zeta = 0.01
    points = POINTS
    if solve in ("static", "harmonic"):
        if not held:
            raise ValueError("electrodes: hold at least one electrode at a voltage (0 V for ground); with every electrode "
                             "open the voltage has no reference")
        fixtures = parse_fixtures(document)
        loads = parse_loads(document, required=False, body=False)
    else:
        fixtures = parse_fixtures(document, required=False)
        if not any(e.volts == 0 for e in electrodes):
            raise ValueError("electrodes: a resonance study needs a ground, an electrode at 0 V, and the electrode it is "
                             "driven or read through (any V, or open)")
        if all(e.volts == 0 for e in electrodes):
            raise ValueError("electrodes: every electrode is at 0 V, so nothing opens at anti-resonance; give the driven "
                             "electrode its voltage (any V) or mark it open")
    if "modes" in document:
        modes = document["modes"]
        if isinstance(modes, bool) or not isinstance(modes, int) or not 1 <= modes <= MAX_MODES:
            raise ValueError(f"modes: how many modes to find, a whole number from 1 to {MAX_MODES}, got {kinds.json_text(modes)}")
    if solve == "harmonic":
        raw = document.get("sweep_Hz")
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("sweep_Hz: the band to drive it over as [low, high] in Hz, like [1000, 50000]")
        low, high = (kinds.number(v, where="sweep_Hz", positive=True) for v in raw)
        if not low < high:
            raise ValueError(f"sweep_Hz: low ({low:g}) must be below high ({high:g})")
        sweep = (low, high)
        if "damping_ratio" in document:
            zeta = kinds.number(document["damping_ratio"], where="damping_ratio", positive=True)
            if zeta >= 0.5:
                raise ValueError(f"damping_ratio: the share of critical damping, under 0.5 (a PZT-4 disc is about 0.001, "
                                 f"PZT-5A 0.007, a mounted part 0.01 to 0.05), got {zeta:g}")
        if "points" in document:
            points = document["points"]
            if isinstance(points, bool) or not isinstance(points, int) or not 10 <= points <= 400:
                raise ValueError(f"points: the sweep's frequencies, a whole number from 10 to 400, got {kinds.json_text(points)}")
    checks = []
    allowed_checks = SOLVE_CHECKS[solve]
    for index, entry in _checks_of(document):
        kind = entry.get("kind")
        if kind in ("stress", "displacement", "voltage", "frequency") and kind not in allowed_checks:
            raise ValueError(f"view.checks[{index}]: a {kind} check is not for a {solve} piezo study; it takes "
                             f"{', '.join(allowed_checks)}")
        if kind == "voltage":
            spec = kinds.VOLTAGE.parse(entry, f"view.checks[{index}]")
            opened = [e.name for e in electrodes if e.volts is None]
            if not opened:
                raise ValueError(f"view.checks[{index}]: a voltage check reads an open electrode's signal; mark the sensing "
                                 'electrode "open": true')
            if spec.get("electrode", opened[0]) not in opened:
                raise ValueError(f"view.checks[{index}].electrode: {kinds.json_text(spec['electrode'])} is not an open "
                                 f"electrode; the open ones are {opened}")
            checks.append(spec)
    materials = _materials_of(document)
    if materials and not any(m.piezo for m in materials):
        raise ValueError("material: a piezo study needs a piezo ceramic in at least one part: name one (\"pzt-4\", "
                         "\"pzt-5a\" or \"pzt-5h\"), or give the material object a piezo block with cE_GPa, e_C_m2, "
                         "epsS_rel and poling")
    needs = {"density"} if solve != "static" else set()
    refs = [ref for e in electrodes for ref in e.faces]
    refs += [ref for fixture in fixtures for ref in fixture.faces]
    refs += [ref for load in loads for ref in load.faces]
    anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
    return PiezoInputs(
        tuple(dict.fromkeys(refs)), anchors, solve != "resonance", solve=solve, electrodes=electrodes, fixtures=fixtures,
        loads=loads, modes=modes, sweep_Hz=sweep, damping_ratio=zeta, points=points, checks=tuple(checks),
        material_needs=frozenset(needs),
    )


# -- the solve's pieces --------------------------------------------------------------------------------


def _part_constants(materials) -> list:
    from cadgen._internal.fea import piezo_ops
    from cadgen._internal.fea.em_ops import CONDUCTOR_BELOW_OHM_M
    from cadgen._internal.fea.operators import elasticity_matrix

    out = []
    for m in materials:
        if m.piezo:
            c, e, eps = piezo_ops.global_constants(m.piezo)
            out.append(piezo_ops.PartConstants("piezo", c, m.density, e, eps))
        elif m.resistivity is not None and m.resistivity < CONDUCTOR_BELOW_OHM_M:
            out.append(piezo_ops.PartConstants("conductor", elasticity_matrix(m), m.density))
        elif m.permittivity:
            import numpy as np

            eps = np.eye(3) * m.permittivity * piezo_ops.EPS0_F_M
            out.append(piezo_ops.PartConstants("dielectric", elasticity_matrix(m), m.density, None, eps))
        else:
            out.append(piezo_ops.PartConstants("inert", elasticity_matrix(m), m.density))
    return out


def _face_dofs(space, refs, ordinal_of, where: str):
    import numpy as np

    ordinals = [ordinal_of[ref] for ref in refs]
    rows = np.isin(space.volume.boundary_ordinal, ordinals)
    if not rows.any():
        raise ValueError(f"{where}: {', '.join(refs)} has no surface in the mesh (it is wholly a joint between parts, or "
                         "on the half a symmetry cut left out); choose a face that is not covered by another part")
    return np.unique(space.boundary_quadratic[rows])


def _conductor_dofs(space, parts) -> list:
    import numpy as np

    out = []
    elements = space.scalar.element_dofs
    domain = np.zeros(elements.shape[1], dtype=np.int64) if space.domain is None or len(parts) == 1 else np.asarray(space.domain)
    for index, part in enumerate(parts):
        if part.kind == "conductor":
            out.append(np.unique(elements[:, domain == index]))
    return out


def _projected(space, values) -> "Any":
    import numpy as np

    return np.maximum(np.asarray(space.scalar.project(values)), 0.0)


def _rigid_count(frequencies, expected: int) -> int:
    if len(frequencies) == 0:
        return 0
    first = frequencies[min(expected, len(frequencies) - 1)]
    if expected == 0:
        first = next((f for f in frequencies if f >= RIGID_HZ), frequencies[-1])
    threshold = max(RIGID_HZ, RIGID_FRACTION * float(first))
    return int((frequencies < threshold).sum())


class PiezoAnalysis:
    name: ClassVar[str] = "piezo"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Piezo"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "solve", "electrodes", "fixtures", "loads", "modes", "sweep_Hz", "damping_ratio", "points",
    })
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.DISPLACEMENT, kinds.VOLTAGE, kinds.FREQUENCY)
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold", "mode", "frame")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "potential", "electric_field", "displacement"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "local_refine", "symmetry", "reduce_modes")
    noun: ClassVar[str] = "this voltage"
    governing_word: ClassVar[str] = "peak stress"

    def __init__(self):
        self._solve = "static"

    @property
    def fields(self) -> tuple[FieldSpec, ...]:
        """The fields the study last parsed writes (its view is checked against them)."""
        return _FIELD_SPECS[self._solve]

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> PiezoInputs:
        inputs = parse_document(document)
        self._solve = inputs.solve
        return inputs

    # -- the ladder ----------------------------------------------------------------------------------

    def _modes_wanted(self, ctx, inputs: PiezoInputs) -> int:
        planned = getattr(getattr(ctx, "plan", None), "modes", None)
        return max(planned or inputs.modes, 1)

    def estimate(self, ctx: SolveContext, inputs: PiezoInputs):
        """Four unknowns per node (three displacements and the voltage). Static: one coupled factorisation (or
        MINRES); resonance: two (shorted and open) and their Lanczos; harmonic: one per frequency, or one and the
        modes when the sweep goes by modes."""
        from cadgen._internal.fea import fit

        plan = ctx.plan
        elements, nodes, two = fit.plan_counts(ctx)
        n = max(int(4 * nodes), 1)
        build = fit.BYTES_PER_ELEMENT[plan.order] * (4.0 / 3.0) * elements
        matrix = 12.0 * fit.NNZ_PER_ROW[plan.order] * (4.0 / 3.0) * n
        assemble = fit.SECONDS_PER_ELEMENT[plan.order] * 2.0 * elements
        factor_bytes = 16.0 * fit.FILL * n ** 1.5
        factor_seconds = fit.DIRECT_SECONDS * n ** 2
        if inputs.solve == "static" and plan.solver != "direct":
            memory, seconds = build + matrix * (1.0 + fit.AMG_COPIES), assemble + 3.0 * fit.AMG_SECONDS_PER_DOF * n
        elif inputs.solve == "static":
            memory, seconds = build + 2.0 * matrix + factor_bytes, assemble + factor_seconds
        elif inputs.solve == "resonance":
            vectors = 2 * self._modes_wanted(ctx, inputs) + 26
            memory = build + 2.0 * matrix + factor_bytes + 8.0 * vectors * n
            seconds = assemble + 2.0 * (factor_seconds + 3 * vectors * 4.0 * fit.FILL * n ** 1.5 * 1e-9)
        else:
            low, high = inputs.sweep_Hz or (1.0, 10.0)
            solves = inputs.points + 13 * self._modes_wanted(ctx, inputs) + 24
            memory = build + 2.0 * matrix + 2.0 * factor_bytes
            if plan.modes is not None:
                vectors = 2 * self._modes_wanted(ctx, inputs) + 20
                memory += 8.0 * vectors * n
                seconds = assemble + 2.0 * factor_seconds + 3 * vectors * 4.0 * fit.FILL * n ** 1.5 * 1e-9 + solves * n * 1e-7
            else:
                seconds = assemble + factor_seconds + 4.0 * solves * factor_seconds
            del low, high
        if two:
            seconds *= 2.0
        return fit.Estimate(n, int(fit.BASE_BYTES + memory), float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: PiezoInputs):
        from cadgen._internal.fea import fit

        plan = ctx.plan
        if rung == "iterative":
            if inputs.solve != "static" or plan.solver != "direct":
                return None
            before = self.estimate(ctx, inputs)
            plan.solver = "iterative"
            after = self.estimate(ctx, inputs)
            if after.memory_bytes >= before.memory_bytes and after.seconds >= 0.95 * before.seconds:
                plan.solver = "direct"
                return None
            why = "fit in memory" if before.memory_bytes > ctx.budget.memory_bytes else "finish sooner"
            return fit.Step("iterative", f"Solved the coupled system with an iterative solver (MINRES with multigrid) to {why}",
                            None, None, detail={"solver": "minres", "from_bytes": before.memory_bytes,
                                                "to_bytes": after.memory_bytes})
        if rung == "reduce_modes":
            if inputs.solve == "resonance":
                current = self._modes_wanted(ctx, inputs)
                if current <= 1:
                    return None
                fewer = max(1, current // 2)
                plan.modes = fewer
                return fit.Step("reduce_modes", f"Found the first {fewer} of the {inputs.modes} modes asked for, to fit",
                                None, None, detail={"from_modes": inputs.modes, "to_modes": fewer})
            if inputs.solve == "harmonic" and plan.modes is None:
                plan.modes = max(inputs.modes, 6)
                return fit.Step("reduce_modes", f"Swept by its first {plan.modes} modes with a static correction instead of "
                                "solving every frequency in full, to fit",
                                "exact below the highest mode kept; above it the response reads a little low", None,
                                detail={"modes": plan.modes, "method": "modes"})
            return None
        if rung == "symmetry" and inputs.solve == "resonance":
            return None  # a symmetric half would miss the antisymmetric modes
        if rung in ("iterative", "local_refine", "symmetry"):
            return fit.apply_generic(rung, self, ctx, inputs)
        return None

    def symmetric_about(self, plane, inputs: PiezoInputs, ctx: SolveContext) -> bool:
        """One part, every electrode, fixture, load and check face its own mirror image, no force across the plane,
        and the ceramic poled along the plane (a mirror across its poling would turn the voltage over)."""
        import numpy as np

        from cadgen._internal.fea import piezo_ops

        if ctx.assembly is not None or inputs.solve == "resonance":
            return False
        axis = plane.component
        for material in ctx.materials or ():
            if material.piezo:
                R = piezo_ops.poling_frame(material.piezo["poling"])
                normal = np.eye(3)[axis]
                if abs(R[2] @ normal) > 1e-9 or not any(abs(abs(R[k] @ normal) - 1.0) < 1e-9 for k in (0, 1)):
                    return False
            elif material.orthotropic:
                from cadgen._internal.fea.materials import mirror_symmetric

                if not mirror_symmetric(material, axis):
                    return False

        def onto_itself(refs) -> bool:
            ordinals = {ctx.ordinal_of[ref] for ref in refs}
            return {plane.mirror.get(o) for o in ordinals} == ordinals

        groups = [e.faces for e in inputs.electrodes] + [f.faces for f in inputs.fixtures] + [load.faces for load in inputs.loads]
        checks = ctx.study.checks if ctx.study is not None else ()
        groups += [tuple(check["faces"]) for check in checks if check.get("faces")]
        if not all(onto_itself(group) for group in groups):
            return False
        for load in inputs.loads:
            if load.type == "force" and abs(load.vector[axis]) > 1e-9 * max(math.sqrt(sum(c * c for c in load.vector)), 1e-300):
                return False
        return True

    def governing(self, result: AnalysisResult):
        values = result.fields["von_mises"]
        if result.scalars.get("solve") == "resonance":
            return values, float(result.scalars["modes"][0]["resonance_Hz"]) if result.scalars["modes"] else 0.0
        return values, float(values.max())

    # -- solve ---------------------------------------------------------------------------------------

    def _planes(self, ctx: SolveContext) -> list:
        plan = ctx.plan
        return list(plan.prepared.planes) if plan is not None and plan.prepared is not None else []

    def _supports(self, ctx: SolveContext, inputs: PiezoInputs, planes):
        from cadgen._internal.fea.supports import supports_of

        space = ctx.space
        held = []
        for plane in planes:
            dofs = space.basis.get_dofs(space.facets_of_ordinals([plane.ordinal], "a symmetry plane")).all()
            held.append(dofs[space.component[dofs] == plane.component])
        return supports_of(space, inputs.fixtures, ctx.ordinal_of, held=held)

    def _electrodes(self, ctx, inputs: PiezoInputs, state: str):
        """The electrodes as the solve holds them: ``as_given``; ``short`` (every one at 0 V); ``open`` (0 V ones held,
        every other floating)."""
        from cadgen._internal.fea import piezo_ops

        out = []
        for e in inputs.electrodes:
            dofs = _face_dofs(ctx.space, e.faces, ctx.ordinal_of, f"electrodes[{e.name}]")
            volts = e.volts if state == "as_given" else 0.0 if state == "short" else (0.0 if e.volts == 0 else None)
            out.append(piezo_ops.Electrode(e.name, dofs, volts))
        return out

    def solve(self, ctx: SolveContext, inputs: PiezoInputs) -> AnalysisResult:
        import time

        from cadgen._internal.fea import piezo_ops

        started = time.perf_counter()
        space = ctx.space
        parts = _part_constants(ctx.materials)
        if not any(p.kind == "piezo" for p in parts):
            raise ValueError("material: a piezo study needs a piezo ceramic in at least one part (\"pzt-4\", \"pzt-5a\", "
                             "\"pzt-5h\", or a material with a piezo block)")
        matrices = piezo_ops.assemble(space, parts)
        timings = {"assemble_s": time.perf_counter() - started}
        planes = self._planes(ctx)
        supports = self._supports(ctx, inputs, planes)
        if inputs.solve != "resonance":
            from cadgen._internal.fea.supports import not_held_sentence, unheld_motions

            if supports.rollers and (loose := unheld_motions(space, supports)):
                raise ValueError(not_held_sentence(loose))
        conductors = _conductor_dofs(space, parts)
        if ctx.log:
            ctx.log(f"piezo {inputs.solve}: {space.dofs} displacement and {space.scalar.N} voltage DOF")
        if inputs.solve == "static":
            result = self._static(ctx, inputs, parts, matrices, supports, conductors, planes)
        elif inputs.solve == "resonance":
            result = self._resonance(ctx, inputs, parts, matrices, supports, conductors)
        else:
            result = self._harmonic(ctx, inputs, parts, matrices, supports, conductors, planes)
        result.timings = {**timings, **result.timings, "piezo_s": time.perf_counter() - started}
        result.scalars["solve"] = inputs.solve
        result.scalars["analysis_extras"] = {"solve": inputs.solve}
        result.scalars["poling"] = self._poling(ctx)
        inputs.resolved["poling"] = result.scalars["poling"]
        if planes:
            self._unfold(ctx, result, planes)
        return result

    def _poling(self, ctx) -> list[dict]:
        names = list(ctx.assembly.names) if ctx.assembly is not None else [ctx.part_name or "the part"]
        return [{"part": name, "material": m.name, "direction": [round(c, 6) + 0.0 for c in m.piezo["poling"]]}
                for name, m in zip(names, ctx.materials) if m.piezo]

    def _base(self, space, **kwargs) -> AnalysisResult:
        return AnalysisResult(dof_locations=space.dof_locations, vertices=space.vertices, tets=space.tets,
                              boundary_quadratic=space.boundary_quadratic, element_dofs=space.element_dofs, **kwargs)

    def _fields(self, space, parts, u, phi):
        """(displacement nodal, von Mises nodal MPa, |E| nodal kV/mm) of a real answer."""
        from cadgen._internal.fea import piezo_ops

        vm_q, e_q = piezo_ops.field_recovery(space, parts, u, phi)
        return space.nodal(u), _projected(space, vm_q), _projected(space, e_q) / 1000.0

    def _electrode_records(self, inputs: PiezoInputs, response, share: float) -> list[dict]:
        out = []
        for spec, charge, volts in zip(inputs.electrodes, response.charges, response.volts):
            out.append({"name": spec.name, "open": spec.volts is None,
                        "V": float(volts.real if isinstance(volts, complex) else volts),
                        "charge_C": float(charge) * 1e-3 / share})
        return out

    def _static(self, ctx, inputs: PiezoInputs, parts, matrices, supports, conductors, planes) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import piezo_ops

        space = ctx.space
        share = 0.5 ** len(planes)
        system = piezo_ops.System(space, matrices, supports, self._electrodes(ctx, inputs, "as_given"), conductors)
        f = piezo_ops.surface_loads(space, inputs.loads, ctx.ordinal_of, share)
        started = time.perf_counter()
        warnings: list[str] = []
        response, how = system.solve_static(f, iterative=ctx.plan is not None and ctx.plan.solver != "direct", warnings=warnings)
        solve_s = time.perf_counter() - started
        displacement, vm, strength = self._fields(space, parts, response.u, response.phi)
        records = self._electrode_records(inputs, response, share)
        # Each electrode's mean displacement (an actuator's stroke): over its nodes; across a symmetry plane it is zero.
        for record, electrode in zip(records, system_electrodes := self._electrodes(ctx, inputs, "as_given")):
            mean = displacement[electrode.dofs].mean(axis=0)
            for plane in planes:
                mean[plane.component] = 0.0
            record["mean_displacement_mm"] = [float(c) for c in mean]
        del system_electrodes
        capacitance = None
        held = [r for r, spec in zip(records, inputs.electrodes) if spec.volts is not None]
        if not inputs.loads and len({r["V"] for r in held}) >= 2:
            hot = max(held, key=lambda r: r["V"])
            cold = min(held, key=lambda r: r["V"])
            capacitance = {"between": [hot["name"], cold["name"]], "F": hot["charge_C"] / (hot["V"] - cold["V"])}
        applied = tuple(float(f[space.component == c].sum()) / share for c in range(3))
        return self._base(
            space, fields={"von_mises": vm, "potential": np.asarray(response.phi, dtype=float), "electric_field": strength,
                           "displacement": displacement},
            deformation=displacement,
            scalars={"electrodes": records, "capacitance": capacitance, "share": share,
                     "analysis_warnings": list(warnings)},
            reactions=list(response.reactions), applied=applied,   # the symmetric part's reactions unfold with its fields
            dofs=int(space.dofs + space.scalar.N), solver=how, timings={"solve_s": solve_s}, warnings=warnings,
        )

    def _modes_of(self, system, wanted: int, expected_rigid: int):
        import numpy as np

        values, vectors, how = system.modes(wanted + expected_rigid)
        frequencies = np.sqrt(np.maximum(values, 0.0)) / _TWO_PI
        rigid = _rigid_count(frequencies, expected_rigid)
        return frequencies[rigid:], vectors[:, rigid:], rigid, how

    def _resonance(self, ctx, inputs: PiezoInputs, parts, matrices, supports, conductors) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import piezo_ops
        from cadgen._internal.fea.analyses.modal import floating_bodies, max_frames, mode_series
        from cadgen._internal.fea.supports import unheld_motions

        space = ctx.space
        warnings: list[str] = []
        body = floating_bodies(space, inputs.fixtures, ctx.ordinal_of)
        floating = int(body.max()) + 1 if len(body) else 0
        loose = unheld_motions(space, supports) if supports.rollers and floating == 0 else 0
        expected = 6 * floating + loose
        wanted = self._modes_wanted(ctx, inputs)
        started = time.perf_counter()
        short = piezo_ops.System(space, matrices, supports, self._electrodes(ctx, inputs, "short"), conductors)
        opened = piezo_ops.System(space, matrices, supports, self._electrodes(ctx, inputs, "open"), conductors)
        fr, ys, rigid, how = self._modes_of(short, wanted, expected)
        fa, yo, _, _ = self._modes_of(opened, wanted + 2, expected)
        eigen_s = time.perf_counter() - started
        fr, ys = fr[:wanted], ys[:, :wanted]
        pairs = piezo_ops.pair_modes(ys[:short.m_u], yo[:opened.m_u], short.Mr)
        modes = []
        for i, j in enumerate(pairs):
            f_r = float(fr[i])
            f_a = float(fa[j]) if j >= 0 else f_r
            k2 = max((f_a ** 2 - f_r ** 2) / f_a ** 2, 0.0) if f_a > 0 else 0.0
            modes.append({"mode": i + 1, "resonance_Hz": f_r, "antiresonance_Hz": f_a, "k_eff2": k2, "k_eff": math.sqrt(k2)})
        # Each mode's shape, its stress and voltage with the shape scaled to a largest motion of 1 mm.
        frames = min(len(modes), max_frames(ctx))
        shapes, stresses, potentials = [], [], []
        for i in range(frames):
            u, phi = short.expand(ys[:, i])
            disp, vm, _ = self._fields(space, parts, u, phi)
            size = float(np.linalg.norm(disp, axis=1).max()) or 1.0
            flat = disp.ravel()
            sign = 1.0 if flat[int(np.abs(flat).argmax())] >= 0 else -1.0
            shapes.append(disp * sign / size)
            stresses.append(vm / size)
            potentials.append(np.asarray(phi) * sign / size)
        held = [e for e in inputs.electrodes if e.volts != 0]
        blocked = piezo_ops.System(space, matrices, supports, [
            piezo_ops.Electrode(e.name, d.dofs, 0.0 if e.volts == 0 else (1.0 if e in held[:1] else None))
            for e, d in zip(inputs.electrodes, self._electrodes(ctx, inputs, "short"))], conductors)
        charges = blocked.blocked_charges()
        hot = inputs.electrodes.index(held[0])
        c0 = float(charges[hot]) * 1e-3   # 1 V on the first driven electrode
        if frames < len(modes):
            warnings.append(f"wrote the shapes of the first {frames} of {len(modes)} modes; every mode's frequencies are "
                            "in the summary")
        series = mode_series([m["resonance_Hz"] for m in modes], hertz_text, "Hz", frames)
        for n, frame in enumerate(series.frames):
            frame.attributes.update({"von_mises": "_VON_MISES" if n == 0 else f"_VON_MISES_F{n}",
                                     "potential": "_POTENTIAL" if n == 0 else f"_POTENTIAL_F{n}"})
        return self._base(
            space, fields={"mode_shape": shapes[0], "von_mises": stresses[0], "potential": potentials[0]},
            deformation=shapes[0], series=series,
            frame_fields={"mode_shape": shapes, "von_mises": stresses, "potential": potentials},
            scalars={"modes": modes, "rigid_body_modes": rigid, "blocked_capacitance": {"electrode": held[0].name, "F": c0},
                     "analysis_warnings": list(warnings)},
            dofs=int(space.dofs + space.scalar.N), solver=how, timings={"eigen_s": eigen_s}, warnings=warnings,
        )

    def _harmonic(self, ctx, inputs: PiezoInputs, parts, matrices, supports, conductors, planes) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import piezo_ops
        from cadgen._internal.fea.analyses.harmonic import choose_frames, sweep_grid
        from cadgen._internal.fea.analyses.modal import max_frames

        space = ctx.space
        share = 0.5 ** len(planes)
        warnings: list[str] = []
        system = piezo_ops.System(space, matrices, supports, self._electrodes(ctx, inputs, "as_given"), conductors)
        low, high = inputs.sweep_Hz
        zeta = inputs.damping_ratio
        loss = 2.0 * zeta
        modal = ctx.plan is not None and ctx.plan.modes is not None
        wanted = self._modes_wanted(ctx, inputs)
        started = time.perf_counter()
        values, vectors, how = system.modes(wanted)
        found_Hz = np.sqrt(np.maximum(values, 0.0)) / _TWO_PI
        eigen_s = time.perf_counter() - started
        if modal and found_Hz[-1] < high:
            warnings.append(f"the {len(found_Hz)} modes kept reach {hertz_text(float(found_Hz[-1]))}, below the sweep's top "
                            f"({hertz_text(high)}); the response above them is the static correction's")
        grid = sweep_grid(low, high, [f for f in found_Hz if low <= f <= high], zeta, inputs.points)
        omegas = _TWO_PI * grid
        f = piezo_ops.surface_loads(space, inputs.loads, ctx.ordinal_of, share)
        b = system.rhs(f)

        def answers(omega_list):
            if modal:
                return system.sweep_modal(b, omega_list, loss, values, vectors)
            return system.sweep_direct(b, omega_list, loss)

        started = time.perf_counter()
        driven = [k for k, e in enumerate(inputs.electrodes) if e.volts]
        hot = max(driven, key=lambda k: abs(inputs.electrodes[k].volts)) if driven else None
        opened = [k for k, e in enumerate(inputs.electrodes) if e.volts is None]
        curve_disp, curve_current, curve_admittance, curve_open = [], [], [], {k: [] for k in opened}
        for omega, y in zip(omegas, answers(omegas)):
            response = system.response(y)
            u = space.nodal(response.u)
            curve_disp.append(float(np.sqrt((np.abs(u) ** 2).sum(axis=1)).max()))
            if hot is not None:
                current = omega * abs(response.charges[hot]) * 1e-3 / share   # A
                curve_current.append(current)
                curve_admittance.append(current / abs(inputs.electrodes[hot].volts))
            for k in opened:
                curve_open[k].append(abs(response.volts[k]))
        sweep_s = time.perf_counter() - started
        curve_disp = np.asarray(curve_disp)
        indices, peaks = choose_frames(grid, curve_disp, max_frames(ctx), zeta)
        frame_Hz = [float(grid[i]) for i in indices]
        re, im, vm, pot = [], [], [], []
        for y in answers(_TWO_PI * np.asarray(frame_Hz)):
            u, phi = system.expand(y)
            re.append(space.nodal(u.real))
            im.append(space.nodal(u.imag))
            peak = None
            for k in range(PHASES):
                turn = np.exp(1j * math.pi * k / PHASES)
                vm_q, _ = piezo_ops.field_recovery(space, parts, (u * turn).real, (phi * turn).real)
                peak = vm_q if peak is None else np.maximum(peak, vm_q)
            vm.append(_projected(space, peak))
            pot.append(np.abs(phi))
        stress_max = [float(v.max()) for v in vm]
        default = int(np.argmax([float(np.linalg.norm(r + 1j * i, axis=1).max()) for r, i in zip(re, im)]))
        series = Series(kind="frequency", unit="Hz", default=default, frames=[
            SeriesFrame(value=round(fz, 6), label=hertz_text(fz), attributes={
                "von_mises": "_VON_MISES" if n == 0 else f"_VON_MISES_F{n}",
                "potential": "_POTENTIAL" if n == 0 else f"_POTENTIAL_F{n}",
                "displacement": "_DISPLACEMENT" if n == 0 else f"_DISPLACEMENT_F{n}",
                "displacement_im": f"_DISPLACEMENT_IM_F{n}",
            }) for n, fz in enumerate(frame_Hz)])
        x = [round(float(v), 6) for v in grid]
        curves = {"max_displacement_mm": {"x": x, "x_unit": "Hz", "y": [round(v, 9) for v in curve_disp.tolist()], "y_unit": "mm"}}
        if hot is not None:
            curves["current_mA"] = {"x": x, "x_unit": "Hz", "y": [round(v * 1e3, 9) for v in curve_current], "y_unit": "mA"}
            curves["admittance_S"] = {"x": x, "x_unit": "Hz", "y": [float(f"{v:.6g}") for v in curve_admittance], "y_unit": "S"}
        for k in opened:
            curves[f"voltage_V:{inputs.electrodes[k].name}"] = {"x": x, "x_unit": "Hz", "y": [round(v, 9) for v in curve_open[k]],
                                                               "y_unit": "V"}
        peak_index = int(np.argmax(curve_disp))
        return self._base(
            space, fields={"von_mises": vm[0], "potential": pot[0], "displacement": re[0]}, deformation=re[0], series=series,
            frame_fields={"von_mises": vm, "potential": pot, "displacement": re, "displacement_im": im}, curves=curves,
            scalars={"modes_Hz": [float(v) for v in found_Hz], "grid_Hz": grid, "frame_Hz": frame_Hz,
                     "stress_max": stress_max, "peak": {"frequency_Hz": float(grid[peak_index]),
                                                        "displacement_mm": float(curve_disp[peak_index])},
                     "hot": None if hot is None else inputs.electrodes[hot].name,
                     "curve_current": curve_current, "curve_admittance": curve_admittance,
                     "curve_open": {inputs.electrodes[k].name: curve_open[k] for k in opened},
                     "method": "modes" if modal else "direct", "share": share, "peaks": [int(p) for p in peaks],
                     "analysis_warnings": list(warnings)},
            dofs=int(space.dofs + space.scalar.N), solver=("modes + static correction; " if modal else "direct sweep; ") + how,
            timings={"eigen_s": eigen_s, "sweep_s": sweep_s}, warnings=warnings,
        )

    def _unfold(self, ctx: SolveContext, result: AnalysisResult, planes) -> None:
        """The solved half (or quarter) mirrored into the whole part, every field and frame with it."""
        import numpy as np

        from cadgen._internal.fea import symmetry

        volume = ctx.volume
        vectors_named = {"displacement", "displacement_im", "mode_shape"}
        for plane in reversed(planes):
            whole, keep = symmetry.unfold_volume(volume, plane)
            scalars, vectors = {}, {}
            for name, values in result.fields.items():
                (vectors if name in vectors_named else scalars)[f"f:{name}"] = np.asarray(values)
            for name, frames in result.frame_fields.items():
                for i, values in enumerate(frames):
                    (vectors if name in vectors_named else scalars)[f"{name}:{i}"] = np.asarray(values)
            if result.deformation is not None:
                vectors["deformation"] = np.asarray(result.deformation)
            locations, s_out, v_out, boundary, tets, elements, vertices = symmetry.unfold_fields(
                plane, result.vertices, result.dof_locations, keep, scalars=scalars, vectors=vectors,
                boundary=result.boundary_quadratic, tets=result.tets, element_dofs=result.element_dofs,
            )
            merged = {**s_out, **v_out}
            result.fields = {name: merged[f"f:{name}"] for name in result.fields}
            result.frame_fields = {name: [merged[f"{name}:{i}"] for i in range(len(frames))]
                                   for name, frames in result.frame_fields.items()}
            if result.deformation is not None:
                result.deformation = merged["deformation"]
            result.reactions = [symmetry.unfold_force(plane, r) for r in result.reactions]
            result.dof_locations, result.boundary_quadratic = locations, boundary
            result.tets, result.element_dofs, result.vertices = tets, elements, vertices
            volume = whole
        ctx.volume = volume

    def needs_finer(self, result: AnalysisResult, inputs: PiezoInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: PiezoInputs) -> dict:
        import numpy as np

        from cadgen._internal.fea import checks

        kind = check["kind"]
        label = check.get("label") or kinds.CHECK_SPECS[kind].default_label
        if kind == "frequency":
            return self._frequency(check, label, result)
        if kind == "voltage":
            name = check.get("electrode") or inputs.open[0].name
            if result.scalars["solve"] == "static":
                value = abs(next(r["V"] for r in result.scalars["electrodes"] if r["name"] == name))
                at = None
            else:
                curve = result.scalars["curve_open"][name]
                worst = int(np.argmax(curve))
                hz = float(result.scalars["grid_Hz"][worst])
                frame = min(range(len(result.scalars["frame_Hz"])), key=lambda k: abs(result.scalars["frame_Hz"][k] - hz))
                value, at = float(curve[worst]), {"frame": frame, "value": round(hz, 6), "unit": "Hz"}
            ratio = check["min_V"] / value if value > 0 else math.inf
            out = {"kind": "voltage", "label": label, "value": round(value, 6), "limit": check["min_V"], "unit": "V",
                   "ratio": round(ratio, 6) if math.isfinite(ratio) else 1e9, "close_at": CLOSE_AT,
                   "status": checks.check_status(ratio, CLOSE_AT), "where": {"ref": None, "at": [0.0, 0.0, 0.0]},
                   "electrode": name}
            electrode = next(e for e in inputs.electrodes if e.name == name)
            face = ctx.volume.faces[ctx.ordinal_of[electrode.faces[0]]]
            out["where"] = {"ref": face.ref, "at": [round(float(c), 3) for c in face.center]}
            if at is not None:
                out["at"] = at
            return out
        frame = 0
        if result.series is not None and result.scalars.get("solve") == "harmonic":
            stress_max = result.scalars["stress_max"]
            frame = int(np.argmax(stress_max)) if kind == "stress" else result.series.default
        if kind == "stress":
            values = result.frame_fields["von_mises"][frame] if result.frame_fields else result.fields["von_mises"]
            peak = kinds.field_max_over(values, (), boundary=result.boundary_quadratic,
                                        boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations,
                                        face_ref=ctx.volume.faces, ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]")
            material = ctx.study.material if ctx.study is not None and ctx.study.material is not None else ctx.materials[0]
            limit = material.yield_strength
            margin = ctx.study.margin if ctx.study is not None else 2.0
            ratio = peak.value / limit
            out = {"kind": "stress", "label": label, "value": round(peak.value, 4), "limit": limit, "unit": "MPa",
                   "ratio": round(ratio, 6), "close_at": round(1 / margin, 6), "margin": margin,
                   "status": "fails" if ratio > 1 else "close" if ratio > 1 / margin else "passes",
                   "where": {"ref": peak.ref, "at": [round(c, 3) for c in peak.at]}}
        else:
            vectors = result.frame_fields["displacement"][frame] if result.frame_fields else result.fields["displacement"]
            if result.frame_fields:
                vectors = vectors + 1j * result.frame_fields["displacement_im"][frame]
            magnitude = np.sqrt((np.abs(vectors) ** 2).sum(axis=1))
            refs = tuple(check.get("faces", ()))
            peak = kinds.field_max_over(magnitude, refs, boundary=result.boundary_quadratic,
                                        boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations,
                                        face_ref=ctx.volume.faces, ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]")
            out = checks.displacement_check(peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces, label=label)
        if result.series is not None and result.scalars.get("solve") == "harmonic":
            frame_value = result.series.frames[frame].value
            out["at"] = {"frame": frame, "value": frame_value, "unit": "Hz"}
        return out

    def _frequency(self, check: dict, label: str, result: AnalysisResult) -> dict:
        from cadgen._internal.fea import checks

        frequencies = [m["resonance_Hz"] for m in result.scalars["modes"]]
        if "avoid_Hz" in check:
            low, high = check["avoid_Hz"]
            nearest = min(range(len(frequencies)), key=lambda i: 0 if low <= frequencies[i] <= high else
                          min(abs(frequencies[i] - low), abs(frequencies[i] - high)))
            f = frequencies[nearest]
            inside = low <= f <= high
            gap = 0.0 if inside else min(abs(f - low) / low, abs(f - high) / high)
            status = "fails" if inside else "close" if gap < 0.1 else "passes"
            ratio = 1.0 if inside else max(0.0, 1.0 - gap)
            return {"kind": "frequency", "label": label, "value": round(f, 4), "limit": low if f < low else high, "unit": "Hz",
                    "ratio": round(ratio, 6), "close_at": CLOSE_AT, "status": status, "band": [low, high],
                    "mode": nearest + 1, "where": {"ref": None, "at": [0.0, 0.0, 0.0]},
                    "at": {"frame": nearest, "value": round(f, 4), "unit": "Hz"}}
        mode = check.get("mode", 1)
        if mode > len(frequencies):
            raise ValueError(f"view.checks: a frequency check names mode {mode}, but only {len(frequencies)} modes were found; "
                             "raise modes")
        f = frequencies[mode - 1]
        ratio = check["min_Hz"] / f if f > 0 else math.inf
        return {"kind": "frequency", "label": label, "value": round(f, 4), "limit": check["min_Hz"], "unit": "Hz",
                "ratio": round(ratio, 6), "close_at": CLOSE_AT, "status": checks.check_status(ratio, CLOSE_AT), "mode": mode,
                "where": {"ref": None, "at": [0.0, 0.0, 0.0]}, "at": {"frame": mode - 1, "value": round(f, 4), "unit": "Hz"}}

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: PiezoInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        scalars = result.scalars
        found = []

        def finding(severity, kind, summary, description, items=()):
            return {"check": "fea", "severity": severity, "type": kind, "summary": summary, "description": description,
                    "items": list(items)}

        if inputs.solve == "static":
            capacitance = scalars["capacitance"]
            if capacitance:
                found.append(finding("info", "piezo_capacitance",
                                     f"Capacitance {farads_text(capacitance['F'])} between {capacitance['between'][0]} and "
                                     f"{capacitance['between'][1]}", "the charge on the driven electrode over the voltage "
                                     "across, with the part free to move as its fixtures allow"))
            for record in scalars["electrodes"]:
                if record["open"]:
                    found.append(finding("info", "piezo_open_voltage", f"Open electrode {record['name']} reads "
                                         f"{record['V']:.4g} V", "an open electrode floats: one voltage, no net charge"))
            peak = float(result.fields["electric_field"].max())
            if peak > 0.35:
                found.append(finding("warning", "piezo_high_field", f"The field reaches {peak:.3g} kV/mm",
                                     "soft PZT starts to depolarise near its coercive field, about 1 kV/mm (PZT-5A 1.2, "
                                     "PZT-5H 0.65 per TP-226); past a third of it the linear model is optimistic"))
        elif inputs.solve == "resonance":
            for mode in scalars["modes"][:3]:
                found.append(finding("info", "piezo_mode",
                                     f"Mode {mode['mode']}: resonance {hertz_text(mode['resonance_Hz'])}, anti-resonance "
                                     f"{hertz_text(mode['antiresonance_Hz'])}, k_eff {mode['k_eff']:.3f}",
                                     "resonance with the electrodes shorted, anti-resonance with them open; "
                                     "k_eff² = (fa² - fr²) / fa²"))
            if scalars["rigid_body_modes"]:
                found.append(finding("info", "rigid_body_modes", f"Free in space: its {scalars['rigid_body_modes']} "
                                     "rigid-body modes were left out", "a mode under 0.5 Hz, or under 1 % of the first "
                                     "elastic mode, is a rigid-body motion"))
        else:
            peak = scalars["peak"]
            found.append(finding("info", "piezo_peak", f"Moves most at {hertz_text(peak['frequency_Hz'])}: "
                                 f"{peak['displacement_mm']:.4g} mm", "the sweep's largest displacement amplitude"))
        return found

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        if requested:
            return requested
        if result.frame_fields.get("mode_shape"):
            return auto_deformation_scale(1.0, bbox_diagonal)
        frames = result.frame_fields.get("displacement") or [result.fields["displacement"]]
        largest = max(float(np.linalg.norm(f, axis=1).max()) for f in frames)
        return auto_deformation_scale(largest, bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: PiezoInputs, check_results: list[dict]) -> dict:
        import numpy as np

        scalars = result.scalars
        out: dict[str, Any] = {"solve": inputs.solve, "poling": scalars["poling"]}
        if inputs.solve == "static":
            magnitude = np.linalg.norm(result.fields["displacement"], axis=1)
            moved = int(magnitude.argmax())
            capacitance = scalars["capacitance"]
            out.update({
                "electrodes": [{**r, "V": round(r["V"], 6), "charge_C": float(f"{r['charge_C']:.6g}"),
                                "mean_displacement_mm": [float(f"{c:.6g}") + 0.0 for c in r["mean_displacement_mm"]]}
                               for r in scalars["electrodes"]],
                "capacitance_F": None if capacitance is None else float(f"{capacitance['F']:.6g}"),
                "capacitance_between": None if capacitance is None else capacitance["between"],
                "max_displacement_mm": round(float(magnitude.max()), 9),
                "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[moved]],
                "max_von_mises_MPa": round(float(result.fields["von_mises"].max()), 4),
                "max_electric_field_kV_mm": round(float(result.fields["electric_field"].max()), 6),
                "potential_range_V": [round(float(result.fields["potential"].min()), 6),
                                      round(float(result.fields["potential"].max()), 6)],
                "applied_force_N": [round(x, 4) for x in result.applied],
                "reaction_force_N": [[round(x, 4) for x in r] for r in result.reactions],
            })
        elif inputs.solve == "resonance":
            out.update({
                "modes": [{"mode": m["mode"], "resonance_Hz": round(m["resonance_Hz"], 4),
                           "antiresonance_Hz": round(m["antiresonance_Hz"], 4), "k_eff": round(m["k_eff"], 6),
                           "k_eff2": round(m["k_eff2"], 6)} for m in scalars["modes"]],
                "first_resonance_Hz": round(scalars["modes"][0]["resonance_Hz"], 4) if scalars["modes"] else None,
                "blocked_capacitance_F": float(f"{scalars['blocked_capacitance']['F']:.6g}"),
                "rigid_body_modes": scalars["rigid_body_modes"],
                "modes_requested": inputs.modes,
            })
        else:
            out.update({
                "sweep_Hz": list(inputs.sweep_Hz), "damping_ratio": inputs.damping_ratio, "method": scalars["method"],
                "modes_Hz": [round(f, 4) for f in scalars["modes_Hz"]],
                "peak_frequency_Hz": round(scalars["peak"]["frequency_Hz"], 4),
                "peak_displacement_mm": round(scalars["peak"]["displacement_mm"], 9),
                "driven_electrode": scalars["hot"],
                "frames": [{"frequency_Hz": round(f, 4), "max_von_mises_MPa": round(s, 4)}
                           for f, s in zip(scalars["frame_Hz"], scalars["stress_max"])],
            })
            if scalars["curve_admittance"]:
                k = int(np.argmax(scalars["curve_admittance"]))
                out["peak_admittance_S"] = float(f"{scalars['curve_admittance'][k]:.6g}")
                out["peak_admittance_Hz"] = round(float(scalars["grid_Hz"][k]), 4)
                out["peak_current_mA"] = round(float(max(scalars["curve_current"])) * 1e3, 6)
            if scalars["curve_open"]:
                out["open_voltage_peak_V"] = {name: round(float(max(v)), 6) for name, v in scalars["curve_open"].items()}
        out["deformation_scale"] = scalars["deformation_scale"]
        out["checks"] = check_results
        return out

    def extras_name(self, stem: str) -> str:
        return f"{stem} piezo"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        out = {}
        for spec in self.fields:
            frames = result.frame_fields.get(spec.name) or [result.fields[spec.name]]
            if spec.components == 3:
                out[spec.name] = (0.0, round(max(float(np.linalg.norm(f, axis=1).max()) for f in frames), 9))
            elif spec.signed:
                out[spec.name] = (round(min(float(f.min()) for f in frames), 6), round(max(float(f.max()) for f in frames), 6))
            else:
                out[spec.name] = (0.0, round(max(float(f.max()) for f in frames), 6))
        return out

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: PiezoInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo: dict[str, Any] = {
            "solve": inputs.solve,
            "electrodes": [{"faces": bare(e.faces), "name": e.name, **({"open": True} if e.volts is None else {"V": e.volts})}
                           for e in inputs.electrodes],
            "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures],
            "loads": [{"type": load.type, "faces": bare(load.faces),
                       **({"vector_N": list(load.vector)} if load.type == "force" else {"pressure_MPa": load.pressure})}
                      for load in inputs.loads],
        }
        if "poling" in inputs.resolved:
            echo["poling"] = [dict(entry) for entry in inputs.resolved["poling"]]
        if inputs.solve == "resonance":
            echo["modes_requested"] = inputs.modes
        if inputs.solve == "harmonic":
            echo.update({"sweep_Hz": list(inputs.sweep_Hz), "damping_ratio": inputs.damping_ratio})
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        lines = [f"piezo {summary['solve']}; poled " + ", ".join(
            f"{p['part']} along {p['direction']}" for p in summary.get("poling", []))]
        if summary["solve"] == "static":
            for e in summary["electrodes"]:
                lines.append(f"electrode {e['name']}: {e['V']:.4g} V{' (open)' if e['open'] else ''}, charge {e['charge_C']:.4g} C")
            if summary.get("capacitance_F") is not None:
                lines.append(f"capacitance {farads_text(summary['capacitance_F'])}")
            lines.append(f"max displacement {summary['max_displacement_mm']:.4g} mm, max von Mises "
                         f"{summary['max_von_mises_MPa']} MPa, max field {summary['max_electric_field_kV_mm']:.4g} kV/mm")
        elif summary["solve"] == "resonance":
            for m in summary["modes"]:
                lines.append(f"mode {m['mode']}: fr {hertz_text(m['resonance_Hz'])}, fa {hertz_text(m['antiresonance_Hz'])}, "
                             f"k_eff {m['k_eff']:.3f}")
            lines.append(f"blocked capacitance {farads_text(summary['blocked_capacitance_F'])}")
        else:
            lines.append(f"sweep {hertz_text(summary['sweep_Hz'][0])} to {hertz_text(summary['sweep_Hz'][1])} "
                         f"({summary['method']}); moves most at {hertz_text(summary['peak_frequency_Hz'])}: "
                         f"{summary['peak_displacement_mm']:.4g} mm")
            if summary.get("peak_admittance_S") is not None:
                lines.append(f"peak admittance {summary['peak_admittance_S']:.4g} S at {hertz_text(summary['peak_admittance_Hz'])}")
        return lines

"""Magnetic / electric (lite): static electric fields, steady (DC) current, static and AC magnetic fields.

The study names a ``mode``:

- ``electrostatic``: faces held at a voltage (``voltages``). A part of a
  conducting material is one voltage throughout (held when any of its faces
  is, floating otherwise); every other part is a dielectric with its relative
  permittivity. ``air`` puts a box of air around the parts (an OCP boolean,
  meshed with them). Fields: the voltage (signed) and the electric field's
  strength (kV/mm). Numbers: the capacitance between two electrodes (named by
  ``capacitance.between``, or the two when there are two), the stored energy,
  each electrode's charge, the strongest field. Check ``electric_field``
  (``limit_kV_mm``: dry air breaks down at about 3).
- ``current``: faces held at a voltage and currents put in through faces
  (``currents``), each part conducting by its resistivity. Fields: the voltage
  and the current density (A/mm²). Numbers: the resistance between the two
  electrodes, each electrode's current and the Joule heat (I² R). With
  ``electro_thermal`` (held temperatures and convection, as a thermal study
  writes them) the Joule heat is put into a steady thermal solve on the same
  mesh, one way: the temperature field and ``temperature`` checks join.
- ``magnetostatic``: coils (``coils``: a part, its turns, its current and its
  axis) in a box of air, each part with its relative permeability, solved for
  the vector potential on lowest-order Nédélec elements. Field: the magnetic
  flux density's strength (mT) on the parts. Numbers: the inductance (one coil),
  the stored energy, the strongest field, the force on each part (J x B on a
  coil, the Maxwell stress on a magnetic part) and the field at ``probes``.
  ``map_to_structure`` hands one part's force to a static solve (spread evenly
  through that part), one way: the stress and displacement checks join.
- ``ac_magnetic``: the same at one frequency (``frequency_Hz``), time-harmonic:
  coils, a conductor fed an AC current through faces on its ends (``currents``,
  its return held at 0 V in ``voltages``) or a uniform field (``applied_field``)
  drive it, and every conducting part carries the eddy currents the changing
  field makes. Solved for the complex vector potential on Nédélec elements and
  the conductors' voltage on P2 elements (the A-phi formulation), the
  conductors' surfaces meshed at half their skin depth. Fields: the eddy
  current density and the magnetic flux density (amplitudes). Numbers: the
  time-averaged loss in each part, the impedance (R and L at the frequency) of
  a lone coil or fed conductor, the skin depth and whether the mesh resolved it.
  With ``electro_thermal`` the loss is put into a steady thermal solve
  (induction heating), one way.

Every mode reports its field at ``probes`` (points in mm). The numbers are in
:mod:`cadgen._internal.fea.em_ops`. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, SolveContext

__all__ = ["AC_LIMITS", "AppliedField", "Coil", "Electrode", "ElectromagneticAnalysis", "ElectromagneticInputs", "LIMITS", "MODES",
           "Probe", "hertz"]

MODES = ("electrostatic", "current", "magnetostatic", "ac_magnetic")
LIMITS = (
    "Static and DC only: no eddy currents, AC or high frequency; linear materials (no saturation, no hysteresis).",
)
AC_LIMITS = (
    "Time-harmonic at one frequency: a sine steady state, no switching transients or harmonics; linear materials "
    "(no saturation, no hysteresis, no permanent magnets); coils are stranded (no eddy currents in their own wire); "
    "no displacement current (not for antennas or waves).",
)
#: The air box reaches this many times the parts' largest extent past them on every side, by default.
AROUND = {"electrostatic": 1.0, "magnetostatic": 1.5, "ac_magnetic": 1.5}
#: A conductor's faces are meshed at its skin depth over this (2: within about 2 % on a round wire's AC resistance).
SKIN_ELEMENTS = 2.0
#: The skin counts as resolved while the surface elements are at most this share of the skin depth.
RESOLVED_AT = 0.55
#: The ladder's ac rungs: no accuracy cost first, then the air, then the skin.
AC_LADDER = ("iterative", "far_field", "local_refine")
#: Out in the air the elements grow to this many times the parts' size, by default; far_field grows it by COARSEN.
FAR, COARSEN = 3.0, 2.5
#: A check is close once its value passes this share of its limit.
CLOSE_AT = 0.9
#: A magnetic part (|mu_r - 1| over this) feels the Maxwell stress; a current-carrying one J x B.
MAGNETIC = 1e-3
#: The cost model of an air region (tetrahedra per mm³ at size h: TETS / h³; Nédélec DOF per tetrahedron).
TETS, EDGES_PER_TET = 4.5, 1.2

FIELD_SPECS = {
    "potential": FieldSpec("potential", "_POTENTIAL", "voltage", "V", signed=True),
    "electric_field": FieldSpec("electric_field", "_ELECTRIC_FIELD", "electric field", "kV/mm"),
    "current_density": FieldSpec("current_density", "_CURRENT_DENSITY", "current density", "A/mm²"),
    "magnetic_field": FieldSpec("magnetic_field", "_MAGNETIC_FIELD", "magnetic flux density", "mT"),
    "eddy_current": FieldSpec("eddy_current", "_EDDY_CURRENT", "eddy current density", "A/mm²"),
    "temperature": FieldSpec("temperature", "_TEMPERATURE", "temperature", "°C", signed=True),
    "von_mises": FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
    "displacement": FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
}
MODE_FIELDS = {
    "electrostatic": ("potential", "electric_field"),
    "current": ("potential", "current_density"),
    "magnetostatic": ("magnetic_field",),
    "ac_magnetic": ("eddy_current", "magnetic_field"),
}
NOUNS = {"electrostatic": "this voltage", "current": "this current", "magnetostatic": "this current", "ac_magnetic": "this current"}


@dataclass(frozen=True)
class Electrode:
    """Faces held at a voltage (``V``) or a current put in through them (``A``, into the part)."""

    faces: tuple[str, ...]
    value: float
    name: str


@dataclass(frozen=True)
class Coil:
    part: str | None
    turns: float
    amps: float
    direction: tuple[float, float, float]
    point: tuple[float, float, float] | None
    name: str


@dataclass(frozen=True)
class AppliedField:
    """A uniform AC field the air box's walls carry (as from a large coil far away): amplitude mT, direction."""

    mT: float
    direction: tuple[float, float, float]


@dataclass(frozen=True)
class Probe:
    at: tuple[float, float, float]
    label: str


@dataclass(frozen=True)
class ElectromagneticInputs(Inputs):
    mode: str = "electrostatic"
    voltages: tuple[Electrode, ...] = ()
    currents: tuple[Electrode, ...] = ()
    coils: tuple[Coil, ...] = ()
    #: How far the air reaches past the parts, mm; ``None`` for no air (electrostatic), 0 for the default.
    air_mm: float | None = None
    probes: tuple[Probe, ...] = ()
    #: The two electrodes a capacitance (electrostatic) or resistance (current) is between, by name.
    between: tuple[str, str] | None = None
    #: electro_thermal: (temperatures, heat, convection) as the thermal analysis parses them, and its reference.
    thermal: tuple | None = None
    reference_C: float | None = None
    #: map_to_structure: the part the force goes on (None: the one feeling the most), its fixtures.
    structure_part: str | None = None
    fixtures: tuple = ()
    material_needs: frozenset[str] = frozenset()
    #: ac_magnetic: the frequency, Hz, and a uniform field the box's walls carry.
    frequency_Hz: float | None = None
    applied: AppliedField | None = None

    @property
    def air(self) -> bool:
        return self.air_mm is not None

    @property
    def electrodes(self) -> tuple[Electrode, ...]:
        return (*self.voltages, *self.currents)

    @property
    def mapped(self) -> bool:
        return bool(self.fixtures)


# -- parse --------------------------------------------------------------------------------------------


def _known(entry: dict, keys: set[str], where: str, words: str) -> None:
    unknown = set(entry) - keys
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; {words}")


def _list(document: dict, key: str, example: str) -> list[dict]:
    raw = document.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"study.{key}: expected a list like [{example}]")
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{key}[{index}]: expected an object like {example}")
    return raw


def _vector(raw: Any, where: str, *, unit: bool = False) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError(f"{where}: expected [x, y, z]")
    vector = tuple(kinds.number(c, where=where) for c in raw)
    if unit and not any(vector):
        raise ValueError(f"{where}: the direction is zero; give the coil's axis, like [0, 0, 1]")
    return vector  # type: ignore[return-value]


def _electrodes(document: dict, key: str, unit: str, example: str, words: str) -> tuple[Electrode, ...]:
    out = []
    for index, entry in enumerate(_list(document, key, example)):
        where = f"{key}[{index}]"
        _known(entry, {"faces", unit, "name"}, where, words)
        if unit not in entry:
            raise ValueError(f"{where}.{unit}: {words}")
        value = kinds.number(entry[unit], where=f"{where}.{unit}")
        name = kinds.text(entry, "name", where=where).get("name") or f"{value:g} {unit}"
        out.append(Electrode(kinds.faces(entry, where=where), value, name))
    names = [e.name for e in out]
    if len(set(names)) != len(names):
        raise ValueError(f"{key}: two entries are named the same ({', '.join(sorted({n for n in names if names.count(n) > 1}))}); "
                         "give each a 'name' of its own")
    return tuple(out)


def _air(document: dict, mode: str) -> float | None:
    raw = document.get("air")
    if raw is None or raw is False:
        return 0.0 if mode in ("magnetostatic", "ac_magnetic") else None
    if raw is True:
        return 0.0
    if not isinstance(raw, dict):
        raise ValueError('air: true, or an object like {"around_mm": 20} (how far the air reaches past the parts)')
    _known(raw, {"around_mm"}, "air", "it takes around_mm, how far the air reaches past the parts on every side")
    return kinds.number(raw["around_mm"], where="air.around_mm", positive=True) if "around_mm" in raw else 0.0


def _probes(document: dict) -> tuple[Probe, ...]:
    out = []
    for index, entry in enumerate(_list(document, "probes", '{"at_mm": [0, 0, 0], "label": "centre"}')):
        where = f"probes[{index}]"
        _known(entry, {"at_mm", "label"}, where, "a probe takes at_mm ([x, y, z]) and a label")
        if "at_mm" not in entry:
            raise ValueError(f"{where}.at_mm: the point to read the field at, [x, y, z] in mm")
        at = _vector(entry["at_mm"], f"{where}.at_mm")
        out.append(Probe(at, kinds.text(entry, "label", where=where).get("label") or f"point {index + 1}"))
    return tuple(out)


def _coils(document: dict) -> tuple[Coil, ...]:
    out = []
    example = '{"part": "coil", "turns": 100, "A": 2, "axis": {"direction": [0, 0, 1]}}'
    for index, entry in enumerate(_list(document, "coils", example)):
        where = f"coils[{index}]"
        _known(entry, {"part", "turns", "A", "axis", "name"}, where,
               "a coil takes part (the winding's solid), turns, A (the current in each turn), axis and name")
        for key, words in (("turns", "the number of turns of wire"), ("A", "the current in each turn, in amperes"),
                           ("axis", 'the axis it winds around: {"direction": [0, 0, 1], "point_mm": [0, 0, 0]}')):
            if key not in entry:
                raise ValueError(f"{where}.{key}: {words}")
        turns = kinds.number(entry["turns"], where=f"{where}.turns", positive=True)
        amps = kinds.number(entry["A"], where=f"{where}.A")
        axis = entry["axis"]
        if not isinstance(axis, dict) or "direction" not in axis:
            raise ValueError(f'{where}.axis: an object like {{"direction": [0, 0, 1], "point_mm": [0, 0, 0]}} '
                             "(point_mm defaults to the coil's centre)")
        _known(axis, {"direction", "point_mm"}, f"{where}.axis", "the axis takes direction and point_mm")
        direction = _vector(axis["direction"], f"{where}.axis.direction", unit=True)
        point = _vector(axis["point_mm"], f"{where}.axis.point_mm") if "point_mm" in axis else None
        part = entry.get("part")
        if part is not None and (not isinstance(part, str) or not part.strip()):
            raise ValueError(f"{where}.part: the coil's part, by its name or ref (\"#o2\")")
        name = kinds.text(entry, "name", where=where).get("name") or f"coil {index + 1}"
        out.append(Coil(part.strip() if part else None, turns, amps, direction, point, name))
    return tuple(out)


def _a(mode: str) -> str:
    return f"{'an' if mode == 'ac_magnetic' else 'a'} {mode}"


def _between(document: dict, electrodes: tuple[Electrode, ...], key: str, what: str) -> tuple[str, str] | None:
    raw = document.get(key)
    if raw is None:
        return (electrodes[0].name, electrodes[1].name) if len(electrodes) == 2 else None
    if not isinstance(raw, dict) or set(raw) != {"between"}:
        raise ValueError(f'{key}: an object like {{"between": ["top", "bottom"]}}, naming two electrodes')
    pair = raw["between"]
    names = [e.name for e in electrodes]
    if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]:
        raise ValueError(f"{key}.between: two different electrode names, from {names}")
    for name in pair:
        if name not in names:
            raise ValueError(f"{key}.between: {kinds.json_text(name)} names no electrode; the {what} are {names}")
    return pair[0], pair[1]


def _electro_thermal(document: dict, needs: set[str]) -> tuple[tuple | None, float | None]:
    """``electro_thermal``: where the Joule heat (DC) or the eddy-current loss (AC) goes, as a thermal study writes it."""
    from cadgen._internal.fea.analyses import thermal as thermal_analysis

    block = document.get("electro_thermal")
    if not isinstance(block, dict):
        raise ValueError('electro_thermal: an object like {"convection": [{"faces": ["#o1.f3"], "h_W_m2K": 10, '
                         '"ambient_C": 25}]}, where the Joule heat goes')
    _known(block, set(thermal_analysis.HEAT_KEYS), "electro_thermal",
           "it takes temperatures, heat and convection, as a thermal study writes them")
    try:
        temperatures, heat, convection = thermal_analysis.parse_heat_keys(block)
    except ValueError as exc:
        raise ValueError(f"electro_thermal.{exc}") from None
    if not temperatures and not convection:
        raise ValueError("electro_thermal: the Joule heat needs somewhere to go: add 'temperatures' (faces held at "
                         "a temperature) or 'convection' (air or liquid carrying it away)")
    reference = thermal_analysis.reference_of(temperatures, convection)
    thermal_analysis.check_limits(document, reference)
    needs.add("conductivity")
    return (temperatures, heat, convection), reference


def _applied(document: dict) -> AppliedField | None:
    raw = document.get("applied_field")
    if raw is None:
        return None
    example = '{"mT": 10, "direction": [1, 0, 0]}'
    if not isinstance(raw, dict):
        raise ValueError(f"applied_field: an object like {example}, a uniform AC field around the parts")
    _known(raw, {"mT", "direction"}, "applied_field", "it takes mT (the field's amplitude) and direction")
    for key, words in (("mT", "the field's amplitude, in millitesla"), ("direction", "the field's direction, like [1, 0, 0]")):
        if key not in raw:
            raise ValueError(f"applied_field.{key}: {words}")
    return AppliedField(kinds.number(raw["mT"], where="applied_field.mT", positive=True),
                        _vector(raw["direction"], "applied_field.direction", unit=True))


def parse_document(document: dict) -> ElectromagneticInputs:
    mode = document.get("mode")
    if mode not in MODES:
        raise ValueError(f"mode: {kinds.json_text(mode)} is not one of {list(MODES)}: electrostatic (voltages, "
                         "capacitance, field strength), current (DC current, resistance, Joule heat), "
                         "magnetostatic (coils, magnetic field, inductance, force) or ac_magnetic (coils or a current "
                         "at a frequency: eddy currents, skin effect, loss, induction heating)")
    allowed = {
        "electrostatic": {"voltages", "air", "probes", "capacitance"},
        "current": {"voltages", "currents", "probes", "resistance", "electro_thermal"},
        "magnetostatic": {"coils", "air", "probes", "map_to_structure"},
        "ac_magnetic": {"frequency_Hz", "coils", "currents", "voltages", "applied_field", "air", "probes", "electro_thermal"},
    }[mode]
    own = {"voltages", "currents", "coils", "air", "probes", "capacitance", "resistance", "electro_thermal", "map_to_structure",
           "frequency_Hz", "applied_field"}
    if stray := sorted((set(document) & own) - allowed):
        raise ValueError(f"study: {', '.join(stray)} {'is' if len(stray) == 1 else 'are'} not for {_a(mode)} study; "
                         f"it takes {', '.join(sorted(allowed))}")
    voltages = _electrodes(document, "voltages", "V", '{"faces": ["#o1.f1"], "V": 1000, "name": "top"}',
                           "a held voltage takes faces, V (volts) and an optional name")
    currents = _electrodes(document, "currents", "A", '{"faces": ["#o1.f2"], "A": 2}',
                           "a current takes faces, A (amperes into the part through them) and an optional name")
    coils = _coils(document)
    names = [e.name for e in (*voltages, *currents)]
    if len(set(names)) != len(names):
        raise ValueError("voltages and currents: two electrodes are named the same; give each a 'name' of its own")
    probes = _probes(document)
    air = _air(document, mode)
    between = None
    thermal = None
    reference = None
    needs: set[str] = set()
    fixtures: tuple = ()
    structure_part = None
    view = document.get("view")
    checks = view.get("checks") if isinstance(view, dict) else None
    check_kinds = [c.get("kind") for c in checks if isinstance(c, dict)] if isinstance(checks, list) else []
    allowed_checks = {"electrostatic": {"electric_field"}, "current": {"temperature"},
                      "magnetostatic": {"stress", "displacement"}, "ac_magnetic": {"temperature"}}[mode]
    for index, kind in enumerate(check_kinds):
        if kind in {"electric_field", "temperature", "stress", "displacement"} and kind not in allowed_checks:
            raise ValueError(f"view.checks[{index}]: a {kind} check is not for {_a(mode)} study"
                             + ("" if allowed_checks else "") + f"; it takes {', '.join(sorted(allowed_checks))}")
    if mode == "electrostatic":
        if not voltages:
            raise ValueError('voltages: an electrostatic study needs faces held at a voltage, like '
                             '[{"faces": ["#o1.f1"], "V": 1000}, {"faces": ["#o1.f2"], "V": 0}]')
        between = _between(document, voltages, "capacitance", "voltages")
    elif mode == "current":
        if not voltages:
            raise ValueError('voltages: a current needs somewhere to leave: hold a face at a voltage, like '
                             '{"faces": ["#o1.f2"], "V": 0} (ground)')
        between = _between(document, (*voltages, *currents), "resistance", "electrodes")
        needs.add("resistivity")
        if document.get("electro_thermal") is not None:
            thermal, reference = _electro_thermal(document, needs)
        elif "temperature" in check_kinds:
            raise ValueError("view.checks: a temperature check needs the Joule heat to go somewhere: add electro_thermal")
    elif mode == "ac_magnetic":
        if "frequency_Hz" not in document:
            raise ValueError("frequency_Hz: an AC study needs its frequency, in hertz, like 50 or 20000")
        frequency = kinds.number(document["frequency_Hz"], where="frequency_Hz", positive=True)
        applied = _applied(document)
        if not coils and not currents and applied is None:
            raise ValueError('coils: an AC study needs a source: a coil ([{"part": "coil", "turns": 10, "A": 2, "axis": '
                             '{"direction": [0, 0, 1]}}]), a current fed through a conductor ("currents", its return in '
                             '"voltages" at 0 V) or a uniform field ("applied_field": {"mT": 10, "direction": [1, 0, 0]})')
        if currents and not voltages:
            raise ValueError('voltages: an AC current needs its return: hold the conductor\'s other end at 0 V, like '
                             '[{"faces": ["#o1.f2"], "V": 0}]')
        for e in voltages:
            if e.value != 0:
                raise ValueError(f"voltages[{e.name}]: an AC study is driven by its current; hold the return at 0 V "
                                 "and give the current in 'currents'")
        if voltages and not currents:
            raise ValueError("voltages: an AC study holds a face at 0 V only as the return of a current; add 'currents'")
        needs.update({"permeability", "resistivity"})
        if document.get("electro_thermal") is not None:
            thermal, reference = _electro_thermal(document, needs)
        elif "temperature" in check_kinds:
            raise ValueError("view.checks: a temperature check needs the loss to go somewhere: add electro_thermal")
    else:
        if not coils:
            raise ValueError('coils: a magnetostatic study needs a source: a coil, like [{"part": "coil", "turns": 100, '
                             '"A": 2, "axis": {"direction": [0, 0, 1]}}]')
        needs.add("permeability")
        if (mapping := document.get("map_to_structure")) is not None:
            from cadgen._internal.fea.study import parse_fixtures

            if not isinstance(mapping, dict):
                raise ValueError('map_to_structure: an object like {"part": "armature", "fixtures": [{"faces": ["#o2.f1"]}]}')
            _known(mapping, {"part", "fixtures"}, "map_to_structure",
                   "it takes the part the magnetic force acts on and the fixtures that hold the parts")
            try:
                fixtures = parse_fixtures(mapping)
            except ValueError as exc:
                raise ValueError(f"map_to_structure.{exc}") from None
            part = mapping.get("part")
            if part is not None and (not isinstance(part, str) or not part.strip()):
                raise ValueError("map_to_structure.part: the part the force acts on, by its name or ref")
            structure_part = part.strip() if part else None
            needs.update({"E", "nu"})
        elif any(kind in ("stress", "displacement") for kind in check_kinds):
            raise ValueError("view.checks: a stress or displacement check needs the magnetic force on a part: add "
                             "map_to_structure with its fixtures")
    if mode != "ac_magnetic":
        frequency = applied = None
    refs = [ref for group in (*voltages, *currents) for ref in group.faces]
    if thermal is not None:
        refs += [ref for group in (*thermal[0], *thermal[1], *thermal[2]) for ref in group.faces]
    refs += [ref for fixture in fixtures for ref in fixture.faces]
    refs_t = tuple(dict.fromkeys(refs))
    anchors = tuple(dict.fromkeys(ref for group in voltages for ref in group.faces))
    return ElectromagneticInputs(
        refs_t, anchors, False, mode=mode, voltages=voltages, currents=currents, coils=coils, air_mm=air,
        probes=probes, between=between, thermal=thermal, reference_C=reference, structure_part=structure_part,
        fixtures=fixtures, material_needs=frozenset(needs), frequency_Hz=frequency, applied=applied,
    )


# -- the parts of a study ---------------------------------------------------------------------------------


@dataclass
class _Parts:
    names: list[str]
    refs: list[str]
    shapes: list
    materials: list
    #: Study face ref -> (part index, the part's face ordinal), and that face's ordinal in the run's mesh.
    face_of: dict[str, tuple[int, int]]
    mesh_ordinal: dict[tuple[int, int], int]


def _parts(ctx: SolveContext, refs) -> _Parts:
    if ctx.assembly is None:
        geometry = ctx.geometry
        face_of = {ref: (0, ctx.ordinal_of[ref]) for ref in refs}
        mesh_ordinal = {(0, k): k for k in (ctx.volume.faces if ctx.volume is not None else {})}
        return _Parts([ctx.part_name or "the part"], [getattr(geometry, "occurrence_ref", "")],
                      [getattr(geometry, "shape", None)], list(ctx.materials), face_of, mesh_ordinal)
    from cadgen._internal.fea.assembly import part_faces

    plan = ctx.assembly
    positions: list[tuple[int, int]] = []
    for i, part in enumerate(plan.parts):
        positions += [(i, k) for k in range(1, len(part_faces(part.shape)) + 1)]
    face_of = {ref: positions[ctx.ordinal_of[ref] - 1] for ref in refs}
    mesh_ordinal = {key: n for n, key in enumerate(positions, 1)}
    return _Parts(list(plan.names), [p.ref for p in plan.parts], [p.shape for p in plan.parts], list(plan.materials),
                  face_of, mesh_ordinal)


def _find(parts: _Parts, key: str | None, where: str) -> int:
    if key is None:
        if len(parts.names) == 1:
            return 0
        raise ValueError(f"{where}: name the part, by its name or ref; the parts are {', '.join(parts.names)}")
    for i, ref in enumerate(parts.refs):
        if key in (ref, f"#{key}"):
            return i
    named = [i for i, name in enumerate(parts.names) if name == key]
    if len(named) != 1:
        raise ValueError(f"{where}: no single part named {key!r}; the parts are {', '.join(parts.names)}")
    return named[0]


def _conductor(material) -> bool:
    from cadgen._internal.fea.em_ops import CONDUCTOR_BELOW_OHM_M

    return material.resistivity is not None and material.resistivity < CONDUCTOR_BELOW_OHM_M


def _coil_parts(parts: _Parts, inputs: ElectromagneticInputs) -> set[int]:
    return {_find(parts, coil.part, f"coils[{index}].part") for index, coil in enumerate(inputs.coils)}


def _eddy_parts(parts: _Parts, inputs: ElectromagneticInputs) -> list[int]:
    """The parts an AC field drives currents in: every conductor but a coil (a coil's wire is stranded)."""
    coils = _coil_parts(parts, inputs)
    return [i for i, m in enumerate(parts.materials) if _conductor(m) and i not in coils]


def _skin(material, frequency_Hz: float) -> float:
    from cadgen._internal.fea import em_ops

    return em_ops.skin_depth_mm(material.resistivity, float(material.permeability or 1.0), frequency_Hz)


def hertz(frequency: float) -> str:
    """A frequency as a person says it: "50 Hz", "15.8 kHz", "2 MHz"."""
    for scale, unit in ((1e6, "MHz"), (1e3, "kHz")):
        if frequency >= scale:
            return f"{frequency / scale:.3g} {unit}"
    return f"{frequency:.3g} Hz"


def _unheld_and_unheated(system) -> "np.ndarray":
    """The temperature DOF of every piece of the mesh conduction does not join to a held or cooled face and no heat
    goes into: its temperature is not set by anything (a singular block of the steady solve)."""
    import numpy as np
    from scipy.sparse.csgraph import connected_components

    count, piece = connected_components(system.conduction, directed=False)
    if count == 1:
        return np.zeros(0, dtype=np.int64)
    held = np.zeros(count, dtype=bool)
    for entry in system.fixed:
        held[piece[entry.dofs]] = True
    for film in system.films:
        held[piece[np.unique(film.matrix.tocoo().row)]] = True
    heated = np.zeros(count)
    for entry in system.heat:
        np.add.at(heated, piece, np.abs(entry.load))
    loose = ~held & (heated == 0)
    return np.flatnonzero(loose[piece]).astype(np.int64)


def _place(at) -> list[float]:
    return [round(float(c), 3) for c in at]


class ElectromagneticAnalysis:
    name: ClassVar[str] = "electromagnetic"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Magnetic / electric"
    estimate_only: ClassVar[bool] = False
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "mode", "voltages", "currents", "coils", "air", "probes", "capacitance", "resistance", "electro_thermal",
        "map_to_structure", "frequency_Hz", "applied_field",
    })
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    checks: ClassVar[tuple] = (kinds.ELECTRIC_FIELD, kinds.TEMPERATURE, kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum",
                  "options": ["potential", "electric_field", "current_density", "magnetic_field", "eddy_current"]},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    #: The static and DC modes' rungs; an AC study takes :data:`AC_LADDER` (``ladder`` follows the parsed mode).
    dc_ladder: ClassVar[tuple[str, ...]] = ("iterative", "local_refine", "defeature", "far_field", "symmetry")
    noun: ClassVar[str] = "this voltage"
    governing_word: ClassVar[str] = "the peak field"

    def __init__(self):
        # The fields the study last parsed writes (a study's view is checked against them); every field before any.
        self._fields: tuple[FieldSpec, ...] = tuple(FIELD_SPECS.values())
        self._mode = "electrostatic"

    @property
    def fields(self) -> tuple[FieldSpec, ...]:
        return self._fields

    @property
    def limits(self) -> tuple[str, ...]:
        """What the model leaves out, for the mode the study last parsed (static and DC, or AC)."""
        return AC_LIMITS if self._mode == "ac_magnetic" else LIMITS

    @property
    def ladder(self) -> tuple[str, ...]:
        return AC_LADDER if self._mode == "ac_magnetic" else self.dc_ladder

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> ElectromagneticInputs:
        inputs = parse_document(document)
        names = list(MODE_FIELDS[inputs.mode])
        if inputs.thermal is not None:
            names.append("temperature")
        if inputs.mapped:
            names += ["von_mises", "displacement"]
        self._fields = tuple(FIELD_SPECS[name] for name in names)
        self._mode = inputs.mode
        return inputs

    # -- the ladder ----------------------------------------------------------------------------------

    def _sizes(self, ctx: SolveContext, inputs: ElectromagneticInputs) -> tuple[float, float, float]:
        """(at the parts, out in the air, how far the air reaches) mm."""
        plan, geometry = ctx.plan, ctx.geometry
        size = float(plan.size_mm or plan.requested_mm or 1.0)
        far = float(plan.fluid_far_size_mm) if plan.fluid_far_size_mm else FAR * size
        extent = (geometry.bbox_diagonal_mm / math.sqrt(3.0)) if geometry is not None else 10.0
        around = inputs.air_mm or AROUND.get(inputs.mode, 1.0) * extent
        return size, max(far, size), around

    def _air_tets(self, ctx: SolveContext, inputs: ElectromagneticInputs) -> float:
        from cadgen._internal.fea import fit

        size, far, around = self._sizes(ctx, inputs)
        geometry = ctx.geometry
        parts = fit.tets_estimate(geometry, size) if geometry is not None else 0.0
        span = (geometry.bbox_diagonal_mm / math.sqrt(3.0) if geometry is not None else 10.0) + 2.0 * around
        air_volume = span ** 3 - (geometry.volume_mm3 if geometry is not None else 0.0)
        area = geometry.area_mm2 if geometry is not None else 0.0
        # A band a few elements thick at the parts' size, the size grading out to ``far`` beyond it.
        near = min(air_volume, area * 2.0 * size)
        middle = min(max(air_volume - near, 0.0), area * far)
        rest = max(air_volume - near - middle, 0.0)
        return parts + TETS * (near / size ** 3 + middle / (0.5 * (size + far)) ** 3 + rest / far ** 3)

    def estimate(self, ctx: SolveContext, inputs: ElectromagneticInputs):
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.thermal import ladder_estimate

        if not inputs.air:
            return ladder_estimate(ctx)
        tets = self._air_tets(ctx, inputs)
        solver = "iterative" if ctx.plan.solver in ("iterative", "matrix_free") else "direct"
        if inputs.mode == "ac_magnetic":
            size = self._sizes(ctx, inputs)[0]
            skin = self._skin_mm(ctx, inputs)
            area = ctx.geometry.area_mm2 if ctx.geometry is not None else 0.0
            if skin < size:
                # A band two skin elements deep over the conductors' faces, grading out to the parts' size.
                tets += TETS * area * (2.0 / skin ** 2 - 2.0 / size ** 2)
            # Nédélec DOF in the air and the parts, P2 voltage DOF in the conductors; complex: twice the memory, ~4x the time.
            cost = fit.solve_cost(tets, (EDGES_PER_TET + 0.7) * tets, components=1, order=1, solver=solver)
            return fit.Estimate(cost.dofs, 2 * cost.memory_bytes, 4.0 * cost.seconds)
        if inputs.mode == "magnetostatic":
            return fit.solve_cost(tets, EDGES_PER_TET * tets, components=1, order=1, solver=solver)
        return fit.solve_cost(tets, fit.NODES_PER_TET[2] * tets, components=1, order=2, solver=solver)

    def _skin_mm(self, ctx: SolveContext, inputs: ElectromagneticInputs) -> float:
        """The size the conductors' faces are meshed at: the thinnest skin over SKIN_ELEMENTS, or what the ladder
        coarsened it to; never over the parts' size."""
        size = self._sizes(ctx, inputs)[0]
        coarsened = getattr(ctx.plan, "skin_mm", None)
        if coarsened:
            return min(size, float(coarsened))
        depth = self._thinnest_skin(ctx, inputs)
        return min(size, depth / SKIN_ELEMENTS)

    def _thinnest_skin(self, ctx: SolveContext, inputs: ElectromagneticInputs) -> float:
        # Only the parts' materials: this runs in the fit ladder before meshing, when an assembly's face refs have
        # no mesh ordinal yet.
        parts = _parts(ctx, ())
        depths = [_skin(parts.materials[i], inputs.frequency_Hz) for i in _eddy_parts(parts, inputs)]
        return min(depths) if depths else math.inf

    def _skin_rung(self, ctx: SolveContext, inputs: ElectromagneticInputs):
        """local_refine, AC: the conductors' faces keep a fine mesh for the skin; when that will not fit, coarsen it
        (never past the parts' size) until it does, and say what that costs."""
        from cadgen._internal.fea import fit

        size = self._sizes(ctx, inputs)[0]
        skin = self._skin_mm(ctx, inputs)
        if skin >= size:
            return None
        depth = self._thinnest_skin(ctx, inputs)
        wanted = skin
        while skin < size:
            skin = min(size, 1.5 * skin)
            ctx.plan.skin_mm = skin
            if self.estimate(ctx, inputs).fits(ctx.budget):
                break
        return fit.Step(
            "local_refine",
            f"Meshed the conductors' surfaces at {skin:.3g} mm to fit, coarser than the {wanted:.3g} mm their "
            f"{depth:.3g} mm skin depth at {hertz(inputs.frequency_Hz)} asks for; the rest of the parts at {size:.3g} mm",
            "the loss and AC resistance read high when the skin is under-resolved: about 6% at one element per skin "
            "depth on a round wire, more when coarser", None,
            detail={"skin_depth_mm": round(depth, 4), "wanted_mm": round(wanted, 4), "surface_mm": round(skin, 4),
                    "size_mm": round(size, 4)},
        )

    def apply(self, rung, ctx: SolveContext, inputs: ElectromagneticInputs):
        from cadgen._internal.fea import fit

        if inputs.mode == "ac_magnetic" and rung == "local_refine":
            return self._skin_rung(ctx, inputs)

        if rung == "far_field":  # the air box out past the parts, meshed coarser
            if not inputs.air:
                return None
            plan = ctx.plan
            size, far, around = self._sizes(ctx, inputs)
            span = (ctx.geometry.bbox_diagonal_mm / math.sqrt(3.0) if ctx.geometry is not None else 10.0) + 2.0 * around
            coarser = min(COARSEN * far, span / 4.0)
            if coarser <= 1.05 * far:
                return None
            before = self.estimate(ctx, inputs)
            saved = plan.fluid_far_size_mm
            plan.fluid_far_size_mm = coarser
            after = self.estimate(ctx, inputs)
            if after.seconds > 0.95 * before.seconds and after.memory_bytes > 0.95 * before.memory_bytes:
                plan.fluid_far_size_mm = saved
                return None
            return fit.Step(
                "far_field",
                f"Coarsened the air away from the parts to fit: the parts are still meshed at {size:.3g} mm, "
                f"the air out at {coarser:.3g} mm",
                "the field far out in the air is resolved more coarsely; near the parts, where the answer is read, "
                "the mesh keeps its size", None,
                detail={"size_mm": round(size, 4), "from_far_mm": round(far, 4), "to_far_mm": round(coarser, 4)},
            )
        if inputs.air and rung in ("local_refine", "defeature", "symmetry"):
            return None  # the air region is meshed from the parts as they are, once
        return fit.apply_generic(rung, self, ctx, inputs)

    def symmetric_about(self, plane, inputs: ElectromagneticInputs, ctx: SolveContext) -> bool:
        """A potential solved on one part only: every electrode, temperature and check face maps onto itself."""
        if ctx.assembly is not None or inputs.air or inputs.mode in ("magnetostatic", "ac_magnetic") or inputs.probes:
            return False
        if inputs.thermal is not None and inputs.thermal[1]:
            return False  # a heat input given as a total power would land twice on half its faces

        def onto_itself(refs) -> bool:
            ordinals = {ctx.ordinal_of[ref] for ref in refs}
            return {plane.mirror.get(o) for o in ordinals} == ordinals

        groups = [e.faces for e in inputs.electrodes]
        if inputs.thermal is not None:
            groups += [g.faces for g in (*inputs.thermal[0], *inputs.thermal[1], *inputs.thermal[2])]
        checks = ctx.study.checks if ctx.study is not None else ()
        groups += [tuple(check["faces"]) for check in checks if check.get("faces")]
        return all(onto_itself(group) for group in groups)

    def governing(self, result: AnalysisResult):
        name = {"electrostatic": "electric_field", "current": "current_density",
                "ac_magnetic": "eddy_current"}.get(result.scalars.get("mode"), "magnetic_field")
        values = result.fields[name]
        return values, float(values.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: ElectromagneticInputs) -> AnalysisResult:
        import time

        started = time.perf_counter()
        parts = _parts(ctx, inputs.face_refs)
        if inputs.mode == "magnetostatic":
            result = self._magnetic(ctx, inputs, parts)
        elif inputs.mode == "ac_magnetic":
            result = self._ac(ctx, inputs, parts)
        else:
            result = self._potential(ctx, inputs, parts)
        result.scalars["mode"] = inputs.mode
        result.scalars["analysis_extras"] = {"mode": inputs.mode, "noun": NOUNS[inputs.mode]}
        if inputs.frequency_Hz is not None:
            result.scalars["analysis_extras"]["frequency_Hz"] = inputs.frequency_Hz
        result.timings["electromagnetic_s"] = time.perf_counter() - started
        result.scalars["summary"] = self.summary(result, inputs, [])
        return result

    def _region(self, ctx: SolveContext, inputs: ElectromagneticInputs, parts: _Parts, order: int = 2,
                part_sizes: dict[int, float] | None = None):
        from cadgen._internal.fea import em_ops

        if not inputs.air:
            return em_ops.part_region(ctx.space, ctx.volume, parts.mesh_ordinal, len(parts.names))
        if any(shape is None for shape in parts.shapes):
            raise ValueError("an electric or magnetic study with air needs the parts' solids; name the part with --occurrence")
        size, far, around = self._sizes(ctx, inputs)
        points = [[*p.at, size] for p in inputs.probes]
        pads = self._flush(inputs, parts, around) if inputs.mode == "ac_magnetic" and inputs.currents else around
        if ctx.log:
            ctx.log(f"meshing the parts at {size:.3g} mm in air reaching {around:.3g} mm past them (out to {far:.3g} mm elements)")
        return em_ops.build_region(parts.shapes, around_mm=pads, size_mm=size, far_mm=far, order=order,
                                   points=points, radius_mm=2.0 * size, part_sizes=part_sizes)

    def _flush(self, inputs: ElectromagneticInputs, parts: _Parts, around: float):
        """The air box's reach per side when a current is fed in: none past the faces it goes in and out through,
        which must be flat, square to x, y or z and at the end of the parts (where the leads go)."""
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.TopoDS import TopoDS

        from cadgen._internal.fea import em_ops
        from cadgen._internal.fea.assembly import part_faces
        from cadgen._internal.fea.mesh import area_center

        low, high = em_ops.bounds_of(parts.shapes)
        span = max(h - lo for lo, h in zip(low, high))
        below, above = [around] * 3, [around] * 3
        for entry in inputs.electrodes:
            key = "currents" if entry in inputs.currents else "voltages"
            for ref in entry.faces:
                part, ordinal = parts.face_of[ref]
                face = TopoDS.Face_s(part_faces(parts.shapes[part])[ordinal - 1])
                surface = BRepAdaptor_Surface(face)
                centre = area_center(face)[1]
                onto = None
                if surface.GetType() == GeomAbs_Plane:
                    normal = surface.Plane().Axis().Direction()
                    n = (normal.X(), normal.Y(), normal.Z())
                    for axis in range(3):
                        if abs(abs(n[axis]) - 1.0) < 1e-6:
                            if abs(centre[axis] - low[axis]) < 1e-6 * span:
                                onto = (axis, below)
                            elif abs(centre[axis] - high[axis]) < 1e-6 * span:
                                onto = (axis, above)
                if onto is None:
                    raise ValueError(f"{key}[{entry.name}]: an AC current goes in and out through flat faces square to "
                                     f"x, y or z at the ends of the parts (where its leads would be), so the air can stop "
                                     f"there; {ref} is not one")
                onto[1][onto[0]] = 0.0
        return below, above

    def _rows(self, region, parts: _Parts, refs, where: str):
        import numpy as np

        rows = []
        for ref in refs:
            key = parts.face_of[ref]
            found = region.face_rows.get(key)
            if found is None or len(found) == 0:
                raise ValueError(f"{where}: {ref} has no surface in the mesh (it is wholly a joint between parts); "
                                 "choose a face that is not covered by another part")
            rows.append(found)
        return np.unique(np.concatenate(rows))

    def _probe_nodes(self, region, probes) -> list[int]:
        import numpy as np
        from scipy.spatial import cKDTree

        if not probes:
            return []
        _, nearest = cKDTree(region.space.dof_locations).query(np.array([p.at for p in probes]))
        return [int(n) for n in np.atleast_1d(nearest)]

    def _potential(self, ctx: SolveContext, inputs: ElectromagneticInputs, parts: _Parts) -> AnalysisResult:
        import numpy as np

        from cadgen._internal.fea import em_ops
        from cadgen._internal.fea.analyses.thermal import plan_solver, space_result

        electro = inputs.mode == "electrostatic"
        region = self._region(ctx, inputs, parts)
        n = region.space.scalar_count
        mats = parts.materials
        planes = list(ctx.plan.prepared.planes) if ctx.plan is not None and ctx.plan.prepared is not None else []
        share = 0.5 ** len(planes)
        warnings: list[str] = []
        held, groups = [], []
        ties: list = []
        fixed_zero = None
        f = None
        if electro:
            conductor = [_conductor(m) for m in mats]
            for i, m in enumerate(mats):
                if not conductor[i] and m.permittivity is None:
                    raise ValueError(f"material: {parts.names[i]} ({m.name}) neither conducts nor has a permittivity; "
                                     f'add relative_permittivity to its material object, like {{"name": "{m.name}", '
                                     '"relative_permittivity": 3.0}')
            if all(conductor) and not region.air:
                raise ValueError("an electrostatic study needs something between its electrodes: a dielectric part "
                                 "(a plastic), or 'air': true for the air around the parts")
            coefficient = [1.0 if conductor[i] else m.permittivity for i, m in enumerate(mats)] + [em_ops.AIR_EPS_R]
            held_part: dict[int, str] = {}
            for e in inputs.voltages:
                rows = self._rows(region, parts, e.faces, f"voltages[{e.name}]")
                dofs = [region.space.boundary_quadratic[rows].ravel()]
                for ref in e.faces:
                    i = parts.face_of[ref][0]
                    if conductor[i]:
                        if i in held_part and held_part[i] != e.name:
                            raise ValueError(f"voltages: {parts.names[i]} conducts, so it is one voltage throughout, but "
                                             f"'{held_part[i]}' and '{e.name}' hold it at two")
                        held_part[i] = e.name
                        dofs.append(region.part_dofs(i))
                group = np.unique(np.concatenate(dofs))
                held.append((group, e.value))
                groups.append(group)
            ties = [region.part_dofs(i) for i in range(len(mats)) if conductor[i] and i not in held_part]
            element_mask = ~np.isin(region.domain, [i for i in range(len(mats)) if conductor[i]])
            K = em_ops.stiffness(region, coefficient)
        else:
            sigma = []
            for i, m in enumerate(mats):
                sigma.append(0.0 if m.resistivity > em_ops.INSULATOR_ABOVE_OHM_M else 1.0 / (m.resistivity * 1000.0))
            if not any(sigma):
                raise ValueError("a current needs a conductor: every part's resistivity is that of an insulator "
                                 f"(over {em_ops.INSULATOR_ABOVE_OHM_M:g} ohm m)")
            coefficient = sigma + [0.0]
            K = em_ops.stiffness(region, coefficient)
            conducting = np.asarray(sigma, dtype=float)[region.domain] > 0
            live = np.unique(region.space.element_dofs[conducting])
            fixed_zero = np.setdiff1d(np.arange(n), live)
            for e in inputs.voltages:
                rows = self._rows(region, parts, e.faces, f"voltages[{e.name}]")
                group = np.unique(region.space.boundary_quadratic[rows])
                if not np.isin(group, live).any():
                    raise ValueError(f"voltages[{e.name}]: its faces are on an insulator, which carries no current")
                held.append((group, e.value))
                groups.append(group)
            f = np.zeros(n)
            for e in inputs.currents:
                rows = self._rows(region, parts, e.faces, f"currents[{e.name}]")
                f += em_ops.flux_load(region, rows, e.value * share)
                groups.append(np.unique(region.space.boundary_quadratic[rows]))
            element_mask = conducting
        solved = em_ops.scalar_solve(K, n, held, ties, f, fixed_zero=fixed_zero, solver=plan_solver(ctx))
        x = solved.x
        energy = 0.5 * float(x @ (K @ x))
        if electro:
            _, field_nodes, magnitude = em_ops.node_gradients(region, x, element_mask)
            field_nodes = field_nodes / 1000.0                    # V/mm -> kV/mm
        else:
            sigma_e = np.asarray(coefficient, dtype=float)[region.domain]
            _, field_nodes, magnitude = em_ops.node_gradients(region, x, element_mask, scale=sigma_e)
        masked = np.where(element_mask[:, None], magnitude, -np.inf)
        e_peak, local = np.unravel_index(int(np.argmax(masked)), masked.shape)
        peak_dof = int(region.space.scalar.element_dofs[local, e_peak])
        peak = float(masked[e_peak, local]) / (1000.0 if electro else 1.0)
        scalars: dict[str, Any] = {"mode": inputs.mode, "parts": parts.names}
        per_electrode = []
        for e, group in zip(inputs.electrodes, groups):
            entry: dict[str, Any] = {"name": e.name, "faces": list(e.faces)}
            if electro:
                entry.update({"V": e.value, "charge_nC": em_ops.EPS0 * float(solved.residual[group].sum()) * 1e9 / share})
            elif e in inputs.voltages:
                entry.update({"V": e.value, "current_A": float(solved.residual[group].sum()) / share})
            else:
                rows = self._rows(region, parts, e.faces, f"currents[{e.name}]")
                entry.update({"V": em_ops.face_mean(region, rows, x), "current_A": e.value})
            per_electrode.append(entry)
        scalars["electrodes"] = per_electrode
        by_name = {entry["name"]: entry for entry in per_electrode}
        if electro:
            scalars["energy_J"] = em_ops.EPS0 * energy / share
            scalars["max_field_kV_mm"] = peak
            scalars["max_in"] = self._where_peak(region, parts, int(e_peak), region.space.dof_locations[peak_dof])
            if inputs.between is not None:
                # As a bridge measures it: the charge on the first electrode over the voltage between the two, every
                # other electrode at its own voltage (a guard ring at the first's voltage keeps the fringe off it).
                a, b = (by_name[name] for name in inputs.between)
                if a["V"] != b["V"]:
                    capacitance = a["charge_nC"] * 1e-9 / (a["V"] - b["V"])
                    scalars["capacitance"] = {"between": list(inputs.between), "pF": capacitance * 1e12}
        else:
            power = 2.0 * energy / share                          # ∫ sigma |grad V|^2, W
            scalars["power_W"] = power
            scalars["max_current_density_A_mm2"] = peak
            if inputs.between is not None:
                a, b = (by_name[name] for name in inputs.between)
                current = a["current_A"] if a["current_A"] > 0 else -b["current_A"]
                if abs(current) > 0:
                    resistance = (a["V"] - b["V"]) / current
                    scalars["resistance"] = {"between": list(inputs.between), "ohm": resistance, "current_A": current}
            # Joule heat at the quadrature points, W/mm³: sigma |grad V|^2.
            grad = region.space.scalar.interpolate(x).grad
            sigma_q = np.asarray(coefficient, dtype=float)[region.domain][:, None]
            joule = sigma_q * (grad ** 2).sum(axis=0)
            scalars["joule_W"] = float((joule * region.space.scalar.dx).sum()) / share
        scalars["max_at"] = region.space.dof_locations[peak_dof]
        if inputs.probes:
            nodes = self._probe_nodes(region, inputs.probes)
            scalars["probes"] = [{"label": p.label, "at_mm": list(p.at), "V": float(x[node]),
                                  ("electric_field_kV_mm" if electro else "current_density_A_mm2"): float(field_nodes[node])}
                                 for p, node in zip(inputs.probes, nodes)]
        field_name = "electric_field" if electro else "current_density"
        if region.air:
            potential = em_ops.to_part_mesh(region, x, ctx.space, ctx.volume.domain)
            field_values = em_ops.to_part_mesh(region, field_nodes, ctx.space, ctx.volume.domain)
            scalars["region"] = {"elements": int(len(region.volume.tets)), "nodes": int(region.space.scalar_count),
                                 "size_mm": round(region.size_mm, 4), "air_mm": round(region.far_mm, 4),
                                 "box_mm": [list(map(float, c)) for c in region.box]}
        else:
            potential, field_values = x, field_nodes
        fields = {"potential": potential, field_name: field_values}
        if not electro and inputs.thermal is not None:
            fields["temperature"] = self._heat(ctx, inputs, region, joule, scalars, warnings)
        result = space_result(ctx.space, fields, solver=f"{'P2' if ctx.space.order == 2 else 'P1'} potential, {solved.how}",
                              warnings=warnings, scalars=scalars)
        result.dofs = int(n)
        if planes:
            self._unfold(ctx, result, planes)
        return result

    def _heat(self, ctx, inputs, region, joule, scalars, warnings):
        """One-way electro-thermal: the Joule heat into a steady thermal solve on the same mesh."""
        from skfem import LinearForm, asm

        from cadgen._internal.fea import thermal_ops
        from cadgen._internal.fea.analyses.thermal import plan_solver

        temperatures, heat, convection = inputs.thermal
        space = ctx.space

        def facets(refs):
            return space.facets_of(refs, ctx.ordinal_of)

        system = thermal_ops.assemble(
            space, list(ctx.materials),
            fixed=[(facets(e.faces), e.celsius, e.history) for e in temperatures],
            heat=[(facets(e.faces), e.watts, e.per_m2, e.history) for e in heat],
            films=[(facets(e.faces), e.h, e.ambient, e.history) for e in convection],
        )

        @LinearForm
        def into(v, w):
            return w["q"] * v

        load = asm(into, space.scalar, q=joule) * thermal_ops.WATT
        system.heat.append(thermal_ops.Heat(load, float(load.sum()) / thermal_ops.WATT))
        unheld = _unheld_and_unheated(system)
        if len(unheld):
            # A part no heat reaches and nothing holds or cools (an induction coil beside its workpiece, the air
            # not modelled) has no temperature of its own: it is drawn at the ambient, not at 0 °C.
            system.fixed.append(thermal_ops.Fixed(unheld, float(inputs.reference_C or 0.0)))
        T, how = thermal_ops.solve_steady(system, warnings, solver=plan_solver(ctx))
        balance = thermal_ops.heat_balance(system, T)
        scalars["thermal"] = {"balance": balance, "reference_C": inputs.reference_C, "how": how}
        scalars["reference_C"] = inputs.reference_C
        return T

    @staticmethod
    def _where_peak(region, parts: _Parts, element: int, at) -> dict:
        """Where the strongest field is: in a part (its name), or in the air and the part nearest it. The colours are
        on the parts' surface, so a peak out in the air reads higher than the colour bar: the result says where."""
        import numpy as np

        domain = int(region.domain[element])
        if not region.air or domain < region.parts:
            return {"in": "part", "part": parts.names[domain]}
        points = region.space.mesh.p
        nearest, best = None, math.inf
        for part in range(region.parts):
            corners = np.unique(region.space.mesh.t[:, region.domain == part])
            if len(corners):
                gap = float(np.linalg.norm(points[:, corners] - np.asarray(at, dtype=float)[:, None], axis=0).min())
                if gap < best:
                    nearest, best = part, gap
        return {"in": "air", **({"near": parts.names[nearest], "gap_mm": round(best, 3)} if nearest is not None else {})}

    def _unfold(self, ctx: SolveContext, result: AnalysisResult, planes) -> None:
        """The solved half (or quarter) mirrored back into the whole part."""
        from cadgen._internal.fea import symmetry

        volume = ctx.volume
        for plane in reversed(planes):
            whole, keep = symmetry.unfold_volume(volume, plane)
            locations, scalars, _, boundary, tets, elements, vertices = symmetry.unfold_fields(
                plane, result.vertices, result.dof_locations, keep, scalars=dict(result.fields), vectors={},
                boundary=result.boundary_quadratic, tets=result.tets, element_dofs=result.element_dofs,
            )
            result.dof_locations, result.fields, result.boundary_quadratic = locations, scalars, boundary
            result.tets, result.element_dofs, result.vertices = tets, elements, vertices
            volume = whole
        ctx.volume = volume

    def _magnetic(self, ctx: SolveContext, inputs: ElectromagneticInputs, parts: _Parts) -> AnalysisResult:
        import numpy as np

        from cadgen._internal.fea import em_ops
        from cadgen._internal.fea.analyses.thermal import plan_solver, space_result

        region = self._region(ctx, inputs, parts, order=1)
        mats = parts.materials
        mu_r = [float(m.permeability) for m in mats] + [em_ops.AIR_MU_R]
        J = None
        coils = []
        for index, coil in enumerate(inputs.coils):
            part = _find(parts, coil.part, f"coils[{index}].part")
            basis = region.space_hcurl
            if coil.point is None:
                inside = region.domain == part
                weights = basis.dx[inside].sum(axis=1)
                centres = region.space.mesh.p[:, region.space.mesh.t[:, inside]].mean(axis=1)
                point = tuple((centres * weights).sum(axis=1) / weights.sum())
            else:
                point = coil.point
            density, section, smallest = em_ops.coil_source(region, part, coil.turns, coil.amps, point, coil.direction)
            if smallest < 0.05 * region.size_mm:
                raise ValueError(f"coils[{index}]: {parts.names[part]} reaches its own axis, so it does not wind around "
                                 "it; a coil is a ring of wire around the axis (check axis.direction and point_mm)")
            J = density if J is None else J + density
            coils.append({"name": coil.name, "part": parts.names[part], "index": part, "turns": coil.turns, "A": coil.amps,
                          "section_mm2": section, "axis_point_mm": _place(point), "axis_direction": list(coil.direction),
                          "current_density_A_mm2": coil.turns * abs(coil.amps) / section})
        solved = em_ops.curl_curl(region, mu_r, J, solver=plan_solver(ctx))
        B = solved.B
        tesla = np.linalg.norm(B, axis=1) * 1e6
        volumes = em_ops.element_volumes(region)
        scalars: dict[str, Any] = {"mode": "magnetostatic", "parts": parts.names, "coils": coils,
                                   "energy_J": solved.energy_J}
        if len(coils) == 1 and coils[0]["A"]:
            scalars["inductance_H"] = 2.0 * solved.energy_J / coils[0]["A"] ** 2
        peak = int(np.argmax(tesla))
        centres = region.space.mesh.p[:, region.space.mesh.t].mean(axis=1).T
        scalars["max_field_T"] = float(tesla[peak])
        scalars["max_at"] = centres[peak]
        forces = []
        coil_parts = {c["index"] for c in coils}
        for i, m in enumerate(mats):
            if i in coil_parts:
                force, how = em_ops.lorentz_force(region, J, B, i), "J x B"
            elif abs(mu_r[i] - 1.0) > MAGNETIC:
                force, how = em_ops.magnetic_force(region, B, i), "Maxwell stress"
            else:
                continue
            forces.append({"part": parts.names[i], "index": i, "N": [float(c) for c in force], "by": how})
        scalars["forces"] = forces
        if inputs.probes:
            found = em_ops.element_at(region, np.array([p.at for p in inputs.probes]))
            scalars["probes"] = [
                {"label": p.label, "at_mm": list(p.at),
                 **({"B_mT": [float(c) * 1e9 for c in B[e]], "magnetic_field_mT": float(tesla[e]) * 1e3} if e >= 0 else
                    {"outside": True})}
                for p, e in zip(inputs.probes, found)
            ]
        # |B| at the region's nodes, each part's own elements averaged (the air's on the air's), then onto the run's mesh.
        nodal = np.zeros(region.space.scalar_count)
        for part in range(region.parts):
            inside = region.domain == part
            dofs = region.space.element_dofs[inside]
            total = np.zeros(region.space.scalar_count)
            count = np.zeros(region.space.scalar_count)
            np.add.at(total, dofs.ravel(), np.repeat(tesla[inside] * volumes[inside], dofs.shape[1]))
            np.add.at(count, dofs.ravel(), np.repeat(volumes[inside], dofs.shape[1]))
            touched = count > 0
            nodal[touched] = total[touched] / count[touched]
        field = em_ops.to_part_mesh(region, nodal * 1e3, ctx.space, ctx.volume.domain)
        scalars["region"] = {"elements": int(len(region.volume.tets)), "edges": int(solved.dofs),
                             "size_mm": round(region.size_mm, 4), "air_mm": round(region.far_mm, 4),
                             "box_mm": [list(map(float, c)) for c in region.box]}
        result = space_result(ctx.space, {"magnetic_field": field}, solver=f"Nédélec curl-curl, {solved.how}",
                              scalars=scalars)
        result.dofs = int(solved.dofs)
        if inputs.mapped:
            self._structure(ctx, inputs, parts, result, forces)
        return result

    def _ac(self, ctx: SolveContext, inputs: ElectromagneticInputs, parts: _Parts) -> AnalysisResult:
        """Time-harmonic magnetics: coils, fed conductors or a uniform field at ``frequency_Hz``; eddy currents in every
        conductor, their loss, the impedance of a lone source, and the loss handed to a thermal solve."""
        import numpy as np

        from cadgen._internal.fea import em_ops
        from cadgen._internal.fea.analyses.thermal import plan_solver, space_result

        frequency = float(inputs.frequency_Hz)
        omega = 2.0 * math.pi * frequency
        mats = parts.materials
        coil_parts = _coil_parts(parts, inputs)
        eddy = _eddy_parts(parts, inputs)
        size = self._sizes(ctx, inputs)[0]
        skin = self._skin_mm(ctx, inputs)
        # Each conductor's faces at half its own skin depth (or the ladder's coarser size), never over the parts' size.
        coarsened = getattr(ctx.plan, "skin_mm", None)
        part_sizes = {i: min(size, float(coarsened) if coarsened else _skin(mats[i], frequency) / SKIN_ELEMENTS) for i in eddy}
        region = self._region(ctx, inputs, parts, order=1, part_sizes={i: h for i, h in part_sizes.items() if h < size})
        mu_r = [float(m.permeability) for m in mats] + [em_ops.AIR_MU_R]
        sigma = [1.0 / (m.resistivity * 1000.0) if i in eddy else 0.0 for i, m in enumerate(mats)] + [0.0]
        J = None
        coils = []
        for index, coil in enumerate(inputs.coils):
            part = _find(parts, coil.part, f"coils[{index}].part")
            if coil.point is None:
                inside = region.domain == part
                weights = region.space_hcurl.dx[inside].sum(axis=1)
                centres = region.space.mesh.p[:, region.space.mesh.t[:, inside]].mean(axis=1)
                point = tuple((centres * weights).sum(axis=1) / weights.sum())
            else:
                point = coil.point
            density, section, smallest = em_ops.coil_source(region, part, coil.turns, coil.amps, point, coil.direction)
            if smallest < 0.05 * region.size_mm:
                raise ValueError(f"coils[{index}]: {parts.names[part]} reaches its own axis, so it does not wind around "
                                 "it; a coil is a ring of wire around the axis (check axis.direction and point_mm)")
            J = density if J is None else J + density
            coils.append({"name": coil.name, "part": parts.names[part], "index": part, "turns": coil.turns, "A": coil.amps,
                          "section_mm2": section, "axis_point_mm": _place(point), "axis_direction": list(coil.direction),
                          "current_density_A_mm2": coil.turns * abs(coil.amps) / section})
        fed, grounds, feeds = [], [], []
        for e in inputs.currents:
            rows = self._rows(region, parts, e.faces, f"currents[{e.name}]")
            part = parts.face_of[e.faces[0]][0]
            if sigma[part] == 0.0:
                raise ValueError(f"currents[{e.name}]: {parts.names[part]} does not conduct ("
                                 + ("a coil is driven by its turns and A" if part in coil_parts else "an insulator") + ")")
            fed.append(em_ops.Fed(em_ops.face_dofs_p2(region, rows), e.value))
            feeds.append({"name": e.name, "part": parts.names[part], "A": e.value})
        for e in inputs.voltages:
            grounds.append(em_ops.face_dofs_p2(region, self._rows(region, parts, e.faces, f"voltages[{e.name}]")))
        applied = None
        if inputs.applied is not None:
            direction = np.asarray(inputs.applied.direction, dtype=float)
            applied = direction / np.linalg.norm(direction) * inputs.applied.mT * 1e-9      # mT -> Wb/mm²
        solved = em_ops.ac_solve(region, mu_r, sigma, omega, J_s=J, fed=fed, grounds=grounds, applied_B=applied,
                                 solver=plan_solver(ctx))
        tesla = np.linalg.norm(np.abs(solved.B), axis=1) * 1e6
        volumes = em_ops.element_volumes(region)
        losses = [{"part": parts.names[i], "index": i, "W": float(solved.loss_by_domain[i])} for i in eddy]
        total = float(sum(entry["W"] for entry in losses))
        scalars: dict[str, Any] = {"mode": "ac_magnetic", "parts": parts.names, "frequency_Hz": frequency, "coils": coils,
                                   "fed": feeds, "energy_J": solved.energy_J, "loss_W": total, "losses": losses}
        if inputs.applied is not None:
            scalars["applied_field"] = {"mT": inputs.applied.mT, "direction": list(inputs.applied.direction)}
        sources = [(c["name"], c["A"]) for c in coils] + [(f["name"], f["A"]) for f in feeds]
        if len(sources) == 1 and inputs.applied is None and sources[0][1]:
            name, amps = sources[0]
            resistance = 2.0 * total / amps ** 2
            inductance = 4.0 * solved.energy_J / amps ** 2
            scalars["impedance"] = {"of": name, "R_ohm": resistance, "L_H": inductance, "X_ohm": omega * inductance,
                                    "Z_ohm": math.hypot(resistance, omega * inductance),
                                    "coil": bool(coils)}
        # The skin: each eddy-current part's depth against the size its faces were meshed at.
        warnings: list[str] = []
        skins = []
        for i in eddy:
            depth = _skin(mats[i], frequency)
            surface = part_sizes[i]
            resolved = surface <= RESOLVED_AT * depth
            skins.append({"part": parts.names[i], "depth_mm": depth, "surface_mm": surface,
                          "elements_per_depth": depth / surface, "resolved": resolved})
            if not resolved:
                warnings.append(
                    f"The mesh at {parts.names[i]}'s surface ({surface:.3g} mm) is coarser than half its skin depth "
                    f"({depth:.3g} mm at {hertz(frequency)}), so the skin is not resolved there: its loss and AC resistance "
                    f"read high, by about 6% at one element per skin depth and more when coarser")
        scalars["skin"] = skins
        scalars["analysis_warnings"] = list(warnings)
        peak = int(np.argmax(tesla))
        centres = region.space.mesh.p[:, region.space.mesh.t].mean(axis=1).T
        scalars["max_field_T"] = float(tesla[peak])
        scalars["max_field_at"] = centres[peak]
        conducting = np.isin(region.domain, eddy)
        if conducting.any():
            corner = np.where(conducting[:, None], solved.vertex_J, -np.inf)
            e_peak, local = np.unravel_index(int(np.argmax(corner)), corner.shape)
            scalars["max_eddy_current_A_mm2"] = float(corner[e_peak, local])
            scalars["max_at"] = region.space.mesh.p[:, region.space.mesh.t[local, e_peak]]
        else:
            scalars["max_eddy_current_A_mm2"] = 0.0
            scalars["max_at"] = scalars["max_field_at"]
        if inputs.probes:
            found = em_ops.element_at(region, np.array([p.at for p in inputs.probes]))
            scalars["probes"] = [
                {"label": p.label, "at_mm": list(p.at),
                 **({"B_mT": [float(abs(c)) * 1e9 for c in solved.B[e]], "magnetic_field_mT": float(tesla[e]) * 1e3}
                    if e >= 0 else {"outside": True})}
                for p, e in zip(inputs.probes, found)
            ]
        # Onto the run's mesh: |B| averaged at each part's nodes, |J| at each conductor's corners averaged at its nodes.
        n = region.space.scalar_count
        b_nodal = np.zeros(n)
        j_nodal = np.zeros(n)
        corner_J = solved.vertex_J                                   # (E, 4), in the element's corner order
        dofs_all = region.space.scalar.element_dofs.T                # (E, 4), the same order
        for part in range(region.parts):
            inside = region.domain == part
            dofs = dofs_all[inside]
            weights = np.repeat(volumes[inside], dofs.shape[1])
            count = np.bincount(dofs.ravel(), weights=weights, minlength=n)
            touched = count > 0
            b_total = np.bincount(dofs.ravel(), weights=np.repeat(tesla[inside] * volumes[inside], dofs.shape[1]), minlength=n)
            b_nodal[touched] = b_total[touched] / count[touched]
            if part in eddy:
                j_total = np.bincount(dofs.ravel(), weights=(corner_J[inside] * volumes[inside][:, None]).ravel(), minlength=n)
                j_nodal[touched] = j_total[touched] / count[touched]
            else:
                j_nodal[touched] = 0.0
        fields = {"eddy_current": em_ops.to_part_mesh(region, j_nodal, ctx.space, ctx.volume.domain),
                  "magnetic_field": em_ops.to_part_mesh(region, b_nodal * 1e3, ctx.space, ctx.volume.domain)}
        scalars["region"] = {"elements": int(len(region.volume.tets)), "dofs": int(solved.dofs),
                             "size_mm": round(region.size_mm, 4), "air_mm": round(region.far_mm, 4),
                             "box_mm": [list(map(float, c)) for c in region.box]}
        if inputs.thermal is not None:
            heat = self._loss_onto_parts(ctx, region, solved, eddy)
            fields["temperature"] = self._heat(ctx, inputs, region, heat, scalars, warnings)
        result = space_result(ctx.space, fields, solver=f"Nédélec + P2 A-phi at {hertz(frequency)}, {solved.how}",
                              warnings=warnings, scalars=scalars)
        result.dofs = int(solved.dofs)
        return result

    def _loss_onto_parts(self, ctx: SolveContext, region, solved, eddy: list[int]):
        """The time-averaged loss density (W/mm³) at the run's mesh's quadrature points: each point takes its nearest
        region element of the same part, then each part is scaled so its total is the loss solved, exactly."""
        import numpy as np
        from scipy.spatial import cKDTree

        space = ctx.space
        basis = space.scalar
        X = basis.mapping.F(basis.quadrature[0])                     # (3, E, Q)
        target_domain = np.zeros(basis.nelems, dtype=np.int64) if ctx.volume.domain is None else np.asarray(ctx.volume.domain)
        q = np.zeros(X.shape[1:])
        dx = solved.basis_p2.dx
        per_element = (solved.loss * dx).sum(axis=1) / dx.sum(axis=1)
        centres = region.space.mesh.p[:, region.space.mesh.t].mean(axis=1).T
        for part in eddy:
            source = np.flatnonzero(region.domain == part)
            target = np.flatnonzero(target_domain == part)
            if len(source) == 0 or len(target) == 0:
                continue
            points = X[:, target, :].reshape(3, -1).T
            _, nearest = cKDTree(centres[source]).query(points)
            values = per_element[source[nearest]].reshape(len(target), -1)
            mapped = float((values * basis.dx[target]).sum())
            if mapped > 0:
                values *= solved.loss_by_domain[part] / mapped
            q[target] = values
        return q

    def _structure(self, ctx, inputs, parts: _Parts, result: AnalysisResult, forces: list[dict]) -> None:
        """One way: the magnetic force on one part, spread evenly through it, as a static load; its fields and checks join."""
        import dataclasses
        import types

        import numpy as np

        from cadgen._internal.fea import solve
        from cadgen._internal.fea.analyses.static import solved_record, solved_part_record

        if inputs.structure_part is not None:
            target = _find(parts, inputs.structure_part, "map_to_structure.part")
        elif forces:
            target = max(forces, key=lambda f: float(np.linalg.norm(f["N"])))["index"]
        else:
            raise ValueError("map_to_structure: no part feels a magnetic force (no coil, no magnetic part) to load")
        force = next((np.array(f["N"]) for f in forces if f["index"] == target), np.zeros(3))
        space, volume = ctx.space, ctx.volume
        inside = np.ones(len(space.tets), bool) if volume.domain is None else np.asarray(volume.domain) == target
        part_volume = float(space.scalar.dx[inside].sum())
        # The force as a body load on the target part alone: unit density there, none elsewhere, b = F / V.
        loaded = [dataclasses.replace(m, density=1.0 if i == target else 0.0) for i, m in enumerate(parts.materials)]
        acceleration = (force / part_volume).tolist()
        extra: dict[str, Any] = {"space": space, "body_loads": [acceleration]}
        if ctx.plan is not None and ctx.plan.solver != "direct":
            extra["solver"] = "iterative"
        material_arg = loaded[0] if ctx.assembly is None else loaded
        outcome = solve.solve_linear_static(volume, material_arg, inputs.fixtures, (), ctx.ordinal_of, log=ctx.log,
                                            automatic=ctx.automatic, **extra)
        margin = getattr(ctx.study, "margin", 2.0) if ctx.study is not None else 2.0
        if ctx.assembly is None:
            study = types.SimpleNamespace(material=parts.materials[0], margin=margin)
            result.solved = [solved_record(volume, outcome, study, ctx.ordinal_of, ctx.part_name, inputs.fixtures)]
        else:
            study = types.SimpleNamespace(material=parts.materials[0], margin=margin)
            result.solved = [solved_part_record(volume, outcome, study, ctx.assembly, i, ctx.ordinal_of, inputs.fixtures)
                             for i in range(len(parts.names))]
        result.fields["von_mises"] = outcome.von_mises
        result.fields["displacement"] = outcome.displacement
        result.deformation = outcome.displacement
        result.reactions = list(outcome.reactions)
        result.applied = tuple(outcome.applied)
        result.warnings += [w for w in outcome.warnings if w not in result.warnings]
        result.scalars["outcome"] = outcome
        result.scalars["structure"] = {"part": parts.names[target], "force_N": force.tolist()}

    def needs_finer(self, result: AnalysisResult, inputs: ElectromagneticInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult,
              inputs: ElectromagneticInputs) -> dict:
        from cadgen._internal.fea.checks import check_status

        if check["kind"] in ("stress", "displacement"):
            from cadgen._internal.fea.analyses import get_analysis

            judged = get_analysis("static").judge(check, index, ctx, result, inputs)
            # The magnetic force, and so the stress and displacement it makes, grow with the current squared:
            # twice the current is four times the stress, so the current that reaches a limit is its square root.
            return {**judged, "scaling": "quadratic"}
        if check["kind"] == "temperature":
            from cadgen._internal.fea.analyses.thermal import temperature_check

            peak = kinds.field_max_over(
                result.fields["temperature"], tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
                boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
                ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
            )
            return temperature_check(check, peak.value, inputs.reference_C, at=peak.at, ref=peak.ref, faces=peak.faces)
        faces = tuple(check.get("faces", ()))
        peak_in = None
        if faces:
            peak = kinds.field_max_over(
                result.fields["electric_field"], faces, boundary=result.boundary_quadratic,
                boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
                ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
            )
            value, at, ref, named = peak.value, peak.at, peak.ref, peak.faces
        else:
            # The strongest field anywhere: in a dielectric part or in the air between the parts.
            value, at, ref, named = result.scalars["max_field_kV_mm"], result.scalars["max_at"], None, ()
            peak_in = result.scalars.get("max_in")
        limit = check["limit_kV_mm"]
        ratio = value / limit
        return {
            "kind": "electric_field", "label": check.get("label") or "Arcing", "value": round(value, 6), "limit": limit,
            "unit": "kV/mm", "ratio": round(ratio, 6), "close_at": CLOSE_AT, "status": check_status(ratio, CLOSE_AT),
            "where": {"ref": ref, "at": _place(at), **(peak_in if not faces and peak_in else {})},
            **({"faces": list(named)} if named else {}),
        }

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: ElectromagneticInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea import checks

        found: list[dict] = []
        if result.solved:
            found += checks.findings(min(result.solved, key=lambda s: math.inf if checks.safety_factor(s) is None
                                         else checks.safety_factor(s)))
        for check in check_results:
            if check["kind"] == "temperature":
                from cadgen._internal.fea.analyses.thermal import temperature_findings

                found += temperature_findings([check], assembly=assembly)
            if check["kind"] != "electric_field" or check["status"] == "passes":
                continue
            fails = check["status"] == "fails"
            value = f"{check['value']:.4g} kV/mm"
            found.append({
                "check": "fea", "severity": "error" if fails else "warning",
                "type": "electric_field_over_limit" if fails else "electric_field_close_to_limit",
                "summary": (f"The field reaches {value}, {'over' if fails else 'close to'} the {check['limit']:g} kV/mm "
                            f"allowed: {'it would arc over' if fails else 'it is close to arcing'}"),
                "description": f"peak field {value} against {check['limit']:g} kV/mm ({check['ratio']:.2f} of it); sharp "
                               "edges concentrate the field, so round them to bring it down",
                "items": [{"text": "the strongest field", **check["where"]}],
            })
        if inputs.mode == "electrostatic" and len({e.value for e in inputs.voltages}) == 1:
            found.append({"check": "fea", "severity": "info", "type": "one_voltage",
                          "summary": f"Every electrode is at {inputs.voltages[0].value:g} V, so there is no field",
                          "description": "hold two faces at different voltages to see a field", "items": []})
        thermal = result.scalars.get("thermal")
        if thermal and thermal["balance"]["imbalance"] > 0.01:
            b = thermal["balance"]
            found.append({"check": "fea", "severity": "warning", "type": "heat_balance",
                          "summary": f"The heat in ({b['in_W']:.4g} W) and out ({b['out_W']:.4g} W) differ by "
                                     f"{b['imbalance']:.1%}: the temperatures may not have settled",
                          "description": "a finer mesh should close it", "items": []})
        return found

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        if "displacement" not in result.fields:
            return None
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        return requested or auto_deformation_scale(float(np.linalg.norm(result.fields["displacement"], axis=1).max()),
                                                   bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: ElectromagneticInputs, check_results: list[dict]) -> dict:
        import numpy as np

        s = result.scalars
        mode = s.get("mode", inputs.mode)
        out: dict[str, Any] = {"mode": mode, "air": inputs.air}
        if "region" in s:
            out["region"] = dict(s["region"])
        if mode == "electrostatic":
            potential = result.fields["potential"]
            out.update({
                "max_field_kV_mm": round(s["max_field_kV_mm"], 6),
                "max_at_mm": _place(s["max_at"]),
                "energy_J": float(f"{s['energy_J']:.6g}"),
                "min_potential_V": round(float(potential.min()), 6),
                "max_potential_V": round(float(potential.max()), 6),
                "max_surface_field_kV_mm": round(float(result.fields["electric_field"].max()), 6),
                **({"max_in": s["max_in"]} if s.get("max_in") else {}),
                "electrodes": [{"name": e["name"], "V": e["V"], "charge_nC": float(f"{e['charge_nC']:.6g}")}
                               for e in s["electrodes"]],
            })
            if "capacitance" in s:
                out["capacitance_pF"] = float(f"{s['capacitance']['pF']:.6g}")
                out["capacitance_between"] = s["capacitance"]["between"]
        elif mode == "current":
            potential = result.fields["potential"]
            out.update({
                "max_current_density_A_mm2": round(s["max_current_density_A_mm2"], 6),
                "max_at_mm": _place(s["max_at"]),
                "power_W": float(f"{s['power_W']:.6g}"),
                "joule_heat_W": float(f"{s['joule_W']:.6g}"),
                "min_potential_V": round(float(potential.min()), 6),
                "max_potential_V": round(float(potential.max()), 6),
                "electrodes": [{"name": e["name"], "V": float(f"{e['V']:.6g}"), "current_A": float(f"{e['current_A']:.6g}")}
                               for e in s["electrodes"]],
            })
            if "resistance" in s:
                out["resistance_ohm"] = float(f"{s['resistance']['ohm']:.6g}")
                out["resistance_between"] = s["resistance"]["between"]
                out["current_A"] = float(f"{s['resistance']['current_A']:.6g}")
            out.update(self._temperature_summary(result, inputs))
        elif mode == "ac_magnetic":
            out.update({
                "frequency_Hz": s["frequency_Hz"],
                "loss_W": float(f"{s['loss_W']:.6g}"),
                "losses": [{"part": entry["part"], "W": float(f"{entry['W']:.6g}")} for entry in s["losses"]],
                "max_eddy_current_A_mm2": round(s["max_eddy_current_A_mm2"], 6),
                "max_at_mm": _place(s["max_at"]),
                "max_field_mT": round(s["max_field_T"] * 1e3, 6),
                "max_field_at_mm": _place(s["max_field_at"]),
                "max_surface_field_mT": round(float(result.fields["magnetic_field"].max()), 6),
                "energy_J": float(f"{s['energy_J']:.6g}"),
                "skin": [{"part": k["part"], "depth_mm": round(k["depth_mm"], 6), "surface_mm": round(k["surface_mm"], 6),
                          "elements_per_depth": round(k["elements_per_depth"], 3), "resolved": k["resolved"]}
                         for k in s["skin"]],
                "coils": [{"name": c["name"], "part": c["part"], "turns": c["turns"], "A": c["A"],
                           "ampere_turns": c["turns"] * c["A"], "section_mm2": round(c["section_mm2"], 6),
                           "current_density_A_mm2": round(c["current_density_A_mm2"], 6),
                           "axis_point_mm": c["axis_point_mm"], "axis_direction": c["axis_direction"]} for c in s["coils"]],
                "currents": [{"name": f["name"], "part": f["part"], "A": f["A"]} for f in s["fed"]],
            })
            if "applied_field" in s:
                out["applied_field"] = dict(s["applied_field"])
            if "impedance" in s:
                z = s["impedance"]
                out["impedance"] = {"of": z["of"], "R_ohm": float(f"{z['R_ohm']:.6g}"), "L_uH": float(f"{z['L_H'] * 1e6:.6g}"),
                                    "X_ohm": float(f"{z['X_ohm']:.6g}"), "Z_ohm": float(f"{z['Z_ohm']:.6g}")}
            out.update(self._temperature_summary(result, inputs))
        else:
            field = result.fields["magnetic_field"]
            out.update({
                "max_field_mT": round(s["max_field_T"] * 1e3, 6),
                "max_at_mm": _place(s["max_at"]),
                "max_surface_field_mT": round(float(field.max()), 6),
                "energy_J": float(f"{s['energy_J']:.6g}"),
                "coils": [{"name": c["name"], "part": c["part"], "turns": c["turns"], "A": c["A"],
                           "ampere_turns": c["turns"] * c["A"], "section_mm2": round(c["section_mm2"], 6),
                           "current_density_A_mm2": round(c["current_density_A_mm2"], 6),
                           "axis_point_mm": c["axis_point_mm"], "axis_direction": c["axis_direction"]} for c in s["coils"]],
                "forces": [{"part": f["part"], "force_N": [float(f"{c:.6g}") for c in f["N"]], "by": f["by"]}
                           for f in s["forces"]],
            })
            if "inductance_H" in s:
                out["inductance_uH"] = float(f"{s['inductance_H'] * 1e6:.6g}")
            if "structure" in s:
                outcome = s["outcome"]
                out["structure"] = {"part": s["structure"]["part"],
                                    "force_N": [float(f"{c:.6g}") for c in s["structure"]["force_N"]],
                                    "max_von_mises_MPa": round(float(outcome.von_mises.max()), 4),
                                    "max_displacement_mm": round(float(np.linalg.norm(outcome.displacement, axis=1).max()), 6)}
        if "probes" in s:
            out["probes"] = [{k: (float(f"{v:.6g}") if isinstance(v, float) else
                                  [float(f"{c:.6g}") for c in v] if isinstance(v, list) and k != "at_mm" else v)
                              for k, v in p.items()} for p in s["probes"]]
        out["deformation_scale"] = s.get("deformation_scale")
        out["checks"] = check_results
        return out

    def _temperature_summary(self, result: AnalysisResult, inputs: ElectromagneticInputs) -> dict:
        if "temperature" not in result.fields:
            return {}
        T = result.fields["temperature"]
        balance = result.scalars["thermal"]["balance"]
        return {"max_temperature_C": round(float(T.max()), 4), "min_temperature_C": round(float(T.min()), 4),
                "temperature_max_at_mm": _place(result.dof_locations[int(T.argmax())]),
                "heat_in_W": round(balance["in_W"], 6), "heat_out_W": round(balance["out_W"], 6),
                "heat_balance": round(balance["imbalance"], 6), "reference_C": inputs.reference_C}

    def extras_name(self, stem: str) -> str:
        return f"{stem} electromagnetic"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        ranges = {}
        for name, values in result.fields.items():
            magnitude = np.linalg.norm(values, axis=1) if values.ndim == 2 else values
            low = float(magnitude.min()) if FIELD_SPECS[name].signed else 0.0
            ranges[name] = (round(low, 6), round(float(magnitude.max()), 6))
        return ranges

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: ElectromagneticInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo: dict[str, Any] = {"mode": inputs.mode}
        if inputs.frequency_Hz is not None:
            echo["frequency_Hz"] = inputs.frequency_Hz
        if inputs.applied is not None:
            echo["applied_field"] = {"mT": inputs.applied.mT, "direction": list(inputs.applied.direction)}
        if inputs.voltages:
            echo["voltages"] = [{"faces": bare(e.faces), "V": e.value, "name": e.name} for e in inputs.voltages]
        if inputs.currents:
            echo["currents"] = [{"faces": bare(e.faces), "A": e.value, "name": e.name} for e in inputs.currents]
        if inputs.coils:
            echo["coils"] = [{"part": c.part, "turns": c.turns, "A": c.amps, "name": c.name,
                              "axis": {"direction": list(c.direction), **({"point_mm": list(c.point)} if c.point else {})}}
                             for c in inputs.coils]
        if inputs.air:
            echo["air"] = {"around_mm": inputs.air_mm} if inputs.air_mm else True
        if inputs.probes:
            echo["probes"] = [{"at_mm": list(p.at), "label": p.label} for p in inputs.probes]
        if inputs.thermal is not None:
            from cadgen._internal.fea.analyses.thermal import heat_echo

            temperatures, heat, convection = inputs.thermal
            echo["electro_thermal"] = heat_echo(
                type("_Heat", (), {"temperatures": temperatures, "heat": heat, "convection": convection})(), bare)
        if inputs.mapped:
            echo["fixtures"] = [{"type": f.type, "faces": bare(f.faces)} for f in inputs.fixtures]
            echo["loads"] = []
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        mode = summary["mode"]
        lines = []
        if mode == "electrostatic":
            where = summary.get("max_in") or {}
            inside = (f" in the air near {where['near']}" if where.get("in") == "air" and where.get("near")
                      else " in the air" if where.get("in") == "air" else "")
            on_surface = (f" ({summary['max_surface_field_kV_mm']:.4g} kV/mm on the parts' surface)"
                          if where.get("in") == "air" else "")
            lines.append(f"strongest field {summary['max_field_kV_mm']:.4g} kV/mm{inside} at {summary['max_at_mm']} mm"
                         f"{on_surface}; voltage {summary['min_potential_V']:g} to {summary['max_potential_V']:g} V")
            if "capacitance_pF" in summary:
                a, b = summary["capacitance_between"]
                lines.append(f"capacitance between {a} and {b}: {summary['capacitance_pF']:.6g} pF; "
                             f"stored energy {summary['energy_J']:.4g} J")
        elif mode == "current":
            if "resistance_ohm" in summary:
                a, b = summary["resistance_between"]
                lines.append(f"resistance between {a} and {b}: {summary['resistance_ohm']:.6g} ohm at "
                             f"{summary['current_A']:.4g} A")
            lines.append(f"Joule heat {summary['joule_heat_W']:.6g} W; densest current "
                         f"{summary['max_current_density_A_mm2']:.4g} A/mm² at {summary['max_at_mm']} mm")
            if "max_temperature_C" in summary:
                lines.append(f"hottest {summary['max_temperature_C']:g} °C, coolest {summary['min_temperature_C']:g} °C "
                             "from the Joule heat")
        elif mode == "ac_magnetic":
            losses = ", ".join(f"{entry['part']} {entry['W']:.4g} W" for entry in summary["losses"]) or "no conductor"
            lines.append(f"at {hertz(summary['frequency_Hz'])}: loss {summary['loss_W']:.4g} W ({losses}); densest eddy current "
                         f"{summary['max_eddy_current_A_mm2']:.4g} A/mm² at {summary['max_at_mm']} mm")
            lines.append(f"strongest field {summary['max_field_mT']:.4g} mT at {summary['max_field_at_mm']} mm")
            if "impedance" in summary:
                z = summary["impedance"]
                lines.append(f"impedance of {z['of']}: R {z['R_ohm']:.4g} ohm, L {z['L_uH']:.4g} µH (X {z['X_ohm']:.4g} ohm)")
            for skin in summary["skin"]:
                lines.append(f"skin depth in {skin['part']} {skin['depth_mm']:.3g} mm, its surface meshed at "
                             f"{skin['surface_mm']:.3g} mm" + ("" if skin["resolved"] else " (not resolved: the loss reads high)"))
            if "max_temperature_C" in summary:
                lines.append(f"hottest {summary['max_temperature_C']:g} °C, coolest {summary['min_temperature_C']:g} °C "
                             "from the induction heat")
        else:
            lines.append(f"strongest field {summary['max_field_mT']:.4g} mT at {summary['max_at_mm']} mm; "
                         f"stored energy {summary['energy_J']:.4g} J")
            if "inductance_uH" in summary:
                lines.append(f"inductance {summary['inductance_uH']:.6g} µH")
            for force in summary["forces"]:
                lines.append(f"force on {force['part']} ({force['by']}): {force['force_N']} N")
            if "structure" in summary:
                st = summary["structure"]
                lines.append(f"under the magnetic force on {st['part']}: peak von Mises {st['max_von_mises_MPa']:.4g} MPa, "
                             f"largest displacement {st['max_displacement_mm']:.4g} mm")
        for probe in summary.get("probes", ()):
            value = (f"{probe['magnetic_field_mT']:.4g} mT" if "magnetic_field_mT" in probe else
                     f"{probe['electric_field_kV_mm']:.4g} kV/mm, {probe['V']:.4g} V" if "electric_field_kV_mm" in probe else
                     f"{probe['current_density_A_mm2']:.4g} A/mm², {probe['V']:.4g} V" if "current_density_A_mm2" in probe else
                     "outside the mesh")
            lines.append(f"at {probe['label']} {probe['at_mm']} mm: {value}")
        return lines

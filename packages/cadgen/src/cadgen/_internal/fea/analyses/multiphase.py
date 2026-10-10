"""Two fluids (lite): a liquid and a gas inside the part, sloshing, filling, draining or a rising bubble, over time.

The study names the two fluids (``water`` and ``air`` by default, or each its
density and viscosity, and optionally the surface tension between them), how
the part is filled at the start (``fill``: a level above the inside's floor, a
share of its volume, a box of liquid or a bubble of gas), gravity, the part's
own acceleration over time (``acceleration``: a direction, a size in g and a
history, as a shaken or braking tank), optional ``inlets`` and ``outlets`` on
the part's open sides (as a flow study's), and how long to follow it
(``end_s``).

The liquid fills the part's inside (:mod:`..cavity`: the space it encloses,
open at most on the sides of its bounding box where it has an opening; an open
side nobody names is open to the air, at 0 Pa). The flow is
:mod:`..multiphase_ops`: Taylor-Hood Navier-Stokes with the density and
viscosity of whichever fluid is where, a level set for the interface, BDF2 in
time with CFL-limited steps, and the liquid's volume kept to round-off.

What comes out, over time, as a series of frames (up to the budget's frame
count, evenly spaced, plus the moments the liquid rises highest and presses
hardest): on the part's wetted faces, the ``water_fraction`` (1 where the
liquid touches the wall, 0 where the gas does) and the wall ``pressure``
(Pa); curves of the highest the liquid reaches, the height at each probe, the
force and moment the fluids put on the part, the largest wall pressure and
the liquid's volume; and in the summary their peaks and when. Checks:
``fill_level`` (the highest the liquid reaches, at probes or anywhere, against
``limit_mm`` above the inside's floor, the brim by default: "Spills over",
"Close to the brim", "Stays in") and ``wall_pressure``. With
``map_to_structure`` the wall pressure at the moment of the largest sloshing
force is applied to a static solve of the part (one-way), and its stress and
displacement join.

Its limits are written into every result: laminar (no turbulence model),
incompressible, the interface a few elements thick, no evaporation, boiling or
mixing. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext

__all__ = ["GASES", "LIQUIDS", "LIMITS", "MultiphaseAnalysis", "MultiphaseInputs", "fill_words", "sloshing_frequency"]

#: Fluids by name at 20 °C: density kg/m³, dynamic viscosity Pa·s.
LIQUIDS = {"water": (998.2, 1.002e-3), "oil": (870.0, 0.1), "glycerine": (1261.0, 1.41)}
GASES = {"air": (1.204, 1.81e-5)}
#: Water against air, N/m: what ``"surface_tension_N_m": "auto"`` means.
WATER_AIR_TENSION = 0.0728
LIMITS = ("Laminar (no turbulence model), incompressible; the interface is smeared over a few elements and the walls "
          "slide freely; no evaporation, boiling, mixing or foam.",)
G0 = 9.80665
FILL_KINDS = ("level_mm", "fraction", "box_mm", "bubble")
WALLS = ("slip", "no_slip")
OPENINGS = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
#: A check is close once its value passes this share of its limit.
CLOSE_AT = 0.9
#: Time steps per period of the first sloshing mode (auto), and with the adaptive_steps rung; the CFL number for each.
STEPS_PER_PERIOD, ADAPTIVE_STEPS_PER_PERIOD = 40.0, 20.0
CFL, ADAPTIVE_CFL = 0.5, 1.0
#: The run's steps at least this many (auto), and its default length in periods of the first sloshing mode.
MIN_STEPS, DEFAULT_PERIODS = 40, 3.0
#: The fluid's mesh by default: its diagonal over this, or half its narrowest extent, whichever is coarser.
ACROSS, NARROWEST = 20.0, 2.0
#: local_refine: away from the interface's band the mesh is this many times coarser; fluid_coarsen grows it by this.
BAND_COARSEN, COARSEN = 2.5, 1.6
#: The cost model (measured on this engine's sloshing tanks; a factor of three is what choosing a rung needs).
TETS_VOLUME, TETS_SURFACE, DOFS_PER_TET = 4.5, 2.0, 6.0
ASSEMBLE_S, LEVEL_SET_S, DIRECT_S, ITERATIVE_S, MESH_S = 6e-5, 1.2e-5, 1.4e-7, 3e-5, 2.5e-4
BYTES_PER_TET, FILL_BYTES, ITERATIVE_BYTES = 45_000.0, 40.0, 2_000.0


@dataclass(frozen=True)
class Fluid:
    name: str
    density_kg_m3: float
    viscosity_Pa_s: float


@dataclass(frozen=True)
class Opening:
    opening: str
    kind: str                       # "inlet" or "outlet"
    velocity_m_s: float = 0.0       # inlet: the speed in, along the side's inward normal
    fluid: str = "liquid"           # inlet: "liquid" or "gas"
    pressure_Pa: float = 0.0        # outlet


@dataclass(frozen=True)
class Probe:
    label: str
    at_mm: tuple[float, float, float]


@dataclass(frozen=True)
class MultiphaseInputs(Inputs):
    liquid: Fluid = Fluid("water", *LIQUIDS["water"])
    gas: Fluid = Fluid("air", *GASES["air"])
    surface_tension_N_m: float = 0.0
    fill: dict = field(default_factory=lambda: {"fraction": 0.5})
    gravity_m_s2: tuple[float, float, float] = (0.0, 0.0, -G0)
    #: The part's own acceleration: (unit direction, size in g, history) or None.
    acceleration: Any = None
    openings: tuple[Opening, ...] = ()
    end_s: float | None = None
    step_s: float | None = None
    walls: str = "slip"
    probes: tuple[Probe, ...] = ()
    fixtures: tuple = ()
    structure_material: Any = None

    @property
    def mapped(self) -> bool:
        return self.structure_material is not None


def sloshing_frequency(length_m: float, depth_m: float, g: float) -> float:
    """The first sloshing mode of a rectangular tank by linear theory, Hz: omega^2 = g k tanh(k h), k = pi / L."""
    if not (length_m > 0 and depth_m > 0 and g > 0):
        return 0.0
    k = math.pi / length_m
    return math.sqrt(g * k * math.tanh(k * depth_m)) / (2.0 * math.pi)


def fill_words(fraction: float | None, liquid: str) -> str:
    """"Half full of water", "A quarter full of oil", "40 % full of water"."""
    if fraction is None:
        return f"Partly {liquid}"
    named = {0.25: "A quarter full", 0.5: "Half full", 0.75: "Three quarters full", 1.0: "Full"}
    for share, words in named.items():
        if abs(fraction - share) < 0.02:
            return f"{words} of {liquid}"
    return f"{round(100 * fraction):.0f} % full of {liquid}"


# -- parse --------------------------------------------------------------------------------------------


def _known(entry: dict, keys: set[str], where: str, words: str) -> None:
    unknown = set(entry) - keys
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; {words}")


def _fluid(raw: Any, table: dict, where: str, example: str) -> Fluid:
    if isinstance(raw, str):
        if raw not in table:
            raise ValueError(f"{where}: {kinds.json_text(raw)} is not one cadgen knows; use {', '.join(map(kinds.json_text, table))} "
                             f"or {{\"density_kg_m3\", \"viscosity_Pa_s\"}}")
        return Fluid(raw, *table[raw])
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: a name like {example} or {{\"density_kg_m3\": 1000, \"viscosity_Pa_s\": 0.001}}")
    _known(raw, {"name", "density_kg_m3", "viscosity_Pa_s"}, where, "a fluid takes density_kg_m3, viscosity_Pa_s and a name")
    for key in ("density_kg_m3", "viscosity_Pa_s"):
        if key not in raw:
            raise ValueError(f"{where}.{key}: a fluid object needs density_kg_m3 and viscosity_Pa_s")
    name = raw.get("name", "fluid")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{where}.name: expected a short piece of text")
    return Fluid(name.strip(), kinds.number(raw["density_kg_m3"], where=f"{where}.density_kg_m3", positive=True),
                 kinds.number(raw["viscosity_Pa_s"], where=f"{where}.viscosity_Pa_s", positive=True))


def _vector(raw: Any, where: str, words: str) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError(f"{where}: {words}")
    return tuple(kinds.number(c, where=where) for c in raw)  # type: ignore[return-value]


def _fill(raw: Any) -> dict:
    example = '{"fraction": 0.5}, {"level_mm": 25}, {"box_mm": [[0, 0, 0], [20, 10, 40]]} or {"bubble": {"center_mm": [30, 5, 10], "radius_mm": 5}}'
    if raw is None:
        return {"fraction": 0.5}
    if not isinstance(raw, dict) or len(raw) != 1 or next(iter(raw)) not in FILL_KINDS:
        raise ValueError(f"fill: how the liquid starts, exactly one of {list(FILL_KINDS)}, like {example}")
    kind, value = next(iter(raw.items()))
    if kind == "level_mm":
        return {"level_mm": kinds.number(value, where="fill.level_mm", positive=True)}
    if kind == "fraction":
        share = kinds.number(value, where="fill.fraction", positive=True)
        if share > 1:
            raise ValueError(f"fill.fraction: the share of the inside the liquid fills, 0 to 1, got {share:g}")
        return {"fraction": share}
    if kind == "box_mm":
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("fill.box_mm: the liquid's box as [[x0, y0, z0], [x1, y1, z1]] in mm")
        low = _vector(value[0], "fill.box_mm[0]", "a corner as [x, y, z] in mm")
        high = _vector(value[1], "fill.box_mm[1]", "a corner as [x, y, z] in mm")
        if not all(h > l for l, h in zip(low, high)):
            raise ValueError("fill.box_mm: the second corner must be above the first on every axis")
        return {"box_mm": [list(low), list(high)]}
    if not isinstance(value, dict):
        raise ValueError('fill.bubble: {"center_mm": [x, y, z], "radius_mm": r}, a bubble of gas in a full part')
    _known(value, {"center_mm", "radius_mm"}, "fill.bubble", "a bubble takes center_mm and radius_mm")
    if "center_mm" not in value or "radius_mm" not in value:
        raise ValueError("fill.bubble: give center_mm and radius_mm")
    return {"bubble": {"center_mm": list(_vector(value["center_mm"], "fill.bubble.center_mm", "the centre as [x, y, z] in mm")),
                       "radius_mm": kinds.number(value["radius_mm"], where="fill.bubble.radius_mm", positive=True)}}


def _history(raw: Any, where: str):
    """A history (``transient``'s: a table or a step, ramp or half-sine shape), or ``{"shape": "sine", "frequency_Hz"}``."""
    from cadgen._internal.fea.analyses.transient import History, parse_time_history

    if raw is None:
        return History("step")
    if isinstance(raw, dict) and raw.get("shape") == "sine":
        _known(raw, {"shape", "frequency_Hz"}, where, "a sine takes shape and frequency_Hz")
        if "frequency_Hz" not in raw:
            raise ValueError(f"{where}.frequency_Hz: how fast it shakes back and forth, Hz")
        return ("sine", kinds.number(raw["frequency_Hz"], where=f"{where}.frequency_Hz", positive=True))
    return parse_time_history(raw, where)


def history_value(history, t: float) -> float:
    if isinstance(history, tuple):
        return math.sin(2.0 * math.pi * history[1] * t)
    return history.value(t)


def history_echo(history):
    if isinstance(history, tuple):
        return {"shape": "sine", "frequency_Hz": history[1]}
    return history.echo()


def history_words(history) -> str:
    if isinstance(history, tuple):
        return f"sine at {history[1]:g} Hz"
    return history.words()


def _acceleration(raw: Any):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError('acceleration: the part\'s own acceleration, like {"direction": [1, 0, 0], "amplitude_g": 0.3, '
                         '"history": {"shape": "half_sine", "duration_s": 0.2}}')
    _known(raw, {"direction", "amplitude_g", "history"}, "acceleration", "it takes direction, amplitude_g and history")
    if "direction" not in raw or "amplitude_g" not in raw:
        raise ValueError("acceleration: give direction ([x, y, z]) and amplitude_g")
    direction = _vector(raw["direction"], "acceleration.direction", "the direction as [x, y, z], like [1, 0, 0]")
    size = math.sqrt(sum(c * c for c in direction))
    if not size > 0:
        raise ValueError("acceleration.direction: the direction is zero; give it, like [1, 0, 0]")
    amplitude = kinds.number(raw["amplitude_g"], where="acceleration.amplitude_g")
    return (tuple(c / size for c in direction), amplitude, _history(raw.get("history"), "acceleration.history"))


def _openings(document: dict) -> tuple[Opening, ...]:
    out = []
    for key, kind in (("inlets", "inlet"), ("outlets", "outlet")):
        raw = document.get(key)
        if raw is None:
            continue
        if not isinstance(raw, list) or not all(isinstance(entry, dict) for entry in raw):
            raise ValueError(f"{key}: a list like [{{\"opening\": \"z_max\", ...}}]")
        for index, entry in enumerate(raw):
            where = f"{key}[{index}]"
            opening = entry.get("opening")
            if opening not in OPENINGS:
                raise ValueError(f"{where}.opening: {kinds.json_text(opening)} is not a side of the part's bounding box; "
                                 f"use one of {list(OPENINGS)}")
            if kind == "inlet":
                _known(entry, {"opening", "velocity_m_s", "fluid"}, where, "an inlet takes opening, velocity_m_s and fluid")
                if "velocity_m_s" not in entry:
                    raise ValueError(f"{where}.velocity_m_s: the speed the fluid comes in at, m/s")
                fluid = entry.get("fluid", "liquid")
                if fluid not in ("liquid", "gas"):
                    raise ValueError(f"{where}.fluid: \"liquid\" or \"gas\", the fluid it brings in")
                out.append(Opening(opening, "inlet", kinds.number(entry["velocity_m_s"], where=f"{where}.velocity_m_s", positive=True),
                                   fluid))
            else:
                _known(entry, {"opening", "pressure_Pa"}, where, "an outlet takes opening and pressure_Pa")
                out.append(Opening(opening, "outlet", pressure_Pa=kinds.number(entry.get("pressure_Pa", 0.0), where=f"{where}.pressure_Pa")))
    named = [o.opening for o in out]
    for opening in named:
        if named.count(opening) > 1:
            raise ValueError(f"inlets/outlets: {opening} is named twice; each open side is one inlet or one outlet")
    return tuple(out)


def _probes(raw: Any) -> tuple[Probe, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(entry, dict) for entry in raw):
        raise ValueError('probes: a list like [{"label": "left wall", "at_mm": [5, 5, 0]}], each a vertical line through its point')
    out = []
    for index, entry in enumerate(raw):
        where = f"probes[{index}]"
        _known(entry, {"label", "at_mm"}, where, "a probe takes label and at_mm")
        label = entry.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{where}.label: a short name for it, like \"left wall\"")
        if "at_mm" not in entry:
            raise ValueError(f"{where}.at_mm: a point on its vertical line, [x, y, z] in mm")
        out.append(Probe(label.strip(), _vector(entry["at_mm"], f"{where}.at_mm", "a point as [x, y, z] in mm")))
    labels = [p.label for p in out]
    if len(set(labels)) != len(labels):
        raise ValueError("probes: each label once")
    return tuple(out)


# -- the analysis -------------------------------------------------------------------------------------


@dataclass
class _Setup:
    """The inside and its numbers: what the ladder estimates from and the solve starts from."""

    domain: Any
    up: tuple[float, float, float]
    floor_mm: float                 # the inside's lowest point along up
    height_mm: float                # the inside's height along up (the brim is floor + height)
    level_mm: float | None          # the starting fill level above the floor (a level or a share)
    fraction: float | None          # the share of the inside filled at the start
    length_mm: float                # the inside's length along the shake (or its longest level extent)
    period_s: float                 # the first sloshing mode's period by linear theory (inf when not sloshing)
    size_mm: float                  # the fluid mesh's default size
    area_mm2: float


class MultiphaseAnalysis:
    name: ClassVar[str] = "multiphase"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Two fluids"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "fluids", "fill", "gravity_m_s2", "acceleration", "inlets", "outlets", "end_s", "step_s", "walls", "probes",
        "map_to_structure",
    })
    material_needs: ClassVar[frozenset[str]] = frozenset()
    #: The material is the structure's, and only a mapped study has one (study.parse_study reads this).
    material_required: ClassVar[bool] = False
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("water_fraction", "_WATER_FRACTION", "water fraction", "", per_frame=True),
        FieldSpec("pressure", "_PRESSURE", "wall pressure", "Pa", signed=True, per_frame=True),
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = (kinds.FILL_LEVEL, kinds.WALL_PRESSURE, kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "frame", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "field": {"drives": "field", "type": "enum", "options": ["water_fraction", "pressure"]},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("adaptive_steps", "iterative", "local_refine", "fluid_coarsen")
    noun: ClassVar[str] = "this shake"

    def __init__(self):
        self._setups: dict[tuple, _Setup] = {}

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> MultiphaseInputs:
        from cadgen._internal.fea.materials import material_from_spec
        from cadgen._internal.fea.study import parse_fixtures

        fluids = document.get("fluids") or {}
        if not isinstance(fluids, dict):
            raise ValueError('fluids: the two fluids, like {"liquid": "water", "gas": "air", "surface_tension_N_m": 0.072}')
        _known(fluids, {"liquid", "gas", "surface_tension_N_m"}, "fluids", "it takes liquid, gas and surface_tension_N_m")
        liquid = _fluid(fluids.get("liquid", "water"), LIQUIDS, "fluids.liquid", '"water"')
        gas = _fluid(fluids.get("gas", "air"), GASES, "fluids.gas", '"air"')
        if not liquid.density_kg_m3 > gas.density_kg_m3:
            raise ValueError(f"fluids: the liquid ({liquid.density_kg_m3:g} kg/m³) must be denser than the gas "
                             f"({gas.density_kg_m3:g} kg/m³); name the heavier fluid the liquid")
        tension = fluids.get("surface_tension_N_m", 0.0)
        if tension == "auto":
            tension = WATER_AIR_TENSION if (liquid.name, gas.name) == ("water", "air") else None
            if tension is None:
                raise ValueError("fluids.surface_tension_N_m: \"auto\" knows water against air only; give the number, N/m")
        sigma = 0.0 if tension in (None, 0, 0.0) else kinds.number(tension, where="fluids.surface_tension_N_m", positive=True)
        gravity = (0.0, 0.0, -G0)
        if "gravity_m_s2" in document:
            gravity = _vector(document["gravity_m_s2"], "gravity_m_s2", "gravity as [x, y, z] in m/s², like [0, 0, -9.81]")
            if not any(gravity):
                raise ValueError("gravity_m_s2: with no gravity the liquid has no level; give it, like [0, 0, -9.81]")
        end = document.get("end_s")
        end_s = None if end is None else kinds.number(end, where="end_s", positive=True)
        step = document.get("step_s", "auto")
        step_s = None if step == "auto" else kinds.number(step, where="step_s", positive=True)
        walls = document.get("walls", "slip")
        if walls not in WALLS:
            raise ValueError(f"walls: {kinds.json_text(walls)} is not \"slip\" (the fluid slides along the walls, the default) "
                             "or \"no_slip\" (it sticks to them)")
        mapping = document.get("map_to_structure")
        fixtures: tuple = ()
        material = None
        if mapping is not None:
            if not isinstance(mapping, dict):
                raise ValueError('map_to_structure: expected an object like {"material": "aluminum-6061-t6", '
                                 '"fixtures": [{"faces": ["#o1.f1"]}]}')
            _known(mapping, {"material", "fixtures"}, "map_to_structure",
                   "it takes the part's material and its fixtures (where it is held while the fluids push on it)")
            spec = mapping.get("material", document.get("material"))
            if spec is None:
                raise ValueError("map_to_structure.material: the part's material, to solve its stress under the fluids' pressure")
            material = material_from_spec(spec)
            try:
                fixtures = parse_fixtures(mapping)
            except ValueError as exc:
                raise ValueError(f"map_to_structure.{exc}") from None
        view = document.get("view")
        checks = view.get("checks") if isinstance(view, dict) else None
        if material is None and isinstance(checks, list):
            for index, check in enumerate(checks):
                if isinstance(check, dict) and check.get("kind") in ("stress", "displacement"):
                    raise ValueError(f"view.checks[{index}]: a {check['kind']} check needs the fluids' pressure on the part: "
                                     "add map_to_structure with the part's material and fixtures")
        refs = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        return MultiphaseInputs(
            refs, refs, material is not None, liquid=liquid, gas=gas, surface_tension_N_m=sigma, fill=_fill(document.get("fill")),
            gravity_m_s2=gravity, acceleration=_acceleration(document.get("acceleration")), openings=_openings(document),
            end_s=end_s, step_s=step_s, walls=walls, probes=_probes(document.get("probes")), fixtures=fixtures,
            structure_material=material,
        )

    # -- the inside and its numbers ------------------------------------------------------------------

    def _setup(self, ctx: SolveContext, inputs: MultiphaseInputs) -> _Setup:
        geometry = ctx.geometry
        shape = getattr(geometry, "shape", None)
        if ctx.assembly is not None or shape is None:
            raise ValueError("a two-fluid study fills one part: name it with --occurrence (#o1.2)")
        key = (id(shape), id(inputs))
        if key in self._setups:
            return self._setups[key]
        from cadgen._internal.fea import cavity

        refs = {face.ordinal: face.ref for face in geometry.faces}
        domain = cavity.build_cavity(shape, refs=refs)
        named = {o.opening for o in inputs.openings}
        have = {face.opening for face in domain.faces if face.kind == "opening"}
        if missing := sorted(named - have):
            raise ValueError(f"inlets/outlets: the part's inside has no opening on {', '.join(missing)}; "
                             f"its open sides are {', '.join(sorted(have)) or 'none (it is sealed)'}")
        vents = (have - named) | {o.opening for o in inputs.openings if o.kind == "outlet"}
        if any(o.kind == "inlet" for o in inputs.openings) and not vents:
            raise ValueError("inlets: fluid coming in needs a way for what it pushes out to leave: name an outlet "
                             "(or leave an open side unnamed: it is open to the air)")
        g = math.sqrt(sum(c * c for c in inputs.gravity_m_s2))
        up = tuple(-c / g for c in inputs.gravity_m_s2)
        corners = [(x, y, z) for x in (domain.box[0][0], domain.box[1][0]) for y in (domain.box[0][1], domain.box[1][1])
                   for z in (domain.box[0][2], domain.box[1][2])]
        heights = [sum(u * c for u, c in zip(up, corner)) for corner in corners]
        floor, height = min(heights), max(heights) - min(heights)
        extents = [h - l for l, h in zip(*domain.box)]
        # The sloshing length: along the shake's level part, else the longest level extent.
        if inputs.acceleration is not None:
            direction = inputs.acceleration[0]
            level = [d - sum(a * b for a, b in zip(direction, up)) * u for d, u in zip(direction, up)]
            norm = math.sqrt(sum(c * c for c in level)) or 1.0
            length = sum(abs(c / norm) * e for c, e in zip(level, extents))
        else:
            length = max(e for e, u in zip(extents, up) if abs(u) < 0.9) if any(abs(u) < 0.9 for u in up) else max(extents)
        fill = inputs.fill
        level_mm, fraction = None, None
        if "level_mm" in fill:
            level_mm = min(fill["level_mm"], height)
            fraction = level_mm / height if height > 0 else None      # exact for a prism; the solve measures it
        elif "fraction" in fill:
            fraction = fill["fraction"]
            level_mm = fraction * height
        depth = (level_mm or 0.0) * 1e-3
        frequency = sloshing_frequency(length * 1e-3, depth, g) if level_mm else 0.0
        period = 1.0 / frequency if frequency > 0 else math.inf
        size = max(math.sqrt(sum(e * e for e in extents)) / ACROSS, min(extents) / NARROWEST)
        area = sum(face.area for face in domain.faces)
        setup = _Setup(domain, up, floor, height, level_mm, fraction, length, period, size, area)
        if len(self._setups) > 4:
            self._setups.clear()
        self._setups[key] = setup
        return setup

    def sizes(self, ctx: SolveContext, setup: _Setup) -> tuple[float, float]:
        """(fine, away) fluid element sizes, mm: the study's size (or the default), and away from the interface's band."""
        plan = ctx.plan
        fine = float(plan.size_mm) if plan is not None and plan.size_mm else setup.size_mm
        away = plan.fluid_far_size_mm if plan is not None and plan.fluid_far_size_mm else fine
        return fine, max(away, fine)

    def _end(self, inputs: MultiphaseInputs, setup: _Setup) -> float:
        if inputs.end_s is not None:
            return inputs.end_s
        if math.isfinite(setup.period_s):
            return DEFAULT_PERIODS * setup.period_s
        return 1.0

    def _step(self, inputs: MultiphaseInputs, setup: _Setup, plan) -> float:
        """The largest step: the study's, else a fortieth of the sloshing period (twentieth adapted), at most the run over 40."""
        end = self._end(inputs, setup)
        if inputs.step_s is not None:
            return min(inputs.step_s, end)
        per = ADAPTIVE_STEPS_PER_PERIOD if plan is not None and plan.adaptive_steps else STEPS_PER_PERIOD
        step = end / MIN_STEPS
        if math.isfinite(setup.period_s):
            step = min(step, setup.period_s / per)
        return step

    def _band(self, ctx: SolveContext, inputs: MultiphaseInputs, setup: _Setup) -> tuple[float, float] | None:
        """The heights (above the floor, mm) the free surface sweeps: its level plus or minus how far it may move."""
        if setup.level_mm is None or inputs.openings:
            return None
        # Fixed by the study (not by the plan), so the band a step names is the band that is meshed.
        requested = ctx.plan.requested_mm if ctx.plan is not None and ctx.plan.requested_mm else setup.size_mm
        g = math.sqrt(sum(c * c for c in inputs.gravity_m_s2))
        shake = 0.0 if inputs.acceleration is None else abs(inputs.acceleration[1]) * G0 / g
        sweep = min(setup.height_mm, 1.5 * shake * setup.length_mm + 2.0 * min(requested, setup.size_mm))
        low, high = max(0.0, setup.level_mm - sweep), min(setup.height_mm, setup.level_mm + sweep)
        if high - low > 0.6 * setup.height_mm:
            return None
        return low, high

    # -- the ladder ----------------------------------------------------------------------------------

    def _tets(self, ctx: SolveContext, inputs: MultiphaseInputs, setup: _Setup) -> float:
        fine, away = self.sizes(ctx, setup)
        volume, area = setup.domain.volume_mm3, setup.area_mm2
        if "local_refine" in ctx.plan.taken and away > fine:
            band = self._band(ctx, inputs, setup)
            share = (band[1] - band[0]) / setup.height_mm if band and setup.height_mm else 1.0
            return TETS_VOLUME * volume * (share / fine ** 3 + (1.0 - share) / away ** 3) + TETS_SURFACE * area / away ** 2
        return TETS_VOLUME * volume / fine ** 3 + TETS_SURFACE * area / fine ** 2

    def estimate(self, ctx: SolveContext, inputs: MultiphaseInputs):
        from cadgen._internal.fea import fit

        setup = self._setup(ctx, inputs)
        plan = ctx.plan
        tets = self._tets(ctx, inputs, setup)
        n = DOFS_PER_TET * tets
        steps = 1.3 * self._end(inputs, setup) / self._step(inputs, setup, plan)
        if plan.solver == "iterative":
            per, memory = ITERATIVE_S * n, ITERATIVE_BYTES * n
        else:
            per, memory = DIRECT_S * n ** 1.5, FILL_BYTES * n ** 1.5
        seconds = MESH_S * tets + steps * (per + (ASSEMBLE_S + LEVEL_SET_S) * tets)
        memory += BYTES_PER_TET * tets
        if inputs.mapped:
            structure = fit.solid_estimate(ctx)
            memory = max(memory, structure.memory_bytes - fit.BASE_BYTES)
            seconds += structure.seconds
        return fit.Estimate(dofs=int(n), memory_bytes=int(fit.BASE_BYTES + memory), seconds=float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: MultiphaseInputs):
        from cadgen._internal.fea import fit

        plan, budget = ctx.plan, ctx.budget
        setup = self._setup(ctx, inputs)
        before = self.estimate(ctx, inputs)
        if rung == "adaptive_steps":
            if plan.adaptive_steps or inputs.step_s is not None:
                return None
            plan.adaptive_steps = True
            after = self.estimate(ctx, inputs)
            if after.seconds > 0.95 * before.seconds:
                plan.adaptive_steps = False
                return None
            words = ("Let the time step grow with the flow to finish sooner: at most a twentieth of the first sloshing period, "
                     "the fastest fluid crossing at most one element a step")
            return fit.Step("adaptive_steps", words,
                            "BDF2 at 20 steps a period reads the sloshing period about 3% long, against 0.8% at the default 40",
                            2.2,
                            detail={"cfl": ADAPTIVE_CFL, "steps_per_period": ADAPTIVE_STEPS_PER_PERIOD})
        if rung == "iterative":
            if plan.solver != "direct":
                return None
            plan.solver = "iterative"
            after = self.estimate(ctx, inputs)
            memory = before.memory_bytes > budget.memory_bytes
            saves = after.memory_bytes < 0.95 * before.memory_bytes if memory else after.seconds < 0.95 * before.seconds
            if not saves:
                plan.solver = "direct"
                return None
            why = "fit in memory" if memory else "finish sooner"
            return fit.Step("iterative", f"Used an iterative two-fluid solver (Krylov with multigrid) to {why}", None, None,
                            detail={"solver": "iterative", "from_bytes": int(before.memory_bytes), "to_bytes": int(after.memory_bytes)})
        if rung == "local_refine":
            band = self._band(ctx, inputs, setup)
            fine, away = self.sizes(ctx, setup)
            if band is None or "local_refine" in plan.taken or away > fine:
                return None
            saved = plan.fluid_far_size_mm
            plan.fluid_far_size_mm = BAND_COARSEN * fine
            plan.taken.append("local_refine")             # the estimate reads it; fit_budget appends it again below
            after = self.estimate(ctx, inputs)
            plan.taken.remove("local_refine")
            if after.seconds > 0.95 * before.seconds and after.memory_bytes > 0.95 * before.memory_bytes:
                plan.fluid_far_size_mm = saved
                return None
            return fit.Step(
                "local_refine",
                f"Meshed the fluid finely ({fine:.3g} mm) only where its surface moves, {band[0]:.3g} to {band[1]:.3g} mm "
                f"above the floor, and at {BAND_COARSEN * fine:.3g} mm above and below",
                None, None, detail={"fine_mm": round(fine, 4), "away_mm": round(BAND_COARSEN * fine, 4),
                                    "band_mm": [round(band[0], 3), round(band[1], 3)]})
        if rung == "fluid_coarsen":
            fine, away = self.sizes(ctx, setup)
            extents = [h - l for l, h in zip(*setup.domain.box)]
            coarser = min(COARSEN * fine, min(extents) / 2.0) if min(extents) / 2.0 > fine else COARSEN * fine
            if coarser <= 1.05 * fine:
                return None
            saved_size, saved_far = plan.size_mm, plan.fluid_far_size_mm
            plan.size_mm = coarser
            if plan.fluid_far_size_mm:
                plan.fluid_far_size_mm = max(plan.fluid_far_size_mm, BAND_COARSEN * coarser)
            after = self.estimate(ctx, inputs)
            if after.seconds > 0.95 * before.seconds and after.memory_bytes > 0.95 * before.memory_bytes:
                plan.size_mm, plan.fluid_far_size_mm = saved_size, saved_far
                return None
            far = f" ({plan.fluid_far_size_mm:.3g} mm away from its surface)" if "local_refine" in plan.taken else ""
            return fit.Step(
                "fluid_coarsen", f"Coarsened the fluid mesh from {fine:.3g} mm to {coarser:.3g} mm{far} to fit",
                f"the free surface is smeared over about {2.0 * coarser:.2g} mm; sloshing periods may read a few percent long",
                None, detail={"from_mm": round(fine, 4), "to_mm": round(coarser, 4)})
        return None

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: MultiphaseInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import cavity, multiphase_ops as ops
        from cadgen._internal.fea.analyses.modal import max_frames

        timings: dict[str, float] = {}
        setup = self._setup(ctx, inputs)
        domain = setup.domain
        timings["cavity_s"] = domain.seconds
        fine, away = self.sizes(ctx, setup)
        band = self._band(ctx, inputs, setup) if "local_refine" in ctx.plan.taken and away > fine else None
        started = time.perf_counter()
        size_field = None
        if band is not None:
            size_field = self._band_field(setup, band, fine)
        if ctx.log:
            ctx.log(f"meshing the part's inside at {fine:.3g} mm" + (f" ({away:.3g} mm away from the surface)" if size_field else ""))
        volume = cavity.mesh_cavity(domain, away if size_field else fine, band=size_field)
        mesh, (facets, facet_face) = cavity.skfem_mesh(volume)
        timings["fluid_mesh_s"] = time.perf_counter() - started

        up = np.array(setup.up)
        face_of = {face.index: face for face in domain.faces}
        kind_of = np.array([face_of[int(f)].kind if int(f) in face_of else "wall" for f in facet_face], dtype=object)
        side_of = np.array([face_of[int(f)].opening if int(f) in face_of else None for f in facet_face], dtype=object)
        openings = []
        named = {o.opening: o for o in inputs.openings}
        for side in sorted({s for s in side_of if s}):
            rows = facets[(kind_of == "opening") & (side_of == side)]
            entry = named.get(side)
            if entry is not None and entry.kind == "inlet":
                axis, high = "xyz".index(side[0]), side.endswith("max")
                velocity = np.zeros(3)
                velocity[axis] = (-1.0 if high else 1.0) * entry.velocity_m_s
                openings.append(ops.Opening(rows, "inlet", velocity=velocity, phase=1.0 if entry.fluid == "liquid" else 0.0))
            else:
                # An outlet, or an open side nobody named: open to the air at its pressure (0 Pa).
                openings.append(ops.Opening(rows, "outlet", pressure=entry.pressure_Pa if entry is not None else 0.0))
        noslip = facets[kind_of == "wall"] if inputs.walls == "no_slip" else None

        distance = self._initial_distance(mesh, inputs, setup)
        g = np.array(inputs.gravity_m_s2, dtype=float)
        acceleration = None
        if inputs.acceleration is not None:
            direction, amplitude, history = inputs.acceleration
            vector = np.array(direction) * amplitude * G0

            def acceleration(t, vector=vector, history=history):
                return vector * history_value(history, t)

        phases = ops.Phases(inputs.liquid.density_kg_m3, inputs.gas.density_kg_m3, inputs.liquid.viscosity_Pa_s,
                            inputs.gas.viscosity_Pa_s, inputs.surface_tension_N_m)
        problem = ops.TwoPhaseProblem(mesh, phases, distance, g, acceleration=acceleration, noslip=noslip, openings=openings)
        solver = "iterative" if ctx.plan.solver == "iterative" else "direct"
        march = ops.TwoPhaseSolver(problem, solver=solver, cfl=ADAPTIVE_CFL if ctx.plan.adaptive_steps else CFL, log=ctx.log)
        if "fraction" in inputs.fill:
            total = float(np.asarray(march.pbasis.dx).sum())
            march.set_level_set(march.keep_volume(distance, inputs.fill["fraction"] * total))
        timings["setup_s"] = time.perf_counter() - started - timings["fluid_mesh_s"]

        # What is read every step: the part's wetted nodes from the fluid's wall corners, the probes, the force.
        part_nodes, fluid_nodes = self._wall_map(ctx, mesh, facets, facet_face, kind_of, face_of)
        floor_m = setup.floor_mm * 1e-3
        probes = self._probe_lines(inputs, setup, march, fine)
        centre = np.array([0.5 * (l + h) for l, h in zip(*domain.box)]) * 1e-3
        centre = centre - (centre @ up - floor_m) * up                 # on the floor, below the inside's middle
        end = self._end(inputs, setup)
        frames_wanted = max(max_frames(ctx), 4)
        even = list(np.linspace(0.0, end, max(frames_wanted - 2, 2)))
        stops = even[1:-1]
        record: dict[str, Any] = {"t": [], "level": [], "force": [], "moment": [], "pmax": [], "volume": [], "speed": [],
                                  "probes": {p["label"]: [] for p in probes}, "frames": {}, "peaks": {}}
        wall_corners = np.unique(mesh.facets[:, march.wall_facets])
        part_count = ctx.space.scalar_count

        def on_part(values):
            out = np.zeros(part_count)
            out[part_nodes] = values[fluid_nodes]
            return out

        def snapshot(state):
            return {"t": state.t, "share": on_part(state.share), "pressure": on_part(state.p)}

        def on_step(state):
            heights = ops.interface_heights(mesh, state.distance, up)
            level = (float(heights.max()) - floor_m) * 1e3 if len(heights) else (setup.height_mm if state.share.min() > 0.5 else 0.0)
            force, moment = march.wall_force(state.p, about=centre)
            pmax = float(state.p[wall_corners].max()) if len(wall_corners) else 0.0
            record["t"].append(state.t)
            record["level"].append(level)
            record["force"].append(force)
            record["moment"].append(moment)
            record["pmax"].append(pmax)
            record["volume"].append(state.volume)
            record["speed"].append(state.max_speed)
            for probe in probes:
                record["probes"][probe["label"]].append(self._probe_height(probe, state.distance))
            if any(abs(state.t - s) <= 1e-9 * max(end, 1.0) for s in even) or state.step == 0:
                record["frames"][round(state.t, 12)] = snapshot(state)
            # The moments to keep beside the even frames: the highest level, the hardest press and the largest slosh.
            drift = np.linalg.norm(force - record["force"][0]) if record["force"] else 0.0
            for key, value in (("level", level), ("pressure", pmax), ("force", float(drift))):
                best = record["peaks"].get(key)
                if state.step > 0 and (best is None or value > best[0]):
                    record["peaks"][key] = (value, snapshot(state))

        started = time.perf_counter()
        dt_max = self._step(inputs, setup, ctx.plan)
        if ctx.log:
            ctx.log(f"two fluids: {len(mesh.t.T)} tets, {march.n} unknowns, up to {end:g} s in steps of at most {dt_max:.3g} s")
        march.run(end, dt_max=dt_max, stops=stops, on_step=on_step)
        timings["march_s"] = time.perf_counter() - started
        timings.update({f"march_{k}": v for k, v in march.timings.items()})
        return self._result(ctx, inputs, setup, march, mesh, volume, record, timings, fine, away, size_field, probes)

    def _band_field(self, setup: _Setup, band: tuple[float, float], fine: float) -> dict:
        """netgen local sizes: points on a grid through the band, each holding the fine size within its reach."""
        import numpy as np

        low, high = (np.array(corner) for corner in setup.domain.box)
        up = np.array(setup.up)
        spacing = 2.0 * fine
        axes = [np.arange(l + 0.5 * spacing, h, spacing) if h - l > spacing else np.array([0.5 * (l + h)])
                for l, h in zip(low, high)]
        grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
        height = grid @ up - setup.floor_mm
        keep = grid[(height >= band[0] - fine) & (height <= band[1] + fine)]
        if len(keep) > 4000:
            keep = keep[np.linspace(0, len(keep) - 1, 4000).astype(int)]
        return {"points": [[*map(float, p), float(fine)] for p in keep], "radius_mm": float(fine)}

    def _initial_distance(self, mesh, inputs: MultiphaseInputs, setup: _Setup):
        """The signed distance to the starting interface at the fluid mesh's corners, m (positive in the liquid)."""
        import numpy as np

        x = mesh.p
        up = np.array(setup.up)
        fill = inputs.fill
        if "box_mm" in fill:
            low, high = (np.array(c)[:, None] * 1e-3 for c in fill["box_mm"])
            q = np.maximum(low - x, x - high)
            outside = np.linalg.norm(np.maximum(q, 0.0), axis=0)
            return -(outside + np.minimum(q.max(axis=0), 0.0))
        if "bubble" in fill:
            centre = np.array(fill["bubble"]["center_mm"])[:, None] * 1e-3
            return np.linalg.norm(x - centre, axis=0) - fill["bubble"]["radius_mm"] * 1e-3
        level = (setup.floor_mm + (setup.level_mm or 0.0)) * 1e-3
        return level - up @ x

    def _wall_map(self, ctx, mesh, facets, facet_face, kind_of, face_of):
        """(part surface nodes, fluid corners): each wetted part node and the nearest fluid wall corner on its face."""
        import numpy as np
        from scipy.spatial import cKDTree

        part_space, volume = ctx.space, ctx.volume
        locations = part_space.dof_locations
        ordinal_of_facet = np.array([face_of[int(f)].ordinal if int(f) in face_of else 0 for f in facet_face])
        part_nodes, fluid_nodes = [], []
        for ordinal in sorted(set(int(o) for o in ordinal_of_facet[kind_of == "wall"]) - {0}):
            corners = np.unique(mesh.facets[:, facets[(kind_of == "wall") & (ordinal_of_facet == ordinal)]])
            target = np.unique(part_space.boundary_quadratic[volume.boundary_ordinal == ordinal])
            if len(corners) == 0 or len(target) == 0:
                continue
            _, nearest = cKDTree(mesh.p[:, corners].T * 1e3).query(locations[target])
            part_nodes.append(target)
            fluid_nodes.append(corners[nearest])
        if not part_nodes:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        return np.concatenate(part_nodes), np.concatenate(fluid_nodes)

    def _probe_lines(self, inputs: MultiphaseInputs, setup: _Setup, march, fine: float) -> list[dict]:
        """Each probe's vertical line, sampled inside the fluid: a matrix to the level set there and the heights."""
        import numpy as np

        up = np.array(setup.up)
        lines = []
        given = [(p.label, np.array(p.at_mm)) for p in inputs.probes]
        if not given and setup.level_mm is not None:
            # Default: the two walls along the shake (or the longest level extent), inset half an element, mid-width.
            low, high = (np.array(c) for c in setup.domain.box)
            mid = 0.5 * (low + high)
            if inputs.acceleration is not None:
                direction = np.array(inputs.acceleration[0])
                direction = direction - (direction @ up) * up
            else:
                extents = (high - low) * (1.0 - np.abs(up))
                direction = np.eye(3)[int(np.argmax(extents))]
            norm = np.linalg.norm(direction)
            if norm > 0:
                direction = direction / norm
                reach = 0.5 * float(np.abs(direction) @ (high - low)) - 0.5 * fine
                given = [("wall ahead", mid + reach * direction), ("wall behind", mid - reach * direction)]
        steps = max(int(setup.height_mm / (0.25 * fine)), 8)
        for label, point in given:
            base = point - (point @ up - setup.floor_mm) * up
            heights = np.linspace(0.0, setup.height_mm, steps + 1)
            points = (base[:, None] + up[:, None] * heights[None]) * 1e-3
            matrix, inside = march.at_points(points)
            lines.append({"label": label, "at_mm": [round(float(c), 4) for c in point], "matrix": matrix[inside],
                          "heights": heights[inside]})
        return lines

    @staticmethod
    def _probe_height(probe: dict, distance) -> float:
        """The liquid's top along a probe's line, mm above the floor: the highest crossing from liquid to gas."""
        import numpy as np

        d = probe["matrix"] @ distance
        z = probe["heights"]
        if len(d) == 0:
            return 0.0
        cross = np.flatnonzero((d[:-1] > 0) & (d[1:] <= 0))
        if len(cross) == 0:
            return float(z[-1]) if d[-1] > 0 else 0.0
        i = cross[-1]
        return float(z[i] + d[i] / (d[i] - d[i + 1]) * (z[i + 1] - z[i]))

    def _result(self, ctx, inputs, setup, march, mesh, volume, record, timings, fine, away, size_field, probes) -> AnalysisResult:
        import numpy as np

        from cadgen._internal.fea.analyses.thermal_transient import time_label

        t = np.array(record["t"])
        level = np.array(record["level"])
        force = np.array(record["force"])
        moment = np.array(record["moment"])
        pmax = np.array(record["pmax"])
        vol = np.array(record["volume"])
        slosh = force - force[0]
        frames = dict(record["frames"])
        for key in ("level", "pressure", "force"):
            peak = record["peaks"].get(key)
            if peak is not None:
                frames.setdefault(round(peak[1]["t"], 12), peak[1])
        times = sorted(frames)
        level_peak = int(np.argmax(level))
        default = int(np.argmin([abs(tt - t[level_peak]) for tt in times]))
        series = Series(kind="time", unit="s", default=default, frames=[
            SeriesFrame(value=round(tt, 9), label=time_label(tt), attributes={
                "water_fraction": "_WATER_FRACTION" if n == 0 else f"_WATER_FRACTION_F{n}",
                "pressure": "_PRESSURE" if n == 0 else f"_PRESSURE_F{n}",
            }) for n, tt in enumerate(times)
        ])
        share_frames = [frames[tt]["share"] for tt in times]
        pressure_frames = [frames[tt]["pressure"] for tt in times]
        stride = max(1, math.ceil(len(t) / 600))
        keep = sorted({0, len(t) - 1, level_peak, int(np.argmax(pmax)), *range(0, len(t), stride)})

        def curve(y, unit):
            return {"x": [round(float(t[i]), 9) for i in keep], "x_unit": "s", "y": [round(float(y[i]), 9) for i in keep], "y_unit": unit}

        curves = {
            "fill_level_mm": curve(level, "mm"),
            "max_wall_pressure_Pa": curve(pmax, "Pa"),
            "volume_change_percent": curve(100.0 * (vol - vol[0]) / vol[0] if vol[0] else 0 * vol, "%"),
            **{f"sloshing_force_{'xyz'[c]}_N": curve(slosh[:, c], "N") for c in range(3)},
            **{f"moment_{'xyz'[c]}_N_m": curve(moment[:, c] - moment[0, c], "N m") for c in range(3)},
            **{f"height_{label}_mm": curve(np.array(values), "mm") for label, values in record["probes"].items()},
        }
        warnings = list(march.warnings)
        analysis_warnings = []
        if march.max_drift > 0.01:
            analysis_warnings.append(f"the liquid's volume drifted by up to {100 * march.max_drift:.2g}% in a step before it was "
                                     "put back: the surface moved fast for the mesh; a finer mesh would follow it better")
        result = AnalysisResult(
            dof_locations=ctx.space.dof_locations, vertices=ctx.space.vertices, tets=ctx.space.tets,
            boundary_quadratic=ctx.space.boundary_quadratic, element_dofs=ctx.space.element_dofs,
            fields={"water_fraction": share_frames[0], "pressure": pressure_frames[0]},
            series=series, frame_fields={"water_fraction": share_frames, "pressure": pressure_frames},
            curves=curves, dofs=int(march.n),
            solver=f"Taylor-Hood P2/P1 two-fluid Navier-Stokes, level set, BDF2, {'GMRES + multigrid' if march.solver == 'iterative' else 'direct'}",
            timings=timings, warnings=warnings,
            scalars={
                "t": t, "level": level, "force": force, "moment": moment, "pmax": pmax, "volume": vol, "slosh": slosh,
                "speed": np.array(record["speed"]), "probes": {p["label"]: (p["at_mm"], np.array(record["probes"][p["label"]])) for p in probes},
                "peaks": {k: (v[0], v[1]["t"]) for k, v in record["peaks"].items()},
                "march": {"steps": len(t) - 1, "solves": march.solves, "rebuilds": march.rebuilds,
                          "max_drift": march.max_drift, "epsilon_mm": march.epsilon * 1e3,
                          "expected_volume": march.expected_volume, "h_min_mm": march.h_min * 1e3,
                          "smallest_step_s": float(np.diff(t).min()) if len(t) > 1 else 0.0,
                          "largest_step_s": float(np.diff(t).max()) if len(t) > 1 else 0.0,
                          "krylov_fallbacks": march.krylov_fallbacks, "solver": march.solver, "cfl": march.cfl},
                "fluid_mesh": {"elements": int(mesh.t.shape[1]), "nodes": int(mesh.p.shape[1]), "size_mm": round(fine, 4),
                               "away_mm": round(away, 4) if size_field else None},
                "setup": setup, "end_s": float(t[-1]), "frame_t": times,
                "analysis_warnings": analysis_warnings,
                # Structured, for the viewer's setup rows: how full it starts, and how it is shaken.
                "analysis_extras": {"fill": {"fraction": round(float(vol[0]) * 1e9 / setup.domain.volume_mm3, 4),
                                             "level_mm": round(float(level[0]), 3), "liquid": inputs.liquid.name,
                                             "gas": inputs.gas.name}},
            },
        )
        if inputs.mapped:
            peak = record["peaks"].get("force") or record["peaks"].get("pressure")
            pressure = peak[1]["pressure"] if peak is not None else pressure_frames[0]
            self._structure(ctx, inputs, result, pressure)
            result.scalars["mapped_at_s"] = peak[1]["t"] if peak is not None else 0.0
        return result

    def _structure(self, ctx: SolveContext, inputs: MultiphaseInputs, result: AnalysisResult, pressure) -> None:
        """One-way: the wall pressure at one moment, face by face, as a static load on the part; its fields and checks join."""
        import types

        from cadgen._internal.fea import solve
        from cadgen._internal.fea.analyses.static import solved_record

        volume = ctx.volume
        per_row = pressure[ctx.space.boundary_quadratic].mean(axis=1) / 1e6
        extra: dict[str, Any] = {"space": ctx.space, "facet_pressures": per_row}
        if ctx.plan is not None and ctx.plan.solver != "direct":
            extra["solver"] = "iterative"
        outcome = solve.solve_linear_static(volume, inputs.structure_material, inputs.fixtures, (), ctx.ordinal_of,
                                            log=ctx.log, automatic=ctx.automatic, **extra)
        study = types.SimpleNamespace(material=inputs.structure_material,
                                      margin=getattr(ctx.study, "margin", 2.0) if ctx.study is not None else 2.0)
        result.solved = [solved_record(volume, outcome, study, ctx.ordinal_of, ctx.part_name, inputs.fixtures)]
        result.fields["von_mises"] = outcome.von_mises
        result.fields["displacement"] = outcome.displacement
        result.deformation = outcome.displacement
        result.reactions = list(outcome.reactions)
        result.applied = tuple(outcome.applied)
        result.warnings += [w for w in outcome.warnings if w not in result.warnings]
        result.scalars["outcome"] = outcome
        result.scalars["yield_MPa"] = inputs.structure_material.yield_strength

    def needs_finer(self, result: AnalysisResult, inputs: MultiphaseInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: MultiphaseInputs) -> dict:
        import numpy as np

        from cadgen._internal.fea.checks import check_status

        if check["kind"] in ("stress", "displacement"):
            from cadgen._internal.fea.analyses import get_analysis

            return get_analysis("static").judge(check, index, ctx, result, inputs)
        scalars = result.scalars
        t = scalars["t"]
        setup = scalars["setup"]
        times = scalars["frame_t"]
        if check["kind"] == "fill_level":
            limit = check.get("limit_mm", setup.height_mm)
            if check.get("probes"):
                known = scalars["probes"]
                missing = [label for label in check["probes"] if label not in known]
                if missing:
                    raise ValueError(f"view.checks[{index}].probes: {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} "
                                     f"not among the study's probes ({', '.join(known) or 'none'})")
                series = np.max([known[label][1] for label in check["probes"]], axis=0)
            else:
                series = scalars["level"]
            peak = int(np.argmax(series))
            value, unit, label = float(series[peak]), "mm", "Fill level"
            where = {"ref": None, "at": None}
        else:
            series = scalars["pmax"]
            peak = int(np.argmax(series))
            value, limit, unit, label = float(series[peak]), check["limit_Pa"], "Pa", "Wall pressure"
            where = {"ref": None, "at": None}
        when = float(t[peak])
        frame = int(np.argmin([abs(tt - when) for tt in times]))
        ratio = value / limit if limit > 0 else math.inf
        out = {
            "kind": check["kind"], "label": check.get("label") or label, "value": round(value, 6), "limit": round(float(limit), 6),
            "unit": unit, "ratio": round(ratio, 6), "close_at": CLOSE_AT, "status": check_status(ratio, CLOSE_AT),
            "where": where, "at": {"frame": frame, "value": round(when, 9), "unit": "s"},
        }
        if check["kind"] == "fill_level" and "limit_mm" not in check:
            out["brim"] = True
        return out

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: MultiphaseInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea import checks

        found: list[dict] = []
        if result.solved:
            found += checks.findings(result.solved[0])
        for check in check_results:
            if check["kind"] not in ("fill_level", "wall_pressure") or check["status"] == "passes":
                continue
            fails = check["status"] == "fails"
            when = check["at"]["value"]
            if check["kind"] == "fill_level":
                what = "the brim" if check.get("brim") else f"the {check['limit']:g} mm allowed"
                summary = (f"The liquid rises to {check['value']:.4g} mm above the floor at {when:.3g} s, "
                           f"{'past' if fails else 'close to'} {what}")
            else:
                summary = (f"The wall pressure reaches {check['value']:.4g} Pa at {when:.3g} s, "
                           f"{'over' if fails else 'close to'} the {check['limit']:g} Pa allowed")
            found.append({
                "check": "fea", "severity": "error" if fails else "warning",
                "type": f"{check['kind']}_{'over_limit' if fails else 'close_to_limit'}", "summary": summary,
                "description": f"{check['value']:.4g} {check['unit']} against {check['limit']:g} {check['unit']} ({check['ratio']:.2f} of it)",
                "items": [],
            })
        for sentence in result.scalars.get("analysis_warnings", ()):
            found.append({"check": "fea", "severity": "warning", "type": "volume_drift", "summary": sentence,
                          "description": "the level set's volume is put back every step; a large drift means the mesh is coarse "
                                         "for how fast the surface moves", "items": []})
        return found

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        if "displacement" not in result.fields:
            return None
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        magnitude = np.linalg.norm(result.fields["displacement"], axis=1)
        return requested or auto_deformation_scale(float(magnitude.max()), bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: MultiphaseInputs, check_results: list[dict]) -> dict:
        import numpy as np

        s = result.scalars
        setup: _Setup = s["setup"]
        t, level, vol, slosh, moment, pmax = s["t"], s["level"], s["volume"], s["slosh"], s["moment"], s["pmax"]
        sloshing = np.linalg.norm(slosh, axis=1)
        peak_slosh = int(np.argmax(sloshing))
        dmoment = np.linalg.norm(moment - moment[0], axis=1)
        march = s["march"]
        total = setup.domain.volume_mm3
        summary: dict[str, Any] = {
            "fluids": {"liquid": {"name": inputs.liquid.name, "density_kg_m3": inputs.liquid.density_kg_m3,
                                  "viscosity_Pa_s": inputs.liquid.viscosity_Pa_s},
                       "gas": {"name": inputs.gas.name, "density_kg_m3": inputs.gas.density_kg_m3,
                               "viscosity_Pa_s": inputs.gas.viscosity_Pa_s},
                       "surface_tension_N_m": inputs.surface_tension_N_m},
            "inside": {"volume_L": round(total * 1e-6, 9), "height_mm": round(setup.height_mm, 4),
                       "floor_mm": round(setup.floor_mm, 4), "length_mm": round(setup.length_mm, 4),
                       "open_sides": sorted({f.opening for f in setup.domain.faces if f.kind == "opening"})},
            "fill": {**{k: v for k, v in inputs.fill.items()},
                     "start_level_mm": round(float(level[0]), 4),
                     "start_fraction": round(float(vol[0]) * 1e9 / total, 6) if total else None,
                     "words": fill_words(round(float(vol[0]) * 1e9 / total, 4) if total else None, inputs.liquid.name)},
            "first_sloshing_Hz": round(1.0 / setup.period_s, 6) if math.isfinite(setup.period_s) else None,
            "end_s": round(s["end_s"], 9),
            "peak_fill_level_mm": round(float(level.max()), 4),
            "peak_fill_level_at_s": round(float(t[int(np.argmax(level))]), 9),
            "brim_mm": round(setup.height_mm, 4),
            "probes": [{"label": label, "at_mm": at, "peak_mm": round(float(h.max()), 4) if len(h) else None,
                        "peak_at_s": round(float(t[int(np.argmax(h))]), 9) if len(h) else None,
                        "final_mm": round(float(h[-1]), 4) if len(h) else None}
                       for label, (at, h) in s["probes"].items()],
            "max_wall_pressure_Pa": round(float(pmax.max()), 6),
            "max_wall_pressure_at_s": round(float(t[int(np.argmax(pmax))]), 9),
            "start_wall_pressure_Pa": round(float(pmax[0]), 6),
            "force_N": {"at_rest": [round(float(c), 9) for c in s["force"][0]],
                        "sloshing_peak": [round(float(c), 9) for c in slosh[peak_slosh]],
                        "sloshing_peak_N": round(float(sloshing[peak_slosh]), 9),
                        "sloshing_peak_at_s": round(float(t[peak_slosh]), 9)},
            "moment_N_m": {"sloshing_peak_N_m": round(float(dmoment.max()), 9),
                           "about_mm": "the inside's floor, below its middle"},
            "volume": {"start_L": round(float(vol[0]) * 1e3, 9), "end_L": round(float(vol[-1]) * 1e3, 9),
                       "change_percent": round(100.0 * float(vol[-1] - vol[0]) / float(vol[0]), 9) if vol[0] else 0.0,
                       "max_change_percent": round(100.0 * float(np.abs(vol - vol[0]).max()) / float(vol[0]), 9) if vol[0] else 0.0,
                       "largest_step_drift_percent": round(100.0 * float(march["max_drift"]), 9),
                       # In through the inlets less out through the outlets and open sides; 0 for a closed part.
                       "net_inflow_L": round((float(march["expected_volume"]) - float(vol[0])) * 1e3, 9),
                       "error_percent": round(100.0 * float(vol[-1] - march["expected_volume"]) / float(vol[0]), 9) if vol[0] else 0.0},
            "max_speed_m_s": round(float(s["speed"].max()), 9),
            "interface_mm": round(4.0 * march["epsilon_mm"], 4),
            "march": {"steps": march["steps"], "rebuilds": march["rebuilds"], "smallest_step_s": float(f"{march['smallest_step_s']:.4g}"),
                      "largest_step_s": float(f"{march['largest_step_s']:.4g}"), "cfl": march["cfl"], "solver": march["solver"]},
            "fluid_mesh": dict(s["fluid_mesh"]),
            "deformation_scale": s.get("deformation_scale"),
        }
        if result.solved:
            from cadgen._internal.fea import checks
            from cadgen._internal.fea.analyses.static import floored

            outcome = s["outcome"]
            magnitude = np.linalg.norm(outcome.displacement, axis=1)
            solved = result.solved[0]
            summary.update({
                "mapped_at_s": round(float(s.get("mapped_at_s", 0.0)), 9),
                "max_von_mises_MPa": round(float(outcome.von_mises.max()), 4),
                "max_von_mises_at_mm": [round(c, 3) for c in solved.peak_at],
                "yield_MPa": solved.yield_MPa,
                "max_displacement_mm": round(float(magnitude.max()), 6),
                "safety_factor": floored(checks.safety_factor(solved)),
            })
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} two fluids"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        pressures = result.frame_fields["pressure"]
        ranges = {"water_fraction": (0.0, 1.0),
                  "pressure": (min(float(p.min()) for p in pressures), max(float(p.max()) for p in pressures))}
        if "max_von_mises_MPa" in summary:
            ranges["von_mises"] = (0.0, summary["max_von_mises_MPa"])
            ranges["displacement"] = (0.0, summary["max_displacement_mm"])
        return ranges

    def extras_head(self, summary: dict) -> dict:
        return {"safety_factor": summary["safety_factor"]} if "safety_factor" in summary else {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: MultiphaseInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        def fluid(f: Fluid) -> dict:
            return {"name": f.name, "density_kg_m3": f.density_kg_m3, "viscosity_Pa_s": f.viscosity_Pa_s}

        echo: dict[str, Any] = {
            "multiphase": {
                "liquid": fluid(inputs.liquid), "gas": fluid(inputs.gas), "surface_tension_N_m": inputs.surface_tension_N_m,
                "fill": dict(inputs.fill), "gravity_m_s2": list(inputs.gravity_m_s2), "walls": inputs.walls,
                "end_s": inputs.end_s, "step_s": inputs.step_s,
                "acceleration": None if inputs.acceleration is None else {
                    "direction": list(inputs.acceleration[0]), "amplitude_g": inputs.acceleration[1],
                    "history": history_echo(inputs.acceleration[2]), "words": history_words(inputs.acceleration[2])},
                "inlets": [{"opening": o.opening, "velocity_m_s": o.velocity_m_s, "fluid": o.fluid} for o in inputs.openings if o.kind == "inlet"],
                "outlets": [{"opening": o.opening, "pressure_Pa": o.pressure_Pa} for o in inputs.openings if o.kind == "outlet"],
                "probes": [{"label": p.label, "at_mm": list(p.at_mm)} for p in inputs.probes],
            },
        }
        if inputs.mapped:
            material = inputs.structure_material
            echo["material"] = {"name": material.name, "yield_MPa": material.yield_strength,
                                "youngs_GPa": round(material.E / 1000.0, 6), "poisson": material.nu}
            echo["fixtures"] = [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures]
            echo["loads"] = []
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        fill = summary["fill"]
        force = summary["force_N"]
        volume = summary["volume"]
        lines = [
            f"{fill['words']} ({summary['fluids']['liquid']['name']} under {summary['fluids']['gas']['name']}), "
            f"followed for {summary['end_s']:g} s in {summary['march']['steps']} steps",
            f"liquid rises to {summary['peak_fill_level_mm']:.4g} mm above the floor at {summary['peak_fill_level_at_s']:.3g} s "
            f"(brim {summary['brim_mm']:.4g} mm)"
            + (f"; first sloshing mode {summary['first_sloshing_Hz']:.3g} Hz by linear theory" if summary.get("first_sloshing_Hz") else ""),
            f"wall pressure up to {summary['max_wall_pressure_Pa']:.4g} Pa; sloshing force up to {force['sloshing_peak_N']:.4g} N "
            f"at {force['sloshing_peak_at_s']:.3g} s",
            f"liquid volume {volume['start_L']:.4g} L to {volume['end_L']:.4g} L ({volume['change_percent']:+.2g}%)",
        ]
        for probe in summary["probes"]:
            if probe["peak_mm"] is not None:
                lines.append(f"probe {probe['label']}: up to {probe['peak_mm']:.4g} mm at {probe['peak_at_s']:.3g} s")
        if "max_von_mises_MPa" in summary:
            lines.append(f"under the fluids' pressure at {summary['mapped_at_s']:.3g} s: peak von Mises "
                         f"{summary['max_von_mises_MPa']:.4g} MPa, largest displacement {summary['max_displacement_mm']:.4g} mm"
                         + (f", safety factor {summary['safety_factor']:g}" if summary.get("safety_factor") is not None else ""))
        return lines

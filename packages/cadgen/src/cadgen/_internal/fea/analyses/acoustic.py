"""Sound (lite): linear acoustics, the Helmholtz equation for sound in air or another fluid.

Three questions, one study shape (:mod:`cadgen._internal.fea.acoustic_ops` does the numbers):

- **Cavity modes** (no ``sources``): the natural acoustic frequencies of an enclosed air volume and
  the pressure shape it rings in at each, its walls rigid and any ``open`` faces (an open pipe end)
  held at zero pressure. A closed cavity's uniform mode (0 Hz) is left out and said.
- **Frequency response** (``sources`` and a ``sweep_Hz`` or ``frequencies_Hz``): a face vibrating
  into the air at a normal velocity (``velocity_mm_s``), or a point source of volume velocity,
  drives the air; the sound pressure level (dB re 20 µPa in air) over the sweep, damped by the
  ``absorbers`` (an absorption coefficient or an impedance per face) and the air's ``loss_factor``.
- **Vibro-acoustics** (``"from": "harmonic"``): a ``harmonic`` study on the same document (its
  material, fixtures, excitation and sweep) is solved first on the part, and its surface's normal
  velocity at each of its frames drives the air inside or around the part (one way: the air does
  not push back).

Where the air is (``domain``): ``part`` (the part's own solid is the air: a duct, a room, a
cavity modelled as its air), ``inside`` (the air the part closes inside it) or ``outside`` (the
air around it, out to a box whose sides absorb outgoing sound by a first-order Sommerfeld
condition: an approximation, said as one). Fields on the part's surface: the pressure (a mode's
shape, signed, or the amplitude in Pa) and the level in dB, per mode or per frequency frame.
Checks: ``sound_level`` (the loudest level over faces, at named ``probes`` or anywhere, against
``limit_dB``) and ``frequency`` on the cavity modes.

The mesh resolves at least six quadratic elements per wavelength at the top frequency; where the
budget cannot afford that, the ladder coarsens it and says how far the frequencies may move. Its
limits are written into every result. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "AcousticAnalysis", "AcousticInputs", "Absorber", "ELEMENTS_PER_WAVELENGTH", "LIMITS", "Probe", "Source",
    "level_words",
]

LIMITS = (
    "Linear acoustics: small sound pressures in still air or fluid, no flow and no heat or viscous loss at the walls.",
    "Absorption is lumped: each absorbing face is a normal-incidence impedance, and the air's loss one factor.",
    "Open air ends at a first-order absorbing (Sommerfeld) boundary: exact for sound spreading from the part's "
    "centre, an approximation for any other.",
)
#: Quadratic elements per wavelength at the top frequency the mesh is sized for.
ELEMENTS_PER_WAVELENGTH = 6.0
#: The fewest the ladder coarsens to: below this the wave is not resolved at all.
FEWEST_PER_WAVELENGTH = 2.5
#: The most modes a study may ask for.
MAX_MODES = 30
#: A sound_level check is close within 3 dB of its limit (a pressure ratio of 10^(-3/20)).
CLOSE_DB = 3.0
#: A frequency check is close within 10 % of its limit.
FREQUENCY_CLOSE = 0.9
#: The default sweep: this many log-spaced frequencies, plus points around each cavity mode in it.
SWEEP_POINTS = 40
MODE_POINTS = (-2, -1, 0, 1, 2)
#: Air's default loss factor in a response (a little damping, so a rigid cavity's peaks stay finite).
DEFAULT_LOSS = 0.01
#: Open air: the box stands this far past the part by default, the larger of half its size and half a wavelength.
#: far_field brings it in, never under a quarter of the part's size or an eighth of a wavelength.
PAD_SHARE, PAD_WAVES, PAD_FLOOR_SHARE, PAD_FLOOR_WAVES = 0.5, 0.5, 0.25, 0.125
#: Cost model: the scalar system has about a third of the vector stiffness's entries per row; a complex
#: factorisation costs about four times a real one in time and twice in memory.
NNZ_PER_ROW, COMPLEX_TIME, COMPLEX_MEMORY = 27.0, 4.0, 2.0
G0_MM_S2 = 9806.65


def level_words(dB: float) -> str:
    return f"{dB:.0f} dB" if abs(dB) >= 10 else f"{dB:.1f} dB"


def _hz(f: float) -> str:
    if f >= 10:
        return f"{f:.0f} Hz"
    return f"{f:.1f} Hz" if f >= 1 else f"{f:.2f} Hz"


@dataclass(frozen=True)
class Source:
    """A vibrating face (``faces``, ``velocity_mm_s`` into the air) or a point (``point_mm``, ``volume_velocity_m3_s``)."""

    faces: tuple[str, ...] = ()
    velocity_mm_s: float | None = None
    point_mm: tuple[float, float, float] | None = None
    volume_velocity_m3_s: float | None = None


@dataclass(frozen=True)
class Absorber:
    faces: tuple[str, ...]
    absorption: float | None = None
    impedance_rayl: float | None = None

    def admittance(self, fluid) -> float:
        from cadgen._internal.fea.acoustic_ops import absorption_admittance

        if self.absorption is not None:
            return absorption_admittance(self.absorption)
        return fluid.density_kg_m3 * fluid.speed_m_s / self.impedance_rayl


@dataclass(frozen=True)
class Probe:
    label: str
    at_mm: tuple[float, float, float]


@dataclass(frozen=True)
class AcousticInputs(Inputs):
    fluid: Any = None
    domain: str = "part"
    #: "modes" (natural frequencies) or "response" (a sweep driven by sources or a harmonic result).
    solve: str = "modes"
    modes: int = 6
    sweep_Hz: tuple[float, float] | None = None
    frequencies_Hz: tuple[float, ...] = ()
    points: int = SWEEP_POINTS
    sources: tuple[Source, ...] = ()
    absorbers: tuple[Absorber, ...] = ()
    open_faces: tuple[str, ...] = ()
    probes: tuple[Probe, ...] = ()
    loss_factor: float = DEFAULT_LOSS
    air_mm: float | None = None
    #: Vibro-acoustics: the harmonic study solved first, its surface velocity the source.
    from_harmonic: bool = False
    harmonic: Any = None
    checks: tuple[dict, ...] = ()
    #: What the material must carry (the harmonic's density); parse_study asks for it by name.
    material_needs: tuple[str, ...] = ()

    @property
    def top_Hz(self) -> float | None:
        if self.frequencies_Hz:
            return max(self.frequencies_Hz)
        if self.sweep_Hz is not None:
            return self.sweep_Hz[1]
        return None

    @property
    def check_modes(self) -> int:
        return max((check.get("mode", 1) for check in self.checks if check["kind"] == "frequency" and "min_Hz" in check), default=0)


# -- parsing ----------------------------------------------------------------------------------------


def _known(entry: dict, keys: set[str], where: str, words: str) -> None:
    unknown = set(entry) - keys
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; {words}")


def _entries(document: dict, key: str, example: str) -> list[dict]:
    raw = document.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"study.{key}: expected a list like [{example}]")
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{key}[{index}]: expected an object like {example}")
    return raw


def _point(raw: Any, where: str) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError(f"{where}: a point as [x, y, z] in mm")
    return tuple(kinds.number(c, where=where) for c in raw)  # type: ignore[return-value]


def parse_fluid(raw: Any):
    from cadgen._internal.fea.acoustic_ops import FLUIDS, Fluid

    if raw is None:
        raw = "air"
    if isinstance(raw, str):
        if raw not in FLUIDS:
            raise ValueError(f"fluid: {kinds.json_text(raw)} is not one of {sorted(FLUIDS)}; or give "
                             '{"density_kg_m3": 1.2, "speed_m_s": 343}')
        density, speed, reference = FLUIDS[raw]
        return Fluid(raw, density, speed, reference)
    if not isinstance(raw, dict):
        raise ValueError('fluid: "air", "water", or {"density_kg_m3": 1.2, "speed_m_s": 343}')
    _known(raw, {"name", "density_kg_m3", "speed_m_s", "reference_Pa"}, "fluid",
           "a fluid takes density_kg_m3, speed_m_s, and optionally name and reference_Pa")
    for key in ("density_kg_m3", "speed_m_s"):
        if key not in raw:
            raise ValueError(f"fluid.{key}: the fluid's {'density, kg/m³' if key.startswith('density') else 'speed of sound, m/s'}")
    name = raw.get("name", "fluid")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("fluid.name: a short name")
    return Fluid(name.strip(), kinds.number(raw["density_kg_m3"], where="fluid.density_kg_m3", positive=True),
                 kinds.number(raw["speed_m_s"], where="fluid.speed_m_s", positive=True),
                 kinds.number(raw.get("reference_Pa", 20e-6), where="fluid.reference_Pa", positive=True))


def _sources(document: dict) -> tuple[Source, ...]:
    out = []
    for index, entry in enumerate(_entries(document, "sources", '{"faces": ["#o1.f3"], "velocity_mm_s": 1}')):
        where = f"sources[{index}]"
        _known(entry, {"faces", "velocity_mm_s", "point_mm", "volume_velocity_m3_s"}, where,
               "a source is a vibrating face (faces, velocity_mm_s) or a point (point_mm, volume_velocity_m3_s)")
        if "faces" in entry:
            if "point_mm" in entry or "volume_velocity_m3_s" in entry:
                raise ValueError(f"{where}: a source is a vibrating face or a point, not both")
            if "velocity_mm_s" not in entry:
                raise ValueError(f"{where}.velocity_mm_s: how fast the face moves into the air, mm/s (its amplitude)")
            velocity = kinds.number(entry["velocity_mm_s"], where=f"{where}.velocity_mm_s")
            if velocity == 0:
                raise ValueError(f"{where}.velocity_mm_s: the face does not move")
            out.append(Source(faces=kinds.faces(entry, where=where), velocity_mm_s=velocity))
        elif "point_mm" in entry:
            if "velocity_mm_s" in entry:
                raise ValueError(f"{where}: a point source takes volume_velocity_m3_s, not velocity_mm_s")
            if "volume_velocity_m3_s" not in entry:
                raise ValueError(f"{where}.volume_velocity_m3_s: the volume the point breathes in and out, m³/s (its amplitude)")
            out.append(Source(point_mm=_point(entry["point_mm"], f"{where}.point_mm"),
                              volume_velocity_m3_s=kinds.number(entry["volume_velocity_m3_s"], where=f"{where}.volume_velocity_m3_s",
                                                                positive=True)))
        else:
            raise ValueError(f"{where}: name the vibrating faces (faces and velocity_mm_s) or a point (point_mm and volume_velocity_m3_s)")
    return tuple(out)


def _absorbers(document: dict) -> tuple[Absorber, ...]:
    out = []
    for index, entry in enumerate(_entries(document, "absorbers", '{"faces": ["#o1.f5"], "absorption": 0.3}')):
        where = f"absorbers[{index}]"
        _known(entry, {"faces", "absorption", "impedance_rayl"}, where,
               "an absorber takes faces and absorption (0 to 1) or impedance_rayl (Pa·s/m)")
        given = [key for key in ("absorption", "impedance_rayl") if key in entry]
        if len(given) != 1:
            raise ValueError(f"{where}: give absorption (the share of sound it soaks up, 0 to 1: foam about 0.7, "
                             "carpet 0.3, painted wall 0.05) or impedance_rayl, exactly one")
        if given == ["absorption"]:
            alpha = kinds.number(entry["absorption"], where=f"{where}.absorption", positive=True)
            if alpha > 1:
                raise ValueError(f"{where}.absorption: a share from 0 to 1, got {alpha:g}")
            out.append(Absorber(kinds.faces(entry, where=where), absorption=alpha))
        else:
            out.append(Absorber(kinds.faces(entry, where=where),
                                impedance_rayl=kinds.number(entry["impedance_rayl"], where=f"{where}.impedance_rayl", positive=True)))
    return tuple(out)


def _probes(document: dict) -> tuple[Probe, ...]:
    out = []
    for index, entry in enumerate(_entries(document, "probes", '{"at_mm": [0, 0, 100], "label": "ear"}')):
        where = f"probes[{index}]"
        _known(entry, {"at_mm", "label"}, where, "a probe takes at_mm ([x, y, z]) and a label")
        label = entry.get("label", f"probe {index + 1}")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{where}.label: a short name, like \"ear\"")
        if "at_mm" not in entry:
            raise ValueError(f"{where}.at_mm: where the microphone is, [x, y, z] in mm")
        out.append(Probe(label.strip(), _point(entry["at_mm"], f"{where}.at_mm")))
    labels = [probe.label for probe in out]
    if len(set(labels)) != len(labels):
        raise ValueError("probes: each probe needs its own label")
    return tuple(out)


def _study_checks(document: dict) -> tuple[dict, ...]:
    view = document.get("view")
    entries = view.get("checks") if isinstance(view, dict) else None
    found = []
    for index, entry in enumerate(entries if isinstance(entries, list) else ()):
        if isinstance(entry, dict) and entry.get("kind") in ("sound_level", "frequency"):
            spec = kinds.SOUND_LEVEL if entry["kind"] == "sound_level" else kinds.FREQUENCY
            try:
                found.append({**spec.parse(entry, f"view.checks[{index}]"), "index": index})
            except ValueError:
                continue
    return tuple(found)


# -- the analysis -----------------------------------------------------------------------------------

_PRESSURE_MODE = FieldSpec("sound_pressure", "_SOUND_PRESSURE", "sound pressure (mode shape)", "", signed=True, per_frame=True)
_LEVEL = FieldSpec("sound_level", "_SOUND_LEVEL", "sound pressure level", "dB", per_frame=True)
_PRESSURE = FieldSpec("sound_pressure", "_SOUND_PRESSURE", "sound pressure amplitude", "Pa", per_frame=True)
_HARMONIC_KEYS = frozenset({"fixtures", "loads", "excitation", "damping_ratio"})


@dataclass
class _Air:
    """What the solve built: the air region, its operators, and how far its mesh resolves the waves."""

    region: Any
    ops: Any
    size_mm: float
    top_Hz: float
    probe: Any = None            # (P x DOF) matrix of the probes inside the air
    probe_inside: Any = None
    probe_extrapolated: list = field(default_factory=list)


class AcousticAnalysis:
    name: ClassVar[str] = "acoustic"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Sound"
    estimate_only: ClassVar[bool] = False
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "fluid", "domain", "modes", "sweep_Hz", "frequencies_Hz", "points", "sources", "absorbers", "open", "probes",
        "loss_factor", "air_mm", "from",
    }) | _HARMONIC_KEYS
    material_needs: ClassVar[frozenset[str]] = frozenset()
    #: The material is the structure's, and only a vibro-acoustic study has one (study.parse_study reads this).
    material_required: ClassVar[bool] = False
    isotropic_only: ClassVar[bool] = False
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    checks: ClassVar[tuple] = (kinds.SOUND_LEVEL, kinds.FREQUENCY)
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "threshold", "mode", "frame")
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "far_field", "local_refine", "reduce_modes", "symmetry")
    noun: ClassVar[str] = "this sound"

    def __init__(self):
        # What the study last parsed solves and where (its fields, controls and limits follow them).
        self._solve = "modes"
        self._domain = "part"

    @property
    def limits(self) -> tuple[str, ...]:
        """What the model leaves out; the open-air sentence only where the air is open."""
        return LIMITS if self._domain == "outside" else LIMITS[:2]

    @property
    def fields(self) -> tuple[FieldSpec, ...]:
        return (_PRESSURE_MODE,) if self._solve == "modes" else (_LEVEL, _PRESSURE)

    @property
    def default_controls(self) -> dict[str, dict]:
        if self._solve == "modes":
            return {"mode": {"drives": "mode", "type": "enum", "options": None},
                    "field": {"drives": "field", "type": "enum", "options": ["sound_pressure"]}}
        return {"frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
                "field": {"drives": "field", "type": "enum", "options": ["sound_level", "sound_pressure"]}}

    @property
    def governing_word(self) -> str:
        return "the first frequency" if self._solve == "modes" else "the loudest level"

    def upstream_for(self, inputs: AcousticInputs) -> tuple[str, ...]:
        return ("harmonic",) if inputs.from_harmonic else ()

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> AcousticInputs:
        fluid = parse_fluid(document.get("fluid"))
        source = document.get("from")
        if source is not None and source != "harmonic":
            raise ValueError(f"from: {kinds.json_text(source)}; sound is driven by a \"harmonic\" result's vibrating surface")
        vibro = source == "harmonic"
        domain = document.get("domain", "outside" if vibro else "part")
        if domain not in ("part", "inside", "outside"):
            raise ValueError(f"domain: {kinds.json_text(domain)} is not one of \"part\" (the part's solid is the air), "
                             "\"inside\" (the air closed inside the part) or \"outside\" (the air around it)")
        sources = _sources(document)
        absorbers = _absorbers(document)
        open_faces: tuple[str, ...] = ()
        for index, entry in enumerate(_entries(document, "open", '{"faces": ["#o1.f2"]}')):
            _known(entry, {"faces"}, f"open[{index}]", "an open face takes faces (held at zero sound pressure, an open pipe end)")
            open_faces += kinds.faces(entry, where=f"open[{index}]")
        probes = _probes(document)
        harmonic_keys = sorted(set(document) & _HARMONIC_KEYS)
        if vibro:
            if sources:
                raise ValueError("sources: a study driven by a harmonic result takes its sound from the part's vibrating "
                                 "surface; leave sources out, or leave out \"from\"")
            if domain == "part":
                raise ValueError("domain: a vibrating part drives the air \"inside\" it or \"outside\" it; the part's own "
                                 "solid cannot be both the structure and the air")
            if document.get("material") is None:
                raise ValueError("material: the vibrating part's material, for the harmonic solve that drives the sound")
            if "frequencies_Hz" in document or "points" in document:
                raise ValueError("frequencies_Hz: a harmonic-driven study hears the harmonic's own frames (its peaks and "
                                 "log-spaced frequencies over sweep_Hz); leave frequencies_Hz and points out")
        elif harmonic_keys:
            raise ValueError(f"{harmonic_keys[0]}: that is a harmonic study's key; add \"from\": \"harmonic\" to drive the "
                             "sound by the part's vibration, or leave it out")
        response = vibro or bool(sources)
        sweep = None
        frequencies: tuple[float, ...] = ()
        if document.get("sweep_Hz") is not None:
            raw = document["sweep_Hz"]
            if not isinstance(raw, list) or len(raw) != 2:
                raise ValueError("sweep_Hz: the frequencies to sweep as [low, high] in Hz, like [100, 2000]")
            low, high = (kinds.number(v, where="sweep_Hz", positive=True) for v in raw)
            if not low < high:
                raise ValueError(f"sweep_Hz: low ({low:g}) must be below high ({high:g})")
            sweep = (low, high)
        if document.get("frequencies_Hz") is not None:
            raw = document["frequencies_Hz"]
            if not isinstance(raw, list) or not raw:
                raise ValueError("frequencies_Hz: the frequencies to solve at, like [250, 500, 1000]")
            frequencies = tuple(sorted({kinds.number(v, where="frequencies_Hz", positive=True) for v in raw}))
            if sweep is not None:
                raise ValueError("frequencies_Hz: give a sweep_Hz or a list of frequencies_Hz, not both")
        points = SWEEP_POINTS
        if "points" in document:
            points = document["points"]
            if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= 400:
                raise ValueError(f"points: how many log-spaced frequencies to solve over sweep_Hz, 2 to 400, got {kinds.json_text(points)}")
        if response and sweep is None and not frequencies:
            raise ValueError("sweep_Hz: the frequencies to solve the sound at, as [low, high] in Hz (or frequencies_Hz, a list)")
        if not response:
            if sweep is not None or frequencies:
                raise ValueError("sources: a sweep needs something making the sound; add sources (a vibrating face or a point), "
                                 "or leave sweep_Hz out to find the air's natural frequencies")
            if absorbers:
                raise ValueError("absorbers: absorbers damp a driven response; a modes study finds the air's natural "
                                 "frequencies with rigid walls; add sources and a sweep_Hz to hear the absorbers")
            if domain == "outside":
                raise ValueError("domain: open air has no natural frequencies to find; add sources and a sweep_Hz to "
                                 "solve the sound radiated around the part")
        modes = document.get("modes", 6)
        if "modes" in document and response:
            raise ValueError("modes: a driven response solves every frequency of its sweep; modes is for a study with no sources")
        if isinstance(modes, bool) or not isinstance(modes, int) or not 1 <= modes <= MAX_MODES:
            raise ValueError(f"modes: how many acoustic modes to find, 1 to {MAX_MODES}, got {kinds.json_text(modes)}")
        loss = DEFAULT_LOSS if response else 0.0
        if "loss_factor" in document:
            loss = kinds.number(document["loss_factor"], where="loss_factor")
            if not 0 <= loss < 1:
                raise ValueError(f"loss_factor: the air's damping, 0 to under 1 (0.01 is a little), got {loss:g}")
            if not response:
                raise ValueError("loss_factor: damping matters to a driven response; a modes study has none")
        air_mm = None
        if "air_mm" in document:
            if domain != "outside":
                raise ValueError("air_mm: how far the open air reaches past the part, for \"domain\": \"outside\" only")
            air_mm = kinds.number(document["air_mm"], where="air_mm", positive=True)
        checks = _study_checks(document)
        labels = {probe.label for probe in probes}
        for check in checks:
            where = f"view.checks[{check['index']}]"
            if check["kind"] == "sound_level" and not response:
                raise ValueError(f"{where}: a sound_level check judges a driven response; add sources and a sweep_Hz")
            if check["kind"] == "frequency" and response:
                raise ValueError(f"{where}: a frequency check judges the air's natural frequencies; a modes study (no sources) finds them")
            for label in check.get("probes", ()):
                if label not in labels:
                    raise ValueError(f"{where}.probes: no probe labelled {label!r}; the study's probes are "
                                     f"{', '.join(repr(p) for p in sorted(labels)) or 'none'}")
            if check["kind"] == "frequency" and check.get("mode", 1) > MAX_MODES:
                raise ValueError(f"{where}.mode: at most mode {MAX_MODES} is found")
        harmonic = None
        refs = [ref for group in (*(s.faces for s in sources), *(a.faces for a in absorbers), open_faces) for ref in group]
        anchors: tuple[str, ...] = ()
        if vibro:
            from cadgen._internal.fea.analyses import get_analysis

            harmonic = get_analysis("harmonic").parse(document)
            sweep = harmonic.sweep_Hz
            refs += list(harmonic.face_refs)
            anchors = tuple(harmonic.anchor_refs)
        self._solve = "response" if response else "modes"
        self._domain = domain
        return AcousticInputs(
            tuple(dict.fromkeys(refs)), anchors, vibro, fluid=fluid, domain=domain, solve=self._solve, modes=modes,
            sweep_Hz=sweep, frequencies_Hz=frequencies, points=points, sources=sources, absorbers=absorbers,
            open_faces=tuple(dict.fromkeys(open_faces)), probes=probes, loss_factor=loss, air_mm=air_mm,
            from_harmonic=vibro, harmonic=harmonic, checks=checks, material_needs=("density",) if vibro else (),
        )

    # -- sizes ---------------------------------------------------------------------------------------

    def _air_volume_mm3(self, ctx: SolveContext, inputs: AcousticInputs) -> float:
        geometry = ctx.geometry
        if geometry is None:
            return float(ctx.volume.bbox_diagonal ** 3 / 5.0) if ctx.volume is not None else 1.0
        if inputs.domain == "part":
            return geometry.volume_mm3
        box = self._part_box(ctx)
        span = [h - l for l, h in zip(*box)]
        if inputs.domain == "inside":
            return max(math.prod(span) - geometry.volume_mm3, 0.05 * math.prod(span))
        pad = self._pad_mm(ctx, inputs)
        return math.prod(s + 2 * pad for s in span) - geometry.volume_mm3

    @staticmethod
    def _part_box(ctx: SolveContext):
        geometry = ctx.geometry
        shape = getattr(geometry, "shape", None)
        if shape is not None:
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib

            box = Bnd_Box()
            BRepBndLib.AddOptimal_s(shape, box, False, False)
            xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
            return (xmin, ymin, zmin), (xmax, ymax, zmax)
        d = geometry.bbox_diagonal_mm / math.sqrt(3.0) if geometry is not None else 10.0
        return (0.0, 0.0, 0.0), (d, d, d)

    def _top_Hz(self, ctx: SolveContext, inputs: AcousticInputs) -> float:
        """The top frequency the mesh is sized for: the sweep's top, or (modes) where the modes asked for end,
        from the smaller of the 1D (n c / 2L) and 3D (Weyl) counts, with a tenth to spare."""
        top = inputs.top_Hz
        if top is not None:
            return float(top)
        c = inputs.fluid.speed_m_s
        span = max(h - l for l, h in zip(*self._part_box(ctx))) / 1000.0
        count = max(inputs.modes, inputs.check_modes) + (0 if inputs.open_faces else 1)
        volume = self._air_volume_mm3(ctx, inputs) * 1e-9
        axial = count * c / (2.0 * max(span, 1e-9))
        weyl = c * (3.0 * count / (4.0 * math.pi * max(volume, 1e-15))) ** (1.0 / 3.0)
        return 1.1 * min(axial, weyl)

    def _wave_mm(self, ctx: SolveContext, inputs: AcousticInputs) -> float:
        return inputs.fluid.wavelength_mm(self._top_Hz(ctx, inputs)) / ELEMENTS_PER_WAVELENGTH

    def _air_size(self, ctx: SolveContext, inputs: AcousticInputs) -> float:
        """The air's element size: the requested size, never coarser than six elements per wavelength, unless
        the ladder coarsened it (``plan.acoustic_size_mm``)."""
        plan = ctx.plan
        chosen = getattr(plan, "acoustic_size_mm", None)
        if chosen:
            return float(chosen)
        # The study's own size when it gives one (``plan.size_mm`` before any rung), else the wave's; and never
        # fewer than eight elements across the part, so a small part at a low frequency is still meshed.
        diagonal = ctx.geometry.bbox_diagonal_mm if ctx.geometry is not None else (ctx.volume.bbox_diagonal if ctx.volume else 0.0)
        size = min(float(plan.size_mm) if plan.size_mm else math.inf, self._wave_mm(ctx, inputs),
                   diagonal / 8.0 if diagonal else math.inf)
        plan.acoustic_size_mm = size
        if inputs.domain == "part":
            # The part is the air: the run meshes it at this size.
            plan.size_mm = size
        return size

    def _far_mm(self, ctx: SolveContext, inputs: AcousticInputs) -> float:
        """Open air's element size away from the part: the wave's, never finer than at the part."""
        return max(self._wave_mm(ctx, inputs), self._air_size(ctx, inputs))

    def _pad_mm(self, ctx: SolveContext, inputs: AcousticInputs) -> float:
        chosen = getattr(ctx.plan, "acoustic_pad_mm", None)
        if chosen:
            return float(chosen)
        if inputs.air_mm:
            return float(inputs.air_mm)
        span = max(h - l for l, h in zip(*self._part_box(ctx)))
        wave = inputs.fluid.wavelength_mm(self._top_Hz(ctx, inputs))
        return max(PAD_SHARE * span, PAD_WAVES * wave)

    def _frequency_count(self, ctx: SolveContext, inputs: AcousticInputs) -> int:
        if inputs.solve == "modes":
            return 0
        if inputs.from_harmonic:
            return int(getattr(ctx.budget, "max_frames", 24) or 24)
        if inputs.frequencies_Hz:
            return len(inputs.frequencies_Hz)
        count = inputs.points
        if inputs.domain != "outside":
            low, high = inputs.sweep_Hz
            c = inputs.fluid.speed_m_s
            volume = self._air_volume_mm3(ctx, inputs) * 1e-9
            weyl = lambda f: 4.0 * math.pi * volume * (f / c) ** 3 / 3.0  # noqa: E731
            count += len(MODE_POINTS) * int(min(weyl(1.2 * high) - weyl(low), 200))
        return count

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: AcousticInputs):
        from cadgen._internal.fea import fit

        if ctx.assembly is not None:
            raise NotImplementedError  # one part only: solve refuses it in a sentence; no rung to take
        plan = ctx.plan
        size = self._air_size(ctx, inputs)
        geometry = ctx.geometry
        area = geometry.area_mm2 if geometry is not None else 0.0
        volume = self._air_volume_mm3(ctx, inputs)
        if inputs.domain == "part":
            tets = fit.plan_counts(ctx)[0]
        elif inputs.domain == "outside":
            far = self._far_mm(ctx, inputs)
            near = min(volume, 2.0 * area * size)
            tets = fit.VOLUME_TETS * (near / size ** 3 + (volume - near) / far ** 3) + fit.SURFACE_TETS * area / size ** 2
        else:
            tets = fit.VOLUME_TETS * volume / size ** 3 + fit.SURFACE_TETS * area / size ** 2
        n = max(int(fit.NODES_PER_TET[2] * tets), 1)
        matrix = 12.0 * NNZ_PER_ROW * n
        build = fit.BYTES_PER_ELEMENT[2] / 3.0 * tets
        seconds = fit.SECONDS_PER_ELEMENT[2] / 3.0 * tets + (fit.SECONDS_PER_ELEMENT[2] * tets if inputs.domain != "part" else 0.0)
        iterative = plan.solver in ("iterative", "matrix_free")
        modal = bool(getattr(plan, "acoustic_modal", False))
        if inputs.solve == "modes" or modal:
            count = (max(inputs.modes, inputs.check_modes) + 2) if inputs.solve == "modes" else self._modal_count(ctx, inputs)
            count = int(getattr(plan, "modes", None) or count) if inputs.solve == "modes" else count
            if iterative:
                memory = build + matrix * (1 + fit.AMG_COPIES) + 8.0 * 3 * (count + 4) * n
                seconds += 0.5 * fit.AMG_SECONDS_PER_DOF / 3.0 * n * (count + 4)
            else:
                memory = build + 2 * matrix + 16.0 * fit.FILL * n ** 1.5 + 8.0 * (2 * count + 20) * n
                seconds += fit.DIRECT_SECONDS * n ** 2 + 3 * (2 * count + 20) * 4.0 * fit.FILL * n ** 1.5 * 1e-9
            if modal:
                seconds += self._frequency_count(ctx, inputs) * (count ** 3 * 1e-8 + 8e-9 * n * count)
        else:
            frequencies = max(self._frequency_count(ctx, inputs), 1)
            if iterative:
                memory = build + matrix * COMPLEX_MEMORY * (1 + fit.AMG_COPIES)
                per = COMPLEX_TIME * 3.0 * fit.AMG_SECONDS_PER_DOF / 3.0 * n
            else:
                memory = build + COMPLEX_MEMORY * (matrix + 16.0 * fit.FILL * n ** 1.5)
                per = COMPLEX_TIME * fit.DIRECT_SECONDS * n ** 2 + 2e-6 * n
            memory += 4.0 * 2 * n * frequencies
            seconds += frequencies * per
        if inputs.from_harmonic:
            from cadgen._internal.fea.analyses import get_analysis

            structure = get_analysis("harmonic").estimate(ctx, inputs.harmonic)
            memory = max(memory, structure.memory_bytes - fit.BASE_BYTES)
            seconds += structure.seconds
        return fit.Estimate(dofs=n, memory_bytes=int(fit.BASE_BYTES + memory), seconds=float(seconds))

    def _modal_count(self, ctx: SolveContext, inputs: AcousticInputs) -> int:
        """Modes a superposed response keeps: every mode up to twice the sweep's top (Weyl's count), at least 10."""
        c = inputs.fluid.speed_m_s
        volume = self._air_volume_mm3(ctx, inputs) * 1e-9
        top = 2.0 * float(inputs.top_Hz or 1.0)
        return int(min(max(4.0 * math.pi * volume * (top / c) ** 3 / 3.0 + 4, 10), 400))

    def apply(self, rung, ctx: SolveContext, inputs: AcousticInputs):
        from cadgen._internal.fea import fit

        plan, budget = ctx.plan, ctx.budget
        if rung == "iterative":
            if plan.solver != "direct":
                return None
            before = self.estimate(ctx, inputs)
            plan.solver = "iterative"
            after = self.estimate(ctx, inputs)
            memory = before.memory_bytes > budget.memory_bytes
            saves = after.memory_bytes < 0.95 * before.memory_bytes if memory else after.seconds < 0.95 * before.seconds
            if not saves:
                plan.solver = "direct"
                return None
            how = ("LOBPCG with multigrid instead of factorising" if inputs.solve == "modes"
                   else "GMRES with a multigrid preconditioner instead of factorising at each frequency")
            return fit.Step("iterative", f"Used an iterative solver ({how}) to {'fit in memory' if memory else 'finish sooner'}",
                            None, None, detail={"solver": "iterative", "from_bytes": int(before.memory_bytes),
                                                "to_bytes": int(after.memory_bytes)})
        if rung == "far_field":
            if inputs.domain != "outside" or inputs.air_mm:
                return None
            span = max(h - l for l, h in zip(*self._part_box(ctx)))
            top = self._top_Hz(ctx, inputs)
            wave = inputs.fluid.wavelength_mm(top)
            pad = self._pad_mm(ctx, inputs)
            floor = max(PAD_FLOOR_SHARE * span, PAD_FLOOR_WAVES * wave)
            if pad <= 1.05 * floor:
                return None
            chosen = floor
            for k in range(1, 9):
                plan.acoustic_pad_mm = pad * (floor / pad) ** (k / 8)
                if self.estimate(ctx, inputs).fits(budget):
                    chosen = plan.acoustic_pad_mm
                    break
            plan.acoustic_pad_mm = chosen
            low = inputs.sweep_Hz[0] if inputs.sweep_Hz else min(inputs.frequencies_Hz)
            kr = 2 * math.pi * (0.5 * span + chosen) / inputs.fluid.wavelength_mm(low)
            return fit.Step(
                "far_field",
                f"Brought the open air's absorbing box in to {chosen:.3g} mm past the part (from {pad:.3g} mm) to fit",
                f"the first-order absorbing boundary is exact for sound spreading from the part's centre; other sound "
                f"reflects more the closer it comes: k·r is {kr:.2g} at {_hz(low)}, and under 1 it reflects strongly", None,
                detail={"from_pad_mm": round(pad, 4), "to_pad_mm": round(chosen, 4), "kr_low": round(kr, 4)},
            )
        if rung == "local_refine":
            size = self._air_size(ctx, inputs)
            top = self._top_Hz(ctx, inputs)
            wave = inputs.fluid.wavelength_mm(top)
            coarsest = wave / FEWEST_PER_WAVELENGTH
            if size >= 0.95 * coarsest:
                return None
            chosen = coarsest
            for k in range(1, 13):
                trial = size * (coarsest / size) ** (k / 12)
                self._set_size(ctx, inputs, trial)
                if self.estimate(ctx, inputs).fits(budget):
                    chosen = trial
                    break
            self._set_size(ctx, inputs, chosen)
            per = wave / chosen
            error = 100.0 * self._error(per)
            return fit.Step(
                "local_refine",
                f"Meshed the air at {chosen:.3g} mm to fit: {per:.1f} elements per wavelength at {_hz(top)}, under the "
                f"{ELEMENTS_PER_WAVELENGTH:g} it should have" + ("; the sources keep their size" if inputs.domain != "part" else ""),
                f"frequencies and levels near {_hz(top)} may be off by about {error:.1f}% (the mesh's wave-speed error); "
                "lower frequencies are resolved better", error,
                detail={"from_size_mm": round(size, 4), "to_size_mm": round(chosen, 4), "elements_per_wavelength": round(per, 3),
                        "top_Hz": round(top, 4)},
            )
        if rung == "reduce_modes":
            if inputs.solve == "modes":
                current = int(getattr(plan, "modes", None) or inputs.modes)
                floor = max(inputs.check_modes, 1)
                if current <= floor:
                    return None
                plan.modes = max(floor, current // 2)
                return fit.Step("reduce_modes", f"Found the first {plan.modes} of the {inputs.modes} modes asked for, to fit",
                                None, None, detail={"from_modes": inputs.modes, "to_modes": plan.modes})
            if inputs.domain == "outside" or getattr(plan, "acoustic_modal", False):
                return None
            before = self.estimate(ctx, inputs)
            plan.acoustic_modal = True
            after = self.estimate(ctx, inputs)
            if after.seconds > 0.95 * before.seconds and after.memory_bytes > 0.95 * before.memory_bytes:
                plan.acoustic_modal = False
                return None
            count = self._modal_count(ctx, inputs)
            return fit.Step(
                "reduce_modes",
                f"Built the response from the air's modes (about {count}, up to twice the sweep's top) instead of "
                "solving every frequency in full, to fit",
                "the absorbers act through the modes kept; the level near the top of the sweep may move by a few percent",
                None, detail={"modes": count},
            )
        if rung == "symmetry":
            if inputs.domain != "part" or inputs.solve != "response":
                return None
            return fit.apply_generic(rung, self, ctx, inputs)
        return None

    def _set_size(self, ctx: SolveContext, inputs: AcousticInputs, size: float) -> None:
        ctx.plan.acoustic_size_mm = size
        if inputs.domain == "part":
            ctx.plan.size_mm = size

    @staticmethod
    def _error(per_wavelength: float) -> float:
        from cadgen._internal.fea.acoustic_ops import frequency_error

        return abs(frequency_error(per_wavelength))

    def symmetric_about(self, plane, inputs: AcousticInputs, ctx: SolveContext) -> bool:
        """A response in the part's own air whose every source, absorber, open face and check face is its own mirror
        image, with no point source or probe (a probe would have to sit on the plane)."""
        if ctx.assembly is not None or inputs.domain != "part" or inputs.solve != "response" or inputs.probes:
            return False
        if any(source.point_mm is not None for source in inputs.sources):
            return False

        def onto_itself(refs) -> bool:
            ordinals = {ctx.ordinal_of[ref] for ref in refs}
            return {plane.mirror.get(o) for o in ordinals} == ordinals

        groups = [s.faces for s in inputs.sources] + [a.faces for a in inputs.absorbers]
        groups += [inputs.open_faces] if inputs.open_faces else []
        checks = ctx.study.checks if ctx.study is not None else ()
        groups += [tuple(check["faces"]) for check in checks if check.get("faces")]
        return all(onto_itself(group) for group in groups)

    def governing(self, result: AnalysisResult):
        if self._solve == "modes":
            return abs(result.fields["sound_pressure"]), result.scalars["frequencies_Hz"][0]
        envelope = result.scalars["level_envelope"]
        return envelope, float(envelope.max())

    # -- solve ---------------------------------------------------------------------------------------

    def _build(self, ctx: SolveContext, inputs: AcousticInputs, warnings: list[str]) -> _Air:
        import numpy as np

        from cadgen._internal.fea import acoustic_ops

        if ctx.assembly is not None:
            raise ValueError("an acoustic study solves one part: name it with --occurrence (#o1.2), or fuse the parts into one")
        size = self._air_size(ctx, inputs)
        top = self._top_Hz(ctx, inputs)
        box = self._part_box(ctx)
        centre = tuple(0.5 * (a + b) for a, b in zip(*box))
        if inputs.domain == "part":
            region = acoustic_ops.part_region(ctx.space, ctx.volume, centre)
        else:
            geometry = ctx.geometry
            refs = {face.ordinal: face.ref for face in geometry.faces}
            pad = self._pad_mm(ctx, inputs)
            if ctx.log:
                ctx.log(f"acoustic: meshing the air {inputs.domain} the part at {size:.3g} mm")
            region = acoustic_ops.build_air(geometry.shape, inputs.domain, refs, pad_mm=pad, wall_mm=size,
                                            far_mm=self._far_mm(ctx, inputs))

        def rows(refs, where: str):
            ordinals = [ctx.ordinal_of[ref] for ref in refs]
            mask = region.rows_on(ordinals)
            dry = [ref for ref, o in zip(refs, ordinals) if not region.rows_on([o]).any()]
            if dry:
                place = {"inside": "the air inside the part", "outside": "the air around the part"}.get(inputs.domain, "the air")
                raise ValueError(f"{where}: {', '.join(dry)} {'does' if len(dry) == 1 else 'do'} not touch {place}; "
                                 "choose a face the air is against")
            return mask

        velocity_rows = [(rows(s.faces, f"sources[{i}]"), s.velocity_mm_s * 1e-3)
                         for i, s in enumerate(inputs.sources) if s.faces]
        points = [(s.point_mm, s.volume_velocity_m3_s) for s in inputs.sources if s.point_mm is not None]
        absorbers = [(rows(a.faces, f"absorbers[{i}]"), a.admittance(inputs.fluid)) for i, a in enumerate(inputs.absorbers)]
        open_rows = rows(inputs.open_faces, "open") if inputs.open_faces else None
        ops = acoustic_ops.assemble(region, absorbers=absorbers, open_rows=open_rows, sources=velocity_rows, points=points,
                                    far=inputs.domain == "outside")
        air = _Air(region, ops, size, top)
        if inputs.probes:
            where = np.array([probe.at_mm for probe in inputs.probes], dtype=float)
            if region.box is not None:
                low, high = (np.array(corner) for corner in region.box)
                c = np.array(region.centre_mm)
                for i, point in enumerate(where):
                    if (point < low).any() or (point > high).any():
                        # Out past the box: read on the ray from the centre just inside the box, carried out by 1/r.
                        d = point - c
                        reach = min(((high[a] if d[a] > 0 else low[a]) - c[a]) / d[a] for a in range(3) if abs(d[a]) > 1e-12)
                        where[i] = c + 0.97 * reach * d
                        air.probe_extrapolated.append(i)
            P, inside = acoustic_ops.probe_matrix(region.space, where)
            missing = [inputs.probes[i].label for i in np.flatnonzero(~inside)]
            if missing:
                raise ValueError(f"probes: {', '.join(repr(m) for m in missing)} {'is' if len(missing) == 1 else 'are'} not in the "
                                 "air (inside the part's solid, or outside the air); move it into the air")
            air.probe, air.probe_inside = P, where
        per = inputs.fluid.wavelength_mm(top) / size
        # Said once: by the ladder's step when it coarsened the air, else here (a study that asked for a coarse mesh).
        if per < ELEMENTS_PER_WAVELENGTH * 0.95 and "local_refine" not in (ctx.plan.taken or ()):
            warnings.append(f"the air is meshed at {per:.1f} elements per wavelength at {_hz(top)}, under "
                            f"{ELEMENTS_PER_WAVELENGTH:g}: frequencies and levels near the top may be off by about "
                            f"{100 * self._error(per):.1f}%")
        return air

    def solve(self, ctx: SolveContext, inputs: AcousticInputs) -> AnalysisResult:
        import time

        warnings: list[str] = []
        started = time.perf_counter()
        air = self._build(ctx, inputs, warnings)
        timings = {"air_s": time.perf_counter() - started}
        if inputs.solve == "modes":
            result = self._modes(ctx, inputs, air, warnings, timings)
        else:
            result = self._response(ctx, inputs, air, warnings, timings)
        region = air.region
        result.scalars["air_mesh"] = {
            "domain": inputs.domain, "elements": int(len(region.volume.tets)), "dofs": int(region.space.scalar_count),
            "size_mm": round(air.size_mm, 4), "top_Hz": round(air.top_Hz, 4),
            "elements_per_wavelength": round(inputs.fluid.wavelength_mm(air.top_Hz) / air.size_mm, 3),
        }
        if region.box is not None:
            result.scalars["air_mesh"]["box_mm"] = [[round(c, 4) for c in corner] for corner in region.box]
        result.scalars["analysis_warnings"] = list(warnings)
        result.scalars["analysis_extras"] = {"acoustic": {"solve": inputs.solve, "domain": inputs.domain}}
        if inputs.domain == "inside" and region.wetted:
            # The air closed inside the part is shown as its own solid: the part's faces it wets, alone. The part's
            # outside reads no pressure and would hide the air's.
            result.scalars["shown_faces"] = sorted(int(o) for o in region.wetted)
            result.scalars["analysis_extras"]["acoustic"]["shown"] = "air"
        # The mesh's resolution is a finding (and the ladder's step); the rest are the run's warnings too.
        result.warnings.extend(w for w in warnings if "elements per wavelength" not in w and w not in result.warnings)
        return result

    def _on_part(self, ctx: SolveContext, air: _Air, values):
        """Air nodal values on the part's nodes: the same nodes for the part's own air, else its wetted surface."""
        if air.region.kind == "part":
            return values
        from cadgen._internal.fea.acoustic_ops import to_part_surface

        return to_part_surface(air.region, ctx.space, ctx.volume, values)[0]

    def _base_result(self, ctx: SolveContext, fields: dict, **more) -> AnalysisResult:
        space = ctx.space
        return AnalysisResult(
            dof_locations=space.dof_locations, vertices=space.vertices, tets=space.tets,
            boundary_quadratic=space.boundary_quadratic, element_dofs=space.element_dofs, fields=fields, **more,
        )

    def _modes(self, ctx: SolveContext, inputs: AcousticInputs, air: _Air, warnings, timings) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import acoustic_ops

        started = time.perf_counter()
        wanted = max(int(getattr(ctx.plan, "modes", None) or inputs.modes), inputs.check_modes, 1)
        closed = air.ops.open_dofs is None
        iterative = ctx.plan.solver in ("iterative", "matrix_free")
        k2, vectors, how = acoustic_ops.cavity_modes(air.ops, wanted + (1 if closed else 0), iterative=iterative)
        timings["eigen_s"] = time.perf_counter() - started
        c = inputs.fluid.speed_m_s
        frequencies = c * np.sqrt(k2) / (2.0 * math.pi)
        uniform = False
        if closed and len(frequencies) and frequencies[0] < 1e-3 * max(frequencies[-1], 1e-9):
            frequencies, vectors, uniform = frequencies[1:], vectors[:, 1:], True
        frequencies, vectors = frequencies[:wanted], vectors[:, :wanted]
        if len(frequencies) < inputs.check_modes:
            raise ValueError(f"view.checks: a check names mode {inputs.check_modes}, but only {len(frequencies)} modes were found")
        frames = min(len(frequencies), int(getattr(ctx.budget, "max_frames", 24) or 24))
        shapes = []
        for column in vectors.T[:frames]:
            peak = int(np.abs(column).argmax())
            shape = column / column[peak] if column[peak] else column
            shapes.append(self._on_part(ctx, air, shape))
        if frames < len(frequencies):
            warnings.append(f"wrote the shapes of the first {frames} of {len(frequencies)} modes; every mode's frequency is in the summary")
        per_top = inputs.fluid.wavelength_mm(float(frequencies[-1])) / air.size_mm if len(frequencies) else math.inf
        if per_top < ELEMENTS_PER_WAVELENGTH * 0.95 and not any("elements per wavelength" in w for w in warnings):
            warnings.append(f"the highest mode found ({_hz(float(frequencies[-1]))}) has {per_top:.1f} elements per wavelength, "
                            f"under {ELEMENTS_PER_WAVELENGTH:g}: it may read about {100 * self._error(per_top):.1f}% high")
        series = Series(kind="mode", unit="Hz", default=0, frames=[
            SeriesFrame(value=float(i + 1), label=f"Mode {i + 1} · {_hz(float(f))}",
                        attributes={"sound_pressure": "_SOUND_PRESSURE" if i == 0 else f"_SOUND_PRESSURE_F{i}"})
            for i, f in enumerate(frequencies[:frames])
        ])
        result = self._base_result(
            ctx, {"sound_pressure": shapes[0]}, series=series, frame_fields={"sound_pressure": shapes},
            dofs=int(air.region.space.scalar_count), solver=f"{how}; quadratic Helmholtz", timings=timings,
            scalars={"frequencies_Hz": [float(f) for f in frequencies], "uniform_mode": uniform, "magnitudes": [abs(s) for s in shapes],
                     "per_wavelength_top": per_top},
        )
        return result

    def _grid(self, inputs: AcousticInputs, air: _Air, ctx: SolveContext, timings) -> tuple["np.ndarray", Any]:
        """The frequencies solved: the list given, or log-spaced over the sweep plus points around each cavity mode in it
        (a closed air's peaks fall there); and the modes when the response is built from them."""
        import time

        import numpy as np

        from cadgen._internal.fea import acoustic_ops

        if inputs.frequencies_Hz:
            return np.array(inputs.frequencies_Hz, dtype=float), None
        low, high = inputs.sweep_Hz
        grid = [np.geomspace(low, high, inputs.points)]
        modal = None
        if inputs.domain != "outside":
            started = time.perf_counter()
            c = inputs.fluid.speed_m_s
            count = self._modal_count(ctx, inputs) if getattr(ctx.plan, "acoustic_modal", False) else \
                max(4, int(4.0 * math.pi * (air.region.volume_mm3 or self._air_volume_mm3(ctx, inputs)) * 1e-9
                           * (1.2 * high / c) ** 3 / 3.0) + 6)
            count = min(count, max(air.ops.size - 3, 1))
            k2, vectors, _ = acoustic_ops.cavity_modes(air.ops, count, iterative=ctx.plan.solver in ("iterative", "matrix_free"))
            timings["modes_s"] = time.perf_counter() - started
            frequencies = c * np.sqrt(k2) / (2.0 * math.pi)
            zeta = max(inputs.loss_factor / 2.0, 1e-3)
            for f in frequencies:
                if low <= f <= high:
                    grid.append(f * (1.0 + zeta * np.array(MODE_POINTS, dtype=float)))
            if getattr(ctx.plan, "acoustic_modal", False):
                modal = (k2, vectors)
        out = np.unique(np.concatenate(grid))
        return out[(out >= low) & (out <= high)], modal

    def _response(self, ctx: SolveContext, inputs: AcousticInputs, air: _Air, warnings, timings) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import acoustic_ops
        from cadgen._internal.fea.analyses.harmonic import choose_frames

        fluid = inputs.fluid
        region = air.region
        ops = air.ops
        iterative = ctx.plan.solver in ("iterative", "matrix_free")
        rhs_at = None
        if inputs.from_harmonic:
            grid, modal, rhs_at = self._vibration(ctx, inputs, air)
        else:
            grid, modal = self._grid(inputs, air, ctx, timings)
        started = time.perf_counter()
        n = ops.size
        amplitudes = np.zeros((len(grid), n), dtype=np.float32)
        probes = np.zeros((len(grid), len(inputs.probes)), dtype=complex)
        if modal is not None:
            k2, Phi = modal
            reduced_abs = [(beta, Phi.T @ (B @ Phi)) for beta, B in ops.absorbers]
        for i, f in enumerate(grid):
            rhs = rhs_at(i) if rhs_at is not None else None
            if modal is not None:
                k = fluid.k(f)
                A = np.diag(k2.astype(complex)) - (k * k) * (1.0 - 1j * inputs.loss_factor) * np.eye(len(k2))
                for beta, B in reduced_abs:
                    A = A + (1j * k * beta) * B
                b = 1j * 2.0 * math.pi * f * fluid.density_kg_m3 * (Phi.T @ (ops.source if rhs is None else rhs))
                p = Phi @ np.linalg.solve(A, b)
            else:
                p = acoustic_ops.solve_frequency(ops, fluid, f, inputs.loss_factor, rhs=rhs, iterative=iterative, warnings=warnings)
            amplitudes[i] = np.abs(p)
            if air.probe is not None:
                probes[i] = air.probe @ p
        timings["sweep_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"acoustic: solved {len(grid)} frequencies in {timings['sweep_s']:.1f}s")
        # Probes read past the open-air box: carried out from just inside it by spherical spreading.
        if air.probe_extrapolated:
            c = np.array(region.centre_mm)
            for j in air.probe_extrapolated:
                inner = np.linalg.norm(air.probe_inside[j] - c)
                outer = np.linalg.norm(np.array(inputs.probes[j].at_mm) - c)
                phase = np.exp(-1j * np.array([fluid.k(f) for f in grid]) * (outer - inner) * 1e-3)
                probes[:, j] = probes[:, j] * (inner / outer) * phase
        reference = fluid.reference_Pa
        loudest = amplitudes.max(axis=1)
        curve = acoustic_ops.level_dB(loudest, reference)

        # Each sound_level check's peak over every frequency solved: over its faces, at its probes, or anywhere.
        study_checks = tuple(ctx.study.checks) if ctx.study is not None else ()
        peaks: dict[int, dict] = {}
        boundary = region.space.boundary_quadratic
        for index, check in enumerate(study_checks):
            if check.get("kind") != "sound_level":
                continue
            if check.get("probes"):
                columns = [next(j for j, probe in enumerate(inputs.probes) if probe.label == label) for label in check["probes"]]
                values = np.abs(probes[:, columns])
                i, j = np.unravel_index(int(values.argmax()), values.shape)
                peaks[index] = {"grid": int(i), "amplitude": float(values[i, j]), "at": inputs.probes[columns[j]].at_mm,
                                "ref": None, "probe": inputs.probes[columns[j]].label}
                continue
            if check.get("faces"):
                ordinals = sorted({ctx.ordinal_of[ref] for ref in check["faces"]})
                nodes = np.unique(boundary[region.rows_on(ordinals)])
                if len(nodes) == 0:
                    raise ValueError(f"view.checks[{index}]: {', '.join(check['faces'])} does not touch the air")
            else:
                nodes = np.arange(n)
            values = amplitudes[:, nodes]
            i, j = np.unravel_index(int(values.argmax()), values.shape)
            node = int(nodes[j])
            on = region.rows_on([o for o in region.wetted]) & (boundary == node).any(axis=1) if check.get("faces") else None
            ref = None
            if on is not None and on.any():
                ordinal = int(region.row_ordinal[on][0])
                ref = next((ref for ref in check["faces"] if ctx.ordinal_of[ref] == ordinal), None)
            peaks[index] = {"grid": int(i), "amplitude": float(values[i, j]),
                            "at": tuple(float(v) for v in region.space.dof_locations[node]), "ref": ref, "probe": None}

        frames_cap = int(getattr(ctx.budget, "max_frames", 24) or 24)
        if inputs.from_harmonic:
            indices = list(range(len(grid)))
        else:
            indices, _ = choose_frames(grid, curve, frames_cap, max(inputs.loss_factor / 2.0, 1e-3))
            forced = sorted({peak["grid"] for peak in peaks.values()} | {int(curve.argmax())})
            indices = sorted(set(indices) | set(forced))
            while len(indices) > frames_cap:
                spare = [i for i in indices if i not in forced]
                if not spare:
                    break
                indices.remove(spare[len(spare) // 2])
        frame_of = {grid_index: frame for frame, grid_index in enumerate(indices)}
        levels, pressures = [], []
        for i in indices:
            on_part = self._on_part(ctx, air, amplitudes[i].astype(float))
            pressures.append(on_part)
            levels.append(acoustic_ops.level_dB(on_part, reference))
        if air.region.kind != "part":
            # A dry face (the air does not touch it) reads silence, not the floor of a quiet one.
            wet = acoustic_ops.to_part_surface(region, ctx.space, ctx.volume, np.ones(n))[1]
            dry = np.setdiff1d(np.arange(ctx.space.scalar_count), wet)
            for level in levels:
                level[dry] = 0.0
        default = int(np.argmax([float(curve[i]) for i in indices]))
        series = Series(kind="frequency", unit="Hz", default=default, frames=[
            SeriesFrame(value=round(float(grid[i]), 6), label=_hz(float(grid[i])), attributes={
                "sound_level": "_SOUND_LEVEL" if frame == 0 else f"_SOUND_LEVEL_F{frame}",
                "sound_pressure": "_SOUND_PRESSURE" if frame == 0 else f"_SOUND_PRESSURE_F{frame}",
            })
            for frame, i in enumerate(indices)
        ])
        curves = {"max_level_dB": {"x": [round(float(f), 6) for f in grid], "x_unit": "Hz",
                                   "y": [round(float(v), 4) for v in curve], "y_unit": "dB"}}
        for j, probe in enumerate(inputs.probes):
            curves[f"level_dB {probe.label}"] = {
                "x": [round(float(f), 6) for f in grid], "x_unit": "Hz",
                "y": [round(float(v), 4) for v in acoustic_ops.level_dB(np.abs(probes[:, j]), reference)], "y_unit": "dB"}
        loudest_grid = int(curve.argmax())
        loudest_node = int(amplitudes[loudest_grid].argmax())
        result = self._base_result(
            ctx, {"sound_level": levels[0], "sound_pressure": pressures[0]}, series=series, frame_fields={"sound_level": levels, "sound_pressure": pressures},
            curves=curves, dofs=int(n), timings=timings,
            solver=("modal superposition of the air's modes" if modal is not None else
                    "GMRES + multigrid" if iterative else "direct (superlu)") + f" at {len(grid)} frequencies; quadratic Helmholtz",
            scalars={
                "grid_Hz": [float(f) for f in grid], "frame_Hz": [float(grid[i]) for i in indices], "frame_of": frame_of,
                "curve_dB": [float(v) for v in curve], "peaks": peaks,
                "loudest": {"level_dB": float(curve[loudest_grid]), "Hz": float(grid[loudest_grid]),
                            "amplitude_Pa": float(amplitudes[loudest_grid, loudest_node]),
                            "at": [float(v) for v in region.space.dof_locations[loudest_node]]},
                "probes": [{"label": probe.label, "at_mm": list(probe.at_mm),
                            "amplitude_Pa": [float(abs(v)) for v in probes[:, j]],
                            "extrapolated": j in air.probe_extrapolated} for j, probe in enumerate(inputs.probes)],
                "level_envelope": np.max(np.stack(levels), axis=0),
                "modal": modal is not None, "modes_kept": None if modal is None else int(modal[0].shape[0]),
            },
        )
        if ctx.plan.symmetry and ctx.plan.prepared is not None:
            self._unfold(ctx, result, list(ctx.plan.prepared.planes))
        return result

    def _vibration(self, ctx: SolveContext, inputs: AcousticInputs, air: _Air):
        """The harmonic's frames as the sweep, and at each the part's surface velocity into the air (m/s) as the source."""
        import numpy as np

        from cadgen._internal.fea import acoustic_ops

        from cadgen._internal.fea.analyses import get_analysis

        upstream = ctx.upstream["harmonic"]
        # The sidecar's `upstream` carries the harmonic's own summary, as the harmonic would write it.
        shaking = get_analysis("harmonic")
        upstream.scalars.setdefault("deformation_scale", shaking.deformation_scale(upstream, ctx.volume.bbox_diagonal, None))
        upstream.scalars.setdefault("summary", shaking.summary(upstream, inputs.harmonic, []))
        region = air.region
        frame_Hz = np.array(upstream.scalars["frame_Hz"], dtype=float)
        real = upstream.frame_fields["displacement"]
        imaginary = upstream.frame_fields["displacement_im"]
        harmonic = inputs.harmonic
        base = None
        if harmonic.excitation == "base":
            base = harmonic.amplitude_g * G0_MM_S2 * np.asarray(harmonic.direction, dtype=float)
        walls = region.row_ordinal > 0
        normals = acoustic_ops.wall_normals(region, walls)
        wall_mass = acoustic_ops.face_mass(region.space, walls)

        def rhs(i: int):
            omega = 2.0 * math.pi * frame_Hz[i]
            velocity = 1j * omega * (real[i] + 1j * imaginary[i])            # mm/s, relative to the base
            if base is not None:
                velocity = velocity + base[None, :] / (1j * omega)           # plus the base's own motion
            on_air = acoustic_ops.from_part_surface(region, ctx.space, ctx.volume, velocity)
            into_air = -np.einsum("ij,ij->i", on_air, normals) * 1e-3       # m/s, along the normal into the air
            return wall_mass @ into_air

        return frame_Hz, None, rhs

    def _unfold(self, ctx: SolveContext, result: AnalysisResult, planes) -> None:
        """The solved half (or quarter) mirrored back into the whole part, every frame with it."""
        import numpy as np

        from cadgen._internal.fea import symmetry

        volume = ctx.volume
        frames = len(result.frame_fields["sound_level"])
        for plane in reversed(planes):
            whole, keep = symmetry.unfold_volume(volume, plane)
            scalars = {f"{name}:{i}": result.frame_fields[name][i] for name in ("sound_level", "sound_pressure") for i in range(frames)}
            scalars["envelope"] = result.scalars["level_envelope"]
            locations, out, _, boundary, tets, elements, vertices = symmetry.unfold_fields(
                plane, result.vertices, result.dof_locations, keep, scalars=scalars, vectors={},
                boundary=result.boundary_quadratic, tets=result.tets, element_dofs=result.element_dofs,
            )
            result.frame_fields = {name: [out[f"{name}:{i}"] for i in range(frames)] for name in ("sound_level", "sound_pressure")}
            result.fields = {name: result.frame_fields[name][0] for name in ("sound_level", "sound_pressure")}
            result.scalars["level_envelope"] = np.asarray(out["envelope"])
            result.dof_locations, result.boundary_quadratic = locations, boundary
            result.tets, result.element_dofs, result.vertices = tets, elements, vertices
            volume = whole
        ctx.volume = volume

    def needs_finer(self, result: AnalysisResult, inputs: AcousticInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: AcousticInputs) -> dict:
        from cadgen._internal.fea.acoustic_ops import level_dB
        from cadgen._internal.fea.checks import check_status

        if check["kind"] == "frequency":
            return self._frequency_check(check, index, ctx, result)
        peak = result.scalars["peaks"][index]
        level = float(level_dB(peak["amplitude"], inputs.fluid.reference_Pa))
        limit = float(check["limit_dB"])
        ratio = 10.0 ** ((level - limit) / 20.0)
        close_at = 10.0 ** (-CLOSE_DB / 20.0)
        f = result.scalars["grid_Hz"][peak["grid"]]
        judged = {
            "kind": "sound_level", "label": check.get("label") or kinds.SOUND_LEVEL.default_label,
            "value": round(level, 4), "limit": limit, "unit": "dB", "ratio": round(ratio, 6), "close_at": round(close_at, 6),
            "status": check_status(ratio, close_at),
            "where": {"ref": peak["ref"], "at": [round(c, 3) for c in peak["at"]]},
            **({"faces": list(check["faces"])} if check.get("faces") else {}),
            **({"probes": list(check["probes"])} if check.get("probes") else {}),
            **({"probe": peak["probe"]} if peak["probe"] else {}),
        }
        frame = result.scalars["frame_of"].get(peak["grid"])
        judged["at"] = {"value": round(f, 4), "unit": "Hz", **({"frame": frame} if frame is not None else {})}
        return judged

    def _frequency_check(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult) -> dict:
        from cadgen._internal.fea.checks import check_status

        frequencies = result.scalars["frequencies_Hz"]
        label = check.get("label") or "Resonance"
        if "min_Hz" in check:
            mode = int(check.get("mode", 1))
            f = frequencies[mode - 1]
            ratio = check["min_Hz"] / f if f > 0 else math.inf
            judged = {"kind": "frequency", "label": label, "value": round(f, 4), "limit": check["min_Hz"], "unit": "Hz",
                      "ratio": round(min(ratio, 1e6), 6), "close_at": FREQUENCY_CLOSE, "status": check_status(ratio, FREQUENCY_CLOSE),
                      "mode": mode}
            frame = mode - 1
        else:
            low, high = check["avoid_Hz"]
            inside = [i for i, f in enumerate(frequencies) if low <= f <= high]
            frame = inside[0] if inside else min(range(len(frequencies)),
                                                 key=lambda i: min(abs(frequencies[i] - low), abs(frequencies[i] - high)))
            f = frequencies[frame]
            edge = low if abs(f - low) <= abs(f - high) else high
            gap = abs(f - edge)
            if inside:
                ratio, status = max(1.0 + gap / edge, 1.000001), "fails"
            else:
                ratio = max(0.0, 1.0 - gap / edge)
                status = "close" if ratio > FREQUENCY_CLOSE else "passes"
            judged = {"kind": "frequency", "label": label, "value": round(f, 4), "limit": edge, "unit": "Hz",
                      "ratio": round(ratio, 6), "close_at": FREQUENCY_CLOSE, "status": status, "mode": frame + 1,
                      "avoid_Hz": [low, high]}
        magnitudes = result.scalars["magnitudes"]
        if frame < len(magnitudes):
            judged["at"] = {"frame": frame, "value": round(f, 4), "unit": "Hz"}
            values = magnitudes[frame]
        else:
            values = magnitudes[0] * 0.0
        peak = kinds.field_max_over(values, (), boundary=result.boundary_quadratic, boundary_ordinal=ctx.volume.boundary_ordinal,
                                    locations=result.dof_locations, face_ref=ctx.volume.faces, ordinal_of=ctx.ordinal_of,
                                    where=f"view.checks[{index}]")
        judged["where"] = {"ref": peak.ref, "at": [round(c, 3) for c in peak.at]}
        return judged

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: AcousticInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        found: list[dict] = []
        for check in check_results:
            if check["status"] == "passes":
                continue
            fails = check["status"] == "fails"
            item = [{"text": check["label"], **check["where"]}]
            if check["kind"] == "sound_level":
                at = f" at {_hz(check['at']['value'])}"
                where = f" at '{check['probe']}'" if check.get("probe") else " on the checked faces" if check.get("faces") else ""
                found.append({
                    "check": "fea", "severity": "error" if fails else "warning",
                    "type": "too_loud" if fails else "sound_close_to_limit",
                    "summary": f"The sound reaches {level_words(check['value'])}{where}{at}, "
                               f"{'over' if fails else 'within 3 dB of'} the {level_words(check['limit'])} allowed ({check['label']})",
                    "description": f"peak level {check['value']:.4g} dB against a {check['limit']:g} dB limit "
                                   f"(re {inputs.fluid.reference_Pa * 1e6:g} µPa)",
                    "items": item,
                })
            else:
                mode, f = check["mode"], check["value"]
                if "avoid_Hz" in check:
                    low, high = check["avoid_Hz"]
                    summary = (f"Acoustic mode {mode} rings at {_hz(f)}, {'inside' if fails else 'close to'} the "
                               f"{low:g}–{high:g} Hz band to keep clear of ({check['label']})")
                else:
                    which = "first acoustic mode" if mode == 1 else f"acoustic mode {mode}"
                    summary = (f"The air's {which} is {_hz(f)}, {'under' if fails else 'within 10 % of'} the "
                               f"{check['limit']:g} Hz it must stay above ({check['label']})")
                found.append({"check": "fea", "severity": "error" if fails else "warning",
                              "type": "acoustic_resonance" if fails else "acoustic_resonance_close",
                              "summary": summary, "description": f"mode {mode} at {f:.4g} Hz", "items": item})
        scalars = result.scalars
        if inputs.solve == "modes":
            frequencies = scalars["frequencies_Hz"]
            if frequencies:
                found.append({"check": "fea", "severity": "info", "type": "first_acoustic_mode",
                              "summary": f"The air's first acoustic mode is {_hz(frequencies[0])}",
                              "description": "the lowest natural frequency of the air; a sound or vibration near it makes the "
                                             "air ring (a boom, a whistle)", "items": []})
            if scalars["uniform_mode"]:
                found.append({"check": "fea", "severity": "info", "type": "uniform_mode",
                              "summary": "The closed air's uniform mode (0 Hz, the whole volume squeezed at once) was left out",
                              "description": "a closed cavity with rigid walls has it; it is not a resonance", "items": []})
        else:
            loudest = scalars["loudest"]
            found.append({"check": "fea", "severity": "info", "type": "loudest",
                          "summary": f"Loudest {level_words(float(level_dB_of(loudest['amplitude_Pa'], inputs.fluid)))} at "
                                     f"{_hz(loudest['Hz'])} (re {inputs.fluid.reference_Pa * 1e6:g} µPa)",
                          "description": "the highest sound pressure level anywhere in the air over the sweep",
                          "items": [{"text": "loudest here", "ref": None, "at": [round(c, 3) for c in loudest["at"]]}]})
            outside = [p["label"] for p in scalars["probes"] if p["extrapolated"]]
            if outside:
                found.append({"check": "fea", "severity": "info", "type": "probe_extrapolated",
                              "summary": f"{', '.join(repr(o) for o in outside)} {'is' if len(outside) == 1 else 'are'} past the "
                                         "meshed air; read just inside its box and carried out by spherical spreading (1/r)",
                              "description": "exact for sound spreading from the part's centre, an estimate for any other",
                              "items": []})
        for warning in scalars.get("analysis_warnings", ()):
            if "elements per wavelength" in warning:
                found.append({"check": "fea", "severity": "warning", "type": "wave_resolution", "summary": warning[0].upper() + warning[1:],
                              "description": f"the mesh should have at least {ELEMENTS_PER_WAVELENGTH:g} quadratic elements per "
                                             "wavelength at the top frequency", "items": []})
        if inputs.domain == "outside":
            found.append({"check": "fea", "severity": "info", "type": "open_air_boundary",
                          "summary": "Open air ends at a first-order absorbing box: an approximation for sound that does not "
                                     "spread from the part's centre", "description": LIMITS[2], "items": []})
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        return None

    def summary(self, result: AnalysisResult, inputs: AcousticInputs, check_results: list[dict]) -> dict:
        scalars = result.scalars
        fluid = inputs.fluid
        summary: dict[str, Any] = {
            "solve": inputs.solve, "domain": inputs.domain,
            "fluid": {"name": fluid.name, "density_kg_m3": fluid.density_kg_m3, "speed_m_s": fluid.speed_m_s,
                      "reference_Pa": fluid.reference_Pa},
            "air_mesh": dict(scalars["air_mesh"]),
        }
        if inputs.solve == "modes":
            frequencies = scalars["frequencies_Hz"]
            summary.update({
                "modes": [{"mode": i + 1, "frequency_Hz": round(f, 4)} for i, f in enumerate(frequencies)],
                "first_frequency_Hz": round(frequencies[0], 4) if frequencies else None,
                "modes_requested": inputs.modes,
                "uniform_mode_left_out": bool(scalars["uniform_mode"]),
            })
        else:
            loudest = scalars["loudest"]
            summary.update({
                "frequencies": len(scalars["grid_Hz"]),
                "sweep_Hz": list(inputs.sweep_Hz) if inputs.sweep_Hz else [min(inputs.frequencies_Hz), max(inputs.frequencies_Hz)],
                "loss_factor": inputs.loss_factor,
                "peak_level_dB": round(loudest["level_dB"], 4),
                "peak_Hz": round(loudest["Hz"], 4),
                "peak_pressure_Pa": float(f"{loudest['amplitude_Pa']:.6g}"),
                "peak_at_mm": [round(c, 3) for c in loudest["at"]],
                "max_level_dB": round(float(max(level.max() for level in result.frame_fields["sound_level"])), 4),
                "min_level_dB": round(float(min(level.min() for level in result.frame_fields["sound_level"])), 4),
                "max_pressure_Pa": float(f"{max(float(p.max()) for p in result.frame_fields['sound_pressure']):.6g}"),
                "probes": [],
                "method": "modal" if scalars["modal"] else "direct",
                **({"modes_kept": scalars["modes_kept"]} if scalars["modal"] else {}),
                "from": "harmonic" if inputs.from_harmonic else None,
            })
            from cadgen._internal.fea.acoustic_ops import level_dB

            for probe in scalars["probes"]:
                levels = level_dB(probe["amplitude_Pa"], fluid.reference_Pa)
                best = int(levels.argmax())
                summary["probes"].append({
                    "label": probe["label"], "at_mm": [round(c, 3) for c in probe["at_mm"]],
                    "peak_level_dB": round(float(levels[best]), 4), "peak_Hz": round(scalars["grid_Hz"][best], 4),
                    "peak_pressure_Pa": float(f"{probe['amplitude_Pa'][best]:.6g}"), "extrapolated": probe["extrapolated"],
                })
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} sound"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        if summary["solve"] == "modes":
            return {"sound_pressure": (-1.0, 1.0)}
        return {"sound_level": (summary["min_level_dB"], summary["max_level_dB"]), "sound_pressure": (0.0, summary["max_pressure_Pa"])}

    def extras_head(self, summary: dict) -> dict:
        if summary["solve"] == "modes":
            return {"first_frequency_Hz": summary["first_frequency_Hz"]}
        return {"peak_level_dB": summary["peak_level_dB"], "peak_Hz": summary["peak_Hz"]}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: AcousticInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        fluid = inputs.fluid
        acoustic: dict[str, Any] = {
            "solve": inputs.solve, "domain": inputs.domain,
            "fluid": {"name": fluid.name, "density_kg_m3": fluid.density_kg_m3, "speed_m_s": fluid.speed_m_s},
            "sources": [({"faces": bare(s.faces), "velocity_mm_s": s.velocity_mm_s} if s.faces else
                         {"point_mm": list(s.point_mm), "volume_velocity_m3_s": s.volume_velocity_m3_s}) for s in inputs.sources],
            "absorbers": [{"faces": bare(a.faces), **({"absorption": a.absorption} if a.absorption is not None else
                                                      {"impedance_rayl": a.impedance_rayl})} for a in inputs.absorbers],
            "open": [{"faces": bare(inputs.open_faces)}] if inputs.open_faces else [],
            "probes": [{"label": p.label, "at_mm": list(p.at_mm)} for p in inputs.probes],
        }
        if inputs.solve == "modes":
            acoustic["modes_requested"] = inputs.modes
        else:
            acoustic["loss_factor"] = inputs.loss_factor
            if inputs.sweep_Hz is not None:
                acoustic["sweep_Hz"] = list(inputs.sweep_Hz)
            if inputs.frequencies_Hz:
                acoustic["frequencies_Hz"] = list(inputs.frequencies_Hz)
        if inputs.from_harmonic:
            acoustic["from"] = "harmonic"
        echo: dict[str, Any] = {"acoustic": acoustic}
        if inputs.from_harmonic:
            from cadgen._internal.fea.analyses import get_analysis

            echo.update(get_analysis("harmonic").study_echo(inputs.harmonic, bare))
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        mesh = summary.get("air_mesh", {})
        where = {"part": "the part's own air", "inside": "the air inside the part", "outside": "the air around the part"}
        lines = []
        if summary.get("solve") == "modes":
            modes = summary.get("modes", [])
            if modes:
                lines.append(f"first acoustic mode {_hz(modes[0]['frequency_Hz'])}; modes "
                             + ", ".join(_hz(mode["frequency_Hz"]) for mode in modes))
            if summary.get("uniform_mode_left_out"):
                lines.append("the closed air's uniform mode (0 Hz) left out")
        else:
            reference = summary["fluid"]["reference_Pa"] * 1e6
            lines.append(f"loudest {level_words(summary['peak_level_dB'])} (re {reference:g} µPa) at {_hz(summary['peak_Hz'])}, "
                         f"{summary['peak_pressure_Pa']:.4g} Pa at {summary['peak_at_mm']} mm, over {summary['frequencies']} "
                         f"frequencies from {_hz(summary['sweep_Hz'][0])} to {_hz(summary['sweep_Hz'][1])}")
            for probe in summary.get("probes", []):
                lines.append(f"probe '{probe['label']}': peak {level_words(probe['peak_level_dB'])} at {_hz(probe['peak_Hz'])}"
                             + (" (carried out past the air box by 1/r)" if probe["extrapolated"] else ""))
        if mesh:
            lines.append(f"{where.get(summary.get('domain'), 'the air')}: {mesh['elements']} elements at {mesh['size_mm']:g} mm, "
                         f"{mesh['elements_per_wavelength']:.1f} per wavelength at {_hz(mesh['top_Hz'])}")
        return lines


def level_dB_of(amplitude_Pa: float, fluid) -> float:
    from cadgen._internal.fea.acoustic_ops import level_dB

    return float(level_dB(amplitude_Pa, fluid.reference_Pa))

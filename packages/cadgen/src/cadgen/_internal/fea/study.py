"""The study file: what ``cadgen fea solve`` is asked to compute.

A study is JSON (a path, an inline JSON string, or a dict from a library
caller) of this shape::

    {
      "analysis": "static",                      # optional; the default (analyses/__init__.py lists every one)
      "material": "aluminum-6061-t6",            # or {"name", "E_MPa", "nu", "yield_MPa"}
      "fixtures": [{"faces": ["#o1.f17"], "type": "fixed"}],
      "loads": [
        {"faces": ["#o1.f22"], "type": "force", "vector_N": [0, -500, 0]},
        {"faces": ["#o1.f3"], "type": "pressure", "pressure_MPa": 0.5}
      ],
      "mesh": {"size_mm": 2.5},                  # optional; default from the bounding box
      "output": {"deformation_scale": "auto"},   # optional; a number, or "auto"
      "margin": 2.0,                             # optional; the safety factor (>= 1) the part should keep
      "parts": {"post": {"material": "steel"}},   # assemblies: a material per part, by name or ref
      "connections": [{"between": ["post", "base"], "type": "free"}],  # assemblies: overrides of the bonded default
      "contact_tolerance_mm": 0.1,               # assemblies: faces this close are bonded
      "fit": {"memory_GB": 8, "seconds": 600, "allow": ["iterative"]},  # optional ladder targets and allowed rungs
      "view": {"checks": [...], "sections": [...], "controls": [...], "presets": [...], "show": {...}}  # optional
    }

That is the static study. ``analysis`` names another (modal, thermal, ...):
the keys above except ``fixtures`` and ``loads`` are common to every analysis
(:data:`COMMON_KEYS`), and each analysis reads its own (``study_keys``)
through its ``parse``. The view's checks, fields and drives, the mesh orders
and the connection types are the analysis's. A static load may also be a body
load, with no faces: ``{"type": "gravity", "vector_g": [0, 0, -1]}`` or
``{"type": "acceleration", "vector_g": [5, 0, 0]}`` (in g).

Face references are the viewer's own selectors (``#o1.f17``, or with the
document prefix ``part.step#o1.f17``); ``cadgen fea faces`` lists them. A
``force`` is the TOTAL force on its faces, spread as a uniform traction. A
``pressure`` acts along the inward normal (positive pushes on the surface).
The optional ``view`` is the agent's choice of what the viewer offers for the
result (see :func:`_view`): copied, checked, into the GLB and the sidecar.
Every check here is stdlib-only and runs before the kernel or the solver is
imported, so a malformed study fails in milliseconds with a message that
names the field.
"""

from __future__ import annotations

import json
import math
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import Rung
from cadgen._internal.fea.materials import Material, material_from_spec, requires

__all__ = [
    "CHECK_KINDS", "COMMON_KEYS", "Connection", "Fixture", "Load", "Study", "VIEW_SECTIONS", "parse_fixtures",
    "parse_loads", "parse_study",
]

FIXTURE_TYPES = ("fixed",)
LOAD_TYPES = ("force", "pressure")
#: Loads on the whole part, with no faces: a static study's gravity and acceleration (in g).
BODY_LOAD_TYPES = ("gravity", "acceleration")
#: The keys every analysis's study may carry; each analysis adds its own (``study_keys``).
COMMON_KEYS = (
    "analysis", "material", "mesh", "output", "margin", "parts", "connections", "contact_tolerance_mm", "view", "fit",
)
#: The ladder's rungs a study's ``fit.allow`` may name.
RUNGS = typing.get_args(Rung)
CONNECTION_TYPES = ("bonded", "free")
UNSUPPORTED_CONNECTION_TYPES = ("bolt", "contact")
#: What a view's control can move; the viewer knows how to apply each. `field` is an enum, the rest numbers.
VIEW_DRIVES = ("field", "deformation", "load_scale", "threshold")
#: Every drive any analysis offers: static's, then a series frame by mode (enum), a frame by its value (number),
#: and random vibration's sigma level (enum).
ALL_DRIVES = (*VIEW_DRIVES, "mode", "frame", "sigma")
#: The fields a result writes, as a view names them: outputs.py's `_VON_MISES` and `_DISPLACEMENT`.
VIEW_FIELDS = ("von_mises", "displacement")
#: What a view's check can judge; cadgen evaluates each (checks.py). With none, the stress check alone.
CHECK_KINDS = ("stress", "displacement")
DEFAULT_CHECKS = ({"kind": "stress"},)
_CHECK_KEYS = {"stress": {"kind", "margin", "label"}, "displacement": {"kind", "limit_mm", "faces", "label"}}
#: The parts of Study, in the order a view may list them; with no list, all four in this order.
VIEW_SECTIONS = ("verdict", "setup", "controls", "details")
#: When a control is shown: always, only while a check fails or is close, or only while every check passes.
CONTROL_WHEN = ("always", "failing", "passing")
# The controls the viewer shows when a view declares none: every field, and the exaggeration from
# zero up (its top is the viewer's, from the result's own scale, so a preset is held only to >= 0).
_DEFAULT_CONTROLS = {
    "field": {"drives": "field", "type": "enum", "options": list(VIEW_FIELDS)},
    "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
}
_CONTROL_KEYS = {
    "field": {"drives", "type", "label", "options", "default", "when"},
    "deformation": {"drives", "type", "label", "min", "max", "default", "unit", "when"},
    "load_scale": {"drives", "type", "label", "min", "max", "default", "unit", "when"},
    "threshold": {"drives", "type", "label", "field", "min", "max", "default", "unit", "when"},
    "mode": {"drives", "type", "label", "default", "when"},
    "frame": {"drives", "type", "label", "min", "max", "default", "unit", "when"},
    "sigma": {"drives", "type", "label", "options", "default", "when"},
}
_ENUM_DRIVES = ("field", "mode", "sigma")


@dataclass(frozen=True)
class Fixture:
    faces: tuple[str, ...]
    type: str = "fixed"


@dataclass(frozen=True)
class Load:
    faces: tuple[str, ...]
    type: str
    #: ``force``: the total force vector in N over all of ``faces``.
    vector: tuple[float, float, float] | None = None
    #: ``pressure``: MPa, positive pushing into the surface.
    pressure: float | None = None
    #: ``gravity`` / ``acceleration`` (no faces): the vector in g.
    vector_g: tuple[float, float, float] | None = None

    @property
    def body(self) -> bool:
        """A load on the whole part (gravity, acceleration), not on faces."""
        return self.type in BODY_LOAD_TYPES


@dataclass(frozen=True)
class Connection:
    """An override of how two parts are joined: by default every touching pair is bonded."""

    #: The two parts, each as the study named it (an occurrence ref or its name).
    between: tuple[str, str]
    type: str


@dataclass(frozen=True)
class Study:
    material: Material
    fixtures: tuple[Fixture, ...]
    loads: tuple[Load, ...]
    #: Target element size in mm; ``None`` derives one from the bounding box.
    mesh_size: float | None = None
    #: A multiplier on the displacement baked into the GLB, or ``None`` for auto.
    deformation_scale: float | None = None
    #: The safety factor the part should keep above yield; below it is a warning.
    margin: float = 2.0
    #: The raw document, echoed into the sidecar so a result names its inputs.
    source: dict = field(default_factory=dict, compare=False)
    #: Assemblies: the material of each part named in the study, as it named the part.
    parts: dict[str, Material] = field(default_factory=dict)
    #: Assemblies: overrides of the bonded default.
    connections: tuple[Connection, ...] = ()
    #: Assemblies: faces this close (or closer) count as touching.
    contact_tolerance_mm: float = 0.1
    #: What the viewer offers for the result (checks, sections, controls, presets, markers), checked; ``None`` for its defaults.
    view: dict | None = None
    #: The analysis's registry name.
    analysis: str = "static"
    #: What the analysis parsed of the study (its own keys); ``None`` only for a Study built by hand.
    inputs: Any = None
    #: The ladder's targets and allowed rungs (``memory_GB``, ``seconds``, ``allow``), checked; ``None`` for the defaults.
    fit: dict | None = None
    #: Element order: 2 (quadratic) unless the analysis allows and the study asks for 1.
    mesh_order: int = 2

    @property
    def face_refs(self) -> tuple[str, ...]:
        """The faces the study names (its fixtures and loads for static), each once."""
        if self.inputs is not None:
            return tuple(self.inputs.face_refs)
        return tuple(dict.fromkeys(ref for group in (*self.fixtures, *self.loads) for ref in group.faces))

    @property
    def surface_loads(self) -> tuple[Load, ...]:
        """The loads on faces (force, pressure): the solver's ``loads``."""
        return tuple(load for load in self.loads if not load.body)

    @property
    def body_loads(self) -> tuple[Load, ...]:
        """The loads on the whole part (gravity, acceleration)."""
        return tuple(load for load in self.loads if load.body)

    @property
    def checks(self) -> tuple[dict, ...]:
        """What the result is judged by: the view's checks, else the analysis's defaults (static: the stress check alone)."""
        checks = (self.view or {}).get("checks")
        if checks:
            return tuple(checks)
        if self.analysis == "static":
            return DEFAULT_CHECKS
        from cadgen._internal.fea.analyses import get_analysis

        return tuple(get_analysis(self.analysis).default_checks)

    @property
    def check_faces(self) -> tuple[str, ...]:
        """The faces the checks name (a displacement check over some faces), each once."""
        return tuple(dict.fromkeys(ref for check in self.checks for ref in check.get("faces", ())))


def _load_document(study: str | dict | Path) -> dict:
    if isinstance(study, dict):
        return study
    if isinstance(study, Path):
        return _read_json_file(study)
    text = str(study).strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"study: inline JSON does not parse: {exc}") from exc
    return _read_json_file(Path(text).expanduser())


def _read_json_file(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"study file does not exist: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"study file {path} does not parse as JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"study file {path} must hold one JSON object")
    return document


_faces = kinds.faces
_json_text = kinds.json_text
_number = kinds.number
_text = kinds.text


def _material(spec: Any) -> Material:
    return material_from_spec(spec)


def _parts(entries: Any) -> dict[str, Material]:
    if entries is None:
        return {}
    if not isinstance(entries, dict):
        raise ValueError('study.parts: expected an object like {"post": {"material": "steel"}}')
    parts = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict) or "material" not in entry:
            raise ValueError(f"parts[{name!r}]: expected an object with a 'material'")
        parts[str(name)] = _material(entry["material"])
    return parts


def _connections(entries: Any, types: tuple[str, ...] = CONNECTION_TYPES) -> tuple[Connection, ...]:
    if entries is None:
        return ()
    if not isinstance(entries, list):
        raise ValueError('study.connections: expected a list like [{"between": ["post", "base"], "type": "free"}]')
    connections = []
    for index, entry in enumerate(entries):
        where = f"connections[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected an object")
        between = entry.get("between")
        if (
            not isinstance(between, list) or len(between) != 2
            or not all(isinstance(name, str) and name.strip() for name in between)
        ):
            raise ValueError(f'{where}.between: name the two parts, like ["post", "base"]')
        kind = entry.get("type")
        if kind in UNSUPPORTED_CONNECTION_TYPES and kind not in types:
            raise ValueError(f"{where}.type: {kind!r} connections are not yet supported; use bonded or free")
        if kind not in types:
            raise ValueError(f"{where}.type: {kind!r} is not one of {types}")
        connections.append(Connection((between[0].strip(), between[1].strip()), kind))
    return tuple(connections)


@dataclass(frozen=True)
class _ViewSpec:
    """What an analysis lets a view name: its fields, drives, check kinds and default controls."""

    analysis: str
    fields: tuple[str, ...]
    drives: tuple[str, ...]
    checks: tuple
    default_controls: dict


def _view_spec(analysis) -> _ViewSpec:
    return _ViewSpec(
        analysis.name, tuple(spec.name for spec in analysis.fields), tuple(analysis.drives), tuple(analysis.checks),
        dict(analysis.default_controls),
    )


def _view_field(value: Any, *, where: str, fields: tuple[str, ...] = VIEW_FIELDS) -> str:
    if value not in fields:
        raise ValueError(f"{where}: {value!r} is not a field the result writes; use one of {list(fields)}")
    return value


def _control(entry: Any, *, where: str, spec: "_ViewSpec | None" = None) -> dict:
    fields = spec.fields if spec else VIEW_FIELDS
    drive_names = spec.drives if spec else VIEW_DRIVES
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"drives\": \"load_scale\", \"max\": 2}}")
    drives = entry.get("drives")
    if drives not in drive_names:
        raise ValueError(f"{where}.drives: {drives!r} is not one of {list(drive_names)}")
    unknown = set(entry) - _CONTROL_KEYS[drives]
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a {drives} control takes {sorted(_CONTROL_KEYS[drives])}")
    kind = "enum" if drives in _ENUM_DRIVES else "number"
    if entry.get("type", kind) != kind:
        raise ValueError(f"{where}.type: a {drives} control is a{'n' if kind == 'enum' else ''} {kind}, not {entry['type']!r}")
    control = {"drives": drives, "type": kind, **_text(entry, "label", where=where)}
    if "when" in entry:
        if entry["when"] not in CONTROL_WHEN:
            raise ValueError(f"{where}.when: {_json_text(entry['when'])} is not one of {list(CONTROL_WHEN)}")
        control["when"] = entry["when"]
    if drives == "field":
        options = entry.get("options", list(fields))
        if not isinstance(options, list) or not options:
            raise ValueError(f"{where}.options: list the fields it offers, like {list(fields)}")
        options = [_view_field(option, where=f"{where}.options", fields=fields) for option in options]
        default = entry.get("default", options[0])
        if default not in options:
            raise ValueError(f"{where}.default: default {default!r} is not one of its options {options}")
        return {**control, "options": options, "default": default}
    if drives == "mode":
        # Its options are the result's frames (labelled by the solve); a default is a 1-based mode number.
        if "default" in entry:
            default = entry["default"]
            if isinstance(default, bool) or not isinstance(default, int) or default < 1:
                raise ValueError(f"{where}.default: the mode it opens on, 1 for the first, got {_json_text(default)}")
            control["default"] = default
        return control
    if drives == "sigma":
        options = entry.get("options", [1, 3])
        if not isinstance(options, list) or not options or any(option not in (1, 3) or isinstance(option, bool) for option in options):
            raise ValueError(f"{where}.options: sigma levels from [1, 3]")
        default = entry.get("default", options[-1])
        if default not in options:
            raise ValueError(f"{where}.default: default {default!r} is not one of its options {options}")
        return {**control, "options": list(options), "default": default}
    if drives == "threshold":
        if entry.get("field") is None:
            raise ValueError(f"{where}.field: name the field it compares, one of {list(fields)}")
        control["field"] = _view_field(entry["field"], where=f"{where}.field", fields=fields)
    # A deformation with no range runs from none to four times the result's own exaggeration, which the
    # solve picks after the study is written; the viewer reads it from the file. A frame control with no
    # range spans the result's frames.
    if drives in ("deformation", "frame") and not {"min", "max", "default"} & set(entry):
        return {**control, **_text(entry, "unit", where=where)}
    if "max" not in entry:
        if drives == "deformation":
            raise ValueError(f"{where}.max: give the top of its range too, or leave min, max and default all out "
                             "to run from 0 to four times the result's own exaggeration")
        if drives == "frame":
            raise ValueError(f"{where}.max: give the top of its range too, or leave min, max and default all out "
                             "to span every frame of the result")
        raise ValueError(f"{where}.max: a {drives} control needs the top of its range")
    # A load_scale's bottom is a tenth of the load: at no load there is no stress and nothing to show.
    low = _number(entry.get("min", 0.1 if drives == "load_scale" else 0), where=f"{where}.min")
    high = _number(entry["max"], where=f"{where}.max")
    if drives == "load_scale" and not low > 0:
        raise ValueError(
            f"{where}.min: a load_scale control starts above no load; min ({low:g}) must be more than 0, like 0.1 for a tenth of the load"
        )
    if low < 0:
        raise ValueError(f"{where}.min: min ({low:g}) must be zero or more")
    if not low < high:
        raise ValueError(f"{where}: min ({low:g}) must be below max ({high:g})")
    control = {**control, "min": low, "max": high}
    # A deformation with no default opens at the result's own exaggeration, which the solve picks:
    # the viewer reads the file's. Otherwise the load as solved, where the range holds it, or the range's bottom.
    if drives == "deformation" and "default" not in entry:
        return {**control, **_text(entry, "unit", where=where)}
    fallback = min(max(1.0, low), high) if drives == "load_scale" else low
    default = _number(entry.get("default", fallback), where=f"{where}.default")
    if not low <= default <= high:
        raise ValueError(f"{where}: default ({default:g}) must be between min ({low:g}) and max ({high:g})")
    return {**control, "default": default, **_text(entry, "unit", where=where)}


def _preset(entry: Any, controls: dict[str, dict], *, where: str) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"label\": \"Landing\", \"load_scale\": 3}}")
    if not isinstance(entry.get("label"), str) or not entry["label"].strip():
        raise ValueError(f"{where}.label: name the preset as the person would, like \"Landing (3×)\"")
    preset = {"label": entry["label"].strip()}
    for key, value in entry.items():
        if key == "label":
            continue
        control = controls.get(key)
        if control is None:
            settable = ", ".join(["label", *sorted(controls)])
            raise ValueError(
                f"{where}: {key!r} is not a control of this view; a preset here can set only {settable}"
                " (declare a control in view.controls for a preset to set it)"
            )
        if control["type"] == "enum":
            options = control.get("options")
            if options is None:  # a mode: any frame number
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError(f"{where}.{key}: the mode number, 1 for the first, got {_json_text(value)}")
            elif value not in options:
                raise ValueError(f"{where}.{key}: {value!r} is not one of {options}")
            preset[key] = value
            continue
        number = _number(value, where=f"{where}.{key}")
        if control.get("max") is None:
            low = control.get("min", 0.0)
            if number < low:
                raise ValueError(f"{where}.{key}: {number:g} must be {low:g} or more")
            preset[key] = number
            continue
        if not control["min"] <= number <= control["max"]:
            raise ValueError(f"{where}.{key}: {number:g} must be between {control['min']:g} and {control['max']:g}")
        preset[key] = number
    return preset


def _checks(entries: Any, spec: "_ViewSpec | None" = None) -> list[dict]:
    specs = spec.checks if spec else (kinds.STRESS, kinds.DISPLACEMENT)
    if not isinstance(entries, list):
        raise ValueError('view.checks: expected a list like [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5}]')
    if not entries:
        if spec is None or spec.analysis == "static":
            raise ValueError("view.checks is empty: leave it out for the stress check alone")
        raise ValueError("view.checks is empty: leave it out for the analysis's default checks")
    checks = [kinds.parse_check(entry, specs, where=f"view.checks[{index}]") for index, entry in enumerate(entries)]
    for check_spec in specs:
        if check_spec.unique and sum(check["kind"] == check_spec.kind for check in checks) > 1:
            if check_spec.kind == "stress":
                raise ValueError("view.checks: only one stress check; it judges the weakest part already")
            raise ValueError(f"view.checks: only one {check_spec.kind} check")
    return checks


def _sections(entries: Any) -> list[str]:
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"view.sections: list the parts of Study to show, in order, from {list(VIEW_SECTIONS)}")
    for index, name in enumerate(entries):
        if name not in VIEW_SECTIONS:
            raise ValueError(f"view.sections[{index}]: {_json_text(name)} is not one of {list(VIEW_SECTIONS)}")
        if name in entries[:index]:
            raise ValueError(f"view.sections[{index}]: {name!r} is listed twice")
    return list(entries)


def _view(raw: Any, analysis=None) -> dict | None:
    """The study's ``view``, checked against ``analysis`` (static when ``None``): what the viewer offers for the result.

    ``controls`` are parameters in the viewer's generic schema (``type``,
    ``label``, ``min``, ``max``, ``default``, ``unit``, ``options``) plus
    ``drives``, which names what each moves, at most one each and only the
    drives the analysis offers: ``field`` (an enum of the fields the result
    writes), ``deformation`` (the exaggeration), ``load_scale`` (the load as a
    multiple of the solved one), ``threshold`` (values of its ``field`` under it
    are drawn grey), ``mode`` and ``frame`` (a series frame, by mode or by its
    value) and ``sigma`` (a random vibration's level), each shown ``when`` the
    checks say (``always``, ``failing``, ``passing``). ``checks`` are what the
    result is judged by (the analysis's kinds; cadgen evaluates them),
    ``sections`` the parts of Study in order. ``presets`` are named states over
    those controls, ``show`` whether the loads and fixtures are drawn and
    whether an assembly's Parts panel is shown (``parts``; by default only from
    six parts up). ``None`` when the study has none.
    """
    if raw is None:
        return None
    spec = _view_spec(analysis) if analysis is not None else None
    if not isinstance(raw, dict):
        raise ValueError('study.view: expected an object like {"checks": [...], "controls": [...], "show": {...}}')
    unknown = set(raw) - {"checks", "sections", "controls", "presets", "show"}
    if unknown:
        raise ValueError(f"view: unknown keys {sorted(unknown)}; expected checks, sections, controls, presets, show")
    view: dict = {}
    if "checks" in raw:
        view["checks"] = _checks(raw["checks"], spec)
    if "sections" in raw:
        view["sections"] = _sections(raw["sections"])
    entries = raw.get("controls", [])
    if not isinstance(entries, list):
        raise ValueError("view.controls: expected a list of controls")
    if "controls" in raw and not entries:
        raise ValueError("view.controls is empty: leave it out for the default controls")
    controls: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        control = _control(entry, where=f"view.controls[{index}]", spec=spec)
        if control["drives"] in controls:
            raise ValueError(f"view.controls[{index}]: only one control drives {control['drives']}")
        controls[control["drives"]] = control
    if "controls" in raw:
        view["controls"] = list(controls.values())
    if "presets" in raw:
        if not isinstance(raw["presets"], list):
            raise ValueError("view.presets: expected a list of named states")
        # With no controls declared the viewer shows the analysis's own, so a preset may set those.
        settable = controls or (spec.default_controls if spec else _DEFAULT_CONTROLS)
        view["presets"] = [_preset(entry, settable, where=f"view.presets[{index}]") for index, entry in enumerate(raw["presets"])]
    if "show" in raw:
        show = raw["show"]
        if not isinstance(show, dict):
            raise ValueError('view.show: expected an object like {"loads": true, "fixtures": true}')
        unknown = set(show) - {"loads", "fixtures", "parts"}
        if unknown:
            raise ValueError(f"view.show: unknown keys {sorted(unknown)}; expected loads, fixtures, parts")
        for key, value in show.items():
            if not isinstance(value, bool):
                raise ValueError(f"view.show.{key}: true or false, got {_json_text(value)}")
        view["show"] = dict(show)
    return view


def parse_fixtures(document: dict, *, required: bool = True) -> tuple[Fixture, ...]:
    """The study's ``fixtures``; ``required`` (static) refuses none, as a part with no fixture cannot be solved."""
    fixtures_in = document.get("fixtures")
    if not required and fixtures_in is None:
        return ()
    if not isinstance(fixtures_in, list) or (required and not fixtures_in):
        raise ValueError("study: 'fixtures' must list at least one {faces, type} entry; a part with no fixture cannot be solved")
    fixtures = []
    for index, entry in enumerate(fixtures_in):
        where = f"fixtures[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected an object")
        kind = str(entry.get("type", "fixed"))
        if kind not in FIXTURE_TYPES:
            raise ValueError(f"{where}.type: {kind!r} is not one of {FIXTURE_TYPES}")
        fixtures.append(Fixture(_faces(entry, where=where), kind))
    return tuple(fixtures)


def _vector(entry: dict, key: str, *, where: str, words: str) -> tuple[float, float, float]:
    vector = entry.get(key)
    if not isinstance(vector, list) or len(vector) != 3:
        raise ValueError(f"{where}.{key}: {words}")
    components = tuple(_number(v, where=f"{where}.{key}") for v in vector)
    return components  # type: ignore[return-value]


def parse_loads(document: dict, *, required: bool = True, body: bool = True) -> tuple[Load, ...]:
    """The study's ``loads``: forces and pressures on faces, plus (``body``) gravity and acceleration on the whole part."""
    loads_in = document.get("loads")
    if not required and loads_in is None:
        return ()
    if not isinstance(loads_in, list) or (required and not loads_in):
        raise ValueError("study: 'loads' must list at least one {faces, type, ...} entry")
    types = (*LOAD_TYPES, *BODY_LOAD_TYPES) if body else LOAD_TYPES
    loads = []
    for index, entry in enumerate(loads_in):
        where = f"loads[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected an object")
        kind = entry.get("type")
        if kind not in types:
            raise ValueError(f"{where}.type: {kind!r} is not one of {types}")
        if kind in BODY_LOAD_TYPES:
            unknown = set(entry) - {"type", "vector_g"}
            if unknown:
                raise ValueError(f"{where}: {kind} acts on the whole part, so it takes only type and vector_g, not {sorted(unknown)}")
            words = "gravity as [x, y, z] in g, like [0, 0, -1] for 1 g down" if kind == "gravity" else \
                "the part's acceleration as [x, y, z] in g, like [5, 0, 0]"
            vector = _vector(entry, "vector_g", where=where, words=words)
            if not any(vector):
                raise ValueError(f"{where}.vector_g: the {kind} is zero")
            loads.append(Load((), kind, vector_g=vector))
            continue
        faces = _faces(entry, where=where)
        if kind == "force":
            components = _vector(entry, "vector_N", where=where, words="a force needs [Fx, Fy, Fz] in newtons")
            if not any(components):
                raise ValueError(f"{where}.vector_N: the force is zero")
            loads.append(Load(faces, "force", vector=components))
        else:
            if "pressure_MPa" not in entry:
                raise ValueError(f"{where}.pressure_MPa: a pressure needs its magnitude in MPa")
            loads.append(Load(faces, "pressure", pressure=_number(entry["pressure_MPa"], where=f"{where}.pressure_MPa")))
    return tuple(loads)


def _fit(raw: Any) -> dict | None:
    """The study's ``fit``: the ladder's memory and time targets and the rungs it may take. Never a refusal."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError('study.fit: expected an object like {"memory_GB": 8, "seconds": 600, "allow": ["iterative"]}')
    unknown = set(raw) - {"memory_GB", "seconds", "allow"}
    if unknown:
        raise ValueError(f"fit: unknown keys {sorted(unknown)}; expected memory_GB, seconds, allow")
    fit: dict = {}
    for key in ("memory_GB", "seconds"):
        if key in raw:
            fit[key] = _number(raw[key], where=f"fit.{key}", positive=True)
    if "allow" in raw:
        allow = raw["allow"]
        if not isinstance(allow, list):
            raise ValueError(f"fit.allow: list the ways it may shrink the model, from {list(RUNGS)} ([] for none)")
        for index, rung in enumerate(allow):
            if rung not in RUNGS:
                raise ValueError(f"fit.allow[{index}]: {_json_text(rung)} is not one of {list(RUNGS)}")
        fit["allow"] = list(dict.fromkeys(allow))
    return fit


def parse_study(study: str | dict | Path | None) -> Study:
    """Validate a study document and return the typed :class:`Study`.

    The common keys are read here; the analysis's own through its ``parse``.
    """
    from cadgen._internal.fea.analyses import DEFAULT_ANALYSIS, get_analysis

    if study is None:
        raise ValueError(
            "a study is required: --study study.json (or inline JSON) naming the material, "
            "the fixed faces and the loads; run `cadgen fea faces IN.step` to list face refs"
        )
    document = _load_document(study)
    name = document.get("analysis", DEFAULT_ANALYSIS)
    if not isinstance(name, str):
        raise ValueError(f"study.analysis: expected the analysis's name, like \"modal\", got {_json_text(name)}")
    analysis = get_analysis(name)
    allowed = {*COMMON_KEYS, *analysis.study_keys}
    unknown = set(document) - allowed
    if unknown:
        order = [key for key in ("material", *sorted(analysis.study_keys)) if key in allowed] + [
            key for key in COMMON_KEYS if key not in ("analysis", "material")
        ]
        raise ValueError(f"study: unknown keys {sorted(unknown)}; {name} studies take {', '.join(['analysis', *order])}")
    material_required = getattr(analysis, "material_required", True)
    if "material" not in document and material_required:
        raise ValueError("study: 'material' is required (a table name or {E_MPa, nu, yield_MPa})")
    material = _material(document["material"]) if "material" in document else None

    inputs = analysis.parse(document)
    fixtures = tuple(getattr(inputs, "fixtures", ()))
    loads = tuple(getattr(inputs, "loads", ()))

    mesh = document.get("mesh") or {}
    if not isinstance(mesh, dict):
        raise ValueError("study.mesh: expected an object like {\"size_mm\": 2.5}")
    mesh_size = None
    if mesh.get("size_mm") is not None:
        mesh_size = _number(mesh["size_mm"], where="mesh.size_mm", positive=True)
    order = mesh.get("order", analysis.mesh_orders[0])
    if order not in analysis.mesh_orders or isinstance(order, bool):
        if tuple(analysis.mesh_orders) == (2,):
            raise ValueError("study.mesh.order: only quadratic (order 2) elements are supported")
        raise ValueError(f"study.mesh.order: {name} studies take order {' or '.join(map(str, analysis.mesh_orders))}")

    output = document.get("output") or {}
    if not isinstance(output, dict):
        raise ValueError("study.output: expected an object like {\"deformation_scale\": \"auto\"}")
    scale_in = output.get("deformation_scale", "auto")
    deformation_scale = None if scale_in in (None, "auto") else _number(scale_in, where="output.deformation_scale")

    margin = _number(document.get("margin", 2.0), where="margin", positive=True)
    if margin < 1:
        raise ValueError(f"margin: a safety factor below 1 means the part yields; must be >= 1, got {margin:g}")
    view = _view(document.get("view"), analysis)
    # A stress check's margin is the study's margin: one number, said once or said the same.
    stress = next((check for check in (view or {}).get("checks", ()) if check["kind"] == "stress"), {})
    if "margin" in stress:
        if "margin" in document and stress["margin"] != margin:
            raise ValueError(
                f"view.checks: the stress check's margin ({stress['margin']:g}) is not the study's margin ({margin:g}); give it once"
            )
        margin = stress["margin"]

    parts = _parts(document.get("parts"))
    connections = _connections(document.get("connections"), tuple(analysis.connection_types))
    tolerance = _number(document.get("contact_tolerance_mm", 0.1), where="contact_tolerance_mm")
    if tolerance < 0:
        raise ValueError(f"contact_tolerance_mm: must be zero or more, got {tolerance:g}")
    fit = _fit(document.get("fit"))

    # What the analysis needs of every material it will solve with, asked for by name.
    needs = (*sorted(analysis.material_needs), *sorted(getattr(inputs, "material_needs", ())))
    for each in ([material] if material is not None else []) + list(parts.values()):
        requires(each, needs, name)

    return Study(
        material, fixtures, loads, mesh_size, deformation_scale, margin, document,
        parts=parts, connections=connections, contact_tolerance_mm=tolerance, view=view,
        analysis=name, inputs=inputs, fit=fit, mesh_order=int(order),
    )

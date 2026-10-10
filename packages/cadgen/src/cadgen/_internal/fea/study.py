"""The study file: what ``cadgen fea solve`` is asked to compute.

A study is JSON (a path, an inline JSON string, or a dict from a library
caller) of this shape::

    {
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
      "view": {"controls": [...], "presets": [...], "show": {...}}  # optional; what the viewer offers
    }

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadgen._internal.fea.materials import Material, lookup_material

__all__ = ["Connection", "Fixture", "Load", "Study", "parse_study"]

FIXTURE_TYPES = ("fixed",)
LOAD_TYPES = ("force", "pressure")
CONNECTION_TYPES = ("bonded", "free")
UNSUPPORTED_CONNECTION_TYPES = ("bolt", "contact")
#: What a view's control can move; the viewer knows how to apply each. `field` is an enum, the rest numbers.
VIEW_DRIVES = ("field", "deformation", "load_scale", "threshold")
#: The fields a result writes, as a view names them: outputs.py's `_VON_MISES` and `_DISPLACEMENT`.
VIEW_FIELDS = ("von_mises", "displacement")
# The controls the viewer shows when a view declares none: every field, and the exaggeration from
# zero up (its top is the viewer's, from the result's own scale, so a preset is held only to >= 0).
_DEFAULT_CONTROLS = {
    "field": {"drives": "field", "type": "enum", "options": list(VIEW_FIELDS)},
    "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
}
_CONTROL_KEYS = {
    "field": {"drives", "type", "label", "options", "default"},
    "deformation": {"drives", "type", "label", "min", "max", "default", "unit"},
    "load_scale": {"drives", "type", "label", "min", "max", "default", "unit"},
    "threshold": {"drives", "type", "label", "field", "min", "max", "default", "unit"},
}


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
    #: What the viewer offers for the result (controls, presets, markers), checked; ``None`` for its defaults.
    view: dict | None = None

    @property
    def face_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ref for group in (*self.fixtures, *self.loads) for ref in group.faces))


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


def _faces(entry: dict, *, where: str) -> tuple[str, ...]:
    faces = entry.get("faces")
    if isinstance(faces, str):
        faces = [faces]
    if not isinstance(faces, list) or not faces or not all(isinstance(f, str) and f.strip() for f in faces):
        raise ValueError(f"{where}: 'faces' must be a non-empty list of face references like \"#o1.f17\"")
    return tuple(f.strip() for f in faces)


def _json_text(value: Any) -> str:
    """A value as the JSON an agent wrote it: true, null, "text", not Python's True, None, 'text'."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def _number(value: Any, *, where: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number, got {_json_text(value)}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{where}: expected a finite number, got {number}")
    if positive and not number > 0:
        raise ValueError(f"{where}: must be > 0, got {number}")
    return number


def _material(spec: Any) -> Material:
    if isinstance(spec, str):
        return lookup_material(spec)
    if not isinstance(spec, dict):
        raise ValueError("material: give a name from the table or an object with E_MPa, nu and yield_MPa")
    # An object may extend a table entry ({"name": "steel", "yield_MPa": 355}).
    base = None
    if isinstance(spec.get("name"), str):
        try:
            base = lookup_material(spec["name"])
        except ValueError:
            pass
    if base is None and not {"E_MPa", "nu", "yield_MPa"} <= set(spec):
        raise ValueError("material: an object needs E_MPa, nu and yield_MPa (density_t_per_mm3 optional)")
    E = _number(spec.get("E_MPa", base.E if base else None), where="material.E_MPa", positive=True)
    nu = _number(spec.get("nu", base.nu if base else None), where="material.nu")
    if not 0 <= nu < 0.5:
        raise ValueError(f"material.nu: Poisson's ratio must be in [0, 0.5), got {nu}")
    yield_strength = _number(
        spec.get("yield_MPa", base.yield_strength if base else None), where="material.yield_MPa", positive=True
    )
    density = _number(spec.get("density_t_per_mm3", base.density if base else 0.0), where="material.density_t_per_mm3")
    return Material(str(spec.get("name", base.name if base else "custom")), E, nu, yield_strength, density)


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


def _connections(entries: Any) -> tuple[Connection, ...]:
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
        if kind in UNSUPPORTED_CONNECTION_TYPES:
            raise ValueError(f"{where}.type: {kind!r} connections are not yet supported; use bonded or free")
        if kind not in CONNECTION_TYPES:
            raise ValueError(f"{where}.type: {kind!r} is not one of {CONNECTION_TYPES}")
        connections.append(Connection((between[0].strip(), between[1].strip()), kind))
    return tuple(connections)


def _text(entry: dict, key: str, *, where: str) -> dict:
    if key not in entry:
        return {}
    if not isinstance(entry[key], str) or not entry[key].strip():
        raise ValueError(f"{where}.{key}: expected a short piece of text")
    return {key: entry[key].strip()}


def _view_field(value: Any, *, where: str) -> str:
    if value not in VIEW_FIELDS:
        raise ValueError(f"{where}: {value!r} is not a field the result writes; use one of {list(VIEW_FIELDS)}")
    return value


def _control(entry: Any, *, where: str) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"drives\": \"load_scale\", \"max\": 2}}")
    drives = entry.get("drives")
    if drives not in VIEW_DRIVES:
        raise ValueError(f"{where}.drives: {drives!r} is not one of {list(VIEW_DRIVES)}")
    unknown = set(entry) - _CONTROL_KEYS[drives]
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a {drives} control takes {sorted(_CONTROL_KEYS[drives])}")
    kind = "enum" if drives == "field" else "number"
    if entry.get("type", kind) != kind:
        raise ValueError(f"{where}.type: a {drives} control is a{'n' if kind == 'enum' else ''} {kind}, not {entry['type']!r}")
    control = {"drives": drives, "type": kind, **_text(entry, "label", where=where)}
    if drives == "field":
        options = entry.get("options", list(VIEW_FIELDS))
        if not isinstance(options, list) or not options:
            raise ValueError(f"{where}.options: list the fields it offers, like {list(VIEW_FIELDS)}")
        options = [_view_field(option, where=f"{where}.options") for option in options]
        default = entry.get("default", options[0])
        if default not in options:
            raise ValueError(f"{where}.default: default {default!r} is not one of its options {options}")
        return {**control, "options": options, "default": default}
    if drives == "threshold":
        if entry.get("field") is None:
            raise ValueError(f"{where}.field: name the field it compares, one of {list(VIEW_FIELDS)}")
        control["field"] = _view_field(entry["field"], where=f"{where}.field")
    if "max" not in entry:
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
            if value not in control["options"]:
                raise ValueError(f"{where}.{key}: {value!r} is not one of {control['options']}")
            preset[key] = value
            continue
        number = _number(value, where=f"{where}.{key}")
        if control["max"] is None:
            if number < control["min"]:
                raise ValueError(f"{where}.{key}: {number:g} must be {control['min']:g} or more")
            preset[key] = number
            continue
        if not control["min"] <= number <= control["max"]:
            raise ValueError(f"{where}.{key}: {number:g} must be between {control['min']:g} and {control['max']:g}")
        preset[key] = number
    return preset


def _view(raw: Any) -> dict | None:
    """The study's ``view``, checked: what the viewer offers for the result.

    ``controls`` are parameters in the viewer's generic schema (``type``,
    ``label``, ``min``, ``max``, ``default``, ``unit``, ``options``) plus
    ``drives``, which names what each moves: ``field`` (an enum of the fields
    the result writes), ``deformation`` (the exaggeration), ``load_scale``
    (the load as a multiple of the solved one) or ``threshold`` (values of its
    ``field`` under it are drawn grey), at most one each. ``presets`` are
    named states over those controls, ``show`` whether the loads and fixtures
    are drawn. ``None`` when the study has none.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError('study.view: expected an object like {"controls": [...], "presets": [...], "show": {...}}')
    unknown = set(raw) - {"controls", "presets", "show"}
    if unknown:
        raise ValueError(f"view: unknown keys {sorted(unknown)}; expected controls, presets, show")
    view: dict = {}
    entries = raw.get("controls", [])
    if not isinstance(entries, list):
        raise ValueError("view.controls: expected a list of controls")
    if "controls" in raw and not entries:
        raise ValueError("view.controls is empty: leave it out for the default controls")
    controls: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        control = _control(entry, where=f"view.controls[{index}]")
        if control["drives"] in controls:
            raise ValueError(f"view.controls[{index}]: only one control drives {control['drives']}")
        controls[control["drives"]] = control
    if "controls" in raw:
        view["controls"] = list(controls.values())
    if "presets" in raw:
        if not isinstance(raw["presets"], list):
            raise ValueError("view.presets: expected a list of named states")
        # With no controls declared the viewer shows its own two, so a preset may set those.
        settable = controls or _DEFAULT_CONTROLS
        view["presets"] = [_preset(entry, settable, where=f"view.presets[{index}]") for index, entry in enumerate(raw["presets"])]
    if "show" in raw:
        show = raw["show"]
        if not isinstance(show, dict):
            raise ValueError('view.show: expected an object like {"loads": true, "fixtures": true}')
        unknown = set(show) - {"loads", "fixtures"}
        if unknown:
            raise ValueError(f"view.show: unknown keys {sorted(unknown)}; expected loads, fixtures")
        for key, value in show.items():
            if not isinstance(value, bool):
                raise ValueError(f"view.show.{key}: true or false, got {_json_text(value)}")
        view["show"] = dict(show)
    return view


def parse_study(study: str | dict | Path | None) -> Study:
    """Validate a study document and return the typed :class:`Study`."""
    if study is None:
        raise ValueError(
            "a study is required: --study study.json (or inline JSON) naming the material, "
            "the fixed faces and the loads; run `cadgen fea faces IN.step` to list face refs"
        )
    document = _load_document(study)
    unknown = set(document) - {
        "material", "fixtures", "loads", "mesh", "output", "margin", "parts", "connections", "contact_tolerance_mm", "view"
    }
    if unknown:
        raise ValueError(
            f"study: unknown keys {sorted(unknown)}; expected material, fixtures, loads, mesh, output, margin, "
            "parts, connections, contact_tolerance_mm, view"
        )
    if "material" not in document:
        raise ValueError("study: 'material' is required (a table name or {E_MPa, nu, yield_MPa})")
    material = _material(document["material"])

    fixtures_in = document.get("fixtures")
    if not isinstance(fixtures_in, list) or not fixtures_in:
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

    loads_in = document.get("loads")
    if not isinstance(loads_in, list) or not loads_in:
        raise ValueError("study: 'loads' must list at least one {faces, type, ...} entry")
    loads = []
    for index, entry in enumerate(loads_in):
        where = f"loads[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected an object")
        kind = entry.get("type")
        if kind not in LOAD_TYPES:
            raise ValueError(f"{where}.type: {kind!r} is not one of {LOAD_TYPES}")
        faces = _faces(entry, where=where)
        if kind == "force":
            vector = entry.get("vector_N")
            if not isinstance(vector, list) or len(vector) != 3:
                raise ValueError(f"{where}.vector_N: a force needs [Fx, Fy, Fz] in newtons")
            components = tuple(_number(v, where=f"{where}.vector_N") for v in vector)
            if not any(components):
                raise ValueError(f"{where}.vector_N: the force is zero")
            loads.append(Load(faces, "force", vector=components))
        else:
            if "pressure_MPa" not in entry:
                raise ValueError(f"{where}.pressure_MPa: a pressure needs its magnitude in MPa")
            loads.append(Load(faces, "pressure", pressure=_number(entry["pressure_MPa"], where=f"{where}.pressure_MPa")))

    mesh = document.get("mesh") or {}
    if not isinstance(mesh, dict):
        raise ValueError("study.mesh: expected an object like {\"size_mm\": 2.5}")
    mesh_size = None
    if mesh.get("size_mm") is not None:
        mesh_size = _number(mesh["size_mm"], where="mesh.size_mm", positive=True)
    if mesh.get("order", 2) != 2:
        raise ValueError("study.mesh.order: only quadratic (order 2) elements are supported")

    output = document.get("output") or {}
    if not isinstance(output, dict):
        raise ValueError("study.output: expected an object like {\"deformation_scale\": \"auto\"}")
    scale_in = output.get("deformation_scale", "auto")
    deformation_scale = None if scale_in in (None, "auto") else _number(scale_in, where="output.deformation_scale")

    margin = _number(document.get("margin", 2.0), where="margin", positive=True)
    if margin < 1:
        raise ValueError(f"margin: a safety factor below 1 means the part yields; must be >= 1, got {margin:g}")

    parts = _parts(document.get("parts"))
    connections = _connections(document.get("connections"))
    tolerance = _number(document.get("contact_tolerance_mm", 0.1), where="contact_tolerance_mm")
    if tolerance < 0:
        raise ValueError(f"contact_tolerance_mm: must be zero or more, got {tolerance:g}")

    return Study(
        material, tuple(fixtures), tuple(loads), mesh_size, deformation_scale, margin, document,
        parts=parts, connections=connections, contact_tolerance_mm=tolerance, view=_view(document.get("view")),
    )

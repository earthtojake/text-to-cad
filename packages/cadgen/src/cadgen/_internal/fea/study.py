"""The study file: what ``cadgen fea solve`` is asked to compute.

A study is JSON (a path, an inline JSON string, or a dict from a library
caller) of this shape::

    {
      "material": {"E_MPa": 68900, "nu": 0.33, "yield_MPa": 276},  # optional; the model's own material otherwise
      "fixtures": [{"faces": ["face 17"], "type": "fixed"}],
      "loads": [
        {"faces": ["face 22"], "type": "force", "vector_N": [0, -500, 0]},
        {"faces": ["face 3"], "type": "pressure", "pressure_MPa": 0.5}
      ],
      "mesh": {"size_mm": 2.5},                  # optional; default from the bounding box
      "output": {"deformation_scale": "auto"},   # optional; a number, or "auto"
      "margin": 2.0,                             # optional; the safety factor (>= 1) the part should keep, the stress check's
      "checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5}],  # optional; the stress check alone
      "parts": {"post": {"material": {...}}},    # assemblies: a part's own numbers, by name or ref
      "connections": [{"between": ["post", "base"], "type": "free"}],  # assemblies: overrides of the bonded default
      "contact_tolerance_mm": 0.1                # assemblies: faces this close are bonded
    }

A load may also be a body load, with no faces: ``{"type": "gravity", "vector_g": [0, 0, -1]}`` or ``{"type":
"acceleration", "vector_g": [5, 0, 0]}`` (in g).

Face references are the engine's refs, as the viewer copies them (``bracket/face 17``, or after the document's path, ``/work/bracket.step#bracket/face 17``); ``cadgen
fea faces`` lists them. A ``force`` is the TOTAL force on its faces, spread as a uniform traction. A ``pressure`` acts
along the inward normal (positive pushes on the surface). Every check here is stdlib-only and runs before the kernel
or the solver is imported, so a malformed study fails in milliseconds with a message that names the field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadgen._internal.fea.materials import Material, material_from_spec
from cadgen._internal.fea.values import faces as _faces, json_text as _json_text, number as _number, text as _text

__all__ = [
    "CHECK_KEYS", "CONTACT_TOLERANCE_MM", "STUDY_KEYS", "Connection", "Fixture", "Load", "Study", "parse_fixtures", "parse_loads", "parse_study",
]

#: A fixed face is held still; a roller face slides in its own plane but never moves along its normal (supports.py).
FIXTURE_TYPES = ("fixed", "roller")
LOAD_TYPES = ("force", "pressure")
#: Loads on the whole part, with no faces: gravity and acceleration (in g).
BODY_LOAD_TYPES = ("gravity", "acceleration")
#: Every key a study may carry.
STUDY_KEYS = (
    "material", "fixtures", "loads", "mesh", "output", "margin", "checks", "parts", "connections", "contact_tolerance_mm",
)
MESH_KEYS = ("size_mm", "refine")
OUTPUT_KEYS = ("deformation_scale",)
CONNECTION_TYPES = ("bonded", "free")
#: What a check can judge, and the keys each takes; cadgen evaluates each (checks.py).
CHECK_KEYS = {
    "stress": frozenset({"kind", "label"}),
    "displacement": frozenset({"kind", "label", "limit_mm", "faces"}),
}
DEFAULT_CHECKS = ({"kind": "stress"},)
#: Faces this close (or closer) count as touching, unless the study says otherwise (``contact_tolerance_mm``).
CONTACT_TOLERANCE_MM = 0.1
#: Standard gravity, mm/s^2 (operators.G0_MM_S2, kept here so parsing imports no numerics).
G0_MM_S2 = 9806.65


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
    #: The study's own material, or ``None``: each part is then solved with the model's (``materials``).
    material: Material | None
    fixtures: tuple[Fixture, ...]
    loads: tuple[Load, ...]
    #: Target element size in mm; ``None`` derives one from the bounding box.
    mesh_size: float | None = None
    #: A multiplier on the displacement baked into the GLB, or ``None`` for auto.
    deformation_scale: float | None = None
    #: The safety factor the part should keep above yield; below it is a warning.
    margin: float = 2.0
    #: The raw document, echoed into the result so it names its inputs.
    source: dict = field(default_factory=dict, compare=False)
    #: Assemblies: the study's own material of each part it names, as it named the part.
    parts: dict[str, Material] = field(default_factory=dict)
    #: Assemblies: overrides of the bonded default.
    connections: tuple[Connection, ...] = ()
    #: Assemblies: faces this close (or closer) count as touching.
    contact_tolerance_mm: float = CONTACT_TOLERANCE_MM
    #: What the result is judged by, checked: the stress check alone when the study names none.
    checks: tuple[dict, ...] = DEFAULT_CHECKS
    #: ``mesh.refine``: balls meshed finer, ``(centre (x, y, z), radius_mm, size_mm)`` each.
    mesh_refine: tuple = ()

    @property
    def face_refs(self) -> tuple[str, ...]:
        """The faces the fixtures and loads name, each once."""
        return tuple(dict.fromkeys(ref for group in (*self.fixtures, *self.loads) for ref in group.faces))

    @property
    def fixed_refs(self) -> tuple[str, ...]:
        """The faces the fixtures name, each once: what holds the part."""
        return tuple(dict.fromkeys(ref for fixture in self.fixtures for ref in fixture.faces))

    @property
    def surface_loads(self) -> tuple[Load, ...]:
        """The loads on faces (force, pressure): the solver's ``loads``."""
        return tuple(load for load in self.loads if not load.body)

    @property
    def body_loads(self) -> tuple[Load, ...]:
        """The loads on the whole part (gravity, acceleration)."""
        return tuple(load for load in self.loads if load.body)

    @property
    def body_accelerations(self) -> list[tuple[float, float, float]]:
        """Each body load as the acceleration b (mm/s^2) of ∫ ρ b·v: gravity is g, an accelerated part -a."""
        sign = {"gravity": 1.0, "acceleration": -1.0}
        return [tuple(sign[load.type] * G0_MM_S2 * c for c in load.vector_g) for load in self.body_loads]

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


def _closed(entry: dict, keys: tuple[str, ...], where: str) -> None:
    """``entry`` names only ``keys``: anything else is refused, naming what it takes."""
    unknown = set(entry) - set(keys)
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; it takes {', '.join(keys)}")


def _parts(entries: Any) -> dict[str, Material]:
    if entries is None:
        return {}
    if not isinstance(entries, dict):
        raise ValueError('study.parts: expected an object like {"post": {"material": {"E_MPa": 200000, "nu": 0.3, '
                         '"yield_MPa": 250}}}')
    parts = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict) or "material" not in entry:
            raise ValueError(f"parts[{name!r}]: expected an object with a 'material'")
        _closed(entry, ("material",), f"parts[{name!r}]")
        parts[str(name)] = material_from_spec(entry["material"])
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
        _closed(entry, ("between", "type"), where)
        kind = entry.get("type")
        if kind not in CONNECTION_TYPES:
            raise ValueError(f"{where}.type: {kind!r} is not one of {CONNECTION_TYPES}")
        connections.append(Connection((between[0].strip(), between[1].strip()), kind))
    return tuple(connections)


def _check(entry: Any, *, where: str) -> dict:
    """One ``checks`` entry: ``stress`` (held to the study's ``margin``) or ``displacement`` (``limit_mm``, over some
    ``faces``)."""
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"kind\": \"displacement\", \"limit_mm\": 0.5}}")
    kind = entry.get("kind")
    if kind not in CHECK_KEYS:
        raise ValueError(f"{where}.kind: {_json_text(kind)} is not a check this cadgen makes; use one of {list(CHECK_KEYS)}")
    unknown = set(entry) - CHECK_KEYS[kind]
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a {kind} check takes {sorted(CHECK_KEYS[kind])}")
    check = {"kind": kind, **_text(entry, "label", where=where)}
    if kind == "stress":
        return check
    if "limit_mm" not in entry:
        raise ValueError(f"{where}.limit_mm: a displacement check needs the most it may move, in mm")
    check["limit_mm"] = _number(entry["limit_mm"], where=f"{where}.limit_mm", positive=True)
    if "faces" in entry:
        check["faces"] = list(_faces(entry, where=where))
    return check


def _checks(entries: Any) -> tuple[dict, ...]:
    """The study's ``checks``, what the result is judged by; with none, the stress check alone."""
    if entries is None:
        return DEFAULT_CHECKS
    if not isinstance(entries, list):
        raise ValueError('study.checks: expected a list like [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5}]')
    if not entries:
        raise ValueError("study.checks is empty: leave it out for the stress check alone")
    checks = tuple(_check(entry, where=f"checks[{index}]") for index, entry in enumerate(entries))
    if sum(check["kind"] == "stress" for check in checks) > 1:
        raise ValueError("study.checks: only one stress check; it judges the weakest part already")
    return checks


def parse_fixtures(document: dict) -> tuple[Fixture, ...]:
    """The study's ``fixtures``: at least one, as a part with no fixture cannot be solved."""
    fixtures_in = document.get("fixtures")
    if not isinstance(fixtures_in, list) or not fixtures_in:
        raise ValueError("study: 'fixtures' must list at least one {faces, type} entry; a part with no fixture cannot be solved")
    fixtures = []
    for index, entry in enumerate(fixtures_in):
        where = f"fixtures[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected an object")
        _closed(entry, ("faces", "type"), where)
        kind = str(entry.get("type", "fixed"))
        if kind not in FIXTURE_TYPES:
            raise ValueError(f"{where}.type: {kind!r} is not one of {FIXTURE_TYPES}")
        fixtures.append(Fixture(_faces(entry, where=where), kind))
    return tuple(fixtures)


def _vector(entry: dict, key: str, *, where: str, words: str) -> tuple[float, float, float]:
    vector = entry.get(key)
    if not isinstance(vector, list) or len(vector) != 3:
        raise ValueError(f"{where}.{key}: {words}")
    return tuple(_number(v, where=f"{where}.{key}") for v in vector)  # type: ignore[return-value]


def parse_loads(document: dict) -> tuple[Load, ...]:
    """The study's ``loads``: forces and pressures on faces, gravity and acceleration on the whole part."""
    loads_in = document.get("loads")
    if not isinstance(loads_in, list) or not loads_in:
        raise ValueError("study: 'loads' must list at least one {faces, type, ...} entry")
    types = (*LOAD_TYPES, *BODY_LOAD_TYPES)
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
        _closed(entry, ("faces", "type", "vector_N" if kind == "force" else "pressure_MPa"), where)
        faces = _faces(entry, where=where)
        if kind == "force":
            components = _vector(entry, "vector_N", where=where, words="a force needs [Fx, Fy, Fz] in newtons")
            if not any(components):
                raise ValueError(f"{where}.vector_N: the force is zero")
            loads.append(Load(faces, "force", vector=components))
        else:
            if "pressure_MPa" not in entry:
                raise ValueError(f"{where}.pressure_MPa: a pressure needs its magnitude in MPa")
            pressure = _number(entry["pressure_MPa"], where=f"{where}.pressure_MPa")
            if pressure == 0:
                raise ValueError(f"{where}.pressure_MPa: the pressure is zero")
            loads.append(Load(faces, "pressure", pressure=pressure))
    return tuple(loads)


def _mesh_refine(raw) -> tuple:
    """``mesh.refine``: ``[{"center_mm": [x, y, z], "radius_mm": r, "size_mm": h}]``, each ball meshed at ``h``."""
    if raw is None:
        return ()
    example = '[{"center_mm": [0, 0, 0], "radius_mm": 3, "size_mm": 0.3}]'
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"study.mesh.refine: a list of balls to mesh finer, like {example}")
    balls = []
    for index, entry in enumerate(raw):
        where = f"mesh.refine[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"center_mm", "radius_mm", "size_mm"}:
            raise ValueError(f"{where}: give center_mm, radius_mm and size_mm, like {example[1:-1]}")
        centre = _vector(entry, "center_mm", where=where, words="the ball's centre as [x, y, z] in mm")
        radius = _number(entry["radius_mm"], where=f"{where}.radius_mm", positive=True)
        size = _number(entry["size_mm"], where=f"{where}.size_mm", positive=True)
        if (radius / size) ** 3 > 2e5:
            raise ValueError(f"{where}: a {radius:g} mm ball at {size:g} mm is too many local sizes to place; "
                             "make the ball smaller or the size larger")
        balls.append((centre, radius, size))
    return tuple(balls)


def refine_points(balls) -> list[list[float]]:
    """``mesh.refine``'s balls as a size field's points: a grid at each ball's size, inside it."""
    points = []
    for (x0, y0, z0), radius, size in balls:
        steps = int(radius // size)
        span = [k * size for k in range(-steps, steps + 1)]
        for dx in span:
            for dy in span:
                for dz in span:
                    if dx * dx + dy * dy + dz * dz <= radius * radius:
                        points.append([x0 + dx, y0 + dy, z0 + dz, size])
    return points


def _known(raw: Any, keys: tuple[str, ...], where: str, example: str) -> dict:
    """``raw``, an object naming only ``keys`` (empty when left out)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected an object like {example}")
    _closed(raw, keys, where)
    return raw


def parse_study(study: str | dict | Path | None) -> Study:
    """Validate a study document and return the typed :class:`Study`."""
    if study is None:
        raise ValueError(
            "a study is required: --study study.json (or inline JSON) naming the fixed faces and the "
            "loads; run `cadgen fea faces IN.step` to list face refs"
        )
    document = _load_document(study)
    unknown = set(document) - set(STUDY_KEYS)
    if unknown:
        raise ValueError(f"study: unknown keys {sorted(unknown)}; a study takes {', '.join(STUDY_KEYS)}")
    material = material_from_spec(document["material"]) if "material" in document else None
    fixtures = parse_fixtures(document)
    loads = parse_loads(document)

    mesh = _known(document.get("mesh"), MESH_KEYS, "study.mesh", '{"size_mm": 2.5}')
    mesh_size = None
    if mesh.get("size_mm") is not None:
        mesh_size = _number(mesh["size_mm"], where="mesh.size_mm", positive=True)
    refine = _mesh_refine(mesh.get("refine"))

    output = _known(document.get("output"), OUTPUT_KEYS, "study.output", '{"deformation_scale": "auto"}')
    scale_in = output.get("deformation_scale", "auto")
    deformation_scale = (None if scale_in in (None, "auto")
                         else _number(scale_in, where="output.deformation_scale", positive=True))

    margin = _number(document.get("margin", 2.0), where="margin", positive=True)
    if margin < 1:
        raise ValueError(f"margin: a safety factor below 1 means the part yields; must be >= 1, got {margin:g}")
    checks = _checks(document.get("checks"))

    parts = _parts(document.get("parts"))
    connections = _connections(document.get("connections"))
    tolerance = _number(document.get("contact_tolerance_mm", CONTACT_TOLERANCE_MM), where="contact_tolerance_mm")
    if tolerance < 0:
        raise ValueError(f"contact_tolerance_mm: must be zero or more, got {tolerance:g}")

    # A body load acts on the mass, so every material it is solved with needs a density (the model's own, once
    # read, by the solve).
    if any(load.body for load in loads):
        for each in [m for m in (material, *parts.values()) if m is not None]:
            if not each.density > 0:
                raise ValueError(
                    f"material: a gravity or acceleration load needs the density, and {each.name} has none; "
                    f'add density_t_per_mm3 to the material object, like {{"name": "{each.name}", "density_t_per_mm3": 7.85e-9}}'
                )

    return Study(
        material, fixtures, loads, mesh_size, deformation_scale, margin, document,
        parts=parts, connections=connections, contact_tolerance_mm=tolerance, checks=checks, mesh_refine=refine,
    )

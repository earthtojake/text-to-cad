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
      "output": {"deformation_scale": "auto"}    # optional; a number, or "auto"
    }

Face references are the viewer's own selectors (``#o1.f17``, or with the
document prefix ``part.step#o1.f17``); ``cadgen fea faces`` lists them. A
``force`` is the TOTAL force on its faces, spread as a uniform traction. A
``pressure`` acts along the inward normal (positive pushes on the surface).
Every check here is stdlib-only and runs before the kernel or the solver is
imported, so a malformed study fails in milliseconds with a message that
names the field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadgen._internal.fea.materials import Material, lookup_material

__all__ = ["Fixture", "Load", "Study", "parse_study"]

FIXTURE_TYPES = ("fixed",)
LOAD_TYPES = ("force", "pressure")


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
class Study:
    material: Material
    fixtures: tuple[Fixture, ...]
    loads: tuple[Load, ...]
    #: Target element size in mm; ``None`` derives one from the bounding box.
    mesh_size: float | None = None
    #: A multiplier on the displacement baked into the GLB, or ``None`` for auto.
    deformation_scale: float | None = None
    #: The raw document, echoed into the sidecar so a result names its inputs.
    source: dict = field(default_factory=dict, compare=False)

    @property
    def face_refs(self) -> tuple[str, ...]:
        seen: list[str] = []
        for group in (*self.fixtures, *self.loads):
            for ref in group.faces:
                if ref not in seen:
                    seen.append(ref)
        return tuple(seen)


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


def _number(value: Any, *, where: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number, got {value!r}")
    number = float(value)
    if positive and not number > 0:
        raise ValueError(f"{where}: must be > 0, got {number}")
    return number


def _material(spec: Any) -> Material:
    if isinstance(spec, str):
        return lookup_material(spec)
    if not isinstance(spec, dict):
        raise ValueError("material: give a name from the table or an object with E_MPa, nu and yield_MPa")
    base = lookup_material(spec["name"]) if "name" in spec and spec["name"].strip().lower() in _known_names() else None
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


def _known_names() -> set[str]:
    from cadgen._internal.fea.materials import MATERIALS, _ALIASES

    return set(MATERIALS) | set(_ALIASES)


def parse_study(study: str | dict | Path | None) -> Study:
    """Validate a study document and return the typed :class:`Study`."""
    if study is None:
        raise ValueError(
            "a study is required: --study study.json (or inline JSON) naming the material, "
            "the fixed faces and the loads; run `cadgen fea faces IN.step` to list face refs"
        )
    document = _load_document(study)
    unknown = set(document) - {"material", "fixtures", "loads", "mesh", "output"}
    if unknown:
        raise ValueError(f"study: unknown keys {sorted(unknown)}; expected material, fixtures, loads, mesh, output")
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

    return Study(material, tuple(fixtures), tuple(loads), mesh_size, deformation_scale, document)

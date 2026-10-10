"""The built-in isotropic material table for ``cadgen fea``.

Textbook room-temperature values for the alloys and polymers a desktop part is
usually made of. They are starting points, not certified data: a study that
matters names its own numbers through the study file's ``material`` object,
which overrides any field here. Units: MPa for E, yield, strength and the
plastic tangent; tonne/mm^3 for density (so mass = density x volume in mm^3 is
in tonnes; x1000 for kg); W/(m K) for conductivity, 1/K for expansion and
J/(kg K) for specific heat, the units people write them in (an analysis
converts them into the mm-N-s-tonne system it solves in).

A value the table does not know is ``None``, and :data:`NONE_REASONS` says why;
an analysis that needs it asks for it by name (:func:`requires`). Stdlib only.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MATERIALS", "MATERIAL_PROPERTIES", "NONE_REASONS", "TABLE_PROPERTIES", "Material", "lookup_material",
    "material_from_spec", "requires",
]


@dataclass(frozen=True)
class Material:
    name: str
    #: Young's modulus, MPa.
    E: float
    #: Poisson's ratio.
    nu: float
    #: Yield strength, MPa. Safety factor = yield / max von Mises.
    yield_strength: float
    #: tonne/mm^3.
    density: float
    #: Ultimate tensile strength, MPa (fatigue: Goodman).
    uts: float | None = None
    #: Fatigue (endurance) strength, MPa, at ``endurance_cycles`` fully reversed cycles.
    endurance: float | None = None
    endurance_cycles: float | None = None
    #: Thermal conductivity, W/(m K).
    conductivity: float | None = None
    #: Coefficient of linear thermal expansion, 1/K.
    expansion: float | None = None
    #: Specific heat capacity, J/(kg K).
    specific_heat: float | None = None
    #: Bilinear plastic tangent modulus, MPa (object only: nonlinear J2).
    tangent: float | None = None
    #: Hyperelastic model, object only: ``{"model": "neo_hookean", "mu_MPa": ..., "bulk_MPa": ...}``.
    hyperelastic: dict | None = field(default=None, hash=False)

    def as_dict(self) -> dict:
        out = {
            "name": self.name,
            "E_MPa": self.E,
            "nu": self.nu,
            "yield_MPa": self.yield_strength,
            "density_t_per_mm3": self.density,
        }
        for attribute, (key, _) in MATERIAL_PROPERTIES.items():
            value = getattr(self, attribute)
            if attribute not in _BASE and value is not None:
                out[key] = dict(value) if isinstance(value, dict) else value
        return out


#: Every property an analysis may need (its ``material_needs``): attribute -> (material-object key, plain words).
MATERIAL_PROPERTIES: dict[str, tuple[str, str]] = {
    "E": ("E_MPa", "Young's modulus"),
    "nu": ("nu", "Poisson's ratio"),
    "yield_strength": ("yield_MPa", "yield strength"),
    "density": ("density_t_per_mm3", "density"),
    "uts": ("uts_MPa", "ultimate tensile strength"),
    "endurance": ("endurance_MPa", "fatigue strength"),
    "endurance_cycles": ("endurance_cycles", "cycles its fatigue strength is quoted at"),
    "conductivity": ("conductivity_W_mK", "thermal conductivity"),
    "expansion": ("expansion_per_K", "thermal expansion coefficient"),
    "specific_heat": ("specific_heat_J_kgK", "specific heat"),
    "tangent": ("tangent_MPa", "plastic tangent modulus"),
    "hyperelastic": ("hyperelastic", "hyperelastic model"),
}
_BASE = ("E", "nu", "yield_strength", "density")
#: The properties every table entry carries, or explains the absence of in :data:`NONE_REASONS`.
TABLE_PROPERTIES = ("uts", "endurance", "endurance_cycles", "conductivity", "expansion", "specific_heat")
#: What an example of each property looks like, for the error that asks for one.
_EXAMPLE = {
    "density": "7.85e-9", "uts_MPa": "400", "endurance_MPa": "200", "endurance_cycles": "1e6",
    "conductivity_W_mK": "50", "expansion_per_K": "11.7e-6", "specific_heat_J_kgK": "486", "tangent_MPa": "2000",
}
_POLYMER_FATIGUE = (
    "polymers have no endurance limit, and their fatigue strength depends on frequency, temperature, "
    "moisture and (printed) layer orientation; give the grade's S-N point from its datasheet"
)

# Keyed by the lower-case name the study file may use; aliases below. Sources per value: references/materials.md.
MATERIALS: dict[str, Material] = {
    "steel": Material("Steel (structural, generic)", 200_000.0, 0.30, 250.0, 7.85e-9,
                      uts=400.0, endurance=200.0, endurance_cycles=1e6,
                      conductivity=50.0, expansion=11.0e-6, specific_heat=470.0),
    "stainless-304": Material("Stainless steel 304", 193_000.0, 0.29, 215.0, 8.00e-9,
                              uts=505.0, endurance=240.0, endurance_cycles=1e7,
                              conductivity=16.2, expansion=17.3e-6, specific_heat=500.0),
    "aluminum-6061-t6": Material("Aluminum 6061-T6", 68_900.0, 0.33, 276.0, 2.70e-9,
                                 uts=310.0, endurance=96.5, endurance_cycles=5e8,
                                 conductivity=167.0, expansion=23.6e-6, specific_heat=896.0),
    "aluminum-7075-t6": Material("Aluminum 7075-T6", 71_700.0, 0.33, 503.0, 2.81e-9,
                                 uts=572.0, endurance=159.0, endurance_cycles=5e8,
                                 conductivity=130.0, expansion=23.6e-6, specific_heat=960.0),
    "titanium-6al-4v": Material("Titanium Ti-6Al-4V", 113_800.0, 0.342, 880.0, 4.43e-9,
                                uts=950.0, endurance=510.0, endurance_cycles=1e7,
                                conductivity=6.7, expansion=8.6e-6, specific_heat=526.0),
    "brass": Material("Brass (C36000)", 97_000.0, 0.31, 310.0, 8.50e-9,
                      uts=393.0, endurance=138.0, endurance_cycles=1e8,
                      conductivity=116.0, expansion=20.5e-6, specific_heat=377.0),
    "abs": Material("ABS", 2_200.0, 0.35, 40.0, 1.04e-9,
                    uts=43.0, conductivity=0.17, expansion=90e-6, specific_heat=1200.0),
    "pla": Material("PLA", 3_500.0, 0.36, 60.0, 1.24e-9,
                    uts=60.0, conductivity=0.13, expansion=85e-6, specific_heat=1800.0),
    "nylon-pa12": Material("Nylon PA12", 1_700.0, 0.40, 48.0, 1.01e-9,
                           uts=48.0, conductivity=0.144, expansion=109e-6, specific_heat=2350.0),
    "petg": Material("PETG", 2_100.0, 0.38, 50.0, 1.27e-9,
                     uts=50.0, conductivity=0.20, expansion=68e-6, specific_heat=1100.0),
}

#: Why a table entry has no value for a property: (table key, attribute) -> the reason, as materials.md says it.
NONE_REASONS: dict[tuple[str, str], str] = {
    (key, attribute): _POLYMER_FATIGUE
    for key in ("abs", "pla", "nylon-pa12", "petg")
    for attribute in ("endurance", "endurance_cycles")
}

_ALIASES = {
    "6061": "aluminum-6061-t6",
    "6061-t6": "aluminum-6061-t6",
    "al6061": "aluminum-6061-t6",
    "aluminium-6061-t6": "aluminum-6061-t6",
    "aluminum": "aluminum-6061-t6",
    "aluminium": "aluminum-6061-t6",
    "7075": "aluminum-7075-t6",
    "7075-t6": "aluminum-7075-t6",
    "304": "stainless-304",
    "stainless": "stainless-304",
    "ss304": "stainless-304",
    "mild-steel": "steel",
    "titanium": "titanium-6al-4v",
    "ti-6al-4v": "titanium-6al-4v",
    "ti6al4v": "titanium-6al-4v",
    "nylon": "nylon-pa12",
    "pa12": "nylon-pa12",
}


def _key(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(" ", "-")


def lookup_material(name: str) -> Material:
    """The table entry for ``name`` (case-insensitive, common aliases), or a
    ValueError that lists what is available."""
    key = _key(name)
    key = _ALIASES.get(key, key)
    material = MATERIALS.get(key)
    if material is None:
        raise ValueError(
            f"unknown material {name!r}; one of {', '.join(sorted(MATERIALS))}, "
            "or give an object with E_MPa, nu and yield_MPa"
        )
    return material


def _json_text(value: Any) -> str:
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


def _optional(spec: dict, keys: tuple[str, ...], fallback: float | None, *, where: str) -> float | None:
    """The first of ``keys`` the object gives, as a positive number, else ``fallback`` (the table's)."""
    for key in keys:
        if key in spec:
            return _number(spec[key], where=f"{where}.{key}", positive=True)
    return fallback


def _hyperelastic(raw: Any) -> dict:
    where = "material.hyperelastic"
    if not isinstance(raw, dict):
        raise ValueError(f'{where}: expected an object like {{"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}}')
    if raw.get("model", "neo_hookean") != "neo_hookean":
        raise ValueError(f"{where}.model: {_json_text(raw.get('model'))} is not one of ['neo_hookean']")
    unknown = set(raw) - {"model", "mu_MPa", "bulk_MPa"}
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; it takes model, mu_MPa and bulk_MPa")
    for key in ("mu_MPa", "bulk_MPa"):
        if key not in raw:
            raise ValueError(f"{where}.{key}: a Neo-Hookean material needs mu_MPa (shear modulus) and bulk_MPa (bulk modulus)")
    return {
        "model": "neo_hookean",
        "mu_MPa": _number(raw["mu_MPa"], where=f"{where}.mu_MPa", positive=True),
        "bulk_MPa": _number(raw["bulk_MPa"], where=f"{where}.bulk_MPa", positive=True),
    }


def material_from_spec(spec: Any) -> Material:
    """The study's ``material``: a table name, or an object that gives the numbers or extends a table entry.

    An object may extend a table entry (``{"name": "steel", "yield_MPa": 355}``);
    one with no table name needs E_MPa, nu and yield_MPa. Every other property
    of :data:`MATERIAL_PROPERTIES` is optional and overrides the table's.
    ``fatigue_strength_MPa`` and ``fatigue_cycles`` are accepted for
    ``endurance_MPa`` and ``endurance_cycles``, and ``plasticity.tangent_MPa``
    for ``tangent_MPa``.
    """
    if isinstance(spec, str):
        return lookup_material(spec)
    if not isinstance(spec, dict):
        raise ValueError("material: give a name from the table or an object with E_MPa, nu and yield_MPa")
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

    def table(attribute: str) -> float | None:
        return getattr(base, attribute) if base else None

    plasticity = spec.get("plasticity")
    if plasticity is not None and (not isinstance(plasticity, dict) or set(plasticity) - {"tangent_MPa"}):
        raise ValueError('material.plasticity: expected an object like {"tangent_MPa": 2000}')
    tangent = _optional(spec, ("tangent_MPa",), table("tangent"), where="material")
    if plasticity:
        tangent = _optional(plasticity, ("tangent_MPa",), tangent, where="material.plasticity")
    if tangent is not None and not tangent < E:
        raise ValueError(f"material.tangent_MPa: the plastic tangent ({tangent:g} MPa) must be below E ({E:g} MPa)")
    return Material(
        str(spec.get("name", base.name if base else "custom")), E, nu, yield_strength, density,
        uts=_optional(spec, ("uts_MPa",), table("uts"), where="material"),
        endurance=_optional(spec, ("endurance_MPa", "fatigue_strength_MPa"), table("endurance"), where="material"),
        endurance_cycles=_optional(spec, ("endurance_cycles", "fatigue_cycles"), table("endurance_cycles"), where="material"),
        conductivity=_optional(spec, ("conductivity_W_mK",), table("conductivity"), where="material"),
        expansion=_optional(spec, ("expansion_per_K",), table("expansion"), where="material"),
        specific_heat=_optional(spec, ("specific_heat_J_kgK",), table("specific_heat"), where="material"),
        tangent=tangent,
        hyperelastic=_hyperelastic(spec["hyperelastic"]) if "hyperelastic" in spec else table("hyperelastic"),
    )


def requires(material: Material, needs: Iterable[str], analysis: str) -> None:
    """Raise a plain ValueError for the first property of ``needs`` the material lacks.

    ``needs`` are :data:`MATERIAL_PROPERTIES` attributes (an analysis's
    ``material_needs``). Density counts as missing at zero. The error names
    the property and the material-object key that supplies it.
    """
    for attribute in needs:
        if attribute not in MATERIAL_PROPERTIES:
            raise KeyError(f"{attribute!r} is not a material property; one of {sorted(MATERIAL_PROPERTIES)}")
        value = getattr(material, attribute)
        missing = value is None or (attribute == "density" and not value > 0)
        if not missing:
            continue
        key, words = MATERIAL_PROPERTIES[attribute]
        example = _EXAMPLE.get(key, _EXAMPLE.get(attribute, "..."))
        if attribute == "hyperelastic":
            example = '{"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}'
        raise ValueError(
            f"material: {analysis} studies need the {words}, and {material.name} has none; "
            f'add {key} to the material object, like {{"name": "{material.name}", "{key}": {example}}}'
        )

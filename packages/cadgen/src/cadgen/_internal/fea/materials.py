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
from dataclasses import dataclass, field, replace
from typing import Any

__all__ = [
    "CREEP_UNITS", "MATERIALS", "MATERIAL_PROPERTIES", "NONE_REASONS", "ORTHOTROPIC_KEYS", "TABLE_PROPERTIES", "Material",
    "lookup_material", "material_from_spec", "mirror_symmetric", "requires",
]


@dataclass(frozen=True)
class Material:
    name: str
    #: Young's modulus, MPa.
    E: float
    #: Poisson's ratio.
    nu: float
    #: Yield strength, MPa. Safety factor = yield / max von Mises. ``None`` only for a rubber given by its
    #: hyperelastic block alone, which has none.
    yield_strength: float | None
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
    #: Norton creep law, object only: ``{"A": ..., "n": ..., "m": 0, "units": "MPa, hours"}`` (strain rate A σ^n t^m).
    creep: dict | None = field(default=None, hash=False)
    #: Orthotropic stiffness, object only: E1_MPa..E3_MPa, nu12, nu13, nu23, G12_MPa..G23_MPa and ``axes``
    #: (directions 1 and 2, unit and perpendicular). Set, it replaces E and nu wherever the operators assemble
    #: stiffness; E and nu stay as its stand-in (E1, nu12) for what has no orthotropic path.
    orthotropic: dict | None = field(default=None, hash=False)
    #: Electrical resistivity, ohm m (electromagnetic: steady current; under 1 ohm m a conductor).
    resistivity: float | None = None
    #: Relative permittivity (dielectric constant), unitless (electromagnetic: electrostatics); none for a conductor.
    permittivity: float | None = None
    #: Relative magnetic permeability, unitless (electromagnetic: magnetostatics).
    permeability: float | None = None

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
    "creep": ("creep", "creep law (Norton A and n)"),
    "orthotropic": ("orthotropic", "orthotropic stiffness"),
    "resistivity": ("resistivity_ohm_m", "electrical resistivity"),
    "permittivity": ("relative_permittivity", "relative permittivity (dielectric constant)"),
    "permeability": ("relative_permeability", "relative magnetic permeability"),
}
_BASE = ("E", "nu", "yield_strength", "density")
#: The properties every table entry carries, or explains the absence of in :data:`NONE_REASONS`.
TABLE_PROPERTIES = ("uts", "endurance", "endurance_cycles", "conductivity", "expansion", "specific_heat",
                    "resistivity", "permittivity", "permeability")
#: What an example of each property looks like, for the error that asks for one.
_EXAMPLE = {
    "density": "7.85e-9", "yield_MPa": "10", "uts_MPa": "400", "endurance_MPa": "200", "endurance_cycles": "1e6",
    "conductivity_W_mK": "50", "expansion_per_K": "11.7e-6", "specific_heat_J_kgK": "486", "tangent_MPa": "2000",
    "resistivity_ohm_m": "1.7e-8", "relative_permittivity": "3.0", "relative_permeability": "1.0",
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

# Electrical and magnetic properties (electromagnetic), sources in references/materials.md "Electrical and
# magnetic": resistivity ohm m, relative permittivity, relative permeability. A metal conducts, so it has no
# permittivity; structural steel is ferromagnetic, so no single permeability holds for it.
_ELECTRICAL: dict[str, tuple[float, float | None, float | None]] = {
    "steel": (1.4368e-7, None, None),
    "stainless-304": (7.2e-7, None, 1.008),
    "aluminum-6061-t6": (3.99e-8, None, 1.000022),
    "aluminum-7075-t6": (5.15e-8, None, 1.000022),
    "titanium-6al-4v": (1.78e-6, None, 1.00005),
    "brass": (6.6312e-8, None, 1.0),
    "abs": (1e13, 3.1, 1.0),
    "pla": (1e14, 3.0, 1.0),
    "petg": (1e13, 2.6, 1.0),
    "nylon-pa12": (1e12, 3.8, 1.0),
}
MATERIALS.update({
    key: replace(material, resistivity=_ELECTRICAL[key][0], permittivity=_ELECTRICAL[key][1],
                 permeability=_ELECTRICAL[key][2])
    for key, material in MATERIALS.items() if key in _ELECTRICAL
})
_CONDUCTOR_PERMITTIVITY = (
    "a metal conducts, so it has no permittivity: in an electric study it is an equipotential (one voltage "
    "throughout), held or floating"
)
_FERROMAGNETIC = (
    "structural steel is ferromagnetic: its permeability depends on the field and saturates (Engineering Toolbox "
    "lists about 100 for carbon steel); give relative_permeability from the grade's B-H curve at the field expected"
)
NONE_REASONS.update({(key, "permittivity"): _CONDUCTOR_PERMITTIVITY for key, values in _ELECTRICAL.items() if values[1] is None})
NONE_REASONS[("steel", "permeability")] = _FERROMAGNETIC

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


#: The units a creep block's A may be given in: σ in MPa, the time (and the rate) per hour or per second.
CREEP_UNITS = {"mpa, hours": "MPa, hours", "mpa, hour": "MPa, hours", "mpa, h": "MPa, hours",
               "mpa, seconds": "MPa, seconds", "mpa, second": "MPa, seconds", "mpa, s": "MPa, seconds"}


def _creep(raw: Any) -> dict:
    """A Norton creep block: creep strain rate A σ^n t^m (σ in MPa), A and n required, m (time hardening) 0 by default."""
    where = "material.creep"
    example = '{"A": 1e-20, "n": 5, "m": 0, "units": "MPa, hours"}'
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected an object like {example}, from the grade's creep data at its temperature")
    unknown = set(raw) - {"A", "n", "m", "units", "temperature_C", "source"}
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; it takes A, n, m, units, temperature_C and source")
    for key in ("A", "n"):
        if key not in raw:
            raise ValueError(f"{where}.{key}: a Norton creep law needs A and n (creep strain rate = A σ^n), like {example}; "
                             "take them from the grade's creep data at the temperature it runs at")
    A = _number(raw["A"], where=f"{where}.A", positive=True)
    n = _number(raw["n"], where=f"{where}.n")
    if not 1.0 <= n <= 20.0:
        raise ValueError(f"{where}.n: the stress exponent must be from 1 to 20 (metals: about 3 to 8), got {n:g}")
    m = _number(raw.get("m", 0.0), where=f"{where}.m")
    if not -1.0 < m <= 0.0:
        raise ValueError(f"{where}.m: the time exponent must be over -1 and at most 0 (0 is steady creep), got {m:g}")
    units = raw.get("units", "MPa, hours")
    key = " ".join(units.lower().split()).replace(" ,", ",") if isinstance(units, str) else None
    if key not in CREEP_UNITS:
        raise ValueError(f'{where}.units: "MPa, hours" (A per hour, the stress in MPa) or "MPa, seconds", got {_json_text(units)}')
    out: dict = {"A": A, "n": n, "m": m, "units": CREEP_UNITS[key]}
    if "temperature_C" in raw:
        out["temperature_C"] = _number(raw["temperature_C"], where=f"{where}.temperature_C")
    if "source" in raw:
        if not isinstance(raw["source"], str) or not raw["source"].strip():
            raise ValueError(f"{where}.source: where the numbers come from, as a short piece of text")
        out["source"] = raw["source"].strip()
    return out


#: An orthotropic block's numbers: three moduli, three Poisson's ratios (nu_ij: contraction along j under stress along i),
#: three shear moduli. ``axes`` (optional) gives directions 1 and 2; 3 is 1 x 2.
ORTHOTROPIC_KEYS = ("E1_MPa", "E2_MPa", "E3_MPa", "nu12", "nu13", "nu23", "G12_MPa", "G13_MPa", "G23_MPa")


def _direction(raw: Any, where: str) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError(f"{where}: a direction as [x, y, z], like [1, 0, 0]")
    vector = [_number(c, where=where) for c in raw]
    size = math.sqrt(sum(c * c for c in vector))
    if not size > 0:
        raise ValueError(f"{where}: the direction is zero")
    return tuple(c / size for c in vector)  # type: ignore[return-value]


def _orthotropic(raw: Any) -> dict:
    """An orthotropic block, checked: every constant positive, the axes perpendicular, the compliance positive definite."""
    where = "material.orthotropic"
    example = ('{"E1_MPa": 135000, "E2_MPa": 10000, "E3_MPa": 10000, "nu12": 0.3, "nu13": 0.3, "nu23": 0.45, '
               '"G12_MPa": 5000, "G13_MPa": 5000, "G23_MPa": 3500}')
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected an object like {example}")
    unknown = set(raw) - {*ORTHOTROPIC_KEYS, "axes"}
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; it takes {', '.join(ORTHOTROPIC_KEYS)} and axes")
    missing = [key for key in ORTHOTROPIC_KEYS if key not in raw]
    if missing:
        raise ValueError(f"{where}: an orthotropic material needs all nine constants; missing {', '.join(missing)} (like {example})")
    out: dict = {}
    for key in ORTHOTROPIC_KEYS:
        out[key] = _number(raw[key], where=f"{where}.{key}", positive=key.endswith("_MPa"))
    axes = raw.get("axes", [[1, 0, 0], [0, 1, 0]])
    if not isinstance(axes, list) or len(axes) != 2:
        raise ValueError(f"{where}.axes: directions 1 and 2 as [[x, y, z], [x, y, z]], like [[1, 0, 0], [0, 1, 0]]")
    a1, a2 = _direction(axes[0], f"{where}.axes[0]"), _direction(axes[1], f"{where}.axes[1]")
    cosine = sum(p * q for p, q in zip(a1, a2))
    if abs(cosine) > 1e-6:
        raise ValueError(f"{where}.axes: directions 1 and 2 must be perpendicular (their cosine is {cosine:.3g})")
    # Exactly perpendicular, so 1, 2 and 1 x 2 are an orthonormal frame.
    a2 = tuple(q - cosine * p for p, q in zip(a1, a2))
    size = math.sqrt(sum(c * c for c in a2))
    out["axes"] = [list(a1), [c / size for c in a2]]
    E = (out["E1_MPa"], out["E2_MPa"], out["E3_MPa"])
    nu = {(0, 1): out["nu12"], (0, 2): out["nu13"], (1, 2): out["nu23"]}
    for (i, j), value in nu.items():
        # |nu_ij| < sqrt(Ei / Ej) for each pair, and the 3x3 normal compliance positive definite.
        if not abs(value) < math.sqrt(E[i] / E[j]):
            raise ValueError(f"{where}.nu{i + 1}{j + 1}: {value:g} is not physically possible with E{i + 1} and E{j + 1} "
                             f"(it must be under {math.sqrt(E[i] / E[j]):.3g} in size)")
    n12, n13, n23 = out["nu12"], out["nu13"], out["nu23"]
    n21, n31, n32 = n12 * E[1] / E[0], n13 * E[2] / E[0], n23 * E[2] / E[1]
    if not 1.0 - n12 * n21 - n23 * n32 - n13 * n31 - 2.0 * n21 * n32 * n13 > 0:
        raise ValueError(f"{where}: these Poisson's ratios with these moduli are not physically possible "
                         "(the material would gain energy when squeezed); check nu12, nu13 and nu23")
    return out


def mirror_symmetric(material: Material, axis: int) -> bool:
    """Whether the material is its own mirror image about a plane normal to global ``axis`` (0, 1, 2):
    always for an isotropic one; for an orthotropic one when that axis is one of its material directions."""
    own = getattr(material, "mirrors_onto_itself", None)
    if callable(own):  # a laminate's plies (laminate.LayeredMaterial)
        return bool(own(axis))
    block = getattr(material, "orthotropic", None)
    if not block:
        return True
    a1, a2 = block["axes"]
    a3 = (a1[1] * a2[2] - a1[2] * a2[1], a1[2] * a2[0] - a1[0] * a2[2], a1[0] * a2[1] - a1[1] * a2[0])
    return any(abs(abs(direction[axis]) - 1.0) < 1e-9 for direction in (a1, a2, a3))


def material_from_spec(spec: Any) -> Material:
    """The study's ``material``: a table name, or an object that gives the numbers or extends a table entry.

    An object may extend a table entry (``{"name": "steel", "yield_MPa": 355}``);
    one with no table name needs E_MPa, nu and yield_MPa. Every other property
    of :data:`MATERIAL_PROPERTIES` is optional and overrides the table's.
    ``fatigue_strength_MPa`` and ``fatigue_cycles`` are accepted for
    ``endurance_MPa`` and ``endurance_cycles``, and ``plasticity.tangent_MPa``
    for ``tangent_MPa`` (0 is perfectly plastic).

    A rubber needs no E, nu or yield: an object with a ``hyperelastic`` block
    and no table name takes its small-strain E and nu from the block's mu and
    bulk modulus, and has no yield strength (``None``) unless it gives one.
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
    hyperelastic = _hyperelastic(spec["hyperelastic"]) if "hyperelastic" in spec else None
    rubber = base is None and hyperelastic is not None
    orthotropic = _orthotropic(spec["orthotropic"]) if "orthotropic" in spec else None
    # An orthotropic object needs no E or nu (E1 and nu12 stand in for them) and no yield unless a stress check asks.
    aniso = base is None and orthotropic is not None and not rubber
    if base is None and not rubber and not aniso and not {"E_MPa", "nu", "yield_MPa"} <= set(spec):
        raise ValueError("material: an object needs E_MPa, nu and yield_MPa (density_t_per_mm3 optional)")
    if rubber:
        # A rubber's small-strain E and nu, from its shear and bulk moduli: what a linear analysis would use.
        mu, bulk = hyperelastic["mu_MPa"], hyperelastic["bulk_MPa"]
        default_E, default_nu = 9.0 * bulk * mu / (3.0 * bulk + mu), (3.0 * bulk - 2.0 * mu) / (2.0 * (3.0 * bulk + mu))
    elif aniso:
        default_E, default_nu = orthotropic["E1_MPa"], orthotropic["nu12"] if 0 <= orthotropic["nu12"] < 0.5 else 0.3
    else:
        default_E, default_nu = (base.E, base.nu) if base else (None, None)
    E = _number(spec.get("E_MPa", default_E), where="material.E_MPa", positive=True)
    nu = _number(spec.get("nu", default_nu), where="material.nu")
    if not 0 <= nu < 0.5:
        raise ValueError(f"material.nu: Poisson's ratio must be in [0, 0.5), got {nu}")
    if (rubber or aniso) and "yield_MPa" not in spec:
        yield_strength = None
    else:
        yield_strength = _number(
            spec.get("yield_MPa", base.yield_strength if base else None), where="material.yield_MPa", positive=True
        )
    density = _number(spec.get("density_t_per_mm3", base.density if base else 0.0), where="material.density_t_per_mm3")

    def table(attribute: str) -> float | None:
        return getattr(base, attribute) if base else None

    plasticity = spec.get("plasticity")
    if plasticity is not None and (not isinstance(plasticity, dict) or set(plasticity) - {"tangent_MPa"}):
        raise ValueError('material.plasticity: expected an object like {"tangent_MPa": 2000}')
    tangent = table("tangent")
    for source, where in ((spec, "material"), (plasticity or {}, "material.plasticity")):
        if "tangent_MPa" in source:
            tangent = _number(source["tangent_MPa"], where=f"{where}.tangent_MPa")
            if tangent < 0:
                raise ValueError(f"{where}.tangent_MPa: the slope past yield must be 0 (perfectly plastic) or more, got {tangent:g}")
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
        hyperelastic=hyperelastic if hyperelastic is not None else table("hyperelastic"),
        creep=_creep(spec["creep"]) if "creep" in spec else table("creep"),
        orthotropic=orthotropic if orthotropic is not None else table("orthotropic"),
        resistivity=_optional(spec, ("resistivity_ohm_m",), table("resistivity"), where="material"),
        permittivity=_optional(spec, ("relative_permittivity",), table("permittivity"), where="material"),
        permeability=_optional(spec, ("relative_permeability",), table("permeability"), where="material"),
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
        if attribute == "creep":
            example = '{"A": 1e-20, "n": 5, "m": 0, "units": "MPa, hours"}'
        raise ValueError(
            f"material: {analysis} studies need the {words}, and {material.name} has none; "
            f'add {key} to the material object, like {{"name": "{material.name}", "{key}": {example}}}'
        )

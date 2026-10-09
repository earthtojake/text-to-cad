"""The built-in isotropic material table for ``cadgen fea``.

Textbook room-temperature values for the alloys and polymers a desktop part is
usually made of. They are starting points, not certified data: a study that
matters names its own numbers through the study file's ``material`` object,
which overrides any field here. Units: MPa for E and yield, tonne/mm^3 for
density (so mass = density x volume in mm^3 is in tonnes; x1000 for kg).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Material", "MATERIALS", "lookup_material"]


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

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "E_MPa": self.E,
            "nu": self.nu,
            "yield_MPa": self.yield_strength,
            "density_t_per_mm3": self.density,
        }


# Keyed by the lower-case name the study file may use; aliases below.
MATERIALS: dict[str, Material] = {
    "steel": Material("Steel (structural, generic)", 200_000.0, 0.30, 250.0, 7.85e-9),
    "stainless-304": Material("Stainless steel 304", 193_000.0, 0.29, 215.0, 8.00e-9),
    "aluminum-6061-t6": Material("Aluminum 6061-T6", 68_900.0, 0.33, 276.0, 2.70e-9),
    "aluminum-7075-t6": Material("Aluminum 7075-T6", 71_700.0, 0.33, 503.0, 2.81e-9),
    "titanium-6al-4v": Material("Titanium Ti-6Al-4V", 113_800.0, 0.342, 880.0, 4.43e-9),
    "brass": Material("Brass (C36000)", 97_000.0, 0.31, 310.0, 8.50e-9),
    "abs": Material("ABS", 2_200.0, 0.35, 40.0, 1.04e-9),
    "pla": Material("PLA", 3_500.0, 0.36, 60.0, 1.24e-9),
    "nylon-pa12": Material("Nylon PA12", 1_700.0, 0.40, 48.0, 1.01e-9),
    "petg": Material("PETG", 2_100.0, 0.38, 50.0, 1.27e-9),
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

"""The isotropic material a ``cadgen fea`` study solves each part with.

A part's material is the model's own (``part.material = bd_materials.metals.aluminum()``), as the document holds
it: its modulus, Poisson's ratio and yield strength are native ``Range`` values, and a study reads the low end of
the yield (the safety factor against the weakest the material may be) and the middle of the modulus and the ratio
(which set the displacement, not whether the part holds). A study may give its own numbers instead
(``{"E_MPa", "nu", "yield_MPa"}``, a supplier's datasheet), which win over the document's. A part with neither is
refused: no table guesses an alloy from a name. Units: MPa for E and yield; tonne/mm^3 for density (so mass =
density x volume in mm^3 is in tonnes; x1000 for kg).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cadgen._internal.fea.values import number as _number

__all__ = ["MATERIAL_KEYS", "Material", "material_from_document", "material_from_spec"]


@dataclass(frozen=True)
class Material:
    name: str
    #: Young's modulus, MPa.
    E: float
    #: Poisson's ratio.
    nu: float
    #: Yield strength, MPa. Safety factor = yield / max von Mises.
    yield_strength: float
    #: tonne/mm^3; 0 when it is not given (a body load then asks for it).
    density: float
    #: Where the numbers are from: ``"study"`` (given in the study) or ``"document"`` (the model's material).
    source: str = "study"
    #: A document material's ranges each number was read from: ``{"E_MPa": [lo, hi], "nu": [...], "yield_MPa": [...]}``.
    ranges: dict = field(default_factory=dict, compare=False)

    def as_dict(self) -> dict:
        return {"name": self.name, "E_MPa": self.E, "nu": self.nu, "yield_MPa": self.yield_strength,
                "density_t_per_mm3": self.density, "source": self.source,
                **({"ranges": self.ranges} if self.ranges else {})}


#: The keys a material object takes.
MATERIAL_KEYS = ("name", "E_MPa", "nu", "yield_MPa", "density_t_per_mm3")


def material_from_spec(spec: Any) -> Material:
    """A study's own material: an object that gives E_MPa, nu and yield_MPa (density_t_per_mm3 and a name
    optional), every number the person's."""
    if not isinstance(spec, dict):
        raise ValueError("material: give an object with E_MPa, nu and yield_MPa (and density_t_per_mm3 for a body "
                         f"load), or leave it out to use the model's own material; got {spec!r}")
    unknown = set(spec) - set(MATERIAL_KEYS)
    if unknown:
        raise ValueError(f"material: unknown keys {sorted(unknown)}; a material object takes {', '.join(MATERIAL_KEYS)}")
    if not {"E_MPa", "nu", "yield_MPa"} <= set(spec):
        missing = sorted({"E_MPa", "nu", "yield_MPa"} - set(spec))
        raise ValueError(f"material: an object needs E_MPa, nu and yield_MPa (density_t_per_mm3 optional); "
                         f"it has no {', '.join(missing)}")
    E = _number(spec["E_MPa"], where="material.E_MPa", positive=True)
    nu = _number(spec["nu"], where="material.nu")
    if not 0 <= nu < 0.5:
        raise ValueError(f"material.nu: Poisson's ratio must be in [0, 0.5), got {nu}")
    yield_strength = _number(spec["yield_MPa"], where="material.yield_MPa", positive=True)
    density = _number(spec.get("density_t_per_mm3", 0.0), where="material.density_t_per_mm3")
    if density < 0:
        raise ValueError(f"material.density_t_per_mm3: must be zero or more, got {density:g}")
    name = spec.get("name", "Custom")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"material.name: a material's name is text, got {name!r}")
    return Material(" ".join(name.split()), E, nu, yield_strength, density)


def _bounds(physics: Any, key: str) -> tuple[float, float] | None:
    value = getattr(physics, key, None)
    low, high = getattr(value, "min", None), getattr(value, "max", None)
    if low is None or high is None or math.isnan(low) or math.isnan(high):
        return None
    return float(low), float(high)


def material_from_document(finished: Any, part: str) -> Material:
    """The model's material of ``part`` (a bd_materials ``FinishedMaterial``, as the document holds it): yield at
    its range's low end, the modulus and Poisson's ratio at their middles, the density as given. A part with none,
    or one whose material carries no modulus, ratio or yield (a STEP holds a material's name and density only), is
    refused, saying how to give one."""
    give = ('set part.material in its model to a bd_materials material and solve the model\'s .xbf, or give the '
            'study its own: "material": {"E_MPa": ..., "nu": ..., "yield_MPa": ...} (in "parts" for one part of an '
            'assembly)')
    if finished is None:
        raise ValueError(f"{part} has no material: {give}")
    physics = getattr(finished, "material", None)
    found = {key: _bounds(physics, key) for key in ("modulus_of_elasticity", "poisson_ratio", "yield_strength")}
    if missing := [key for key, bounds in found.items() if bounds is None]:
        raise ValueError(f"{part}'s material {finished.name} gives no {', '.join(missing)}: {give}")
    (e_low, e_high), (nu_low, nu_high), (yield_low, yield_high) = found.values()
    density = getattr(physics, "density", None)
    return Material(
        finished.name, (e_low + e_high) / 2 * 1000.0, (nu_low + nu_high) / 2, yield_low,
        0.0 if density is None or math.isnan(float(density)) else float(density) * 1e-12, source="document",
        ranges={"E_MPa": [e_low * 1000.0, e_high * 1000.0], "nu": [nu_low, nu_high], "yield_MPa": [yield_low, yield_high]},
    )

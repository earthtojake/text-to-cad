"""Editable provisional material properties; no structural allowables."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    name: str
    density_kg_m3: float
    provenance: str


cured_carbon_laminate = Material("cured carbon laminate", 1550.0, "project brief")
structural_foam_core = Material("structural foam core", 80.0, "project brief")
aluminum = Material("aluminum", 2700.0, "project brief")
provisional_glazing = Material("provisional glazing", 1200.0, "ESTIMATED")
rubberized_aluminum_grid = Material(
    "rubberized aluminum dog grid", 2900.0, "ESTIMATED composite density"
)

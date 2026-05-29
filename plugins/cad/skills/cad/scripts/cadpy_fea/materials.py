"""Isotropic linear-elastic material table for first-pass modal FEA.

Pure Python (no heavy imports) so the CLI and tests can use it without ngsolve.
E in pascals, density in kg/m^3, nu dimensionless. These are nominal handbook
values for design iteration, not certified datasheet figures.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    name: str
    E: float       # Young's modulus [Pa]
    nu: float      # Poisson ratio
    rho: float     # density [kg/m^3]

    def lame(self) -> tuple[float, float]:
        """Return (lambda, mu) Lame parameters."""
        lam = self.E * self.nu / ((1 + self.nu) * (1 - 2 * self.nu))
        mu = self.E / (2 * (1 + self.nu))
        return lam, mu


MATERIALS: dict[str, Material] = {
    "steel": Material("steel", 200e9, 0.30, 7850.0),
    "stainless": Material("stainless", 193e9, 0.30, 8000.0),
    "aluminum": Material("aluminum", 69e9, 0.33, 2700.0),
    "titanium": Material("titanium", 114e9, 0.34, 4430.0),
    "brass": Material("brass", 100e9, 0.34, 8500.0),
    "abs": Material("abs", 2.3e9, 0.35, 1050.0),
    "pla": Material("pla", 3.5e9, 0.36, 1240.0),
    "nylon": Material("nylon", 2.0e9, 0.39, 1140.0),
    "delrin": Material("delrin", 3.1e9, 0.35, 1410.0),
    "fr4": Material("fr4", 22e9, 0.18, 1850.0),
    "acrylic": Material("acrylic", 3.2e9, 0.37, 1180.0),
}

# Physical constants for composite (e.g. PCB) density estimates.
RHO_COPPER = 8960.0  # kg/m^3


def get_material(name: str) -> Material:
    key = name.strip().lower()
    if key not in MATERIALS:
        options = ", ".join(sorted(MATERIALS))
        raise KeyError(f"Unknown material '{name}'. Available: {options}")
    return MATERIALS[key]


def pcb_composite_density(
    board_thickness_m: float,
    *,
    num_copper_layers: int = 8,
    copper_layer_thickness_m: float = 35e-6,
    base_density: float = 1850.0,
) -> float:
    """Volume-weighted density of an FR-4 board with embedded copper planes.

    Copper-free flexure arms keep the base FR-4 density; copper-bearing hub/ring
    regions use this composite value. Default is 8 x 35 um (1 oz) layers.
    """
    if board_thickness_m <= 0:
        raise ValueError("board_thickness_m must be positive")
    cu_fraction = (num_copper_layers * copper_layer_thickness_m) / board_thickness_m
    cu_fraction = max(0.0, min(1.0, cu_fraction))
    return cu_fraction * RHO_COPPER + (1.0 - cu_fraction) * base_density

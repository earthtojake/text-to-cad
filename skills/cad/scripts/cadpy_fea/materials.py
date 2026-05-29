"""Isotropic linear-elastic material table for first-pass modal FEA.

Pure Python (no heavy imports) so the CLI and tests can use it without ngsolve.
E in pascals, density in kg/m^3, nu dimensionless. ``zeta`` is a nominal modal
damping ratio (fraction of critical damping ~= loss_factor / 2) used to set the
decay rate of free vibration; metals ring for a long time (zeta ~ 1e-3),
plastics damp out quickly (zeta ~ 2e-2), elastomers barely ring (zeta ~ 0.15).

Values are nominal handbook figures for design iteration across common
3D-printing, machining, sheet-metal, and structural materials -- not certified
datasheet numbers. For anisotropic materials (wood, fiber composites, printed
parts) these are isotropic-equivalent estimates; treat resonance and decay
results as ballpark.

Add or override a material by editing the MATERIALS dict below.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    name: str
    E: float          # Young's modulus [Pa]
    nu: float         # Poisson ratio
    rho: float        # density [kg/m^3]
    category: str = "other"
    zeta: float = 0.01  # modal damping ratio (fraction of critical)

    def lame(self) -> tuple[float, float]:
        """Return (lambda, mu) Lame parameters."""
        lam = self.E * self.nu / ((1 + self.nu) * (1 - 2 * self.nu))
        mu = self.E / (2 * (1 + self.nu))
        return lam, mu


def _m(name, E, nu, rho, category, zeta):
    return Material(name, E, nu, rho, category, zeta)


_MATERIAL_LIST = [
    # --- Metals: machining, sheet metal, casting (ring for a long time) ---
    _m("steel", 200e9, 0.30, 7850.0, "metal", 0.0010),
    _m("stainless", 193e9, 0.30, 8000.0, "metal", 0.0010),
    _m("tool_steel", 210e9, 0.30, 7800.0, "metal", 0.0008),
    _m("cast_iron", 170e9, 0.26, 7200.0, "metal", 0.0040),   # cast iron damps well
    _m("aluminum", 69e9, 0.33, 2700.0, "metal", 0.0005),
    _m("aluminum_7075", 71.7e9, 0.33, 2810.0, "metal", 0.0005),
    _m("titanium", 114e9, 0.34, 4430.0, "metal", 0.0006),
    _m("magnesium", 45e9, 0.35, 1770.0, "metal", 0.0010),
    _m("brass", 100e9, 0.34, 8500.0, "metal", 0.0010),
    _m("bronze", 110e9, 0.34, 8800.0, "metal", 0.0010),
    _m("copper", 117e9, 0.34, 8960.0, "metal", 0.0020),
    _m("zinc", 108e9, 0.25, 7140.0, "metal", 0.0008),
    _m("nickel", 207e9, 0.31, 8900.0, "metal", 0.0008),
    _m("inconel", 200e9, 0.29, 8190.0, "metal", 0.0010),
    _m("lead", 16e9, 0.44, 11340.0, "metal", 0.0150),        # very dissipative
    _m("tungsten", 411e9, 0.28, 19300.0, "metal", 0.0004),

    # --- 3D-printing & engineering thermoplastics (damp out quickly) ---
    _m("pla", 3.5e9, 0.36, 1240.0, "plastic", 0.020),
    _m("abs", 2.3e9, 0.35, 1050.0, "plastic", 0.020),
    _m("asa", 2.0e9, 0.35, 1070.0, "plastic", 0.020),
    _m("petg", 2.1e9, 0.37, 1270.0, "plastic", 0.022),
    _m("nylon", 2.0e9, 0.39, 1140.0, "plastic", 0.025),
    _m("nylon_cf", 7.0e9, 0.35, 1150.0, "composite", 0.015),
    _m("polycarbonate", 2.3e9, 0.37, 1200.0, "plastic", 0.018),
    _m("resin", 2.8e9, 0.35, 1180.0, "plastic", 0.025),
    _m("tpu", 0.026e9, 0.48, 1210.0, "elastomer", 0.10),
    _m("acrylic", 3.2e9, 0.37, 1180.0, "plastic", 0.025),
    _m("delrin", 3.1e9, 0.35, 1410.0, "plastic", 0.020),
    _m("hdpe", 1.0e9, 0.42, 950.0, "plastic", 0.040),
    _m("polypropylene", 1.5e9, 0.42, 905.0, "plastic", 0.045),
    _m("ptfe", 0.5e9, 0.46, 2200.0, "plastic", 0.040),
    _m("pvc", 3.0e9, 0.38, 1400.0, "plastic", 0.030),
    _m("peek", 3.6e9, 0.38, 1320.0, "plastic", 0.020),
    _m("ultem", 3.2e9, 0.36, 1270.0, "plastic", 0.018),

    # --- Composites / boards / wood ---
    _m("fr4", 22e9, 0.18, 1850.0, "composite", 0.015),
    _m("cfrp", 70e9, 0.30, 1600.0, "composite", 0.005),
    _m("gfrp", 25e9, 0.28, 1900.0, "composite", 0.010),
    _m("plywood", 8e9, 0.30, 600.0, "wood", 0.015),
    _m("wood", 10e9, 0.35, 500.0, "wood", 0.012),
    _m("mdf", 3.6e9, 0.25, 750.0, "wood", 0.020),

    # --- Ceramics / glass / mineral ---
    _m("glass", 70e9, 0.22, 2500.0, "ceramic", 0.0015),
    _m("alumina", 370e9, 0.22, 3950.0, "ceramic", 0.0008),
    _m("concrete", 30e9, 0.20, 2400.0, "mineral", 0.015),

    # --- Elastomers (linear estimate only; real behavior is hyperelastic) ---
    _m("rubber", 0.01e9, 0.48, 1100.0, "elastomer", 0.15),
    _m("silicone", 0.01e9, 0.48, 1100.0, "elastomer", 0.15),
]

MATERIALS: dict[str, Material] = {m.name: m for m in _MATERIAL_LIST}

# Common aliases / standard designations -> canonical key.
ALIASES: dict[str, str] = {
    "mild_steel": "steel", "carbon_steel": "steel", "a36": "steel", "1018": "steel",
    "ss": "stainless", "stainless_steel": "stainless", "304": "stainless", "316": "stainless",
    "al": "aluminum", "aluminium": "aluminum", "6061": "aluminum", "7075": "aluminum_7075",
    "ti": "titanium", "ti64": "titanium",
    "pom": "delrin", "acetal": "delrin",
    "pmma": "acrylic", "plexiglass": "acrylic",
    "pc": "polycarbonate", "pei": "ultem",
    "pp": "polypropylene", "teflon": "ptfe",
    "pa": "nylon", "pa6": "nylon", "pa12": "nylon",
    "carbon_fiber": "cfrp", "carbon": "cfrp", "fiberglass": "gfrp",
    "pcb": "fr4", "g10": "fr4",
}

# Physical constants for composite (e.g. PCB) density estimates.
RHO_COPPER = 8960.0  # kg/m^3


def get_material(name: str) -> Material:
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    key = ALIASES.get(key, key)
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

    Copper-free regions keep the base FR-4 density; copper-bearing regions
    (planes and pours) use this composite value. Default is 8 x 35 um (1 oz) layers.
    """
    if board_thickness_m <= 0:
        raise ValueError("board_thickness_m must be positive")
    cu_fraction = (num_copper_layers * copper_layer_thickness_m) / board_thickness_m
    cu_fraction = max(0.0, min(1.0, cu_fraction))
    return cu_fraction * RHO_COPPER + (1.0 - cu_fraction) * base_density

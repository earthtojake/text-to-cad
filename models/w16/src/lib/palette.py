"""Material and color language for the W16, authored as the sRGB hex a shape takes.

Four surface languages, kept distinct (see the brief):
  CAST      raw cast alloy — block, heads, sump, turbo centre housings
  MACHINED  bright machined faces — mating surfaces, cam caps, compressor housings
  CARBON    carbon / dark composite — plenums, cam covers, some brackets
  TITANIUM / STEEL fasteners; STEEL_DARK for studs, chain, cams; HEAT_TINT for turbines

Each colour is also a finish: `FINISHES` holds what a part of that colour is made
of, in the look it wears, and `apply_finishes` sets it on every leaf of the engine
by its colour.
"""

from __future__ import annotations

import build123d as bd

from cadgen import Material, materials


CAST = "#7f8288"           # raw cast alloy, warm mid grey (reads matte next to MACHINED)
CAST_DARK = "#6a6e74"      # cast, shadowed / as-cast texture zones
MACHINED = "#d6d9dd"       # bright machined aluminium
MACHINED_STEEL = "#b9bcc2" # ground steel: journals, valves, pins
ALUMINIUM_TUBE = "#aeb3ba"  # mandrel-bent aluminium pipe: satin, darker than a machined face
CARBON = "#1e2124"         # carbon composite, near black
COMPOSITE = "#2c2f33"      # dark composite / anodised covers
TITANIUM = "#9da3ab"       # titanium fasteners, rods
TITANIUM_DARK = "#6e737a"  # anodised titanium
STEEL = "#aeb2b8"          # zinc-plated / bright steel
STEEL_DARK = "#4b4f55"     # black-oxide steel: studs, chain, cams
STEEL_BLUE = "#5b6a80"     # heat-treated blue steel (springs, retainers)
HEAT_TINT = "#6a4e3f"      # turbine housings: bronze/brown heat tint
HEAT_TINT_BLUE = "#4a5470" # hotter blue tint band
HEAT_TINT_BRONZE = "#8a6a4a"  # mid-way tint band on the turbine inlet duct
INCONEL = "#8b8f96"        # exhaust primaries, turbine wheels
BRASS = "#b8975a"
COPPER = "#a86a45"
RUBBER = "#26282b"
HOSE = "#303338"
RED_ANODISE = "#a8322c"
GOLD_HEAT_WRAP = "#b59a5e"
GASKET = "#3a3d42"
INTERCOOLER_CORE = "#6f7378"
OIL_FILTER = "#2b2e33"
BELT = "#1c1e21"
LENS_CLEAR = "#9fb3c859"


# ---------------------------------------------------------------------------
# Finishes: what a part of each colour is made of, in the look it wears. Each is
# the catalogue's material (its density and physical numbers) in the original
# finish's look (metallic, roughness, clear coat), with `color=None`, so the
# colour above stays the one that shows. Inconel and the heat wrap are the
# project's own: the catalogue has neither.
# ---------------------------------------------------------------------------

INCONEL_625 = Material(
    "Inconel 625", 8440.0, family="metal", standard="UNS N06625",
    source="typical: Special Metals datasheet", description="Nickel superalloy exhaust tube",
    metallic=0.88, roughness=0.36)
HEAT_WRAP = Material(
    "Heat wrap", None, family="other", description="Basalt-fibre heat wrap, gold foil faced",
    roughness=0.95, metallic=0.1)


def _finish(base, description, *, metallic, roughness, coat=0.0, coat_roughness=0.0, **look):
    return base.but(color=None, description=description, metallic=metallic, roughness=roughness,
                    anisotropy=0.0, coat=coat, coat_roughness=coat_roughness, **look)


FINISHES = {
    "aluminium_tube": _finish(materials.aluminium_6063, "Mandrel-bent aluminium tube, satin",
                              metallic=0.85, roughness=0.42),
    "belt": _finish(materials.nbr_70a, "Ribbed accessory belt", metallic=0.0, roughness=0.92),
    "brass": _finish(materials.brass_c360, "Brass", metallic=0.9, roughness=0.34),
    "carbon": _finish(materials.carbon_fibre_laminate, "Carbon composite, clear-coated",
                      metallic=0.05, roughness=0.32, coat=1.0, coat_roughness=0.12),
    "cast": _finish(materials.aluminium_6061, "Cast aluminium, as cast", metallic=0.3, roughness=0.82),
    "cast_dark": _finish(materials.aluminium_6061, "Cast aluminium, as-cast texture",
                         metallic=0.25, roughness=0.88),
    "composite": _finish(materials.nylon_pa6_cf, "Dark composite", metallic=0.15, roughness=0.55),
    "copper": _finish(materials.copper_c110, "Copper", metallic=0.9, roughness=0.34),
    "gasket": _finish(materials.nbr_70a, "Gasket", metallic=0.0, roughness=0.9),
    "gold_heat_wrap": HEAT_WRAP,
    "heat_tint": _finish(materials.stainless_316, "Turbine housing, heat-tinted",
                         metallic=0.8, roughness=0.4, coat=0.6, coat_roughness=0.3),
    "heat_tint_blue": _finish(materials.stainless_316, "Turbine housing, blue heat band",
                              metallic=0.8, roughness=0.36, coat=0.6, coat_roughness=0.25),
    "heat_tint_bronze": _finish(materials.stainless_316, "Turbine inlet, bronze heat band",
                                metallic=0.8, roughness=0.38, coat=0.6, coat_roughness=0.28),
    "hose": _finish(materials.silicone_50a, "Hose", metallic=0.0, roughness=0.85),
    "inconel": INCONEL_625,
    "intercooler_core": _finish(materials.aluminium_6063, "Brazed aluminium intercooler core",
                                metallic=0.6, roughness=0.62),
    "lens_clear": _finish(materials.polycarbonate, "Clear lens", metallic=0.0, roughness=0.1),
    "machined": _finish(materials.aluminium_6061, "Machined aluminium", metallic=0.92, roughness=0.26),
    "machined_steel": _finish(materials.steel_4140, "Ground steel", metallic=0.95, roughness=0.22),
    "oil_filter": _finish(materials.steel_1018, "Painted filter canister", metallic=0.3, roughness=0.5),
    "red_anodise": _finish(materials.aluminium_6061, "Red anodised aluminium", metallic=0.55, roughness=0.4),
    "rubber": _finish(materials.nbr_70a, "Rubber", metallic=0.0, roughness=0.92),
    "steel": _finish(materials.steel_1018, "Zinc-plated steel", metallic=0.9, roughness=0.3),
    "steel_blue": _finish(materials.steel_spring_1095, "Heat-treated spring steel, blued",
                          metallic=0.8, roughness=0.35),
    "steel_dark": _finish(materials.steel_4140, "Black-oxide steel", metallic=0.7, roughness=0.55),
    "titanium": _finish(materials.titanium_grade5, "Titanium", metallic=0.85, roughness=0.38),
    "titanium_dark": _finish(materials.titanium_grade5, "Anodised titanium", metallic=0.7, roughness=0.48),
}

FINISH_COLORS = {
    "aluminium_tube": ALUMINIUM_TUBE,
    "belt": BELT,
    "brass": BRASS,
    "carbon": CARBON,
    "cast": CAST,
    "cast_dark": CAST_DARK,
    "composite": COMPOSITE,
    "copper": COPPER,
    "gasket": GASKET,
    "gold_heat_wrap": GOLD_HEAT_WRAP,
    "heat_tint": HEAT_TINT,
    "heat_tint_blue": HEAT_TINT_BLUE,
    "heat_tint_bronze": HEAT_TINT_BRONZE,
    "hose": HOSE,
    "inconel": INCONEL,
    "intercooler_core": INTERCOOLER_CORE,
    "lens_clear": LENS_CLEAR,
    "machined": MACHINED,
    "machined_steel": MACHINED_STEEL,
    "oil_filter": OIL_FILTER,
    "red_anodise": RED_ANODISE,
    "rubber": RUBBER,
    "steel": STEEL,
    "steel_blue": STEEL_BLUE,
    "steel_dark": STEEL_DARK,
    "titanium": TITANIUM,
    "titanium_dark": TITANIUM_DARK,
}


def _color_key(color):
    # OpenCascade stores assigned colors as single-precision floats, so allow
    # for its last-place round trip while keeping every palette color distinct.
    return tuple(round(float(channel), 5) for channel in bd.Color(color))


_FINISH_BY_COLOR = {_color_key(color): FINISHES[name] for name, color in FINISH_COLORS.items()}


def apply_finishes(assembly):
    """Every leaf below ``assembly`` takes the finish of its colour; a leaf of no
    palette colour is an error, by its label. Returns the assembly."""
    leaves = [assembly] if not assembly.children else [n for n in assembly.descendants if not n.children]
    for part in leaves:
        finish = _FINISH_BY_COLOR.get(_color_key(part.color))
        if finish is None:
            raise ValueError(f"{part.label} has no W16 finish for color {part.color}")
        part.material = finish
    return assembly


def style(shape, label: str, color=None):
    """Label and color a leaf; `apply_finishes` gives it the finish of its colour."""
    shape.label = label
    if color is not None:
        shape.color = color
    return shape

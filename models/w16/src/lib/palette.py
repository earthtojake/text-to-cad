"""FinishedMaterial and color language for the W16, authored as the sRGB hex a shape takes.

Four surface languages, kept distinct (see the brief):
  CAST      raw cast alloy — block, heads, sump, turbo centre housings
  MACHINED  bright machined faces — mating surfaces, cam caps, compressor housings
  CARBON    carbon / dark composite — plenums, cam covers, some brackets
  TITANIUM / STEEL fasteners; STEEL_DARK for studs, chain, cams; HEAT_TINT for turbines

Each colour is also a finish: `FINISHES` holds what a part of that colour is made
of, in the look it wears, and `apply_finishes` sets it on every leaf of the engine
by its colour (or, for the few parts coloured as their neighbours, by its label:
`LABEL_FINISHES`). Bare metals are metalness 1 and paint, composites and carbon 0,
so a render reads each as what it is; a finish that carries its own colour (the
cast alloys, black oxide, ceramic, red anodise) wears it, any other the part's.
"""

from __future__ import annotations

from bd_materials import FinishedMaterial, metals, plastics
from bd_materials.core import RangeMaterial
from cad.build123d.materials import anodized, black_oxide, ceramic
from threejs_materials import PbrProperties


import build123d as bd


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

# The colour a finish WEARS where it differs from the colour that picks it: the cast alloys,
# lifted so that, as metals, they read as raw alloy rather than grey primer. The constants
# above are what the systems colour their parts with and stay as they are: a `@memo` stage's
# key holds every palette symbol it reaches, so changing one would rebuild the stages.
# `FINISHES`, `LABEL_FINISHES` and `apply_finishes` are reached from w16.py's body alone.
CAST_LOOK = "#a7abb1"       # raw cast alloy as a metal (bead-blasted-like), not grey primer
CAST_DARK_LOOK = "#8f9399"  # its shadowed/as-cast zones, a step darker


# ---------------------------------------------------------------------------
# Finishes: what a part of each colour is made of, in the look it wears. Each is
# the catalogue's material (its density and physical numbers) in the original
# finish's look (metalness, roughness, clearcoat), with an explicit native PBR look, or
# one of cad.build123d.materials' named finishes (black oxide, anodised, ceramic). A finish
# with no colour of its own wears the part's colour above. Inconel and the heat wrap are
# the project's own: the catalogue has neither.
# ---------------------------------------------------------------------------

INCONEL_625 = FinishedMaterial(
    RangeMaterial(name='Inconel 625', density=8440.0),
    pbr=PbrProperties.create('Nickel superalloy exhaust tube', color=INCONEL, metalness=1.0, roughness=0.36),
)
HEAT_WRAP = FinishedMaterial(
    RangeMaterial(name='Heat wrap', density=None),
    pbr=PbrProperties.create('Basalt-fibre heat wrap, gold foil faced', metalness=0.1, roughness=0.95),
)


FINISHES = {
    "aluminium_tube": FinishedMaterial(
        RangeMaterial(name='Aluminum 6063-T5', density=2700.0),
        pbr=PbrProperties.create('Mandrel-bent aluminium tube, satin', metalness=1.0, roughness=0.42),
    ),
    "belt": FinishedMaterial(
        RangeMaterial(name='NBR 70A', density=1250.0),
        pbr=PbrProperties.create('Ribbed accessory belt', metalness=0.0, roughness=0.92),
    ),
    "brass": FinishedMaterial(
        metals.brass().material,
        pbr=PbrProperties.create('Brass', metalness=1.0, roughness=0.34),
    ),
    "carbon": FinishedMaterial(
        plastics.cfrp().material,
        pbr=PbrProperties.create('Carbon composite, clear-coated', metalness=0.0, roughness=0.32,
            clearcoat=1.0, clearcoat_roughness=0.12),
    ),
    "cast": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Cast aluminium, as cast', color=CAST_LOOK, metalness=1.0, roughness=0.6),
    ),
    "cast_dark": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Cast aluminium, as-cast texture', color=CAST_DARK_LOOK, metalness=1.0,
            roughness=0.65),
    ),
    "composite": FinishedMaterial(
        RangeMaterial(name='Nylon PA6-CF', density=1170.0),
        pbr=PbrProperties.create('Dark composite', metalness=0.0, roughness=0.55),
    ),
    "copper": FinishedMaterial(
        metals.copper().material,
        pbr=PbrProperties.create('Copper', metalness=1.0, roughness=0.34),
    ),
    "gasket": FinishedMaterial(
        RangeMaterial(name='NBR 70A', density=1250.0),
        pbr=PbrProperties.create('Gasket', metalness=0.0, roughness=0.9),
    ),
    "gold_heat_wrap": HEAT_WRAP,
    "heat_tint": FinishedMaterial(
        metals.stainless(metals.Stainless.G316L_ANNEALED).material,
        pbr=PbrProperties.create('Turbine housing, heat-tinted', metalness=1.0, roughness=0.45),
    ),
    "heat_tint_blue": FinishedMaterial(
        metals.stainless(metals.Stainless.G316L_ANNEALED).material,
        pbr=PbrProperties.create('Turbine housing, blue heat band', metalness=1.0, roughness=0.42),
    ),
    "heat_tint_bronze": FinishedMaterial(
        metals.stainless(metals.Stainless.G316L_ANNEALED).material,
        pbr=PbrProperties.create('Turbine inlet, bronze heat band', metalness=1.0, roughness=0.44),
    ),
    "hose": FinishedMaterial(
        RangeMaterial(name='Silicone 50A', density=1150.0),
        pbr=PbrProperties.create('Hose', metalness=0.0, roughness=0.85),
    ),
    "inconel": INCONEL_625,
    "intercooler_core": FinishedMaterial(
        RangeMaterial(name='Aluminum 6063-T5', density=2700.0),
        pbr=PbrProperties.create('Brazed aluminium intercooler core', metalness=1.0, roughness=0.62),
    ),
    "lens_clear": FinishedMaterial(
        plastics.pc().material,
        pbr=PbrProperties.create('Clear lens', metalness=0.0, roughness=0.1, ior=1.586, transmission=0.9),
    ),
    "machined": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Machined aluminium', metalness=1.0, roughness=0.26),
    ),
    "machined_steel": FinishedMaterial(
        metals.alloy_steel().material,
        pbr=PbrProperties.create('Ground steel', metalness=1.0, roughness=0.22),
    ),
    "oil_filter": FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Painted filter canister', metalness=0.0, roughness=0.45),
    ),
    "red_anodise": anodized(RED_ANODISE),
    "rubber": FinishedMaterial(
        RangeMaterial(name='NBR 70A', density=1250.0),
        pbr=PbrProperties.create('Rubber', metalness=0.0, roughness=0.92),
    ),
    "steel": FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Zinc-plated steel', metalness=1.0, roughness=0.3),
    ),
    "steel_blue": FinishedMaterial(
        RangeMaterial(name='Spring steel 1095', density=7850.0),
        pbr=PbrProperties.create('Heat-treated spring steel, blued', metalness=1.0, roughness=0.35),
    ),
    "steel_dark": black_oxide(substrate=metals.alloy_steel()),
    # worn by label, not colour (LABEL_FINISHES): spark-plug insulators
    "ceramic_white": ceramic("white"),
    "titanium": FinishedMaterial(
        metals.titanium().material,
        pbr=PbrProperties.create('Titanium', metalness=1.0, roughness=0.38),
    ),
    "titanium_dark": FinishedMaterial(
        metals.titanium().material,
        pbr=PbrProperties.create('Anodised titanium', metalness=1.0, roughness=0.48),
    ),
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


# Parts whose colour picks the wrong finish, by their label's name (before ``:``). The systems
# colour these as their neighbours (the collectors CAST_DARK, the insulators MACHINED); the label
# says what they are, and changing their colour in the system would rebuild its stage.
LABEL_FINISHES = {
    "exhaust_collector": "inconel",
    "spark_plug_insulator": "ceramic_white",
}


def _color_key(color):
    # OpenCascade stores assigned colors as single-precision floats, so allow
    # for its last-place round trip while keeping every palette color distinct.
    return tuple(round(float(channel), 5) for channel in bd.Color(color))


def _finish_by_color():
    return {_color_key(color): FINISHES[name] for name, color in FINISH_COLORS.items()}


def apply_finishes(assembly):
    """Every leaf below ``assembly`` takes the finish of its colour; a leaf of no
    palette colour is an error, by its label. Returns the assembly."""
    leaves = [assembly] if not assembly.children else [n for n in assembly.descendants if not n.children]
    by_color = _finish_by_color()
    for part in leaves:
        by_label = LABEL_FINISHES.get((part.label or "").split(":")[0])
        finish = FINISHES[by_label] if by_label else by_color.get(_color_key(part.color))
        if finish is None:
            raise ValueError(f"{part.label} has no W16 finish for color {part.color}")
        color = part.color
        part.material = finish  # build123d sets the part's colour to the finish's PBR colour
        if finish.pbr.values.color is None:
            part.color = color  # a finish with no colour of its own wears the part's
    return assembly


def style(shape, label: str, color=None):
    """Label and color a leaf; `apply_finishes` gives it the finish of its colour."""
    shape.label = label
    if color is not None:
        shape.color = color
    return shape

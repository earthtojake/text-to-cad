"""FinishedMaterial language for the radial, authored as the sRGB hex a shape takes.

The brief's finishes, kept distinct:
  ENAMEL_BLACK     gloss black enamel — cylinder barrels, mount ring
  CAST_ALU         bare cast aluminium — heads, rocker boxes (fins crisp, bright)
  MACHINED_ALU     machined aluminium — pistons, rocker-cover tops, spot faces
  CASE_SILVER      satin silver-grey enamel — crankcase, nose case, blower/accessory cases
  STEEL_POLISHED   polished steel — pushrod tubes, packing nuts, fittings
  STEEL_MACHINED   ground steel — crank, rods, pins, gears, valves, pushrods
  HEAT_TINT(_BLUE) heat-tinted stainless — exhaust collector and stacks
  BRAID / COPPER   ignition leads; POLISHED_ALU harness ring, propeller, spinner
Every leaf gets exactly one of these colours, and its system gives it the finish
that colour names: a native `FinishedMaterial` set on the part (`FINISHES`).
"""

from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties


import build123d as bd


ENAMEL_BLACK = "#0f1012"
ENAMEL_GREY = "#383c42"        # dark-grey enamel (barrels): keeps every fin legible
CAST_ALU = "#dcdfe1"
MACHINED_ALU = "#dcdfe2"
CASE_SILVER = "#9fa5ac"
STEEL_POLISHED = "#e2e4e7"
STEEL_MACHINED = "#b8bbc1"
STEEL_DARK = "#4a4d52"
BLUED_STEEL = "#3e495b"
FASTENER = "#cfcab8"          # cadmium-plated AN hardware
SAFETY_WIRE = "#d3d6d9"
SECTION_RED = "#d4382a"        # museum paint on every cut face
HEAT_TINT = "#c8c2b6"           # heat-tinted stainless: warm steel grey (bands carry the straw/blue)
HEAT_TINT_BLUE = "#7c7aa8"
HEAT_TINT_STRAW = "#cdb27c"
COPPER = "#d08a62"
BRAID = "#a8a69e"
POLISHED_ALU = "#eceef0"
BRONZE = "#c49658"
BRASS = "#c09a55"
MAGNETO_BLACK = "#19191a"
CARB_ALU = "#b4b8bc"
RUBBER = "#202224"
GASKET = "#3b3a36"
CERAMIC = "#e6e2d8"

# Aliases the shared fastener vocabulary (lib/fasteners.py) speaks.
TITANIUM = FASTENER
MACHINED = MACHINED_ALU

# Each finish is a native `FinishedMaterial` set on the part: the catalogue's entry for the
# metal (or a material of the project's own where the catalogue has none), in the
# finish's look -- the original's metalness, roughness and clearcoat as `metalness`,
# `roughness`, `clearcoat` and `clearcoat_roughness`, its name the description, no grain
# (`anisotropy=0`). Assignments restore the authored colour after setting the native material,
# so a part stays the colour its builder authored. The original tuned these against its photographic Render rig: a
# dark room lit by two cards, where near-mirror metals (roughness < ~0.3) read black,
# so "polished" is a satin base under a sharp clearcoat.


FINISHES = {
    "enamel_black": FinishedMaterial(
        metals.alloy_steel().material,
        pbr=PbrProperties.create('Black enamel', metalness=0.0, roughness=0.45, clearcoat=0.7,
            clearcoat_roughness=0.2),
    ),
    "section_red": FinishedMaterial(
        RangeMaterial(name='Section red', density=None),
        pbr=PbrProperties.create('museum paint on every cut face', metalness=0.0, roughness=0.5,
            clearcoat=0.5, clearcoat_roughness=0.3),
    ),
    "enamel_grey": FinishedMaterial(
        metals.alloy_steel().material,
        pbr=PbrProperties.create('Dark-grey enamel', metalness=0.0, roughness=0.45, clearcoat=0.7,
            clearcoat_roughness=0.2),
    ),
    "cast_alu": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Cast aluminium', metalness=0.62, roughness=0.5),
    ),
    "machined_alu": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Machined aluminium', metalness=0.9, roughness=0.42, clearcoat=0.6,
            clearcoat_roughness=0.1),
    ),
    "case_silver": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Satin silver-grey enamel', metalness=0.55, roughness=0.4, clearcoat=0.5,
            clearcoat_roughness=0.22),
    ),
    "steel_polished": FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Polished steel', metalness=1.0, roughness=0.42, clearcoat=1.0,
            clearcoat_roughness=0.04),
    ),
    "steel_machined": FinishedMaterial(
        metals.alloy_steel().material,
        pbr=PbrProperties.create('Ground steel', metalness=1.0, roughness=0.36),
    ),
    "steel_dark": FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Dark steel', metalness=0.8, roughness=0.5),
    ),
    "blued_steel": FinishedMaterial(
        RangeMaterial(name='Spring steel 1095', density=7850.0),
        pbr=PbrProperties.create('Blued spring steel', metalness=0.9, roughness=0.42, clearcoat=0.5,
            clearcoat_roughness=0.12),
    ),
    "fastener": FinishedMaterial(
        metals.alloy_steel().material,
        pbr=PbrProperties.create('Cadmium-plated steel', metalness=0.9, roughness=0.4),
    ),
    "safety_wire": FinishedMaterial(
        metals.stainless().material,
        pbr=PbrProperties.create('Stainless safety wire', metalness=1.0, roughness=0.35),
    ),
    "heat_tint": FinishedMaterial(
        metals.stainless().material,
        pbr=PbrProperties.create('Heat-tinted stainless', metalness=1.0, roughness=0.4, clearcoat=0.5,
            clearcoat_roughness=0.15),
    ),
    "heat_tint_blue": FinishedMaterial(
        metals.stainless().material,
        pbr=PbrProperties.create('Heat-tinted stainless (blue)', metalness=1.0, roughness=0.4, clearcoat=0.5,
            clearcoat_roughness=0.15),
    ),
    "heat_tint_straw": FinishedMaterial(
        metals.stainless().material,
        pbr=PbrProperties.create('Heat-tinted stainless (straw)', metalness=1.0, roughness=0.4, clearcoat=0.5,
            clearcoat_roughness=0.15),
    ),
    "copper": FinishedMaterial(
        metals.copper().material,
        pbr=PbrProperties.create('Copper', metalness=1.0, roughness=0.35),
    ),
    "braid": FinishedMaterial(
        metals.copper().material,
        pbr=PbrProperties.create('Tinned braid', metalness=0.9, roughness=0.55),
    ),
    "polished_alu": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Polished aluminium', metalness=1.0, roughness=0.3, clearcoat=1.0,
            clearcoat_roughness=0.04),
    ),
    "bronze": FinishedMaterial(
        RangeMaterial(name='Bronze', density=8800.0),
        pbr=PbrProperties.create('Bronze', metalness=1.0, roughness=0.4),
    ),
    "brass": FinishedMaterial(
        metals.brass().material,
        pbr=PbrProperties.create('Brass', metalness=1.0, roughness=0.38, clearcoat=0.3,
            clearcoat_roughness=0.15),
    ),
    "magneto_black": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Black crinkle', metalness=0.0, roughness=0.85),
    ),
    "carb_alu": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Cast aluminium (carburettor)', metalness=0.5, roughness=0.62),
    ),
    "rubber": FinishedMaterial(
        RangeMaterial(name='NBR 70A', density=1250.0),
        pbr=PbrProperties.create('Rubber', metalness=0.0, roughness=0.9),
    ),
    "gasket": FinishedMaterial(
        RangeMaterial(name='Gasket', density=None),
        pbr=PbrProperties.create('compressed fibre gasket', metalness=0.0, roughness=0.85),
    ),
    "ceramic": FinishedMaterial(
        RangeMaterial(name='Alumina ceramic', density=3900.0),
        pbr=PbrProperties.create('Ceramic (spark-plug insulator)', metalness=0.0, roughness=0.3),
    ),
}


MATERIAL_COLORS = {
    "enamel_black": ENAMEL_BLACK,
    "section_red": SECTION_RED,
    "enamel_grey": ENAMEL_GREY,
    "cast_alu": CAST_ALU,
    "machined_alu": MACHINED_ALU,
    "case_silver": CASE_SILVER,
    "steel_polished": STEEL_POLISHED,
    "steel_machined": STEEL_MACHINED,
    "steel_dark": STEEL_DARK,
    "blued_steel": BLUED_STEEL,
    "fastener": FASTENER,
    "safety_wire": SAFETY_WIRE,
    "heat_tint": HEAT_TINT,
    "heat_tint_blue": HEAT_TINT_BLUE,
    "heat_tint_straw": HEAT_TINT_STRAW,
    "copper": COPPER,
    "braid": BRAID,
    "polished_alu": POLISHED_ALU,
    "bronze": BRONZE,
    "brass": BRASS,
    "magneto_black": MAGNETO_BLACK,
    "carb_alu": CARB_ALU,
    "rubber": RUBBER,
    "gasket": GASKET,
    "ceramic": CERAMIC,
}


def _color_key(color):
    # OpenCascade stores colours as single-precision floats; round so the
    # last-place round trip still maps every palette colour to one material.
    return tuple(round(float(channel), 5) for channel in bd.Color(color))


def _material_by_color():
    return {_color_key(color): material for material, color in MATERIAL_COLORS.items()}


def material_of(part, by_color=None) -> str:
    material = (by_color or _material_by_color()).get(_color_key(part.color))
    if material is None:
        raise ValueError(f"{part.label!r} has no named radial material for colour {part.color}")
    return material


def material_compound(parts, label, finishes):
    """A system: its leaves, each given the finish its colour names, under one compound.

    `finishes` is the system's declared finish tuple; a leaf in an undeclared finish,
    or a declared finish no leaf uses, fails the build instead of a finish going
    missing. The original grouped the leaves by finish (`<label>__<material>`
    compounds) for its decorator's `materials=` to target; a material is set on the
    part itself here, so the leaves sit directly under the system."""
    grouped: dict[str, list] = {}
    by_color = _material_by_color()
    for part in parts:
        grouped.setdefault(material_of(part, by_color), []).append(part)
    labels = [p.label for p in parts]
    if any(not l for l in labels):
        raise ValueError(f"{label}: unlabelled leaf")
    dupes = sorted({l for l in labels if labels.count(l) > 1})
    if dupes:
        raise ValueError(f"{label}: duplicate leaf labels {dupes[:10]}")
    expected, actual = set(finishes), set(grouped)
    if actual != expected:
        raise ValueError(
            f"{label} finishes changed: missing {sorted(expected - actual)}, "
            f"unexpected {sorted(actual - expected)} - update the system's MATERIALS tuple")
    for finish, members in grouped.items():
        for part in members:
            authored_color = part.color
            part.material = FINISHES[finish]
            part.color = authored_color
    return bd.Compound(label=label, children=list(parts))


def style(shape, label: str, color=None):
    """Label and colour a leaf; the owning system model assigns its finish."""
    shape.label = label
    if color is not None:
        shape.color = color
    return shape

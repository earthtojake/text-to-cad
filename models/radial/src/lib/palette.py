"""Material language for the radial, authored as sRGB hex via cadgen.srgb().

The brief's finishes, kept distinct:
  ENAMEL_BLACK     gloss black enamel — cylinder barrels, mount ring
  CAST_ALU         bare cast aluminium — heads, rocker boxes (fins crisp, bright)
  MACHINED_ALU     machined aluminium — pistons, rocker-cover tops, spot faces
  CASE_SILVER      satin silver-grey enamel — crankcase, nose case, blower/accessory cases
  STEEL_POLISHED   polished steel — pushrod tubes, packing nuts, fittings
  STEEL_MACHINED   ground steel — crank, rods, pins, gears, valves, pushrods
  HEAT_TINT(_BLUE) heat-tinted stainless — exhaust collector and stacks
  BRAID / COPPER   ignition leads; POLISHED_ALU harness ring, propeller, spinner
Every leaf gets exactly one of these colours; the system model groups leaves by
colour into `material_<name>` compounds and assigns the named PBR finish.
"""

from __future__ import annotations

from cadgen import build123d as bd, srgb

ENAMEL_BLACK = srgb("#0f1012")
ENAMEL_GREY = srgb("#383c42")        # dark-grey enamel (barrels): keeps every fin legible
CAST_ALU = srgb("#dcdfe1")
MACHINED_ALU = srgb("#dcdfe2")
CASE_SILVER = srgb("#9fa5ac")
STEEL_POLISHED = srgb("#e2e4e7")
STEEL_MACHINED = srgb("#b8bbc1")
STEEL_DARK = srgb("#4a4d52")
BLUED_STEEL = srgb("#3e495b")
FASTENER = srgb("#cfcab8")          # cadmium-plated AN hardware
SAFETY_WIRE = srgb("#d3d6d9")
SECTION_RED = srgb("#d4382a")        # museum paint on every cut face
HEAT_TINT = srgb("#c8c2b6")           # heat-tinted stainless: warm steel grey (bands carry the straw/blue)
HEAT_TINT_BLUE = srgb("#7c7aa8")
HEAT_TINT_STRAW = srgb("#cdb27c")
COPPER = srgb("#d08a62")
BRAID = srgb("#a8a69e")
POLISHED_ALU = srgb("#eceef0")
BRONZE = srgb("#c49658")
BRASS = srgb("#c09a55")
MAGNETO_BLACK = srgb("#19191a")
CARB_ALU = srgb("#b4b8bc")
RUBBER = srgb("#202224")
GASKET = srgb("#3b3a36")
CERAMIC = srgb("#e6e2d8")

# Aliases the shared fastener vocabulary (lib/fasteners.py) speaks.
TITANIUM = FASTENER
MACHINED = MACHINED_ALU

# Tuned against the photographic Render rig (render/presentation.json): a dark
# procedural room (radiance 0.04) lit only by a key softbox card and a rear fill
# card. A metal shows ONLY what it reflects, so near-mirror metals (roughness
# < ~0.3) reflect the dark room and render black. "Polished" finishes are
# therefore a satin metal base (roughness ~0.3-0.42, which spreads the cards into
# a bright body) under a sharp clearcoat (the crisp mirror highlight). Cast
# aluminium keeps some diffuse (metalness 0.55) so it answers the key light
# directly and fin edges read bright from any view.
MATERIAL_DEFINITIONS = {
    "enamel_black": {"name": "Black enamel", "metalness": 0.0, "roughness": 0.45,
                     "clearcoat": 0.7, "clearcoatRoughness": 0.2},
    "section_red": {"name": "Section red", "metalness": 0.0, "roughness": 0.5, "clearcoat": 0.5, "clearcoatRoughness": 0.3},
    "enamel_grey": {"name": "Dark-grey enamel", "metalness": 0.0, "roughness": 0.45,
                     "clearcoat": 0.7, "clearcoatRoughness": 0.2},
    "cast_alu": {"name": "Cast aluminium", "metalness": 0.62, "roughness": 0.5},
    "machined_alu": {"name": "Machined aluminium", "metalness": 0.9, "roughness": 0.42,
                     "clearcoat": 0.6, "clearcoatRoughness": 0.1},
    "case_silver": {"name": "Satin silver-grey enamel", "metalness": 0.55, "roughness": 0.4,
                    "clearcoat": 0.5, "clearcoatRoughness": 0.22},
    "steel_polished": {"name": "Polished steel", "metalness": 1.0, "roughness": 0.42,
                       "clearcoat": 1.0, "clearcoatRoughness": 0.04},
    "steel_machined": {"name": "Ground steel", "metalness": 1.0, "roughness": 0.36},
    "steel_dark": {"name": "Dark steel", "metalness": 0.8, "roughness": 0.5},
    "blued_steel": {"name": "Blued spring steel", "metalness": 0.9, "roughness": 0.42,
                    "clearcoat": 0.5, "clearcoatRoughness": 0.12},
    "fastener": {"name": "Cadmium-plated steel", "metalness": 0.9, "roughness": 0.4},
    "safety_wire": {"name": "Stainless safety wire", "metalness": 1.0, "roughness": 0.35},
    "heat_tint": {"name": "Heat-tinted stainless", "metalness": 1.0, "roughness": 0.4,
                  "clearcoat": 0.5, "clearcoatRoughness": 0.15},
    "heat_tint_blue": {"name": "Heat-tinted stainless (blue)", "metalness": 1.0, "roughness": 0.4,
                       "clearcoat": 0.5, "clearcoatRoughness": 0.15},
    "heat_tint_straw": {"name": "Heat-tinted stainless (straw)", "metalness": 1.0, "roughness": 0.4,
                        "clearcoat": 0.5, "clearcoatRoughness": 0.15},
    "copper": {"name": "Copper", "metalness": 1.0, "roughness": 0.35},
    "braid": {"name": "Tinned braid", "metalness": 0.9, "roughness": 0.55},
    "polished_alu": {"name": "Polished aluminium", "metalness": 1.0, "roughness": 0.3,
                     "clearcoat": 1.0, "clearcoatRoughness": 0.04},
    "bronze": {"name": "Bronze", "metalness": 1.0, "roughness": 0.4},
    "brass": {"name": "Brass", "metalness": 1.0, "roughness": 0.38,
              "clearcoat": 0.3, "clearcoatRoughness": 0.15},
    "magneto_black": {"name": "Black crinkle", "metalness": 0.0, "roughness": 0.85},
    "carb_alu": {"name": "Cast aluminium (carburettor)", "metalness": 0.5, "roughness": 0.62},
    "rubber": {"name": "Rubber", "metalness": 0.0, "roughness": 0.9},
    "gasket": {"name": "Gasket", "metalness": 0.0, "roughness": 0.85},
    "ceramic": {"name": "Ceramic", "metalness": 0.0, "roughness": 0.3},
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
    return tuple(round(float(channel), 5) for channel in color)


_MATERIAL_BY_COLOR = {_color_key(color): material for material, color in MATERIAL_COLORS.items()}


def material_of(part) -> str:
    material = _MATERIAL_BY_COLOR.get(_color_key(part.color))
    if material is None:
        raise ValueError(f"{part.label!r} has no named radial material for colour {part.color}")
    return material


def material_compound(parts, label, materials):
    """Group a system's leaves by finish: system -> <label>__<material> -> leaves.

    `materials` is the system's declared finish tuple (the same one its
    decorator passed to `materials_for`); a leaf in an undeclared finish, or a
    declared finish no leaf uses, fails the build instead of leaving an
    assignment that resolves to nothing. The animation addresses leaves by
    LABEL, so this grouping never reaches it."""
    grouped: dict[str, list] = {}
    for part in parts:
        grouped.setdefault(material_of(part), []).append(part)
    labels = [p.label for p in parts]
    if any(not l for l in labels):
        raise ValueError(f"{label}: unlabelled leaf")
    dupes = sorted({l for l in labels if labels.count(l) > 1})
    if dupes:
        raise ValueError(f"{label}: duplicate leaf labels {dupes[:10]}")
    expected, actual = set(materials), set(grouped)
    if actual != expected:
        raise ValueError(
            f"{label} finishes changed: missing {sorted(expected - actual)}, "
            f"unexpected {sorted(actual - expected)} - update the system's MATERIALS tuple")
    return bd.Compound(label=label, children=[
        bd.Compound(label=f"{label}__{m}", children=grouped[m]) for m in sorted(materials)
    ])


def materials_for(label, materials):
    """The `materials=` declaration for a system whose leaves use `materials`."""
    return {
        "definitions": {m: MATERIAL_DEFINITIONS[m] for m in sorted(materials)},
        "assignments": [{"targets": [f"#{label}__{m}"], "material": m} for m in sorted(materials)],
    }


def style(shape, label: str, color=None):
    """Label and colour a leaf; the owning system model assigns its finish."""
    shape.label = label
    if color is not None:
        shape.color = color
    return shape

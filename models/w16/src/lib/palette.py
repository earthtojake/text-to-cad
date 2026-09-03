"""Material language for the W16, authored as sRGB hex via cadgen.srgb().

Four surface languages, kept distinct (see the brief):
  CAST      raw cast alloy — block, heads, sump, turbo centre housings
  MACHINED  bright machined faces — mating surfaces, cam caps, compressor housings
  CARBON    carbon / dark composite — plenums, cam covers, some brackets
  TITANIUM / STEEL fasteners; STEEL_DARK for studs, chain, cams; HEAT_TINT for turbines
"""

from __future__ import annotations

from cadgen import srgb

CAST = srgb("#7f8288")           # raw cast alloy, warm mid grey (reads matte next to MACHINED)
CAST_DARK = srgb("#6a6e74")      # cast, shadowed / as-cast texture zones
MACHINED = srgb("#d6d9dd")       # bright machined aluminium
MACHINED_STEEL = srgb("#b9bcc2") # ground steel: journals, valves, pins
ALUMINIUM_TUBE = srgb("#aeb3ba")  # mandrel-bent aluminium pipe: satin, darker than a machined face
CARBON = srgb("#1e2124")         # carbon composite, near black
COMPOSITE = srgb("#2c2f33")      # dark composite / anodised covers
TITANIUM = srgb("#9da3ab")       # titanium fasteners, rods
TITANIUM_DARK = srgb("#6e737a")  # anodised titanium
STEEL = srgb("#aeb2b8")          # zinc-plated / bright steel
STEEL_DARK = srgb("#4b4f55")     # black-oxide steel: studs, chain, cams
STEEL_BLUE = srgb("#5b6a80")     # heat-treated blue steel (springs, retainers)
HEAT_TINT = srgb("#6a4e3f")      # turbine housings: bronze/brown heat tint
HEAT_TINT_BLUE = srgb("#4a5470") # hotter blue tint band
INCONEL = srgb("#8b8f96")        # exhaust primaries, turbine wheels
BRASS = srgb("#b8975a")
COPPER = srgb("#a86a45")
RUBBER = srgb("#26282b")
HOSE = srgb("#303338")
RED_ANODISE = srgb("#a8322c")
GOLD_HEAT_WRAP = srgb("#b59a5e")
GASKET = srgb("#3a3d42")
INTERCOOLER_CORE = srgb("#6f7378")
OIL_FILTER = srgb("#2b2e33")
BELT = srgb("#1c1e21")
LENS_CLEAR = srgb("#9fb3c8", 0.35)


# Per-part finish (cadgen >= 43ffa724: `shape.cad_material` rides the package
# occurrence and overrides the theme's single material for that leaf).  Keyed
# by palette colour so every call site keeps passing one token.
_R = "roughness"; _M = "metalness"
MATERIALS = {
    CAST: {_R: 0.82, _M: 0.30},              # as-cast: sand texture, no sheen
    CAST_DARK: {_R: 0.88, _M: 0.25},
    MACHINED: {_R: 0.26, _M: 0.92},          # face-milled aluminium
    MACHINED_STEEL: {_R: 0.22, _M: 0.95},    # ground journals / valves / pins
    ALUMINIUM_TUBE: {_R: 0.42, _M: 0.85},
    CARBON: {_R: 0.32, _M: 0.05, "clearcoat": 1.0, "clearcoatRoughness": 0.12},
    COMPOSITE: {_R: 0.55, _M: 0.15},
    TITANIUM: {_R: 0.38, _M: 0.85},
    TITANIUM_DARK: {_R: 0.48, _M: 0.70},
    STEEL: {_R: 0.30, _M: 0.90},
    STEEL_DARK: {_R: 0.55, _M: 0.70},        # black oxide
    STEEL_BLUE: {_R: 0.35, _M: 0.80},
    HEAT_TINT: {_R: 0.40, _M: 0.80, "clearcoat": 0.6, "clearcoatRoughness": 0.3},
    HEAT_TINT_BLUE: {_R: 0.36, _M: 0.80, "clearcoat": 0.6, "clearcoatRoughness": 0.25},
    INCONEL: {_R: 0.36, _M: 0.88},
    BRASS: {_R: 0.34, _M: 0.90},
    COPPER: {_R: 0.34, _M: 0.90},
    RUBBER: {_R: 0.92, _M: 0.0},
    HOSE: {_R: 0.85, _M: 0.0},
    RED_ANODISE: {_R: 0.40, _M: 0.55},
    GOLD_HEAT_WRAP: {_R: 0.95, _M: 0.10},
    GASKET: {_R: 0.90, _M: 0.0},
    INTERCOOLER_CORE: {_R: 0.62, _M: 0.60},
    OIL_FILTER: {_R: 0.50, _M: 0.30},
    BELT: {_R: 0.92, _M: 0.0},
    LENS_CLEAR: {_R: 0.10, _M: 0.0, "opacity": 0.35},
}


def style(shape, label: str, color=None):
    """Label (and colour + finish) a leaf shape in place and return it."""
    shape.label = label
    if color is not None:
        shape.color = color
        mat = MATERIALS.get(color)
        if mat is not None:
            shape.cad_material = dict(mat)
    return shape

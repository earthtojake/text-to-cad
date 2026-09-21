"""Material and color language for the W16, authored as sRGB hex via cadgen.srgb().

Four surface languages, kept distinct (see the brief):
  CAST      raw cast alloy — block, heads, sump, turbo centre housings
  MACHINED  bright machined faces — mating surfaces, cam caps, compressor housings
  CARBON    carbon / dark composite — plenums, cam covers, some brackets
  TITANIUM / STEEL fasteners; STEEL_DARK for studs, chain, cams; HEAT_TINT for turbines
"""

from __future__ import annotations

from cadgen import build123d as bd, srgb

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


# Named PBR definitions retain the STEP-authored base colors. Each system
# groups its leaves by the same palette color its factories already assign, so
# material declarations stay compact and follow generated labels automatically.
MATERIAL_DEFINITIONS = {'aluminium_tube': {'metalness': 0.85, 'name': 'Aluminium Tube', 'roughness': 0.42},
 'belt': {'metalness': 0.0, 'name': 'Belt', 'roughness': 0.92},
 'brass': {'metalness': 0.9, 'name': 'Brass', 'roughness': 0.34},
 'carbon': {'clearcoat': 1.0,
            'clearcoatRoughness': 0.12,
            'metalness': 0.05,
            'name': 'Carbon',
            'roughness': 0.32},
 'cast': {'metalness': 0.3, 'name': 'Cast', 'roughness': 0.82},
 'cast_dark': {'metalness': 0.25, 'name': 'Cast Dark', 'roughness': 0.88},
 'composite': {'metalness': 0.15, 'name': 'Composite', 'roughness': 0.55},
 'copper': {'metalness': 0.9, 'name': 'Copper', 'roughness': 0.34},
 'gasket': {'metalness': 0.0, 'name': 'Gasket', 'roughness': 0.9},
 'gold_heat_wrap': {'metalness': 0.1, 'name': 'Gold Heat Wrap', 'roughness': 0.95},
 'heat_tint': {'clearcoat': 0.6,
               'clearcoatRoughness': 0.3,
               'metalness': 0.8,
               'name': 'Heat Tint',
               'roughness': 0.4},
 'heat_tint_blue': {'clearcoat': 0.6,
                    'clearcoatRoughness': 0.25,
                    'metalness': 0.8,
                    'name': 'Heat Tint Blue',
                    'roughness': 0.36},
 'hose': {'metalness': 0.0, 'name': 'Hose', 'roughness': 0.85},
 'inconel': {'metalness': 0.88, 'name': 'Inconel', 'roughness': 0.36},
 'intercooler_core': {'metalness': 0.6, 'name': 'Intercooler Core', 'roughness': 0.62},
 'lens_clear': {'metalness': 0.0, 'name': 'Lens Clear', 'roughness': 0.1},
 'machined': {'metalness': 0.92, 'name': 'Machined', 'roughness': 0.26},
 'machined_steel': {'metalness': 0.95, 'name': 'Machined Steel', 'roughness': 0.22},
 'oil_filter': {'metalness': 0.3, 'name': 'Oil Filter', 'roughness': 0.5},
 'red_anodise': {'metalness': 0.55, 'name': 'Red Anodise', 'roughness': 0.4},
 'rubber': {'metalness': 0.0, 'name': 'Rubber', 'roughness': 0.92},
 'steel': {'metalness': 0.9, 'name': 'Steel', 'roughness': 0.3},
 'steel_blue': {'metalness': 0.8, 'name': 'Steel Blue', 'roughness': 0.35},
 'steel_dark': {'metalness': 0.7, 'name': 'Steel Dark', 'roughness': 0.55},
 'titanium': {'metalness': 0.85, 'name': 'Titanium', 'roughness': 0.38},
 'titanium_dark': {'metalness': 0.7, 'name': 'Titanium Dark', 'roughness': 0.48}}

MATERIAL_COLORS = {
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

SYSTEM_MATERIALS = {'block': ('cast', 'machined', 'titanium'),
 'crank': ('machined', 'machined_steel', 'steel_dark'),
 'pistons': ('brass', 'machined', 'machined_steel', 'steel_blue', 'steel_dark', 'titanium'),
 'heads': ('cast', 'machined', 'machined_steel', 'steel', 'titanium_dark'),
 'valvetrain': ('brass', 'machined_steel', 'steel', 'steel_blue', 'steel_dark', 'titanium_dark'),
 'cams': ('machined', 'steel_dark'),
 'camdrive': ('composite', 'machined', 'machined_steel', 'steel_dark'),
 'covers': ('carbon', 'composite', 'hose', 'machined', 'rubber', 'steel', 'titanium'),
 'oil_system': ('belt',
                'cast',
                'copper',
                'gasket',
                'hose',
                'machined',
                'machined_steel',
                'oil_filter',
                'steel_dark',
                'titanium'),
 'turbos': ('cast',
            'cast_dark',
            'heat_tint',
            'heat_tint_blue',
            'inconel',
            'machined',
            'machined_steel',
            'steel_dark',
            'titanium'),
 'exhaust': ('cast_dark',
             'gasket',
             'inconel',
             'machined',
             'machined_steel',
             'steel_dark',
             'titanium'),
 'induction': ('aluminium_tube',
               'carbon',
               'cast',
               'composite',
               'gasket',
               'hose',
               'intercooler_core',
               'machined',
               'machined_steel',
               'red_anodise',
               'titanium'),
 'ancillaries': ('belt',
                 'brass',
                 'cast',
                 'composite',
                 'hose',
                 'machined',
                 'machined_steel',
                 'red_anodise',
                 'steel',
                 'steel_dark',
                 'titanium')}


def _color_key(color):
    # OpenCascade stores assigned colors as single-precision floats, so allow
    # for its last-place round trip while keeping every palette color distinct.
    return tuple(round(float(channel), 5) for channel in color)


_MATERIAL_BY_COLOR = {_color_key(color): material for material, color in MATERIAL_COLORS.items()}


def material_compound(parts, label):
    grouped = {}
    for part in parts:
        material = _MATERIAL_BY_COLOR.get(_color_key(part.color))
        if material is None:
            raise ValueError(f"{part.label} has no named W16 material for color {part.color}")
        grouped.setdefault(material, []).append(part)
    expected = set(SYSTEM_MATERIALS[label])
    actual = set(grouped)
    if actual != expected:
        raise ValueError(
            f"{label} material groups changed: missing {sorted(expected - actual)}, "
            f"unexpected {sorted(actual - expected)}"
        )
    return bd.Compound(label=label, children=[
        bd.Compound(label=f"material_{material}", children=grouped[material])
        for material in SYSTEM_MATERIALS[label]
    ])


def materials_for_system(system):
    materials = SYSTEM_MATERIALS[system]
    return {
        "definitions": {material: MATERIAL_DEFINITIONS[material] for material in materials},
        "assignments": [
            {"targets": [f"#material_{material}"], "material": material}
            for material in materials
        ],
    }


def style(shape, label: str, color=None):
    """Label and color a leaf; the owning @step assigns its named finish."""
    shape.label = label
    if color is not None:
        shape.color = color
    return shape

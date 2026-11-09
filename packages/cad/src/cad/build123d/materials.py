"""``cad.build123d.materials``: named looks for what bd_materials' catalogue lacks.

Printed circuit boards and their parts, and the common process finishes, as scalar looks that the
viewer, an OCCT still and a GLB all draw (no texture maps: a part's mesh has no UVs)::

    from cad.build123d import materials

    board.material = materials.soldermask("green")
    paint(board, pads, materials.enig())
    housing.material = materials.anodized("black")
    bracket.material = materials.powder_coat("RAL7016", finish="satin")

Each factory returns a fresh native ``bd_materials.FinishedMaterial``: the physics one of bd_materials' own
classes (its metals' and FR-4's tables where they have them, renamed for the look; ``custom_metal`` and
``custom_plastic`` or ``SolidMaterial`` where they do not), the look a ``threejs_materials.PbrProperties``.
No class of its own, so any release that reads an xbf reads these. A ``color`` is a preset name, an sRGB
hex string, a CSS name or an sRGB 0-1 tuple. ``substrate=`` takes the bd_materials metal a finish is on;
its physics are kept, its look replaced.

Nothing here loads before a factory is called: ``import cad.build123d.materials`` imports neither
bd_materials nor threejs_materials.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from bd_materials import FinishedMaterial

__all__ = [
    # Boards
    "soldermask", "soldermask_green", "soldermask_matte_black", "fr4", "silkscreen",
    "bare_copper", "enig", "hasl", "solder",
    # Components
    "mold_compound", "ceramic", "led_lens", "connector_housing",
    # Process finishes
    "anodized", "anodized_black", "powder_coat", "powder_coat_black", "bead_blasted", "brushed",
    "zinc_plated", "black_oxide",
]

Color = Any  # a preset name, "#rrggbb", a CSS name or an sRGB (r, g, b) of 0-1 floats

SOLDERMASK = {"green": "#1d6b38", "black": "#18191b", "blue": "#1b3f8b", "red": "#a01c22",
              "white": "#ebeae4", "yellow": "#d8b21f", "purple": "#4a2a6c"}
SILKSCREEN = {"white": "#f2f2ee", "black": "#141414", "yellow": "#e6c52c"}
ANODIZE = {"clear": "#c8cbce", "silver": "#c8cbce", "black": "#1e1f22", "grey": "#5d6166", "gray": "#5d6166",
           "red": "#9e1b25", "blue": "#1e4f9c", "gold": "#c79a3c", "green": "#2f6b3a", "purple": "#5a3478",
           "orange": "#c4581e"}
# RAL classic shades, by number, and plain names.
POWDER_COAT = {"black": "#1c1c1c", "white": "#f1f0ea", "grey": "#383e42", "gray": "#383e42",
               "RAL9005": "#0e0e10", "RAL9010": "#f1ede1", "RAL9016": "#f1f0ea", "RAL7016": "#383e42",
               "RAL7035": "#c5c7c4", "RAL7024": "#45494e", "RAL3020": "#bb1e10", "RAL5010": "#13447c",
               "RAL1023": "#f0ca00", "RAL6005": "#114232"}
CERAMIC = {"white": "#f0eee8", "tan": "#c6aa7c", "beige": "#c6aa7c"}
LED = {"clear": "#ffffff", "white": "#ffffff", "red": "#ff3b30", "green": "#34c759", "blue": "#2f6bff",
       "amber": "#ffb000", "yellow": "#ffe14d"}
HOUSING = {"black": "#1f1f20", "white": "#ecebe5", "natural": "#ddd3b8", "beige": "#ddd3b8", "grey": "#7d8085",
           "gray": "#7d8085"}
ZINC = {"clear": ("#d9dde2", 1.0, 0.3), "blue": ("#c5cfdf", 1.0, 0.3), "yellow": ("#cfb766", 0.85, 0.35),
        "black": ("#2a2b2e", 0.6, 0.4)}

Finish = Literal["glossy", "matte"]
Sheen = Literal["matte", "satin", "gloss"]


def _named(table: dict[str, Any], color: Color, what: str) -> tuple[Any, str]:
    """A colour (a preset of ``table``, or one as given) and its slug in the look's name."""
    if isinstance(color, str):
        presets = {name.lower(): (name, value) for name, value in table.items()}
        if color.strip().lower() in presets:
            name, found = presets[color.strip().lower()]
            return found, name if name.startswith("RAL") else name.lower()
        if not color.strip():
            raise ValueError(f"{what}: an empty colour; one of {sorted(table)}, a hex string or an sRGB tuple")
        return color, color.strip().lstrip("#").lower().replace(" ", "_")
    try:
        rgb = [float(value) for value in color][:3]
    except TypeError:
        raise TypeError(f"{what}: a colour is a preset name, a hex string, a CSS name or an sRGB (r, g, b) "
                        f"tuple of 0-1 floats, not {type(color).__name__}") from None
    return tuple(rgb), "".join(f"{round(min(max(value, 0.0), 1.0) * 255):02x}" for value in rgb)


def _choice(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise ValueError(f"{what} is one of {', '.join(map(repr, allowed))}, not {value!r}")
    return value


def _look(name: str, physics: Any, **pbr: Any) -> FinishedMaterial:
    """A finished material: ``physics`` renamed for the look, and a scalar PBR look of that name."""
    from bd_materials import FinishedMaterial
    from threejs_materials import PbrProperties

    return FinishedMaterial(replace(physics, name=name), pbr=PbrProperties.create(name, **pbr))


def _metal(substrate: FinishedMaterial | None, default: str) -> Any:
    """The bd_materials metal a finish is on: ``substrate``, else bd_materials' own ``default``."""
    from bd_materials import FinishedMaterial, metals

    if substrate is None:
        return getattr(metals, default)()
    if not isinstance(substrate, FinishedMaterial):
        raise TypeError(f"substrate is a bd_materials FinishedMaterial (metals.aluminum(), ...), "
                        f"not {type(substrate).__name__}")
    return substrate


def _f0(metal: FinishedMaterial) -> Any:
    """A metal's base colour (its reflectance at normal incidence) as bd_materials' own look has it."""
    color = metal.pbr.values.color
    return tuple(color) if color else (0.8, 0.8, 0.8)


# --- Boards --------------------------------------------------------------------------------------


def _fr4_physics() -> Any:
    from bd_materials import plastics

    return plastics.fr4().material


def soldermask(color: Color = "green", finish: Finish = "glossy") -> FinishedMaterial:
    """A board in solder mask over FR-4 (its physics bd_materials' FR-4): ``glossy`` a clear-coated
    lacquer, ``matte`` a flat one. Presets: green, black, blue, red, white, yellow, purple."""
    value, slug = _named(SOLDERMASK, color, "soldermask")
    _choice(finish, ("glossy", "matte"), "soldermask's finish")
    look = (dict(roughness=0.35, clearcoat=0.6, clearcoat_roughness=0.15) if finish == "glossy"
            else dict(roughness=0.75))
    return _look(f"soldermask_{slug}" + ("_matte" if finish == "matte" else ""), _fr4_physics(),
                 color=value, metalness=0.0, ior=1.5, **look)


def soldermask_green() -> FinishedMaterial:
    """The common board: glossy green solder mask over FR-4."""
    return soldermask("green")


def soldermask_matte_black() -> FinishedMaterial:
    """Matte black solder mask over FR-4."""
    return soldermask("black", finish="matte")


def fr4() -> FinishedMaterial:
    """Bare FR-4 laminate, unmasked: a pale yellow-green glass-epoxy (a board's edge, a slot's wall)."""
    return _look("fr4_bare", _fr4_physics(), color="#cdc28a", metalness=0.0, roughness=0.5, ior=1.55)


def silkscreen(color: Color = "white") -> FinishedMaterial:
    """Silkscreen ink, flat and matte, painted on a board's faces. Presets: white, black, yellow.
    An ink has no bulk physics: its density is unknown."""
    from bd_materials.core import RangeMaterial

    value, slug = _named(SILKSCREEN, color, "silkscreen")
    return _look(f"silkscreen_{slug}", RangeMaterial(name="silkscreen", density=None),
                 color=value, metalness=0.0, roughness=0.85, ior=1.5)


def _copper() -> Any:
    from bd_materials import metals

    return metals.copper().material


def bare_copper(oxidized: bool = False) -> FinishedMaterial:
    """Bare copper (bd_materials' C110), bright, or ``oxidized`` to a dull brown-orange."""
    if oxidized:
        return _look("copper_oxidized", _copper(), color="#c48466", metalness=1.0, roughness=0.45)
    from bd_materials import metals

    return _look("copper_bare", _copper(), color=_f0(metals.copper()), metalness=1.0, roughness=0.25)


def enig() -> FinishedMaterial:
    """ENIG (electroless nickel, immersion gold) on copper pads: a pale, slightly satin gold. The physics
    are the pad's copper; the plating is microns thick."""
    return _look("enig_gold", _copper(), color="#f4d58f", metalness=1.0, roughness=0.3)


def hasl(lead_free: bool = True) -> FinishedMaterial:
    """HASL (hot-air solder levelled) tin on copper pads: bright, the lead-free alloy a little duller.
    The physics are the pad's copper."""
    return _look("hasl_lead_free" if lead_free else "hasl", _copper(), color="#d3d6d8", metalness=1.0,
                 roughness=0.35 if lead_free else 0.22)


def solder() -> FinishedMaterial:
    """Solder (SAC305, Sn-3Ag-0.5Cu): a joint, a fillet, a ball. Its own physics (``custom_metal``)."""
    from bd_materials import metals
    from bd_materials.core import Range

    physics = metals.custom_metal(
        "SAC305", 7380, family="tin", tensile_strength=Range(40, 55), yield_strength=Range(30, 45),
        modulus_of_elasticity=Range(45, 54), shear_modulus=Range(16, 20), poisson_ratio=Range(0.35, 0.40),
        hardness=Range(13, 16), hardness_scale="HB", melting_temperature=Range(217, 220),
        max_service_temp=Range(125, 150), specific_heat_capacity=Range(220, 240), thermal_conductivity=Range(55, 64),
        thermal_expansion=Range(21e-6, 23e-6),
    ).material
    return _look("solder_sac305", physics, color="#cfd2d4", metalness=1.0, roughness=0.3)


# --- Components ----------------------------------------------------------------------------------


def mold_compound() -> FinishedMaterial:
    """Black epoxy moulding compound: an IC package, a moulded module. Its own physics (``custom_plastic``,
    silica-filled epoxy)."""
    from bd_materials import plastics
    from bd_materials.core import Range

    physics = plastics.custom_plastic(
        "epoxy_mold_compound", 1900, family="epoxy", tensile_strength=Range(70, 120),
        modulus_of_elasticity=Range(15, 25), poisson_ratio=Range(0.25, 0.30), elongation_at_break=Range(0.5, 1.5),
        glass_transition_temperature=Range(130, 180), heat_deflection_temperature=Range(150, 200),
        max_service_temp=Range(150, 175), specific_heat_capacity=Range(800, 1000), thermal_conductivity=Range(0.6, 1.0),
        thermal_expansion=Range(8e-6, 12e-6),
    ).material
    return _look("mold_compound_black", physics, color="#1c1c1e", metalness=0.0, roughness=0.65, ior=1.5)


def ceramic(color: Color = "white") -> FinishedMaterial:
    """A ceramic body: a chip capacitor's (``tan``), a resistor's or a substrate's (``white``). Physics:
    96% alumina (``SolidMaterial``). Presets: white, tan, beige."""
    from bd_materials.core import Range, SolidMaterial

    value, slug = _named(CERAMIC, color, "ceramic")
    physics = SolidMaterial(
        name="alumina_96", density=3900, family="ceramic", tensile_strength=Range(200, 300),
        modulus_of_elasticity=Range(300, 370), shear_modulus=Range(120, 150), poisson_ratio=Range(0.21, 0.24),
        specific_heat_capacity=Range(750, 880), max_service_temp=Range(1500, 1700),
        thermal_expansion=Range(6.5e-6, 8.5e-6), thermal_conductivity=Range(20, 30))
    return _look(f"ceramic_{slug}", physics, color=value, metalness=0.0, roughness=0.5, ior=1.7)


def led_lens(color: Color = "clear", diffused: bool = False) -> FinishedMaterial:
    """An LED's lens, clear epoxy that light passes through (``transmission``), tinted by ``color``;
    ``diffused`` a frosted one. Presets: clear, white, red, green, blue, amber, yellow."""
    from bd_materials import plastics
    from bd_materials.core import Range

    value, slug = _named(LED, color, "led_lens")
    physics = plastics.custom_plastic(
        "clear_epoxy", 1150, family="epoxy", transparent=True, tensile_strength=Range(50, 80),
        modulus_of_elasticity=Range(2.5, 3.5), poisson_ratio=Range(0.33, 0.37),
        glass_transition_temperature=Range(110, 130), max_service_temp=Range(100, 120),
        thermal_conductivity=Range(0.17, 0.21), thermal_expansion=Range(55e-6, 70e-6),
    ).material
    tint = {} if slug in ("clear", "white") else dict(attenuation_color=value, attenuation_distance=0.002)
    return _look(f"led_lens_{slug}" + ("_diffused" if diffused else ""), physics, color=value, metalness=0.0,
                 roughness=0.55 if diffused else 0.05, ior=1.5, transmission=0.7 if diffused else 1.0, **tint)


def connector_housing(color: Color = "black") -> FinishedMaterial:
    """A connector's or a switch's housing: glass-filled PBT (PBT-GF30, ``custom_plastic``), moulded
    satin. Presets: black, white, natural, beige, grey."""
    from bd_materials import plastics
    from bd_materials.core import Range

    value, slug = _named(HOUSING, color, "connector_housing")
    physics = plastics.custom_plastic(
        "PBT_GF30", 1530, family="PBT", tensile_strength=Range(120, 140), modulus_of_elasticity=Range(9, 10.5),
        poisson_ratio=Range(0.35, 0.40), elongation_at_break=Range(2, 3.5), glass_transition_temperature=Range(50, 60),
        heat_deflection_temperature=Range(200, 215), max_service_temp=Range(130, 150),
        specific_heat_capacity=Range(1200, 1400), thermal_conductivity=Range(0.2, 0.3),
        thermal_expansion=Range(25e-6, 60e-6),
    ).material
    return _look(f"connector_housing_{slug}", physics, color=value, metalness=0.0, roughness=0.45, ior=1.55)


# --- Process finishes ----------------------------------------------------------------------------


def anodized(color: Color = "clear", substrate: FinishedMaterial | None = None) -> FinishedMaterial:
    """Anodized aluminium (bd_materials' 6061-T6 unless ``substrate``): the dyed oxide over the metal,
    satin, its colour carried by the coating rather than by a coloured mirror. Presets: clear, silver,
    black, grey, red, blue, gold, green, purple, orange."""
    value, slug = _named(ANODIZE, color, "anodized")
    metalness = {"clear": 0.9, "silver": 0.9, "black": 0.45}.get(slug, 0.7)
    return _look(f"anodized_{slug}", _metal(substrate, "aluminum").material, color=value, metalness=metalness,
                 roughness=0.5 if slug == "black" else 0.42, clearcoat=0.2, clearcoat_roughness=0.35)


def anodized_black() -> FinishedMaterial:
    """Black anodized 6061-T6."""
    return anodized("black")


def powder_coat(color: Color = "black", finish: Sheen = "satin",
                substrate: FinishedMaterial | None = None) -> FinishedMaterial:
    """Powder coat over a metal (bd_materials' mild steel unless ``substrate``): an opaque polymer skin,
    ``matte``, ``satin`` or ``gloss``. Presets: black, white, grey, and RAL9005, RAL9010, RAL9016, RAL7016,
    RAL7035, RAL7024, RAL3020, RAL5010, RAL1023, RAL6005."""
    value, slug = _named(POWDER_COAT, color, "powder_coat")
    _choice(finish, ("matte", "satin", "gloss"), "powder_coat's finish")
    look = {"matte": dict(roughness=0.8), "satin": dict(roughness=0.5),
            "gloss": dict(roughness=0.25, clearcoat=0.5, clearcoat_roughness=0.1)}[finish]
    return _look(f"powder_coat_{slug}_{finish}", _metal(substrate, "mild_steel").material, color=value,
                 metalness=0.0, ior=1.5, **look)


def powder_coat_black() -> FinishedMaterial:
    """Satin black powder coat on mild steel."""
    return powder_coat("black")


def bead_blasted(substrate: FinishedMaterial | None = None) -> FinishedMaterial:
    """Bead-blasted metal (bd_materials' 6061-T6 unless ``substrate``): an even, diffuse satin in the
    metal's own colour."""
    metal = _metal(substrate, "aluminum")
    return _look(f"bead_blasted_{metal.material.family or 'metal'}", metal.material, color=_f0(metal),
                 metalness=1.0, roughness=0.55)


def brushed(substrate: FinishedMaterial | None = None) -> FinishedMaterial:
    """Brushed metal (bd_materials' 304 stainless unless ``substrate``): satin, its highlight stretched
    across the grain (``anisotropy``), the grain around the part's Z axis."""
    metal = _metal(substrate, "stainless")
    return _look(f"brushed_{metal.material.family or 'metal'}", metal.material, color=_f0(metal),
                 metalness=1.0, roughness=0.3, anisotropy=0.8, anisotropy_rotation=0.0)


def zinc_plated(color: Color = "clear", substrate: FinishedMaterial | None = None) -> FinishedMaterial:
    """Zinc-plated steel (bd_materials' mild steel unless ``substrate``), passivated ``clear``, ``blue``,
    ``yellow`` or ``black``."""
    if not isinstance(color, str) or color.lower() not in ZINC:
        raise ValueError(f"zinc_plated's colour is one of {', '.join(map(repr, ZINC))}, not {color!r}")
    value, metalness, roughness = ZINC[color.lower()]
    return _look(f"zinc_plated_{color.lower()}", _metal(substrate, "mild_steel").material, color=value,
                 metalness=metalness, roughness=roughness)


def black_oxide(oiled: bool = True, substrate: FinishedMaterial | None = None) -> FinishedMaterial:
    """Black-oxide steel (bd_materials' mild steel unless ``substrate``): a dark, faintly metallic
    conversion coat, ``oiled`` a little glossier."""
    return _look("black_oxide" + ("" if oiled else "_dry"), _metal(substrate, "mild_steel").material,
                 color="#2b2c2e", metalness=0.6, roughness=0.38 if oiled else 0.5)

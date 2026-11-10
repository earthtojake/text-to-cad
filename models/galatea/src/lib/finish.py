"""Galatea's finishes: every part wears one of these native materials.

Physics comes from `bd_materials` (a real grade where there is one, a homogenised
density where a part stands for an assembly the model does not open: an actuator, a
battery, an electronics module). The look is a scalar PBR record, no texture maps,
so the snapshot, the viewer and a GLB all draw it.
"""

from functools import cache

from bd_materials import glass, metals, plastics
from threejs_materials import PbrProperties


def _look(base, name, **pbr):
    base.pbr = PbrProperties.create(name, **pbr)
    return base


@cache
def material(name):
    return _FINISHES[name]()


def apply(shape, name):
    """Give `shape` the finish `name` and return it. Set after the last geometric operation."""
    shape.material = material(name)
    return shape


_FINISHES = {
    # Shells: carbon-fibre skins under an ivory ceramic lacquer, clear-coated.
    "ivory": lambda: _look(plastics.cfrp(), "ivory_lacquer", color="#f3efe4", metalness=0.0, roughness=0.34,
                           clearcoat=1.0, clearcoat_roughness=0.08),
    # Inner liners, bellows and moulded covers: glass-filled nylon, satin graphite.
    "graphite": lambda: _look(plastics.nylon(), "graphite_nylon", color="#33373d", metalness=0.0, roughness=0.55),
    # Structure: 7075 aluminium, hard anodised gunmetal.
    "gunmetal": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "gunmetal_anodise", color="#8a929d",
                              metalness=0.6, roughness=0.45),
    # A darker structural tone for links that sit behind the gunmetal ones.
    "slate": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "slate_anodise", color="#5b636e",
                           metalness=0.55, roughness=0.45),
    # Actuator housings: finned aluminium, bronze anodised. Density is the assembly's
    # (stator, rotor, gear set and bearings homogenised), not aluminium's.
    "bronze": lambda: _look(metals.custom_metal("Actuator assembly, bronze anodised housing", 3400.0,
                                                family="aluminum"),
                            "bronze_anodise", color="#b9773f", metalness=1.0, roughness=0.36),
    # Bronze-anodised machined trim that is plain aluminium all the way through.
    "bronze_trim": lambda: _look(metals.aluminum(), "bronze_trim", color="#b9773f", metalness=1.0, roughness=0.36),
    # Output flanges, axles, pins, the Achilles rods: 4340 steel, quenched and tempered, ground satin.
    "steel": lambda: _look(metals.alloy_steel(metals.AlloySteel.G4340_QUENCHED_TEMPERED), "steel_satin", color="#c4c5c4",
                           metalness=1.0, roughness=0.28),
    # Fasteners: alloy steel, black oxide.
    "black_oxide": lambda: _look(metals.alloy_steel(), "black_oxide", color="#22252a", metalness=0.9, roughness=0.5),
    # The knee pushrods: titanium, satin.
    "titanium": lambda: _look(metals.titanium(), "titanium_satin", color="#a9a59d", metalness=1.0, roughness=0.3),
    # Structural tubes: gloss carbon.
    "carbon": lambda: _look(plastics.cfrp(), "carbon_gloss", color="#17191c", metalness=0.0, roughness=0.3,
                            clearcoat=1.0, clearcoat_roughness=0.05),
    # The sensor bay's liner: aluminium, bead-blasted and anodised black.
    "black": lambda: _look(metals.aluminum(), "black_anodise", color="#101215", metalness=0.4, roughness=0.62),
    # Soles, pads, bump stops: TPU.
    "rubber": lambda: _look(plastics.tpu(), "rubber_matte", color="#1d1e20", metalness=0.0, roughness=0.9),
    # The visor: smoked polycarbonate, clear enough that the eyes behind it show through.
    "visor": lambda: _look(plastics.pc(), "visor_smoke", color="#1b222b", metalness=0.0, roughness=0.05,
                           clearcoat=1.0, clearcoat_roughness=0.03, transmission=1.0),
    # Light guides: status bar, eye rings.
    "glow": lambda: _look(plastics.pc(), "glow_amber", color="#ff9d3c", metalness=0.0, roughness=0.4,
                          emissive="#ff7a10", emissive_intensity=0.6),
    # Camera and depth-sensor windows.
    "lens": lambda: _look(glass.borosilicate(), "lens_glass", color="#0a0c10", metalness=0.2, roughness=0.02,
                          clearcoat=1.0, clearcoat_roughness=0.0),
    # Battery pack and compute module: homogenised densities.
    "battery": lambda: _look(plastics.custom_plastic("Battery pack (cells, busbars and case homogenised)", 2100.0,
                                                     family="PC"),
                             "battery_case", color="#2b2e33", metalness=0.0, roughness=0.5),
    "module": lambda: _look(plastics.custom_plastic("Electronics module (homogenised)", 1300.0, family="PC"),
                            "module_case", color="#3a3e45", metalness=0.2, roughness=0.5),
}

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
    # Output flanges, axles, pins: stainless, satin.
    "steel": lambda: _look(metals.stainless(), "steel_satin", color="#c4c5c4", metalness=1.0, roughness=0.28),
    # Fasteners: alloy steel, black oxide.
    "black_oxide": lambda: _look(metals.alloy_steel(), "black_oxide", color="#22252a", metalness=0.9, roughness=0.5),
    # Pushrods and linkage tubes: titanium, satin.
    "titanium": lambda: _look(metals.titanium(), "titanium_satin", color="#a9a59d", metalness=1.0, roughness=0.3),
    # Structural tubes: gloss carbon.
    "carbon": lambda: _look(plastics.cfrp(), "carbon_gloss", color="#17191c", metalness=0.0, roughness=0.3,
                            clearcoat=1.0, clearcoat_roughness=0.05),
    # Soles, pads, bump stops: TPU.
    "rubber": lambda: _look(plastics.tpu(), "rubber_matte", color="#1d1e20", metalness=0.0, roughness=0.9),
    # The face: smoked polycarbonate, drawn near-opaque so the sensors glow through it.
    "visor": lambda: _look(plastics.pc(), "visor_smoke", color="#0d1014", metalness=0.0, roughness=0.06,
                           clearcoat=1.0, clearcoat_roughness=0.03),
    # Light guides: status bar, eye rings.
    "glow": lambda: _look(plastics.pc(), "glow_amber", color="#ffd9a6", metalness=0.0, roughness=0.4,
                          emissive="#ffb04a", emissive_intensity=1.6),
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

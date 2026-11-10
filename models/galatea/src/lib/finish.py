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


def actuator(model, density):
    """The finish of an actuator of `model`: black anodised, at the density that gives the unit its maker's mass."""
    name = f"actuator_{model}"
    _FINISHES[name] = lambda: _look(metals.custom_metal(f"RobStride {model}, homogenised", density, family="aluminum"),
                                    "actuator_black", color="#1b1d21", metalness=0.6, roughness=0.42)
    return name


def apply(shape, name):
    """Give `shape` the finish `name` and return it. Set after the last geometric operation."""
    shape.material = material(name)
    return shape


_FINISHES = {
    # The restyled exterior: two tones. Shells are a satin pearl white over a matte black
    # under-body; joints are black anodised; the face is one smoked shield.
    "shell": lambda: _look(plastics.cfrp(), "shell_pearl", color="#e6e8ea", metalness=0.0, roughness=0.42,
                           clearcoat=0.6, clearcoat_roughness=0.25),
    "under": lambda: _look(plastics.nylon(), "under_black", color="#17181b", metalness=0.0, roughness=0.78),
    "joint": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "joint_black", color="#202226", metalness=0.55,
                           roughness=0.48),
    "trim": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "trim_grey", color="#8f959c", metalness=0.8,
                          roughness=0.38),
    "face": lambda: _look(plastics.pc(), "face_gloss", color="#050607", metalness=0.0, roughness=0.04,
                          clearcoat=1.0, clearcoat_roughness=0.02),
    "smoke35": lambda: _look(plastics.pc(), "smoke35", color="#050607", metalness=0.0, roughness=0.04,
                             clearcoat=1.0, clearcoat_roughness=0.02, transmission=0.35),
    "smoke60": lambda: _look(plastics.pc(), "smoke60", color="#050607", metalness=0.0, roughness=0.04,
                             clearcoat=1.0, clearcoat_roughness=0.02, transmission=0.6),
    "smoke85": lambda: _look(plastics.pc(), "smoke85", color="#050607", metalness=0.0, roughness=0.04,
                             clearcoat=1.0, clearcoat_roughness=0.02, transmission=0.85),
    "light": lambda: _look(plastics.pc(), "light_white", color="#eef4ff", metalness=0.0, roughness=0.4,
                           emissive="#dfeaff", emissive_intensity=0.9),
    # Shells: carbon-fibre skins under an ivory ceramic lacquer, clear-coated.
    "ivory": lambda: _look(plastics.cfrp(), "shell_pearl", color="#e6e8ea", metalness=0.0, roughness=0.42,
                           clearcoat=0.6, clearcoat_roughness=0.25),
    # Inner liners, bellows and moulded covers: glass-filled nylon, satin graphite.
    "graphite": lambda: _look(plastics.nylon(), "graphite_nylon", color="#33373d", metalness=0.0, roughness=0.55),
    # Structure: 7075 aluminium, hard anodised gunmetal.
    "gunmetal": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "gunmetal_anodise", color="#4b4f56",
                              metalness=0.6, roughness=0.48),
    # A darker structural tone for links that sit behind the gunmetal ones.
    "slate": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "slate_anodise", color="#3a3d43",
                           metalness=0.55, roughness=0.5),
    # Actuator housings: finned aluminium, bronze anodised. Density is the assembly's
    # (stator, rotor, gear set and bearings homogenised), not aluminium's.
    "bronze": lambda: _look(metals.custom_metal("Actuator assembly, bronze anodised housing", 3400.0,
                                                family="aluminum"),
                            "actuator_black", color="#1b1d21", metalness=0.6, roughness=0.42),
    # Bronze-anodised machined trim that is plain aluminium all the way through.
    "bronze_trim": lambda: _look(metals.aluminum(), "trim_dark", color="#2a2d32", metalness=0.7, roughness=0.4),
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
    "glow": lambda: _look(plastics.pc(), "light_white", color="#eef4ff", metalness=0.0, roughness=0.4,
                          emissive="#dfeaff", emissive_intensity=0.9),
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

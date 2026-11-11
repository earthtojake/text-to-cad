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
    # The exterior, in two tones. Panels: carbon-fibre skins in a satin pearl lacquer.
    "shell": lambda: _look(plastics.cfrp(), "shell_pearl", color="#e6e8ea", metalness=0.0, roughness=0.42,
                           clearcoat=0.6, clearcoat_roughness=0.25),
    # Liners, the under-body that shows between panels, and moulded covers: glass-filled nylon, matte black.
    "under": lambda: _look(plastics.nylon(), "under_black", color="#17181b", metalness=0.0, roughness=0.78),
    # Passive pivots' caps: aluminium, anodised black.
    "joint": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "joint_black", color="#202226", metalness=0.55,
                           roughness=0.48),
    # The styling model's trim and its opaque face.
    "trim": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "trim_grey", color="#8f959c", metalness=0.8,
                          roughness=0.38),
    "face": lambda: _look(plastics.pc(), "face_gloss", color="#050607", metalness=0.0, roughness=0.04,
                          clearcoat=1.0, clearcoat_roughness=0.02),
    # The face shield: smoked polycarbonate that lets a third of the light through, so what stands behind it shows faintly.
    "smoke35": lambda: _look(plastics.pc(), "smoke35", color="#050607", metalness=0.0, roughness=0.04,
                             clearcoat=1.0, clearcoat_roughness=0.02, transmission=0.35),
    # Light guides: the head's and the chest's status lines.
    "light": lambda: _look(plastics.pc(), "light_white", color="#eef4ff", metalness=0.0, roughness=0.4,
                           emissive="#dfeaff", emissive_intensity=0.9),
    # The accents, and there are few: a hairline ring at a joint, a sleeve's rim, the wordmark. Aluminium, anodised champagne.
    "accent": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "accent_champagne", color="#c4a57a", metalness=1.0,
                            roughness=0.32),
    # Structure: 7075 aluminium, anodised black, so that what shows between the panels reads as one
    # under-body with the liners and the drives.
    "frame": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "frame_black", color="#2b2d31",
                           metalness=0.6, roughness=0.5),
    # The same, a shade deeper, for links that sit behind the others.
    "link": lambda: _look(metals.aluminum(metals.Alu.G7075_T6), "link_black", color="#222428",
                          metalness=0.55, roughness=0.52),
    # Output hubs, axles, pins, the ankle's rod: 4340 steel, quenched and tempered, ground satin.
    "steel": lambda: _look(metals.alloy_steel(metals.AlloySteel.G4340_QUENCHED_TEMPERED), "steel_satin", color="#c4c5c4",
                           metalness=1.0, roughness=0.28),
    # Fasteners: alloy steel, black oxide.
    "black_oxide": lambda: _look(metals.alloy_steel(), "black_oxide", color="#22252a", metalness=0.9, roughness=0.5),
    # The knee's pushrods: titanium, satin.
    "titanium": lambda: _look(metals.titanium(), "titanium_satin", color="#a9a59d", metalness=1.0, roughness=0.3),
    # Structural tubes: gloss carbon.
    "carbon": lambda: _look(plastics.cfrp(), "carbon_gloss", color="#17191c", metalness=0.0, roughness=0.3,
                            clearcoat=1.0, clearcoat_roughness=0.05),
    # Ports and small moulded parts: nylon, satin graphite.
    "graphite": lambda: _look(plastics.nylon(), "graphite_nylon", color="#33373d", metalness=0.0, roughness=0.55),
    # Soles, pads, bump stops: TPU.
    "rubber": lambda: _look(plastics.tpu(), "rubber_matte", color="#1d1e20", metalness=0.0, roughness=0.9),
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

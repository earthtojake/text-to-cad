"""SHORT CIRCUIT's materials: one place for every finish the machine is made of.

The palette: matte black (soldermask, dyed MJF nylon, black-anodised aluminium), gold (ENIG, brass), clear
(cast acrylic, clear resin), one accent (signal orange: the rubbers and the buttons) and warm amber light.
Each look is a scalar PBR override of a bd_materials family: a process texture (MJF's, FDM's) carries
image maps the viewer cannot draw without UVs, so the printed parts' grain is a roughness, not a map.
"""
from __future__ import annotations

from bd_materials import finishes, metals, plastics, resins

AMBER = (1.0, 0.64, 0.24)          # the machine's light: inserts, bumpers, the backbox's marquee
DMD = (1.0, 0.42, 0.08)            # the display's orange


def _look(mat, **pbr):
    mat.pbr = mat.pbr.override(**pbr)
    return mat


def soldermask():
    """Matte black soldermask over FR-4."""
    return _look(plastics.fr4(color="#0b0c0f"), color=(0.040, 0.043, 0.050), roughness=0.58, clearcoat=0.12,
                 clearcoat_roughness=0.45)


def enig():
    """Electroless nickel immersion gold: paler and flatter than jewellery gold."""
    return _look(metals.gold(), color=(0.90, 0.74, 0.46), roughness=0.30)


def silkscreen():
    return _look(plastics.pla(color="#f2f0ea"), color=(0.93, 0.92, 0.88), roughness=0.75)


def fr4_window(lit: bool = False):
    """Bare FR-4 where no copper and no mask cover it: an insert, glowing when its LED is on."""
    if lit:
        return _look(plastics.fr4(color="#ff8a1e"), color=(1.0, 0.36, 0.03), roughness=0.5, emissive=(1.0, 0.30, 0.02),
                     emissive_intensity=1.3)
    return _look(plastics.fr4(color="#d9d2b8"), color=(0.80, 0.77, 0.66), roughness=0.45, transmission=0.2,
                 thickness=1.6)


def mjf_black():
    """MJF PA12, dyed black: a fine matte grain."""
    return _look(plastics.nylon(color="#17181b"), color=(0.075, 0.078, 0.086), roughness=0.82)


def anodised_black():
    return _look(metals.aluminum(finish=finishes.anodize("black")), color=(0.06, 0.06, 0.065), roughness=0.42)


def clear_resin():
    """Clear SLA resin, polished: the bumpers' crystals."""
    return _look(resins.transparent(), transmission=0.96, roughness=0.03, thickness=5.0, ior=1.52)


def smoked_amber():
    """2 mm smoked amber cast acrylic: the target faces."""
    return _look(plastics.pmma(color="#ff9a2e", thickness_mm=2), color=(1.0, 0.56, 0.16), transmission=0.72,
                 roughness=0.06, thickness=2.0)


def smoked_bronze(lit: bool = False):
    """2 mm smoked grey cast acrylic: the sling plastics, glowing amber when the LED under them is lit."""
    if lit:
        return _look(plastics.pmma(color="#5a3a1e", thickness_mm=2), color=(0.55, 0.32, 0.12), transmission=0.45,
                     roughness=0.05, thickness=2.0, emissive=(1.0, 0.46, 0.10), emissive_intensity=0.7)
    return _look(plastics.pmma(color="#2a2b2e", thickness_mm=2), color=(0.20, 0.20, 0.22), transmission=0.7,
                 roughness=0.04, thickness=2.0)


def smoked_grey():
    """1 mm smoked grey acrylic: the display window."""
    return _look(plastics.pmma(color="#202226", thickness_mm=1), color=(0.30, 0.30, 0.32), transmission=0.86,
                 roughness=0.03, thickness=1.0)


def crystal(lit: bool = False):
    """The bumpers' crystals: amber-tinted clear resin, the LED under each scattering in it when lit."""
    if lit:
        return _look(resins.transparent(), transmission=0.7, roughness=0.04, thickness=5.0, ior=1.52,
                     color=(1.0, 0.55, 0.16), emissive=(1.0, 0.36, 0.04), emissive_intensity=0.9)
    return _look(resins.transparent(), transmission=0.9, roughness=0.03, thickness=5.0, ior=1.52, color=(1.0, 0.74, 0.42))


def smoked_panel():
    """3 mm smoked grey cast acrylic: the cabinet's sides, front and back (the engine room seen through)."""
    return _look(plastics.pmma(color="#2a2c31", thickness_mm=3), color=(0.07, 0.074, 0.082), transmission=0.0,
                 opacity=0.62, roughness=0.05)


def glass():
    return _look(plastics.pmma(color="clear", thickness_mm=2), transmission=0.98, roughness=0.01, thickness=2.0)


def rubber_orange():
    return _look(plastics.rubber(color="#ff5a1f"), color=(1.0, 0.33, 0.10), roughness=0.62)


def rubber_black():
    return _look(plastics.rubber(color="#111214"), color=(0.05, 0.05, 0.055), roughness=0.7)


def orange_resin():
    """The buttons and the plunger's knob: signal orange."""
    return _look(resins.tough(), color=(1.0, 0.33, 0.10), roughness=0.38)


def white_resin():
    """The flipper bats: bone white."""
    return _look(resins.tough(), color=(0.93, 0.91, 0.86), roughness=0.33, clearcoat=0.3)


def brass():
    return _look(metals.brass(), color=(0.86, 0.72, 0.44), roughness=0.22)


def chrome():
    return _look(metals.stainless(), color=(0.94, 0.94, 0.95), roughness=0.03)


def steel():
    return _look(metals.stainless(), color=(0.72, 0.72, 0.73), roughness=0.28)


def zinc():
    """Zinc-plated steel: the solenoids' frames."""
    return _look(metals.mild_steel(), color=(0.70, 0.71, 0.74), roughness=0.35)


def copper_wire():
    return _look(metals.copper(), color=(0.80, 0.42, 0.24), roughness=0.3)


def component_black():
    """Moulded IC packages, connectors."""
    return _look(plastics.pla(color="#1c1d20"), color=(0.09, 0.09, 0.10), roughness=0.55)


def ceramic_tan():
    return _look(plastics.pla(color="#b9a37a"), color=(0.62, 0.53, 0.38), roughness=0.5)


def led_white():
    """An LED's white body (SK6812, WS2812B)."""
    return _look(plastics.pla(color="#ebe8df"), color=(0.88, 0.87, 0.83), roughness=0.4)


def led(lit: bool = False, colour=(1.0, 0.33, 0.03), strength: float = 1.5):
    if lit:
        return _look(plastics.pmma(color="#ffb347"), transmission=0.0, color=colour, roughness=0.4, emissive=colour,
                     emissive_intensity=strength)
    return _look(plastics.pmma(color="#ffcf8a"), transmission=0.3, color=(0.95, 0.80, 0.58), roughness=0.25)


def dmd_dot(lit: bool):
    if lit:
        return _look(plastics.pmma(color="#ff6a14"), transmission=0.0, color=(1.0, 0.34, 0.04), roughness=0.4,
                     emissive=(1.0, 0.32, 0.03), emissive_intensity=2.6)
    return _look(plastics.pmma(color="#3a2416"), transmission=0.0, color=(0.22, 0.13, 0.08), roughness=0.4)

"""Materials: what a part is made of, as a value, and a catalogue of common ones.

A ``Material`` is a physical material -- what it is and what it weighs, how stiff and strong it
is, how it takes heat -- with the look it is drawn in. A model sets one on a finished part
(``part.material = materials.aluminium_6061``), on faces of a part (``paint(part, faces,
material)``), or on an assembly, whose material every part below it that has none takes when the
document is made. Everything is SI, and ``None`` is unknown: a value the source did not give is
left out, never guessed.

The physical half: ``name`` (what the catalogue looks it up by), ``family`` (one of
``FAMILIES``), ``standard`` (the designation it is sold under: ``UNS A96061``), ``description``,
``source`` (where its numbers came from), ``density`` kg/m^3, ``young_modulus`` Pa,
``poisson_ratio``, ``yield_strength`` Pa, ``ultimate_strength`` Pa, ``thermal_expansion`` 1/K,
``thermal_conductivity`` W/(m K), ``specific_heat`` J/(kg K), and ``isotropic`` (False for a
laminate or a ply, whose numbers hold in the sheet's plane only).

The look is a strict subset of OpenPBR cut to what glTF carries: thirteen parameters, each one
glTF field, so a GLB says all of it and any glTF renderer draws it. The contract:

| OpenPBR | ``Material`` | glTF 2.0 | Blender Principled BSDF |
| --- | --- | --- | --- |
| ``base_color`` | ``color`` RGB | ``baseColorFactor`` RGB | Base Color |
| ``geometry_opacity`` | ``color`` alpha | ``baseColorFactor`` A, ``alphaMode`` BLEND | Alpha |
| ``base_metalness`` | ``metallic`` | ``metallicFactor`` | Metallic |
| ``specular_roughness`` | ``roughness`` | ``roughnessFactor`` | Roughness |
| ``specular_ior`` | ``ior`` | ``KHR_materials_ior`` ``ior`` | IOR |
| ``specular_roughness_anisotropy`` | ``anisotropy`` | ``KHR_materials_anisotropy`` ``anisotropyStrength`` | Anisotropic |
| ``geometry_tangent``'s turn | ``anisotropy_rotation`` | ``KHR_materials_anisotropy`` ``anisotropyRotation`` | Anisotropic Rotation |
| ``transmission_weight`` | ``transmission`` | ``KHR_materials_transmission`` ``transmissionFactor`` | Transmission Weight |
| ``transmission_color`` | ``transmission_color`` | ``KHR_materials_volume`` ``attenuationColor`` | Volume Absorption Color |
| ``transmission_depth`` | ``transmission_depth`` | ``KHR_materials_volume`` ``attenuationDistance`` | Volume Absorption Density |
| ``coat_weight`` | ``coat`` | ``KHR_materials_clearcoat`` ``clearcoatFactor`` | Coat Weight |
| ``coat_roughness`` | ``coat_roughness`` | ``KHR_materials_clearcoat`` ``clearcoatRoughnessFactor`` | Coat Roughness |
| ``emission_color`` | ``emissive`` RGB | ``emissiveFactor`` | Emission Color |
| ``emission_luminance`` | ``emissive_strength`` | ``KHR_materials_emissive_strength`` ``emissiveStrength`` | Emission Strength |

A colour is given as the author sees it, in sRGB: a hex string (``"#e8ebeb"``, or
``"#rrggbbaa"`` with alpha), a tuple of 0-255 integers (three, or four with alpha), or a
build123d ``Color`` (``colors``); ``color`` None draws the part in its own colour. The field holds
it linear, 0-1, as the document and glTF do (``colors.Linear``): ``Material("x",
color="#808080").color`` is ``(0.2158..., 0.2158..., 0.2158..., 1.0)``; ``transmission_color``
and ``emissive`` are colours too, with no alpha. ``anisotropy_rotation`` is radians, as glTF's
(Blender's is turns);
``transmission_depth`` is metres, the distance light goes through the material before it is
``transmission_color`` (Blender's density is its inverse); ``emissive_strength`` multiplies
``emissive`` (default 1), a factor, not OpenPBR's nits. A GLB gives ``KHR_materials_volume`` the
part's thickness, the smallest extent of its box. Everything else is 0-1, ``ior`` 1-3 (default
1.5).

The catalogue is this module itself: ``materials("6061")`` looks a material up (any case, by its
name, its attribute or a common alias; a miss raises ``LookupError`` naming the three nearest),
``materials.aluminium_6061`` is an entry, ``materials.names()`` every name by family and
``materials.by(family="metal")`` the entries a field selects. Its physical values are a snapshot,
taken once, of public data -- FreeCAD's material cards where one exists, a typical datasheet
otherwise -- each entry's ``source`` naming which; the looks are the engine's own. A project's
own materials are ``Material(...)`` constants in its own module: there is nothing to register.

Importing this module imports no kernel.
"""

from __future__ import annotations

import dataclasses
import difflib
import math
import re
import sys
import types
from dataclasses import KW_ONLY, dataclass
from typing import Any

from cadgen.engine.colors import linear

__all__ = ["CATALOGUE", "FAMILIES", "Material", "by", "names"]

FAMILIES = ("metal", "plastic", "elastomer", "composite", "wood", "glass", "other")


def _number(field: str, value: Any, what: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Material {field} must be {what}, not {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Material {field} must be {what}, not {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"Material {field} must be {what}, not {value!r}")
    return number


def _unit(field: str, value: Any) -> float:
    number = _number(field, value, "a number in 0-1")
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"Material {field} must be in 0-1, not {value!r}")
    return number


def _positive(field: str, value: Any, unit: str) -> float | None:
    if value is None:
        return None
    number = _number(field, value, f"a positive number of {unit}")
    if number <= 0:
        raise ValueError(f"Material {field} must be positive ({unit}), not {value!r}")
    return number


@dataclass(frozen=True)
class Material:
    """A physical material and its look (the module docstring names every field). ``name`` is
    required and ``density`` may be given second; every other field by name. A field out of
    range raises ``ValueError`` naming it."""

    name: str
    density: float | None = None
    _: KW_ONLY
    family: str | None = None
    standard: str | None = None
    description: str | None = None
    source: str | None = None
    young_modulus: float | None = None
    poisson_ratio: float | None = None
    yield_strength: float | None = None
    ultimate_strength: float | None = None
    thermal_expansion: float | None = None
    thermal_conductivity: float | None = None
    specific_heat: float | None = None
    isotropic: bool = True
    color: Any = None
    metallic: float = 0.0
    roughness: float = 0.5
    ior: float = 1.5
    anisotropy: float = 0.0
    anisotropy_rotation: float = 0.0
    transmission: float = 0.0
    transmission_color: Any = None
    transmission_depth: float | None = None
    coat: float = 0.0
    coat_roughness: float = 0.0
    emissive: Any = None
    emissive_strength: float = 1.0

    def __post_init__(self) -> None:
        def put(field: str, value: Any) -> None:
            object.__setattr__(self, field, value)  # frozen: validation normalises in place

        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"Material name must be a non-empty string, not {self.name!r}")
        if self.family is not None and self.family not in FAMILIES:
            raise ValueError(f"Material family must be one of {', '.join(FAMILIES)}, not {self.family!r}")
        for field in ("standard", "description", "source"):
            if getattr(self, field) is not None and not isinstance(getattr(self, field), str):
                raise ValueError(f"Material {field} must be a string, not {getattr(self, field)!r}")
        for field, unit in (("density", "kg/m^3"), ("young_modulus", "Pa"), ("yield_strength", "Pa"),
                            ("ultimate_strength", "Pa"), ("thermal_conductivity", "W/(m K)"),
                            ("specific_heat", "J/(kg K)"), ("transmission_depth", "m")):
            put(field, _positive(field, getattr(self, field), unit))
        if self.poisson_ratio is not None:
            ratio = _number("poisson_ratio", self.poisson_ratio, "a number in -1-0.5")
            if not -1.0 < ratio <= 0.5:
                raise ValueError(f"Material poisson_ratio must be in -1-0.5, not {self.poisson_ratio!r}")
            put("poisson_ratio", ratio)
        if self.thermal_expansion is not None:
            put("thermal_expansion", _number("thermal_expansion", self.thermal_expansion, "a number of 1/K"))
        if not isinstance(self.isotropic, bool):
            raise ValueError(f"Material isotropic must be True or False, not {self.isotropic!r}")
        if self.color is not None:
            put("color", linear(self.color, "Material color"))
        for field in ("metallic", "roughness", "anisotropy", "transmission", "coat", "coat_roughness"):
            put(field, _unit(field, getattr(self, field)))
        ior = _number("ior", self.ior, "a number in 1-3")
        if not 1.0 <= ior <= 3.0:
            raise ValueError(f"Material ior must be in 1-3, not {self.ior!r}")
        put("ior", ior)
        put("anisotropy_rotation", _number("anisotropy_rotation", self.anisotropy_rotation, "an angle in radians"))
        for field in ("transmission_color", "emissive"):
            if getattr(self, field) is not None:
                put(field, linear(getattr(self, field), f"Material {field}", alpha=False))
        strength = _number("emissive_strength", self.emissive_strength, "a number at least 0")
        if strength < 0:
            raise ValueError(f"Material emissive_strength must be at least 0, not {self.emissive_strength!r}")
        put("emissive_strength", strength)

    def but(self, **changes: Any) -> "Material":
        """A copy with ``changes``: ``materials.steel_1018.but(roughness=0.2, description="polished")``."""
        return dataclasses.replace(self, **changes)

    def mass(self, volume_m3: float) -> float | None:
        """The mass in kg of ``volume_m3`` cubic metres of it; None where its density is unknown."""
        return None if self.density is None else self.density * float(volume_m3)

    # A material is a value: a copy of a shape (build123d's deepcopy) shares it.
    def __copy__(self) -> "Material":
        return self

    def __deepcopy__(self, memo: Any) -> "Material":
        return self


# --- the table ---------------------------------------------------------------------------------
# One entry per line, by family. The physical values are a snapshot of the source each names,
# taken once and kept as ours: FreeCAD's material card of that name (its Resources/Materials/
# Standard), or a typical published datasheet for the grade and temper named. FreeCAD's
# X5CrNi18-10 and X5CrNiMo17-12-2 cards give carbon steel's expansion and no thermal values, so
# 304 and 316 are the datasheet's. The looks are the engine's own: metals metallic, roughness by
# finish (polished 0.2, machined 0.35-0.45, cast 0.6), brushed aluminium and stainless
# anisotropic; plastics dielectric; glass and the clear plastics transmissive; rubber rough.

def _fc(card: str) -> str:
    return f"FreeCAD material card {card}"


def _ds(what: str) -> str:
    return f"typical datasheet: {what}"


_MACHINED_AL = dict(color="#f5f6f6", metallic=1.0, roughness=0.35, anisotropy=0.3)
_SHEET_AL = dict(color="#f5f6f6", metallic=1.0, roughness=0.4, anisotropy=0.3)
_STEEL = dict(color="#c5c7c8", metallic=1.0, roughness=0.4)
_MILL_SCALE = dict(color="#848486", metallic=1.0, roughness=0.6)
_BRUSHED_SS = dict(color="#d6d4d1", metallic=1.0, roughness=0.3, anisotropy=0.3)

# fmt: off
# metals
aluminium_6061 = Material("Aluminum 6061-T6", 2700, family="metal", standard="UNS A96061", source=_fc("Aluminum-6061-T6"), young_modulus=68.9e9, poisson_ratio=0.33, yield_strength=276e6, ultimate_strength=310e6, thermal_expansion=23.6e-6, thermal_conductivity=167, specific_heat=896, description="Precipitation-hardened structural aluminium: the usual machined and plate alloy", **_MACHINED_AL)  # noqa: E501
aluminium_5052 = Material("Aluminum 5052-H32", 2680, family="metal", standard="UNS A95052", source=_ds("5052-H32 sheet"), young_modulus=70.3e9, poisson_ratio=0.33, yield_strength=193e6, ultimate_strength=228e6, thermal_expansion=23.8e-6, thermal_conductivity=138, specific_heat=880, description="Strain-hardened sheet aluminium that bends well", **_SHEET_AL)  # noqa: E501
aluminium_6063 = Material("Aluminum 6063-T5", 2700, family="metal", standard="UNS A96063", source=_ds("6063-T5 extrusion"), young_modulus=68.9e9, poisson_ratio=0.33, yield_strength=145e6, ultimate_strength=186e6, thermal_expansion=23.4e-6, thermal_conductivity=209, specific_heat=900, description="Extrusion aluminium: profiles, rails and heat sinks", **_SHEET_AL)  # noqa: E501
aluminium_7075 = Material("Aluminum 7075-T6", 2810, family="metal", standard="UNS A97075", source=_fc("Aluminum-7075-T6"), young_modulus=71.7e9, poisson_ratio=0.33, yield_strength=503e6, ultimate_strength=572e6, thermal_expansion=23.6e-6, thermal_conductivity=130, specific_heat=960, description="High-strength zinc-alloyed aluminium for stressed parts", **_MACHINED_AL)  # noqa: E501
steel_1018 = Material("Steel 1018", 7870, family="metal", standard="UNS G10180", source=_ds("AISI 1018 cold drawn"), young_modulus=205e9, poisson_ratio=0.29, yield_strength=370e6, ultimate_strength=440e6, thermal_expansion=11.5e-6, thermal_conductivity=51.9, specific_heat=486, description="Low-carbon mild steel, cold drawn bar", **_STEEL)  # noqa: E501
steel_a36 = Material("Steel A36", 7850, family="metal", standard="ASTM A36", source=_ds("ASTM A36 hot rolled"), young_modulus=200e9, poisson_ratio=0.26, yield_strength=250e6, ultimate_strength=400e6, thermal_expansion=11.7e-6, thermal_conductivity=50, specific_heat=486, description="Hot-rolled structural steel plate and section, mill scale on", **_MILL_SCALE)  # noqa: E501
steel_s235 = Material("Steel S235JR", 7800, family="metal", standard="EN 10025 1.0037", source=_fc("Steel-S235JR"), young_modulus=210e9, poisson_ratio=0.3, yield_strength=235e6, ultimate_strength=360e6, thermal_expansion=11e-6, description="European hot-rolled structural steel, mill scale on", **_MILL_SCALE)  # noqa: E501
steel_4140 = Material("Steel 4140", 7850, family="metal", standard="UNS G41400", source=_ds("AISI 4140 annealed"), young_modulus=205e9, poisson_ratio=0.29, yield_strength=415e6, ultimate_strength=655e6, thermal_expansion=12.2e-6, thermal_conductivity=42.6, specific_heat=473, description="Chromium-molybdenum alloy steel for shafts and gears", color="#bcbdbf", metallic=1.0, roughness=0.4)  # noqa: E501
steel_spring_1095 = Material("Spring steel 1095", 7850, family="metal", standard="UNS G10950", source=_ds("AISI 1095 annealed"), young_modulus=205e9, poisson_ratio=0.29, yield_strength=525e6, ultimate_strength=685e6, thermal_expansion=11e-6, thermal_conductivity=49.8, specific_heat=461, description="High-carbon steel for springs and blades, blued; strengths as annealed, before hardening", color="#7c8190", metallic=1.0, roughness=0.35)  # noqa: E501
stainless_304 = Material("Stainless 304", 8000, family="metal", standard="UNS S30400", source=_ds("AISI 304 annealed"), young_modulus=193e9, poisson_ratio=0.29, yield_strength=215e6, ultimate_strength=505e6, thermal_expansion=17.3e-6, thermal_conductivity=16.2, specific_heat=500, description="Austenitic 18-8 stainless steel, brushed", **_BRUSHED_SS)  # noqa: E501
stainless_316 = Material("Stainless 316", 8000, family="metal", standard="UNS S31600", source=_ds("AISI 316 annealed"), young_modulus=193e9, poisson_ratio=0.3, yield_strength=205e6, ultimate_strength=515e6, thermal_expansion=15.9e-6, thermal_conductivity=16.3, specific_heat=500, description="Molybdenum austenitic stainless for corrosive and marine service, brushed", **_BRUSHED_SS)  # noqa: E501
stainless_17_4ph = Material("Stainless 17-4 PH", 7800, family="metal", standard="UNS S17400", source=_ds("17-4 PH condition H900"), young_modulus=196e9, poisson_ratio=0.27, yield_strength=1170e6, ultimate_strength=1310e6, thermal_expansion=10.8e-6, thermal_conductivity=17.9, specific_heat=460, description="Precipitation-hardening martensitic stainless, hardened", color="#cecdcb", metallic=1.0, roughness=0.4)  # noqa: E501
brass_c360 = Material("Brass C360", 8500, family="metal", standard="UNS C36000", source=_ds("C360 half hard"), young_modulus=97e9, poisson_ratio=0.31, yield_strength=310e6, ultimate_strength=385e6, thermal_expansion=20.5e-6, thermal_conductivity=115, specific_heat=380, description="Free-machining leaded brass", color="#f2e6b0", metallic=1.0, roughness=0.35)  # noqa: E501
brass_c260 = Material("Brass C260", 8530, family="metal", standard="UNS C26000", source=_ds("C260 half hard"), young_modulus=110e9, poisson_ratio=0.375, yield_strength=360e6, ultimate_strength=420e6, thermal_expansion=20e-6, thermal_conductivity=120, specific_heat=375, description="Cartridge brass: sheet, drawn and polished parts", color="#f3e5b3", metallic=1.0, roughness=0.2)  # noqa: E501
copper_c110 = Material("Copper C110", 8890, family="metal", standard="UNS C11000", source=_ds("C110 annealed"), young_modulus=115e9, poisson_ratio=0.31, yield_strength=69e6, ultimate_strength=220e6, thermal_expansion=17e-6, thermal_conductivity=388, specific_heat=385, description="Electrolytic tough-pitch copper", color="#fad1c2", metallic=1.0, roughness=0.35)  # noqa: E501
titanium_grade5 = Material("Titanium Ti-6Al-4V", 4430, family="metal", standard="Grade 5, UNS R56400", source=_fc("Ti-6Al-4V"), young_modulus=114e9, poisson_ratio=0.33, yield_strength=910e6, ultimate_strength=975.5e6, thermal_expansion=8.6e-6, thermal_conductivity=6.7, specific_heat=553, description="Alpha-beta titanium alloy", color="#c2bbb3", metallic=1.0, roughness=0.4)  # noqa: E501
zinc_za8 = Material("Zinc ZA-8", 6300, family="metal", standard="UNS Z25630", source=_ds("ZA-8 die cast"), young_modulus=85.5e9, yield_strength=290e6, ultimate_strength=374e6, thermal_expansion=23.3e-6, thermal_conductivity=115, specific_heat=435, description="Zinc-aluminium die-casting alloy, as cast", color="#d4d7da", metallic=1.0, roughness=0.6)  # noqa: E501
neodymium = Material("Neodymium magnet N42", 7500, family="metal", standard="NdFeB N42", source=_ds("sintered NdFeB, nickel plated"), description="Sintered rare-earth magnet, nickel plated; brittle, no structural values", color="#d4cdc0", metallic=1.0, roughness=0.2)  # noqa: E501

# printing plastics
pla = Material("PLA", 1240, family="plastic", standard="PLA", source=_fc("PLA-Generic"), young_modulus=3.64e9, poisson_ratio=0.36, yield_strength=35.9e6, ultimate_strength=26.4e6, thermal_expansion=41e-6, thermal_conductivity=0.13, specific_heat=1800, description="Polylactic acid, the common FDM filament", color="#ededeb", roughness=0.45)  # noqa: E501
petg = Material("PETG", 1270, family="plastic", standard="PETG", source=_ds("PETG filament"), young_modulus=2.0e9, yield_strength=50e6, thermal_expansion=68e-6, thermal_conductivity=0.2, description="Glycol-modified PET filament: tough and glossy", color="#e7eaed", roughness=0.3)  # noqa: E501
abs = Material("ABS", 1060, family="plastic", standard="ABS", source=_fc("ABS-Generic"), young_modulus=2.3e9, poisson_ratio=0.37, yield_strength=44.1e6, ultimate_strength=38.8e6, thermal_expansion=93e-6, thermal_conductivity=0.158, specific_heat=2050, description="Acrylonitrile butadiene styrene, moulded or printed", color="#767679", roughness=0.55)  # noqa: A001, E501
asa = Material("ASA", 1070, family="plastic", standard="ASA", source=_ds("ASA moulding grade"), young_modulus=2.3e9, yield_strength=45e6, thermal_expansion=95e-6, thermal_conductivity=0.17, description="UV-stable relative of ABS for outdoor parts", color="#e1e1de", roughness=0.6)  # noqa: E501
nylon_pa12 = Material("Nylon PA12", 930, family="plastic", standard="PA12", source=_ds("PA12 laser sintered"), young_modulus=1.7e9, ultimate_strength=48e6, description="Polyamide 12, the powder-bed printing nylon; a sintered part's density", color="#e1dfda", roughness=0.85)  # noqa: E501
nylon_pa6_cf = Material("Nylon PA6-CF", 1170, family="plastic", standard="PA6-CF", source=_ds("PA6-CF filament, dry, in the print plane"), young_modulus=7.45e9, ultimate_strength=105e6, description="Chopped carbon fibre in polyamide 6 filament", color="#303035", roughness=0.7)  # noqa: E501
tpu_95a = Material("TPU 95A", 1220, family="elastomer", standard="TPU Shore 95A", source=_ds("TPU 95A filament"), young_modulus=26e6, ultimate_strength=39e6, description="Thermoplastic polyurethane for flexible prints", color="#3f3f3f", roughness=0.6)  # noqa: E501
polycarbonate = Material("Polycarbonate", 1200, family="plastic", standard="PC", source=_fc("PC-Molded"), young_modulus=2.2e9, poisson_ratio=0.37, yield_strength=80e6, ultimate_strength=60e6, thermal_expansion=68e-6, thermal_conductivity=0.2, specific_heat=1250, description="Tough clear thermoplastic", color="#f9fafc", roughness=0.08, ior=1.586, transmission=0.9)  # noqa: E501
resin_standard = Material("SLA resin, standard", 1180, family="plastic", standard="photopolymer", source=_ds("clear SLA resin, post-cured"), young_modulus=2.8e9, ultimate_strength=65e6, description="Clear photopolymer for stereolithography", color="#faf8f1", roughness=0.15, ior=1.5, transmission=0.8)  # noqa: E501

# engineering plastics
acetal_pom = Material("Acetal (POM)", 1410, family="plastic", standard="POM-C", source=_fc("POM-Copolymer-Generic"), young_modulus=2.66e9, poisson_ratio=0.363, yield_strength=59.8e6, ultimate_strength=56.5e6, thermal_expansion=109e-6, thermal_conductivity=0.304, specific_heat=1460, description="Polyoxymethylene copolymer: low friction, stable, machinable", color="#f3f3f1", roughness=0.4)  # noqa: E501
acrylic_pmma = Material("Acrylic (PMMA)", 1160, family="plastic", standard="PMMA", source=_fc("Acrylic-Glass-Generic"), young_modulus=2.55e9, poisson_ratio=0.38, yield_strength=73.7e6, ultimate_strength=57.7e6, thermal_expansion=75e-6, thermal_conductivity=0.193, specific_heat=1480, description="Clear cast or extruded acrylic sheet", color="#ffffff", roughness=0.03, ior=1.49, transmission=0.95)  # noqa: E501
ptfe = Material("PTFE", 2070, family="plastic", standard="PTFE", source=_fc("PTFE-Generic"), young_modulus=564e6, poisson_ratio=0.46, yield_strength=20.5e6, ultimate_strength=34.6e6, thermal_expansion=108e-6, thermal_conductivity=0.263, specific_heat=1010, description="Polytetrafluoroethylene: slippery, chemically inert", color="#f6f6f3", roughness=0.5)  # noqa: E501
peek = Material("PEEK", 1340, family="plastic", standard="PEEK", source=_fc("PEEK-Generic"), young_modulus=3.88e9, yield_strength=97.1e6, ultimate_strength=98.9e6, thermal_expansion=52.9e-6, thermal_conductivity=0.299, specific_heat=1410, description="Polyether ether ketone: a high-temperature engineering plastic", color="#cebca0", roughness=0.4)  # noqa: E501
hdpe = Material("HDPE", 950, family="plastic", standard="PE-HD", source=_ds("HDPE sheet"), young_modulus=1.1e9, yield_strength=26e6, thermal_expansion=120e-6, thermal_conductivity=0.48, specific_heat=1900, description="High-density polyethylene", color="#ededeb", roughness=0.5)  # noqa: E501
uhmw_pe = Material("UHMW-PE", 930, family="plastic", standard="PE-UHMW", source=_ds("UHMW-PE sheet"), young_modulus=0.69e9, yield_strength=21e6, ultimate_strength=40e6, thermal_expansion=200e-6, thermal_conductivity=0.41, description="Ultra-high-molecular-weight polyethylene: wear strips and guides", color="#f6f6f3", roughness=0.5)  # noqa: E501
nylon_pa6 = Material("Nylon PA6", 1150, family="plastic", standard="PA6", source=_fc("PA6-Generic"), young_modulus=2.93e9, poisson_ratio=0.39, yield_strength=70.5e6, ultimate_strength=75.5e6, thermal_expansion=82e-6, thermal_conductivity=0.262, specific_heat=1670, description="Polyamide 6, moulded or machined", color="#efece5", roughness=0.6)  # noqa: E501
polypropylene = Material("Polypropylene", 916, family="plastic", standard="PP", source=_fc("PP-Generic"), young_modulus=1.47e9, poisson_ratio=0.44, yield_strength=32.8e6, ultimate_strength=79.7e6, thermal_expansion=123e-6, thermal_conductivity=0.249, specific_heat=1920, description="Polypropylene: living hinges and chemical-resistant parts", color="#efefec", roughness=0.45)  # noqa: E501

# sheet, composites, wood
fr4 = Material("FR4", 1850, family="composite", standard="NEMA FR-4", source=_ds("FR-4 laminate, in plane"), young_modulus=24e9, ultimate_strength=310e6, thermal_expansion=14e-6, thermal_conductivity=0.3, description="Woven glass and epoxy circuit-board laminate under green solder mask", color="#1f5e3a", roughness=0.45, coat=0.5, coat_roughness=0.2)  # noqa: E501
carbon_fibre_laminate = Material("Carbon fibre laminate", 1550, family="composite", standard="CFRP 0/90 woven", source=_ds("woven carbon/epoxy plate, in plane"), young_modulus=70e9, poisson_ratio=0.1, ultimate_strength=600e6, thermal_expansion=2e-6, isotropic=False, description="Woven carbon fibre in epoxy, clear-coated; values in the plate's plane", color="#272729", roughness=0.35, anisotropy=0.6, coat=1.0, coat_roughness=0.05)  # noqa: E501
plywood_birch = Material("Birch plywood", 680, family="wood", standard="EN 636", source=_ds("birch plywood; thermal values EN 13986's"), thermal_conductivity=0.17, specific_heat=1600, isotropic=False, description="Cross-laminated birch veneers", color="#e2c8a0", roughness=0.7)  # noqa: E501
mdf = Material("MDF", 750, family="wood", standard="EN 622-5", source=_ds("MDF board; thermal values EN 13986's"), young_modulus=3.0e9, thermal_conductivity=0.14, specific_heat=1700, description="Medium-density fibreboard", color="#b4966e", roughness=0.8)  # noqa: E501
hardboard = Material("Hardboard", 950, family="wood", standard="EN 622-2", source=_ds("hardboard; thermal values EN 13986's"), thermal_conductivity=0.2, specific_heat=1700, description="High-density wet-process fibreboard", color="#6e5037", roughness=0.6)  # noqa: E501

# elastomers, other
silicone_50a = Material("Silicone 50A", 1150, family="elastomer", standard="VMQ Shore 50A", source=_ds("silicone rubber, 50 Shore A"), young_modulus=2.3e6, poisson_ratio=0.49, ultimate_strength=7e6, thermal_conductivity=0.2, description="Silicone rubber: seals, pads and moulded soft parts", color="#ededea", roughness=0.6)  # noqa: E501
nbr_70a = Material("NBR 70A", 1250, family="elastomer", standard="NBR Shore 70A", source=_ds("nitrile O-ring compound, 70 Shore A"), young_modulus=5.5e6, poisson_ratio=0.49, ultimate_strength=15e6, description="Nitrile rubber: O-rings and oil seals", color="#272727", roughness=0.9)  # noqa: E501
epdm_foam = Material("EPDM foam", 120, family="elastomer", standard="EPDM closed cell", source=_ds("closed-cell EPDM sponge"), thermal_conductivity=0.04, description="Closed-cell EPDM sponge: gaskets and weather seals", color="#303030", roughness=0.95)  # noqa: E501
glass_soda_lime = Material("Glass, soda-lime", 2520, family="glass", standard="soda-lime float", source=_fc("Glass-Generic"), young_modulus=72e9, poisson_ratio=0.22, thermal_expansion=9e-6, description="Window and float glass", color="#ffffff", roughness=0.02, ior=1.52, transmission=1.0, transmission_color="#eaf7f0", transmission_depth=0.05)  # noqa: E501
# fmt: on

# Every entry by its attribute name, in the order above.
CATALOGUE: dict[str, Material] = {name: value for name, value in dict(globals()).items()
                                  if isinstance(value, Material) and not name.startswith("_")}

# Short attributes for the common choice, the catalogue's earlier names among them.
aluminium = aluminium_6061
steel = steel_1018
stainless_steel = stainless_304
brass = brass_c360
copper = copper_c110
titanium = titanium_grade5
nylon = nylon_pa12
acrylic = acrylic_pmma
glass = glass_soda_lime
abs_plastic = abs
acetal = acetal_pom
_SHORT = ("aluminium", "steel", "stainless_steel", "brass", "copper", "titanium", "nylon", "acrylic", "glass",
          "abs_plastic", "acetal")

# What else a material is called: designations, numbers and trade names.
_ALIASES: dict[Material, tuple[str, ...]] = {
    aluminium_6061: ("6061", "6061-t6", "al 6061", "al6061", "aluminum 6061", "aluminium 6061", "aluminum", "al"),
    aluminium_5052: ("5052", "5052-h32", "al 5052", "aluminum 5052", "aluminium 5052"),
    aluminium_6063: ("6063", "6063-t5", "al 6063", "aluminum 6063", "aluminium 6063"),
    aluminium_7075: ("7075", "7075-t6", "al 7075", "aluminum 7075", "aluminium 7075"),
    steel_1018: ("1018", "mild steel", "low carbon steel"),
    steel_a36: ("a36", "astm a36", "structural steel"),
    steel_s235: ("s235", "s235jr", "1.0037"),
    steel_4140: ("4140", "42crmo4", "chromoly"),
    steel_spring_1095: ("1095", "spring steel"),
    stainless_304: ("304", "ss304", "1.4301", "18-8", "stainless", "stainless steel"),
    stainless_316: ("316", "ss316", "1.4401"),
    stainless_17_4ph: ("17-4", "17-4ph", "630"),
    brass_c360: ("c360", "360 brass", "free-cutting brass"),
    brass_c260: ("c260", "260 brass", "cartridge brass"),
    copper_c110: ("c110", "etp copper"),
    titanium_grade5: ("ti-6al-4v", "ti64", "grade 5", "titanium grade 5"),
    zinc_za8: ("za-8", "za8", "zinc"),
    neodymium: ("n42", "ndfeb", "magnet"),
    nylon_pa12: ("pa12", "nylon 12"),
    nylon_pa6_cf: ("pa6-cf", "pa6 cf", "nylon cf"),
    tpu_95a: ("tpu", "95a"),
    polycarbonate: ("pc",),
    resin_standard: ("resin", "sla resin"),
    acetal_pom: ("pom", "delrin"),
    acrylic_pmma: ("pmma", "plexiglass", "perspex"),
    ptfe: ("teflon",),
    uhmw_pe: ("uhmw", "uhmwpe"),
    nylon_pa6: ("pa6", "nylon 6"),
    polypropylene: ("pp",),
    fr4: ("fr-4", "pcb"),
    carbon_fibre_laminate: ("cfrp", "carbon fibre", "carbon fiber", "carbon fiber laminate"),
    plywood_birch: ("plywood", "birch ply"),
    silicone_50a: ("silicone",),
    nbr_70a: ("nbr", "nitrile", "buna-n"),
    epdm_foam: ("epdm",),
    glass_soda_lime: ("soda-lime glass", "soda lime glass"),
}


def _key(text: str) -> str:
    return re.sub(r"[\s_]+", " ", str(text).strip().lower())


_LOOKUP: dict[str, Material] = {}
for _name, _entry in [*CATALOGUE.items(), *((name, globals()[name]) for name in _SHORT)]:
    _LOOKUP.setdefault(_key(_entry.name), _entry)
    _LOOKUP.setdefault(_key(_name), _entry)
for _entry, _spellings in _ALIASES.items():
    for _name in _spellings:
        _LOOKUP.setdefault(_key(_name), _entry)
del _name, _entry, _spellings


def _lookup(name: str) -> Material:
    found = _LOOKUP.get(_key(name))
    if found is not None:
        return found
    near: list[str] = []
    for spelling in difflib.get_close_matches(_key(name), list(_LOOKUP), n=len(_LOOKUP), cutoff=0.0):
        if _LOOKUP[spelling].name not in near:
            near.append(_LOOKUP[spelling].name)
        if len(near) == 3:
            break
    raise LookupError(f"no material {name!r} in the catalogue; the nearest: {', '.join(near)}")


def names() -> dict[str, list[str]]:
    """Every entry's name by family, in the table's order."""
    found: dict[str, list[str]] = {}
    for entry in CATALOGUE.values():
        found.setdefault(entry.family or "other", []).append(entry.name)
    return found


def by(**fields: Any) -> list[Material]:
    """The entries whose fields equal ``fields``: ``materials.by(family="metal")``."""
    unknown = set(fields) - {field.name for field in dataclasses.fields(Material)}
    if unknown:
        raise TypeError(f"a Material has no field {', '.join(sorted(unknown))}")
    return [entry for entry in CATALOGUE.values() if all(getattr(entry, k) == v for k, v in fields.items())]


class _Catalogue(types.ModuleType):
    """This module, called: ``materials(name)`` is the catalogue's material of ``name``, by its
    name, its attribute or an alias, in any case; a miss raises ``LookupError`` naming the three
    nearest."""

    def __call__(self, name: str) -> Material:
        return _lookup(name)


sys.modules[__name__].__class__ = _Catalogue

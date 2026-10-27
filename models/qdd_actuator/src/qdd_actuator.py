"""Compact quasi-direct-drive (QDD) actuator concept for a humanoid robot joint.

Functional concept layout, manufacturable industrial design:
- high-torque-density outrunner BLDC motor (24-slot stator, 28-magnet rotor)
- low-ratio single-stage planetary reduction (sun 24T / planets 30T / ring 84T,
  module 1.0, fixed ring -> 4.5:1)
- integrated rear magnetic encoder (rotor magnet ring + encoder PCB)
- output torque sensing (4-spoke strain-gauge flexure between carrier and flange)
- cross-roller output bearing (alternating +/-45 deg rollers in V-groove races)
- hollow shaft cable routing (Ø14/Ø11 static tube through the full stack)
- compact annular motor-driver PCB (FETs, bus capacitors, MCU)
- aluminum housing with axial heat fins, bolted front retainer ring
- sealed rear circular connectors (power + signal, o-ring glands)

Coordinate convention:
- Units mm. Origin on the actuator centerline (Z = rotation axis).
- +Z is the output direction; the gear stage and output flange are at +Z,
  the driver electronics and sealed connectors are at -Z.

The same parameterized builder produces the assembled model (explode=0) and an
exploded technical layout (explode=1) used by qdd_actuator_exploded.py. The
exploded translations are documented per-part static Locations along +/-Z.

The assembled model carries the mechanism: every mount a rigid fastening, every
turning member a revolute joint geared by the `drive` coupling, its two
configurations, and the old `drive` clip as a motion. The old `inspect` and
`teardown` clips, which run the drive while the stack opens to its stations, are
GLB animations (`cadgen.gltf`).
"""

from __future__ import annotations

from bd_materials import FinishedMaterial, metals, plastics
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties


from cadgen import model
from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state
from cadgen.gltf import animation

import math

import build123d as bd

# ---------------------------------------------------------------------------
# Gear stage parameters (module-1.0 concept teeth, trapezoidal with backlash)
# ---------------------------------------------------------------------------
GEAR_MODULE = 1.0
SUN_TEETH = 24
PLANET_TEETH = 30
RING_TEETH = 84  # = SUN_TEETH + 2 * PLANET_TEETH
PLANET_COUNT = 3
REDUCTION_RATIO = 1.0 + RING_TEETH / SUN_TEETH  # 4.5:1, fixed ring gear

SUN_PITCH_R = GEAR_MODULE * SUN_TEETH / 2  # 12.0
PLANET_PITCH_R = GEAR_MODULE * PLANET_TEETH / 2  # 15.0
RING_PITCH_R = GEAR_MODULE * RING_TEETH / 2  # 42.0
PLANET_CENTER_R = SUN_PITCH_R + PLANET_PITCH_R  # 27.0
PLANET_ANGLES_DEG = (90.0, 210.0, 330.0)

ADDENDUM = 1.0 * GEAR_MODULE
DEDENDUM = 1.25 * GEAR_MODULE
GEAR_WIDTH = 12.0
GEAR_Z = (8.5, 20.5)

SUN_ROOT_R = SUN_PITCH_R - DEDENDUM  # 10.75
SUN_TIP_R = SUN_PITCH_R + ADDENDUM  # 13.0
PLANET_ROOT_R = PLANET_PITCH_R - DEDENDUM  # 13.75
PLANET_TIP_R = PLANET_PITCH_R + ADDENDUM  # 16.0
RING_TIP_R = RING_PITCH_R - ADDENDUM  # 41.0 (internal teeth point inward)
RING_ROOT_R = RING_PITCH_R + DEDENDUM  # 43.25
RING_RIM_R = 46.0
PLANET_BORE_R = 4.0

# ---------------------------------------------------------------------------
# Hollow shaft cable routing
# ---------------------------------------------------------------------------
TUBE_OUTER_R = 7.0  # Ø14 conduit
TUBE_INNER_R = 5.5  # Ø11 cable bore
# The static tube protrudes past the rear cover and the output flange so the
# hollow-shaft cable path visibly enters and exits the actuator.
TUBE_Z = (-36.5, 35.5)

# ---------------------------------------------------------------------------
# Outrunner BLDC motor
# ---------------------------------------------------------------------------
STATOR_SLOTS = 24
STATOR_YOKE_IR = 28.0  # seats on the housing center sleeve
STATOR_YOKE_OR = 33.0
STATOR_TOOTH_TIP_R = 40.0
STATOR_TOOTH_W = 5.0  # tangential tooth width
STATOR_SHOE_W = 7.6  # tangential pole-shoe width
STATOR_SHOE_IR = 38.8
STATOR_STACK_Z = (-13.0, 1.0)

WINDING_RADIAL = (33.4, 38.6)  # clears yoke OD and pole shoes
WINDING_TANGENTIAL = 8.0
WINDING_AXIAL = 17.0  # end turns overhang the stack
WINDING_HOLE_TANGENTIAL = 5.1
WINDING_HOLE_AXIAL = 14.1

MAGNET_COUNT = 28
MAGNET_IR = 40.75  # 0.75 mm airgap over the stator tooth tips
MAGNET_OR = 43.75
MAGNET_W = 8.0
MAGNET_Z = (-13.0, 1.0)
BACK_IRON_R = (43.75, 45.5)
BACK_IRON_Z = (-13.5, 2.5)

ROTOR_HUB_R = (7.5, 11.0)  # hollow hub over the cable tube
ROTOR_HUB_Z = (-20.0, 5.5)
ROTOR_WEB_Z = (2.5, 5.5)  # front web (output-side bell)
ROTOR_FLANGE_R = (7.5, 17.0)  # sun-gear coupling flange
ROTOR_FLANGE_Z = (5.5, 6.8)
COUPLING_HOLE_R = 11.25  # 4x M3 rotor/sun coupling circle
AIRGAP = MAGNET_IR - STATOR_TOOTH_TIP_R

# Rotor support ball bearings (inner race on hub, outer race in sleeve bore)
ROTOR_BRG_IR = (11.0, 12.4)
ROTOR_BRG_OR = (13.6, 15.0)
ROTOR_BRG_BALL_R = 1.25
ROTOR_BRG_BALL_COUNT = 10
ROTOR_BRG_REAR_Z = (-17.0, -12.0)
ROTOR_BRG_FRONT_Z = (-3.5, 1.5)

# ---------------------------------------------------------------------------
# Housing (aluminum, axial heat fins) and front retainer
# ---------------------------------------------------------------------------
BARREL_R = (46.0, 50.0)
BARREL_Z = (-31.0, 29.0)
# Dense thin-fin array over the motor/electronics zone; deliberately many,
# thin, and shallow so the array reads as heat-sink fins, not gear teeth.
# Fins stop short of BOTH end faces so each rim keeps a machined solid band.
FIN_COUNT = 64
FIN_RADIAL = (49.5, 52.5)
FIN_W = 1.4
FIN_Z = (-26.5, 12.0)
REAR_WALL_R = (13.0, 46.0)
REAR_WALL_Z = (-22.0, -18.0)
SLEEVE_R = (15.0, 28.0)
SLEEVE_Z = (-18.0, 1.5)
RETAINER_R = (41.5, 50.0)
RETAINER_Z = (29.0, 31.0)
FRONT_SCREW_CIRCLE_R = 48.0  # 8x M3 retainer screws into the barrel face
FRONT_SCREW_COUNT = 8
RETAINER_SCREW_HEAD_R = 2.75  # visible M3 socket-head fasteners in the ring
RETAINER_SCREW_HEAD_H = 2.2
RETAINER_SCREW_SOCKET_R = 1.45
REAR_SCREW_CIRCLE_R = 48.0  # 8x M3 rear cover screws
REAR_SCREW_COUNT = 8
PHASE_WIRE_HOLE_R = 2.5  # 3x stator phase-wire passages through the rear wall
PHASE_WIRE_CIRCLE_R = 34.0
PHASE_WIRE_ANGLES = (15.0, 135.0, 255.0)

ENC_STANDOFF_R = 2.5
ENC_STANDOFF_CIRCLE_R = 17.5
ENC_STANDOFF_Z = (-24.4, -22.0)
ENC_STANDOFF_ANGLES = (90.0, 210.0, 330.0)
DRV_STANDOFF_R = 3.0
DRV_STANDOFF_CIRCLE_R = 40.0
DRV_STANDOFF_Z = (-28.8, -22.0)
DRV_STANDOFF_ANGLES = (30.0, 150.0, 270.0)

# ---------------------------------------------------------------------------
# Rear cover and sealed connectors
# ---------------------------------------------------------------------------
COVER_PLATE_Z = (-34.0, -31.0)
COVER_R = 50.0
COVER_LIP_R = (43.8, 45.8)
COVER_LIP_Z = (-31.0, -29.5)
COVER_BOSS_R = (7.05, 8.5)
COVER_BOSS_Z = (-31.0, -29.0)
CONNECTOR_CIRCLE_R = 28.0
CONNECTOR_ANGLES = {"power": 135.0, "signal": 225.0}
CONNECTOR_SCALE = {"power": 1.0, "signal": 0.82}
ORING_MAJOR_R = 8.2  # scaled per connector
ORING_MINOR_R = 0.6
ORING_GLAND_MINOR_R = 0.7

# ---------------------------------------------------------------------------
# Electronics
# ---------------------------------------------------------------------------
DRIVER_BOARD_R = (9.0, 43.0)
DRIVER_BOARD_Z = (-30.4, -28.8)
FET_COUNT = 6
FET_SIZE = (9.0, 7.0, 2.5)  # radial, tangential, height
FET_CIRCLE_R = 38.0
CAP_COUNT = 6
CAP_R = 4.0
CAP_H = 5.0
CAP_CIRCLE_R = 33.0
MCU_SIZE = (10.0, 10.0, 1.5)
MCU_CENTER = (0.0, 22.0)  # az 90 deg

ENCODER_BOARD_R = (8.0, 20.0)
ENCODER_BOARD_Z = (-26.0, -24.4)
ENCODER_CHIP_SIZE = (5.0, 5.0, 1.0)
ENCODER_CHIP_CENTER = (0.0, -10.0)  # az 270 deg, faces the rotor magnet ring
ENC_MAGNET_R = (7.5, 12.0)
ENC_MAGNET_Z = (-22.0, -20.0)

# ---------------------------------------------------------------------------
# Output: carrier, cross-roller bearing, torque sensor, flange
# ---------------------------------------------------------------------------
CARRIER_PIN_R = 3.75
CARRIER_PIN_Z = (8.5, 21.0)
CARRIER_PLATE_R = (8.0, 31.0)
CARRIER_PLATE_Z = (21.0, 24.5)
CARRIER_HUB_R = (8.0, 25.0)
CARRIER_HUB_Z = (24.5, 26.0)
CARRIER_LIGHTEN_HOLE_R = 4.0
CARRIER_LIGHTEN_CIRCLE_R = 19.0
CARRIER_LIGHTEN_ANGLES = (30.0, 150.0, 270.0)

XROLLER_INNER_R = (33.0, 37.5)
XROLLER_OUTER_R = (41.5, 46.0)
XROLLER_Z = (21.0, 29.0)
XROLLER_GROOVE_SQ = 5.65  # rotated-45deg square raceway profile
XROLLER_PITCH_R = 39.5
XROLLER_ROLLER_R = 2.75
XROLLER_ROLLER_L = 5.5
XROLLER_COUNT = 16

FLEXURE_HUB_R = (8.0, 14.0)
FLEXURE_HUB_Z = (26.0, 28.5)
FLEXURE_SPOKE_COUNT = 4
FLEXURE_SPOKE_L = 13.0
FLEXURE_SPOKE_W = 6.0
FLEXURE_SPOKE_Z = (26.5, 28.5)
FLEXURE_RIM_R = (26.0, 32.0)
FLEXURE_RIM_Z = (26.5, 29.0)
GAUGE_SIZE = (8.0, 4.0, 0.3)
GAUGE_Z = 28.5

FLANGE_PLATE_R = (7.6, 36.0)
FLANGE_PLATE_Z = (29.0, 33.0)
FLANGE_BOSS_R = (14.0, 20.0)
FLANGE_BOSS_Z = (33.0, 34.5)
FLANGE_BOLT_CIRCLE_R = 28.0  # 6x M5 output bolt circle
FLANGE_BOLT_R = 2.75
FLANGE_BOLT_COUNT = 6
FLANGE_PILOT_HOLE_R = 1.7  # 4x M3 on the pilot boss
FLANGE_PILOT_CIRCLE_R = 17.0

# ---------------------------------------------------------------------------
# Exploded-view static translations (mm at explode=1.0), documented per part.
# Pure +/-Z technical explosion with two-tier spacing rhythm: ~10-17 mm air
# gaps between parts inside a subsystem and ~20-25 mm gaps at subsystem
# boundaries (electronics | housing | motor | gear stage | output stage), so
# every part owns a readable station. Verified pairwise non-overlapping at
# factor 1.0.
# ---------------------------------------------------------------------------
EXPLODE_OFFSETS = {
    # rear: sealed connectors / cover / electronics (~12-18 mm internal gaps)
    "connector_power": -82.0,
    "connector_signal": -82.0,
    "rear_cover": -64.0,
    "driver_pcb": -46.0,
    "encoder_pcb": -32.0,
    # fixed root (housing | electronics boundary ~24 mm)
    "housing": 0.0,
    # motor group (housing | motor boundary ~19 mm, ~11-16 mm internal)
    "encoder_magnet_ring": 70.0,
    "rotor_bearing_rear": 78.0,
    "stator": 94.0,
    "rotor": 128.0,
    "rotor_bearing_front": 154.0,
    # gear stage (motor | gears boundary ~21 mm, ~14-16 mm internal)
    "ring_gear": 168.0,
    "sun_gear": 196.0,
    "planet_gear": 222.0,
    "planet_carrier": 250.0,
    # output stage (gears | output boundary ~25 mm, ~11-18 mm internal)
    "cross_roller_bearing": 280.0,
    "front_retainer": 298.0,
    "retainer_screws": 312.0,
    "torque_sensor": 330.0,
    "output_flange": 348.0,
    "cable_tube": 360.0,
}
# Planets additionally translate radially outward so the three gears separate
# in projection instead of stacking behind each other.
PLANET_EXPLODE_RADIAL = 14.0

# ---------------------------------------------------------------------------
# Concept material colors (production-actuator palette: dark anodized body,
# machined-aluminum output hardware, one anodized accent ring)
# ---------------------------------------------------------------------------
# Plain RGB(A) tuples / sRGB hex strings, not bd.Color objects: build123d's
# Shape.color setter builds the Color on assignment, and a module-level
# bd.Color(...) would import the CAD kernel when the module loads.
AL_BODY = "#65676c"  # black-anodized housing
AL_COVER = "#5f6165"  # black-anodized rear cover
AL_BRIGHT = "#e5e6e8"  # machined aluminum (flange, carrier)
AL_RETAINER = "#ed7c19"  # saturated anodized-orange accent ring
STEEL = "#ced0d4"
STEEL_POLISHED = "#e2e3e6"
STEEL_RACE = "#868993"  # dark bearing-steel races vs aluminum
STEEL_ROLLER = "#edeff1"
LAMINATION = "#95979e"
COPPER = "#e7b376"
ROTOR_DARK = "#868990"
MAGNET_N = "#595961"  # alternating pole colors: dark / nickel
MAGNET_S = "#d7d8db"
FERRITE = "#895059"
PCB_GREEN = "#3f9569"
IC_BLACK = "#505055"
CAP_GRAY = "#818695"
PLASTIC_BLACK = "#4b4b50"
GUNMETAL = "#9ea0a6"  # connector coupling nuts
PIN_GOLD = "#e7d189"  # connector contacts
BLACK_OXIDE = "#7c7c81"  # socket-head fasteners
RUBBER = "#383838"
TITANIUM = "#cbcad1"
GAUGE_GOLD = "#eddda0"
TUBE_BLACK = "#999ba0"  # dark gunmetal, reads against the cover

# ---------------------------------------------------------------------------
# Concept materials: what each part is made of, in the finish its colour above
# names. Catalogue entries (the project's own where the catalogue has none),
# each with explicit scalar PBR. `_label` restores the authored palette colour
# after setting the native material.
# ---------------------------------------------------------------------------
ANODIZED_AL = FinishedMaterial(
    metals.aluminum().material,
    pbr=PbrProperties.create('Bead-blasted 6061-T6, hard-anodised', metalness=1.0, roughness=0.6),
)
MACHINED_AL = FinishedMaterial(
    metals.aluminum(metals.Alu.G7075_T6).material,
    pbr=PbrProperties.create('High-strength zinc-alloyed aluminium for stressed parts', metalness=1.0,
        roughness=0.35, anisotropy=0.3),
)  # carrier, output flange: stressed, machined
TUBE_AL = FinishedMaterial(
    RangeMaterial(name='Aluminum 6063-T5', density=2700.0),
    pbr=PbrProperties.create('Extruded tube, dark anodised', metalness=1.0, roughness=0.45),
)
SCREW_STEEL = FinishedMaterial(
    metals.alloy_steel().material,
    pbr=PbrProperties.create('Alloy steel, black oxide', metalness=1.0, roughness=0.55),
)
GEAR_STEEL = FinishedMaterial(
    metals.alloy_steel().material,
    pbr=PbrProperties.create('Hardened and ground gear steel', metalness=1.0, roughness=0.3),
)
BEARING_STEEL = FinishedMaterial(
    metals.alloy_steel().material,
    pbr=PbrProperties.create('Through-hardened bearing steel, ground', metalness=1.0, roughness=0.12),
)
LAMINATION_STEEL = FinishedMaterial(
    metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
    pbr=PbrProperties.create('Laminated electrical steel, varnished', metalness=1.0, roughness=0.5,
        clearcoat=0.3, clearcoat_roughness=0.3),
)
ROTOR_STEEL = FinishedMaterial(
    metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
    pbr=PbrProperties.create('Rotor bell and back iron', metalness=1.0, roughness=0.4),
)
MAGNET_WIRE = FinishedMaterial(
    metals.copper().material,
    pbr=PbrProperties.create('Enamelled magnet wire', metalness=1.0, roughness=0.25, clearcoat=1.0,
        clearcoat_roughness=0.1),
)
NDFEB = FinishedMaterial(
    RangeMaterial(name='Neodymium magnet N42', density=7500.0),
    pbr=PbrProperties.create('Sintered rare-earth magnet, nickel plated; brittle, no structural values',
        metalness=1.0, roughness=0.2),
)  # rotor magnets, the pole colours above
FERRITE_MAGNET = FinishedMaterial(
    RangeMaterial(name='Ferrite magnet', density=4900.0),
    pbr=PbrProperties.create('Diametric encoder magnet ring', metalness=0.0, roughness=0.7),
)
FR4_BOARD = FinishedMaterial(
    plastics.fr4().material,
    pbr=PbrProperties.create('Woven glass and epoxy circuit-board laminate under green solder mask',
        metalness=0.0, roughness=0.45, clearcoat=0.5, clearcoat_roughness=0.2),
)  # driver and encoder boards, under solder mask
IC_PACKAGE = FinishedMaterial(
    plastics.abs_().material,
    pbr=PbrProperties.create('Acrylonitrile butadiene styrene, moulded or printed', metalness=0.0,
        roughness=0.55),
)  # FETs, MCU, encoder IC
CAPACITOR_AL = FinishedMaterial(
    metals.aluminum(metals.Alu.G5052_H32).material,
    pbr=PbrProperties.create('Drawn aluminium capacitor can', metalness=1.0, roughness=0.4, anisotropy=0.3),
)
CONNECTOR_NYLON = FinishedMaterial(
    plastics.nylon(plastics.Nylon.PA6).material,
    pbr=PbrProperties.create('Polyamide 6, moulded or machined', metalness=0.0, roughness=0.6),
)  # connector bodies
COLLAR_STEEL = FinishedMaterial(
    metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
    pbr=PbrProperties.create('Connector coupling nut', metalness=1.0, roughness=0.4),
)
O_RING_NBR = FinishedMaterial(
    RangeMaterial(name='NBR 70A', density=1250.0),
    pbr=PbrProperties.create('Nitrile rubber: O-rings and oil seals', metalness=0.0, roughness=0.9),
)
CONTACT_BRASS = FinishedMaterial(
    metals.brass().material,
    pbr=PbrProperties.create('Gold-plated contacts', metalness=1.0, roughness=0.2),
)
FLEXURE_TI = FinishedMaterial(
    metals.titanium().material,
    pbr=PbrProperties.create('Alpha-beta titanium alloy', metalness=1.0, roughness=0.4),
)  # torque-sensing flexure
GAUGE_FOIL = FinishedMaterial(
    RangeMaterial(name='Polyimide film', density=1420.0),
    pbr=PbrProperties.create('Foil strain gauge on a polyimide carrier', metalness=0.0, roughness=0.3,
        clearcoat=0.5, clearcoat_roughness=0.1),
)

# ---------------------------------------------------------------------------
# Consistency checks (concept-level fit, not tolerance engineering)
# ---------------------------------------------------------------------------
assert RING_TEETH == SUN_TEETH + 2 * PLANET_TEETH, "planetary tooth-count identity"
assert (SUN_TEETH + RING_TEETH) % PLANET_COUNT == 0, "equal planet spacing condition"
assert AIRGAP >= 0.5, "outrunner magnetic airgap"
assert SUN_ROOT_R - TUBE_OUTER_R - 0.5 >= 2.5, "sun gear wall over hollow tube"
assert MAGNET_OR <= BACK_IRON_R[0] + 1e-9, "magnets sit inside the back iron"
assert BACK_IRON_R[1] < BARREL_R[0], "rotor bell clears the housing bore"
assert XROLLER_INNER_R[1] < XROLLER_PITCH_R - 0.5, "roller pitch sits in the race gap"
assert XROLLER_OUTER_R[0] > XROLLER_PITCH_R + 0.5, "roller pitch sits in the race gap"
assert RING_RIM_R == BARREL_R[0], "ring gear rim seats in the housing bore"
assert FLEXURE_RIM_R[1] < XROLLER_INNER_R[0], "torque flexure clears the bearing"


def _tube_z(outer_r: float, inner_r: float, z: tuple[float, float]) -> bd.Part:
    """Annular ring solid between z[0]..z[1]."""
    return bd.Pos(0, 0, z[0]) * bd.extrude(bd.Circle(outer_r) - bd.Circle(inner_r), amount=z[1] - z[0])


def _cyl_z(r: float, z: tuple[float, float]) -> bd.Part:
    return bd.Pos(0, 0, z[0]) * bd.extrude(bd.Circle(r), amount=z[1] - z[0])


def _external_gear(teeth: int, root_r: float, tip_r: float, bore_r: float) -> bd.Part:
    """Concept gear: root cylinder + trapezoidal teeth with visible backlash."""
    half_arc = math.pi * GEAR_MODULE / 2
    wt = half_arc * 0.34  # half-width at tip (thinned for visible backlash)
    wr = half_arc * 0.55  # half-width at root
    h = tip_r - root_r
    rm = (tip_r + root_r) / 2
    tooth = bd.Polygon(
        (-h / 2 - 0.4, -wr), (h / 2, -wt), (h / 2, wt), (-h / 2 - 0.4, wr), align=None
    )
    teeth_sk = [loc * tooth for loc in bd.PolarLocations(rm, teeth)]
    sketch = bd.Circle(root_r) + teeth_sk - bd.Circle(bore_r)
    return bd.extrude(sketch, amount=GEAR_WIDTH)


def _internal_ring_gear() -> bd.Part:
    """Internal ring gear with inward trapezoidal teeth and press-in rim."""
    half_arc = math.pi * GEAR_MODULE / 2
    wt = half_arc * 0.34
    wr = half_arc * 0.55
    h = RING_ROOT_R - RING_TIP_R
    rm = (RING_ROOT_R + RING_TIP_R) / 2
    # counter-clockwise point order so the face normal is +Z and the teeth
    # extrude in the same direction as the rim
    tooth = bd.Polygon(
        (h / 2 + 0.4, -wr), (h / 2 + 0.4, wr), (-h / 2, wt), (-h / 2, -wt), align=None
    )
    teeth_sk = [loc * tooth for loc in bd.PolarLocations(rm, RING_TEETH)]
    sketch = bd.Circle(RING_RIM_R) - bd.Circle(RING_ROOT_R) + teeth_sk
    return bd.extrude(sketch, amount=GEAR_WIDTH)


def make_housing() -> bd.Part:
    """Finned aluminum housing: barrel, rear wall, stator sleeve, standoffs."""
    barrel = _tube_z(BARREL_R[1], BARREL_R[0], BARREL_Z)
    rear_wall = _tube_z(REAR_WALL_R[1], REAR_WALL_R[0], REAR_WALL_Z)
    sleeve = _tube_z(SLEEVE_R[1], SLEEVE_R[0], SLEEVE_Z)

    fin = bd.Box(
        FIN_RADIAL[1] - FIN_RADIAL[0] + 0.5,  # overlap into the barrel for fusing
        FIN_W,
        FIN_Z[1] - FIN_Z[0],
    )
    fin_loc = bd.Pos((FIN_RADIAL[0] - 0.5 + FIN_RADIAL[1]) / 2, 0, (FIN_Z[0] + FIN_Z[1]) / 2)
    fins = [rot * (fin_loc * fin) for rot in bd.PolarLocations(0, FIN_COUNT)]

    standoffs = []
    for az in ENC_STANDOFF_ANGLES:
        standoffs.append(
            bd.Rotation(0, 0, az)
            * bd.Pos(ENC_STANDOFF_CIRCLE_R, 0, 0)
            * _cyl_z(ENC_STANDOFF_R, ENC_STANDOFF_Z)
        )
    for az in DRV_STANDOFF_ANGLES:
        standoffs.append(
            bd.Rotation(0, 0, az)
            * bd.Pos(DRV_STANDOFF_CIRCLE_R, 0, 0)
            * _cyl_z(DRV_STANDOFF_R, DRV_STANDOFF_Z)
        )

    housing = barrel + [rear_wall, sleeve, *fins, *standoffs]

    cuts = []
    # 8x M3 retainer screw holes in the front barrel face
    for loc in bd.PolarLocations(FRONT_SCREW_CIRCLE_R, FRONT_SCREW_COUNT, start_angle=22.5):
        cuts.append(loc * _cyl_z(1.7, (BARREL_Z[1] - 8.0, BARREL_Z[1] + 0.1)))
    # 8x M3 rear cover screw holes in the rear barrel face
    for loc in bd.PolarLocations(REAR_SCREW_CIRCLE_R, REAR_SCREW_COUNT, start_angle=22.5):
        cuts.append(loc * _cyl_z(1.4, (BARREL_Z[0] - 0.1, BARREL_Z[0] + 5.0)))
    # 3x stator phase-wire passages through the rear wall
    for az in PHASE_WIRE_ANGLES:
        cuts.append(
            bd.Rotation(0, 0, az)
            * bd.Pos(PHASE_WIRE_CIRCLE_R, 0, 0)
            * _cyl_z(PHASE_WIRE_HOLE_R, (REAR_WALL_Z[0] - 0.1, REAR_WALL_Z[1] + 0.1))
        )
    return housing - cuts


def make_front_retainer() -> bd.Part:
    """Bolted bearing retainer ring (makes the front stack assemblable)."""
    ring = _tube_z(RETAINER_R[1], RETAINER_R[0], RETAINER_Z)
    holes = [
        loc * _cyl_z(1.7, (RETAINER_Z[0] - 0.1, RETAINER_Z[1] + 0.1))
        for loc in bd.PolarLocations(FRONT_SCREW_CIRCLE_R, FRONT_SCREW_COUNT, start_angle=22.5)
    ]
    return ring - holes


def make_retainer_screws() -> list[bd.Part]:
    """8x M3 socket-head fasteners populating the retainer screw circle."""
    screws = []
    socket = bd.extrude(bd.RegularPolygon(RETAINER_SCREW_SOCKET_R, 6), amount=1.2)
    for loc in bd.PolarLocations(FRONT_SCREW_CIRCLE_R, FRONT_SCREW_COUNT, start_angle=22.5):
        head = _cyl_z(
            RETAINER_SCREW_HEAD_R, (RETAINER_Z[1], RETAINER_Z[1] + RETAINER_SCREW_HEAD_H)
        )
        shank = _cyl_z(1.55, (RETAINER_Z[0] + 0.5, RETAINER_Z[1]))
        screw = (head + shank) - bd.Pos(
            0, 0, RETAINER_Z[1] + RETAINER_SCREW_HEAD_H - 1.1
        ) * socket
        screws.append(loc * screw)
    return screws


def make_rear_cover() -> bd.Part:
    """Sealed rear cover: plate, locating lip, tube boss, o-ring glands."""
    plate = _cyl_z(COVER_R, COVER_PLATE_Z)
    lip = _tube_z(COVER_LIP_R[1], COVER_LIP_R[0], COVER_LIP_Z)
    boss = _tube_z(COVER_BOSS_R[1], COVER_BOSS_R[0], COVER_BOSS_Z)
    cover = plate + [lip, boss]

    cuts = [_cyl_z(COVER_BOSS_R[0], (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[1] + 0.1))]
    # connector pass-throughs + o-ring glands on the rear face
    for name, az in CONNECTOR_ANGLES.items():
        hole_r = 5.0 if name == "power" else 4.0
        conn_loc = bd.Rotation(0, 0, az) * bd.Pos(CONNECTOR_CIRCLE_R, 0, 0)
        cuts.append(conn_loc * _cyl_z(hole_r, (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[1] + 0.1)))
        cuts.append(
            conn_loc
            * bd.Pos(0, 0, COVER_PLATE_Z[0])
            * bd.Torus(ORING_MAJOR_R * CONNECTOR_SCALE[name], ORING_GLAND_MINOR_R)
        )
    # 8x M3 counterbored cover screws
    for loc in bd.PolarLocations(REAR_SCREW_CIRCLE_R, REAR_SCREW_COUNT, start_angle=22.5):
        cuts.append(loc * _cyl_z(1.7, (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[1] + 0.1)))
        cuts.append(loc * _cyl_z(3.0, (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[0] + 1.8)))
    return cover - cuts


def make_connector(kind: str) -> list[bd.Part]:
    """Sealed circular connector at the cover face.

    Body with shrouded keying cup, 12-flat coupling nut (knurl read), recessed
    insert floor with a gold pin array, and an o-ring seal at the flange.
    """
    az = CONNECTOR_ANGLES[kind]
    scale = CONNECTOR_SCALE[kind]
    z0 = COVER_PLATE_Z[0]  # mounting face, body protrudes in -Z
    flange = _cyl_z(9.0 * scale, (z0 - 1.5, z0))
    barrel = _cyl_z(7.5 * scale, (z0 - 6.5, z0 - 1.5))
    core = _cyl_z(5.5 * scale, (z0 - 7.8, z0 - 1.5))
    shroud = _tube_z(6.0 * scale, 5.0 * scale, (z0 - 10.0, z0 - 7.5))
    insert_floor = _cyl_z(5.0 * scale, (z0 - 8.4, z0 - 7.5))
    body = flange + [barrel, core, shroud, insert_floor]
    # cut the gland into the connector flange as well so the o-ring seats cleanly
    body = body - bd.Pos(0, 0, z0) * bd.Torus(ORING_MAJOR_R * scale, ORING_GLAND_MINOR_R)
    collar = bd.Pos(0, 0, z0 - 9.0) * bd.extrude(
        bd.RegularPolygon(8.5 * scale, 12) - bd.Circle(6.2 * scale), amount=2.5
    )
    o_ring = bd.Pos(0, 0, z0) * bd.Torus(ORING_MAJOR_R * scale, ORING_MINOR_R)
    pin_count = 4 if kind == "power" else 6
    pin_r = 0.8 * scale if kind == "power" else 0.55
    pins = bd.Compound(
        children=[
            loc * _cyl_z(pin_r, (z0 - 9.7, z0 - 8.4))
            for loc in bd.PolarLocations(2.6 * scale, pin_count)
        ]
    )
    loc = bd.Rotation(0, 0, az) * bd.Pos(CONNECTOR_CIRCLE_R, 0, 0)
    return [loc * body, loc * collar, loc * o_ring, loc * pins]


def make_driver_pcb() -> dict[str, object]:
    """Annular motor-driver PCB with FETs, bus capacitors, and MCU."""
    board = _tube_z(DRIVER_BOARD_R[1], DRIVER_BOARD_R[0], DRIVER_BOARD_Z)
    z_face = DRIVER_BOARD_Z[1]
    fets = []
    for i, loc in enumerate(bd.PolarLocations(FET_CIRCLE_R, FET_COUNT, start_angle=15.0)):
        fets.append(
            loc * bd.Pos(0, 0, z_face + FET_SIZE[2] / 2) * bd.Box(FET_SIZE[0], FET_SIZE[1], FET_SIZE[2])
        )
    caps = [
        loc * bd.Pos(0, 0, z_face + CAP_H / 2) * bd.Cylinder(CAP_R, CAP_H)
        for loc in bd.PolarLocations(CAP_CIRCLE_R, CAP_COUNT, start_angle=0.0)
    ]
    mcu = bd.Pos(MCU_CENTER[0], MCU_CENTER[1], z_face + MCU_SIZE[2] / 2) * bd.Box(*MCU_SIZE)
    return {"board": board, "fets": fets, "caps": caps, "mcu": mcu}


def make_encoder_pcb() -> dict[str, object]:
    """Encoder PCB behind the rotor magnet ring."""
    board = _tube_z(ENCODER_BOARD_R[1], ENCODER_BOARD_R[0], ENCODER_BOARD_Z)
    chip = bd.Pos(
        ENCODER_CHIP_CENTER[0], ENCODER_CHIP_CENTER[1], ENCODER_BOARD_Z[1] + ENCODER_CHIP_SIZE[2] / 2
    ) * bd.Box(*ENCODER_CHIP_SIZE)
    return {"board": board, "chip": chip}


def make_stator() -> dict[str, object]:
    """24-slot outrunner stator: laminated yoke/teeth and copper windings."""
    yoke = _tube_z(STATOR_YOKE_OR, STATOR_YOKE_IR, STATOR_STACK_Z)
    z_mid = (STATOR_STACK_Z[0] + STATOR_STACK_Z[1]) / 2
    stack_h = STATOR_STACK_Z[1] - STATOR_STACK_Z[0]

    tooth = bd.Pos((STATOR_YOKE_OR - 0.5 + STATOR_TOOTH_TIP_R) / 2, 0, z_mid) * bd.Box(
        STATOR_TOOTH_TIP_R - STATOR_YOKE_OR + 0.5, STATOR_TOOTH_W, stack_h
    )
    shoe = bd.Pos((STATOR_SHOE_IR + STATOR_TOOTH_TIP_R) / 2, 0, z_mid) * bd.Box(
        STATOR_TOOTH_TIP_R - STATOR_SHOE_IR, STATOR_SHOE_W, stack_h
    )
    tooth_unit = tooth + shoe
    teeth = [rot * tooth_unit for rot in bd.PolarLocations(0, STATOR_SLOTS)]
    stack = yoke + teeth

    # one rectangular coil loop around a tooth, then a polar pattern of copies
    wind_r_mid = (WINDING_RADIAL[0] + WINDING_RADIAL[1]) / 2
    coil_outer = bd.Pos(wind_r_mid, 0, z_mid) * bd.Box(
        WINDING_RADIAL[1] - WINDING_RADIAL[0], WINDING_TANGENTIAL, WINDING_AXIAL
    )
    coil_hole = bd.Pos(wind_r_mid, 0, z_mid) * bd.Box(
        WINDING_RADIAL[1] - WINDING_RADIAL[0] + 1.0, WINDING_HOLE_TANGENTIAL, WINDING_HOLE_AXIAL
    )
    coil = coil_outer - coil_hole
    windings = [rot * coil for rot in bd.PolarLocations(0, STATOR_SLOTS)]
    return {"stack": stack, "windings": windings}


def make_rotor() -> dict[str, object]:
    """Outrunner rotor bell: hollow hub, front web, back iron, magnet ring."""
    hub = _tube_z(ROTOR_HUB_R[1], ROTOR_HUB_R[0], ROTOR_HUB_Z)
    web = _tube_z(BACK_IRON_R[1], ROTOR_HUB_R[0], ROTOR_WEB_Z)
    iron = _tube_z(BACK_IRON_R[1], BACK_IRON_R[0], BACK_IRON_Z)
    flange = _tube_z(ROTOR_FLANGE_R[1], ROTOR_FLANGE_R[0], ROTOR_FLANGE_Z)
    body = hub + [web, iron, flange]

    cuts = []
    # 6x web lightening holes
    for loc in bd.PolarLocations(28.0, 6, start_angle=30.0):
        cuts.append(loc * _cyl_z(5.0, (ROTOR_WEB_Z[0] - 0.1, ROTOR_WEB_Z[1] + 0.1)))
    # 4x M3 sun-gear coupling holes
    for loc in bd.PolarLocations(COUPLING_HOLE_R, 4, start_angle=45.0):
        cuts.append(loc * _cyl_z(1.6, (ROTOR_FLANGE_Z[0] - 0.1, ROTOR_FLANGE_Z[1] + 0.1)))
    body = body - cuts

    z_mid = (MAGNET_Z[0] + MAGNET_Z[1]) / 2

    # Two independent prototypes so the alternating pole groups keep distinct
    # exported materials (copies of one shape share a single STEP style).
    def magnet_proto() -> bd.Part:
        return bd.Pos((MAGNET_IR + MAGNET_OR) / 2, 0, z_mid) * bd.Box(
            MAGNET_OR - MAGNET_IR, MAGNET_W, MAGNET_Z[1] - MAGNET_Z[0]
        )

    north_proto, south_proto = magnet_proto(), magnet_proto()
    locs = list(bd.PolarLocations(0, MAGNET_COUNT))
    magnets_north = [locs[i] * north_proto for i in range(0, MAGNET_COUNT, 2)]
    magnets_south = [locs[i] * south_proto for i in range(1, MAGNET_COUNT, 2)]
    return {"body": body, "magnets_north": magnets_north, "magnets_south": magnets_south}


def make_ball_bearing(z: tuple[float, float]) -> dict[str, object]:
    """Simplified deep-groove rotor support bearing: races + ball ring."""
    z_mid = (z[0] + z[1]) / 2
    ball_pitch_r = (ROTOR_BRG_IR[1] + ROTOR_BRG_OR[0]) / 2
    groove = bd.Pos(0, 0, z_mid) * bd.Torus(ball_pitch_r, ROTOR_BRG_BALL_R + 0.05)
    inner = _tube_z(ROTOR_BRG_IR[1], ROTOR_BRG_IR[0], z) - groove
    outer = _tube_z(ROTOR_BRG_OR[1], ROTOR_BRG_OR[0], z) - groove
    balls = [
        loc * bd.Pos(0, 0, z_mid) * bd.Sphere(ROTOR_BRG_BALL_R)
        for loc in bd.PolarLocations(ball_pitch_r, ROTOR_BRG_BALL_COUNT)
    ]
    return {"inner": inner, "outer": outer, "balls": balls}


def make_sun_gear() -> bd.Part:
    """Sun gear with hollow bore and rotor coupling flange."""
    gear = bd.Pos(0, 0, GEAR_Z[0]) * _external_gear(SUN_TEETH, SUN_ROOT_R, SUN_TIP_R, TUBE_OUTER_R + 0.5)
    neck = _tube_z(SUN_ROOT_R, TUBE_OUTER_R + 0.5, (ROTOR_FLANGE_Z[1], GEAR_Z[0]))
    flange = _tube_z(15.0, TUBE_OUTER_R + 0.5, (ROTOR_FLANGE_Z[1], ROTOR_FLANGE_Z[1] + 1.5))
    sun = gear + [neck, flange]
    holes = [
        loc * _cyl_z(1.6, (ROTOR_FLANGE_Z[1] - 0.1, ROTOR_FLANGE_Z[1] + 1.6))
        for loc in bd.PolarLocations(COUPLING_HOLE_R, 4, start_angle=45.0)
    ]
    return sun - holes


def make_planet_gear() -> bd.Part:
    """One planet gear at the origin; placed with mesh-phase rotation."""
    return _external_gear(PLANET_TEETH, PLANET_ROOT_R, PLANET_TIP_R, PLANET_BORE_R)


def planet_location(psi_deg: float) -> bd.Location:
    """Planet placement: position on the carrier circle plus mesh phasing.

    With sun/ring tooth patterns starting at azimuth 0, a tooth of each faces
    the planet center whenever psi is a multiple of the sun/ring angular pitch
    (true for 90/210/330 with 24 and 84 teeth). Rotating the planet by
    psi + half a planet tooth pitch puts a tooth gap on the line of centers.
    """
    phase = psi_deg + 180.0 / PLANET_TEETH
    px = PLANET_CENTER_R * math.cos(math.radians(psi_deg))
    py = PLANET_CENTER_R * math.sin(math.radians(psi_deg))
    return bd.Pos(px, py, GEAR_Z[0]) * bd.Rotation(0, 0, phase)


def make_carrier() -> bd.Part:
    """Single-sided planet carrier: pins, plate, and torque-sensor hub."""
    plate = _tube_z(CARRIER_PLATE_R[1], CARRIER_PLATE_R[0], CARRIER_PLATE_Z)
    hub = _tube_z(CARRIER_HUB_R[1], CARRIER_HUB_R[0], CARRIER_HUB_Z)
    pins = [
        loc * _cyl_z(CARRIER_PIN_R, CARRIER_PIN_Z)
        for loc in bd.PolarLocations(PLANET_CENTER_R, PLANET_COUNT, start_angle=90.0)
    ]
    carrier = plate + [hub, *pins]
    lighten = [
        bd.Rotation(0, 0, az)
        * bd.Pos(CARRIER_LIGHTEN_CIRCLE_R, 0, 0)
        * _cyl_z(CARRIER_LIGHTEN_HOLE_R, (CARRIER_PLATE_Z[0] - 0.1, CARRIER_PLATE_Z[1] + 0.1))
        for az in CARRIER_LIGHTEN_ANGLES
    ]
    return carrier - lighten


def make_cross_roller_bearing() -> dict[str, object]:
    """Cross-roller output bearing: V-groove races, alternating 45-deg rollers."""
    z_mid = (XROLLER_Z[0] + XROLLER_Z[1]) / 2
    groove_profile = bd.Plane.XZ * (
        bd.Pos(XROLLER_PITCH_R, z_mid) * bd.Rotation(0, 0, 45) * bd.Rectangle(XROLLER_GROOVE_SQ, XROLLER_GROOVE_SQ)
    )
    groove = bd.revolve(groove_profile, axis=bd.Axis.Z)
    inner = _tube_z(XROLLER_INNER_R[1], XROLLER_INNER_R[0], XROLLER_Z) - groove
    outer = _tube_z(XROLLER_OUTER_R[1], XROLLER_OUTER_R[0], XROLLER_Z) - groove

    rollers = []
    for i in range(XROLLER_COUNT):
        az = 360.0 * i / XROLLER_COUNT
        tilt = 45.0 if i % 2 == 0 else -45.0
        rollers.append(
            bd.Rotation(0, 0, az)
            * bd.Pos(XROLLER_PITCH_R, 0, z_mid)
            * bd.Rotation(0, tilt, 0)
            * bd.Cylinder(XROLLER_ROLLER_R, XROLLER_ROLLER_L)
        )
    return {"inner": inner, "outer": outer, "rollers": rollers}


def make_torque_sensor() -> dict[str, object]:
    """Spoked torque-sensing flexure with strain-gauge pads."""
    hub = _tube_z(FLEXURE_HUB_R[1], FLEXURE_HUB_R[0], FLEXURE_HUB_Z)
    rim = _tube_z(FLEXURE_RIM_R[1], FLEXURE_RIM_R[0], FLEXURE_RIM_Z)
    spoke_mid_r = (FLEXURE_HUB_R[1] + FLEXURE_RIM_R[0]) / 2
    spoke = bd.Pos(spoke_mid_r, 0, (FLEXURE_SPOKE_Z[0] + FLEXURE_SPOKE_Z[1]) / 2) * bd.Box(
        FLEXURE_SPOKE_L, FLEXURE_SPOKE_W, FLEXURE_SPOKE_Z[1] - FLEXURE_SPOKE_Z[0]
    )
    spokes = [rot * spoke for rot in bd.PolarLocations(0, FLEXURE_SPOKE_COUNT)]
    flexure = hub + [rim, *spokes]
    gauges = [
        rot * bd.Pos(spoke_mid_r, 0, GAUGE_Z + GAUGE_SIZE[2] / 2) * bd.Box(*GAUGE_SIZE)
        for rot in bd.PolarLocations(0, FLEXURE_SPOKE_COUNT)
    ]
    return {"flexure": flexure, "gauges": gauges}


def make_output_flange() -> bd.Part:
    """Output flange: bolt circle, pilot boss, hollow bore."""
    plate = _tube_z(FLANGE_PLATE_R[1], FLANGE_PLATE_R[0], FLANGE_PLATE_Z)
    boss = _tube_z(FLANGE_BOSS_R[1], FLANGE_BOSS_R[0], FLANGE_BOSS_Z)
    flange = plate + boss
    cuts = [
        loc * _cyl_z(FLANGE_BOLT_R, (FLANGE_PLATE_Z[0] - 0.1, FLANGE_PLATE_Z[1] + 0.1))
        for loc in bd.PolarLocations(FLANGE_BOLT_CIRCLE_R, FLANGE_BOLT_COUNT)
    ]
    cuts += [
        loc * _cyl_z(FLANGE_PILOT_HOLE_R, (FLANGE_PLATE_Z[0] + 0.5, FLANGE_BOSS_Z[1] + 0.1))
        for loc in bd.PolarLocations(FLANGE_PILOT_CIRCLE_R, 4, start_angle=45.0)
    ]
    return flange - cuts


def make_cable_tube() -> bd.Part:
    """Static hollow cable-routing tube through the full actuator stack."""
    return _tube_z(TUBE_OUTER_R, TUBE_INNER_R, TUBE_Z)


# ---------------------------------------------------------------------------
# Kinematics: the 4.5:1 planetary drive train's rates (the joints' limits)
# ---------------------------------------------------------------------------
# The drive is measured in INPUT REVOLUTIONS of the rotor. 4.5 input
# revolutions return the carrier to exactly 360 deg, and every rotating member
# is 180-deg symmetric (28 alternating magnets = 14 pole pairs, 24/30 tooth
# gears, 6x lightening + 4x coupling holes), so the cycle closes at tooth/pole
# phase. Each planet's joint is on the CARRIER, so its angle is the
# mesh-relative spin. Each revolute joint's range is the closed cycle at its
# member's rate; the gearing between them is the `drive` coupling, a
# constraint: one control, in input revolutions (0..4.5, the rotor's limits
# over its rate), and no member that turns alone.

_INPUT_TURNS = REDUCTION_RATIO  # 4.5 input revolutions = 1 carrier revolution
_ROTOR_DEG = 360.0
_CARRIER_DEG = 360.0 / REDUCTION_RATIO
# External sun/planet mesh reverses the relative rotation:
#   -(Ns/Np) * (rotor - carrier)
_PLANET_DEG = -(SUN_TEETH / PLANET_TEETH) * (_ROTOR_DEG - _CARRIER_DEG)
# Rotor-bearing ball cage runs near half the inner-race speed; 4/9 (~0.444 vs
# the physical ~0.452 for this geometry) lands the 10-ball ring exactly on its
# 36-deg symmetry at the end of the drive cycle.
_BALL_CAGE_DEG = _ROTOR_DEG * (4.0 / 9.0)
# Cross-roller cage: outer race fixed, inner race at carrier speed -> cage at
# half carrier speed; 16 alternating-tilt rollers repeat every 45 deg.
_ROLLER_CAGE_DEG = _CARRIER_DEG * 0.5

# The drive train: each revolute joint's degrees per input revolution.
_RATES = {
    "rotor_spin": _ROTOR_DEG,
    "output": _CARRIER_DEG,
    "rear_cage": _BALL_CAGE_DEG,
    "front_cage": _BALL_CAGE_DEG,
    "roller_cage": _ROLLER_CAGE_DEG,
    **{f"planet{i}_spin": _PLANET_DEG for i in range(1, PLANET_COUNT + 1)},
}

_Z = (0.0, 0.0, 1.0)


def _planet_center(psi_deg: float) -> tuple[float, float, float]:
    psi = math.radians(psi_deg)
    return (
        PLANET_CENTER_R * math.cos(psi),
        PLANET_CENTER_R * math.sin(psi),
        (GEAR_Z[0] + GEAR_Z[1]) / 2.0,
    )


def _turns(deg_per_turn: float) -> tuple[float, float]:
    """Revolute limits spanning the full closed cycle at this member's rate."""
    span = deg_per_turn * _INPUT_TURNS
    return (min(0.0, span), max(0.0, span))


# ---------------------------------------------------------------------------
# The clips' explode: the old ANIMATION_JS stations, as a GLB animation
# ---------------------------------------------------------------------------
# The old clips moved every module along Z to its EXPLODE_OFFSETS station times
# `explode`, rebased by FLOOR_LIFT so the lowest station (the connectors) stays at
# 0: the connectors are the one world-fixed thing and the housing rises 82 mm.
# `inspect` lifted the ring, sun and planets as one meshed cluster at GEAR_CLUSTER
# so the tooth engagement stays watchable, while the drive ran; `teardown` gave each
# its own station and spread the planets PLANET_EXPLODE_RADIAL out, the drive still.
# Each module is a reference of its own in the actuator's tree, so each takes its own
# translation, after the drive's pose.
FLOOR_LIFT = -min(EXPLODE_OFFSETS.values())  # 82: the connectors' station rebased to 0
GEAR_CLUSTER = 210.0  # inspect's meshed ring, sun and planets
_GEARS = ("ring_gear", "sun_gear", "planet_gear")
# Each module's reference in the actuator and the station it takes.
_STATIONS = {
    "housing": "housing", "front_retainer": "front_retainer", "retainer_screws": "retainer_screws",
    "rear_cover": "rear_cover", "connector:power": "connector_power", "connector:signal": "connector_signal",
    "driver_pcb": "driver_pcb", "encoder_pcb": "encoder_pcb", "encoder_magnet_ring": "encoder_magnet_ring",
    "stator": "stator", "rotor": "rotor", "rotor_bearing:rear": "rotor_bearing_rear",
    "rotor_bearing:front": "rotor_bearing_front", "sun_gear": "sun_gear", "ring_gear": "ring_gear",
    **{f"planet_gear:p{i}": "planet_gear" for i in range(1, len(PLANET_ANGLES_DEG) + 1)},
    "planet_carrier": "planet_carrier", "cross_roller_bearing": "cross_roller_bearing",
    "torque_sensor": "torque_sensor", "output_flange": "output_flange", "cable_tube": "cable_tube",
}
_KEY_STEP = 0.1  # s between the sampled keys of an explode's channels


def _offset(ref: str, explode: float, keep_mesh: bool) -> tuple[float, float, float]:
    """A module's offset (mm) at ``explode`` (0..1): its station, rebased, along Z, and a
    planet's radial spread when the gears do not stay meshed."""
    station = _STATIONS[ref]
    lift = (GEAR_CLUSTER if keep_mesh and station in _GEARS else EXPLODE_OFFSETS[station]) + FLOOR_LIFT
    x = y = 0.0
    if station == "planet_gear" and not keep_mesh:
        psi = math.radians(PLANET_ANGLES_DEG[int(ref.rsplit("p", 1)[1]) - 1])
        x, y = PLANET_EXPLODE_RADIAL * math.cos(psi), PLANET_EXPLODE_RADIAL * math.sin(psi)
    return (x * explode, y * explode, lift * explode)


def _explode_animation(actuator: bd.Compound, name: str, duration: float, keep_mesh: bool, drive: bool) -> None:
    """The old clip ``name``: the stack opens on ``sin(pi * phase)`` and closes, each module
    sampled every ``_KEY_STEP`` as LINEAR keys, while ``drive`` runs one closed cycle (or the
    train stays as built)."""
    show = animation(actuator, name, duration=duration)
    if drive:
        show.pose(at={0: {"drive": 0.0}, duration: {"drive": _INPUT_TURNS}}, interpolation="LINEAR")
    count = round(duration / _KEY_STEP)
    times = [duration * i / count for i in range(count + 1)]
    explodes = [math.sin(math.pi * t / duration) for t in times]
    for ref in _STATIONS:
        if not any(_offset(ref, 1.0, keep_mesh)):
            continue  # the connectors: the world-fixed station
        keys = [(t, _offset(ref, e, keep_mesh)) for t, e in zip(times, explodes)]
        show.channel(ref, path="translation", keys=keys, interpolation="LINEAR")


# ---------------------------------------------------------------------------
# Assembly: native build123d labels, compounds and joints
# ---------------------------------------------------------------------------
# The port's stand-ins for cadgen's (deprecated) AssemblyHelper: a label and a
# colour on the shape, a module as a labelled Compound, and every mount as a pair
# of build123d joints with `connect_to` placing the moving side. Every datum is
# world-coincident, so each connection places a part where it was authored.


def _label(shape, name: str, *details: object, color=None, material=None):
    """``name:detail``, a colour and a material on the shape (the old ``asm.add``/``feature``)."""
    shape.label = ":".join(str(token) for token in (name, *details))
    if color is not None:
        shape.color = color
    if material is not None:
        color = shape.color
        shape.material = material
        shape.color = color
    return shape


def _module(name: str, children: list, *details: object) -> bd.Compound:
    """A labelled sub-assembly (the old ``asm.add_module``)."""
    return bd.Compound(children=children, label=":".join(str(token) for token in (name, *details)))


def _fasten(fixed, fixed_frame: str, moving, moving_frame: str, location: bd.Location) -> None:
    """A mount (the old ``rigid_frame`` pair + ``face_to_face``, and the old
    ``cadgen.fastened`` mate): a RigidJoint on each side at one world datum; the moving side
    placed by ``connect_to``."""
    bd.RigidJoint(fixed_frame, fixed, location)
    bd.RigidJoint(moving_frame, moving, location)
    fixed.joints[fixed_frame].connect_to(moving.joints[moving_frame])


def _spin(name: str, parent, child, origin, limits: tuple[float, float]) -> None:
    """A revolute mate about +Z through ``origin`` (the old ``cadgen.revolute``): a
    RevoluteJoint on the parent with the mate's limits, a RigidJoint on the child at the
    joint's own frame, the child placed at angle 0 -- its as-built pose."""
    bd.RevoluteJoint(name, parent, axis=bd.Axis(origin, _Z), angular_range=limits)
    bd.RigidJoint(name, child, bd.Plane(origin=origin, z_dir=_Z).location)
    parent.joints[name].connect_to(child.joints[name], angle=0.0)


def build_actuator(explode: float = 0.0) -> bd.Compound:
    """Build the labeled actuator assembly.

    explode=0 returns the assembled model with its joints, coupling,
    configurations and motions.
    explode>0 translates each part along Z by EXPLODE_OFFSETS * explode as a
    documented static exploded layout (joints are omitted in that mode).
    """
    children = []

    housing = _label(make_housing(), "housing", color=AL_BODY, material=ANODIZED_AL)
    retainer = _label(make_front_retainer(), "front_retainer", color=AL_RETAINER, material=ANODIZED_AL)
    cover = _label(make_rear_cover(), "rear_cover", color=AL_COVER, material=ANODIZED_AL)
    children += [housing, retainer, cover]

    screws = make_retainer_screws()
    retainer_screws = _label(bd.Compound(children=screws), "retainer_screws", color=BLACK_OXIDE, material=SCREW_STEEL)
    children.append(retainer_screws)

    connectors = {}
    for kind in CONNECTOR_ANGLES:
        body, collar, o_ring, pins = make_connector(kind)
        _label(body, "connector_body", kind, color=PLASTIC_BLACK, material=CONNECTOR_NYLON)
        _label(collar, "connector_collar", kind, color=GUNMETAL, material=COLLAR_STEEL)
        _label(o_ring, "connector_o_ring", kind, color=RUBBER, material=O_RING_NBR)
        _label(pins, "connector_pins", kind, color=PIN_GOLD, material=CONTACT_BRASS)
        connectors[kind] = _module("connector", [body, collar, o_ring, pins], kind)
        children.append(connectors[kind])

    drv = make_driver_pcb()
    _label(drv["board"], "driver_board", color=PCB_GREEN, material=FR4_BOARD)
    for i, fet in enumerate(drv["fets"], start=1):
        _label(fet, "fet", f"q{i}", color=IC_BLACK, material=IC_PACKAGE)
    for i, cap in enumerate(drv["caps"], start=1):
        _label(cap, "bus_capacitor", f"c{i}", color=CAP_GRAY, material=CAPACITOR_AL)
    _label(drv["mcu"], "mcu", color=IC_BLACK, material=IC_PACKAGE)
    driver_pcb = _module("driver_pcb", [drv["board"], *drv["fets"], *drv["caps"], drv["mcu"]])
    children.append(driver_pcb)

    enc = make_encoder_pcb()
    _label(enc["board"], "encoder_board", color=PCB_GREEN, material=FR4_BOARD)
    _label(enc["chip"], "encoder_ic", color=IC_BLACK, material=IC_PACKAGE)
    encoder_pcb = _module("encoder_pcb", [enc["board"], enc["chip"]])
    children.append(encoder_pcb)

    enc_magnet = _label(
        _tube_z(ENC_MAGNET_R[1], ENC_MAGNET_R[0], ENC_MAGNET_Z),
        "encoder_magnet_ring",
        color=FERRITE,
        material=FERRITE_MAGNET,
    )
    children.append(enc_magnet)

    st = make_stator()
    _label(st["stack"], "lamination_stack", color=LAMINATION, material=LAMINATION_STEEL)
    winding_compound = _label(bd.Compound(children=st["windings"]), "windings", color=COPPER, material=MAGNET_WIRE)
    stator = _module("stator", [st["stack"], winding_compound])
    children.append(stator)

    rt = make_rotor()
    _label(rt["body"], "rotor_bell", color=ROTOR_DARK, material=ROTOR_STEEL)
    mag_n = _label(bd.Compound(children=rt["magnets_north"]), "magnets_north", color=MAGNET_N, material=NDFEB)
    mag_s = _label(bd.Compound(children=rt["magnets_south"]), "magnets_south", color=MAGNET_S, material=NDFEB)
    rotor = _module("rotor", [rt["body"], mag_n, mag_s])
    children.append(rotor)

    bearings = {}
    races = {}
    balls_by_side = {}
    for name, z in (("rear", ROTOR_BRG_REAR_Z), ("front", ROTOR_BRG_FRONT_Z)):
        brg = make_ball_bearing(z)
        races[name] = _label(brg["inner"], "inner_race", name, color=STEEL_POLISHED, material=BEARING_STEEL)
        _label(brg["outer"], "outer_race", name, color=STEEL_POLISHED, material=BEARING_STEEL)
        balls = _label(bd.Compound(children=brg["balls"]), "balls", name, color=STEEL_ROLLER, material=BEARING_STEEL)
        balls_by_side[name] = balls
        bearings[name] = _module("rotor_bearing", [brg["inner"], brg["outer"], balls], name)
        children.append(bearings[name])

    sun = _label(make_sun_gear(), "sun_gear", color=STEEL, material=GEAR_STEEL)
    ring = _label(bd.Pos(0, 0, GEAR_Z[0]) * _internal_ring_gear(), "ring_gear", color=STEEL, material=GEAR_STEEL)
    children += [sun, ring]

    planet_proto = make_planet_gear()
    planets = []
    for i, psi in enumerate(PLANET_ANGLES_DEG, start=1):
        planet = planet_location(psi) * planet_proto
        planets.append(_label(planet, "planet_gear", f"p{i}", color=STEEL, material=GEAR_STEEL))
    children += planets

    carrier = _label(make_carrier(), "planet_carrier", color=AL_BRIGHT, material=MACHINED_AL)
    children.append(carrier)

    xr = make_cross_roller_bearing()
    inner_ring = _label(xr["inner"], "inner_ring", color=STEEL_RACE, material=BEARING_STEEL)
    _label(xr["outer"], "outer_ring", color=STEEL_RACE, material=BEARING_STEEL)
    rollers = _label(bd.Compound(children=xr["rollers"]), "rollers", color=STEEL_ROLLER, material=BEARING_STEEL)
    xroller = _module("cross_roller_bearing", [xr["inner"], xr["outer"], rollers])
    children.append(xroller)

    ts = make_torque_sensor()
    _label(ts["flexure"], "flexure_disc", color=TITANIUM, material=FLEXURE_TI)
    for i, gauge in enumerate(ts["gauges"], start=1):
        _label(gauge, "strain_gauge", f"g{i}", color=GAUGE_GOLD, material=GAUGE_FOIL)
    torque_sensor = _module("torque_sensor", [ts["flexure"], *ts["gauges"]])
    children.append(torque_sensor)

    flange = _label(make_output_flange(), "output_flange", color=AL_BRIGHT, material=MACHINED_AL)
    tube = _label(make_cable_tube(), "cable_tube", color=TUBE_BLACK, material=TUBE_AL)
    children += [flange, tube]

    by_name = {
        "housing": housing,
        "front_retainer": retainer,
        "retainer_screws": retainer_screws,
        "rear_cover": cover,
        "connector_power": connectors["power"],
        "connector_signal": connectors["signal"],
        "driver_pcb": driver_pcb,
        "encoder_pcb": encoder_pcb,
        "encoder_magnet_ring": enc_magnet,
        "stator": stator,
        "rotor": rotor,
        "rotor_bearing_rear": bearings["rear"],
        "rotor_bearing_front": bearings["front"],
        "sun_gear": sun,
        "ring_gear": ring,
        "planet_carrier": carrier,
        "cross_roller_bearing": xroller,
        "torque_sensor": torque_sensor,
        "output_flange": flange,
        "cable_tube": tube,
    }

    if explode:
        for name, part in by_name.items():
            offset = EXPLODE_OFFSETS.get(name, 0.0) * explode
            if offset:
                part.move(bd.Location((0, 0, offset)))
        for psi, planet in zip(PLANET_ANGLES_DEG, planets):
            dx = PLANET_EXPLODE_RADIAL * explode * math.cos(math.radians(psi))
            dy = PLANET_EXPLODE_RADIAL * explode * math.sin(math.radians(psi))
            planet.move(bd.Location((dx, dy, EXPLODE_OFFSETS["planet_gear"] * explode)))
    else:
        _connect(housing, retainer, cover, retainer_screws, connectors, driver_pcb, encoder_pcb,
                 stator, rotor, sun, ring, enc_magnet, carrier, torque_sensor, flange, xroller,
                 tube, races, bearings, balls_by_side, rollers, inner_ring, planets)

    actuator = bd.Compound(children=children, label="qdd_actuator")
    if not explode:
        _drive(actuator)
        _clips(actuator)
    return actuator


def _connect(housing, retainer, cover, retainer_screws, connectors, driver_pcb, encoder_pcb,
             stator, rotor, sun, ring, enc_magnet, carrier, torque_sensor, flange, xroller,
             tube, races, bearings, balls_by_side, rollers, inner_ring, planets) -> None:
    """Every joint of the assembled actuator. All identity by construction: each
    ``connect_to`` re-derives a placement from named datums."""
    # --- mounts (the original source mate frames) ------------------------------
    _fasten(housing, "stator_seat", stator, "stack_rear", bd.Location((0, 0, STATOR_STACK_Z[0])))
    _fasten(housing, "ring_gear_seat", ring, "rim_rear", bd.Location((0, 0, GEAR_Z[0])))
    _fasten(housing, "cover_seat", cover, "lip_face", bd.Location((0, 0, BARREL_Z[0])))
    _fasten(housing, "retainer_seat", retainer, "ring_rear", bd.Location((0, 0, RETAINER_Z[0])))
    _fasten(retainer, "screw_seats", retainer_screws, "head_seats", bd.Location((0, 0, RETAINER_Z[1])))

    for kind, module in connectors.items():
        az = math.radians(CONNECTOR_ANGLES[kind])
        mount = bd.Location(
            (
                CONNECTOR_CIRCLE_R * math.cos(az),
                CONNECTOR_CIRCLE_R * math.sin(az),
                COVER_PLATE_Z[0],
            )
        )
        _fasten(cover, f"{kind}_pad", module, "mount_face", mount)

    for name, module, z_seat in (
        ("driver_pcb", driver_pcb, DRV_STANDOFF_Z[0]),
        ("encoder_pcb", encoder_pcb, ENC_STANDOFF_Z[0]),
    ):
        _fasten(housing, f"{name}_seat", module, "mount_plane", bd.Location((0, 0, z_seat)))

    _fasten(rotor, "sun_coupling", sun, "flange_rear", bd.Location((0, 0, ROTOR_FLANGE_Z[1])))
    _fasten(rotor, "encoder_magnet_seat", enc_magnet, "ring_rear", bd.Location((0, 0, ENC_MAGNET_Z[0])))
    _fasten(carrier, "sensor_seat", torque_sensor, "hub_rear", bd.Location((0, 0, FLEXURE_HUB_Z[0])))
    # The flange's face on the flexure rim, a datum pair left unconnected: the flange
    # rides the carrier on `flange_mount` (the old fastened mate), and a second seat on
    # the torque sensor would close a loop.
    bd.RigidJoint("rim_face", torque_sensor, bd.Location((0, 0, FLEXURE_RIM_Z[1])))
    bd.RigidJoint("mount_rear", flange, bd.Location((0, 0, FLEXURE_RIM_Z[1])))
    _fasten(housing, "bearing_seat", xroller, "outer_ring_rear", bd.Location((0, 0, XROLLER_Z[0])))
    # The rotor bearings' outer races stay in the sleeve bore: each bearing module is
    # fastened to the housing (its inner race and ball ring ride their own joints).
    _fasten(housing, "rear_bearing_seat", bearings["rear"], "outer_race_face", bd.Location((0, 0, ROTOR_BRG_REAR_Z[0])))
    _fasten(housing, "front_bearing_seat", bearings["front"], "outer_race_face",
          bd.Location((0, 0, ROTOR_BRG_FRONT_Z[0])))
    _fasten(cover, "tube_bore", tube, "rear_end", bd.Location((0, 0, COVER_PLATE_Z[0])))

    # --- the old KINEMATICS mates as joints ------------------------------------
    # Fastened mates the mounts above do not already state (sun_coupling,
    # encoder_target and sensor_mount are the seats above): each rider turns with
    # the member it rides.
    _fasten(rotor, "rear_race", races["rear"], "rear_race", bd.Location())
    _fasten(rotor, "front_race", races["front"], "front_race", bd.Location())
    _fasten(carrier, "flange_mount", flange, "flange_mount", bd.Location())
    _fasten(carrier, "xroller_inner", inner_ring, "xroller_inner", bd.Location())
    # Revolute mates, their limits the closed drive cycle at each member's rate. Each
    # spin hub connects while its carrier is still pristine (planets before the
    # carrier's own joint). Every cage turns on the module that carries its outer race,
    # and the carrier on the cross-roller bearing's outer ring.
    for i, (psi, planet) in enumerate(zip(PLANET_ANGLES_DEG, planets), start=1):
        _spin(f"planet{i}_spin", carrier, planet, _planet_center(psi), _turns(_PLANET_DEG))
    _spin("rotor_spin", housing, rotor, (0, 0, 0), _turns(_ROTOR_DEG))
    _spin("rear_cage", bearings["rear"], balls_by_side["rear"], (0, 0, 0), _turns(_BALL_CAGE_DEG))
    _spin("front_cage", bearings["front"], balls_by_side["front"], (0, 0, 0), _turns(_BALL_CAGE_DEG))
    _spin("output", xroller, carrier, (0, 0, 0), _turns(_CARRIER_DEG))
    _spin("roller_cage", xroller, rollers, (0, 0, 0), _turns(_ROLLER_CAGE_DEG))
    # The old motion datums rotor_axis/output_axis are the rotor_spin/output joints.


def _drive(actuator: bd.Compound) -> None:
    """The drive train: one control in input revolutions gearing the rotor, the
    carrier, the cages and the planets at 4.5:1 (the old ``drive`` coupling), a
    constraint, as a gear train is: its joints turn only through it; and the old poses
    as its configurations ("rest" is as built)."""
    gear_pair(actuator, "drive", **_RATES)
    mechanism_state(actuator, "quarter_output", drive=_INPUT_TURNS / 4.0)
    mechanism_state(actuator, "full_output", drive=_INPUT_TURNS)


def _clips(actuator: bd.Compound) -> None:
    """The old ANIMATION_JS clips, by name (each looped there; a player repeats them):
    `drive` (12 s), a motion, sweeps the coupling over one closed cycle; `inspect` (12 s),
    an animation, runs the same cycle while the stack explodes with sin(pi * phase), the
    gears meshed at GEAR_CLUSTER; `teardown` (10 s), an animation, explodes every module to
    its own station and spreads the planets, no drive."""
    configuration_sequence(actuator, "drive", sweep={"drive": (0.0, _INPUT_TURNS)}, duration=12, ease="linear")
    _explode_animation(actuator, "inspect", 12, keep_mesh=True, drive=True)
    _explode_animation(actuator, "teardown", 10, keep_mesh=False, drive=False)


@model
def qdd_actuator():
    return build_actuator(explode=0.0)


if __name__ == "__main__":
    qdd_actuator()

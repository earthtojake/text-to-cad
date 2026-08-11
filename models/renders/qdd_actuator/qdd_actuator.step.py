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
"""

from __future__ import annotations

import math

from build123d import *  # noqa: F401,F403
from cadgen.assembly import AssemblyHelper

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
AL_BODY = Color(0.13, 0.135, 0.15)  # black-anodized housing
AL_COVER = Color(0.115, 0.12, 0.13)  # black-anodized rear cover
AL_BRIGHT = Color(0.78, 0.79, 0.81)  # machined aluminum (flange, carrier)
AL_RETAINER = Color(0.85, 0.20, 0.01)  # saturated anodized-orange accent ring
STEEL = Color(0.62, 0.63, 0.66)
STEEL_POLISHED = Color(0.76, 0.77, 0.79)
STEEL_RACE = Color(0.24, 0.25, 0.29)  # dark bearing-steel races vs aluminum
STEEL_ROLLER = Color(0.85, 0.86, 0.88)
LAMINATION = Color(0.30, 0.31, 0.34)
COPPER = Color(0.80, 0.45, 0.18)
ROTOR_DARK = Color(0.24, 0.25, 0.28)
MAGNET_N = Color(0.10, 0.10, 0.12)  # alternating pole colors: dark / nickel
MAGNET_S = Color(0.68, 0.69, 0.71)
FERRITE = Color(0.25, 0.08, 0.10)
PCB_GREEN = Color(0.05, 0.30, 0.14)
IC_BLACK = Color(0.08, 0.08, 0.09)
CAP_GRAY = Color(0.22, 0.24, 0.30)
PLASTIC_BLACK = Color(0.07, 0.07, 0.08)
GUNMETAL = Color(0.34, 0.35, 0.38)  # connector coupling nuts
PIN_GOLD = Color(0.80, 0.64, 0.25)  # connector contacts
BLACK_OXIDE = Color(0.20, 0.20, 0.22)  # socket-head fasteners
RUBBER = Color(0.04, 0.04, 0.04)
TITANIUM = Color(0.60, 0.59, 0.64)
GAUGE_GOLD = Color(0.85, 0.72, 0.35)
TUBE_BLACK = Color(0.32, 0.33, 0.35)  # dark gunmetal, reads against the cover

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


def _tube_z(outer_r: float, inner_r: float, z: tuple[float, float]) -> Part:
    """Annular ring solid between z[0]..z[1]."""
    return Pos(0, 0, z[0]) * extrude(Circle(outer_r) - Circle(inner_r), amount=z[1] - z[0])


def _cyl_z(r: float, z: tuple[float, float]) -> Part:
    return Pos(0, 0, z[0]) * extrude(Circle(r), amount=z[1] - z[0])


def _external_gear(teeth: int, root_r: float, tip_r: float, bore_r: float) -> Part:
    """Concept gear: root cylinder + trapezoidal teeth with visible backlash."""
    half_arc = math.pi * GEAR_MODULE / 2
    wt = half_arc * 0.34  # half-width at tip (thinned for visible backlash)
    wr = half_arc * 0.55  # half-width at root
    h = tip_r - root_r
    rm = (tip_r + root_r) / 2
    tooth = Polygon(
        (-h / 2 - 0.4, -wr), (h / 2, -wt), (h / 2, wt), (-h / 2 - 0.4, wr), align=None
    )
    teeth_sk = [loc * tooth for loc in PolarLocations(rm, teeth)]
    sketch = Circle(root_r) + teeth_sk - Circle(bore_r)
    return extrude(sketch, amount=GEAR_WIDTH)


def _internal_ring_gear() -> Part:
    """Internal ring gear with inward trapezoidal teeth and press-in rim."""
    half_arc = math.pi * GEAR_MODULE / 2
    wt = half_arc * 0.34
    wr = half_arc * 0.55
    h = RING_ROOT_R - RING_TIP_R
    rm = (RING_ROOT_R + RING_TIP_R) / 2
    # counter-clockwise point order so the face normal is +Z and the teeth
    # extrude in the same direction as the rim
    tooth = Polygon(
        (h / 2 + 0.4, -wr), (h / 2 + 0.4, wr), (-h / 2, wt), (-h / 2, -wt), align=None
    )
    teeth_sk = [loc * tooth for loc in PolarLocations(rm, RING_TEETH)]
    sketch = Circle(RING_RIM_R) - Circle(RING_ROOT_R) + teeth_sk
    return extrude(sketch, amount=GEAR_WIDTH)


def make_housing() -> Part:
    """Finned aluminum housing: barrel, rear wall, stator sleeve, standoffs."""
    barrel = _tube_z(BARREL_R[1], BARREL_R[0], BARREL_Z)
    rear_wall = _tube_z(REAR_WALL_R[1], REAR_WALL_R[0], REAR_WALL_Z)
    sleeve = _tube_z(SLEEVE_R[1], SLEEVE_R[0], SLEEVE_Z)

    fin = Box(
        FIN_RADIAL[1] - FIN_RADIAL[0] + 0.5,  # overlap into the barrel for fusing
        FIN_W,
        FIN_Z[1] - FIN_Z[0],
    )
    fin_loc = Pos((FIN_RADIAL[0] - 0.5 + FIN_RADIAL[1]) / 2, 0, (FIN_Z[0] + FIN_Z[1]) / 2)
    fins = [rot * (fin_loc * fin) for rot in PolarLocations(0, FIN_COUNT)]

    standoffs = []
    for az in ENC_STANDOFF_ANGLES:
        standoffs.append(
            Rotation(0, 0, az)
            * Pos(ENC_STANDOFF_CIRCLE_R, 0, 0)
            * _cyl_z(ENC_STANDOFF_R, ENC_STANDOFF_Z)
        )
    for az in DRV_STANDOFF_ANGLES:
        standoffs.append(
            Rotation(0, 0, az)
            * Pos(DRV_STANDOFF_CIRCLE_R, 0, 0)
            * _cyl_z(DRV_STANDOFF_R, DRV_STANDOFF_Z)
        )

    housing = barrel + [rear_wall, sleeve, *fins, *standoffs]

    cuts = []
    # 8x M3 retainer screw holes in the front barrel face
    for loc in PolarLocations(FRONT_SCREW_CIRCLE_R, FRONT_SCREW_COUNT, start_angle=22.5):
        cuts.append(loc * _cyl_z(1.7, (BARREL_Z[1] - 8.0, BARREL_Z[1] + 0.1)))
    # 8x M3 rear cover screw holes in the rear barrel face
    for loc in PolarLocations(REAR_SCREW_CIRCLE_R, REAR_SCREW_COUNT, start_angle=22.5):
        cuts.append(loc * _cyl_z(1.4, (BARREL_Z[0] - 0.1, BARREL_Z[0] + 5.0)))
    # 3x stator phase-wire passages through the rear wall
    for az in PHASE_WIRE_ANGLES:
        cuts.append(
            Rotation(0, 0, az)
            * Pos(PHASE_WIRE_CIRCLE_R, 0, 0)
            * _cyl_z(PHASE_WIRE_HOLE_R, (REAR_WALL_Z[0] - 0.1, REAR_WALL_Z[1] + 0.1))
        )
    return housing - cuts


def make_front_retainer() -> Part:
    """Bolted bearing retainer ring (makes the front stack assemblable)."""
    ring = _tube_z(RETAINER_R[1], RETAINER_R[0], RETAINER_Z)
    holes = [
        loc * _cyl_z(1.7, (RETAINER_Z[0] - 0.1, RETAINER_Z[1] + 0.1))
        for loc in PolarLocations(FRONT_SCREW_CIRCLE_R, FRONT_SCREW_COUNT, start_angle=22.5)
    ]
    return ring - holes


def make_retainer_screws() -> list[Part]:
    """8x M3 socket-head fasteners populating the retainer screw circle."""
    screws = []
    socket = extrude(RegularPolygon(RETAINER_SCREW_SOCKET_R, 6), amount=1.2)
    for loc in PolarLocations(FRONT_SCREW_CIRCLE_R, FRONT_SCREW_COUNT, start_angle=22.5):
        head = _cyl_z(
            RETAINER_SCREW_HEAD_R, (RETAINER_Z[1], RETAINER_Z[1] + RETAINER_SCREW_HEAD_H)
        )
        shank = _cyl_z(1.55, (RETAINER_Z[0] + 0.5, RETAINER_Z[1]))
        screw = (head + shank) - Pos(
            0, 0, RETAINER_Z[1] + RETAINER_SCREW_HEAD_H - 1.1
        ) * socket
        screws.append(loc * screw)
    return screws


def make_rear_cover() -> Part:
    """Sealed rear cover: plate, locating lip, tube boss, o-ring glands."""
    plate = _cyl_z(COVER_R, COVER_PLATE_Z)
    lip = _tube_z(COVER_LIP_R[1], COVER_LIP_R[0], COVER_LIP_Z)
    boss = _tube_z(COVER_BOSS_R[1], COVER_BOSS_R[0], COVER_BOSS_Z)
    cover = plate + [lip, boss]

    cuts = [_cyl_z(COVER_BOSS_R[0], (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[1] + 0.1))]
    # connector pass-throughs + o-ring glands on the rear face
    for name, az in CONNECTOR_ANGLES.items():
        hole_r = 5.0 if name == "power" else 4.0
        conn_loc = Rotation(0, 0, az) * Pos(CONNECTOR_CIRCLE_R, 0, 0)
        cuts.append(conn_loc * _cyl_z(hole_r, (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[1] + 0.1)))
        cuts.append(
            conn_loc
            * Pos(0, 0, COVER_PLATE_Z[0])
            * Torus(ORING_MAJOR_R * CONNECTOR_SCALE[name], ORING_GLAND_MINOR_R)
        )
    # 8x M3 counterbored cover screws
    for loc in PolarLocations(REAR_SCREW_CIRCLE_R, REAR_SCREW_COUNT, start_angle=22.5):
        cuts.append(loc * _cyl_z(1.7, (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[1] + 0.1)))
        cuts.append(loc * _cyl_z(3.0, (COVER_PLATE_Z[0] - 0.1, COVER_PLATE_Z[0] + 1.8)))
    return cover - cuts


def make_connector(kind: str) -> list[Part]:
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
    body = body - Pos(0, 0, z0) * Torus(ORING_MAJOR_R * scale, ORING_GLAND_MINOR_R)
    collar = Pos(0, 0, z0 - 9.0) * extrude(
        RegularPolygon(8.5 * scale, 12) - Circle(6.2 * scale), amount=2.5
    )
    o_ring = Pos(0, 0, z0) * Torus(ORING_MAJOR_R * scale, ORING_MINOR_R)
    pin_count = 4 if kind == "power" else 6
    pin_r = 0.8 * scale if kind == "power" else 0.55
    pins = Compound(
        children=[
            loc * _cyl_z(pin_r, (z0 - 9.7, z0 - 8.4))
            for loc in PolarLocations(2.6 * scale, pin_count)
        ]
    )
    loc = Rotation(0, 0, az) * Pos(CONNECTOR_CIRCLE_R, 0, 0)
    return [loc * body, loc * collar, loc * o_ring, loc * pins]


def make_driver_pcb() -> dict[str, object]:
    """Annular motor-driver PCB with FETs, bus capacitors, and MCU."""
    board = _tube_z(DRIVER_BOARD_R[1], DRIVER_BOARD_R[0], DRIVER_BOARD_Z)
    z_face = DRIVER_BOARD_Z[1]
    fets = []
    for i, loc in enumerate(PolarLocations(FET_CIRCLE_R, FET_COUNT, start_angle=15.0)):
        fets.append(
            loc * Pos(0, 0, z_face + FET_SIZE[2] / 2) * Box(FET_SIZE[0], FET_SIZE[1], FET_SIZE[2])
        )
    caps = [
        loc * Pos(0, 0, z_face + CAP_H / 2) * Cylinder(CAP_R, CAP_H)
        for loc in PolarLocations(CAP_CIRCLE_R, CAP_COUNT, start_angle=0.0)
    ]
    mcu = Pos(MCU_CENTER[0], MCU_CENTER[1], z_face + MCU_SIZE[2] / 2) * Box(*MCU_SIZE)
    return {"board": board, "fets": fets, "caps": caps, "mcu": mcu}


def make_encoder_pcb() -> dict[str, object]:
    """Encoder PCB behind the rotor magnet ring."""
    board = _tube_z(ENCODER_BOARD_R[1], ENCODER_BOARD_R[0], ENCODER_BOARD_Z)
    chip = Pos(
        ENCODER_CHIP_CENTER[0], ENCODER_CHIP_CENTER[1], ENCODER_BOARD_Z[1] + ENCODER_CHIP_SIZE[2] / 2
    ) * Box(*ENCODER_CHIP_SIZE)
    return {"board": board, "chip": chip}


def make_stator() -> dict[str, object]:
    """24-slot outrunner stator: laminated yoke/teeth and copper windings."""
    yoke = _tube_z(STATOR_YOKE_OR, STATOR_YOKE_IR, STATOR_STACK_Z)
    z_mid = (STATOR_STACK_Z[0] + STATOR_STACK_Z[1]) / 2
    stack_h = STATOR_STACK_Z[1] - STATOR_STACK_Z[0]

    tooth = Pos((STATOR_YOKE_OR - 0.5 + STATOR_TOOTH_TIP_R) / 2, 0, z_mid) * Box(
        STATOR_TOOTH_TIP_R - STATOR_YOKE_OR + 0.5, STATOR_TOOTH_W, stack_h
    )
    shoe = Pos((STATOR_SHOE_IR + STATOR_TOOTH_TIP_R) / 2, 0, z_mid) * Box(
        STATOR_TOOTH_TIP_R - STATOR_SHOE_IR, STATOR_SHOE_W, stack_h
    )
    tooth_unit = tooth + shoe
    teeth = [rot * tooth_unit for rot in PolarLocations(0, STATOR_SLOTS)]
    stack = yoke + teeth

    # one rectangular coil loop around a tooth, then a polar pattern of copies
    wind_r_mid = (WINDING_RADIAL[0] + WINDING_RADIAL[1]) / 2
    coil_outer = Pos(wind_r_mid, 0, z_mid) * Box(
        WINDING_RADIAL[1] - WINDING_RADIAL[0], WINDING_TANGENTIAL, WINDING_AXIAL
    )
    coil_hole = Pos(wind_r_mid, 0, z_mid) * Box(
        WINDING_RADIAL[1] - WINDING_RADIAL[0] + 1.0, WINDING_HOLE_TANGENTIAL, WINDING_HOLE_AXIAL
    )
    coil = coil_outer - coil_hole
    windings = [rot * coil for rot in PolarLocations(0, STATOR_SLOTS)]
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
    for loc in PolarLocations(28.0, 6, start_angle=30.0):
        cuts.append(loc * _cyl_z(5.0, (ROTOR_WEB_Z[0] - 0.1, ROTOR_WEB_Z[1] + 0.1)))
    # 4x M3 sun-gear coupling holes
    for loc in PolarLocations(COUPLING_HOLE_R, 4, start_angle=45.0):
        cuts.append(loc * _cyl_z(1.6, (ROTOR_FLANGE_Z[0] - 0.1, ROTOR_FLANGE_Z[1] + 0.1)))
    body = body - cuts

    z_mid = (MAGNET_Z[0] + MAGNET_Z[1]) / 2

    # Two independent prototypes so the alternating pole groups keep distinct
    # exported materials (copies of one shape share a single STEP style).
    def magnet_proto() -> Part:
        return Pos((MAGNET_IR + MAGNET_OR) / 2, 0, z_mid) * Box(
            MAGNET_OR - MAGNET_IR, MAGNET_W, MAGNET_Z[1] - MAGNET_Z[0]
        )

    north_proto, south_proto = magnet_proto(), magnet_proto()
    locs = list(PolarLocations(0, MAGNET_COUNT))
    magnets_north = [locs[i] * north_proto for i in range(0, MAGNET_COUNT, 2)]
    magnets_south = [locs[i] * south_proto for i in range(1, MAGNET_COUNT, 2)]
    return {"body": body, "magnets_north": magnets_north, "magnets_south": magnets_south}


def make_ball_bearing(z: tuple[float, float]) -> dict[str, object]:
    """Simplified deep-groove rotor support bearing: races + ball ring."""
    z_mid = (z[0] + z[1]) / 2
    ball_pitch_r = (ROTOR_BRG_IR[1] + ROTOR_BRG_OR[0]) / 2
    groove = Pos(0, 0, z_mid) * Torus(ball_pitch_r, ROTOR_BRG_BALL_R + 0.05)
    inner = _tube_z(ROTOR_BRG_IR[1], ROTOR_BRG_IR[0], z) - groove
    outer = _tube_z(ROTOR_BRG_OR[1], ROTOR_BRG_OR[0], z) - groove
    balls = [
        loc * Pos(0, 0, z_mid) * Sphere(ROTOR_BRG_BALL_R)
        for loc in PolarLocations(ball_pitch_r, ROTOR_BRG_BALL_COUNT)
    ]
    return {"inner": inner, "outer": outer, "balls": balls}


def make_sun_gear() -> Part:
    """Sun gear with hollow bore and rotor coupling flange."""
    gear = Pos(0, 0, GEAR_Z[0]) * _external_gear(SUN_TEETH, SUN_ROOT_R, SUN_TIP_R, TUBE_OUTER_R + 0.5)
    neck = _tube_z(SUN_ROOT_R, TUBE_OUTER_R + 0.5, (ROTOR_FLANGE_Z[1], GEAR_Z[0]))
    flange = _tube_z(15.0, TUBE_OUTER_R + 0.5, (ROTOR_FLANGE_Z[1], ROTOR_FLANGE_Z[1] + 1.5))
    sun = gear + [neck, flange]
    holes = [
        loc * _cyl_z(1.6, (ROTOR_FLANGE_Z[1] - 0.1, ROTOR_FLANGE_Z[1] + 1.6))
        for loc in PolarLocations(COUPLING_HOLE_R, 4, start_angle=45.0)
    ]
    return sun - holes


def make_planet_gear() -> Part:
    """One planet gear at the origin; placed with mesh-phase rotation."""
    return _external_gear(PLANET_TEETH, PLANET_ROOT_R, PLANET_TIP_R, PLANET_BORE_R)


def planet_location(psi_deg: float) -> Location:
    """Planet placement: position on the carrier circle plus mesh phasing.

    With sun/ring tooth patterns starting at azimuth 0, a tooth of each faces
    the planet center whenever psi is a multiple of the sun/ring angular pitch
    (true for 90/210/330 with 24 and 84 teeth). Rotating the planet by
    psi + half a planet tooth pitch puts a tooth gap on the line of centers.
    """
    phase = psi_deg + 180.0 / PLANET_TEETH
    px = PLANET_CENTER_R * math.cos(math.radians(psi_deg))
    py = PLANET_CENTER_R * math.sin(math.radians(psi_deg))
    return Pos(px, py, GEAR_Z[0]) * Rotation(0, 0, phase)


def make_carrier() -> Part:
    """Single-sided planet carrier: pins, plate, and torque-sensor hub."""
    plate = _tube_z(CARRIER_PLATE_R[1], CARRIER_PLATE_R[0], CARRIER_PLATE_Z)
    hub = _tube_z(CARRIER_HUB_R[1], CARRIER_HUB_R[0], CARRIER_HUB_Z)
    pins = [
        loc * _cyl_z(CARRIER_PIN_R, CARRIER_PIN_Z)
        for loc in PolarLocations(PLANET_CENTER_R, PLANET_COUNT, start_angle=90.0)
    ]
    carrier = plate + [hub, *pins]
    lighten = [
        Rotation(0, 0, az)
        * Pos(CARRIER_LIGHTEN_CIRCLE_R, 0, 0)
        * _cyl_z(CARRIER_LIGHTEN_HOLE_R, (CARRIER_PLATE_Z[0] - 0.1, CARRIER_PLATE_Z[1] + 0.1))
        for az in CARRIER_LIGHTEN_ANGLES
    ]
    return carrier - lighten


def make_cross_roller_bearing() -> dict[str, object]:
    """Cross-roller output bearing: V-groove races, alternating 45-deg rollers."""
    z_mid = (XROLLER_Z[0] + XROLLER_Z[1]) / 2
    groove_profile = Plane.XZ * (
        Pos(XROLLER_PITCH_R, z_mid) * Rotation(0, 0, 45) * Rectangle(XROLLER_GROOVE_SQ, XROLLER_GROOVE_SQ)
    )
    groove = revolve(groove_profile, axis=Axis.Z)
    inner = _tube_z(XROLLER_INNER_R[1], XROLLER_INNER_R[0], XROLLER_Z) - groove
    outer = _tube_z(XROLLER_OUTER_R[1], XROLLER_OUTER_R[0], XROLLER_Z) - groove

    rollers = []
    for i in range(XROLLER_COUNT):
        az = 360.0 * i / XROLLER_COUNT
        tilt = 45.0 if i % 2 == 0 else -45.0
        rollers.append(
            Rotation(0, 0, az)
            * Pos(XROLLER_PITCH_R, 0, z_mid)
            * Rotation(0, tilt, 0)
            * Cylinder(XROLLER_ROLLER_R, XROLLER_ROLLER_L)
        )
    return {"inner": inner, "outer": outer, "rollers": rollers}


def make_torque_sensor() -> dict[str, object]:
    """Spoked torque-sensing flexure with strain-gauge pads."""
    hub = _tube_z(FLEXURE_HUB_R[1], FLEXURE_HUB_R[0], FLEXURE_HUB_Z)
    rim = _tube_z(FLEXURE_RIM_R[1], FLEXURE_RIM_R[0], FLEXURE_RIM_Z)
    spoke_mid_r = (FLEXURE_HUB_R[1] + FLEXURE_RIM_R[0]) / 2
    spoke = Pos(spoke_mid_r, 0, (FLEXURE_SPOKE_Z[0] + FLEXURE_SPOKE_Z[1]) / 2) * Box(
        FLEXURE_SPOKE_L, FLEXURE_SPOKE_W, FLEXURE_SPOKE_Z[1] - FLEXURE_SPOKE_Z[0]
    )
    spokes = [rot * spoke for rot in PolarLocations(0, FLEXURE_SPOKE_COUNT)]
    flexure = hub + [rim, *spokes]
    gauges = [
        rot * Pos(spoke_mid_r, 0, GAUGE_Z + GAUGE_SIZE[2] / 2) * Box(*GAUGE_SIZE)
        for rot in PolarLocations(0, FLEXURE_SPOKE_COUNT)
    ]
    return {"flexure": flexure, "gauges": gauges}


def make_output_flange() -> Part:
    """Output flange: bolt circle, pilot boss, hollow bore."""
    plate = _tube_z(FLANGE_PLATE_R[1], FLANGE_PLATE_R[0], FLANGE_PLATE_Z)
    boss = _tube_z(FLANGE_BOSS_R[1], FLANGE_BOSS_R[0], FLANGE_BOSS_Z)
    flange = plate + boss
    cuts = [
        loc * _cyl_z(FLANGE_BOLT_R, (FLANGE_PLATE_Z[0] - 0.1, FLANGE_PLATE_Z[1] + 0.1))
        for loc in PolarLocations(FLANGE_BOLT_CIRCLE_R, FLANGE_BOLT_COUNT)
    ]
    cuts += [
        loc * _cyl_z(FLANGE_PILOT_HOLE_R, (FLANGE_PLATE_Z[0] + 0.5, FLANGE_BOSS_Z[1] + 0.1))
        for loc in PolarLocations(FLANGE_PILOT_CIRCLE_R, 4, start_angle=45.0)
    ]
    return flange - cuts


def make_cable_tube() -> Part:
    """Static hollow cable-routing tube through the full actuator stack."""
    return _tube_z(TUBE_OUTER_R, TUBE_INNER_R, TUBE_Z)


def build_actuator(explode: float = 0.0) -> Compound:
    """Build the labeled actuator assembly.

    explode=0 returns the assembled model with source mate frames/joints.
    explode>0 translates each part along Z by EXPLODE_OFFSETS * explode as a
    documented static exploded layout (joints are omitted in that mode).
    """
    asm = AssemblyHelper("qdd_actuator")

    housing = asm.add(make_housing(), "housing", color=AL_BODY)
    retainer = asm.add(make_front_retainer(), "front_retainer", color=AL_RETAINER)
    cover = asm.add(make_rear_cover(), "rear_cover", color=AL_COVER)

    screws = make_retainer_screws()
    retainer_screws = asm.add(
        Compound(children=screws), "retainer_screws", color=BLACK_OXIDE
    )

    connectors = {}
    for kind in CONNECTOR_ANGLES:
        body, collar, o_ring, pins = make_connector(kind)
        asm.feature(body, "connector_body", kind, color=PLASTIC_BLACK)
        asm.feature(collar, "connector_collar", kind, color=GUNMETAL)
        asm.feature(o_ring, "connector_o_ring", kind, color=RUBBER)
        asm.feature(pins, "connector_pins", kind, color=PIN_GOLD)
        connectors[kind] = asm.add_module("connector", [body, collar, o_ring, pins], kind)

    drv = make_driver_pcb()
    asm.feature(drv["board"], "driver_board", color=PCB_GREEN)
    for i, fet in enumerate(drv["fets"], start=1):
        asm.feature(fet, "fet", f"q{i}", color=IC_BLACK)
    for i, cap in enumerate(drv["caps"], start=1):
        asm.feature(cap, "bus_capacitor", f"c{i}", color=CAP_GRAY)
    asm.feature(drv["mcu"], "mcu", color=IC_BLACK)
    driver_pcb = asm.add_module(
        "driver_pcb", [drv["board"], *drv["fets"], *drv["caps"], drv["mcu"]]
    )

    enc = make_encoder_pcb()
    asm.feature(enc["board"], "encoder_board", color=PCB_GREEN)
    asm.feature(enc["chip"], "encoder_ic", color=IC_BLACK)
    encoder_pcb = asm.add_module("encoder_pcb", [enc["board"], enc["chip"]])

    enc_magnet = asm.add(
        _tube_z(ENC_MAGNET_R[1], ENC_MAGNET_R[0], ENC_MAGNET_Z),
        "encoder_magnet_ring",
        color=FERRITE,
    )

    st = make_stator()
    asm.feature(st["stack"], "lamination_stack", color=LAMINATION)
    winding_compound = asm.feature(Compound(children=st["windings"]), "windings", color=COPPER)
    stator = asm.add_module("stator", [st["stack"], winding_compound])

    rt = make_rotor()
    asm.feature(rt["body"], "rotor_bell", color=ROTOR_DARK)
    mag_n = asm.feature(Compound(children=rt["magnets_north"]), "magnets_north", color=MAGNET_N)
    mag_s = asm.feature(Compound(children=rt["magnets_south"]), "magnets_south", color=MAGNET_S)
    rotor = asm.add_module("rotor", [rt["body"], mag_n, mag_s])

    bearings = {}
    for name, z in (("rear", ROTOR_BRG_REAR_Z), ("front", ROTOR_BRG_FRONT_Z)):
        brg = make_ball_bearing(z)
        asm.feature(brg["inner"], "inner_race", name, color=STEEL_POLISHED)
        asm.feature(brg["outer"], "outer_race", name, color=STEEL_POLISHED)
        balls = asm.feature(Compound(children=brg["balls"]), "balls", name, color=STEEL_ROLLER)
        bearings[name] = asm.add_module(
            "rotor_bearing", [brg["inner"], brg["outer"], balls], name
        )

    sun = asm.add(make_sun_gear(), "sun_gear", color=STEEL)
    ring = asm.add(Pos(0, 0, GEAR_Z[0]) * _internal_ring_gear(), "ring_gear", color=STEEL)

    planet_proto = make_planet_gear()
    planets = []
    for i, psi in enumerate(PLANET_ANGLES_DEG, start=1):
        planet = planet_location(psi) * planet_proto
        planets.append(asm.add(planet, "planet_gear", f"p{i}", color=STEEL))

    carrier = asm.add(make_carrier(), "planet_carrier", color=AL_BRIGHT)

    xr = make_cross_roller_bearing()
    asm.feature(xr["inner"], "inner_ring", color=STEEL_RACE)
    asm.feature(xr["outer"], "outer_ring", color=STEEL_RACE)
    rollers = asm.feature(Compound(children=xr["rollers"]), "rollers", color=STEEL_ROLLER)
    xroller = asm.add_module("cross_roller_bearing", [xr["inner"], xr["outer"], rollers])

    ts = make_torque_sensor()
    asm.feature(ts["flexure"], "flexure_disc", color=TITANIUM)
    for i, gauge in enumerate(ts["gauges"], start=1):
        asm.feature(gauge, "strain_gauge", f"g{i}", color=GAUGE_GOLD)
    torque_sensor = asm.add_module("torque_sensor", [ts["flexure"], *ts["gauges"]])

    flange = asm.add(make_output_flange(), "output_flange", color=AL_BRIGHT)
    tube = asm.add(make_cable_tube(), "cable_tube", color=TUBE_BLACK)

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
                part.move(Location((0, 0, offset)))
        for psi, planet in zip(PLANET_ANGLES_DEG, planets):
            dx = PLANET_EXPLODE_RADIAL * explode * math.cos(math.radians(psi))
            dy = PLANET_EXPLODE_RADIAL * explode * math.sin(math.radians(psi))
            planet.move(Location((dx, dy, EXPLODE_OFFSETS["planet_gear"] * explode)))
    else:
        # Source mate frames + rigid connections (all identity by construction;
        # connect() re-derives placement from the named datums and records the
        # relationships for the exported topology).
        seat = asm.rigid_frame(housing, "stator_seat", Location((0, 0, STATOR_STACK_Z[0])))
        asm.face_to_face(seat, asm.rigid_frame(stator, "stack_rear", Location((0, 0, STATOR_STACK_Z[0]))))

        ring_seat = asm.rigid_frame(housing, "ring_gear_seat", Location((0, 0, GEAR_Z[0])))
        asm.face_to_face(ring_seat, asm.rigid_frame(ring, "rim_rear", Location((0, 0, GEAR_Z[0]))))

        cover_seat = asm.rigid_frame(housing, "cover_seat", Location((0, 0, BARREL_Z[0])))
        asm.face_to_face(cover_seat, asm.rigid_frame(cover, "lip_face", Location((0, 0, BARREL_Z[0]))))

        retainer_seat = asm.rigid_frame(housing, "retainer_seat", Location((0, 0, RETAINER_Z[0])))
        asm.face_to_face(
            retainer_seat, asm.rigid_frame(retainer, "ring_rear", Location((0, 0, RETAINER_Z[0])))
        )
        screw_seat = asm.rigid_frame(retainer, "screw_seats", Location((0, 0, RETAINER_Z[1])))
        asm.face_to_face(
            screw_seat,
            asm.rigid_frame(retainer_screws, "head_seats", Location((0, 0, RETAINER_Z[1]))),
        )

        for kind, module in connectors.items():
            az = math.radians(CONNECTOR_ANGLES[kind])
            mount = Location(
                (
                    CONNECTOR_CIRCLE_R * math.cos(az),
                    CONNECTOR_CIRCLE_R * math.sin(az),
                    COVER_PLATE_Z[0],
                )
            )
            pad = asm.rigid_frame(cover, f"{kind}_pad", mount)
            asm.face_to_face(pad, asm.rigid_frame(module, "mount_face", mount))

        for name, module, z_seat in (
            ("driver_pcb", driver_pcb, DRV_STANDOFF_Z[0]),
            ("encoder_pcb", encoder_pcb, ENC_STANDOFF_Z[0]),
        ):
            seat_frame = asm.rigid_frame(housing, f"{name}_seat", Location((0, 0, z_seat)))
            asm.face_to_face(
                seat_frame, asm.rigid_frame(module, "mount_plane", Location((0, 0, z_seat)))
            )

        coupling = asm.rigid_frame(rotor, "sun_coupling", Location((0, 0, ROTOR_FLANGE_Z[1])))
        asm.face_to_face(
            coupling, asm.rigid_frame(sun, "flange_rear", Location((0, 0, ROTOR_FLANGE_Z[1])))
        )
        magnet_seat = asm.rigid_frame(rotor, "encoder_magnet_seat", Location((0, 0, ENC_MAGNET_Z[0])))
        asm.face_to_face(
            magnet_seat,
            asm.rigid_frame(enc_magnet, "ring_rear", Location((0, 0, ENC_MAGNET_Z[0]))),
        )

        sensor_seat = asm.rigid_frame(carrier, "sensor_seat", Location((0, 0, FLEXURE_HUB_Z[0])))
        asm.face_to_face(
            sensor_seat,
            asm.rigid_frame(torque_sensor, "hub_rear", Location((0, 0, FLEXURE_HUB_Z[0]))),
        )
        rim_face = asm.rigid_frame(torque_sensor, "rim_face", Location((0, 0, FLEXURE_RIM_Z[1])))
        asm.face_to_face(
            rim_face, asm.rigid_frame(flange, "mount_rear", Location((0, 0, FLEXURE_RIM_Z[1])))
        )

        xr_seat = asm.rigid_frame(housing, "bearing_seat", Location((0, 0, XROLLER_Z[0])))
        asm.face_to_face(
            xr_seat, asm.rigid_frame(xroller, "outer_ring_rear", Location((0, 0, XROLLER_Z[0])))
        )

        tube_bore = asm.rigid_frame(cover, "tube_bore", Location((0, 0, COVER_PLATE_Z[0])))
        asm.face_to_face(
            tube_bore, asm.rigid_frame(tube, "rear_end", Location((0, 0, COVER_PLATE_Z[0])))
        )

        # Motion datums (joint frames only; static pose is authored explicitly):
        asm.revolute_frame(housing, "rotor_axis", Axis((0, 0, 0), (0, 0, 1)))
        asm.revolute_frame(housing, "output_axis", Axis((0, 0, XROLLER_Z[1]), (0, 0, 1)))

    return asm.build()


def gen_step():
    return {"shape": build_actuator(explode=0.0), "params": "qdd_actuator.params.js"}

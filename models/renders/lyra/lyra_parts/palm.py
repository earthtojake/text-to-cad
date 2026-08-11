"""lyra palm: wrist flange, carpal core, palm slab, knuckle row, thumb turret.

Local frame = robot root frame: origin at the wrist-flange mount face
center, +Z distal, +Y palmar, +X radial. The palm owns all MCP clevis
cheeks, knuckle pins, the thumb CMC turret pedestal/spindle, and the
tactile palm pad.

Articulation clearances baked into the shape:
- Knuckle slots are open from y -14 to +15 so proximal phalanges sweep
  -15..+95 deg without touching the covers.
- The palmar plate's top edge stays >= 8 mm proximal of each MCP axis,
  outside the swept envelope of the flexing proximal shaft.
- A 15 mm radius relief is turned around the thumb turret so the yawing
  thumb base clevis never clips the radial palm corner.
"""

from __future__ import annotations

from build123d import (
    Axis,
    Box,
    Plane,
    Polyline,
    Pos,
    Rot,
    RectangleRounded,
    extrude,
    loft,
    make_face,
)

from .chain import FINGERS, MCP_ORIGIN_MM, THUMB_CMC_ORIGIN_MM
from .digits import (
    FINGER_SCALE,
    MCP_PIN_R,
    PALM_LOBE_R,
    PROX_TANG_W,
    TB_TANG_R,
    TB_TANG_H,
)
from .lib import (
    ALU_COLOR,
    AMBER_COLOR,
    GRAPHITE_COLOR,
    PAD_COLOR,
    PEARL_COLOR,
    SENSOR_COLOR,
    part_compound,
    pin,
    safe_chamfer,
    safe_fillet,
    styled,
    xcyl,
    ycyl,
    zcyl,
)

SLAB_HALF_Y = 9.5          # graphite core half-depth
COVER_Y0, COVER_Y1 = -12.1, -9.5   # pearl dorsal cover
PLATE_Y0, PLATE_Y1 = 9.5, 11.5     # pearl palmar plate
MCP_PIN_LEN = 17.0

# Thumb turret (axis +Z through chain.THUMB_CMC_ORIGIN_MM).
TURRET_R = 10.5
TURRET_RELIEF_R = 15.0
SPINDLE_R = 2.7

CX, CY, CZ = THUMB_CMC_ORIGIN_MM

# Palm silhouette in the XZ plane (clockwise; +X radial, +Z distal). The
# knuckle arch follows the MCP line (index 99 / middle 103 / ring 99 /
# pinky 90); lobes added per knuckle crown above it.
CORE_PTS = [
    (-25.0, 33.0), (-33.0, 50.0), (-36.5, 72.0), (-36.5, 87.0),
    (-30.0, 90.0), (-19.0, 95.0), (-9.5, 99.0), (0.0, 101.0),
    (9.5, 103.0), (19.0, 101.0), (28.5, 99.0), (34.0, 97.5),
    (37.5, 95.5), (37.5, 70.0), (30.0, 46.0), (25.0, 33.0),
]
COVER_PTS = [
    (-23.5, 35.0), (-31.3, 51.0), (-34.8, 72.0), (-34.8, 85.6),
    (-29.0, 88.4), (-18.6, 93.0), (-9.5, 97.0), (0.0, 99.0),
    (9.5, 101.0), (18.6, 99.0), (28.5, 97.0), (33.0, 95.6),
    (35.8, 93.8), (35.8, 71.0), (28.6, 47.5), (23.4, 35.0),
]
PLATE_PTS = [
    (-23.5, 35.0), (-31.0, 51.0), (-34.5, 72.0), (-34.5, 80.0),
    (-28.6, 82.5), (-18.6, 86.0), (-9.5, 91.0), (0.0, 93.0),
    (9.5, 95.0), (19.0, 93.0), (28.5, 91.0), (35.5, 87.5),
    (35.5, 71.0), (28.6, 47.5), (23.4, 35.0),
]


def _outline_solid(pts, y0, depth):
    pts3 = [(x, y0, z) for x, z in pts]
    face = make_face(Polyline(*pts3, close=True))
    return extrude(face, amount=depth, dir=(0, 1, 0))


def _slot_gap(finger: str) -> float:
    return PROX_TANG_W * FINGER_SCALE[finger] + 0.7


def _knuckle_cuts(solid):
    """Open the four MCP clevis slots and pin bores in a palm solid."""
    for finger in FINGERS:
        kx, _, kz = MCP_ORIGIN_MM[finger]
        gap = _slot_gap(finger)
        solid -= Pos(kx, 0.5, kz + 2.0) * Box(gap, 29.0, 26.0)
        solid -= Pos(kx, 0, kz) * xcyl(MCP_PIN_R + 0.4, 26.0)
    return solid


def _thumb_relief(solid):
    """Turned clearance around the thumb turret for the yawing base clevis."""
    disc_z0 = CZ - TB_TANG_H / 2.0
    return solid - Pos(CX, CY, disc_z0 + 5.6) * zcyl(TURRET_RELIEF_R, 11.6)


def _wrist_flange():
    flange = Pos(0, 0, 3.0) * zcyl(23.0, 6.0)
    flange = safe_chamfer(flange, flange.edges(), 1.2)
    heads = []
    for i in range(6):
        from math import cos, pi, sin

        a = 2.0 * pi * i / 6.0
        bx, by = 16.5 * cos(a), 16.5 * sin(a)
        flange -= Pos(bx, by, 1.5) * zcyl(3.6, 3.0)
        flange -= Pos(bx, by, 3.0) * zcyl(2.3, 8.0)
        head = Pos(bx, by, 1.4) * zcyl(3.3, 2.2)
        head = safe_chamfer(head, head.edges(), 0.5)
        heads.append(styled(head, f"flange_bolt_{i}", GRAPHITE_COLOR))
    return styled(flange, "wrist_flange", ALU_COLOR), heads


def _carpal_core():
    try:
        f1 = Plane.XY.offset(6.0) * RectangleRounded(40.0, 17.5, 7.0)
        f2 = Plane.XY.offset(33.0) * RectangleRounded(50.0, 19.0, 8.0)
        carpal = loft([f1, f2])
    except Exception:
        carpal = Pos(0, 0, 19.5) * Box(46.0, 18.2, 27.0)
        carpal = safe_fillet(carpal, carpal.edges().filter_by(Axis.Z), 7.0)
    return styled(carpal, "carpal_core", GRAPHITE_COLOR)


def _palm_core():
    core = _outline_solid(CORE_PTS, -SLAB_HALF_Y, 2 * SLAB_HALF_Y)
    core = safe_fillet(core, core.edges().filter_by(Axis.Y), 2.2)

    # Knuckle lobe crowns (cut by the clevis slots into cheek arcs).
    for finger in FINGERS:
        kx, _, kz = MCP_ORIGIN_MM[finger]
        s = FINGER_SCALE[finger]
        core += Pos(kx, 0, kz) * xcyl(PALM_LOBE_R * s, _slot_gap(finger) + 7.0)

    # Thumb turret pedestal (bored for the spindle), merged into the
    # radial-palmar corner.
    disc_z0 = CZ - TB_TANG_H / 2.0
    pedestal = Pos(CX, CY, disc_z0 - 3.4) * (zcyl(TURRET_R, 6.4) - zcyl(SPINDLE_R + 0.7, 9.0))
    pedestal = safe_chamfer(pedestal, pedestal.edges(), 1.0)
    core += pedestal

    core = _knuckle_cuts(core)
    core = _thumb_relief(core)
    return styled(core, "palm_core", GRAPHITE_COLOR)


def _dorsal_cover():
    cover = _outline_solid(COVER_PTS, COVER_Y0, COVER_Y1 - COVER_Y0)
    cover = safe_fillet(cover, cover.edges().filter_by(Axis.Y), 2.0)
    try:
        outer = cover.faces().sort_by(Axis.Y)[0]
        cover = safe_chamfer(cover, outer.edges(), 1.0)
    except Exception:
        pass
    # Engraved tendon-channel lines running from the carpal exit to each
    # knuckle slot (clean covered cable routing, shown as shadow grooves).
    from math import atan2, degrees, hypot

    for finger in FINGERS:
        kx, _, kz = MCP_ORIGIN_MM[finger]
        ax, az = kx * 0.42, 40.0
        bx, bz = kx, kz - 12.0
        mx, mz = (ax + bx) / 2.0, (az + bz) / 2.0
        ang = degrees(atan2(bx - ax, bz - az))
        glen = hypot(bx - ax, bz - az)
        groove = Pos(mx, COVER_Y0 + 0.25, mz) * Rot(0, ang, 0) * Box(1.6, 1.0, glen)
        try:
            cover -= groove
        except Exception:
            pass
    cover = _knuckle_cuts(cover)
    cover = _thumb_relief(cover)
    return styled(cover, "dorsal_cover", PEARL_COLOR)


def _palmar_plate():
    plate = _outline_solid(PLATE_PTS, PLATE_Y0, PLATE_Y1 - PLATE_Y0)
    plate = safe_fillet(plate, plate.edges().filter_by(Axis.Y), 2.0)
    try:
        outer = plate.faces().sort_by(Axis.Y)[-1]
        plate = safe_chamfer(plate, outer.edges(), 0.8)
    except Exception:
        pass
    # Pocket for the tactile pad (pad sits 0.4 into the plate).
    plate -= Pos(0, PLATE_Y1, 65.0) * Box(46.4, 2.0, 30.4)
    plate = _knuckle_cuts(plate)
    plate = _thumb_relief(plate)
    return styled(plate, "palmar_plate", PEARL_COLOR)


def _palm_pad():
    pad = Pos(0, PLATE_Y1 - 0.4 + 0.85, 65.0) * Box(46.0, 1.7, 30.0)
    pad = safe_fillet(pad, pad.edges().filter_by(Axis.Y), 5.0)
    # Tactile zone split grooves (2 x 2 sensor array read as fine lines).
    for cut in (
        Pos(0, PLATE_Y1 + 1.3, 65.0) * Box(1.2, 1.0, 30.5),
        Pos(0, PLATE_Y1 + 1.3, 65.0) * Box(46.5, 1.0, 1.2),
    ):
        try:
            pad -= cut
        except Exception:
            pass
    pad = _thumb_relief(pad)
    return styled(pad, "palm_pad", PAD_COLOR)


def _palm_sensor():
    ring = Pos(0, PLATE_Y1 + 0.3, 87.0) * (ycyl(5.0, 0.6) - ycyl(4.0, 3.0))
    lens = Pos(0, PLATE_Y1 + 0.2, 87.0) * ycyl(3.9, 0.8)
    return [
        styled(ring, "palm_sensor_ring", AMBER_COLOR),
        styled(lens, "palm_sensor_lens", SENSOR_COLOR),
    ]


def _tensioners():
    """Tendon tensioner dial row on the dorsal carpal face."""
    out = []
    for i, dx in enumerate((-12.0, -6.0, 0.0, 6.0, 12.0)):
        face_y = -(8.75 + 0.75 * (20.0 - 6.0) / 27.0)
        dial = Pos(dx, face_y - 1.1, 20.0) * ycyl(2.6, 2.4)
        dial = safe_chamfer(dial, dial.edges(), 0.5)
        out.append(styled(dial, f"tensioner_dial_{i}", ALU_COLOR))
        dot = Pos(dx, face_y - 2.5, 20.0) * ycyl(1.0, 0.7)
        out.append(styled(dot, f"tensioner_dot_{i}", AMBER_COLOR))
    return out


def _knuckle_hardware():
    """Palm-owned MCP pins plus rim washers on the outer index/pinky cheeks."""
    out = []
    for finger in FINGERS:
        kx, _, kz = MCP_ORIGIN_MM[finger]
        out.append(
            styled(
                Pos(kx, 0, kz) * pin("x", MCP_PIN_R, MCP_PIN_LEN),
                f"{finger}_mcp_pin",
                ALU_COLOR,
            )
        )
    for finger, xr in (("index", 38.2), ("pinky", -37.2)):
        kx, _, kz = MCP_ORIGIN_MM[finger]
        rim = Pos(xr, 0, kz) * (xcyl(4.6, 1.2) - xcyl(MCP_PIN_R + 0.4, 3.0))
        out.append(styled(rim, f"{finger}_mcp_rim", ALU_COLOR))
    return out


def _turret_hardware():
    """Bearing collar + spindle/cap for the thumb CMC turret (palm side)."""
    disc_z0 = CZ - TB_TANG_H / 2.0
    disc_z1 = CZ + TB_TANG_H / 2.0
    collar = Pos(CX, CY, disc_z0 - 0.95) * (zcyl(TURRET_R + 0.7, 1.5) - zcyl(TB_TANG_R + 0.8, 3.0))
    collar = safe_chamfer(collar, collar.edges(), 0.4)
    spindle = Pos(CX, CY, (disc_z0 - 5.0 + disc_z1 + 0.4) / 2.0) * zcyl(
        SPINDLE_R, disc_z1 + 0.4 - (disc_z0 - 5.0)
    )
    cap = Pos(CX, CY, disc_z1 + 0.4 + 0.8) * zcyl(4.8, 1.6)
    cap = safe_chamfer(cap, cap.edges(), 0.5)
    spindle += cap
    return [
        styled(collar, "thumb_turret_collar", ALU_COLOR),
        styled(spindle, "thumb_turret_spindle", ALU_COLOR),
    ]


def build_palm():
    flange, bolt_heads = _wrist_flange()
    solids = [flange]
    solids += bolt_heads
    solids.append(_carpal_core())
    solids.append(_palm_core())
    solids.append(_dorsal_cover())
    solids.append(_palmar_plate())
    solids.append(_palm_pad())
    solids += _palm_sensor()
    solids += _tensioners()
    solids += _knuckle_hardware()
    solids += _turret_hardware()
    return part_compound("palm", solids)

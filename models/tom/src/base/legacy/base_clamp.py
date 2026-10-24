#!/usr/bin/env python3
"""Generate a bent base clamp that wraps under the base servo footprint.

Rev3 datums and helpers the rev4 stages still read; the standalone part model is in git history.

The upper plate stays in the servo base frame, a side wall rises from the
positive-x side, and a lower return closes the U so the part can clamp to a
desk or fixture from below.
"""

from __future__ import annotations

from lib.diag import say


from dataclasses import dataclass
import math
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = Path(__file__).resolve().parent


import build123d

from lib import corner_rules as cr
from lib import fastener_clearance as fc  # noqa: E402  (same reason)
from lib.materials import ALUMINUM_5052_COLOR


DISPLAY_NAME = "Base Clamp"
INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES = False
INCLUDE_RETURN_SURFACE_MOUNT_FEATURES = True
PLATE_THICKNESS_MM = 25.4 * 0.125
STANDARD_DESK_CLAMP_CLEARANCE_MM = 65.0
STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM = 33.5
SADDLE_FOOTPRINT_X_BUFFER_MM = 2.0
SIDE_WALL_THICKNESS_MM = PLATE_THICKNESS_MM
BOOLEAN_OVERLAP_MM = 0.05
CUT_EXTENSION_MM = 0.5
CORNER_RADIUS_MM = cr.BASE_CLAMP_CORNER_R_MM
# Was 1.6 -- Ø3.2, the CLOSE fit, where every other M3 in the repo is Ø3.4. It drills the servo horn's
# own bolt circle, and this variant currently cuts none of them (horn_m3_holes=0), so pointing it at
# the shared table changes no geometry today and stops the two sizes existing side by side.
M3_CLEARANCE_RADIUS_MM = fc.M3_CLEARANCE_RADIUS_MM
BASE_CENTER_HORN_FACE_RADIUS_MM = 2.8
BASE_CENTER_HORN_FACE_CLEARANCE_BUFFER_MM = 0.25
BASE_CENTER_HORN_FACE_CLEARANCE_RADIUS_MM = (
    BASE_CENTER_HORN_FACE_RADIUS_MM + BASE_CENTER_HORN_FACE_CLEARANCE_BUFFER_MM
)
# The clamp screw hole is TAPPED M8x1.25 (SendCutSend tapping service; ALU-125 supports up to
# M10x1.5 per sendcutsend-specs.json ALU-125 tapping_specs, fetched 2026-08-27), so the model
# carries the tap drill Ø6.8, not an M8 clearance bore. ~2.5 threads of engagement in 3.175 mm --
# adequate for a hand-tightened clamp screw -- and the screw threads straight into the return: no
# nut, no washer. Tapping rules guarded in build_bracket(): hole CL >= 13.132 mm (0.517 in) from
# the bend line, >= 6.248 mm (0.246 in) from every edge.
M8_TAP_DRILL_DIAMETER_MM = 6.8
M8_TAP_DRILL_RADIUS_MM = 0.5 * M8_TAP_DRILL_DIAMETER_MM
SENDCUTSEND_TAP_CL_TO_BEND_MIN_MM = 25.4 * 0.517
SENDCUTSEND_TAP_CL_TO_EDGE_MIN_MM = 25.4 * 0.246
SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM = 25.4 * 0.125
SENDCUTSEND_K_FACTOR = 0.44
SENDCUTSEND_HALF_DIE_WIDTH_MM = 0.5 * (25.4 * 0.630)
SENDCUTSEND_MIN_FLANGE_FORMED_MM = 25.4 * 0.476
SENDCUTSEND_BEND_RELIEF_DEPTH_MM = 25.4 * 0.270
SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM = 25.4 * 0.246
SENDCUTSEND_COUNTERSINK_CENTER_TO_BEND_MIN_MM = 25.4 * 0.517
SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM = 0.5
SENDCUTSEND_MOUNT_HOLE_TO_BEND_BUFFER_MM = 0.5
# Real bends, in the base plate's own material: 0.125in 5052 at k=0.44. These were 0.0, which
# modelled the part with SHARP corners -- fine as a placeholder, wrong as a thing to cut and fold.
# The fillet machinery below (see _apply_bend_radii) has always been wired for this; it was only
# ever switched off. Inner radius is the tooling's effective bend radius; the outer face is one
# material thickness further out.
BEND_INNER_RADIUS_MM = SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM
BEND_OUTER_RADIUS_MM = SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM + PLATE_THICKNESS_MM

# Base servo footprint bounds in robot-arm local coordinates.
SADDLE_BASE_FACE_Y_MM = -29.8002
SADDLE_BASE_X_MIN_MM = -35.61
SADDLE_BASE_X_MAX_MM = 6.338516
SADDLE_BASE_Z_MIN_MM = -15.960226
SADDLE_BASE_Z_MAX_MM = 15.960224

BASE_SERVO_FOOTPRINT_X_MIN_MM = SADDLE_BASE_X_MIN_MM - SADDLE_FOOTPRINT_X_BUFFER_MM
BASE_SERVO_FOOTPRINT_X_MAX_MM = SADDLE_BASE_X_MAX_MM + SADDLE_FOOTPRINT_X_BUFFER_MM
BASE_SERVO_SIDE_X_MIN_MM = BASE_SERVO_FOOTPRINT_X_MAX_MM - BOOLEAN_OVERLAP_MM
BASE_SERVO_SIDE_X_MAX_MM = BASE_SERVO_SIDE_X_MIN_MM + SIDE_WALL_THICKNESS_MM
BASE_SERVO_END_FOR_END_PIVOT_LOCAL_X_MM = 0.5 * (
    BASE_SERVO_FOOTPRINT_X_MIN_MM + BASE_SERVO_SIDE_X_MAX_MM
)
BASE_SERVO_END_FOR_END_PIVOT_LOCAL_Z_MM = 0.5 * (SADDLE_BASE_Z_MIN_MM + SADDLE_BASE_Z_MAX_MM)

# End-for-end flip of the base servo: a 180 deg rotation about the vertical axis through the servo
# body centre (the pivot above), which swings the output horn from one end of the case to the other.
# This is the single source of truth -- base_clamp_assembly.step.py reads it so the servo placement
# transform and this plate's mounting holes can never disagree about which way the servo faces.
# Set False to leave the servo in its imported orientation, horn toward the plate's far end.
APPLY_BASE_SERVO_END_FOR_END_FLIP = False

# Extra X offset for the whole servo. Kept at 0: the bus board's X origin is derived from the
# servo's mounted footprint, so translating the servo moves the board with it and does not change
# their clearance -- use SERVO_BUS_TO_SERVO_CLEARANCE_MM for that.
BASE_SERVO_EXTRA_X_OFFSET_MM = 0.0

# The plate was historically centred on the horn axis. That couples plate length to horn position
# at 2:1, which leaves the plate long and mostly empty once the servo is not centred on it.
CENTER_BASE_PLATE_ON_SERVO_HORN = False

SERVO_STANDOFF_HEIGHT_MM = 10.0
SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM = BASE_SERVO_FOOTPRINT_X_MIN_MM
BASE_PLATE_UNDER_ACCESS_CLEARANCE_MM = 5.0

# 5x M3 lower-horn clearance pattern on the base plate.
BASE_HORN_CONNECTION_HOLE_SPECS_MM: tuple[tuple[float, float, float], ...] = (
    (-32.5, 0.0, M3_CLEARANCE_RADIUS_MM),
    (-25.5, -7.0, M3_CLEARANCE_RADIUS_MM),
    (-25.5, 0.0, BASE_CENTER_HORN_FACE_CLEARANCE_RADIUS_MM),
    (-25.5, 7.0, M3_CLEARANCE_RADIUS_MM),
    (-18.5, 0.0, M3_CLEARANCE_RADIUS_MM),
)
BASE_SERVO_HORN_LOCAL_X_MM = -25.5

# Resolved from:
# @cad[STEP/imports/sts3250#o1.2.e920,o1.2.e922]
# @cad[STEP/imports/sts3250#o1.2.e921,o1.2.e923]
# Close-clearance diameters are shared with the arm brackets.
M2_CLEARANCE_RADIUS_MM = fc.M2_CLEARANCE_RADIUS_MM
# The four M2 standoff holes are COUNTERSUNK by SendCutSend, and their countersinking spec floors
# the pilot (minor) at 0.099 in = 2.515 mm -- above the plate's own M2 clearance. Ø2.6 is the ISO
# selected service pilot, 0.085 mm above the floor. Ordinary M2 through-holes
# elsewhere use fc's Ø2.2; the countersink pilot is a documented exception.
M2_CSK_PILOT_RADIUS_MM = 0.5 * 2.6
M2_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM = 2.15
# A 90-degree included angle has equal radial and axial runs.
M2_UNDERSIDE_COUNTERSINK_DEPTH_MM = (
    M2_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM - M2_CSK_PILOT_RADIUS_MM
)
# M2.5 close clearance: Ø2.7, from the shared policy.
M2_5_CLEARANCE_RADIUS_MM = fc.M2_5_CLEARANCE_RADIUS_MM
M2_5_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM = 2.5
M2_5_UNDERSIDE_COUNTERSINK_DEPTH_MM = 1.15
SERVO_BUS_STANDOFF_HEIGHT_MM = 6.0
BASE_SERVO_M2_HOLE_SPECS_MM: tuple[tuple[float, float, float], ...] = (
    (-17.2, -10.25, M2_CSK_PILOT_RADIUS_MM),
    (7.25, -10.25, M2_CSK_PILOT_RADIUS_MM),
    (-17.2, 10.25, M2_CSK_PILOT_RADIUS_MM),
    (7.25, 10.25, M2_CSK_PILOT_RADIUS_MM),
)
def base_servo_mounted_x_mm(local_x: float) -> float:
    """Map a servo-local X to its mounted X on the base plate.

    The under-access shift always applies -- it is what keeps the standoff screws clear of the
    lower return face so a driver can reach them, independent of which way the servo faces. Only
    the 180 deg rotation about the body-centre pivot is switched.
    """
    if not APPLY_BASE_SERVO_END_FOR_END_FLIP:
        return (
            local_x
            + SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM
            + BASE_SERVO_EXTRA_X_OFFSET_MM
        )
    return (
        (2.0 * BASE_SERVO_END_FOR_END_PIVOT_LOCAL_X_MM)
        - local_x
        + SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM
    )


def base_servo_mounted_z_mm(local_z: float) -> float:
    """Map a servo-local Z to its mounted Z on the base plate (see base_servo_mounted_x_mm)."""
    if not APPLY_BASE_SERVO_END_FOR_END_FLIP:
        return local_z
    return (2.0 * BASE_SERVO_END_FOR_END_PIVOT_LOCAL_Z_MM) - local_z


BASE_SERVO_STANDOFF_MOUNT_HOLES_MM: tuple[tuple[float, float, float], ...] = tuple(
    (
        base_servo_mounted_x_mm(x),
        base_servo_mounted_z_mm(z),
        # the COUNTERSUNK pilot, not the plain M2 clearance -- this derived list is what actually
        # drills the plate, and it silently reset the radius the spec list above chose
        M2_CSK_PILOT_RADIUS_MM,
    )
    for x, z, _radius in BASE_SERVO_M2_HOLE_SPECS_MM
)
# Map both footprint ends and re-sort: the flip reverses which local end becomes the mounted min.
_BASE_SERVO_MOUNTED_FOOTPRINT_XS = (
    base_servo_mounted_x_mm(BASE_SERVO_FOOTPRINT_X_MIN_MM),
    base_servo_mounted_x_mm(BASE_SERVO_FOOTPRINT_X_MAX_MM),
)
BASE_SERVO_MOUNTED_FOOTPRINT_X_MAX_MM = max(_BASE_SERVO_MOUNTED_FOOTPRINT_XS)
BASE_SERVO_MOUNTED_HORN_CENTER_X_MM = base_servo_mounted_x_mm(BASE_SERVO_HORN_LOCAL_X_MM)
BASE_ATTACHMENT_HOLES_MM: tuple[tuple[float, float, float], ...] = (
    BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
    + (
        BASE_HORN_CONNECTION_HOLE_SPECS_MM + BASE_SERVO_M2_HOLE_SPECS_MM
        if INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES
        else ()
    )
)

# Resolved from the four PCB mount holes of the Waveshare "Servo Driver with ESP32"
# (imports/servo_driver_with_esp32.step, official vendor model): Ø2.75 on a 58 x 23 mm pattern,
# board 65 x 30 mm. Measured off the model's cylinder axes 2026-08-27; matches the wiki's stated
# hole spacing. Convention (owner redirect 2026-08-27, board back on the TOP PLATE, CROSSWISE --
# the original morning orientation): bus_x (the 58 mm span) runs ACROSS the plate width (clamp z),
# centered on the plate z-centre; bus_y (the 23 mm span) runs ALONG the plate (clamp x). The strip
# width re-derives from this span plus countersink margins; the plate stays short lengthwise.
SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM: tuple[tuple[float, float], ...] = (
    (3.5, 3.5),
    (3.5, 26.5),
    (61.5, 3.5),
    (61.5, 26.5),
)
SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM = M2_5_CLEARANCE_RADIUS_MM
SERVO_BUS_MOUNT_LOCAL_X_MIN_MM = min(x for x, _y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM)
SERVO_BUS_MOUNT_LOCAL_X_MAX_MM = max(x for x, _y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM)
SERVO_BUS_MOUNT_LOCAL_X_CENTER_MM = 0.5 * (SERVO_BUS_MOUNT_LOCAL_X_MIN_MM + SERVO_BUS_MOUNT_LOCAL_X_MAX_MM)
# Width the top plate needs across z for the board's four COUNTERSUNK mounts, CROSSWISE: the
# 58 mm hole span (board local x) plus the countersink centre-to-edge rule AND the repo's
# standard buffer each side -- the full buffer fits again at this width, no spending needed.
BASE_CLAMP_SERVO_BUS_SPACER_WIDTH_MM = (
    (SERVO_BUS_MOUNT_LOCAL_X_MAX_MM - SERVO_BUS_MOUNT_LOCAL_X_MIN_MM)
    + (2.0 * (
        SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM
        + SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM
    ))
)

# The bus board is back on the TOP PLATE (owner revert 2026-08-27), so the wall carries no
# holes and the throat returns to the standard desk-clamp clearance -- nothing on the wall
# demands more any longer.
U_BRACKET_CLEARANCE_MM = STANDARD_DESK_CLAMP_CLEARANCE_MM

# Resolved from imports/servo_driver_with_esp32.step (bbox measured 2026-08-27). Local frame:
# PCB top at z=0, PCB bottom at z=-1.6; components reach +7.3 above the PCB (OLED, DC jack) and
# -3.9 below it (through-hole legs). The x<0 sliver is the DC jack overhanging the board edge.
SERVO_BUS_LOCAL_X_MIN_MM = -0.89
SERVO_BUS_LOCAL_X_MAX_MM = 65.0
SERVO_BUS_LOCAL_Y_MIN_MM = -0.5
SERVO_BUS_LOCAL_Y_MAX_MM = 30.01
# --- Bus board on the top plate, crosswise (owner redirect 2026-08-27) ---------------------------
# The board sits flat on the plate's top face on its four 6 mm hex standoffs, long axis ACROSS
# the plate, centred on the plate z-centre. Along the plate, the board occupies its 30.5 mm
# local-y extent starting one SERVO_BUS_TO_SERVO_CLEARANCE_MM past the servo footprint; the
# USB-C long edge (board local y=0) faces the FOLD end, away from the servo (owner call), which
# puts the DC jack (board local x=0 end) out the plate's +z side. Four M2.5 clearance holes,
# COUNTERSUNK on the plate's UNDERSIDE (table-contact face -- flat-heads flush).
SERVO_BUS_TO_SERVO_CLEARANCE_MM = 5.0
SERVO_BUS_TOP_BOARD_X_MIN_MM = (
    BASE_SERVO_MOUNTED_FOOTPRINT_X_MAX_MM + SERVO_BUS_TO_SERVO_CLEARANCE_MM
)
SERVO_BUS_TOP_BOARD_X_MAX_MM = SERVO_BUS_TOP_BOARD_X_MIN_MM + (
    SERVO_BUS_LOCAL_Y_MAX_MM - SERVO_BUS_LOCAL_Y_MIN_MM
)
BASE_PLATE_Z_CENTER_MM = 0.5 * (SADDLE_BASE_Z_MIN_MM + SADDLE_BASE_Z_MAX_MM)
# Mappings chosen so base_link can place the board with a single clean Rz(90) and every hole
# lands on its own plate hole: plate_x = X_MIN + (LOCAL_Y_MAX - bus_y)  (local y=0 edge, USB-C,
# lands at X_MAX, the fold end); plate_z = Z_CENTER - (bus_x - local x centre)  (the minus is the
# same identity-alignment trick as the lengthwise attempt; the drilled SET is symmetric anyway).
SERVO_BUS_TOP_MOUNT_HOLES_MM: tuple[tuple[float, float, float], ...] = tuple(
    (
        SERVO_BUS_TOP_BOARD_X_MIN_MM + (SERVO_BUS_LOCAL_Y_MAX_MM - bus_y),
        BASE_PLATE_Z_CENTER_MM - (bus_x - SERVO_BUS_MOUNT_LOCAL_X_CENTER_MM),
        SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM,
    )
    for bus_x, bus_y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM
)
BASE_ATTACHMENT_HOLES_MM = BASE_ATTACHMENT_HOLES_MM + SERVO_BUS_TOP_MOUNT_HOLES_MM
# The SQUARE SHOULDER's x position (owner 2026-08-27, superseding the straight-shot taper: "should
# be a straight edge, not slightly slanted"): the plate runs full width to here, then steps
# PERPENDICULARLY down to the contact-width neck, corners rounded. The edge sits just past the
# fold-nearest bus countersinks' centre-to-edge rule + buffer; the outer corner arcs curve away
# from the holes and the re-entrant arcs add material on the fold side, so the straight edge is
# the governing feature -- gen_step() re-measures the full rounded outline regardless.
# (Name kept from the taper iteration; it is the shoulder edge now.)
SERVO_BUS_TAPER_START_X_MM = max(
    x for x, _z, _r in SERVO_BUS_TOP_MOUNT_HOLES_MM
) + (
    SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM
    + SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM
)
# The neck starts after the last hardware on the TOP plate -- the bus board's far edge again.
TOP_PLATE_NECK_CLEARANCE_AFTER_BUS_MM = 2.0
TOP_PLATE_NECK_START_X_MM = (
    SERVO_BUS_TOP_BOARD_X_MAX_MM + TOP_PLATE_NECK_CLEARANCE_AFTER_BUS_MM
)
TOP_PLATE_NECK_TO_BEND_MIN_MM = SENDCUTSEND_BEND_RELIEF_DEPTH_MM + 2.0

# ONE FLUSH STRIP (owner request 2026-08-27): the whole clamp -- top plate, side wall, lower
# return -- runs at ONE width, fold ends square, far-end diagonals kept. The width itself is now
# DERIVED from the crosswise bus board (owner redirect 2026-08-27, superseding the earlier
# yoke-width 36.064 flush constant): the board's 58 mm hole span across the plate plus the full
# countersink centre-to-edge rule and standard buffer each side.
BASE_PLATE_Z_WIDTH_MM = BASE_CLAMP_SERVO_BUS_SPACER_WIDTH_MM
# The board's own silhouette (65.89 mm across, jack overhang included) must also sit on the strip
# with a whisker of edge margin; at the countersink-derived width this holds with real room.
_BOARD_SILHOUETTE_MIN_WIDTH_MM = (
    (SERVO_BUS_LOCAL_X_MAX_MM - SERVO_BUS_LOCAL_X_MIN_MM) + 2.0
)
if BASE_PLATE_Z_WIDTH_MM < _BOARD_SILHOUETTE_MIN_WIDTH_MM - 1e-6:
    raise RuntimeError(
        "Flush clamp width cannot cover the ESP32 board's silhouette: "
        f"{BASE_PLATE_Z_WIDTH_MM:.3f} mm < {_BOARD_SILHOUETTE_MIN_WIDTH_MM:.3f} mm"
    )
if BASE_PLATE_Z_WIDTH_MM < STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM - 1e-6:
    raise RuntimeError(
        "Flush clamp width is narrower than the desk-clamp contact width: "
        f"{BASE_PLATE_Z_WIDTH_MM:.3f} mm < {STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM:.3f} mm"
    )
# Case-retention slots are disabled: the five obround slots (2 side positions x 2 z sides, plus
# one 90deg end slot) are no longer cut from the top plate. The length/width constants below stay
# because _top_plate_outline_points() also uses them to size the plate's left flat and clamp-side
# edges, so the outline is unchanged by this switch.
INCLUDE_CASE_RETENTION_SLOTS = False
BASE_PLATE_HUB_SLOT_LENGTH_MM = 26.0
BASE_PLATE_HUB_SLOT_WIDTH_MM = 4.0
BASE_PLATE_HUB_SLOT_EDGE_INSET_MM = 5.5
BASE_PLATE_HUB_END_SLOT_X_INSET_MM = 6.0
BASE_PLATE_HUB_SIDE_SLOT_COUNT = 2
# The far end's two corners are cut off square on the diagonal rather than radiused. The size is
# NOT set here -- _end_chamfer_mm() solves for the largest 45 deg cut that still clears the mount
# holes, so the cut grows and shrinks with the plate instead of being a number that quietly stops
# being true. This caps it, in case the solve ever runs away on a much longer plate.
BASE_PLATE_END_CHAMFER_MAX_MM = 20.0
BASE_PLATE_MAIN_SURFACE_CENTER_X_MM = BASE_SERVO_MOUNTED_HORN_CENTER_X_MM
BASE_PLATE_LEFT_EDGE_EXTRA_INSET_MM = 0.0
# Sharp vertices on the ten-point outline. Since 2026-08-24 the FAR-end 45 deg diagonal-cut
# junctions go sharp: both ends of each far-end diagonal (0/9 and 7/8) are junction corners on a
# cut outline with no reachable touch hazard, so the cosmetic r3.0 rounds come off and the laser
# kerf (~0.13) is all the radius they get -- see DIAGONAL_END_CORNER_R_MM in link_plate.step.py.
# The SQUARE SHOULDER (owner 2026-08-27): the OUTER step corners 1 and 6 are rounded at
# CORNER_RADIUS_MM; the RE-ENTRANT shoulder-to-neck corners 2 and 5 go SHARP (owner follow-up the
# same day: recessed junction corners on a cut outline, laser kerf is all the radius they get --
# the same call as FLANGE_RELIEF_FILLET_MM = 0.0 in shoulder_yaw_yoke.step.py). Dropping their
# arcs also lets the fold come back in: no flat-neck run is needed ahead of the bend for an arc
# that no longer exists. 3 and 4 stay rounded as bend-end relief, as do the return flange's two
# end corners (rounded elsewhere off CORNER_RADIUS_MM).
BASE_PLATE_SHARP_NECK_CORNER_INDICES: tuple[int, ...] = (0, 2, 5, 7, 8, 9)


@dataclass(frozen=True)
class BracketLayout:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float
    clamp_z_min: float
    clamp_z_max: float
    end_chamfer_mm: float
    fold_chamfer_mm: float
    taper_start_x: float
    bend_tangent_x: float
    neck_start_x: float
    width: float
    height: float
    clamp_height: float
    return_width: float
    return_x_min: float
    return_y_min: float
    return_y_max: float
    side_x_min: float
    side_x_max: float
    overall_y_min: float
    face_y: float
    attachment_holes: tuple[tuple[float, float, float], ...]
    return_mount_holes: tuple[tuple[float, float, float], ...]
    servo_bus_mount_holes_xzr: tuple[tuple[float, float, float], ...]


def _make_box(
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_box(
        x_max - x_min,
        y_max - y_min,
        z_max - z_min,
        plane=build123d.Plane(origin=build123d.Vector(x_min, y_min, z_min)),
    )


def _make_xz_outline_solid(
    points_xz: tuple[tuple[float, float], ...],
    *,
    y_min: float,
    y_max: float,
) -> build123d.Shape:
    points_xyz = tuple((x, y_min, z) for x, z in points_xz)
    face = build123d.make_face(build123d.Polyline(*points_xyz, close=True))
    return build123d.extrude(face, amount=y_max - y_min, dir=(0.0, 1.0, 0.0))


def _make_cylinder_along(
    *,
    radius: float,
    height: float,
    origin: build123d.Vector,
    direction: build123d.Vector,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        height,
        plane=build123d.Plane(origin=origin, z_dir=direction),
    )


def _make_cone_along(
    *,
    base_radius: float,
    top_radius: float,
    height: float,
    origin: build123d.Vector,
    direction: build123d.Vector,
) -> build123d.Solid:
    return build123d.Solid.make_cone(
        base_radius,
        top_radius,
        height,
        plane=build123d.Plane(origin=origin, z_dir=direction),
    )


def _cast_shape(obj: object) -> build123d.Shape:
    from build123d.topology import downcast
    from build123d.topology.shape_core import shapetype

    occt_shape = downcast(obj)
    shape_name = build123d.Shape.shape_LUT[shapetype(occt_shape)]
    shape_type = getattr(build123d, shape_name)
    return shape_type.cast(occt_shape)


def _geom_type_name(shape: build123d.Shape) -> str:
    geom_type = shape.geom_type
    return geom_type.name if hasattr(geom_type, "name") else str(geom_type)


def _build_bracket_layout() -> BracketLayout:
    # The plate's far end comes from the servo standoff holes' countersink centre-to-edge envelope
    # ALONE (owner call 2026-08-27): the servo hangs on its four M2 standoffs, so it needs those
    # four holes, not plate under all of itself -- the case overhangs the shortened edge. The old
    # min() against BASE_SERVO_FOOTPRINT_X_MIN_MM kept the plate out at the full footprint, which
    # was ~13.7 mm of empty plate past the last fixing.
    x_min = min(
        x
        - SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM
        - SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM
        for x, _z, _radius in BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
    )
    x_max = BASE_SERVO_FOOTPRINT_X_MAX_MM
    if BASE_ATTACHMENT_HOLES_MM:
        required_x_max_for_mount_holes = max(
            x
            + SENDCUTSEND_COUNTERSINK_CENTER_TO_BEND_MIN_MM
            + SENDCUTSEND_MOUNT_HOLE_TO_BEND_BUFFER_MM
            for x, _z, _radius in BASE_ATTACHMENT_HOLES_MM
        )
        x_max = max(x_max, required_x_max_for_mount_holes)
    x_max = max(x_max, TOP_PLATE_NECK_START_X_MM + TOP_PLATE_NECK_TO_BEND_MIN_MM)
    # THIN OUT BEFORE THE BEND, SQUARE SHOULDER (owner 2026-08-27, third revision: "should be a
    # straight edge, not slightly slanted -- round the corners as well"): the plate runs at its
    # full countersink-derived width over the servo + board, then each side steps PERPENDICULARLY
    # down to the desk-clamp contact width at SERVO_BUS_TAPER_START_X_MM (the shoulder), and the
    # parallel neck runs into the bend. All four shoulder corners take CORNER_RADIUS_MM -- the
    # outer pair convex, the re-entrant pair filling the inside corner. The fold sits far enough
    # out that the re-entrant arc lands on flat neck, not in the bend zone (same x_max datum
    # convention as the neck term below). gen_step() re-measures the ROUNDED outline against
    # every countersunk mount with a hard guard. The FAR end keeps its solved 45 deg cuts.
    _plate_z_center = 0.5 * (SADDLE_BASE_Z_MIN_MM + SADDLE_BASE_Z_MAX_MM)
    _end_chamfer = _solve_end_chamfer(
        BASE_ATTACHMENT_HOLES_MM,
        x_min=x_min,
        z_min=_plate_z_center - (0.5 * BASE_PLATE_Z_WIDTH_MM),
        z_max=_plate_z_center + (0.5 * BASE_PLATE_Z_WIDTH_MM),
    )
    _fold_chamfer = 0.5 * (BASE_PLATE_Z_WIDTH_MM - STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM)
    # No shoulder-driven x_max term: with the re-entrant corners SHARP (owner follow-up
    # 2026-08-27) no arc needs flat neck ahead of the bend zone, so the plain neck rule above is
    # what places the fold.
    bend_tangent_x = x_max - BEND_INNER_RADIUS_MM - SIDE_WALL_THICKNESS_MM
    required_x_min = x_min
    if CENTER_BASE_PLATE_ON_SERVO_HORN:
        # Symmetric about the horn axis: x_min mirrors the neck across the horn. Note this makes
        # the plate grow by *twice* any horn movement, which is why it is off by default now that
        # the servo is no longer horn-centred on the plate.
        x_min = (
            (2.0 * BASE_PLATE_MAIN_SURFACE_CENTER_X_MM)
            - TOP_PLATE_NECK_START_X_MM
            + BASE_PLATE_LEFT_EDGE_EXTRA_INSET_MM
        )
        if x_min > required_x_min:
            raise RuntimeError(
                "Base plate main-surface centering would clip required geometry: "
                f"x_min={x_min:.3f} mm > required_x_min={required_x_min:.3f} mm"
            )
    else:
        # Size the plate to the hardware it actually carries: the servo footprint and its standoff
        # holes (required_x_min already carries the mount-hole edge buffer).
        x_min = required_x_min + BASE_PLATE_LEFT_EDGE_EXTRA_INSET_MM
    z_center = 0.5 * (SADDLE_BASE_Z_MIN_MM + SADDLE_BASE_Z_MAX_MM)
    z_min = z_center - (0.5 * BASE_PLATE_Z_WIDTH_MM)
    z_max = z_center + (0.5 * BASE_PLATE_Z_WIDTH_MM)
    # The bend, wall and return carry the CONTACT width: the square shoulder steps down to it at
    # SERVO_BUS_TAPER_START_X_MM, so everything from the shoulder onward is the narrow section.
    clamp_z_min = z_min + _fold_chamfer
    clamp_z_max = z_max - _fold_chamfer
    y_min = SADDLE_BASE_FACE_Y_MM - PLATE_THICKNESS_MM
    y_max = SADDLE_BASE_FACE_Y_MM
    return_y_max = y_min - U_BRACKET_CLEARANCE_MM
    return_y_min = return_y_max - PLATE_THICKNESS_MM
    side_x_max = x_max
    side_x_min = side_x_max - SIDE_WALL_THICKNESS_MM
    # The return stops short of the innermost servo-standoff countersink so a driver comes up
    # VERTICALLY at each of the four servo screws (owner reinstated 2026-08-27, superseding the
    # earlier equal-jaws waiver -- straight access is cheap again on the shortened plate). The
    # clamp screw's equidistant solve below tracks this edge, so the screw sits as deep as the
    # shortened return allows.
    return_x_min = (
        max(x for x, _z, _radius in BASE_SERVO_STANDOFF_MOUNT_HOLES_MM)
        + BASE_PLATE_UNDER_ACCESS_CLEARANCE_MM
    )
    # The clamp screw sits as deep under the table as it can while staying EQUIDISTANT from the
    # three edges around it -- the return's end edge and the two sides. Its distance from the desk
    # edge is the clamp's leverage, and the old midpoint-of-the-return position threw most of that
    # away: the hole was at x 2.685 when the return reached to -19.050.
    #
    # Equidistant makes the offset the clamp half-width, since the sides are that far off centre.
    # Pushing deeper than this buys leverage by moving the hole toward one edge and away from the
    # other two, which is where the surrounding material gets thin and starts to tear out under the
    # very load the leverage is for.
    return_mount_holes = (
        (
            return_x_min + (0.5 * (clamp_z_max - clamp_z_min)),
            0.5 * (clamp_z_min + clamp_z_max),
            # Tap drill for the TAPPED M8x1.25 clamp-screw hole -- see M8_TAP_DRILL_DIAMETER_MM.
            M8_TAP_DRILL_RADIUS_MM,
        ),
    ) if INCLUDE_RETURN_SURFACE_MOUNT_FEATURES else ()

    return BracketLayout(
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=z_min,
        z_max=z_max,
        clamp_z_min=clamp_z_min,
        clamp_z_max=clamp_z_max,
        end_chamfer_mm=_end_chamfer,
        fold_chamfer_mm=_fold_chamfer,
        taper_start_x=SERVO_BUS_TAPER_START_X_MM,
        bend_tangent_x=bend_tangent_x,
        neck_start_x=TOP_PLATE_NECK_START_X_MM,
        width=x_max - x_min,
        height=z_max - z_min,
        clamp_height=clamp_z_max - clamp_z_min,
        return_width=side_x_max - return_x_min,
        return_x_min=return_x_min,
        return_y_min=return_y_min,
        return_y_max=return_y_max,
        side_x_min=side_x_min,
        side_x_max=side_x_max,
        overall_y_min=return_y_min,
        face_y=y_max,
        attachment_holes=BASE_ATTACHMENT_HOLES_MM,
        return_mount_holes=return_mount_holes,
        servo_bus_mount_holes_xzr=SERVO_BUS_TOP_MOUNT_HOLES_MM,
    )


def _min_servo_bus_hole_center_to_plate_edge(layout: BracketLayout) -> float:
    if not SERVO_BUS_TOP_MOUNT_HOLES_MM:
        return math.inf
    return min(
        min(z - layout.z_min, layout.z_max - z)
        for _x, z, _radius in SERVO_BUS_TOP_MOUNT_HOLES_MM
    )


def _fillet_plan_corners(
    plate: build123d.Solid,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
    include_min_x: bool = True,
    include_max_x: bool = True,
) -> build123d.Shape:
    matches: list[build123d.Edge] = []
    for edge in plate.edges():
        if _geom_type_name(edge) != "LINE":
            continue
        bb = edge.bounding_box()
        if abs((bb.max.Y - bb.min.Y) - (y_max - y_min)) > 1e-3:
            continue
        if (bb.max.X - bb.min.X) > 1e-3 or (bb.max.Z - bb.min.Z) > 1e-3:
            continue
        center = edge.center()
        if abs(abs(center.X - ((x_min + x_max) * 0.5)) - ((x_max - x_min) * 0.5)) > 1e-3:
            continue
        if abs(abs(center.Z - ((z_min + z_max) * 0.5)) - ((z_max - z_min) * 0.5)) > 1e-3:
            continue
        at_min_x = abs(center.X - x_min) <= 1e-3
        at_max_x = abs(center.X - x_max) <= 1e-3
        if at_min_x and not include_min_x:
            continue
        if at_max_x and not include_max_x:
            continue
        matches.append(edge)

    expected_count = (2 if include_min_x else 0) + (2 if include_max_x else 0)
    if len(matches) != expected_count:
        raise RuntimeError(f"Expected {expected_count} plan-view corner edges to fillet, found {len(matches)}")

    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet

    mk = BRepFilletAPI_MakeFillet(plate.wrapped)
    for edge in matches:
        mk.Add(CORNER_RADIUS_MM, edge.wrapped)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("Failed to round U-bracket plate corners")
    return _cast_shape(mk.Shape())


def _fillet_plan_outline_vertices(
    plate: build123d.Shape,
    *,
    points_xz: tuple[tuple[float, float], ...],
    y_min: float,
    y_max: float,
    radius: float,
) -> build123d.Shape:
    matches: list[build123d.Edge] = []
    for edge in plate.edges():
        if _geom_type_name(edge) != "LINE":
            continue
        bb = edge.bounding_box()
        if abs((bb.max.Y - bb.min.Y) - (y_max - y_min)) > 1e-3:
            continue
        if (bb.max.X - bb.min.X) > 1e-3 or (bb.max.Z - bb.min.Z) > 1e-3:
            continue
        center = edge.center()
        if not any(
            abs(center.X - point_x) <= 1e-3 and abs(center.Z - point_z) <= 1e-3
            for point_x, point_z in points_xz
        ):
            continue
        matches.append(edge)

    if len(matches) != len(points_xz):
        raise RuntimeError(
            f"Expected {len(points_xz)} outline vertex edges to fillet, found {len(matches)}"
        )

    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet

    mk = BRepFilletAPI_MakeFillet(plate.wrapped)
    for edge in matches:
        mk.Add(radius, edge.wrapped)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("Failed to round top-plate outline")
    return _cast_shape(mk.Shape())


def _cut_y_holes(
    plate: build123d.Shape,
    *,
    holes_xzr: tuple[tuple[float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    hole_depth = (y_max - y_min) + (2.0 * CUT_EXTENSION_MM)
    for x, z, radius in holes_xzr:
        if not (x_min + radius <= x <= x_max - radius):
            raise RuntimeError(f"Hole at x={x:.3f} mm does not fit within the bracket x span")
        if not (z_min + radius <= z <= z_max - radius):
            raise RuntimeError(f"Hole at z={z:.3f} mm does not fit within the bracket z span")
        plate = plate.cut(
            _make_cylinder_along(
                radius=radius,
                height=hole_depth,
                origin=build123d.Vector(x, y_min - CUT_EXTENSION_MM, z),
                direction=build123d.Vector(0.0, 1.0, 0.0),
            )
        )
    return plate


def _cut_y_oriented_slots(
    plate: build123d.Shape,
    *,
    slots_xzlwr: tuple[tuple[float, float, float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    slot_depth = (y_max - y_min) + (2.0 * CUT_EXTENSION_MM)
    for x, z, length, width, rotation_deg in slots_xzlwr:
        if length <= width:
            raise RuntimeError(
                f"Slot length must exceed slot width, got {length:.3f} x {width:.3f} mm"
            )
        angle = math.radians(rotation_deg)
        unit_x = math.cos(angle)
        unit_z = math.sin(angle)
        perp_x = -unit_z
        perp_z = unit_x
        radius = 0.5 * width
        half_straight = 0.5 * (length - width)
        half_length = 0.5 * length
        projected_half_x = abs(unit_x) * half_length + abs(perp_x) * radius
        projected_half_z = abs(unit_z) * half_length + abs(perp_z) * radius
        if not (x_min + projected_half_x <= x <= x_max - projected_half_x):
            raise RuntimeError(f"Oriented slot at x={x:.3f} mm does not fit within the bracket x span")
        if not (z_min + projected_half_z <= z <= z_max - projected_half_z):
            raise RuntimeError(f"Oriented slot at z={z:.3f} mm does not fit within the bracket z span")

        rect_points = (
            (
                x - (half_straight * unit_x) - (radius * perp_x),
                z - (half_straight * unit_z) - (radius * perp_z),
            ),
            (
                x + (half_straight * unit_x) - (radius * perp_x),
                z + (half_straight * unit_z) - (radius * perp_z),
            ),
            (
                x + (half_straight * unit_x) + (radius * perp_x),
                z + (half_straight * unit_z) + (radius * perp_z),
            ),
            (
                x - (half_straight * unit_x) + (radius * perp_x),
                z - (half_straight * unit_z) + (radius * perp_z),
            ),
        )
        plate = plate.cut(
            _make_xz_outline_solid(
                rect_points,
                y_min=y_min - CUT_EXTENSION_MM,
                y_max=y_min - CUT_EXTENSION_MM + slot_depth,
            )
        )
        for sign in (-1.0, 1.0):
            plate = plate.cut(
                _make_cylinder_along(
                    radius=radius,
                    height=slot_depth,
                    origin=build123d.Vector(
                        x + (sign * half_straight * unit_x),
                        y_min - CUT_EXTENSION_MM,
                        z + (sign * half_straight * unit_z),
                    ),
                    direction=build123d.Vector(0.0, 1.0, 0.0),
                )
            )
    return plate


def _cut_base_plate_mount_features(
    plate: build123d.Shape,
    *,
    holes_xzr: tuple[tuple[float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    return _cut_y_holes(
        plate,
        holes_xzr=holes_xzr,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=z_min,
        z_max=z_max,
    )


def _cut_underside_countersinks(
    plate: build123d.Shape,
    *,
    holes_xzr: tuple[tuple[float, float, float], ...],
    y_min: float,
    clearance_radius: float,
    countersink_major_radius: float,
    countersink_depth: float,
) -> build123d.Shape:
    for x, z, radius in holes_xzr:
        if abs(radius - clearance_radius) > 1e-6:
            continue
        plate = plate.cut(
            _make_cone_along(
                base_radius=countersink_major_radius,
                top_radius=radius,
                height=countersink_depth,
                origin=build123d.Vector(x, y_min, z),
                direction=build123d.Vector(0.0, 1.0, 0.0),
            )
        )
    return plate


def _as_single_solid(shape: build123d.Shape) -> build123d.Solid:
    solids = list(shape.solids())
    if len(solids) != 1:
        raise RuntimeError(f"Expected a single solid, found {len(solids)}")
    return solids[0]


def _countersink_edge_reach() -> float:
    """Perpendicular clearance a countersink centre needs from a 45 deg cut, along x+z."""
    limit = (
        SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM
        + SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM
    )
    return limit * math.sqrt(2.0)


def _solve_end_chamfer(
    holes: tuple[tuple[float, float, float], ...],
    *,
    x_min: float,
    z_min: float,
    z_max: float,
) -> float:
    """The largest 45 deg corner cut at the FAR end that still clears every mount hole.

    Each cut is the line ``x +/- z = const``; a hole centre's distance to it is the perpendicular
    distance, hence the sqrt(2). Every hole is tested against both corners rather than the two
    obvious ones, so moving a hole pattern can only ever make the cut smaller, never silently push
    an edge through something.

    The holes are countersunk, so the limit is CENTRE-to-edge -- the same rule that sets the plate's
    width and its x_min. Both end up at the same clearance, which is what makes the far end fully
    determined: shrink either and one of them starts to bind.
    """
    if not holes:
        return 0.0
    reach = _countersink_edge_reach()
    return max(0.0, min(
        min((x + z) - (x_min + z_min) - reach for x, z, _r in holes),
        min((x - z) - (x_min - z_max) - reach for x, z, _r in holes),
        BASE_PLATE_END_CHAMFER_MAX_MM,
    ))


def _fold_shoulder_outline_clearance(
    holes: tuple[tuple[float, float, float], ...],
    *,
    shoulder_x: float,
    bend_tangent_x: float,
    z_min: float,
    z_max: float,
    clamp_z_min: float,
    clamp_z_max: float,
    corner_radius: float,
) -> tuple[float, tuple[float, float]]:
    """Min distance from any hole centre to the ROUNDED square-shoulder outline.

    Owner 2026-08-27 ("straight edge, not slanted -- round the corners", then same-day follow-up
    sharpening the re-entrant pair): the fold-end boundary per side is wide z-edge -> convex
    outer arc -> perpendicular shoulder edge -> SHARP re-entrant corner -> neck edge into the
    bend. This samples that exact boundary (the outer arcs are the same CORNER_RADIUS_MM arcs
    _fillet_plan_outline_vertices cuts; the re-entrant corners carry no arc) so the guard
    measures the final geometry, not an idealised line. Returns (min_distance, governing_hole_xz).
    """
    samples: list[tuple[float, float]] = []

    def _arc(cx: float, cz: float, start_deg: float, end_deg: float) -> None:
        steps = 24
        for i in range(steps + 1):
            a = math.radians(start_deg + (end_deg - start_deg) * (i / steps))
            samples.append((cx + corner_radius * math.cos(a), cz + corner_radius * math.sin(a)))

    def _seg(p1: tuple[float, float], p2: tuple[float, float]) -> None:
        steps = max(2, int(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / 0.25))
        for i in range(steps + 1):
            t = i / steps
            samples.append((p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t))

    for sign, z_edge, neck_z in ((1.0, z_max, clamp_z_max), (-1.0, z_min, clamp_z_min)):
        # Wide z-edge up to the outer arc's tangent point.
        _seg((shoulder_x - 4.0 * corner_radius, z_edge), (shoulder_x - corner_radius, z_edge))
        # Convex outer corner: centre one radius inboard of both edges.
        _arc(shoulder_x - corner_radius, z_edge - sign * corner_radius,
             90.0 if sign > 0 else -90.0, 0.0)
        # The perpendicular shoulder edge from the outer arc's tangent point down to the SHARP
        # re-entrant corner (owner follow-up 2026-08-27: no arc there).
        _seg((shoulder_x, z_edge - sign * corner_radius), (shoulder_x, neck_z))
        # Neck edge from the sharp corner to the bend tangent.
        _seg((shoulder_x, neck_z), (bend_tangent_x, neck_z))

    best = math.inf
    governing = (math.nan, math.nan)
    for x, z, _r in holes:
        for sx, sz in samples:
            dist = math.hypot(x - sx, z - sz)
            if dist < best:
                best = dist
                governing = (x, z)
    return best, governing


def _top_plate_outline_points(layout: BracketLayout) -> tuple[tuple[float, float], ...]:
    """The plate outline: full width in the middle, cut at both ends -- differently.

    Ten points. The far corners take the solved 45 deg end chamfer that clears the servo-mount
    countersinks; the fold end takes the SQUARE SHOULDER (owner 2026-08-27): a perpendicular
    straight edge at taper_start_x stepping the full width down to the contact-width neck, which
    then runs parallel into the bend. All four shoulder vertices (1, 2, 5, 6) are rounded at
    CORNER_RADIUS_MM by _fillet_plan_outline_vertices.
    """
    chamfer = layout.end_chamfer_mm
    fold_chamfer = layout.fold_chamfer_mm
    if chamfer <= 0.0 and fold_chamfer <= 0.0:
        return (
            (layout.x_min, layout.z_min),
            (layout.x_max, layout.z_min),
            (layout.x_max, layout.z_max),
            (layout.x_min, layout.z_max),
        )
    return (
        (layout.x_min + chamfer, layout.z_min),
        (layout.taper_start_x, layout.z_min),
        (layout.taper_start_x, layout.clamp_z_min),
        (layout.x_max, layout.clamp_z_min),
        (layout.x_max, layout.clamp_z_max),
        (layout.taper_start_x, layout.clamp_z_max),
        (layout.taper_start_x, layout.z_max),
        (layout.x_min + chamfer, layout.z_max),
        (layout.x_min, layout.z_max - chamfer),
        (layout.x_min, layout.z_min + chamfer),
    )


def _top_plate_hub_slot_specs(layout: BracketLayout) -> tuple[tuple[float, float, float, float, float], ...]:
    if not INCLUDE_CASE_RETENTION_SLOTS:
        return ()
    outline_points = _top_plate_outline_points(layout)
    side_start_x = outline_points[0][0]
    side_end_x = layout.neck_start_x
    side_span = side_end_x - side_start_x
    side_slot_gap = (
        side_span - (BASE_PLATE_HUB_SIDE_SLOT_COUNT * BASE_PLATE_HUB_SLOT_LENGTH_MM)
    ) / (BASE_PLATE_HUB_SIDE_SLOT_COUNT + 1)
    if side_slot_gap <= BASE_PLATE_HUB_SLOT_WIDTH_MM:
        raise RuntimeError(
            "Side case-retention slots cannot be evenly spaced with the current "
            f"edge span: {side_span:.3f} mm"
        )
    slot_z_abs = (0.5 * layout.height) - BASE_PLATE_HUB_SLOT_EDGE_INSET_MM
    side_slot_xs = tuple(
        side_start_x
        + side_slot_gap
        + (0.5 * BASE_PLATE_HUB_SLOT_LENGTH_MM)
        + (index * (BASE_PLATE_HUB_SLOT_LENGTH_MM + side_slot_gap))
        for index in range(BASE_PLATE_HUB_SIDE_SLOT_COUNT)
    )
    slots: list[tuple[float, float, float, float, float]] = []
    for slot_x in side_slot_xs:
        for slot_z in (-slot_z_abs, slot_z_abs):
            slots.append(
                (
                    slot_x,
                    slot_z,
                    BASE_PLATE_HUB_SLOT_LENGTH_MM,
                    BASE_PLATE_HUB_SLOT_WIDTH_MM,
                    0.0,
                )
            )
    slots.append(
        (
            layout.x_min + BASE_PLATE_HUB_END_SLOT_X_INSET_MM,
            0.5 * (layout.z_min + layout.z_max),
            BASE_PLATE_HUB_SLOT_LENGTH_MM,
            BASE_PLATE_HUB_SLOT_WIDTH_MM,
            90.0,
        )
    )
    return tuple(slots)


def _make_lower_plate(layout: BracketLayout) -> build123d.Shape:
    outline_points = _top_plate_outline_points(layout)
    plate = _make_xz_outline_solid(
        outline_points,
        y_min=layout.y_min,
        y_max=layout.y_max,
    )
    rounded_outline_points = tuple(
        point
        for index, point in enumerate(outline_points)
        if index not in BASE_PLATE_SHARP_NECK_CORNER_INDICES
    )
    plate = _fillet_plan_outline_vertices(
        plate,
        points_xz=rounded_outline_points,
        y_min=layout.y_min,
        y_max=layout.y_max,
        radius=CORNER_RADIUS_MM,
    )
    plate = _cut_base_plate_mount_features(
        plate,
        holes_xzr=layout.attachment_holes,
        x_min=layout.x_min,
        x_max=layout.x_max,
        y_min=layout.y_min,
        y_max=layout.y_max,
        z_min=layout.z_min,
        z_max=layout.z_max,
    )
    plate = _cut_y_oriented_slots(
        plate,
        slots_xzlwr=_top_plate_hub_slot_specs(layout),
        x_min=layout.x_min,
        x_max=layout.x_max,
        y_min=layout.y_min,
        y_max=layout.y_max,
        z_min=layout.z_min,
        z_max=layout.z_max,
    )
    # MATCH THE PILOT RADIUS, not M2 clearance: BASE_SERVO_STANDOFF_MOUNT_HOLES_MM carries
    # M2_CSK_PILOT_RADIUS_MM (see its definition -- "this derived list is what actually drills the
    # plate"), and _cut_underside_countersinks skips any hole whose radius differs from the value
    # passed here. Passing M2_CLEARANCE_RADIUS_MM made the filter skip all four holes, so the part
    # built with NO underside countersinks while the print line still echoed the countersink
    # constants. Found by measuring the built solid (zero cone faces), 2026-08-27.
    plate = _cut_underside_countersinks(
        plate,
        holes_xzr=BASE_SERVO_STANDOFF_MOUNT_HOLES_MM,
        y_min=layout.y_min,
        clearance_radius=M2_CSK_PILOT_RADIUS_MM,
        countersink_major_radius=M2_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM,
        countersink_depth=M2_UNDERSIDE_COUNTERSINK_DEPTH_MM,
    )
    # Bus-board M2.5 mounts, back on the plate (owner revert 2026-08-27). The stored radius and
    # the clearance_radius passed here are the SAME constant, so the filter above cannot silently
    # skip these -- the lesson from the M2 regression. gen_step() verifies by counting cone faces.
    plate = _cut_underside_countersinks(
        plate,
        holes_xzr=layout.servo_bus_mount_holes_xzr,
        y_min=layout.y_min,
        clearance_radius=SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM,
        countersink_major_radius=M2_5_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM,
        countersink_depth=M2_5_UNDERSIDE_COUNTERSINK_DEPTH_MM,
    )
    return _as_single_solid(plate)


def _make_return_plate(layout: BracketLayout) -> build123d.Shape:
    plate = _make_box(
        x_min=layout.return_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.return_y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
    )
    plate = _fillet_plan_corners(
        plate,
        x_min=layout.return_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.return_y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
        include_min_x=True,
        include_max_x=False,
    )
    plate = _cut_y_holes(
        plate,
        holes_xzr=layout.return_mount_holes,
        x_min=layout.return_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.return_y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
    )
    return _as_single_solid(plate)


def _make_side_wall(layout: BracketLayout) -> build123d.Shape:
    return _make_box(
        x_min=layout.side_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
    )


def _long_z_edges_near(
    shape: build123d.Shape,
    *,
    x: float,
    y: float,
    z_min: float,
    z_max: float,
    tolerance: float = 0.08,
) -> build123d.ShapeList:
    matches = build123d.ShapeList()
    min_length = 0.8 * (z_max - z_min)
    for edge in shape.edges():
        if _geom_type_name(edge) != "LINE":
            continue
        bb = edge.bounding_box()
        if (bb.max.X - bb.min.X) > 1e-3 or (bb.max.Y - bb.min.Y) > 1e-3:
            continue
        if (bb.max.Z - bb.min.Z) < min_length:
            continue
        center = edge.center()
        if abs(center.X - x) > tolerance or abs(center.Y - y) > tolerance:
            continue
        matches.append(edge)
    return matches


def _apply_sendcutsend_bend_radii(
    bracket: build123d.Shape,
    *,
    layout: BracketLayout,
) -> build123d.Shape:
    if BEND_INNER_RADIUS_MM < 0.0 or BEND_OUTER_RADIUS_MM < 0.0:
        raise ValueError("Bend radii must be >= 0")
    if BEND_INNER_RADIUS_MM == 0.0 and BEND_OUTER_RADIUS_MM == 0.0:
        return bracket

    inner_bend_edges = build123d.ShapeList()
    for bend_y in (layout.y_min, layout.return_y_max):
        inner_bend_edges.extend(
            _long_z_edges_near(
                bracket,
                x=layout.side_x_min,
                y=bend_y,
                z_min=layout.clamp_z_min,
                z_max=layout.clamp_z_max,
            )
        )
    if len(inner_bend_edges) != 2:
        raise RuntimeError(f"Expected two inside bend edges to fillet, found {len(inner_bend_edges)}")

    if BEND_INNER_RADIUS_MM > 0.0:
        bracket = bracket.fillet(BEND_INNER_RADIUS_MM, inner_bend_edges)

    outer_bend_edges = build123d.ShapeList()
    for bend_y in (layout.y_max, layout.return_y_min):
        outer_bend_edges.extend(
            _long_z_edges_near(
                bracket,
                x=layout.side_x_max,
                y=bend_y,
                z_min=layout.clamp_z_min,
                z_max=layout.clamp_z_max,
                tolerance=0.25,
            )
        )
    if len(outer_bend_edges) != 2:
        raise RuntimeError(f"Expected two outside bend edges to fillet, found {len(outer_bend_edges)}")

    if BEND_OUTER_RADIUS_MM > 0.0:
        bracket = bracket.fillet(BEND_OUTER_RADIUS_MM, outer_bend_edges)

    return bracket


def build_bracket() -> build123d.Solid:
    layout = _build_bracket_layout()
    hub_slot_specs = _top_plate_hub_slot_specs(layout)
    # Vertical driver access to the four servo standoff screws: the return must stop at least
    # the access clearance short of the innermost countersink. Hard failure (owner reinstated
    # 2026-08-27).
    standoff_under_access_clearance = layout.return_x_min - max(
        x for x, _z, _radius in BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
    )
    if standoff_under_access_clearance < BASE_PLATE_UNDER_ACCESS_CLEARANCE_MM - 1e-6:
        raise RuntimeError(
            "Base servo standoff holes are too close to the lower return face for "
            f"driver access: {standoff_under_access_clearance:.3f} mm < "
            f"{BASE_PLATE_UNDER_ACCESS_CLEARANCE_MM:.3f} mm"
        )
    # Tapped M8 clamp-screw hole: SendCutSend tapping rules, hard failures. The return's flat
    # ends one inner bend radius before the wall (x = side_x_min - r_in); edges are the return's
    # end and the two chamfered sides.
    tap_margins = []
    for hole_x, hole_z, _radius in layout.return_mount_holes:
        tap_cl_to_bend = (layout.side_x_min - BEND_INNER_RADIUS_MM) - hole_x
        tap_cl_to_edge = min(
            hole_x - layout.return_x_min,
            hole_z - layout.clamp_z_min,
            layout.clamp_z_max - hole_z,
        )
        tap_margins.append((tap_cl_to_bend, tap_cl_to_edge))
        if tap_cl_to_bend < SENDCUTSEND_TAP_CL_TO_BEND_MIN_MM:
            raise RuntimeError(
                "Tapped M8 clamp-screw hole is too close to the return's bend line: "
                f"{tap_cl_to_bend:.3f} mm < {SENDCUTSEND_TAP_CL_TO_BEND_MIN_MM:.3f} mm"
            )
        if tap_cl_to_edge < SENDCUTSEND_TAP_CL_TO_EDGE_MIN_MM:
            raise RuntimeError(
                "Tapped M8 clamp-screw hole is too close to a return edge: "
                f"{tap_cl_to_edge:.3f} mm < {SENDCUTSEND_TAP_CL_TO_EDGE_MIN_MM:.3f} mm"
            )

    # The rounded square-shoulder outline vs EVERY countersunk mount: the sampled boundary
    # (shoulder edge + corner arcs + adjacent flats, exactly what the fillets cut) must keep the
    # countersink centre-to-edge rule + buffer. The shoulder x was chosen for exactly this; the
    # guard re-measures the final rounded geometry regardless.
    _taper_reach = (
        SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM
        + SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM
    )
    taper_clearance, taper_governing = _fold_shoulder_outline_clearance(
        BASE_ATTACHMENT_HOLES_MM,
        shoulder_x=layout.taper_start_x,
        bend_tangent_x=layout.bend_tangent_x,
        z_min=layout.z_min,
        z_max=layout.z_max,
        clamp_z_min=layout.clamp_z_min,
        clamp_z_max=layout.clamp_z_max,
        corner_radius=CORNER_RADIUS_MM,
    )
    if taper_clearance < _taper_reach - 1e-6:
        raise RuntimeError(
            "A countersunk mount sits too close to the shoulder outline: "
            f"{taper_clearance:.3f} mm < {_taper_reach:.3f} mm at hole "
            f"({taper_governing[0]:.3f}, {taper_governing[1]:.3f})"
        )

    # The strip width is derived to give the bus countersinks exactly rule + buffer of edge
    # clearance, so the hard guard sits at the RAW rule (guarding at rule+buffer would trip on
    # its own float noise); the print reports the achieved value against both.
    servo_bus_countersink_edge_clearance = _min_servo_bus_hole_center_to_plate_edge(layout)
    _bus_csk_edge_min = SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM
    if servo_bus_countersink_edge_clearance < _bus_csk_edge_min:
        raise RuntimeError(
            "Servo bus countersunk holes are too close to the plate edge: "
            f"{servo_bus_countersink_edge_clearance:.3f} mm < "
            f"{_bus_csk_edge_min:.3f} mm"
        )

    bracket = _make_lower_plate(layout)
    bracket = _as_single_solid(bracket.fuse(_make_side_wall(layout)))
    bracket = _as_single_solid(bracket.fuse(_make_return_plate(layout)))
    bracket = _as_single_solid(_apply_sendcutsend_bend_radii(bracket, layout=layout))
    # The side wall is a blank flush panel again -- the bus board went back to the top plate
    # (owner revert 2026-08-27), taking its four wall holes with it.

    say(
        f"{DISPLAY_NAME}: "
        f"lower_width={layout.width:.3f} mm, "
        f"return_width={layout.return_width:.3f} mm, "
        f"plate_width={layout.height:.3f} mm (= crosswise bus-board span + csk rule + buffer), "
        f"contact_width={layout.clamp_z_max - layout.clamp_z_min:.3f} mm at bend/wall/return, "
        f"square_shoulder x={layout.taper_start_x:.3f} (perpendicular edge, outer corners "
        f"r{CORNER_RADIUS_MM:.1f}, re-entrant corners SHARP, "
        f"neck {layout.taper_start_x:.3f}..{layout.bend_tangent_x:.3f}, "
        f"csk_outline_clearance={taper_clearance:.3f} min {_taper_reach:.3f} "
        f"governing hole ({taper_governing[0]:.3f}, {taper_governing[1]:.3f})), "
        f"far_end_chamfer={layout.end_chamfer_mm:.3f} mm, "
        f"plate_thickness={PLATE_THICKNESS_MM:.3f} mm, "
        f"clearance={U_BRACKET_CLEARANCE_MM:.3f} mm, "
        f"overall_y_min={layout.overall_y_min:.4f} mm, "
        f"top_surface_holes={len(layout.attachment_holes)}, "
        f"bottom_surface_holes={len(layout.return_mount_holes)}, "
        f"horn_m3_holes={len(BASE_HORN_CONNECTION_HOLE_SPECS_MM) if INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES else 0}, "
        f"m2_mount_holes={len(BASE_SERVO_M2_HOLE_SPECS_MM) if INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES else 0}, "
        f"m2_standoff_mount_holes={len(BASE_SERVO_STANDOFF_MOUNT_HOLES_MM)}, "
        f"m2_standoff_height={SERVO_STANDOFF_HEIGHT_MM:.3f} mm, "
        f"m2_plate_clearance_diameter={2.0 * M2_CLEARANCE_RADIUS_MM:.3f} mm, "
        f"m2_countersink_major_diameter={2.0 * M2_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM:.3f} mm, "
        f"m2_under_access_clearance={standoff_under_access_clearance:.3f} mm, "
        f"return_mount_holes={len(layout.return_mount_holes)}x tapped M8x1.25 "
        f"(drill Ø{2.0 * M8_TAP_DRILL_RADIUS_MM:.1f}, "
        + ", ".join(
            f"cl_to_bend={b:.3f} (min {SENDCUTSEND_TAP_CL_TO_BEND_MIN_MM:.3f}) "
            f"cl_to_edge={e:.3f} (min {SENDCUTSEND_TAP_CL_TO_EDGE_MIN_MM:.3f})"
            for b, e in tap_margins
        )
        + "), "
        f"servo_bus_top_holes={len(layout.servo_bus_mount_holes_xzr)}, "
        f"case_retention_slots={len(hub_slot_specs)}x"
        f"{BASE_PLATE_HUB_SLOT_LENGTH_MM:.3f}x{BASE_PLATE_HUB_SLOT_WIDTH_MM:.3f} mm, "
        f"case_retention_slot_centers={[(round(slot[0], 3), round(slot[1], 3)) for slot in hub_slot_specs]}, "
        f"servo_bus_standoff_height={SERVO_BUS_STANDOFF_HEIGHT_MM:.3f} mm, "
        f"servo_bus_plate_clearance_diameter={2.0 * SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM:.3f} mm, "
        f"servo_bus_on_plate=crosswise x {SERVO_BUS_TOP_BOARD_X_MIN_MM:.3f}.."
        f"{SERVO_BUS_TOP_BOARD_X_MAX_MM:.3f} (USB-C toward fold, jack out +z side), "
        f"M2.5 underside countersinks, "
        f"servo_bus_csk_center_to_edge={servo_bus_countersink_edge_clearance:.3f} mm "
        f"(rule {_bus_csk_edge_min:.3f} + buffer "
        f"{SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM:.3f}), "
        f"neck_to_bend_min={TOP_PLATE_NECK_TO_BEND_MIN_MM:.3f} mm, "
        f"bend_radii_inner_outer=({BEND_INNER_RADIUS_MM:.3f}, {BEND_OUTER_RADIUS_MM:.3f}) mm, "
        f"horn_center_x={BASE_SERVO_MOUNTED_HORN_CENTER_X_MM:.3f} mm, "
        f"flush_y={layout.face_y:.4f} mm"
    )
    bracket.color = ALUMINUM_5052_COLOR
    return bracket


def base_clamp():
    # Floor-up presentation. The bracket is AUTHORED on its side -- the saddle plane is a Y level,
    # which is the frame every layout constant, the flat pattern and build_dxf() live in -- but the
    # PART stands on a table edge. The entry shape is rotated upright (Rx +90) with the underside
    # of the lower return on z=0: the same floor frame base_link.step.py's clamp stack is authored
    # in, which is why that assembly places this part at identity.
    layout = _build_bracket_layout()
    bracket = build_bracket()
    upright = bracket.moved(
        build123d.Location((0.0, 0.0, -layout.overall_y_min), (90.0, 0.0, 0.0))
    )
    upright.label = getattr(bracket, "label", "") or "base_clamp"
    if getattr(bracket, "color", None) is not None:
        upright.color = bracket.color
    return upright

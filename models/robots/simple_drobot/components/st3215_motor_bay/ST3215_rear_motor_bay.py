"""Reusable rear-body bay for a Feetech/Waveshare ST3215 servo.

The printable bay is intentionally independent of any limb.  Its flat
attachment datum is the outer face at X=0, and the bay extends toward negative
X.  A future limb can import ``gen_step()`` and fuse that face to its own
geometry without copying the fit-critical servo cavity.

Coordinate convention:
    - Units are millimeters.
    - The attachment datum is the YZ plane at X=0.
    - The servo inserts from the open negative-X end.
    - Servo local X follows global X, local Z follows global -Y, and servo
      local Y follows global +Z.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Align, Box, Cylinder, Location, Shape, import_step


ST3215_SERVO_STEP = (
    Path(__file__).parents[3]
    / "lekiwi_quadruped"
    / "components"
    / "waveshare_feetech_st3215_servo.step"
)

# Dimensions inspected from the exact step.parts catalog model.
ST3215_CATALOG_HEIGHT_Y_MM = 37.8
ST3215_CATALOG_WIDTH_Z_MM = 24.7234
ST3215_CATALOG_MAX_X_MM = 9.6117

# Fit parameters. These are preliminary FDM test-fit allowances, not final
# production tolerances.
SOCKET_CLEARANCE_Y_PER_SIDE_MM = 0.25
SOCKET_CLEARANCE_Z_TOTAL_MM = 0.25
SOCKET_WALL_MM = 3.0
SOCKET_LENGTH_X_MM = 16.0
SOCKET_STOP_THICKNESS_MM = 1.5
BOOLEAN_OVERTRAVEL_MM = 0.6

# The stop is a perimeter rim, leaving this opening for the servo cable.
SOCKET_CABLE_WINDOW_Y_MM = 16.0
SOCKET_CABLE_WINDOW_Z_MM = 14.0

# Four vertical access holes expose the ST3215 mounting positions visible in
# the left/right projections.  Their 20.5 mm spacing agrees with the
# manufacturer drawing; the staggered X locations come from the exact STEP.
SERVO_MOUNT_HOLE_Y_SPACING_MM = 20.5
SERVO_TOP_MOUNT_HOLE_X_MM = -6.8117
SERVO_BOTTOM_MOUNT_HOLE_X_MM = -3.0617
SERVO_MOUNT_THROUGH_DIAMETER_MM = 2.0
SERVO_MOUNT_COUNTERBORE_DIAMETER_MM = 4.0
SERVO_MOUNT_INNER_PILOT_DEPTH_MM = 2.8
# Construction clearance erases the imported servo's reverse-imprinted holes;
# concentric sleeves added afterward establish the smaller finished diameters.
SERVO_MOUNT_PROFILE_CLEARANCE_DIAMETER_MM = 5.4
SERVO_MOUNT_LOCAL_CLEANUP_SIZE_MM = 6.0
SERVO_TOP_MOUNT_FACE_Z_MM = 19.025
SERVO_BOTTOM_MOUNT_FACE_Z_MM = -19.025
SERVO_TOP_ACCESS_REACH_Z_MM = 14.0
SERVO_BOTTOM_ACCESS_REACH_Z_MM = -13.0

# Public datum: the outer flat face used to attach this bay to another part.
ATTACHMENT_DATUM_X_MM = 0.0


def st3215_installed_location() -> Location:
    """Return the exact catalog servo pose seated against the stop rim."""
    stop_x = ATTACHMENT_DATUM_X_MM - SOCKET_STOP_THICKNESS_MM
    translation_x = stop_x - ST3215_CATALOG_MAX_X_MM

    # The source servo's asymmetric local-Y bounds are -28.2 to +9.6 mm.
    # After the +90-degree X rotation, this centers it in global Z while
    # shifting it by half the total vertical clearance.
    translation_z = 9.3 + SOCKET_CLEARANCE_Z_TOTAL_MM / 2.0
    return Location((translation_x, 0.0, translation_z), (90.0, 0.0, 0.0))


def _largest_connected_solid(shape: Shape, operation: str) -> Shape:
    """Keep the connected bay when source-servo holes leave isolated pins."""
    solids = list(shape.solids())
    if not solids:
        raise RuntimeError(f"{operation} removed the entire motor bay")
    return max(solids, key=lambda solid: float(solid.volume))


def _servo_mount_access_cutters(
    outer_z: float,
    overtravel: float,
) -> list[Shape]:
    """Build temporary clearance cutters that erase reverse imprints."""
    spacing_y = float(SERVO_MOUNT_HOLE_Y_SPACING_MM)
    clearance_diameter = float(SERVO_MOUNT_PROFILE_CLEARANCE_DIAMETER_MM)
    top_access_reach_z = float(SERVO_TOP_ACCESS_REACH_Z_MM)
    bottom_access_reach_z = float(SERVO_BOTTOM_ACCESS_REACH_Z_MM)
    outer_top_z = outer_z / 2.0
    outer_bottom_z = -outer_top_z

    if min(spacing_y, clearance_diameter) <= 0.0:
        raise ValueError("Mount-hole dimensions must be positive")
    if not (
        outer_bottom_z
        < bottom_access_reach_z
        < top_access_reach_z
        < outer_top_z
    ):
        raise ValueError("Mount-hole reach limits must lie inside the bay")

    cutters = []
    for y in (-spacing_y / 2.0, spacing_y / 2.0):
        cutters.append(
            Cylinder(
                clearance_diameter / 2.0,
                outer_top_z + overtravel - top_access_reach_z,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            ).moved(
                Location((SERVO_TOP_MOUNT_HOLE_X_MM, y, top_access_reach_z))
            )
        )
        cutters.append(
            Cylinder(
                clearance_diameter / 2.0,
                bottom_access_reach_z - (outer_bottom_z - overtravel),
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            ).moved(
                Location(
                    (
                        SERVO_BOTTOM_MOUNT_HOLE_X_MM,
                        y,
                        outer_bottom_z - overtravel,
                    )
                )
            )
        )
    return cutters


def _servo_mount_local_access_cleanup(
    inner_y: float,
    cavity_min_x: float,
    cavity_max_x: float,
) -> list[Shape]:
    """Clear four local mount pockets, preserving surrounding fitting grooves."""
    spacing_y = float(SERVO_MOUNT_HOLE_Y_SPACING_MM)
    cleanup_size = float(SERVO_MOUNT_LOCAL_CLEANUP_SIZE_MM)
    top_mount_face_z = float(SERVO_TOP_MOUNT_FACE_Z_MM)
    bottom_mount_face_z = float(SERVO_BOTTOM_MOUNT_FACE_Z_MM)
    top_access_reach_z = float(SERVO_TOP_ACCESS_REACH_Z_MM)
    bottom_access_reach_z = float(SERVO_BOTTOM_ACCESS_REACH_Z_MM)
    top_cleanup_depth = top_mount_face_z - top_access_reach_z
    bottom_cleanup_depth = bottom_access_reach_z - bottom_mount_face_z
    cavity_span_x = cavity_max_x - cavity_min_x

    if min(
        inner_y,
        top_cleanup_depth,
        bottom_cleanup_depth,
        cleanup_size,
        cavity_span_x,
    ) <= 0.0:
        raise ValueError("Local cleanup dimensions must be positive")

    top_clip = Box(
        cavity_span_x,
        inner_y,
        top_cleanup_depth,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).moved(
        Location(
            (
                (cavity_min_x + cavity_max_x) / 2.0,
                0.0,
                top_access_reach_z,
            )
        )
    )
    bottom_clip = Box(
        cavity_span_x,
        inner_y,
        bottom_cleanup_depth,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).moved(
        Location(
            (
                (cavity_min_x + cavity_max_x) / 2.0,
                0.0,
                bottom_mount_face_z,
            )
        )
    )

    cleanup_cutters = []
    for y in (-spacing_y / 2.0, spacing_y / 2.0):
        top_local = Box(
            cleanup_size,
            cleanup_size,
            top_cleanup_depth,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_TOP_MOUNT_HOLE_X_MM,
                    y,
                    top_access_reach_z,
                )
            )
        )
        cleanup_cutters.append(top_local & top_clip)

        bottom_local = Box(
            cleanup_size,
            cleanup_size,
            bottom_cleanup_depth,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_BOTTOM_MOUNT_HOLE_X_MM,
                    y,
                    bottom_mount_face_z,
                )
            )
        )
        cleanup_cutters.append(bottom_local & bottom_clip)
    return cleanup_cutters


def _add_servo_mount_step_sleeves(
    bay: Shape,
    outer_z: float,
    overtravel: float,
) -> Shape:
    """Restore only the intended diameter-4/diameter-2 paths after cleanup."""
    spacing_y = float(SERVO_MOUNT_HOLE_Y_SPACING_MM)
    pilot_radius = float(SERVO_MOUNT_THROUGH_DIAMETER_MM) / 2.0
    access_radius = float(SERVO_MOUNT_COUNTERBORE_DIAMETER_MM) / 2.0
    clearance_radius = float(SERVO_MOUNT_PROFILE_CLEARANCE_DIAMETER_MM) / 2.0
    pilot_depth = float(SERVO_MOUNT_INNER_PILOT_DEPTH_MM)
    top_mount_face_z = float(SERVO_TOP_MOUNT_FACE_Z_MM)
    bottom_mount_face_z = float(SERVO_BOTTOM_MOUNT_FACE_Z_MM)
    top_access_reach_z = float(SERVO_TOP_ACCESS_REACH_Z_MM)
    bottom_access_reach_z = float(SERVO_BOTTOM_ACCESS_REACH_Z_MM)
    outer_top_z = outer_z / 2.0
    outer_bottom_z = -outer_top_z
    radial_overlap = 0.05

    if not 0.0 < pilot_radius < access_radius < clearance_radius:
        raise ValueError("Mount sleeve radii must increase from pilot to clearance")
    if top_mount_face_z - pilot_depth <= top_access_reach_z:
        raise ValueError("Top pilot step exceeds the cleaned cavity reach")
    if bottom_mount_face_z + pilot_depth >= bottom_access_reach_z:
        raise ValueError("Bottom pilot step exceeds the cleaned cavity reach")

    sleeves = []
    for y in (-spacing_y / 2.0, spacing_y / 2.0):
        top_access_outer = Cylinder(
            clearance_radius + radial_overlap,
            outer_top_z - top_mount_face_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location((SERVO_TOP_MOUNT_HOLE_X_MM, y, top_mount_face_z))
        )
        top_access_inner = Cylinder(
            access_radius,
            outer_top_z + 2.0 * overtravel - top_mount_face_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_TOP_MOUNT_HOLE_X_MM,
                    y,
                    top_mount_face_z - overtravel,
                )
            )
        )
        top_pilot_outer = Cylinder(
            access_radius + radial_overlap,
            pilot_depth,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_TOP_MOUNT_HOLE_X_MM,
                    y,
                    top_mount_face_z - pilot_depth,
                )
            )
        )
        top_pilot_inner = Cylinder(
            pilot_radius,
            pilot_depth + 2.0 * overtravel,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_TOP_MOUNT_HOLE_X_MM,
                    y,
                    top_mount_face_z - pilot_depth - overtravel,
                )
            )
        )
        sleeves.append(
            (top_access_outer - top_access_inner).fuse(
                top_pilot_outer - top_pilot_inner
            )
        )

        bottom_access_outer = Cylinder(
            clearance_radius + radial_overlap,
            bottom_mount_face_z - outer_bottom_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_BOTTOM_MOUNT_HOLE_X_MM,
                    y,
                    outer_bottom_z,
                )
            )
        )
        bottom_access_inner = Cylinder(
            access_radius,
            bottom_mount_face_z - outer_bottom_z + 2.0 * overtravel,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_BOTTOM_MOUNT_HOLE_X_MM,
                    y,
                    outer_bottom_z - overtravel,
                )
            )
        )
        bottom_pilot_outer = Cylinder(
            access_radius + radial_overlap,
            pilot_depth,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_BOTTOM_MOUNT_HOLE_X_MM,
                    y,
                    bottom_mount_face_z,
                )
            )
        )
        bottom_pilot_inner = Cylinder(
            pilot_radius,
            pilot_depth + 2.0 * overtravel,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ).moved(
            Location(
                (
                    SERVO_BOTTOM_MOUNT_HOLE_X_MM,
                    y,
                    bottom_mount_face_z - overtravel,
                )
            )
        )
        sleeves.append(
            (bottom_access_outer - bottom_access_inner).fuse(
                bottom_pilot_outer - bottom_pilot_inner
            )
        )

    for sleeve in sleeves:
        bay = _largest_connected_solid(
            bay.fuse(sleeve),
            "ST3215 stepped mount-sleeve fuse",
        )
    return bay


def gen_step() -> Shape:
    """Return the standalone, STEP-ready ST3215 rear motor bay."""
    clearance_y = float(SOCKET_CLEARANCE_Y_PER_SIDE_MM)
    clearance_z = float(SOCKET_CLEARANCE_Z_TOTAL_MM)
    wall = float(SOCKET_WALL_MM)
    length_x = float(SOCKET_LENGTH_X_MM)
    stop = float(SOCKET_STOP_THICKNESS_MM)
    overtravel = float(BOOLEAN_OVERTRAVEL_MM)

    if min(clearance_y, clearance_z) < 0.0:
        raise ValueError("Socket clearances cannot be negative")
    if min(wall, length_x, stop, overtravel) <= 0.0:
        raise ValueError("Wall, length, stop, and overtravel must be positive")
    if stop >= length_x:
        raise ValueError("The stop must be thinner than the bay length")

    inner_y = ST3215_CATALOG_WIDTH_Z_MM + 2.0 * clearance_y
    inner_z = ST3215_CATALOG_HEIGHT_Y_MM + clearance_z
    outer_y = inner_y + 2.0 * wall
    outer_z = inner_z + 2.0 * wall
    outer_min_x = ATTACHMENT_DATUM_X_MM - length_x

    bay = Box(
        length_x,
        outer_y,
        outer_z,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).moved(Location(((outer_min_x + ATTACHMENT_DATUM_X_MM) / 2.0, 0.0, 0.0)))

    cavity_max_x = ATTACHMENT_DATUM_X_MM - stop
    cavity_min_x = outer_min_x - overtravel
    cavity_trim = Box(
        cavity_max_x - cavity_min_x,
        outer_y + 2.0 * wall,
        outer_z + 2.0 * wall,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).moved(Location(((cavity_min_x + cavity_max_x) / 2.0, 0.0, 0.0)))

    installed_servo = import_step(ST3215_SERVO_STEP).moved(
        st3215_installed_location()
    )
    rear_pieces = []
    for servo_solid in installed_servo.solids():
        trimmed = servo_solid & cavity_trim
        if trimmed is None:
            continue
        rear_pieces.extend(
            solid for solid in trimmed.solids() if float(solid.volume) > 1.0e-6
        )
    if not rear_pieces:
        raise RuntimeError("The ST3215 model did not intersect the bay capture zone")

    exact_rear_profile = rear_pieces[0].fuse(*rear_pieces[1:])
    if len(exact_rear_profile.solids()) != 1 or not exact_rear_profile.is_valid:
        raise RuntimeError("Could not consolidate the ST3215 rear profile")

    # Expand the exact negative profile to create the specified allowances.
    for delta_y, delta_z in (
        (0.0, 0.0),
        (clearance_y, 0.0),
        (-clearance_y, 0.0),
        (0.0, clearance_z),
    ):
        bay = _largest_connected_solid(
            bay - exact_rear_profile.moved(Location((0.0, delta_y, delta_z))),
            "ST3215 cavity cut",
        )

    cable_y = float(SOCKET_CABLE_WINDOW_Y_MM)
    cable_z = float(SOCKET_CABLE_WINDOW_Z_MM)
    if min(cable_y, cable_z) <= 0.0:
        raise ValueError("Cable-window dimensions must be positive")
    if cable_y >= inner_y or cable_z >= inner_z:
        raise ValueError("Cable window must remain inside the attachment rim")

    cable_window = Box(
        stop + 2.0 * overtravel,
        cable_y,
        cable_z,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).moved(
        Location(
            (
                ATTACHMENT_DATUM_X_MM - stop / 2.0,
                0.0,
                0.0,
            )
        )
    )
    bay = _largest_connected_solid(bay - cable_window, "Cable-window cut")
    for cleanup_cutter in _servo_mount_local_access_cleanup(
        inner_y,
        cavity_min_x,
        cavity_max_x,
    ):
        bay = _largest_connected_solid(
            bay - cleanup_cutter,
            "ST3215 local mount-zone cleanup",
        )
    for access_cutter in _servo_mount_access_cutters(outer_z, overtravel):
        bay = _largest_connected_solid(
            bay - access_cutter,
            "ST3215 mount-profile clearance cut",
        )
    bay = _add_servo_mount_step_sleeves(bay, outer_z, overtravel)

    if len(bay.solids()) != 1 or not bay.is_valid:
        raise RuntimeError("The ST3215 motor bay is not one valid solid")
    bay.label = "st3215_rear_motor_bay"
    return bay

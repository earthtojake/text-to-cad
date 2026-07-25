"""Editable build123d wrapper around the original SO-101 upper-arm STEP.

The imported STEP is a boundary-representation model, so its original Fusion
feature history is not recoverable.  This file keeps the reference geometry
unchanged and adds reproducible build123d cut, servo-socket, and pose stages
around it.

Coordinate convention:
    - Units are millimeters.
    - Coordinates initially match ``Upper_arm_SO101.step``.
    - The perforated mounting panel occupies the negative-X end.
    - The optional box cut is evaluated in the original part coordinates.
    - The ST3215 socket extends the arm toward negative X.
    - The installed servo's local X axis follows global X, its local Z axis
      follows global -Y, and its local Y axis follows global +Z.
    - Rotations are applied about the configured pivot in X, Y, Z order.
    - Translation is applied after all rotations.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Align, Axis, Box, Location, Shape, Vector, import_step


REFERENCE_STEP = Path(__file__).with_name("Upper_arm_SO101.step")
ST3215_SERVO_STEP = (
    Path(__file__).parents[4]
    / "lekiwi_quadruped"
    / "components"
    / "waveshare_feetech_st3215_servo.step"
)

# Remove the complete perforated mounting panel marked in the Back
# orthographic view.  The reference panel joins the main body at
# X=-29.084989 mm; a small positive-X overtravel avoids a coincident boolean.
REMOVE_PERFORATED_MOUNT_PANEL = True
MOUNT_PANEL_CUT_PLANE_X_MM = -29.0
MOUNT_PANEL_CUT_OVERSIZE_MM = 5.0

# Preliminary rear-body socket for the exact catalog ST3215 model.  The servo
# slides in from negative X until its rear face meets the stop.  The main horn
# and passive output remain outside the socket on the global +/-Y sides.
#
# The catalog STEP overall bounds are 45.2234 x 37.8 x 24.7234 mm in local
# X/Y/Z.  After the +90 degree X rotation, local Z controls socket width in
# global Y and local Y controls socket height in global Z.
ADD_ST3215_REAR_SOCKET = True
ST3215_CATALOG_LENGTH_X_MM = 45.2234
ST3215_CATALOG_HEIGHT_Y_MM = 37.8
ST3215_CATALOG_WIDTH_Z_MM = 24.7234
ST3215_CATALOG_MAX_X_MM = 9.6117

ST3215_SOCKET_CENTER_Y_MM = 12.0
ST3215_SOCKET_CENTER_Z_MM = -1.95
ST3215_SOCKET_CLEARANCE_Y_PER_SIDE_MM = 0.25
ST3215_SOCKET_CLEARANCE_Z_TOTAL_MM = 0.25
ST3215_SOCKET_WALL_MM = 3.0
ST3215_SOCKET_LENGTH_X_MM = 16.0
ST3215_SOCKET_JOIN_OVERLAP_MM = 0.6
ST3215_SOCKET_STOP_THICKNESS_MM = 1.5
ST3215_SOCKET_CABLE_WINDOW_Y_MM = 16.0
ST3215_SOCKET_CABLE_WINDOW_Z_MM = 14.0

# Optional subtractive edit.  Leave disabled until the intended cut region is
# needed.  The box is centered at CUT_BOX_CENTER_MM and may safely extend
# beyond the imported body.
CUT_ENABLED = False
CUT_BOX_SIZE_MM = (20.0, 30.0, 20.0)
CUT_BOX_CENTER_MM = (0.0, 12.25, 0.0)

# Final pose controls.  The default pivot is near the inspected body center.
# Change it to a measured servo axis or mating datum before posing a real link.
ROTATION_PIVOT_MM = (5.9845195, 12.25, -1.95)
ROTATION_X_DEG = 0.0
ROTATION_Y_DEG = 0.0
ROTATION_Z_DEG = 0.0
TRANSLATION_MM = (0.0, 0.0, 0.0)


def _validated_xyz(name: str, values: tuple[float, float, float]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise ValueError(f"{name} must contain exactly three values")
    return tuple(float(value) for value in values)


def _load_reference_body() -> Shape:
    """Load the one non-empty solid from the source STEP assembly."""
    imported = import_step(REFERENCE_STEP)
    solids = list(imported.solids())
    if len(solids) != 1:
        raise RuntimeError(
            f"Expected one non-empty upper-arm solid in {REFERENCE_STEP.name}, "
            f"found {len(solids)}"
        )
    body = solids[0]
    body.label = "upper_arm_so101"
    return body


def _apply_optional_cut(body: Shape) -> Shape:
    result = body

    if REMOVE_PERFORATED_MOUNT_PANEL:
        bounds = result.bounding_box()
        oversize = float(MOUNT_PANEL_CUT_OVERSIZE_MM)
        if oversize <= 0.0:
            raise ValueError("MOUNT_PANEL_CUT_OVERSIZE_MM must be positive")

        cut_min_x = bounds.min.X - oversize
        cut_max_x = float(MOUNT_PANEL_CUT_PLANE_X_MM)
        if not bounds.min.X < cut_max_x < bounds.max.X:
            raise ValueError("MOUNT_PANEL_CUT_PLANE_X_MM must intersect the upper arm")

        cutter_size = (
            cut_max_x - cut_min_x,
            bounds.size.Y + 2.0 * oversize,
            bounds.size.Z + 2.0 * oversize,
        )
        cutter_center = (
            (cut_min_x + cut_max_x) / 2.0,
            (bounds.min.Y + bounds.max.Y) / 2.0,
            (bounds.min.Z + bounds.max.Z) / 2.0,
        )
        mount_panel_cutter = Box(
            *cutter_size,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).moved(Location(cutter_center))
        result = result - mount_panel_cutter

    if CUT_ENABLED:
        size = _validated_xyz("CUT_BOX_SIZE_MM", CUT_BOX_SIZE_MM)
        if any(dimension <= 0.0 for dimension in size):
            raise ValueError("Every CUT_BOX_SIZE_MM dimension must be positive")

        center = _validated_xyz("CUT_BOX_CENTER_MM", CUT_BOX_CENTER_MM)
        cutter = Box(
            *size,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        ).moved(Location(center))
        result = result - cutter

    solids = list(result.solids())
    if not solids:
        raise RuntimeError("The configured cut removed the entire upper arm")
    if len(solids) != 1:
        raise RuntimeError(f"The configured cut split the upper arm into {len(solids)} solids")
    result.label = "upper_arm_so101_cut"
    return result


def _add_st3215_rear_socket(body: Shape) -> Shape:
    """Add a keyed socket derived from the exact ST3215 rear-case geometry."""
    if not ADD_ST3215_REAR_SOCKET:
        return body

    clearance_y = float(ST3215_SOCKET_CLEARANCE_Y_PER_SIDE_MM)
    clearance_z_total = float(ST3215_SOCKET_CLEARANCE_Z_TOTAL_MM)
    wall = float(ST3215_SOCKET_WALL_MM)
    length_x = float(ST3215_SOCKET_LENGTH_X_MM)
    overlap = float(ST3215_SOCKET_JOIN_OVERLAP_MM)
    stop = float(ST3215_SOCKET_STOP_THICKNESS_MM)
    if min(clearance_y, clearance_z_total) < 0.0:
        raise ValueError("ST3215 socket clearances cannot be negative")
    if min(wall, length_x, overlap, stop) <= 0.0:
        raise ValueError("ST3215 socket wall, length, overlap, and stop must be positive")
    if overlap >= length_x or stop >= length_x:
        raise ValueError("ST3215 socket overlap and stop must be smaller than its length")

    center_y = float(ST3215_SOCKET_CENTER_Y_MM)
    center_z = float(ST3215_SOCKET_CENTER_Z_MM)
    inner_y = float(ST3215_CATALOG_WIDTH_Z_MM) + 2.0 * clearance_y
    inner_z = float(ST3215_CATALOG_HEIGHT_Y_MM) + clearance_z_total
    outer_y = inner_y + 2.0 * wall
    outer_z = inner_z + 2.0 * wall

    outer_max_x = float(MOUNT_PANEL_CUT_PLANE_X_MM) + overlap
    outer_min_x = outer_max_x - length_x
    outer = Box(
        length_x,
        outer_y,
        outer_z,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).moved(
        Location(
            (
                (outer_min_x + outer_max_x) / 2.0,
                center_y,
                center_z,
            )
        )
    )

    # Trim the installed catalog servo to the portion captured by the socket.
    # Using the actual solids preserves the raised connector-side housing and
    # other case steps as matching negative grooves instead of reducing the
    # interface to a loose rectangular envelope.
    cavity_min_x = outer_min_x - overlap
    cavity_max_x = outer_max_x - stop
    cavity_trim = Box(
        cavity_max_x - cavity_min_x,
        outer_y + 2.0 * wall,
        outer_z + 2.0 * wall,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).moved(
        Location(
            (
                (cavity_min_x + cavity_max_x) / 2.0,
                center_y,
                center_z,
            )
        )
    )

    installed_servo = import_step(ST3215_SERVO_STEP).moved(st3215_preview_location())
    rear_pieces = []
    for servo_solid in installed_servo.solids():
        trimmed = servo_solid & cavity_trim
        if trimmed is None:
            continue
        rear_pieces.extend(
            solid for solid in trimmed.solids() if float(solid.volume) > 1.0e-6
        )
    if not rear_pieces:
        raise RuntimeError("The ST3215 catalog model did not intersect the socket capture zone")

    exact_rear_profile = rear_pieces[0].fuse(*rear_pieces[1:])
    if len(exact_rear_profile.solids()) != 1 or not exact_rear_profile.is_valid:
        raise RuntimeError("Could not consolidate the ST3215 rear profile into one valid solid")

    # Expand the negative profile in global +/-Y and global +Z.  The installed
    # preview is shifted by half the total Z allowance, so the resulting
    # vertical clearance is centered without asking the CAD kernel to perform
    # a fragile overlapping subtraction in both Z directions.  Boolean
    # subtraction can leave isolated pins where the source servo contains
    # holes; retain only the connected outer socket after each cut.
    socket = outer
    for delta_y, delta_z in (
        (0.0, 0.0),
        (clearance_y, 0.0),
        (-clearance_y, 0.0),
        (0.0, clearance_z_total),
    ):
        cut_result = socket - exact_rear_profile.moved(
            Location((0.0, delta_y, delta_z))
        )
        connected_solids = list(cut_result.solids())
        if not connected_solids:
            raise RuntimeError("The keyed ST3215 cavity removed the entire socket")
        socket = max(connected_solids, key=lambda solid: float(solid.volume))

    # The stop is a rim rather than a sealed wall, so rear wiring can continue
    # into the arm's existing central opening.
    cable_window_y = float(ST3215_SOCKET_CABLE_WINDOW_Y_MM)
    cable_window_z = float(ST3215_SOCKET_CABLE_WINDOW_Z_MM)
    if min(cable_window_y, cable_window_z) <= 0.0:
        raise ValueError("ST3215 cable-window dimensions must be positive")
    if cable_window_y >= inner_y or cable_window_z >= inner_z:
        raise ValueError("ST3215 cable window must remain inside the socket stop rim")
    cable_window = Box(
        stop + 2.0 * overlap,
        cable_window_y,
        cable_window_z,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    ).moved(
        Location(
            (
                outer_max_x - stop / 2.0,
                center_y,
                center_z,
            )
        )
    )

    socket = socket - cable_window
    if not socket.is_valid:
        raise RuntimeError("The keyed ST3215 socket is not a valid solid")
    socket.label = "st3215_rear_body_socket"
    result = body + socket
    solids = list(result.solids())
    if len(solids) != 1:
        raise RuntimeError(
            f"ST3215 socket must fuse into one upper-arm solid, found {len(solids)} solids"
        )
    result.label = "upper_arm_so101_with_st3215_socket"
    return result


def st3215_preview_location() -> Location:
    """Return the catalog servo pose seated against the socket stop."""
    socket_outer_max_x = (
        float(MOUNT_PANEL_CUT_PLANE_X_MM) + float(ST3215_SOCKET_JOIN_OVERLAP_MM)
    )
    stop_x = socket_outer_max_x - float(ST3215_SOCKET_STOP_THICKNESS_MM)
    translation_x = stop_x - float(ST3215_CATALOG_MAX_X_MM)
    translation_z = (
        float(ST3215_SOCKET_CENTER_Z_MM)
        + 9.3
        + float(ST3215_SOCKET_CLEARANCE_Z_TOTAL_MM) / 2.0
    )
    return Location(
        (
            translation_x,
            float(ST3215_SOCKET_CENTER_Y_MM),
            translation_z,
        ),
        (90.0, 0.0, 0.0),
    )


def _apply_pose(body: Shape) -> Shape:
    pivot = Vector(*_validated_xyz("ROTATION_PIVOT_MM", ROTATION_PIVOT_MM))
    posed = body
    for direction, angle in (
        ((1.0, 0.0, 0.0), ROTATION_X_DEG),
        ((0.0, 1.0, 0.0), ROTATION_Y_DEG),
        ((0.0, 0.0, 1.0), ROTATION_Z_DEG),
    ):
        if angle:
            posed = posed.rotate(Axis(pivot, direction), float(angle))

    translation = _validated_xyz("TRANSLATION_MM", TRANSLATION_MM)
    if any(translation):
        posed = posed.moved(Location(translation))
    posed.label = "upper_arm_so101_editable"
    return posed


def gen_step() -> Shape:
    """Return the STEP-ready edited upper arm."""
    body = _load_reference_body()
    body = _apply_optional_cut(body)
    body = _add_st3215_rear_socket(body)
    return _apply_pose(body)

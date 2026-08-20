"""Underbone frame and center stand.

The frame is the fixed root of the assembly: head tube, twin downtubes to the
step-through floor pan, seat spine tubes to the tail, engine pivot plates,
shock upper lug, and stand brackets — one welded steel solid plus the floor
pan. The center stand is shown folded up under the floor pan.
"""

from build123d import Box, Location, Plane, RectangleRounded, extrude

import _lib as L
import _spec as S


def _at(point):
    return Location(point)


def _centered_box(center, size):
    return Box(*size).moved(_at(center))


def _floor_pan():
    plane = Plane(origin=(90.0, 0.0, 250.0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    face = RectangleRounded(
        S.FLOOR_X_FRONT - S.FLOOR_X_REAR, 2 * S.FLOOR_HALF_WIDTH, 26.0,
    ).moved(plane.location)
    return extrude(face, S.FLOOR_TOP_Z - S.FLOOR_BOTTOM_Z)


def build_frame():
    # --- tubes -----------------------------------------------------------
    head_tube = L.axis_cylinder(
        tuple(
            (a + b) / 2
            for a, b in zip(
                S.steer_point(S.HEAD_TUBE_BOT_T), S.steer_point(S.HEAD_TUBE_TOP_T)
            )
        ),
        S.STEER_DIR, S.HEAD_TUBE_OD / 2,
        S.HEAD_TUBE_TOP_T - S.HEAD_TUBE_BOT_T,
    )
    downtubes = [
        L.tube([(x, sign * y, z) for x, y, z in S.DOWNTUBE_PATH], S.DOWNTUBE_OD)
        for sign in (-1.0, 1.0)
    ]
    spines = [
        L.tube(
            [(x, sign * S.SPINE_Y, z) for x, z in S.SPINE_PATH], S.SPINE_TUBE_OD
        )
        for sign in (-1.0, 1.0)
    ]
    crosses = [
        L.axis_cylinder((x, 0.0, z), (0, 1, 0), 12.0, 2 * S.SPINE_Y)
        for x, z in S.CROSS_TUBES
    ]

    # --- plates and lugs --------------------------------------------------
    px, pz = S.ENGINE_PIVOT[0], S.PIVOT_PLATE_Z
    sx, sy, sz = S.PIVOT_PLATE_SIZE
    pivot_plates = [
        _centered_box((px, sign * S.PIVOT_PLATE_Y, pz), (sx, sy, sz))
        for sign in (-1.0, 1.0)
    ]
    # frame-side shock lug: reaches inboard from the spine to the mount bore
    shock_lug = _centered_box(
        (S.SHOCK_UPPER[0], S.SHOCK_UPPER[1] - 13.0, S.SHOCK_UPPER[2] - 4.0),
        S.SHOCK_LUG_SIZE,
    )
    stand_lugs = [
        _centered_box(
            (
                S.STAND_PIVOT[0],
                sign * (S.STAND_PIVOT[1] + 4.0),
                S.FLOOR_BOTTOM_Z + 6.0,
            ),
            (26.0, 24.0, 32.0),
        )
        for sign in (-1.0, 1.0)
    ]

    frame = head_tube.fuse(
        *downtubes, *spines, *crosses, _floor_pan(),
        *pivot_plates, shock_lug, *stand_lugs,
    )

    # --- bores, one cut ---------------------------------------------------
    cutters = [
        L.axis_cylinder(
            (0.0, 0.0, 0.0), S.STEER_DIR, S.HEAD_TUBE_BORE / 2, 200.0,
        ).moved(_at(S.steer_point(S.HEAD_TUBE_TOP_T))),
        *[
            L.axis_cylinder(
                (px, sign * S.PIVOT_PLATE_Y, pz), (0, 1, 0),
                S.PIVOT_BORE_D / 2, sy + 4.0,
            )
            for sign in (-1.0, 1.0)
        ],
        *[
            L.axis_cylinder(
                (px, sign * S.PIVOT_PLATE_Y, pz + 45.0), (0, 1, 0),
                14.0, sy + 4.0,
            )
            for sign in (-1.0, 1.0)
        ],
        L.axis_cylinder(S.SHOCK_UPPER, (0, 1, 0), S.SHOCK_EYE_D / 2, 30.0),
        *[
            L.axis_cylinder(
                (S.STAND_PIVOT[0], sign * S.STAND_PIVOT[1], S.STAND_PIVOT[2]),
                (0, 1, 0), 5.5, 40.0,
            )
            for sign in (-1.0, 1.0)
        ],
    ]
    frame = frame.cut(*cutters)
    return L.paint(frame, "frame", "underbone", color=S.FRAME_BLACK)


def build_center_stand():
    arms = [
        L.tube(
            [
                (S.STAND_PIVOT[0], sign * S.STAND_PIVOT[1], S.STAND_PIVOT[2]),
                (S.STAND_ELBOW[0], sign * S.STAND_ELBOW[1], S.STAND_ELBOW[2]),
                (S.STAND_FOOT[0], sign * S.STAND_FOOT[1], S.STAND_FOOT[2]),
            ],
            S.STAND_TUBE_OD,
        )
        for sign in (-1.0, 1.0)
    ]
    cross = L.axis_cylinder(
        S.STAND_CROSS, (0, 1, 0),
        S.STAND_TUBE_OD / 2, 2 * S.STAND_PIVOT[1],
    )
    feet = [
        L.axis_cylinder(
            (S.STAND_FOOT[0], sign * S.STAND_FOOT[1], S.STAND_FOOT[2] - 12.0),
            (0, 0, 1), 11.0, 22.0,
        )
        for sign in (-1.0, 1.0)
    ]
    stand = arms[0].fuse(*arms[1:], cross, *feet)
    stand = stand.cut(
        *[
            L.axis_cylinder(
                (S.STAND_PIVOT[0], sign * S.STAND_PIVOT[1], S.STAND_PIVOT[2]),
                (0, 1, 0), 5.5, 60.0,
            )
            for sign in (-1.0, 1.0)
        ]
    )
    return L.paint(stand, "center_stand", "folded", color=S.FRAME_BLACK)

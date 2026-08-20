"""Steering front end: telescopic fork, handlebar, front fender.

Everything hangs on the steering axis (through ``FRONT_AXLE``, raked 27 deg).
The fork is one black solid plus a chrome axle; the handlebar carries black
grips and steel levers; the front fender is a cream arc band over the tire,
narrow enough to sit between the fork sliders.
"""

from build123d import Box, Location

import _lib as L
import _spec as S


def _leg_center(t, y):
    p = S.steer_point(t)
    return (p[0], y, p[2])


def build_front_fork():
    stem = L.axis_cylinder(
        _leg_center(665.0, 0.0), S.STEER_DIR, 14.0, 70.0 + 0.0,
    )
    stanchions = [
        L.axis_cylinder(
            _leg_center((250.0 + 620.0) / 2, sign * S.FORK_LEG_OFFSET_Y),
            S.STEER_DIR, S.STANCHION_OD / 2, 620.0 - 250.0,
        )
        for sign in (-1.0, 1.0)
    ]
    sliders = [
        L.axis_cylinder(
            _leg_center((-10.0 + 300.0) / 2, sign * S.FORK_LEG_OFFSET_Y),
            S.STEER_DIR, S.SLIDER_OD / 2, 300.0 - (-10.0),
        )
        for sign in (-1.0, 1.0)
    ]
    brace = L.axis_cylinder(
        _leg_center(380.0, 0.0), (0, 1, 0), 11.0, 2 * S.FORK_LEG_OFFSET_Y,
    )
    fork = stem.fuse(*stanchions, *sliders, brace)
    fork = L.paint(fork, "front_fork", "telescopic", color=S.FRAME_BLACK)

    axle = L.paint(
        L.axis_cylinder(S.FRONT_AXLE, (0, 1, 0), S.AXLE_DIAMETER / 2, 160.0),
        "front_axle", color=S.CHROME,
    )
    return [fork, axle]


def build_handlebar():
    from build123d import Vector

    top = S.steer_point(S.STEM_TOP_T)
    collar = L.axis_cylinder(
        _leg_center(S.STEM_TOP_T - 12.0, 0.0), S.STEER_DIR, 21.0, 58.0,
    )
    bar_pts_right = [
        (top[0], 0.0, top[2] + 4.0),
        (top[0] - 2.0, 90.0, top[2] + 1.0),
        (top[0] - 11.0, 210.0, top[2] + 5.0),
        (top[0] - 25.0, 300.0, top[2] + 17.0),
    ]
    # full bar path: mirrored left half + right half (shared center point)
    left_half = [(x, -y, z) for x, y, z in reversed(bar_pts_right)][:-1]
    bar = collar.fuse(
        L.tube(left_half + bar_pts_right[1:], S.BAR_TUBE_OD)
    )
    bar = L.paint(bar, "handlebar", "steel", color=S.FRAME_BLACK)

    # grips along the outer bar tangent, mirrored per side
    end_prev = Vector(bar_pts_right[-2])
    end = Vector(bar_pts_right[-1])
    grip_dir = (end - end_prev).normalized()
    k = S.GRIP_LEN / 2 - 4.0
    grip_base = (
        end.X + grip_dir.X * k,
        end.Y + grip_dir.Y * k,
        end.Z + grip_dir.Z * k,
    )
    grips = []
    for sign, label in ((1.0, "right"), (-1.0, "left")):
        center = (grip_base[0], sign * grip_base[1], grip_base[2])
        axis = (grip_dir.X, sign * grip_dir.Y, grip_dir.Z)
        grips.append(
            L.paint(
                L.axis_cylinder(center, axis, S.GRIP_OD / 2, S.GRIP_LEN),
                "grip", label, color=S.RUBBER,
            )
        )

    # brake levers ahead of the grips, mirrored per side
    levers = []
    for sign, label in ((1.0, "right"), (-1.0, "left")):
        base = (end.X + 44.0, sign * (end.Y - 26.0), end.Z + 11.0)
        lever = L.axis_cylinder(
            base, (1.0, -sign * 0.12, 0.10), 5.0, 92.0,
        )
        levers.append(L.paint(lever, "brake_lever", label, color=S.STEEL))
    return [bar, *grips, *levers]


def build_front_fender():
    r_mid = (S.FRONT_FENDER_R0 + S.FRONT_FENDER_R1) / 2
    band = L.revolve_band(
        S.FRONT_AXLE, r_mid,
        S.FRONT_FENDER_R1 - S.FRONT_FENDER_R0, S.FRONT_FENDER_HALF_WIDTH,
        S.FRONT_FENDER_ANGLES[0], S.FRONT_FENDER_ANGLES[1],
    )
    return L.paint(band, "front_fender", color=S.CREAM)

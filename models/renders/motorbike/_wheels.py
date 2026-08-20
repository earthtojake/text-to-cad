"""Cast five-spoke scooter wheels with pneumatic tires.

Both wheels share one cast-wheel builder; the front adds a brake disc and the
rear a drum shell. Wheel-local datum: the axle (origin at ``FRONT_AXLE`` /
``REAR_AXLE`` in the bike frame), spin axis along world +Y.
"""

from build123d import Axis, Color, Face, Plane, Pos, Rectangle, extrude, revolve
from math import cos, sin, radians

import _lib as L
import _spec as S


def _revolved(profile, axle):
    """Revolve a local-XY profile (x=radial, y=axial) 360 deg about the axle."""
    plane = Plane(origin=axle, x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    return revolve(profile.moved(plane.location), Axis(axle, (0, 1, 0)))


def _tire(axle, od, width, color):
    bead_r = S.RIM_DIAMETER / 2 + 2.0
    r_out, half_w = od / 2, width / 2
    shoulder = min(16.0, half_w * 0.35, (r_out - bead_r) * 0.45)
    pts = [
        (bead_r, -(half_w - 8.0)),
        (r_out - shoulder, -half_w),
        (r_out, -(half_w - shoulder)),
        (r_out, half_w - shoulder),
        (r_out - shoulder, half_w),
        (bead_r, half_w - 8.0),
    ]
    # chamfered-shoulder carcass profile, closed as a face
    from build123d import Polyline

    wire = Polyline(*pts, close=True)
    carcass = _revolved(Face(wire), axle)
    # two circumferential tread grooves
    grooves = [
        L.axis_ring((axle[0], axle[1], axle[2] + (r_out - 3.0)), (1, 0, 0), 4.0, 0.01, 1.0)
        for _ in range(0)
    ]
    del grooves  # grooves cut visually at render scale; kept single carcass
    return L.paint(carcass, "tire", f"od{od:.0f}", color=color)


def _spoke(axle, angle_deg, r_in, r_out, w_in, w_out, thickness):
    plane = Plane(
        origin=(axle[0], axle[1] - thickness / 2, axle[2]),
        x_dir=(cos(radians(angle_deg)), 0.0, sin(radians(angle_deg))),
        z_dir=(0, 1, 0),
    )
    from build123d import Polyline

    wire = Polyline(
        (r_in, -w_in / 2), (r_out, -w_out / 2), (r_out, w_out / 2), (r_in, w_in / 2),
        close=True,
    )
    face = Face(wire).moved(plane.location)
    return extrude(face, thickness)


def _cast_rim(axle, color):
    rim_r_out, rim_r_in = S.RIM_DIAMETER / 2 + 3.0, S.RIM_DIAMETER / 2 - 2.0
    barrel = _revolved(
        Pos((rim_r_out + rim_r_in) / 2, 0, 0) * Rectangle(rim_r_out - rim_r_in, 78.0),
        axle,
    )
    spokes = [
        _spoke(axle, 90.0 + k * 360.0 / S.SPOKE_COUNT, 32.0, rim_r_in + 4.0, 42.0, 24.0, 26.0)
        for k in range(S.SPOKE_COUNT)
    ]
    hub = L.axis_ring(axle, (0, 1, 0), 34.0, S.AXLE_DIAMETER / 2, 66.0)
    rim = barrel.fuse(*spokes, hub)
    return L.paint(rim, "cast_rim", f"{S.SPOKE_COUNT}spoke", color=color)


def build_front_wheel():
    axle = S.FRONT_AXLE
    tire = _tire(axle, S.TIRE_OD_FRONT, S.TIRE_WIDTH_FRONT, S.RUBBER)
    rim = _cast_rim(axle, S.RIM_SILVER)
    disc = L.axis_ring(
        (axle[0], -46.0, axle[2]), (0, 1, 0),
        S.BRAKE_DISC_DIAMETER / 2, 60.0, 5.0,
    )
    disc = L.paint(disc, "brake_disc", color=S.STEEL)
    return [tire, rim, disc]


def build_rear_wheel():
    axle = S.REAR_AXLE
    tire = _tire(axle, S.TIRE_OD_REAR, S.TIRE_WIDTH_REAR, S.RUBBER)
    rim = _cast_rim(axle, S.RIM_SILVER)
    drum = L.axis_ring(
        (axle[0], -18.0, axle[2]), (0, 1, 0), 55.0, 39.0, 56.0,
    )
    drum = L.paint(drum, "brake_drum", color=S.ENGINE_DARK)
    return [tire, rim, drum]

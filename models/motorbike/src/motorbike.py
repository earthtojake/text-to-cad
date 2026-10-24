"""Full motorbike assembly: the one model here, every part composed by CALLING it.

Each part is a plain function in a sibling file, called inside this body: the
bike is one body and one xbf, and the kernel memo caches the parts' kernel calls
(a `@memo` per part saves under 0.1 s, so none carries one). Every part is
authored in the BIKE frame (see `lib/spec.py`), so the assembly composes at
identity and still
records the functional relationships as native build123d joints on
world-coincident datum frames:

- steering: frame head tube <-> fork (revolute, raked axis through the axle)
- front spin: fork axle <-> front wheel (revolute)
- engine swing: frame pivot plates <-> engine (revolute)
- rear spin: engine output hub <-> rear wheel (revolute)
- center stand: frame bracket <-> stand pivot tubes (revolute)
- everything else: rigid mounts at named, parameterized datums.

Each revolute joint carries the range the old typed mate declared, and the old
`KINEMATICS` poses are configurations on those joints: `stand_down` (the stand
deployed to the floor), `turned_left` (the bars 32 degrees left) and `bump` (the
engine swung up 12 degrees); `ride`, which set nothing, is the bike as built. One
motion: `steer`, the bars swung 20 degrees each way and back, which a GLB export
bakes into a clip of that name.

Two parts are instanced twice: `turn_signal_left()` is the front-left signal
and, PLACED with `Pos`, the rear-left one (a second call in one build is a new
placement of the first's result); `turn_signal_right()` the same on the
right. The right-hand signals and mirror are the left parts' mirror images —
new geometry, not a placement — so each is its own function built from the same
`lib/trim.py` factory, and the assembly links all four signals and both mirrors.

OCCURRENCE ORDER IS FROZEN — top to bottom below.
"""

from __future__ import annotations

from cadgen import model
from cadgen.ap242 import configuration_sequence, mechanism_state

import build123d as bd

from center_stand import center_stand
from engine import engine
from exhaust import exhaust
from frame import frame
from front_fender import front_fender
from front_fork import front_fork
from front_wheel import front_wheel
from handlebar import MIRROR_MOUNT_LEFT, MIRROR_MOUNT_RIGHT, handlebar
from headlight import headlight
from leg_shield import leg_shield
from mirror_left import mirror_left
from mirror_right import mirror_right
from rear_fender import rear_fender
from rear_shock import rear_shock
from rear_wheel import rear_wheel
from seat import seat
from steering_cover import steering_cover
from tail_light import tail_light
from turn_signal_left import turn_signal_left
from turn_signal_right import turn_signal_right
from under_seat_body import under_seat_body

from lib import spec as S


def _label(shape, name, *details):
    """``name:detail`` on the shape (the old ``asm.add``)."""
    shape.label = ":".join(str(token) for token in (name, *details))
    return shape


def _revolute_mate(fixed_part, moving_part, point, direction,
                   fixed_name, moving_name, limits):
    """Native revolute relationship at a world datum. The moving side must be
    a rigid frame (this build123d version's connect_to contract); its Plane
    orientation matches the RevoluteJoint's own frame convention so a static
    angle-0 pose keeps the as-authored placement exactly. ``limits``: the range
    the old typed mate declared."""
    bd.RevoluteJoint(fixed_name, fixed_part, axis=bd.Axis(point, direction), angular_range=limits)
    bd.RigidJoint(moving_name, moving_part, bd.Plane(origin=point, z_dir=direction).location)
    fixed_part.joints[fixed_name].connect_to(moving_part.joints[moving_name], angle=0.0)


def _rigid_mate(fixed_part, fixed_name, moving_part, moving_name, location):
    """A rigid mount (the old ``rigid_frame`` pair + ``connect``)."""
    bd.RigidJoint(fixed_name, fixed_part, location)
    bd.RigidJoint(moving_name, moving_part, location)
    fixed_part.joints[fixed_name].connect_to(moving_part.joints[moving_name])


@model
def motorbike():
    fx, fy, fz = S.FRONT_SIGNAL_POS
    rx, ry, rz = S.REAR_SIGNAL_POS

    # --- fixed root + front body ------------------------------------------
    chassis = _label(frame().shape, "frame")
    shroud = _label(steering_cover().shape, "steering_cover")
    shield = _label(leg_shield().shape, "leg_shield")

    # --- steering front end -------------------------------------------------
    fork = _label(front_fork().shape, "front_fork")
    bars = _label(handlebar().shape, "handlebar")
    fender_front = _label(front_fender().shape, "front_fender")
    wheel_front = _label(front_wheel().shape, "front_wheel")
    lamp = _label(headlight().shape, "headlight")
    signal_fl = _label(turn_signal_left().shape, "turn_signal", "front_left")
    signal_fr = _label(turn_signal_right().shape, "turn_signal", "front_right")

    # --- powertrain ---------------------------------------------------------
    motor = _label(engine().shape, "engine")
    pipe = _label(exhaust().shape, "exhaust")
    shock = _label(rear_shock().shape, "rear_shock")
    wheel_rear = _label(rear_wheel().shape, "rear_wheel")

    # --- rear body + trim ---------------------------------------------------
    body = _label(under_seat_body().shape, "under_seat_body")
    fender_rear = _label(rear_fender().shape, "rear_fender")
    saddle = _label(seat().shape, "seat")
    lamp_rear = _label(tail_light().shape, "tail_light")
    signal_rl = _label(bd.Pos(rx - fx, ry - fy, rz - fz) * turn_signal_left().shape,
                       "turn_signal", "rear_left")
    signal_rr = _label(bd.Pos(rx - fx, -(ry - fy), rz - fz) * turn_signal_right().shape,
                       "turn_signal", "rear_right")
    mirror_l = _label(mirror_left().shape, "mirror", "left")
    mirror_r = _label(mirror_right().shape, "mirror", "right")
    stand = _label(center_stand().shape, "center_stand")

    # --- joints: motion ------------------------------------------------------
    # Order matters: connect_to() repositions the moving part, and a part that
    # has already been repositioned must not be the FIXED side of a later
    # revolute (its axis relativization picks up the located state). So each
    # spin hub connects to its carrier while the carrier is still pristine,
    # before that carrier is itself moved by its parent relation.
    _revolute_mate(fork, wheel_front, S.FRONT_AXLE, (0, 1, 0),
                   "front_axle_hub", "front_axle", (-3600.0, 3600.0))
    _revolute_mate(motor, wheel_rear, S.REAR_AXLE, (0, 1, 0),
                   "rear_axle_hub", "rear_axle", (-3600.0, 3600.0))
    steer_mid = S.steer_point((S.HEAD_TUBE_BOT_T + S.HEAD_TUBE_TOP_T) / 2)
    _revolute_mate(chassis, fork, steer_mid, S.STEER_DIR,
                   "head_tube_axis", "steering_axis", (-40.0, 40.0))
    _revolute_mate(chassis, motor, S.ENGINE_PIVOT, (0, 1, 0),
                   "engine_pivot", "swing_pivot", (-5.0, 12.0))
    # Negative deploys: about +Y the stowed foot swings down and forward;
    # -76.2 deg is where the foot reaches z = 0.
    _revolute_mate(chassis, stand, (S.STAND_PIVOT[0], 0.0, S.STAND_PIVOT[2]),
                   (0, 1, 0), "stand_bracket", "pivot_tubes", (-76.2, 0.0))

    # --- joints: rigid mounts ------------------------------------------------
    stem_top = S.steer_point(S.STEM_TOP_T)
    _rigid_mate(fork, "stem_clamp", bars, "stem", bd.Location(stem_top))

    fender_at = S.steer_point(150.0)
    _rigid_mate(fork, "fork_leg_mount", fender_front, "fork_mount", bd.Location(fender_at))

    shroud_at = S.steer_point(S.HEAD_TUBE_TOP_T)
    _rigid_mate(chassis, "head_shroud", shroud, "head_tube_mount", bd.Location(shroud_at))

    apron_at = bd.Location((S.LEG_SHIELD_SECTIONS[2][0], 0.0, S.LEG_SHIELD_SECTIONS[2][1]))
    _rigid_mate(chassis, "apron_mount", shield, "frame_mount", apron_at)

    _rigid_mate(shield, "headlight_mount", lamp, "apron_mount", bd.Location(S.HEADLIGHT_CENTER))

    _rigid_mate(shield, "signal_mount_left", signal_fl, "apron_mount", bd.Location((fx, fy, fz)))
    _rigid_mate(shield, "signal_mount_right", signal_fr, "apron_mount", bd.Location((fx, -fy, fz)))

    _rigid_mate(motor, "exhaust_port", pipe, "head_flange", bd.Location(S.EXHAUST_FLANGE))

    # The shock's two eyes tie the frame to the swinging engine: a closed loop,
    # which the old kinematics left unmated (the shock stays put while the
    # engine swings). Only its upper eye is mounted, to the frame: a rigid
    # lower eye too would weld the engine to the frame and lock engine_pivot.
    _rigid_mate(chassis, "shock_upper_lug", shock, "upper_eye", bd.Location(S.SHOCK_UPPER))

    seat_frame_at = bd.Location((-480.0, 0.0, 560.0))
    _rigid_mate(chassis, "seat_frame_mount", body, "frame_mount", seat_frame_at)

    seat_rail_at = bd.Location((-550.0, 0.0, 705.0))
    _rigid_mate(body, "seat_rail", saddle, "body_mount", seat_rail_at)

    fender_at2 = bd.Location((S.REAR_AXLE[0], 0.0, S.REAR_AXLE[2] + 245.0))
    _rigid_mate(body, "rear_fender_mount", fender_rear, "body_mount", fender_at2)

    _rigid_mate(body, "tail_light_mount", lamp_rear, "body_mount", bd.Location(S.TAILLIGHT_CENTER))

    _rigid_mate(body, "signal_mount_left", signal_rl, "body_mount", bd.Location((rx, ry, rz)))
    _rigid_mate(body, "signal_mount_right", signal_rr, "body_mount", bd.Location((rx, -ry, rz)))

    _rigid_mate(bars, "mirror_mount_left", mirror_l, "bar_mount", bd.Location(MIRROR_MOUNT_LEFT))
    _rigid_mate(bars, "mirror_mount_right", mirror_r, "bar_mount", bd.Location(MIRROR_MOUNT_RIGHT))

    bike = bd.Compound(children=[
        chassis, shroud, shield,
        fork, bars, fender_front, wheel_front, lamp, signal_fl, signal_fr,
        motor, pipe, shock, wheel_rear,
        body, fender_rear, saddle, lamp_rear, signal_rl, signal_rr, mirror_l, mirror_r, stand,
    ], label="motorbike")
    # The old typed mates' poses, by the joints that carry them now (steering is
    # head_tube_axis, engine_swing engine_pivot, center_stand_pivot stand_bracket;
    # same axes, same senses). "ride" set nothing: it is the bike as built.
    mechanism_state(bike, "stand_down", stand_bracket=-76.2)
    mechanism_state(bike, "turned_left", head_tube_axis=32.0)
    mechanism_state(bike, "bump", engine_pivot=12.0)
    # The bars swung from 20 degrees right to 20 left and back, 2 s each way.
    return configuration_sequence(bike, "steer", [(0, {"head_tube_axis": -20}), (2, {"head_tube_axis": 20}),
                                  (4, {"head_tube_axis": -20})])


if __name__ == "__main__":
    motorbike()

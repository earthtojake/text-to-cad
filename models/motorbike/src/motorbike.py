"""Full motorbike assembly: every part model composed by CALLING it.

Children are sibling models: calling one inside this body builds it if stale
(on its own worker, in parallel with its siblings) or loads it, and the
assembly LINKS to the child's geometry rather than copying it. Every child
authors its parts in the BIKE frame (see `lib/spec.py`), so the assembly
composes at identity and still records the functional relationships as native
build123d joints on world-coincident datum frames:

- steering: frame head tube <-> fork (revolute, raked axis through the axle)
- front spin: fork axle <-> front wheel (revolute)
- engine swing: frame pivot plates <-> engine (revolute)
- rear spin: engine output hub <-> rear wheel (revolute)
- everything else: rigid mounts at named, parameterized datums.

Two children are instanced: `turn_signal()` is the front-left signal and, PLACED
with `Pos`, the rear-left one (both links). The right-hand signals and mirror
are the models' mirror images — new geometry, not a placement — so the
assembly builds them from the same `lib/trim.py` helpers and owns them.

OCCURRENCE ORDER IS FROZEN — top to bottom below.
"""

from __future__ import annotations

import cadgen
from cadgen import build123d as bd
from cadgen import step

from cadgen.assembly import AssemblyHelper

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
from mirror import mirror
from rear_fender import rear_fender
from rear_shock import rear_shock
from rear_wheel import rear_wheel
from seat import seat
from steering_cover import steering_cover
from tail_light import tail_light
from turn_signal import turn_signal
from under_seat_body import under_seat_body

from lib import spec as S
from lib import trim as T


def _revolute_mate(asm, fixed_part, moving_part, point, direction,
                   fixed_name, moving_name, label):
    """Native revolute relationship at a world datum. The moving side must be
    a rigid frame (this build123d version's connect_to contract); its Plane
    orientation matches the RevoluteJoint's own frame convention so a static
    angle-0 pose keeps the as-authored placement exactly."""
    fixed = asm.revolute_frame(fixed_part, fixed_name, bd.Axis(point, direction))
    moving = asm.rigid_frame(
        moving_part, moving_name, bd.Plane(origin=point, z_dir=direction).location,
    )
    asm.revolute(fixed, moving, angle=0.0, label=label)


# --- typed mates: the DECLARED motion the viewer poses and a bake exports ----
#
# The native joints above place the children (angle 0 = the as-authored bike);
# these are the same pivots restated as pure data on the instance tree, from
# the same S.* hardpoints, so nothing can drift between the two.
#
# Refs name instance-tree nodes: `#frame` is a part occurrence, `#front_fork`
# and `#engine` are subassemblies, and mating a group carries its whole subtree.
# Only SIBLINGS need a `fastened` mate — the handlebar, front fender and mirrors
# are separate top-level children, so without one they would not follow the
# steering. Everything bolted to the frame (leg shield, apron trim, tail, seat)
# is already at rest relative to the root and needs no mate.
#
# The rear shock is deliberately NOT mated: its two eyes tie the frame to the
# swinging engine, which is a closed loop, and cadgen evaluates pure forward
# kinematics by design. It stays put while the engine swings.
_STEER_AXIS = S.steer_point((S.HEAD_TUBE_BOT_T + S.HEAD_TUBE_TOP_T) / 2)
_STAND_AXIS = (S.STAND_PIVOT[0], 0.0, S.STAND_PIVOT[2])

KINEMATICS = {
    "mates": [
        cadgen.revolute("steering", parent="#frame", child="#front_fork",
                        origin=_STEER_AXIS, direction=S.STEER_DIR,
                        limits=(-40.0, 40.0)),
        cadgen.fastened("handlebar_clamp", parent="#front_fork", child="#handlebar"),
        cadgen.fastened("front_fender_mount", parent="#front_fork", child="#front_fender"),
        cadgen.fastened("mirror_left_mount", parent="#handlebar", child="#mirror:left"),
        cadgen.fastened("mirror_right_mount", parent="#handlebar", child="#mirror:right"),
        cadgen.revolute("front_wheel_spin", parent="#front_fork", child="#front_wheel",
                        origin=S.FRONT_AXLE, direction=(0, 1, 0),
                        limits=(-3600.0, 3600.0)),
        cadgen.revolute("engine_swing", parent="#frame", child="#engine",
                        origin=S.ENGINE_PIVOT, direction=(0, 1, 0),
                        limits=(-5.0, 12.0)),
        cadgen.fastened("exhaust_mount", parent="#engine", child="#exhaust"),
        cadgen.revolute("rear_wheel_spin", parent="#engine", child="#rear_wheel",
                        origin=S.REAR_AXLE, direction=(0, 1, 0),
                        limits=(-3600.0, 3600.0)),
        # Negative deploys: about +Y the stowed foot swings down and forward.
        # -76.2 deg is where the foot reaches z = 0 (pivot 250.3 mm above the
        # foot arc, 240 mm off the ground), so the limit stops at the floor.
        cadgen.revolute("center_stand_pivot", parent="#frame", child="#center_stand",
                        origin=_STAND_AXIS, direction=(0, 1, 0),
                        limits=(-76.2, 0.0)),
    ],
    "poses": {
        "ride": {},
        "stand_down": {"center_stand_pivot": -76.2},
        "turned_left": {"steering": 32.0},
        "bump": {"engine_swing": 12.0},
    },
}


@step(out="../STEP/motorbike.step", kinematics=KINEMATICS)
def motorbike():
    asm = AssemblyHelper("motorbike")
    fx, fy, fz = S.FRONT_SIGNAL_POS
    rx, ry, rz = S.REAR_SIGNAL_POS

    # --- fixed root + front body ------------------------------------------
    chassis = asm.add(frame(), "frame")
    shroud = asm.add(steering_cover(), "steering_cover")
    shield = asm.add(leg_shield(), "leg_shield")

    # --- steering front end -------------------------------------------------
    fork = asm.add(front_fork(), "front_fork")
    bars = asm.add(handlebar(), "handlebar")
    fender_front = asm.add(front_fender(), "front_fender")
    wheel_front = asm.add(front_wheel(), "front_wheel")
    lamp = asm.add(headlight(), "headlight")
    signal_fl = asm.add(turn_signal(), "turn_signal", "front_left")
    signal_fr = asm.add(bd.Compound(children=T.build_turn_signal((fx, -fy, fz), -1.0)),
                        "turn_signal", "front_right")

    # --- powertrain ---------------------------------------------------------
    motor = asm.add(engine(), "engine")
    pipe = asm.add(exhaust(), "exhaust")
    shock = asm.add(rear_shock(), "rear_shock")
    wheel_rear = asm.add(rear_wheel(), "rear_wheel")

    # --- rear body + trim ---------------------------------------------------
    body = asm.add(under_seat_body(), "under_seat_body")
    fender_rear = asm.add(rear_fender(), "rear_fender")
    saddle = asm.add(seat(), "seat")
    lamp_rear = asm.add(tail_light(), "tail_light")
    signal_rl = asm.add(bd.Pos(rx - fx, ry - fy, rz - fz) * turn_signal(),
                        "turn_signal", "rear_left")
    signal_rr = asm.add(bd.Compound(children=T.build_turn_signal((rx, -ry, rz), -1.0)),
                        "turn_signal", "rear_right")
    mirror_l = asm.add(mirror(), "mirror", "left")
    mirror_r = asm.add(bd.Compound(children=T.build_mirror(-1.0, MIRROR_MOUNT_RIGHT)),
                       "mirror", "right")
    stand = asm.add(center_stand(), "center_stand")

    # --- joints: motion ------------------------------------------------------
    # Order matters: connect_to() repositions the moving part, and a part that
    # has already been repositioned must not be the FIXED side of a later
    # revolute (its axis relativization picks up the located state). So each
    # spin hub connects to its carrier while the carrier is still pristine,
    # before that carrier is itself moved by its parent relation.
    _revolute_mate(asm, fork, wheel_front, S.FRONT_AXLE, (0, 1, 0),
                   "front_axle_hub", "front_axle", "front_wheel_spin")
    _revolute_mate(asm, motor, wheel_rear, S.REAR_AXLE, (0, 1, 0),
                   "rear_axle_hub", "rear_axle", "rear_wheel_spin")
    steer_mid = S.steer_point((S.HEAD_TUBE_BOT_T + S.HEAD_TUBE_TOP_T) / 2)
    _revolute_mate(asm, chassis, fork, steer_mid, S.STEER_DIR,
                   "head_tube_axis", "steering_axis", "steering")
    _revolute_mate(asm, chassis, motor, S.ENGINE_PIVOT, (0, 1, 0),
                   "engine_pivot", "swing_pivot", "engine_swing")
    _revolute_mate(asm, chassis, stand, (S.STAND_PIVOT[0], 0.0, S.STAND_PIVOT[2]),
                   (0, 1, 0), "stand_bracket", "pivot_tubes", "center_stand_pivot")

    # --- joints: rigid mounts ------------------------------------------------
    stem_top = S.steer_point(S.STEM_TOP_T)
    stem = asm.rigid_frame(fork, "stem_clamp", bd.Location(stem_top))
    bar_stem = asm.rigid_frame(bars, "stem", bd.Location(stem_top))
    asm.connect(stem, bar_stem, relation="rigid", label="handlebar_clamp")

    fender_at = S.steer_point(150.0)
    fork_leg = asm.rigid_frame(fork, "fork_leg_mount", bd.Location(fender_at))
    fender_mount = asm.rigid_frame(fender_front, "fork_mount", bd.Location(fender_at))
    asm.connect(fork_leg, fender_mount, relation="rigid", label="front_fender_mount")

    shroud_at = S.steer_point(S.HEAD_TUBE_TOP_T)
    head_shroud = asm.rigid_frame(chassis, "head_shroud", bd.Location(shroud_at))
    cover_mount = asm.rigid_frame(shroud, "head_tube_mount", bd.Location(shroud_at))
    asm.connect(head_shroud, cover_mount, relation="rigid", label="steering_cover_mount")

    apron_at = bd.Location((S.LEG_SHIELD_SECTIONS[2][0], 0.0, S.LEG_SHIELD_SECTIONS[2][1]))
    apron = asm.rigid_frame(chassis, "apron_mount", apron_at)
    shield_mount = asm.rigid_frame(shield, "frame_mount", apron_at)
    asm.connect(apron, shield_mount, relation="rigid", label="leg_shield_mount")

    lamp_at = bd.Location(S.HEADLIGHT_CENTER)
    shield_lamp = asm.rigid_frame(shield, "headlight_mount", lamp_at)
    lamp_mount = asm.rigid_frame(lamp, "apron_mount", lamp_at)
    asm.connect(shield_lamp, lamp_mount, relation="rigid", label="headlight_mount")

    fl_mount = asm.rigid_frame(shield, "signal_mount_left", bd.Location((fx, fy, fz)))
    fl_eye = asm.rigid_frame(signal_fl, "apron_mount", bd.Location((fx, fy, fz)))
    asm.connect(fl_mount, fl_eye, relation="rigid", label="front_left_signal")
    fr_mount = asm.rigid_frame(shield, "signal_mount_right", bd.Location((fx, -fy, fz)))
    fr_eye = asm.rigid_frame(signal_fr, "apron_mount", bd.Location((fx, -fy, fz)))
    asm.connect(fr_mount, fr_eye, relation="rigid", label="front_right_signal")

    flange_at = bd.Location(S.EXHAUST_FLANGE)
    head_port = asm.rigid_frame(motor, "exhaust_port", flange_at)
    pipe_flange = asm.rigid_frame(pipe, "head_flange", flange_at)
    asm.connect(head_port, pipe_flange, relation="rigid", label="exhaust_mount")

    upper_at = bd.Location(S.SHOCK_UPPER)
    frame_shock = asm.rigid_frame(chassis, "shock_upper_lug", upper_at)
    shock_upper = asm.rigid_frame(shock, "upper_eye", upper_at)
    asm.connect(frame_shock, shock_upper, relation="coaxial", label="shock_upper_mount")
    lower_at = bd.Location(S.SHOCK_LOWER)
    engine_shock = asm.rigid_frame(motor, "shock_lower_boss", lower_at)
    shock_lower = asm.rigid_frame(shock, "lower_eye", lower_at)
    asm.connect(engine_shock, shock_lower, relation="coaxial", label="shock_lower_mount")

    seat_frame_at = bd.Location((-480.0, 0.0, 560.0))
    frame_seat = asm.rigid_frame(chassis, "seat_frame_mount", seat_frame_at)
    body_mount = asm.rigid_frame(body, "frame_mount", seat_frame_at)
    asm.connect(frame_seat, body_mount, relation="rigid", label="under_body_mount")

    seat_rail_at = bd.Location((-550.0, 0.0, 705.0))
    body_seat = asm.rigid_frame(body, "seat_rail", seat_rail_at)
    seat_mount = asm.rigid_frame(saddle, "body_mount", seat_rail_at)
    asm.connect(body_seat, seat_mount, relation="rigid", label="seat_mount")

    fender_at2 = bd.Location((S.REAR_AXLE[0], 0.0, S.REAR_AXLE[2] + 245.0))
    body_fender = asm.rigid_frame(body, "rear_fender_mount", fender_at2)
    rfender_mount = asm.rigid_frame(fender_rear, "body_mount", fender_at2)
    asm.connect(body_fender, rfender_mount, relation="rigid", label="rear_fender_mount")

    tail_at = bd.Location(S.TAILLIGHT_CENTER)
    body_tail = asm.rigid_frame(body, "tail_light_mount", tail_at)
    tail_mount = asm.rigid_frame(lamp_rear, "body_mount", tail_at)
    asm.connect(body_tail, tail_mount, relation="rigid", label="tail_light_mount")

    rl_mount = asm.rigid_frame(body, "signal_mount_left", bd.Location((rx, ry, rz)))
    rl_eye = asm.rigid_frame(signal_rl, "body_mount", bd.Location((rx, ry, rz)))
    asm.connect(rl_mount, rl_eye, relation="rigid", label="rear_left_signal")
    rr_mount = asm.rigid_frame(body, "signal_mount_right", bd.Location((rx, -ry, rz)))
    rr_eye = asm.rigid_frame(signal_rr, "body_mount", bd.Location((rx, -ry, rz)))
    asm.connect(rr_mount, rr_eye, relation="rigid", label="rear_right_signal")

    bar_left = asm.rigid_frame(bars, "mirror_mount_left", bd.Location(MIRROR_MOUNT_LEFT))
    mirror_left = asm.rigid_frame(mirror_l, "bar_mount", bd.Location(MIRROR_MOUNT_LEFT))
    asm.connect(bar_left, mirror_left, relation="rigid", label="mirror_left_mount")
    bar_right = asm.rigid_frame(bars, "mirror_mount_right", bd.Location(MIRROR_MOUNT_RIGHT))
    mirror_right = asm.rigid_frame(mirror_r, "bar_mount", bd.Location(MIRROR_MOUNT_RIGHT))
    asm.connect(bar_right, mirror_right, relation="rigid", label="mirror_right_mount")

    return asm.build()


if __name__ == "__main__":
    motorbike()

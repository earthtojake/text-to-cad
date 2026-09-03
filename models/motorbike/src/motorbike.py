"""Full motorbike assembly: every individual part entry composed in place.

Children are authored in the BIKE frame by the shared builder modules (the
f1/moonwatch package pattern), so the assembly composes at identity and still
records the functional relationships as native build123d joints on
world-coincident datum frames:

- steering: frame head tube <-> fork (revolute, raked axis through the axle)
- front spin: fork axle <-> front wheel (revolute)
- engine swing: frame pivot plates <-> engine (revolute)
- rear spin: engine output hub <-> rear wheel (revolute)
- everything else: rigid mounts at named, parameterized datums.

OCCURRENCE ORDER IS FROZEN — top to bottom below.
"""

from __future__ import annotations

import cadgen
from cadgen import build123d as bd
from cadgen import step

from cadgen.assembly import AssemblyHelper

from lib import bodywork as BODY
from lib import chassis as CH
from lib import drivetrain as DT
from lib import frontend as FE
from lib import lib as L
from lib import spec as S
from lib import trim as T
from lib import wheels as WH


def _part(built):
    """Builders return one shape or a list of shapes; asm.add wants a shape."""
    if isinstance(built, list):
        return L.paint_compound(built, "part")
    return built


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

    # --- fixed root + front body ------------------------------------------
    frame = asm.add(_part(CH.build_frame()), "frame")
    steering_cover = asm.add(_part(BODY.build_steering_cover()), "steering_cover")
    leg_shield = asm.add(_part(BODY.build_leg_shield()), "leg_shield")

    # --- steering front end -------------------------------------------------
    fork = asm.add(_part(FE.build_front_fork()), "front_fork")
    handlebar = asm.add(_part(FE.build_handlebar()), "handlebar")
    front_fender = asm.add(_part(FE.build_front_fender()), "front_fender")
    front_wheel = asm.add(_part(WH.build_front_wheel()), "front_wheel")
    headlight = asm.add(_part(T.build_headlight()), "headlight")
    fx, fy, fz = S.FRONT_SIGNAL_POS
    signal_fl = asm.add(_part(T.build_turn_signal((fx, fy, fz), 1.0)),
                        "turn_signal", "front_left")
    signal_fr = asm.add(_part(T.build_turn_signal((fx, -fy, fz), -1.0)),
                        "turn_signal", "front_right")

    # --- powertrain ---------------------------------------------------------
    engine = asm.add(_part(DT.build_engine()), "engine")
    exhaust = asm.add(_part(DT.build_exhaust()), "exhaust")
    rear_shock = asm.add(_part(DT.build_rear_shock()), "rear_shock")
    rear_wheel = asm.add(_part(WH.build_rear_wheel()), "rear_wheel")

    # --- rear body + trim ---------------------------------------------------
    under_seat = asm.add(_part(BODY.build_under_seat_body()), "under_seat_body")
    rear_fender = asm.add(_part(BODY.build_rear_fender()), "rear_fender")
    seat = asm.add(_part(BODY.build_seat()), "seat")
    tail_light = asm.add(_part(T.build_tail_light()), "tail_light")
    rx, ry, rz = S.REAR_SIGNAL_POS
    signal_rl = asm.add(_part(T.build_turn_signal((rx, ry, rz), 1.0)),
                        "turn_signal", "rear_left")
    signal_rr = asm.add(_part(T.build_turn_signal((rx, -ry, rz), -1.0)),
                        "turn_signal", "rear_right")
    mirror_l = asm.add(_part(T.build_mirror(1.0)), "mirror", "left")
    mirror_r = asm.add(_part(T.build_mirror(-1.0)), "mirror", "right")
    stand = asm.add(_part(CH.build_center_stand()), "center_stand")

    # --- joints: motion ------------------------------------------------------
    # Order matters: connect_to() repositions the moving part, and a part that
    # has already been repositioned must not be the FIXED side of a later
    # revolute (its axis relativization picks up the located state). So each
    # spin hub connects to its carrier while the carrier is still pristine,
    # before that carrier is itself moved by its parent relation.
    _revolute_mate(asm, fork, front_wheel, S.FRONT_AXLE, (0, 1, 0),
                   "front_axle_hub", "front_axle", "front_wheel_spin")
    _revolute_mate(asm, engine, rear_wheel, S.REAR_AXLE, (0, 1, 0),
                   "rear_axle_hub", "rear_axle", "rear_wheel_spin")
    steer_mid = S.steer_point((S.HEAD_TUBE_BOT_T + S.HEAD_TUBE_TOP_T) / 2)
    _revolute_mate(asm, frame, fork, steer_mid, S.STEER_DIR,
                   "head_tube_axis", "steering_axis", "steering")
    _revolute_mate(asm, frame, engine, S.ENGINE_PIVOT, (0, 1, 0),
                   "engine_pivot", "swing_pivot", "engine_swing")
    _revolute_mate(asm, frame, stand, (S.STAND_PIVOT[0], 0.0, S.STAND_PIVOT[2]),
                   (0, 1, 0), "stand_bracket", "pivot_tubes", "center_stand_pivot")

    # --- joints: rigid mounts ------------------------------------------------
    stem_top = S.steer_point(S.STEM_TOP_T)
    stem = asm.rigid_frame(fork, "stem_clamp", bd.Location(stem_top))
    bar_stem = asm.rigid_frame(handlebar, "stem", bd.Location(stem_top))
    asm.connect(stem, bar_stem, relation="rigid", label="handlebar_clamp")

    fender_at = S.steer_point(150.0)
    fork_leg = asm.rigid_frame(fork, "fork_leg_mount", bd.Location(fender_at))
    fender_mount = asm.rigid_frame(front_fender, "fork_mount", bd.Location(fender_at))
    asm.connect(fork_leg, fender_mount, relation="rigid", label="front_fender_mount")

    shroud_at = S.steer_point(S.HEAD_TUBE_TOP_T)
    head_shroud = asm.rigid_frame(frame, "head_shroud", bd.Location(shroud_at))
    cover_mount = asm.rigid_frame(steering_cover, "head_tube_mount", bd.Location(shroud_at))
    asm.connect(head_shroud, cover_mount, relation="rigid", label="steering_cover_mount")

    apron_at = bd.Location((S.LEG_SHIELD_SECTIONS[2][0], 0.0, S.LEG_SHIELD_SECTIONS[2][1]))
    apron = asm.rigid_frame(frame, "apron_mount", apron_at)
    shield_mount = asm.rigid_frame(leg_shield, "frame_mount", apron_at)
    asm.connect(apron, shield_mount, relation="rigid", label="leg_shield_mount")

    lamp_at = bd.Location(S.HEADLIGHT_CENTER)
    shield_lamp = asm.rigid_frame(leg_shield, "headlight_mount", lamp_at)
    lamp_mount = asm.rigid_frame(headlight, "apron_mount", lamp_at)
    asm.connect(shield_lamp, lamp_mount, relation="rigid", label="headlight_mount")

    fl_mount = asm.rigid_frame(leg_shield, "signal_mount_left", bd.Location((fx, fy, fz)))
    fl_eye = asm.rigid_frame(signal_fl, "apron_mount", bd.Location((fx, fy, fz)))
    asm.connect(fl_mount, fl_eye, relation="rigid", label="front_left_signal")
    fr_mount = asm.rigid_frame(leg_shield, "signal_mount_right", bd.Location((fx, -fy, fz)))
    fr_eye = asm.rigid_frame(signal_fr, "apron_mount", bd.Location((fx, -fy, fz)))
    asm.connect(fr_mount, fr_eye, relation="rigid", label="front_right_signal")

    flange_at = bd.Location(S.EXHAUST_FLANGE)
    head_port = asm.rigid_frame(engine, "exhaust_port", flange_at)
    pipe_flange = asm.rigid_frame(exhaust, "head_flange", flange_at)
    asm.connect(head_port, pipe_flange, relation="rigid", label="exhaust_mount")

    upper_at = bd.Location(S.SHOCK_UPPER)
    frame_shock = asm.rigid_frame(frame, "shock_upper_lug", upper_at)
    shock_upper = asm.rigid_frame(rear_shock, "upper_eye", upper_at)
    asm.connect(frame_shock, shock_upper, relation="coaxial", label="shock_upper_mount")
    lower_at = bd.Location(S.SHOCK_LOWER)
    engine_shock = asm.rigid_frame(engine, "shock_lower_boss", lower_at)
    shock_lower = asm.rigid_frame(rear_shock, "lower_eye", lower_at)
    asm.connect(engine_shock, shock_lower, relation="coaxial", label="shock_lower_mount")

    seat_frame_at = bd.Location((-480.0, 0.0, 560.0))
    frame_seat = asm.rigid_frame(frame, "seat_frame_mount", seat_frame_at)
    body_mount = asm.rigid_frame(under_seat, "frame_mount", seat_frame_at)
    asm.connect(frame_seat, body_mount, relation="rigid", label="under_body_mount")

    seat_rail_at = bd.Location((-550.0, 0.0, 705.0))
    body_seat = asm.rigid_frame(under_seat, "seat_rail", seat_rail_at)
    seat_mount = asm.rigid_frame(seat, "body_mount", seat_rail_at)
    asm.connect(body_seat, seat_mount, relation="rigid", label="seat_mount")

    fender_at2 = bd.Location((S.REAR_AXLE[0], 0.0, S.REAR_AXLE[2] + 245.0))
    body_fender = asm.rigid_frame(under_seat, "rear_fender_mount", fender_at2)
    rfender_mount = asm.rigid_frame(rear_fender, "body_mount", fender_at2)
    asm.connect(body_fender, rfender_mount, relation="rigid", label="rear_fender_mount")

    tail_at = bd.Location(S.TAILLIGHT_CENTER)
    body_tail = asm.rigid_frame(under_seat, "tail_light_mount", tail_at)
    tail_mount = asm.rigid_frame(tail_light, "body_mount", tail_at)
    asm.connect(body_tail, tail_mount, relation="rigid", label="tail_light_mount")

    rl_mount = asm.rigid_frame(under_seat, "signal_mount_left", bd.Location((rx, ry, rz)))
    rl_eye = asm.rigid_frame(signal_rl, "body_mount", bd.Location((rx, ry, rz)))
    asm.connect(rl_mount, rl_eye, relation="rigid", label="rear_left_signal")
    rr_mount = asm.rigid_frame(under_seat, "signal_mount_right", bd.Location((rx, -ry, rz)))
    rr_eye = asm.rigid_frame(signal_rr, "body_mount", bd.Location((rx, -ry, rz)))
    asm.connect(rr_mount, rr_eye, relation="rigid", label="rear_right_signal")

    bar_l = S.steer_point(S.STEM_TOP_T)
    bar_left = asm.rigid_frame(handlebar, "mirror_mount_left",
                               bd.Location((bar_l[0] - 16.0, 235.0, bar_l[2] + 6.0)))
    mirror_left = asm.rigid_frame(mirror_l, "bar_mount",
                                  bd.Location((bar_l[0] - 16.0, 235.0, bar_l[2] + 6.0)))
    asm.connect(bar_left, mirror_left, relation="rigid", label="mirror_left_mount")
    bar_right = asm.rigid_frame(handlebar, "mirror_mount_right",
                                bd.Location((bar_l[0] - 16.0, -235.0, bar_l[2] + 6.0)))
    mirror_right = asm.rigid_frame(mirror_r, "bar_mount",
                                   bd.Location((bar_l[0] - 16.0, -235.0, bar_l[2] + 6.0)))
    asm.connect(bar_right, mirror_right, relation="rigid", label="mirror_right_mount")

    return asm.build()


if __name__ == "__main__":
    motorbike()

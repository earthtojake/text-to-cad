"""Unit powertrain: engine (doubles as the swingarm), exhaust, rear shock.

The engine pivots on the frame at ``ENGINE_PIVOT`` and carries the rear wheel
on its output hub — the scooter layout. The horizontal cylinder points
forward-up; the CVT drum is rider-left, the exhaust runs rider-right.
"""

from math import sqrt

from build123d import Box, Cone, Location, Plane

import _lib as L
import _spec as S


def _along(axis_dir, base, s):
    """Point s mm along axis_dir from base."""
    return (
        base[0] + axis_dir[0] * s,
        base[1] + axis_dir[1] * s,
        base[2] + axis_dir[2] * s,
    )


def build_engine():
    cx, cy, cz = S.CASE_CENTER
    sx, sy, sz = S.CASE_SIZE
    case = Box(sx, sy, sz).moved(Location((cx, cy, cz)))
    edges = [e for e in case.edges() if abs(e.center().Z - (cz + sz / 2)) < 1e-6]
    case = case.chamfer(16.0, None, edges)

    # pivot nose reaching between the frame plates (plates sit at |y|>=79)
    nose = L.axis_cylinder(S.ENGINE_PIVOT, (0, 1, 0), 26.0, 156.0)

    # cylinder barrel + fins + head, tilted up from horizontal
    barrel = L.axis_cylinder(S.CYL_BASE, S.CYL_DIR, S.CYL_BARREL_OD / 2, S.CYL_BARREL_LEN)
    fins = [
        L.axis_cylinder(
            _along(S.CYL_DIR, S.CYL_BASE, 18.0 + i * (S.FIN_TH + S.FIN_GAP)),
            S.CYL_DIR, S.FIN_OD / 2, S.FIN_TH,
        )
        for i in range(S.FIN_COUNT)
    ]
    head = L.axis_cylinder(
        _along(S.CYL_DIR, S.CYL_BASE, S.CYL_BARREL_LEN + S.HEAD_DEPTH / 2),
        S.CYL_DIR, S.HEAD_OD / 2, S.HEAD_DEPTH,
    )

    # rear wheel carrier: left-side swingarm plate (outside the tire, |y|>54)
    # plus a hub flange meeting the wheel hub face
    hub_arm = Box(
        S.HUB_ARM_X1 - S.HUB_ARM_X0, S.HUB_ARM_Y1 - S.HUB_ARM_Y0,
        S.HUB_ARM_Z1 - S.HUB_ARM_Z0,
    ).moved(Location(((S.HUB_ARM_X0 + S.HUB_ARM_X1) / 2,
                      (S.HUB_ARM_Y0 + S.HUB_ARM_Y1) / 2,
                      (S.HUB_ARM_Z0 + S.HUB_ARM_Z1) / 2)))
    hub_flange = L.axis_ring(
        (S.REAR_AXLE[0], (S.HUB_FLANGE_Y0 + S.HUB_FLANGE_Y1) / 2, S.REAR_AXLE[2]),
        (0, 1, 0), S.HUB_FLANGE_OD / 2, 8.0,
        S.HUB_FLANGE_Y1 - S.HUB_FLANGE_Y0,
    )

    # shock-lower boss on the case rear, rider left
    boss = Box(*S.SHOCK_BOSS_SIZE).moved(Location(S.SHOCK_BOSS_CENTER))

    engine = case.fuse(nose, barrel, head, *fins, hub_arm, hub_flange, boss)
    engine = engine.cut(
        # pivot bore through the nose
        L.axis_cylinder(S.ENGINE_PIVOT, (0, 1, 0), S.PIVOT_BORE_D / 2, 170.0),
        # shock bolt bore through the boss
        L.axis_cylinder(S.SHOCK_LOWER, (0, 1, 0), S.SHOCK_EYE_D / 2, 40.0),
        # rear axle bore through the flange
        L.axis_cylinder(S.REAR_AXLE, (0, 1, 0), S.AXLE_DIAMETER / 2 - 1.0, 70.0),
        # wheel-arch clearance: notch engine material inside the rear wheel
        L.axis_cylinder(S.REAR_AXLE, (0, 1, 0), S.WHEEL_ARCH_R_OUT,
                        2 * S.WHEEL_ARCH_HALF_Y)
        - L.axis_cylinder(S.REAR_AXLE, (0, 1, 0), S.WHEEL_ARCH_R_IN,
                          2 * S.WHEEL_ARCH_HALF_Y + 2.0),
    )
    engine = L.paint(engine, "engine", "unit_swingarm", color=S.ENGINE_SILVER)

    rear_axle = L.paint(
        L.axis_cylinder(S.REAR_AXLE, (0, 1, 0), S.AXLE_DIAMETER / 2, 130.0),
        "rear_axle", color=S.CHROME,
    )

    cvt_drum = L.axis_cylinder(
        (S.CVT_COVER_CENTER[0], (S.CVT_COVER_Y0 + S.CVT_COVER_Y1) / 2,
         S.CVT_COVER_CENTER[2]),
        (0, 1, 0), S.CVT_COVER_OD / 2, S.CVT_COVER_Y1 - S.CVT_COVER_Y0,
    )
    cvt_drum = L.paint(cvt_drum, "cvt_cover", "rider_left", color=S.ENGINE_DARK)
    cvt_plate = L.axis_cylinder(
        (S.CVT_COVER_CENTER[0], S.CVT_COVER_Y0 - S.CVT_PLATE_T / 2,
         S.CVT_COVER_CENTER[2]),
        (0, 1, 0), S.CVT_PLATE_OD / 2, S.CVT_PLATE_T,
    )
    cvt_plate = L.paint(cvt_plate, "cvt_inner_plate", color=S.ENGINE_DARK)
    crank_cover = L.axis_cylinder(
        (S.CRANK_COVER_CENTER[0], (S.CRANK_COVER_Y0 + S.CRANK_COVER_Y1) / 2,
         S.CRANK_COVER_CENTER[2]),
        (0, 1, 0), S.CRANK_COVER_OD / 2, abs(S.CRANK_COVER_Y1 - S.CRANK_COVER_Y0),
    )
    crank_cover = L.paint(crank_cover, "crank_cover", "rider_right", color=S.ENGINE_DARK)
    return [engine, cvt_drum, cvt_plate, crank_cover, rear_axle]


def build_exhaust():
    pipe = L.tube(S.PIPE_PATH, S.PIPE_OD)
    flange = L.axis_ring(
        tuple(S.EXHAUST_FLANGE),
        tuple((S.PIPE_PATH[1][i] - S.EXHAUST_FLANGE[i]) for i in range(3)),
        26.0, S.PIPE_OD / 2 + 1.0, 12.0,
    )
    muffler_len = S.MUFFLER_X1 - S.MUFFLER_X0
    muffler_center = ((S.MUFFLER_X0 + S.MUFFLER_X1) / 2, S.MUFFLER_Y, S.MUFFLER_Z)
    can = L.axis_cylinder(muffler_center, (1, 0, 0), S.MUFFLER_R, muffler_len)
    from build123d import Sphere

    cap_front = Sphere(S.MUFFLER_R).moved(Location((S.MUFFLER_X0, S.MUFFLER_Y, S.MUFFLER_Z)))
    cap_rear = Sphere(S.MUFFLER_R).moved(Location((S.MUFFLER_X1, S.MUFFLER_Y, S.MUFFLER_Z)))
    tip = L.axis_cylinder(
        (S.MUFFLER_X1 - 22.0, S.MUFFLER_Y, S.MUFFLER_Z), (1, 0, 0), 12.0, 60.0,
    )
    exhaust = pipe.fuse(flange, can, cap_front, cap_rear, tip)
    return L.paint(exhaust, "exhaust", "chrome", color=S.CHROME)


def build_rear_shock():
    """Compact coilover between SHOCK_LOWER and SHOCK_UPPER, authored in place."""
    lower, upper = S.SHOCK_LOWER, S.SHOCK_UPPER
    from build123d import Vector

    start, end = Vector(lower), Vector(upper)
    axis = (end - start).normalized()
    length = (end - start).length
    plane = Plane(origin=start, z_dir=axis)

    def local(shape):
        return shape.moved(plane.location)

    eye_lower = local(L.axis_ring((0, 0, 0), (0, 0, 1), S.SHOCK_EYE_OD / 2,
                                  S.SHOCK_EYE_D / 2, S.SHOCK_EYE_W))
    eye_upper = local(L.axis_ring((0, 0, length), (0, 0, 1), S.SHOCK_EYE_OD / 2,
                                  S.SHOCK_EYE_D / 2, S.SHOCK_EYE_W))
    body = local(L.axis_cylinder((0, 0, 60.0), (0, 0, 1),
                                 S.SHOCK_BODY_OD / 2, 90.0))
    seat_lower = local(Cone(S.SHOCK_BODY_OD / 2, S.SHOCK_SPRING_MEAN_D / 2 - 2.0, 10.0)
                       .moved(Location((0, 0, 102.0))))
    seat_upper = local(Cone(S.SHOCK_SPRING_MEAN_D / 2 - 2.0, S.SHOCK_BODY_OD / 2, 10.0)
                       .moved(Location((0, 0, 158.0))))
    damper = eye_lower.fuse(body, seat_lower, seat_upper, eye_upper)
    damper = L.paint(damper, "damper", color=S.SHOCK_BODY)

    spring = L.coil_between(
        (0, 0, 108.0), (0, 0, 162.0),
        S.SHOCK_SPRING_MEAN_D, S.SHOCK_SPRING_WIRE_D, S.SHOCK_SPRING_TURNS,
    ).moved(plane.location)
    spring = L.paint(spring, "coil_spring", color=S.SPRING_YELLOW)

    rod = local(L.axis_cylinder((0, 0, 130.0), (0, 0, 1), 7.0, 76.0))
    rod = L.paint(rod, "piston_rod", color=S.CHROME)
    return [damper, spring, rod]

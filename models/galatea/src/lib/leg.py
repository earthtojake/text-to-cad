"""The left leg at the zero pose, link by link. `dims.py` holds the skeleton it is built on.

Hip: three actuators whose axes meet at one point. The yaw actuator sits in the pelvis
and turns the hip yoke; the roll actuator on the back of the yoke turns the cradle; the
pitch actuator on the outside of the cradle turns the femur, under a cap on the cradle's cheek.

Knee: a rotary actuator high on the femur turns a crank between the femur plates; a
pushrod carries the motion down to the horn behind the knee hub. Crank and horn are
equal and parallel, so the linkage is a parallelogram and the knee follows the actuator
one to one, with the motor's mass up at the hip.

Ankle: a drive across the calf, on a bracket between the shin rails, turns one crank; a
pushrod runs down the back of the shin to the ankle gimbal (pitch). The roll actuator is
the gimbal's own axle, lying along the foot.

Thigh and shin wear a skin of two layers (`skin.py`): a black liner that holds the
mechanism with air round it, and pearl panels over its front and back. Each ends at a
joint on the line that joint's travel needs, and is carried on pads that grow from the
frame to the liner's inner surface.
"""

import math

import build123d as bd

from . import geo, skin
from .dims import (
    ACTUATORS, ANKLE, HIP_YOKE_Y, ANKLE_ACT, ANKLE_ARM_PIN, ANKLE_CRANK_PIN, ANKLE_ROD_R, ANKLE_ROD_X, CRADLE_CHEEK_X, FEMUR_PLATE_X, HIP,
    KNEE, KNEE_ACT, KNEE_CRANK_PIN, KNEE_HORN_PIN, KNEE_ROD_R, PELVIS_Z, PLATE_T, SHIN_RAIL_X, TOE,
)
from .hardware import ROTOR_PROUD, mount_bores, pin, pushrod, rotor_counterbores
from .kit import frame, part

HX, HZ = HIP[0], HIP[2]
KZ, AZ, KAZ, CAZ, CAY = KNEE[2], ANKLE[2], KNEE_ACT[2], ANKLE_ACT[2], ANKLE_ACT[1]
C0, C1 = CRADLE_CHEEK_X
P0, P1 = FEMUR_PLATE_X
R0, R1 = SHIN_RAIL_X
SKIN_T = 2.6
DECK_Z = 33.5         # top of the foot shell's deck, half a millimetre under its rim
LEG_LINKS = ("hip_yoke", "hip_cradle", "thigh", "knee_crank", "knee_rod", "shin", "ankle_crank", "ankle_rods",
             "ankle_gimbal", "foot", "toe")


# The thigh's form, drawn close: the femur's plates stand 26 either side of the leg's centre plane, and the
# knee drive (an RS04: 120 across, 52 long, at z 780) on the outside of the outer one, so the outer side
# swells from mid-thigh to hold it and the inner side runs straight. Its back holds the pushrod, which
# stands 61 behind the axis at mid bend. The upper sections are squarer than the lower: a can seen end
# on fills a rectangle.
THIGH_TOP = 852.0                              # under the hip drive's can and its cap
YOKE_Y = HIP_YOKE_Y                            # the hip yoke's rear plate: its front face, behind the hip's centre
HIP_CAP_R = 65.6                               # the hip cap's outer radius: an RS04 is 60, with 3 of air
# The knee rim in the side view (y, z). Before the knee it is the line the calf's back comes up to at full flexion with a
# calf 64 deep; behind it the line is steeper, for the calf is 83 deep where its drive stands (z = 583 + 0.98 y).
THIGH_RIM = ((-200.0, 446.0), (10.7, 593.5), (200.0, 779.0))
THIGH_RAKE = (878.1, 0.40, 1.30)                # the thigh's raked top in front: the plane z = 878.1 + 0.40 x + 1.30 y
THIGH_ROWS = skin.register("thigh", [
    geo.S(520, HX + 3, 0, rx=40, rxn=42, ry=58, ryn=50, n=3.5),
    geo.S(640, HX + 3, 0, rx=58, rxn=40, ry=71, ryn=58, n=4.0),
    geo.S(716, HX + 3, 0, rx=84, rxn=38, ry=75, ryn=68, n=6.0),
    geo.S(780, HX + 3, 0, rx=85, rxn=38, ry=77, ryn=74, n=6.0),
    geo.S(860, HX + 3, 0, rx=85, rxn=38, ry=73, ryn=66, n=6.0),
], covers=["l_thigh", "l_knee_crank", "l_knee_rod"], link="l_thigh", above=[THIGH_RIM[:2], THIGH_RIM[1:]],
    below=[((-100.0, THIGH_TOP), (100.0, THIGH_TOP))], poses=[{"l_knee": 40}, {"l_knee": 62.5}, {"l_knee": 90}, {"l_knee": 125}])
# The shin's form: the rails stand 48 either side of the centre plane all the way down; the calf drive, an
# RS04 120 across on a bracket, stands 12 behind the leg's axis, so the shin is straight in front and has a calf.
CALF_FACE = 14.0                               # the calf drive's mounting face, outboard of the leg's centre plane
# The top rim in the side view (y, z): a guard rising before the knee, then a step down behind the knee's axis to the
# line the pushrod comes down to at full flexion (it swings back over the shin's top as the knee folds).
SHIN_RIM = ((-200.0, 660.5), (-52.0, 530.0), (-12.0, 494.7), (4.0, 447.0), (200.0, 310.0))
SHIN_ROWS = skin.register("shin", [
    geo.S(150, HX, 4, rx=60, ry=62, ryn=41, n=4.0),
    geo.S(240, HX, 6, rx=63, ry=64, ryn=45, n=4.0),
    geo.S(340, HX, 8, rx=63, ry=75, ryn=67, n=3.6),
    geo.S(425, HX, 6, rx=64, ry=62, ryn=52, n=3.4),
    geo.S(470, HX, 0, rx=54, ry=50, ryn=46, n=3.2),
    geo.S(535, HX, -2, rx=44, ry=46, ryn=50, n=3.0),
], covers=["l_shin", "l_ankle_crank", "l_ankle_rods"], link="l_shin", below=[SHIN_RIM[3:]],
    poses=[{"l_ankle_pitch": -45}, {"l_ankle_pitch": 30}])


def xr(offset):
    """World X of a point `offset` outboard of the leg's centre plane."""
    return HX + offset


def build_leg(hw):
    """Every part of the left leg, by link; `pelvis` holds what the leg bolts into the pelvis."""
    links = {name: [] for name in ("pelvis", *LEG_LINKS)}
    _hip(hw, links)
    _thigh(hw, links)
    _knee_drive(hw, links)
    _shin(hw, links)
    _ankle(hw, links)
    _foot(hw, links)
    return links


def _skin_mounts(hw, cavity, outer, seats, size="M4", radius=6.0):
    """Mount pads and their screws for a skin: `seats` are (origin on the frame, direction)."""
    pads, screws = None, []
    for origin, direction in seats:
        pad = geo.mount_pad(cavity, origin, direction, radius)
        pads = pad if pads is None else pads + pad
        screws.append(hw.screw(size, *geo.seat(outer, origin, direction), label="skin_screw"))
    return pads, screws


# ---------------------------------------------------------------------------------------------
# Hip: yoke (yaw) and cradle (roll)
# ---------------------------------------------------------------------------------------------
def _hip(hw, links):
    zt = PELVIS_Z[0] - 1.0            # the yoke's flange meets the yaw output just under the pelvis
    zb = zt - 10.0
    yaw_at = (HX, 0.0, PELVIS_Z[0] + PLATE_T)
    stator, rotor = hw.actuator("RS06", yaw_at, (0, 0, -1), x_dir=(-1, 0, 0), name="hip_yaw")
    links["pelvis"] += stator

    top = geo.plate_xy(geo.bones([(HX, 0, 40), (HX, 56, 30)], holes=[(HX, 0, 8)]), zb, zt)
    top -= geo.box(40, 300, 40, (xr(30) + 20, 0, zb))                    # cut off outboard, where the pitch drive's can rises when the leg swings out
    roll_at = (HX, YOKE_Y + 8.0, HZ)
    rear = geo.plate_xz(geo.bones([(HX, HZ, 60), (HX, zt - 30, 30)]), YOKE_Y, YOKE_Y + 8) - mount_bores("RS04", roll_at, (0, -1, 0), x_dir=(1, 0, 0))
    rib = geo.polygon((YOKE_Y, zb), (YOKE_Y - 34, zb), (YOKE_Y, zb - 26))
    yoke = top + rear + geo.plate_yz(rib, xr(21), xr(27)) + geo.plate_yz(rib, xr(-27), xr(-21))
    roll_stator, roll_rotor = hw.actuator("RS04", roll_at, (0, -1, 0), x_dir=(1, 0, 0), name="hip_roll")
    links["hip_yoke"] += [part(yoke, "hip_yoke", "frame"), *rotor,
                          *hw.rotor_screws("RS06", yaw_at, (0, 0, -1), 10.0, x_dir=(-1, 0, 0)), *roll_stator]

    back = geo.plate_xz(geo.bones([(xr(-25), 894, 10), (xr(25), 894, 10), (xr(25), 940, 10), (xr(-25), 940, 10)],
                                  links=[(0, 1, 2, 3)], holes=[(HX, HZ, 8)]), YOKE_Y - 11, YOKE_Y - 1)
    pitch_at = (xr(C1), 0.0, HZ)
    outer = geo.plate_yz(geo.bones([(0, HZ, HIP_CAP_R), (YOKE_Y - 24, HZ - 3, 23)]), xr(C0), xr(C1))
    inner = geo.plate_yz(geo.bones([(0, HZ, 40), (YOKE_Y - 24, HZ - 3, 23)], holes=[(0, HZ, 14)]), xr(-C1), xr(-C0))
    # The pitch drive is turned half round, so that its cable connector stands out underneath, away from the pelvis.
    cradle = back + outer + inner - mount_bores("RS04", pitch_at, (-1, 0, 0), x_dir=(0, -1, 0), turn=180.0)
    pitch_stator, pitch_rotor = hw.actuator("RS04", pitch_at, (-1, 0, 0), x_dir=(0, -1, 0), name="hip_pitch", turn=180.0)
    # Its cap: a cup that stands on the cradle's cheek, flush with its rim, over the can and, stepped in, over its rear
    # cover (the step is what lets the leg swing out under the pelvis), slotted where the connector stands out.
    t, (rf, lf), (rr, lr) = skin.PANEL_T, ACTUATORS["RS04"]["front"], ACTUATORS["RS04"]["rear"]
    small = rr + 5.0
    cup = geo.revolve([(HIP_CAP_R - t, 0.0), (HIP_CAP_R, 0.0), (HIP_CAP_R, lf + 2.0 + t), (small + t, lf + 2.0 + t),
                       (small + t, lf + lr + 3.0 + t), (0.0, lf + lr + 3.0 + t), (0.0, lf + lr + 3.0), (small, lf + lr + 3.0),
                       (small, lf + 2.0), (HIP_CAP_R - t, lf + 2.0)], pitch_at, (1, 0, 0))
    cup -= geo.box(13.0, 12.0, 30.0, (xr(C1) + 45.4, 0, HZ - rr - 12.0))            # the connector: 7 across, 41 to 49 behind the face
    ring = geo.tube(small + t - 2.6, small + t - 5.1, 1.0, (xr(C1) + lf + lr + 2.0 + t, 0, HZ), (1, 0, 0))   # a hairline let into the cap's end, flush
    cup = geo.cut(cup, ring, "hip cap's ring groove")
    links["hip_cradle"] += [part(cradle, "hip_cradle", "frame"), *roll_rotor,
                            *hw.rotor_screws("RS04", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0)), *pitch_stator,
                            hw.pivot_cap(19, (xr(-C1), 0, HZ), (-1, 0, 0), label="hip_bearing_cap"),
                            part(cup, "panel_hip", "under"), part(ring, "trim_hip", "accent")]
    links["thigh"] += [*pitch_rotor, *hw.rotor_screws("RS04", pitch_at, (-1, 0, 0), PLATE_T, x_dir=(0, -1, 0), sunk=5.0)]


# ---------------------------------------------------------------------------------------------
# Thigh: the femur, two plates with the knee drive on the outer one, and its skin
# ---------------------------------------------------------------------------------------------
def _thigh(hw, links):
    # The thigh's skin holds the femur, the knee drive on its outer plate and the pushrod's
    # whole sweep. It ends under the hip drive's drum, and at the knee on a slant: the line the
    # calf's back comes up to when the knee is fully bent.
    form = skin.Form(THIGH_ROWS)
    cuts = [geo.plate_yz(geo.polygon(*THIGH_RIM, (200, 300), (-200, 300)), -400, 400),
            geo.box(600, 600, 100, (HX, 0, THIGH_TOP + 50)),
            # In front the top is raked, lower toward the groin: the plane under every point of the skin that would come
            # up under the pelvis with the thigh raised and the leg turned in or swung out (`THIGH_RAKE`, found by
            # taking the skin's points through the hip's whole travel).
            geo.half_space((HX, 0.0, THIGH_RAKE[0] + THIGH_RAKE[1] * HX), (-THIGH_RAKE[1], -THIGH_RAKE[2], 1.0)),
            # Behind the hip stands its roll drive. When the leg swings 30 degrees back the thigh's upper back comes up under
            # it, so the skin is cut away there on the line the drive's can sweeps (seen from the thigh), with 4 mm to spare.
            geo.plate_yz(geo.polygon((33, 880), (33, 852), (29, 846), (24, 838), (20, 830), (86, 792), (140, 792), (140, 880)), -400, 400)]
    liner = skin.trim(form.liner, cuts, "thigh liner")
    # Two pearl plates, one over the front and one over the back, with the thigh's sides (and its inside) left black between them.
    inside = geo.box(60, 600, 600, (xr(-50), 0, 700))
    stripe = skin.from_side([(8, 900), (-8, 500)], [(22, 500), (38, 900)])
    panel = skin.trim(form.panel, [*cuts, inside, stripe], "thigh panels")
    pads = None
    for origin, direction in [((xr(s * 20), -14, z), (s, 0, 0)) for s in (1, -1) for z in (630, 700)]:
        pad = geo.mount_pad(form.cavity, origin, direction)
        pads = pad if pads is None else pads + pad

    knee_at = (xr(P1), 0.0, KAZ)
    circles = [(0, HZ, 44), (0, KAZ, 60), (-4, HZ, 26), (-4, KAZ, 26), (0, KAZ, 40), (-2, 650, 27), (0, KZ, 34)]
    chain = [(0,), (1,), (2, 3), (4, 5), (5, 6)]
    window = geo.slot(-2, 695, -2, 585, 9)
    outer = geo.plate_yz(geo.bones(circles, chain, holes=[(0, HZ, 10), (0, KZ, 10)], cuts=[window]), xr(P0), xr(P1))
    outer -= mount_bores("RS04", knee_at, (-1, 0, 0), x_dir=(0, -1, 0))
    slim = [(0, KAZ, 40) if k == 1 else c for k, c in enumerate(circles)]       # no drive to carry on the inside
    inner = geo.plate_yz(geo.bones(slim, chain, holes=[(0, KAZ, 12), (0, KZ, 10)], cuts=[window]), xr(-P1), xr(-P0))
    web_low = geo.box(2 * P0 + 2, 6, 190, (HX, -26, 640))
    web_high = geo.box(2 * P0 + 2, 6, 42, (HX, -26, 864))
    spacer = geo.tube(22, 10, 2 * P0 + 2, (xr(-P0 - 1), 0, HZ), (1, 0, 0))
    stub = geo.cyl(14, C1 - P1, (xr(-P1), 0, HZ), (-1, 0, 0))
    femur = outer + inner + web_low + web_high + spacer + stub
    femur -= rotor_counterbores("RS04", (xr(C1), 0.0, HZ), (-1, 0, 0), PLATE_T, x_dir=(0, -1, 0))    # the hip pitch output's screws

    stator, rotor = hw.actuator("RS04", knee_at, (-1, 0, 0), x_dir=(0, -1, 0), name="knee")
    links["thigh"] += [part(femur, "femur", "frame"), *stator,
                       pin((xr(-P1), 0, KZ), (1, 0, 0), 10.0, 2 * P1, label="knee_axle"),
                       hw.pivot_cap(17, (xr(P1), 0, KZ), (1, 0, 0), label="knee_cap"),
                       hw.pivot_cap(17, (xr(-P1), 0, KZ), (-1, 0, 0), label="knee_cap"),
                       part(geo.tube(19.6, 17.2, 1.0, (xr(P1), 0, KZ), (1, 0, 0)), "knee_ring", "accent"),       # a hairline round each cap
                       part(geo.tube(19.6, 17.2, 1.0, (xr(-P1), 0, KZ), (-1, 0, 0)), "knee_ring", "accent"),
                       part(skin.solids(pads - femur), "pad_thigh", "frame"),
                       part(skin.solids(liner), "liner_thigh", "under"), part(skin.solids(panel), "panel_thigh", "shell")]
    links["knee_crank"] += rotor


def _knee_drive(hw, links):
    B, C = KNEE_CRANK_PIN, KNEE_HORN_PIN
    knee_at = (xr(P1), 0.0, KAZ)
    outer = geo.plate_yz(geo.bones([(0, KAZ, 34), (B[1], B[2], 13)], holes=[(0, KAZ, 6), (B[1], B[2], 5)]),
                         xr(8), xr(17))
    inner = geo.plate_yz(geo.bones([(0, KAZ, 20), (B[1], B[2], 13)], holes=[(B[1], B[2], 5)]), xr(-17), xr(-8))
    stub = geo.cyl(12, P1 - 17, (xr(-17), 0, KAZ), (-1, 0, 0))
    crank = outer + inner + stub - rotor_counterbores("RS04", knee_at, (-1, 0, 0), 9.0, x_dir=(0, -1, 0))
    links["knee_crank"] += [part(crank, "knee_crank", "link"),
                            pin((xr(-17), B[1], B[2]), (1, 0, 0), 5.0, 34.0, label="crank_pin"),
                            *hw.rotor_screws("RS04", knee_at, (-1, 0, 0), 9.0, x_dir=(0, -1, 0), sunk=5.0)]
    links["knee_rod"] += [pushrod(B, C, KNEE_ROD_R, 10.0, 13.0, 5.0, label="knee_pushrod")]


# ---------------------------------------------------------------------------------------------
# Shin: the tibia (spool hub, wishbone, two rails), the calf drive and the shin's skin
# ---------------------------------------------------------------------------------------------
def _shin(hw, links):
    # The shin's skin holds the rails, the calf drive between them and the rod behind,
    # through the ankle's travel. Its liner is the whole boot; the pearl panel is a greave over
    # the front of it that rises to a guard before the knee and leaves the calf black.
    form = skin.Form(SHIN_ROWS)
    over = geo.plate_yz(geo.polygon(*SHIN_RIM, (200, 700), (-200, 700)), -400, 400)
    panel, liner = geo.cut(form.panel, over, "shin panel's rim"), geo.cut(form.liner, over, "shin liner's rim")
    stripe = skin.from_side([(26, 560), (20, 440), (10, 300), (-2, 120)], [(22, 120), (34, 300), (44, 440), (50, 560)])
    # Both plates end over the ankle in a point, drawn in the front view: the liner's black shows at the
    # hem's corners, so the pearl narrows to the foot where the form itself cannot (the ankle's fork is under it).
    tip = 163.0
    cuff = geo.polygon((xr(-90), 100), (xr(-90), tip + 94.5), (xr(0), tip), (xr(90), tip + 94.5), (xr(90), 100))
    cuff = bd.fillet(cuff.vertices().sort_by(lambda v: abs(v.X - xr(0)) + abs(v.Y - tip))[0], 22.0)
    panel = skin.trim(panel, [stripe, geo.plate_xz(cuff, -400, 400)], "greave and calf plate")   # a greave before and a plate behind, black between
    pads = None
    for origin, direction in [((xr(s * 42), y, z), (s, 0, 0)) for s in (1, -1) for y, z in ((-6, 255), (-8, 415))]:
        pad = geo.mount_pad(form.cavity, origin, direction)
        pads = pad if pads is None else pads + pad

    C = KNEE_HORN_PIN
    core = geo.tube(17, 10, 34, (xr(-17), 0, KZ), (1, 0, 0))
    flange = geo.bones([(0, KZ, 30), (C[1], C[2], 12)], holes=[(0, KZ, 10), (C[1], C[2], 5)])
    flanges = geo.plate_yz(flange, xr(7.5), xr(17)) + geo.plate_yz(flange, xr(-17), xr(-7.5))
    wishbone = geo.plate_xz(geo.bones([(HX, 488, 16), (HX, 452, 16), (xr(-42), 402, 9), (xr(42), 402, 9)],
                                      links=[(0, 1), (1, 2), (1, 3)]), -23, 7)   # a neck between the femur's lobes, then the fork
    wishbone -= geo.cyl(10, 40, KNEE, (1, 0, 0), centered=True)          # the knee axle passes through
    rail = geo.bones([(-6, 404, 16), (0, CAZ, 24), (-2, 215, 15), (0, AZ, 22)], holes=[(0, CAZ, 9), (0, AZ, 12)])
    rails = geo.plate_yz(rail, xr(R0), xr(R1)) + geo.plate_yz(rail, xr(-R1), xr(-R0))
    beam = geo.box(2 * R0 + 2, 28, 12, (HX, -2, CAZ + 68))               # over the calf drive
    tie = geo.cyl(7, 2 * R0 + 2, (xr(-R0 - 1), -8, 195), (1, 0, 0))
    # The calf drive: an RS04 across the leg between the rails, on a bracket hung from the beam,
    # its output outboard. Its crank carries one rod down the back of the shin.
    calf_at = (xr(CALF_FACE), CAY, CAZ)
    bracket = geo.plate_yz(geo.bones([(CAY, CAZ, 61), (-2, CAZ + 68, 14)]), xr(CALF_FACE), xr(CALF_FACE + PLATE_T))
    bracket -= mount_bores("RS04", calf_at, (1, 0, 0), x_dir=(0, 1, 0), turn=180.0)      # its connector underneath, clear of the wishbone
    stator, rotor = hw.actuator("RS04", calf_at, (1, 0, 0), x_dir=(0, 1, 0), name="ankle_pitch", turn=180.0)
    tibia = core + flanges + wishbone + rails + beam + tie + bracket
    links["shin"] += [part(tibia, "tibia", "frame"), *stator,
                      pin((xr(-17), C[1], C[2]), (1, 0, 0), 5.0, 34.0, label="horn_pin"),
                      part(skin.solids(pads - tibia), "pad_shin", "frame"),
                      part(skin.solids(liner), "liner_shin", "under"), part(skin.solids(panel), "panel_shin", "shell")]
    P, Q = ANKLE_CRANK_PIN, ANKLE_ARM_PIN
    x0 = CALF_FACE + ROTOR_PROUD                                          # the hub's end
    arm = geo.plate_yz(geo.bones([(CAY, CAZ, 27), (P[1], P[2], 9)]), xr(x0), xr(x0 + 8))
    arm -= rotor_counterbores("RS04", calf_at, (1, 0, 0), 8.0, x_dir=(0, 1, 0))
    rod_x = xr(ANKLE_ROD_X)
    links["ankle_crank"] += [*rotor, part(arm, "calf_crank", "steel"),
                             *hw.rotor_screws("RS04", calf_at, (1, 0, 0), 8.0, x_dir=(0, 1, 0), sunk=5.0),
                             pin((xr(x0 + 8), P[1], P[2]), (1, 0, 0), 4.0, rod_x + 5.0 - xr(x0 + 8), label="crank_pin")]
    links["ankle_rods"].append(pushrod((rod_x, P[1], P[2]), (rod_x, Q[1], Q[2]), ANKLE_ROD_R, 8.0, 7.0, 4.0,
                                       label="achilles_rod", finish="steel", nut_af=7.0))


# ---------------------------------------------------------------------------------------------
# Ankle gimbal (pitch) with the roll actuator as its axle
# ---------------------------------------------------------------------------------------------
def _ankle(hw, links):
    Q = ANKLE_ARM_PIN
    roll_at = (HX, -4.0, AZ)
    gimbal = geo.plate_xz(geo.bones([(HX, AZ, 30)], links=[(0,)]), -4, 4) - mount_bores("RS00", roll_at, (0, 1, 0), x_dir=(-1, 0, 0))
    for s in (1, -1):
        gimbal += geo.plate_yz(geo.hull([(0, AZ, 12), (10, AZ, 12)]), xr(s * 30), xr(s * 39))
        gimbal += geo.cyl(12, R1 - 39, (xr(s * 39), 0, AZ), (s, 0, 0))
    gimbal += geo.plate_yz(geo.bones([(14, AZ, 9), (Q[1], Q[2], 9)], holes=[(Q[1], Q[2], 4)]), xr(24), xr(30))   # the rod's arm
    pins = [pin((xr(24), Q[1], Q[2]), (1, 0, 0), 4.0, 16.0, label="achilles_pin"),
            part(geo.cyl(6, 1.5, (xr(40), Q[1], Q[2]), (1, 0, 0)), "achilles_pin_head", "steel")]
    stator, rotor = hw.actuator("RS00", roll_at, (0, 1, 0), x_dir=(-1, 0, 0), name="ankle_roll")
    links["ankle_gimbal"] += [part(gimbal, "ankle_gimbal", "frame"), *pins, *stator]
    links["foot"] += [*rotor, *hw.rotor_screws("RS00", roll_at, (0, 1, 0), 10.0, x_dir=(-1, 0, 0))]


# ---------------------------------------------------------------------------------------------
# Foot and toe
# ---------------------------------------------------------------------------------------------
def _foot(hw, links):
    TY, TZ = TOE[1], TOE[2]
    along = frame((HX, 0, 0), z_dir=(0, -1, 0), x_dir=(1, 0, 0))     # loft frame: local Z forward, local Y up

    # Foot shell: a low rand round the sole, rising to a cup at the heel.
    rows = [
        geo.S(-74, 0, 18, rx=31, ry=40, n=3.2, ryn=12),
        geo.S(-45, 0, 18, rx=41, ry=42, n=3.2, ryn=12),
        geo.S(0, 1, 17, rx=48, ry=34, n=3.2, ryn=11),
        geo.S(60, 2.5, 16, rx=52, ry=28, n=3.2, ryn=10),
        geo.S(112, 3, 15, rx=53, ry=23, n=3.2, ryn=9),
    ]
    skin, cavity, shell_outer = (along * s for s in geo.shell(rows, SKIN_T, bottom=(0, 20, -85), tip=8.0))   # a blunt heel: its point is a dimple 10 across
    rim = geo.polygon((95, 58), (62, 56), (36, 41), (0, 36), (-80, 34), (-125, 34), (-125, 140), (95, 140))
    skin -= geo.half_space((0, 0, 10.5), (0, 0, -1))
    skin -= geo.plate_yz(rim, xr(-90), xr(90))
    # A deck closes the shell just under its rim, with a well for the ankle's uprights and the keel between them.
    deck = geo.box(240, 320, SKIN_T, (HX, -20, DECK_Z - SKIN_T / 2)) & shell_outer
    skin += deck - geo.plate_xy(geo.slot(HX, -62, HX, 10, 20), 0, 60)
    skin -= geo.cyl(26, 240, TOE, (1, 0, 0), centered=True)               # round opening about the toe hinge
    skin -= geo.half_space((0, TY + 8.5, 0), (0, -1, 0))
    pads, screws = _skin_mounts(hw, cavity, shell_outer, [((xr(s * 28), y, 15), (s, 0, 0))
                                                         for s in (1, -1) for y in (34, -62)], size="M3", radius=4.5)

    edge = TY + 8.0                                            # the sole plate stops short of the hinge
    outline = geo.hull([(HX, 40, 31), (xr(3), -40, 38), (xr(3), -88, 42)])
    sole = geo.plate_xy(outline, 10, 20) - geo.box(240, 120, 40, (HX, edge - 60, 15))
    rear = geo.plate_xz(geo.bones([(HX, AZ, 19), (HX, 26, 15)], holes=[(HX, AZ, 4)]), 5, 15)
    front = geo.plate_xz(geo.bones([(HX, AZ, 12), (HX, 26, 12)]), -76, -66)
    tail = geo.cyl(3.4, 10.7, (HX, -66, AZ), (0, 1, 0))                  # to the back of the roll drive's cover
    keel = geo.box(12, 71, 12, (HX, -30.5, 26))
    foot = sole + rear + front + tail + keel + pads
    for a, b in ((-40, -24), (-8, 8), (24, 40)):
        foot += geo.cyl(7, b - a, (xr(a), TY, TZ), (1, 0, 0)) + geo.box(b - a, 9, 10, (xr((a + b) / 2), TY + 4.5, 15))
    foot -= geo.cyl(3, 100, (xr(-50), TY, TZ), (1, 0, 0))

    def tread(pad, ys):
        for y in ys:
            pad -= geo.box(140, 3, 4, (HX, y, 0))
        return pad

    heel_pad = tread(geo.plate_xy(geo.hull([(HX, 40, 28), (xr(1), 12, 30)]), 0, 10), (60, 46, 32, 18, 4))
    ball_pad = geo.plate_xy(geo.hull([(xr(3), -62, 37), (xr(3), -88, 41)]), 0, 10) - geo.box(240, 120, 40, (HX, edge - 60, 5))
    ball_pad = tread(ball_pad, (-48, -62, -76, -90, -104))
    links["foot"] += [part(foot, "foot_frame", "frame"), part(heel_pad, "heel_pad", "rubber"),
                      part(ball_pad, "ball_pad", "rubber"),
                      pin((xr(-41), TY, TZ), (1, 0, 0), 3.0, 82.0, label="toe_pin"),
                      part(skin, "foot_shell", "shell")]

    # Toe: a sprung plate on a barrel hinge under its own cap.
    rows = [
        geo.S(126.5, 3, 15, rx=53, ry=23, n=3.2, ryn=9),
        geo.S(150, 2.5, 15, rx=50, ry=21, n=3.1, ryn=9),
        geo.S(168, 2, 14.5, rx=42, ry=17, n=2.9, ryn=8.5),
        geo.S(180, 1.5, 14, rx=28, ry=12.5, n=2.6, ryn=8),
    ]
    cap, cap_cavity, cap_outer = (along * s for s in geo.shell(rows, SKIN_T, top=(1.5, 14.5, 187), seam=270.0))
    cap -= geo.half_space((0, 0, 10.5), (0, 0, -1))
    cap -= geo.cyl(10, 240, TOE, (1, 0, 0), centered=True)
    back = TY - 8.0
    cap_pads, cap_screws = _skin_mounts(hw, cap_cavity, cap_outer, [((xr(s * 20), -146, 15), (s, 0, 0)) for s in (1, -1)],
                                        size="M3", radius=4.5)
    toe_outline = geo.hull([(xr(-15), -152, 22), (xr(18), -150, 25), (xr(-37), back - 3, 3), (xr(43), back - 3, 3)])
    toe = geo.plate_xy(toe_outline, 10, 20) + cap_pads
    for a, b in ((-23, -9), (9, 23)):
        toe += geo.cyl(7, b - a, (xr(a), TY, TZ), (1, 0, 0)) + geo.box(b - a, 9, 10, (xr((a + b) / 2), TY - 4.5, 15))
    toe -= geo.cyl(3, 100, (xr(-50), TY, TZ), (1, 0, 0))
    toe_pad = geo.plate_xy(geo.hull([(xr(-15), -152, 20), (xr(18), -150, 23), (xr(-35), back - 5, 3), (xr(41), back - 5, 3)]),
                           0, 10)
    toe_pad = tread(toe_pad, (-140, -154))
    links["toe"] += [part(toe, "toe_plate", "frame"), part(toe_pad, "toe_pad", "rubber"),
                     part(cap, "toe_cap", "shell")]

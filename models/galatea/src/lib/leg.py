"""The left leg at the zero pose, link by link. `dims.py` holds the skeleton it is built on.

Hip: three actuators whose axes meet at one point. The yaw actuator sits in the pelvis
and turns the hip yoke; the roll actuator on the back of the yoke turns the cradle; the
pitch actuator on the outside of the cradle turns the femur.

Knee: a rotary actuator high on the femur turns a crank between the femur plates; a
pushrod carries the motion down to the horn behind the knee hub. Crank and horn are
equal and parallel, so the linkage is a parallelogram and the knee follows the actuator
one to one, with the motor's mass up at the hip.

Ankle: a double-ended drive between the shin rails turns twin cranks; two pushrods run
down the back of the shin to the ankle gimbal (pitch). The roll actuator is the gimbal's
own axle, lying along the foot.

Skins are thin lofted shells. Each is trimmed by a cylinder about every axis it borders
(the knee actuator, the knee, the ankle, the toe hinge), so a joint always turns inside a
round opening, and each is carried on pads that grow from the frame to its inner surface.
"""

from . import geo
from .dims import (
    ANKLE, ANKLE_ACT, ANKLE_ARM_PIN, ANKLE_CRANK_PIN, ANKLE_ROD_R, ANKLE_ROD_X, CRADLE_CHEEK_X, FEMUR_PLATE_X, HIP,
    KNEE, KNEE_ACT, KNEE_CRANK_PIN, KNEE_HORN_PIN, KNEE_ROD_R, PELVIS_Z, PLATE_T, SHIN_RAIL_X, TOE,
)
from .hardware import pin, pushrod, rotor_counterbores
from .kit import frame, part

HX, HZ = HIP[0], HIP[2]
KZ, AZ, KAZ, CAZ = KNEE[2], ANKLE[2], KNEE_ACT[2], ANKLE_ACT[2]
C0, C1 = CRADLE_CHEEK_X
P0, P1 = FEMUR_PLATE_X
R0, R1 = SHIN_RAIL_X
SKIN_T = 2.6
DECK_Z = 33.5         # top of the foot shell's deck, half a millimetre under its rim
LEG_LINKS = ("hip_yoke", "hip_cradle", "thigh", "knee_crank", "knee_rod", "shin", "ankle_crank", "ankle_rods",
             "ankle_gimbal", "foot", "toe")


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
    stator, rotor = hw.actuator("A86", yaw_at, (0, 0, -1), x_dir=(-1, 0, 0), name="hip_yaw")
    links["pelvis"] += stator

    top = geo.plate_xy(geo.bones([(HX, 0, 40), (HX, 50, 30)], holes=[(HX, 0, 8)]), zb, zt)
    rear = geo.plate_xz(geo.bones([(HX, HZ, 47), (HX, zt - 30, 30)], holes=[(HX, HZ, 27)]), 64, 72)
    rib = geo.polygon((64, zb), (30, zb), (64, zb - 26))
    yoke = top + rear + geo.plate_yz(rib, xr(21), xr(27)) + geo.plate_yz(rib, xr(-27), xr(-21))
    roll_at = (HX, 72.0, HZ)
    roll_stator, roll_rotor = hw.actuator("A86", roll_at, (0, -1, 0), x_dir=(1, 0, 0), name="hip_roll")
    links["hip_yoke"] += [part(yoke, "hip_yoke", "gunmetal"), *rotor,
                          *hw.rotor_screws("A86", yaw_at, (0, 0, -1), 10.0, x_dir=(-1, 0, 0)), *roll_stator]

    back = geo.plate_xz(geo.bones([(xr(-25), 894, 10), (xr(25), 894, 10), (xr(25), 940, 10), (xr(-25), 940, 10)],
                                  links=[(0, 1, 2, 3)], holes=[(HX, HZ, 8)]), 53, 63)
    outer = geo.plate_yz(geo.bones([(0, HZ, 58), (40, HZ - 3, 23)], holes=[(0, HZ, 35)]), xr(C0), xr(C1))
    inner = geo.plate_yz(geo.bones([(0, HZ, 40), (40, HZ - 3, 23)], holes=[(0, HZ, 14)]), xr(-C1), xr(-C0))
    pitch_at = (xr(C1), 0.0, HZ)
    pitch_stator, pitch_rotor = hw.actuator("A110", pitch_at, (-1, 0, 0), x_dir=(0, -1, 0), cover=True, name="hip_pitch")
    links["hip_cradle"] += [part(back + outer + inner, "hip_cradle", "gunmetal"), *roll_rotor,
                            *hw.rotor_screws("A86", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0)), *pitch_stator,
                            hw.pivot_cap(19, (xr(-C1), 0, HZ), (-1, 0, 0), label="hip_bearing_cap")]
    links["thigh"] += [*pitch_rotor, *hw.rotor_screws("A110", pitch_at, (-1, 0, 0), PLATE_T, x_dir=(0, -1, 0))]


# ---------------------------------------------------------------------------------------------
# Thigh: the femur, two plates with the knee drive between them, and its fairing
# ---------------------------------------------------------------------------------------------
def _thigh(hw, links):
    rows = [
        geo.S(538, HX + 0, -5, rx=44, ry=38, n=2.6, rxn=42, ryn=48),
        geo.S(600, HX + 1, -6, rx=48, ry=42, n=2.6, rxn=45, ryn=57),
        geo.S(680, HX + 2, -7, rx=52, ry=46, n=2.5, rxn=48, ryn=64),
        geo.S(760, HX + 2, -7, rx=57, ry=50, n=2.5, rxn=53, ryn=70),
        geo.S(830, HX + 2, -6, rx=59, ry=50, n=2.5, rxn=55, ryn=71),
        geo.S(890, HX + 2, -5, rx=58, ry=48, n=2.5, rxn=55, ryn=68),
    ]
    skin, cavity, shell_outer = geo.shell(rows, SKIN_T)
    back_edge = geo.behind_curve([(8, 520), (26, 600), (30, 680), (22, 750), (0, 800), (-22, 850), (-34, 910)], [(160, 910), (160, 520)])
    skin -= geo.plate_yz(back_edge, xr(-90), xr(90))                     # open to the back: the pushrod's channel
    skin -= geo.half_space((HX, 0, 856), (0.3, 0.0, 1.0))                # top edge, falling toward the outside
    skin -= geo.cyl(62, 240, HIP, (1, 0, 0), centered=True)              # round openings about the hip drive
    skin -= geo.cyl(62, 240, KNEE_ACT, (1, 0, 0), centered=True)         # and the knee drive
    skin -= geo.cyl(50, 240, KNEE, (1, 0, 0), centered=True)             # arch over the knee
    reveal = geo.band([(xr(-70), 706), (xr(-20), 692), (xr(30), 670), (xr(70), 640)], 2.2)
    skin -= geo.plate_xz(reveal, -200, -12)                              # a reveal line across the front
    pads, screws = _skin_mounts(hw, cavity, shell_outer, [((xr(s * 20), -14, z), (s, 0, 0))
                                                         for s in (1, -1) for z in (600, 715)])

    circles = [(0, HZ, 44), (0, KAZ, 58), (-4, HZ, 26), (-4, KAZ, 26), (0, KAZ, 40), (-2, 650, 27), (0, KZ, 34)]
    chain = [(0,), (1,), (2, 3), (4, 5), (5, 6)]
    window = geo.slot(-2, 705, -2, 585, 9)
    outer = geo.plate_yz(geo.bones(circles, chain, holes=[(0, HZ, 10), (0, KAZ, 35), (0, KZ, 10)], cuts=[window]),
                         xr(P0), xr(P1))
    slim = [(0, KAZ, 40) if k == 1 else c for k, c in enumerate(circles)]       # no drive to carry on the inside
    inner = geo.plate_yz(geo.bones(slim, chain, holes=[(0, KAZ, 12), (0, KZ, 10)], cuts=[window]), xr(-P1), xr(-P0))
    web_low = geo.box(2 * P0 + 2, 6, 190, (HX, -26, 640))
    web_high = geo.box(2 * P0 + 2, 6, 42, (HX, -26, 864))
    spacer = geo.tube(22, 10, 2 * P0 + 2, (xr(-P0 - 1), 0, HZ), (1, 0, 0))
    stub = geo.cyl(14, C1 - P1, (xr(-P1), 0, HZ), (-1, 0, 0))
    femur = outer + inner + web_low + web_high + spacer + stub + pads

    knee_at = (xr(P1), 0.0, KAZ)
    stator, rotor = hw.actuator("A110", knee_at, (-1, 0, 0), x_dir=(0, -1, 0), cover=True, name="knee")
    links["thigh"] += [part(femur, "femur", "gunmetal"), *stator,
                       pin((xr(-P1), 0, KZ), (1, 0, 0), 10.0, 2 * P1, label="knee_axle"),
                       hw.pivot_cap(17, (xr(P1), 0, KZ), (1, 0, 0), label="knee_cap"),
                       hw.pivot_cap(17, (xr(-P1), 0, KZ), (-1, 0, 0), label="knee_cap"),
                       part(skin, "thigh_fairing", "ivory"), *screws]
    links["knee_crank"] += rotor


def _knee_drive(hw, links):
    B, C = KNEE_CRANK_PIN, KNEE_HORN_PIN
    knee_at = (xr(P1), 0.0, KAZ)
    outer = geo.plate_yz(geo.bones([(0, KAZ, 34), (B[1], B[2], 13)], holes=[(0, KAZ, 6), (B[1], B[2], 5)]),
                         xr(8), xr(17))
    inner = geo.plate_yz(geo.bones([(0, KAZ, 20), (B[1], B[2], 13)], holes=[(B[1], B[2], 5)]), xr(-17), xr(-8))
    stub = geo.cyl(12, P1 - 17, (xr(-17), 0, KAZ), (-1, 0, 0))
    crank = outer + inner + stub - rotor_counterbores("A110", knee_at, (-1, 0, 0), 9.0, x_dir=(0, -1, 0))
    links["knee_crank"] += [part(crank, "knee_crank", "slate"),
                            pin((xr(-17), B[1], B[2]), (1, 0, 0), 5.0, 34.0, label="crank_pin"),
                            *hw.rotor_screws("A110", knee_at, (-1, 0, 0), 9.0, x_dir=(0, -1, 0), sunk=5.0)]
    links["knee_rod"] += [pushrod(B, C, KNEE_ROD_R, 10.0, 13.0, 5.0, label="knee_pushrod")]


# ---------------------------------------------------------------------------------------------
# Shin: the tibia (spool hub, wishbone, two rails), the calf drive and the shin guard
# ---------------------------------------------------------------------------------------------
def _calf_housing():
    half, r_tip, r_root, pitch = 24.0, 36.0, 32.0, 5.25
    pts = [(9.6, -half), (33.0, -half), (33.0, -21.0)]
    z = -21.0
    while z < 21.0 - 1e-6:
        pts += [(r_root, z), (r_root, z + pitch / 2), (r_tip, z + pitch / 2), (r_tip, z + pitch)]
        z += pitch
    pts += [(33.0, 21.0), (33.0, half), (9.6, half)]
    body = geo.revolve(pts, origin=ANKLE_ACT, axis=(1, 0, 0))
    saddle = geo.box(44, 26, 9, (HX, -2, CAZ + 34.5))         # hangs from the tibia's cross-beam at z = CAZ + 39
    return body + saddle


def _shin(hw, links):
    rows = [
        geo.S(118, HX, 0, rx=50, ry=28, n=2.6, ryn=40),
        geo.S(170, HX, -1, rx=51, ry=28, n=2.6, ryn=44),
        geo.S(255, HX, -2, rx=54, ry=40, n=2.5, ryn=52),
        geo.S(345, HX, -2, rx=58, ry=50, n=2.5, ryn=60),
        geo.S(430, HX, -2, rx=56, ry=46, n=2.5, ryn=59),
        geo.S(492, HX, -2, rx=49, ry=36, n=2.5, ryn=57),
        geo.S(536, HX, -2, rx=41, ry=26, n=2.6, ryn=50),
    ]
    skin, cavity, shell_outer = geo.shell(rows, SKIN_T)
    back_edge = geo.behind_curve([(2, 100), (4, 200), (13, 300), (23, 395), (15, 480), (3, 550)], [(160, 550), (160, 100)])
    skin -= geo.plate_yz(back_edge, xr(-90), xr(90))                     # open to the back: calf drive and rods
    skin -= geo.cyl(80, 240, ANKLE, (1, 0, 0), centered=True)            # arch over the ankle
    reveal = geo.band([(xr(-70), 478), (xr(-34), 452), (xr(0), 442), (xr(34), 452), (xr(70), 478)], 2.2)
    skin -= geo.plate_xz(reveal, -200, -6)                               # the kneecap's reveal line
    pads, screws = _skin_mounts(hw, cavity, shell_outer, [((xr(s * 42), y, z), (s, 0, 0))
                                                         for s in (1, -1) for y, z in ((-6, 255), (-8, 415))])

    C = KNEE_HORN_PIN
    core = geo.tube(17, 10, 34, (xr(-17), 0, KZ), (1, 0, 0))
    flange = geo.bones([(0, KZ, 30), (C[1], C[2], 12)], holes=[(0, KZ, 10), (C[1], C[2], 5)])
    flanges = geo.plate_yz(flange, xr(7.5), xr(17)) + geo.plate_yz(flange, xr(-17), xr(-7.5))
    wishbone = geo.plate_xz(geo.bones([(HX, 488, 16), (HX, 452, 16), (xr(-42), 402, 9), (xr(42), 402, 9)],
                                      links=[(0, 1), (1, 2), (1, 3)]), -23, 7)   # a neck between the femur's lobes, then the fork
    wishbone -= geo.cyl(10, 40, KNEE, (1, 0, 0), centered=True)          # the knee axle passes through
    rail = geo.bones([(-6, 404, 16), (0, CAZ, 24), (-2, 215, 15), (0, AZ, 22)], holes=[(0, CAZ, 9), (0, AZ, 12)])
    rails = geo.plate_yz(rail, xr(R0), xr(R1)) + geo.plate_yz(rail, xr(-R1), xr(-R0))
    beam = geo.box(2 * R0 + 2, 28, 12, (HX, -2, CAZ + 45))               # the calf drive hangs from this
    tie = geo.cyl(7, 2 * R0 + 2, (xr(-R0 - 1), -8, 195), (1, 0, 0))
    tibia = core + flanges + wishbone + rails + beam + tie + pads
    links["shin"] += [part(tibia, "tibia", "gunmetal"),
                      pin((xr(-17), C[1], C[2]), (1, 0, 0), 5.0, 34.0, label="horn_pin"),
                      part(_calf_housing(), "calf_drive", "bronze"),
                      part(skin, "shin_guard", "ivory"), *screws]
    links["shin"] += [hw.screw("M4", (xr(sx * 14), -2 + sy * 8, CAZ + 51), (0, 0, 1)) for sx in (1, -1) for sy in (1, -1)]

    P, Q = ANKLE_CRANK_PIN, ANKLE_ARM_PIN
    crank = geo.cyl(9, 2 * R1, (xr(-R1), 0, CAZ), (1, 0, 0))
    arm = geo.bones([(0, CAZ, 15), (P[1], P[2], 9)])
    for s in (1, -1):
        crank += geo.plate_yz(arm, xr(s * 25), xr(s * 30))
        crank += geo.cyl(4, 13, (xr(s * 25), P[1], P[2]), (s, 0, 0))
        crank += geo.cyl(6, 1.5, (xr(s * 38), P[1], P[2]), (s, 0, 0))
    links["ankle_crank"] += [part(crank, "calf_crankshaft", "steel")]
    for s, name in ((1, "outer"), (-1, "inner")):
        x = xr(s * ANKLE_ROD_X)
        links["ankle_rods"].append(pushrod((x, P[1], P[2]), (x, Q[1], Q[2]), ANKLE_ROD_R, 8.0, 7.0, 4.0,
                                           label=f"achilles_rod_{name}", finish="steel", nut_af=6.3))


# ---------------------------------------------------------------------------------------------
# Ankle gimbal (pitch) with the roll actuator as its axle
# ---------------------------------------------------------------------------------------------
def _ankle(hw, links):
    Q = ANKLE_ARM_PIN
    gimbal = geo.plate_xz(geo.bones([(HX, AZ, 30)], links=[(0,)], holes=[(HX, AZ, 16)]), -4, 4)
    pins = []
    for s in (1, -1):
        gimbal += geo.plate_yz(geo.hull([(0, AZ, 12), (10, AZ, 12)]), xr(s * 27), xr(s * 39))
        gimbal += geo.plate_yz(geo.bones([(14, AZ, 9), (Q[1], Q[2], 9)], holes=[(Q[1], Q[2], 4)]), xr(s * 24), xr(s * 30))
        gimbal += geo.cyl(12, R1 - 39, (xr(s * 39), 0, AZ), (s, 0, 0))
        pins.append(pin((xr(s * 24), Q[1], Q[2]), (s, 0, 0), 4.0, 14.0, label="achilles_pin"))
        pins.append(part(geo.cyl(6, 1.5, (xr(s * 38), Q[1], Q[2]), (s, 0, 0)), "achilles_pin_head", "steel"))
    roll_at = (HX, -4.0, AZ)
    stator, rotor = hw.actuator("A52L", roll_at, (0, 1, 0), x_dir=(-1, 0, 0), name="ankle_roll")
    links["ankle_gimbal"] += [part(gimbal, "ankle_gimbal", "gunmetal"), *pins, *stator]
    links["foot"] += [*rotor, *hw.rotor_screws("A52L", roll_at, (0, 1, 0), 10.0, x_dir=(-1, 0, 0))]


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
    skin, cavity, shell_outer = (along * s for s in geo.shell(rows, SKIN_T, bottom=(0, 20, -85)))
    rim = geo.polygon((95, 58), (62, 56), (36, 41), (0, 36), (-80, 34), (-125, 34), (-125, 140), (95, 140))
    skin -= geo.half_space((0, 0, 10.5), (0, 0, -1))
    skin -= geo.plate_yz(rim, xr(-90), xr(90))
    # A deck closes the shell just under its rim, with a well for the ankle's uprights and the keel between them.
    deck = geo.box(240, 320, SKIN_T, (HX, -20, DECK_Z - SKIN_T / 2)) & shell_outer
    skin += deck - geo.plate_xy(geo.slot(HX, -62, HX, 1, 20), 0, 60)
    skin -= geo.cyl(26, 240, TOE, (1, 0, 0), centered=True)               # round opening about the toe hinge
    skin -= geo.half_space((0, TY + 8.5, 0), (0, -1, 0))
    pads, screws = _skin_mounts(hw, cavity, shell_outer, [((xr(s * 28), y, 15), (s, 0, 0))
                                                         for s in (1, -1) for y in (34, -62)], size="M3", radius=4.5)

    edge = TY + 8.0                                            # the sole plate stops short of the hinge
    outline = geo.hull([(HX, 40, 31), (xr(3), -40, 38), (xr(3), -88, 44)])
    sole = geo.plate_xy(outline, 10, 20) - geo.box(240, 120, 40, (HX, edge - 60, 15))
    rear = geo.plate_xz(geo.bones([(HX, AZ, 19), (HX, 26, 15)], holes=[(HX, AZ, 4)]), 5, 15)
    front = geo.plate_xz(geo.bones([(HX, AZ, 12), (HX, 26, 12)]), -76, -66)
    tail = geo.cyl(3.4, 30, (HX, -66, AZ), (0, 1, 0))
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
    links["foot"] += [part(foot, "foot_frame", "gunmetal"), part(heel_pad, "heel_pad", "rubber"),
                      part(ball_pad, "ball_pad", "rubber"),
                      pin((xr(-41), TY, TZ), (1, 0, 0), 3.0, 82.0, label="toe_pin"),
                      part(skin, "foot_shell", "ivory"), *screws]

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
    links["toe"] += [part(toe, "toe_plate", "gunmetal"), part(toe_pad, "toe_pad", "rubber"),
                     part(cap, "toe_cap", "ivory"), *cap_screws]

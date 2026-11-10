"""The left arm at the zero pose: hanging, palm toward the thigh, thumb forward.

Shoulder: three axes through one point. The pitch drive sits in the chest and turns the
yoke; the roll drive on the back of the yoke turns the shoulder block, which wears the
ivory ball; the yaw drive sits in the top of the upper arm, its output bolted up into
the block, so the arm turns under the ball.

Elbow, wrist pitch and wrist yaw are in-line hinges: the drive is the joint's hub, its
stator on one link's side plate and its output on the next link's lug. The forearm turns
on a drive just under the elbow.
"""

import math

import build123d as bd

from . import geo
from .dims import CHEST_SIDE_X, ELBOW, PLATE_T, SHOULDER, WRIST, WRIST_ROLL, WRIST_YAW
from .kit import part

SX, SZ = SHOULDER[0], SHOULDER[2]
EZ, WZ, YZ = ELBOW[2], WRIST[2], WRIST_YAW[2]
RZ = WRIST_ROLL[2]
SKIN_T = 2.6
BALL_R = 46.0
ARM_LINKS = ("shoulder_yoke", "shoulder_block", "upper_arm", "forearm", "forearm_distal", "wrist_link")


def build_arm(hw, shoulder_pitch_output):
    """Every part of the left arm above the hand, by link; `palm` collects the wrist's output."""
    links = {name: [] for name in (*ARM_LINKS, "palm")}
    links["shoulder_yoke"] += shoulder_pitch_output
    _shoulder(hw, links)
    _upper_arm(hw, links)
    _forearm(hw, links)
    _wrist(hw, links)
    return links


def _skin_mounts(hw, cavity, outer, seats, size="M3", radius=5.0, reach=80.0):
    pads, screws = None, []
    for origin, direction in seats:
        pad = geo.mount_pad(cavity, origin, direction, radius, reach)
        pads = pad if pads is None else pads + pad
        screws.append(hw.screw(size, *geo.seat(outer, origin, direction), label="skin_screw"))
    return pads, screws


# ---------------------------------------------------------------------------------------------
# Shoulder: yoke (pitch), block and ball (roll)
# ---------------------------------------------------------------------------------------------
def _shoulder(hw, links):
    pitch_at = (CHEST_SIDE_X[0], 0.0, SZ)
    x0 = CHEST_SIDE_X[0] + 9.0                                           # the pitch output's face
    lug = geo.plate_yz(geo.bones([(0, SZ, 40)], links=[(0,)], holes=[(0, SZ, 8)]), x0, x0 + 10)
    # The arm to the roll drive leaves the chest through the round shoulder opening: inboard of
    # the skin it stays inside the opening's radius about the pitch axis.
    ring = geo.plate_xz(geo.bones([(SX, SZ, 39), (SX - 46, SZ, 24)], holes=[(SX, SZ, 22)]), 34, 42)
    ring -= geo.half_space((x0, 0, 0), (-1, 0, 0))
    corner = geo.box(16, 18, 40, (160, 51, SZ))
    roll_at = (SX, 42.0, SZ)
    stator, rotor = hw.actuator("A70", roll_at, (0, -1, 0), x_dir=(1, 0, 0), cover=True, name="shoulder_roll")
    links["shoulder_yoke"] += [part(lug + ring + corner, "shoulder_yoke", "gunmetal"),
                               *hw.rotor_screws("A86", pitch_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0)), *stator]

    lug = geo.plate_xz(geo.bones([(SX, SZ, 30)], links=[(0,)], holes=[(SX, SZ, 6)]), 23, 33)
    cup = geo.tube(22, 15, 17, (SX, 0, SZ - 36), (0, 0, 1)) + geo.tube(22, 5, 10, (SX, 0, SZ - 36), (0, 0, 1))
    neck = geo.box(24, 12, 9, (SX, 18, SZ - 25.5))
    ball = bd.Pos(*SHOULDER) * (bd.Sphere(BALL_R) - bd.Sphere(BALL_R - SKIN_T))
    ball -= geo.half_space((0, 22, 0), (0, 1, 0))                         # open behind, where the yoke carries it
    ball -= geo.cyl(29, 70, (SX, 0, SZ - 70), (0, 0, 1))                  # round opening for the arm
    inside = bd.Pos(*SHOULDER) * bd.Sphere(BALL_R - SKIN_T)
    pads, screws = None, []
    for s in (1, -1):
        pad = geo.cyl(5, 40, (SX + s * 18, 0, SZ - 27), (s, 0, 0)) & inside
        pads = pad if pads is None else pads + pad
        reach = math.sqrt(BALL_R ** 2 - 27 ** 2)
        screws.append(hw.screw("M3", (SX + s * reach, 0, SZ - 27), (s * reach, 0, -27), label="skin_screw"))
    yaw_at = (SX, 0.0, SZ - 45)
    yaw_stator, yaw_rotor = hw.actuator("A52", yaw_at, (0, 0, 1), x_dir=(1, 0, 0), name="shoulder_yaw")
    links["shoulder_block"] += [part(lug + cup + neck + pads, "shoulder_block", "gunmetal"), *rotor,
                                *hw.rotor_screws("A70", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0)),
                                part(ball, "shoulder_ball", "ivory"), *screws, *yaw_rotor,
                                *hw.rotor_screws("A52", yaw_at, (0, 0, 1), 10.0, x_dir=(1, 0, 0))]
    links["upper_arm"] += yaw_stator


# ---------------------------------------------------------------------------------------------
# Upper arm
# ---------------------------------------------------------------------------------------------
def _upper_arm(hw, links):
    rows = [
        geo.S(1150, SX + 2, 0, rx=37, ry=37, n=2.5, rxn=35),
        geo.S(1215, SX + 2, 0, rx=41, ry=41, n=2.5, rxn=37),
        geo.S(1290, SX + 1, 0, rx=42, ry=43, n=2.4, rxn=39),
        geo.S(1345, SX, 0, rx=39, ry=39, n=2.3),
        geo.S(1378, SX, 0, rx=36, ry=36, n=2.1),
    ]
    skin, cavity, outer = geo.shell(rows, SKIN_T, seam=180.0)
    skin -= geo.cyl(46, 200, ELBOW, (1, 0, 0), centered=True)             # round opening about the elbow
    relief = geo.behind_curve([(-80, 1262), (-30, 1232), (0, 1196), (12, 1150)], [(-80, 1150)])
    skin -= geo.plate_yz(relief, SX - 80, SX + 80)                        # cut back in front, where the forearm folds in
    pads, screws = _skin_mounts(hw, cavity, outer, [((SX + 20, 0, z), (1, 0, 0)) for z in (1215, 1295)])

    top = geo.tube(32, 16, PLATE_T, (SX, 0, SZ - 45), (0, 0, 1))
    housing = geo.tube(32, 27.5, 48, (SX, 0, SZ - 93), (0, 0, 1)) + geo.tube(32, 6, 8, (SX, 0, SZ - 101), (0, 0, 1))
    windows = None
    for k in range(6):                                                    # windows on the yaw drive's fins
        a = math.radians(30 + 60 * k)
        slot = geo.rod((SX + 20 * math.cos(a), 20 * math.sin(a), SZ - 72), (SX + 40 * math.cos(a), 40 * math.sin(a), SZ - 72), 6.0)
        windows = slot if windows is None else windows + slot
    housing -= windows
    plate = geo.plate_yz(geo.bones([(0, SZ - 124, 26), (6, 1240, 16), (10, 1180, 13), (0, EZ, 39)], holes=[(0, EZ, 22)]), SX + 17, SX + 25)
    ribs = geo.box(26, 6, 140, (SX + 12, 20, 1245))                       # one rib, behind: the forearm folds in front
    elbow_at = (SX + 17, 0.0, EZ)
    stator, rotor = hw.actuator("A70", elbow_at, (1, 0, 0), x_dir=(0, 1, 0), cover=True, name="elbow")
    links["upper_arm"] += [part(top + housing + plate + ribs + pads, "humerus", "gunmetal"), *stator,
                           part(skin, "upper_arm_fairing", "ivory"), *screws]
    links["forearm"] += [*rotor, *hw.rotor_screws("A70", elbow_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0))]


# ---------------------------------------------------------------------------------------------
# Forearm: the elbow lug and roll drive, then the turning half
# ---------------------------------------------------------------------------------------------
def _forearm(hw, links):
    lug = geo.plate_yz(geo.bones([(0, EZ, 30), (0, RZ + 24, 22)], holes=[(0, EZ, 6)]), SX + 26, SX + 36)
    mount = geo.tube(31, 16, PLATE_T, (SX, 0, RZ + 1), (0, 0, 1))
    housing = geo.tube(31, 27.5, 38, (SX, 0, RZ + 9), (0, 0, 1))
    cuff = geo.tube(34.6, 32.0, 46, (SX, 0, RZ + 3), (0, 0, 1)) - geo.cyl(46, 200, ELBOW, (1, 0, 0), centered=True) \
        - geo.box(30, 50, 80, (SX + 34, 0, RZ + 30))
    cuff_pad = geo.tube(32.0, 31.0, 10, (SX, 0, RZ + 12), (0, 0, 1)) - geo.box(30, 50, 80, (SX + 34, 0, RZ + 30))
    roll_at = (SX, 0.0, RZ + 9)
    stator, rotor = hw.actuator("A52", roll_at, (0, 0, -1), x_dir=(1, 0, 0), name="wrist_roll")
    links["forearm"] += [part(lug + mount + housing + cuff_pad, "elbow_bracket", "gunmetal"), *stator,
                         part(cuff, "forearm_cuff", "ivory")]

    rows = [
        geo.S(940, SX, 0, rx=25, ry=27, n=2.3),
        geo.S(965, SX, 0, rx=28, ry=30, n=2.3),
        geo.S(1002, SX, 0, rx=33, ry=34, n=2.3),
        geo.S(RZ - 3, SX, 0, rx=33.5, ry=33.5, n=2.1),
    ]
    skin, cavity, outer = geo.shell(rows, SKIN_T, seam=180.0)
    skin -= geo.cyl(45, 200, WRIST, (0, 1, 0), centered=True)             # round opening about the wrist
    pads, screws = _skin_mounts(hw, cavity, outer, [((SX, s * 8, 1006), (0, s, 0)) for s in (1, -1)])
    lug = geo.tube(22, 5, 10, (SX, 0, RZ - 10), (0, 0, 1)) + geo.cyl(7, 8, (SX, 0, RZ - 18), (0, 0, 1))
    stem = geo.cyl(13, RZ - 18 - 955, (SX, 0, 955), (0, 0, 1))        # necked under the lug for its screw heads
    block = geo.cyl(21, 22, (SX, 0, 938), (0, 0, 1))
    fork = geo.plate_xz(geo.bones([(SX, WZ, 22), (SX, 944, 14)], holes=[(SX, WZ, 12.5)]), -22, -14)
    sleeve = geo.tube(16, 13, 30, (SX, 0, 962), (0, 0, 1))
    pitch_at = (SX, -14.0, WZ)
    wp_stator, wp_rotor = hw.actuator("A40", pitch_at, (0, -1, 0), x_dir=(1, 0, 0), name="wrist_pitch")
    links["forearm_distal"] += [*rotor, *hw.rotor_screws("A52", roll_at, (0, 0, -1), 10.0, x_dir=(1, 0, 0)),
                                part(lug + stem + block + fork + pads, "radius", "gunmetal"),
                                part(sleeve, "forearm_tube", "carbon"), part(skin, "forearm_fairing", "ivory"), *screws,
                                *wp_stator]
    links["wrist_link"] += [*wp_rotor, *hw.rotor_screws("A40", pitch_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0))]


def _wrist(hw, links):
    lug = geo.plate_xz(geo.bones([(SX, WZ, 16), (SX + 14, WZ - 30, 10)], holes=[(SX, WZ, 3)]), -33, -23)
    yaw_plate = geo.plate_yz(geo.bones([(0, YZ, 22), (-22, YZ + 16, 10)], holes=[(0, YZ, 12.5)]), SX + 14, SX + 22)
    yaw_at = (SX + 14, 0.0, YZ)
    stator, rotor = hw.actuator("A40", yaw_at, (1, 0, 0), x_dir=(0, 1, 0), name="wrist_yaw")
    links["wrist_link"] += [part(lug + yaw_plate, "wrist_bracket", "gunmetal"), *stator]
    links["palm"] += [*rotor, *hw.rotor_screws("A40", yaw_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0))]

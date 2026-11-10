"""The left arm at the zero pose: hanging, palm toward the thigh, thumb forward.

Shoulder: three axes through one point. The pitch drive sits in the chest and turns the
yoke; the roll drive on the back of the yoke turns the shoulder block, which wears the
shoulder's pod; the yaw drive sits in the top of the upper arm, its output bolted up into
the block, so the arm turns under the pod.

Elbow, wrist pitch and wrist yaw are in-line hinges: the drive is the joint's hub, its
stator on one link's side plate and its output on the next link's lug. The forearm turns
on a drive just under the elbow.
"""

import math

import build123d as bd

from . import geo, skin
from .dims import CHEST_SIDE_X, ELBOW, PLATE_T, SHOULDER, WRIST, WRIST_ROLL, WRIST_YAW
from .hardware import mount_bores, rotor_counterbores
from .kit import part

SX, SZ = SHOULDER[0], SHOULDER[2]
EZ, WZ, YZ = ELBOW[2], WRIST[2], WRIST_YAW[2]
RZ = WRIST_ROLL[2]
SKIN_T = 2.6
BALL_R = 46.0
RIM = 1.5                   # a sleeve's upper rim, in champagne: this much of the pearl panel's top
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


POD_R, POD_FRONT, POD_BACK = 52.0, 50.0, 108.0      # the shoulder pod: its radius about the roll axis, and how far it reaches


def _sector(a0, a1, radius, steps=24):
    """A pie slice in the plane of the roll's travel: angles from inboard (-X) toward up (+Z), degrees."""
    points = [(0.0, 0.0)]
    for k in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * k / steps)
        points.append((-radius * math.cos(a), radius * math.sin(a)))
    return points


def _skin_mounts(hw, cavity, outer, seats, size="M3", radius=5.0, reach=80.0):
    pads, screws = None, []
    for origin, direction in seats:
        pad = geo.mount_pad(cavity, origin, direction, radius, reach)
        pads = pad if pads is None else pads + pad
        screws.append(hw.screw(size, *geo.seat(outer, origin, direction), label="skin_screw"))
    return pads, screws


# ---------------------------------------------------------------------------------------------
# Shoulder: yoke (pitch), block and pod (roll)
# ---------------------------------------------------------------------------------------------
def _shoulder(hw, links):
    pitch_at = (CHEST_SIDE_X[0], 0.0, SZ)
    x0 = CHEST_SIDE_X[0] + 9.0                                           # the pitch output's face
    lug = geo.plate_yz(geo.bones([(0, SZ, 40)], links=[(0,)], holes=[(0, SZ, 8)]), x0, x0 + 10)
    # The arm to the roll drive leaves the chest through the round shoulder opening: inboard of
    # the skin it stays inside the opening's radius about the pitch axis.
    roll_at = (SX, 42.0, SZ)
    ring = geo.plate_xz(geo.bones([(SX, SZ, 45), (SX - 46, SZ, 24)]), 34, 42) - mount_bores("RS06", roll_at, (0, -1, 0), x_dir=(1, 0, 0))
    ring -= geo.half_space((x0, 0, 0), (-1, 0, 0))
    corner = geo.box(8, 10, 30, (x0 + 4, 47, SZ))                         # a gusset inboard of the roll drive's can
    stator, rotor = hw.actuator("RS06", roll_at, (0, -1, 0), x_dir=(1, 0, 0), name="shoulder_roll")
    links["shoulder_yoke"] += [part(lug + ring + corner, "shoulder_yoke", "frame"),
                               *hw.rotor_screws("RS03", pitch_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0)), *stator]

    lug = geo.plate_xz(geo.bones([(SX, SZ, 30)], links=[(0,)], holes=[(SX, SZ, 6)]), 23, 33)
    yaw_at = (SX, 0.0, SZ - 45)
    cup = geo.tube(22, 17, 17, (SX, 0, SZ - 36), (0, 0, 1)) + geo.tube(22, 5, 10, (SX, 0, SZ - 36), (0, 0, 1))
    neck = geo.box(24, 12, 9, (SX, 18, SZ - 25.5))
    block = lug + cup + neck - rotor_counterbores("RS00", yaw_at, (0, 0, 1), 10.0, x_dir=(1, 0, 0))     # the yaw output's screws, sunk
    # The shoulder's pod: a body of revolution about the roll axis, so that it turns with the arm
    # round the yoke's ring and the roll drive behind it without meeting either. A slot round it
    # lets the yoke's arm through over the whole of the roll's travel; the arm leaves it below.
    t = skin.PANEL_T
    def capsule(radius, front, back, fore=36.0, aft=30.0):
        """A capsule about the roll axis: an elliptical cap `fore` deep before and `aft` deep behind a
        cylinder, each one smooth surface (a polygon's turning shows as rings on a pearl panel)."""
        outline = [bd.EllipticalCenterArc((0, fore - front), radius, fore, -90.0, arc_size=90.0),
                   bd.Line((radius, fore - front), (radius, back - aft)),
                   bd.EllipticalCenterArc((0, back - aft), radius, aft, 0.0, arc_size=90.0), bd.Line((0, back), (0, -front))]
        face = bd.Rot(90, 0, 0) * bd.Face(bd.Wire(outline))               # drawn as (r, y), stood up as (r, z)
        return geo.frame(SHOULDER, (0, 1, 0), (1, 0, 0)) * bd.revolve(face, bd.Axis.Z, 360.0)

    outer, inner = capsule(POD_R, POD_FRONT, POD_BACK), capsule(POD_R - t, POD_FRONT - t, POD_BACK - t, 36.0 - t, 30.0 - t)
    pod = outer - inner
    slot = geo.plate_xz(geo.polygon(*[(SX + x, SZ + z) for x, z in _sector(-54.0, 164.0, 80.0)]), 30, 46)
    pod = geo.carve(pod, slot, "shoulder pod's slot")                     # the yoke's arm, through the roll's travel
    pod -= geo.cyl(36, 80, (SX, 0, SZ - 90), (0, 0, 1))                   # round opening for the arm
    pads = None
    for s in (1, -1):
        pad = geo.cyl(5, 60, (SX + s * 18, 0, SZ - 27), (s, 0, 0)) & inner
        pads = pad if pads is None else pads + pad
    yaw_at = (SX, 0.0, SZ - 45)
    yaw_stator, yaw_rotor = hw.actuator("RS00", yaw_at, (0, 0, 1), x_dir=(1, 0, 0), name="shoulder_yaw")
    links["shoulder_block"] += [part(block, "shoulder_block", "frame"), part(skin.solids(pads - block), "pad_shoulder", "frame"),
                                *rotor, *hw.rotor_screws("RS06", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0)),
                                part(skin.solids(pod), "panel_shoulder", "shell"), *yaw_rotor,
                                *hw.rotor_screws("RS00", yaw_at, (0, 0, 1), 10.0, x_dir=(1, 0, 0), sunk=3.0)]
    links["upper_arm"] += yaw_stator


# ---------------------------------------------------------------------------------------------
# Upper arm
# ---------------------------------------------------------------------------------------------
ARM_RIM = (1215.5, -0.76)                       # the elbow rim in the side view: z = 1215.5 - 0.76 y
UPPER_ARM_ROWS = skin.register("upper_arm", [
    geo.S(1140, SX + 3, 2, rx=38, rxn=38, ry=40, ryn=38, n=3.0),
    geo.S(1230, SX + 3, 2, rx=38, rxn=40, ry=42, ryn=40, n=3.0),
    geo.S(1320, SX + 2, 0, rx=41, rxn=43, ry=43, ryn=43, n=3.0),
    geo.S(1352, SX + 2, 0, rx=41, rxn=43, ry=43, ryn=43, n=3.0),
], covers=["l_upper_arm"], link="l_upper_arm", skip=("elbow",), above=[((-100.0, 1291.5), (100.0, 1139.5))])


def _upper_arm(hw, links):
    # The upper arm's skin, from under the shoulder's pod to the elbow, where its rim is slanted:
    # the line the forearm's front comes up to at a full bend.
    form = skin.Form(UPPER_ARM_ROWS)
    rim = skin.from_side([(-200, ARM_RIM[0] - 200 * ARM_RIM[1]), (200, ARM_RIM[0] + 200 * ARM_RIM[1])], [(200, 1000), (-200, 1000)])
    liner, panel = skin.trim(form.liner, [rim], "upper arm liner"), skin.trim(form.panel, [rim], "upper arm panel")
    top = geo.half_space((0, 0, UPPER_ARM_ROWS[-1][0] - RIM), (0, 0, 1))        # the sleeve's upper rim, under the shoulder's pod
    trim, panel = geo.common(panel, top, "upper arm rim"), geo.cut(panel, top, "upper arm panel under its rim")
    pads = None
    for origin, direction in [((SX + 20, 0, z), (1, 0, 0)) for z in (1240, 1300)]:
        pad = geo.mount_pad(form.cavity, origin, direction, 5.0, 80.0)
        pads = pad if pads is None else pads + pad

    yaw_at, elbow_at = (SX, 0.0, SZ - 45), (SX + 17, 0.0, EZ)
    top = geo.tube(33.5, 8, PLATE_T, (SX, 0, SZ - 45), (0, 0, 1)) - mount_bores("RS00", yaw_at, (0, 0, 1), x_dir=(1, 0, 0))
    housing = geo.tube(33.5, 29.3, 52, (SX, 0, SZ - 97), (0, 0, 1)) + geo.tube(33.5, 6, 8, (SX, 0, SZ - 105), (0, 0, 1))   # the yaw drive's sleeve: an RS00 is 51.1 long
    plate = geo.plate_yz(geo.bones([(0, SZ - 124, 26), (6, 1240, 16), (10, 1182, 13), (0, EZ, 45)]), SX + 17, SX + 25)
    plate -= mount_bores("RS06", elbow_at, (1, 0, 0), x_dir=(0, 1, 0))
    ribs = geo.box(26, 6, 126, (SX + 12, 20, 1252))                       # one rib, behind: the forearm folds in front
    stator, rotor = hw.actuator("RS06", elbow_at, (1, 0, 0), x_dir=(0, 1, 0), name="elbow")
    links["upper_arm"] += [part(top + housing + plate + ribs, "humerus", "frame"), *stator,
                           part(skin.solids(pads - (top + housing + plate + ribs)), "pad_upper_arm", "frame"),
                           part(skin.solids(liner), "liner_upper_arm", "under"), part(skin.solids(panel), "panel_upper_arm", "shell"),
                           part(skin.solids(trim), "trim_upper_arm", "accent")]
    links["forearm"] += [*rotor, *hw.rotor_screws("RS06", elbow_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0))]


# ---------------------------------------------------------------------------------------------
# Forearm: the elbow lug and roll drive, then the turning half
# ---------------------------------------------------------------------------------------------
FOREARM_ROWS = skin.register("forearm", [
    geo.S(950, SX, 0, rx=28, ry=30, n=2.6),
    geo.S(980, SX, 0, rx=31, ry=32.5, n=2.8),
    geo.S(RZ - 3, SX, 0, rx=32.6, ry=33.6, n=2.8),
], covers=["l_forearm_distal"], link="l_forearm_distal", skip=("wrist_pitch",), within=((-1e4, -1e4, 970.0), (1e4, 1e4, 2e3)))


def _forearm(hw, links):
    lug = geo.plate_yz(geo.bones([(0, EZ, 30), (0, RZ + 24, 22)], holes=[(0, EZ, 6)]), SX + 26, SX + 36)
    roll_at = (SX, 0.0, RZ + 9)
    mount = geo.tube(28, 8, PLATE_T, (SX, 0, RZ + 1), (0, 0, 1)) - mount_bores("RS05", roll_at, (0, 0, -1), x_dir=(1, 0, 0))
    housing = geo.tube(28, 23.8, 44, (SX, 0, RZ + 9), (0, 0, 1))          # the roll drive's sleeve
    cuff = geo.tube(32.6, 30.0, 52, (SX, 0, RZ + 3), (0, 0, 1)) - geo.cyl(48, 200, ELBOW, (1, 0, 0), centered=True) \
        - geo.box(30, 50, 90, (SX + 34, 0, RZ + 36))
    cuff_pad = geo.tube(30.0, 28.0, 10, (SX, 0, RZ + 12), (0, 0, 1)) - geo.box(30, 50, 90, (SX + 34, 0, RZ + 36))
    stator, rotor = hw.actuator("RS05", roll_at, (0, 0, -1), x_dir=(1, 0, 0), name="wrist_roll")
    links["forearm"] += [part(lug + mount + housing + cuff_pad, "elbow_bracket", "frame"), *stator,
                         part(cuff, "panel_forearm_cuff", "shell")]

    form = skin.Form(FOREARM_ROWS)
    opening = geo.cyl(45, 200, WRIST, (0, 1, 0), centered=True)            # round opening about the wrist
    liner, panel = skin.trim(form.liner, [opening], "forearm liner"), skin.trim(form.panel, [opening], "forearm panel")
    top = geo.half_space((0, 0, FOREARM_ROWS[-1][0] - RIM), (0, 0, 1))          # the forearm's upper rim, under the cuff
    trim, panel = geo.common(panel, top, "forearm rim"), geo.cut(panel, top, "forearm panel under its rim")
    pads = None
    for origin, direction in [((SX, s * 8, 1003), (0, s, 0)) for s in (1, -1)]:
        pad = geo.mount_pad(form.cavity, origin, direction, 5.0, 80.0)
        pads = pad if pads is None else pads + pad
    lug = geo.tube(22, 5, 10, (SX, 0, RZ - 10), (0, 0, 1)) + geo.cyl(7, 8, (SX, 0, RZ - 18), (0, 0, 1))
    pitch_at = (SX, -14.0, WZ)
    stem = geo.cyl(13, RZ - 18 - 966, (SX, 0, 966), (0, 0, 1))        # necked under the lug for its screw heads
    block = geo.cyl(21, 18, (SX, 0, 950), (0, 0, 1))                   # over the pitch drive's can
    fork = geo.plate_xz(geo.bones([(SX, WZ, 24), (SX, 956, 14)]), -22, -14) - mount_bores("RS05", pitch_at, (0, -1, 0), x_dir=(1, 0, 0))
    sleeve = geo.tube(16, 13, 26, (SX, 0, 970), (0, 0, 1))
    wp_stator, wp_rotor = hw.actuator("RS05", pitch_at, (0, -1, 0), x_dir=(1, 0, 0), name="wrist_pitch")
    links["forearm_distal"] += [*rotor, *hw.rotor_screws("RS05", roll_at, (0, 0, -1), 10.0, x_dir=(1, 0, 0)),
                                part(lug + stem + block + fork, "radius", "frame"), part(skin.solids(pads - (lug + stem + block + fork)), "pad_forearm", "frame"),
                                part(sleeve, "forearm_tube", "carbon"),
                                part(skin.solids(liner), "liner_forearm", "under"), part(skin.solids(panel), "panel_forearm", "shell"),
                                part(skin.solids(trim), "trim_forearm", "accent"),
                                *wp_stator]
    links["wrist_link"] += [*wp_rotor, *hw.rotor_screws("RS05", pitch_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0))]


def _wrist(hw, links):
    yaw_at = (SX + 14, 0.0, YZ)
    lug = geo.plate_xz(geo.bones([(SX, WZ, 18), (SX + 14, WZ - 34, 10)], holes=[(SX, WZ, 3)]), -33, -23)
    yaw_plate = geo.plate_yz(geo.bones([(0, YZ, 24), (-24, YZ + 20, 10)]), SX + 14, SX + 22) - mount_bores("RS05", yaw_at, (1, 0, 0), x_dir=(0, 1, 0))
    stator, rotor = hw.actuator("RS05", yaw_at, (1, 0, 0), x_dir=(0, 1, 0), name="wrist_yaw")
    links["wrist_link"] += [part(lug + yaw_plate, "wrist_bracket", "frame"), *stator]
    links["palm"] += [*rotor, *hw.rotor_screws("RS05", yaw_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0))]

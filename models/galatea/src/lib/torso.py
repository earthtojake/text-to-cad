"""The trunk: pelvis, waist gimbal and chest, built on the centre plane at the zero pose.

Pelvis: two plates and a wall. Three actuators stand between the plates, the two hip yaw
drives bolted to the lower plate with their outputs down, the waist yaw drive bolted to
the upper plate with its output up. The upper plate is a closed deck over the hip drives;
the waist drive's end cap shows through the lower one.

Waist: a universal joint. The lumbar yoke turns on the waist yaw drive and holds a spider
between a bearing plate in front and an upright behind (roll, driven from behind); the chest
hangs on the spider's side arms between two lugs (pitch, driven from both sides, the stators
on the chest).

Chest: a frame carrying the shoulder and neck drives, the compute module in front of the
spine and the battery behind it, under a liner and one pearl vest: breastplate, back and
straps. The liner runs on down past the waist as the abdomen, over the waist's three drives.
The battery comes out through a hatch in the back, which carries three vents and the
robot's name; the breastplate carries the status light, a chevron like the vest's hems.
"""

import build123d as bd

from . import geo, skin
from .dims import CHEST_SIDE_X, HIP, NECK_BASE, PELVIS_Z, PLATE_T, SHOULDER, WAIST, WAIST_AXIS_Y
from .hardware import mount_bores, rotor_counterbores
from .kit import mirror_tree, part

HX = HIP[0]
PZ0, PZ1 = PELVIS_Z
WY, WZ = WAIST[1], WAIST[2]
SHZ = SHOULDER[2]
S0, S1 = CHEST_SIDE_X
TRUNK_LINKS = ("pelvis", "lumbar_yoke", "waist_cross", "chest")


def _both_sides(parts):
    """Parts given for the left, with their mirror images on the right."""
    return [*parts, *[mirror_tree(p) for p in parts]]


def build_trunk(hw, hip_yaw_stators):
    """Every part of the trunk, by link. `hip_yaw_stators` are the left leg's parts that
    bolt into the pelvis; `shoulder_yoke` and `neck` collect the outputs the chest drives."""
    links = {name: [] for name in (*TRUNK_LINKS, "shoulder_yoke", "neck")}
    links["pelvis"] += _both_sides(hip_yaw_stators)
    _pelvis(hw, links)
    _waist(hw, links)
    _chest(hw, links)
    return links


# ---------------------------------------------------------------------------------------------
# Pelvis
# ---------------------------------------------------------------------------------------------
PORTS_X = (-60.0, 60.0)        # the charge and data ports, behind the pelvis
PELVIS_ROWS = skin.register("pelvis", [
    geo.S(1003, 0, 10, rx=143, ry=82, n=3.0, ryn=77.5),
    geo.S(1040, 0, 10, rx=146, ry=84, n=3.0, ryn=79.5),
    geo.S(1082, 0, 10, rx=141, ry=81, n=3.0, ryn=76.5),
], covers=["pelvis"], within=((-200, -200, 1009), (200, 200, 1076)))


def _pelvis(hw, links):
    outline = geo.hull([(-HX, 0, 52), (HX, 0, 52), (0, 34, 50), (0, -14, 44)])     # 52 at the hips: an RS06 is 88 over its lobes, inside a 6 mm wall
    rotor_hole, cap_hole = 27.0, 33.0

    # The pelvis's skin: a black band round the casting, arched over each hip and pierced behind
    # for the two ports, with one pearl plate across the front.
    form = skin.Form(PELVIS_ROWS)
    tools = [geo.half_space((0, 0, PZ0 + 0.5), (0, 0, -1)), geo.half_space((0, 0, PZ1 + 1.0), (0, 0, 1)),
             *[geo.cyl(13, 60, (x, 60, 1042), (0, 1, 0)) for x in PORTS_X],                          # a round opening on each port
             *[geo.cyl(110, 400, (s * HX, 0, HIP[2]), (0, 1, 0), centered=True) for s in (1, -1)]]   # arches over the hips
    liner = skin.trim(form.liner, tools, "pelvis liner")
    plate = skin.from_front(geo.hull([(-92, 1066, 8), (92, 1066, 8), (-80, 1029, 8), (80, 1029, 8)]))     # clear of the thighs at full flexion
    panel = geo.common(form.panel, plate, "pelvis plate")
    pads = None
    for origin, direction in ([((s * 124, -20, 1042), (s, 0, 0)) for s in (1, -1)] + [((s * 46, -50, 1042), (0, -1, 0)) for s in (1, -1)]):
        pad = geo.mount_pad(form.cavity, origin, direction)
        pads = pad if pads is None else pads + pad

    lower = outline
    for x, y, r in ((-HX, 0, rotor_hole), (HX, 0, rotor_hole), (0, WAIST_AXIS_Y, cap_hole)):
        lower -= bd.Pos(x, y) * bd.Circle(r)
    upper = outline - bd.Pos(0, WAIST_AXIS_Y) * bd.Circle(rotor_hole)         # a closed deck over the hip drives, 1 mm over their covers
    wall = geo.plate_xy(outline - bd.offset(outline, amount=-6.0), PZ0 + PLATE_T, PZ1 - PLATE_T)
    wall -= geo.plate_xz(geo.slot(-26, 1042, 26, 1042, 13), 40, 120)       # a window on the waist drive, at the back
    waist_at = (0.0, WAIST_AXIS_Y, PZ1 - PLATE_T)
    casting = geo.plate_xy(lower, PZ0, PZ0 + PLATE_T) + geo.plate_xy(upper, PZ1 - PLATE_T, PZ1) + wall
    casting -= mount_bores("RS06", waist_at, (0, 0, 1), x_dir=(-1, 0, 0), turn=22.5)
    for s in (1, -1):
        casting -= mount_bores("RS06", (s * HX, 0.0, PZ0 + PLATE_T), (0, 0, -1), x_dir=(-s, 0, 0))

    # Nothing hangs between the hips: a thigh raised and turned in swings through there.
    stator, rotor = hw.actuator("RS06", waist_at, (0, 0, 1), x_dir=(-1, 0, 0), name="waist_yaw", turn=22.5)   # its ribs between the hip drives'

    # Charge and data ports, either side of the rear window, seated on the wall's curve.
    ports = []
    for x, r in zip(PORTS_X, (9.0, 6.0)):
        block = geo.box(30, 40, 30, (x, 78, 1042)) - geo.plate_xy(outline, PZ0, PZ1) - geo.half_space((0, 80, 0), (0, 1, 0))
        ports.append(part(block - geo.cyl(r, 60, (x, 40, 1042), (0, 1, 0)), "port", "graphite"))
    links["pelvis"] += [part(casting, "pelvis_casting", "frame"), *stator, part(skin.solids(pads - casting), "pad_pelvis", "frame"),
                        part(skin.solids(liner), "liner_pelvis", "under"), part(skin.solids(panel), "panel_pelvis", "shell"),
                        *ports]
    links["lumbar_yoke"] += [*rotor, *hw.rotor_screws("RS06", waist_at, (0, 0, 1), 10.0, x_dir=(-1, 0, 0))]


# ---------------------------------------------------------------------------------------------
# Waist: lumbar yoke (yaw), spider (roll), chest lugs (pitch)
# ---------------------------------------------------------------------------------------------
UPRIGHT = 46.0         # the waist yoke's uprights stand this far before and behind its centre, outside the pitch drives' rings
BELLY_R = 64.0         # the belly shield's outer radius about the waist's centre: inside the abdomen's front wall however the chest leans


def _waist(hw, links):
    z0 = PZ1 + 1.0
    base = geo.plate_xy(geo.bones([(0, WY, 40), (0, WY + 50, 30)], holes=[(0, WY, 8)]), z0, z0 + 10)
    roll_at = (0.0, WY + UPRIGHT + 8, WZ)
    rear = geo.plate_xz(geo.bones([(0, WZ, 47), (0, z0 + 16, 30)]), WY + UPRIGHT, WY + UPRIGHT + 8) \
        - mount_bores("RS06", roll_at, (0, -1, 0), x_dir=(1, 0, 0))
    # In front, the spider's journal runs in a bearing plate on a strut raked back to the base: the
    # abdomen's front wall swings down round the waist's centre when the chest bows, and nothing of
    # the yoke may stand in front of the strut's line where that wall comes.
    front = geo.plate_xz(geo.bones([(0, WZ, 22)], links=[(0,)], holes=[(0, WZ, 12)]), WY - UPRIGHT - 8, WY - UPRIGHT)
    front += geo.plate_yz(geo.polygon(*[(WY + y, WZ + z) for y, z in (                # behind the belly's shield, then down to the base
        (-54, -16), (-50, -27), (-44, -36), (-36, -44), (-30, -50), (-28, -58), (-27, z0 + 2 - WZ), (-15, z0 + 2 - WZ),
        (-24, -38), (-40, -25), (-46, -22), (-46, -16))]), -18, 18)                   # its foot clear of the yaw output's screws
    rear -= geo.half_space((0, 0, z0), (0, 0, -1))
    stator, rotor = hw.actuator("RS06", roll_at, (0, -1, 0), x_dir=(1, 0, 0), name="waist_roll")
    # The belly's shield: a piece of a sphere about the waist's centre, on two posts from the strut.
    # It closes the front under the abdomen's hem, between the chest's lugs, and the abdomen's wall
    # passes outside it at one distance through the whole of the waist's roll and pitch.
    inside = bd.Pos(*WAIST) * bd.Sphere(BELLY_R - skin.PANEL_T)
    shield = (bd.Pos(*WAIST) * bd.Sphere(BELLY_R) - inside) & geo.plate_xz(
        geo.hull([(-22, 1094, 10), (22, 1094, 10), (-22, WZ + 6, 10), (22, WZ + 6, 10)]), -200, WY - 34)
    post = (geo.cyl(6, 40, (-12, WY - 40, WZ - 36), (0, -1, 0)) + geo.cyl(6, 40, (12, WY - 40, WZ - 36), (0, -1, 0))) & inside
    links["lumbar_yoke"] += [part(base + rear + front + post, "lumbar_yoke", "frame"), *stator,
                             hw.pivot_cap(16, (0, WY - UPRIGHT - 8, WZ), (0, -1, 0), label="waist_bearing_cap"),
                             part(skin.solids(shield), "liner_belly", "under")]

    pitch_at = (48.0, WY, WZ)
    spider = bd.Pos(*WAIST) * bd.Sphere(25)
    spider += geo.cyl(17, UPRIGHT + 28, (0, WY - UPRIGHT + 1, WZ), (0, 1, 0)) + geo.cyl(26, 10, (0, WY + UPRIGHT - 11, WZ), (0, 1, 0))
    spider += geo.cyl(12, 9, (0, WY - UPRIGHT + 1, WZ), (0, -1, 0))        # front journal, in the yoke's upright
    for s in (1, -1):
        spider += geo.cyl(12, 30, (0, WY, WZ), (s, 0, 0)) + geo.cyl(21, 10, (s * 29, WY, WZ), (s, 0, 0))
        spider -= rotor_counterbores("RS06", (s * 48.0, WY, WZ), (-s, 0, 0), 10.0, x_dir=(0, -1, 0))
    spider -= rotor_counterbores("RS06", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0))
    spider -= geo.cyl(6, 120, (0, WY - 60, WZ), (0, 1, 0)) + geo.cyl(5, 90, (-45, WY, WZ), (1, 0, 0))
    links["waist_cross"] += [part(spider, "waist_spider", "link"), *rotor,
                             *hw.rotor_screws("RS06", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0), sunk=4.0)]
    stator, rotor = hw.actuator("RS06", pitch_at, (-1, 0, 0), x_dir=(0, -1, 0), name="waist_pitch")
    links["chest"] += _both_sides(stator)
    links["waist_cross"] += _both_sides([*rotor, *hw.rotor_screws("RS06", pitch_at, (-1, 0, 0), 10.0, x_dir=(0, -1, 0), sunk=4.0)])


# ---------------------------------------------------------------------------------------------
# Chest
# ---------------------------------------------------------------------------------------------
# The chest's form: z, centre y, half-width, back depth, exponent, front depth. It holds the frame, the
# compute module before the spine and the battery behind it (whose back stands 130 behind the hips' line),
# and runs on down round the waist as the abdomen: wide enough there for the pitch drives on the chest's
# lugs, and deep enough behind for the roll drive's can, which the chest swings past as it leans.
#
# The abdomen ends in a hem, drawn in the side view as a V with its point under the pitch axis. However
# the chest leans (40 forward, 20 back, 15 to a side, and two of those together) the hem stays 6 mm above
# the pelvis: its point may hang low because a bow does not move it, and its ends ride high because a bow
# swings them down.
HEM = ((-43.0, 1146.0), (WY, 1109.0), (152.0, 1142.0))
SHOULDER_HOLE = 57.0       # the round opening about each shoulder: the pitch drive's ring plate (54) stands in it
# The vest's hems in the front and back views (x, z): each a shallow V, (height at the centre, rise per mm to a side).
FRONT_HEM, BACK_HEM = (1250.0, 46.0 / 260.0), (1222.0, 40.0 / 260.0)
# The status light on the breastplate, a chevron on the front hem's slope: half-width, its point's height, its stroke.
LIGHT = (30.0, 1447.0, 3.2)
# The battery's hatch in the back (x, z): half-width, top, and how far its lower edge runs above the back hem. The
# battery behind it is 150 wide and stands from 1260 to 1430.
HATCH = (82.0, 1442.0, 22.0)
VENTS = ((1402.0, 46.0), (1412.0, 54.0), (1422.0, 58.0))       # the hatch's vents (z, width): the nape's three, again
NAME = ("G A L A T E A", 7.0, 1272.0, 0.35)                    # the wordmark on the hatch: text, capital height, z, how proud
CHEST_ROWS = skin.register("chest", [geo.S(z, 0, cy, rx=rx, ry=ry, n=n, ryn=ryn) for z, cy, rx, ry, n, ryn in (
    (1096, 26, 104, 118, 3.4, 66),
    (1150, 26, 108, 124, 3.4, 68),
    (1196, 26, 108, 120, 3.2, 68),
    (1260, 26, 122, 112, 3.1, 80),
    (1330, 25, 142, 113, 3.2, 92),
    (1392, 24, 152, 112, 3.3, 94),
    (1450, 24, 152, 104, 3.3, 84),
    (1486, 24, 144, 92, 3.2, 72),
    (1504, 24, 126, 78, 3.0, 62),
)], covers=["chest"], skip=("neck_yaw", "shoulder_pitch", "m4_screw", "m3_screw"),
    above=[(HEM[0], HEM[1]), (HEM[1], HEM[2])],
    holes=[((s * 150.0, 0.0, SHOULDER[2]), (1.0, 0.0, 0.0), SHOULDER_HOLE) for s in (1, -1)])


def _chest(hw, links):
    # The chest's skin: a black liner over the whole form, open round each shoulder and ending in
    # the abdomen's hem, and one pearl vest over it: breastplate, back and the straps between them.
    # The flanks under the arms and the whole abdomen are left black; the breastplate and the back
    # each end in a shallow V over the waist.
    form = skin.Form(CHEST_ROWS)
    cavity = form.cavity
    (y0, z0), (y1, z1), (y2, z2) = HEM
    under = geo.polygon((-300, 1000), (-300, z0 + (z1 - z0) / (y1 - y0) * (-300 - y0)), (y1, z1),
                        (300, z2 + (z2 - z1) / (y2 - y1) * (300 - y2)), (300, 1000))
    under = bd.fillet(under.vertices().sort_by(lambda v: abs(v.X - y1) + abs(v.Y - z1))[0], 24.0)    # the V's point, rounded
    tools = [geo.plate_yz(under, -260, 260),                               # everything under the hem
             *[geo.cyl(SHOULDER_HOLE, 100, (s * 150, 0, SHZ), (1, 0, 0), centered=True) for s in (1, -1)]]   # round openings about the shoulders
    flank = geo.polygon((-22, 1080), (-10, 1376), (10, 1438), (62, 1438), (66, 1080))
    hem = lambda at: geo.polygon((-260, 1080), (-260, at[0] + 260 * at[1]), (0, at[0]), (260, at[0] + 260 * at[1]), (260, 1080))
    (half, point, stroke), rise = LIGHT, FRONT_HEM[1]
    window = skin.from_front(geo.polygon((-half, point + half * rise), (0, point), (half, point + half * rise),
                                         (half, point + half * rise + stroke), (0, point + stroke), (-half, point + half * rise + stroke)))
    # The hatch: the back's middle, cut free by one shut line. Its lower edge runs parallel to the hem below it.
    (wide, top, over), (low, rise) = HATCH, BACK_HEM
    door = geo.polygon((-wide, top), (wide, top), (wide, low + over + wide * rise), (0, low + over), (-wide, low + over + wide * rise))
    corner = lambda face, x, z: face.vertices().sort_by(lambda v: abs(v.X - x) + abs(v.Y - z))[0]
    for x, z, radius in ((-wide, top, 12.0), (wide, top, 12.0), (wide, low + over + wide * rise, 10.0),
                         (-wide, low + over + wide * rise, 10.0), (0, low + over, 16.0)):
        door = bd.fillet(corner(door, x, z), radius)
    behind = dict(y0=40.0, y1=skin.WIDE)
    panel = skin.trim(form.panel, [*tools, geo.plate_yz(flank, 80, 260), geo.plate_yz(flank, -260, -80),
                                   skin.from_front(hem(FRONT_HEM), y1=40.0), skin.from_front(hem(BACK_HEM), **behind), window,
                                   skin.from_front(door, **behind)], "chest panel")
    hatch = geo.common(form.panel, skin.from_front(bd.offset(door, amount=-skin.GAP), **behind), "battery hatch")
    for z, across in VENTS:
        hatch = geo.carve(hatch, geo.box(across, 80, 2.2, (0, 140, z)), "hatch vent")
    text, tall, z, proud = NAME
    raised = geo.cut(geo.loft(CHEST_ROWS, shrink=-proud), form(0.0), "wordmark's layer")
    name = geo.common(raised, skin.lettering(text, tall, bd.Plane(origin=(0, 40, z), x_dir=(-1, 0, 0), z_dir=(0, 1, 0)), 200.0), "wordmark")
    liner = skin.trim(form.liner, [*tools, window], "chest liner")
    light = geo.common(form.liner, window, "status light")

    lug = geo.bones([(WY, WZ, 45), (WY - 8, 1206, 24)])                          # raked forward, clear of the roll drive
    frame = geo.plate_yz(lug, 40, 48) + geo.plate_yz(lug, -48, -40)
    for s in (1, -1):
        frame -= mount_bores("RS06", (s * 48.0, WY, WZ), (-s, 0, 0), x_dir=(0, -1, 0))
    # The lugs' cross-tie and the spine start high enough to swing clear of the roll drive
    # behind the waist when the chest leans back.
    frame += geo.plate_xy(geo.hull([(-40, WY - 6, 26), (40, WY - 6, 26), (0, 50, 16)]), 1218, 1230)
    frame += geo.box(92, 18, 230, (0, 57, 1337))                         # spine: y 48..66, z 1222..1452
    frame += geo.plate_xz(geo.hull([(-96, SHZ, 44), (96, SHZ, 44), (0, 1452, 44)]), 56, 66)     # behind the shoulder drives' cans
    ring = geo.bones([(0, SHZ, 54), (38, SHZ, 34)])
    frame += geo.plate_yz(ring, S0, S1) + geo.plate_yz(ring, -S1, -S0)
    for s in (1, -1):
        frame -= mount_bores("RS03", (s * S0, 0.0, SHZ), (s, 0, 0), x_dir=(0, 1, 0))
    neck_at = (0.0, NECK_BASE[1], 1488.0)
    frame += geo.plate_xy(geo.bones([(0, neck_at[1], 40), (0, 50, 32), (0, -20, 14)], links=[(0, 1), (0, 2)],
                                    holes=[(0, neck_at[1], 22)]), 1488, 1496)
    pads = None
    for origin, direction in ([((s * 30, 50, 1410), (s * 0.3, -1, 0)) for s in (1, -1)]
                              + [((s * 40, 57, 1360), (s, -0.75, 0)) for s in (1, -1)]
                              + [((s * 100, 56, 1440), (s * 0.3, 1, 0)) for s in (1, -1)]):
        pad = geo.mount_pad(cavity, origin, direction, 6.0, 180.0)
        pads = pad if pads is None else pads + pad

    battery = geo.box(150, 56, 170, (0, 94, 1345))                       # y 66..122, z 1260..1430, its back corners rounded to the chest's
    battery = bd.fillet(battery.edges().filter_by(bd.Axis.Z).group_by(bd.Axis.Y)[-1], 20.0)
    for z in range(1285, 1420, 20):
        battery -= geo.box(96, 4, 5, (0, 122, z))
    module = geo.box(110, 84, 100, (0, 6, 1300))                         # y -36..48, z 1250..1350, on the spine
    deck = geo.cut(geo.common(geo.box(400, 300, 2.0, (0, 0, 1497.0)), cavity, "neck deck"),
                   geo.cyl(37, 20, (0, NECK_BASE[1], 1490), (0, 0, 1)), "neck deck's hole")          # z 1496..1498
    collar = geo.tube(41.0, 38.5, 1.2, (0, NECK_BASE[1], 1498.0), (0, 0, 1))                         # a hairline round the neck, on the deck

    links["chest"] += [part(frame, "thorax_frame", "frame"), part(skin.solids(pads - frame), "pad_chest", "frame"),
                       part(skin.solids(liner), "liner_chest", "under"), part(skin.solids(panel), "panel_chest", "shell"),
                       part(skin.solids(hatch), "panel_hatch", "shell"), part(skin.solids(name), "wordmark", "accent"),
                       part(battery, "battery", "battery"), part(module, "compute_module", "module"),
                       part(skin.solids(light), "status_light", "light"), part(deck, "liner_neck_deck", "under"),
                       part(collar, "trim_collar", "accent")]
    stator, rotor = hw.actuator("RS03", (S0, 0.0, SHZ), (1, 0, 0), x_dir=(0, 1, 0), name="shoulder_pitch")
    links["chest"] += _both_sides(stator)
    links["shoulder_yoke"] += rotor                                       # the left one; the arm's mirror makes the right
    stator, rotor = hw.actuator("RS00", neck_at, (0, 0, 1), x_dir=(-1, 0, 0), name="neck_yaw")
    links["chest"] += stator
    links["neck"] += rotor

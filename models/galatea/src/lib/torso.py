"""The trunk: pelvis, waist gimbal and chest, built on the centre plane at the zero pose.

Pelvis: two plates and a wall. Three actuators stand between the plates, the two hip yaw
drives bolted to the lower plate with their outputs down, the waist yaw drive bolted to
the upper plate with its output up; each one's end cap shows through the opposite plate.

Waist: a universal joint. The lumbar yoke turns on the waist yaw drive and holds a spider
between two uprights (roll, driven from behind); the chest hangs on the spider's side
arms between two lugs (pitch, driven from both sides, the stators on the chest).

Chest: a frame carrying the shoulder and neck drives, the compute module in front of the
spine and the battery behind it, under a breastplate, a backplate and a ribbed midriff.
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
SKIN_T = 2.6
TRUNK_LINKS = ("pelvis", "lumbar_yoke", "waist_cross", "chest")


def _both_sides(parts):
    """Parts given for the left, with their mirror images on the right."""
    return [*parts, *[mirror_tree(p) for p in parts]]


def _mounts(hw, cavity, outer, seats, size="M4", radius=6.0, reach=120.0):
    pads, screws = None, []
    for origin, direction in seats:
        pad = geo.mount_pad(cavity, origin, direction, radius, reach)
        pads = pad if pads is None else pads + pad
        screws.append(hw.screw(size, *geo.seat(outer, origin, direction), label="skin_screw"))
    return pads, screws


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
PELVIS_ROWS = skin.register("pelvis", [
    geo.S(1003, 0, 10, rx=142, ry=82, n=3.0, ryn=76),
    geo.S(1040, 0, 10, rx=145, ry=84, n=3.0, ryn=78),
    geo.S(1082, 0, 10, rx=140, ry=81, n=3.0, ryn=75),
], covers=["pelvis"], skip=("port",), within=((-200, -200, 1009), (200, 60, 1076)))


def _pelvis(hw, links):
    outline = geo.hull([(-HX, 0, 50), (HX, 0, 50), (0, 34, 50), (0, -14, 44)])
    rotor_hole, cap_hole = 27.0, 33.0

    # The pelvis's skin: a black band round the casting, open at the back over the ports and
    # arched over each hip, with one pearl plate across the front.
    form = skin.Form(PELVIS_ROWS)
    back_edge = geo.behind_curve([(-150, 30), (-80, 62), (0, 70), (80, 62), (150, 30)], [(150, 200), (-150, 200)])
    tools = [geo.half_space((0, 0, PZ0 + 0.5), (0, 0, -1)), geo.half_space((0, 0, PZ1 + 1.0), (0, 0, 1)),
             geo.plate_xy(back_edge, 980, 1110),                         # open at the back: the sacral panel
             *[geo.cyl(110, 400, (s * HX, 0, HIP[2]), (0, 1, 0), centered=True) for s in (1, -1)]]   # arches over the hips
    liner = skin.trim(form.liner, tools, "pelvis liner")
    plate = skin.from_front(geo.hull([(-92, 1066, 8), (92, 1066, 8), (-78, 1022, 8), (78, 1022, 8)]))
    panel = geo.common(form.panel, plate, "pelvis plate")
    pads = None
    for origin, direction in ([((s * 124, -20, 1042), (s, 0, 0)) for s in (1, -1)] + [((s * 46, -50, 1042), (0, -1, 0)) for s in (1, -1)]):
        pad = geo.mount_pad(form.cavity, origin, direction)
        pads = pad if pads is None else pads + pad

    lower = outline
    for x, y, r in ((-HX, 0, rotor_hole), (HX, 0, rotor_hole), (0, WAIST_AXIS_Y, cap_hole)):
        lower -= bd.Pos(x, y) * bd.Circle(r)
    upper = outline
    for x, y, r in ((-HX, 0, cap_hole), (HX, 0, cap_hole), (0, WAIST_AXIS_Y, rotor_hole)):
        upper -= bd.Pos(x, y) * bd.Circle(r)
    wall = geo.plate_xy(outline - bd.offset(outline, amount=-6.0), PZ0 + PLATE_T, PZ1 - PLATE_T)
    wall -= geo.plate_xz(geo.slot(-26, 1042, 26, 1042, 13), 40, 120)       # a window on the waist drive, at the back
    strut = geo.box(16, 10, 70, (0, -43, PZ0 - 31))                      # carries the apron between the hips
    waist_at = (0.0, WAIST_AXIS_Y, PZ1 - PLATE_T)
    casting = geo.plate_xy(lower, PZ0, PZ0 + PLATE_T) + geo.plate_xy(upper, PZ1 - PLATE_T, PZ1) + wall + strut
    casting -= mount_bores("RS06", waist_at, (0, 0, 1), x_dir=(-1, 0, 0), turn=22.5)
    for s in (1, -1):
        casting -= mount_bores("RS06", (s * HX, 0.0, PZ0 + PLATE_T), (0, 0, -1), x_dir=(-s, 0, 0))

    # Apron: a shield hanging between the hips.
    apron_rows = [
        geo.S(915, 0, -38, rx=19, ry=10, n=4.5, ryn=14),
        geo.S(968, 0, -38, rx=27, ry=10, n=4.5, ryn=17),
        geo.S(1012, 0, -38, rx=34, ry=10, n=4.5, ryn=20),
    ]
    apron, apron_cavity, apron_outer = geo.shell(apron_rows, SKIN_T)
    apron -= geo.half_space((0, -42, 0), (0, 1, 0))
    apron -= geo.half_space((0, 0, PZ0 - 0.5), (0, 0, 1))
    apron -= geo.half_space((0, -55, 930), (0, 0.4, -1))                 # a raked lower edge
    apron -= geo.plate_xz(geo.band([(-40, 975), (0, 968), (40, 975)], 2.0), -200, -44)
    apron_pads, apron_screws = _mounts(hw, apron_cavity, apron_outer, [((0, -43, z), (0, -1, 0)) for z in (952, 994)])
    casting += apron_pads

    stator, rotor = hw.actuator("RS06", waist_at, (0, 0, 1), x_dir=(-1, 0, 0), name="waist_yaw", turn=22.5)   # its ribs between the hip drives'

    # Charge and data ports, either side of the rear window, seated on the wall's curve.
    ports = []
    for x, r in ((-60, 9.0), (60, 6.0)):
        block = geo.box(30, 40, 30, (x, 78, 1042)) - geo.plate_xy(outline, PZ0, PZ1) - geo.half_space((0, 80, 0), (0, 1, 0))
        ports.append(part(block - geo.cyl(r, 60, (x, 40, 1042), (0, 1, 0)), "port", "graphite"))
    links["pelvis"] += [part(casting, "pelvis_casting", "gunmetal"), *stator, part(skin.solids(pads - casting), "pad_pelvis", "gunmetal"),
                        part(skin.solids(liner), "liner_pelvis", "under"), part(skin.solids(panel), "panel_pelvis", "shell"),
                        part(apron, "panel_apron", "shell"), *ports]
    links["lumbar_yoke"] += [*rotor, *hw.rotor_screws("RS06", waist_at, (0, 0, 1), 10.0, x_dir=(-1, 0, 0))]


# ---------------------------------------------------------------------------------------------
# Waist: lumbar yoke (yaw), spider (roll), chest lugs (pitch)
# ---------------------------------------------------------------------------------------------
UPRIGHT = 46.0         # the waist yoke's uprights stand this far before and behind its centre, outside the pitch drives' rings
BELLY_R = 103.6        # the belly shield's outer radius about the waist's centre: outside all the chest swings there


def _waist(hw, links):
    z0 = PZ1 + 1.0
    base = geo.plate_xy(geo.bones([(0, WY, 40), (0, WY + 50, 30), (0, WY - 50, 30)], links=[(0, 1), (0, 2)],
                                  holes=[(0, WY, 8)]), z0, z0 + 10)
    roll_at = (0.0, WY + UPRIGHT + 8, WZ)
    rear = geo.plate_xz(geo.bones([(0, WZ, 47), (0, z0 + 16, 30)]), WY + UPRIGHT, WY + UPRIGHT + 8) \
        - mount_bores("RS06", roll_at, (0, -1, 0), x_dir=(1, 0, 0))
    front = geo.plate_xz(geo.bones([(0, WZ, 22), (0, z0 + 16, 24)], holes=[(0, WZ, 12)]), WY - UPRIGHT - 8, WY - UPRIGHT)
    rear -= geo.half_space((0, 0, z0), (0, 0, -1))
    front -= geo.half_space((0, 0, z0), (0, 0, -1))
    stator, rotor = hw.actuator("RS06", roll_at, (0, -1, 0), x_dir=(1, 0, 0), name="waist_roll")
    # The belly's shield: a piece of a sphere about the waist's centre, carried on a post before the
    # yoke's front upright. The chest turns about that centre, so its lower edge passes inside the
    # shield at one distance through the whole of the waist's roll and pitch.
    inside = bd.Pos(*WAIST) * bd.Sphere(BELLY_R - skin.PANEL_T)
    shield = (bd.Pos(*WAIST) * bd.Sphere(BELLY_R) - inside) & geo.plate_xz(
        geo.hull([(-50, 1100, 10), (50, 1100, 10), (-58, WZ, 10), (58, WZ, 10), (-44, 1196, 10), (44, 1196, 10)]), -200, WY - 66)
    post = geo.cyl(8, 80, (0, WY - UPRIGHT - 7, WZ - 30), (0, -1, 0)) & inside
    links["lumbar_yoke"] += [part(base + rear + front + post, "lumbar_yoke", "gunmetal"), *stator,
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
    links["waist_cross"] += [part(spider, "waist_spider", "slate"), *rotor,
                             *hw.rotor_screws("RS06", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0), sunk=4.0)]
    stator, rotor = hw.actuator("RS06", pitch_at, (-1, 0, 0), x_dir=(0, -1, 0), name="waist_pitch")
    links["chest"] += _both_sides(stator)
    links["waist_cross"] += _both_sides([*rotor, *hw.rotor_screws("RS06", pitch_at, (-1, 0, 0), 10.0, x_dir=(0, -1, 0), sunk=4.0)])


# ---------------------------------------------------------------------------------------------
# Chest
# ---------------------------------------------------------------------------------------------
# The chest's form: z, centre y, half-width, back depth, exponent, front depth. It holds the frame, the
# compute module before the spine and the battery behind it (whose back stands 130 behind the hips' line).
CHEST_BOTTOM = 1202.0
SHOULDER_HOLE = 57.0       # the round opening about each shoulder: the pitch drive's ring plate (54) stands in it
CHEST_ROWS = skin.register("chest", [geo.S(z, 0, cy, rx=rx, ry=ry, n=n, ryn=ryn) for z, cy, rx, ry, n, ryn in (
    (1196, 26, 104, 111, 3.0, 64),
    (1260, 26, 122, 112, 3.1, 80),
    (1330, 25, 142, 113, 3.2, 92),
    (1392, 24, 152, 112, 3.3, 94),
    (1450, 24, 152, 104, 3.3, 84),
    (1486, 24, 144, 92, 3.2, 72),
    (1504, 24, 126, 78, 3.0, 62),
)], covers=["chest"], skip=("neck_yaw", "shoulder_pitch", "waist_pitch", "m4_screw", "m3_screw"),
    above=[((-200.0, CHEST_BOTTOM), (200.0, CHEST_BOTTOM))],
    holes=[((s * 150.0, 0.0, SHOULDER[2]), (1.0, 0.0, 0.0), SHOULDER_HOLE) for s in (1, -1)])


def _chest(hw, links):
    # The chest's skin: a black liner over the whole form, open round each shoulder, and one pearl
    # vest over it: breastplate, back and the straps between them. The flanks under the arms are
    # left black, and the breastplate ends in a shallow V over the waist.
    form = skin.Form(CHEST_ROWS)
    cavity = form.cavity
    tools = [geo.half_space((0, 0, CHEST_BOTTOM), (0, 0, -1)),
             *[geo.cyl(SHOULDER_HOLE, 100, (s * 150, 0, SHZ), (1, 0, 0), centered=True) for s in (1, -1)]]   # round openings about the shoulders
    flank = geo.polygon((-22, 1150), (-10, 1376), (10, 1438), (62, 1438), (66, 1150))
    front_edge = geo.polygon((-260, 1100), (-260, 1296), (0, 1250), (260, 1296), (260, 1100))
    window = skin.from_front(geo.slot(-26, 1452, 26, 1452, 1.6))
    panel = skin.trim(form.panel, [*tools, geo.plate_yz(flank, 80, 260), geo.plate_yz(flank, -260, -80),
                                   skin.from_front(front_edge, y1=40.0), window], "chest panel")
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

    links["chest"] += [part(frame, "thorax_frame", "gunmetal"), part(skin.solids(pads - frame), "pad_chest", "gunmetal"),
                       part(skin.solids(liner), "liner_chest", "under"), part(skin.solids(panel), "panel_chest", "shell"),
                       part(battery, "battery", "battery"), part(module, "compute_module", "module"),
                       part(skin.solids(light), "status_light", "light"), part(deck, "liner_neck_deck", "under")]
    stator, rotor = hw.actuator("RS03", (S0, 0.0, SHZ), (1, 0, 0), x_dir=(0, 1, 0), name="shoulder_pitch")
    links["chest"] += _both_sides(stator)
    links["shoulder_yoke"] += rotor                                       # the left one; the arm's mirror makes the right
    stator, rotor = hw.actuator("RS00", neck_at, (0, 0, 1), x_dir=(-1, 0, 0), name="neck_yaw")
    links["chest"] += stator
    links["neck"] += rotor

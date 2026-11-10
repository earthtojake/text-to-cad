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

from . import geo
from .dims import CHEST_SIDE_X, HIP, NECK_BASE, PELVIS_Z, PLATE_T, SHOULDER, WAIST, WAIST_AXIS_Y
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
def _pelvis(hw, links):
    outline = geo.hull([(-HX, 0, 50), (HX, 0, 50), (0, 34, 50), (0, -14, 44)])
    rotor_hole, cap_hole = 27.0, 33.0

    rows = [
        geo.S(1003, 0, 10, rx=140, ry=80, n=3.0, ryn=74),
        geo.S(1040, 0, 10, rx=143, ry=82, n=3.0, ryn=76),
        geo.S(1082, 0, 10, rx=138, ry=79, n=3.0, ryn=73),
    ]
    belt, cavity, belt_outer = geo.shell(rows, SKIN_T)
    belt -= geo.half_space((0, 0, PZ0 + 0.5), (0, 0, -1))
    belt -= geo.half_space((0, 0, PZ1 + 1.0), (0, 0, 1))
    back_edge = geo.behind_curve([(-150, 30), (-80, 62), (0, 70), (80, 62), (150, 30)], [(150, 200), (-150, 200)])
    belt -= geo.plate_xy(back_edge, 990, 1100)                           # open at the back: the sacral panel
    for s in (1, -1):                                                    # arches over the hips, about each roll axis
        belt -= geo.cyl(110, 400, (s * HX, 0, HIP[2]), (0, 1, 0), centered=True)
    pads, screws = _mounts(hw, cavity, belt_outer, [((s * 124, -20, 1042), (s, 0, 0)) for s in (1, -1)]
                           + [((s * 46, -50, 1042), (0, -1, 0)) for s in (1, -1)])

    lower = outline
    for x, y, r in ((-HX, 0, rotor_hole), (HX, 0, rotor_hole), (0, WAIST_AXIS_Y, cap_hole)):
        lower -= bd.Pos(x, y) * bd.Circle(r)
    upper = outline
    for x, y, r in ((-HX, 0, cap_hole), (HX, 0, cap_hole), (0, WAIST_AXIS_Y, rotor_hole)):
        upper -= bd.Pos(x, y) * bd.Circle(r)
    wall = geo.plate_xy(outline - bd.offset(outline, amount=-6.0), PZ0 + PLATE_T, PZ1 - PLATE_T)
    wall -= geo.plate_xz(geo.slot(-26, 1042, 26, 1042, 13), 40, 120)       # a window on the waist drive, at the back
    strut = geo.box(16, 10, 70, (0, -43, PZ0 - 31))                      # carries the apron between the hips
    casting = geo.plate_xy(lower, PZ0, PZ0 + PLATE_T) + geo.plate_xy(upper, PZ1 - PLATE_T, PZ1) + wall + strut + pads

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

    waist_at = (0.0, WAIST_AXIS_Y, PZ1 - PLATE_T)
    stator, rotor = hw.actuator("A86", waist_at, (0, 0, 1), x_dir=(-1, 0, 0), name="waist_yaw")
    # Charge and data ports, either side of the rear window, seated on the wall's curve.
    ports = []
    for x, r in ((-60, 9.0), (60, 6.0)):
        block = geo.box(30, 40, 30, (x, 78, 1042)) - geo.plate_xy(outline, PZ0, PZ1) - geo.half_space((0, 80, 0), (0, 1, 0))
        ports.append(part(block - geo.cyl(r, 60, (x, 40, 1042), (0, 1, 0)), "port", "graphite"))
    links["pelvis"] += [part(casting, "pelvis_casting", "gunmetal"), *stator, part(belt, "pelvis_belt", "ivory"), *screws,
                        part(apron, "apron", "ivory"), *apron_screws, *ports]
    links["lumbar_yoke"] += [*rotor, *hw.rotor_screws("A86", waist_at, (0, 0, 1), 10.0, x_dir=(-1, 0, 0))]


# ---------------------------------------------------------------------------------------------
# Waist: lumbar yoke (yaw), spider (roll), chest lugs (pitch)
# ---------------------------------------------------------------------------------------------
def _waist(hw, links):
    z0 = PZ1 + 1.0
    base = geo.plate_xy(geo.bones([(0, WY, 40), (0, WY + 44, 30), (0, WY - 44, 30)], links=[(0, 1), (0, 2)],
                                  holes=[(0, WY, 8)]), z0, z0 + 10)
    rear = geo.plate_xz(geo.bones([(0, WZ, 47), (0, z0 + 16, 30)], holes=[(0, WZ, 27)]), WY + 40, WY + 48)
    front = geo.plate_xz(geo.bones([(0, WZ, 22), (0, z0 + 16, 24)], holes=[(0, WZ, 12)]), WY - 48, WY - 40)
    rear -= geo.half_space((0, 0, z0), (0, 0, -1))
    front -= geo.half_space((0, 0, z0), (0, 0, -1))
    roll_at = (0.0, WY + 48, WZ)
    stator, rotor = hw.actuator("A86", roll_at, (0, -1, 0), x_dir=(1, 0, 0), name="waist_roll")
    links["lumbar_yoke"] += [part(base + rear + front, "lumbar_yoke", "gunmetal"), *stator,
                             hw.pivot_cap(16, (0, WY - 48, WZ), (0, -1, 0), label="waist_bearing_cap")]

    spider = bd.Pos(*WAIST) * bd.Sphere(25)
    spider += geo.cyl(17, 68, (0, WY - 39, WZ), (0, 1, 0)) + geo.cyl(26, 10, (0, WY + 29, WZ), (0, 1, 0))
    spider += geo.cyl(12, 9, (0, WY - 39, WZ), (0, -1, 0))                 # front journal, in the yoke's upright
    for s in (1, -1):
        spider += geo.cyl(12, 30, (0, WY, WZ), (s, 0, 0)) + geo.cyl(21, 10, (s * 29, WY, WZ), (s, 0, 0))
    spider -= geo.cyl(6, 100, (0, WY - 50, WZ), (0, 1, 0)) + geo.cyl(5, 90, (-45, WY, WZ), (1, 0, 0))
    links["waist_cross"] += [part(spider, "waist_spider", "slate"), *rotor,
                             *hw.rotor_screws("A86", roll_at, (0, -1, 0), 10.0, x_dir=(1, 0, 0))]
    pitch_at = (48.0, WY, WZ)
    stator, rotor = hw.actuator("A70", pitch_at, (-1, 0, 0), x_dir=(0, -1, 0), cover=True, name="waist_pitch")
    links["chest"] += _both_sides(stator)
    links["waist_cross"] += _both_sides([*rotor, *hw.rotor_screws("A70", pitch_at, (-1, 0, 0), 10.0, x_dir=(0, -1, 0))])


# ---------------------------------------------------------------------------------------------
# Chest
# ---------------------------------------------------------------------------------------------
CHEST_ROWS = (
    # z, centre y, half-width, back depth, exponent, front depth
    (1165, 26, 84, 56, 3.0, 56),
    (1198, 26, 94, 62, 3.0, 58),
    (1250, 26, 116, 76, 3.1, 76),
    (1320, 25, 140, 88, 3.2, 92),
    (1390, 24, 150, 92, 3.3, 92),
    (1450, 24, 150, 88, 3.3, 82),
    (1484, 24, 144, 82, 3.2, 72),
    (1500, 24, 128, 72, 3.0, 60),
)


def _chest_rows(z_lo=0.0, z_hi=1e9):
    return [geo.S(z, 0, cy, rx=rx, ry=ry, n=n, ryn=ryn) for z, cy, rx, ry, n, ryn in CHEST_ROWS if z_lo <= z <= z_hi]


def _chest(hw, links):
    skin, cavity, chest_outer = geo.shell(_chest_rows(), SKIN_T)
    for s in (1, -1):                                                    # round openings about the shoulders
        skin -= geo.cyl(52, 80, (s * 150, 0, SHZ), (1, 0, 0), centered=True)
    front_edge = geo.behind_curve([(-170, 1352), (-100, 1318), (-45, 1281), (0, 1264), (45, 1281), (100, 1318), (170, 1352)],
                                  [(170, 1100), (-170, 1100)])
    back_edge = geo.behind_curve([(-170, 1352), (-100, 1330), (0, 1300), (100, 1330), (170, 1352)], [(170, 1100), (-170, 1100)])
    breast = skin - geo.half_space((0, 34, 0), (0, 1, 0)) - geo.plate_xz(front_edge, -200, 60)
    breast -= geo.plate_xz(geo.slot(-30, 1448, 30, 1448, 2.6), -200, 0)   # the status light's window
    sternum = geo.polygon((-11, 1438), (-5, 1240), (5, 1240), (11, 1438))
    breast -= geo.plate_xz(sternum, -200, 0)                             # parted down the sternum
    inlay = geo.plate_xz(geo.polygon((-15, 1441), (-9, 1258), (9, 1258), (15, 1441)), -200, 0)
    inlay = (inlay & cavity) - geo.loft(_chest_rows(), shrink=SKIN_T + 3.0, extend=10.0)
    back = skin - geo.half_space((0, 38, 0), (0, -1, 0)) - geo.plate_xz(back_edge, 0, 200)
    back -= geo.plate_xz(geo.hull([(-74, 1226, 12), (74, 1226, 12), (-74, 1384, 12), (74, 1384, 12)]), 60, 200)   # battery bay

    # Midriff: a ribbed liner under the plates, down to the waist.
    liner_rows = _chest_rows(z_hi=1400)
    liner_cavity = geo.loft(liner_rows, shrink=10.0, extend=10.0)
    liner = geo.loft(liner_rows, shrink=6.0) - liner_cavity - geo.half_space((0, 0, 1350), (0, 0, 1))
    louvres = None                                                       # vent slits across the front and flanks
    for z in range(1216, 1330, 14):
        slit = geo.box(400, 250, 2.6, (0, -95, z))
        louvres = slit if louvres is None else louvres + slit
    liner -= louvres
    liner -= geo.plate_xz(geo.hull([(-74, 1226, 14), (74, 1226, 14), (-74, 1384, 14), (74, 1384, 14)]), 60, 200)   # battery bay
    liner -= geo.cyl(41, 400, WAIST, (1, 0, 0), centered=True)           # round openings about the waist's pitch drives
    liner -= geo.cyl(58, 400, WAIST, (0, 1, 0), centered=True)           # and about its roll axis, front and back

    lug = geo.bones([(WY, WZ, 39), (WY - 8, 1206, 24)], holes=[(WY, WZ, 22)])     # raked forward, clear of the roll drive
    frame = geo.plate_yz(lug, 40, 48) + geo.plate_yz(lug, -48, -40)
    # The lugs' cross-tie and the spine start high enough to swing clear of the roll drive
    # behind the waist when the chest leans back.
    frame += geo.plate_xy(geo.hull([(-40, WY - 6, 26), (40, WY - 6, 26), (0, 50, 16)]), 1218, 1230)
    frame += geo.box(92, 18, 230, (0, 57, 1337))                         # spine: y 48..66, z 1222..1452
    frame += geo.plate_xz(geo.hull([(-96, SHZ, 44), (96, SHZ, 44), (0, 1452, 44)]), 50, 62)
    ring = geo.bones([(0, SHZ, 45), (34, SHZ, 36)], holes=[(0, SHZ, 27)])
    frame += geo.plate_yz(ring, S0, S1) + geo.plate_yz(ring, -S1, -S0)
    neck_at = (0.0, NECK_BASE[1], 1488.0)
    frame += geo.plate_xy(geo.bones([(0, neck_at[1], 40), (0, 50, 32), (0, -20, 14)], links=[(0, 1), (0, 2)],
                                    holes=[(0, neck_at[1], 22)]), 1488, 1496)
    frame += geo.box(16, 8, 52, (0, -34, 1466)) + geo.box(16, 21.5, 14, (0, -40.75, 1447))   # the status light's bracket
    seats = ([((s * 30, 50, 1410), (s * 0.3, -1, 0)) for s in (1, -1)]
             + [((s * 40, 57, 1360), (s, -0.75, 0)) for s in (1, -1)])
    pads, screws = _mounts(hw, cavity, chest_outer, seats, reach=180.0)
    back_seats = ([((s * 100, 56, 1440), (s * 0.3, 1, 0)) for s in (1, -1)]
                  + [((s * 40, 56, 1360), (s, 0, 0)) for s in (1, -1)])
    back_pads, back_screws = _mounts(hw, cavity, chest_outer, back_seats, reach=180.0)
    liner_pads = None
    for s in (1, -1):
        pad = geo.mount_pad(liner_cavity, (s * 40, WY, 1222), (s, 0, 0), 6.0)
        liner_pads = pad if liner_pads is None else liner_pads + pad
    frame += pads + back_pads + liner_pads

    battery = geo.box(160, 64, 176, (0, 98, 1305))                       # y 66..130, z 1217..1393
    battery = bd.fillet(battery.edges().filter_by(bd.Axis.Y), 10.0)
    for z in range(1240, 1380, 20):
        battery -= geo.box(120, 6, 6, (0, 130, z))
    module = geo.box(110, 84, 100, (0, 6, 1300))                         # y -36..48, z 1250..1350, on the spine
    bar = geo.plate_xz(geo.slot(-30, 1448, 30, 1448, 2.2), -54.5, -51.5)
    collar_rows = [geo.S(1498, 0, 16, rx=78, ry=50, n=2.6, ryn=44), geo.S(1524, 0, NECK_BASE[1], rx=50, ry=46, n=2.2, ryn=44)]
    collar = geo.shell(collar_rows, SKIN_T)[0] - geo.half_space((0, 0, 1498), (0, 0, -1)) \
        - geo.half_space((0, 0, 1524), (0, 0, 1))
    deck = (geo.box(400, 300, 2.0, (0, 0, 1497.0)) & cavity) - geo.cyl(37, 20, (0, NECK_BASE[1], 1490), (0, 0, 1))   # z 1496..1498

    links["chest"] += [part(frame, "thorax_frame", "gunmetal"), part(breast, "breastplate", "ivory"), *screws,
                       part(back, "backplate", "ivory"), *back_screws, part(liner, "midriff", "graphite"),
                       part(battery, "battery", "battery"), part(module, "compute_module", "module"),
                       part(bar, "status_light", "glow"), part(inlay, "sternum_inlay", "graphite"),
                       part(deck, "neck_deck", "graphite"), part(collar, "collar", "ivory")]
    stator, rotor = hw.actuator("A86", (S0, 0.0, SHZ), (1, 0, 0), x_dir=(0, 1, 0), name="shoulder_pitch")
    links["chest"] += _both_sides(stator)
    links["shoulder_yoke"] += rotor                                       # the left one; the arm's mirror makes the right
    stator, rotor = hw.actuator("A70", neck_at, (0, 0, 1), x_dir=(-1, 0, 0), name="neck_yaw")
    links["chest"] += stator
    links["neck"] += rotor

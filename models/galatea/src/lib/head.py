"""Neck and head, on the centre plane at the zero pose.

Neck: the yaw drive sits in the chest's collar. On its output stands the neck's root, an
in-line hinge that leans the neck sideways (roll); the stem above it carries a second
in-line hinge at the base of the skull that nods the head (pitch).

Head: a helmet more than a face. The ivory skull swells into a brow over two eye sockets
cut deep into its front, each sweeping up toward the temple, and a ridge runs from the
nape over the crown and down between them as a nasal, as on a Corinthian helmet. Behind
the sockets is one bay, lined in black and closed by a smoked visor; in it sit two camera
eyes, toed out to lie with the face: a bronze barrel, a dark lens set back in it, a ring
of amber light in eight segments, a bronze ring round the pupil. The brow stands over the
upper inner part of each eye and is the only lid they have. A small depth sensor is set
in the ridge on the forehead; a row of slots lit from behind shows the voice; the ridge
carries the antenna turret on the crown; each ear is a finned pod (microphones round a
status light) with a blade swept up and back from it.
"""

import math

import build123d as bd

from . import geo
from .dims import HEAD_TOP_Z, NECK, NECK_BASE, NECK_ROLL, PLATE_T
from .kit import frame, mirror_tree, part

NY, NZ = NECK[1], NECK[2]
RZ = NECK_ROLL[2]
SKIN_T = 2.6
HEAD_LINKS = ("neck", "neck_stem", "head")

SKULL_ROWS = (
    # z, centre y, half-width, back depth, exponent, front depth
    (1560, 16, 52, 60, 2.6, 46),          # the jaw's lower edge
    (1592, 13, 66, 78, 2.6, 70),
    (1628, 9, 75, 90, 2.7, 81),           # cheeks
    (1662, 8, 78, 94, 3.0, 85),           # eye level: squarer, so the face is broad and nearly flat across the eyes
    (1700, 8, 77, 94, 2.7, 91),           # the brow, 6 mm proud of the face under it
    (1730, 10, 63, 79, 2.3, 71),
    (1746, 12, 40, 52, 2.2, 44),
)
CROWN = (0.0, 13.0, HEAD_TOP_Z)
EYE = (31.0, -66.5, 1667.0)                # the centre of the left eye's rim
TOE = 8.0                                  # degrees each eye looks outward of straight ahead
BAY = 14.0                                 # the bay's depth behind the skull's inner surface


def build_head(hw, neck_yaw_output):
    """Every part of the neck and head, by link."""
    links = {name: [] for name in HEAD_LINKS}
    links["neck"] += neck_yaw_output
    _neck(hw, links)
    _head(hw, links)
    return links


def _neck(hw, links):
    yaw_at = (0.0, NY, NECK_BASE[2] - 9.0)
    lug = geo.tube(28, 6, 10, (0, NY, NECK_BASE[2]), (0, 0, 1))
    rear = geo.plate_xz(geo.bones([(0, RZ, 22), (0, RZ - 22, 20)], holes=[(0, RZ, 12.5)]), 32, 40)
    rear -= geo.half_space((0, 0, NECK_BASE[2]), (0, 0, -1))
    roll_at = (0.0, 32.0, RZ)
    stator, rotor = hw.actuator("A40", roll_at, (0, 1, 0), x_dir=(1, 0, 0), name="neck_roll")
    links["neck"] += [part(lug + rear, "neck_root", "gunmetal"),
                      *hw.rotor_screws("A70", yaw_at, (0, 0, 1), 10.0, x_dir=(-1, 0, 0)), *stator]

    lug = geo.plate_xz(geo.bones([(0, RZ, 18), (22, RZ + 17, 12)], holes=[(0, RZ, 3)]), 41, 51)
    side = geo.plate_yz(geo.bones([(NY, NZ, 30), (46, RZ + 26, 12)], holes=[(NY, NZ, 16)]), 18, 26)
    pitch_at = (18.0, NY, NZ)
    p_stator, p_rotor = hw.actuator("A52", pitch_at, (1, 0, 0), x_dir=(0, 1, 0), name="neck_pitch")
    links["neck_stem"] += [part(lug + side, "neck_stem", "gunmetal"), *rotor,
                           *hw.rotor_screws("A40", roll_at, (0, 1, 0), 10.0, x_dir=(1, 0, 0)), *p_stator]
    links["head"] += [*p_rotor, *hw.rotor_screws("A52", pitch_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0))]


def _skull_rows():
    return [geo.S(z, 0, cy, rx=rx, ry=ry, n=n, ryn=ryn) for z, cy, rx, ry, n, ryn in SKULL_ROWS]


class _Forms:
    """The skull's form at several insets, each lofted once: `forms(2.6)` is the form with
    every section drawn in by 2.6 (out, when negative)."""

    def __init__(self):
        self.made = {}

    def __call__(self, shrink):
        if shrink not in self.made:
            self.made[shrink] = geo.loft(_skull_rows(), shrink=shrink, top=(CROWN[0], CROWN[1], CROWN[2] - shrink))
        return self.made[shrink]


def _front(face, back=-22.0):
    """A (x, z) outline carried through the front of the head."""
    return geo.plate_xz(face, -130, back)


def _eye_axis(side):
    toe = math.radians(TOE)
    return (side * math.sin(toe), -math.cos(toe), 0.0)


def _eye(side):
    """One camera eye: [parts]. Its barrel passes through the bay's floor into a bore of the
    sensor core, 22 deep from its rim; everything in it is turned about the eye's axis."""
    ahead = _eye_axis(side)
    rim = (side * EYE[0], EYE[1], EYE[2])
    back = tuple(rim[k] - 22.0 * ahead[k] for k in range(3))
    barrel = geo.revolve([(14.5, 0), (18.5, 0), (18.5, 20.8), (17.3, 22), (15.5, 22), (14.5, 21)], back, ahead)
    lens = geo.revolve([(0, 13.5), (14.5, 13.5), (14.5, 17.7), (13.4, 18.7), (0, 18.7)], back, ahead)
    face = tuple(rim[k] - 3.3 * ahead[k] for k in range(3))               # the lens's front, 3.3 inside the rim
    iris = geo.tube(11.4, 8.2, 0.7, face, ahead)
    for k in range(8):                                                    # eight lit segments
        iris -= frame(face, ahead) * bd.Rot(0, 0, 22.5 + 45.0 * k) * bd.Box(1.5, 30.0, 3.0)
    pupil = geo.tube(5.6, 4.2, 0.7, face, ahead)
    return [part(barrel, "eye_barrel", "bronze_trim"), part(lens, "eye_lens", "lens"), part(iris, "eye_iris", "glow"),
            part(pupil, "eye_pupil_ring", "bronze_trim")]


def _ear(outer):
    """The left ear: a finned pod on the skull's side, and the blade swept up and back from it."""
    at = (58.0, 10.0, 1655.0)
    pod = geo.carve(geo.revolve([(14, 0), (26, 0), (26, 22), (23.6, 22), (23.6, 24), (26, 24), (26, 26), (23.6, 26), (23.6, 28),
                                 (25, 28), (25, 29.5), (14, 29.5)], at, (1, 0, 0)), outer, "ear pod")
    cap = geo.carve(geo.revolve([(0, 0), (14, 0), (14, 30.5), (12.5, 31.5), (0, 31.5)], at, (1, 0, 0)), outer, "ear cap")
    for k in range(6):                                                    # microphone ports round the light
        angle = math.radians(60.0 * k)
        cap -= geo.cyl(1.3, 4.0, (at[0] + 28.5, at[1] + 8.5 * math.cos(angle), at[2] + 8.5 * math.sin(angle)), (1, 0, 0))
    cap -= geo.cyl(3.4, 2.0, (at[0] + 30.5, at[1], at[2]), (1, 0, 0))
    light = geo.cyl(3.4, 1.6, (at[0] + 30.5, at[1], at[2]), (1, 0, 0))
    blade = geo.plate_yz(geo.bones([(at[1] + 4, at[2] + 6, 12.0), (at[1] + 22, at[2] + 44, 6.5), (at[1] + 34, at[2] + 74, 3.0)]),
                         at[0] + 19.0, at[0] + 21.6)
    blade = geo.carve(blade - geo.cyl(23.6, 60, at, (1, 0, 0)), outer, "ear blade")   # it springs from the pod, behind its fins
    return [part(pod, "ear_pod", "bronze_trim"), part(cap, "ear_cap", "graphite"), part(light, "ear_light", "glow"),
            part(blade, "ear_blade", "ivory")]


def _head(hw, links):
    forms = _Forms()
    outer, cavity = forms(0.0), forms(SKIN_T)
    deep = forms(SKIN_T + BAY)                                            # the bay's liner stops here
    skin = geo.cut(outer, cavity, "skull skin")
    ex, _, ez = EYE

    # The sockets, seen from the front: almonds, as a bronze statue's inlaid eyes are. Each
    # springs from under the nasal, arches over its eye and tapers up toward the temple, and
    # its edge stands over the top and the bottom of the barrel behind it as lids do.
    sockets = None
    for s in (1, -1):
        socket = geo.hull([(s * 9, ez - 3, 4.0), (s * 20, ez - 1, 12.5), (s * 32, ez + 0.5, 18.0), (s * 44, ez + 3, 11.5),
                           (s * 54.5, ez + 7, 4.0)])
        sockets = socket if sockets is None else sockets + socket
    through = _front(sockets)
    visor = geo.common(geo.cut(forms(0.8), cavity, "visor shell"), through, "visor")
    # A bronze lid is laid round each socket and over the edge of its glass, as those eyes are
    # rimmed with copper; it stops against the nasal.
    lids = geo.common(geo.cut(forms(-1.0), outer, "lid shell"),
                      _front(bd.offset(sockets, amount=2.0) - bd.offset(sockets, amount=-1.2)), "eye lids")
    lids = geo.cut(lids, geo.box(13.4, 400, 400, (0, 0, 1700)), "lids at the nasal")
    wall = geo.common(geo.cut(cavity, deep, "bay wall shell"), _front(bd.offset(sockets, amount=2.5) - sockets), "bay wall")
    behind = bd.offset(sockets, amount=6.0) + bd.Pos(0, ez - 2) * bd.Rectangle(24, 26)       # one floor behind both sockets
    floor = geo.common(geo.cut(forms(SKIN_T + BAY - 3.0), deep, "bay floor shell"), _front(behind), "bay floor")
    liner = geo.fuse(wall, floor, "bay liner")
    core = geo.common(geo.box(108, 16, 52, (0, -48, ez + 1)), deep, "sensor core")    # cameras and their board, behind the bay
    for s in (1, -1):                                                     # an eye's barrel passes through both
        ahead = _eye_axis(s)
        bore = geo.cyl(18.5, 80, (s * ex + 20 * ahead[0], EYE[1] + 20 * ahead[1], ez), tuple(-a for a in ahead))
        liner, core = geo.carve(liner, bore, "eye bore in the liner"), core - bore

    # The voice: nine slots through the jaw, lit from behind.
    voice = None
    for k, tall in enumerate((5, 9, 13, 17, 20, 17, 13, 9, 5)):
        x = 6.5 * (k - 4)
        slot = _front(geo.slot(x, 1611 - tall / 2, x, 1611 + tall / 2, 1.3), back=0.0)
        voice = slot if voice is None else voice + slot
    lining = geo.cut(cavity, forms(SKIN_T + 2.0), "lining shell")         # 2 mm against the skull's inner surface
    voice_light = geo.common(lining, _front(geo.hull([(-30, 1611, 13), (30, 1611, 13)]), back=0.0), "voice light")
    baffle = geo.common(lining, geo.box(72, 120, 54, (0, 120, 1624.5)), "nape baffle")   # dark behind the nape's vents

    skull = geo.carve(geo.carve(skin, through, "sockets"), voice, "voice slots")
    # The jaw's lines, cheekbone to chin: a graphite fillet let 0.8 mm into the skin on each side.
    over = geo.cut(forms(-2.0), forms(0.8), "ridge shell")                # 2 mm proud of the skin to 0.8 mm into it
    jaw_lines = []
    for s in (1, -1):
        sweep = _front(geo.band([(s * 62, ez - 18), (s * 52, ez - 44), (s * 37, ez - 74), (s * 24, ez - 102)], 4.0), back=0.0)
        groove = geo.common(over, sweep, "jaw line's groove")
        skull = geo.carve(skull, groove, "jaw line")
        jaw_lines.append(geo.common(groove, outer, "jaw line's fillet"))
    for z, wide in ((1608, 40), (1619, 50), (1630, 56), (1641, 52)):      # vents across the nape
        skull = geo.carve(skull, geo.box(wide, 80, 2.4, (0, 120, z)), "nape vent")
    # The depth sensor: a small lens in a bronze bezel, let into the ridge on the forehead.
    jewel = (0.0, -68.0, 1716.0)
    bore = geo.cyl(7.5, 40, (jewel[0], jewel[1] - 30, jewel[2]), (0, 1, 0))
    depth_bezel = geo.revolve([(5.2, 0), (7.5, 0), (7.5, 9.0), (6.6, 10.0), (5.2, 10.0)], jewel, (0, -1, 0))
    depth_lens = geo.revolve([(0, 0), (5.2, 0), (5.2, 7.5), (0, 7.5)], jewel, (0, -1, 0))
    skull = geo.carve(skull, bore, "depth sensor's bore in the skull")
    # The ridge: a strip of the form drawn 3 mm out, from the nape over the crown and down the
    # forehead to under the sockets, where it is the nasal.
    strip = geo.common(over, geo.box(13, 400, 400, (0, 0, 1700)), "ridge strip")
    nasal = geo.carve(geo.common(strip, geo.box(40, 200, 216, (0, -100, 1752)), "ridge, front"), bore, "depth sensor's bore in the ridge")
    ridge = geo.fuse(geo.common(strip, geo.box(40, 200, 210, (0, 100, 1755)), "ridge, back"), nasal, "ridge")
    ridge = geo.carve(ridge, geo.cyl(20.5, 60, (0, 13, HEAD_TOP_Z - 30), (0, 0, 1)), "ridge round the turret")
    skull = geo.fuse(skull, ridge, "skull and ridge")
    # A graphite line is laid along the ridge from the depth sensor over the crown to the nape, as
    # the sternum's is down the chest.
    line = geo.common(geo.cut(forms(-3.0), forms(-2.0), "spine shell"), geo.box(5.0, 400, 400, (0, 0, 1700)), "spine strip")
    spine = geo.fuse(geo.common(line, geo.box(40, 200, 210, (0, 100, 1755)), "spine, back"),
                     geo.common(line, geo.box(40, 200, 140, (0, -100, 1796)), "spine, front"), "spine")

    # Frame: a lug on the pitch drive, a beam over it, a riser for the sensor core, arms to the skin.
    lug = geo.plate_yz(geo.bones([(NY, NZ, 20), (NY, NZ + 44, 14)], holes=[(NY, NZ, 4)]), 27, 37)
    beam = geo.box(67, 16, 14, (3.5, NY, NZ + 43)) + geo.box(12, 56, 12, (0, -12, NZ + 44))
    riser = geo.box(12, 8, 50, (0, -36, NZ + 69))
    seats = [((s * 25, NY, NZ + 40), (s, 0, 0)) for s in (1, -1)] + [((s * 20, NY, NZ + 45), (s * 0.25, 0.2, 1)) for s in (1, -1)]
    pads, screws = None, []
    for origin, direction in seats:
        pad = geo.common(geo.cyl(5.0, 140.0, origin, direction), cavity, "skull pad")
        pads = pad if pads is None else pads + pad
        screws.append(hw.screw("M3", *geo.seat(outer, origin, direction), label="skin_screw"))
    frame_part = lug + beam + riser + pads

    # The antenna turret stands on the skull itself: the ridge and its line stop at its collar.
    turret = geo.carve(geo.cyl(17, 26, (0, 13, HEAD_TOP_Z - 18), (0, 0, 1)), outer, "turret")
    turret = bd.fillet(turret.edges().group_by(bd.Axis.Z)[-1], 2.5)
    collar = geo.carve(geo.tube(20.5, 17, 22, (0, 13, HEAD_TOP_Z - 18), (0, 0, 1)), outer, "turret collar")
    spine = geo.carve(spine, geo.cyl(20.5, 60, (0, 13, HEAD_TOP_Z - 30), (0, 0, 1)), "spine round the turret")
    ear = _ear(outer)

    links["head"] += [part(frame_part, "head_frame", "gunmetal"), part(skull, "skull", "ivory"), *screws,
                      part(visor, "visor", "visor"), *[part(lid, "eye_lid", "bronze_trim") for lid in lids.solids()],
                      *[part(line, "jaw_line", "graphite") for line in jaw_lines],
                      part(liner, "bay_liner", "black"),
                      part(core, "sensor_core", "module"), *_eye(1), *_eye(-1),
                      part(depth_bezel, "depth_bezel", "bronze_trim"), part(depth_lens, "depth_lens", "lens"),
                      part(voice_light, "voice_light", "glow"), part(baffle, "nape_baffle", "black"),
                      part(spine, "spine_inlay", "graphite"),
                      part(turret, "crown_turret", "graphite"), part(collar, "crown_collar", "bronze_trim"),
                      *ear, *[mirror_tree(e) for e in ear]]

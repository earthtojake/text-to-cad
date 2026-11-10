"""Neck and head, on the centre plane at the zero pose.

Neck: the yaw drive sits in the chest's collar. On its output stands the neck's root, an
in-line hinge that leans the neck sideways (roll); the stem above it carries a second
in-line hinge at the base of the skull that nods the head (pitch).

Head: a helmet with one face. The pearl helmet covers the crown, the back and the sides;
the face is a single smoked shield from the brow round the temples to under the chin,
flush with the helmet and parted from it by one shut line. Under both lies a black
liner. Behind the shield the liner carries the head's sensors, which show through the
smoke only faintly: four small camera windows in a row under the brow, and a line of
light over them. The helmet ends higher at the nape than at the chin, as a helmet does,
so the neck has room when the head looks up.
"""

import build123d as bd

from . import geo, skin
from .dims import NECK, NECK_BASE, NECK_ROLL
from .geo import S
from .hardware import mount_bores, rotor_counterbores
from .kit import part

NY, NZ = NECK[1], NECK[2]
RZ = NECK_ROLL[2]
HEAD_LINKS = ("neck", "neck_stem", "head")

CROWN = (0.0, 10.0, 1764.0)
HEAD_ROWS = skin.register("head", [
    S(1540, 0, -12, rx=42, ry=46, ryn=40, n=2.4),
    S(1572, 0, -8, rx=59, ry=68, ryn=60, n=2.6),
    S(1610, 0, -3, rx=69, ry=86, ryn=75, n=2.7),
    S(1652, 0, 0, rx=75, ry=96, ryn=81, n=2.7),
    S(1694, 0, 3, rx=76, ry=95, ryn=80, n=2.6),
    S(1728, 0, 6, rx=70, ry=86, ryn=71, n=2.4),
    S(1750, 0, 9, rx=54, ry=66, ryn=53, n=2.2),
], covers=["head", "neck_stem", "neck"], link="head", above=[((-60.0, 1556.0), (70.0, 1602.0))],
    poses=[{"neck_pitch": -25}, {"neck_pitch": 40}, {"neck_roll": 25}, {"neck_roll": 25, "neck_pitch": -25}],
    skip=("sensor_bar", "camera_lens"))                     # what looks out through the skin reaches it by design
RIM = ((-60.0, 1556.0), (70.0, 1602.0))    # the helmet's lower edge in the side view (y, z): chin to nape
# The shield's edge in the side view (y, z), brow to chin: everything ahead of it is the face.
EDGE = [(-90, 1738), (-60, 1728), (-40, 1708), (-27, 1674), (-25, 1640), (-33, 1602), (-45, 1572), (-62, 1536)]
DEPTH = 7.0                                # the sensors' fascia lies this far behind the shield's glass
SENSOR_Z = 1688.0                          # the row of camera windows
SENSOR_X = (-33.0, -11.0, 11.0, 33.0)
LIGHT_Z = 1704.0


def build_head(hw, neck_yaw_output):
    """Every part of the neck and head, by link."""
    links = {name: [] for name in HEAD_LINKS}
    links["neck"] += neck_yaw_output
    _neck(hw, links)
    _head(hw, links)
    return links


def _neck(hw, links):
    yaw_at = (0.0, NY, NECK_BASE[2] - 9.0)
    lug = geo.tube(28, 6, 10, (0, NY, NECK_BASE[2]), (0, 0, 1)) - rotor_counterbores("RS00", yaw_at, (0, 0, 1), 10.0, x_dir=(-1, 0, 0))
    roll_at = (0.0, 32.0, RZ)
    rear = geo.plate_xz(geo.bones([(0, RZ, 24), (0, RZ - 24, 20)]), 32, 40) - mount_bores("RS05", roll_at, (0, 1, 0), x_dir=(1, 0, 0))
    rear -= geo.half_space((0, 0, NECK_BASE[2]), (0, 0, -1))
    stator, rotor = hw.actuator("RS05", roll_at, (0, 1, 0), x_dir=(1, 0, 0), name="neck_roll")
    links["neck"] += [part(lug + rear, "neck_root", "gunmetal"),
                      *hw.rotor_screws("RS00", yaw_at, (0, 0, 1), 10.0, x_dir=(-1, 0, 0), sunk=3.0), *stator]

    lug = geo.plate_xz(geo.bones([(0, RZ, 18), (22, RZ + 17, 12)], holes=[(0, RZ, 3)]), 41, 51)
    pitch_at = (18.0, NY, NZ)
    side = geo.plate_yz(geo.bones([(NY, NZ, 30), (46, RZ + 26, 12)]), 18, 26) - mount_bores("RS00", pitch_at, (1, 0, 0), x_dir=(0, 1, 0))
    p_stator, p_rotor = hw.actuator("RS00", pitch_at, (1, 0, 0), x_dir=(0, 1, 0), name="neck_pitch")
    links["neck_stem"] += [part(lug + side, "neck_stem", "gunmetal"), *rotor,
                           *hw.rotor_screws("RS05", roll_at, (0, 1, 0), 10.0, x_dir=(1, 0, 0)), *p_stator]
    links["head"] += [*p_rotor, *hw.rotor_screws("RS00", pitch_at, (1, 0, 0), 10.0, x_dir=(0, 1, 0))]


def _head(hw, links):
    form = skin.Form(HEAD_ROWS, top=CROWN)
    (y0, z0), (y1, z1) = RIM
    slope = (z1 - z0) / (y1 - y0)
    under = skin.from_side([(-200, z0 + slope * (-200 - y0)), (200, z0 + slope * (200 - y0))], [(200, 1400), (-200, 1400)])
    panel = geo.cut(form.panel, under, "helmet's rim")
    liner = geo.cut(form.liner, under, "liner's rim")
    cavity = form.cavity
    ahead = skin.from_side(EDGE, [(-200, 1530), (-200, 1738)], -100, 100)
    behind = skin.from_side([(y + skin.GAP, z) for y, z in EDGE], [(200, 1530), (200, 1800), (-90 + skin.GAP, 1800)], -100, 100)
    shield = geo.common(panel, ahead, "face shield")
    helmet = geo.common(panel, behind, "helmet")

    # Behind the shield the liner gives way to a fascia set DEPTH back, a tray whose rim lies under
    # the liner's edge: air between the glass and what it covers.
    def within(shift):
        return skin.from_side([(y + shift, z) for y, z in EDGE], [(-200, 1530), (-200, 1738)], -100, 100)

    lt, back = skin.PANEL_T + skin.LINER_T, skin.PANEL_T + DEPTH
    liner = geo.cut(liner, within(-3.0), "liner under the shield")
    tray = geo.common(geo.cut(form(lt), form(back + skin.LINER_T), "fascia layer"), geo.cut(within(-1.0), under, "fascia's reach"), "fascia")
    pocket = geo.common(geo.cut(form(lt - 0.5), form(back), "pocket layer"), within(-3.0 - skin.LINER_T), "fascia's pocket")
    fascia = geo.cut(tray, pocket, "fascia's tray")
    # In it: a bar of four cameras under the brow, each looking out through a window, and a line of light.
    house = geo.common(geo.box(92, 32, 24, (0, -56, SENSOR_Z)), form(back + skin.LINER_T + 0.8), "sensor bar")   # its back on the riser
    lenses = []
    for x in SENSOR_X:
        (_, y, _), _ = geo.seat(form(back), (x, 0.0, SENSOR_Z), (0, -1, 0))
        face = y + 0.6                                                    # the window, just inside the fascia's outside
        fascia = geo.carve(fascia, geo.cyl(6.4, 14, (x, face - 7, SENSOR_Z), (0, 1, 0)), "camera window")
        house = (house - geo.cyl(4.6, 5.0, (x, face - 1.0, SENSOR_Z), (0, 1, 0))) + geo.tube(6.0, 4.6, 12, (x, face, SENSOR_Z), (0, 1, 0))
        lenses.append(part(geo.cyl(4.6, 1.4, (x, face + 0.4, SENSOR_Z), (0, 1, 0)), "camera_lens", "lens"))
    slot = skin.from_front(geo.slot(-27, LIGHT_Z, 27, LIGHT_Z, 0.9))
    light = geo.common(geo.cut(form(back), form(back + skin.LINER_T), "fascia's floor"), slot, "status light")
    fascia = geo.carve(fascia, slot, "status light's slot")

    # The helmet's own lines: a slot at each temple over a microphone, three vents across the nape.
    for s in (1, -1):
        helmet = geo.carve(helmet, skin.from_side([(16, 1640), (34, 1672)], [(37, 1670), (19, 1638)], s * 40 if s > 0 else -120,
                                                  120 if s > 0 else -40), "temple slot")
    for z, wide in ((1624, 46), (1634, 54), (1644, 58)):
        helmet = geo.carve(helmet, geo.box(wide, 80, 2.2, (0, 120, z)), "nape vent")

    # Frame: a lug on the pitch drive, a beam over it, a riser to the sensor bar, arms to the liner.
    lug = geo.plate_yz(geo.bones([(NY, NZ, 20), (NY, NZ + 44, 14)], holes=[(NY, NZ, 4)]), 27, 37)
    beam = geo.box(67, 16, 14, (3.5, NY, NZ + 43)) + geo.box(12, 60, 12, (0, -10, NZ + 44))
    riser = geo.box(12, 8, 72, (0, -36, NZ + 80))
    frame_part = lug + beam + riser
    pads = None
    for origin, direction in ([((s * 25, NY, NZ + 40), (s, 0, 0)) for s in (1, -1)]
                              + [((s * 20, NY, NZ + 45), (s * 0.25, 0.2, 1)) for s in (1, -1)]):
        pad = geo.common(geo.cyl(5.0, 140.0, origin, direction), cavity, "liner pad")
        pads = pad if pads is None else pads + pad

    links["head"] += [part(frame_part, "head_frame", "gunmetal"), part(skin.solids(pads - frame_part), "pad_head", "gunmetal"),
                      part(skin.solids(helmet), "helmet", "shell"),
                      part(skin.solids(shield), "face_shield", "smoke35"), part(skin.solids(liner), "head_liner", "under"),
                      part(skin.solids(fascia), "face_fascia", "under"),
                      part(skin.solids(house), "sensor_bar", "module"), *lenses, part(skin.solids(light), "status_light", "light")]

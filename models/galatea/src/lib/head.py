"""Neck and head, on the centre plane at the zero pose.

Neck: the yaw drive sits in the chest's collar. On its output stands the neck's root, an
in-line hinge that leans the neck sideways (roll); the stem above it carries a second
in-line hinge at the base of the skull that nods the head (pitch).

Head: an ivory skull over a frame hung from the pitch drive, a smoked visor wrapped across
the face with two light bars for eyes, the camera module behind it, an ear pod each side
(microphone and speaker) and a puck on the crown for the antennas.
"""

import build123d as bd

from . import geo
from .dims import HEAD_TOP_Z, NECK, NECK_BASE, NECK_ROLL, PLATE_T
from .kit import mirror_tree, part

NY, NZ = NECK[1], NECK[2]
RZ = NECK_ROLL[2]
SKIN_T = 2.6
HEAD_LINKS = ("neck", "neck_stem", "head")

SKULL_ROWS = (
    # z, centre y, half-width, back depth, exponent, front depth
    (1562, 16, 52, 60, 2.4, 48),
    (1596, 12, 67, 78, 2.4, 72),
    (1645, 8, 77, 92, 2.4, 90),
    (1694, 8, 75, 92, 2.3, 84),
    (1728, 10, 60, 77, 2.2, 64),
    (1744, 12, 38, 50, 2.1, 40),
)


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


def _head(hw, links):
    crown = (0.0, 13.0, HEAD_TOP_Z)
    skin, cavity, outer = geo.shell(_skull_rows(), SKIN_T, top=crown)

    # The visor's outline: a band across the face seen from the front, round-ended seen from the side.
    band = geo.plate_xz(geo.hull([(-52, 1668, 27), (52, 1668, 27)]), -200, 60) \
        & geo.plate_yz(geo.hull([(-120, 1668, 27), (-36, 1668, 27)]), -120, 120)
    eyes = None
    for s in (1, -1):
        eye = geo.plate_xz(geo.hull([(s * 22, 1666.5, 4.2), (s * 47, 1672.5, 4.2)]), -200, 0)
        eyes = eye if eyes is None else eyes + eye
    visor = (skin & band) - eyes
    lights = skin & eyes
    skull = skin - band
    skull -= geo.box(2.2, 400, 100, (0, 150, 1750)) + geo.box(2.2, 200, 200, (0, 120, 1620))   # the crest's reveal, brow to nape
    grille = None
    for z in (1601, 1609, 1617):                                          # voice grille under the visor
        slit = geo.plate_xz(geo.slot(-15, z, 15, z, 1.2), -200, 0)
        grille = slit if grille is None else grille + slit
    skull -= grille

    # Frame: a lug on the pitch drive, a beam over it, arms to the skin.
    lug = geo.plate_yz(geo.bones([(NY, NZ, 20), (NY, NZ + 44, 14)], holes=[(NY, NZ, 4)]), 27, 37)
    beam = geo.box(67, 16, 14, (3.5, NY, NZ + 43)) + geo.box(12, 70, 12, (0, -21, NZ + 44))
    riser = geo.box(12, 8, 44, (0, -52, NZ + 68))                         # carries the camera module
    seats = [((s * 25, NY, NZ + 40), (s, 0, 0)) for s in (1, -1)] + [((s * 20, NY, NZ + 45), (s * 0.25, 0.2, 1)) for s in (1, -1)]
    pads, screws = None, []
    for origin, direction in seats:
        pad = geo.mount_pad(cavity, origin, direction, 5.0, 140.0)
        pads = pad if pads is None else pads + pad
        screws.append(hw.screw("M3", *geo.seat(outer, origin, direction), label="skin_screw"))
    frame = lug + beam + riser + pads

    module = (geo.box(96, 30, 40, (0, -71, 1668)) & cavity) - geo.half_space((0, -56, 0), (0, 1, 0))
    puck = geo.cyl(17, 19, (0, 13, HEAD_TOP_Z - 14), (0, 0, 1)) - outer
    puck = bd.fillet(puck.edges().group_by(bd.Axis.Z)[-1], 2.5)
    ear_ring = geo.tube(24, 16, 40, (50, 10, 1650), (1, 0, 0)) - outer - geo.half_space((84, 0, 0), (1, 0, 0))
    ear_core = geo.cyl(16, 40, (50, 10, 1650), (1, 0, 0)) - outer - geo.half_space((81, 0, 0), (1, 0, 0))
    for z in (1643, 1650, 1657):
        ear_core -= geo.box(8, 22, 2.4, (80, 10, z))
    ears = [part(ear_ring, "ear_ring", "bronze_trim"), part(ear_core, "ear_grille", "graphite")]

    links["head"] += [part(frame, "head_frame", "gunmetal"), part(skull, "skull", "ivory"), *screws,
                      part(visor, "visor", "visor"), part(lights, "eye_lights", "glow"),
                      part(module, "camera_module", "module"), part(puck, "crown_puck", "graphite"),
                      *ears, *[mirror_tree(e) for e in ears]]

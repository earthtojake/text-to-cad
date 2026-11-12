"""Galatea's exterior as a styling model: the outside alone, at the standing pose.

    cad run src/styling.py

Every volume here is a plain solid on the robot's joint layout (`lib.dims`): pearl panels
over a black under-body, black joints, one smoked face. Nothing inside it is modelled
(but the hands, which are the robot's own) and nothing moves. It is the page the
proportions and the panel lines are settled on before the shells are built over the
mechanism.
"""

import build123d as bd
from cad import model

from lib import geo
from lib.dims import ANKLE, ELBOW, HIP, KNEE, SHOULDER
from lib.finish import material
from lib.geo import S
from lib.hand import build_hand
from lib.hardware import Hardware
from lib.kit import group, mirror_tree, part

GAP = 1.6          # a shut line between two panels
SKIN = 3.0         # a panel's thickness over the under-body
WIDE = 400.0


def piece(shape, label, finish):
    """A labelled, finished part; what a boolean returned in several pieces is one part of them."""
    solids = list(shape) if isinstance(shape, (list, bd.ShapeList)) else shape.solids()
    if not solids:
        raise ValueError(f"{label}: nothing is left of it")
    return part(solids[0] if len(solids) == 1 else bd.Compound(solids), label, finish)


def forms(rows, **loft):
    """(panel shell, under-body solid) of one lofted form."""
    outer, core = geo.loft(rows, **loft), geo.loft(rows, shrink=SKIN, **loft)
    return outer - core, core


def from_side(points, closing, x0=-WIDE, x1=WIDE):
    """The region ahead of (or behind) a curve drawn in the side view (y, z), as a prism across the robot."""
    return geo.plate_yz(geo.behind_curve(points, closing), x0, x1)


def from_front(face, y0=-WIDE, y1=0.0):
    """An outline drawn in the front view (x, z), as a prism through the robot's front (or all of it)."""
    return geo.plate_xz(face, y0, y1)


def recolour(node):
    """The robot's own hand in the styling model's two tones."""
    if node.children:
        for child in node.children:
            recolour(child)
    else:
        node.material = material("shell" if node.label == "hand_back" else "joint" if "pin" in node.label else "under")
    return node


def head():
    rows = [
        S(1546, 0, -14, rx=44, ry=44, ryn=42, n=2.4),
        S(1574, 0, -8, rx=60, ry=66, ryn=62, n=2.6),
        S(1610, 0, -3, rx=69, ry=84, ryn=75, n=2.7),
        S(1652, 0, 0, rx=75, ry=95, ryn=81, n=2.7),
        S(1694, 0, 3, rx=76, ry=98, ryn=80, n=2.6),
        S(1728, 0, 7, rx=70, ry=92, ryn=71, n=2.4),
        S(1750, 0, 11, rx=54, ry=72, ryn=53, n=2.2),
    ]
    crown = (0.0, 14.0, 1764.0)
    shell = geo.loft(rows, top=crown) - geo.loft(rows, shrink=SKIN, top=(crown[0], crown[1], crown[2] - SKIN))
    core = geo.loft(rows, shrink=SKIN, top=(crown[0], crown[1], crown[2] - SKIN))
    # The face: one shield, from the brow round the temples to under the chin.
    edge = [(-90, 1738), (-60, 1728), (-40, 1708), (-27, 1674), (-25, 1640), (-33, 1600), (-47, 1566), (-60, 1530)]
    ahead = from_side(edge, [(-200, 1530), (-200, 1738)], -100, 100)
    behind = from_side([(y + GAP, z) for y, z in edge], [(200, 1530), (200, 1800), (-90 + GAP, 1800)], -100, 100)
    shield = shell & ahead
    helmet = shell & behind
    neck = geo.loft([S(1490, 0, 14, rx=47, ry=50, n=2.3), S(1530, 0, 12, rx=42, ry=45, n=2.3), S(1562, 0, 8, rx=40, ry=44, n=2.3)])
    return group("head", piece(helmet, "helmet", "shell"), piece(shield, "face_shield", "face"), piece(core, "head_core", "under"),
                 piece(neck, "neck", "under"))


def torso():
    chest_rows = [
        S(1262, 0, 10, rx=114, ry=96, ryn=96, n=3.0),
        S(1330, 0, 10, rx=128, ry=104, ryn=108, n=3.0),
        S(1392, 0, 10, rx=140, ry=110, ryn=118, n=3.0),
        S(1440, 0, 10, rx=143, ry=110, ryn=114, n=3.0),
        S(1478, 0, 10, rx=134, ry=98, ryn=94, n=2.8),
        S(1502, 0, 11, rx=102, ry=76, ryn=68, n=2.5),
        S(1513, 0, 12, rx=68, ry=60, ryn=52, n=2.3),
    ]
    panel, core = forms(chest_rows)
    # The breastplate ends in a shallow V over the waist; the flanks under the arms stay black.
    below = from_front(geo.polygon((-200, 1200), (-200, 1318), (0, 1276), (200, 1318), (200, 1200)), y1=10)
    flank = geo.polygon((-44, 1240), (-30, 1396), (-10, 1448), (50, 1448), (40, 1240))
    flanks = geo.plate_yz(flank, 96, 200) + geo.plate_yz(flank, -200, -96)
    seam = geo.box(GAP, 200, 260, (0, -100, 1390))
    chest = panel - below - flanks - seam
    chest = chest - geo.box(400, 200, 30, (0, 110, 1262))              # the back plate ends square
    pack = bd.Pos(0, 116, 1382) * bd.fillet(bd.Box(168, 30, 176).edges(), 12)        # the battery, on the back
    collar = geo.tube(58, 48, 8, (0, 13, 1509), (0, 0, 1))
    # The waist: black, narrower than what it joins, with one plate at the front.
    waist_rows = [S(1076, 0, 12, rx=108, ry=90, ryn=82, n=2.7), S(1160, 0, 12, rx=101, ry=86, ryn=80, n=2.6),
                  S(1276, 0, 11, rx=114, ry=96, ryn=96, n=2.8)]
    waist_panel, waist = forms(waist_rows)
    ab = bd.fillet(geo.polygon((-60, 1273), (0, 1260), (60, 1273), (46, 1126), (-46, 1126)).vertices(), 7)
    plate = waist_panel & from_front(ab)
    pelvis_rows = [
        S(884, 0, 8, rx=104, ry=90, ryn=80, n=2.8),
        S(940, 0, 8, rx=122, ry=98, ryn=88, n=2.9),
        S(1000, 0, 8, rx=128, ry=102, ryn=92, n=2.9),
        S(1060, 0, 9, rx=120, ry=98, ryn=88, n=2.8),
        S(1096, 0, 10, rx=110, ry=92, ryn=84, n=2.7),
    ]
    girdle, pelvis_core = forms(pelvis_rows)
    legs = geo.plate_xz(geo.polygon((-220, 860), (-220, 990), (-140, 984), (-60, 930), (0, 904), (60, 930), (140, 984), (220, 990),
                                    (220, 860)), -300, 300)
    front_plate = girdle & from_front(geo.hull([(-70, 1080, 8), (70, 1080, 8), (-88, 1034, 10), (88, 1034, 10), (-34, 936, 12),
                                                (34, 936, 12)]))
    back_plate = girdle & from_front(geo.hull([(-80, 1076, 10), (80, 1076, 10), (-90, 1020, 10), (90, 1020, 10), (-50, 950, 12),
                                               (50, 950, 12)]), y0=0.0, y1=WIDE)
    return group("torso", piece(chest, "chest_shell", "shell"), piece(core, "chest_core", "under"), piece(pack, "pack", "shell"),
                 piece(collar, "collar", "joint"), piece(waist, "waist", "under"), piece(plate, "waist_plate", "shell"),
                 piece(pelvis_core - legs, "pelvis_core", "under"), piece(front_plate, "pelvis_front", "shell"),
                 piece(back_plate, "pelvis_back", "shell"))


def arm():
    sx, _, sz = SHOULDER
    cap_rows = [S(1344, sx + 2, 0, rx=44, rxn=42, ry=47, n=2.5), S(1388, sx + 2, 0, rx=52, rxn=52, ry=55, n=2.5),
                S(1432, sx + 1, 0, rx=53, rxn=55, ry=55, n=2.4), S(1464, sx - 2, 0, rx=44, rxn=50, ry=46, n=2.3)]
    cap = geo.loft(cap_rows, top=(sx - 4, 0.0, 1484.0)) - geo.loft(cap_rows, shrink=SKIN, top=(sx - 4, 0.0, 1481.0), extend=(10.0, 0.0))
    cap = cap - geo.box(60, 200, 200, (sx - 66, 0, 1396))               # open toward the chest
    ball = bd.Pos(sx, 0, sz) * bd.Sphere(44) + geo.cyl(43, 62, (140, 0, sz), (1, 0, 0))
    upper, upper_core = forms([S(1186, sx, 0, rx=35, ry=38, n=3.0), S(1270, sx, 0, rx=39, ry=44, n=3.0),
                               S(1352, sx + 1, 0, rx=40, ry=44, n=2.8)])
    elbow_core = geo.loft([S(1084, sx, 0, rx=33, ry=37, n=2.6), S(1130, sx, 0, rx=36, ry=40, n=2.6), S(1196, sx, 0, rx=34, ry=37, n=2.6)])
    elbow_cap = geo.cyl(23, 76, (sx - 38, 0, ELBOW[2]), (1, 0, 0))
    fore, fore_core = forms([S(934, sx, 0, rx=29, ry=33, n=2.8), S(990, sx, 0, rx=37, ry=41, n=3.0),
                             S(1046, sx, 0, rx=41, ry=45, n=3.0), S(1092, sx, 0, rx=37, ry=40, n=3.0)])
    fore = fore - geo.box(200, 200, GAP, (sx, 0, 1039))                 # where the forearm turns
    wrist = geo.loft([S(880, sx, 0, rx=22, ry=29, n=2.5), S(936, sx, 0, rx=27, ry=31, n=2.5)])
    hand = [recolour(group(name, parts)) for name, parts in build_hand(Hardware(), []).items() if parts]
    return group("l_arm", piece(cap, "shoulder_cap", "shell"), piece(ball, "shoulder", "under"), piece(upper, "upper_arm_shell", "shell"),
                 piece(upper_core, "upper_arm_core", "under"), piece(elbow_core, "elbow_core", "under"),
                 piece(elbow_cap, "elbow_cap", "joint"), piece(fore, "forearm_shell", "shell"), piece(fore_core, "forearm_core", "under"),
                 piece(wrist, "wrist", "under"), *hand)


def leg():
    hx = HIP[0]
    thigh_rows = [
        S(556, hx, -2, rx=48, rxn=46, ry=54, ryn=58, n=3.0),
        S(700, hx + 2, -2, rx=56, rxn=52, ry=64, ryn=70, n=3.2),
        S(850, hx + 5, -2, rx=64, rxn=57, ry=74, ryn=80, n=3.2),
        S(930, hx + 7, -2, rx=64, rxn=55, ry=72, ryn=76, n=3.0),
    ]
    panel, core = forms(thigh_rows)
    above = geo.plate_xz(geo.polygon((-40, 1100), (-40, 838), (30, 838), (156, 906), (260, 906), (260, 1100)), -300, 300)
    # The panel covers the front and both sides; behind a line that falls forward toward the knee, the thigh is black.
    thigh = panel - above
    hip = geo.cyl(54, 116, (hx - 52, 0, HIP[2]), (1, 0, 0))
    hip_cap = geo.cyl(40, 4, (hx + 62, 0, HIP[2]), (1, 0, 0))
    knee_rows = [S(440, hx, 0, rx=44, ry=54, ryn=50, n=2.8), S(500, hx, 2, rx=47, ry=58, ryn=54, n=2.8),
                 S(566, hx, -2, rx=46, ry=54, ryn=56, n=2.8)]
    knee_panel, knee_core = forms(knee_rows)
    knee_guard = knee_panel & from_front(geo.hull([(hx - 22, 540, 10), (hx + 22, 540, 10), (hx - 34, 470, 8), (hx + 34, 470, 8),
                                                   (hx - 44, 452, 4), (hx + 44, 452, 4)]))
    knee_cap = geo.cyl(26, 100, (hx - 50, 0, KNEE[2]), (1, 0, 0))
    shin_rows = [
        S(140, hx, 0, rx=33, rxn=32, ry=42, ryn=37, n=2.8),
        S(250, hx, 0, rx=40, rxn=39, ry=56, ryn=44, n=3.0),
        S(360, hx, 0, rx=47, rxn=45, ry=70, ryn=50, n=3.0),
        S(444, hx, 0, rx=48, rxn=46, ry=64, ryn=54, n=3.0),
    ]
    shin_panel, shin_core = forms(shin_rows)
    shin = shin_panel & from_side([(26, 470), (22, 360), (14, 250), (6, 120)], [(-200, 120), (-200, 470)])
    ankle_core = geo.loft([S(80, hx, -2, rx=30, ry=40, ryn=34, n=2.5), S(146, hx, 0, rx=31, ry=41, ryn=35, n=2.5)])
    ankle_cap = geo.cyl(19, 68, (hx - 34, 0, ANKLE[2]), (1, 0, 0))
    sole = geo.loft([S(0, hx, -64, rx=47, ry=124, ryn=126, n=2.6), S(13, hx, -64, rx=48, ry=125, ryn=127, n=2.6)])
    upper = geo.loft([S(13, hx, -64, rx=47, ry=123, ryn=125, n=2.6), S(28, hx, -56, rx=45, ry=112, ryn=120, n=2.6),
                      S(48, hx, -24, rx=39, ry=80, ryn=76, n=2.5), S(70, hx, -6, rx=34, ry=56, ryn=46, n=2.5)])
    upper = upper - geo.box(200, GAP, 100, (hx, -118, 50))             # the toe's hinge line
    return group("l_leg", piece(thigh, "thigh_shell", "shell"), piece(core - above, "thigh_core", "under"), piece(hip, "hip", "under"),
                 piece(hip_cap, "hip_cap", "joint"), piece(knee_core, "knee_core", "under"), piece(knee_guard, "knee_guard", "shell"),
                 piece(knee_cap, "knee_cap", "joint"), piece(shin, "shin_shell", "shell"), piece(shin_core, "shin_core", "under"),
                 piece(ankle_core, "ankle_core", "under"), piece(ankle_cap, "ankle_cap", "joint"), piece(sole, "sole", "rubber"),
                 piece(upper, "foot_shell", "shell"))


@model
def galatea_styling():
    left_arm, left_leg = arm(), leg()
    return group("galatea_styling", head(), torso(), left_arm, mirror_tree(left_arm, "r_arm"), left_leg, mirror_tree(left_leg, "r_leg"))


if __name__ == "__main__":
    galatea_styling()

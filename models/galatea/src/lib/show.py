"""The exploded view: an animation of the robot's GLB (`cad.build123d.animation`), not a motion.

It is no part of the mechanism: the document's joints, states and motions know nothing of
it, and a STEP shows none of it. Every GLB exported from the model carries it as the clip
`explode`, which the CAD Viewer's playbar plays and `film.py` renders.

It comes apart in two stages, with a hold after each, and comes back:

    first     the links go apart up the robot and the arms out to the sides, so that each
              joint opens; the parts of each link start away from its middle; then each
              skin slides off the mechanism it covers (a limb's sideways, the trunk's
              forward, the hatch backward, the helmet up and back);
    second    every piece on its own: the links further apart and wider, each part well
              away from its link's middle (a drive off its plate, every screw off its
              hole), the skins further off.

The numbers are choreography, set by looking: nothing else in the model reads them.
"""

from cad.build123d import animation

from .dims import FINGERS

DURATION = 9.0
ONE = (1.30, 2.20)            # it stands whole until the first stage: the links apart, seconds
BURST = (1.45, 2.30)          # ... the parts of each a little
SLIDE = (2.32, 2.85)          # ... then the skins off
TWO = (3.90, 4.90)            # the second stage: links, parts and skins all further
BACK = (7.30, 8.80)           # everything comes back: skins first, then parts and links
NEAR, FAR = 45.0, 150.0       # how far a part stands from its link's middle after each stage, mm

# Where a link goes in the first stage: (outward from the centre plane, backward, up), mm, times FIRST. A side
# link's is the left one's. In the second stage it goes to SECOND times that, each direction by its own factor,
# and a leg's links a little further out as well: the robot comes apart wider than it is tall.
FIRST, SECOND, LEG_OUT = 0.75, (3.0, 1.6, 0.82), 170.0
STACK = {
    "toe": (0, -50, 0), "foot": (0, 0, 0), "ankle_gimbal": (0, 0, 50), "ankle_rods": (0, 70, 150),
    "ankle_crank": (60, 40, 200), "shin": (0, 0, 130), "knee_rod": (0, 90, 330), "knee_crank": (40, 60, 400),
    "thigh": (10, 0, 300), "hip_cradle": (40, 0, 440), "hip_yoke": (20, 30, 520),
    "pelvis": (0, 0, 560), "lumbar_yoke": (0, 0, 650), "waist_cross": (0, 0, 720), "chest": (0, 0, 800),
    "neck": (0, 0, 930), "neck_stem": (0, 0, 990), "head": (0, 0, 1060),
    "shoulder_yoke": (70, 0, 800), "shoulder_block": (140, 0, 800), "upper_arm": (210, 0, 740),
    "forearm": (250, 0, 680), "forearm_distal": (270, 0, 620), "wrist_link": (285, 0, 570), "palm": (300, 0, 520),
    "thumb_meta": (300, -40, 510), "thumb_prox": (300, -70, 485), "thumb_dist": (300, -100, 460),
    **{f"{finger}_{bone}": (300, 0, up) for finger in FINGERS for bone, up in (("prox", 480), ("mid", 450), ("dist", 420))},
}
LEGS = ("toe", "foot", "ankle_gimbal", "ankle_rods", "ankle_crank", "shin", "knee_rod", "knee_crank", "thigh", "hip_cradle", "hip_yoke")
# About where the middle of a link's parts is, at the zero pose, mm (the left one's): what its parts move away from.
# A link that is not here (a phalanx: a bone, a pin, a pad) keeps its parts together.
MIDDLE = {
    "foot": (82, -20, 40), "ankle_gimbal": (82, 0, 90), "shin": (82, 5, 300), "thigh": (90, 0, 700),
    "ankle_crank": (110, 30, 345), "knee_crank": (82, 20, 780), "hip_cradle": (100, 10, 920), "hip_yoke": (82, 60, 930),
    "pelvis": (0, 10, 1042), "lumbar_yoke": (0, 50, 1120), "waist_cross": (0, 32, 1150), "chest": (0, 35, 1350),
    "neck": (0, 20, 1515), "neck_stem": (10, 25, 1560), "head": (0, 0, 1660), "toe": (82, -150, 20),
    "shoulder_yoke": (175, 25, 1420), "shoulder_block": (212, 10, 1410), "upper_arm": (215, 0, 1250),
    "forearm": (225, 0, 1075), "forearm_distal": (212, 0, 980), "wrist_link": (220, -10, 900), "palm": (212, 0, 810),
}
# Where a skin goes when it slides off what it covers: label (or its beginning) -> the same three, mm. In the
# second stage it goes half as far again.
SKINS = {
    "panel_chest": (0, -380, 0), "liner_chest": (0, -220, 0), "status_light": (0, -220, 0), "panel_hatch": (0, 260, 0),
    "wordmark": (0, 260, 0), "liner_neck_deck": (0, 0, 90), "trim_collar": (0, 0, 90),
    "panel_pelvis": (0, -260, 0), "liner_pelvis": (0, -150, 0), "liner_belly": (0, -120, 0),
    "helmet": (0, 160, 140), "trim_temple": (0, 160, 140), "head_liner": (0, 90, 80), "face_shield": (0, -220, 0),
    "face_fascia": (0, -110, 0),
    "panel_thigh": (260, 0, 0), "liner_thigh": (150, 0, 0), "panel_shin": (260, 0, 0), "liner_shin": (150, 0, 0),
    "panel_hip": (160, 0, 0), "trim_hip": (160, 0, 0), "panel_shoulder": (150, 0, 60),
    "panel_upper_arm": (220, 0, 0), "trim_upper_arm": (220, 0, 0), "liner_upper_arm": (130, 0, 0),
    "panel_forearm_cuff": (120, 0, 0), "panel_forearm": (200, 0, 0), "trim_forearm": (200, 0, 0), "liner_forearm": (120, 0, 0),
    "foot_shell": (170, 0, 0), "toe_cap": (0, -120, 0), "hand_back": (70, 0, 0),
}
HEAD_LIGHT = (0, -110, 0)     # the head's status light goes with its fascia, not with a liner
FURTHER = 0.5


def explode(robot):
    """Write the animation `explode` on the assembled robot (whose children are its links)."""
    show = animation(robot, "explode", duration=DURATION)
    zero = (0, 0, 0)
    for link in robot.children:
        name = link.label
        sign, base = (-1, name[2:]) if name.startswith("r_") else (1, name[2:] if name.startswith("l_") else name)
        side = lambda v, k=1.0: (sign * v[0] * k, v[1] * k, v[2] * k)
        out, back, up = STACK[base]
        near = side((out, back, up), FIRST)
        far = side((out * SECOND[0] + (LEG_OUT if base in LEGS else 0.0), back * SECOND[1], up * SECOND[2]))
        if any(far):
            # A link is named by a glob that only its own name matches: a plain name is refused where a link and a part
            # of it share one (`lumbar_yoke`, `neck_stem`), and of a glob's matches the outermost is taken.
            show.channel(f"{name[:-1]}[{name[-1]}]", path="translation",
                         keys=[(ONE[0], zero), (ONE[1], near), (TWO[0], near), (TWO[1], far), (BACK[0] + 0.5, far), (BACK[1], zero)])
        several = lambda label: sum(part.label == label for part in link.children) > 1
        ref = lambda label: f"{name}/{label}*" if several(label) else f"{name}/{label}"
        for label in sorted({part.label for part in link.children}):
            slide = HEAD_LIGHT if (base, label) == ("head", "status_light") else next(
                (v for start, v in SKINS.items() if label.startswith(start)), None)
            if slide is not None:                           # a skin: off what it covers, then further
                first, second = side(slide), side(slide, 1.0 + FURTHER)
                show.channel(ref(label), path="translation",
                             keys=[(SLIDE[0], zero), (SLIDE[1], first), (TWO[0], first), (TWO[1], second), (BACK[0], second),
                                   (BACK[0] + 0.55, zero)])
            elif base in MIDDLE and len(link.children) > 1:  # any other part: away from the link's middle, twice
                middle = side(MIDDLE[base])
                show.explode(ref(label), radial=middle, distance=NEAR, start=BURST[0], end=BURST[1])
                show.explode(ref(label), radial=middle, distance=FAR - NEAR, start=TWO[0] + 0.05, end=TWO[1])
                show.explode(ref(label), radial=middle, distance=-FAR, start=BACK[0] + 0.45, end=BACK[1] - 0.15)
    return robot

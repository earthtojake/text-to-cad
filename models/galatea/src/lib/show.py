"""The exploded view: an animation of the robot's GLB (`cad.build123d.animation`), not a motion.

It is no part of the mechanism: the document's joints, states and motions know nothing of
it, and a STEP shows none of it. Every GLB exported from the model carries it as the clip
`explode`, which the CAD Viewer's playbar plays and `film.py` renders.

Three things move, each on its own clock, and all come back:

    links     apart along the robot: every link up from the feet by its place in the stack,
              the arms out to the sides as well, so that each joint opens;
    parts     within a link, away from its middle (the helper `.explode`): a drive off its
              plate, the screws off their holes;
    skins     after that, each skin off the mechanism it covers: a limb's sideways, the
              trunk's forward, the hatch backward, the helmet up and back.

The numbers are choreography, set by looking: nothing else in the model reads them.
"""

from cad.build123d import animation

from .dims import FINGERS

DURATION = 5.0
OUT = (0.30, 1.20)            # the links go apart, seconds
BURST = (0.45, 1.30)          # ... and the parts of each
SLIDE = (1.20, 1.75)          # ... then the skins slide off
BACK = (3.50, 4.70)           # everything comes back: skins first, then parts and links
SPREAD = 0.75                 # how far apart, as a share of STACK
PARTS = 45.0                  # how far a part goes from its link's middle, mm

# Where a link goes: (outward from the centre plane, backward, up), mm. A side link's is the left one's.
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
# Where a skin goes after that, off what it covers: label (or its beginning) -> the same three, mm.
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


def explode(robot):
    """Write the animation `explode` on the assembled robot (whose children are its links)."""
    show = animation(robot, "explode", duration=DURATION)
    for link in robot.children:
        name = link.label
        sign, base = (-1, name[2:]) if name.startswith("r_") else (1, name[2:] if name.startswith("l_") else name)
        side = lambda v, k=1.0: (sign * v[0] * k, v[1] * k, v[2] * k)
        away = side(STACK[base], SPREAD)
        if any(away):
            # A link is named by a glob that only its own name matches: a plain name is refused where a link and a part
            # of it share one (`lumbar_yoke`, `neck_stem`), and of a glob's matches the outermost is taken.
            whole = f"{name[:-1]}[{name[-1]}]"
            show.channel(whole, path="translation", keys=[(OUT[0], (0, 0, 0)), (OUT[1], away), (BACK[0] + 0.2, away), (BACK[1], (0, 0, 0))])
        if len(link.children) > 1:
            show.explode(f"{name}/*", radial=True, distance=PARTS, start=BURST[0], end=BURST[1])
            show.explode(f"{name}/*", radial=True, distance=-PARTS, start=BACK[0] + 0.1, end=BACK[1] - 0.15)
        labels = {part.label for part in link.children}
        for label in sorted(labels):
            move = HEAD_LIGHT if (base, label) == ("head", "status_light") else next(
                (v for start, v in SKINS.items() if label.startswith(start)), None)
            if move is None:
                continue
            ref = f"{name}/{label}*" if sum(part.label == label for part in link.children) > 1 else f"{name}/{label}"
            show.translation(ref, by=side(move), start=BURST[1] + 0.02, end=SLIDE[1])          # after its burst: one part's channels may not overlap
            show.translation(ref, by=side(tuple(-v for v in move)), start=BACK[0] - 0.45, end=BACK[0] + 0.08)
    return robot

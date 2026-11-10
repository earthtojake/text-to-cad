"""The left hand at the zero pose: fingers hanging, palm toward the thigh, thumb forward.

Four fingers of three phalanges on barrel hinges and a thumb that swings across the palm
on an opposition pivot. Each finger is one tendon-driven degree of freedom: its three
knuckles are coupled in the assembly (`galatea.py`), as are the thumb's two.

A phalanx is a prototype in its own frame: the hinge axis along local X, the palmar side
local +Y, the bone running down local -Z from the hinge. That makes it symmetric about its
local YZ plane, so the right hand places the same prototypes.
"""

import build123d as bd

from . import geo
from .dims import FINGERS, KNUCKLE_Z, SHOULDER, THUMB_BASE, THUMB_BONES, THUMB_DIR, THUMB_IP, THUMB_MCP, THUMB_ROOT, WRIST_YAW
from .hardware import pin
from .kit import frame, inst, part, proto

SX = SHOULDER[0]
YZ = WRIST_YAW[2]
BARREL_R = 7.0
THICK = 13.0
HAND_LINKS = ("palm", *[f"{finger}_{bone}" for finger in FINGERS for bone in ("prox", "mid", "dist")],
              "thumb_meta", "thumb_prox", "thumb_dist")


def _barrel(width):
    return geo.cyl(BARREL_R, width, (0, 0, 0), (1, 0, 0), centered=True) - geo.cyl(2.5, width + 2, (0, 0, 0), (1, 0, 0), centered=True)


def _ears(length, width):
    """The fork at a phalanx's far end that carries the next one's barrel."""
    ear = geo.plate_yz(geo.hull([(0, -length, 6.0), (0, -length + 9, 6.0)]), 0, 3.0)
    return bd.Pos(width / 2 - 3.0, 0, 0) * ear + bd.Pos(-width / 2, 0, 0) * ear


def _bone(length, width, root_width, tip=False):
    """A phalanx: a barrel `root_width` wide on the hinge, a neck, the body and, unless it is
    the fingertip, a fork for the next hinge."""
    neck = geo.box(root_width, THICK - 2, 10, (0, 0, -5))
    if tip:
        body = geo.box(width - 2, THICK, length - 8 - 6.5, (0, 0, -8 - (length - 14.5) / 2))
        nose = geo.cyl(6.5, width - 2, (0, 0, -length + 6.5), (1, 0, 0), centered=True)
        shape = _barrel(root_width) + neck + body + nose
    else:
        body = geo.box(width - 2, THICK, length - 8 - 9, (0, 0, -8 - (length - 17) / 2))
        shape = _barrel(root_width) + neck + body + _ears(length, width)
        shape -= geo.cyl(2.5, width + 2, (0, 0, -length), (1, 0, 0), centered=True)
    return shape - geo.cyl(2.5, width + 2, (0, 0, 0), (1, 0, 0), centered=True)      # the hinge pin's bore


def _pad(length, width, tip=False):
    start, end = (10.0, length - 3.0) if tip else (12.0, length - 13.0)
    return geo.box(width - 4, 2.5, end - start, (0, THICK / 2 + 1.25, -(start + end) / 2))


class _Bones:
    """Phalanx prototypes, one per distinct size."""

    def __init__(self):
        self._made = {}

    def place(self, kind, length, width, loc, label):
        key = (kind, length, width)
        if key not in self._made:
            root = width if kind == "prox" else width - 7.0
            tip = kind == "dist"
            bone = proto(_bone(length, width, root, tip), "shell" if tip else "slate")
            pad = proto(_pad(length, width, tip), "rubber") if (tip or length - 25.0 > 6.0) else None
            hinge = proto(geo.cyl(2.5, width, (0, 0, 0), (1, 0, 0), centered=True), "steel")
            self._made[key] = (bone, pad, hinge)
        bone, pad, hinge = self._made[key]
        placed = [inst(bone, loc, label)]
        if kind != "prox":                                   # a proximal phalanx turns on the palm's knuckle pin
            placed.append(inst(hinge, loc, "hinge_pin"))
        if pad is not None:
            placed.append(inst(pad, loc, f"{label}_pad"))
        return placed


def build_hand(hw, wrist_output):
    """Every part of the left hand, by link."""
    links = {name: [] for name in HAND_LINKS}
    links["palm"] += wrist_output
    bones = _Bones()
    _palm(hw, links)
    for finger, (y, lengths) in FINGERS.items():
        width = 14.0 if finger == "little" else 16.0
        z = KNUCKLE_Z
        for bone, length in zip(("prox", "mid", "dist"), lengths):
            loc = frame((SX, y, z), z_dir=(0, 0, 1), x_dir=(0, 1, 0))
            links[f"{finger}_{bone}"] += bones.place(bone, length, width, loc, f"{finger}_{bone}")
            z -= length
    _thumb(links, bones)
    return links


def _palm(hw, links):
    # Frame: a slab from the knuckles to the wrist, notched for the thumb's pivot.
    slab = geo.plate_yz(geo.hull([(-36, 840, 8), (31, 840, 8), (-37, 778, 6), (33, 778, 6)]), SX - 9, SX + 9)
    slab -= geo.box(40, 34, 45, (SX, THUMB_BASE[1] - 7, THUMB_BASE[2] - 11.5))       # deep enough for the thumb swung across the palm
    ear = geo.hull([(SX, KNUCKLE_Z, 8.0), (SX, KNUCKLE_Z + 14, 8.0)])
    for y0, y1 in ((-41.5, -38.5), (-21.5, -18.5), (-1.5, 1.5), (18.5, 21.5), (36.5, 39.5)):
        slab += geo.plate_xz(ear, y0, y1)
    slab -= geo.cyl(2.5, 90, (SX, -45, KNUCKLE_Z), (0, 1, 0))             # the knuckle pin's bore
    slab -= geo.cyl(4.0, 40, (THUMB_BASE[0], THUMB_BASE[1], THUMB_BASE[2] - 20), (0, 0, 1))   # the thumb pivot's
    lug = geo.plate_yz(geo.bones([(0, YZ, 18), (0, YZ - 26, 12)], holes=[(0, YZ, 3)]), SX + 23, SX + 33)
    bridge = geo.box(33, 24, 12, (SX + 16.5, 0, 841))
    back = geo.plate_yz(geo.hull([(-30, 824, 8), (28, 824, 8), (-32, 784, 6), (30, 784, 6)]), SX + 9, SX + 12.5)
    back = bd.fillet(back.edges().group_by(bd.Axis.X)[-1], 2.0)
    pad = geo.plate_yz(geo.hull([(-14, 830, 8), (24, 830, 8), (-14, 796, 8), (26, 796, 8)]), SX - 12, SX - 9)
    links["palm"] += [part(slab + lug + bridge, "palm_frame", "slate"), part(back, "hand_back", "shell"),
                      part(pad, "palm_pad", "rubber"),
                      pin((SX, -42.0, KNUCKLE_Z), (0, 1, 0), 2.5, 82.0, label="knuckle_pin"),
                      pin((THUMB_BASE[0], THUMB_BASE[1], THUMB_BASE[2] - 10), (0, 0, 1), 4.0, 30.0, label="thumb_pivot")]


def _thumb(links, bones):
    base, mcp, ip, d = THUMB_ROOT, THUMB_MCP, THUMB_IP, THUMB_DIR
    # Metacarpal: a ring on the opposition pivot, an arm out to the thumb's line, a fork for the MCP.
    ring = geo.tube(9.0, 4.0, 18.0, (THUMB_BASE[0], THUMB_BASE[1], THUMB_BASE[2] - 9), (0, 0, 1))
    arm = geo.rod(THUMB_BASE, base, 6.5)
    loc = frame(base, z_dir=tuple(-k for k in d), x_dir=(1, 0, 0))
    width = 17.0
    body = geo.box(width - 2, THICK, THUMB_BONES[0] - 9, (0, 0, -(THUMB_BONES[0] - 9) / 2))
    fork = _ears(THUMB_BONES[0], width) - geo.cyl(2.5, width + 2, (0, 0, -THUMB_BONES[0]), (1, 0, 0), centered=True)
    meta = ring + arm + loc * (body + fork)
    meta -= geo.cyl(4.0, 30, (THUMB_BASE[0], THUMB_BASE[1], THUMB_BASE[2] - 15), (0, 0, 1))     # the pivot's bore
    links["thumb_meta"] += [part(meta, "thumb_meta", "slate")]
    links["thumb_prox"] += bones.place("mid", THUMB_BONES[1], width, frame(mcp, tuple(-k for k in d), (1, 0, 0)), "thumb_prox")
    links["thumb_dist"] += bones.place("dist", THUMB_BONES[2], width, frame(ip, tuple(-k for k in d), (1, 0, 0)), "thumb_dist")

"""Trim: headlight, tail light, turn signals, mirrors.

Signals and mirrors are single-geometry parts instanced per side in the
assembly; the standalone entries show the rider-left instance.
"""

from __future__ import annotations

from cadgen import build123d as bd

from lib import lib as L
from lib import spec as S


def build_headlight():
    cx, cy, cz = S.HEADLIGHT_CENTER
    r = S.HEADLIGHT_OD / 2
    shell = L.axis_cylinder((cx - 24.0, cy, cz), (1, 0, 0), r - 2.0,
                            S.HEADLIGHT_DEPTH)
    rim = L.axis_ring((cx + 4.0, cy, cz), (1, 0, 0), r + 3.0, r - 4.0, 10.0)
    lamp = shell.fuse(rim)
    lamp = L.paint(lamp, "headlight_shell", color=S.CHROME)

    flat = L.axis_cylinder((cx + 6.0, cy, cz), (1, 0, 0), r - 6.0, 8.0)
    dome = (
        bd.Sphere(r - 2.0).moved(bd.Location((cx - 8.0, cy, cz)))
        - L.axis_cylinder((cx - 18.0, cy, cz), (1, 0, 0), r + 10.0, 40.0)
        - L.axis_cylinder((cx + 36.0, cy, cz), (1, 0, 0), r + 10.0, 40.0)
    )
    lens = flat.fuse(dome)
    lens = L.paint(lens, "headlight_lens", color=S.LENS_CLEAR)
    return [lamp, lens]


def build_tail_light():
    cx, cy, cz = S.TAILLIGHT_CENTER
    housing = L.axis_cylinder((cx + 14.0, cy, cz), (1, 0, 0),
                              S.TAILLIGHT_OD / 2, S.TAILLIGHT_DEPTH)
    housing = L.paint(housing, "tail_light_housing", color=S.ENGINE_DARK)
    lens = L.axis_cylinder((cx - 2.0, cy, cz), (1, 0, 0),
                           S.TAILLIGHT_OD / 2 - 6.0, 10.0)
    lens = L.paint(lens, "tail_light_lens", color=S.RED_LENS)
    return [housing, lens]


def build_turn_signal(position, side):
    """One amber signal: stalk + chrome housing + lens, pointing outward."""
    x, y, z = position
    out = (0.0, 1.0 if side > 0 else -1.0, 0.0)
    stalk = L.axis_cylinder(
        (x, y + out[1] * 14.0, z), out, 6.0, 30.0,
    )
    housing = L.axis_cylinder(
        (x, y + out[1] * 32.0, z), out, S.SIGNAL_LENS_OD / 2, 20.0,
    )
    body = stalk.fuse(housing)
    body = L.paint(body, "turn_signal_housing", "left" if side > 0 else "right",
                   color=S.CHROME)
    lens = L.axis_cylinder(
        (x, y + out[1] * 43.0, z), out, S.SIGNAL_LENS_OD / 2 - 6.0, 8.0,
    )
    lens = L.paint(lens, "turn_signal_lens", "left" if side > 0 else "right",
                   color=S.AMBER)
    return [body, lens]


def build_mirror(side, base):
    """Round bar-end mirror: raked stalk + head, glass facing back toward the
    rider. ``side`` +1 rider-left, -1 rider-right; ``base`` is the bar-end
    mount point, which the handlebar model owns (``handlebar.MIRROR_MOUNT_*``)."""
    x, y, z = base
    head_center = (x + 28.0, y + side * 57.0, z + 117.0)
    stalk = L.tube(
        [base, (x + 10.0, y + side * 30.0, z + 55.0), head_center],
        S.MIRROR_STALK_OD,
    )
    n = (-0.55, side * 0.28, 0.79)  # face normal, back-up toward the rider
    head = L.axis_cylinder(head_center, n, S.MIRROR_HEAD_RX, S.MIRROR_HEAD_T)
    mirror = stalk.fuse(head)
    # `mirror_shell`, not `mirror`: the assembly labels the two-part GROUP
    # `mirror:<side>`, and a leaf sharing that label shadows it — a `#mirror:left`
    # mate ref would resolve leaf-first and leave the glass behind.
    mirror = L.paint(mirror, "mirror_shell", "left" if side > 0 else "right",
                     color=S.CHROME)
    glass = L.axis_cylinder(
        (head_center[0] - n[0] * (S.MIRROR_HEAD_T / 2 + 1.0),
         head_center[1] - n[1] * (S.MIRROR_HEAD_T / 2 + 1.0),
         head_center[2] - n[2] * (S.MIRROR_HEAD_T / 2 + 1.0)),
        n, S.MIRROR_HEAD_RX - 7.0, 2.0,
    )
    glass = L.paint(glass, "mirror_glass", "left" if side > 0 else "right",
                    color=(0.12, 0.14, 0.18, 1.0))
    return [mirror, glass]

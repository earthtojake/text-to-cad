"""juno expressive sensor head.

Local frame: origin at the neck-pitch joint center, +X face direction, +Z up.
Envelope z +12..+150, |y| <= 69, x -58..+78. Below z=+12 kept clear within
radius 45 (graphite neck guard starts at z=+12 >= +8 allowance).

Construction notes:
- The helmet is a smooth loft of rounded-rectangle sections built in a frame
  centered at HEAD_CTR so a uniform `scale()` (which scales about the origin
  for identity-location parts) yields a concentric "inflated" copy. The visor,
  chin sensor bar, and rear panel are each (inflated copy) & (band tool) -
  helmet, giving thin curved slabs ~2 mm proud that follow the shell surface.
- Ear pods and camera dots are subtracted from the shell before being added as
  separate solids, so all contacts are exact face-to-face with no overlap.
"""

from __future__ import annotations

import sys
from pathlib import Path



import math

from build123d import (
    Axis,
    Box,
    Cone,
    Cylinder,
    GeomType,
    Pos,
    RectangleRounded,
    Rot,
    chamfer,
    fillet,
    loft,
    scale,
)

from .juno_lib import (
    ACCENT_COLOR,
    ALU_COLOR,
    EYE_COLOR,
    SHELL_COLOR,
    STRUCT_COLOR,
    VISOR_COLOR,
    part_compound,
    styled,
)

# Head-frame point all local modeling is centered on (also the scale center
# for the inflated shell copies used to cut the visor/chin/rear slabs).
HEAD_CTR = (7.0, 0.0, 89.0)


def _try_fillet(solid, edges, radius):
    for r in (radius, radius * 0.6, radius * 0.35):
        try:
            return fillet(edges, r)
        except Exception:
            continue
    return solid


def _try_chamfer(solid, edges, length):
    for c in (length, length * 0.5):
        try:
            return chamfer(edges, c)
        except Exception:
            continue
    return solid


def _helmet_loft():
    """Smooth helmet: fuller cheeks low, widest at sensor band, tapered crown.

    Sections are (z, xc, depth_x, width_y, corner_frac) in LOCAL coords
    (head frame minus HEAD_CTR).
    """
    sections = [
        (-69.0, -3.0, 100.0, 98.0, 0.40),  # jaw line (head z=20)
        (-41.0, 0.0, 114.0, 120.0, 0.42),  # cheeks (head z=48)
        (-7.0, 0.0, 120.0, 130.0, 0.44),  # sensor band, widest (head z=82)
        (23.0, -3.0, 110.0, 118.0, 0.45),  # upper visor (head z=112)
        (47.0, -7.0, 88.0, 92.0, 0.46),  # crown taper (head z=136)
        (57.0, -9.0, 62.0, 64.0, 0.47),
        (60.5, -10.0, 34.0, 34.0, 0.48),  # crown top (head z=149.5)
    ]
    profiles = []
    for z, xc, d, w, rf in sections:
        profiles.append(Pos(xc, 0, z) * RectangleRounded(d, w, rf * min(d, w)))
    return loft(profiles)


def build_head():
    """Expressive sensor head; origin at the neck-pitch joint center."""
    helmet = _helmet_loft()

    # Soften jaw line and dome the crown.
    helmet = _try_fillet(helmet, helmet.edges().group_by(Axis.Z)[0], 5.0)
    helmet = _try_fillet(helmet, helmet.edges().group_by(Axis.Z)[-1], 9.0)

    # Concentric inflated copy (~2 mm proud) for surface-following slabs.
    big = scale(helmet, by=1.032)

    # --- aluminum ear pods (dia 36, head z~88, outer face head y=+-67) ---
    pods, buttons = [], []
    for s in (1.0, -1.0):
        rot = Rot(-90, 0, 0) if s > 0 else Rot(90, 0, 0)
        pod = Pos(-7.0, s * 58.5, -1.0) * rot * Cylinder(radius=18.0, height=17.0)
        outer = [
            e
            for e in pod.edges().filter_by(GeomType.CIRCLE)
            if abs(e.arc_center.Y) > 66.0
        ]
        pod = _try_chamfer(pod, outer, 2.2)
        helmet -= pod
        pods.append(pod)
        btn = Pos(-7.0, s * 67.8, -1.0) * rot * Cylinder(radius=7.0, height=1.6)
        buttons.append(btn)

    # --- tiny camera dots below the visor (head z=51, y=+-13) ---
    dots = []
    for s in (1.0, -1.0):
        dot = Pos(53.0, s * 13.0, -38.0) * Rot(0, 90, 0) * Cylinder(
            radius=2.8, height=12.0
        )
        helmet -= dot
        dots.append(dot)

    # --- wraparound gloss visor (head z ~57..117 at front center) ---
    # Single sculpted tool: bottom plane tilted forward-down 6 deg, top plane
    # raked gently rear-down 4 deg, rear wrap edge raked 15 deg (wraps farther
    # back at the temples), corner edges filleted for a sporty
    # rounded-trapezoid side profile.
    bot_half = Pos(60.0, 0, -32.0) * Rot(0, 6, 0) * Pos(0, 0, 150.0) * Box(
        360.0, 300.0, 300.0
    )
    top_half = Pos(60.0, 0, 28.0) * Rot(0, -4, 0) * Pos(0, 0, -150.0) * Box(
        360.0, 300.0, 300.0
    )
    rear_half = Pos(13.0, 0, 0) * Rot(0, -15, 0) * Pos(150.0, 0, 0) * Box(
        300.0, 320.0, 360.0
    )
    visor_tool = bot_half & top_half & rear_half
    corner_edges = [
        e
        for e in visor_tool.edges().filter_by(Axis.Y)
        if abs(e.center().X) < 45.0 and abs(e.center().Z) < 80.0
    ]
    visor_tool = _try_fillet(visor_tool, corner_edges, 12.0)
    visor = (big & visor_tool) - helmet

    # --- graphite chin sensor bar: head z 29..45, |y| <= 26, front ---
    chin_tool = Pos(53.0, 0, -52.0) * Box(60.0, 52.0, 16.0)
    chin_tool = _try_fillet(chin_tool, chin_tool.edges().filter_by(Axis.X), 5.0)
    chin = (big & chin_tool) - helmet

    # --- graphite rear vent louvers: three strips, head z 76..118 ---
    louvers = []
    for zc in (-8.0, 8.0, 24.0):
        tool = Pos(-71.0, 0, zc) * Box(60.0, 220.0, 10.0)
        tool = _try_fillet(tool, tool.edges().filter_by(Axis.Y), 4.0)
        louvers.append((big & tool) - helmet)

    # --- cute pixelated cyan eyes on the visor (Anki Cozmo style) ---
    # Each "pixel" rides the same surface family as the visor: the thin shell
    # between the visor outer copy (`big`, 1.032x) and a slightly larger copy
    # (`big_eye`), clipped to a small +X-facing square column. This makes the
    # tiles follow the curved screen and sit ~1.3 mm proud with exact contact.
    big_eye = scale(helmet, by=1.055)
    EYE_PITCH = 4.4          # tile center-to-center
    EYE_TILE = 3.6          # tile size (gaps read as the dark "screen" grid)
    EYE_Z = 6.0            # local z of the eye block (head z ~95)
    EYE_DY = 12.0           # half-separation between the two eyes
    # 4x4 grid with the four corners dropped -> rounded-square eye.
    eye_mask = [
        (c, r)
        for c in range(4)
        for r in range(4)
        if (c, r) not in {(0, 0), (0, 3), (3, 0), (3, 3)}
    ]
    eye_tiles = []
    for ysign, tag in ((1.0, "l"), (-1.0, "r")):
        yc = ysign * EYE_DY
        for c, r in eye_mask:
            ty = yc + (c - 1.5) * EYE_PITCH
            tz = EYE_Z + (r - 1.5) * EYE_PITCH
            tool = Pos(70.0, ty, tz) * Box(120.0, EYE_TILE, EYE_TILE)
            tool = _try_fillet(tool, tool.edges().filter_by(Axis.X), 0.9)
            tile = (big_eye & tool) - big
            eye_tiles.append((tile, f"head_eye_{tag}_{c}{r}"))

    # --- graphite neck guard: frustum head z 12..20 under the jaw ---
    guard = Pos(-3.0, 0, -73.0) * Cone(
        bottom_radius=33.0, top_radius=42.0, height=8.0
    )
    guard = _try_chamfer(
        guard,
        [
            e
            for e in guard.edges().filter_by(GeomType.CIRCLE)
            if e.arc_center.Z < -76.0
        ],
        1.2,
    )

    at = Pos(*HEAD_CTR)
    children = [
        styled(at * helmet, "head_shell", SHELL_COLOR),
        styled(at * visor, "head_visor", VISOR_COLOR),
        styled(at * chin, "head_chin_sensor", STRUCT_COLOR),
        styled(at * guard, "head_neck_guard", STRUCT_COLOR),
        styled(at * pods[0], "head_ear_pod_l", ALU_COLOR),
        styled(at * pods[1], "head_ear_pod_r", ALU_COLOR),
        styled(at * buttons[0], "head_ear_button_l", ACCENT_COLOR),
        styled(at * buttons[1], "head_ear_button_r", ACCENT_COLOR),
        styled(at * dots[0], "head_cam_dot_l", VISOR_COLOR),
        styled(at * dots[1], "head_cam_dot_r", VISOR_COLOR),
    ]
    for i, louver in enumerate(louvers):
        children.append(styled(at * louver, f"head_vent_louver_{i}", ACCENT_COLOR))
    for tile, name in eye_tiles:
        children.append(styled(at * tile, name, EYE_COLOR))
    return part_compound("head", children)


def gen_step():
    return build_head()

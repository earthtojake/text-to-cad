#!/usr/bin/env python3
"""
Shared layout for the tom v2 servo-to-servo link brackets.

Link frame convention (millimeters, Z-up):
- +Z is up. The bottom servo's output shaft is coaxial with the link's
  vertical centerline (X = Y = 0) and points down (-Z); its case-bottom
  face is up at Z = 0 and its body runs along +X (rear end at
  X = -10.11, front end at X = +35.11). It uses the rear-horn-less
  variant (STEP/imports/sts3215_no_rear_horn.step) so bracket feet seat flat
  on its case-bottom face; only the case's small rear journal/screw stub
  still protrudes there.
- The top servo forms a horizontal pitch joint: it stands on end with
  its horn axis along X at (Y = 0, Z = TOP_PIVOT_Z_MM) and the
  horn-to-horn span centered on the link centerline (output horn face at
  X = +18.3, rear horn face at X = -18.3). Two mounting variations are
  supported:
  - horn mount: the bracket horn plates bolt to both horn faces
    (4x M3-pattern screws per side) and the servo body, which belongs to
    the next link, is flipped to stand above the pivot so it rotates
    freely.
  - case mount: the brackets bolt to the servo case with 2x M2 screws
    per side (flush side into the case-bottom face holes at
    Y = +/-10.25, Z = 102.25; offset side into the case-top face holes
    at Y = +/-10.25, Z = 106.0), the body hangs down into the link, and
    the next link's yoke grabs the free horns.

All brackets are authored directly in this link frame so the bracket
STEP files and the verification assemblies compose with identity
transforms for the brackets.

Servo source geometry (STS3250 local frame, from
STEP/imports/sts3250.step):
- body bounds x [-35.61, 9.61], y [-28.2, 9.2], z [-12.36, +12.36]
- output shaft axis at (x, z) = (-25.5, 0), pointing +y; output horn
  face at y = +9.2, rear horn face at y = -27.4, each with four
  diameter-3.2 screw holes on a 7 mm circle plus a center hole; the rear
  journal/screw stub protrudes to y = -28.2
- case-bottom plane y = -25.6 with four M2 holes (r 1.1) at
  x in {-17.2, +7.25}, z = +/-10.25, facing -y
- case-top plane y = +6.4 with four M2 holes (r 1.1) at
  x in {-17.2, +3.5}, z = +/-10.25, facing +y, around the output horn
  boss (radius 11.2)
"""

from __future__ import annotations


from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
# No XDG_CACHE_HOME override: one cache root for the project, the default. See src/base_clamp.py.

import build123d

from lib.materials import ALUMINUM_5052_COLOR


# Plain bare-aluminum tint for the v2 brackets. Without an explicit source
# color the viewer falls back to its dark theme paint, which reads as a
# deliberately colored part.
BRACKET_COLOR = ALUMINUM_5052_COLOR

# STEP copy: these resolve inside STEP/imports, not STEP/imports, so this tree is
# self-contained and a change to STEP/'s vendor import cannot silently move v2 geometry.
# The servo import is now the OFFICIAL Waveshare ST3215 model (imports/sts3215.step).
# The 2mm copies live one level deeper than the originals, so this file's SRC_DIR (which means
# the REPO ROOT here, not STEP -- see AGENTS.md) lands on STEP instead. Vendor STEP is
# shared and unaffected by gauge, so point at the original tree explicitly.
_VENDOR_DIR = Path(__file__).resolve().parents[2] / "STEP" / "imported"
SERVO_STEP = _VENDOR_DIR / "sts3215.step"

from lib import sheet_rule_scs as scs  # noqa: E402

# The two servo models this module composes (see _load_servo_shape). Importing binds, never builds.


# Sheet stock for the v2 aluminum brackets (SendCutSend 0.063 in 5052-H32).
SENDCUTSEND_ALU_063_THICKNESS_MM = scs.THICKNESS_MM   # 2mm tree: ALU-080, from sheet_rule_scs
SHEET_THICKNESS_MM = SENDCUTSEND_ALU_063_THICKNESS_MM


# Requested M2 close clearance is Ø2.2. At the -0.127 mm cutting limit
# this retains 0.073 mm diametral clearance, before positional/forming error.
# See SERVO_FIT_UPDATE.md for fixture and post-form hole-finishing requirements.


# Top pitch joint: the horn axis runs along X at this height. For the
# case-mounted link, center the visible case span on the link centerline so
# the top servo body reads centered over the bottom horn axis; the pitch axis
# still intersects that vertical axis at X = Y = 0.
TOP_PIVOT_Z_MM = 180.0


def make_box(
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_box(
        x_max - x_min,
        y_max - y_min,
        z_max - z_min,
        plane=build123d.Plane(origin=build123d.Vector(x_min, y_min, z_min)),
    )


def make_z_cylinder(
    *,
    x: float,
    y: float,
    radius: float,
    z_min: float,
    z_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        z_max - z_min,
        plane=build123d.Plane(origin=build123d.Vector(x, y, z_min), z_dir=(0.0, 0.0, 1.0)),
    )


def make_y_cylinder(
    *,
    x: float,
    z: float,
    radius: float,
    y_min: float,
    y_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        y_max - y_min,
        plane=build123d.Plane(origin=build123d.Vector(x, y_min, z), z_dir=(0.0, 1.0, 0.0)),
    )

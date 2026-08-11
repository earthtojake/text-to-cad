#!/usr/bin/env python3
"""
Generate an STS3250 variant with the rear (bottom) servo horn removed.

The stock import at STEP/imports/sts3250.step contains five solids; the
fifth is the detachable rear-journal horn disk (diameter 19.2 mm, 3.1 mm
thick, on the case-bottom side). The tom v2 link seats bracket feet
directly on the bottom servo's case-bottom face, so this variant drops
that horn solid. The case's rear journal/screw stub (about 6 mm across,
protruding 2.6 mm past the case-bottom plane) belongs to the case solid
and remains.

The remaining solids are tinted black aluminum to match the uniform
source color of the stock import, which would otherwise be lost when
re-exporting through the Python generator.

Usage:
  python v2/imports/sts3250_no_rear_horn.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[2]
TOM_DIR = V2_DIR
_CACHE_HOME = V2_DIR / ".cache"
_CACHE_HOME.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_HOME))

import build123d

if str(TOM_DIR) not in sys.path:
    sys.path.insert(0, str(TOM_DIR))

from robot_common.materials import BLACK_ALUMINUM_COLOR
from robot_common.step_import import import_as_shape


PART_NAME = Path(__file__).stem

SERVO_STEP = V2_DIR / "parts" / "imports" / "sts3250.step"

REAR_HORN_DIAMETER_MM = 19.2
REAR_HORN_THICKNESS_MM = 3.1
REAR_HORN_CENTER_Y_MM = -25.85
SOLID_MATCH_TOLERANCE_MM = 0.2
EXPECTED_SOLID_COUNT = 5


def _is_rear_horn(solid: build123d.Solid) -> bool:
    bb = solid.bounding_box()
    return (
        abs(bb.size.X - REAR_HORN_DIAMETER_MM) <= SOLID_MATCH_TOLERANCE_MM
        and abs(bb.size.Z - REAR_HORN_DIAMETER_MM) <= SOLID_MATCH_TOLERANCE_MM
        and abs(bb.size.Y - REAR_HORN_THICKNESS_MM) <= SOLID_MATCH_TOLERANCE_MM
        and abs(bb.center().Y - REAR_HORN_CENTER_Y_MM) <= SOLID_MATCH_TOLERANCE_MM
    )


def build_step() -> build123d.Compound:
    if not SERVO_STEP.exists():
        raise FileNotFoundError(f"Missing STS3250 servo STEP: {SERVO_STEP}")

    servo = import_as_shape(SERVO_STEP)
    solids = servo.solids()
    if len(solids) != EXPECTED_SOLID_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_SOLID_COUNT} solids in the STS3250 import, found {len(solids)}"
        )

    rear_horns = [solid for solid in solids if _is_rear_horn(solid)]
    if len(rear_horns) != 1:
        raise RuntimeError(
            f"Expected exactly one rear horn solid in the STS3250 import, found {len(rear_horns)}"
        )

    kept = [solid for solid in solids if not solid.is_same(rear_horns[0])]
    for solid in kept:
        solid.color = BLACK_ALUMINUM_COLOR

    variant = build123d.Compound(children=kept, label=PART_NAME)

    bb = variant.bounding_box()
    source_bb = servo.bounding_box()
    for measured, expected, axis in (
        (bb.size.X, source_bb.size.X, "X"),
        (bb.size.Y, source_bb.size.Y, "Y"),
        (bb.size.Z, source_bb.size.Z, "Z"),
    ):
        if abs(measured - expected) > 0.01:
            raise RuntimeError(
                f"Variant {axis} extent {measured:.4f} mm deviates from the stock servo {expected:.4f} mm; "
                "removing the rear horn must not change the body envelope"
            )

    horn_bb = rear_horns[0].bounding_box()
    print(
        "Removed rear horn solid: "
        f"bb min=({horn_bb.min.X:.2f}, {horn_bb.min.Y:.2f}, {horn_bb.min.Z:.2f}) mm, "
        f"max=({horn_bb.max.X:.2f}, {horn_bb.max.Y:.2f}, {horn_bb.max.Z:.2f}) mm"
    )
    print(f"Variant solids: {len(kept)}; envelope X={bb.size.X:.3f} Y={bb.size.Y:.3f} Z={bb.size.Z:.3f} mm")
    return variant


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()

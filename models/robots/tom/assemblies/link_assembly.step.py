#!/usr/bin/env python3
"""
Verification assembly for the tom v2 link bracket pair.

Both servos sit exactly as in the case-mount variation. One two-bend wrap
plate connects them along the +Y side; a mirrored instance of the same
plate connects the -Y side.

Usage:
  python v2/assemblies/link_assembly.py
"""

from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
ASSEMBLIES_DIR = Path(__file__).resolve().parent
PARTS_DIR = V2_DIR / "parts"
for path in (V2_DIR, PARTS_DIR, ASSEMBLIES_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import link_common as lc
from robot_common.step_entry import load_step_entry

link_bracket = load_step_entry("link_bracket")
pitch_link_sts3250 = load_step_entry("pitch_link_sts3250")
servo_horn_yoke = load_step_entry("servo_horn_yoke")
from robot_common.link_assembly import link_assembly_from_instances


YOKE_HORN_SPAN_CENTER_LOCAL_Y_MM = -9.1
IDENTITY_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)

MIRROR_Y_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, -1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


YOKE_ON_SERVO_HORNS_TRANSFORM = tuple(
    servo_horn_yoke.STANDALONE_YOKE_ON_SERVO_HORNS_TRANSFORM
)


def _matrix(transform: list[float] | tuple[float, ...]) -> list[list[float]]:
    return [list(transform[index : index + 4]) for index in range(0, 16, 4)]


def _flatten(matrix: list[list[float]]) -> list[float]:
    return [value for row in matrix for value in row]


def _matmul(
    left: list[float] | tuple[float, ...],
    right: list[float] | tuple[float, ...],
) -> list[float]:
    left_matrix = _matrix(left)
    right_matrix = _matrix(right)
    return _flatten(
        [
            [
                sum(left_matrix[row][inner] * right_matrix[inner][col] for inner in range(4))
                for col in range(4)
            ]
            for row in range(4)
        ]
    )


def _invert_rigid_transform(transform: list[float] | tuple[float, ...]) -> list[float]:
    matrix = _matrix(transform)
    rotation = [row[:3] for row in matrix[:3]]
    translation = [matrix[row][3] for row in range(3)]
    inverse_rotation = [[rotation[col][row] for col in range(3)] for row in range(3)]
    inverse_translation = [
        -sum(inverse_rotation[row][col] * translation[col] for col in range(3))
        for row in range(3)
    ]
    return _flatten(
        [
            [*inverse_rotation[0], inverse_translation[0]],
            [*inverse_rotation[1], inverse_translation[1]],
            [*inverse_rotation[2], inverse_translation[2]],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


YOKE_WEB_ON_BOTTOM_SERVO_OUTPUT_HORN_TRANSFORM = _matmul(
    lc.BOTTOM_SERVO_TRANSFORM,
    _invert_rigid_transform(pitch_link_sts3250.STS3250_TRANSFORM),
)

THIRD_SERVO_HORNS_IN_YOKE_TRANSFORM = _matmul(
    YOKE_WEB_ON_BOTTOM_SERVO_OUTPUT_HORN_TRANSFORM,
    _invert_rigid_transform(YOKE_ON_SERVO_HORNS_TRANSFORM),
)

TOP_SERVO_FACE_TO_FLANGE_TRANSFORM = link_bracket.top_servo_case_transform(
    case_span_centering_offset_mm=link_bracket.TOP_SERVO_MATED_CASE_SPAN_CENTERING_OFFSET_MM,
)


def _translation_transform(x: float, y: float, z: float) -> list[float]:
    return [
        1.0, 0.0, 0.0, x,
        0.0, 1.0, 0.0, y,
        0.0, 0.0, 1.0, z,
        0.0, 0.0, 0.0, 1.0,
    ]


def _standoff_children() -> list[dict[str, object]]:
    return [
        {
            "path": "../parts/link_standoff_m3_35.step",
            "name": f"link_standoff_{label}",
            "transform": _translation_transform(x, 0.0, z),
            "use_source_colors": True,
        }
        for label, x, z in link_bracket.STANDOFF_CENTER_XZ_MM
    ]


def assembly_instances() -> dict[str, object]:
    return {
        "instances": [
            {
                "path": "../parts/imports/sts3250.step",
                "name": "sts3250_top",
                "transform": list(TOP_SERVO_FACE_TO_FLANGE_TRANSFORM),
            },
            {
                "path": "../parts/imports/sts3250.step",
                "name": "sts3250_bottom",
                "transform": list(lc.BOTTOM_SERVO_TRANSFORM),
                "use_source_colors": True,
            },
            {
                "path": "../parts/link_bracket_right.step",
                "name": "link_bracket_right",
                "transform": list(IDENTITY_TRANSFORM),
            },
            {
                "path": "../parts/link_bracket_left.step",
                "name": "link_bracket_left",
                "transform": list(IDENTITY_TRANSFORM),
            },
            *_standoff_children(),
            {
                "path": "../parts/servo_horn_yoke.step",
                "name": "servo_horn_yoke",
                "transform": YOKE_WEB_ON_BOTTOM_SERVO_OUTPUT_HORN_TRANSFORM,
            },
            {
                "path": "../parts/imports/sts3215.step",
                "name": "sts3215_yoke_servo",
                "transform": THIRD_SERVO_HORNS_IN_YOKE_TRANSFORM,
                "use_source_colors": True,
            },
        ],
    }


def build():
    return link_assembly_from_instances(
        "link_assembly",
        assembly_instances()["instances"],
        base_dir=Path(__file__).resolve().parent,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}

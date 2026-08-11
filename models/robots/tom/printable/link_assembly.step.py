#!/usr/bin/env python3
"""Printable-side tom v2 link assembly with straight tongue shell halves added.

This is a working copy of the regular link assembly in the printable folder.
It keeps the original servo, bracket, standoff, and yoke layout, then adds the
current straight four-tongue plastic shell halves on both link brackets. The
right shell has printed male dovetail rails; the left shell has matching
female dovetail channels. Future printable connector iterations can target this
assembly without keeping assemblies/link_assembly.py in sync.
"""

from __future__ import annotations

import sys
from pathlib import Path

PRINTABLE_DIR = Path(__file__).resolve().parent
V2_DIR = PRINTABLE_DIR.parent
ASSEMBLIES_DIR = V2_DIR / "assemblies"
PARTS_DIR = V2_DIR / "parts"
for path in (V2_DIR, ASSEMBLIES_DIR, PARTS_DIR, PRINTABLE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import link_common as lc
from robot_common.step_entry import load_step_entry

link_bracket = load_step_entry("link_bracket")
connector = load_step_entry("link_bracket_slot_pair_straight_sample")
pitch_link_sts3250 = load_step_entry("pitch_link_sts3250")
servo_horn_yoke = load_step_entry("servo_horn_yoke")


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

LOWER_SLOT_PAIR_CENTER_X_MM = 0.5 * (
    link_bracket.LOWER_SLOT_CENTER_X_MM[0] + link_bracket.LOWER_SLOT_CENTER_X_MM[1]
)

# Map shell local coordinates into the right bracket slot frame:
# connector X (section offset and tongue length) -> bracket Z
# connector Y (slot-pair spacing and upper-section offset) -> bracket -X
# connector Z (insertion depth) -> bracket -Y, seated from the right bracket outside face
SHELL_ON_RIGHT_BRACKET_TRANSFORM = [
    0.0, -1.0, 0.0, LOWER_SLOT_PAIR_CENTER_X_MM,
    0.0, 0.0, -1.0, link_bracket.LEG_OUTER_Y_MM + connector.BASE_THICKNESS_MM,
    1.0, 0.0, 0.0, link_bracket.LOWER_SLOT_CENTER_Z_MM,
    0.0, 0.0, 0.0, 1.0,
]

# Same shell half mirrored to the other bracket. Local Z still runs from the
# outside plastic face through the bracket slots and on to the Y=0 center plane.
SHELL_ON_LEFT_BRACKET_TRANSFORM = [
    0.0, -1.0, 0.0, LOWER_SLOT_PAIR_CENTER_X_MM,
    0.0, 0.0, 1.0, -(link_bracket.LEG_OUTER_Y_MM + connector.BASE_THICKNESS_MM),
    1.0, 0.0, 0.0, link_bracket.LOWER_SLOT_CENTER_Z_MM,
    0.0, 0.0, 0.0, 1.0,
]


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


def _mate(
    source_label: str,
    *,
    fixed: str,
    moving: str,
    relation: str = "rigid",
) -> dict[str, object]:
    fixed_part, fixed_frame = fixed.split(":", 1)
    moving_part, moving_frame = moving.split(":", 1)
    return {
        "sourceLabel": source_label,
        "type": relation,
        "relation": relation,
        "fixed": fixed,
        "moving": moving,
        "parameters": {},
        "fixedEndpoint": {
            "part": fixed_part,
            "frame": fixed_frame,
        },
        "movingEndpoint": {
            "part": moving_part,
            "frame": moving_frame,
        },
    }


def _standoff_mates() -> list[dict[str, object]]:
    mates: list[dict[str, object]] = []
    for label, _x, _z in link_bracket.STANDOFF_CENTER_XZ_MM:
        mates.append(
            _mate(
                f"{label}_standoff_to_right_bracket",
                fixed=f"link_bracket_right:{label}_standoff_hole",
                moving=f"link_standoff_{label}:positive_y_thread",
            )
        )
        mates.append(
            _mate(
                f"{label}_standoff_to_left_bracket",
                fixed=f"link_bracket_left:{label}_standoff_hole",
                moving=f"link_standoff_{label}:negative_y_thread",
            )
        )
    return mates


def _children() -> list[dict[str, object]]:
    return [
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
        {
            "path": "link_bracket_slot_pair_straight_sample.step",
            "name": "straight_slot_shell_right",
            "transform": SHELL_ON_RIGHT_BRACKET_TRANSFORM,
            "use_source_colors": True,
        },
        {
            "path": "link_bracket_slot_pair_straight_socket_sample.step",
            "name": "straight_slot_shell_left",
            "transform": SHELL_ON_LEFT_BRACKET_TRANSFORM,
            "use_source_colors": True,
        },
    ]


def _assembly_mates() -> list[dict[str, object]]:
    return [
        _mate(
            "bottom_servo_to_right_bracket",
            fixed="sts3250_bottom:upstream_case",
            moving="link_bracket_right:bottom_servo_mount",
        ),
        _mate(
            "bottom_servo_to_left_bracket",
            fixed="sts3250_bottom:upstream_case",
            moving="link_bracket_left:bottom_servo_mount",
        ),
        _mate(
            "right_bracket_to_top_servo",
            fixed="link_bracket_right:top_servo_mount",
            moving="sts3250_top:case_mount",
        ),
        _mate(
            "left_bracket_to_top_servo",
            fixed="link_bracket_left:top_servo_mount",
            moving="sts3250_top:case_mount",
        ),
        _mate(
            "bottom_servo_output_horn_to_yoke_web",
            fixed="sts3250_bottom:horn_axis",
            moving="servo_horn_yoke:web_horn_axis",
        ),
        _mate(
            "third_servo_horns_to_yoke",
            fixed="servo_horn_yoke:horn_axis",
            moving="sts3215_yoke_servo:horn_axis",
        ),
        *_standoff_mates(),
    ]


def gen_step() -> dict[str, object]:
    children = _children()
    print(
        "Printable link assembly with straight shell halves "
        f"children={len(children)}; connector lower slot center x={LOWER_SLOT_PAIR_CENTER_X_MM:.3f} mm, "
        f"lower slot center z={link_bracket.LOWER_SLOT_CENTER_Z_MM:.3f} mm, "
        f"tongue depth={connector.TONGUE_INSERTION_DEPTH_MM:.3f} mm, "
        f"base sheet={connector.BASE_LENGTH_MM:.3f} x {connector.BASE_WIDTH_MM:.3f} mm, "
        f"shell half depth={connector.SHELL_HALF_DEPTH_MM:.3f} mm, "
        "printed dovetail slide seam"
    )
    from robot_common.link_assembly import compound_from_instances

    return {
        "shape": compound_from_instances(
            "link_assembly",
            children,
            base_dir=Path(__file__).resolve().parent,
            assembly_mates=_assembly_mates(),
        ),
    }


if __name__ == "__main__":
    gen_step()

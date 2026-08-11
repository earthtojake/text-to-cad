from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
PARTS_DIR = V2_DIR / "parts"
for path in (V2_DIR, PARTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robot_common.step_entry import load_step_entry

servo_horn_yoke = load_step_entry("servo_horn_yoke")
from robot_common.link_assembly import link_assembly_from_instances


YOKE_PLATE_FACE_X_MM = (
    servo_horn_yoke.SERVO_HORN_AXIS_X_MM
    - servo_horn_yoke.YOKE_HORN_AXIS_TO_WEB_OUTER_LENGTH_MM
)
YOKE_HORN_AXIS_Y_MM = -9.1
YOKE_HORN_AXIS_Z_MM = 0.0
# The horn's outer contact face seats directly on the outside yoke plate face.
YOKE_HORN_MATING_FACE_X_MM = YOKE_PLATE_FACE_X_MM
# Use the output horn face against the yoke plate so the servo's case-bottom
# cable face points toward the next roll-link bracket instead of away from it.
STS3250_OUTPUT_HORN_AXIS_LOCAL_X_MM = -25.5
STS3250_OUTPUT_HORN_FACE_LOCAL_Y_MM = 9.2
MATE_TOLERANCE_MM = 1e-6

STS3250_DESIGN_TRANSFORM = [
    0.0,
    1.0,
    0.0,
    (
        YOKE_HORN_MATING_FACE_X_MM
        - STS3250_OUTPUT_HORN_FACE_LOCAL_Y_MM
    ),
    -1.0,
    0.0,
    0.0,
    YOKE_HORN_AXIS_Y_MM + STS3250_OUTPUT_HORN_AXIS_LOCAL_X_MM,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]
STS3250_TRANSFORM = list(
    servo_horn_yoke.multiply_transforms(
        servo_horn_yoke.DESIGN_TO_STANDALONE_TRANSFORM,
        STS3250_DESIGN_TRANSFORM,
    )
)


def _validate_sts3250_transform() -> None:
    design_transform = servo_horn_yoke.multiply_transforms(
        servo_horn_yoke.STANDALONE_TO_DESIGN_TRANSFORM,
        STS3250_TRANSFORM,
    )
    horn_face_x = (
        design_transform[1] * STS3250_OUTPUT_HORN_FACE_LOCAL_Y_MM
        + design_transform[3]
    )
    if abs(horn_face_x - YOKE_HORN_MATING_FACE_X_MM) > MATE_TOLERANCE_MM:
        raise RuntimeError(
            "STS3250 output horn face is not seated on the yoke horn mating face: "
            f"{horn_face_x:.6f} != {YOKE_HORN_MATING_FACE_X_MM:.6f}"
        )
    horn_axis_y = (
        design_transform[4] * STS3250_OUTPUT_HORN_AXIS_LOCAL_X_MM
        + design_transform[7]
    )
    if abs(horn_axis_y - YOKE_HORN_AXIS_Y_MM) > MATE_TOLERANCE_MM:
        raise RuntimeError(
            "STS3250 output horn axis is not centered on the yoke horn face: "
            f"{horn_axis_y:.6f} != {YOKE_HORN_AXIS_Y_MM:.6f}"
        )
    horn_axis_z = design_transform[11]
    if abs(horn_axis_z - YOKE_HORN_AXIS_Z_MM) > MATE_TOLERANCE_MM:
        raise RuntimeError(
            "STS3250 output horn axis Z is not centered on the yoke horn face: "
            f"{horn_axis_z:.6f} != {YOKE_HORN_AXIS_Z_MM:.6f}"
        )


def assembly_instances() -> dict[str, object]:
    _validate_sts3250_transform()
    return {
        "instances": [
            {
                "path": "../parts/servo_horn_yoke.step",
                "name": "servo_horn_yoke",
                "transform": [
                    1.0, 0.0, 0.0, 0.0,
                    0.0, 1.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0,
                    0.0, 0.0, 0.0, 1.0,
                ],
            },
            {
                "path": "../parts/imports/sts3250.step",
                "name": "sts3250",
                "transform": STS3250_TRANSFORM,
            },
        ],
    }


def build():
    return link_assembly_from_instances(
        "pitch_link_sts3250",
        assembly_instances()["instances"],
        base_dir=Path(__file__).resolve().parent,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}

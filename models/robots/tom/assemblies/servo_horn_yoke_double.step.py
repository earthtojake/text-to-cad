from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
PARTS_DIR = V2_DIR / "parts"
for path in (V2_DIR, PARTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import link_common as lc
from robot_common.link_assembly import link_assembly_from_instances


SIDE_BY_SIDE_CLEARANCE_MM = 2.0
SERVO_CENTER_SPACING_Y_MM = (2.0 * abs(lc.SERVO_REAR_EXTREME_LOCAL_Y_MM)) + SIDE_BY_SIDE_CLEARANCE_MM
SERVO_CENTER_OFFSET_Y_MM = 0.5 * SERVO_CENTER_SPACING_Y_MM

IDENTITY_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def _translate_y(y_mm: float) -> list[float]:
    transform = list(IDENTITY_TRANSFORM)
    transform[7] = y_mm
    return transform


def _flip_about_x_then_translate_y(y_mm: float) -> list[float]:
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, -1.0, 0.0, y_mm,
        0.0, 0.0, -1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def _servo_instance(label: str, transform: list[float]) -> dict[str, object]:
    return {
        "path": "../parts/imports/sts3250.step",
        "name": f"sts3250_{label}",
        "transform": transform,
        "use_source_colors": True,
    }


def assembly_instances() -> dict[str, object]:
    instances = [
        _servo_instance("rear", _flip_about_x_then_translate_y(-SERVO_CENTER_OFFSET_Y_MM)),
        _servo_instance("front", _translate_y(SERVO_CENTER_OFFSET_Y_MM)),
        {
            "path": "../parts/servo_horn_yoke_double_horn.step",
            "name": "servo_horn_yoke_double_horn",
            "transform": IDENTITY_TRANSFORM,
        },
        {
            "path": "../parts/servo_end_mount_double.step",
            "name": "servo_end_mount_double",
            "transform": IDENTITY_TRANSFORM,
        },
    ]
    return {
        "instances": instances,
    }


def build():
    return link_assembly_from_instances(
        "servo_horn_yoke_double",
        assembly_instances()["instances"],
        base_dir=Path(__file__).resolve().parent,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}

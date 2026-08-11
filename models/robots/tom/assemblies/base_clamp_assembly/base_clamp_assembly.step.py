from __future__ import annotations

import sys
from pathlib import Path

ASSEMBLY_DIR = Path(__file__).resolve().parent
V2_DIR = ASSEMBLY_DIR.parents[1]
for _path in (ASSEMBLY_DIR, V2_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from robot_common.step_entry import load_step_entry

base_clamp = load_step_entry("base_clamp")
from robot_common.link_assembly import link_assembly_from_instances


def multiply_transforms(
    left: list[float] | tuple[float, ...],
    right: list[float] | tuple[float, ...],
) -> list[float]:
    return [
        sum(float(left[row * 4 + inner]) * float(right[inner * 4 + col]) for inner in range(4))
        for row in range(4)
        for col in range(4)
    ]


BASE_CLAMP_LAYOUT = base_clamp._build_bracket_layout()
STS3250_BASE_PLATE_FACE_LOCAL_Y_MM = -27.4
STS3250_UNDERSIDE_M2_MOUNT_FACE_LOCAL_Y_MM = -25.6
STS3250_BASE_PLATE_CLEARANCE_MM = base_clamp.SERVO_STANDOFF_HEIGHT_MM - (
    STS3250_UNDERSIDE_M2_MOUNT_FACE_LOCAL_Y_MM - STS3250_BASE_PLATE_FACE_LOCAL_Y_MM
)
STS3250_END_FOR_END_PIVOT_LOCAL_X_MM = base_clamp.BASE_SERVO_END_FOR_END_PIVOT_LOCAL_X_MM
STS3250_END_FOR_END_PIVOT_LOCAL_Z_MM = base_clamp.BASE_SERVO_END_FOR_END_PIVOT_LOCAL_Z_MM
STS3250_END_FOR_END_ROTATION_TRANSFORM = [
    -1.0,
    0.0,
    0.0,
    (2.0 * STS3250_END_FOR_END_PIVOT_LOCAL_X_MM)
    + base_clamp.SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, -1.0, 2.0 * STS3250_END_FOR_END_PIVOT_LOCAL_Z_MM,
    0.0, 0.0, 0.0, 1.0,
]
STS3250_BASE_PLATE_TO_CLAMP_FACE_TRANSFORM = [
    1.0, 0.0, 0.0, 0.0,
    0.0,
    1.0,
    0.0,
    base_clamp.SADDLE_BASE_FACE_Y_MM
    + STS3250_BASE_PLATE_CLEARANCE_MM
    - STS3250_BASE_PLATE_FACE_LOCAL_Y_MM,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]
STS3250_TO_BASE_CLAMP_TRANSFORM = multiply_transforms(
    STS3250_BASE_PLATE_TO_CLAMP_FACE_TRANSFORM,
    STS3250_END_FOR_END_ROTATION_TRANSFORM,
)
BASE_CLAMP_F12_TO_FLOOR_TRANSFORM = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 0.0, -1.0, 0.0,
    0.0, 1.0, 0.0, -BASE_CLAMP_LAYOUT.overall_y_min,
    0.0, 0.0, 0.0, 1.0,
]
STS3250_FLOOR_TRANSFORM = multiply_transforms(
    BASE_CLAMP_F12_TO_FLOOR_TRANSFORM,
    STS3250_TO_BASE_CLAMP_TRANSFORM,
)
BASE_CLAMP_TOP_FACE_WORLD_Z_MM = base_clamp.SADDLE_BASE_FACE_Y_MM - BASE_CLAMP_LAYOUT.overall_y_min
M2_STANDOFF_FLOOR_TRANSFORMS = tuple(
    [
        1.0, 0.0, 0.0, x,
        0.0, 1.0, 0.0, -z,
        0.0, 0.0, 1.0, BASE_CLAMP_TOP_FACE_WORLD_Z_MM,
        0.0, 0.0, 0.0, 1.0,
    ]
    for x, z, _radius in base_clamp.BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
)
M2_5_BUS_STANDOFF_FLOOR_TRANSFORMS = tuple(
    [
        1.0, 0.0, 0.0, x,
        0.0, 1.0, 0.0, -z,
        0.0, 0.0, 1.0, BASE_CLAMP_TOP_FACE_WORLD_Z_MM,
        0.0, 0.0, 0.0, 1.0,
    ]
    for x, z, _radius in base_clamp.SERVO_BUS_TOP_MOUNT_HOLES_MM
)

WAVESHARE_BUS_PCB_BOTTOM_LOCAL_Z_MM = -1.599999
WAVESHARE_BUS_LOWEST_LOCAL_Z_MM = -11.499994
WAVESHARE_BUS_UNDERSIDE_CLEARANCE_MM = base_clamp.SERVO_BUS_STANDOFF_HEIGHT_MM - (
    WAVESHARE_BUS_PCB_BOTTOM_LOCAL_Z_MM - WAVESHARE_BUS_LOWEST_LOCAL_Z_MM
)
WAVESHARE_BUS_MOUNT_CENTER_LOCAL_X_MM = base_clamp.SERVO_BUS_MOUNT_LOCAL_X_CENTER_MM
WAVESHARE_BUS_MOUNT_CENTER_LOCAL_Y_MM = base_clamp.SERVO_BUS_MOUNT_LOCAL_Y_CENTER_MM
WAVESHARE_BUS_UNFLIPPED_WORLD_X_MM = base_clamp.SERVO_BUS_TOP_TO_BASE_CLAMP_X_OFFSET_MM
WAVESHARE_BUS_UNFLIPPED_WORLD_Y_MM = -base_clamp.SERVO_BUS_TOP_TO_BASE_CLAMP_Z_OFFSET_MM

WAVESHARE_BUS_FLOOR_TRANSFORM = [
    0.0,
    -1.0,
    0.0,
    WAVESHARE_BUS_UNFLIPPED_WORLD_X_MM
    + (2.0 * WAVESHARE_BUS_MOUNT_CENTER_LOCAL_Y_MM),
    1.0,
    0.0,
    0.0,
    WAVESHARE_BUS_UNFLIPPED_WORLD_Y_MM
    - (2.0 * WAVESHARE_BUS_MOUNT_CENTER_LOCAL_X_MM),
    0.0,
    0.0,
    1.0,
    BASE_CLAMP_TOP_FACE_WORLD_Z_MM
    + base_clamp.SERVO_BUS_STANDOFF_HEIGHT_MM
    - WAVESHARE_BUS_PCB_BOTTOM_LOCAL_Z_MM,
    0.0,
    0.0,
    0.0,
    1.0,
]


def assembly_instances() -> dict[str, object]:
    # Flat instance list for the base-clamp sub-assembly. build() expresses the
    # part-to-part relationships as native build123d joints (link_assembly_from_instances),
    # so the assembly mates derive from those joints rather than a hand-authored dict.
    return {
        "instances": [
            {
                "path": "sts3250.step",
                "name": "sts3250",
                "transform": STS3250_FLOOR_TRANSFORM,
            },
            *(
                {
                    "path": "m2_spacer_5mm.step",
                    "name": f"m2_spacer_{index}",
                    "transform": transform,
                    "use_source_colors": True,
                }
                for index, transform in enumerate(M2_STANDOFF_FLOOR_TRANSFORMS, start=1)
            ),
            {
                "path": "base_clamp.step",
                "name": "base_clamp",
                "transform": BASE_CLAMP_F12_TO_FLOOR_TRANSFORM,
            },
            *(
                {
                    "path": "m2_5_hex_spacer_6mm.step",
                    "name": f"m2_5_bus_spacer_{index}",
                    "transform": transform,
                    "use_source_colors": True,
                }
                for index, transform in enumerate(M2_5_BUS_STANDOFF_FLOOR_TRANSFORMS, start=1)
            ),
            {
                "path": "waveshare_bus_servo_adapter_a.step",
                "name": "waveshare_bus_servo_adapter_a",
                "transform": WAVESHARE_BUS_FLOOR_TRANSFORM,
                "use_source_colors": True,
            },
        ],
    }


def build():
    return link_assembly_from_instances(
        "base_clamp_assembly",
        assembly_instances()["instances"],
        base_dir=ASSEMBLY_DIR,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}

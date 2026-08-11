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

# Demonstration assembly for the servo horn yoke's intended mate: the yoke
# straddles both the output horn and rear horn, with the yoke flipped 180 degrees
# about its web axis so the web remains outside the servo case. The yoke<->servo
# relationship is expressed as native build123d joints by build() via
# link_assembly_from_instances; the mates derive from those joints, not a dict.
YOKE_HORN_SPAN_CENTER_LOCAL_Y_MM = -9.1
YOKE_180_ABOUT_WEB_AXIS_TRANSFORM = list(
    servo_horn_yoke.STANDALONE_YOKE_ON_SERVO_HORNS_TRANSFORM
)


def assembly_instances() -> dict[str, object]:
    return {
        "instances": [
            {
                "path": "../parts/imports/sts3250.step",
                "name": "sts3250",
                "transform": [
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                ],
                "use_source_colors": True,
            },
            {
                "path": "../parts/servo_horn_yoke.step",
                "name": "servo_horn_yoke",
                "transform": YOKE_180_ABOUT_WEB_AXIS_TRANSFORM,
            },
        ],
    }


def build():
    return link_assembly_from_instances(
        "servo_horn_yoke_mount",
        assembly_instances()["instances"],
        base_dir=Path(__file__).resolve().parent,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}

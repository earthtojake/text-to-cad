#!/usr/bin/env python3
"""
Verification assembly for the tom v2 servo end mount on an STS3250.

The mount is authored directly in the imported STS3250 local frame, so both
parts use identity transforms here. This keeps the assembly useful as a direct
fit check for the flange wrap clearances and screw-hole placement.
"""

from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))

# Import while V2_DIR is on sys.path (module-load time): the cad CLI's generator
# loader restores sys.path after exec, so a deferred import inside build() would
# fail in a fresh CLI process.
from robot_common.link_assembly import link_assembly_from_instances


IDENTITY_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def assembly_instances() -> dict[str, object]:
    return {
        "instances": [
            {
                "path": "../parts/imports/sts3250.step",
                "name": "sts3250",
                "transform": list(IDENTITY_TRANSFORM),
                "use_source_colors": True,
            },
            {
                "path": "../parts/servo_end_mount.step",
                "name": "servo_end_mount",
                "transform": list(IDENTITY_TRANSFORM),
                "use_source_colors": True,
            },
        ],
    }


def build():
    return link_assembly_from_instances(
        "servo_end_mount_sts3250",
        assembly_instances()["instances"],
        base_dir=Path(__file__).resolve().parent,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}

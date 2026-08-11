from __future__ import annotations

import sys
from pathlib import Path

TOM_DIR = Path(__file__).resolve().parents[1]
if str(TOM_DIR) not in sys.path:
    sys.path.insert(0, str(TOM_DIR))

from robot_common.robot_arm_link_common import rebased_robot_arm_instances


SOURCE_REF = "@cad[STEP/robot_arm#o1.2]"
ANCHOR_INSTANCE_NAME = "sts3250_1"
EXTRACTED_INSTANCE_NAMES = (
    "sts3250_1",
    "servo_end_mount",
)


def assembly_instances() -> dict[str, object]:
    # Flat instance list consumed by tom's composition (V1-derived placements
    # rebased from robot_arm). gen_step() returns the shape; this is internal data.
    instances = rebased_robot_arm_instances(
        source_ref=SOURCE_REF,
        anchor_instance_name=ANCHOR_INSTANCE_NAME,
        extracted_instance_names=EXTRACTED_INSTANCE_NAMES,
    )
    for instance in instances:
        if instance.get("name") == "servo_end_mount":
            instance["path"] = "../parts/servo_end_mount.step"
            instance["use_source_colors"] = True
    return {
        "instances": instances,
    }


def build():
    """shoulder_yaw_link as an AssemblyHelper sub-assembly with explicit rigid mates.

    The placements are V1-derived (rebased from the robot_arm reference assembly), so
    the link re-expresses those correct placements as rigid mates via the shared
    converter rather than re-encoding constants.
    """
    from robot_common.link_assembly import link_assembly_from_instances

    return link_assembly_from_instances(
        "shoulder_yaw_link",
        assembly_instances()["instances"],
        base_dir=Path(__file__).resolve().parent,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}

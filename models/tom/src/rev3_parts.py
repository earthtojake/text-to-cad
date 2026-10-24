"""Tom rev3's parts: the occurrences of its production arm that `stages/tom2.py` reads.

`recovered/tom_rev3/tom.step` (354 MB) is never read by the build. Each occurrence the stage
uses is a model of its own here, the occurrence `read_step` finds at its path in the arm (the
labels `cadgen inspect` names), returned at its own frame; every one of them stands at the
arm's origin, so its parts stay where they were. Running this script exports each to the xbf
`tom2.py` reads, `STEP/imported/parts/<occurrence>.xbf`: the conversion of a vendor STEP,
made once (the first read parses the STEP, about 40 s; the others replay it).

    python src/rev3_parts.py
"""
from pathlib import Path

import build123d as bd
from cadgen import export, model, read_step

IMPORTED = Path(__file__).resolve().parents[1] / "STEP" / "imported"
TOM_STEP = IMPORTED / "recovered" / "tom_rev3" / "tom.step"
PARTS = IMPORTED / "parts"


def occurrence(path):
    """The occurrence of tom.step at ``path`` (labels from the root, ``/``-separated), at its
    own frame: its location in the arm dropped, its subtree as the file has it."""
    node = read_step(TOM_STEP)
    for label in path.split("/"):
        matches = [child for child in node.children if child.label == label]
        if len(matches) != 1:
            raise LookupError(f"{path}: {len(matches)} children of {node.label!r} are labelled {label!r}")
        node = matches[0]
    # A new assembly of the occurrence's components, so the document's root is the
    # occurrence itself (returned as it is, a placed instance, it would sit inside a root of
    # its own name), at its own frame: its components keep their places in it.
    components = list(node.children)
    node.children = ()
    return bd.Compound(children=components, label=node.label)


@model
def shoulder_yaw_servo():
    return occurrence("base_link/shoulder_yaw_servo")


@model
def m8_thumbscrew():
    return occurrence("base_link/m8_thumbscrew")


@model
def shoulder_yaw_assembly():
    return occurrence("shoulder_yaw_assembly")


@model
def shoulder_pitch_assembly_screws():
    return occurrence("shoulder_pitch_assembly/shoulder_pitch_assembly_screws")


@model
def upper_arm_assembly():
    return occurrence("upper_arm_assembly")


@model
def elbow_assembly():
    return occurrence("elbow_assembly")


@model
def forearm_assembly():
    return occurrence("forearm_assembly")


@model
def gripper_screws():
    return occurrence("gripper/gripper_screws")


PARTS_MODELS = (shoulder_yaw_servo, m8_thumbscrew, shoulder_yaw_assembly, shoulder_pitch_assembly_screws,
                upper_arm_assembly, elbow_assembly, forearm_assembly, gripper_screws)


if __name__ == "__main__":
    for part in PARTS_MODELS:
        export(part, PARTS / f"{part.__name__}.xbf")

"""Robot gripper, gear-rack drive (thang010146): imported STEP + its kinematics.

A sliding piston drives two conrods, the conrods crank two counter-rotating
pinions, and each pinion pushes an opposing rack jaw. Only the pinion->rack
half is exactly linear, so that half is the `grip` coupling; the piston and
conrods of the closed loop are solved per pose, and the continuous loop lives
in the clip.
"""

from __future__ import annotations

from pathlib import Path

import cadgen
from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "STEP" / "imported" / "gear_rack_gripper.step"

Z_AXIS = (0.0, 0.0, 1.0)

# Rack travel per full pinion sweep: 20 mm pitch radius over 82 degrees.
JAW_TRAVEL = 28.6234
PISTON_TRAVEL = 27.8754

KINEMATICS = {
    "mates": [
        # Base -> pinions, counter-rotating about their own bore axes.
        cadgen.revolute(
            "left_pinion",
            parent="#o1.1.10",
            child="#o1.1.13",
            origin=(-40.0, 0.0, 14.000004),
            direction=Z_AXIS,
            limits=(0.0, 82.0),
        ),
        cadgen.revolute(
            "right_pinion",
            parent="#o1.1.10",
            child="#o1.1.14",
            origin=(40.0, 0.0, 14.000004),
            direction=Z_AXIS,
            limits=(-82.0, 0.0),
        ),
        # Base -> rack jaws, sliding out along their own racks.
        cadgen.slider(
            "left_jaw",
            parent="#o1.1.10",
            child="#o1.1.11",
            origin=(-27.36, 54.5, 14.0),
            direction=(-1.0, 0.0, 0.0),
            limits=(0.0, JAW_TRAVEL),
        ),
        cadgen.slider(
            "right_jaw",
            parent="#o1.1.10",
            child="#o1.1.12",
            origin=(27.36, 54.5, 14.0),
            direction=(1.0, 0.0, 0.0),
            limits=(0.0, JAW_TRAVEL),
        ),
        # Base -> piston: the input, sliding up the gripper's axis.
        cadgen.slider(
            "piston",
            parent="#o1.1.10",
            child="#o1.1.17",
            origin=(0.0, -47.0, 14.0),
            direction=(0.0, 1.0, 0.0),
            limits=(0.0, PISTON_TRAVEL),
        ),
        # Piston -> conrods, about the crank pins they carry.
        cadgen.revolute(
            "left_conrod",
            parent="#o1.1.17",
            child="#o1.1.15",
            origin=(-20.0, -10.0, 14.000004),
            direction=Z_AXIS,
            limits=(0.0, 62.0),
        ),
        cadgen.revolute(
            "right_conrod",
            parent="#o1.1.17",
            child="#o1.1.16",
            origin=(20.0, -10.0, 14.000004),
            direction=Z_AXIS,
            limits=(-62.0, 0.0),
        ),
    ],
    # One grip handle, 0 closed to 1 open: the pinion/rack gearing is exact.
    "couplings": [
        cadgen.couple(
            "grip",
            {
                "left_pinion": 82.0,
                "right_pinion": -82.0,
                "left_jaw": 28.623399732707,
                "right_jaw": 28.623399732707,
            },
            limits=(0.0, 1.0),
        ),
    ],
    "poses": {
        "closed": {"grip": 0.0},
        "half_open": {
            "grip": 0.5,
            "piston": 16.617929017260018,
            "left_conrod": 46.439667670303905,
            "right_conrod": -46.43966767030392,
        },
        "open": {
            "grip": 1.0,
            "piston": 27.87534165741835,
            "left_conrod": 61.50892814542118,
            "right_conrod": -61.508928145421194,
        },
    },
}


@step(
    out="../STEP/gear_rack_gripper.step",
    kinematics=KINEMATICS,
    animation="gear_rack_gripper.anim.js",
)
def gear_rack_gripper():
    return read_step(_SOURCE)


if __name__ == "__main__":
    gear_rack_gripper()

"""180 degree flip mechanism (thang010146): imported STEP + its kinematics.

The geometry is not ours — the vendor document under ``STEP/imported/`` is the
only source of shape here. This script exists so the ANNOTATION (mates, poses,
the reference clip) is authored code that can be edited and rebuilt with one
``python src/flip_mechanism_180.py``.

The mechanism is a closed-loop four-bar: crank, coupler, rocker. cadgen mates
are a tree evaluating forward kinematics, so each named pose is the loop
already SOLVED at that configuration, and the continuous motion lives in the
clip.
"""

from __future__ import annotations

from pathlib import Path

import cadgen
from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "STEP" / "imported" / "180_degree_flip_mechanism.step"

Z_AXIS = (0.0, 0.0, 1.0)

KINEMATICS = {
    "mates": [
        # Frame -> crank, about the ground pivot.
        cadgen.revolute(
            "crank",
            parent="#o1.1",
            child="#o1.3",
            origin=(104.981, 29.599, 0.0),
            direction=Z_AXIS,
            limits=(-115.0, 0.0),
        ),
        # Crank -> coupler, about the floating pin they share.
        cadgen.revolute(
            "coupler",
            parent="#o1.3",
            child="#o1.4",
            origin=(45.03, 229.61, 0.0),
            direction=Z_AXIS,
            limits=(-185.0, 170.0),
        ),
        # Frame -> rocker, about the second ground pivot.
        cadgen.revolute(
            "rocker",
            parent="#o1.1",
            child="#o1.2",
            origin=(-15.002, 229.609, 0.0),
            direction=Z_AXIS,
            limits=(-150.0, 0.0),
        ),
    ],
    # Each preset is the four-bar solved at one crank angle: the DOFs are not
    # independent, so a pose sets all three together.
    "poses": {
        "rest": {"crank": 0.0, "coupler": 0.0, "rocker": 0.0},
        "quarter": {
            "crank": -54.953089135182346,
            "coupler": 85.21953242495402,
            "rocker": -32.49779469176195,
        },
        "over_center": {
            "crank": -109.90617827036469,
            "coupler": 167.0800826980021,
            "rocker": -105.3506617817834,
        },
        "three_quarter": {
            "crank": -54.953089135182346,
            "coupler": -171.807869748,
            "rocker": -129.06225340466568,
        },
        "flipped": {
            "crank": 0.0,
            "coupler": -180.02571935719533,
            "rocker": -145.09125186021225,
        },
    },
}


@step(
    out="../STEP/flip_mechanism_180.step",
    kinematics=KINEMATICS,
)
def flip_mechanism_180():
    return read_step(_SOURCE)


if __name__ == "__main__":
    flip_mechanism_180()

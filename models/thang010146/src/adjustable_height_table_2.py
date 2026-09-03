"""Adjustable height table 2 (thang010146): imported STEP + its kinematics.

A scissor lift: one screw actuator drives a pair of counter-rotating scissor
arms whose ends ride on four rollers, and the table top hoists straight up.
The loop is closed, so the `scissor` coupling carries the exactly-linear half
(the two arms are equal and opposite) and each pose is the loop solved at one
height. The reference motion lives in the clip.
"""

from __future__ import annotations

from pathlib import Path

import cadgen
from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent
_SOURCE = _HERE.parent / "STEP" / "imported" / "adjustable_height_table_2.step"

X_AXIS = (1.0, 0.0, 0.0)
Y_AXIS = (0.0, 1.0, 0.0)
Z_AXIS = (0.0, 0.0, 1.0)

# The scissor's two hinge lines, on the base and on the lifted top.
BASE_HINGE = (14.610456, -171.775187, 23.0)
TOP_HINGE = (14.610456, -171.775187, 69.00033)
# The rolling ends travel along the table's long (y) direction.
ROLLER_LINE = (14.610456, 124.677119, 23.0)
ROLLER_LINE_TOP = (14.610456, 124.677119, 69.00033)
ACTUATOR_PIVOT = (14.610456, -142.775187, 27.499913)

KINEMATICS = {
    "mates": [
        # Base -> table top: the straight-line lift the whole mechanism serves.
        cadgen.slider(
            "hoist",
            parent="#o1.1",
            child="#o1.2",
            origin=TOP_HINGE,
            direction=Z_AXIS,
            limits=(0.0, 176.708),
        ),
        # The two scissor arms, hinged on the base and on the top.
        cadgen.revolute(
            "rise",
            parent="#o1.1",
            child="#o1.3",
            origin=BASE_HINGE,
            direction=X_AXIS,
            limits=(0.0, 39.113),
        ),
        cadgen.revolute(
            "descend",
            parent="#o1.2",
            child="#o1.4",
            origin=TOP_HINGE,
            direction=X_AXIS,
            limits=(-39.113, 0.0),
        ),
        # Four rolling ends: two in the base track, two under the top.
        cadgen.slider(
            "lower_roller_1",
            parent="#o1.1",
            child="#o1.6",
            origin=ROLLER_LINE,
            direction=Y_AXIS,
            limits=(-95.453, 0.0),
        ),
        cadgen.slider(
            "lower_roller_2",
            parent="#o1.1",
            child="#o1.7",
            origin=ROLLER_LINE,
            direction=Y_AXIS,
            limits=(-95.453, 0.0),
        ),
        cadgen.slider(
            "upper_roller_1",
            parent="#o1.2",
            child="#o1.8",
            origin=ROLLER_LINE_TOP,
            direction=Y_AXIS,
            limits=(-95.453, 0.0),
        ),
        cadgen.slider(
            "upper_roller_2",
            parent="#o1.2",
            child="#o1.9",
            origin=ROLLER_LINE_TOP,
            direction=Y_AXIS,
            limits=(-95.453, 0.0),
        ),
        # Screw actuator: the rod extends, its shaft rides along, and the
        # slider block swings with the arm it pushes.
        cadgen.slider(
            "actuator_rod",
            parent="#o1.1",
            child="#o1.5",
            origin=ACTUATOR_PIVOT,
            direction=Z_AXIS,
            limits=(0.0, 27.633),
        ),
        # Siblings in the instance tree, so the shaft needs a rigid mate to
        # ride the rod.
        cadgen.fastened("actuator_shaft", parent="#o1.5", child="#o1.11"),
        cadgen.revolute(
            "actuator_slider",
            parent="#o1.5",
            child="#o1.10",
            origin=ACTUATOR_PIVOT,
            direction=X_AXIS,
            limits=(0.0, 39.113),
        ),
    ],
    # The scissor arms are equal and opposite: one virtual DOF, two real ones.
    "couplings": [
        cadgen.couple("scissor", {"rise": 1.0, "descend": -1.0}, limits=(0.0, 39.113)),
    ],
    "poses": {
        "collapsed": {"hoist": 0.0},
        "mid": {
            "hoist": 84.49983499999998,
            "scissor": 16.96511725715513,
            "lower_roller_1": -26.32324975502783,
            "lower_roller_2": -26.32324975502783,
            "upper_roller_1": -26.32324975502783,
            "upper_roller_2": -26.32324975502783,
            "actuator_rod": 9.510074809559974,
            "actuator_slider": 16.96511725715513,
        },
        "raised": {
            "hoist": 168.99966999999998,
            "scissor": 36.95974393771785,
            "lower_roller_1": -87.22754624908873,
            "lower_roller_2": -87.22754624908873,
            "upper_roller_1": -87.22754624908873,
            "upper_roller_2": -87.22754624908873,
            "actuator_rod": 25.300575275971575,
            "actuator_slider": 36.95974393771785,
        },
    },
}


@step(
    out="../STEP/adjustable_height_table_2.step",
    kinematics=KINEMATICS,
    animation="adjustable_height_table_2.anim.js",
)
def adjustable_height_table_2():
    return read_step(_SOURCE)


if __name__ == "__main__":
    adjustable_height_table_2()

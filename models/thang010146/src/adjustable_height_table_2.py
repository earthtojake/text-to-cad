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


ANIMATION_JS = r'''// Reference lift loop for the scissor
// table (thang010146). The scissor is a closed loop with rolling contacts, so
// the solve lives here; the kinematics block carries the individual joints and
// the solved presets (`mid`, `raised`).
//
// Targets are occurrence ids from the imported assembly:
//   o1.1 base   o1.2 table top   o1.3 rising links   o1.4 descending links
//   o1.5 piston rod   o1.6/o1.7 lower rollers   o1.8/o1.9 upper rollers
//   o1.10 green actuator slider   o1.11 actuator cross shaft

const X = [1, 0, 0];

const BOTTOM_FIXED_PIVOT = [14.610456, -171.775187, 23.0];
const TOP_FIXED_PIVOT = [14.610456, -171.775187, 69.00033];
const ROLLER_PIVOT = [14.610456, 124.677119, 69.00033];
const LOWER_ROLLER_CENTER = [14.610456, 124.677119, 23.0];
const UPPER_ROLLER_CENTER = [14.610456, 124.677119, 69.00033];
const ACTUATOR_PIVOT = [14.610456, -142.775187, 27.499913];

const INITIAL_HEIGHT = TOP_FIXED_PIVOT[2] - BOTTOM_FIXED_PIVOT[2];
const INITIAL_RUN = ROLLER_PIVOT[1] - BOTTOM_FIXED_PIVOT[1];
const LINK_LENGTH = Math.hypot(INITIAL_RUN, INITIAL_HEIGHT);
const INITIAL_LINK_ANGLE_DEG = angleDeg(INITIAL_HEIGHT, INITIAL_RUN);
const ACTUATOR_Y_OFFSET = ACTUATOR_PIVOT[1] - BOTTOM_FIXED_PIVOT[1];
const ROLLER_RADIUS = 20.0;
const RAISED_HEIGHT = 215.0;

function clamp(value, min, max) {
  return Math.min(Math.max(Number(value) || 0, min), max);
}

function smooth01(value) {
  const t = clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function angleDeg(height, run) {
  return (Math.atan2(height, run) * 180) / Math.PI;
}

// Low table, hydraulic lift, brief dwell at height, return, brief dwell.
function cycleLift(phase) {
  const p = ((phase % 1) + 1) % 1;
  if (p < 0.42) return smooth01(p / 0.42);
  if (p < 0.52) return 1;
  if (p < 0.94) return 1 - smooth01((p - 0.52) / 0.42);
  return 0;
}

function sampleLift(rawLift) {
  const height = lerp(INITIAL_HEIGHT, RAISED_HEIGHT, smooth01(rawLift));
  const run = Math.sqrt(Math.max(1e-6, LINK_LENGTH * LINK_LENGTH - height * height));
  const angle = angleDeg(height, run);
  const rollerYDelta = BOTTOM_FIXED_PIVOT[1] + run - ROLLER_PIVOT[1];
  // The green slider follows the lower link along the fixed actuator
  // centerline: intersect the link with that line to place it.
  const actuatorZ = BOTTOM_FIXED_PIVOT[2] + height * clamp(ACTUATOR_Y_OFFSET / run, 0, 1);
  return {
    heightDelta: height - INITIAL_HEIGHT,
    rollerYDelta,
    actuatorZDelta: actuatorZ - ACTUATOR_PIVOT[2],
    risingAngleDelta: angle - INITIAL_LINK_ANGLE_DEG,
    descendingAngleDelta: -(angle - INITIAL_LINK_ANGLE_DEG),
    wheelSpinDeg: -(rollerYDelta / (2 * Math.PI * ROLLER_RADIUS)) * 360
  };
}

export const clips = {
  lift: {
    label: "Reference lift loop",
    duration: 8,
    loop: true,
    update(t, m) {
      const pose = sampleLift(cycleLift(t / 8));
      const rise = [0, 0, pose.heightDelta];
      const actuator = [0, 0, pose.actuatorZDelta];

      m.get("#o1.2").translate(rise);
      m.get("#o1.3").rotate(X, pose.risingAngleDelta, BOTTOM_FIXED_PIVOT);
      m.get("#o1.4").rotate(X, pose.descendingAngleDelta, TOP_FIXED_PIVOT).translate(rise);
      m.get("#o1.6,o1.7")
        .rotate(X, pose.wheelSpinDeg, LOWER_ROLLER_CENTER)
        .translate([0, pose.rollerYDelta, 0]);
      m.get("#o1.8,o1.9")
        .rotate(X, pose.wheelSpinDeg, UPPER_ROLLER_CENTER)
        .translate([0, pose.rollerYDelta, pose.heightDelta]);
      m.get("#o1.5,o1.11").translate(actuator);
      m.get("#o1.10").rotate(X, pose.risingAngleDelta, ACTUATOR_PIVOT).translate(actuator);
    }
  }
};
'''


@step(
    out="../STEP/adjustable_height_table_2.step",
    kinematics=KINEMATICS,
    animation=ANIMATION_JS,
)
def adjustable_height_table_2():
    return read_step(_SOURCE)


if __name__ == "__main__":
    adjustable_height_table_2()

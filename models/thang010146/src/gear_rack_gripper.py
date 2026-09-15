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


ANIMATION_JS = r'''// Reference drive loop for the gear-rack robot
// gripper (thang010146). The mechanism is a closed loop: a sliding piston
// drives two conrods, the conrods crank two counter-rotating pinions, and the
// pinions push two opposing rack jaws. Only the pinion->rack half is linear,
// so the gearing lives in the kinematics block (`grip`) and the whole solved
// loop lives here.
//
// Targets are occurrence ids from the imported assembly:
//   o1.1.10 base   o1.1.11/12 rack jaws   o1.1.13/14 pinions
//   o1.1.15/16 conrods   o1.1.17 piston

const Z = [0, 0, 1];

const GEAR_PITCH_RADIUS_MM = 20;
const MAX_GEAR_ANGLE_DEG = 82;

const LEFT_GEAR_CENTER = [-40, 0, 14.000004];
const RIGHT_GEAR_CENTER = [40, 0, 14.000004];
const LEFT_CRANK_PIN = [-40, -15, 14.000004];
const RIGHT_CRANK_PIN = [40, -15, 14.000004];
const LEFT_PISTON_PIN = [-20, -10, 14.000004];
const RIGHT_PISTON_PIN = [20, -10, 14.000004];

const LINK_LENGTH_MM = distance2(LEFT_PISTON_PIN, LEFT_CRANK_PIN);
const LEFT_LINK_ANGLE_0 = angleDeg2(LEFT_PISTON_PIN, LEFT_CRANK_PIN);
const RIGHT_LINK_ANGLE_0 = angleDeg2(RIGHT_PISTON_PIN, RIGHT_CRANK_PIN);

function clamp(value, min, max) {
  return Math.min(Math.max(Number(value) || 0, min), max);
}

function smooth01(value) {
  const t = clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
}

function distance2(a, b) {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

function angleDeg2(a, b) {
  return (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI;
}

function rotatePointZ(point, origin, angleDeg) {
  const r = (angleDeg * Math.PI) / 180;
  const c = Math.cos(r);
  const s = Math.sin(r);
  const dx = point[0] - origin[0];
  const dy = point[1] - origin[1];
  return [origin[0] + dx * c - dy * s, origin[1] + dx * s + dy * c, point[2]];
}

function normalizeAngleDeg(value) {
  let angle = Number(value) || 0;
  while (angle > 180) angle -= 360;
  while (angle < -180) angle += 360;
  return angle;
}

// Slider-crank branch: the imported pose has the piston pin ahead of the crank
// pin, so keep the +dy root and the conrod never flips through the gear.
function solvePistonY(leftCrankPin) {
  const dx = clamp(
    LEFT_PISTON_PIN[0] - leftCrankPin[0],
    -LINK_LENGTH_MM + 1e-6,
    LINK_LENGTH_MM - 1e-6
  );
  return leftCrankPin[1] + Math.sqrt(Math.max(1e-6, LINK_LENGTH_MM * LINK_LENGTH_MM - dx * dx));
}

function samplePose(rawStroke) {
  const stroke = smooth01(rawStroke);
  const leftGearAngleDeg = stroke * MAX_GEAR_ANGLE_DEG;
  const rackTravelMm = ((leftGearAngleDeg * Math.PI) / 180) * GEAR_PITCH_RADIUS_MM;
  const leftCrankPin = rotatePointZ(LEFT_CRANK_PIN, LEFT_GEAR_CENTER, leftGearAngleDeg);
  const rightCrankPin = rotatePointZ(RIGHT_CRANK_PIN, RIGHT_GEAR_CENTER, -leftGearAngleDeg);
  const pistonY = solvePistonY(leftCrankPin);
  const leftPistonPin = [LEFT_PISTON_PIN[0], pistonY, LEFT_PISTON_PIN[2]];
  const rightPistonPin = [RIGHT_PISTON_PIN[0], pistonY, RIGHT_PISTON_PIN[2]];
  return {
    pistonDeltaY: pistonY - LEFT_PISTON_PIN[1],
    rackTravelMm,
    leftGearAngleDeg,
    rightGearAngleDeg: -leftGearAngleDeg,
    leftLinkAngleDeltaDeg: normalizeAngleDeg(
      angleDeg2(leftPistonPin, leftCrankPin) - LEFT_LINK_ANGLE_0
    ),
    rightLinkAngleDeltaDeg: normalizeAngleDeg(
      angleDeg2(rightPistonPin, rightCrankPin) - RIGHT_LINK_ANGLE_0
    )
  };
}

// Closed pose, piston-driven opening, short dwell, return, short dwell.
function cycleStroke(phase) {
  const p = ((phase % 1) + 1) % 1;
  if (p < 0.38) return smooth01(p / 0.38);
  if (p < 0.5) return 1;
  if (p < 0.88) return 1 - smooth01((p - 0.5) / 0.38);
  return 0;
}

export const clips = {
  drive: {
    label: "Piston rack drive",
    duration: 6,
    loop: true,
    update(t, m) {
      const pose = samplePose(cycleStroke(t / 6));
      const lift = [0, pose.pistonDeltaY, 0];

      m.get("#o1.1.17").translate(lift);
      m.get("#o1.1.15").rotate(Z, pose.leftLinkAngleDeltaDeg, LEFT_PISTON_PIN).translate(lift);
      m.get("#o1.1.16").rotate(Z, pose.rightLinkAngleDeltaDeg, RIGHT_PISTON_PIN).translate(lift);
      m.get("#o1.1.13").rotate(Z, pose.leftGearAngleDeg, LEFT_GEAR_CENTER);
      m.get("#o1.1.14").rotate(Z, pose.rightGearAngleDeg, RIGHT_GEAR_CENTER);
      m.get("#o1.1.11").translate([-pose.rackTravelMm, 0, 0]);
      m.get("#o1.1.12").translate([pose.rackTravelMm, 0, 0]);
    }
  }
};
'''


@step(
    out="../STEP/gear_rack_gripper.step",
    kinematics=KINEMATICS,
    animation=ANIMATION_JS,
)
def gear_rack_gripper():
    return read_step(_SOURCE)


if __name__ == "__main__":
    gear_rack_gripper()

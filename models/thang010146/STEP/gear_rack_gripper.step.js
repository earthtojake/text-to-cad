// gear_rack_gripper.step.js — reference drive loop for the gear-rack robot
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

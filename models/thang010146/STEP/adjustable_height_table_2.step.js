// adjustable_height_table_2.step.js — reference lift loop for the scissor
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

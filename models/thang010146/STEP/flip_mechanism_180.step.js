// flip_mechanism_180.step.js — reference flip loop (thang010146).
// A toggle four-bar: the pink lower rocker drives the red/panel coupler out to
// an over-center tangent pose, then the coupler returns on the OPPOSITE circle
// branch with the panel flipped 180 degrees. Branch switching is exactly what
// a forward-kinematics mate tree cannot express, so the loop is solved here;
// the kinematics block carries the three revolutes and the solved presets.
//
// Targets are occurrence ids from the imported assembly:
//   o1.1 fixed frame   o1.2 blue upper link   o1.3 lower rocker + handle
//   o1.4 red coupler + flip panel

const Z = [0, 0, 1];

const PIVOTS = {
  upperFrame: [-15.002, 229.609, 0],
  lowerFrame: [104.981, 29.599, 0],
  lowerBoard: [45.03, 229.61, 0],
  upperBoard: [44.984, 420.401, 0]
};

const PANEL_ANGLE_0 = angleDeg2(PIVOTS.lowerBoard, PIVOTS.upperBoard);
const BLUE_ANGLE_0 = angleDeg2(PIVOTS.upperFrame, PIVOTS.upperBoard);
const LOWER_ROCKER_ANGLE_0 = angleDeg2(PIVOTS.lowerFrame, PIVOTS.lowerBoard);
const LOWER_LINK_LENGTH = distance2(PIVOTS.lowerFrame, PIVOTS.lowerBoard);
const UPPER_LINK_LENGTH = distance2(PIVOTS.upperFrame, PIVOTS.upperBoard);
const COUPLER_LINK_LENGTH = distance2(PIVOTS.lowerBoard, PIVOTS.upperBoard);
const OVER_CENTER_CRANK_ANGLE_DEG = -3.22068;

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

function distance2(a, b) {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

function angleDeg2(a, b) {
  return (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI;
}

function pointFromAngle(origin, length, angleDeg) {
  const r = (angleDeg * Math.PI) / 180;
  return [origin[0] + Math.cos(r) * length, origin[1] + Math.sin(r) * length, origin[2] || 0];
}

function circleIntersections(centerA, radiusA, centerB, radiusB) {
  const dx = centerB[0] - centerA[0];
  const dy = centerB[1] - centerA[1];
  const distance = Math.hypot(dx, dy);
  if (distance <= 1e-6) {
    return [centerA, centerA];
  }
  const solved = clamp(
    distance,
    Math.abs(radiusA - radiusB) + 1e-6,
    radiusA + radiusB - 1e-6
  );
  const along = (radiusA * radiusA - radiusB * radiusB + solved * solved) / (2 * solved);
  const height = Math.sqrt(Math.max(0, radiusA * radiusA - along * along));
  const ux = dx / distance;
  const uy = dy / distance;
  const mx = centerA[0] + along * ux;
  const my = centerA[1] + along * uy;
  return [
    [mx - uy * height, my + ux * height, centerA[2] || 0],
    [mx + uy * height, my - ux * height, centerA[2] || 0]
  ];
}

// The two coupler branches, highest upper-pivot first: [closed, open].
function boardBranches(lower) {
  return circleIntersections(
    PIVOTS.upperFrame,
    UPPER_LINK_LENGTH,
    lower,
    COUPLER_LINK_LENGTH
  ).sort((a, b) => b[1] - a[1]);
}

function samplePose(rawFlip) {
  const flip = clamp(rawFlip, 0, 1);
  const firstHalf = flip <= 0.5;
  const leg = firstHalf ? smooth01(flip / 0.5) : smooth01((flip - 0.5) / 0.5);
  const lowerAngleDeg = firstHalf
    ? lerp(LOWER_ROCKER_ANGLE_0, OVER_CENTER_CRANK_ANGLE_DEG, leg)
    : lerp(OVER_CENTER_CRANK_ANGLE_DEG, LOWER_ROCKER_ANGLE_0, leg);
  const lower = pointFromAngle(PIVOTS.lowerFrame, LOWER_LINK_LENGTH, lowerAngleDeg);
  const branches = boardBranches(lower);
  const upper = firstHalf ? branches[0] : branches[1];
  return {
    lower,
    panelAngleDelta: angleDeg2(lower, upper) - PANEL_ANGLE_0,
    blueAngleDelta: angleDeg2(PIVOTS.upperFrame, upper) - BLUE_ANGLE_0,
    lowerRockerAngleDelta: lowerAngleDeg - LOWER_ROCKER_ANGLE_0
  };
}

// Closed -> over-center -> open -> over-center -> closed.
function cycleFlip(phase) {
  const p = ((phase % 1) + 1) % 1;
  return 0.5 - 0.5 * Math.cos(p * Math.PI * 2);
}

export const clips = {
  flip: {
    label: "Reference flip loop",
    duration: 5,
    loop: true,
    update(t, m) {
      const pose = samplePose(cycleFlip(t / 5));
      const couplerTranslate = [
        pose.lower[0] - PIVOTS.lowerBoard[0],
        pose.lower[1] - PIVOTS.lowerBoard[1],
        0
      ];

      m.get("#o1.4")
        .rotate(Z, pose.panelAngleDelta, PIVOTS.lowerBoard)
        .translate(couplerTranslate);
      m.get("#o1.2").rotate(Z, pose.blueAngleDelta, PIVOTS.upperFrame);
      m.get("#o1.3").rotate(Z, pose.lowerRockerAngleDelta, PIVOTS.lowerFrame);
    }
  }
};

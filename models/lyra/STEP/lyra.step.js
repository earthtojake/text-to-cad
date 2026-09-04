// lyra.step.js — articulation choreography for the lyra dexterous hand.
//
// The STEP geometry is baked in the "relaxed" pose (chain.BAKED_POSE_NAME).
// Each clip recomputes full-chain FK at its target pose and applies, per link,
// the rigid delta T_target * inverse(T_relaxed): a rotation about the world
// origin followed by a translation. Successive handle calls PREMULTIPLY, so
// `.rotate(axis, deg, [0,0,0]).translate(t)` is exactly `p -> Rd*p + t`.
//
// The pose tables and the joint list mirror src/lib/chain.py
// (named_poses_deg() / all_joints()); the STATIC space — joint limits and the
// named poses as viewer presets — lives in the model's `kinematics=` block, and
// this module is the motion. Poses are blended in JOINT space with smoothstep
// easing: every intermediate state of a serial digit chain is itself a valid
// pose, so a blend can never break the mechanism. Every loop starts and ends on
// the exact pose it began with.
//
// Key orders are capsule-verified collision-free (src/lib/clearance.py) —
// re-run that check after changing a pose or a key order.

const FINGERS = ["index", "middle", "ring", "pinky"];

// Chain offsets (mm), mirrored from src/lib/chain.py.
const MCP = {
  index: [28.5, 0, 99],
  middle: [9.5, 0, 103],
  ring: [-9.5, 0, 99],
  pinky: [-28.5, 0, 90],
};
const SEG = { index: [44, 26], middle: [48, 29], ring: [44, 27], pinky: [35, 21] };
const THUMB_CMC = [31, 4, 44];
const THUMB_BASE_LEN = 13;
const THUMB_METACARPAL_LEN = 46;
const THUMB_PROXIMAL_LEN = 30;

const NEG_X = [-1, 0, 0];
const NEG_Y = [0, -1, 0];
const Z = [0, 0, 1];

function buildJoints() {
  const joints = [];
  for (const finger of FINGERS) {
    joints.push(
      { name: `${finger}_mcp`, parent: "palm", child: `${finger}_proximal`, origin: MCP[finger], axis: NEG_X },
      { name: `${finger}_pip`, parent: `${finger}_proximal`, child: `${finger}_middle`, origin: [0, 0, SEG[finger][0]], axis: NEG_X },
      { name: `${finger}_dip`, parent: `${finger}_middle`, child: `${finger}_distal`, origin: [0, 0, SEG[finger][1]], axis: NEG_X },
    );
  }
  joints.push(
    { name: "thumb_cmc_yaw", parent: "palm", child: "thumb_base", origin: THUMB_CMC, axis: Z },
    { name: "thumb_cmc_flex", parent: "thumb_base", child: "thumb_metacarpal", origin: [THUMB_BASE_LEN, 0, 0], axis: NEG_Y },
    { name: "thumb_mp", parent: "thumb_metacarpal", child: "thumb_proximal", origin: [THUMB_METACARPAL_LEN, 0, 0], axis: NEG_Y },
    { name: "thumb_ip", parent: "thumb_proximal", child: "thumb_distal", origin: [THUMB_PROXIMAL_LEN, 0, 0], axis: NEG_Y },
  );
  return joints;
}

const JOINTS = buildJoints();
const LINKS = ["palm", ...JOINTS.map((j) => j.child)];

// ---------------------------------------------------------------- poses
function fingerPose(curls, thumb) {
  const pose = {};
  for (const finger of FINGERS) {
    const [mcp, pip, dip] = curls[finger];
    pose[`${finger}_mcp`] = mcp;
    pose[`${finger}_pip`] = pip;
    pose[`${finger}_dip`] = dip;
  }
  const [yaw, flex, mp, ip] = thumb;
  pose.thumb_cmc_yaw = yaw;
  pose.thumb_cmc_flex = flex;
  pose.thumb_mp = mp;
  pose.thumb_ip = ip;
  return pose;
}

// Mirrored from chain.named_poses_deg().
const POSES = {
  zero: fingerPose(
    { index: [0, 0, 0], middle: [0, 0, 0], ring: [0, 0, 0], pinky: [0, 0, 0] },
    [0, 0, 0, 0],
  ),
  relaxed: fingerPose(
    { index: [10, 14, 8], middle: [12, 16, 9], ring: [14, 18, 10], pinky: [16, 20, 12] },
    [34, 26, 14, 12],
  ),
  fist: fingerPose(
    { index: [78, 100, 60], middle: [78, 100, 60], ring: [78, 100, 60], pinky: [78, 100, 60] },
    [92, 13, 58, 74],
  ),
  precision_pinch: fingerPose(
    { index: [40, 48, 30], middle: [66, 92, 55], ring: [66, 92, 55], pinky: [66, 92, 55] },
    [91, 34, 29, 8],
  ),
  tripod_pinch: fingerPose(
    { index: [44, 52, 32], middle: [42, 50, 30], ring: [66, 92, 55], pinky: [66, 92, 55] },
    [100, 39, 0, 14],
  ),
  point: fingerPose(
    { index: [-6, 0, 0], middle: [80, 102, 62], ring: [80, 102, 62], pinky: [80, 102, 62] },
    [62, 30, 42, 45],
  ),
  ok_sign: fingerPose(
    { index: [42, 52, 32], middle: [6, 8, 4], ring: [10, 12, 6], pinky: [14, 16, 8] },
    [91, 26, 35, 20],
  ),
};

const BAKED_POSE = POSES.relaxed;

// ------------------------------------------------------------- math kit
const finite = (v, fallback = 0) => (Number.isFinite(Number(v)) ? Number(v) : fallback);
const clamp = (v, lo, hi) => Math.min(Math.max(finite(v, lo), lo), hi);
const smoothstep = (u) => {
  const t = clamp(u, 0, 1);
  return t * t * (3 - 2 * t);
};
const wrap01 = (v) => ((finite(v, 0) % 1) + 1) % 1;

function rotAxisDeg(axis, deg) {
  const rad = (deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const t = 1 - c;
  const [ax, ay, az] = axis;
  return [
    [c + ax * ax * t, ax * ay * t - az * s, ax * az * t + ay * s],
    [ay * ax * t + az * s, c + ay * ay * t, ay * az * t - ax * s],
    [az * ax * t - ay * s, az * ay * t + ax * s, c + az * az * t],
  ];
}

function matMul3(a, b) {
  const out = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let i = 0; i < 3; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      out[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j];
    }
  }
  return out;
}

function matVec3(a, v) {
  return [
    a[0][0] * v[0] + a[0][1] * v[1] + a[0][2] * v[2],
    a[1][0] * v[0] + a[1][1] * v[1] + a[1][2] * v[2],
    a[2][0] * v[0] + a[2][1] * v[1] + a[2][2] * v[2],
  ];
}

const matTranspose3 = (a) => [
  [a[0][0], a[1][0], a[2][0]],
  [a[0][1], a[1][1], a[2][1]],
  [a[0][2], a[1][2], a[2][2]],
];

const IDENTITY3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];

function fkFrames(anglesDeg) {
  const frames = { palm: { R: IDENTITY3, p: [0, 0, 0] } };
  for (const joint of JOINTS) {
    const parent = frames[joint.parent];
    const offset = matVec3(parent.R, joint.origin);
    const p = [parent.p[0] + offset[0], parent.p[1] + offset[1], parent.p[2] + offset[2]];
    const R = matMul3(parent.R, rotAxisDeg(joint.axis, finite(anglesDeg[joint.name], 0)));
    frames[joint.child] = { R, p };
  }
  return frames;
}

const BAKED_FRAMES = fkFrames(BAKED_POSE);

/**
 * Axis-angle of a rotation matrix.
 *
 * The handle vocabulary has no matrix door, so the delta has to be expressed
 * as one rotation. Near theta = pi the antisymmetric part vanishes and the
 * axis has to come from the diagonal instead, which is the branch below.
 */
function axisAngle(R) {
  const trace = R[0][0] + R[1][1] + R[2][2];
  const cos = clamp((trace - 1) / 2, -1, 1);
  const deg = (Math.acos(cos) * 180) / Math.PI;
  if (deg < 1e-7) return { axis: [0, 0, 1], deg: 0 };
  const sin = Math.sqrt(Math.max(1 - cos * cos, 0));
  if (sin > 1e-6) {
    const k = 1 / (2 * sin);
    return {
      axis: [(R[2][1] - R[1][2]) * k, (R[0][2] - R[2][0]) * k, (R[1][0] - R[0][1]) * k],
      deg,
    };
  }
  // theta ~ pi: the largest diagonal entry gives the most numerically stable
  // column of (R + I), whose direction IS the axis.
  const diag = [R[0][0], R[1][1], R[2][2]];
  const i = diag.indexOf(Math.max(...diag));
  const axis = [R[0][i], R[1][i], R[2][i]];
  axis[i] += 1;
  const n = Math.hypot(axis[0], axis[1], axis[2]) || 1;
  return { axis: [axis[0] / n, axis[1] / n, axis[2] / n], deg };
}

/** The rigid delta carrying a link from its baked placement to `target`. */
function delta(original, target) {
  const Rd = matMul3(target.R, matTranspose3(original.R));
  const moved = matVec3(Rd, original.p);
  return {
    ...axisAngle(Rd),
    translate: [
      target.p[0] - moved[0],
      target.p[1] - moved[1],
      target.p[2] - moved[2],
    ],
  };
}

function blendPoses(a, b, u) {
  const e = smoothstep(u);
  const out = {};
  for (const joint of JOINTS) {
    const from = finite(a[joint.name], 0);
    out[joint.name] = from + (finite(b[joint.name], 0) - from) * e;
  }
  return out;
}

function addScaled(pose, d, scale) {
  const out = {};
  for (const joint of JOINTS) {
    out[joint.name] = finite(pose[joint.name], 0) + finite(d[joint.name], 0) * scale;
  }
  return out;
}

/** Apply a joint-space pose to the model. */
function apply(m, target) {
  const frames = fkFrames(target);
  for (const link of LINKS) {
    const d = delta(BAKED_FRAMES[link], frames[link]);
    m.get(link).rotate(d.axis, d.deg, [0, 0, 0]).translate(d.translate);
  }
}

// ---------------------------------------------------------------- modes
// Keyframe cycle through the showpiece poses; each segment blends for 65% of
// its window and dwells for 35%, wrapping back to its first key so the loop is
// exact. Key order is capsule-verified collision-free: the fist only neighbours
// tripod/relaxed, because blending it with pinch/point/ok would sweep the thumb
// through the index.
const TOUR_KEYS = ["relaxed", "precision_pinch", "ok_sign", "point", "tripod_pinch", "fist"];
// The tour opens with one finger-ripple wave — it starts and ends exactly on
// the relaxed pose, so it splices seamlessly before the first keyframe blend.
const TOUR_RIPPLE_FRAC = 0.22;

function tourPose(phase) {
  const p = wrap01(phase);
  if (p < TOUR_RIPPLE_FRAC) return ripplePose(p / TOUR_RIPPLE_FRAC, 1);
  const q = (p - TOUR_RIPPLE_FRAC) / (1 - TOUR_RIPPLE_FRAC);
  const segCount = TOUR_KEYS.length;
  const seg = Math.min(Math.floor(q * segCount), segCount - 1);
  const u = q * segCount - seg;
  return blendPoses(POSES[TOUR_KEYS[seg]], POSES[TOUR_KEYS[(seg + 1) % segCount]], u / 0.65);
}

/** Open-close power grasp: relaxed -> fist -> relaxed on a raised cosine. */
function graspPose(phase, grip) {
  const wave = 0.5 * (1 - Math.cos(2 * Math.PI * wrap01(phase)));
  return blendPoses(POSES.relaxed, POSES.fist, wave * grip);
}

// Precision pinch with a double pad tap while closed.
const PINCH_TAP = fingerPose(
  { index: [-5, -7, -4], middle: [0, 0, 0], ring: [0, 0, 0], pinky: [0, 0, 0] },
  [0, 0, -7, -5],
);

function pinchPose(phase) {
  const p = wrap01(phase);
  if (p < 0.3) return blendPoses(POSES.relaxed, POSES.precision_pinch, p / 0.3);
  if (p < 0.72) {
    const tap = Math.sin(2 * Math.PI * 2 * ((p - 0.3) / 0.42));
    return addScaled(POSES.precision_pinch, PINCH_TAP, Math.max(0, tap));
  }
  return blendPoses(POSES.precision_pinch, POSES.relaxed, (p - 0.72) / 0.28);
}

// Traveling curl wave: each digit pulses inside its own window (raised cosine,
// zero at both ends), thumb last. The windows are wide relative to the digit
// spacing, so each digit starts curling while its neighbour is still mid-pulse
// and the wave reads as one continuous motion.
const RIPPLE_ORDER = ["index", "middle", "ring", "pinky", "thumb"];
const RIPPLE_CURL = { mcp: 30, pip: 40, dip: 22, thumbFlex: 12, thumbMp: 30, thumbIp: 30 };
const RIPPLE_WINDOW = 0.45;

function ripplePose(phase, grip) {
  const p = wrap01(phase);
  const step = (1 - RIPPLE_WINDOW) / (RIPPLE_ORDER.length - 1);
  const pose = {};
  for (const joint of JOINTS) pose[joint.name] = BAKED_POSE[joint.name];
  RIPPLE_ORDER.forEach((digit, i) => {
    const u = (p - i * step) / RIPPLE_WINDOW;
    if (u <= 0 || u >= 1) return;
    const lobe = Math.sin(Math.PI * u);
    const amp = lobe * lobe * grip;
    if (digit === "thumb") {
      pose.thumb_cmc_flex += RIPPLE_CURL.thumbFlex * amp;
      pose.thumb_mp += RIPPLE_CURL.thumbMp * amp;
      pose.thumb_ip += RIPPLE_CURL.thumbIp * amp;
    } else {
      pose[`${digit}_mcp`] += RIPPLE_CURL.mcp * amp;
      pose[`${digit}_pip`] += RIPPLE_CURL.pip * amp;
      pose[`${digit}_dip`] += RIPPLE_CURL.dip * amp;
    }
  });
  return pose;
}

// Count 1..5 from a fist (index first, thumb last), then close back. The thumb
// lifts to a hover clear of the fingers before any finger extends, and only
// re-wraps once the fingers are curled again — every adjacent blend is
// capsule-verified collision-free.
const COUNT_EXTENDED = { index: [2, 2, 1], middle: [2, 2, 1], ring: [4, 4, 2], pinky: [6, 6, 3] };
const COUNT_THUMB_FIST = [92, 13, 58, 74];
const COUNT_THUMB_HOVER = [50, 30, 25, 20];
const COUNT_THUMB_OPEN = [20, 10, 4, 4];

function countKey(step, thumb) {
  const curls = {};
  FINGERS.forEach((finger, i) => {
    curls[finger] = step >= i + 1 ? COUNT_EXTENDED[finger] : [78, 100, 60];
  });
  return fingerPose(curls, thumb);
}

// 8 segments: fist -> thumb hover -> 1 -> 2 -> 3 -> 4 -> 5 (thumb opens) ->
// hover (fingers re-curl) -> wrap back to the fist.
const COUNT_KEYS = [
  countKey(0, COUNT_THUMB_FIST),
  countKey(0, COUNT_THUMB_HOVER),
  countKey(1, COUNT_THUMB_HOVER),
  countKey(2, COUNT_THUMB_HOVER),
  countKey(3, COUNT_THUMB_HOVER),
  countKey(4, COUNT_THUMB_HOVER),
  countKey(5, COUNT_THUMB_OPEN),
  countKey(0, COUNT_THUMB_HOVER),
];

function countPose(phase) {
  const p = wrap01(phase);
  const segCount = COUNT_KEYS.length;
  const seg = Math.min(Math.floor(p * segCount), segCount - 1);
  const u = p * segCount - seg;
  const to = seg + 1 < segCount ? COUNT_KEYS[seg + 1] : COUNT_KEYS[0];
  return blendPoses(COUNT_KEYS[seg], to, u / 0.6);
}

export const clips = {
  poseTour: {
    label: "Pose tour",
    duration: 11.5,
    loop: true,
    update(t, m) {
      apply(m, tourPose(t / 11.5));
    },
  },
  graspLoop: {
    label: "Power grasp",
    duration: 2.6,
    loop: true,
    update(t, m) {
      apply(m, graspPose(t / 2.6, 1));
    },
  },
  pinchLoop: {
    label: "Precision pinch",
    duration: 2.8,
    loop: true,
    update(t, m) {
      apply(m, pinchPose(t / 2.8));
    },
  },
  rippleLoop: {
    label: "Finger ripple",
    duration: 2.6,
    loop: true,
    update(t, m) {
      apply(m, ripplePose(t / 2.6, 1));
    },
  },
  countLoop: {
    label: "Count to five",
    duration: 7.0,
    loop: true,
    update(t, m) {
      apply(m, countPose(t / 7.0));
    },
  },
};

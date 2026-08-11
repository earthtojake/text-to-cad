// Pose articulation animations for the lyra dexterous-hand STEP assembly.
//
// The STEP geometry is baked in the "relaxed" pose (see lyra.py /
// lyra_parts/chain.py). This module recomputes full-chain FK each frame at
// the target pose and applies, per link, the rigid delta matrix
// T_target * inverse(T_relaxed) in the fixed model frame (mm, RIGHT hand,
// +Z distal, +Y palmar, +X radial, wrist-flange face center at the origin).
//
// All pose tables mirror lyra_parts/chain.py named_poses_deg(); the joint
// list mirrors chain.all_joints() (origins mm in the parent link frame,
// axes: finger flexion about -X, thumb cmc yaw about +Z, thumb flexion
// about -Y). Poses are blended in joint space with smoothstep easing —
// every intermediate state of a serial digit chain is itself a valid pose,
// so blends never break the mechanism. Every loop starts and ends on the
// exact pose it began with.

const FINGERS = ["index", "middle", "ring", "pinky"];

// Chain offsets (mm), mirrored from lyra_parts/chain.py.
const MCP = {
  index: [28.5, 0, 99],
  middle: [9.5, 0, 103],
  ring: [-9.5, 0, 99],
  pinky: [-28.5, 0, 90]
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
      { name: `${finger}_dip`, parent: `${finger}_middle`, child: `${finger}_distal`, origin: [0, 0, SEG[finger][1]], axis: NEG_X }
    );
  }
  joints.push(
    { name: "thumb_cmc_yaw", parent: "palm", child: "thumb_base", origin: THUMB_CMC, axis: Z },
    { name: "thumb_cmc_flex", parent: "thumb_base", child: "thumb_metacarpal", origin: [THUMB_BASE_LEN, 0, 0], axis: NEG_Y },
    { name: "thumb_mp", parent: "thumb_metacarpal", child: "thumb_proximal", origin: [THUMB_METACARPAL_LEN, 0, 0], axis: NEG_Y },
    { name: "thumb_ip", parent: "thumb_proximal", child: "thumb_distal", origin: [THUMB_PROXIMAL_LEN, 0, 0], axis: NEG_Y }
  );
  return joints;
}

const JOINTS = buildJoints();

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
    [0, 0, 0, 0]
  ),
  relaxed: fingerPose(
    { index: [10, 14, 8], middle: [12, 16, 9], ring: [14, 18, 10], pinky: [16, 20, 12] },
    [34, 26, 14, 12]
  ),
  fist: fingerPose(
    { index: [78, 100, 60], middle: [78, 100, 60], ring: [78, 100, 60], pinky: [78, 100, 60] },
    [92, 13, 58, 74]
  ),
  precision_pinch: fingerPose(
    { index: [40, 48, 30], middle: [66, 92, 55], ring: [66, 92, 55], pinky: [66, 92, 55] },
    [91, 34, 29, 8]
  ),
  tripod_pinch: fingerPose(
    { index: [44, 52, 32], middle: [42, 50, 30], ring: [66, 92, 55], pinky: [66, 92, 55] },
    [100, 39, 0, 14]
  ),
  point: fingerPose(
    { index: [-6, 0, 0], middle: [80, 102, 62], ring: [80, 102, 62], pinky: [80, 102, 62] },
    [62, 30, 42, 45]
  ),
  ok_sign: fingerPose(
    { index: [42, 52, 32], middle: [6, 8, 4], ring: [10, 12, 6], pinky: [14, 16, 8] },
    [91, 26, 35, 20]
  )
};

const BAKED_POSE = POSES.relaxed;

// ------------------------------------------------------------- math kit
function finite(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(finite(value, min), min), max);
}

function smoothstep(u) {
  const t = clamp(u, 0, 1);
  return t * t * (3 - 2 * t);
}

// Rodrigues rotation about a unit axis (covers -X, -Y, and Z here).
function rotAxisDeg(axis, deg) {
  const rad = (deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const t = 1 - c;
  const [ax, ay, az] = axis;
  return [
    [c + ax * ax * t, ax * ay * t - az * s, ax * az * t + ay * s],
    [ay * ax * t + az * s, c + ay * ay * t, ay * az * t - ax * s],
    [az * ax * t - ay * s, az * ay * t + ax * s, c + az * az * t]
  ];
}

function matMul3(a, b) {
  const out = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let i = 0; i < 3; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      out[i][j] = (a[i][0] * b[0][j]) + (a[i][1] * b[1][j]) + (a[i][2] * b[2][j]);
    }
  }
  return out;
}

function matVec3(a, v) {
  return [
    (a[0][0] * v[0]) + (a[0][1] * v[1]) + (a[0][2] * v[2]),
    (a[1][0] * v[0]) + (a[1][1] * v[1]) + (a[1][2] * v[2]),
    (a[2][0] * v[0]) + (a[2][1] * v[1]) + (a[2][2] * v[2])
  ];
}

function matTranspose3(a) {
  return [
    [a[0][0], a[1][0], a[2][0]],
    [a[0][1], a[1][1], a[2][1]],
    [a[0][2], a[1][2], a[2][2]]
  ];
}

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

// Row-major 4x4 mapping the baked placement of a link onto its target
// placement: M = [R_t R_o^T | p_t - R_t R_o^T p_o].
function deltaMatrixRowMajor(original, target) {
  const Rd = matMul3(target.R, matTranspose3(original.R));
  const moved = matVec3(Rd, original.p);
  const t = [target.p[0] - moved[0], target.p[1] - moved[1], target.p[2] - moved[2]];
  return [
    Rd[0][0], Rd[0][1], Rd[0][2], t[0],
    Rd[1][0], Rd[1][1], Rd[1][2], t[1],
    Rd[2][0], Rd[2][1], Rd[2][2], t[2],
    0, 0, 0, 1
  ];
}

function blendPoses(a, b, u) {
  const e = smoothstep(u);
  const out = {};
  for (const joint of JOINTS) {
    out[joint.name] = finite(a[joint.name], 0) + ((finite(b[joint.name], 0) - finite(a[joint.name], 0)) * e);
  }
  return out;
}

function addScaled(pose, delta, scale) {
  const out = {};
  for (const joint of JOINTS) {
    out[joint.name] = finite(pose[joint.name], 0) + (finite(delta[joint.name], 0) * scale);
  }
  return out;
}

// ---------------------------------------------------------------- modes
// Keyframe cycle through the showpiece poses; each segment blends for 65%
// of its window and dwells for 35%, and the cycle wraps back to its first
// key so the loop is exact. Key order is chosen so every adjacent blend is
// capsule-verified collision-free (the fist only neighbors tripod/relaxed;
// blending it with pinch/point/ok would sweep the thumb through the index).
const TOUR_KEYS = ["relaxed", "precision_pinch", "ok_sign", "point", "tripod_pinch", "fist"];
// The tour opens with one finger-ripple wave (starts and ends exactly on
// the relaxed pose, so it splices seamlessly before the first keyframe
// blend) and spends the rest of the cycle on the pose keyframes.
const TOUR_RIPPLE_FRAC = 0.22;

function tourPose(phase) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  if (p < TOUR_RIPPLE_FRAC) {
    return ripplePose(p / TOUR_RIPPLE_FRAC, 1);
  }
  const q = (p - TOUR_RIPPLE_FRAC) / (1 - TOUR_RIPPLE_FRAC);
  const segCount = TOUR_KEYS.length;
  const seg = Math.min(Math.floor(q * segCount), segCount - 1);
  const u = (q * segCount) - seg;
  const from = POSES[TOUR_KEYS[seg]];
  const to = POSES[TOUR_KEYS[(seg + 1) % segCount]];
  return blendPoses(from, to, u / 0.65);
}

// Open-close power grasp: relaxed -> fist -> relaxed on a raised cosine.
function graspPose(phase, grip) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  const wave = 0.5 * (1 - Math.cos(2 * Math.PI * p));
  return blendPoses(POSES.relaxed, POSES.fist, wave * grip);
}

// Precision pinch with a double pad tap while closed.
const PINCH_TAP = fingerPose(
  { index: [-5, -7, -4], middle: [0, 0, 0], ring: [0, 0, 0], pinky: [0, 0, 0] },
  [0, 0, -7, -5]
);

function pinchPose(phase) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  if (p < 0.3) {
    return blendPoses(POSES.relaxed, POSES.precision_pinch, p / 0.3);
  }
  if (p < 0.72) {
    const u = (p - 0.3) / 0.42;
    const tap = Math.sin(2 * Math.PI * 2 * u);
    return addScaled(POSES.precision_pinch, PINCH_TAP, Math.max(0, tap));
  }
  return blendPoses(POSES.precision_pinch, POSES.relaxed, (p - 0.72) / 0.28);
}

// Traveling curl wave: each digit pulses inside its own window (raised
// cosine, zero at both ends), thumb last. The windows are wide relative to
// the digit spacing, so each digit starts curling while its neighbor is
// still mid-pulse and the wave reads as one continuous motion.
const RIPPLE_ORDER = ["index", "middle", "ring", "pinky", "thumb"];
const RIPPLE_CURL = { mcp: 30, pip: 40, dip: 22, thumbFlex: 12, thumbMp: 30, thumbIp: 30 };
const RIPPLE_WINDOW = 0.45;

function ripplePose(phase, grip) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  const window = RIPPLE_WINDOW;
  const step = (1 - window) / (RIPPLE_ORDER.length - 1);
  const pose = {};
  for (const joint of JOINTS) {
    pose[joint.name] = BAKED_POSE[joint.name];
  }
  RIPPLE_ORDER.forEach((digit, i) => {
    const start = i * step;
    const u = (p - start) / window;
    if (u <= 0 || u >= 1) {
      return;
    }
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

// Count 1..5 from a fist (index first, thumb last), then close back. The
// thumb lifts off to a hover clear of the fingers before any finger
// extends, and only re-wraps once the fingers are curled again — every
// adjacent blend is capsule-verified collision-free.
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

function countPose(phase) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  // 8 segments: fist -> thumb hover -> 1 -> 2 -> 3 -> 4 -> 5 (thumb opens)
  // -> hover (fingers re-curl) -> wrap back to the fist.
  const keys = [
    countKey(0, COUNT_THUMB_FIST),
    countKey(0, COUNT_THUMB_HOVER),
    countKey(1, COUNT_THUMB_HOVER),
    countKey(2, COUNT_THUMB_HOVER),
    countKey(3, COUNT_THUMB_HOVER),
    countKey(4, COUNT_THUMB_HOVER),
    countKey(5, COUNT_THUMB_OPEN),
    countKey(0, COUNT_THUMB_HOVER)
  ];
  const segCount = keys.length;
  const seg = Math.min(Math.floor(p * segCount), segCount - 1);
  const u = (p * segCount) - seg;
  const from = keys[seg];
  const to = seg + 1 < segCount ? keys[seg + 1] : keys[0];
  return blendPoses(from, to, u / 0.6);
}

const FEATURE_BY_LINK = {
  palm: "palm",
  index_proximal: "indexProximal",
  index_middle: "indexMiddle",
  index_distal: "indexDistal",
  middle_proximal: "middleProximal",
  middle_middle: "middleMiddle",
  middle_distal: "middleDistal",
  ring_proximal: "ringProximal",
  ring_middle: "ringMiddle",
  ring_distal: "ringDistal",
  pinky_proximal: "pinkyProximal",
  pinky_middle: "pinkyMiddle",
  pinky_distal: "pinkyDistal",
  thumb_base: "thumbBase",
  thumb_metacarpal: "thumbMetacarpal",
  thumb_proximal: "thumbProximal",
  thumb_distal: "thumbDistal"
};

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/renders/lyra/lyra.step"
    },
    label: "lyra dexterous hand",
    description: "16-DOF humanoid right hand: pose tour, power grasp, precision pinch with pad taps, finger ripple, and counting, all driven by per-frame chain FK against the baked relaxed pose.",
    units: {
      length: "mm",
      angle: "deg",
      time: "s"
    },
    features: {
      palm: { ref: "#o1.1", label: "Palm", description: "Root link; static during all hand animations." },
      indexProximal: { ref: "#o1.2", label: "Index proximal" },
      indexMiddle: { ref: "#o1.3", label: "Index middle" },
      indexDistal: { ref: "#o1.4", label: "Index distal" },
      middleProximal: { ref: "#o1.5", label: "Middle proximal" },
      middleMiddle: { ref: "#o1.6", label: "Middle middle" },
      middleDistal: { ref: "#o1.7", label: "Middle distal" },
      ringProximal: { ref: "#o1.8", label: "Ring proximal" },
      ringMiddle: { ref: "#o1.9", label: "Ring middle" },
      ringDistal: { ref: "#o1.10", label: "Ring distal" },
      pinkyProximal: { ref: "#o1.11", label: "Pinky proximal" },
      pinkyMiddle: { ref: "#o1.12", label: "Pinky middle" },
      pinkyDistal: { ref: "#o1.13", label: "Pinky distal" },
      thumbBase: { ref: "#o1.14", label: "Thumb CMC base" },
      thumbMetacarpal: { ref: "#o1.15", label: "Thumb metacarpal" },
      thumbProximal: { ref: "#o1.16", label: "Thumb proximal" },
      thumbDistal: { ref: "#o1.17", label: "Thumb distal" }
    },
    parameters: {
      phase: {
        type: "number",
        label: "Cycle phase",
        description: "One full cycle of the active mode; the animations drive this 0 -> 1.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.001
      },
      mode: {
        type: "select",
        label: "Mode",
        description: "Which articulation cycle the phase scrubs. Each animation drives the matching mode; 'pose' holds the static pose picked below.",
        default: "tour",
        options: [
          { value: "tour", label: "Pose tour" },
          { value: "grasp", label: "Power grasp" },
          { value: "pinch", label: "Precision pinch" },
          { value: "ripple", label: "Finger ripple" },
          { value: "count", label: "Count to five" },
          { value: "pose", label: "Hold named pose" }
        ]
      },
      pose: {
        type: "select",
        label: "Named pose",
        description: "SRDF group-state pose held when mode is 'pose' (blend with Grip).",
        default: "relaxed",
        options: [
          { value: "zero", label: "Zero (flat open)" },
          { value: "relaxed", label: "Relaxed (baked)" },
          { value: "fist", label: "Fist" },
          { value: "precision_pinch", label: "Precision pinch" },
          { value: "tripod_pinch", label: "Tripod pinch" },
          { value: "point", label: "Point" },
          { value: "ok_sign", label: "OK sign" }
        ]
      },
      grip: {
        type: "number",
        label: "Grip",
        description: "Scales the grasp/ripple amplitude, and blends relaxed -> named pose in 'pose' mode.",
        default: 1,
        min: 0,
        max: 1,
        step: 0.01
      }
    },
    animations: {
      poseTour: {
        label: "Pose tour",
        description: "Opens with a finger ripple wave, then cycles relaxed -> precision pinch -> OK sign -> point -> tripod pinch -> fist and back, dwelling on each pose.",
        duration: 11.5,
        loop: true,
        update({ cycle, set }) {
          set("mode", "tour");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      graspLoop: {
        label: "Power grasp",
        description: "Full-hand open-close: all four fingers wrap and the thumb locks over them, then releases back to the relaxed pose.",
        duration: 2.6,
        loop: true,
        update({ cycle, set }) {
          set("mode", "grasp");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      pinchLoop: {
        label: "Precision pinch",
        description: "Thumb-index pad opposition with a double tap while closed; the other fingers curl clear.",
        duration: 2.8,
        loop: true,
        update({ cycle, set }) {
          set("mode", "pinch");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      rippleLoop: {
        label: "Finger ripple",
        description: "A curl wave travels index -> pinky and hands off to the thumb, like drumming fingers in the air.",
        duration: 2.6,
        loop: true,
        update({ cycle, set }) {
          set("mode", "ripple");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      countLoop: {
        label: "Count to five",
        description: "From a fist: the thumb lifts clear, then index, middle, ring, pinky extend in turn and the thumb opens to a flat five before the hand closes again.",
        duration: 7.0,
        loop: true,
        update({ cycle, set }) {
          set("mode", "count");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      }
    }
  },

  update({ params, effects }) {
    const phase = ((finite(params.phase, 0) % 1) + 1) % 1;
    const grip = clamp(params.grip, 0, 1);
    const mode = String(params.mode || "tour");
    let target;
    if (mode === "grasp") {
      target = graspPose(phase, grip);
    } else if (mode === "pinch") {
      target = pinchPose(phase);
    } else if (mode === "ripple") {
      target = ripplePose(phase, grip);
    } else if (mode === "count") {
      target = countPose(phase);
    } else if (mode === "pose") {
      const named = POSES[String(params.pose || "relaxed")] || POSES.relaxed;
      target = blendPoses(POSES.relaxed, named, grip);
    } else {
      target = tourPose(phase);
    }

    const targetFrames = fkFrames(target);
    for (const [link, feature] of Object.entries(FEATURE_BY_LINK)) {
      effects.transform(feature, {
        matrix: deltaMatrixRowMajor(BAKED_FRAMES[link], targetFrames[link])
      });
    }
  }
};

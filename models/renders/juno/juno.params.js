// Walking-in-place animation for the juno humanoid STEP assembly.
//
// The STEP geometry is baked in the athletic ready stance (see juno.py /
// juno_parts/chain.py). This module recomputes full-chain FK each frame at
// (athletic pose + gait deltas) and applies, per link subtree, the rigid
// delta matrix T_target * inverse(T_athletic) in the fixed model frame
// (mm, +X forward, +Y robot-left, +Z up, pelvis waist-yaw center at the
// origin).
//
// Gait design: an in-place march. Each leg swings inside its own window of
// the cycle with a raised-cosine envelope that starts and ends at zero, and
// is EXACTLY at the athletic pose for the rest of the cycle — so the stance
// foot stays planted on the ground with no IK. The pelvis root is
// intentionally static for the same reason. Arms swing continuously,
// antiphase to their own-side leg; the torso counter-rotates about the
// waist with a hint of roll, and the neck compensates so the head keeps
// facing forward.

const X = [1, 0, 0];
const Y = [0, 1, 0];
const Z = [0, 0, 1];

const HIP_Y = 90;
const SHOULDER_Y = 148;

// Athletic ready stance angles (deg), mirrored from juno_parts/chain.py.
const ATHLETIC = {
  HIP_PITCH: -16,
  KNEE: 32,
  ANKLE_PITCH: -16,
  HIP_ROLL_ABDUCT: 3,
  HIP_YAW: 0,
  WAIST_YAW: 0,
  SHOULDER_PITCH: -8,
  SHOULDER_ROLL_ABDUCT: 8,
  SHOULDER_YAW_INTERNAL: 8,
  ELBOW: -20,
  WRIST_ROLL: 0,
  WRIST_PITCH: -2,
  NECK_YAW: 0,
  NECK_PITCH: -2
};

// Gait amplitudes (deg) at parameter scale 1. Sign conventions follow the
// chain ledger: pitch about +Y (negative = forward), roll about +X
// (positive = toward robot-left), yaw about +Z (positive = turn left).
const HIP_LIFT_DEG = 24;        // swing-leg thigh raise (forward = negative pitch)
const KNEE_FOLD_DEG = 44;       // extra swing-leg knee flexion
const TOE_POINT_DEG = 8;        // slight toes-down of the airborne foot
const ARM_SWING_DEG = 12;       // shoulder pitch swing, antiphase to own-side leg
const ELBOW_EXTRA_DEG = 10;     // extra elbow flexion on the forward arm swing
const WAIST_SWAY_DEG = 4;       // torso counter-rotation about the waist yaw axis
const TORSO_ROLL_DEG = 1.2;     // weight-shift hint, roll about +X at the waist
const NECK_COMPENSATION = 0.8;  // head stabilization fraction against waist sway

// Swing windows of the normalized cycle (left lifts first), with
// double-support dwell between them.
const SWING = { left: [0.05, 0.45], right: [0.55, 0.95] };

// Stride gait (treadmill-style walk in place): the stance foot slides
// backward flat on the ground while the swing leg passes through the air,
// both solved with planar two-link leg IK in each leg's (slightly rolled)
// sagittal plane. The athletic stance is exactly the IK solution at stride
// center, so the gait converges to plain standing as strideLength -> 0.
const THIGH_LEN = 290;            // hip-pitch to knee (mm)
const SHIN_LEN = 290;             // knee to ankle-pitch (mm)
const STANCE_FRACTION = 0.58;     // ground-contact share of each leg cycle
const STRIDE_LIFT_MM = 60;        // swing-foot apex clearance at legLift 1
const STRIDE_TOE_OFF_DEG = 14;    // toes-down just after toe-off
const STRIDE_HEEL_DEG = 10;       // toes-up heel-first approach to contact
const STRIDE_ARM_FACTOR = 1.5;    // arms swing wider with long strides
const STRIDE_SWAY_FACTOR = 1.25;
const MAX_STRIDE_MM = 300;        // keeps two-link IK inside reach at the extremes
const DEFAULT_STRIDE_MM = 230;    // lift/pitch accents are normalized to this
const STRIDE_PHASE = { left: 0, right: 0.5 };
// Mid-swing cycle positions (offset + stance + half the swing window).
const STRIDE_MID_SWING = {
  left: (STRIDE_PHASE.left + STANCE_FRACTION + ((1 - STANCE_FRACTION) / 2)) % 1,
  right: (STRIDE_PHASE.right + STANCE_FRACTION + ((1 - STANCE_FRACTION) / 2)) % 1
};

// Run gait: short ground contacts with a FLIGHT phase between them (both
// feet airborne), a vertical body bounce absorbed by the stance-leg IK
// (lowest at mid-stance, highest at mid-flight), toe-pivot heel-off into
// push-off, high heel-recovery swing, forward torso lean, and pumping bent
// arms. Foot contact lands slightly ahead of the hip and pushes off well
// behind it (asymmetric split of the stride travel).
const RUN_STANCE_FRACTION = 0.35;
const RUN_PHASE = { left: 0, right: 0.5 };
const RUN_MID_STANCE = {
  left: RUN_STANCE_FRACTION / 2,
  right: (RUN_PHASE.right + (RUN_STANCE_FRACTION / 2)) % 1
};
const RUN_MID_SWING = {
  left: (RUN_STANCE_FRACTION + ((1 - RUN_STANCE_FRACTION) / 2)) % 1,
  right: (RUN_PHASE.right + RUN_STANCE_FRACTION + ((1 - RUN_STANCE_FRACTION) / 2)) % 1
};
const RUN_CONTACT_SHARE = 0.3;    // stride share landing ahead of the hip
const RUN_BOUNCE_MM = 22;         // body bounce amplitude at legLift 1
const RUN_APEX_MM = 140;          // swing-ankle apex over flat stance (heel tuck)
const RUN_HEEL_OFF_DEG = 26;      // toe-pivot heel rise into push-off
const RUN_HEEL_OFF_START = 0.62;  // stance progress where the heel starts rising
const RUN_HEEL_IN_DEG = 8;        // toes-up into the next contact
const RUN_TOE_PIVOT_X_MM = 112;   // sole front edge (foot bbox +x) — pivoting
const RUN_ANKLE_HEIGHT_MM = 56;   // there keeps the toe from digging in
const RUN_LEAN_DEG = 7;           // forward torso lean (waist pitch extra)
const RUN_ARM_SWING_DEG = 26;     // shoulder pump amplitude
const RUN_ELBOW_BASE_DEG = -60;   // extra constant elbow flexion (runner's arms)
const RUN_ELBOW_PUMP_DEG = 15;    // extra flexion on the forward pump
const RUN_SWAY_DEG = 5;           // waist yaw counter-rotation
const RUN_ROLL_DEG = 1.6;         // lean toward the stance side

// Jump gait: countermovement crouch -> push -> ballistic flight with toe
// point and leg tuck -> springy landing (underdamped body-height response
// absorbed by the leg IK) -> recover. Arms swing back in the crouch, sweep
// overhead for the flight ("hands in the air"), dip with the landing
// spring, and settle back. Both legs work symmetrically; takeoff/landing
// fall out of the IK reach clamp (targets go out of reach -> legs straight
// -> feet leave/meet the ground smoothly).
const JUMP_TIMING = { crouch: 0.18, push: 0.3, land: 0.62, absorb: 0.74 };
const JUMP_CROUCH_MM = 120;       // countermovement depth at legLift 1
const JUMP_TAKEOFF_MM = 20;       // body rise at full leg extension (reach limit)
const JUMP_APEX_MM = 160;         // ballistic apex above standing at legLift 1
const JUMP_TUCK_MM = 250;         // mid-flight ankle tuck toward the body
const JUMP_TOE_POINT_DEG = 25;    // toes point down in the air
const JUMP_LAND_DIP_MM = -80;     // first landing compression
const JUMP_SPRING_DECAY = 3.5;    // landing spring: exp decay rate ...
const JUMP_SPRING_CYCLES = 1.25;  // ... and bounce count (ends at zero crossing)
const JUMP_ARM_BACK_DEG = 30;     // crouch arm backswing (shoulder pitch)
const JUMP_ARM_UP_DEG = -155;     // overhead shoulder pitch in flight
const JUMP_ARM_V_DEG = 20;        // shoulder roll abduction for an overhead V
const JUMP_ARM_SPRING_DEG_PER_MM = 0.3; // landing arm dip coupled to body spring
const JUMP_LEAN_DEG = 8;          // crouch/landing forward lean
const JUMP_HEAD_UP_DEG = -8;      // look up slightly while airborne

// Showpiece animations: karate kick, handstand, and the Elvis dance each
// run as their own loop; every one starts and ends in the athletic stance.
// Lateral pendulum for weight shifts: the hip-roll joint sits at z=-184 in
// the pelvis frame; rolling there (with the ankle roll compensating) moves
// the planted sole sideways by ~(soleZ - HIP_ROLL_Z) * sin(roll).
const HIP_ROLL_Z_MM = -184;
// Kick (segment-local): weight shifts over the left leg, the right leg
// chambers and snaps a front kick at hip height with a guard up.
const KICK_WEIGHT_SHIFT_MM = 42;
const KICK_DIP_MM = 18;
const KICK_CHAMBER_HIP_DEG = -70;
const KICK_CHAMBER_KNEE_DEG = 115;
const KICK_CHAMBER_ANKLE_DEG = 10;
const KICK_EXTEND_HIP_DEG = -20;   // added on top of the chamber
const KICK_EXTEND_KNEE_DEG = -105; // snaps the shin out nearly straight
const KICK_EXTEND_ANKLE_DEG = -25; // ball-of-foot strike (toes pulled back)
const KICK_GUARD_SHOULDER_DEG = -45;
const KICK_GUARD_ELBOW_DEG = -105;
const KICK_GUARD_ROLL_OUT_DEG = 18;
const KICK_HIP_TURN_DEG = -14;     // hips rotate into the kick
const KICK_LEAN_BACK_DEG = -7;     // counterbalance during the snap
// Handstand: keyframed root rotation about +Y with contact anchoring —
// toe-pinned while folding, palm-pinned once the hands plant.
const HS_PLANT_X_MM = 430;         // hand plant line in front of the feet
// Palm contact point in the hand frame: the hands plant palm-down with the
// fingers pointing forward (total hand pitch -90 at the hold), so contact
// is on the local -x palm face — the one extent that is symmetric between
// the two hands (the posed finger curl differs in local z).
const HS_PALM_LOCAL_MM = [-35, 0, -70];
const HS_TOE_LOCAL_MM = [112, 0, -26]; // sole FRONT EDGE (pivoting there keeps the whole sole above ground)
const HS_WOBBLE_DEG = 1.6;         // leg wobble while holding the stand
// Elvis dance (4 beats): weight over the right leg, left leg kicked out
// to the left planted on a pointed toe (closed-form lateral+sagittal leg
// IK), rubber-leg shake, right arm pointing up to the right with a beat
// pulse, hip swivel, head turned toward the pointing hand.
const ELVIS_BEATS = 4;
const ELVIS_WEIGHT_SHIFT_MM = -55;   // pelvis shifts over the right leg
const ELVIS_DIP_MM = 20;             // settled crouch on the stance leg
const ELVIS_BOUNCE_MM = 8;           // beat bounce on top of the dip
const ELVIS_TOE_X_MM = 80;           // kicked-out toe plant, forward of the hips
const ELVIS_TOE_Y_MM = 330;          // ... and out to the robot-left
const ELVIS_TOE_SHAKE_MM = 28;       // rubber-leg lateral toe shake (2x beat)
const ELVIS_FOOT_POINT_DEG = 55;     // pointed toe of the kicked-out foot
const ELVIS_FOOT_POINT_SHAKE_DEG = 7;
const ELVIS_TOE_TIP_LOCAL = { x: 112, drop: 56 }; // toe tip rel ankle-pitch (fwd, down)
const ELVIS_POINT_ROLL_DEG = -115;   // right arm raised out-and-up to the right
const ELVIS_POINT_PITCH_DEG = -25;
const ELVIS_POINT_ELBOW_DEG = -12;   // nearly straight: the finger points
const ELVIS_POINT_PULSE_DEG = 8;     // beat pulse of the pointing arm
const ELVIS_OFF_ARM_PITCH_DEG = -30; // left arm low and bent across
const ELVIS_OFF_ARM_ELBOW_DEG = -70;
const ELVIS_TWIST_DEG = 10;          // hip swivel via the waist
const ELVIS_LEAN_RIGHT_DEG = -3;     // lean into the point
const ELVIS_HEAD_TURN_DEG = -20;     // look toward the pointing hand
const ELVIS_CHIN_UP_DEG = -5;

const SIDES = ["left", "right"];

function sideSign(side) {
  return side === "left" ? 1 : -1;
}

// Kinematic chain in root-to-leaf order, mirrored from juno_parts/chain.py.
// origin is the joint center in the parent link frame (mm); each child link
// frame sits at its joint center.
function buildJoints() {
  const joints = [
    { name: "waist_yaw", parent: "pelvis", child: "torso", origin: [0, 0, 0], axis: Z },
    { name: "neck_yaw", parent: "torso", child: "neck_collar", origin: [0, 0, 324], axis: Z },
    { name: "neck_pitch", parent: "neck_collar", child: "head", origin: [0, 0, 46], axis: Y }
  ];
  for (const side of SIDES) {
    const s = sideSign(side);
    joints.push(
      { name: `hip_yaw_${side}`, parent: "pelvis", child: `hip_bracket_${side}`, origin: [0, s * HIP_Y, -120], axis: Z },
      { name: `hip_roll_${side}`, parent: `hip_bracket_${side}`, child: `hip_carrier_${side}`, origin: [0, 0, -64], axis: X },
      { name: `hip_pitch_${side}`, parent: `hip_carrier_${side}`, child: `thigh_${side}`, origin: [0, 0, -78], axis: Y },
      { name: `knee_${side}`, parent: `thigh_${side}`, child: `shin_${side}`, origin: [0, 0, -290], axis: Y },
      { name: `ankle_pitch_${side}`, parent: `shin_${side}`, child: `ankle_link_${side}`, origin: [0, 0, -290], axis: Y },
      { name: `ankle_roll_${side}`, parent: `ankle_link_${side}`, child: `foot_${side}`, origin: [0, 0, -30], axis: X }
    );
  }
  for (const side of SIDES) {
    const s = sideSign(side);
    joints.push(
      { name: `shoulder_pitch_${side}`, parent: "torso", child: `shoulder_pod_${side}`, origin: [0, s * SHOULDER_Y, 290], axis: Y },
      { name: `shoulder_roll_${side}`, parent: `shoulder_pod_${side}`, child: `yaw_housing_${side}`, origin: [0, s * 34, -72], axis: X },
      { name: `shoulder_yaw_${side}`, parent: `yaw_housing_${side}`, child: `bicep_${side}`, origin: [0, 0, -24], axis: Z },
      { name: `elbow_${side}`, parent: `bicep_${side}`, child: `forearm_${side}`, origin: [0, 0, -156], axis: Y },
      { name: `wrist_roll_${side}`, parent: `forearm_${side}`, child: `wrist_carrier_${side}`, origin: [0, 0, -150], axis: Z },
      { name: `wrist_pitch_${side}`, parent: `wrist_carrier_${side}`, child: `hand_${side}`, origin: [0, 0, -28], axis: Y }
    );
  }
  return joints;
}

const JOINTS = buildJoints();

// Optional artistic extras applied on top of joint FK, keyed by joint name:
// { rollDeg } adds a small rotation about +X at the same joint center.
function athleticAnglesDeg() {
  const angles = {
    waist_yaw: ATHLETIC.WAIST_YAW,
    neck_yaw: ATHLETIC.NECK_YAW,
    neck_pitch: ATHLETIC.NECK_PITCH
  };
  for (const side of SIDES) {
    const s = sideSign(side);
    angles[`hip_yaw_${side}`] = ATHLETIC.HIP_YAW;
    angles[`hip_roll_${side}`] = s * ATHLETIC.HIP_ROLL_ABDUCT;
    angles[`hip_pitch_${side}`] = ATHLETIC.HIP_PITCH;
    angles[`knee_${side}`] = ATHLETIC.KNEE;
    angles[`ankle_pitch_${side}`] = ATHLETIC.ANKLE_PITCH;
    angles[`ankle_roll_${side}`] = -s * ATHLETIC.HIP_ROLL_ABDUCT;
    angles[`shoulder_pitch_${side}`] = ATHLETIC.SHOULDER_PITCH;
    angles[`shoulder_roll_${side}`] = s * ATHLETIC.SHOULDER_ROLL_ABDUCT;
    angles[`shoulder_yaw_${side}`] = -s * ATHLETIC.SHOULDER_YAW_INTERNAL;
    angles[`elbow_${side}`] = ATHLETIC.ELBOW;
    angles[`wrist_roll_${side}`] = ATHLETIC.WRIST_ROLL;
    angles[`wrist_pitch_${side}`] = ATHLETIC.WRIST_PITCH;
  }
  return angles;
}

const ATHLETIC_ANGLES = athleticAnglesDeg();

function finite(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(finite(value, min), min), max);
}

const IDENTITY3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];

function rotAxisDeg(axis, deg) {
  const rad = (deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  if (axis === X) {
    return [[1, 0, 0], [0, c, -s], [0, s, c]];
  }
  if (axis === Y) {
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]];
  }
  return [[c, -s, 0], [s, c, 0], [0, 0, 1]];
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

// FK over the whole chain. extras[jointName] = { pitchDeg, rollDeg } folds
// small artistic +Y/+X rotations in at that joint center (torso lean and
// weight shift); rootOffset translates the pelvis (body bounce in the air
// gaits — the stance-leg IK absorbs it on the ground side); rootPitchDeg
// rotates the whole body about +Y at the pelvis (handstand inversion —
// callers solve the matching translation so contacts stay put).
function fkFrames(anglesDeg, extras = {}, rootOffset = [0, 0, 0], rootPitchDeg = 0) {
  const rootR = rootPitchDeg ? rotAxisDeg(Y, rootPitchDeg) : IDENTITY3;
  const frames = { pelvis: { R: rootR, p: [...rootOffset] } };
  for (const joint of JOINTS) {
    const parent = frames[joint.parent];
    const offset = matVec3(parent.R, joint.origin);
    const p = [parent.p[0] + offset[0], parent.p[1] + offset[1], parent.p[2] + offset[2]];
    let R = matMul3(parent.R, rotAxisDeg(joint.axis, finite(anglesDeg[joint.name], 0)));
    const extra = extras[joint.name];
    if (extra && finite(extra.pitchDeg, 0) !== 0) {
      R = matMul3(R, rotAxisDeg(Y, extra.pitchDeg));
    }
    if (extra && finite(extra.rollDeg, 0) !== 0) {
      R = matMul3(R, rotAxisDeg(X, extra.rollDeg));
    }
    frames[joint.child] = { R, p };
  }
  return frames;
}

const ATHLETIC_FRAMES = fkFrames(ATHLETIC_ANGLES);

// Per-side stride-IK constants derived from the athletic FK: the hip-pitch
// joint center stays fixed in the world (static pelvis, athletic hip
// yaw/roll), and the compensated ankle roll keeps the foot flat, so the
// ankle-pitch target maps exactly onto the rolled sagittal plane.
const STRIDE_RIG = (() => {
  const rig = {};
  for (const side of SIDES) {
    const hip = ATHLETIC_FRAMES[`thigh_${side}`].p;   // hip-pitch joint center
    const foot = ATHLETIC_FRAMES[`foot_${side}`];
    const rollRad = (sideSign(side) * ATHLETIC.HIP_ROLL_ABDUCT * Math.PI) / 180;
    // Sole plane and the flat-foot vertical offset from the ankle-pitch
    // joint: the 30 mm ankle-roll drop is still rolled by the hip roll, the
    // 26 mm sole sits below the roll-compensated (world-aligned) foot frame.
    const soleZ = foot.p[2] + matVec3(foot.R, [0, 0, -26])[2];
    const ankleToSole = (30 * Math.cos(rollRad)) + 26;
    rig[side] = { hipZ: hip[2], cosRoll: Math.cos(rollRad), soleZ, ankleToSole };
  }
  return rig;
})();

// Athletic left toe-tip world position (x, y): the Elvis kick-out leg IK
// starts and ends its toe-target path here so the dance loop rests
// exactly on the athletic stance.
const ELVIS_ATHLETIC_TOE = (() => {
  const foot = ATHLETIC_FRAMES.foot_left;
  const toe = matVec3(foot.R, [112, 0, -26]).map((v, k) => v + foot.p[k]);
  return [toe[0], toe[1]];
})();

// Row-major 4x4 mapping the baked athletic placement of a link onto its
// target placement: M = [R_t R_o^T | p_t - R_t R_o^T p_o].
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

// Raised-cosine swing envelope: 0 at lift-off and touch-down, 1 mid-swing,
// identically 0 outside the window so the stance foot never moves.
function swingEnvelope(phase, [start, end]) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  if (p <= start || p >= end) {
    return 0;
  }
  const u = (p - start) / (end - start);
  const lobe = Math.sin(Math.PI * u);
  return lobe * lobe;
}

// Cosine forwardness peaking at the given cycle position.
function forwardness(phase, peakAt) {
  return Math.cos(2 * Math.PI * (finite(phase, 0) - peakAt));
}

function gaitAnglesDeg(phase, { legLift = 1, armSwing = 1, torsoSway = 1 } = {}) {
  const angles = { ...ATHLETIC_ANGLES };

  for (const side of SIDES) {
    const env = swingEnvelope(phase, SWING[side]) * legLift;
    const hipDelta = -HIP_LIFT_DEG * env;
    const kneeDelta = KNEE_FOLD_DEG * env;
    // Cancel hip+knee so the airborne foot stays near level, then point
    // the toes down a touch mid-swing.
    const ankleDelta = -(hipDelta + kneeDelta) + (TOE_POINT_DEG * env);
    angles[`hip_pitch_${side}`] += hipDelta;
    angles[`knee_${side}`] += kneeDelta;
    angles[`ankle_pitch_${side}`] += ankleDelta;

    // Arms swing antiphase to the own-side leg: the left arm leads when the
    // right leg lifts (left swing centered at 0.25, right at 0.75).
    const ownLegPeak = side === "left" ? 0.25 : 0.75;
    const armForward = forwardness(phase, ownLegPeak + 0.5) * armSwing;
    angles[`shoulder_pitch_${side}`] += -ARM_SWING_DEG * armForward;
    angles[`elbow_${side}`] += -ELBOW_EXTRA_DEG * Math.max(0, armForward);
  }

  // Torso counter-rotation: turning left brings the right shoulder forward
  // exactly while the left leg swings; the neck compensates most of it so
  // the head keeps facing forward.
  const sway = WAIST_SWAY_DEG * torsoSway * Math.sin(2 * Math.PI * finite(phase, 0));
  angles.waist_yaw += sway;
  angles.neck_yaw += -sway * NECK_COMPENSATION;

  return angles;
}

function torsoRollExtras(phase, torsoSway) {
  // Lean toward the stance side: negative roll (lean robot-right) while the
  // left leg is lifted at phase 0.25.
  const rollDeg = -TORSO_ROLL_DEG * torsoSway * Math.sin(2 * Math.PI * finite(phase, 0));
  return { waist_yaw: { rollDeg } };
}

function smooth01(value) {
  const t = clamp(value, 0, 1);
  return t * t * (3 - (2 * t));
}

// Two-link planar leg IK in the rolled sagittal plane. Targets the
// ankle-pitch joint at forward offset dx (mm, from the hip-pitch joint) and
// plane depth d (mm); footPitchDeg is the desired world pitch of the foot.
// Returns hip-pitch / knee / ankle-pitch angles in the chain's conventions
// (hip negative = forward, knee positive = flexion).
function legPitchIk(dx, d, footPitchDeg) {
  const dist = clamp(Math.hypot(dx, d), Math.abs(THIGH_LEN - SHIN_LEN) + 1, THIGH_LEN + SHIN_LEN - 1);
  const phi = Math.atan2(dx, d); // forward angle of the hip->ankle line from straight down
  const cosInterior = clamp(
    ((THIGH_LEN * THIGH_LEN) + (SHIN_LEN * SHIN_LEN) - (dist * dist)) / (2 * THIGH_LEN * SHIN_LEN),
    -1,
    1
  );
  const kneeRad = Math.PI - Math.acos(cosInterior); // knee flexion, >= 0 (knee bends forward)
  const cosBeta = clamp(
    ((THIGH_LEN * THIGH_LEN) + (dist * dist) - (SHIN_LEN * SHIN_LEN)) / (2 * THIGH_LEN * dist),
    -1,
    1
  );
  const thighRad = phi + Math.acos(cosBeta); // thigh angle from straight down, + forward
  const hipDeg = (-thighRad * 180) / Math.PI;
  const kneeDeg = (kneeRad * 180) / Math.PI;
  const ankleDeg = footPitchDeg - (hipDeg + kneeDeg);
  return { hipDeg, kneeDeg, ankleDeg };
}

// Treadmill stride: stance foot slides backward flat on the ground from
// +stride/2 to -stride/2; the swing leg returns through the air with toe-off
// and heel-strike accents. Both halves meet at zero velocity mismatch in
// position, so the loop is seamless.
function strideAnglesDeg(phase, { strideLength = 230, legLift = 1, armSwing = 1, torsoSway = 1 } = {}) {
  const angles = { ...ATHLETIC_ANGLES };
  const stride = clamp(strideLength, 0, MAX_STRIDE_MM);

  for (const side of SIDES) {
    const rig = STRIDE_RIG[side];
    const q = ((finite(phase, 0) + STRIDE_PHASE[side]) % 1 + 1) % 1;
    let ankleX;
    let soleTargetZ;
    let footPitchDeg;
    if (q < STANCE_FRACTION) {
      const s = q / STANCE_FRACTION;
      ankleX = (stride / 2) - (stride * s); // front contact -> push-off behind
      soleTargetZ = rig.soleZ;
      footPitchDeg = 0;
    } else {
      const u = (q - STANCE_FRACTION) / (1 - STANCE_FRACTION);
      ankleX = (-stride / 2) + (stride * smooth01(u));
      const lobe = Math.sin(Math.PI * u);
      // Clearance and toe-off/heel accents scale with the stride so a zero
      // stride degenerates to plain athletic standing.
      const reach = stride / DEFAULT_STRIDE_MM;
      soleTargetZ = rig.soleZ + (STRIDE_LIFT_MM * clamp(legLift, 0, 1.4) * lobe * reach);
      // Toes down right after toe-off, toes up (heel first) into contact.
      footPitchDeg = ((STRIDE_TOE_OFF_DEG * lobe * (1 - u)) - (STRIDE_HEEL_DEG * lobe * u)) * reach;
    }
    const ankleTargetZ = soleTargetZ + rig.ankleToSole;
    const depth = (rig.hipZ - ankleTargetZ) / rig.cosRoll;
    // ankleX is authored relative to the hip-pitch joint; the athletic ankle
    // sits exactly under the hip, so stride 0 reproduces the athletic legs.
    const ik = legPitchIk(ankleX, depth, footPitchDeg);
    angles[`hip_pitch_${side}`] = ik.hipDeg;
    angles[`knee_${side}`] = ik.kneeDeg;
    angles[`ankle_pitch_${side}`] = ik.ankleDeg;

    // Arms counter the opposite leg: forward peak at the other side's
    // mid-swing, wider than the march to match the longer stride.
    const otherSide = side === "left" ? "right" : "left";
    const armForward = forwardness(phase, STRIDE_MID_SWING[otherSide]) * armSwing * STRIDE_ARM_FACTOR;
    angles[`shoulder_pitch_${side}`] += -ARM_SWING_DEG * armForward;
    angles[`elbow_${side}`] += -ELBOW_EXTRA_DEG * Math.max(0, armForward);
  }

  // Shoulder girdle counters the hips: the right shoulder leads while the
  // right arm swings forward (right-arm peak == left leg mid-swing).
  const sway = WAIST_SWAY_DEG * STRIDE_SWAY_FACTOR * torsoSway
    * forwardness(phase, STRIDE_MID_SWING.left);
  angles.waist_yaw += sway;
  angles.neck_yaw += -sway * NECK_COMPENSATION;

  return angles;
}

function strideTorsoRollExtras(phase, torsoSway) {
  // Lean toward the stance side: robot-right lean while the left leg swings.
  const rollDeg = -TORSO_ROLL_DEG * STRIDE_SWAY_FACTOR * torsoSway
    * forwardness(phase, STRIDE_MID_SWING.left);
  return { waist_yaw: { rollDeg } };
}

// ------------------------------------------------------------------- run
function runBounceMm(phase, legLift) {
  // Twice per cycle: lowest at each mid-stance, highest at mid-flight.
  return -RUN_BOUNCE_MM * clamp(legLift, 0, 1.4)
    * Math.cos(4 * Math.PI * (finite(phase, 0) - RUN_MID_STANCE.left));
}

// Stance-foot targets with a toe-pivot heel-off: the foot pivots about the
// sole's front edge so the heel rises into push-off without the toe digging
// below the ground.
function runStanceTarget(s, stride, reach, rig) {
  const flatAnkleX = (stride * RUN_CONTACT_SHARE) - (stride * s);
  let pitchDeg = 0;
  if (s > RUN_HEEL_OFF_START) {
    pitchDeg = RUN_HEEL_OFF_DEG * reach * smooth01((s - RUN_HEEL_OFF_START) / (1 - RUN_HEEL_OFF_START));
  }
  const pitchRad = (pitchDeg * Math.PI) / 180;
  const c = Math.cos(pitchRad);
  const sn = Math.sin(pitchRad);
  // Ankle relative to the toe pivot when flat: (-RUN_TOE_PIVOT_X_MM, +ankle height).
  const ankleX = flatAnkleX + (RUN_TOE_PIVOT_X_MM * (1 - c)) + (RUN_ANKLE_HEIGHT_MM * sn);
  const ankleZ = rig.soleZ + (RUN_TOE_PIVOT_X_MM * sn) + (rig.ankleToSole * c);
  return { ankleX, ankleZ, pitchDeg };
}

function runAnglesDeg(phase, { strideLength = 230, legLift = 1, armSwing = 1, torsoSway = 1 } = {}) {
  const angles = { ...ATHLETIC_ANGLES };
  const stride = clamp(strideLength, 0, MAX_STRIDE_MM);
  const reach = stride / DEFAULT_STRIDE_MM;
  const lift = clamp(legLift, 0, 1.4);
  const bounce = runBounceMm(phase, legLift);

  for (const side of SIDES) {
    const rig = STRIDE_RIG[side];
    const q = ((finite(phase, 0) + RUN_PHASE[side]) % 1 + 1) % 1;
    let target;
    if (q < RUN_STANCE_FRACTION) {
      target = runStanceTarget(q / RUN_STANCE_FRACTION, stride, reach, rig);
    } else {
      const u = (q - RUN_STANCE_FRACTION) / (1 - RUN_STANCE_FRACTION);
      const t = smooth01(u);
      const end = runStanceTarget(1, stride, reach, rig);
      const contactX = stride * RUN_CONTACT_SHARE;
      const contactZ = rig.soleZ + rig.ankleToSole;
      target = {
        ankleX: end.ankleX + ((contactX - end.ankleX) * t),
        ankleZ: end.ankleZ + ((contactZ - end.ankleZ) * t)
          + (RUN_APEX_MM * lift * reach * Math.sin(Math.PI * u)),
        pitchDeg: (end.pitchDeg * (1 - t) * (1 - t))
          - (RUN_HEEL_IN_DEG * reach * Math.sin(Math.PI * u) * u)
      };
    }
    const depth = ((rig.hipZ + bounce) - target.ankleZ) / rig.cosRoll;
    const ik = legPitchIk(target.ankleX, depth, target.pitchDeg);
    angles[`hip_pitch_${side}`] = ik.hipDeg;
    angles[`knee_${side}`] = ik.kneeDeg;
    angles[`ankle_pitch_${side}`] = ik.ankleDeg;

    // Runner's arm pump: bent elbows, antiphase to the own-side leg.
    const otherSide = side === "left" ? "right" : "left";
    const armForward = forwardness(phase, RUN_MID_SWING[otherSide]) * armSwing;
    angles[`shoulder_pitch_${side}`] += -RUN_ARM_SWING_DEG * armForward;
    angles[`elbow_${side}`] += (RUN_ELBOW_BASE_DEG * clamp(armSwing, 0, 1.5))
      - (RUN_ELBOW_PUMP_DEG * Math.max(0, armForward));
  }

  // Shoulder girdle counters the hips; the head keeps level against both
  // the sway and the forward lean.
  const sway = RUN_SWAY_DEG * torsoSway * forwardness(phase, RUN_MID_SWING.left);
  angles.waist_yaw += sway;
  angles.neck_yaw += -sway * NECK_COMPENSATION;
  angles.neck_pitch += -RUN_LEAN_DEG * NECK_COMPENSATION;

  return angles;
}

function runTorsoExtras(phase, torsoSway) {
  // Constant forward lean plus a lean toward the stance side.
  const rollDeg = RUN_ROLL_DEG * torsoSway * forwardness(phase, RUN_MID_STANCE.left);
  return { waist_yaw: { pitchDeg: RUN_LEAN_DEG, rollDeg } };
}

// ------------------------------------------------------------------ jump
function jumpBodyZMm(phase, lift) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  const { crouch, push, land, absorb } = JUMP_TIMING;
  if (p < crouch) {
    return -JUMP_CROUCH_MM * lift * smooth01(p / crouch);
  }
  if (p < push) {
    const t = smooth01((p - crouch) / (push - crouch));
    return (-JUMP_CROUCH_MM * lift) + (((JUMP_TAKEOFF_MM) + (JUMP_CROUCH_MM * lift)) * t);
  }
  if (p < land) {
    // Ballistic parabola between takeoff and landing at the same height.
    const t = (p - push) / (land - push);
    const apex = JUMP_APEX_MM * lift;
    return JUMP_TAKEOFF_MM + ((apex - JUMP_TAKEOFF_MM) * (1 - ((2 * t) - 1) * ((2 * t) - 1)));
  }
  if (p < absorb) {
    // Impact: ride down into the first compression.
    const t = smooth01((p - land) / (absorb - land));
    return JUMP_TAKEOFF_MM + (((JUMP_LAND_DIP_MM * lift) - JUMP_TAKEOFF_MM) * t);
  }
  // Springy recovery: underdamped wobble that ends exactly at zero.
  const t = (p - absorb) / (1 - absorb);
  return JUMP_LAND_DIP_MM * lift * Math.exp(-JUMP_SPRING_DECAY * t)
    * Math.cos(2 * Math.PI * JUMP_SPRING_CYCLES * t);
}

function jumpFlightProgress(phase) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  const { push, land } = JUMP_TIMING;
  if (p <= push || p >= land) {
    return 0;
  }
  return (p - push) / (land - push);
}

// Arms: backswing in the crouch, sweep overhead for the flight, dip with
// the landing spring, settle back to athletic by the end of the cycle.
function jumpShoulderPitchDeg(phase, bodyZ) {
  const p = ((finite(phase, 0) % 1) + 1) % 1;
  const { crouch, push, land, absorb } = JUMP_TIMING;
  const athletic = ATHLETIC.SHOULDER_PITCH;
  if (p < crouch) {
    return athletic + ((JUMP_ARM_BACK_DEG - athletic) * smooth01(p / crouch));
  }
  if (p < push) {
    return JUMP_ARM_BACK_DEG + ((JUMP_ARM_UP_DEG - JUMP_ARM_BACK_DEG) * smooth01((p - crouch) / (push - crouch)));
  }
  if (p < land) {
    return JUMP_ARM_UP_DEG;
  }
  if (p < absorb) {
    // Dip with the impact: arms lower in proportion to the body drop.
    return JUMP_ARM_UP_DEG + (Math.abs(Math.min(0, bodyZ)) * JUMP_ARM_SPRING_DEG_PER_MM);
  }
  const t = smooth01((p - absorb) / (1 - absorb));
  const dipped = JUMP_ARM_UP_DEG + (Math.abs(Math.min(0, bodyZ)) * JUMP_ARM_SPRING_DEG_PER_MM);
  return dipped + ((athletic - dipped) * t);
}

function jumpAnglesDeg(phase, { legLift = 1, armSwing = 1 } = {}) {
  const angles = { ...ATHLETIC_ANGLES };
  const lift = clamp(legLift, 0, 1.4);
  const bodyZ = jumpBodyZMm(phase, lift);
  const flight = jumpFlightProgress(phase);
  const tuckLobe = Math.sin(Math.PI * flight);

  for (const side of SIDES) {
    const rig = STRIDE_RIG[side];
    // Feet stay planted under the hips; in flight the ankle target rises
    // (tuck) and the IK reach clamp straightens the legs at takeoff/landing.
    const ankleZ = rig.soleZ + rig.ankleToSole + (flight > 0 ? JUMP_TUCK_MM * lift * tuckLobe : 0);
    const pitchDeg = flight > 0 ? JUMP_TOE_POINT_DEG * tuckLobe : 0;
    const depth = ((rig.hipZ + bodyZ) - ankleZ) / rig.cosRoll;
    const ik = legPitchIk(0, depth, pitchDeg);
    angles[`hip_pitch_${side}`] = ik.hipDeg;
    angles[`knee_${side}`] = ik.kneeDeg;
    angles[`ankle_pitch_${side}`] = ik.ankleDeg;

    // Overhead V: pitch sweeps the arms up; roll spreads them outward in
    // proportion to how raised they are.
    const s = sideSign(side);
    const shoulderPitch = jumpShoulderPitchDeg(phase, bodyZ);
    const raised = clamp(
      (shoulderPitch - ATHLETIC.SHOULDER_PITCH) / (JUMP_ARM_UP_DEG - ATHLETIC.SHOULDER_PITCH),
      0,
      1
    );
    const armScale = clamp(armSwing, 0, 1.5);
    angles[`shoulder_pitch_${side}`] = ATHLETIC.SHOULDER_PITCH
      + ((shoulderPitch - ATHLETIC.SHOULDER_PITCH) * armScale);
    angles[`shoulder_roll_${side}`] += s * JUMP_ARM_V_DEG * raised * armScale;
    angles[`elbow_${side}`] = ATHLETIC.ELBOW + (5 * raised * armScale);
  }

  // Look up a touch while airborne.
  angles.neck_pitch += JUMP_HEAD_UP_DEG * tuckLobe;
  return { angles, bodyZ, flight };
}

function jumpTorsoExtras(phase, bodyZ, flight, torsoSway) {
  // Lean into the crouch and the landing compression, upright in the air.
  const compression = clamp(-Math.min(0, bodyZ) / JUMP_CROUCH_MM, 0, 1.2);
  const pitchDeg = JUMP_LEAN_DEG * compression * (1 - flight) * clamp(torsoSway, 0, 1.5);
  return { waist_yaw: { pitchDeg } };
}

// --------------------------------------------------------------- routine
function wrap01(value) {
  return ((finite(value, 0) % 1) + 1) % 1;
}

// Smooth on/off window: ramps up over [inStart, inEnd], back down over
// [outStart, outEnd], zero outside.
function pulse(t, inStart, inEnd, outStart, outEnd) {
  return smooth01((t - inStart) / Math.max(1e-9, inEnd - inStart))
    * (1 - smooth01((t - outStart) / Math.max(1e-9, outEnd - outStart)));
}

// Planted-leg solve shared by the kick support leg and the dance: the
// pitch IK keeps the sole at ground height under a bobbing pelvis, and a
// hip/ankle roll pair absorbs a lateral pelvis shift dy (the second-order
// foot lift from the roll arc is under 2 mm at these amplitudes).
function plantedLegAngles(side, bodyZMm, pelvisDyMm) {
  const rig = STRIDE_RIG[side];
  const s = sideSign(side);
  const depth = ((rig.hipZ + bodyZMm) - (rig.soleZ + rig.ankleToSole)) / rig.cosRoll;
  const ik = legPitchIk(0, depth, 0);
  const lateralDrop = HIP_ROLL_Z_MM - rig.soleZ;
  const rollDeltaDeg = (Math.asin(clamp(pelvisDyMm / lateralDrop, -0.5, 0.5)) * 180) / Math.PI;
  return {
    [`hip_pitch_${side}`]: ik.hipDeg,
    [`knee_${side}`]: ik.kneeDeg,
    [`ankle_pitch_${side}`]: ik.ankleDeg,
    [`hip_roll_${side}`]: (s * ATHLETIC.HIP_ROLL_ABDUCT) - rollDeltaDeg,
    [`ankle_roll_${side}`]: -((s * ATHLETIC.HIP_ROLL_ABDUCT) - rollDeltaDeg)
  };
}

// ---- karate front kick (segment-local t): weight onto the left leg,
// chamber, snap, re-chamber, plant.
function kickPose(t) {
  const angles = { ...ATHLETIC_ANGLES };
  const weight = pulse(t, 0.0, 0.12, 0.86, 0.98);
  const chamber = pulse(t, 0.14, 0.3, 0.72, 0.88);
  const extend = pulse(t, 0.36, 0.48, 0.58, 0.7);
  const guard = pulse(t, 0.04, 0.16, 0.8, 0.94);

  const dy = KICK_WEIGHT_SHIFT_MM * weight;
  const bodyZ = -KICK_DIP_MM * chamber;
  Object.assign(angles, plantedLegAngles("left", bodyZ, dy));

  // Kicking leg, authored in joint space (airborne).
  angles.hip_pitch_right = ATHLETIC.HIP_PITCH
    + ((KICK_CHAMBER_HIP_DEG - ATHLETIC.HIP_PITCH) * chamber)
    + (KICK_EXTEND_HIP_DEG * extend);
  angles.knee_right = ATHLETIC.KNEE
    + ((KICK_CHAMBER_KNEE_DEG - ATHLETIC.KNEE) * chamber)
    + (KICK_EXTEND_KNEE_DEG * extend);
  angles.ankle_pitch_right = ATHLETIC.ANKLE_PITCH
    + ((KICK_CHAMBER_ANKLE_DEG - ATHLETIC.ANKLE_PITCH) * chamber)
    + (KICK_EXTEND_ANKLE_DEG * extend);
  angles.ankle_roll_right = -sideSign("right") * ATHLETIC.HIP_ROLL_ABDUCT;

  // Guard: both fists up, elbows tight.
  for (const side of SIDES) {
    const s = sideSign(side);
    angles[`shoulder_pitch_${side}`] = ATHLETIC.SHOULDER_PITCH
      + ((KICK_GUARD_SHOULDER_DEG - ATHLETIC.SHOULDER_PITCH) * guard);
    angles[`shoulder_roll_${side}`] = (s * ATHLETIC.SHOULDER_ROLL_ABDUCT)
      + (s * KICK_GUARD_ROLL_OUT_DEG * guard);
    angles[`elbow_${side}`] = ATHLETIC.ELBOW
      + ((KICK_GUARD_ELBOW_DEG - ATHLETIC.ELBOW) * guard);
  }

  const turn = KICK_HIP_TURN_DEG * ((0.5 * chamber) + (0.5 * extend));
  angles.waist_yaw += turn;
  angles.neck_yaw += -turn * NECK_COMPENSATION;

  return {
    angles,
    extras: { waist_yaw: { pitchDeg: KICK_LEAN_BACK_DEG * extend } },
    rootOffset: [0, dy, bodyZ],
    rootPitchDeg: 0
  };
}

// ---- handstand: keyframed whole-body rotation about +Y. While folding,
// the root is anchored so the sole front edge stays at its athletic spot
// (heels rise, toe pivot); once the hands plant, the root is anchored so
// the palm contact point stays on the ground at the plant line. Anchors
// are solved once at init by evaluating the FK and shifting the root.
function anchoredRootOffset(angles, rootPitchDeg, link, localMm, targetMm) {
  const frames = fkFrames(angles, {}, [0, 0, 0], rootPitchDeg);
  const f = frames[link];
  const world = matVec3(f.R, localMm).map((v, k) => v + f.p[k]);
  // null target components leave that axis where the pose naturally put it.
  return targetMm.map((t, k) => (t === null ? 0 : t - world[k]));
}

function handstandKeyAngles(overrides) {
  const angles = { ...ATHLETIC_ANGLES };
  for (const side of SIDES) {
    // Square the limbs for the gymnastic line: no abduction or twist.
    angles[`hip_roll_${side}`] = 0;
    angles[`ankle_roll_${side}`] = 0;
    angles[`shoulder_yaw_${side}`] = 0;
    angles[`wrist_pitch_${side}`] = 0;
    for (const [name, value] of Object.entries(overrides.legs || {})) {
      angles[`${name}_${side}`] = value;
    }
    for (const [name, value] of Object.entries(overrides.arms || {})) {
      angles[`${name}_${side}`] = value;
    }
  }
  if (overrides.neckPitch !== undefined) {
    angles.neck_pitch = overrides.neckPitch;
  }
  return angles;
}

const HANDSTAND_KEYS = (() => {
  const toeFrame = ATHLETIC_FRAMES.foot_left;
  const toeWorld = matVec3(toeFrame.R, HS_TOE_LOCAL_MM).map((v, k) => v + toeFrame.p[k]);
  // Anchor x/z only; the lateral position stays where the pose puts it.
  const toeTarget = [toeWorld[0], null, toeWorld[2]];
  const ground = STRIDE_RIG.left.soleZ;
  const palmTarget = [HS_PLANT_X_MM, null, ground];

  // The arms stay roughly vertical under the rotating body — the world
  // arm direction is rootPitch + shoulderPitch, so the shoulder tracks
  // -rootPitch as the body goes over, reaching shoulder -180 / elbow -18 /
  // wrist -70 at the hold (total hand pitch -90: palms flat, fingers
  // forward), all inside the URDF joint limits.
  const HOLD_ARMS = { shoulder_pitch: -180, shoulder_roll: 0, elbow: -18, wrist_roll: 0, wrist_pitch: -70 };
  const spec = [
    { t: 0.0, pitch: 0, anchor: null, overrides: null },
    {
      t: 0.09, pitch: 12, anchor: "toe",
      overrides: {
        legs: { hip_pitch: -30, knee: 20, ankle_pitch: 3 }, // foot pitch +5: heel just off the ground
        arms: { shoulder_pitch: -52, shoulder_roll: 0, elbow: -10, wrist_roll: 0, wrist_pitch: -20 }
      }
    },
    {
      t: 0.2, pitch: 55, anchor: "toe",
      overrides: {
        legs: { hip_pitch: -100, knee: 30, ankle_pitch: 27 }, // foot pitch +12: heels rise in the fold
        arms: { shoulder_pitch: -70, shoulder_roll: 0, elbow: -8, wrist_roll: 0, wrist_pitch: -45 }
      }
    },
    {
      // Press position: palms planted, arms vertical, pike fold with the
      // toes still resting on the ground (hip solved at init below).
      t: 0.3, pitch: 95, anchor: "palm", solvePressHip: true,
      overrides: {
        legs: { hip_pitch: -80, knee: 8, ankle_pitch: 30 },
        arms: { shoulder_pitch: -95, shoulder_roll: 0, elbow: -20, wrist_roll: 0, wrist_pitch: -70 }
      }
    },
    {
      t: 0.4, pitch: 140, anchor: "palm",
      overrides: {
        legs: { hip_pitch: -45, knee: 25, ankle_pitch: 10 },
        arms: { shoulder_pitch: -145, shoulder_roll: 0, elbow: -18, wrist_roll: 0, wrist_pitch: -67 }
      }
    },
    {
      t: 0.48, pitch: 178, anchor: "palm",
      overrides: {
        legs: { hip_pitch: -6, knee: 4, ankle_pitch: 25 },
        arms: HOLD_ARMS
      }
    },
    {
      t: 0.58, pitch: 178, anchor: "palm",
      overrides: {
        legs: { hip_pitch: -6, knee: 4, ankle_pitch: 25 },
        arms: HOLD_ARMS
      }
    }
  ];
  // Mirror the way back down through the same shapes.
  const back = [
    { ...spec[4], t: 0.66 },
    { ...spec[3], t: 0.76 },
    { ...spec[2], t: 0.86 },
    { ...spec[1], t: 0.94 },
    { ...spec[0], t: 1.0 }
  ];

  // Resolve every key with its anchor TYPE plus the toe-line x position
  // it implies; the root translation itself is solved per frame at
  // runtime, so contacts stay exact through every interpolated pose.
  // Palm-typed keys still record their natural toe x so toe<->palm
  // boundary intervals can slide the toe target continuously.
  const resolved = [...spec, ...back].map((key) => {
    const angles = key.overrides ? handstandKeyAngles(key.overrides) : { ...ATHLETIC_ANGLES };
    const type = key.anchor === "palm" ? "palm" : "toe";
    if (key.solvePressHip) {
      // Bisect the pike fold so the toes rest exactly on the ground
      // behind the planted hands (toe height grows monotonically with
      // hip angle on the toes-behind branch). The palm anchor depends
      // only on the arm chain, so the hip search does not disturb it.
      const rootOffset = anchoredRootOffset(angles, key.pitch, "hand_left", HS_PALM_LOCAL_MM, palmTarget);
      let lo = -95;
      let hi = -40;
      for (let i = 0; i < 48; i += 1) {
        const mid = (lo + hi) / 2;
        for (const side of SIDES) {
          angles[`hip_pitch_${side}`] = mid;
        }
        const f = fkFrames(angles, {}, rootOffset, key.pitch).foot_left;
        const toeZ = f.p[2] + matVec3(f.R, HS_TOE_LOCAL_MM)[2];
        if (toeZ < ground) {
          lo = mid;
        } else {
          hi = mid;
        }
      }
    }
    const rootOffset = type === "palm"
      ? anchoredRootOffset(angles, key.pitch, "hand_left", HS_PALM_LOCAL_MM, palmTarget)
      : anchoredRootOffset(angles, key.pitch, "foot_left", HS_TOE_LOCAL_MM, toeTarget);
    const foot = fkFrames(angles, {}, rootOffset, key.pitch).foot_left;
    const toeX = foot.p[0] + matVec3(foot.R, HS_TOE_LOCAL_MM)[0];
    return { t: key.t, pitch: key.pitch, type, toeX, angles };
  });
  return { keys: resolved.sort((a, b) => a.t - b.t), toeZ: toeWorld[2], palmTarget };
})();

function handstandPose(t) {
  const { keys, toeZ, palmTarget } = HANDSTAND_KEYS;
  let a = keys[0];
  let b = keys[keys.length - 1];
  for (let i = 0; i < keys.length - 1; i += 1) {
    if (t >= keys[i].t && t <= keys[i + 1].t) {
      a = keys[i];
      b = keys[i + 1];
      break;
    }
  }
  const s = smooth01((t - a.t) / Math.max(1e-9, b.t - a.t));
  const angles = {};
  for (const name of Object.keys(ATHLETIC_ANGLES)) {
    angles[name] = a.angles[name] + ((b.angles[name] - a.angles[name]) * s);
  }
  // A breath of leg wobble during the hold (hips only, so the planted
  // hands stay put).
  const hold = pulse(t, 0.46, 0.5, 0.56, 0.6);
  const wobble = HS_WOBBLE_DEG * hold * Math.sin(2 * Math.PI * ((t - 0.46) / 0.14) * 2);
  for (const side of SIDES) {
    angles[`hip_pitch_${side}`] += wobble;
    angles[`knee_${side}`] += -wobble * 0.6;
  }
  const rootPitchDeg = a.pitch + ((b.pitch - a.pitch) * s);
  // Solve the contact anchor for THIS frame: palm-anchored only while both
  // bracketing keys are palm keys (the press key satisfies both contacts,
  // so the anchor handoff there is seamless); otherwise toe-anchored with
  // the toe target sliding along the ground line between the keys.
  let rootOffset;
  if (a.type === "palm" && b.type === "palm") {
    rootOffset = anchoredRootOffset(angles, rootPitchDeg, "hand_left", HS_PALM_LOCAL_MM, palmTarget);
  } else {
    const toeX = a.toeX + ((b.toeX - a.toeX) * s);
    rootOffset = anchoredRootOffset(angles, rootPitchDeg, "foot_left", HS_TOE_LOCAL_MM, [toeX, null, toeZ]);
  }
  return { angles, extras: {}, rootOffset, rootPitchDeg };
}

// ---- Elvis dance. The left leg kicks out to the robot-left and plants
// on a pointed toe, solved with closed-form leg IK: the hip roll angle
// follows directly from requiring the toe target to lie in the leg's
// (rolled) pitch plane, then the in-plane two-link IK places the
// ankle-pitch joint so the toe tip lands exactly on the target. The
// ankle roll stays 0, so the pointed foot rolls onto its outer toe edge
// with the leg — the classic look.
function elvisKickOutLeg(bodyZMm, pelvisDyMm, toeXMm, toeYMm, footPointDeg, liftMm, edgeScale) {
  const rig = STRIDE_RIG.left;
  // Left hip-roll joint center in the world, with the shifted pelvis.
  const hipRoll = [0, HIP_Y + pelvisDyMm, HIP_ROLL_Z_MM + bodyZMm];
  // The foot rolls with the leg (ankle roll 0), so at full kick-out the
  // contact is the OUTER toe corner: lift the centerline target by the
  // rolled half foot width (scaled in with the pose; roll barely changes
  // with the lift, so one extra pass converges).
  let target = [toeXMm, toeYMm, rig.soleZ + liftMm];
  let v = [target[0] - hipRoll[0], target[1] - hipRoll[1], target[2] - hipRoll[2]];
  const edgeLift = ((35 * Math.abs(Math.sin(Math.atan2(v[1], -v[2])))) + 1) * edgeScale;
  target = [toeXMm, toeYMm, rig.soleZ + liftMm + edgeLift];
  v = [target[0] - hipRoll[0], target[1] - hipRoll[1], target[2] - hipRoll[2]];
  // Roll that brings the target into the leg's pitch plane.
  const rollRad = Math.atan2(v[1], -v[2]);
  const planeDepth = Math.hypot(v[1], v[2]); // hip-roll -> target, in-plane
  // Toe tip relative to the ankle-pitch joint at the pointed foot pitch.
  const pointRad = (footPointDeg * Math.PI) / 180;
  const toeForward = (ELVIS_TOE_TIP_LOCAL.x * Math.cos(pointRad))
    - (ELVIS_TOE_TIP_LOCAL.drop * Math.sin(pointRad));
  const toeDrop = (ELVIS_TOE_TIP_LOCAL.x * Math.sin(pointRad))
    + (ELVIS_TOE_TIP_LOCAL.drop * Math.cos(pointRad));
  // Ankle-pitch target measured from the hip-PITCH joint (78 mm further
  // down the plane from the hip-roll joint).
  const ik = legPitchIk(v[0] - toeForward, planeDepth - 78 - toeDrop, footPointDeg);
  const rollDeg = (rollRad * 180) / Math.PI;
  return {
    hip_pitch_left: ik.hipDeg,
    knee_left: ik.kneeDeg,
    ankle_pitch_left: ik.ankleDeg,
    hip_roll_left: rollDeg,
    // Flat (roll-compensated) foot at rest, rolling onto the outer toe
    // edge with the leg as the kick-out engages.
    ankle_roll_left: -rollDeg * (1 - edgeScale)
  };
}

function dancePose(t) {
  const angles = { ...ATHLETIC_ANGLES };
  const env = pulse(t, 0.0, 0.12, 0.88, 1.0);
  const beat = t * ELVIS_BEATS;

  const dy = ELVIS_WEIGHT_SHIFT_MM * env;
  const bodyZ = (-ELVIS_DIP_MM * env)
    - (ELVIS_BOUNCE_MM * env * Math.abs(Math.sin(Math.PI * beat)));
  // Stance leg: planted under the shifted, bobbing pelvis.
  Object.assign(angles, plantedLegAngles("right", bodyZ, dy));

  // Kicked-out leg: toe planted out to the left, shaking with the beat.
  // The whole transition is IK-driven — the toe target slides from the
  // athletic toe spot to the kick-out point with a lift bump mid-blend,
  // so the foot never sweeps through the floor (at env=0 the IK lands
  // exactly back on the athletic leg).
  const shake = env * Math.sin(2 * Math.PI * 2 * beat);
  const toeX = ELVIS_ATHLETIC_TOE[0] + ((ELVIS_TOE_X_MM - ELVIS_ATHLETIC_TOE[0]) * env);
  const toeY = ELVIS_ATHLETIC_TOE[1]
    + (((ELVIS_TOE_Y_MM + (ELVIS_TOE_SHAKE_MM * shake)) - ELVIS_ATHLETIC_TOE[1]) * env);
  const point = (ELVIS_FOOT_POINT_DEG * env) + (ELVIS_FOOT_POINT_SHAKE_DEG * shake);
  const lift = 45 * Math.sin(Math.PI * env);
  Object.assign(angles, elvisKickOutLeg(bodyZ, dy, toeX, toeY, point, lift, env));

  // The point: right arm up and out to the right, pulsing on the beat.
  const pulseDeg = ELVIS_POINT_PULSE_DEG * Math.sin(2 * Math.PI * beat);
  angles.shoulder_roll_right = (sideSign("right") * ATHLETIC.SHOULDER_ROLL_ABDUCT)
    + (((ELVIS_POINT_ROLL_DEG + pulseDeg) - (sideSign("right") * ATHLETIC.SHOULDER_ROLL_ABDUCT)) * env);
  angles.shoulder_pitch_right = ATHLETIC.SHOULDER_PITCH
    + ((ELVIS_POINT_PITCH_DEG - ATHLETIC.SHOULDER_PITCH) * env);
  angles.elbow_right = ATHLETIC.ELBOW + ((ELVIS_POINT_ELBOW_DEG - ATHLETIC.ELBOW) * env);
  // Off arm low and bent across the body.
  angles.shoulder_pitch_left = ATHLETIC.SHOULDER_PITCH
    + ((ELVIS_OFF_ARM_PITCH_DEG - ATHLETIC.SHOULDER_PITCH) * env);
  angles.elbow_left = ATHLETIC.ELBOW + ((ELVIS_OFF_ARM_ELBOW_DEG - ATHLETIC.ELBOW) * env);

  // Hip swivel, lean into the point, head to the pointing hand, chin up.
  const twist = ELVIS_TWIST_DEG * env * Math.sin(Math.PI * beat);
  angles.waist_yaw += twist;
  angles.neck_yaw += (ELVIS_HEAD_TURN_DEG * env) - (twist * 0.6);
  angles.neck_pitch += ELVIS_CHIN_UP_DEG * env;

  return {
    angles,
    extras: { waist_yaw: { rollDeg: ELVIS_LEAN_RIGHT_DEG * env } },
    rootOffset: [0, dy, bodyZ],
    rootPitchDeg: 0
  };
}

const FEATURE_BY_LINK = {
  pelvis: "pelvis",
  torso: "torso",
  neck_collar: "neckCollar",
  head: "head",
  hip_bracket_left: "hipBracketLeft",
  hip_carrier_left: "hipCarrierLeft",
  thigh_left: "thighLeft",
  shin_left: "shinLeft",
  ankle_link_left: "ankleLinkLeft",
  foot_left: "footLeft",
  shoulder_pod_left: "shoulderPodLeft",
  yaw_housing_left: "yawHousingLeft",
  bicep_left: "bicepLeft",
  forearm_left: "forearmLeft",
  wrist_carrier_left: "wristCarrierLeft",
  hand_left: "handLeft",
  hip_bracket_right: "hipBracketRight",
  hip_carrier_right: "hipCarrierRight",
  thigh_right: "thighRight",
  shin_right: "shinRight",
  ankle_link_right: "ankleLinkRight",
  foot_right: "footRight",
  shoulder_pod_right: "shoulderPodRight",
  yaw_housing_right: "yawHousingRight",
  bicep_right: "bicepRight",
  forearm_right: "forearmRight",
  wrist_carrier_right: "wristCarrierRight",
  hand_right: "handRight"
};

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/renders/juno/juno.step"
    },
    label: "juno humanoid",
    description: "Walking-in-place march for the juno humanoid: alternating leg lift with planted stance feet, antiphase arm swing, torso counter-sway, and a head that keeps facing forward.",
    units: {
      length: "mm",
      angle: "deg",
      time: "s"
    },
    features: {
      pelvis: { ref: "#o1.1", label: "Pelvis", description: "Root link; static during the in-place march." },
      torso: { ref: "#o1.2", label: "Torso" },
      neckCollar: { ref: "#o1.3", label: "Neck collar" },
      head: { ref: "#o1.4", label: "Head" },
      hipBracketLeft: { ref: "#o1.5", label: "Left hip bracket" },
      hipCarrierLeft: { ref: "#o1.6", label: "Left hip carrier" },
      thighLeft: { ref: "#o1.7", label: "Left thigh" },
      shinLeft: { ref: "#o1.8", label: "Left shin" },
      ankleLinkLeft: { ref: "#o1.9", label: "Left ankle link" },
      footLeft: { ref: "#o1.10", label: "Left foot" },
      shoulderPodLeft: { ref: "#o1.11", label: "Left shoulder pod" },
      yawHousingLeft: { ref: "#o1.12", label: "Left yaw housing" },
      bicepLeft: { ref: "#o1.13", label: "Left bicep" },
      forearmLeft: { ref: "#o1.14", label: "Left forearm" },
      wristCarrierLeft: { ref: "#o1.15", label: "Left wrist carrier" },
      handLeft: { ref: "#o1.16", label: "Left hand" },
      hipBracketRight: { ref: "#o1.17", label: "Right hip bracket" },
      hipCarrierRight: { ref: "#o1.18", label: "Right hip carrier" },
      thighRight: { ref: "#o1.19", label: "Right thigh" },
      shinRight: { ref: "#o1.20", label: "Right shin" },
      ankleLinkRight: { ref: "#o1.21", label: "Right ankle link" },
      footRight: { ref: "#o1.22", label: "Right foot" },
      shoulderPodRight: { ref: "#o1.23", label: "Right shoulder pod" },
      yawHousingRight: { ref: "#o1.24", label: "Right yaw housing" },
      bicepRight: { ref: "#o1.25", label: "Right bicep" },
      forearmRight: { ref: "#o1.26", label: "Right forearm" },
      wristCarrierRight: { ref: "#o1.27", label: "Right wrist carrier" },
      handRight: { ref: "#o1.28", label: "Right hand" }
    },
    parameters: {
      phase: {
        type: "number",
        label: "Gait phase",
        description: "One full gait cycle; the walk animations drive this 0 -> 1.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.001
      },
      gait: {
        type: "select",
        label: "Gait",
        description: "Showpieces (Elvis dance, handstand, karate kick) and in-place gaits (jump, run, stride, march). Each walk animation drives the matching mode.",
        default: "march",
        options: [
          { value: "dance", label: "Elvis dance" },
          { value: "handstand", label: "Handstand" },
          { value: "kick", label: "Karate kick" },
          { value: "jump", label: "Jump in place" },
          { value: "run", label: "Run in place" },
          { value: "stride", label: "Stride in place" },
          { value: "march", label: "March in place" }
        ]
      },
      strideLength: {
        type: "number",
        label: "Stride length",
        description: "Front-to-back foot travel (mm) of the stride gait; capped so the leg IK stays inside reach. Ignored by the march.",
        default: 230,
        min: 0,
        max: 300,
        step: 5
      },
      legLift: {
        type: "number",
        label: "Leg lift",
        description: "Scales hip raise, knee fold, and toe point of the swing leg. Stance feet stay planted at any value.",
        default: 1,
        min: 0,
        max: 1.4,
        step: 0.01
      },
      armSwing: {
        type: "number",
        label: "Arm swing",
        description: "Scales the antiphase shoulder swing and forward-arm elbow flexion.",
        default: 1,
        min: 0,
        max: 1.5,
        step: 0.01
      },
      torsoSway: {
        type: "number",
        label: "Torso sway",
        description: "Scales the waist counter-rotation and weight-shift roll; the head compensates to keep facing forward.",
        default: 1,
        min: 0,
        max: 1.5,
        step: 0.01
      }
    },
    // Ordered most exciting first — this is the order the viewer lists them.
    animations: {
      danceLoop: {
        label: "Elvis dance",
        description: "The King: weight on the right leg, left leg kicked out to the left on a shaking pointed toe, right finger pointing up to the right with a beat pulse, hip swivel and chin up.",
        duration: 3.2,
        loop: true,
        update({ cycle, set }) {
          set("gait", "dance");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      handstandLoop: {
        label: "Handstand",
        description: "Toe-pivot fold, press to a palms-flat inverted hold with a breathing wobble, and back up to the ready stance.",
        duration: 4.6,
        loop: true,
        update({ cycle, set }) {
          set("gait", "handstand");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      kickLoop: {
        label: "Karate kick",
        description: "Weight shifts over the left leg, the right leg chambers and snaps a ball-of-foot front kick at hip height behind a fists-up guard.",
        duration: 2.8,
        loop: true,
        update({ cycle, set }) {
          set("gait", "kick");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      jumpLoop: {
        label: "Jump in place",
        description: "Crouch, leap with hands overhead, and land with a springy knee-absorbed wobble before settling back to the ready stance.",
        duration: 1.8,
        loop: true,
        update({ cycle, set }) {
          set("gait", "jump");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      runLoop: {
        label: "Run in place",
        description: "Running cadence with flight phases: body bounce, toe-pivot push-off, high heel recovery, forward lean, and pumping bent arms.",
        duration: 0.8,
        loop: true,
        update({ cycle, set }) {
          set("gait", "run");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      strideLoop: {
        label: "Stride in place",
        description: "Bigger strides: legs sweep back and forward with the stance foot sliding flat on the ground, wider arm swing, stronger torso counter-sway.",
        duration: 1.9,
        loop: true,
        update({ cycle, set }) {
          set("gait", "stride");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      },
      walkLoop: {
        label: "Walk in place",
        description: "Continuous march loop; scrub the gait phase or scale lift/swing/sway live.",
        duration: 1.5,
        loop: true,
        update({ cycle, set }) {
          set("gait", "march");
          set("phase", ((finite(cycle, 0) % 1) + 1) % 1);
        }
      }
    }
  },

  update({ params, effects }) {
    const phase = ((finite(params.phase, 0) % 1) + 1) % 1;
    const scales = {
      legLift: clamp(params.legLift, 0, 1.4),
      armSwing: clamp(params.armSwing, 0, 1.5),
      torsoSway: clamp(params.torsoSway, 0, 1.5),
      strideLength: clamp(params.strideLength, 0, MAX_STRIDE_MM)
    };
    const gait = String(params.gait || "march");
    let targetFrames;
    if (gait === "stride") {
      targetFrames = fkFrames(
        strideAnglesDeg(phase, scales),
        strideTorsoRollExtras(phase, scales.torsoSway)
      );
    } else if (gait === "run") {
      targetFrames = fkFrames(
        runAnglesDeg(phase, scales),
        runTorsoExtras(phase, scales.torsoSway),
        [0, 0, runBounceMm(phase, scales.legLift)]
      );
    } else if (gait === "jump") {
      const jump = jumpAnglesDeg(phase, scales);
      targetFrames = fkFrames(
        jump.angles,
        jumpTorsoExtras(phase, jump.bodyZ, jump.flight, scales.torsoSway),
        [0, 0, jump.bodyZ]
      );
    } else if (gait === "kick" || gait === "handstand" || gait === "dance") {
      const pose = gait === "kick"
        ? kickPose(phase)
        : gait === "handstand"
          ? handstandPose(phase)
          : dancePose(phase);
      targetFrames = fkFrames(pose.angles, pose.extras, pose.rootOffset, pose.rootPitchDeg);
    } else {
      targetFrames = fkFrames(
        gaitAnglesDeg(phase, scales),
        torsoRollExtras(phase, scales.torsoSway)
      );
    }

    // The pelvis root is included: it bobs in the run and jump gaits and
    // resolves to an identity delta in the march and stride.
    for (const [link, feature] of Object.entries(FEATURE_BY_LINK)) {
      effects.transform(feature, {
        matrix: deltaMatrixRowMajor(ATHLETIC_FRAMES[link], targetFrames[link])
      });
    }
  }
};

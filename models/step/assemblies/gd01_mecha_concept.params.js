// GD01-inspired manned transformable mecha — viewer parameter/animation sidecar.
//
// The STEP is exported in a neutral upright stance; this module drives all
// articulation as rigid-group transforms about joint pivots read live from the
// actuator feature centers, so it stays correct if the Python geometry
// parameters are regenerated. Kinematic conventions (matching the generator):
// +X forward, +Y left, +Z up, sagittal joint axes along Y, angles in degrees
// with "forward-positive" pitch (top of the rotated body tips toward +X).
//
// Rigid chains:
//   body (pelvis + torso + cockpit + sensors) pitches about the hip axis line;
//   thigh -> shin -> foot hang from each hip with planted-foot compensation
//   (body height/forward shift solved from leg FK so feet stay grounded);
//   upper arm -> forearm -> hand pad hang from each shoulder, switching from
//   FK (biped) to 2-link IK ground contact (quadruped) as the blend rises.

const Y_AXIS = [0, 1, 0];
const DEFAULT_HUE = 356;
const DEFAULT_STANCE = 720; // mm, matches the generator's stance_width default

// Choreographed endpoint poses for the biped <-> quadruped transformation.
const BIPED_POSE = { bodyPitch: 2, thigh: 6, kneeFlex: 10, shoulder: 8, elbowFlex: 14 };
const QUAD_POSE = { bodyPitch: 75, thigh: 55, kneeFlex: 115 };

// Walk/crawl gait amplitudes (degrees / millimeter-scale factors).
const WALK_HIP_AMP = 22;
const WALK_KNEE_AMP = 30;
const WALK_ARM_AMP = 16;
const CRAWL_HIP_AMP = 13;
const CRAWL_KNEE_AMP = 16;

const ARMOR_FEATURES = [
  "pelvis_armor",
  "torso_armor",
  "left_thigh_armor",
  "right_thigh_armor",
  "left_shin_armor",
  "right_shin_armor",
  "left_upper_arm_armor",
  "right_upper_arm_armor",
  "left_forearm_armor",
  "right_forearm_armor",
];

const ACTUATOR_FEATURES = [
  "left_hip_actuator",
  "right_hip_actuator",
  "left_knee_actuator",
  "right_knee_actuator",
  "left_ankle_joint",
  "right_ankle_joint",
  "left_shoulder_actuator",
  "right_shoulder_actuator",
  "left_elbow_actuator",
  "right_elbow_actuator",
];

// Exploded-reveal direction per feature id (unit-ish world vectors, applied
// after the kinematic pose as offset = dir * exploded_distance).
const EXPLODE_DIRS = {
  pelvis_core: [0, 0, 0],
  pelvis_armor: [0.95, 0, -0.1],
  torso_frame: [0, 0, 0.5],
  torso_armor: [-0.5, 0, 0.85],
  cockpit_module: [0.65, 0, 0.4],
  pilot_placeholder: [1.0, 0, 0.7],
  cockpit_gate: [1.25, 0, 0.3],
  cockpit_gate_hinge: [1.25, 0, 0.3],
  sensor_head: [0, 0, 1.3],
  left_hip_actuator: [0, 1.15, 0],
  right_hip_actuator: [0, -1.15, 0],
  left_thigh_core: [0, 0.25, 0],
  right_thigh_core: [0, -0.25, 0],
  left_thigh_armor: [0.45, 0.9, 0],
  right_thigh_armor: [0.45, -0.9, 0],
  left_knee_actuator: [0, 1.05, -0.1],
  right_knee_actuator: [0, -1.05, -0.1],
  left_shin_core: [0, 0.2, -0.15],
  right_shin_core: [0, -0.2, -0.15],
  left_shin_armor: [0.5, 0.85, -0.1],
  right_shin_armor: [0.5, -0.85, -0.1],
  left_ankle_joint: [0, 0.95, -0.3],
  right_ankle_joint: [0, -0.95, -0.3],
  left_foot_pad: [0.1, 0.35, -0.75],
  right_foot_pad: [0.1, -0.35, -0.75],
  left_shoulder_actuator: [0, 1.2, 0.15],
  right_shoulder_actuator: [0, -1.2, 0.15],
  left_upper_arm_core: [0, 0.3, 0],
  right_upper_arm_core: [0, -0.3, 0],
  left_upper_arm_armor: [0.35, 0.95, 0.15],
  right_upper_arm_armor: [0.35, -0.95, 0.15],
  left_elbow_actuator: [0, 1.05, -0.05],
  right_elbow_actuator: [0, -1.05, -0.05],
  left_forearm_core: [0, 0.25, -0.1],
  right_forearm_core: [0, -0.25, -0.1],
  left_forearm_armor: [0.45, 0.85, -0.05],
  right_forearm_armor: [0.45, -0.85, -0.05],
  left_hand_pad: [0.05, 0.3, -0.8],
  right_hand_pad: [0.05, -0.3, -0.8],
};

// Package meshes bake native part colors into vertex colors, so a style
// `color` MULTIPLIES the red rather than replacing it. Palettes therefore
// combine a multiply base with an additive emissive lift to land on the
// intended tone.
const PALETTES = {
  gd01_red: null, // native STEP colors
  stealth_black: { color: "#17181c", emissive: "", emissiveIntensity: 0 },
  arctic_silver: { color: "#aab0b8", emissive: "#dde2e9", emissiveIntensity: 0.42 },
  aurora_blue: { color: "#141a2e", emissive: "#2563eb", emissiveIntensity: 0.55 },
};

function finite(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp(value, lo, hi) {
  return Math.min(Math.max(value, lo), hi);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function smoothstep(t) {
  const x = clamp(t, 0, 1);
  return x * x * (3 - 2 * x);
}

function degToRad(deg) {
  return (deg * Math.PI) / 180;
}

function featureCenter(features, id, fallback = [0, 0, 0]) {
  const center = features?.[id]?.center;
  if (Array.isArray(center) && center.length >= 3) {
    return [finite(center[0]), finite(center[1]), finite(center[2])];
  }
  return [...fallback];
}

// Forward-positive pitch rotation about the Y axis through `pivot`.
// In this Z-up frame a right-handed rotation about +Y tips the top of a body
// toward +X (forward), matching spin2 below, so the angle passes through.
function pitch(pivot, deg) {
  return { rotate: { axis: Y_AXIS, origin: pivot, angleDeg: deg } };
}

// 2D forward-positive rotation of (x, z) about the origin.
function spin2(x, z, deg) {
  const c = Math.cos(degToRad(deg));
  const s = Math.sin(degToRad(deg));
  return [x * c + z * s, -x * s + z * c];
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/step/assemblies/gd01_mecha_concept.step",
    },
    units: { length: "mm", angle: "deg", time: "s" },
    features: {
      pelvis_core: { ref: "#o1.1", label: "Pelvis structure", description: "Hip crossmember, spine riser, battery pack, hip cable looms." },
      pelvis_armor: { ref: "#o1.2", label: "Pelvis armor", description: "Front and rear glossy red pelvis plates." },
      torso_frame: { ref: "#o1.3", label: "Roll-cage frame", description: "Silver protective cage hoops, braces, black cockpit beams." },
      torso_armor: { ref: "#o1.4", label: "Torso armor", description: "Red chest cheeks, vented back shell, cowl, tinted visor." },
      cockpit_module: { ref: "#o1.5", label: "Cockpit module", description: "Floor, pilot seat placeholder, harness, sticks, pedals." },
      pilot_placeholder: { ref: "#o1.6", label: "Pilot placeholder", description: "Seated pilot dummy for scale." },
      cockpit_gate: { ref: "#o1.7", label: "Cockpit gate", description: "Silver lap-bar restraint hoop; swings up for boarding." },
      cockpit_gate_hinge: { ref: "#o1.8", label: "Gate hinge drums", description: "Hinge axis datum for the boarding gate." },
      sensor_head: { ref: "#o1.9", label: "Sensor suite", description: "Lidar puck, stereo camera bar, antennas, beacon fin." },
      left_hip_actuator: { ref: "#o1.10", label: "Left hip actuator" },
      right_hip_actuator: { ref: "#o1.11", label: "Right hip actuator" },
      left_thigh_core: { ref: "#o1.12", label: "Left thigh structure" },
      left_thigh_armor: { ref: "#o1.13", label: "Left thigh armor" },
      right_thigh_core: { ref: "#o1.14", label: "Right thigh structure" },
      right_thigh_armor: { ref: "#o1.15", label: "Right thigh armor" },
      left_knee_actuator: { ref: "#o1.16", label: "Left knee actuator" },
      right_knee_actuator: { ref: "#o1.17", label: "Right knee actuator" },
      left_shin_core: { ref: "#o1.18", label: "Left shin structure" },
      left_shin_armor: { ref: "#o1.19", label: "Left shin armor" },
      right_shin_core: { ref: "#o1.20", label: "Right shin structure" },
      right_shin_armor: { ref: "#o1.21", label: "Right shin armor" },
      left_ankle_joint: { ref: "#o1.22", label: "Left ankle joint" },
      right_ankle_joint: { ref: "#o1.23", label: "Right ankle joint" },
      left_foot_pad: { ref: "#o1.24", label: "Left foot pad" },
      right_foot_pad: { ref: "#o1.25", label: "Right foot pad" },
      left_shoulder_actuator: { ref: "#o1.26", label: "Left shoulder actuator" },
      right_shoulder_actuator: { ref: "#o1.27", label: "Right shoulder actuator" },
      left_upper_arm_core: { ref: "#o1.28", label: "Left upper arm structure" },
      left_upper_arm_armor: { ref: "#o1.29", label: "Left upper arm armor" },
      right_upper_arm_core: { ref: "#o1.30", label: "Right upper arm structure" },
      right_upper_arm_armor: { ref: "#o1.31", label: "Right upper arm armor" },
      left_elbow_actuator: { ref: "#o1.32", label: "Left elbow actuator" },
      right_elbow_actuator: { ref: "#o1.33", label: "Right elbow actuator" },
      left_forearm_core: { ref: "#o1.34", label: "Left forearm structure" },
      left_forearm_armor: { ref: "#o1.35", label: "Left forearm armor" },
      right_forearm_core: { ref: "#o1.36", label: "Right forearm structure" },
      right_forearm_armor: { ref: "#o1.37", label: "Right forearm armor" },
      left_hand_pad: { ref: "#o1.38", label: "Left hand pad" },
      right_hand_pad: { ref: "#o1.39", label: "Right hand pad" },
    },
    parameters: {
      biped_quadruped_blend: {
        type: "number", label: "Biped-quadruped blend",
        description: "0 = upright biped stance, 1 = low quadruped crawl; hips, knees, body pitch, and arm ground contact are coordinated.",
        default: 0, min: 0, max: 1, step: 0.01,
      },
      hip_angle: {
        type: "number", label: "Hip angle", unit: "deg",
        description: "Hip pitch offset added to the pose on both legs; feet stay planted.",
        default: 0, min: -40, max: 40, step: 0.5,
      },
      knee_angle: {
        type: "number", label: "Knee angle", unit: "deg",
        description: "Knee flexion offset added to the pose on both legs.",
        default: 0, min: -20, max: 60, step: 0.5,
      },
      ankle_angle: {
        type: "number", label: "Ankle angle", unit: "deg",
        description: "Foot tilt away from auto-leveled ground contact.",
        default: 0, min: -25, max: 25, step: 0.5,
      },
      shoulder_angle: {
        type: "number", label: "Shoulder angle", unit: "deg",
        description: "Shoulder pitch offset on both arms (biped mode; quadruped mode uses ground-contact IK).",
        default: 0, min: -60, max: 60, step: 0.5,
      },
      elbow_angle: {
        type: "number", label: "Elbow angle", unit: "deg",
        description: "Elbow flexion offset on both arms.",
        default: 0, min: -20, max: 80, step: 0.5,
      },
      stance_width: {
        type: "number", label: "Stance width", unit: "mm",
        description: "Lateral hip spacing; legs and hip pods slide along the crossmember.",
        default: DEFAULT_STANCE, min: 600, max: 900, step: 5,
      },
      walk_cycle: {
        type: "number", label: "Gait phase",
        description: "0-1 phase of the walk (biped) or crawl (quadruped) gait; 0 is the neutral pose.",
        default: 0, min: 0, max: 1, step: 0.01,
      },
      actuator_demo: {
        type: "number", label: "Actuator demo",
        description: "Scripted articulation sweep of the LEFT leg and arm joints while balancing on the right leg.",
        default: 0, min: 0, max: 1, step: 0.01,
      },
      cockpit_access: {
        type: "number", label: "Cockpit access",
        description: "Swings the lap-bar boarding gate up over the cockpit.",
        default: 0, min: 0, max: 1, step: 0.01,
      },
      exploded_distance: {
        type: "number", label: "Explode distance", unit: "mm",
        description: "Separates armor shells, frame, cockpit, actuators, pads, and sensors for the reveal.",
        default: 0, min: 0, max: 800, step: 5,
      },
      frame_exposure_level: {
        type: "number", label: "Frame exposure",
        description: "Fades the armor shells to expose the tubular frame and black understructure.",
        default: 0, min: 0, max: 1, step: 0.01,
      },
      armor_panel_gloss: {
        type: "number", label: "Armor gloss",
        description: "Viewer-time sheen boost on the red armor shells.",
        default: 0.35, min: 0, max: 1, step: 0.01,
      },
      red_panel_hue: {
        type: "number", label: "Armor hue", unit: "deg",
        description: "Viewer-time armor hue shift; 356 keeps the native GD01 red.",
        default: DEFAULT_HUE, min: 0, max: 360, step: 1,
      },
      shell_transparency: {
        type: "number", label: "Shell transparency",
        description: "Makes armor shells translucent to show the mechanism zones.",
        default: 0, min: 0, max: 1, step: 0.01,
      },
      sensor_detail_level: {
        type: "number", label: "Sensor detail",
        description: "0 hides the sensor suite, 1 shows it, 2 adds an emitter glow.",
        default: 2, min: 0, max: 2, step: 1,
      },
      pilot_placeholder_visibility: {
        type: "boolean", label: "Pilot placeholder", default: true,
      },
      accent_color_palette: {
        type: "select", label: "Accent palette", default: "gd01_red",
        options: [
          { value: "gd01_red", label: "GD01 red (native)" },
          { value: "stealth_black", label: "Stealth black" },
          { value: "arctic_silver", label: "Arctic silver" },
          { value: "aurora_blue", label: "Aurora blue" },
        ],
      },
    },
    animations: {
      transformation: {
        label: "Biped-quadruped transformation",
        duration: 10,
        loop: true,
        update({ progress, set }) {
          // out to quadruped and back, with dwell at both ends
          const b = 0.5 - 0.5 * Math.cos(progress * 2 * Math.PI);
          set("biped_quadruped_blend", smoothstep(b * 1.12 - 0.06));
          set("walk_cycle", 0);
          set("actuator_demo", 0);
          set("cockpit_access", 0);
          set("exploded_distance", 0);
        },
      },
      walk_loop: {
        label: "Heroic walk loop",
        duration: 2.4,
        loop: true,
        update({ cycle, set }) {
          set("biped_quadruped_blend", 0);
          set("walk_cycle", cycle % 1);
          set("actuator_demo", 0);
          set("exploded_distance", 0);
        },
      },
      crawl_pose: {
        label: "Quadruped crawl",
        duration: 3.6,
        loop: true,
        update({ cycle, set }) {
          set("biped_quadruped_blend", 1);
          set("walk_cycle", cycle % 1);
          set("actuator_demo", 0);
          set("exploded_distance", 0);
        },
      },
      cockpit_access: {
        label: "Cockpit access",
        duration: 6,
        loop: true,
        update({ progress, set }) {
          let gate = 0;
          if (progress < 0.3) {
            gate = smoothstep(progress / 0.3);
          } else if (progress < 0.65) {
            gate = 1;
          } else {
            gate = 1 - smoothstep((progress - 0.65) / 0.35);
          }
          set("biped_quadruped_blend", 0);
          set("cockpit_access", gate);
          set("walk_cycle", 0);
          set("exploded_distance", 0);
        },
      },
      actuator_demo: {
        label: "Actuator articulation demo",
        duration: 9,
        loop: true,
        update({ progress, set }) {
          set("biped_quadruped_blend", 0);
          set("walk_cycle", 0);
          set("actuator_demo", progress);
          set("exploded_distance", 0);
        },
      },
      exploded_reveal: {
        label: "Exploded reveal",
        duration: 8,
        loop: true,
        update({ progress, set }) {
          const bump = Math.sin(Math.PI * clamp(progress, 0, 1));
          set("biped_quadruped_blend", 0);
          set("walk_cycle", 0);
          set("cockpit_access", 0);
          set("exploded_distance", 720 * smoothstep(bump * 1.15));
          set("frame_exposure_level", 0.45 * smoothstep((bump - 0.55) / 0.45));
        },
      },
    },
  },

  update({ params, features, effects }) {
    const blend = clamp(finite(params.biped_quadruped_blend), 0, 1);
    const walkPhase = finite(params.walk_cycle) % 1;
    const demo = clamp(finite(params.actuator_demo), 0, 1);
    const access = clamp(finite(params.cockpit_access), 0, 1);
    const explode = clamp(finite(params.exploded_distance), 0, 800);
    const exposure = clamp(finite(params.frame_exposure_level), 0, 1);
    const gloss = clamp(finite(params.armor_panel_gloss, 0.35), 0, 1);
    const transparency = clamp(finite(params.shell_transparency), 0, 1);
    const hue = clamp(finite(params.red_panel_hue, DEFAULT_HUE), 0, 360);
    const sensorLevel = Math.round(clamp(finite(params.sensor_detail_level, 2), 0, 2));
    const palette = PALETTES[params.accent_color_palette] !== undefined ? params.accent_color_palette : "gd01_red";

    // --- pivots & segment lengths from the base (neutral) model ------------
    const hipL = featureCenter(features, "left_hip_actuator", [0, 360, 1510]);
    const hipR = featureCenter(features, "right_hip_actuator", [0, -360, 1510]);
    const kneeL = featureCenter(features, "left_knee_actuator", [0, 360, 830]);
    const ankleL = featureCenter(features, "left_ankle_joint", [0, 360, 190]);
    const shoulderL = featureCenter(features, "left_shoulder_actuator", [-200, 590, 2290]);
    const elbowL = featureCenter(features, "left_elbow_actuator", [-200, 620, 1770]);
    const handL = featureCenter(features, "left_hand_pad", [-200, 620, 1120]);
    const gateHinge = featureCenter(features, "cockpit_gate_hinge", [180, 0, 2270]);

    const hipX = hipL[0];
    const hipZ = hipL[2];
    const thighLen = Math.max(hipZ - kneeL[2], 1);
    const shinLen = Math.max(kneeL[2] - ankleL[2], 1);
    const scale = ankleL[2] / 190; // generator: ANKLE_Z = 190 * S
    const upperLen = Math.max(shoulderL[2] - elbowL[2], 1);
    const foreLen = Math.max(elbowL[2] - handL[2], 1);
    // hand-pad feature center sits ~112*S above the dome's ground contact
    const padContactZ = 112 * scale;

    // --- transformation choreography: legs fold, body pitches, arms plant --
    const legsT = smoothstep(blend / 0.6);
    const bodyT = smoothstep((blend - 0.15) / 0.7);
    const armsT = smoothstep((blend - 0.25) / 0.75);

    const bodyPitch = lerp(BIPED_POSE.bodyPitch, QUAD_POSE.bodyPitch, bodyT);

    // --- gait offsets (walk in biped, trot-like crawl in quadruped) --------
    const gaitBlend = smoothstep(blend);
    const hipAmp = lerp(WALK_HIP_AMP, CRAWL_HIP_AMP, gaitBlend);
    const kneeAmp = lerp(WALK_KNEE_AMP, CRAWL_KNEE_AMP, gaitBlend);
    const phase = walkPhase * 2 * Math.PI;
    const gait = {
      left: {
        hip: hipAmp * Math.sin(phase),
        knee: kneeAmp * Math.max(0, Math.sin(phase)),
      },
      right: {
        hip: hipAmp * Math.sin(phase + Math.PI),
        knee: kneeAmp * Math.max(0, Math.sin(phase + Math.PI)),
      },
    };

    // --- actuator demo: scripted sweep of the left leg + arm ---------------
    // five sequential segments: hip, knee, ankle, shoulder, elbow
    const demoSeg = Math.min(4, Math.floor(demo * 5));
    const demoLocal = clamp(demo * 5 - demoSeg, 0, 1);
    const demoWave = Math.sin(demoLocal * Math.PI);
    const demoOffsets = { hip: 0, knee: 0, ankle: 0, shoulder: 0, elbow: 0 };
    if (demo > 0) {
      if (demoSeg === 0) demoOffsets.hip = -34 * demoWave;
      if (demoSeg === 1) { demoOffsets.hip = -22 * demoWave; demoOffsets.knee = 58 * demoWave; }
      if (demoSeg === 2) { demoOffsets.hip = -14 * demoWave; demoOffsets.knee = 30 * demoWave; demoOffsets.ankle = 20 * demoWave; }
      if (demoSeg === 3) demoOffsets.shoulder = 52 * demoWave;
      if (demoSeg === 4) { demoOffsets.shoulder = 26 * demoWave; demoOffsets.elbow = 64 * demoWave; }
    }

    // --- leg pose angles (absolute-from-vertical, forward-positive) --------
    const hipUser = finite(params.hip_angle);
    const kneeUser = finite(params.knee_angle);
    const ankleUser = finite(params.ankle_angle);
    const legPose = (side) => {
      const g = gait[side];
      const isDemoSide = side === "left" && demo > 0;
      const thigh = lerp(BIPED_POSE.thigh, QUAD_POSE.thigh, legsT) + hipUser + g.hip +
        (isDemoSide ? demoOffsets.hip : 0);
      const kneeFlex = Math.max(
        -25,
        lerp(BIPED_POSE.kneeFlex, QUAD_POSE.kneeFlex, legsT) + kneeUser + g.knee +
          (isDemoSide ? demoOffsets.knee : 0)
      );
      const shin = thigh - kneeFlex;
      const foot = ankleUser + (isDemoSide ? demoOffsets.ankle : 0);
      return { thigh, kneeFlex, shin, foot };
    };
    const legL = legPose("left");
    const legR = legPose("right");

    // --- planted-foot body solve: keep the support ankles at base height ---
    const ankleDrop = (leg) =>
      thighLen * Math.cos(degToRad(leg.thigh)) + shinLen * Math.cos(degToRad(leg.shin));
    const ankleReach = (leg) =>
      thighLen * Math.sin(degToRad(leg.thigh)) + shinLen * Math.sin(degToRad(leg.shin));
    const neutralDrop = thighLen + shinLen;
    // during the demo the left leg is airborne, so the body follows the right
    const solveLegs = demo > 0 ? [legR] : [legL, legR];
    let bodyDz = 0;
    let bodyDx = 0;
    for (const leg of solveLegs) {
      bodyDz += (ankleDrop(leg) - neutralDrop) / solveLegs.length;
      bodyDx += -ankleReach(leg) / solveLegs.length;
    }

    // --- shoulder world position under the body transform -------------------
    const shoulderRel = [shoulderL[0] - hipX, shoulderL[2] - hipZ];
    const shoulderSpun = spin2(shoulderRel[0], shoulderRel[1], bodyPitch);
    const shoulderW = [hipX + shoulderSpun[0] + bodyDx, hipZ + shoulderSpun[1] + bodyDz];

    // --- arm pose: FK in biped, ground-contact IK in quadruped -------------
    const shoulderUser = finite(params.shoulder_angle);
    const elbowUser = finite(params.elbow_angle);
    const armPose = (side) => {
      const isDemoSide = side === "left" && demo > 0;
      const armSwing = (side === "left" ? -1 : 1) * WALK_ARM_AMP * Math.sin(phase) * (1 - gaitBlend);
      const fkUpper = BIPED_POSE.shoulder + shoulderUser + armSwing +
        (isDemoSide ? demoOffsets.shoulder : 0);
      const fkFore = fkUpper + BIPED_POSE.elbowFlex + elbowUser +
        (isDemoSide ? demoOffsets.elbow : 0);
      if (armsT <= 0.001) {
        return { upper: fkUpper, fore: fkFore };
      }
      // crawl stepping: hands step in a trot pair with the opposite leg
      const stepPhase = phase + (side === "left" ? Math.PI : 0);
      const stepFwd = 90 * Math.sin(stepPhase) * gaitBlend * (walkPhase > 0 ? 1 : 0);
      const stepLift = 70 * Math.max(0, Math.sin(stepPhase)) * gaitBlend * (walkPhase > 0 ? 1 : 0);
      const targetX = shoulderW[0] + 150 * scale + stepFwd;
      const targetZ = padContactZ + stepLift;
      const dx = targetX - shoulderW[0];
      const dz = targetZ - shoulderW[1];
      const l1 = upperLen;
      const l2 = Math.max(elbowL[2] - handL[2], foreLen); // elbow to hand-pad center
      const dist = clamp(Math.hypot(dx, dz), Math.abs(l1 - l2) + 1, l1 + l2 - 1);
      const chord = (Math.atan2(dx, -dz) * 180) / Math.PI; // forward-positive from straight-down
      const beta1 = (Math.acos(clamp((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1, 1)) * 180) / Math.PI;
      const beta2 = (Math.acos(clamp((l2 * l2 + dist * dist - l1 * l1) / (2 * l2 * dist), -1, 1)) * 180) / Math.PI;
      const ikUpper = chord - beta1; // elbow apex trails behind the chord
      const ikFore = chord + beta2;
      return {
        upper: lerp(fkUpper, ikUpper, armsT),
        fore: lerp(fkFore, ikFore, armsT),
      };
    };
    const armL = armPose("left");
    const armR = armPose("right");

    // --- stance width slide --------------------------------------------------
    const stance = clamp(finite(params.stance_width, DEFAULT_STANCE), 600, 900);
    const stanceShift = (stance / DEFAULT_STANCE - 1) * Math.abs(hipL[1]);

    // --- shared transform builders ------------------------------------------
    const hipMid = [hipX, 0, hipZ];
    const bodySteps = [pitch(hipMid, bodyPitch), { translate: [bodyDx, 0, bodyDz] }];
    const explodeStep = (id) => {
      const dir = EXPLODE_DIRS[id] || [0, 0, 0];
      return { translate: [dir[0] * explode, dir[1] * explode, dir[2] * explode] };
    };
    const apply = (id, steps) => {
      effects.transform(id, { transforms: [...steps, explodeStep(id)] });
    };

    const bodyFeatures = [
      "pelvis_core", "pelvis_armor", "torso_frame", "torso_armor",
      "cockpit_module", "pilot_placeholder", "cockpit_gate_hinge", "sensor_head",
    ];
    for (const id of bodyFeatures) {
      apply(id, bodySteps);
    }
    // boarding gate: hinge swing, then ride the body
    apply("cockpit_gate", [pitch(gateHinge, -104 * smoothstep(access)), ...bodySteps]);

    // --- legs ---------------------------------------------------------------
    const legChain = (side, leg) => {
      const cap = side[0].toUpperCase() + side.slice(1);
      const hip = featureCenter(features, `${side}_hip_actuator`, side === "left" ? hipL : hipR);
      const knee = featureCenter(features, `${side}_knee_actuator`, [0, hip[1], kneeL[2]]);
      const ankle = featureCenter(features, `${side}_ankle_joint`, [0, hip[1], ankleL[2]]);
      const sideSign = side === "left" ? 1 : -1;
      const slide = { translate: [0, sideSign * stanceShift, 0] };
      const hipStep = pitch(hip, leg.thigh - bodyPitch);
      const kneeStep = pitch(knee, -leg.kneeFlex);
      const ankleStep = pitch(ankle, leg.foot - leg.shin);
      apply(`${side}_hip_actuator`, [slide, ...bodySteps]);
      apply(`${side}_thigh_core`, [slide, hipStep, ...bodySteps]);
      apply(`${side}_thigh_armor`, [slide, hipStep, ...bodySteps]);
      apply(`${side}_knee_actuator`, [slide, hipStep, ...bodySteps]);
      apply(`${side}_shin_core`, [slide, kneeStep, hipStep, ...bodySteps]);
      apply(`${side}_shin_armor`, [slide, kneeStep, hipStep, ...bodySteps]);
      apply(`${side}_ankle_joint`, [slide, kneeStep, hipStep, ...bodySteps]);
      apply(`${side}_foot_pad`, [slide, ankleStep, kneeStep, hipStep, ...bodySteps]);
      return cap;
    };
    legChain("left", legL);
    legChain("right", legR);

    // --- arms ---------------------------------------------------------------
    const armChain = (side, arm) => {
      const shoulder = featureCenter(features, `${side}_shoulder_actuator`, shoulderL);
      const elbow = featureCenter(features, `${side}_elbow_actuator`, elbowL);
      const shoulderStep = pitch(shoulder, arm.upper - bodyPitch);
      const elbowStep = pitch(elbow, arm.fore - arm.upper);
      apply(`${side}_shoulder_actuator`, bodySteps);
      apply(`${side}_upper_arm_core`, [shoulderStep, ...bodySteps]);
      apply(`${side}_upper_arm_armor`, [shoulderStep, ...bodySteps]);
      apply(`${side}_elbow_actuator`, [shoulderStep, ...bodySteps]);
      apply(`${side}_forearm_core`, [elbowStep, shoulderStep, ...bodySteps]);
      apply(`${side}_forearm_armor`, [elbowStep, shoulderStep, ...bodySteps]);
      apply(`${side}_hand_pad`, [elbowStep, shoulderStep, ...bodySteps]);
    };
    armChain("left", armL);
    armChain("right", armR);

    // --- style: palette, hue, gloss, transparency, exposure -----------------
    const paletteSpec = PALETTES[palette];
    const armorOpacity = clamp((1 - 0.85 * exposure) * (1 - 0.72 * transparency), 0.08, 1);
    const sheen = gloss * (0.30 - 0.12 * exposure);
    if (paletteSpec) {
      effects.style(ARMOR_FEATURES, {
        color: paletteSpec.color,
        opacity: armorOpacity,
        edgeOpacity: clamp(armorOpacity + 0.25, 0, 1),
        emissive: paletteSpec.emissive,
        emissiveIntensity: paletteSpec.emissiveIntensity,
      });
    } else {
      // native red family: hue shift multiplies cleanly within reds; the gloss
      // sheen rides a warm emissive so highlights read as polished paint.
      const hueColor = Math.round(hue) !== DEFAULT_HUE ? `hsl(${Math.round(hue)}, 88%, 45%)` : "";
      effects.style(ARMOR_FEATURES, {
        color: hueColor,
        opacity: armorOpacity,
        edgeOpacity: clamp(armorOpacity + 0.25, 0, 1),
        emissive: sheen > 0.01 ? "#8c1218" : "",
        emissiveIntensity: sheen > 0.01 ? sheen : 0,
      });
    }

    effects.visible("pilot_placeholder", params.pilot_placeholder_visibility !== false);
    effects.visible("sensor_head", sensorLevel > 0);
    if (sensorLevel >= 2) {
      effects.style("sensor_head", { emissive: "#b45309", emissiveIntensity: 0.10 });
    } else {
      effects.style("sensor_head", { emissive: "", emissiveIntensity: 0 });
    }

    // subtle boarding cue: warm pulse on the gate while it is moving
    if (access > 0.02 && access < 0.98) {
      effects.style("cockpit_gate", {
        emissive: "#7f1d1d",
        emissiveIntensity: 0.25 * Math.sin(Math.PI * access),
      });
    }
    // actuator demo cue: glow the joint currently being exercised
    if (demo > 0.001) {
      const demoTargets = [
        ["left_hip_actuator"],
        ["left_knee_actuator"],
        ["left_ankle_joint"],
        ["left_shoulder_actuator"],
        ["left_elbow_actuator"],
      ][demoSeg];
      effects.style(demoTargets, { emissive: "#b91c1c", emissiveIntensity: 0.35 });
    }
  },
};

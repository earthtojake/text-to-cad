// Mars rover concept — viewer parameter/animation sidecar.
//
// Source geometry parameters (rover_scale, body_length, wheel_diameter,
// wheel_grouser_count, mast_height, antenna_count, science_payload_density,
// terrain_* ...) live in mars_rover_concept.step.py. This module drives the
// pose, style, and animation degrees of freedom at viewer time.
//
// All pivot constants below mirror the DEFAULT source parameter values
// (wheelbase 2500, track 1980, wheel dia 520, clearance 560, deck z 1180).
// Regenerating with different source parameters requires updating them.

const X_AXIS = [1, 0, 0];
const Y_AXIS = [0, 1, 0];
const Z_AXIS = [0, 0, 1];

const BODY_CENTER = [0, 0, 870];
const DECK_Z = 1180;

// Suspension kinematics (left = +Y). Rocker pivots carry the front wheel and
// the bogie; bogies carry the middle and rear wheels. The differential bar on
// deck mirrors the left/right rocker split.
const ROCKER_PIVOT_L = [150, 760, 800];
const ROCKER_PIVOT_R = [150, -760, 800];
const BOGIE_PIVOT_L = [-700, 760, 430];
const BOGIE_PIVOT_R = [-700, -760, 430];
const DIFF_PIVOT = [430, 0, 1235];

const WHEELS = {
  wheel_front_left: { center: [1250, 990, 260], side: 1, steer: "steering_angle_front_left", bogie: false },
  wheel_front_right: { center: [1250, -990, 260], side: -1, steer: "steering_angle_front_right", bogie: false },
  wheel_middle_left: { center: [-150, 990, 260], side: 1, steer: null, bogie: true },
  wheel_middle_right: { center: [-150, -990, 260], side: -1, steer: null, bogie: true },
  wheel_rear_left: { center: [-1250, 990, 260], side: 1, steer: "steering_angle_rear_left", bogie: true },
  wheel_rear_right: { center: [-1250, -990, 260], side: -1, steer: "steering_angle_rear_right", bogie: true }
};
const STEERING_FORKS = {
  steering_front_left: { origin: [1250, 990, 260], side: 1, steer: "steering_angle_front_left", bogie: false },
  steering_front_right: { origin: [1250, -990, 260], side: -1, steer: "steering_angle_front_right", bogie: false },
  steering_rear_left: { origin: [-1250, 990, 260], side: 1, steer: "steering_angle_rear_left", bogie: true },
  steering_rear_right: { origin: [-1250, -990, 260], side: -1, steer: "steering_angle_rear_right", bogie: true }
};

// Mast / arm chain pivots (display pose; angles are deltas from this pose).
const MAST_AXIS_ORIGIN = [780, -380, DECK_Z];
const HEAD_PIVOT = [780, -380, 2200];
const ARM_AZIMUTH = [1160, 200, 715];
const ARM_SHOULDER = [1160, 200, 760];
const ARM_ELBOW = [1761.4, 200, 541.1];
const ARM_WRIST = [2268.9, 200, 304.4];
const ARM_TURRET = [2343.9, 200, 174.5];
const TURRET_AXIS = [0.5, 0, -0.866];        // wrist link direction at -60 deg
const HGA_ELEV_PIVOT = [-520, 420, 1360];
const SOLAR_HINGE_L = [-150, 650, 1186];
const SOLAR_HINGE_R = [-150, -650, 1186];
const SOLAR_DEPLOY_MODELED = 102;            // deg, deploy angle baked into geometry

// Chassis-fixed groups that ride the body pose (suspension, wheels, and the
// terrain are handled separately).
const BODY_GROUPS = [
  "chassis_frame", "body_core", "body_shell", "deck_lid", "side_panel_left",
  "access_panels", "thermal_control", "internals_avionics", "internals_power",
  "science_payloads", "cable_harness", "dust_covers", "dust_layer",
  "differential", "mast_base", "mast_head", "arm_azimuth", "arm_shoulder",
  "arm_elbow", "arm_wrist", "arm_turret", "antenna_hga_mast",
  "antenna_hga_dish", "antenna_uhf", "antenna_whips", "solar_wing_left",
  "solar_wing_right", "power_rtg"
];

// Exploded-view unit offsets (scaled by exploded_distance).
const EXPLODE_VECTORS = {
  body_core: [0, 0, 0.35],
  body_shell: [0, 0, 0.5],
  deck_lid: [0, 0, 1.15],
  side_panel_left: [0, 0.9, 0.15],
  access_panels: [0, -0.8, 0.1],
  thermal_control: [0, -0.35, 0.75],
  internals_avionics: [0, 0, 0.85],
  internals_power: [0.15, -0.2, 0.75],
  science_payloads: [-0.2, 0.15, 0.95],
  cable_harness: [0, 0, 0.3],
  dust_covers: [0, 0, -0.4],
  dust_layer: [0, 0, 1.35],
  rocker_left: [0, 0.45, 0],
  rocker_right: [0, -0.45, 0],
  bogie_left: [0, 0.6, 0],
  bogie_right: [0, -0.6, 0],
  differential: [0, 0, 0.9],
  steering_front_left: [0.15, 0.75, 0.1],
  steering_front_right: [0.15, -0.75, 0.1],
  steering_rear_left: [-0.15, 0.75, 0.1],
  steering_rear_right: [-0.15, -0.75, 0.1],
  wheel_front_left: [0.15, 1.0, 0],
  wheel_front_right: [0.15, -1.0, 0],
  wheel_middle_left: [0, 1.0, 0],
  wheel_middle_right: [0, -1.0, 0],
  wheel_rear_left: [-0.15, 1.0, 0],
  wheel_rear_right: [-0.15, -1.0, 0],
  mast_base: [0, 0, 0.7],
  mast_head: [0, 0, 1.25],
  arm_azimuth: [0.5, 0, 0.35],
  arm_shoulder: [0.8, 0, 0.5],
  arm_elbow: [1.05, 0, 0.6],
  arm_wrist: [1.25, 0, 0.68],
  arm_turret: [1.45, 0, 0.78],
  antenna_hga_mast: [-0.3, 0.5, 0.5],
  antenna_hga_dish: [-0.45, 0.75, 0.85],
  antenna_uhf: [-0.35, -0.6, 0.6],
  antenna_whips: [-0.5, -0.8, 0.45],
  solar_wing_left: [0, 0.85, 0.3],
  solar_wing_right: [0, -0.85, 0.3],
  power_rtg: [-0.95, 0, 0.15]
};

// Accent hardware (each group's first child is its accent part by contract in
// the Python source). Restyled by accent_color_palette; "jpl_orange" keeps
// the source STEP colors untouched.
const ACCENT_PRIMARY_REFS = [
  "#o1.15.1", "#o1.16.1", "#o1.17.1", "#o1.18.1", "#o1.19.1",
  "#o1.20.1", "#o1.21.1", "#o1.22.1", "#o1.23.1",
  "#o1.30.1", "#o1.31.1", "#o1.32.1", "#o1.33.1", "#o1.34.1", "#o1.35.1",
  "#o1.36.1", "#o1.37.1", "#o1.41.1", "#o1.42.1", "#o1.43.1",
  "#o1.5.4", "#o1.6.3", "#o1.40.3"
];
const ACCENT_HUB_REFS = [
  "#o1.24.1", "#o1.25.1", "#o1.26.1", "#o1.27.1", "#o1.28.1", "#o1.29.1"
];
const ACCENT_PALETTES = {
  jpl_orange: null,
  ember_red: { primary: "#e0401f", hub: "#e8b63c" },
  cobalt_blue: { primary: "#2563eb", hub: "#f0b429" },
  solar_gold: { primary: "#f0b429", hub: "#e2e8f0" },
  stealth_graphite: { primary: "#454b52", hub: "#6b7280" }
};

const SHELL_STYLE_TARGETS = ["body_shell", "side_panel_left", "access_panels"];
const DUST_EXTRA_REFS = ["#o1.5.9", "#o1.1.12", "#o1.1.13"]; // lid patch + terrain aprons
const INTERNAL_GROUPS = ["internals_avionics", "internals_power", "science_payloads"];

const TAU = Math.PI * 2;

function finite(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp01(value) {
  return Math.min(Math.max(value, 0), 1);
}

function seg(progress, from, to) {
  return clamp01((progress - from) / (to - from));
}

function bump(t) {
  return Math.sin(Math.PI * clamp01(t));
}

function rot(origin, axis, angleDeg) {
  return { rotate: { axis, origin, angleDeg } };
}

function shift(vector, scaleFactor) {
  return { translate: [vector[0] * scaleFactor, vector[1] * scaleFactor, vector[2] * scaleFactor] };
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/step/assemblies/mars_rover_concept.step"
    },
    units: { length: "mm", angle: "deg", time: "s" },

    features: {
      terrain: { ref: "#o1.1", label: "Terrain diorama", description: "Regolith slab and rocks; the only group that never moves." },
      chassis_frame: { ref: "#o1.2", label: "Chassis frame" },
      body_core: { ref: "#o1.3", label: "Equipment floor" },
      body_shell: { ref: "#o1.4", label: "Body shell panels" },
      deck_lid: { ref: "#o1.5", label: "Cutaway deck lid" },
      side_panel_left: { ref: "#o1.6", label: "Cutaway side panel" },
      access_panels: { ref: "#o1.7", label: "Access panels" },
      thermal_control: { ref: "#o1.8", label: "Thermal control surfaces" },
      internals_avionics: { ref: "#o1.9", label: "Avionics bay" },
      internals_power: { ref: "#o1.10", label: "Battery modules" },
      science_payloads: { ref: "#o1.11", label: "Science payloads" },
      cable_harness: { ref: "#o1.12", label: "Cable harness" },
      dust_covers: { ref: "#o1.13", label: "Dust covers" },
      dust_layer: { ref: "#o1.14", label: "Dust film" },
      rocker_left: { ref: "#o1.15", label: "Rocker (left)", origin: ROCKER_PIVOT_L, axis: Y_AXIS },
      rocker_right: { ref: "#o1.16", label: "Rocker (right)", origin: ROCKER_PIVOT_R, axis: Y_AXIS },
      bogie_left: { ref: "#o1.17", label: "Bogie (left)", origin: BOGIE_PIVOT_L, axis: Y_AXIS },
      bogie_right: { ref: "#o1.18", label: "Bogie (right)", origin: BOGIE_PIVOT_R, axis: Y_AXIS },
      differential: { ref: "#o1.19", label: "Differential bar", origin: DIFF_PIVOT, axis: Z_AXIS },
      steering_front_left: { ref: "#o1.20", label: "Steering fork FL", origin: STEERING_FORKS.steering_front_left.origin, axis: Z_AXIS },
      steering_front_right: { ref: "#o1.21", label: "Steering fork FR", origin: STEERING_FORKS.steering_front_right.origin, axis: Z_AXIS },
      steering_rear_left: { ref: "#o1.22", label: "Steering fork RL", origin: STEERING_FORKS.steering_rear_left.origin, axis: Z_AXIS },
      steering_rear_right: { ref: "#o1.23", label: "Steering fork RR", origin: STEERING_FORKS.steering_rear_right.origin, axis: Z_AXIS },
      wheel_front_left: { ref: "#o1.24", label: "Wheel FL", origin: WHEELS.wheel_front_left.center, axis: Y_AXIS },
      wheel_front_right: { ref: "#o1.25", label: "Wheel FR", origin: WHEELS.wheel_front_right.center, axis: Y_AXIS },
      wheel_middle_left: { ref: "#o1.26", label: "Wheel ML", origin: WHEELS.wheel_middle_left.center, axis: Y_AXIS },
      wheel_middle_right: { ref: "#o1.27", label: "Wheel MR", origin: WHEELS.wheel_middle_right.center, axis: Y_AXIS },
      wheel_rear_left: { ref: "#o1.28", label: "Wheel RL", origin: WHEELS.wheel_rear_left.center, axis: Y_AXIS },
      wheel_rear_right: { ref: "#o1.29", label: "Wheel RR", origin: WHEELS.wheel_rear_right.center, axis: Y_AXIS },
      mast_base: { ref: "#o1.30", label: "Mast", origin: MAST_AXIS_ORIGIN, axis: Z_AXIS },
      mast_head: { ref: "#o1.31", label: "Remote sensing head", origin: HEAD_PIVOT, axis: Y_AXIS },
      arm_azimuth: { ref: "#o1.32", label: "Arm azimuth drum", origin: ARM_AZIMUTH, axis: Z_AXIS },
      arm_shoulder: { ref: "#o1.33", label: "Arm upper link", origin: ARM_SHOULDER, axis: Y_AXIS },
      arm_elbow: { ref: "#o1.34", label: "Arm forearm", origin: ARM_ELBOW, axis: Y_AXIS },
      arm_wrist: { ref: "#o1.35", label: "Arm wrist", origin: ARM_WRIST, axis: Y_AXIS },
      arm_turret: { ref: "#o1.36", label: "Instrument turret", origin: ARM_TURRET, axis: TURRET_AXIS },
      antenna_hga_mast: { ref: "#o1.37", label: "HGA pedestal" },
      antenna_hga_dish: { ref: "#o1.38", label: "HGA dish", origin: HGA_ELEV_PIVOT, axis: Y_AXIS },
      antenna_uhf: { ref: "#o1.39", label: "UHF helix" },
      antenna_whips: { ref: "#o1.40", label: "Low-gain antennas" },
      solar_wing_left: { ref: "#o1.41", label: "Solar wing (left)", origin: SOLAR_HINGE_L, axis: X_AXIS },
      solar_wing_right: { ref: "#o1.42", label: "Solar wing (right)", origin: SOLAR_HINGE_R, axis: X_AXIS },
      power_rtg: { ref: "#o1.43", label: "RTG power module" },
      lid_dust: { ref: "#o1.5.9", label: "Deck lid dust patch" }
    },

    parameters: {
      wheel_drive_angle: { type: "number", label: "Wheel drive", description: "Common drive rotation of all six wheels about their axles.", default: 0, min: 0, max: 360, step: 1, unit: "deg" },
      steering_angle_front_left: { type: "number", label: "Steer FL", description: "Front-left steering yaw about the vertical axis through the wheel center.", default: 0, min: -60, max: 60, step: 0.5, unit: "deg" },
      steering_angle_front_right: { type: "number", label: "Steer FR", default: 0, min: -60, max: 60, step: 0.5, unit: "deg" },
      steering_angle_rear_left: { type: "number", label: "Steer RL", default: 0, min: -60, max: 60, step: 0.5, unit: "deg" },
      steering_angle_rear_right: { type: "number", label: "Steer RR", default: 0, min: -60, max: 60, step: 0.5, unit: "deg" },
      rocker_angle: { type: "number", label: "Rocker split", description: "Differential rocker articulation: +tips the left front wheel down, right up. The deck differential bar follows.", default: 0, min: -12, max: 12, step: 0.1, unit: "deg" },
      bogie_angle: { type: "number", label: "Bogie pitch", description: "Bogie articulation about both bogie pivots (middle/rear wheel pairs).", default: 0, min: -15, max: 15, step: 0.1, unit: "deg" },
      suspension_travel: { type: "number", label: "Suspension travel", description: "Body heave over the wheels: positive compresses (body drops).", default: 0, min: -80, max: 80, step: 1, unit: "mm" },
      chassis_pitch_angle: { type: "number", label: "Chassis pitch", default: 0, min: -10, max: 10, step: 0.1, unit: "deg" },
      chassis_roll_angle: { type: "number", label: "Chassis roll", default: 0, min: -8, max: 8, step: 0.1, unit: "deg" },
      mast_yaw_angle: { type: "number", label: "Mast yaw", description: "Pans the remote sensing head about the mast axis.", default: 0, min: -170, max: 170, step: 1, unit: "deg" },
      mast_pitch_angle: { type: "number", label: "Mast pitch", description: "Tilts the camera head; positive looks up.", default: 0, min: -25, max: 60, step: 0.5, unit: "deg" },
      robotic_arm_base_angle: { type: "number", label: "Arm azimuth", default: 0, min: -45, max: 45, step: 0.5, unit: "deg" },
      robotic_arm_shoulder_angle: { type: "number", label: "Arm shoulder", description: "Positive raises the upper arm from the sampling-hover pose.", default: 0, min: -35, max: 60, step: 0.5, unit: "deg" },
      robotic_arm_elbow_angle: { type: "number", label: "Arm elbow", default: 0, min: -45, max: 75, step: 0.5, unit: "deg" },
      robotic_arm_wrist_angle: { type: "number", label: "Arm wrist", default: 0, min: -60, max: 70, step: 0.5, unit: "deg" },
      instrument_turret_rotation: { type: "number", label: "Turret rotation", description: "Spins the instrument carousel about the wrist axis.", default: 0, min: -180, max: 180, step: 1, unit: "deg" },
      antenna_angle: { type: "number", label: "HGA elevation", description: "High-gain dish elevation delta from its 35 deg display pose.", default: 0, min: -15, max: 55, step: 0.5, unit: "deg" },
      solar_panel_deploy_angle: { type: "number", label: "Solar deploy", description: "Wing hinge angle: 20 leans the wings stowed against the body flanks (lower values would sweep through the rocker tubes); 102 is the display cruise pose.", default: 102, min: 20, max: 115, step: 0.5, unit: "deg" },
      rtg_module_visibility: { type: "boolean", label: "RTG module", default: true },
      cable_harness_visibility: { type: "boolean", label: "Cable harness", default: true },
      dust_cover_opacity: { type: "number", label: "Dust covers", description: "Opacity of the pivot boots and mast bellows.", default: 1, min: 0, max: 1, step: 0.01 },
      dust_accumulation_level: { type: "number", label: "Dust buildup", description: "Martian dust film intensity on deck, panels, and terrain aprons.", default: 0.35, min: 0, max: 1, step: 0.01 },
      shell_transparency: { type: "number", label: "Shell X-ray", description: "Fades the body shell to reveal internal packaging without moving panels.", default: 0, min: 0, max: 1, step: 0.01 },
      cutaway_fraction: { type: "number", label: "Cutaway reveal", description: "Lifts the front deck lid and swings the left side panel open.", default: 0, min: 0, max: 1, step: 0.01 },
      accent_color_palette: {
        type: "select", label: "Accent palette", default: "jpl_orange",
        options: [
          { value: "jpl_orange", label: "JPL orange (source)" },
          { value: "ember_red", label: "Ember red" },
          { value: "cobalt_blue", label: "Cobalt blue" },
          { value: "solar_gold", label: "Solar gold" },
          { value: "stealth_graphite", label: "Stealth graphite" }
        ]
      },
      exploded_distance: { type: "number", label: "Explode", description: "Radial/vertical assembly separation distance.", default: 0, min: 0, max: 600, step: 5, unit: "mm" }
    },

    animations: {
      terrain_traverse: {
        label: "Terrain traverse",
        description: "All six wheels roll while the rocker-bogie articulates over uneven ground.",
        duration: 14,
        loop: true,
        update({ progress, cycle, set }) {
          set("wheel_drive_angle", (cycle * 720) % 360);
          set("rocker_angle", 6 * Math.sin(TAU * progress));
          set("bogie_angle", 8 * Math.sin(TAU * progress + 1.1));
          set("suspension_travel", 22 * Math.sin(2 * TAU * progress + 0.4));
          set("chassis_pitch_angle", 3.2 * Math.sin(TAU * progress + 0.7));
          set("chassis_roll_angle", 2.4 * Math.sin(TAU * progress + 2.2));
          set("steering_angle_front_left", 3 * Math.sin(TAU * progress + 3.0));
          set("steering_angle_front_right", 3 * Math.sin(TAU * progress + 3.0));
        }
      },
      steering_sweep: {
        label: "Steering sweep",
        description: "Coordinated four-corner steering with Ackermann-style inner/outer split.",
        duration: 8,
        loop: true,
        update({ progress, cycle, set }) {
          const sweep = Math.sin(TAU * progress);
          set("steering_angle_front_left", 48 * sweep);
          set("steering_angle_front_right", 38 * sweep);
          set("steering_angle_rear_left", -48 * sweep);
          set("steering_angle_rear_right", -38 * sweep);
          set("wheel_drive_angle", (cycle * 360) % 360);
        }
      },
      suspension_cycle: {
        label: "Suspension cycle",
        description: "Compression/rebound heave with rocker and bogie follow-through.",
        duration: 6,
        loop: true,
        update({ progress, set }) {
          set("suspension_travel", 70 * Math.sin(TAU * progress));
          set("bogie_angle", 6 * Math.sin(TAU * progress));
          set("rocker_angle", 4 * Math.sin(TAU * progress));
          set("chassis_pitch_angle", 1.5 * Math.sin(TAU * progress + 1.57));
        }
      },
      mast_scan: {
        label: "Mast scan",
        description: "Remote-sensing head pans the horizon and tilts through a survey nod.",
        duration: 10,
        loop: true,
        update({ progress, set }) {
          set("mast_yaw_angle", 120 * Math.sin(TAU * progress));
          set("mast_pitch_angle", 22 - 22 * Math.cos(TAU * progress));
        }
      },
      arm_deploy: {
        label: "Arm deploy",
        description: "Multi-joint arm sweep with instrument turret positioning.",
        duration: 12,
        loop: true,
        update({ progress, set }) {
          set("robotic_arm_base_angle", 28 * Math.sin(TAU * progress));
          set("robotic_arm_shoulder_angle", 20 * Math.sin(TAU * progress + 0.6));
          set("robotic_arm_elbow_angle", 26 * Math.sin(TAU * progress + 1.1));
          set("robotic_arm_wrist_angle", 24 * Math.sin(2 * TAU * progress));
          set("instrument_turret_rotation", 180 * Math.sin(TAU * progress));
        }
      },
      antenna_and_solar: {
        label: "Antennas + solar deploy",
        description: "HGA elevation slew plus a full solar-wing stow/deploy cycle.",
        duration: 10,
        loop: true,
        update({ progress, set }) {
          set("antenna_angle", 24 - 24 * Math.cos(TAU * progress));
          set("solar_panel_deploy_angle", 102 - 41 * (1 - Math.cos(TAU * progress)));
        }
      },
      cutaway_reveal: {
        label: "Cutaway reveal",
        description: "Deck lid lifts and the side panel swings open over the avionics bays.",
        duration: 9,
        loop: true,
        update({ progress, set }) {
          const f = (1 - Math.cos(TAU * progress)) / 2;
          set("cutaway_fraction", f);
          set("shell_transparency", 0.65 * f);
          set("dust_cover_opacity", 1 - 0.6 * f);
        }
      },
      exploded_assembly: {
        label: "Exploded assembly",
        description: "Separates wheels, suspension, panels, mast, arm, antennas, power, and payloads.",
        duration: 12,
        loop: true,
        update({ progress, set }) {
          set("exploded_distance", 600 * (1 - Math.cos(TAU * progress)) / 2);
        }
      },
      grand_tour: {
        label: "Grand tour",
        description: "Traverse, steering, mast scan, arm work, antennas, cutaway, and explode in one take.",
        duration: 32,
        loop: true,
        update({ progress, cycle, set }) {
          set("wheel_drive_angle", (cycle * 1440) % 360);
          const a = bump(seg(progress, 0.0, 0.2));
          set("rocker_angle", 6 * Math.sin(5 * TAU * progress) * a);
          set("bogie_angle", 8 * Math.sin(5 * TAU * progress + 1.1) * a);
          set("suspension_travel", 20 * Math.sin(10 * TAU * progress) * a);
          set("chassis_pitch_angle", 3 * Math.sin(5 * TAU * progress + 0.7) * a);
          const b = seg(progress, 0.2, 0.32);
          const sweep = Math.sin(TAU * b);
          set("steering_angle_front_left", 48 * sweep);
          set("steering_angle_front_right", 38 * sweep);
          set("steering_angle_rear_left", -48 * sweep);
          set("steering_angle_rear_right", -38 * sweep);
          const c = seg(progress, 0.32, 0.45);
          set("mast_yaw_angle", 120 * Math.sin(TAU * c));
          set("mast_pitch_angle", 40 * bump(c));
          const d = seg(progress, 0.45, 0.62);
          set("robotic_arm_base_angle", 28 * Math.sin(TAU * d));
          set("robotic_arm_shoulder_angle", 22 * bump(d));
          set("robotic_arm_elbow_angle", -30 * bump(d));
          set("robotic_arm_wrist_angle", 28 * Math.sin(TAU * d));
          set("instrument_turret_rotation", 180 * Math.sin(TAU * d));
          const e = seg(progress, 0.62, 0.74);
          set("antenna_angle", 48 * bump(e));
          set("solar_panel_deploy_angle", 102 - 82 * bump(e));
          const f = seg(progress, 0.74, 0.88);
          set("cutaway_fraction", bump(f));
          set("shell_transparency", 0.6 * bump(f));
          const g = seg(progress, 0.88, 1.0);
          set("exploded_distance", 520 * bump(g));
        }
      }
    }
  },

  update({ params, effects }) {
    const drive = finite(params.wheel_drive_angle);
    const rocker = finite(params.rocker_angle);
    const bogiePitch = finite(params.bogie_angle);
    const travel = finite(params.suspension_travel);
    const pitch = finite(params.chassis_pitch_angle);
    const roll = finite(params.chassis_roll_angle);
    const explode = finite(params.exploded_distance);
    const cutaway = clamp01(finite(params.cutaway_fraction));
    const shellFade = clamp01(finite(params.shell_transparency));
    const dust = clamp01(finite(params.dust_accumulation_level));
    const bootOpacity = clamp01(finite(params.dust_cover_opacity, 1));

    // Chassis pose applied to every body-mounted group. Suspension groups get
    // the same pose after their own articulation so the pivots stay attached.
    const chassisT = [
      rot(BODY_CENTER, X_AXIS, roll),
      rot(BODY_CENTER, Y_AXIS, pitch),
      { translate: [0, 0, -travel] }
    ];
    const rockerRot = {
      left: rot(ROCKER_PIVOT_L, Y_AXIS, rocker),
      right: rot(ROCKER_PIVOT_R, Y_AXIS, -rocker)
    };
    const bogieRot = {
      left: rot(BOGIE_PIVOT_L, Y_AXIS, bogiePitch),
      right: rot(BOGIE_PIVOT_R, Y_AXIS, bogiePitch)
    };
    const explodeFor = (id) => {
      const vec = EXPLODE_VECTORS[id];
      return vec && explode > 0 ? [shift(vec, explode)] : [];
    };

    for (const id of BODY_GROUPS) {
      const extra = [];
      if (id === "differential") {
        extra.push(rot(DIFF_PIVOT, Z_AXIS, rocker * 0.5));
      }
      if (id === "mast_head") {
        extra.push(rot(HEAD_PIVOT, Y_AXIS, -finite(params.mast_pitch_angle)));
        extra.push(rot(MAST_AXIS_ORIGIN, Z_AXIS, finite(params.mast_yaw_angle)));
      }
      if (id === "arm_azimuth") {
        extra.push(rot(ARM_AZIMUTH, Z_AXIS, finite(params.robotic_arm_base_angle)));
      }
      if (id === "arm_shoulder" || id === "arm_elbow" || id === "arm_wrist" || id === "arm_turret") {
        if (id === "arm_turret") {
          extra.push(rot(ARM_TURRET, TURRET_AXIS, finite(params.instrument_turret_rotation)));
        }
        if (id === "arm_wrist" || id === "arm_turret") {
          extra.push(rot(ARM_WRIST, Y_AXIS, -finite(params.robotic_arm_wrist_angle)));
        }
        if (id !== "arm_shoulder") {
          extra.push(rot(ARM_ELBOW, Y_AXIS, -finite(params.robotic_arm_elbow_angle)));
        }
        extra.push(rot(ARM_SHOULDER, Y_AXIS, -finite(params.robotic_arm_shoulder_angle)));
        extra.push(rot(ARM_AZIMUTH, Z_AXIS, finite(params.robotic_arm_base_angle)));
      }
      if (id === "antenna_hga_dish") {
        extra.push(rot(HGA_ELEV_PIVOT, Y_AXIS, finite(params.antenna_angle)));
      }
      if (id === "solar_wing_left") {
        extra.push(rot(SOLAR_HINGE_L, X_AXIS, finite(params.solar_panel_deploy_angle, SOLAR_DEPLOY_MODELED) - SOLAR_DEPLOY_MODELED));
      }
      if (id === "solar_wing_right") {
        extra.push(rot(SOLAR_HINGE_R, X_AXIS, SOLAR_DEPLOY_MODELED - finite(params.solar_panel_deploy_angle, SOLAR_DEPLOY_MODELED)));
      }
      if (id === "deck_lid" && cutaway > 0) {
        extra.push({ translate: [0, 0, 420 * cutaway] });
      }
      if (id === "side_panel_left" && cutaway > 0) {
        extra.push(rot([0, 650, 570], X_AXIS, -75 * cutaway));
      }
      effects.transform(id, { transforms: [...extra, ...chassisT, ...explodeFor(id)] });
    }

    for (const [id, spec] of Object.entries({ rocker_left: "left", rocker_right: "right" })) {
      effects.transform(id, { transforms: [rockerRot[spec], ...chassisT, ...explodeFor(id)] });
    }
    for (const [id, spec] of Object.entries({ bogie_left: "left", bogie_right: "right" })) {
      effects.transform(id, { transforms: [bogieRot[spec], rockerRot[spec], ...chassisT, ...explodeFor(id)] });
    }
    for (const [id, fork] of Object.entries(STEERING_FORKS)) {
      const sideKey = fork.side > 0 ? "left" : "right";
      const chain = [rot(fork.origin, Z_AXIS, finite(params[fork.steer]))];
      if (fork.bogie) {
        chain.push(bogieRot[sideKey]);
      }
      chain.push(rockerRot[sideKey], ...chassisT, ...explodeFor(id));
      effects.transform(id, { transforms: chain });
    }
    for (const [id, wheelSpec] of Object.entries(WHEELS)) {
      const sideKey = wheelSpec.side > 0 ? "left" : "right";
      const chain = [rot(wheelSpec.center, Y_AXIS, drive)];
      if (wheelSpec.steer) {
        chain.push(rot(wheelSpec.center, Z_AXIS, finite(params[wheelSpec.steer])));
      }
      if (wheelSpec.bogie) {
        chain.push(bogieRot[sideKey]);
      }
      chain.push(rockerRot[sideKey], ...chassisT, ...explodeFor(id));
      effects.transform(id, { transforms: chain });
    }

    // Visibility and style state.
    effects.visible("power_rtg", params.rtg_module_visibility !== false);
    effects.visible("cable_harness", params.cable_harness_visibility !== false);
    effects.visible("dust_covers", bootOpacity > 0.02);
    effects.style("dust_covers", { opacity: bootOpacity });
    effects.visible("dust_layer", dust > 0.02);
    effects.style("dust_layer", { opacity: dust });
    for (const ref of DUST_EXTRA_REFS) {
      effects.visible(ref, dust > 0.02);
      effects.style(ref, { opacity: dust });
    }

    const shellOpacity = 1 - 0.9 * Math.max(shellFade, cutaway * 0.35);
    effects.style(SHELL_STYLE_TARGETS, {
      opacity: shellOpacity,
      edgeOpacity: Math.max(0.15, shellOpacity)
    });
    effects.style("deck_lid", {
      opacity: Math.min(shellOpacity, 1 - 0.75 * cutaway),
      edgeOpacity: Math.max(0.15, 1 - 0.75 * cutaway)
    });
    if (cutaway > 0.25) {
      effects.style(INTERNAL_GROUPS, {
        emissive: "#b45309",
        emissiveIntensity: 0.16 * clamp01((cutaway - 0.25) / 0.75)
      });
    }

    const palette = ACCENT_PALETTES[params.accent_color_palette] || null;
    if (palette) {
      effects.style(ACCENT_PRIMARY_REFS, { color: palette.primary });
      effects.style(ACCENT_HUB_REFS, { color: palette.hub });
    }
  }
};

// F1 concept car — STEP parameter sidecar.
//
// Three normalized parameters, all driven by solved geometry rather than by
// eyeballed keyframes:
//
//   drs       0..1   rear wing flap swings open about its visible pivot, with
//                    the bellcrank and link solved as a proper four-bar so the
//                    linkage stays closed at every intermediate value.
//   steering -1..1   rack translates; each front wheel's angle is then solved
//                    independently against its own fixed-length track rod, so
//                    the two sides differ slightly (the hardpoints give about
//                    half a degree of anti-Ackermann at full lock).
//   explode   0..1   staged teardown. First third lifts the bodywork panels
//                    away; the rest walks the exposed internals outward by
//                    system, in sequence, so the car comes apart in readable
//                    layers instead of becoming a cloud of debris.
//
// The solve and the wiring are one file by necessity (see KINEMATICS below),
// but the solve is exported by name as well as bundled into the default
// export, so it can be checked under node without a viewer.
//
// WHAT STEERING MOVES, AND WHY IT IS NOT EVERYTHING. The upright, wheel, brake,
// track rod and rack move. The pushrods and rockers deliberately DO NOT: both
// front ball joints sit exactly on the steer axis (spec.F_LOWER_BALL and
// spec.F_UPPER_BALL define it), which is precisely why steering does not
// disturb the wishbones or anything inboard of them. That is the real
// geometry — animating the rockers here would look busier and be wrong.


// ===========================================================================
// KINEMATICS
//
// Inlined deliberately. The viewer's asset gate (`_is_declared_params_sidecar`
// in viewer/server_py/scanner.py) serves ONLY the exact file a package
// descriptor names as `paramsPath` — a sibling module next to it is not
// served, so `import "./f1_kinematics.js"` 404s in the browser even though it
// resolves fine under node. A parameter sidecar therefore has to be one file.
//
// Everything below is SOLVED from the real hardpoints in f1_parts/spec.py, not
// eyeballed:
//   DRS       a planar four-bar solved as a circle-circle intersection,
//             branch-locked to the closed pose so it never snaps through.
//   STEERING  parameterised by RACK DISPLACEMENT, not by wheel angle. The rack
//             is one bar, so both wheels take the same d and each wheel's angle
//             is then solved against its own track rod — the two sides differ
//             slightly, which is where the anti-Ackermann comes from.
//
// Angle convention matches spec.py: a positive "incidence" lifts a trailing
// edge, which is exactly a right-handed rotation about +Y.
// ===========================================================================

// ---------------------------------------------------------------- hardpoints
// Mirrors of the constants in f1_parts/spec.py. Keep in sync by hand — these
// are a viewer-time copy, spec.py remains the source of truth.
export const HP = {
  // DRS four-bar (all in the y = DRS_LINK_Y plane)
  DRS_PIVOT: [-3985.0, 872.0],           // (x, z)
  DRS_CRANK_PIVOT: [-3894.0, 800.0],     // (x, z)
  DRS_CRANK_R: 66.0,
  DRS_CRANK_ANGLE_CLOSED_DEG: 118.0,
  DRS_LUG_R: 88.0,
  DRS_LUG_ANGLE_CLOSED_DEG: 214.0,
  DRS_LINK_Y: 462.0,
  FLAP_INC_CLOSED_DEG: 34.0,
  FLAP_INC_OPEN_DEG: -30.0,

  // Front suspension, LEFT side (right side is the y-mirror)
  F_LOWER_BALL: [6.0, 762.0, 166.0],
  F_UPPER_BALL: [-10.0, 742.0, 548.0],
  F_TRACKROD_OUT: [152.0, 736.0, 512.0],
  F_RACK_END: [152.0, 318.0, 505.0],
  MAX_RACK_TRAVEL: 55.4, // mm at full lock — measured, see the solve below
};

// ------------------------------------------------------------------ vec utils
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const len = (a) => Math.sqrt(dot(a, a));
const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const norm = (a) => scale(a, 1 / (len(a) || 1));
export const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
export const clamp01 = (v) => clamp(Number(v) || 0, 0, 1);
export const smoothstep = (t) => {
  const u = clamp01(t);
  return u * u * (3 - 2 * u);
};
/** Eased window: 0 before `a`, 1 after `b`, smooth between. */
export const window01 = (a, b, u) => smoothstep((u - a) / Math.max(b - a, 1e-6));

/** Rodrigues rotation of `p` about the axis through `origin` along `axis`. */
export function rotateAboutAxis(p, origin, axis, deg) {
  const a = (deg * Math.PI) / 180;
  const k = norm(axis);
  const v = sub(p, origin);
  const c = Math.cos(a);
  const s = Math.sin(a);
  return add(
    origin,
    add(add(scale(v, c), scale(cross(k, v), s)), scale(k, dot(k, v) * (1 - c)))
  );
}

// ------------------------------------------------------------------- DRS
const dist2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const polar = (c, r, deg) => [
  c[0] + r * Math.cos((deg * Math.PI) / 180),
  c[1] + r * Math.sin((deg * Math.PI) / 180),
];

const LUG_CLOSED = polar(HP.DRS_PIVOT, HP.DRS_LUG_R, HP.DRS_LUG_ANGLE_CLOSED_DEG);
const CRANK_END_CLOSED = polar(
  HP.DRS_CRANK_PIVOT,
  HP.DRS_CRANK_R,
  HP.DRS_CRANK_ANGLE_CLOSED_DEG
);
export const DRS_LINK_L = dist2(CRANK_END_CLOSED, LUG_CLOSED);
export const DRS_TRAVEL_DEG = HP.FLAP_INC_OPEN_DEG - HP.FLAP_INC_CLOSED_DEG; // -64

/** Rotate a 2D (x, z) point about a pivot; +deg lifts a trailing edge. */
function rotIncidence2(p, pivot, deg) {
  const a = (deg * Math.PI) / 180;
  const ca = Math.cos(a);
  const sa = Math.sin(a);
  const dx = p[0] - pivot[0];
  const dz = p[1] - pivot[1];
  return [pivot[0] + dx * ca + dz * sa, pivot[1] - dx * sa + dz * ca];
}

/**
 * Solve the DRS four-bar at normalized travel `t` (0 shut, 1 fully open).
 * Returns the flap angle, the crank angle delta, and both link end points.
 * The circle-circle solve has two roots; we lock to the branch that
 * reproduces the closed pose so the linkage never snaps through.
 */
export function solveDrs(t) {
  const flapDeg = DRS_TRAVEL_DEG * clamp01(t);
  const lug = rotIncidence2(LUG_CLOSED, HP.DRS_PIVOT, flapDeg);

  const C = HP.DRS_CRANK_PIVOT;
  const dx = lug[0] - C[0];
  const dz = lug[1] - C[1];
  const d = Math.hypot(dx, dz);
  const R = HP.DRS_CRANK_R;
  const L = DRS_LINK_L;

  let end = CRANK_END_CLOSED;
  if (d <= R + L && d >= Math.abs(R - L) && d > 1e-9) {
    const a = (R * R - L * L + d * d) / (2 * d);
    const h = Math.sqrt(Math.max(R * R - a * a, 0));
    const mx = C[0] + (a * dx) / d;
    const mz = C[1] + (a * dz) / d;
    const s1 = [mx + (h * -dz) / d, mz + (h * dx) / d];
    const s2 = [mx - (h * -dz) / d, mz - (h * dx) / d];
    // branch lock: at t = 0 this must reproduce CRANK_END_CLOSED
    end = dist2(s1, CRANK_END_CLOSED) <= dist2(s2, CRANK_END_CLOSED) ? s1 : s2;
  }

  const angOf = (p) =>
    (Math.atan2(p[1] - C[1], p[0] - C[0]) * 180) / Math.PI;
  const crankDeltaDeg = angOf(end) - HP.DRS_CRANK_ANGLE_CLOSED_DEG;

  return {
    flapDeg,
    crankDeltaDeg,
    crankEnd: end,
    lug,
    crankEnd0: CRANK_END_CLOSED,
    lug0: LUG_CLOSED,
  };
}

// --------------------------------------------------------------- STEERING
function mirrorY(p) {
  return [p[0], -p[1], p[2]];
}

/** Steer-axis origin and direction for one side. */
export function steerAxis(side) {
  const lb = side > 0 ? HP.F_LOWER_BALL : mirrorY(HP.F_LOWER_BALL);
  const ub = side > 0 ? HP.F_UPPER_BALL : mirrorY(HP.F_UPPER_BALL);
  return { origin: lb, dir: norm(sub(ub, lb)) };
}

const TRACK_ROD_L = len(sub(HP.F_TRACKROD_OUT, HP.F_RACK_END));

/**
 * Given a rack displacement `d` (mm, +y), solve ONE wheel's steer angle.
 *
 * The track rod is a fixed-length link between the rack end (which translates
 * with the rack) and the steering-arm ball (which swings about the steer axis),
 * so the angle is the root of |P(theta) - rackEnd(d)| = L. Solved by bisection
 * on a bracket around zero — Newton is unnecessary here and bisection cannot
 * jump branches, which matters because the far root folds the upright over.
 */
export function solveSteerAngle(side, d) {
  const { origin, dir } = steerAxis(side);
  const arm = side > 0 ? HP.F_TRACKROD_OUT : mirrorY(HP.F_TRACKROD_OUT);
  const rack0 = side > 0 ? HP.F_RACK_END : mirrorY(HP.F_RACK_END);
  const rack = [rack0[0], rack0[1] + d, rack0[2]];

  const err = (deg) => len(sub(rotateAboutAxis(arm, origin, dir, deg), rack)) - TRACK_ROD_L;

  let lo = -34;
  let hi = 34;
  let flo = err(lo);
  let fhi = err(hi);
  if (flo * fhi > 0) {
    // No sign change in the bracket: clamp to whichever end is closer rather
    // than returning a bogus root.
    return Math.abs(flo) < Math.abs(fhi) ? lo : hi;
  }
  for (let i = 0; i < 60; i += 1) {
    const mid = 0.5 * (lo + hi);
    const fm = err(mid);
    if (flo * fm <= 0) {
      hi = mid;
      fhi = fm;
    } else {
      lo = mid;
      flo = fm;
    }
  }
  return 0.5 * (lo + hi);
}

/**
 * Full steering state for a normalized input in [-1, 1].
 * Positive steers LEFT (the car's +Y side is the inside of the turn).
 */
export function solveSteering(s) {
  const d = clamp(Number(s) || 0, -1, 1) * HP.MAX_RACK_TRAVEL;
  const left = solveSteerAngle(1, d);
  const right = solveSteerAngle(-1, d);
  return {
    rackDy: d,
    leftDeg: left,
    rightDeg: right,
    leftAxis: steerAxis(1),
    rightAxis: steerAxis(-1),
    // Track-rod endpoints, so the rod can be re-aimed rigidly.
    leftRod: {
      from0: HP.F_RACK_END,
      to0: HP.F_TRACKROD_OUT,
      from1: [HP.F_RACK_END[0], HP.F_RACK_END[1] + d, HP.F_RACK_END[2]],
      to1: rotateAboutAxis(HP.F_TRACKROD_OUT, steerAxis(1).origin, steerAxis(1).dir, left),
    },
    rightRod: {
      from0: mirrorY(HP.F_RACK_END),
      to0: mirrorY(HP.F_TRACKROD_OUT),
      from1: [HP.F_RACK_END[0], -HP.F_RACK_END[1] + d, HP.F_RACK_END[2]],
      to1: rotateAboutAxis(
        mirrorY(HP.F_TRACKROD_OUT),
        steerAxis(-1).origin,
        steerAxis(-1).dir,
        right
      ),
    },
  };
}

/**
 * Rigid transform steps that carry a two-ended member from (a0,b0) to (a1,b1).
 * Used for the track rods and the DRS link: rotate about the member's own first
 * end, then translate that end onto its new position. Exact whenever the two
 * lengths match, which the four-bar and the rack solve both guarantee.
 */
export function reaimSteps(a0, b0, a1, b1) {
  const v0 = sub(b0, a0);
  const v1 = sub(b1, a1);
  const n0 = norm(v0);
  const n1 = norm(v1);
  const axis = cross(n0, n1);
  const s = len(axis);
  const c = clamp(dot(n0, n1), -1, 1);
  const steps = [];
  if (s > 1e-9) {
    const deg = (Math.atan2(s, c) * 180) / Math.PI;
    steps.push({ rotate: { axis, origin: a0, angleDeg: deg } });
  }
  const t = sub(a1, a0);
  if (Math.abs(t[0]) + Math.abs(t[1]) + Math.abs(t[2]) > 1e-9) {
    steps.push({ translate: t });
  }
  return steps;
}

// ---------------------------------------------------------------------------
// FEATURES
// Top-level occurrence order is frozen by f1.step.py's assemble(); see the
// OCCURRENCE ORDER block in that file. Do not renumber without updating both.
// ---------------------------------------------------------------------------

const F = {
  front_wing: "#o1.1",
  nose: "#o1.2",
  monocoque: "#o1.3",
  halo: "#o1.4",
  cockpit: "#o1.5",
  sidepod_left: "#o1.6",
  sidepod_right: "#o1.7",
  engine_cover: "#o1.8",
  airbox: "#o1.9",
  floor: "#o1.10",
  diffuser: "#o1.11",
  cooling: "#o1.12",
  power_unit: "#o1.13",
  drivetrain: "#o1.14",
  rear_wing: "#o1.15",
  drs_flap: "#o1.16",
  drs_actuator: "#o1.17",
  beam_wing: "#o1.18",
  suspension_front: "#o1.19",
  suspension_rear: "#o1.20",
  corner_fl: "#o1.21",
  corner_fr: "#o1.22",
  track_rod_left: "#o1.23",
  track_rod_right: "#o1.24",
  corner_rl: "#o1.25",
  corner_rr: "#o1.26",
  steering_rack: "#o1.27",
  details: "#o1.28",
};

// ---------------------------------------------------------------------------
// EXPLODE STAGING
//
// Each group gets a direction, a distance and a TIME WINDOW. Windows overlap
// only slightly and run in a deliberate order — bodywork, then cooling and
// rear aero, then running gear, then power unit and drivetrain last. That
// sequencing is what keeps the teardown readable. `dir` is in car coordinates
// (+X forward, +Y left, +Z up) and is normalized before use.
// ---------------------------------------------------------------------------

// Entries are [ref, dir, dist, [winStart, winEnd]].
//
// PURE TRANSLATION. An earlier pass also spun each part a few degrees about
// its own centroid and turntabled the whole car; both are gone. The animation
// is now the teardown and nothing else, which is what makes the engine
// legible — a rotating subject and a rotating part fight the one thing the
// viewer is meant to be reading.
//
// Distances are sized so parts clear each other in PROJECTION, not just in
// space: at 500-900 mm they still overlapped in silhouette from a three-
// quarter view and the frame read as a pile.
//
// THE POWER UNIT DELIBERATELY BARELY MOVES. Everything else evacuates around
// it, which leaves the engine sitting alone at the centre of the frame as the
// hero — then it takes itself apart. Giving it a big vector like the rest
// would just make it one more object in a scatter.
const BODYWORK = [
  // ref              dir              dist  window
  // Both are pushed off the centreline: the column straight above the car is
  // reserved for the power unit, which rises into it as the hero.
  [F.engine_cover, [-0.22, -0.72, 0.72], 1150, [0.0, 0.30]],
  [F.airbox, [0.18, -0.78, 0.70], 1180, [0.03, 0.33]],
  [F.sidepod_left, [0, 1, 0.34], 1320, [0.05, 0.33]],
  [F.sidepod_right, [0, -1, 0.34], 1320, [0.05, 0.33]],
  [F.floor, [0, 0, -1], 980, [0.08, 0.33]],
  [F.diffuser, [-0.45, 0, -1], 1020, [0.10, 0.33]],
];

const INTERNALS = [
  [F.cooling, [0, 1, 0.55], 1860, [0.33, 0.52]],
  [F.rear_wing, [-0.34, 0, 1], 1160, [0.33, 0.52]],
  [F.drs_flap, [-0.34, 0, 1], 1420, [0.33, 0.52]],
  [F.drs_actuator, [-0.34, 0, 1], 1280, [0.33, 0.52]],
  [F.beam_wing, [-1, 0, 0.25], 980, [0.36, 0.55]],
  [F.front_wing, [1, 0, -0.08], 1420, [0.36, 0.55]],
  [F.nose, [1, 0, 0.22], 1680, [0.38, 0.58]],

  [F.corner_fl, [0, 1, 0.05], 1180, [0.50, 0.72]],
  [F.corner_fr, [0, -1, 0.05], 1180, [0.50, 0.72]],
  [F.corner_rl, [0, 1, 0.05], 1180, [0.50, 0.72]],
  [F.corner_rr, [0, -1, 0.05], 1180, [0.50, 0.72]],
  [F.track_rod_left, [0, 1, 0.18], 820, [0.53, 0.74]],
  [F.track_rod_right, [0, -1, 0.18], 820, [0.53, 0.74]],
  [F.suspension_front, [0.35, 0, 0.85], 880, [0.55, 0.76]],
  [F.suspension_rear, [-0.35, 0, 0.85], 880, [0.55, 0.76]],
  [F.steering_rack, [1, 0, 0.20], 980, [0.57, 0.78]],
  [F.details, [0, 1, 0.62], 1320, [0.62, 0.84]],

  [F.halo, [0.42, 0.55, 0.68], 940, [0.62, 0.82]],
  [F.cockpit, [0.12, 0.85, 0.62], 1180, [0.64, 0.86]],
  [F.drivetrain, [-1, 0, 0.32], 1560, [0.70, 0.92]],

  // THE HERO. It lifts straight up and OUT of the car, early, into the column
  // everything else was pushed clear of — so by the time the teardown settles
  // the engine is hanging in open air above the wreck with nothing in front of
  // it. Sitting it in the middle of the spread (the first attempt, a 150 mm
  // token lift late in the sequence) buried it: it was geometrically exploded
  // and visually invisible.
  [F.power_unit, [0, 0, 1], 1080, [0.08, 0.34]],
];

const EXPLODE_GROUPS = [...BODYWORK, ...INTERNALS];

// ---------------------------------------------------------------------------
// ENGINE SUB-EXPLODE
//
// Addressed BY NAME, not by occurrence id. Occurrence ids under a part module
// are positional and shift the moment that module's child count changes, so a
// sidecar pinned to `#o1.13.36` can silently start driving a different body —
// and a ref that matches the WRONG part is indistinguishable from a correct
// one. A declared name that matches nothing reports `missing` instead.
//
// The 100 leaves are collapsed into 12 SYSTEMS plus a static core. Exploding
// 100 individual bodies is the "cloud of debris" failure: what a viewer can
// actually read is induction lifting off the vee, the heads splitting outward,
// the split turbo separating fore and aft, the exhaust sweeping back. The
// crankcase, sump, bearing webs and joint rails never move — they are the
// spine everything else is measured against.
// ---------------------------------------------------------------------------

const sides = ["left", "right"];
const n3 = [1, 2, 3];
const seq = (base, n) => Array.from({ length: n }, (_, i) => `${base}:${i + 1}`);

const ENGINE_GROUPS = [
  ["eng_induction",
    ["plenum", "charge_pipe", "charge_pipe_clamp", "airbox_trunk",
      ...sides.flatMap((s) => n3.map((i) => `trumpet:${s}:${i}`))],
    [0, 0, 1], 760],

  ["eng_head_left",
    ["cylinder_head:left", "cam_cover:left", "fuel_rail:left", "head_joint_rail:left",
      ...n3.map((i) => `coil_pack:left:${i}`)],
    [0, 1, 0.5], 620],
  ["eng_head_right",
    ["cylinder_head:right", "cam_cover:right", "fuel_rail:right", "head_joint_rail:right",
      ...n3.map((i) => `coil_pack:right:${i}`)],
    [0, -1, 0.5], 620],

  // split turbo: compressor forward, turbine aft — the layout reads instantly
  ["eng_compressor", ["compressor_volute", "compressor_housing"], [1, 0, 0.2], 620],
  ["eng_turbine", ["turbine_volute", "turbine_housing", "turbine_inlet"], [-1, 0, 0.2], 620],
  ["eng_mguh", ["turbo_shaft", "mgu_h", "mgu_h_gland", "mgu_h_cable"], [0, 0, 1], 380],

  ["eng_exhaust_left",
    [...n3.map((i) => `exhaust_primary:left:${i}`), "collector:left", "heat_shield:collector"],
    [-0.45, 1, 0.45], 760],
  ["eng_exhaust_right",
    [...n3.map((i) => `exhaust_primary:right:${i}`), "collector:right"],
    [-0.45, -1, 0.45], 760],
  ["eng_tailpipe",
    ["collector_merge", "tailpipe", "tailpipe_tip", "heat_shield:tailpipe",
      "wastegate_body", "wastegate_flange", "wastegate_pipe", "wastegate_tip"],
    [-1, 0, 0.15], 900],

  ["eng_mguk",
    ["mgu_k", "mgu_k_ring", "mgu_k_drive_housing", ...seq("mgu_k_cable", 2)],
    [0.35, 1, -0.3], 700],

  ["eng_ers",
    ["ers_battery_case", "ers_battery_lid", "ers_terminal_block",
      ...seq("ers_bracket", 4), ...seq("ers_bus_bar", 6), ...seq("ers_coolant", 2)],
    [1, 0, -0.35], 860],

  ["eng_ancillaries",
    ["water_pump", "oil_pump", "oil_tank", "ecu_box", "ecu_connector",
      "water_feed", "water_return", "oil_feed", "oil_return",
      "fuel_line", "fuel_crossover",
      ...seq("ecu_pin", 3), ...seq("line_bracket", 4)],
    [0, -1, -0.28], 780],
];

// Members whose transform is authored explicitly below; everything else gets
// its explode offset and nothing more.
const DRIVEN = new Set([
  F.drs_flap,
  F.drs_actuator,
  F.corner_fl,
  F.corner_fr,
  F.steering_rack,
  F.track_rod_left,
  F.track_rod_right,
]);

const DRS_PIVOT_3 = [-3985.0, 0, 872.0];
const DRS_CRANK_PIVOT_3 = [-3894.0, 0, 800.0];

function unit(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

// ===========================================================================
// SHOWCASE — one loop-closed timeline
//
// `showcase` is a single 0..1 parameter that choreographs the other three, and
// it is built so that showcase(1) is IDENTICAL to showcase(0). That matters:
// the renderer's looping mode maps frame i to i/frameCount (not
// i/(frameCount-1)), so the last frame runs straight back into the first. A
// plain 0->1 explode sweep would therefore snap shut on the wrap. Every
// segment below is a there-and-back, so the loop is seamless by construction
// rather than by trimming frames.
//
// The beat sheet, and why it is in this order:
//
//   0.00-0.08  hold assembled. A showcase needs a moment of the whole object
//              before it starts taking itself apart, or the viewer never
//              registers what is being disassembled.
//   0.05-0.16  DRS opens and closes. The one mechanism you can show while the
//              car is still whole, so it goes first and gets a clear stage.
//   0.14-0.28  steering sweeps right, through centre, to left and back. Reads
//              as the car "looking around" before it comes apart.
//   0.26-0.62  the explode opens out to full.
//   0.62-0.72  hold fully exploded — the money frame, and it must be still
//              long enough to actually read.
//   0.72-0.96  everything comes back together.
//   0.96-1.00  settle assembled, closing the loop exactly.
// ===========================================================================

/** Smooth ramp 0->1 across [a,b], holding 1 after b. */
function ramp(a, b, t) {
  return smoothstep((t - a) / Math.max(b - a, 1e-6));
}

/**
 * Resolve the three real parameters from the showcase clock.
 * Returns {drs, steering, explode}; at t=0 and t=1 all three are exactly 0.
 */
export function showcaseAt(t) {
  const u = clamp01(t);

  // Beat sheet, in seconds against the 22.5 s loop:
  //
  //   0.0 - 1.5   hold assembled
  //   1.5 - 10.5  CAR opens (9.0 s — deliberately slow; this is the part
  //               worth watching, and at half this length the panels moved
  //               faster than the eye could follow one of them)
  //  10.5 - 11.2  short handover (0.7 s, was 2.2 s — long enough to register
  //               the engine as a subject, short enough not to stall)
  //  11.2 - 14.8  ENGINE opens
  //  14.8 - 16.3  hold at full spread
  //  16.3 - 18.8  engine closes
  //  18.8 - 22.3  car closes
  //  22.3 - 22.5  settle, closing the loop exactly
  //
  // The two piecewise switch points (0.70 / 0.69) each sit inside a plateau
  // where both branches evaluate to 1, so neither introduces a step.
  const explode = u < 0.7 ? ramp(0.067, 0.467, u) : 1 - ramp(0.836, 0.991, u);
  const engine = u < 0.69 ? ramp(0.498, 0.658, u) : 1 - ramp(0.724, 0.836, u);

  // DRS, steering and the turntable are all deliberately absent: this
  // animation is the exploded view and nothing else.
  return {
    drs: 0,
    steering: 0,
    explode: clamp01(explode),
    engine: clamp01(engine),
  };
}

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/f1/f1.step" },
    label: "F1 concept car",
    units: { length: "mm", angle: "deg", time: "s" },
    features: {
      ...Object.fromEntries(
        Object.entries(F).map(([k, ref]) => [
          k,
          { ref, label: k.replace(/_/g, " ") },
        ])
      ),
      // Engine subsystems are addressed BY NAME. See the ENGINE SUB-EXPLODE
      // block: positional ids under a part module shift whenever that module's
      // child count changes, and a ref that lands on the wrong body looks
      // exactly like one that landed on the right body. Names that match
      // nothing are reported as `missing` instead of silently doing nothing.
      ...Object.fromEntries(
        ENGINE_GROUPS.map(([key, names]) => [
          key,
          { names, label: key.replace(/^eng_/, "engine ").replace(/_/g, " ") },
        ])
      ),
    },

    // Declaring an animation is what gives the CAD Viewer its transport —
    // play/pause, restart, a loop toggle and a scrub bar all appear once this
    // exists. The animation does nothing but map playback progress onto the
    // `showcase` parameter; all the choreography lives in `showcaseAt`, so the
    // slider and the player are guaranteed to agree.
    //
    // `loop: true` is safe here precisely because showcase(1) === showcase(0)
    // exactly — see the SHOWCASE block. A timeline that did not close would
    // visibly snap on every repeat.
    animations: {
      showcase: {
        label: "Showcase",
        description:
          "The car comes apart, holds while the engine stands alone, then " +
          "the engine itself comes apart — and back. One seamless loop.",
        duration: 22.5,
        loop: true,
        update({ progress, set }) {
          set("showcase", progress);
        },
      },
    },
    parameters: {
      engine: {
        type: "number",
        label: "Engine explode",
        description:
          "Blows the power unit apart into its 12 subsystems — induction, " +
          "heads, split turbo, exhaust, MGU-K, ERS, ancillaries — about a " +
          "crankcase that stays put. Independent of the car-level explode.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.01,
        control: "slider",
      },
      drs: {
        type: "number",
        label: "DRS",
        description:
          "Rear wing flap, 0 shut to 1 fully open. The bellcrank and link are " +
          "solved as a four-bar, so the linkage stays closed through the travel.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.01,
        control: "slider",
      },
      steering: {
        type: "number",
        label: "Steering",
        description:
          "Lock to lock, positive steers left. Drives the rack; each front " +
          "wheel is then solved against its own track rod. Pushrods and " +
          "rockers correctly stay put — the ball joints define the steer axis.",
        default: 0,
        min: -1,
        max: 1,
        step: 0.01,
        control: "slider",
      },
      explode: {
        type: "number",
        label: "Explode",
        description:
          "Staged teardown. The first third lifts the bodywork panels away; " +
          "the rest walks the internals outward by system, in sequence, each " +
          "part turning slightly as it leaves so its best face is presented.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.01,
        control: "slider",
      },
      showcase: {
        type: "number",
        label: "Showcase",
        description:
          "One loop-closed timeline: the car comes apart, holds while the " +
          "engine stands alone, then the engine itself comes apart, then " +
          "both reassemble. Explode only — no turntable, DRS or steering. " +
          "showcase(1) equals showcase(0) exactly, so it loops seamlessly.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.005,
        control: "slider",
      },
    },
  },

  update({ params, effects }) {
    // The showcase clock, when engaged, owns all three real parameters.
    const show = clamp01(params.showcase);
    const driven = show > 0 ? showcaseAt(show) : null;

    const drs = driven ? driven.drs : clamp01(params.drs);
    const steer = driven
      ? driven.steering
      : clamp(Number(params.steering) || 0, -1, 1);
    const u = driven ? driven.explode : clamp01(params.explode);

    effects.visible("*", true);

    // ---- explode offsets --------------------------------------------------
    const offset = new Map();
    for (const [key, dir, dist, win] of EXPLODE_GROUPS) {
      const amt = window01(win[0], win[1], u);
      if (amt <= 0) continue;
      const d0 = unit(dir);
      offset.set(key, [d0[0] * dist * amt, d0[1] * dist * amt, d0[2] * dist * amt]);
    }

    // ---- engine sub-explode ------------------------------------------------
    // Runs on its OWN clock so the engine can come apart while the car around
    // it is already fully spread and stationary. Sub-parts inherit the power
    // unit's own (deliberately tiny) offset, or they would detach from it.
    const eng = driven ? driven.engine : clamp01(params.engine);
    const engBase = offset.get(F.power_unit) || [0, 0, 0];
    for (const [key, , dir, dist] of ENGINE_GROUPS) {
      if (eng <= 0) {
        effects.transform(key, { transforms: [{ translate: engBase }] });
        continue;
      }
      const d0 = unit(dir);
      effects.transform(key, {
        transforms: [{
          translate: [
            engBase[0] + d0[0] * dist * eng,
            engBase[1] + d0[1] * dist * eng,
            engBase[2] + d0[2] * dist * eng,
          ],
        }],
      });
    }

    // The explode translation is appended LAST so a part can be simultaneously
    // articulated (DRS, steering) and exploded without the articulation
    // dragging the offset around with it.
    const withShift = (key, steps) => {
      const t = offset.get(key);
      return t ? [...steps, { translate: t }] : steps;
    };

    // ---- DRS ---------------------------------------------------------------
    const d = solveDrs(drs);

    effects.transform(F.drs_flap, {
      transforms: withShift(F.drs_flap, [
        { rotate: { axis: [0, 1, 0], origin: DRS_PIVOT_3, angleDeg: d.flapDeg } },
      ]),
    });
    effects.transform(F.drs_actuator, {
      transforms: withShift(F.drs_actuator, [
        {
          rotate: {
            axis: [0, 1, 0],
            origin: DRS_CRANK_PIVOT_3,
            angleDeg: d.crankDeltaDeg,
          },
        },
      ]),
    });

    // ---- steering ----------------------------------------------------------
    const s = solveSteering(steer);

    effects.transform(F.corner_fl, {
      transforms: withShift(F.corner_fl, [
        {
          rotate: {
            axis: s.leftAxis.dir,
            origin: s.leftAxis.origin,
            angleDeg: s.leftDeg,
          },
        },
      ]),
    });
    effects.transform(F.corner_fr, {
      transforms: withShift(F.corner_fr, [
        {
          rotate: {
            axis: s.rightAxis.dir,
            origin: s.rightAxis.origin,
            angleDeg: s.rightDeg,
          },
        },
      ]),
    });
    effects.transform(F.steering_rack, {
      transforms: withShift(F.steering_rack, [{ translate: [0, s.rackDy, 0] }]),
    });
    effects.transform(F.track_rod_left, {
      transforms: withShift(
        F.track_rod_left,
        reaimSteps(s.leftRod.from0, s.leftRod.to0, s.leftRod.from1, s.leftRod.to1)
      ),
    });
    effects.transform(F.track_rod_right, {
      transforms: withShift(
        F.track_rod_right,
        reaimSteps(
          s.rightRod.from0,
          s.rightRod.to0,
          s.rightRod.from1,
          s.rightRod.to1
        )
      ),
    });

    // ---- everything else: explode (spin + offset) only ----------------------
    for (const ref of Object.values(F)) {
      if (DRIVEN.has(ref)) continue;
      effects.transform(ref, { transforms: withShift(ref, []) });
    }
  },
};

// f1.step.js — choreography for the F1 concept car.
//
// Everything this car does is here rather than in a `kinematics=` block, and
// that is a decision, not an omission: both of its mechanisms are CLOSED
// LOOPS. The DRS is a planar four-bar and the steering solves each wheel
// against a fixed-length track rod; typed mates evaluate pure forward
// kinematics on a TREE, so a loop needs a solver and the solver lives here,
// where arbitrary JS is allowed. The teardown belongs here regardless.
//
// The solves are exported by name as well as used by the clips, so they can be
// checked under node without a viewer.
//
// WHAT STEERING MOVES, AND WHY IT IS NOT EVERYTHING. The upright, wheel,
// brake, track rod and rack move. The pushrods and rockers deliberately DO
// NOT: both front ball joints sit exactly on the steer axis (spec.F_LOWER_BALL
// and spec.F_UPPER_BALL define it), which is precisely why steering does not
// disturb the wishbones or anything inboard of them. That is the real
// geometry — animating the rockers would look busier and be wrong.

// ---------------------------------------------------------------- hardpoints
// Mirrors of the constants in src/lib/spec.py. Keep in sync by hand — these are
// a render-time copy, spec.py remains the source of truth.
export const HP = {
  // DRS four-bar (all in the y = DRS_LINK_Y plane)
  DRS_PIVOT: [-3985.0, 872.0], // (x, z)
  DRS_CRANK_PIVOT: [-3894.0, 800.0], // (x, z)
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
  return add(origin, add(add(scale(v, c), scale(cross(k, v), s)), scale(k, dot(k, v) * (1 - c))));
}

// ------------------------------------------------------------------- DRS
const dist2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const polar = (c, r, deg) => [
  c[0] + r * Math.cos((deg * Math.PI) / 180),
  c[1] + r * Math.sin((deg * Math.PI) / 180),
];

const LUG_CLOSED = polar(HP.DRS_PIVOT, HP.DRS_LUG_R, HP.DRS_LUG_ANGLE_CLOSED_DEG);
const CRANK_END_CLOSED = polar(HP.DRS_CRANK_PIVOT, HP.DRS_CRANK_R, HP.DRS_CRANK_ANGLE_CLOSED_DEG);
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
 * The circle-circle solve has two roots; we lock to the branch that reproduces
 * the closed pose so the linkage never snaps through.
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

  const angOf = (p) => (Math.atan2(p[1] - C[1], p[0] - C[0]) * 180) / Math.PI;
  return { flapDeg, crankDeltaDeg: angOf(end) - HP.DRS_CRANK_ANGLE_CLOSED_DEG };
}

// --------------------------------------------------------------- STEERING
const mirrorY = (p) => [p[0], -p[1], p[2]];

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
 * on a bracket around zero — Newton is unnecessary and bisection cannot jump
 * branches, which matters because the far root folds the upright over.
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
  const fhi = err(hi);
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
    } else {
      lo = mid;
      flo = fm;
    }
  }
  return 0.5 * (lo + hi);
}

/**
 * Full steering state for a normalized input in [-1, 1].
 * Positive steers LEFT (the car's +Y side is the inside of the turn). The rack
 * is one bar, so both wheels take the same d and each wheel's angle is solved
 * against its OWN track rod — the two sides differ slightly, which is where the
 * anti-Ackermann comes from.
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
        right,
      ),
    },
  };
}

/**
 * Carry a two-ended member from (a0,b0) to (a1,b1) on a handle: rotate about
 * the member's own first end, then translate that end onto its new position.
 * Exact whenever the two lengths match, which the four-bar and the rack solve
 * both guarantee.
 */
export function reaim(handle, a0, b0, a1, b1) {
  const n0 = norm(sub(b0, a0));
  const n1 = norm(sub(b1, a1));
  const axis = cross(n0, n1);
  const s = len(axis);
  if (s > 1e-9) {
    handle.rotate(axis, (Math.atan2(s, clamp(dot(n0, n1), -1, 1)) * 180) / Math.PI, a0);
  }
  const t = sub(a1, a0);
  if (Math.abs(t[0]) + Math.abs(t[1]) + Math.abs(t[2]) > 1e-9) handle.translate(t);
  return handle;
}

// ---------------------------------------------------------------------------
// OCCURRENCES
// Top-level occurrence order is frozen by src/f1.py's assemble(); see the
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
// only slightly and run in a deliberate order — bodywork, then cooling and rear
// aero, then running gear, then power unit and drivetrain last. That sequencing
// is what keeps the teardown readable. `dir` is in car coordinates (+X forward,
// +Y left, +Z up) and is normalized before use.
//
// PURE TRANSLATION. An earlier pass also spun each part a few degrees about its
// own centroid and turntabled the whole car; both are gone. A rotating subject
// and a rotating part fight the one thing the viewer is meant to be reading.
//
// Distances are sized so parts clear each other in PROJECTION, not just in
// space: at 500-900 mm they still overlapped in silhouette from a three-quarter
// view and the frame read as a pile.
//
// THE POWER UNIT DELIBERATELY BARELY MOVES sideways. Everything else evacuates
// around it, which leaves the engine sitting alone at the centre of the frame
// as the hero — then it takes itself apart.
//
// Entries are [ref, dir, dist, [winStart, winEnd]].
const BODYWORK = [
  // Both are pushed off the centreline: the column straight above the car is
  // reserved for the power unit, which rises into it as the hero.
  [F.engine_cover, [-0.22, -0.72, 0.72], 1150, [0.0, 0.3]],
  [F.airbox, [0.18, -0.78, 0.7], 1180, [0.03, 0.33]],
  [F.sidepod_left, [0, 1, 0.34], 1320, [0.05, 0.33]],
  [F.sidepod_right, [0, -1, 0.34], 1320, [0.05, 0.33]],
  [F.floor, [0, 0, -1], 980, [0.08, 0.33]],
  [F.diffuser, [-0.45, 0, -1], 1020, [0.1, 0.33]],
];

const INTERNALS = [
  [F.cooling, [0, 1, 0.55], 1860, [0.33, 0.52]],
  [F.rear_wing, [-0.34, 0, 1], 1160, [0.33, 0.52]],
  [F.drs_flap, [-0.34, 0, 1], 1420, [0.33, 0.52]],
  [F.drs_actuator, [-0.34, 0, 1], 1280, [0.33, 0.52]],
  [F.beam_wing, [-1, 0, 0.25], 980, [0.36, 0.55]],
  [F.front_wing, [1, 0, -0.08], 1420, [0.36, 0.55]],
  [F.nose, [1, 0, 0.22], 1680, [0.38, 0.58]],

  [F.corner_fl, [0, 1, 0.05], 1180, [0.5, 0.72]],
  [F.corner_fr, [0, -1, 0.05], 1180, [0.5, 0.72]],
  [F.corner_rl, [0, 1, 0.05], 1180, [0.5, 0.72]],
  [F.corner_rr, [0, -1, 0.05], 1180, [0.5, 0.72]],
  [F.track_rod_left, [0, 1, 0.18], 820, [0.53, 0.74]],
  [F.track_rod_right, [0, -1, 0.18], 820, [0.53, 0.74]],
  [F.suspension_front, [0.35, 0, 0.85], 880, [0.55, 0.76]],
  [F.suspension_rear, [-0.35, 0, 0.85], 880, [0.55, 0.76]],
  [F.steering_rack, [1, 0, 0.2], 980, [0.57, 0.78]],
  [F.details, [0, 1, 0.62], 1320, [0.62, 0.84]],

  [F.halo, [0.42, 0.55, 0.68], 940, [0.62, 0.82]],
  [F.cockpit, [0.12, 0.85, 0.62], 1180, [0.64, 0.86]],
  [F.drivetrain, [-1, 0, 0.32], 1560, [0.7, 0.92]],

  // THE HERO. It lifts straight up and OUT of the car, early, into the column
  // everything else was pushed clear of — so by the time the teardown settles
  // the engine is hanging in open air above the wreck with nothing in front of
  // it. Sitting it in the middle of the spread (the first attempt, a 150 mm
  // token lift late in the sequence) buried it: geometrically exploded and
  // visually invisible.
  [F.power_unit, [0, 0, 1], 1080, [0.08, 0.34]],
];

const EXPLODE_GROUPS = [...BODYWORK, ...INTERNALS];

// ---------------------------------------------------------------------------
// ENGINE SUB-EXPLODE
//
// Addressed BY LABEL, not by occurrence id. Occurrence ids under a part module
// are positional and shift the moment that module's child count changes, so a
// ref pinned to `#o1.13.36` can silently start driving a different body — and a
// ref that matches the WRONG part is indistinguishable from a correct one. A
// label that matches nothing THROWS instead.
//
// The 100 leaves are collapsed into 12 SYSTEMS plus a static core. Exploding
// 100 individual bodies is the "cloud of debris" failure: what a viewer can
// actually read is induction lifting off the vee, the heads splitting outward,
// the split turbo separating fore and aft, the exhaust sweeping back. The
// crankcase, sump, bearing webs and joint rails never move — they are the spine
// everything else is measured against.
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
const Y_AXIS = [0, 1, 0];

function unit(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

/**
 * One frame.
 *
 * The explode translation is applied LAST on every handle, so a part can be
 * simultaneously articulated (DRS, steering) and exploded without the
 * articulation dragging the offset around with it — successive handle calls
 * PREMULTIPLY, which is exactly that ordering.
 */
function frame(m, { drs = 0, steer = 0, explode = 0, engine = 0 } = {}) {
  const offset = new Map();
  for (const [key, dir, dist, win] of EXPLODE_GROUPS) {
    const amt = window01(win[0], win[1], explode);
    if (amt <= 0) continue;
    const d0 = unit(dir);
    offset.set(key, [d0[0] * dist * amt, d0[1] * dist * amt, d0[2] * dist * amt]);
  }
  const shift = (handle, key) => {
    const t = offset.get(key);
    if (t) handle.translate(t);
    return handle;
  };

  // Engine sub-explode runs on its OWN clock, so the engine can come apart
  // while the car around it is already fully spread and stationary. Sub-parts
  // inherit the power unit's own offset, or they would detach from it.
  const engBase = offset.get(F.power_unit) || [0, 0, 0];
  for (const [, names, dir, dist] of ENGINE_GROUPS) {
    const d0 = unit(dir);
    const t = [
      engBase[0] + d0[0] * dist * engine,
      engBase[1] + d0[1] * dist * engine,
      engBase[2] + d0[2] * dist * engine,
    ];
    for (const name of names) m.get(name).translate(t);
  }

  // ---- DRS ---------------------------------------------------------------
  const d = solveDrs(drs);
  shift(m.get(F.drs_flap).rotate(Y_AXIS, d.flapDeg, DRS_PIVOT_3), F.drs_flap);
  shift(
    m.get(F.drs_actuator).rotate(Y_AXIS, d.crankDeltaDeg, DRS_CRANK_PIVOT_3),
    F.drs_actuator,
  );

  // ---- steering ----------------------------------------------------------
  const s = solveSteering(steer);
  shift(m.get(F.corner_fl).rotate(s.leftAxis.dir, s.leftDeg, s.leftAxis.origin), F.corner_fl);
  shift(m.get(F.corner_fr).rotate(s.rightAxis.dir, s.rightDeg, s.rightAxis.origin), F.corner_fr);
  shift(m.get(F.steering_rack).translate([0, s.rackDy, 0]), F.steering_rack);
  shift(
    reaim(m.get(F.track_rod_left), s.leftRod.from0, s.leftRod.to0, s.leftRod.from1, s.leftRod.to1),
    F.track_rod_left,
  );
  shift(
    reaim(m.get(F.track_rod_right), s.rightRod.from0, s.rightRod.to0, s.rightRod.from1, s.rightRod.to1),
    F.track_rod_right,
  );

  // ---- everything else: explode offset only -------------------------------
  for (const ref of Object.values(F)) {
    if (DRIVEN.has(ref)) continue;
    shift(m.get(ref), ref);
  }
}

// ===========================================================================
// SHOWCASE — one loop-closed timeline
//
// Built so showcase(1) is IDENTICAL to showcase(0): the renderer's looping maps
// frame i to i/frameCount (not i/(frameCount-1)), so the last frame runs
// straight back into the first. A plain 0->1 explode sweep would snap shut on
// the wrap. Every segment is a there-and-back, so the loop is seamless by
// construction rather than by trimming frames.
//
// The beat sheet, in seconds against the 22.5 s loop:
//    0.0 -  1.5  hold assembled — a showcase needs a moment of the whole object
//                before it starts taking itself apart, or the viewer never
//                registers what is being disassembled
//    1.5 - 10.5  CAR opens (9.0 s — deliberately slow; at half this length the
//                panels moved faster than the eye could follow one of them)
//   10.5 - 11.2  short handover (long enough to register the engine as a
//                subject, short enough not to stall)
//   11.2 - 14.8  ENGINE opens
//   14.8 - 16.3  hold at full spread — the money frame
//   16.3 - 18.8  engine closes
//   18.8 - 22.3  car closes
//   22.3 - 22.5  settle, closing the loop exactly
//
// The two piecewise switch points (0.70 / 0.69) each sit inside a plateau where
// both branches evaluate to 1, so neither introduces a step.
// ===========================================================================

/** Smooth ramp 0->1 across [a,b], holding 1 after b. */
const ramp = (a, b, t) => smoothstep((t - a) / Math.max(b - a, 1e-6));

/** Resolve the showcase clock; at u=0 and u=1 both values are exactly 0. */
export function showcaseAt(t) {
  const u = clamp01(t);
  const explode = u < 0.7 ? ramp(0.067, 0.467, u) : 1 - ramp(0.836, 0.991, u);
  const engine = u < 0.69 ? ramp(0.498, 0.658, u) : 1 - ramp(0.724, 0.836, u);
  // DRS and steering are deliberately absent: this clip is the exploded view
  // and nothing else.
  return { explode: clamp01(explode), engine: clamp01(engine) };
}

const wrap01 = (v) => ((Number(v) || 0) % 1 + 1) % 1;
/** Symmetric there-and-back on a raised cosine, so a loop closes exactly. */
const pingpong = (u) => 0.5 * (1 - Math.cos(2 * Math.PI * wrap01(u)));

export const clips = {
  showcase: {
    label: "Showcase",
    duration: 22.5,
    loop: true,
    update(t, m) {
      frame(m, showcaseAt(wrap01(t / 22.5)));
    },
  },
  drs: {
    label: "DRS",
    duration: 4,
    loop: true,
    update(t, m) {
      // The one mechanism you can show while the car is still whole.
      frame(m, { drs: pingpong(t / 4) });
    },
  },
  steering: {
    label: "Steering",
    duration: 6,
    loop: true,
    update(t, m) {
      // Right, through centre, to left and back — the car "looking around".
      frame(m, { steer: Math.sin(2 * Math.PI * wrap01(t / 6)) });
    },
  },
  teardown: {
    label: "Teardown",
    duration: 12,
    loop: true,
    update(t, m) {
      frame(m, { explode: pingpong(t / 12) });
    },
  },
  engine: {
    label: "Engine explode",
    duration: 8,
    loop: true,
    update(t, m) {
      frame(m, { engine: pingpong(t / 8) });
    },
  },
};

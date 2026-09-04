// moonwatch.step.js — choreography for the moonwatch chronograph assembly.
// Declared by `@step(animation="moonwatch.step.js")`; the TEXT of this file is
// copied into STEP/moonwatch.step.json at build.
//
// This is the half of the retired `moonwatch.params.js` sidecar that is NOT
// kinematics: staged explodes, the sinusoidal balance swing and the escape
// wheel's per-beat snap (neither is a linear gearing, so neither is a mate),
// and the movement's lift-and-flip out of the case. The watch's real degrees
// of freedom — hands, going train, escapement, chronograph, crown, pushers —
// and the gear ratios between them live in `KINEMATICS` in moonwatch.py.
// Animation is deliberately ignorant of mates, so these clips restate the
// motion in a few lines of ratio math.
//
// Clips:
//   running    — one seamless escapement loop, slow-motion macro pacing:
//                4 balance oscillations, 8 beats. The escape wheel advances
//                one half-tooth-pitch step per beat (8 x 12 deg = 96 deg =
//                exactly 4 tooth pitches of the 15-tooth wheel, so the loop
//                is seamless), the pallet fork snaps between banking
//                positions at each beat, the fourth/third wheels creep
//                spoke-symmetric increments, and the chronograph runs.
//   reveal     — staged partial explode: the caseback stack fans downward,
//                the movement ring drops clear, the box crystal and gasket
//                lift off the dial, the bracelet straps slide apart, and the
//                movement rises into the case mouth and flips bridge-side-up.
//   showcase   — full explode timeline: the dial, bezel stack and crystal fan
//                out to the sides, the caseback stack and bracelet spread
//                away, then the movement rises straight up the middle, flips,
//                and its own subassembly fans open in tiers. The second half
//                mirrors the first, so the watch reassembles and the loop
//                closes.
//   grand_tour — reveal opens and dwells with the escapement running, then
//                the movement's tiers fan open while the floating face stack
//                lifts for headroom; everything mirrors closed again.
//
// Watch frame: +Z = dial. Movement parts sit at watch (x, -y) of their local
// layout positions in lib/spec.py (the movement is cased dial-down via a
// 180 deg flip about X). All run rotations are about watch +Z through each
// wheel center; every target is emitted as ONE chain, rotations BEFORE the
// summed translation, and successive handle calls PREMULTIPLY — so the
// composition order matches the retired sidecar's
// `effects.transform(ref, {transforms: [...]})` exactly.

const Z_AXIS = [0, 0, 1];

// Movement layout positions (lib/spec.py, local) mapped to watch frame (x, -y).
const BALANCE = [-0.4, 7.6, 0];
const PALLET = [-4.9, 7.2, 0];
const ESCAPE = [-7.6, 5.2, 0];
const FOURTH = [-10.2, 0, 0];
const THIRD = [-5.0, 2.6, 0];
const CENTER = [0, 0, 0];
const COUPLING = [5.6, 4.6, 0];

// Escapement pacing (per run loop).
const OSCILLATIONS = 4; // balance swings per loop
const BEATS = OSCILLATIONS * 2; // escape steps per loop
const BALANCE_AMPLITUDE_DEG = 75;
const ESCAPE_STEP_DEG = 12; // half a tooth pitch (360/15/2)
const PALLET_BANK_DEG = 8;
const STEP_FRACTION = 0.25; // fraction of a beat spent mid-snap

function smooth(t) {
  const x = Math.min(1, Math.max(0, t));
  return x * x * (3 - 2 * x);
}

// Staged smoothstep: 0 before a, 1 after b.
function stage(t, a, b) {
  return smooth((t - a) / (b - a));
}

// Quick snap easing inside one beat: completes in STEP_FRACTION of the beat.
function snap(fraction) {
  return smooth(fraction / STEP_FRACTION);
}

// --- targets ----------------------------------------------------------------
// Labels are canonical for RENDERED PARTS; a GROUP has to be named by its
// occurrence id (labels here match rendered parts only). Verified against
// STEP/moonwatch.step's assembly.json.
const MOVEMENT_BASE = "#o1.4.1";

const REF = {
  // case parts that move during reveal / showcase
  bezel_ring: "bezel_ring",
  bezel_insert: "bezel_insert",
  tachymeter_scale: "tachymeter_scale",
  crystal: "crystal",
  crystal_gasket: "crystal_gasket",
  caseback: "caseback",
  caseback_sapphire: "caseback_sapphire",
  caseback_retaining_ring: "caseback_retaining_ring",
  caseback_o_ring: "caseback_o_ring",
  crown: "crown",
  crown_tube: "crown_tube",
  crown_o_ring: "crown_o_ring",
  pusher_cap_2: "pusher_cap:2oclock",
  pusher_tube_2: "pusher_tube:2oclock",
  pusher_spring_2: "pusher_spring:2oclock",
  pusher_o_ring_2: "pusher_o_ring:2oclock",
  pusher_cap_4: "pusher_cap:4oclock",
  pusher_tube_4: "pusher_tube:4oclock",
  pusher_spring_4: "pusher_spring:4oclock",
  pusher_o_ring_4: "pusher_o_ring:4oclock",
  spring_bar_12: "spring_bar:12",
  spring_bar_6: "spring_bar:6",
  bezel_polish: "case_polish:bezel",
  movement_ring: "movement_ring",
  // groups: occurrence ids
  dial_group: "#o1.2",
  movement_group: "#o1.4",
  keyless_group: "#o1.4.2",
  chrono_group: "#o1.4.3",
  strap_12: "#o1.3.1",
  strap_6: "#o1.3.2",
  clasp: "#o1.3.3",
  // going train + escapement
  center_wheel: "center_wheel",
  center_pinion: "center_pinion",
  third_wheel: "third_wheel",
  third_pinion: "third_pinion",
  fourth_wheel: "fourth_wheel",
  fourth_pinion: "fourth_pinion",
  escape_pinion: "escape_pinion",
  escape_wheel: "escape_wheel",
  pallet_fork: "pallet_fork",
  pallet_stone_entry: "pallet_stone:entry",
  pallet_stone_exit: "pallet_stone:exit",
  pallet_arbor: "pallet_arbor",
  balance_wheel: "balance_wheel",
  balance_staff: "balance_staff",
  impulse_jewel: "impulse_jewel",
  // chronograph runner (the chrono is shown running)
  chrono_runner_wheel: "chrono_runner_wheel",
  chrono_runner_heart_cam: "chrono_runner_heart_cam",
  chrono_runner_arbor: "chrono_runner_arbor",
  coupling_wheel: "coupling_wheel",
  // hands that ride animated arbors
  chrono_seconds_hand: "hand:chrono_seconds",
  chrono_hand_cap: "hand:chrono_cap",
  sub_seconds_hand: "hand:sub_seconds",
};

// timing_screw:0..15 are movement-base children 76..91.
for (let i = 0; i < 16; i += 1) REF[`timing_screw_${i}`] = `timing_screw:${i}`;

// Movement-base parts the showcase tiers fan but nothing else names: address
// them by occurrence id, exactly the child indices the retired sidecar used.
function baseFeature(index) {
  const id = `movt_base_${index}`;
  if (!REF[id]) REF[id] = `${MOVEMENT_BASE}.${index}`;
  return id;
}

function baseRange(from, to) {
  const ids = [];
  for (let i = from; i <= to; i += 1) ids.push(baseFeature(i));
  return ids;
}

const BALANCE_GROUP = [
  "balance_wheel",
  "balance_staff",
  "impulse_jewel",
  ...Array.from({ length: 16 }, (_, i) => `timing_screw_${i}`),
];

const PALLET_GROUP = [
  "pallet_fork",
  "pallet_stone_entry",
  "pallet_stone_exit",
  "pallet_arbor",
];

// Staged reveal translations: [feature, direction, distance, start, end].
// The bezel stack and crystal lift clear first, then the dial floats up so
// the face (hands running) and the movement (flipped bridge-side-up in the
// case mouth, escapement beating) are BOTH visible, vertically separated.
const REVEAL_MOVES = [
  ["caseback_o_ring", [0, 0, -1], 9.0, 0.0, 0.35],
  ["caseback_retaining_ring", [0, 0, -1], 13.0, 0.03, 0.38],
  ["caseback", [0, 0, -1], 18.0, 0.06, 0.42],
  ["caseback_sapphire", [0, 0, -1], 24.0, 0.09, 0.45],
  ["movement_ring", [0, 0, -1], 5.5, 0.0, 0.3],
  ["bezel_ring", [0, 0, 1], 34.0, 0.05, 0.45],
  ["bezel_polish", [0, 0, 1], 34.0, 0.05, 0.45],
  ["bezel_insert", [0, 0, 1], 37.0, 0.05, 0.45],
  ["tachymeter_scale", [0, 0, 1], 40.0, 0.05, 0.45],
  ["crystal", [0, 0, 1], 48.0, 0.05, 0.45],
  ["crystal_gasket", [0, 0, 1], 43.0, 0.05, 0.45],
  ["dial_group", [0, 0, 1], 26.0, 0.25, 0.6],
  ["strap_12", [0, 1, 0], 9.0, 0.1, 0.5],
  ["strap_6", [0, -1, 0], 9.0, 0.1, 0.5],
  ["clasp", [0, -1, 0], 9.0, 0.1, 0.5],
];

// Reveal movement lift-and-flip: once the caseback stack is away and the
// dial is rising, the movement climbs into the case mouth and turns
// bridge-side-up so the beating escapement faces the same camera as the
// floating dial.
const REVEAL_RISE = 16;
function revealStages(r) {
  return {
    rise: stage(r, 0.45, 0.85),
    flip: stage(r, 0.55, 0.92),
  };
}

// Grand tour timeline: reveal opens and dwells with the escapement running,
// then the movement's tiers fan open showcase-style while the floating face
// stack rises further to make room; everything mirrors closed again so the
// loop is seamless.
//   r — reveal openness (trapezoid: open by 0.20, close from 0.83)
//   f — gear-tier fan (open 0.45..0.55, closed again by 0.83)
const TOUR_HEADROOM = 32; // extra face-stack lift while the tiers are open
function tourStages(t) {
  return {
    r: Math.min(stage(t, 0.0, 0.2), stage(1 - t, 0.0, 0.17)),
    f: Math.min(stage(t, 0.45, 0.55), stage(1 - t, 0.17, 0.25)),
  };
}

// Face-stack features lifted for tier headroom during the tour fan.
const TOUR_HEADROOM_FEATURES = [
  "dial_group",
  "crystal",
  "crystal_gasket",
  "bezel_ring",
  "bezel_polish",
  "bezel_insert",
  "tachymeter_scale",
];

// --- showcase choreography ---------------------------------------------------
// The dial, bezel stack and crystal clear out to the SIDES so the movement can
// rise straight up the middle; the caseback stack and bracelet spread away.
// Lateral offsets keep every disc's center at least (disc radius + movement
// radius) from the rise corridor. Pushers sit at 2 and 4 o'clock.
const P2 = [0.866, 0.5, 0];
const P4 = [0.866, -0.5, 0];

// [feature, absolute offset at t = 1] applied with the lateral sub-stage.
const SHOWCASE_LATERALS = [
  ["dial_group", [-40, 0, 12]],
  ["bezel_ring", [-48, 0, 14]],
  ["bezel_polish", [-48, 0, 14]],
  ["bezel_insert", [-52, 0, 16]],
  ["tachymeter_scale", [-56, 0, 18]],
  ["crystal", [40, 0, 12]],
  ["crystal_gasket", [35, 0, 9]],
  ["crown", [13, 0, 0]],
  ["crown_tube", [9, 0, 0]],
  ["crown_o_ring", [6, 0, 0]],
  ["pusher_cap_2", [P2[0] * 11, P2[1] * 11, 0]],
  ["pusher_tube_2", [P2[0] * 8, P2[1] * 8, 0]],
  ["pusher_spring_2", [P2[0] * 5.5, P2[1] * 5.5, 0]],
  ["pusher_o_ring_2", [P2[0] * 3.5, P2[1] * 3.5, 0]],
  ["pusher_cap_4", [P4[0] * 11, P4[1] * 11, 0]],
  ["pusher_tube_4", [P4[0] * 8, P4[1] * 8, 0]],
  ["pusher_spring_4", [P4[0] * 5.5, P4[1] * 5.5, 0]],
  ["pusher_o_ring_4", [P4[0] * 3.5, P4[1] * 3.5, 0]],
];

// [feature, offset at t = 1] applied with the caseback/bracelet sub-stage.
const SHOWCASE_SPREADS = [
  ["movement_ring", [0, 0, -7]],
  ["caseback_o_ring", [0, 0, -12]],
  ["caseback_retaining_ring", [0, 0, -17]],
  ["caseback", [0, 0, -23]],
  ["caseback_sapphire", [0, 0, -30]],
  ["spring_bar_12", [0, 4, 0]],
  ["spring_bar_6", [0, -4, 0]],
  ["strap_12", [0, 14, 0]],
  ["strap_6", [0, -14, 0]],
  ["clasp", [0, -21, 0]],
];

// Movement subassembly tiers (pre-flip z offsets; negative = bridge side, so
// after the 180 deg flip these tiers stack UPWARD with the chronograph works
// on top). Applied with the fan sub-stage, in the movement's pre-parent frame
// so the group flip + rise carries them.
const MOVEMENT_TIERS = [
  { ids: ["keyless_group"], dz: 7 },
  { ids: [...baseRange(14, 20), baseFeature(63), ...baseRange(64, 67)], dz: -5 },
  { ids: baseRange(10, 13), dz: -8 }, // barrel
  { ids: baseRange(68, 74), dz: -11.5 }, // pallet bridge
  { ids: [...baseRange(34, 47), ...baseRange(51, 53)], dz: -15.5 }, // train bridge
  { ids: [...baseRange(21, 33), ...baseRange(48, 50)], dz: -15.5 }, // barrel bridge
  { ids: baseRange(54, 62), dz: -19 }, // ratchet, crown wheel, click
  { ids: baseRange(75, 105), dz: -24 }, // balance + cock + shock
  { ids: ["chrono_group"], dz: -30 },
];

const MOVEMENT_RISE = 30;
const MOVEMENT_CENTER = [0, 0, 1.7];

// Showcase timeline sub-stages, keyed on u = min(s, 1-s) so the reassembly
// half mirrors the expansion half exactly and the loop is seamless.
function showcaseStages(s) {
  return {
    lateral: stage(Math.min(s, 1 - s), 0.02, 0.17),
    spread: stage(Math.min(s, 1 - s), 0.05, 0.25),
    rise: stage(Math.min(s, 1 - s), 0.17, 0.34),
    flip: stage(Math.min(s, 1 - s), 0.3, 0.38),
    fan: stage(Math.min(s, 1 - s), 0.36, 0.42),
  };
}

// --- the one choreography routine -------------------------------------------
// `run`, `reveal`, `showcase` and `tour` are the four normalized timelines the
// retired sidecar exposed as viewer sliders; each clip below drives them.
function choreograph({ run = 0, reveal = 0, showcase = 0, tour = 0 }, m) {
  const s = Math.min(1, Math.max(0, showcase));
  const tr = tourStages(Math.min(1, Math.max(0, tour)));
  // The tour timeline reuses the reveal choreography for its open/close.
  const rv = Math.max(reveal, tr.r);
  // Three escapement loops per tour cycle: (run + 2*tour) sweeps 0..3 when the
  // grand tour clip drives both with the same progress, and reduces to plain
  // `run` whenever tour is 0.
  const effRun = (run + 2 * tour) % 1;
  const st = showcaseStages(s);

  // Per-feature accumulator: rotations happen first (about original pivots),
  // then one summed translation. Each feature gets exactly one m.get() chain.
  const rotations = new Map();
  const offsets = new Map();
  const addRot = (feature, pivot, deg) => {
    const list = rotations.get(feature) || [];
    list.push([pivot, deg]);
    rotations.set(feature, list);
  };
  const addMove = (feature, vec, scale) => {
    if (!scale) return;
    const cur = offsets.get(feature) || [0, 0, 0];
    offsets.set(feature, [
      cur[0] + vec[0] * scale,
      cur[1] + vec[1] * scale,
      cur[2] + vec[2] * scale,
    ]);
  };

  // --- reveal ---------------------------------------------------------------
  for (const [feature, dir, dist, a, b] of REVEAL_MOVES) {
    addMove(feature, dir, dist * stage(rv, a, b));
  }

  // --- showcase -------------------------------------------------------------
  if (s > 0) {
    for (const [feature, vec] of SHOWCASE_LATERALS) addMove(feature, vec, st.lateral);
    for (const [feature, vec] of SHOWCASE_SPREADS) addMove(feature, vec, st.spread);
    for (const tier of MOVEMENT_TIERS) {
      for (const feature of tier.ids) addMove(feature, [0, 0, tier.dz], st.fan);
    }
  }

  // --- grand tour: fan the movement tiers in the reveal pose -----------------
  if (tr.f > 0) {
    for (const tier of MOVEMENT_TIERS) {
      for (const feature of tier.ids) addMove(feature, [0, 0, tier.dz], tr.f);
    }
    for (const feature of TOUR_HEADROOM_FEATURES) {
      addMove(feature, [0, 0, 1], TOUR_HEADROOM * tr.f);
    }
  }

  // --- escapement -----------------------------------------------------------
  const beats = effRun * BEATS;
  const beatIndex = Math.min(Math.floor(beats), BEATS - 1);
  const beatFraction = beats - beatIndex;

  // Balance: sinusoidal oscillation; beats land on its zero crossings.
  const balanceDeg =
    BALANCE_AMPLITUDE_DEG * Math.sin(2 * Math.PI * OSCILLATIONS * effRun);
  for (const feature of BALANCE_GROUP) addRot(feature, BALANCE, balanceDeg);

  // Pallet fork: snaps between banking positions once per beat.
  const fromBank = beatIndex % 2 === 0 ? PALLET_BANK_DEG : -PALLET_BANK_DEG;
  const palletDeg = fromBank * (1 - 2 * snap(beatFraction));
  for (const feature of PALLET_GROUP) addRot(feature, PALLET, palletDeg);

  // Escape wheel: one crisp half-tooth step per beat, released as the pallet
  // snaps. 8 steps x 12 deg = 4 whole tooth pitches per loop.
  const escapeDeg = ESCAPE_STEP_DEG * (beatIndex + snap(beatFraction));
  for (const feature of ["escape_wheel", "escape_pinion"]) {
    addRot(feature, ESCAPE, escapeDeg);
  }

  // Going train creeps against the escape wheel: alternating directions,
  // spoke-and-tooth-symmetric 144 deg per loop so the seam is invisible.
  const trainDeg = 144 * effRun;
  for (const feature of ["fourth_wheel", "fourth_pinion"]) {
    addRot(feature, FOURTH, -trainDeg);
  }
  for (const feature of ["third_wheel", "third_pinion"]) {
    addRot(feature, THIRD, trainDeg);
  }

  // Small seconds hand rides the fourth-wheel arbor (clockwise from dial).
  addRot("sub_seconds_hand", FOURTH, -trainDeg);

  // Chronograph shown running: the center runner sweeps one full turn per loop
  // (full revolutions are always seam-free), the coupling wheel counter-
  // rotates, and the chrono seconds hand rides the runner arbor.
  const runnerDeg = -360 * effRun;
  for (const feature of [
    "chrono_runner_wheel",
    "chrono_runner_heart_cam",
    "chrono_runner_arbor",
    "chrono_seconds_hand",
    "chrono_hand_cap",
  ]) {
    addRot(feature, CENTER, runnerDeg);
  }
  addRot("coupling_wheel", COUPLING, 360 * effRun);

  // --- emit ------------------------------------------------------------------
  const features = new Set([...rotations.keys(), ...offsets.keys()]);
  for (const feature of features) {
    const handle = m.get(REF[feature]);
    for (const [pivot, deg] of rotations.get(feature) || []) {
      handle.rotate(Z_AXIS, deg, pivot);
    }
    const translate = offsets.get(feature);
    if (translate) handle.translate(translate);
  }

  // Movement group: flip in place about its own center (child tiers and gear
  // pivots compose in pre-parent space), then rise out of the case. Reveal and
  // showcase both drive this; their contributions add (in practice one is
  // active at a time).
  const revealStage = revealStages(rv);
  const movementFlip = Math.min(1, st.flip + revealStage.flip);
  const movementRise = MOVEMENT_RISE * st.rise + REVEAL_RISE * revealStage.rise;
  if (movementFlip > 0 || movementRise > 0) {
    m
      .get(REF.movement_group)
      .rotate([1, 0, 0], 180 * movementFlip, MOVEMENT_CENTER)
      .translate([0, 0, movementRise]);
  }
}

export const clips = {
  running: {
    label: "Escapement running",
    duration: 6,
    loop: true,
    update(t, m) {
      choreograph({ run: (t / 6) % 1 }, m);
    },
  },
  reveal: {
    label: "Reveal movement",
    duration: 12,
    loop: true,
    update(t, m) {
      const progress = (t / 12) % 1;
      // Trapezoid timeline: open, hold with the face and escapement both
      // running in view, then close — so the loop is seamless.
      let r;
      if (progress < 0.35) r = smooth(progress / 0.35);
      else if (progress < 0.65) r = 1;
      else r = smooth((1 - progress) / 0.35);
      choreograph({ reveal: r, run: progress }, m);
    },
  },
  showcase: {
    label: "Showcase explode",
    duration: 12,
    loop: true,
    update(t, m) {
      const progress = (t / 12) % 1;
      choreograph({ showcase: progress, run: progress }, m);
    },
  },
  grand_tour: {
    label: "Grand tour",
    duration: 24,
    loop: true,
    update(t, m) {
      const progress = (t / 24) % 1;
      choreograph({ tour: progress, run: progress }, m);
    },
  },
};

// Mid-engine hypercar -- choreography.
//
// The split (see the $cad skill's kinematics reference): the DOOR MECHANISM is
// a typed mate declaration on @step (a cylindrical joint per side, geared by
// the "doors" coupling), because it is a real tree-structured articulation and
// belongs on the viewer's pose slider. Everything in THIS file is
// choreography -- staged explodes, timing, easing -- which mates cannot and
// should not express.
//
// Clips
//   showcase  the cinematic tour: skin off, interior out, engine back and then
//             apart, running gear off, then everything back together
//   doors     both doors through the full synchro-helix and shut again
//   explode   the whole car apart and back
//
// Every clip is an exact loop: each is built from window functions that are
// identically zero at cycle 0 and cycle 1, so the last frame equals the first
// and there is no jump on repeat.
//
// The `doors` clip re-describes the helix in JS rather than reading the mates:
// animation is deliberately ignorant of kinematics, which is what guarantees a
// choreography edit can never invalidate a build. The constants below are the
// SAME numbers hypercar.py hands the mates, both read out of lib/hinge.py.

// --- helix, straight out of lib/hinge.py -----------------------------------

const DOOR_SWEEP_DEG = 62.0; // total rotation about the tower axis
const HELIX_LEAD = 5.0; // mm of axial travel per degree of rotation
// => 310 mm along the axis = 299 up, 80 forward

const DOORS = [
  {
    // left
    origin: [811.8501485267049, 919.8407997711387, 390.4092944787193],
    axis: [0.25761192449358467, 0.040017386329100534, 0.9654194451895503],
    sign: -1.0,
    // Everything that rides with the door: the panel, its glass, its trim, its
    // mirror, and the two mechanism parts bolted to the door.
    parts: [
      "door:left",
      "side_glass:left",
      "door_card_upper:left",
      "door_card_lower:left",
      "door_pull:left",
      "mirror_housing:left",
      "mirror_bezel:left",
      "mirror_glass:left",
      "mirror_stalk:left",
      "mirror_base:left",
      "door_bracket:left",
      "door_lug_lower:left",
    ],
  },
  {
    // right: mirrored axis AND reversed sense, so the doors open as mirror
    // images of each other
    origin: [811.8501485267049, -919.8407997711387, 390.4092944787193],
    axis: [0.25761192449358467, -0.040017386329100534, 0.9654194451895503],
    sign: 1.0,
    parts: [
      "door:right",
      "side_glass:right",
      "door_card_upper:right",
      "door_card_lower:right",
      "door_pull:right",
      "mirror_housing:right",
      "mirror_bezel:right",
      "mirror_glass:right",
      "mirror_stalk:right",
      "mirror_base:right",
      "door_bracket:right",
      "door_lug_lower:right",
    ],
  },
];

// --- easing ----------------------------------------------------------------

function clamp01(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0;
}

function smooth(t) {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
}

// rise a..b, hold b..c, fall c..d, zero outside. Every tour window ends its
// fall before phase 1, which is what makes the loop exact.
function win(p, a, b, c, d) {
  if (p <= a || p >= d) return 0;
  if (p < b) return smooth((p - a) / (b - a));
  if (p <= c) return 1;
  return 1 - smooth((p - c) / (d - c));
}

// Raised cosine: 0 at both ends, 1 at the middle, and its derivative is 0 at
// the seam too, so the repeat has no visible kick.
function bump(p) {
  return 0.5 - 0.5 * Math.cos(2 * Math.PI * clamp01(p));
}

// --- explode ---------------------------------------------------------------
//
//   radial   away from the car's long axis -- each group leaves along its own
//            normal, so the shell opens like a flower instead of every panel
//            sliding the same way
//   lateral  straight out in +/-Y by which side the group sits on
//   fixed    along one declared vector
//   (the chassis appears nowhere: it is the spine everything else leaves)
//
// `centre` is the group's REST-POSE centre, measured off the built package.
// The retired sidecar read those centres from the runtime at every frame; the
// .anim.js handle deliberately exposes only transforms, so they are pinned
// here instead. They are geometry, not choreography -- re-measure them if the
// car's proportions move.
//
// `tour` is the window the group occupies in the showcase. The order -- skin,
// then glass and trim, then interior, then powertrain, then running gear -- is
// a strip-down: you always remove what is on top of the thing you want to see
// next, so the car never hides the part being shown.

const CAR_AXIS_Z = 560.0;

const SKIN_TOUR = [0.1, 0.22, 0.86, 0.97];
const TRIM_TOUR = [0.12, 0.24, 0.86, 0.97];
const INTERIOR_TOUR = [0.24, 0.36, 0.86, 0.97];
const POWERTRAIN_TOUR = [0.38, 0.5, 0.86, 0.97];
const SUSPENSION_TOUR = [0.66, 0.78, 0.84, 0.95];
const WHEEL_TOUR = [0.68, 0.8, 0.84, 0.95];
const BRAKE_TOUR = [0.7, 0.81, 0.84, 0.95];

function ids(prefix, from, to) {
  const out = [];
  for (let i = from; i <= to; i += 1) out.push(`${prefix}.${i}`);
  return out.join(",");
}

const GROUPS = [
  // body: the flanks swing out sideways, the upper skins lift, the ends draw
  // fore and aft, the floor drops away
  { target: "o1.1.3,o1.1.4,o1.1.5,o1.1.6,o1.1.18,o1.1.20,o1.1.22",
    centre: [-82.5, 772.8, 567.1], mode: "radial", gain: 1500, tour: SKIN_TOUR },
  { target: "o1.1.7,o1.1.8,o1.1.9,o1.1.10,o1.1.19,o1.1.21,o1.1.23",
    centre: [-82.5, -772.8, 567.1], mode: "radial", gain: 1500, tour: SKIN_TOUR },
  { target: "o1.1.2,o1.1.11,o1.1.13,o1.1.14,o1.1.15,o1.1.17",
    centre: [-82.5, 0.0, 849.1], mode: "radial", gain: 1500, tour: SKIN_TOUR },
  { target: "o1.1.1,o1.1.24,o1.1.25,o1.1.26",
    mode: "fixed", vec: [1500, 0, 150], tour: SKIN_TOUR },
  { target: "o1.1.16", mode: "fixed", vec: [-1500, 0, 150], tour: SKIN_TOUR },
  { target: "o1.1.12", mode: "fixed", vec: [0, 0, -900], tour: SKIN_TOUR },

  // glazing: side glass follows its own door's flank, screens lift, lenses
  // leave with the lamps they cover
  { target: "o1.2.2", centre: [-237.9, 513.6, 943.9], mode: "radial", gain: 2150,
    tour: [0.11, 0.23, 0.86, 0.97] },
  { target: "o1.2.3", centre: [-237.9, -513.6, 943.9], mode: "radial", gain: 2150,
    tour: [0.11, 0.23, 0.86, 0.97] },
  { target: "o1.2.1,o1.2.4", centre: [-230.0, 0.0, 947.9], mode: "radial", gain: 2150,
    tour: [0.11, 0.23, 0.86, 0.97] },
  { target: "o1.2.5,o1.2.6", mode: "fixed", vec: [1750, 0, 300],
    tour: [0.11, 0.23, 0.86, 0.97] },
  { target: "o1.2.7", mode: "fixed", vec: [-1750, 0, 300], tour: [0.11, 0.23, 0.86, 0.97] },

  // lighting: head and tail units leave out of their own ends
  { target: ids("o1.3", 1, 48), mode: "fixed", vec: [1750, 0, 560], tour: TRIM_TOUR },
  { target: ids("o1.3", 49, 92), mode: "fixed", vec: [-1750, 0, 560], tour: TRIM_TOUR },

  // chassis holds still -- no entry.

  // suspension: each corner straight out, the steering rack and ARBs along the
  // car so they stay legible between the corners
  { target: "o1.5.1", centre: [1242.1, 437.2, 448.9], mode: "lateral", gain: 1150,
    tour: SUSPENSION_TOUR },
  { target: "o1.5.2", centre: [1242.1, -437.2, 448.9], mode: "lateral", gain: 1150,
    tour: SUSPENSION_TOUR },
  { target: "o1.5.3,o1.5.4", mode: "fixed", vec: [900, 0, 700], tour: SUSPENSION_TOUR },
  { target: ids("o1.6", 1, 48), centre: [-1453.2, 546.9, 490.3], mode: "lateral",
    gain: 1150, tour: SUSPENSION_TOUR },
  { target: ids("o1.6", 49, 96), centre: [-1453.2, -546.9, 490.0], mode: "lateral",
    gain: 1150, tour: SUSPENSION_TOUR },
  { target: ids("o1.6", 97, 101), mode: "fixed", vec: [-900, 0, 700], tour: SUSPENSION_TOUR },

  // wheels and brakes: off their own hubs, one corner at a time in space
  { target: "o1.7.1,o1.7.5", centre: [1326.9, 855.3, 403.1], mode: "lateral", gain: 2400,
    tour: WHEEL_TOUR },
  { target: "o1.7.2,o1.7.6", centre: [1326.9, -855.3, 403.1], mode: "lateral", gain: 2400,
    tour: WHEEL_TOUR },
  { target: "o1.7.3,o1.7.7", centre: [-1351.6, 835.2, 424.4], mode: "lateral", gain: 2400,
    tour: WHEEL_TOUR },
  { target: "o1.7.4,o1.7.8", centre: [-1351.6, -835.2, 424.4], mode: "lateral", gain: 2400,
    tour: WHEEL_TOUR },
  { target: "o1.8.1,o1.8.2", centre: [1350.0, 852.7, 397.0], mode: "lateral", gain: 1750,
    tour: BRAKE_TOUR },
  { target: "o1.8.3,o1.8.4", centre: [1347.7, -847.3, 388.1], mode: "lateral", gain: 1750,
    tour: BRAKE_TOUR },
  { target: "o1.8.5,o1.8.6", centre: [-1350.0, 830.0, 407.2], mode: "lateral", gain: 1750,
    tour: BRAKE_TOUR },
  { target: "o1.8.7,o1.8.8", centre: [-1350.0, -830.0, 417.4], mode: "lateral", gain: 1750,
    tour: BRAKE_TOUR },

  // powertrain out of the back as one unit; it comes apart later, on its own
  { target: "o1.9", mode: "fixed", vec: [-2350, 0, 320], tour: POWERTRAIN_TOUR },

  // interior lifts straight out of the tub
  { target: "o1.10", mode: "fixed", vec: [140, 0, 1950], tour: INTERIOR_TOUR },

  // aero: front furniture forward and down, floor and diffuser back and down,
  // wing back and up -- each leaves the way it was fitted
  { target: ids("o1.11", 1, 11), mode: "fixed", vec: [1900, 0, -200], tour: TRIM_TOUR },
  { target: ids("o1.11", 12, 18), mode: "fixed", vec: [-1400, 0, -800], tour: TRIM_TOUR },
  { target: ids("o1.11", 19, 24), mode: "fixed", vec: [-1200, 0, 900], tour: TRIM_TOUR },

  // door mechanism: outboard with its own flank
  { target: "o1.12.1", centre: [798.5, 821.4, 529.0], mode: "lateral", gain: 1400,
    tour: TRIM_TOUR },
  { target: "o1.12.2", centre: [798.5, -821.4, 529.0], mode: "lateral", gain: 1400,
    tour: TRIM_TOUR },

  // details: side jewellery out with its flank, badges and filler straight up
  { target: ids("o1.13", 1, 37), centre: [-64.7, 652.5, 691.5], mode: "radial", gain: 2500,
    tour: SKIN_TOUR },
  { target: ids("o1.13", 38, 74), centre: [-64.7, -652.5, 691.5], mode: "radial", gain: 2500,
    tour: SKIN_TOUR },
  { target: ids("o1.13", 75, 84), mode: "fixed", vec: [0, 0, 1400], tour: SKIN_TOUR },
];

// --- engine sub-explode ----------------------------------------------------
//
// The powertrain gets a second, nested stage: once the whole unit has moved
// clear of the car it comes apart on its own, around the block. Directions are
// derived from each part's rest-pose centre relative to the block, so heads and
// cam covers leave along their real bank angle rather than a hand-picked
// vector. `vec` overrides that where a fixed direction reads better (the plenum
// straight up, the transaxle straight back).

const ENGINE_ANCHOR = [-1500.0, 0.0, 478.6]; // engine_block:v12
const ENGINE_TOUR = [0.52, 0.62, 0.8, 0.9];

const ENGINE_PARTS = [
  { target: "o1.9.2", centre: [-1343.7, 0.0, 626.6], gain: 520 }, // head, front bank
  { target: "o1.9.4", centre: [-1656.3, 0.0, 626.6], gain: 520 }, // head, rear bank
  { target: "o1.9.3", centre: [-1310.9, 0.0, 685.6], gain: 980 }, // cam cover, front
  { target: "o1.9.5", centre: [-1689.1, 0.0, 685.6], gain: 980 }, // cam cover, rear
  { target: "o1.9.6", centre: [-1500.0, 388.0, 468.0], gain: 760 },
  { target: "o1.9.8", centre: [-1500.0, -388.0, 468.0], gain: 760 },
  { target: "o1.9.7,o1.9.9", centre: [-1500.0, 0.0, 884.0], gain: 760 },
  { target: "o1.9.10", vec: [0, 0, 1250] }, // intake plenum
  { target: "o1.9.11", centre: [-1800.2, 0.2, 526.1], gain: 900 }, // exhaust
  { target: "o1.9.12", vec: [-1150, 0, 60] }, // transaxle
];

// --- vectors ---------------------------------------------------------------

function scaled(v, k) {
  return [v[0] * k, v[1] * k, v[2] * k];
}

function unitTimes(d, gain) {
  const m = Math.hypot(d[0], d[1], d[2]);
  if (m < 1e-3) return [0, 0, gain];
  return [(d[0] / m) * gain, (d[1] / m) * gain, (d[2] / m) * gain];
}

function explodeVector(spec) {
  if (spec.mode === "fixed") return spec.vec;
  const c = spec.centre;
  if (spec.mode === "lateral") return [0, c[1] >= 0 ? spec.gain : -spec.gain, 0];
  return unitTimes([0, c[1], c[2] - CAR_AXIS_Z], spec.gain); // radial
}

function engineVector(spec) {
  if (spec.vec) return spec.vec;
  const c = spec.centre;
  return unitTimes(
    [c[0] - ENGINE_ANCHOR[0], c[1] - ENGINE_ANCHOR[1], c[2] - ENGINE_ANCHOR[2]],
    spec.gain
  );
}

// --- the moves --------------------------------------------------------------

// One group's explode step. k is 0..1.
function explodeGroup(m, spec, k) {
  if (k <= 0) return;
  const v = explodeVector(spec);
  if (!v[0] && !v[1] && !v[2]) return;
  m.get(spec.target).translate(scaled(v, k));
}

// The engine's own stage. It accumulates ON TOP of the powertrain translation
// (transforms premultiply), so the V12 comes apart where it already stands
// instead of dragging itself back across the car.
function explodeEngine(m, k) {
  if (k <= 0) return;
  for (const spec of ENGINE_PARTS) {
    const v = engineVector(spec);
    if (!v[0] && !v[1] && !v[2]) continue;
    m.get(spec.target).translate(scaled(v, k));
  }
}

// Both doors through the synchro-helix at u = 0..1. Rotation and axial travel
// share one axis, so the door rotates outward while sweeping up and forward
// along the same line: a true helix, not a scissor, butterfly or gullwing.
function openDoors(m, u) {
  if (u <= 0) return;
  for (const door of DOORS) {
    const travel = u * DOOR_SWEEP_DEG * HELIX_LEAD;
    const slide = scaled(door.axis, travel);
    for (const part of door.parts) {
      m.get(part)
        .rotate(door.axis, door.sign * u * DOOR_SWEEP_DEG, door.origin)
        .translate(slide);
    }
  }
}

export const clips = {
  // The headline loop. Long enough to dwell on each system rather than
  // flicking past it -- the staged strip-down needs time to read, especially
  // the engine's own sub-explode.
  //
  // NOTE: the retired sidecar also lifted the emissive of whichever system was
  // being featured. The animation handle exposes transforms, opacity and
  // visibility only, and fading systems in a dark scene just makes it muddy,
  // so the tour now tells the eye where to look by TIMING alone.
  showcase: {
    label: "Showcase tour",
    description:
      "Skin away, interior out, engine back and then apart, running gear off, then reassembled. Doors stay shut. Loops exactly.",
    duration: 48,
    loop: true,
    update(t, m) {
      const p = clamp01((t / 48) % 1);
      for (const spec of GROUPS) {
        explodeGroup(m, spec, win(p, spec.tour[0], spec.tour[1], spec.tour[2], spec.tour[3]));
      }
      explodeEngine(m, win(p, ENGINE_TOUR[0], ENGINE_TOUR[1], ENGINE_TOUR[2], ENGINE_TOUR[3]));
    },
  },

  doors: {
    label: "Doors",
    description: "Both doors through the full synchro-helix and back. Loops exactly.",
    duration: 7,
    loop: true,
    update(t, m) {
      openDoors(m, bump((t / 7) % 1));
    },
  },

  explode: {
    label: "Explode",
    description: "The whole car apart and back together. Loops exactly.",
    duration: 10,
    loop: true,
    update(t, m) {
      const k = bump((t / 10) % 1);
      for (const spec of GROUPS) explodeGroup(m, spec, k);
      // the manual explode drives the engine apart too, so the sub-explode is
      // not only reachable through the tour
      explodeEngine(m, k);
    },
  },
};

// Mid-engine hypercar -- STEP module sidecar.
//
// Parameters
//   doorAngle  0..1  both doors through the full DIHEDRAL SYNCHRO-HELIX.
//                    Rotation and axial travel are coupled through ONE lead
//                    constant, so the door follows a true helix: it rotates
//                    outward while sweeping up and forward along the same
//                    axis, lifting clear of the body without swinging wide.
//                    Not a scissor, not a butterfly, not a gullwing.
//   explode    0..1  every part outward along its own vector, GROUPED BY
//                    SYSTEM, so the structure reads instead of becoming a
//                    cloud of debris.  The chassis holds still.
//   demo_mode        "off" for the manual controls above, "showcase" to hand
//                    both over to the staged tour driven by demo_phase.
//   demo_phase 0..1  scrubs the tour.  Exposed as a real parameter so the
//                    cinematic sequence can be sampled headlessly -- the
//                    snapshot CLI ignores manifest.animations entirely.
//
// Animations (viewer: play / pause / scrub / speed)
//   showcase      the cinematic tour -- see TOUR below
//   doorCycle     doors open and shut
//   explodeCycle  the whole car apart and back
//
// EVERY animation is an exact loop: each one is built from functions that are
// identically zero at cycle 0 and cycle 1, so the last frame equals the first
// and there is no jump on repeat.
//
// The helix constants are NOT eyeballed -- they are the values the mechanism
// itself is built from, exported by hypercar_parts/hinge.py as
// HELIX_AXIS_ORIGIN / HELIX_AXIS_DIR / HELIX_LEAD_MM_PER_DEG / DOOR_SWEEP_DEG
// / DOOR_SWEEP_SIGN.  Change the tower in the Python and re-read these.

// --- helix, straight out of hinge.py ---------------------------------------

const DOOR_SWEEP_DEG = 62.0;   // total rotation about the tower axis
const HELIX_LEAD = 5.0;        // mm of axial travel per degree of rotation
                               // => 310 mm along the axis = 299 up, 80 forward

const HELIX = {
  1: {                          // left
    origin: [811.85, 919.841, 390.409],
    axis: [0.257612, 0.040017, 0.965419],
    sign: -1.0
  },
  "-1": {                       // right: mirrored axis AND reversed sense, so
    origin: [811.85, -919.841, 390.409],   // the doors open as mirror images
    axis: [0.257612, -0.040017, 0.965419],
    sign: 1.0
  }
};

function helixFor(side, t) {
  const h = HELIX[String(side)];
  const travel = t * DOOR_SWEEP_DEG * HELIX_LEAD;
  return [
    { rotate: { axis: h.axis, origin: h.origin, angleDeg: h.sign * t * DOOR_SWEEP_DEG } },
    { translate: [h.axis[0] * travel, h.axis[1] * travel, h.axis[2] * travel] }
  ];
}

// --- easing ----------------------------------------------------------------

function clamp01(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0;
}

function smooth(t) {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
}

// rise a..b, hold b..c, fall c..d, zero outside.  Every tour window ends its
// fall before phase 1, which is what makes the loop exact.
function win(p, a, b, c, d) {
  if (p <= a || p >= d) return 0;
  if (p < b) return smooth((p - a) / (b - a));
  if (p <= c) return 1;
  return 1 - smooth((p - c) / (d - c));
}

// --- explode ---------------------------------------------------------------
//
//   radial   away from the car's long axis -- each panel leaves along its own
//            normal, so the shell opens like a flower instead of every panel
//            sliding the same way
//   lateral  straight out in +/-Y by which side the part sits on
//   fixed    along one declared vector
//   hold     stays put; the chassis is the spine everything else leaves
//
// `tour` is the window this system occupies in the showcase.  The order --
// skin, then glass and trim, then interior, then powertrain, then running
// gear -- is a strip-down: you always remove what is on top of the thing you
// want to see next, so the car never hides the part being shown.

const CAR_AXIS_Z = 560.0;

const SYSTEMS = {
  body:             { mode: "radial",  gain: 1500, tour: [0.10, 0.22, 0.86, 0.97] },
  glazing:          { mode: "radial",  gain: 2150, tour: [0.11, 0.23, 0.86, 0.97] },
  lighting:         { mode: "fixed",   vec: [1750, 0, 560], tour: [0.12, 0.24, 0.86, 0.97] },
  chassis:          { mode: "hold" },
  suspension_front: { mode: "lateral", gain: 1150, tour: [0.66, 0.78, 0.84, 0.95] },
  suspension_rear:  { mode: "lateral", gain: 1150, tour: [0.66, 0.78, 0.84, 0.95] },
  wheels:           { mode: "lateral", gain: 2400, tour: [0.68, 0.80, 0.84, 0.95] },
  brakes:           { mode: "lateral", gain: 1750, tour: [0.70, 0.81, 0.84, 0.95] },
  powertrain:       { mode: "fixed",   vec: [-2350, 0, 320], tour: [0.38, 0.50, 0.86, 0.97] },
  interior:         { mode: "fixed",   vec: [140, 0, 1950], tour: [0.24, 0.36, 0.86, 0.97] },
  aero:             { mode: "radial",  gain: 1900, tour: [0.12, 0.24, 0.86, 0.97] },
  hinge:            { mode: "lateral", gain: 1400, tour: [0.12, 0.24, 0.86, 0.97] },
  details:          { mode: "radial",  gain: 2500, tour: [0.10, 0.22, 0.86, 0.97] }
};

// --- engine sub-explode ----------------------------------------------------
//
// The powertrain gets a second, nested stage: once the whole unit has moved
// clear of the car it comes apart on its own, around the block.  Directions are
// derived at runtime from each part's rest-pose centre relative to the block,
// so heads and cam covers leave along their real bank angle rather than a
// hand-picked vector.  `vec` overrides that where a fixed direction reads
// better (the plenum straight up, the transaxle straight back).

const ENGINE_ANCHOR = "engine_block";
const ENGINE_TOUR = [0.52, 0.62, 0.80, 0.90];

const ENGINE_PARTS = {
  engine_heads:      { gain: 520 },
  engine_cam_covers: { gain: 980 },
  engine_gear_drive: { gain: 760 },
  engine_intake:     { vec: [0, 0, 1250] },
  engine_exhaust:    { gain: 900 },
  engine_transaxle:  { vec: [-1150, 0, 60] }
};

function engineVector(spec, feature, anchor) {
  if (spec.vec) return spec.vec;
  const c = (feature && feature.center) || anchor;
  const d = [c[0] - anchor[0], c[1] - anchor[1], c[2] - anchor[2]];
  const m = Math.hypot(d[0], d[1], d[2]);
  if (m < 1e-3) return [0, 0, spec.gain];
  return [d[0] / m * spec.gain, d[1] / m * spec.gain, d[2] / m * spec.gain];
}

// Which system is being SHOWN at each point of the tour.  The featured system
// gets a warm emissive lift so the eye is told where to look; nothing is
// faded, because dimming a dark scene just makes it muddy.
const FEATURE = [
  { id: null,         a: 0.00, b: 0.10 },   // the whole car, shut
  { id: "body",       a: 0.10, b: 0.24 },   // skin, glass, aero come off
  { id: "interior",   a: 0.24, b: 0.38 },   // seats, wheel, dash
  { id: "powertrain", a: 0.38, b: 0.68 },   // V12 out, then the V12 apart
  { id: "wheels",     a: 0.68, b: 0.82 },   // rims, tyres, brakes, suspension
  { id: null,         a: 0.82, b: 1.00 }    // full spread, then reassemble
];

const FEATURE_EMISSIVE = "#5a2410";
const FEATURE_INTENSITY = 0.30;

function featuredAt(p) {
  for (const f of FEATURE) {
    if (p >= f.a && p < f.b) return f.id;
  }
  return null;
}

// The showcase no longer opens the doors.  The helix is still on the doorAngle
// slider and its own doorCycle animation; the tour is about the exploded
// structure, and a door swinging through the first stage only competed with it.

// Everything that rides with a door: the panel, its glass, its trim, its
// mirror, and the carrier assembly that actually travels the helix.
const DOOR_PARTS = {
  1: ["door_left", "door_glass_left", "door_card_left", "mirror_left", "door_carrier_left"],
  "-1": ["door_right", "door_glass_right", "door_card_right", "mirror_right", "door_carrier_right"]
};

function scaled(v, k) {
  return [v[0] * k, v[1] * k, v[2] * k];
}

function radialUnit(feature) {
  const c = (feature && feature.center) || [0, 0, CAR_AXIS_Z];
  const dy = c[1];
  const dz = c[2] - CAR_AXIS_Z;
  const m = Math.hypot(dy, dz);
  if (m < 1e-3) return [0, 0, 1];
  return [0, dy / m, dz / m];
}

function lateralUnit(feature) {
  const c = (feature && feature.center) || [0, 0, 0];
  return [0, c[1] >= 0 ? 1 : -1, 0];
}

function explodeVector(spec, feature) {
  if (spec.mode === "hold") return [0, 0, 0];
  if (spec.mode === "fixed") return spec.vec;
  const unit = spec.mode === "lateral" ? lateralUnit(feature) : radialUnit(feature);
  return scaled(unit, spec.gain);
}

// Resolve the pose: either the two manual sliders, or the staged tour.
function pose(params) {
  const showcase = String(params.demo_mode || "off") === "showcase";
  const factors = {};
  if (!showcase) {
    const e = smooth(clamp01(params.explode));
    for (const id of Object.keys(SYSTEMS)) factors[id] = e;
    // the manual slider drives the engine apart too, so the sub-explode is not
    // only reachable through the tour
    return { factors, engine: e, door: clamp01(params.doorAngle), featured: null };
  }
  const p = clamp01(params.demo_phase);
  for (const [id, spec] of Object.entries(SYSTEMS)) {
    factors[id] = spec.tour ? win(p, spec.tour[0], spec.tour[1], spec.tour[2], spec.tour[3]) : 0;
  }
  return {
    factors,
    engine: win(p, ENGINE_TOUR[0], ENGINE_TOUR[1], ENGINE_TOUR[2], ENGINE_TOUR[3]),
    door: 0,
    featured: featuredAt(p)
  };
}

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/hypercar/hypercar.step" },
    label: "Mid-engine hypercar",
    description: "Dihedral synchro-helix doors and a staged, looping exploded showcase.",
    units: { length: "mm", angle: "deg", time: "s" },

    features: {
      // system groups -- these ARE the assembly order in hypercar.step.py
      body: { ref: "#o1.1", label: "Body panels" },
      glazing: { ref: "#o1.2", label: "Glazing" },
      lighting: { ref: "#o1.3", label: "Lighting" },
      chassis: { ref: "#o1.4", label: "Chassis" },
      suspension_front: { ref: "#o1.5", label: "Front suspension" },
      suspension_rear: { ref: "#o1.6", label: "Rear suspension" },
      wheels: { ref: "#o1.7", label: "Wheels" },
      brakes: { ref: "#o1.8", label: "Brakes" },
      powertrain: { ref: "#o1.9", label: "Powertrain" },
      interior: { ref: "#o1.10", label: "Interior" },
      aero: { ref: "#o1.11", label: "Aero" },
      hinge: { ref: "#o1.12", label: "Door mechanism" },
      details: { ref: "#o1.13", label: "Detail parts" },

      // powertrain sub-groups, for the engine's own stage of the showcase
      engine_block: { ref: "#o1.9.1", label: "Engine block (V12)" },
      engine_heads: { ref: "#o1.9.2,o1.9.4", label: "Cylinder heads" },
      engine_cam_covers: { ref: "#o1.9.3,o1.9.5", label: "Cam covers" },
      engine_gear_drive: { ref: "#o1.9.6,o1.9.7,o1.9.8,o1.9.9", label: "Gear drive" },
      engine_intake: { ref: "#o1.9.10", label: "Intake plenum" },
      engine_exhaust: { ref: "#o1.9.11", label: "Exhaust" },
      engine_transaxle: { ref: "#o1.9.12", label: "Transaxle" },

      // the parts a door carries
      door_left: { ref: "#o1.1.4", label: "Door skin (left)" },
      door_right: { ref: "#o1.1.8", label: "Door skin (right)" },
      door_glass_left: { ref: "#o1.2.2", label: "Side glass (left)" },
      door_glass_right: { ref: "#o1.2.3", label: "Side glass (right)" },
      door_card_left: { ref: "#o1.10.58,o1.10.59,o1.10.60", label: "Door card (left)" },
      door_card_right: { ref: "#o1.10.61,o1.10.62,o1.10.63", label: "Door card (right)" },
      mirror_left: { ref: "#o1.13.1,o1.13.2,o1.13.3,o1.13.4,o1.13.5", label: "Mirror (left)" },
      mirror_right: { ref: "#o1.13.38,o1.13.39,o1.13.40,o1.13.41,o1.13.42", label: "Mirror (right)" },
      // carrier + door bracket + lugs: the parts of the mechanism that
      // actually travel the helix, as opposed to the tower and rails
      door_carrier_left: {
        ref: "#o1.12.1.8,o1.12.1.9,o1.12.1.12,o1.12.1.13,o1.12.1.14,o1.12.1.21",
        label: "Helix carrier (left)"
      },
      door_carrier_right: {
        ref: "#o1.12.2.8,o1.12.2.9,o1.12.2.12,o1.12.2.13,o1.12.2.14,o1.12.2.21",
        label: "Helix carrier (right)"
      }
    },

    parameters: {
      doorAngle: {
        type: "number",
        label: "Doors",
        description:
          "Dihedral synchro-helix: the doors rotate 62 deg outward while sweeping 299 mm up and 80 mm forward along the same axis. 0 shut, 1 fully open.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.005
      },
      explode: {
        type: "number",
        label: "Explode",
        description:
          "Separates the car by system. The chassis holds still and every other system moves away from it along its own vector.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.005
      },
      demo_mode: {
        type: "select",
        label: "Timeline",
        description:
          "Showcase hands Doors and Explode over to the staged tour and scrubs them with Tour phase.",
        default: "off",
        options: [
          { value: "off", label: "Off (manual)" },
          { value: "showcase", label: "Showcase tour" }
        ]
      },
      demo_phase: {
        type: "number",
        label: "Tour phase",
        description:
          "Scrubs the showcase: doors, then skin off, then interior, then powertrain, then running gear, then everything back together.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.002
      }
    },

    animations: {
      // The headline loop. Long enough to dwell on each system rather than
      // flicking past it.
      showcase: {
        label: "Showcase tour",
        description:
          "Skin away, interior out, engine back and then apart, running gear off, then reassembled. Doors stay shut. Loops exactly.",
        duration: 48,   // 2x slower than the original 24 s -- the staged
                        // strip-down needs time to read, especially the
                        // engine's own sub-explode
        loop: true,
        update({ cycle, set }) {
          set("demo_mode", "showcase");
          set("demo_phase", cycle % 1);
        }
      },
      // Raised cosine: 0 at both ends, 1 at the middle, and its derivative is
      // 0 at the seam too, so the repeat has no visible kick.
      doorCycle: {
        label: "Doors",
        description: "Doors through the full synchro-helix and back. Loops exactly.",
        duration: 7,
        loop: true,
        update({ cycle, set }) {
          set("demo_mode", "off");
          set("explode", 0);
          set("doorAngle", 0.5 - 0.5 * Math.cos(2 * Math.PI * (cycle % 1)));
        }
      },
      explodeCycle: {
        label: "Explode",
        description: "The whole car apart and back together. Loops exactly.",
        duration: 10,
        loop: true,
        update({ cycle, set }) {
          set("demo_mode", "off");
          set("doorAngle", 0);
          set("explode", 0.5 - 0.5 * Math.cos(2 * Math.PI * (cycle % 1)));
        }
      }
    }
  },

  update({ params, features, effects }) {
    const { factors, engine, door, featured } = pose(params);

    for (const [id, spec] of Object.entries(SYSTEMS)) {
      const feature = features[id];
      if (!feature || feature.missing) continue;

      const k = factors[id] || 0;
      if (k > 0) {
        const v = explodeVector(spec, feature);
        if (v[0] || v[1] || v[2]) {
          effects.transform(id, { transforms: [{ translate: scaled(v, k) }] });
        }
      }

      // effects are cleared every frame, so the lift has to be re-declared
      // (and explicitly cleared) on every system, every call
      effects.style(id, {
        emissive: id === featured ? FEATURE_EMISSIVE : "",
        emissiveIntensity: id === featured ? FEATURE_INTENSITY : 0
      });
    }

    // Engine's own stage: the powertrain has already moved out as a unit, so
    // these accumulate on top of that translation and take the V12 apart in
    // place rather than dragging it back across the car.
    if (engine > 0) {
      const anchorFeature = features[ENGINE_ANCHOR];
      const anchor = (anchorFeature && anchorFeature.center) || [0, 0, 0];
      for (const [id, spec] of Object.entries(ENGINE_PARTS)) {
        const feature = features[id];
        if (!feature || feature.missing) continue;
        const v = engineVector(spec, feature, anchor);
        if (!v[0] && !v[1] && !v[2]) continue;
        effects.transform(id, { transforms: [{ translate: scaled(v, engine) }] });
      }
    }

    if (door > 0) {
      for (const side of [1, -1]) {
        const ids = DOOR_PARTS[String(side)].filter(
          (id) => features[id] && !features[id].missing
        );
        if (!ids.length) continue;
        // accumulates on top of the explode translation, so a door can be both
        // open and exploded
        effects.transform(ids, { transforms: helixFor(side, door) });
      }
    }
  }
};

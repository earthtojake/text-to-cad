// f14d.params.js — exploded-view sidecar for f14d.step.py.
//
// Viewer-time presentation only: rigid translations away from the baked rest
// pose, plus an opacity ramp on the skin. No geometry lives here.
//
// WHY THE SKIN FADES RATHER THAN JUST MOVING. The airframe is one lofted solid
// (f14_parts/body.py) and it encloses everything worth looking at -- cockpit
// tub, inlet ducts, engine bays, gear wells. Translate it far enough to clear
// the internals and the aircraft stops reading as an aircraft; leave it opaque
// and close and it hides them. So it does both, gently: lifts up and forward
// while dropping to ~22% opacity, which keeps the Tomcat silhouette overhead as
// context while the systems fan out underneath it.
//
// WHY THE STAGES OVERLAP. Everything moving on the same 0..1 ramp reads as one
// object inflating. Each system instead gets its own window inside the ramp, so
// the skin is already lifting before the cockpit follows, and the details land
// last -- the eye gets a sequence to follow instead of a single pop. The
// windows overlap on purpose: strict succession looks mechanical, and at 8 s a
// fully serial teardown gives each system under a second of travel.

const clamp01 = (v) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));

// Hermite ease. Applied per stage rather than to the master parameter so the
// manual slider stays linear and predictable while each part still starts and
// stops softly.
const smoothstep = (t) => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};

// TWO ACTS ON ONE PARAMETER. Act 1 separates the ten systems; act 2 breaks the
// wings and the aft section down into their own parts. Both are driven by the
// single `exploded` ramp rather than a second parameter, because a GIF sweep is
// linear over ONE parameter -- two parameters would sweep simultaneously, not in
// sequence, and the second act would happen during the first.
//
// The acts overlap by 0.06 so the handoff is continuous: the last systems are
// still settling as the first control surfaces start to leave the wing.
const ACT1_END = 0.58;
const ACT2_START = 0.52;

const act1 = (e) => clamp01(e / ACT1_END);
const act2 = (e) => clamp01((e - ACT2_START) / (1 - ACT2_START));

// Per-system window inside ACT 1 (0..1 within the act, not within the master).
const STAGE = {
  airframe: [0.00, 0.55],
  cockpit: [0.10, 0.62],
  wings: [0.16, 0.68],
  empennage: [0.22, 0.74],
  nozzles: [0.26, 0.78],
  aft: [0.32, 0.84],
  inlets: [0.38, 0.88],
  main_gear: [0.44, 0.92],
  nose_gear: [0.48, 0.96],
  details: [0.52, 1.00],
};

const staged = (table, id, t) => {
  const [a, b] = table[id] || [0, 1];
  return smoothstep(b > a ? (t - a) / (b - a) : t);
};

// Per-subassembly window inside ACT 2.
const SUBSTAGE = {
  spoilers: [0.00, 0.42],
  slats: [0.08, 0.52],
  flaps: [0.14, 0.58],
  tip_port: [0.24, 0.66],
  tip_stbd: [0.24, 0.66],
  sb_dorsal: [0.30, 0.72],
  sb_ventral_port: [0.38, 0.80],
  sb_ventral_stbd: [0.38, 0.80],
  beavertail: [0.48, 0.88],
  tailhook: [0.56, 1.00],
};

// Act-2 travel, ADDITIVE on top of the parent system's act-1 translation --
// child transforms compose with their group's, so these are offsets from where
// the wing or the aft section has already moved to, not world positions.
//
// Each surface leaves the way it is actually removed: slats forward off the
// leading edge, flaps aft and down off the trailing edge, spoilers straight up
// out of their wells, speedbrakes opening about their hinge lines, the hook
// dropping. Mirrored pairs are split so port goes +Y and starboard -Y; one ref
// moves everything it matches by the same vector.
const SUBEXPLODE = {
  spoilers: [0, 0, 1100],
  slats: [-1300, 0, 250],
  flaps: [1500, 0, -450],
  tip_port: [0, 1500, 250],
  tip_stbd: [0, -1500, 250],
  sb_dorsal: [200, 0, 1500],
  sb_ventral_port: [200, 1100, -1200],
  sb_ventral_stbd: [200, -1100, -1200],
  beavertail: [1600, 0, 0],
  tailhook: [800, 0, -1400],
};

// Separation travel at full explode, in MILLIMETRES on the model's own axes:
// +X aft (nose at X=0), +Y port, +Z up. The aircraft is 19.11 m long and 4.88 m
// tall, so these are sized against that -- the skin clears by about a fuselage
// height, and nothing travels so far that the group leaves frame in a
// three-quarter view.
//
// Directions follow how the real thing comes apart rather than a radial burst:
// nozzles draw aft off the engine faces, gear drops out of its wells, inlets
// swing down and forward off the duct line, tails lift up and aft.
const EXPLODE = {
  airframe: [-1400, 0, 5200],
  cockpit: [-500, 0, 2500],
  wings: [200, 0, 3300],
  empennage: [1900, 0, 2700],
  nozzles: [4400, 0, 300],
  aft: [2700, 0, -600],
  inlets: [-1000, 0, -2500],
  main_gear: [200, 0, -2300],
  nose_gear: [-1900, 0, -1700],
  details: [0, 0, 1500],
};

// Occurrence refs are BY CHILD ORDER of the groups gen_step() actually returns,
// which is NOT the SYSTEMS list in f14d.step.py -- glove, engines and markings
// are listed there but have no module, so they take no number and everything
// after them shifts up. These ten are what the built package contains, read
// back off __cadgen__/models/f14d.step.py/assembly.json rather than counted off
// the source; the leaf names confirm each one (o1.1 airframe_skin, o1.3
// wing_panel:port, o1.6 fin:port, o1.9 mlg_wheel_arch:port).
//
// ADDING ANY OF THE THREE MISSING MODULES RENUMBERS EVERYTHING AFTER IT, and
// this block plus STAGE and EXPLODE have to be renumbered in the same commit.
// That is not hypothetical: `nozzles` was absent from this list until its
// revolve bug was fixed, and restoring it moved five systems by one.
const FEATURES = {
  airframe: { ref: "#o1.1", label: "Airframe skin (one blended loft)" },
  cockpit: { ref: "#o1.2", label: "Cockpit — tub, seats, panels, canopy" },
  wings: { ref: "#o1.3", label: "Wings — panels, slats, flaps, spoilers" },
  inlets: { ref: "#o1.4", label: "Inlets — ramps, splitters, ducts" },
  nozzles: { ref: "#o1.5", label: "Nozzles — C-D petals, seals, actuators" },
  empennage: { ref: "#o1.6", label: "Empennage — fins, rudders, stabilators" },
  aft: { ref: "#o1.7", label: "Aft — speed brakes, beavertail, hook" },
  nose_gear: { ref: "#o1.8", label: "Nose gear — leg, wheels, launch bar" },
  main_gear: { ref: "#o1.9", label: "Main gear — legs, wheels, doors, bays" },
  details: { ref: "#o1.10", label: "Details — antennas, probes, lights, vents" },
};

// Occurrence ids for the act-2 subassemblies, GENERATED -- do not hand-edit.
// A sidecar ref is an occurrence list, not a name selector, so these ~100 leaf
// ids come from the built package by name pattern:
//
//     python render/subrefs.py        (see that file for the patterns)
//
// They are as fragile as the o1.N refs above and go stale the same way: any
// rebuild that changes leaf COUNTS inside wings or aft invalidates them.
const SUBPARTS = {
  slats: "#o1.3.1.3,o1.3.1.4,o1.3.1.5,o1.3.1.6,o1.3.1.7,o1.3.1.8,o1.3.1.9,o1.3.1.10,o1.3.1.11,o1.3.1.12,o1.3.1.13,o1.3.1.14,o1.3.1.15,o1.3.2.3,o1.3.2.4,o1.3.2.5,o1.3.2.6,o1.3.2.7,o1.3.2.8,o1.3.2.9,o1.3.2.10,o1.3.2.11,o1.3.2.12,o1.3.2.13,o1.3.2.14,o1.3.2.15",   // 26 occurrences
  flaps: "#o1.3.1.16,o1.3.1.17,o1.3.1.18,o1.3.1.19,o1.3.1.20,o1.3.2.16,o1.3.2.17,o1.3.2.18,o1.3.2.19,o1.3.2.20",   // 10 occurrences
  spoilers: "#o1.3.1.21,o1.3.1.22,o1.3.1.23,o1.3.1.24,o1.3.2.21,o1.3.2.22,o1.3.2.23,o1.3.2.24",   // 8 occurrences
  tip_port: "#o1.3.1.25,o1.3.1.26,o1.3.1.27",   // 3 occurrences
  tip_stbd: "#o1.3.2.25,o1.3.2.26,o1.3.2.27",   // 3 occurrences
  sb_dorsal: "#o1.7.1,o1.7.2,o1.7.3,o1.7.4,o1.7.5,o1.7.6,o1.7.7,o1.7.8,o1.7.9,o1.7.10,o1.7.11,o1.7.12,o1.7.13,o1.7.14",   // 14 occurrences
  sb_ventral_port: "#o1.7.15,o1.7.16,o1.7.17,o1.7.18,o1.7.19,o1.7.20,o1.7.21,o1.7.22,o1.7.23,o1.7.24,o1.7.25,o1.7.26,o1.7.27,o1.7.28",   // 14 occurrences
  sb_ventral_stbd: "#o1.7.29,o1.7.30,o1.7.31,o1.7.32,o1.7.33,o1.7.34,o1.7.35,o1.7.36,o1.7.37,o1.7.38,o1.7.39,o1.7.40,o1.7.41,o1.7.42",   // 14 occurrences
  beavertail: "#o1.7.52,o1.7.53",   // 2 occurrences
  tailhook: "#o1.7.54,o1.7.55,o1.7.56,o1.7.57,o1.7.58,o1.7.59,o1.7.60,o1.7.61,o1.7.62,o1.7.63,o1.7.64,o1.7.65",   // 12 occurrences
};

// Act-2 groups have to be DECLARED FEATURES too -- effects.transform() resolves
// a feature id, not a raw ref, so a SUBPARTS entry the manifest does not list is
// silently a no-op.
const SUBLABEL = {
  slats: "Wing slats + tracks",
  flaps: "Wing flaps + track fairings",
  spoilers: "Wing spoilers",
  tip_port: "Wingtip light housing (port)",
  tip_stbd: "Wingtip light housing (stbd)",
  sb_dorsal: "Dorsal speed brake",
  sb_ventral_port: "Ventral speed brake (port)",
  sb_ventral_stbd: "Ventral speed brake (stbd)",
  beavertail: "Beavertail access panels",
  tailhook: "Tailhook + bay doors",
};

const ALL_FEATURES = { ...FEATURES };
Object.entries(SUBPARTS).forEach(([id, ref]) => {
  ALL_FEATURES[id] = { ref, label: SUBLABEL[id] || id };
});

const SKIN_OPACITY_MIN = 0.22;

const TIMELINES = {
  teardown: (phase) => ({ exploded: clamp01(phase) }),
};

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/f14d/f14d.step" },
    label: "F-14D Super Tomcat — exploded view",
    description:
      "Staged teardown: the skin lifts and fades, then each system separates " +
      "along the axis it actually comes off on.",
    units: { length: "mm", angle: "deg", time: "s" },
    features: ALL_FEATURES,
    parameters: {
      exploded: {
        type: "number",
        label: "Exploded view",
        default: 0,
        min: 0,
        max: 1,
        step: 0.005,
        description:
          "Staged separation of all ten systems. The skin fades as it lifts so " +
          "the internals stay visible underneath it.",
      },
      skin_fade: {
        type: "boolean",
        label: "Fade skin when exploded",
        default: true,
        description:
          "Off keeps the airframe fully opaque as it lifts — useful for reading " +
          "the outer surface, less useful for reading what is under it.",
      },
      demo_mode: {
        type: "select",
        label: "Demo timeline",
        default: "off",
        description: "Scrub with Demo phase; overrides the manual Exploded value.",
        options: [
          { value: "off", label: "Off (manual)" },
          { value: "teardown", label: "Staged teardown" },
        ],
      },
      demo_phase: {
        type: "number",
        label: "Demo phase",
        default: 0,
        min: 0,
        max: 1,
        step: 0.005,
      },
    },
    animations: {
      teardown: {
        label: "Staged teardown",
        description:
          "Out and back: the aircraft comes apart system by system, holds at " +
          "full separation, and reassembles.",
        // 60 s, not the 10 s this was authored at.  A published frame of this
        // aircraft costs the viewer far more than a display frame -- it is a
        // 2,392-record assembly -- so playback paces itself down to a low frame
        // rate rather than saturating the tab.  At 10 s that left the teardown
        // jumping in visibly coarse steps; stretching the clip shrinks the
        // per-frame delta by the same factor and the separation reads as motion
        // again.  Nothing about the choreography changes: every stage window in
        // STAGE/SUBSTAGE is a fraction of progress, not a time.
        duration: 60,
        loop: true,
        update({ progress, set }) {
          set("demo_mode", "off");
          // sin() rather than a sawtooth so the loop returns through the
          // reassembly instead of snapping back to the built aircraft.
          set("exploded", Math.sin(Math.PI * clamp01(progress)));
        },
      },
    },
  },

  update({ params: rawParams, effects }) {
    let params = rawParams;
    const mode = String(rawParams.demo_mode || "off");
    if (mode !== "off" && TIMELINES[mode]) {
      params = { ...rawParams, ...TIMELINES[mode](clamp01(rawParams.demo_phase)) };
    }

    const e = clamp01(params.exploded);
    effects.visible("*", true);

    // Act 1 -- the ten systems come off the aircraft.
    const e1 = act1(e);
    Object.keys(FEATURES).forEach((id) => {
      const t = staged(STAGE, id, e1);
      const v = EXPLODE[id] || [0, 0, 0];
      effects.transform(id, {
        transforms: [{ translate: [v[0] * t, v[1] * t, v[2] * t] }],
      });
    });

    // Act 2 -- the wings and the aft section come apart in turn. These ride on
    // top of act 1: the transform of a child occurrence composes with its
    // group's, so a spoiler ends up at the wing's travel plus its own.
    const e2 = act2(e);
    Object.keys(SUBPARTS).forEach((id) => {
      const t = staged(SUBSTAGE, id, e2);
      const v = SUBEXPLODE[id] || [0, 0, 0];
      effects.transform(id, {
        transforms: [{ translate: [v[0] * t, v[1] * t, v[2] * t] }],
      });
    });

    // The skin reaches minimum opacity well before it finishes travelling, so
    // the internals are already readable while it is still clearing them.
    const fade = params.skin_fade === false ? 0 : smoothstep(clamp01(e / 0.45));
    const opacity = 1 - (1 - SKIN_OPACITY_MIN) * fade;
    effects.style("airframe", {
      opacity,
      // Edges stay a little more present than the surface: at 22% the loft's
      // feature edges are what still describe the shape.
      edgeOpacity: Math.min(1, opacity + 0.3),
    });
  },
};

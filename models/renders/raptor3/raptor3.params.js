// raptor3.params.js — epic exploded-view animation sidecar for
// raptor3.step.py. Viewer-time presentation only (rigid deltas from the baked
// rest pose); geometry lives in the generator and requires regeneration.
//
// The "exploded_reveal" demo (driven by demo_phase in headless GIF sweeps, and
// mirrored as the default viewer animation) plays a STAGED radial+axial burst
// on a slow turntable: the thrust frame/gimbal cage lifts off and the nozzle
// drops away first, then the chamber, inlets and valves separate, the twin
// turbopumps swing out to port/starboard, and finally the injector head + LOX
// dome — the heart of the engine — lifts clear and is held in view. Each of
// the 12 subsystems flies to its own place so every internal component reads
// as a distinct part, then the whole diagram re-assembles seamlessly.
//
// Engine frame: centerline = Z, nozzle exit plane z=0, +Z up, interface plate
// at z~3100. Fuel (methane) hardware at -X, oxygen hardware at +X.

const clamp01 = (v) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));
const finite = (v, f = 0) => (Number.isFinite(v) ? v : f);
const smooth = (a, b, v) => {
  const t = clamp01((v - a) / (b - a || 1e-6));
  return t * t * (3 - 2 * t);
};
// Triangle 0->1->0 so a 0..1 demo_phase sweep explodes OUT then back IN,
// looping seamlessly; staging windows below play forward then reverse.
const triangle = (p) => 1 - Math.abs(2 * clamp01(p) - 1);
const DEG = Math.PI / 180;
const norm = (v) => {
  const m = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / m, v[1] / m, v[2] / m];
};
const rad = (deg) => [Math.cos(deg * DEG), Math.sin(deg * DEG), 0];

// Per-subsystem choreography: ref (gen_step child order), unit direction,
// travel (mm), and the [start,end] window on the 0..1 explode progress. Outer
// structure leaves first (low window); the injector head is revealed last
// (high window) and emphasized.
//
// GROUNDED: the nozzle stays put as the datum (dist 0) and every on-axis part
// separates UPWARD, so nothing drops below the z=0 floor. Radial + vertical
// travels are kept tight so the full turntable stays readable on-screen.
const GROUPS = [
  { key: "nozzle", ref: "#o1.1", label: "Nozzle bell", dir: [0, 0, 1], dist: 0, win: [0.00, 0.28] },
  { key: "chamber", ref: "#o1.2", label: "Combustion chamber", dir: [0, 0, 1], dist: 500, win: [0.08, 0.38] },
  { key: "injector", ref: "#o1.3", label: "Injector head + LOX dome", dir: [0, 0, 1], dist: 1050, win: [0.46, 0.94] },
  { key: "fuel_pump", ref: "#o1.4", label: "Methane turbopump + fuel preburner", dir: [-1, 0, 0], dist: 2000, win: [0.30, 0.70] },
  { key: "ox_pump", ref: "#o1.5", label: "LOX turbopump + oxygen preburner", dir: [1, 0, 0], dist: 2000, win: [0.30, 0.70] },
  { key: "main_ox_valve", ref: "#o1.6", label: "Main oxidizer valve", dir: [0, 0, 1], dist: 1450, win: [0.12, 0.44] },
  { key: "plumbing", ref: "#o1.7", label: "Propellant + hot-gas plumbing", dir: rad(285), dist: 2000, win: [0.18, 0.54] },
  { key: "inlets", ref: "#o1.8", label: "Propellant inlets", dir: [0, 0, 1], dist: 1750, win: [0.05, 0.35] },
  { key: "frame", ref: "#o1.9", label: "Thrust frame + gimbal", dir: [0, 0, 1], dist: 2200, win: [0.00, 0.30] },
  { key: "tvc", ref: "#o1.10", label: "TVC actuators", dir: rad(215), dist: 2250, win: [0.22, 0.58] },
  { key: "avionics", ref: "#o1.11", label: "Engine controller + harness", dir: rad(90), dist: 2100, win: [0.15, 0.50] },
  { key: "sensors", ref: "#o1.12", label: "Sensors + fittings", dir: rad(45), dist: 2250, win: [0.20, 0.56] },
];

const FEATURES = Object.fromEntries(
  GROUPS.map((g) => [g.key, { ref: g.ref, label: g.label }]),
);

const TIMELINES = {
  exploded_reveal: (phase) => ({ exploded: triangle(phase), spin_deg: 360 * clamp01(phase) }),
};

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/raptor3/raptor3.step" },
    label: "Raptor 3 - exploded view",
    description: "Staged exploded reveal of all engine subsystems on a turntable; viewer-time presentation only.",
    units: { length: "mm", angle: "deg", time: "s" },
    features: FEATURES,
    parameters: {
      exploded: {
        type: "number", label: "Exploded view", default: 0,
        min: 0, max: 1, step: 0.005,
        description: "Staged separation of all 12 subsystems (outer frame/nozzle first, injector head last).",
      },
      spin_deg: {
        type: "number", label: "Turntable", default: 0,
        min: 0, max: 360, step: 1, unit: "deg",
        description: "Rotates the whole (exploded) engine about its vertical axis.",
      },
      demo_mode: {
        type: "select", label: "Demo timeline", default: "off",
        description: "Scrub with Demo phase; overrides the manual Exploded / Turntable values.",
        options: [
          { value: "off", label: "Off (manual)" },
          { value: "exploded_reveal", label: "Exploded reveal" },
        ],
      },
      demo_phase: { type: "number", label: "Demo phase", default: 0, min: 0, max: 1, step: 0.004 },
    },
    animations: {
      exploded_reveal: {
        label: "Exploded reveal",
        description: "All engine subsystems burst out in staged waves on a slow turntable, then re-assemble.",
        duration: 14, loop: true,
        update({ progress, set }) {
          set("demo_mode", "off");
          const patch = TIMELINES.exploded_reveal(progress);
          Object.entries(patch).forEach(([k, v]) => set(k, v));
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
    const u = clamp01(params.exploded);
    const spin = finite(params.spin_deg, 0);

    effects.visible("*", true);

    GROUPS.forEach((g) => {
      const amt = smooth(g.win[0], g.win[1], u);
      const d = norm(g.dir);
      const steps = [
        { translate: [d[0] * g.dist * amt, d[1] * g.dist * amt, d[2] * g.dist * amt] },
      ];
      if (spin) {
        // outermost turntable rotation about the engine's vertical axis
        steps.push({ rotate: { axis: [0, 0, 1], origin: [0, 0, 0], angleDeg: spin } });
      }
      effects.transform(g.key, { transforms: steps });
    });
  },
};

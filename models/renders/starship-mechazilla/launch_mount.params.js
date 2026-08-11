// launch_mount.params.js — exploded-view animation sidecar for
// launch_mount.step.py. Viewer-time presentation only (rigid deltas from the
// baked rest pose); geometry lives in the shared helper.
//
// The `exploded` parameter (and the "exploded_reveal" demo timeline driven by
// demo_phase in headless GIF sweeps) separates the pad hardware vertically:
// the clamp table lifts off the legs, the flame deflector rises, the water /
// deluge system drops below, and the booster quick-disconnect slides toward
// the tower side.

const clamp01 = (v) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));

// Per-feature separation travel at exploded = 1 (mm, world axes).
const EXPLODE = {
  olm_legs: [0, 0, 0],
  olm_table: [0, 0, 14000],
  olm_deflector: [0, 0, 6000],
  olm_water: [0, 0, -6000],
  olm_qd: [-9000, 0, 0],
};

const FEATURES = {
  olm_legs: { ref: "#o1.1", label: "Six-leg base" },
  olm_table: { ref: "#o1.2", label: "Clamp table + 20 hold-downs" },
  olm_deflector: { ref: "#o1.3", label: "Water-cooled flame deflector" },
  olm_water: { ref: "#o1.4", label: "Deluge / water supply system" },
  olm_qd: { ref: "#o1.5", label: "Booster quick-disconnect" },
};

const TIMELINES = {
  exploded_reveal: (phase) => ({ exploded: clamp01(phase) }),
};

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/starship-mechazilla/launch_mount.step" },
    label: "Orbital launch mount",
    description: "Exploded pad-hardware reveal; viewer-time presentation only.",
    units: { length: "mm", angle: "deg", time: "s" },
    features: FEATURES,
    parameters: {
      exploded: {
        type: "number", label: "Exploded view", default: 0,
        min: 0, max: 1, step: 0.005,
        description: "Separates legs, clamp table, deflector, water system, and QD.",
      },
      demo_mode: {
        type: "select", label: "Demo timeline", default: "off",
        description: "Scrub with Demo phase; overrides the manual Exploded value.",
        options: [
          { value: "off", label: "Off (manual)" },
          { value: "exploded_reveal", label: "Exploded reveal" },
        ],
      },
      demo_phase: { type: "number", label: "Demo phase", default: 0, min: 0, max: 1, step: 0.005 },
    },
    animations: {
      exploded_reveal: {
        label: "Exploded pad reveal",
        description: "Pad hardware separates vertically to show the mount stack-up.",
        duration: 8, loop: true,
        update({ progress, set }) {
          set("demo_mode", "off");
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
    const mv = (id) => {
      const v = EXPLODE[id] || [0, 0, 0];
      return { translate: [v[0] * e, v[1] * e, v[2] * e] };
    };
    Object.keys(FEATURES).forEach((id) => {
      effects.transform(id, { transforms: [mv(id)] });
    });
  },
};

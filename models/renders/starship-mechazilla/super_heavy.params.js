// super_heavy.params.js — exploded-view animation sidecar for
// super_heavy.step.py. Viewer-time presentation only (rigid deltas from the
// baked rest pose); geometry lives in the shared helper.
//
// The `exploded` parameter (and the "exploded_reveal" demo timeline that the
// headless GIF sweep drives via demo_phase) lifts the hot-stage ring up,
// slides the barrel shell out, fans the four grid fins radially, drops the 33
// engines, and leaves the tank internals (thrust dome, common dome, forward
// dome, CH4 downcomer, engine manifold, slosh baffles) in place to be seen.

const clamp01 = (v) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));

// Grid fin azimuths mirrored from the generator (deg).
const FIN_AZ = [45.0, 135.0, 225.0, 315.0];
const rad = (deg, d) => [
  Math.cos((deg * Math.PI) / 180) * d,
  Math.sin((deg * Math.PI) / 180) * d,
  0,
];

// The shell is a full 9 m cylinder, so it must travel well clear of the 4.5 m
// interior stack (+X ~22 m + a lift) to expose the tank domes; the interior
// tank stack stays put on the axis to be seen.
const EXPLODE = {
  booster_shell: [23000, 0, 5000],
  booster_interior: [0, 0, 0],
  hot_stage_ring: [0, 0, 13000],
  grid_fin_1: rad(FIN_AZ[0], 7500),
  grid_fin_2: rad(FIN_AZ[1], 7500),
  grid_fin_3: rad(FIN_AZ[2], 7500),
  grid_fin_4: rad(FIN_AZ[3], 7500),
  booster_engines: [0, 0, -9000],
};

const joinRefs = (from, to) => {
  const r = [];
  for (let i = from; i <= to; i += 1) r.push(`#o1.${i}`);
  return r.join(",");
};

const FEATURES = {
  booster_shell: { ref: "#o1.1", label: "Booster barrel shell" },
  booster_interior: { ref: "#o1.2", label: "Tank domes + downcomer + manifold" },
  hot_stage_ring: { ref: "#o1.3", label: "Vented hot-stage ring" },
  grid_fin_1: { ref: "#o1.4", label: "Grid fin 1 (az 45)" },
  grid_fin_2: { ref: "#o1.5", label: "Grid fin 2 (az 135)" },
  grid_fin_3: { ref: "#o1.6", label: "Grid fin 3 (az 225)" },
  grid_fin_4: { ref: "#o1.7", label: "Grid fin 4 (az 315)" },
  booster_engines: { ref: joinRefs(8, 40), label: "Raptor engines (33)" },
};

const TIMELINES = {
  exploded_reveal: (phase) => ({ exploded: clamp01(phase) }),
};

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/starship-mechazilla/super_heavy.step" },
    label: "Super Heavy booster",
    description: "Exploded interior reveal; viewer-time presentation only.",
    units: { length: "mm", angle: "deg", time: "s" },
    features: FEATURES,
    parameters: {
      exploded: {
        type: "number", label: "Exploded view", default: 0,
        min: 0, max: 1, step: 0.005,
        description: "Separates shell, hot-stage ring, grid fins, and engines to reveal tank internals.",
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
        label: "Exploded interior reveal",
        description: "Booster separates to expose tank domes, downcomer, and engine manifold.",
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

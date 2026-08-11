// starship.params.js — exploded-view animation sidecar for starship.step.py.
// Viewer-time presentation only (rigid deltas from the baked rest pose);
// geometry lives in the shared helper and requires regeneration to change.
//
// The `exploded` parameter (and the "exploded_reveal" demo timeline, which is
// what the headless GIF sweep drives via demo_phase) lifts the nosecone up,
// slides the barrel and tile shells radially outward, fans the aft flaps out,
// drops the engines down, and leaves the tank internals (thrust dome, common
// dome, forward dome, LOX header tank, transfer tube) in place to be seen.

const clamp01 = (v) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));
const finite = (v, f = 0) => (Number.isFinite(v) ? v : f);

// Ship geometry azimuths mirrored from the generator (deg).
const FLAP_AZ = 116.0;
const rad = (deg, d) => [
  Math.cos((deg * Math.PI) / 180) * d,
  Math.sin((deg * Math.PI) / 180) * d,
  0,
];

// Per-feature separation travel at exploded = 1 (mm, world axes).
// Barrel shell is a full 9 m cylinder; travel it well clear of the 4.5 m
// interior (+X ~14 m) so the tank domes and LOX header tank are exposed.
const EXPLODE = {
  ship_shell: [14000, 0, 0],
  ship_nose: [0, 0, 14000],
  ship_tiles: [21000, 0, 0],
  ship_interior: [0, 0, 0],
  aft_flap_port: rad(FLAP_AZ, 6500),
  aft_flap_starboard: rad(-FLAP_AZ, 6500),
  ship_engines: [0, 0, -9000],
};

const joinRefs = (from, to) => {
  const r = [];
  for (let i = from; i <= to; i += 1) r.push(`#o1.${i}`);
  return r.join(",");
};

const FEATURES = {
  ship_shell: { ref: "#o1.1", label: "Barrel shell + skirt" },
  ship_nose: { ref: "#o1.2", label: "Nosecone + forward flaps" },
  ship_tiles: { ref: "#o1.3", label: "Windward tile shell" },
  ship_interior: { ref: "#o1.4", label: "Tank domes + LOX header tank" },
  aft_flap_port: { ref: "#o1.5", label: "Aft flap (port)" },
  aft_flap_starboard: { ref: "#o1.6", label: "Aft flap (starboard)" },
  ship_engines: { ref: joinRefs(7, 12), label: "Raptor engines (3 SL + 3 vac)" },
};

const TIMELINES = {
  exploded_reveal: (phase) => ({ exploded: clamp01(phase) }),
};

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/starship-mechazilla/starship.step" },
    label: "Starship upper stage",
    description: "Exploded interior reveal; viewer-time presentation only.",
    units: { length: "mm", angle: "deg", time: "s" },
    features: FEATURES,
    parameters: {
      exploded: {
        type: "number", label: "Exploded view", default: 0,
        min: 0, max: 1, step: 0.005,
        description: "Separates shells, flaps, and engines to reveal tank internals.",
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
        description: "Ship separates to expose tank domes, header tank, and transfer tube.",
        duration: 8, loop: true,
        update({ progress, set }) {
          set("demo_mode", "off");
          set("exploded", Math.sin(Math.PI * clamp01(progress)));  // out-and-back, seamless loop
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

// starship_mechazilla.params.js — viewer/animation sidecar declared by
// starship_mechazilla.step.py gen_step(). Viewer-time presentation only: all
// motion is a rigid delta from the baked STEP rest pose (stacked on the OLM);
// geometry changes belong in the generator and require regeneration.
//
// Demo timelines (mirrored by the manifest animations and by headless GIF
// sweeps via demo_mode + demo_phase):
//   booster_catch   — Super Heavy descends vertically onto the tower while
//                     the chopstick arms close to capture it (ship hidden,
//                     QD arm retracted, carriage raised to the catch level).
//   exploded_reveal — the full stack separates axially/radially, lifting the
//                     shells away to reveal internal tank domes, downcomer,
//                     header tank, engines, grid fins, and hot-stage ring.
//
// Mirrored constants below are position contracts with the generator
// (starship_mechazilla.step.py); refresh them if the generator changes.

const clamp01 = (v) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));
const finite = (v, f = 0) => (Number.isFinite(v) ? v : f);
const smooth = (a, b, v) => {
  const t = clamp01((v - a) / (b - a || 1));
  return t * t * (3 - 2 * t);
};

// ---- generator mirrors (mm / deg) -----------------------------------------
const ARM_PIVOT_X = -13700.0;          // ARM_PIVOT_X in the generator
const ARM_PIVOT_Y = 6500.0;            // +Y port arm, -Y starboard arm
const QD_PIVOT = [-15100.0, -3800.0];  // QD_PIVOT_X / QD_PIVOT_Y
const Z_AXIS = [0, 0, 1];

// Catch geometry: arm pads (carriage raised) seat the booster catch pins.
const CATCH_CARRIAGE_DZ = 31000.0;     // carriage 96 m -> 127 m rail level
const CATCH_BOOSTER_DZ = 44410.0;      // pin underside meets raised pad top
const CATCH_APPROACH = 30000.0;        // extra descent height at phase 0
const ARM_OPEN_DEG = 16.0;             // catch-ready arm spread (each arm)
const QD_RETRACT_DEG = 45.0;           // QD arm swung clear during catch

// Exploded-view travel (mm at exploded = 1).
const EXPLODE = {
  ship_group: [0, 0, 20000],
  ship_nose: [0, 0, 12000],
  ship_shell: [9000, 0, 0],
  ship_tiles: [16000, 0, 0],
  ship_engines: [0, 0, -8000],
  booster_group: [0, 0, 8000],
  hot_stage_ring: [0, 0, 6000],
  booster_shell: [12000, 0, 0],
  booster_engines: [0, 0, -4000],
};
const FLAP_AZ_DEG = 116.0;             // aft flap azimuth (per generator)
const FLAP_TRAVEL = 5000.0;
const FIN_AZ_DEG = [45.0, 135.0, 225.0, 315.0];
const FIN_TRAVEL = 4000.0;

const radial = (azDeg, d) => [
  Math.cos((azDeg * Math.PI) / 180) * d,
  Math.sin((azDeg * Math.PI) / 180) * d,
  0,
];

// ---- features: #o refs follow gen_step child order (see build_scene) ------
const joinRefs = (prefix, from, to) => {
  const refs = [];
  for (let i = from; i <= to; i += 1) refs.push(`${prefix}.${i}`);
  return refs.join(",");
};

const FEATURES = {
  tower: { ref: "#o1.1", label: "Launch tower (static)" },
  carriage: { ref: "#o1.2", label: "Chopstick carriage" },
  arm_port: { ref: "#o1.3", label: "Chopstick arm (port, +Y)" },
  arm_starboard: { ref: "#o1.4", label: "Chopstick arm (starboard, -Y)" },
  qd_arm: { ref: "#o1.5", label: "Ship quick-disconnect arm" },
  olm: { ref: "#o1.6", label: "Orbital launch mount (static)" },

  booster: { ref: "#o1.7", label: "Super Heavy booster" },
  booster_shell: { ref: "#o1.7.1", label: "Booster shell" },
  booster_interior: { ref: "#o1.7.2", label: "Booster tank internals" },
  hot_stage_ring: { ref: "#o1.7.3", label: "Hot-stage ring" },
  grid_fin_1: { ref: "#o1.7.4", label: "Grid fin 1 (az 45)" },
  grid_fin_2: { ref: "#o1.7.5", label: "Grid fin 2 (az 135)" },
  grid_fin_3: { ref: "#o1.7.6", label: "Grid fin 3 (az 225)" },
  grid_fin_4: { ref: "#o1.7.7", label: "Grid fin 4 (az 315)" },
  booster_engines: { ref: joinRefs("#o1.7", 8, 40), label: "Booster Raptors (33)" },

  ship: { ref: "#o1.8", label: "Starship upper stage" },
  ship_shell: { ref: "#o1.8.1", label: "Ship barrel shell" },
  ship_nose: { ref: "#o1.8.2", label: "Ship nosecone" },
  ship_tiles: { ref: "#o1.8.3", label: "Ship barrel tile shell" },
  ship_interior: { ref: "#o1.8.4", label: "Ship tank internals" },
  aft_flap_port: { ref: "#o1.8.5", label: "Aft flap (port)" },
  aft_flap_starboard: { ref: "#o1.8.6", label: "Aft flap (starboard)" },
  ship_engines: { ref: joinRefs("#o1.8", 7, 12), label: "Ship Raptors (6)" },
};

// ---- shared demo timelines (viewer animations + headless GIF sweeps) ------
const TIMELINES = {
  booster_catch(phase) {
    const p = clamp01(phase);
    return {
      ship_visible: false,
      qd_retract_deg: QD_RETRACT_DEG,
      carriage_travel_mm: CATCH_CARRIAGE_DZ,
      chopstick_open_deg: ARM_OPEN_DEG * (1 - smooth(0.62, 0.88, p)),
      booster_lift_mm: CATCH_BOOSTER_DZ + CATCH_APPROACH * Math.pow(1 - p, 1.4),
      exploded: 0,
    };
  },
  exploded_reveal(phase) {
    return {
      ship_visible: true,
      qd_retract_deg: 0,
      carriage_travel_mm: 0,
      chopstick_open_deg: 0,
      booster_lift_mm: 0,
      exploded: clamp01(phase),
    };
  },
};

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/starship-mechazilla/starship_mechazilla.step" },
    label: "Starship + Mechazilla launch system",
    description:
      "Viewer-time rig: booster-catch choreography (descent + chopstick closure) " +
      "and an exploded interior reveal. demo_mode overrides manual pose params.",
    units: { length: "mm", angle: "deg", time: "s" },
    features: FEATURES,

    parameters: {
      demo_mode: {
        type: "select",
        label: "Demo timeline",
        default: "off",
        description: "Choreographed pose driven by Demo phase; overrides manual pose parameters.",
        options: [
          { value: "off", label: "Off (manual)" },
          { value: "booster_catch", label: "Booster catch" },
          { value: "exploded_reveal", label: "Exploded reveal" },
        ],
      },
      demo_phase: {
        type: "number", label: "Demo phase", default: 0,
        min: 0, max: 1, step: 0.005,
      },
      chopstick_open_deg: {
        type: "number", label: "Chopstick spread", default: 0,
        min: 0, max: 25, step: 0.25, unit: "deg",
        description: "Each arm yaws open about its carriage pivot (0 = catch/support pose).",
      },
      carriage_travel_mm: {
        type: "number", label: "Carriage travel", default: 0,
        min: -20000, max: 40000, step: 100, unit: "mm",
        description: "Carriage + arms ride the tower rails (delta from stacked level).",
      },
      booster_lift_mm: {
        type: "number", label: "Booster lift", default: 0,
        min: 0, max: 90000, step: 250, unit: "mm",
        description: "Vertical booster offset from the launch mount (catch hang ~44.4 m).",
      },
      qd_retract_deg: {
        type: "number", label: "QD arm retract", default: 0,
        min: 0, max: 60, step: 0.5, unit: "deg",
      },
      exploded: {
        type: "number", label: "Exploded view", default: 0,
        min: 0, max: 1, step: 0.005,
        description: "Separates shells, stages, fins, and engines to reveal tank internals.",
      },
      ship_visible: { type: "boolean", label: "Show Starship", default: true },
    },

    // Order matters: the viewer selects the FIRST animation by default, so
    // the exploded interior reveal leads and the booster catch is second.
    animations: {
      exploded_reveal: {
        label: "Exploded interior reveal",
        description: "Stack separates to expose tank domes, downcomer, header tank, and engines.",
        duration: 9,
        loop: true,
        update({ progress, set }) {
          set("demo_mode", "off");
          // sine out-and-back so the loop closes exactly
          const patch = TIMELINES.exploded_reveal(Math.sin(Math.PI * clamp01(progress)));
          Object.entries(patch).forEach(([k, v]) => set(k, v));
        },
      },
      booster_catch: {
        label: "Booster catch",
        description: "Super Heavy descends onto the tower; chopsticks close to capture.",
        duration: 12,
        loop: true,
        update({ progress, set }) {
          set("demo_mode", "off");
          const patch = TIMELINES.booster_catch(progress >= 1 ? 0 : progress);
          Object.entries(patch).forEach(([k, v]) => set(k, v));
        },
      },
    },
  },

  update({ params: rawParams, effects }) {
    let params = rawParams;
    const demoMode = String(rawParams.demo_mode || "off");
    if (demoMode !== "off" && TIMELINES[demoMode]) {
      params = { ...rawParams, ...TIMELINES[demoMode](clamp01(rawParams.demo_phase)) };
    }

    effects.visible("*", true);
    if (params.ship_visible === false) effects.visible("ship", false);

    const openDeg = finite(params.chopstick_open_deg, 0);
    const carriageDz = finite(params.carriage_travel_mm, 0);
    const boosterDz = Math.max(0, finite(params.booster_lift_mm, 0));
    const qdDeg = finite(params.qd_retract_deg, 0);
    const e = clamp01(params.exploded);

    const mv = (vec, k) => ({ translate: [vec[0] * k, vec[1] * k, vec[2] * k] });
    const armRot = (sy, deg) => ({
      rotate: { axis: Z_AXIS, origin: [ARM_PIVOT_X, sy * ARM_PIVOT_Y, 0], angleDeg: sy * deg },
    });

    // Sub-feature steps FIRST (innermost), then whole-group steps: repeated
    // transforms on the same leaves premultiply (first call closest to part).

    // -- ship internals/shells (exploded view) --
    effects.transform("ship_shell", { transforms: [mv(EXPLODE.ship_shell, e)] });
    effects.transform("ship_nose", { transforms: [mv(EXPLODE.ship_nose, e)] });
    effects.transform("ship_tiles", { transforms: [mv(EXPLODE.ship_tiles, e)] });
    effects.transform("ship_interior", { transforms: [] });
    effects.transform("aft_flap_port", { transforms: [mv(radial(FLAP_AZ_DEG, FLAP_TRAVEL), e)] });
    effects.transform("aft_flap_starboard", { transforms: [mv(radial(-FLAP_AZ_DEG, FLAP_TRAVEL), e)] });
    effects.transform("ship_engines", { transforms: [mv(EXPLODE.ship_engines, e)] });
    // whole ship group (stack separation rides on top of the sub-steps)
    effects.transform("ship", { transforms: [mv(EXPLODE.ship_group, e)] });

    // -- booster internals/shells --
    effects.transform("booster_shell", { transforms: [mv(EXPLODE.booster_shell, e)] });
    effects.transform("booster_interior", { transforms: [] });
    effects.transform("hot_stage_ring", { transforms: [mv(EXPLODE.hot_stage_ring, e)] });
    FIN_AZ_DEG.forEach((az, i) => {
      effects.transform(`grid_fin_${i + 1}`, { transforms: [mv(radial(az, FIN_TRAVEL), e)] });
    });
    effects.transform("booster_engines", { transforms: [mv(EXPLODE.booster_engines, e)] });
    // whole booster group: exploded stage separation + catch descent lift
    effects.transform("booster", {
      transforms: [mv(EXPLODE.booster_group, e), { translate: [0, 0, boosterDz] }],
    });

    // -- tower mechanisms --
    effects.transform("carriage", { transforms: [{ translate: [0, 0, carriageDz] }] });
    effects.transform("arm_port", {
      transforms: [armRot(1, openDeg), { translate: [0, 0, carriageDz] }],
    });
    effects.transform("arm_starboard", {
      transforms: [armRot(-1, openDeg), { translate: [0, 0, carriageDz] }],
    });
    effects.transform("qd_arm", {
      transforms: [{ rotate: { axis: Z_AXIS, origin: [QD_PIVOT[0], QD_PIVOT[1], 0], angleDeg: -qdDeg } }],
    });

    // -- statics (touched every frame so effect state fully rebuilds) --
    effects.transform("tower", { transforms: [] });
    effects.transform("olm", { transforms: [] });
  },
};

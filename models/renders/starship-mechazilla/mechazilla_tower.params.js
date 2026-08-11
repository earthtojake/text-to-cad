// mechazilla_tower.params.js — chopstick catch/close animation sidecar for
// mechazilla_tower.step.py. Viewer-time presentation only (rigid deltas from
// the baked rest pose); geometry lives in the shared helper.
//
// The "chopstick_catch" demo timeline (driven by demo_phase in headless GIF
// sweeps) starts with the arms swung WIDE OPEN (catch-ready) and the QD arm
// retracted clear, then closes the arms about their carriage pivots to the
// capture pose. Manual params expose the arm spread, carriage travel, and QD
// retraction independently.

const clamp01 = (v) => Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));
const finite = (v, f = 0) => (Number.isFinite(v) ? v : f);
const smooth = (a, b, v) => {
  const t = clamp01((v - a) / (b - a || 1));
  return t * t * (3 - 2 * t);
};

// Pivot constants mirrored from the generator (world mm).
const ARM_PIVOT_X = -13700.0;   // TOWER_CX + TOWER_HALF + 2300
const ARM_PIVOT_Y = 6500.0;     // +Y port arm, -Y starboard arm
const QD_PIVOT = [-15100.0, -3800.0];  // TOWER_CX + TOWER_HALF + 900, -3800
const Z_AXIS = [0, 0, 1];

const ARM_OPEN_DEG = 18.0;      // catch-ready spread per arm
const QD_RETRACT_DEG = 45.0;

const FEATURES = {
  tower: { ref: "#o1.1", label: "Launch tower (static)" },
  carriage: { ref: "#o1.2", label: "Chopstick carriage" },
  arm_port: { ref: "#o1.3", label: "Chopstick arm (port, +Y)" },
  arm_starboard: { ref: "#o1.4", label: "Chopstick arm (starboard, -Y)" },
  qd_arm: { ref: "#o1.5", label: "Ship quick-disconnect arm" },
};

const TIMELINES = {
  // phase 0 = arms wide open + QD clear; phase 1 = arms closed (captured).
  chopstick_catch(phase) {
    const p = clamp01(phase);
    return {
      chopstick_open_deg: ARM_OPEN_DEG * (1 - smooth(0.15, 0.9, p)),
      qd_retract_deg: QD_RETRACT_DEG * (1 - smooth(0.8, 1.0, p)),
      carriage_travel_mm: 0,
    };
  },
};

export default {
  manifest: {
    schemaVersion: 1,
    step: { path: "models/renders/starship-mechazilla/mechazilla_tower.step" },
    label: "Mechazilla launch tower",
    description: "Chopstick catch/close animation; viewer-time presentation only.",
    units: { length: "mm", angle: "deg", time: "s" },
    features: FEATURES,
    parameters: {
      chopstick_open_deg: {
        type: "number", label: "Chopstick spread", default: 0,
        min: 0, max: 25, step: 0.25, unit: "deg",
        description: "Each arm yaws open about its carriage pivot (0 = closed capture pose).",
      },
      carriage_travel_mm: {
        type: "number", label: "Carriage travel", default: 0,
        min: -30000, max: 40000, step: 100, unit: "mm",
        description: "Carriage + arms ride the tower rails (delta from stacked level).",
      },
      qd_retract_deg: {
        type: "number", label: "QD arm retract", default: 0,
        min: 0, max: 60, step: 0.5, unit: "deg",
      },
      demo_mode: {
        type: "select", label: "Demo timeline", default: "off",
        description: "Scrub with Demo phase; overrides the manual pose parameters.",
        options: [
          { value: "off", label: "Off (manual)" },
          { value: "chopstick_catch", label: "Chopstick catch" },
        ],
      },
      demo_phase: { type: "number", label: "Demo phase", default: 0, min: 0, max: 1, step: 0.005 },
    },
    animations: {
      chopstick_catch: {
        label: "Chopstick catch",
        description: "Arms swing from wide open to closed capture; QD arm retracts.",
        duration: 9, loop: true,
        update({ progress, set }) {
          set("demo_mode", "off");
          const patch = TIMELINES.chopstick_catch(progress >= 1 ? 0 : progress);
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

    effects.visible("*", true);

    const openDeg = finite(params.chopstick_open_deg, 0);
    const carriageDz = finite(params.carriage_travel_mm, 0);
    const qdDeg = finite(params.qd_retract_deg, 0);

    const armRot = (sy, deg) => ({
      rotate: { axis: Z_AXIS, origin: [ARM_PIVOT_X, sy * ARM_PIVOT_Y, 0], angleDeg: sy * deg },
    });

    effects.transform("tower", { transforms: [] });
    effects.transform("carriage", { transforms: [{ translate: [0, 0, carriageDz] }] });
    // arm's own hinge yaw first (innermost), then the carriage rail travel
    effects.transform("arm_port", {
      transforms: [armRot(1, openDeg), { translate: [0, 0, carriageDz] }],
    });
    effects.transform("arm_starboard", {
      transforms: [armRot(-1, openDeg), { translate: [0, 0, carriageDz] }],
    });
    effects.transform("qd_arm", {
      transforms: [{ rotate: { axis: Z_AXIS, origin: [QD_PIVOT[0], QD_PIVOT[1], 0], angleDeg: -qdDeg } }],
    });
  },
};

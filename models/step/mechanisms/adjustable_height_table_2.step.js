const X_AXIS = [1, 0, 0];

const BOTTOM_FIXED_PIVOT = [14.610456, -171.775187, 23.0];
const TOP_FIXED_PIVOT_INITIAL = [14.610456, -171.775187, 69.00033];
const ROLLER_PIVOT_INITIAL = [14.610456, 124.677119, 69.00033];
const LOWER_ROLLER_CENTER_INITIAL = [14.610456, 124.677119, 23.0];
const UPPER_ROLLER_CENTER_INITIAL = [14.610456, 124.677119, 69.00033];
const ACTUATOR_PIVOT_INITIAL = [14.610456, -142.775187, 27.499913];

const INITIAL_HEIGHT = TOP_FIXED_PIVOT_INITIAL[2] - BOTTOM_FIXED_PIVOT[2];
const INITIAL_RUN = ROLLER_PIVOT_INITIAL[1] - BOTTOM_FIXED_PIVOT[1];
const LINK_LENGTH = Math.hypot(INITIAL_RUN, INITIAL_HEIGHT);
const INITIAL_LINK_ANGLE_DEG = angleDeg(INITIAL_HEIGHT, INITIAL_RUN);
const ACTUATOR_Y_OFFSET = ACTUATOR_PIVOT_INITIAL[1] - BOTTOM_FIXED_PIVOT[1];
const ROLLER_RADIUS = 20.0;
const RUNWAY_MIN_Y = -2.775187;
const RUNWAY_END_CLEARANCE = 12.0;
const MAX_RAISED_HEIGHT = maxSafeRaisedHeight();
const DEFAULT_RAISED_HEIGHT = 215;

const TOP_ASSEMBLY = ["topAssembly"];
const RISING_LINKAGE = ["risingLinkage"];
const DESCENDING_LINKAGE = ["descendingLinkage"];
const LOWER_ROLLERS = ["lowerRollers"];
const UPPER_ROLLERS = ["upperRollers"];
const ACTUATOR_ROD = ["piston", "actuatorCrossShaft"];
const ACTUATOR_SLIDER = ["actuatorSlider"];
const MOVING_PARTS = [
  ...TOP_ASSEMBLY,
  ...RISING_LINKAGE,
  ...DESCENDING_LINKAGE,
  ...LOWER_ROLLERS,
  ...UPPER_ROLLERS,
  ...ACTUATOR_ROD,
  ...ACTUATOR_SLIDER
];

function finite(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(finite(value, min), min), max);
}

function clamp01(value) {
  return clamp(value, 0, 1);
}

function smooth01(value) {
  const t = clamp01(value);
  return t * t * (3 - (2 * t));
}

function lerp(start, end, t) {
  return start + ((end - start) * t);
}

function angleDeg(height, run) {
  return Math.atan2(height, run) * 180 / Math.PI;
}

function maxSafeRaisedHeight() {
  const minRollerCenterY = RUNWAY_MIN_Y + ROLLER_RADIUS + RUNWAY_END_CLEARANCE;
  const minRun = minRollerCenterY - BOTTOM_FIXED_PIVOT[1];
  return Math.sqrt(Math.max(0, (LINK_LENGTH * LINK_LENGTH) - (minRun * minRun)));
}

function cycleLift(cycle) {
  const phase = ((finite(cycle, 0) % 1) + 1) % 1;
  if (phase < 0.42) {
    return smooth01(phase / 0.42);
  }
  if (phase < 0.52) {
    return 1;
  }
  if (phase < 0.94) {
    return 1 - smooth01((phase - 0.52) / 0.42);
  }
  return 0;
}

function sampleLift(rawLift, rawRaisedHeight) {
  const lift = smooth01(rawLift);
  const raisedHeight = clamp(rawRaisedHeight, INITIAL_HEIGHT + 5, MAX_RAISED_HEIGHT);
  const height = lerp(INITIAL_HEIGHT, raisedHeight, lift);
  const run = Math.sqrt(Math.max(1e-6, (LINK_LENGTH * LINK_LENGTH) - (height * height)));
  const angle = angleDeg(height, run);
  const rollerY = BOTTOM_FIXED_PIVOT[1] + run;
  const heightDelta = height - INITIAL_HEIGHT;
  const rollerYDelta = rollerY - ROLLER_PIVOT_INITIAL[1];

  // The reference video shows the actuator rising vertically while a green
  // slider follows the lower blue link. Solve that slider by intersecting the
  // lower link with the fixed actuator centerline.
  const actuatorRatio = clamp(ACTUATOR_Y_OFFSET / run, 0, 1);
  const actuatorZ = BOTTOM_FIXED_PIVOT[2] + (height * actuatorRatio);
  const actuatorZDelta = actuatorZ - ACTUATOR_PIVOT_INITIAL[2];
  return {
    angle,
    heightDelta,
    rollerYDelta,
    actuatorZDelta,
    risingAngleDelta: angle - INITIAL_LINK_ANGLE_DEG,
    descendingAngleDelta: -(angle - INITIAL_LINK_ANGLE_DEG),
    wheelSpinDeg: -(rollerYDelta / (2 * Math.PI * ROLLER_RADIUS)) * 360
  };
}

function applyVisibility(effects, params) {
  effects.visible("*", true);
  effects.visible("actuator", params.showActuator !== false);
  effects.visible("hardware", params.showHardware !== false);
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/step/mechanisms/adjustable_height_table_2.step"
    },
    label: "Adjustable height table 2",
    description: "Viewer-time scissor-lift animation matched to the reference video: the top stays level, right pivots roll in the runways, and the vertical actuator drives the lower-link slider.",
    units: {
      length: "mm",
      angle: "deg",
      time: "s"
    },
    features: {
      baseAssembly: { ref: "#o1.1", label: "Base assembly" },
      basePlate: { ref: "#o1.1.1", label: "Base plate" },
      baseBearings: { ref: "#o1.1.2,o1.1.3", label: "Base fixed bearings" },
      baseRunways: { ref: "#o1.1.9,o1.1.10", label: "Base roller runways" },
      cylinder: { ref: "#o1.1.8", label: "Fixed cylinder" },

      topAssembly: { ref: "#o1.2", label: "Moving table top" },
      topPlate: { ref: "#o1.2.1", label: "Table top" },
      topBearings: { ref: "#o1.2.2,o1.2.3", label: "Top fixed bearings" },
      topRunways: { ref: "#o1.2.8,o1.2.9", label: "Top roller runways" },

      risingLinkage: { ref: "#o1.3", label: "Rising scissor links", description: "Links from the lower fixed pivots to the upper rolling pivots." },
      descendingLinkage: { ref: "#o1.4", label: "Descending scissor links", description: "Links from the upper fixed pivots to the lower rolling pivots." },
      centralPivot: { ref: "#o1.3.3,o1.3.4,o1.3.5", label: "Central scissor pivot" },
      upperRollerShafts: { ref: "#o1.3.6,o1.3.7,o1.3.8,o1.3.9,o1.3.10,o1.3.11", label: "Upper roller shafts" },
      lowerRollerShafts: { ref: "#o1.4.3,o1.4.4,o1.4.5,o1.4.6,o1.4.7,o1.4.8", label: "Lower roller shafts" },
      upperRollers: { ref: "#o1.8,o1.9", label: "Upper pink rollers" },
      lowerRollers: { ref: "#o1.6,o1.7", label: "Lower pink rollers" },

      piston: { ref: "#o1.5", label: "Piston rod" },
      actuatorSlider: { ref: "#o1.10", label: "Green actuator slider" },
      actuatorCrossShaft: { ref: "#o1.11", label: "Actuator cross shaft" },
      actuator: { ref: "#o1.1.8,o1.5,o1.10,o1.11", label: "Hydraulic actuator" },
      hardware: {
        ref: "#o1.1.4,o1.1.5,o1.1.6,o1.1.7,o1.2.4,o1.2.5,o1.2.6,o1.2.7,o1.3.4,o1.3.5,o1.3.7,o1.3.9,o1.3.10,o1.3.11,o1.4.4,o1.4.5,o1.4.7,o1.4.8",
        label: "Nuts and bolts"
      }
    },
    parameters: {
      lift: { type: "number", label: "Lift", description: "Collapsed to raised scissor-lift travel.", default: 0, min: 0, max: 1, step: 0.01 },
      raisedHeightMm: { type: "number", label: "Raised height", description: "Upper fixed-pivot height above the base fixed pivots at full lift; clamped so rollers stay inside the runways.", default: DEFAULT_RAISED_HEIGHT, min: 80, max: MAX_RAISED_HEIGHT, step: 1, unit: "mm" },
      explode: { type: "number", label: "Explode", description: "Separates the motion groups for inspection after the linkage pose is applied.", default: 0, min: 0, max: 1, step: 0.01 },
      showActuator: { type: "boolean", label: "Actuator", default: true },
      showHardware: { type: "boolean", label: "Hardware", default: true },
      highlightMoving: { type: "boolean", label: "Highlight moving parts", default: false }
    },
    animations: {
      liftLoop: {
        label: "Reference lift loop",
        description: "Low table, hydraulic lift to raised position, brief dwell, and return.",
        duration: 8,
        loop: true,
        update({ cycle, set }) {
          set("lift", cycleLift(cycle));
        }
      },
      inspectExplode: {
        label: "Lift with exploded groups",
        duration: 8,
        loop: true,
        update({ cycle, set }) {
          const lift = cycleLift(cycle);
          set("lift", lift);
          set("explode", Math.sin(lift * Math.PI));
        }
      }
    }
  },

  update({ params, effects }) {
    const pose = sampleLift(params.lift, params.raisedHeightMm);
    const explode = clamp01(params.explode);

    applyVisibility(effects, params);

    effects.style("basePlate", { opacity: 1, edgeOpacity: 0.8 });
    effects.style(["baseBearings", "topBearings"], { opacity: 1, edgeOpacity: 0.8 });
    effects.style(["baseRunways", "topRunways"], { opacity: 1, edgeOpacity: 0.9 });
    effects.style("topPlate", { opacity: 1, edgeOpacity: 0.85 });
    effects.style("risingLinkage", { opacity: 1, edgeOpacity: 1 });
    effects.style("descendingLinkage", { opacity: 1, edgeOpacity: 1 });
    effects.style("centralPivot", { opacity: 1, edgeOpacity: 1 });
    effects.style(["lowerRollerShafts", "upperRollerShafts", "actuatorCrossShaft"], { opacity: 1, edgeOpacity: 0.9 });
    effects.style(["lowerRollers", "upperRollers"], { opacity: 1, edgeOpacity: 1 });
    effects.style("cylinder", { opacity: 1, edgeOpacity: 1 });
    effects.style("piston", { opacity: 1, edgeOpacity: 1 });
    effects.style("actuatorSlider", { opacity: 1, edgeOpacity: 1 });
    effects.style("hardware", { opacity: 1, edgeOpacity: 0.7 });

    if (params.highlightMoving !== false) {
      effects.highlight(MOVING_PARTS, true);
    }

    effects.transform("topAssembly", {
      translate: [0, explode * -10, pose.heightDelta + (explode * 22)]
    });

    effects.transform("risingLinkage", {
      transforms: [
        {
          rotate: {
            axis: X_AXIS,
            origin: BOTTOM_FIXED_PIVOT,
            angleDeg: pose.risingAngleDelta
          }
        },
        { translate: [explode * 12, explode * -8, explode * 12] }
      ]
    });

    effects.transform("descendingLinkage", {
      transforms: [
        {
          rotate: {
            axis: X_AXIS,
            origin: TOP_FIXED_PIVOT_INITIAL,
            angleDeg: pose.descendingAngleDelta
          }
        },
        { translate: [explode * -12, explode * 8, pose.heightDelta + (explode * 12)] }
      ]
    });

    effects.transform("lowerRollers", {
      transforms: [
        {
          rotate: {
            axis: X_AXIS,
            origin: LOWER_ROLLER_CENTER_INITIAL,
            angleDeg: pose.wheelSpinDeg
          }
        },
        { translate: [0, pose.rollerYDelta + (explode * 10), explode * 8] }
      ]
    });

    effects.transform("upperRollers", {
      transforms: [
        {
          rotate: {
            axis: X_AXIS,
            origin: UPPER_ROLLER_CENTER_INITIAL,
            angleDeg: pose.wheelSpinDeg
          }
        },
        { translate: [0, pose.rollerYDelta + (explode * -10), pose.heightDelta + (explode * 18)] }
      ]
    });

    effects.transform(ACTUATOR_ROD, {
      translate: [0, 0, pose.actuatorZDelta + (explode * 10)]
    });

    effects.transform("actuatorSlider", {
      transforms: [
        {
          rotate: {
            axis: X_AXIS,
            origin: ACTUATOR_PIVOT_INITIAL,
            angleDeg: pose.risingAngleDelta
          }
        },
        { translate: [0, 0, pose.actuatorZDelta + (explode * 14)] }
      ]
    });
  }
};

const Z_AXIS = [0, 0, 1];

const GEAR_PITCH_RADIUS_MM = 20;
const MAX_GEAR_ANGLE_DEG = 82;

const LEFT_GEAR_CENTER = [-40, 0, 14.000004];
const RIGHT_GEAR_CENTER = [40, 0, 14.000004];
const LEFT_CRANK_PIN_INITIAL = [-40, -15, 14.000004];
const RIGHT_CRANK_PIN_INITIAL = [40, -15, 14.000004];
const LEFT_PISTON_PIN_INITIAL = [-20, -10, 14.000004];
const RIGHT_PISTON_PIN_INITIAL = [20, -10, 14.000004];

const LINK_LENGTH_MM = distance2(LEFT_PISTON_PIN_INITIAL, LEFT_CRANK_PIN_INITIAL);
const INITIAL_LEFT_LINK_ANGLE_DEG = angleDeg2(LEFT_PISTON_PIN_INITIAL, LEFT_CRANK_PIN_INITIAL);
const INITIAL_RIGHT_LINK_ANGLE_DEG = angleDeg2(RIGHT_PISTON_PIN_INITIAL, RIGHT_CRANK_PIN_INITIAL);

const MOVING_FEATURES = [
  "piston",
  "leftConrod",
  "rightConrod",
  "leftPinion",
  "rightPinion",
  "leftRack",
  "rightRack"
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

function distance2(start, end) {
  return Math.hypot(end[0] - start[0], end[1] - start[1]);
}

function angleDeg2(start, end) {
  return Math.atan2(end[1] - start[1], end[0] - start[0]) * 180 / Math.PI;
}

function rotatePointZ(point, origin, angleDeg) {
  const angleRad = angleDeg * Math.PI / 180;
  const cosA = Math.cos(angleRad);
  const sinA = Math.sin(angleRad);
  const dx = point[0] - origin[0];
  const dy = point[1] - origin[1];
  return [
    origin[0] + (dx * cosA) - (dy * sinA),
    origin[1] + (dx * sinA) + (dy * cosA),
    point[2]
  ];
}

function normalizeAngleDeg(value) {
  let angle = finite(value, 0);
  while (angle > 180) angle -= 360;
  while (angle < -180) angle += 360;
  return angle;
}

function solvePistonY(leftCrankPin) {
  const dx = LEFT_PISTON_PIN_INITIAL[0] - leftCrankPin[0];
  const allowedDx = clamp(dx, -LINK_LENGTH_MM + 1e-6, LINK_LENGTH_MM - 1e-6);
  const dy = Math.sqrt(Math.max(1e-6, (LINK_LENGTH_MM * LINK_LENGTH_MM) - (allowedDx * allowedDx)));

  // The uploaded STEP starts with the piston pin slightly ahead of the crank
  // pin. Keep that same branch so the conrod never flips through the gear.
  return leftCrankPin[1] + dy;
}

function samplePose(rawStroke) {
  const stroke = smooth01(rawStroke);
  const leftGearAngleDeg = stroke * MAX_GEAR_ANGLE_DEG;
  const rightGearAngleDeg = -leftGearAngleDeg;
  const rackTravelMm = (leftGearAngleDeg * Math.PI / 180) * GEAR_PITCH_RADIUS_MM;

  const leftCrankPin = rotatePointZ(LEFT_CRANK_PIN_INITIAL, LEFT_GEAR_CENTER, leftGearAngleDeg);
  const rightCrankPin = rotatePointZ(RIGHT_CRANK_PIN_INITIAL, RIGHT_GEAR_CENTER, rightGearAngleDeg);
  const pistonY = solvePistonY(leftCrankPin);
  const pistonDeltaY = pistonY - LEFT_PISTON_PIN_INITIAL[1];

  const leftPistonPin = [LEFT_PISTON_PIN_INITIAL[0], pistonY, LEFT_PISTON_PIN_INITIAL[2]];
  const rightPistonPin = [RIGHT_PISTON_PIN_INITIAL[0], pistonY, RIGHT_PISTON_PIN_INITIAL[2]];

  return {
    stroke,
    pistonDeltaY,
    rackTravelMm,
    leftGearAngleDeg,
    rightGearAngleDeg,
    leftLinkAngleDeltaDeg: normalizeAngleDeg(angleDeg2(leftPistonPin, leftCrankPin) - INITIAL_LEFT_LINK_ANGLE_DEG),
    rightLinkAngleDeltaDeg: normalizeAngleDeg(angleDeg2(rightPistonPin, rightCrankPin) - INITIAL_RIGHT_LINK_ANGLE_DEG)
  };
}

function cycleStroke(cycle) {
  const phase = ((finite(cycle, 0) % 1) + 1) % 1;
  if (phase < 0.38) {
    return smooth01(phase / 0.38);
  }
  if (phase < 0.50) {
    return 1;
  }
  if (phase < 0.88) {
    return 1 - smooth01((phase - 0.50) / 0.38);
  }
  return 0;
}

function applyVisibility(effects, params) {
  effects.visible("*", true);
  effects.visible("hardware", params.showHardware !== false);
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/step/mechanisms/gear_rack_gripper.step"
    },
    label: "Robot gripper gear-rack assembly",
    description: "Uploaded STEP assembly with viewer-time animation based on the reference video: a sliding piston drives two blue conrods, counter-rotating pinions, and opposing rack jaws.",
    units: {
      length: "mm",
      angle: "deg",
      time: "s"
    },
    features: {
      base: { ref: "#o1.1.10", label: "Fixed base plate" },
      cylinder: { ref: "#o1.1.9", label: "Fixed green cylinder" },
      piston: { ref: "#o1.1.17", label: "Sliding piston rod" },
      leftRack: { ref: "#o1.1.11", label: "Left moving rack jaw" },
      rightRack: { ref: "#o1.1.12", label: "Right moving rack jaw" },
      leftPinion: {
        ref: "#o1.1.13",
        label: "Left yellow pinion and crank",
        origin: LEFT_GEAR_CENTER,
        axis: Z_AXIS
      },
      rightPinion: {
        ref: "#o1.1.14",
        label: "Right yellow pinion and crank",
        origin: RIGHT_GEAR_CENTER,
        axis: Z_AXIS
      },
      leftConrod: { ref: "#o1.1.15", label: "Left blue connecting rod" },
      rightConrod: { ref: "#o1.1.16", label: "Right blue connecting rod" },
      hardware: {
        ref: "#o1.1.1,#o1.1.2,#o1.1.3,#o1.1.4,#o1.1.5,#o1.1.6,#o1.1.7,#o1.1.8",
        label: "Fixed bolts and pins"
      },
      movingAssembly: {
        ref: "#o1.1.11,#o1.1.12,#o1.1.13,#o1.1.14,#o1.1.15,#o1.1.16,#o1.1.17",
        label: "Moving drive train"
      }
    },
    parameters: {
      stroke: {
        type: "number",
        label: "Stroke",
        description: "0 is the imported closed pose; 1 pushes the piston forward and opens the two rack jaws with the pinion pitch relationship preserved.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.01
      },
      explode: {
        type: "number",
        label: "Explode",
        description: "Separates the moving groups after the solved pose for mechanism inspection.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.01
      },
      showHardware: { type: "boolean", label: "Hardware", default: true },
      highlightMoving: { type: "boolean", label: "Highlight moving", default: false }
    },
    animations: {
      driveLoop: {
        label: "Piston rack drive",
        description: "Closed pose, piston-driven rack opening, short dwell, then return.",
        duration: 6,
        loop: true,
        update({ cycle, set }) {
          set("stroke", cycleStroke(cycle));
        }
      },
      inspectDrive: {
        label: "Exploded drive inspection",
        duration: 6,
        loop: true,
        update({ cycle, set }) {
          const stroke = cycleStroke(cycle);
          set("stroke", stroke);
          set("explode", Math.sin(stroke * Math.PI));
        }
      }
    }
  },

  update({ params, effects }) {
    const pose = samplePose(params.stroke);
    const explode = clamp01(params.explode);

    applyVisibility(effects, params);

    if (params.highlightMoving === true) {
      effects.highlight(MOVING_FEATURES, true);
    }

    effects.transform("piston", {
      translate: [0, pose.pistonDeltaY, explode * 12]
    });

    effects.transform("leftConrod", {
      transforms: [
        {
          rotate: {
            axis: Z_AXIS,
            origin: LEFT_PISTON_PIN_INITIAL,
            angleDeg: pose.leftLinkAngleDeltaDeg
          }
        },
        { translate: [0, pose.pistonDeltaY, explode * 16] }
      ]
    });

    effects.transform("rightConrod", {
      transforms: [
        {
          rotate: {
            axis: Z_AXIS,
            origin: RIGHT_PISTON_PIN_INITIAL,
            angleDeg: pose.rightLinkAngleDeltaDeg
          }
        },
        { translate: [0, pose.pistonDeltaY, explode * 16] }
      ]
    });

    effects.transform("leftPinion", {
      transforms: [
        {
          rotate: {
            axis: Z_AXIS,
            origin: LEFT_GEAR_CENTER,
            angleDeg: pose.leftGearAngleDeg
          }
        },
        { translate: [-explode * 8, -explode * 5, explode * 18] }
      ]
    });

    effects.transform("rightPinion", {
      transforms: [
        {
          rotate: {
            axis: Z_AXIS,
            origin: RIGHT_GEAR_CENTER,
            angleDeg: pose.rightGearAngleDeg
          }
        },
        { translate: [explode * 8, -explode * 5, explode * 18] }
      ]
    });

    effects.transform("leftRack", {
      translate: [-pose.rackTravelMm - (explode * 14), 0, explode * 8]
    });

    effects.transform("rightRack", {
      translate: [pose.rackTravelMm + (explode * 14), 0, explode * 8]
    });
  }
};

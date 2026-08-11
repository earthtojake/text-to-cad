const Z_AXIS = [0, 0, 1];
const FLAT_ON_GROUND_TRANSFORM = [
  0, 0, -1, 0,
  0, 1, 0, 0,
  1, 0, 0, -322.461928,
  0, 0, 0, 1
];

// CAD coordinates measured from the STEP occurrence bounds. The side-view
// mechanism is a toggle four-bar: the lower pink rocker drives the yellow/red
// panel coupler out to an over-center tangent pose, then the coupler returns on
// the opposite branch with the panel flipped.
const PIVOTS = {
  upperFrame: [-15.002, 229.609, 0],
  lowerFrame: [104.981, 29.599, 0],
  lowerBoard: [45.03, 229.61, 0],
  upperBoard: [44.984, 420.401, 0]
};

const PANEL_COUPLER_PARTS = ["panel", "redLink", "driveRod", "hingeRod", "panelHardware"];
const LOWER_ROCKER_PARTS = ["rocker2", "greenRod", "handleHardware"];
const FRAME_DETAIL_PARTS = ["stopper", "bearings"];
const FRAME_PARTS = ["frame", ...FRAME_DETAIL_PARTS, "frameHardware"];
const HARDWARE = ["frameHardware", "handleHardware", "panelHardware"];
const CROSS_RODS = ["hingeRod", "driveRod"];
const MOVING_PARTS = ["rockerBlue", ...PANEL_COUPLER_PARTS, ...LOWER_ROCKER_PARTS];

const INITIAL_PANEL_ANGLE_DEG = angleDeg2(PIVOTS.lowerBoard, PIVOTS.upperBoard);
const INITIAL_BLUE_ANGLE_DEG = angleDeg2(PIVOTS.upperFrame, PIVOTS.upperBoard);
const INITIAL_LOWER_ROCKER_ANGLE_DEG = angleDeg2(PIVOTS.lowerFrame, PIVOTS.lowerBoard);
const LOWER_LINK_LENGTH = distance2(PIVOTS.lowerFrame, PIVOTS.lowerBoard);
const UPPER_LINK_LENGTH = distance2(PIVOTS.upperFrame, PIVOTS.upperBoard);
const COUPLER_LINK_LENGTH = distance2(PIVOTS.lowerBoard, PIVOTS.upperBoard);
const OVER_CENTER_CRANK_ANGLE_DEG = -3.22068;

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

function lerpPoint(start, end, t) {
  return [
    lerp(start[0], end[0], t),
    lerp(start[1], end[1], t),
    lerp(start[2] || 0, end[2] || 0, t)
  ];
}

function distance2(start, end) {
  return Math.hypot(end[0] - start[0], end[1] - start[1]);
}

function angleDeg2(start, end) {
  return Math.atan2(end[1] - start[1], end[0] - start[0]) * 180 / Math.PI;
}

function pointFromAngle(origin, length, angleDeg) {
  const angleRad = angleDeg * Math.PI / 180;
  return [
    origin[0] + (Math.cos(angleRad) * length),
    origin[1] + (Math.sin(angleRad) * length),
    origin[2] || 0
  ];
}

function circleIntersections(centerA, radiusA, centerB, radiusB) {
  const dx = centerB[0] - centerA[0];
  const dy = centerB[1] - centerA[1];
  const distance = Math.hypot(dx, dy);
  if (distance <= 1e-6) {
    return [centerA, centerA];
  }
  const maxDistance = radiusA + radiusB;
  const minDistance = Math.abs(radiusA - radiusB);
  const solvedDistance = clamp(distance, minDistance + 1e-6, maxDistance - 1e-6);
  const along = ((radiusA * radiusA) - (radiusB * radiusB) + (solvedDistance * solvedDistance)) / (2 * solvedDistance);
  const height = Math.sqrt(Math.max(0, (radiusA * radiusA) - (along * along)));
  const unitX = dx / distance;
  const unitY = dy / distance;
  const midX = centerA[0] + (along * unitX);
  const midY = centerA[1] + (along * unitY);
  const offsetX = -unitY * height;
  const offsetY = unitX * height;
  return [
    [midX + offsetX, midY + offsetY, centerA[2] || 0],
    [midX - offsetX, midY - offsetY, centerA[2] || 0]
  ];
}

function boardBranches(lower) {
  const branches = circleIntersections(PIVOTS.upperFrame, UPPER_LINK_LENGTH, lower, COUPLER_LINK_LENGTH);
  return branches.sort((a, b) => b[1] - a[1]);
}

function translateVector(start, end) {
  return [
    end[0] - start[0],
    end[1] - start[1],
    (end[2] || 0) - (start[2] || 0)
  ];
}

function cycleFlip(cycle) {
  const phase = ((finite(cycle, 0) % 1) + 1) % 1;
  return 0.5 - (0.5 * Math.cos(phase * Math.PI * 2));
}

function sampleMotion(rawFlip, { extension = 1, turnover = 1 } = {}) {
  const flip = clamp01(rawFlip);
  const travel = clamp(extension, 0.2, 1);
  const turnoverAmount = clamp(turnover, 0, 1);
  const extendedAngle = lerp(INITIAL_LOWER_ROCKER_ANGLE_DEG, OVER_CENTER_CRANK_ANGLE_DEG, travel);
  const firstHalf = flip <= 0.5;
  const legT = firstHalf ? smooth01(flip / 0.5) : smooth01((flip - 0.5) / 0.5);
  const lowerAngleDeg = firstHalf
    ? lerp(INITIAL_LOWER_ROCKER_ANGLE_DEG, extendedAngle, legT)
    : lerp(extendedAngle, INITIAL_LOWER_ROCKER_ANGLE_DEG, legT);
  const lower = pointFromAngle(PIVOTS.lowerFrame, LOWER_LINK_LENGTH, lowerAngleDeg);
  const [closedBranch, openBranch] = boardBranches(lower);
  const upper = !firstHalf && turnoverAmount > 0 ? openBranch : closedBranch;
  const angleDeg = angleDeg2(lower, upper);
  return { lower, upper, angleDeg, lowerAngleDeg };
}

function applyVisibility(effects, params) {
  effects.visible("*", true);
  effects.visible("frame", params.showFrame !== false);
  effects.visible(FRAME_DETAIL_PARTS, params.showFrame !== false && params.showDetails !== false);
  effects.visible("frameHardware", params.showFrame !== false && params.showHardware === true);
  effects.visible(["handleHardware", "panelHardware"], params.showHardware === true);
  effects.visible(CROSS_RODS, params.showCrossRods !== false);
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/step/mechanisms/180_degree_flip_mechanism.step"
    },
    label: "180 degree flip mechanism",
    description: "Planar four-bar viewer rig reconstructed from the reference video: blue upper link, pink lower rocker, red/board coupler, and an over-center turnover.",
    units: {
      length: "mm",
      angle: "deg",
      time: "s"
    },
    features: {
      frame: { ref: "#o1.1.1", label: "Frame", description: "Fixed frame body." },
      stopper: { ref: "#o1.1.2", label: "Stopper" },
      bearings: { ref: "#o1.1.3,o1.1.4", label: "Bearing blocks" },
      frameHardware: { ref: "#o1.1.5,o1.1.6,o1.1.7,o1.1.8,o1.1.9,o1.1.10,o1.1.11,o1.1.12,o1.1.13,o1.1.14,o1.1.15,o1.1.16,o1.1.17,o1.1.18,o1.1.19,o1.1.20,o1.1.21,o1.1.22,o1.1.23,o1.1.24,o1.1.25,o1.1.26,o1.1.27,o1.1.28", label: "Frame hardware" },

      rockerBlue: { ref: "#o1.2", label: "Blue upper link", description: "Upper 200 mm link rotating about the upper fixed pivot." },
      rocker2: { ref: "#o1.3.1", label: "Pink lower rocker", description: "Lower rocker arm rotating about the lower fixed pivot." },
      greenRod: { ref: "#o1.3.2", label: "Handle rod" },
      handleHardware: { ref: "#o1.3.3,o1.3.4", label: "Handle hardware" },

      redLink: { ref: "#o1.4.1", label: "Red coupler", description: "Rigid coupler between the upper and lower board pivots." },
      panel: { ref: "#o1.4.2", label: "Flip panel", description: "Panel fixed to the red coupler." },
      driveRod: { ref: "#o1.4.3", label: "Upper board rod" },
      hingeRod: { ref: "#o1.4.7", label: "Lower board rod" },
      panelHardware: { ref: "#o1.4.4,o1.4.5,o1.4.6,o1.4.8", label: "Panel nuts" }
    },
    parameters: {
      flip: { type: "number", label: "Flip", description: "Closed to open travel. The animation loops this 0 -> 1 -> 0.", default: 0, min: 0, max: 1, step: 0.01 },
      extension: { type: "number", label: "Extension", description: "How close the lower rocker drives to the over-center tangent pose.", default: 1, min: 0.2, max: 1, step: 0.01 },
      turnover: { type: "number", label: "Turnover", description: "Enables the returning coupler to use the open branch after the over-center pose.", default: 1, min: 0, max: 1, step: 1 },
      explode: { type: "number", label: "Explode", description: "Separates moving groups for inspection after the linkage motion is applied.", default: 0, min: 0, max: 1, step: 0.01 },
      showFrame: { type: "boolean", label: "Frame", default: true },
      showDetails: { type: "boolean", label: "Frame details", default: true },
      showCrossRods: { type: "boolean", label: "Cross rods", default: true },
      showHardware: { type: "boolean", label: "Hardware", default: true },
      highlightLinks: { type: "boolean", label: "Highlight moving parts", default: false }
    },
    animations: {
      flipLoop: {
        label: "Reference flip loop",
        description: "Closed -> over-center -> open -> over-center -> closed.",
        duration: 5,
        loop: true,
        update({ cycle, set }) {
          set("flip", cycleFlip(cycle));
        }
      },
      inspectExplode: {
        label: "Inspect explode",
        duration: 5,
        loop: true,
        update({ cycle, set }) {
          set("flip", cycleFlip(cycle));
          set("explode", Math.sin((((finite(cycle, 0) % 1) + 1) % 1) * Math.PI));
        }
      }
    }
  },

  update({ params, effects }) {
    const extension = clamp(params.extension, 0.2, 1);
    const turnover = clamp(params.turnover, 0, 1);
    const explode = clamp01(params.explode);
    const pose = sampleMotion(params.flip, { extension, turnover });

    const panelAngleDelta = pose.angleDeg - INITIAL_PANEL_ANGLE_DEG;
    const panelTranslate = translateVector(PIVOTS.lowerBoard, pose.lower);
    const blueAngleDelta = angleDeg2(PIVOTS.upperFrame, pose.upper) - INITIAL_BLUE_ANGLE_DEG;
    const lowerRockerAngleDelta = pose.lowerAngleDeg - INITIAL_LOWER_ROCKER_ANGLE_DEG;

    applyVisibility(effects, params);

    effects.style(FRAME_PARTS, { opacity: 1, edgeOpacity: 0.9 });
    effects.style(FRAME_DETAIL_PARTS, { opacity: 1, edgeOpacity: 0.8 });
    effects.style(HARDWARE, { opacity: 1, edgeOpacity: 0.7 });
    effects.style("panel", { opacity: 1, edgeOpacity: 1 });
    effects.style(["rocker2", "greenRod"], { opacity: 1, edgeOpacity: 1 });
    effects.style("rockerBlue", { opacity: 1, edgeOpacity: 1 });
    effects.style("redLink", { opacity: 1, edgeOpacity: 1 });
    effects.style(CROSS_RODS, { opacity: 1, edgeOpacity: 1 });

    if (params.highlightLinks !== false) {
      effects.highlight(MOVING_PARTS, true);
    }

    effects.transform(PANEL_COUPLER_PARTS, {
      transforms: [
        {
          rotate: {
            axis: Z_AXIS,
            origin: PIVOTS.lowerBoard,
            angleDeg: panelAngleDelta
          }
        },
        { translate: [panelTranslate[0] + (explode * 16), panelTranslate[1] - (explode * 8), panelTranslate[2] + (explode * 24)] }
      ]
    });

    effects.transform("rockerBlue", {
      transforms: [
        {
          rotate: {
            axis: Z_AXIS,
            origin: PIVOTS.upperFrame,
            angleDeg: blueAngleDelta
          }
        },
        { translate: [-explode * 10, -explode * 8, explode * 18] }
      ]
    });

    effects.transform(LOWER_ROCKER_PARTS, {
      transforms: [
        {
          rotate: {
            axis: Z_AXIS,
            origin: PIVOTS.lowerFrame,
            angleDeg: lowerRockerAngleDelta
          }
        },
        { translate: [0, explode * 10, explode * 14] }
      ]
    });

    effects.transform("*", { matrix: FLAT_ON_GROUND_TRANSFORM });
  }
};

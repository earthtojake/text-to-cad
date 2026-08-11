// Shared, renderer-agnostic viewport/camera helpers used by both the mesh CAD
// viewer (CadViewer) and its implicit raymarch pass (useImplicitRaymarch). These
// helpers operate on a generic `runtime` shape that exposes at least
// `{ THREE, camera, controls, keyboardOrbitState }`; they make no assumption
// about how the scene itself is rendered (mesh scene graph vs raymarch quad).
//
// The implementations here are the canonical mesh-viewer versions. The implicit
// viewer is being brought in line with the mesh viewer, so it consumes these
// instead of maintaining its own parallel copies.

export const WORLD_UP = Object.freeze([0, 0, 1]);
export const KEYBOARD_ORBIT_NUDGE_RAD = Math.PI / 32;
export const KEYBOARD_ORBIT_SPEED_RAD_PER_SEC = Math.PI * 0.42;
export const KEYBOARD_POLAR_EPSILON = 0.02;
export const VIEW_PLANE_ACTIVE_DOT_THRESHOLD = 0.994;
export const VIEW_PLANE_TRANSITION_MS = 280;
export const VIEW_PLANE_POLE_DIRECTION_DOT_THRESHOLD = 0.9999;
export const VIEW_PLANE_POLE_DIRECTION_NUDGE = 0.02;
export const DEFAULT_PERSPECTIVE_DIRECTION_DOT_THRESHOLD = 0.999;
export const DEFAULT_PERSPECTIVE_UP_DOT_THRESHOLD = 0.999;
export const DEFAULT_VIEW_DIRECTION = Object.freeze([2.1, -1.65, 1.08]);
export const DEFAULT_VIEW_PLANE_ORIENTATION = Object.freeze({
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1]
});
export const VIEW_PLANE_FACES = [
  { id: "z", label: "Z", title: "Jump to top view", direction: [0, 0, 1], up: [0, 1, 0] },
  { id: "zNeg", label: "-Z", title: "Jump to bottom view", direction: [0, 0, -1], up: [0, 1, 0] },
  { id: "yNeg", label: "-Y", title: "Jump to front view", direction: [0, -1, 0], up: WORLD_UP },
  { id: "y", label: "Y", title: "Jump to back view", direction: [0, 1, 0], up: WORLD_UP },
  { id: "x", label: "X", title: "Jump to right view", direction: [1, 0, 0], up: WORLD_UP },
  { id: "xNeg", label: "-X", title: "Jump to left view", direction: [-1, 0, 0], up: WORLD_UP }
];
export const VIEW_PLANE_FACE_BY_ID = Object.fromEntries(
  VIEW_PLANE_FACES.map((face) => [face.id, face])
);
export const VIEW_PLANE_DEFAULT_PRESET = {
  id: "isometric",
  title: "Reset to default isometric view",
  direction: DEFAULT_VIEW_DIRECTION,
  up: WORLD_UP
};

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

export function normalizeAngleAround(angle, center) {
  let adjusted = angle;
  while (adjusted - center > Math.PI) {
    adjusted -= Math.PI * 2;
  }
  while (adjusted - center < -Math.PI) {
    adjusted += Math.PI * 2;
  }
  return adjusted;
}

export function easeInOutCubic(t) {
  if (t <= 0) {
    return 0;
  }
  if (t >= 1) {
    return 1;
  }
  return t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2;
}

export function isTrackpadLikeWheelEvent(event) {
  return event.ctrlKey || (event.deltaMode === 0 && Math.abs(event.deltaY) < 20);
}

export function normalizeViewportFrameInsets(value = {}) {
  const normalizeInset = (inset) => {
    const numericInset = Number(inset);
    return Number.isFinite(numericInset) ? Math.max(0, numericInset) : 0;
  };
  return {
    top: normalizeInset(value?.top),
    right: normalizeInset(value?.right),
    bottom: normalizeInset(value?.bottom),
    left: normalizeInset(value?.left)
  };
}

// How far back the camera has to sit (perspective) or how tall the orthographic
// frustum has to be, per unit of model radius, for the model to be framed by the
// given viewport. The absolute value is only meaningful against a radius; what
// callers use is the RATIO between two viewports. Rescaling the camera by that
// ratio keeps the model the same fraction of the framed area when the window
// resizes or a side sheet opens or closes, which is what stops a wide model from
// being cropped by a narrowing viewport.
//
// The formulas mirror getFitDistanceForBoundingSphere and
// getOrthographicHalfHeightForBoundingSphere in CadViewer, so a viewport change
// leaves the camera exactly where a fresh fit would have put it -- that is what
// keeps "100%" honest across a resize.
export function viewportFitScale({
  orthographic = false,
  fov = 48,
  aspect = 1,
  height = 1,
  framedHeight = 1
} = {}) {
  const safeAspect = Math.max(finiteNumber(aspect, 1), 1e-3);
  if (orthographic) {
    const safeHeight = Math.max(finiteNumber(height, 1), 1);
    const safeFramedHeight = Math.max(finiteNumber(framedHeight, safeHeight), 1);
    return (1 / Math.min(safeAspect, 1)) * (safeHeight / safeFramedHeight);
  }
  const verticalHalfFov = (Math.max(finiteNumber(fov, 48), 1e-3) * Math.PI) / 360;
  const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * safeAspect);
  const limitingHalfFov = Math.max(Math.min(verticalHalfFov, horizontalHalfFov), 1e-3);
  return 1 / Math.sin(limitingHalfFov);
}

export function getKeyboardOrbitCommand(event) {
  if (!event) {
    return null;
  }
  if (event.key === "ArrowLeft") {
    return { direction: "left", keyId: "ArrowLeft" };
  }
  if (event.key === "ArrowRight") {
    return { direction: "right", keyId: "ArrowRight" };
  }
  if (event.key === "ArrowUp") {
    return { direction: "up", keyId: "ArrowUp" };
  }
  if (event.key === "ArrowDown") {
    return { direction: "down", keyId: "ArrowDown" };
  }

  const key = String(event.key || "").toLowerCase();
  if (key === "a" || event.code === "KeyA") {
    return { direction: "left", keyId: event.code || "KeyA" };
  }
  if (key === "d" || event.code === "KeyD") {
    return { direction: "right", keyId: event.code || "KeyD" };
  }
  if (key === "w" || event.code === "KeyW") {
    return { direction: "up", keyId: event.code || "KeyW" };
  }
  if (key === "s" || event.code === "KeyS") {
    return { direction: "down", keyId: event.code || "KeyS" };
  }
  return null;
}

export function getKeyboardOrbitAxes(keyboardOrbitState) {
  return {
    azimuth:
      (keyboardOrbitState.directionCounts.right > 0 ? 1 : 0) -
      (keyboardOrbitState.directionCounts.left > 0 ? 1 : 0),
    polar:
      (keyboardOrbitState.directionCounts.down > 0 ? 1 : 0) -
      (keyboardOrbitState.directionCounts.up > 0 ? 1 : 0)
  };
}

export function clearKeyboardOrbitState(keyboardOrbitState) {
  if (!keyboardOrbitState) {
    return;
  }
  keyboardOrbitState.pressedKeys.clear();
  keyboardOrbitState.directionCounts.left = 0;
  keyboardOrbitState.directionCounts.right = 0;
  keyboardOrbitState.directionCounts.up = 0;
  keyboardOrbitState.directionCounts.down = 0;
  keyboardOrbitState.lastFrameTime = 0;
}

export function createKeyboardOrbitState() {
  return {
    pressedKeys: new Set(),
    directionCounts: { left: 0, right: 0, up: 0, down: 0 },
    lastFrameTime: 0
  };
}

export function applyOrbitDelta(runtime, azimuthDelta, polarDelta) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return false;
  }
  if (Math.abs(azimuthDelta) < 1e-6 && Math.abs(polarDelta) < 1e-6) {
    return false;
  }

  const offset = new runtime.THREE.Vector3().copy(runtime.camera.position).sub(runtime.controls.target);
  const distance = offset.length();
  if (!Number.isFinite(distance) || distance <= 1e-6) {
    return false;
  }
  const worldUp = new runtime.THREE.Vector3(...WORLD_UP).normalize();
  const direction = offset.clone().divideScalar(distance);
  const minPolar = Math.max(
    Number.isFinite(runtime.controls.minPolarAngle) ? runtime.controls.minPolarAngle : 0,
    KEYBOARD_POLAR_EPSILON
  );
  const maxPolar = Math.min(
    Number.isFinite(runtime.controls.maxPolarAngle) ? runtime.controls.maxPolarAngle : Math.PI,
    Math.PI - KEYBOARD_POLAR_EPSILON
  );
  const currentPolar = Math.acos(clamp(direction.dot(worldUp), -1, 1));
  const requestedPolar = clamp(currentPolar + polarDelta, minPolar, maxPolar);
  const resolvedPolarDelta = requestedPolar - currentPolar;

  const minAzimuth = Number.isFinite(runtime.controls.minAzimuthAngle) ? runtime.controls.minAzimuthAngle : -Infinity;
  const maxAzimuth = Number.isFinite(runtime.controls.maxAzimuthAngle) ? runtime.controls.maxAzimuthAngle : Infinity;
  if (Number.isFinite(minAzimuth) || Number.isFinite(maxAzimuth)) {
    const currentAzimuth = Math.atan2(offset.y, offset.x);
    const nextAzimuth = clamp(normalizeAngleAround(currentAzimuth + azimuthDelta, currentAzimuth), minAzimuth, maxAzimuth);
    azimuthDelta = nextAzimuth - currentAzimuth;
  }

  if (Math.abs(azimuthDelta) > 1e-6) {
    offset.applyAxisAngle(worldUp, azimuthDelta);
  }
  if (Math.abs(resolvedPolarDelta) > 1e-6) {
    let orbitRight = new runtime.THREE.Vector3().crossVectors(worldUp, offset).normalize();
    if (orbitRight.lengthSq() <= 1e-9) {
      orbitRight = new runtime.THREE.Vector3(1, 0, 0);
    }
    offset.applyAxisAngle(orbitRight, resolvedPolarDelta);
  }
  runtime.camera.position.copy(runtime.controls.target).add(offset);
  runtime.camera.up.set(...WORLD_UP);
  runtime.camera.lookAt(runtime.controls.target);
  return true;
}

export function stepKeyboardOrbit(runtime, timestamp) {
  const keyboardOrbitState = runtime?.keyboardOrbitState;
  if (!keyboardOrbitState) {
    return false;
  }

  const axes = getKeyboardOrbitAxes(keyboardOrbitState);
  if (!axes.azimuth && !axes.polar) {
    keyboardOrbitState.lastFrameTime = 0;
    return false;
  }
  if (!keyboardOrbitState.lastFrameTime) {
    keyboardOrbitState.lastFrameTime = timestamp;
    return false;
  }

  const deltaSeconds = clamp((timestamp - keyboardOrbitState.lastFrameTime) / 1000, 0, 0.05);
  keyboardOrbitState.lastFrameTime = timestamp;
  return applyOrbitDelta(
    runtime,
    axes.azimuth * KEYBOARD_ORBIT_SPEED_RAD_PER_SEC * deltaSeconds,
    axes.polar * KEYBOARD_ORBIT_SPEED_RAD_PER_SEC * deltaSeconds
  );
}

export function viewPlaneOrientationEqual(a, b, epsilon = 1e-4) {
  if (!a || !b) {
    return false;
  }
  for (const axis of ["x", "y", "z"]) {
    const left = a[axis];
    const right = b[axis];
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== 3 || right.length !== 3) {
      return false;
    }
    for (let index = 0; index < 3; index += 1) {
      if (Math.abs((left[index] || 0) - (right[index] || 0)) > epsilon) {
        return false;
      }
    }
  }
  return true;
}

export function readViewPlaneOrientation(runtime) {
  if (!runtime?.THREE || !runtime?.camera) {
    return null;
  }
  const inverseCameraRotation = runtime.camera.quaternion.clone().invert();
  const projectAxis = (x, y, z) => {
    const projected = new runtime.THREE.Vector3(x, y, z).applyQuaternion(inverseCameraRotation);
    return [projected.x, projected.y, projected.z];
  };
  return {
    x: projectAxis(1, 0, 0),
    y: projectAxis(0, 1, 0),
    z: projectAxis(0, 0, 1)
  };
}

export function getActiveViewPlaneFaceId(runtime) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return "";
  }

  const offset = new runtime.THREE.Vector3().copy(runtime.camera.position).sub(runtime.controls.target);
  if (offset.lengthSq() < 1e-6) {
    return "";
  }
  offset.normalize();

  let bestId = "";
  let bestScore = -Infinity;
  for (const face of VIEW_PLANE_FACES) {
    const direction = new runtime.THREE.Vector3(...face.direction).normalize();
    const score = offset.dot(direction);
    if (score > bestScore) {
      bestScore = score;
      bestId = face.id;
    }
  }
  return bestScore >= VIEW_PLANE_ACTIVE_DOT_THRESHOLD ? bestId : "";
}

export function cameraMatchesViewPreset(runtime, preset, {
  directionDotThreshold = DEFAULT_PERSPECTIVE_DIRECTION_DOT_THRESHOLD,
  upDotThreshold = DEFAULT_PERSPECTIVE_UP_DOT_THRESHOLD
} = {}) {
  if (
    !runtime?.THREE ||
    !runtime?.camera ||
    !runtime?.controls ||
    !preset ||
    !Array.isArray(preset.direction) ||
    !Array.isArray(preset.up)
  ) {
    return false;
  }
  const currentDirection = runtime.camera.position.clone().sub(runtime.controls.target);
  const nextDirection = new runtime.THREE.Vector3(...preset.direction);
  const currentUp = runtime.camera.up.clone();
  const nextUp = new runtime.THREE.Vector3(...preset.up);
  if (
    currentDirection.lengthSq() <= 1e-8 ||
    nextDirection.lengthSq() <= 1e-8 ||
    currentUp.lengthSq() <= 1e-8 ||
    nextUp.lengthSq() <= 1e-8
  ) {
    return false;
  }
  currentDirection.normalize();
  nextDirection.normalize();
  currentUp.normalize();
  nextUp.normalize();
  return currentDirection.dot(nextDirection) >= directionDotThreshold &&
    currentUp.dot(nextUp) >= upDotThreshold;
}

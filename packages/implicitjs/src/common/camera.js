import * as THREE from "three";

export const WORLD_UP = Object.freeze([0, 0, 1]);
export const TOP_VIEW_UP = Object.freeze([0, 1, 0]);

export const RENDER_CAMERA_PRESETS = Object.freeze({
  front: Object.freeze({ name: "front", direction: Object.freeze([0, -1, 0]), up: WORLD_UP }),
  back: Object.freeze({ name: "back", direction: Object.freeze([0, 1, 0]), up: WORLD_UP }),
  right: Object.freeze({ name: "right", direction: Object.freeze([1, 0, 0]), up: WORLD_UP }),
  left: Object.freeze({ name: "left", direction: Object.freeze([-1, 0, 0]), up: WORLD_UP }),
  top: Object.freeze({ name: "top", direction: Object.freeze([0, 0, 1]), up: TOP_VIEW_UP }),
  bottom: Object.freeze({ name: "bottom", direction: Object.freeze([0, 0, -1]), up: TOP_VIEW_UP }),
  iso: Object.freeze({ name: "iso", direction: Object.freeze([1, -1, 0.8]), up: WORLD_UP }),
  isometric: Object.freeze({ name: "iso", direction: Object.freeze([1, -1, 0.8]), up: WORLD_UP }),
  side: Object.freeze({ name: "side", direction: Object.freeze([1, 0, 0]), up: WORLD_UP })
});

export const RENDER_VIEW_PRESETS = RENDER_CAMERA_PRESETS;

const DEFAULT_CAMERA_PRESET = "iso";
const CAMERA_SPEC_KEYS = Object.freeze(["preset", "position", "target", "up", "zoom", "direction", "name"]);

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function normalizeVector(value, {
  fieldName = "camera vector",
  required = false,
  nonZero = false,
  strict = true
} = {}) {
  if (value === undefined || value === null) {
    if (required && strict) {
      throw new Error(`${fieldName} must be a three-number array`);
    }
    return null;
  }
  if (!Array.isArray(value) || value.length < 3) {
    if (strict) {
      throw new Error(`${fieldName} must be a three-number array`);
    }
    return null;
  }
  const vector = [
    Number(value[0]),
    Number(value[1]),
    Number(value[2])
  ];
  if (!vector.every(Number.isFinite)) {
    if (strict) {
      throw new Error(`${fieldName} must contain only finite numbers`);
    }
    return null;
  }
  if (nonZero && vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2 <= 1e-12) {
    if (strict) {
      throw new Error(`${fieldName} must not be the zero vector`);
    }
    return null;
  }
  return vector;
}

export function cloneCameraVector(vector) {
  return normalizeVector(vector, { strict: false });
}

export function normalizeCameraZoom(value, fallback = 1, {
  fieldName = "camera.zoom",
  strict = false
} = {}) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  const numericValue = Number(value);
  if (Number.isFinite(numericValue) && numericValue > 0) {
    return numericValue;
  }
  if (strict) {
    throw new Error(`${fieldName} must be a positive finite number`);
  }
  return fallback;
}

function clonePreset(preset) {
  return {
    name: preset.name,
    direction: [...preset.direction],
    up: [...preset.up]
  };
}

function cameraPresetByName(name, {
  presets = RENDER_CAMERA_PRESETS,
  strict = true
} = {}) {
  const raw = String(name || DEFAULT_CAMERA_PRESET).trim().toLowerCase();
  if (presets[raw]) {
    return clonePreset(presets[raw]);
  }
  const parts = raw.split(":").map((entry) => Number(entry));
  if (parts.length >= 2 && parts.every(Number.isFinite)) {
    const azimuth = (parts[0] * Math.PI) / 180;
    const elevation = (parts[1] * Math.PI) / 180;
    const cosElevation = Math.cos(elevation);
    return {
      name: `${parts[0]}:${parts[1]}`,
      direction: [
        Math.sin(azimuth) * cosElevation,
        -Math.cos(azimuth) * cosElevation,
        Math.sin(elevation)
      ],
      up: [...WORLD_UP]
    };
  }
  if (strict) {
    throw new Error(`Unknown camera preset: ${name}`);
  }
  return clonePreset(presets[DEFAULT_CAMERA_PRESET]);
}

function parseCameraJsonString(raw, { strict = true } = {}) {
  const text = String(raw || "").trim();
  if (!text.startsWith("{")) {
    return null;
  }
  try {
    const parsed = JSON.parse(text);
    if (!isPlainObject(parsed)) {
      throw new Error("camera JSON must be an object");
    }
    return parsed;
  } catch (error) {
    if (strict) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Invalid camera JSON: ${message}`);
    }
    return null;
  }
}

function validateCameraSpecKeys(spec) {
  const unknownKeys = Object.keys(spec).filter((key) => !CAMERA_SPEC_KEYS.includes(key));
  if (unknownKeys.length) {
    throw new Error(`Unsupported camera fields: ${unknownKeys.join(", ")}`);
  }
}

export function normalizeCameraSpec(rawCamera = DEFAULT_CAMERA_PRESET, {
  presets = RENDER_CAMERA_PRESETS,
  strict = true
} = {}) {
  const parsedJson = typeof rawCamera === "string"
    ? parseCameraJsonString(rawCamera, { strict })
    : null;
  const source = parsedJson || rawCamera;
  if (!isPlainObject(source)) {
    const preset = cameraPresetByName(source || DEFAULT_CAMERA_PRESET, { presets, strict });
    return {
      sourceKind: "string",
      name: preset.name,
      preset: preset.name,
      direction: preset.direction,
      position: null,
      target: null,
      up: preset.up,
      zoom: 1,
      hasExplicitPosition: false,
      hasExplicitTarget: false,
      hasExplicitUp: false,
      hasExplicitZoom: false
    };
  }

  validateCameraSpecKeys(source);
  const rawPreset = source.preset ?? DEFAULT_CAMERA_PRESET;
  const preset = cameraPresetByName(rawPreset, { presets, strict });
  const direction = normalizeVector(source.direction, {
    fieldName: "camera.direction",
    nonZero: true,
    strict
  }) || preset.direction;
  const position = normalizeVector(source.position, {
    fieldName: "camera.position",
    strict
  });
  const target = normalizeVector(source.target, {
    fieldName: "camera.target",
    strict
  });
  const up = normalizeVector(source.up, {
    fieldName: "camera.up",
    nonZero: true,
    strict
  }) || preset.up || [...WORLD_UP];
  const hasExplicitZoom = Object.prototype.hasOwnProperty.call(source, "zoom");
  return {
    sourceKind: "object",
    name: String(source.name || preset.name || "custom"),
    preset: preset.name,
    direction,
    position,
    target,
    up,
    zoom: normalizeCameraZoom(source.zoom, 1, { strict, fieldName: "camera.zoom" }),
    hasExplicitPosition: Object.prototype.hasOwnProperty.call(source, "position"),
    hasExplicitTarget: Object.prototype.hasOwnProperty.call(source, "target"),
    hasExplicitUp: Object.prototype.hasOwnProperty.call(source, "up"),
    hasExplicitZoom
  };
}

function settingsForCamera(sceneScale, settingsByScale) {
  if (settingsByScale?.[sceneScale]) {
    return settingsByScale[sceneScale];
  }
  if (settingsByScale?.cad) {
    return settingsByScale.cad;
  }
  return {
    minBoundsSpan: 1,
    minModelRadius: 1,
    minCameraDistance: 10,
    minCameraFar: 1000
  };
}

function centerAndRadiusFromBounds(bounds, sceneScale, settingsByScale) {
  const settings = settingsForCamera(sceneScale, settingsByScale);
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : [1, 1, 1];
  const center = new THREE.Vector3(
    (toFiniteNumber(min[0]) + toFiniteNumber(max[0], 1)) / 2,
    (toFiniteNumber(min[1]) + toFiniteNumber(max[1], 1)) / 2,
    (toFiniteNumber(min[2]) + toFiniteNumber(max[2], 1)) / 2
  );
  const size = new THREE.Vector3(
    Math.max(toFiniteNumber(max[0], 1) - toFiniteNumber(min[0]), settings.minBoundsSpan),
    Math.max(toFiniteNumber(max[1], 1) - toFiniteNumber(min[1]), settings.minBoundsSpan),
    Math.max(toFiniteNumber(max[2], 1) - toFiniteNumber(min[2]), settings.minBoundsSpan)
  );
  return {
    center,
    radius: Math.max(size.length() / 2, settings.minModelRadius),
    size
  };
}

function vectorFromArray(vector) {
  return new THREE.Vector3(vector[0], vector[1], vector[2]);
}

export function resolveCameraView(rawCamera = DEFAULT_CAMERA_PRESET, options = {}) {
  const spec = normalizeCameraSpec(rawCamera, options);
  const target = spec.target ? vectorFromArray(spec.target) : null;
  const position = spec.position ? vectorFromArray(spec.position) : null;
  const direction = position && target
    ? position.clone().sub(target).normalize().toArray()
    : normalizeVector(spec.direction, {
        fieldName: "camera.direction",
        nonZero: true,
        strict: false
      }) || [...RENDER_CAMERA_PRESETS[DEFAULT_CAMERA_PRESET].direction];
  return {
    name: spec.name,
    direction,
    up: [...(spec.up || WORLD_UP)],
    zoom: spec.zoom
  };
}

export function resolveCameraSnapshot(rawCamera = DEFAULT_CAMERA_PRESET, bounds = null, {
  sceneScale = "cad",
  settingsByScale = null,
  presets = RENDER_CAMERA_PRESETS,
  strict = true
} = {}) {
  const spec = normalizeCameraSpec(rawCamera, { presets, strict });
  const settings = settingsForCamera(sceneScale, settingsByScale);
  const { center, radius, size } = centerAndRadiusFromBounds(bounds, sceneScale, settingsByScale);
  const target = spec.target ? vectorFromArray(spec.target) : center.clone();
  const direction = normalizeVector(spec.direction, {
    fieldName: "camera.direction",
    nonZero: true,
    strict
  }) || [...RENDER_CAMERA_PRESETS[DEFAULT_CAMERA_PRESET].direction];
  const position = spec.position
    ? vectorFromArray(spec.position)
    : target.clone().add(vectorFromArray(direction).normalize().multiplyScalar(
        Math.max(radius * 3.2, settings.minCameraDistance || settings.minModelRadius * 10 || 10)
      ));
  const resolvedDirection = position.clone().sub(target);
  if (resolvedDirection.lengthSq() <= 1e-12) {
    throw new Error("camera.position must differ from camera.target");
  }
  const up = vectorFromArray(spec.up || WORLD_UP);
  if (up.lengthSq() <= 1e-12) {
    throw new Error("camera.up must not be the zero vector");
  }
  return {
    name: spec.name,
    preset: spec.preset,
    position: position.toArray(),
    target: target.toArray(),
    up: up.normalize().toArray(),
    zoom: spec.zoom,
    direction: resolvedDirection.normalize().toArray(),
    view: {
      name: spec.name,
      direction: resolvedDirection.normalize().toArray(),
      up: up.normalize().toArray(),
      zoom: spec.zoom
    },
    sourceKind: spec.sourceKind,
    hasExplicitPosition: spec.hasExplicitPosition,
    hasExplicitTarget: spec.hasExplicitTarget,
    hasExplicitUp: spec.hasExplicitUp,
    hasExplicitZoom: spec.hasExplicitZoom,
    radius,
    size: size.toArray()
  };
}

export function cameraSpecUsesPerspectiveProjection(rawCamera = DEFAULT_CAMERA_PRESET, options = {}) {
  const spec = normalizeCameraSpec(rawCamera, options);
  return spec.sourceKind === "object" && (
    spec.hasExplicitPosition ||
    spec.hasExplicitTarget ||
    spec.hasExplicitUp
  );
}

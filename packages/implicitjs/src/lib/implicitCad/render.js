import {
  normalizeCameraSpec
} from "../../common/camera.js";
import {
  resolveThemeSettings
} from "../../common/renderOptions.js";
import {
  normalizeThemeSettings,
  DEFAULT_FILL_LIGHT_SETTINGS,
  DEFAULT_RIM_LIGHT_SETTINGS
} from "../../common/themeSettings.js";
import {
  normalizeImplicitGraphicsSettings
} from "./graphicsSettings.js";
import { normalizeImplicitCadModel } from "./model.js";
import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";
import {
  BASE_VIEWER_THEME,
  getViewerThemeValue
} from "../viewer/stageTheme.js";
import {
  readSourceColor,
  resolveSourceBaseColor
} from "../viewer/surfaceMaterials.js";

const DEFAULT_BACKGROUND = "#0b1020";
const DEFAULT_FOV_DEG = 48;
const DEFAULT_SNAPSHOT_CAMERA_ZOOM = 1.25;
const DEFAULT_SNAPSHOT_FRAME_MARGIN = 1.42;
const FRAME_BOUNDS_SAMPLE_COUNT = 25;
const FRAME_BOUNDS_THRESHOLD_STEP_FACTOR = 0.45;
const FRAME_BOUNDS_MARGIN_STEP_FACTOR = 0.75;
const FRAME_BOUNDS_MARGIN_SIZE_FACTOR = 0.015;
const DEFAULT_THEME_ID = "workbench";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function colorToRgb01(color) {
  return [
    clamp(Number(color?.r) || 0, 0, 1),
    clamp(Number(color?.g) || 0, 0, 1),
    clamp(Number(color?.b) || 0, 0, 1)
  ];
}

function normalizeBackgroundMode(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "linear") {
    return 1;
  }
  if (normalized === "radial") {
    return 2;
  }
  return 0;
}

function degreesToRadians(value, fallback = 180) {
  const numeric = Number(value);
  return (Number.isFinite(numeric) ? numeric : fallback) * Math.PI / 180;
}

function implicitCadUniformDeclarations(uniforms = {}) {
  return Object.entries(uniforms)
    .map(([name, uniform]) => `uniform ${uniform.type} ${name};`)
    .sort()
    .join("\n");
}

// Mirrors the mesh viewer's default workbench light rig so implicit models
// shade like STEP/GLB models when no theme settings are provided.
const DEFAULT_LIGHTING_RIG = Object.freeze({
  toneMappingExposure: 1.16,
  directional: { color: "#ffffff", intensity: 1.16, position: { x: -210, y: 260, z: 270 } },
  spot: { color: "#f4fbff", intensity: 0.52, position: { x: 190, y: 210, z: 170 } },
  point: { color: "#ffe2ba", intensity: 0.28, position: { x: -240, y: 110, z: -210 } },
  ambient: { color: "#ffffff", intensity: 0.4 },
  hemisphere: { skyColor: "#ffffff", groundColor: "#d6e2ee", intensity: 1.12 },
  environmentAmbientScale: 1.0,
  rimColor: "#6db6e8",
  rimIntensity: 0.08,
  floorShadowOpacity: 0.16,
});

function srgbChannelToLinear(value) {
  const channel = Math.min(Math.max(finiteNumber(value, 0), 0), 1);
  return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
}

function linearLightRgb(color, intensity, fallbackColor) {
  const rgb = hexToRgb01(color, fallbackColor);
  const scale = Math.max(finiteNumber(intensity, 0), 0);
  return rgb.map((channel) => srgbChannelToLinear(channel) * scale);
}

function lightDirectionFromPosition(position, fallbackPosition) {
  const source = position && typeof position === "object" ? position : fallbackPosition;
  const x = finiteNumber(source?.x, fallbackPosition.x);
  const y = finiteNumber(source?.y, fallbackPosition.y);
  const z = finiteNumber(source?.z, fallbackPosition.z);
  const length = Math.hypot(x, y, z);
  return length > 1e-9
    ? [x / length, y / length, z / length]
    : lightDirectionFromPosition(fallbackPosition, { x: 0, y: 0, z: 1 });
}

function implicitFloorFadeRadius(bounds) {
  const size = [
    bounds.max[0] - bounds.min[0],
    bounds.max[1] - bounds.min[1],
    bounds.max[2] - bounds.min[2],
  ];
  return Math.max(Math.hypot(size[0], size[1], size[2]) * 1.2, 1e-3);
}

// Declared model bounds are often padded well past the surface, which would
// hang the stage-floor shadow in mid-air. Sample the SDF for tight bounds and
// cache per material; re-estimate only when declared bounds move materially.
function implicitFloorBoundsForModel(normalized, userData = null, { estimate = true } = {}) {
  const boundsKey = `${normalized.bounds.min.join(",")}|${normalized.bounds.max.join(",")}`;
  if (userData?.implicitFloorBounds) {
    if (userData.implicitFloorBoundsKey === boundsKey) {
      return userData.implicitFloorBounds;
    }
    const previous = userData.implicitFloorDeclaredBounds;
    if (previous) {
      const current = [...normalized.bounds.min, ...normalized.bounds.max];
      const radius = Math.max(finiteNumber(normalized.radius, 1), 1e-6);
      let maxDelta = 0;
      for (let index = 0; index < 6; index += 1) {
        maxDelta = Math.max(maxDelta, Math.abs(finiteNumber(previous[index], 0) - finiteNumber(current[index], 0)));
      }
      if (maxDelta < radius * 0.05) {
        return userData.implicitFloorBounds;
      }
    }
  }
  let floorBounds = null;
  try {
    floorBounds = estimate
      ? estimateImplicitCadFrameBounds(normalized)
      : peekImplicitCadFrameBounds(normalized);
  } catch {
    floorBounds = null;
  }
  if (!floorBounds) {
    // No estimate available yet: place the floor on declared bounds without
    // caching, so a later (possibly async) estimate can still refine it.
    return normalized.bounds;
  }
  if (userData) {
    userData.implicitFloorBounds = floorBounds;
    userData.implicitFloorBoundsKey = boundsKey;
    userData.implicitFloorDeclaredBounds = [...normalized.bounds.min, ...normalized.bounds.max];
  }
  return floorBounds;
}

function applyImplicitFloorUniforms(material, floorBounds) {
  if (!material?.uniforms?.uFloorZ || !material.uniforms.uFloorCenter || !material.uniforms.uFloorFadeRadius) {
    return;
  }
  material.uniforms.uFloorZ.value = floorBounds.min[2];
  material.uniforms.uFloorCenter.value.set(
    (floorBounds.min[0] + floorBounds.max[0]) / 2,
    (floorBounds.min[1] + floorBounds.max[1]) / 2
  );
  material.uniforms.uFloorFadeRadius.value = implicitFloorFadeRadius(floorBounds);
}

// Resolve tight floor bounds off the main thread and apply them to the
// material; loading stays responsive and the floor snaps in when ready.
export async function refreshImplicitCadFloorBounds(material, model) {
  const normalized = normalizeImplicitCadModel(model);
  await estimateImplicitCadFrameBoundsAsync(normalized);
  const floorBounds = implicitFloorBoundsForModel(normalized, material?.userData || null, { estimate: false });
  applyImplicitFloorUniforms(material, floorBounds);
  return floorBounds;
}

function vecUniformValue(THREE, type, value = []) {
  const source = Array.isArray(value) || ArrayBuffer.isView(value) ? value : [];
  if (type === "vec2") {
    return new THREE.Vector2(finiteNumber(source[0], 0), finiteNumber(source[1], 0));
  }
  if (type === "vec3") {
    return new THREE.Vector3(finiteNumber(source[0], 0), finiteNumber(source[1], 0), finiteNumber(source[2], 0));
  }
  return new THREE.Vector4(
    finiteNumber(source[0], 0),
    finiteNumber(source[1], 0),
    finiteNumber(source[2], 0),
    finiteNumber(source[3], 0)
  );
}

function threeUniformValue(THREE, uniform) {
  if (uniform?.type === "bool") {
    return uniform.value === true;
  }
  if (uniform?.type === "int") {
    return Math.trunc(finiteNumber(uniform.value, 0));
  }
  if (uniform?.type === "vec2" || uniform?.type === "vec3" || uniform?.type === "vec4") {
    return vecUniformValue(THREE, uniform.type, uniform.value);
  }
  return finiteNumber(uniform?.value, 0);
}

function updateThreeUniformValue(THREE, targetUniform, uniform) {
  if (!targetUniform) {
    return;
  }
  if (uniform?.type === "bool") {
    targetUniform.value = uniform.value === true;
    return;
  }
  if (uniform?.type === "int") {
    targetUniform.value = Math.trunc(finiteNumber(uniform.value, 0));
    return;
  }
  if (uniform?.type === "vec2" || uniform?.type === "vec3" || uniform?.type === "vec4") {
    const nextValue = vecUniformValue(THREE, uniform.type, uniform.value);
    if (targetUniform.value?.copy) {
      targetUniform.value.copy(nextValue);
    } else {
      targetUniform.value = nextValue;
    }
    return;
  }
  targetUniform.value = finiteNumber(uniform?.value, 0);
}

function isIdentifierCharacter(value) {
  return /[A-Za-z0-9_]/.test(value || "");
}

function previousSignificantCharacter(source, index) {
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const character = source[cursor];
    if (!/\s/.test(character)) {
      return character;
    }
  }
  return "";
}

function nextSignificantCharacter(source, index) {
  for (let cursor = index; cursor < source.length; cursor += 1) {
    const character = source[cursor];
    if (!/\s/.test(character)) {
      return character;
    }
  }
  return "";
}

function statementPrefix(source, index) {
  const boundary = Math.max(
    source.lastIndexOf(";", index - 1),
    source.lastIndexOf("{", index - 1),
    source.lastIndexOf("}", index - 1),
    source.lastIndexOf("\n", index - 1)
  );
  return source.slice(boundary + 1, index);
}

function isInsideForHeader(source, index) {
  const forIndex = source.lastIndexOf("for", index);
  if (forIndex < 0) {
    return false;
  }
  const boundary = Math.max(
    source.lastIndexOf(";", forIndex - 1),
    source.lastIndexOf("{", forIndex - 1),
    source.lastIndexOf("}", forIndex - 1),
    source.lastIndexOf("\n", forIndex - 1)
  );
  if (forIndex < boundary) {
    return false;
  }
  const openParen = source.indexOf("(", forIndex);
  const closeParen = openParen >= 0 ? source.indexOf(")", openParen) : -1;
  return openParen >= 0 && openParen < index && closeParen >= index;
}

function isExponentSuffixDigits(source, start) {
  // Adjacent characters only: a signed exponent never contains whitespace, so
  // "1.0e-6" matches here while "value - 6" and "foo_e-6" do not.
  const sign = source[start - 1];
  if (sign !== "+" && sign !== "-") {
    return false;
  }
  const marker = source[start - 2];
  if (marker !== "e" && marker !== "E") {
    return false;
  }
  return /[0-9.]/.test(source[start - 3] || "");
}

const INT_SCALAR_DECLARATION_PATTERN = /\b(?:int|uint)\s+([A-Za-z_]\w*)/g;

function collectIntScalarIdentifiers(source) {
  const identifiers = new Set();
  let match;
  INT_SCALAR_DECLARATION_PATTERN.lastIndex = 0;
  while ((match = INT_SCALAR_DECLARATION_PATTERN.exec(source)) !== null) {
    identifiers.add(match[1]);
  }
  return identifiers;
}

function comparisonOperandBefore(source, start) {
  // Only operators ending in "=" can reach a literal here: a bare "<" or ">"
  // before the literal is already rejected by the previous-character guard.
  let cursor = start - 1;
  while (cursor >= 0 && /\s/.test(source[cursor])) {
    cursor -= 1;
  }
  if (source[cursor] !== "=") {
    return "";
  }
  const lead = source[cursor - 1];
  if (lead !== "=" && lead !== "!" && lead !== "<" && lead !== ">") {
    return "";
  }
  let operandEnd = cursor - 2;
  while (operandEnd >= 0 && /\s/.test(source[operandEnd])) {
    operandEnd -= 1;
  }
  let operandStart = operandEnd;
  while (operandStart >= 0 && isIdentifierCharacter(source[operandStart])) {
    operandStart -= 1;
  }
  return source.slice(operandStart + 1, operandEnd + 1);
}

function shouldPromoteIntegerLiteral(source, start, end, intIdentifiers) {
  const previous = previousSignificantCharacter(source, start);
  const next = nextSignificantCharacter(source, end);
  if (previous === "." || next === "." || isIdentifierCharacter(previous) || isIdentifierCharacter(next)) {
    return false;
  }
  if (next === "[" || previous === "[") {
    return false;
  }
  if (previous && !/[+\-*/=(,{?:]/.test(previous)) {
    return false;
  }
  if (next && !/[,);}\]+\-*/?:]/.test(next)) {
    return false;
  }
  if (isExponentSuffixDigits(source, start)) {
    return false;
  }
  const comparedOperand = comparisonOperandBefore(source, start);
  if (comparedOperand && intIdentifiers?.has(comparedOperand)) {
    return false;
  }
  if (isInsideForHeader(source, start)) {
    return false;
  }
  const prefix = statementPrefix(source, start);
  return !/\b(?:int|ivec[234]|uint|uvec[234])\b/.test(prefix);
}

export function normalizeImplicitCadGlslFloatLiterals(source) {
  const text = String(source || "");
  const intIdentifiers = collectIntScalarIdentifiers(text);
  let result = "";
  let index = 0;
  while (index < text.length) {
    const character = text[index];
    const nextCharacter = text[index + 1];
    if (character === "/" && (nextCharacter === "/" || nextCharacter === "*")) {
      const commentEnd = nextCharacter === "/"
        ? text.indexOf("\n", index + 2)
        : text.indexOf("*/", index + 2);
      const end = commentEnd < 0
        ? text.length
        : nextCharacter === "/" ? commentEnd : commentEnd + 2;
      result += text.slice(index, end);
      index = end;
      continue;
    }
    const match = text.slice(index).match(/^\d+/);
    if (match) {
      const token = match[0];
      const end = index + token.length;
      result += shouldPromoteIntegerLiteral(text, index, end, intIdentifiers) ? `${token}.0` : token;
      index = end;
      continue;
    }
    result += character;
    index += 1;
  }
  return result;
}

function hexToRgb01(hex, fallback = DEFAULT_BACKGROUND) {
  const raw = String(hex || fallback).trim();
  const value = /^#(?:[0-9a-fA-F]{3}){1,2}$/.test(raw) ? raw : fallback;
  const expanded = value.length === 4
    ? `${value[1]}${value[1]}${value[2]}${value[2]}${value[3]}${value[3]}`
    : value.slice(1);
  return [
    parseInt(expanded.slice(0, 2), 16) / 255,
    parseInt(expanded.slice(2, 4), 16) / 255,
    parseInt(expanded.slice(4, 6), 16) / 255,
  ];
}

function cameraBoundsForImplicitModel(model) {
  if (model?.bounds?.min && model?.bounds?.max) {
    return model.bounds;
  }
  const radius = Math.max(finiteNumber(model?.radius, 1), 1e-3);
  const center = Array.isArray(model?.center) ? model.center : [0, 0, 0];
  return {
    min: [center[0] - radius, center[1] - radius, center[2] - radius],
    max: [center[0] + radius, center[1] + radius, center[2] + radius]
  };
}

function boundsCenter(bounds) {
  return [
    (finiteNumber(bounds?.min?.[0], -1) + finiteNumber(bounds?.max?.[0], 1)) / 2,
    (finiteNumber(bounds?.min?.[1], -1) + finiteNumber(bounds?.max?.[1], 1)) / 2,
    (finiteNumber(bounds?.min?.[2], -1) + finiteNumber(bounds?.max?.[2], 1)) / 2
  ];
}

function boundsSize(bounds) {
  return [
    Math.max(finiteNumber(bounds?.max?.[0], 1) - finiteNumber(bounds?.min?.[0], -1), 1e-3),
    Math.max(finiteNumber(bounds?.max?.[1], 1) - finiteNumber(bounds?.min?.[1], -1), 1e-3),
    Math.max(finiteNumber(bounds?.max?.[2], 1) - finiteNumber(bounds?.min?.[2], -1), 1e-3)
  ];
}

function expandBounds(min, max, margin) {
  const safeMargin = Math.max(finiteNumber(margin, 0), 0);
  return {
    min: [min[0] - safeMargin, min[1] - safeMargin, min[2] - safeMargin],
    max: [max[0] + safeMargin, max[1] + safeMargin, max[2] + safeMargin]
  };
}

const FRAME_BOUNDS_CACHE_LIMIT = 32;
const frameBoundsEstimateCache = new Map();

function frameBoundsCacheKey(model, fallbackBounds) {
  const source = String(model?.glslSource || model?.distanceSource || "");
  let uniformsKey = "";
  try {
    uniformsKey = JSON.stringify(model?.uniforms ?? null);
  } catch {
    uniformsKey = "?";
  }
  return `${JSON.stringify(fallbackBounds)}|${uniformsKey}|${source}`;
}

// The CPU evaluator interprets the model's GLSL per sample, so the grid
// density must shrink as source size grows or heavy models stall the browser
// main thread for tens of seconds on load.
function frameBoundsSampleCount(model) {
  const sourceLength = String(model?.glslSource || model?.distanceSource || "").length;
  if (sourceLength > 16000) {
    return 9;
  }
  if (sourceLength > 8000) {
    return 11;
  }
  if (sourceLength > 4000) {
    return 17;
  }
  return FRAME_BOUNDS_SAMPLE_COUNT;
}

function rememberFrameBoundsEstimate(cacheKey, estimated) {
  frameBoundsEstimateCache.set(cacheKey, estimated);
  while (frameBoundsEstimateCache.size > FRAME_BOUNDS_CACHE_LIMIT) {
    frameBoundsEstimateCache.delete(frameBoundsEstimateCache.keys().next().value);
  }
}

function peekImplicitCadFrameBounds(model) {
  if (model?.frameBounds?.min && model?.frameBounds?.max) {
    return model.frameBounds;
  }
  const fallbackBounds = cameraBoundsForImplicitModel(model);
  return frameBoundsEstimateCache.get(frameBoundsCacheKey(model, fallbackBounds)) || null;
}

// Shared core of the sync and async estimators: a generator that yields after
// each sample row so the async driver can hand control back to the event loop
// between slices while the sync driver simply drains it in one pass.
function* scanImplicitCadFrameBoundsSteps(model, fallbackBounds, cacheKey) {
  let sdf = null;
  try {
    sdf = createImplicitCadSdfEvaluator(model);
  } catch {
    return fallbackBounds;
  }

  const sampleCount = frameBoundsSampleCount(model);
  const size = boundsSize(fallbackBounds);
  const step = size.map((axisSize) => axisSize / Math.max(sampleCount - 1, 1));
  const threshold = Math.max(
    Math.min(...step) * FRAME_BOUNDS_THRESHOLD_STEP_FACTOR,
    finiteNumber(model?.epsilon, 0.002) * 12,
    0.01
  );
  const hitMin = [Infinity, Infinity, Infinity];
  const hitMax = [-Infinity, -Infinity, -Infinity];
  let hitCount = 0;
  try {
    for (let ix = 0; ix < sampleCount; ix += 1) {
      const x = fallbackBounds.min[0] + step[0] * ix;
      for (let iy = 0; iy < sampleCount; iy += 1) {
        const y = fallbackBounds.min[1] + step[1] * iy;
        for (let iz = 0; iz < sampleCount; iz += 1) {
          const z = fallbackBounds.min[2] + step[2] * iz;
          if (finiteNumber(sdf(x, y, z), 1e6) > threshold) {
            continue;
          }
          hitCount += 1;
          hitMin[0] = Math.min(hitMin[0], x);
          hitMin[1] = Math.min(hitMin[1], y);
          hitMin[2] = Math.min(hitMin[2], z);
          hitMax[0] = Math.max(hitMax[0], x);
          hitMax[1] = Math.max(hitMax[1], y);
          hitMax[2] = Math.max(hitMax[2], z);
        }
        yield;
      }
    }
  } catch {
    return fallbackBounds;
  }
  if (!hitCount) {
    return fallbackBounds;
  }
  const margin = Math.max(
    Math.max(...step) * FRAME_BOUNDS_MARGIN_STEP_FACTOR,
    Math.max(...size) * FRAME_BOUNDS_MARGIN_SIZE_FACTOR,
    finiteNumber(model?.epsilon, 0.002) * 20,
    0.25
  );
  const expanded = expandBounds(hitMin, hitMax, margin);
  // The sampling margin can push past the model's declared bounds, especially
  // at coarse grids; declared bounds are an authoritative outer limit, so the
  // estimate only ever refines inward.
  const estimated = {
    min: expanded.min.map((value, axis) => Math.max(value, fallbackBounds.min[axis])),
    max: expanded.max.map((value, axis) => Math.min(value, fallbackBounds.max[axis])),
  };
  rememberFrameBoundsEstimate(cacheKey, estimated);
  return estimated;
}

function estimateImplicitCadFrameBounds(model) {
  const fallbackBounds = cameraBoundsForImplicitModel(model);
  if (model?.frameBounds?.min && model?.frameBounds?.max) {
    return model.frameBounds;
  }
  const cacheKey = frameBoundsCacheKey(model, fallbackBounds);
  if (frameBoundsEstimateCache.has(cacheKey)) {
    const cached = frameBoundsEstimateCache.get(cacheKey);
    frameBoundsEstimateCache.delete(cacheKey);
    frameBoundsEstimateCache.set(cacheKey, cached);
    return cached;
  }
  const steps = scanImplicitCadFrameBoundsSteps(model, fallbackBounds, cacheKey);
  let current = steps.next();
  while (!current.done) {
    current = steps.next();
  }
  return current.value || fallbackBounds;
}

const frameBoundsEstimatePending = new Map();

export async function estimateImplicitCadFrameBoundsAsync(model) {
  const fallbackBounds = cameraBoundsForImplicitModel(model);
  if (model?.frameBounds?.min && model?.frameBounds?.max) {
    return model.frameBounds;
  }
  const cacheKey = frameBoundsCacheKey(model, fallbackBounds);
  if (frameBoundsEstimateCache.has(cacheKey)) {
    return frameBoundsEstimateCache.get(cacheKey);
  }
  if (frameBoundsEstimatePending.has(cacheKey)) {
    return frameBoundsEstimatePending.get(cacheKey);
  }
  const pending = (async () => {
    const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());
    const steps = scanImplicitCadFrameBoundsSteps(model, fallbackBounds, cacheKey);
    let sliceStart = now();
    let current = steps.next();
    while (!current.done) {
      if (now() - sliceStart >= 10) {
        await new Promise((resolve) => setTimeout(resolve, 0));
        sliceStart = now();
      }
      current = steps.next();
    }
    return current.value || fallbackBounds;
  })().finally(() => {
    frameBoundsEstimatePending.delete(cacheKey);
  });
  frameBoundsEstimatePending.set(cacheKey, pending);
  return pending;
}

function vectorFromArray(value, fallback) {
  const source = Array.isArray(value) || ArrayBuffer.isView(value) ? value : fallback;
  return [0, 1, 2].map((index) => finiteNumber(source?.[index], fallback[index] || 0));
}

function vectorLength(value) {
  return Math.hypot(value[0], value[1], value[2]);
}

function normalizeVector(value, fallback = [1, 0, 0]) {
  const source = vectorFromArray(value, fallback);
  const length = vectorLength(source);
  return length > 1e-9
    ? source.map((component) => component / length)
    : normalizeVector(fallback, [1, 0, 0]);
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]
  ];
}

function subtract(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function addScaled(a, direction, scale) {
  return [
    a[0] + direction[0] * scale,
    a[1] + direction[1] * scale,
    a[2] + direction[2] * scale
  ];
}

function boundsCorners(bounds) {
  const corners = [];
  for (const x of [bounds.min[0], bounds.max[0]]) {
    for (const y of [bounds.min[1], bounds.max[1]]) {
      for (const z of [bounds.min[2], bounds.max[2]]) {
        corners.push([x, y, z]);
      }
    }
  }
  return corners;
}

function cameraFrameAxes(direction, up) {
  const zAxis = normalizeVector(direction, [1, -1, 0.8]);
  let requestedUp = normalizeVector(up, [0, 0, 1]);
  if (Math.abs(dot(zAxis, requestedUp)) > 0.96) {
    requestedUp = Math.abs(zAxis[2]) > 0.8 ? [0, 1, 0] : [0, 0, 1];
  }
  const right = normalizeVector(cross(requestedUp, zAxis), [1, 0, 0]);
  const screenUp = normalizeVector(cross(zAxis, right), [0, 0, 1]);
  return { zAxis, right, screenUp };
}

function fitDistanceForFrameBounds(bounds, target, axes, aspect, margin = DEFAULT_SNAPSHOT_FRAME_MARGIN, zoom = 1) {
  const tanHalfFov = Math.tan((DEFAULT_FOV_DEG * Math.PI) / 360);
  const safeAspect = Math.max(finiteNumber(aspect, 4 / 3), 0.05);
  const safeMargin = Math.max(finiteNumber(margin, DEFAULT_SNAPSHOT_FRAME_MARGIN), 1.05);
  const safeZoom = Math.max(finiteNumber(zoom, 1), 0.05);
  let distance = 0;
  for (const corner of boundsCorners(bounds)) {
    const relative = subtract(corner, target);
    const x = Math.abs(dot(relative, axes.right));
    const y = Math.abs(dot(relative, axes.screenUp));
    const z = dot(relative, axes.zAxis);
    distance = Math.max(
      distance,
      z + Math.max(x / (tanHalfFov * safeAspect), y / tanHalfFov) * safeMargin * safeZoom
    );
  }
  return Math.max(distance, 1e-3);
}

function projectedBoundsCenter(bounds, target, axes, distance, aspect, zoom) {
  const tanHalfFov = Math.tan((DEFAULT_FOV_DEG * Math.PI) / 360);
  const safeAspect = Math.max(finiteNumber(aspect, 4 / 3), 0.05);
  const safeZoom = Math.max(finiteNumber(zoom, 1), 0.05);
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const corner of boundsCorners(bounds)) {
    const relative = subtract(corner, target);
    const depth = Math.max(distance - dot(relative, axes.zAxis), 1e-3);
    const x = dot(relative, axes.right) * safeZoom / (depth * tanHalfFov * safeAspect);
    const y = dot(relative, axes.screenUp) * safeZoom / (depth * tanHalfFov);
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  return {
    x: (minX + maxX) / 2,
    y: (minY + maxY) / 2
  };
}

function recenterTargetForProjectedBounds(bounds, target, axes, distance, aspect, zoom) {
  const center = projectedBoundsCenter(bounds, target, axes, distance, aspect, zoom);
  const tanHalfFov = Math.tan((DEFAULT_FOV_DEG * Math.PI) / 360);
  const safeAspect = Math.max(finiteNumber(aspect, 4 / 3), 0.05);
  const safeZoom = Math.max(finiteNumber(zoom, 1), 0.05);
  const xShift = center.x * distance * tanHalfFov * safeAspect / safeZoom;
  const yShift = center.y * distance * tanHalfFov / safeZoom;
  return addScaled(addScaled(target, axes.right, xShift), axes.screenUp, yShift);
}

export function implicitCadCameraState(model, camera = "iso", {
  zoom = DEFAULT_SNAPSHOT_CAMERA_ZOOM,
  width = 4,
  height = 3,
  frameMargin = DEFAULT_SNAPSHOT_FRAME_MARGIN,
  estimateFrameBounds = true
} = {}) {
  const spec = normalizeCameraSpec(camera, { strict: true });
  // estimateFrameBounds=false keeps this call off the CPU SDF evaluator: it
  // uses a cached estimate when one exists and declared bounds otherwise, so
  // interactive callers can frame instantly and refine after
  // estimateImplicitCadFrameBoundsAsync completes.
  const frameBounds = estimateFrameBounds
    ? estimateImplicitCadFrameBounds(model)
    : (peekImplicitCadFrameBounds(model) || cameraBoundsForImplicitModel(model));
  const fallbackBounds = cameraBoundsForImplicitModel(model);
  const center = boundsCenter(frameBounds || fallbackBounds);
  let target = vectorFromArray(spec.target, center);
  const effectiveZoom = spec.hasExplicitZoom
    ? spec.zoom
    : Math.max(finiteNumber(zoom, DEFAULT_SNAPSHOT_CAMERA_ZOOM), 0.05);
  const direction = spec.position
    ? [
        spec.position[0] - target[0],
        spec.position[1] - target[1],
        spec.position[2] - target[2]
      ]
    : vectorFromArray(spec.direction, [1, -1, 0.8]);
  const unitDirection = normalizeVector(direction, [1, -1, 0.8]);
  const axes = cameraFrameAxes(unitDirection, spec.up);
  const aspect = Math.max(finiteNumber(width, 4) / Math.max(finiteNumber(height, 3), 1), 0.05);
  const fitDistance = fitDistanceForFrameBounds(frameBounds, target, axes, aspect, frameMargin, effectiveZoom);
  const distance = Math.max(fitDistance, Math.max(finiteNumber(model?.radius, 1), 1e-3) * 0.45);
  if (!spec.position && !spec.hasExplicitTarget) {
    target = recenterTargetForProjectedBounds(frameBounds, target, axes, distance, aspect, effectiveZoom);
  }
  const position = spec.position
    ? vectorFromArray(spec.position, [target[0] + unitDirection[0] * distance, target[1] + unitDirection[1] * distance, target[2] + unitDirection[2] * distance])
    : [
        target[0] + unitDirection[0] * distance,
        target[1] + unitDirection[1] * distance,
        target[2] + unitDirection[2] * distance
      ];
  return {
    label: spec.name,
    preset: spec.preset,
    target,
    position,
    direction: unitDirection,
    up: vectorFromArray(spec.up, [0, 0, 1]),
    zoom: effectiveZoom,
    fov: DEFAULT_FOV_DEG,
    bounds: fallbackBounds,
    frameBounds,
  };
}

// The shader's helper library, lifted out of the fragment-shader template so it has a name.
//
// Every function here also exists, hand-written a second time, as a JS entry in the BUILTINS
// table of `sdfEvaluator.js`: the GPU runs these bodies, the baked render artifact runs those.
// Two implementations of one contract is a standing divergence risk, so `sdfField.test.js`
// parses THIS text and differentially evaluates it against the JS table. It is interpolated verbatim into the shader below.
export const IMPLICIT_CAD_GLSL_LIBRARY = `float implicit_clamp01(float value) {
  return clamp(value, 0.0, 1.0);
}

float implicit_linear_map(float value, float inMin, float inMax, float outMin, float outMax) {
  float slope = (outMax - outMin) / (inMax - inMin);
  return (value - inMin) * slope + outMin;
}

float implicit_ramp(float value, float inMin, float inMax, float outMin, float outMax) {
  return clamp(implicit_linear_map(value, inMin, inMax, outMin, outMax), outMin, outMax);
}

float implicit_two_body_field(float a, float b) {
  return (a - b) / (a + b);
}

float implicit_two_body_polar(float a, float b, float angle) {
  return a * cos(angle) + b * sin(angle);
}

float implicit_triangle_wave_even(float value, float period) {
  float halfPeriod = period * 0.5;
  float quarterPeriod = period * 0.25;
  float wrapped = mod(value + halfPeriod, period);
  return quarterPeriod - abs(wrapped - halfPeriod);
}

vec2 implicit_triangle_wave_even(vec2 value, vec2 period) {
  return vec2(
    implicit_triangle_wave_even(value.x, period.x),
    implicit_triangle_wave_even(value.y, period.y)
  );
}

vec3 implicit_triangle_wave_even(vec3 value, vec3 period) {
  return vec3(
    implicit_triangle_wave_even(value.x, period.x),
    implicit_triangle_wave_even(value.y, period.y),
    implicit_triangle_wave_even(value.z, period.z)
  );
}

float implicit_triangle_wave_even_positive(float value, float period) {
  return implicit_triangle_wave_even(value, period) + period * 0.25;
}

vec2 implicit_triangle_wave_even_positive(vec2 value, vec2 period) {
  return vec2(
    implicit_triangle_wave_even_positive(value.x, period.x),
    implicit_triangle_wave_even_positive(value.y, period.y)
  );
}

vec3 implicit_triangle_wave_even_positive(vec3 value, vec3 period) {
  return vec3(
    implicit_triangle_wave_even_positive(value.x, period.x),
    implicit_triangle_wave_even_positive(value.y, period.y),
    implicit_triangle_wave_even_positive(value.z, period.z)
  );
}

float implicit_triangle_wave_odd(float value, float period) {
  return implicit_triangle_wave_even(value - period * 0.5, period);
}

vec2 implicit_triangle_wave_odd(vec2 value, vec2 period) {
  return vec2(
    implicit_triangle_wave_odd(value.x, period.x),
    implicit_triangle_wave_odd(value.y, period.y)
  );
}

vec3 implicit_triangle_wave_odd(vec3 value, vec3 period) {
  return vec3(
    implicit_triangle_wave_odd(value.x, period.x),
    implicit_triangle_wave_odd(value.y, period.y),
    implicit_triangle_wave_odd(value.z, period.z)
  );
}

float implicit_triangle_wave_odd_positive(float value, float period) {
  return implicit_triangle_wave_odd(value, period) + period * 0.25;
}

vec2 implicit_triangle_wave_odd_positive(vec2 value, vec2 period) {
  return vec2(
    implicit_triangle_wave_odd_positive(value.x, period.x),
    implicit_triangle_wave_odd_positive(value.y, period.y)
  );
}

vec3 implicit_triangle_wave_odd_positive(vec3 value, vec3 period) {
  return vec3(
    implicit_triangle_wave_odd_positive(value.x, period.x),
    implicit_triangle_wave_odd_positive(value.y, period.y),
    implicit_triangle_wave_odd_positive(value.z, period.z)
  );
}

vec2 implicit_repeat_centered(vec2 p, vec2 period) {
  return mod(p + period * 0.5, period) - period * 0.5;
}

vec3 implicit_repeat_centered(vec3 p, vec3 period) {
  return mod(p + period * 0.5, period) - period * 0.5;
}

float implicit_intersect_sharp(float a, float b) {
  return max(a, b);
}

float implicit_union_sharp(float a, float b) {
  return min(a, b);
}

float implicit_intersect_round(float a, float b, float radius) {
  float k = max(radius, 0.0);
  vec2 q = max(vec2(a, b) + k, 0.0);
  return min(-k, max(a, b)) + length(q);
}

float implicit_union_round(float a, float b, float radius) {
  return -implicit_intersect_round(-a, -b, radius);
}

float implicit_intersect_chamfer(float a, float b, float radius) {
  return max(max(a, b), (a + b + radius) * 0.7071067811865476);
}

float implicit_union_chamfer(float a, float b, float radius) {
  return -implicit_intersect_chamfer(-a, -b, radius);
}

float implicit_intersect_exp(float a, float b, float radius) {
  float k = max(radius, 1.0e-6) * 0.5;
  return k * log(exp(a / k) + exp(b / k));
}

float implicit_union_exp(float a, float b, float radius) {
  return -implicit_intersect_exp(-a, -b, radius);
}

float implicit_intersect_lp_norm(float a, float b, float radius, float normPower) {
  float k = max(radius, 0.0);
  float p = max(normPower, 1.0e-6);
  vec2 q = max(vec2(a, b) + k, 0.0);
  return min(-k, max(a, b)) + pow(pow(q.x, p) + pow(q.y, p), 1.0 / p);
}

float implicit_union_lp_norm(float a, float b, float radius, float normPower) {
  return -implicit_intersect_lp_norm(-a, -b, radius, normPower);
}

float implicit_intersect_rvachev(float a, float b, float radius) {
  float sharp = max(a, b);
  float k = max(radius, 0.0);
  if (k <= 0.0) {
    return sharp;
  }
  float r0 = a + b - sqrt(a * a + b * b);
  float t = clamp((sharp + k) / k, 0.0, 1.0);
  float s = t * t * (3.0 - 2.0 * t);
  return sharp < -k ? sharp : mix(sharp, r0, s);
}

float implicit_union_rvachev(float a, float b, float radius) {
  return -implicit_intersect_rvachev(-a, -b, radius);
}

float implicit_plane2(vec2 p, vec2 origin, vec2 normal) {
  vec2 n = normalize(normal);
  return dot(p - origin, n);
}

float implicit_line_segment2(vec2 p, vec2 a, vec2 b) {
  vec2 segment = b - a;
  float segmentLengthSq = dot(segment, segment);
  if (segmentLengthSq < 1.0e-12) {
    return length(p - a);
  }
  float t = clamp(dot(p - a, segment) / segmentLengthSq, 0.0, 1.0);
  return length(p - (a + t * segment));
}

float implicit_sphere(vec3 p, vec3 center, float radius) {
  return length(p - center) - radius;
}

float implicit_box_centered(vec3 p, vec3 size, vec3 center) {
  vec3 q = abs(p - center) - size * 0.5;
  return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0);
}

float implicit_plane(vec3 p, vec3 origin, vec3 normal) {
  vec3 n = normalize(normal);
  return dot(p - origin, n);
}

float implicit_line_segment(vec3 p, vec3 a, vec3 b) {
  vec3 segment = b - a;
  float segmentLengthSq = dot(segment, segment);
  if (segmentLengthSq < 1.0e-12) {
    return length(p - a);
  }
  float t = clamp(dot(p - a, segment) / segmentLengthSq, 0.0, 1.0);
  return length(p - (a + t * segment));
}

float implicit_torus(vec3 p, float majorRadius, float minorRadius) {
  vec2 q = vec2(length(p.xy) - majorRadius, p.z);
  return length(q) - minorRadius;
}

float implicit_axis(vec3 p, vec3 origin, vec3 direction) {
  float directionLength = length(direction);
  if (directionLength < 1.0e-12) {
    return length(p - origin);
  }
  vec3 axis = direction / directionLength;
  vec3 toPoint = p - origin;
  return length(toPoint - dot(toPoint, axis) * axis);
}

float implicit_cylinder(vec3 p, vec3 origin, vec3 direction, float radius) {
  return implicit_axis(p, origin, direction) - radius;
}

float implicit_cylinder_capped(vec3 p, vec3 a, vec3 b, float radius) {
  vec3 axis = b - a;
  float side = implicit_cylinder(p, a, axis, radius);
  float capA = -implicit_plane(p, a, axis);
  float capB = implicit_plane(p, b, axis);
  return max(side, max(capA, capB));
}

float implicit_capsule(vec3 p, vec3 a, vec3 b, float radius) {
  return implicit_line_segment(p, a, b) - radius;
}

float implicit_cone_capsule(vec3 p, vec3 a, vec3 b, float radiusA, float radiusB) {
  vec3 axis = b - a;
  float axisLengthSq = dot(axis, axis);
  if (axisLengthSq < 1.0e-12) {
    return implicit_sphere(p, a, radiusA);
  }
  float t = clamp(dot(p - a, axis) / axisLengthSq, 0.0, 1.0);
  float radius = mix(radiusA, radiusB, t);
  return length(p - (a + t * axis)) - radius;
}

float implicit_cone(vec3 p, vec3 apex, vec3 direction, float halfAngle) {
  float directionLength = length(direction);
  if (directionLength < 1.0e-12) {
    return length(p - apex);
  }
  vec3 axis = direction / directionLength;
  vec3 toPoint = p - apex;
  float axial = dot(toPoint, axis);
  float perpendicular = length(toPoint - axial * axis);
  return perpendicular - axial * tan(halfAngle);
}

float implicit_cone_capped(vec3 p, vec3 a, vec3 b, float radiusA, float radiusB) {
  vec3 axis = b - a;
  float axisLength = length(axis);
  if (axisLength < 1.0e-12) {
    return implicit_sphere(p, a, radiusA);
  }
  float halfAngle = atan(abs(radiusB - radiusA), axisLength);
  float coneDistance = radiusA < radiusB
    ? implicit_cone(p, a, axis, halfAngle) - radiusA
    : implicit_cone(p, b, -axis, halfAngle) - radiusB;
  float capA = -implicit_plane(p, a, axis);
  float capB = implicit_plane(p, b, axis);
  return max(coneDistance, max(capA, capB));
}

float implicit_shell(float distanceValue, float thickness, float bias) {
  float halfThickness = thickness * 0.5;
  return abs(distanceValue + bias * halfThickness) - halfThickness;
}

vec3 implicit_rotate_axis(vec3 p, vec3 origin, vec3 direction, float angle) {
  vec3 k = normalize(direction);
  vec3 local = p - origin;
  float c = cos(angle);
  float s = sin(angle);
  return origin + local * c + cross(k, local) * s + k * dot(k, local) * (1.0 - c);
}

vec3 implicit_remap_cylindrical(vec3 p, float circumference) {
  float radial = length(p.xy);
  float theta = atan(p.y, p.x);
  return vec3(radial, theta * (circumference / 6.283185307179586), p.z);
}

float implicit_tpms_gyroid(vec3 p, vec3 period, vec3 drop) {
  vec3 xyz = p * (6.283185307179586 / period);
  vec3 yzx = xyz.yzx;
  float field = dot(drop, sin(xyz) * cos(yzx));
  return field * (period.x + period.y + period.z) / 18.0;
}

float implicit_tpms_schwarz(vec3 p, vec3 period, vec3 drop, float gyroidBlend) {
  vec3 xyz = p * (6.283185307179586 / period);
  vec3 yzx = xyz.yzx;
  vec3 mixTerm = vec3(-(1.0 - gyroidBlend)) + sin(xyz) * gyroidBlend;
  float field = dot(drop, cos(yzx) * mixTerm);
  return field * (period.x + period.y + period.z) / 36.0;
}

float implicit_tpms_diamond(vec3 p, vec3 period, vec3 drop, float gyroidBlend) {
  vec3 xyz = p * (6.283185307179586 / period);
  vec3 yzx = xyz.yzx;
  vec3 zxy = xyz.zxy;
  vec3 sinXyz = sin(xyz);
  vec3 cosYzx = cos(yzx);
  vec3 cosZxy = cos(zxy);
  float blendFactor = 1.0 - gyroidBlend;
  float term1 = blendFactor * sinXyz.x * sinXyz.y * sinXyz.z;
  float term2 = dot(drop, sinXyz * cosYzx * (cosZxy * blendFactor + vec3(gyroidBlend)));
  return (term1 + term2) * (period.x + period.y + period.z) / (6.0 * 2.8284271247461903 * 2.0);
}

float implicit_tpms_lidinoid(vec3 p, vec3 period, vec3 drop, float gyroidBlend) {
  vec3 xyz = p * (6.283185307179586 / period);
  vec3 yzx = xyz.yzx;
  vec3 zxy = xyz.zxy;
  vec3 cos2Xyz = cos(2.0 * xyz);
  vec3 cos2Yzx = cos2Xyz.yzx;
  float blendFactor = 1.0 - gyroidBlend;
  float term1 = dot(drop, sin(zxy) * cos(yzx) * (sin(2.0 * xyz) * blendFactor + vec3(gyroidBlend)));
  float term2 = blendFactor * dot(cos2Xyz, cos2Yzx);
  return (term1 - term2) * (period.x + period.y + period.z) / 72.0;
}

float implicit_tpms_neovius(vec3 p, vec3 period, vec3 drop, float schwarzBlend) {
  vec3 xyz = p * (6.283185307179586 / period);
  vec3 cosDrop = cos(xyz) * drop;
  float term1 = -dot(cosDrop, vec3(1.0));
  float term2 = (1.0 - schwarzBlend) * (4.0 / 3.0) * cosDrop.x * cosDrop.y * cosDrop.z;
  return (term1 - term2) * (period.x + period.y + period.z) / (6.0 * (26.0 / 3.0));
}

float implicit_tpms_split_p(vec3 p, vec3 period, float lidinoidBlend, float gyroidOctave, float schwarzOctave) {
  vec3 xyz = p * (6.283185307179586 / period);
  vec3 yzx = xyz.yzx;
  vec3 zxy = xyz.zxy;
  vec3 sin2Xyz = sin(2.0 * xyz);
  vec3 cos2Xyz = cos(2.0 * xyz);
  float term1 = -lidinoidBlend * dot(sin2Xyz * cos(yzx) * sin(zxy), vec3(1.0));
  float term2 = gyroidOctave * dot(sin2Xyz * cos2Xyz, vec3(1.0));
  float term3 = schwarzOctave * dot(cos2Xyz, vec3(1.0));
  return (term1 + term2 + term3) * (period.x + period.y + period.z) / 36.0;
}

float implicit_tpms_iwp(vec3 p, vec3 period, vec3 drop) {
  vec3 xyz = p * (6.283185307179586 / period);
  vec3 yzx = xyz.yzx;
  float term1 = 2.0 * dot(drop * cos(xyz) * cos(yzx), vec3(1.0));
  float term2 = dot(cos(2.0 * xyz), vec3(1.0));
  return (term1 - term2) * (period.x + period.y + period.z) / 48.0;
}

float implicit_cubic_grid(vec3 p, vec3 size) {
  vec3 d = implicit_triangle_wave_even_positive(p, size);
  return min(d.x, min(d.y, d.z));
}

float implicit_square_honeycomb(vec3 p, vec2 size) {
  vec2 d = implicit_triangle_wave_even_positive(p.xy, size);
  return min(d.x, d.y);
}

float implicit_square_honeycomb_reinforced(vec3 p, vec2 size, float rotation, float rotation2, float hasRotation2) {
  vec2 pxy = p.xy;
  vec2 grid = implicit_triangle_wave_even_positive(pxy, size);
  float squareGrid = min(grid.x, grid.y);
  vec2 repeated = implicit_repeat_centered(pxy, size);
  float angle = 3.141592653589793 * rotation;
  float diagonal = abs(implicit_plane2(repeated, vec2(0.0), vec2(cos(angle), sin(angle))));
  if (hasRotation2 > 0.5) {
    float angle2 = 3.141592653589793 * rotation2;
    float diagonal2 = abs(implicit_plane2(repeated, vec2(0.0), vec2(cos(angle2), sin(angle2))));
    diagonal = min(diagonal, diagonal2);
  }
  return min(squareGrid, diagonal);
}

float implicit_square_diagonal_honeycomb(vec3 p, vec2 size) {
  vec2 period = vec2(size.x + size.y);
  vec2 repeated = implicit_repeat_centered(p.xy, period);
  float positive = abs(implicit_plane2(repeated, vec2(0.0), vec2(size.y, size.x)));
  float negative = abs(implicit_plane2(repeated, vec2(0.0), vec2(size.y, -size.x)));
  return min(positive, negative);
}

float implicit_octet_honeycomb(vec3 p, vec2 size) {
  vec2 pxy = p.xy;
  float square = implicit_square_honeycomb(p, size);
  vec2 oddGrid = implicit_triangle_wave_odd_positive(pxy, size);
  float planeGrid = min(oddGrid.x, oddGrid.y);
  float diagonalPeriod = length(size) * 0.5;
  vec2 rotated = vec2((pxy.x + pxy.y) / 1.4142135623730951, (pxy.x - pxy.y) / 1.4142135623730951);
  vec2 diagonal = implicit_triangle_wave_odd_positive(rotated, vec2(diagonalPeriod));
  return min(min(square, planeGrid), min(diagonal.x, diagonal.y));
}

float implicit_hexagonal_honeycomb(vec3 p, vec2 size, float setback) {
  vec2 pxy = p.xy;
  vec2 halfSize = size * 0.5;
  vec2 quarterSize = size * 0.25;
  vec2 starCenter = vec2(0.0, (1.0 - setback) * halfSize.y);
  vec2 transition = vec2(halfSize.x, setback * halfSize.y);
  vec2 folded = abs(implicit_repeat_centered(pxy, size));
  vec2 reflected = vec2(folded.x - halfSize.x, halfSize.y - folded.y);

  float foldedStar = min(
    implicit_line_segment2(folded, starCenter, vec2(0.0, size.y)),
    min(
      implicit_line_segment2(folded, starCenter, transition),
      implicit_line_segment2(folded, starCenter, vec2(-transition.x, transition.y))
    )
  );
  float reflectedStar = min(
    implicit_line_segment2(reflected, starCenter, vec2(0.0, size.y)),
    min(
      implicit_line_segment2(reflected, starCenter, transition),
      implicit_line_segment2(reflected, starCenter, vec2(-transition.x, transition.y))
    )
  );
  return folded.x < quarterSize.x ? foldedStar : reflectedStar;
}

float implicit_triangular_honeycomb(vec3 p, vec2 size) {
  vec2 folded = abs(implicit_repeat_centered(p.xy, size));
  vec2 halfSize = size * 0.5;
  vec2 quarterSize = size * 0.25;
  vec2 normalH = vec2(0.0, 1.0);
  vec2 normalP60 = normalize(vec2(size.y, size.x));
  vec2 normalN60 = normalize(vec2(size.y, -size.x));
  float foldedStar = min(
    abs(dot(folded, normalH)),
    min(abs(dot(folded, normalP60)), abs(dot(folded, normalN60)))
  );
  vec2 shifted = folded - halfSize;
  float shiftedStar = min(
    abs(dot(shifted, normalH)),
    min(abs(dot(shifted, normalP60)), abs(dot(shifted, normalN60)))
  );
  return folded.y < quarterSize.y ? foldedStar : shiftedStar;
}`;

export function implicitCadFragmentShader(model) {
  const maxSteps = Math.max(16, Math.min(Math.floor(finiteNumber(model.maxSteps, 192)), 768));
  const uniforms = model.uniforms && typeof model.uniforms === "object" ? model.uniforms : {};
  const customUniformDeclarations = implicitCadUniformDeclarations(uniforms);
  const glslSource = normalizeImplicitCadGlslFloatLiterals(model.glslSource || model.distanceSource);
  const hasColorFunction = /\bvec3\s+color\s*\(\s*vec3\s+\w+\s*,\s*vec3\s+\w+\s*\)/.test(glslSource);
  return `
precision highp float;

uniform vec2 uResolution;
uniform vec3 uCameraPosition;
uniform mat4 uCameraWorld;
uniform mat4 uProjectionInverse;
uniform vec3 uBoundsMin;
uniform vec3 uBoundsMax;
uniform vec3 uSurfaceColor;
uniform vec3 uBackgroundColor;
uniform vec3 uBackgroundColorA;
uniform vec3 uBackgroundColorB;
uniform float uBackgroundMode;
uniform float uBackgroundAngle;
uniform float uBackgroundAlpha;
uniform float uPaintBackground;
uniform float uOrthographic;
uniform float uUseProceduralColor;
uniform float uHitEpsilon;
uniform float uNormalEpsilon;
uniform float uMaxDistance;
uniform float uStepScale;
uniform float uMaxStep;
uniform float uStepBudget;
uniform float uShadowStrength;
uniform float uAmbientOcclusionStrength;
uniform float uRimStrength;
uniform float uExposure;
uniform vec3 uHemiSky;
uniform vec3 uHemiGround;
uniform vec3 uAmbientLight;
uniform vec3 uKeyColor;
uniform vec3 uKeyDir;
uniform vec3 uFillColor;
uniform vec3 uFillDir;
uniform vec3 uBounceColor;
uniform vec3 uBounceDir;
uniform vec3 uRimColor;
uniform float uFloorEnabled;
uniform float uFloorShadowOpacity;
uniform float uFloorZ;
uniform vec2 uFloorCenter;
uniform float uFloorFadeRadius;
${customUniformDeclarations}
varying vec2 vUv;

const int IMPLICIT_MAX_STEPS = ${maxSteps};

${IMPLICIT_CAD_GLSL_LIBRARY}

${glslSource}

float implicit_distance(vec3 p) {
  return sdf(p);
}

vec3 implicit_color(vec3 p, vec3 normal) {
  ${hasColorFunction ? "return clamp(color(p, normal), vec3(0.0), vec3(1.0));" : "return vec3(1.0);"}
}

float implicit_scene_sdf(vec3 p) {
  return implicit_distance(p);
}

vec2 implicit_ray_slab(float origin, float direction, float boundsMin, float boundsMax) {
  if (abs(direction) < 1.0e-8) {
    return origin < boundsMin || origin > boundsMax
      ? vec2(1.0, -1.0)
      : vec2(-1.0e20, 1.0e20);
  }
  float invDirection = 1.0 / direction;
  float nearPlane = (boundsMin - origin) * invDirection;
  float farPlane = (boundsMax - origin) * invDirection;
  return vec2(min(nearPlane, farPlane), max(nearPlane, farPlane));
}

vec2 implicit_ray_bounds(vec3 origin, vec3 direction, vec3 boundsMin, vec3 boundsMax) {
  vec2 x = implicit_ray_slab(origin.x, direction.x, boundsMin.x, boundsMax.x);
  vec2 y = implicit_ray_slab(origin.y, direction.y, boundsMin.y, boundsMax.y);
  vec2 z = implicit_ray_slab(origin.z, direction.z, boundsMin.z, boundsMax.z);
  float tMin = max(max(x.x, y.x), z.x);
  float tMax = min(min(x.y, y.y), z.y);
  return vec2(tMin, tMax);
}

vec3 implicit_estimate_normal(vec3 p) {
  float e = uNormalEpsilon;
  vec2 k = vec2(1.0, -1.0);
  return normalize(
    k.xyy * implicit_scene_sdf(p + k.xyy * e) +
    k.yyx * implicit_scene_sdf(p + k.yyx * e) +
    k.yxy * implicit_scene_sdf(p + k.yxy * e) +
    k.xxx * implicit_scene_sdf(p + k.xxx * e)
  );
}

float implicit_ambient_occlusion(vec3 p, vec3 normal) {
  float occlusion = 0.0;
  float scale = 1.0;
  for (int sampleIndex = 1; sampleIndex <= 5; sampleIndex += 1) {
    float distanceAlongNormal = 0.018 * float(sampleIndex) * uMaxDistance;
    float sampled = implicit_scene_sdf(p + normal * distanceAlongNormal);
    occlusion += (distanceAlongNormal - sampled) * scale;
    scale *= 0.58;
  }
  // Gentler floor than a typical raymarcher: the mesh viewer has no SSAO, so
  // heavy AO reads as "implicit models render darker".
  return clamp(1.0 - 0.045 * occlusion, 0.62, 1.0);
}

float implicit_soft_shadow(vec3 origin, vec3 direction, float maxDistance) {
  // Tight penumbra and a higher floor keep self-shadowing close to the mesh
  // viewer's crisp PCF shadows instead of dimming broad surface areas.
  float shadow = 1.0;
  float t = uHitEpsilon * 8.0;
  for (int shadowStep = 0; shadowStep < 28; shadowStep += 1) {
    if (t >= maxDistance) {
      break;
    }
    float h = implicit_scene_sdf(origin + direction * t);
    if (h < uHitEpsilon) {
      return 0.32;
    }
    shadow = min(shadow, 22.0 * h / t);
    t += clamp(h, uHitEpsilon * 3.0, maxDistance * 0.08);
  }
  return clamp(shadow, 0.32, 1.0);
}

vec3 implicit_srgb_to_linear(vec3 c) {
  c = clamp(c, vec3(0.0), vec3(1.0));
  vec3 low = c / 12.92;
  vec3 high = pow((c + 0.055) / 1.055, vec3(2.4));
  return mix(low, high, step(vec3(0.04045), c));
}

vec3 implicit_linear_to_srgb(vec3 c) {
  c = clamp(c, vec3(0.0), vec3(1.0));
  vec3 low = c * 12.92;
  vec3 high = 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055;
  return mix(low, high, step(vec3(0.0031308), c));
}

// THREE.js ACESFilmicToneMapping port so implicit shading matches the mesh
// viewer's renderer output transform.
vec3 implicit_rrt_odt_fit(vec3 v) {
  vec3 a = v * (v + 0.0245786) - 0.000090537;
  vec3 b = v * (0.983729 * v + 0.4329510) + 0.238081;
  return a / b;
}

vec3 implicit_aces_tone_map(vec3 color) {
  const mat3 acesInput = mat3(
    vec3(0.59719, 0.07600, 0.02840),
    vec3(0.35458, 0.90834, 0.13383),
    vec3(0.04823, 0.01566, 0.83777)
  );
  const mat3 acesOutput = mat3(
    vec3(1.60475, -0.10208, -0.00327),
    vec3(-0.53108, 1.10813, -0.07276),
    vec3(-0.07367, -0.00605, 1.07602)
  );
  color *= 1.0 / 0.6;
  color = acesInput * color;
  color = implicit_rrt_odt_fit(color);
  color = acesOutput * color;
  return clamp(color, vec3(0.0), vec3(1.0));
}

// Sharper than implicit_soft_shadow so the stage shadow stays a tight contact
// shadow like the mesh viewer's PCF shadow map instead of a broad blob.
float implicit_floor_shadow(vec3 origin, vec3 direction, float maxDistance) {
  float shadow = 1.0;
  float t = uHitEpsilon * 8.0;
  for (int shadowStep = 0; shadowStep < 32; shadowStep += 1) {
    if (t >= maxDistance) {
      break;
    }
    float h = implicit_scene_sdf(origin + direction * t);
    if (h < uHitEpsilon) {
      return 0.0;
    }
    shadow = min(shadow, 30.0 * h / t);
    t += clamp(h, uHitEpsilon * 3.0, maxDistance * 0.05);
  }
  return clamp(shadow, 0.0, 1.0);
}

// How much a ray that misses the model is darkened by the stage-floor shadow,
// matching the mesh viewer's shadow-catcher plane under the part. 0 = unshadowed.
float implicit_floor_shadow_strength(vec3 rayOrigin, vec3 rayDirection) {
  float shadowStrength = clamp(uShadowStrength, 0.0, 1.0);
  if (uFloorEnabled < 0.5 || shadowStrength < 0.001 || rayDirection.z > -1.0e-5) {
    return 0.0;
  }
  float tFloor = (uFloorZ - rayOrigin.z) / rayDirection.z;
  if (tFloor <= 0.0) {
    return 0.0;
  }
  vec3 floorPoint = rayOrigin + rayDirection * tFloor;
  float fade = 1.0 - smoothstep(uFloorFadeRadius * 0.5, uFloorFadeRadius, length(floorPoint.xy - uFloorCenter));
  if (fade < 0.002) {
    return 0.0;
  }
  vec3 shadowOrigin = vec3(floorPoint.xy, uFloorZ + max(uHitEpsilon * 6.0, uFloorFadeRadius * 0.0001));
  float lit = implicit_floor_shadow(shadowOrigin, uKeyDir, uFloorFadeRadius * 1.5);
  float occlusion = clamp(1.0 - lit, 0.0, 1.0);
  return occlusion * fade * clamp(uFloorShadowOpacity, 0.0, 1.0) * shadowStrength;
}

// A miss either paints this pass's own background (standalone renderers: the
// snapshot CLI and renderImplicitCadToDataUrl) or leaves the pixel to whatever
// is already in the framebuffer (the CAD Viewer, where the shared scene draws
// the themed background, grid and stage floor and this pass composites over
// them). In the composited case the shadow is emitted as black-with-alpha, so
// ordinary blending darkens the floor underneath exactly as multiplying the
// background used to.
vec4 implicit_miss_color(vec3 backgroundColor, vec3 rayOrigin, vec3 rayDirection) {
  float strength = implicit_floor_shadow_strength(rayOrigin, rayDirection);
  if (uPaintBackground > 0.5) {
    return vec4(backgroundColor * (1.0 - strength), uBackgroundAlpha);
  }
  return vec4(0.0, 0.0, 0.0, strength);
}

vec3 implicit_background_color(vec2 uv) {
  if (uBackgroundMode < 0.5) {
    return uBackgroundColor;
  }
  // NOTE: this backdrop only paints in HEADLESS/standalone implicit renders. In the viewer
  // the raymarch pass composites over the shared stage, so the on-screen backdrop comes
  // from cadjs/lib/viewer/stageTheme.js and these ramps are not what you are looking at.
  // The two do NOT agree: the canvas path ramps linearly between stops (radial 0.1 -> 0.75
  // of the texture width), this one uses a smoothstep over 0..0.72. See the theme
  // conformance section of viewer/docs/render-types.md before changing either.
  if (uBackgroundMode < 1.5) {
    vec2 direction = normalize(vec2(cos(uBackgroundAngle), sin(uBackgroundAngle)));
    float t = dot(uv - vec2(0.5), direction) * 0.7071067811865476 + 0.5;
    return mix(uBackgroundColorA, uBackgroundColorB, clamp(t, 0.0, 1.0));
  }
  float radial = smoothstep(0.0, 0.72, length(uv - vec2(0.5)));
  return mix(uBackgroundColorA, uBackgroundColorB, radial);
}

// Perspective and orthographic are opposite constructions, and the difference is the
// whole reason an implicit could not render under an ortho camera: a pinhole fans ONE
// origin into per-pixel directions, while a parallel projection shares ONE direction
// across per-pixel origins. Feeding an ortho projection matrix to the pinhole path
// yields garbage directions, and the model vanishes.
struct ImplicitRay {
  vec3 origin;
  vec3 direction;
};

ImplicitRay implicit_camera_ray(vec2 uv) {
  vec2 ndc = uv * 2.0 - 1.0;
  vec4 clip = vec4(ndc, -1.0, 1.0);
  vec4 view = uProjectionInverse * clip;
  ImplicitRay ray;
  if (uOrthographic > 0.5) {
    // Unproject to a point on the near plane, then march along the camera's forward
    // axis: every ray is parallel, offset across the image plane.
    vec3 viewPoint = view.xyz / max(abs(view.w), 1.0e-6);
    ray.origin = (uCameraWorld * vec4(viewPoint.xy, viewPoint.z, 1.0)).xyz;
    ray.direction = normalize(-uCameraWorld[2].xyz);
    return ray;
  }
  ray.origin = uCameraPosition;
  ray.direction = normalize((uCameraWorld * vec4(view.xy, -1.0, 0.0)).xyz);
  return ray;
}

void main() {
  vec2 screenUv = gl_FragCoord.xy / uResolution;
  vec3 backgroundColor = implicit_background_color(screenUv);
  ImplicitRay cameraRay = implicit_camera_ray(screenUv);
  vec3 rayOrigin = cameraRay.origin;
  vec3 rayDirection = cameraRay.direction;
  vec2 boundsHit = implicit_ray_bounds(rayOrigin, rayDirection, uBoundsMin, uBoundsMax);
  float t = max(boundsHit.x, 0.0);
  float tEnd = min(boundsHit.y, uMaxDistance);
  if (boundsHit.x > boundsHit.y || tEnd < 0.0) {
    gl_FragColor = implicit_miss_color(backgroundColor, rayOrigin, rayDirection);
    return;
  }

  bool hit = false;
  float previousT = t;
  vec3 p = rayOrigin;
  for (int stepIndex = 0; stepIndex < IMPLICIT_MAX_STEPS; stepIndex += 1) {
    if (float(stepIndex) >= uStepBudget) {
      break;
    }
    previousT = t;
    p = rayOrigin + rayDirection * t;
    float distanceValue = implicit_scene_sdf(p);
    float hitEpsilon = max(uHitEpsilon, t * 0.00028);
    if (distanceValue < hitEpsilon) {
      hit = true;
      break;
    }
    float stepDistance = max(distanceValue * uStepScale, uHitEpsilon * 0.25);
    t += min(stepDistance, uMaxStep);
    if (t > tEnd) {
      break;
    }
  }

  if (!hit) {
    gl_FragColor = implicit_miss_color(backgroundColor, rayOrigin, rayDirection);
    return;
  }

  float refineNear = previousT;
  float refineFar = t;
  for (int refineIndex = 0; refineIndex < 5; refineIndex += 1) {
    float mid = (refineNear + refineFar) * 0.5;
    float midDistance = implicit_scene_sdf(rayOrigin + rayDirection * mid);
    if (midDistance > 0.0) {
      refineNear = mid;
    } else {
      refineFar = mid;
    }
  }
  p = rayOrigin + rayDirection * refineFar;
  vec3 normal = implicit_estimate_normal(p);
  vec3 viewDirection = normalize(rayOrigin - p);
  float shadowStrength = clamp(uShadowStrength, 0.0, 1.0);
  float shadow = 1.0;
  if (shadowStrength > 0.001) {
    shadow = mix(
      1.0,
      implicit_soft_shadow(p + normal * uHitEpsilon * 4.0, uKeyDir, uMaxDistance * 0.55),
      shadowStrength
    );
  }
  float ambientOcclusionStrength = clamp(uAmbientOcclusionStrength, 0.0, 1.0);
  float ao = 1.0;
  if (ambientOcclusionStrength > 0.001) {
    ao = mix(1.0, implicit_ambient_occlusion(p, normal), ambientOcclusionStrength);
  }
  vec3 sourceColor = clamp(implicit_color(p, normal), vec3(0.0), vec3(1.0));
  vec3 surfaceColor = implicit_srgb_to_linear(mix(uSurfaceColor, sourceColor, clamp(uUseProceduralColor, 0.0, 1.0)));
  // Match the mesh viewer's light rig: hemisphere + ambient indirect terms,
  // key/fill/bounce directional terms with a Lambert 1/pi factor, then the
  // same ACES filmic tone mapping and sRGB encode THREE.js applies.
  vec3 irradiance = (mix(uHemiGround, uHemiSky, normal.z * 0.5 + 0.5) + uAmbientLight) * ao;
  irradiance += uKeyColor * clamp(dot(normal, uKeyDir), 0.0, 1.0) * shadow;
  irradiance += uFillColor * clamp(dot(normal, uFillDir), 0.0, 1.0);
  irradiance += uBounceColor * clamp(dot(normal, uBounceDir), 0.0, 1.0);
  vec3 color = surfaceColor * irradiance * 0.3183098861837907;
  float rim = pow(1.0 - clamp(dot(normal, viewDirection), 0.0, 1.0), 2.4);
  color += uRimColor * rim * clamp(uRimStrength, 0.0, 1.0);
  color = implicit_aces_tone_map(color * uExposure);
  color = implicit_linear_to_srgb(color);
  gl_FragColor = vec4(color, 1.0);
}
`;
}

export function implicitCadModelShaderKey(model) {
  const normalized = normalizeImplicitCadModel(model);
  return [
    normalized.maxSteps,
    normalized.uniformSignature || "",
    normalized.glslSource
  ].join("\n---implicit-cad-shader-key---\n");
}

export function implicitCadVertexShader() {
  return `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;
}

export function createImplicitCadMaterial(THREE, model) {
  const normalized = normalizeImplicitCadModel(model);
  const customUniforms = Object.fromEntries(
    Object.entries(normalized.uniforms || {}).map(([name, uniform]) => [
      name,
      { value: threeUniformValue(THREE, uniform) }
    ])
  );
  const floorUserData = {};
  const floorBounds = implicitFloorBoundsForModel(normalized, floorUserData, { estimate: false });
  const material = new THREE.ShaderMaterial({
    name: "ImplicitCadRaymarchMaterial",
    depthTest: false,
    depthWrite: false,
    transparent: true,
    uniforms: {
      uResolution: { value: new THREE.Vector2(1, 1) },
      uCameraPosition: { value: new THREE.Vector3() },
      uCameraWorld: { value: new THREE.Matrix4() },
      uProjectionInverse: { value: new THREE.Matrix4() },
      uBoundsMin: { value: new THREE.Vector3(...normalized.bounds.min) },
      uBoundsMax: { value: new THREE.Vector3(...normalized.bounds.max) },
      uSurfaceColor: { value: new THREE.Vector3(...hexToRgb01(normalized.material.color, "#f4f4f5")) },
      uBackgroundColor: { value: new THREE.Vector3(...hexToRgb01(normalized.background.color, DEFAULT_BACKGROUND)) },
      uBackgroundColorA: { value: new THREE.Vector3(...hexToRgb01(normalized.background.color, DEFAULT_BACKGROUND)) },
      uBackgroundColorB: { value: new THREE.Vector3(...hexToRgb01(normalized.background.color, DEFAULT_BACKGROUND)) },
      uBackgroundMode: { value: 0 },
      uBackgroundAngle: { value: Math.PI },
      uBackgroundAlpha: { value: normalized.background.transparent ? 0 : 1 },
      // Standalone renderers paint their own background; the CAD Viewer turns
      // this off so the shared themed background/grid/stage show through.
      uPaintBackground: { value: 1 },
      // Perspective unless a host says otherwise, so snapshot/export are unchanged.
      uOrthographic: { value: 0 },
      uUseProceduralColor: { value: normalized.colorSource ? 1 : 0 },
      uHitEpsilon: { value: normalized.epsilon },
      uNormalEpsilon: { value: normalized.normalEpsilon },
      uMaxDistance: { value: normalized.maxDistance },
      uStepScale: { value: normalized.stepScale },
      uMaxStep: { value: normalized.maxStep },
      uStepBudget: { value: normalized.maxSteps },
      uShadowStrength: { value: 1 },
      uAmbientOcclusionStrength: { value: 1 },
      uRimStrength: { value: 1 },
      uExposure: { value: DEFAULT_LIGHTING_RIG.toneMappingExposure },
      uHemiSky: { value: new THREE.Vector3(...linearLightRgb(DEFAULT_LIGHTING_RIG.hemisphere.skyColor, DEFAULT_LIGHTING_RIG.hemisphere.intensity, "#ffffff")) },
      uHemiGround: { value: new THREE.Vector3(...linearLightRgb(DEFAULT_LIGHTING_RIG.hemisphere.groundColor, DEFAULT_LIGHTING_RIG.hemisphere.intensity, "#d6e2ee")) },
      uAmbientLight: { value: new THREE.Vector3(...linearLightRgb(DEFAULT_LIGHTING_RIG.ambient.color, DEFAULT_LIGHTING_RIG.ambient.intensity, "#ffffff")) },
      uKeyColor: { value: new THREE.Vector3(...linearLightRgb(DEFAULT_LIGHTING_RIG.directional.color, DEFAULT_LIGHTING_RIG.directional.intensity, "#ffffff")) },
      uKeyDir: { value: new THREE.Vector3(...lightDirectionFromPosition(DEFAULT_LIGHTING_RIG.directional.position, DEFAULT_LIGHTING_RIG.directional.position)) },
      uFillColor: { value: new THREE.Vector3(...linearLightRgb(DEFAULT_LIGHTING_RIG.spot.color, DEFAULT_LIGHTING_RIG.spot.intensity, "#f4fbff")) },
      uFillDir: { value: new THREE.Vector3(...lightDirectionFromPosition(DEFAULT_LIGHTING_RIG.spot.position, DEFAULT_LIGHTING_RIG.spot.position)) },
      uBounceColor: { value: new THREE.Vector3(...linearLightRgb(DEFAULT_LIGHTING_RIG.point.color, DEFAULT_LIGHTING_RIG.point.intensity, "#ffe2ba")) },
      uBounceDir: { value: new THREE.Vector3(...lightDirectionFromPosition(DEFAULT_LIGHTING_RIG.point.position, DEFAULT_LIGHTING_RIG.point.position)) },
      uRimColor: { value: new THREE.Vector3(...linearLightRgb(DEFAULT_LIGHTING_RIG.rimColor, DEFAULT_LIGHTING_RIG.rimIntensity, "#6db6e8")) },
      uFloorEnabled: { value: 1 },
      uFloorShadowOpacity: { value: DEFAULT_LIGHTING_RIG.floorShadowOpacity },
      uFloorZ: { value: floorBounds.min[2] },
      uFloorCenter: { value: new THREE.Vector2(
        (floorBounds.min[0] + floorBounds.max[0]) / 2,
        (floorBounds.min[1] + floorBounds.max[1]) / 2
      ) },
      uFloorFadeRadius: { value: implicitFloorFadeRadius(floorBounds) },
      ...customUniforms,
    },
    vertexShader: implicitCadVertexShader(),
    fragmentShader: implicitCadFragmentShader(normalized),
  });
  Object.assign(material.userData, floorUserData);
  return material;
}

export function updateImplicitCadModelUniforms(THREE, material, model) {
  if (!material?.uniforms) {
    return;
  }
  const normalized = normalizeImplicitCadModel(model);
  if (material.uniforms.uBoundsMin) {
    material.uniforms.uBoundsMin.value.set(...normalized.bounds.min);
  }
  if (material.uniforms.uBoundsMax) {
    material.uniforms.uBoundsMax.value.set(...normalized.bounds.max);
  }
  if (material.uniforms.uMaxDistance) {
    material.uniforms.uMaxDistance.value = normalized.maxDistance;
  }
  applyImplicitFloorUniforms(
    material,
    implicitFloorBoundsForModel(normalized, material.userData, { estimate: false })
  );
  for (const [name, uniform] of Object.entries(normalized.uniforms || {})) {
    updateThreeUniformValue(THREE, material.uniforms[name], uniform);
  }
}

export function resolveImplicitCadThemeSettings({
  theme = DEFAULT_THEME_ID,
  themeSettings = null
} = {}) {
  if (themeSettings && typeof themeSettings === "object" && !Array.isArray(themeSettings)) {
    return normalizeThemeSettings(themeSettings);
  }
  return resolveThemeSettings({ theme: theme || DEFAULT_THEME_ID }, {
    defaultThemeId: DEFAULT_THEME_ID
  });
}

function applyImplicitLightingUniforms(uniforms, normalizedTheme) {
  const lighting = normalizedTheme?.lighting || {};
  const rig = DEFAULT_LIGHTING_RIG;
  if (uniforms.uExposure) {
    uniforms.uExposure.value = Math.max(finiteNumber(lighting.toneMappingExposure, rig.toneMappingExposure), 0.05);
  }
  const hemisphere = lighting.hemisphere || rig.hemisphere;
  const hemiIntensity = hemisphere.enabled === false ? 0 : finiteNumber(hemisphere.intensity, rig.hemisphere.intensity);
  if (uniforms.uHemiSky) {
    uniforms.uHemiSky.value.set(...linearLightRgb(hemisphere.skyColor, hemiIntensity, rig.hemisphere.skyColor));
  }
  if (uniforms.uHemiGround) {
    uniforms.uHemiGround.value.set(...linearLightRgb(hemisphere.groundColor, hemiIntensity, rig.hemisphere.groundColor));
  }
  if (uniforms.uAmbientLight) {
    const ambient = lighting.ambient || rig.ambient;
    const ambientIntensity = ambient.enabled === false ? 0 : finiteNumber(ambient.intensity, rig.ambient.intensity);
    const ambientRgb = linearLightRgb(ambient.color, ambientIntensity, rig.ambient.color);
    // The mesh stage adds an environment map; fold its contribution into a
    // white ambient term so overall brightness tracks the mesh viewer.
    const environment = normalizedTheme?.environment || {};
    const environmentAmbient = environment.enabled === false
      ? 0
      : Math.max(finiteNumber(environment.intensity, 0), 0) * rig.environmentAmbientScale;
    uniforms.uAmbientLight.value.set(
      ambientRgb[0] + environmentAmbient,
      ambientRgb[1] + environmentAmbient,
      ambientRgb[2] + environmentAmbient
    );
  }
  const directional = lighting.directional || rig.directional;
  if (uniforms.uKeyColor) {
    const keyIntensity = directional.enabled === false ? 0 : finiteNumber(directional.intensity, rig.directional.intensity);
    uniforms.uKeyColor.value.set(...linearLightRgb(directional.color, keyIntensity, rig.directional.color));
  }
  if (uniforms.uKeyDir) {
    uniforms.uKeyDir.value.set(...lightDirectionFromPosition(directional.position, rig.directional.position));
  }
  // Fill is the theme's FILL light. This used to read `lighting.spot`, so every theme's
  // fill settings were ignored and the spot was doing double duty.
  const fill = lighting.fill || DEFAULT_FILL_LIGHT_SETTINGS;
  if (uniforms.uFillColor) {
    const fillIntensity = fill.enabled === false ? 0 : finiteNumber(fill.intensity, DEFAULT_FILL_LIGHT_SETTINGS.intensity);
    uniforms.uFillColor.value.set(...linearLightRgb(fill.color, fillIntensity, DEFAULT_FILL_LIGHT_SETTINGS.color));
  }
  if (uniforms.uFillDir) {
    uniforms.uFillDir.value.set(...lightDirectionFromPosition(fill.position, DEFAULT_FILL_LIGHT_SETTINGS.position));
  }
  const point = lighting.point || rig.point;
  if (uniforms.uBounceColor) {
    const pointIntensity = point.enabled === false ? 0 : finiteNumber(point.intensity, rig.point.intensity);
    uniforms.uBounceColor.value.set(...linearLightRgb(point.color, pointIntensity, rig.point.color));
  }
  if (uniforms.uBounceDir) {
    uniforms.uBounceDir.value.set(...lightDirectionFromPosition(point.position, rig.point.position));
  }
  // Rim was pinned to the built-in rig, so switching theme moved the mesh renderer's rim
  // and left the raymarcher's where it was — the single most visible way the two diverged.
  const rim = lighting.rim || DEFAULT_RIM_LIGHT_SETTINGS;
  if (uniforms.uRimColor) {
    const rimIntensity = rim.enabled === false ? 0 : finiteNumber(rim.intensity, DEFAULT_RIM_LIGHT_SETTINGS.intensity);
    uniforms.uRimColor.value.set(...linearLightRgb(rim.color, rimIntensity, DEFAULT_RIM_LIGHT_SETTINGS.color));
  }
  const floor = normalizedTheme?.floor || {};
  if (uniforms.uFloorEnabled) {
    uniforms.uFloorEnabled.value = floor.mode === "none" ? 0 : 1;
  }
  if (uniforms.uFloorShadowOpacity) {
    uniforms.uFloorShadowOpacity.value = Math.min(
      Math.max(finiteNumber(floor.shadowOpacity, rig.floorShadowOpacity), 0),
      1
    );
  }
}

export function updateImplicitCadThemeUniforms(THREE, material, model, {
  theme = DEFAULT_THEME_ID,
  themeSettings = null,
  graphicsSettings = null,
  forceTransparent = false
} = {}) {
  const uniforms = material?.uniforms;
  if (!uniforms) {
    return resolveImplicitCadThemeSettings({ theme, themeSettings });
  }
  const normalizedTheme = resolveImplicitCadThemeSettings({ theme, themeSettings });
  const normalizedGraphics = normalizeImplicitGraphicsSettings(graphicsSettings);
  const materialSettings = normalizedTheme.materials || {};
  const sourceColor = readSourceColor(THREE, model?.material?.color);
  uniforms.uUseProceduralColor.value = model?.colorSource &&
    normalizedGraphics.modelColors &&
    materialSettings.overrideSourceColors !== true
    ? 1
    : 0;
  const surfaceColor = resolveSourceBaseColor(THREE, {
    sourceColor: materialSettings.overrideSourceColors === true ? null : sourceColor,
    materialSettings,
    fallbackColor: materialSettings.defaultColor || BASE_VIEWER_THEME.surface,
    forceFill: materialSettings.overrideSourceColors === true
  });
  uniforms.uSurfaceColor.value.set(...colorToRgb01(surfaceColor));
  applyImplicitLightingUniforms(uniforms, normalizedTheme);

  if (model?.background?.color) {
    const backgroundRgb = hexToRgb01(model.background.color, BASE_VIEWER_THEME.sceneBackground);
    uniforms.uBackgroundColor.value.set(...backgroundRgb);
    uniforms.uBackgroundColorA.value.set(...backgroundRgb);
    uniforms.uBackgroundColorB.value.set(...backgroundRgb);
    uniforms.uBackgroundMode.value = 0;
    uniforms.uBackgroundAngle.value = Math.PI;
    uniforms.uBackgroundAlpha.value = forceTransparent || model.background.transparent ? 0 : 1;
    return normalizedTheme;
  }

  const backgroundSettings = normalizedTheme.background || {};
  const backgroundMode = normalizeBackgroundMode(backgroundSettings.type);
  const solidColor = backgroundSettings.solidColor || getViewerThemeValue(normalizedTheme, "sceneBackground", BASE_VIEWER_THEME.sceneBackground);
  const colorA = backgroundMode === 1
    ? backgroundSettings.linearStart
    : backgroundMode === 2
      ? backgroundSettings.radialInner
      : solidColor;
  const colorB = backgroundMode === 1
    ? backgroundSettings.linearEnd
    : backgroundMode === 2
      ? backgroundSettings.radialOuter
      : solidColor;
  uniforms.uBackgroundColor.value.set(...hexToRgb01(solidColor, BASE_VIEWER_THEME.sceneBackground));
  uniforms.uBackgroundColorA.value.set(...hexToRgb01(colorA, solidColor));
  uniforms.uBackgroundColorB.value.set(...hexToRgb01(colorB, solidColor));
  uniforms.uBackgroundMode.value = backgroundMode;
  uniforms.uBackgroundAngle.value = degreesToRadians(backgroundSettings.linearAngle, 180);
  uniforms.uBackgroundAlpha.value = forceTransparent || backgroundSettings.type === "transparent" ? 0 : 1;
  return normalizedTheme;
}

export function updateImplicitCadGraphicsUniforms(material, model, graphicsSettings = null) {
  const uniforms = material?.uniforms;
  if (!uniforms) {
    return normalizeImplicitGraphicsSettings(graphicsSettings);
  }
  const settings = normalizeImplicitGraphicsSettings(graphicsSettings);
  const detail = Math.max(settings.detail, 0.001);
  const detailRoot = Math.sqrt(detail);
  if (uniforms.uHitEpsilon) {
    uniforms.uHitEpsilon.value = Math.max(finiteNumber(model?.epsilon, 0.001) / detailRoot, 1e-6);
  }
  if (uniforms.uNormalEpsilon) {
    uniforms.uNormalEpsilon.value = Math.max(
      finiteNumber(model?.normalEpsilon, 0.001) * settings.normalSmoothing / detailRoot,
      1e-6
    );
  }
  if (uniforms.uStepScale) {
    uniforms.uStepScale.value = Math.max(finiteNumber(model?.stepScale, 1) / detail, 0.01);
  }
  if (uniforms.uMaxStep) {
    uniforms.uMaxStep.value = Math.max(finiteNumber(model?.maxStep, 1) / detail, 1e-6);
  }
  if (uniforms.uStepBudget) {
    const maxSteps = Math.max(Math.floor(finiteNumber(model?.maxSteps, 192)), 1);
    const requestedStepBudget = Math.floor(finiteNumber(graphicsSettings?.stepBudget, maxSteps));
    uniforms.uStepBudget.value = Math.max(Math.min(requestedStepBudget, maxSteps), 1);
  }
  if (uniforms.uShadowStrength) {
    uniforms.uShadowStrength.value = settings.shadows ? 1 : 0;
  }
  if (uniforms.uAmbientOcclusionStrength) {
    uniforms.uAmbientOcclusionStrength.value = settings.ambientOcclusion ? 1 : 0;
  }
  if (uniforms.uRimStrength) {
    uniforms.uRimStrength.value = settings.rimLight ? 1 : 0;
  }
  return settings;
}

// Composited mode: the pass stops painting its own background and emits the
// stage-floor shadow as black-with-alpha instead, so a host that already draws a
// themed background, grid and floor (the CAD Viewer) shows through and gets the
// shadow blended onto its own floor. Standalone renderers leave this alone.
export function setImplicitCadBackgroundPainting(material, paintBackground) {
  const uniform = material?.uniforms?.uPaintBackground;
  if (!uniform) {
    return false;
  }
  uniform.value = paintBackground === false ? 0 : 1;
  return true;
}

export function updateImplicitCadMaterialUniforms(material, camera, width, height) {
  camera.updateMatrixWorld(true);
  if (material.uniforms.uOrthographic) {
    material.uniforms.uOrthographic.value = camera.isOrthographicCamera ? 1 : 0;
  }
  material.uniforms.uResolution.value.set(Math.max(width, 1), Math.max(height, 1));
  material.uniforms.uCameraPosition.value.copy(camera.position);
  material.uniforms.uCameraWorld.value.copy(camera.matrixWorld);
  material.uniforms.uProjectionInverse.value.copy(camera.projectionMatrixInverse);
}

export function createImplicitCadFullscreenScene(THREE, model) {
  const scene = new THREE.Scene();
  const normalized = normalizeImplicitCadModel(model);
  const material = createImplicitCadMaterial(THREE, model);
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  quad.frustumCulled = false;
  scene.add(quad);
  return {
    scene,
    material,
    quad,
    shaderKey: implicitCadModelShaderKey(normalized),
    dispose() {
      quad.geometry?.dispose?.();
      material.dispose?.();
    },
  };
}

export function configureImplicitCadCamera(THREE, model, width, height, cameraSpec = "iso", options = {}) {
  const cameraState = implicitCadCameraState(model, cameraSpec, {
    ...options,
    width,
    height
  });
  const camera = new THREE.PerspectiveCamera(
    cameraState.fov,
    Math.max(width, 1) / Math.max(height, 1),
    Math.max(model.radius * 0.002, 0.001),
    Math.max(model.radius * 12, 1000)
  );
  camera.position.set(...cameraState.position);
  camera.up.set(...cameraState.up);
  camera.zoom = Math.max(finiteNumber(cameraState.zoom, 1), 0.05);
  camera.lookAt(new THREE.Vector3(...cameraState.target));
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return camera;
}

export async function renderImplicitCadToDataUrl(THREE, modelValue, {
  width = 1200,
  height = 900,
  camera = "iso",
  theme = DEFAULT_THEME_ID,
  graphics = null,
  render = {},
} = {}) {
  const model = normalizeImplicitCadModel(modelValue);
  const themeSettings = resolveImplicitCadThemeSettings({ theme });
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(1);
  renderer.setSize(width, height, false);
  const background = model.background?.color
    ? model.background
    : themeSettings.background || {};
  const transparent = Boolean(render.transparent || background.transparent || background.type === "transparent");
  const backgroundColor = hexToRgb01(background.color || background.solidColor, DEFAULT_BACKGROUND);
  renderer.setClearColor(new THREE.Color(...backgroundColor), transparent ? 0 : 1);
  // Configure the camera before creating the scene: the camera fit warms the
  // frame-bounds estimate cache that floor placement reads at material
  // creation time.
  const captureCamera = configureImplicitCadCamera(THREE, model, width, height, camera, {
    zoom: render.zoom,
    frameMargin: render.frameMargin,
  });
  const { scene, material, dispose } = createImplicitCadFullscreenScene(THREE, model);
  updateImplicitCadThemeUniforms(THREE, material, model, {
    themeSettings,
    graphicsSettings: graphics,
    forceTransparent: transparent
  });
  updateImplicitCadGraphicsUniforms(material, model, graphics);
  updateImplicitCadMaterialUniforms(material, captureCamera, width, height);
  const screenCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  renderer.render(scene, screenCamera);
  const dataUrl = renderer.domElement.toDataURL("image/png");
  dispose();
  renderer.dispose();
  return dataUrl;
}

export const implicitModelShaderKey = implicitCadModelShaderKey;
export const implicitVertexShader = implicitCadVertexShader;
export const implicitFragmentShader = implicitCadFragmentShader;
export const createImplicitMaterial = createImplicitCadMaterial;
export const updateImplicitModelUniforms = updateImplicitCadModelUniforms;
export const resolveImplicitThemeSettings = resolveImplicitCadThemeSettings;
export const updateImplicitThemeUniforms = updateImplicitCadThemeUniforms;
export const updateImplicitGraphicsUniforms = updateImplicitCadGraphicsUniforms;
export const updateImplicitMaterialUniforms = updateImplicitCadMaterialUniforms;
export const createImplicitFullscreenScene = createImplicitCadFullscreenScene;
export const configureImplicitCamera = configureImplicitCadCamera;
export const renderImplicitToDataUrl = renderImplicitCadToDataUrl;

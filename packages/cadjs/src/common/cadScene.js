import {
  normalizeThemeSettings,
  resolveThemeDisplayEdgeSettings,
  resolveThemeFillColor
} from "./themeSettings.js";
import {
  CAD_DISPLAY_MODE,
  displayModeAllowsEdges,
  displayModeForcesEdges,
  displayModeIsWireframe,
  displayModeShowsThroughEdges,
  displayModeSurfaceOpacity,
  displayModeUsesUnlitSurfaces,
  normalizeDisplayMode
} from "./displaySettings.js";
import {
  createDisplayEdgeObject,
  syncScreenSpaceLineMaterialResolution
} from "./renderEdges.js";
import { resolveStepModuleFeatures } from "./stepModule.js";
import {
  applyStepModuleEffectsToRecords,
  buildPartTransformMatrix,
  buildStepModuleContext,
  createStepModuleEffectsApi,
  displayTransformForPart
} from "./stepModuleEffects.js";
import { axisIndex, normalizeStepClipSettings } from "../lib/viewer/clipPlane.js";
import {
  clampSceneModelRadius,
  getSceneScaleSettings,
  normalizeSceneScaleMode,
  VIEWER_SCENE_SCALE
} from "../lib/viewer/sceneScale.js";

export { CAD_DISPLAY_MODE, normalizeDisplayMode };

export const CAD_SCENE_SCALE = VIEWER_SCENE_SCALE;

const CAD_EDGE_OPACITY = 0.84;
const CAD_EDGE_THRESHOLD_DEG = 16;
const REFERENCE_HOVER_COLOR = "#8dc5ff";
const REFERENCE_SELECTED_COLOR = "#4f9dff";
const PART_HOVER_OPACITY_BOOST = 0.08;
const PART_SELECTED_OPACITY_BOOST = 0.12;
const PART_HIGHLIGHT_SURFACE_RENDER_ORDER = 23;
const PART_HIGHLIGHT_EDGE_RENDER_ORDER = 26;
const FOCUSED_DIMMED_SURFACE_OPACITY = 0.035;
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
const MODEL_PART_ID = "__model__";
const DEFAULT_THEME = Object.freeze({
  surface: "#f4f4f5",
  surfaceRoughness: 0.92,
  surfaceMetalness: 0.03,
  surfaceClearcoat: 0,
  surfaceClearcoatRoughness: 0.6,
  edge: "#18181b",
  edgeThickness: 1,
  edgeOpacity: CAD_EDGE_OPACITY
});
const SURFACE_EDGE_BARYCENTRIC_ATTRIBUTE = "_cad_edge_barycentric";
const SURFACE_EDGE_CLASS_ATTRIBUTE = "_cad_edge_class";
const SURFACE_EDGE_CLASS_IDS = Object.freeze(["feature", "tangent", "seam", "degenerate"]);
const SURFACE_EDGE_CLASS_DEFAULTS = Object.freeze({
  feature: Object.freeze({ thickness: 1.15, opacity: 1 }),
  tangent: Object.freeze({ thickness: 1.15, opacity: 0.5 }),
  seam: Object.freeze({ thickness: 1.15, opacity: 0.85 }),
  degenerate: Object.freeze({ thickness: 0, opacity: 1 })
});

const meshGeometryCache = new WeakMap();

function cacheOwnerForMeshData(meshData) {
  const geometrySource = meshData?.geometrySource;
  return geometrySource && typeof geometrySource === "object" ? geometrySource : meshData;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toNumber(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function isNumericArray(value, stride = 1) {
  return (
    (Array.isArray(value) || ArrayBuffer.isView(value)) &&
    value.length >= stride &&
    value.length % stride === 0
  );
}

function normalizeBoolean(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

export function normalizeCadSceneScale(value) {
  return normalizeSceneScaleMode(value);
}

export function boundsFromVertices(vertices) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index + 2 < (vertices?.length || 0); index += 3) {
    const x = Number(vertices[index]);
    const y = Number(vertices[index + 1]);
    const z = Number(vertices[index + 2]);
    if (![x, y, z].every(Number.isFinite)) {
      continue;
    }
    min[0] = Math.min(min[0], x);
    min[1] = Math.min(min[1], y);
    min[2] = Math.min(min[2], z);
    max[0] = Math.max(max[0], x);
    max[1] = Math.max(max[1], y);
    max[2] = Math.max(max[2], z);
  }
  if (!min.every(Number.isFinite) || !max.every(Number.isFinite)) {
    return { min: [0, 0, 0], max: [1, 1, 1] };
  }
  return { min, max };
}

export function centerAndRadiusFromBounds(THREE, bounds, scale = CAD_SCENE_SCALE.CAD) {
  const sceneScale = normalizeCadSceneScale(scale);
  const settings = getSceneScaleSettings(sceneScale);
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : [1, 1, 1];
  const center = new THREE.Vector3(
    (toNumber(min[0]) + toNumber(max[0], 1)) / 2,
    (toNumber(min[1]) + toNumber(max[1], 1)) / 2,
    (toNumber(min[2]) + toNumber(max[2], 1)) / 2
  );
  const size = new THREE.Vector3(
    Math.max(toNumber(max[0], 1) - toNumber(min[0]), settings.minModelRadius),
    Math.max(toNumber(max[1], 1) - toNumber(min[1]), settings.minModelRadius),
    Math.max(toNumber(max[2], 1) - toNumber(min[2]), settings.minModelRadius)
  );
  return {
    center,
    size,
    radius: clampSceneModelRadius(size.length() / 2, sceneScale)
  };
}

function cacheForMeshData(meshData) {
  const cacheOwner = cacheOwnerForMeshData(meshData);
  let cache = meshGeometryCache.get(cacheOwner);
  if (!cache) {
    cache = {
      whole: new Map(),
      part: new Map(),
      edge: new Map()
    };
    meshGeometryCache.set(cacheOwner, cache);
  }
  return cache;
}

function cacheKey(parts) {
  return parts.map((part, index) => String(part?.id || part?.occurrenceId || `part:${index}`)).join("|");
}

function markCachedGeometry(geometry) {
  if (geometry) {
    geometry.userData = {
      ...(geometry.userData || {}),
      cadSceneCachedGeometry: true
    };
  }
  return geometry;
}

function disposeMaterial(material) {
  const materials = Array.isArray(material) ? material : [material];
  for (const item of materials) {
    item?.map?.dispose?.();
    item?.alphaMap?.dispose?.();
    item?.dispose?.();
  }
}

function disposeSceneObject(object, { disposeCachedGeometry = false } = {}) {
  if (!object) {
    return;
  }
  while (object.children?.length) {
    disposeSceneObject(object.children[0], { disposeCachedGeometry });
  }
  object.parent?.remove(object);
  if (typeof object.userData?.beforeDispose === "function") {
    object.userData.beforeDispose(object);
    delete object.userData.beforeDispose;
  }
  if (disposeCachedGeometry || object.geometry?.userData?.cadSceneCachedGeometry !== true) {
    object.geometry?.dispose?.();
  }
  disposeMaterial(object.material);
}

function clearGroup(group, options = {}) {
  while (group?.children?.length) {
    disposeSceneObject(group.children[0], options);
  }
}

function applyGeometryNormals(THREE, geometry, normals, recomputeNormals) {
  const hasNormals = isNumericArray(normals, 3);
  if (!recomputeNormals && hasNormals) {
    geometry.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(normals), 3));
    return;
  }
  geometry.computeVertexNormals();
}

function setSurfaceEdgeAttributes(THREE, geometry, meshData, vertexOffset = 0, vertexCount = 0) {
  const barycentric = meshData?.surfaceEdgeBarycentric;
  const edgeClass = meshData?.surfaceEdgeClass;
  const componentOffset = Math.max(0, Math.floor(Number(vertexOffset) || 0)) * 3;
  const componentCount = Math.max(0, Math.floor(Number(vertexCount) || 0)) * 3;
  if (
    !(barycentric instanceof Float32Array) ||
    !(edgeClass instanceof Uint8Array) ||
    componentCount <= 0 ||
    barycentric.length < componentOffset + componentCount ||
    edgeClass.length < componentOffset + componentCount
  ) {
    return;
  }
  geometry.setAttribute(
    SURFACE_EDGE_BARYCENTRIC_ATTRIBUTE,
    new THREE.BufferAttribute(barycentric.slice(componentOffset, componentOffset + componentCount), 3)
  );
  geometry.setAttribute(
    SURFACE_EDGE_CLASS_ATTRIBUTE,
    new THREE.BufferAttribute(edgeClass.slice(componentOffset, componentOffset + componentCount), 3)
  );
}

function geometryHasSurfaceEdgeAttributes(geometry) {
  const barycentric = geometry?.getAttribute?.(SURFACE_EDGE_BARYCENTRIC_ATTRIBUTE);
  const edgeClass = geometry?.getAttribute?.(SURFACE_EDGE_CLASS_ATTRIBUTE);
  return Boolean(
    barycentric?.itemSize === 3 &&
    edgeClass?.itemSize === 3 &&
    barycentric.count > 0 &&
    barycentric.count === edgeClass.count
  );
}

function readSourceColor(THREE, value) {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) {
    return null;
  }
  const expanded = normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`
    : normalized;
  return new THREE.Color(expanded);
}

function shapeSourceColor(THREE, sourceColor, materialSettings = {}, { applyTint = true } = {}) {
  const shaped = (sourceColor || new THREE.Color("#ffffff")).clone();
  const tintStrength = clamp(Number(materialSettings.tintStrength) || 0, 0, 1);
  if (applyTint && tintStrength > 0) {
    const tintColor = new THREE.Color(materialSettings.defaultColor || materialSettings.tintColor || "#ffffff");
    if (materialSettings.tintMode === "blend") {
      shaped.lerp(tintColor, tintStrength);
    } else {
      shaped.lerp(shaped.clone().multiply(tintColor), tintStrength);
    }
  }

  const saturation = clamp(Number(materialSettings.saturation) || 1, 0, 2.5);
  if (Math.abs(saturation - 1) > 1e-4) {
    const hsl = {};
    shaped.getHSL(hsl);
    shaped.setHSL(hsl.h, clamp(hsl.s * saturation, 0, 1), hsl.l);
  }

  const contrast = clamp(Number(materialSettings.contrast) || 1, 0, 2.5);
  const brightness = clamp(Number(materialSettings.brightness) || 1, 0, 2);
  shaped.r = clamp(((shaped.r - 0.5) * contrast + 0.5) * brightness, 0, 1);
  shaped.g = clamp(((shaped.g - 0.5) * contrast + 0.5) * brightness, 0, 1);
  shaped.b = clamp(((shaped.b - 0.5) * contrast + 0.5) * brightness, 0, 1);
  return shaped;
}

function shapeSourceColorBuffer(THREE, colors, materialSettings = {}) {
  if (!isNumericArray(colors, 3)) {
    return null;
  }
  const shapedColors = new Float32Array(colors.length);
  const color = new THREE.Color();
  for (let index = 0; index + 2 < colors.length; index += 3) {
    color.setRGB(
      clamp(Number(colors[index]) || 0, 0, 1),
      clamp(Number(colors[index + 1]) || 0, 0, 1),
      clamp(Number(colors[index + 2]) || 0, 0, 1)
    );
    const shaped = shapeSourceColor(THREE, color, materialSettings);
    shapedColors[index] = shaped.r;
    shapedColors[index + 1] = shaped.g;
    shapedColors[index + 2] = shaped.b;
  }
  return shapedColors;
}

function shouldUseDisplayVertexColors(meshData) {
  return !!meshData?.has_source_colors && isNumericArray(meshData?.colors, 3);
}

function partUsesDisplayVertexColors(meshData, part) {
  if (!shouldUseDisplayVertexColors(meshData)) {
    return false;
  }
  if (part && Object.hasOwn(part, "hasSourceColors")) {
    return !!part.hasSourceColors;
  }
  return true;
}

function createMaterialFillColor(THREE, materialSettings = {}, fillIndex = 0) {
  return new THREE.Color(resolveThemeFillColor(materialSettings, fillIndex));
}

function resolveMaterialFillBaseColor(THREE, materialSettings = {}, fillIndex = 0) {
  return shapeSourceColor(
    THREE,
    createMaterialFillColor(THREE, materialSettings, fillIndex),
    materialSettings,
    { applyTint: false }
  );
}

function resolveSourceBaseColor(THREE, {
  hasVertexColors = false,
  sourceColor = null,
  materialSettings,
  fallbackColor = "#ffffff",
  fillIndex = 0,
  forceFill = false
}) {
  if (forceFill) {
    return resolveMaterialFillBaseColor(THREE, materialSettings, fillIndex);
  }
  if (hasVertexColors) {
    return new THREE.Color("#ffffff");
  }
  if (!sourceColor) {
    return resolveMaterialFillBaseColor(THREE, {
      ...materialSettings,
      defaultColor: fallbackColor || materialSettings?.defaultColor
    }, fillIndex);
  }
  return shapeSourceColor(THREE, sourceColor, materialSettings);
}

function surfaceEdgeClassSetting(edgeSettings = {}, classId) {
  const fallback = SURFACE_EDGE_CLASS_DEFAULTS[classId] || SURFACE_EDGE_CLASS_DEFAULTS.feature;
  const source = edgeSettings?.classes?.[classId] || {};
  return {
    thickness: clamp(
      Number.isFinite(Number(source.thickness)) ? Number(source.thickness) : fallback.thickness,
      0,
      6
    ),
    opacity: clamp(
      Number.isFinite(Number(source.opacity)) ? Number(source.opacity) : fallback.opacity,
      0,
      1
    )
  };
}

function addCadSurfaceEdgeShader(THREE, material, edgeSettings = {}, baseTheme = DEFAULT_THEME) {
  const classSettings = Object.fromEntries(
    SURFACE_EDGE_CLASS_IDS.map((classId) => [classId, surfaceEdgeClassSetting(edgeSettings, classId)])
  );
  const edgeColor = new THREE.Color(edgeSettings?.color || baseTheme?.edge || DEFAULT_THEME.edge);
  material.userData.cadSurfaceEdges = true;
  material.userData.cadSurfaceEdgeBaseColor = edgeColor.clone();
  material.userData.cadSurfaceEdgeColor = edgeColor.clone();
  material.userData.cadSurfaceEdgeBaseClassSettings = Object.fromEntries(
    Object.entries(classSettings).map(([classId, setting]) => [classId, { ...setting }])
  );
  material.extensions = {
    ...(material.extensions || {}),
    derivatives: true
  };
  material.onBeforeCompile = (shader) => {
    const activeEdgeColor = material.userData.cadSurfaceEdgeColor?.isColor
      ? material.userData.cadSurfaceEdgeColor
      : edgeColor;
    material.userData.cadSurfaceEdgeShader = shader;
    shader.uniforms.cadSurfaceEdgeColor = { value: activeEdgeColor.clone() };
    shader.uniforms.cadSurfaceFeatureThickness = { value: classSettings.feature.thickness };
    shader.uniforms.cadSurfaceTangentThickness = { value: classSettings.tangent.thickness };
    shader.uniforms.cadSurfaceSeamThickness = { value: classSettings.seam.thickness };
    shader.uniforms.cadSurfaceDegenerateThickness = { value: classSettings.degenerate.thickness };
    shader.uniforms.cadSurfaceFeatureOpacity = { value: classSettings.feature.opacity };
    shader.uniforms.cadSurfaceTangentOpacity = { value: classSettings.tangent.opacity };
    shader.uniforms.cadSurfaceSeamOpacity = { value: classSettings.seam.opacity };
    shader.uniforms.cadSurfaceDegenerateOpacity = { value: classSettings.degenerate.opacity };
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
attribute vec3 ${SURFACE_EDGE_BARYCENTRIC_ATTRIBUTE};
attribute vec3 ${SURFACE_EDGE_CLASS_ATTRIBUTE};
varying vec3 vCadSurfaceEdgeBarycentric;
varying vec3 vCadSurfaceEdgeClass;`
      )
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
vCadSurfaceEdgeBarycentric = ${SURFACE_EDGE_BARYCENTRIC_ATTRIBUTE};
vCadSurfaceEdgeClass = ${SURFACE_EDGE_CLASS_ATTRIBUTE};`
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
uniform vec3 cadSurfaceEdgeColor;
uniform float cadSurfaceFeatureThickness;
uniform float cadSurfaceTangentThickness;
uniform float cadSurfaceSeamThickness;
uniform float cadSurfaceDegenerateThickness;
uniform float cadSurfaceFeatureOpacity;
uniform float cadSurfaceTangentOpacity;
uniform float cadSurfaceSeamOpacity;
uniform float cadSurfaceDegenerateOpacity;
varying vec3 vCadSurfaceEdgeBarycentric;
varying vec3 vCadSurfaceEdgeClass;

float cadSurfaceEdgeThicknessFor(float classCode) {
  if (classCode < 0.5) {
    return 0.0;
  }
  if (abs(classCode - 2.0) < 0.5) {
    return cadSurfaceTangentThickness;
  }
  if (abs(classCode - 3.0) < 0.5) {
    return cadSurfaceSeamThickness;
  }
  if (abs(classCode - 4.0) < 0.5) {
    return cadSurfaceDegenerateThickness;
  }
  return cadSurfaceFeatureThickness;
}

float cadSurfaceEdgeOpacityFor(float classCode) {
  if (classCode < 0.5) {
    return 0.0;
  }
  if (abs(classCode - 2.0) < 0.5) {
    return cadSurfaceTangentOpacity;
  }
  if (abs(classCode - 3.0) < 0.5) {
    return cadSurfaceSeamOpacity;
  }
  if (abs(classCode - 4.0) < 0.5) {
    return cadSurfaceDegenerateOpacity;
  }
  return cadSurfaceFeatureOpacity;
}

float cadSurfaceEdgeCoverage(float barycentric, float classCode) {
  float thickness = cadSurfaceEdgeThicknessFor(classCode);
  float opacity = cadSurfaceEdgeOpacityFor(classCode);
  if (thickness <= 0.0 || opacity <= 0.0) {
    return 0.0;
  }
  float pixelDistance = barycentric / max(fwidth(barycentric), 1e-6);
  float halfWidth = max(thickness * 0.5, 0.001);
  float coverage = 1.0 - smoothstep(max(halfWidth - 0.75, 0.0), halfWidth + 0.75, pixelDistance);
  return clamp(coverage * opacity, 0.0, 1.0);
}

float cadSurfaceEdgeAlpha() {
  float edge0 = cadSurfaceEdgeCoverage(vCadSurfaceEdgeBarycentric.x, vCadSurfaceEdgeClass.x);
  float edge1 = cadSurfaceEdgeCoverage(vCadSurfaceEdgeBarycentric.y, vCadSurfaceEdgeClass.y);
  float edge2 = cadSurfaceEdgeCoverage(vCadSurfaceEdgeBarycentric.z, vCadSurfaceEdgeClass.z);
  return max(edge0, max(edge1, edge2));
}`
      )
      .replace(
        "#include <opaque_fragment>",
        `float cadSurfaceEdgeMix = cadSurfaceEdgeAlpha();
if (cadSurfaceEdgeMix > 0.0) {
  outgoingLight = mix(outgoingLight, cadSurfaceEdgeColor, cadSurfaceEdgeMix);
}
#include <opaque_fragment>`
      );
  };
  material.customProgramCacheKey = () => "cad-surface-edges-v1";
}

function createSurfaceMaterial(THREE, baseTheme, { color, useVertexColors = false, edgeSettings = null } = {}) {
  const opacity = Number.isFinite(Number(baseTheme?.surfaceOpacity))
    ? Number(baseTheme.surfaceOpacity)
    : 1;
  const material = new THREE.MeshPhysicalMaterial({
    color: color || baseTheme?.surface || DEFAULT_THEME.surface,
    roughness: Number.isFinite(Number(baseTheme?.surfaceRoughness)) ? Number(baseTheme.surfaceRoughness) : DEFAULT_THEME.surfaceRoughness,
    metalness: Number.isFinite(Number(baseTheme?.surfaceMetalness)) ? Number(baseTheme.surfaceMetalness) : DEFAULT_THEME.surfaceMetalness,
    clearcoat: Number.isFinite(Number(baseTheme?.surfaceClearcoat)) ? Number(baseTheme.surfaceClearcoat) : DEFAULT_THEME.surfaceClearcoat,
    clearcoatRoughness: Number.isFinite(Number(baseTheme?.surfaceClearcoatRoughness)) ? Number(baseTheme.surfaceClearcoatRoughness) : DEFAULT_THEME.surfaceClearcoatRoughness,
    side: THREE.DoubleSide,
    vertexColors: useVertexColors,
    transparent: opacity < 0.999,
    opacity,
    emissive: 0x000000,
    emissiveIntensity: 0,
    polygonOffset: false,
    polygonOffsetFactor: 0,
    polygonOffsetUnits: 0
  });
  if (edgeSettings?.enabled) {
    addCadSurfaceEdgeShader(THREE, material, edgeSettings, baseTheme);
  }
  return material;
}

function createWireframeSurfaceMaterial(THREE, materialSettings, fillIndex = 0) {
  return new THREE.MeshBasicMaterial({
    color: resolveThemeFillColor(materialSettings || {}, fillIndex),
    transparent: true,
    opacity: 0.035,
    depthWrite: false
  });
}

function createUnshadedSurfaceMaterial(THREE, { color, useVertexColors = false, opacity = 1 } = {}) {
  return new THREE.MeshBasicMaterial({
    color: color || DEFAULT_THEME.surface,
    side: THREE.DoubleSide,
    vertexColors: useVertexColors,
    transparent: opacity < 0.999,
    opacity,
    depthWrite: opacity >= 0.999
  });
}

function sourceColorForPart(THREE, part, meshData) {
  return readSourceColor(THREE, part?.color || meshData?.sourceColor);
}

function meshUsesPartSourceColors(meshData, parts) {
  const renderableParts = Array.isArray(parts) ? parts : [];
  const partColors = renderableParts
    .map((part) => String(part?.color || "").trim().toLowerCase())
    .filter(Boolean);
  if (!partColors.length) {
    return false;
  }
  return partColors.length !== renderableParts.length || new Set(partColors).size > 1;
}

function emptyLineGeometry(THREE) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(0), 3));
  return geometry;
}

function stablePartFillKey(part, index) {
  return [
    String(part?.occurrenceId || ""),
    String(part?.id || ""),
    String(part?.partSourcePath || part?.sourcePath || ""),
    String(part?.label || part?.name || ""),
    String(index).padStart(8, "0")
  ].join("\u0000");
}

export function buildPartFillIndexMap(parts = []) {
  return new Map(
    [...parts]
      .map((part, index) => ({ part, key: stablePartFillKey(part, index) }))
      .sort((left, right) => left.key.localeCompare(right.key))
      .map(({ part }, index) => [part, index])
  );
}

function geometryCacheEntry(THREE, meshData, key, createGeometry) {
  const cache = cacheForMeshData(meshData);
  const cached = cache.part.get(key) || cache.whole.get(key);
  if (cached) {
    return cached;
  }
  const entry = createGeometry();
  if (!entry?.geometry) {
    return null;
  }
  markCachedGeometry(entry.geometry);
  if (key === MODEL_PART_ID) {
    cache.whole.set(key, entry);
  } else {
    cache.part.set(key, entry);
  }
  return entry;
}

function buildPartGeometryEntry(THREE, meshData, part, recomputeNormals = false) {
  const partId = String(part?.id || part?.occurrenceId || "").trim();
  const key = partId || `${toNumber(part?.vertexOffset)}:${toNumber(part?.triangleOffset)}`;
  return geometryCacheEntry(THREE, meshData, key, () => {
    const vertexOffset = toNumber(part?.vertexOffset, 0);
    const vertexCount = toNumber(part?.vertexCount, 0);
    const triangleOffset = toNumber(part?.triangleOffset, 0);
    const triangleCount = toNumber(part?.triangleCount, 0);
    if (vertexCount <= 0 || triangleCount <= 0) {
      return null;
    }

    const positionStart = vertexOffset * 3;
    const positionEnd = positionStart + vertexCount * 3;
    const localVertices = meshData.vertices.slice(positionStart, positionEnd);
    const rawColors = partUsesDisplayVertexColors(meshData, part)
      ? new Float32Array(meshData.colors.slice(positionStart, positionEnd))
      : null;
    const localNormals = isNumericArray(meshData.normals, 3) ? meshData.normals.slice(positionStart, positionEnd) : null;
    const rawIndices = meshData.indices.slice(triangleOffset * 3, triangleOffset * 3 + triangleCount * 3);
    const localIndices = new Uint32Array(rawIndices.length);
    for (let index = 0; index < rawIndices.length; index += 1) {
      localIndices[index] = Math.max(0, Number(rawIndices[index]) - vertexOffset);
    }
    if (!localIndices.length) {
      return null;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(localVertices), 3));
    geometry.setIndex(new THREE.BufferAttribute(localIndices, 1));
    if (rawColors && rawColors.length === localVertices.length) {
      geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(rawColors), 3));
    }
    setSurfaceEdgeAttributes(THREE, geometry, meshData, vertexOffset, vertexCount);
    applyGeometryNormals(THREE, geometry, localNormals, recomputeNormals);
    geometry.computeBoundingSphere();
    return {
      geometry,
      rawColors
    };
  });
}

function buildWholeGeometryEntry(THREE, meshData, recomputeNormals = false) {
  return geometryCacheEntry(THREE, meshData, MODEL_PART_ID, () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(meshData.vertices || []), 3));
    geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(meshData.indices || []), 1));
    const rawColors = shouldUseDisplayVertexColors(meshData) && meshData.colors?.length === meshData.vertices?.length
      ? new Float32Array(meshData.colors)
      : null;
    if (rawColors) {
      geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(rawColors), 3));
    }
    setSurfaceEdgeAttributes(THREE, geometry, meshData, 0, Math.floor((meshData.vertices?.length || 0) / 3));
    applyGeometryNormals(THREE, geometry, meshData.normals, recomputeNormals);
    geometry.computeBoundingSphere();
    return {
      geometry,
      rawColors
    };
  });
}

function syncRecordVertexColors(THREE, record, materialSettings) {
  if (!record?.geometry || !record.rawColors || !record.hasVertexColors) {
    return;
  }
  const shapedColors = shapeSourceColorBuffer(THREE, record.rawColors, materialSettings);
  if (!shapedColors) {
    return;
  }
  const attribute = record.geometry.getAttribute("color");
  if (attribute?.array?.length === shapedColors.length) {
    attribute.array.set(shapedColors);
    attribute.needsUpdate = true;
    return;
  }
  record.geometry.setAttribute("color", new THREE.BufferAttribute(shapedColors, 3));
}

function buildEdgeGeometryFromIndices(THREE, vertices, edgeIndices) {
  if (!isNumericArray(vertices, 3) || !isNumericArray(edgeIndices, 2)) {
    return null;
  }
  const vertexCount = Math.floor(vertices.length / 3);
  const segmentCount = Math.floor(edgeIndices.length / 2);
  if (segmentCount <= 0) {
    return null;
  }
  const linePositions = new Float32Array(segmentCount * 6);
  let writeOffset = 0;
  for (let index = 0; index + 1 < edgeIndices.length; index += 2) {
    const a = Number(edgeIndices[index]);
    const b = Number(edgeIndices[index + 1]);
    if (!Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b < 0 || a >= vertexCount || b >= vertexCount) {
      continue;
    }
    const aOffset = a * 3;
    const bOffset = b * 3;
    linePositions[writeOffset] = Number(vertices[aOffset]);
    linePositions[writeOffset + 1] = Number(vertices[aOffset + 1]);
    linePositions[writeOffset + 2] = Number(vertices[aOffset + 2]);
    linePositions[writeOffset + 3] = Number(vertices[bOffset]);
    linePositions[writeOffset + 4] = Number(vertices[bOffset + 1]);
    linePositions[writeOffset + 5] = Number(vertices[bOffset + 2]);
    writeOffset += 6;
  }
  if (!writeOffset) {
    return null;
  }
  const geometry = new THREE.BufferGeometry();
  const packedPositions = writeOffset === linePositions.length ? linePositions : linePositions.subarray(0, writeOffset);
  geometry.setAttribute("position", new THREE.BufferAttribute(packedPositions, 3));
  return geometry;
}

function buildEdgeGeometry(THREE, meshData, part, sourceGeometry, displayMode, edgeSettings = {}) {
  void edgeSettings;
  const cache = cacheForMeshData(meshData);
  const partId = part ? String(part?.id || part?.occurrenceId || "").trim() : MODEL_PART_ID;
  const edgeKey = `${displayMode}:${partId || MODEL_PART_ID}`;
  const cached = cache.edge.get(edgeKey);
  if (cached) {
    return cached;
  }

  let geometry = null;
  if (displayModeIsWireframe(displayMode)) {
    geometry = new THREE.WireframeGeometry(sourceGeometry);
  } else if (part) {
    const edgeIndexOffset = toNumber(part?.edgeIndexOffset, 0);
    const edgeIndexCount = toNumber(part?.edgeIndexCount, 0);
    const hasExplicitPartEdges = edgeIndexCount >= 2 && isNumericArray(meshData?.edge_indices, 2);
    if (hasExplicitPartEdges) {
      const partEdgeIndices = typeof meshData.edge_indices.subarray === "function"
        ? meshData.edge_indices.subarray(edgeIndexOffset, edgeIndexOffset + edgeIndexCount)
        : meshData.edge_indices.slice(edgeIndexOffset, edgeIndexOffset + edgeIndexCount);
      geometry = buildEdgeGeometryFromIndices(THREE, meshData.vertices, partEdgeIndices);
    }
    geometry ||= new THREE.EdgesGeometry(sourceGeometry, CAD_EDGE_THRESHOLD_DEG);
  } else if (isNumericArray(meshData?.edge_indices, 2)) {
    geometry = buildEdgeGeometryFromIndices(THREE, meshData.vertices, meshData.edge_indices);
  }

  geometry ||= new THREE.EdgesGeometry(sourceGeometry, CAD_EDGE_THRESHOLD_DEG);
  if (!geometry.getAttribute("position")?.count) {
    geometry.dispose();
    geometry = emptyLineGeometry(THREE);
  }
  markCachedGeometry(geometry);
  cache.edge.set(edgeKey, geometry);
  return geometry;
}

function getEdgeThickness(edgeSettings = null, baseTheme = null) {
  const fallbackThickness = Number.isFinite(Number(baseTheme?.edgeThickness))
    ? Number(baseTheme.edgeThickness)
    : DEFAULT_THEME.edgeThickness;
  return Number.isFinite(Number(edgeSettings?.thickness))
    ? clamp(Number(edgeSettings.thickness), 0.5, 6)
    : fallbackThickness;
}

function syncLineMaterialOpacity(material, opacity) {
  if (!material) {
    return;
  }
  const nextOpacity = clamp(Number(opacity) || 0, 0, 1);
  const nextTransparent = nextOpacity < 0.999;
  material.opacity = nextOpacity;
  material.depthWrite = false;
  if (material.transparent !== nextTransparent) {
    material.transparent = nextTransparent;
    material.needsUpdate = true;
  }
}

function createDefaultEdgeObject(THREE, geometry, baseTheme, edgeSettings, partId, displayMode) {
  const wireframeMode = displayModeIsWireframe(displayMode);
  const depthTest = edgeSettings?.depthTest === false ? false : !wireframeMode;
  const material = new THREE.LineBasicMaterial({
    color: edgeSettings?.color || baseTheme?.edge || DEFAULT_THEME.edge,
    transparent: true,
    opacity: wireframeMode
      ? Math.max(toNumber(edgeSettings?.opacity, 0.92), 0.9)
      : toNumber(edgeSettings?.opacity, baseTheme?.edgeOpacity ?? CAD_EDGE_OPACITY),
    depthTest,
    depthWrite: false
  });
  const object = new THREE.LineSegments(geometry, material);
  object.userData.partId = partId;
  return { object, material };
}

function normalizeEdgeResult(result) {
  if (!result) {
    return { object: null, material: null };
  }
  const object = result.object || result.edgeMesh || result.mesh || result.line || null;
  return {
    object,
    material: result.material || result.edgeMaterial || object?.material || null
  };
}

function normalizeEdgeRendering(edgeRendering = null) {
  if (!edgeRendering || typeof edgeRendering !== "object") {
    return { mode: "basic" };
  }
  const mode = String(edgeRendering.mode || edgeRendering.type || "").trim().toLowerCase();
  return {
    ...edgeRendering,
    mode: mode === "screen-space" || mode === "screenspace" ? "screen-space" : "basic",
    wireframeEdgeColor: String(edgeRendering.wireframeEdgeColor || "").trim()
  };
}

function applyEdgeRenderingToRuntime(runtime, edgeRendering = {}) {
  runtime.edgeRendering = edgeRendering;
  for (const key of ["Line2", "LineGeometry", "LineSegments2", "LineSegmentsGeometry", "LineMaterial"]) {
    runtime[key] = edgeRendering[key] || edgeRendering.constructors?.[key] || null;
  }
}

function createSilhouetteMesh(THREE, geometry, edgeSettings, radius) {
  const offset = radius * clamp(toNumber(edgeSettings?.silhouetteScale, 0.004), 0, 0.04);
  if (!(offset > 0)) {
    return null;
  }
  const material = new THREE.ShaderMaterial({
    uniforms: {
      color: { value: new THREE.Color(edgeSettings?.color || DEFAULT_THEME.edge) },
      opacity: { value: clamp(toNumber(edgeSettings?.opacity, 0.9), 0, 1) },
      offset: { value: offset }
    },
    vertexShader: `
      uniform float offset;
      void main() {
        vec3 displaced = position + normal * offset;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 color;
      uniform float opacity;
      void main() {
        gl_FragColor = vec4(color, opacity);
      }
    `,
    side: THREE.BackSide,
    transparent: true,
    depthTest: true,
    depthWrite: false
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = -1;
  return mesh;
}

function shouldBuildSilhouette(edgeSettings, displayMode, settings = {}) {
  return (
    settings.silhouette !== false &&
    !displayModeIsWireframe(displayMode) &&
    edgeSettings.silhouette === true &&
    (edgeSettings.enabled === true || settings.silhouette === true)
  );
}

export function readBoundsCenter(THREE, bounds) {
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : min;
  return new THREE.Vector3(
    (toNumber(min[0]) + toNumber(max[0])) / 2,
    (toNumber(min[1]) + toNumber(max[1])) / 2,
    (toNumber(min[2]) + toNumber(max[2])) / 2
  );
}

function applyObjectMatrix(THREE, object3d, matrix) {
  if (!object3d || !(matrix instanceof THREE.Matrix4)) {
    return;
  }
  object3d.matrixAutoUpdate = false;
  const targetMatrix = object3d.matrix instanceof THREE.Matrix4 ? object3d.matrix : new THREE.Matrix4();
  targetMatrix.copy(matrix);
  object3d.matrix = targetMatrix;
  object3d.matrixWorldNeedsUpdate = true;
}

export function applyDisplayRecordTransform(THREE, record) {
  if (!record) {
    return;
  }
  const baseMatrix = buildPartTransformMatrix(THREE, record.baseTransform);
  const effectMatrix = record.effectMatrix instanceof THREE.Matrix4 ? record.effectMatrix.clone() : null;
  const combinedMatrix = effectMatrix ? effectMatrix.multiply(baseMatrix) : baseMatrix;
  applyObjectMatrix(THREE, record.mesh, combinedMatrix);
  applyObjectMatrix(THREE, record.edges, combinedMatrix);
  applyObjectMatrix(THREE, record.silhouette, combinedMatrix);
}

function safeColor(THREE, value, fallback = null) {
  const text = String(value || "").trim();
  if (!text) {
    return fallback;
  }
  try {
    return new THREE.Color(text);
  } catch {
    return fallback;
  }
}

export function applyMaterialSettingsToRecord(THREE, record, materialSettings, {
  baseTheme = DEFAULT_THEME,
  displayMode = CAD_DISPLAY_MODE.SOLID
} = {}) {
  if (!record?.material || !materialSettings) {
    return;
  }
  const wireframeMode = displayModeIsWireframe(displayMode);
  const forceFill = materialSettings.overrideSourceColors === true || wireframeMode;
  const hasVertexColors = !forceFill && !!record.hasVertexColors;
  record.useVertexColors = hasVertexColors;
  record.baseColor = resolveSourceBaseColor(THREE, {
    hasVertexColors,
    sourceColor: forceFill ? null : record.sourceColor || null,
    materialSettings,
    fallbackColor: materialSettings?.defaultColor || baseTheme?.surface || DEFAULT_THEME.surface,
    fillIndex: record.fillIndex || 0,
    forceFill: forceFill || !record.hasSourceColor
  });
  record.material.vertexColors = hasVertexColors;
  if (wireframeMode) {
    if (record.material.color && record.baseColor) {
      record.material.color.copy(record.baseColor);
    }
    record.baseOpacity = displayModeSurfaceOpacity(displayMode, 0.035);
    record.material.opacity = record.baseOpacity;
    record.material.transparent = true;
    record.material.depthWrite = false;
    record.material.needsUpdate = true;
    return;
  }
  syncRecordVertexColors(THREE, record, materialSettings);
  record.material.roughness = clamp(Number(materialSettings.roughness) || 0, 0, 1);
  record.material.metalness = clamp(Number(materialSettings.metalness) || 0, 0, 1);
  record.material.clearcoat = clamp(Number(materialSettings.clearcoat) || 0, 0, 1);
  record.material.clearcoatRoughness = clamp(Number(materialSettings.clearcoatRoughness) || 0, 0, 1);
  record.baseOpacity = clamp(displayModeSurfaceOpacity(displayMode, materialSettings.opacity), 0, 1);
  record.material.opacity = record.baseOpacity;
  record.material.transparent = record.baseOpacity < 0.999;
  record.material.depthWrite = displayMode === CAD_DISPLAY_MODE.TRANSPARENT ? false : record.baseOpacity >= 0.999;
  record.material.envMapIntensity = Math.max(Number(materialSettings.envMapIntensity) || 0, 0);
  if (record.material.color && record.baseColor) {
    record.material.color.copy(record.baseColor);
  }
  record.baseEmissiveIntensity = clamp(Number(materialSettings.emissiveIntensity) || 0, 0, 2);
  record.baseEmissiveColor = record.baseColor ? record.baseColor.clone() : null;
  if ("emissive" in record.material && record.material.emissive) {
    if (record.baseEmissiveColor && record.baseEmissiveIntensity > 0) {
      record.material.emissive.copy(record.baseEmissiveColor);
    } else {
      record.material.emissive.set(0x000000);
    }
    record.material.emissiveIntensity = record.baseEmissiveIntensity;
  }
  record.material.needsUpdate = true;
}

function normalizePartIdList(value) {
  return (Array.isArray(value) ? value : [value])
    .map((id) => String(id || "").trim())
    .filter(Boolean);
}

function baseObjectRenderOrder(record, object, fieldName) {
  if (!object) {
    return 0;
  }
  if (!Number.isFinite(Number(record[fieldName]))) {
    record[fieldName] = Number.isFinite(Number(object.renderOrder)) ? Number(object.renderOrder) : 0;
  }
  return record[fieldName];
}

function syncHighlightRenderOrder(record, object, fieldName, highlighted, highlightRenderOrder) {
  if (!object) {
    return;
  }
  const baseRenderOrder = baseObjectRenderOrder(record, object, fieldName);
  object.renderOrder = highlighted ? highlightRenderOrder : baseRenderOrder;
}

function syncSurfaceTransparency(record, forceTransparent, opacity, {
  writeTransparentDepth = true
} = {}) {
  const material = record?.material;
  if (!material) {
    return;
  }
  if (!Object.hasOwn(record, "baseDepthWrite")) {
    record.baseDepthWrite = material.depthWrite !== false;
  }
  const nextTransparent = forceTransparent || opacity < 0.999;
  if (material.transparent !== nextTransparent) {
    material.transparent = nextTransparent;
    material.needsUpdate = true;
  }
  material.depthWrite = nextTransparent && !writeTransparentDepth ? false : record.baseDepthWrite;
}

const CAD_SURFACE_EDGE_OPACITY_UNIFORMS = Object.freeze({
  feature: "cadSurfaceFeatureOpacity",
  tangent: "cadSurfaceTangentOpacity",
  seam: "cadSurfaceSeamOpacity",
  degenerate: "cadSurfaceDegenerateOpacity"
});

function syncCadSurfaceEdgeHighlight(THREE, record, edgeColor, edgeOpacity = null) {
  const material = record?.material;
  const userData = material?.userData;
  if (!material || userData?.cadSurfaceEdges !== true) {
    return;
  }
  const nextColor = edgeColor?.isColor
    ? edgeColor
    : readSourceColor(THREE, edgeColor) || userData.cadSurfaceEdgeBaseColor;
  if (nextColor?.isColor) {
    userData.cadSurfaceEdgeColor = nextColor.clone();
    const colorUniform = userData.cadSurfaceEdgeShader?.uniforms?.cadSurfaceEdgeColor;
    if (colorUniform?.value?.copy) {
      colorUniform.value.copy(nextColor);
    }
  }

  const highlightedOpacity = edgeOpacity !== null && edgeOpacity !== undefined && Number.isFinite(Number(edgeOpacity))
    ? clamp(Number(edgeOpacity), 0, 1)
    : null;
  const baseClassSettings = userData.cadSurfaceEdgeBaseClassSettings || {};
  const uniforms = userData.cadSurfaceEdgeShader?.uniforms || null;
  for (const [classId, uniformName] of Object.entries(CAD_SURFACE_EDGE_OPACITY_UNIFORMS)) {
    const baseOpacity = Number(baseClassSettings[classId]?.opacity);
    const nextOpacity = highlightedOpacity === null
      ? (Number.isFinite(baseOpacity) ? baseOpacity : null)
      : highlightedOpacity;
    if (nextOpacity === null) {
      continue;
    }
    userData[`cadSurfaceEdge${classId}Opacity`] = nextOpacity;
    if (uniforms?.[uniformName]) {
      uniforms[uniformName].value = nextOpacity;
    }
  }
}

export function applyPartVisualState(THREE, records, {
  baseTheme = DEFAULT_THEME,
  edgeSettings,
  hiddenPartIds,
  hoveredPartId,
  focusedPartId,
  selectedPartIds,
  showEdges = true
} = {}) {
  const hidden = new Set(Array.isArray(hiddenPartIds) ? hiddenPartIds : []);
  const selected = new Set(Array.isArray(selectedPartIds) ? selectedPartIds : []);
  const hovered = new Set(
    (Array.isArray(hoveredPartId) ? hoveredPartId : [hoveredPartId])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const baseEdgeColor = edgeSettings?.color || baseTheme?.edge || DEFAULT_THEME.edge;
  const defaultSurfaceOpacity = Number.isFinite(Number(baseTheme?.surfaceOpacity))
    ? Number(baseTheme.surfaceOpacity)
    : 1;
  const focusIds = new Set(normalizePartIdList(focusedPartId));
  const hasFocus = focusIds.size > 0;
  const baseEdgeOpacity = Number.isFinite(Number(edgeSettings?.opacity))
    ? clamp(Number(edgeSettings.opacity), 0, 1)
    : (baseTheme?.edgeOpacity ?? DEFAULT_THEME.edgeOpacity ?? CAD_EDGE_OPACITY);
  const highlightEdgeOpacity = Number.isFinite(Number(edgeSettings?.highlightOpacity))
    ? clamp(Number(edgeSettings.highlightOpacity), 0, 1)
    : 1;
  const edgeHighlightColor = String(edgeSettings?.highlightColor || REFERENCE_SELECTED_COLOR).trim() || REFERENCE_SELECTED_COLOR;
  const hoveredSurfaceColor = new THREE.Color(REFERENCE_HOVER_COLOR);
  const hoveredEdgeColor = new THREE.Color(edgeHighlightColor);
  const selectedSurfaceColor = new THREE.Color(REFERENCE_SELECTED_COLOR);
  const selectedEdgeColor = new THREE.Color(edgeHighlightColor);

  for (const record of Array.isArray(records) ? records : []) {
    if (!record?.mesh || !record?.material) {
      continue;
    }
    const effectStyle = record.effectStyle && typeof record.effectStyle === "object" ? record.effectStyle : {};
    const effectHidden = record.effectVisible === false;
    const effectColor = readSourceColor(THREE, effectStyle.color);
    const effectEdgeColor = readSourceColor(THREE, effectStyle.edgeColor);
    const effectEmissive = readSourceColor(THREE, effectStyle.emissive);
    const isHidden = hidden.has(record.partId);
    const isSelected = !isHidden && (selected.has(record.partId) || record.effectHighlighted === true);
    const isHovered = !isHidden && !effectHidden && hovered.has(record.partId);
    const isFocused = !isHidden && !effectHidden && hasFocus && focusIds.has(record.partId);
    const isDimmed = !isHidden && !effectHidden && hasFocus && !isFocused;
    const isHighlighted = isSelected || isHovered;

    record.mesh.visible = !effectHidden;
    if (record.edges) {
      record.edges.visible = showEdges && !effectHidden;
    }
    if (record.silhouette) {
      record.silhouette.visible = !effectHidden;
    }
    syncHighlightRenderOrder(record, record.mesh, "baseMeshRenderOrder", isHighlighted, PART_HIGHLIGHT_SURFACE_RENDER_ORDER);
    syncHighlightRenderOrder(record, record.edges, "baseEdgeRenderOrder", isHighlighted, PART_HIGHLIGHT_EDGE_RENDER_ORDER);

    const baseSurfaceOpacity = Number.isFinite(Number(record.baseOpacity))
      ? Number(record.baseOpacity)
      : defaultSurfaceOpacity;
    const effectOpacity = Number.isFinite(Number(effectStyle.opacity))
      ? clamp(Number(effectStyle.opacity), 0, 1)
      : 1;
    const effectEdgeOpacity = Number.isFinite(Number(effectStyle.edgeOpacity))
      ? clamp(Number(effectStyle.edgeOpacity), 0, 1)
      : effectOpacity;
    const highlightedEdgeOpacity = (isSelected || isHovered) ? highlightEdgeOpacity * effectEdgeOpacity : null;
    const dimmedSurfaceOpacity = Math.min(baseSurfaceOpacity * effectOpacity, FOCUSED_DIMMED_SURFACE_OPACITY);
    const highlightedSurfaceOpacity = isSelected
      ? clamp((baseSurfaceOpacity * effectOpacity) + PART_SELECTED_OPACITY_BOOST, 0, 1)
      : isHovered
        ? clamp((baseSurfaceOpacity * effectOpacity) + PART_HOVER_OPACITY_BOOST, 0, 1)
        : baseSurfaceOpacity * effectOpacity;
    const nextSurfaceOpacity = isHidden || isDimmed ? dimmedSurfaceOpacity : highlightedSurfaceOpacity;
    syncSurfaceTransparency(record, isHidden || isDimmed || isHighlighted, nextSurfaceOpacity, {
      writeTransparentDepth: !isHidden && !isDimmed
    });
    record.material.opacity = nextSurfaceOpacity;

    if (record.baseColor && record.material.color) {
      record.material.color.copy(
        isSelected
          ? selectedSurfaceColor
          : isHovered
            ? hoveredSurfaceColor
            : effectColor || record.baseColor
      );
    }

    if ("emissive" in record.material && record.material.emissive) {
      if (isSelected) {
        record.material.emissive.set(REFERENCE_SELECTED_COLOR);
      } else if (isHovered) {
        record.material.emissive.set(REFERENCE_HOVER_COLOR);
      } else if (record.baseEmissiveColor && record.baseEmissiveIntensity > 0) {
        record.material.emissive.copy(record.baseEmissiveColor);
      } else {
        record.material.emissive.set(0x000000);
      }
      record.material.emissiveIntensity = isSelected
        ? 0.08
        : isHovered
          ? 0.12
          : effectEmissive
            ? clamp(Number(effectStyle.emissiveIntensity) || 0.22, 0, 2)
            : clamp(Number(record.baseEmissiveIntensity) || 0, 0, 2);
      if (!isSelected && !isHovered && effectEmissive) {
        record.material.emissive.copy(effectEmissive);
      }
    }

    const nextEdgeColor = isSelected
      ? selectedEdgeColor
      : isHovered
        ? hoveredEdgeColor
        : effectEdgeColor || baseEdgeColor;
    syncCadSurfaceEdgeHighlight(THREE, record, nextEdgeColor, highlightedEdgeOpacity);

    if (record.edgeMaterial) {
      record.edgeMaterial.color?.set?.(nextEdgeColor);
      syncLineMaterialOpacity(record.edgeMaterial, isSelected
        ? highlightEdgeOpacity * effectEdgeOpacity
        : isHovered
          ? highlightEdgeOpacity * effectEdgeOpacity
          : isHidden || isDimmed
            ? nextSurfaceOpacity
            : baseEdgeOpacity * effectEdgeOpacity);
    }
  }
}

function resetParameterEffects(records) {
  for (const record of Array.isArray(records) ? records : []) {
    record.effectMatrix = null;
    record.effectStyle = null;
    record.effectVisible = null;
    record.effectHighlighted = false;
  }
}

function boundsCorners(THREE, bounds) {
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : [1, 1, 1];
  return [
    [min[0], min[1], min[2]],
    [min[0], min[1], max[2]],
    [min[0], max[1], min[2]],
    [min[0], max[1], max[2]],
    [max[0], min[1], min[2]],
    [max[0], min[1], max[2]],
    [max[0], max[1], min[2]],
    [max[0], max[1], max[2]]
  ].map((corner) => new THREE.Vector3(
    toNumber(corner[0]),
    toNumber(corner[1]),
    toNumber(corner[2])
  ));
}

function transformedBounds(THREE, bounds, matrix = null) {
  if (!bounds || !Array.isArray(bounds.min) || !Array.isArray(bounds.max)) {
    return null;
  }
  if (!(matrix instanceof THREE.Matrix4)) {
    return {
      min: [...bounds.min],
      max: [...bounds.max]
    };
  }
  const corners = boundsCorners(THREE, bounds).map((corner) => corner.applyMatrix4(matrix));
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const corner of corners) {
    min[0] = Math.min(min[0], corner.x);
    min[1] = Math.min(min[1], corner.y);
    min[2] = Math.min(min[2], corner.z);
    max[0] = Math.max(max[0], corner.x);
    max[1] = Math.max(max[1], corner.y);
    max[2] = Math.max(max[2], corner.z);
  }
  return min.every(Number.isFinite) && max.every(Number.isFinite) ? { min, max } : null;
}

function mergeBoundsList(boundsList) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let count = 0;
  for (const bounds of Array.isArray(boundsList) ? boundsList : []) {
    if (!bounds || !Array.isArray(bounds.min) || !Array.isArray(bounds.max)) {
      continue;
    }
    count += 1;
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], toNumber(bounds.min[axis]));
      max[axis] = Math.max(max[axis], toNumber(bounds.max[axis]));
    }
  }
  return count > 0 && min.every(Number.isFinite) && max.every(Number.isFinite) ? { min, max } : null;
}

function effectiveBoundsFromRecords(THREE, records, fallbackBounds) {
  const boundsList = [];
  for (const record of Array.isArray(records) ? records : []) {
    if (record.effectVisible === false) {
      continue;
    }
    const baseMatrix = buildPartTransformMatrix(THREE, record.baseTransform);
    const effectMatrix = record.effectMatrix instanceof THREE.Matrix4 ? record.effectMatrix.clone() : null;
    const combinedMatrix = effectMatrix ? effectMatrix.multiply(baseMatrix) : baseMatrix;
    boundsList.push(transformedBounds(THREE, record.partBounds, combinedMatrix));
  }
  return mergeBoundsList(boundsList) || fallbackBounds;
}

function runParameterSetup(THREE, runtime, parameters, meshData, callbacks = {}) {
  const definition = parameters?.definition || null;
  const module = definition?.module || null;
  if (!definition || !module?.setup) {
    return;
  }
  const effectsByPartId = new Map();
  const features = resolveStepModuleFeatures(definition, {
    meshData,
    selectorRuntime: parameters?.selectorRuntime || null
  });
  const ctx = buildStepModuleContext({
    runtime,
    stepModuleRuntime: parameters,
    features,
    effects: createStepModuleEffectsApi(THREE, {
      meshData,
      features,
      runtime,
      effectsByPartId
    }),
    cleanup: (cleanup) => {
      if (typeof cleanup === "function") {
        runtime.cleanups.push(cleanup);
      }
    }
  });
  try {
    module.setup(ctx);
  } catch (error) {
    callbacks.onWarning?.({
      title: "STEP parameter setup failed",
      message: error instanceof Error ? error.message : String(error),
      error
    });
  }
}

function cleanupParameterRuntime(runtime, parameters, callbacks = {}) {
  while (runtime.cleanups.length) {
    try {
      runtime.cleanups.pop()?.();
    } catch (error) {
      callbacks.onWarning?.({
        title: "STEP parameter cleanup failed",
        message: error instanceof Error ? error.message : String(error),
        error
      });
    }
  }
  const module = parameters?.definition?.module || null;
  if (!module?.dispose) {
    return;
  }
  const ctx = buildStepModuleContext({
    runtime,
    stepModuleRuntime: parameters,
    features: {},
    effects: {},
    cleanup: () => {}
  });
  try {
    module.dispose(ctx);
  } catch (error) {
    callbacks.onWarning?.({
      title: "STEP parameter dispose failed",
      message: error instanceof Error ? error.message : String(error),
      error
    });
  }
}

function applyParameters(THREE, runtime, parameters, meshData, callbacks = {}) {
  const definition = parameters?.definition || null;
  const module = definition?.module || null;
  if (!definition || !module) {
    resetParameterEffects(runtime.displayRecords);
    for (const record of runtime.displayRecords) {
      applyDisplayRecordTransform(THREE, record);
    }
    return runtime.baseBounds;
  }

  const effectsByPartId = new Map();
  const features = resolveStepModuleFeatures(definition, {
    meshData,
    selectorRuntime: parameters?.selectorRuntime || null
  });
  const effects = createStepModuleEffectsApi(THREE, {
    meshData,
    features,
    runtime,
    effectsByPartId
  });
  const ctx = buildStepModuleContext({
    runtime,
    stepModuleRuntime: parameters,
    features,
    effects,
    cleanup: (cleanup) => {
      if (typeof cleanup === "function") {
        runtime.cleanups.push(cleanup);
      }
    }
  });

  try {
    module.update?.(ctx);
    module.render?.(ctx);
  } catch (error) {
    callbacks.onWarning?.({
      title: "STEP parameter update failed",
      message: error instanceof Error ? error.message : String(error),
      error
    });
  }

  applyStepModuleEffectsToRecords(THREE, runtime.displayRecords, effectsByPartId);
  for (const record of runtime.displayRecords) {
    applyDisplayRecordTransform(THREE, record);
  }
  return effectiveBoundsFromRecords(THREE, runtime.displayRecords, runtime.baseBounds);
}

export function buildStepClipPlane(THREE, clip, bounds, modelOffset = null) {
  const normalized = normalizeStepClipSettings(clip);
  if (!normalized.enabled || !bounds) {
    return null;
  }
  const index = axisIndex(normalized.axis);
  const boundsMin = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const boundsMax = Array.isArray(bounds?.max) ? bounds.max : boundsMin;
  const min = toNumber(boundsMin[index]);
  const max = toNumber(boundsMax[index]);
  const low = Math.min(min, max);
  const high = Math.max(min, max);
  const position = low + ((high - low) * normalized.offset);
  const normal = new THREE.Vector3(
    index === 0 ? 1 : 0,
    index === 1 ? 1 : 0,
    index === 2 ? 1 : 0
  );
  if (normalized.invert) {
    normal.multiplyScalar(-1);
  }
  const point = modelOffset?.clone ? modelOffset.clone() : new THREE.Vector3(0, 0, 0);
  point.setComponent(index, point.getComponent(index) + position);
  return new THREE.Plane().setFromNormalAndCoplanarPoint(normal, point);
}

export function syncMaterialClipPlanes(material, clipPlanes) {
  if (!material) {
    return;
  }
  const materials = Array.isArray(material) ? material : [material];
  const clippingEnabled = Array.isArray(clipPlanes) && clipPlanes.length > 0;
  for (const item of materials) {
    if (!item) {
      continue;
    }
    const previousEnabled = item.userData?.cadClipPlaneEnabled === true;
    const previousCount = Number(item.userData?.cadClipPlaneCount) || 0;
    const previousShaderClipping = item.clipping === true;
    item.clippingPlanes = clippingEnabled ? clipPlanes : null;
    item.clipIntersection = false;
    item.clipShadows = clippingEnabled;
    if ("clipping" in item) {
      item.clipping = clippingEnabled;
    }
    item.userData = {
      ...(item.userData || {}),
      cadClipPlaneEnabled: clippingEnabled,
      cadClipPlaneCount: clippingEnabled ? clipPlanes.length : 0
    };
    if (
      previousEnabled !== clippingEnabled ||
      previousCount !== (clippingEnabled ? clipPlanes.length : 0) ||
      previousShaderClipping !== (item.clipping === true)
    ) {
      item.needsUpdate = true;
    }
  }
}

function syncClip(runtime, clip, bounds, modelOffset = null) {
  const clipPlane = buildStepClipPlane(runtime.THREE, clip, bounds, modelOffset);
  const clipPlanes = clipPlane ? [clipPlane] : [];
  runtime.activeClipPlane = clipPlane;
  runtime.activeClipPlanes = clipPlanes;
  for (const record of runtime.displayRecords) {
    syncMaterialClipPlanes(record.material, clipPlanes);
    syncMaterialClipPlanes(record.edgeMaterial, clipPlanes);
    syncMaterialClipPlanes(record.silhouette?.material, clipPlanes);
  }
}

function normalizeSelection(selection = {}) {
  return selection && typeof selection === "object" ? selection : {};
}

function selectorEntries(value) {
  if (Array.isArray(value)) {
    return value;
  }
  const text = String(value || "").trim();
  return text.split(",");
}

function selectorValuesFromEntry(value) {
  const text = String(value || "").trim();
  if (!text) {
    return [];
  }
  const selectorText = text.startsWith("#") ? text.slice(1) : text;
  return selectorText.split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function normalizedSelectorValues(value) {
  return selectorEntries(value).flatMap(selectorValuesFromEntry);
}

function valueMatchesSelector(value, selector, { descendants = false } = {}) {
  const normalizedValue = String(value || "").trim();
  const normalizedSelector = String(selector || "").trim();
  if (!normalizedValue || !normalizedSelector) {
    return false;
  }
  return normalizedValue === normalizedSelector ||
    (descendants && normalizedValue.startsWith(`${normalizedSelector}.`));
}

function partMatchesSelector(part, selector) {
  const normalized = String(selector || "").trim();
  if (!normalized) {
    return false;
  }
  if ([
    part?.id,
    part?.occurrenceId
  ].some((value) => valueMatchesSelector(value, normalized, { descendants: true }))) {
    return true;
  }
  return [
    part?.name,
    part?.label,
    part?.linkName
  ].some((value) => valueMatchesSelector(value, normalized));
}

function mergePartBounds(parts) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let count = 0;
  for (const part of Array.isArray(parts) ? parts : []) {
    const bounds = part?.bounds;
    if (!Array.isArray(bounds?.min) || !Array.isArray(bounds?.max)) {
      continue;
    }
    count += 1;
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], Number(bounds.min[axis]));
      max[axis] = Math.max(max[axis], Number(bounds.max[axis]));
    }
  }
  return count > 0 && min.every(Number.isFinite) && max.every(Number.isFinite) ? { min, max } : null;
}

function filterMeshDataForSelection(meshData, selection = {}) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  if (!parts.length) {
    return meshData;
  }
  const focus = [
    ...normalizedSelectorValues(selection.focus),
    ...normalizedSelectorValues(selection.refs)
  ];
  const hide = normalizedSelectorValues(selection.hide);
  if (!focus.length && !hide.length) {
    return meshData;
  }
  const nextParts = parts.filter((part) => {
    if (focus.length && !focus.some((selector) => partMatchesSelector(part, selector))) {
      return false;
    }
    return !hide.some((selector) => partMatchesSelector(part, selector));
  });
  if (!nextParts.length) {
    throw new Error("No renderable parts remain after applying focus/hide filters");
  }
  return {
    ...meshData,
    parts: nextParts,
    bounds: mergePartBounds(nextParts) || meshData.bounds
  };
}

function resolveMaterialSettings(theme, settings = {}) {
  if (settings.materialSettings && typeof settings.materialSettings === "object") {
    return settings.materialSettings;
  }
  return theme.materials || {};
}

function resolvePartsToRender(meshData, theme, settings) {
  if (Array.isArray(settings.parts)) {
    return settings.parts.filter((part) => toNumber(part?.vertexCount) > 0 && toNumber(part?.triangleCount) > 0);
  }
  const parts = toArray(meshData?.parts).filter((part) => toNumber(part?.vertexCount) > 0 && toNumber(part?.triangleCount) > 0);
  if (!parts.length) {
    return [];
  }
  if (settings.renderPartsIndividually === true) {
    return parts;
  }
  if (settings.renderPartsIndividually === false) {
    const pickableParts = toArray(settings.pickableParts).filter((part) => toNumber(part?.vertexCount) > 0 && toNumber(part?.triangleCount) > 0);
    if (pickableParts.length) {
      return pickableParts;
    }
    if (meshUsesPartSourceColors(meshData, parts)) {
      return parts;
    }
    const hasFillRotation = theme?.materials?.cycleColors === true &&
      Array.isArray(theme?.materials?.fillColors) &&
      theme.materials.fillColors.length > 1;
    return hasFillRotation ? parts : [];
  }
  return parts;
}

function addEdgeObject(THREE, runtime, record, edgeGeometry, settings) {
  const edgeSettings = runtime.edgeSettings;
  const baseTheme = runtime.baseTheme;
  const displayMode = runtime.displayMode;
  const useScreenSpaceEdges = runtime.edgeRendering?.mode === "screen-space";
  const rawResult = useScreenSpaceEdges
    ? createDisplayEdgeObject(runtime, {
        THREE,
        geometry: edgeGeometry,
        edgeSettings,
        baseTheme,
        partId: record.partId,
        displayMode,
        thickness: getEdgeThickness(edgeSettings, baseTheme),
        wireframeEdgeColor: runtime.edgeRendering?.wireframeEdgeColor || ""
      }, runtime.screenSpaceLineMaterials)
    : createDefaultEdgeObject(THREE, edgeGeometry, baseTheme, edgeSettings, record.partId, displayMode);
  const { object, material } = normalizeEdgeResult(rawResult);
  if (!object) {
    return;
  }
  object.userData.partId = record.partId;
  record.edges = object;
  record.edgeMaterial = material;
  record.baseEdgeColor = material?.color?.isColor ? material.color.clone() : new THREE.Color(edgeSettings?.color || baseTheme?.edge || DEFAULT_THEME.edge);
  record.baseEdgeOpacity = Number.isFinite(Number(material?.opacity)) ? Number(material.opacity) : 1;
  runtime.edgesGroup.add(object);
}

function buildDisplayRecords(THREE, runtime, meshData, settings) {
  const theme = runtime.theme;
  const materialSettings = runtime.materialSettings;
  const displayMode = runtime.displayMode;
  const baseTheme = runtime.baseTheme;
  const edgeSettings = runtime.edgeSettings;
  const bounds = meshData.bounds || boundsFromVertices(meshData.vertices || []);
  const { radius } = centerAndRadiusFromBounds(THREE, bounds, runtime.scale);
  const useSilhouette = shouldBuildSilhouette(edgeSettings, displayMode, settings);
  const renderParts = resolvePartsToRender(meshData, theme, settings);
  const partFillIndexMap = buildPartFillIndexMap(renderParts);
  const useWholeMesh = renderParts.length === 0;
  const records = [];

  const makeRecord = ({ part = null, geometryEntry, fillIndex = 0, baseTransform = null }) => {
    const partId = part ? String(part?.id || part?.occurrenceId || `part:${records.length}`) : MODEL_PART_ID;
    const wireframeMode = displayModeIsWireframe(displayMode);
    const forceFill = materialSettings.overrideSourceColors === true || wireframeMode;
    const sourceVertexColors = !!geometryEntry.geometry.getAttribute("color");
    const useSurfaceEdges = !wireframeMode &&
      !displayModeShowsThroughEdges(displayMode) &&
      edgeSettings.enabled &&
      geometryHasSurfaceEdgeAttributes(geometryEntry.geometry);
    const sourceColor = sourceColorForPart(THREE, part, meshData);
    const hasSourceColor = sourceVertexColors || !!sourceColor;
    const hasVertexColors = !forceFill && sourceVertexColors;
    const baseColor = resolveSourceBaseColor(THREE, {
      hasVertexColors,
      sourceColor: forceFill ? null : sourceColor,
      materialSettings,
      fallbackColor: materialSettings.defaultColor || baseTheme?.surface || DEFAULT_THEME.surface,
      fillIndex,
      forceFill: forceFill || !hasSourceColor
    });
    const material = wireframeMode
      ? createWireframeSurfaceMaterial(THREE, materialSettings, fillIndex)
      : displayModeUsesUnlitSurfaces(displayMode)
        ? createUnshadedSurfaceMaterial(THREE, {
            color: baseColor,
            useVertexColors: hasVertexColors,
            opacity: displayModeSurfaceOpacity(displayMode, materialSettings.opacity)
          })
        : createSurfaceMaterial(THREE, baseTheme, {
          color: baseColor,
          useVertexColors: hasVertexColors,
          edgeSettings: useSurfaceEdges ? edgeSettings : null
        });
    if (edgeSettings.enabled && !wireframeMode && !useSurfaceEdges) {
      material.polygonOffset = true;
      material.polygonOffsetFactor = 1;
      material.polygonOffsetUnits = 1;
    }
    const mesh = new THREE.Mesh(geometryEntry.geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = false;
    mesh.userData.partId = partId;
    const faceIds = part
      ? settings.callbacks?.faceIdsForPart?.(part)
      : settings.callbacks?.faceIdsForMesh?.(meshData);
    if (faceIds) {
      mesh.userData.faceIds = faceIds;
    }
    runtime.modelGroup.add(mesh);

    const record = {
      partId,
      mesh,
      edges: null,
      silhouette: null,
      material,
      edgeMaterial: null,
      baseColor,
      sourceColor,
      baseTransform,
      partCenter: readBoundsCenter(THREE, part?.bounds || bounds),
      partBounds: part?.bounds || part?.sourceBounds || bounds,
      effectMatrix: null,
      effectStyle: null,
      effectVisible: null,
      effectHighlighted: false,
      fillIndex,
      hasSourceColor,
      hasVertexColors,
      useVertexColors: hasVertexColors,
      rawColors: geometryEntry.rawColors,
      geometry: geometryEntry.geometry,
      baseOpacity: Number.isFinite(Number(material.opacity)) ? Number(material.opacity) : 1,
      baseEmissiveColor: baseColor ? baseColor.clone() : null,
      baseEmissiveIntensity: 0,
      baseEdgeColor: null,
      baseEdgeOpacity: 1
    };

    if (useSilhouette) {
      const silhouette = createSilhouetteMesh(THREE, geometryEntry.geometry, edgeSettings, radius);
      if (silhouette) {
        record.silhouette = silhouette;
        runtime.modelGroup.add(silhouette);
      }
    }

    if (settings.selection?.showEdges !== false && !useSurfaceEdges && (edgeSettings.enabled || wireframeMode)) {
      addEdgeObject(
        THREE,
        runtime,
        record,
        buildEdgeGeometry(THREE, meshData, part, geometryEntry.geometry, displayMode, edgeSettings),
        settings
      );
    }

    applyMaterialSettingsToRecord(THREE, record, materialSettings, {
      baseTheme,
      displayMode
    });
    applyDisplayRecordTransform(THREE, record);
    records.push(record);
  };

  if (useWholeMesh) {
    const geometryEntry = buildWholeGeometryEntry(THREE, meshData, settings.recomputeNormals === true);
    if (geometryEntry) {
      makeRecord({ geometryEntry, fillIndex: 0 });
    }
  } else {
    for (const part of renderParts) {
      const geometryEntry = buildPartGeometryEntry(THREE, meshData, part, settings.recomputeNormals === true);
      if (!geometryEntry) {
        continue;
      }
      makeRecord({
        part,
        geometryEntry,
        fillIndex: partFillIndexMap.get(part) ?? records.length,
        baseTransform: displayTransformForPart(meshData, part, settings.renderPartsIndividually === true)
      });
    }
  }

  return records;
}

function settingsSignature(meshData, theme, settings) {
  const edgeSettings = resolveThemeDisplayEdgeSettings(theme);
  return JSON.stringify({
    meshData: meshData ? "mesh" : "",
    displayMode: normalizeDisplayMode(settings.displayMode),
    parts: cacheKey(resolvePartsToRender(meshData, theme, settings)),
    recomputeNormals: settings.recomputeNormals === true,
    edgeSettings,
    silhouette: settings.silhouette !== false &&
      edgeSettings.silhouette === true &&
      (edgeSettings.enabled !== false || settings.silhouette === true),
    edgeRendering: settings.edgeRendering?.mode || "basic",
    wireframeEdgeColor: settings.edgeRendering?.wireframeEdgeColor || ""
  });
}

function normalizeSettings(settings = {}) {
  const displayMode = normalizeDisplayMode(settings.displayMode);
  const normalizedTheme = normalizeThemeSettings(settings.theme || settings.themeSettings || settings.settings || undefined);
  const themeEdgeSettings = resolveThemeDisplayEdgeSettings(normalizedTheme);
  const applyDisplayModeEdgePolicy = settings.applyDisplayModeEdgePolicy !== false;
  const theme = {
    ...normalizedTheme,
    edges: applyDisplayModeEdgePolicy
      ? {
          ...themeEdgeSettings,
          enabled: displayModeAllowsEdges(displayMode) &&
            (displayModeForcesEdges(displayMode) || themeEdgeSettings.enabled === true),
          depthTest: displayModeShowsThroughEdges(displayMode) ? false : themeEdgeSettings.depthTest
        }
      : themeEdgeSettings
  };
  const scale = normalizeCadSceneScale(settings.scale ?? settings.sceneScale ?? settings.sceneScaleMode);
  const callbacks = settings.callbacks && typeof settings.callbacks === "object" ? settings.callbacks : {};
  const baseTheme = settings.baseTheme && typeof settings.baseTheme === "object" ? settings.baseTheme : DEFAULT_THEME;
  return {
    ...settings,
    theme,
    displayMode,
    scale,
    callbacks,
    baseTheme,
    selection: normalizeSelection(settings.selection),
    clip: normalizeStepClipSettings(settings.clip),
    stepParameters: settings.stepParameters || null,
    parameterSetup: settings.parameterSetup !== false,
    materialSettings: resolveMaterialSettings(theme, settings),
    edgeRendering: normalizeEdgeRendering(settings.edgeRendering)
  };
}

function setRuntimeTheme(runtime, settings) {
  runtime.theme = settings.theme;
  runtime.displayMode = settings.displayMode;
  runtime.scale = settings.scale;
  runtime.baseTheme = settings.baseTheme;
  runtime.edgeSettings = {
    ...resolveThemeDisplayEdgeSettings(settings.theme),
    depthTest: displayModeShowsThroughEdges(settings.displayMode) ? false : undefined
  };
  runtime.materialSettings = settings.materialSettings;
  applyEdgeRenderingToRuntime(runtime, settings.edgeRendering);
}

function meshDataFromSource(source) {
  return source?.meshData || source;
}

export function buildModel(THREE, source, settings = {}) {
  if (!THREE) {
    throw new Error("buildModel requires THREE");
  }
  const rawMeshData = meshDataFromSource(source);
  const normalized = normalizeSettings(settings);
  const meshData = filterMeshDataForSelection(rawMeshData, normalized.selection);
  const root = new THREE.Group();
  const modelGroup = new THREE.Group();
  const edgesGroup = new THREE.Group();
  root.name = "CadSceneRoot";
  modelGroup.name = "CadSceneModel";
  edgesGroup.name = "CadSceneEdges";
  root.add(modelGroup);
  root.add(edgesGroup);

  const baseBounds = meshData?.bounds || boundsFromVertices(meshData?.vertices || []);
  const runtime = {
    THREE,
    root,
    modelGroup,
    edgesGroup,
    displayRecords: [],
    records: [],
    baseBounds,
    bounds: baseBounds,
    modelBounds: baseBounds,
    modelRadius: centerAndRadiusFromBounds(THREE, baseBounds, normalized.scale).radius,
    cleanups: [],
    activeClipPlane: null,
    activeClipPlanes: [],
    screenSpaceLineMaterials: new Set(),
    syncScreenSpaceLineMaterials(width, height) {
      syncScreenSpaceLineMaterialResolution(runtime.screenSpaceLineMaterials, width, height);
    },
    registerScreenSpaceLineMaterial(material) {
      if (!material?.resolution?.set) {
        return;
      }
      runtime.screenSpaceLineMaterials.add(material);
    },
    unregisterScreenSpaceLineMaterial(material) {
      runtime.screenSpaceLineMaterials.delete(material);
    },
    requestRender: () => {}
  };
  setRuntimeTheme(runtime, normalized);

  let disposed = false;
  let currentSettings = normalized;
  let currentSignature = "";
  let activeParameters = null;
  let activeParameterSetup = false;

  const rebuild = (nextSettings = currentSettings) => {
    clearGroup(modelGroup);
    clearGroup(edgesGroup);
    setRuntimeTheme(runtime, nextSettings);
    runtime.baseBounds = meshData?.bounds || boundsFromVertices(meshData?.vertices || []);
    runtime.displayRecords = buildDisplayRecords(THREE, runtime, meshData, nextSettings);
    runtime.records = runtime.displayRecords;
    runtime.bounds = runtime.baseBounds;
    runtime.modelBounds = runtime.baseBounds;
    runtime.modelRadius = centerAndRadiusFromBounds(THREE, runtime.baseBounds, runtime.scale).radius;
    currentSignature = settingsSignature(meshData, runtime.theme, nextSettings);
  };

  const applyMutableState = (nextSettings = currentSettings) => {
    setRuntimeTheme(runtime, nextSettings);
    for (const record of runtime.displayRecords) {
      applyMaterialSettingsToRecord(THREE, record, runtime.materialSettings, {
        baseTheme: runtime.baseTheme,
        displayMode: runtime.displayMode
      });
    }
    const nextParameterSetup = nextSettings.parameterSetup !== false;
    const nextParameters = nextSettings.stepParameters || null;
    if (activeParameters !== nextParameters || activeParameterSetup !== nextParameterSetup) {
      if (activeParameterSetup) {
        cleanupParameterRuntime(runtime, activeParameters, nextSettings.callbacks);
      }
      activeParameters = nextParameters;
      activeParameterSetup = nextParameterSetup;
      if (activeParameterSetup) {
        runParameterSetup(THREE, runtime, activeParameters, meshData, nextSettings.callbacks);
      }
    }
    const effectiveBounds = applyParameters(THREE, runtime, activeParameters, meshData, nextSettings.callbacks);
    runtime.bounds = effectiveBounds || runtime.baseBounds;
    runtime.modelBounds = runtime.bounds;
    runtime.modelRadius = centerAndRadiusFromBounds(THREE, runtime.bounds, runtime.scale).radius;
    applyPartVisualState(THREE, runtime.displayRecords, {
      baseTheme: runtime.baseTheme,
      edgeSettings: runtime.edgeSettings,
      ...nextSettings.selection,
      showEdges: nextSettings.selection?.showEdges !== false
    });
    syncClip(runtime, nextSettings.clip, runtime.bounds, nextSettings.modelOffset || modelGroup.position);
  };

  rebuild(currentSettings);
  applyMutableState(currentSettings);

  const api = {
    source,
    meshData,
    root,
    modelGroup,
    edgesGroup,
    get displayRecords() {
      return runtime.displayRecords;
    },
    get records() {
      return runtime.displayRecords;
    },
    get bounds() {
      return runtime.bounds;
    },
    get radius() {
      return runtime.modelRadius;
    },
    get runtime() {
      return runtime;
    },
    update(nextSettings = {}) {
      if (disposed) {
        return api;
      }
      const mergedSettings = {
        ...currentSettings,
        ...nextSettings,
        selection: {
          ...(currentSettings.selection || {}),
          ...(nextSettings.selection || {})
        },
        callbacks: {
          ...(currentSettings.callbacks || {}),
          ...(nextSettings.callbacks || {})
        }
      };
      if (
        Object.prototype.hasOwnProperty.call(nextSettings, "theme") &&
        !Object.prototype.hasOwnProperty.call(nextSettings, "materialSettings")
      ) {
        delete mergedSettings.materialSettings;
      }
      currentSettings = normalizeSettings(mergedSettings);
      const nextSignature = settingsSignature(meshData, currentSettings.theme, currentSettings);
      if (nextSignature !== currentSignature) {
        rebuild(currentSettings);
      }
      applyMutableState(currentSettings);
      return api;
    },
    dispose() {
      if (disposed) {
        return;
      }
      disposed = true;
      if (activeParameterSetup) {
        cleanupParameterRuntime(runtime, activeParameters, currentSettings.callbacks);
      }
      clearGroup(root);
    }
  };

  return api;
}

export function fitCameraToModel(THREE, camera, bounds, {
  direction = [1, -1, 0.8],
  up = [0, 0, 1],
  width = 1400,
  height = 900,
  padding = 0.12,
  scale = CAD_SCENE_SCALE.CAD,
  lockedHalfHeight = null
} = {}) {
  const sceneScale = normalizeCadSceneScale(scale);
  const settings = getSceneScaleSettings(sceneScale);
  const { center, radius } = centerAndRadiusFromBounds(THREE, bounds, sceneScale);
  const viewDirection = new THREE.Vector3(...direction).normalize();
  const viewUp = new THREE.Vector3(...up).normalize();
  const distance = Math.max(radius * 3.2, settings.minModelRadius * 10);
  camera.position.copy(center).add(viewDirection.multiplyScalar(distance));
  camera.up.copy(viewUp);
  camera.lookAt(center);

  const aspect = Math.max(width / Math.max(height, 1), 0.01);
  const right = new THREE.Vector3().crossVectors(viewDirection, viewUp).normalize();
  const screenUp = new THREE.Vector3().crossVectors(right, viewDirection).normalize();
  const corners = boundsCorners(THREE, bounds);
  const xs = corners.map((corner) => corner.dot(right));
  const ys = corners.map((corner) => corner.dot(screenUp));
  const minSpan = settings.minModelRadius;
  const spanX = Math.max(Math.max(...xs) - Math.min(...xs), minSpan);
  const spanY = Math.max(Math.max(...ys) - Math.min(...ys), minSpan);
  const safeContentScale = Math.max(1 - (clamp(Number(padding) || 0, 0.1, 0.4) * 2), 0.1);
  const halfHeight = lockedHalfHeight || Math.max(
    spanY / (2 * safeContentScale),
    spanX / (2 * aspect * safeContentScale),
    minSpan / 2
  );
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.left = -halfHeight * aspect;
  camera.right = halfHeight * aspect;
  camera.near = 0.01;
  camera.far = Math.max(distance + radius * 6, sceneScale === CAD_SCENE_SCALE.URDF ? 10 : 1000);
  camera.updateProjectionMatrix?.();
  return {
    center,
    radius,
    halfHeight,
    distance
  };
}

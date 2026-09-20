import { resolveCadGridSettings } from "./cadInk.js";
import { buildGridConfig } from "../lib/viewer/stageGrid.js";
import * as THREE from "three";
import {
  RENDER_CAMERA_PRESETS,
  TOP_VIEW_UP,
  WORLD_UP,
  normalizeCameraZoom,
  resolveCameraSnapshot,
  resolveCameraView
} from "./camera.js";
import {
  DEFAULT_FILL_LIGHT_SETTINGS,
  DEFAULT_FLOOR_AXIS_SETTINGS,
  DEFAULT_FLOOR_GRID_SETTINGS,
  DEFAULT_RIM_LIGHT_SETTINGS,
  FLOOR_AXIS_RADIUS_MULTIPLE,
  THEME_FLOOR_MODES
} from "./themeSettings.js";
import {
  createCadWebGlRenderer
} from "./webglRenderer.js";
import { resolveViewSettings } from "./viewSettings.js";
import { PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER } from "./photographicStudioRig.js";
import {
  BASE_VIEWER_THEME,
  createStageFloorGlowPlane,
  createStageFloorPlane,
  createStageShadowPlane,
  getStageFloorSize
} from "../lib/viewer/stageTheme.js";
import {
  clampSceneModelRadius,
  getLightingScopeRadius,
  getProportionalLightingScopeRadius,
  getShadowCameraSettings
} from "../lib/viewer/sceneScale.js";

export const RENDER_SCENE_SCALE = Object.freeze({
  CAD: "cad",
  URDF: "urdf"
});

export { TOP_VIEW_UP, WORLD_UP };
export const RENDER_VIEW_PRESETS = RENDER_CAMERA_PRESETS;

export const SHARED_RENDER_OPTION_KEYS = Object.freeze([
  "themeSettings",
  "display",
  "camera",
  "framing",
  "sceneScale",
  "clip",
  "selection",
  "floor",
  "background",
  "lighting",
  "outputSize",
  "renderScale"
]);

/**
 * SharedRenderOptions is the policy-free shape consumed by lower-level render
 * helpers after snapshot or viewer code has already chosen defaults.
 *
 * @typedef {Object} SharedRenderOptions
 * @property {Object|null} themeSettings Explicit, normalized theme settings.
 * @property {Object|null} display Explicit display settings.
 * @property {Object|null} camera Explicit camera/view state.
 * @property {Object|null} framing Explicit framing settings.
 * @property {string|null} sceneScale Explicit CAD/URDF scene scale.
 * @property {Object|null} clip Explicit clip settings.
 * @property {Object|null} selection Explicit part/selection settings.
 * @property {Object|null} floor Explicit floor settings.
 * @property {Object|null} background Explicit background settings.
 * @property {Object|null} lighting Explicit lighting settings.
 * @property {Object|null} outputSize Explicit output width/height.
 * @property {number|null} renderScale Explicit render scale.
 */

export function createSharedRenderOptions(explicitOptions = {}) {
  const result = {};
  for (const key of SHARED_RENDER_OPTION_KEYS) {
    result[key] = Object.prototype.hasOwnProperty.call(explicitOptions, key)
      ? explicitOptions[key]
      : null;
  }
  return result;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

export function normalizeRenderSceneScale(value) {
  return value === RENDER_SCENE_SCALE.URDF ? RENDER_SCENE_SCALE.URDF : RENDER_SCENE_SCALE.CAD;
}

export function renderSceneScaleSettings(value, settingsByScale) {
  return settingsByScale[normalizeRenderSceneScale(value)];
}

export function inferRenderSceneScale({
  explicit = "",
  kind = "",
  parts = []
} = {}) {
  const normalizedExplicit = String(explicit || "").trim().toLowerCase();
  if (normalizedExplicit) {
    return normalizeRenderSceneScale(normalizedExplicit);
  }
  const normalizedKind = String(kind || "").trim().toLowerCase();
  if (normalizedKind === "urdf" || normalizedKind === "srdf" || normalizedKind === "sdf") {
    return RENDER_SCENE_SCALE.URDF;
  }
  return (Array.isArray(parts) ? parts : []).some((part) => String(part?.linkName || "").trim())
    ? RENDER_SCENE_SCALE.URDF
    : RENDER_SCENE_SCALE.CAD;
}

export function resolveRenderView(camera = "iso", viewPresets = RENDER_VIEW_PRESETS, {
  strict = false
} = {}) {
  return resolveCameraView(camera, {
    presets: viewPresets,
    strict
  });
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

export function centerAndRadiusFromBounds(bounds, sceneScale, settingsByScale) {
  const settings = renderSceneScaleSettings(sceneScale, settingsByScale);
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

export function colorTextureFromBackground(background, width, height) {
  if (background.type === "solid") {
    return new THREE.Color(background.solidColor);
  }
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(2, width);
  canvas.height = Math.max(2, height);
  const context = canvas.getContext("2d");
  if (background.type === "radial") {
    const gradient = context.createRadialGradient(
      canvas.width / 2,
      canvas.height / 2,
      0,
      canvas.width / 2,
      canvas.height / 2,
      Math.max(canvas.width, canvas.height) / 1.35
    );
    gradient.addColorStop(0, background.radialInner);
    gradient.addColorStop(1, background.radialOuter);
    context.fillStyle = gradient;
    context.fillRect(0, 0, canvas.width, canvas.height);
  } else {
    const angle = ((toFiniteNumber(background.linearAngle, 135) - 90) * Math.PI) / 180;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const length = Math.hypot(canvas.width, canvas.height);
    const dx = Math.cos(angle) * length / 2;
    const dy = Math.sin(angle) * length / 2;
    const gradient = context.createLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy);
    gradient.addColorStop(0, background.linearStart);
    gradient.addColorStop(1, background.linearEnd);
    context.fillStyle = gradient;
    context.fillRect(0, 0, canvas.width, canvas.height);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function modelRadiusFromBounds(bounds, sceneScale) {
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : [0, 0, 0];
  return clampSceneModelRadius(new THREE.Vector3(
    toFiniteNumber(max[0]) - toFiniteNumber(min[0]),
    toFiniteNumber(max[1]) - toFiniteNumber(min[1]),
    toFiniteNumber(max[2]) - toFiniteNumber(min[2])
  ).length() / 2, sceneScale);
}

function lightingScaleForRadius(radius, sceneScale) {
  return getProportionalLightingScopeRadius(radius, sceneScale) /
    Math.max(getLightingScopeRadius(sceneScale), 1e-9);
}

function setScaledPosition(light, position, scale, fallback = { x: 0, y: 0, z: 0 }) {
  light.position.set(
    toFiniteNumber(position?.x, fallback.x) * scale,
    toFiniteNumber(position?.y, fallback.y) * scale,
    toFiniteNumber(position?.z, fallback.z) * scale
  );
}

export function applyLighting(scene, themeSettings, {
  bounds = null,
  sceneScale = RENDER_SCENE_SCALE.CAD,
  shadowMapSize = 2048
} = {}) {
  const lighting = themeSettings.lighting || {};
  const radius = bounds ? modelRadiusFromBounds(bounds, sceneScale) : null;
  const positionScale = radius == null ? 1 : lightingScaleForRadius(radius, sceneScale);
  const addIfEnabled = (light, enabled) => {
    light.visible = enabled;
    scene.add(light);
  };
  addIfEnabled(
    new THREE.HemisphereLight(
      lighting.hemisphere?.skyColor || "#ffffff",
      lighting.hemisphere?.groundColor || "#101014",
      toFiniteNumber(lighting.hemisphere?.intensity, 1)
    ),
    lighting.hemisphere?.enabled !== false
  );
  addIfEnabled(
    new THREE.AmbientLight(lighting.ambient?.color || "#ffffff", toFiniteNumber(lighting.ambient?.intensity, 0.2)),
    lighting.ambient?.enabled !== false
  );
  const directional = new THREE.DirectionalLight(
    lighting.directional?.color || "#ffffff",
    toFiniteNumber(lighting.directional?.intensity, 1)
  );
  setScaledPosition(directional, lighting.directional?.position, positionScale, { x: 160, y: -140, z: 240 });
  directional.castShadow = true;
  addIfEnabled(directional, lighting.directional?.enabled !== false);
  if (bounds && directional.shadow?.camera) {
    const shadow = getShadowCameraSettings(sceneScale, {
      radius,
      keyLightDistance: directional.position.length(),
      shadowMapSize
    });
    directional.shadow.mapSize.set(shadowMapSize, shadowMapSize);
    directional.shadow.bias = -0.00025;
    directional.shadow.normalBias = shadow.normalBias;
    directional.shadow.radius = shadow.radius;
    directional.shadow.camera.left = -shadow.extent;
    directional.shadow.camera.right = shadow.extent;
    directional.shadow.camera.top = shadow.extent;
    directional.shadow.camera.bottom = -shadow.extent;
    directional.shadow.camera.near = 0.1;
    directional.shadow.camera.far = shadow.far;
    directional.shadow.camera.updateProjectionMatrix?.();
  }

  // Fill and rim mirror the interactive viewer's soft secondary directionals.
  // Theme settings arrive NORMALIZED (normalizeThemeSettings always carries
  // fill/rim); the fallbacks here are the same structural defaults.
  const fill = new THREE.DirectionalLight(
    lighting.fill?.color || DEFAULT_FILL_LIGHT_SETTINGS.color,
    toFiniteNumber(lighting.fill?.intensity, DEFAULT_FILL_LIGHT_SETTINGS.intensity)
  );
  setScaledPosition(fill, lighting.fill?.position, positionScale, DEFAULT_FILL_LIGHT_SETTINGS.position);
  addIfEnabled(fill, lighting.fill?.enabled !== false);

  const rim = new THREE.DirectionalLight(
    lighting.rim?.color || DEFAULT_RIM_LIGHT_SETTINGS.color,
    toFiniteNumber(lighting.rim?.intensity, DEFAULT_RIM_LIGHT_SETTINGS.intensity)
  );
  setScaledPosition(rim, lighting.rim?.position, positionScale, DEFAULT_RIM_LIGHT_SETTINGS.position);
  addIfEnabled(rim, lighting.rim?.enabled !== false);

  const spot = new THREE.SpotLight(
    lighting.spot?.color || "#ffffff",
    toFiniteNumber(lighting.spot?.intensity, 0),
    toFiniteNumber(lighting.spot?.distance, 0) * positionScale,
    toFiniteNumber(lighting.spot?.angle, Math.PI / 6)
  );
  setScaledPosition(spot, lighting.spot?.position, positionScale, { x: 160, y: -120, z: 140 });
  addIfEnabled(spot, lighting.spot?.enabled === true);
  scene.add(spot.target);

  const point = new THREE.PointLight(
    lighting.point?.color || "#ffffff",
    toFiniteNumber(lighting.point?.intensity, 0),
    toFiniteNumber(lighting.point?.distance, 0) * positionScale
  );
  setScaledPosition(point, lighting.point?.position, positionScale, { x: -120, y: 80, z: 140 });
  addIfEnabled(point, lighting.point?.enabled === true);
  return { directional, fill, rim, spot, point, radius, positionScale };
}

export function addFloor(scene, bounds, themeSettings, sceneScale, settingsByScale, guideSettings = null) {
  const floor = themeSettings.floor || {};
  const mode = floor.mode || THEME_FLOOR_MODES.STAGE;
  const floorEnabled = floor.enabled === true || (
    !Object.hasOwn(floor, "enabled")
      && mode !== THEME_FLOOR_MODES.NONE
      && mode !== THEME_FLOOR_MODES.GRID
  );
  const gridSettings = resolveCadGridSettings(guideSettings?.grid, { colorMode: themeSettings.colorMode });
  const gridEnabled = gridSettings.enabled === true;
  const axisSettings = guideSettings?.axis && typeof guideSettings.axis === "object" && !Array.isArray(guideSettings.axis)
    ? guideSettings.axis
    : {};
  const axisEnabled = axisSettings.enabled === true;
  if (!floorEnabled && !gridEnabled && !axisEnabled) {
    return;
  }
  const settings = renderSceneScaleSettings(sceneScale, settingsByScale);
  const { radius } = centerAndRadiusFromBounds(bounds, sceneScale, settingsByScale);
  // The stage floor sits at world z=0, matching the viewer
  // (resolveRuntimeModelFloorZ in lib/viewer/modelRuntime.js). This path used to
  // glue the floor to bounds.min[2], which silently re-grounded EVERY model: a
  // part authored 200 mm above the floor rendered as if it were resting on it,
  // and snapshots could never agree with the viewer about whether something was
  // grounded. Follow the model only downward, so geometry below z=0 pushes the
  // floor down rather than clipping through it.
  const boundsMinZ = Array.isArray(bounds?.min) ? toFiniteNumber(bounds.min[2]) : 0;
  // The presentation floor may follow geometry below z=0. Inspection guides
  // are independent scene references and always stay at the world origin.
  const followModel = floorEnabled && floor.followModel !== false;
  const minZ = followModel ? Math.min(0, boundsMinZ) : 0;
  if (gridEnabled) {
    const gridConfig = buildGridConfig(radius, sceneScale);
    const grid = new THREE.GridHelper(
      gridConfig.size,
      gridConfig.divisions,
      gridSettings.centerColor,
      gridSettings.cellColor
    );
    const materials = Array.isArray(grid.material) ? grid.material : [grid.material];
    for (const material of materials) {
      material.transparent = true;
      material.opacity = clamp(
        toFiniteNumber(gridSettings.opacity, DEFAULT_FLOOR_GRID_SETTINGS.opacity),
        0,
        1
      );
      material.depthWrite = false;
      material.toneMapped = false;
    }
    grid.rotation.x = Math.PI / 2;
    grid.position.set(0, 0, 0);
    scene.add(grid);
  }
  if (axisEnabled) {
    // Vertical line through the world origin, depth-tested so model surfaces
    // in front of it hide it.
    const axisLength = Math.max(radius, 1) * FLOOR_AXIS_RADIUS_MULTIPLE;
    const axis = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, -axisLength),
        new THREE.Vector3(0, 0, axisLength)
      ]),
      new THREE.LineBasicMaterial({
        color: axisSettings.color
          || gridSettings.centerColor
          || DEFAULT_FLOOR_GRID_SETTINGS.centerColor,
        transparent: true,
        opacity: clamp(toFiniteNumber(axisSettings.opacity, DEFAULT_FLOOR_AXIS_SETTINGS.opacity), 0, 1),
        depthWrite: false,
        toneMapped: false
      })
    );
    axis.position.set(0, 0, 0);
    scene.add(axis);
  }
  if (!floorEnabled) {
    return;
  }
  const stageSize = getStageFloorSize(radius, sceneScale);
  const lightingScopeRadius = getProportionalLightingScopeRadius(radius, sceneScale);
  scene.add(createStageFloorPlane(THREE, BASE_VIEWER_THEME, themeSettings, stageSize, minZ, 0));
  const glow = createStageFloorGlowPlane(
    THREE,
    themeSettings,
    lightingScopeRadius,
    stageSize,
    minZ,
    sceneScale
  );
  if (glow) {
    scene.add(glow);
  }
  const shadow = createStageShadowPlane(THREE, themeSettings, stageSize, minZ);
  if (shadow) {
    scene.add(shadow);
  }
}

export function boundsCorners(bounds) {
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
    toFiniteNumber(corner[0]),
    toFiniteNumber(corner[1]),
    toFiniteNumber(corner[2])
  ));
}

export function framePadding(job = {}) {
  const rawPadding = job.output?.padding ?? job.output?.paddingPercent;
  return clamp(toFiniteNumber(rawPadding, 0.04), 0, 0.15);
}

export function frameHalfHeightForView(view, bounds, width, height, padding, sceneScale, settingsByScale) {
  const settings = renderSceneScaleSettings(sceneScale, settingsByScale);
  const resolvedView = resolveRenderView(view, RENDER_VIEW_PRESETS, { strict: false });
  const direction = new THREE.Vector3(...resolvedView.direction).normalize();
  const up = new THREE.Vector3(...resolvedView.up).normalize();
  const right = new THREE.Vector3().crossVectors(direction, up).normalize();
  const screenUp = new THREE.Vector3().crossVectors(right, direction).normalize();
  const corners = boundsCorners(bounds);
  const xs = corners.map((corner) => corner.dot(right));
  const ys = corners.map((corner) => corner.dot(screenUp));
  const spanX = Math.max(Math.max(...xs) - Math.min(...xs), settings.minBoundsSpan);
  const spanY = Math.max(Math.max(...ys) - Math.min(...ys), settings.minBoundsSpan);
  const aspect = Math.max(width / Math.max(height, 1), 0.01);
  const safeContentScale = Math.max(1 - (padding * 2), 0.1);
  return Math.max(
    spanY / (2 * safeContentScale),
    spanX / (2 * aspect * safeContentScale),
    settings.minBoundsSpan / 2
  ) / normalizeCameraZoom(resolvedView.zoom, 1);
}

export function fitOrthographicCamera(camera, view, bounds, width, height, {
  lockedHalfHeight = null,
  padding = 0.12,
  sceneScale = RENDER_SCENE_SCALE.CAD,
  settingsByScale
} = {}) {
  const settings = renderSceneScaleSettings(sceneScale, settingsByScale);
  const resolvedCamera = resolveCameraSnapshot(view, bounds, {
    sceneScale,
    settingsByScale,
    strict: false
  });
  const target = new THREE.Vector3(...resolvedCamera.target);
  camera.position.set(...resolvedCamera.position);
  camera.up.set(...resolvedCamera.up);
  camera.lookAt(target);
  const aspect = Math.max(width / Math.max(height, 1), 0.01);
  const explicitHalfHeight = lockedHalfHeight == null
    ? resolvedCamera.orthographicHalfHeight
    : null;
  const halfHeight = lockedHalfHeight || explicitHalfHeight || frameHalfHeightForView(resolvedCamera.view, bounds, width, height, padding, sceneScale, settingsByScale);
  // A canonical half-height is the stored orthographic frustum before camera
  // zoom, matching the interactive camera's cadHalfHeight. Automatic and
  // sequence fits already fold zoom into their computed half-height.
  camera.zoom = explicitHalfHeight
    ? normalizeCameraZoom(resolvedCamera.zoom, 1)
    : 1;
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.left = -halfHeight * aspect;
  camera.right = halfHeight * aspect;
  camera.near = 0.01;
  camera.far = Math.max(resolvedCamera.radius * 12, settings.minCameraFar);
  camera.updateProjectionMatrix();
  return resolvedCamera;
}

export function fitPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
  framePoints = null,
  padding = 0.12,
  sceneScale = RENDER_SCENE_SCALE.CAD,
  settingsByScale,
  strict = true
} = {}) {
  const settings = renderSceneScaleSettings(sceneScale, settingsByScale);
  const resolvedCamera = resolveCameraSnapshot(cameraSpec, bounds, {
    sceneScale,
    settingsByScale,
    strict
  });
  camera.aspect = Math.max(width / Math.max(height, 1), 0.01);
  if (resolvedCamera.focalLength != null) {
    camera.setFocalLength(resolvedCamera.focalLength);
  }
  camera.position.set(...resolvedCamera.position);
  camera.up.set(...resolvedCamera.up);
  camera.zoom = normalizeCameraZoom(resolvedCamera.zoom, 1);
  camera.near = Math.max(resolvedCamera.radius / 1200, 0.01);
  camera.far = Math.max(resolvedCamera.radius * 600, settings.minCameraFar, 2000);
  const target = new THREE.Vector3(...resolvedCamera.target);
  camera.lookAt(target);
  camera.updateMatrixWorld(true);

  // A supplied position is authored framing. Automatic cameras instead fit
  // their subject to the requested output aspect and padding. The old fixed
  // 3.2-radius distance left flat and round parts occupying barely half the
  // image, especially in Render's default perspective projection.
  if (!resolvedCamera.hasExplicitPosition) {
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
    const screenUp = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
    const backward = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 2).normalize();
    const relative = new THREE.Vector3();
    const aspect = camera.aspect;
    const safeContentScale = Math.max(1 - (clamp(toFiniteNumber(padding, 0.12), 0, 0.45) * 2), 0.1);
    // Camera zoom remains an explicit compositional zoom, matching the
    // orthographic snapshot contract. It intentionally does not disappear
    // into the automatic distance calculation.
    const verticalSlope = Math.max(Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) * safeContentScale, 1e-6);
    const horizontalSlope = Math.max(verticalSlope * aspect, 1e-6);
    const nearClearance = camera.near * 2;
    let distance = Math.max(settings.minCameraDistance || 0, nearClearance);
    let pointCount = 0;
    const includePoint = (point) => {
      if (!point?.isVector3 || ![point.x, point.y, point.z].every(Number.isFinite)) {
        return;
      }
      relative.copy(point).sub(target);
      const depthOffset = relative.dot(backward);
      distance = Math.max(
        distance,
        depthOffset + Math.abs(relative.dot(right)) / horizontalSlope,
        depthOffset + Math.abs(relative.dot(screenUp)) / verticalSlope,
        depthOffset + nearClearance
      );
      pointCount += 1;
    };
    if (framePoints && typeof framePoints[Symbol.iterator] === "function") {
      for (const point of framePoints) includePoint(point);
    }
    if (!pointCount) {
      for (const point of boundsCorners(bounds)) includePoint(point);
    }
    camera.position.copy(target).addScaledVector(backward, distance);
    camera.lookAt(target);
    resolvedCamera.position = camera.position.toArray();
    resolvedCamera.direction = backward.toArray();
    resolvedCamera.view.direction = backward.toArray();
  }
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return resolvedCamera;
}

function groundPlaneFrustumDepths(camera, groundZ) {
  if (!camera?.isPerspectiveCamera && !camera?.isOrthographicCamera) return [];
  const depths = [];
  const cameraPosition = new THREE.Vector3();
  const origin = new THREE.Vector3();
  const direction = new THREE.Vector3();
  const sample = new THREE.Vector3();
  const hit = new THREE.Vector3();
  camera.getWorldPosition(cameraPosition);

  // A plane clipped by a convex perspective frustum reaches its nearest
  // positive camera-space depth on the viewport boundary. Its depth over each
  // boundary edge is monotonic, so the four corner rays are sufficient here.
  for (const [x, y] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
    if (camera.isPerspectiveCamera) {
      origin.copy(cameraPosition);
      sample.set(x, y, 0).unproject(camera);
      direction.subVectors(sample, origin);
    } else {
      origin.set(x, y, -1).unproject(camera);
      direction.set(0, 0, -1).transformDirection(camera.matrixWorld);
    }
    if (Math.abs(direction.z) <= 1e-12) continue;
    const distance = (groundZ - origin.z) / direction.z;
    hit.copy(origin).addScaledVector(direction, distance);
    const depth = -hit.applyMatrix4(camera.matrixWorldInverse).z;
    if (Number.isFinite(depth)) depths.push(depth);
  }
  // Orthographic rays can meet the floor behind the eye plane at low angles.
  // Their signed depths remain meaningful: an orthographic projection permits
  // a negative near plane, equivalent to moving the eye back without reframing.
  return camera.isOrthographicCamera ? depths : depths.filter((depth) => depth > 0);
}

// A close camera can enter an assembly's mostly empty aggregate box while
// remaining well outside every visible part. Fit those parts independently so
// the near plane does not collapse and make thin surfaces fight for depth.
// This uses existing occurrence bounds, never vertex scans or CAD picking.
function closeupSubjectNear(camera, displayRecords, modelGroup) {
  if (!displayRecords?.length) return null;
  const frustum = new THREE.Frustum().setFromProjectionMatrix(
    new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse),
    camera.coordinateSystem, camera.reversedDepth
  );
  // Only the side planes: the previous near/far must not exclude a part that
  // the camera has just moved through or approached.
  const sides = frustum.planes.slice(0, 4);
  const box = new THREE.Box3(), point = new THREE.Vector3();
  const center = new THREE.Vector3(), halfSize = new THREE.Vector3();
  const world = new THREE.Matrix4(), view = new THREE.Matrix4();
  modelGroup?.updateWorldMatrix?.(true, false);
  let nearest = Infinity;
  for (const record of displayRecords) {
    if (record.mesh?.visible === false) continue;
    const bounds = record.partBounds;
    if (!Array.isArray(bounds?.min) || !Array.isArray(bounds?.max)
      || bounds.min.length !== 3 || bounds.max.length !== 3
      || !bounds.min.every(Number.isFinite) || !bounds.max.every(Number.isFinite)
      || bounds.max.some((value, axis) => value < bounds.min[axis])
      || record.effectDeformation || record.tubeDeformationState?.active || record.tubeGpuState?.active) return null;
    world.identity();
    if (record.effectMatrix) world.premultiply(record.effectMatrix);
    if (record.explodedViewMatrix) world.premultiply(record.explodedViewMatrix);
    if (modelGroup) world.premultiply(modelGroup.matrixWorld);
    if (!world.elements.every(Number.isFinite)) return null;
    box.min.fromArray(bounds.min); box.max.fromArray(bounds.max);
    box.getCenter(center); box.getSize(halfSize).multiplyScalar(0.5);
    box.applyMatrix4(world);
    if (sides.some(plane => {
      point.set(plane.normal.x >= 0 ? box.max.x : box.min.x,
        plane.normal.y >= 0 ? box.max.y : box.min.y,
        plane.normal.z >= 0 ? box.max.z : box.min.z);
      return plane.distanceToPoint(point) < 0;
    })) continue;
    view.multiplyMatrices(camera.matrixWorldInverse, world);
    const depth = -center.applyMatrix4(view).z;
    const extent = Math.abs(view.elements[2]) * halfSize.x
      + Math.abs(view.elements[6]) * halfSize.y + Math.abs(view.elements[10]) * halfSize.z;
    if (depth + extent <= 0) continue;
    nearest = Math.min(nearest, depth - extent);
  }
  return Number.isFinite(nearest) ? nearest * 0.98 : null;
}

// Ordinary depth is required for the photographic shadow pass. Fit its range
// to the subject as the camera moves, retaining room behind it for the stage.
// The bounds corners cover the model; frustum-corner intersections cover the
// foreground ground that is actually visible without forcing an arbitrary
// scene-scale near plane.
export function fitCameraDepthToBounds(camera, bounds, {
  displayRecords, modelGroup, groundZ = bounds?.min?.[2], gridBounds = null
} = {}) {
  if (!camera?.isCamera || !Array.isArray(bounds?.min) || !Array.isArray(bounds?.max)
    || bounds.min.length < 3 || bounds.max.length < 3
    || !bounds.min.every(Number.isFinite) || !bounds.max.every(Number.isFinite)
    || bounds.max.some((value, axis) => value < bounds.min[axis])) return false;
  camera.updateMatrixWorld(true);
  const corners = boundsCorners(bounds);
  const depths = corners.map((point) => -point.applyMatrix4(camera.matrixWorldInverse).z);
  const radius = Math.max(Math.hypot(...bounds.max.map((value, axis) => value - bounds.min[axis])) / 2, 1e-6);
  let subjectNear = Math.min(...depths) - radius * 0.1;
  if (subjectNear <= radius * 1e-5) {
    subjectNear = closeupSubjectNear(camera, displayRecords, modelGroup) ?? subjectNear;
  }
  // Guides exist independently of the photographic floor. Fit their visible
  // plane too, otherwise the model's near plane slices off foreground grid lines.
  const planeHeights = [...new Set([groundZ, gridBounds?.min?.[2]].filter(Number.isFinite))];
  const groundDepths = planeHeights.flatMap(z => groundPlaneFrustumDepths(camera, z));
  const nearestGroundDepth = Math.min(...groundDepths);
  const groundNear = nearestGroundDepth * (nearestGroundDepth < 0 ? 1.02 : 0.98);
  const near = camera.isOrthographicCamera && groundNear < 0
    ? Math.min(subjectNear, groundNear)
    : Math.max(Math.min(subjectNear, groundNear), radius * 1e-5, 1e-7);
  const gridDepths = gridBounds ? boundsCorners(gridBounds).map(point => -point.applyMatrix4(camera.matrixWorldInverse).z) : [];
  const far = Math.max(Math.max(...depths, ...gridDepths) + radius * PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER, near * 2);
  const unchanged = (actual, next) => Math.abs(actual - next)
    <= Math.max(Math.abs(next) * 1e-6, 1e-12);
  if (unchanged(camera.near, near) && unchanged(camera.far, far)) return false;
  camera.near = near;
  camera.far = far;
  camera.updateProjectionMatrix();
  return true;
}

export function lockedFrameHalfHeight(outputs, bounds, width, height, job, sceneScale, settingsByScale) {
  const padding = framePadding(job);
  return Math.max(
    ...outputs.map((output) => {
      const outputWidth = toFiniteNumber(output.width, width);
      const outputHeight = toFiniteNumber(output.height, height);
      return frameHalfHeightForView(resolveRenderView(output.camera || job.camera || "iso"), bounds, outputWidth, outputHeight, padding, sceneScale, settingsByScale);
    }),
    renderSceneScaleSettings(sceneScale, settingsByScale).minBoundsSpan / 2
  );
}

export function outputSize(output, job) {
  return {
    width: Math.max(1, Math.floor(toFiniteNumber(output.width, job.output?.width || 1400))),
    height: Math.max(1, Math.floor(toFiniteNumber(output.height, job.output?.height || 900)))
  };
}

export function snapshotUsesLogarithmicDepthBuffer(job = {}) {
  return !resolveViewSettings(job.display ?? {}).lighting.enabled;
}

export function configurePngRenderer(width, height, job, {
  defaultRenderScale = 1,
  toneMappingExposure = 1
} = {}) {
  const renderer = createCadWebGlRenderer(THREE, {
    preserveDrawingBuffer: true,
    // Three's logarithmic depth shaders do not compare correctly with the
    // standard shadow map depth. Render uses a model-fitted camera range and
    // ordinary depth; CAD inspection retains its wide-range depth buffer.
    logarithmicDepthBuffer: snapshotUsesLogarithmicDepthBuffer(job)
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = Math.max(toFiniteNumber(toneMappingExposure, 1), 0.05);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.setPixelRatio(clamp(toFiniteNumber(job.output?.renderScale, defaultRenderScale), 1, 3));
  renderer.setSize(width, height, false);
  document.body.innerHTML = "";
  document.body.appendChild(renderer.domElement);
  return renderer;
}

export function dataUrlFromRenderer(renderer, mime = "image/png") {
  return renderer.domElement.toDataURL(mime);
}

export function shouldBurnInViewLabels(job = {}) {
  return typeof job.output?.viewLabels === "boolean" ? job.output.viewLabels : false;
}

export function drawBurnedInLabel(context, label, width, height, {
  corner = "top-left",
  fill = "#111827",
  background = "rgba(255, 255, 255, 0.9)",
  border = "rgba(17, 24, 39, 0.42)"
} = {}) {
  const text = String(label || "").trim();
  if (!text) {
    return;
  }
  const safeWidth = Math.max(width, 1);
  const safeHeight = Math.max(height, 1);
  const fontSize = Math.max(18, Math.min(Math.round(safeWidth * 0.018), 32));
  const padX = Math.round(fontSize * 0.72);
  const padY = Math.round(fontSize * 0.42);
  context.save();
  context.font = `700 ${fontSize}px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`;
  context.textBaseline = "top";
  const metrics = context.measureText(text);
  const boxWidth = Math.ceil(metrics.width + padX * 2);
  const boxHeight = Math.ceil(fontSize + padY * 2);
  const margin = Math.max(18, Math.round(Math.min(safeWidth, safeHeight) * 0.024));
  const x = corner.includes("right") ? safeWidth - margin - boxWidth : margin;
  const y = corner.includes("bottom") ? safeHeight - margin - boxHeight : margin;
  context.fillStyle = background;
  context.strokeStyle = border;
  context.lineWidth = Math.max(1, Math.round(fontSize * 0.06));
  context.beginPath();
  context.roundRect(x, y, boxWidth, boxHeight, Math.round(fontSize * 0.28));
  context.fill();
  context.stroke();
  context.fillStyle = fill;
  context.fillText(text, x + padX, y + padY);
  context.restore();
}

export function rendererDataUrlWithOptionalLabel(renderer, label, job, outputSize = {}) {
  const source = renderer.domElement;
  // `setPixelRatio` deliberately makes the WebGL drawing buffer larger than
  // the requested output for supersampling. The snapshot contract, however,
  // is expressed in output pixels: encode a high-quality resample rather than
  // leaking the implementation-sized drawing buffer into the PNG.
  const width = Math.max(1, Math.floor(toFiniteNumber(outputSize.width, toFiniteNumber(source.width, 1))));
  const height = Math.max(1, Math.floor(toFiniteNumber(outputSize.height, toFiniteNumber(source.height, 1))));
  const needsResample = source.width !== width || source.height !== height;
  if (!needsResample && !shouldBurnInViewLabels(job)) {
    return dataUrlFromRenderer(renderer);
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Unable to prepare snapshot PNG output");
  }
  context.imageSmoothingEnabled = true;
  if ("imageSmoothingQuality" in context) {
    context.imageSmoothingQuality = "high";
  }
  context.drawImage(source, 0, 0, source.width, source.height, 0, 0, width, height);
  if (shouldBurnInViewLabels(job)) {
    drawBurnedInLabel(context, label, width, height);
  }
  return canvas.toDataURL("image/png");
}

import {
  clampSceneModelRadius,
  VIEWER_SCENE_SCALE,
  getSceneScaleSettings
} from "./sceneScale.js";
import { BASE_VIEWER_THEME } from "./stageTheme.js";
import {
  DEFAULT_FLOOR_AXIS_SETTINGS,
  DEFAULT_FLOOR_GRID_SETTINGS,
  FLOOR_AXIS_RADIUS_MULTIPLE,
  MAX_FLOOR_GRID_DENSITY,
  MIN_FLOOR_GRID_DENSITY,
  THEME_FLOOR_MODES
} from "../themeSettings.js";
import { DEFAULT_AUTO_ZOOM_PADDING } from "./autoZoom.js";

export const DEFAULT_GRID_DIVISIONS = 28;
export const GRID_TARGET_VISIBLE_CELLS = 1.25;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeGridDensity(value) {
  const density = Number(value);
  return Number.isFinite(density)
    ? clamp(density, MIN_FLOOR_GRID_DENSITY, MAX_FLOOR_GRID_DENSITY)
    : DEFAULT_FLOOR_GRID_SETTINGS.density;
}

function resolveGridStyle(viewerTheme = {}, floorSettings = {}) {
  const gridSettings = floorSettings?.grid || {};
  return {
    centerColor: gridSettings?.centerColor
      || floorSettings?.gridCenterColor
      || floorSettings?.gridCenter
      || viewerTheme?.gridCenter
      || BASE_VIEWER_THEME.gridCenter,
    cellColor: gridSettings?.cellColor
      || floorSettings?.gridCellColor
      || floorSettings?.gridCell
      || viewerTheme?.gridCell
      || BASE_VIEWER_THEME.gridCell,
    opacity: Number.isFinite(Number(gridSettings?.opacity))
      ? clamp(Number(gridSettings.opacity), 0, 1)
      : Number.isFinite(Number(floorSettings?.gridOpacity))
      ? clamp(Number(floorSettings.gridOpacity), 0, 1)
      : (viewerTheme?.gridOpacity ?? BASE_VIEWER_THEME.gridOpacity)
  };
}

export function niceGridStep(minimumStep) {
  if (!Number.isFinite(minimumStep) || minimumStep <= 0) {
    return getSceneScaleSettings(VIEWER_SCENE_SCALE.CAD).minGridSize / DEFAULT_GRID_DIVISIONS;
  }
  const exponent = Math.floor(Math.log10(minimumStep));
  const base = 10 ** exponent;
  for (const multiplier of [1, 2, 5, 10]) {
    const step = base * multiplier;
    if (step >= minimumStep) {
      return step;
    }
  }
  return base * 10;
}

export function buildGridConfig(radius, sceneScaleMode, floorSettings = {}) {
  const gridDensity = normalizeGridDensity(floorSettings?.grid?.density ?? floorSettings?.gridDensity);
  const safeRadius = clampSceneModelRadius(radius, sceneScaleMode);
  const targetVisibleCells = GRID_TARGET_VISIBLE_CELLS * gridDensity;
  const cellSize = (safeRadius * 2 * DEFAULT_AUTO_ZOOM_PADDING) / targetVisibleCells;
  let divisions = Math.max(2, Math.round(DEFAULT_GRID_DIVISIONS * gridDensity));
  if (divisions % 2 !== 0) {
    divisions += 1;
  }
  return {
    size: cellSize * divisions,
    cellSize,
    divisions
  };
}

export function updateGridHelper(
  runtime,
  viewerTheme,
  radius,
  floorZ = 0,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  floorMode = THEME_FLOOR_MODES.STAGE,
  { disposeSceneObject = () => {}, floorSettings = {} } = {}
) {
  if (!runtime?.THREE || !runtime?.scene) {
    return;
  }
  runtime.gridRadius = radius;
  runtime.gridFloorZ = floorZ;
  const gridEnabled = floorSettings?.grid?.enabled === true || floorMode === THEME_FLOOR_MODES.GRID;
  runtime.floorMode = gridEnabled ? THEME_FLOOR_MODES.GRID : floorMode;
  if (!gridEnabled) {
    disposeSceneObject(runtime.gridHelper);
    runtime.gridHelper = null;
    runtime.gridConfig = null;
    return;
  }
  const nextConfig = {
    ...buildGridConfig(radius, sceneScaleMode, floorSettings),
    ...resolveGridStyle(viewerTheme, floorSettings)
  };
  const currentConfig = runtime.gridConfig;
  if (
    currentConfig &&
    currentConfig.size === nextConfig.size &&
    currentConfig.cellSize === nextConfig.cellSize &&
    currentConfig.divisions === nextConfig.divisions &&
    currentConfig.centerColor === nextConfig.centerColor &&
    currentConfig.cellColor === nextConfig.cellColor &&
    currentConfig.opacity === nextConfig.opacity
  ) {
    if (runtime.gridHelper) {
      runtime.gridHelper.rotation.x = Math.PI / 2;
    }
    runtime.gridHelper?.position.set(0, 0, floorZ);
    return;
  }

  disposeSceneObject(runtime.gridHelper);
  runtime.gridHelper = new runtime.THREE.GridHelper(
    nextConfig.size,
    nextConfig.divisions,
    nextConfig.centerColor,
    nextConfig.cellColor
  );
  const materials = Array.isArray(runtime.gridHelper.material)
    ? runtime.gridHelper.material
    : [runtime.gridHelper.material];
  for (const material of materials) {
    material.transparent = true;
    material.opacity = nextConfig.opacity;
    material.depthWrite = false;
    material.toneMapped = false;
  }
  runtime.gridHelper.rotation.x = Math.PI / 2;
  runtime.gridHelper.position.set(0, 0, floorZ);
  runtime.scene.add(runtime.gridHelper);
  runtime.gridConfig = nextConfig;
}

function resolveAxisConfig(radius, viewerTheme = {}, floorSettings = {}) {
  const axisSettings = floorSettings?.axis || {};
  return {
    color: axisSettings.color
      || floorSettings?.grid?.centerColor
      || viewerTheme?.gridCenter
      || BASE_VIEWER_THEME.gridCenter,
    opacity: clamp(
      Number.isFinite(Number(axisSettings.opacity))
        ? Number(axisSettings.opacity)
        : DEFAULT_FLOOR_AXIS_SETTINGS.opacity,
      0,
      1
    ),
    length: Math.max(radius, 1) * FLOOR_AXIS_RADIUS_MULTIPLE
  };
}

// A vertical line through the world origin, rising from the floor along +Z.
// Kept separate from the grid so a theme can show either on its own.
export function updateOriginAxis(
  runtime,
  viewerTheme,
  radius,
  floorZ = 0,
  { disposeSceneObject = () => {}, floorSettings = {} } = {}
) {
  if (!runtime?.THREE || !runtime?.scene) {
    return;
  }
  const THREE = runtime.THREE;
  if (floorSettings?.axis?.enabled !== true) {
    disposeSceneObject(runtime.originAxis);
    runtime.originAxis = null;
    runtime.originAxisConfig = null;
    return;
  }
  const nextConfig = resolveAxisConfig(radius, viewerTheme, floorSettings);
  const currentConfig = runtime.originAxisConfig;
  if (
    runtime.originAxis &&
    currentConfig &&
    currentConfig.color === nextConfig.color &&
    currentConfig.opacity === nextConfig.opacity &&
    currentConfig.length === nextConfig.length
  ) {
    runtime.originAxis.position.set(0, 0, floorZ);
    return;
  }

  disposeSceneObject(runtime.originAxis);
  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, -nextConfig.length),
    new THREE.Vector3(0, 0, nextConfig.length)
  ]);
  // Depth-tested like the grid: the axis is scene furniture, so any model
  // surface in front of it hides it rather than being drawn over.
  const material = new THREE.LineBasicMaterial({
    color: nextConfig.color,
    transparent: true,
    opacity: nextConfig.opacity,
    depthWrite: false,
    toneMapped: false
  });
  runtime.originAxis = new THREE.Line(geometry, material);
  runtime.originAxis.position.set(0, 0, floorZ);
  runtime.scene.add(runtime.originAxis);
  runtime.originAxisConfig = nextConfig;
}

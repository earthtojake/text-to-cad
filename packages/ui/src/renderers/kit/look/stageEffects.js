// The look's stage: the lighting rig scaled to the model, the floor with its glow
// and shadow catcher, and the grid and origin axes. Callers pass the runtime, the
// resolved theme/settings values and the model's radius; nothing here reads what
// the model is.
import {
  VIEWER_SCENE_SCALE,
  getProportionalLightingScopeRadius,
  getLightingScopeRadius,
  getSceneScaleSettings
} from "@hardcore/core/lib/viewer/sceneScale.js";
import {
  applyRuntimeModelBounds
} from "@hardcore/core/lib/viewer/modelRuntime.js";
import {
  THEME_FLOOR_MODES
} from "@hardcore/core/lib/themeSettings.js";
import {
  getStageFloorSize,
  createStageFloorPlane,
  createStageFloorGlowPlane,
  createStageShadowPlane
} from "@hardcore/core/lib/viewer/stageTheme.js";
import {
  updateOriginAxis as updateStageOriginAxis,
  updateGridHelper as updateStageGridHelper
} from "@hardcore/core/lib/viewer/stageGrid.js";
import {
  disposeSceneObject
} from "../viewport/sceneObjects.js";

export const DEFAULT_LIGHTING = {
  toneMappingExposure: 1.08,
  hemisphereSky: "#d3dde6",
  hemisphereGround: "#090c16",
  hemisphereIntensity: 1.62,
  keyLightColor: "#d6e0ea",
  keyLightIntensity: 0.82,
  fillLightColor: "#6b7f95",
  fillLightIntensity: 0.46,
  rimLightColor: "#6db6e8",
  rimLightIntensity: 0.04
};

export function getStageEffectRadius(radius, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  return getProportionalLightingScopeRadius(radius, sceneScaleMode);
}

export function getStageEffectScale(radius, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  const referenceRadius = Math.max(
    getLightingScopeRadius(sceneScaleMode),
    getSceneScaleSettings(sceneScaleMode).minModelRadius
  );
  return getStageEffectRadius(radius, sceneScaleMode) / referenceRadius;
}

export function setScaledLightPosition(light, position = {}, scale = 1) {
  light?.position?.set?.(
    (Number(position.x) || 0) * scale,
    (Number(position.y) || 0) * scale,
    (Number(position.z) || 0) * scale
  );
}

export function scaledLightDistance(distance, scale = 1) {
  const numericDistance = Number(distance);
  return Number.isFinite(numericDistance) && numericDistance > 0
    ? numericDistance * scale
    : 0;
}

export function syncRuntimeScaledLighting(runtime, lightingSettings = {}, radius, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  const scale = getStageEffectScale(radius, sceneScaleMode);
  setScaledLightPosition(runtime?.keyLight, lightingSettings.directional?.position, scale);
  if (lightingSettings.fill?.position) {
    setScaledLightPosition(runtime?.fillLight, lightingSettings.fill.position, scale);
  }
  if (lightingSettings.rim?.position) {
    setScaledLightPosition(runtime?.rimLight, lightingSettings.rim.position, scale);
  }
  setScaledLightPosition(runtime?.spotLight, lightingSettings.spot?.position, scale);
  setScaledLightPosition(runtime?.pointLight, lightingSettings.point?.position, scale);
  if (runtime?.spotLight) {
    runtime.spotLight.distance = scaledLightDistance(lightingSettings.spot?.distance, scale);
  }
  if (runtime?.pointLight) {
    runtime.pointLight.distance = scaledLightDistance(lightingSettings.point?.distance, scale);
  }
}

export function syncRuntimeScaledLightingAndShadow(
  THREE,
  runtime,
  lightingSettings = {},
  radius,
  bounds,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  shadowMapSize = 2048
) {
  syncRuntimeScaledLighting(runtime, lightingSettings, radius, sceneScaleMode);
  if (THREE && bounds && runtime?.keyLight?.shadow?.camera) {
    applyRuntimeModelBounds(THREE, runtime, bounds, sceneScaleMode, { shadowMapSize });
  }
}

// The stage group holds only what this module put there (floor, glow, shadow).
function clearStageGroup(group) {
  for (const child of [...group.children]) {
    disposeSceneObject(child);
  }
}

export function updateStageEffects(runtime, viewerTheme, themeSettings, radius, floorZ = 0, floorMode = THEME_FLOOR_MODES.STAGE, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  if (!runtime?.THREE || !runtime?.stageGroup) {
    return;
  }

  clearStageGroup(runtime.stageGroup);

  if (floorMode !== THEME_FLOOR_MODES.STAGE) {
    return;
  }

  const stageScaleMode = sceneScaleMode;
  const floorSize = getStageFloorSize(radius, stageScaleMode);
  const lightingScopeRadius = getStageEffectRadius(radius, stageScaleMode);
  runtime.stageGroup.add(createStageFloorPlane(runtime.THREE, viewerTheme, themeSettings, floorSize, floorZ, 0));
  const glowPlane = createStageFloorGlowPlane(
    runtime.THREE,
    themeSettings,
    lightingScopeRadius,
    floorSize,
    floorZ,
    stageScaleMode
  );
  if (glowPlane) {
    runtime.stageGroup.add(glowPlane);
  }
  const shadowPlane = createStageShadowPlane(runtime.THREE, themeSettings, floorSize, floorZ);
  if (shadowPlane) {
    runtime.stageGroup.add(shadowPlane);
  }
}

export function updateGridHelper(
  runtime,
  viewerTheme,
  radius,
  floorZ = 0,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  floorMode = THEME_FLOOR_MODES.STAGE,
  floorSettings = {}
) {
  // Inspection guides live on the authored world plane. The physical Render
  // floor may follow the model, but that placement belongs to stage effects.
  updateStageOriginAxis(runtime, viewerTheme, radius, 0, {
    disposeSceneObject,
    floorSettings
  });
  const result = updateStageGridHelper(runtime, viewerTheme, radius, 0, sceneScaleMode, floorMode, {
    disposeSceneObject,
    floorSettings
  });
  runtime.gridFloorZ = floorZ;
  runtime.floorMode = floorMode;
  return result;
}

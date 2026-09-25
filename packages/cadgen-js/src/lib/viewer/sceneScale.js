export const VIEWER_SCENE_SCALE = Object.freeze({
  CAD: "cad",
  URDF: "urdf"
});

const SCENE_SCALE_SETTINGS = Object.freeze({
  [VIEWER_SCENE_SCALE.CAD]: Object.freeze({
    minModelRadius: 1,
    minGridSize: 280,
    lightingScopeRadius: 140,
    lightingReferenceModelRadius: 760
  }),
  [VIEWER_SCENE_SCALE.URDF]: Object.freeze({
    minModelRadius: 0.05,
    minGridSize: 0.28,
    lightingScopeRadius: 0.14,
    lightingReferenceModelRadius: 0.76
  })
});

const SHADOW_SETTINGS = Object.freeze({
  [VIEWER_SCENE_SCALE.CAD]: Object.freeze({
    minExtent: 60,
    normalBias: 0.024,
    radius: 14
  }),
  [VIEWER_SCENE_SCALE.URDF]: Object.freeze({
    minExtent: 0.55,
    normalBias: 0.000012,
    radius: 14
  })
});

export function normalizeSceneScaleMode(value) {
  return value === VIEWER_SCENE_SCALE.URDF
    ? VIEWER_SCENE_SCALE.URDF
    : VIEWER_SCENE_SCALE.CAD;
}

export function getSceneScaleSettings(value) {
  return SCENE_SCALE_SETTINGS[normalizeSceneScaleMode(value)];
}

export function clampSceneModelRadius(radius, value) {
  const numericRadius = Number(radius);
  return Math.max(
    Number.isFinite(numericRadius) ? numericRadius : 0,
    getSceneScaleSettings(value).minModelRadius
  );
}

export function defaultSceneGridRadius(value) {
  return getSceneScaleSettings(value).minGridSize / 2;
}

export function getLightingScopeRadius(value) {
  return getSceneScaleSettings(value).lightingScopeRadius;
}

export function getProportionalLightingScopeRadius(radius, value) {
  const sceneScaleMode = normalizeSceneScaleMode(value);
  const sceneScaleSettings = getSceneScaleSettings(sceneScaleMode);
  const safeModelRadius = clampSceneModelRadius(radius, sceneScaleMode);
  const referenceModelRadius = Math.max(
    Number(sceneScaleSettings.lightingReferenceModelRadius) || 0,
    sceneScaleSettings.minModelRadius
  );
  return (safeModelRadius / referenceModelRadius) * sceneScaleSettings.lightingScopeRadius;
}

export function getShadowCameraSettings(value, { radius = 0, keyLightDistance = 0 } = {}) {
  const sceneScaleMode = normalizeSceneScaleMode(value);
  const shadowSettings = SHADOW_SETTINGS[sceneScaleMode];
  const shadowScopeRadius = clampSceneModelRadius(radius, sceneScaleMode);
  const shadowExtent = Math.max(shadowScopeRadius * 2.8, shadowSettings.minExtent);
  const shadowFar = sceneScaleMode === VIEWER_SCENE_SCALE.URDF
    ? Math.max(
      shadowScopeRadius * 8,
      Math.max(Number(keyLightDistance) || 0, 0) + (shadowScopeRadius * 6) + 1
    )
    : Math.max(shadowScopeRadius * 8, 320);

  return {
    scopeRadius: shadowScopeRadius,
    extent: shadowExtent,
    far: shadowFar,
    normalBias: shadowSettings.normalBias,
    radius: shadowSettings.radius
  };
}

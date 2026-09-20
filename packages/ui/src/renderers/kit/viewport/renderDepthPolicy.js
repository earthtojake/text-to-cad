// The interactive viewer can enable shadows at any time. Keep one compatible
// context for its lifetime; fitCameraDepthToBounds keeps near/far tight on every
// frame, including CAD closeups, instead of replacing the context per preset.
export function viewerLogarithmicDepthBuffer() {
  return false;
}

// The grid's authored Z plane and finite span matter even when Floor is off.
export function viewerDepthSettings(runtime) {
  const grid = runtime?.gridHelper;
  const halfSize = Number(runtime?.gridConfig?.size) / 2;
  const { x = 0, y = 0, z = 0 } = grid?.position || {};
  return {
    displayRecords: runtime?.displayRecords,
    modelGroup: runtime?.modelGroup,
    groundZ: runtime?.photographicStudio?.ground?.position.z ?? null,
    gridBounds: grid && grid.visible !== false && Number.isFinite(halfSize) && halfSize > 0
      ? { min: [x - halfSize, y - halfSize, z], max: [x + halfSize, y + halfSize, z] }
      : null
  };
}

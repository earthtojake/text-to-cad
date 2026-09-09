export function worldUnitsPerPixelAtDistance(camera, viewportHeightPx, distance) {
  const safeViewportHeightPx = Number(viewportHeightPx);
  const safeDistance = Number(distance);
  if (!camera || !Number.isFinite(safeViewportHeightPx) || safeViewportHeightPx <= 0 || !Number.isFinite(safeDistance) || safeDistance <= 0) {
    return null;
  }
  if (camera.isPerspectiveCamera) {
    const verticalFovRadians = (Number(camera.fov) || 0) * (Math.PI / 180);
    if (!(verticalFovRadians > 0 && verticalFovRadians < Math.PI)) {
      return null;
    }
    return (2 * safeDistance * Math.tan(verticalFovRadians / 2)) / safeViewportHeightPx;
  }
  if (camera.isOrthographicCamera) {
    const zoom = Number(camera.zoom) || 1;
    const top = Number(camera.top);
    const bottom = Number(camera.bottom);
    if (!(zoom > 0) || !Number.isFinite(top) || !Number.isFinite(bottom)) {
      return null;
    }
    return Math.abs(top - bottom) / zoom / safeViewportHeightPx;
  }
  return null;
}

export function screenLimitedPickThreshold({
  baseThreshold,
  thresholdScale = 1,
  maxScreenDistancePx,
  camera,
  viewportHeightPx,
  distance
} = {}) {
  const scaledBaseThreshold = Math.max((Number(baseThreshold) || 0) * (Number(thresholdScale) || 0), 0);
  if (!(scaledBaseThreshold > 0)) {
    return 0;
  }
  const screenDistancePx = Number(maxScreenDistancePx);
  if (!(screenDistancePx > 0)) {
    return scaledBaseThreshold;
  }
  const unitsPerPixel = worldUnitsPerPixelAtDistance(camera, viewportHeightPx, distance);
  if (!(Number.isFinite(unitsPerPixel) && unitsPerPixel > 0)) {
    return scaledBaseThreshold;
  }
  return Math.min(scaledBaseThreshold, unitsPerPixel * screenDistancePx);
}

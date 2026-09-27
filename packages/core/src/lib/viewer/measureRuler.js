import { Vector3 } from "three";

export function projectWorldPointToClient(point, camera, rect) {
  if (!Array.isArray(point) || point.length < 3 || !camera?.matrixWorldInverse || !camera?.projectionMatrix) {
    return null;
  }
  const x = Number(point[0]);
  const y = Number(point[1]);
  const z = Number(point[2]);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
    return null;
  }
  const projected = new Vector3(x, y, z)
    .applyMatrix4(camera.matrixWorldInverse)
    .applyMatrix4(camera.projectionMatrix);
  if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y) || projected.z > 1) {
    return null;
  }
  const left = Number(rect?.left) || 0;
  const top = Number(rect?.top) || 0;
  const width = Number(rect?.width) || 1;
  const height = Number(rect?.height) || 1;
  return {
    x: left + ((projected.x + 1) * 0.5 * width),
    y: top + ((1 - projected.y) * 0.5 * height)
  };
}

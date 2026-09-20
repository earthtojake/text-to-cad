import { boundsCenterAndRadius, fitDistanceForRadius } from '@hardcore/core/lib/viewer/autoZoom.js';
import { DEFAULT_VIEW_DIRECTION, WORLD_UP } from './viewportCameraKit.js';

// Interactive framing only. Snapshot/export framing retains its own policy.
// A 1.1 multiplier leaves about 4.5% of the limiting dimension on each side.
export const INTERACTIVE_CAMERA_FIT_PADDING = 1.1;

/** Fit the projected bounding box, including perspective depth, rather than
 * the rotation-invariant sphere that wastes space around long or flat models.
 * Returns a plan; never mutates the camera, controls or saved view.
 */
export function interactiveCameraFrameForBounds(THREE, {
  camera, controls, bounds, modelOffset = null, frameAspect = camera?.aspect || 1,
  minRadius = 0, viewDirection = null, viewUp = null,
  nearClip = camera?.near,
  padding = INTERACTIVE_CAMERA_FIT_PADDING,
} = {}) {
  if (!camera || !controls || !bounds?.min?.every(Number.isFinite) || !bounds?.max?.every(Number.isFinite)) return null;
  const frame = boundsCenterAndRadius(THREE, bounds, { offset: modelOffset });
  if (!frame) return null;
  const direction = viewDirection
    ? new THREE.Vector3(...viewDirection) : camera.position.clone().sub(controls.target);
  if (direction.lengthSq() < 1e-12) direction.set(...DEFAULT_VIEW_DIRECTION);
  direction.normalize();
  const up = new THREE.Vector3(...(viewUp || camera.up?.toArray() || WORLD_UP)).normalize();
  const right = new THREE.Vector3().crossVectors(up, direction);
  if (right.lengthSq() < 1e-12) right.crossVectors(Math.abs(direction.z) < 0.99
    ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0), direction);
  right.normalize();
  const screenUp = new THREE.Vector3().crossVectors(direction, right).normalize();
  const halfSize = new THREE.Vector3(...bounds.max).sub(new THREE.Vector3(...bounds.min)).multiplyScalar(0.5);
  const aspect = Math.max(Number.isFinite(frameAspect) ? frameAspect : 1, 1e-3);
  const safePadding = Math.max(Number.isFinite(padding) ? padding : INTERACTIVE_CAMERA_FIT_PADDING, 1);
  const verticalSlope = Math.tan((Number(camera.fov) || 48) * Math.PI / 360);
  const horizontalSlope = verticalSlope * aspect;
  const nearMargin = Math.max(Number(nearClip) || 0, 0) * 1.1;
  let halfHeight = Math.max(minRadius, 1e-6), distance = Math.max(minRadius, 1e-6);
  for (const x of [-halfSize.x, halfSize.x]) {
    for (const y of [-halfSize.y, halfSize.y]) {
      for (const z of [-halfSize.z, halfSize.z]) {
        const corner = new THREE.Vector3(x, y, z);
        const extentX = Math.abs(corner.dot(right)) * safePadding;
        const extentY = Math.abs(corner.dot(screenUp)) * safePadding;
        const depth = corner.dot(direction);
        halfHeight = Math.max(halfHeight, extentY, extentX / aspect);
        distance = Math.max(distance, depth + Math.max(extentX / horizontalSlope, extentY / verticalSlope, minRadius, nearMargin, 1e-6));
      }
    }
  }
  // Orthographic distance has no effect on screen occupancy; keep enough room
  // for orbit/near planes using the old conservative sphere depth.
  if (camera.isOrthographicCamera) distance = fitDistanceForRadius(camera, frame.radius, { aspect, minRadius, padding: safePadding });
  return {
    ...frame, halfHeight, distance, direction, up,
    position: frame.center.clone().addScaledVector(direction, distance),
    target: frame.center.clone(), zoom: 1,
  };
}

/** A resize uses the orientation of the last fit, not a later manual orbit. */
export function interactiveViewportFitScale(THREE, { camera, framing, aspect, minRadius = 0 }) {
  if (!framing) return null;
  const frame = interactiveCameraFrameForBounds(THREE, {
    camera, controls: { target: new THREE.Vector3() }, bounds: framing.bounds,
    frameAspect: aspect, minRadius: framing.minRadius ?? minRadius, viewDirection: framing.direction, viewUp: framing.up,
    nearClip: framing.nearClip ?? camera?.near,
  });
  return frame ? camera.isOrthographicCamera ? frame.halfHeight : frame.distance : null;
}

/** The zoom ruler is always the authored box at the default orientation.
 * Never derive 100% from a live pose, selection fit, near plane, or saved camera.
 */
export function originalModelCameraFrame(THREE, { camera, bounds, frameAspect, minRadius = 0, modelOffset = null }) {
  const radius = boundsCenterAndRadius(THREE, bounds)?.radius || minRadius;
  return interactiveCameraFrameForBounds(THREE, {
    camera, controls: { target: new THREE.Vector3() }, bounds, frameAspect, minRadius, modelOffset,
    viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP,
    nearClip: Math.max(radius / 1200, 0.01),
  });
}

import { boundsCenterAndRadius, fitDistanceForRadius } from '@cad/core/lib/viewer/autoZoom.js';
import { DEFAULT_VIEW_DIRECTION, WORLD_UP } from './viewportCameraKit.js';

// Interactive framing only. Snapshot/export framing retains its own policy.
// A 1.1 multiplier leaves about 4.5% of the limiting dimension on each side.
export const INTERACTIVE_CAMERA_FIT_PADDING = 1.1;
// A wide viewport gives the model more room above and below it: from a square viewport to
// 16:9 the vertical padding eases from 1.1 to 1.25, so at 16:9 and wider a model whose height
// limits the fit fills 80% of it rather than reaching to the top and bottom edges. A square
// or narrower viewport (a side pane, a phone) frames exactly as 1.1 always has.
const WIDE_VIEWPORT_ASPECT = 16 / 9;
const WIDE_VIEWPORT_EXTRA_VERTICAL_PADDING = 0.15;

/** The fit's padding along each screen axis for a viewport `aspect` (width / height). */
export function interactiveFitPadding(aspect) {
  const safeAspect = Number.isFinite(aspect) ? aspect : 1;
  const wide = Math.min(Math.max((safeAspect - 1) / (WIDE_VIEWPORT_ASPECT - 1), 0), 1);
  return { x: INTERACTIVE_CAMERA_FIT_PADDING, y: INTERACTIVE_CAMERA_FIT_PADDING + WIDE_VIEWPORT_EXTRA_VERTICAL_PADDING * wide };
}

/** The share of the viewport's height a fit frames in: what the strip over its top leaves
 * (`clearTop` CSS pixels of a `height`-pixel viewport), never under half of it; 1 with no strip. */
export function fitRoom(clearTop, height) {
  if (!(Number(clearTop) > 0) || !(Number(height) > 0)) return 1;
  return Math.max(1 - Number(clearTop) / Number(height), 0.5);
}

/** Fit the projected bounding box, including perspective depth, rather than
 * the rotation-invariant sphere that wastes space around long or flat models.
 * Returns a plan; never mutates the camera, controls or saved view. Without a
 * `padding` the viewport's own applies (`interactiveFitPadding`); a number is
 * both axes' padding (a library card's picture). `room`: the share of the height
 * under the view's tool strip (`fitRoom`), the bottom of the viewport: the box is
 * fitted in it and centred in it, as a flat view's fit keeps clear of the strip, so
 * the target stands above the box's centre by half of what the strip takes.
 */
export function interactiveCameraFrameForBounds(THREE, {
  camera, controls, bounds, modelOffset = null, frameAspect = camera?.aspect || 1,
  minRadius = 0, viewDirection = null, viewUp = null,
  nearClip = camera?.near,
  padding = null,
  room = 1,
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
  const share = Number(room) > 0 && Number(room) < 1 ? Math.max(Number(room), 0.5) : 1;
  const roomPadding = Number.isFinite(padding)
    ? { x: Math.max(padding, 1), y: Math.max(padding, 1) }
    : interactiveFitPadding(aspect / share);
  // Every height counts against the room's share of the viewport's.
  const fitPadding = { x: roomPadding.x, y: roomPadding.y / share };
  const verticalSlope = Math.tan((Number(camera.fov) || 48) * Math.PI / 360);
  const horizontalSlope = verticalSlope * aspect;
  const nearMargin = Math.max(Number(nearClip) || 0, 0) * 1.1;
  let halfHeight = Math.max(minRadius, 1e-6), distance = Math.max(minRadius, 1e-6);
  for (const x of [-halfSize.x, halfSize.x]) {
    for (const y of [-halfSize.y, halfSize.y]) {
      for (const z of [-halfSize.z, halfSize.z]) {
        const corner = new THREE.Vector3(x, y, z);
        const extentX = Math.abs(corner.dot(right)) * fitPadding.x;
        const extentY = Math.abs(corner.dot(screenUp)) * fitPadding.y;
        const depth = corner.dot(direction);
        halfHeight = Math.max(halfHeight, extentY, extentX / aspect);
        distance = Math.max(distance, depth + Math.max(extentX / horizontalSlope, extentY / verticalSlope, minRadius, nearMargin, 1e-6));
      }
    }
  }
  // Orthographic distance has no effect on screen occupancy; keep enough room
  // for orbit/near planes using the old conservative sphere depth.
  if (camera.isOrthographicCamera) {
    distance = fitDistanceForRadius(camera, frame.radius, { aspect, minRadius, padding: Math.max(roomPadding.x, roomPadding.y) });
  }
  // Centred in the room: the room's middle stands (1 - share) of the half height under the viewport's.
  const lift = (1 - share) * (camera.isOrthographicCamera ? halfHeight : distance * verticalSlope);
  const target = frame.center.clone().addScaledVector(screenUp, lift);
  return {
    ...frame, halfHeight, distance, direction, up,
    position: target.clone().addScaledVector(direction, distance),
    target, zoom: 1,
  };
}

/** A resize uses the orientation of the last fit, not a later manual orbit. */
export function interactiveViewportFitScale(THREE, { camera, framing, aspect, minRadius = 0, room = 1 }) {
  if (!framing) return null;
  const frame = interactiveCameraFrameForBounds(THREE, {
    camera, controls: { target: new THREE.Vector3() }, bounds: framing.bounds,
    frameAspect: aspect, minRadius: framing.minRadius ?? minRadius, viewDirection: framing.direction, viewUp: framing.up,
    nearClip: framing.nearClip ?? camera?.near, room,
  });
  return frame ? camera.isOrthographicCamera ? frame.halfHeight : frame.distance : null;
}

/** The zoom ruler is always the authored box at the default orientation.
 * Never derive 100% from a live pose, selection fit, near plane, or saved camera.
 */
export function originalModelCameraFrame(THREE, { camera, bounds, frameAspect, minRadius = 0, modelOffset = null, room = 1 }) {
  const radius = boundsCenterAndRadius(THREE, bounds)?.radius || minRadius;
  return interactiveCameraFrameForBounds(THREE, {
    camera, controls: { target: new THREE.Vector3() }, bounds, frameAspect, minRadius, modelOffset,
    viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP,
    nearClip: Math.max(radius / 1200, 0.01), room,
  });
}

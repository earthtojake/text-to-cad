/**
 * Draw mode's camera: the view direction is fixed and the drawing editor is the
 * pan/zoom authority, so ink and model move as one picture.
 *
 * The editor places a scene point `s` at `(s + scroll) * zoom` CSS pixels. The
 * lock records where the camera's focal plane sat under that mapping when
 * drawing began; every later editor viewport is answered by ONE camera pose
 * derived from the lock, never from the previous frame, so a long pan cannot
 * drift. Pan slides the orbit target along the camera's own right/up; zoom is
 * orthographic zoom or a perspective dolly along the fixed view direction.
 *
 * In perspective only the focal plane through the orbit target tracks the ink
 * exactly; nearer and farther geometry parallaxes, as it does for any pan.
 */

const MIN_SCALE = 1e-9;

function focalFrame(THREE, camera, target, width, height) {
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix?.();
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
  const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
  const toPixels = point => {
    const ndc = point.clone().project(camera);
    return { x: (ndc.x + 1) * width / 2, y: (1 - ndc.y) * height / 2 };
  };
  const center = toPixels(target);
  // Measured, not derived from fov or frustum: whatever projection, view offset
  // or aspect policy the viewport uses, this is what one world unit covers.
  const pixelsPerUnit = Math.abs(toPixels(target.clone().add(right)).x - center.x);
  return { right, up, center, pixelsPerUnit };
}

/**
 * Record the pose drawing starts from. `null` when the viewport cannot be measured yet.
 *
 * `viewport` is the editor viewport this pose is showing: the identity when Draw
 * begins, the editor's current one when the viewport runtime was replaced
 * mid-sketch, so the new lock answers that viewport with exactly this pose.
 */
export function captureDrawingViewLock(THREE, { camera, controls, width, height }, viewport = null) {
  if (!camera || !controls?.target || !(width > 0) || !(height > 0)) return null;
  const zoom = Number(viewport?.zoom) > 0 ? Number(viewport.zoom) : 1;
  const target = controls.target.clone();
  const { right, up, center, pixelsPerUnit } = focalFrame(THREE, camera, target, width, height);
  if (!(pixelsPerUnit > MIN_SCALE)) return null;
  const offset = camera.position.clone().sub(target);
  return { target, right, up, direction: offset.clone().normalize(), distance: offset.length(),
    pixelsPerUnit: pixelsPerUnit / zoom,
    center: { x: center.x / zoom - (Number(viewport?.scrollX) || 0), y: center.y / zoom - (Number(viewport?.scrollY) || 0) } };
}

/** Pose the camera for an editor viewport. Mutates `camera` and `controls.target`; returns false when it could not. */
export function applyDrawingViewLock(THREE, lock, { camera, controls, width, height }, viewport) {
  const zoom = Number(viewport?.zoom);
  if (!lock || !camera || !controls?.target || !(width > 0) || !(height > 0) || !(zoom > 0)) return false;
  const scrollX = Number(viewport.scrollX) || 0, scrollY = Number(viewport.scrollY) || 0;
  const current = focalFrame(THREE, camera, controls.target, width, height);
  if (!(current.pixelsPerUnit > MIN_SCALE)) return false;
  const pixelsPerUnit = lock.pixelsPerUnit * zoom;
  // The focal point stays wherever this viewport projects it (its centre, unless
  // a view offset says otherwise), including after a resize.
  const panRight = (current.center.x - (lock.center.x + scrollX) * zoom) / pixelsPerUnit;
  const panUp = ((lock.center.y + scrollY) * zoom - current.center.y) / pixelsPerUnit;
  const target = lock.target.clone().addScaledVector(lock.right, panRight).addScaledVector(lock.up, panUp);
  let distance = camera.position.distanceTo(controls.target) || lock.distance;
  if (camera.isOrthographicCamera) camera.zoom *= pixelsPerUnit / current.pixelsPerUnit;
  else distance *= current.pixelsPerUnit / pixelsPerUnit;
  controls.target.copy(target);
  // Pure translation: the orientation is the lock, so it is never recomputed.
  camera.position.copy(target).addScaledVector(lock.direction, distance);
  camera.updateProjectionMatrix?.();
  camera.updateMatrixWorld();
  return true;
}

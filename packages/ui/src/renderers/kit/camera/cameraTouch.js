// Whose camera is on screen, as a rebuild reads it (`settings-ui.md`, "Camera, animation and
// Preview"). A document page opens on the viewer's own fit and is UNTOUCHED; while it stays so, a
// rebuild whose box changed is fitted again, as the open fitted it. The first touch makes the
// camera the person's for the page's life, and a rebuild then keeps it exactly, as CAD programs
// do. A fit (F, Zoom to fit, the live `resetCamera`) hands the camera back:
// a fit is untouched again. A resize is neither: it keeps its own refit rule (`ShellViewport`).
//
// The state lives on the runtime, beside `userMovedCamera`, the flag a progressive model's
// completion fit stands down for. A hand on the camera sets both. A RESTORED view (a reload putting
// back the camera the file was left at) sets only the touch: it is the person's camera, but not one
// they made on this page, and the completion fit restores it again rather than leaving the framing
// on the first pieces (`ShellViewport`'s `restorable`).

/** Every way the camera is touched: what ends the untouched state, by kind. */
export const CAMERA_TOUCH = Object.freeze({
  // An orbit, a pan or a pinch on the model (the controls' drag).
  DRAG: "drag",
  // A wheel or trackpad zoom.
  WHEEL: "wheel",
  // The arrow keys' orbit.
  KEYS: "keys",
  // A view cube face, edge or corner pressed: a preset view.
  VIEW_CUBE: "view_cube",
  // The view cube dragged, which orbits.
  VIEW_CUBE_DRAG: "view_cube_drag",
  // A double-click's Look at: a face, an edge or ink turned square.
  LOOK_AT: "look_at",
  // Zoom to selection.
  ZOOM_TO: "zoom_to",
  // A camera handed to the viewport (the live `setCamera`).
  SET_CAMERA: "set_camera",
  // The view a reload restored from the file's saved view.
  RESTORE: "restore"
});
const TOUCHES = new Set(Object.values(CAMERA_TOUCH));

/** The camera touched, by `kind` (`CAMERA_TOUCH`): untouched no longer, until the next fit. */
export function touchCamera(runtime, kind) {
  if (!runtime || !TOUCHES.has(kind)) return;
  runtime.cameraTouch = kind;
  if (kind !== CAMERA_TOUCH.RESTORE) runtime.userMovedCamera = true;
}

/** A fit: the camera is the viewer's again, untouched, and a progressive model is framed again whole. */
export function fitCamera(runtime) {
  if (!runtime) return;
  runtime.cameraTouch = "";
  runtime.userMovedCamera = false;
}

/** Whether the camera is still the fit: nothing has touched it since the page opened or the last fit. */
export function cameraUntouched(runtime) {
  return Boolean(runtime) && !runtime.cameraTouch && !runtime.userMovedCamera;
}

// Two boxes are the same box within a ten-thousandth of their size: a rebuild of the same geometry
// can tessellate a hair differently, and a fit to that would animate for nothing.
const SAME_BOX = 1e-4;
function isBox(box) {
  return Array.isArray(box?.min) && Array.isArray(box?.max) && box.min.length === 3 && box.max.length === 3
    && [...box.min, ...box.max].every(value => Number.isFinite(Number(value)));
}
function boxSize(box) {
  return Math.hypot(...[0, 1, 2].map(axis => Number(box.max[axis]) - Number(box.min[axis])));
}

/** Whether `next` is another box than `previous` (`{ min, max }` each), beyond a rebuild's noise. */
export function boundsChanged(previous, next) {
  if (!isBox(previous) || !isBox(next)) return false;
  const tolerance = SAME_BOX * Math.max(boxSize(previous), boxSize(next), 1e-9);
  return [0, 1, 2].some(axis => Math.abs(Number(next.min[axis]) - Number(previous.min[axis])) > tolerance
    || Math.abs(Number(next.max[axis]) - Number(previous.max[axis])) > tolerance);
}

/**
 * Whether a rebuild re-fits the camera: it is still the fit (`cameraUntouched`) and the rebuilt
 * model's rest box (`next`) is another box than the one before it (`previous`). A rebuild with the
 * same box, or any rebuild under a camera the person took, leaves the camera exactly where it is.
 */
export function rebuildRefits(runtime, previous, next) {
  return cameraUntouched(runtime) && boundsChanged(previous, next);
}

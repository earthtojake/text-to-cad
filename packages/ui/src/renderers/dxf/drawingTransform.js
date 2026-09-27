/**
 * What a drawing remembers about one file: the view, and only once the person
 * has moved it. It is the drawing's `camera` in the file's view
 * (`kit/shell/fileView.js`): a plane transform, not a scene camera.
 *
 * A drawing that is still sitting where it opened has nothing worth storing —
 * the fit is recomputed from the pane's size anyway, and storing it would make
 * a pane that is reopened narrower come back framed for the old width. So the
 * transform exists only after a pan or a zoom, and its absence means "fit me".
 */

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * The stored transform, or null: nothing but the three numbers, each a number.
 *
 * @param {unknown} raw
 * @returns {{ scale: number, offsetX: number, offsetY: number }|null}
 */
export function readDrawingTransform(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const { scale, offsetX, offsetY } = raw;
  if (!finite(scale) || scale <= 0 || !finite(offsetX) || !finite(offsetY)) return null;
  return { scale, offsetX, offsetY };
}

/**
 * The camera to store for a moved view, or null when the view is untouched and
 * there is nothing to remember.
 *
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} transform
 * @param {boolean} moved
 */
export function drawingTransformCamera(transform, moved) {
  const read = moved ? readDrawingTransform(transform) : null;
  return read ? { scale: read.scale, offsetX: read.offsetX, offsetY: read.offsetY } : null;
}

/**
 * The view transform for a 2D drawing: model space (DXF, y UP) to screen space
 * (CSS pixels, y DOWN).
 *
 * One uniform scale and a translation — no rotation, no shear, no per-axis
 * scale. A drawing is looked at, not posed, so the whole camera is three
 * numbers:
 *
 *     screenX =  modelX * scale + offsetX
 *     screenY = -modelY * scale + offsetY
 *
 * The y flip lives in the transform rather than in the geometry, so primitives
 * are stored in the coordinates the payload arrived in and a coordinate read
 * back out of a pick is a drawing coordinate without a second convention in
 * between.
 *
 * Everything here is pure arithmetic on plain objects: no canvas, no DOM, no
 * React. The viewer drives it from pointer events and the headless snapshot
 * bundle drives it from a requested framing, and both get the same picture.
 */

/**
 * @typedef {object} DrawingTransform
 * @property {number} scale Screen CSS pixels per model unit. Always > 0.
 * @property {number} offsetX Screen x of model x = 0.
 * @property {number} offsetY Screen y of model y = 0.
 *
 * @typedef {readonly [number, number, number, number]} DrawingBounds
 *   `[minX, minY, maxX, maxY]` in model coordinates.
 *
 * @typedef {object} DrawingZoomLimits
 * @property {number} minScale
 * @property {number} maxScale
 */

/** The gutter `fitTransform` leaves on every side, in CSS pixels. */
export const DRAWING_FIT_MARGIN = 16;

/**
 * How far out and in the view may be zoomed, as a multiple of the FITTED
 * scale.
 *
 * Relative, because an absolute scale limit means nothing: the same drawing in
 * metres and in millimetres would hit it a thousand model units apart. Fitted
 * is the one scale that is meaningful for every drawing, which is also why the
 * viewer's zoom readout calls it 100%.
 */
export const DRAWING_ZOOM_OUT_LIMIT = 50;
export const DRAWING_ZOOM_IN_LIMIT = 400;

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * The zoom range around one fitted scale.
 *
 * @param {number} fitScale
 * @returns {DrawingZoomLimits}
 */
export function zoomLimits(fitScale) {
  if (!finite(fitScale) || fitScale <= 0) {
    throw new Error(`zoomLimits needs a positive fitted scale; received ${fitScale}.`);
  }
  return { minScale: fitScale / DRAWING_ZOOM_OUT_LIMIT, maxScale: fitScale * DRAWING_ZOOM_IN_LIMIT };
}

/**
 * A scale brought inside its limits.
 *
 * @param {number} scale
 * @param {DrawingZoomLimits} limits
 * @returns {number}
 */
export function clampScale(scale, limits) {
  const { minScale, maxScale } = limits;
  if (!finite(minScale) || !finite(maxScale) || minScale <= 0 || maxScale < minScale) {
    throw new Error(
      `clampScale needs 0 < minScale <= maxScale; received minScale ${minScale}, maxScale ${maxScale}.`
    );
  }
  return Math.min(maxScale, Math.max(minScale, scale));
}

/**
 * The transform that centres `bounds` in a `width` x `height` pane.
 *
 * A degenerate box is not an error — a drawing that is one horizontal line has
 * no height, and a single POINT entity has neither. An axis with no extent
 * simply does not constrain the scale; when neither does, the scale is 1 and
 * the point lands in the middle of the pane, which is the only honest answer.
 *
 * An EMPTY drawing (`bounds: null`) is a different thing and throws: there is
 * nothing to frame, and a viewer that fits nothing shows a blank pane instead
 * of saying the drawing is empty. Callers check `bounds` first.
 *
 * @param {DrawingBounds|null} bounds
 * @param {number} width CSS pixels.
 * @param {number} height CSS pixels.
 * @param {{ margin?: number }} [options]
 * @returns {DrawingTransform}
 */
export function fitTransform(bounds, width, height, { margin = DRAWING_FIT_MARGIN } = {}) {
  if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(finite)) {
    throw new Error(
      "fitTransform needs a [minX, minY, maxX, maxY] box of finite numbers; "
      + `received ${JSON.stringify(bounds)}. An empty drawing (bounds: null) has nothing to `
      + "fit — show its empty state instead of framing it."
    );
  }
  if (!finite(width) || !finite(height) || width <= 0 || height <= 0) {
    throw new Error(`fitTransform needs a pane with positive size; received ${width} x ${height}.`);
  }
  const [minX, minY, maxX, maxY] = bounds;
  const spanX = Math.abs(maxX - minX);
  const spanY = Math.abs(maxY - minY);
  // Never let the margin eat the pane: a 30 px pane with a 16 px gutter has no
  // room left, and a non-positive usable size would make the scale 0 or worse.
  const usableWidth = Math.max(width - 2 * margin, width * 0.5);
  const usableHeight = Math.max(height - 2 * margin, height * 0.5);
  const scaleX = spanX > 0 ? usableWidth / spanX : Infinity;
  const scaleY = spanY > 0 ? usableHeight / spanY : Infinity;
  const fitted = Math.min(scaleX, scaleY);
  const scale = Number.isFinite(fitted) && fitted > 0 ? fitted : 1;
  const centreX = (minX + maxX) / 2;
  const centreY = (minY + maxY) / 2;
  return {
    scale,
    offsetX: width / 2 - centreX * scale,
    offsetY: height / 2 + centreY * scale
  };
}

/**
 * Model point to screen point.
 *
 * @param {DrawingTransform} transform
 * @param {number} x
 * @param {number} y
 * @returns {[number, number]}
 */
export function modelToScreen(transform, x, y) {
  return [x * transform.scale + transform.offsetX, -y * transform.scale + transform.offsetY];
}

/**
 * Screen point to model point. The exact inverse of `modelToScreen`, which is
 * what makes zoom-about-the-pointer land where the pointer is.
 *
 * @param {DrawingTransform} transform
 * @param {number} x
 * @param {number} y
 * @returns {[number, number]}
 */
export function screenToModel(transform, x, y) {
  return [(x - transform.offsetX) / transform.scale, (transform.offsetY - y) / transform.scale];
}

/**
 * The transform after dragging the drawing by a screen delta.
 *
 * @param {DrawingTransform} transform
 * @param {number} dx CSS pixels.
 * @param {number} dy CSS pixels.
 * @returns {DrawingTransform}
 */
export function panTransform(transform, dx, dy) {
  return { scale: transform.scale, offsetX: transform.offsetX + dx, offsetY: transform.offsetY + dy };
}

/**
 * The transform after zooming by `factor` about a screen point, which stays
 * exactly where it is.
 *
 * Expressed on the OFFSETS rather than by re-deriving a centre, so the fixed
 * point is fixed by construction: the model point under the pointer is
 * whatever it was, and the only thing that changed is how many pixels a model
 * unit is worth. Clamping the scale shortens the step; it never slides the
 * picture sideways, because the same ratio drives both offsets.
 *
 * @param {DrawingTransform} transform
 * @param {{ x: number, y: number }} anchor Screen point that must not move.
 * @param {number} factor
 * @param {DrawingZoomLimits} limits
 * @returns {DrawingTransform}
 */
export function zoomTransform(transform, anchor, factor, limits) {
  if (!finite(factor) || factor <= 0) {
    throw new Error(`zoomTransform needs a positive factor; received ${factor}.`);
  }
  const scale = clampScale(transform.scale * factor, limits);
  const ratio = scale / transform.scale;
  return {
    scale,
    offsetX: anchor.x - (anchor.x - transform.offsetX) * ratio,
    offsetY: anchor.y - (anchor.y - transform.offsetY) * ratio
  };
}

/**
 * The zoom readout: the current scale as a percentage of the fitted one, so
 * "100%" means "the whole drawing, as it opened".
 *
 * @param {DrawingTransform} transform
 * @param {number} fitScale
 * @returns {number}
 */
export function zoomPercent(transform, fitScale) {
  if (!finite(fitScale) || fitScale <= 0) {
    throw new Error(`zoomPercent needs a positive fitted scale; received ${fitScale}.`);
  }
  return (transform.scale / fitScale) * 100;
}

/**
 * Whether two transforms are the same view, within a pixel-invisible epsilon.
 *
 * Used to decide whether the person has MOVED the view (and so whether it is
 * worth persisting, and whether a container resize may re-fit): float drift
 * from a resize must not read as an intentional pan.
 *
 * @param {DrawingTransform|null} left
 * @param {DrawingTransform|null} right
 * @returns {boolean}
 */
export function sameTransform(left, right) {
  if (!left || !right) {
    return left === right;
  }
  return Math.abs(left.scale - right.scale) <= Math.abs(left.scale) * 1e-9
    && Math.abs(left.offsetX - right.offsetX) <= 1e-6
    && Math.abs(left.offsetY - right.offsetY) <= 1e-6;
}

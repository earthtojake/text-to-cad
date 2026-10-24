/**
 * A drawing's view in the camera shape every other view speaks: its PLAN view, looking straight
 * down at the sheet. A prompt's views carry a camera (`annotation/views.js`), and a snapshot job
 * takes one; for a drawing that camera is the window the pane shows — centred on `target`,
 * `orthographicHalfHeight` drawing units above and below — and nothing else, since a drawing is
 * never turned.
 *
 * `planProjection` is the same view as the two matrices a scene camera carries, for the code that
 * projects a point the way a 3D view does (Measure's dimensions, `measureRuler.js`): drawing
 * coordinates to clip space under the pane's transform, so what it draws lands where the drawing is.
 *
 * Plain arithmetic: no canvas, no three.js.
 */
import { screenToModel } from "./transform.js";

/**
 * @typedef {{ position: number[], target: number[], up: number[], orthographicHalfHeight: number }} PlanCamera
 */

/**
 * The camera of the view a transform shows in a `width` × `height` pane.
 * @param {import("./transform.js").DrawingTransform} transform
 * @returns {PlanCamera | null}
 */
export function planCamera(transform, width, height) {
  if (!transform || !(transform.scale > 0) || !(width > 0) || !(height > 0)) return null;
  const [x, y] = screenToModel(transform, width / 2, height / 2);
  const half = height / (2 * transform.scale);
  // The eye's height is any above the sheet; four half-heights reads as a sane camera to a 3D tool.
  return { position: [x, y, half * 4], target: [x, y, 0], up: [0, 1, 0], orthographicHalfHeight: half };
}

/**
 * The transform that shows a plan camera's window in a `width` × `height` picture.
 * @param {PlanCamera} camera
 * @returns {import("./transform.js").DrawingTransform | null}
 */
export function planTransform(camera, width, height) {
  const half = Number(camera?.orthographicHalfHeight);
  const target = camera?.target;
  if (!(half > 0) || !Array.isArray(target) || !(width > 0) || !(height > 0)) return null;
  const scale = height / (2 * half);
  return { scale, offsetX: width / 2 - Number(target[0]) * scale, offsetY: height / 2 + Number(target[1]) * scale };
}

/**
 * The view as a scene camera's matrices (column order, as three.js keeps them): the view matrix the
 * identity, the projection the transform into clip space. Enough for `projectWorldPointToClient`.
 * @param {import("./transform.js").DrawingTransform} transform
 */
export function planProjection(transform, width, height) {
  if (!transform || !(width > 0) || !(height > 0)) return null;
  const { scale, offsetX, offsetY } = transform;
  return {
    matrixWorldInverse: { elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
    projectionMatrix: {
      elements: [
        (2 * scale) / width, 0, 0, 0,
        0, (2 * scale) / height, 0, 0,
        0, 0, 0, 0,
        (2 * offsetX) / width - 1, 1 - (2 * offsetY) / height, 0, 1
      ]
    }
  };
}

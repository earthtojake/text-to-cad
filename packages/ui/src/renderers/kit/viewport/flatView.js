/**
 * What a flat view (a board, a schematic's sheet, a drawing: `useFlatCanvasView.js`) keeps of itself:
 * its `camera` in the file's view (`kit/shell/fileView.js`), the plane transform the person left the
 * picture at (`@cad/core`'s `drawing2d/transform.js`) and the pane it was framed in, in CSS pixels,
 *
 *   { scale, offsetX, offsetY, width, height }
 *
 * and only once the person has moved the view: a view still at its fit stores nothing (null is "fit
 * me"), since the fit is recomputed from whatever pane it opens in.
 *
 * The pane is what lets the view come back as it was left. A transform is pixels of one pane; the
 * pane a file reopens in is often another for a moment (the panel docks beside the canvas once the
 * file has loaded, so the canvas starts the wider), and a view adopted there and then carried to the
 * pane it ends in by what it shows came back half a panel off. So a view is placed on every pane by
 * what it shows (`carryTransform`: the point at its pane's centre at this one's, the zoom against
 * each pane's fit), and on a pane of the size it was framed in it is the stored transform exactly.
 * A record stored without its pane (an earlier build's) is taken as it is.
 */

const finite = value => typeof value === "number" && Number.isFinite(value);
const size = value => (finite(value) && value > 0 ? value : undefined);

/**
 * The stored view, or null: the transform's three numbers (each finite, the scale positive) and, where
 * the record has them, the pane's two sizes. Anything else (a scene's camera, a broken transform, a
 * record's other fields) is nothing stored, never a half-restored view.
 * @param {unknown} raw
 * @returns {{ scale: number, offsetX: number, offsetY: number, width?: number, height?: number } | null}
 */
export function readFlatView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const { scale, offsetX, offsetY } = raw;
  if (!finite(scale) || scale <= 0 || !finite(offsetX) || !finite(offsetY)) return null;
  const width = size(raw.width), height = size(raw.height);
  return width && height ? { scale, offsetX, offsetY, width, height } : { scale, offsetX, offsetY };
}

/**
 * The record of a view the person moved: its transform and the pane it is framed in, nothing else.
 * @param {{ scale: number, offsetX: number, offsetY: number }} transform
 * @param {{ width: number, height: number }} pane
 */
export function flatViewRecord(transform, pane) {
  const width = size(pane?.width), height = size(pane?.height);
  const { scale, offsetX, offsetY } = transform;
  return width && height ? { scale, offsetX, offsetY, width, height } : { scale, offsetX, offsetY };
}

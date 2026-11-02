/**
 * A board seen in a view: where what is drawn ON the board (an annotation's ink, Measure's ends) is
 * kept, and how it reaches the screen. Shared by the viewer's board view and the headless snapshot,
 * so a Quick Edit's views come back as the person saw them.
 *
 * Three frames. The **sheet** is the payload's page space (`plot.js`): millimetres, x right, y down,
 * the board's sheet corner at the origin — where ink and measurements are kept, so they stay on the
 * board whichever side it is seen from. The **plan** is drawing2d's model space for the view on
 * screen: the sheet with y negated and, from below (`side: "bottom"`), mirrored about the sheet's
 * vertical centre line — what the view's transform maps to the screen, and the frame a plan-view
 * camera (`../drawing2d/planView.js`) speaks. The **screen** is the pane's CSS pixels.
 *
 * Pure arithmetic: no canvas, no DOM.
 */

/** The page x a board is mirrored about when it is seen from below, or null from the top. */
export function boardMirrorX(sheet, side) {
  return side === "bottom" && sheet ? sheet.x + sheet.width / 2 : null;
}

/** A sheet point in the plan of the view (`mirrorX`: `boardMirrorX`), and back: the map is its own inverse. */
export function sheetToPlan([x, y], mirrorX = null) {
  return [mirrorX == null ? x : 2 * mirrorX - x, -y];
}
export const planToSheet = sheetToPlan;

const MARKS = new WeakMap();

/**
 * Annotation marks (`../../common/annotation.js`: their `points` x, y, z triples) as they lie in the
 * plan of the view, for drawing2d's mark code (`../drawing2d/marks.js`). Each converted mark is kept
 * with its original for the same side, so a frame of a pan converts nothing.
 */
export function marksInPlan(marks, mirrorX = null) {
  return (marks || []).map((mark) => {
    const kept = MARKS.get(mark);
    if (kept && kept.mirrorX === mirrorX) return kept.mark;
    const source = mark.points || [];
    const points = new Float32Array(source.length);
    for (let index = 0; index + 1 < source.length; index += 3) {
      const [x, y] = sheetToPlan([source[index], source[index + 1]], mirrorX);
      points[index] = x;
      points[index + 1] = y;
      points[index + 2] = source[index + 2] || 0;
    }
    const converted = { ...mark, points };
    MARKS.set(mark, { mirrorX, mark: converted });
    return converted;
  });
}

/**
 * The view as a scene camera's matrices (column order, as three.js keeps them), from the SHEET to
 * clip space: what Measure's kit code projects a pick with, its points on the sheet (y down), the
 * board mirrored from below. Enough for `projectWorldPointToClient`.
 *
 * @param {{ scale: number, offsetX: number, offsetY: number }} transform  The view's (plan to screen).
 * @param {number} width  The pane's CSS pixels.
 * @param {number} height
 * @param {number | null} [mirrorX]
 */
export function boardPlanProjection(transform, width, height, mirrorX = null) {
  if (!transform || !(transform.scale > 0) || !(width > 0) || !(height > 0)) return null;
  const { scale, offsetX, offsetY } = transform;
  // screen x = scale * plan x + offsetX, plan x = x or 2·mirrorX − x; screen y = offsetY + scale * y.
  const sx = mirrorX == null ? scale : -scale;
  const tx = mirrorX == null ? offsetX : offsetX + 2 * mirrorX * scale;
  return {
    matrixWorldInverse: { elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
    projectionMatrix: {
      elements: [
        (2 * sx) / width, 0, 0, 0,
        0, (-2 * scale) / height, 0, 0,
        0, 0, 0, 0,
        (2 * tx) / width - 1, 1 - (2 * offsetY) / height, 0, 1
      ]
    }
  };
}

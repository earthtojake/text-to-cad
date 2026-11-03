/**
 * Annotate on a drawing: where its marks go, and how they come back to the screen — the flat view's
 * `surface` for the kit's Annotate layer (`kit/tools/annotate/AnnotationOverlay.jsx`).
 *
 * A mark drawn over a drawing lies on the sheet: its screen points become drawing coordinates
 * (x, y, 0) under the view as it stood, on no part, so it pans and zooms with the drawing and the
 * annotation file a prompt carries is in the drawing's own coordinates — what `cad snapshot`
 * draws it over (`@cad/core/lib/drawing2d/marks.js`). A stroke keeps its width in screen
 * pixels, as over a model; a text mark's corners are on the sheet, so its words zoom with it.
 *
 * Importing this module has no environmental effects.
 */
import { annotationDocument } from "@cad/core/common/annotation.js";
import { annotationMarkOnScreen } from "@cad/core/lib/drawing2d/marks.js";
import { screenToModel } from "@cad/core/lib/drawing2d/index.js";
import { markPoints } from "../../annotation/geometry.js";

/**
 * A screen mark (`annotation/geometry.js`) as the session keeps it on a drawing: its points on the
 * sheet under `transform`.
 * @param {object} mark
 * @param {import("@cad/core/lib/drawing2d/transform.js").DrawingTransform} transform
 */
export function placeOnSheet(mark, transform) {
  const screen = markPoints(mark);
  const points = new Float32Array(screen.length * 3);
  screen.forEach((point, index) => {
    const [x, y] = screenToModel(transform, point.x, point.y);
    points[index * 3] = x;
    points[index * 3 + 1] = y;
  });
  const item = { id: mark.id, kind: mark.kind, points, color: mark.color,
    ...(mark.group ? { group: mark.group } : {}), ...(mark.view ? { view: mark.view } : {}), touches: [] };
  if (mark.kind === "stroke") {
    Object.assign(item, { width: mark.width, opacity: mark.opacity, closed: mark.closed, ...(mark.widths ? { widths: mark.widths } : {}) });
  } else if (mark.kind === "area") {
    // A fill's outline alone, fanned from its first point: a drawing's fills are drawn by outline.
    const count = screen.length;
    const triangles = [];
    for (let index = 1; index + 1 < count; index += 1) triangles.push(0, index, index + 1);
    Object.assign(item, { opacity: mark.opacity, triangles, outline: count });
  } else Object.assign(item, { text: mark.text, fontPx: mark.fontPx });
  return item;
}

/**
 * The flat view's surface for Annotate's layer: ink placed on the sheet under the view's transform
 * now, ink back on the screen, and the canvas a press or a wheel that is the view's goes on to.
 * @param {{ transform(): object | null, canvas(): Element | null }} view
 */
export function drawingAnnotationSurface(view) {
  return {
    place: marks => {
      const transform = view.transform();
      return transform ? marks.map(mark => placeOnSheet(mark, transform)) : [];
    },
    onScreen: items => {
      const transform = view.transform();
      return transform ? items.map(item => annotationMarkOnScreen(item, transform)) : [];
    },
    view: () => view.canvas()
  };
}

/** The annotation as an annotation file says it, its marks on the sheet in `unit`; null without ink. */
export function drawingAnnotationDocument(items, unit) {
  return items.length ? annotationDocument({ units: unit, marks: items }) : null;
}

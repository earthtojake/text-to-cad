/**
 * Annotate on a board: where its marks go, and how they come back to the screen — the flat view's
 * `surface` for the kit's Annotate layer (`kit/tools/annotate/AnnotationOverlay.jsx`), as a
 * drawing's is (`../dxf/drawingAnnotation.js`).
 *
 * A mark drawn over a board lies on the board: its screen points become sheet millimetres (x, y
 * down, the payload's page space: `@text-to-cad/core`'s `plot2d/boardView.js`) under the view as it
 * stood — through the mirror while the board is seen from below — on no part, so it pans and zooms
 * with the board, stays on what it marks when the side changes, and the annotation file a prompt
 * carries is in the sheet's own coordinates, what `cadgen pcb snapshot` draws it over.
 *
 * Importing this module has no environmental effects.
 */
import { annotationDocument } from "@text-to-cad/core/common/annotation.js";
import { annotationMarkOnScreen } from "@text-to-cad/core/lib/drawing2d/marks.js";
import { screenToModel } from "@text-to-cad/core/lib/drawing2d/index.js";
import { marksInPlan, planToSheet } from "@text-to-cad/core/lib/plot2d/index.js";
import { markPoints } from "../../annotation/geometry.js";

/**
 * A screen mark (`annotation/geometry.js`) as the session keeps it on a board: its points on the
 * sheet under `transform`, the board mirrored about `mirrorX` (null: seen from the top).
 */
export function placeOnBoard(mark, transform, mirrorX = null) {
  const screen = markPoints(mark);
  const points = new Float32Array(screen.length * 3);
  screen.forEach((point, index) => {
    const [x, y] = planToSheet(screenToModel(transform, point.x, point.y), mirrorX);
    points[index * 3] = x;
    points[index * 3 + 1] = y;
  });
  const item = { id: mark.id, kind: mark.kind, part: null, placement: "space", points, color: mark.color,
    ...(mark.group ? { group: mark.group } : {}), ...(mark.view ? { view: mark.view } : {}), touches: [] };
  if (mark.kind === "stroke") {
    Object.assign(item, { width: mark.width, opacity: mark.opacity, dash: mark.dash, closed: mark.closed, ...(mark.widths ? { widths: mark.widths } : {}) });
  } else if (mark.kind === "area") {
    // A fill's outline alone, fanned from its first point, as a drawing's.
    const count = screen.length;
    const triangles = [];
    for (let index = 1; index + 1 < count; index += 1) triangles.push(0, index, index + 1);
    Object.assign(item, { opacity: mark.opacity, triangles, outline: count });
  } else Object.assign(item, { text: mark.text, fontPx: mark.fontPx });
  return item;
}

/**
 * The board view's surface for Annotate's layer: ink placed on the sheet under the view's transform
 * and side now, ink back on the screen, and the canvas a press or a wheel that is the view's goes on to.
 * @param {{ transform(): object | null, mirrorX(): number | null, canvas(): Element | null }} view
 */
export function boardAnnotationSurface(view) {
  return {
    place: marks => {
      const transform = view.transform();
      return transform ? marks.map(mark => placeOnBoard(mark, transform, view.mirrorX())) : [];
    },
    onScreen: items => {
      const transform = view.transform();
      return transform ? marksInPlan(items, view.mirrorX()).map(item => annotationMarkOnScreen(item, transform)) : [];
    },
    view: () => view.canvas()
  };
}

/** The annotation as an annotation file says it, its marks on the sheet in millimetres; null without ink. */
export function boardAnnotationDocument(items) {
  return items.length ? annotationDocument({ units: "mm", marks: items }) : null;
}

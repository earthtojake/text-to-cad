/**
 * Annotate on a plot — a board, a schematic's sheet (`@cad/core`'s `plot2d`): where its marks go, and how
 * they come back to the screen — the flat view's `surface` for the kit's Annotate layer
 * (`AnnotationOverlay.jsx`), as a drawing's is.
 *
 * A mark drawn over a board (or a sheet: never mirrored) lies on the board: its screen points become sheet millimetres (x, y
 * down, the payload's page space: `@cad/core`'s `plot2d/boardView.js`) under the view as it
 * stood — through the mirror while the board is seen from below — on no part, so it pans and zooms
 * with the board, stays on what it marks when the side changes, and the annotation file a prompt
 * carries is in the sheet's own coordinates, what `cad <type> snapshot` draws it over.
 *
 * Importing this module has no environmental effects.
 */
import { annotationDocument } from "@cad/core/common/annotation.js";
import { annotationMarkOnScreen } from "@cad/core/lib/drawing2d/marks.js";
import { screenToModel } from "@cad/core/lib/drawing2d/index.js";
import { marksInPlan, planToSheet } from "@cad/core/lib/plot2d/index.js";
import { markPoints } from "../../../../annotation/geometry.js";

/**
 * A screen mark (`annotation/geometry.js`) as the session keeps it on a plot: its points on the
 * sheet under `transform`, the board mirrored about `mirrorX` (null: seen from the top).
 */
export function placeOnPlot(mark, transform, mirrorX = null) {
  return placeOnSheet(mark, point => planToSheet(screenToModel(transform, point.x, point.y), mirrorX));
}

/**
 * A screen mark as the session keeps it on a plot, each of its points put on the sheet by `toSheet`
 * (a pane point to sheet millimetres, or null where it meets no sheet: that point is dropped). The flat
 * view's is its transform (`placeOnPlot`); a 3D view of the sheet's, the point its camera's ray meets.
 * Null when no point lands.
 */
export function placeOnSheet(mark, toSheet) {
  const screen = markPoints(mark).map(toSheet).filter(Boolean);
  if (!screen.length) return null;
  const points = new Float32Array(screen.length * 3);
  screen.forEach(([x, y], index) => {
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
 * A plot view's surface for Annotate's layer: ink placed on the sheet under the view's transform
 * and side now, ink back on the screen, and the canvas a press or a wheel that is the view's goes on to.
 * @param {{ transform(): object | null, mirrorX(): number | null, canvas(): Element | null }} view
 */
export function plotAnnotationSurface(view) {
  return {
    place: marks => {
      const transform = view.transform();
      return transform ? marks.map(mark => placeOnPlot(mark, transform, view.mirrorX())) : [];
    },
    onScreen: items => {
      const transform = view.transform();
      return transform ? marksInPlan(items, view.mirrorX()).map(item => annotationMarkOnScreen(item, transform)) : [];
    },
    view: () => view.canvas()
  };
}

/** The annotation as an annotation file says it, its marks on the sheet in millimetres; null without ink. */
export function plotAnnotationDocument(items) {
  return items.length ? annotationDocument({ units: "mm", marks: items }) : null;
}

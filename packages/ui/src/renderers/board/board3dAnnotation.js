/**
 * Annotate on a board shown in 3D: the same marks as the flat view's (`kit/tools/annotate/plotAnnotation.js`),
 * kept in sheet millimetres, laid on the face of the side the camera sees — each point where its pane
 * point's ray meets that face — and brought back to the screen through the camera. So ink drawn in 2D
 * lies where it was drawn in 3D, ink drawn in 3D lies on the board in 2D, and the annotation file a
 * prompt carries is in the sheet's own coordinates either way.
 *
 * Importing this module has no environmental effects.
 */
import { faceZ, rayToFace, sheetToWorld } from "@cad/core/lib/board3d/boardFrame.js";
import { placeOnSheet } from "../kit/tools/annotate/plotAnnotation.js";

/**
 * @param {{ ray(point: { x: number, y: number }): { origin: number[], direction: number[] } | null,
 *   project(world: number[]): { x: number, y: number } | null, side(): "top" | "bottom", thickness(): number,
 *   canvas(): Element | null }} view  The 3D view now: a pane point's ray, a world point's pane point (null
 *   behind the eye), the side its camera sees, the board's thickness and its canvas.
 */
export function board3dAnnotationSurface(view) {
  const onScreen = item => {
    const side = view.side(), z = faceZ(side, view.thickness());
    const count = item.kind === "area" && item.outline ? item.outline : item.points.length / 3;
    const points = [];
    for (let index = 0; index < count; index += 1) {
      const point = view.project(sheetToWorld([item.points[index * 3], item.points[index * 3 + 1]], z));
      if (!point) return null;
      points.push(point);
    }
    if (item.kind === "area") return { id: item.id, kind: "area", points, closed: true, width: 0 };
    if (item.kind === "text") return { id: item.id, kind: "text", points, closed: true, width: 0 };
    return { id: item.id, kind: "stroke", points, closed: Boolean(item.closed), width: Math.max(...(item.widths || [1])) * (item.width || 0) };
  };
  return {
    place: marks => {
      const side = view.side(), thickness = view.thickness();
      return marks.map(mark => placeOnSheet(mark, point => { const ray = view.ray(point); return ray ? rayToFace(ray, side, thickness) : null; })).filter(Boolean);
    },
    onScreen: items => items.map(onScreen).filter(Boolean),
    view: () => view.canvas()
  };
}

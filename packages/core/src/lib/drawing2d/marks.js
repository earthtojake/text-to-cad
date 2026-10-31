/**
 * What is drawn OVER a drawing: an annotation's ink, on its 2D canvas, under the view's transform.
 * The viewer's DXF pane paints a person's ink with this as they draw it, and `cad snapshot`
 * paints a job's `annotation` with it, so a Quick Edit's views come back as the person saw them.
 *
 * The ink is an annotation's marks (`../../common/annotation.js`) lying on the sheet: on no part, their
 * points in drawing coordinates (x, y, 0). A stroke's width is in screen pixels at any zoom, as it is
 * over a model; a text mark's four corners are on the sheet, so its words grow and shrink with it.
 */
import { REFERENCE_SELECTED_COLOR } from "../viewer/referenceGeometry.js";
import { modelToScreen } from "./transform.js";

const TEXT_LINE_HEIGHT = 1.25;
const HALO_PX = 6;

/** A mark's points as screen points under `transform`. */
function screenPoints(points, transform, count = points.length / 3) {
  const out = [];
  for (let index = 0; index < count; index += 1) {
    const [x, y] = modelToScreen(transform, points[index * 3], points[index * 3 + 1]);
    out.push({ x, y });
  }
  return out;
}

/**
 * A mark as it falls on the screen now: a stroke's line, an area's outline, a text mark's corners —
 * and the polygon Select and the eraser test against (`annotation/geometry.js`'s screen ink).
 * @param {import("../../common/annotation.js").AnnotationMark} mark
 * @param {import("./transform.js").DrawingTransform} transform
 */
export function annotationMarkOnScreen(mark, transform) {
  if (mark.kind === "area") {
    const outline = screenPoints(mark.points, transform, Number(mark.outline) || mark.points.length / 3);
    return { id: mark.id, kind: "area", points: outline, closed: true, width: 0 };
  }
  const points = screenPoints(mark.points, transform);
  if (mark.kind === "text") return { id: mark.id, kind: "text", points, closed: true, width: 0 };
  return { id: mark.id, kind: "stroke", points, closed: Boolean(mark.closed), width: Math.max(...(mark.widths || [1])) * (mark.width || 0) };
}

function paintText(ctx, mark, corners) {
  const [a, b, , d] = corners;
  const across = Math.hypot(b.x - a.x, b.y - a.y), down = Math.hypot(d.x - a.x, d.y - a.y);
  if (!(across > 0) || !(down > 0)) return;
  const lines = String(mark.text).split("\n");
  // Its words fill the box they were written in: the box is on the sheet, so they zoom with it.
  const px = down / (lines.length * TEXT_LINE_HEIGHT);
  ctx.save();
  ctx.transform((b.x - a.x) / across, (b.y - a.y) / across, (d.x - a.x) / down, (d.y - a.y) / down, a.x, a.y);
  ctx.font = `500 ${px}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textBaseline = "top";
  ctx.fillStyle = mark.color;
  lines.forEach((line, index) => ctx.fillText(line, 0, index * px * TEXT_LINE_HEIGHT));
  ctx.restore();
}

function paintStroke(ctx, mark, points, lineScale) {
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  const path = mark.closed ? [...points, points[0]] : points;
  if (mark.widths?.length === points.length) {
    for (let index = 1; index < points.length; index += 1) {
      ctx.lineWidth = mark.width * lineScale * (mark.widths[index - 1] + mark.widths[index]) / 2;
      ctx.beginPath();
      ctx.moveTo(points[index - 1].x, points[index - 1].y);
      ctx.lineTo(points[index].x, points[index].y);
      ctx.stroke();
    }
    return;
  }
  ctx.lineWidth = mark.width * lineScale;
  ctx.beginPath();
  path.forEach((point, index) => (index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)));
  ctx.stroke();
}

/**
 * Paint an annotation's marks over a drawing. `lineScale` multiplies a stroke's screen width (a
 * snapshot's picture is as heavy against its height as the viewer was); `selected` and `hovered`
 * (mark ids) are haloed in the selection's blue, as Select shows picked ink.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {readonly import("../../common/annotation.js").AnnotationMark[]} marks
 * @param {{ transform: import("./transform.js").DrawingTransform, pixelRatio?: number, lineScale?: number,
 *   selected?: readonly string[], hovered?: readonly string[] }} options
 */
export function drawAnnotationMarks(ctx, marks, { transform, pixelRatio = 1, lineScale = 1, selected = [], hovered = [] }) {
  if (!marks?.length || !transform) return;
  ctx.save();
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  const halo = new Map([...hovered.map(id => [id, 0.25]), ...selected.map(id => [id, 0.5])]);
  for (const mark of marks) {
    const screen = annotationMarkOnScreen(mark, transform);
    if (halo.has(mark.id) && screen.points.length) {
      ctx.globalAlpha = halo.get(mark.id);
      ctx.strokeStyle = REFERENCE_SELECTED_COLOR;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.lineWidth = (mark.kind === "stroke" ? screen.width * lineScale : 2) + HALO_PX;
      ctx.beginPath();
      const ring = screen.closed ? [...screen.points, screen.points[0]] : screen.points;
      ring.forEach((point, index) => (index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)));
      ctx.stroke();
    }
    ctx.globalAlpha = mark.opacity ?? 1;
    ctx.strokeStyle = mark.color;
    ctx.fillStyle = mark.color;
    if (mark.kind === "stroke") paintStroke(ctx, mark, screen.points, lineScale);
    else if (mark.kind === "area") {
      ctx.beginPath();
      screen.points.forEach((point, index) => (index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)));
      ctx.closePath();
      ctx.fill();
    } else paintText(ctx, mark, screen.points);
  }
  ctx.restore();
}

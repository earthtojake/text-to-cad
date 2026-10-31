import { getStrokePoints } from "perfect-freehand";
import { FILL_ANALYSIS_MAX_DIMENSION, FILL_CONNECT_GAP_PX, findFillRegion, pairNearbyBoundaryEndpoints } from "@text-to-cad/core/lib/annotation/fillRegion.js";

// Ink on the screen: what each Annotate tool puts down, as marks in CSS pixels from the viewport's
// top-left — a stroke (a polyline of a width), an area (a filled polygon:
// a fill), or a text mark (words, on a flat rectangle) — before `kit/tools/annotate/annotation3d.js` projects them
// into the model; and the ink already in the model, projected back onto the screen, to hit-test
// (the eraser, select) and to bound a fill. Pure: no DOM, no WebGL.

/** Strokes are split so no segment is longer than this, so a projected one can follow a curved surface. */
export const ANNOTATION_SEGMENT_PX = 6;
const ELLIPSE_SEGMENTS = 72;
/** A fill is translucent, so it marks an area without hiding the model or the ink under it. */
export const FILL_OPACITY = 0.35;

/**
 * @typedef {{ x: number, y: number }} ScreenPoint
 * @typedef {{ color: string, width: number }} AnnotationStyle  `width`: the
 *   stroke's weight (1, 2, 4, 6), in CSS pixels on screen.
 * @typedef {{ kind: "stroke", id: string, points: ScreenPoint[], closed: boolean, color: string,
 *   width: number, opacity: number, widths?: number[], group?: string }} ScreenStroke
 *   `widths`: the pen's, each point's width as a share of `width` (its pressure). `group`: the
 *   marks drawn as one thing (an arrow's line and its head), which are erased, picked and moved together.
 * @typedef {{ kind: "area", id: string, outline: ScreenPoint[], color: string, opacity: number }} ScreenArea
 * @typedef {{ kind: "text", id: string, corners: ScreenPoint[], text: string, color: string, fontPx: number }} ScreenText
 * @typedef {(ScreenStroke | ScreenArea | ScreenText) & { placement?: "surface" | "space" }} ScreenMark  `placement`:
 *   where it lies once put down — on the model (the default) or in space (`annotation3d.js`).
 */

let made = 0;
/** A new mark's id: unique for the page's life, which is as long as any ink lasts. */
export const annotationId = () => `ink-${Date.now().toString(36)}-${(made += 1).toString(36)}`;

/** The pen draws a little heavier than a shape at the same weight, as a felt tip does next to a ruler. */
export const penWidth = width => Math.max(1, width * 1.5);

/** The highlighter is broad and translucent: five times the weight chosen, at this opacity. */
export const HIGHLIGHTER_WIDTH_FACTOR = 5;
export const HIGHLIGHTER_OPACITY = 0.35;
export const highlighterWidth = width => width * HIGHLIGHTER_WIDTH_FACTOR;
/** A stroke the highlighter drew: an ordinary stroke, told by its opacity (no pressure `widths`, a shape is opaque). */
export const isHighlighterStroke = item => item.kind === "stroke" && !item.widths && Math.abs((item.opacity ?? 1) - HIGHLIGHTER_OPACITY) < 1e-3;
/** A stroke's width in px at the weight `setting` (1, 2, 4, 6), as its own tool draws it: the pen's heavier, the highlighter's broad. */
export const strokeWidthAt = (item, setting) => (item.widths ? penWidth(setting) : isHighlighterStroke(item) ? highlighterWidth(setting) : setting);
/** The weight a stroke was drawn at, whichever tool drew it (`strokeWidthAt` undone). */
export const strokeSettingOf = item => (item.widths ? item.width / penWidth(1) : isHighlighterStroke(item) ? item.width / HIGHLIGHTER_WIDTH_FACTOR : item.width);

// The pen: perfect-freehand's handling of a freehand line: the path smoothed as it is drawn (streamline ½), and each point's width from its
// pressure — a stylus's own, or with a mouse simulated from speed, so a quick stroke thins and a
// slow one swells — eased by sin, thinned 0.6, and normalised so an even pressure is the weight.
const PEN = Object.freeze({ streamline: 0.5, thinning: 0.6, size: 16, rate: 0.275 });
const ease = t => Math.sin((t * Math.PI) / 2);
const widthAt = pressure => ease(0.5 - PEN.thinning * (0.5 - pressure)) / ease(0.5);
function penPath(points, pressures) {
  const input = points.map((point, index) => (pressures ? [point.x, point.y, pressures[index]] : [point.x, point.y]));
  const smoothed = getStrokePoints(input, { streamline: PEN.streamline, size: PEN.size, last: true });
  let previous = pressures ? smoothed[0]?.pressure ?? 0.5 : 0.5;
  return smoothed.map(({ point, pressure, distance }) => {
    if (!pressures) {
      // perfect-freehand's simulation: pressure eases toward what the speed implies.
      const speed = Math.min(1, distance / PEN.size);
      previous = Math.min(1, previous + (Math.min(1, 1 - speed) - previous) * (speed * PEN.rate));
    } else previous = pressure;
    return { x: point[0], y: point[1], width: widthAt(previous) };
  });
}

/** A polyline with no segment longer than `step` pixels; a closed one comes back to its start. */
export function densify(points, closed = false, step = ANNOTATION_SEGMENT_PX) {
  const path = closed && points.length > 2 ? [...points, points[0]] : points;
  const out = [];
  for (let index = 0; index < path.length; index += 1) {
    const point = path[index];
    if (index > 0) {
      const from = path[index - 1];
      const length = Math.hypot(point.x - from.x, point.y - from.y);
      const pieces = Math.max(1, Math.ceil(length / step));
      for (let piece = 1; piece < pieces; piece += 1) {
        out.push({ x: from.x + (point.x - from.x) * piece / pieces, y: from.y + (point.y - from.y) * piece / pieces });
      }
    }
    out.push(point);
  }
  return out;
}

/** An arrowhead's two wings at `tip`, coming from `from`, sized by the stroke's width. */
export function arrowWings(from, tip, width) {
  const length = Math.hypot(tip.x - from.x, tip.y - from.y);
  if (length < 1e-6) return [];
  const ux = (tip.x - from.x) / length, uy = (tip.y - from.y) / length;
  const size = Math.max(10, width * 5), spread = Math.PI / 7;
  return [-spread, spread].map(turn => {
    const cos = Math.cos(turn), sin = Math.sin(turn);
    const bx = -(ux * cos - uy * sin), by = -(ux * sin + uy * cos);
    return [{ x: tip.x + bx * size, y: tip.y + by * size }, tip];
  });
}

// A stroke mark of a style: its points, open or closed, at the style's weight.
const stroke = (points, closed, { color, width }, { id = annotationId(), weight = width, opacity = 1 } = {}) =>
  ({ kind: "stroke", id, points: densify(points, closed), closed, color, width: weight, opacity });

/**
 * The pen's mark: the line it was drawn along, smoothed, each point as wide as its pressure made it
 * (`pressures`: a stylus's, 0–1; none, a mouse's, simulated). A press with no drag is a dot.
 */
export function penMark(points, style, pressures = null) {
  if (!points.length) return null;
  const path = penPath(points.length === 1 ? [points[0], { x: points[0].x + 0.01, y: points[0].y }] : points,
    pressures && pressures.length === points.length ? pressures : null);
  if (path.length < 2) path.push({ ...path[0], x: path[0].x + 0.01 });
  return { kind: "stroke", id: annotationId(), points: path.map(({ x, y }) => ({ x, y })), closed: false, color: style.color,
    width: penWidth(style.width), opacity: 1, widths: path.map(point => point.width) };
}

/**
 * The highlighter's mark: the line it was drawn along, smoothed as the pen's is, but of one broad
 * width (`highlighterWidth`) and translucent (`HIGHLIGHTER_OPACITY`), with no pressure taper: a
 * plain stroke, round at its ends. A press with no drag is a dot.
 */
export function highlighterMark(points, style) {
  if (!points.length) return null;
  const path = penPath(points.length === 1 ? [points[0], { x: points[0].x + 0.01, y: points[0].y }] : points, null);
  if (path.length < 2) path.push({ ...path[0], x: path[0].x + 0.01 });
  return { kind: "stroke", id: annotationId(), points: path.map(({ x, y }) => ({ x, y })), closed: false, color: style.color,
    width: highlighterWidth(style.width), opacity: HIGHLIGHTER_OPACITY };
}

// A rectangle's corners, rounded: a quarter of its shorter side, at most 32px.
function roundedRectangle(left, top, right, bottom) {
  const radius = Math.min(32, Math.min(right - left, bottom - top) * 0.25);
  if (radius < 1) return [{ x: left, y: top }, { x: right, y: top }, { x: right, y: bottom }, { x: left, y: bottom }];
  const corner = (cx, cy, from) => Array.from({ length: 9 }, (_, index) => {
    const turn = from + (index / 8) * (Math.PI / 2);
    return { x: cx + radius * Math.cos(turn), y: cy + radius * Math.sin(turn) };
  });
  return [...corner(right - radius, top + radius, -Math.PI / 2), ...corner(right - radius, bottom - radius, 0),
    ...corner(left + radius, bottom - radius, Math.PI / 2), ...corner(left + radius, top + radius, Math.PI)];
}

/**
 * The marks a shape tool puts down, dragged from `from` to `to`: a line, an arrow (its line and its
 * head's two wings, one mark each), a rectangle or an ellipse in the box they span. Nothing for a
 * drag too short to mean a shape.
 *
 * @param {"line" | "arrow" | "rectangle" | "ellipse"} tool
 * @returns {ScreenStroke[]}
 */
export function shapeMarks(tool, from, to, style) {
  if (Math.hypot(to.x - from.x, to.y - from.y) < 2) return [];
  if (tool === "line") return [stroke([from, to], false, style)];
  if (tool === "arrow") {
    const group = annotationId();
    return [stroke([from, to], false, style), ...arrowWings(from, to, style.width).map(wing => stroke(wing, false, style))]
      .map(mark => ({ ...mark, group }));
  }
  const left = Math.min(from.x, to.x), right = Math.max(from.x, to.x), top = Math.min(from.y, to.y), bottom = Math.max(from.y, to.y);
  if (tool === "rectangle") return [stroke(roundedRectangle(left, top, right, bottom), true, style)];
  const cx = (left + right) / 2, cy = (top + bottom) / 2, rx = (right - left) / 2, ry = (bottom - top) / 2;
  const ring = Array.from({ length: ELLIPSE_SEGMENTS }, (_, index) => {
    const turn = (index / ELLIPSE_SEGMENTS) * Math.PI * 2;
    return { x: cx + rx * Math.cos(turn), y: cy + ry * Math.sin(turn) };
  });
  return [stroke(ring, true, style)];
}

/** A text mark at `at` (its top-left), as wide and tall as the text measured (`size`). */
export function textMark(text, at, { width, height }, { color, fontPx }) {
  const value = String(text || "").trim();
  if (!value) return null;
  return { kind: "text", id: annotationId(), text: value, color, fontPx,
    corners: [at, { x: at.x + width, y: at.y }, { x: at.x + width, y: at.y + height }, { x: at.x, y: at.y + height }] };
}

/** Every screen point a mark lies on: what is projected to decide where it goes. */
export const markPoints = mark => (mark.kind === "stroke" ? mark.points : mark.kind === "area" ? mark.outline : mark.corners);

// ---- ink on the screen: hit-testing and fill --------------------------------------------------

/**
 * Ink already in the model as it falls on the screen now: each item's points projected (`screen`),
 * a stroke's at its on-screen width, an area and a text mark as the polygon they cover.
 * @typedef {{ id: string, kind: "stroke" | "area" | "text", points: ScreenPoint[], closed: boolean, width: number }} ScreenAnnotation
 */

function segmentDistance(point, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const length = dx * dx + dy * dy;
  const t = length ? Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / length)) : 0;
  return Math.hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy));
}
function inside(point, polygon) {
  let hit = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i], b = polygon[j];
    if ((a.y > point.y) !== (b.y > point.y) && point.x < ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}

/**
 * A point inside a closed outline on the screen, where a fill of it is seeded: its centroid, or, for
 * an outline that does not hold its centroid (a crescent), the middle of the first span inside it
 * along the centroid's row. Null for an outline with nothing inside.
 */
export function interiorPoint(polygon) {
  if (polygon.length < 3) return null;
  const centre = { x: polygon.reduce((sum, p) => sum + p.x, 0) / polygon.length, y: polygon.reduce((sum, p) => sum + p.y, 0) / polygon.length };
  if (inside(centre, polygon)) return centre;
  const crossings = [];
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i], b = polygon[j];
    if ((a.y > centre.y) !== (b.y > centre.y)) crossings.push(a.x + ((centre.y - a.y) * (b.x - a.x)) / (b.y - a.y));
  }
  crossings.sort((a, b) => a - b);
  return crossings.length >= 2 ? { x: (crossings[0] + crossings[1]) / 2, y: centre.y } : null;
}

/** How far a point is from a piece of ink on the screen: 0 inside an area or a text mark. */
export function annotationDistance(point, ink) {
  if (ink.kind !== "stroke" && ink.points.length >= 3 && inside(point, ink.points)) return 0;
  const path = ink.closed || ink.kind !== "stroke" ? [...ink.points, ink.points[0]] : ink.points;
  let best = Infinity;
  for (let index = 1; index < path.length; index += 1) best = Math.min(best, segmentDistance(point, path[index - 1], path[index]));
  if (path.length === 1) best = Math.hypot(point.x - path[0].x, point.y - path[0].y);
  return Math.max(0, best - (ink.kind === "stroke" ? ink.width / 2 : 0));
}

/** Ids with every piece drawn as one thing with them (`group`): what is erased, picked or moved together. */
export function withGroups(ids, items) {
  const chosen = new Set(ids);
  const groups = new Set(items.filter(item => chosen.has(item.id) && item.group).map(item => item.group));
  return items.filter(item => chosen.has(item.id) || (item.group && groups.has(item.group))).map(item => item.id);
}

/** The ink within `radius` pixels of `point`, nearest last-drawn first: what a press there takes. */
export function annotationAt(point, inks, radius = 6) {
  return inks.filter(ink => annotationDistance(point, ink) <= radius).reverse();
}

/**
 * The area a fill pressed at `seed` covers: the region the ink on the screen closes around it
 * (stroke ends near each other joined, as an annotation rarely closes exactly), as an area mark — or
 * `null` when no ink bounds it. The ink is rasterised at most `FILL_ANALYSIS_MAX_DIMENSION` pixels
 * a side, around the ink there is.
 */
export function fillMarkAt(seed, inks, color) {
  const outlines = inks.filter(ink => ink.kind === "stroke" && ink.points.length);
  if (!outlines.length) return null;
  const all = outlines.flatMap(ink => ink.points);
  const pad = 12;
  const minX = Math.min(...all.map(p => p.x)) - pad, minY = Math.min(...all.map(p => p.y)) - pad;
  const maxX = Math.max(...all.map(p => p.x)) + pad, maxY = Math.max(...all.map(p => p.y)) + pad;
  if (seed.x < minX || seed.x > maxX || seed.y < minY || seed.y > maxY) return null;
  const scale = Math.min(1, FILL_ANALYSIS_MAX_DIMENSION / Math.max(maxX - minX, maxY - minY, 1));
  const width = Math.max(3, Math.ceil((maxX - minX) * scale)), height = Math.max(3, Math.ceil((maxY - minY) * scale));
  const toMask = point => [(point.x - minX) * scale, (point.y - minY) * scale];
  const ink = new Uint8Array(width * height);
  const line = (mask, from, to, radius) => {
    const steps = Math.max(Math.abs(to[0] - from[0]), Math.abs(to[1] - from[1]), 1);
    const r = Math.max(1, Math.ceil(radius));
    for (let step = 0; step <= steps; step += 1) {
      const x = Math.round(from[0] + (to[0] - from[0]) * step / steps), y = Math.round(from[1] + (to[1] - from[1]) * step / steps);
      for (let dy = -r; dy <= r; dy += 1) for (let dx = -r; dx <= r; dx += 1) {
        if (dx * dx + dy * dy <= r * r && x + dx >= 0 && y + dy >= 0 && x + dx < width && y + dy < height) mask[(y + dy) * width + x + dx] = 1;
      }
    }
  };
  for (const outline of outlines) {
    const path = outline.closed ? [...outline.points, outline.points[0]] : outline.points;
    for (let index = 1; index < path.length; index += 1) line(ink, toMask(path[index - 1]), toMask(path[index]), (outline.width * scale) / 2);
  }
  const ends = outlines.filter(outline => !outline.closed && outline.points.length >= 2)
    .flatMap(outline => [outline.points[0], outline.points[outline.points.length - 1]].map(point => ({ point: toMask(point), strokeId: outline.id, allowSelfConnect: true })));
  const region = findFillRegion(gapPx => {
    const mask = ink.slice();
    for (const [from, to] of pairNearbyBoundaryEndpoints(ends, gapPx)) line(mask, from, to, 1);
    return mask;
  }, width, height, toMask(seed), { gapPx: FILL_CONNECT_GAP_PX * scale });
  if (!region) return null;
  // The region's points come back normalised to the mask's size (`normalizePolygonPoints`).
  const outline = region.points.map(point => ({ x: minX + (point.x * width) / scale, y: minY + (point.y * height) / scale }));
  return outline.length >= 3 ? { kind: "area", id: annotationId(), outline, color, opacity: FILL_OPACITY } : null;
}

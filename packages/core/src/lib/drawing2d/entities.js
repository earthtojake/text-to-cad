/**
 * A prepared drawing's entities (`prepareDrawing`'s `entities`), as a pointer meets them: which one
 * lies under a point (`entityAt`), where a point snaps (`snapAt`: an end, a centre, a point on a
 * line), and each one's outline for drawing it lit (`drawEntityHighlights`).
 *
 * All of it is in drawing coordinates, y up, against the primitives the payload sent: no DXF is
 * parsed here. An entity is what the payload names by handle, so a pick of anything a block draws
 * is its INSERT, and a dimension is one pick however many lines, arrows and words draw it.
 */
import { REFERENCE_HOVER_COLOR, REFERENCE_SELECTED_COLOR } from "../viewer/referenceGeometry.js";

/** Points along a curve segment, for a distance to it: plenty for a pick a few pixels wide. */
const CURVE_STEPS = 12;
/** A lit entity's stroke, in CSS pixels, at every zoom. */
export const DRAWING_HIGHLIGHT_CSS_PX = 3;

/**
 * Each run of a path's commands as a polyline of `[x, y]`: a curve sampled, `Z` closing its run.
 * @param {readonly (readonly any[])[]} commands
 * @returns {number[][][]}
 */
export function flattenPath(commands) {
  const runs = [];
  let run = null;
  let start = null;
  for (const command of commands) {
    const letter = command[0];
    if (letter === "M") {
      run = [[command[1], command[2]]];
      start = run[0];
      runs.push(run);
      continue;
    }
    if (!run) continue;
    const [x0, y0] = run[run.length - 1];
    if (letter === "L") run.push([command[1], command[2]]);
    else if (letter === "Q") {
      for (let step = 1; step <= CURVE_STEPS; step += 1) {
        const t = step / CURVE_STEPS, u = 1 - t;
        run.push([u * u * x0 + 2 * u * t * command[1] + t * t * command[3], u * u * y0 + 2 * u * t * command[2] + t * t * command[4]]);
      }
    } else if (letter === "C") {
      for (let step = 1; step <= CURVE_STEPS; step += 1) {
        const t = step / CURVE_STEPS, u = 1 - t;
        run.push([
          u * u * u * x0 + 3 * u * u * t * command[1] + 3 * u * t * t * command[3] + t * t * t * command[5],
          u * u * u * y0 + 3 * u * u * t * command[2] + 3 * u * t * t * command[4] + t * t * t * command[6]
        ]);
      }
    } else if (letter === "Z" && start) run.push([start[0], start[1]]);
  }
  return runs;
}

/** The point of segment `a`–`b` nearest `(x, y)`, and how far it is. */
function nearestOnSegment(x, y, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const length = dx * dx + dy * dy;
  const t = length ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / length)) : 0;
  const px = ax + t * dx, py = ay + t * dy;
  return { distance: Math.hypot(x - px, y - py), point: [px, py] };
}

/** Even-odd: whether `(x, y)` is inside the rings, as a filled region's holes are holes. */
function insideRings(rings, x, y) {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}

/** A text's quad in the drawing: its baseline box, descender to cap height, through its transform. */
function textQuad(item) {
  const [a, b, c, d, e, f] = item.transform;
  return [[0, -0.25 * item.height], [item.width, -0.25 * item.height], [item.width, 1.2 * item.height], [0, 1.2 * item.height]]
    .map(([x, y]) => [a * x + c * y + e, b * x + d * y + f]);
}

/**
 * A primitive's line-work as polylines and, for a fill, the rings it fills: what a distance, a snap
 * and an outline are measured on.
 */
function shapeOf(primitive) {
  const { type, geometry } = primitive;
  if (type === "lines") return { lines: geometry.map(line => [[line[0], line[1]], [line[2], line[3]]]) };
  if (type === "path") return { lines: flattenPath(geometry) };
  if (type === "filled-paths") { const rings = geometry.flatMap(flattenPath); return { lines: rings, rings }; }
  if (type === "filled-polygon") { const ring = geometry.map(vertex => [vertex[0], vertex[1]]); if (ring.length) ring.push(ring[0]); return { lines: [ring], rings: [ring] }; }
  if (type === "point") return { lines: [], points: [[geometry[0], geometry[1]]] };
  if (type === "text") { const quad = textQuad(primitive.item); return { lines: [[...quad, quad[0]]], rings: [quad], text: true }; }
  return { lines: [] };
}
// One entity's shapes, made at its first pick and kept: a drawing is read many times between edits.
const shapes = new WeakMap();
function entityShapes(entity) {
  let made = shapes.get(entity);
  if (!made) {
    made = entity.primitives.map(primitive => ({ layer: primitive.layer, ...shapeOf(primitive) }));
    shapes.set(entity, made);
  }
  return made;
}

const near = (box, x, y, reach) => Boolean(box) && x >= box[0] - reach && x <= box[2] + reach && y >= box[1] - reach && y <= box[3] + reach;
const shownShapes = (entity, hiddenLayers) => entityShapes(entity).filter(shape => !hiddenLayers?.has(shape.layer));

/**
 * How far `(x, y)` is from what an entity draws, in drawing units. Inside a filled region counts as
 * just within reach, so the lines drawn over a hatch are picked before the hatch; inside a word, as
 * on it.
 */
function entityDistance(entity, x, y, tolerance, hiddenLayers) {
  let best = Infinity;
  for (const shape of shownShapes(entity, hiddenLayers)) {
    for (const line of shape.lines) {
      for (let index = 1; index < line.length; index += 1) {
        const { distance } = nearestOnSegment(x, y, line[index - 1][0], line[index - 1][1], line[index][0], line[index][1]);
        if (distance < best) best = distance;
      }
    }
    for (const [px, py] of shape.points || []) best = Math.min(best, Math.hypot(x - px, y - py));
    if (shape.rings && insideRings(shape.rings, x, y)) best = Math.min(best, shape.text ? 0 : tolerance * 0.99);
  }
  return best;
}

/**
 * The handle of the entity under `point`, within `tolerance` drawing units of what it draws, or "".
 * The nearest wins; of two as near, the one drawn later (on top). Nothing on a hidden layer is there.
 *
 * @param {import("./drawing.js").PreparedDrawing} drawable
 * @param {readonly number[]} point  `[x, y]` in drawing coordinates.
 * @param {number} tolerance
 * @param {{ hiddenLayers?: ReadonlySet<string> | null }} [options]
 */
export function entityAt(drawable, point, tolerance, { hiddenLayers = null } = {}) {
  const [x, y] = point;
  let best = null;
  for (const entity of drawable?.entities?.values?.() || []) {
    if (!near(entity.box, x, y, tolerance)) continue;
    const distance = entityDistance(entity, x, y, tolerance, hiddenLayers);
    if (distance <= tolerance && (!best || distance <= best.distance)) best = { handle: entity.handle, distance };
  }
  return best?.handle || "";
}

/**
 * Where a point snaps, as a CAD program's object snap does: to the nearest end of a line or curve
 * (or a corner, or a point entity) or a circle's or arc's centre within `tolerance`; else to the
 * nearest point on a line within it; else nowhere (`free`, the point itself). `handle` is the entity
 * it snapped to.
 *
 * @param {import("./drawing.js").PreparedDrawing} drawable
 * @param {readonly number[]} point
 * @param {number} tolerance
 * @param {{ hiddenLayers?: ReadonlySet<string> | null }} [options]
 * @returns {{ point: number[], kind: "vertex" | "center" | "edge" | "free", handle: string }}
 */
export function snapAt(drawable, point, tolerance, { hiddenLayers = null } = {}) {
  const [x, y] = point;
  let corner = null, edge = null;
  const corners = (candidate, kind, handle) => {
    const distance = Math.hypot(x - candidate[0], y - candidate[1]);
    if (distance <= tolerance && (!corner || distance < corner.distance)) corner = { point: [candidate[0], candidate[1]], kind, handle, distance };
  };
  for (const entity of drawable?.entities?.values?.() || []) {
    if (!near(entity.box, x, y, tolerance)) continue;
    const shown = shownShapes(entity, hiddenLayers);
    if (!shown.length) continue;
    if (entity.center) corners(entity.center, "center", entity.handle);
    for (const shape of shown) {
      if (shape.text) continue;
      for (const vertex of shape.points || []) corners(vertex, "vertex", entity.handle);
      for (const line of shape.lines) {
        for (let index = 1; index < line.length; index += 1) {
          const nearest = nearestOnSegment(x, y, line[index - 1][0], line[index - 1][1], line[index][0], line[index][1]);
          if (nearest.distance <= tolerance && (!edge || nearest.distance < edge.distance)) edge = { ...nearest, kind: "edge", handle: entity.handle };
        }
      }
    }
    // The corners are the primitives' own: a line's ends, each path command's end point (a curve's
    // samples are not corners), a polygon's vertices.
    for (const primitive of entity.primitives) {
      if (hiddenLayers?.has(primitive.layer)) continue;
      if (primitive.type === "lines") for (const line of primitive.geometry) { corners([line[0], line[1]], "vertex", entity.handle); corners([line[2], line[3]], "vertex", entity.handle); }
      else if (primitive.type === "path" || primitive.type === "filled-paths") {
        const lists = primitive.type === "path" ? [primitive.geometry] : primitive.geometry;
        for (const commands of lists) for (const command of commands) if (command.length >= 3) corners(command.slice(-2), "vertex", entity.handle);
      } else if (primitive.type === "filled-polygon") for (const vertex of primitive.geometry) corners(vertex, "vertex", entity.handle);
    }
  }
  const found = corner || edge;
  return found ? { point: found.point, kind: found.kind, handle: found.handle } : { point: [x, y], kind: "free", handle: "" };
}

/** An entity's outline as one path (made once, kept): what it is lit along. */
const outlines = new WeakMap();
function entityOutline(drawable, entity, hiddenLayers) {
  const key = hiddenLayers?.size ? [...hiddenLayers].sort().join("\n") : "";
  const kept = outlines.get(entity);
  if (kept && kept.key === key) return kept.path;
  const path = new drawable.Path2D();
  for (const shape of shownShapes(entity, hiddenLayers)) {
    for (const line of shape.lines) {
      line.forEach(([px, py], index) => (index ? path.lineTo(px, py) : path.moveTo(px, py)));
    }
  }
  outlines.set(entity, { key, path });
  return path;
}

/**
 * Draw the entities hovered and selected lit, over the drawing: each one's outline in the viewer's
 * reference colours (a selection solid, a hover fainter), `DRAWING_HIGHLIGHT_CSS_PX` wide at any zoom.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {import("./drawing.js").PreparedDrawing} drawable
 * @param {{ transform: import("./transform.js").DrawingTransform, pixelRatio?: number,
 *   selected?: readonly string[], hovered?: readonly string[], hiddenLayers?: ReadonlySet<string> | null }} options
 *   `selected` and `hovered` are handles.
 */
export function drawEntityHighlights(ctx, drawable, { transform, pixelRatio = 1, selected = [], hovered = [], hiddenLayers = null }) {
  if (!drawable?.entities || !transform || (!selected.length && !hovered.length)) return;
  const { scale, offsetX, offsetY } = transform;
  ctx.save();
  ctx.setTransform(scale * pixelRatio, 0, 0, -scale * pixelRatio, offsetX * pixelRatio, offsetY * pixelRatio);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.lineWidth = DRAWING_HIGHLIGHT_CSS_PX / scale;
  const chosen = new Set(selected);
  const draw = (handles, color, alpha) => {
    ctx.strokeStyle = color;
    ctx.globalAlpha = alpha;
    for (const handle of handles) {
      const entity = drawable.entities.get(handle);
      if (entity) ctx.stroke(entityOutline(drawable, entity, hiddenLayers));
    }
  };
  draw(hovered.filter(handle => !chosen.has(handle)), REFERENCE_HOVER_COLOR, 0.9);
  draw(selected, REFERENCE_SELECTED_COLOR, 1);
  ctx.restore();
}

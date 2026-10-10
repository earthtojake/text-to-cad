/**
 * What a person is pointing at, drawn over a board's or a schematic's plot: the hovered item, the
 * selection, the measurement in hand and the markers of a check. The plot stays KiCad's picture;
 * this draws on top of it, in the same pass, so a capture of the view shows what was selected.
 *
 * `resolved` items come from an index's `resolve()` or `pick()` (`createBoardIndex`,
 * `createSchematicIndex`); geometry is in page millimetres. Pure canvas 2D: the viewer and a
 * headless capture draw the same thing.
 *
 * A net can be thousands of pads and tracks, and the viewer draws this on every hover change and
 * every frame of a pan, so shapes are drawn in PAGE space — the canvas's transform maps them,
 * through the bottom view's mirror — each from a path made once and kept with its item (`Path2D`),
 * and what lies off screen is left out. Each item is its own path: a canvas fills and strokes many
 * small paths far faster than one path of them all. Widths are screen pixels, as the person reads
 * them, whatever the zoom.
 *
 * In a board's Placement display (`placement`) the plot carries no copper and no drills (a via's
 * hole is routing), so this draws the pads (in KiCad's copper colours, the far side first), their
 * holes and the board's own, and every connection as an airwire (`boardAirwires`), under the dim
 * and the highlights. A net with a pour is joined by it, so its airwires are left out unless the
 * net is selected; a selected net's airwires are highlighted.
 */
import { pageToScreen } from "../plot2d/plot.js";
import { boardAirwires } from "./airwires.js";

/** The viewer's highlight (the CAD views' ink highlight), and how the rest steps back for a net. */
export const BOARD_OVERLAY_COLORS = Object.freeze({
  selection: "#8dc5ff",
  hover: "rgba(141, 197, 255, 0.55)",
  dim: "rgba(0, 8, 20, 0.6)",
  measure: "#ffd166",
  marker: "#ff6b6b",
});
/** On a schematic's paper the highlight is a deeper blue, and the rest is washed out, not darkened. */
export const SCHEMATIC_OVERLAY_COLORS = Object.freeze({
  selection: "#1f6feb",
  hover: "rgba(31, 111, 235, 0.5)",
  fill: "rgba(31, 111, 235, 0.08)",
  dim: "rgba(245, 244, 239, 0.72)",
  measure: "#d97706",
  marker: "#d93025",
});
const PART_FILL = "rgba(141, 197, 255, 0.10)";
const PART_PAD_FILL = "rgba(141, 197, 255, 0.35)";
const ZONE_FILL = "rgba(141, 197, 255, 0.12)";
const COPPER_ZONE_FILL = "rgba(141, 197, 255, 0.18)";
// Placement's pads, KiCad's default theme's F.Cu and B.Cu (a through-hole pad is the side looked at),
// and its airwires: thin, light, under everything a person points at.
const PLACEMENT_PAD_FILL = Object.freeze({ front: "rgba(200, 52, 52, 0.9)", back: "rgba(77, 127, 196, 0.9)" });
const AIRWIRE_COLOR = "rgba(232, 238, 245, 0.8)";
const PLACEMENT_HOLE_FILL = "#000000";
// Dots (vias, junctions, a pin's end) are filled a few dozen to a path.
const DOTS_PER_PATH = 64;

/**
 * A view of the page: `px` is one screen pixel in page millimetres, `shows(box, margin)` whether a
 * box (page mm) reaches the screen. `transform` maps page millimetres to CSS pixels; `mirrorX` is
 * the page x the board is mirrored about (the view from the bottom), or null.
 */
function createView(transform, { width, height, mirrorX = null } = {}) {
  const scale = transform.scale;
  const project = mirrorX == null ? (x, y) => pageToScreen(transform, x, y) : (x, y) => pageToScreen(transform, 2 * mirrorX - x, y);
  // The page box on screen, when the pane's size is known.
  let visible = null;
  if (width > 0 && height > 0) {
    let minX = -transform.offsetX / scale; let maxX = (width - transform.offsetX) / scale;
    if (mirrorX != null) [minX, maxX] = [2 * mirrorX - maxX, 2 * mirrorX - minX];
    visible = [minX, -transform.offsetY / scale, maxX, (height - transform.offsetY) / scale];
  }
  const shows = (box, margin = 0) => !visible || !box
    || (box[0] - margin <= visible[2] && box[2] + margin >= visible[0] && box[1] - margin <= visible[3] && box[3] + margin >= visible[1]);
  return { transform, mirrorX, px: 1 / scale, project, shows };
}

/** Draw in page millimetres from here on: the view's transform, its mirror and the pixel ratio. */
function pageSpace(ctx, view, pixelRatio) {
  const { scale, offsetX, offsetY } = view.transform;
  const s = scale * pixelRatio;
  if (view.mirrorX == null) ctx.setTransform(s, 0, 0, s, offsetX * pixelRatio, offsetY * pixelRatio);
  else ctx.setTransform(-s, 0, 0, s, (2 * view.mirrorX * scale + offsetX) * pixelRatio, offsetY * pixelRatio);
}

// ---- paths, in page space, made once per item -----------------------------------
function addPoints(target, points, closed) {
  if (points.length < 2) return;
  target.moveTo(points[0][0], points[0][1]);
  for (let index = 1; index < points.length; index += 1) target.lineTo(points[index][0], points[index][1]);
  if (closed) target.closePath();
}
// An item's path, by its points (the index keeps them for as long as the index lives).
const CLOSED_PATHS = new WeakMap();
const OPEN_PATHS = new WeakMap();
const cachePaths = typeof Path2D === "function";

/** Fill and/or stroke one shape: its kept path where the canvas takes one, else drawn afresh. */
function draw(ctx, points, closed, { fill = false, stroke = false }) {
  if (points.length < 2) return;
  if (cachePaths) {
    const paths = closed ? CLOSED_PATHS : OPEN_PATHS;
    let path = paths.get(points);
    if (!path) { path = new Path2D(); addPoints(path, points, closed); paths.set(points, path); }
    if (fill) ctx.fill(path);
    if (stroke) ctx.stroke(path);
    return;
  }
  ctx.beginPath();
  addPoints(ctx, points, closed);
  if (fill) ctx.fill();
  if (stroke) ctx.stroke();
}

/** Polygons (`{ polygon, box }`), each filled (`fill`) and stroked `width` screen pixels wide. */
function polygons(ctx, view, list, { color, width, fill = null }) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width * view.px;
  ctx.lineJoin = "miter";
  if (fill) ctx.fillStyle = fill;
  for (const item of list) {
    if (item.polygon.length < 2 || !view.shows(item.box, width * view.px)) continue;
    draw(ctx, item.polygon, true, { fill: Boolean(fill), stroke: true });
  }
}

/** Polylines (`{ points, box }`), each `widthOf(item)` page millimetres wide, round at their ends. */
function strokes(ctx, view, list, color, widthOf) {
  ctx.strokeStyle = color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const item of list) {
    const width = widthOf(item);
    if (item.points.length < 2 || !view.shows(item.box, width / 2)) continue;
    ctx.lineWidth = width;
    draw(ctx, item.points, false, { stroke: true });
  }
}

/** Dots at `item.at`, each `radiusOf(item)` page millimetres: a few dozen to a path. */
function dots(ctx, view, list, color, radiusOf) {
  ctx.fillStyle = color;
  let pending = 0;
  ctx.beginPath();
  for (const item of list) {
    const [x, y] = item.at;
    const radius = radiusOf(item);
    if (!view.shows([x, y, x, y], radius)) continue;
    ctx.moveTo(x + radius, y);
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    pending += 1;
    if (pending === DOTS_PER_PATH) { ctx.fill(); ctx.beginPath(); pending = 0; }
  }
  if (pending) ctx.fill();
}

// A track at least `minimum` screen pixels wide; a via's dot at least `minimum` pixels across its radius.
const trackWidth = (view, minimum) => (track) => Math.max(minimum * view.px, track.width);
const viaRadius = (view, minimum) => (via) => Math.max(minimum * view.px, via.diameter / 2);

/** Placement's layer: every pad, the side looked at drawn last, the holes, and the airwires of every net without a pour. */
function placementLayer(ctx, view, index) {
  const looked = view.mirrorX == null ? "top" : "bottom";
  const near = [];
  const far = [];
  for (const pad of index.padShapes) (pad.side === "both" || pad.side === looked ? near : far).push(pad);
  for (const [list, color] of [[far, looked === "top" ? PLACEMENT_PAD_FILL.back : PLACEMENT_PAD_FILL.front],
    [near, looked === "top" ? PLACEMENT_PAD_FILL.front : PLACEMENT_PAD_FILL.back]]) {
    ctx.fillStyle = color;
    for (const pad of list) if (pad.polygon.length > 2 && view.shows(pad.box)) draw(ctx, pad.polygon, true, { fill: true });
  }
  dots(ctx, view, [...index.padShapes.filter((pad) => pad.drill > 0), ...index.holes], PLACEMENT_HOLE_FILL,
    (hole) => (hole.drill || hole.diameter) / 2);
  const poured = (name) => index.nets.get(name)?.zones.length > 0;
  strokes(ctx, view, boardAirwires(index).filter((wire) => !poured(wire.net)), AIRWIRE_COLOR, () => view.px);
}

// ---- screen space: what keeps its size in pixels ---------------------------------
function crosshair(ctx, view, [x, y], color, size = 7) {
  const [sx, sy] = view.project(x, y);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(sx - size, sy); ctx.lineTo(sx + size, sy);
  ctx.moveTo(sx, sy - size); ctx.lineTo(sx, sy + size);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(sx, sy, size * 0.45, 0, Math.PI * 2);
  ctx.stroke();
}

// A schematic pin: its line from the body out to where a wire meets it, and a dot there.
const PIN_LINES = new WeakMap();
function pins(ctx, view, list, color, width) {
  const shown = list.filter((pin) => !pin.hidden && view.shows(pin.box, (width + 0.75) * view.px));
  if (!shown.length) return;
  const lines = shown.map((pin) => {
    let line = PIN_LINES.get(pin);
    if (!line) { line = { points: [pin.end, pin.at], box: pin.box }; PIN_LINES.set(pin, line); }
    return line;
  });
  strokes(ctx, view, lines, color, () => width * view.px);
  dots(ctx, view, shown, color, () => (width + 0.75) * view.px);
}

/**
 * One resolved schematic reference (or hit), highlighted in `color`, in page space (`pageSpace`).
 * `shapesOf(pin)`: every drawing of that pin (`index.shapesOf`).
 */
export function drawSchematicResolved(ctx, view, resolved, { color, fill, weight = 1, shapesOf = null }) {
  if (!resolved) return;
  const drawings = shapesOf || ((pad) => pad.part.pads.filter((shape) => shape.number === pad.number));
  if (resolved.kind === "part") {
    polygons(ctx, view, resolved.part.units.map((unit) => ({ polygon: unit.outline, box: unit.box })), { color, width: 2 * weight, fill });
    pins(ctx, view, resolved.part.pads, color, 1.5 * weight);
  } else if (resolved.kind === "pad") {
    pins(ctx, view, drawings(resolved.pad), color, 2.5 * weight);
  } else if (resolved.kind === "net") {
    const net = resolved.net;
    strokes(ctx, view, net.wires, color, () => 2.5 * weight * view.px);
    polygons(ctx, view, net.labels.map((label) => ({ polygon: label.outline, box: label.box })), { color, width: 1.5 * weight, fill });
    dots(ctx, view, net.junctions, color, () => 3.5 * weight * view.px);
    pins(ctx, view, net.pads.flatMap(drawings), color, 2 * weight);
  }
}

/**
 * One resolved board reference (or hit), highlighted in `color`. Its shapes are drawn in page
 * space (`pageSpace`); a point's crosshair keeps its size on screen, so it is handed back in
 * `crosshairs` for the caller to draw once the context is in pixels again. `shapesOf(pad)`: a pin's
 * pads (`index.shapesOf`).
 */
export function drawResolved(ctx, view, resolved, { color, toPage, weight = 1, shapesOf = null, crosshairs = null }) {
  if (!resolved) return;
  const kind = resolved.kind;
  const pinPads = shapesOf || ((pad) => pad.part.pads.filter((shape) => shape.number === pad.number));
  if (kind === "part") {
    const part = resolved.part;
    polygons(ctx, view, [{ polygon: part.outline, box: part.box }], { color, width: 2 * weight, fill: PART_FILL });
    polygons(ctx, view, part.pads, { color, width: 1, fill: PART_PAD_FILL });
  } else if (kind === "pad") {
    polygons(ctx, view, pinPads(resolved.pad), { color, width: 1.5 * weight, fill: color });
  } else if (kind === "net") {
    const net = resolved.net;
    polygons(ctx, view, net.zones.map((zone) => ({ polygon: zone.outline, box: zone.box })), { color, width: 1.5, fill: ZONE_FILL });
    strokes(ctx, view, net.tracks, color, trackWidth(view, 2));
    dots(ctx, view, net.vias, color, viaRadius(view, 2.5));
    polygons(ctx, view, net.pads.flatMap(pinPads), { color, width: 1, fill: color });
  } else if (kind === "copper" || kind === "point") {
    const item = kind === "copper" ? resolved.item : null;
    if (item?.kind === "track") strokes(ctx, view, [item], color, trackWidth(view, 3));
    else if (item?.kind === "via") dots(ctx, view, [item], color, viaRadius(view, 3));
    else if (item?.kind === "zone") polygons(ctx, view, [{ polygon: item.outline, box: item.box }], { color, width: 2, fill: COPPER_ZONE_FILL });
    crosshairs?.push({ at: resolved.page || toPage(resolved.at), color });
  }
}

/**
 * The overlay for one frame. `transform` maps page millimetres to CSS pixels; the context is set to
 * `pixelRatio` here. `dim`: the rest of the board steps back (a net or a check in focus).
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {ReturnType<typeof import("./boardIndex.js").createBoardIndex> | ReturnType<typeof import("./schematicIndex.js").createSchematicIndex>} index
 * @param {{ transform: object, pixelRatio?: number, width: number, height: number, hover?: object|null,
 *   selection?: object[], dim?: boolean, measure?: { points: number[][], draft?: number[]|null }|null,
 *   markers?: number[][], mirrorX?: number|null, colors?: typeof BOARD_OVERLAY_COLORS, placement?: boolean }} frame
 *   `mirrorX`: the page x the board is mirrored about (the view from the bottom), or null.
 *   `placement`: a board's Placement display, its pads and airwires drawn here.
 */
export function drawBoardOverlay(ctx, index, { transform, pixelRatio = 1, width, height, hover = null, selection = [], dim = false,
  measure = null, markers = [], mirrorX = null, colors = null, placement = false }) {
  if (!ctx || !index || !transform || !(transform.scale > 0)) return;
  const schematic = index.document === "schematic";
  colors = colors || (schematic ? SCHEMATIC_OVERLAY_COLORS : BOARD_OVERLAY_COLORS);
  const view = createView(transform, { width, height, mirrorX });
  const shapesOf = index.shapesOf || null;
  const crosshairs = [];
  const highlight = schematic
    ? (resolved, options) => drawSchematicResolved(ctx, view, resolved, { ...options, fill: colors.fill, shapesOf })
    : (resolved, options) => drawResolved(ctx, view, resolved, { ...options, toPage: index.toPage, shapesOf, crosshairs });
  ctx.save();
  placement = placement && !schematic;
  if (placement) {
    pageSpace(ctx, view, pixelRatio);
    placementLayer(ctx, view, index);
  }
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  if (dim && selection.length) {
    ctx.fillStyle = colors.dim;
    ctx.fillRect(0, 0, width, height);
  }
  pageSpace(ctx, view, pixelRatio);
  for (const resolved of selection) highlight(resolved, { color: colors.selection, weight: 1.25 });
  if (placement) {
    const nets = new Set(selection.filter((resolved) => resolved.kind === "net").map((resolved) => resolved.net.name));
    if (nets.size) strokes(ctx, view, boardAirwires(index).filter((wire) => nets.has(wire.net)), colors.selection, () => 2 * view.px);
  }
  if (hover && !selection.some((resolved) => resolved.selector === hover.selector)) highlight(hover, { color: colors.hover });
  // Back to screen pixels: the crosshairs, a check's rings and a measurement keep their size.
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  for (const { at, color } of crosshairs) crosshair(ctx, view, at, color);
  for (const marker of markers) {
    ctx.strokeStyle = colors.marker;
    ctx.lineWidth = 2;
    const [sx, sy] = view.project(marker[0], marker[1]);
    ctx.beginPath();
    ctx.arc(sx, sy, 9, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (measure && measure.points.length) {
    const points = (measure.draft ? [...measure.points, measure.draft] : measure.points).map(([x, y]) => view.project(x, y));
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    points.forEach(([sx, sy], at) => { if (at === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy); });
    ctx.strokeStyle = colors.measure;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = colors.measure;
    for (const [sx, sy] of points) {
      ctx.beginPath();
      ctx.arc(sx, sy, 3.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}

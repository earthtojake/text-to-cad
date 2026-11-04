/**
 * A `GET /api/v1/documents/kicad_pcb/<id>/plot` payload, laid out in one page space and drawn.
 *
 * A plot is a KiCad board drawn from its file (`docs/plot-payload.md`, schema 4): one sheet in
 * millimetres, y DOWN, on KiCad's board background, its LAYERS bottom to top as KiCad's PCB editor
 * draws them with the front copper active — the drawing sheet, the board's area, the back side,
 * the inner coppers, the user layers and the outline, the front side, then what goes through the
 * board: the pads' holes, the vias' holes, the ratsnest and the through-hole names — each a list of
 * ITEMS: filled polygons (pads, pours, filled graphics, the board's area with its cutouts), stroked
 * paths (tracks, graphics, a pour's outline and hatch), circles (via rings, holes), text as the
 * strokes of a permissive font, and labels (a pad's number and net, a via's net) laid out here in
 * that font (`strokeFont.js`). This module draws them on a 2D canvas in KiCad's default colours and
 * display (`theme.js`: pours at KiCad's zone opacity, plated holes seen through), so the viewer's
 * pane and the headless snapshot draw the same picture from the same payload.
 *
 * **Page space** is the payload's own: millimetres, x right, y down, the sheet's top-left corner
 * at the origin. The board's index (`payload.board`, sheet millimetres) is the layout's `board`.
 *
 * **The view transform is drawing2d's** (`../drawing2d/transform.js`): one uniform scale and a
 * translation, with fit, zoom and pan already written there. drawing2d's model space is y UP;
 * a plot's page is that model space with y negated, so `modelBounds` is the page box flipped
 * and `fitTransform(layout.modelBounds, …)` frames a plot as it frames a drawing — with a board's
 * wider margin (`boardFitMargin`: the 3D views' room round a model) and clear of the tool strip,
 * `fitPlotTransform`. With that flip, a transform maps page to screen as
 * `screen = page * scale + offset` on both axes.
 *
 * **A frame** (`drawPlot`) is the canvas filled with the sheet's background, then the layers a
 * `view` chooses, in its order: every layer by default (KiCad's default view), or the layers the
 * view names; the copper with or without its pours; from the top, or from below, each layer
 * mirrored about the sheet's vertical centre line and the board's stack reversed. Nothing is
 * clipped to the sheet: the sheet is the outline's box, which the fit frames (`bounds`), and what
 * the file draws past it (a fab note off the edge) is drawn where it falls; `extent` is the box of
 * everything drawn. A label is drawn only once the view is close enough for it to read (its
 * `lod`), as KiCad's level of detail decides, and so is a track's net name, which the payload does
 * not carry: it is laid out along the track as it is drawn (`trackNames.js`), since where KiCad
 * writes it depends on the size of the view. Each item's path is made once (`Path2D`) and kept
 * with the item, and what lies off the canvas is left out, so a board of tens of thousands of items
 * pans in a few milliseconds. The pane keeps rasters of a view made with this same function and
 * paints them with `drawPlotImages`.
 */
import { DRAWING_FIT_MARGIN, fitTransform, modelToScreen, screenToModel } from "../drawing2d/transform.js";
import { textStrokes } from "./strokeFont.js";
import { DIM_OPACITY, HOLE_COLORS, ZONE_OPACITY, itemColor, layerColor, netnameColor } from "./theme.js";
import { isTrack, trackNameDetail, trackNames } from "./trackNames.js";

/**
 * The payload shape this module understands. Must match `cad.engine.formats.kicad.PLOT_SCHEMA_VERSION`.
 */
export const PLOT_SCHEMA_VERSION = 4;

/** A board layer's side: what faces the top, the bottom, or neither (through the board). */
export const PLOT_LAYER_SIDES = Object.freeze(["front", "back", "both"]);
/** The item types a layer holds. */
export const PLOT_ITEM_TYPES = Object.freeze(["poly", "path", "circle", "text", "label"]);
/** Layer kinds drawn only when a view names them: none, as KiCad shows every layer of a board it opens. */
export const OPTIONAL_LAYER_KINDS = Object.freeze([]);
/** Layer kinds drawn under the stack from either side: the drawing sheet and the board's area. */
const UNDERLAY_KINDS = new Set(["area"]);
/** Layer kinds drawn over the stack from either side: what goes through the board. */
const OVERLAY_KINDS = new Set(["drill", "via", "ratsnest", "names"]);
/** A path of width 0 is drawn this many CSS pixels wide at every zoom: a hairline. */
export const PLOT_HAIRLINE_CSS_PX = 1;

const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

/**
 * @typedef {import("../drawing2d/transform.js").DrawingTransform} DrawingTransform
 *
 * @typedef {object} PlotItem One drawn thing, in sheet millimetres (`docs/plot-payload.md`).
 * @property {"poly"|"path"|"circle"|"text"|"label"} t
 * @property {readonly (readonly [number, number])[]} [pts] A polygon's vertices or a path's points.
 * @property {readonly (readonly (readonly [number, number])[])[]} [holes] A polygon's holes (the board's cutouts).
 * @property {readonly [number, number]} [at] A circle's centre, a label's.
 * @property {number} [r] A circle's radius.
 * @property {number} [w] A path's or a text's stroke width; a polygon's outline width; a circle's ring width (0 fills it); a hole's wall.
 * @property {boolean} [closed] A path that returns to its start.
 * @property {boolean} [pairs] A path of separate segments, its points taken two by two (a pour's hatch).
 * @property {string} [text] A text item's or a label's string.
 * @property {readonly (readonly (readonly [number, number])[])[]} [strokes] A text item's stroke polylines.
 * @property {readonly [number, number]} [size] A label's glyph height and width.
 * @property {number} [angle] A label's angle, degrees counter-clockwise.
 * @property {number} [lod] The CSS pixels per millimetre a view must show for a label to be drawn.
 * @property {"pad"|"via"} [kind] What a label names.
 * @property {string} [ref] The board reference of what drew it (`#R1`, `#R1.2`).
 * @property {string} [net] The net of a piece of copper.
 * @property {boolean} [pour] A zone's fill: hidden by a view without pours, drawn at KiCad's zone opacity.
 * @property {boolean} [teardrop] A pour that is a teardrop: drawn opaque, as KiCad draws teardrops.
 * @property {"through"|"blind"|"micro"} [via]
 * @property {"pad"|"via"|"npth"} [hole]
 * @property {readonly [string, string]} [span] A blind or buried via's hole: its top and bottom copper.
 * @property {number} [clearance] A front-copper pad's clearance: KiCad outlines it, a hairline that far out.
 * @property {readonly (readonly [number, number])[]} [knockout] Knocked-out text's box: filled, the letters cut from it.
 * @property {readonly [number, number, number, number]} box The item's page box, computed at layout.
 *
 * @typedef {object} PlotLayer
 * @property {string} id KiCad's layer (`"F.Cu"`), or `"vias"`, `"ratsnest"`, `"drills"`.
 * @property {string} kind `"copper"`, `"silk"`, `"fab"`, `"courtyard"`, `"mask"`, `"paste"`, `"adhesive"`, `"user"`, `"margin"`, `"outline"`, `"via"`, `"ratsnest"`, `"drill"`.
 * @property {"front"|"back"|"both"} side
 * @property {readonly PlotItem[]} items
 *
 * @typedef {object} PlotSheet
 * @property {number} index Its place in the payload (0: a board is one sheet).
 * @property {string} name
 * @property {readonly PlotLayer[]} layers Back to front.
 * @property {number} width Millimetres.
 * @property {number} height Millimetres.
 * @property {string} background The colour the board is drawn on, `#rrggbb`.
 * @property {number} x Page position of the sheet's top-left corner, millimetres.
 * @property {number} y
 *
 * @typedef {object} PlotLayout
 * @property {number} schemaVersion
 * @property {string} kind What the payload draws: `"board"`. Words only, never drawing.
 * @property {string} generator What wrote the file, for words: `"pcbnew 10.99"`.
 * @property {number|null} unrouted The board's connections still to make (the ratsnest's lines), else null.
 * @property {readonly PlotSheet[]} sheets
 * @property {object|null} board The board's index (`payload.board`), sheet millimetres; else null.
 * @property {readonly [number, number, number, number]} bounds The sheet's page box, `[minX, minY, maxX, maxY]`, y down: what the fit frames.
 * @property {readonly [number, number, number, number]} modelBounds The same box in drawing2d's model space, y up.
 * @property {readonly [number, number, number, number]} extent The page box of everything drawn: the sheet and every item, items past the sheet's edge included.
 *
 * @typedef {object} PlacedImage A raster of a view, placed in page space.
 * @property {CanvasImageSource|null} image
 * @property {number} x Page millimetres.
 * @property {number} y
 * @property {number} width
 * @property {number} height
 *
 * @typedef {object} PlotView What of a board to draw, and from which side.
 * @property {readonly string[]|null} [layers] The layer ids to draw (in the sheet's order); null or omitted for the board as it is made.
 * @property {boolean} [poured] False leaves the pours' fills out. Default true.
 * @property {"top"|"bottom"} [side] Bottom: the sheet mirrored left-right, the stack reversed. Default top.
 * @property {string|null} [active] The active layer, drawn on top of the board's stack (KiCad's); null keeps KiCad's order.
 * @property {string|null} [dim] With a layer id, every other layer but the board's area is drawn at `DIM_OPACITY` (KiCad's "Inactive layers: Dim").
 * @property {number} [zones] The pours' fill opacity, 0..1. Default KiCad's 0.6.
 * @property {number} [tracks] The tracks' opacity, 0..1. Default 1.
 */

function describe(value) {
  const text = JSON.stringify(value);
  return text === undefined ? String(value) : text;
}

function positive(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function isPoint(value) {
  return Array.isArray(value) && value.length === 2 && finite(value[0]) && finite(value[1]);
}

function boxOf(points, reach = 0) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  }
  return [minX - reach, minY - reach, maxX + reach, maxY + reach];
}

function layoutItem(item, where) {
  if (!item || typeof item !== "object" || !PLOT_ITEM_TYPES.includes(item.t)) {
    throw new Error(`${where} is not a plot item (one of ${PLOT_ITEM_TYPES.join(", ")}): ${describe(item)}.`);
  }
  const width = item.w === undefined ? 0 : item.w;
  if (!finite(width) || width < 0) throw new Error(`${where} (${item.t}) has a width that is no non-negative number: ${describe(item.w)}.`);
  let box;
  if (item.t === "circle") {
    if (!isPoint(item.at) || !positive(item.r)) throw new Error(`${where} (circle) needs a centre and a positive radius; received ${describe({ at: item.at, r: item.r })}.`);
    box = boxOf([item.at], item.r + width / 2);
  } else if (item.t === "label") {
    const size = item.size;
    if (typeof item.text !== "string" || !isPoint(item.at) || !Array.isArray(size) || size.length !== 2 || !positive(size[0]) || !positive(size[1])
      || !finite(item.angle ?? 0) || !finite(item.lod ?? 0)) {
      throw new Error(`${where} (label) needs a string, a centre, a positive size, an angle and a level of detail; received ${describe(item)}.`);
    }
    const strokes = textStrokes(item.text, { size, at: item.at, angle: item.angle ?? 0 });
    box = strokes.length ? boxOf(strokes.flat(), width / 2) : boxOf([item.at], 0);
  } else if (item.t === "text") {
    if (typeof item.text !== "string" || !Array.isArray(item.strokes) || !item.strokes.every((stroke) => Array.isArray(stroke) && stroke.length >= 2 && stroke.every(isPoint))) {
      throw new Error(`${where} (text) needs a string and strokes of two points or more; received ${describe(item.text)}.`);
    }
    box = boxOf(item.strokes.flat(), width / 2);
  } else {
    const least = item.t === "poly" ? 3 : 2;
    if (!Array.isArray(item.pts) || item.pts.length < least || !item.pts.every(isPoint)) {
      throw new Error(`${where} (${item.t}) needs ${least} points or more; received ${describe(item.pts)}.`);
    }
    if (item.holes !== undefined && (!Array.isArray(item.holes) || !item.holes.every((ring) => Array.isArray(ring) && ring.length >= 3 && ring.every(isPoint)))) {
      throw new Error(`${where} (${item.t}) has holes that are no rings of three points or more: ${describe(item.holes)}.`);
    }
    if (item.pairs && item.pts.length % 2) throw new Error(`${where} (path) pairs its points, so it needs an even number of them; received ${item.pts.length}.`);
    box = boxOf(item.pts, width / 2);
  }
  return Object.freeze({ ...item, w: width, box: Object.freeze(box) });
}

function layoutLayers(sheet, where) {
  if (!Array.isArray(sheet.layers) || sheet.layers.length === 0) {
    throw new Error(`${where} (${describe(sheet.name)}) carries no layers.`);
  }
  return Object.freeze(sheet.layers.map((layer, index) => {
    const at = `${where}.layers[${index}]`;
    if (!layer || typeof layer !== "object" || typeof layer.id !== "string" || !layer.id) {
      throw new Error(`${at} is not a layer with an id: ${describe(layer)}.`);
    }
    if (!PLOT_LAYER_SIDES.includes(layer.side)) {
      throw new Error(`${at} (${layer.id}) has side ${describe(layer.side)}; a layer is ${PLOT_LAYER_SIDES.join(", ")}.`);
    }
    if (!Array.isArray(layer.items)) throw new Error(`${at} (${layer.id}) carries no items array.`);
    const items = layer.items.map((item, number) => layoutItem(item, `${at} (${layer.id}).items[${number}]`));
    return Object.freeze({ id: layer.id, kind: String(layer.kind ?? ""), side: layer.side, items: Object.freeze(items) });
  }));
}

/**
 * A payload, validated and laid out.
 *
 * Throws — naming the offender — on a payload this build does not understand. A layer or an
 * item that silently went missing would be a plausible picture with part of the board gone.
 *
 * @param {object} payload
 * @returns {PlotLayout}
 */
export function layoutPlot(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`layoutPlot needs a plot payload object; received ${describe(payload)}.`);
  }
  if (payload.schemaVersion !== PLOT_SCHEMA_VERSION) {
    throw new Error(
      `This plot was made at payload schemaVersion ${describe(payload.schemaVersion)}, but this `
      + `build reads version ${PLOT_SCHEMA_VERSION}. Update cad-server and the app together so the `
      + "server and the viewer agree on the payload."
    );
  }
  const sheets = payload.sheets;
  if (!Array.isArray(sheets) || sheets.length !== 1) {
    throw new Error(`A plot payload's \`sheets\` is one board sheet; received ${describe(sheets)}.`);
  }
  const placed = sheets.map((sheet, index) => {
    const where = `sheets[${index}]`;
    if (!sheet || typeof sheet !== "object") {
      throw new Error(`${where} is not a sheet object: ${describe(sheet)}.`);
    }
    if (!positive(sheet.width) || !positive(sheet.height)) {
      throw new Error(
        `${where} (${describe(sheet.name)}) needs a positive width and height in millimetres; `
        + `received ${describe(sheet.width)} x ${describe(sheet.height)}.`
      );
    }
    if (typeof sheet.background !== "string" || !HEX_COLOR.test(sheet.background)) {
      throw new Error(
        `${where} (${describe(sheet.name)}) needs its background as a #rrggbb colour; received `
        + `${describe(sheet.background)}.`
      );
    }
    return Object.freeze({
      index, name: String(sheet.name ?? ""), layers: layoutLayers(sheet, where),
      width: sheet.width, height: sheet.height, background: sheet.background, x: 0, y: 0
    });
  });
  const [sheet] = placed;
  const board = payload.board && typeof payload.board === "object" && !Array.isArray(payload.board) ? payload.board : null;
  const bounds = [0, 0, sheet.width, sheet.height];
  const extent = [...bounds];
  for (const layer of sheet.layers) {
    for (const { box } of layer.items) {
      if (box[0] < extent[0]) extent[0] = box[0]; if (box[1] < extent[1]) extent[1] = box[1];
      if (box[2] > extent[2]) extent[2] = box[2]; if (box[3] > extent[3]) extent[3] = box[3];
    }
  }
  return Object.freeze({
    schemaVersion: payload.schemaVersion,
    kind: String(payload.kind ?? ""),
    generator: String(payload.generator ?? ""),
    unrouted: Number.isInteger(payload.unrouted) ? payload.unrouted : null,
    sheets: Object.freeze(placed),
    board,
    bounds: Object.freeze(bounds),
    modelBounds: Object.freeze([0, -sheet.height, sheet.width, 0]),
    extent: Object.freeze(extent)
  });
}

/** The share of a pane's smaller side a board's fit leaves on each side: the 3D views' default framing's room. */
export const BOARD_FIT_MARGIN_SHARE = 0.06;

/**
 * The room a board's fit leaves round it, in pane pixels: 6% of the pane's smaller side, never less
 * than drawing2d's 16px — the breathing room a STEP's default view has, more than a drawing's
 * fixed gutter. `cad kicad_pcb snapshot` frames with the same (`render/board.py`).
 *
 * @param {number} width
 * @param {number} height
 * @returns {number}
 */
export function boardFitMargin(width, height) {
  return Math.max(DRAWING_FIT_MARGIN, BOARD_FIT_MARGIN_SHARE * Math.min(width, height));
}

/**
 * The view that frames the sheet — the board's outline — in a `width` x `height` pane:
 * drawing2d's fit, through the flip, with a board's margin (`boardFitMargin`) and, where the view's
 * tool strip lies over its top, `top` pixels clear of it. What the file draws past the outline is
 * drawn where it falls. The board view's first view, its double-click and its card all fit so.
 *
 * @param {PlotLayout} layout
 * @param {number} width
 * @param {number} height
 * @param {{ top?: number }} [options]
 * @returns {DrawingTransform}
 */
export function fitPlotTransform(layout, width, height, { top = 0 } = {}) {
  return fitBoardBounds(layout.modelBounds, width, height, { top });
}

/** `fitPlotTransform` for a box of the board's (its outline, model space, y up). */
export function fitBoardBounds(bounds, width, height, { top = 0 } = {}) {
  return fitTransform(bounds, width, height, { margin: boardFitMargin(width, height), top });
}

/**
 * Page point to screen point.
 *
 * @param {DrawingTransform} transform
 * @param {number} x
 * @param {number} y
 * @returns {[number, number]}
 */
export function pageToScreen(transform, x, y) {
  return modelToScreen(transform, x, -y);
}

/**
 * Screen point to page point. The exact inverse of `pageToScreen`.
 *
 * @param {DrawingTransform} transform
 * @param {number} x
 * @param {number} y
 * @returns {[number, number]}
 */
export function screenToPage(transform, x, y) {
  const [modelX, modelY] = screenToModel(transform, x, y);
  return [modelX, -modelY];
}

/**
 * The page rectangle a `width` x `height` pane shows, `[minX, minY, maxX, maxY]`.
 *
 * @param {DrawingTransform} transform
 * @param {number} width CSS pixels.
 * @param {number} height CSS pixels.
 */
export function visiblePageRect(transform, width, height) {
  const [minX, minY] = screenToPage(transform, 0, 0);
  const [maxX, maxY] = screenToPage(transform, width, height);
  return [minX, minY, maxX, maxY];
}

/** Whether two `[minX, minY, maxX, maxY]` boxes overlap with some area. */
export function rectsOverlap(left, right) {
  return left[0] < right[2] && right[0] < left[2] && left[1] < right[3] && right[1] < left[3];
}

/**
 * A page x mirrored about sheet `sheetIndex`'s vertical centre line: where a point of the board
 * seen from the top is drawn when the board is seen from below (`view.side: "bottom"`), and back.
 *
 * @param {PlotLayout} layout
 * @param {number} sheetIndex
 * @param {number} x Page millimetres.
 */
export function mirrorPageX(layout, sheetIndex, x) {
  const sheet = layout.sheets[sheetIndex];
  if (!sheet) throw new Error(`This plot has no sheet ${describe(sheetIndex)}.`);
  return 2 * sheet.x + sheet.width - x;
}

/**
 * A sheet's layers in the order `view` draws them. A view that names no layers draws every layer,
 * as KiCad shows a board it opens; a view's `layers` choose (a board's Display modes, its Layers).
 *
 * @param {PlotSheet} sheet
 * @param {PlotView|null} view
 * @returns {PlotLayer[]}
 */
export function viewedLayers(sheet, view) {
  const chosen = Array.isArray(view?.layers) ? new Set(view.layers) : null;
  const kept = sheet.layers.filter((layer) => (chosen ? chosen.has(layer.id) : !OPTIONAL_LAYER_KINDS.includes(layer.kind)));
  // From below, the board's stack reverses — the back layers face the viewer — while the board's
  // area stays under it and what goes through the board stays over it; the active layer tops the stack.
  const stack = kept.filter((layer) => !OVERLAY_KINDS.has(layer.kind) && !UNDERLAY_KINDS.has(layer.kind));
  if (view?.side === "bottom") stack.reverse();
  const active = stack.findIndex((layer) => layer.id === view?.active);
  if (active >= 0) stack.push(...stack.splice(active, 1));
  return [...kept.filter((layer) => UNDERLAY_KINDS.has(layer.kind)), ...stack, ...kept.filter((layer) => OVERLAY_KINDS.has(layer.kind))];
}

// ---- paths, in page space, made once per item ----------------------------------
const PATHS = new WeakMap();
// A label's strokes, laid out once for each side it is seen from (from below, it is laid out mirrored
// so the mirrored canvas shows it reading the right way round, as KiCad shows its names).
const LABELS = new WeakMap();
// A track's names, laid out for the last view size and side they were drawn for: `{ key, path }`.
const TRACK_NAMES = new WeakMap();

function addPolyline(target, points, closed) {
  target.moveTo(points[0][0], points[0][1]);
  for (let index = 1; index < points.length; index += 1) target.lineTo(points[index][0], points[index][1]);
  if (closed) target.closePath();
}

function addPairs(target, points) {
  for (let index = 0; index + 1 < points.length; index += 2) {
    target.moveTo(points[index][0], points[index][1]);
    target.lineTo(points[index + 1][0], points[index + 1][1]);
  }
}

function addCircle(target, at, radius) {
  target.moveTo(at[0] + radius, at[1]);
  target.arc(at[0], at[1], radius, 0, Math.PI * 2);
}

function labelStrokes(item, mirrored) {
  let laid = LABELS.get(item);
  if (!laid) LABELS.set(item, (laid = {}));
  const key = mirrored ? "bottom" : "top";
  if (!laid[key]) laid[key] = textStrokes(item.text, { size: item.size, at: item.at, angle: item.angle ?? 0, mirror: mirrored });
  return laid[key];
}

function addItem(target, item, mirrored) {
  if (item.t === "circle") {
    addCircle(target, item.at, item.r);
  } else if (item.t === "text") {
    for (const stroke of item.strokes) addPolyline(target, stroke, false);
  } else if (item.t === "label") {
    for (const stroke of labelStrokes(item, mirrored)) addPolyline(target, stroke, false);
  } else if (item.pairs) {
    addPairs(target, item.pts);
  } else {
    addPolyline(target, item.pts, item.t === "poly" || item.closed === true);
    for (const ring of item.holes || []) addPolyline(target, ring, true);
  }
}

/** The item's path, kept with it where the canvas takes a `Path2D`; else drawn into the context afresh. */
function pathOf(ctx, item, PathCtor, mirrored = false) {
  if (typeof PathCtor !== "function") {
    ctx.beginPath();
    addItem(ctx, item, mirrored);
    return null;
  }
  const keep = item.t === "label" ? (mirrored ? "bottom" : "top") : "any";
  let paths = PATHS.get(item);
  if (!paths) PATHS.set(item, (paths = {}));
  if (!paths[keep]) {
    paths[keep] = new PathCtor();
    addItem(paths[keep], item, mirrored);
  }
  return paths[keep];
}

function fill(ctx, path, rule = "nonzero") {
  if (path) ctx.fill(path, rule);
  else ctx.fill(rule);
}

function stroke(ctx, path) {
  if (path) ctx.stroke(path);
  else ctx.stroke();
}

/** Stroke a track's names for this view: laid out again only when the view's size changes how many it carries. */
function strokeTrackNames(ctx, item, viewport, mirrored, PathCtor) {
  const names = trackNames(item, viewport);
  if (names.length === 0) return;
  const key = `${mirrored ? "b" : "t"}${names.length}`;
  const add = (target) => {
    for (const name of names) {
      for (const points of textStrokes(name.text, { size: name.size, at: name.at, angle: name.angle, mirror: mirrored })) {
        addPolyline(target, points, false);
      }
    }
  };
  ctx.lineWidth = names[0].w;
  if (typeof PathCtor !== "function") {
    ctx.beginPath();
    add(ctx);
    ctx.stroke();
    return;
  }
  let laid = TRACK_NAMES.get(item);
  if (!laid || laid.key !== key) {
    const path = new PathCtor();
    add(path);
    TRACK_NAMES.set(item, (laid = { key, path }));
  }
  ctx.stroke(laid.path);
}

/**
 * A convex outline grown by `distance` with round corners, as KiCad grows a pad by its clearance:
 * each side moved out, each corner an arc between them.
 */
export function grownOutline(points, distance) {
  const count = points.length;
  let area = 0;
  for (let index = 0; index < count; index += 1) {
    const [x1, y1] = points[index];
    const [x2, y2] = points[(index + 1) % count];
    area += x1 * y2 - x2 * y1;
  }
  const sign = area > 0 ? 1 : -1;
  const normal = (a, b) => {
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    return length > 1e-12 ? [sign * (b[1] - a[1]) / length, -sign * (b[0] - a[0]) / length] : null;
  };
  const out = [];
  let previous = null;
  for (let index = 0; index < count && previous === null; index += 1) previous = normal(points[(index - 1 + count) % count], points[index]);
  for (let index = 0; index < count; index += 1) {
    const here = points[index];
    const next = normal(here, points[(index + 1) % count]);
    if (!next) continue;
    const from = Math.atan2(previous[1], previous[0]);
    let sweep = Math.atan2(next[1], next[0]) - from;
    // Round the corner the way the outline turns, never the long way about.
    while (sign * sweep < 0) sweep += sign * Math.PI * 2;
    if (Math.abs(sweep) > Math.PI) sweep -= sign * Math.PI * 2;
    const steps = Math.max(1, Math.ceil(Math.abs(sweep) / (Math.PI / 8)));
    for (let step = 0; step <= steps; step += 1) {
      const angle = from + (sweep * step) / steps;
      out.push([here[0] + distance * Math.cos(angle), here[1] + distance * Math.sin(angle)]);
    }
    previous = next;
  }
  return out;
}

const OUTLINES = new WeakMap();

/** A pad's clearance outline, made once: KiCad's hairline around the pad on the copper being edited. */
function clearancePath(item, PathCtor) {
  let path = OUTLINES.get(item);
  if (!path) {
    path = new PathCtor();
    addPolyline(path, grownOutline(item.pts, item.clearance), true);
    OUTLINES.set(item, path);
  }
  return path;
}

/**
 * Knocked-out text: its box in the layer's colour with the letters cut from it, so what lies under the
 * text shows through them. Drawn on a canvas of its own and laid on; without one (a context that
 * draws nothing, a recording double), the letters are drawn in the board's background instead.
 */
function drawKnockout(ctx, item, paint, background, PathCtor) {
  const box = new Array(item.knockout.length);
  const strokeLetters = (target) => {
    target.beginPath();
    for (const stroke of item.strokes) addPolyline(target, stroke, false);
    target.stroke();
  };
  const outline = (target) => {
    target.beginPath();
    addPolyline(target, item.knockout, true);
  };
  const transform = typeof ctx.getTransform === "function" ? ctx.getTransform() : null;
  const document = ctx.canvas?.ownerDocument;
  const make = typeof OffscreenCanvas === "function" ? (w, h) => new OffscreenCanvas(w, h)
    : document ? (w, h) => Object.assign(document.createElement("canvas"), { width: w, height: h }) : null;
  if (transform && make) {
    item.knockout.forEach(([x, y], index) => { box[index] = [transform.a * x + transform.c * y + transform.e, transform.b * x + transform.d * y + transform.f]; });
    const left = Math.max(0, Math.floor(Math.min(...box.map((p) => p[0]))));
    const top = Math.max(0, Math.floor(Math.min(...box.map((p) => p[1]))));
    const right = Math.min(ctx.canvas.width, Math.ceil(Math.max(...box.map((p) => p[0]))));
    const bottom = Math.min(ctx.canvas.height, Math.ceil(Math.max(...box.map((p) => p[1]))));
    if (right <= left || bottom <= top) return;
    const layer = make(right - left, bottom - top);
    const into = layer.getContext("2d");
    if (into) {
      into.setTransform(transform.a, transform.b, transform.c, transform.d, transform.e - left, transform.f - top);
      into.fillStyle = paint;
      outline(into);
      into.fill();
      into.globalCompositeOperation = "destination-out";
      into.lineCap = "round";
      into.lineJoin = "round";
      into.lineWidth = item.w;
      strokeLetters(into);
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(layer, left, top);
      ctx.restore();
      return;
    }
  }
  ctx.fillStyle = paint;
  outline(ctx);
  ctx.fill();
  ctx.strokeStyle = background;
  ctx.lineWidth = item.w;
  strokeLetters(ctx);
}

/** A disc's path, made afresh: a hole's wall and a blind via's two halves are drawn from their item's centre. */
function disc(ctx, at, radius, start = 0, end = Math.PI * 2) {
  ctx.beginPath();
  if (end - start < Math.PI * 2) ctx.moveTo(at[0], at[1]);
  ctx.arc(at[0], at[1], radius, start, end);
  ctx.closePath();
}

/**
 * A hole as KiCad paints it: its plated wall a ring `w` wide around it, then the hole — the board's
 * background for a pad's (seen through), golden for a via's, two halves in its end layers' copper for a
 * blind or buried via's — or cyan for an unplated one.
 */
function drawHole(ctx, item, background, PathCtor) {
  const colors = HOLE_COLORS[item.hole] || HOLE_COLORS.npth;
  if (item.t === "circle") {
    if (item.w > 0 && colors.wall) {
      ctx.fillStyle = colors.wall;
      disc(ctx, item.at, item.r + item.w);
      ctx.fill();
    }
    if (item.span && item.span.length === 2) {
      // KiCad's DrawArc from 180 degrees is the half on top of the screen: the via's top layer.
      ctx.fillStyle = layerColor(item.span[0]);
      disc(ctx, item.at, item.r, Math.PI, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = layerColor(item.span[1]);
      disc(ctx, item.at, item.r, 0, Math.PI);
      ctx.fill();
      return;
    }
    ctx.fillStyle = colors.fill || background;
    fill(ctx, pathOf(ctx, item, PathCtor));
    return;
  }
  // A slot: its outline stroked for the wall, then filled.
  const path = pathOf(ctx, item, PathCtor);
  if (item.w > 0 && colors.wall) {
    ctx.strokeStyle = colors.wall;
    ctx.lineWidth = item.w * 2;
    stroke(ctx, path);
  }
  ctx.fillStyle = colors.fill || background;
  fill(ctx, path);
}

/** Draw in page millimetres from here on: the view's transform, its mirror and the pixel ratio. */
function pageSpace(ctx, transform, pixelRatio, mirrorX) {
  const { scale, offsetX, offsetY } = transform;
  const s = scale * pixelRatio;
  if (mirrorX == null) ctx.setTransform(s, 0, 0, s, offsetX * pixelRatio, offsetY * pixelRatio);
  else ctx.setTransform(-s, 0, 0, s, (2 * mirrorX * scale + offsetX) * pixelRatio, offsetY * pixelRatio);
}

function drawLayer(ctx, layer, { hairline, poured, visible, PathCtor, detail, background, mirrored, vias, names, viewport, fade = 1, zones = ZONE_OPACITY,
  tracks = 1 }) {
  const color = layerColor(layer.id);
  const copper = layer.kind === "copper";
  // The tracks whose net names this frame writes, over everything else on their copper (KiCad's netname layer).
  const named = [];
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.globalAlpha = fade;
  for (const item of layer.items) {
    if (!poured && item.pour) continue;
    // A via's copper goes with its hole (the vias layer), and every name with the names layer, as KiCad's
    // Vias and its pad and net names are shown or hidden as one.
    if ((!vias && item.via && !item.hole) || (!names && item.t === "label")) continue;
    if (visible && !rectsOverlap(visible, item.box)) continue;
    if (copper && names && isTrack(item) && detail >= trackNameDetail(item.w)) named.push(item);
    if (item.hole) {
      drawHole(ctx, item, background, PathCtor);
      continue;
    }
    if (item.t === "label") {
      // KiCad's level of detail: a name is drawn once its pad or via reads at this scale.
      if (detail < (item.lod || 0)) continue;
      // At its own stroke, however thin: KiCad's names fade out as the view draws back, never bolden.
      ctx.strokeStyle = itemColor(layer.id, item);
      ctx.lineWidth = item.w > 0 ? item.w : hairline;
      stroke(ctx, pathOf(ctx, item, PathCtor, mirrored));
      continue;
    }
    const paint = color;
    if (item.knockout) {
      drawKnockout(ctx, item, paint, background, PathCtor);
      continue;
    }
    if (item.clearance > 0 && typeof PathCtor === "function") {
      ctx.strokeStyle = paint;
      ctx.lineWidth = hairline;
      ctx.stroke(clearancePath(item, PathCtor));
    }
    const path = pathOf(ctx, item, PathCtor);
    // A pour is drawn at the zones' opacity (KiCad's 60%); a teardrop, as KiCad draws it, opaque; a
    // track at the tracks' opacity; all of it at the layer's (a dimmed layer's).
    const alpha = item.pour && !item.teardrop ? zones : copper && isTrack(item) ? tracks : 1;
    if (alpha !== 1) ctx.globalAlpha = fade * alpha;
    if (item.t === "poly") {
      ctx.fillStyle = paint;
      fill(ctx, path, item.holes ? "evenodd" : undefined);
      // A pad is never thinner than a pixel, as KiCad draws pads: fine-pitch rows read as bars from afar.
      const width = copper && item.ref ? Math.max(item.w, hairline) : item.w;
      if (width > 0) {
        ctx.strokeStyle = paint;
        ctx.lineWidth = width;
        stroke(ctx, path);
      }
    } else if (item.t === "circle" && item.w === 0) {
      ctx.fillStyle = paint;
      fill(ctx, path);
    } else {
      // A line is never thinner than a pixel (KiCad's minimum line width), but copper keeps its own width:
      // KiCad's tracks thin out as the view draws back.
      ctx.strokeStyle = paint;
      ctx.lineWidth = item.w > 0 ? (copper ? item.w : Math.max(item.w, hairline)) : hairline;
      stroke(ctx, path);
    }
    if (alpha !== 1) ctx.globalAlpha = fade;
  }
  if (named.length > 0) {
    ctx.strokeStyle = netnameColor(layer.id);
    for (const item of named) strokeTrackNames(ctx, item, viewport, mirrored, PathCtor);
  }
  ctx.globalAlpha = 1;
}

/** What the canvas shows, in page millimetres, when the context has a sized canvas; else null. */
function shownRect(ctx, transform, pixelRatio) {
  const canvas = ctx.canvas;
  return canvas && canvas.width > 0 && canvas.height > 0
    ? visiblePageRect(transform, canvas.width / pixelRatio, canvas.height / pixelRatio)
    : null;
}

const clampUnit = (value, fallback) => (typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : fallback);

function checkTransform(transform, who) {
  if (!transform || !(transform.scale > 0)) {
    throw new Error(`${who} needs a transform with a positive scale; received ${describe(transform)}.`);
  }
}

/**
 * The background under the board alone, for a picture on a card: its area (the outline filled, its
 * cutouts open) in the sheet's background, nothing round it — the board's shape, never a box of
 * canvas. A board with no outline fills its sheet.
 */
function drawBoardBackdrop(ctx, sheet, { transform, pixelRatio, mirrorX, PathCtor }) {
  const area = sheet.layers.find((layer) => layer.kind === "area");
  if (!area?.items.length) {
    ctx.fillRect(sheet.x, sheet.y, sheet.width, sheet.height);
    return;
  }
  pageSpace(ctx, transform, pixelRatio, mirrorX);
  for (const item of area.items) fill(ctx, pathOf(ctx, item, PathCtor, mirrorX != null), item.holes ? "evenodd" : undefined);
}

/**
 * Draw one frame of a plot: the canvas in the sheet's background, then the layers `view` chooses,
 * in its order, each item in KiCad's colours, all in page space under the view. Nothing is clipped
 * to the sheet: an item past the outline is drawn where it falls, as KiCad draws it.
 *
 * The context carries the whole view (page millimetres to device pixels), so the picture is
 * exact at any zoom. A path of width 0 (a ratsnest line, a pour's outline) is a hairline of
 * `PLOT_HAIRLINE_CSS_PX`. Nothing outside the canvas is drawn. Without a `view`, a board is every
 * layer, poured, from the top: KiCad's default view.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {PlotLayout} layout
 * @param {{ transform: DrawingTransform, pixelRatio?: number, view?: PlotView|null, detail?: number,
 *   viewport?: readonly [number, number], backdrop?: "canvas" | "board", Path2D?: any }} options
 *   `detail` is the CSS pixels per millimetre the view shows, for the labels' level of detail
 *   (`transform.scale` when omitted: a raster drawn at device scale passes its view's own), and
 *   `viewport` the millimetres it shows across and down, for where the tracks' names fall (what the
 *   canvas shows when omitted: a raster larger than its view passes the view's own).
 *   `backdrop`: `"canvas"`, the canvas the sheet's background everywhere (the view, a snapshot), or
 *   `"board"`, the board's own area alone, the rest left clear (a library card's picture).
 *   `Path2D` is injectable so this module is exercised in `node --test` with a recording double.
 */
export function drawPlot(ctx, layout, { transform, pixelRatio = 1, view = null, detail = null, viewport = null, backdrop = "canvas",
  Path2D: PathCtor = globalThis.Path2D }) {
  checkTransform(transform, "drawPlot");
  const visible = shownRect(ctx, transform, pixelRatio);
  const across = viewport ?? (visible ? [visible[2] - visible[0], visible[3] - visible[1]] : null);
  const hairline = PLOT_HAIRLINE_CSS_PX / transform.scale;
  const poured = view?.poured !== false;
  const scale = detail > 0 ? detail : transform.scale;
  const named = Array.isArray(view?.layers) ? new Set(view.layers) : null;
  const vias = !named || named.has("vias");
  const names = !named || named.has("names");
  const zones = clampUnit(view?.zones, ZONE_OPACITY);
  const tracks = clampUnit(view?.tracks, 1);
  const dimmed = typeof view?.dim === "string" && view.dim ? view.dim : null;
  ctx.save();
  for (const sheet of layout.sheets) {
    const mirrorX = view?.side === "bottom" ? sheet.x + sheet.width / 2 : null;
    // What the canvas shows, mirrored back into the board's own coordinates.
    const shown = visible && mirrorX != null ? [2 * mirrorX - visible[2], visible[1], 2 * mirrorX - visible[0], visible[3]] : visible;
    if (shown && !rectsOverlap(shown, layout.extent)) continue;
    pageSpace(ctx, transform, pixelRatio, null);
    ctx.fillStyle = sheet.background;
    if (backdrop === "board") drawBoardBackdrop(ctx, sheet, { transform, pixelRatio, mirrorX, PathCtor });
    else if (visible) ctx.fillRect(visible[0], visible[1], visible[2] - visible[0], visible[3] - visible[1]);
    else ctx.fillRect(sheet.x, sheet.y, sheet.width, sheet.height);
    for (const layer of viewedLayers(sheet, view)) {
      pageSpace(ctx, transform, pixelRatio, mirrorX);
      drawLayer(ctx, layer, {
        hairline, poured, visible: shown, PathCtor, detail: scale, background: sheet.background, mirrored: mirrorX != null, vias, names, zones, tracks,
        fade: dimmed && layer.id !== dimmed && !UNDERLAY_KINDS.has(layer.kind) ? DIM_OPACITY : 1,
        viewport: across ?? [sheet.width, sheet.height]
      });
    }
  }
  ctx.restore();
}

/**
 * The pane's frame: each visible sheet's rectangle in its background, then `images` — rasters of
 * a view made with `drawPlot`, placed in page space — over them. An image that misses the canvas
 * costs nothing.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {PlotLayout} layout
 * @param {{ transform: DrawingTransform, pixelRatio?: number, images: readonly PlacedImage[] }} options
 */
export function drawPlotImages(ctx, layout, { transform, pixelRatio = 1, images = [] }) {
  checkTransform(transform, "drawPlotImages");
  const visible = shownRect(ctx, transform, pixelRatio);
  const shows = (x, y, width, height) => !visible || rectsOverlap(visible, [x, y, x + width, y + height]);
  ctx.save();
  pageSpace(ctx, transform, pixelRatio, null);
  for (const sheet of layout.sheets) {
    if (!shows(sheet.x, sheet.y, sheet.width, sheet.height)) continue;
    ctx.fillStyle = sheet.background;
    ctx.fillRect(sheet.x, sheet.y, sheet.width, sheet.height);
  }
  for (const { image, x, y, width, height } of images) {
    if (!image || !(width > 0) || !(height > 0) || !shows(x, y, width, height)) continue;
    ctx.drawImage(image, x, y, width, height);
  }
  ctx.restore();
}

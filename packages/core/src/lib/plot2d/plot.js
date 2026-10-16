/**
 * A `GET /__cad/plot` payload, laid out in one page space and drawn.
 *
 * A plot is a KiCad board drawn from its file (`docs/plot-payload.md`, schema 3): one sheet in
 * millimetres, y DOWN, on KiCad's board background, its LAYERS back to front — bottom courtyard,
 * fabrication, silkscreen, paste and mask, bottom copper, the inner coppers, top copper, mask,
 * paste, silkscreen, fabrication and courtyard, the user layers, the outline, then what goes
 * through the board: the vias, the ratsnest and the drill holes — each a list of ITEMS: filled
 * polygons (pads, pours, filled graphics), stroked paths (tracks, graphics, a pour's outline),
 * circles (vias, holes) and text as the strokes of a permissive font. This module draws them on a
 * 2D canvas in KiCad's default colours (`theme.js`), so the viewer's pane and the headless
 * snapshot bundle draw the same picture from the same payload, as the DXF view draws its own
 * geometry.
 *
 * **Page space** is the payload's own: millimetres, x right, y down, the sheet's top-left corner
 * at the origin. The board's index (`payload.board`, sheet millimetres) is the layout's `board`.
 *
 * **The view transform is drawing2d's** (`../drawing2d/transform.js`): one uniform scale and a
 * translation, with fit, zoom and pan already written there. drawing2d's model space is y UP;
 * a plot's page is that model space with y negated, so `modelBounds` is the page box flipped
 * and `fitTransform(layout.modelBounds, …)` frames a plot exactly as it frames a drawing. With
 * that flip, a transform maps page to screen as `screen = page * scale + offset` on both axes.
 *
 * **A frame** (`drawPlot`) is the sheet's rectangle filled with its background, then the layers
 * a `view` chooses, in its order: every layer but the courtyards, mask and paste by default (the
 * board as it is made, which the snapshot and a library card draw), or the layers the view names;
 * the copper with or without its pours; from the top, or from below, each layer mirrored about
 * the sheet's vertical centre line and the stack reversed. Nothing is clipped to the sheet: the
 * sheet is the outline's box, which the fit frames (`bounds`), and what the file draws past it
 * (a fab note off the edge, as KiCad draws it) is drawn over the surround; `extent` is the box of
 * everything drawn. Each item's path is made once (`Path2D`) and kept with the item, and what
 * lies off the canvas is left out, so a board of tens of thousands of items pans in a few
 * milliseconds. The pane keeps rasters of a view made with this same function and paints them
 * with `drawPlotImages`.
 */
import { fitTransform, modelToScreen, screenToModel } from "../drawing2d/transform.js";
import { itemColor, layerColor } from "./theme.js";

/**
 * The payload shape this module understands. Must match `cadgen.plot.PLOT_SCHEMA_VERSION`.
 */
export const PLOT_SCHEMA_VERSION = 3;

/** A board layer's side: what faces the top, the bottom, or neither (through the board). */
export const PLOT_LAYER_SIDES = Object.freeze(["front", "back", "both"]);
/** The item types a layer holds. */
export const PLOT_ITEM_TYPES = Object.freeze(["poly", "path", "circle", "text"]);
/** Layer kinds drawn only when a view names them: not the board as it is made. */
export const OPTIONAL_LAYER_KINDS = Object.freeze(["courtyard", "mask", "paste"]);
/** Layer kinds drawn over the stack from either side: what goes through the board. */
const OVERLAY_KINDS = new Set(["outline", "via", "ratsnest", "drill"]);
/** A path of width 0 is drawn this many CSS pixels wide at every zoom: a hairline. */
export const PLOT_HAIRLINE_CSS_PX = 1;

const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

/**
 * @typedef {import("../drawing2d/transform.js").DrawingTransform} DrawingTransform
 *
 * @typedef {object} PlotItem One drawn thing, in sheet millimetres (`docs/plot-payload.md`).
 * @property {"poly"|"path"|"circle"|"text"} t
 * @property {readonly (readonly [number, number])[]} [pts] A polygon's vertices or a path's points.
 * @property {readonly [number, number]} [at] A circle's centre.
 * @property {number} [r] A circle's radius.
 * @property {number} [w] A path's or a text's stroke width; a polygon's outline width; a circle's ring width (0 fills it).
 * @property {boolean} [closed] A path that returns to its start.
 * @property {string} [text] A text item's string.
 * @property {readonly (readonly (readonly [number, number])[])[]} [strokes] A text item's stroke polylines.
 * @property {string} [ref] The board reference of what drew it (`#R1`, `#R1.2`).
 * @property {string} [net] The net of a piece of copper.
 * @property {boolean} [pour] A zone's fill: hidden by a view without pours.
 * @property {"through"|"blind"|"micro"} [via]
 * @property {"pad"|"via"|"npth"} [hole]
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
      + `build reads version ${PLOT_SCHEMA_VERSION}. Update cadgen and the app together so the `
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

/**
 * The view that frames the sheet — the board's outline — in a `width` x `height` pane:
 * drawing2d's fit, through the flip. What the file draws past the outline is drawn where it falls.
 *
 * @param {PlotLayout} layout
 * @param {number} width
 * @param {number} height
 * @returns {DrawingTransform}
 */
export function fitPlotTransform(layout, width, height) {
  return fitTransform(layout.modelBounds, width, height);
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
 * A sheet's layers in the order `view` draws them. A view that names no layers draws the board as
 * it is made — every layer but the courtyards, mask and paste, which only a view naming them shows
 * (a board's Assembly and Placement): a snapshot or a card is the board as it is made.
 *
 * @param {PlotSheet} sheet
 * @param {PlotView|null} view
 * @returns {PlotLayer[]}
 */
export function viewedLayers(sheet, view) {
  const chosen = Array.isArray(view?.layers) ? new Set(view.layers) : null;
  const kept = sheet.layers.filter((layer) => (chosen ? chosen.has(layer.id) : !OPTIONAL_LAYER_KINDS.includes(layer.kind)));
  if (view?.side !== "bottom") return kept;
  // From below, the stack reverses — the back layers face the viewer — while what goes through
  // the board (outline, vias, ratsnest, drills) stays over it.
  const stack = kept.filter((layer) => !OVERLAY_KINDS.has(layer.kind)).reverse();
  return [...stack, ...kept.filter((layer) => OVERLAY_KINDS.has(layer.kind))];
}

// ---- paths, in page space, made once per item ----------------------------------
const PATHS = new WeakMap();

function addPolyline(target, points, closed) {
  target.moveTo(points[0][0], points[0][1]);
  for (let index = 1; index < points.length; index += 1) target.lineTo(points[index][0], points[index][1]);
  if (closed) target.closePath();
}

function addItem(target, item) {
  if (item.t === "circle") {
    target.moveTo(item.at[0] + item.r, item.at[1]);
    target.arc(item.at[0], item.at[1], item.r, 0, Math.PI * 2);
  } else if (item.t === "text") {
    for (const stroke of item.strokes) addPolyline(target, stroke, false);
  } else {
    addPolyline(target, item.pts, item.t === "poly" || item.closed === true);
  }
}

/** The item's path, kept with it where the canvas takes a `Path2D`; else drawn into the context afresh. */
function pathOf(ctx, item, PathCtor) {
  if (typeof PathCtor !== "function") {
    ctx.beginPath();
    addItem(ctx, item);
    return null;
  }
  let path = PATHS.get(item);
  if (!path) {
    path = new PathCtor();
    addItem(path, item);
    PATHS.set(item, path);
  }
  return path;
}

function fill(ctx, path) {
  if (path) ctx.fill(path);
  else ctx.fill();
}

function stroke(ctx, path) {
  if (path) ctx.stroke(path);
  else ctx.stroke();
}

/** Draw in page millimetres from here on: the view's transform, its mirror and the pixel ratio. */
function pageSpace(ctx, transform, pixelRatio, mirrorX) {
  const { scale, offsetX, offsetY } = transform;
  const s = scale * pixelRatio;
  if (mirrorX == null) ctx.setTransform(s, 0, 0, s, offsetX * pixelRatio, offsetY * pixelRatio);
  else ctx.setTransform(-s, 0, 0, s, (2 * mirrorX * scale + offsetX) * pixelRatio, offsetY * pixelRatio);
}

function drawLayer(ctx, layer, { hairline, poured, visible, PathCtor }) {
  const color = layerColor(layer.id);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const item of layer.items) {
    if (!poured && item.pour) continue;
    if (visible && !rectsOverlap(visible, item.box)) continue;
    const paint = item.via || item.hole ? itemColor(layer.id, item) : color;
    const path = pathOf(ctx, item, PathCtor);
    if (item.t === "poly") {
      ctx.fillStyle = paint;
      fill(ctx, path);
      if (item.w > 0) {
        ctx.strokeStyle = paint;
        ctx.lineWidth = item.w;
        stroke(ctx, path);
      }
    } else if (item.t === "circle" && item.w === 0) {
      ctx.fillStyle = paint;
      fill(ctx, path);
    } else {
      ctx.strokeStyle = paint;
      ctx.lineWidth = item.w > 0 ? item.w : hairline;
      stroke(ctx, path);
    }
  }
}

/** What the canvas shows, in page millimetres, when the context has a sized canvas; else null. */
function shownRect(ctx, transform, pixelRatio) {
  const canvas = ctx.canvas;
  return canvas && canvas.width > 0 && canvas.height > 0
    ? visiblePageRect(transform, canvas.width / pixelRatio, canvas.height / pixelRatio)
    : null;
}

function checkTransform(transform, who) {
  if (!transform || !(transform.scale > 0)) {
    throw new Error(`${who} needs a transform with a positive scale; received ${describe(transform)}.`);
  }
}

/**
 * Draw one frame of a plot: the sheet's rectangle in its background, then the layers `view`
 * chooses, in its order, each item in KiCad's colours, all in page space under the view. Nothing
 * is clipped to the sheet: an item past the outline is drawn over the surround, as KiCad draws it.
 *
 * The context carries the whole view (page millimetres to device pixels), so the picture is
 * exact at any zoom. A path of width 0 (a ratsnest line, a pour's outline) is a hairline of
 * `PLOT_HAIRLINE_CSS_PX`. Nothing outside the canvas is drawn. The caller paints the surface
 * around the sheet (`clearSurface`), exactly as a drawing's caller does. Without a `view`, a board
 * is every layer but the optional ones, poured, from the top: the board as it is made.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {PlotLayout} layout
 * @param {{ transform: DrawingTransform, pixelRatio?: number, view?: PlotView|null, Path2D?: any }} options
 *   `Path2D` is injectable so this module is exercised in `node --test` with a recording double.
 */
export function drawPlot(ctx, layout, { transform, pixelRatio = 1, view = null, Path2D: PathCtor = globalThis.Path2D }) {
  checkTransform(transform, "drawPlot");
  const visible = shownRect(ctx, transform, pixelRatio);
  const hairline = PLOT_HAIRLINE_CSS_PX / transform.scale;
  const poured = view?.poured !== false;
  ctx.save();
  for (const sheet of layout.sheets) {
    const mirrorX = view?.side === "bottom" ? sheet.x + sheet.width / 2 : null;
    // What the canvas shows, mirrored back into the board's own coordinates.
    const shown = visible && mirrorX != null ? [2 * mirrorX - visible[2], visible[1], 2 * mirrorX - visible[0], visible[3]] : visible;
    if (shown && !rectsOverlap(shown, layout.extent)) continue;
    pageSpace(ctx, transform, pixelRatio, null);
    ctx.fillStyle = sheet.background;
    ctx.fillRect(sheet.x, sheet.y, sheet.width, sheet.height);
    pageSpace(ctx, transform, pixelRatio, mirrorX);
    for (const layer of viewedLayers(sheet, view)) drawLayer(ctx, layer, { hairline, poured, visible: shown, PathCtor });
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

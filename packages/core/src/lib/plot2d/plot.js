/**
 * A `GET /__cad/plot` payload, laid out in one page space and drawn.
 *
 * A plot is a document drawn by its own tool — a KiCad board or schematic, plotted by
 * `kicad-cli` — as one SVG per sheet, in millimetres, y DOWN, each with the background its
 * tool draws it on. This module never parses an SVG: the browser draws it as an image. What
 * it owns is where the sheets go and how one frame is put together, so the viewer's pane and
 * the headless snapshot bundle draw the same picture from the same payload.
 *
 * **Page space** is the payload's own: millimetres, x right, y down. The sheets are stacked
 * top to bottom in payload order (a schematic's root sheet first), each centred on the widest,
 * a gap between them. A board is one sheet.
 *
 * **The view transform is drawing2d's** (`../drawing2d/transform.js`): one uniform scale and a
 * translation, with fit, zoom and pan already written there. drawing2d's model space is y UP;
 * a plot's page is that model space with y negated, so `modelBounds` is the page box flipped
 * and `fitTransform(layout.modelBounds, …)` frames a plot exactly as it frames a drawing. With
 * that flip, a transform maps page to screen as `screen = page * scale + offset` on both axes.
 *
 * **A frame** (`drawPlot`) is each visible sheet's rectangle filled with its background, then
 * the images placed over them in page space. The headless bundle and a library card pass the
 * sheets' SVGs themselves (`sheetImages`); the viewer passes the rasters it keeps of them,
 * which it made with this same function.
 */
import { fitTransform, modelToScreen, screenToModel } from "../drawing2d/transform.js";

/**
 * The payload shape this module understands. Must match
 * `cadgen.kicad.plot.PLOT_SCHEMA_VERSION`.
 */
export const PLOT_SCHEMA_VERSION = 1;

/** The gap between two stacked sheets, as a share of the widest sheet's width. */
export const PLOT_SHEET_GAP = 0.04;

const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

/**
 * @typedef {import("../drawing2d/transform.js").DrawingTransform} DrawingTransform
 *
 * @typedef {object} PlotSheet
 * @property {number} index Its place in the payload.
 * @property {string} name
 * @property {string} svg The tool's SVG, as it drew it.
 * @property {number} width Millimetres.
 * @property {number} height Millimetres.
 * @property {string} background The colour the tool draws this sheet on, `#rrggbb`.
 * @property {number} x Page position of the sheet's top-left corner, millimetres.
 * @property {number} y
 *
 * @typedef {object} PlotLayout
 * @property {number} schemaVersion
 * @property {string} kind What drew it: `"board"`, `"schematic"`, … Words only, never drawing.
 * @property {number|null} unrouted A board's unconnected pairs (drawn as its ratsnest), else null.
 * @property {readonly PlotSheet[]} sheets
 * @property {readonly [number, number, number, number]} bounds The page box, `[minX, minY, maxX, maxY]`, y down.
 * @property {readonly [number, number, number, number]} modelBounds The same box in drawing2d's model space, y up.
 *
 * @typedef {object} PlacedImage
 * @property {CanvasImageSource|null} image
 * @property {number} x Page millimetres.
 * @property {number} y
 * @property {number} width
 * @property {number} height
 */

function describe(value) {
  const text = JSON.stringify(value);
  return text === undefined ? String(value) : text;
}

function positive(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/**
 * A payload, validated and laid out.
 *
 * Throws — naming the offender — on a payload this build does not understand. A sheet that
 * silently went missing would be a plausible picture with part of the document gone.
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
  if (!Array.isArray(sheets) || sheets.length === 0) {
    throw new Error(`A plot payload's \`sheets\` is a non-empty array; received ${describe(sheets)}.`);
  }
  sheets.forEach((sheet, index) => {
    const where = `sheets[${index}]`;
    if (!sheet || typeof sheet !== "object") {
      throw new Error(`${where} is not a sheet object: ${describe(sheet)}.`);
    }
    if (typeof sheet.svg !== "string" || !sheet.svg.trim()) {
      throw new Error(`${where} (${describe(sheet.name)}) carries no SVG.`);
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
  });
  const widest = Math.max(...sheets.map((sheet) => sheet.width));
  const gap = widest * PLOT_SHEET_GAP;
  let top = 0;
  const placed = sheets.map((sheet, index) => {
    const entry = {
      index,
      name: String(sheet.name ?? ""),
      svg: sheet.svg,
      width: sheet.width,
      height: sheet.height,
      background: sheet.background,
      x: (widest - sheet.width) / 2,
      y: top
    };
    top += sheet.height + gap;
    return Object.freeze(entry);
  });
  const height = top - gap;
  return Object.freeze({
    schemaVersion: payload.schemaVersion,
    kind: String(payload.kind ?? ""),
    unrouted: Number.isInteger(payload.unrouted) ? payload.unrouted : null,
    sheets: Object.freeze(placed),
    bounds: Object.freeze([0, 0, widest, height]),
    modelBounds: Object.freeze([0, -height, widest, 0])
  });
}

/**
 * The view that frames the whole plot in a `width` x `height` pane: drawing2d's fit, through
 * the flip.
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
 * Each sheet's SVG image, placed on its sheet: what the snapshot and a library card draw.
 *
 * @param {PlotLayout} layout
 * @param {readonly (CanvasImageSource|null)[]} images One per sheet, in payload order.
 * @returns {PlacedImage[]}
 */
export function sheetImages(layout, images) {
  return layout.sheets.map((sheet) => ({
    image: images[sheet.index] ?? null,
    x: sheet.x,
    y: sheet.y,
    width: sheet.width,
    height: sheet.height
  }));
}

/**
 * Draw one frame of a plot: each visible sheet's rectangle in its background, then `images`
 * over them, all in page space under the view.
 *
 * The context carries the whole view (page millimetres to device pixels), so a sheet's
 * rectangle is exact at any zoom and an SVG image is drawn by the browser at the scale it
 * lands at, which is what keeps a plot crisp. Nothing outside the canvas is drawn: an image
 * that misses it costs no rasterisation. The caller paints the surface around the sheets
 * (`clearSurface`), exactly as a drawing's caller does.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {PlotLayout} layout
 * @param {{ transform: DrawingTransform, pixelRatio?: number, images?: readonly PlacedImage[] }} options
 */
export function drawPlot(ctx, layout, { transform, pixelRatio = 1, images = [] }) {
  if (!transform || !(transform.scale > 0)) {
    throw new Error(`drawPlot needs a transform with a positive scale; received ${describe(transform)}.`);
  }
  const { scale, offsetX, offsetY } = transform;
  const canvas = ctx.canvas;
  // What the canvas shows, in page millimetres; unknown for a context without a canvas.
  const visible = canvas && canvas.width > 0 && canvas.height > 0
    ? visiblePageRect(transform, canvas.width / pixelRatio, canvas.height / pixelRatio)
    : null;
  const shows = (x, y, width, height) => !visible || rectsOverlap(visible, [x, y, x + width, y + height]);
  ctx.save();
  ctx.setTransform(scale * pixelRatio, 0, 0, scale * pixelRatio, offsetX * pixelRatio, offsetY * pixelRatio);
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

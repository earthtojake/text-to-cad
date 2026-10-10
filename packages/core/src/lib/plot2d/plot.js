/**
 * A `GET /__cad/plot` payload, laid out in one page space and drawn.
 *
 * A plot is a document drawn by its own tool — a KiCad board or schematic, plotted by
 * `kicad-cli` — in millimetres, y DOWN, each sheet with the background its tool draws it on. A
 * schematic or harness sheet is one SVG; a board's sheet is its LAYERS, back to front (bottom
 * fabrication and silkscreen, bottom copper, inner copper, top copper, top silkscreen and
 * fabrication, the outline, a draft's ratsnest, the drill holes), each an SVG of the whole page,
 * a copper layer with an `unpoured` SVG beside it when the board has pours. This module never
 * parses an SVG: the browser draws each as an image. What it owns is where the sheets go and
 * how one frame is put together, so the viewer's pane and the headless snapshot bundle draw the
 * same picture from the same payload.
 *
 * **Page space** is the payload's own: millimetres, x right, y down. The sheets are stacked
 * top to bottom in payload order (a schematic's root sheet first), each centred on the widest,
 * a gap between them. A board is one sheet; its index (`payload.board`, sheet millimetres) is
 * the layout's `board`.
 *
 * **The view transform is drawing2d's** (`../drawing2d/transform.js`): one uniform scale and a
 * translation, with fit, zoom and pan already written there. drawing2d's model space is y UP;
 * a plot's page is that model space with y negated, so `modelBounds` is the page box flipped
 * and `fitTransform(layout.modelBounds, …)` frames a plot exactly as it frames a drawing. With
 * that flip, a transform maps page to screen as `screen = page * scale + offset` on both axes.
 *
 * **A frame** (`drawPlot`) is each visible sheet's rectangle filled with its background, then
 * the images placed over them in page space. The headless bundle and a library card pass the
 * sheets' own SVGs (`sheetImages`): every layer, poured, seen from the top — the picture KiCad
 * plots of the whole board. A board's images carry their layer, so a `view` can draw some of
 * them, the copper without its pours, or the board from below (each layer mirrored about the
 * sheet's vertical centre line, the stack drawn in reverse). The viewer passes rasters it keeps
 * of a view, made with this same function, which carry no layer and are drawn as they are.
 */
import { fitTransform, modelToScreen, screenToModel } from "../drawing2d/transform.js";

/**
 * The payload shape this module understands. Must match
 * `cadgen.kicad.plot.PLOT_SCHEMA_VERSION`.
 */
export const PLOT_SCHEMA_VERSION = 2;

/** The gap between two stacked sheets, as a share of the widest sheet's width. */
export const PLOT_SHEET_GAP = 0.04;

/** A board layer's side: what faces the top, the bottom, or neither (through the board). */
export const PLOT_LAYER_SIDES = Object.freeze(["front", "back", "both"]);

/** Layer kinds drawn over the stack from either side: what goes through the board. */
const OVERLAY_KINDS = new Set(["outline", "ratsnest", "drill"]);

const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

/**
 * @typedef {import("../drawing2d/transform.js").DrawingTransform} DrawingTransform
 *
 * @typedef {object} PlotLayer
 * @property {string} id KiCad's layer (`"F.Cu"`), or `"ratsnest"`, `"drills"`.
 * @property {string} kind `"courtyard"`, `"fab"`, `"silk"`, `"copper"`, `"outline"`, `"ratsnest"`, `"drill"`.
 * @property {"front"|"back"|"both"} side
 * @property {string} svg The layer as KiCad plotted it, poured.
 * @property {string|null} unpoured A copper layer with its pours' fills removed, when it has any.
 *
 * @typedef {object} PlotSheet
 * @property {number} index Its place in the payload.
 * @property {string} name
 * @property {string|null} svg The tool's SVG of a schematic or harness sheet; null for a board's.
 * @property {readonly PlotLayer[]|null} layers A board sheet's layers, back to front; else null.
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
 * @property {object|null} board A board's index (`payload.board`), sheet millimetres; else null.
 * @property {readonly [number, number, number, number]} bounds The page box, `[minX, minY, maxX, maxY]`, y down.
 * @property {readonly [number, number, number, number]} modelBounds The same box in drawing2d's model space, y up.
 *
 * @typedef {object} PlotLayerImages One board layer's pictures, decoded.
 * @property {string} id
 * @property {CanvasImageSource} poured
 * @property {CanvasImageSource|null} unpoured
 *
 * @typedef {object} PlacedImage
 * @property {CanvasImageSource|null} image
 * @property {number} x Page millimetres.
 * @property {number} y
 * @property {number} width
 * @property {number} height
 * @property {number} [sheet] The sheet a board layer's image belongs to.
 * @property {string} [layer] A board layer's id: a `view` chooses and orders these.
 * @property {string} [kind] That layer's kind.
 * @property {CanvasImageSource|null} [unpoured] That layer's picture without its pours.
 *
 * @typedef {object} PlotView What of a board to draw, and from which side.
 * @property {readonly string[]|null} [layers] The layer ids to draw (in the sheet's order); null or omitted for all.
 * @property {boolean} [poured] False draws copper from its `unpoured` picture. Default true.
 * @property {"top"|"bottom"} [side] Bottom: the sheet mirrored left-right, the stack reversed. Default top.
 */

function describe(value) {
  const text = JSON.stringify(value);
  return text === undefined ? String(value) : text;
}

function positive(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function svgText(value) {
  return typeof value === "string" && value.trim() !== "";
}

function layoutLayers(sheet, where) {
  if (!Array.isArray(sheet.layers) || sheet.layers.length === 0) {
    throw new Error(`${where} (${describe(sheet.name)}) carries no SVG and no layers.`);
  }
  return Object.freeze(sheet.layers.map((layer, index) => {
    const at = `${where}.layers[${index}]`;
    if (!layer || typeof layer !== "object" || typeof layer.id !== "string" || !layer.id) {
      throw new Error(`${at} is not a layer with an id: ${describe(layer)}.`);
    }
    if (!svgText(layer.svg)) throw new Error(`${at} (${layer.id}) carries no SVG.`);
    if (!PLOT_LAYER_SIDES.includes(layer.side)) {
      throw new Error(`${at} (${layer.id}) has side ${describe(layer.side)}; a layer is ${PLOT_LAYER_SIDES.join(", ")}.`);
    }
    if (layer.unpoured !== undefined && layer.unpoured !== null && !svgText(layer.unpoured)) {
      throw new Error(`${at} (${layer.id}) has an unpoured picture that is no SVG.`);
    }
    return Object.freeze({
      id: layer.id,
      kind: String(layer.kind ?? ""),
      side: layer.side,
      svg: layer.svg,
      unpoured: svgText(layer.unpoured) ? layer.unpoured : null
    });
  }));
}

/**
 * A payload, validated and laid out.
 *
 * Throws — naming the offender — on a payload this build does not understand. A sheet or a
 * layer that silently went missing would be a plausible picture with part of the document gone.
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
  const layered = sheets.map((sheet, index) => {
    const where = `sheets[${index}]`;
    if (!sheet || typeof sheet !== "object") {
      throw new Error(`${where} is not a sheet object: ${describe(sheet)}.`);
    }
    const layers = svgText(sheet.svg) ? null : layoutLayers(sheet, where);
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
    return layers;
  });
  const widest = Math.max(...sheets.map((sheet) => sheet.width));
  const gap = widest * PLOT_SHEET_GAP;
  let top = 0;
  const placed = sheets.map((sheet, index) => {
    const entry = {
      index,
      name: String(sheet.name ?? ""),
      svg: layered[index] ? null : sheet.svg,
      layers: layered[index],
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
  const board = payload.board && typeof payload.board === "object" && !Array.isArray(payload.board) ? payload.board : null;
  return Object.freeze({
    schemaVersion: payload.schemaVersion,
    kind: String(payload.kind ?? ""),
    unrouted: Number.isInteger(payload.unrouted) ? payload.unrouted : null,
    sheets: Object.freeze(placed),
    board,
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
 * Each sheet's layers with their decoded pictures: per sheet, per layer, `{ id, kind, side,
 * poured, unpoured }`. A schematic or harness sheet is one layer of kind `"sheet"`, id null.
 *
 * @param {PlotLayout} layout
 * @param {readonly any[]} images From `loadSheetImages`: per sheet, an image or `PlotLayerImages[]`.
 */
export function layerImages(layout, images) {
  return layout.sheets.map((sheet) => {
    const decoded = images[sheet.index] ?? null;
    if (!sheet.layers) {
      return [{ id: null, kind: "sheet", side: "both", poured: Array.isArray(decoded) ? null : decoded, unpoured: null }];
    }
    return sheet.layers.map((layer, index) => {
      const pictures = Array.isArray(decoded) ? decoded[index] ?? null : null;
      return { id: layer.id, kind: layer.kind, side: layer.side, poured: pictures?.poured ?? null, unpoured: pictures?.unpoured ?? null };
    });
  });
}

/**
 * Each sheet's images, placed on its sheet in drawing order: what the snapshot and a library card
 * draw. A board sheet's are one per layer, back to front, each carrying its layer (and its
 * unpoured picture) for a `view` to choose from.
 *
 * @param {PlotLayout} layout
 * @param {readonly any[]} images Per sheet, in payload order: an image for a schematic or harness
 *   sheet, `PlotLayerImages[]` for a board's (as `loadSheetImages` decodes them).
 * @returns {PlacedImage[]}
 */
export function sheetImages(layout, images) {
  return layout.sheets.flatMap((sheet) => {
    const place = { x: sheet.x, y: sheet.y, width: sheet.width, height: sheet.height };
    if (!sheet.layers) {
      const decoded = images[sheet.index] ?? null;
      return [{ image: Array.isArray(decoded) ? null : decoded, ...place }];
    }
    return layerImages(layout, images)[sheet.index].map(({ id, kind, poured, unpoured }) => ({
      image: poured, unpoured, sheet: sheet.index, layer: id, kind, ...place
    }));
  });
}

/**
 * A sheet's layer images in the order `view` draws them, each with the picture it draws. A view
 * that names no layers draws them all but the courtyards, which only a view naming them shows (a
 * board's Assembly and Placement): a snapshot or a card is the board as it is made.
 */
function viewed(entries, view) {
  const chosen = Array.isArray(view?.layers) ? new Set(view.layers) : null;
  const poured = view?.poured !== false;
  const kept = entries
    .filter((entry) => (chosen ? chosen.has(entry.layer) : entry.kind !== "courtyard"))
    .map((entry) => ({ ...entry, image: poured || !entry.unpoured ? entry.image : entry.unpoured }));
  if (view?.side !== "bottom") return kept;
  // From below, the stack reverses — the back layers face the viewer — while what goes through
  // the board (outline, ratsnest, drills) stays over it.
  const stack = kept.filter((entry) => !OVERLAY_KINDS.has(entry.kind)).reverse();
  return [...stack, ...kept.filter((entry) => OVERLAY_KINDS.has(entry.kind))];
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
 * A board layer's image (one `sheetImages` placed) is drawn as `view` says: only the layers it
 * names, the copper poured or not, from the top or — mirrored about its sheet's vertical centre
 * line, the stack reversed — from below. Any other image is drawn as it is. Without a `view`, a
 * board is every layer, poured, from the top: KiCad's picture of it.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {PlotLayout} layout
 * @param {{ transform: DrawingTransform, pixelRatio?: number, images?: readonly PlacedImage[], view?: PlotView }} options
 */
export function drawPlot(ctx, layout, { transform, pixelRatio = 1, images = [], view = null }) {
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
  // Each run of one sheet's layer images, put in the order the view draws them.
  const drawn = [];
  for (let index = 0; index < images.length;) {
    const entry = images[index];
    if (typeof entry?.layer !== "string") {
      drawn.push(entry);
      index += 1;
      continue;
    }
    let end = index;
    while (end < images.length && typeof images[end]?.layer === "string" && images[end].sheet === entry.sheet) end += 1;
    const mirrored = view?.side === "bottom";
    for (const layer of viewed(images.slice(index, end), view)) drawn.push({ ...layer, mirrored });
    index = end;
  }
  ctx.save();
  ctx.setTransform(scale * pixelRatio, 0, 0, scale * pixelRatio, offsetX * pixelRatio, offsetY * pixelRatio);
  for (const sheet of layout.sheets) {
    if (!shows(sheet.x, sheet.y, sheet.width, sheet.height)) continue;
    ctx.fillStyle = sheet.background;
    ctx.fillRect(sheet.x, sheet.y, sheet.width, sheet.height);
  }
  for (const { image, x, y, width, height, mirrored, sheet } of drawn) {
    if (!image || !(width > 0) || !(height > 0) || !shows(x, y, width, height)) continue;
    if (!mirrored) {
      ctx.drawImage(image, x, y, width, height);
      continue;
    }
    const at = layout.sheets[sheet];
    ctx.save();
    ctx.translate(2 * at.x + at.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(image, x, y, width, height);
    ctx.restore();
  }
  ctx.restore();
}

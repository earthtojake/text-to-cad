/**
 * A `GET /__cad/drawing` payload, batched once and then drawn many times.
 *
 * The backend flattens a `.dxf` into five primitive shapes (`point`, `lines`,
 * `path`, `filled-paths`, `filled-polygon`) and its text (`text`) in DXF
 * modelspace coordinates, y up. This module turns the shapes into `Path2D`
 * objects ONCE, and then paints them under a view transform on every frame.
 * Nothing here parses DXF, knows what a layer means, or touches the DOM beyond
 * the 2D context and the `Path2D` constructor it is handed — which is what lets
 * the viewer and the headless snapshot bundle share it.
 *
 * Text is set with `fillText`, where the server placed it. A `text` primitive
 * carries its string, font, cap height, the advance width the server measured
 * in its own copy of the font, and the transform from the string's space
 * (baseline-left at the origin, y up) to the drawing. The string is set at that
 * cap height in the face the page has under the font's name, and stretched
 * along its baseline to that width: a face that differs from the server's then
 * keeps the server's layout — a centred or right-aligned note stays where the
 * drawing put it, and a title-block field stays inside its box.
 *
 * Two rules the payload only implies:
 *
 * - **`color: null` is the default pen**, ACI 7, "whatever contrasts with the
 *   background". It is resolved at DRAW time against the theme's foreground,
 *   not at prepare time, so one prepared drawing serves the light and the dark
 *   theme and a theme flip costs a repaint rather than a re-fetch.
 * - **Lineweights are not displayed.** Strokes are hairlines at a constant
 *   screen width, as AutoCAD draws with LWDISPLAY off. Model-space widths would
 *   make a zoomed-out drawing a solid block of ink.
 *
 * Batching is per colour for strokes and per colour, per primitive for fills.
 * Strokes of one colour can share a single `Path2D` because stroking is
 * order-independent and overlap is harmless. Fills cannot: `filled-paths` is
 * filled EVEN-ODD so its inner rings punch holes, and merging two overlapping
 * regions into one path would turn their overlap into a hole as well. So the
 * fills of one colour are grouped to share a `fillStyle`, and each is still
 * filled on its own.
 */

/**
 * The payload shape this module understands. Must match
 * `cadgen.drawing_payload.DRAWING_PAYLOAD_SCHEMA_VERSION`.
 */
export const DRAWING_SCHEMA_VERSION = 2;

/** Stroke width in CSS pixels, at every zoom. */
export const DRAWING_HAIRLINE_CSS_PX = 1.25;
/** Radius of a POINT entity's mark, in CSS pixels, at every zoom. */
export const DRAWING_POINT_RADIUS_CSS_PX = 1.6;

/**
 * The size every string's font is SET at. A string's real size is in its
 * transform: setting each one at its own size would hand the canvas fonts a
 * fraction of a pixel tall, which it is free to round.
 */
const TEXT_SET_PX = 100;
/** A face's cap height per em where the canvas cannot measure one (no `actualBoundingBoxAscent`). */
const FALLBACK_CAP_PER_EM = 0.7;
/** CSS generic families, which a font shorthand names bare: quoted, they would name a face. */
const GENERIC_FAMILIES = new Set(["serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"]);

/**
 * @typedef {import("./transform.js").DrawingTransform} DrawingTransform
 * @typedef {import("./transform.js").DrawingBounds} DrawingBounds
 *
 * @typedef {object} PreparedText
 * @property {string} text
 * @property {string} font The CSS font it is set in, at `TEXT_SET_PX`.
 * @property {number} height Cap height, in the string's own units.
 * @property {number} width Advance width the server measured, in the same units.
 * @property {readonly number[]} transform `[a, b, c, d, e, f]`: the string's space to the drawing's.
 * @property {DrawingBounds} box A drawing-space box around the string, for skipping it off screen.
 *
 * @typedef {object} PreparedDrawing
 * @property {number} schemaVersion
 * @property {object} units
 * @property {DrawingBounds|null} bounds
 * @property {readonly object[]} layers
 * @property {readonly { color: string|null, paths: readonly any[] }[]} fills
 * @property {readonly { color: string|null, items: readonly PreparedText[] }[]} texts
 * @property {readonly { color: string|null, path: any }[]} strokes
 * @property {readonly { color: string|null, coordinates: readonly number[] }[]} points
 * @property {number} primitiveCount
 */

function isArray(value) {
  return Array.isArray(value);
}

function describe(value) {
  const text = JSON.stringify(value);
  return text === undefined ? String(value) : text;
}

/**
 * A `Path2D` constructor: the injected one, the ambient one, or a loud
 * refusal. Injectable so this module is exercised in `node --test` with a
 * recording double and never drags a DOM into core's unit tests.
 */
function resolvePath2D(injected) {
  const candidate = injected || (typeof globalThis !== "undefined" ? globalThis.Path2D : undefined);
  if (typeof candidate !== "function") {
    throw new Error(
      "prepareDrawing needs a Path2D constructor: this runtime has no global Path2D, so pass "
      + "one as `prepareDrawing(payload, { Path2D })`."
    );
  }
  return candidate;
}

/** One `path` command list appended to an open Path2D. */
function appendPath(path, commands, context) {
  for (const command of commands) {
    const letter = command[0];
    if (letter === "M") {
      path.moveTo(command[1], command[2]);
    } else if (letter === "L") {
      path.lineTo(command[1], command[2]);
    } else if (letter === "Q") {
      path.quadraticCurveTo(command[1], command[2], command[3], command[4]);
    } else if (letter === "C") {
      path.bezierCurveTo(command[1], command[2], command[3], command[4], command[5], command[6]);
    } else if (letter === "Z") {
      path.closePath();
    } else {
      throw new Error(
        `${context}: unknown path command ${describe(letter)}. A cadgen drawing payload at `
        + `schemaVersion ${DRAWING_SCHEMA_VERSION} uses only M, L, Q, C and Z.`
      );
    }
  }
}

/** An explicitly closed ring appended to an open Path2D. */
function appendPolygon(path, vertices) {
  vertices.forEach((vertex, index) => {
    if (index === 0) {
      path.moveTo(vertex[0], vertex[1]);
    } else {
      path.lineTo(vertex[0], vertex[1]);
    }
  });
  if (vertices.length) {
    path.closePath();
  }
}

/** A `fonts` row as the CSS font a string in it is set in. */
function cssFont(row, where) {
  const family = typeof row?.family === "string" ? row.family.trim() : "";
  const weight = Number(row?.weight);
  if (!family || !Number.isFinite(weight)) {
    throw new Error(`${where}: a font is { family, weight, italic }; received ${describe(row)}.`);
  }
  const named = GENERIC_FAMILIES.has(family.toLowerCase()) ? family : `"${family.replace(/["\\]/g, "")}"`;
  const fallback = family.toLowerCase() === "sans-serif" ? "" : ", sans-serif";
  return `${row.italic ? "italic " : ""}${Math.round(weight)} ${TEXT_SET_PX}px ${named}${fallback}`;
}

/** A text primitive, checked, as the item `drawDrawing` sets. */
function prepareText(primitive, fonts, where) {
  const font = fonts[primitive.font];
  if (font === undefined) {
    throw new Error(`${where}: text is set in font ${describe(primitive.font)}, which the payload's \`fonts\` does not list.`);
  }
  const transform = primitive.transform;
  if (!isArray(transform) || transform.length !== 6 || !transform.every(Number.isFinite)) {
    throw new Error(`${where}: a text transform is [a, b, c, d, e, f]; received ${describe(transform)}.`);
  }
  const height = primitive.height;
  const width = primitive.width;
  if (!(height > 0) || !(width >= 0) || typeof primitive.text !== "string") {
    throw new Error(
      `${where}: text needs a string, a positive height and a width; received ${describe({ text: primitive.text, height, width })}.`
    );
  }
  // The string's box with room for descenders and accents, in the drawing's space: only ever used
  // to skip a string that is nowhere near the screen, so generous beats exact.
  const [a, b, c, d, e, f] = transform;
  const xs = [];
  const ys = [];
  for (const [x, y] of [[0, -0.5 * height], [width, -0.5 * height], [width, 1.5 * height], [0, 1.5 * height]]) {
    xs.push(a * x + c * y + e);
    ys.push(b * x + d * y + f);
  }
  return {
    text: primitive.text,
    font,
    height,
    width,
    transform,
    box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)],
    // Set at first paint, when there is a canvas to measure the string with (`textFit`).
    unit: 0,
    stretch: 0
  };
}

/**
 * Colour-keyed grouping. `null` — the default pen — is a KEY of its own, kept
 * distinct from every hex string: it is resolved at draw time and must not be
 * folded into whatever the theme's foreground happens to be right now. A Map
 * takes `null` as a key directly, so there is no sentinel string that a real
 * colour could ever collide with.
 */
function group(map, color) {
  const key = color === null || color === undefined ? null : String(color);
  let entry = map.get(key);
  if (!entry) {
    entry = { color: key, items: [] };
    map.set(key, entry);
  }
  return entry;
}

/**
 * A payload, validated and batched into drawable paths.
 *
 * Throws — loudly, naming the offender — on a payload this build does not
 * understand. A drawing that silently drops the primitives it did not
 * recognise is worse than one that refuses to open: the person sees a plausible
 * picture with parts missing and no reason to doubt it.
 *
 * @param {object} payload
 * @param {{ Path2D?: any }} [options]
 * @returns {PreparedDrawing}
 */
export function prepareDrawing(payload, { Path2D: injectedPath2D } = {}) {
  if (!payload || typeof payload !== "object" || isArray(payload)) {
    throw new Error(`prepareDrawing needs a drawing payload object; received ${describe(payload)}.`);
  }
  if (payload.schemaVersion !== DRAWING_SCHEMA_VERSION) {
    throw new Error(
      `This drawing was rendered at payload schemaVersion ${describe(payload.schemaVersion)}, but `
      + `this build reads version ${DRAWING_SCHEMA_VERSION}. Update cadgen and the app together so `
      + "the server and the viewer agree on the payload."
    );
  }
  const primitives = payload.primitives;
  if (!isArray(primitives)) {
    throw new Error(`A drawing payload's \`primitives\` must be an array; received ${describe(primitives)}.`);
  }
  const bounds = payload.bounds === null || payload.bounds === undefined ? null : payload.bounds;
  if (bounds !== null && (!isArray(bounds) || bounds.length !== 4)) {
    throw new Error(
      `A drawing payload's \`bounds\` is [minX, minY, maxX, maxY] or null; received ${describe(bounds)}.`
    );
  }

  if (!isArray(payload.fonts)) {
    throw new Error(`A drawing payload's \`fonts\` must be an array; received ${describe(payload.fonts)}.`);
  }
  const fonts = payload.fonts.map((row, index) => cssFont(row, `fonts[${index}]`));

  const PathCtor = resolvePath2D(injectedPath2D);
  const strokeGroups = new Map();
  const fillGroups = new Map();
  const textGroups = new Map();
  const pointGroups = new Map();

  primitives.forEach((primitive, index) => {
    const where = `primitives[${index}]`;
    const type = primitive?.type;
    const geometry = primitive?.geometry;
    if (type === "lines") {
      const entry = group(strokeGroups, primitive.color);
      if (!entry.path) {
        entry.path = new PathCtor();
      }
      for (const line of geometry) {
        entry.path.moveTo(line[0], line[1]);
        entry.path.lineTo(line[2], line[3]);
      }
    } else if (type === "path") {
      const entry = group(strokeGroups, primitive.color);
      if (!entry.path) {
        entry.path = new PathCtor();
      }
      appendPath(entry.path, geometry, where);
    } else if (type === "filled-paths") {
      const path = new PathCtor();
      for (const commands of geometry) {
        appendPath(path, commands, where);
      }
      group(fillGroups, primitive.color).items.push(path);
    } else if (type === "filled-polygon") {
      const path = new PathCtor();
      appendPolygon(path, geometry);
      group(fillGroups, primitive.color).items.push(path);
    } else if (type === "point") {
      const entry = group(pointGroups, primitive.color);
      entry.items.push(geometry[0], geometry[1]);
    } else if (type === "text") {
      group(textGroups, primitive.color).items.push(prepareText(primitive, fonts, where));
    } else {
      throw new Error(
        `${where}: unknown drawing primitive type ${describe(type)}. A cadgen drawing payload at `
        + `schemaVersion ${DRAWING_SCHEMA_VERSION} carries only "point", "lines", "path", `
        + '"filled-paths", "filled-polygon" and "text".'
      );
    }
  });

  return {
    schemaVersion: payload.schemaVersion,
    units: payload.units || null,
    bounds,
    layers: isArray(payload.layers) ? payload.layers : [],
    fills: [...fillGroups.values()].map((entry) => ({ color: entry.color, paths: entry.items })),
    texts: [...textGroups.values()].map((entry) => ({ color: entry.color, items: entry.items })),
    strokes: [...strokeGroups.values()].map((entry) => ({ color: entry.color, path: entry.path })),
    points: [...pointGroups.values()].map((entry) => ({ color: entry.color, coordinates: entry.items })),
    primitiveCount: primitives.length
  };
}

/**
 * Paint the pane's background, in CSS pixels, on a DPR-scaled backing store.
 *
 * Separate from `drawDrawing` because a snapshot needs the background in the
 * PNG while an on-screen canvas may prefer to let the pane's own background
 * show through — and because "clear" and "draw" failing together is a worse
 * bug than either alone.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{ width: number, height: number, pixelRatio?: number, background?: string|null }} options
 */
export function clearSurface(ctx, { width, height, pixelRatio = 1, background = null }) {
  ctx.save();
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  if (background) {
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, width, height);
  } else {
    ctx.clearRect(0, 0, width, height);
  }
  ctx.restore();
}

/** The drawing-space box the canvas shows, or null where the context has no canvas to say. */
function visibleBox(ctx, { scale, offsetX, offsetY }, pixelRatio) {
  const canvas = ctx.canvas;
  if (!(canvas?.width > 0) || !(canvas?.height > 0)) {
    return null;
  }
  const width = canvas.width / pixelRatio;
  const height = canvas.height / pixelRatio;
  return [-offsetX / scale, (offsetY - height) / scale, (width - offsetX) / scale, offsetY / scale];
}

/** A face's cap height in CSS pixels at `TEXT_SET_PX`, per CSS font, as the canvas measures it. */
const capHeights = new Map();
function capHeightPx(ctx, font) {
  let cap = capHeights.get(font);
  if (cap === undefined) {
    const measured = typeof ctx.measureText === "function" ? ctx.measureText("H").actualBoundingBoxAscent : 0;
    cap = measured > 0 ? measured : TEXT_SET_PX * FALLBACK_CAP_PER_EM;
    capHeights.set(font, cap);
  }
  return cap;
}

/**
 * How one string is set, measured once (`ctx.font` must already be its font): `unit`, the string's
 * own units per CSS pixel of the set font, so its cap height is its `height`; and `stretch`, the
 * horizontal factor that makes this face's advance the server's `width`.
 */
function textFit(ctx, item) {
  item.unit = item.height / capHeightPx(ctx, item.font);
  const natural = typeof ctx.measureText === "function" ? ctx.measureText(item.text).width * item.unit : 0;
  item.stretch = natural > 0 && item.width > 0 ? item.width / natural : 1;
}

/**
 * Every string, each under the device transform composed with its own: its space to the drawing
 * (`transform`), and the set font's pixels (y DOWN) to its space (y UP), stretched to its width.
 * A string wholly off the canvas is skipped; it costs a `fillText` per frame for nothing.
 */
function drawTexts(ctx, groups, { device, foreground, visible }) {
  const [scaleX, , , scaleY, deviceX, deviceY] = device;
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  let font = "";
  for (const { color, items } of groups) {
    ctx.fillStyle = color || foreground;
    for (const item of items) {
      const box = item.box;
      if (visible && (box[0] > visible[2] || box[2] < visible[0] || box[1] > visible[3] || box[3] < visible[1])) {
        continue;
      }
      if (item.font !== font) {
        font = item.font;
        ctx.font = font;
      }
      if (!item.unit) {
        textFit(ctx, item);
      }
      const [a, b, c, d, e, f] = item.transform;
      const across = item.unit * item.stretch;
      const down = -item.unit;
      ctx.setTransform(
        scaleX * a * across, scaleY * b * across,
        scaleX * c * down, scaleY * d * down,
        scaleX * e + deviceX, scaleY * f + deviceY
      );
      ctx.fillText(item.text, 0, 0);
    }
  }
}

/**
 * Draw a prepared drawing under a view transform.
 *
 * Paths are in MODEL coordinates and the context carries the whole view, which
 * is what keeps a hairline a hairline: one `lineWidth` in model units,
 * recomputed per frame as `1.25 / scale`, is 1.25 CSS pixels wide at any zoom,
 * and no geometry is rebuilt when the view moves.
 *
 * Fills go down first, then text, then strokes. Within a DXF a filled region
 * is nearly always a hatch or a solid BEHIND the line-work and lettering on
 * it, and painting per colour means the primitive order cannot be honoured
 * exactly anyway; fills first is the one ordering that never hides an edge or
 * a word, and text before strokes keeps the order text had as filled glyphs.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {PreparedDrawing} drawable
 * @param {{ transform: DrawingTransform, foreground: string, pixelRatio?: number }} options
 */
export function drawDrawing(ctx, drawable, { transform, foreground, pixelRatio = 1 }) {
  if (!transform || !(transform.scale > 0)) {
    throw new Error(`drawDrawing needs a transform with a positive scale; received ${describe(transform)}.`);
  }
  if (typeof foreground !== "string" || !foreground) {
    throw new Error(
      "drawDrawing needs the theme's foreground colour: a drawing's default pen (`color: null`) "
      + `has no colour of its own to fall back on. Received ${describe(foreground)}.`
    );
  }
  const { scale, offsetX, offsetY } = transform;
  ctx.save();
  // The y flip is the `-scale` in the vertical term; DPR multiplies everything,
  // so model units land on device pixels in one step.
  const device = [scale * pixelRatio, 0, 0, -scale * pixelRatio, offsetX * pixelRatio, offsetY * pixelRatio];
  ctx.setTransform(...device);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  for (const { color, paths } of drawable.fills) {
    ctx.fillStyle = color || foreground;
    for (const path of paths) {
      ctx.fill(path, "evenodd");
    }
  }

  if (drawable.texts.length) {
    drawTexts(ctx, drawable.texts, { device, foreground, visible: visibleBox(ctx, transform, pixelRatio) });
    ctx.setTransform(...device);
  }

  ctx.lineWidth = DRAWING_HAIRLINE_CSS_PX / scale;
  for (const { color, path } of drawable.strokes) {
    ctx.strokeStyle = color || foreground;
    ctx.stroke(path);
  }

  const radius = DRAWING_POINT_RADIUS_CSS_PX / scale;
  for (const { color, coordinates } of drawable.points) {
    ctx.fillStyle = color || foreground;
    for (let index = 0; index < coordinates.length; index += 2) {
      ctx.beginPath();
      ctx.arc(coordinates[index], coordinates[index + 1], radius, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.restore();
}

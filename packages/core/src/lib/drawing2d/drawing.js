/**
 * A `GET /__cad/drawing` payload, batched once and then drawn many times.
 *
 * The backend flattens a `.dxf` into five primitive shapes (`point`, `lines`,
 * `path`, `filled-paths`, `filled-polygon`) in DXF modelspace coordinates, y
 * up. This module turns that list into `Path2D` objects ONCE, and then paints
 * them under a view transform on every frame. Nothing here parses DXF, knows
 * what a layer means, or touches the DOM beyond the 2D context and the
 * `Path2D` constructor it is handed — which is what lets the viewer and the
 * headless snapshot bundle share it.
 *
 * Two rules the payload only implies:
 *
 * - **`color: null` is the default pen**, ACI 7, "whatever contrasts with the
 *   background". It is resolved at DRAW time against the theme's foreground,
 *   not at prepare time, so one prepared drawing serves the light and the dark
 *   theme and a theme flip costs a repaint rather than a re-fetch.
 * - **Lineweights are not displayed.** Strokes are hairlines at a constant
 *   screen width, as AutoCAD draws with LWDISPLAY off. Model-space widths would
 *   make a zoomed-out drawing a solid block of ink. A primitive may name its own
 *   SCREEN width (`width`, CSS pixels) -- a section's outline is drawn heavier
 *   than its hatch -- which is still constant at every zoom.
 * - **`opacity`** (0..1, default 1) is a primitive's own alpha, applied as it
 *   is painted: a section's fill and hatch let what is under them show.
 *
 * Batching is per pen -- colour, width, opacity -- for strokes, and per colour
 * and opacity, per primitive, for fills.
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
 * @typedef {import("./transform.js").DrawingTransform} DrawingTransform
 * @typedef {import("./transform.js").DrawingBounds} DrawingBounds
 *
 * @typedef {object} PreparedDrawing
 * @property {number} schemaVersion
 * @property {object} units
 * @property {DrawingBounds|null} bounds
 * @property {readonly object[]} layers
 * @property {readonly { color: string|null, opacity: number, paths: readonly any[] }[]} fills
 * @property {readonly { color: string|null, opacity: number, width: number, path: any }[]} strokes
 * @property {readonly { color: string|null, opacity: number, coordinates: readonly number[] }[]} points
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

/** A primitive's `opacity`, 1 when it names none; anything else is refused. */
function primitiveOpacity(primitive, where) {
  const value = primitive?.opacity;
  if (value === undefined || value === null) return 1;
  if (typeof value !== "number" || !(value >= 0 && value <= 1)) {
    throw new Error(`${where}: opacity must be a number from 0 to 1; received ${describe(value)}.`);
  }
  return value;
}

/** A stroke primitive's `width` in CSS pixels, the hairline when it names none. */
function primitiveWidth(primitive, where) {
  const value = primitive?.width;
  if (value === undefined || value === null) return DRAWING_HAIRLINE_CSS_PX;
  if (typeof value !== "number" || !(value > 0) || !Number.isFinite(value)) {
    throw new Error(`${where}: width must be a positive number of CSS pixels; received ${describe(value)}.`);
  }
  return value;
}

/**
 * Pen-keyed grouping: colour, opacity and (for strokes) width. `null` -- the
 * default pen -- is a colour of its own, kept distinct from every hex string:
 * it is resolved at draw time and must not be folded into whatever the theme's
 * foreground happens to be right now.
 */
function group(map, color, opacity = 1, width = DRAWING_HAIRLINE_CSS_PX) {
  const colorKey = color === null || color === undefined ? null : String(color);
  const key = JSON.stringify([colorKey, opacity, width]);
  let entry = map.get(key);
  if (!entry) {
    entry = { color: colorKey, opacity, width, items: [] };
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

  const PathCtor = resolvePath2D(injectedPath2D);
  const strokeGroups = new Map();
  const fillGroups = new Map();
  const pointGroups = new Map();

  primitives.forEach((primitive, index) => {
    const where = `primitives[${index}]`;
    const type = primitive?.type;
    const geometry = primitive?.geometry;
    const opacity = primitiveOpacity(primitive, where);
    if (type === "lines") {
      const entry = group(strokeGroups, primitive.color, opacity, primitiveWidth(primitive, where));
      if (!entry.path) {
        entry.path = new PathCtor();
      }
      for (const line of geometry) {
        entry.path.moveTo(line[0], line[1]);
        entry.path.lineTo(line[2], line[3]);
      }
    } else if (type === "path") {
      const entry = group(strokeGroups, primitive.color, opacity, primitiveWidth(primitive, where));
      if (!entry.path) {
        entry.path = new PathCtor();
      }
      appendPath(entry.path, geometry, where);
    } else if (type === "filled-paths") {
      const path = new PathCtor();
      for (const commands of geometry) {
        appendPath(path, commands, where);
      }
      group(fillGroups, primitive.color, opacity).items.push(path);
    } else if (type === "filled-polygon") {
      const path = new PathCtor();
      appendPolygon(path, geometry);
      group(fillGroups, primitive.color, opacity).items.push(path);
    } else if (type === "point") {
      const entry = group(pointGroups, primitive.color, opacity);
      entry.items.push(geometry[0], geometry[1]);
    } else {
      throw new Error(
        `${where}: unknown drawing primitive type ${describe(type)}. A cadgen drawing payload at `
        + `schemaVersion ${DRAWING_SCHEMA_VERSION} carries only "point", "lines", "path", `
        + '"filled-paths" and "filled-polygon".'
      );
    }
  });

  return {
    schemaVersion: payload.schemaVersion,
    units: payload.units || null,
    bounds,
    layers: isArray(payload.layers) ? payload.layers : [],
    fills: [...fillGroups.values()].map((entry) => ({ color: entry.color, opacity: entry.opacity, paths: entry.items })),
    strokes: [...strokeGroups.values()].map((entry) => ({
      color: entry.color, opacity: entry.opacity, width: entry.width, path: entry.path
    })),
    points: [...pointGroups.values()].map((entry) => ({
      color: entry.color, opacity: entry.opacity, coordinates: entry.items
    })),
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

/**
 * Draw a prepared drawing under a view transform.
 *
 * Paths are in MODEL coordinates and the context carries the whole view, which
 * is what keeps a hairline a hairline: one `lineWidth` in model units,
 * recomputed per frame as `1.25 / scale`, is 1.25 CSS pixels wide at any zoom,
 * and no geometry is rebuilt when the view moves.
 *
 * Fills go down before strokes. Within a DXF a filled region is nearly always
 * a hatch or a glyph BEHIND the line-work that bounds it, and painting per
 * colour means the primitive order cannot be honoured exactly anyway; putting
 * every fill first is the one ordering that never hides an edge.
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
  ctx.setTransform(
    scale * pixelRatio, 0,
    0, -scale * pixelRatio,
    offsetX * pixelRatio, offsetY * pixelRatio
  );
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  for (const { color, opacity = 1, paths } of drawable.fills) {
    ctx.globalAlpha = opacity;
    ctx.fillStyle = color || foreground;
    for (const path of paths) {
      ctx.fill(path, "evenodd");
    }
  }

  for (const { color, opacity = 1, width = DRAWING_HAIRLINE_CSS_PX, path } of drawable.strokes) {
    ctx.globalAlpha = opacity;
    ctx.lineWidth = width / scale;
    ctx.strokeStyle = color || foreground;
    ctx.stroke(path);
  }

  const radius = DRAWING_POINT_RADIUS_CSS_PX / scale;
  for (const { color, opacity = 1, coordinates } of drawable.points) {
    ctx.globalAlpha = opacity;
    ctx.fillStyle = color || foreground;
    for (let index = 0; index < coordinates.length; index += 2) {
      ctx.beginPath();
      ctx.arc(coordinates[index], coordinates[index + 1], radius, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.restore();
}

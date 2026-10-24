/**
 * `cadgen dxf snapshot` in the page: a `GET /__cad/drawing` payload, on a 2D
 * canvas, as a PNG.
 *
 * This is the CLI half of the viewer's DXF pane, and deliberately shares its
 * whole drawing path (`../lib/drawing2d`): the same fit, the same hairline rule,
 * the same default-pen resolution against the same theme pair. A drawing has
 * no scene and no lights, so nothing here renders with three.js — the
 * headless entry routes a `dxf` job straight past the mesh pipeline.
 *
 * A job may frame it (a plan-view `camera`, the window a Quick Edit's view was
 * looking at) and draw over it (an `annotation` whose marks lie on the sheet), with the
 * code the pane draws it with
 * (`../lib/drawing2d/marks.js`): so a prompt's views come back as they were seen.
 *
 * The payload arrives over the snapshot host's loopback asset server rather
 * than inside the job: cadgen renders it with ezdxf, caches it in the store and
 * writes the bytes to a file the page fetches. A megabyte of JSON inlined in
 * the job would cross the Playwright driver pipe as one escaped protocol
 * message, which is the transport that fails on real drawings.
 */
import { appThemeColors } from "../lib/appTheme.js";
import { clearSurface, drawDrawing, fitTransform, prepareDrawing } from "../lib/drawing2d/index.js";
import { drawAnnotationMarks } from "../lib/drawing2d/marks.js";
import { planTransform } from "../lib/drawing2d/planView.js";
import { ANNOTATION_REFERENCE_HEIGHT_PX, normalizeAnnotation } from "./annotation.js";

/** What an output falls back to when the host sent no size (it always does). */
const DEFAULT_OUTPUT_WIDTH = 1200;
const DEFAULT_OUTPUT_HEIGHT = 900;
/** `output.renderScale`'s range, as `renderOptions.configurePngRenderer` clamps it. */
const MIN_RENDER_SCALE = 1;
const MAX_RENDER_SCALE = 3;

function positiveInteger(value, fallback) {
  const number = Math.floor(Number(value));
  return Number.isFinite(number) && number > 0 ? number : fallback;
}

function renderScale(job) {
  const requested = Number(job?.output?.renderScale);
  if (!Number.isFinite(requested)) {
    return MIN_RENDER_SCALE;
  }
  return Math.min(MAX_RENDER_SCALE, Math.max(MIN_RENDER_SCALE, requested));
}

function canvasContext(width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("this browser gave no 2D canvas context, so the drawing cannot be painted");
  }
  return { canvas, context };
}

/**
 * One output's PNG.
 *
 * Painted at `width * scale` and resampled to `width`, exactly as the mesh
 * path supersamples its drawing buffer: the snapshot contract is expressed in
 * OUTPUT pixels, so a render scale buys sampling quality and never changes the
 * size of the file.
 */
function drawOutput(drawable, { width, height, scale, background, foreground, camera = null, annotation = null }) {
  const { canvas, context } = canvasContext(
    Math.max(1, Math.round(width * scale)),
    Math.max(1, Math.round(height * scale))
  );
  clearSurface(context, { width, height, pixelRatio: scale, background });
  // A plan view frames the window it names; without one the drawing is fitted whole.
  const transform = camera ? planTransform(camera, width, height)
    : drawable.bounds ? fitTransform(drawable.bounds, width, height) : null;
  if (drawable.bounds && transform) {
    drawDrawing(context, drawable, { transform, foreground, pixelRatio: scale });
  }
  if (transform && annotation?.marks?.length) {
    drawAnnotationMarks(context, annotation.marks, { transform, pixelRatio: scale, lineScale: height / ANNOTATION_REFERENCE_HEIGHT_PX });
  }
  if (canvas.width === width && canvas.height === height) {
    return canvas.toDataURL("image/png");
  }
  const resampled = canvasContext(width, height);
  resampled.context.imageSmoothingEnabled = true;
  if ("imageSmoothingQuality" in resampled.context) {
    resampled.context.imageSmoothingQuality = "high";
  }
  resampled.context.drawImage(canvas, 0, 0, canvas.width, canvas.height, 0, 0, width, height);
  return resampled.canvas.toDataURL("image/png");
}

/**
 * A job's annotation, checked as every annotation is: on a drawing its points are in drawing
 * coordinates, on the sheet.
 */
function drawingAnnotation(raw) {
  return raw == null ? null : normalizeAnnotation(raw);
}

/**
 * Render one resolved `dxf` snapshot job.
 *
 * What the picture says about itself (an empty drawing) is cadgen's to say,
 * and it does, beside the job; the page only paints.
 *
 * @param {object} job The resolved render job; `job.resolved.drawingUrl` names the payload.
 * @returns {Promise<object>} The host's result shape: `{ ok, mode, outputs, warnings }`.
 */
export async function runHeadlessDrawingJob(job) {
  const url = String(job?.resolved?.drawingUrl || "");
  if (!url) {
    throw new Error(
      "a drawing render job carries no drawingUrl: cadgen resolves a .dxf to its 2D payload "
      + "before the page is asked to draw it"
    );
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`the drawing payload could not be read (HTTP ${response.status} for ${url})`);
  }
  const drawable = prepareDrawing(await response.json());
  const annotation = drawingAnnotation(job?.annotation);
  const warnings = [];
  if (!drawable.bounds) {
    // A true answer, and one nobody would guess from a blank PNG.
    warnings.push("this drawing has no geometry in its modelspace, so the image is empty");
  }
  const { background, foreground } = appThemeColors(job?.display?.appearance);
  const scale = renderScale(job);
  const transparent = job?.output?.transparent === true;
  const outputs = (Array.isArray(job?.outputs) ? job.outputs : []).map((output) => {
    const width = positiveInteger(output?.width, DEFAULT_OUTPUT_WIDTH);
    const height = positiveInteger(output?.height, DEFAULT_OUTPUT_HEIGHT);
    return {
      path: String(output?.path || ""),
      width,
      height,
      mimeType: "image/png",
      dataUrl: drawOutput(drawable, {
        width,
        height,
        scale,
        background: transparent ? null : background,
        foreground,
        camera: output?.camera && typeof output.camera === "object" ? output.camera : null,
        annotation
      })
    };
  });
  return {
    ok: true,
    mode: "view",
    appearance: job?.display?.appearance === "dark" ? "dark" : "light",
    primitiveCount: drawable.primitiveCount,
    outputs,
    warnings: []
  };
}

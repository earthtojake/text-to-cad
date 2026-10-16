/**
 * The 2D half of the snapshot bundle's output contract, shared by every flat render (a DXF
 * drawing, a plot): one PNG per declared output, at exactly the size it asked for.
 *
 * A picture is painted at `width * renderScale` and resampled to `width`, exactly as the mesh
 * path supersamples its drawing buffer: the snapshot contract is expressed in OUTPUT pixels,
 * so a render scale buys sampling quality and never changes the size of the file.
 */

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

/** The job's supersampling factor, clamped to the range every render honours. */
export function renderScale(job) {
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
    throw new Error("this browser gave no 2D canvas context, so the picture cannot be painted");
  }
  return { canvas, context };
}

/**
 * One output's PNG as a data URL: `paint(context)` draws the picture in CSS pixels on a
 * backing store `scale` times larger (`pixelRatio: scale`), which is then resampled to
 * `width` x `height`.
 *
 * @param {{ width: number, height: number, scale: number }} size
 * @param {(context: CanvasRenderingContext2D) => void} paint
 */
export function paintOutput({ width, height, scale }, paint) {
  const { canvas, context } = canvasContext(
    Math.max(1, Math.round(width * scale)),
    Math.max(1, Math.round(height * scale))
  );
  paint(context);
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
 * The job's declared outputs, each with its PNG: `render(width, height)` answers a data URL.
 *
 * @param {object} job
 * @param {(width: number, height: number) => string} render
 */
export function renderOutputs(job, render) {
  return (Array.isArray(job?.outputs) ? job.outputs : []).map((output) => {
    const width = positiveInteger(output?.width, DEFAULT_OUTPUT_WIDTH);
    const height = positiveInteger(output?.height, DEFAULT_OUTPUT_HEIGHT);
    return {
      path: String(output?.path || ""),
      width,
      height,
      mimeType: "image/png",
      dataUrl: render(width, height)
    };
  });
}

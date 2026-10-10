/**
 * The rasters a plot pane paints from: what keeps a zoom crisp and a pan cheap.
 *
 * A sheet's SVG is drawn by the browser, which rasterises the vector at whatever scale it lands
 * at — crisp at any zoom, and far too slow to do every frame: a large board's plot is tens of
 * megabytes of SVG and a second to rasterise. So the pane draws the SVGs into a PATCH — a canvas
 * covering what the pane shows plus a margin, at exactly the scale it is shown at, made with
 * core's `drawPlot` and the sheets' own images (`sheetImages`), the frame a snapshot draws — and
 * every frame is the sheets' backgrounds and the patches over them, placed in page space
 * (`drawPlot` again). A pan moves a patch by whole device pixels: a blit, never a resample. A
 * zoom scales the patches it has until the view has been still for `SETTLE_MS`; then the view is
 * drawn again at its new scale. A pan past the margin is the same: what is not covered shows the
 * sheet's background until the view rests, then it is drawn.
 *
 * A few patches are kept (`PATCH_LIMIT`, and `PATCH_BUDGET_PIXELS` between them), least recently
 * drawn first out: zooming back out to a view drawn before is instant, and a zoom or a pan has
 * something under it. The one at the scale on screen is drawn last, over the others.
 *
 * Nothing here is React: the pane's view hook owns one of these per plot, paints through it and
 * disposes of it with the plot.
 */
import { drawPlot, rectsOverlap, sheetImages, visiblePageRect } from "@text-to-cad/core/lib/plot2d/index.js";

/** What a patch covers beyond the pane, on each side, as a share of the pane. */
const PATCH_MARGIN = 0.15;
/** One patch's backing store, at most: a margin that would pass it is given up first. */
const PATCH_MAX_PIXELS = 32 * 1024 * 1024;
/** How many patches are kept, and how many pixels they may hold between them. */
export const PATCH_LIMIT = 3;
const PATCH_BUDGET_PIXELS = 48 * 1024 * 1024;
/** How long a view must rest before it is drawn again at its own scale. */
export const SETTLE_MS = 120;

const intersect = (left, right) => {
  const box = [Math.max(left[0], right[0]), Math.max(left[1], right[1]), Math.min(left[2], right[2]), Math.min(left[3], right[3])];
  return box[0] < box[2] && box[1] < box[3] ? box : null;
};
const sameScale = (left, right) => Math.abs(left - right) <= right * 1e-9;

function defaultCanvas(width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

/**
 * @param {{ layout: import("@text-to-cad/core/lib/plot2d/plot.js").PlotLayout,
 *   images: readonly CanvasImageSource[], onChange: () => void, view?: object|null,
 *   createCanvas?: (width: number, height: number) => HTMLCanvasElement,
 *   schedule?: typeof setTimeout, cancel?: typeof clearTimeout }} options
 *   `onChange`: a better picture is ready; paint again.
 */
export function createPlotRasters({ layout, images, onChange, view = null, createCanvas = defaultCanvas,
  schedule = (callback, delay) => setTimeout(callback, delay), cancel = (handle) => clearTimeout(handle) }) {
  const svgs = sheetImages(layout, images);
  /** @type {{ canvas: HTMLCanvasElement, scale: number, rect: number[], used: number }[]} */
  let patches = [];
  let wanted = null;
  let timer = 0;
  let clock = 0;
  let disposed = false;

  const deviceScale = (frame) => frame.transform.scale * frame.pixelRatio;
  /** What of the plot the frame shows, in page millimetres, or null when it shows none of it. */
  const shown = (frame) => intersect(visiblePageRect(frame.transform, frame.width, frame.height), layout.bounds);

  /** Whether a patch draws everything the frame shows, at the frame's own scale. */
  const covers = (patch, frame, box) => sameScale(patch.scale, deviceScale(frame))
    && patch.rect[0] <= box[0] + 1e-9 && patch.rect[1] <= box[1] + 1e-9
    && patch.rect[2] >= box[2] - 1e-9 && patch.rect[3] >= box[3] - 1e-9;

  function release(patch) {
    // Zeroing the size frees the backing store now rather than whenever the canvas is collected.
    patch.canvas.width = 0;
    patch.canvas.height = 0;
  }

  /** Draw the plot for this frame's view into a new patch. */
  function rasterize(frame) {
    const box = shown(frame);
    if (!box) return;
    const scale = deviceScale(frame);
    const originX = frame.transform.offsetX * frame.pixelRatio;
    const originY = frame.transform.offsetY * frame.pixelRatio;
    // Device pixels of THIS view, so the patch lands on the pane's own pixel grid.
    const grid = (rect) => [Math.floor(rect[0] * scale + originX), Math.floor(rect[1] * scale + originY),
      Math.ceil(rect[2] * scale + originX), Math.ceil(rect[3] * scale + originY)];
    const visible = visiblePageRect(frame.transform, frame.width, frame.height);
    const marginX = (visible[2] - visible[0]) * PATCH_MARGIN;
    const marginY = (visible[3] - visible[1]) * PATCH_MARGIN;
    let pixels = grid(intersect([visible[0] - marginX, visible[1] - marginY, visible[2] + marginX, visible[3] + marginY], layout.bounds));
    if ((pixels[2] - pixels[0]) * (pixels[3] - pixels[1]) > PATCH_MAX_PIXELS) pixels = grid(box);
    const [left, top, right, bottom] = pixels;
    const canvas = createCanvas(right - left, bottom - top);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("This browser gave no 2D canvas context, so the plot cannot be drawn.");
    // The board's Display (`view`: its side, its layers, its pours) is drawn into the patch; a frame
    // only places patches, so it never applies it twice.
    drawPlot(context, layout, { transform: { scale, offsetX: originX - left, offsetY: originY - top }, images: svgs, ...(view ? { view } : {}) });
    patches.push({
      canvas, scale, used: (clock += 1),
      rect: [(left - originX) / scale, (top - originY) / scale, (right - originX) / scale, (bottom - originY) / scale]
    });
    // Out goes the least recently drawn, never the one just made.
    const held = () => patches.reduce((total, patch) => total + patch.canvas.width * patch.canvas.height, 0);
    while (patches.length > PATCH_LIMIT || (patches.length > 1 && held() > PATCH_BUDGET_PIXELS)) {
      const oldest = patches.slice(0, -1).reduce((least, patch) => (patch.used < least.used ? patch : least));
      patches = patches.filter((patch) => patch !== oldest);
      release(oldest);
    }
  }

  /** The patches as page-placed images: the farthest from this frame's scale first. */
  function placed(frame) {
    const scale = deviceScale(frame);
    const originX = frame.transform.offsetX * frame.pixelRatio;
    const originY = frame.transform.offsetY * frame.pixelRatio;
    const distance = (patch) => Math.abs(Math.log(patch.scale / scale));
    return [...patches]
      .sort((left, right) => distance(right) - distance(left) || left.scale - right.scale)
      .map((patch) => {
        let [x, y] = patch.rect;
        if (sameScale(patch.scale, scale)) {
          // At its own scale a patch is moved, not resampled: whole device pixels only.
          const deviceX = x * scale + originX;
          const deviceY = y * scale + originY;
          x += (Math.round(deviceX) - deviceX) / scale;
          y += (Math.round(deviceY) - deviceY) / scale;
        }
        return { image: patch.canvas, x, y, width: patch.rect[2] - patch.rect[0], height: patch.rect[3] - patch.rect[1] };
      });
  }

  function refine() {
    timer = 0;
    if (disposed || !wanted) return;
    const frame = wanted;
    wanted = null;
    rasterize(frame);
    onChange();
  }

  return {
    /**
     * Paint one frame: the sheets and every patch over them. Answers whether the frame is final —
     * drawn at its own scale wherever it shows the plot — or will be drawn again once the view rests.
     *
     * @param {CanvasRenderingContext2D} ctx
     * @param {{ transform: object, width: number, height: number, pixelRatio: number }} frame
     */
    paint(ctx, frame) {
      if (disposed) return true;
      const box = shown(frame);
      // Nothing to show yet: draw it now, so the first frame is the plot and not its backgrounds.
      if (box && patches.length === 0) rasterize(frame);
      // The browser's default (bilinear) smoothing: a patch is resampled only while the view
      // moves, and "high" quality costs several times as much per frame on a software canvas.
      drawPlot(ctx, layout, { transform: frame.transform, pixelRatio: frame.pixelRatio, images: placed(frame) });
      const visible = box ? visiblePageRect(frame.transform, frame.width, frame.height) : null;
      for (const patch of patches) {
        if (visible && rectsOverlap(patch.rect, visible)) patch.used = (clock += 1);
      }
      const final = !box || patches.some((patch) => covers(patch, frame, box));
      if (timer) cancel(timer);
      timer = 0;
      wanted = final ? null : { transform: { ...frame.transform }, width: frame.width, height: frame.height, pixelRatio: frame.pixelRatio };
      if (wanted) timer = schedule(refine, SETTLE_MS);
      return final;
    },
    /** Draw what the last frame was waiting for now, rather than once the view rests. */
    flush() {
      if (timer) cancel(timer);
      timer = 0;
      if (!wanted || disposed) return;
      const frame = wanted;
      wanted = null;
      rasterize(frame);
    },
    /** How many patches are kept: for tests and nothing else. */
    get size() { return patches.length; },
    dispose() {
      disposed = true;
      if (timer) cancel(timer);
      timer = 0;
      wanted = null;
      patches.forEach(release);
      patches = [];
    }
  };
}

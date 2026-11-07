/**
 * A board in 3D, its faces' pictures: each face is the 2D drawer's own picture of that side
 * (`plot2d`'s `drawPlot`, with the Display the Layers tab sets, in the view's theme), drawn on a
 * raster laid over the face, and the highlight (`board2d`'s `drawBoardOverlay`: the selection, the
 * hover, a net in focus, what is isolated, the area being named) and the ink on a second, see-through
 * raster over it. So a face shows exactly what the 2D view shows for that side: one drawer, two views.
 *
 * The budget: a face's picture is at most `FACE_PIXELS` and the GPU's largest texture on a side; its
 * overlay at most `OVERLAY_PIXELS`. Every draw goes through ONE scratch canvas per kind, which the
 * stage uploads into its face's texture at once (`boardStage.js`), so the page holds two canvases
 * however many faces and redraws there are, and the GPU two pictures and two overlays: overwritten in
 * place, never kept by revision or by Display.
 *
 * Importing this module has no environmental effects.
 */
import { drawPlot } from "../plot2d/plot.js";
import { boardDrawView } from "../plot2d/boardDisplay.js";
import { boardMirrorX } from "../plot2d/boardView.js";

/** The most pixels a face's picture takes: about 15 px a millimetre across a 312 mm board. */
export const FACE_PIXELS = 8_000_000;
/** The most pixels a face's overlay (the highlight and the ink) takes. */
export const OVERLAY_PIXELS = 2_000_000;

/**
 * The box a face's pictures cover, in page millimetres: the sheet (the outline's box) and what the
 * file draws past it (`layout.extent`: a dimension, a fab note off the edge), so nothing the 2D view
 * shows is lost in 3D, though at most half the sheet's longer side past each of its edges (a stray
 * item far off would starve the board of pixels). Wide enough on both sides of the sheet's centre
 * line that the back's picture, mirrored about it, lands in the same box.
 * @returns {{ x: number, y: number, width: number, height: number }}
 */
export function faceBox(layout, sheet) {
  const x0 = sheet.x || 0, y0 = sheet.y || 0, x1 = x0 + sheet.width, y1 = y0 + sheet.height;
  const reach = Math.max(sheet.width, sheet.height) / 2;
  const [e0, e1, e2, e3] = Array.isArray(layout?.extent) ? layout.extent : [x0, y0, x1, y1];
  const past = (value, edge, sign) => (Number.isFinite(value) ? Math.min(Math.max((value - edge) * sign, 0), reach) : 0);
  const across = Math.max(past(e0, x0, -1), past(e2, x1, 1));
  const top = past(e1, y0, -1), bottom = past(e3, y1, 1);
  return { x: x0 - across, y: y0 - top, width: sheet.width + 2 * across, height: sheet.height + top + bottom };
}

/**
 * The raster for a sheet within a budget: as many pixels a millimetre as `maxPixels` allows, and no
 * side longer than `maxSize` (the GPU's `MAX_TEXTURE_SIZE`).
 * @returns {{ width: number, height: number, scale: number }}  `scale`: pixels a millimetre.
 */
export function faceRaster(sheet, { maxPixels = FACE_PIXELS, maxSize = 16384 } = {}) {
  const w = Math.max(sheet.width, 1e-6), h = Math.max(sheet.height, 1e-6);
  const scale = Math.min(Math.sqrt(maxPixels / (w * h)), maxSize / w, maxSize / h);
  return { width: Math.max(1, Math.floor(w * scale)), height: Math.max(1, Math.floor(h * scale)), scale };
}

/**
 * The transform a face is drawn under (drawing2d's: model space, y up, to raster pixels): the face's
 * box (`faceBox`) filling the raster. The same for both sides: from the back, `drawPlot` mirrors about
 * the sheet's centre line, which is the box's, so the box stays where it is.
 */
export function faceTransform(sheet, scale) {
  return { scale, offsetX: -(sheet.x || 0) * scale, offsetY: -(sheet.y || 0) * scale };
}

/**
 * A sheet point's place on a face's raster (its box, `faceBox`), as texture coordinates (v up, three's):
 * from the back the picture is mirrored left to right, so the point seen from below lands on what is
 * drawn under it.
 */
export function faceUv([x, y], sheet, side) {
  const u = (x - (sheet.x || 0)) / sheet.width;
  return [side === "bottom" ? 1 - u : u, 1 - (y - (sheet.y || 0)) / sheet.height];
}

/** What a face draws: the Display, from that face's side. */
export const faceView = (display, sheet, side) => boardDrawView({ ...display, side }, sheet);

/**
 * The scratch canvases and what is drawn on them, over the face's box (`faceBox`).
 * @param {{ layout: object, sheet: object, box?: object, createCanvas?: () => HTMLCanvasElement, maxSize?: number, maxPixels?: number }} options
 *   `maxPixels`: a face's budget (`FACE_PIXELS`; a quarter of it where WebGL runs in software).
 */
export function createFaceRasters({ layout, sheet, box = faceBox(layout, sheet), createCanvas = () => document.createElement("canvas"), maxSize = 16384,
  maxPixels = FACE_PIXELS }) {
  const base = faceRaster(box, { maxPixels, maxSize });
  const overlay = faceRaster(box, { maxPixels: OVERLAY_PIXELS, maxSize });
  let pictureCanvas = null, overlayCanvas = null;
  const canvasOf = (current, size) => {
    const canvas = current || createCanvas();
    if (canvas.width !== size.width) canvas.width = size.width;
    if (canvas.height !== size.height) canvas.height = size.height;
    return canvas;
  };
  return {
    base, overlay, box,
    /**
     * A face's picture, drawn on the picture's scratch canvas: hand it to the face's texture at once. It is
     * drawn as the 2D view draws the board at `lineScale` pixels a millimetre (the screen's, as the 3D view
     * shows the whole board): its hairlines a pixel there and its labels at that level of detail, in the
     * raster's finer pixels. Drawn at the raster's own scale, a hairline would be a quarter of a pixel on
     * screen, and the picture paler than the 2D view's.
     */
    drawFace(side, { display, theme, lineScale = base.scale }) {
      pictureCanvas = canvasOf(pictureCanvas, base);
      const ctx = pictureCanvas.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, base.width, base.height);
      const nominal = Math.min(base.scale, Math.max(lineScale || 0, base.scale / 8));
      drawPlot(ctx, layout, { transform: faceTransform(box, nominal), pixelRatio: base.scale / nominal, view: faceView(display, sheet, side), detail: nominal,
        backdrop: "board", theme });
      return pictureCanvas;
    },
    /**
     * A face's overlay: `paint(ctx, frame)` draws in page millimetres under `frame.transform`, as the 2D
     * view's overlay does, at `lineScale` pixels a millimetre (the screen's): its lines as thick on screen
     * as the 2D view's. Null when it drew nothing (`paint` answering false): the overlay is put away.
     */
    drawOverlay(side, paint, { lineScale }) {
      overlayCanvas = canvasOf(overlayCanvas, overlay);
      const ctx = overlayCanvas.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, overlay.width, overlay.height);
      const nominal = Math.max(lineScale || 0, 1e-3);
      const drew = paint(ctx, { transform: faceTransform(box, nominal), pixelRatio: overlay.scale / nominal,
        width: box.width * nominal, height: box.height * nominal, mirrorX: side === "bottom" ? boardMirrorX(sheet, side) : null, side });
      return drew === false ? null : overlayCanvas;
    },
    /** The pixels the scratch canvases hold now. */
    pixels: () => [pictureCanvas, overlayCanvas].reduce((sum, canvas) => sum + (canvas ? canvas.width * canvas.height : 0), 0),
    dispose() {
      for (const canvas of [pictureCanvas, overlayCanvas]) if (canvas) { canvas.width = 0; canvas.height = 0; }
      pictureCanvas = overlayCanvas = null;
    }
  };
}

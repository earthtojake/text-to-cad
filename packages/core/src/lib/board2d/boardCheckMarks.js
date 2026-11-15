/**
 * Where a board fails its design rule check, marked on its picture: a pin at each failing finding's
 * place (`boardChecks.js`'s `boardCheckMarks`), drawn in the overlay's pass, after the hover and the
 * selection (`boardOverlay.js`). A pin keeps its size on screen, so a fault a tenth of a millimetre
 * across is seen at the fit, and its head stands off the place its tip is on, so the copper at fault
 * is not under it. Red in both themes, edged in white so it parts from KiCad's red copper, with the
 * mark every error wears.
 *
 * Pure canvas 2D, in CSS pixels: `transform` maps page millimetres to them, `mirrorX` is the page x
 * the board is mirrored about (the view from the bottom), or null.
 */
import { pageToScreen } from "../plot2d/plot.js";

/** The pin's colours in each theme: its fill, its edge and its mark. */
export const BOARD_CHECK_MARK_COLORS = Object.freeze({
  dark: Object.freeze({ fill: "#f2555a", edge: "#ffffff", mark: "#ffffff" }),
  light: Object.freeze({ fill: "#d92d20", edge: "#ffffff", mark: "#ffffff" }),
});
// The pin, in CSS pixels: its head's radius, how far the head's centre stands over the tip, and its edge.
const HEAD = 8;
const RISE = 18;
const EDGE = 1.5;
// The half angle the pin's sides leave its head at, from straight down.
const SPREAD = Math.asin(HEAD / RISE);

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {readonly [number, number][]} marks  Page points.
 * @param {{ transform: { scale: number, offsetX: number, offsetY: number }, pixelRatio?: number, width: number,
 *   height: number, mirrorX?: number | null, scheme?: "light" | "dark" }} frame
 * @returns {number} How many it drew: the marks on screen.
 */
export function drawBoardCheckMarks(ctx, marks, { transform, pixelRatio = 1, width, height, mirrorX = null, scheme = "dark" }) {
  if (!ctx || !marks?.length || !transform || !(transform.scale > 0)) return 0;
  const colors = scheme === "light" ? BOARD_CHECK_MARK_COLORS.light : BOARD_CHECK_MARK_COLORS.dark;
  const reach = RISE + HEAD + EDGE;
  let drawn = 0;
  ctx.save();
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  for (const [x, y] of marks) {
    const [sx, sy] = pageToScreen(transform, mirrorX == null ? x : 2 * mirrorX - x, y);
    if (sx < -reach || sx > width + reach || sy < -EDGE || sy > height + reach) continue;
    const cy = sy - RISE;
    // The pin: its tip on the place, its sides up to the head, round over the top.
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.arc(sx, cy, HEAD, Math.PI / 2 + (Math.PI / 2 - SPREAD), Math.PI / 2 - (Math.PI / 2 - SPREAD), false);
    ctx.closePath();
    ctx.fillStyle = colors.fill;
    ctx.fill();
    ctx.strokeStyle = colors.edge;
    ctx.lineWidth = EDGE;
    ctx.stroke();
    // The mark: an exclamation mark in the head.
    ctx.strokeStyle = colors.mark;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(sx, cy - 4.2);
    ctx.lineTo(sx, cy + 0.8);
    ctx.stroke();
    ctx.fillStyle = colors.mark;
    ctx.beginPath();
    ctx.arc(sx, cy + 4, 1, 0, Math.PI * 2);
    ctx.fill();
    drawn += 1;
  }
  ctx.restore();
  return drawn;
}

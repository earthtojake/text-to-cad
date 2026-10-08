/**
 * The chrome a section snapshot carries over its drawing: the cut locator, and
 * the burnt-in view label when the job asks for one.
 *
 * cadgen computes the section and everything said about it
 * (`cadgen.section_drawing`): the drawing payload this page paints, the plane's
 * label and where the cut sits across the parts. This only paints those two
 * facts, in output pixels, on top of the finished drawing.
 */
import { drawBurnedInLabel } from "./renderOptions.js";

const LOCATOR_FONT = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";

/**
 * @param {CanvasRenderingContext2D} context A context in output pixels.
 * @param {{ label: string, locator: number, title?: string|null }} section From the job's `resolved.section`.
 */
export function drawSectionOverlay(context, section, width, height) {
  const label = String(section?.label || "");
  const fraction = Math.min(Math.max(Number(section?.locator) || 0, 0), 1);
  const locatorWidth = Math.max(170, Math.min(width * 0.24, 260));
  const locatorHeight = Math.max(78, Math.min(height * 0.16, 130));
  const margin = Math.max(18, Math.round(Math.min(width, height) * 0.024));
  const x = width - margin - locatorWidth;
  const y = height - margin - locatorHeight;
  const pad = 16;
  const trackX = x + pad;
  const trackY = y + locatorHeight / 2;
  const trackWidth = locatorWidth - pad * 2;
  const cutX = trackX + fraction * trackWidth;
  context.save();
  context.fillStyle = "rgba(255, 255, 255, 0.92)";
  context.strokeStyle = "rgba(17, 24, 39, 0.42)";
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(x, y, locatorWidth, locatorHeight, 8);
  context.fill();
  context.stroke();
  context.fillStyle = "#111827";
  context.font = `700 13px ${LOCATOR_FONT}`;
  context.fillText("CUT LOCATOR", x + pad, y + 10);
  context.strokeStyle = "#9ca3af";
  context.lineWidth = 8;
  context.lineCap = "round";
  context.beginPath();
  context.moveTo(trackX, trackY);
  context.lineTo(trackX + trackWidth, trackY);
  context.stroke();
  context.strokeStyle = "#ef4444";
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(cutX, trackY - 22);
  context.lineTo(cutX, trackY + 22);
  context.stroke();
  context.font = `600 12px ${LOCATOR_FONT}`;
  context.fillStyle = "#ef4444";
  context.fillText(label, x + pad, y + locatorHeight - 22);
  context.restore();
  if (section?.title) {
    drawBurnedInLabel(context, section.title, width, height);
  }
}

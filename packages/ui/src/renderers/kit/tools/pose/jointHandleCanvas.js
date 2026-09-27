/**
 * How a joint handle looks: drawn on a 2D canvas over the viewport, like the
 * measurement rulers, in screen pixels. That is what keeps a handle the same
 * size at every zoom and on top of the model, and keeps it out of everything
 * the 3D scene feeds: captures, render mode, bounds, shadows and picking.
 */

import { CAD_EDGE_HIGHLIGHT_COLOR } from "@hardcore/core/common/displaySettings.js";

/** The arm's length on screen, pivot to knob. */
export const JOINT_HANDLE_ARM_PX = 44;
/** How close a press has to land to take a knob: generous, a knob is small. */
export const JOINT_HANDLE_HIT_PX = 12;
export const JOINT_HANDLE_TOUCH_HIT_PX = 22;

// The viewport's own highlight colour reads on the dark and the light canvas
// alike; the dark under-stroke is what keeps a thin line legible over a pale part.
const COLOR = CAD_EDGE_HIGHLIGHT_COLOR;
const HALO = "rgba(15, 23, 42, 0.45)";
const KNOB_RIM = "rgba(255, 255, 255, 0.95)";

/** `shoulder 42.0 deg`-style reading for the label beside a held or hovered knob. */
export function formatJointHandleValue(value, unit) {
  const number = Number(value) || 0;
  if (unit === "deg") return `${number.toFixed(1)}°`;
  return unit === "m" ? `${number.toFixed(3)} m` : `${number.toFixed(1)} ${unit}`;
}

function strokePolyline(context, points, { closed = false } = {}) {
  let drawing = false;
  context.beginPath();
  for (const point of points) {
    // A point behind the camera breaks the line rather than streaking across the view.
    if (!point) { drawing = false; continue; }
    if (drawing) context.lineTo(point[0], point[1]);
    else context.moveTo(point[0], point[1]);
    drawing = true;
  }
  if (closed && points.every(Boolean)) context.closePath();
  context.stroke();
}

function strokeWithHalo(context, points, { width, alpha, closed }) {
  context.globalAlpha = alpha;
  context.lineWidth = width + 2;
  context.strokeStyle = HALO;
  strokePolyline(context, points, { closed });
  context.lineWidth = width;
  context.strokeStyle = COLOR;
  strokePolyline(context, points, { closed });
}

function fillCircle(context, [x, y], radius) {
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.fill();
}

/** A short tick across each end of a slider's track, in screen space: where the travel stops. */
function trackStops(guidePx, half = 4) {
  const [from, to] = guidePx;
  if (!from || !to) return [];
  const length = Math.hypot(to[0] - from[0], to[1] - from[1]);
  if (!(length > 1)) return [];
  const across = [(-(to[1] - from[1]) / length) * half, ((to[0] - from[0]) / length) * half];
  return [from, to].map((end) => [[end[0] - across[0], end[1] - across[1]], [end[0] + across[0], end[1] + across[1]]]);
}

function drawHandle(context, layout, { active, quiet }) {
  context.lineCap = "round";
  context.lineJoin = "round";
  // A crowded model rests as knobs alone; the arm and the travel appear with the pointer.
  if (active || !quiet) {
    if (layout.slider) {
      // The track IS the handle's shape, so it is drawn as firmly as an arm, with a stop at each end.
      strokeWithHalo(context, layout.guidePx, { width: active ? 2 : 1.25, alpha: active ? 1 : 0.7 });
      for (const stop of trackStops(layout.guidePx)) strokeWithHalo(context, stop, { width: active ? 2 : 1.25, alpha: active ? 1 : 0.7 });
    } else {
      strokeWithHalo(context, layout.guidePx, { width: active ? 1.5 : 1, alpha: active ? 0.8 : 0.4, closed: layout.guideClosed });
      strokeWithHalo(context, [layout.pivotPx, layout.knobPx], { width: active ? 2 : 1.25, alpha: active ? 1 : 0.7 });
      context.globalAlpha = active ? 1 : 0.7;
      context.fillStyle = COLOR;
      fillCircle(context, layout.pivotPx, active ? 2.5 : 2);
    }
  }
  context.globalAlpha = active ? 1 : 0.85;
  context.fillStyle = HALO;
  fillCircle(context, layout.knobPx, active ? 8 : 6.5);
  context.fillStyle = KNOB_RIM;
  fillCircle(context, layout.knobPx, active ? 6.5 : 5);
  context.fillStyle = COLOR;
  fillCircle(context, layout.knobPx, active ? 5 : 3.75);
}

/** Paint every handle; the hovered or held one (`activeId`) last, brighter, with its travel. */
export function drawJointHandles(context, layouts, { activeId = "", quiet = false } = {}) {
  for (const layout of layouts) {
    if (layout.id !== activeId) drawHandle(context, layout, { active: false, quiet });
  }
  const active = layouts.find((layout) => layout.id === activeId);
  if (active) drawHandle(context, active, { active: true, quiet });
  context.globalAlpha = 1;
}

/** The knob under a pointer at `point` (CSS pixels), nearest first; `null` when none is within `radius`. */
export function jointHandleAt(layouts, point, radius) {
  let best = null;
  let bestDistance = radius;
  for (const layout of layouts) {
    const distance = Math.hypot(layout.knobPx[0] - point[0], layout.knobPx[1] - point[1]);
    if (distance <= bestDistance) {
      best = layout;
      bestDistance = distance;
    }
  }
  return best;
}

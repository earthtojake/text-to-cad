import { formatMeasurement } from "./measurement.js";
import { dimensionEndpoints, measureDimensionSegments } from "./measureLines.js";
import { projectWorldPointToClient } from "./measureRuler.js";

// Draft state is amber so it can never be confused with a committed dimension.
export const MEASURE_DIMENSION_DRAFT_COLOR = "#f59e0b";
export const MEASURE_DIMENSION_COMMITTED_COLOR = "#22d3ee";

/**
 * One colour per measurement, so a line in the viewport and its row in the panel
 * identify each other without hovering either. Muted mid-tones rather than
 * saturated ones: several are on screen at once over a shaded model, and they
 * have to read in both the light and dark themes without competing with the
 * selection blue or the amber draft.
 */
// Twelve hues at even 30 degree spacing, all at the same lightness and
// saturation (HSL 45%/70%), so no measurement's colour shouts louder than
// another's. The order is deliberately not the order around the wheel: colours
// are handed out in sequence, so stepping by 150 degrees each time means two
// measurements taken one after another — the pair most likely to be compared —
// are never neighbouring hues.
export const MEASURE_SERIES_COLORS = Object.freeze([
  "#d59090",
  "#90d5b2",
  "#d590d5",
  "#b2d590",
  "#9090d5",
  "#d5b290",
  "#90d5d5",
  "#d590b2",
  "#90d590",
  "#b290d5",
  "#d5d590",
  "#90b2d5"
]);

export function measureSeriesColor(index) {
  const numeric = Number(index);
  if (!Number.isFinite(numeric)) {
    return MEASURE_SERIES_COLORS[0];
  }
  const wrapped = Math.trunc(numeric) % MEASURE_SERIES_COLORS.length;
  return MEASURE_SERIES_COLORS[wrapped < 0 ? wrapped + MEASURE_SERIES_COLORS.length : wrapped];
}
// Inactive dimensions recede, but they still have to be identifiable by colour
// against their row. The series palette is already muted, so the 0.3 that suited
// one saturated cyan line washed the pastels out to nothing; the emphasis on the
// active dimension now comes mostly from line weight and its label.
export const MEASURE_DIMENSION_FADED_ALPHA = 0.7;
export const MEASURE_DIMENSION_LABEL_BACKGROUND = "rgba(15, 23, 42, 0.92)";
export const MEASURE_DIMENSION_LABEL_FONT =
  "600 8px ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif";

const LABEL_PADDING_X = 6;
const LABEL_PADDING_Y = 3;
const LABEL_MIN_MARGIN = 4;

export function measureLabelText(measurement, { precision = 2 } = {}) {
  const formatted = formatMeasurement(measurement, { precision });
  if (!formatted) {
    return "";
  }
  if (measurement?.perpendicular !== null && measurement?.perpendicular !== undefined) {
    return `⟂ ${formatted}`;
  }
  // C-C is the standard shorthand for a centre-to-centre (hole spacing) reading.
  if (measurement?.centerDistance !== null && measurement?.centerDistance !== undefined) {
    return `C-C ${formatted}`;
  }
  return formatted;
}

/**
 * Projects world-space measurement endpoints to screen space and builds an
 * offset dimension construction in pixel coordinates.
 * Completely immune to camera orbit jitter.
 */
export function screenSpaceDimensionLayout(
  pickA,
  pickB,
  measurement = null,
  camera = null,
  rect = null,
  {
    offset = 24,
    witnessOvershoot = 5,
    arrowLength = 8,
    arrowWidth = 3.5
  } = {}
) {
  const endpoints = dimensionEndpoints(pickA, pickB, measurement);
  if (!endpoints) {
    return null;
  }
  const screenStart = projectWorldPointToClient(endpoints.start, camera, rect);
  const screenEnd = projectWorldPointToClient(endpoints.end, camera, rect);
  if (!screenStart || !screenEnd) {
    return null;
  }

  const dx = screenEnd.x - screenStart.x;
  const dy = screenEnd.y - screenStart.y;
  const length = Math.hypot(dx, dy);
  if (!(length > 1e-6)) {
    return null;
  }

  const dirX = dx / length;
  const dirY = dy / length;
  const perpX = -dirY;
  const perpY = dirX;

  const offsetX = perpX * offset;
  const offsetY = perpY * offset;

  const witnessStartA = { x: screenStart.x, y: screenStart.y };
  const witnessEndA = {
    x: screenStart.x + perpX * (offset + witnessOvershoot),
    y: screenStart.y + perpY * (offset + witnessOvershoot)
  };

  const witnessStartB = { x: screenEnd.x, y: screenEnd.y };
  const witnessEndB = {
    x: screenEnd.x + perpX * (offset + witnessOvershoot),
    y: screenEnd.y + perpY * (offset + witnessOvershoot)
  };

  const dimensionStart = {
    x: screenStart.x + offsetX,
    y: screenStart.y + offsetY
  };
  const dimensionEnd = {
    x: screenEnd.x + offsetX,
    y: screenEnd.y + offsetY
  };

  const flip = length < arrowLength * 2.5;
  const arrow1Dir = flip ? -1 : 1;
  const arrow2Dir = flip ? 1 : -1;

  const arrow1 = {
    tip: dimensionStart,
    left: {
      x: dimensionStart.x + (dirX * arrowLength * arrow1Dir) + (perpX * arrowWidth),
      y: dimensionStart.y + (dirY * arrowLength * arrow1Dir) + (perpY * arrowWidth)
    },
    right: {
      x: dimensionStart.x + (dirX * arrowLength * arrow1Dir) - (perpX * arrowWidth),
      y: dimensionStart.y + (dirY * arrowLength * arrow1Dir) - (perpY * arrowWidth)
    }
  };

  const arrow2 = {
    tip: dimensionEnd,
    left: {
      x: dimensionEnd.x + (dirX * arrowLength * arrow2Dir) + (perpX * arrowWidth),
      y: dimensionEnd.y + (dirY * arrowLength * arrow2Dir) + (perpY * arrowWidth)
    },
    right: {
      x: dimensionEnd.x + (dirX * arrowLength * arrow2Dir) - (perpX * arrowWidth),
      y: dimensionEnd.y + (dirY * arrowLength * arrow2Dir) - (perpY * arrowWidth)
    }
  };

  const label = {
    x: (dimensionStart.x + dimensionEnd.x) / 2,
    y: (dimensionStart.y + dimensionEnd.y) / 2
  };

  return {
    rings: [screenStart, screenEnd],
    witnesses: [
      [witnessStartA, witnessEndA],
      [witnessStartB, witnessEndB]
    ],
    dimensionLine: [dimensionStart, dimensionEnd],
    arrows: [arrow1, arrow2],
    ticks: [
      [
        { x: dimensionStart.x - dirX * 3, y: dimensionStart.y - dirY * 3 },
        { x: dimensionStart.x + dirX * 3, y: dimensionStart.y + dirY * 3 }
      ],
      [
        { x: dimensionEnd.x - dirX * 3, y: dimensionEnd.y - dirY * 3 },
        { x: dimensionEnd.x + dirX * 3, y: dimensionEnd.y + dirY * 3 }
      ]
    ],
    label
  };
}

/**
 * Projects a world-space dimension construction into device-pixel client space
 * for canvas drawing. Returns null when any construction point is behind the
 * camera or otherwise unprojectable.
 */
export function screenDimensionLayout(segments, camera, rect) {
  if (!segments) {
    return null;
  }
  const project = (point) => projectWorldPointToClient(point, camera, rect);
  const start = project(segments.start);
  const end = project(segments.end);
  const witnessStart = project(segments.witnessStart);
  const witnessEnd = project(segments.witnessEnd);
  const label = project(segments.labelPoint);
  if (!start || !end || !witnessStart || !witnessEnd || !label) {
    return null;
  }
  const ticks = [];
  for (const [tickStart, tickEnd] of segments.ticks || []) {
    const a = project(tickStart);
    const b = project(tickEnd);
    if (!a || !b) {
      return null;
    }
    ticks.push([a, b]);
  }
  return {
    rings: [start, end],
    witnesses: [
      [start, witnessStart],
      [end, witnessEnd]
    ],
    dimensionLine: [witnessStart, witnessEnd],
    ticks,
    label
  };
}

function strokeSegment(context, start, end) {
  context.beginPath();
  context.moveTo(start.x, start.y);
  context.lineTo(end.x, end.y);
  context.stroke();
}

export function drawMeasureDimension(context, layout, {
  color = MEASURE_DIMENSION_COMMITTED_COLOR,
  alpha = 1,
  lineWidth = 2.2,
  witnessWidth = 1.6,
  tickWidth = 2.6,
  ringRadius = 3.75,
  ringStrokeWidth = 2,
  label = "",
  labelColor = "#ffffff",
  labelBackground = MEASURE_DIMENSION_LABEL_BACKGROUND,
  bounds = null
} = {}) {
  if (!context || !layout) {
    return;
  }
  context.save();
  context.globalAlpha = Math.max(0, Math.min(1, Number(alpha) || 1));
  context.strokeStyle = color;
  context.lineCap = "round";
  context.lineJoin = "round";

  for (const [start, end] of layout.witnesses) {
    context.lineWidth = witnessWidth;
    strokeSegment(context, start, end);
  }

  const [dimensionStart, dimensionEnd] = layout.dimensionLine;
  context.lineWidth = lineWidth;
  strokeSegment(context, dimensionStart, dimensionEnd);

  if (Array.isArray(layout.arrows) && layout.arrows.length) {
    context.fillStyle = color;
    for (const arrow of layout.arrows) {
      if (arrow?.tip && arrow?.left && arrow?.right) {
        context.beginPath();
        context.moveTo(arrow.tip.x, arrow.tip.y);
        context.lineTo(arrow.left.x, arrow.left.y);
        context.lineTo(arrow.right.x, arrow.right.y);
        context.closePath();
        context.fill();
      }
    }
  } else if (Array.isArray(layout.ticks)) {
    for (const [tickStart, tickEnd] of layout.ticks) {
      context.lineWidth = tickWidth;
      strokeSegment(context, tickStart, tickEnd);
    }
  }

  for (const point of layout.rings) {
    context.beginPath();
    context.arc(point.x, point.y, ringRadius, 0, Math.PI * 2);
    context.fillStyle = "#ffffff";
    context.fill();
    context.lineWidth = ringStrokeWidth;
    context.strokeStyle = color;
    context.stroke();
  }

  const labelText = String(label || "").trim();
  if (labelText) {
    context.font = MEASURE_DIMENSION_LABEL_FONT;
    const textWidth = context.measureText(labelText).width;
    const paddingX = LABEL_PADDING_X;
    const paddingY = LABEL_PADDING_Y;
    const chipWidth = textWidth + (paddingX * 2);
    const chipHeight = 11 + (paddingY * 2);
    let chipX = layout.label.x - (chipWidth / 2);
    let chipY = layout.label.y - (chipHeight / 2);
    if (bounds && Number(bounds.width) > 0 && Number(bounds.height) > 0) {
      const minX = LABEL_MIN_MARGIN;
      const maxX = Math.max(minX, Number(bounds.width) - chipWidth - LABEL_MIN_MARGIN);
      const minY = LABEL_MIN_MARGIN;
      const maxY = Math.max(minY, Number(bounds.height) - chipHeight - LABEL_MIN_MARGIN);
      chipX = Math.min(Math.max(chipX, minX), maxX);
      chipY = Math.min(Math.max(chipY, minY), maxY);
    }
    const radius = 5;
    context.beginPath();
    if (typeof context.roundRect === "function") {
      context.roundRect(chipX, chipY, chipWidth, chipHeight, radius);
    } else {
      context.rect(chipX, chipY, chipWidth, chipHeight);
    }
    context.fillStyle = labelBackground;
    context.fill();
    context.strokeStyle = color;
    context.lineWidth = 1;
    context.stroke();

    context.fillStyle = labelColor;
    context.textBaseline = "middle";
    context.textAlign = "center";
    context.fillText(labelText, chipX + (chipWidth / 2), chipY + (chipHeight / 2));
  }

  context.restore();
}

export function drawPulsingEndRing(context, point, {
  now = null,
  color = MEASURE_DIMENSION_DRAFT_COLOR,
  baseRadius = 4.5,
  periodMs = 1000,
  amplitude = 1.2
} = {}) {
  if (!context || !point) {
    return;
  }
  const readoutNow = Number.isFinite(now)
    ? now
    : typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();
  const pulseRadius = baseRadius + 2 +
    Math.abs(Math.sin(readoutNow / periodMs)) * amplitude;
  context.save();
  context.globalAlpha = 0.35;
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.beginPath();
  context.arc(point.x, point.y, pulseRadius, 0, Math.PI * 2);
  context.stroke();
  context.globalAlpha = 1;
  context.fillStyle = "#ffffff";
  context.beginPath();
  context.arc(point.x, point.y, baseRadius, 0, Math.PI * 2);
  context.fill();
  context.lineWidth = 2;
  context.strokeStyle = color;
  context.stroke();
  context.restore();
}

export const MEASURE_SNAP_COLOR = "#f59e0b";
export const MEASURE_SNAP_FREE_COLOR = "#94a3b8";

/**
 * Where the next click would actually land, and what it would bind to. Without
 * this the tool gives no sign that a click is about to snap to an edge rather
 * than to the surface under the cursor, and the two produce different numbers.
 *
 * The marker is shaped by snap kind rather than only coloured, so it survives
 * both themes and reads without a legend: a square corner is a vertex, a ring is
 * an edge, a hollow diamond is a face, and a bare cross is an unsnapped point on
 * the mesh.
 */
export function drawMeasureSnapMarker(context, point, { snapKind = "free", now = null } = {}) {
  if (!context || !point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
    return;
  }
  const snapped = snapKind === "vertex" || snapKind === "edge" || snapKind === "face";
  const color = snapped ? MEASURE_SNAP_COLOR : MEASURE_SNAP_FREE_COLOR;
  const { x, y } = point;

  context.save();
  context.lineWidth = 1.6;
  context.strokeStyle = color;
  context.fillStyle = color;

  // A crosshair under every marker keeps the exact point readable even where the
  // marker sits against a busy edge.
  context.globalAlpha = snapped ? 0.9 : 0.7;
  context.beginPath();
  context.moveTo(x - 7, y);
  context.lineTo(x - 2.5, y);
  context.moveTo(x + 2.5, y);
  context.lineTo(x + 7, y);
  context.moveTo(x, y - 7);
  context.lineTo(x, y - 2.5);
  context.moveTo(x, y + 2.5);
  context.lineTo(x, y + 7);
  context.stroke();

  context.globalAlpha = 1;
  if (snapKind === "vertex") {
    context.beginPath();
    context.rect(x - 3.5, y - 3.5, 7, 7);
    context.fill();
  } else if (snapKind === "edge") {
    // Pulses so a snap that engages under a stationary cursor is still noticed.
    const phase = Number.isFinite(now) ? (Math.sin((now / 500) * Math.PI) + 1) / 2 : 0.5;
    context.beginPath();
    context.arc(x, y, 3.6 + (phase * 0.8), 0, Math.PI * 2);
    context.fill();
  } else if (snapKind === "face") {
    context.beginPath();
    context.moveTo(x, y - 4.2);
    context.lineTo(x + 4.2, y);
    context.lineTo(x, y + 4.2);
    context.lineTo(x - 4.2, y);
    context.closePath();
    context.stroke();
  }
  context.restore();
}

/**
 * A short caption pinned beside the cursor. The docked panel already carries the
 * same words, but it is across the viewport from where the user is looking.
 */
export function drawMeasureSnapChip(context, point, text, {
  bounds = null,
  color = MEASURE_SNAP_COLOR,
  background = MEASURE_DIMENSION_LABEL_BACKGROUND,
  labelColor = "#f8fafc"
} = {}) {
  if (!context || !point || !text) {
    return;
  }
  context.save();
  context.font = MEASURE_DIMENSION_LABEL_FONT;
  const width = context.measureText(text).width + 14;
  const height = 20;
  let x = point.x + 14;
  let y = point.y - height - 10;
  if (bounds) {
    x = Math.min(Math.max(x, 4), Math.max(4, bounds.width - width - 4));
    y = Math.min(Math.max(y, 4), Math.max(4, bounds.height - height - 4));
  }
  context.beginPath();
  if (typeof context.roundRect === "function") {
    context.roundRect(x, y, width, height, 5);
  } else {
    context.rect(x, y, width, height);
  }
  context.fillStyle = background;
  context.fill();
  context.strokeStyle = color;
  context.lineWidth = 1;
  context.stroke();
  context.fillStyle = labelColor;
  context.textBaseline = "middle";
  context.textAlign = "left";
  context.fillText(text, x + 7, y + (height / 2));
  context.restore();
}

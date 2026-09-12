import { DRAWING_TOOL } from "./drawingTools.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function distancePointToSegment2d(point, start, end) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
    return Math.hypot(point[0] - start[0], point[1] - start[1]);
  }
  const t = clamp(
    ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy),
    0,
    1
  );
  const projected = [start[0] + dx * t, start[1] + dy * t];
  return Math.hypot(point[0] - projected[0], point[1] - projected[1]);
}

export function pointInPolygon2d(point, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const a = polygon[index];
    const b = polygon[previous];
    if (distancePointToSegment2d(point, a, b) <= 1e-4) {
      return true;
    }
    const intersects =
      (a[1] > point[1]) !== (b[1] > point[1]) &&
      point[0] < ((b[0] - a[0]) * (point[1] - a[1])) / (b[1] - a[1] || 1e-9) + a[0];
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

export function buildDrawingPoint(event, canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = rect.width || 1;
  const height = rect.height || 1;
  return {
    x: clamp((event.clientX - rect.left) / width, 0, 1),
    y: clamp((event.clientY - rect.top) / height, 0, 1)
  };
}

export function drawingPointToPixels(point, width, height) {
  return [point.x * width, point.y * height];
}

export function strokeLengthInPixels(stroke, width, height) {
  const points = Array.isArray(stroke?.points) ? stroke.points : [];
  if (points.length < 2) {
    return 0;
  }
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const previous = drawingPointToPixels(points[index - 1], width, height);
    const current = drawingPointToPixels(points[index], width, height);
    total += Math.hypot(current[0] - previous[0], current[1] - previous[1]);
  }
  return total;
}

export function getDrawingStrokePoints(stroke) {
  return Array.isArray(stroke?.points)
    ? stroke.points.filter((point) => point && Number.isFinite(point.x) && Number.isFinite(point.y))
    : [];
}

export function getFillStrokePoints(stroke) {
  return Array.isArray(stroke?.fillPoints)
    ? stroke.fillPoints.filter((point) => point && Number.isFinite(point.x) && Number.isFinite(point.y))
    : [];
}

export function isFillStroke(stroke) {
  return stroke?.tool === DRAWING_TOOL.FILL;
}

export function isSurfaceLineStroke(stroke) {
  return stroke?.tool === DRAWING_TOOL.SURFACE_LINE && !!stroke?.surfaceLine;
}

export function isClosedDrawingStroke(stroke) {
  return stroke?.tool === DRAWING_TOOL.RECTANGLE || stroke?.tool === DRAWING_TOOL.CIRCLE;
}

export function isFillBoundaryStroke(stroke) {
  return !!stroke && stroke.tool !== DRAWING_TOOL.ERASE && stroke.tool !== DRAWING_TOOL.FILL && stroke.tool !== DRAWING_TOOL.SURFACE_LINE;
}

export function drawingToolNeedsTwoPoints(tool) {
  return (
    tool === DRAWING_TOOL.LINE ||
    tool === DRAWING_TOOL.SURFACE_LINE ||
    tool === DRAWING_TOOL.ARROW ||
    tool === DRAWING_TOOL.DOUBLE_ARROW ||
    tool === DRAWING_TOOL.RECTANGLE ||
    tool === DRAWING_TOOL.CIRCLE
  );
}

export function distanceToStrokeInPixels(point, stroke, width, height) {
  if (isFillStroke(stroke)) {
    const pixelPoint = drawingPointToPixels(point, width, height);
    const polygon = getFillStrokePoints(stroke).map((entry) => drawingPointToPixels(entry, width, height));
    if (polygon.length < 3) {
      return Infinity;
    }
    if (pointInPolygon2d(pixelPoint, polygon)) {
      return 0;
    }
    let minimum = Infinity;
    for (let index = 0; index < polygon.length; index += 1) {
      const start = polygon[index];
      const end = polygon[(index + 1) % polygon.length];
      minimum = Math.min(minimum, distancePointToSegment2d(pixelPoint, start, end));
    }
    return minimum;
  }

  const points = getDrawingStrokePoints(stroke);
  if (!points.length) {
    return Infinity;
  }
  const pixelPoint = drawingPointToPixels(point, width, height);
  const pixelPoints = points.map((entry) => drawingPointToPixels(entry, width, height));
  if (pixelPoints.length === 1) {
    const pointPixels = pixelPoints[0];
    return Math.hypot(pixelPoint[0] - pointPixels[0], pixelPoint[1] - pointPixels[1]);
  }

  if (stroke.tool === DRAWING_TOOL.RECTANGLE) {
    const start = pixelPoints[0];
    const end = pixelPoints[pixelPoints.length - 1];
    const corners = [
      [start[0], start[1]],
      [end[0], start[1]],
      [end[0], end[1]],
      [start[0], end[1]]
    ];
    let minimum = Infinity;
    for (let index = 0; index < corners.length; index += 1) {
      const a = corners[index];
      const b = corners[(index + 1) % corners.length];
      minimum = Math.min(minimum, distancePointToSegment2d(pixelPoint, a, b));
    }
    return minimum;
  }

  if (stroke.tool === DRAWING_TOOL.CIRCLE) {
    const center = pixelPoints[0];
    const edge = pixelPoints[pixelPoints.length - 1];
    const radius = Math.hypot(edge[0] - center[0], edge[1] - center[1]);
    return Math.abs(Math.hypot(pixelPoint[0] - center[0], pixelPoint[1] - center[1]) - radius);
  }

  let minimum = Infinity;
  for (let index = 1; index < pixelPoints.length; index += 1) {
    const start = pixelPoints[index - 1];
    const end = pixelPoints[index];
    minimum = Math.min(minimum, distancePointToSegment2d(pixelPoint, start, end));
  }
  return minimum;
}

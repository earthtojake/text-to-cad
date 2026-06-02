const DXF_RENDER_SCHEMA_VERSION = 1;
const SUPPORTED_ENTITY_TYPES = new Set(["LINE", "ARC", "CIRCLE", "LWPOLYLINE"]);
const ANGLE_EPSILON = 1e-9;

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function semanticKindForLayer(layerName) {
  return String(layerName || "").trim().toLowerCase().includes("bend") ? "bend" : "cut";
}

function normalizeLayerName(value) {
  const text = String(value || "").trim();
  return text || "0";
}

function normalizeAngle(angleDeg) {
  const value = angleDeg % 360;
  return value < 0 ? value + 360 : value;
}

function angleInCcwSweep(angleDeg, startAngleDeg, sweepAngleDeg) {
  if (sweepAngleDeg >= 360 - ANGLE_EPSILON) {
    return true;
  }
  const normalizedDelta = (normalizeAngle(angleDeg) - normalizeAngle(startAngleDeg) + 360) % 360;
  return normalizedDelta <= sweepAngleDeg + ANGLE_EPSILON;
}

function pointOnCircle(center, radius, angleDeg) {
  const radians = (angleDeg * Math.PI) / 180;
  return [
    center[0] + radius * Math.cos(radians),
    center[1] + radius * Math.sin(radians)
  ];
}

function angleDegForPoint(center, point) {
  return normalizeAngle((Math.atan2(point[1] - center[1], point[0] - center[0]) * 180) / Math.PI);
}

function arcExtremaPoints(arc) {
  const points = [
    pointOnCircle(arc.center, arc.radius, arc.startAngleDeg),
    pointOnCircle(arc.center, arc.radius, arc.endAngleDeg)
  ];
  for (const candidateAngle of [0, 90, 180, 270]) {
    if (angleInCcwSweep(candidateAngle, arc.startAngleDeg, arc.sweepAngleDeg)) {
      points.push(pointOnCircle(arc.center, arc.radius, candidateAngle));
    }
  }
  return points;
}

function expandBounds(current, nextBounds) {
  if (!current) {
    return nextBounds;
  }
  return {
    minX: Math.min(current.minX, nextBounds.minX),
    minY: Math.min(current.minY, nextBounds.minY),
    maxX: Math.max(current.maxX, nextBounds.maxX),
    maxY: Math.max(current.maxY, nextBounds.maxY)
  };
}

function lineBounds(line) {
  return {
    minX: Math.min(line.start[0], line.end[0]),
    minY: Math.min(line.start[1], line.end[1]),
    maxX: Math.max(line.start[0], line.end[0]),
    maxY: Math.max(line.start[1], line.end[1])
  };
}

function circleBounds(circle) {
  return {
    minX: circle.center[0] - circle.radius,
    minY: circle.center[1] - circle.radius,
    maxX: circle.center[0] + circle.radius,
    maxY: circle.center[1] + circle.radius
  };
}

function arcBounds(arc) {
  const points = arcExtremaPoints(arc);
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys)
  };
}

function screenPoint(point, { minX, maxY }) {
  return [point[0] - minX, maxY - point[1]];
}

function formatNumber(value) {
  const rounded = Math.round(toFiniteNumber(value) * 1_000_000) / 1_000_000;
  return Math.abs(rounded) < ANGLE_EPSILON ? 0 : rounded;
}

function parseRecordPairs(text) {
  const normalized = String(text || "").replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");
  if (lines.length && lines[lines.length - 1] === "") {
    lines.pop();
  }
  if (lines.length % 2 !== 0) {
    throw new Error("DXF group code stream is malformed");
  }
  const pairs = [];
  for (let index = 0; index < lines.length; index += 2) {
    const code = Number.parseInt(lines[index].trim(), 10);
    if (!Number.isFinite(code)) {
      throw new Error(`Invalid DXF group code: ${JSON.stringify(lines[index])}`);
    }
    pairs.push({
      code,
      value: lines[index + 1] ?? ""
    });
  }
  return pairs;
}

function parseHeader(records) {
  let sourceUnits = 0;
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    if (record.code !== 9) {
      continue;
    }
    const variableName = String(record.value || "").trim();
    const valueRecord = records[index + 1];
    if (!valueRecord) {
      continue;
    }
    if (variableName === "$INSUNITS") {
      sourceUnits = Math.max(0, Math.trunc(toFiniteNumber(valueRecord.value, 0)));
    }
  }
  return {
    sourceUnits,
    defaultThicknessMm: 0
  };
}

function parseLineEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const startX = toFiniteNumber(records.find((record) => record.code === 10)?.value);
  const startY = toFiniteNumber(records.find((record) => record.code === 20)?.value);
  const endX = toFiniteNumber(records.find((record) => record.code === 11)?.value);
  const endY = toFiniteNumber(records.find((record) => record.code === 21)?.value);
  return {
    layer,
    start: [startX, startY],
    end: [endX, endY]
  };
}

function parseArcEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const radius = toFiniteNumber(records.find((record) => record.code === 40)?.value, -1);
  if (radius <= 0) {
    throw new Error("Invalid DXF arc radius");
  }
  const startAngleDeg = normalizeAngle(toFiniteNumber(records.find((record) => record.code === 50)?.value));
  const endAngleDeg = normalizeAngle(toFiniteNumber(records.find((record) => record.code === 51)?.value));
  let sweepAngleDeg = (endAngleDeg - startAngleDeg + 360) % 360;
  if (sweepAngleDeg <= ANGLE_EPSILON) {
    sweepAngleDeg = 360;
  }
  return {
    layer,
    center: [
      toFiniteNumber(records.find((record) => record.code === 10)?.value),
      toFiniteNumber(records.find((record) => record.code === 20)?.value)
    ],
    radius,
    startAngleDeg,
    sweepAngleDeg,
    endAngleDeg: startAngleDeg + sweepAngleDeg
  };
}

function parseCircleEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const radius = toFiniteNumber(records.find((record) => record.code === 40)?.value, -1);
  if (radius <= 0) {
    throw new Error("Invalid DXF circle radius");
  }
  return {
    layer,
    center: [
      toFiniteNumber(records.find((record) => record.code === 10)?.value),
      toFiniteNumber(records.find((record) => record.code === 20)?.value)
    ],
    radius
  };
}

function bulgeArcFromSegment(layer, start, end, bulge) {
  if (Math.abs(bulge) <= ANGLE_EPSILON) {
    return null;
  }
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const chordLength = Math.hypot(dx, dy);
  if (chordLength <= ANGLE_EPSILON) {
    return null;
  }
  const sweepRadians = Math.abs(4 * Math.atan(bulge));
  if (sweepRadians <= ANGLE_EPSILON) {
    return null;
  }
  const radius = (chordLength * (1 + bulge * bulge)) / (4 * Math.abs(bulge));
  const midpoint = [
    (start[0] + end[0]) / 2,
    (start[1] + end[1]) / 2
  ];
  const leftNormal = [
    -dy / chordLength,
    dx / chordLength
  ];
  const centerOffset = (chordLength * (1 - bulge * bulge)) / (4 * bulge);
  const center = [
    midpoint[0] + leftNormal[0] * centerOffset,
    midpoint[1] + leftNormal[1] * centerOffset
  ];
  const startPoint = bulge > 0 ? start : end;
  const startAngleDeg = angleDegForPoint(center, startPoint);
  const sweepAngleDeg = (sweepRadians * 180) / Math.PI;
  return {
    layer,
    center,
    radius,
    startAngleDeg,
    sweepAngleDeg,
    endAngleDeg: startAngleDeg + sweepAngleDeg
  };
}

function appendLwpolylineSegment(result, layer, startVertex, endVertex) {
  const start = startVertex.point;
  const end = endVertex.point;
  if (start[0] === end[0] && start[1] === end[1]) {
    return;
  }
  const arc = bulgeArcFromSegment(layer, start, end, startVertex.bulge);
  if (arc) {
    result.arcs.push(arc);
    return;
  }
  result.lines.push({ layer, start, end });
}

function parseLwpolylineEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const flags = Math.trunc(toFiniteNumber(records.find((record) => record.code === 70)?.value, 0));
  const vertices = [];
  let currentVertex = null;
  for (const record of records) {
    if (record.code === 10) {
      if (currentVertex && Number.isFinite(currentVertex.point[0]) && Number.isFinite(currentVertex.point[1])) {
        vertices.push(currentVertex);
      }
      currentVertex = { point: [toFiniteNumber(record.value), Number.NaN], bulge: 0 };
      continue;
    }
    if (record.code === 20 && currentVertex) {
      currentVertex.point[1] = toFiniteNumber(record.value);
      continue;
    }
    if (record.code === 42 && currentVertex) {
      currentVertex.bulge = toFiniteNumber(record.value);
    }
  }
  if (currentVertex && Number.isFinite(currentVertex.point[0]) && Number.isFinite(currentVertex.point[1])) {
    vertices.push(currentVertex);
  }
  if (vertices.length < 2) {
    throw new Error("Invalid DXF LWPOLYLINE; expected at least 2 vertices");
  }
  const result = {
    lines: [],
    arcs: []
  };
  for (let index = 0; index < vertices.length - 1; index += 1) {
    appendLwpolylineSegment(result, layer, vertices[index], vertices[index + 1]);
  }
  if ((flags & 1) !== 0) {
    appendLwpolylineSegment(result, layer, vertices[vertices.length - 1], vertices[0]);
  }
  return result;
}

function parseEntities(records) {
  const lines = [];
  const arcs = [];
  const circles = [];
  let index = 0;
  while (index < records.length) {
    const startRecord = records[index];
    if (startRecord.code !== 0) {
      index += 1;
      continue;
    }
    const entityType = String(startRecord.value || "").trim().toUpperCase();
    if (entityType === "ENDSEC") {
      break;
    }
    const entityRecords = [];
    index += 1;
    while (index < records.length && records[index].code !== 0) {
      entityRecords.push(records[index]);
      index += 1;
    }
    if (!SUPPORTED_ENTITY_TYPES.has(entityType)) {
      throw new Error(`Unsupported DXF entity ${entityType}`);
    }
    if (entityType === "LINE") {
      lines.push(parseLineEntity(entityRecords));
      continue;
    }
    if (entityType === "ARC") {
      arcs.push(parseArcEntity(entityRecords));
      continue;
    }
    if (entityType === "CIRCLE") {
      circles.push(parseCircleEntity(entityRecords));
      continue;
    }
    const polyline = parseLwpolylineEntity(entityRecords);
    lines.push(...polyline.lines);
    arcs.push(...polyline.arcs);
  }
  if (!lines.length && !arcs.length && !circles.length) {
    throw new Error("No supported DXF entities found");
  }
  return { lines, arcs, circles };
}

function splitSections(records) {
  const sections = new Map();
  let index = 0;
  while (index < records.length) {
    const record = records[index];
    if (record.code !== 0 || String(record.value || "").trim().toUpperCase() !== "SECTION") {
      index += 1;
      continue;
    }
    const nameRecord = records[index + 1];
    const sectionName = String(nameRecord?.value || "").trim().toUpperCase();
    index += 2;
    const sectionRecords = [];
    while (index < records.length) {
      const nextRecord = records[index];
      if (nextRecord.code === 0 && String(nextRecord.value || "").trim().toUpperCase() === "ENDSEC") {
        index += 1;
        break;
      }
      sectionRecords.push(nextRecord);
      index += 1;
    }
    sections.set(sectionName, sectionRecords);
  }
  return sections;
}

function buildPathRecord(layerName, kind, pathData) {
  return {
    layer: layerName,
    kind,
    d: pathData
  };
}

function touchLayer(layerSummary, layerName) {
  const existing = layerSummary.get(layerName);
  if (existing) {
    return existing;
  }
  const next = {
    name: layerName,
    kind: semanticKindForLayer(layerName),
    pathCount: 0,
    circleCount: 0
  };
  layerSummary.set(layerName, next);
  return next;
}

export function parseDxf(dxfText, { fileRef = "", sourceUrl = "" } = {}) {
  const records = parseRecordPairs(dxfText);
  const sections = splitSections(records);
  const header = parseHeader(sections.get("HEADER") || []);
  const entities = parseEntities(sections.get("ENTITIES") || []);

  let rawBounds = null;
  for (const line of entities.lines) {
    rawBounds = expandBounds(rawBounds, lineBounds(line));
  }
  for (const arc of entities.arcs) {
    rawBounds = expandBounds(rawBounds, arcBounds(arc));
  }
  for (const circle of entities.circles) {
    rawBounds = expandBounds(rawBounds, circleBounds(circle));
  }
  if (!rawBounds) {
    throw new Error("Failed to compute DXF bounds");
  }

  const width = Math.max(rawBounds.maxX - rawBounds.minX, 0);
  const height = Math.max(rawBounds.maxY - rawBounds.minY, 0);
  const pathRecords = [];
  const circleRecords = [];
  const layerSummary = new Map();

  for (const line of entities.lines) {
    const start = screenPoint(line.start, { minX: rawBounds.minX, maxY: rawBounds.maxY });
    const end = screenPoint(line.end, { minX: rawBounds.minX, maxY: rawBounds.maxY });
    pathRecords.push(
      buildPathRecord(
        line.layer,
        semanticKindForLayer(line.layer),
        `M ${formatNumber(start[0])} ${formatNumber(start[1])} L ${formatNumber(end[0])} ${formatNumber(end[1])}`
      )
    );
    touchLayer(layerSummary, line.layer).pathCount += 1;
  }

  for (const arc of entities.arcs) {
    const start = screenPoint(pointOnCircle(arc.center, arc.radius, arc.startAngleDeg), {
      minX: rawBounds.minX,
      maxY: rawBounds.maxY
    });
    const end = screenPoint(pointOnCircle(arc.center, arc.radius, arc.endAngleDeg), {
      minX: rawBounds.minX,
      maxY: rawBounds.maxY
    });
    const largeArcFlag = arc.sweepAngleDeg > 180 + ANGLE_EPSILON ? 1 : 0;
    pathRecords.push(
      buildPathRecord(
        arc.layer,
        semanticKindForLayer(arc.layer),
        `M ${formatNumber(start[0])} ${formatNumber(start[1])} A ${formatNumber(arc.radius)} ${formatNumber(arc.radius)} 0 ${largeArcFlag} 1 ${formatNumber(end[0])} ${formatNumber(end[1])}`
      )
    );
    touchLayer(layerSummary, arc.layer).pathCount += 1;
  }

  for (const circle of entities.circles) {
    const center = screenPoint(circle.center, { minX: rawBounds.minX, maxY: rawBounds.maxY });
    circleRecords.push({
      layer: circle.layer,
      kind: semanticKindForLayer(circle.layer),
      cx: formatNumber(center[0]),
      cy: formatNumber(center[1]),
      r: formatNumber(circle.radius)
    });
    touchLayer(layerSummary, circle.layer).circleCount += 1;
  }

  return {
    schemaVersion: DXF_RENDER_SCHEMA_VERSION,
    fileRef,
    sourceUrl,
    sourceUnits: header.sourceUnits,
    defaultThicknessMm: formatNumber(header.defaultThicknessMm),
    bounds: {
      minX: 0,
      minY: 0,
      maxX: formatNumber(width),
      maxY: formatNumber(height),
      width: formatNumber(width),
      height: formatNumber(height)
    },
    counts: {
      paths: pathRecords.length,
      circles: circleRecords.length,
      entities: pathRecords.length + circleRecords.length
    },
    layers: [...layerSummary.keys()].sort().map((name) => layerSummary.get(name)),
    geometry: {
      lines: entities.lines.map((line) => ({
        layer: line.layer,
        kind: semanticKindForLayer(line.layer),
        start: [formatNumber(line.start[0]), formatNumber(line.start[1])],
        end: [formatNumber(line.end[0]), formatNumber(line.end[1])]
      })),
      arcs: entities.arcs.map((arc) => ({
        layer: arc.layer,
        kind: semanticKindForLayer(arc.layer),
        center: [formatNumber(arc.center[0]), formatNumber(arc.center[1])],
        radius: formatNumber(arc.radius),
        startAngleDeg: formatNumber(arc.startAngleDeg),
        sweepAngleDeg: formatNumber(arc.sweepAngleDeg)
      })),
      circles: entities.circles.map((circle) => ({
        layer: circle.layer,
        kind: semanticKindForLayer(circle.layer),
        center: [formatNumber(circle.center[0]), formatNumber(circle.center[1])],
        radius: formatNumber(circle.radius)
      }))
    },
    paths: pathRecords,
    circles: circleRecords
  };
}

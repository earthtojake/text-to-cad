/** How deep an INSERT chain may nest before we call it a cycle. */
const MAX_BLOCK_NESTING = 16;
const ANGLE_EPSILON = 1e-9;

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

// Layer intent by WHOLE tokens of the layer name (split on non-alphanumerics),
// mirroring cadgen.drawing_checks.layer_intent so validation, snapshots, and
// rendering classify layers identically ("PREFORM" must not match "ref").
const LAYER_INTENT_BY_TOKEN = new Map([
  ["cut", "cut"],
  ["profile", "cut"],
  ["bend", "bend"],
  ["fold", "bend"],
  ["engrave", "engrave"],
  ["etch", "engrave"],
  ["ref", "reference"],
  ["reference", "reference"],
  ["note", "reference"],
  ["notes", "reference"],
  ["annotation", "reference"],
  ["construction", "reference"],
  ["dim", "reference"],
  ["dims", "reference"],
  ["dimension", "reference"],
  ["dimensions", "reference"],
  ["section", "reference"],
  ["sections", "reference"],
  ["hidden", "reference"],
  ["center", "reference"],
  ["centre", "reference"],
  ["centerline", "reference"],
  ["centreline", "reference"],
  ["phantom", "reference"],
  ["title", "reference"],
  ["titleblock", "reference"],
  ["border", "reference"],
  ["frame", "reference"],
  ["viewport", "reference"],
  ["hatch", "reference"],
  ["text", "reference"],
  ["label", "reference"],
  ["labels", "reference"],
  ["leader", "reference"],
  ["axis", "reference"]
]);

function semanticKindForLayer(layerName) {
  const tokens = String(layerName || "").trim().toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  for (const intent of ["cut", "bend", "engrave", "reference"]) {
    if (tokens.some((token) => LAYER_INTENT_BY_TOKEN.get(token) === intent)) {
      return intent;
    }
  }
  return "cut";
}

function normalizeLayerName(value) {
  const text = String(value || "").trim();
  return text || "0";
}

function normalizeAngle(angleDeg) {
  const value = angleDeg % 360;
  return value < 0 ? value + 360 : value;
}

function angleInSweep(angleDeg, startAngleDeg, sweepAngleDeg) {
  const absSweepAngleDeg = Math.abs(sweepAngleDeg);
  if (absSweepAngleDeg >= 360 - ANGLE_EPSILON) {
    return true;
  }
  if (sweepAngleDeg >= 0) {
    const normalizedDelta = (normalizeAngle(angleDeg) - normalizeAngle(startAngleDeg) + 360) % 360;
    return normalizedDelta <= absSweepAngleDeg + ANGLE_EPSILON;
  }
  const normalizedDelta = (normalizeAngle(startAngleDeg) - normalizeAngle(angleDeg) + 360) % 360;
  return normalizedDelta <= absSweepAngleDeg + ANGLE_EPSILON;
}

function pointOnCircle(center, radius, angleDeg) {
  const radians = (angleDeg * Math.PI) / 180;
  return [
    center[0] + radius * Math.cos(radians),
    center[1] + radius * Math.sin(radians)
  ];
}

function arcExtremaPoints(arc) {
  const endAngleDeg = arc.startAngleDeg + arc.sweepAngleDeg;
  const points = [
    pointOnCircle(arc.center, arc.radius, arc.startAngleDeg),
    pointOnCircle(arc.center, arc.radius, endAngleDeg)
  ];
  for (const candidateAngle of [0, 90, 180, 270]) {
    if (angleInSweep(candidateAngle, arc.startAngleDeg, arc.sweepAngleDeg)) {
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

/**
 * $INSUNITS -> millimetres per drawing unit. The whole downstream stack (mesher, viewer,
 * thickness sliders) is millimetre-denominated, so geometry is scaled to mm at parse time.
 * Unitless (0) is treated as mm — the de-facto convention for laser-cutter DXF — and codes
 * this table does not carry fall back to 1 rather than guessing.
 */
const INSUNITS_TO_MM = new Map([
  [0, 1], // unspecified: assume mm
  [1, 25.4], // inches
  [2, 304.8], // feet
  [4, 1], // millimetres
  [5, 10], // centimetres
  [6, 1000], // metres
  [7, 1_000_000], // kilometres
  [8, 0.0000254], // microinches
  [9, 0.0254], // mils
  [10, 914.4], // yards
  [13, 0.001], // microns
  [14, 100] // decimetres
]);

export function dxfUnitsScaleMm(sourceUnits) {
  return INSUNITS_TO_MM.get(Math.trunc(toFiniteNumber(sourceUnits, 0))) ?? 1;
}

/**
 * ACI (AutoCAD Color Index) -> hex. The standard palette's first nine plus the grayscale
 * band cover what real layer tables use; anything else falls back to a neutral so an exotic
 * index degrades to "no color", never to a crash.
 */
const ACI_BASE_COLORS = new Map([
  [1, "#ff3b30"], [2, "#ffd60a"], [3, "#34c759"], [4, "#32ade6"],
  [5, "#3a5cff"], [6, "#ff2ddf"], [7, "#e5e7eb"], [8, "#8e8e93"], [9, "#c7c7cc"]
]);

export function aciColorHex(aci) {
  const index = Math.trunc(toFiniteNumber(aci, 7));
  if (ACI_BASE_COLORS.has(index)) {
    return ACI_BASE_COLORS.get(index);
  }
  if (index >= 250 && index <= 255) {
    const level = Math.round(51 + ((index - 250) * (255 - 51)) / 5);
    const channel = level.toString(16).padStart(2, "0");
    return `#${channel}${channel}${channel}`;
  }
  return null;
}

/**
 * TABLES section -> layer name -> {aci}. A negative color code means the layer is switched
 * OFF in the authoring tool; the sign is preserved as `visibleDefault` so the viewer can
 * start the layer hidden the way the file says.
 */
function parseLayerTable(records) {
  const layers = new Map();
  let index = 0;
  while (index < records.length) {
    const record = records[index];
    if (record.code !== 0 || String(record.value || "").trim().toUpperCase() !== "LAYER") {
      index += 1;
      continue;
    }
    index += 1;
    const body = [];
    while (index < records.length && records[index].code !== 0) {
      body.push(records[index]);
      index += 1;
    }
    const name = normalizeLayerName(body.find((entry) => entry.code === 2)?.value);
    const colorValue = Math.trunc(toFiniteNumber(body.find((entry) => entry.code === 62)?.value, 7));
    // Code 6 is the linetype name (CONTINUOUS, HIDDEN, CENTER, ...); 370 the lineweight in
    // hundredths of a millimetre, negative for "by default / by layer / by block".
    const linetype = String(body.find((entry) => entry.code === 6)?.value || "").trim().toUpperCase() || "CONTINUOUS";
    const lineweightRaw = Math.trunc(toFiniteNumber(body.find((entry) => entry.code === 370)?.value, -3));
    layers.set(name, {
      aci: Math.abs(colorValue),
      visibleDefault: colorValue >= 0,
      linetype,
      lineweightMm: lineweightRaw > 0 ? lineweightRaw / 100 : null
    });
  }
  return layers;
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
    sweepAngleDeg
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

function arcFromBulgeSegment(layer, start, end, bulge) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const chordLength = Math.hypot(dx, dy);
  if (chordLength <= ANGLE_EPSILON || Math.abs(bulge) <= ANGLE_EPSILON) {
    return null;
  }

  const includedAngleRad = 4 * Math.atan(bulge);
  const radius = (chordLength * (1 + bulge * bulge)) / (4 * Math.abs(bulge));
  const midpoint = [
    (start[0] + end[0]) / 2,
    (start[1] + end[1]) / 2
  ];
  const leftNormal = [-dy / chordLength, dx / chordLength];
  const centerOffset = (chordLength * (1 - bulge * bulge)) / (4 * bulge);
  const center = [
    midpoint[0] + leftNormal[0] * centerOffset,
    midpoint[1] + leftNormal[1] * centerOffset
  ];
  return {
    layer,
    center,
    radius,
    startAngleDeg: normalizeAngle((Math.atan2(start[1] - center[1], start[0] - center[0]) * 180) / Math.PI),
    sweepAngleDeg: (includedAngleRad * 180) / Math.PI
  };
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
  const lines = [];
  const arcs = [];
  const addSegment = (startVertex, endVertex) => {
    const start = startVertex.point;
    const end = endVertex.point;
    if (start[0] === end[0] && start[1] === end[1]) {
      return;
    }
    if (Math.abs(startVertex.bulge) > ANGLE_EPSILON) {
      const arc = arcFromBulgeSegment(layer, start, end, startVertex.bulge);
      if (arc) {
        arcs.push(arc);
      }
      return;
    }
    lines.push({ layer, start, end });
  };
  for (let index = 0; index < vertices.length - 1; index += 1) {
    addSegment(vertices[index], vertices[index + 1]);
  }
  if ((flags & 1) !== 0) {
    addSegment(vertices[vertices.length - 1], vertices[0]);
  }
  return { lines, arcs };
}

// --- entity coverage beyond LINE/ARC/CIRCLE/LWPOLYLINE -------------------------------
//
// Everything below LOWERS a richer entity onto the three primitives the mesher understands
// (lines, arcs, circles). That keeps the flat-pattern mesher untouched: it still sees the
// same contour soup, and only the parser learns new ways of spelling a curve.
//
// Curves are sampled rather than kept parametric because the contour walk joins segments by
// coincident endpoints -- an exact ellipse would still have to be flattened before it could
// close a loop against a neighbouring line.

/** Segments used to approximate a full curve. A closed profile has to LOOK closed at the
 *  scale a laser cuts, and the mesher welds by exact endpoints, so this is uniform rather
 *  than adaptive: a shared vertex count is what lets two curves meet exactly. */
const CURVE_SAMPLE_SEGMENTS = 72;

function samplePolylinePoints(layer, points, { closed = false } = {}) {
  const lines = [];
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    if (start[0] === end[0] && start[1] === end[1]) {
      continue;
    }
    lines.push({ layer, start, end });
  }
  if (closed && points.length > 2) {
    const first = points[0];
    const last = points[points.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) {
      lines.push({ layer, start: last, end: first });
    }
  }
  return lines;
}

/** ELLIPSE: centre + major-axis VECTOR (codes 11/21, relative to the centre) + minor/major
 *  ratio, over a parameter range. The vector carries the rotation, so there is no separate
 *  angle to apply. */
function parseEllipseEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const cx = toFiniteNumber(records.find((record) => record.code === 10)?.value);
  const cy = toFiniteNumber(records.find((record) => record.code === 20)?.value);
  const mx = toFiniteNumber(records.find((record) => record.code === 11)?.value);
  const my = toFiniteNumber(records.find((record) => record.code === 21)?.value);
  const ratio = toFiniteNumber(records.find((record) => record.code === 40)?.value, 1);
  const start = toFiniteNumber(records.find((record) => record.code === 41)?.value, 0);
  const end = toFiniteNumber(records.find((record) => record.code === 42)?.value, Math.PI * 2);
  const major = Math.hypot(mx, my);
  if (!(major > 0) || !(ratio > 0)) {
    throw new Error("Invalid DXF ellipse axes");
  }
  const rotation = Math.atan2(my, mx);
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  const minor = major * ratio;
  const sweep = end - start;
  const closed = Math.abs(Math.abs(sweep) - Math.PI * 2) < 1e-6;
  const points = [];
  for (let step = 0; step <= CURVE_SAMPLE_SEGMENTS; step += 1) {
    const t = start + (sweep * step) / CURVE_SAMPLE_SEGMENTS;
    const ex = major * Math.cos(t);
    const ey = minor * Math.sin(t);
    points.push([cx + ex * cos - ey * sin, cy + ex * sin + ey * cos]);
  }
  if (closed) {
    points[points.length - 1] = [...points[0]];
  }
  return { lines: samplePolylinePoints(layer, points), arcs: [] };
}

/** SPLINE via de Boor. Fit points are preferred when present and no control points are: a
 *  spline saved with only fit points has no basis to evaluate, and interpolating them is
 *  what every CAD viewer does with it. */
function parseSplineEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const flags = Math.trunc(toFiniteNumber(records.find((record) => record.code === 70)?.value, 0));
  const degree = Math.max(1, Math.trunc(toFiniteNumber(records.find((record) => record.code === 71)?.value, 3)));
  const knots = records.filter((record) => record.code === 40).map((record) => toFiniteNumber(record.value));
  const control = [];
  const fit = [];
  let pending = null;
  let pendingFit = null;
  for (const record of records) {
    if (record.code === 10) {
      if (pending) control.push(pending);
      pending = [toFiniteNumber(record.value), 0];
    } else if (record.code === 20 && pending) {
      pending[1] = toFiniteNumber(record.value);
    } else if (record.code === 11) {
      if (pendingFit) fit.push(pendingFit);
      pendingFit = [toFiniteNumber(record.value), 0];
    } else if (record.code === 21 && pendingFit) {
      pendingFit[1] = toFiniteNumber(record.value);
    }
  }
  if (pending) control.push(pending);
  if (pendingFit) fit.push(pendingFit);

  const closed = (flags & 1) !== 0;
  if (control.length <= degree) {
    // Not enough control points for the declared degree; fall back to whatever polygon the
    // file does describe rather than refusing the drawing.
    const points = control.length >= 2 ? control : fit;
    if (points.length < 2) {
      throw new Error("Invalid DXF spline; expected at least 2 points");
    }
    return { lines: samplePolylinePoints(layer, points, { closed }), arcs: [] };
  }

  const order = degree + 1;
  const knotVector = knots.length >= control.length + order
    ? knots
    // A uniform clamped knot vector is the sane default when the file omits one.
    : Array.from({ length: control.length + order }, (_, index) => {
      if (index < order) return 0;
      if (index >= control.length) return control.length - degree;
      return index - degree;
    });

  const evaluate = (t) => {
    let span = degree;
    while (span < control.length - 1 && knotVector[span + 1] <= t) {
      span += 1;
    }
    const working = [];
    for (let index = 0; index <= degree; index += 1) {
      const point = control[span - degree + index] || control[control.length - 1];
      working.push([point[0], point[1]]);
    }
    for (let level = 1; level <= degree; level += 1) {
      for (let index = degree; index >= level; index -= 1) {
        const knotIndex = span - degree + index;
        const low = knotVector[knotIndex];
        const high = knotVector[knotIndex + order - level];
        const denominator = high - low;
        const alpha = denominator > 0 ? (t - low) / denominator : 0;
        working[index] = [
          working[index - 1][0] * (1 - alpha) + working[index][0] * alpha,
          working[index - 1][1] * (1 - alpha) + working[index][1] * alpha,
        ];
      }
    }
    return working[degree];
  };

  const tStart = knotVector[degree];
  const tEnd = knotVector[control.length];
  const points = [];
  for (let step = 0; step <= CURVE_SAMPLE_SEGMENTS; step += 1) {
    const t = tStart + ((tEnd - tStart) * step) / CURVE_SAMPLE_SEGMENTS;
    points.push(evaluate(Math.min(t, tEnd)));
  }
  return { lines: samplePolylinePoints(layer, points, { closed }), arcs: [] };
}

/** Legacy POLYLINE: the vertices are SEPARATE entities following it until SEQEND, unlike
 *  LWPOLYLINE which carries them inline. Bulges live on the vertex, same as LWPOLYLINE. */
function parsePolylineEntity(records, vertexGroups) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const flags = Math.trunc(toFiniteNumber(records.find((record) => record.code === 70)?.value, 0));
  const vertices = vertexGroups
    .map((group) => ({
      point: [
        toFiniteNumber(group.find((record) => record.code === 10)?.value),
        toFiniteNumber(group.find((record) => record.code === 20)?.value),
      ],
      bulge: toFiniteNumber(group.find((record) => record.code === 42)?.value, 0),
    }))
    .filter((vertex) => Number.isFinite(vertex.point[0]) && Number.isFinite(vertex.point[1]));
  if (vertices.length < 2) {
    throw new Error("Invalid DXF POLYLINE; expected at least 2 vertices");
  }
  const lines = [];
  const arcs = [];
  const addSegment = (startVertex, endVertex) => {
    const start = startVertex.point;
    const end = endVertex.point;
    if (start[0] === end[0] && start[1] === end[1]) {
      return;
    }
    if (Math.abs(startVertex.bulge) > ANGLE_EPSILON) {
      const arc = arcFromBulgeSegment(layer, start, end, startVertex.bulge);
      if (arc) {
        arcs.push(arc);
      }
      return;
    }
    lines.push({ layer, start, end });
  };
  for (let index = 0; index < vertices.length - 1; index += 1) {
    addSegment(vertices[index], vertices[index + 1]);
  }
  if ((flags & 1) !== 0) {
    addSegment(vertices[vertices.length - 1], vertices[0]);
  }
  return { lines, arcs };
}

/** A HATCH writes its boundary paths FIRST, then pattern-definition lines, then seed points,
 *  then optional gradient data. Code 75 (hatch style) opens that tail and code 98 counts the
 *  seed points -- and a seed point is written as another 10/20 pair. Reading to the end of the
 *  entity therefore appends the seed to the last boundary path, and a seed may sit ANYWHERE:
 *  in models/drawings/DXF/imported/alu_extrusion_profile.dxf one sits 62 m off a 1.8 m sheet, which inflated the
 *  drawing's bounds ~35x and left auto-fit framing the whole drawing as a speck. */
const HATCH_BOUNDARY_END_CODES = new Set([75, 98]);

/** HATCH boundary paths (codes 10/20 per path). A hatch is a FILL, and its boundary is the
 *  region outline -- exactly the closed contour a flat pattern wants. The pattern itself is
 *  decoration and is ignored: extruding hatch lines would produce hair, not a part. */
function parseHatchEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const lines = [];
  let points = [];
  const flush = () => {
    if (points.length >= 3) {
      lines.push(...samplePolylinePoints(layer, points, { closed: true }));
    }
    points = [];
  };
  for (const record of records) {
    if (HATCH_BOUNDARY_END_CODES.has(record.code)) {
      break;
    }
    // 92 opens a boundary path; 10/20 are its vertices. A new path flushes the previous one.
    if (record.code === 92) {
      flush();
      continue;
    }
    if (record.code === 10) {
      points.push([toFiniteNumber(record.value), Number.NaN]);
      continue;
    }
    if (record.code === 20 && points.length) {
      points[points.length - 1][1] = toFiniteNumber(record.value);
    }
  }
  flush();
  if (!lines.length) {
    throw new Error("Invalid DXF hatch; no boundary path");
  }
  return { lines, arcs: [] };
}

/** SOLID / TRACE: a filled triangle or quad, which is what an AutoCAD arrowhead is
 *  (`_CLOSEDFILLED` and friends are one SOLID each). Rendered as its outline. Corners are
 *  codes 10/20, 11/21, 12/22, 13/23; the format stores a quad as a bow-tie (1, 2, 4, 3),
 *  so the last two are swapped to walk the perimeter. A triangle repeats its third corner. */
function parseSolidEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const corner = (xCode, yCode) => {
    const x = records.find((record) => record.code === xCode);
    const y = records.find((record) => record.code === yCode);
    if (!x || !y) {
      return null;
    }
    return [toFiniteNumber(x.value), toFiniteNumber(y.value)];
  };
  const raw = [corner(10, 20), corner(11, 21), corner(13, 23), corner(12, 22)].filter(Boolean);
  const points = raw.filter((point, index) => {
    const previous = raw[index - 1];
    return !previous || previous[0] !== point[0] || previous[1] !== point[1];
  });
  if (points.length < 3) {
    return { lines: [], arcs: [], fills: [] };
  }
  // The outline serves the cut/engrave consumers; the fill is what a drawing shows.
  return { lines: samplePolylinePoints(layer, points, { closed: true }), arcs: [], fills: [{ layer, points }] };
}

/** LEADER: a polyline from the note to the feature, vertices as repeated 10/20 pairs. Its
 *  arrowhead is drawn by the file as a SOLID or an INSERT, not by the LEADER itself. */
function parseLeaderEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const points = [];
  for (const record of records) {
    if (record.code === 10) {
      points.push([toFiniteNumber(record.value), Number.NaN]);
    } else if (record.code === 20 && points.length) {
      points[points.length - 1][1] = toFiniteNumber(record.value);
    }
  }
  const usable = points.filter((point) => Number.isFinite(point[1]));
  return { lines: usable.length >= 2 ? samplePolylinePoints(layer, usable) : [], arcs: [] };
}

/** Entities that carry no cut geometry. Skipped rather than rejected: a drawing is not
 *  unrenderable because it is annotated, and refusing one over a dimension line is how a
 *  perfectly good profile ends up showing an error card. (TEXT/MTEXT/DIMENSION are no longer
 *  here — they parse into flat text markings the viewer engraves onto the sheet; SOLID, TRACE
 *  and LEADER are outlines, because arrowheads and leader lines are what a dimensioned
 *  drawing is made of.) */
const NON_GEOMETRIC_ENTITY_TYPES = new Set([
  "ATTRIB", "ATTDEF", "MLEADER", "MULTILEADER",
  "POINT", "VIEWPORT", "SEQEND", "TOLERANCE", "OLE2FRAME", "WIPEOUT", "IMAGE", "RAY", "XLINE",
  "ACAD_PROXY_ENTITY", "ACAD_TABLE", "BODY", "REGION", "SHAPE", "3DFACE",
  "HELIX", "MESH", "SPLINE_PROXY",
]);

// --- text markings --------------------------------------------------------------------
//
// TEXT/MTEXT/DIMENSION carry no cut geometry, but a laser workflow engraves them, so they
// are captured as flat MARKINGS: an anchor, a height, a rotation, and the string. Glyph
// outlines are deliberately NOT generated here — the viewer draws the string onto the sheet
// itself, which needs no font tables in the parser.

/** MTEXT strings carry inline formatting: {\fArial|b0;...}, \P paragraph breaks, %%
 *  escapes. Strip to the readable text the way every DXF viewer's tooltip does. */
export function stripMtextFormatting(raw) {
  let text = String(raw ?? "");
  // \P is a paragraph break, \~ a hard space; \\ and \{ \} escape literals.
  // Case-sensitive: lowercase \p is paragraph PROPERTIES (\pxqc;), a different
  // command carrying a payload up to a semicolon. Matching it here consumed
  // only the two characters and left the rest in the text.
  text = text.replace(/\\P/g, "\n").replace(/\\~/g, " ");
  // Inline property runs: \f...; \H...; \C...; \T...; \Q...; \W...; \A...; — command up to ;
  text = text.replace(/\\[fFhHcCtTqQwWaAp][^;]*;/g, "");
  // Stacking \S...^...; renders as the plain parts.
  text = text.replace(/\\S([^^;]*)\^([^;]*);/g, "$1/$2");
  // Grouping braces are structure, not content.
  text = text.replace(/[{}]/g, "");
  // %%d degree, %%p plus-minus, %%c diameter, %%u/%%o toggles.
  text = text.replace(/%%d/gi, "°").replace(/%%p/gi, "±").replace(/%%c/gi, "∅");
  text = text.replace(/%%[uo]/gi, "");
  return text.trim();
}

/** Where a marking's anchor sits on its text box. DXF stores the anchor point and an
 *  alignment code; the viewer, which is the only thing that knows the rendered width, turns
 *  the two into a placement. Default is the format's own: baseline, left. */
const TEXT_H_ALIGN = { 0: "left", 1: "center", 2: "right", 3: "left", 4: "center", 5: "left" };
const TEXT_V_ALIGN = { 0: "baseline", 1: "bottom", 2: "middle", 3: "top" };
const MTEXT_ATTACHMENT = {
  1: ["left", "top"], 2: ["center", "top"], 3: ["right", "top"],
  4: ["left", "middle"], 5: ["center", "middle"], 6: ["right", "middle"],
  7: ["left", "bottom"], 8: ["center", "bottom"], 9: ["right", "bottom"],
};

function parseTextEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const value = String(records.find((record) => record.code === 1)?.value ?? "").trim();
  if (!value) {
    return null;
  }
  const hCode = Math.trunc(toFiniteNumber(records.find((record) => record.code === 72)?.value, 0));
  const vCode = Math.trunc(toFiniteNumber(records.find((record) => record.code === 73)?.value, 0));
  // With any alignment other than baseline-left the anchor is the SECOND alignment point
  // (11/21); the first is where the text would start if it were left-justified.
  const aligned = hCode !== 0 || vCode !== 0;
  const pointCodes = aligned && records.some((record) => record.code === 11) ? [11, 21] : [10, 20];
  return {
    layer,
    position: [
      toFiniteNumber(records.find((record) => record.code === pointCodes[0])?.value),
      toFiniteNumber(records.find((record) => record.code === pointCodes[1])?.value)
    ],
    heightMm: Math.max(toFiniteNumber(records.find((record) => record.code === 40)?.value, 2.5), 0.01),
    rotationDeg: toFiniteNumber(records.find((record) => record.code === 50)?.value, 0),
    hAlign: TEXT_H_ALIGN[hCode] || "left",
    vAlign: TEXT_V_ALIGN[vCode] || "baseline",
    value
  };
}

function parseMtextEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  // The string is code 1, preceded by any number of code-3 continuation chunks.
  const chunks = records.filter((record) => record.code === 3).map((record) => String(record.value ?? ""));
  const tail = String(records.find((record) => record.code === 1)?.value ?? "");
  const value = stripMtextFormatting(chunks.join("") + tail);
  if (!value) {
    return null;
  }
  return {
    layer,
    position: [
      toFiniteNumber(records.find((record) => record.code === 10)?.value),
      toFiniteNumber(records.find((record) => record.code === 20)?.value)
    ],
    heightMm: Math.max(toFiniteNumber(records.find((record) => record.code === 40)?.value, 2.5), 0.01),
    rotationDeg: toFiniteNumber(records.find((record) => record.code === 50)?.value, 0),
    hAlign: (MTEXT_ATTACHMENT[Math.trunc(toFiniteNumber(records.find((record) => record.code === 71)?.value, 1))] || ["left", "top"])[0],
    vAlign: (MTEXT_ATTACHMENT[Math.trunc(toFiniteNumber(records.find((record) => record.code === 71)?.value, 1))] || ["left", "top"])[1],
    value
  };
}

/** DIMENSION: the graphics -- witness lines, the dimension line, arrowheads and the value
 *  as MTEXT -- live in an anonymous block (code 2, `*D12`) that every CAD package writes when
 *  it renders the dimension. The block is drawn in model coordinates, so it expands like an
 *  INSERT at the origin. A file without the block (some exporters write the entity alone)
 *  falls back to a marking of the value: the override (code 1) when there is one, else the
 *  measurement the file stored (code 42). "<>" means "the measured value" and is not text. */
function dimensionBlockName(records) {
  return String(records.find((record) => record.code === 2)?.value || "").trim();
}

function formatMeasurement(value) {
  if (!Number.isFinite(value)) {
    return "";
  }
  // Two decimals, then trailing zeros dropped: 100 reads "100", 4.5 reads "4.5". The file's
  // own dimension style would know its precision; without the block that style rendered
  // into, this is the readable default, not a tolerance statement.
  return String(Number(value.toFixed(2)));
}

function parseDimensionEntity(records) {
  const layer = normalizeLayerName(records.find((record) => record.code === 8)?.value);
  const override = String(records.find((record) => record.code === 1)?.value ?? "").trim();
  const measured = formatMeasurement(toFiniteNumber(records.find((record) => record.code === 42)?.value, Number.NaN));
  const value = override && override !== "<>"
    ? stripMtextFormatting(override.replace(/<>/g, measured))
    : measured;
  if (!value) {
    return null;
  }
  return {
    layer,
    position: [
      toFiniteNumber(records.find((record) => record.code === 11)?.value),
      toFiniteNumber(records.find((record) => record.code === 21)?.value)
    ],
    heightMm: 2.5,
    rotationDeg: toFiniteNumber(records.find((record) => record.code === 53)?.value, 0),
    hAlign: "center",
    vAlign: "middle",
    value
  };
}

function transformTextMarking(text, transform) {
  if (!transform) {
    return text;
  }
  const scale = Math.abs(transform.sx) || 1;
  const rotationDeg = (Math.atan2(transform.sin, transform.cos) * 180) / Math.PI;
  return {
    ...text,
    position: transformPoint(text.position, transform),
    heightMm: text.heightMm * scale,
    rotationDeg: text.rotationDeg + rotationDeg
  };
}

function transformPoint(point, transform) {
  if (!transform) {
    return point;
  }
  const { cos, sin, sx, sy, tx, ty } = transform;
  const x = point[0] * sx;
  const y = point[1] * sy;
  return [x * cos - y * sin + tx, x * sin + y * cos + ty];
}

function transformGeometry({ lines, arcs, circles, fills = [] }, transform) {
  if (!transform) {
    return { lines, arcs, circles, fills };
  }
  const { cos, sin, sx, sy, tx, ty } = transform;
  const scale = Math.abs(sx);
  const rotationDeg = (Math.atan2(sin, cos) * 180) / Math.PI;
  return {
    lines: lines.map((line) => ({
      ...line,
      start: transformPoint(line.start, transform),
      end: transformPoint(line.end, transform),
    })),
    // Arcs and circles survive only under a uniform scale; a non-uniform one would turn them
    // into ellipses, so the caller flattens those to line segments before we get here.
    arcs: arcs.map((arc) => ({
      ...arc,
      center: transformPoint(arc.center, transform),
      radius: arc.radius * scale,
      // A rotation shifts where the arc starts; its sweep is rotation-invariant.
      startAngleDeg: arc.startAngleDeg + rotationDeg,
    })),
    circles: (circles || []).map((circle) => ({
      ...circle,
      center: transformPoint(circle.center, transform),
      radius: circle.radius * scale,
    })),
    fills: fills.map((fill) => ({
      ...fill,
      points: fill.points.map((point) => transformPoint(point, transform)),
    })),
  };
}

/** Entities on layer "0" inside a block belong to whatever placed the block: that is the
 *  format's rule for block contents, and it is how an arrowhead block drawn on layer 0
 *  lands on the DIM layer of the dimension that uses it. */
function inheritBlockLayer(parsed, blockLayer) {
  if (!blockLayer || blockLayer === "0") {
    return parsed;
  }
  const relayer = (entity) => (entity.layer === "0" ? { ...entity, layer: blockLayer } : entity);
  return {
    lines: parsed.lines.map(relayer),
    arcs: parsed.arcs.map(relayer),
    circles: parsed.circles.map(relayer),
    texts: parsed.texts.map(relayer),
    fills: parsed.fills.map(relayer),
  };
}

/** INSERT: place a block's geometry with scale + rotation, including the MINSERT grid
 *  (columns/rows, codes 70/71 with spacing 44/45) that expands one entity into many. */
function insertTransforms(records) {
  const tx = toFiniteNumber(records.find((record) => record.code === 10)?.value);
  const ty = toFiniteNumber(records.find((record) => record.code === 20)?.value);
  const sx = toFiniteNumber(records.find((record) => record.code === 41)?.value, 1) || 1;
  const sy = toFiniteNumber(records.find((record) => record.code === 42)?.value, 1) || 1;
  const rotationDeg = toFiniteNumber(records.find((record) => record.code === 50)?.value, 0);
  const columns = Math.max(1, Math.trunc(toFiniteNumber(records.find((record) => record.code === 70)?.value, 1)));
  const rows = Math.max(1, Math.trunc(toFiniteNumber(records.find((record) => record.code === 71)?.value, 1)));
  const columnSpacing = toFiniteNumber(records.find((record) => record.code === 44)?.value, 0);
  const rowSpacing = toFiniteNumber(records.find((record) => record.code === 45)?.value, 0);
  const radians = (rotationDeg * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const transforms = [];
  for (let column = 0; column < columns; column += 1) {
    for (let row = 0; row < rows; row += 1) {
      transforms.push({
        cos,
        sin,
        sx,
        sy,
        tx: tx + column * columnSpacing,
        ty: ty + row * rowSpacing,
      });
    }
  }
  return transforms;
}

function composeTransforms(outer, inner) {
  if (!outer) return inner;
  if (!inner) return outer;
  const placed = transformPoint([inner.tx, inner.ty], outer);
  const cos = outer.cos * inner.cos - outer.sin * inner.sin;
  const sin = outer.sin * inner.cos + outer.cos * inner.sin;
  return { cos, sin, sx: outer.sx * inner.sx, sy: outer.sy * inner.sy, tx: placed[0], ty: placed[1] };
}

/** The XDATA a cadgen sheet writes on each entity (application CADGEN, strings
 *  "view=<name>" and "dim=<index>"), as {view, dim}. Other files have none. */
export const DXF_SHEET_XDATA_APPID = "CADGEN";

function sheetTagsFromRecords(entityRecords) {
  const tags = {};
  let inside = false;
  for (const record of entityRecords) {
    if (record.code === 1001) {
      inside = String(record.value || "").trim().toUpperCase() === DXF_SHEET_XDATA_APPID;
      continue;
    }
    if (inside && record.code === 1000) {
      const text = String(record.value || "");
      const eq = text.indexOf("=");
      if (eq > 0) {
        tags[text.slice(0, eq).trim()] = text.slice(eq + 1).trim();
      }
    }
  }
  return tags;
}

function stampSheetTags(items, tags) {
  if (!tags.view) {
    return items;
  }
  for (const item of items) {
    item.view = tags.view;
    if (tags.dim !== undefined) {
      item.dim = tags.dim;
    }
  }
  return items;
}

function parseEntities(records, { blocks = new Map(), transform = null, depth = 0, apparatus = null } = {}) {
  const lines = [];
  const arcs = [];
  const circles = [];
  const texts = [];
  const fills = [];
  // The sheet tags of the entity being parsed, stamped on everything it produces
  // (a DIMENSION's expanded block included) so a view's extent can be found later.
  let currentTags = {};
  const push = (geometry) => {
    const placed = transformGeometry(
      { lines: geometry.lines || [], arcs: geometry.arcs || [], circles: geometry.circles || [], fills: geometry.fills || [] },
      transform
    );
    lines.push(...stampSheetTags(placed.lines, currentTags));
    arcs.push(...stampSheetTags(placed.arcs, currentTags));
    circles.push(...stampSheetTags(placed.circles, currentTags));
    fills.push(...stampSheetTags(placed.fills, currentTags));
  };
  const pushNested = (nested) => {
    lines.push(...stampSheetTags(nested.lines, currentTags));
    arcs.push(...stampSheetTags(nested.arcs, currentTags));
    circles.push(...stampSheetTags(nested.circles, currentTags));
    texts.push(...stampSheetTags(nested.texts, currentTags));
    fills.push(...stampSheetTags(nested.fills, currentTags));
  };
  const pushText = (text) => {
    if (text) {
      texts.push(...stampSheetTags([transformTextMarking(text, transform)], currentTags));
    }
  };

  let index = 0;
  while (index < records.length) {
    const startRecord = records[index];
    if (startRecord.code !== 0) {
      index += 1;
      continue;
    }
    const entityType = String(startRecord.value || "").trim().toUpperCase();
    if (entityType === "ENDSEC" || entityType === "ENDBLK") {
      break;
    }
    const entityRecords = [];
    index += 1;
    while (index < records.length && records[index].code !== 0) {
      entityRecords.push(records[index]);
      index += 1;
    }

    currentTags = depth === 0 ? sheetTagsFromRecords(entityRecords) : currentTags;
    if (apparatus) {
      // Dimensioned-drawing evidence (the profile predicate's inputs). Mirrors
      // cadgen.drawing_checks.document_is_drawing: positive evidence only — a
      // cut layout has no dimensions, leaders, or paper-space entities.
      if (entityType === "DIMENSION" || entityType === "ARC_DIMENSION") {
        apparatus.dimensions += 1;
        if (currentTags.view && currentTags.dim !== undefined && Array.isArray(apparatus.sheetDimensions)) {
          const marking = parseDimensionEntity(entityRecords);
          // The value as the file rendered it (tolerance included) comes from the
          // dimension's block text, filled in below once the block is expanded.
          apparatus.sheetDimensions.push({
            kind: "dimension",
            view: currentTags.view,
            index: currentTags.dim,
            value: marking?.value || "",
            position: marking?.position || [
              toFiniteNumber(entityRecords.find((record) => record.code === 11)?.value),
              toFiniteNumber(entityRecords.find((record) => record.code === 21)?.value)
            ]
          });
        }
      } else if (entityType === "LEADER" || entityType === "MLEADER" || entityType === "MULTILEADER") {
        apparatus.leaders += 1;
      }
      if (entityRecords.some((record) => record.code === 67 && Number(record.value) === 1)) {
        apparatus.paperspaceEntities += 1;
      }
    }

    if (entityType === "LINE") {
      push({ lines: [parseLineEntity(entityRecords)] });
      continue;
    }
    if (entityType === "ARC") {
      push({ arcs: [parseArcEntity(entityRecords)] });
      continue;
    }
    if (entityType === "CIRCLE") {
      push({ circles: [parseCircleEntity(entityRecords)] });
      continue;
    }
    if (entityType === "LWPOLYLINE") {
      push(parseLwpolylineEntity(entityRecords));
      continue;
    }
    if (entityType === "ELLIPSE") {
      push(parseEllipseEntity(entityRecords));
      continue;
    }
    if (entityType === "SPLINE") {
      push(parseSplineEntity(entityRecords));
      continue;
    }
    if (entityType === "HATCH") {
      push(parseHatchEntity(entityRecords));
      continue;
    }
    if (entityType === "TEXT") {
      const text = parseTextEntity(entityRecords);
      if (depth === 0 && currentTags.view && currentTags.map && apparatus?.sheetViewPlacement) {
        const numbers = String(currentTags.map).split(",").map(Number);
        const at = String(currentTags.at || "").split(",").map(Number);
        if (numbers.length === 8 && numbers.every(Number.isFinite)) {
          apparatus.sheetViewPlacement.set(currentTags.view, {
            at: at.length === 2 && at.every(Number.isFinite) ? at : null,
            map: numbers
          });
        }
      }
      if (text && depth === 0 && currentTags.view && currentTags.dim !== undefined && Array.isArray(apparatus?.sheetDimensions)) {
        // A callout (hole, diameter, note): a leader plus this text, tagged like a dimension.
        apparatus.sheetDimensions.push({
          kind: "callout",
          view: currentTags.view,
          index: currentTags.dim,
          value: stripMtextFormatting(String(text.value || "")),
          position: [text.position[0], text.position[1]]
        });
      }
      pushText(text);
      continue;
    }
    if (entityType === "MTEXT") {
      pushText(parseMtextEntity(entityRecords));
      continue;
    }
    if (entityType === "DIMENSION" || entityType === "ARC_DIMENSION") {
      const blockRecords = blocks.get(dimensionBlockName(entityRecords).toUpperCase());
      if (blockRecords && depth < MAX_BLOCK_NESTING) {
        // The rendered dimension, exactly as the authoring package drew it.
        const dimensionLayer = normalizeLayerName(entityRecords.find((record) => record.code === 8)?.value);
        const expanded = inheritBlockLayer(
          parseEntities(blockRecords, { blocks, transform, depth: depth + 1 }),
          dimensionLayer
        );
        const listed = Array.isArray(apparatus?.sheetDimensions) && currentTags.dim !== undefined
          ? apparatus.sheetDimensions[apparatus.sheetDimensions.length - 1]
          : null;
        if (listed && listed.kind === "dimension" && !listed.value) {
          // The block's MTEXT stacks a tolerance right after the value; a space keeps it readable.
          const rendered = expanded.texts.map((text) => stripMtextFormatting(String(text.value || "")).trim()).filter(Boolean);
          listed.value = rendered.join(" ").replace(/(\d)([±+])/g, "$1 $2");
          if (expanded.texts[0]) {
            listed.position = [expanded.texts[0].position[0], expanded.texts[0].position[1]];
          }
        }
        pushNested(expanded);
      } else {
        pushText(parseDimensionEntity(entityRecords));
      }
      continue;
    }
    if (entityType === "SOLID" || entityType === "TRACE") {
      push(parseSolidEntity(entityRecords));
      continue;
    }
    if (entityType === "LEADER") {
      push(parseLeaderEntity(entityRecords));
      continue;
    }
    if (entityType === "POLYLINE") {
      // Its vertices are SEPARATE entities that follow until SEQEND, so the walker has to
      // consume them here rather than the entity parser reading them inline.
      const vertexGroups = [];
      while (index < records.length) {
        const next = records[index];
        if (next.code !== 0) {
          index += 1;
          continue;
        }
        const nextType = String(next.value || "").trim().toUpperCase();
        if (nextType === "VERTEX") {
          const group = [];
          index += 1;
          while (index < records.length && records[index].code !== 0) {
            group.push(records[index]);
            index += 1;
          }
          vertexGroups.push(group);
          continue;
        }
        if (nextType === "SEQEND") {
          index += 1;
          while (index < records.length && records[index].code !== 0) {
            index += 1;
          }
        }
        break;
      }
      push(parsePolylineEntity(entityRecords, vertexGroups));
      continue;
    }
    if (entityType === "INSERT") {
      // Depth-limited: a block that references itself would otherwise recurse forever, and a
      // malformed file should not hang a build.
      if (depth >= MAX_BLOCK_NESTING) {
        throw new Error("DXF block nesting is too deep");
      }
      const blockName = String(entityRecords.find((record) => record.code === 2)?.value || "").trim();
      const blockRecords = blocks.get(blockName.toUpperCase());
      if (!blockRecords) {
        // A missing block is empty, not fatal: drawings reference blocks they no longer
        // define, and one dangling name should not cost the whole profile.
        continue;
      }
      const insertLayer = normalizeLayerName(entityRecords.find((record) => record.code === 8)?.value);
      for (const placement of insertTransforms(entityRecords)) {
        pushNested(inheritBlockLayer(
          parseEntities(blockRecords, {
            blocks,
            transform: composeTransforms(transform, placement),
            depth: depth + 1,
          }),
          insertLayer
        ));
      }
      continue;
    }
    if (NON_GEOMETRIC_ENTITY_TYPES.has(entityType)) {
      continue;
    }
    throw new Error(`Unsupported DXF entity ${entityType}`);
  }

  return { lines, arcs, circles, texts, fills };
}

/** BLOCKS as name -> its entity records, so an INSERT can be expanded in place.
 *
 * A block runs from its BLOCK header (its name is code 2) to ENDBLK. Names are keyed
 * upper-case because DXF block references are not case-sensitive in practice. */
function parseBlocks(records) {
  const blocks = new Map();
  let index = 0;
  while (index < records.length) {
    const record = records[index];
    if (record.code !== 0 || String(record.value || "").trim().toUpperCase() !== "BLOCK") {
      index += 1;
      continue;
    }
    index += 1;
    const header = [];
    while (index < records.length && records[index].code !== 0) {
      header.push(records[index]);
      index += 1;
    }
    const name = String(header.find((entry) => entry.code === 2)?.value || "").trim();
    const body = [];
    while (index < records.length) {
      const next = records[index];
      if (next.code === 0 && String(next.value || "").trim().toUpperCase() === "ENDBLK") {
        index += 1;
        break;
      }
      body.push(next);
      index += 1;
    }
    if (name) {
      blocks.set(name.toUpperCase(), body);
    }
  }
  return blocks;
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
    circleCount: 0,
    textCount: 0
  };
  layerSummary.set(layerName, next);
  return next;
}

/** Scale every parsed coordinate to millimetres. Lengths (radii, text heights) scale with
 *  positions; angles are unit-free. */
function scaleEntitiesToMm(entities, scale) {
  if (scale === 1) {
    return entities;
  }
  const scalePoint = (point) => [point[0] * scale, point[1] * scale];
  return {
    lines: entities.lines.map((line) => ({
      ...line,
      start: scalePoint(line.start),
      end: scalePoint(line.end)
    })),
    arcs: entities.arcs.map((arc) => ({
      ...arc,
      center: scalePoint(arc.center),
      radius: arc.radius * scale
    })),
    circles: entities.circles.map((circle) => ({
      ...circle,
      center: scalePoint(circle.center),
      radius: circle.radius * scale
    })),
    texts: entities.texts.map((text) => ({
      ...text,
      position: scalePoint(text.position),
      heightMm: text.heightMm * scale
    })),
    fills: (entities.fills || []).map((fill) => ({
      ...fill,
      points: fill.points.map(scalePoint)
    }))
  };
}

/**
 * Whether parsed DXF data is a dimensioned DRAWING rather than a cut layout.
 *
 * The client twin of cadgen.drawing_checks.document_is_drawing, on the same
 * positive-evidence rule: dimensions/leaders or paper-space entities make a
 * document; "nothing closes, so it must be a drawing" would excuse a genuinely
 * broken cut layout. A document renders as 2D line work; a layout renders as
 * its 3D flat pattern.
 */
export function dxfDataIsDocument(dxfData) {
  const apparatus = dxfData?.apparatus;
  if (!apparatus || typeof apparatus !== "object") {
    return false;
  }
  return (
    Number(apparatus.dimensions) > 0
    || Number(apparatus.leaders) > 0
    || Number(apparatus.paperspaceEntities) > 0
  );
}

export function parseDxf(dxfText, { fileRef = "", sourceUrl = "" } = {}) {
  // A Git LFS pointer is 3 lines of metadata, not a drawing. Without this check it fails
  // as "group code stream is malformed", which sends people debugging the parser instead
  // of hydrating the file.
  if (/^version https:\/\/git-lfs/.test(String(dxfText || ""))) {
    throw new Error(
      "This DXF is a Git LFS pointer, not the drawing itself. Run `git lfs checkout` on it and rebuild."
    );
  }
  const records = parseRecordPairs(dxfText);
  const sections = splitSections(records);
  const header = parseHeader(sections.get("HEADER") || []);
  const layerTable = parseLayerTable(sections.get("TABLES") || []);
  const blocks = parseBlocks(sections.get("BLOCKS") || []);
  const unitsScaleMm = dxfUnitsScaleMm(header.sourceUnits);
  const apparatus = { dimensions: 0, leaders: 0, paperspaceEntities: 0, sheetDimensions: [], sheetViewPlacement: new Map() };
  const entities = scaleEntitiesToMm(
    parseEntities(sections.get("ENTITIES") || [], { blocks, apparatus }),
    unitsScaleMm
  );

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
    const end = screenPoint(pointOnCircle(arc.center, arc.radius, arc.startAngleDeg + arc.sweepAngleDeg), {
      minX: rawBounds.minX,
      maxY: rawBounds.maxY
    });
    const largeArcFlag = Math.abs(arc.sweepAngleDeg) > 180 + ANGLE_EPSILON ? 1 : 0;
    const sweepFlag = arc.sweepAngleDeg >= 0 ? 0 : 1;
    pathRecords.push(
      buildPathRecord(
        arc.layer,
        semanticKindForLayer(arc.layer),
        `M ${formatNumber(start[0])} ${formatNumber(start[1])} A ${formatNumber(arc.radius)} ${formatNumber(arc.radius)} 0 ${largeArcFlag} ${sweepFlag} ${formatNumber(end[0])} ${formatNumber(end[1])}`
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

  for (const text of entities.texts) {
    touchLayer(layerSummary, text.layer).textCount += 1;
  }

  // Sheet views (from the tags a cadgen sheet writes): each view's extent on the sheet,
  // from its tagged line work, and the dimensions authored in it.
  const viewBounds = new Map();
  const grow = (view, xs, ys) => {
    if (!view) return;
    const current = viewBounds.get(view) || { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    for (const x of xs) { current.minX = Math.min(current.minX, x); current.maxX = Math.max(current.maxX, x); }
    for (const y of ys) { current.minY = Math.min(current.minY, y); current.maxY = Math.max(current.maxY, y); }
    viewBounds.set(view, current);
  };
  for (const line of entities.lines) {
    if (line.view && line.dim === undefined) grow(line.view, [line.start[0], line.end[0]], [line.start[1], line.end[1]]);
  }
  for (const arc of entities.arcs) {
    if (arc.view && arc.dim === undefined) grow(arc.view, [arc.center[0] - arc.radius, arc.center[0] + arc.radius], [arc.center[1] - arc.radius, arc.center[1] + arc.radius]);
  }
  for (const circle of entities.circles) {
    if (circle.view && circle.dim === undefined) grow(circle.view, [circle.center[0] - circle.radius, circle.center[0] + circle.radius], [circle.center[1] - circle.radius, circle.center[1] + circle.radius]);
  }
  const sheetDimensions = (apparatus.sheetDimensions || []).map((dimension) => ({
    ...dimension,
    position: [formatNumber(dimension.position[0] * unitsScaleMm), formatNumber(dimension.position[1] * unitsScaleMm)]
  }));
  const viewPlacement = apparatus.sheetViewPlacement || new Map();
  const views = [...viewBounds.entries()].map(([name, bounds]) => ({
    name,
    minX: formatNumber(bounds.minX),
    minY: formatNumber(bounds.minY),
    maxX: formatNumber(bounds.maxX),
    maxY: formatNumber(bounds.maxY),
    dimensionCount: sheetDimensions.filter((dimension) => dimension.view === name).length,
    // Placement (at=) and the model->sheet affine map (map=b, a0, a1, a2) the sheet wrote.
    at: viewPlacement.get(name)?.at || null,
    map: viewPlacement.get(name)?.map || null
  }));
  delete apparatus.sheetViewPlacement;
  delete apparatus.sheetDimensions;

  return {
    fileRef,
    sourceUrl,
    sourceUnits: header.sourceUnits,
    views,
    sheetDimensions,
    unitsScaleMm,
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
    apparatus,
    layers: [...layerSummary.keys()].sort().map((name) => {
      const summary = layerSummary.get(name);
      const tableEntry = layerTable.get(name);
      return {
        ...summary,
        colorAci: tableEntry ? tableEntry.aci : null,
        colorHex: tableEntry ? aciColorHex(tableEntry.aci) : null,
        visibleDefault: tableEntry ? tableEntry.visibleDefault : true,
        linetype: tableEntry ? tableEntry.linetype : "CONTINUOUS",
        lineweightMm: tableEntry ? tableEntry.lineweightMm : null
      };
    }),
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
      })),
      texts: entities.texts.map((text) => ({
        layer: text.layer,
        kind: semanticKindForLayer(text.layer),
        position: [formatNumber(text.position[0]), formatNumber(text.position[1])],
        heightMm: formatNumber(text.heightMm),
        rotationDeg: formatNumber(text.rotationDeg),
        hAlign: text.hAlign || "left",
        vAlign: text.vAlign || "baseline",
        value: text.value
      })),
      fills: (entities.fills || []).map((fill) => ({
        layer: fill.layer,
        kind: semanticKindForLayer(fill.layer),
        points: fill.points.map((point) => [formatNumber(point[0]), formatNumber(point[1])])
      }))
    },
    paths: pathRecords,
    circles: circleRecords
  };
}

import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyMeasurePick,
  classifyMeasureSnapKind,
  closestPointOnSegment,
  closestPointOnSegmentList,
  edgeGeometryFromSegments,
  entityMeasurementFromPick,
  formatEntityMeasurement,
  formatMeasurementAngle,
  hasMeasurableSegments,
  distanceBetweenPoints,
  formatMeasurement,
  formatMeasurementDelta,
  isFinitePoint,
  isPlanarFace,
  measurePointFromReference,
  measurementFromPicks,
  normalizeVector3,
  pickMeshVertexByScreenDistance
} from "./measurement.js";


test("isFinitePoint accepts finite length-3 points and rejects malformed inputs", () => {
  assert.equal(isFinitePoint([1, 2, 3]), true);
  assert.equal(isFinitePoint([1, 2]), false);
  assert.equal(isFinitePoint([1, 2, NaN]), false);
  assert.equal(isFinitePoint([1, 2, Infinity]), false);
  assert.equal(isFinitePoint(null), false);
  assert.equal(isFinitePoint("1,2,3"), false);
});

test("normalizeVector3 normalizes unit and scales and rejects unusable input", () => {
  assert.deepEqual(normalizeVector3([3, 0, 0]), [1, 0, 0]);
  const normalized = normalizeVector3([1, 1, 1]);
  assert.ok(Math.abs(Math.hypot(...normalized) - 1) < 1e-9);
  assert.equal(normalizeVector3([0, 0, 0]), null);
  assert.equal(normalizeVector3([NaN, 1, 0]), null);
  assert.equal(normalizeVector3("x"), null);
});

test("pickMeshVertexByScreenDistance keeps STEP's close-range corner rule", () => {
  const vertices = [[0, 0, 0], [10, 0, 0], [0, 10, 0]];
  const projectToClient = (vertex) => ({ x: vertex[0] * 10, y: vertex[1] * 10 });
  assert.deepEqual(
    pickMeshVertexByScreenDistance(vertices, { x: 2, y: 1 }, 5, projectToClient),
    { point: [0, 0, 0], snapKind: "vertex", screenDistance: Math.hypot(2, 1) }
  );
  assert.equal(
    pickMeshVertexByScreenDistance(vertices, { x: 40, y: 40 }, 5, projectToClient),
    null
  );
  assert.equal(pickMeshVertexByScreenDistance(vertices, { x: 0, y: 0 }, 5, null), null);
});

test("distanceBetweenPoints measures euclidean distance and clamps tiny values to zero", () => {
  assert.equal(distanceBetweenPoints([0, 0, 0], [3, 4, 0]), 5);
  assert.equal(distanceBetweenPoints([0, 0, 0], [0, 0, 0]), 0);
  assert.equal(distanceBetweenPoints([0, 0, 0], [1e-12, 0, 0]), 0);
  assert.equal(distanceBetweenPoints([0, 0], [1, 0, 0]), null);
});

test("closestPointOnSegment projects onto the segment interior and clamps to endpoints", () => {
  assert.deepEqual(closestPointOnSegment([0, 1, 0], [0, 0, 0], [0, 2, 0]), [0, 1, 0]);
  assert.deepEqual(closestPointOnSegment([0, 5, 0], [0, 0, 0], [0, 2, 0]), [0, 2, 0]);
  assert.deepEqual(closestPointOnSegment([0, -2, 0], [0, 0, 0], [0, 2, 0]), [0, 0, 0]);
  assert.deepEqual(closestPointOnSegment([1, 0, 0], [0, 0, 0], [0, 0, 0]), [0, 0, 0]);
  assert.equal(closestPointOnSegment([0, 0], [0, 0, 0], [0, 2, 0]), null);
});

test("closestPointOnSegmentList snaps to the nearest of independent segments", () => {
  // Two parallel bars: consecutive segments must NOT be treated as joined, or the
  // gap between them would attract snaps that belong to neither.
  const segments = [0, 0, 0, 4, 0, 0, 0, 10, 0, 4, 10, 0];
  assert.deepEqual(closestPointOnSegmentList(segments, [2, 1, 0]), [2, 0, 0]);
  assert.deepEqual(closestPointOnSegmentList(segments, [2, 9, 0]), [2, 10, 0]);
  assert.deepEqual(closestPointOnSegmentList(segments, [9, 0, 0]), [4, 0, 0]);
  assert.deepEqual(closestPointOnSegmentList(segments, [2, 5, 0]), [2, 0, 0]);
  assert.equal(closestPointOnSegmentList(new Float32Array([0, 0, 0, 1, 0, 0]), [0.5, 1, 0])[0], 0.5);
  assert.equal(closestPointOnSegmentList([0, 0, 0], [0, 0, 0]), null);
  assert.equal(closestPointOnSegmentList(null, [0, 0, 0]), null);
  assert.equal(closestPointOnSegmentList(segments, null), null);
});

test("hasMeasurableSegments requires whole segment pairs", () => {
  assert.equal(hasMeasurableSegments([0, 0, 0, 1, 1, 1]), true);
  assert.equal(hasMeasurableSegments(new Float32Array(12)), true);
  assert.equal(hasMeasurableSegments([0, 0, 0, 1, 1]), false);
  assert.equal(hasMeasurableSegments([]), false);
  assert.equal(hasMeasurableSegments(null), false);
});

test("isPlanarFace accepts stable surfaceType tokens and requires a finite normal", () => {
  assert.equal(isPlanarFace({ pickData: { surfaceType: "PLANE", normal: [0, 0, 1] } }), true);
  assert.equal(isPlanarFace({ pickData: { surfaceType: "planar", normal: [0, 0, 1] } }), true);
  assert.equal(isPlanarFace({ pickData: { surface: { type: "PLANE" }, normal: [0, 0, 1] } }), true);
  assert.equal(isPlanarFace({ pickData: { surfaceType: "CYLINDRICAL_SURFACE", normal: [0, 0, 1] } }), false);
  assert.equal(isPlanarFace({ pickData: { surfaceType: "PLANE" } }), false);
  assert.equal(isPlanarFace({ pickData: { surfaceType: "PLANE", normal: [0, 0, 0] } }), false);
  assert.equal(isPlanarFace({}), false);
  assert.equal(isPlanarFace(null), false);
});

test("measurePointFromReference resolves vertex point, edge snap, and hit points", () => {
  const edgeSegments = [0, 0, 0, 4, 0, 0];
  assert.deepEqual(
    measurePointFromReference({ snapKind: "vertex", vertexPoint: [1, 2, 3], hitPoint: [0, 0, 0] }),
    [1, 2, 3]
  );
  assert.deepEqual(
    measurePointFromReference({ snapKind: "edge", edgeSegments, hitPoint: [2, 1, 0] }),
    [2, 0, 0]
  );
  assert.deepEqual(measurePointFromReference({ snapKind: "face", hitPoint: [1, 1, 1] }), [1, 1, 1]);
  assert.deepEqual(measurePointFromReference({ snapKind: "free", hitPoint: [2, 2, 2] }), [2, 2, 2]);
  assert.equal(measurePointFromReference({ snapKind: "edge", edgeSegments }), null);
  assert.equal(measurePointFromReference({ snapKind: "unknown" }), null);
  assert.equal(measurePointFromReference({ snapKind: "vertex" }), null);
});

test("measurementFromPicks measures euclidean distance and per-axis delta", () => {
  const result = measurementFromPicks(
    { point: [0, 0, 0] },
    { point: [3, 4, 0] }
  );
  assert.equal(result.euclidean, 5);
  assert.deepEqual(result.delta, [3, 4, 0]);
  assert.equal(result.unit, "mm");
  assert.equal(result.perpendicular, null);
  assert.equal(measurementFromPicks({ }, { point: [1, 0, 0] }), null);
});

test("measurementFromPicks reports perpendicular distance for parallel planar faces", () => {
  const faceA = {
    point: [0, 0, 0],
    snapKind: "face", reference: { pickData: { surfaceType: "PLANE", normal: [0, 0, 1] } }
  };
  const faceB = {
    point: [0, 0, 2.5],
    snapKind: "face", reference: { pickData: { surfaceType: "PLANE", normal: [0, 0, 1] } }
  };
  assert.equal(measurementFromPicks(faceA, faceB).perpendicular, 2.5);
});

test("measurementFromPicks treats anti-parallel planar faces as perpendicular", () => {
  const faceA = {
    point: [0, 0, 0],
    snapKind: "face", reference: { pickData: { surfaceType: "PLANE", normal: [0, 0, 1] } }
  };
  const faceB = {
    point: [0, 0, 4],
    snapKind: "face", reference: { pickData: { surfaceType: "PLANE", normal: [0, 0, -1] } }
  };
  assert.equal(measurementFromPicks(faceA, faceB).perpendicular, 4);
});

test("measurementFromPicks falls back to euclidean for non-parallel faces", () => {
  const faceA = {
    point: [0, 0, 0],
    snapKind: "face", reference: { pickData: { surfaceType: "PLANE", normal: [1, 0, 0] } }
  };
  const faceB = {
    point: [0, 0, 1],
    snapKind: "face", reference: { pickData: { surfaceType: "PLANE", normal: [0, 1, 0] } }
  };
  const result = measurementFromPicks(faceA, faceB);
  assert.equal(result.perpendicular, null);
  assert.equal(result.euclidean, 1);
});

test("measurementFromPicks refuses perpendicular distance for non-planar picks", () => {
  const cylinder = {
    point: [0, 0, 0],
    snapKind: "face", reference: { pickData: { surfaceType: "CYLINDRICAL_SURFACE", normal: [0, 1, 0] } }
  };
  const face = {
    point: [0, 0, 5],
    snapKind: "face", reference: { pickData: { surfaceType: "PLANE", normal: [0, 0, 1] } }
  };
  const result = measurementFromPicks(cylinder, face);
  assert.equal(result.perpendicular, null);
  assert.equal(result.euclidean, 5);
});

test("measurementFromPicks treats a vanishing perpendicular gap as no gap at all", () => {
  // Faces this close are the same plane. Reporting a perpendicular of 0 hides the
  // real distance between the picked points and draws a zero-length dimension.
  const faceA = {
    point: [0, 0, 0],
    referenceId: "a",
    snapKind: "face",
    reference: { pickData: { surfaceType: "PLANE", normal: [0, 0, 1] } }
  };
  const faceB = {
    point: [3, 4, 1e-12],
    referenceId: "b",
    snapKind: "face",
    reference: { pickData: { surfaceType: "PLANE", normal: [0, 0, 1] } }
  };
  const result = measurementFromPicks(faceA, faceB);
  assert.equal(result.perpendicular, null);
  assert.equal(result.euclidean, 5);
});

test("classifyMeasureSnapKind classifies references deterministically", () => {
  assert.equal(
    classifyMeasureSnapKind({ pickData: { selectorType: "vertex" }, vertexPoint: [1, 2, 3], hitPoint: [0, 0, 0] }),
    "vertex"
  );
  assert.equal(
    classifyMeasureSnapKind({ pickData: { selectorType: "edge" }, edgeSegments: [0, 0, 0, 1, 0, 0], hitPoint: [0, 0, 0] }),
    "edge"
  );
  assert.equal(
    classifyMeasureSnapKind({ pickData: { selectorType: "face", normal: [0, 0, 1] }, hitPoint: [0, 0, 1] }),
    "face"
  );
  assert.equal(
    classifyMeasureSnapKind({ pickData: { selectorType: "occurrence", name: "part" }, hitPoint: [1, 2, 3] }),
    "free"
  );
  // Real pickData carries edges as segmentStart/segmentCount into a shared buffer
  // and has no points array, so an unresolved edge must degrade to a free point
  // rather than silently claiming an edge snap it never computed.
  assert.equal(
    classifyMeasureSnapKind({ pickData: { selectorType: "edge", segmentStart: 0, segmentCount: 41 }, hitPoint: [0, 0, 0] }),
    "free"
  );
  assert.equal(classifyMeasureSnapKind({ pickData: { selectorType: "vertex" }, hitPoint: [0, 0, 0] }), "free");
  assert.equal(classifyMeasureSnapKind({ pickData: null, hitPoint: [1, 2, 3] }), "free");
  assert.equal(classifyMeasureSnapKind({ pickData: {} }), null);
  assert.equal(classifyMeasureSnapKind({ pickData: { selectorType: "face" } }), "face");
});

test("classifyMeasurePick resolves the reference to a snap point and returns the reference", () => {
  const classify = (reference, hitPoint, snap = {}) => classifyMeasurePick({
    reference,
    hitPoint,
    referenceId: reference?.id || "",
    ...snap
  });
  const edgeReference = { id: "topology|1|edge|2", selectorType: "edge", pickData: { selectorType: "edge" } };
  assert.deepEqual(
    classify(edgeReference, [5, 1, 0], { edgeSegments: [0, 0, 0, 4, 0, 0] }),
    {
      referenceId: "topology|1|edge|2",
      reference: edgeReference,
      snapKind: "edge",
      point: [4, 0, 0],
      geometry: { kind: "line", direction: [1, 0, 0] }
    }
  );
  const vertexReference = { id: "v1", selectorType: "vertex", pickData: { selectorType: "vertex" } };
  assert.deepEqual(
    classify(vertexReference, [0, 0, 0], { vertexPoint: [1.5, 2.5, 3.5] }),
    { referenceId: "v1", reference: vertexReference, snapKind: "vertex", point: [1.5, 2.5, 3.5], geometry: null }
  );
  const faceReference = { id: "f1", selectorType: "face", pickData: { selectorType: "face", normal: [0, 0, 1], center: [0, 0, 0] } };
  assert.deepEqual(
    classify(faceReference, [2, 2, 0]),
    { referenceId: "f1", reference: faceReference, snapKind: "face", point: [2, 2, 0], geometry: null }
  );
  const freeReference = { id: "p1", selectorType: "occurrence", pickData: { selectorType: "occurrence", name: "part" } };
  assert.deepEqual(
    classify(freeReference, [1, 2, 3]),
    { referenceId: "p1", reference: freeReference, snapKind: "free", point: [1, 2, 3], geometry: null }
  );
  assert.equal(classify({}, null), null);
  assert.equal(classify({ pickData: { selectorType: "face", normal: [0, 0, 1] } }, null), null);
});

test("classifyMeasurePick keeps world-space coordinates for transformed references", () => {
  const worldEdge = [[0, 0, 0], [4, 0, 0]].flatMap(([x, y, z]) => {
    const rotated = [-y, x, z];
    return [rotated[0] + 10, rotated[1] + 20, rotated[2] - 5];
  });
  const reference = { id: "world-edge", selectorType: "edge", pickData: { selectorType: "edge" } };
  const result = classifyMeasurePick({
    reference,
    hitPoint: [10, 22, -5],
    referenceId: "world-edge",
    edgeSegments: worldEdge
  });
  assert.deepEqual(result.point, [10, 22, -5]);
  assert.equal(result.snapKind, "edge");
  assert.equal(result.reference, reference);
});

test("classifyMeasurePick keeps float precision in hit coordinates", () => {
  const result = classifyMeasurePick({
    reference: { pickData: { selectorType: "face", normal: [0, 0, 1] } },
    hitPoint: [1.2345678, -2.3456789, 3.4567891]
  });
  assert.deepEqual(result.point, [1.2345678, -2.3456789, 3.4567891]);
  assert.equal(result.snapKind, "face");
});

test("classifyMeasurePick rejects non-finite hit points for free/face picks", () => {
  assert.equal(classifyMeasurePick({ hitPoint: [NaN, 0, 0] }), null);
  assert.equal(classifyMeasurePick({ hitPoint: [0, 0] }), null);
});

test("formatMeasurement renders the preferred distance with units and precision", () => {
  assert.equal(formatMeasurement({ euclidean: 12.345, perpendicular: null, unit: "mm" }), "12.35 mm");
  assert.equal(formatMeasurement({ euclidean: 5, perpendicular: 2.5, unit: "mm" }), "2.50 mm");
  assert.equal(formatMeasurement({ euclidean: 10, perpendicular: 10, unit: "mm" }, { precision: 0 }), "10 mm");
  assert.equal(formatMeasurement(null), "");
  assert.equal(formatMeasurement({ euclidean: NaN }), "");
});
test("formatMeasurementDelta renders per-axis deltas with units-free labels", () => {
  assert.equal(
    formatMeasurementDelta({ delta: [1.234, -5.5, 0] }),
    "ΔX 1.23  ΔY -5.50  ΔZ 0.00"
  );
  assert.equal(
    formatMeasurementDelta({ delta: [10, 20, 30] }, { precision: 0 }),
    "ΔX 10  ΔY 20  ΔZ 30"
  );
});

test("formatMeasurementDelta normalizes negative zero components", () => {
  assert.equal(formatMeasurementDelta({ delta: [-0.0001, 0, -0] }), "ΔX 0.00  ΔY 0.00  ΔZ 0.00");
  assert.equal(formatMeasurementDelta({ delta: [0, 0, 0] }), "ΔX 0.00  ΔY 0.00  ΔZ 0.00");
});

test("formatMeasurementDelta rejects invalid deltas", () => {
  assert.equal(formatMeasurementDelta(null), "");
  assert.equal(formatMeasurementDelta({}), "");
  assert.equal(formatMeasurementDelta({ delta: null }), "");
  assert.equal(formatMeasurementDelta({ delta: [1, 2] }), "");
  assert.equal(formatMeasurementDelta({ delta: [NaN, 0, 0] }), "");
});

const planePick = (normal, point, extra = {}) => ({
  snapKind: "face",
  point,
  reference: { pickData: { selectorType: "face", surfaceType: "plane", normal, ...extra } }
});

const linePick = (direction, point) => ({
  snapKind: "edge",
  point,
  geometry: { kind: "line", direction },
  reference: { pickData: { selectorType: "edge" } }
});

test("measurementFromPicks reports the acute angle between skew planar faces", () => {
  // A 45 degree chamfer: outward normals sit 135 degrees apart, but the number a
  // machinist wants quoted is 45, so the acute angle between the planes is used.
  const result = measurementFromPicks(
    planePick([0, 0, 1], [0, 0, 0]),
    planePick([Math.SQRT1_2, 0, -Math.SQRT1_2], [10, 0, 0])
  );
  assert.equal(Math.round(result.angleDeg), 45);
  assert.equal(result.perpendicular, null);
});

test("measurementFromPicks reports perpendicular distance and no angle for parallel planes", () => {
  const result = measurementFromPicks(
    planePick([0, 0, 1], [0, 0, 0]),
    planePick([0, 0, -1], [7, 9, 20])
  );
  assert.equal(result.perpendicular, 20);
  assert.equal(result.angleDeg, null);
});

test("measurementFromPicks reports the angle between two straight edges", () => {
  const result = measurementFromPicks(linePick([1, 0, 0], [0, 0, 0]), linePick([0, 1, 0], [5, 0, 0]));
  assert.equal(Math.round(result.angleDeg), 90);
  const parallel = measurementFromPicks(linePick([1, 0, 0], [0, 0, 0]), linePick([-1, 0, 0], [5, 0, 0]));
  assert.equal(Math.round(parallel.angleDeg), 0);
});

test("measurementFromPicks refuses plane and edge relations for picks that never snapped", () => {
  // A free pick landed somewhere on the mesh the reference does not describe, so
  // its plane would be a fiction and must not produce a perpendicular or angle.
  const freeFace = { ...planePick([0, 0, 1], [0, 0, 0]), snapKind: "free" };
  const result = measurementFromPicks(freeFace, planePick([0, 0, -1], [0, 0, 20]));
  assert.equal(result.perpendicular, null);
  assert.equal(result.angleDeg, null);
  assert.equal(result.euclidean, 20);

  const freeEdge = { ...linePick([1, 0, 0], [0, 0, 0]), snapKind: "free" };
  assert.equal(measurementFromPicks(freeEdge, linePick([0, 1, 0], [5, 0, 0])).angleDeg, null);
});

test("entityMeasurementFromPick reports what a single edge or face is worth on its own", () => {
  const circle = entityMeasurementFromPick({
    snapKind: "edge",
    geometry: { kind: "arc", radius: 4, center: [1, 2, 3] },
    reference: { pickData: { selectorType: "edge", length: 25.13 } }
  });
  assert.equal(circle.diameter, 8);
  assert.equal(circle.radius, 4);
  assert.equal(circle.length, 25.13);
  assert.deepEqual(circle.center, [1, 2, 3]);

  const line = entityMeasurementFromPick({
    snapKind: "edge",
    geometry: { kind: "line", direction: [1, 0, 0] },
    reference: { pickData: { selectorType: "edge", length: 100 } }
  });
  assert.equal(line.length, 100);
  assert.equal(line.diameter, undefined);

  const face = entityMeasurementFromPick({
    snapKind: "face",
    reference: { pickData: { selectorType: "face", surfaceType: "cylinder", area: 314.16, params: { radius: 5 } } }
  });
  assert.equal(face.area, 314.16);
  assert.equal(face.diameter, 10);

  // Nothing measurable, no reference, or a pick that never snapped yields nothing.
  assert.equal(entityMeasurementFromPick({ snapKind: "face", reference: { pickData: { selectorType: "face" } } }), null);
  assert.equal(entityMeasurementFromPick({ snapKind: "free", reference: { pickData: { selectorType: "face", area: 1 } } }), null);
  assert.equal(entityMeasurementFromPick(null), null);
});

test("formatEntityMeasurement leads with diameter, then length, then area", () => {
  assert.equal(
    formatEntityMeasurement({ diameter: 8, radius: 4, length: 25.132, unit: "mm" }),
    "⌀ 8.00 mm  L 25.13 mm"
  );
  assert.equal(formatEntityMeasurement({ area: 6000, unit: "mm" }), "A 6000.00 mm²");
  assert.equal(formatEntityMeasurement({ length: 100, unit: "mm" }, { precision: 0 }), "L 100 mm");
  assert.equal(formatEntityMeasurement(null), "");
});

test("formatMeasurementAngle renders degrees only when an angle exists", () => {
  assert.equal(formatMeasurementAngle({ angleDeg: 45 }), "45.0°");
  assert.equal(formatMeasurementAngle({ angleDeg: 45.67 }, { precision: 2 }), "45.67°");
  assert.equal(formatMeasurementAngle({ angleDeg: null }), "");
  assert.equal(formatMeasurementAngle(null), "");
});

test("entityMeasurementFromPick ignores explicit null quantities rather than reporting zero", () => {
  // The pickData constructor emits `length: null` / `area: null` for entities that
  // have neither. Number(null) is 0, so these must be rejected before coercion.
  const face = entityMeasurementFromPick({
    snapKind: "face",
    reference: { pickData: { selectorType: "face", surfaceType: "plane", area: 6000, length: null } }
  });
  assert.equal(face.area, 6000);
  assert.equal(face.length, undefined);

  const edge = entityMeasurementFromPick({
    snapKind: "edge",
    geometry: { kind: "line", direction: [1, 0, 0] },
    reference: { pickData: { selectorType: "edge", length: 12, area: null } }
  });
  assert.equal(edge.length, 12);
  assert.equal(edge.radius, undefined);
  assert.equal(edge.diameter, undefined);
});

test("edgeGeometryFromSegments recovers a circle from its tessellation", () => {
  // The artifact labels a circular edge's curveType "cylinder" and ships no edge
  // params, so radius and centre have to come from the geometry itself.
  const arcSegments = (cx, cy, r, from, to, count) => {
    const segments = [];
    for (let index = 0; index < count; index += 1) {
      const a = from + (((to - from) * index) / count);
      const b = from + (((to - from) * (index + 1)) / count);
      segments.push(cx + (r * Math.cos(a)), cy + (r * Math.sin(a)), 10);
      segments.push(cx + (r * Math.cos(b)), cy + (r * Math.sin(b)), 10);
    }
    return segments;
  };

  // A closed circle's first and last tessellation points coincide, which
  // collapses a circumcircle taken from the ends.
  const closed = edgeGeometryFromSegments(arcSegments(35, 20, 4, 0, 2 * Math.PI, 64));
  assert.equal(closed.kind, "arc");
  assert.ok(Math.abs(closed.radius - 4) < 1e-6);
  assert.ok(Math.abs(closed.center[0] - 35) < 1e-6);
  assert.ok(Math.abs(closed.center[1] - 20) < 1e-6);

  const quarter = edgeGeometryFromSegments(arcSegments(-10, 7, 12.5, 0, Math.PI / 2, 24));
  assert.equal(quarter.kind, "arc");
  assert.ok(Math.abs(quarter.radius - 12.5) < 1e-6);

  assert.deepEqual(
    edgeGeometryFromSegments([0, 0, 0, 5, 0, 0, 5, 0, 0, 10, 0, 0]),
    { kind: "line", direction: [1, 0, 0] }
  );
  // A doubled-back polyline is neither, and must not be reported as a radius.
  assert.equal(edgeGeometryFromSegments([0, 0, 0, 1, 3, 0, 1, 3, 0, 2, 3.2, 0, 2, 3.2, 0, 9, 1, 0]).kind, "curve");
  assert.equal(edgeGeometryFromSegments(null), null);
});

test("classifyMeasurePick attaches derived geometry to edge snaps only", () => {
  const edge = classifyMeasurePick({
    reference: { id: "e1", selectorType: "edge", pickData: { selectorType: "edge" } },
    hitPoint: [2, 1, 0],
    edgeSegments: [0, 0, 0, 4, 0, 0]
  });
  assert.deepEqual(edge.geometry, { kind: "line", direction: [1, 0, 0] });

  const face = classifyMeasurePick({
    reference: { id: "f1", selectorType: "face", pickData: { selectorType: "face", normal: [0, 0, 1] } },
    hitPoint: [2, 1, 0]
  });
  assert.equal(face.geometry, null);
});

test("measurementFromPicks reports centre-to-centre spacing for two circular edges", () => {
  // Two holes 70 mm apart, clicked at arbitrary points on their rims: the rim
  // points are ~62 mm apart, but the spacing that matters is 70.
  const holeA = { snapKind: "edge", point: [-31, 20, 10], geometry: { kind: "arc", radius: 4, center: [-35, 20, 10] } };
  const holeB = { snapKind: "edge", point: [31, 20, 10], geometry: { kind: "arc", radius: 4, center: [35, 20, 10] } };
  const result = measurementFromPicks(holeA, holeB);
  assert.equal(result.centerDistance, 70);
  assert.equal(result.euclidean, 62);
  assert.equal(formatMeasurement(result), "70.00 mm");

  // One rim and one flat: no centres to compare, so the straight distance stands.
  const flat = { snapKind: "face", point: [35, 20, 10], reference: { pickData: { selectorType: "face" } } };
  assert.equal(measurementFromPicks(holeA, flat).centerDistance, null);
});

test("formatMeasurement prefers perpendicular, then centre distance, then straight distance", () => {
  assert.equal(formatMeasurement({ euclidean: 62, centerDistance: 70, perpendicular: 20, unit: "mm" }), "20.00 mm");
  assert.equal(formatMeasurement({ euclidean: 62, centerDistance: 70, perpendicular: null, unit: "mm" }), "70.00 mm");
  assert.equal(formatMeasurement({ euclidean: 62, centerDistance: null, perpendicular: null, unit: "mm" }), "62.00 mm");
});

test("two points on one face measure the distance between them, not zero", () => {
  // The commonest measurement there is. Both picks share a face, so the
  // separation lies entirely IN the plane and the perpendicular distance along
  // its normal is exactly 0. Reporting that reads as "0.00 mm" and collapses the
  // dimension line to zero length, so the tool looks broken.
  const face = { pickData: { selectorType: "face", surfaceType: "plane", normal: [0, 0, 1] } };
  const a = { snapKind: "face", point: [0, 0, 10], referenceId: "o1.1.f8", reference: face };
  const b = { snapKind: "face", point: [30, 40, 10], referenceId: "o1.1.f8", reference: face };

  const result = measurementFromPicks(a, b);
  assert.equal(result.perpendicular, null);
  assert.equal(result.angleDeg, null);
  assert.equal(result.euclidean, 50);
  assert.equal(formatMeasurement(result), "50.00 mm");
});

test("coplanar picks on different faces also have no perpendicular reading", () => {
  // Two separate flats milled to the same height: parallel and distinct, but with
  // nothing between them to report.
  const plane = (id) => ({
    snapKind: "face",
    referenceId: id,
    reference: { pickData: { selectorType: "face", surfaceType: "plane", normal: [0, 0, 1] } }
  });
  const result = measurementFromPicks(
    { ...plane("f1"), point: [0, 0, 10] },
    { ...plane("f2"), point: [30, 40, 10] }
  );
  assert.equal(result.perpendicular, null);
  assert.equal(result.euclidean, 50);
});

test("genuinely separated parallel faces still report perpendicular distance", () => {
  const plane = (id, normal) => ({
    snapKind: "face",
    referenceId: id,
    reference: { pickData: { selectorType: "face", surfaceType: "plane", normal } }
  });
  const result = measurementFromPicks(
    { ...plane("top", [0, 0, 1]), point: [0, 0, 10] },
    { ...plane("bottom", [0, 0, -1]), point: [30, 40, -10] }
  );
  assert.equal(result.perpendicular, 20);
  assert.equal(formatMeasurement(result), "20.00 mm");
});

test("classifyMeasurePick accepts a precomputed edge fit and derives one otherwise", () => {
  const reference = { id: "e1", selectorType: "edge", pickData: { selectorType: "edge" } };
  const segments = [0, 0, 0, 4, 0, 0];

  // Omitted: derived from the segments, so the fit always matches what was snapped.
  assert.deepEqual(
    classifyMeasurePick({ reference, hitPoint: [2, 1, 0], edgeSegments: segments }).geometry,
    { kind: "line", direction: [1, 0, 0] }
  );

  // Supplied: reused as-is, which is what lets a caller hovering one edge frame
  // after frame skip refitting it every tick.
  const precomputed = { kind: "arc", radius: 9, center: [1, 2, 3] };
  assert.equal(
    classifyMeasurePick({ reference, hitPoint: [2, 1, 0], edgeSegments: segments, edgeGeometry: precomputed }).geometry,
    precomputed
  );

  // An explicit null means "this edge has no usable fit", not "derive one".
  assert.equal(
    classifyMeasurePick({ reference, hitPoint: [2, 1, 0], edgeSegments: segments, edgeGeometry: null }).geometry,
    null
  );
});

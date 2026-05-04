function finitePoint3(value) {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const point = value.slice(0, 3).map((component) => Number(component));
  return point.every(Number.isFinite) ? point : null;
}

function roundedPointKey(point) {
  return point.map((component) => String(Math.round(component * 100000) / 100000)).join(",");
}

function sameFinitePoint(a, b) {
  return !!(a && b) && Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) <= 1e-7;
}

function typedArrayLength(value) {
  return Number.isFinite(Number(value?.length)) ? Number(value.length) : 0;
}

function uniqueStringList(values) {
  const seen = new Set();
  const result = [];
  for (const value of Array.isArray(values) ? values : []) {
    const normalizedValue = String(value || "").trim();
    if (!normalizedValue || seen.has(normalizedValue)) {
      continue;
    }
    seen.add(normalizedValue);
    result.push(normalizedValue);
  }
  return result;
}

function pointFromProxyPosition(positions, pointIndex) {
  const offset = Number(pointIndex) * 3;
  if (!Number.isInteger(offset) || offset < 0 || offset + 2 >= typedArrayLength(positions)) {
    return null;
  }
  return finitePoint3([positions[offset], positions[offset + 1], positions[offset + 2]]);
}

function edgeProxyPoints(reference, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  const positions = proxy.edgePositions;
  const indices = proxy.edgeIndices;
  const edgeIds = proxy.edgeIds;
  if (!(positions instanceof Float32Array) || !(indices instanceof Uint32Array)) {
    return [];
  }

  const pickData = reference?.pickData || {};
  const segmentStart = Math.max(0, Number(pickData.segmentStart || 0));
  const segmentCount = Math.max(0, Number(pickData.segmentCount || 0));
  const rowIndex = pickData.rowIndex === null || pickData.rowIndex === undefined
    ? NaN
    : Number(pickData.rowIndex);
  const points = [];
  const appendPoint = (point) => {
    if (!point) {
      return;
    }
    const previous = points[points.length - 1];
    if (!previous || !sameFinitePoint(previous, point)) {
      points.push(point);
    }
  };
  const appendSegment = (segmentIndex) => {
    const firstPointIndex = indices[segmentIndex * 2];
    const secondPointIndex = indices[(segmentIndex * 2) + 1];
    appendPoint(pointFromProxyPosition(positions, firstPointIndex));
    appendPoint(pointFromProxyPosition(positions, secondPointIndex));
  };

  if (segmentCount > 0 && Number.isFinite(segmentStart)) {
    const end = Math.min(segmentStart + segmentCount, Math.floor(typedArrayLength(indices) / 2));
    for (let segmentIndex = segmentStart; segmentIndex < end; segmentIndex += 1) {
      appendSegment(segmentIndex);
    }
    return points;
  }

  if (Number.isInteger(rowIndex) && edgeIds) {
    for (let segmentIndex = 0; segmentIndex < typedArrayLength(edgeIds); segmentIndex += 1) {
      if (Number(edgeIds[segmentIndex]) === rowIndex) {
        appendSegment(segmentIndex);
      }
    }
  }

  return points;
}

function addMeasurePointReference(pointMap, {
  reference,
  center,
  measurePointKind,
  selectorSuffix,
  summary,
  radius = null
}) {
  const point = finitePoint3(center);
  if (!point) {
    return;
  }
  const pickData = reference?.pickData || {};
  const partId = String(reference?.partId || "").trim();
  const key = `${partId}|${roundedPointKey(point)}`;
  const adjacentSelectors = uniqueStringList([
    reference?.displaySelector,
    reference?.normalizedSelector,
    ...(Array.isArray(pickData.adjacentSelectors) ? pickData.adjacentSelectors : [])
  ]);
  const existing = pointMap.get(key);
  if (existing) {
    existing.pickData.adjacentSelectors = uniqueStringList([
      ...existing.pickData.adjacentSelectors,
      ...adjacentSelectors
    ]);
    existing.pickData.sourceReferenceIds = uniqueStringList([
      ...existing.pickData.sourceReferenceIds,
      reference?.id
    ]);
    return;
  }
  const sourceSelector = String(reference?.displaySelector || reference?.normalizedSelector || reference?.id || "").trim();
  const normalizedSuffix = String(selectorSuffix || measurePointKind || "point").trim();
  const sourceId = String(reference?.id || key).trim();
  pointMap.set(key, {
    id: `measure-point|${sourceId}|${normalizedSuffix}`,
    selectorType: "vertex",
    normalizedSelector: sourceSelector ? `${sourceSelector}:${normalizedSuffix}` : `measure-point:${key}`,
    displaySelector: sourceSelector ? `${sourceSelector}:${normalizedSuffix}` : "measure point",
    label: sourceSelector ? `${summary} ${sourceSelector}` : summary,
    summary,
    shortSummary: summary,
    copyText: reference?.copyText || "",
    partId: reference?.partId || "",
    occurrenceId: reference?.occurrenceId || "",
    shapeId: reference?.shapeId || "",
    rowIndex: null,
    pickData: {
      selectorType: "vertex",
      kind: "measure-point",
      measurePointKind,
      sourceReferenceId: reference?.id || "",
      sourceReferenceIds: uniqueStringList([reference?.id]),
      sourceSelectorType: reference?.selectorType || "",
      sourceCurveType: pickData.curveType || "",
      center: point,
      radius: Number.isFinite(Number(radius)) ? Number(radius) : null,
      adjacentSelectors,
      transform: pickData.transform || null
    }
  });
}

export function buildMeasurePointReferences(edgeReferences, selectorRuntime) {
  const pointMap = new Map();
  for (const reference of Array.isArray(edgeReferences) ? edgeReferences : []) {
    if (String(reference?.selectorType || "").trim().toLowerCase() !== "edge") {
      continue;
    }
    const pickData = reference?.pickData || {};
    const curveType = String(pickData.curveType || "").trim().toLowerCase();
    const params = pickData.params || {};
    const radius = Number(params.radius);
    if (Number.isFinite(radius) && radius > 0 && (curveType.includes("circle") || curveType.includes("arc"))) {
      addMeasurePointReference(pointMap, {
        reference,
        center: finitePoint3(params.center) || finitePoint3(pickData.center),
        measurePointKind: "circle-center",
        selectorSuffix: "center",
        summary: "Circle center",
        radius
      });
    }

    const proxyPoints = edgeProxyPoints(reference, selectorRuntime);
    if (proxyPoints.length >= 2 && (!curveType.includes("circle") || curveType.includes("arc"))) {
      const startPoint = proxyPoints[0];
      const endPoint = proxyPoints[proxyPoints.length - 1];
      addMeasurePointReference(pointMap, {
        reference,
        center: startPoint,
        measurePointKind: "edge-endpoint",
        selectorSuffix: "start",
        summary: "Edge endpoint"
      });
      if (!sameFinitePoint(startPoint, endPoint)) {
        addMeasurePointReference(pointMap, {
          reference,
          center: endPoint,
          measurePointKind: "edge-endpoint",
          selectorSuffix: "end",
          summary: "Edge endpoint"
        });
      }
    }
  }
  return [...pointMap.values()];
}

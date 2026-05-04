const EPSILON = 1e-9;

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function lower(value) {
  return String(value || "").trim().toLowerCase();
}

export function point3(value) {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const point = value.slice(0, 3).map((component) => Number(component));
  return point.every(Number.isFinite) ? point : null;
}

function vector3(value) {
  const vector = point3(value);
  if (!vector) {
    return null;
  }
  const vectorLength = Math.hypot(vector[0], vector[1], vector[2]);
  if (vectorLength <= EPSILON) {
    return null;
  }
  return [vector[0] / vectorLength, vector[1] / vectorLength, vector[2] / vectorLength];
}

function distanceBetweenPoints(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

function samePoint(a, b) {
  return distanceBetweenPoints(a, b) <= EPSILON;
}

export function formatNumber(value, digits = 3) {
  const numericValue = finiteNumber(value);
  if (numericValue === null) {
    return "";
  }
  const rounded = Math.round(numericValue * (10 ** digits)) / (10 ** digits);
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

export function formatPoint(point) {
  const normalizedPoint = point3(point);
  if (!normalizedPoint) {
    return "";
  }
  return normalizedPoint.map((component) => formatNumber(component)).join(", ");
}

export function formatMeasurementValue(value, unit = "mm") {
  const formatted = formatNumber(value);
  if (!formatted) {
    return "";
  }
  if (unit === "deg") {
    return `${formatted} deg`;
  }
  if (unit === "mm2") {
    return `${formatted} mm^2`;
  }
  if (unit === "mm3") {
    return `${formatted} mm^3`;
  }
  return `${formatted} ${unit || "mm"}`;
}

function measurementResult({
  kind,
  title,
  value,
  unit = "mm",
  detail = "",
  referenceIds = []
}) {
  const numericValue = finiteNumber(value);
  if (numericValue === null) {
    return null;
  }
  return {
    kind,
    title,
    value: numericValue,
    unit,
    detail: String(detail || "").trim(),
    referenceIds: referenceIds.map((id) => String(id || "").trim()).filter(Boolean)
  };
}

function typedLength(value) {
  return Number.isFinite(Number(value?.length)) ? Number(value.length) : 0;
}

function pointFromProxyPosition(positions, pointIndex) {
  const offset = Number(pointIndex) * 3;
  if (!Number.isInteger(offset) || offset < 0 || offset + 2 >= typedLength(positions)) {
    return null;
  }
  return point3([positions[offset], positions[offset + 1], positions[offset + 2]]);
}

function edgeProxyPoints(reference, selectorRuntime) {
  const proxy = selectorRuntime?.proxy || {};
  const positions = proxy.edgePositions;
  const indices = proxy.edgeIndices;
  const edgeIds = proxy.edgeIds;
  if (!positions || !indices) {
    return [];
  }

  const pickData = reference?.pickData || {};
  const segmentStart = Math.max(0, Number(pickData.segmentStart || 0));
  const segmentCount = Math.max(0, Number(pickData.segmentCount || 0));
  const rowIndex = finiteNumber(pickData.rowIndex);
  const points = [];

  const appendPoint = (point) => {
    if (!point) {
      return;
    }
    const previous = points[points.length - 1];
    if (!previous || !samePoint(previous, point)) {
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
    const end = Math.min(segmentStart + segmentCount, Math.floor(typedLength(indices) / 2));
    for (let segmentIndex = segmentStart; segmentIndex < end; segmentIndex += 1) {
      appendSegment(segmentIndex);
    }
    return points;
  }

  if (rowIndex !== null && edgeIds) {
    for (let segmentIndex = 0; segmentIndex < typedLength(edgeIds); segmentIndex += 1) {
      if (Number(edgeIds[segmentIndex]) === rowIndex) {
        appendSegment(segmentIndex);
      }
    }
  }

  return points;
}

function midpointFromPoints(points) {
  if (!Array.isArray(points) || !points.length) {
    return null;
  }
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) {
    return null;
  }
  return [
    (first[0] + last[0]) / 2,
    (first[1] + last[1]) / 2,
    (first[2] + last[2]) / 2
  ];
}

function edgeEndpoints(reference, selectorRuntime) {
  const points = edgeProxyPoints(reference, selectorRuntime);
  if (points.length < 2) {
    return null;
  }
  return [points[0], points[points.length - 1]];
}

function inferredPoint(reference, selectorRuntime) {
  const selectorType = lower(reference?.selectorType);
  if (selectorType === "edge") {
    return point3(reference?.pickData?.center) || midpointFromPoints(edgeProxyPoints(reference, selectorRuntime));
  }
  if (selectorType === "face" || selectorType === "shape") {
    return point3(reference?.pickData?.center);
  }
  return point3(reference?.pickData?.center);
}

function lineDirection(reference, selectorRuntime) {
  if (lower(reference?.selectorType) !== "edge") {
    return null;
  }
  const curveType = lower(reference?.pickData?.curveType);
  if (curveType && curveType !== "line") {
    return null;
  }
  const paramDirection = vector3(reference?.pickData?.params?.direction);
  if (paramDirection) {
    return paramDirection;
  }
  const endpoints = edgeEndpoints(reference, selectorRuntime);
  if (!endpoints) {
    return null;
  }
  return vector3([
    endpoints[1][0] - endpoints[0][0],
    endpoints[1][1] - endpoints[0][1],
    endpoints[1][2] - endpoints[0][2]
  ]);
}

function faceNormal(reference) {
  if (lower(reference?.selectorType) !== "face") {
    return null;
  }
  const surfaceType = lower(reference?.pickData?.surfaceType);
  if (surfaceType && surfaceType !== "plane") {
    return null;
  }
  return vector3(reference?.pickData?.normal) || vector3(reference?.pickData?.params?.axis);
}

function acuteAngleBetweenVectors(a, b) {
  if (!a || !b) {
    return null;
  }
  const cosine = Math.min(Math.max(Math.abs((a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])), -1), 1);
  return (Math.acos(cosine) * 180) / Math.PI;
}

function angleBetweenLineEdges(a, b, selectorRuntime) {
  return acuteAngleBetweenVectors(
    lineDirection(a, selectorRuntime),
    lineDirection(b, selectorRuntime)
  );
}

function angleBetweenPlanarFaces(a, b) {
  return acuteAngleBetweenVectors(faceNormal(a), faceNormal(b));
}

function referenceRadius(reference) {
  const params = reference?.pickData?.params || {};
  return finiteNumber(params.radius);
}

function measurementsForSingleReference(reference, selectorRuntime) {
  const selectorType = lower(reference?.selectorType);
  const pickData = reference?.pickData || {};
  const referenceIds = [reference?.id];
  const results = [];

  if (selectorType === "edge") {
    const length = finiteNumber(pickData.length);
    const radius = referenceRadius(reference);
    const center = inferredPoint(reference, selectorRuntime);
    const curveType = lower(pickData.curveType);
    const centerDetail = center ? `Center ${formatPoint(center)}` : "";
    const midpointDetail = center ? `Midpoint ${formatPoint(center)}` : "";

    if (radius !== null && (curveType.includes("circle") || curveType.includes("arc"))) {
      results.push(measurementResult({
        kind: "radius",
        title: "Radius",
        value: radius,
        detail: [`Diameter ${formatMeasurementValue(radius * 2)}`, centerDetail].filter(Boolean).join(" | "),
        referenceIds
      }));
    }

    if (length !== null) {
      results.push(measurementResult({
        kind: "length",
        title: "Edge length",
        value: length,
        detail: midpointDetail,
        referenceIds
      }));
    }
  }

  if (selectorType === "face") {
    const radius = referenceRadius(reference);
    const area = finiteNumber(pickData.area);
    const surfaceType = lower(pickData.surfaceType);

    if (radius !== null && (surfaceType.includes("cylinder") || surfaceType.includes("sphere"))) {
      results.push(measurementResult({
        kind: "radius",
        title: "Radius",
        value: radius,
        detail: `Diameter ${formatMeasurementValue(radius * 2)}`,
        referenceIds
      }));
    }

    if (area !== null) {
      results.push(measurementResult({
        kind: "area",
        title: "Surface area",
        value: area,
        unit: "mm2",
        referenceIds
      }));
    }
  }

  if (selectorType === "shape") {
    const volume = finiteNumber(pickData.volume);
    const area = finiteNumber(pickData.area);
    if (volume !== null) {
      results.push(measurementResult({
        kind: "volume",
        title: "Volume",
        value: volume,
        unit: "mm3",
        referenceIds
      }));
    }
    if (area !== null) {
      results.push(measurementResult({
        kind: "area",
        title: "Surface area",
        value: area,
        unit: "mm2",
        referenceIds
      }));
    }
  }

  return results.filter(Boolean);
}

function measurementsForTwoReferences(references, selectorRuntime) {
  const [first, second] = references;
  const firstType = lower(first?.selectorType);
  const secondType = lower(second?.selectorType);
  const referenceIds = references.map((reference) => reference?.id);
  const results = [];

  if (firstType === "edge" && secondType === "edge") {
    const angle = angleBetweenLineEdges(first, second, selectorRuntime);
    if (angle !== null) {
      results.push(measurementResult({
        kind: "angle",
        title: "Edge angle",
        value: angle,
        unit: "deg",
        referenceIds
      }));
    }
  }

  if (firstType === "face" && secondType === "face") {
    const angle = angleBetweenPlanarFaces(first, second);
    if (angle !== null) {
      results.push(measurementResult({
        kind: "face-angle",
        title: "Face angle",
        value: angle,
        unit: "deg",
        referenceIds
      }));
    }
  }

  const firstPoint = inferredPoint(first, selectorRuntime);
  const secondPoint = inferredPoint(second, selectorRuntime);
  if (firstPoint && secondPoint) {
    results.push(measurementResult({
      kind: "point-distance",
      title: firstType === "edge" && secondType === "edge" ? "Midpoint distance" : "Point distance",
      value: distanceBetweenPoints(firstPoint, secondPoint),
      detail: `${formatPoint(firstPoint)} to ${formatPoint(secondPoint)}`,
      referenceIds
    }));
  }

  return results.filter(Boolean);
}

export function measurementsForReferences(references, selectorRuntime = null) {
  const normalizedReferences = (Array.isArray(references) ? references : []).filter(Boolean);
  if (normalizedReferences.length === 1) {
    return measurementsForSingleReference(normalizedReferences[0], selectorRuntime);
  }
  if (normalizedReferences.length === 2) {
    return measurementsForTwoReferences(normalizedReferences, selectorRuntime);
  }
  return [];
}

export function measurementForReferences(references, selectorRuntime = null) {
  return measurementsForReferences(references, selectorRuntime)[0] || null;
}

export function measurementKey(result) {
  const numericValue = finiteNumber(result?.value);
  if (numericValue === null) {
    return "";
  }
  return [
    result.kind || "",
    result.unit || "mm",
    formatNumber(numericValue),
    ...(Array.isArray(result.referenceIds) ? result.referenceIds : [])
  ].join("|");
}

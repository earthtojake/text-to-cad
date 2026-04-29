function finiteNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function point3(value) {
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
  if (vectorLength <= 1e-9) {
    return null;
  }
  return [vector[0] / vectorLength, vector[1] / vectorLength, vector[2] / vectorLength];
}

function distanceBetweenPoints(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

function formatPoint(point) {
  if (!point3(point)) {
    return "";
  }
  return point.slice(0, 3)
    .map((component) => {
      const rounded = Math.round(Number(component) * 1000) / 1000;
      return Object.is(rounded, -0) ? 0 : rounded;
    })
    .join(", ");
}

function lineDirection(reference) {
  if (String(reference?.selectorType || "").trim() !== "edge") {
    return null;
  }
  const curveType = String(reference?.pickData?.curveType || "").trim().toLowerCase();
  if (curveType && curveType !== "line") {
    return null;
  }
  return vector3(reference?.pickData?.params?.direction);
}

function faceNormal(reference) {
  if (String(reference?.selectorType || "").trim() !== "face") {
    return null;
  }
  const surfaceType = String(reference?.pickData?.surfaceType || "").trim().toLowerCase();
  if (surfaceType && surfaceType !== "plane") {
    return null;
  }
  return vector3(reference?.pickData?.normal);
}

function angleBetweenLineEdges(a, b) {
  const left = lineDirection(a);
  const right = lineDirection(b);
  if (!left || !right) {
    return null;
  }
  const cosine = Math.min(Math.max(Math.abs((left[0] * right[0]) + (left[1] * right[1]) + (left[2] * right[2])), -1), 1);
  return (Math.acos(cosine) * 180) / Math.PI;
}

function angleBetweenPlanarFaces(a, b) {
  const left = faceNormal(a);
  const right = faceNormal(b);
  if (!left || !right) {
    return null;
  }
  const cosine = Math.min(Math.max(Math.abs((left[0] * right[0]) + (left[1] * right[1]) + (left[2] * right[2])), -1), 1);
  return (Math.acos(cosine) * 180) / Math.PI;
}

export function formatMeasurementValue(value, unit = "mm") {
  const numericValue = finiteNumber(value);
  if (numericValue === null) {
    return "";
  }
  const rounded = Math.round(numericValue * 1000) / 1000;
  return `${Object.is(rounded, -0) ? 0 : rounded}${unit === "deg" ? " deg" : ` ${unit}`}`;
}

export function measurementForSingleReference(reference) {
  const selectorType = String(reference?.selectorType || "").trim();
  const pickData = reference?.pickData || {};
  const params = pickData.params || {};

  if (selectorType === "edge") {
    const length = finiteNumber(pickData.length);
    const radius = finiteNumber(params.radius);
    const center = point3(pickData.center);
    const curveType = String(pickData.curveType || "").trim().toLowerCase();
    if (radius !== null && (curveType.includes("circle") || curveType.includes("arc"))) {
      return {
        kind: "radius",
        title: "Radius",
        value: radius,
        detail: `Diameter ${formatMeasurementValue(radius * 2)}${center ? ` | Center ${formatPoint(center)}` : ""}`,
        referenceIds: [reference.id]
      };
    }
    if (length !== null) {
      return {
        kind: "length",
        title: "Edge length",
        value: length,
        detail: center ? `Midpoint ${formatPoint(center)}` : "",
        referenceIds: [reference.id]
      };
    }
  }

  if (selectorType === "face") {
    const radius = finiteNumber(params.radius);
    const area = finiteNumber(pickData.area);
    const surfaceType = String(pickData.surfaceType || "").trim().toLowerCase();
    if (radius !== null && surfaceType.includes("cylinder")) {
      return {
        kind: "radius",
        title: "Radius",
        value: radius,
        detail: `Diameter ${formatMeasurementValue(radius * 2)}`,
        referenceIds: [reference.id]
      };
    }
    if (area !== null) {
      return {
        kind: "area",
        title: "Surface area",
        value: area,
        unit: "mm^2",
        detail: "",
        referenceIds: [reference.id]
      };
    }
  }

  return null;
}

export function measurementForReferences(references) {
  const normalizedReferences = (Array.isArray(references) ? references : []).filter(Boolean);
  if (normalizedReferences.length === 1) {
    return measurementForSingleReference(normalizedReferences[0]);
  }
  if (normalizedReferences.length === 2 && normalizedReferences.every((reference) => reference.selectorType === "vertex")) {
    const start = point3(normalizedReferences[0]?.pickData?.center);
    const end = point3(normalizedReferences[1]?.pickData?.center);
    if (start && end) {
      return {
        kind: "distance",
        title: "Point distance",
        value: distanceBetweenPoints(start, end),
        detail: "",
        referenceIds: normalizedReferences.map((reference) => reference.id)
      };
    }
  }
  if (normalizedReferences.length === 2 && normalizedReferences.every((reference) => reference.selectorType === "edge")) {
    const angle = angleBetweenLineEdges(normalizedReferences[0], normalizedReferences[1]);
    if (angle !== null) {
      return {
        kind: "angle",
        title: "Angle",
        value: angle,
        unit: "deg",
        detail: "",
        referenceIds: normalizedReferences.map((reference) => reference.id)
      };
    }
  }
  if (normalizedReferences.length === 2 && normalizedReferences.every((reference) => reference.selectorType === "face")) {
    const angle = angleBetweenPlanarFaces(normalizedReferences[0], normalizedReferences[1]);
    if (angle !== null) {
      return {
        kind: "face-angle",
        title: "Face angle",
        value: angle,
        unit: "deg",
        detail: "",
        referenceIds: normalizedReferences.map((reference) => reference.id)
      };
    }
  }
  return null;
}

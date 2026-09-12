export const SURFACE_LINE_UNSUPPORTED_TYPES = new Set(["", "SPHERICAL_SURFACE", "TOROIDAL_SURFACE", "BSPLINE_SURFACE"]);

function length(vector) {
  return Math.hypot(vector[0], vector[1], vector[2]);
}

function normalizeVector3(vector) {
  const magnitude = length(vector);
  if (magnitude <= 1e-9) {
    return null;
  }
  return [vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude];
}

function subtract(a, b) {
  return [Number(a[0]) - Number(b[0]), Number(a[1]) - Number(b[1]), Number(a[2]) - Number(b[2])];
}

function dot(a, b) {
  return (Number(a[0]) * Number(b[0])) + (Number(a[1]) * Number(b[1])) + (Number(a[2]) * Number(b[2]));
}

function normalizeAngleAround(angle, center) {
  let adjusted = angle;
  while (adjusted - center > Math.PI) {
    adjusted -= Math.PI * 2;
  }
  while (adjusted - center < -Math.PI) {
    adjusted += Math.PI * 2;
  }
  return adjusted;
}

function clonePoint3(point) {
  return Array.isArray(point) && point.length >= 3
    ? [Number(point[0]), Number(point[1]), Number(point[2])]
    : null;
}

function clonePoint2(point) {
  return Array.isArray(point) && point.length >= 2
    ? [Number(point[0]), Number(point[1])]
    : null;
}

export function projectPointToPlane(point, surface) {
  if (!Array.isArray(point) || !Array.isArray(surface?.origin) || !Array.isArray(surface?.xDir) || !Array.isArray(surface?.yDir)) {
    return null;
  }
  const relative = subtract(point, surface.origin);
  return [dot(relative, surface.xDir), dot(relative, surface.yDir)];
}

export function projectPointToCylinder(point, surface, angleCenter = null) {
  if (
    !Array.isArray(point) ||
    !Array.isArray(surface?.origin) ||
    !Array.isArray(surface?.axis) ||
    !Array.isArray(surface?.xDir) ||
    !Array.isArray(surface?.yDir) ||
    Number(surface?.radius) <= 0
  ) {
    return null;
  }
  const radius = Number(surface.radius);
  const relative = subtract(point, surface.origin);
  const axial = dot(relative, surface.axis);
  const radial = [
    relative[0] - (Number(surface.axis[0]) * axial),
    relative[1] - (Number(surface.axis[1]) * axial),
    relative[2] - (Number(surface.axis[2]) * axial)
  ];
  const rawAngle = Math.atan2(dot(radial, surface.yDir), dot(radial, surface.xDir));
  const center = Number(angleCenter);
  const angle = Number.isFinite(center) ? normalizeAngleAround(rawAngle, center) : rawAngle;
  return [angle * radius, axial];
}

export function projectPointToSurfaceUv(surface, point, angleCenter = null) {
  if (!surface || !Array.isArray(point) || point.length < 3) {
    return null;
  }
  if (
    surface.type === "PLANE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir)
  ) {
    return projectPointToPlane(point, surface);
  }
  if (
    surface.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.axis) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir) &&
    Number(surface.radius) > 0
  ) {
    return projectPointToCylinder(point, surface, angleCenter);
  }
  return null;
}

export function pointOnSurfaceFromUv(surface, uv) {
  if (!surface || !Array.isArray(uv) || uv.length < 2) {
    return null;
  }
  if (
    surface.type === "PLANE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir)
  ) {
    return [
      surface.origin[0] + surface.xDir[0] * uv[0] + surface.yDir[0] * uv[1],
      surface.origin[1] + surface.xDir[1] * uv[0] + surface.yDir[1] * uv[1],
      surface.origin[2] + surface.xDir[2] * uv[0] + surface.yDir[2] * uv[1]
    ];
  }
  if (
    surface.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface.origin) &&
    Array.isArray(surface.axis) &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir) &&
    Number(surface.radius) > 0
  ) {
    const radius = Number(surface.radius);
    const theta = uv[0] / radius;
    const cosTheta = Math.cos(theta);
    const sinTheta = Math.sin(theta);
    return [
      surface.origin[0] + surface.axis[0] * uv[1] + radius * (surface.xDir[0] * cosTheta + surface.yDir[0] * sinTheta),
      surface.origin[1] + surface.axis[1] * uv[1] + radius * (surface.xDir[1] * cosTheta + surface.yDir[1] * sinTheta),
      surface.origin[2] + surface.axis[2] * uv[1] + radius * (surface.xDir[2] * cosTheta + surface.yDir[2] * sinTheta)
    ];
  }
  return null;
}

export function surfaceNormalAtUv(surface, uv) {
  if (!surface || !Array.isArray(uv) || uv.length < 2) {
    return null;
  }
  if (surface.type === "PLANE") {
    return normalizeVector3(surface.normal || []);
  }
  if (
    surface.type === "CYLINDRICAL_SURFACE" &&
    Array.isArray(surface.xDir) &&
    Array.isArray(surface.yDir) &&
    Number(surface.radius) > 0
  ) {
    const theta = uv[0] / Number(surface.radius);
    return normalizeVector3([
      surface.xDir[0] * Math.cos(theta) + surface.yDir[0] * Math.sin(theta),
      surface.xDir[1] * Math.cos(theta) + surface.yDir[1] * Math.sin(theta),
      surface.xDir[2] * Math.cos(theta) + surface.yDir[2] * Math.sin(theta)
    ]);
  }
  return null;
}

export function buildSurfaceLinePositions(reference, surfaceLine, { segments = 48, offset = 0.04 } = {}) {
  const surface = reference?.pickData?.surface || {};
  const startPoint = clonePoint3(surfaceLine?.startPoint);
  const endPoint = clonePoint3(surfaceLine?.endPoint);
  const startUv = clonePoint2(surfaceLine?.startUv);
  const endUv = clonePoint2(surfaceLine?.endUv);

  if (surface.type === "PLANE" && startPoint && endPoint) {
    const normal = normalizeVector3(reference?.pickData?.normal || surface.normal || []);
    const project = (point) => normal ? [
      point[0] + normal[0] * offset,
      point[1] + normal[1] * offset,
      point[2] + normal[2] * offset
    ] : point;
    const start = project(startPoint);
    const end = project(endPoint);
    return [
      start[0], start[1], start[2],
      end[0], end[1], end[2]
    ];
  }

  if (surface.type === "CYLINDRICAL_SURFACE" && startUv && endUv) {
    const linePositions = [];
    const count = Math.max(4, Math.round(Number(segments) || 48));
    let previousPoint = null;
    for (let index = 0; index <= count; index += 1) {
      const t = index / count;
      const uv = [
        startUv[0] + (endUv[0] - startUv[0]) * t,
        startUv[1] + (endUv[1] - startUv[1]) * t
      ];
      const point = pointOnSurfaceFromUv(surface, uv);
      if (!point) {
        continue;
      }
      const normal = surfaceNormalAtUv(surface, uv);
      const offsetPoint = normal ? [
        point[0] + normal[0] * offset,
        point[1] + normal[1] * offset,
        point[2] + normal[2] * offset
      ] : point;
      if (previousPoint) {
        linePositions.push(
          previousPoint[0], previousPoint[1], previousPoint[2],
          offsetPoint[0], offsetPoint[1], offsetPoint[2]
        );
      }
      previousPoint = offsetPoint;
    }
    return linePositions;
  }

  if (startPoint && endPoint) {
    return [
      startPoint[0], startPoint[1], startPoint[2],
      endPoint[0], endPoint[1], endPoint[2]
    ];
  }

  return [];
}

import { normalizeImplicitCadModel } from "./model.js";
import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function isNumericArray(value) {
  return value instanceof Float32Array || value instanceof Float64Array || Array.isArray(value);
}

function subtract(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function normalize(v) {
  const length = Math.hypot(v[0], v[1], v[2]);
  return length > 1e-12 ? [v[0] / length, v[1] / length, v[2] / length] : [0, 0, 0];
}

function midpoint(a, b, c) {
  return [
    (a[0] + b[0] + c[0]) / 3,
    (a[1] + b[1] + c[1]) / 3,
    (a[2] + b[2] + c[2]) / 3,
  ];
}

function triangleAreaNormal(a, b, c) {
  const normal = cross(subtract(b, a), subtract(c, a));
  const doubleArea = Math.hypot(normal[0], normal[1], normal[2]);
  return {
    area: doubleArea * 0.5,
    normal: doubleArea > 1e-12 ? [normal[0] / doubleArea, normal[1] / doubleArea, normal[2] / doubleArea] : [0, 0, 0],
  };
}

function readVec3(array, offset) {
  return [array[offset], array[offset + 1], array[offset + 2]];
}

function boundsForPositions(positions) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < positions.length; index += 3) {
    min[0] = Math.min(min[0], finiteNumber(positions[index], 0));
    min[1] = Math.min(min[1], finiteNumber(positions[index + 1], 0));
    min[2] = Math.min(min[2], finiteNumber(positions[index + 2], 0));
    max[0] = Math.max(max[0], finiteNumber(positions[index], 0));
    max[1] = Math.max(max[1], finiteNumber(positions[index + 1], 0));
    max[2] = Math.max(max[2], finiteNumber(positions[index + 2], 0));
  }
  if (!min.every(Number.isFinite) || !max.every(Number.isFinite)) {
    return { min: [0, 0, 0], max: [0, 0, 0], size: [0, 0, 0], diagonal: 0 };
  }
  const size = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
  return {
    min,
    max,
    size,
    diagonal: Math.hypot(size[0], size[1], size[2]),
  };
}

function quantizedVertexKey(vertex, tolerance) {
  return vertex.map((component) => Math.round(component / tolerance)).join(",");
}

function sortedEdgeKey(a, b) {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

function sdfForOptions(options) {
  if (typeof options.sdf === "function") {
    return options.sdf;
  }
  if (options.model) {
    return createImplicitCadSdfEvaluator(normalizeImplicitCadModel(options.model));
  }
  return null;
}

function sampleNormalAlignment(normals, triangleOffset, faceNormal) {
  let worst = 1;
  for (let vertex = 0; vertex < 3; vertex += 1) {
    const normal = normalize(readVec3(normals, triangleOffset + vertex * 3));
    const length = Math.hypot(normal[0], normal[1], normal[2]);
    if (length <= 0) {
      worst = -1;
    } else {
      worst = Math.min(worst, dot(normal, faceNormal));
    }
  }
  return worst;
}

export function analyzeImplicitMeshQuality(mesh, options = {}) {
  const positions = mesh?.positions || new Float32Array();
  const normals = isNumericArray(mesh?.normals) && mesh.normals.length === positions.length ? mesh.normals : null;
  const triangleCount = Math.floor(positions.length / 9);
  const bounds = boundsForPositions(positions);
  const stepValues = Array.isArray(mesh?.grid?.step) ? mesh.grid.step.map((value) => finiteNumber(value, 0)).filter((value) => value > 0) : [];
  const minStep = stepValues.length ? Math.min(...stepValues) : Math.max(bounds.diagonal / 64, 1e-3);
  const edgeTolerance = Math.max(finiteNumber(options.edgeTolerance, 0), minStep * 1e-4, bounds.diagonal * 1e-8, 1e-7);
  const areaTolerance = Math.max(finiteNumber(options.areaTolerance, 0), minStep * minStep * 1e-10, 1e-12);
  const orientationEpsilon = Math.max(finiteNumber(options.orientationEpsilon, 0), minStep * 0.2, 1e-5);
  const orientationTolerance = Math.max(finiteNumber(options.orientationTolerance, 0), minStep * 1e-4, 1e-6);
  const maxOrientationSamples = Math.max(0, Math.floor(finiteNumber(options.maxOrientationSamples, 5000)));
  const orientationStride = maxOrientationSamples > 0 ? Math.max(1, Math.floor(triangleCount / maxOrientationSamples)) : Infinity;
  const sdf = sdfForOptions(options);
  const edgeCounts = new Map();
  let nonFinitePositions = 0;
  let nonFiniteNormals = 0;
  let degenerateTriangles = 0;
  let invertedOrientationSamples = 0;
  let ambiguousOrientationSamples = 0;
  let orientationSamples = 0;
  let poorNormalAlignment = 0;
  let worstNormalAlignment = 1;
  let minArea = Infinity;
  let maxArea = 0;

  for (let offset = 0; offset < positions.length; offset += 9) {
    const triangleIndex = offset / 9;
    const a = readVec3(positions, offset);
    const b = readVec3(positions, offset + 3);
    const c = readVec3(positions, offset + 6);
    if (![...a, ...b, ...c].every(Number.isFinite)) {
      nonFinitePositions += 1;
      continue;
    }
    const { area, normal } = triangleAreaNormal(a, b, c);
    minArea = Math.min(minArea, area);
    maxArea = Math.max(maxArea, area);
    if (area <= areaTolerance) {
      degenerateTriangles += 1;
      continue;
    }
    if (normals) {
      const alignment = sampleNormalAlignment(normals, offset, normal);
      worstNormalAlignment = Math.min(worstNormalAlignment, alignment);
      if (!Number.isFinite(alignment)) {
        nonFiniteNormals += 1;
      } else if (alignment < -0.35) {
        poorNormalAlignment += 1;
      }
    }
    const vertexKeys = [a, b, c].map((vertex) => quantizedVertexKey(vertex, edgeTolerance));
    edgeCounts.set(sortedEdgeKey(vertexKeys[0], vertexKeys[1]), (edgeCounts.get(sortedEdgeKey(vertexKeys[0], vertexKeys[1])) || 0) + 1);
    edgeCounts.set(sortedEdgeKey(vertexKeys[1], vertexKeys[2]), (edgeCounts.get(sortedEdgeKey(vertexKeys[1], vertexKeys[2])) || 0) + 1);
    edgeCounts.set(sortedEdgeKey(vertexKeys[2], vertexKeys[0]), (edgeCounts.get(sortedEdgeKey(vertexKeys[2], vertexKeys[0])) || 0) + 1);

    if (sdf && triangleIndex % orientationStride === 0) {
      const center = midpoint(a, b, c);
      const positive = finiteNumber(
        sdf(
          center[0] + normal[0] * orientationEpsilon,
          center[1] + normal[1] * orientationEpsilon,
          center[2] + normal[2] * orientationEpsilon
        ),
        1e6
      );
      const negative = finiteNumber(
        sdf(
          center[0] - normal[0] * orientationEpsilon,
          center[1] - normal[1] * orientationEpsilon,
          center[2] - normal[2] * orientationEpsilon
        ),
        1e6
      );
      orientationSamples += 1;
      if (Math.abs(positive - negative) <= orientationTolerance) {
        ambiguousOrientationSamples += 1;
      } else if (positive < negative) {
        invertedOrientationSamples += 1;
      }
    }
  }

  let boundaryEdges = 0;
  let manifoldEdges = 0;
  let nonManifoldEdges = 0;
  for (const count of edgeCounts.values()) {
    if (count === 1) {
      boundaryEdges += 1;
    } else if (count === 2) {
      manifoldEdges += 1;
    } else {
      nonManifoldEdges += 1;
    }
  }

  const edgeCount = edgeCounts.size;
  return {
    triangleCount,
    vertexCount: Math.floor(positions.length / 3),
    bounds,
    grid: mesh?.grid || null,
    minStep,
    tolerances: {
      edge: edgeTolerance,
      area: areaTolerance,
      orientation: orientationEpsilon,
    },
    triangles: {
      minArea: Number.isFinite(minArea) ? minArea : 0,
      maxArea,
      degenerate: degenerateTriangles,
      degenerateRatio: triangleCount ? degenerateTriangles / triangleCount : 0,
      nonFinitePositions,
      nonFiniteNormals,
      poorNormalAlignment,
      worstNormalAlignment,
    },
    orientation: {
      samples: orientationSamples,
      inverted: invertedOrientationSamples,
      ambiguous: ambiguousOrientationSamples,
      invertedRatio: orientationSamples ? invertedOrientationSamples / orientationSamples : 0,
    },
    edges: {
      total: edgeCount,
      manifold: manifoldEdges,
      boundary: boundaryEdges,
      nonManifold: nonManifoldEdges,
      boundaryRatio: edgeCount ? boundaryEdges / edgeCount : 0,
      nonManifoldRatio: edgeCount ? nonManifoldEdges / edgeCount : 0,
    },
  };
}

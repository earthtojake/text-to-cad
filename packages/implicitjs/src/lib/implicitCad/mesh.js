import { normalizeImplicitCadModel } from "./model.js";
import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

const DEFAULT_RESOLUTION = 96;
const DEFAULT_MAX_CELLS = 2500000;
const TETRAHEDRA = Object.freeze([
  [0, 5, 1, 6],
  [0, 1, 2, 6],
  [0, 2, 3, 6],
  [0, 3, 7, 6],
  [0, 7, 4, 6],
  [0, 4, 5, 6],
]);
const CUBE_OFFSETS = Object.freeze([
  [0, 0, 0],
  [1, 0, 0],
  [1, 1, 0],
  [0, 1, 0],
  [0, 0, 1],
  [1, 0, 1],
  [1, 1, 1],
  [0, 1, 1],
]);

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeResolution(value = DEFAULT_RESOLUTION) {
  return Math.max(8, Math.min(192, Math.floor(finiteNumber(value, DEFAULT_RESOLUTION))));
}

function normalizedGrid(model, { resolution = DEFAULT_RESOLUTION, maxCells = DEFAULT_MAX_CELLS } = {}) {
  const bounds = model.bounds;
  const size = model.size;
  const longest = Math.max(size[0], size[1], size[2], 1e-6);
  const targetResolution = normalizeResolution(resolution);
  const cellSize = longest / targetResolution;
  let nx = Math.max(2, Math.ceil(size[0] / cellSize));
  let ny = Math.max(2, Math.ceil(size[1] / cellSize));
  let nz = Math.max(2, Math.ceil(size[2] / cellSize));
  const maxCellCount = Math.max(4096, Math.floor(finiteNumber(maxCells, DEFAULT_MAX_CELLS)));
  const cellCount = nx * ny * nz;
  if (cellCount > maxCellCount) {
    const scale = Math.cbrt(maxCellCount / cellCount);
    nx = Math.max(2, Math.floor(nx * scale));
    ny = Math.max(2, Math.floor(ny * scale));
    nz = Math.max(2, Math.floor(nz * scale));
  }
  return {
    min: bounds.min,
    max: bounds.max,
    size,
    nx,
    ny,
    nz,
    step: [
      size[0] / nx,
      size[1] / ny,
      size[2] / nz,
    ],
  };
}

function pointAt(grid, ix, iy, iz) {
  return [
    grid.min[0] + ix * grid.step[0],
    grid.min[1] + iy * grid.step[1],
    grid.min[2] + iz * grid.step[2],
  ];
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
  const len = Math.hypot(v[0], v[1], v[2]);
  return len > 1e-12 ? [v[0] / len, v[1] / len, v[2] / len] : [0, 0, 1];
}

function midpoint(a, b, c) {
  return [
    (a[0] + b[0] + c[0]) / 3,
    (a[1] + b[1] + c[1]) / 3,
    (a[2] + b[2] + c[2]) / 3,
  ];
}

function estimateGradient(sdf, point, epsilon) {
  const [x, y, z] = point;
  return normalize([
    sdf(x + epsilon, y, z) - sdf(x - epsilon, y, z),
    sdf(x, y + epsilon, z) - sdf(x, y - epsilon, z),
    sdf(x, y, z + epsilon) - sdf(x, y, z - epsilon),
  ]);
}

function offsetPoint(point, direction, distance) {
  return [
    point[0] + direction[0] * distance,
    point[1] + direction[1] * distance,
    point[2] + direction[2] * distance,
  ];
}

function normalFacesOutward(sdf, point, normal, epsilon) {
  const positive = finiteNumber(sdf(...offsetPoint(point, normal, epsilon)), 1e6);
  const negative = finiteNumber(sdf(...offsetPoint(point, normal, -epsilon)), 1e6);
  return positive >= negative;
}

function smoothNormalForVertex(sdf, vertex, epsilon, normalCache) {
  const key = `${vertex[0].toPrecision(12)},${vertex[1].toPrecision(12)},${vertex[2].toPrecision(12)}`;
  let normal = normalCache.get(key);
  if (!normal) {
    normal = estimateGradient(sdf, vertex, epsilon);
    normalCache.set(key, normal);
  }
  return normal;
}

function interpolateVertex(a, b, iso = 0) {
  const denominator = b.value - a.value;
  const t = Math.abs(denominator) < 1e-12
    ? 0.5
    : clamp((iso - a.value) / denominator, 0, 1);
  return [
    a.position[0] + (b.position[0] - a.position[0]) * t,
    a.position[1] + (b.position[1] - a.position[1]) * t,
    a.position[2] + (b.position[2] - a.position[2]) * t,
  ];
}

function pushTriangle(mesh, sdf, normalEpsilon, a, b, c, {
  normalCache = null,
  orientByGradient = false,
  orientBySdf = true,
  orientationEpsilon = normalEpsilon,
  smoothNormals = false,
} = {}) {
  let v0 = a;
  let v1 = b;
  let v2 = c;
  let normal = normalize(cross(subtract(v1, v0), subtract(v2, v0)));
  const triangleMidpoint = midpoint(v0, v1, v2);
  const gradient = orientByGradient ? estimateGradient(sdf, triangleMidpoint, normalEpsilon) : null;
  const facesOutward = gradient
    ? dot(normal, gradient) >= 0
    : !orientBySdf || normalFacesOutward(sdf, triangleMidpoint, normal, orientationEpsilon);
  if (!facesOutward) {
    v1 = c;
    v2 = b;
    normal = [-normal[0], -normal[1], -normal[2]];
  }
  for (const vertex of [v0, v1, v2]) {
    const vertexNormal = smoothNormals && normalCache
      ? smoothNormalForVertex(sdf, vertex, normalEpsilon, normalCache)
      : normal;
    const alignedNormal = dot(vertexNormal, normal) < 0
      ? [-vertexNormal[0], -vertexNormal[1], -vertexNormal[2]]
      : vertexNormal;
    mesh.positions.push(vertex[0], vertex[1], vertex[2]);
    mesh.normals.push(alignedNormal[0], alignedNormal[1], alignedNormal[2]);
  }
}

function polygonizeTetra(mesh, sdf, normalEpsilon, corners, iso = 0, options = {}) {
  const inside = [];
  const outside = [];
  for (const corner of corners) {
    if (corner.value <= iso) {
      inside.push(corner);
    } else {
      outside.push(corner);
    }
  }
  if (inside.length === 0 || inside.length === 4) {
    return;
  }
  const edge = (a, b) => interpolateVertex(a, b, iso);
  if (inside.length === 1) {
    pushTriangle(mesh, sdf, normalEpsilon, edge(inside[0], outside[0]), edge(inside[0], outside[1]), edge(inside[0], outside[2]), options);
    return;
  }
  if (inside.length === 3) {
    pushTriangle(mesh, sdf, normalEpsilon, edge(outside[0], inside[0]), edge(outside[0], inside[2]), edge(outside[0], inside[1]), options);
    return;
  }
  const a = edge(inside[0], outside[0]);
  const b = edge(inside[1], outside[0]);
  const c = edge(inside[1], outside[1]);
  const d = edge(inside[0], outside[1]);
  pushTriangle(mesh, sdf, normalEpsilon, a, b, c, options);
  pushTriangle(mesh, sdf, normalEpsilon, a, c, d, options);
}

function sampledValueIndex(grid, ix, iy, iz) {
  return ix + (grid.nx + 1) * (iy + (grid.ny + 1) * iz);
}

export function meshImplicitCadModel(modelValue, options = {}) {
  const model = normalizeImplicitCadModel(modelValue);
  const sdf = typeof options.sdf === "function"
    ? options.sdf
    : createImplicitCadSdfEvaluator(model);
  const grid = normalizedGrid(model, options);
  const valueCount = (grid.nx + 1) * (grid.ny + 1) * (grid.nz + 1);
  const values = new Float32Array(valueCount);

  for (let iz = 0; iz <= grid.nz; iz += 1) {
    for (let iy = 0; iy <= grid.ny; iy += 1) {
      for (let ix = 0; ix <= grid.nx; ix += 1) {
        const p = pointAt(grid, ix, iy, iz);
        values[sampledValueIndex(grid, ix, iy, iz)] = finiteNumber(sdf(p[0], p[1], p[2]), 1e6);
      }
    }
  }

  const mesh = {
    positions: [],
    normals: [],
    format: "triangle-list",
    sourceModel: model,
    grid: {
      resolution: [grid.nx, grid.ny, grid.nz],
      step: grid.step,
    },
  };
  const normalEpsilon = Math.max(finiteNumber(options.normalEpsilon, model.normalEpsilon), 1e-5);
  const orientationEpsilon = Math.max(Math.min(...grid.step) * 0.15, 1e-5);
  const normalCache = options.smoothNormals === true ? new Map() : null;

  for (let iz = 0; iz < grid.nz; iz += 1) {
    for (let iy = 0; iy < grid.ny; iy += 1) {
      for (let ix = 0; ix < grid.nx; ix += 1) {
        const corners = CUBE_OFFSETS.map(([dx, dy, dz]) => {
          const cx = ix + dx;
          const cy = iy + dy;
          const cz = iz + dz;
          return {
            position: pointAt(grid, cx, cy, cz),
            value: values[sampledValueIndex(grid, cx, cy, cz)],
          };
        });
        for (const tetra of TETRAHEDRA) {
          polygonizeTetra(mesh, sdf, normalEpsilon, tetra.map((index) => corners[index]), 0, {
            normalCache,
            orientByGradient: options.orientByGradient === true,
            orientBySdf: options.orientBySdf !== false,
            orientationEpsilon,
            smoothNormals: options.smoothNormals === true,
          });
        }
      }
    }
  }

  return {
    ...mesh,
    positions: new Float32Array(mesh.positions),
    normals: new Float32Array(mesh.normals),
    vertexCount: mesh.positions.length / 3,
    triangleCount: mesh.positions.length / 9,
  };
}

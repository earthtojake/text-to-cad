import { normalizeImplicitCadModel } from "./model.js";
import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

export const DEFAULT_RESOLUTION = 144;
export const DEFAULT_MAX_CELLS = 8000000;

/**
 * The fewest cells the thinnest axis of a model may have.
 *
 * A flat model's thin axis is what its surface curves through, so too few cells there reads
 * as voxel stair-stepping no matter how accurate the field is. Lifting it costs cells
 * CUBICALLY, though: at 24, dragon-curve-ribbon went 12 -> 24 and its build went 123s -> 815s
 * for one doubling. 16 keeps a third of the linear gain at roughly a third of the cost
 * (~2.4x cells rather than 8x), which is the balance to hold until the planned performance
 * work makes finer lattices affordable. Cubic models sit far above this and never pay.
 */
export const MIN_THIN_AXIS_CELLS = 24;
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

// The cube's 12 OUTER edges (indices into CUBE_OFFSETS). Crossings on these are shared with
// neighbouring cells and must never move; they are also exactly the Hermite samples the
// feature snap reads. The only crossing interior to a cell lies on the main diagonal 0-6,
// which every tetra in TETRAHEDRA shares -- that one vertex is ours to place.
const CUBE_EDGES = Object.freeze([
  [0, 1], [1, 2], [2, 3], [3, 0],
  [4, 5], [5, 6], [6, 7], [7, 4],
  [0, 4], [1, 5], [2, 6], [3, 7],
]);

// The 6 cube faces with the diagonal this decomposition draws across each. A face diagonal
// is shared by exactly TWO cells, and the uniform decomposition draws the SAME diagonal from
// both sides, so a snap computed purely from the face's own four edge crossings is
// deterministic across the pair -- both cells move the shared vertex to the same point, and
// the mesh stays crack-free.
const CUBE_FACES = Object.freeze([
  { edges: [[0, 1], [1, 5], [5, 4], [4, 0]], diagonal: [0, 5] },
  { edges: [[1, 2], [2, 6], [6, 5], [5, 1]], diagonal: [1, 6] },
  { edges: [[0, 1], [1, 2], [2, 3], [3, 0]], diagonal: [0, 2] },
  { edges: [[3, 2], [2, 6], [6, 7], [7, 3]], diagonal: [3, 6] },
  { edges: [[0, 3], [3, 7], [7, 4], [4, 0]], diagonal: [0, 7] },
  { edges: [[4, 5], [5, 6], [6, 7], [7, 4]], diagonal: [4, 6] },
]);

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeResolution(value = DEFAULT_RESOLUTION) {
  return Math.max(8, Math.min(256, Math.floor(finiteNumber(value, DEFAULT_RESOLUTION))));
}

/**
 * The sampling grid one model+resolution produces.
 *
 * Exported because the parallel mesher (`meshWorkers.js`) has to derive the grid ONCE on the
 * main thread and ship it to the workers: a worker that recomputed it from the model would
 * have to re-run auto-bounds estimation, and any divergence there would silently move the
 * whole lattice.
 */
export function implicitCadGrid(model, { resolution = DEFAULT_RESOLUTION, maxCells = DEFAULT_MAX_CELLS } = {}) {
  const bounds = model.bounds;
  const size = model.size;
  const longest = Math.max(size[0], size[1], size[2], 1e-6);
  const targetResolution = normalizeResolution(resolution);
  const cellSize = longest / targetResolution;
  let nx = Math.max(2, Math.ceil(size[0] / cellSize));
  let ny = Math.max(2, Math.ceil(size[1] / cellSize));
  let nz = Math.max(2, Math.ceil(size[2] / cellSize));
  const maxCellCount = Math.max(4096, Math.floor(finiteNumber(maxCells, DEFAULT_MAX_CELLS)));

  // Resolution is defined against the LONGEST axis, so a flat model gets very few cells
  // through its thin one -- dragon-curve-ribbon lands on 96x96x12 -- and a ribbon a couple of
  // cells thick can only come out as visible stair steps, however good the field is. Lift the
  // whole lattice until the thinnest axis carries enough cells to curve, which costs nothing
  // on a cubic model (already far above the floor) and is bounded by the same cell budget.
  const thinnest = Math.min(nx, ny, nz);
  if (thinnest < MIN_THIN_AXIS_CELLS) {
    const lift = Math.min(
      MIN_THIN_AXIS_CELLS / thinnest,
      Math.cbrt(maxCellCount / Math.max(nx * ny * nz, 1))
    );
    if (lift > 1) {
      nx = Math.max(2, Math.round(nx * lift));
      ny = Math.max(2, Math.round(ny * lift));
      nz = Math.max(2, Math.round(nz * lift));
    }
  }

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

function pointOnEdge(a, b, t) {
  return [
    a.position[0] + (b.position[0] - a.position[0]) * t,
    a.position[1] + (b.position[1] - a.position[1]) * t,
    a.position[2] + (b.position[2] - a.position[2]) * t,
  ];
}

/** How many false-position steps to spend recovering a crossing on a non-distance field. */
const EDGE_REFINE_STEPS = 5;

/** Normals within ~30deg of the face keep the smooth gradient; beyond it is a crease. */
const CREASE_NORMAL_DOT = Math.cos((30 * Math.PI) / 180);

/** Fraction of an edge below which the crossing counts as settled. */
const EDGE_REFINE_EPSILON = 1e-4;

/**
 * Where the surface crosses the edge `a -> b`.
 *
 * The linear guess `t = -a.value / (b.value - a.value)` is exact only when the field varies
 * linearly along the edge, which is what a true signed DISTANCE function does. An algebraic
 * field -- Chmutov's Chebyshev polynomials, a tanglecube -- carries no distance information
 * at all: its magnitude can change several times faster than the distance travelled, so the
 * linear guess lands off the real surface. Neighbouring cells then disagree about where that
 * surface is, and the mesh tears into the floating shards and shredded rims those models show.
 *
 * When `sdf` is supplied the guess is polished by false position against the real field,
 * bracketed by the two corners whose signs already straddle the surface. Bisection is the
 * fallback whenever a false-position step would leave the bracket, so the iteration cannot
 * run away on a badly-scaled field.
 *
 * Refinement is DELIBERATELY opt-in per build rather than per edge: the decision is made once
 * uniformly for every edge, so two workers meshing different slabs of one model can never
 * disagree about it -- which is what keeps parallel output byte-identical to serial.
 */
function interpolateVertex(a, b, iso = 0, sdf = null) {
  const denominator = b.value - a.value;
  let t = Math.abs(denominator) < 1e-12
    ? 0.5
    : clamp((iso - a.value) / denominator, 0, 1);
  if (!sdf) {
    return pointOnEdge(a, b, t);
  }
  let low = 0;
  let high = 1;
  let atLow = a.value - iso;
  let atHigh = b.value - iso;
  for (let step = 0; step < EDGE_REFINE_STEPS; step += 1) {
    const point = pointOnEdge(a, b, t);
    const value = finiteNumber(sdf(point[0], point[1], point[2]), 0) - iso;
    if (value === 0) {
      return point;
    }
    const previous = t;
    if ((value < 0) === (atLow < 0)) {
      low = t;
      atLow = value;
    } else {
      high = t;
      atHigh = value;
    }
    const spread = atHigh - atLow;
    const next = Math.abs(spread) < 1e-12
      ? 0.5 * (low + high)
      : low + (high - low) * (-atLow / spread);
    t = next > low && next < high ? next : 0.5 * (low + high);
    // Converged: on a well-behaved field the linear guess was already right, so this exits
    // after a single probe and the whole corpus keeps close to its old build cost.
    if (Math.abs(t - previous) < EDGE_REFINE_EPSILON) {
      break;
    }
  }
  return pointOnEdge(a, b, t);
}

/**
 * Refinement is ALWAYS on. An earlier attempt gated it on a measured "is this field
 * distance-like" score, tried two different metrics, and neither discriminated: field slope
 * is irrelevant because linear interpolation is scale invariant, and the residual at the
 * linear guess is in field units, so a gentle algebraic field scores BELOW a true distance
 * field (measured: 0.0087 vs 0.0136 of a cell). Since a reliable test costs about as much as
 * the fix, the fix simply always runs, and pays for itself by converging in one step wherever
 * the linear guess was already right.
 */


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
  // Marching tetrahedra emits genuinely degenerate triangles whenever two of a tetra's
  // crossings land on the same point -- which happens when the surface passes exactly through
  // a lattice corner, and gets more common as the lattice gets finer. They carry no geometry
  // (zero area), have no definable normal, and only cost bytes downstream, so they are dropped
  // rather than welded and shipped.
  const face = cross(subtract(v1, v0), subtract(v2, v0));
  if (!(Math.hypot(face[0], face[1], face[2]) > 0)) {
    return;
  }
  let normal = normalize(face);
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
    // Crease-aware: the gradient normal is right on smooth surface, but across a sharp
    // edge it AVERAGES the two faces and visually melts the crease -- gear teeth read as
    // molten. Where the smooth normal disagrees with this triangle's face beyond ~30deg,
    // the face normal wins, which is the standard auto-smooth rule.
    let vertexNormal = normal;
    if (smoothNormals && normalCache) {
      const smooth = smoothNormalForVertex(sdf, vertex, normalEpsilon, normalCache);
      const agreement = smooth[0] * normal[0] + smooth[1] * normal[1] + smooth[2] * normal[2];
      vertexNormal = agreement >= CREASE_NORMAL_DOT ? smooth : normal;
    }
    const alignedNormal = dot(vertexNormal, normal) < 0
      ? [-vertexNormal[0], -vertexNormal[1], -vertexNormal[2]]
      : vertexNormal;
    mesh.positions.push(vertex[0], vertex[1], vertex[2]);
    mesh.normals.push(alignedNormal[0], alignedNormal[1], alignedNormal[2]);
  }
}

/**
 * Hermite feature snapping: where a cell contains a sharp crease, place its one interior
 * vertex ON the crease instead of on the chamfer.
 *
 * Marching tetrahedra puts vertices only on cell edges, so a sharp edge (a gear tooth's
 * flank meeting its top face) is truncated to a bevel about one cell wide at ANY
 * resolution. But the surface crossings on the cell's outer edges, with the field's
 * gradients there, define the surface's tangent planes -- and a sharp feature is exactly
 * where those planes disagree. The point minimizing the squared distance to all of them
 * (the QEF of extended marching cubes) lies on the true edge or corner.
 *
 * Snapping ONLY the main-diagonal crossing keeps every guarantee intact: it is the sole
 * vertex interior to the cell, so boundary crossings shared with neighbours never move --
 * watertight by construction, topology unchanged, and the per-cell decision is
 * deterministic, so parallel and serial output stay byte-identical.
 *
 * The gradients are seeded into `normalCache` under the same keys `pushTriangle` uses, so
 * with smooth normals on (the builder's configuration) this costs almost nothing extra.
 */
function hermiteSamples(sdf, corners, edges, normalEpsilon, refineSdf, normalCache) {
  const points = [];
  const normals = [];
  for (const [i, j] of edges) {
    const a = corners[i];
    const b = corners[j];
    if ((a.value <= 0) === (b.value <= 0)) {
      continue;
    }
    const p = interpolateVertex(a, b, 0, refineSdf);
    const n = normalCache
      ? smoothNormalForVertex(sdf, p, normalEpsilon, normalCache)
      : estimateGradient(sdf, p, normalEpsilon);
    points.push(p);
    normals.push(n);
  }
  return { points, normals };
}

function isFeature(normals) {
  for (let i = 0; i < normals.length; i += 1) {
    for (let j = i + 1; j < normals.length; j += 1) {
      if (dot(normals[i], normals[j]) < CREASE_NORMAL_DOT) {
        return true;
      }
    }
  }
  return false;
}

/** QEF minimizer over the sampled tangent planes, clamped to the diagonal's bounding box. */
function qefSnap(a, b, samples) {
  const m = samples.points.length;
  if (m < 2 || !isFeature(samples.normals)) {
    return null;
  }
  const A = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const rhs = [0, 0, 0];
  const centroid = [0, 0, 0];
  for (let k = 0; k < m; k += 1) {
    const n = samples.normals[k];
    const d = dot(n, samples.points[k]);
    for (let r = 0; r < 3; r += 1) {
      centroid[r] += samples.points[k][r] / m;
      rhs[r] += (n[r] * d) / m;
      for (let c = 0; c < 3; c += 1) {
        A[r][c] += (n[r] * n[c]) / m;
      }
    }
  }
  const LAMBDA = 1e-3;
  for (let r = 0; r < 3; r += 1) {
    A[r][r] += LAMBDA;
    rhs[r] += LAMBDA * centroid[r];
  }
  const x = solve3(A, rhs);
  if (!x) {
    return null;
  }
  // Clamped to the diagonal's own bounding box: for a face diagonal that box is flat along
  // the face's normal axis, which pins the snapped point onto the shared face -- the
  // property that keeps the two-cell agreement exact.
  for (let r = 0; r < 3; r += 1) {
    const lo = Math.min(a.position[r], b.position[r]);
    const hi = Math.max(a.position[r], b.position[r]);
    x[r] = Math.min(Math.max(x[r], lo), hi);
  }
  return { a, b, point: x };
}

/**
 * Hermite feature snapping: place a cell's movable crossing vertices ON sharp creases.
 *
 * Marching tetrahedra chamfers a sharp edge to about one cell width at any resolution. The
 * crossings on a cell's outer edges plus the field gradients there define the surface's
 * tangent planes; where those disagree beyond the crease angle, their least-squares
 * intersection (the QEF of extended marching cubes) IS the edge. Two kinds of vertex may
 * move without cracking the mesh: the main-diagonal crossing (interior to one cell, solved
 * from all 12 outer edges) and each face-diagonal crossing (shared by two cells, solved
 * from that face's 4 edges only, so both cells derive the identical point). Cube-edge
 * crossings never move. Topology is untouched, watertightness is preserved by construction,
 * and every decision is deterministic per cell, keeping parallel and serial byte-identical.
 */
function cellFeatureSnaps(sdf, corners, normalEpsilon, refineSdf, normalCache) {
  let snaps = null;
  const c0 = corners[0];
  const c6 = corners[6];
  if ((c0.value <= 0) !== (c6.value <= 0)) {
    const snap = qefSnap(c0, c6, hermiteSamples(sdf, corners, CUBE_EDGES, normalEpsilon, refineSdf, normalCache));
    if (snap) {
      (snaps ||= []).push(snap);
    }
  }
  for (const face of CUBE_FACES) {
    const a = corners[face.diagonal[0]];
    const b = corners[face.diagonal[1]];
    if ((a.value <= 0) === (b.value <= 0)) {
      continue;
    }
    const snap = qefSnap(a, b, hermiteSamples(sdf, corners, face.edges, normalEpsilon, refineSdf, normalCache));
    if (snap) {
      (snaps ||= []).push(snap);
    }
  }
  return snaps;
}

/** Gaussian elimination with partial pivoting for the 3x3 QEF system; null if singular. */
function solve3(A, b) {
  const M = [
    [A[0][0], A[0][1], A[0][2], b[0]],
    [A[1][0], A[1][1], A[1][2], b[1]],
    [A[2][0], A[2][1], A[2][2], b[2]],
  ];
  for (let col = 0; col < 3; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < 3; row += 1) {
      if (Math.abs(M[row][col]) > Math.abs(M[pivot][col])) {
        pivot = row;
      }
    }
    if (Math.abs(M[pivot][col]) < 1e-12) {
      return null;
    }
    [M[col], M[pivot]] = [M[pivot], M[col]];
    for (let row = col + 1; row < 3; row += 1) {
      const f = M[row][col] / M[col][col];
      for (let k = col; k < 4; k += 1) {
        M[row][k] -= f * M[col][k];
      }
    }
  }
  const out = [0, 0, 0];
  for (let row = 2; row >= 0; row -= 1) {
    let sum = M[row][3];
    for (let k = row + 1; k < 3; k += 1) {
      sum -= M[row][k] * out[k];
    }
    out[row] = sum / M[row][row];
  }
  return out;
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
  const snaps = options.snaps;
  const edge = (a, b) => {
    if (snaps) {
      for (const snap of snaps) {
        if ((a === snap.a && b === snap.b) || (a === snap.b && b === snap.a)) {
          return snap.point;
        }
      }
    }
    return interpolateVertex(a, b, iso, options.refineEdges ? sdf : null);
  };
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

/** Element count of the sampled field for `grid` (one value per lattice CORNER). */
export function sampledValueCount(grid) {
  return (grid.nx + 1) * (grid.ny + 1) * (grid.nz + 1);
}

/** The number of sample planes (`iz` slices) the sample pass walks. */
export function samplePlaneCount(grid) {
  return grid.nz + 1;
}

/** The number of cell slabs (`iz` layers) the polygonize pass walks. */
export function cellPlaneCount(grid) {
  return grid.nz;
}

/**
 * Sample the field into `values` for the `iz` planes in `[from, to)`.
 *
 * Separable by construction: plane `iz` occupies the contiguous block
 * `[iz * (nx+1) * (ny+1), (iz+1) * (nx+1) * (ny+1))` of `values`, so two ranges never touch
 * the same element and the array may be a SharedArrayBuffer view written by several workers
 * at once. `onPlane` is called after each plane, which is what gives the build a determinate
 * progress denominator.
 */
export function sampleFieldPlanes(sdf, grid, values, { from = 0, to = null, onPlane = null } = {}) {
  const last = to === null ? samplePlaneCount(grid) : to;
  for (let iz = from; iz < last; iz += 1) {
    for (let iy = 0; iy <= grid.ny; iy += 1) {
      for (let ix = 0; ix <= grid.nx; ix += 1) {
        const p = pointAt(grid, ix, iy, iz);
        values[sampledValueIndex(grid, ix, iy, iz)] = finiteNumber(sdf(p[0], p[1], p[2]), 1e6);
      }
    }
    onPlane?.(iz);
  }
  return values;
}

/**
 * Polygonize the cell slabs `iz` in `[from, to)` into flat position/normal arrays.
 *
 * Reads `values` at `cz ∈ {iz, iz+1}` only and appends to its own output, so slabs are
 * independent. Concatenating the outputs in slab order reproduces the serial pass EXACTLY --
 * which is what lets `meshImplicitCadModelParallel` assert byte-identical output rather than
 * merely equivalent geometry.
 *
 * `normalCache` is per-call: `estimateGradient` is pure, so a vertex on a slab boundary is
 * computed once per worker instead of once per model, and yields the same value either way.
 */
export function polygonizeCellPlanes(sdf, grid, values, {
  from = 0,
  to = null,
  normalEpsilon,
  orientByGradient = false,
  orientBySdf = true,
  smoothNormals = false,
  refineEdges = true,
  snapFeatures = true,
  onPlane = null,
} = {}) {
  const last = to === null ? cellPlaneCount(grid) : to;
  const mesh = { positions: [], normals: [] };
  const orientationEpsilon = Math.max(Math.min(...grid.step) * 0.15, 1e-5);
  const normalCache = smoothNormals ? new Map() : null;
  const triangleOptions = {
    normalCache,
    orientByGradient,
    orientBySdf,
    orientationEpsilon,
    smoothNormals,
    refineEdges,
  };
  for (let iz = from; iz < last; iz += 1) {
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
        const snaps = snapFeatures
          ? cellFeatureSnaps(sdf, corners, normalEpsilon, refineEdges ? sdf : null, normalCache)
          : null;
        const cellOptions = snaps ? { ...triangleOptions, snaps } : triangleOptions;
        for (const tetra of TETRAHEDRA) {
          polygonizeTetra(mesh, sdf, normalEpsilon, tetra.map((index) => corners[index]), 0, cellOptions);
        }
      }
    }
    onPlane?.(iz);
  }
  return {
    positions: new Float32Array(mesh.positions),
    normals: new Float32Array(mesh.normals),
  };
}

/** The normal-probe epsilon a mesh pass uses, given the model and the caller's options. */
export function meshNormalEpsilon(model, options = {}) {
  return Math.max(finiteNumber(options.normalEpsilon, model.normalEpsilon), 1e-5);
}

export function meshImplicitCadModel(modelValue, options = {}) {
  const model = normalizeImplicitCadModel(modelValue);
  const sdf = typeof options.sdf === "function"
    ? options.sdf
    : createImplicitCadSdfEvaluator(model);
  const grid = implicitCadGrid(model, options);
  const values = sampleFieldPlanes(sdf, grid, new Float32Array(sampledValueCount(grid)));
  const { positions, normals } = polygonizeCellPlanes(sdf, grid, values, {
    normalEpsilon: meshNormalEpsilon(model, options),
    orientByGradient: options.orientByGradient === true,
    orientBySdf: options.orientBySdf !== false,
    smoothNormals: options.smoothNormals === true,
    refineEdges: options.refineEdges !== false,
    snapFeatures: options.snapFeatures !== false,
  });

  return {
    positions,
    normals,
    format: "triangle-list",
    sourceModel: model,
    grid: {
      resolution: [grid.nx, grid.ny, grid.nz],
      step: grid.step,
    },
    vertexCount: positions.length / 3,
    triangleCount: positions.length / 9,
  };
}

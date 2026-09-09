// Reference evaluators for SURF geometry (design/surface-rendering.md R2).
//
// These are the CPU twins of the WGSL kernels: every function is written
// in a directly portable style — flat arrays, iterative de Boor, no
// recursion, no allocation in inner loops. The node test suite pins them
// against OCCT-sampled ground truth; the GPU tests then pin the WGSL
// kernels against these.

import { floatSpan } from "./container.js";

// --- NURBS basics ----------------------------------------------------------
//
// Knots arrive FLAT (each knot repeated by its multiplicity), exactly the
// arrays OCCT hands out, so `findSpan`/`deBoor` follow the standard
// Piegl & Tiller formulation with n = poleCount - 1, order = degree + 1.

export function findSpan(flatKnots, degree, poleCount, t) {
  const last = poleCount; // knot index of the domain end (0-based)
  if (t >= flatKnots[last]) return last - 1;
  if (t <= flatKnots[degree]) return degree;
  let low = degree;
  let high = last;
  let mid = (low + high) >> 1;
  while (t < flatKnots[mid] || t >= flatKnots[mid + 1]) {
    if (t < flatKnots[mid]) high = mid;
    else low = mid;
    mid = (low + high) >> 1;
  }
  return mid;
}

// Scratch pools: these run millions of times per large assembly and the
// per-call Float64Array allocations dominated GC time. JS realms are
// single-threaded (each worker has its own module instance), so shared
// module scratch is safe.
const scratchBySize = new Map();
function scratch(slot, size) {
  let bySlot = scratchBySize.get(size);
  if (!bySlot) scratchBySize.set(size, (bySlot = []));
  let array = bySlot[slot];
  if (!array) bySlot[slot] = array = new Float64Array(size);
  return array;
}

export function basisFunctions(flatKnots, degree, span, t, out) {
  // out must hold degree+1 values; left/right are shared scratch.
  const left = scratch(0, degree + 1);
  const right = scratch(1, degree + 1);
  out[0] = 1.0;
  for (let j = 1; j <= degree; j += 1) {
    left[j] = t - flatKnots[span + 1 - j];
    right[j] = flatKnots[span + j] - t;
    let saved = 0.0;
    for (let r = 0; r < j; r += 1) {
      const temp = out[r] / (right[r + 1] + left[j - r]);
      out[r] = saved + right[r + 1] * temp;
      saved = left[j - r] * temp;
    }
    out[j] = saved;
  }
  return out;
}

// --- Curves ----------------------------------------------------------------

// payload: {deg, n, poles: span-ref, knots: span-ref, weights?: span-ref}
// dim: 2 for pcurves, 3 for edge curves. Returns [x, y] or [x, y, z].
export function evaluateBSplineCurve(payload, floats, t, dim) {
  const degree = payload.deg;
  const poles = floatSpan(floats, payload.poles);
  const knots = floatSpan(floats, payload.knots);
  const weights = payload.weights ? floatSpan(floats, payload.weights) : null;
  if (payload.period) {
    // Clamped from a CLOSED curve: sweep faces may address parameters past
    // the period (a face crossing the profile seam); wrap into the domain.
    const [first, last] = payload.range;
    if (t > last || t < first) {
      t = first + ((((t - first) % payload.period) + payload.period) % payload.period);
    }
  }
  const span = findSpan(knots, degree, payload.n, t);
  const basis = basisFunctions(knots, degree, span, t, scratch(2, degree + 1));
  const point = [0, 0, 0];
  let w = 0.0;
  for (let i = 0; i <= degree; i += 1) {
    const poleIndex = span - degree + i;
    const weight = weights ? weights[poleIndex] : 1.0;
    const b = basis[i] * weight;
    for (let d = 0; d < dim; d += 1) point[d] += b * poles[poleIndex * dim + d];
    w += b;
  }
  for (let d = 0; d < dim; d += 1) point[d] /= w;
  return point.slice(0, dim);
}

const CURVE3_EVALUATORS = {
  line(payload, t) {
    const { origin, dir } = payload;
    return [origin[0] + t * dir[0], origin[1] + t * dir[1], origin[2] + t * dir[2]];
  },
  circle(payload, t) {
    const c = Math.cos(t) * payload.radius;
    const s = Math.sin(t) * payload.radius;
    return frameMix(payload, c, s, 0);
  },
  ellipse(payload, t) {
    const c = Math.cos(t) * payload.majorRadius;
    const s = Math.sin(t) * payload.minorRadius;
    return frameMix(payload, c, s, 0);
  },
};

export function evaluateCurve3(payload, floats, t) {
  const direct = CURVE3_EVALUATORS[payload.kind];
  if (direct) return direct(payload, t);
  if (payload.kind === "bspline") return evaluateBSplineCurve(payload, floats, t, 3);
  throw new Error(`unknown curve kind ${payload.kind}`);
}

export function evaluatePCurve(payload, floats, t) {
  return evaluateBSplineCurve(payload, floats, t, 2);
}

// --- Surfaces ---------------------------------------------------------------

function frameMix(frame, x, y, z) {
  const { origin, xdir, ydir, zdir } = frame;
  return [
    origin[0] + x * xdir[0] + y * ydir[0] + z * zdir[0],
    origin[1] + x * xdir[1] + y * ydir[1] + z * zdir[1],
    origin[2] + x * xdir[2] + y * ydir[2] + z * zdir[2],
  ];
}

function evaluateNurbsSurface(payload, floats, u, v) {
  const { degU, degV, nu, nv } = payload;
  const poles = floatSpan(floats, payload.poles);
  const knotsU = floatSpan(floats, payload.knotsU);
  const knotsV = floatSpan(floats, payload.knotsV);
  const weights = payload.weights ? floatSpan(floats, payload.weights) : null;
  const spanU = findSpan(knotsU, degU, nu, u);
  const spanV = findSpan(knotsV, degV, nv, v);
  const basisU = basisFunctions(knotsU, degU, spanU, u, scratch(2, degU + 1));
  const basisV = basisFunctions(knotsV, degV, spanV, v, scratch(3, degV + 1));
  let x = 0;
  let y = 0;
  let z = 0;
  let w = 0;
  for (let i = 0; i <= degU; i += 1) {
    const row = spanU - degU + i;
    for (let j = 0; j <= degV; j += 1) {
      const col = spanV - degV + j;
      const poleIndex = row * nv + col; // poles stored row-major [u][v]
      const weight = weights ? weights[poleIndex] : 1.0;
      const b = basisU[i] * basisV[j] * weight;
      x += b * poles[poleIndex * 3];
      y += b * poles[poleIndex * 3 + 1];
      z += b * poles[poleIndex * 3 + 2];
      w += b;
    }
  }
  return [x / w, y / w, z / w];
}

const SURFACE_EVALUATORS = {
  plane(payload, u, v) {
    return frameMix(payload, u, v, 0);
  },
  cylinder(payload, u, v) {
    const r = payload.radius;
    return frameMix(payload, r * Math.cos(u), r * Math.sin(u), v);
  },
  cone(payload, u, v) {
    const r = payload.radius + v * Math.sin(payload.semiAngle);
    return frameMix(payload, r * Math.cos(u), r * Math.sin(u), v * Math.cos(payload.semiAngle));
  },
  sphere(payload, u, v) {
    const r = payload.radius;
    const cv = Math.cos(v);
    return frameMix(payload, r * cv * Math.cos(u), r * cv * Math.sin(u), r * Math.sin(v));
  },
  torus(payload, u, v) {
    const ring = payload.majorRadius + payload.minorRadius * Math.cos(v);
    return frameMix(payload, ring * Math.cos(u), ring * Math.sin(u), payload.minorRadius * Math.sin(v));
  },
};

export function evaluateSurface(payload, floats, u, v) {
  const direct = SURFACE_EVALUATORS[payload.kind];
  if (direct) return direct(payload, u, v);
  if (payload.kind === "nurbs") return evaluateNurbsSurface(payload, floats, u, v);
  if (payload.kind === "revolution") {
    // Value(u, v) = profile(v) rotated by u around the axis (OCCT
    // convention) — exact and parametrization-preserving, which a NURBS
    // conversion of a revolved surface is NOT.
    const point = evaluateCurve3(payload.profile, floats, v);
    return rotateAroundAxis(point, payload.origin, payload.dir, u);
  }
  if (payload.kind === "extrusion") {
    const point = evaluateCurve3(payload.profile, floats, u);
    return [
      point[0] + v * payload.dir[0],
      point[1] + v * payload.dir[1],
      point[2] + v * payload.dir[2],
    ];
  }
  throw new Error(`unknown surface kind ${payload.kind}`);
}

function rotateAroundAxis(point, origin, axis, angle) {
  // Rodrigues rotation of (point - origin) around unit axis.
  const px = point[0] - origin[0];
  const py = point[1] - origin[1];
  const pz = point[2] - origin[2];
  const [ax, ay, az] = axis;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const dot = ax * px + ay * py + az * pz;
  const crossX = ay * pz - az * py;
  const crossY = az * px - ax * pz;
  const crossZ = ax * py - ay * px;
  return [
    origin[0] + px * cos + crossX * sin + ax * dot * (1 - cos),
    origin[1] + py * cos + crossY * sin + ay * dot * (1 - cos),
    origin[2] + pz * cos + crossZ * sin + az * dot * (1 - cos),
  ];
}

// Central-difference normal; the WGSL kernel mirrors this (exact partials
// come later per surface kind if goldens demand them).
export function evaluateSurfaceNormal(payload, floats, u, v, uvBox, flip) {
  const [u0, u1, v0, v1] = uvBox;
  const hu = Math.max((u1 - u0) * 1e-4, 1e-7);
  const hv = Math.max((v1 - v0) * 1e-4, 1e-7);
  const pu0 = evaluateSurface(payload, floats, u - hu, v);
  const pu1 = evaluateSurface(payload, floats, u + hu, v);
  const pv0 = evaluateSurface(payload, floats, u, v - hv);
  const pv1 = evaluateSurface(payload, floats, u, v + hv);
  const du = [pu1[0] - pu0[0], pu1[1] - pu0[1], pu1[2] - pu0[2]];
  const dv = [pv1[0] - pv0[0], pv1[1] - pv0[1], pv1[2] - pv0[2]];
  let nx = du[1] * dv[2] - du[2] * dv[1];
  let ny = du[2] * dv[0] - du[0] * dv[2];
  let nz = du[0] * dv[1] - du[1] * dv[0];
  const length = Math.hypot(nx, ny, nz) || 1;
  const sign = flip ? -1 : 1;
  nx = (nx / length) * sign;
  ny = (ny / length) * sign;
  nz = (nz / length) * sign;
  return [nx, ny, nz];
}

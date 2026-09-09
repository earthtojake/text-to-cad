// SURF tessellation (design/surface-rendering.md R2).
//
// Faces triangulate in UV space: trim loops are sampled adaptively from
// their exact pcurves, earcut triangulates the outer loop with holes
// (boundary-exact — no trim masks, no cracks along trims), then triangles
// refine by edge splitting wherever the 3D chord deviates from the true
// surface. Midpoints are cached per edge so refinement is crack-free.
//
// WATERTIGHT ACROSS FACES (design/unified-tessellation.md Phase 1): each model
// edge's exact 3D curve is sampled ONCE per component, and every adjacent
// face's boundary conforms to it — boundary vertices are addressed by arc
// fraction along that shared polyline (pcurve parameterizations cannot be
// assumed aligned with the 3D curve's), their 3D coordinates are computed by
// ONE function so they are bit-identical across faces, and a final conformity
// pass fan-splits to the union of fractions so no T-junctions remain. The
// display edge overlay reuses the same polylines, so drawn edges coincide
// exactly with mesh boundaries.
// Every UV vertex introduced by refinement lies inside an earcut triangle
// and therefore inside the face, so no inside/outside testing is needed
// after the initial triangulation.
//
// Edge curves polyline the same way (adaptive chordal sampling of the
// exact 3D curve). All hot loops stay allocation-light and portable to
// WGSL compute later; the contract here is correctness first.

import { ShapeUtils, Vector2 } from "three";

import { evaluateCurve3, evaluatePCurve, evaluateSurface, evaluateSurfaceNormal } from "./evaluate.js";

// Bump on ANY change that alters output triangles/normals/edge polylines for
// the same input at the same tolerances — algorithm tweaks included, not just
// entry-format changes (the codec version in tessellationCache.js only covers
// those). This salts every shared tessellation-cache key (-t<version>-), so
// meshes produced by the previous algorithm become unreachable instead of
// being served stale; `cadgen cache gc` collects the orphans. Mirrored as
// MESH_TESSELLATION_VERSION in cadgen/_internal/cache_paths.py (sync-tested).
export const TESSELLATION_VERSION = 1;

export const DEFAULT_OPTIONS = {
  // Max 3D distance between the surface and a triangle edge midpoint,
  // relative to the component diagonal.
  chordTolerance: 1.5e-3,
  // Pcurve sampling: max 3D deviation of a loop segment, same scale.
  loopTolerance: 5e-4,
  // Max normal spread across one triangle edge (radians). Bounds facet
  // tilt — chord criteria alone admit Schwarz-lantern triangles whose
  // vertices sit on the surface while the facet cuts across it.
  angleTolerance: 0.35,
  maxRefineDepth: 7,
  minLoopSegments: 8,
};

function sub(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function length3(a) {
  return Math.hypot(a[0], a[1], a[2]);
}

// --- Loop sampling -----------------------------------------------------------

function sampleLoopPolygon(face, loop, floats, tolerance, sharedEdges) {
  // points[i] -> points[i+1] lies on the model edge segmentOrds[i].
  // segmentMeta[i] carries {ord, f0, f1} when that segment lies on a shared
  // edge polyline (fractions are arc positions along the SHARED polyline,
  // in its own convention regardless of loop direction).
  const points = [];
  const segmentOrds = [];
  const segmentMeta = [];
  for (const pcurve of loop) {
    const forward = !pcurve.reversed;
    const shared = pcurve.edgeOrd ? sharedEdges?.get(pcurve.edgeOrd) : null;
    let segment = null;
    let fractions = null;
    if (shared && shared.points.length >= 2) {
      const mapped = mapSharedEdgeToPCurve(face, pcurve, floats, tolerance, shared);
      if (mapped) {
        segment = mapped.uvs;
        fractions = mapped.fractions;
      }
    }
    if (!segment) {
      segment = samplePCurveAdaptive(face, pcurve, floats, tolerance);
    }
    if (!forward) {
      segment.reverse();
      fractions?.reverse();
    }
    // Drop each segment's last point; the next pcurve supplies it.
    for (let i = 0; i < segment.length - 1; i += 1) {
      points.push(segment[i]);
      segmentOrds.push(pcurve.edgeOrd || 0);
      segmentMeta.push(
        fractions ? { ord: pcurve.edgeOrd, f0: fractions[i], f1: fractions[i + 1] } : null,
      );
    }
  }
  points.segmentOrds = segmentOrds;
  points.segmentMeta = segmentMeta;
  return points;
}

function samplePCurveParams(face, pcurve, floats, tolerance) {
  const [t0, t1] = pcurve.range;
  const surface = face.surface;
  const uvOf = (t) => evaluatePCurve(pcurve, floats, t);
  const xyzOf = (uv) => evaluateSurface(surface, floats, uv[0], uv[1]);
  // Adaptive initial density: a straight or gently curved OPEN pcurve needs no
  // 8-segment floor (that floor made every rectangular face carry 8x boundary
  // density and floored whole-model triangle counts); a CLOSED pcurve (full
  // circle/period) must start subdivided or the chord test degenerates.
  const start3 = xyzOf(uvOf(t0));
  const end3 = xyzOf(uvOf(t1));
  const closed = length3(sub(start3, end3)) <= tolerance;
  const initial = Math.max(closed ? DEFAULT_OPTIONS.minLoopSegments : 2, pcurve.n ?? 2);
  const params = [];
  for (let i = 0; i <= initial; i += 1) params.push(t0 + ((t1 - t0) * i) / initial);

  // Refine parameter intervals until the 3D midpoint deviation is small.
  let depth = 0;
  while (depth < DEFAULT_OPTIONS.maxRefineDepth) {
    let split = false;
    const next = [params[0]];
    for (let i = 0; i + 1 < params.length; i += 1) {
      const a = params[i];
      const b = params[i + 1];
      const mid = (a + b) / 2;
      const pa = xyzOf(uvOf(a));
      const pb = xyzOf(uvOf(b));
      const pm = xyzOf(uvOf(mid));
      const chordMid = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2];
      if (length3(sub(pm, chordMid)) > tolerance) {
        next.push(mid);
        split = true;
      }
      next.push(b);
    }
    params.length = 0;
    params.push(...next);
    if (!split) break;
    depth += 1;
  }
  return { params, uvs: params.map(uvOf) };
}

function samplePCurveAdaptive(face, pcurve, floats, tolerance) {
  return samplePCurveParams(face, pcurve, floats, tolerance).uvs;
}

// Map a shared edge polyline into this face's UV space by ARC FRACTION: the
// pcurve's parameterization need not align with the 3D curve's (conversion may
// reparameterize either), but both trace the same locus, so cumulative arc
// length is the invariant coordinate. Returns UVs in pcurve-forward order with
// each point's fraction in the SHARED polyline's convention, or null when the
// mapping cannot be trusted (mismatched locus, degenerate spans).
function mapSharedEdgeToPCurve(face, pcurve, floats, tolerance, shared) {
  const own = samplePCurveParams(face, pcurve, floats, tolerance);
  if (own.uvs.length < 2) return null;
  const surface = face.surface;
  const own3 = own.uvs.map((uv) => evaluateSurface(surface, floats, uv[0], uv[1]));
  const cumulative = [0];
  for (let i = 1; i < own3.length; i += 1) {
    cumulative.push(cumulative[i - 1] + length3(sub(own3[i], own3[i - 1])));
  }
  const total = cumulative[cumulative.length - 1];
  if (!(total > 0)) return null;
  for (let i = 0; i < cumulative.length; i += 1) cumulative[i] /= total;

  // Orientation: does the shared polyline run with or against pcurve params?
  const sharedStart = shared.points[0];
  const sharedEnd = shared.points[shared.points.length - 1];
  const dSame = length3(sub(sharedStart, own3[0])) + length3(sub(sharedEnd, own3[own3.length - 1]));
  const dFlip = length3(sub(sharedStart, own3[own3.length - 1])) + length3(sub(sharedEnd, own3[0]));
  const flip = dFlip < dSame;

  const uvs = [];
  const fractions = [];
  const params = [];
  const subset = shared.boundarySubset || shared.points.map((_, i) => i);
  const count = subset.length;
  let cursor = 0;
  for (let step = 0; step < count; step += 1) {
    const sharedIndex = subset[flip ? count - 1 - step : step];
    const f = shared.fractions[sharedIndex];
    const g = flip ? 1 - f : f; // arc position in pcurve-forward direction
    while (cursor + 1 < cumulative.length - 1 && cumulative[cursor + 1] < g) cursor += 1;
    // Endpoints map to the exact pcurve range ends (no drift at corners).
    let t;
    if (step === 0) {
      t = own.params[0];
    } else if (step === count - 1) {
      t = own.params[own.params.length - 1];
    } else {
      const c0 = cumulative[cursor];
      const c1 = cumulative[cursor + 1];
      const w = c1 > c0 ? (g - c0) / (c1 - c0) : 0;
      t = own.params[cursor] + w * (own.params[cursor + 1] - own.params[cursor]);
    }
    const uv = evaluatePCurve(pcurve, floats, t);
    // Guard: the mapped point must land near the shared point it claims to be
    // (a rotated closed-pcurve correspondence, a mismatched locus). Measured on
    // the corpus, arclength interpolation alone maps within tolerance — a
    // golden-section polish added 24 surface evals per point for no gain.
    const target = shared.points[sharedIndex];
    const mapped3 = evaluateSurface(surface, floats, uv[0], uv[1]);
    if (length3(sub(mapped3, target)) > tolerance * 2) return null;
    uvs.push(uv);
    fractions.push(f);
    params.push(t);
  }

  // The shared polyline is sampled by the CURVE's chord error, but this face's
  // SURFACE can bulge between those points (a straight edge on a cylinder):
  // densify by surface chord error so the first row of triangles keeps the
  // face's own tolerance. New fractions still materialize on the exact curve
  // (edgePointAt), so cross-face conformity is unaffected — the union simply
  // grows where a face needed more. Planes cannot bulge; every 3D point is
  // evaluated once and reused across rounds (this loop dominated NURBS-heavy
  // components before that).
  if (surface.kind !== "plane") {
    const points3 = uvs.map((uvPoint) => evaluateSurface(surface, floats, uvPoint[0], uvPoint[1]));
    for (let depth = 0; depth < 4; depth += 1) {
      let split = false;
      const nextUvs = [uvs[0]];
      const nextFractions = [fractions[0]];
      const nextParams = [params[0]];
      const nextPoints3 = [points3[0]];
      for (let i = 0; i + 1 < uvs.length; i += 1) {
        const pa = points3[i];
        const pb = points3[i + 1];
        const tMid = (params[i] + params[i + 1]) / 2;
        const uvMid = evaluatePCurve(pcurve, floats, tMid);
        const pm = evaluateSurface(surface, floats, uvMid[0], uvMid[1]);
        const chordMid = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2];
        if (length3(sub(pm, chordMid)) > tolerance) {
          nextUvs.push(uvMid);
          nextFractions.push((fractions[i] + fractions[i + 1]) / 2);
          nextParams.push(tMid);
          nextPoints3.push(pm);
          split = true;
        }
        nextUvs.push(uvs[i + 1]);
        nextFractions.push(fractions[i + 1]);
        nextParams.push(params[i + 1]);
        nextPoints3.push(points3[i + 1]);
      }
      uvs.length = 0;
      fractions.length = 0;
      params.length = 0;
      points3.length = 0;
      uvs.push(...nextUvs);
      fractions.push(...nextFractions);
      params.push(...nextParams);
      points3.push(...nextPoints3);
      if (!split) break;
    }
  }
  return { uvs, fractions };
}

// THE canonical position of arc fraction `f` on a shared edge. Every face
// computes boundary coordinates through this one function, so the same
// (edge, fraction) yields bit-identical floats on both sides of the edge.
// Between polyline knots it evaluates the EXACT curve at an interpolated
// parameter (not a chord lerp): a minted mid-segment vertex therefore lies ON
// the model edge, which is what keeps a planar face's bore boundary at the
// true radius instead of a chord's sag inside it.
export function edgePointAt(shared, fraction, floats) {
  const fractions = shared.fractions;
  const last = fractions.length - 1;
  if (fraction <= fractions[0]) return shared.points[0];
  if (fraction >= fractions[last]) return shared.points[last];
  let lo = 0;
  let hi = last;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (fractions[mid] <= fraction) lo = mid;
    else hi = mid;
  }
  const f0 = fractions[lo];
  const f1 = fractions[lo + 1];
  if (fraction === f0) return shared.points[lo];
  if (fraction === f1) return shared.points[lo + 1];
  const w = f1 > f0 ? (fraction - f0) / (f1 - f0) : 0;
  if (shared.curve && floats) {
    const t = shared.params[lo] + w * (shared.params[lo + 1] - shared.params[lo]);
    return evaluateCurve3(shared.curve, floats, t);
  }
  const a = shared.points[lo];
  const b = shared.points[lo + 1];
  return [a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1]), a[2] + w * (b[2] - a[2])];
}

// Sample one model edge's exact 3D curve: the shared polyline every adjacent
// face conforms to, and the display overlay's polyline (drawn edges therefore
// coincide exactly with mesh boundaries).
function sampleSharedEdge(curve, floats, tolerance) {
  const [t0, t1] = curve.range;
  const start = evaluateCurve3(curve, floats, t0);
  const end = evaluateCurve3(curve, floats, t1);
  const closed = length3(sub(start, end)) <= tolerance;
  const initial = curve.kind === "line" ? 1 : Math.max(closed ? 8 : 4, curve.n ?? 2);
  const params = [];
  for (let i = 0; i <= initial; i += 1) params.push(t0 + ((t1 - t0) * i) / initial);
  let depth = 0;
  while (depth < DEFAULT_OPTIONS.maxRefineDepth) {
    let split = false;
    const next = [params[0]];
    for (let i = 0; i + 1 < params.length; i += 1) {
      const a = params[i];
      const b = params[i + 1];
      const mid = (a + b) / 2;
      const pa = evaluateCurve3(curve, floats, a);
      const pb = evaluateCurve3(curve, floats, b);
      const pm = evaluateCurve3(curve, floats, mid);
      const chordMid = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2];
      if (length3(sub(pm, chordMid)) > tolerance) {
        next.push(mid);
        split = true;
      }
      next.push(b);
    }
    params.length = 0;
    params.push(...next);
    if (!split) break;
    depth += 1;
  }
  const points = params.map((t) => evaluateCurve3(curve, floats, t));
  if (closed && points.length > 1) {
    // The seam is ONE physical point; share the array so fraction 0 and 1
    // pin to bit-identical coordinates.
    points[points.length - 1] = points[0];
  }
  const fractions = [0];
  for (let i = 1; i < points.length; i += 1) {
    fractions.push(fractions[i - 1] + length3(sub(points[i], points[i - 1])));
  }
  const total = fractions[fractions.length - 1];
  if (total > 0) {
    for (let i = 0; i < fractions.length; i += 1) fractions[i] /= total;
    fractions[fractions.length - 1] = 1;
  }
  // The polyline serves two consumers at different densities: the display
  // overlay wants chord tolerance, but face BOUNDARIES only need loop
  // tolerance — mapping every chord-fine point into every adjacent face made
  // NURBS-heavy components pay for boundary vertices they didn't need.
  // boundarySubset marks a loop-tolerance decimation (endpoints always kept).
  const boundarySubset = [0];
  {
    const boundaryTolerance = tolerance * (DEFAULT_OPTIONS.loopTolerance / DEFAULT_OPTIONS.chordTolerance);
    let anchor = 0;
    for (let i = 1; i < points.length; i += 1) {
      if (i === points.length - 1) {
        boundarySubset.push(i);
        break;
      }
      // Keep i's predecessor when dropping [anchor..i] would deviate from the
      // polyline by more than the boundary tolerance (max point-to-chord).
      const a = points[anchor];
      const b = points[i + 1];
      let worst = 0;
      for (let k = anchor + 1; k <= i; k += 1) {
        const ap = sub(points[k], a);
        const ab = sub(b, a);
        const abLen2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2];
        const t = abLen2 > 0 ? (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / abLen2 : 0;
        const clamped = Math.max(0, Math.min(1, t));
        const q = [a[0] + clamped * ab[0], a[1] + clamped * ab[1], a[2] + clamped * ab[2]];
        worst = Math.max(worst, length3(sub(points[k], q)));
        if (worst > boundaryTolerance) break;
      }
      if (worst > boundaryTolerance) {
        boundarySubset.push(i);
        anchor = i;
      }
    }
  }
  return { curve, params, points, fractions, closed, length: total, boundarySubset };
}

// --- Face triangulation ------------------------------------------------------

function polygonArea(points) {
  let area = 0;
  for (let i = 0; i < points.length; i += 1) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    area += x0 * y1 - x1 * y0;
  }
  return area / 2;
}

// --- Grid triangulation ------------------------------------------------------

function gridStepsForDirection(face, floats, uvBox, chordLimit, direction) {
  const [u0, u1, v0, v1] = uvBox;
  const span = direction === 0 ? u1 - u0 : v1 - v0;
  if (span <= 0) return 1;
  const PROBES = 4;
  let worst = 0;
  for (let line = 0; line <= PROBES; line += 1) {
    const across =
      direction === 0
        ? v0 + ((v1 - v0) * line) / PROBES
        : u0 + ((u1 - u0) * line) / PROBES;
    for (let i = 0; i < PROBES; i += 1) {
      const t0 = (direction === 0 ? u0 : v0) + (span * i) / PROBES;
      const t1 = t0 + span / PROBES;
      const tm = (t0 + t1) / 2;
      const at = (t) =>
        direction === 0
          ? evaluateSurface(face.surface, floats, t, across)
          : evaluateSurface(face.surface, floats, across, t);
      const pa = at(t0);
      const pb = at(t1);
      const pm = at(tm);
      const chordMid = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2];
      worst = Math.max(worst, length3(sub(pm, chordMid)));
    }
  }
  if (worst <= chordLimit) return 1;
  // Chord error scales ~h^2: required steps per probe interval.
  const perInterval = Math.sqrt(worst / chordLimit);
  return Math.min(256, Math.max(1, Math.ceil(PROBES * perInterval)));
}

function pointInLoopsEvenOdd(loops, u, v) {
  let inside = false;
  for (const points of loops) {
    for (let i = 0; i < points.length; i += 1) {
      const [x0, y0] = points[i];
      const [x1, y1] = points[(i + 1) % points.length];
      if (y0 > v !== y1 > v && u < ((x1 - x0) * (v - y0)) / (y1 - y0) + x0) {
        inside = !inside;
      }
    }
  }
  return inside;
}

// Sutherland–Hodgman against an axis-aligned rectangle.
function clipPolygonToCell(points, cu0, cu1, cv0, cv1) {
  let output = points;
  for (const [axis, bound, keepBelow] of [
    [0, cu0, false],
    [0, cu1, true],
    [1, cv0, false],
    [1, cv1, true],
  ]) {
    const input = output;
    output = [];
    for (let i = 0; i < input.length; i += 1) {
      const current = input[i];
      const previous = input[(i + input.length - 1) % input.length];
      const currentIn = keepBelow ? current[axis] <= bound : current[axis] >= bound;
      const previousIn = keepBelow ? previous[axis] <= bound : previous[axis] >= bound;
      if (currentIn !== previousIn) {
        const t = (bound - previous[axis]) / (current[axis] - previous[axis]);
        output.push([
          previous[0] + t * (current[0] - previous[0]),
          previous[1] + t * (current[1] - previous[1]),
        ]);
      }
      if (currentIn) output.push(current);
    }
    if (output.length < 3) return [];
  }
  return output;
}

function gridTriangulate(face, floats, loops, chordLimit) {
  let minU = Infinity;
  let maxU = -Infinity;
  let minV = Infinity;
  let maxV = -Infinity;
  for (const points of loops) {
    for (const [u, v] of points) {
      if (u < minU) minU = u;
      if (u > maxU) maxU = u;
      if (v < minV) minV = v;
      if (v > maxV) maxV = v;
    }
  }
  if (!(maxU > minU) || !(maxV > minV)) return null;
  const uvBox = [minU, maxU, minV, maxV];
  const stepsU = gridStepsForDirection(face, floats, uvBox, chordLimit, 0);
  const stepsV = gridStepsForDirection(face, floats, uvBox, chordLimit, 1);
  const du = (maxU - minU) / stepsU;
  const dv = (maxV - minV) / stepsV;

  // Bucket loop segments by the cells their bounding boxes touch. The same
  // buckets serve two consumers: boundary-cell detection here, and model-
  // edge attribution of region-boundary mesh edges afterwards.
  const cellOf = (u, v) => [
    Math.min(stepsU - 1, Math.max(0, Math.floor((u - minU) / du))),
    Math.min(stepsV - 1, Math.max(0, Math.floor((v - minV) / dv))),
  ];
  const crossed = new Set();
  const segments = [];
  const segmentsByCell = new Map();
  for (const points of loops) {
    const ords = points.segmentOrds || [];
    const metas = points.segmentMeta || [];
    for (let i = 0; i < points.length; i += 1) {
      const [x0, y0] = points[i];
      const [x1, y1] = points[(i + 1) % points.length];
      const segIndex = segments.length;
      segments.push([x0, y0, x1, y1, ords[i] || 0, metas[i] || null]);
      const [ca0, cb0] = cellOf(Math.min(x0, x1), Math.min(y0, y1));
      const [ca1, cb1] = cellOf(Math.max(x0, x1), Math.max(y0, y1));
      for (let cu = ca0; cu <= ca1; cu += 1) {
        for (let cv = cb0; cv <= cb1; cv += 1) {
          const key = cu * stepsV + cv;
          crossed.add(key);
          let list = segmentsByCell.get(key);
          if (!list) segmentsByCell.set(key, (list = []));
          list.push(segIndex);
        }
      }
    }
  }

  const uvVerts = [];
  const vertexIds = new Map();
  const vertexId = (u, v) => {
    const key = `${u}:${v}`;
    let id = vertexIds.get(key);
    if (id === undefined) {
      id = uvVerts.length;
      uvVerts.push([u, v]);
      vertexIds.set(key, id);
    }
    return id;
  };

  const triangles = [];
  const degenerateLimit = Math.abs((maxU - minU) * (maxV - minV)) * 1e-12 || 1e-30;
  // Canonical grid-line coordinates: adjacent cells MUST address their shared
  // border with bitwise-identical floats, or vertex dedup misses and every
  // cell border becomes an unmerged crack (visible as hairline banding).
  const gridU = [];
  const gridV = [];
  for (let iu = 0; iu <= stepsU; iu += 1) gridU.push(iu === stepsU ? maxU : minU + iu * du);
  for (let iv = 0; iv <= stepsV; iv += 1) gridV.push(iv === stepsV ? maxV : minV + iv * dv);
  for (let iu = 0; iu < stepsU; iu += 1) {
    for (let iv = 0; iv < stepsV; iv += 1) {
      const cu0 = gridU[iu];
      const cu1 = gridU[iu + 1];
      const cv0 = gridV[iv];
      const cv1 = gridV[iv + 1];
      if (!crossed.has(iu * stepsV + iv)) {
        // Uncrossed cell: uniformly inside or outside; test the center.
        if (!pointInLoopsEvenOdd(loops, (cu0 + cu1) / 2, (cv0 + cv1) / 2)) continue;
        const a = vertexId(cu0, cv0);
        const b = vertexId(cu1, cv0);
        const c = vertexId(cu1, cv1);
        const d = vertexId(cu0, cv1);
        triangles.push(a, b, c, a, c, d);
        continue;
      }
      // Boundary cell: clip every loop to the cell, then earcut the piece.
      const clipped = loops
        .map((points) => clipPolygonToCell(points, cu0, cu1, cv0, cv1))
        .filter((points) => points.length >= 3);
      if (!clipped.length) continue;
      let outerIndex = 0;
      let outerAbsArea = 0;
      for (let i = 0; i < clipped.length; i += 1) {
        const absArea = Math.abs(polygonArea(clipped[i]));
        if (absArea > outerAbsArea) {
          outerAbsArea = absArea;
          outerIndex = i;
        }
      }
      if (outerAbsArea <= degenerateLimit) continue;
      const contour = clipped[outerIndex].map(([x, y]) => new Vector2(x, y));
      const holes = clipped
        .filter((_, i) => i !== outerIndex)
        .map((points) => points.map(([x, y]) => new Vector2(x, y)));
      let cellFaces;
      try {
        cellFaces = ShapeUtils.triangulateShape(contour, holes);
      } catch {
        continue;
      }
      const localPoints = [...contour, ...holes.flat()];
      const localIds = localPoints.map(({ x, y }) => vertexId(x, y));
      for (const [a, b, c] of cellFaces) {
        const A = localPoints[a];
        const B = localPoints[b];
        const C = localPoints[c];
        const cross = (B.x - A.x) * (C.y - A.y) - (C.x - A.x) * (B.y - A.y);
        if (Math.abs(cross) / 2 > degenerateLimit) {
          triangles.push(localIds[a], localIds[b], localIds[c]);
        }
      }
    }
  }
  return {
    uvVerts,
    triangles,
    vertexIds,
    segmentIndex: { segments, segmentsByCell, cellOf, stepsV },
  };
}

function projectToSegment(px, py, x0, y0, x1, y1) {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const lengthSq = dx * dx + dy * dy;
  let t = lengthSq > 0 ? ((px - x0) * dx + (py - y0) * dy) / lengthSq : 0;
  t = Math.max(0, Math.min(1, t));
  const qx = x0 + t * dx;
  const qy = y0 + t * dy;
  return { distSq: (px - qx) * (px - qx) + (py - qy) * (py - qy), t };
}

function pointToSegmentDistanceSq(px, py, x0, y0, x1, y1) {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const lengthSq = dx * dx + dy * dy;
  let t = lengthSq > 0 ? ((px - x0) * dx + (py - y0) * dy) / lengthSq : 0;
  t = Math.max(0, Math.min(1, t));
  const qx = x0 + t * dx;
  const qy = y0 + t * dy;
  return (px - qx) * (px - qx) + (py - qy) * (py - qy);
}

// Per-triangle model-edge ordinals for the barycentric edge overlay, in the
// GLB half-edge convention: side 0 = (v1,v2), side 1 = (v2,v0),
// side 2 = (v0,v1). A mesh edge belongs to a model edge when it appears in
// exactly one triangle (region boundary — interior edges are shared by two)
// and both endpoints lie on one sampled trim segment, whose ordinal it
// inherits. Clip intersections and refinement midpoints stay on their
// segment, so containment is exact up to float noise.
function attributeBoundaryEdges(triangles, uvVerts, segmentIndex, epsilon) {
  const counts = new Map();
  const keyOf = (a, b) => (a < b ? a * 0x100000000 + b : b * 0x100000000 + a);
  for (let t = 0; t < triangles.length; t += 3) {
    const [a, b, c] = [triangles[t], triangles[t + 1], triangles[t + 2]];
    for (const [p, q] of [[a, b], [b, c], [c, a]]) {
      const key = keyOf(p, q);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  const { segments, segmentsByCell, cellOf, stepsV } = segmentIndex;
  const epsilonSq = epsilon * epsilon;
  const ordCache = new Map();
  const ordOfMeshEdge = (p, q) => {
    const key = keyOf(p, q);
    if (counts.get(key) !== 1) return 0;
    let ord = ordCache.get(key);
    if (ord !== undefined) return ord;
    ord = 0;
    const [pu, pv] = uvVerts[p];
    const [qu, qv] = uvVerts[q];
    const [cu, cv] = cellOf((pu + qu) / 2, (pv + qv) / 2);
    const candidates = segmentsByCell.get(cu * stepsV + cv) || [];
    for (const segIdx of candidates) {
      const [x0, y0, x1, y1, segOrd] = segments[segIdx];
      if (!segOrd) continue;
      if (
        pointToSegmentDistanceSq(pu, pv, x0, y0, x1, y1) < epsilonSq &&
        pointToSegmentDistanceSq(qu, qv, x0, y0, x1, y1) < epsilonSq
      ) {
        ord = segOrd;
        break;
      }
    }
    ordCache.set(key, ord);
    return ord;
  };
  const sideOrds = new Uint32Array(triangles.length);
  for (let t = 0; t < triangles.length; t += 3) {
    const [a, b, c] = [triangles[t], triangles[t + 1], triangles[t + 2]];
    sideOrds[t] = ordOfMeshEdge(b, c);
    sideOrds[t + 1] = ordOfMeshEdge(c, a);
    sideOrds[t + 2] = ordOfMeshEdge(a, b);
  }
  return sideOrds;
}

export function tessellateFace(face, floats, scale, options = {}) {
  const raw = tessellateFaceRaw(face, floats, scale, options, null);
  return raw ? finalizeFaceMesh(face, raw) : null;
}

function tessellateFaceRaw(face, floats, scale, options = {}, sharedEdges = null) {
  const { chordTolerance, loopTolerance, angleTolerance, maxRefineDepth } = {
    ...DEFAULT_OPTIONS,
    ...options,
  };
  // Tolerances scale by the FACE's own extent (min of face and component
  // scale): small curved features refine properly instead of inheriting a
  // large component's coarse budget.
  const roughLimit = loopTolerance * scale;
  const loops0 = face.loops
    .map((loop) => sampleLoopPolygon(face, loop, floats, roughLimit, sharedEdges))
    .filter((points) => points.length >= 3);
  if (!loops0.length) return null;
  let faceScale = 0;
  {
    let minU = Infinity;
    let maxU = -Infinity;
    let minV = Infinity;
    let maxV = -Infinity;
    for (const points of loops0) {
      for (const [u, v] of points) {
        if (u < minU) minU = u;
        if (u > maxU) maxU = u;
        if (v < minV) minV = v;
        if (v > maxV) maxV = v;
      }
    }
    // Probe the 3D extent from UV box corners + center.
    const probes = [
      [minU, minV],
      [maxU, minV],
      [minU, maxV],
      [maxU, maxV],
      [(minU + maxU) / 2, (minV + maxV) / 2],
    ].map(([u, v]) => evaluateSurface(face.surface, floats, u, v));
    for (let i = 0; i < probes.length; i += 1) {
      for (let j = i + 1; j < probes.length; j += 1) {
        faceScale = Math.max(faceScale, length3(sub(probes[i], probes[j])));
      }
    }
  }
  const local = Math.max(Math.min(scale, faceScale * 4), 1e-9);
  const chordLimit = chordTolerance * local;
  const loopLimit = loopTolerance * local;

  const loops =
    loopLimit < roughLimit
      ? face.loops
          .map((loop) => sampleLoopPolygon(face, loop, floats, loopLimit, sharedEdges))
          .filter((points) => points.length >= 3)
      : loops0;
  if (!loops.length) return null;

  // Base triangulation: a curvature-driven UV grid, with trim loops clipped
  // per cell. Interior cells emit two well-shaped triangles; boundary cells
  // triangulate their clipped polygon with earcut. This is boundary-exact
  // like a global earcut but never produces the long fans and caps that
  // made global earcut meshes fat on curved faces (Schwarz-lantern effect).
  const built = gridTriangulate(face, floats, loops, chordLimit);
  if (!built) return null;
  const { uvVerts, triangles: baseTriangles, vertexIds, segmentIndex } = built;
  let triangles = baseTriangles;
  if (!triangles.length) return null;

  // Crack-free refinement, two-phase per round so neighbours stay
  // conforming: (1) MARK edges — an edge splits when its 3D midpoint
  // chord error exceeds tolerance, and a triangle whose CENTROID deviates
  // from the surface (the earcut-sliver failure mode: short edges, curved
  // interior) marks its longest edge; (2) SUBDIVIDE every triangle by its
  // marked edges, materializing midpoints through a shared cache.
  const xyz = uvVerts.map(([u, v]) => evaluateSurface(face.surface, floats, u, v));
  const vertexNormal = ([u, v]) =>
    evaluateSurfaceNormal(face.surface, floats, u, v, face.uv, false);
  const nrm = uvVerts.map(vertexNormal);
  const angleCos = Math.cos(angleTolerance);
  const edgeKey = (a, b) => (a < b ? `${a}_${b}` : `${b}_${a}`);
  for (let depth = 0; depth < maxRefineDepth; depth += 1) {
    const marked = new Set();
    const chordChecked = new Map();
    const edgeChordBad = (a, b) => {
      const key = edgeKey(a, b);
      let bad = chordChecked.get(key);
      if (bad === undefined) {
        const mu = (uvVerts[a][0] + uvVerts[b][0]) / 2;
        const mv = (uvVerts[a][1] + uvVerts[b][1]) / 2;
        const surfaceMid = evaluateSurface(face.surface, floats, mu, mv);
        const chordMid = [
          (xyz[a][0] + xyz[b][0]) / 2,
          (xyz[a][1] + xyz[b][1]) / 2,
          (xyz[a][2] + xyz[b][2]) / 2,
        ];
        bad =
          length3(sub(surfaceMid, chordMid)) > chordLimit ||
          nrm[a][0] * nrm[b][0] + nrm[a][1] * nrm[b][1] + nrm[a][2] * nrm[b][2] < angleCos;
        chordChecked.set(key, bad);
      }
      return bad;
    };
    for (let t = 0; t < triangles.length; t += 3) {
      const a = triangles[t];
      const b = triangles[t + 1];
      const c = triangles[t + 2];
      let anyEdge = false;
      for (const [p, q] of [[a, b], [b, c], [c, a]]) {
        if (edgeChordBad(p, q)) {
          marked.add(edgeKey(p, q));
          anyEdge = true;
        }
      }
      if (anyEdge) continue;
      const cu = (uvVerts[a][0] + uvVerts[b][0] + uvVerts[c][0]) / 3;
      const cv = (uvVerts[a][1] + uvVerts[b][1] + uvVerts[c][1]) / 3;
      const surfaceCentroid = evaluateSurface(face.surface, floats, cu, cv);
      const flatCentroid = [
        (xyz[a][0] + xyz[b][0] + xyz[c][0]) / 3,
        (xyz[a][1] + xyz[b][1] + xyz[c][1]) / 3,
        (xyz[a][2] + xyz[b][2] + xyz[c][2]) / 3,
      ];
      // Cap detection: a triangle of near-collinear UV points bridges the
      // surface as a chord-vs-arc cap — its FACET normal swings away from
      // the surface normal even though every vertex (and its centroid, and
      // its edge midpoints) sits close to the surface.
      const e1 = sub(xyz[b], xyz[a]);
      const e2 = sub(xyz[c], xyz[a]);
      const facet = [
        e1[1] * e2[2] - e1[2] * e2[1],
        e1[2] * e2[0] - e1[0] * e2[2],
        e1[0] * e2[1] - e1[1] * e2[0],
      ];
      const facetLength = length3(facet);
      const surfaceNormal = nrm[a];
      const misaligned =
        facetLength > 1e-30 &&
        Math.abs(
          (facet[0] * surfaceNormal[0] + facet[1] * surfaceNormal[1] + facet[2] * surfaceNormal[2]) /
            facetLength,
        ) < angleCos;
      if (misaligned || length3(sub(surfaceCentroid, flatCentroid)) > chordLimit) {
        let longest = [a, b];
        let longestSq = -1;
        for (const [p, q] of [[a, b], [b, c], [c, a]]) {
          const du = uvVerts[p][0] - uvVerts[q][0];
          const dv = uvVerts[p][1] - uvVerts[q][1];
          const sq = du * du + dv * dv;
          if (sq > longestSq) {
            longestSq = sq;
            longest = [p, q];
          }
        }
        marked.add(edgeKey(longest[0], longest[1]));
      }
    }
    if (!marked.size) break;

    const midCache = new Map();
    const midpointOf = (a, b) => {
      const key = edgeKey(a, b);
      if (!marked.has(key)) return -1;
      let midIndex = midCache.get(key);
      if (midIndex === undefined) {
        const mu = (uvVerts[a][0] + uvVerts[b][0]) / 2;
        const mv = (uvVerts[a][1] + uvVerts[b][1]) / 2;
        midIndex = uvVerts.length;
        uvVerts.push([mu, mv]);
        xyz.push(evaluateSurface(face.surface, floats, mu, mv));
        nrm.push(vertexNormal([mu, mv]));
        midCache.set(key, midIndex);
      }
      return midIndex;
    };

    const next = [];
    for (let t = 0; t < triangles.length; t += 3) {
      const a = triangles[t];
      const b = triangles[t + 1];
      const c = triangles[t + 2];
      const mab = midpointOf(a, b);
      const mbc = midpointOf(b, c);
      const mca = midpointOf(c, a);
      const splits = (mab >= 0) + (mbc >= 0) + (mca >= 0);
      if (splits === 0) {
        next.push(a, b, c);
        continue;
      }
      if (splits === 3) {
        next.push(a, mab, mca, mab, b, mbc, mca, mbc, c, mab, mbc, mca);
      } else if (splits === 2) {
        // Rotate so the un-split edge is (c, a).
        let [va, vb, vc, m1, m2] =
          mab >= 0 && mbc >= 0
            ? [a, b, c, mab, mbc]
            : mbc >= 0 && mca >= 0
              ? [b, c, a, mbc, mca]
              : [c, a, b, mca, mab];
        next.push(va, m1, m2, va, m2, vc, m1, vb, m2);
        void vb;
      } else {
        // Rotate so the split edge is (a, b).
        const [va, vb, vc, m] =
          mab >= 0 ? [a, b, c, mab] : mbc >= 0 ? [b, c, a, mbc] : [c, a, b, mca];
        next.push(va, m, vc, m, vb, vc);
      }
    }
    triangles = next;
  }

  // Pin every boundary vertex onto its shared edge polyline: original loop
  // points, cell-clip intersections and refinement midpoints all lie ON a
  // sampled trim segment in UV, so a proximity pass over the segment index
  // finds them without threading metadata through clipping and earcut. Their
  // 3D coordinates are recomputed through edgePointAt, the one function both
  // adjacent faces use — the same (edge, fraction) is bit-identical across
  // faces.
  const boundary = new Map(); // vertex index -> [{ ord, f }, ...]
  if (sharedEdges) {
    let spanUPin = 0;
    let spanVPin = 0;
    for (const [u, v] of uvVerts) {
      spanUPin = Math.max(spanUPin, Math.abs(u));
      spanVPin = Math.max(spanVPin, Math.abs(v));
    }
    const eps = Math.max(spanUPin, spanVPin, 1) * 1e-7;
    const { segments, segmentsByCell, cellOf, stepsV } = segmentIndex;
    for (let i = 0; i < uvVerts.length; i += 1) {
      const [u, v] = uvVerts[i];
      const [cu, cv] = cellOf(u, v);
      const candidates = segmentsByCell.get(cu * stepsV + cv);
      if (!candidates) continue;
      // A vertex can lie on SEVERAL model edges (a corner lies on both of the
      // edges that meet there); keep the best match PER EDGE, or conformity
      // is blind to whichever edge lost the single-label toss.
      const byOrd = new Map();
      for (const segIdx of candidates) {
        const [x0, y0, x1, y1, ord, meta] = segments[segIdx];
        if (!meta) continue;
        let projected = projectToSegment(u, v, x0, y0, x1, y1);
        if (projected.distSq >= eps * eps) {
          // Adjacent pcurves can disagree about a shared corner's UV by more
          // than the on-segment eps; catch the corner through plain endpoint
          // proximity so it still carries THIS edge's label.
          const cornerEpsSq = eps * eps * 16;
          const d0 = (u - x0) * (u - x0) + (v - y0) * (v - y0);
          const d1 = (u - x1) * (u - x1) + (v - y1) * (v - y1);
          if (d0 < cornerEpsSq) projected = { distSq: d0, t: 0 };
          else if (d1 < cornerEpsSq) projected = { distSq: d1, t: 1 };
          else continue;
        }
        const existing = byOrd.get(ord);
        if (existing && existing.distSq <= projected.distSq) continue;
        // Snap segment endpoints to their exact fractions so the same corner
        // dedups across faces (and edgePointAt returns the stored polyline
        // point verbatim).
        const t = projected.t < 1e-9 ? 0 : projected.t > 1 - 1e-9 ? 1 : projected.t;
        byOrd.set(ord, { distSq: projected.distSq, f: meta.f0 + t * (meta.f1 - meta.f0) });
      }
      if (!byOrd.size) continue;
      const labels = [];
      let pinTo = null;
      for (const [ord, { distSq, f }] of byOrd) {
        const shared = sharedEdges.get(ord);
        if (!shared) continue;
        const fraction = shared.closed && f >= 1 - 1e-12 ? 0 : f;
        labels.push({ ord, f: fraction });
        if (!pinTo || distSq < pinTo.distSq) pinTo = { distSq, ord, f: fraction, shared };
      }
      if (!labels.length) continue;
      // Convention: labels[0] is the label the vertex is PINNED through.
      labels.sort((x, y) => (x.ord === pinTo.ord && x.f === pinTo.f ? -1 : y.ord === pinTo.ord && y.f === pinTo.f ? 1 : 0));
      boundary.set(i, labels);
      xyz[i] = edgePointAt(pinTo.shared, pinTo.f, floats);
    }
  }

  return { uvVerts, xyz, nrm, triangles, segmentIndex, boundary };
}

// One refinement round over a raw face mesh that never splits BOUNDARY edges
// (their vertex sets are conformity-controlled): the fan triangles minted by
// the conformity pass are born after the main refinement ran, so without this
// their interiors stay flat across curved surfaces and the mesh loses the
// bulge the tolerance promises.
function refineInteriorPostConform(face, raw, floats, options = {}) {
  const { chordTolerance, angleTolerance, maxRefineDepth } = {
    ...DEFAULT_OPTIONS,
    ...options,
  };
  const { uvVerts, xyz, nrm, boundary } = raw;
  const minted = raw.mintedVerts;
  if (!minted?.size) return;
  let triangles = raw.triangles;
  let scale = 0;
  for (const p of xyz) {
    scale = Math.max(scale, length3(sub(p, xyz[0])));
  }
  const chordLimit = chordTolerance * Math.max(scale, 1e-9);
  const vertexNormal = ([u, v]) =>
    evaluateSurfaceNormal(face.surface, floats, u, v, face.uv, false);
  const angleCos = Math.cos(angleTolerance);
  const edgeKey = (a, b) => (a < b ? `${a}_${b}` : `${b}_${a}`);
  void angleCos;
  const REFINE_DEPTH = Math.min(3, maxRefineDepth);
  for (let depth = 0; depth < REFINE_DEPTH; depth += 1) {
    const marked = new Set();
    for (let t = 0; t < triangles.length; t += 3) {
      const [a, b, c] = [triangles[t], triangles[t + 1], triangles[t + 2]];
      // Only the fans the conformity pass created: everything else was
      // already refined to tolerance by the main pass.
      if (!minted.has(a) && !minted.has(b) && !minted.has(c)) continue;
      for (const [p, q] of [[a, b], [b, c], [c, a]]) {
        if (boundary.has(p) && boundary.has(q)) continue; // conformity-owned
        const mu = (uvVerts[p][0] + uvVerts[q][0]) / 2;
        const mv = (uvVerts[p][1] + uvVerts[q][1]) / 2;
        const surfaceMid = evaluateSurface(face.surface, floats, mu, mv);
        if (!surfaceMid || !Number.isFinite(surfaceMid[0])) continue;
        const chordMid = [
          (xyz[p][0] + xyz[q][0]) / 2,
          (xyz[p][1] + xyz[q][1]) / 2,
          (xyz[p][2] + xyz[q][2]) / 2,
        ];
        if (length3(sub(surfaceMid, chordMid)) > chordLimit) {
          marked.add(edgeKey(p, q));
        }
      }
    }
    if (!marked.size) break;
    const midCache = new Map();
    const midpointOf = (a, b) => {
      const key = edgeKey(a, b);
      if (!marked.has(key)) return -1;
      let midIndex = midCache.get(key);
      if (midIndex === undefined) {
        const mu = (uvVerts[a][0] + uvVerts[b][0]) / 2;
        const mv = (uvVerts[a][1] + uvVerts[b][1]) / 2;
        midIndex = uvVerts.length;
        uvVerts.push([mu, mv]);
        xyz.push(evaluateSurface(face.surface, floats, mu, mv));
        nrm.push(vertexNormal([mu, mv]));
        midCache.set(key, midIndex);
      }
      return midIndex;
    };
    const next = [];
    for (let t = 0; t < triangles.length; t += 3) {
      const a = triangles[t];
      const b = triangles[t + 1];
      const c = triangles[t + 2];
      const mab = midpointOf(a, b);
      const mbc = midpointOf(b, c);
      const mca = midpointOf(c, a);
      const splits = (mab >= 0) + (mbc >= 0) + (mca >= 0);
      if (splits === 0) {
        next.push(a, b, c);
      } else if (splits === 3) {
        next.push(a, mab, mca, mab, b, mbc, mca, mbc, c, mab, mbc, mca);
      } else if (splits === 2) {
        const [va, vb, vc, m1, m2] =
          mab >= 0 && mbc >= 0
            ? [a, b, c, mab, mbc]
            : mbc >= 0 && mca >= 0
              ? [b, c, a, mbc, mca]
              : [c, a, b, mca, mab];
        next.push(va, m1, m2, va, m2, vc, m1, vb, m2);
        void vb;
      } else {
        const [va, vb, vc, m] =
          mab >= 0 ? [a, b, c, mab] : mbc >= 0 ? [b, c, a, mbc] : [c, a, b, mca];
        next.push(va, m, vc, m, vb, vc);
      }
    }
    triangles = next;
  }
  raw.triangles = triangles;
}

export function finalizeFaceMesh(face, raw) {
  const { uvVerts, xyz, nrm, triangles, segmentIndex } = raw;
  const positions = new Float32Array(xyz.length * 3);
  const normals = new Float32Array(xyz.length * 3);
  const sign = face.reversed ? -1 : 1;
  for (let i = 0; i < xyz.length; i += 1) {
    positions.set(xyz[i], i * 3);
    normals[i * 3] = nrm[i][0] * sign;
    normals[i * 3 + 1] = nrm[i][1] * sign;
    normals[i * 3 + 2] = nrm[i][2] * sign;
  }
  const indices = face.reversed ? flipWinding(triangles) : Uint32Array.from(triangles);
  let spanU = 0;
  let spanV = 0;
  for (const [u, v] of uvVerts) {
    spanU = Math.max(spanU, Math.abs(u));
    spanV = Math.max(spanV, Math.abs(v));
  }
  const sideOrds = attributeBoundaryEdges(
    indices,
    uvVerts,
    segmentIndex,
    Math.max(spanU, spanV, 1) * 1e-7,
  );
  return {
    positions,
    normals,
    indices,
    sideOrds,
    uv: uvVerts,
  };
}

// Fan-split every face's boundary mesh edges to the UNION of boundary vertex
// fractions across the component, so no T-junction survives: a vertex present
// on one side of a model edge exists on the other side too, with bit-identical
// coordinates (both sides mint it through edgePointAt).
function conformBoundaries(rawFaces, sharedEdges, floats, mergeTolerance = 0) {
  // Fractions closer than the SPATIAL merge tolerance are the same point of
  // the model; a pure 1e-9 fraction eps let two labels 0.1um apart survive as
  // distinct vertices on long edges.
  const fractionEps = (ord) => {
    const shared = sharedEdges.get(ord);
    const spatial = shared?.length ? (mergeTolerance * 0.5) / shared.length : 0;
    return Math.max(1e-9, spatial);
  };
  const FRACTION_EPS = 1e-9;
  // Closed edges wrap: any fraction within eps of 1 IS the seam point 0.
  const canonicalFraction = (ord, f) => {
    const shared = sharedEdges.get(ord);
    if (shared?.closed && f >= 1 - Math.max(1e-6, fractionEps(ord))) return 0;
    return f;
  };
  const fractionsByOrd = new Map();
  const addFraction = (ord, f) => {
    let list = fractionsByOrd.get(ord);
    if (!list) fractionsByOrd.set(ord, (list = []));
    list.push(canonicalFraction(ord, f));
  };
  for (const { raw } of rawFaces) {
    for (const labels of raw.boundary.values()) {
      for (const { ord, f } of labels) addFraction(ord, f);
    }
  }
  for (const [ord, list] of fractionsByOrd) {
    const eps = fractionEps(ord);
    list.sort((a, b) => a - b);
    const unique = [];
    for (const f of list) {
      if (!unique.length || f - unique[unique.length - 1] > eps) unique.push(f);
    }
    // A closed edge's last fraction may have crept within eps of 1 (== 0).
    const shared = sharedEdges.get(ord);
    if (shared?.closed && unique.length > 1 && 1 - unique[unique.length - 1] <= eps) unique.pop();
    fractionsByOrd.set(ord, unique);
  }

  // Canonicalize: snap every boundary fraction to its union representative and
  // re-materialize the vertex through edgePointAt, so knot-vs-lerp float noise
  // and seam wrap cannot make two faces disagree about the same point.
  const representativeOf = (ord, f) => {
    const union = fractionsByOrd.get(ord);
    if (!union) return f;
    let lo = 0;
    let hi = union.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (union[mid] < f) lo = mid + 1;
      else hi = mid;
    }
    const candidates = [union[lo], union[lo - 1] ?? union[lo]];
    return Math.abs(candidates[0] - f) <= Math.abs(candidates[1] - f) ? candidates[0] : candidates[1];
  };
  for (const { raw } of rawFaces) {
    for (const [vertIndex, labels] of raw.boundary) {
      for (const label of labels) {
        label.f = representativeOf(label.ord, canonicalFraction(label.ord, label.f));
      }
      // Deterministic materialization: the LOWEST (ord, f) label wins, so two
      // vertices representing the same model point (in this face or across
      // faces) mint identical coordinates regardless of which segment each
      // was pinned through. Corner objects are welded at the polyline level,
      // so endpoint labels of different edges agree too.
      labels.sort((x, y) => x.ord - y.ord || x.f - y.f);
      const pinned = labels[0];
      const shared = sharedEdges.get(pinned.ord);
      if (shared) raw.xyz[vertIndex] = edgePointAt(shared, pinned.f, floats);
    }
    // Snapping can land two of a face's boundary vertices on the same
    // canonical point; weld them (by exact coordinates — they are
    // bit-identical by construction) and drop the triangles that collapse.
    let spanWeld = 0;
    for (const [u, v] of raw.uvVerts) {
      spanWeld = Math.max(spanWeld, Math.abs(u), Math.abs(v));
    }
    const uvWeldEps = Math.max(spanWeld, 1) * 1e-2;
    const uvClose = (i, j) =>
      Math.abs(raw.uvVerts[i][0] - raw.uvVerts[j][0]) <= uvWeldEps &&
      Math.abs(raw.uvVerts[i][1] - raw.uvVerts[j][1]) <= uvWeldEps;
    const canonicalByPosition = new Map();
    const remap = new Map();
    for (const vertIndex of raw.boundary.keys()) {
      const p = raw.xyz[vertIndex];
      const key = `${p[0]}:${p[1]}:${p[2]}`;
      const bucket = canonicalByPosition.get(key);
      if (bucket === undefined) {
        canonicalByPosition.set(key, [vertIndex]);
        continue;
      }
      // A periodic face's SEAM pair shares 3D coordinates but lives at the
      // two ends of the uv box; merging it corrupts every later uv-based
      // evaluation on that face. Weld only uv-coincident duplicates.
      const target = bucket.find((candidate) => uvClose(candidate, vertIndex));
      if (target !== undefined) remap.set(vertIndex, target);
      else bucket.push(vertIndex);
    }
    if (remap.size) {
      const mapped = [];
      for (let t = 0; t < raw.triangles.length; t += 3) {
        const a = remap.get(raw.triangles[t]) ?? raw.triangles[t];
        const b = remap.get(raw.triangles[t + 1]) ?? raw.triangles[t + 1];
        const c = remap.get(raw.triangles[t + 2]) ?? raw.triangles[t + 2];
        if (a !== b && b !== c && c !== a) mapped.push(a, b, c);
      }
      raw.triangles = mapped;
      for (const vertIndex of remap.keys()) raw.boundary.delete(vertIndex);
    }
  }

  for (const { face, raw } of rawFaces) {
    const { uvVerts, xyz, nrm, boundary } = raw;
    if (!boundary.size) continue;
    // Only REGION-BOUNDARY mesh edges (used by exactly one triangle) may be
    // split: an interior diagonal that merely CONNECTS two pinned vertices is
    // a chord across the face, and pulling union points onto it would drag
    // the mesh toward the model edge (measured as a +1.7% volume error on the
    // sun gear before this gate, plus a fan explosion on notched faces).
    const edgeUse = new Map();
    const pairKey = (p, q) => (p < q ? p * 0x100000000 + q : q * 0x100000000 + p);
    for (let t = 0; t < raw.triangles.length; t += 3) {
      const [a, b, c] = [raw.triangles[t], raw.triangles[t + 1], raw.triangles[t + 2]];
      for (const [p, q] of [[a, b], [b, c], [c, a]]) {
        const key = pairKey(p, q);
        edgeUse.set(key, (edgeUse.get(key) || 0) + 1);
      }
    }
    const vertexNormal = ([u, v]) =>
      evaluateSurfaceNormal(face.surface, floats, u, v, face.uv, false);
    // Per (ord, fraction-bucket) vertex cache so corners shared between this
    // face's own triangles dedup.
    const minted = new Map();
    const vertexAt = (ord, f, a, b, w) => {
      // The pair is part of the key: a SEAM edge appears twice on one face,
      // and reusing side A's minted vertex (with side A's uv) inside side B's
      // triangles evaluates every later uv on the wrong side of the surface.
      const key = `${ord}:${f.toFixed(12)}:${Math.min(a, b)}:${Math.max(a, b)}`;
      let id = minted.get(key);
      if (id !== undefined) return id;
      const uv = [
        uvVerts[a][0] + w * (uvVerts[b][0] - uvVerts[a][0]),
        uvVerts[a][1] + w * (uvVerts[b][1] - uvVerts[a][1]),
      ];
      id = uvVerts.length;
      uvVerts.push(uv);
      const pinned = edgePointAt(sharedEdges.get(ord), f, floats);
      xyz.push(pinned);
      nrm.push(vertexNormal(uv));
      boundary.set(id, [{ ord, f }]);
      (raw.mintedVerts ??= new Set()).add(id);
      minted.set(key, id);
      return id;
    };
    const insertsFor = (p, q) => {
      const labelsP = boundary.get(p);
      const labelsQ = boundary.get(q);
      if (!labelsP || !labelsQ) return null;
      if (edgeUse.get(pairKey(p, q)) !== 1) return null;
      let bp = null;
      let bq = null;
      for (const lp of labelsP) {
        const lq = labelsQ.find((label) => label.ord === lp.ord);
        if (lq) {
          bp = lp;
          bq = lq;
          break;
        }
      }
      if (!bp || !bq) return null;
      const union = fractionsByOrd.get(bp.ord);
      if (!union) return null;
      const shared = sharedEdges.get(bp.ord);
      const eps = fractionEps(bp.ord);
      const between = [];
      if (shared?.closed) {
        // Fractions wrap on a closed edge: 0 and 1 are the same point, and a
        // mesh edge next to the seam (say 0.97 -> 0) spans 3% of the arc, not
        // 97%. Without this, the union fanned across the entire bore of the
        // sun-gear fixture (+13% face area). Take the SHORT arc from p to q.
        const forward = (bq.f - bp.f + 1) % 1;
        const useForward = forward <= 0.5;
        const start = useForward ? bp.f : bq.f;
        const arc = useForward ? forward : (bp.f - bq.f + 1) % 1;
        if (arc <= eps * 2) return null;
        for (const f of union) {
          const d = (f - start + 1) % 1;
          if (d > eps && d < arc - eps) {
            // s: chord parameter from p toward q.
            between.push({ f, s: useForward ? d / arc : 1 - d / arc });
          }
        }
      } else {
        const lo = Math.min(bp.f, bq.f);
        const hi = Math.max(bp.f, bq.f);
        if (hi - lo <= eps * 2) return null;
        for (const f of union) {
          if (f > lo + eps && f < hi - eps) {
            between.push({ f, s: (f - bp.f) / (bq.f - bp.f) });
          }
        }
      }
      if (!between.length) return null;
      between.sort((x, y) => x.s - y.s);
      return { ord: bp.ord, between };
    };

    const out = [];
    const emit = (a, b, c, depth) => {
      if (depth > 24) {
        out.push(a, b, c);
        return;
      }
      for (const [p, q, r] of [[a, b, c], [b, c, a], [c, a, b]]) {
        const found = insertsFor(p, q);
        if (found) {
          let previous = p;
          for (const { f, s: chordParam } of found.between) {
            const m = vertexAt(found.ord, f, p, q, chordParam);
            emit(previous, m, r, depth + 1);
            previous = m;
          }
          emit(previous, q, r, depth + 1);
          return;
        }
      }
      out.push(a, b, c);
    };
    const triangles = raw.triangles;
    for (let t = 0; t < triangles.length; t += 3) {
      emit(triangles[t], triangles[t + 1], triangles[t + 2], 0);
    }
    raw.triangles = out;

    // Splitting can mint a vertex coincident with an existing boundary vertex
    // (same model point reached through another edge's labels). Positions are
    // bit-identical by construction, so a second exact-coordinate weld folds
    // them together and drops any triangle that collapsed.
    let spanAfter = 0;
    for (const [u, v] of uvVerts) {
      spanAfter = Math.max(spanAfter, Math.abs(u), Math.abs(v));
    }
    const uvAfterEps = Math.max(spanAfter, 1) * 1e-2;
    const uvCloseAfter = (i, j) =>
      Math.abs(uvVerts[i][0] - uvVerts[j][0]) <= uvAfterEps &&
      Math.abs(uvVerts[i][1] - uvVerts[j][1]) <= uvAfterEps;
    const canonicalAfter = new Map();
    const remapAfter = new Map();
    for (const vertIndex of boundary.keys()) {
      const p = xyz[vertIndex];
      const key = `${p[0]}:${p[1]}:${p[2]}`;
      const bucket = canonicalAfter.get(key);
      if (bucket === undefined) {
        canonicalAfter.set(key, [vertIndex]);
        continue;
      }
      const target = bucket.find((candidate) => uvCloseAfter(candidate, vertIndex));
      if (target !== undefined) remapAfter.set(vertIndex, target);
      else bucket.push(vertIndex);
    }
    if (remapAfter.size) {
      const mapped = [];
      for (let t = 0; t < raw.triangles.length; t += 3) {
        const a = remapAfter.get(raw.triangles[t]) ?? raw.triangles[t];
        const b = remapAfter.get(raw.triangles[t + 1]) ?? raw.triangles[t + 1];
        const c = remapAfter.get(raw.triangles[t + 2]) ?? raw.triangles[t + 2];
        if (a !== b && b !== c && c !== a) mapped.push(a, b, c);
      }
      raw.triangles = mapped;
      for (const [vertIndex, target] of remapAfter) {
        const labels = boundary.get(vertIndex);
        const targetLabels = boundary.get(target);
        if (labels && targetLabels) {
          for (const label of labels) {
            if (!targetLabels.some((existing) => existing.ord === label.ord && existing.f === label.f)) {
              targetLabels.push(label);
            }
          }
        }
        boundary.delete(vertIndex);
      }
    }
  }
}

function flipWinding(triangles) {
  const flipped = new Uint32Array(triangles.length);
  for (let t = 0; t < triangles.length; t += 3) {
    flipped[t] = triangles[t];
    flipped[t + 1] = triangles[t + 2];
    flipped[t + 2] = triangles[t + 1];
  }
  return flipped;
}

// --- Edge polylines ----------------------------------------------------------

export function polylineEdge(curve, floats, scale, options = {}) {
  const { loopTolerance, maxRefineDepth } = { ...DEFAULT_OPTIONS, ...options };
  const tolerance = loopTolerance * scale;
  const [t0, t1] = curve.range;
  const params = [];
  const initial = Math.max(2, curve.n ?? 2, curve.kind === "line" ? 1 : 8);
  for (let i = 0; i <= initial; i += 1) params.push(t0 + ((t1 - t0) * i) / initial);
  let depth = 0;
  while (depth < maxRefineDepth) {
    let split = false;
    const next = [params[0]];
    for (let i = 0; i + 1 < params.length; i += 1) {
      const a = params[i];
      const b = params[i + 1];
      const mid = (a + b) / 2;
      const pa = evaluateCurve3(curve, floats, a);
      const pb = evaluateCurve3(curve, floats, b);
      const pm = evaluateCurve3(curve, floats, mid);
      const chordMid = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2];
      if (length3(sub(pm, chordMid)) > tolerance) {
        next.push(mid);
        split = true;
      }
      next.push(b);
    }
    params.length = 0;
    params.push(...next);
    if (!split) break;
    depth += 1;
  }
  const polyline = new Float32Array(params.length * 3);
  for (let i = 0; i < params.length; i += 1) {
    polyline.set(evaluateCurve3(curve, floats, params[i]), i * 3);
  }
  return polyline;
}

// --- Component assembly ------------------------------------------------------

// Tessellate a full parsed SURF component. Returns merged buffers plus a
// per-vertex face ordinal channel (picking / selection tint) and per-class
// edge segment lists.
export function tessellateComponent(index, floats, options = {}) {
  // Component scale: bbox diagonal from a cheap pass over loop samples.
  let min = [Infinity, Infinity, Infinity];
  let max = [-Infinity, -Infinity, -Infinity];
  const faceMeshes = [];
  let vertexTotal = 0;
  let indexTotal = 0;

  // First pass without scale to estimate bounds from loop polygons only.
  for (const face of index.faces) {
    for (const loop of face.loops) {
      for (const pcurve of loop) {
        for (const t of [pcurve.range[0], (pcurve.range[0] + pcurve.range[1]) / 2, pcurve.range[1]]) {
          const [u, v] = evaluatePCurve(pcurve, floats, t);
          const p = evaluateSurface(face.surface, floats, u, v);
          for (let d = 0; d < 3; d += 1) {
            if (p[d] < min[d]) min[d] = p[d];
            if (p[d] > max[d]) max[d] = p[d];
          }
        }
      }
    }
  }
  const scale = Math.max(length3(sub(max, min)), 1e-6);

  // ONE polyline per model edge, sampled from its exact 3D curve. Every
  // adjacent face's boundary conforms to it (and the display overlay reuses
  // it), which is what makes the component watertight across faces.
  // Shared polylines are the authoritative boundary geometry for BOTH
  // adjacent faces and the display overlay, so they sample at the tighter
  // CHORD tolerance: a 1D curve costs little to refine, and every consumer
  // inherits the fidelity.
  const { chordTolerance } = { ...DEFAULT_OPTIONS, ...options };
  const sharedEdges = new Map();
  for (const edge of index.edges) {
    if (!edge.curve) continue;
    sharedEdges.set(edge.ord, sampleSharedEdge(edge.curve, floats, chordTolerance * scale));
  }
  // Weld model CORNERS: edge endpoints that coincide (within tolerance) are
  // the same vertex of the model, but each curve evaluates it with its own
  // float rounding. Snap every cluster to ONE canonical point object so a
  // corner is bit-identical no matter which edge a face pinned it through.
  {
    const weldTolerance = chordTolerance * scale;
    const corners = [];
    const canonicalCorner = (point) => {
      for (const corner of corners) {
        if (length3(sub(corner, point)) <= weldTolerance) return corner;
      }
      corners.push(point);
      return point;
    };
    for (const shared of sharedEdges.values()) {
      if (shared.closed) {
        // A closed edge's seam point can coincide with other edges' corners
        // (a cylinder seam meeting a vertical line); weld it too, keeping both
        // ends the SAME object.
        const welded = canonicalCorner(shared.points[0]);
        shared.points[0] = welded;
        shared.points[shared.points.length - 1] = welded;
        continue;
      }
      shared.points[0] = canonicalCorner(shared.points[0]);
      shared.points[shared.points.length - 1] = canonicalCorner(shared.points[shared.points.length - 1]);
    }
  }

  const rawFaces = [];
  for (const face of index.faces) {
    const raw = tessellateFaceRaw(
      face, floats, scale, options, options.noSharedBoundaries ? null : sharedEdges);
    if (raw) rawFaces.push({ face, raw });
  }
  if (!options.noSharedBoundaries && !options.noConformPass) {
    conformBoundaries(rawFaces, sharedEdges, floats, chordTolerance * scale);
    for (const { face, raw } of rawFaces) {
      refineInteriorPostConform(face, raw, floats, options);
    }
  }
  const boundaryDebug = options.collectBoundaryDebug ? [] : null;
  for (const { face, raw } of rawFaces) {
    if (boundaryDebug) {
      boundaryDebug.push({
        faceOrd: face.ord,
        reversed: !!face.reversed,
        xyz: raw.xyz,
        triangles: raw.triangles.slice(),
        boundaryByVert: new Map(raw.boundary),
      });
    }
    const mesh = finalizeFaceMesh(face, raw);
    if (!mesh) continue;
    faceMeshes.push({ ord: face.ord, color: face.color ?? null, mesh });
    vertexTotal += mesh.positions.length / 3;
    indexTotal += mesh.indices.length;
  }

  const positions = new Float32Array(vertexTotal * 3);
  const normals = new Float32Array(vertexTotal * 3);
  const faceOrds = new Float32Array(vertexTotal);
  const indices = new Uint32Array(indexTotal);
  const sideOrds = new Uint32Array(indexTotal);
  const faceRanges = [];
  let vertexOffset = 0;
  let indexOffset = 0;
  for (const { ord, color, mesh } of faceMeshes) {
    positions.set(mesh.positions, vertexOffset * 3);
    normals.set(mesh.normals, vertexOffset * 3);
    faceOrds.fill(ord, vertexOffset, vertexOffset + mesh.positions.length / 3);
    for (let i = 0; i < mesh.indices.length; i += 1) {
      indices[indexOffset + i] = mesh.indices[i] + vertexOffset;
    }
    if (mesh.sideOrds) sideOrds.set(mesh.sideOrds, indexOffset);
    faceRanges.push({ ord, color, indexStart: indexOffset, indexCount: mesh.indices.length });
    vertexOffset += mesh.positions.length / 3;
    indexOffset += mesh.indices.length;
  }

  // Bounds from the FINAL tessellated positions: the loop-sample estimate
  // above seeds tolerances but can clip extreme points, and camera auto-fit
  // is sensitive to the difference.
  min = [Infinity, Infinity, Infinity];
  max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3) {
    for (let d = 0; d < 3; d += 1) {
      const value = positions[i + d];
      if (value < min[d]) min[d] = value;
      if (value > max[d]) max[d] = value;
    }
  }

  const edges = [];
  for (const edge of index.edges) {
    const shared = sharedEdges.get(edge.ord);
    if (!shared) continue;
    const polyline = new Float32Array(shared.points.length * 3);
    for (let i = 0; i < shared.points.length; i += 1) polyline.set(shared.points[i], i * 3);
    edges.push({
      ord: edge.ord,
      visibilityClass: edge.class,
      polyline,
    });
  }

  return {
    positions,
    normals,
    faceOrds,
    indices,
    sideOrds,
    faceRanges,
    edges,
    bounds: { min, max },
    scale,
    ...(boundaryDebug ? { boundaryDebug, sharedEdges } : {}),
  };
}

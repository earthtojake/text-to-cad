import { applyTubeBraidMaterial } from "./tubeBraidMaterial.js";
import {
  GPU_TUBE_MAX_PATH_LENGTH,
  applyGpuTube,
  disableGpuTube,
  syncGpuTubeMaterials
} from "./tubeGpuDeformation.js";
import { TUBE_MATERIAL_ATTRIBUTE } from "./tubeMaterialShader.js";

// Analytic line/arc/Bézier paths and rest-mesh deformation. Coordinates are
// assembly/world millimetres before occurrence animation transforms. No CAD
// kernel or source model is read: the original STEP tessellation is the rest mesh.
const EPS = 1e-7;
const MAX_REFINED_TRIANGLES = 700000;
const COMPILED_PATH_CACHE_SIZE = 128;

const add = (a, b) => a.map((x, i) => x + b[i]);
const sub = (a, b) => a.map((x, i) => x - b[i]);
const mul = (a, s) => a.map((x) => x * s);
const dot = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0]
];
const length = (a) => Math.hypot(...a);
const distanceSq = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

function boundsDistanceSq(bounds, point) {
  let result = 0;
  for (let i = 0; i < 3; i++) {
    result += Math.max(bounds.min[i] - point[i], 0, point[i] - bounds.max[i]) ** 2;
  }
  return result;
}

function fail(message) {
  throw new Error(`animation deformTube: ${message}`);
}

function vector(value, name) {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(Number.isFinite)) {
    fail(`${name} must be a finite vec3`);
  }
  return value.slice();
}

function unit(v, name) {
  const size = length(v);
  if (size < EPS) {
    fail(`${name} must be nonzero`);
  }
  return mul(v, 1 / size);
}

function keys(value, allowed, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(`${name} must be an object`);
  }
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) {
      fail(`unknown ${name} key ${JSON.stringify(key)}; expected ${allowed.join(", ")}`);
    }
  }
}

function rotate(v, axis, angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return add(add(mul(v, c), mul(cross(axis, v), s)), mul(axis, dot(axis, v) * (1 - c)));
}

function bezierAt(points, t) {
  const q = 1 - t;
  return [0, 1, 2].map((i) =>
    q * q * q * points[0][i] + 3 * q * q * t * points[1][i] + 3 * q * t * t * points[2][i] + t * t * t * points[3][i]
  );
}

function bezierDerivative(points, t) {
  const q = 1 - t;
  return [0, 1, 2].map((i) =>
    3 * q * q * (points[1][i] - points[0][i]) + 6 * q * t * (points[2][i] - points[1][i]) + 3 * t * t * (points[3][i] - points[2][i])
  );
}

function bezierSecond(points, t) {
  return [0, 1, 2].map((i) =>
    6 * (1 - t) * (points[2][i] - 2 * points[1][i] + points[0][i]) + 6 * t * (points[3][i] - 2 * points[2][i] + points[1][i])
  );
}

// Five-point Gauss-Legendre on a short interval. The adaptive subdivision below
// checks the arc-length integral, rather than equating a chord with a curve.
const GAUSS_NODES = [0, 0.5384693101056831, -0.5384693101056831, 0.906179845938664, -0.906179845938664];
const GAUSS_WEIGHTS = [0.5688888888888889, 0.4786286704993665, 0.4786286704993665, 0.2369268850561891, 0.2369268850561891];

function bezierLength(points, lo, hi) {
  const mid = (lo + hi) / 2;
  const half = (hi - lo) / 2;
  let sum = 0;
  for (let i = 0; i < 5; i++) {
    const t = mid + half * GAUSS_NODES[i];
    const q = 1 - t;
    const a = 3 * q * q;
    const b = 6 * q * t;
    const c = 3 * t * t;
    const dx = a * (points[1][0] - points[0][0]) + b * (points[2][0] - points[1][0]) + c * (points[3][0] - points[2][0]);
    const dy = a * (points[1][1] - points[0][1]) + b * (points[2][1] - points[1][1]) + c * (points[3][1] - points[2][1]);
    const dz = a * (points[1][2] - points[0][2]) + b * (points[2][2] - points[1][2]) + c * (points[3][2] - points[2][2]);
    sum += GAUSS_WEIGHTS[i] * Math.hypot(dx, dy, dz);
  }
  return half * sum;
}

// Parallel transport of a transverse normal from one unit tangent to the next.
function transport(normal, from, to) {
  const axis = cross(from, to);
  const sine = length(axis);
  const cosine = dot(from, to);
  if (sine < EPS) {
    if (cosine < 0) {
      fail("path tangent reverses");
    }
    return normal.slice();
  }
  return rotate(normal, mul(axis, 1 / sine), Math.atan2(sine, cosine));
}

function buildBezierTable(segment) {
  const table = [{ t: 0, s: 0, tangent: segment.tangent, normal: segment.normal }];
  const append = (lo, hi, depth = 0) => {
    const mid = (lo + hi) / 2;
    const whole = bezierLength(segment.points, lo, hi);
    const left = bezierLength(segment.points, lo, mid);
    const right = bezierLength(segment.points, mid, hi);
    const a = unit(bezierDerivative(segment.points, lo), "Bezier tangent");
    const b = unit(bezierDerivative(segment.points, hi), "Bezier tangent");
    if (depth < 20 && (hi - lo > 1 / 128 || Math.abs(whole - left - right) > 1e-9 || dot(a, b) < 0.9999)) {
      append(lo, mid, depth + 1);
      append(mid, hi, depth + 1);
      return;
    }
    if (dot(a, b) < 0.99) {
      fail("Bezier has a cusp or unresolved tangent");
    }
    const previous = table.at(-1);
    table.push({
      t: hi,
      s: previous.s + left + right,
      tangent: b,
      normal: transport(previous.normal, previous.tangent, b)
    });
  };
  append(0, 1);
  segment.table = table;
  for (const entry of table) {
    entry.point = bezierAt(segment.points, entry.t);
  }
  segment.length = table.at(-1).s;
}

function bezierParameter(segment, distance) {
  const table = segment.table;
  let lo = 0;
  let hi = table.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (table[mid].s < distance) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  const lower = table[lo];
  const upper = table[hi];
  let t = lower.t + (upper.t - lower.t) * (distance - lower.s) / (upper.s - lower.s);
  for (let i = 0; i < 3; i++) {
    const error = lower.s + bezierLength(segment.points, lower.t, t) - distance;
    if (Math.abs(error) < 1e-11) {
      break;
    }
    t = Math.max(lower.t, Math.min(upper.t, t - error / length(bezierDerivative(segment.points, t))));
  }
  return { t, lower };
}

function segmentPoint(segment, distance) {
  if (segment.kind === "line") {
    return add(segment.start, mul(segment.tangent, distance));
  }
  if (segment.kind === "bezier") {
    return bezierAt(segment.points, bezierParameter(segment, distance).t);
  }
  return add(segment.center, rotate(segment.radial, segment.axis, distance / segment.radius * segment.sign));
}

function segmentFrame(segment, distance) {
  if (segment.kind === "bezier") {
    const { t, lower } = bezierParameter(segment, distance);
    const first = bezierDerivative(segment.points, t);
    const speed = length(first);
    const tangent = mul(first, 1 / speed);
    const normal = transport(lower.normal, lower.tangent, tangent);
    const second = bezierSecond(segment.points, t);
    const curvature = mul(sub(second, mul(tangent, dot(second, tangent))), 1 / (speed * speed));
    return { point: bezierAt(segment.points, t), tangent, normal, binormal: cross(tangent, normal), curvature };
  }
  const angle = segment.kind === "arc" ? distance / segment.radius * segment.sign : 0;
  const tangent = angle ? rotate(segment.tangent, segment.axis, angle) : segment.tangent;
  const normal = angle ? rotate(segment.normal, segment.axis, angle) : segment.normal;
  const point = segmentPoint(segment, distance);
  const curvature = segment.kind === "arc"
    ? mul(sub(segment.center, point), 1 / (segment.radius * segment.radius))
    : [0, 0, 0];
  return { point, tangent, normal, binormal: cross(tangent, normal), curvature };
}

const SEGMENT_KEYS = {
  line: ["kind", "start", "end"],
  arc: ["kind", "center", "axis", "start", "sweepDeg"],
  bezier: ["kind", "points"]
};

function compileSegment(spec, index) {
  keys(spec, SEGMENT_KEYS[spec.kind] || SEGMENT_KEYS.arc, `segment ${index}`);
  if (spec.kind === "line") {
    const start = vector(spec.start, "start");
    const end = vector(spec.end, "end");
    const delta = sub(end, start);
    return { kind: "line", start, end, tangent: unit(delta, "line"), length: length(delta), radius: Infinity };
  }
  if (spec.kind === "arc") {
    const center = vector(spec.center, "center");
    const start = vector(spec.start, "start");
    const axis = unit(vector(spec.axis, "axis"), "axis");
    const radial = sub(start, center);
    const radius = length(radial);
    const angle = spec.sweepDeg * Math.PI / 180;
    if (!Number.isFinite(angle) || Math.abs(angle) < EPS || Math.abs(angle) > 2 * Math.PI + EPS) {
      fail("arc sweepDeg must be nonzero and at most 360 degrees");
    }
    if (radius < EPS || Math.abs(dot(radial, axis)) > EPS * Math.max(1, radius)) {
      fail("arc start must be in its normal plane with nonzero radius");
    }
    const sign = Math.sign(angle);
    const tangent = mul(cross(axis, radial), sign / radius);
    const segment = { kind: "arc", center, start, axis, radial, radius, sign, tangent, length: radius * Math.abs(angle) };
    segment.end = segmentPoint(segment, segment.length);
    return segment;
  }
  if (spec.kind === "bezier") {
    if (!Array.isArray(spec.points) || spec.points.length !== 4) {
      fail("Bezier points must contain four vec3 control points");
    }
    const points = spec.points.map((p) => vector(p, "Bezier point"));
    return {
      kind: "bezier",
      points,
      start: points[0],
      end: points[3],
      tangent: unit(bezierDerivative(points, 0), "Bezier tangent"),
      radius: Infinity
    };
  }
  return fail(`unknown segment kind ${JSON.stringify(spec.kind)}; expected line, arc, bezier`);
}

// A sampled curvature bound is diagnostic only. Collision/curvature gates must
// evaluate the authored analytic centerline independently.
function sampledBezierRadius(segment) {
  return Math.min(...segment.table.map((entry) => {
    const d = bezierDerivative(segment.points, entry.t);
    const dd = bezierSecond(segment.points, entry.t);
    const speed = length(d);
    const tangent = mul(d, 1 / speed);
    entry.curvature = mul(sub(dd, mul(tangent, dot(dd, tangent))), 1 / (speed * speed));
    return Math.pow(speed, 3) / length(cross(d, dd));
  }));
}

// A Bézier lies inside its control hull. Circular bounds deliberately cover the
// entire circle: pruning must never discard the closest path segment.
function segmentBounds(segment) {
  if (segment.kind === "arc") {
    return {
      min: segment.center.map((v) => v - segment.radius),
      max: segment.center.map((v) => v + segment.radius)
    };
  }
  const points = segment.kind === "bezier" ? segment.points : [segment.start, segment.end];
  return {
    min: [0, 1, 2].map((i) => Math.min(...points.map((p) => p[i]))),
    max: [0, 1, 2].map((i) => Math.max(...points.map((p) => p[i])))
  };
}

/** Validate a tangent-continuous path and produce exact lengths/curvatures. */
export function compileTubePath(raw) {
  keys(raw, ["segments", "normal"], "path");
  if (!Array.isArray(raw.segments) || !raw.segments.length) {
    fail("path needs at least one segment");
  }
  // No default seed: a guessed transverse normal would flip as the first
  // tangent turns during an animation, twisting the tube by 90 degrees in one
  // frame. The author names the frame on both paths.
  if (raw.normal === undefined) {
    fail("path normal is required: give both the rest and the posed path an explicit transverse normal seed");
  }
  const seed = vector(raw.normal, "normal");
  let total = 0;
  let previous = null;
  const segments = raw.segments.map((spec, index) => {
    const segment = compileSegment(spec, index);
    if (previous) {
      if (length(sub(previous.end, segment.start)) > 1e-5) {
        fail(`path discontinuity before segment ${index}`);
      }
      const endFrame = segmentFrame(previous, previous.length);
      if (dot(endFrame.tangent, segment.tangent) < 1 - 1e-7) {
        fail(`path is not tangent-continuous before segment ${index}`);
      }
      segment.normal = endFrame.normal;
    } else {
      segment.normal = unit(
        sub(seed, mul(segment.tangent, dot(seed, segment.tangent))),
        "path normal transverse to first tangent"
      );
    }
    if (segment.kind === "bezier") {
      buildBezierTable(segment);
      segment.radius = sampledBezierRadius(segment);
    }
    segment.offset = total;
    segment.bounds = segmentBounds(segment);
    total += segment.length;
    previous = segment;
    return segment;
  });
  return { segments, length: total, minRadius: Math.min(...segments.map((s) => s.radius)) };
}

/** Exact frame at arc length; endpoint tangent extrapolation is deliberate. */
export function sampleTubePath(path, distance) {
  if (!Number.isFinite(distance)) {
    fail("path distance must be finite");
  }
  const segment = distance <= 0
    ? path.segments[0]
    : path.segments.find((s) => distance <= s.offset + s.length) || path.segments.at(-1);
  const local = distance - segment.offset;
  const clamped = Math.max(0, Math.min(segment.length, local));
  const frame = segmentFrame(segment, clamped);
  if (local !== clamped) {
    frame.point = add(frame.point, mul(frame.tangent, local - clamped));
  }
  return frame;
}

function closestBezierDistance(segment, point) {
  let bestIndex = 0;
  let bestD = Infinity;
  for (let i = 0; i < segment.table.length; i++) {
    const d = distanceSq(point, segment.table[i].point);
    if (d < bestD) {
      bestD = d;
      bestIndex = i;
    }
  }
  let lo = segment.table[Math.max(0, bestIndex - 1)].t;
  let hi = segment.table[Math.min(segment.table.length - 1, bestIndex + 1)].t;
  for (let i = 0; i < 35; i++) {
    const a = lo + (hi - lo) / 3;
    const b = hi - (hi - lo) / 3;
    if (distanceSq(point, bezierAt(segment.points, a)) < distanceSq(point, bezierAt(segment.points, b))) {
      hi = b;
    } else {
      lo = a;
    }
  }
  const bestT = (lo + hi) / 2;
  const lower = segment.table.findLast((entry) => entry.t <= bestT) || segment.table[0];
  return lower.s + bezierLength(segment.points, lower.t, bestT);
}

function closestArcDistance(segment, point) {
  const delta = sub(point, segment.center);
  let angle = Math.atan2(dot(cross(segment.radial, delta), segment.axis), dot(segment.radial, delta)) * segment.sign;
  if (angle < 0) {
    angle += 2 * Math.PI;
  }
  const local = angle * segment.radius;
  if (local > segment.length) {
    // Outside the sweep the nearest arc point is an endpoint; distance to a
    // circle is monotone in angular offset, so Euclidean comparison decides.
    return length(sub(point, segment.start)) < length(sub(point, segment.end)) ? 0 : segment.length;
  }
  return local;
}

/** Closest exact analytic centerline point, used once per immutable rest mesh. */
export function projectTubePath(path, point) {
  let best = null;
  const candidates = path.segments
    .map((segment) => ({ segment, bound: boundsDistanceSq(segment.bounds, point) }))
    .sort((a, b) => a.bound - b.bound);
  for (const { segment, bound } of candidates) {
    if (best && bound > best.distanceSq + 1e-12) {
      break;
    }
    let local;
    if (segment.kind === "line") {
      local = dot(sub(point, segment.start), segment.tangent);
    } else if (segment.kind === "bezier") {
      local = closestBezierDistance(segment, point);
    } else {
      local = closestArcDistance(segment, point);
    }
    local = Math.max(0, Math.min(segment.length, local));
    const frame = segmentFrame(segment, local);
    const delta = sub(point, frame.point);
    const d2 = dot(delta, delta);
    if (!best || d2 < best.distanceSq) {
      best = {
        distance: segment.offset + local,
        distanceSq: d2,
        transverse: [dot(delta, frame.normal), dot(delta, frame.binormal)],
        axial: dot(delta, frame.tangent)
      };
    }
  }
  return best;
}

// Values, not object identity: animation authors may mutate/reuse control arrays.
// A bounded LRU retains the rest paths and the current posed packet.
const compiledPaths = new Map();

function cachedCompile(raw) {
  const key = JSON.stringify(raw);
  let path = compiledPaths.get(key);
  if (path) {
    compiledPaths.delete(key);
  } else {
    path = compileTubePath(raw);
    Object.defineProperty(path, "sourceKey", { value: key });
  }
  compiledPaths.set(key, path);
  if (compiledPaths.size > COMPILED_PATH_CACHE_SIZE) {
    compiledPaths.delete(compiledPaths.keys().next().value);
  }
  return path;
}

export function normalizeTubeDeformation(spec) {
  keys(spec, ["rest", "path", "twistDeg", "maxSegmentLength", "braid"], "deformation");
  const twistDeg = spec.twistDeg ?? 0;
  if (!Number.isFinite(twistDeg)) {
    fail("twistDeg must be finite");
  }
  const maxSegmentLength = spec.maxSegmentLength ?? 1;
  if (!Number.isFinite(maxSegmentLength) || maxSegmentLength < 0.05) {
    fail("maxSegmentLength must be at least 0.05 mm");
  }
  let braid = null;
  if (spec.braid) {
    keys(spec.braid, ["pitch", "depth", "strands"], "braid");
    const { pitch, depth, strands } = spec.braid;
    const valid = Number.isFinite(pitch) && pitch > 0
      && Number.isFinite(depth) && depth >= 0
      && Number.isInteger(strands) && strands >= 2 && strands <= 64 && strands % 2 === 0;
    if (!valid) {
      fail("braid needs positive pitch, nonnegative depth, and an even strand count from 2 to 64");
    }
    braid = { pitch, depth, strands };
  }
  const rest = cachedCompile(spec.rest);
  const path = cachedCompile(spec.path);
  return {
    rest,
    path,
    twistDeg,
    maxSegmentLength,
    braid,
    key: JSON.stringify([rest.sourceKey, path.sourceKey, twistDeg, maxSegmentLength, braid])
  };
}

const restMappingKey = (deformation) =>
  JSON.stringify([deformation.rest.sourceKey ?? deformation.rest, deformation.maxSegmentLength]);

// Clip a triangle (as [distance, w0, w1, w2] barycentric rows) against one
// rest-arc-length band boundary, dropping repeated corners.
function clipPolygon(polygon, cut, above) {
  const result = [];
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i];
    const b = polygon[(i + 1) % polygon.length];
    const inA = above ? a[0] >= cut : a[0] <= cut;
    const inB = above ? b[0] >= cut : b[0] <= cut;
    if (inA) {
      result.push(a);
    }
    if (inA !== inB) {
      const t = (cut - a[0]) / (b[0] - a[0]);
      result.push(a.map((v, j) => v + t * (b[j] - v)));
    }
  }
  return result.filter((v, i) =>
    !i || Math.abs(v[1] - result[i - 1][1]) + Math.abs(v[2] - result[i - 1][2]) + Math.abs(v[3] - result[i - 1][3]) > 1e-10
  );
}

// STEP tessellation need not have intermediate rings on a straight cylinder.
// Split its existing triangles at rest-arc-length bands once, interpolating all
// attributes. This changes tessellation only, never the original rest surface.
function refineRestMesh(THREE, source, rest, base, step) {
  if (step >= rest.length) {
    return { geometry: source, sourceTriangles: null };
  }
  const position = source.attributes.position;
  const vertex = new THREE.Vector3();
  const distances = new Float64Array(position.count);
  const projectedPositions = new Map();
  for (let i = 0; i < position.count; i++) {
    const key = [position.getX(i), position.getY(i), position.getZ(i)].join(",");
    let distance = projectedPositions.get(key);
    if (distance === undefined) {
      vertex.fromBufferAttribute(position, i).applyMatrix4(base);
      distance = projectTubePath(rest, vertex.toArray()).distance;
      projectedPositions.set(key, distance);
    }
    distances[i] = distance;
  }
  projectedPositions.clear();
  const count = source.index?.count ?? position.count;
  if (count % 3) {
    // Not a triangle surface (proxy data): nothing to split.
    return { geometry: source.clone(), sourceTriangles: null };
  }
  const attributes = Object.entries(source.attributes);
  const values = Object.fromEntries(attributes.map(([name]) => [name, []]));
  const sourceTriangles = [];
  const indices = [];
  const vertices = new Map();
  const index = (i) => (source.index ? source.index.getX(i) : i);
  for (let ti = 0; ti < count; ti += 3) {
    const ids = [index(ti), index(ti + 1), index(ti + 2)];
    const ds = ids.map((id) => distances[id]);
    const initial = ds.map((d, i) => [d, ...[0, 1, 2].map((j) => (i === j ? 1 : 0))]);
    const first = Math.floor(Math.min(...ds) / step);
    const last = Math.floor(Math.max(...ds) / step);
    for (let band = first; band <= last; band++) {
      const polygon = clipPolygon(clipPolygon(initial, band * step, true), (band + 1) * step, false);
      for (let j = 1; j < polygon.length - 1; j++) {
        const corners = [polygon[0], polygon[j], polygon[j + 1]];
        // Zero-area slivers at an exact band boundary are not surface triangles.
        const u = sub(corners[1].slice(1), corners[0].slice(1));
        const v = sub(corners[2].slice(1), corners[0].slice(1));
        if (length(cross(u, v)) < 1e-12) {
          continue;
        }
        sourceTriangles.push(ti / 3);
        if (sourceTriangles.length > MAX_REFINED_TRIANGLES) {
          fail(`refined tube exceeds ${MAX_REFINED_TRIANGLES} triangles; increase maxSegmentLength`);
        }
        for (const corner of corners) {
          const key = ids
            .map((id, k) => [id, Math.round(corner[k + 1] * 1e10)])
            .filter(([, weight]) => weight)
            .sort((a, b) => a[0] - b[0])
            .map((pair) => pair.join(":"))
            .join(",");
          let vertexIndex = vertices.get(key);
          if (vertexIndex === undefined) {
            vertexIndex = vertices.size;
            vertices.set(key, vertexIndex);
            for (const [name, attribute] of attributes) {
              for (let component = 0; component < attribute.itemSize; component++) {
                values[name].push(ids.reduce((sum, id, k) => sum + corner[k + 1] * attribute.getComponent(id, component), 0));
              }
            }
          }
          indices.push(vertexIndex);
        }
      }
    }
  }
  const geometry = source.clone();
  for (const [name, attribute] of attributes) {
    geometry.setAttribute(name, new THREE.Float32BufferAttribute(values[name], attribute.itemSize));
  }
  geometry.setIndex(indices);
  geometry.clearGroups();
  return { geometry, sourceTriangles: new Uint32Array(sourceTriangles) };
}

// One eight-float record per unique (position, normal) pair:
//   [arc-length fraction, transverse u, transverse v, axial,
//    normal·N, normal·B, normal·T, rest metric]
// GPU mappings are Float32 padded to a texture row; exact Float64 records are
// built only for CPU materialization. `indices` maps each vertex to its record.
function mappingFor(THREE, attribute, normals, rest, baseMatrix, gpu = false) {
  const values = [];
  const indices = gpu ? new Float32Array(attribute.count) : new Uint32Array(attribute.count);
  const unique = new Map();
  const point = new THREE.Vector3();
  const normalMatrix = new THREE.Matrix3().getNormalMatrix(baseMatrix);
  const normal = new THREE.Vector3();
  for (let i = 0; i < attribute.count; i++) {
    const key = [
      attribute.getX(i), attribute.getY(i), attribute.getZ(i),
      ...(normals ? [normals.getX(i), normals.getY(i), normals.getZ(i)] : [])
    ].join(",");
    const existing = unique.get(key);
    if (existing !== undefined) {
      indices[i] = existing;
      continue;
    }
    const slot = values.length / 8;
    unique.set(key, slot);
    indices[i] = slot;
    point.fromBufferAttribute(attribute, i).applyMatrix4(baseMatrix);
    const projected = projectTubePath(rest, [point.x, point.y, point.z]);
    const frame = sampleTubePath(rest, projected.distance);
    const offset = add(mul(frame.normal, projected.transverse[0]), mul(frame.binormal, projected.transverse[1]));
    const metric = 1 - dot(frame.curvature, offset);
    if (metric <= EPS) {
      fail("rest mesh crosses the centerline curvature radius");
    }
    let components = [0, 0, 0];
    if (normals) {
      normal.fromBufferAttribute(normals, i).applyNormalMatrix(normalMatrix);
      const n = [normal.x, normal.y, normal.z];
      components = [dot(n, frame.normal), dot(n, frame.binormal), dot(n, frame.tangent)];
    }
    values.push(projected.distance / rest.length, ...projected.transverse, projected.axial, ...components, metric);
  }
  const packed = gpu ? new Float32Array(Math.ceil(values.length / 4096) * 4096) : new Float64Array(values.length);
  packed.set(values);
  return { values: packed, indices, gpu };
}

// Re-emit every vertex on the posed path. Normals take the deformation's
// inverse-transpose: transverse components ride the frame, the tangential
// component scales by rest metric / (posed metric * stretch).
function updateAttribute(THREE, attribute, normals, mapping, deformation, inverse) {
  const { path, rest } = deformation;
  const point = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const normalMatrix = new THREE.Matrix3().getNormalMatrix(inverse);
  const twist = deformation.twistDeg * Math.PI / 180;
  const c = Math.cos(twist);
  const s = Math.sin(twist);
  const stretch = path.length / rest.length;
  const frames = new Map();
  const values = mapping.values;
  const evaluated = new Map();
  for (let i = 0; i < attribute.count; i++) {
    const slot = mapping.indices[i];
    const prior = evaluated.get(slot);
    if (prior !== undefined) {
      attribute.setXYZ(i, attribute.getX(prior), attribute.getY(prior), attribute.getZ(prior));
      if (normals) {
        normals.setXYZ(i, normals.getX(prior), normals.getY(prior), normals.getZ(prior));
      }
      continue;
    }
    evaluated.set(slot, i);
    const j = slot * 8;
    const fraction = values[j];
    let frame = frames.get(fraction);
    if (!frame) {
      frame = sampleTubePath(path, fraction * path.length);
      frames.set(fraction, frame);
    }
    const u = c * values[j + 1] - s * values[j + 2];
    const v = s * values[j + 1] + c * values[j + 2];
    const ox = frame.normal[0] * u + frame.binormal[0] * v;
    const oy = frame.normal[1] * u + frame.binormal[1] * v;
    const oz = frame.normal[2] * u + frame.binormal[2] * v;
    const metric = 1 - (frame.curvature[0] * ox + frame.curvature[1] * oy + frame.curvature[2] * oz);
    if (metric <= EPS) {
      fail("posed mesh crosses the centerline curvature radius");
    }
    point.set(
      frame.point[0] + ox + values[j + 3] * frame.tangent[0],
      frame.point[1] + oy + values[j + 3] * frame.tangent[1],
      frame.point[2] + oz + values[j + 3] * frame.tangent[2]
    ).applyMatrix4(inverse);
    attribute.setXYZ(i, point.x, point.y, point.z);
    if (normals) {
      const nu = c * values[j + 4] - s * values[j + 5];
      const nv = s * values[j + 4] + c * values[j + 5];
      const nt = values[j + 6] * values[j + 7] / (metric * stretch);
      normal.set(
        nu * frame.normal[0] + nv * frame.binormal[0] + nt * frame.tangent[0],
        nu * frame.normal[1] + nv * frame.binormal[1] + nt * frame.tangent[1],
        nu * frame.normal[2] + nv * frame.binormal[2] + nt * frame.tangent[2]
      ).applyNormalMatrix(normalMatrix);
      normals.setXYZ(i, normal.x, normal.y, normal.z);
    }
  }
  attribute.needsUpdate = true;
  if (normals) {
    normals.needsUpdate = true;
  }
}

function refineLineGeometry(THREE, object, source, rest, base, step) {
  const geometry = source.clone();
  const starts = source.attributes.instanceStart;
  const ends = source.attributes.instanceEnd;
  const sourcePosition = source.attributes.position;
  if (!starts && !sourcePosition) {
    return geometry;
  }
  // Ordinary lines may be indexed (CAD edge lines share polyline points); the
  // refined copy is emitted flat, every other attribute (the per-point class
  // colour) replicated onto the emitted points.
  const index = starts ? null : source.index;
  const count = starts
    ? starts.count
    : index ? index.count / 2 : object.isLineSegments ? sourcePosition.count / 2 : sourcePosition.count - 1;
  const vertexOf = (i, end) => index ? index.getX(i * 2 + end) : object.isLineSegments ? i * 2 + end : i + end;
  const extras = starts ? [] : Object.entries(source.attributes).filter(([name]) => name !== "position");
  const extraValues = Object.fromEntries(extras.map(([name]) => [name, []]));
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const world = new THREE.Vector3();
  const positions = [];
  for (let i = 0; i < count; i++) {
    const va = starts ? i : vertexOf(i, 0);
    const vb = ends ? i : vertexOf(i, 1);
    a.fromBufferAttribute(starts || sourcePosition, va);
    b.fromBufferAttribute(ends || sourcePosition, vb);
    const sa = projectTubePath(rest, world.copy(a).applyMatrix4(base).toArray()).distance;
    const sb = projectTubePath(rest, world.copy(b).applyMatrix4(base).toArray()).distance;
    const divisions = Math.max(1, Math.ceil(Math.abs(sb - sa) / step));
    for (let j = 0; j < divisions; j++) {
      for (const t of [j / divisions, (j + 1) / divisions]) {
        positions.push(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t);
        for (const [name, attribute] of extras) {
          const vertex = t < 1 ? va : vb;
          for (let component = 0; component < attribute.itemSize; component++) {
            extraValues[name].push(attribute.array[vertex * attribute.itemSize + component]);
          }
        }
      }
    }
  }
  if (starts) {
    geometry.setPositions(positions);
  } else {
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    for (const [name, attribute] of extras) {
      geometry.setAttribute(name, new THREE.BufferAttribute(
        new attribute.array.constructor(extraValues[name]), attribute.itemSize, attribute.normalized
      ));
    }
    geometry.setIndex(null);
  }
  return geometry;
}

// The wireframe/topology view must follow the same centerline as the surface.
// Line2 uses interleaved instanceStart/instanceEnd, ordinary THREE lines use
// position. Their originals are retained just like the surface mesh's buffers.
export function applyTubeDeformationToLineObject(THREE, object, deformation, base = new THREE.Matrix4()) {
  if (!object) {
    return;
  }
  for (const child of object.children || []) {
    applyTubeDeformationToLineObject(THREE, child, deformation, base);
  }
  if (!object.geometry) {
    return;
  }
  let state = object.tubeLineDeformationState;
  if (!deformation && !state?.active) {
    return;
  }
  if (deformation?.key && state?.active && state.lastKey === deformation.key) {
    return;
  }
  const restKey = deformation ? restMappingKey(deformation) : state?.restKey;
  if (!state || (deformation && restKey !== state.restKey)) {
    const original = state?.original || object.geometry;
    const source = refineLineGeometry(THREE, object, original, deformation.rest, base, deformation.maxSegmentLength);
    const geometry = source.clone();
    state?.geometry.dispose();
    geometry.userData = { ...geometry.userData, cadSceneCachedGeometry: false };
    const names = source.attributes.instanceStart ? ["instanceStart", "instanceEnd"] : ["position"];
    state = object.tubeLineDeformationState = { original, source, geometry, names, mappings: {}, restKey: null, active: false };
    object.geometry = geometry;
  }
  if (!deformation) {
    for (const name of state.names) {
      const target = state.geometry.attributes[name];
      const source = state.source.attributes[name];
      for (let i = 0; i < source.count; i++) {
        target.setXYZ(i, source.getX(i), source.getY(i), source.getZ(i));
      }
      target.needsUpdate = true;
    }
    state.geometry.computeBoundingBox();
    state.geometry.computeBoundingSphere();
    state.active = false;
    return;
  }
  const inverse = base.clone().invert();
  for (const name of state.names) {
    if (restKey !== state.restKey) {
      state.mappings[name] = mappingFor(THREE, state.source.attributes[name], null, deformation.rest, base);
    }
    updateAttribute(THREE, state.geometry.attributes[name], null, state.mappings[name], deformation, inverse);
  }
  state.restKey = restKey;
  state.active = true;
  state.lastKey = deformation.key;
  state.geometry.computeBoundingBox();
  state.geometry.computeBoundingSphere();
}

// Build the per-record display geometry over the (possibly refined) rest
// surface. Only positions and normals ever change: indices and display
// attributes stay shared with the retained rest surface.
function createDeformationState(THREE, record, previous, deformation, base) {
  const source = previous?.original || record.mesh.geometry;
  const originalFaceIds = previous?.originalFaceIds || record.mesh.userData?.faceIds;
  const refined = refineRestMesh(THREE, source, deformation.rest, base, deformation.maxSegmentLength);
  const restSource = refined.geometry;
  const geometry = new THREE.BufferGeometry();
  geometry.setIndex(restSource.index);
  for (const [name, attribute] of Object.entries(restSource.attributes)) {
    const writable = !record.gpuTubeDeformationAllowed && (name === "position" || name === "normal");
    geometry.setAttribute(name, writable ? attribute.clone() : attribute);
  }
  geometry.userData = { ...geometry.userData, cadSceneCachedGeometry: false, __bvhSkipped: true };
  geometry.boundsTree = null;
  previous?.geometry.dispose();
  const state = {
    original: source,
    originalFaceIds,
    source: restSource,
    geometry,
    active: false,
    restKey: restMappingKey(deformation),
    mapping: null,
    partBounds: previous?.partBounds || record.partBounds
  };
  record.mesh.geometry = geometry;
  if (originalFaceIds && refined.sourceTriangles) {
    record.mesh.userData.faceIds = new Uint32Array(refined.sourceTriangles.map((index) => originalFaceIds[index]));
  }
  record.geometry = geometry;
  if (record.silhouette) {
    record.silhouette.geometry = geometry;
  }
  if (record.ghostMesh) {
    record.ghostMesh.geometry = geometry;
  }
  return state;
}

function restoreRestSurface(record, state) {
  state.geometry.attributes.position.copy(state.source.attributes.position);
  state.geometry.attributes.position.needsUpdate = true;
  if (state.source.attributes.normal) {
    state.geometry.attributes.normal.copy(state.source.attributes.normal);
    state.geometry.attributes.normal.needsUpdate = true;
  }
  state.geometry.computeBoundingBox();
  state.geometry.computeBoundingSphere();
  record.partBounds = state.partBounds;
  state.active = false;
}

// Keep the source immutable. Display occurrences often share one component's
// buffers; a clone is owned by this record and disposed with its visible mesh.
export function applyRecordTubeDeformation(THREE, record, deformation) {
  if (!record?.mesh?.geometry) {
    return;
  }
  record.effectDeformation = deformation || null;
  applyTubeBraidMaterial(THREE, record.material || record.mesh.material, deformation?.braid || null);
  const base = new THREE.Matrix4();
  if (record.baseTransform) {
    base.fromArray(record.baseTransform).transpose();
  }
  if (!deformation || record.edges?.visible !== false) {
    applyTubeDeformationToLineObject(THREE, record.edges, deformation, base);
  }
  let state = record.tubeDeformationState;
  if (deformation?.key && state?.active && state.lastKey === deformation.key) {
    syncGpuTubeMaterials(record);
    return;
  }
  if (!deformation && !state?.active) {
    return;
  }
  if (!deformation) {
    disableGpuTube(record);
  }
  if (!state || (deformation && restMappingKey(deformation) !== state.restKey)) {
    state = record.tubeDeformationState = createDeformationState(THREE, record, state, deformation, base);
  }
  if (!deformation) {
    restoreRestSurface(record, state);
    return;
  }
  const inverse = base.clone().invert();
  const gpu = record.gpuTubeDeformationAllowed && deformation.path.length <= GPU_TUBE_MAX_PATH_LENGTH;
  if (!state.mapping) {
    state.mapping = mappingFor(THREE, state.source.attributes.position, state.source.attributes.normal, deformation.rest, base, gpu);
    if (!state.mapping.gpu) {
      // The CPU path stores braid material coordinates per vertex; the GPU
      // path derives them from its mapping texture instead.
      const coords = new Float32Array(state.geometry.attributes.position.count * 3);
      for (let i = 0; i < coords.length / 3; i++) {
        const j = state.mapping.indices[i] * 8;
        const v = state.mapping.values;
        coords.set([v[j] * deformation.rest.length, v[j + 1], v[j + 2]], i * 3);
      }
      state.geometry.setAttribute(TUBE_MATERIAL_ATTRIBUTE, new THREE.BufferAttribute(coords, 3));
    }
  }
  const materialize = () => {
    for (const name of ["position", "normal"]) {
      if (state.geometry.attributes[name] === state.source.attributes[name]) {
        state.geometry.setAttribute(name, state.source.attributes[name].clone());
      }
    }
    // The exact mapping depends only on the rest path, which this state is
    // keyed by; a hover during animation must not re-project every vertex per pose.
    state.exactMapping ??= state.mapping.gpu
      ? mappingFor(THREE, state.source.attributes.position, state.source.attributes.normal, deformation.rest, base)
      : state.mapping;
    updateAttribute(THREE, state.geometry.attributes.position, state.geometry.attributes.normal, state.exactMapping, deformation, inverse);
    state.geometry.computeBoundingBox();
    state.geometry.computeBoundingSphere();
  };
  if (applyGpuTube(THREE, record, state, deformation, inverse, sampleTubePath, materialize)) {
    state.active = true;
    state.lastKey = deformation.key;
    return;
  }
  disableGpuTube(record);
  materialize();
  const bounds = state.geometry.boundingBox.clone().applyMatrix4(base);
  record.partBounds = { min: bounds.min.toArray(), max: bounds.max.toArray() };
  state.active = true;
  state.lastKey = deformation.key;
}

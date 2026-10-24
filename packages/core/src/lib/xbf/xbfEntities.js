// What one face, edge or vertex of an engine document IS, for the tools that take an element
// whole -- Measure (`../viewer/measureEntities.js` reads what a pair of them makes) and Look at
// (`@text-to-cad/ui`'s `kit/camera/lookAt.js` turns the view square to one) -- read from the part
// buffer alone (`xbm.js`), as a STEP's were read from its topology rows:
//
// - a face's surface, from its nodes and the normals the engine meshed it with (the surface's own
//   normal at each node, so what is read is the surface, not its triangles): a plane (one normal,
//   every node on it), a cylinder (every normal square to one axis and through it, one radius), a
//   sphere (every normal through one centre, one radius), else a surface no reading takes (a cone,
//   a torus, a B-spline), of which only the point picked is known;
// - an edge's polyline, the mesher's, through the B-rep's own vertices;
// - a vertex's place, the vertex table's.
//
// Each in the part's own frame; `placeXbfPoint` and `placeXbfDirection` take it to where an
// instance's matrix (column-major, the structure's and three's) puts it. Plain arrays, no three.js.

import { xbmEdgeRow, xbmFaceRow, xbmVertexRow } from "./xbm.js";

const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const length = a => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => {
  const size = length(a);
  return size > 1e-12 ? scale(a, 1 / size) : null;
};

// How far a normal may turn and still be the plane's one normal, as 1 - cos (about 0.08°).
const PLANE_NORMAL = 1e-6;
// How far a cylinder's normal may lean off square to its axis, and any round face's off radial (sin).
const SQUARE = 1e-4;
const RADIAL = 1e-3;
// How far a round face's radii may spread, of its radius.
const ROUND = 1e-3;

/** The 3x3 system `m x = b` (row-major `m`), or null when it is all but singular. */
function solve3(m, b) {
  const [a, bb, c, d, e, f, g, h, i] = m;
  const det = a * (e * i - f * h) - bb * (d * i - f * g) + c * (d * h - e * g);
  const size = Math.max(...m.map(Math.abs));
  if (!(Math.abs(det) > size * size * size * 1e-9)) return null;
  const inverse = [e * i - f * h, c * h - bb * i, bb * f - c * e, f * g - d * i, a * i - c * g, c * d - a * f, d * h - e * g, bb * g - a * h, a * e - bb * d];
  return [0, 1, 2].map(row => (inverse[row * 3] * b[0] + inverse[row * 3 + 1] * b[1] + inverse[row * 3 + 2] * b[2]) / det);
}

/**
 * The point the lines `points[k] + t * directions[k]` all come nearest (least squares), held to the
 * plane square to `keep` through the origin when it is given (a cylinder's axis, along which every
 * point of it is as near), or null where they are all but parallel.
 */
function meetingPoint(points, directions, keep = null) {
  const m = [0, 0, 0, 0, 0, 0, 0, 0, 0];
  const b = [0, 0, 0];
  points.forEach((point, index) => {
    const d = directions[index];
    for (let row = 0; row < 3; row += 1) {
      for (let column = 0; column < 3; column += 1) {
        const projector = (row === column ? 1 : 0) - d[row] * d[column];
        m[row * 3 + column] += projector;
        b[row] += projector * point[column];
      }
    }
  });
  if (keep) for (let row = 0; row < 3; row += 1) for (let column = 0; column < 3; column += 1) m[row * 3 + column] += keep[row] * keep[column];
  return solve3(m, b);
}

/** A face's nodes and their normals, each node once (`[[x, y, z], ...]`), or null for no such face. */
export function xbfFaceNodes(mesh, ordinal) {
  const row = xbmFaceRow(mesh, ordinal);
  if (row < 0) return null;
  const first = mesh.faces[row * 3 + 1], count = mesh.faces[row * 3 + 2];
  const seen = new Set();
  const points = [], normals = [];
  for (let at = first; at < first + count; at += 1) {
    const node = mesh.indices[at];
    if (seen.has(node)) continue;
    seen.add(node);
    points.push([mesh.positions[node * 3], mesh.positions[node * 3 + 1], mesh.positions[node * 3 + 2]]);
    normals.push([mesh.normals[node * 3], mesh.normals[node * 3 + 1], mesh.normals[node * 3 + 2]]);
  }
  return { points, normals };
}

/**
 * What a face's surface is, read off its nodes and their normals (the surface's own, the engine's):
 * `{ type: "plane", normal, origin }` (the normal as the face's own, the origin the middle of its
 * nodes), `{ type: "cylinder", axis, origin, radius }` (the origin on the axis, level with the
 * middle of the face), `{ type: "sphere", center, radius }`, or `{ type: "surface" }`. Null for a
 * face that is not in the part or has no triangles. In the part's frame.
 */
export function xbfFaceSurface(mesh, ordinal) {
  const nodes = xbfFaceNodes(mesh, ordinal);
  if (!nodes || nodes.points.length < 3) return null;
  const { points } = nodes;
  const normals = nodes.normals.map(normal => unit(normal) || [0, 0, 0]);
  const count = points.length;
  const middle = scale(points.reduce((sum, point) => add(sum, point), [0, 0, 0]), 1 / count);
  // How far apart its nodes are, and how far a float32 coordinate this far out may be off.
  const span = Math.max(...points.map(point => length(sub(point, middle))));
  const far = Math.max(...points.map(point => Math.max(Math.abs(point[0]), Math.abs(point[1]), Math.abs(point[2]))));
  const off = Math.max(span * 1e-4, far * 4e-6, 1e-7);

  const first = normals[0];
  if (normals.every(normal => dot(normal, first) >= 1 - PLANE_NORMAL) && points.every(point => Math.abs(dot(sub(point, middle), first)) <= off)) {
    return { type: "plane", normal: first, origin: middle };
  }

  // A cylinder: its normals square to one axis, which the two most apart of them are both square to.
  const across = normals.reduce((best, normal) => (Math.abs(dot(normal, first)) < Math.abs(dot(best, first)) ? normal : best), first);
  const axis = unit(cross(first, across));
  if (axis && length(cross(first, across)) > 1e-3 && normals.every(normal => Math.abs(dot(normal, axis)) <= SQUARE)) {
    const flat = point => sub(point, scale(axis, dot(point, axis)));
    const center = meetingPoint(points.map(flat), normals.map(normal => unit(flat(normal)) || normal), axis);
    const round = center && roundAbout(points.map(flat), normals.map(normal => unit(flat(normal)) || normal), center, off);
    if (round) return { type: "cylinder", axis, origin: add(center, scale(axis, dot(middle, axis))), radius: round };
  }

  // A sphere: every normal through one centre.
  const center = meetingPoint(points, normals);
  const round = center && roundAbout(points, normals, center, off);
  if (round) return { type: "sphere", center, radius: round };
  return { type: "surface" };
}

/** The one radius of `points` about `center` along their normals, or null where they are not round about it. */
function roundAbout(points, normals, center, off) {
  const radii = points.map(point => length(sub(point, center)));
  const radius = radii.reduce((sum, value) => sum + value, 0) / radii.length;
  if (!(radius > off)) return null;
  if (radii.some(value => Math.abs(value - radius) > Math.max(radius * ROUND, off))) return null;
  // Each normal along its radius, outward or in (a boss or a hole).
  const radial = points.every((point, index) => length(cross(scale(sub(point, center), 1 / radii[index]), normals[index])) <= RADIAL);
  return radial ? radius : null;
}

/** An edge's polyline (`[[x, y, z], ...]`, at least two points), or null for no such edge. */
export function xbfEdgePolyline(mesh, ordinal) {
  const row = xbmEdgeRow(mesh, ordinal);
  if (row < 0) return null;
  const first = mesh.edges[row * 4 + 1], count = mesh.edges[row * 4 + 2];
  if (count < 2) return null;
  const points = [];
  for (let at = first; at < first + count; at += 1) points.push([mesh.edgePoints[at * 3], mesh.edgePoints[at * 3 + 1], mesh.edgePoints[at * 3 + 2]]);
  return points;
}

/** A vertex's place (`[x, y, z]`), or null for no such vertex. */
export function xbfVertexPoint(mesh, ordinal) {
  const row = xbmVertexRow(mesh, ordinal);
  return row < 0 ? null : [mesh.vertices[row * 4 + 1], mesh.vertices[row * 4 + 2], mesh.vertices[row * 4 + 3]];
}

/** A polyline as independent segments, flat (`[x1, y1, z1, x2, y2, z2, ...]`): what Measure's edge maths reads. */
export function xbfSegments(points) {
  const out = [];
  for (let index = 0; index + 1 < points.length; index += 1) out.push(...points[index], ...points[index + 1]);
  return out;
}

/** A point where the 4x4 `matrix` (column-major) puts it. */
export function placeXbfPoint(matrix, p) {
  const m = matrix;
  return [0, 1, 2].map(row => m[row] * p[0] + m[4 + row] * p[1] + m[8 + row] * p[2] + m[12 + row]);
}

/** A direction as the 4x4 `matrix` (column-major, rigid) turns it, unit length. */
export function placeXbfDirection(matrix, d) {
  const m = matrix;
  return unit([0, 1, 2].map(row => m[row] * d[0] + m[4 + row] * d[1] + m[8 + row] * d[2])) || d.slice();
}

/** A face's surface (`xbfFaceSurface`) where the 4x4 `matrix` (column-major, rigid) puts it. */
export function placeXbfSurface(matrix, surface) {
  if (!surface) return null;
  if (surface.type === "plane") return { type: "plane", normal: placeXbfDirection(matrix, surface.normal), origin: placeXbfPoint(matrix, surface.origin) };
  if (surface.type === "cylinder") {
    return { type: "cylinder", axis: placeXbfDirection(matrix, surface.axis), origin: placeXbfPoint(matrix, surface.origin), radius: surface.radius };
  }
  if (surface.type === "sphere") return { type: "sphere", center: placeXbfPoint(matrix, surface.center), radius: surface.radius };
  return { type: surface.type };
}

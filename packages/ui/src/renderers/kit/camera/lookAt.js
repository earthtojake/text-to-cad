// Look at: where a double-click under Select turns the view, as CAD's "Normal To" does — square to
// the face, edge or ink it is on, its "zero point" (`point`) the orbit centre. The viewport moves
// the camera from it (`ShellViewport.jsx`'s `lookAt`): navigation only. Plain arrays, no three.js.
//
// - A planar face, or flat ink: along its normal, from the side the camera is on; the middle of
//   it, fitted.
// - A cylinder's side: from the side, along the radius toward the camera; the zero point the point
//   of its circumference nearest the camera, the face fitted.
// - A circular edge (or an ellipse): down its axis; its centre, fitted.
// - A straight edge: of the views square to it, the one nearest the camera's now; its middle, fitted.
// - Anything else (a free-form face or edge): the view as it is, the zero point its point nearest
//   the camera, the zoom as it is.
// A straight line of ink is a plane through it, as square to the view as it can be
// (`planeThroughLine`): a line drawn on one face sets the plane standing up through it.

/**
 * @typedef {{ kind: "plane", normal: number[], origin?: number[], points: number[][] }
 *   | { kind: "cylinder", axis: number[], origin: number[], radius: number, points: number[][] }
 *   | { kind: "circle", axis: number[], center: number[], points: number[][] }
 *   | { kind: "line", direction: number[], points: number[][] }
 *   | { kind: "free", points: number[][] }} LookSubject
 *   `points`: where it is in the world (a face's vertices, an edge's or ink's polyline). A plane's
 *   `origin`, a point on it exactly, where its points only lie near it (a highlight's lifted mesh).
 * @typedef {{ direction: number[], point: number[], fit: { min: number[], max: number[] } | null }} LookAt
 *   `direction`: from `point` toward the camera, unit length. `fit`: the box to frame, or null to
 *   keep the zoom.
 */

// A direction this close to an axis is that axis: a mesh normal a hair off true still looks
// straight down it.
const AXIS_SNAP_DEG = 1.5;

const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const scale = (a, s) => a.map(c => c * s);
const add = (a, b) => a.map((c, i) => c + b[i]);
const sub = (a, b) => a.map((c, i) => c - b[i]);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = v => { const l = Math.hypot(v[0], v[1], v[2]); return l > 1e-9 ? v.map(c => c / l) : null; };
const towardEye = (direction, toEye) => (dot(direction, toEye) < 0 ? scale(direction, -1) : direction);

function snapToAxis(direction) {
  const index = [0, 1, 2].reduce((best, axis) => (Math.abs(direction[axis]) > Math.abs(direction[best]) ? axis : best), 0);
  const axis = [0, 1, 2].map(i => (i === index ? Math.sign(direction[index]) || 1 : 0));
  return dot(direction, axis) >= Math.cos((AXIS_SNAP_DEG * Math.PI) / 180) ? axis : direction;
}

/** The box round some points, or null for none. */
export function boundsOf(points) {
  if (!points.length) return null;
  return {
    min: [0, 1, 2].map(axis => Math.min(...points.map(point => point[axis]))),
    max: [0, 1, 2].map(axis => Math.max(...points.map(point => point[axis]))),
  };
}
const middleOf = bounds => bounds.min.map((c, i) => (c + bounds.max[i]) / 2);

/**
 * The plane some points lie in, or null where they lie in none or in many (a straight line): its
 * normal (Newell's, of the polygon they make), when every point is within `tolerance` of the plane
 * through their mean.
 * @param {number[][]} points
 */
export function planeOfPoints(points, tolerance) {
  if (points.length < 3) return null;
  const mean = [0, 1, 2].map(axis => points.reduce((sum, point) => sum + point[axis], 0) / points.length);
  const sum = [0, 0, 0];
  points.forEach((a, index) => {
    const b = points[(index + 1) % points.length];
    sum[0] += (a[1] - b[1]) * (a[2] + b[2]);
    sum[1] += (a[2] - b[2]) * (a[0] + b[0]);
    sum[2] += (a[0] - b[0]) * (a[1] + b[1]);
  });
  const normal = unit(sum);
  const span = Math.max(...points.map(point => Math.hypot(...sub(point, mean))));
  if (!normal || !(span > 0) || Math.hypot(...sum) < span * span * 1e-6) return null;
  return points.every(point => Math.abs(dot(normal, sub(point, mean))) <= tolerance) ? { normal, origin: mean } : null;
}

/**
 * The straight line some points lie along, or null where they do not: its direction and middle, when
 * every point is within `tolerance` of the line from the first to the farthest from it.
 * @param {number[][]} points
 */
export function lineOfPoints(points, tolerance) {
  if (points.length < 2) return null;
  const first = points[0];
  const last = points.reduce((far, point) => (Math.hypot(...sub(point, first)) > Math.hypot(...sub(far, first)) ? point : far), first);
  const direction = unit(sub(last, first));
  if (!direction) return null;
  const off = point => { const from = sub(point, first); return Math.hypot(...sub(from, scale(direction, dot(from, direction)))); };
  return points.every(point => off(point) <= tolerance) ? { direction, origin: scale(add(first, last), 0.5) } : null;
}

// A plane through a line within this angle of standing upright (or lying flat) does: a line drawn
// on a plate's top, double-clicked from a view a little above the side, stands its plane up.
const UPRIGHT_SNAP_DEG = 30;

/**
 * The normal of the plane through a line (`direction`) that is as square to a view along `toEye` as
 * it can be — upright or flat, where it is within `UPRIGHT_SNAP_DEG` of being so; looking straight
 * down the line, the upright one through it (or, upright itself, the one across x). Toward the eye.
 */
export function planeThroughLine(direction, toEye) {
  const along = unit(direction);
  if (!along) return null;
  const square = unit(sub(toEye, scale(along, dot(toEye, along)))) || unit(cross(along, [0, 0, 1])) || unit(cross(along, [1, 0, 0]));
  // The upright planes through the line, and the flat one where the line itself lies flat.
  const candidates = [cross(along, [0, 0, 1]), cross(along, [1, 0, 0]), cross(along, [0, 1, 0]), Math.abs(along[2]) < 1e-6 ? [0, 0, 1] : null]
    .map(candidate => candidate && unit(candidate))
    .filter(candidate => candidate && Math.abs(dot(candidate, along)) < 1e-6 && (Math.abs(candidate[2]) < 1e-6 || Math.abs(Math.abs(candidate[2]) - 1) < 1e-6))
    .map(candidate => towardEye(candidate, square));
  const nearest = candidates.reduce((best, candidate) => (!best || dot(candidate, square) > dot(best, square) ? candidate : best), null);
  return nearest && dot(nearest, square) >= Math.cos((UPRIGHT_SNAP_DEG * Math.PI) / 180) ? nearest : square;
}

/**
 * Where to look at `subject` from a camera whose view runs along `toEye` (from the scene toward the
 * camera, unit length).
 * @param {LookSubject} subject
 * @param {number[]} toEye
 * @returns {LookAt | null}
 */
export function lookAtFor(subject, toEye) {
  const points = subject.points || [];
  const fit = boundsOf(points);
  if (!fit) return null;
  const middle = middleOf(fit);
  if (subject.kind === "plane") {
    const normal = unit(subject.normal);
    if (!normal) return null;
    const direction = snapToAxis(towardEye(normal, toEye));
    // The middle of it, on its plane.
    const offset = subject.origin ? dot(normal, subject.origin) : points.reduce((sum, point) => sum + dot(normal, point), 0) / points.length;
    return { direction, point: sub(middle, scale(normal, dot(normal, middle) - offset)), fit };
  }
  if (subject.kind === "cylinder") {
    const axis = unit(subject.axis);
    if (!axis) return null;
    const across = vector => sub(vector, scale(axis, dot(vector, axis)));
    const direction = unit(across(toEye)) || unit(cross(axis, [0, 0, 1])) || unit(cross(axis, [1, 0, 0]));
    // On the axis level with the face's middle, out along the radius toward the camera.
    const onAxis = add(subject.origin, scale(axis, dot(sub(middle, subject.origin), axis)));
    return { direction, point: add(onAxis, scale(direction, subject.radius)), fit };
  }
  if (subject.kind === "circle") {
    const axis = unit(subject.axis);
    if (!axis) return null;
    return { direction: snapToAxis(towardEye(axis, toEye)), point: subject.center.slice(), fit };
  }
  if (subject.kind === "line") {
    const along = unit(subject.direction);
    if (!along) return null;
    const square = vector => unit(sub(vector, scale(along, dot(vector, along))));
    const direction = square(toEye) || square([0, 0, 1]) || square([1, 0, 0]);
    return { direction: snapToAxis(direction), point: middle, fit };
  }
  // Free-form: the view as it is; the point of it nearest the camera.
  const nearest = points.reduce((best, point) => (dot(point, toEye) > dot(best, toEye) ? point : best), points[0]);
  return { direction: toEye.slice(), point: nearest.slice(), fit: null };
}

/** A box about `point` holding `bounds`: framed, it puts `point` in the middle of the view. */
export function boundsAbout(point, bounds) {
  const half = [0, 1, 2].map(axis => Math.max(Math.abs(point[axis] - bounds.min[axis]), Math.abs(bounds.max[axis] - point[axis])));
  return { min: sub(point, half), max: add(point, half) };
}

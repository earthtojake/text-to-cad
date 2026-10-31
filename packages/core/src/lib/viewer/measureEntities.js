// What two picked ENTITIES measure, as a CAD measure tool reads them (SolidWorks, Onshape, Fusion):
// a pick of a STEP is a vertex, an edge or a face, whole, and the reading follows from the pair, not
// from where on each the pointer happened to be.
//
//   vertex - vertex              distance, and its X Y Z deltas
//   vertex - face / edge         the shortest (perpendicular) distance
//   parallel planes              the distance between them, along their normal
//   planes at an angle           the angle (the acute one, as a chamfer or a draft is quoted)
//   straight edges               the angle; parallel, the distance between them
//   circle - circle / cylinder   centre to centre (axis to axis for a cylinder)
//   circle / cylinder - other    from the centre (the axis), as a hole is located: from its centre
//   anything else                the shortest distance between the two
//
// Pure maths on plain arrays, in the MODEL's frame: a pick's `point` is where the viewer drew it,
// `offset` (the translation the viewer re-centred the model by) takes it back. Nothing here reads
// the selector proxy or the camera; the caller put what it needs in the pick (`segments`, the edge's
// polyline; `geometry`, its fit; `reference.pickData`, the exact surface and curve parameters).

const EPSILON = 1e-9;
// cos of the angle under which two directions are taken as parallel (a quarter of a degree).
const PARALLEL = 0.99999;
// sin of that angle: how far off a plane a line may lean and still be taken as parallel to it.
const PARALLEL_SIN = Math.sqrt(1 - PARALLEL * PARALLEL);
const COPLANAR_TOLERANCE = 1e-6;
// The most segment pairs two polylines are compared on; a longer pair is sampled, not walked.
const MAX_SEGMENT_PAIRS = 40000;

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const length = a => Math.hypot(a[0], a[1], a[2]);
const finitePoint = a => Array.isArray(a) && a.length >= 3 && a.slice(0, 3).every(Number.isFinite);
const unit = a => {
  if (!finitePoint(a)) return null;
  const size = length(a);
  return size > 0 ? scale(a, 1 / size) : null;
};
const clean = distance => (distance < EPSILON ? 0 : distance);
const degrees = alignment => (Math.acos(Math.max(-1, Math.min(1, alignment))) * 180) / Math.PI;
const positive = value => (Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : null);

// ---- an entity from a pick ----------------------------------------------------------------------

const offsetOf = pick => (finitePoint(pick?.offset) ? pick.offset.slice(0, 3) : [0, 0, 0]);
const toModel = (pick, point) => sub(point, offsetOf(pick));

/**
 * What a pick is, for a measurement: a `point` (a vertex), a `line` (a straight edge, its ends
 * where the polyline gives them), a `circle` (a circular edge or arc), a `polyline` (any other
 * edge), a `plane`, a `cylinder`, a `sphere`, or `surface` (a face that is none of those: only
 * the point under the pointer is known). A free point, or a pick that never snapped, is `loose`: it
 * describes nothing but where it landed, so no relation is read off it. In the model's frame.
 *
 * @param {object} pick  `{ point, snapKind, geometry?, segments?, reference?, offset? }`
 */
export function entityOfPick(pick) {
  if (!finitePoint(pick?.point)) return null;
  const at = toModel(pick, pick.point);
  const pickData = pick.reference?.pickData || {};
  const params = pickData.params || {};
  if (pick.snapKind === "vertex") return { type: "point", p: at };
  if (pick.snapKind === "edge") {
    const geometry = pick.geometry;
    const segments = pick.segments && pick.segments.length >= 6 ? pick.segments : null;
    if (geometry?.kind === "line") {
      const d = unit(geometry.direction);
      if (!d) return { type: "loose", p: at };
      let start = null;
      let end = null;
      if (segments) {
        let low = Infinity, high = -Infinity;
        for (let index = 0; index + 2 < segments.length; index += 3) {
          const point = [segments[index], segments[index + 1], segments[index + 2]];
          const t = dot(sub(point, at), d);
          if (t < low) { low = t; start = point; }
          if (t > high) { high = t; end = point; }
        }
      }
      return { type: "line", p: at, d, a: start, b: end };
    }
    if (geometry?.kind === "arc") {
      const exactCenter = finitePoint(params.center) ? params.center.slice(0, 3) : null;
      const center = exactCenter || (finitePoint(geometry.center) ? toModel(pick, geometry.center) : null);
      const radius = positive(params.radius) ?? positive(geometry.radius);
      if (!center || !radius) return { type: "loose", p: at };
      let axis = unit(params.axis);
      if (!axis && segments) {
        // Without the exact axis: the plane of the centre, the first point and one a third of the way round.
        const third = Math.floor(segments.length / 18) * 6;
        axis = unit(cross(sub([segments[0], segments[1], segments[2]], center), sub([segments[third], segments[third + 1], segments[third + 2]], center)));
      }
      return { type: "circle", c: center, r: radius, n: axis, segs: segments };
    }
    if (segments) return { type: "polyline", segs: segments };
    return { type: "loose", p: at };
  }
  if (pick.snapKind === "face") {
    const surface = String(pickData.surfaceType || "").trim().toLowerCase();
    const normal = unit(pickData.normal);
    if (normal && (surface === "plane" || surface === "planar")) return { type: "plane", p: at, n: normal };
    const axis = unit(params.axis);
    if (surface.includes("cylind") && axis && finitePoint(params.origin) && positive(params.radius)) {
      return { type: "cylinder", p: at, o: params.origin.slice(0, 3), d: axis, r: Number(params.radius) };
    }
    if (surface.includes("sphere") && finitePoint(params.center) && positive(params.radius)) {
      return { type: "sphere", c: params.center.slice(0, 3), r: Number(params.radius) };
    }
    return { type: "surface", p: at };
  }
  return { type: "loose", p: at };
}

/**
 * What a pick is, as a key: the same vertex, edge or face is the same key, so a second press on
 * what is already picked is told from a press on something else. Null for a free point or a pick
 * that bound to no entity.
 */
export function pickEntityKey(pick) {
  if (!finitePoint(pick?.point)) return null;
  if (pick.snapKind === "vertex") return `v:${toModel(pick, pick.point).map(value => value.toFixed(5)).join(",")}`;
  if ((pick.snapKind === "edge" || pick.snapKind === "face") && pick.referenceId) return `${pick.snapKind[0]}:${pick.referenceId}`;
  return null;
}

// ---- closest points ----------------------------------------------------------------------------

function closestOnSegment(point, a, b) {
  const direction = sub(b, a);
  const size = dot(direction, direction);
  const t = size > 0 ? Math.max(0, Math.min(1, dot(sub(point, a), direction) / size)) : 0;
  return add(a, scale(direction, t));
}

const segmentAt = (segs, index) => [[segs[index], segs[index + 1], segs[index + 2]], [segs[index + 3], segs[index + 4], segs[index + 5]]];

/** The closest points of two segments (Ericson, Real-Time Collision Detection 5.1.9). */
function closestOfSegments(p1, q1, p2, q2) {
  const d1 = sub(q1, p1), d2 = sub(q2, p2), r = sub(p1, p2);
  const a = dot(d1, d1), e = dot(d2, d2), f = dot(d2, r);
  let s, t;
  if (a <= EPSILON && e <= EPSILON) { s = 0; t = 0; }
  else if (a <= EPSILON) { s = 0; t = Math.max(0, Math.min(1, f / e)); }
  else {
    const c = dot(d1, r);
    if (e <= EPSILON) { t = 0; s = Math.max(0, Math.min(1, -c / a)); }
    else {
      const b = dot(d1, d2), denominator = a * e - b * b;
      s = denominator > EPSILON * a * e ? Math.max(0, Math.min(1, (b * f - c * e) / denominator)) : 0;
      t = (b * s + f) / e;
      if (t < 0) { t = 0; s = Math.max(0, Math.min(1, -c / a)); }
      else if (t > 1) { t = 1; s = Math.max(0, Math.min(1, (b - c) / a)); }
    }
  }
  const one = add(p1, scale(d1, s)), two = add(p2, scale(d2, t));
  return { one, two, distance: length(sub(one, two)) };
}

function closestOfPolylines(first, second) {
  const count = (first.length / 6) * (second.length / 6);
  const stride = count > MAX_SEGMENT_PAIRS ? Math.ceil(Math.sqrt(count / MAX_SEGMENT_PAIRS)) : 1;
  let best = null;
  for (let i = 0; i + 5 < first.length; i += 6 * stride) {
    const [p1, q1] = segmentAt(first, i);
    for (let j = 0; j + 5 < second.length; j += 6 * stride) {
      const [p2, q2] = segmentAt(second, j);
      const found = closestOfSegments(p1, q1, p2, q2);
      if (!best || found.distance < best.distance) best = found;
    }
  }
  return best;
}

function closestOnPolyline(point, segs) {
  let best = null;
  for (let index = 0; index + 5 < segs.length; index += 6) {
    const [a, b] = segmentAt(segs, index);
    const on = closestOnSegment(point, a, b);
    const distance = length(sub(point, on));
    if (!best || distance < best.distance) best = { on, distance };
  }
  return best;
}

/** The polyline (or segment) of an edge entity, flat, or null when its extent is unknown. */
function segsOf(entity) {
  if (entity.type === "line") return entity.a && entity.b ? [...entity.a, ...entity.b] : null;
  return entity.segs || null;
}

// ---- relations ---------------------------------------------------------------------------------

const reading = (kind, start, end, extra = {}) => ({ kind, start, end, ...extra });

function pointPoint(a, b) {
  return reading("distance", a.p, b.p, { distance: length(sub(b.p, a.p)) });
}

function pointPlane(point, plane) {
  const signed = dot(sub(point.p, plane.p), plane.n);
  return reading("normal", point.p, sub(point.p, scale(plane.n, signed)), { distance: Math.abs(signed) });
}

function pointLine(point, line) {
  const segment = line.a && line.b;
  const on = segment ? closestOnSegment(point.p, line.a, line.b) : add(line.p, scale(line.d, dot(sub(point.p, line.p), line.d)));
  const interior = !segment || (dot(sub(on, line.a), sub(line.b, line.a)) > EPSILON && dot(sub(on, line.b), sub(line.a, line.b)) > EPSILON);
  return reading(interior ? "normal" : "min", point.p, on, { distance: length(sub(on, point.p)) });
}

function pointPolyline(point, edge) {
  const segs = segsOf(edge);
  const best = segs ? closestOnPolyline(point.p, segs) : null;
  return best ? reading("min", point.p, best.on, { distance: best.distance }) : null;
}

// A hole is located by its axis: a vertex to a cylinder is the distance to the axis, square to it.
function pointCylinder(point, cylinder) {
  const foot = add(cylinder.o, scale(cylinder.d, dot(sub(point.p, cylinder.o), cylinder.d)));
  return reading("normal", point.p, foot, { distance: length(sub(point.p, foot)) });
}

// And a circle by its centre: a vertex to a circular edge is the distance to the centre.
function pointCircle(point, circle) {
  return reading("centers", point.p, circle.c, { distance: length(sub(circle.c, point.p)) });
}

function pointSphere(point, sphere) {
  const radial = sub(point.p, sphere.c);
  const rho = length(radial);
  if (rho <= EPSILON) return null;
  return reading("min", point.p, add(sphere.c, scale(radial, sphere.r / rho)), { distance: Math.abs(rho - sphere.r) });
}

function planePlane(first, second, { sameFace }) {
  const alignment = Math.abs(dot(first.n, second.n));
  if (alignment < PARALLEL) return { kind: "angle", angleDeg: degrees(alignment), start: first.p, end: second.p, distance: null };
  const separation = dot(sub(second.p, first.p), first.n);
  // One face twice, or two flats at one height, have nothing between them to report.
  if (sameFace || Math.abs(separation) <= COPLANAR_TOLERANCE) return null;
  return reading("normal", first.p, add(first.p, scale(first.n, separation)), { distance: Math.abs(separation) });
}

function linePlane(line, plane) {
  const lean = Math.abs(dot(line.d, plane.n));
  const ends = line.a && line.b ? [line.a, line.b] : [line.p];
  const signed = ends.map(end => dot(sub(end, plane.p), plane.n));
  if (lean > PARALLEL_SIN) {
    // The angle a line makes with a plane; its distance is where it comes nearest, 0 where it crosses.
    const crosses = signed.length === 2 && Math.sign(signed[0]) !== Math.sign(signed[1]);
    return { kind: "angle", angleDeg: (Math.asin(Math.min(1, lean)) * 180) / Math.PI, start: line.p, end: plane.p,
      distance: crosses ? 0 : Math.min(...signed.map(Math.abs)) };
  }
  const gap = dot(sub(line.p, plane.p), plane.n);
  return reading("normal", line.p, sub(line.p, scale(plane.n, gap)), { distance: Math.abs(gap) });
}

function circlePlane(circle, plane) {
  // From the centre, square to the plane, whichever way the circle faces: a hole's distance from a face.
  const signed = dot(sub(circle.c, plane.p), plane.n);
  return reading("normal", circle.c, sub(circle.c, scale(plane.n, signed)), { distance: Math.abs(signed) });
}

function polylinePlane(edge, plane) {
  const segs = segsOf(edge);
  if (!segs) return null;
  let best = null, below = false, above = false;
  for (let index = 0; index + 2 < segs.length; index += 3) {
    const point = [segs[index], segs[index + 1], segs[index + 2]];
    const signed = dot(sub(point, plane.p), plane.n);
    below ||= signed < 0; above ||= signed > 0;
    if (!best || Math.abs(signed) < Math.abs(best.signed)) best = { point, signed };
  }
  if (!best) return null;
  return reading("min", best.point, sub(best.point, scale(plane.n, best.signed)), { distance: below && above ? 0 : Math.abs(best.signed) });
}

function cylinderPlane(cylinder, plane) {
  // A hole's wall to a face it runs along: its axis's distance from the face, drawn level with the pick.
  if (Math.abs(dot(cylinder.d, plane.n)) > PARALLEL_SIN) return null;
  const axisPoint = add(cylinder.o, scale(cylinder.d, dot(sub(cylinder.p || cylinder.o, cylinder.o), cylinder.d)));
  const signed = dot(sub(axisPoint, plane.p), plane.n);
  return reading("normal", axisPoint, sub(axisPoint, scale(plane.n, signed)), { distance: Math.abs(signed) });
}

// The centre to a straight edge, square to it where it falls within the edge.
const circleLine = (circle, line) => pointLine({ p: circle.c }, line);

function cylinderLine(cylinder, line) {
  // An edge along a hole: the distance between the edge and the axis.
  if (Math.abs(dot(cylinder.d, line.d)) < PARALLEL) return null;
  const foot = add(cylinder.o, scale(cylinder.d, dot(sub(line.p, cylinder.o), cylinder.d)));
  return reading("normal", foot, line.p, { distance: length(sub(line.p, foot)) });
}

function planeSphere(plane, sphere) {
  const signed = dot(sub(sphere.c, plane.p), plane.n);
  const near = sub(sphere.c, scale(plane.n, Math.sign(signed || 1) * Math.min(Math.abs(signed), sphere.r)));
  return reading("min", near, sub(near, scale(plane.n, dot(sub(near, plane.p), plane.n))), { distance: Math.max(0, Math.abs(signed) - sphere.r) });
}

function lineLine(first, second) {
  const alignment = Math.abs(dot(first.d, second.d));
  const apart = sub(second.p, first.p);
  if (alignment >= PARALLEL) {
    const toSecond = sub(apart, scale(first.d, dot(apart, first.d)));
    return reading("normal", first.p, add(first.p, toSecond), { distance: length(toSecond), angleDeg: 0 });
  }
  let distance;
  if (first.a && first.b && second.a && second.b) distance = closestOfSegments(first.a, first.b, second.a, second.b).distance;
  else distance = Math.abs(dot(apart, unit(cross(first.d, second.d)))) ;
  return { kind: "angle", angleDeg: degrees(alignment), start: first.p, end: second.p, distance };
}

function circleCircle(first, second) {
  return reading("centers", first.c, second.c, { distance: length(sub(second.c, first.c)) });
}

function axisLine(point, direction, other) {
  const toPoint = sub(other, point);
  return sub(toPoint, scale(direction, dot(toPoint, direction)));
}

function circleCylinder(circle, cylinder) {
  // Coaxial or side by side, the centre to the axis: a rim and a bore are compared by their centres.
  const found = pointCylinder({ p: circle.c }, cylinder);
  return { ...found, kind: "centers" };
}

function cylinderCylinder(first, second) {
  const alignment = Math.abs(dot(first.d, second.d));
  if (alignment < PARALLEL) return { kind: "angle", angleDeg: degrees(alignment), start: first.o, end: second.o, distance: null };
  const radial = axisLine(first.o, first.d, second.o);
  return reading("centers", first.o, add(first.o, radial), { distance: length(radial) });
}

function polylinePolyline(first, second) {
  const one = segsOf(first), two = segsOf(second);
  if (!one || !two) return null;
  const best = closestOfPolylines(one, two);
  return best ? reading("min", best.one, best.two, { distance: best.distance }) : null;
}

// Each row names a pair in the order its function takes it; the other order is the same row, swapped.
const RELATIONS = {
  "point|point": pointPoint, "point|plane": pointPlane, "point|line": pointLine, "point|polyline": pointPolyline,
  "point|circle": pointCircle, "point|cylinder": pointCylinder, "point|sphere": pointSphere,
  "plane|plane": planePlane, "line|plane": linePlane, "circle|plane": circlePlane, "polyline|plane": polylinePlane,
  "cylinder|plane": cylinderPlane, "plane|sphere": planeSphere,
  "line|line": lineLine, "circle|circle": circleCircle, "circle|cylinder": circleCylinder, "cylinder|cylinder": cylinderCylinder,
  "line|polyline": polylinePolyline, "circle|line": circleLine, "cylinder|line": cylinderLine, "circle|polyline": polylinePolyline, "polyline|polyline": polylinePolyline
};

function swapped(result) {
  return result ? { ...result, start: result.end, end: result.start } : null;
}

/**
 * The relation of two entities (`entityOfPick`), first to second: `{ kind, distance, angleDeg?, start,
 * end }`, `kind` what the pair is read as ("distance", "normal", "centers", "angle" or "min") and
 * `start`/`end` the points the reading is drawn between. Null where the pair has no reading but the
 * distance between the two points picked.
 */
export function relateEntities(first, second, { sameFace = false } = {}) {
  if (!first || !second) return null;
  const direct = RELATIONS[`${first.type}|${second.type}`];
  const reverse = RELATIONS[`${second.type}|${first.type}`];
  const found = direct ? direct(first, second, { sameFace }) : reverse ? swapped(reverse(second, first, { sameFace })) : null;
  if (!found || !(found.distance === null || Number.isFinite(found.distance))) return null;
  return found;
}

/**
 * The reading of two picks: `measurementFromPicks`' entity half. In the picks' own (world)
 * coordinates, `start` and `end` the points its dimension is drawn between.
 *
 * @returns {{ kind: string, distance: number | null, angleDeg: number | null, start: number[], end: number[] } | null}
 */
export function measureEntityPair(pickA, pickB) {
  const first = entityOfPick(pickA), second = entityOfPick(pickB);
  const sameFace = Boolean(pickA?.referenceId && pickA.referenceId === pickB?.referenceId);
  const found = relateEntities(first, second, { sameFace });
  if (!found) return null;
  // Two that touch (an edge in the face it is measured to, a vertex on its own face) have no gap to
  // report, as two flats at one height have none: the reading is the two points', not "0.00 mm".
  if ((found.kind === "normal" || found.kind === "min") && found.distance !== null && found.distance <= COPLANAR_TOLERANCE) return null;
  const offset = offsetOf(pickA);
  return {
    kind: found.kind,
    distance: found.distance === null || found.distance === undefined ? null : clean(found.distance),
    angleDeg: Number.isFinite(found.angleDeg) ? found.angleDeg : null,
    // An angle is read between the planes or edges, not along any line: its dimension joins the points picked.
    start: found.kind === "angle" ? pickA.point.slice(0, 3) : add(found.start, offset),
    end: found.kind === "angle" ? pickB.point.slice(0, 3) : add(found.end, offset)
  };
}

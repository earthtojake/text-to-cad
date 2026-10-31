// Where an engine document's PMI is drawn in the model: for each annotation (`xbfPmi.js`), the
// point on its feature its leader starts from, where its label stands, and a distance's extension
// and dimension lines -- all in the scene's coordinates, made from the elements its references name
// (`xbfScene.js`'s `elementGeometry`: a face's surface and its nodes).
//
// Where the model's code placed it (`presentation`: an anchor on the feature and the label's offset
// from it) is where it is drawn; an annotation the code never placed is put beside its feature, out
// from the part, each of a face's turned a little from the last so two on one face stand apart. A
// placement says where a callout is drawn and nothing else: the feature it is about and every value
// it says are the document's, wherever it stands.
//
// A distance is drawn as a drawing draws one: its text at the label, the dimension line through it
// along what it measures, from one end to the other, and an extension line from each end out to it.
// Each end is a flat face's plane or a round face's axis (a basic dimension to a hole is to its
// centre line): between two planes it is measured along the first's normal, from a plane to an axis
// along the plane's, between two axes square to both. A plane's extension line runs from the
// anchor's foot on it, an axis's from the point of the axis nearest the dimension line. One the code
// never placed is anchored at the first face's edge (a first axis: at its end), so its extension
// lines are short.
//
// A flag note is drawn as a frame is, out from its first face. A general note, the part's general
// profile (its Note 1, on every face nothing else controls) and a flag note naming annotations and
// no face are said in the notes and drawn as nothing on the part (`pmiDrawnOnPart`), so they take
// no turn of a face either.

import { add, cross, dot, length, placeXbfPoint, scale, sub, unit } from "./xbfEntities.js";
import { invert } from "./xbfKinematics.js";

const mean = points => scale(points.reduce((sum, point) => add(sum, point), [0, 0, 0]), 1 / points.length);
// Any direction square to `n`: what a side is where nothing else says one.
const anyPerpendicular = n => unit(Math.abs(n[0]) < 0.9 ? cross(n, [1, 0, 0]) : cross(n, [0, 1, 0]));
// `v` turned by `angle` about the unit axis `n` (Rodrigues).
const turned = (v, n, angle) => add(add(scale(v, Math.cos(angle)), scale(cross(n, v), Math.sin(angle))), scale(n, dot(n, v) * (1 - Math.cos(angle))));
/** The part of `v` square to the unit `n`. */
const across = (v, n) => sub(v, scale(n, dot(v, n)));

// Each later annotation of a feature is turned this much about its normal from the one before.
const SPREAD = Math.PI / 4.5;
// How far out a label the code never placed stands: this share of the model's diagonal, at least the floor.
const REACH_SHARE = 0.18, REACH_MIN = 4;

const boxCentre = bounds => (bounds ? scale(add(bounds.min, bounds.max), 0.5) : [0, 0, 0]);
const boxDiagonal = bounds => (bounds ? length(sub(bounds.max, bounds.min)) : 0);
/** How far out from its feature a label the code never placed stands. */
const pmiReach = bounds => Math.max(REACH_MIN, boxDiagonal(bounds) * REACH_SHARE);
/**
 * Whether an annotation is drawn on the part: all but what is said in the notes alone -- a general
 * note, the general profile, and a flag note naming annotations and no face. That one has no face
 * of its own to stand on, and drawn on its annotations' it would say it is about those faces,
 * which its code never said (a drawing flags the callout, which this cannot stand beside): it is
 * listed, its pick lighting what its annotations are on.
 *
 * @param {import("./xbfPmi.js").XbfPmiEntry} entry
 */
export function pmiDrawnOnPart(entry) {
  if (entry.note?.general || entry.tolerance?.general) return false;
  return !(entry.kind === "note" && !entry.refs.length);
}

/**
 * A point on a face to start a leader from: one of its own nodes, so it is on the face whatever its
 * shape (a plate's top round a hole has its middle in the hole). A flat face's is the node nearest
 * its nodes' middle; a cylinder's is on its rim at its axis's far end, the one farthest out from the
 * model's middle, so a hole's leader leaves its edge.
 *
 * @param {{ surface: object, points?: number[][] } | null} geometry  `elementGeometry(id, { points: true })`.
 * @param {number[]} [centre]  The model's middle.
 */
export function pmiFeaturePoint(geometry, centre = [0, 0, 0]) {
  const points = geometry?.points || [];
  if (!points.length) return geometry?.surface?.origin ? geometry.surface.origin.slice() : null;
  const surface = geometry.surface || {};
  if (surface.type === "cylinder" && surface.axis) {
    const far = Math.max(...points.map(point => dot(point, surface.axis)));
    const rim = points.filter(point => dot(point, surface.axis) > far - 1e-6 * Math.max(1, Math.abs(far)));
    return rim.reduce((best, point) => (length(sub(point, centre)) > length(sub(best, centre)) + 1e-9 ? point : best), rim[0]).slice();
  }
  const middle = mean(points);
  return points.reduce((best, point) => (length(sub(point, middle)) < length(sub(best, middle)) - 1e-9 ? point : best), points[0]).slice();
}

/**
 * A point at a flat face's edge, the node of it farthest out from the model's middle across `n`:
 * where a distance the code never placed has its anchor, so its extension lines run out from the
 * part's side rather than across it.
 */
function edgePoint(geometry, centre, n) {
  const points = geometry?.points || [];
  if (!points.length) return geometry?.surface?.origin ? geometry.surface.origin.slice() : null;
  const out = point => length(across(sub(point, centre), n));
  return points.reduce((best, point) => (out(point) > out(best) + 1e-9 ? point : best), points[0]).slice();
}

// How far an axis may lean off square to what a distance measures, or two axes off parallel (sin).
const SQUARE = 1e-3;

/** The direction a face's callouts go out along: a flat face's normal, a cylinder's axis. */
function outward(geometry) {
  const surface = geometry?.surface || {};
  if (surface.type === "plane" && surface.normal) return unit(surface.normal);
  if (surface.type === "cylinder" && surface.axis) return unit(surface.axis);
  return null;
}

/**
 * One end of a distance: a flat face's plane (`{ origin, normal }`) or a round face's axis
 * (`{ origin, axis }`), else null.
 */
function distanceEnd(geometry) {
  const surface = geometry?.surface || {};
  if (surface.type === "plane" && surface.normal && surface.origin) return { origin: surface.origin, normal: unit(surface.normal) };
  if (surface.type === "cylinder" && surface.axis && surface.origin) return { origin: surface.origin, axis: unit(surface.axis) };
  return null;
}

/**
 * The direction a distance between two ends is measured along, or null where they make none: the
 * first plane's normal, else the other's; two axes, square to both from the first to the second
 * (none where they are not parallel, or are one). An axis must lie square to it.
 */
function measuredAlong(from, to) {
  let n;
  if (from.normal) n = from.normal;
  else if (to.normal) n = to.normal;
  else {
    if (length(cross(from.axis, to.axis)) > SQUARE) return null;
    n = unit(across(sub(to.origin, from.origin), from.axis));
  }
  if (!n) return null;
  return [from, to].every(end => !end.axis || Math.abs(dot(end.axis, n)) <= SQUARE) ? n : null;
}

/**
 * The direction a distance between two faces is measured along (each an `elementGeometry`, or
 * anything with its `surface`), as it is drawn (`measuredAlong`), or null where they make none.
 */
export function pmiDistanceAlong(a, b) {
  const from = distanceEnd(a), to = distanceEnd(b);
  return from && to ? measuredAlong(from, to) : null;
}

/**
 * Where an annotation the code never placed stands: out from its feature along the feature's
 * direction (`out`) and away from the model's middle across it, turned `turn` steps about it.
 */
function defaultOffset({ anchor, out, centre, reach, turn }) {
  const away = unit(across(sub(anchor, centre), out)) || anyPerpendicular(out);
  const side = turned(away, out, turn * SPREAD);
  return add(scale(out, reach), scale(side, reach * 0.6));
}

/**
 * What an annotation is drawn as, in the scene's coordinates, or null where it cannot be (a
 * reference that names no element on the page and no placement to stand at) or is not drawn on the
 * part (said in the notes alone, `pmiDrawnOnPart`).
 *
 * - `anchor`: where its leader starts on its feature (a distance's: on its first face); where its
 *   feature is not on the page (a broken reference), where the code anchored it, and `broken`.
 * - `label`: where its text stands.
 * - `dimension`: a distance's dimension line (`from`, `to`: at each end's plane or axis, through the label)
 *   and its extension lines (`extensions`), else null; a distance has no leader.
 * - `presentation`: the placement drawn (`{ anchor, offset }`), as `place` would write it.
 * - `placed`: `"given"` (its `placement` here, or the code's), or `"default"`.
 *
 * @param {import("./xbfPmi.js").XbfPmiEntry} entry
 * @param {{ geometry: Record<string, { surface: object, points?: number[][] } | null>, bounds?: { min: number[], max: number[] } | null,
 *   turn?: number, placement?: { anchor: number[], offset: number[] } | null }} options
 *   `geometry`: each role's element (`feature`, `from`, `to`), null for one not on the page; `turn`:
 *   how many of its feature's annotations came before it; `placement`: one to draw it at in place of
 *   the code's (a drag not yet written).
 */
export function pmiConstruction(entry, { geometry, bounds = null, turn = 0, placement = null }) {
  if (!pmiDrawnOnPart(entry)) return null;
  const centre = boxCentre(bounds);
  const reach = pmiReach(bounds);
  const given = placement || entry.presentation;
  const at = given ? { anchor: given.anchor.slice(), offset: given.offset.slice() } : null;
  const placed = given ? "given" : "default";
  if (entry.kind === "dimension" && entry.dimension?.type === "distance") {
    const from = distanceEnd(geometry.from), to = distanceEnd(geometry.to);
    const n = from && to ? measuredAlong(from, to) : null;
    if (!n) {
      return at ? { anchor: at.anchor, label: add(at.anchor, at.offset), dimension: null, presentation: at, placed, broken: true } : null;
    }
    // How far along the measure a point stands; each end stands at its origin's (an axis lies square to it).
    const level = point => dot(point, n);
    const onLevel = (point, end) => sub(point, scale(n, level(point) - level(end.origin)));
    const onAxis = (point, end) => add(end.origin, scale(end.axis, dot(sub(point, end.origin), end.axis)));
    const anchor = at ? at.anchor
      : from.normal ? edgePoint(geometry.from, centre, n) : onAxis(pmiFeaturePoint(geometry.from, centre), from);
    const offset = at ? at.offset : (() => {
      const away = unit(across(sub(anchor, centre), n)) || anyPerpendicular(n);
      const side = turned(away, n, turn * SPREAD);
      // Halfway between the ends, out to the side.
      return add(scale(n, (level(to.origin) - level(anchor)) / 2), scale(side, reach * 0.5));
    })();
    const label = add(anchor, offset);
    // The dimension line through the label, from one end's level to the other's. A plane's extension
    // line runs square to it from the anchor's foot on the plane (an anchor the code put off the face,
    // at its side's mid-height, still extends from the face); an axis's from its point nearest the
    // dimension line's end, across to it.
    const onFrom = onLevel(label, from), onTo = onLevel(label, to);
    const extension = (end, on) => [end.normal ? onLevel(anchor, end) : onAxis(on, end), on];
    return { anchor, label, dimension: { from: onFrom, to: onTo, extensions: [extension(from, onFrom), extension(to, onTo)] },
      presentation: { anchor, offset }, placed };
  }
  const feature = geometry.feature;
  const out = outward(feature);
  if (!feature || !out) return at ? { anchor: at.anchor, label: add(at.anchor, at.offset), dimension: null, presentation: at, placed, broken: true } : null;
  const anchor = at ? at.anchor : pmiFeaturePoint(feature, centre);
  const offset = at ? at.offset : defaultOffset({ anchor, out, centre, reach, turn });
  return { anchor, label: add(anchor, offset), dimension: null, presentation: { anchor, offset }, placed };
}

/**
 * Where a label dragged to `label` puts the annotation: its anchor where it was, its offset to the
 * label's new place. What it means is not touched.
 */
export function pmiMovedPlacement(presentation, label) {
  return { anchor: presentation.anchor.slice(), offset: sub(label, presentation.anchor) };
}

// A part's placement as the structure holds it: 4 x 4, column-major (`instances[].matrix`). An offset
// is turned by it and not moved, at its own length (`placeXbfDirection` would make it a unit).
const turnedBy = (m, d) => [0, 1, 2].map(row => m[row] * d[0] + m[4 + row] * d[1] + m[8 + row] * d[2]);
const isMatrix = m => Array.isArray(m) && m.length === 16 && m.every(Number.isFinite);

/**
 * A presentation in its part's frame (as `place` writes it) where the part stands in the scene
 * (`matrix`, the part's placement), and `pmiPresentationToPart` back: the anchor is a point, the
 * offset a direction. No placement, or one that is no matrix: the frames are one.
 */
export function pmiPresentationToScene(presentation, matrix) {
  if (!presentation || !isMatrix(matrix)) return presentation;
  return { anchor: placeXbfPoint(matrix, presentation.anchor), offset: turnedBy(matrix, presentation.offset) };
}

export function pmiPresentationToPart(presentation, matrix) {
  return isMatrix(matrix) ? pmiPresentationToScene(presentation, invert(matrix)) : presentation;
}

/**
 * Every annotation of a document as the viewer draws it (`pmiConstruction`), by `key`: each supported
 * one from the elements its references name where it is drawn (`elements`, by ref: an element id, or
 * null for one not on the page), as `geometry` reads each, a role's the first of its refs' (a
 * profile or a flag note on several faces stands on the first); its presentation, and a label
 * dragged there and not yet written (`placements`, by key), taken from its part's frame (`frame`:
 * the matrix of the occurrence it is drawn at; none, the scene's) to the scene's; and each later
 * annotation of a feature (its first element) turned from the one before. One that cannot be drawn,
 * or is said in the notes, is left out.
 *
 * @param {ReadonlyArray<{ entry: import("./xbfPmi.js").XbfPmiEntry,
 *   elements: ReadonlyArray<string | null>, frame?: number[] | null }>} drawn
 * @param {{ geometry: (id: string) => { surface: object, points?: number[][] } | null,
 *   bounds?: { min: number[], max: number[] } | null,
 *   placements?: ReadonlyMap<string, { anchor: number[], offset: number[] }> | null }} options
 * @returns {Map<string, NonNullable<ReturnType<typeof pmiConstruction>>>}
 */
export function pmiConstructions(drawn, { geometry, bounds = null, placements = null }) {
  const found = new Map();
  const turns = new Map();
  for (const { entry, elements, frame = null } of drawn) {
    if (!entry.supported || !pmiDrawnOnPart(entry)) continue;
    const roles = {};
    entry.refs.forEach((ref, index) => { if (!(ref.role in roles)) roles[ref.role] = elements[index] ? geometry(elements[index]) : null; });
    const first = elements[0] || entry.key;
    const turn = turns.get(first) || 0;
    turns.set(first, turn + 1);
    const construction = pmiConstruction({ ...entry, presentation: pmiPresentationToScene(entry.presentation, frame) },
      { geometry: roles, bounds, turn, placement: pmiPresentationToScene(placements?.get(entry.key) || null, frame) });
    if (construction) found.set(entry.key, construction);
  }
  return found;
}

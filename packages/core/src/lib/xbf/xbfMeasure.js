// An engine document's faces, edges and vertices as Measure takes them: whole, in the measure
// tool's pick (`../viewer/measurement.js`'s `classifyMeasurePick`: `{ point, snapKind, referenceId,
// reference: { pickData }, geometry, segments }`), so the readings of a pair are the ones a STEP's
// were (`../viewer/measureEntities.js`): parallel faces square across, holes by their axes and
// centres, faces and edges at an angle by the angle, vertices by the distance between them.
//
// What a face is comes from its mesh (`xbfEntities.js`: a plane's normal, a cylinder's axis and
// radius, a sphere's centre); an edge is its polyline, read as a line or an arc
// (`edgeGeometryFromSegments`), as a STEP's edge was when its row carried no parameters. What only
// the kernel knows exactly -- an edge's length along a curve, a circle's radius, a face's area --
// is the engine's facts of the element (`fetchXbfElementFacts`), where the caller has them.
// Everything in the scene's coordinates, where the instance stands now: nothing re-centres an
// engine document, so a pick carries no offset.

import { closestPointOnSegmentList, edgeGeometryFromSegments, isFinitePoint } from "../viewer/measurement.js";
import { xbfSegments } from "./xbfEntities.js";

const positive = value => (Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : null);

/**
 * A face or an edge under the pointer (`pickElement`'s hit: `{ id, kind, point }`) as Measure takes
 * it whole, or null where the scene has no such element. `facts`: the engine's facts of it, when
 * they are in (an edge's exact `length` and a circle's `radius`).
 *
 * @param {ReturnType<typeof import("./xbfScene.js").createXbfScene>} scene
 * @param {{ id: string, kind: "face" | "edge", point: number[] }} hit
 * @param {{ facts?: object | null }} [options]
 */
export function xbfMeasureEntity(scene, hit, { facts = null } = {}) {
  if (!hit || !isFinitePoint(hit.point) || !["face", "edge"].includes(hit.kind)) return null;
  const element = scene.elementGeometry(hit.id);
  if (!element || element.kind !== hit.kind) return null;
  if (element.kind === "face") {
    const surface = element.surface;
    const params = {};
    if (surface.type === "cylinder") Object.assign(params, { axis: surface.axis, origin: surface.origin, radius: surface.radius });
    if (surface.type === "sphere") Object.assign(params, { center: surface.center, radius: surface.radius });
    const pickData = { selectorType: "face", surfaceType: surface.type, params, ...(surface.type === "plane" ? { normal: surface.normal } : {}) };
    return { point: hit.point.slice(0, 3), snapKind: "face", referenceId: hit.id,
      reference: { id: hit.id, selectorType: "face", pickData }, geometry: null };
  }
  const segments = xbfSegments(element.points);
  const geometry = edgeGeometryFromSegments(segments);
  const point = closestPointOnSegmentList(segments, hit.point) || hit.point.slice(0, 3);
  // A straight edge's length is its polyline's; a curve's is the kernel's, along it.
  const along = element.points.reduce((sum, at, index) => (index ? sum + Math.hypot(...[0, 1, 2].map(axis => at[axis] - element.points[index - 1][axis])) : 0), 0);
  const length = geometry?.kind === "line" ? along : positive(facts?.length);
  const radius = geometry?.kind === "arc" && facts?.curve === "circle" ? positive(facts.radius) : null;
  const pickData = { selectorType: "edge", params: radius ? { radius } : {}, ...(length !== null ? { length } : {}) };
  return { point, snapKind: "edge", referenceId: hit.id, reference: { id: hit.id, selectorType: "edge", pickData }, geometry, segments };
}

/**
 * A vertex (`i3/vertex/2`) as Measure takes it, or null: what an edge's end under the pointer is
 * (`kit/tools/measure/measureFilter.js` turns an edge pick into one).
 */
export function xbfMeasureVertex(scene, id) {
  const element = scene.elementGeometry(id);
  return element?.kind === "vertex" ? { point: element.point, snapKind: "vertex", referenceId: id, reference: null, geometry: null } : null;
}

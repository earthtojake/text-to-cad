import { projectWorldPointToClient } from "@text-to-cad/core/lib/viewer/measureRuler.js";
import { xbfMeasureEntity } from "@text-to-cad/core/lib/xbf/xbfMeasure.js";
import { edgeEnds, nearestEnd, restrictMeasurePick } from "../kit/tools/measure/measureFilter.js";

// What a Measure press, or the pointer resting, takes on an engine document: an ENTITY, whole, as a
// STEP's Measure took it -- the vertex within a few pixels of the pointer (an edge's end), else
// the edge, else the face under it, kept to what Measure's menu chose (`measureFilter.js`) -- and
// the point on it its reading is drawn from. The hover and the press ask the same question, with
// a press's reach: what lights before a press is what the press takes. Shift takes the point on
// the model as it is, the one free point.

/**
 * @param {{ scene: object, ray: object, view: { camera: object, width: number, height: number },
 *   pointer: { x: number, y: number }, filter: readonly string[], free?: boolean,
 *   facts?: (hit: { id: string }) => object | null }} options
 *   `pointer`: where the pointer is, in CSS pixels from the viewport's top-left (`usePointerPick`'s);
 *   `facts`: the engine's facts of an element, where they are in (`xbfMeasureEntity`).
 * @returns {object | null}  The pick (`measurement.js`'s), or null: nothing Measure takes there.
 */
export function xbfMeasurePick({ scene, ray, view, pointer, filter, free = false, facts = () => null }) {
  if (!scene || !ray || !view?.camera) return null;
  if (free || !filter.length) {
    const hit = scene.pick(ray);
    return hit ? { point: hit.point.slice(0, 3), snapKind: "free", referenceId: "", reference: null, geometry: null } : null;
  }
  const entity = hit => (hit ? xbfMeasureEntity(scene, hit, { facts: facts(hit) }) : null);
  const pick = entity(scene.pickElement(ray, view, { faces: filter.includes("face"), edges: filter.includes("edge") || filter.includes("vertex") }));
  if (!pick) return null;
  const rect = { left: 0, top: 0, width: view.width, height: view.height };
  const vertex = pick.snapKind === "edge" && filter.includes("vertex")
    ? nearestEnd(edgeEnds(pick.segments), point => projectWorldPointToClient(point, view.camera, rect), pointer) : null;
  return restrictMeasurePick(pick, filter, { vertex, face: () => entity(scene.pickElement(ray, view, { faces: true, edges: false })) });
}

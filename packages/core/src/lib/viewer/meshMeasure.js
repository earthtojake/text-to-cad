// Measure on a family's scene: a GLB, a 3MF or a robot. Such a file is triangles, with no B-rep: no
// vertex, edge or face to take whole, only a surface. So Measure there is TWO POINTS ON THE SURFACE, at
// the pointer exactly — a triangle's corner or side is the tessellation's, not the part's, and
// snapping to it would only move a point by an amount no one chose — and a length between them is
// the distance between the two points, in the file's unit (`sceneUnits.js`). It is APPROXIMATE: a
// tessellated curve's width across two facets is not its diameter, and every reading says so
// (`approximate`).
//
// Pure maths on plain arrays. A pick is the shape a STEP's Measure pick has (`measurement.js`):
// `{ point, snapKind, referenceId }`, plus the units it is read in.

import { isFinitePoint } from "./measurement.js";

/**
 * Where a Measure pick lands on `hit`: the point on the surface the pointer is over ("surface").
 *
 * @param {{ id: string, point: number[] } | null} hit  The scene's pick.
 * @param {import("./sceneUnits.js").SceneUnits} units
 */
export function meshMeasurePick(hit, units) {
  const point = hit?.point;
  if (!isFinitePoint(point)) return null;
  return { point: [...point], snapKind: "surface", referenceId: `${hit.id}:s`, units, approximate: true };
}

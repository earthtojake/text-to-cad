// Display normals for a triangle mesh that arrives without usable ones (STL, 3MF).
//
// three's `toCreasedNormals` smooths across edges shallower than the crease angle and keeps
// the rest hard, which is what makes a coarse cylinder read as round while a box stays a box.
//
// 30 degrees. Facets of anything meant to read as round meet at far less (a 24-segment
// cylinder: 15), so they still smooth; a chamfer meets its flat at 45 and must not. At 45 a
// chamfer's normals were averaged into the flat face beside it, and because these formats
// tessellate a flat face into long slivers, that tilt smeared across the whole face as
// radial streaks. Fully smooth normals (`computeVertexNormals` on an indexed mesh) are the
// same fault at every hard edge.
export const MESH_NORMAL_CREASE_ANGLE = Math.PI / 6;

// Above this triangle count, smooth the mesh with computeVertexNormals instead.
//
// toCreasedNormals is superlinear and dominates loading completely. Measured on so101's 13
// link meshes (322,564 triangles total, binary STL):
//
//   STL parse .............     14 ms
//   toCreasedNormals ......  14,090 ms   <- 99.9% of the load
//   computeVertexNormals ..     31 ms
//
// Per mesh the cost climbs far faster than size: 9,430 triangles took 49 ms, 53,994 took
// 3,552 ms — 5.7x the triangles for 72x the time. The whole robot went from 16.7 s to
// 0.47 s with it skipped, and the two renders are visually indistinguishable, because a
// mesh this dense has sub-pixel facets and nothing left to smooth.
//
// So the threshold keeps creasing exactly where it earns its cost: coarse meshes, where
// facets are visible AND the function is still cheap. Do not raise it without re-measuring
// — the cost is not linear in the count, and 20,000 already put a robot back at 2-5 s.
export const CREASED_NORMAL_MAX_TRIANGLES = 10000;

function triangleCount(geometry) {
  const indexCount = geometry.getIndex?.()?.count || 0;
  return (indexCount || geometry.getAttribute?.("position")?.count || 0) / 3;
}

/**
 * The geometry to display: creased normals for a coarse mesh, smooth ones for a dense one.
 * Returns a new geometry when it creased (three returns a non-indexed copy that keeps the
 * draw order, so material groups still apply); otherwise the geometry it was given.
 */
export function displayGeometryWithNormals(geometry, toCreasedNormals) {
  if (typeof toCreasedNormals === "function" && triangleCount(geometry) <= CREASED_NORMAL_MAX_TRIANGLES) {
    geometry.deleteAttribute?.("normal");
    return toCreasedNormals(geometry, MESH_NORMAL_CREASE_ANGLE);
  }
  if (!geometry.getAttribute("normal")) geometry.computeVertexNormals?.();
  return geometry;
}

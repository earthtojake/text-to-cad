/**
 * DXF flat-pattern GLB-space helpers.
 *
 * The drawing package that used to bake `preview.glb` is gone (design/
 * standalone-viewer.md Phase A): the viewer parses the `.dxf` itself and meshes
 * client-side, and the snapshot CLI meshes on demand through bin/dxf-mesh.mjs.
 * What remains here is the geometry contract both of those share: the mm->glTF
 * scale, the reference prism thickness, and the Y-up -> CAD Z-up soup expansion.
 */

/**
 * Millimetres to glTF metres. The viewer's loader multiplies by 1000 on the way back in
 * (`GLB_CAD_UNIT_SCALE`, `render/glbMeshData.js`), and cadgen's Python GLB writer applies the
 * same 0.001 (`_internal/glb_mesh_payload.py`). Writing raw millimetres would load a part at
 * 1000x its size.
 */
export const DXF_MM_TO_GLB_SCALE = 0.001;

/**
 * The thickness the prism is baked at. 1 mm so a renderer's Z scale IS the thickness in
 * millimetres, with no division to get wrong.
 */
export const DXF_PREVIEW_REFERENCE_THICKNESS_MM = 1;

/**
 * Y-up -> CAD Z-up: (x, y, z) -> (x, z, -y), scaled.
 *
 * The flat-pattern mesher builds Y-up (thickness on Y), but this GLB carries
 * cadOccurrenceId extras, and the viewer's loader reads those as "already CAD space" and
 * skips its own conversion. The drawing therefore arrived in a Z-up scene still Y-up and
 * stood on its edge. Converting HERE keeps that convention true — a GLB with occurrence
 * ids is CAD-space — instead of teaching the loader a per-format exception.
 *
 * (x, z, -y): a rotation about X, determinant +1. Handedness is not academic here --
 * (x, z, y) and (x, -z, y) both map the axes plausibly and both MIRROR the drawing, which
 * is invisible on a symmetric plate and obvious the moment the profile is lettering.
 *
 * Every soup that shares a GLB with the prism must ride this SAME conversion, or the
 * overlay lands on a different axis from the sheet it annotates.
 */
export function dxfSoupToGlbPositions(soup, { scale = DXF_MM_TO_GLB_SCALE } = {}) {
  const source = soup || new Float32Array(0);
  const positions = new Float32Array(source.length);
  for (let index = 0; index + 2 < source.length; index += 3) {
    positions[index] = source[index] * scale;
    positions[index + 1] = source[index + 2] * scale;
    positions[index + 2] = -source[index + 1] * scale;
  }
  return positions;
}

/**
 * The mesher returns an INDEXED triangle list whose vertex array also carries the edge-overlay
 * vertices (unreferenced by `indices`), and no normals. Expand to a non-indexed soup in glTF
 * metres: `writeGlb` then welds it and derives per-face normals, which both drops the
 * unreferenced tail and gives the flat pattern crisp creases.
 */
export function dxfPreviewPositions(meshData, { scale = DXF_MM_TO_GLB_SCALE } = {}) {
  const vertices = meshData?.vertices;
  const indices = meshData?.indices;
  if (!vertices?.length || !indices?.length) {
    throw new Error("DXF preview produced no triangles");
  }
  const positions = new Float32Array(indices.length * 3);
  for (let slot = 0; slot < indices.length; slot += 1) {
    const source = indices[slot] * 3;
    const target = slot * 3;
    positions[target] = vertices[source] * scale;
    positions[target + 1] = vertices[source + 2] * scale;
    positions[target + 2] = -vertices[source + 1] * scale;
  }
  return positions;
}


/**
 * The client render path's soup: CAD Z-up, in MILLIMETRES (the scene's unit),
 * skipping the glTF-metres round trip the deleted bake needed. Same axis map,
 * same reference thickness — a mesh built from this is byte-for-byte the
 * geometry the baked preview.glb decoded to.
 */
export function dxfPreviewPositionsMm(meshData) {
  return dxfPreviewPositions(meshData, { scale: 1 });
}

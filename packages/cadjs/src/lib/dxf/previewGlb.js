/**
 * Bake a DXF flat pattern into render-preset GLB bytes.
 *
 * This is the build-time half of the DXF render path: `buildDxfPreviewMeshData` is reused
 * VERBATIM as an input (it is ~1,300 lines of meshing nobody is rewriting), and its output is
 * handed to the shared `writeGlb`. Once the package carries `preview.glb` the browser stops
 * parsing and extruding DXF at open time -- the viewport is fed a GLB like every other entry.
 *
 * It lives in `src/` rather than in `bin/dxf-artifact.mjs` so it is testable without spawning
 * a process: the builder script owns argv, file IO and the NDJSON protocol, and this owns the
 * geometry.
 *
 * **Baked flat, at a REFERENCE thickness.** The unfolded pattern is a prism: the 2D profile
 * swept perpendicular. That is the whole reason thickness need not be baked -- stretching a
 * prism along its sweep axis is exact, moving the walls and leaving the caps and holes
 * untouched in XY, and normals are invariant under it (wall normals stay horizontal, cap
 * normals renormalise to themselves). So the bake stores a 1 mm prism and the renderer scales
 * Z by whatever thickness the user picks.
 *
 * Nothing configurable is therefore frozen here, which is the point: `preview.glb` is a cache
 * of the expensive part (parsing and meshing the profile), not a snapshot of settings that
 * would need invalidating when someone moves a slider.
 */

import { writeGlb } from "../../glb/writeGlb.js";

import {
  buildDxfPreviewMeshData,
  extractOrderedDxfBendLines,
} from "./buildPreviewMesh.js";

/**
 * Millimetres to glTF metres. The viewer's loader multiplies by 1000 on the way back in
 * (`GLB_CAD_UNIT_SCALE`, `render/glbMeshData.js`), and cadgen's Python GLB writer applies the
 * same 0.001 (`_internal/glb_mesh_payload.py`). Writing raw millimetres would load a part at
 * 1000x its size.
 */
export const DXF_MM_TO_GLB_SCALE = 0.001;

/** Identity of this bake's geometry contract, recorded in the descriptor's bake block. */
// v2: CAD Z-up positions. v3: baked at a reference thickness, thickness applied at render.
// v4: $INSUNITS honored — the parser scales geometry to mm, so an inch-unit drawing's bake
// is 25.4x the one v3 produced from the same file.
export const DXF_PREVIEW_BAKE_FORMAT = "dxf-preview-glb-v4";

/**
 * The thickness the prism is baked at. 1 mm so a renderer's Z scale IS the thickness in
 * millimetres, with no division to get wrong.
 */
export const DXF_PREVIEW_REFERENCE_THICKNESS_MM = 1;

/**
 * The mesher returns an INDEXED triangle list whose vertex array also carries the edge-overlay
 * vertices (unreferenced by `indices`), and no normals. Expand to a non-indexed soup in glTF
 * metres: `writeGlb` then welds it and derives per-face normals, which both drops the
 * unreferenced tail and gives the flat pattern crisp creases.
 */
export function dxfPreviewPositions(meshData) {
  const vertices = meshData?.vertices;
  const indices = meshData?.indices;
  if (!vertices?.length || !indices?.length) {
    throw new Error("DXF preview produced no triangles");
  }
  const positions = new Float32Array(indices.length * 3);
  for (let slot = 0; slot < indices.length; slot += 1) {
    const source = indices[slot] * 3;
    const target = slot * 3;
    // Y-up -> CAD Z-up: (x, y, z) -> (x, -z, y).
    //
    // The flat-pattern mesher builds Y-up (thickness on Y), but this GLB carries
    // cadOccurrenceId extras, and the viewer's loader reads those as "already CAD space" and
    // skips its own conversion. The drawing therefore arrived in a Z-up scene still Y-up and
    // stood on its edge. Converting HERE keeps that convention true — a GLB with occurrence
    // ids is CAD-space — instead of teaching the loader a per-format exception.
    //
    // (x, z, -y): a rotation about X, determinant +1. Handedness is not academic here --
    // (x, z, y) and (x, -z, y) both map the axes plausibly and both MIRROR the drawing, which
    // is invisible on a symmetric plate and obvious the moment the profile is lettering.
    positions[target] = vertices[source] * DXF_MM_TO_GLB_SCALE;
    positions[target + 1] = vertices[source + 2] * DXF_MM_TO_GLB_SCALE;
    positions[target + 2] = -vertices[source + 1] * DXF_MM_TO_GLB_SCALE;
  }
  return positions;
}

/**
 * `dxfData` (from `parseDxf`) -> `{ bytes, stats }`, where `bytes` is a render-preset GLB.
 *
 * `encoder` is meshoptimizer's `MeshoptEncoder`, already awaited on `.ready`; the render
 * preset requires it. There is no thickness parameter: the prism is baked at
 * `DXF_PREVIEW_REFERENCE_THICKNESS_MM` and scaled at render time.
 */
export function buildDxfPreviewGlb(dxfData, { encoder, name = "drawing" } = {}) {
  const meshData = buildDxfPreviewMeshData(dxfData, DXF_PREVIEW_REFERENCE_THICKNESS_MM, null);
  const bendLines = extractOrderedDxfBendLines(dxfData);
  const positions = dxfPreviewPositions(meshData);
  const bytes = writeGlb(
    { primitives: [{ positions, name }], name, units: "mm" },
    { preset: "render", encoder, sourceKind: "dxf", occurrenceIdPrefix: "dxf" }
  );
  return {
    bytes,
    stats: {
      triangleCount: meshData.triangle_count,
      vertexCount: meshData.vertex_count,
      bounds: meshData.bounds,
      // Carried so the viewer can show a Bends tab only for drawings that HAVE bends. It is
      // a fact about the drawing, not a bake setting, so it stays out of bakeHash.
      bendLineCount: bendLines.length,
      // The fold axes, in the CAD frame this GLB is written in. A bend line is vertical in
      // the flat pattern, so after the Z-up rotation it is a line of constant X running along
      // Y -- which is all a renderer needs to fold the sheet: split the mesh at these X
      // values and rotate each strip about the one before it.
      bendAxisX: bendLines.map((bendLine) => bendLine.start[0] * DXF_MM_TO_GLB_SCALE * 1000),
    },
    meshData,
  };
}

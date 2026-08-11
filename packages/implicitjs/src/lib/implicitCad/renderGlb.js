/**
 * Bake an implicit CAD mesh into render-preset GLB bytes.
 *
 * The build-time half of the implicit render path: the mesher's triangle soup goes in, the
 * bytes the CAD Viewer loads come out. It lives in `src/` rather than in
 * `cadjs/bin/implicit-artifact.mjs` so it is testable without spawning a process -- the
 * builder script owns argv, file IO and the NDJSON protocol, and this owns the geometry.
 *
 * **One primitive, one material colour.** The shader's colour is per PIXEL and a baked mesh
 * cannot keep that. Per-vertex colours would not help: the viewer's GLB reader takes a
 * primitive's colour from its MATERIAL and returns an empty colour array
 * (`cadjs/lib/render/glbMeshData.js`), so a COLOR_0 attribute would be written and then
 * dropped. Averaging the colour field is the same degradation `export --glb` already ships,
 * so a baked model and an exported one look alike.
 */

import { weldMesh, writeGlb } from "../glb/writeGlb.js";
import { IMPLICIT_CAD_SOURCE_KIND } from "./exporters.js";
import { createImplicitCadColorEvaluator } from "./sdfEvaluator.js";

/**
 * Millimetres to glTF metres. The viewer's loader multiplies by 1000 on the way back in
 * (`GLB_CAD_UNIT_SCALE`, `cadjs/lib/render/glbMeshData.js`), and cadgen's Python GLB writer
 * applies the same 0.001 (`_internal/glb_mesh_payload.py`). Writing raw millimetres would
 * load a model at 1000x its size.
 */
export const IMPLICIT_MM_TO_GLB_SCALE = 0.001;

/**
 * The occurrence-id namespace. Keyed on the SOURCE KIND rather than the model's display name
 * so an id survives a rename -- the convention `writeGlb` documents. Imported from the
 * exporter rather than restated so a baked model and an exported one carry the same ids.
 */
export const IMPLICIT_SOURCE_KIND = IMPLICIT_CAD_SOURCE_KIND;

/** How many mesh vertices the display colour is averaged over. */
const COLOR_SAMPLE_LIMIT = 768;

function rgb01ToHex(rgb) {
  const channel = (value) => {
    const numeric = Number(value);
    const clamped = Math.min(Math.max(Number.isFinite(numeric) ? numeric : 0, 0), 1);
    return Math.round(clamped * 255).toString(16).padStart(2, "0");
  };
  return `#${channel(rgb[0])}${channel(rgb[1])}${channel(rgb[2])}`;
}


/**
 * Per-vertex colour callback for `writeGlb`, or null when the model declares no color().
 * `scale` maps the mesh's coordinate space back to CAD mm before evaluating -- the render
 * bake hands writeGlb positions already in glTF metres, and color(p) is defined over mm.
 */
function implicitVertexColorAt(model, scale) {
  if (!model?.colorSource) {
    return null;
  }
  try {
    const evaluate = createImplicitCadColorEvaluator(model);
    return (x, y, z, nx, ny, nz) => evaluate([x * scale, y * scale, z * scale], [nx, ny, nz]);
  } catch {
    return null;
  }
}

function faceNormalAt(positions, offset) {
  const ax = positions[offset], ay = positions[offset + 1], az = positions[offset + 2];
  const bx = positions[offset + 3], by = positions[offset + 4], bz = positions[offset + 5];
  const cx = positions[offset + 6], cy = positions[offset + 7], cz = positions[offset + 8];
  const ux = bx - ax, uy = by - ay, uz = bz - az;
  const vx = cx - ax, vy = cy - ay, vz = cz - az;
  const nx = uy * vz - uz * vy;
  const ny = uz * vx - ux * vz;
  const nz = ux * vy - uy * vx;
  const length = Math.hypot(nx, ny, nz);
  return length > 1e-12 ? [nx / length, ny / length, nz / length] : [0, 0, 1];
}

/**
 * One display colour for the whole mesh, averaged over the model's `color(p, normal)` field.
 *
 * The normal handed to `color()` is the TRIANGLE's geometric normal, recomputed from
 * positions: the display colour is a property of the surface and must not shift because the
 * mesh was built with smooth normals. Failure is not fatal -- a model whose colour function
 * throws still gets its geometry, in the colour the model's material declares.
 */
export function implicitDisplayColor(model, positions) {
  if (!model?.colorSource) {
    return model?.material?.color;
  }
  try {
    const colorAt = createImplicitCadColorEvaluator(model);
    const vertexCount = Math.floor(positions.length / 3);
    const stride = Math.max(1, Math.floor(vertexCount / COLOR_SAMPLE_LIMIT));
    const sum = [0, 0, 0];
    let count = 0;
    for (let vertex = 0; vertex < vertexCount; vertex += stride) {
      const offset = vertex * 3;
      const color = colorAt(
        [positions[offset], positions[offset + 1], positions[offset + 2]],
        faceNormalAt(positions, Math.floor(vertex / 3) * 9)
      );
      if (!color.every((component) => Number.isFinite(component))) {
        continue;
      }
      sum[0] += color[0];
      sum[1] += color[1];
      sum[2] += color[2];
      count += 1;
    }
    return count ? rgb01ToHex(sum.map((component) => component / count)) : model?.material?.color;
  } catch {
    return model?.material?.color;
  }
}

/** Axis-aligned bounds of a flat position array, in the array's own units. */
export function positionBounds(positions) {
  if (!positions?.length) {
    return { min: [0, 0, 0], max: [0, 0, 0] };
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < positions.length; index += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = positions[index + axis];
      if (value < min[axis]) min[axis] = value;
      if (value > max[axis]) max[axis] = value;
    }
  }
  return { min, max };
}

/**
 * Weld the mesh, THEN scale to glTF metres.
 *
 * That order matters: welding in the mesher's own units keeps the weld tolerance the one
 * `weldMesh` documents. Scaling first would divide the tolerance by 1000 along with the
 * coordinates and quietly stop merging vertices the mesher emitted as identical.
 */
export function weldImplicitMesh(mesh, { scale = IMPLICIT_MM_TO_GLB_SCALE } = {}) {
  const welded = weldMesh(mesh.positions, mesh.normals);
  const positions = new Float32Array(welded.positions.length);
  for (let index = 0; index < welded.positions.length; index += 1) {
    positions[index] = welded.positions[index] * scale;
  }
  return { positions, normals: welded.normals, indices: welded.indices, unscaled: welded.positions };
}

/**
 * `mesh` (from the implicit mesher) + `model` -> `{ bytes, stats }`, where `bytes` is a
 * render-preset GLB: welded, indexed, quantized and meshopt-compressed.
 *
 * `encoder` is meshoptimizer's `MeshoptEncoder`, already awaited on `.ready`; it is injected
 * for the same reason `writeGlb` injects it -- this module stays dependency-free.
 */
export function buildImplicitRenderGlb(mesh, { model, encoder, welded = null } = {}) {
  if (!mesh?.positions?.length) {
    throw new Error("Implicit render bake produced no triangles");
  }
  const geometry = welded || weldImplicitMesh(mesh);
  const bytes = writeGlb({
    primitives: [{
      positions: geometry.positions,
      normals: geometry.normals,
      indices: geometry.indices,
      color: implicitDisplayColor(model, mesh.positions),
      colorAt: implicitVertexColorAt(model, 1 / IMPLICIT_MM_TO_GLB_SCALE),
      name: model?.name,
    }],
    name: model?.name || "implicit-cad",
    units: model?.units || "mm",
  }, {
    preset: "render",
    encoder,
    sourceKind: IMPLICIT_SOURCE_KIND,
    units: model?.units || "mm",
    name: model?.name || "implicit-cad",
  });
  return {
    bytes,
    stats: {
      triangleCount: mesh.triangleCount ?? Math.floor(mesh.positions.length / 9),
      vertexCount: geometry.positions.length / 3,
      bytes: bytes.length,
    },
    // Model units, not glTF metres: the descriptor describes the MODEL, and every other
    // number in it (bounds, sizes) is in the units the model declares.
    bounds: positionBounds(geometry.unscaled || mesh.positions),
  };
}

/**
 * The same geometry as an EXPORT-preset GLB: welded and indexed, but unquantized,
 * uncompressed, and in the model's own units.
 *
 * This is what `gen --write` leaves beside the source, and it is deliberately NOT a copy of
 * the package's `model.glb`: that one is quantized, meshopt-compressed and in glTF metres for
 * a viewer that registers a decoder, which is the wrong file to hand a slicer. Both come from
 * ONE mesh pass, so the sibling costs an encode, not a rebake.
 */
export function buildImplicitExportGlb(mesh, { model, welded = null } = {}) {
  if (!mesh?.positions?.length) {
    throw new Error("Implicit export bake produced no triangles");
  }
  const geometry = welded || weldImplicitMesh(mesh);
  return writeGlb({
    primitives: [{
      positions: geometry.unscaled || mesh.positions,
      normals: geometry.normals,
      indices: geometry.indices,
      color: implicitDisplayColor(model, mesh.positions),
      colorAt: implicitVertexColorAt(model, 1),
      name: model?.name,
    }],
    name: model?.name || "implicit-cad",
    units: model?.units || "mm",
  }, {
    preset: "export",
    sourceKind: IMPLICIT_SOURCE_KIND,
    units: model?.units || "mm",
    name: model?.name || "implicit-cad",
  });
}

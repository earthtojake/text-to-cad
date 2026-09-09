// meshData from a .surf container (design/surface-rendering.md R2/R5).
//
// Produces the exact structure buildMeshDataFromGlbBuffer produced from a
// component GLB, so everything downstream — package composition, themes,
// the barycentric edge overlay, selection ranges — is untouched by the
// artifact swap. Geometry is tessellated client-side from exact surfaces
// (grid + clip, curvature-driven), in CAD units, de-indexed to carry the
// per-corner `_cad_edge_barycentric` / `_cad_edge_class` attributes in the
// same half-edge convention as the GLB writer (side 0 = (v1,v2),
// side 1 = (v2,v0), side 2 = (v0,v1)).

import { linearRgbToHex } from "../color.js";
import { parseSurf } from "./container.js";
import { tessellateComponent } from "./tessellate.js";

// Mirror of cadgen's STEP_EDGE_SURFACE_CLASS_CODES.
const SURFACE_CLASS_CODES = {
  none: 0,
  feature: 1,
  tangent: 2,
  seam: 3,
  degenerate: 4,
  boundary: 5,
  nonManifold: 6,
  unknown: 7,
};

export function buildMeshDataFromSurf(index, floats, options = {}) {
  const component = options.component || tessellateComponent(index, floats, options);
  const triangleCount = component.indices.length / 3;
  const vertexCount = triangleCount * 3;

  const vertices = new Float32Array(vertexCount * 3);
  const normals = new Float32Array(vertexCount * 3);
  const indices = new Uint32Array(vertexCount);
  const surfaceEdgeBarycentric = new Float32Array(vertexCount * 3);
  const surfaceEdgeClass = new Uint8Array(vertexCount * 3);

  const classByOrd = new Map();
  for (const edge of index.edges) {
    classByOrd.set(edge.ord, SURFACE_CLASS_CODES[edge.class] ?? 0);
  }

  const bounds = {
    min: [...component.bounds.min],
    max: [...component.bounds.max],
  };
  const BARYCENTRIC = [1, 0, 0, 0, 1, 0, 0, 0, 1];
  for (let t = 0; t < triangleCount; t += 1) {
    const sideClasses = [
      classByOrd.get(component.sideOrds[t * 3]) || 0,
      classByOrd.get(component.sideOrds[t * 3 + 1]) || 0,
      classByOrd.get(component.sideOrds[t * 3 + 2]) || 0,
    ];
    for (let corner = 0; corner < 3; corner += 1) {
      const sourceVertex = component.indices[t * 3 + corner];
      const out = (t * 3 + corner) * 3;
      vertices[out] = component.positions[sourceVertex * 3];
      vertices[out + 1] = component.positions[sourceVertex * 3 + 1];
      vertices[out + 2] = component.positions[sourceVertex * 3 + 2];
      normals[out] = component.normals[sourceVertex * 3];
      normals[out + 1] = component.normals[sourceVertex * 3 + 1];
      normals[out + 2] = component.normals[sourceVertex * 3 + 2];
      surfaceEdgeBarycentric[out] = BARYCENTRIC[corner * 3];
      surfaceEdgeBarycentric[out + 1] = BARYCENTRIC[corner * 3 + 1];
      surfaceEdgeBarycentric[out + 2] = BARYCENTRIC[corner * 3 + 2];
      surfaceEdgeClass[out] = sideClasses[0];
      surfaceEdgeClass[out + 1] = sideClasses[1];
      surfaceEdgeClass[out + 2] = sideClasses[2];
      indices[t * 3 + corner] = t * 3 + corner;
    }
  }

  // The surf's partColor is LINEAR RGBA (a build123d/OCCT Color), while
  // `part.color` is the sRGB hex the viewer decodes with new THREE.Color.
  const partColor = Array.isArray(index.partColor) ? index.partColor : null;
  const color = partColor ? linearRgbToHex(partColor) : null;
  const part = {
    id: "surf:0",
    occurrenceId: "",
    primitiveIndex: 0,
    name: "",
    label: "",
    nodeType: "part",
    color,
    opacity: partColor && Number.isFinite(partColor[3]) ? partColor[3] : 1,
    hasSourceColors: Boolean(color),
    bounds,
    vertexOffset: 0,
    vertexCount,
    triangleOffset: 0,
    triangleCount,
    edgeIndexOffset: 0,
    edgeIndexCount: 0,
  };

  return {
    vertices,
    indices,
    normals,
    surfaceEdgeBarycentric,
    surfaceEdgeClass,
    colors: new Float32Array(0),
    edge_indices: new Uint32Array(0),
    bounds,
    parts: [part],
    has_source_colors: Boolean(color),
    sourceColor: color || "",
  };
}

export function buildMeshDataFromSurfBuffer(buffer, options = {}) {
  const { index, floats } = parseSurf(buffer);
  return buildMeshDataFromSurf(index, floats, options);
}

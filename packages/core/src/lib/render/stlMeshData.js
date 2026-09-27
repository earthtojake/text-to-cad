import { displayGeometryWithNormals } from "./meshNormals.js";

function buildBoundsFromGeometry(geometry) {
  geometry.computeBoundingBox();
  const min = geometry.boundingBox?.min;
  const max = geometry.boundingBox?.max;
  if (!min || !max) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0],
    };
  }
  return {
    min: [min.x, min.y, min.z],
    max: [max.x, max.y, max.z],
  };
}

function buildDisplayGeometryFromStlGeometry(geometry, toCreasedNormals) {
  const displayGeometry = geometry.clone();
  // An STL's own normals are per facet; the display wants them smoothed or creased.
  displayGeometry.deleteAttribute?.("normal");
  const normalGeometry = displayGeometryWithNormals(displayGeometry, toCreasedNormals);
  if (normalGeometry !== displayGeometry) {
    displayGeometry.dispose?.();
  }
  return normalGeometry;
}

function buildGeometryIndices(geometry, vertexCount) {
  const indexAttribute = geometry.getIndex?.();
  if (indexAttribute?.count > 0) {
    return new Uint32Array(indexAttribute.array);
  }
  const indices = new Uint32Array(vertexCount);
  for (let index = 0; index < vertexCount; index += 1) {
    indices[index] = index;
  }
  return indices;
}

export function buildMeshDataFromStlGeometry(geometry, { toCreasedNormals } = {}) {
  const displayGeometry = buildDisplayGeometryFromStlGeometry(geometry, toCreasedNormals);
  const positions = geometry.getAttribute("position");
  const displayPositions = displayGeometry.getAttribute("position");
  const displayNormals = displayGeometry.getAttribute("normal");
  try {
    if (!positions || positions.itemSize !== 3 || !displayPositions || displayPositions.itemSize !== 3) {
      throw new Error("STL geometry is missing vertex positions");
    }
    const vertexCount = displayPositions.count;
    return {
      vertices: new Float32Array(displayPositions.array),
      indices: buildGeometryIndices(displayGeometry, vertexCount),
      normals: displayNormals?.itemSize === 3 ? new Float32Array(displayNormals.array) : new Float32Array(displayPositions.array.length),
      colors: new Float32Array(0),
      edge_indices: new Uint32Array(0),
      bounds: buildBoundsFromGeometry(geometry),
      parts: [],
      has_source_colors: false,
      sourceColor: "",
    };
  } finally {
    displayGeometry.dispose?.();
  }
}

export async function buildMeshDataFromStlBuffer(buffer) {
  const [{ STLLoader }, { toCreasedNormals }] = await Promise.all([
    import("three/examples/jsm/loaders/STLLoader.js"),
    import("three/examples/jsm/utils/BufferGeometryUtils.js"),
  ]);
  const loader = new STLLoader();
  const geometry = loader.parse(buffer);
  try {
    return buildMeshDataFromStlGeometry(geometry, { toCreasedNormals });
  } finally {
    geometry.dispose?.();
  }
}

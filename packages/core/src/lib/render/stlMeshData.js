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

const STL_NORMAL_CREASE_ANGLE = Math.PI / 4;

// Above this triangle count, smooth the mesh with computeVertexNormals instead of
// three's toCreasedNormals.
//
// toCreasedNormals welds vertices to average normals across shallow edges, which is what
// makes a coarse cylinder read as round instead of faceted. It is also superlinear, and
// dominates STL loading completely. Measured on so101's 13 link meshes (322,564 triangles
// total, binary STL, on this machine):
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
// facets are visible AND the function is still cheap (9,430 triangles = 49 ms). Faceting
// shows on a cylinder built from hundreds or a few thousand triangles, which is an order of
// magnitude below this line. Do not raise it without re-measuring — the cost is not linear
// in the count, and 20,000 already put a robot back at 2-5 s.
const STL_CREASED_NORMAL_MAX_TRIANGLES = 10000;

function shouldCreaseStlNormals(geometry) {
  const positionCount = geometry.getAttribute?.("position")?.count || 0;
  return positionCount / 3 <= STL_CREASED_NORMAL_MAX_TRIANGLES;
}

function buildDisplayGeometryFromStlGeometry(geometry, toCreasedNormals) {
  const displayGeometry = geometry.clone();
  displayGeometry.deleteAttribute?.("normal");
  const normalGeometry = typeof toCreasedNormals === "function" && shouldCreaseStlNormals(displayGeometry)
    ? toCreasedNormals(displayGeometry, STL_NORMAL_CREASE_ANGLE)
    : displayGeometry;
  if (normalGeometry !== displayGeometry) {
    displayGeometry.dispose?.();
  }
  if (!normalGeometry.getAttribute("normal")) {
    normalGeometry.computeVertexNormals?.();
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
      sourceFormat: "stl",
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

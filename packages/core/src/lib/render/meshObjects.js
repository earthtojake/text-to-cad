// A mesh file (STL, 3MF) as the viewer draws it: one three geometry per object
// (per material within an object that has several), each with its display
// normals and the one colour its source gave it. Nothing
// else: no part table, no edges, no ids. The decoded arrays are the loaders'
// (`stlMeshData.js`, `threeMfMeshData.js`), which already carry the display
// normals (`meshNormals.js`) and are parsed once per file revision, off the main
// thread where a worker exists. Geometries here are VIEWS over those arrays, so
// building a scene copies nothing and the cached decode stays shared with every
// other reader of the same file (a robot's link meshes, the headless renderer).

/**
 * @typedef {{ name: string, geometry: import("three").BufferGeometry,
 *   color: import("three").Color | null, paletteIndex: number }} MeshObject
 *   `color`: the object's source colour (linear, as authored), or null when the
 *   file gave it none and the viewer's own surface colour applies.
 *   `paletteIndex`: the object's place when a palette is cycled over the file.
 */

// A palette has always been dealt over a file's objects in the order of this key
// compared as text (`buildPartFillIndexMap`, common/cadScene.js), which is not file
// order once there are more than ten. A saved "Color by part" view keeps its colours.
function paletteKey(range, index) {
  return [String(range?.occurrenceId || ""), String(range?.id || ""), String(range?.label || range?.name || ""),
    String(index).padStart(8, "0")].join("\u0000");
}

function paletteIndices(ranges) {
  const places = new Array(ranges.length);
  ranges.map((range, index) => ({ index, key: paletteKey(range, index) }))
    .sort((left, right) => left.key.localeCompare(right.key))
    .forEach(({ index }, place) => { places[index] = place; });
  return places;
}

function view(array, start, count, stride) {
  return array.subarray(start * stride, (start + count) * stride);
}

function sequentialFrom(indices, triangleOffset, triangleCount, vertexOffset) {
  for (let slot = 0; slot < triangleCount * 3; slot += 1) {
    if (indices[triangleOffset * 3 + slot] !== vertexOffset + slot) return false;
  }
  return true;
}

function objectGeometry(THREE, meshData, range) {
  const geometry = new THREE.BufferGeometry();
  const { vertexOffset, vertexCount, triangleOffset, triangleCount } = range;
  geometry.setAttribute("position", new THREE.BufferAttribute(view(meshData.vertices, vertexOffset, vertexCount, 3), 3));
  if (meshData.normals?.length === meshData.vertices.length) {
    geometry.setAttribute("normal", new THREE.BufferAttribute(view(meshData.normals, vertexOffset, vertexCount, 3), 3));
  } else geometry.computeVertexNormals();
  // Creased normals and the 3MF reader both emit triangle soup in draw order; an
  // index that only counts upward is dropped, anything else is rebased onto the object.
  if (!sequentialFrom(meshData.indices, triangleOffset, triangleCount, vertexOffset)) {
    const source = view(meshData.indices, triangleOffset, triangleCount, 3);
    geometry.setIndex(new THREE.BufferAttribute(vertexOffset ? source.map(index => index - vertexOffset) : source, 1));
  }
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

/**
 * @param {typeof import("three")} THREE
 * @param {object} meshData  `buildMeshDataFromStlBuffer` / `buildMeshDataFrom3MfBuffer` output.
 * @returns {MeshObject[]}  In file order. Geometries belong to the caller, who disposes them;
 *   the arrays under them belong to the decode and are never written.
 */
export function buildMeshObjects(THREE, meshData) {
  const vertexCount = Math.floor((meshData?.vertices?.length || 0) / 3);
  const triangleCount = Math.floor((meshData?.indices?.length || 0) / 3);
  if (!vertexCount || !triangleCount) return [];
  const ranges = Array.isArray(meshData.parts) && meshData.parts.length
    ? meshData.parts
    : [{ name: "", vertexOffset: 0, vertexCount, triangleOffset: 0, triangleCount }];
  // Once one object is coloured the file is: the rest keep the colour their material
  // carried (a writer's default grey included) rather than the viewer's surface colour.
  const colored = meshData.has_source_colors === true && meshData.colors?.length === meshData.vertices.length;
  const places = paletteIndices(ranges);
  return ranges.map((range, index) => {
    if (!(range.vertexCount > 0 && range.triangleCount > 0)) return null;
    const at = range.vertexOffset * 3;
    return {
      name: String(range.label || range.name || ""),
      geometry: objectGeometry(THREE, meshData, range),
      color: colored ? new THREE.Color(meshData.colors[at], meshData.colors[at + 1], meshData.colors[at + 2]) : null,
      paletteIndex: places[index]
    };
  }).filter(Boolean);
}

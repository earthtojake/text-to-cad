// Named imports, never `import("three")`: a namespace import of three defeats
// Rollup's tree-shaking and drags the whole renderer (~730 kB) into every
// bundle that reaches this module -- which includes the GLB and surf WORKERS,
// where nothing else needs three at all. Three classes are all this file uses.
import { Matrix3, Matrix4, Vector3 } from "three";

const GLB_CAD_UNIT_SCALE = 1000;
const CAD_EDGE_BARYCENTRIC_ATTRIBUTE_NAMES = Object.freeze([
  "_cad_edge_barycentric",
  "_CAD_EDGE_BARYCENTRIC"
]);
const CAD_EDGE_CLASS_ATTRIBUTE_NAMES = Object.freeze([
  "_cad_edge_class",
  "_CAD_EDGE_CLASS"
]);
const GENERATED_STEP_DEFAULT_BASE_COLOR = Object.freeze([0.72, 0.72, 0.72, 1]);
const BASE_COLOR_EPSILON = 1e-6;

function createBoundsAccumulator() {
  return {
    min: [Infinity, Infinity, Infinity],
    max: [-Infinity, -Infinity, -Infinity],
  };
}

function includeBoundsPoint(bounds, x, y, z) {
  if (![x, y, z].every(Number.isFinite)) {
    return;
  }
  bounds.min[0] = Math.min(bounds.min[0], x);
  bounds.min[1] = Math.min(bounds.min[1], y);
  bounds.min[2] = Math.min(bounds.min[2], z);
  bounds.max[0] = Math.max(bounds.max[0], x);
  bounds.max[1] = Math.max(bounds.max[1], y);
  bounds.max[2] = Math.max(bounds.max[2], z);
}

function boundsFromAccumulator(bounds) {
  if (!bounds?.min?.every(Number.isFinite) || !bounds?.max?.every(Number.isFinite)) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0],
    };
  }
  return {
    min: [...bounds.min],
    max: [...bounds.max],
  };
}

function rawBaseColorFactor(rawMaterial) {
  const value = rawMaterial?.pbrMetallicRoughness?.baseColorFactor;
  return Array.isArray(value) ? value : null;
}

function colorFactorsEqual(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right)) {
    return false;
  }
  return right.every((expected, index) => (
    Math.abs(Number(left[index] ?? (index === 3 ? 1 : 0)) - expected) <= BASE_COLOR_EPSILON
  ));
}

function rawMaterialSourceColorHint(rawMaterial) {
  const value = rawMaterial?.extras?.cadSourceColor;
  return value === true || value === false ? value : null;
}

function materialSourceColorHint(material) {
  const value = material?.userData?.cadSourceColor;
  return value === true || value === false ? value : null;
}

function isGeneratedStepDefaultMaterial(rawMaterial, material) {
  return (
    colorFactorsEqual(rawBaseColorFactor(rawMaterial), GENERATED_STEP_DEFAULT_BASE_COLOR) &&
    material?.color?.getHexString?.() === "dddddd"
  );
}

function colorFromMaterial(material, useSourceColors, {
  rawMaterial = null,
  stepTopology = false
} = {}) {
  if (!useSourceColors || !material?.color) {
    return null;
  }
  const sourceColorHint = materialSourceColorHint(material) ?? rawMaterialSourceColorHint(rawMaterial);
  if (sourceColorHint === false) {
    return null;
  }
  if (stepTopology && sourceColorHint !== true && isGeneratedStepDefaultMaterial(rawMaterial, material)) {
    return null;
  }
  return {
    rgb: [material.color.r, material.color.g, material.color.b],
    hex: `#${material.color.getHexString()}`,
    opacity: materialOpacity(material, rawMaterial),
  };
}

function materialOpacity(material, rawMaterial = null) {
  const materialValue = Number(material?.opacity);
  if (Number.isFinite(materialValue)) {
    return Math.min(Math.max(materialValue, 0), 1);
  }
  const rawAlpha = rawBaseColorFactor(rawMaterial)?.[3];
  const rawValue = Number(rawAlpha);
  return Number.isFinite(rawValue) ? Math.min(Math.max(rawValue, 0), 1) : 1;
}

function materialForGroup(material, group) {
  if (Array.isArray(material)) {
    const materialIndex = Number.isInteger(group?.materialIndex) ? group.materialIndex : 0;
    return material[materialIndex] || material[0] || null;
  }
  return material || null;
}

function materialIndexForGroup(group) {
  return Number.isInteger(group?.materialIndex) ? group.materialIndex : 0;
}

function rawMaterialForGroup(rawMaterials, group) {
  if (!Array.isArray(rawMaterials) || rawMaterials.length <= 0) {
    return null;
  }
  return rawMaterials[materialIndexForGroup(group)] || rawMaterials[0] || null;
}

function isBuild123dAxisCorrectionMatrix(matrix) {
  const elements = matrix?.elements;
  if (!Array.isArray(elements) && !(elements instanceof Float32Array)) {
    return false;
  }
  const expected = [
    1, 0, 0, 0,
    0, 0, -1, 0,
    0, 1, 0, 0,
    0, 0, 0, 1,
  ];
  return expected.every((value, index) => Math.abs(Number(elements[index]) - value) < 1e-6);
}

function buildGlbCadRootCorrection(scene) {
  scene?.updateWorldMatrix?.(true, true);
  const children = Array.isArray(scene?.children) ? scene.children : [];
  if (children.length !== 1 || !isBuild123dAxisCorrectionMatrix(children[0]?.matrixWorld)) {
    return null;
  }
  return new Matrix4().copy(children[0].matrixWorld).invert();
}

function cadOccurrenceIdForObject(object) {
  let current = object || null;
  while (current) {
    const rawOccurrenceId = String(current.userData?.cadOccurrenceId || "").trim();
    if (rawOccurrenceId) {
      return rawOccurrenceId;
    }
    current = current.parent || null;
  }
  const objectName = String(object?.name || "").trim();
  return /^o\d+(?:\.\d+)*$/.test(objectName) ? objectName : "";
}

/**
 * The coordinate space this GLB DECLARES, or "" when it declares none.
 *
 * `cadUpAxis` is written into node extras by `glb/writeGlb.js` (GLTFLoader copies extras
 * into `userData`), so a cadgen-written GLB says outright whether its positions are glTF
 * Y-up or already CAD Z-up. That replaces an inference that was not merely weak but FALSE:
 * the old test was "does any node carry a cadOccurrenceId", and both writer presets stamp
 * that id on every node they write, in BOTH spaces — packageMeshExport writes Y-up, and
 * bin/dxf-mesh.mjs writes Z-up. So the proxy answered "already CAD space" for every file
 * cadgen produced, the Y-up correction was skipped, and models rendered at the right size
 * rotated -90 degrees about X — on their side.
 *
 * Returns the first declaration found; a GLB mixing spaces across nodes is not a thing any
 * writer produces, and the alternative (per-node spaces) would have to be plumbed through
 * every primitive rather than decided once for the file.
 */
function declaredCadUpAxis(scene) {
  let declared = "";
  scene?.traverse?.((object) => {
    if (declared) {
      return;
    }
    const raw = String(object?.userData?.cadUpAxis || "").trim().toLowerCase();
    if (raw === "y" || raw === "z") {
      declared = raw;
    }
  });
  return declared;
}

function cadVectorFromGlbVector(vector, convertYUpToCad) {
  const x = vector.x * GLB_CAD_UNIT_SCALE;
  const y = vector.y * GLB_CAD_UNIT_SCALE;
  const z = vector.z * GLB_CAD_UNIT_SCALE;
  return convertYUpToCad
    ? { x, y: -z, z: y }
    : { x, y, z };
}

function sourceIndexForSlot(indexAttribute, slot) {
  return indexAttribute ? indexAttribute.getX(slot) : slot;
}

function geometryAttributeByName(geometry, names) {
  for (const name of names) {
    const attribute = geometry?.getAttribute?.(name);
    if (attribute) {
      return attribute;
    }
  }
  return null;
}

function isValidTriangleSource(positions, indexAttribute, sourceStart) {
  for (let offset = 0; offset < 3; offset += 1) {
    const sourceIndex = sourceIndexForSlot(indexAttribute, sourceStart + offset);
    if (sourceIndex < 0 || sourceIndex >= positions.count) {
      return false;
    }
  }
  return true;
}

function countPrimitiveOutputVertices(positions, indexAttribute, sourceStart, triangleVertexCount) {
  let vertexCount = 0;
  for (let localIndex = 0; localIndex < triangleVertexCount; localIndex += 3) {
    if (isValidTriangleSource(positions, indexAttribute, sourceStart + localIndex)) {
      vertexCount += 3;
    }
  }
  return vertexCount;
}

function inspectGlbPrimitive(
  mesh,
  group,
  material,
  useSourceColors,
  rootCorrection,
  convertYUpToCad,
  primitiveIndex = 0,
  partIndex = 0,
  { rawMaterial = null, stepTopology = false } = {}
) {
  const geometry = mesh?.geometry;
  const positions = geometry?.getAttribute?.("position");
  if (!positions || positions.itemSize !== 3 || positions.count <= 0) {
    return null;
  }
  mesh.updateWorldMatrix?.(true, false);
  const matrixWorld = mesh.matrixWorld
    ? (
      rootCorrection
        ? new Matrix4().multiplyMatrices(rootCorrection, mesh.matrixWorld)
        : new Matrix4().copy(mesh.matrixWorld)
    )
    : null;
  const normalMatrix = matrixWorld ? new Matrix3().getNormalMatrix(matrixWorld) : null;
  const normals = geometry.getAttribute("normal");
  const surfaceEdgeBarycentric = geometryAttributeByName(geometry, CAD_EDGE_BARYCENTRIC_ATTRIBUTE_NAMES);
  const surfaceEdgeClass = geometryAttributeByName(geometry, CAD_EDGE_CLASS_ATTRIBUTE_NAMES);
  const indexAttribute = geometry.getIndex?.();
  const sourceStart = Math.max(0, Math.floor(Number(group?.start || 0)));
  const availableCount = indexAttribute?.count || positions.count;
  const rawCount = Math.floor(Number(group?.count || (availableCount - sourceStart)));
  const sourceCount = Math.max(0, Math.min(rawCount, availableCount - sourceStart));
  const triangleVertexCount = sourceCount - (sourceCount % 3);
  if (triangleVertexCount <= 0) {
    return null;
  }
  const vertexCount = countPrimitiveOutputVertices(positions, indexAttribute, sourceStart, triangleVertexCount);
  const triangleCount = Math.floor(vertexCount / 3);
  if (vertexCount <= 0 || triangleCount <= 0) {
    return null;
  }

  const color = colorFromMaterial(material, useSourceColors, {
    rawMaterial,
    stepTopology
  });
  const cadOccurrenceId = cadOccurrenceIdForObject(mesh);
  const label = String(cadOccurrenceId || mesh?.name || mesh?.parent?.name || `glb:${partIndex}`).trim();
  const id = cadOccurrenceId || `glb:${partIndex}`;
  return {
    mesh,
    positions,
    normals,
    surfaceEdgeBarycentric,
    surfaceEdgeClass,
    indexAttribute,
    sourceStart,
    triangleVertexCount,
    matrixWorld,
    normalMatrix,
    convertYUpToCad,
    id,
    occurrenceId: id,
    primitiveIndex: Math.max(0, Math.floor(Number(primitiveIndex) || 0)),
    name: label || id,
    label: label || id,
    color: color?.hex || "",
    opacity: color ? color.opacity : 1,
    hasSourceColors: Boolean(color),
    vertexCount,
    triangleCount,
  };
}

function writeGlbPrimitive(descriptor, output, offsets) {
  const partBounds = createBoundsAccumulator();
  const positionVector = new Vector3();
  const normalVector = new Vector3();
  const vertexOffset = offsets.vertexOffset;
  const triangleOffset = Math.floor(offsets.indexOffset / 3);
  let localVertexCount = 0;

  for (let localIndex = 0; localIndex < descriptor.triangleVertexCount; localIndex += 3) {
    if (!isValidTriangleSource(
      descriptor.positions,
      descriptor.indexAttribute,
      descriptor.sourceStart + localIndex
    )) {
      continue;
    }
    for (let triangleOffsetIndex = 0; triangleOffsetIndex < 3; triangleOffsetIndex += 1) {
      const sourceSlot = descriptor.sourceStart + localIndex + triangleOffsetIndex;
      const sourceIndex = sourceIndexForSlot(descriptor.indexAttribute, sourceSlot);
      const outputVertexIndex = vertexOffset + localVertexCount;
      const outputComponentIndex = outputVertexIndex * 3;
      positionVector.set(
        descriptor.positions.getX(sourceIndex),
        descriptor.positions.getY(sourceIndex),
        descriptor.positions.getZ(sourceIndex)
      );
      if (descriptor.matrixWorld) {
        positionVector.applyMatrix4(descriptor.matrixWorld);
      }
      const cadPosition = cadVectorFromGlbVector(positionVector, descriptor.convertYUpToCad);
      const x = cadPosition.x;
      const y = cadPosition.y;
      const z = cadPosition.z;
      output.vertices[outputComponentIndex] = x;
      output.vertices[outputComponentIndex + 1] = y;
      output.vertices[outputComponentIndex + 2] = z;
      includeBoundsPoint(partBounds, x, y, z);
      includeBoundsPoint(output.bounds, x, y, z);

      if (output.colors && descriptor.colorsAttribute && sourceIndex < descriptor.colorsAttribute.count) {
        // getX/Y/Z denormalize USHORT-normalized attributes; values stay LINEAR, which is
        // what the viewer's vertex-colour material path expects.
        output.colors[outputComponentIndex] = descriptor.colorsAttribute.getX(sourceIndex);
        output.colors[outputComponentIndex + 1] = descriptor.colorsAttribute.getY(sourceIndex);
        output.colors[outputComponentIndex + 2] = descriptor.colorsAttribute.getZ(sourceIndex);
      }

      if (descriptor.normals?.itemSize === 3 && sourceIndex < descriptor.normals.count) {
        normalVector.set(
          descriptor.normals.getX(sourceIndex),
          descriptor.normals.getY(sourceIndex),
          descriptor.normals.getZ(sourceIndex)
        );
        if (descriptor.normalMatrix) {
          normalVector.applyMatrix3(descriptor.normalMatrix).normalize();
        }
        const cadNormal = descriptor.convertYUpToCad
          ? { x: normalVector.x, y: -normalVector.z, z: normalVector.y }
          : normalVector;
        output.normals[outputComponentIndex] = cadNormal.x;
        output.normals[outputComponentIndex + 1] = cadNormal.y;
        output.normals[outputComponentIndex + 2] = cadNormal.z;
      }
      if (output.surfaceEdgeBarycentric && descriptor.surfaceEdgeBarycentric?.itemSize === 3 && sourceIndex < descriptor.surfaceEdgeBarycentric.count) {
        output.surfaceEdgeBarycentric[outputComponentIndex] = descriptor.surfaceEdgeBarycentric.getX(sourceIndex);
        output.surfaceEdgeBarycentric[outputComponentIndex + 1] = descriptor.surfaceEdgeBarycentric.getY(sourceIndex);
        output.surfaceEdgeBarycentric[outputComponentIndex + 2] = descriptor.surfaceEdgeBarycentric.getZ(sourceIndex);
      }
      if (output.surfaceEdgeClass && descriptor.surfaceEdgeClass?.itemSize === 3 && sourceIndex < descriptor.surfaceEdgeClass.count) {
        output.surfaceEdgeClass[outputComponentIndex] = descriptor.surfaceEdgeClass.getX(sourceIndex);
        output.surfaceEdgeClass[outputComponentIndex + 1] = descriptor.surfaceEdgeClass.getY(sourceIndex);
        output.surfaceEdgeClass[outputComponentIndex + 2] = descriptor.surfaceEdgeClass.getZ(sourceIndex);
      }
      output.indices[offsets.indexOffset + localVertexCount] = outputVertexIndex;
      localVertexCount += 1;
    }
  }

  const triangleCount = Math.floor(localVertexCount / 3);
  const part = {
    id: descriptor.id,
    occurrenceId: descriptor.occurrenceId,
    primitiveIndex: descriptor.primitiveIndex,
    name: descriptor.name,
    label: descriptor.label,
    nodeType: "part",
    color: descriptor.color,
    opacity: descriptor.opacity,
    hasSourceColors: descriptor.hasSourceColors,
    bounds: boundsFromAccumulator(partBounds),
    vertexOffset,
    vertexCount: localVertexCount,
    triangleOffset,
    triangleCount,
    edgeIndexOffset: 0,
    edgeIndexCount: 0,
  };

  offsets.vertexOffset += localVertexCount;
  offsets.indexOffset += triangleCount * 3;
  return part;
}

function buildMeshDataFromGltf(gltf) {
  const declaredMaterials = Array.isArray(gltf?.parser?.json?.materials) && gltf.parser.json.materials.length > 0;
  const rawMaterials = Array.isArray(gltf?.parser?.json?.materials) ? gltf.parser.json.materials : [];
  const rootCorrection = buildGlbCadRootCorrection(gltf?.scene);
  const hasStepTopology = !!gltf?.parser?.json?.extensions?.STEP_topology;
  // Honour a declaration; fall back to the glTF SPEC when there is none.
  //
  // `declared` is what the writer said (see declaredCadUpAxis). Files that predate the
  // field — every GLB already on disk, and every foreign one — declare nothing and take
  // the fallback: glTF is Y-up by definition, so an undeclared file is converted unless
  // it carries STEP topology, whose payload is authored in CAD space already.
  //
  // `rootCorrection` vetoes in BOTH branches. It exists only when the file itself carries
  // an explicit build123d axis-correction node, which the loader inverts and applies to
  // the geometry; rotating on top of that would correct twice.
  const declared = declaredCadUpAxis(gltf?.scene);
  const convertYUpToCad = !rootCorrection && (declared ? declared === "y" : !hasStepTopology);
  const descriptors = [];
  const colorSet = new Set();
  let totalVertexCount = 0;
  let totalIndexCount = 0;
  let hasSurfaceEdgeAttributes = false;
  const nextPrimitiveIndexByOccurrence = new Map();
  gltf?.scene?.traverse?.((object) => {
    if (!object?.isMesh || !object.geometry) {
      return;
    }
    const occurrenceId = cadOccurrenceIdForObject(object) || String(object?.name || `glb:${descriptors.length}`).trim();
    const primitiveIndexBase = nextPrimitiveIndexByOccurrence.get(occurrenceId) || 0;
    const groups = Array.isArray(object.geometry.groups) && object.geometry.groups.length
      ? object.geometry.groups
      : [null];
    groups.forEach((group, primitiveIndex) => {
      const descriptor = inspectGlbPrimitive(
        object,
        group,
        materialForGroup(object.material, group),
        declaredMaterials,
        rootCorrection,
        convertYUpToCad,
        primitiveIndexBase + primitiveIndex,
        descriptors.length,
        {
          rawMaterial: rawMaterialForGroup(rawMaterials, group),
          stepTopology: hasStepTopology
        }
      );
      if (!descriptor) {
        return;
      }
      descriptor.colorsAttribute = object.geometry.getAttribute?.("color") || null;
      // COLOR_0 is a source colour too: a vertex-coloured GLB with no (or a default
      // white) material must still render its ramp, so the part flags itself even
      // when no material declared a colour.
      descriptor.hasSourceColors = descriptor.hasSourceColors || Boolean(descriptor.colorsAttribute);
      descriptors.push(descriptor);
      totalVertexCount += descriptor.vertexCount;
      totalIndexCount += descriptor.triangleCount * 3;
      hasSurfaceEdgeAttributes ||= Boolean(descriptor.surfaceEdgeBarycentric && descriptor.surfaceEdgeClass);
      if (descriptor.color) {
        colorSet.add(descriptor.color.toLowerCase());
      }
    });
    nextPrimitiveIndexByOccurrence.set(occurrenceId, primitiveIndexBase + groups.length);
  });
  const vertices = new Float32Array(totalVertexCount * 3);
  const indices = new Uint32Array(totalIndexCount);
  const normals = new Float32Array(totalVertexCount * 3);
  const surfaceEdgeBarycentric = hasSurfaceEdgeAttributes
    ? new Float32Array(totalVertexCount * 3)
    : null;
  const surfaceEdgeClass = hasSurfaceEdgeAttributes
    ? new Uint8Array(totalVertexCount * 3)
    : null;
  const parts = [];
  const output = {
    vertices,
    indices,
    normals,
    surfaceEdgeBarycentric,
    surfaceEdgeClass,
    bounds: createBoundsAccumulator(),
  };
  // Vertex colours ride the same de-index walk as positions/normals; absent everywhere,
  // the empty array keeps the old shape.
  const colorsOut = descriptors.some((d) => d.colorsAttribute)
    ? new Float32Array(totalVertexCount * 3)
    : null;
  output.colors = colorsOut;
  const offsets = {
    vertexOffset: 0,
    indexOffset: 0,
  };
  for (const descriptor of descriptors) {
    parts.push(writeGlbPrimitive(descriptor, output, offsets));
  }
  const colors = colorsOut || new Float32Array(0);
  return {
    vertices,
    indices,
    normals,
    surfaceEdgeBarycentric: surfaceEdgeBarycentric || new Float32Array(0),
    surfaceEdgeClass: surfaceEdgeClass || new Uint8Array(0),
    colors,
    edge_indices: new Uint32Array(0),
    bounds: boundsFromAccumulator(output.bounds),
    parts,
    has_source_colors: colorSet.size > 0 || descriptors.some((d) => d.colorsAttribute),
    sourceColor: colorSet.size === 1 ? [...colorSet][0] : "",
  };
}

function parseGlb(GLTFLoader, decoder, buffer) {
  const loader = new GLTFLoader();
  // Render-artifact packages are written with EXT_meshopt_compression, which is what makes a
  // 66 MB mesh ship at a few MB. It is a REQUIRED extension, so without the decoder
  // registered GLTFLoader rejects the file outright -- registering it here rather than at each
  // call site is why the worker needs no separate wiring: it loads through this same function.
  // KHR_mesh_quantization needs nothing; three's loader supports it natively.
  if (decoder) {
    loader.setMeshoptDecoder(decoder);
  }
  return new Promise((resolve, reject) => {
    loader.parse(buffer, "", resolve, reject);
  });
}

/** meshoptimizer's decoder, ready to hand to GLTFLoader. Loaded once per realm. */
let meshoptDecoderPromise = null;

function loadMeshoptDecoder() {
  if (!meshoptDecoderPromise) {
    // The decoder subpath, not the package root: the root re-exports the encoder,
    // simplifier and clusterizer too, each carrying its own embedded wasm (~120 kB
    // together, ~30 kB for the decoder alone), and a namespace import keeps them all.
    meshoptDecoderPromise = import("meshoptimizer/decoder")
      .then(async ({ MeshoptDecoder }) => {
        await MeshoptDecoder.ready;
        return MeshoptDecoder;
      })
      // An uncompressed GLB must still load if the decoder is unavailable for any reason;
      // only a meshopt-compressed one fails, and it fails loudly in GLTFLoader.
      .catch(() => null);
  }
  return meshoptDecoderPromise;
}

export async function buildMeshDataFromGlbBuffer(buffer) {
  const [{ GLTFLoader }, decoder] = await Promise.all([
    import("three/examples/jsm/loaders/GLTFLoader.js"),
    loadMeshoptDecoder(),
  ]);
  const gltf = await parseGlb(GLTFLoader, decoder, buffer);
  return buildMeshDataFromGltf(gltf);
}

// Named imports, never `import("three")`: a namespace import of three defeats
// Rollup's tree-shaking and drags the whole renderer (~730 kB) into every
// bundle that reaches this module -- which includes the GLB and part WORKERS,
// where nothing else needs three at all. Three classes are all this file uses.
import { AnimationMixer, LoadingManager, Box3, Group, LoopOnce, Matrix3, Matrix4, Vector3 } from "three";

import { isOccurrenceToken } from "../cadRefs.js";

const GLB_CAD_UNIT_SCALE = 1000;

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

function rawMaterialSourceColorHint(rawMaterial) {
  const value = rawMaterial?.extras?.cadSourceColor;
  return value === true || value === false ? value : null;
}

function materialSourceColorHint(material) {
  const value = material?.userData?.cadSourceColor;
  return value === true || value === false ? value : null;
}

function colorFromMaterial(material, useSourceColors, { rawMaterial = null } = {}) {
  if (!useSourceColors || !material?.color) {
    return null;
  }
  const sourceColorHint = materialSourceColorHint(material) ?? rawMaterialSourceColorHint(rawMaterial);
  if (sourceColorHint === false) {
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
  return isOccurrenceToken(objectName) ? objectName : "";
}

function authoredGlbNameForObject(object) {
  for (let current = object; current; current = current.parent) {
    // GLTFLoader retains the original node name here, before sanitizing the
    // Three object name. Unnamed meshes receive generated names instead.
    const name = String(current.userData?.name || "").trim();
    if (name) return name;
  }
  return "";
}

/**
 * The coordinate space this GLB DECLARES, or "" when it declares none.
 *
 * `cadUpAxis` is written into node extras by cadgen's GLB writer (GLTFLoader copies extras
 * into `userData`), so a cadgen-written GLB says outright whether its positions are glTF
 * Y-up or already CAD Z-up. That replaces an inference that was not merely weak but FALSE:
 * the old test was "does any node carry a cadOccurrenceId", and cadgen stamps that id on
 * every node it writes, whichever space those positions are in. So the proxy
 * answered "already CAD space" for every file cadgen produced, the Y-up correction was
 * skipped, and models rendered at the right size rotated -90 degrees about X — on their
 * side.
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
  { rawMaterial = null } = {}
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

  const color = colorFromMaterial(material, useSourceColors, { rawMaterial });
  const cadOccurrenceId = cadOccurrenceIdForObject(mesh);
  const label = String(authoredGlbNameForObject(mesh) || cadOccurrenceId || mesh?.name || mesh?.parent?.name || `glb:${partIndex}`).trim();
  const id = cadOccurrenceId || `glb:${partIndex}`;
  return {
    mesh,
    positions,
    normals,
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

/** The triangle whose corners start at `at` in `output.vertices`: its unit normal on all three corners. */
function writeFlatNormal(output, at, mirrored) {
  const v = output.vertices;
  const ux = v[at + 3] - v[at], uy = v[at + 4] - v[at + 1], uz = v[at + 5] - v[at + 2];
  const wx = v[at + 6] - v[at], wy = v[at + 7] - v[at + 1], wz = v[at + 8] - v[at + 2];
  let nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
  const length = Math.hypot(nx, ny, nz);
  if (!(length > 0)) return; // a triangle of no area has no direction: its normal stays zero
  const scale = (mirrored ? -1 : 1) / length;
  nx *= scale; ny *= scale; nz *= scale;
  for (let corner = 0; corner < 9; corner += 3) {
    output.normals[at + corner] = nx;
    output.normals[at + corner + 1] = ny;
    output.normals[at + corner + 2] = nz;
  }
}

function writeGlbPrimitive(descriptor, output, offsets) {
  const partBounds = createBoundsAccumulator();
  const positionVector = new Vector3();
  const normalVector = new Vector3();
  const vertexOffset = offsets.vertexOffset;
  const triangleOffset = Math.floor(offsets.indexOffset / 3);
  let localVertexCount = 0;
  // A primitive with no normals is shaded flat, as glTF asks of a client: each triangle its own
  // normal, from its corners as placed. A mirroring placement reverses the winding (the spec's
  // rule for a negative determinant), so its cross product is turned back.
  const flat = descriptor.normals?.itemSize !== 3;
  const mirrored = flat && Boolean(descriptor.matrixWorld) && descriptor.matrixWorld.determinant() < 0;

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
      output.indices[offsets.indexOffset + localVertexCount] = outputVertexIndex;
      localVertexCount += 1;
    }
    if (flat) {
      writeFlatNormal(output, (vertexOffset + localVertexCount - 3) * 3, mirrored);
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
  // Honour a declaration; fall back to the glTF SPEC when there is none.
  //
  // The declaration is what the writer said (`declaredCadUpAxis`). A file that declares
  // nothing (every foreign one) takes the fallback: glTF is Y-up by definition, so an
  // undeclared file is converted.
  //
  // `rootCorrection` vetoes in BOTH cases. It exists only when the file itself carries
  // an explicit build123d axis-correction node, which the loader inverts and applies to
  // the geometry; rotating on top of that would correct twice.
  const convertYUpToCad = !rootCorrection && declaredCadUpAxis(gltf?.scene) !== "z";
  const descriptors = [];
  const colorSet = new Set();
  let totalVertexCount = 0;
  let totalIndexCount = 0;
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
        { rawMaterial: rawMaterialForGroup(rawMaterials, group) }
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
      if (descriptor.color) {
        colorSet.add(descriptor.color.toLowerCase());
      }
    });
    nextPrimitiveIndexByOccurrence.set(occurrenceId, primitiveIndexBase + groups.length);
  });
  const vertices = new Float32Array(totalVertexCount * 3);
  const indices = new Uint32Array(totalIndexCount);
  const normals = new Float32Array(totalVertexCount * 3);
  const parts = [];
  const output = {
    vertices,
    indices,
    normals,
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
    colors,
    edge_indices: new Uint32Array(0),
    bounds: boundsFromAccumulator(output.bounds),
    parts,
    has_source_colors: colorSet.size > 0 || descriptors.some((d) => d.colorsAttribute),
    sourceColor: colorSet.size === 1 ? [...colorSet][0] : "",
  };
}

async function parseGlb(GLTFLoader, decoder, buffer, { resources, sourceUrl = "", signal } = {}) {
  const manager = new LoadingManager();
  const urls = new Map();
  if (resources) {
    const view = new DataView(buffer);
    const binary = buffer.byteLength >= 20 && view.getUint32(0, true) === 0x46546c67;
    const jsonBytes = binary ? new Uint8Array(buffer, 20, view.getUint32(12, true)) : new Uint8Array(buffer);
    const document = JSON.parse(new TextDecoder().decode(jsonBytes));
    const references = [...new Set([...(document.buffers || []), ...(document.images || [])]
      .map(item => item.uri).filter(uri => typeof uri === "string" && !uri.startsWith("data:")))];
    let next = 0;
    try {
      const transfers = await Promise.allSettled(Array.from({ length: Math.min(6, references.length) }, async () => {
        while (next < references.length) {
          const reference = references[next++];
          const url = resources.resolveDependency(sourceUrl, reference);
          const bytes = await resources.readBytes(url, { signal, maxBytes: 64 * 1024 * 1024 });
          signal?.throwIfAborted();
          urls.set(reference, URL.createObjectURL(new Blob([bytes])));
        }
      }));
      const failed = transfers.find(result => result.status === "rejected");
      if (failed) throw failed.reason;
    } catch (error) { for (const url of urls.values()) URL.revokeObjectURL(url); throw error; }
    manager.setURLModifier(url => {
      if (urls.has(url)) return urls.get(url);
      if (url.startsWith("data:") || url.startsWith("blob:")) return url;
      throw new Error(`Unresolved glTF dependency: ${url}`);
    });
    if (!binary) buffer = new TextDecoder().decode(buffer);
  }
  const loader = new GLTFLoader(manager);
  // Render-artifact packages are written with EXT_meshopt_compression, which is what makes a
  // 66 MB mesh ship at a few MB. It is a REQUIRED extension, so without the decoder
  // registered GLTFLoader rejects the file outright -- registering it here rather than at each
  // call site is why the worker needs no separate wiring: it loads through this same function.
  // KHR_mesh_quantization needs nothing; three's loader supports it natively.
  if (decoder) {
    loader.setMeshoptDecoder(decoder);
  }
  try { return await new Promise((resolve, reject) => { loader.parse(buffer, "", resolve, reject); }); }
  finally { for (const url of urls.values()) URL.revokeObjectURL(url); }
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

export async function buildMeshDataFromGlbBuffer(buffer, options) {
  const [{ GLTFLoader }, decoder] = await Promise.all([
    import("three/examples/jsm/loaders/GLTFLoader.js"),
    loadMeshoptDecoder(),
  ]);
  const gltf = await parseGlb(GLTFLoader, decoder, buffer, options);
  return buildMeshDataFromGltf(gltf);
}

const GLTF_ANIMATION_PROPERTIES = new Set(["position", "quaternion", "scale", "morphTargetInfluences"]);

export function isPlayableGlbAnimationClip(clip) {
  return Number(clip?.duration) > 0 &&
    Array.isArray(clip?.tracks) &&
    clip.tracks.length > 0 &&
    clip.tracks.every((track) => {
      const property = String(track?.name || "").split(".").pop()?.split("[")[0] || "";
      return GLTF_ANIMATION_PROPERTIES.has(property);
    });
}

function playableGlbAnimationClips(gltf) {
  return (Array.isArray(gltf?.animations) ? gltf.animations : []).filter((clip) => (
    isPlayableGlbAnimationClip(clip)
  ));
}

function nativeCadRootMatrix(gltf) {
  const rootCorrection = buildGlbCadRootCorrection(gltf?.scene);
  const convertYUpToCad = !rootCorrection && declaredCadUpAxis(gltf?.scene) !== "z";
  const orientation = rootCorrection || (convertYUpToCad
    ? new Matrix4().makeRotationX(Math.PI / 2)
    : new Matrix4());
  return new Matrix4().makeScale(GLB_CAD_UNIT_SCALE, GLB_CAD_UNIT_SCALE, GLB_CAD_UNIT_SCALE)
    .multiply(orientation);
}

function sampledAnimatedBounds(scene, clips, cadRootMatrix) {
  const root = new Group();
  root.matrix.copy(cadRootMatrix);
  root.matrixAutoUpdate = false;
  root.add(scene);
  const union = new Box3();
  const sampleBox = new Box3();
  const mixer = new AnimationMixer(scene);
  let vertexCount = 0;
  scene.traverse((object) => { vertexCount += Number(object?.geometry?.attributes?.position?.count) || 0; });
  // Bound precise vertex transforms as well as sample count. A million-vertex
  // baked animation gets endpoints, not dozens of full CPU skinning passes.
  let remainingSamples = Math.min(256, Math.max(2, Math.floor(2_000_000 / Math.max(vertexCount, 1))));
  const includePose = () => {
    root.updateMatrixWorld(true);
    sampleBox.setFromObject(root, true);
    if (!sampleBox.isEmpty()) union.union(sampleBox);
  };
  includePose();
  for (const [clipIndex, clip] of clips.entries()) {
    const action = mixer.clipAction(clip);
    action.setLoop(LoopOnce, 1);
    action.clampWhenFinished = true;
    action.play();
    const duration = Math.max(Number(clip.duration) || 0, 0.001);
    // This is a bounded framing estimate, not an extrema proof: cubic tracks,
    // rotations, and skinning can peak between samples. A global cap prevents
    // imported baked animation with thousands of keys/clips from blocking load.
    const remainingClips = clips.length - clipIndex;
    const uniformCount = Math.min(65, Math.max(Math.floor(remainingSamples / remainingClips), 1));
    const uniformTimes = Array.from(
      { length: uniformCount },
      (_, index) => uniformCount === 1 ? duration : duration * index / (uniformCount - 1)
    );
    const times = uniformTimes.slice(0, remainingSamples);
    for (const time of times) {
      mixer.setTime(Math.min(Math.max(Number(time) || 0, 0), duration));
      includePose();
    }
    remainingSamples -= times.length;
    action.stop();
    if (remainingSamples <= 0) break;
  }
  mixer.stopAllAction();
  mixer.uncacheRoot(scene);
  scene.updateMatrixWorld(true);
  scene.removeFromParent();
  if (union.isEmpty()) return { min: [0, 0, 0], max: [0, 0, 0] };
  return { min: union.min.toArray(), max: union.max.toArray() };
}

/**
 * Say, on each native material, whether its colour is a SOURCE colour. A file with
 * no materials and a material its writer flagged (`cadSourceColor: false`) are not:
 * a viewer paints those with its own surface colour, exactly as the flattened mesh
 * path drops them. `cadSourceColor` records that shared rule. An explicit lit
 * glTF material also marks `cadAuthoredFinish`, so regular shaded views keep its
 * PBR channels; the loader's implicit material remains the viewer's fallback.
 */
function markGlbMaterials(gltf) {
  const json = gltf?.parser?.json;
  const rawMaterials = Array.isArray(json?.materials) ? json.materials : [];
  gltf?.scene?.traverse?.((object) => {
    for (const material of Array.isArray(object?.material) ? object.material : [object?.material]) {
      if (!material?.color || !material.userData) continue;
      const rawMaterial = rawMaterials[gltf.parser?.associations?.get(material)?.materials] || null;
      material.userData.cadSourceColor = Boolean(rawMaterials.length > 0 &&
        colorFromMaterial(material, true, { rawMaterial }));
      // An explicit glTF material owns its PBR finish, including Standard materials.
      // GLTFLoader's implicit no-material default still takes the viewer's finish.
      material.userData.cadAuthoredFinish = Boolean(rawMaterial && material.isMeshStandardMaterial);
    }
  });
}

// Thickness is mesh-local and Three scales its transmission ray by modelMatrix.
// Attenuation distance is world-space: convert it once alongside the native scene's
// metre-to-CAD placement, deduplicating materials shared by several meshes.
function convertGlbWorldDistances(scene, cadRootMatrix) {
  const scale = cadRootMatrix.getMaxScaleOnAxis(), seen = new Set();
  scene.traverse(object => {
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (!material || seen.has(material)) continue;
      seen.add(material);
      if (Number.isFinite(material.attenuationDistance)) material.attenuationDistance *= scale;
    }
  });
}

function nativeRestBounds(scene, cadRootMatrix) {
  const root = new Group();
  root.matrix.copy(cadRootMatrix);
  root.matrixAutoUpdate = false;
  root.add(scene);
  root.updateMatrixWorld(true);
  const box = new Box3().setFromObject(root, true);
  scene.removeFromParent();
  scene.updateMatrixWorld(true);
  if (box.isEmpty()) return { min: [0, 0, 0], max: [0, 0, 0] };
  return { min: box.min.toArray(), max: box.max.toArray() };
}

// Which glTF node each object of the scene is (`userData.gltfNode`, its index in the file's
// `nodes`), and where that node stands in the default scene's tree (`userData.gltfNodePath`,
// "1.2": the first root node's second child, counted from 1). A reference names a node by its
// index (`model.glb#n12`); Explode reads the tree's levels from the path. A mesh of several
// primitives is a group of meshes under its node's object; those meshes are no node of their own.
function markGlbNodes(gltf) {
  const json = gltf.parser?.json || {};
  const paths = new Map();
  const walk = (indices, prefix) => (Array.isArray(indices) ? indices : []).forEach((node, place) => {
    if (!Number.isInteger(node) || paths.has(node)) return;
    const path = [...prefix, place + 1];
    paths.set(node, path.join("."));
    walk(json.nodes?.[node]?.children, path);
  });
  walk(json.scenes?.[json.scene ?? 0]?.nodes, []);
  gltf.scene.traverse((object) => {
    const node = gltf.parser?.associations?.get(object)?.nodes;
    if (!Number.isInteger(node)) return;
    object.userData.gltfNode = node;
    if (paths.has(node)) object.userData.gltfNodePath = paths.get(node);
  });
}

/**
 * Parse an interactive direct GLB once, as the document a viewer shows: the
 * native hierarchy (nodes, skins, morphs, authored materials), its playable
 * clips, the matrix that places it in CAD space, and two boxes in that space.
 * `restBounds` is the file as authored; `animatedBounds` (null without clips)
 * also covers every sampled pose, so a camera framed on it never clips a clip.
 * The document owns its geometry, materials and textures (`disposeGlbDocument`).
 */
export async function buildGlbDocumentFromBuffer(buffer, options) {
  const [{ GLTFLoader }, decoder] = await Promise.all([
    import("three/examples/jsm/loaders/GLTFLoader.js"),
    loadMeshoptDecoder(),
  ]);
  const gltf = await parseGlb(GLTFLoader, decoder, buffer, options);
  try {
    markGlbMaterials(gltf);
    markGlbNodes(gltf);
    const clips = playableGlbAnimationClips(gltf);
    const cadRootMatrix = nativeCadRootMatrix(gltf);
    convertGlbWorldDistances(gltf.scene, cadRootMatrix);
    const restBounds = nativeRestBounds(gltf.scene, cadRootMatrix);
    const animatedBounds = clips.length ? sampledAnimatedBounds(gltf.scene, clips, cadRootMatrix) : null;
    return {
      scene: gltf.scene,
      clips,
      cadRootMatrix: cadRootMatrix.toArray(),
      animatedBounds,
      restBounds,
    };
  } catch (error) {
    disposeGlbDocument({ scene: gltf.scene });
    throw error;
  }
}

// Scene hosts detach native GLBs when changing presentation. Detachment is not
// disposal: the document retains geometry, material and texture ownership for
// the next mode toggle.
export function detachGlbDocumentScene(document) {
  document?.scene?.removeFromParent?.();
}

/** Release resources owned by one uncached interactive GLB document. */
export function disposeGlbDocument(document) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  const images = new Set();
  const skeletons = new Set();
  document?.scene?.traverse?.((object) => {
    if (object?.geometry) geometries.add(object.geometry);
    if (object?.skeleton) skeletons.add(object.skeleton);
    const values = Array.isArray(object?.material) ? object.material : [object?.material];
    for (const material of values) {
      if (!material) continue;
      materials.add(material);
      for (const value of Object.values(material)) {
        if (value?.isTexture) {
          textures.add(value);
          if (value.source?.data) images.add(value.source.data);
        }
      }
    }
  });
  for (const geometry of geometries) geometry.dispose?.();
  for (const skeleton of skeletons) skeleton.dispose?.();
  for (const material of materials) material.dispose?.();
  for (const texture of textures) texture.dispose?.();
  for (const image of images) image.close?.();
  detachGlbDocumentScene(document);
}

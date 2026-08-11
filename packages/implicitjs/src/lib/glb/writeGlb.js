/**
 * The one JS GLB writer.
 *
 * Replaces `meshToGlb`, which emitted a single non-indexed f32 primitive at 72 B/triangle --
 * fine for a download, ruinous for a render artifact. This writer is a generic mesh
 * serializer with no implicit-specific behaviour, which is why it lives in implicitjs and is
 * re-exported by cadjs (the repo's dependency rule: shared primitives source in implicitjs,
 * cadjs re-exports; cadjs may depend on implicitjs, never the reverse).
 *
 * **It is PURE and LOCK-FREE.** Writing a render *package* is a different operation with a
 * different precondition -- it must hold the artifact's generation lock -- and lives in
 * `writeRenderPackage`. Conflating them would make every ordinary `export --glb`, which
 * holds no lock and has no run id, throw.
 *
 * ## Presets
 *
 * `preset: "render"` -- indexed, welded, quantized, meshopt-compressed. For artifacts the
 * CAD Viewer loads; the viewer registers the decoder.
 *
 * `preset: "export"` -- indexed and welded, but **unquantized and uncompressed**. Most
 * slicers and stock glTF importers cannot read `EXT_meshopt_compression`, and several read
 * `KHR_mesh_quantization` poorly. A shared writer with shared defaults would silently ship
 * an export nothing can open, so the export preset trades bytes for portability.
 *
 * ## Input
 *
 * ```
 * { primitives: [ { positions: Float32Array,   // non-indexed, 9 floats per triangle
 *                   normals?: Float32Array,    // same length; derived per-face when absent
 *                   color?: "#rrggbb",         // becomes a per-primitive material
 *                   occurrenceId?: string,     // extras.cadOccurrenceId, STEP convention
 *                   name?: string } ],
 *   name?: string, units?: string }
 * ```
 *
 * One node per primitive, so a caller can drive visibility per group (G-code layer
 * scrubbing) without re-meshing.
 */

import {
  boundsForPositions,
  buildGlb,
  clamp01,
  concatBytes,
  hexToRgb01,
  sanitizeName,
  srgbToLinear,
  typedArrayBytes,
} from "./bytes.js";

const COMPONENT_FLOAT = 5126;
const COMPONENT_SHORT = 5122;
const COMPONENT_BYTE = 5120;
const COMPONENT_UNSIGNED_SHORT = 5123;
const COMPONENT_UNSIGNED_INT = 5125;
const TARGET_ARRAY_BUFFER = 34962;
const TARGET_ELEMENT_ARRAY_BUFFER = 34963;
const MODE_TRIANGLES = 4;

// A primitive with at most this many vertices indexes in UNSIGNED_SHORT, halving index
// bytes. Callers that care (the toolpath builder) assert no primitive exceeds it, so a
// pathological file fails a budget test instead of silently shipping u32.
export const UNSIGNED_SHORT_VERTEX_LIMIT = 65535;

const SHORT_MAX = 32767;
const BYTE_MAX = 127;

/** Round up to the next multiple of 4 -- glTF requires 4-byte aligned accessor offsets. */
function align4(value) {
  return (value + 3) & ~3;
}

function padTo(bytes, length) {
  if (bytes.length >= length) {
    return bytes;
  }
  const padded = new Uint8Array(length);
  padded.set(bytes, 0);
  return padded;
}

/**
 * Re-lay a tightly packed VEC3 array into one padded to `stride` bytes PER ELEMENT.
 *
 * glTF requires each accessor element to be 4-byte aligned, so a VEC3/SHORT (6 bytes)
 * occupies a stride of 8 and a VEC3/BYTE (3 bytes) a stride of 4. Padding only the
 * buffer's TAIL leaves it short by `(stride - packed) * count` and hands
 * `encodeVertexBuffer(bytes, count, stride)` fewer bytes than the stride says it may read
 * -- 121,478 bytes short for positions and 60,739 for normals on a 60,739-vertex mesh.
 * The result decodes as corrupted attributes: the geometry survives well enough to keep a
 * recognisable silhouette, which is why this was invisible until a real model was rendered
 * and its surface shattered.
 */
function strideElements(packed, elementBytes, stride, count) {
  if (stride === elementBytes) {
    return padTo(packed, align4(packed.length));
  }
  const out = new Uint8Array(count * stride);
  for (let index = 0; index < count; index += 1) {
    out.set(packed.subarray(index * elementBytes, (index + 1) * elementBytes), index * stride);
  }
  return out;
}

function faceNormal(positions, offset) {
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
 * Weld a non-indexed triangle soup into indexed geometry.
 *
 * Keys on quantized position AND normal, so a crease keeps its two distinct normals instead
 * of being averaged into a smooth-shaded artefact. `weldDecimals` controls the position
 * tolerance; the default matches the mesher's own precision.
 *
 * Iteration is in source order and the key is a deterministic string, so the same input
 * always yields the same output -- content-addressed caching depends on it.
 */
export function weldMesh(positions, normals, { weldDecimals = 5 } = {}) {
  const vertexCount = Math.floor(positions.length / 3);
  const scale = 10 ** weldDecimals;
  const q = (value) => Math.round(value * scale) / scale;

  const outPositions = [];
  const outNormals = [];
  const indices = new Uint32Array(vertexCount);
  const seen = new Map();

  const hasNormals = normals && normals.length === positions.length;

  for (let triangle = 0; triangle * 9 < positions.length; triangle += 1) {
    const base = triangle * 9;
    const derived = hasNormals ? null : faceNormal(positions, base);
    for (let corner = 0; corner < 3; corner += 1) {
      const p = base + corner * 3;
      const px = positions[p], py = positions[p + 1], pz = positions[p + 2];
      const nx = hasNormals ? normals[p] : derived[0];
      const ny = hasNormals ? normals[p + 1] : derived[1];
      const nz = hasNormals ? normals[p + 2] : derived[2];
      const key = `${q(px)},${q(py)},${q(pz)},${q(nx)},${q(ny)},${q(nz)}`;
      let index = seen.get(key);
      if (index === undefined) {
        index = outPositions.length / 3;
        seen.set(key, index);
        outPositions.push(px, py, pz);
        outNormals.push(nx, ny, nz);
      }
      indices[triangle * 3 + corner] = index;
    }
  }

  return {
    positions: new Float32Array(outPositions),
    normals: new Float32Array(outNormals),
    indices: indices.subarray(0, Math.floor(positions.length / 3) * 3),
  };
}

/**
 * Quantize positions to SHORT over the primitive's own bounds.
 *
 * Returns the Int16 array plus the node-level scale/translation that maps it back, which is
 * how `KHR_mesh_quantization` preserves world placement: the accessor holds integers and the
 * NODE carries the transform.
 */
function quantizePositions(positions, bounds) {
  const count = positions.length / 3;
  const out = new Int16Array(positions.length);
  const extent = [
    Math.max(bounds.max[0] - bounds.min[0], 1e-9),
    Math.max(bounds.max[1] - bounds.min[1], 1e-9),
    Math.max(bounds.max[2] - bounds.min[2], 1e-9),
  ];
  for (let vertex = 0; vertex < count; vertex += 1) {
    for (let axis = 0; axis < 3; axis += 1) {
      const i = vertex * 3 + axis;
      const unit = (positions[i] - bounds.min[axis]) / extent[axis]; // 0..1
      out[i] = Math.max(-SHORT_MAX, Math.min(SHORT_MAX, Math.round(unit * SHORT_MAX)));
    }
  }
  return {
    array: out,
    scale: extent.map((value) => value / SHORT_MAX),
    translation: [bounds.min[0], bounds.min[1], bounds.min[2]],
  };
}

function quantizeNormals(normals) {
  const out = new Int8Array(normals.length);
  for (let index = 0; index < normals.length; index += 1) {
    out[index] = Math.max(-BYTE_MAX, Math.min(BYTE_MAX, Math.round(normals[index] * BYTE_MAX)));
  }
  return out;
}

function materialFor(color, name) {
  // sRGB in, LINEAR out: baseColorFactor is a linear quantity per the glTF spec, and the
  // authored hex is sRGB. Without the conversion every generated GLB renders too bright.
  const rgb = hexToRgb01(color).map(clamp01).map(srgbToLinear);
  return {
    name: sanitizeName(name || "material", "material"),
    doubleSided: true,
    extras: { cadSourceColor: true },
    pbrMetallicRoughness: {
      baseColorFactor: [...rgb, 1],
      roughnessFactor: 0.72,
      metallicFactor: 0.02,
    },
  };
}

/**
 * Serialize `mesh` to .glb bytes.
 *
 * `encoder` is meshoptimizer's `MeshoptEncoder`, already `await`ed on `.ready`. It is
 * injected rather than imported so this module stays dependency-free for the export preset
 * and for the browser, and so a caller that has not initialised the encoder gets a clear
 * error instead of a broken artifact.
 */
export function writeGlb(mesh, options = {}) {
  const {
    preset = "export",
    name = "model",
    units = "mm",
    weldDecimals = 5,
    encoder = null,
    occurrenceIdPrefix = null,
  } = options;

  // Namespace for cadOccurrenceId. Defaults to the source kind so ids survive a model
  // rename; falls back to the sanitized name only when neither is given.
  const occurrenceIdPrefix_ = String(
    occurrenceIdPrefix || options.sourceKind || sanitizeName(name, "model")
  );

  const render = preset === "render";
  if (render && !encoder) {
    throw new Error(
      "writeGlb: preset 'render' requires meshoptimizer's MeshoptEncoder (await MeshoptEncoder.ready)"
    );
  }

  const inputs = Array.isArray(mesh?.primitives) && mesh.primitives.length
    ? mesh.primitives
    : [{ positions: mesh?.positions, normals: mesh?.normals, color: options.color }];

  const binaryParts = [];
  const bufferViews = [];
  const accessors = [];
  const meshes = [];
  const nodes = [];
  const materials = [];
  let byteOffset = 0;

  /** Append `bytes` to the BIN chunk at a 4-byte aligned offset; return that offset. */
  const appendBytes = (bytes) => {
    const aligned = align4(byteOffset);
    if (aligned > byteOffset) {
      binaryParts.push(new Uint8Array(aligned - byteOffset));
      byteOffset = aligned;
    }
    binaryParts.push(bytes);
    const offset = byteOffset;
    byteOffset += bytes.length;
    return offset;
  };

  /** A plain, uncompressed bufferView. */
  const pushView = (bytes, target) => {
    const offset = appendBytes(bytes);
    const view = { buffer: 0, byteOffset: offset, byteLength: bytes.length };
    if (target) {
      view.target = target;
    }
    bufferViews.push(view);
    return bufferViews.length - 1;
  };

  /**
   * A meshopt-compressed bufferView.
   *
   * Per EXT_meshopt_compression the bufferView describes the DECOMPRESSED data
   * (`byteLength === count * byteStride`) and deliberately carries no `buffer`/`byteOffset`
   * of its own -- the extension object is the sole pointer to the compressed bytes. Writing
   * both is the mistake that yields a file a decoder-aware loader reads as garbage: it
   * allocates from the bufferView and fills from the extension.
   */
  const pushCompressedView = (compressed, { count, stride, mode, target }) => {
    const offset = appendBytes(compressed);
    const view = {
      byteLength: count * stride,
      byteStride: stride,
      extensions: {
        EXT_meshopt_compression: {
          buffer: 0,
          byteOffset: offset,
          byteLength: compressed.length,
          count,
          byteStride: stride,
          mode,
        },
      },
    };
    if (target) {
      view.target = target;
    }
    bufferViews.push(view);
    return bufferViews.length - 1;
  };

  for (const input of inputs) {
    const rawPositions = input?.positions instanceof Float32Array
      ? input.positions
      : new Float32Array(input?.positions || []);
    if (!rawPositions.length) {
      continue;
    }
    // ALREADY-INDEXED input passes straight through. The G-code mesher emits indexed
    // ribbon geometry with its own groups; de-indexing it just to re-weld would cost a
    // full pass and could only lose information.
    const welded = input?.indices
      ? {
        positions: rawPositions,
        normals: input.normals instanceof Float32Array && input.normals.length === rawPositions.length
          ? input.normals
          : new Float32Array(rawPositions.length),
        indices: input.indices,
      }
      : weldMesh(rawPositions, input?.normals, { weldDecimals });
    const vertexCount = welded.positions.length / 3;
    const bounds = boundsForPositions(welded.positions);

    // Per-vertex COLOR_0, evaluated on the WELDED vertices: `colorAt` is a pure function of
    // position+normal, so a welded vertex has one well-defined colour. Stored VEC4/USHORT
    // normalized (natural 8-byte stride) in LINEAR space -- glTF's contract for COLOR_0 --
    // via the same srgbToLinear the material path uses. When present, the material goes
    // WHITE, because three multiplies material colour by vertex colour.
    let colorArray = null;
    if (typeof input?.colorAt === "function") {
      colorArray = new Uint16Array(vertexCount * 4);
      for (let v = 0; v < vertexCount; v += 1) {
        const c = input.colorAt(
          welded.positions[v * 3], welded.positions[v * 3 + 1], welded.positions[v * 3 + 2],
          welded.normals[v * 3], welded.normals[v * 3 + 1], welded.normals[v * 3 + 2]
        );
        for (let k = 0; k < 3; k += 1) {
          colorArray[v * 4 + k] = Math.round(srgbToLinear(clamp01(Number(c?.[k]) || 0)) * 65535);
        }
        colorArray[v * 4 + 3] = 65535;
      }
    }

    let positionView;
    let normalView;
    let colorView = null;
    let positionAccessor;
    let normalAccessor;
    let nodeScale = null;
    let nodeTranslation = null;

    if (render) {
      const quantized = quantizePositions(welded.positions, bounds);
      // VEC3/SHORT is 6 bytes; glTF requires each element 4-byte aligned, so the accessor
      // byteStride is 8 and each element is padded. VEC3/BYTE is 3 -> 4.
      const positionBytes = strideElements(
        typedArrayBytes(quantized.array), 6, 8, vertexCount
      );
      const normalBytes = strideElements(
        typedArrayBytes(quantizeNormals(welded.normals)), 3, 4, vertexCount
      );
      positionView = pushCompressedView(
        encoder.encodeVertexBuffer(positionBytes, vertexCount, 8),
        { count: vertexCount, stride: 8, mode: "ATTRIBUTES", target: TARGET_ARRAY_BUFFER }
      );
      normalView = pushCompressedView(
        encoder.encodeVertexBuffer(normalBytes, vertexCount, 4),
        { count: vertexCount, stride: 4, mode: "ATTRIBUTES", target: TARGET_ARRAY_BUFFER }
      );
      if (colorArray) {
        colorView = pushCompressedView(
          encoder.encodeVertexBuffer(typedArrayBytes(colorArray), vertexCount, 8),
          { count: vertexCount, stride: 8, mode: "ATTRIBUTES", target: TARGET_ARRAY_BUFFER }
        );
      }
      nodeScale = quantized.scale;
      nodeTranslation = quantized.translation;
      positionAccessor = {
        bufferView: positionView,
        byteOffset: 0,
        componentType: COMPONENT_SHORT,
        count: vertexCount,
        type: "VEC3",
        // In quantized space, and normalized=false: the node transform restores world units.
        min: [0, 0, 0],
        max: [SHORT_MAX, SHORT_MAX, SHORT_MAX],
      };
      normalAccessor = {
        bufferView: normalView,
        byteOffset: 0,
        componentType: COMPONENT_BYTE,
        count: vertexCount,
        type: "VEC3",
        normalized: true,
      };
    } else {
      positionView = pushView(typedArrayBytes(welded.positions), TARGET_ARRAY_BUFFER);
      normalView = pushView(typedArrayBytes(welded.normals), TARGET_ARRAY_BUFFER);
      if (colorArray) {
        colorView = pushView(typedArrayBytes(colorArray), TARGET_ARRAY_BUFFER);
      }
      positionAccessor = {
        bufferView: positionView,
        byteOffset: 0,
        componentType: COMPONENT_FLOAT,
        count: vertexCount,
        type: "VEC3",
        min: bounds.min,
        max: bounds.max,
      };
      normalAccessor = {
        bufferView: normalView,
        byteOffset: 0,
        componentType: COMPONENT_FLOAT,
        count: vertexCount,
        type: "VEC3",
      };
    }

    const useShortIndices = vertexCount <= UNSIGNED_SHORT_VERTEX_LIMIT;
    const indexArray = useShortIndices
      ? new Uint16Array(welded.indices)
      : new Uint32Array(welded.indices);
    const indexStride = useShortIndices ? 2 : 4;
    const indexView = render
      ? pushCompressedView(
        encoder.encodeIndexBuffer(
          new Uint8Array(indexArray.buffer, indexArray.byteOffset, indexArray.byteLength),
          indexArray.length,
          indexStride
        ),
        {
          count: indexArray.length,
          stride: indexStride,
          mode: "TRIANGLES",
          target: TARGET_ELEMENT_ARRAY_BUFFER,
        }
      )
      : pushView(
        padTo(typedArrayBytes(indexArray), align4(indexArray.byteLength)),
        TARGET_ELEMENT_ARRAY_BUFFER
      );

    accessors.push(positionAccessor);
    const positionAccessorIndex = accessors.length - 1;
    accessors.push(normalAccessor);
    const normalAccessorIndex = accessors.length - 1;
    let colorAccessorIndex = null;
    if (colorArray) {
      accessors.push({
        bufferView: colorView,
        byteOffset: 0,
        componentType: COMPONENT_UNSIGNED_SHORT,
        count: vertexCount,
        type: "VEC4",
        normalized: true,
      });
      colorAccessorIndex = accessors.length - 1;
    }
    accessors.push({
      bufferView: indexView,
      byteOffset: 0,
      componentType: useShortIndices ? COMPONENT_UNSIGNED_SHORT : COMPONENT_UNSIGNED_INT,
      count: indexArray.length,
      type: "SCALAR",
    });
    const indexAccessorIndex = accessors.length - 1;

    materials.push(materialFor(colorArray ? "#ffffff" : input?.color, input?.name));
    meshes.push({
      primitives: [{
        attributes: {
          POSITION: positionAccessorIndex,
          NORMAL: normalAccessorIndex,
          ...(colorAccessorIndex === null ? {} : { COLOR_0: colorAccessorIndex }),
        },
        indices: indexAccessorIndex,
        material: materials.length - 1,
        mode: MODE_TRIANGLES,
      }],
    });
    const node = {
      mesh: meshes.length - 1,
      name: sanitizeName(input?.name || name, name),
      extras: {
        // The occurrence id is an identity NAMESPACE, so it is keyed on the source kind
        // rather than the model's display name -- "implicit-cad:0" is stable across a
        // rename, "export sphere:0" is not. A per-primitive `occurrenceId` still wins, and
        // an explicit `occurrenceIdPrefix` overrides the namespace.
        cadOccurrenceId: String(
          input?.occurrenceId
          || `${occurrenceIdPrefix_}:${nodes.length}`
        ),
        cadSourceKind: options.sourceKind || "mesh",
        cadUnits: units,
      },
    };
    if (nodeScale) {
      node.scale = nodeScale;
      node.translation = nodeTranslation;
    }
    nodes.push(node);
  }

  const extensionsUsed = [];
  if (render) {
    extensionsUsed.push("KHR_mesh_quantization", "EXT_meshopt_compression");
  }

  const gltf = {
    asset: { version: "2.0", generator: "implicitjs writeGlb" },
    scene: 0,
    scenes: [{ nodes: nodes.map((_, index) => index) }],
    nodes,
    meshes,
    materials,
    bufferViews,
    accessors,
  };
  if (extensionsUsed.length) {
    gltf.extensionsUsed = extensionsUsed;
    // Both are REQUIRED for a render artifact: a loader without them would misread the
    // integers as world units, which is worse than refusing the file.
    gltf.extensionsRequired = [...extensionsUsed];
  }
  return buildGlb(gltf, binaryParts);
}

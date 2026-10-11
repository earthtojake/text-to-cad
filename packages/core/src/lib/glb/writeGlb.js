/**
 * A small JS GLB writer, for the tests that need GLB bytes to load.
 *
 * Nothing the product ships comes out of here: cadgen writes every GLB export itself, in
 * Python. The core and UI suites use this to build the files their loaders, scenes and
 * renderers read -- a static part, an animated one, a meshopt-compressed one -- so it keeps
 * exactly the shapes those fixtures need. It is a generic, pure mesh serializer with no
 * format-specific behaviour.
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
 *                   opacity?: number,          // < 1 makes that material BLEND
 *                   material?: {               // the authored PBR FINISH, if any
 *                     roughness?, metalness?,  //   -> pbrMetallicRoughness factors
 *                     clearcoat?,              //   -> KHR_materials_clearcoat
 *                     clearcoatRoughness?,
 *                     opacity? },              //   alpha when no `opacity` is given
 *                   occurrenceId?: string,     // extras.cadOccurrenceId, STEP convention
 *                   node?: string,             // group key: same key -> same node
 *                   indices?: Uint32Array,     // already-indexed input, passed through
 *                   name?: string } ],
 *   name?: string, units?: string }
 * ```
 *
 * One node per primitive by default, so a caller can drive visibility per group (G-code
 * layer scrubbing) without re-meshing. A caller that needs a node to mean something
 * else -- one glTF node per CAD OCCURRENCE, so an animation channel has something to
 * target -- gives its primitives a shared `node` key and they become the primitives of
 * one mesh instead.
 *
 * ## Animation
 *
 * `options.animations` is `[{ name, times, channels: [{ node, times?, translation?,
 * rotation?, scale? }] }]`, where `node` is a group key from the primitives above and
 * each track is a flat Float32Array of samples (VEC3 / quaternion VEC4). One time
 * accessor is written per distinct `times` array, so a clip's channels share it.
 * `options.nodeTransforms` (a Map keyed by the same group keys) sets each node's own TRS
 * -- what the file shows when nothing is playing it. Both are export-preset only: the
 * render preset spends a node's TRS on dequantizing its one primitive.
 */

import {
  boundsForPositions,
  buildGlb,
  clamp01,
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
// bytes.
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
  const length = Math.sqrt(nx * nx + ny * ny + nz * nz);
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

// The finish a source that authored none gets. A caller supplying no `material` (and a
// channel a material omits) keeps exactly these numbers, so its bytes are unchanged.
const DEFAULT_ROUGHNESS = 0.42;
const DEFAULT_METALNESS = 0.03;

/** One PBR channel off a caller's material, clamped to [0, 1]; null when unauthored. */
function finishChannel(finish, key) {
  const value = Number(finish?.[key]);
  return Number.isFinite(value) ? clamp01(value) : null;
}

function materialFor(color, name, opacity = null, finish = null) {
  // sRGB in, LINEAR out: baseColorFactor is a linear quantity per the glTF spec, and the
  // authored hex is sRGB. Without the conversion every generated GLB renders too bright.
  // Canonical Float32 precision: exponentiation can differ by a Float64 ULP across JS
  // engines. Serializing that extra precision made identical colours produce different
  // GLB hashes on Node 22 and 26. The input has only 256 values per channel; Float32
  // preserves every one on an sRGB round trip and matches the renderer's precision.
  const rgb = hexToRgb01(color).map(clamp01).map(srgbToLinear).map(Math.fround);
  // Alpha is NOT an sRGB quantity, so it rides through unconverted. A material below
  // fully opaque also needs alphaMode: importers ignore baseColorFactor[3] in the
  // default OPAQUE mode, which would render a half-faded part solid.
  //
  // An explicit `opacity` (a caller's own override -- an animation clip's faded
  // occurrence) wins over the material's authored one; with neither, opaque.
  const authoredAlpha = finishChannel(finish, "opacity");
  const alpha = opacity === null || opacity === undefined
    ? (authoredAlpha === null ? 1 : authoredAlpha)
    : clamp01(opacity);
  // The authored FINISH, when the caller has one. Metalness especially is not a
  // decoration: a metal has no diffuse lobe, so exporting a brushed-aluminium part at
  // the plastic default inverts its shading and is why an exported file used to
  // look nothing like the same document in the viewer.
  const roughness = finishChannel(finish, "roughness");
  const metalness = finishChannel(finish, "metalness");
  const clearcoat = finishChannel(finish, "clearcoat");
  const clearcoatRoughness = finishChannel(finish, "clearcoatRoughness");
  const material = {
    name: sanitizeName(name || "material", "material"),
    doubleSided: true,
    extras: { cadSourceColor: true },
    pbrMetallicRoughness: {
      baseColorFactor: [...rgb, alpha],
      roughnessFactor: roughness === null ? DEFAULT_ROUGHNESS : roughness,
      metallicFactor: metalness === null ? DEFAULT_METALNESS : metalness,
    },
  };
  if (alpha < 1) {
    material.alphaMode = "BLEND";
  }
  // A clearcoat of 0 IS the glTF default, so an authored zero is written by leaving the
  // extension off -- the file then says the same thing in fewer bytes and never lands in
  // extensionsUsed for a coat nobody asked for.
  if (clearcoat !== null && clearcoat > 0) {
    material.extensions = {
      KHR_materials_clearcoat: {
        clearcoatFactor: clearcoat,
        ...(clearcoatRoughness === null ? {} : { clearcoatRoughnessFactor: clearcoatRoughness }),
      },
    };
  }
  return material;
}

// The three node properties a glTF sampler may drive, and the accessor each track needs.
const ANIMATION_PATHS = [
  ["translation", 3, "VEC3"],
  ["rotation", 4, "VEC4"],
  ["scale", 3, "VEC3"],
];

/**
 * `options.animations` -> the glTF `animations` array, appending its accessors and
 * bufferViews through the callers' own writers so the BIN chunk stays one stream.
 *
 * One INPUT accessor per distinct `times` array (compared by identity, which is what a
 * caller sampling every channel on one schedule hands in): a clip's channels then share
 * a single time line instead of repeating it per occurrence, and the file says out loud
 * that they are the same schedule.
 */
function buildAnimations(animations, { nodeIndexByKey, accessors, pushView }) {
  const out = [];
  for (const animation of Array.isArray(animations) ? animations : []) {
    const samplers = [];
    const channels = [];
    const timeAccessors = new Map();
    const timeAccessorFor = (times) => {
      let index = timeAccessors.get(times);
      if (index !== undefined) {
        return index;
      }
      if (!times || !times.length) {
        throw new Error("writeGlb: an animation channel needs a non-empty times array");
      }
      accessors.push({
        bufferView: pushView(typedArrayBytes(times)),
        byteOffset: 0,
        componentType: COMPONENT_FLOAT,
        count: times.length,
        type: "SCALAR",
        // REQUIRED on a sampler input by the glTF spec: a loader reads the clip's
        // duration off them rather than scanning the accessor.
        min: [times[0]],
        max: [times[times.length - 1]],
      });
      index = accessors.length - 1;
      timeAccessors.set(times, index);
      return index;
    };
    for (const channel of animation?.channels || []) {
      const node = nodeIndexByKey.get(String(channel?.node));
      if (node === undefined) {
        throw new Error(
          `writeGlb: animation channel targets node ${JSON.stringify(channel?.node)}, `
          + "which no primitive declared"
        );
      }
      const input = timeAccessorFor(channel?.times || animation?.times);
      for (const [path, stride, type] of ANIMATION_PATHS) {
        const values = channel?.[path];
        if (!values) {
          continue;
        }
        accessors.push({
          bufferView: pushView(typedArrayBytes(values)),
          byteOffset: 0,
          componentType: COMPONENT_FLOAT,
          count: values.length / stride,
          type,
        });
        samplers.push({ input, output: accessors.length - 1, interpolation: "LINEAR" });
        channels.push({ sampler: samplers.length - 1, target: { node, path } });
      }
    }
    if (channels.length) {
      out.push({ name: sanitizeName(animation?.name || "clip", "clip"), samplers, channels });
    }
  }
  return out;
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
    upAxis = "y",
    animations = null,
    nodeTransforms = null,
  } = options;

  // WHICH SPACE the caller's positions are in, declared rather than guessed. glTF's
  // own convention is Y-up, so "y" is the default and the value a spec-conformant
  // writer wants; "z" says these bytes were pre-rotated into CAD Z-up before they got
  // here, and a CAD reader must NOT rotate again.
  //
  // The reader used to infer this from the presence of a `cadOccurrenceId` extra, which
  // is written on every node by both presets and so answered "already CAD space" for
  // files that are plainly Y-up — every model loaded on its side, correctly sized. An
  // identity namespace cannot also carry orientation; the writer knows the space, so
  // the writer states it.
  const upAxis_ = String(upAxis).trim().toLowerCase();
  if (upAxis_ !== "y" && upAxis_ !== "z") {
    throw new Error(`writeGlb: upAxis must be "y" (glTF) or "z" (CAD), got ${JSON.stringify(upAxis)}`);
  }

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
  // The render preset writes each node's scale/translation to dequantize its ONE
  // primitive, so a node it did not create is a node whose geometry would land in the
  // wrong place. Refuse rather than emit an artifact that renders scrambled.
  if (render && (animations || nodeTransforms)) {
    throw new Error(
      "writeGlb: preset 'render' spends every node transform on dequantization, so it "
      + "carries no animation or node TRS — use preset 'export' for an animated file"
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
  // Node key -> the primitives that share it, in first-appearance order. An input
  // without a `node` key gets one of its own, which is the default one-node-per-
  // primitive layout expressed as the degenerate case of grouping rather than as a
  // second code path.
  const groups = new Map();
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
    // ALREADY-INDEXED input passes straight through: de-indexing it just to re-weld
    // would cost a full pass and could only lose information.
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

    let positionView;
    let normalView;
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
    accessors.push({
      bufferView: indexView,
      byteOffset: 0,
      componentType: useShortIndices ? COMPONENT_UNSIGNED_SHORT : COMPONENT_UNSIGNED_INT,
      count: indexArray.length,
      type: "SCALAR",
    });
    const indexAccessorIndex = accessors.length - 1;

    materials.push(
      materialFor(input?.color, input?.materialName || input?.name, input?.opacity ?? null, input?.material ?? null)
    );
    const primitive = {
      attributes: { POSITION: positionAccessorIndex, NORMAL: normalAccessorIndex },
      indices: indexAccessorIndex,
      material: materials.length - 1,
      mode: MODE_TRIANGLES,
    };
    // An input with no `node` key gets a group of its own. The prefix is the
    // ESCAPE `\0`, never the byte: a raw control character makes this file binary
    // to grep and ripgrep, and every later search of it would silently find
    // nothing. No occurrence id can contain it, so the key can never collide with
    // a caller's.
    const groupKey = input?.node === undefined || input?.node === null
      ? `\0primitive:${groups.size}`
      : String(input.node);
    let group = groups.get(groupKey);
    if (!group) {
      group = { key: groupKey, input, primitives: [], quantization: null };
      groups.set(groupKey, group);
    } else if (render) {
      // Quantization puts the primitive's dequantizing scale/translation on the NODE, so
      // two primitives on one node would need two different node transforms. Refuse
      // rather than write the first one's and misplace the rest.
      throw new Error(
        `writeGlb: preset 'render' cannot put two primitives on node ${JSON.stringify(groupKey)}: `
        + "each quantized primitive owns its node's transform"
      );
    }
    group.primitives.push(primitive);
    if (nodeScale) {
      group.quantization = { scale: nodeScale, translation: nodeTranslation };
    }
  }

  const nodeIndexByKey = new Map();
  for (const group of groups.values()) {
    meshes.push({ primitives: group.primitives });
    const node = {
      mesh: meshes.length - 1,
      name: sanitizeName(group.input?.name || name, name),
      extras: {
        // The occurrence id is an identity NAMESPACE, so it is keyed on the source kind
        // rather than the model's display name -- "mesh:0" is stable across a rename,
        // "export sphere:0" is not. A per-primitive `occurrenceId` still wins, and an
        // explicit `occurrenceIdPrefix` overrides the namespace.
        cadOccurrenceId: String(
          group.input?.occurrenceId
          || `${occurrenceIdPrefix_}:${nodes.length}`
        ),
        cadSourceKind: options.sourceKind || "mesh",
        cadUnits: units,
        // The DECLARED coordinate space of this node's positions. Read back by
        // render/glbMeshData.js to decide whether the Y-up -> CAD Z-up correction is
        // owed; absent (a foreign GLB, or one written before this field existed) the
        // reader falls back to the glTF spec and converts.
        cadUpAxis: upAxis_,
      },
    };
    if (group.quantization) {
      node.scale = group.quantization.scale;
      node.translation = group.quantization.translation;
    }
    const rest = nodeTransforms instanceof Map ? nodeTransforms.get(group.key) : null;
    if (rest) {
      // The pose the file shows when nothing is playing it: an animated clip's first
      // sample. A channel overrides it during playback; a node with a constant offset
      // and no channel carries it here alone.
      if (rest.translation) {
        node.translation = [...rest.translation];
      }
      if (rest.rotation) {
        node.rotation = [...rest.rotation];
      }
      if (rest.scale) {
        node.scale = [...rest.scale];
      }
    }
    nodeIndexByKey.set(group.key, nodes.length);
    nodes.push(node);
  }

  const gltfAnimations = buildAnimations(animations, { nodeIndexByKey, accessors, pushView });

  // Both quantization extensions are REQUIRED for a render artifact: a loader without
  // them would misread the integers as world units, which is worse than refusing the
  // file. KHR_materials_clearcoat is only USED -- a loader that ignores it still draws
  // the right geometry in the right colour, just without the coat, so requiring it would
  // make ordinary importers refuse a file they can very nearly read.
  const extensionsRequired = render
    ? ["KHR_mesh_quantization", "EXT_meshopt_compression"]
    : [];
  const extensionsUsed = [...extensionsRequired];
  if (materials.some((material) => material.extensions?.KHR_materials_clearcoat)) {
    extensionsUsed.push("KHR_materials_clearcoat");
  }

  const gltf = {
    // This literal is part of the canonical GLB bytes, independent of the
    // JavaScript package's distribution name.
    asset: { version: "2.0", generator: "cadgen-js writeGlb" },
    scene: 0,
    scenes: [{ nodes: nodes.map((_, index) => index) }],
    nodes,
    meshes,
    materials,
    bufferViews,
    accessors,
    ...(gltfAnimations.length ? { animations: gltfAnimations } : {}),
  };
  if (extensionsUsed.length) {
    gltf.extensionsUsed = extensionsUsed;
  }
  if (extensionsRequired.length) {
    gltf.extensionsRequired = extensionsRequired;
  }
  return buildGlb(gltf, binaryParts);
}

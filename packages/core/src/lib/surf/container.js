// SURF container parsing.
//
// A `.surf` is one component's exact topology for the clients that select,
// measure and recognize it (cadgen meshes it; nothing tessellates a `.surf`):
// `SURF` magic, u32 version, u32 JSON length, JSON index, then a single
// little-endian f32 buffer (a bilinear patch's corners). The JSON references
// float spans as `[offsetInFloats, count]` pairs.

export const SURF_MAGIC = 0x46525553; // "SURF" little-endian
// version 2: shape membership, selector-table metadata (surfaceType/
// curveType/params/classification columns), edge faceOrds.
// version 3: no tessellation inputs: loops are edge references, B-splines
// carry no control nets (a bilinear patch keeps its corners).
export const SURF_VERSION = 3;
// A store may still hold a version-2 surface an older build pinned; version 3
// only removed fields, so both read the same.
export const SURF_VERSIONS_READ = Object.freeze([2, 3]);

export function parseSurf(arrayBuffer) {
  const header = new DataView(arrayBuffer, 0, 12);
  if (header.getUint32(0, true) !== SURF_MAGIC) {
    throw new Error("not a SURF container");
  }
  const version = header.getUint32(4, true);
  if (!SURF_VERSIONS_READ.includes(version)) {
    throw new Error(`unsupported SURF version ${version}`);
  }
  const jsonLength = header.getUint32(8, true);
  const jsonBytes = new Uint8Array(arrayBuffer, 12, jsonLength);
  const index = JSON.parse(new TextDecoder().decode(jsonBytes));
  const binStart = 12 + jsonLength;
  const floats = new Float32Array(
    arrayBuffer.slice(binStart, binStart + ((arrayBuffer.byteLength - binStart) >> 2 << 2)),
  );
  return { index, floats };
}

export function floatSpan(floats, ref) {
  const [offset, count] = ref;
  return floats.subarray(offset, offset + count);
}

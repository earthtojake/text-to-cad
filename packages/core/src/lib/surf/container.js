// SURF container parsing (design/surface-rendering.md R1/R2).
//
// A `.surf` ships one component's exact B-rep geometry for client-side GPU
// tessellation: `SURF` magic, u32 version, u32 JSON length, JSON index,
// then a single little-endian f32 buffer. The JSON references float spans
// as `[offsetInFloats, count]` pairs.

export const SURF_MAGIC = 0x46525553; // "SURF" little-endian
// version 2: shape membership, selector-table metadata (surfaceType/
// curveType/params/classification columns), edge faceOrds.
export const SURF_VERSION = 2;

export function parseSurf(arrayBuffer) {
  const header = new DataView(arrayBuffer, 0, 12);
  if (header.getUint32(0, true) !== SURF_MAGIC) {
    throw new Error("not a SURF container");
  }
  const version = header.getUint32(4, true);
  if (version !== SURF_VERSION) {
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

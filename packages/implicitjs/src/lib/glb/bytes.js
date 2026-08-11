/**
 * Byte primitives and the glTF binary container.
 *
 * Extracted from implicitCad/exporters.js so the GLB writer and the exporters share ONE
 * copy. Works on both Node (`Buffer`) and the browser (`Uint8Array`) -- the same module is
 * imported by a build-time Node builder and by client code.
 */

const NativeBuffer = globalThis.Buffer;
const textEncoder = typeof TextEncoder !== "undefined" ? new TextEncoder() : null;

export function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

export function clamp01(value) {
  return Math.min(Math.max(finiteNumber(value), 0), 1);
}

export function bytesFromString(value, encoding = "utf-8") {
  if (NativeBuffer?.from) {
    return NativeBuffer.from(String(value), encoding);
  }
  if (encoding !== "utf-8" && encoding !== "utf8") {
    const text = String(value);
    const bytes = new Uint8Array(text.length);
    for (let index = 0; index < text.length; index += 1) {
      bytes[index] = text.charCodeAt(index) & 0xff;
    }
    return bytes;
  }
  return textEncoder.encode(String(value));
}

export function allocBytes(length, fill = 0) {
  if (NativeBuffer?.alloc) {
    return NativeBuffer.alloc(length, fill);
  }
  const bytes = new Uint8Array(length);
  if (fill) {
    bytes.fill(fill);
  }
  return bytes;
}

export function concatBytes(parts, totalLength = undefined) {
  if (NativeBuffer?.concat) {
    return NativeBuffer.concat(parts, totalLength);
  }
  const length = totalLength ?? parts.reduce((sum, part) => sum + part.length, 0);
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    bytes.set(part, offset);
    offset += part.length;
  }
  return bytes;
}

export function typedArrayBytes(array) {
  return new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
}

function viewFor(bytes) {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

export function writeUInt16LE(bytes, offset, value) {
  viewFor(bytes).setUint16(offset, value, true);
}

export function writeUInt32LE(bytes, offset, value) {
  viewFor(bytes).setUint32(offset, value, true);
}

export function writeFloatLE(bytes, offset, value) {
  viewFor(bytes).setFloat32(offset, value, true);
}

export function writeAscii(bytes, offset, text, maxLength) {
  const source = String(text).slice(0, maxLength);
  for (let index = 0; index < source.length; index += 1) {
    bytes[offset + index] = source.charCodeAt(index) & 0x7f;
  }
}

export function align4Buffer(buffer, fill = 0x20) {
  const padding = (4 - (buffer.length % 4)) % 4;
  return padding ? concatBytes([buffer, allocBytes(padding, fill)]) : buffer;
}

export function sanitizeName(value, fallback = "implicit-cad") {
  return String(value || fallback).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g, "-") || fallback;
}

export function boundsForPositions(positions) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < positions.length; index += 3) {
    min[0] = Math.min(min[0], positions[index]);
    min[1] = Math.min(min[1], positions[index + 1]);
    min[2] = Math.min(min[2], positions[index + 2]);
    max[0] = Math.max(max[0], positions[index]);
    max[1] = Math.max(max[1], positions[index + 1]);
    max[2] = Math.max(max[2], positions[index + 2]);
  }
  return {
    min: min.map((value) => (Number.isFinite(value) ? value : 0)),
    max: max.map((value) => (Number.isFinite(value) ? value : 0)),
  };
}

/**
 * One sRGB-encoded channel (0..1) to linear.
 *
 * glTF is explicit that `baseColorFactor` and `COLOR_0` are LINEAR, while authored hex
 * colours -- what a colour picker shows and what every model's `baseColor` param holds --
 * are sRGB-encoded. three.js reads the factor with
 * `color.setRGB(r, g, b, LinearSRGBColorSpace)`, so handing it sRGB values makes everything
 * render brighter and washed out, most visibly in the midtones.
 *
 * Kept separate from `hexToRgb01` on purpose: that function's job is "hex to 0..1", which is
 * still sRGB, and a future caller wanting sRGB should not be silently handed linear.
 */
export function srgbToLinear(component) {
  return component <= 0.04045
    ? component / 12.92
    : ((component + 0.055) / 1.055) ** 2.4;
}

export function hexToRgb01(hex, fallback = "#d4d4d8") {
  const raw = String(hex || fallback).trim();
  const value = /^#(?:[0-9a-fA-F]{3}){1,2}$/.test(raw) ? raw : fallback;
  const expanded = value.length === 4
    ? `${value[1]}${value[1]}${value[2]}${value[2]}${value[3]}${value[3]}`
    : value.slice(1);
  return [
    parseInt(expanded.slice(0, 2), 16) / 255,
    parseInt(expanded.slice(2, 4), 16) / 255,
    parseInt(expanded.slice(4, 6), 16) / 255,
  ];
}

/**
 * Wrap a glTF JSON document and its binary parts into a .glb container.
 *
 * Mutates `gltf.buffers` to declare the single BIN chunk, which is what every caller wants
 * and what the previous private copy did.
 */
export function buildGlb(gltf, binaryParts) {
  const binaryChunk = align4Buffer(concatBytes(binaryParts), 0);
  gltf.buffers = [{ byteLength: binaryChunk.length }];
  const jsonChunk = align4Buffer(bytesFromString(JSON.stringify(gltf)), 0x20);
  const totalLength = 12 + 8 + jsonChunk.length + 8 + binaryChunk.length;
  const header = allocBytes(12);
  writeUInt32LE(header, 0, 0x46546c67);
  writeUInt32LE(header, 4, 2);
  writeUInt32LE(header, 8, totalLength);
  const jsonHeader = allocBytes(8);
  writeUInt32LE(jsonHeader, 0, jsonChunk.length);
  writeUInt32LE(jsonHeader, 4, 0x4e4f534a);
  const binHeader = allocBytes(8);
  writeUInt32LE(binHeader, 0, binaryChunk.length);
  writeUInt32LE(binHeader, 4, 0x004e4942);
  return concatBytes([header, jsonHeader, jsonChunk, binHeader, binaryChunk], totalLength);
}

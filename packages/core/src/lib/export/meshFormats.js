/**
 * Low-level mesh serialization primitives shared by the package mesh exporters.
 *
 * `meshToBinaryStl` writes a binary STL (colorless by format), `xmlEscape`
 * escapes 3MF XML text, and `zipStore` builds a STORED (uncompressed) zip
 * container with a fixed DOS timestamp so the same mesh always produces the
 * same 3MF bytes.
 *
 * These are pure byte helpers: no filesystem, no three.js, no descriptor
 * knowledge. `packageMeshExport.js` owns the CAD-level assembly on top.
 */
import {
  allocBytes,
  bytesFromString,
  concatBytes,
  sanitizeName,
  writeAscii,
  writeFloatLE,
  writeUInt16LE,
  writeUInt32LE,
} from "../glb/bytes.js";

export function triangleNormal(positions, offset) {
  const ax = positions[offset];
  const ay = positions[offset + 1];
  const az = positions[offset + 2];
  const bx = positions[offset + 3];
  const by = positions[offset + 4];
  const bz = positions[offset + 5];
  const cx = positions[offset + 6];
  const cy = positions[offset + 7];
  const cz = positions[offset + 8];
  const ux = bx - ax;
  const uy = by - ay;
  const uz = bz - az;
  const vx = cx - ax;
  const vy = cy - ay;
  const vz = cz - az;
  const nx = uy * vz - uz * vy;
  const ny = uz * vx - ux * vz;
  const nz = ux * vy - uy * vx;
  const length = Math.hypot(nx, ny, nz);
  return length > 1e-12 ? [nx / length, ny / length, nz / length] : [0, 0, 1];
}

export function meshToBinaryStl(mesh, { name = "model" } = {}) {
  const positions = mesh.positions || new Float32Array();
  const triangleCount = Math.floor(positions.length / 9);
  const buffer = allocBytes(84 + triangleCount * 50);
  writeAscii(buffer, 0, `cad ${sanitizeName(name)}`, 80);
  writeUInt32LE(buffer, 80, triangleCount);
  let offset = 84;
  for (let triangle = 0; triangle < triangleCount; triangle += 1) {
    const positionOffset = triangle * 9;
    const normal = triangleNormal(positions, positionOffset);
    for (const component of normal) {
      writeFloatLE(buffer, offset, component);
      offset += 4;
    }
    for (let vertex = 0; vertex < 9; vertex += 1) {
      writeFloatLE(buffer, offset, positions[positionOffset + vertex]);
      offset += 4;
    }
    writeUInt16LE(buffer, offset, 0);
    offset += 2;
  }
  return buffer;
}

export function xmlEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function crc32(buffer) {
  let table = crc32.table;
  if (!table) {
    table = new Uint32Array(256);
    for (let index = 0; index < 256; index += 1) {
      let c = index;
      for (let bit = 0; bit < 8; bit += 1) {
        c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      }
      table[index] = c >>> 0;
    }
    crc32.table = table;
  }
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export function zipStore(files) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  // Fixed timestamp (the DOS epoch, 1980-01-01): archives are
  // byte-deterministic, so the same mesh produces the same 3MF bytes from any
  // producer at any time.
  const dosTime = 0;
  const dosDate = (1 << 5) | 1;
  for (const file of files) {
    const nameBuffer = bytesFromString(file.name);
    const body = file.body instanceof Uint8Array ? file.body : bytesFromString(String(file.body || ""));
    const crc = crc32(body);
    const local = allocBytes(30);
    writeUInt32LE(local, 0, 0x04034b50);
    writeUInt16LE(local, 4, 20);
    writeUInt16LE(local, 6, 0);
    writeUInt16LE(local, 8, 0);
    writeUInt16LE(local, 10, dosTime);
    writeUInt16LE(local, 12, dosDate);
    writeUInt32LE(local, 14, crc);
    writeUInt32LE(local, 18, body.length);
    writeUInt32LE(local, 22, body.length);
    writeUInt16LE(local, 26, nameBuffer.length);
    writeUInt16LE(local, 28, 0);
    localParts.push(local, nameBuffer, body);

    const central = allocBytes(46);
    writeUInt32LE(central, 0, 0x02014b50);
    writeUInt16LE(central, 4, 20);
    writeUInt16LE(central, 6, 20);
    writeUInt16LE(central, 8, 0);
    writeUInt16LE(central, 10, 0);
    writeUInt16LE(central, 12, dosTime);
    writeUInt16LE(central, 14, dosDate);
    writeUInt32LE(central, 16, crc);
    writeUInt32LE(central, 20, body.length);
    writeUInt32LE(central, 24, body.length);
    writeUInt16LE(central, 28, nameBuffer.length);
    writeUInt16LE(central, 30, 0);
    writeUInt16LE(central, 32, 0);
    writeUInt16LE(central, 34, 0);
    writeUInt16LE(central, 36, 0);
    writeUInt32LE(central, 38, 0);
    writeUInt32LE(central, 42, offset);
    centralParts.push(central, nameBuffer);
    offset += local.length + nameBuffer.length + body.length;
  }
  const centralStart = offset;
  const centralDirectory = concatBytes(centralParts);
  const end = allocBytes(22);
  writeUInt32LE(end, 0, 0x06054b50);
  writeUInt16LE(end, 4, 0);
  writeUInt16LE(end, 6, 0);
  writeUInt16LE(end, 8, files.length);
  writeUInt16LE(end, 10, files.length);
  writeUInt32LE(end, 12, centralDirectory.length);
  writeUInt32LE(end, 16, centralStart);
  writeUInt16LE(end, 20, 0);
  return concatBytes([...localParts, centralDirectory, end]);
}

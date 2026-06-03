const NativeBuffer = globalThis.Buffer;
const textEncoder = typeof TextEncoder !== "undefined" ? new TextEncoder() : null;

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp01(value) {
  return Math.min(Math.max(finiteNumber(value), 0), 1);
}

function bytesFromString(value, encoding = "utf-8") {
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

function allocBytes(length, fill = 0) {
  if (NativeBuffer?.alloc) {
    return NativeBuffer.alloc(length, fill);
  }
  const bytes = new Uint8Array(length);
  if (fill) {
    bytes.fill(fill);
  }
  return bytes;
}

function concatBytes(parts, totalLength = undefined) {
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

function typedArrayBytes(array) {
  return new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
}

function viewFor(bytes) {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

function writeUInt16LE(bytes, offset, value) {
  viewFor(bytes).setUint16(offset, value, true);
}

function writeUInt32LE(bytes, offset, value) {
  viewFor(bytes).setUint32(offset, value, true);
}

function writeFloatLE(bytes, offset, value) {
  viewFor(bytes).setFloat32(offset, value, true);
}

function writeAscii(bytes, offset, text, maxLength) {
  const source = String(text).slice(0, maxLength);
  for (let index = 0; index < source.length; index += 1) {
    bytes[offset + index] = source.charCodeAt(index) & 0x7f;
  }
}

function align4Buffer(buffer, fill = 0x20) {
  const padding = (4 - (buffer.length % 4)) % 4;
  return padding ? concatBytes([buffer, allocBytes(padding, fill)]) : buffer;
}

function hexToRgb01(hex, fallback = "#d4d4d8") {
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

function hexTo3mfDisplayColor(hex, fallback = "#d4d4d8") {
  const toChannel = (component) => Math.round(clamp01(component) * 255)
    .toString(16)
    .padStart(2, "0")
    .toUpperCase();
  const rgb = hexToRgb01(hex, fallback);
  return `#${toChannel(rgb[0])}${toChannel(rgb[1])}${toChannel(rgb[2])}FF`;
}

function triangleNormal(positions, offset) {
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

function sanitizeName(value, fallback = "implicit-cad") {
  return String(value || fallback).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g, "-") || fallback;
}

function boundsForPositions(positions) {
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
    min: min.map((value) => Number.isFinite(value) ? value : 0),
    max: max.map((value) => Number.isFinite(value) ? value : 0),
  };
}

function buildGlb(gltf, binaryParts) {
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

export function meshToBinaryStl(mesh, { name = "implicit-cad" } = {}) {
  const positions = mesh.positions || new Float32Array();
  const triangleCount = Math.floor(positions.length / 9);
  const buffer = allocBytes(84 + triangleCount * 50);
  writeAscii(buffer, 0, `implicit-cad ${sanitizeName(name)}`, 80);
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

export function meshToGlb(mesh, { name = "Implicit CAD", color = "#d4d4d8" } = {}) {
  const positions = mesh.positions || new Float32Array();
  const normals = mesh.normals && mesh.normals.length === positions.length
    ? mesh.normals
    : new Float32Array(positions.length);
  const vertexCount = Math.floor(positions.length / 3);
  const positionBuffer = typedArrayBytes(positions);
  const normalBuffer = typedArrayBytes(normals);
  const positionBounds = boundsForPositions(positions);
  const baseColor = hexToRgb01(color);
  const gltf = {
    asset: { version: "2.0", generator: "implicitjs exporter" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{
      mesh: 0,
      name: sanitizeName(name, "Implicit CAD"),
      extras: {
        cadOccurrenceId: "implicit-cad:0",
        cadSourceKind: "implicit-cad",
        cadUnits: "mm",
      },
    }],
    meshes: [{
      primitives: [{
        attributes: { POSITION: 0, NORMAL: 1 },
        material: 0,
        mode: 4,
      }],
    }],
    materials: [{
      name: "Implicit material",
      doubleSided: true,
      extras: { cadSourceColor: true },
      pbrMetallicRoughness: {
        baseColorFactor: [...baseColor.map(clamp01), 1],
        roughnessFactor: 0.72,
        metallicFactor: 0.02,
      },
    }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: positionBuffer.length, target: 34962 },
      { buffer: 0, byteOffset: positionBuffer.length, byteLength: normalBuffer.length, target: 34962 },
    ],
    accessors: [
      {
        bufferView: 0,
        byteOffset: 0,
        componentType: 5126,
        count: vertexCount,
        type: "VEC3",
        min: positionBounds.min,
        max: positionBounds.max,
      },
      {
        bufferView: 1,
        byteOffset: 0,
        componentType: 5126,
        count: vertexCount,
        type: "VEC3",
      },
    ],
  };
  return buildGlb(gltf, [positionBuffer, normalBuffer]);
}

export function meshToAnimatedGlb(mesh, {
  name = "Implicit CAD",
  color = "#d4d4d8",
  duration = 4,
  times = [],
  targetPositions = [],
} = {}) {
  const positions = mesh.positions || new Float32Array();
  const normals = mesh.normals && mesh.normals.length === positions.length
    ? mesh.normals
    : new Float32Array(positions.length);
  const vertexCount = Math.floor(positions.length / 3);
  const positionBuffer = typedArrayBytes(positions);
  const normalBuffer = typedArrayBytes(normals);
  const positionBounds = boundsForPositions(positions);
  const cleanTargets = targetPositions
    .filter((target) => target && target.length === positions.length)
    .map((target) => {
      const delta = new Float32Array(positions.length);
      for (let index = 0; index < positions.length; index += 1) {
        delta[index] = finiteNumber(target[index], positions[index]) - positions[index];
      }
      return delta;
    });
  if (!cleanTargets.length) {
    throw new Error("Animated GLB export needs at least one compatible animation frame.");
  }

  const keyTimes = Array.isArray(times) && times.length >= 2
    ? times.map((value) => Math.max(finiteNumber(value, 0), 0))
    : [0, Math.max(finiteNumber(duration, 4), 0.001)];
  const targetCount = cleanTargets.length;
  const weightValues = new Float32Array(keyTimes.length * targetCount);
  for (let key = 0; key < keyTimes.length; key += 1) {
    const targetIndex = key - 1;
    if (targetIndex >= 0 && targetIndex < targetCount) {
      weightValues[key * targetCount + targetIndex] = 1;
    }
  }
  const targetBuffers = cleanTargets.map((target) => typedArrayBytes(target));
  const timeValues = new Float32Array(keyTimes);
  const timeBuffer = typedArrayBytes(timeValues);
  const weightBuffer = typedArrayBytes(weightValues);
  const offsets = [];
  let byteOffset = 0;
  for (const part of [positionBuffer, normalBuffer, ...targetBuffers, timeBuffer, weightBuffer]) {
    offsets.push(byteOffset);
    byteOffset += part.length;
  }
  const baseColor = hexToRgb01(color);
  const targetAccessorStart = 2;
  const timeAccessor = targetAccessorStart + targetCount;
  const weightAccessor = timeAccessor + 1;
  const gltf = {
    asset: { version: "2.0", generator: "implicitjs animated exporter" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{
      mesh: 0,
      name: sanitizeName(name, "Implicit CAD"),
      weights: Array.from({ length: targetCount }, () => 0),
      extras: {
        cadOccurrenceId: "implicit-cad:0",
        cadSourceKind: "implicit-cad",
        cadUnits: "mm",
        implicitjsAnimated: true,
      },
    }],
    meshes: [{
      weights: Array.from({ length: targetCount }, () => 0),
      primitives: [{
        attributes: { POSITION: 0, NORMAL: 1 },
        targets: cleanTargets.map((_, index) => ({ POSITION: targetAccessorStart + index })),
        material: 0,
        mode: 4,
      }],
    }],
    materials: [{
      name: "Implicit material",
      doubleSided: true,
      extras: { cadSourceColor: true },
      pbrMetallicRoughness: {
        baseColorFactor: [...baseColor.map(clamp01), 1],
        roughnessFactor: 0.72,
        metallicFactor: 0.02,
      },
    }],
    animations: [{
      name: "Implicit parameter animation",
      channels: [{ sampler: 0, target: { node: 0, path: "weights" } }],
      samplers: [{ input: timeAccessor, output: weightAccessor, interpolation: "LINEAR" }],
    }],
    bufferViews: [
      { buffer: 0, byteOffset: offsets[0], byteLength: positionBuffer.length, target: 34962 },
      { buffer: 0, byteOffset: offsets[1], byteLength: normalBuffer.length, target: 34962 },
      ...targetBuffers.map((target, index) => ({
        buffer: 0,
        byteOffset: offsets[2 + index],
        byteLength: target.length,
        target: 34962,
      })),
      { buffer: 0, byteOffset: offsets[2 + targetCount], byteLength: timeBuffer.length },
      { buffer: 0, byteOffset: offsets[3 + targetCount], byteLength: weightBuffer.length },
    ],
    accessors: [
      {
        bufferView: 0,
        byteOffset: 0,
        componentType: 5126,
        count: vertexCount,
        type: "VEC3",
        min: positionBounds.min,
        max: positionBounds.max,
      },
      {
        bufferView: 1,
        byteOffset: 0,
        componentType: 5126,
        count: vertexCount,
        type: "VEC3",
      },
      ...cleanTargets.map((target, index) => {
        const bounds = boundsForPositions(target);
        return {
          bufferView: targetAccessorStart + index,
          byteOffset: 0,
          componentType: 5126,
          count: vertexCount,
          type: "VEC3",
          min: bounds.min,
          max: bounds.max,
        };
      }),
      {
        bufferView: timeAccessor,
        byteOffset: 0,
        componentType: 5126,
        count: timeValues.length,
        type: "SCALAR",
        min: [Math.min(...keyTimes)],
        max: [Math.max(...keyTimes)],
      },
      {
        bufferView: weightAccessor,
        byteOffset: 0,
        componentType: 5126,
        count: weightValues.length,
        type: "SCALAR",
        min: [0],
        max: [1],
      },
    ],
  };
  return buildGlb(gltf, [positionBuffer, normalBuffer, ...targetBuffers, timeBuffer, weightBuffer]);
}

function xmlEscape(value) {
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

function dosDateTime(date = new Date()) {
  const year = Math.max(date.getFullYear(), 1980);
  const dosTime = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
  const dosDate = ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
  return { dosTime, dosDate };
}

function zipStore(files) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  const { dosTime, dosDate } = dosDateTime();
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

export function meshTo3mf(mesh, { name = "Implicit CAD", color = "#d4d4d8" } = {}) {
  const positions = mesh.positions || new Float32Array();
  const vertexCount = Math.floor(positions.length / 3);
  const triangleCount = Math.floor(positions.length / 9);
  const displayColor = hexTo3mfDisplayColor(color);
  const vertices = [];
  for (let index = 0; index < vertexCount; index += 1) {
    const offset = index * 3;
    vertices.push(`<vertex x="${positions[offset]}" y="${positions[offset + 1]}" z="${positions[offset + 2]}"/>`);
  }
  const triangles = [];
  for (let index = 0; index < triangleCount; index += 1) {
    const base = index * 3;
    triangles.push(`<triangle v1="${base}" v2="${base + 1}" v3="${base + 2}" pid="2" p1="0"/>`);
  }
  const modelXml = `<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Title">${xmlEscape(name)}</metadata>
  <resources>
    <basematerials id="2">
      <base name="Implicit material" displaycolor="${displayColor}"/>
    </basematerials>
    <object id="1" type="model" name="${xmlEscape(name)}">
      <mesh>
        <vertices>
          ${vertices.join("\n          ")}
        </vertices>
        <triangles>
          ${triangles.join("\n          ")}
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1"/>
  </build>
</model>`;
  const contentTypes = `<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>`;
  const relationships = `<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>`;
  return zipStore([
    { name: "[Content_Types].xml", body: contentTypes },
    { name: "_rels/.rels", body: relationships },
    { name: "3D/3dmodel.model", body: modelXml },
  ]);
}

export function meshToFormat(mesh, format, options = {}) {
  const normalized = String(format || "").trim().toLowerCase().replace(/^\./, "");
  if (normalized === "stl") {
    return {
      body: meshToBinaryStl(mesh, options),
      contentType: "model/stl",
      extension: ".stl",
    };
  }
  if (normalized === "glb" || normalized === "gltf") {
    return {
      body: meshToGlb(mesh, options),
      contentType: "model/gltf-binary",
      extension: ".glb",
    };
  }
  if (normalized === "3mf") {
    return {
      body: meshTo3mf(mesh, options),
      contentType: "model/3mf",
      extension: ".3mf",
    };
  }
  throw new Error(`Unsupported implicit CAD export format: ${format || "(missing)"}`);
}

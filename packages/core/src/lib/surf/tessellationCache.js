// THE component-mesh store interface: one key scheme, one codec, shared by
// every consumer that draws a component — the viewer, the snapshot page and
// the docs hero. cadgen is the only producer: OCCT meshes each component's
// exact BREP on the server (cadgen/_internal/occt_mesh.py) and stores one GLB
// body per component and tolerance pair in the store's mesh index
// (cadgen/store/meshes.py, the format's Python half). This module only reads.
//
// It is BROWSER-PURE: codec and key only, no filesystem. Browser consumers
// reach the store through the async provider below, over the host's
// /__tess_cache/ routes (the viewer server, or the snapshot page's
// Playwright-routed origin served by cadgen's snapshot host).
//
// A body is glTF 2.0 binary, in CAD units (millimetres, Z up). Its BIN chunk
// holds, each section 4-byte aligned and present only when not empty: POSITION
// and NORMAL (f32 xyz), the indices of the ONE triangle primitive (u16 for at
// most 65,535 vertices, else u32), the face table (u32 rows: ord, indexStart,
// indexCount, colour — 0 for none, else a palette row plus one), the edge table
// (u32 rows: ord, pointStart, pointCount, class) and every edge's polyline (f32
// xyz) back to back. Its JSON chunk is the canonical JSON for the values in
// `extras.cadgen` (identity, bounds, scale, part colour, face colour palette)
// and the counts: a node carrying the CAD -> glTF frame, one mesh, three
// accessors, the buffer views and where each table is. A reader rebuilds that
// JSON and requires it, then views every section in place.

// v6: glTF 2.0 binary replaced TESS v5. Non-v6 entries are misses.
export const MESH_PAYLOAD_VERSION = 6;
// The producer's revision, part of every key (cadgen/store/meshes.py
// TESSELLATOR_VERSION). 10: OCCT BRepMesh on the exact BREP replaced the
// browser's surface tessellator.
export const TESSELLATION_VERSION = 10;
export const MESH_INDEX_SCHEMA = 2;
// The JSON chunk grows only with the face colour palette: cadgen/store/meshes.py
// MAX_JSON_BYTES, the same number.
export const MESH_MAX_JSON_BYTES = 64 * 1024 * 1024;
// The edge table's class codes, in this order (cadgen/store/meshes.py EDGE_CLASSES).
export const MESH_EDGE_CLASSES = Object.freeze([
  "none", "feature", "tangent", "seam", "degenerate", "boundary", "nonManifold", "unknown",
]);
// Both tables are rows of four u32: (ord, start, count, reference).
export const MESH_TABLE_COLUMNS = 4;

const GLB_MAGIC = 0x46546c67; // "glTF" little-endian
const GLB_VERSION = 2;
const JSON_CHUNK = 0x4e4f534a; // "JSON"
const BIN_CHUNK = 0x004e4942; // "BIN\0"
const UNSIGNED_SHORT_VERTEX_LIMIT = 65535;
// Z-up millimetres as glTF's Y-up metres: -90 degrees about X, then 0.001.
const NODE_ROTATION = Object.freeze([-Math.SQRT1_2, 0, 0, Math.SQRT1_2]);
const NODE_SCALE = Object.freeze([0.001, 0.001, 0.001]);
// `extras.cadgen`'s values, in the order cadgen writes them; the class names and the
// table references follow them.
const CAD_VALUES = Object.freeze([
  "payloadVersion", "tessellatorVersion", "tessellationInput", "surfaceInput", "surfaceObject",
  "quality", "bounds", "scale", "partColor", "faceColors",
]);
const COUNT_FIELDS = Object.freeze(["vertexCount", "indexCount", "faceCount", "edgeCount", "edgePointCount"]);
const SHA256_RE = /^[0-9a-f]{64}$/;
const QUALITY_FIELDS = new Set([
  "chordTolerance", "chordToleranceF64", "angleTolerance", "angleToleranceF64",
]);
const JSON_TEXT = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

function requireDigest(value, label) {
  const digest = typeof value === "string" ? value : "";
  if (!SHA256_RE.test(digest)) {
    throw new TypeError(`${label} must be 64 lowercase hex characters`);
  }
  return digest;
}

const HEX_BYTES = Array.from({ length: 256 }, (_, byte) => byte.toString(16).padStart(2, "0"));
const FLOAT64 = new DataView(new ArrayBuffer(8));

export function float64Hex(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new TypeError("tessellation tolerances must be positive finite binary64 values");
  }
  FLOAT64.setFloat64(0, value, false);
  let hex = "";
  for (let index = 0; index < 8; index += 1) hex += HEX_BYTES[FLOAT64.getUint8(index)];
  return hex;
}

// The tolerances are the only options a request carries, and it names both: the
// key spells both, and which pair a mesh is drawn at is cadgen's (a rung of the
// ladder it published, or the tessellation a job names), never a number here. A
// quality object read back from an entry (with its lossless f64 spellings) is
// accepted as its own request; any other field is a caller asking for something
// no mesh is keyed by, and is refused.
const TESSELLATION_OPTIONS = new Set(["chordTolerance", "angleTolerance", "chordToleranceF64", "angleToleranceF64"]);

export function tessellationQuality(options) {
  const unknown = Object.keys(options || {}).filter((name) => !TESSELLATION_OPTIONS.has(name));
  if (unknown.length) {
    throw new TypeError(
      `tessellation options are not part of the mesh key: ${unknown.join(", ")}.`
      + " Keyed options: chordTolerance, angleTolerance",
    );
  }
  const chordTolerance = options?.chordTolerance;
  const angleTolerance = options?.angleTolerance;
  if (chordTolerance === undefined || angleTolerance === undefined) {
    throw new TypeError(
      "a mesh request names both tolerances, chordTolerance and angleTolerance: a rung of cadgen's"
      + ` ladder (lodTessellationForLevel) or the tessellation a job names; got ${JSON.stringify(options ?? null)}`,
    );
  }
  return Object.freeze({
    chordTolerance,
    chordToleranceF64: float64Hex(chordTolerance),
    angleTolerance,
    angleToleranceF64: float64Hex(angleTolerance),
  });
}

// L is available before SURF output bytes: D already binds geometry and the
// frozen surface producer. Lossless f64 spelling prevents distinct accepted
// tolerances from colliding. The payload version is part of the key, so an
// older body can never answer for this one.
export function tessellationCacheKey(surfaceInput, options) {
  return keyOf(requireDigest(surfaceInput, "surfaceInput"), tessellationQuality(options));
}

// The key of a checked digest at a normalized quality (`tessellationQuality`).
function keyOf(digest, quality) {
  return `${digest}-t${TESSELLATION_VERSION}-p${MESH_PAYLOAD_VERSION}`
    + `-l${quality.chordToleranceF64}-a${quality.angleToleranceF64}`;
}

// R is the concrete display/selector identity. A body's extras carry O, so R
// remains discoverable even after the SURF object and index are gone.
export function resolvedTessellationIdentity(surfaceInput, surfaceObject, options) {
  const key = tessellationCacheKey(surfaceInput, options);
  return `${key}-s${requireDigest(surfaceObject, "surfaceObject")}`;
}

function align4(value) {
  return (value + 3) & ~3;
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function finiteTuple(value, length) {
  return Array.isArray(value) && value.length === length && value.every(finiteNumber);
}

function validCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

// JSON equality as cadgen decides it (meshes._same): numbers by value, objects by
// their key sets, arrays element by element.
function sameJson(a, b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    for (let index = 0; index < a.length; index += 1) {
      if (!sameJson(a[index], b[index])) return false;
    }
    return true;
  }
  const keys = Object.keys(a);
  if (keys.length !== Object.keys(b).length) return false;
  for (const key of keys) {
    if (!Object.hasOwn(b, key) || !sameJson(a[key], b[key])) return false;
  }
  return true;
}

/**
 * What decoding a body costs beyond its bytes (cadgen/store/meshes.py decoded_bytes): the
 * client's mesh data (positions, normals, u32 indices, the edges' points and segment pairs),
 * never less than what `buildMeshDataFromSurf` builds, and an allowance per face and edge
 * for the selector tables.
 */
export function tessellationDecodedBytes(counts) {
  const values = COUNT_FIELDS.map((field) => counts?.[field]);
  if (!values.every(validCount) || counts.edgePointCount < 2 * counts.edgeCount
    || (counts.edgeCount === 0) !== (counts.edgePointCount === 0)) {
    throw new TypeError("invalid tessellation size facts");
  }
  const decodedBytes = 24 * counts.vertexCount + 4 * counts.indexCount + 12 * counts.edgePointCount
    + 8 * (counts.edgePointCount - counts.edgeCount) + 256 * (counts.faceCount + counts.edgeCount);
  if (!Number.isSafeInteger(decodedBytes)) {
    throw new TypeError("tessellation decoded size exceeds the safe integer range");
  }
  return decodedBytes;
}

function meshSections({ vertexCount, indexCount, faceCount, edgeCount, edgePointCount }) {
  const sections = [];
  if (vertexCount) {
    const width = vertexCount <= UNSIGNED_SHORT_VERTEX_LIMIT ? 2 : 4;
    sections.push(["POSITION", 12 * vertexCount, 34962], ["NORMAL", 12 * vertexCount, 34962],
      ["indices", width * indexCount, 34963]);
  }
  if (faceCount) sections.push(["cadgen.faces", 4 * MESH_TABLE_COLUMNS * faceCount, null]);
  if (edgeCount) {
    sections.push(["cadgen.edges", 4 * MESH_TABLE_COLUMNS * edgeCount, null],
      ["cadgen.edgePoints", 12 * edgePointCount, null]);
  }
  return sections;
}

/**
 * The JSON chunk of a body whose `extras.cadgen` values (identity, bounds, scale, colours) and
 * counts these are: what cadgen writes (cadgen/store/meshes.py canonical_gltf) and what a body
 * must hold to be read.
 */
export function canonicalMeshGltf(cad, counts) {
  const views = [];
  const tables = {};
  let offset = 0;
  for (const [name, byteLength, target] of meshSections(counts)) {
    const view = { buffer: 0, byteOffset: offset, byteLength };
    if (target !== null) {
      view.target = target;
    } else {
      view.name = name;
      tables[name.slice("cadgen.".length)] = views.length;
    }
    views.push(view);
    offset += align4(byteLength);
  }
  const extras = { ...cad, edgeClasses: [...MESH_EDGE_CLASSES] };
  for (const [name, count] of [["faces", counts.faceCount], ["edges", counts.edgeCount], ["edgePoints", counts.edgePointCount]]) {
    if (name in tables) extras[name] = { bufferView: tables[name], count };
  }
  const gltf = { asset: { version: "2.0", generator: "cadgen" }, extras: { cadgen: extras } };
  if (counts.vertexCount) {
    Object.assign(gltf, {
      scene: 0,
      scenes: [{ nodes: [0] }],
      nodes: [{ mesh: 0, rotation: [...NODE_ROTATION], scale: [...NODE_SCALE] }],
      meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, mode: 4 }] }],
      accessors: [
        { bufferView: 0, componentType: 5126, count: counts.vertexCount, type: "VEC3",
          min: [...cad.bounds.min], max: [...cad.bounds.max] },
        { bufferView: 1, componentType: 5126, count: counts.vertexCount, type: "VEC3" },
        { bufferView: 2, componentType: counts.vertexCount <= UNSIGNED_SHORT_VERTEX_LIMIT ? 5123 : 5125,
          count: counts.indexCount, type: "SCALAR" },
      ],
    });
  }
  if (views.length) {
    gltf.bufferViews = views;
    gltf.buffers = [{ byteLength: offset }];
  }
  return gltf;
}

function validCad(cad) {
  if (!isObject(cad)) return false;
  const bounds = cad.bounds;
  if (!isObject(bounds) || Object.keys(bounds).length !== 2
    || !finiteTuple(bounds.min, 3) || !finiteTuple(bounds.max, 3)
    || bounds.min.some((value, index) => value > bounds.max[index])) return false;
  if (!finiteNumber(cad.scale) || cad.scale <= 0) return false;
  if (cad.partColor != null && !finiteTuple(cad.partColor, 4)) return false;
  return Array.isArray(cad.faceColors) && cad.faceColors.every((color) => finiteTuple(color, 4));
}

function decodedIdentity(cad, expected = {}) {
  try {
    if (cad?.tessellatorVersion !== TESSELLATION_VERSION
      || cad?.payloadVersion !== MESH_PAYLOAD_VERSION) return null;
    const surfaceInput = requireDigest(cad.surfaceInput, "surfaceInput");
    const surfaceObject = requireDigest(cad.surfaceObject, "surfaceObject");
    const quality = cad.quality;
    if (!isObject(quality)
      || Object.keys(quality).length !== QUALITY_FIELDS.size
      || Object.keys(quality).some((key) => !QUALITY_FIELDS.has(key))) return null;
    const normalized = tessellationQuality({
      chordTolerance: quality.chordTolerance,
      angleTolerance: quality.angleTolerance,
    });
    if (quality.chordToleranceF64 !== normalized.chordToleranceF64
      || quality.angleToleranceF64 !== normalized.angleToleranceF64) return null;
    const tessellationInput = keyOf(surfaceInput, normalized);
    if (cad.tessellationInput !== tessellationInput) return null;
    const renderIdentity = `${tessellationInput}-s${surfaceObject}`;

    if (expected.surfaceInput !== undefined
      && requireDigest(expected.surfaceInput, "expected surfaceInput") !== surfaceInput) return null;
    const expectedSurface = expected.surfaceObject ?? expected.surfaceDigest;
    if (expectedSurface !== undefined
      && requireDigest(expectedSurface, "expected surfaceObject") !== surfaceObject) return null;
    if (expected.tessellationInput !== undefined
      && String(expected.tessellationInput) !== tessellationInput) return null;
    if (expected.renderIdentity !== undefined
      && String(expected.renderIdentity) !== renderIdentity) return null;
    if (expected.tessellation !== undefined
      && tessellationCacheKey(surfaceInput, expected.tessellation) !== tessellationInput) return null;

    return Object.freeze({
      surfaceInput,
      surfaceObject,
      tessellationInput,
      renderIdentity,
      quality: normalized,
      tessellatorVersion: TESSELLATION_VERSION,
      payloadVersion: MESH_PAYLOAD_VERSION,
    });
  } catch {
    return null;
  }
}

// A table reference's count: 0 when the table is absent, null when the reference is malformed.
function tableCount(reference) {
  if (reference === undefined || reference === null) return 0;
  return isObject(reference) && Number.isSafeInteger(reference.count) && reference.count > 0
    ? reference.count : null;
}

// The rows rise by ordinal and cover `total` from 0 in order; `valid(count, reference)` holds of
// each row's count and reference.
function validTable(table, total, valid) {
  let previous = 0;
  let cursor = 0;
  for (let row = 0; row < table.length; row += MESH_TABLE_COLUMNS) {
    const ord = table[row];
    const count = table[row + 2];
    if (ord <= previous || table[row + 1] !== cursor || !valid(count, table[row + 3])) return false;
    previous = ord;
    cursor += count;
  }
  return cursor === total;
}

// The validated body: its identity, counts and every section viewed in place (copied when the
// bytes do not sit on a 4-byte boundary).
function decodeBody(bytes, expected = {}) {
  if (!(bytes instanceof Uint8Array) || bytes.length < 20) return null;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.getUint32(0, true) !== GLB_MAGIC || view.getUint32(4, true) !== GLB_VERSION
    || view.getUint32(8, true) !== bytes.length || view.getUint32(16, true) !== JSON_CHUNK) return null;
  const jsonLength = view.getUint32(12, true);
  if (jsonLength === 0 || jsonLength > MESH_MAX_JSON_BYTES || jsonLength % 4 !== 0
    || 20 + jsonLength > bytes.length) return null;
  let binStart = 20 + jsonLength;
  let binLength = 0;
  if (binStart < bytes.length) {
    if (binStart + 8 > bytes.length) return null;
    binLength = view.getUint32(binStart, true);
    if (view.getUint32(binStart + 4, true) !== BIN_CHUNK || binLength === 0 || binLength % 4 !== 0
      || binStart + 8 + binLength !== bytes.length) return null;
    binStart += 8;
  }
  const gltf = JSON.parse(JSON_TEXT.decode(bytes.subarray(20, 20 + jsonLength)));
  const cad = isObject(gltf) && isObject(gltf.extras) ? gltf.extras.cadgen : null;
  if (!validCad(cad)) return null;
  const identity = decodedIdentity(cad, expected);
  if (!identity) return null;
  let vertexCount = 0;
  let indexCount = 0;
  if (gltf.accessors !== undefined) {
    const accessors = gltf.accessors;
    if (!Array.isArray(accessors) || accessors.length !== 3 || !accessors.every(isObject)
      || !validCount(accessors[0].count) || !validCount(accessors[2].count)) return null;
    vertexCount = accessors[0].count;
    indexCount = accessors[2].count;
    if (!vertexCount || !indexCount || indexCount % 3 !== 0) return null;
  }
  const counts = {
    vertexCount,
    indexCount,
    faceCount: tableCount(cad.faces),
    edgeCount: tableCount(cad.edges),
    edgePointCount: tableCount(cad.edgePoints),
  };
  if (counts.faceCount === null || counts.edgeCount === null || counts.edgePointCount === null
    || (counts.edgeCount === 0) !== (counts.edgePointCount === 0)) return null;
  const values = {};
  for (const name of CAD_VALUES) {
    if (!Object.hasOwn(cad, name)) return null;
    values[name] = cad[name];
  }
  const canonical = canonicalMeshGltf(values, counts);
  if (!sameJson(gltf, canonical) || binLength !== (canonical.buffers?.[0].byteLength ?? 0)) return null;

  const views = canonical.bufferViews || [];
  const viewOf = (name) => views[name === "POSITION" ? 0 : name === "NORMAL" ? 1 : name === "indices" ? 2
    : views.findIndex((entry) => entry.name === name)];
  const take = (name, Ctor) => {
    const entry = viewOf(name);
    const start = bytes.byteOffset + binStart + entry.byteOffset;
    const length = entry.byteLength / Ctor.BYTES_PER_ELEMENT;
    return start % 4 === 0
      ? new Ctor(bytes.buffer, start, length)
      : new Ctor(bytes.buffer.slice(start, start + entry.byteLength));
  };
  const IndexArray = vertexCount <= UNSIGNED_SHORT_VERTEX_LIMIT ? Uint16Array : Uint32Array;
  const component = {
    positions: vertexCount ? take("POSITION", Float32Array) : new Float32Array(0),
    normals: vertexCount ? take("NORMAL", Float32Array) : new Float32Array(0),
    indices: vertexCount ? take("indices", IndexArray) : new Uint32Array(0),
    faceTable: counts.faceCount ? take("cadgen.faces", Uint32Array) : new Uint32Array(0),
    edgeTable: counts.edgeCount ? take("cadgen.edges", Uint32Array) : new Uint32Array(0),
    edgePoints: counts.edgeCount ? take("cadgen.edgePoints", Float32Array) : new Float32Array(0),
    faceColors: cad.faceColors,
    bounds: cad.bounds,
    scale: cad.scale,
  };
  const palette = cad.faceColors.length;
  if (!validTable(component.faceTable, indexCount, (count, color) => count % 3 === 0 && color <= palette)
    || !validTable(component.edgeTable, counts.edgePointCount,
      (count, edgeClass) => count >= 2 && edgeClass < MESH_EDGE_CLASSES.length)) return null;
  return { component, partColor: cad.partColor ?? null, identity, counts };
}

export function tessellationPayloadFacts(bytes, expected = {}) {
  try {
    const body = decodeBody(bytes, expected);
    if (!body) return null;
    const facts = Object.freeze({
      byteLength: bytes.byteLength,
      decodedBytes: tessellationDecodedBytes(body.counts),
      surfaceInput: body.identity.surfaceInput,
      surfaceObject: body.identity.surfaceObject,
      tessellationInput: body.identity.tessellationInput,
      renderIdentity: body.identity.renderIdentity,
      quality: body.identity.quality,
      tessellatorVersion: TESSELLATION_VERSION,
      payloadVersion: MESH_PAYLOAD_VERSION,
      ...body.counts,
    });
    for (const field of [
      "byteLength", "decodedBytes", "surfaceInput", "surfaceObject", "tessellationInput",
      "renderIdentity", "tessellatorVersion", "payloadVersion", ...COUNT_FIELDS,
    ]) {
      if (expected[field] !== undefined && expected[field] !== facts[field]) return null;
    }
    return facts;
  } catch {
    return null;
  }
}

const MESH_RECORD_FIELDS = new Set([
  "schemaVersion", "object", "byteLength", "decodedBytes", "surfaceInput", "surfaceObject",
  "tessellationInput", "renderIdentity", "quality", "tessellatorVersion", "payloadVersion",
  ...COUNT_FIELDS,
]);

export function validateTessellationProbeRow(value, expected = {}) {
  try {
    if (!value || typeof value !== "object" || Array.isArray(value)
      || Object.keys(value).length !== MESH_RECORD_FIELDS.size
      || Object.keys(value).some((key) => !MESH_RECORD_FIELDS.has(key))) return null;
    if (value.schemaVersion !== MESH_INDEX_SCHEMA
      || value.tessellatorVersion !== TESSELLATION_VERSION
      || value.payloadVersion !== MESH_PAYLOAD_VERSION) return null;
    const surfaceInput = requireDigest(value.surfaceInput, "surfaceInput");
    const surfaceObject = requireDigest(value.surfaceObject, "surfaceObject");
    const object = requireDigest(value.object, "object");
    const quality = tessellationQuality({
      chordTolerance: value.quality?.chordTolerance,
      angleTolerance: value.quality?.angleTolerance,
    });
    if (value.quality?.chordToleranceF64 !== quality.chordToleranceF64
      || value.quality?.angleToleranceF64 !== quality.angleToleranceF64) return null;
    const tessellationInput = keyOf(surfaceInput, quality);
    const renderIdentity = `${tessellationInput}-s${surfaceObject}`;
    if (value.tessellationInput !== tessellationInput || value.renderIdentity !== renderIdentity) return null;
    const counts = Object.fromEntries(COUNT_FIELDS.map((field) => [field, value[field]]));
    if (!validCount(value.byteLength) || value.byteLength < 20 || value.byteLength % 4 !== 0
      || value.decodedBytes !== tessellationDecodedBytes(counts)) return null;
    if (expected.tessellationInput !== undefined && expected.tessellationInput !== tessellationInput) return null;
    if (expected.object !== undefined && expected.object !== object) return null;
    if (expected.surfaceInput !== undefined && expected.surfaceInput !== surfaceInput) return null;
    if (expected.surfaceObject !== undefined && expected.surfaceObject !== surfaceObject) return null;
    return Object.freeze({
      schemaVersion: MESH_INDEX_SCHEMA,
      object,
      byteLength: value.byteLength,
      decodedBytes: value.decodedBytes,
      surfaceInput,
      surfaceObject,
      tessellationInput,
      renderIdentity,
      quality,
      tessellatorVersion: TESSELLATION_VERSION,
      payloadVersion: MESH_PAYLOAD_VERSION,
      ...counts,
    });
  } catch {
    return null;
  }
}

/**
 * One stored mesh, decoded: `component` holds its sections viewed in place -- `positions` and
 * `normals` (f32 xyz), `indices` (u16 or u32), `faceTable` and `edgeTable` (u32 rows of
 * MESH_TABLE_COLUMNS), `edgePoints` (f32 xyz) -- with its face colour palette, bounds and scale.
 * `meshFaceRanges` and `meshEdgePolylines` read the tables as objects. Null for anything that is
 * not a valid body bound to `expected`: a corrupt entry is a miss, never an error.
 */
export function decodeComponentTessellation(bytes, expected = {}) {
  try {
    const body = decodeBody(bytes, expected);
    return body ? { component: body.component, partColor: body.partColor, identity: body.identity } : null;
  } catch {
    return null;
  }
}

/** A decoded component's faces: `[{ord, color, indexStart, indexCount}]`, a colour its palette row or null. */
export function meshFaceRanges(component) {
  const table = component.faceTable;
  const ranges = [];
  for (let row = 0; row < table.length; row += MESH_TABLE_COLUMNS) {
    const color = table[row + 3];
    ranges.push({
      ord: table[row],
      color: color ? component.faceColors[color - 1] : null,
      indexStart: table[row + 1],
      indexCount: table[row + 2],
    });
  }
  return ranges;
}

/** A decoded component's edges: `[{ord, visibilityClass, polyline}]`, each polyline a view of its points. */
export function meshEdgePolylines(component) {
  const table = component.edgeTable;
  const points = component.edgePoints;
  const edges = [];
  for (let row = 0; row < table.length; row += MESH_TABLE_COLUMNS) {
    const start = table[row + 1] * 3;
    edges.push({
      ord: table[row],
      visibilityClass: MESH_EDGE_CLASSES[table[row + 3]],
      polyline: points.subarray(start, start + table[row + 2] * 3),
    });
  }
  return edges;
}

// The stand-in for a parsed surf index that render consumers (buildMeshDataFromSurf) read:
// the part colour, which every body carries, so drawing a component never needs its SURF.
export function surfIndexFromCacheEntry(decoded) {
  return decoded?.component ? { partColor: decoded.partColor ?? null } : null;
}

// --- batch container ---------------------------------------------------------
//
// One round trip for N bodies: "TESB" u32, version u32, count u32, then per
// entry u32 byteLength (0 = miss) + bytes padded to a 4-byte boundary so each
// entry decodes zero-copy (a GLB body is a 4-byte multiple already). Served by
// both cache hosts (the snapshot loopback server and the viewer server) on POST
// <prefix>/batch with a JSON body naming the admitted objects; this module is
// the format's single home.

export const TESS_CACHE_BATCH_MAGIC = 0x42534554; // "TESB" little-endian
export const TESS_CACHE_BATCH_VERSION = 1;

export function encodeTessellationCacheBatch(entries) {
  let total = 12;
  for (const entry of entries) {
    total += 4 + align4(entry ? entry.length : 0);
  }
  const bytes = new Uint8Array(total);
  const view = new DataView(bytes.buffer);
  view.setUint32(0, TESS_CACHE_BATCH_MAGIC, true);
  view.setUint32(4, TESS_CACHE_BATCH_VERSION, true);
  view.setUint32(8, entries.length, true);
  let offset = 12;
  for (const entry of entries) {
    view.setUint32(offset, entry ? entry.length : 0, true);
    offset += 4;
    if (entry && entry.length) {
      bytes.set(entry, offset);
      offset += align4(entry.length);
    }
  }
  return bytes;
}

export function decodeTessellationCacheBatch(bytes) {
  try {
    if (!(bytes instanceof Uint8Array) || bytes.length < 12) return null;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (view.getUint32(0, true) !== TESS_CACHE_BATCH_MAGIC) return null;
    if (view.getUint32(4, true) !== TESS_CACHE_BATCH_VERSION) return null;
    const count = view.getUint32(8, true);
    const entries = [];
    let offset = 12;
    for (let i = 0; i < count; i += 1) {
      if (offset + 4 > bytes.length) return null;
      const length = view.getUint32(offset, true);
      offset += 4;
      if (length === 0) {
        entries.push(null);
        continue;
      }
      if (offset + length > bytes.length) return null;
      entries.push(bytes.subarray(offset, offset + length));
      const padded = align4(length);
      if (offset + padded > bytes.length) return null;
      offset += padded;
    }
    return offset === bytes.length ? entries : null;
  } catch {
    return null;
  }
}

function abortError(error, signal) {
  return signal?.aborted || error?.name === "AbortError";
}

export class TessellationCacheProbeMissError extends Error {
  constructor(probe, options = {}) {
    super("A probed tessellation cache object is no longer readable", options);
    this.name = "TessellationCacheProbeMissError";
    this.code = "TESS_CACHE_PROBE_MISS";
    this.probe = probe;
  }
}

export function isTessellationCacheProbeMissError(error) {
  return error?.code === "TESS_CACHE_PROBE_MISS";
}

// A root connection or standalone job owns its provider. Views borrow
// cancellable sessions; no provider is installed into module state.
export function createTessellationCache({ provider = null } = {}) {
  let disposed = false;
  let cacheProvider = provider
    && typeof provider.probeMany === "function"
    && typeof provider.getProbed === "function" ? provider : null;
  const lifetime = new AbortController();
  const requestOptions = (request = {}) => ({
    ...request,
    signal: request.signal
      ? AbortSignal.any([lifetime.signal, request.signal])
      : lifetime.signal,
  });
  function tessellationCacheProviderRegistered() { return !disposed && cacheProvider !== null; }
  async function probeCachedTessellationEntries(surfaceInputs, options, { signal } = {}) {
    const hits = new Map();
    const provider = disposed ? null : cacheProvider;
    if (!provider || !Array.isArray(surfaceInputs) || !surfaceInputs.length) return hits;
    // The HTTP provider refuses oversized metadata requests. Split here so
    // assembly size never silently converts a complete warm cache into misses.
    for (let start = 0; start < surfaceInputs.length; start += TESS_PROBE_MAX_KEYS) {
      const inputs = surfaceInputs.slice(start, start + TESS_PROBE_MAX_KEYS);
      const keys = inputs.map((surfaceInput) => tessellationCacheKey(surfaceInput, options));
      const rows = await provider.probeMany(keys, { signal });
      signal?.throwIfAborted();
      if (!Array.isArray(rows) || rows.length !== keys.length) continue;
      for (let index = 0; index < keys.length; index += 1) {
        const row = validateTessellationProbeRow(rows[index], {
          tessellationInput: keys[index],
          surfaceInput: inputs[index],
        });
        if (row) hits.set(inputs[index], row);
      }
    }
    return hits;
  }

  // Ask the host to mesh what a probe found missing: cadgen produces it, stores
  // it, and answers with its probe row, exactly as a probe would have. Only a
  // host that can mesh offers this (`provider.produceMany`); elsewhere a
  // missing mesh stays missing.
  async function produceTessellationEntries(surfaceInputs, options, { signal } = {}) {
    const hits = new Map();
    const provider = disposed ? null : cacheProvider;
    if (!provider || typeof provider.produceMany !== "function"
      || !Array.isArray(surfaceInputs) || !surfaceInputs.length) return hits;
    for (let start = 0; start < surfaceInputs.length; start += TESS_PROBE_MAX_KEYS) {
      const inputs = surfaceInputs.slice(start, start + TESS_PROBE_MAX_KEYS);
      const keys = inputs.map((surfaceInput) => tessellationCacheKey(surfaceInput, options));
      const rows = await provider.produceMany(keys, { signal });
      signal?.throwIfAborted();
      if (!Array.isArray(rows) || rows.length !== keys.length) continue;
      for (let index = 0; index < keys.length; index += 1) {
        const row = validateTessellationProbeRow(rows[index], {
          tessellationInput: keys[index],
          surfaceInput: inputs[index],
        });
        if (row) hits.set(inputs[index], row);
      }
    }
    return hits;
  }

  async function getCachedEntryBytes(surfaceInput, options, {
    signal,
    probe = null,
    strictProbe = false,
  } = {}) {
    const provider = disposed ? null : cacheProvider;
    if (!provider) {
      if (strictProbe) throw new TessellationCacheProbeMissError(probe);
      return null;
    }
    const key = tessellationCacheKey(surfaceInput, options);
    let row = validateTessellationProbeRow(probe, { tessellationInput: key, surfaceInput });
    if (!row) {
      row = (await probeCachedTessellationEntries([surfaceInput], options, { signal })).get(surfaceInput) || null;
    }
    if (!row) {
      if (strictProbe) throw new TessellationCacheProbeMissError(probe);
      return null;
    }
    let bytes;
    try {
      bytes = await provider.getProbed(row, { signal, maxBytes: row.byteLength });
      signal?.throwIfAborted();
    } catch (error) {
      if (abortError(error, signal) || !strictProbe) throw error;
      throw new TessellationCacheProbeMissError(row, { cause: error });
    }
    if (tessellationPayloadFacts(bytes, row)) return bytes;
    if (strictProbe) throw new TessellationCacheProbeMissError(row);
    return null;
  }

  async function getCachedEntryBytesMany(probes, { signal, maxBytes = TESS_BATCH_MAX_BYTES } = {}) {
    const provider = disposed ? null : cacheProvider;
    if (!provider || !Array.isArray(probes) || !probes.length) return null;
    const rows = probes.map((probe) => validateTessellationProbeRow(probe));
    if (rows.some((row) => !row)) return null;
    const bytes = typeof provider.getManyProbed !== "function"
      ? await Promise.all(rows.map((row) => provider.getProbed(row, {
        signal,
        maxBytes: row.byteLength,
      })))
      : await provider.getManyProbed(rows, { signal, maxBytes });
    signal?.throwIfAborted();
    if (!Array.isArray(bytes) || bytes.length !== rows.length) return null;
    return bytes.map((entry, index) => (
      tessellationPayloadFacts(entry, rows[index]) ? entry : null
    ));
  }

  async function getCachedComponentEntry(surfaceInput, options, request = {}) {
    const bytes = await getCachedEntryBytes(surfaceInput, options, request);
    return decodeComponentTessellation(bytes, {
      surfaceInput,
      ...(request.probe?.surfaceObject ? { surfaceObject: request.probe.surfaceObject } : {}),
      tessellationInput: tessellationCacheKey(surfaceInput, options),
      tessellation: options,
    });
  }

  function createSession({ signal } = {}) {
    if (disposed) throw new Error("This tessellation cache has been disposed.");
    const sessionLifetime = new AbortController();
    const sessionSignal = AbortSignal.any([
      lifetime.signal,
      sessionLifetime.signal,
      ...(signal ? [signal] : []),
    ]);
    const active = () => !sessionSignal.aborted;
    const read = async (method, args, request = {}) => {
      sessionSignal.throwIfAborted();
      return cache[method](...args, {
        ...request,
        signal: request.signal ? AbortSignal.any([sessionSignal, request.signal]) : sessionSignal,
      });
    };
    return {
      ...cache,
      tessellationCacheProviderRegistered: () => active() && cache.tessellationCacheProviderRegistered(),
      probeCachedTessellationEntries: (inputs, options, request) => read("probeCachedTessellationEntries", [inputs, options], request),
      produceTessellationEntries: (inputs, options, request) => read("produceTessellationEntries", [inputs, options], request),
      getCachedEntryBytes: (input, options, request) => read("getCachedEntryBytes", [input, options], request),
      getCachedEntryBytesMany: (probes, request) => read("getCachedEntryBytesMany", [probes], request),
      getCachedComponentEntry: (input, options, request) => read("getCachedComponentEntry", [input, options], request),
      createSession: ({ signal: childSignal } = {}) => createSession({
        signal: childSignal ? AbortSignal.any([sessionSignal, childSignal]) : sessionSignal,
      }),
      // Cancels this view's reads alone, never another view's.
      dispose: () => sessionLifetime.abort(),
    };
  }

  const cache = {
    // What one batched read may ask for over this cache's provider (`tessBatchMaxBytes`).
    batchMaxBytes: tessBatchMaxBytes(cacheProvider?.maxBatchBytes),
    tessellationCacheProviderRegistered,
    probeCachedTessellationEntries: (inputs, options, request) => probeCachedTessellationEntries(inputs, options, requestOptions(request)),
    produceTessellationEntries: (inputs, options, request) => produceTessellationEntries(inputs, options, requestOptions(request)),
    getCachedEntryBytes: (input, options, request) => getCachedEntryBytes(input, options, requestOptions(request)),
    getCachedEntryBytesMany: (probes, request) => getCachedEntryBytesMany(probes, requestOptions(request)),
    getCachedComponentEntry: (input, options, request) => getCachedComponentEntry(input, options, requestOptions(request)),
    createSession,
    dispose() {
      if (disposed) return;
      disposed = true;
      lifetime.abort();
      cacheProvider = null;
    },
  };
  return cache;
}
export const TESS_PROBE_MAX_KEYS = 256;
export const TESS_BATCH_MAX_BYTES = 32 * 1024 * 1024;

/**
 * The most framed bytes one batched read may ask for: the server's bound
 * (`TESS_BATCH_MAX_BYTES`), or a transport's lower ceiling. A host whose channel
 * carries large replies slowly declares one (`createCadClient({ maxBatchBytes })`);
 * a ceiling above the server's bound, or none, leaves the server's.
 */
export function tessBatchMaxBytes(transportMaxBytes) {
  const ceiling = Number(transportMaxBytes);
  return Number.isSafeInteger(ceiling) && ceiling > 0 ? Math.min(ceiling, TESS_BATCH_MAX_BYTES) : TESS_BATCH_MAX_BYTES;
}

async function sha256Hex(bytes) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function withReadBinding(url, row, maxBytes) {
  const base = typeof location === "undefined" ? "http://cadgen.invalid/" : location.href;
  const parsed = new URL(url, base);
  parsed.searchParams.set("object", row.object);
  parsed.searchParams.set("maxBytes", String(maxBytes));
  return parsed.origin === "http://cadgen.invalid"
    ? `${parsed.pathname}${parsed.search}${parsed.hash}`
    : parsed.href;
}

async function boundedResponseBytes(response, maxBytes) {
  const length = Number(response.headers.get("content-length"));
  if (!Number.isSafeInteger(length) || length < 0 || length > maxBytes) return null;
  if (response.body?.getReader) {
    const bytes = new Uint8Array(length);
    const reader = response.body.getReader();
    let offset = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!(value instanceof Uint8Array) || offset + value.byteLength > length) {
          await reader.cancel();
          return null;
        }
        bytes.set(value, offset);
        offset += value.byteLength;
      }
    } finally {
      reader.releaseLock?.();
    }
    return offset === length ? bytes : null;
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  return bytes.byteLength === length ? bytes : null;
}

export function originPrefix(origin) {
  return String(origin ?? "").trim().replace(/\/+$/u, "");
}

export function createHttpTessellationCacheProvider({
  origin = "",
  entryUrl = (key) => `${originPrefix(origin)}/__tess_cache/${encodeURIComponent(key)}.glb`,
  probeUrl = `${originPrefix(origin)}/__tess_cache/probe`,
  batchUrl = `${originPrefix(origin)}/__tess_cache/batch`,
  // Only a host that meshes on request serves this route (the snapshot host).
  produceUrl = "",
  headers = {},
  fetch: fetchImpl = globalThis.fetch,
  signal: lifetimeSignal,
  // The transport's ceiling for one batched read (`tessBatchMaxBytes`).
  maxBatchBytes,
} = {}) {
  const scopedSignal = (signal) => lifetimeSignal && signal
    ? AbortSignal.any([lifetimeSignal, signal]) : lifetimeSignal || signal;
  const batchCeiling = tessBatchMaxBytes(maxBatchBytes);
  return {
    maxBatchBytes: batchCeiling,
    async probeMany(keys, { signal } = {}) {
      signal = scopedSignal(signal);
      if (!Array.isArray(keys) || keys.length > TESS_PROBE_MAX_KEYS) return null;
      try {
        const response = await fetchImpl(probeUrl, {
          method: "POST",
          headers: { ...headers, "content-type": "application/json" },
          body: JSON.stringify({ tessellationInputs: keys }),
          signal,
          cache: "no-store",
        });
        if (!response.ok) return null;
        const payload = await response.json();
        const entries = payload?.entries;
        return keys.map((key) => validateTessellationProbeRow(entries?.[key], { tessellationInput: key }));
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return null;
      }
    },
    ...(produceUrl ? {
      async produceMany(keys, { signal } = {}) {
        signal = scopedSignal(signal);
        if (!Array.isArray(keys) || keys.length > TESS_PROBE_MAX_KEYS) return null;
        const response = await fetchImpl(produceUrl, {
          method: "POST",
          headers: { ...headers, "content-type": "application/json" },
          body: JSON.stringify({ tessellationInputs: keys }),
          signal,
          cache: "no-store",
        });
        // cadgen could not mesh what was asked: that is the caller's error, with its reason.
        if (!response.ok) throw new Error(await response.text() || `mesh request failed: HTTP ${response.status}`);
        const payload = await response.json();
        const entries = payload?.entries;
        return keys.map((key) => validateTessellationProbeRow(entries?.[key], { tessellationInput: key }));
      },
    } : {}),
    async getProbed(value, { signal, maxBytes } = {}) {
      signal = scopedSignal(signal);
      const row = validateTessellationProbeRow(value);
      const limit = Number(maxBytes);
      if (!row || !Number.isSafeInteger(limit) || limit < row.byteLength) return null;
      try {
        const response = await fetchImpl(withReadBinding(entryUrl(row.tessellationInput), row, limit), {
          cache: "no-store", headers, signal,
        });
        if (!response.ok) return null;
        const bytes = await boundedResponseBytes(response, limit);
        // The content address binds the body to its row; the cache checks its facts.
        if (!bytes || await sha256Hex(bytes) !== row.object) return null;
        return bytes;
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return null;
      }
    },
    async getManyProbed(values, { signal, maxBytes = TESS_BATCH_MAX_BYTES } = {}) {
      signal = scopedSignal(signal);
      const rows = values.map((value) => validateTessellationProbeRow(value));
      const limit = Number(maxBytes);
      const framedBytes = 12 + rows.reduce((sum, row) => sum + 4 + (row ? align4(row.byteLength) : 0), 0);
      if (rows.some((row) => !row) || !Number.isSafeInteger(limit)
        || framedBytes > limit || framedBytes > batchCeiling) return null;
      try {
        const response = await fetchImpl(batchUrl, {
          method: "POST",
          headers: { ...headers, "content-type": "application/json" },
          body: JSON.stringify({ entries: rows.map((row) => ({
            tessellationInput: row.tessellationInput,
            object: row.object,
            maxBytes: row.byteLength,
          })) }),
          signal,
          cache: "no-store",
        });
        if (!response.ok) return null;
        const container = await boundedResponseBytes(response, limit);
        const entries = decodeTessellationCacheBatch(container);
        if (!entries || entries.length !== rows.length) return null;
        // Each entry is verified on its own: one the store no longer holds, or holds damaged, is a
        // miss for that component alone, never for every other component in the batch. The
        // content address binds an entry to its row; the cache checks its facts.
        const digests = await Promise.all(entries.map((entry) => (entry ? sha256Hex(entry) : null)));
        return entries.map((entry, index) => (entry && digests[index] === rows[index].object ? entry : null));
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return null;
      }
    },
  };
}

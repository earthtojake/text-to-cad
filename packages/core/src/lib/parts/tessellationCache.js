// THE part store interface: one key, one record, one codec, shared by every consumer that
// draws a component — the viewer, the snapshot page and the docs hero. cadgen is the only
// producer: it derives each part's display data once, as ONE index record naming two
// objects — its display mesh (a GLB body) and its selector table (cadgen/store/parts.py) —
// keyed by the part (`<digest>-v<version>`, which a view names for each component and which
// carries no tolerance). This module only reads.
//
// It is BROWSER-PURE: codec and records only, no filesystem. Browser consumers reach the
// store through the async provider below, over the host's /__tess_cache/ routes (the viewer
// server, or the snapshot page's Playwright-routed origin served by cadgen's snapshot host):
// a probe answers parts' records, a batch reads many display meshes in one round trip, and
// `<part>.glb` / `<part>.selectors.json` read one object, each bound to the record that
// names it.
//
// A body is glTF 2.0 binary, in CAD units (millimetres, Z up). Its BIN chunk holds, each
// section 4-byte aligned and present only when not empty: POSITION and NORMAL (f32 xyz), the
// indices of the ONE triangle primitive (u16 for at most 65,535 vertices, else u32), the face
// table (u32 rows: ord, indexStart, indexCount, colour — 0 for none, else a palette row plus
// one), the edge table (u32 rows: ord, pointStart, pointCount, class) and every edge's
// polyline (f32 xyz) back to back. Its JSON chunk is the canonical JSON for the values in
// `extras.cadgen` (the part, bounds, face colour palette) and the counts: a node carrying the
// CAD -> glTF frame, one mesh, three accessors, the buffer views and where each table is. A
// reader rebuilds that JSON and requires it, then views every section in place
// (cadgen/store/meshes.py is the format's Python half).

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
const CAD_VALUES = Object.freeze(["part", "bounds", "faceColors"]);
// The faces no mesher could cover, which the body leaves undrawn: a value only a body with one
// has (cadgen/store/meshes.py `unmeshedFaces`), and a count only its record has.
const UNMESHED = "unmeshedFaces";
const UNMESHED_COUNT = "unmeshedFaceCount";
const COUNT_FIELDS = Object.freeze(["vertexCount", "indexCount", "faceCount", "edgeCount", "edgePointCount"]);
const SHA256_RE = /^[0-9a-f]{64}$/;
// A part's key (cadgen/store/parts.py `part_key`): a digest and the version of its derivation.
const PART_RE = /^[0-9a-f]{64}-v[0-9]+$/;
const GLB_FIELDS = Object.freeze(["object", "byteLength", "decodedBytes", ...COUNT_FIELDS]);
const SELECTOR_FIELDS = Object.freeze(["object", "byteLength", "faceCount", "edgeCount", "vertexCount"]);
const JSON_TEXT = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

/** Whether `value` is a part's key as a view names it. */
export function isPartKey(value) {
  return typeof value === "string" && PART_RE.test(value);
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
 * never less than what `buildComponentMeshData` builds, and an allowance per face and edge
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
 * The JSON chunk of a body whose `extras.cadgen` values (part, bounds, colours) and counts these
 * are: what cadgen writes (cadgen/store/meshes.py canonical_gltf) and what a body must hold to be
 * read.
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
  if (!isObject(cad) || !isPartKey(cad.part)) return false;
  const bounds = cad.bounds;
  if (!isObject(bounds) || Object.keys(bounds).length !== 2
    || !finiteTuple(bounds.min, 3) || !finiteTuple(bounds.max, 3)
    || bounds.min.some((value, index) => value > bounds.max[index])) return false;
  if (Object.hasOwn(cad, UNMESHED)) {
    const unmeshed = cad[UNMESHED];
    if (!Array.isArray(unmeshed) || !unmeshed.length
      || unmeshed.some((ord, index) => !Number.isSafeInteger(ord) || ord < 1 || (index && ord <= unmeshed[index - 1]))) {
      return false;
    }
  }
  return Array.isArray(cad.faceColors) && cad.faceColors.every((color) => finiteTuple(color, 4));
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

// The validated body: its part, counts and every section viewed in place (copied when the
// bytes do not sit on a 4-byte boundary). `part`, when given, is the part it must be.
function decodeBody(bytes, part) {
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
  if (!validCad(cad) || (part !== undefined && cad.part !== part)) return null;
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
  for (const name of CAD_VALUES) values[name] = cad[name];
  if (Object.hasOwn(cad, UNMESHED)) values[UNMESHED] = cad[UNMESHED];
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
    unmeshedFaces: Object.freeze([...(cad[UNMESHED] || [])]),
  };
  const palette = cad.faceColors.length;
  if (!validTable(component.faceTable, indexCount, (count, color) => count % 3 === 0 && color <= palette)
    || !validTable(component.edgeTable, counts.edgePointCount,
      (count, edgeClass) => count >= 2 && edgeClass < MESH_EDGE_CLASSES.length)) return null;
  if (component.unmeshedFaces.length) {
    // Each one is a face of the table, and an empty one.
    const empty = new Set();
    for (let row = 0; row < component.faceTable.length; row += MESH_TABLE_COLUMNS) {
      if (!component.faceTable[row + 2]) empty.add(component.faceTable[row]);
    }
    if (!component.unmeshedFaces.every((ord) => empty.has(ord))) return null;
  }
  return { component, part: cad.part, counts };
}

// A record's facts about one of its objects, exactly `fields` (and `optional`, when present).
function objectFacts(value, fields, optional = []) {
  if (!isObject(value)) return null;
  const keys = Object.keys(value);
  if (keys.some((key) => !fields.includes(key) && !optional.includes(key)) || fields.some((key) => !Object.hasOwn(value, key))) {
    return null;
  }
  if (!SHA256_RE.test(value.object)) return null;
  const facts = { object: value.object };
  for (const key of [...fields, ...optional]) {
    if (key === "object" || !Object.hasOwn(value, key)) continue;
    if (!validCount(value[key])) return null;
    facts[key] = value[key];
  }
  return facts;
}

/**
 * A part's row: its key and its record (cadgen/store/parts.py), checked and frozen —
 * `{part, glb: {object, byteLength, decodedBytes, <counts>, unmeshedFaceCount?}, selectors:
 * {object, byteLength, faceCount, edgeCount, vertexCount}}`. Null for anything else.
 */
export function partRow(part, record) {
  try {
    if (!isPartKey(part) || !isObject(record)) return null;
    const keys = Object.keys(record).filter((key) => key !== "part");
    if (keys.length !== 2 || !keys.includes("glb") || !keys.includes("selectors")
      || (record.part !== undefined && record.part !== part)) return null;
    const glb = objectFacts(record.glb, GLB_FIELDS, [UNMESHED_COUNT]);
    const selectors = objectFacts(record.selectors, SELECTOR_FIELDS);
    if (!glb || !selectors || glb.byteLength < 20 || glb.byteLength % 4 !== 0 || selectors.byteLength < 1
      || glb.decodedBytes !== tessellationDecodedBytes(glb)) return null;
    if (Object.hasOwn(glb, UNMESHED_COUNT) && (glb[UNMESHED_COUNT] < 1 || glb[UNMESHED_COUNT] > glb.faceCount)) return null;
    return Object.freeze({ part, glb: Object.freeze(glb), selectors: Object.freeze(selectors) });
  } catch {
    return null;
  }
}

/**
 * Whether `bytes` are the display mesh `row` names: its part's body, whose framing and counts are
 * the record's. The content address is the provider's to check.
 */
export function partMeshMatches(bytes, row) {
  try {
    const body = decodeBody(bytes, row?.part);
    if (!body) return false;
    const facts = { byteLength: bytes.byteLength, decodedBytes: tessellationDecodedBytes(body.counts), ...body.counts,
      ...(body.component.unmeshedFaces.length ? { [UNMESHED_COUNT]: body.component.unmeshedFaces.length } : {}) };
    const { object: _object, ...expected } = row.glb;
    return sameJson(facts, expected);
  } catch {
    return false;
  }
}

/**
 * One stored mesh, decoded: `component` holds its sections viewed in place -- `positions` and
 * `normals` (f32 xyz), `indices` (u16 or u32), `faceTable` and `edgeTable` (u32 rows of
 * MESH_TABLE_COLUMNS), `edgePoints` (f32 xyz) -- with its face colour palette and bounds, and
 * `unmeshedFaces`: the faces no mesher could cover, which it does not draw. `meshFaceRanges` and
 * `meshEdgePolylines` read the tables as objects. Null for anything that is not a valid body of
 * `part` (any part when it is not given): a corrupt entry is a miss, never an error.
 */
export function decodeComponentTessellation(bytes, { part } = {}) {
  try {
    const body = decodeBody(bytes, part);
    return body ? { component: body.component, part: body.part } : null;
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

/** Where a part's selector table is read (`GET /__tess_cache/<part>.selectors.json`), bound to `row`. */
export function partSelectorsPath(row) {
  return `/__tess_cache/${encodeURIComponent(row.part)}.selectors.json`
    + `?object=${row.selectors.object}&maxBytes=${row.selectors.byteLength}`;
}

// --- batch container ---------------------------------------------------------
//
// One round trip for N bodies: "TESB" u32, version u32, count u32, then per
// entry u32 byteLength (0 = miss) + bytes padded to a 4-byte boundary so each
// entry decodes zero-copy (a GLB body is a 4-byte multiple already). Served by
// both store hosts (the snapshot loopback server and the viewer server) on POST
// <prefix>/batch with a JSON body naming the admitted parts' meshes; this module is
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
    super("A probed part's mesh is no longer readable", options);
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
  // The stored parts of `parts` (keys), as rows by key.
  async function probeCachedTessellationEntries(parts, { signal } = {}) {
    const hits = new Map();
    const provider = disposed ? null : cacheProvider;
    if (!provider || !Array.isArray(parts) || !parts.length) return hits;
    // The HTTP provider refuses oversized metadata requests. Split here so
    // assembly size never silently converts a complete warm store into misses.
    for (let start = 0; start < parts.length; start += TESS_PROBE_MAX_KEYS) {
      const keys = parts.slice(start, start + TESS_PROBE_MAX_KEYS);
      const rows = await provider.probeMany(keys, { signal });
      signal?.throwIfAborted();
      if (!Array.isArray(rows) || rows.length !== keys.length) continue;
      for (let index = 0; index < keys.length; index += 1) {
        const row = partRow(keys[index], rows[index]);
        if (row) hits.set(keys[index], row);
      }
    }
    return hits;
  }

  // The display mesh of `part`, read for `probe` (its row) or for a row probed here.
  async function getCachedEntryBytes(part, {
    signal,
    probe = null,
    strictProbe = false,
  } = {}) {
    const provider = disposed ? null : cacheProvider;
    if (!provider) {
      if (strictProbe) throw new TessellationCacheProbeMissError(probe);
      return null;
    }
    let row = partRow(part, probe);
    if (!row) {
      row = (await probeCachedTessellationEntries([part], { signal })).get(part) || null;
    }
    if (!row) {
      if (strictProbe) throw new TessellationCacheProbeMissError(probe);
      return null;
    }
    let bytes;
    try {
      bytes = await provider.getProbed(row, { signal, maxBytes: row.glb.byteLength });
      signal?.throwIfAborted();
    } catch (error) {
      if (abortError(error, signal) || !strictProbe) throw error;
      throw new TessellationCacheProbeMissError(row, { cause: error });
    }
    if (partMeshMatches(bytes, row)) return bytes;
    if (strictProbe) throw new TessellationCacheProbeMissError(row);
    return null;
  }

  async function getCachedEntryBytesMany(probes, { signal, maxBytes = TESS_BATCH_MAX_BYTES } = {}) {
    const provider = disposed ? null : cacheProvider;
    if (!provider || !Array.isArray(probes) || !probes.length) return null;
    const rows = probes.map((probe) => partRow(probe?.part, probe));
    if (rows.some((row) => !row)) return null;
    const bytes = typeof provider.getManyProbed !== "function"
      ? await Promise.all(rows.map((row) => provider.getProbed(row, {
        signal,
        maxBytes: row.glb.byteLength,
      })))
      : await provider.getManyProbed(rows, { signal, maxBytes });
    signal?.throwIfAborted();
    if (!Array.isArray(bytes) || bytes.length !== rows.length) return null;
    return bytes.map((entry, index) => (partMeshMatches(entry, rows[index]) ? entry : null));
  }

  async function getCachedComponentEntry(part, request = {}) {
    return decodeComponentTessellation(await getCachedEntryBytes(part, request), { part });
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
      probeCachedTessellationEntries: (parts, request) => read("probeCachedTessellationEntries", [parts], request),
      getCachedEntryBytes: (part, request) => read("getCachedEntryBytes", [part], request),
      getCachedEntryBytesMany: (probes, request) => read("getCachedEntryBytesMany", [probes], request),
      getCachedComponentEntry: (part, request) => read("getCachedComponentEntry", [part], request),
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
    probeCachedTessellationEntries: (parts, request) => probeCachedTessellationEntries(parts, requestOptions(request)),
    getCachedEntryBytes: (part, request) => getCachedEntryBytes(part, requestOptions(request)),
    getCachedEntryBytesMany: (probes, request) => getCachedEntryBytesMany(probes, requestOptions(request)),
    getCachedComponentEntry: (part, request) => getCachedComponentEntry(part, requestOptions(request)),
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
  parsed.searchParams.set("object", row.glb.object);
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
  entryUrl = (part) => `${originPrefix(origin)}/__tess_cache/${encodeURIComponent(part)}.glb`,
  probeUrl = `${originPrefix(origin)}/__tess_cache/probe`,
  batchUrl = `${originPrefix(origin)}/__tess_cache/batch`,
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
    async probeMany(parts, { signal } = {}) {
      signal = scopedSignal(signal);
      if (!Array.isArray(parts) || parts.length > TESS_PROBE_MAX_KEYS) return null;
      try {
        const response = await fetchImpl(probeUrl, {
          method: "POST",
          headers: { ...headers, "content-type": "application/json" },
          body: JSON.stringify({ parts }),
          signal,
          cache: "no-store",
        });
        if (!response.ok) return null;
        const payload = await response.json();
        const entries = payload?.entries;
        return parts.map((part) => partRow(part, entries?.[part]));
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return null;
      }
    },
    async getProbed(value, { signal, maxBytes } = {}) {
      signal = scopedSignal(signal);
      const row = partRow(value?.part, value);
      const limit = Number(maxBytes);
      if (!row || !Number.isSafeInteger(limit) || limit < row.glb.byteLength) return null;
      try {
        const response = await fetchImpl(withReadBinding(entryUrl(row.part), row, limit), {
          cache: "no-store", headers, signal,
        });
        if (!response.ok) return null;
        const bytes = await boundedResponseBytes(response, limit);
        // The content address binds the body to its row; the cache checks its facts.
        if (!bytes || await sha256Hex(bytes) !== row.glb.object) return null;
        return bytes;
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return null;
      }
    },
    async getManyProbed(values, { signal, maxBytes = TESS_BATCH_MAX_BYTES } = {}) {
      signal = scopedSignal(signal);
      const rows = values.map((value) => partRow(value?.part, value));
      const limit = Number(maxBytes);
      const framedBytes = 12 + rows.reduce((sum, row) => sum + 4 + (row ? align4(row.glb.byteLength) : 0), 0);
      if (rows.some((row) => !row) || !Number.isSafeInteger(limit)
        || framedBytes > limit || framedBytes > batchCeiling) return null;
      try {
        const response = await fetchImpl(batchUrl, {
          method: "POST",
          headers: { ...headers, "content-type": "application/json" },
          body: JSON.stringify({ entries: rows.map((row) => ({
            part: row.part,
            object: row.glb.object,
            maxBytes: row.glb.byteLength,
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
        return entries.map((entry, index) => (entry && digests[index] === rows[index].glb.object ? entry : null));
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return null;
      }
    },
  };
}

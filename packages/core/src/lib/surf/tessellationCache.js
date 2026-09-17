// THE component-tessellation cache interface (design/unified-tessellation.md
// Phase 3): one key scheme, one codec, shared by every consumer that turns a
// .surf into triangles — the export CLI (bin/mesh-export.mjs), the snapshot
// browser runtime, and the viewer. A cache entry is one FULL
// tessellateComponent result for one component at one tolerance pair, so a
// snapshot warms the cache for an export and vice versa.
//
// This module is BROWSER-PURE: codec and key only, no filesystem. Node
// consumers pair it with tessellationCacheFs.mjs (the shared immutable
// object/index store); browser consumers reach that store through the async
// provider below (the snapshot page's provider round-trips bytes over its
// Playwright-routed /__tess_cache/ origin, served by cadgen's snapshot host).
//
// Entry layout (little-endian): "TESS" magic u32, version u32, headerLength
// u32, JSON header padded with trailing spaces to a 4-byte boundary, then the
// typed-array payload — positions f32, normals f32, faceOrds f32, indices
// u32, sideOrds u32, then each display-edge polyline f32 in header order.
// Every section is 4-byte-sized, so decode returns zero-copy views over the
// source buffer.

import { DEFAULT_OPTIONS, TESSELLATION_VERSION } from "./tessellate.js";

export const TESS_CACHE_MAGIC = 0x53534554; // "TESS" little-endian
// v4: v3's complete render payload plus the exact D/O/L/Q provenance binding.
// A hit therefore proves its concrete render identity without requiring the
// producing SURF object/index to remain present. Non-v4 entries are misses.
export const TESS_CACHE_VERSION = 4;
export const TESS_MESH_INDEX_SCHEMA = 1;
export const TESS_MAX_INDEX_BYTES = 16 * 1024;
export const TESS_MAX_HEADER_BYTES = 4 * 1024 * 1024;

const SHA256_RE = /^[0-9a-f]{64}$/;
const QUALITY_FIELDS = new Set([
  "chordTolerance", "chordToleranceF64", "angleTolerance", "angleToleranceF64",
]);
const EDGE_CLASSES = new Set([
  "none", "feature", "tangent", "seam", "degenerate", "boundary", "nonManifold", "unknown",
]);

function requireDigest(value, label) {
  const digest = typeof value === "string" ? value : "";
  if (!SHA256_RE.test(digest)) {
    throw new TypeError(`${label} must be 64 lowercase hex characters`);
  }
  return digest;
}

export function float64Hex(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new TypeError("tessellation tolerances must be positive finite binary64 values");
  }
  const bytes = new Uint8Array(8);
  new DataView(bytes.buffer).setFloat64(0, value, false);
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

// The tessellation options the KEY spells, and therefore the only ones a
// caller may vary. Every other geometry option in DEFAULT_OPTIONS
// (loopTolerance, maxRefineDepth, minLoopSegments) changes the triangles
// without changing the key, so a run that overrides one would read back
// another run's geometry under its own name. Refusing the key is the only
// answer that cannot silently serve the wrong mesh; keying them instead would
// fork the shared cache for options no caller has ever needed to set.
const KEYED_TESSELLATION_OPTIONS = Object.freeze(["chordTolerance", "angleTolerance"]);
const UNKEYED_TESSELLATION_OPTIONS = Object.freeze(
  Object.keys(DEFAULT_OPTIONS).filter((name) => !KEYED_TESSELLATION_OPTIONS.includes(name)),
);

export function tessellationQuality(options = {}) {
  const unkeyed = UNKEYED_TESSELLATION_OPTIONS.filter((name) => (
    Object.hasOwn(options, name) && options[name] !== DEFAULT_OPTIONS[name]
  ));
  if (unkeyed.length) {
    throw new TypeError(
      `tessellation options are not part of the cache key: ${unkeyed.join(", ")}.`
      + ` Keyed options: ${KEYED_TESSELLATION_OPTIONS.join(", ")}`,
    );
  }
  const effective = { ...DEFAULT_OPTIONS, ...options };
  const chordTolerance = effective.chordTolerance;
  const angleTolerance = effective.angleTolerance;
  return Object.freeze({
    chordTolerance,
    chordToleranceF64: float64Hex(chordTolerance),
    angleTolerance,
    angleToleranceF64: float64Hex(angleTolerance),
  });
}

// L is available before SURF output bytes: D already binds geometry and the
// frozen surface producer. Lossless f64 spelling prevents distinct accepted
// tolerances from colliding. The v4 payload version is part of the key because
// pre-v4 bytes cannot prove the full provenance contract.
export function tessellationCacheKey(surfaceInput, options = {}) {
  const digest = requireDigest(surfaceInput, "surfaceInput");
  const quality = tessellationQuality(options);
  return `${digest}-t${TESSELLATION_VERSION}-p${TESS_CACHE_VERSION}`
    + `-l${quality.chordToleranceF64}-a${quality.angleToleranceF64}`;
}

// R is the concrete display/selector identity. A warm v4 TESS header carries
// O, so R remains discoverable even after the SURF object and index are gone.
export function resolvedTessellationIdentity(surfaceInput, surfaceObject, options = {}) {
  const key = tessellationCacheKey(surfaceInput, options);
  return `${key}-s${requireDigest(surfaceObject, "surfaceObject")}`;
}

// Debug toggles change the geometry or bloat the result; those runs must
// neither read nor write the shared cache.
export function tessellationOptionsCacheable(options = {}) {
  return !options.collectBoundaryDebug && !options.noSharedBoundaries && !options.noConformPass;
}

function align4(value) {
  return (value + 3) & ~3;
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function finiteTuple(value, length) {
  return Array.isArray(value) && value.length === length
    && value.every((entry) => typeof entry === "number" && Number.isFinite(entry));
}

function validOrdinal(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function edgeClassMap(value) {
  if (!Array.isArray(value)) return null;
  const result = new Map();
  for (const entry of value) {
    if (!Array.isArray(entry) || entry.length !== 2
      || !validOrdinal(entry[0]) || !EDGE_CLASSES.has(entry[1])
      || result.has(entry[0])) return null;
    result.set(entry[0], entry[1]);
  }
  return result;
}

function validRenderingMetadata(header) {
  if (!isObject(header?.bounds)
    || !finiteTuple(header.bounds.min, 3) || !finiteTuple(header.bounds.max, 3)
    || header.bounds.min.some((value, index) => value > header.bounds.max[index])
    || typeof header.scale !== "number" || !Number.isFinite(header.scale) || header.scale <= 0
    || (header.partColor != null && !finiteTuple(header.partColor, 4))
    || !Array.isArray(header.faceRanges) || !Array.isArray(header.edges)) return false;

  const faceOrds = new Set();
  let indexCursor = 0;
  for (const range of header.faceRanges) {
    if (!isObject(range) || !validOrdinal(range.ord) || faceOrds.has(range.ord)
      || !validCount(range.indexStart) || !validCount(range.indexCount)
      || range.indexStart % 3 !== 0 || range.indexCount % 3 !== 0
      || range.indexStart !== indexCursor
      || (range.color != null && !finiteTuple(range.color, 4))) return false;
    faceOrds.add(range.ord);
    indexCursor += range.indexCount;
    if (!Number.isSafeInteger(indexCursor)) return false;
  }
  if (indexCursor !== header.indexCount) return false;

  const classes = edgeClassMap(header.edgeClasses);
  if (!classes) return false;
  const edgeOrds = new Set();
  for (const edge of header.edges) {
    if (!isObject(edge) || !validOrdinal(edge.ord) || edgeOrds.has(edge.ord)
      || !validCount(edge.count) || edge.count % 3 !== 0
      || (edge.visibilityClass != null && !EDGE_CLASSES.has(edge.visibilityClass))
      || !classes.has(edge.ord)
      || (edge.visibilityClass != null && classes.get(edge.ord) !== edge.visibilityClass)) return false;
    edgeOrds.add(edge.ord);
  }
  return true;
}

// `index.edges` -> the compact [ord, class] pairs the header stores. Callers
// that hold the parsed surf index pass this so a later hit can skip the surf.
export function edgeClassesFromSurfIndex(index) {
  const edges = Array.isArray(index?.edges) ? index.edges : [];
  return edges.map((edge) => [edge.ord, String(edge.class ?? "none")]);
}

export function encodeComponentTessellation(component, {
  partColor = null,
  edgeClasses = null,
  surfaceInput,
  surfaceObject,
  tessellation = {},
} = {}) {
  const edges = Array.isArray(component.edges) ? component.edges : [];
  if (!Array.isArray(component.faceRanges) || !Array.isArray(edgeClasses)) {
    throw new TypeError("TESS v4 requires complete faceRanges and edgeClasses metadata");
  }
  const quality = tessellationQuality(tessellation);
  const tessellationInput = tessellationCacheKey(surfaceInput, tessellation);
  const surfaceDigest = requireDigest(surfaceObject, "surfaceObject");
  const header = {
    tessellationInput,
    surfaceInput: requireDigest(surfaceInput, "surfaceInput"),
    surfaceDigest,
    quality,
    tessellatorVersion: TESSELLATION_VERSION,
    payloadVersion: TESS_CACHE_VERSION,
    partColor: partColor ?? null,
    edgeClasses,
    faceRanges: component.faceRanges,
    bounds: { min: [...component.bounds.min], max: [...component.bounds.max] },
    scale: component.scale,
    positionCount: component.positions.length,
    normalCount: component.normals.length,
    faceOrdCount: component.faceOrds.length,
    indexCount: component.indices.length,
    sideOrdCount: component.sideOrds.length,
    edges: edges.map((edge) => ({
      ord: edge.ord,
      visibilityClass: edge.visibilityClass ?? null,
      count: edge.polyline.length,
    })),
  };
  if (!validRenderingMetadata(header)) {
    throw new TypeError("TESS v4 requires valid complete rendering metadata");
  }
  const headerJson = JSON.stringify(header);
  const headerBytes = new TextEncoder().encode(headerJson);
  // Pad the header with spaces (valid JSON whitespace) so the payload starts
  // 4-byte aligned and decode can hand out views instead of copies.
  const headerLength = align4(headerBytes.length);
  const payloadFloats =
    component.positions.length +
    component.normals.length +
    component.faceOrds.length +
    component.indices.length +
    component.sideOrds.length +
    edges.reduce((sum, edge) => sum + edge.polyline.length, 0);
  const bytes = new Uint8Array(12 + headerLength + payloadFloats * 4);
  const view = new DataView(bytes.buffer);
  view.setUint32(0, TESS_CACHE_MAGIC, true);
  view.setUint32(4, TESS_CACHE_VERSION, true);
  view.setUint32(8, headerLength, true);
  bytes.set(headerBytes, 12);
  bytes.fill(0x20, 12 + headerBytes.length, 12 + headerLength);
  let offset = 12 + headerLength;
  const append = (array, Ctor) => {
    new Ctor(bytes.buffer, offset, array.length).set(array);
    offset += array.length * 4;
  };
  append(component.positions, Float32Array);
  append(component.normals, Float32Array);
  append(component.faceOrds, Float32Array);
  append(component.indices, Uint32Array);
  append(component.sideOrds, Uint32Array);
  for (const edge of edges) append(edge.polyline, Float32Array);
  return bytes;
}

function validCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

export function tessellationDecodedBytes({
  headerBytes,
  arrayBytes,
  faceRangeCount,
  edgeCount,
  edgeClassCount,
  edgeSegmentCount,
}) {
  const values = [headerBytes, arrayBytes, faceRangeCount, edgeCount, edgeClassCount, edgeSegmentCount];
  if (!values.every(validCount) || headerBytes <= 0 || headerBytes > TESS_MAX_HEADER_BYTES
    || headerBytes % 4 !== 0 || arrayBytes % 4 !== 0) {
    throw new TypeError("invalid tessellation size facts");
  }
  const decodedBytes = arrayBytes + 8 * edgeSegmentCount + 8 * headerBytes
    + 256 * (faceRangeCount + edgeCount + edgeClassCount);
  if (!Number.isSafeInteger(decodedBytes)) {
    throw new TypeError("tessellation decoded size exceeds the safe integer range");
  }
  return decodedBytes;
}

function decodedIdentity(header, expected = {}) {
  try {
    if (header?.tessellatorVersion !== TESSELLATION_VERSION
      || header?.payloadVersion !== TESS_CACHE_VERSION) return null;
    const surfaceInput = requireDigest(header.surfaceInput, "surfaceInput");
    const surfaceObject = requireDigest(header.surfaceDigest, "surfaceDigest");
    const quality = header.quality;
    if (!quality || typeof quality !== "object" || Array.isArray(quality)
      || Object.keys(quality).length !== QUALITY_FIELDS.size
      || Object.keys(quality).some((key) => !QUALITY_FIELDS.has(key))) return null;
    const normalized = tessellationQuality({
      chordTolerance: quality.chordTolerance,
      angleTolerance: quality.angleTolerance,
    });
    if (quality.chordToleranceF64 !== normalized.chordToleranceF64
      || quality.angleToleranceF64 !== normalized.angleToleranceF64) return null;
    const tessellationInput = tessellationCacheKey(surfaceInput, normalized);
    if (header.tessellationInput !== tessellationInput) return null;
    const renderIdentity = resolvedTessellationIdentity(surfaceInput, surfaceObject, normalized);

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
      payloadVersion: TESS_CACHE_VERSION,
    });
  } catch {
    return null;
  }
}

function decodeEnvelope(bytes, expected = {}) {
  if (!(bytes instanceof Uint8Array) || bytes.length < 12) return null;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.getUint32(0, true) !== TESS_CACHE_MAGIC) return null;
  if (view.getUint32(4, true) !== TESS_CACHE_VERSION) return null;
  const headerLength = view.getUint32(8, true);
  if (headerLength === 0 || headerLength > TESS_MAX_HEADER_BYTES
    || headerLength % 4 !== 0 || 12 + headerLength > bytes.length) return null;
  const header = JSON.parse(
    new TextDecoder().decode(bytes.subarray(12, 12 + headerLength)),
  );
  const identity = decodedIdentity(header, expected);
  if (!identity || !Array.isArray(header.edges)
    || !Array.isArray(header.faceRanges) || !Array.isArray(header.edgeClasses)) return null;
  const baseCounts = [
    header.positionCount,
    header.normalCount,
    header.faceOrdCount,
    header.indexCount,
    header.sideOrdCount,
  ];
  const edgeCounts = header.edges.map((edge) => edge?.count);
  const counts = [...baseCounts, ...edgeCounts];
  if (!counts.every(validCount)
    || header.positionCount % 3 !== 0
    || header.normalCount !== header.positionCount
    || header.faceOrdCount * 3 !== header.positionCount
    || header.indexCount % 3 !== 0
    || header.sideOrdCount !== header.indexCount
    || edgeCounts.some((count) => count % 3 !== 0)
    || !validRenderingMetadata(header)) return null;
  const elementCount = counts.reduce((sum, count) => sum + count, 0);
  if (!Number.isSafeInteger(elementCount) || elementCount > Number.MAX_SAFE_INTEGER / 4) return null;
  const arrayBytes = elementCount * 4;
  if (bytes.length !== 12 + headerLength + arrayBytes) return null;
  const sizes = Object.freeze({
    headerBytes: headerLength,
    arrayBytes,
    faceRangeCount: header.faceRanges.length,
    edgeCount: header.edges.length,
    edgeClassCount: header.edgeClasses.length,
    edgeSegmentCount: edgeCounts.reduce((sum, count) => sum + Math.max(0, count / 3 - 1), 0),
  });
  const decodedBytes = tessellationDecodedBytes(sizes);
  return { header, identity, sizes, decodedBytes };
}

export function tessellationPayloadFacts(bytes, expected = {}) {
  try {
    const envelope = decodeEnvelope(bytes, expected);
    if (!envelope) return null;
    const facts = Object.freeze({
      byteLength: bytes.byteLength,
      decodedBytes: envelope.decodedBytes,
      surfaceInput: envelope.identity.surfaceInput,
      surfaceObject: envelope.identity.surfaceObject,
      tessellationInput: envelope.identity.tessellationInput,
      renderIdentity: envelope.identity.renderIdentity,
      quality: envelope.identity.quality,
      tessellatorVersion: TESSELLATION_VERSION,
      payloadVersion: TESS_CACHE_VERSION,
      ...envelope.sizes,
    });
    for (const field of [
      "byteLength", "decodedBytes", "surfaceInput", "surfaceObject", "tessellationInput",
      "renderIdentity", "tessellatorVersion", "payloadVersion", "headerBytes", "arrayBytes",
      "faceRangeCount", "edgeCount", "edgeClassCount", "edgeSegmentCount",
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
  "headerBytes", "arrayBytes", "faceRangeCount", "edgeCount", "edgeClassCount", "edgeSegmentCount",
]);

export function validateTessellationProbeRow(value, expected = {}) {
  try {
    if (!value || typeof value !== "object" || Array.isArray(value)
      || Object.keys(value).length !== MESH_RECORD_FIELDS.size
      || Object.keys(value).some((key) => !MESH_RECORD_FIELDS.has(key))) return null;
    if (value.schemaVersion !== TESS_MESH_INDEX_SCHEMA
      || value.tessellatorVersion !== TESSELLATION_VERSION
      || value.payloadVersion !== TESS_CACHE_VERSION) return null;
    const surfaceInput = requireDigest(value.surfaceInput, "surfaceInput");
    const surfaceObject = requireDigest(value.surfaceObject, "surfaceObject");
    const object = requireDigest(value.object, "object");
    const quality = tessellationQuality({
      chordTolerance: value.quality?.chordTolerance,
      angleTolerance: value.quality?.angleTolerance,
    });
    if (value.quality?.chordToleranceF64 !== quality.chordToleranceF64
      || value.quality?.angleToleranceF64 !== quality.angleToleranceF64) return null;
    const tessellationInput = tessellationCacheKey(surfaceInput, quality);
    const renderIdentity = resolvedTessellationIdentity(surfaceInput, surfaceObject, quality);
    if (value.tessellationInput !== tessellationInput || value.renderIdentity !== renderIdentity) return null;
    const sizeFields = {
      headerBytes: value.headerBytes,
      arrayBytes: value.arrayBytes,
      faceRangeCount: value.faceRangeCount,
      edgeCount: value.edgeCount,
      edgeClassCount: value.edgeClassCount,
      edgeSegmentCount: value.edgeSegmentCount,
    };
    if (!validCount(value.byteLength) || value.byteLength <= 0
      || value.byteLength !== 12 + value.headerBytes + value.arrayBytes
      || value.decodedBytes !== tessellationDecodedBytes(sizeFields)) return null;
    if (expected.tessellationInput !== undefined && expected.tessellationInput !== tessellationInput) return null;
    if (expected.object !== undefined && expected.object !== object) return null;
    if (expected.surfaceInput !== undefined && expected.surfaceInput !== surfaceInput) return null;
    if (expected.surfaceObject !== undefined && expected.surfaceObject !== surfaceObject) return null;
    return Object.freeze({
      schemaVersion: TESS_MESH_INDEX_SCHEMA,
      object,
      byteLength: value.byteLength,
      decodedBytes: value.decodedBytes,
      surfaceInput,
      surfaceObject,
      tessellationInput,
      renderIdentity,
      quality,
      tessellatorVersion: TESSELLATION_VERSION,
      payloadVersion: TESS_CACHE_VERSION,
      ...sizeFields,
    });
  } catch {
    return null;
  }
}

export function decodeComponentTessellation(bytes, expected = {}) {
  try {
    const envelope = decodeEnvelope(bytes, expected);
    if (!envelope) return null;
    const { header, identity } = envelope;
    let offset = bytes.byteOffset + 12 + envelope.sizes.headerBytes;
    // Zero-copy views are only sound on 4-byte-aligned offsets; a misaligned
    // source buffer (e.g. a subarray) falls back to copying via slice.
    const aligned = offset % 4 === 0;
    const take = (count, Ctor) => {
      const section = aligned
        ? new Ctor(bytes.buffer, offset, count)
        : new Ctor(bytes.buffer.slice(offset, offset + count * 4));
      offset += count * 4;
      return section;
    };
    const positions = take(header.positionCount, Float32Array);
    const normals = take(header.normalCount, Float32Array);
    const faceOrds = take(header.faceOrdCount, Float32Array);
    const indices = take(header.indexCount, Uint32Array);
    const sideOrds = take(header.sideOrdCount, Uint32Array);
    const edges = header.edges.map((edge) => ({
      ord: edge.ord,
      visibilityClass: edge.visibilityClass,
      polyline: take(edge.count, Float32Array),
    }));
    return {
      component: {
        positions,
        normals,
        faceOrds,
        indices,
        sideOrds,
        faceRanges: header.faceRanges,
        edges,
        bounds: header.bounds,
        scale: header.scale,
      },
      partColor: header.partColor ?? null,
      edgeClasses: Array.isArray(header.edgeClasses) ? header.edgeClasses : null,
      identity,
    };
  } catch {
    return null; // a corrupt entry is a miss, never an error
  }
}

// The minimal stand-in for a parsed surf index that render consumers
// (buildMeshDataFromSurf) read on a cache hit: per-edge classes and the part
// color. Null when the entry predates edgeClasses — the caller then needs the
// real surf.
export function surfIndexFromCacheEntry(decoded) {
  const classes = edgeClassMap(decoded?.edgeClasses);
  if (!classes) return null;
  return {
    edges: [...classes].map(([ord, cls]) => ({ ord, class: cls })),
    partColor: decoded.partColor ?? null,
  };
}

// --- batch container ---------------------------------------------------------
//
// One round trip for N entries: "TESB" u32, version u32, count u32, then per
// entry u32 byteLength (0 = miss) + bytes padded to a 4-byte boundary so each
// entry decodes zero-copy. Served by both cache hosts (the snapshot loopback
// server and the viewer server) on POST <prefix>/batch with a JSON body of
// entry file names; this module is the format's single home.

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

// Each render session owns its provider, request cancellation, and write queue.
// A provider is never installed into module state: concurrent roots stay independent.
export function createTessellationCache({ provider = null, writeBack = {} } = {}) {
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
  async function probeCachedTessellationEntries(surfaceInputs, options = {}, { signal } = {}) {
    const hits = new Map();
    const provider = disposed ? null : cacheProvider;
    if (!provider || !Array.isArray(surfaceInputs) || !surfaceInputs.length
      || !tessellationOptionsCacheable(options)) return hits;
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

  async function getCachedEntryBytes(surfaceInput, options = {}, {
    signal,
    probe = null,
    strictProbe = false,
  } = {}) {
    const provider = disposed ? null : cacheProvider;
    if (!provider || !tessellationOptionsCacheable(options)) {
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

  async function getCachedComponentEntry(surfaceInput, options = {}, request = {}) {
    const bytes = await getCachedEntryBytes(surfaceInput, options, request);
    return decodeComponentTessellation(bytes, {
      surfaceInput,
      ...(request.probe?.surfaceObject ? { surfaceObject: request.probe.surfaceObject } : {}),
      tessellationInput: tessellationCacheKey(surfaceInput, options),
      tessellation: options,
    });
  }

  let writeBackPolicy = { deferMs: 0, concurrency: Infinity, maxPendingBytes: TESS_BATCH_MAX_BYTES };
  const pendingWriteBacks = new Map();
  let pendingWriteBackBytes = 0;
  let activeWriteBackBytes = 0;
  let writeBackTimer = null;
  let writeBackDrain = null;

  function configureTessellationCacheWriteBack({ deferMs = 0, concurrency = Infinity, maxPendingBytes = TESS_BATCH_MAX_BYTES } = {}) {
    writeBackPolicy = {
      deferMs: Number.isFinite(deferMs) && deferMs > 0 ? deferMs : 0,
      concurrency: Number.isFinite(concurrency) && concurrency >= 1 ? Math.floor(concurrency) : Infinity,
      maxPendingBytes: Number.isSafeInteger(maxPendingBytes) && maxPendingBytes >= 0 ? maxPendingBytes : TESS_BATCH_MAX_BYTES,
    };
  }

  async function putEntry(key, bytes) {
    const provider = disposed ? null : cacheProvider;
    if (!provider || typeof provider.put !== "function") return;
    try {
      await provider.put(key, bytes, { signal: lifetime.signal });
    } catch {
      // best-effort write-back
    }
  }

  async function drainWriteBacks() {
    const limit = writeBackPolicy.concurrency;
    const queue = [...pendingWriteBacks.entries()];
    pendingWriteBacks.clear();
    activeWriteBackBytes += pendingWriteBackBytes;
    pendingWriteBackBytes = 0;
    let next = 0;
    const lane = async () => {
      while (next < queue.length) {
        const [key, bytes] = queue[next];
        next += 1;
        try {
          await putEntry(key, bytes);
        } finally {
          activeWriteBackBytes -= bytes.byteLength;
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(queue.length, Number.isFinite(limit) ? limit : queue.length) }, lane));
  }

  /** Write every deferred entry now. Resolves when the drain (and any running one) is done. */
  async function flushTessellationCacheWriteBacks() {
    if (writeBackTimer) {
      clearTimeout(writeBackTimer);
      writeBackTimer = null;
    }
    if (writeBackDrain) {
      await writeBackDrain;
    }
    if (pendingWriteBacks.size) {
      writeBackDrain = drainWriteBacks().finally(() => {
        writeBackDrain = null;
      });
      await writeBackDrain;
    }
  }

  function scheduleWriteBackDrain() {
    if (writeBackTimer) {
      clearTimeout(writeBackTimer);
    }
    writeBackTimer = setTimeout(() => {
      writeBackTimer = null;
      void flushTessellationCacheWriteBacks();
    }, writeBackPolicy.deferMs);
  }


  async function writeBackEntryBytes(surfaceInput, options, bytes) {
    const provider = disposed ? null : cacheProvider;
    if (!provider || typeof provider.put !== "function" || !tessellationOptionsCacheable(options)) return null;
    const key = tessellationCacheKey(surfaceInput, options);
    if (!tessellationPayloadFacts(bytes, { surfaceInput, tessellationInput: key, tessellation: options })) return null;
    if (writeBackPolicy.deferMs > 0) {
      const previousBytes = pendingWriteBacks.get(key)?.byteLength || 0;
      const nextBytes = pendingWriteBackBytes + bytes.byteLength - previousBytes;
      // Deferred writes are optional cache warming. Never retain an unbounded
      // assembly of encoded bodies beside its render-owned arrays.
      if (nextBytes + activeWriteBackBytes > writeBackPolicy.maxPendingBytes) return null;
      pendingWriteBacks.set(key, bytes);
      pendingWriteBackBytes = nextBytes;
      scheduleWriteBackDrain();
      return null;
    }
    return putEntry(key, bytes);
  }

  async function writeBackComponentEntry(surfaceInput, surfaceObject, options, component, index) {
    if (!cacheProvider || !surfaceInput || !surfaceObject || !tessellationOptionsCacheable(options)) return null;
    return writeBackEntryBytes(surfaceInput, options, encodeComponentTessellation(component, {
      surfaceInput, surfaceObject, tessellation: options,
      partColor: Array.isArray(index?.partColor) ? index.partColor : null,
      edgeClasses: edgeClassesFromSurfIndex(index),
    }));
  }

  configureTessellationCacheWriteBack(writeBack);
  return {
    tessellationCacheProviderRegistered,
    probeCachedTessellationEntries: (inputs, options, request) => probeCachedTessellationEntries(inputs, options, requestOptions(request)),
    getCachedEntryBytes: (input, options, request) => getCachedEntryBytes(input, options, requestOptions(request)),
    getCachedEntryBytesMany: (probes, request) => getCachedEntryBytesMany(probes, requestOptions(request)),
    getCachedComponentEntry: (input, options, request) => getCachedComponentEntry(input, options, requestOptions(request)),
    configureTessellationCacheWriteBack,
    flushTessellationCacheWriteBacks,
    writeBackEntryBytes,
    writeBackComponentEntry,
    memoryStats: () => ({ pendingWriteBackBytes, activeWriteBackBytes, writeBackBytes: pendingWriteBackBytes + activeWriteBackBytes }),
    dispose() {
      if (disposed) return;
      disposed = true;
      lifetime.abort();
      cacheProvider = null;
      if (writeBackTimer) clearTimeout(writeBackTimer);
      writeBackTimer = null;
      pendingWriteBacks.clear();
      pendingWriteBackBytes = 0;
    },
  };
}
export const TESS_PROBE_MAX_KEYS = 256;
export const TESS_BATCH_MAX_BYTES = 32 * 1024 * 1024;

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
  entryUrl = (key) => `${originPrefix(origin)}/__tess_cache/${encodeURIComponent(key)}.tess`,
  probeUrl = `${originPrefix(origin)}/__tess_cache/probe`,
  batchUrl = `${originPrefix(origin)}/__tess_cache/batch`,
  headers = {},
  fetch: fetchImpl = globalThis.fetch,
  signal: lifetimeSignal,
} = {}) {
  const scopedSignal = (signal) => lifetimeSignal && signal
    ? AbortSignal.any([lifetimeSignal, signal]) : lifetimeSignal || signal;
  return {
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
        if (!bytes || await sha256Hex(bytes) !== row.object
          || !tessellationPayloadFacts(bytes, row)) return null;
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
        || framedBytes > limit || framedBytes > TESS_BATCH_MAX_BYTES) return null;
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
        for (let index = 0; index < rows.length; index += 1) {
          if (!entries[index] || await sha256Hex(entries[index]) !== rows[index].object
            || !tessellationPayloadFacts(entries[index], rows[index])) return null;
        }
        return entries;
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return null;
      }
    },
    async put(key, bytes, { signal } = {}) {
      signal = scopedSignal(signal);
      try {
        const response = await fetchImpl(entryUrl(key), { method: "POST", body: bytes, headers, signal });
        return response.ok;
      } catch (error) {
        if (abortError(error, signal)) throw error;
        return false;
      }
    },
  };
}

// THE component-tessellation cache interface (design/unified-tessellation.md
// Phase 3): one key scheme, one codec, shared by every consumer that turns a
// .surf into triangles — the export CLI (bin/mesh-export.mjs), the snapshot
// browser runtime, and later the viewer (Phase 5). A cache entry is one FULL
// tessellateComponent result for one component at one tolerance pair, so a
// snapshot warms the cache for an export and vice versa.
//
// This module is BROWSER-PURE: codec and key only, no filesystem. Node
// consumers pair it with tessellationCacheFs.mjs (the ~/.cache/cadgen/meshes
// store); browser consumers reach a store through the pluggable async
// provider below (the snapshot page's provider round-trips bytes over its
// Playwright-routed /__tess_cache/ origin, served by cadgen's snapshot host).
//
// Entry layout (little-endian): "TESS" magic u32, version u32, headerLength
// u32, JSON header padded with trailing spaces to a 4-byte boundary, then the
// typed-array payload — positions f32, normals f32, faceOrds f32, indices
// u32, sideOrds u32, then each display-edge polyline f32 in header order.
// Every section is 4-byte-sized, so decode returns zero-copy views over the
// source buffer.

import { DEFAULT_OPTIONS, TESSELLATION_VERSION, tessellateComponent } from "./tessellate.js";

export const TESS_CACHE_MAGIC = 0x53534554; // "TESS" little-endian
// v3: header carries edgeClasses (every surf edge's ord -> class string) and
// partColor, so a HIT rebuilds render meshData without fetching the .surf at
// all (surfMeshData needs exactly those two index fields). v2 carried the
// full component payload but still required the surf for edge classes; v1
// stored the export subset only. Older versions are ordinary misses.
export const TESS_CACHE_VERSION = 3;

// The key covers the WHOLE function from surf to triangles: component
// geometry (cid), tessellator algorithm (-t<TESSELLATION_VERSION>-), and the
// tolerances, formatted canonically so 0.0015 and 1.5e-3 hit the same entry.
// Dropping the version salt would serve stale triangles across algorithm
// changes — a policy test pins its presence.
export function tessellationCacheKey(cid, options = {}) {
  const effective = { ...DEFAULT_OPTIONS, ...options };
  const num = (value) => Number(value).toExponential(6);
  return `${cid}-t${TESSELLATION_VERSION}-l${num(effective.chordTolerance)}-a${num(effective.angleTolerance)}`;
}

// Debug toggles change the geometry or bloat the result; those runs must
// neither read nor write the shared cache.
export function tessellationOptionsCacheable(options = {}) {
  return !options.collectBoundaryDebug && !options.noSharedBoundaries && !options.noConformPass;
}

function align4(value) {
  return (value + 3) & ~3;
}

// `index.edges` -> the compact [ord, class] pairs the header stores. Callers
// that hold the parsed surf index pass this so a later hit can skip the surf.
export function edgeClassesFromSurfIndex(index) {
  const edges = Array.isArray(index?.edges) ? index.edges : [];
  return edges.map((edge) => [edge.ord, String(edge.class ?? "none")]);
}

export function encodeComponentTessellation(component, { partColor = null, edgeClasses = null } = {}) {
  const edges = Array.isArray(component.edges) ? component.edges : [];
  const headerJson = JSON.stringify({
    partColor: partColor ?? null,
    edgeClasses: Array.isArray(edgeClasses) ? edgeClasses : null,
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
  });
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

export function decodeComponentTessellation(bytes) {
  try {
    if (!(bytes instanceof Uint8Array) || bytes.length < 12) return null;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (view.getUint32(0, true) !== TESS_CACHE_MAGIC) return null;
    if (view.getUint32(4, true) !== TESS_CACHE_VERSION) return null;
    const headerLength = view.getUint32(8, true);
    const header = JSON.parse(
      new TextDecoder().decode(bytes.subarray(12, 12 + headerLength)),
    );
    let offset = bytes.byteOffset + 12 + headerLength;
    const expect =
      (header.positionCount +
        header.normalCount +
        header.faceOrdCount +
        header.indexCount +
        header.sideOrdCount +
        header.edges.reduce((sum, edge) => sum + edge.count, 0)) * 4;
    if (bytes.byteOffset + bytes.byteLength - offset !== expect) return null;
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
  if (!decoded || !Array.isArray(decoded.edgeClasses)) return null;
  return {
    edges: decoded.edgeClasses.map(([ord, cls]) => ({ ord, class: cls })),
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
      offset += align4(length);
    }
    return entries;
  } catch {
    return null;
  }
}

// --- pluggable store (browser consumers) -----------------------------------
//
// get(key) -> Promise<Uint8Array|null>, put(key, bytes) -> Promise<void>.
// Both are best-effort: any throw is treated as a miss / ignored. No provider
// registered (the default — e.g. the viewer today) means every call
// tessellates exactly as before.

let cacheProvider = null;

export function setTessellationCacheProvider(provider) {
  cacheProvider = provider && typeof provider.get === "function" ? provider : null;
}

export function tessellationCacheProviderRegistered() {
  return cacheProvider !== null;
}

// Decoded entry for one component, from the registered provider alone — the
// caller can skip fetching the surf entirely when this answers (v3 entries
// carry the index fields render meshData needs). Null on miss/any failure.
export async function getCachedComponentEntry(cid, options = {}) {
  const provider = cacheProvider;
  if (!provider || !cid || !tessellationOptionsCacheable(options)) return null;
  try {
    return decodeComponentTessellation(await provider.get(tessellationCacheKey(cid, options)));
  } catch {
    return null;
  }
}

// Batch form: Map(cid -> decoded entry) containing HITS only. One round trip
// when the provider supports getMany; falls back to per-key gets otherwise.
export async function getCachedComponentEntries(cids, options = {}) {
  const hits = new Map();
  const provider = cacheProvider;
  if (!provider || !cids.length || !tessellationOptionsCacheable(options)) return hits;
  const keys = cids.map((cid) => tessellationCacheKey(cid, options));
  let raw = null;
  if (typeof provider.getMany === "function") {
    try {
      raw = await provider.getMany(keys);
    } catch {
      raw = null;
    }
  }
  if (!Array.isArray(raw) || raw.length !== keys.length) {
    raw = await Promise.all(keys.map(async (key) => {
      try {
        return await provider.get(key);
      } catch {
        return null;
      }
    }));
  }
  for (let i = 0; i < cids.length; i += 1) {
    const decoded = decodeComponentTessellation(raw[i]);
    if (decoded) hits.set(cids[i], decoded);
  }
  return hits;
}

// --- priming: one round trip for a whole assembly's hit set ----------------
//
// A component load asks the cache per component (`getCachedEntryBytes`), and
// over HTTP that is one request per component: a 483-component assembly made
// 483 GETs to a single-process backend that was also streaming its 483 surfs,
// and the round trips cost more than the tessellation they skipped. The batch
// route (`getMany`) exists for exactly this; priming asks it once for every
// cid up front and parks the answers — hits AND known misses — for the
// per-component reads to take. An entry is taken once (a second read for the
// same key goes back to the provider), so a primed set never goes stale past
// the load it was primed for.

const primedEntries = new Map();
const PRIME_CHUNK = 1024;

export async function primeCachedEntryBytes(cids, options = {}) {
  const provider = cacheProvider;
  const unique = [...new Set((cids || []).filter(Boolean))];
  if (!provider || typeof provider.getMany !== "function" || !unique.length) return 0;
  if (!tessellationOptionsCacheable(options)) return 0;
  let hits = 0;
  for (let start = 0; start < unique.length; start += PRIME_CHUNK) {
    const chunk = unique.slice(start, start + PRIME_CHUNK);
    const keys = chunk.map((cid) => tessellationCacheKey(cid, options));
    let raw = null;
    try {
      raw = await provider.getMany(keys);
    } catch {
      raw = null;
    }
    if (!Array.isArray(raw) || raw.length !== keys.length) {
      continue; // no batch route: the per-component reads ask as before
    }
    for (let i = 0; i < keys.length; i += 1) {
      const bytes = raw[i] instanceof Uint8Array && raw[i].length ? raw[i] : null;
      primedEntries.set(keys[i], bytes);
      if (bytes) hits += 1;
    }
  }
  return hits;
}

export function clearPrimedEntries() {
  primedEntries.clear();
}

// Raw entry bytes for one component — for callers that hand the entry to a
// worker (transfer) instead of decoding on this thread. Null on miss/failure.
// A primed answer is taken first, once.
export async function getCachedEntryBytes(cid, options = {}) {
  const provider = cacheProvider;
  if (!provider || !cid || !tessellationOptionsCacheable(options)) return null;
  const key = tessellationCacheKey(cid, options);
  if (primedEntries.has(key)) {
    const primed = primedEntries.get(key);
    primedEntries.delete(key);
    return primed;
  }
  try {
    const bytes = await provider.get(key);
    return bytes instanceof Uint8Array ? bytes : null;
  } catch {
    return null;
  }
}

// --- write-back scheduling --------------------------------------------------
//
// The default is immediate: a miss is written back the moment the worker
// hands its entry over, which is what a snapshot or an export wants (the page
// is gone right after). A viewer loading a large assembly wants the opposite —
// hundreds of PUTs racing the surf fetches on the same backend doubled a cold
// open — so a host may defer them: writes queue until `deferMs` has passed
// with no new one, then drain `concurrency` at a time.

let writeBackPolicy = { deferMs: 0, concurrency: Infinity };
const pendingWriteBacks = new Map();
let writeBackTimer = null;
let writeBackDrain = null;

export function configureTessellationCacheWriteBack({ deferMs = 0, concurrency = Infinity } = {}) {
  writeBackPolicy = {
    deferMs: Number.isFinite(deferMs) && deferMs > 0 ? deferMs : 0,
    concurrency: Number.isFinite(concurrency) && concurrency >= 1 ? Math.floor(concurrency) : Infinity,
  };
}

async function putEntry(key, bytes) {
  const provider = cacheProvider;
  if (!provider || typeof provider.put !== "function") return;
  try {
    await provider.put(key, bytes);
  } catch {
    // best-effort write-back
  }
}

async function drainWriteBacks() {
  const limit = writeBackPolicy.concurrency;
  const queue = [...pendingWriteBacks.entries()];
  pendingWriteBacks.clear();
  let next = 0;
  const lane = async () => {
    while (next < queue.length) {
      const [key, bytes] = queue[next];
      next += 1;
      await putEntry(key, bytes);
    }
  };
  await Promise.all(Array.from({ length: Math.min(queue.length, Number.isFinite(limit) ? limit : queue.length) }, lane));
}

/** Write every deferred entry now. Resolves when the drain (and any running one) is done. */
export async function flushTessellationCacheWriteBacks() {
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

// Raw write-back for entry bytes a worker already encoded.
export async function writeBackEntryBytes(cid, options, bytes) {
  const provider = cacheProvider;
  if (!provider || typeof provider.put !== "function" || !cid) return;
  if (!tessellationOptionsCacheable(options) || !(bytes instanceof Uint8Array)) return;
  const key = tessellationCacheKey(cid, options);
  if (writeBackPolicy.deferMs > 0) {
    pendingWriteBacks.set(key, bytes);
    scheduleWriteBackDrain();
    return;
  }
  await putEntry(key, bytes);
}

// Best-effort write-back of a fresh tessellation; `index` supplies the header
// fields (partColor, edge classes) a later hit needs to skip the surf.
export async function writeBackComponentEntry(cid, options, component, index) {
  const provider = cacheProvider;
  if (!provider || typeof provider.put !== "function" || !cid) return;
  if (!tessellationOptionsCacheable(options)) return;
  try {
    await provider.put(
      tessellationCacheKey(cid, options),
      encodeComponentTessellation(component, {
        partColor: Array.isArray(index?.partColor) ? index.partColor : null,
        edgeClasses: edgeClassesFromSurfIndex(index),
      }),
    );
  } catch {
    // best-effort write-back
  }
}

export async function tessellateComponentCached(index, floats, { cid = "", options = {} } = {}) {
  const cached = await getCachedComponentEntry(cid, options);
  if (cached) return cached.component;
  const component = tessellateComponent(index, floats, options);
  if (cacheProvider && cid && tessellationOptionsCacheable(options)) {
    await writeBackComponentEntry(cid, options, component, index);
  }
  return component;
}

// "" (same origin) or an absolute origin with no trailing slash.
export function originPrefix(origin) {
  return String(origin ?? "").trim().replace(/\/+$/u, "");
}

// The fetch-backed provider both browser hosts use. `entryUrl(key)` resolves a
// single entry, `batchUrl` the POST endpoint speaking the batch container
// above; `headers` ride every request (the viewer adds its cross-site POST
// guard header). A host without the batch route (404/405) demotes getMany to
// per-key gets permanently for this provider instance.
//
// `origin` is the backend these routes live on, with "" (the default) meaning
// same origin — the only case a page served BY that backend ever needs. A page
// served from somewhere else (an embedded viewer surface) passes the absolute
// origin instead; this package stays React-free and framework-free, so the
// origin arrives as a plain argument and is never looked up.
export function createHttpTessellationCacheProvider({
  origin = "",
  entryUrl = (key) => `${originPrefix(origin)}/__tess_cache/${encodeURIComponent(key)}.tess`,
  batchUrl = `${originPrefix(origin)}/__tess_cache/batch`,
  headers = {},
} = {}) {
  let batchSupported = Boolean(batchUrl);
  return {
    async get(key) {
      try {
        const response = await fetch(entryUrl(key), { cache: "no-store", headers });
        if (!response.ok) return null;
        return new Uint8Array(await response.arrayBuffer());
      } catch {
        return null;
      }
    },
    async put(key, bytes) {
      try {
        await fetch(entryUrl(key), { method: "POST", body: bytes, headers });
      } catch {
        // best-effort write-back
      }
    },
    async getMany(keys) {
      if (!batchSupported) return null; // caller falls back to per-key gets
      try {
        const response = await fetch(batchUrl, {
          method: "POST",
          headers: { ...headers, "content-type": "application/json" },
          body: JSON.stringify({ names: keys.map((key) => `${key}.tess`) }),
        });
        if (!response.ok) {
          batchSupported = false;
          return null;
        }
        return decodeTessellationCacheBatch(new Uint8Array(await response.arrayBuffer()));
      } catch {
        return null;
      }
    },
  };
}

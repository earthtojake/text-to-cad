import { cadResourceCacheKey } from "../client/resources.js";
import { buildGlbDocumentFromBuffer, buildMeshDataFromGlbBuffer } from "./render/glbMeshData.js";
import { buildMeshDataFromStlBuffer } from "./render/stlMeshData.js";
import { buildMeshDataFrom3MfBuffer } from "./render/threeMfMeshData.js";
import { loadGlbMeshDataInWorker } from "./render/glbMeshWorkerClient.js";
import { loadStlMeshDataInWorker } from "./render/stlMeshWorkerClient.js";
import {
  prewarmPartWorkerPool,
  reclaimIdlePartWorkers as reclaimIdlePartWorkerPool,
  releasePartWorkerPoolWhenIdle,
  partWorkerMemoryStats as partWorkerMemoryStatsFromPool,
} from "./parts/partWorkerClient.js";
import { TessellationCacheProbeMissError } from "./parts/tessellationCache.js";
import {
  assertAssetSourceScope,
  assetSourceScopeMatches,
  releaseAssetSourceScope
} from "./renderAssetSourceScope.js";

function fetchError(url, response) {
  return new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
}

const jsonCache = new Map();
const arrayBufferCache = new Map();
const arrayBufferPendingCache = new Map();
const glbCache = new Map();
const stlCache = new Map();
const threeMfCache = new Map();
const selectorCache = new Map();
const robotCache = new Map();
const GIT_LFS_POINTER_PREFIX = "version https://git-lfs.github.com/spec/v1";
const GIT_LFS_POINTER_SCAN_BYTES = 512;

async function fetchJson(url, { signal, resources } = {}) {
  if (resources) return resources.readJson(url, { signal });
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw fetchError(url, response);
  }
  return response.json();
}

async function fetchArrayBuffer(url, { signal, resources } = {}) {
  if (resources) return resources.readBytes(url, { signal });
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw fetchError(url, response);
  }
  return response.arrayBuffer();
}

async function loadCached(cache, key, loader, { cachePending = true } = {}) {
  if (!key) {
    throw new Error("Missing asset cache key");
  }
  assertAssetSourceScope(cache, key);
  if (cache.has(key)) {
    const cached = cache.get(key);
    if (cachePending || typeof cached?.then !== "function") {
      return cached;
    }
  }
  if (!cachePending) {
    const payload = await loader();
    cache.set(key, payload);
    return payload;
  }
  let pending;
  pending = loader().catch((error) => {
    if (cache.get(key) === pending) {
      cache.delete(key);
      releaseAssetSourceScope(cache, key);
    }
    throw error;
  });
  cache.set(key, pending);
  return pending;
}

function peekCached(cache, key) {
  if (!assetSourceScopeMatches(cache, key)) {
    return null;
  }
  const value = cache.get(key);
  return value && typeof value.then !== "function" ? value : null;
}

function finalizeCached(cache, key, value) {
  cache.set(key, value);
  return value;
}

export function isAbortError(error) {
  return error instanceof DOMException && error.name === "AbortError";
}

export function gitLfsPointerDetailsFromBuffer(buffer) {
  const byteLength = Number(buffer?.byteLength || 0);
  if (!Number.isFinite(byteLength) || byteLength <= 0) {
    return null;
  }
  const preview = new TextDecoder("utf-8").decode(
    new Uint8Array(buffer, 0, Math.min(byteLength, GIT_LFS_POINTER_SCAN_BYTES))
  );
  if (!preview.startsWith(GIT_LFS_POINTER_PREFIX)) {
    return null;
  }
  const oid = preview.match(/^oid sha256:([0-9a-f]{64})\r?$/m)?.[1] || "";
  const sizeText = preview.match(/^size ([0-9]+)\r?$/m)?.[1] || "";
  const size = sizeText ? Number(sizeText) : null;
  return {
    oid,
    size: Number.isSafeInteger(size) ? size : null,
  };
}

function displayPathFromUrl(url) {
  const rawUrl = String(url || "").trim();
  if (!rawUrl) {
    return "(unknown)";
  }
  try {
    const baseUrl = typeof window !== "undefined" && window.location?.href
      ? window.location.href
      : "http://localhost/";
    const parsed = new URL(rawUrl, baseUrl);
    return decodeURIComponent(parsed.pathname || rawUrl);
  } catch {
    return rawUrl.split(/[?#]/)[0] || rawUrl;
  }
}

export function assertNotGitLfsPointer(buffer, url, assetLabel = "Render asset") {
  const pointer = gitLfsPointerDetailsFromBuffer(buffer);
  if (!pointer) {
    return;
  }
  const sizeText = pointer.size !== null ? ` Expected LFS object size: ${pointer.size} bytes.` : "";
  const oidText = pointer.oid ? ` sha256:${pointer.oid}.` : "";
  throw new Error(
    `${assetLabel} is a Git LFS pointer, not downloaded mesh data: ${displayPathFromUrl(url)}.${oidText}${sizeText} Fetch the LFS object for this file and reload the viewer.`
  );
}

function makeAbortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The operation was aborted.", "AbortError");
  }
  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

function withConsumerAbort(promise, signal) {
  if (!signal) {
    return promise;
  }
  if (signal.aborted) {
    return Promise.reject(makeAbortError());
  }
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      signal.removeEventListener?.("abort", abort);
    };
    const abort = () => {
      cleanup();
      reject(makeAbortError());
    };
    signal.addEventListener?.("abort", abort, { once: true });
    promise.then(
      (value) => {
        cleanup();
        resolve(value);
      },
      (error) => {
        cleanup();
        reject(error);
      }
    );
  });
}

export async function loadRenderJson(url, { signal, resources } = {}) {
  const cacheKey = cadResourceCacheKey(resources, url);
  const payload = await loadCached(jsonCache, cacheKey, () => fetchJson(url, { signal, resources }), { cachePending: !signal });
  return finalizeCached(jsonCache, cacheKey, payload);
}

export function peekRenderJson(url, { resources } = {}) {
  return peekCached(jsonCache, cadResourceCacheKey(resources, url));
}

export async function loadRenderArrayBuffer(url, { signal, resources } = {}) {
  const cacheKey = cadResourceCacheKey(resources, url);
  if (!url) {
    throw new Error("Missing asset cache key");
  }
  if (signal?.aborted) {
    throw makeAbortError();
  }
  // After the abort check: a consumer that fetches nothing must not claim the URL for its source.
  assertAssetSourceScope(arrayBufferCache, cacheKey, {
    occupied: arrayBufferCache.has(cacheKey) || arrayBufferPendingCache.has(cacheKey)
  });
  const cached = peekCached(arrayBufferCache, cacheKey);
  if (cached) {
    return cached;
  }
  let pending = arrayBufferPendingCache.get(cacheKey);
  if (!pending) {
    pending = fetchArrayBuffer(url, { resources })
      .then((payload) => finalizeCached(arrayBufferCache, cacheKey, payload))
      .catch((error) => {
        releaseAssetSourceScope(arrayBufferCache, cacheKey);
        throw error;
      })
      .finally(() => {
        if (arrayBufferPendingCache.get(cacheKey) === pending) {
          arrayBufferPendingCache.delete(cacheKey);
        }
      });
    arrayBufferPendingCache.set(cacheKey, pending);
  }
  return withConsumerAbort(pending, signal);
}

export async function loadRenderGlb(url, { signal, resources, preferWorker = false } = {}) {
  const cacheKey = cadResourceCacheKey(resources, url);
  const meshData = await loadCached(glbCache, cacheKey, async () => {
    if (preferWorker) {
      const workerMeshData = loadGlbMeshDataInWorker(url, { signal, resources });
      if (workerMeshData) {
        try {
          return await workerMeshData;
        } catch (error) {
          if (signal?.aborted || isAbortError(error)) {
            throw error;
          }
        }
      }
    }
    const buffer = await loadRenderArrayBuffer(url, { signal, resources });
    assertNotGitLfsPointer(buffer, url, "GLB render asset");
    return buildMeshDataFromGlbBuffer(buffer, { resources, sourceUrl: url, signal });
  }, { cachePending: !signal });
  return finalizeCached(glbCache, cacheKey, meshData);
}

export function peekRenderGlb(url, { resources } = {}) {
  return peekCached(glbCache, cadResourceCacheKey(resources, url));
}

// Interactive GLB documents are intentionally uncached: their scene graph is
// mutable animation state and has one viewer owner with an explicit lifetime.
export async function loadRenderGlbDocument(url, { signal, resources } = {}) {
  const buffer = await loadRenderArrayBuffer(url, { signal, resources });
  assertNotGitLfsPointer(buffer, url, "GLB render asset");
  return buildGlbDocumentFromBuffer(buffer, { resources, sourceUrl: url, signal });
}

/**
 * One part's display payload, from its stored mesh. `identity` is `{ part, tessellationProbe }`:
 * the part's key and its row (`partRow`), and `tessellationEntry` when a batched read already
 * holds the mesh's verified bytes.
 */
export async function loadRenderPart({
  signal,
  resources,
  identity,
  memoryEstimateBytes,
  tessellationCache,
} = {}) {
  // The worker builds only the display payload. A stored mesh carries
  // geometry, display edges and bounds, so this path skips both
  // the selector join and the selector table request.
  const cacheKey = identityCacheKey(identity);
  const meshData = await loadCached(glbCache, cacheKey, async () => {
    return (await loadPartPayload("", {
      signal,
      resources,
      identity,
      memoryEstimateBytes,
      tessellationCache,
      capabilities: { render: true, selectors: false },
    })).meshData;
  }, { cachePending: !signal });
  finalizeCached(glbCache, cacheKey, meshData);
  // On the part leash too: the package's componentMeshDataByCid owns the
  // displayed arrays, and a pinned entry here kept a previous model's
  // geometry alive across a file switch.
  retainPartEntry(glbCache, cacheKey);
  return meshData;
}

// Hand the part worker pool's isolates back once nothing is loading. The
// generation-scoped wait prevents an overlapping package/topology request from
// leaving its conservative retained-memory estimate charged after it drains.
export async function releasePartWorkers() {
  return releasePartWorkerPoolWhenIdle();
}

/** Start the isolates a package load will decode on (`prewarmPartWorkerPool`). */
export function prewarmPartWorkers(count) {
  return prewarmPartWorkerPool(count);
}

export function reclaimIdlePartWorkers() {
  return reclaimIdlePartWorkerPool();
}

export function partWorkerMemoryStats() {
  return partWorkerMemoryStatsFromPool();
}

export async function loadRenderStl(url, { signal, resources } = {}) {
  const cacheKey = cadResourceCacheKey(resources, url);
  const meshData = await loadCached(stlCache, cacheKey, async () => {
    const workerMeshData = loadStlMeshDataInWorker(url, { signal, resources });
    if (workerMeshData) {
      try {
        return await workerMeshData;
      } catch (error) {
        if (signal?.aborted || isAbortError(error)) {
          throw error;
        }
      }
    }
    const buffer = await loadRenderArrayBuffer(url, { signal, resources });
    assertNotGitLfsPointer(buffer, url, "STL render asset");
    return buildMeshDataFromStlBuffer(buffer);
  }, { cachePending: !signal });
  return finalizeCached(stlCache, cacheKey, meshData);
}

export function peekRenderStl(url, { resources } = {}) {
  return peekCached(stlCache, cadResourceCacheKey(resources, url));
}

export async function loadRender3Mf(url, { signal, resources } = {}) {
  const cacheKey = cadResourceCacheKey(resources, url);
  const meshData = await loadCached(threeMfCache, cacheKey, async () => {
    const buffer = await loadRenderArrayBuffer(url, { signal, resources });
    assertNotGitLfsPointer(buffer, url, "3MF render asset");
    return buildMeshDataFrom3MfBuffer(buffer);
  }, { cachePending: !signal });
  return finalizeCached(threeMfCache, cacheKey, meshData);
}

export function peekRender3Mf(url, { resources } = {}) {
  return peekCached(threeMfCache, cadResourceCacheKey(resources, url));
}

// --- Exact topology ----------------------------------------------------------
//
// cadgen's selector table carries a part's topology, and the page joins it to
// the stored mesh (parts/selectorTable.js).
// Worker requests declare whether they need render data, selectors, or both.
// Display uses render only; selection and measurement join the table on
// demand, to the same mesh.

const partPayloadCache = new Map();

// Every part entry — a component's payload, its mesh data, its selector
// bundle — lives on ONE bounded LRU leash. The consumers own
// what they keep: the package's componentMeshDataByCid holds every displayed
// meshData, the reference composition holds the bundles of the occurrences it
// composed. Retaining a second
// reference here for the load's lifetime pinned every component's decoded
// selector bundle (manifest rows + edge polylines) for the whole session; a
// miss re-decodes from the shared part store in a worker. Keys name the part
// and its display mesh's object (`partCacheKey`).
//
// The leash is bounded by COUNT and by BYTES. A count alone pinned whatever the
// entries weighed: the tendon hand's components decode to ~90 MB each, so 24
// of them held >2 GB of typed arrays here beside the copies the package
// already owns, and the tab died at load time. The byte
// ceiling evicts oldest-first until the decoded bytes fit; the count floor
// keeps a few entries whatever they weigh, so small models behave as before
// (their whole working set fits under the ceiling anyway).
const PART_CACHE_LIMIT = 24;
const PART_CACHE_MIN_ENTRIES = 4;
const PART_CACHE_MAX_BYTES = 256 * 1024 * 1024;
const partLeashConfig = { limit: PART_CACHE_LIMIT, minEntries: PART_CACHE_MIN_ENTRIES, maxBytes: PART_CACHE_MAX_BYTES };
const partEntries = [];

// Test seam: lower the ceilings to exercise eviction with small fixtures.
// Returns the previous configuration so a test can restore it.
export function configurePartLeash(next = {}) {
  const previous = { ...partLeashConfig };
  for (const key of ["limit", "minEntries", "maxBytes"]) {
    if (Number.isFinite(Number(next[key]))) {
      partLeashConfig[key] = Number(next[key]);
    }
  }
  return previous;
}

// Decoded typed-array bytes the leash retains, each buffer counted once (a
// part payload and its meshData entry share arrays). Pending entries weigh zero.
function partLeashBytes() {
  const seen = new Set();
  let total = 0;
  for (const entry of partEntries) {
    const value = entry.cache.get(entry.key);
    if (value && typeof value.then !== "function") {
      total += typedArrayBytesOf(value, seen);
    }
  }
  return total;
}

function evictOldestPartEntry() {
  const evicted = partEntries.shift();
  if (evicted.cache.get(evicted.key)?.then === undefined) {
    evicted.cache.delete(evicted.key);
    releaseAssetSourceScope(evicted.cache, evicted.key);
  }
}

function retainPartEntry(cache, key) {
  const existing = partEntries.findIndex((entry) => entry.cache === cache && entry.key === key);
  if (existing !== -1) {
    partEntries.splice(existing, 1);
  }
  partEntries.push({ cache, key });
  while (partEntries.length > partLeashConfig.limit) {
    evictOldestPartEntry();
  }
  while (partEntries.length > partLeashConfig.minEntries && partLeashBytes() > partLeashConfig.maxBytes) {
    evictOldestPartEntry();
  }
}

function typedArrayBytesOf(value, seen, visited = new Set()) {
  if (!value || typeof value !== "object") {
    return 0;
  }
  if (ArrayBuffer.isView(value)) {
    if (seen.has(value.buffer)) {
      return 0;
    }
    seen.add(value.buffer);
    // A short view retains its whole backing allocation. Stored mesh bodies
    // deliberately decode as disjoint zero-copy views over one packed buffer;
    // charging the first view's length and suppressing the rest understated
    // those entries by most of their actual retained bytes.
    return value.buffer.byteLength;
  }
  if (value instanceof ArrayBuffer) {
    if (seen.has(value)) {
      return 0;
    }
    seen.add(value);
    return value.byteLength;
  }
  if (visited.has(value)) {
    return 0;
  }
  visited.add(value);
  let total = 0;
  for (const child of Object.values(value)) {
    if (child && typeof child === "object") {
      total += typedArrayBytesOf(child, seen, visited);
    }
  }
  return total;
}

// Byte attribution of what these caches retain, for the memory harness:
// typed-array bytes (each buffer counted once) and manifest row counts per
// cache. Pending entries count as zero.
export function renderAssetCacheStats({ excludeBuffers = [] } = {}) {
  const seen = new Set(excludeBuffers);
  const stats = {};
  for (const [name, cache] of [
    ["partPayload", partPayloadCache],
    ["selector", selectorCache],
    ["glb", glbCache],
  ]) {
    let typedBytes = 0;
    let manifestRows = 0;
    let entries = 0;
    for (const value of cache.values()) {
      if (!value || typeof value.then === "function") {
        continue;
      }
      entries += 1;
      typedBytes += typedArrayBytesOf(value, seen);
      const manifest = value.manifest || value.bundle?.manifest;
      for (const rows of [manifest?.faces, manifest?.edges, manifest?.shapes, manifest?.occurrences]) {
        manifestRows += Array.isArray(rows) ? rows.length : 0;
      }
    }
    stats[name] = { entries, typedBytes, manifestRows };
  }
  stats.partLeash = {
    entries: partEntries.length,
    limit: partLeashConfig.limit,
    bytes: partLeashBytes(),
    maxBytes: partLeashConfig.maxBytes,
    minEntries: partLeashConfig.minEntries
  };
  return stats;
}

/** The display payload `loadRenderPart` already holds for the part `row` names, or null. */
export function peekRenderPart(row) {
  return peekCached(glbCache, partCacheKey(row));
}

/** What a part's decoded payloads are cached under: its key and its display mesh's object. */
export function partCacheKey(row) {
  const part = String(row?.part || "");
  const object = String(row?.glb?.object || "");
  return part && object ? `${part}@${object}` : "";
}

// A load reads `identity.part` and is cached under its row's key, so a row naming a part must name
// that one: another part's would cache this part's mesh as that one's. A row naming none has no key.
function identityCacheKey(identity) {
  const row = identity?.tessellationProbe;
  if (row?.part && row.part !== identity.part) throw new TypeError("A part's load names another part's row");
  return partCacheKey(row);
}

function capabilityCacheKey(capabilities) {
  return `${capabilities.render ? "r" : ""}${capabilities.selectors ? "s" : ""}`;
}

async function loadPartPayloadInline(url, { signal, resources, identity, capabilities, tessellationCache } = {}) {
  const [
    { decodeComponentTessellation },
    { buildComponentMeshData },
    { joinSelectorTable, parseSelectorTable },
  ] = await Promise.all([
    import("./parts/tessellationCache.js"),
    import("./parts/partMeshData.js"),
    import("./parts/selectorTable.js"),
  ]);
  const part = String(identity?.part || "");
  const probe = identity?.tessellationProbe || null;
  // As the worker path takes them (`loadPartInWorker`): bytes a batched read already
  // verified for this probe, else the part's mesh read here. cadgen produces every mesh; one
  // the store does not hold is a probe miss, which the caller answers by asking for it.
  const readEntry = identity?.tessellationEntry instanceof Uint8Array ? identity.tessellationEntry : null;
  const cached = readEntry
    ? decodeComponentTessellation(readEntry, { part })
    : await tessellationCache?.getCachedComponentEntry(part, { signal, probe, strictProbe: true });
  if (!cached) throw new TessellationCacheProbeMissError(probe);
  const meshData = capabilities.render ? buildComponentMeshData(cached.component) : null;
  // Drawing needs only the mesh; selectors also need the part's selector table (`url`, its
  // record's other object), joined to this mesh.
  if (!capabilities.selectors) {
    return { meshData };
  }
  if (!url) throw new Error("The selector table is not ready for this component");
  const buffer = await loadRenderArrayBuffer(url, { signal, resources });
  assertNotGitLfsPointer(buffer, url, "selector table asset");
  return {
    ...(meshData ? { meshData } : {}),
    bundle: joinSelectorTable(parseSelectorTable(buffer), cached.component),
  };
}

async function loadPartPayload(url, {
  signal,
  resources,
  identity,
  memoryEstimateBytes,
  tessellationCache,
  capabilities = { render: true, selectors: true },
} = {}) {
  const cacheKey = `${identityCacheKey(identity)}#cap=${capabilityCacheKey(capabilities)}`;
  const payload = await loadCached(partPayloadCache, cacheKey, async () => {
    const { loadPartInWorker } = await import("./parts/partWorkerClient.js");
    const workerPayload = loadPartInWorker(url, {
      signal,
      resources,
      identity,
      capabilities,
      memoryEstimateBytes,
      tessellationCache,
    });
    if (workerPayload) {
      // Once a worker accepts the job, keep decoding and selector building off
      // the UI thread even when that job fails. Propagate the failure; inline
      // is only the path for environments where Workers never started.
      return workerPayload;
    }
    return loadPartPayloadInline(url, { signal, resources, identity, capabilities, tessellationCache });
  }, { cachePending: !signal });
  finalizeCached(partPayloadCache, cacheKey, payload);
  retainPartEntry(partPayloadCache, cacheKey);
  return payload;
}

/** The selector bundle of one part: cadgen's selector table (`selectorsUrl`, read for the row in
 * `identity`) joined to its display mesh. */
export async function loadRenderPartSelectorBundle(selectorsUrl, {
  signal,
  resources,
  identity,
  memoryEstimateBytes,
  tessellationCache,
} = {}) {
  const cacheKey = identityCacheKey(identity);
  const bundle = await loadCached(selectorCache, cacheKey, async () => {
    return (await loadPartPayload(selectorsUrl, {
      signal,
      resources,
      identity,
      memoryEstimateBytes,
      tessellationCache,
      capabilities: { render: false, selectors: true },
    })).bundle;
  }, { cachePending: !signal });
  finalizeCached(selectorCache, cacheKey, bundle);
  retainPartEntry(selectorCache, cacheKey);
  return bundle;
}

/**
 * A robot as cadgen resolved it (`cadgen.robot_payload`, `GET /__cad/robot`): the articulation
 * to play and the visuals to draw. Cached for the page by file and revision, as a description
 * once was, so a warm reopen is whole on the first render; the page validates nothing of it but
 * the schema it reads.
 *
 * @param {string} file  The description's absolute path, as the catalog names it.
 * @param {{ client: { robot: Function }, revision?: string, signal?: AbortSignal }} options
 */
export async function loadRenderRobot(file, { client, revision = "", signal } = {}) {
  const cacheKey = robotCacheKey(file, revision);
  const payload = await loadCached(robotCache, cacheKey, async () => {
    const robot = await client.robot(file, { signal });
    if (robot?.schemaVersion !== ROBOT_PAYLOAD_SCHEMA_VERSION) {
      throw new RobotSchemaError(robot?.schemaVersion);
    }
    return robot;
  }, { cachePending: !signal });
  return finalizeCached(robotCache, cacheKey, payload);
}

export function peekRenderRobot(file, { revision = "" } = {}) {
  return peekCached(robotCache, robotCacheKey(file, revision));
}

function robotCacheKey(file, revision) {
  return `${String(file || "")}::${String(revision || "")}`;
}

/** The payload shape this build reads (`cadgen.robot_payload.ROBOT_PAYLOAD_SCHEMA_VERSION`). */
export const ROBOT_PAYLOAD_SCHEMA_VERSION = 2;

/** A payload from a cadgen that does not agree with this build about the shape. */
export class RobotSchemaError extends Error {
  constructor(received) {
    super(`The viewer received a robot payload at schemaVersion ${JSON.stringify(received)}, but this `
      + `build of the app reads version ${ROBOT_PAYLOAD_SCHEMA_VERSION}.`);
    this.name = "RobotSchemaError";
    this.received = received;
  }
}

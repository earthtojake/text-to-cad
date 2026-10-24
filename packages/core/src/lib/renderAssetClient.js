import { cadResourceCacheKey } from "../client/resources.js";
import { buildGlbDocumentFromBuffer, buildMeshDataFromGlbBuffer } from "./render/glbMeshData.js";
import { buildMeshDataFromStlBuffer } from "./render/stlMeshData.js";
import { buildMeshDataFrom3MfBuffer } from "./render/threeMfMeshData.js";
import { loadGlbMeshDataInWorker } from "./render/glbMeshWorkerClient.js";
import { loadStlMeshDataInWorker } from "./render/stlMeshWorkerClient.js";
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

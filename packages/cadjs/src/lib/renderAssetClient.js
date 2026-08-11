import { parseDxf } from "./dxf/parseDxf.js";
import {
  STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
  STEP_EDGE_CLASS_ATTRIBUTE,
  STEP_TOPOLOGY_EXTENSION,
  STEP_TOPOLOGY_SCHEMA_VERSION,
  isCurrentStepTopologySchemaVersion
} from "../common/stepTopology.mjs";
import { buildMeshDataFromGlbBuffer } from "./render/glbMeshData.js";
import { buildMeshDataFromStlBuffer } from "./render/stlMeshData.js";
import { buildMeshDataFrom3MfBuffer } from "./render/threeMfMeshData.js";
import { loadGlbMeshDataInWorker } from "./render/glbMeshWorkerClient.js";
import { loadStlMeshDataInWorker } from "./render/stlMeshWorkerClient.js";
import {
  assertAssetSourceScope,
  assetSourceScopeMatches,
  releaseAssetSourceScope
} from "./renderAssetSourceScope.js";

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function fetchError(url, response) {
  return new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
}

const jsonCache = new Map();
const textCache = new Map();
const arrayBufferCache = new Map();
const arrayBufferPendingCache = new Map();
const glbCache = new Map();
const stlCache = new Map();
const threeMfCache = new Map();
const selectorCache = new Map();
const displayEdgeCache = new Map();
const topologyIndexCache = new Map();
const dxfCache = new Map();
const urdfCache = new Map();
const srdfCache = new Map();
const sdfCache = new Map();
const GIT_LFS_POINTER_PREFIX = "version https://git-lfs.github.com/spec/v1";
const GIT_LFS_POINTER_SCAN_BYTES = 512;

async function fetchJson(url, { signal } = {}) {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw fetchError(url, response);
  }
  return response.json();
}

async function fetchText(url, { signal } = {}) {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw fetchError(url, response);
  }
  return response.text();
}

async function fetchArrayBuffer(url, { signal } = {}) {
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

export async function loadRenderJson(url, { signal } = {}) {
  const payload = await loadCached(jsonCache, url, () => fetchJson(url, { signal }), { cachePending: !signal });
  return finalizeCached(jsonCache, url, payload);
}

export function peekRenderJson(url) {
  return peekCached(jsonCache, url);
}

export async function loadRenderText(url, { signal } = {}) {
  const payload = await loadCached(textCache, url, () => fetchText(url, { signal }), { cachePending: !signal });
  return finalizeCached(textCache, url, payload);
}

export function peekRenderText(url) {
  return peekCached(textCache, url);
}

export async function loadRenderArrayBuffer(url, { signal } = {}) {
  if (!url) {
    throw new Error("Missing asset cache key");
  }
  if (signal?.aborted) {
    throw makeAbortError();
  }
  // After the abort check: a consumer that fetches nothing must not claim the URL for its source.
  assertAssetSourceScope(arrayBufferCache, url, {
    occupied: arrayBufferCache.has(url) || arrayBufferPendingCache.has(url)
  });
  const cached = peekCached(arrayBufferCache, url);
  if (cached) {
    return cached;
  }
  let pending = arrayBufferPendingCache.get(url);
  if (!pending) {
    pending = fetchArrayBuffer(url)
      .then((payload) => finalizeCached(arrayBufferCache, url, payload))
      .catch((error) => {
        releaseAssetSourceScope(arrayBufferCache, url);
        throw error;
      })
      .finally(() => {
        if (arrayBufferPendingCache.get(url) === pending) {
          arrayBufferPendingCache.delete(url);
        }
      });
    arrayBufferPendingCache.set(url, pending);
  }
  return withConsumerAbort(pending, signal);
}

export function peekRenderArrayBuffer(url) {
  return peekCached(arrayBufferCache, url);
}

export async function loadRenderGlb(url, { signal, preferWorker = false } = {}) {
  const meshData = await loadCached(glbCache, url, async () => {
    if (preferWorker) {
      const workerMeshData = loadGlbMeshDataInWorker(url, { signal });
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
    const buffer = await loadRenderArrayBuffer(url, { signal });
    assertNotGitLfsPointer(buffer, url, "GLB render asset");
    return buildMeshDataFromGlbBuffer(buffer);
  }, { cachePending: !signal });
  return finalizeCached(glbCache, url, meshData);
}

export function peekRenderGlb(url) {
  return peekCached(glbCache, url);
}

export async function loadRenderStl(url, { signal } = {}) {
  const meshData = await loadCached(stlCache, url, async () => {
    const workerMeshData = loadStlMeshDataInWorker(url, { signal });
    if (workerMeshData) {
      try {
        return await workerMeshData;
      } catch (error) {
        if (signal?.aborted || isAbortError(error)) {
          throw error;
        }
      }
    }
    const buffer = await loadRenderArrayBuffer(url, { signal });
    assertNotGitLfsPointer(buffer, url, "STL render asset");
    return buildMeshDataFromStlBuffer(buffer);
  }, { cachePending: !signal });
  return finalizeCached(stlCache, url, meshData);
}

export function peekRenderStl(url) {
  return peekCached(stlCache, url);
}

export async function loadRender3Mf(url, { signal } = {}) {
  const meshData = await loadCached(threeMfCache, url, async () => {
    const buffer = await loadRenderArrayBuffer(url, { signal });
    assertNotGitLfsPointer(buffer, url, "3MF render asset");
    return buildMeshDataFrom3MfBuffer(buffer);
  }, { cachePending: !signal });
  return finalizeCached(threeMfCache, url, meshData);
}

export function peekRender3Mf(url) {
  return peekCached(threeMfCache, url);
}

function parseGlbContainer(arrayBuffer) {
  const data = new DataView(arrayBuffer);
  if (data.byteLength < 20 || data.getUint32(0, true) !== 0x46546c67 || data.getUint32(4, true) !== 2) {
    throw new Error("Invalid GLB topology container");
  }
  const totalLength = Math.min(data.getUint32(8, true), data.byteLength);
  let offset = 12;
  let json = null;
  let bin = null;
  while (offset + 8 <= totalLength) {
    const chunkLength = data.getUint32(offset, true);
    const chunkType = data.getUint32(offset + 4, true);
    offset += 8;
    if (offset + chunkLength > totalLength) {
      throw new Error("Invalid GLB chunk length");
    }
    if (chunkType === 0x4e4f534a) {
      json = JSON.parse(new TextDecoder("utf-8").decode(arrayBuffer.slice(offset, offset + chunkLength)).trim());
    } else if (chunkType === 0x004e4942) {
      bin = {
        buffer: arrayBuffer,
        byteOffset: offset,
        byteLength: chunkLength,
      };
    }
    offset += chunkLength;
  }
  if (!json || !bin) {
    throw new Error("GLB topology requires JSON and BIN chunks");
  }
  return { json, bin };
}

function glbBufferViewRange(gltf, bin, viewIndex) {
  const index = Number(viewIndex);
  const view = Array.isArray(gltf?.bufferViews) ? gltf.bufferViews[index] : null;
  if (!Number.isInteger(index) || !view || Number(view.buffer || 0) !== 0) {
    return null;
  }
  const byteOffset = bin.byteOffset + Number(view.byteOffset || 0);
  const byteLength = Number(view.byteLength || 0);
  if (!Number.isFinite(byteOffset) || !Number.isFinite(byteLength) || byteLength < 0) {
    return null;
  }
  if (byteOffset < bin.byteOffset || byteOffset + byteLength > bin.byteOffset + bin.byteLength) {
    return null;
  }
  return { byteOffset, byteLength };
}

function buildTypedView(glb, view) {
  if (!isObject(view)) {
    return null;
  }
  const range = glbBufferViewRange(glb.json, glb.bin, view.bufferView);
  if (!range) {
    return null;
  }
  const count = Number(view.count || 0);
  const relativeOffset = Number(view.byteOffset || 0);
  if (!Number.isFinite(count) || count < 0 || !Number.isFinite(relativeOffset) || relativeOffset < 0) {
    return null;
  }
  const byteOffset = range.byteOffset + relativeOffset;
  if (view.dtype === "float32") {
    return new Float32Array(glb.bin.buffer, byteOffset, count);
  }
  if (view.dtype === "uint32") {
    return new Uint32Array(glb.bin.buffer, byteOffset, count);
  }
  return null;
}

function buildSelectorBuffers(manifest, glb) {
  const views = manifest?.buffers?.views;
  if (!isObject(views)) {
    return {};
  }
  const output = {};
  for (const [name, view] of Object.entries(views)) {
    const typed = buildTypedView(glb, view);
    if (typed) {
      output[name] = typed;
    }
  }
  return output;
}

function glbPrimitivesHaveSurfaceEdgeAttributes(glb) {
  const meshes = Array.isArray(glb?.json?.meshes) ? glb.json.meshes : [];
  let primitiveCount = 0;
  for (const mesh of meshes) {
    for (const primitive of Array.isArray(mesh?.primitives) ? mesh.primitives : []) {
      primitiveCount += 1;
      const attributes = primitive?.attributes || {};
      if (
        attributes[STEP_EDGE_BARYCENTRIC_ATTRIBUTE] === undefined ||
        attributes[STEP_EDGE_CLASS_ATTRIBUTE] === undefined
      ) {
        return false;
      }
    }
  }
  return primitiveCount > 0;
}

function stepTopologyExtension(glb) {
  const extension = glb.json?.extensions?.[STEP_TOPOLOGY_EXTENSION];
  if (!isObject(extension)) {
    throw new Error(`GLB is missing ${STEP_TOPOLOGY_EXTENSION}`);
  }
  if (!isCurrentStepTopologySchemaVersion(extension.schemaVersion)) {
    throw new Error(`Unsupported ${STEP_TOPOLOGY_EXTENSION} schemaVersion ${extension.schemaVersion || "unknown"}; expected ${STEP_TOPOLOGY_SCHEMA_VERSION}`);
  }
  if (extension.edgeView === undefined || extension.edgeView === null) {
    throw new Error(`${STEP_TOPOLOGY_EXTENSION} edgeView is not available`);
  }
  if (!glbPrimitivesHaveSurfaceEdgeAttributes(glb)) {
    throw new Error(`${STEP_TOPOLOGY_EXTENSION} requires ${STEP_EDGE_BARYCENTRIC_ATTRIBUTE} and ${STEP_EDGE_CLASS_ATTRIBUTE} on every STEP mesh primitive`);
  }
  return extension;
}

function parseJsonBufferView(glb, viewIndex, encoding = "utf-8") {
  const range = glbBufferViewRange(glb.json, glb.bin, viewIndex);
  if (!range) {
    return null;
  }
  const bytes = new Uint8Array(glb.bin.buffer, range.byteOffset, range.byteLength);
  return JSON.parse(new TextDecoder(String(encoding || "utf-8")).decode(bytes));
}

function topologyIndexFromGlbBuffer(arrayBuffer) {
  const glb = parseGlbContainer(arrayBuffer);
  const extension = stepTopologyExtension(glb);
  const manifest = parseJsonBufferView(glb, extension.indexView, extension.encoding);
  if (!isObject(manifest)) {
    throw new Error(`${STEP_TOPOLOGY_EXTENSION} indexView is invalid`);
  }
  if (!isCurrentStepTopologySchemaVersion(manifest.schemaVersion)) {
    throw new Error(`Unsupported ${STEP_TOPOLOGY_EXTENSION} index schemaVersion ${manifest.schemaVersion || "unknown"}; expected ${STEP_TOPOLOGY_SCHEMA_VERSION}`);
  }
  return manifest;
}

function selectorBundleFromGlbBuffer(arrayBuffer) {
  const glb = parseGlbContainer(arrayBuffer);
  const extension = stepTopologyExtension(glb);
  const manifest = parseJsonBufferView(glb, extension.selectorView, extension.encoding);
  if (!isObject(manifest)) {
    throw new Error(`${STEP_TOPOLOGY_EXTENSION} selectorView is not available`);
  }
  if (!isCurrentStepTopologySchemaVersion(manifest.schemaVersion)) {
    throw new Error(`Unsupported ${STEP_TOPOLOGY_EXTENSION} selector schemaVersion ${manifest.schemaVersion || "unknown"}; expected ${STEP_TOPOLOGY_SCHEMA_VERSION}`);
  }
  if (manifest?.buffers?.littleEndian === false) {
    throw new Error("Big-endian selector buffers are not supported");
  }
  return {
    manifest,
    buffers: buildSelectorBuffers(manifest, glb),
  };
}

function displayEdgeBundleFromGlbBuffer(arrayBuffer) {
  const glb = parseGlbContainer(arrayBuffer);
  const extension = stepTopologyExtension(glb);
  const manifest = parseJsonBufferView(glb, extension.edgeView, extension.encoding);
  if (!isObject(manifest)) {
    throw new Error(`${STEP_TOPOLOGY_EXTENSION} edgeView is not available`);
  }
  if (!isCurrentStepTopologySchemaVersion(manifest.schemaVersion)) {
    throw new Error(`Unsupported ${STEP_TOPOLOGY_EXTENSION} edgeView schemaVersion ${manifest.schemaVersion || "unknown"}; expected ${STEP_TOPOLOGY_SCHEMA_VERSION}`);
  }
  if (String(manifest.profile || "") !== "surface-edges") {
    throw new Error(`${STEP_TOPOLOGY_EXTENSION} edgeView has unsupported profile ${manifest.profile || "unknown"}`);
  }
  if (manifest?.buffers?.littleEndian === false) {
    throw new Error("Big-endian edgeView buffers are not supported");
  }
  return {
    manifest,
    buffers: buildSelectorBuffers(manifest, glb),
  };
}

export async function loadRenderTopologyIndex(glbUrl, { signal } = {}) {
  const manifest = await loadCached(topologyIndexCache, glbUrl, async () => {
    const arrayBuffer = await loadRenderArrayBuffer(glbUrl, { signal });
    assertNotGitLfsPointer(arrayBuffer, glbUrl, "GLB topology asset");
    return topologyIndexFromGlbBuffer(arrayBuffer);
  }, { cachePending: !signal });
  return finalizeCached(topologyIndexCache, glbUrl, manifest);
}

export function peekRenderTopologyIndex(glbUrl) {
  return peekCached(topologyIndexCache, glbUrl);
}

export async function loadRenderSelectorBundle(glbUrl, { signal } = {}) {
  const cacheKey = glbUrl;
  const bundle = await loadCached(selectorCache, cacheKey, async () => {
    const arrayBuffer = await loadRenderArrayBuffer(glbUrl, { signal });
    assertNotGitLfsPointer(arrayBuffer, glbUrl, "GLB selector topology asset");
    return selectorBundleFromGlbBuffer(arrayBuffer);
  }, { cachePending: !signal });
  return finalizeCached(selectorCache, cacheKey, bundle);
}

export function peekRenderSelectorBundle(glbUrl) {
  return peekCached(selectorCache, glbUrl);
}

export async function loadRenderDisplayEdgeBundle(glbUrl, { signal } = {}) {
  const cacheKey = glbUrl;
  const bundle = await loadCached(displayEdgeCache, cacheKey, async () => {
    const arrayBuffer = await loadRenderArrayBuffer(glbUrl, { signal });
    assertNotGitLfsPointer(arrayBuffer, glbUrl, "GLB display edge topology asset");
    return displayEdgeBundleFromGlbBuffer(arrayBuffer);
  }, { cachePending: !signal });
  return finalizeCached(displayEdgeCache, cacheKey, bundle);
}

export function peekRenderDisplayEdgeBundle(glbUrl) {
  return peekCached(displayEdgeCache, glbUrl);
}

export async function loadRenderDxf(url, { signal } = {}) {
  const payload = await loadCached(dxfCache, url, async () => {
    const dxfText = await loadRenderText(url, { signal });
    return parseDxf(dxfText, { fileRef: "", sourceUrl: url });
  }, { cachePending: !signal });
  return finalizeCached(dxfCache, url, payload);
}

export function peekRenderDxf(url) {
  return peekCached(dxfCache, url);
}

function urdfCacheKey(url) {
  return String(url || "");
}

export async function loadRenderUrdf(url, { signal } = {}) {
  const cacheKey = urdfCacheKey(url);
  const payload = await loadCached(urdfCache, cacheKey, async () => {
    const [xmlText, { parseUrdf }] = await Promise.all([
      loadRenderText(url, { signal }),
      import("./urdf/parseUrdf.js"),
    ]);
    return parseUrdf(xmlText, { sourceUrl: url });
  }, { cachePending: !signal });
  return finalizeCached(urdfCache, cacheKey, payload);
}

export function peekRenderUrdf(url) {
  return peekCached(urdfCache, urdfCacheKey(url));
}

function srdfCacheKey(srdfUrl, urdfUrl = "") {
  return [srdfUrl, urdfUrl].filter(Boolean).join("::");
}

export async function loadRenderSrdf(srdfUrl, { signal, urdfUrl = "" } = {}) {
  const cacheKey = srdfCacheKey(srdfUrl, urdfUrl);
  const payload = await loadCached(srdfCache, cacheKey, async () => {
    const [srdfText, urdfData, { parseSrdf, motionFromSrdf }] = await Promise.all([
      loadRenderText(srdfUrl, { signal }),
      loadRenderUrdf(urdfUrl, { signal }),
      import("./urdf/parseSrdf.js"),
    ]);
    const srdfData = parseSrdf(srdfText, { sourceUrl: srdfUrl, urdfData });
    return {
      srdfData,
      urdfData: {
        ...urdfData,
        motion: motionFromSrdf(srdfData),
        srdf: srdfData
      }
    };
  }, { cachePending: !signal });
  return finalizeCached(srdfCache, cacheKey, payload);
}

export function peekRenderSrdf(srdfUrl, { urdfUrl = "" } = {}) {
  return peekCached(srdfCache, srdfCacheKey(srdfUrl, urdfUrl));
}

function sdfCacheKey(url) {
  return String(url || "");
}

export async function loadRenderSdf(url, { signal } = {}) {
  const cacheKey = sdfCacheKey(url);
  const payload = await loadCached(sdfCache, cacheKey, async () => {
    const [xmlText, { parseSdf }] = await Promise.all([
      loadRenderText(url, { signal }),
      import("./urdf/parseSdf.js"),
    ]);
    return parseSdf(xmlText, { sourceUrl: url });
  }, { cachePending: !signal });
  return finalizeCached(sdfCache, cacheKey, payload);
}

export function peekRenderSdf(url) {
  return peekCached(sdfCache, sdfCacheKey(url));
}

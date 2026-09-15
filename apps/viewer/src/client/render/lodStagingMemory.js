import { MESH_DATA_ARRAY_FIELDS } from "cadgen-js/lib/render/meshTransfer.js";

const owners = new Map();

export function lodPayloadMemory(payload) {
  const buffers = new Set(), arrays = new Set(), seen = new Set();
  const retain = value => {
    const buffer = ArrayBuffer.isView(value) ? value.buffer : value instanceof ArrayBuffer ? value : null;
    if (buffer) buffers.add(buffer);
  };
  const visitMesh = mesh => {
    if (!mesh || seen.has(mesh)) return;
    seen.add(mesh);
    for (const key of MESH_DATA_ARRAY_FIELDS) {
      const value = mesh[key]; retain(value);
      if (ArrayBuffer.isView(value)) arrays.add(value);
    }
    for (const part of mesh.parts || []) if (part.sourceMesh) visitMesh(part.sourceMesh);
  };
  visitMesh(payload?.meshData);
  const visitBundle = value => {
    if (!value || typeof value !== "object" || seen.has(value)) return;
    seen.add(value);
    if (ArrayBuffer.isView(value) || value instanceof ArrayBuffer) { retain(value); return; }
    for (const child of Object.values(value)) visitBundle(child);
  };
  visitBundle(payload?.bundle);
  return { buffers, cpuBytes: [...buffers].reduce((sum, buffer) => sum + buffer.byteLength, 0),
    gpuInputBytes: [...arrays].reduce((sum, array) => sum + array.byteLength, 0) };
}

// Only byte buffers are held here, and only while a scheduler lease owns them.
// The normal scene ledger takes over before these exclusions are removed.
export function setLodStaging(owner, entries) {
  const buffers = new Set();
  for (const entry of entries || []) for (const buffer of lodPayloadMemory(entry.payload).buffers) buffers.add(buffer);
  if (buffers.size) owners.set(owner, buffers); else owners.delete(owner);
}

export function lodStagingBuffers(excluded = []) {
  const buffers = new Set(excluded);
  for (const owned of owners.values()) for (const buffer of owned) buffers.add(buffer);
  return buffers;
}

export function lodStagingSnapshot() {
  const buffers = lodStagingBuffers();
  return { owners: owners.size, buffers: buffers.size, bytes: [...buffers].reduce((sum, buffer) => sum + buffer.byteLength, 0) };
}

const selectorCacheCharges = new WeakMap();

// Cache refreshes must not erase the renderer's separately measured picking
// arrays. A full scene measurement supplies derivedBytes; cache-only updates
// replace just the cache portion of that same ledger category.
export function syncSelectorCacheAccounting(policy, cacheBytes, derivedBytes = null) {
  const current = policy.snapshot().retainedByCategory.selectors || 0;
  const derived = derivedBytes === null ? Math.max(0, current - (selectorCacheCharges.get(policy) || 0)) : derivedBytes;
  const selectorCacheCharge = Math.max(0, Number(cacheBytes) || 0);
  selectorCacheCharges.set(policy, selectorCacheCharge);
  policy.setRetained("selectors", derived + selectorCacheCharge);
}

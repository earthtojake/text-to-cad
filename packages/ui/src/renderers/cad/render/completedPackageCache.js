import { buildComposedPackageMeshData } from "@hardcore/core/lib/assembly/meshData.js";
import { entryAssetUrl, entryMeshAssetSignature } from "@hardcore/core/lib/entryAssets.js";
import { entrySourceFormat } from "@hardcore/core/lib/fileFormats.js";
import { renderCapabilities } from "@hardcore/core/lib/renderCapabilities.js";
import { renderAssetCacheStats, surfTessellationCacheKey } from "@hardcore/core/lib/renderAssetClient.js";
import { lodTessellationForLevel, normalizeLodLevel } from "@hardcore/core/lib/surf/lodPolicy.js";

const MAX_PACKAGES = 8;
const MAX_BYTES = 256 * 1024 * 1024;

export function completedPackageRevision(entry) {
  if (!renderCapabilities(entrySourceFormat(entry)).topology || entry?.editingPreview
      || entry?.runtimeSurfaceViewReplacement || !entry?.file || !entry?.hash) return "";
  return JSON.stringify([entry.file, entry.kind, entry.hash, entryAssetUrl(entry, "glb"),
    entryMeshAssetSignature(entry), entry.documentHash || "", entry.sourceSidecar?.appearance || null]);
}

function descriptorIdentity(descriptor) {
  return JSON.stringify(descriptor);
}

// Only plain display data is admitted. Structural metadata is private to the
// cache and then cloned for each consumer; immutable typed arrays share their
// existing backing allocations. A scene, worker, promise or selector runtime
// cannot accidentally enter through a new field on a loader context.
function copyDisplayData(value, { maxBytes = Infinity } = {}) {
  const copies = new Map(), buffers = new Set();
  let metadataBytes = 0, typedBytes = 0;
  const charge = size => {
    metadataBytes += size;
    if (metadataBytes + typedBytes > maxBytes) throw new RangeError("Completed package exceeds its cache budget");
  };
  const copy = item => {
    if (item == null) return item;
    if (typeof item !== "object") {
      if (!["string", "number", "boolean", "undefined"].includes(typeof item)) throw new TypeError("Not display data");
      charge(typeof item === "string" ? item.length * 2 : 8);
      return item;
    }
    if (copies.has(item)) return copies.get(item);
    const buffer = ArrayBuffer.isView(item) ? item.buffer : item instanceof ArrayBuffer ? item : null;
    if (buffer) {
      if (!buffers.has(buffer)) { buffers.add(buffer); typedBytes += buffer.byteLength; }
      charge(32);
      copies.set(item, item);
      return item;
    }
    if (!Array.isArray(item) && ![Object.prototype, null].includes(Object.getPrototypeOf(item))) {
      throw new TypeError("Not plain display metadata");
    }
    const result = Array.isArray(item) ? [] : {};
    copies.set(item, result);
    charge(64);
    for (const [key, child] of Object.entries(item)) {
      charge(key.length * 2 + 8);
      Object.defineProperty(result, key, { value: copy(child), enumerable: true, configurable: true, writable: true });
    }
    return result;
  };
  return { value: copy(value), buffers, metadataBytes, typedBytes };
}

export function createCompletedPackageCache({ maxEntries = MAX_PACKAGES, maxBytes = MAX_BYTES } = {}) {
  const entries = new Map(), anonymousScopes = new WeakMap();
  let nextScope = 1;
  const scope = client => {
    if (!client || typeof client !== "object") return "";
    // A root may get a new client after its last tab closes. Both its stable
    // root and exact transport origin must agree before completed data crosses
    // that boundary. Anonymous/test clients remain object-isolated.
    if (client.workspaceId && client.origin) return JSON.stringify([client.origin, client.workspaceId]);
    if (!anonymousScopes.has(client)) anonymousScopes.set(client, nextScope++);
    return `client:${anonymousScopes.get(client)}`;
  };
  const key = (client, entry) => JSON.stringify([scope(client), entry?.file]);
  const stats = ({ excludeBuffers = [] } = {}) => {
    const buffers = new Set(), excluded = new Set(excludeBuffers);
    let typedBytes = 0, metadataBytes = 0;
    for (const cached of entries.values()) {
      metadataBytes += cached.metadataBytes;
      for (const buffer of cached.buffers) {
        if (!buffers.has(buffer) && !excluded.has(buffer)) typedBytes += buffer.byteLength;
        buffers.add(buffer);
      }
    }
    return { entries: entries.size, typedBytes, metadataBytes, bytes: typedBytes + metadataBytes,
      maxEntries, maxBytes, buffers };
  };
  const matchingEntry = (client, entry, descriptor) => {
    const id = key(client, entry), cached = entries.get(id), expected = completedPackageRevision(entry);
    if (!cached) return null;
    if (!expected || cached.revision !== expected
        || (descriptor && cached.descriptorIdentity !== descriptorIdentity(descriptor))) {
      entries.delete(id);
      return null;
    }
    entries.delete(id); entries.set(id, cached);
    return cached;
  };
  return {
    get(client, entry, { descriptor = null } = {}) {
      const cached = matchingEntry(client, entry, descriptor);
      if (!cached) return null;
      try {
        const data = copyDisplayData(cached.value).value;
        // No cached occurrence/material objects are handed to the scene. This
        // composition is cheap and retains the exact component arrays and L/Q/R.
        return { ...data, entry, file: entry.file, meshHash: entryMeshAssetSignature(entry),
          meshUrl: entryAssetUrl(entry, "glb"), complete: true, publishCount: 1,
          meshData: buildComposedPackageMeshData(data.descriptor, data.componentMeshDataByCid) };
      } catch {
        entries.delete(key(client, entry));
        return null;
      }
    },
    // Recognition only needs the accepted D/O bindings. Validate the whole view
    // once, then copy these small records without traversing geometry or exposing
    // the cache's mutable metadata. A missing descriptor cannot prove this view.
    peekComponentIdentities(client, entry, { descriptor } = {}) {
      if (!descriptor) return null;
      const cached = matchingEntry(client, entry, descriptor);
      if (!cached) return null;
      return Object.fromEntries(Object.entries(cached.value.componentIdentityByCid).map(([cid, identity]) => [cid, {
        surfaceInput: identity.surfaceInput, surfaceObject: identity.surfaceObject,
      }]));
    },
    set(client, entry, context) {
      const expected = completedPackageRevision(entry), id = key(client, entry);
      // A declined newer publication must not expose a previous detail tier
      // under the same document revision on the next mount.
      entries.delete(id);
      if (!expected || !scope(client) || !context?.complete || context.lodPending
          || context.meshHash !== entryMeshAssetSignature(entry)) return false;
      const components = Object.entries(context.descriptor?.components || {});
      if (!components.length || components.length !== Object.keys(context.componentMeshDataByCid || {}).length) return false;
      const componentLodLevelByCid = {}, componentKeyByCid = {};
      for (const [cid, component] of components) {
        const mesh = context.componentMeshDataByCid[cid], identity = context.componentIdentityByCid?.[cid];
        const level = normalizeLodLevel(context.componentLodLevelByCid?.[cid] ?? mesh?.lodLevel);
        if (!mesh || !identity?.surfaceInput || !identity.surfaceObject || identity.surfaceInput !== component.surfaceInput
            || (component.surfaceObject && component.surfaceObject !== identity.surfaceObject)
            || normalizeLodLevel(mesh.lodLevel) !== level) return false;
        let concreteKey;
        try { concreteKey = surfTessellationCacheKey("", lodTessellationForLevel(level), identity); }
        catch { return false; }
        if (mesh.lodKey && mesh.lodKey !== concreteKey) return false;
        componentLodLevelByCid[cid] = level;
        componentKeyByCid[cid] = concreteKey;
      }
      // Explicit fields omit live request IDs/controllers, selector bundles,
      // publication receipts, callbacks and any pending LOD transaction.
      let snapshot;
      try {
        snapshot = copyDisplayData({ descriptor: context.descriptor,
          runtimeDescriptor: context.runtimeDescriptor || context.descriptor,
          componentMeshDataByCid: context.componentMeshDataByCid,
          componentIdentityByCid: context.componentIdentityByCid,
          componentLodLevelByCid, componentKeyByCid }, { maxBytes });
      } catch { return false; }
      if (maxEntries < 1) return false;
      const descriptorKey = descriptorIdentity(context.runtimeDescriptor || context.descriptor);
      snapshot.metadataBytes += 2 * (id.length + expected.length + descriptorKey.length);
      entries.set(id, { ...snapshot, revision: expected,
        descriptorIdentity: descriptorKey });
      while (entries.size > maxEntries || stats().bytes > maxBytes) entries.delete(entries.keys().next().value);
      return entries.has(id);
    },
    delete(client, entry) { return entries.delete(key(client, entry)); },
    clear() { const count = entries.size; entries.clear(); return count; },
    stats,
  };
}

export const completedPackages = createCompletedPackageCache();

// Charge shared backing buffers once across displayed/staged arrays, this
// package cache, and core's unchanged component LRU. Metadata is bounded too.
export function renderAssetCacheStatsWithPackages({ excludeBuffers = [] } = {}) {
  const completed = completedPackages.stats({ excludeBuffers });
  const excluded = new Set([...excludeBuffers, ...completed.buffers]);
  const { buffers: _buffers, ...packageStats } = completed;
  return { ...renderAssetCacheStats({ excludeBuffers: excluded }), completedPackages: packageStats };
}

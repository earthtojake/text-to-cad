// Surf component worker (design/surface-rendering.md R2).
//
// One request = one component URL and an explicit capability set. Ordinary
// display asks only for render data; picking/measurement asks for selectors;
// Refinement of active topology asks for both so triangle ranges stay aligned. A current
// cache entry can satisfy render-only requests without fetching or parsing the
// .surf at all. Tessellation is the cost this migration moved from the build
// to the client; running misses here keeps the page's main thread responsive.

import { parseSurf } from "./container.js";
import { tessellateComponent } from "./tessellate.js";
import { buildMeshDataFromSurf } from "./surfMeshData.js";
import { buildSelectorBundleFromSurf } from "./surfSelectorBundle.js";
import { meshDataTransferList } from "../render/meshTransfer.js";
import {
  decodeComponentTessellation,
  edgeClassesFromSurfIndex,
  encodeComponentTessellation,
  surfIndexFromCacheEntry,
} from "./tessellationCache.js";

const activeControllers = new Map();

async function loadArrayBuffer(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }
  return response.arrayBuffer();
}

function bundleTransferList(bundle) {
  return Object.values(bundle?.buffers || {})
    .map((view) => view?.buffer)
    .filter((buffer) => buffer instanceof ArrayBuffer && buffer.byteLength > 0);
}

function requestedCapabilities(message) {
  const value = message?.capabilities;
  // Backward compatibility for callers from an older built client. New
  // callers always send the bounded protocol explicitly.
  if (!value || typeof value !== "object") {
    return { render: true, selectors: true };
  }
  return {
    render: value.render === true,
    selectors: value.selectors === true,
  };
}

self.addEventListener("message", async (event) => {
  const message = event.data || {};
  const id = message.id;
  if (!id) {
    return;
  }
  if (message.type === "cancel") {
    activeControllers.get(id)?.abort();
    activeControllers.delete(id);
    return;
  }
  if (message.type !== "loadSurf") {
    return;
  }
  const controller = new AbortController();
  activeControllers.set(id, controller);
  try {
    const capabilities = requestedCapabilities(message);
    if (!capabilities.render && !capabilities.selectors) {
      throw new Error("Surf worker request has no capabilities");
    }
    // A cached entry (bytes handed in by the client thread, which owns the
    // shared-cache provider) skips tessellation. When its optional display
    // header is complete, a render-only request also skips the .surf fetch and
    // parse. A corrupt/version-drifted entry, or one missing the header fields,
    // is an ordinary miss.
    const cacheIdentity = message.cacheIdentity || {};
    const cached = message.cachedEntry ? decodeComponentTessellation(message.cachedEntry, {
      surfaceInput: cacheIdentity.surfaceInput,
      surfaceObject: cacheIdentity.surfaceObject,
      tessellation: message.tessellation || {},
    }) : null;
    const cachedIndex = surfIndexFromCacheEntry(cached);
    let index = cachedIndex;
    let floats = null;
    if (capabilities.selectors || !cached || (capabilities.render && !cachedIndex)) {
      const buffer = await loadArrayBuffer(message.url, controller.signal);
      ({ index, floats } = parseSurf(buffer));
    }
    // Optional tolerance override (viewport LOD re-tessellates a component at
    // a finer chord level from the same exact surfaces).
    const component = cached
      ? cached.component
      : tessellateComponent(index, floats, message.tessellation || {});
    const meshData = capabilities.render
      ? buildMeshDataFromSurf(index, floats, { component })
      : null;
    const bundle = capabilities.selectors
      ? buildSelectorBundleFromSurf(index, floats, { component })
      : null;
    // On a miss the client asked for the encoded entry back so it can write
    // it into the shared cache. Encoded BEFORE the arrays transfer out below
    // (transfer detaches their buffers).
    const entryBytes = ((!cached && message.wantEntry) || (cached && !cachedIndex))
      ? encodeComponentTessellation(component, {
        surfaceInput: cacheIdentity.surfaceInput,
        surfaceObject: cacheIdentity.surfaceObject,
        tessellation: message.tessellation || {},
        partColor: Array.isArray(index.partColor) ? index.partColor : null,
        edgeClasses: edgeClassesFromSurfIndex(index),
      })
      : null;
    if (controller.signal.aborted) {
      return;
    }
    self.postMessage(
      {
        id,
        ok: true,
        ...(meshData ? { meshData } : {}),
        ...(bundle ? { bundle } : {}),
        ...(entryBytes ? { entryBytes } : {}),
      },
      [...new Set([
        ...(meshData ? meshDataTransferList(meshData) : []),
        ...bundleTransferList(bundle),
        ...(entryBytes ? [entryBytes.buffer] : []),
      ])],
    );
  } catch (error) {
    if (!controller.signal.aborted) {
      self.postMessage({
        id,
        ok: false,
        error: {
          name: error?.name || "Error",
          message: error instanceof Error ? error.message : String(error),
        },
      });
    }
  } finally {
    activeControllers.delete(id);
  }
});

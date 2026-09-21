import { loadRenderJson } from "cadgen-js/lib/renderAssetClient.js";

import { resolvePackageAssetUrl } from "./packageAssetUrl.js";

const PACKAGE_DESCRIPTOR_CACHE = new Map();
const PACKAGE_DESCRIPTOR_CACHE_LIMIT = 32;

// Cache only completed descriptors. An in-flight request belongs to the mesh or
// reference consumer that supplied its AbortSignal; sharing that promise lets
// cancelling either consumer abort the other's read. The descriptor is small,
// immutable and versioned by URL, so overlapping consumers may safely read it
// independently and converge on the same completed cache entry.
export async function loadPackageDescriptor(packageAssetUrl, { signal } = {}) {
  const descriptorUrl = resolvePackageAssetUrl(packageAssetUrl, "assembly.json");
  if (signal?.aborted) {
    return null;
  }
  if (PACKAGE_DESCRIPTOR_CACHE.has(descriptorUrl)) {
    return PACKAGE_DESCRIPTOR_CACHE.get(descriptorUrl);
  }
  const descriptor = await loadRenderJson(descriptorUrl, { signal }).catch(() => null);
  if (!descriptor || signal?.aborted) {
    return null;
  }
  // A surface request can install a newer runtime view while this saved-view
  // read is in flight. That installed view wins; an older response must neither
  // overwrite it nor escape to the caller that is about to compose geometry.
  if (PACKAGE_DESCRIPTOR_CACHE.has(descriptorUrl)) {
    return PACKAGE_DESCRIPTOR_CACHE.get(descriptorUrl);
  }
  if (PACKAGE_DESCRIPTOR_CACHE.size >= PACKAGE_DESCRIPTOR_CACHE_LIMIT) {
    PACKAGE_DESCRIPTOR_CACHE.clear();
  }
  PACKAGE_DESCRIPTOR_CACHE.set(descriptorUrl, descriptor);
  return descriptor;
}

export function installRuntimePackageDescriptor(packageAssetUrl, descriptor) {
  const descriptorUrl = resolvePackageAssetUrl(packageAssetUrl, "assembly.json");
  PACKAGE_DESCRIPTOR_CACHE.set(descriptorUrl, descriptor);
}

import { loadRenderJson } from "@hardcore/core/lib/renderAssetClient.js";

import { cadResourceCacheKey } from "@hardcore/core/client";

const PACKAGE_DESCRIPTOR_CACHE = new Map();
const PACKAGE_DESCRIPTOR_CACHE_LIMIT = 32;

export function peekPackageDescriptor(packageAssetUrl, { resources } = {}) {
  if (!packageAssetUrl) return null;
  const descriptorUrl = resources.resolveDependency(packageAssetUrl, "assembly.json", { kind: "package" });
  return PACKAGE_DESCRIPTOR_CACHE.get(cadResourceCacheKey(resources, descriptorUrl)) || null;
}

// Cache only completed descriptors. An in-flight request belongs to the mesh or
// reference consumer that supplied its AbortSignal; sharing that promise lets
// cancelling either consumer abort the other's read. The descriptor is small,
// immutable and versioned by URL, so overlapping consumers may safely read it
// independently and converge on the same completed cache entry.
export async function loadPackageDescriptor(packageAssetUrl, { signal, resources } = {}) {
  const descriptorUrl = resources.resolveDependency(packageAssetUrl, "assembly.json", { kind: "package" });
  const cacheKey = cadResourceCacheKey(resources, descriptorUrl);
  if (signal?.aborted) {
    return null;
  }
  if (PACKAGE_DESCRIPTOR_CACHE.has(cacheKey)) {
    return PACKAGE_DESCRIPTOR_CACHE.get(cacheKey);
  }
  // Missing (404) means the artifact was never built as a package, which the caller reports.
  // Anything else is the viewer saying why it could not build one: that reaches the person.
  const descriptor = await loadRenderJson(descriptorUrl, { signal, resources }).catch((error) => {
    if (error?.status === 404 || !error?.status) return null;
    throw error;
  });
  if (!descriptor || signal?.aborted) {
    return null;
  }
  // A surface request can install a newer runtime view while this saved-view
  // read is in flight. That installed view wins; an older response must neither
  // overwrite it nor escape to the caller that is about to compose geometry.
  if (PACKAGE_DESCRIPTOR_CACHE.has(cacheKey)) {
    return PACKAGE_DESCRIPTOR_CACHE.get(cacheKey);
  }
  if (PACKAGE_DESCRIPTOR_CACHE.size >= PACKAGE_DESCRIPTOR_CACHE_LIMIT) {
    PACKAGE_DESCRIPTOR_CACHE.clear();
  }
  PACKAGE_DESCRIPTOR_CACHE.set(cacheKey, descriptor);
  return descriptor;
}

export function installRuntimePackageDescriptor(packageAssetUrl, descriptor, { resources } = {}) {
  const descriptorUrl = resources.resolveDependency(packageAssetUrl, "assembly.json", { kind: "package" });
  const cacheKey = cadResourceCacheKey(resources, descriptorUrl);
  if (PACKAGE_DESCRIPTOR_CACHE.size >= PACKAGE_DESCRIPTOR_CACHE_LIMIT && !PACKAGE_DESCRIPTOR_CACHE.has(cacheKey)) PACKAGE_DESCRIPTOR_CACHE.clear();
  PACKAGE_DESCRIPTOR_CACHE.set(cacheKey, descriptor);
}

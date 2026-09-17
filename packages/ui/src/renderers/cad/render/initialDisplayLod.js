import { LOD_DEFAULT_LEVEL, lodTessellationForLevel } from "@hardcore/core/lib/surf/lodPolicy.js";

export const LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS = 64;
export const DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE = 64;
export const COARSE_SURF_DECODE_EXPANSION_ESTIMATE = 32;
export const INITIAL_DECODE_ESTIMATE_FLOOR_BYTES = 64 * 1024 * 1024;

// A large assembly only needs a coarse first pass when standard meshes are
// missing. Prefer the existing standard entry, including when its SURF has
// been reclaimed. Probe metadata before body allocation; the loader still
// reserves memory and verifies the exact object before displaying it.
export async function probeInitialDisplayLod({
  surfaceInput, surfaceObject, maxInFlightBytes, signal, tessellationCache,
  rejectedCacheObjects = new Set(),
  probeEntries = (...args) => tessellationCache.probeCachedTessellationEntries(...args),
}) {
  for (const level of [LOD_DEFAULT_LEVEL, 0]) {
    const hits = await probeEntries([surfaceInput], lodTessellationForLevel(level), { signal });
    const cacheProbe = hits.get(surfaceInput);
    if (!cacheProbe || (surfaceObject && surfaceObject !== cacheProbe.surfaceObject)) continue;
    if (rejectedCacheObjects.has(cacheProbe.object)) continue;
    const estimatedBytes = Number(cacheProbe.byteLength) + Number(cacheProbe.decodedBytes);
    if (!Number.isSafeInteger(estimatedBytes) || estimatedBytes <= 0 || estimatedBytes > maxInFlightBytes) continue;
    return {
      cacheProbe,
      plan: {
        level,
        sourceExpansionRatio: level === 0
          ? COARSE_SURF_DECODE_EXPANSION_ESTIMATE : DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
        estimatedBytes,
        fitsDecodeCap: true,
        reason: level === 0 ? "warm-coarse-cache" : "warm-standard-cache",
      },
    };
  }
  return null;
}

export function estimateInitialSurfDecodeBytes(
  surfBytes,
  sourceExpansionRatio,
  { floorBytes = INITIAL_DECODE_ESTIMATE_FLOOR_BYTES } = {},
) {
  const bytes = Number(surfBytes);
  const expanded = Number.isFinite(bytes) && bytes > 0
    ? bytes * Math.max(1, Number(sourceExpansionRatio) || 1)
    : 0;
  return Math.max(floorBytes, expanded);
}

// Pure per-component initial display decision. Large assemblies take the
// explicit coarse tier throughout. In a smaller package, any individual leaf
// takes that tier when its conservative default estimate cannot be admitted.
// The caller still applies the independent memory reservation; an unfit coarse
// estimate can run only through the caller's serial, globally reserved
// oversized-component path.
export function initialDisplayLodPlan({
  componentCount,
  surfBytes = null,
  maxInFlightBytes,
} = {}) {
  const count = Math.max(0, Math.trunc(Number(componentCount) || 0));
  const cap = Math.max(1, Number(maxInFlightBytes) || 1);
  const defaultEstimate = estimateInitialSurfDecodeBytes(
    surfBytes,
    DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
  );
  const coarse = count >= LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS
    || defaultEstimate > cap;
  const sourceExpansionRatio = coarse
    ? COARSE_SURF_DECODE_EXPANSION_ESTIMATE
    : DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE;
  const estimatedBytes = estimateInitialSurfDecodeBytes(surfBytes, sourceExpansionRatio);
  return {
    level: coarse ? 0 : LOD_DEFAULT_LEVEL,
    sourceExpansionRatio,
    estimatedBytes,
    fitsDecodeCap: estimatedBytes <= cap,
    reason: count >= LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS
      ? "large-assembly"
      : coarse ? "component-admission" : "default",
  };
}

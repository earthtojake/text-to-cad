import { LOD_DEFAULT_LEVEL, lodTessellationForLevel } from "@text-to-cad/core/lib/surf/lodPolicy.js";
import { TESS_PROBE_MAX_KEYS } from "@text-to-cad/core/lib/surf/tessellationCache.js";

export const LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS = 64;
export const DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE = 64;
export const COARSE_SURF_DECODE_EXPANSION_ESTIMATE = 32;
export const INITIAL_DECODE_ESTIMATE_FLOOR_BYTES = 64 * 1024 * 1024;
// The tiers a component may open at, in the order they are tried.
const INITIAL_LEVELS = Object.freeze([LOD_DEFAULT_LEVEL, 0]);
// The first probe of a package covers the loader's first publish (`PROGRESSIVE_PUBLISH_FIRST_COMPONENTS`).
export const INITIAL_PROBE_FIRST_CHUNK = 8;

// A large assembly only needs a coarse first pass when standard meshes are
// missing. Prefer the existing standard entry, including when its SURF has
// been reclaimed. Probe metadata before body allocation; the loader still
// reserves memory and verifies the exact object before displaying it.
//
// The rule for one probed row of one tier: a warm plan when the entry is this
// component's surface, not refused before, and admissible; null otherwise.
export function initialDisplayLodFromProbe(cacheProbe, level, {
  surfaceObject, maxInFlightBytes, rejectedCacheObjects = new Set(),
} = {}) {
  if (!cacheProbe || (surfaceObject && surfaceObject !== cacheProbe.surfaceObject)) return null;
  if (rejectedCacheObjects.has(cacheProbe.object)) return null;
  const estimatedBytes = Number(cacheProbe.byteLength) + Number(cacheProbe.decodedBytes);
  if (!Number.isSafeInteger(estimatedBytes) || estimatedBytes <= 0 || estimatedBytes > maxInFlightBytes) return null;
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

export async function probeInitialDisplayLod({
  surfaceInput, surfaceObject, maxInFlightBytes, signal, tessellationCache,
  rejectedCacheObjects = new Set(),
  probeEntries = (...args) => tessellationCache.probeCachedTessellationEntries(...args),
}) {
  for (const level of INITIAL_LEVELS) {
    const hits = await probeEntries([surfaceInput], lodTessellationForLevel(level), { signal });
    const warm = initialDisplayLodFromProbe(hits.get(surfaceInput), level,
      { surfaceObject, maxInFlightBytes, rejectedCacheObjects });
    if (warm) return warm;
  }
  return null;
}

/**
 * A package's initial display plans, a chunk of components at a time in load order: one metadata
 * probe of the standard tier for the whole chunk, then one of the coarse tier for the components
 * the standard tier did not admit. The rule is `probeInitialDisplayLod`'s; the requests are one per
 * chunk and tier where that made one per component and tier. The first chunk is `firstChunk`
 * components (the loader's first publish) and each next one twice the last, up to `maxChunk`: a
 * server answers a probe a key at a time, so the first geometry waits on a probe of what it draws,
 * not of the whole package. Asking about a chunk probes the two after it with it, so neither a load
 * crossing into the next nor a batch read reaching past it waits; past the first chunk, only once
 * `readAheadAfter` settles (the first body read), so nothing competes with the two requests the
 * first geometry waits on. A probe that fails (an older server, a network error) reads as nothing
 * warm, as it did for one component.
 *
 * `plan(cid)`: that component's warm plan (`{ cacheProbe, plan }`), or null when neither tier
 * holds one; undefined for a component this table was not given. `peek(cid)`: the same without
 * waiting, undefined while its chunk is unprobed. `probed(surfaceInput, level)`: the row a probe of
 * that tier answered for that input (null for none), undefined for a tier it was never asked.
 */
export function createInitialDisplayPlans({
  components, probeEntries, maxInFlightBytes, signal, readAheadAfter = null,
  firstChunk = INITIAL_PROBE_FIRST_CHUNK, maxChunk = TESS_PROBE_MAX_KEYS,
}) {
  const chunks = [];
  const chunkOf = new Map();
  for (const [cid, component] of components) {
    const size = Math.min(maxChunk, Math.max(1, firstChunk) * 2 ** Math.min(30, Math.max(0, chunks.length - 1)));
    if (!chunks.length || chunks.at(-1).length >= size) chunks.push([]);
    chunks.at(-1).push([cid, component]);
    chunkOf.set(cid, chunks.length - 1);
  }
  const plans = new Map();
  const answered = new Map();
  const work = new Map();
  const inputOf = component => String(component?.surfaceInput || "");
  const planChunk = (index) => {
    if (!work.has(index)) {
      const planned = (async () => {
        let remaining = chunks[index];
        for (const level of INITIAL_LEVELS) {
          if (!remaining.length) break;
          const inputs = [...new Set(remaining.map(([, component]) => inputOf(component)))];
          const hits = await probeEntries(inputs, lodTessellationForLevel(level), { signal });
          for (const input of inputs) answered.set(`${level}|${input}`, hits.get(input) || null);
          const next = [];
          for (const [cid, component] of remaining) {
            const warm = initialDisplayLodFromProbe(hits.get(inputOf(component)), level,
              { surfaceObject: component?.surfaceObject, maxInFlightBytes });
            if (warm) plans.set(cid, warm); else next.push([cid, component]);
          }
          remaining = next;
        }
        for (const [cid] of remaining) plans.set(cid, null);
      })();
      // Awaited by whoever asked; a chunk probed ahead fails quietly until somebody does.
      planned.catch(() => {});
      work.set(index, planned);
    }
    return work.get(index);
  };
  return {
    async plan(cid) {
      const index = chunkOf.get(cid);
      if (index === undefined) return undefined;
      const planned = planChunk(index);
      const readAhead = () => {
        for (let ahead = index + 1; ahead <= index + 2 && ahead < chunks.length; ahead += 1) planChunk(ahead);
      };
      if (index === 0 && readAheadAfter) Promise.resolve(readAheadAfter).then(readAhead, () => {});
      else readAhead();
      await planned;
      return plans.get(cid) ?? null;
    },
    peek: cid => plans.get(cid),
    probed: (surfaceInput, level) => (INITIAL_LEVELS.includes(level)
      ? answered.get(`${level}|${String(surfaceInput || "")}`) : undefined),
  };
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

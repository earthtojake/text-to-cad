import { lodDefaultLevel, lodTessellationForLevel } from "@text-to-cad/core/lib/surf/lodPolicy.js";
import { TESS_PROBE_MAX_KEYS } from "@text-to-cad/core/lib/surf/tessellationCache.js";

// The first probe of a package covers the loader's first publish (`PROGRESSIVE_PUBLISH_FIRST_COMPONENTS`).
export const INITIAL_PROBE_FIRST_CHUNK = 8;

// Every component opens at the standard level, whatever the size of its
// assembly: its stored standard mesh when the store holds one, else the one
// cadgen makes in the request that derives its surface. A coarser opening tier
// would cost each component a second mesh, and the store a second entry, for a
// first picture that waits on the surface either way. Coarser meshes are memory
// pressure's (`lodScheduler.js`), never an opening's.

/**
 * The plan for a component whose standard mesh the store holds (`cacheProbe`, its probe row): sized
 * by the stored body, and null when the row is another surface's or a body this load already found
 * missing. One too large to admit with the rest still loads, alone, as the loader admits an oversized
 * single component.
 */
export function initialDisplayLodFromProbe(cacheProbe, {
  surfaceObject, maxInFlightBytes, rejectedCacheObjects = new Set(),
} = {}) {
  if (!cacheProbe || (surfaceObject && surfaceObject !== cacheProbe.surfaceObject)) return null;
  if (rejectedCacheObjects.has(cacheProbe.object)) return null;
  const plan = storedMeshPlan(cacheProbe, "warm", maxInFlightBytes);
  return plan ? { cacheProbe, plan } : null;
}

/**
 * The plan for a component whose standard mesh cadgen just produced (its surface request named the
 * standard tier, and `mesh` is the probe row the request answered with), sized as a warm one is.
 */
export function producedDisplayLodPlan(mesh, { maxInFlightBytes } = {}) {
  return storedMeshPlan(mesh, "produced", maxInFlightBytes);
}

function storedMeshPlan(row, reason, maxInFlightBytes) {
  const estimatedBytes = Number(row?.byteLength) + Number(row?.decodedBytes);
  if (!Number.isSafeInteger(estimatedBytes) || estimatedBytes <= 0) return null;
  return {
    level: lodDefaultLevel(),
    estimatedBytes,
    fitsDecodeCap: estimatedBytes <= Math.max(1, Number(maxInFlightBytes) || 1),
    reason,
  };
}

/** One component's warm plan, probed alone (a retry after a probed body went missing). */
export async function probeInitialDisplayLod({
  surfaceInput, surfaceObject, maxInFlightBytes, signal, tessellationCache,
  rejectedCacheObjects = new Set(),
  probeEntries = (...args) => tessellationCache.probeCachedTessellationEntries(...args),
}) {
  const hits = await probeEntries([surfaceInput], lodTessellationForLevel(lodDefaultLevel()), { signal });
  return initialDisplayLodFromProbe(hits.get(surfaceInput), { surfaceObject, maxInFlightBytes, rejectedCacheObjects });
}

/**
 * A package's initial display plans, a chunk of components at a time in load order: one metadata
 * probe of the standard tier for the whole chunk. The rule is `probeInitialDisplayLod`'s; the
 * requests are one per chunk where that made one per component. The first chunk is `firstChunk`
 * components (the loader's first publish) and each next one twice the last, up to `maxChunk`: a
 * server answers a probe a key at a time, so the first geometry waits on a probe of what it draws,
 * not of the whole package. Asking about a chunk probes the two after it with it, so neither a load
 * crossing into the next nor a batch read reaching past it waits; past the first chunk, only once
 * `readAheadAfter` settles (the first body read), so nothing competes with the two requests the
 * first geometry waits on. A probe that fails (an older server, a network error) reads as nothing
 * warm, as it did for one component.
 *
 * `plan(cid)`: that component's warm plan (`{ cacheProbe, plan }`), or null when the store holds
 * none; undefined for a component this table was not given. `peek(cid)`: the same without waiting,
 * undefined while its chunk is unprobed.
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
  const work = new Map();
  const inputOf = component => String(component?.surfaceInput || "");
  const planChunk = (index) => {
    if (!work.has(index)) {
      const planned = (async () => {
        const chunk = chunks[index];
        const inputs = [...new Set(chunk.map(([, component]) => inputOf(component)))];
        const hits = await probeEntries(inputs, lodTessellationForLevel(lodDefaultLevel()), { signal });
        for (const [cid, component] of chunk) {
          plans.set(cid, initialDisplayLodFromProbe(hits.get(inputOf(component)),
            { surfaceObject: component?.surfaceObject, maxInFlightBytes }));
        }
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
  };
}

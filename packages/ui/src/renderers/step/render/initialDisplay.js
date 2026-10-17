import { TESS_PROBE_MAX_KEYS } from "@text-to-cad/core/lib/parts/tessellationCache.js";

// The first probe of a package covers the loader's first publish (`PROGRESSIVE_PUBLISH_FIRST_COMPONENTS`).
export const INITIAL_PROBE_FIRST_CHUNK = 8;

// Every component opens at, and stays at, its part's display mesh: the stored one when the store
// holds it, else the one cadgen derives in the request that answers with its part's record.

/**
 * What reading and decoding a part's display mesh costs, as its row (core's `partRow`) states it:
 * the stored body's bytes and what decoding them takes, `glb.byteLength + glb.decodedBytes`. The
 * loader admits a component's decode by exactly this. Null for a row that does not say.
 */
export function displayMeshBytes(row) {
  const bytes = Number(row?.glb?.byteLength) + Number(row?.glb?.decodedBytes);
  return Number.isSafeInteger(bytes) && bytes > 0 ? bytes : null;
}

/**
 * The plan for a component whose part the store holds (`cacheProbe`, its row): sized by the stored
 * mesh, and null when it is a mesh this load already found missing. One too large to admit with the
 * rest still loads, alone, as the loader admits an oversized single component.
 */
export function initialDisplayFromProbe(cacheProbe, { rejectedCacheObjects = new Set() } = {}) {
  if (!cacheProbe || rejectedCacheObjects.has(cacheProbe.glb.object)) return null;
  const plan = producedDisplayPlan(cacheProbe);
  return plan ? { cacheProbe, plan } : null;
}

/**
 * The plan for a component whose part cadgen just derived (`row`, the record its request answered
 * with), sized as a warm one is.
 */
export function producedDisplayPlan(row) {
  const estimatedBytes = displayMeshBytes(row);
  return estimatedBytes === null ? null : { estimatedBytes };
}

/** One component's warm plan, probed alone (a retry after a probed body went missing). */
export async function probeInitialDisplay({
  part, signal, tessellationCache,
  rejectedCacheObjects = new Set(),
  probeEntries = (...args) => tessellationCache.probeCachedTessellationEntries(...args),
}) {
  const hits = await probeEntries([part], { signal });
  return initialDisplayFromProbe(hits.get(part), { rejectedCacheObjects });
}

/**
 * A package's initial display plans, a chunk of components at a time in load order: one metadata
 * probe of the parts for the whole chunk. The rule is `probeInitialDisplay`'s; the
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
  components, probeEntries, signal, readAheadAfter = null,
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
  const partOf = component => String(component?.part || "");
  const planChunk = (index) => {
    if (!work.has(index)) {
      const planned = (async () => {
        const chunk = chunks[index];
        const parts = [...new Set(chunk.map(([, component]) => partOf(component)))];
        const hits = await probeEntries(parts, { signal });
        for (const [cid, component] of chunk) {
          plans.set(cid, initialDisplayFromProbe(hits.get(partOf(component))));
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

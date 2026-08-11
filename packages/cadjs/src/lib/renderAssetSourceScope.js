// Render asset caches are page-lifetime: the snapshot batch renderer reuses a single page across
// every job in a packet, so an entry populated while rendering one source outlives that job. An
// entry must therefore never satisfy a different source's request for the same URL — that is the
// stale-pixel failure where two jobs whose inputs resolved to the same render-asset URL silently
// rendered the first job's geometry at exit 0.
//
// Render-asset URLs are keyed by file identity upstream, so a collision should be unreachable.
// This module records the source each cache entry was populated under and turns any future
// re-collision into an error instead of a plausible wrong image. Callers that never declare a
// scope (the interactive viewer) keep the empty default and are unaffected: every comparison is
// then "" === "".
//
// Both render asset clients share this state deliberately. They are near-verbatim forks, and the
// guard living in only one of them is exactly how the hole stayed open.

let activeAssetSourceScope = "";
const assetSourceScopes = new WeakMap();

class RenderAssetSourceScopeError extends Error {
  constructor(message) {
    super(message);
    this.name = "RenderAssetSourceScopeError";
  }
}

export function isRenderAssetSourceScopeError(error) {
  return String(error?.name || "") === "RenderAssetSourceScopeError";
}

function normalizeScope(scope) {
  return typeof scope === "string" ? scope.trim() : "";
}

export function setRenderAssetSourceScope(scope) {
  activeAssetSourceScope = normalizeScope(scope);
}

export function renderAssetSourceScope() {
  return activeAssetSourceScope;
}

// The scope of a resolved render job is its source path: the file the job renders. The snapshot
// driver always resolves and emits it (skills/cad/scripts/snapshot/__main__.py resolve_render_job
// sets resolved.inputPath from an already-resolved absolute path), and cadjs already reads the
// same field for cadPath, so this is not a new field dependency.
//
// A resolved job fails CLOSED: batched jobs are the ones that share a page, so a job that presents
// a resolved packet without a usable source path must not populate those caches at all. Silently
// coercing it to the empty default would both disable the guard for that job and claim every URL it
// touched for "(unset)", which is worse than refusing.
//
// A caller that presents no resolved job — the interactive viewer, and the single-source
// docs/viewer shape documented in packages/cadjs/docs/render-pipeline.md — renders one source per
// page and keeps the unscoped default, unchanged.
export function renderAssetSourceScopeForJob(job) {
  const resolved = job?.resolved;
  if (!resolved || typeof resolved !== "object" || Array.isArray(resolved)) {
    return "";
  }
  const scope = normalizeScope(resolved.inputPath);
  if (!scope) {
    throw new RenderAssetSourceScopeError(
      "Resolved render jobs require resolved.inputPath to scope the render asset cache; refusing "
        + "to populate a page-lifetime cache for an unidentified source."
    );
  }
  return scope;
}

function scopesFor(cache) {
  let scopes = assetSourceScopes.get(cache);
  if (!scopes) {
    scopes = new Map();
    assetSourceScopes.set(cache, scopes);
  }
  return scopes;
}

// Occupancy is re-derived from the cache on every check rather than trusted from the record, so a
// recorded scope can never outlive the entry it describes. Without that, a load that failed or was
// aborted under one source left a permanent claim on a URL nothing had cached, and a later
// legitimate load from another source was rejected with an error claiming the asset "is cached".
export function assertAssetSourceScope(cache, key, { occupied = cache.has(key) } = {}) {
  const scopes = scopesFor(cache);
  const recorded = scopes.get(key);
  if (!occupied || recorded === undefined) {
    scopes.set(key, activeAssetSourceScope);
    return;
  }
  if (recorded !== activeAssetSourceScope) {
    throw new RenderAssetSourceScopeError(
      `Render asset ${key} is cached for source ${recorded || "(unset)"} but was requested for `
        + `${activeAssetSourceScope || "(unset)"}; refusing to reuse it. Two distinct sources `
        + "produced the same render-asset URL."
    );
  }
}

// Non-throwing form for cache peeks: a cross-source entry is not a usable hit, so a peek reports a
// miss and the caller falls through to a real load, which raises the error above if the collision
// is real. Keeping peeks non-throwing preserves their "do I already have this?" contract.
export function assetSourceScopeMatches(cache, key) {
  const recorded = assetSourceScopes.get(cache)?.get(key);
  return recorded === undefined || recorded === activeAssetSourceScope;
}

export function releaseAssetSourceScope(cache, key) {
  assetSourceScopes.get(cache)?.delete(key);
}

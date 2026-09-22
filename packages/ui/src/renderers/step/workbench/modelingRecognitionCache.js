import { cadResourceCacheKey } from "@hardcore/core/client";
// Bump when inference rules, tolerances or serialized recognition results change.
export const MODELING_RECOGNITION_VERSION = 1;
// Hundreds of small unique parts can fit well below the byte budget. Keep a
// whole ordinary assembly warm instead of evicting its tail on every reopen.
const MAX_ENTRIES = 512;
const MAX_BYTES = 8 * 1024 * 1024;

/** Recognition is component-local; occurrence placement and selection remain file-owned. */
export function modelingRecognitionKey(identity, surfUrl, { resources, recognizerVersion = MODELING_RECOGNITION_VERSION } = {}) {
  const scope = resources ? cadResourceCacheKey(resources, "") : "static";
  if (identity?.surfaceInput && identity?.surfaceObject) {
    return JSON.stringify([scope, recognizerVersion, "surface", identity.surfaceInput, identity.surfaceObject]);
  }
  if (!surfUrl) return "";
  // Older static packages carry an immutable component URL instead of D/O.
  return JSON.stringify([scope, recognizerVersion, "url", String(surfUrl)]);
}

/** Store JSON metadata only: no SURF arrays, mutable scene, worker or pending promise. */
export function createModelingRecognitionCache({ maxEntries = MAX_ENTRIES, maxBytes = MAX_BYTES } = {}) {
  const entries = new Map();
  let bytes = 0;
  const remove = key => {
    const entry = entries.get(key);
    if (!entry) return;
    bytes -= entry.bytes;
    entries.delete(key);
  };
  return {
    get(key) {
      const entry = entries.get(key);
      if (!entry) return null;
      entries.delete(key);
      entries.set(key, entry);
      // Each mounted Features tree receives its own mutable presentation metadata.
      return JSON.parse(entry.json);
    },
    set(key, result) {
      if (!key || result?.error || !Array.isArray(result?.tree)) return false;
      const json = JSON.stringify(result);
      const size = 2 * (key.length + json.length);
      remove(key);
      if (size > maxBytes || maxEntries < 1) return false;
      entries.set(key, { json, bytes: size });
      bytes += size;
      while (entries.size > maxEntries || bytes > maxBytes) remove(entries.keys().next().value);
      return true;
    },
  };
}

export const completedModelingRecognition = createModelingRecognitionCache();

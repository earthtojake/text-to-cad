// Composition of a component-GLB package's picking runtimes, split out of
// useCadAssets so it unit-tests in Node (the hook's other imports are
// Vite-resolved; same pattern as scene/partPicking.js).
//
// THE INVARIANT this module exists to hold: the display mesh and the selector
// runtime must always come from ONE mesh of each component. A selector
// bundle's faceRuns are triangle ranges of a SPECIFIC mesh, so another mesh
// read through them mislabels triangles — the user sees striped/partial face
// highlights and picks that resolve through the surface to occluded faces.
import {
  buildSelectorCompositionPart,
  buildSelectorRuntime,
  composeSelectorRuntimes,
  createSelectorRuntimeComposer
} from "@text-to-cad/core/lib/selectors/runtime.js";

// The options one occurrence's selector runtime is built with. Shared by the topology
// composition and the incremental composer so both build picking runtimes IDENTICALLY — the
// options here (partId namespacing, transform placement, the occurrence token every ref of the
// part begins with) are what keep picks aligned with the composed mesh's sourcePartRanges.
function occurrenceRuntimeOptions(entry, occurrence, { singleComponentPart } = {}) {
  const occurrenceId = String(occurrence?.id || "").trim();
  return {
    // The name the host gives the file, which every copied ref carries.
    copyCadPath: String(entry?.fileRefPrefix || ""),
    partId: singleComponentPart ? "" : occurrenceId,
    transform: occurrence?.transform || null,
    occurrenceId
  };
}

function occurrenceBundle(occurrence, bundleByCid) {
  return bundleByCid?.[String(occurrence?.component || "").trim()] || null;
}

// Per-occurrence selector runtimes, one bundle per component cid.
export function buildPackageOccurrenceRuntimes(entry, occurrencesToLoad, bundleByCid, { singleComponentPart } = {}) {
  return (Array.isArray(occurrencesToLoad) ? occurrencesToLoad : [])
    .map((occurrence) => {
      const bundle = occurrenceBundle(occurrence, bundleByCid);
      return bundle ? buildSelectorRuntime(bundle, occurrenceRuntimeOptions(entry, occurrence, { singleComponentPart })) : null;
    })
    .filter(Boolean);
}

// With `composer` (createPackageReferenceComposer), occurrences composed before are not rebuilt;
// the result is the same either way.
export function composePackageSelectorRuntime(entry, occurrencesToLoad, bundleByCid, { singleComponentPart, composer = null } = {}) {
  if (composer) {
    return composer.compose(entry, occurrencesToLoad, bundleByCid, { singleComponentPart });
  }
  return composeSelectorRuntimes(
    buildPackageOccurrenceRuntimes(entry, occurrencesToLoad, bundleByCid, { singleComponentPart })
  );
}

// A transform's exact values: -0 and 0 place a point differently in the last bit of a sign.
function transformKey(transform) {
  if (!Array.isArray(transform)) return JSON.stringify(transform ?? null);
  return transform.map((value) => (typeof value === "number" ? (Object.is(value, -0) ? "-0" : String(value)) : JSON.stringify(value))).join(",");
}

// Incremental composition for one viewer: each placed occurrence is built into a composition part
// once — keyed by its component bundle (the exact bundle object, so a new file
// revision is a different part), its occurrence, placement and copy prefix — and composed by one
// `createSelectorRuntimeComposer`, which re-places only what moved and extends the previous result
// when the new composition begins with it. Adding N occurrences builds N parts, whatever is already
// loaded. Parts not composed in the last `retainCompositions` compositions are dropped, so what a
// collapsed part held is released as it is today.
export function createPackageReferenceComposer({ retainCompositions = 4 } = {}) {
  const composer = createSelectorRuntimeComposer();
  const bundleIds = new WeakMap();
  let nextBundleId = 1;
  const parts = new Map();
  let compositions = 0;
  const bundleId = (bundle) => {
    if (!bundleIds.has(bundle)) bundleIds.set(bundle, nextBundleId++);
    return bundleIds.get(bundle);
  };
  return {
    compose(entry, occurrencesToLoad, bundleByCid, { singleComponentPart } = {}) {
      compositions += 1;
      const list = [];
      for (const occurrence of Array.isArray(occurrencesToLoad) ? occurrencesToLoad : []) {
        const bundle = occurrenceBundle(occurrence, bundleByCid);
        if (!bundle) continue;
        const options = occurrenceRuntimeOptions(entry, occurrence, { singleComponentPart });
        const key = [bundleId(bundle), options.copyCadPath, options.partId, options.occurrenceId, transformKey(options.transform)].join("\u0000");
        let cached = parts.get(key);
        if (!cached) {
          cached = { part: buildSelectorCompositionPart(bundle, options), used: compositions };
          parts.set(key, cached);
        }
        cached.used = compositions;
        list.push(cached.part);
      }
      for (const [key, cached] of parts) {
        if (compositions - cached.used >= retainCompositions) parts.delete(key);
      }
      return composer.compose(list);
    },
    get size() {
      return parts.size;
    },
    reset() {
      parts.clear();
      composer.reset();
    }
  };
}

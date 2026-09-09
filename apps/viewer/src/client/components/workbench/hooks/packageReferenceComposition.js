// Composition of a component-GLB package's picking runtimes, split out of
// useCadAssets so it unit-tests in Node (the hook's other imports are
// Vite-resolved; same pattern as viewer/hooks/partPicking.js).
//
// THE INVARIANT this module exists to hold (viewport LOD, design/
// unified-tessellation.md Phase 5): the display mesh and the selector runtime
// must always come from ONE tessellation of each component. A selector
// bundle's faceRuns are triangle ranges of a SPECIFIC tessellation, so a
// level-N mesh read through level-M runs mislabels triangles — the user sees
// striped/partial face highlights and picks that resolve through the surface
// to occluded faces. Every level swap therefore re-composes the runtime from
// the swapped level's bundle (swapCompositionBundle), and a topology load
// that lands after a swap composes from the swapped bundle, not the level-0
// cache.
import { buildSelectorRuntime, composeSelectorRuntimes } from "cadgen-js/lib/selectors/runtime.js";

// Per-occurrence selector runtimes, one bundle per component cid. Shared by
// the initial topology composition and the LOD re-composition so both build
// picking runtimes IDENTICALLY — the options here (partId namespacing,
// transform placement, remapOccurrenceId) are what keep picks aligned with
// the composed mesh's sourcePartRanges.
export function buildPackageOccurrenceRuntimes(entry, occurrencesToLoad, bundleByCid, { singleComponentPart } = {}) {
  return (Array.isArray(occurrencesToLoad) ? occurrencesToLoad : [])
    .map((occurrence) => {
      const bundle = bundleByCid?.[String(occurrence?.component || "").trim()];
      if (!bundle) {
        return null;
      }
      const occurrenceId = String(occurrence?.id || "").trim();
      return buildSelectorRuntime(bundle, {
        // The SUFP, not the full path: a copied ref should be compact.
        copyCadPath: String(entry?.fileRefPrefix || ""),
        partId: singleComponentPart ? "" : occurrenceId,
        transform: occurrence?.transform || null,
        remapOccurrenceId: occurrenceId
      });
    })
    .filter(Boolean);
}

export function composePackageSelectorRuntime(entry, occurrencesToLoad, bundleByCid, { singleComponentPart } = {}) {
  return composeSelectorRuntimes(
    buildPackageOccurrenceRuntimes(entry, occurrencesToLoad, bundleByCid, { singleComponentPart })
  );
}

// Whether a remembered composition includes any occurrence of `cid` — i.e.
// whether an LOD swap of that component requires re-composing picking.
export function compositionUsesComponent(composition, cid) {
  return (Array.isArray(composition?.occurrencesToLoad) ? composition.occurrencesToLoad : [])
    .some((occurrence) => String(occurrence?.component || "").trim() === String(cid || "").trim());
}

// The remembered composition with one component's bundle replaced by the
// level the display mesh just moved to. Pure: returns the next composition,
// callers store it and re-compose from it.
export function swapCompositionBundle(composition, cid, bundle) {
  return {
    ...composition,
    bundleByCid: { ...composition.bundleByCid, [String(cid || "").trim()]: bundle }
  };
}

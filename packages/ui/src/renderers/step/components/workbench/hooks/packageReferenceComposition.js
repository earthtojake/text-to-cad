// Composition of a component-GLB package's picking runtimes, split out of
// useCadAssets so it unit-tests in Node (the hook's other imports are
// Vite-resolved; same pattern as scene/partPicking.js).
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
import { buildSelectorRuntime, composeSelectorRuntimes } from "@hardcore/core/lib/selectors/runtime.js";

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

// Reference loads can finish while a display replacement still owns its old
// scene. Keep both exact selector levels ready for the same newly demanded
// occurrence subset, and recheck if adoption changed during either await.
export async function reconcileLodReferencePublication({ pendingForContext, loadBaseBundle, reconcile, isCurrent, maxPasses = 16 }) {
  for (let pass = 0; pass < maxPasses && isCurrent(); pass++) {
    const pending = pendingForContext();
    const phase = pending?.phase;
    const baseBundle = pending && phase !== "restoring" ? await loadBaseBundle(pending) : null;
    if (!isCurrent()) return null;
    const bundles = await reconcile();
    if (!bundles || !isCurrent()) return null;
    if (pendingForContext() === pending && pending?.phase === phase) return { bundles, pending, baseBundle };
  }
  if (!isCurrent()) return null;
  throw new Error("Selector publication could not settle on the displayed component LOD");
}

export function baseLodReferenceComposition(composition, pending, baseBundle) {
  if (!pending || pending.phase === "restoring") return composition;
  let base = composition;
  for (const item of pending.items || [pending]) {
    if (!compositionUsesComponent(composition, item.cid)) continue;
    const bundle = pending.items ? baseBundle?.[item.cid] : baseBundle;
    if (!bundle) throw new Error("Previous detail's selector bundle is unavailable");
    base = swapCompositionBundle(base, item.cid, bundle);
  }
  return base;
}

// Resolve selector bundles against the LOD state that is live immediately
// before composition. Initial selector fetches can overlap a viewport LOD
// swap; their result is exact for the level they requested, but no longer for
// the mesh on screen. Keys include the component surf URL and effective
// tessellation inputs, so a same-named LOD level can never stand in for a
// different concrete geometry request.
export async function reconcileLivePackageSelectorBundles({
  cids,
  initialBundleByCid,
  initialKeyByCid,
  snapshotLiveLod,
  keyForLevel,
  loadForLevel,
  isCurrent = () => true,
  maxPasses = 16
}) {
  const resolved = {};
  for (const rawCid of cids || []) {
    const cid = String(rawCid || "").trim();
    if (!cid) continue;
    resolved[cid] = {
      key: initialKeyByCid?.[cid] || "",
      bundle: initialBundleByCid?.[cid] || null
    };
  }

  for (let pass = 0; pass < maxPasses; pass += 1) {
    if (!isCurrent()) return null;
    const live = snapshotLiveLod() || {};
    const loads = [];
    for (const cid of Object.keys(resolved)) {
      const level = Number(live.levelByCid?.[cid]) || 0;
      const key = keyForLevel(cid, level);
      const liveBundle = live.bundleByCid?.[cid];
      if (liveBundle) {
        resolved[cid] = { key, bundle: liveBundle };
      } else if (resolved[cid].key !== key) {
        loads.push((async () => {
          const bundle = await loadForLevel(cid, level, key);
          return { cid, key, bundle: bundle || null };
        })());
      }
    }
    if (loads.length) {
      for (const result of await Promise.all(loads)) {
        resolved[result.cid] = result;
      }
      continue;
    }

    // One final synchronous snapshot closes a swap between the scan above and
    // composition. If it moved again without publishing a bundle, the next
    // pass fetches that exact concrete tessellation and rechecks once more.
    const finalLive = snapshotLiveLod() || {};
    let stable = true;
    for (const cid of Object.keys(resolved)) {
      const level = Number(finalLive.levelByCid?.[cid]) || 0;
      const key = keyForLevel(cid, level);
      const liveBundle = finalLive.bundleByCid?.[cid];
      if (liveBundle) {
        resolved[cid] = { key, bundle: liveBundle };
      } else if (resolved[cid].key !== key) {
        stable = false;
      }
    }
    if (stable && isCurrent()) {
      return Object.fromEntries(
        Object.entries(resolved)
          .filter(([, value]) => value.bundle)
          .map(([cid, value]) => [cid, value.bundle])
      );
    }
  }
  throw new Error("Selector topology could not settle on the displayed component LOD");
}

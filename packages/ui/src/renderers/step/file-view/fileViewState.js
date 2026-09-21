// Per-file surface defaults and normalization. Hosts own storage and panel layout.
// Single user-facing label for "the viewer is (re)generating the render artifacts a STEP model
// needs before it can render" — used for both the filename status chip and its tooltip across every
// artifact-generation trigger (first build, stale rebuild, source-changed regen). Browser-side
// asset-load/parse stages ("loading mesh", reference "loading topology", etc.) are a different
// concept and keep their own wording.
export const ARTIFACT_GENERATING_LABEL = "Generating artifacts";
export const EMPTY_LIST = Object.freeze([]);
export const DEFAULT_LARGE_FILE_STATE = Object.freeze({
  selectableTopologyEnabled: false
});

export function normalizeLargeFileState(value = {}) {
  return {
    selectableTopologyEnabled: value?.selectableTopologyEnabled === true
  };
}

// Hide an entry's render assets (url/hash/bytes/assets) so the viewer treats it as "not yet
// renderable" — used while its render artifact is missing/stale/building or has failed, so the
// viewer shows a loading/error state and never renders a stale cache. Once the artifact is ready
// the unstripped catalog entry is used and the mesh loads.
export function entryWithoutRenderAssets(entry) {
  if (!entry) {
    return entry;
  }
  const next = { ...entry };
  delete next.url;
  delete next.hash;
  delete next.bytes;
  delete next.assets;
  // A baked mesh published as a `glb` relation rather than as the entry's own url would
  // otherwise stay renderable while its replacement is being built -- which is exactly the
  // stale cache this function exists to hide.
  if (next.relations?.glb) {
    const relations = { ...next.relations };
    delete relations.glb;
    next.relations = relations;
  }
  return next;
}

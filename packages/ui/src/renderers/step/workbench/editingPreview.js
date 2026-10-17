// A tab's view of the build feed for its file: whether a build is running, how far it has got,
// whether it failed, and the preview revision it announced (`preview`: the names of artifact-side
// objects, never geometry -- STORE.md 9b). The view shows the saved file, or that preview labelled
// as one until the file replaces it in place.
export const BUILDING_STATES = Object.freeze(["submitted", "queued", "building"]);

export function initialEditingPreview() {
  return {
    epoch: "",
    revision: 0,
    superseded: false,
    state: "disconnected",
    phase: "",
    detail: "",
    updatedAt: 0,
    error: "",
    preview: null,
    saved: null,
  };
}

// The file the build saved, as the feed names it: the tree its bytes were written from and their
// digest; null while the build has written nothing. A build records its result and writes its file
// after, so this is the feed's second event, which the catalog is read on.
function savedFile(value) {
  const tree = String(value?.tree || "").trim();
  const documentHash = String(value?.documentHash || "").trim();
  return tree && documentHash ? { tree, documentHash } : null;
}

// The preview revision an answer names, as the state keeps it; null for an answer naming none
// (the build's result does not exist yet).
function previewRevision(value) {
  const tree = String(value?.tree || "").trim();
  if (!tree) return null;
  const producer = value.producer && typeof value.producer === "object" && !Array.isArray(value.producer) ? value.producer : null;
  const parts = value.parts && typeof value.parts === "object" && !Array.isArray(value.parts) ? value.parts : {};
  return {
    tree,
    producer,
    parts: Object.fromEntries(Object.entries(parts).map(([cid, part]) => [String(cid), String(part)])),
    complete: value.complete === true,
    annotations: String(value.annotations || "").trim() || null,
  };
}

/**
 * The annotations object as it binds to `preview`: the object itself when the build resolved it
 * against the preview's tree, else null -- a late read of another revision's object, or a tree the
 * feed has moved on from, binds nothing.
 */
export function previewAnnotationsFor(preview, object) {
  return preview?.tree && object && typeof object === "object" && object.tree === preview.tree ? object : null;
}

/** Whether a build of the file is queued or running. */
export function editingBuildActive(state) {
  return BUILDING_STATES.includes(state?.state);
}

export function reduceEditingPreview(current, next) {
  if (!next || typeof next !== "object") return current;
  if (!next.epoch) {
    // The server lists no build of the file (no daemon, or one restarted since): there is no
    // preview. A poll that failed says nothing of the build, so the preview in hand stays.
    const listed = next.state === "disconnected";
    return { ...current, state: "disconnected", phase: "", detail: "", updatedAt: 0, error: next.error || "",
      preview: listed ? null : current.preview };
  }
  const previous = current.epoch && current.epoch !== next.epoch ? initialEditingPreview() : current;
  const revision = Number(next.revision) || 0;
  if (revision < previous.revision) return current;
  const same = revision === previous.revision;
  const state = next.state || "building";
  const active = BUILDING_STATES.includes(state);
  // A build the file moved past (the server's `superseded`): its failure is no longer the news.
  const superseded = next.superseded === true;
  return {
    epoch: next.epoch,
    revision,
    superseded,
    state,
    phase: active ? String(next.phase || (same ? previous.phase : "") || "").trim() : "",
    detail: active ? String(next.detail || (same ? previous.detail : "") || "").trim() : "",
    updatedAt: active ? Number(next.updatedAt) || (same ? previous.updatedAt : 0) || 0 : 0,
    error: superseded ? "" : next.error || "",
    output: next.output,
    file: next.file || next.output,
    // Named from the moment the result exists; a build the file moved past has none to show.
    preview: superseded ? null : previewRevision(next.preview),
    saved: savedFile(next.saved),
  };
}

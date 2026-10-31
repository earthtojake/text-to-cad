import { isProgressEvent, progressFraction, progressKey } from "./progressEvent.js";

// A stage reports a real fraction (`done` of a `total` above zero) or nothing.
function stageFraction(progress) {
  return progressFraction(progress);
}

// A file cadgen is importing: the compile that reads its bytes, whose phases cadgen labels
// as importing. The word a CAD user knows from opening a file anywhere else.
function importing(hint) {
  return /\bcompil|\bimport/.test(hint);
}

// The phases a cadgen build once reported before the engine's progress event (below); the page emits
// none of them.
const BUILD_PHASES = new Set(["load", "body", "names", "document", "write", "generate", "package", "components", "finalize", "mesh"]);

// Internal phases stay diagnostic data. The screen describes the user's wait. "Reading model" is
// only ever an actual read of a model the store holds; a wait with nothing more specific to say is
// "Opening model". The engine's own progress event (`progressEvent.js`: a build's, an import's, an
// export's, a snapshot's or a measurement's stage) is named by its key, `progress.<kind>.<stage>`,
// which the screen says in the view's language (`statusLabels.js`), with its count where it has one.
export function loadingProgress(progress, { finding = false, preparing = false } = {}) {
  if (!finding && !preparing && isProgressEvent(progress)) {
    const frame = stageFraction(progress);
    return { label: progressKey(progress), detail: String(progress.detail || ""), counts: frame.counts, percent: frame.percent,
      connectionLost: progress.connectionLost || null };
  }
  const phase = String(progress?.phase || "").toLowerCase();
  const hint = `${phase} ${progress?.label || ""}`.toLowerCase();
  const label = finding ? "Finding file"
    : preparing ? "Preparing view"
    : /catalog|metadata|finding/.test(hint) ? "Finding file"
    : importing(hint) ? "Importing model"
    // A model script running: every phase of its build, the parts it stores included.
    : BUILD_PHASES.has(phase) ? "Building model"
    // cadgen is meshing parts the store did not hold (a cold open); a warm open only reads them.
    : phase === "meshing" ? "Meshing parts"
    : phase === "read" ? "Reading model"
    : /geometry|mesh|surface|tessellat/.test(hint) ? "Loading geometry"
    : /view|finaliz|writing|saving|saved|module|building assembly/.test(hint) ? "Preparing view"
    : "Opening model";
  const frame = stageFraction(progress);
  return {
    label,
    detail: String(progress?.detail || ""),
    counts: !finding && !preparing ? frame.counts : "",
    percent: !finding && !preparing && frame.determinate ? frame.percent : null,
    connectionLost: progress?.connectionLost || null,
  };
}

// `currentPreview`: what is drawn is the build's own preview revision, so the
// wait for that build is over even though its write is not; the view says so in its place.
export function viewerLoadingState({
  busy = false, editPending = false, previousView = false, currentPreview = false,
  error = null, progress = null,
  finding = false, preparing = false,
} = {}) {
  const failed = error && (typeof error === "string" || error.severity !== "warning" || error.blocking === true);
  const active = !failed && (busy || (editPending && !currentPreview));
  return {
    opening: active && !previousView,
    updating: active && previousView,
    busy: active,
    preview: currentPreview === true,
    progress: loadingProgress(progress, { finding, preparing }),
  };
}

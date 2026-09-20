import { artifactWarningItems } from "./artifactWarnings.js";

function status(label, title, tone = "neutral", busy = false) {
  return { label, title, tone, busy };
}

function text(value) {
  return String(value || "").trim();
}

function previewIsCurrent(editingState) {
  const revision = Number(editingState?.revision) || 0;
  const previewRevision = Number(editingState?.preview?.revision) || 0;
  return Boolean(revision && previewRevision === revision);
}

function failureStatus(error, { hasGeometry, editingState, showingPreview, savedAs }) {
  const editState = text(editingState?.state).toLowerCase();
  const editError = text(editingState?.error);
  const explicitEditFailure = editState === "failed" && editError;
  const blockedMissingPreview = editingState?.previewUnavailable
    && !hasGeometry
    && !editingState?.saved
    && !editingState?.retainedSaved;
  const failure = error || (explicitEditFailure || blockedMissingPreview
    ? { message: editError || "The live model is no longer available." }
    : null);
  if (!failure) {
    return null;
  }

  const record = typeof failure === "object" ? failure : {};
  if (record.severity === "warning") {
    return null;
  }
  const updatedModelVisible = showingPreview && previewIsCurrent(editingState);
  const usableModelVisible = Boolean(hasGeometry || showingPreview);
  const label = usableModelVisible ? "Update failed" : "Open failed";
  // Dialogs retain full diagnostics; a tooltip explains the view, never a trace.
  if (updatedModelVisible && explicitEditFailure) {
    return status(label, `The new geometry is visible, but it was not written to the ${savedAs}.`, "error");
  }
  const explanation = text(record.tooltip) || (usableModelVisible
    ? "The latest update couldn’t be loaded."
    : "The viewer couldn’t prepare this file for display.");
  return status(label, [
    explanation,
    usableModelVisible ? "You’re still viewing the previous version." : "",
  ].filter(Boolean).join(" "), "error");
}

function loadingExplanation(progress, { updating, renderMode }) {
  if (progress?.connectionLost) {
    return "Waiting for the viewer to respond. The browser is retrying automatically.";
  }
  const stage = {
    "Finding file": "Looking up the selected file before loading it.",
    "Reading model": "Reading the model and preparing its shapes for display.",
    "Loading geometry": "Loading the shapes that make up the model.",
    "Preparing view": renderMode
      ? "Setting up the lighting and drawing the render."
      : "Preparing the model’s appearance before showing it.",
  }[progress?.label] || "Preparing the selected model for display.";
  // Counts describe this stage only, never overall completion or an ETA.
  const counts = /^(\d+)\/(\d+)$/.exec(text(progress?.counts));
  return [
    stage,
    counts ? `${counts[1]} of ${counts[2]} items complete in this stage.` : "",
    updating ? "The update will appear automatically when it’s ready." : "",
  ].filter(Boolean).join(" ");
}

/**
 * Resolve the single compact status shown beside the selected filename.
 *
 * `opening` covers every incomplete first load, including a progressive load
 * that already has partial geometry. `updating` covers a replacement of a
 * complete same-file view. `showingPreview` is true only after the current
 * authored preview has actually reached the viewport.
 *
 * `reloading` is the development backend restarting itself onto its own port
 * after its Python changed. It outranks everything: the page is about to
 * reload, so no other verdict about this file is worth showing. It is
 * unreachable in an installed wheel, which never watches its own code.
 */
export function resolveFileStatus({
  hasFile = false,
  error = null,
  opening = false,
  updating = false,
  loadingProgress = null,
  renderMode = false,
  editingState = null,
  showingPreview = false,
  qualityStatus = null,
  hasGeometry = false,
  reloading = false,
  // What a live edit is saved as, in the words of whoever offers editing.
  savedAs = "file"
} = {}) {
  if (!hasFile) {
    return null;
  }

  if (reloading) {
    return status(
      "Reloading",
      "The viewer’s code changed. The page reloads as soon as the updated viewer is ready.",
      "info",
      true
    );
  }

  const failure = failureStatus(error, { hasGeometry, editingState, showingPreview, savedAs });
  if (failure) {
    return failure;
  }

  // A current preview is the result of the update. Its save to disk and any
  // remaining background preparation do not keep the filename busy.
  if (updating) {
    if (!showingPreview) {
      return status(
        "Updating",
        loadingExplanation(loadingProgress, { updating: true, renderMode }),
        "info",
        true
      );
    }
  } else if (opening) {
    return status(
      "Opening",
      loadingExplanation(loadingProgress, { updating: false, renderMode }),
      "info",
      true
    );
  }

  if (error?.severity === "warning") {
    // An alert carrying backend warnings summarizes THEM: the badge's tooltip is
    // the only place their headings fit before the dialog is opened. The label
    // stays the same string whatever the count, because it is also the badge's
    // `data-file-status` hook.
    const warnings = artifactWarningItems(error);
    if (warnings.length > 0) {
      return status(
        "Model warning",
        warnings.map((warning) => warning.heading || warning.message).join(" "),
        "warning"
      );
    }
    return status("Model warning", text(error.tooltip || error.message) || "Some model settings could not be applied. The model can still be viewed.", "warning");
  }

  if (qualityStatus?.state === "limited" || qualityStatus?.state === "error") {
    return status(
      "Limited detail",
      text(qualityStatus.title) || "Some surfaces are shown at lower detail. This affects the view, not the model’s geometry.",
      "warning"
    );
  }

  return null;
}

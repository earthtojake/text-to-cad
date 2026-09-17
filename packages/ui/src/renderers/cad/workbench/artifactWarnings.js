// The advisory `warnings` an artifact-status payload may carry.
//
// A warning describes the document's NEIGHBOURS, not its state: the backend
// attaches the same list to `compiled`, `not-compiled` and `failed` alike (and
// to the narrowed compile offer), so a warning NEVER means the entry failed.
// The geometry on screen is correct; something beside it is not.
//
// Each warning arrives as the viewer's actionable triple — heading, explanation,
// recovery step — the shape every alert here already renders. This module only
// normalizes and forwards those fields: it knows nothing about what any given
// warning is about, so a new backend warning reaches the UI with no change here.

function text(value) {
  return String(value ?? "").trim();
}

function warningList(source) {
  if (Array.isArray(source)) {
    return source;
  }
  return Array.isArray(source?.warnings) ? source.warnings : [];
}

function normalizeWarning(entry) {
  // A bare sentence is still an explanation; it has no heading of its own and
  // offers no recovery step. Older servers and any hand-built payload land here.
  if (typeof entry === "string") {
    return { heading: "", message: text(entry), recovery: "" };
  }
  if (!entry || typeof entry !== "object") {
    return null;
  }
  return {
    heading: text(entry.heading),
    message: text(entry.message),
    recovery: text(entry.recovery),
  };
}

/**
 * The renderable warnings in a status payload, an alert, or a bare array.
 *
 * Entries with nothing to say are dropped and exact duplicates collapse, so a
 * caller can ask "are there any?" by looking at the length.
 */
export function artifactWarningItems(source) {
  const items = [];
  const seen = new Set();
  for (const entry of warningList(source)) {
    const item = normalizeWarning(entry);
    if (!item || (!item.heading && !item.message)) {
      continue;
    }
    const key = JSON.stringify([item.heading, item.message, item.recovery]);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    items.push(item);
  }
  return items;
}

/**
 * The alert that carries those warnings, or null when there are none.
 *
 * Deliberately `blocking: false` and warning severity: the model renders, so
 * this rides the file-status badge and its dialog instead of covering the
 * viewport. The per-warning wording stays in `warnings` rather than being
 * flattened into `message`/`recovery`, so the dialog can list several and the
 * badge can summarize them — and `details` repeats the text, which is what
 * makes `fileStatusAlertKey` notice one warning list replacing another.
 */
export function buildArtifactWarningAlert(fileRef, source) {
  const warnings = artifactWarningItems(source);
  if (warnings.length === 0) {
    return null;
  }
  const summary = warnings.length > 1 ? `${warnings.length} model warnings` : "Model warning";
  return {
    severity: "warning",
    kind: "advisory",
    blocking: false,
    compact: true,
    summary,
    title: summary,
    warnings,
    details: [
      text(fileRef) && `File: ${text(fileRef)}`,
      ...warnings.map((item) => [item.heading, item.message, item.recovery].filter(Boolean).join(" ")),
    ].filter(Boolean).join("\n"),
  };
}

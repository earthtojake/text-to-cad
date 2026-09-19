import assert from "node:assert/strict";
import test from "node:test";

import { resolveFileStatus } from "./fileStatus.js";
import { buildViewerMeshAlert, resolveFileStatusAlert } from "./viewerAlerts.js";

const ready = { hasFile: true, hasGeometry: true };

test("idle files and optional edit-feed states stay quiet", () => {
  assert.equal(resolveFileStatus(), null);
  assert.equal(resolveFileStatus(ready), null);
  assert.equal(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "done", saved: { tree: "saved" } }
  }), null);
  assert.equal(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "disconnected", error: "Connection closed" }
  }), null);
  assert.equal(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "building", revision: 3, preview: { revision: 3 } }
  }), null);
});

test("opening is authoritative for incomplete first loads, including partial geometry", () => {
  const opening = resolveFileStatus({
    ...ready,
    opening: true,
    loadingProgress: { label: "Loading geometry", counts: "4/12" }
  });
  assert.equal(opening.label, "Opening");
  assert.equal(opening.busy, true);
  assert.match(opening.title, /4 of 12.*in this stage/);
  const interrupted = resolveFileStatus({
    hasFile: true, opening: true,
    loadingProgress: { label: "Loading geometry", counts: "4/12", connectionLost: { failures: 1 } }
  });
  assert.match(interrupted.title, /retrying automatically/);
  assert.doesNotMatch(interrupted.title, /4 of 12/);
});

test("updates stay busy only until the current preview is displayed", () => {
  assert.equal(resolveFileStatus({
    ...ready,
    opening: true,
    updating: true,
    loadingProgress: { label: "Preparing view" }
  }).label, "Updating");

  assert.equal(resolveFileStatus({
    ...ready,
    updating: true,
    showingPreview: true,
    editingState: { state: "building", revision: 4, preview: { revision: 4 } }
  }), null);
});

test("failure tooltips explain the visible version and keep diagnostics in the dialog", () => {
  const diagnostic = "Invalid file header\nfull parser trace";
  const error = buildViewerMeshAlert({ file: "part.step", kind: "part" }, false, diagnostic);
  const opening = resolveFileStatus({ hasFile: true, error });
  assert.equal(opening.label, "Open failed");
  assert.doesNotMatch(opening.title, /parser trace|previous version/);
  assert.match(resolveFileStatusAlert(opening, error).details, /full parser trace/);
  const update = resolveFileStatus({ ...ready, error });
  assert.equal(update.label, "Update failed");
  assert.match(update.title, /previous version/);
  assert.doesNotMatch(update.title, /parser trace/);
});

test("a failed save explains that the updated model remains visible", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: {
      state: "failed",
      error: "Disk full",
      revision: 5,
      preview: { revision: 5 }
    }
  }), {
    label: "Update failed",
    title: "The new geometry is visible, but it was not written to the STEP file.",
    tone: "error",
    busy: false
  });
});

test("backend warnings badge the entry without failing it", () => {
  const alert = {
    severity: "warning",
    title: "Model warning",
    warnings: [
      {
        heading: "part.step.js is a retired render module",
        message: "It is read by nothing.",
        recovery: "Move its clips into the decorator and delete part.step.js."
      }
    ]
  };
  // A warning is not a failure: the model stays visible and the badge summarizes
  // the server's own heading rather than any wording of the client's.
  assert.deepEqual(resolveFileStatus({ ...ready, error: alert }), {
    label: "Model warning",
    title: "part.step.js is a retired render module",
    tone: "warning",
    busy: false
  });
  // Several warnings keep one stable badge label -- it is also the `data-file-status` hook.
  const two = resolveFileStatus({
    ...ready,
    error: { ...alert, warnings: [...alert.warnings, { heading: "Second neighbour", message: "" }] }
  });
  assert.equal(two.label, "Model warning");
  assert.equal(two.title, "part.step.js is a retired render module Second neighbour");
  // A warning with no heading falls back to its explanation, and an alert with no
  // warnings at all keeps the pre-existing tooltip/message behaviour.
  assert.equal(
    resolveFileStatus({ ...ready, error: { ...alert, warnings: ["Bare sentence."] } }).title,
    "Bare sentence."
  );
  assert.equal(
    resolveFileStatus({
      ...ready,
      error: { ...alert, warnings: [], message: "Saved model settings are unavailable." }
    }).title,
    "Saved model settings are unavailable."
  );
  assert.equal(
    resolveFileStatus({ ...ready, error: { ...alert, warnings: [] } }).title,
    "Some model settings could not be applied. The model can still be viewed."
  );
});

test("warnings remain actionable while successful background work stays quiet", () => {
  assert.equal(resolveFileStatus({
    ...ready,
    error: { severity: "warning", message: "Saved model settings are unavailable." }
  }).label, "Model warning");
  assert.equal(resolveFileStatus({
    ...ready, opening: true,
    error: { severity: "warning", message: "Saved model settings are unavailable." }
  }).label, "Opening");
  assert.equal(resolveFileStatus({
    ...ready,
    editingState: { state: "done", previewUnavailable: true, saved: { tree: "saved" } }
  }), null);
  assert.equal(resolveFileStatus({
    hasFile: true,
    editingState: { state: "done", previewUnavailable: true }
  }).label, "Open failed");
  assert.deepEqual(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "refining", title: "More detail is loading." }
  }), null);
  assert.deepEqual(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "error", title: "Fine surfaces could not be loaded." }
  }), {
    label: "Limited detail",
    title: "Fine surfaces could not be loaded.",
    tone: "warning",
    busy: false
  });
});

test("the resolver emits only the approved filename labels", () => {
  const inputs = [
    { hasFile: true, opening: true },
    { ...ready, updating: true },
    { hasFile: true, error: "bad" },
    { ...ready, error: "bad" },
    { ...ready, qualityStatus: { state: "limited" } },
    { ...ready, error: { severity: "warning", message: "Missing settings" } }
  ];
  const allowed = new Set(["Opening", "Updating", "Open failed", "Update failed", "Limited detail", "Model warning"]);
  for (const input of inputs) {
    assert.ok(allowed.has(resolveFileStatus(input).label));
  }
});

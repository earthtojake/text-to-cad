import assert from "node:assert/strict";
import { test } from "node:test";
import { shellLoadReport } from "../../../../dist/renderers/kit/shell/loadReport.js";

const base = { hasFile: true, alert: null, busy: false, previousView: false, hasGeometry: true, renderMode: false, preparing: false };

// A renderer whose document is a plain download passes `load` and nothing else. Its
// report must be exactly what it was before the optional fields existed, which is
// what glb, mesh and robot get: no edit states, no preview, no quality verdict, no
// warning, and no chip at all once the file is on screen.
test("a renderer that passes nothing gets the plain download report", () => {
  const report = shellLoadReport({ load: { busy: false }, ...base });
  assert.deepEqual(report.loading, { opening: false, updating: false, busy: false,
    progress: { label: "Reading model", detail: "", counts: "", percent: null, connectionLost: null } });
  assert.equal(report.fileStatus, null);
  assert.equal(report.fileStatusAlert, null);
});

test("busy with nothing on screen opens; busy over a complete view updates", () => {
  const opening = shellLoadReport({ load: { busy: true }, ...base, hasGeometry: false });
  assert.deepEqual([opening.loading.opening, opening.loading.updating], [true, false]);
  assert.equal(opening.fileStatus.label, "Opening");
  const updating = shellLoadReport({ load: { busy: false, updating: true }, ...base, previousView: true });
  assert.deepEqual([updating.loading.opening, updating.loading.updating], [false, true]);
  assert.equal(updating.fileStatus.label, "Updating");
});

// `busy` the shell's own (a presentation still preparing) is a reason to be busy
// beside the renderer's, and it is what says "Preparing view" rather than a phase.
test("the shell's own busy reasons join the renderer's", () => {
  const report = shellLoadReport({ load: { busy: false }, ...base, busy: true, preparing: true, hasGeometry: false });
  assert.equal(report.loading.busy, true);
  assert.equal(report.loading.progress.label, "Preparing view");
});

test("finding names the wait before the file is even located", () => {
  const report = shellLoadReport({ load: { busy: true, finding: true }, ...base, hasGeometry: false });
  assert.equal(report.loading.progress.label, "Finding file");
});

// An edit of the person's own is a wait even when nothing is downloading; it ends
// when its result is on screen, not when it is written.
test("editPending is a wait, and currentPreview ends it", () => {
  const pending = shellLoadReport({ load: { busy: false, editPending: true }, ...base, previousView: true });
  assert.equal(pending.loading.busy, true);
  assert.equal(pending.loading.updating, true);
  const shown = shellLoadReport({ load: { busy: false, editPending: true, currentPreview: true }, ...base, previousView: true });
  assert.equal(shown.loading.busy, false);
});

// The chip reads the edit, not the download: an update that is on screen but not yet
// written says so with the words of whoever offers the editing.
test("the file-status fields a renderer supplies reach the chip", () => {
  const report = shellLoadReport({
    load: { busy: false },
    fileStatus: { editingState: { state: "failed", error: "The build failed.", revision: 2, preview: { revision: 2 } },
      showingPreview: true, savedAs: "STEP file" },
    ...base
  });
  assert.equal(report.fileStatus.label, "Update failed");
  assert.match(report.fileStatus.title, /not written to the STEP file/);
});

test("a quality verdict rides the chip once the load is over", () => {
  const report = shellLoadReport({ load: { busy: false }, fileStatus: { qualityStatus: { state: "limited", title: "Fewer triangles." } }, ...base });
  assert.equal(report.fileStatus.label, "Limited detail");
  assert.equal(report.fileStatus.tone, "warning");
});

// `hasGeometry` is the shell's `hasContent` unless the renderer knows better: a scene
// that exists before it is whole is not geometry to report on yet.
test("a renderer may say its scene is not whole yet", () => {
  const whole = shellLoadReport({ load: { busy: true }, ...base });
  const partial = shellLoadReport({ load: { busy: true }, fileStatus: { hasGeometry: false }, ...base });
  assert.equal(whole.fileStatus.label, "Opening");
  assert.equal(partial.fileStatus.label, "Opening");
  const failed = { severity: "error", message: "gone" };
  assert.equal(shellLoadReport({ load: { busy: false }, ...base, alert: failed }).fileStatus.label, "Update failed");
  assert.equal(shellLoadReport({ load: { busy: false }, fileStatus: { hasGeometry: false }, ...base, alert: failed }).fileStatus.label, "Open failed");
});

// A warning is not a failed load: the model stays on screen, the loading state is
// over, and the badge carries the warning's own summary and opens it as an alert.
test("a warning rides the badge without failing the load", () => {
  const warning = { severity: "warning", blocking: false, summary: "Animation unavailable",
    title: "Animation unavailable", tooltip: "The shape is visible.", message: "long", details: "why" };
  const report = shellLoadReport({ load: { busy: false, warning }, ...base });
  assert.equal(report.loading.busy, false);
  assert.equal(report.fileStatus.label, "Animation unavailable");
  assert.equal(report.fileStatus.tone, "warning");
  assert.equal(report.fileStatusAlert, warning);
  // And it never outranks a real failure.
  const failed = { severity: "error", message: "gone" };
  assert.equal(shellLoadReport({ load: { busy: false, warning }, ...base, alert: failed }).fileStatusAlert, failed);
});

test("no file at all has no chip, whatever else is passed", () => {
  const report = shellLoadReport({ load: { busy: true, finding: true }, fileStatus: { qualityStatus: { state: "limited" } }, ...base, hasFile: false });
  assert.equal(report.fileStatus, null);
  assert.equal(report.fileStatusAlert, null);
});

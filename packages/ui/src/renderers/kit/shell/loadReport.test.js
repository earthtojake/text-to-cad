import assert from "node:assert/strict";
import { test } from "node:test";
import { shellLoadReport } from "../../../../dist/renderers/kit/shell/loadReport.js";

const base = { alert: null, busy: false, previousView: false, preparing: false };

// A renderer whose document is a plain download passes `load` and nothing else, which is
// what glb, mesh and robot do: no edit states and no preview.
test("a renderer that passes nothing gets the plain download report", () => {
  assert.deepEqual(shellLoadReport({ load: { busy: false }, ...base }), { opening: false, updating: false, busy: false,
    progress: { label: "Reading model", detail: "", counts: "", percent: null, connectionLost: null } });
});

test("busy with nothing on screen opens; busy over a complete view updates", () => {
  const opening = shellLoadReport({ load: { busy: true }, ...base });
  assert.deepEqual([opening.opening, opening.updating], [true, false]);
  const updating = shellLoadReport({ load: { busy: false, updating: true }, ...base, previousView: true });
  assert.deepEqual([updating.opening, updating.updating], [false, true]);
});

// `busy` the shell's own (a presentation still preparing) is a reason to be busy
// beside the renderer's, and it is what says "Preparing view" rather than a phase.
test("the shell's own busy reasons join the renderer's", () => {
  const report = shellLoadReport({ load: { busy: false }, ...base, busy: true, preparing: true });
  assert.equal(report.busy, true);
  assert.equal(report.progress.label, "Preparing view");
});

test("finding names the wait before the file is even located", () => {
  const report = shellLoadReport({ load: { busy: true, finding: true }, ...base });
  assert.equal(report.progress.label, "Finding file");
});

// An edit of the person's own is a wait even when nothing is downloading; it ends
// when its result is on screen, not when it is written.
test("editPending is a wait, and currentPreview ends it", () => {
  const pending = shellLoadReport({ load: { busy: false, editPending: true }, ...base, previousView: true });
  assert.equal(pending.busy, true);
  assert.equal(pending.updating, true);
  const shown = shellLoadReport({ load: { busy: false, editPending: true, currentPreview: true }, ...base, previousView: true });
  assert.equal(shown.busy, false);
});

import assert from "node:assert/strict";
import test from "node:test";
import { loadingProgress, viewerLoadingState, prolongedLoadingMessage } from "./loadingState.js";

test("opening counts real geometry work and an update preserves the prior view", () => {
  const progress = { phase: "geometry", label: "Loading geometry", done: 3, total: 8, determinate: true };
  const first = viewerLoadingState({ busy: true, progress });
  assert.equal(first.opening, true);
  assert.equal(first.progress.counts, "3/8");
  assert.equal(first.progress.percent, 38);
  const update = viewerLoadingState({ busy: true, previousView: true, progress });
  assert.equal(update.opening, false);
  assert.equal(update.updating, true);
  assert.equal(viewerLoadingState({ error: "failed", busy: true }).busy, false);
  assert.equal(viewerLoadingState({ error: { severity: "warning", blocking: false }, busy: true }).opening, true);
});

test("current preview ends update activity even while the output is still being written", () => {
  assert.equal(viewerLoadingState({ editPending: true, previousView: true }).updating, true);
  assert.equal(viewerLoadingState({ editPending: true, previousView: true, currentPreview: true }).busy, false);
  assert.equal(viewerLoadingState({}).busy, false);
});

test("technical stages have a small vocabulary and uncounted waits never claim a fraction", () => {
  for (const phase of ["compile", "generate", "package", "Source ready", "finalize", "tessellating surfaces", "saving STEP", "module"]) {
    assert.ok(["Finding file", "Reading model", "Loading geometry", "Preparing view"].includes(loadingProgress({ phase }).label));
    assert.equal(loadingProgress({ phase }).percent, null);
  }
  assert.equal(loadingProgress({ phase: "geometry", total: 8, done: 8, determinate: true }, { preparing: true }).counts, "");
});

test("a loader names its STAGE in `phase`; its own label never has to be recognized", () => {
  // A description, then its meshes counted, then the scene built from them.
  assert.deepEqual(loadingProgress({ phase: "read", label: "Loading description", determinate: false }), { label: "Reading model", detail: "", counts: "", percent: null, connectionLost: null });
  assert.deepEqual(loadingProgress({ phase: "meshes", label: "Loading meshes", done: 7, total: 13, determinate: true }), { label: "Loading geometry", detail: "", counts: "7/13", percent: 54, connectionLost: null });
  assert.equal(loadingProgress({ phase: "view", label: "Building anything at all", determinate: false }).label, "Preparing view");
});

test("a long wait reports elapsed time without inferring a stall", () => {
  assert.equal(prolongedLoadingMessage(9999), "");
  assert.match(prolongedLoadingMessage(65_000), /1m 5s elapsed/);
  assert.match(prolongedLoadingMessage(100, { failures: 1 }), /Waiting for a response/);
});

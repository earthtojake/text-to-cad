import assert from "node:assert/strict";
import test from "node:test";
import { loadingProgress, viewerLoadingState } from "./loadingState.js";

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

test("a build of the file is an update of the model on screen until it ends", () => {
  assert.equal(viewerLoadingState({ editPending: true, previousView: true }).updating, true);
  assert.equal(viewerLoadingState({ editPending: true, previousView: true }).opening, false);
  assert.equal(viewerLoadingState({}).busy, false);
});

test("technical stages have a small vocabulary and uncounted waits never claim a fraction", () => {
  for (const phase of ["compile", "generate", "package", "Source ready", "finalize", "tessellating surfaces", "saving STEP", "module"]) {
    assert.ok(["Finding file", "Opening model", "Reading model", "Importing model", "Building model", "Meshing parts", "Loading geometry", "Preparing view"].includes(loadingProgress({ phase }).label));
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

test("a file being imported reads as importing, and a cold open's meshing as meshing", () => {
  // The import's build, as cadgen labels its phases: reading the file, collecting its parts
  // (counted), storing them.
  assert.equal(loadingProgress({ phase: "compile" }).label, "Importing model");
  assert.equal(loadingProgress({ phase: "generate", label: "Importing STEP", detail: "Reading moonwatch.step (120.3 MB)" }).label, "Importing model");
  assert.deepEqual(
    loadingProgress({ phase: "package", label: "Importing STEP: collecting parts", done: 120, total: 256, determinate: true }),
    { label: "Importing model", detail: "", counts: "120/256", percent: 47, connectionLost: null });
  // A model script's own build is not an import, nor a read: every phase of it is building,
  // the parts it stores included.
  for (const [phase, label] of [["generate", "Building geometry"], ["package", "Collecting parts"], ["components", "Storing parts"], ["finalize", "Writing outputs"]]) {
    assert.equal(loadingProgress({ phase, label }).label, "Building model");
  }
  // "Reading model" is a read; a wait with nothing to say is opening.
  assert.equal(loadingProgress(null).label, "Opening model");
  assert.equal(loadingProgress({ phase: "waiting", label: "Waiting for build status" }).label, "Opening model");
  // cadgen meshing what its store lacked, against reading meshes it already had.
  assert.deepEqual(loadingProgress({ phase: "meshing", label: "Meshing parts", done: 37, total: 256, determinate: true }),
    { label: "Meshing parts", detail: "", counts: "37/256", percent: 14, connectionLost: null });
  assert.equal(loadingProgress({ phase: "geometry", label: "Loading geometry", done: 37, total: 256, determinate: true }).label, "Loading geometry");
});

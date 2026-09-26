import assert from "node:assert/strict";
import test from "node:test";

import { meshLoadErrorForViewer, meshLoadTargetsEntry, shouldStartMeshLoad } from "./meshLoadTarget.js";

test("an in-progress mesh load owns one concrete file revision", () => {
  const base = {
    inProgress: true,
    targetFile: "hand.step",
    targetHash: "tree-a",
    entryFile: "hand.step",
    entryHash: "tree-a",
  };
  assert.equal(meshLoadTargetsEntry(base), true);
  assert.equal(meshLoadTargetsEntry({ ...base, entryHash: "tree-b" }), false,
    "a new revision supersedes the old load immediately instead of waiting for a 56→8 reset");
  assert.equal(meshLoadTargetsEntry({ ...base, entryFile: "other.step" }), false);
  assert.equal(meshLoadTargetsEntry({ ...base, targetHash: "" }), false);
});

test("a failed hydration is terminal only for the selected concrete mesh hash", () => {
  const target = {
    inProgress: false,
    targetFile: "",
    targetHash: "",
    entryFile: "hand.step",
    entryHash: "tree-a",
    isAssembly: true,
    interactionReady: false,
  };
  assert.equal(shouldStartMeshLoad({
    ...target,
    selectedMeshMatches: true,
    hydrationFailed: true,
  }), false, "the same failed revision does not automatically restart");
  assert.equal(shouldStartMeshLoad({
    ...target,
    selectedMeshMatches: false,
    hydrationFailed: false,
    failedTargetFile: "hand.step",
    failedTargetHash: "tree-a",
  }), false, "a retained predecessor does not retry the exact failed target");
  assert.equal(shouldStartMeshLoad({
    ...target,
    entryHash: "tree-b",
    selectedMeshMatches: false,
    hydrationFailed: false,
    failedTargetFile: "hand.step",
    failedTargetHash: "tree-a",
  }), true, "a different selected hash starts a new revision");
  assert.equal(shouldStartMeshLoad({
    ...target,
    entryFile: "other.step",
    selectedMeshMatches: false,
    hydrationFailed: false,
    failedTargetFile: "hand.step",
    failedTargetHash: "tree-a",
  }), true, "the same opaque hash in another file is a different target");
  assert.equal(shouldStartMeshLoad({
    ...target,
    selectedMeshMatches: true,
    hydrationFailed: false,
  }), true, "a healthy partial package keeps hydrating");
});

test("a terminal partial hydration reports its background error instead of loading forever", () => {
  assert.equal(meshLoadErrorForViewer({ hydrationFailed: false, backgroundError: "limit" }), "");
  assert.equal(meshLoadErrorForViewer({ hydrationFailed: true, backgroundError: "memory limit" }), "memory limit");
  assert.match(meshLoadErrorForViewer({ hydrationFailed: true }), /stopped before every component/);
  assert.equal(meshLoadErrorForViewer({
    fatalError: "network failed",
    hydrationFailed: true,
    backgroundError: "memory limit",
  }), "network failed");
});

test("a load that failed with nothing on screen is not restarted until the revision changes", () => {
  const failed = { file: "/p/STEP/deck.step", hash: "rev-1" };
  const idle = { inProgress: false, entryFile: "/p/STEP/deck.step", selectedMeshMatches: false };
  // The failure ended "in progress"; the same file and revision must not load again by itself.
  assert.equal(shouldStartMeshLoad({ ...idle, entryHash: "rev-1", fatalFailure: failed }), false);
  // A new revision of the file, or another file, loads.
  assert.equal(shouldStartMeshLoad({ ...idle, entryHash: "rev-2", fatalFailure: failed }), true);
  assert.equal(shouldStartMeshLoad({ ...idle, entryFile: "/p/STEP/other.step", entryHash: "rev-1", fatalFailure: failed }), true);
  // With no failure recorded (as after Reload remounts the viewer), it loads.
  assert.equal(shouldStartMeshLoad({ ...idle, entryHash: "rev-1" }), true);
});

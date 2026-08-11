import assert from "node:assert/strict";
import test from "node:test";

import {
  ARTIFACT_ACTION_ATTACH,
  ARTIFACT_ACTION_BUILD,
  ARTIFACT_ACTION_ERROR,
  ARTIFACT_ACTION_READY,
  artifactActionFor,
  reconcileArtifactRun
} from "./artifactResolution.js";

test("a ready artifact needs no work", () => {
  assert.equal(artifactActionFor({ state: "ready" }), ARTIFACT_ACTION_READY);
});

test("an absent state is treated as ready, so a fresh model never flashes", () => {
  assert.equal(artifactActionFor(undefined), ARTIFACT_ACTION_READY);
  assert.equal(artifactActionFor({}), ARTIFACT_ACTION_READY);
});

test("an errored artifact surfaces the error", () => {
  assert.equal(artifactActionFor({ state: "error" }), ARTIFACT_ACTION_ERROR);
});

test("needs-build is the ONLY state that starts a build", () => {
  assert.equal(artifactActionFor({ state: "needs-build" }), ARTIFACT_ACTION_BUILD);
});

test("a build already running is attached to, never duplicated", () => {
  // The regression this pins: the client used to POST for every non-ready state, so
  // opening a model during a long `cad gen` waited out that build and then ran a second
  // full one.
  assert.equal(
    artifactActionFor({ state: "generating", runId: "abc" }),
    ARTIFACT_ACTION_ATTACH
  );
});

test("a blocked needs-build waits instead of POSTing into a held lock", () => {
  assert.equal(
    artifactActionFor({ state: "needs-build", blocked: true }),
    ARTIFACT_ACTION_ATTACH
  );
});

test("progress from the same run is kept", () => {
  const progress = { phase: "components", ratio: 0.4 };
  const result = reconcileArtifactRun("run-1", { runId: "run-1" }, progress);
  assert.equal(result.handedOff, false);
  assert.equal(result.progress, progress);
  assert.equal(result.runId, "run-1");
});

test("a new runId drops the previous run's position so the bar cannot go backwards", () => {
  const result = reconcileArtifactRun("run-1", { runId: "run-2" }, { ratio: 0.05 });
  assert.equal(result.handedOff, true);
  assert.equal(result.progress, null);
  assert.equal(result.runId, "run-2");
});

test("the first observed run is not a handoff", () => {
  const progress = { ratio: 0.77 };
  const result = reconcileArtifactRun(null, { runId: "run-1" }, progress);
  assert.equal(result.handedOff, false);
  assert.equal(result.progress, progress);
  assert.equal(result.runId, "run-1");
});

test("a server that reports no runId leaves the shown run alone", () => {
  // Rollout skew: an older producer writes no run id. Progress still shows; it just
  // cannot be attributed, so it must not read as a handoff either.
  const result = reconcileArtifactRun("run-1", {}, { ratio: 0.5 });
  assert.equal(result.handedOff, false);
  assert.equal(result.runId, "run-1");
});

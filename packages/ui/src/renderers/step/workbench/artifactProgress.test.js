import assert from "node:assert/strict";
import test from "node:test";

import {
  artifactProgressConnectionLost,
  artifactStatusFailure,
  normalizeArtifactProgress,
  refreshArtifactProgress
} from "./artifactProgress.js";

function countingPayload(overrides = {}) {
  return {
    phase: "components",
    label: "Meshing components",
    detail: "a1b2c3",
    index: 3,
    count: 4,
    done: 31,
    total: 50,
    determinate: true,
    updatedAt: 5_000,
    ...overrides
  };
}

test("normalizeArtifactProgress keeps a well-formed payload", () => {
  const progress = normalizeArtifactProgress(countingPayload());
  assert.equal(progress.phase, "components");
  assert.equal(progress.label, "Meshing components");
  assert.equal(progress.done, 31);
  assert.equal(progress.total, 50);
  assert.equal(progress.index, 3);
  assert.equal(progress.count, 4);
  assert.equal(progress.determinate, true);
});

test("normalizeArtifactProgress returns null for anything unrenderable", () => {
  for (const raw of [null, undefined, "compiling", 42, {}, { phase: "" }, { phase: "   " }]) {
    assert.equal(normalizeArtifactProgress(raw), null);
  }
});

test("normalizeArtifactProgress does not trust determinate without a total", () => {
  // The build never emits this, but the payload is a file another process wrote —
  // trusting the flag over the count would render "31/null".
  const progress = normalizeArtifactProgress(countingPayload({ total: null }));
  assert.equal(progress.determinate, false);
});

test("normalizeArtifactProgress degrades non-numeric fields instead of producing NaN", () => {
  const progress = normalizeArtifactProgress(
    countingPayload({ done: undefined, index: "hello", updatedAt: null })
  );
  assert.equal(progress.done, 0);
  assert.equal(progress.index, 0);
  assert.equal(progress.updatedAt, 0);
});

test("status reads stamp freshness and a later miss retains useful work with connection context", () => {
  const refreshed = refreshArtifactProgress(normalizeArtifactProgress(countingPayload()), 6_000);
  const missed = artifactProgressConnectionLost(
    refreshed,
    { kind: "timeout", detail: "The server did not respond within 10 seconds." },
    1,
    7_000
  );
  assert.equal(missed.label, "Meshing components");
  assert.equal(missed.detail, "a1b2c3");
  assert.equal(missed.updatedAt, 5_000);
  assert.equal(missed.refreshedAt, 6_000);
  assert.deepEqual(missed.connectionLost, {
    failures: 1, since: 7_000, detail: "The server did not respond within 10 seconds."
  });
  assert.equal(refreshArtifactProgress(missed, 8_000).connectionLost, null);
});

test("a first missed status read is still renderable and repeated misses become a status failure", () => {
  const waiting = artifactProgressConnectionLost(null, { detail: "Failed to fetch" }, 1, 9_000);
  assert.equal(waiting.phase, "waiting");
  assert.equal(waiting.label, "Waiting for build status");
  assert.equal(waiting.determinate, false);
  assert.equal(waiting.connectionLost.since, 9_000);
  const failure = artifactStatusFailure({
    failure: { kind: "network", operation: "checking display assets", detail: "Failed to fetch" }
  }, 3);
  assert.equal(failure.kind, "status");
  assert.equal(failure.attempts, 3);
  assert.equal(failure.operation, "checking display assets");
  assert.match(failure.detail, /3 attempts.*Failed to fetch/);
});

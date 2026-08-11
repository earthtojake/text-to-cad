import assert from "node:assert/strict";
import test from "node:test";

import {
  estimatedLoadingRatio,
  artifactProgressRatio,
  formatArtifactProgress,
  MAX_DISPLAY_PERCENT,
  continuedLoadingRatio,
  normalizeArtifactProgress
} from "./artifactProgress.js";

function componentsPayload(overrides = {}) {
  return {
    phase: "components",
    label: "Meshing components",
    detail: "a1b2c3",
    done: 31,
    total: 50,
    determinate: true,
    ratio: 0.62,
    ratioFloor: 0.46,
    ratioCeiling: 0.96,
    phaseStartedAt: 1_000,
    phaseExpectedMs: 8_000,
    updatedAt: 5_000,
    ...overrides
  };
}

function indeterminatePayload(overrides = {}) {
  return componentsPayload({
    phase: "generate",
    label: "Building geometry",
    determinate: false,
    total: null,
    done: 0,
    ratio: 0,
    ratioFloor: 0,
    ratioCeiling: 0.4,
    phaseStartedAt: 1_000,
    phaseExpectedMs: 10_000,
    ...overrides
  });
}

test("normalizeArtifactProgress keeps a well-formed payload", () => {
  const progress = normalizeArtifactProgress(componentsPayload());
  assert.equal(progress.phase, "components");
  assert.equal(progress.label, "Meshing components");
  assert.equal(progress.done, 31);
  assert.equal(progress.total, 50);
  assert.equal(progress.determinate, true);
});

test("normalizeArtifactProgress returns null for anything unrenderable", () => {
  for (const raw of [null, undefined, "generating", 42, {}, { phase: "" }, { phase: "   " }]) {
    assert.equal(normalizeArtifactProgress(raw), null);
  }
});

test("normalizeArtifactProgress does not trust determinate without a total", () => {
  // The build never emits this, but the payload is a file another process wrote —
  // trusting the flag over the count would render "31/null".
  const progress = normalizeArtifactProgress(componentsPayload({ total: null }));
  assert.equal(progress.determinate, false);
});

test("normalizeArtifactProgress degrades non-numeric fields instead of producing NaN", () => {
  const progress = normalizeArtifactProgress(
    componentsPayload({ ratio: "hello", done: undefined, phaseStartedAt: null })
  );
  assert.equal(progress.ratio, 0);
  assert.equal(progress.done, 0);
  assert.equal(progress.phaseStartedAt, 0);
});

test("a determinate phase is reported exactly, never smoothed", () => {
  const progress = normalizeArtifactProgress(componentsPayload());
  // Same answer however much wall-clock time passes: the count is measured, and
  // inventing motion between two real counts would misreport the one measured stage.
  assert.equal(artifactProgressRatio(progress, 1_000), 0.62);
  assert.equal(artifactProgressRatio(progress, 900_000), 0.62);
});

test("an indeterminate phase advances through its band on the clock", () => {
  const progress = normalizeArtifactProgress(indeterminatePayload());
  assert.equal(artifactProgressRatio(progress, 1_000), 0);
  assert.ok(Math.abs(artifactProgressRatio(progress, 6_000) - 0.2) < 1e-9);
  // Capped at the band ceiling: overrunning the estimate must not spill into the next
  // phase's share of the bar.
  assert.ok(Math.abs(artifactProgressRatio(progress, 999_000) - 0.4) < 1e-9);
});

test("an indeterminate phase with no recorded expectation sits where the build reported", () => {
  const progress = normalizeArtifactProgress(
    indeterminatePayload({ ratio: 0.1, phaseExpectedMs: 0 })
  );
  assert.equal(artifactProgressRatio(progress, 500_000), 0.1);
});

test("interpolation never drops below the position the build reported", () => {
  const progress = normalizeArtifactProgress(indeterminatePayload({ ratio: 0.35 }));
  assert.equal(artifactProgressRatio(progress, 1_100), 0.35);
});

test("formatArtifactProgress surfaces the real counts for a determinate phase", () => {
  const frame = formatArtifactProgress(normalizeArtifactProgress(componentsPayload()));
  assert.equal(frame.percent, 62);
  assert.equal(frame.counts, "31/50");
  assert.equal(frame.label, "Meshing components");
});

test("formatArtifactProgress omits counts when the phase has none", () => {
  const frame = formatArtifactProgress(normalizeArtifactProgress(indeterminatePayload()));
  assert.equal(frame.counts, "");
});

test("formatArtifactProgress never reads 100%", () => {
  // The artifact is not ready until the build's own request resolves; a full bar
  // beside a still-spinning viewer reads as a hang.
  const frame = formatArtifactProgress(
    normalizeArtifactProgress(componentsPayload({ done: 50, ratio: 1 }))
  );
  assert.equal(frame.percent, 99);
});

test("formatArtifactProgress maps null progress to null, not a zeroed bar", () => {
  assert.equal(formatArtifactProgress(null), null);
});

test("estimatedLoadingRatio moves without a denominator and never reaches 100%", () => {
  const t0 = 1_000_000;
  assert.equal(estimatedLoadingRatio(t0, t0), 0);
  const early = estimatedLoadingRatio(t0, t0 + 1000);
  const later = estimatedLoadingRatio(t0, t0 + 5000);
  assert.ok(early > 0 && early < later, "the estimate must advance with elapsed time");
  // An estimate that hits 100% would sit full while work continued, which reads as a hang.
  assert.ok(estimatedLoadingRatio(t0, t0 + 10 * 60 * 1000) < 1);
});

test("estimatedLoadingRatio is 0 before a load has started", () => {
  assert.equal(estimatedLoadingRatio(0), 0);
  assert.equal(estimatedLoadingRatio(Number.NaN), 0);
});

// The "stuck at 92%" regression. An implicit build reports real phases for ~38s (its bar
// climbing past 0.94 during `polygonize`) and then stops reporting the moment it finishes,
// while the package GLB is still being fetched and decoded. The old code fell back to
// estimatedLoadingRatio there, whose clock started when the LOAD started -- so it returned
// a fully-saturated 0.92: BELOW where the measurement had already reached, and frozen.
test("continuedLoadingRatio resumes above the measured floor instead of snapping back", () => {
  const measuredFloor = 0.945;
  const handover = 1_000_000;
  // The old behaviour, for contrast: a from-scratch estimate 38s into the load is pinned at
  // its ceiling and is LOWER than what the build already measured.
  const staleEstimate = estimatedLoadingRatio(handover - 38_000, handover);
  assert.ok(staleEstimate < measuredFloor, "precondition: the stale estimate is a step backwards");

  assert.equal(continuedLoadingRatio(measuredFloor, handover, handover), measuredFloor);
  const tail = continuedLoadingRatio(measuredFloor, handover, handover + 4000);
  assert.ok(tail > measuredFloor, "the tail must keep moving after the build stops reporting");
  assert.ok(tail < 1, "the tail must never reach 100%");
});

test("continuedLoadingRatio stays under the display cap however long the tail runs", () => {
  const ceiling = MAX_DISPLAY_PERCENT / 100;
  const forever = continuedLoadingRatio(0.5, 1_000_000, 1_000_000 + 60 * 60 * 1000);
  assert.ok(forever <= ceiling, `tail ${forever} must not exceed ${ceiling}`);
});

test("continuedLoadingRatio never walks a floor backwards", () => {
  // A floor already at/above the ceiling must hold, not be dragged down to it.
  assert.equal(continuedLoadingRatio(1, 1_000_000, 1_000_000 + 10_000), 1);
  assert.equal(continuedLoadingRatio(0.6, 0, 1_000_000), 0.6);
});

import assert from "node:assert/strict";
import test from "node:test";

import { formatArtifactProgress, normalizeArtifactProgress } from "./artifactProgress.js";

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

function labelOnlyPayload(overrides = {}) {
  return countingPayload({
    phase: "generate",
    label: "Building geometry",
    detail: "airframe",
    index: 1,
    determinate: false,
    total: null,
    done: 0,
    ...overrides
  });
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
  for (const raw of [null, undefined, "generating", 42, {}, { phase: "" }, { phase: "   " }]) {
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

test("a phase that can count reports its real fraction and count", () => {
  const frame = formatArtifactProgress(normalizeArtifactProgress(countingPayload()));
  assert.equal(frame.determinate, true);
  assert.equal(frame.percent, 62);
  assert.equal(frame.counts, "31/50");
  assert.equal(frame.label, "Meshing components");
});

test("a phase that cannot count reports no number at all", () => {
  // The whole point of the rewrite: an uncountable phase used to be given a percentage
  // derived from a guessed phase weighting, which on a first build was simply 0 for the
  // entire phase. `percent: null` is the caller's signal to render an indeterminate bar.
  const frame = formatArtifactProgress(normalizeArtifactProgress(labelOnlyPayload()));
  assert.equal(frame.determinate, false);
  assert.equal(frame.percent, null);
  assert.equal(frame.counts, "");
  assert.equal(frame.detail, "airframe", "it says what it is working on instead");
});

test("a frame carries the phase's position in the run", () => {
  assert.equal(formatArtifactProgress(normalizeArtifactProgress(countingPayload())).ordinal, "3/4");
});

test("a phase the kind did not declare has no ordinal rather than a bogus one", () => {
  const frame = formatArtifactProgress(normalizeArtifactProgress(countingPayload({ index: 0 })));
  assert.equal(frame.ordinal, "");
});

test("formatArtifactProgress is pure — the same frame renders the same whenever it is read", () => {
  // There are no clocks in this module. A frame is a statement about the present that the
  // build made; re-reading it later must not invent motion the build did not report.
  const progress = normalizeArtifactProgress(countingPayload());
  assert.deepEqual(formatArtifactProgress(progress), formatArtifactProgress(progress));
});

test("a completed phase is allowed to read 100%", () => {
  // The old cap existed because the number described the WHOLE build, where a full bar
  // beside a still-spinning viewer read as a hang. Per phase, finishing is just finishing —
  // the next phase's frame replaces this one immediately.
  const frame = formatArtifactProgress(normalizeArtifactProgress(countingPayload({ done: 50 })));
  assert.equal(frame.percent, 100);
});

test("formatArtifactProgress maps null progress to null, not a zeroed bar", () => {
  assert.equal(formatArtifactProgress(null), null);
});

// A robot has no artifact build behind it — it is a URDF plus a pile of meshes — so its
// loader's own count is the only progress in existence. It goes through the SAME two
// functions as a build's, which is what lets the overlay stay ignorant of which subsystem
// produced the frame. Before this the count was formatted into a string at the source and
// only ever reached the filename chip.
test("a robot mesh load formats through the same path as a build", () => {
  const frame = formatArtifactProgress(
    normalizeArtifactProgress({
      phase: "meshes",
      label: "Loading meshes",
      done: 7,
      total: 13,
      determinate: true
    })
  );
  assert.equal(frame.label, "Loading meshes");
  assert.equal(frame.counts, "7/13");
  assert.equal(frame.percent, 54);
  assert.equal(frame.ordinal, "", "a robot load has no phase sequence to place itself in");
});

test("a robot stage with no count still renders as a labelled indeterminate frame", () => {
  const frame = formatArtifactProgress(
    normalizeArtifactProgress({ phase: "robot", label: "Building robot", determinate: false })
  );
  assert.equal(frame.label, "Building robot");
  assert.equal(frame.percent, null);
  assert.equal(frame.counts, "");
});

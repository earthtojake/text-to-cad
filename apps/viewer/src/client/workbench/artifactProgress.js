// Reading the build-progress payload the artifact-status route attaches while a model is
// generating (written by cadgen's coordination/record.py, served by cadgen.viewer's artifact.py).
//
// Each phase reports ITSELF. There is no overall percentage, because a build's phases have
// no fixed relationship to each other: measured across this repo's models, `generate` is 11%
// of one build and 84% of another. A single bar spanning all four therefore had to be
// weighted by a guess, and on a first build — where nothing about the model has been
// measured — the guess had no inputs, so the bar sat at exactly 0% for ten minutes and then
// jumped to 46% when the phase ended.
//
// So a frame says which phase is running, where it sits in the run ("1/4"), and then ONE of:
//
//   * a real fraction — `done`/`total` — rendered as a bar with its count;
//   * a `detail` label naming the sub-unit in flight, rendered as an indeterminate bar.
//
// Both are true statements about the present. Nothing here extrapolates, and there are no
// clocks: this module is a pure formatter, so a frame renders the same whenever it is read.

export const ARTIFACT_PROGRESS_POLL_MS = 400;
// The first poll runs sooner than the rest. The overlay grows the moment progress first
// arrives, and that is the one layout shift the stacked design cannot avoid — so it should
// happen while the loading state is still appearing, not a noticeable beat later. The build
// reports its opening phase immediately, so there is something to read this early.
export const ARTIFACT_PROGRESS_FIRST_POLL_MS = 120;

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function nonNegativeInt(value) {
  return Math.max(0, Math.round(finiteNumber(value, 0)));
}

// Normalizes the server payload into the shape the UI reads, or null when there is nothing
// renderable. Defensive by intent: this is a file on disk written by another process, so a
// partial or unexpected payload must degrade to "no progress", never to a broken overlay.
export function normalizeArtifactProgress(raw) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const phase = String(raw.phase || "").trim();
  if (!phase) {
    return null;
  }
  const total = raw.total === null || raw.total === undefined ? null : finiteNumber(raw.total, 0);
  return {
    phase,
    label: String(raw.label || "").trim(),
    detail: String(raw.detail || "").trim(),
    index: nonNegativeInt(raw.index),
    count: nonNegativeInt(raw.count),
    done: nonNegativeInt(raw.done),
    total: total === null ? null : Math.max(0, Math.round(total)),
    // Never trust the flag over the count: a payload claiming `determinate` without a total
    // would render "31/null".
    determinate: Boolean(raw.determinate) && Number(total) > 0,
    updatedAt: finiteNumber(raw.updatedAt, 0)
  };
}

/**
 * The display model for one frame.
 *
 * `percent` is null for a phase with no denominator — the caller renders an indeterminate
 * bar rather than a number. It is deliberately NOT capped below 100: a phase that has
 * finished its own work has honestly finished it, and the next phase's frame replaces this
 * one immediately. The old cap existed because the number claimed to describe the whole
 * build, where 100% beside a still-spinning viewer read as a hang.
 */
export function formatArtifactProgress(progress) {
  if (!progress) {
    return null;
  }
  const determinate = progress.determinate && progress.total > 0;
  return {
    label: progress.label,
    ordinal: progress.index > 0 && progress.count > 0 ? `${progress.index}/${progress.count}` : "",
    detail: progress.detail,
    determinate,
    percent: determinate ? Math.round((progress.done / progress.total) * 100) : null,
    counts: determinate ? `${progress.done}/${progress.total}` : ""
  };
}

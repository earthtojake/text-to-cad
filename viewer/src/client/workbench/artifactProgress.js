// Reading the build-progress payload the artifact-status route attaches while a model
// is generating (written by cadgen's _internal/progress.py, served by
// server_py/artifact.py's read_generation_progress).
//
// The build reports at WORK BOUNDARIES, never on a timer: OCP meshing holds Python's
// GIL inside C for long stretches, so a heartbeat thread in the build process would
// starve during exactly the work it was meant to report. Interpolation is therefore the
// READER's job, and it splits cleanly in two:
//
// * a determinate phase (meshing components) is shown exactly as reported -- a real
//   done/total, never smoothed, because inventing motion between two measured counts
//   would misreport the one stage we actually measure;
// * an indeterminate phase (a generator running, a STEP parsing) is advanced against
//   the wall clock inside its band, using the duration this model's PREVIOUS build
//   recorded for that phase. Absent that, it simply sits at the band's floor.
//
// Progress never reaches 100% here. The artifact is not ready until the build's own
// request resolves, and a bar that sits full while the viewer still shows a spinner
// reads as a hang.

export const ARTIFACT_PROGRESS_POLL_MS = 400;
// The first poll runs sooner than the rest. The overlay grows by two rows the moment
// progress first arrives, and that is the one layout shift the stacked design cannot
// avoid — so it should happen while the loading state is still appearing, not a
// noticeable beat later. The build reports its opening phase immediately, so there is
// something to read this early.
export const ARTIFACT_PROGRESS_FIRST_POLL_MS = 120;
// Progress never displays 100%: the artifact is not ready until the build's own request
// resolves, and a bar that sits full while the viewer still shows a spinner reads as a hang.
export const MAX_DISPLAY_PERCENT = 99;

function clamp01(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.min(1, Math.max(0, numeric));
}

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

// Normalizes the server payload into the shape the UI reads, or null when there is
// nothing renderable. Defensive by intent: this is a file on disk written by another
// process, so a partial or unexpected payload must degrade to "no progress", never to a
// broken overlay.
export function normalizeArtifactProgress(raw) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const phase = String(raw.phase || "").trim();
  if (!phase) {
    return null;
  }
  const total = raw.total === null || raw.total === undefined ? null : finiteNumber(raw.total, 0);
  const determinate = Boolean(raw.determinate) && Number(total) > 0;
  return {
    phase,
    label: String(raw.label || "").trim(),
    detail: String(raw.detail || "").trim(),
    done: Math.max(0, Math.round(finiteNumber(raw.done, 0))),
    total: total === null ? null : Math.max(0, Math.round(total)),
    determinate,
    ratio: clamp01(raw.ratio),
    ratioFloor: clamp01(raw.ratioFloor),
    ratioCeiling: clamp01(raw.ratioCeiling),
    phaseStartedAt: finiteNumber(raw.phaseStartedAt, 0),
    phaseExpectedMs: finiteNumber(raw.phaseExpectedMs, 0),
    updatedAt: finiteNumber(raw.updatedAt, 0)
  };
}

export function artifactProgressRatio(progress, nowMs = Date.now()) {
  if (!progress) {
    return 0;
  }
  if (progress.determinate) {
    return clamp01(progress.ratio);
  }
  if (!progress.phaseExpectedMs || !progress.phaseStartedAt) {
    return clamp01(progress.ratio);
  }
  const elapsed = Math.max(0, nowMs - progress.phaseStartedAt);
  const within = Math.min(1, elapsed / progress.phaseExpectedMs);
  const interpolated = progress.ratioFloor + (progress.ratioCeiling - progress.ratioFloor) * within;
  // Never below what the build itself reported: the recorded expectation can be wrong,
  // but a measured position is not.
  return clamp01(Math.max(progress.ratio, interpolated));
}

// The display model for one frame: a ratio, a capped percent, the phase label, and the
// real counts when (and only when) the phase has them.
export function formatArtifactProgress(progress, nowMs = Date.now()) {
  if (!progress) {
    return null;
  }
  const ratio = artifactProgressRatio(progress, nowMs);
  return {
    ratio,
    percent: Math.min(MAX_DISPLAY_PERCENT, Math.round(ratio * 100)),
    label: progress.label,
    counts: progress.determinate && progress.total ? `${progress.done}/${progress.total}` : "",
    determinate: progress.determinate
  };
}

// How long a load with no reported progress is assumed to take. Not a promise -- it only
// sets how fast the estimate creeps.
const ESTIMATED_LOAD_MS = 6000;
// An estimate must never reach 100%: the bar would sit full while work continued, which
// reads as a hang. It approaches this ceiling and stops.
const ESTIMATED_CEILING = 0.92;
// The ceiling for the TAIL of a load whose measured phase already finished. Higher than
// ESTIMATED_CEILING because we know strictly more here: the build is done and only the
// download/decode is left, so promising most of the bar is honest rather than optimistic.
const CONTINUED_CEILING = MAX_DISPLAY_PERCENT / 100;

// Eases from `floor` toward `ceiling` on an exponential curve. Deliberately NOT linear: a
// linear estimate that outruns the real work has to jump backwards or freeze, and both
// look broken. This moves quickly at first (when most short loads finish) and slows rather
// than stalling at a hard stop.
function easedEstimate(floor, ceiling, sinceMs, nowMs) {
  const low = clamp01(floor);
  const high = Math.max(low, clamp01(ceiling));
  if (!Number.isFinite(sinceMs) || sinceMs <= 0) {
    return low;
  }
  const elapsed = Math.max(0, nowMs - sinceMs);
  return clamp01(low + (high - low) * (1 - Math.exp(-elapsed / ESTIMATED_LOAD_MS)));
}

/**
 * A time-based ratio for a load that has reported no progress at all.
 *
 * Most loads have no denominator -- reading a GLB off disk, decoding it in a worker -- and
 * the alternative to estimating is a bar that sits at zero, which tells the user less than
 * nothing.
 */
export function estimatedLoadingRatio(startedAtMs, nowMs = Date.now()) {
  return easedEstimate(0, ESTIMATED_CEILING, startedAtMs, nowMs);
}

/**
 * The estimate for the TAIL of a load whose measured phase has ended.
 *
 * An artifact build reports real progress and then stops reporting the moment it finishes
 * -- but the load is not over: the package GLB still has to be fetched and decoded, and for
 * a large implicit mesh that is the longer half. Falling back to `estimatedLoadingRatio`
 * there is wrong twice over: its clock started when the LOAD started, so after a 38s build
 * the curve has fully saturated and the bar freezes at ESTIMATED_CEILING; and because the
 * measured ratio had already climbed past that ceiling, the bar first jumps BACKWARDS.
 * That pair is exactly what reads as "stuck at 92%".
 *
 * So the tail eases from where the measurement actually left off, on a clock that starts at
 * the handover.
 */
export function continuedLoadingRatio(floorRatio, sinceMs, nowMs = Date.now()) {
  return easedEstimate(floorRatio, CONTINUED_CEILING, sinceMs, nowMs);
}

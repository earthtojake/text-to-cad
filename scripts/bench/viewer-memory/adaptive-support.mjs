import { isCompletePublication } from './completion.mjs';

export function preservesCompleteAdaptiveView(probe, { occurrences }, modelKey) {
  return !!modelKey && probe.modelKey === modelKey
    && probe.renderMemoryProbe?.occurrences === occurrences
    && probe.sceneSync?.records === occurrences;
}

// A completed draw is distinct from policy convergence. Denied refinement can
// leave a stable, complete view; report that outcome without calling it full detail.
export function adaptiveStatus(probe, { components, occurrences }) {
  const complete = isCompletePublication(probe)
    && probe.meshCost.totalComponents === components
    && probe.meshCost.occurrenceCount === occurrences;
  const drawn = complete && probe.draw?.lastAt >= probe.meshCost.at;
  const lod = probe.viewportLod;
  const counts = Object.values(lod?.levelCounts || {}).reduce((sum, value) => sum + value, 0);
  const schedulerIdle = lod?.componentCount === components && counts === components
    && lod.minimumLevel === 0 && !lod.busy && !lod.pendingEvaluation;
  const resourcesIdle = probe.memoryPolicy?.reservationCount === 0
    && probe.cacheWrites?.active === 0 && probe.workers?.live === 0;
  const unmetTargets = Array.isArray(lod?.unmetTargets) ? lod.unmetTargets : [];
  const qualitySettled = lod?.qualitySettled === true && unmetTargets.length === 0;
  const limited = !!probe.memoryPolicy?.lastLimitation
    || unmetTargets.some(({ reason }) => reason === 'memory-denied' || reason === 'memory-pressure');
  const failed = Number(lod?.failedLevels) || 0;
  const detailOutcome = limited ? 'budget-limited' : failed ? 'failed-levels'
    : qualitySettled ? 'policy-satisfied' : 'unmet-targets';
  return {
    complete, drawn, schedulerIdle, resourcesIdle, qualitySettled, unmetTargets,
    stableCandidate: drawn && schedulerIdle && resourcesIdle && detailOutcome !== 'unmet-targets',
    detailOutcome,
    limitation: probe.memoryPolicy?.lastLimitation || null,
    failedLevels: failed,
  };
}

export function createAdaptiveStabilityWindow(stableMs = 2000) {
  let key = null, since = null;
  return (probe, expected, now) => {
    const status = adaptiveStatus(probe, expected);
    // Camera changes and any new publication reset the interval even when the
    // scheduler happens to look idle between two operations.
    const nextKey = JSON.stringify([
      probe.modelKey, probe.meshCost?.at, probe.events?.lodCount,
      probe.events?.cameraCount, probe.cameraZoomPercent, probe.viewportLod?.levelCounts,
      status.detailOutcome, status.failedLevels, status.qualitySettled, status.unmetTargets,
    ]);
    if (!status.stableCandidate) { key = null; since = null; }
    else if (key !== nextKey) { key = nextKey; since = now; }
    return { ...status, stableForMs: since === null ? 0 : now - since,
      stable: since !== null && now - since >= stableMs };
  };
}

// A phase timeout is evidence, even when recovery is still worth exercising.
// Hard deadline/RSS/browser failures must be checked by the caller first.
export function finishAdaptiveSettlePhase(phase, { sample, status, finishedAt, allowRecovery = false }) {
  Object.assign(phase, { sample, status, finishedAt, complete: status?.stable === true });
  if (phase.complete) return sample;
  phase.failure = `${phase.label}: complete adaptive view did not reach stable idle before phase deadline`;
  phase.recoveryContinued = allowRecovery;
  if (!allowRecovery) throw new Error(phase.failure);
  return sample;
}

export function adaptiveSettleAssertions(phases) {
  const settles = phases.filter(phase => phase.kind === 'settle');
  return {
    stableAllPhases: settles.length > 0 && settles.every(phase => phase.complete),
    requestedDetailSatisfied: settles.length > 0 && settles.every(phase => phase.complete && phase.status?.detailOutcome === 'policy-satisfied'),
  };
}

export function gradeAdaptiveOutcome(assertions, phases) {
  const outcomeBuckets = new Set(['requestedDetailSatisfied', 'adaptiveExercised']);
  if (assertions.completeScene !== true || Object.entries(assertions).some(([key, value]) => !outcomeBuckets.has(key) && value !== true)) return 'failed';
  if (phases.some(phase => phase.status?.detailOutcome === 'failed-levels')) return 'complete-view-with-failed-detail';
  if (assertions.requestedDetailSatisfied !== true) return 'complete-adaptive-view-with-budget-limitation';
  if (assertions.adaptiveExercised !== true) return 'complete-view-adaptive-exercise-inconclusive';
  return 'passed-default-adaptive';
}

export function summarizeIntervals(values) {
  const sorted = [...values].filter(Number.isFinite).sort((a, b) => a - b);
  const at = q => sorted.length ? sorted[Math.min(sorted.length - 1, Math.ceil(q * sorted.length) - 1)] : null;
  return { samples: sorted.length, p50: at(.5), p95: at(.95), max: at(1) };
}

// Process-tree accounting takes ps text so tests do not
// need a browser and can prove that a second renderer is not summed into a cap.
export function processMemoryFromPs(output, profileDirectory) {
  const rows = output.split('\n').flatMap(line => {
    const match = line.match(/^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.*)$/);
    return match ? [{ pid: +match[1], ppid: +match[2], bytes: +match[3] * 1024, command: match[4] }] : [];
  });
  const ours = new Set(rows.filter(row => row.command.includes(profileDirectory)).map(row => row.pid));
  if (!ours.size) return null;
  for (let previous = -1; previous !== ours.size;) {
    previous = ours.size;
    for (const row of rows) if (ours.has(row.ppid)) ours.add(row.pid);
  }
  const result = {};
  for (const row of rows) {
    if (!ours.has(row.pid)) continue;
    const type = row.command.match(/--type=([a-zA-Z-]+)/)?.[1] || 'browser';
    const value = result[type] ||= { rssBytes: 0, largestPidBytes: 0, processCount: 0 };
    value.rssBytes += row.bytes;
    value.largestPidBytes = Math.max(value.largestPidBytes, row.bytes);
    value.processCount++;
  }
  return result;
}

export function mergeProcessPeak(peak, sample) {
  for (const [type, value] of Object.entries(sample || {})) {
    const current = peak[type] ||= { rssBytes: 0, largestPidBytes: 0, processCount: 0 };
    for (const key of Object.keys(current)) current[key] = Math.max(current[key], value[key]);
  }
  return peak;
}

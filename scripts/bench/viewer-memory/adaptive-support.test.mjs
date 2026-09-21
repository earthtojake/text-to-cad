import assert from 'node:assert/strict';
import { test } from 'node:test';
import { adaptiveStatus, preservesCompleteAdaptiveView, createAdaptiveStabilityWindow, finishAdaptiveSettlePhase, adaptiveSettleAssertions, gradeAdaptiveOutcome, processMemoryFromPs, mergeProcessPeak } from './adaptive-support.mjs';

const expected = { components: 2, occurrences: 4 };
function probe() {
  return { modelKey: 'tree', meshCost: { final: true, loadedComponents: 2, totalComponents: 2,
    componentCount: 2, occurrenceCount: 4, at: 10 }, renderMemoryProbe: { occurrences: 4 },
  sceneSync: { records: 4, atMs: 10 }, draw: { lastAt: 12 },
  viewportLod: { componentCount: 2, minimumLevel: 0, levelCounts: { 0: 1, 1: 1 },
    busy: false, pendingEvaluation: false, failedLevels: 0, qualitySettled: true, unmetTargets: [] },
  memoryPolicy: { reservationCount: 0, lastLimitation: null }, cacheWrites: { active: 0 },
  workers: { live: 0 }, events: { lodCount: 1, cameraCount: 0 } };
}

test('adaptive stable gate requires actual complete draw and default policy', () => {
  assert.equal(adaptiveStatus(probe(), expected).stableCandidate, true);
  for (const change of [p => p.meshCost.final = false, p => p.sceneSync.records = 3,
    p => p.draw.lastAt = 9, p => p.viewportLod.minimumLevel = 1,
    p => p.viewportLod.busy = true, p => p.viewportLod.pendingEvaluation = true,
    p => p.viewportLod.levelCounts[0] = 0, p => p.memoryPolicy.reservationCount = 1,
    p => p.cacheWrites.active = 1, p => p.workers.live = 1]) {
    const p = probe(); change(p); assert.equal(adaptiveStatus(p, expected).stableCandidate, false);
  }
});

test('stable budget-limited view remains distinct from satisfied or failed detail', () => {
  const p = probe(); p.memoryPolicy.lastLimitation = { cid: 'part', reason: 'budget' }; p.viewportLod.failedLevels = 1;
  assert.deepEqual([adaptiveStatus(p, expected).stableCandidate, adaptiveStatus(p, expected).detailOutcome], [true, 'budget-limited']);
  p.memoryPolicy.lastLimitation = null;
  assert.equal(adaptiveStatus(p, expected).detailOutcome, 'failed-levels');
});

test('idle alone cannot establish camera quality satisfaction', () => {
  for (const value of [false, undefined]) {
    const p = probe(); p.viewportLod.qualitySettled = value;
    const status = adaptiveStatus(p, expected);
    assert.equal(status.schedulerIdle, true);
    assert.equal(status.stableCandidate, false);
    assert.equal(status.detailOutcome, 'unmet-targets');
  }
  const p = probe();
  p.viewportLod.unmetTargets = [{ cid: 'part', currentLevel: 1, targetLevel: 3, reason: 'pending' }];
  assert.equal(adaptiveStatus(p, expected).qualitySettled, false);
  assert.equal(adaptiveStatus(p, expected).stableCandidate, false);
});

test('parked pressure targets remain budget-limited even without a UI limitation', () => {
  const p = probe(); p.viewportLod.qualitySettled = false;
  p.viewportLod.unmetTargets = [{ cid: 'part', currentLevel: 2, targetLevel: 3, reason: 'memory-pressure' }];
  const status = adaptiveStatus(p, expected);
  assert.equal(status.stableCandidate, true);
  assert.equal(status.detailOutcome, 'budget-limited');
  const update = createAdaptiveStabilityWindow(2000);
  update(p, expected, 0);
  assert.equal(update(p, expected, 2000).stable, true);
  p.viewportLod.unmetTargets = [{ cid: 'part', currentLevel: 1, targetLevel: 3, reason: 'memory-denied' }];
  assert.equal(update(p, expected, 2100).stable, false);
});

test('new publication pending React commit preserves the old complete view', () => {
  const p = probe(); p.meshCost.at = 15;
  assert.equal(adaptiveStatus(p, expected).complete, false);
  assert.equal(preservesCompleteAdaptiveView(p, expected, 'tree'), true);
  p.renderMemoryProbe.occurrences = 3;
  assert.equal(preservesCompleteAdaptiveView(p, expected, 'tree'), false);
  p.renderMemoryProbe.occurrences = 4; p.modelKey = 'other';
  assert.equal(preservesCompleteAdaptiveView(p, expected, 'tree'), false);
});

test('camera, publications, active work and level changes restart stable interval', () => {
  for (const change of [p => p.events.cameraCount++, p => p.events.lodCount++,
    p => p.meshCost.at++, p => p.viewportLod.levelCounts = { 0: 2 }]) {
    const p = probe(), update = createAdaptiveStabilityWindow(2000);
    assert.equal(update(p, expected, 0).stable, false);
    assert.equal(update(p, expected, 2000).stable, true);
    change(p); p.sceneSync.atMs = p.meshCost.at;
    assert.equal(update(p, expected, 2200).stable, false);
    assert.equal(update(p, expected, 4200).stable, true);
    p.viewportLod.busy = true; assert.equal(update(p, expected, 4300).stable, false);
    p.viewportLod.busy = false; assert.equal(update(p, expected, 4400).stable, false);
  }
});

test('RSS gate distinguishes largest renderer and excludes unrelated browser', () => {
  const sample = processMemoryFromPs('1 0 10 chrome --user-data-dir=/tmp/owned\n2 1 40 chrome --type=renderer\n3 1 20 chrome --type=renderer\n4 0 90 chrome --user-data-dir=/tmp/other', '/tmp/owned');
  assert.deepEqual(sample.renderer, { rssBytes: 60 * 1024, largestPidBytes: 40 * 1024, processCount: 2 });
  const peak = mergeProcessPeak({}, sample); mergeProcessPeak(peak, { renderer: { rssBytes: 20, largestPidBytes: 20, processCount: 1 } });
  assert.equal(peak.renderer.largestPidBytes, 40 * 1024);
  assert.equal(processMemoryFromPs('', '/tmp/owned'), null);
});

test('soft near timeout preserves failure while later recovery can pass', () => {
  const p = probe(), phases = [];
  const near = { kind: 'settle', label: 'near' }; phases.push(near);
  assert.equal(finishAdaptiveSettlePhase(near, { sample: p, status: { stable: false, detailOutcome: 'policy-satisfied' }, finishedAt: 'near-end', allowRecovery: true }), p);
  assert.equal(near.complete, false);
  assert.equal(near.recoveryContinued, true);
  assert.match(near.failure, /phase deadline/);
  const far = { kind: 'settle', label: 'returned' }; phases.push(far);
  finishAdaptiveSettlePhase(far, { sample: p, status: { stable: true, detailOutcome: 'policy-satisfied' }, finishedAt: 'far-end', allowRecovery: true });
  assert.equal(far.complete, true);
  assert.deepEqual(adaptiveSettleAssertions(phases), { stableAllPhases: false, requestedDetailSatisfied: false });
  assert.deepEqual(adaptiveSettleAssertions([far]), { stableAllPhases: true, requestedDetailSatisfied: true });
});

test('initial timeout still stops and stable budget limitation is not policy satisfaction', () => {
  const initial = { kind: 'settle', label: 'initial' };
  assert.throws(() => finishAdaptiveSettlePhase(initial, { sample: probe(), status: { stable: false }, finishedAt: 'end' }), /initial:.*phase deadline/);
  assert.equal(initial.recoveryContinued, false);
  const limited = { kind: 'settle', complete: true, status: { detailOutcome: 'budget-limited' } };
  assert.deepEqual(adaptiveSettleAssertions([limited]), { stableAllPhases: true, requestedDetailSatisfied: false });
  assert.deepEqual(adaptiveSettleAssertions([]), { stableAllPhases: false, requestedDetailSatisfied: false });
});

test('every required boolean, including optional resize and interaction checks, controls the final grade', () => {
  const assertions = Object.fromEntries(['completeScene', 'defaultPolicy', 'stableAllPhases', 'interactionRendered',
    'orbitCadence', 'orbitMaxGuard', 'selectionCleared', 'withinRssBound', 'noPageErrors', 'noUnexpectedHttpErrors',
    'resizedPolicyReevaluated', 'requestedDetailSatisfied', 'adaptiveExercised'].map(key => [key, true]));
  assert.equal(gradeAdaptiveOutcome(assertions, []), 'passed-default-adaptive');
  for (const key of Object.keys(assertions).filter(key => !['requestedDetailSatisfied', 'adaptiveExercised'].includes(key))) {
    assert.equal(gradeAdaptiveOutcome({ ...assertions, [key]: false }, []), 'failed', key);
  }
  assert.equal(gradeAdaptiveOutcome({}, []), 'failed');
  assert.equal(gradeAdaptiveOutcome({ ...assertions, adaptiveExercised: false }, []), 'complete-view-adaptive-exercise-inconclusive');
  assert.equal(gradeAdaptiveOutcome({ ...assertions, requestedDetailSatisfied: false }, []), 'complete-adaptive-view-with-budget-limitation');
  assert.equal(gradeAdaptiveOutcome({ ...assertions, requestedDetailSatisfied: false }, [{ status: { detailOutcome: 'failed-levels' } }]), 'complete-view-with-failed-detail');
});

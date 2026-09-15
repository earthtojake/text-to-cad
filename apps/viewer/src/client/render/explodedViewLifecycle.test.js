import assert from 'node:assert/strict';
import test from 'node:test';
import { Matrix4 } from 'three';
import { inactiveExplodedViewNeedsReset } from './explodedViewLifecycle.js';
import { clearExplodedViewRecords } from 'cadgen-js/lib/viewer/explodedView.js';

test('initial and retained rest records need no reset on another publication', () => {
  const records = [{}, { explodedViewMatrix: null }];
  assert.equal(inactiveExplodedViewNeedsReset({ progress: 0 }, records), false);
  assert.equal(inactiveExplodedViewNeedsReset({ progress: 0 }, [...records, {}]), false);
});

test('a publication interrupting collapse still clears its retained offset', () => {
  const record = { explodedViewMatrix: new Matrix4().makeTranslation(0, 0, 6) };
  // The disabling effect has already changed enabled to false, although its
  // animation has not reached rest. The next effect must keep the clear pass.
  const animation = { enabled: false, progress: 0.6 };
  assert.equal(inactiveExplodedViewNeedsReset(animation, [record]), true);
  clearExplodedViewRecords([record]);
  animation.progress = 0;
  assert.equal(record.explodedViewMatrix, null);
  assert.equal(inactiveExplodedViewNeedsReset(animation, [record]), false);
});

test('a residual record offset requires clearing even with zero progress', () => {
  const record = { explodedViewMatrix: new Matrix4() };
  assert.equal(inactiveExplodedViewNeedsReset({ progress: 0 }, [record]), true);
  clearExplodedViewRecords([record]);
  assert.equal(inactiveExplodedViewNeedsReset({ progress: 0 }, [record]), false);
});

test('an interrupted collapse still resets if its displaced records were replaced', () => {
  assert.equal(inactiveExplodedViewNeedsReset({ progress: 0.5 }, [{}]), true);
  assert.equal(inactiveExplodedViewNeedsReset({ progress: NaN }, [{}]), true);
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { setImmediate } from 'node:timers';
import { resolveViewSceneSettings } from '@hardcore/core/common/sceneSettings.js';
import { createViewUpdateCoordinator } from './viewUpdateCoordinator.js';
import { viewPreparationKey } from './viewUpdatePlan.js';

const scene = value => resolveViewSceneSettings({ display: value, lightingQuality: "preview" });
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; }
function harness(options = {}) {
  const initial = scene({ mode: 'solid' }), calls = [], statuses = [];
  const coordinator = createViewUpdateCoordinator(initial, {
    yieldPaint: async () => {},
    prepare: async target => { calls.push(['prepare', target]); },
    apply: async target => { calls.push(['apply', target]); },
    present: async () => { calls.push(['present']); },
    onStatus: status => statuses.push(status),
    ...options,
  });
  return { initial, calls, statuses, ...coordinator };
}

test('rapid mode changes prepare and present only the last target', async () => {
  const h = harness(), render = scene({ mode: 'render' }), xray = scene({ mode: 'xray' });
  h.request(render); h.request(xray);
  await h.whenReady();
  assert.deepEqual(h.calls, [['prepare', xray], ['apply', xray], ['present']]);
  assert.equal(h.statuses.at(-1).pending, false);
});

test('return to visible settings during preparation cancels work and settles captures', async () => {
  const h = harness({ prepare: (_, signal) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('cancelled')))) });
  h.request(scene({ mode: 'render' })); await tick();
  const capture = h.whenReady(); h.request(h.initial);
  await capture;
  assert.deepEqual(h.calls, []);
  assert.equal(h.statuses.at(-1).pending, false);
});

test('a superseded reconciliation is restored without presenting the stale recipe', async () => {
  const first = deferred(), applied = [], presented = [];
  const h = harness({ apply: async target => { applied.push(target); if(applied.length===1) await first.promise; }, present: async () => presented.push(applied.at(-1)) });
  const render = scene({ mode: 'render' });
  h.request(render); await tick();
  h.request(h.initial); first.resolve();
  await h.whenReady();
  assert.deepEqual(applied, [render, h.initial]);
  assert.deepEqual(presented, [h.initial]);
});

test('live edits skip preparation and capture waits for the actual presented frame', async () => {
  const frame = deferred(), h = harness({ present: () => frame.promise });
  h.request(scene({ grid: { color: '#ffffff' }, clip: { enabled: false } }));
  let ready = false; const capture = h.whenReady().then(() => { ready = true; });
  await tick(); assert.equal(ready, false);
  assert.deepEqual(h.calls.map(c => c[0]), ['apply']);
  frame.resolve(); await capture;
});

test('failures surface once, reject captures, and retry the requested values', async () => {
  let fail = true;
  const h = harness({ present: async () => { if (fail) throw new Error('GPU failure'); } });
  const render = scene({ mode: 'render' }); h.request(render);
  await assert.rejects(h.whenReady(), /GPU failure/);
  assert.equal(h.statuses.at(-1).error, 'GPU failure');
  fail = false; h.retry(); await h.whenReady();
  assert.equal(h.statuses.at(-1).error, null);
});

test('unmount aborts preparation and rejects pending captures', async () => {
  let signal;
  const h = harness({ prepare: (_, value) => { signal=value; return new Promise(()=>{}); } });
  h.request(scene({ mode: 'render' })); await tick();
  const capture = h.whenReady(); h.dispose();
  await assert.rejects(capture, /Viewer closed/); assert.equal(signal.aborted, true);
});

test('only resource boundaries prepare; clip motion, exposure, rotation and color stay live', () => {
  const render = scene({ mode: 'render', clip: { enabled: true } });
  for (const patch of [
    { lighting: { exposure: 1, rotation: 35 } }, { clip: { enabled: true, offset: 0.7 } },
    { floor: { color: '#abcabc', opacity: 0.7 } }, { surfaces: { color: '#abcdef' } },
    { camera: { projection: 'orthographic' } },
  ]) assert.equal(viewPreparationKey(scene({ mode: 'render', clip: { enabled: true }, ...patch })), viewPreparationKey(render));
  for (const patch of [ { clip: { enabled: false } }, { lighting: { quality: 'final' } }, { surfaces: { opacity: 0.5 } }, { lighting: { size: 2 } } ]) {
    assert.notEqual(viewPreparationKey(scene({ mode: 'render', clip: { enabled: true }, ...patch })), viewPreparationKey(render));
  }
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { setImmediate } from 'node:timers';
import { resolveViewSceneSettings } from '@text-to-cad/core/common/sceneSettings.js';
import { createViewUpdateCoordinator } from './viewUpdateCoordinator.js';
import { afterViewPaint, viewPreparationKey } from './viewUpdatePlan.js';

// A display, drawn in its mode or, with `render`, in Render (Preview's).
const scene = (value, preview = false, previewSettings = {}) => resolveViewSceneSettings({ display: value, preview, previewSettings, lightingQuality: "preview" });
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
  const h = harness(), render = scene({}, true), xray = scene({ mode: 'xray' });
  h.request(render); h.request(xray);
  await h.whenReady();
  assert.deepEqual(h.calls, [['prepare', xray], ['apply', xray], ['present']]);
  assert.equal(h.statuses.at(-1).pending, false);
});

test('return to visible settings during preparation cancels work and settles captures', async () => {
  const h = harness({ prepare: (_, signal) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('cancelled')))) });
  h.request(scene({}, true)); await tick();
  const capture = h.whenReady(); h.request(h.initial);
  await capture;
  assert.deepEqual(h.calls, []);
  assert.equal(h.statuses.at(-1).pending, false);
});

test('a superseded reconciliation is restored without presenting the stale recipe', async () => {
  const first = deferred(), applied = [], presented = [];
  const h = harness({ apply: async target => { applied.push(target); if(applied.length===1) await first.promise; }, present: async () => presented.push(applied.at(-1)) });
  const render = scene({}, true);
  h.request(render); await tick();
  h.request(h.initial); first.resolve();
  await h.whenReady();
  assert.deepEqual(applied, [render, h.initial]);
  assert.deepEqual(presented, [h.initial]);
});

test('live edits skip preparation and capture waits for the actual presented frame', async () => {
  const frame = deferred(), h = harness({ present: () => frame.promise });
  h.request(scene({ grid: true, clip: { enabled: false } }));
  let ready = false; const capture = h.whenReady().then(() => { ready = true; });
  await tick(); assert.equal(ready, false);
  assert.deepEqual(h.calls.map(c => c[0]), ['apply']);
  frame.resolve(); await capture;
});

test('failures surface once, reject captures, and retry the requested values', async () => {
  let fail = true;
  const h = harness({ present: async () => { if (fail) throw new Error('GPU failure'); } });
  const render = scene({}, true); h.request(render);
  await assert.rejects(h.whenReady(), /GPU failure/);
  assert.equal(h.statuses.at(-1).error, 'GPU failure');
  fail = false; h.retry(); await h.whenReady();
  assert.equal(h.statuses.at(-1).error, null);
});

test('unmount aborts preparation and rejects pending captures', async () => {
  let signal;
  const h = harness({ prepare: (_, value) => { signal=value; return new Promise(()=>{}); } });
  h.request(scene({}, true)); await tick();
  const capture = h.whenReady(); h.dispose();
  await assert.rejects(capture, /Viewer closed/); assert.equal(signal.aborted, true);
});

test('only resource boundaries prepare; clip motion, exposure, rotation and color stay live', () => {
  const render = scene({ clip: { enabled: true } }, true);
  const key = (display, previewSettings = {}) => viewPreparationKey(scene({ clip: { enabled: true }, ...display }, true, previewSettings));
  for (const [display, previewSettings] of [
    [{}, { lighting: { exposure: 1, rotation: 35 } }], [{ clip: { enabled: true, at: 0.7 } }],
    [{}, { floor: { color: '#abcabc', opacity: 0.7 } }], [{}, { parts: { color: '#abcdef' } }],
    [{ camera: { projection: 'orthographic' } }],
  ]) assert.equal(key(display, previewSettings), viewPreparationKey(render));
  for (const [display, previewSettings] of [[{ clip: { enabled: false } }], [{}, { lighting: { quality: 'final' } }], [{}, { lighting: { size: 2 } }]]) {
    assert.notEqual(key(display, previewSettings), viewPreparationKey(render));
  }
});

test('a paint wait no frame comes to settles on its timer and reaches for no frame API', async t => {
  // A hidden tab draws no frame, and a page can be gone, its frame API with it, when the timer
  // fires (the CI flake: a test file torn down first). Node has no cancelAnimationFrame at all.
  t.mock.timers.enable({ apis: ['setTimeout'] });
  globalThis.requestAnimationFrame = () => 1;
  try {
    const painted = afterViewPaint();
    t.mock.timers.tick(100);
    await painted;
  } finally {
    delete globalThis.requestAnimationFrame;
  }
});

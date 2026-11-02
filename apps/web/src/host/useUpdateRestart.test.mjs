import assert from 'node:assert/strict';
import test from 'node:test';
import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { RECONNECT_UPDATE_MS } from './useEngineReconnect.js';
import { useUpdateRestart } from './useUpdateRestart.js';

/** A page following its update through the restart, its server's answers `answers` in turn (an Error throws). */
async function following(t, answers, { restarting = true } = {}) {
  const dom = new JSDOM('<div id="root"></div>');
  const previous = new Map(['window', 'document', 'IS_REACT_ACT_ENVIRONMENT'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const queued = [];
  const said = { asked: 0, reloads: 0, settled: [] };
  const options = {
    instance: 'a', release: '0.10.1',
    ask: async () => {
      said.asked += 1;
      const answer = answers.shift();
      if (answer instanceof Error) throw answer;
      return answer ?? null;
    },
    reload: () => { said.reloads += 1; },
    settle: answer => { said.settled.push(answer); },
    schedule: (run, delayMs) => { const timer = { run, delayMs }; queued.push(timer); return timer; },
    cancel: timer => { const at = queued.indexOf(timer); if (at >= 0) queued.splice(at, 1); },
  };
  let phase = restarting;
  function Probe() { useUpdateRestart(phase, options); return null; }
  const root = createRoot(dom.window.document.getElementById('root'));
  await act(() => root.render(createElement(Probe)));
  t.after(async () => {
    await act(() => root.unmount());
    dom.window.close();
    for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  });
  const delays = [];
  const advance = () => act(async () => { const timer = queued.shift(); delays.push(timer.delayMs); await timer.run(); });
  const render = async (next) => { phase = next; await act(() => root.render(createElement(Probe))); };
  return { said, queued, delays, advance, render };
}

test('through the restart the page asks on its own, and an answer from another start of the engine reloads it', async (t) => {
  // The draining engine (the page's own, still restarting), nothing, an error, then the engine that
  // followed: the release before's, started again after a failed switch -- the same release, another start.
  const answers = [{ instance: 'a', release: '0.10.1', update: { state: 'restarting' } }, null, new TypeError('Failed to fetch'),
    { instance: 'b', release: '0.10.1', update: { state: 'failed' } }];
  const page = await following(t, answers);
  for (let turn = 0; turn < 4; turn += 1) await page.advance();
  assert.deepEqual(page.delays, Array(4).fill(RECONNECT_UPDATE_MS), 'every quarter second, never backing off');
  assert.deepEqual([page.said.asked, page.said.reloads, page.said.settled, page.queued.length], [4, 1, [], 0],
    'reloaded once, into the engine that followed, and it stops asking');
});

test('an answer of another release reloads the page too, the same start or not', async (t) => {
  const page = await following(t, [{ instance: 'a', release: '0.10.2', update: { state: 'idle' } }]);
  await page.advance();
  assert.deepEqual([page.said.reloads, page.queued.length], [1, 0]);
});

test("the page's own engine saying its update failed ends the restart there", async (t) => {
  const failed = { instance: 'a', release: '0.10.1', update: { state: 'failed', target: '0.10.2', error: 'it did not start' } };
  const page = await following(t, [{ instance: 'a', release: '0.10.1', update: { state: 'working' } }, failed]);
  await page.advance();
  assert.deepEqual([page.said.reloads, page.said.settled, page.queued.length], [0, [], 1], 'still working: asked again');
  await page.advance();
  assert.deepEqual([page.said.reloads, page.said.settled, page.queued.length], [0, [failed], 0], 'settled, and it stops asking');
});

test('a page not restarting asks nothing', async (t) => {
  const idle = await following(t, [], { restarting: false });
  assert.deepEqual([idle.queued.length, idle.said.asked], [0, 0]);
});

test('a page whose restart ends stops asking', async (t) => {
  const page = await following(t, [{ instance: 'a', release: '0.10.1', update: { state: 'restarting' } }]);
  await page.advance();
  assert.equal(page.queued.length, 1);
  await page.render(false);
  assert.deepEqual([page.queued.length, page.said.reloads], [0, 0]);
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { useViewerAutoReload } from './useViewerAutoReload.js';

function driver(answers, { follow = true } = {}) {
  const queued = [];
  const reloads = [];
  const foreign = [];
  let clock = 0;
  let asks = 0;
  let asked = Promise.resolve();
  return {
    reloads,
    foreign,
    get asks() { return asks; },
    options: {
      follow, onForeign: () => foreign.push(clock),
      fetchServerInfo: () => { asks += 1; return (asked = Promise.resolve(answers.shift() ?? { ok: true, identityToken: 'a' })); },
      reload: () => reloads.push(clock), now: () => clock,
      schedule: (run, delayMs) => { const timer = { run, delayMs }; queued.push(timer); return timer; },
      cancel: timer => { const index = queued.indexOf(timer); if (index >= 0) queued.splice(index, 1); },
    },
    get scheduled() { return queued.length; },
    get asked() { return asked; },
    async advance() { const next = queued.shift(); if (next) { clock += next.delayMs; await next.run(); } },
  };
}
async function mount(serverInfo, drive) {
  const dom = new JSDOM('<div id="root"></div>');
  const previous = new Map(['window', 'document', 'IS_REACT_ACT_ENVIRONMENT'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const root = createRoot(dom.window.document.getElementById('root'));
  function Probe() { useViewerAutoReload(serverInfo, drive.options); return null; }
  await act(() => root.render(createElement(Probe)));
  return {
    advance: () => act(() => drive.advance()),
    // The hook's own answer is handled before this await resumes: it awaited the same promise first.
    focus: () => act(async () => { dom.window.dispatchEvent(new dom.window.Event('focus')); await drive.asked; }),
    async dispose() {
      await act(() => root.unmount()); dom.window.close();
      for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
    },
  };
}

test('an engine-served page stops at another process on its port and never loads it', async () => {
  const drive = driver([{ ok: false }, { ok: true, identityToken: 'b' }, { ok: true, identityToken: 'c' }], { follow: false });
  const view = await mount({ identityToken: 'a' }, drive);
  try {
    await view.advance(); await view.advance();
    assert.deepEqual(drive.reloads, [], 'nothing on the port is loaded into the tab');
    assert.deepEqual(drive.foreign, [5_000], 'it is said as the engine being gone');
    assert.equal(drive.scheduled, 0, 'and it stops asking');
    await view.focus();
    assert.equal(drive.asks, 2, 'coming back to the window asks nothing more');
  } finally { await view.dispose(); }
});

test('a dev server reloads for another build on its port, not for its own restart', async () => {
  const drive = driver([{ ok: false }, { ok: true, identityToken: 'a' }, { ok: true, identityToken: 'b' }]);
  const view = await mount({ identityToken: 'a' }, drive);
  try {
    await view.advance(); await view.advance(); assert.deepEqual(drive.reloads, []);
    await view.advance();
    assert.deepEqual(drive.reloads, [10_000], 'asked every 5 s, answered or not'); assert.equal(drive.scheduled, 0);
  } finally { await view.dispose(); }
});

test('coming back to the window asks at once', async () => {
  const drive = driver([{ ok: true, identityToken: 'b' }]);
  const view = await mount({ identityToken: 'a' }, drive);
  try {
    await view.focus();
    assert.equal(drive.reloads.length, 1); assert.equal(drive.scheduled, 0, 'the tick it pre-empted is cancelled');
  } finally { await view.dispose(); }
});

test('a transient outage does not reload, and unmount cancels polling', async () => {
  const drive = driver([{ ok: false }, { ok: true, identityToken: 'a' }]);
  const view = await mount({ identityToken: 'a' }, drive);
  await view.advance(); await view.advance(); assert.deepEqual(drive.reloads, []);
  assert.equal(drive.scheduled, 1);
  await view.dispose(); assert.equal(drive.scheduled, 0);
});

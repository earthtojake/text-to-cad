import assert from 'node:assert/strict';
import test from 'node:test';
import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { useViewerAutoReload } from './useViewerAutoReload.js';

function driver(answers) {
  const queued = [];
  const reloads = [];
  let clock = 0;
  return {
    reloads,
    options: {
      fetchServerInfo: async () => answers.shift() ?? { ok: true, identityToken: 'a' },
      reload: () => reloads.push(clock), now: () => clock,
      schedule: (run, delayMs) => { const timer = { run, delayMs }; queued.push(timer); return timer; },
      cancel: timer => { const index = queued.indexOf(timer); if (index >= 0) queued.splice(index, 1); },
    },
    get scheduled() { return queued.length; },
    async advance() { const next = queued.shift(); if (next) { clock += next.delayMs; await next.run(); } },
  };
}
async function mount(serverInfo, drive) {
  const dom = new JSDOM('<div id="root"></div>');
  const previous = new Map(['window', 'document', 'IS_REACT_ACT_ENVIRONMENT'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const root = createRoot(dom.window.document.getElementById('root'));
  let result;
  function Probe() { result = useViewerAutoReload(serverInfo, drive.options); return null; }
  await act(() => root.render(createElement(Probe)));
  return {
    get result() { return result; },
    advance: () => act(() => drive.advance()),
    async dispose() {
      await act(() => root.unmount()); dom.window.close();
      for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
    },
  };
}

test('production viewer schedules no reload polling', async () => {
  const drive = driver([]);
  const view = await mount({ autoReload: false, identityToken: 'a' }, drive);
  try { assert.equal(view.result, false); assert.equal(drive.scheduled, 0); }
  finally { await view.dispose(); }
});

test('development restart reports pending and reloads exactly once', async () => {
  const drive = driver([{ ok: true, identityToken: 'a' }, { ok: false }, { ok: false }, { ok: true, identityToken: 'b' }]);
  const view = await mount({ autoReload: true, identityToken: 'a' }, drive);
  try {
    await view.advance(); assert.equal(view.result, false);
    await view.advance(); assert.equal(view.result, true); assert.deepEqual(drive.reloads, []);
    await view.advance(); await view.advance();
    assert.equal(drive.reloads.length, 1); assert.equal(drive.scheduled, 0);
  } finally { await view.dispose(); }
});

test('a transient outage clears pending without reload and unmount cancels polling', async () => {
  const drive = driver([{ ok: false }, { ok: true, identityToken: 'a' }]);
  const view = await mount({ autoReload: true, identityToken: 'a' }, drive);
  await view.advance(); assert.equal(view.result, true);
  await view.advance(); assert.equal(view.result, false); assert.deepEqual(drive.reloads, []);
  assert.equal(drive.scheduled, 1);
  await view.dispose(); assert.equal(drive.scheduled, 0);
});

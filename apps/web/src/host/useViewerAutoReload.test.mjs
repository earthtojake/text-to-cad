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
  let asked = Promise.resolve();
  return {
    reloads,
    options: {
      fetchServerInfo: () => (asked = Promise.resolve(answers.shift() ?? { ok: true, identityToken: 'a' })),
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

test('an installed viewer reloads for another install on its port, not for its own restart', async () => {
  const drive = driver([{ ok: false }, { ok: true, identityToken: 'a' }, { ok: true, identityToken: 'b' }]);
  const view = await mount({ autoReload: false, identityToken: 'a' }, drive);
  try {
    await view.advance(); await view.advance(); assert.deepEqual(drive.reloads, []);
    await view.advance();
    assert.deepEqual(drive.reloads, [10_000], 'asked every 5 s, answered or not'); assert.equal(drive.scheduled, 0);
  } finally { await view.dispose(); }
});

test('coming back to the window asks at once', async () => {
  const drive = driver([{ ok: true, identityToken: 'b' }]);
  const view = await mount({ autoReload: false, identityToken: 'a' }, drive);
  try {
    await view.focus();
    assert.equal(drive.reloads.length, 1); assert.equal(drive.scheduled, 0, 'the tick it pre-empted is cancelled');
  } finally { await view.dispose(); }
});

test('a development restart reloads exactly once, when the new server answers', async () => {
  const drive = driver([{ ok: true, identityToken: 'a' }, { ok: false }, { ok: false }, { ok: true, identityToken: 'b' }]);
  const view = await mount({ autoReload: true, identityToken: 'a' }, drive);
  try {
    await view.advance(); await view.advance(); assert.deepEqual(drive.reloads, []);
    await view.advance(); await view.advance();
    assert.equal(drive.reloads.length, 1); assert.equal(drive.scheduled, 0);
  } finally { await view.dispose(); }
});

test('a transient outage does not reload, and unmount cancels polling', async () => {
  const drive = driver([{ ok: false }, { ok: true, identityToken: 'a' }]);
  const view = await mount({ autoReload: true, identityToken: 'a' }, drive);
  await view.advance(); await view.advance(); assert.deepEqual(drive.reloads, []);
  assert.equal(drive.scheduled, 1);
  await view.dispose(); assert.equal(drive.scheduled, 0);
});

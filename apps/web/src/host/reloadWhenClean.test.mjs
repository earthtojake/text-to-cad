import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';
import { pageHasUnsaved, reloadWhenClean, RELOAD_RETRY_MS } from './reloadWhenClean.js';

test('a reload waits while a field holds what the person is typing', () => {
  const dom = new JSDOM('<input>');
  const { document } = dom.window;
  const input = document.querySelector('input');
  input.focus();
  assert.equal(pageHasUnsaved(document), false, 'an empty field loses nothing');
  input.value = 'make the bracket 2 mm thicker';
  assert.equal(pageHasUnsaved(document), true);
  // The page's timers and focus events, run by hand.
  const timers = [];
  const listeners = new Set();
  const target = {
    setTimeout: (run, delayMs) => { timers.push({ run, delayMs }); return timers.length; },
    clearTimeout: () => {},
    addEventListener: (_type, listener) => listeners.add(listener),
    removeEventListener: (_type, listener) => listeners.delete(listener),
  };
  const reloads = [];
  reloadWhenClean(() => reloads.push(1), { unsaved: () => pageHasUnsaved(document), target });
  assert.deepEqual([reloads, timers.map(timer => timer.delayMs)], [[], [RELOAD_RETRY_MS]]);
  timers.shift().run();
  assert.deepEqual(reloads, [], 'still typing');
  input.blur();
  for (const listener of listeners) listener();
  timers.at(-1).run();
  assert.deepEqual([reloads, listeners.size], [[1], 0]);
  dom.window.close();
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { dismissNotice, dismissedNotices } from './dismissedNotices.js';

/** The browser's local storage, as every page of it sees it. */
function browserStorage() {
  const kept = new Map();
  return { kept, getItem: key => kept.get(key) ?? null, setItem: (key, value) => kept.set(key, String(value)) };
}

test('a notice dismissed is kept by its id for every page of this browser, each once', () => {
  const storage = browserStorage();
  assert.deepEqual(dismissedNotices(storage), []);
  dismissNotice('install-moved', storage);
  dismissNotice('plain', storage);
  dismissNotice('install-moved', storage);
  assert.deepEqual(dismissedNotices(storage), ['install-moved', 'plain']);
  assert.deepEqual([...storage.kept.values()], ['["install-moved","plain"]']);
});

test('storage that refuses, holds something else, or is not there reads none, keeps none, and never fails', () => {
  const refused = () => { throw new DOMException('denied', 'SecurityError'); };
  const storage = { getItem: refused, setItem: refused };
  dismissNotice('install-moved', storage);
  assert.deepEqual(dismissedNotices(storage), []);
  for (const held of ['not json', '{"a":1}', '[1,"a",null]']) {
    const other = browserStorage();
    other.setItem('text-to-cad.notices.dismissed', held);
    assert.deepEqual(dismissedNotices(other), held.startsWith('[') ? ['a'] : []);
  }
  // No storage at all (no window here): none.
  assert.deepEqual(dismissedNotices(), []);
  dismissNotice('install-moved');
});

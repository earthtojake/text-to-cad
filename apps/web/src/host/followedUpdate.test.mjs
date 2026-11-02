import assert from 'node:assert/strict';
import test from 'node:test';
import { followedUpdate, forgetFollowedUpdate, noteFollowedUpdate } from './followedUpdate.js';

/** The tab's session storage, as a page sees it across its reload. */
function tabStorage() {
  const kept = new Map();
  return { getItem: key => kept.get(key) ?? null, setItem: (key, value) => kept.set(key, String(value)),
    removeItem: key => kept.delete(key) };
}

test('a page that followed an update through the restart is known to the page reloaded after it, once', () => {
  const storage = tabStorage();
  assert.equal(followedUpdate(storage), false);
  noteFollowedUpdate(storage);  // the update restarts the engine; the page reloads into the one that comes back
  assert.equal(followedUpdate(storage), true);
  assert.equal(followedUpdate(storage), true, 'read twice in strict mode, the same answer');
  forgetFollowedUpdate(storage);
  assert.equal(followedUpdate(storage), false, 'a later load of the tab follows nothing');
});

test('storage the tab refuses (a private window, blocked site data) leaves the page as it was', () => {
  const refused = () => { throw new DOMException('denied', 'SecurityError'); };
  const storage = { getItem: refused, setItem: refused, removeItem: refused };
  noteFollowedUpdate(storage);
  assert.equal(followedUpdate(storage), false);
  forgetFollowedUpdate(storage);
});

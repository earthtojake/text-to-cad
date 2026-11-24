import assert from "node:assert/strict";
import test from "node:test";
import { STALE_BUILD_KEY, STALE_BUILD_WINDOW_MS, reloadOnStaleBuild } from "./staleBuild.js";

function page({ last = null, clock = 100000 } = {}) {
  const target = new EventTarget();
  const stored = new Map(last === null ? [] : [[STALE_BUILD_KEY, String(last)]]);
  const storage = { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value) };
  const reloads = [];
  const stop = reloadOnStaleBuild({ target, storage, reload: () => reloads.push(clock), now: () => clock, whenClean: reload => { reload(); return () => {}; },
    settle: callback => { callback(); return () => {}; } });
  return { fail: () => target.dispatchEvent(new Event("vite:preloadError", { cancelable: true })), reloads, stored, stop };
}

test("a chunk of an old build that the server no longer has reloads the page into the build it has now, once", () => {
  const open = page();
  open.fail();
  open.fail();
  assert.deepEqual(open.reloads, [100000], "one reload, however many views asked");
  assert.equal(open.stored.get(STALE_BUILD_KEY), "100000");
});

test("a failure right after such a reload is a chunk the new build lacks too: no second reload, the view says it", () => {
  const reloaded = page({ last: 100000 - 1000 });
  reloaded.fail();
  assert.deepEqual(reloaded.reloads, []);
  const later = page({ last: 100000 - STALE_BUILD_WINDOW_MS - 1 });
  later.fail();
  assert.deepEqual(later.reloads, [100000], "long after, an old build again");
});

test("stopped, it listens no more", () => {
  const open = page();
  open.stop();
  open.fail();
  assert.deepEqual(open.reloads, []);
});

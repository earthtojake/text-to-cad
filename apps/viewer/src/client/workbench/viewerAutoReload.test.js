import assert from "node:assert/strict";
import test from "node:test";
import {
  AUTO_RELOAD_PHASE,
  VIEWER_RELOADING_POLL_MS,
  VIEWER_RELOAD_TIMEOUT_MS,
  VIEWER_WATCH_INTERVAL_MS,
  autoReloadIsPending,
  nextAutoReloadState
} from "./viewerAutoReload.js";

const watching = { phase: AUTO_RELOAD_PHASE.WATCHING, since: 0 };

test("the same server on the same port keeps the page as it is", () => {
  const next = nextAutoReloadState(watching, { ok: true, identityToken: "a" }, { baseline: "a", now: 10 });
  assert.equal(next.phase, AUTO_RELOAD_PHASE.WATCHING);
  assert.equal(next.reload, false);
  assert.equal(next.delayMs, VIEWER_WATCH_INTERVAL_MS);
  assert.equal(autoReloadIsPending(next, 10), false);
});

test("a closed port is the restart beginning, not a failure", () => {
  const next = nextAutoReloadState(watching, { ok: false }, { baseline: "a", now: 10 });
  assert.equal(next.phase, AUTO_RELOAD_PHASE.RELOADING);
  assert.equal(next.reload, false);
  assert.equal(next.delayMs, VIEWER_RELOADING_POLL_MS);
  assert.equal(next.since, 10, "the bound starts when the server first stops answering");
  assert.equal(autoReloadIsPending(next, 10), true);

  const still = nextAutoReloadState(next, { ok: false }, { baseline: "a", now: 400 });
  assert.equal(still.since, 10, "a continuing outage does not restart the bound");
});

test("a different identity on the same port reloads the page", () => {
  const down = nextAutoReloadState(watching, { ok: false }, { baseline: "a", now: 10 });
  const back = nextAutoReloadState(down, { ok: true, identityToken: "b" }, { baseline: "a", now: 500 });
  assert.equal(back.reload, true);
});

test("the restarted server is noticed even when no poll ever missed", () => {
  const next = nextAutoReloadState(watching, { ok: true, identityToken: "b" }, { baseline: "a", now: 10 });
  assert.equal(next.reload, true);
});

test("a transient fetch failure that resolves to the same server is not a restart", () => {
  const down = nextAutoReloadState(watching, { ok: false }, { baseline: "a", now: 10 });
  const back = nextAutoReloadState(down, { ok: true, identityToken: "a" }, { baseline: "a", now: 500 });
  assert.equal(back.reload, false);
  assert.equal(back.phase, AUTO_RELOAD_PHASE.WATCHING);
  assert.equal(autoReloadIsPending(back, 500), false);
});

test("the reloading claim is bounded; the watch is not", () => {
  const down = nextAutoReloadState(watching, { ok: false }, { baseline: "a", now: 0 });
  assert.equal(autoReloadIsPending(down, VIEWER_RELOAD_TIMEOUT_MS - 1), true);
  assert.equal(autoReloadIsPending(down, VIEWER_RELOAD_TIMEOUT_MS), false);
  const late = nextAutoReloadState(down, { ok: true, identityToken: "b" }, {
    baseline: "a",
    now: VIEWER_RELOAD_TIMEOUT_MS * 3
  });
  assert.equal(late.reload, true, "a very slow restart still reloads when it lands");
});

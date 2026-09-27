import assert from "node:assert/strict";
import test from "node:test";
import {
  AUTO_RELOAD_PHASE,
  VIEWER_RELOADING_POLL_MS,
  VIEWER_WATCH_INTERVAL_MS,
  nextAutoReloadState
} from "./viewerAutoReload.js";

const watching = { phase: AUTO_RELOAD_PHASE.WATCHING, since: 0 };

test("the same server on the same port keeps the page as it is", () => {
  const next = nextAutoReloadState(watching, { ok: true, identityToken: "a" }, { baseline: "a", now: 10 });
  assert.equal(next.phase, AUTO_RELOAD_PHASE.WATCHING);
  assert.equal(next.reload, false);
  assert.equal(next.delayMs, VIEWER_WATCH_INTERVAL_MS);
});

test("a closed port is the restart beginning, not a failure", () => {
  const next = nextAutoReloadState(watching, { ok: false }, { baseline: "a", now: 10 });
  assert.equal(next.phase, AUTO_RELOAD_PHASE.RELOADING);
  assert.equal(next.reload, false);
  assert.equal(next.delayMs, VIEWER_RELOADING_POLL_MS);
  assert.equal(next.since, 10, "the outage is dated from when the server first stops answering");

  const still = nextAutoReloadState(next, { ok: false }, { baseline: "a", now: 400 });
  assert.equal(still.since, 10, "a continuing outage keeps its first date");
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
});

test("the watch is not bounded: a very slow restart still reloads when it lands", () => {
  const down = nextAutoReloadState(watching, { ok: false }, { baseline: "a", now: 0 });
  const late = nextAutoReloadState(down, { ok: true, identityToken: "b" }, {
    baseline: "a",
    now: 90_000
  });
  assert.equal(late.reload, true, "a very slow restart still reloads when it lands");
});

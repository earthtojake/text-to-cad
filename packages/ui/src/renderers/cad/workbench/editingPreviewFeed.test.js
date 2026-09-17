import test from "node:test";
import assert from "node:assert/strict";
import { setImmediate } from "node:timers";
import { observeEditingPreview } from "./editingPreviewFeed.js";

const settled = () => new Promise(resolve => setImmediate(resolve));

function harness(file = "part.step") {
  const requests = [], timers = [], updates = [], errors = [];
  const stop = observeEditingPreview(file, value => updates.push(value), error => errors.push(error), {
    fetchImpl(url, options) {
      return new Promise(resolve => requests.push({ url, options, resolve }));
    },
    schedule(callback, delay) {
      const timer = { callback, delay, cancelled: false };
      timers.push(timer);
      return timer;
    },
    cancel(timer) { if (timer) timer.cancelled = true; },
  });
  return { requests, timers, updates, errors, stop };
}

function answer(request, value, ok = true) {
  request.resolve({ ok, json: async () => value });
}

test("holds one request, carries the returned cursor and coalesces progress", async () => {
  const h = harness("parts/a b.step");
  try {
    assert.equal(h.requests.length, 1);
    assert.equal(new URL(h.requests[0].url, "http://localhost").searchParams.get("file"), "parts/a b.step");
    assert.equal(h.timers.length, 0, "an unresolved request cannot schedule another");
    answer(h.requests[0], { state: "building", feedCursor: "epoch:1" });
    await settled();
    assert.equal(h.updates.length, 1);
    assert.equal(h.timers[0].delay, 16);
    h.timers[0].callback();
    assert.equal(h.requests.length, 2);
    assert.equal(new URL(h.requests[1].url, "http://localhost").searchParams.get("after"), "epoch:1");
    assert.equal(h.timers.length, 1);
  } finally { h.stop(); }
});

test("switching files aborts a held request and ignores a late response", async () => {
  const h = harness("old.step");
  h.stop();
  assert.equal(h.requests[0].options.signal.aborted, true);
  answer(h.requests[0], { feedCursor: "old:1", preview: { tree: "old" } });
  await settled();
  assert.deepEqual(h.updates, []);
  assert.deepEqual(h.errors, []);
  assert.deepEqual(h.timers, []);
  const next = harness("new.step");
  assert.equal(new URL(next.requests[0].url, "http://localhost").searchParams.has("after"), false);
  next.stop();
});

test("errors clear the cursor and retry slowly; cleanup cancels the retry", async () => {
  const h = harness();
  answer(h.requests[0], { feedCursor: "epoch:1" });
  await settled();
  h.timers[0].callback();
  answer(h.requests[1], null, false);
  await settled();
  assert.equal(h.errors.length, 1);
  assert.equal(h.timers[1].delay, 500);
  h.timers[1].callback();
  assert.equal(new URL(h.requests[2].url, "http://localhost").searchParams.has("after"), false);
  answer(h.requests[2], { state: "disconnected" });
  await settled();
  assert.equal(h.timers[2].delay, 500);
  h.stop();
  assert.equal(h.timers[2].cancelled, true);
});

test("watcher saturation backs off while retaining its output cursor", async () => {
  const h = harness();
  try {
    for (let index = 0; index < 3; index++) {
      answer(h.requests[index], { feedCursor: "epoch:1", feedLimited: true });
      await settled();
      assert.equal(h.timers[index].delay, 500, "saturation must not spin at frame rate");
      h.timers[index].callback();
      assert.equal(new URL(h.requests[index + 1].url, "http://localhost").searchParams.get("after"), "epoch:1");
    }
  } finally { h.stop(); }
});

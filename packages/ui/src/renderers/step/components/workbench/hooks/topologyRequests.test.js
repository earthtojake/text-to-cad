import assert from "node:assert/strict";
import test from "node:test";

import { chooseTopologyBatch, createTopologyRequestSession, sameTopologyIds, topologyIdsWithin } from "./topologyRequests.js";

test("a batch keeps what is loaded and still requested, and adds the newest requests within budget", () => {
  const order = new Map([["a", 1], ["b", 2], ["c", 3], ["d", 4], ["e", 5]]);
  assert.deepEqual(chooseTopologyBatch(["a", "b", "c", "d", "e"], ["a", "x"], { budget: 2, requestOrder: order }), ["a", "e", "d"]);
  assert.deepEqual(chooseTopologyBatch(["a", "b"], ["a", "b", "c"], { budget: 2, requestOrder: order }), ["a", "b"]);
  assert.deepEqual(chooseTopologyBatch(["c", "a", "a"], [], {}), ["c", "a"]);
  assert.deepEqual(chooseTopologyBatch([], ["a"], { budget: 3 }), []);
});

test("requested ids compare as sets", () => {
  assert.ok(sameTopologyIds(["a", "b"], ["b", "a", "a"]));
  assert.ok(!sameTopologyIds(["a"], ["a", "b"]));
  assert.ok(topologyIdsWithin(["a"], ["b", "a"]));
  assert.ok(topologyIdsWithin([], ["a"]));
  assert.ok(!topologyIdsWithin(["a", "c"], ["a"]));
});

// A session whose batches the test finishes by hand: each loadBatch call waits until resolved,
// then publishes what the session accepts, as the viewer's loader does.
function harness({ budget = 64, priorityBudget = 8, published = null } = {}) {
  const calls = [];
  let current = true;
  const events = [];
  let clock = 1000;
  const session = createTopologyRequestSession({
    published,
    budget,
    priorityBudget,
    intervalMs: 150,
    now: () => clock,
    wait: async (ms) => { clock += ms; },
    isCurrent: () => current,
    onLoading: () => events.push("loading"),
    onSettled: (state) => events.push(["settled", state]),
    onFailed: async (error) => events.push(["failed", error.message]),
    loadBatch: (ids) => new Promise((resolve, reject) => {
      calls.push({
        ids: [...ids],
        finish() {
          if (!current) return resolve("stale");
          if (!session.accepts(ids)) return resolve("skipped");
          session.publish(ids, { ids: [...ids].sort() });
          resolve("published");
        },
        fail(error) { reject(error); }
      });
    })
  });
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
  return { session, calls, events, flush, cancel: () => { current = false; }, tick: (ms) => { clock += ms; } };
}

test("requests union into the session: a batch in flight is never aborted, and the next adds what arrived", async () => {
  const { session, calls, events, flush } = harness();
  assert.equal(session.request(["a", "b"]).started, true);
  assert.deepEqual(calls.map((call) => call.ids), [["a", "b"]]);
  // A superset while the batch loads: nothing is cancelled; "c" (one new part) loads beside it.
  assert.equal(session.request(["a", "b", "c"]).started, false);
  assert.deepEqual(calls.map((call) => call.ids), [["a", "b"], ["c"]]);
  calls[0].finish(); await flush();
  assert.deepEqual(session.published.ids, ["a", "b"]);
  // The priority batch was chosen before "a" and "b" were published: it would take them back.
  calls[1].finish(); await flush();
  assert.deepEqual(session.published.ids, ["a", "b"]);
  // The bulk loop composes both.
  assert.deepEqual(calls.at(-1).ids, ["a", "b", "c"]);
  calls.at(-1).finish(); await flush();
  assert.deepEqual(session.published.ids, ["a", "b", "c"]);
  assert.deepEqual(events, ["loading", ["settled", { ids: ["a", "b", "c"] }]]);
});

test("a part requested behind a big batch is published before that batch finishes", async () => {
  const { session, calls, flush } = harness({ budget: 3 });
  session.request(["p1", "p2", "p3"]);
  calls[0].finish(); await flush();
  const many = Array.from({ length: 10 }, (_, index) => `q${index}`);
  session.request(["p1", "p2", "p3", ...many]);
  await flush();
  const bulk = calls.at(-1);
  assert.equal(bulk.ids.length, 6, "what is published and the three newest new parts");
  session.request(["p1", "p2", "p3", ...many, "pressed"]);
  const priority = calls.at(-1);
  assert.ok(priority !== bulk && priority.ids.includes("pressed"));
  assert.ok(["p1", "p2", "p3"].every((id) => priority.ids.includes(id)), "keeping everything published");
  priority.finish(); await flush();
  assert.ok(session.published.ids.includes("pressed"), "pickable while the big batch still loads");
  bulk.finish(); await flush();
  assert.ok(session.published.ids.includes("pressed"), "and never taken back by the batch that started before it");
});

test("a request settling back to what is published starts nothing; letting a part go recomposes without it", async () => {
  const { session, calls, events, flush } = harness();
  session.request(["a", "b"]);
  calls[0].finish(); await flush();
  const before = calls.length;
  assert.equal(session.request(["b", "a", "a"]).settled, true);
  assert.equal(calls.length, before);
  // Collapsing "b" while nothing loads: a batch without it.
  session.request(["a"]);
  await flush();
  assert.deepEqual(calls.at(-1).ids, ["a"]);
  calls.at(-1).finish(); await flush();
  assert.deepEqual(session.published.ids, ["a"]);
  assert.equal(events.filter((event) => event === "loading").length, 2);
});

test("a batch for a part let go of while it loaded is not published", async () => {
  const { session, calls, flush } = harness();
  session.request(["a", "b"]);
  session.request(["a"]);
  calls[0].finish(); await flush();
  assert.equal(session.published?.ids.includes("b") ?? false, false);
  calls.at(-1).finish(); await flush();
  assert.deepEqual(session.published.ids, ["a"]);
});

test("repeating a request while a batch loads costs nothing", async () => {
  const { session, calls } = harness();
  session.request(["a", "b"]);
  for (let index = 0; index < 100; index += 1) session.request(["a", "b"]);
  assert.equal(calls.length, 1);
});

test("a cancelled session publishes nothing and settles nothing; a failed batch reports once", async () => {
  const cancelled = harness();
  cancelled.session.request(["a"]);
  cancelled.cancel();
  cancelled.calls[0].finish(); await cancelled.flush();
  assert.equal(cancelled.session.published, null);
  assert.deepEqual(cancelled.events, ["loading"]);

  const failing = harness();
  failing.session.request(["a"]);
  failing.calls[0].fail(new Error("no topology")); await failing.flush();
  assert.equal(failing.session.failed, true);
  assert.deepEqual(failing.events, ["loading", ["failed", "no topology"]]);
});

test("topology carried into a new session is kept and extended", async () => {
  const { session, calls, flush } = harness({ published: { ids: ["a"], state: "carried" } });
  assert.equal(session.request(["a"]).settled, true);
  session.request(["a", "b"]);
  await flush();
  assert.deepEqual(calls[0].ids, ["a", "b"]);
});

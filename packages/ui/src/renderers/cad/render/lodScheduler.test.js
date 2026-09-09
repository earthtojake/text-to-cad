// The LOD scheduler owns time: debounce, one in-flight re-tessellation,
// worst-first ordering, cancellation, and drain-until-settled.
import assert from "node:assert/strict";
import test from "node:test";

import { createLodScheduler } from "./lodScheduler.js";

// A camera sample factory over a fake model: per-cid distances, 1000px / 45deg.
function sampleWith(distances) {
  return {
    camera: { kind: "perspective", fovYDeg: 45 },
    viewportHeightPx: 1000,
    distanceFor: (cid) => distances[cid],
  };
}

// Manual clock: timers fire only when the test says so.
function makeClock() {
  const timers = new Map();
  let nextId = 1;
  return {
    setTimeoutFn: (fn) => {
      const id = nextId;
      nextId += 1;
      timers.set(id, fn);
      return id;
    },
    clearTimeoutFn: (id) => timers.delete(id),
    fire: () => {
      const pending = [...timers.values()];
      timers.clear();
      pending.forEach((fn) => fn());
    },
    count: () => timers.size,
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// queueMicrotask twice: the scheduler's apply/drain settles across two
// microtask hops (then + finally). No setImmediate — that's node-only and the
// unbound-identifier policy test rejects it in client code.
const tick = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
};

test("debounce: rapid samples collapse to one evaluation; worst error loads first", async () => {
  const clock = makeClock();
  const loads = [];
  const applied = [];
  const gates = [];
  const scheduler = createLodScheduler({
    loadLevel: (cid, level) => {
      loads.push(`${cid}@L${level}`);
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    },
    applyLevel: (cid, level) => applied.push(`${cid}@L${level}`),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([
    { cid: "near", diagonal: 100 },
    { cid: "mid", diagonal: 100 },
    { cid: "far", diagonal: 100 },
  ]);
  const sample = sampleWith({ near: 60, mid: 150, far: 5000 });
  scheduler.onCameraSample(sample);
  scheduler.onCameraSample(sample);
  scheduler.onCameraSample(sample);
  assert.equal(clock.count(), 1, "re-armed debounce keeps one pending timer");
  assert.equal(loads.length, 0, "nothing loads before the debounce fires");
  clock.fire();
  assert.deepEqual(loads, ["near@L1"], "worst projected error first, one in flight");
  assert.ok(scheduler.busy());

  // Finishing the swap drains the next-worst item.
  gates[0].resolve({ fake: true });
  await tick();
  assert.equal(scheduler.levelOf("near"), 1);
  assert.deepEqual(applied, ["near@L1"]);
  assert.ok(loads.length >= 2 && loads[1].startsWith("near@L2") || loads[1].startsWith("mid@L1"),
    `drain continues: ${JSON.stringify(loads)}`);
  scheduler.dispose();
});

test("drain climbs the ladder to settle, then goes quiet", async () => {
  const clock = makeClock();
  const loads = [];
  const scheduler = createLodScheduler({
    loadLevel: (cid, level) => {
      loads.push(level);
      return Promise.resolve({});
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100 }]);
  scheduler.onCameraSample(sampleWith({ part: 52 }));
  clock.fire();
  for (let i = 0; i < 6; i += 1) {
    await tick();
  }
  assert.deepEqual(loads, [1, 2], "one rung at a time, stops at the finest");
  assert.equal(scheduler.levelOf("part"), 2);
  assert.equal(scheduler.busy(), false, "settled: no further work");
  scheduler.dispose();
});

test("dispose aborts in-flight work and a late resolve applies nothing", async () => {
  const clock = makeClock();
  const gate = deferred();
  let aborted = false;
  const applied = [];
  const scheduler = createLodScheduler({
    loadLevel: (cid, level, { signal }) => {
      signal.addEventListener("abort", () => {
        aborted = true;
      });
      return gate.promise;
    },
    applyLevel: (cid, level) => applied.push(level),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  scheduler.dispose();
  assert.equal(aborted, true, "dispose aborts the in-flight load");
  gate.resolve({});
  await tick();
  assert.deepEqual(applied, [], "a late payload is dropped");
});

test("a failed level load leaves the current level standing and does not wedge", async () => {
  const clock = makeClock();
  let calls = 0;
  const scheduler = createLodScheduler({
    loadLevel: () => {
      calls += 1;
      return Promise.reject(new Error("worker died"));
    },
    applyLevel: () => {
      throw new Error("must not apply a failed load");
    },
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  await tick();
  await tick();
  assert.equal(scheduler.levelOf("part"), 0, "level unchanged after failure");
  assert.equal(scheduler.busy(), false, "scheduler is not wedged");
  assert.ok(calls >= 1);
  scheduler.dispose();
});

test("setComponents resets levels and cancels stale work (model switch)", async () => {
  const clock = makeClock();
  const gate = deferred();
  let aborted = false;
  const scheduler = createLodScheduler({
    loadLevel: (cid, level, { signal }) => {
      signal.addEventListener("abort", () => {
        aborted = true;
      });
      return gate.promise;
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "old", diagonal: 100 }]);
  scheduler.onCameraSample(sampleWith({ old: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  scheduler.setComponents([{ cid: "new", diagonal: 50 }]);
  assert.equal(aborted, true, "model switch cancels the stale load");
  assert.equal(scheduler.levelOf("old"), null);
  assert.equal(scheduler.levelOf("new"), 0);
  scheduler.dispose();
});

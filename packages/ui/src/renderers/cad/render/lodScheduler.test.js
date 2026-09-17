// The LOD scheduler owns time: debounce, one in-flight re-tessellation,
// worst-first ordering, cancellation, and drain-until-settled.
import assert from "node:assert/strict";
import test from "node:test";

import { LOD_TESSELLATION_LEVELS, nextLevel } from "@hardcore/core/lib/surf/lodPolicy.js";

import { createLodScheduler } from "./lodScheduler.js";
import { estimateViewportLodMemory } from "./viewportLodMemory.js";

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

// Flush the bounded loader, preparation and adoption promise chain. No timer
// advances here: collection and camera deadlines remain controlled by the test.
const tick = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};
const drain = async () => { for (let i = 0; i < 12; i += 1) await tick(); };

test("an omitted level means the canonical default while explicit L0 stays coarse", () => {
  const scheduler = createLodScheduler({ loadLevel: async () => ({}), applyLevel: () => {} });
  scheduler.setComponents([
    { cid: "default", diagonal: 100 },
    { cid: "coarse", diagonal: 100, level: 0 },
  ]);
  assert.equal(scheduler.levelOf("default"), 1);
  assert.equal(scheduler.levelOf("coarse"), 0);
  scheduler.dispose();
});

test("a stationary camera corrects the coarse angular tier and later progressive arrivals", async () => {
  const clock = makeClock();
  const loads = [];
  const scheduler = createLodScheduler({
    ...clock,
    minimumLevel: 1,
    loadLevel: async (cid, level) => { loads.push(`${cid}@${level}`); return {}; },
    applyLevel: () => {},
  });
  scheduler.setComponents([{ cid: "first", diagonal: 10, level: 0 }]);
  const camera = sampleWith({ first: 10000, later: 10000 });
  assert.equal(nextLevel({ diagonal: 10, cameraDistance: 10000,
    camera: camera.camera, viewportHeightPx: camera.viewportHeightPx }, 0), 0,
  "projected chord error alone considers the coarse mesh settled");
  assert.ok(LOD_TESSELLATION_LEVELS[0].angleTolerance > LOD_TESSELLATION_LEVELS[1].angleTolerance,
    "the standard floor must still repair coarse angular tessellation");
  scheduler.onCameraSample(camera);
  clock.fire(); await tick(); await tick();
  assert.equal(scheduler.levelOf("first"), 1);
  scheduler.setComponents([{ cid: "first", diagonal: 10, level: 0 }, { cid: "later", diagonal: 10, level: 0 }], { preserveLevels: true });
  clock.fire(); await tick(); await tick();
  assert.deepEqual(loads, ["first@1", "later@1"]);
  assert.deepEqual(scheduler.snapshot().levelCounts, { 1: 2 });
  assert.equal(scheduler.snapshot().belowMinimum, 0);
  assert.equal(scheduler.snapshot().standardSettled, true);
  scheduler.dispose();
});

test("standard-floor work prioritizes selected then large visible components and defers offscreen leaves", async () => {
  const clock = makeClock();
  const loads = [];
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 1,
    loadLevel: async (cid, level) => { loads.push(`${cid}@${level}`); return {}; }, applyLevel: () => true });
  scheduler.setComponents([
    { cid: "small", diagonal: 1, level: 0 },
    { cid: "offscreen", diagonal: 1000, level: 0 },
    { cid: "large", diagonal: 100, level: 0 },
    { cid: "selected", diagonal: 0.1, level: 0 },
  ]);
  scheduler.onCameraSample({ ...sampleWith({ small: 10000, offscreen: 10000, large: 10000, selected: 10000 }),
    visibleFor: cid => cid !== "offscreen", selectedFor: cid => cid === "selected" });
  clock.fire(); await drain();
  assert.deepEqual(loads, ["selected@1", "large@1", "small@1"]);
  assert.equal(scheduler.levelOf("offscreen"), 0);
  assert.equal(scheduler.snapshot().belowMinimum, 0, "the visible floor excludes deferred offscreen work");
  assert.equal(scheduler.snapshot().standardSettled, true);
  scheduler.dispose();
});

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
    { cid: "near", diagonal: 100, level: 0 },
    { cid: "mid", diagonal: 100, level: 0 },
    { cid: "far", diagonal: 100, level: 0 },
  ]);
  const sample = sampleWith({ near: 60, mid: 150, far: 5000 });
  scheduler.onCameraSample(sample);
  scheduler.onCameraSample(sample);
  scheduler.onCameraSample(sample);
  assert.equal(clock.count(), 1, "re-armed debounce keeps one pending timer");
  assert.equal(loads.length, 0, "nothing loads before the debounce fires");
  clock.fire();
  assert.deepEqual(loads, ["near@L3"], "worst projected error first, one in flight");
  assert.ok(scheduler.busy());

  // Finishing the swap drains the next-worst item.
  gates[0].resolve({ fake: true });
  await tick();
  assert.equal(scheduler.levelOf("near"), 3);
  assert.deepEqual(applied, ["near@L3"]);
  assert.deepEqual(loads, ["near@L3", "mid@L2"], "the next component starts only after adoption");
  scheduler.dispose();
});

test("drain loads only the settled target, then goes quiet", async () => {
  const clock = makeClock();
  const loads = [];
  let idleCalls = 0;
  const scheduler = createLodScheduler({
    onIdle: () => { idleCalls += 1; },
    loadLevel: (cid, level) => {
      loads.push(level);
      return Promise.resolve({});
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 52 }));
  clock.fire();
  for (let i = 0; i < 6; i += 1) {
    await tick();
  }
  assert.deepEqual(loads, [3], "intermediate levels never load or publish");
  assert.equal(scheduler.levelOf("part"), 3);
  assert.equal(scheduler.busy(), false, "settled: no further work");
  assert.equal(scheduler.snapshot().qualitySettled, true);
  assert.equal(idleCalls, 1, "worker ownership ends once after the whole drain, not after each component");
  scheduler.dispose();
});

test("dispose aborts in-flight work and a late resolve applies nothing", async () => {
  const clock = makeClock();
  const gate = deferred();
  let aborted = false;
  const applied = [];
  const releases = [];
  const scheduler = createLodScheduler({
    reserveLevel: () => ({ ok: true, token: "dispose-reservation" }),
    releaseLevel: (token) => releases.push(token),
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
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  scheduler.dispose();
  assert.equal(aborted, true, "dispose aborts the in-flight load");
  gate.resolve({});
  await tick();
  assert.deepEqual(applied, [], "a late payload is dropped");
  assert.deepEqual(releases, ["dispose-reservation"], "cancellation releases its reservation exactly once");
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
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  await drain();
  assert.equal(scheduler.levelOf("part"), 0, "level unchanged after failure");
  assert.equal(scheduler.busy(), false, "scheduler is not wedged");
  assert.ok(calls >= 1);
  scheduler.dispose();
});

test("a denied refinement keeps the usable level and reports the limitation", async () => {
  const clock = makeClock();
  const loads = [];
  const limitations = [];
  const scheduler = createLodScheduler({
    loadLevel: (cid, level) => {
      loads.push(`${cid}@${level}`);
      return Promise.resolve({});
    },
    applyLevel: () => {},
    reserveLevel: ({ cid, currentLevel, level, direction }) => ({
      ok: false,
      detail: { cid, currentLevel, level, direction, requestedBytes: 400 },
    }),
    onLimitation: (detail) => limitations.push(detail),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  await tick();
  assert.deepEqual(loads, [], "denied work never starts");
  assert.equal(scheduler.levelOf("part"), 0, "current display remains usable");
  assert.deepEqual(limitations.map(({ level }) => level), [3, 2, 1]);
  assert.ok(limitations.every(({ direction }) => direction === "refine"));
  assert.equal(scheduler.snapshot().qualitySettled, false);
  assert.equal(scheduler.snapshot().unmetTargets[0].targetLevel, 3);
  assert.equal(scheduler.snapshot().unmetTargets[0].reason, "memory-denied");
  assert.equal(scheduler.busy(), false);
  scheduler.dispose();
});

test("LOD reservation spans replacement load and apply, then releases", async () => {
  const clock = makeClock();
  const gate = deferred();
  const events = [];
  const scheduler = createLodScheduler({
    reserveLevel: ({ direction }) => {
      events.push(`reserve:${direction}`);
      return { ok: true, token: "r1" };
    },
    loadLevel: () => {
      events.push("load");
      return gate.promise;
    },
    applyLevel: () => events.push("apply"),
    releaseLevel: (token) => events.push(`release:${token}`),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.deepEqual(events, ["reserve:refine", "load"]);
  gate.resolve({});
  await tick();
  assert.deepEqual(events.slice(0, 4), ["reserve:refine", "load", "apply", "release:r1"]);
  scheduler.dispose();
});

test("async selector reconciliation retains admission and delays the committed level", async () => {
  const clock = makeClock();
  const apply = deferred();
  const released = [];
  const scheduler = createLodScheduler({
    ...clock,
    loadLevel: async () => ({}),
    applyLevel: () => apply.promise,
    reserveLevel: () => ({ ok: true, token: "held" }),
    releaseLevel: (token) => released.push(token),
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  await tick();
  assert.equal(scheduler.levelOf("part"), 0);
  assert.equal(scheduler.busy(), true);
  assert.deepEqual(released, []);
  scheduler.onCameraSample(sampleWith({ part: 10000 }));
  apply.resolve(true);
  await tick(); await tick();
  assert.ok(released.includes("held"));
  scheduler.dispose();
});

test("a model switch aborts pending selector reconciliation and ignores its late apply", async () => {
  const clock = makeClock();
  const gate = deferred();
  let applySignal;
  const scheduler = createLodScheduler({
    ...clock,
    loadLevel: async () => ({}),
    applyLevel: (_cid, _level, _payload, { signal }) => { applySignal = signal; return gate.promise; },
  });
  scheduler.setComponents([{ cid: "old", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ old: 60 }));
  clock.fire(); await tick();
  scheduler.setComponents([{ cid: "new", diagonal: 100, level: 0 }]);
  assert.equal(applySignal.aborted, true);
  gate.resolve(false); await tick(); await tick();
  assert.equal(scheduler.levelOf("new"), 0);
  assert.equal(scheduler.levelOf("old"), null);
  scheduler.dispose();
});

test("memory pressure coarsens the least-visible detail even while the camera requests fine geometry", async () => {
  const clock = makeClock();
  const loads = [];
  const scheduler = createLodScheduler({
    memoryPressure: () => true,
    loadLevel: (cid, level) => {
      loads.push(`${cid}@L${level}`);
      return Promise.resolve({});
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([
    { cid: "near", diagonal: 100, level: 2 },
    { cid: "farther", diagonal: 100, level: 2 },
  ]);
  scheduler.onCameraSample(sampleWith({ near: 52, farther: 80 }));
  clock.fire();
  for (let i = 0; i < 8; i += 1) await tick();
  assert.equal(loads[0], "farther@L1", "smaller screen error releases detail first");
  assert.equal(scheduler.levelOf("near"), 0);
  assert.equal(scheduler.levelOf("farther"), 0);
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
  scheduler.setComponents([{ cid: "old", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ old: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  scheduler.setComponents([{ cid: "new", diagonal: 50, level: 0 }]);
  assert.equal(aborted, true, "model switch cancels the stale load");
  assert.equal(scheduler.levelOf("old"), null);
  assert.equal(scheduler.levelOf("new"), 0);
  scheduler.dispose();
});

test("setComponents({ preserveLevels }) keeps levels and in-flight work while the same model grows", async () => {
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
  // First progressive batch: "part" loads to a finer level.
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  gate.resolve({});
  await tick();
  // The drain has already moved the near component to a finer rung.
  assert.equal(scheduler.levelOf("part"), 3);
  // A later batch adds a component: the applied level survives.
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }, { cid: "later", diagonal: 50, level: 0 }], { preserveLevels: true });
  assert.equal(scheduler.levelOf("part"), 3);
  assert.equal(scheduler.levelOf("later"), 0);
  // An in-flight load for a retained cid keeps running across a grow...
  const gate2 = deferred();
  const scheduler2 = createLodScheduler({
    loadLevel: (cid, level, { signal }) => {
      signal.addEventListener("abort", () => {
        aborted = true;
      });
      return gate2.promise;
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler2.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler2.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.ok(scheduler2.busy());
  scheduler2.setComponents([{ cid: "part", diagonal: 100, level: 0 }, { cid: "later", diagonal: 50, level: 0 }], { preserveLevels: true });
  assert.equal(aborted, false, "growing the model keeps the in-flight load");
  assert.ok(scheduler2.busy());
  // ...but the default (model switch) still resets everything.
  scheduler2.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  assert.equal(aborted, true);
  assert.equal(scheduler2.levelOf("part"), 0);
  scheduler.dispose();
  scheduler2.dispose();
});

test("an admitted intermediate supplies real bytes for one new final-target estimate after adoption", async () => {
  const clock = makeClock();
  const adoption = deferred();
  const estimates = [], loads = [], releases = [];
  let meshBytes = 100;
  const scheduler = createLodScheduler({
    ...clock,
    reserveLevel: ({ currentLevel, level }) => {
      const estimate = estimateViewportLodMemory({ meshBytes, currentLevel, level });
      estimates.push([currentLevel, level, meshBytes]);
      return estimate.admissionBytes <= 2400 ? { ok: true, token: `L${level}` } : { ok: false, detail: estimate };
    },
    releaseLevel: token => releases.push(token),
    loadLevel: async (_cid, level) => { loads.push(level); return { level }; },
    applyLevel: async (_cid, level) => {
      if (level === 2) await adoption.promise;
      meshBytes = 60;
      return true;
    },
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 })); clock.fire(); await tick();
  assert.deepEqual(estimates, [[0, 3, 100], [0, 2, 100]]);
  assert.deepEqual(loads, [2]);
  assert.equal(scheduler.levelOf("part"), 0, "reservation and publication are not adoption");
  assert.deepEqual(releases, []);
  adoption.resolve(); await drain();
  assert.deepEqual(estimates, [[0, 3, 100], [0, 2, 100], [2, 3, 60]]);
  assert.deepEqual(loads, [2, 3]);
  assert.deepEqual(releases, ["L2", "L3"]);
  assert.equal(scheduler.snapshot().qualitySettled, true);
  scheduler.dispose();
});

test("a partial fallback stays visibly limited after another component succeeds", async () => {
  const clock = makeClock();
  const estimates = [], loads = [], idle = [];
  const scheduler = createLodScheduler({
    ...clock,
    reserveLevel: ({ cid, currentLevel, level }) => {
      estimates.push(`${cid}:${currentLevel}:${level}`);
      return cid === "limited" && level === 3 ? { ok: false, detail: { availableBytes: 1 } } : { ok: true };
    },
    loadLevel: async (cid, level) => { loads.push(`${cid}:${level}`); return {}; },
    applyLevel: () => true,
    onIdle: status => idle.push(status),
  });
  scheduler.setComponents([{ cid: "limited", diagonal: 100, level: 0 }, { cid: "other", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ limited: 52, other: 60 })); clock.fire(); await drain();
  assert.deepEqual(loads, ["limited:2", "other:3"]);
  assert.deepEqual(estimates, ["limited:0:3", "limited:0:2", "limited:2:3", "other:0:3"]);
  assert.equal(idle.length, 1);
  assert.equal(idle[0].qualitySettled, false);
  assert.equal(idle[0].unmetTargets.length, 1);
  assert.deepEqual(idle[0].unmetTargets.map(({ cid, currentLevel, targetLevel, reason }) =>
    ({ cid, currentLevel, targetLevel, reason })), [{ cid: "limited", currentLevel: 2, targetLevel: 3, reason: "memory-denied" }]);
  await drain();
  assert.equal(estimates.length, 4, "same actual state never retries automatically");
  scheduler.onCameraSample(sampleWith({ limited: 52, other: 60 })); clock.fire(); await drain();
  assert.equal(estimates.at(-1), "limited:2:3", "a fresh sample permits a new bounded attempt");
  scheduler.dispose();
});

test("denial fallback has at most six distinct probes and never bypasses the floor branch", async () => {
  const clock = makeClock();
  const probes = [];
  const scheduler = createLodScheduler({
    ...clock,
    reserveLevel: ({ currentLevel, level }) => {
      probes.push(`${currentLevel}:${level}`);
      return { ok: level === currentLevel + 1 };
    },
    loadLevel: async () => ({}), applyLevel: () => true,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 })); clock.fire(); await drain();
  assert.deepEqual(probes, ["0:3", "0:2", "0:1", "1:3", "1:2", "2:3"]);
  assert.equal(scheduler.levelOf("part"), 3);
  scheduler.dispose();

  const floorProbes = [];
  const floor = createLodScheduler({ ...clock, minimumLevel: 2,
    reserveLevel: ({ level }) => { floorProbes.push(level); return { ok: false }; },
    loadLevel: () => assert.fail("denied floor must not load"), applyLevel: () => true });
  floor.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  floor.onCameraSample(sampleWith({ part: 60 })); clock.fire(); await drain();
  assert.deepEqual(floorProbes, [3, 2], "visible work probes only eligible targets at or above the floor");
  assert.equal(floor.snapshot().belowMinimum, 1);
  assert.equal(floor.snapshot().qualitySettled, false);
  floor.dispose();
});

test("hard target failures remain parked after fallback adoption and refused swaps do not advance", async () => {
  for (const failure of ["load", "adoption"]) {
    const clock = makeClock();
    const loads = [], releases = [];
    const scheduler = createLodScheduler({ ...clock,
      reserveLevel: ({ level }) => ({ ok: true, token: `L${level}` }),
      releaseLevel: token => releases.push(token),
      loadLevel: async (_cid, level) => {
        loads.push(level);
        if (failure === "load" && level === 3) throw new Error("failed exact level");
        return {};
      },
      applyLevel: async (_cid, level) => !(failure === "adoption" && level === 3),
    });
    scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
    scheduler.onCameraSample(sampleWith({ part: 60 })); clock.fire(); await drain();
    assert.deepEqual(loads, [3, 2]);
    assert.deepEqual(releases, ["L3", "L2"]);
    assert.equal(scheduler.levelOf("part"), 2);
    assert.equal(scheduler.snapshot().unmetTargets[0].reason, failure === "load" ? "load-failed" : "adoption-refused");
    scheduler.dispose();
  }
});

test("synchronous loader failure parks every attempted rung and releases exactly once", async () => {
  const clock = makeClock();
  const loads = [], releases = [];
  const scheduler = createLodScheduler({ ...clock,
    reserveLevel: ({ level }) => ({ ok: true, token: `L${level}` }), releaseLevel: token => releases.push(token),
    loadLevel: (_cid, level) => { loads.push(level); throw new Error("synchronous loader failure"); },
    applyLevel: () => assert.fail("failed payload must not apply"),
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 })); clock.fire(); await drain();
  assert.deepEqual(loads, [3, 2, 1]);
  assert.deepEqual(releases, ["L3", "L2", "L1"]);
  assert.equal(scheduler.levelOf("part"), 0);
  assert.equal(scheduler.busy(), false);
  assert.equal(scheduler.snapshot().failedLevels, 3);
  scheduler.dispose();
  assert.equal(releases.length, 3);
});

test("an aborted old-model failure cannot poison the same CID in a replacement model", async () => {
  const clock = makeClock();
  const old = deferred(), replacement = deferred();
  const loads = [], releases = [];
  const scheduler = createLodScheduler({ ...clock,
    reserveLevel: () => ({ ok: true, token: `reservation-${loads.length}` }),
    releaseLevel: token => releases.push(token),
    loadLevel: (_cid, level) => { loads.push(level); return loads.length === 1 ? old.promise : replacement.promise; },
    applyLevel: () => true,
  });
  scheduler.setComponents([{ cid: "same", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ same: 60 })); clock.fire();
  scheduler.setComponents([{ cid: "same", diagonal: 100, level: 0 }]);
  assert.equal(scheduler.snapshot().qualitySettled, false, "new model has no accepted camera sample");
  scheduler.onCameraSample(sampleWith({ same: 60 })); clock.fire();
  old.reject(new Error("late abort failure")); await drain();
  assert.deepEqual(loads, [3, 3]);
  assert.equal(scheduler.snapshot().failedLevels, 0);
  assert.equal(scheduler.busy(), true, "old finally cannot clear the replacement task");
  assert.deepEqual(releases, ["reservation-0"]);
  replacement.resolve({}); await drain();
  assert.equal(scheduler.levelOf("same"), 3);
  assert.deepEqual(releases, ["reservation-0", "reservation-1"]);
  scheduler.dispose();
});

test("a failed old-sample task does not park the new sample and a successful one replans latest quality", async () => {
  for (const reject of [true, false]) {
    const clock = makeClock(), first = deferred();
    const loads = [];
    const scheduler = createLodScheduler({ ...clock,
      loadLevel: (_cid, level) => { loads.push(level); return loads.length === 1 ? first.promise : Promise.resolve({}); },
      applyLevel: () => true,
    });
    scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
    scheduler.onCameraSample(sampleWith({ part: 60 })); clock.fire();
    scheduler.onCameraSample(sampleWith({ part: reject ? 52 : 10000 })); clock.fire();
    if (reject) first.reject(new Error("old sample failure")); else first.resolve({});
    await drain();
    assert.deepEqual(loads, reject ? [3, 3] : [3, 0]);
    assert.equal(scheduler.levelOf("part"), reject ? 3 : 0);
    assert.equal(scheduler.snapshot().failedLevels, 0);
    assert.equal(scheduler.snapshot().qualitySettled, true);
    scheduler.dispose();
  }
});

test("memory pressure retains one-rung coarsening and truthfully reports unmet camera quality", async () => {
  const clock = makeClock(), loads = [];
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 1, memoryPressure: () => true,
    loadLevel: async (_cid, level) => { loads.push(level); return {}; }, applyLevel: () => true });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 3 }]);
  scheduler.onCameraSample(sampleWith({ part: 52 })); clock.fire(); await drain();
  assert.deepEqual(loads, [2, 1]);
  assert.equal(scheduler.snapshot().belowMinimum, 0);
  assert.equal(scheduler.snapshot().qualitySettled, false);
  assert.equal(scheduler.snapshot().unmetTargets[0].reason, "memory-pressure");
  scheduler.dispose();
});

test("memory pressure parks a coarse standard floor without loading or retrying", async () => {
  const clock = makeClock(), loads = [];
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 1, memoryPressure: () => true,
    loadLevel: async (_cid, level) => { loads.push(level); return {}; }, applyLevel: () => true });
  scheduler.setComponents([{ cid: "coarse", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ coarse: 10000 })); clock.fire(); await drain();
  assert.deepEqual(loads, []);
  assert.equal(scheduler.snapshot().standardSettled, false);
  assert.equal(scheduler.snapshot().qualitySettled, false);
  assert.deepEqual(scheduler.snapshot().unmetTargets.map(({ currentLevel, targetLevel, reason }) =>
    ({ currentLevel, targetLevel, reason })), [{ currentLevel: 0, targetLevel: 1, reason: "memory-pressure" }]);
  clock.fire(); await drain();
  assert.deepEqual(loads, [], "an idle pressure floor cannot schedule its own retry loop");
  scheduler.dispose();
});

test("offscreen pressure denial is neither a standard target nor a user-facing memory limitation", async () => {
  const clock = makeClock(), limitations = [];
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 1, memoryPressure: () => true,
    reserveLevel: () => ({ ok: false, detail: { requestedBytes: 10 } }),
    onLimitation: detail => limitations.push(detail), loadLevel: async () => ({}), applyLevel: () => true });
  scheduler.setComponents([{ cid: "offscreen", diagonal: 100, level: 3 }]);
  scheduler.onCameraSample({ ...sampleWith({ offscreen: 10000 }), visibleFor: () => false });
  clock.fire(); await drain();
  assert.deepEqual(limitations, []);
  assert.deepEqual(scheduler.snapshot().unmetTargets, []);
  assert.equal(scheduler.snapshot().belowMinimum, 0);
  assert.equal(scheduler.snapshot().standardSettled, true);
  scheduler.dispose();
});

test("accepted pressure coarsening cannot oscillate back through its ceiling without fresh camera intent", async () => {
  const clock = makeClock(), loads = [];
  let scheduler;
  scheduler = createLodScheduler({ ...clock,
    memoryPressure: () => scheduler.levelOf("part") === 3,
    loadLevel: async (_cid, level) => { loads.push(level); assert.ok(loads.length <= 8, "accepted-work drain must be bounded"); return {}; },
    applyLevel: () => true });
  const sample = { ...sampleWith({ part: 52 }), cameraKey: "camera-a" };
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sample); clock.fire(); await drain();
  assert.deepEqual(loads, [3, 2]);
  assert.equal(scheduler.snapshot().qualitySettled, false);
  assert.equal(scheduler.snapshot().unmetTargets[0].pressureCeiling, 2);
  assert.equal(scheduler.snapshot().unmetTargets[0].reason, "memory-pressure");
  scheduler.onCameraSample({ ...sample, distanceFor: () => 51 }); clock.fire(); await drain();
  assert.deepEqual(loads, [3, 2], "bounds/accounting-only samples cannot reset the pressure decision");
  scheduler.onCameraSample({ ...sample, cameraKey: "camera-b" }); clock.fire(); await drain();
  assert.deepEqual(loads, [3, 2, 3, 2], "actual camera motion permits one fresh attempt");
  scheduler.onCameraSample({ ...sample, cameraKey: "camera-b" }, { retry: true }); clock.fire(); await drain();
  assert.deepEqual(loads, [3, 2, 3, 2, 3, 2], "an explicit retry is a new intent, not an automatic recheck");
  scheduler.dispose();
});

test("pressure ceilings tighten only after admitted adoption and never cross the minimum floor", async () => {
  const clock = makeClock(), loads = [], probes = [];
  let pressure = true;
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 2, memoryPressure: () => pressure,
    reserveLevel: ({ level }) => { probes.push(level); return { ok: false }; },
    loadLevel: async (_cid, level) => { loads.push(level); return {}; }, applyLevel: () => true });
  const sample = { ...sampleWith({ part: 52 }), cameraKey: "camera" };
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 3 }]);
  scheduler.onCameraSample(sample); clock.fire(); await drain();
  assert.deepEqual(probes, [2]);
  assert.deepEqual(loads, []);
  assert.equal(scheduler.levelOf("part"), 3);
  assert.equal(scheduler.snapshot().pressureLimitedComponents, 0, "denial alone cannot pretend a coarsening was adopted");
  assert.deepEqual(scheduler.snapshot().unmetTargets.map(({ currentLevel, targetLevel, cameraTargetLevel, reason }) =>
    ({ currentLevel, targetLevel, cameraTargetLevel, reason })),
  [{ currentLevel: 3, targetLevel: 2, cameraTargetLevel: 3, reason: "memory-denied" }]);
  assert.equal(scheduler.snapshot().qualitySettled, false, "blocked pressure relief is not idle success");
  pressure = false;
  scheduler.onCameraSample(sample); clock.fire(); await drain();
  assert.deepEqual(probes, [2]);
  scheduler.dispose();

  const floorLoads = [];
  const floor = createLodScheduler({ ...clock, minimumLevel: 2, memoryPressure: () => true,
    loadLevel: async (_cid, level) => { floorLoads.push(level); return {}; }, applyLevel: () => true });
  floor.setComponents([{ cid: "part", diagonal: 100, level: 3 }]);
  floor.onCameraSample(sample); clock.fire(); await drain();
  assert.deepEqual(floorLoads, [2]);
  assert.equal(floor.snapshot().belowMinimum, 0);
  assert.equal(floor.snapshot().unmetTargets[0].pressureCeiling, 2);
  floor.dispose();
});

test("idle telemetry reports a blocked visible floor target rather than pending work", async () => {
  for (const failure of ["memory", "load"]) {
    const clock = makeClock();
    const scheduler = createLodScheduler({ ...clock, minimumLevel: 2,
      reserveLevel: () => ({ ok: failure !== "memory" }),
      loadLevel: async () => { throw new Error("floor load failed"); }, applyLevel: () => true });
    scheduler.setComponents([{ cid: "visible", diagonal: 100, level: 0 }]);
    scheduler.onCameraSample(sampleWith({ visible: 10000 }));
    clock.fire(); await drain();
    const target = scheduler.snapshot().unmetTargets[0];
    assert.equal(target.currentLevel, 0);
    assert.equal(target.targetLevel, 2);
    assert.equal(target.blockedLevel, undefined);
    assert.equal(target.reason, failure === "memory" ? "memory-denied" : "load-failed");
    if (failure === "load") assert.deepEqual(target.detail, { name: "Error", message: "floor load failed" });
    assert.equal(scheduler.snapshot().qualitySettled, false);
    scheduler.dispose();
  }
});

test("replacing a model waits for the retiring owner's cleanup before starting new work", async () => {
  const clock = makeClock(), old = deferred(), next = deferred();
  const idle = [], loads = [];
  const scheduler = createLodScheduler({ ...clock,
    loadLevel: (cid) => { loads.push(cid); return cid === "old" ? old.promise : next.promise; },
    applyLevel: () => true, onIdle: status => idle.push(status) });
  scheduler.setComponents([{ cid: "old", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ old: 60 })); clock.fire();
  scheduler.onCameraSample(sampleWith({ old: 60 }));
  scheduler.setComponents([]);
  assert.equal(idle.length, 0, "abort alone is not proof that published data stopped being owned");
  assert.equal(clock.count(), 0, "the old package's debounce is canceled too");
  scheduler.setComponents([{ cid: "next", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ next: 60 })); clock.fire();
  old.reject(new Error("old worker stopped")); await drain();
  assert.equal(idle.length, 0, "old completion cannot release a newer active pool");
  assert.deepEqual(loads, ["old", "next"]);
  assert.equal(scheduler.busy(), true);
  next.resolve({}); await drain();
  assert.equal(idle.length, 1);
  scheduler.dispose();
});

test("same-camera resampling preserves hard failures and memory denials across progressive publication", async () => {
  for (const failure of ["load", "memory"]) {
    const clock = makeClock(), attempts = [];
    const scheduler = createLodScheduler({ ...clock,
      reserveLevel: ({ level }) => { if (failure === "memory") attempts.push(level); return { ok: failure !== "memory" }; },
      loadLevel: async (_cid, level) => { attempts.push(level); throw new Error("hard fail"); }, applyLevel: () => true });
    const sample = { ...sampleWith({ part: 52 }), cameraKey: "same-camera" };
    scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
    scheduler.onCameraSample(sample); clock.fire(); await drain();
    assert.deepEqual(attempts, [3, 2, 1]);
    scheduler.setComponents([{ cid: "part", diagonal: 101, level: 0 }], { preserveLevels: true });
    scheduler.onCameraSample({ ...sample, distanceFor: () => 53 }); clock.fire(); await drain();
    assert.deepEqual(attempts, [3, 2, 1]);
    scheduler.onCameraSample({ ...sample, cameraKey: "new-camera" }); clock.fire(); await drain();
    assert.deepEqual(attempts, [3, 2, 1, 3, 2, 1]);
    scheduler.dispose();
  }
});

test("an idle viewport resampling itself settles, and real camera motion still pends then settles", async () => {
  const clock = makeClock(), loads = [];
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 1,
    loadLevel: async (_cid, level) => { loads.push(level); return {}; }, applyLevel: () => true });
  const stationary = { ...sampleWith({ part: 52 }), cameraKey: "camera-a" };
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  assert.equal(scheduler.onCameraSample(stationary), true, "the first sample is new camera intent");
  assert.equal(scheduler.snapshot().pendingEvaluation, true);
  clock.fire(); await drain();
  assert.deepEqual(loads, [3]);
  assert.equal(scheduler.snapshot().qualitySettled, true, "the settled target is applied");

  // A host that resamples a motionless viewport (an effect re-running, a
  // resize observer, a status republication) must not hold the viewport
  // pending: the repeated sample plans nothing new.
  for (let i = 0; i < 5; i += 1) {
    assert.equal(scheduler.onCameraSample({ ...stationary }), false, "a repeated sample changes nothing");
  }
  assert.equal(clock.count(), 0, "an unchanged sample does not arm or re-arm the debounce");
  assert.equal(scheduler.snapshot().pendingEvaluation, false);
  assert.equal(scheduler.snapshot().qualitySettled, true, "an idle viewport stays settled while it resamples");

  // Real motion is pending work again, and so is a same-camera sample whose
  // component distances actually moved.
  assert.equal(scheduler.onCameraSample({ ...sampleWith({ part: 10000 }), cameraKey: "camera-b" }), true);
  assert.equal(scheduler.snapshot().pendingEvaluation, true);
  assert.equal(scheduler.snapshot().qualitySettled, false, "moved camera has an unevaluated sample");
  clock.fire(); await drain();
  assert.deepEqual(loads, [3, 1]);
  assert.equal(scheduler.snapshot().pendingEvaluation, false);
  assert.equal(scheduler.snapshot().qualitySettled, true);
  assert.equal(scheduler.onCameraSample({ ...sampleWith({ part: 52 }), cameraKey: "camera-b" }), true,
    "same camera key, moved component: still real work to replan");
  assert.equal(scheduler.snapshot().pendingEvaluation, true);
  clock.fire(); await drain();
  assert.deepEqual(loads, [3, 1, 3]);
  assert.equal(scheduler.snapshot().qualitySettled, true);
  scheduler.dispose();
});

test("an unchanged sample keeps the pending work it cannot replan away", async () => {
  const clock = makeClock(), gate = deferred();
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 1,
    loadLevel: () => gate.promise, applyLevel: () => true });
  const sample = { ...sampleWith({ part: 52 }), cameraKey: "camera-a" };
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sample);
  clock.fire(); await tick();
  assert.equal(scheduler.busy(), true);
  assert.equal(scheduler.onCameraSample({ ...sample }), false);
  assert.equal(scheduler.snapshot().qualitySettled, false, "an in-flight replacement is not settled");
  gate.resolve({}); await drain();
  assert.equal(scheduler.levelOf("part"), 3);
  assert.equal(scheduler.snapshot().qualitySettled, true);
  scheduler.dispose();
});

test("a sample a visibility or selection change reaches is new work even at the same camera", async () => {
  const clock = makeClock(), loads = [];
  const scheduler = createLodScheduler({ ...clock, minimumLevel: 1,
    loadLevel: async (cid) => { loads.push(cid); return {}; }, applyLevel: () => true });
  const base = { ...sampleWith({ hidden: 52 }), cameraKey: "camera-a" };
  scheduler.setComponents([{ cid: "hidden", diagonal: 100, level: 1 }]);
  assert.equal(scheduler.onCameraSample({ ...base, visibleFor: () => false }), true);
  clock.fire(); await drain();
  assert.deepEqual(loads, [], "an offscreen component keeps its level");
  assert.equal(scheduler.onCameraSample({ ...base, visibleFor: () => false }), false);
  assert.equal(scheduler.onCameraSample({ ...base, visibleFor: () => true }), true,
    "the component coming on screen is new work");
  clock.fire(); await drain();
  assert.deepEqual(loads, ["hidden"]);
  assert.equal(scheduler.onCameraSample({ ...base, selectedFor: () => true }), true,
    "a changed selection reorders the plan");
  scheduler.dispose();
});

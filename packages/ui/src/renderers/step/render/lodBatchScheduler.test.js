import assert from "node:assert/strict";
import test from "node:test";
import { createLodScheduler } from "./lodScheduler.js";
const flush = async () => { for (let i = 0; i < 150; i++) await Promise.resolve(); };
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function clock() {
  let time = 0, id = 0; const timers = new Map();
  return { now: () => time,
    setTimeoutFn: (fn, delay = 0) => { timers.set(++id, { fn, at: time + delay }); return id; },
    clearTimeoutFn: key => timers.delete(key),
    advance(ms) { const end = time + ms;
      for (;;) { const due = [...timers].filter(([, task]) => task.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break; timers.delete(due[0]); time = due[1].at; due[1].fn(); }
      time = end;
    },
  };
}
const sample = (cameraKey = "fixed") => ({ cameraKey, camera: { kind: "perspective", fovYDeg: 45 },
  viewportHeightPx: 1000, distanceFor: () => 10000, visibleFor: () => true });
const components = (count, level = 0) => Array.from({ length: count }, (_, i) => ({ cid: String(i), diagonal: 10, level }));
function fixture(options = {}, count = 9) {
  const time = clock(), loads = [], batches = [], releases = [], leases = new Set(), discards = []; let token = 0;
  const scheduler = createLodScheduler({ ...time, debounceMs: 0, minimumLevel: 1, batchSize: 4,
    reserveLevel: () => { const value = ++token; leases.add(value); return { ok: true, token: value, bytes: 10 }; },
    releaseLevel: value => { assert.ok(leases.delete(value), "each lease released once"); releases.push(value); },
    discardLevel: cid => discards.push(cid), loadLevel: async cid => { loads.push(cid); return { cid }; },
    applyBatch: entries => { const gate = deferred(); batches.push({ entries, gate }); return gate.promise; }, ...options,
  });
  scheduler.setComponents(components(count)); scheduler.onCameraSample(sample()); time.advance(0);
  return { scheduler, time, loads, batches, releases, leases, discards };
}
async function cancel(f) {
  f.scheduler.dispose(); if (f.scheduler.snapshot().adopting) f.batches.at(-1).gate.resolve(false);
  await flush(); assert.equal(f.leases.size, 0);
}

test("nine cached CIDs adopt as 4/4/1, keeping count, levels and leases behind actual acknowledgment", async () => {
  const f = fixture(); await flush();
  assert.deepEqual(f.loads, ["0", "1", "2", "3"]); assert.equal(f.batches.length, 1);
  assert.equal(f.scheduler.snapshot().occupied, 4); assert.equal(f.scheduler.snapshot().adopting, 4);
  assert.deepEqual(f.scheduler.snapshot().levelCounts, { 0: 9 }); assert.equal(f.releases.length, 0);
  for (const size of [4, 4, 1]) { const batch = f.batches.at(-1); assert.equal(batch.entries.length, size);
    assert.equal(new Set(batch.entries.map(entry => entry.cid)).size, size); batch.gate.resolve(true); await flush(); }
  assert.deepEqual(f.batches.map(batch => batch.entries.length), [4, 4, 1]);
  assert.deepEqual(f.scheduler.snapshot().levelCounts, { 1: 9 }); assert.equal(f.scheduler.snapshot().batching.maxOccupied, 4);
  assert.equal(f.scheduler.snapshot().qualitySettled, true); await cancel(f);
});

test("size-one control uses the same preparation, measurement, publication and acknowledgment hooks", async () => {
  const phases = [], f = fixture({ batchSize: 1,
    reconcileLevel: ({ cid }) => { phases.push(`measure:${cid}`); return { ok: true }; },
    prepareLevel: (cid, _level, payload) => { phases.push(`prepare:${cid}`); return payload; },
  }, 3); await flush();
  for (let i = 0; i < 3; i++) { assert.equal(f.batches.at(-1).entries.length, 1); f.batches.at(-1).gate.resolve(true); await flush(); }
  assert.deepEqual(phases, ["measure:0", "prepare:0", "measure:1", "prepare:1", "measure:2", "prepare:2"]);
  assert.equal(f.scheduler.snapshot().batching.maxOccupied, 1); await cancel(f);
});

test("32ms deadline publishes three beside a hung carryover without starting a fifth load", async () => {
  const fourth = deferred(), loads = [], f = fixture({ loadLevel: cid => {
    loads.push(cid); return cid === "3" ? fourth.promise : Promise.resolve({ cid }); } });
  await flush(); assert.equal(f.batches.length, 0); assert.deepEqual(loads, ["0", "1", "2", "3"]);
  f.time.advance(31); await flush(); assert.equal(f.batches.length, 0);
  f.time.advance(1); await flush(); assert.equal(f.batches[0].entries.length, 3);
  assert.equal(f.scheduler.snapshot().loading, 1); assert.equal(f.scheduler.snapshot().occupied, 4);
  fourth.resolve({ cid: "3" }); await flush(); assert.deepEqual(loads, ["0", "1", "2", "3"]);
  f.time.advance(100); await flush(); assert.equal(f.batches.length, 1);
  f.batches[0].gate.resolve(true); await flush(); assert.equal(f.batches[1].entries.length, 1);
  assert.equal(f.batches[1].entries[0].cid, "3", "expired carryover deadline flushes after acknowledgment");
  f.batches[1].gate.resolve(true); await flush(); await cancel(f);
});

test("a bounded collection window coalesces serialized cached reads", async () => {
  const pending = [];
  const f = fixture({ collectionMs: 128, loadLevel: cid => {
    const read = deferred(); pending.push({ cid, read }); return read.promise;
  } }, 4);
  assert.deepEqual(pending.map(item => item.cid), ["0"]);
  for (let index = 0; index < 4; index++) {
    pending[index].read.resolve({ cid: String(index) }); await flush();
    if (index < 3) {
      assert.equal(f.batches.length, 0);
      f.time.advance(40);
    }
  }
  assert.deepEqual(pending.map(item => item.cid), ["0", "1", "2", "3"]);
  assert.equal(f.batches.length, 1);
  assert.equal(f.batches[0].entries.length, 4);
  assert.ok(f.scheduler.snapshot().batching.collectionMs <= 128);
  f.batches[0].gate.resolve(true); await flush(); await cancel(f);
});

test("temporary sibling denial flushes and retries only after a real ownership transition", async () => {
  const attempts = [], active = new Set(); let token = 0;
  const f = fixture({ reserveLevel: ({ cid }) => { attempts.push(cid);
    if (active.size >= 2) return { ok: false }; const value = ++token; active.add(value); return { ok: true, token: value };
  }, releaseLevel: value => assert.ok(active.delete(value)) }, 3);
  await flush(); assert.deepEqual(attempts, ["0", "1", "2"]); assert.equal(f.batches[0].entries.length, 2);
  assert.equal(f.scheduler.snapshot().deniedAttempts, 0); f.time.advance(1000); await flush();
  assert.deepEqual(attempts, ["0", "1", "2"]); f.batches[0].gate.resolve(true); await flush();
  assert.deepEqual(attempts, ["0", "1", "2", "2"]); f.batches[1].gate.resolve(true); await flush();
  assert.equal(active.size, 0); await cancel(f);
});

test("measured payload top-up precedes the next admission, and denied payload retries after sibling adoption", async () => {
  const active = new Set(), attempts = [], measured = [], discarded = []; let token = 0;
  const f = fixture({ reserveLevel: ({ cid }) => { attempts.push(cid); const key = ++token; active.add(key); return { ok: true, token: key, bytes: 1 }; },
    releaseLevel: key => assert.ok(active.delete(key)), discardLevel: cid => discarded.push(cid),
    reconcileLevel: ({ cid }) => { measured.push(cid); if (cid === "1" && active.size > 1) return { ok: false };
      const key = ++token; active.add(key); return { ok: true, token: key, bytes: 3 }; },
  }, 2); await flush();
  assert.deepEqual(attempts, ["0", "1"]); assert.deepEqual(measured, ["0", "1"]); assert.deepEqual(discarded, ["1"]);
  assert.equal(f.batches[0].entries.length, 1); assert.equal(f.scheduler.snapshot().deniedAttempts, 0);
  f.batches[0].gate.resolve(true); await flush(); assert.deepEqual(measured, ["0", "1", "1"]);
  f.batches[1].gate.resolve(true); await flush(); assert.equal(active.size, 0); await cancel(f);
});

test("a top-up rejection with no sibling parks without spinning", async () => {
  let measured = 0; const f = fixture({ reconcileLevel: () => { measured++; return { ok: false }; } }, 1);
  await flush(); assert.equal(measured, 1); assert.equal(f.scheduler.busy(), false);
  assert.equal(f.scheduler.snapshot().unmetTargets[0].reason, "memory-denied");
  f.time.advance(1000); await flush(); assert.equal(measured, 1); await cancel(f);
});

test("late selector preparation shares the one loader lane while a ready sibling may flush", async () => {
  const selector = deferred(), second = deferred(), order = []; let demanded = false;
  const f = fixture({ loadLevel: cid => { order.push(`load:${cid}`); return cid === "1" ? second.promise : { cid }; },
    needsPreparation: (cid, _level, payload) => cid === "0" && demanded && !payload.bundle,
    prepareLevel: (cid, _level, payload) => { order.push(`prepare:${cid}`);
      return cid === "0" && demanded && !payload.bundle ? selector.promise.then(() => ({ ...payload, bundle: {} })) : payload; },
  }, 3); await flush(); demanded = true; second.resolve({ cid: "1" }); await flush();
  assert.deepEqual(order, ["load:0", "prepare:0", "load:1", "prepare:1", "prepare:0"]);
  f.time.advance(32); await flush(); assert.deepEqual(f.batches[0].entries.map(entry => entry.cid), ["1"]);
  assert.equal(f.scheduler.snapshot().loading, 1); assert.equal(f.scheduler.snapshot().occupied, 2);
  selector.resolve(); await flush(); assert.equal(order.includes("load:2"), false);
  f.batches[0].gate.resolve(true); await flush();
  assert.ok(f.batches.at(-1).entries.find(entry => entry.cid === "0").payload.bundle); await cancel(f);
});

test("one loader failure preserves ready siblings and parks only that exact target", async () => {
  const f = fixture({ loadLevel: async cid => { if (cid === "1") throw new Error("selector read failed"); return { cid }; } }, 3);
  await flush(); assert.deepEqual(f.batches[0].entries.map(entry => entry.cid), ["0"]);
  f.batches[0].gate.resolve(true); await flush(); assert.deepEqual(f.batches[1].entries.map(entry => entry.cid), ["2"]);
  f.batches[1].gate.resolve(true); await flush(); assert.equal(f.scheduler.levelOf("1"), 0);
  assert.equal(f.scheduler.snapshot().failedLevels, 1); assert.equal(f.scheduler.snapshot().unmetTargets[0].reason, "load-failed"); await cancel(f);
});

test("model replacement cancels private carryover but holds published owners until confirmed cleanup", async () => {
  const fourth = deferred(); let signal, pending;
  const f = fixture({ loadLevel: cid => cid === "3" ? fourth.promise : { cid },
    applyBatch: (_entries, options) => { signal = options.signal; pending = deferred(); return pending.promise; },
  }); await flush(); f.time.advance(32); await flush(); assert.equal(f.scheduler.snapshot().adopting, 3);
  f.scheduler.setComponents([{ cid: "0", diagonal: 10, level: 0 }]); assert.equal(signal.aborted, true); assert.equal(f.releases.length, 0);
  fourth.resolve({ cid: "3" }); await flush(); assert.equal(f.releases.length, 1);
  pending.resolve({ status: "adopted" }); await flush(); assert.equal(f.releases.length, 4);
  assert.equal(f.scheduler.levelOf("0"), 0); await cancel(f);
});

test("pressure coarsening stays singleton and never spends unadopted savings below the floor", async () => {
  const time = clock(), batches = [], releases = []; let pressure = true;
  const scheduler = createLodScheduler({ ...time, debounceMs: 0, minimumLevel: 1, batchSize: 4,
    memoryPressure: () => pressure, reserveLevel: ({ cid }) => ({ ok: true, token: cid }), releaseLevel: cid => releases.push(cid),
    loadLevel: async cid => ({ cid }), applyBatch: entries => { const gate = deferred(); batches.push({ entries, gate }); return gate.promise; },
  }); scheduler.setComponents(components(3, 2)); scheduler.onCameraSample(sample()); time.advance(0); await flush();
  assert.equal(batches[0].entries.length, 1); assert.equal(batches[0].entries[0].level, 1); assert.equal(releases.length, 0);
  for (let i = 0; i < 3; i++) { assert.equal(batches[i].entries.length, 1); batches[i].gate.resolve(true); await flush(); }
  assert.deepEqual(scheduler.snapshot().levelCounts, { 1: 3 }); assert.equal(batches.length, 3);
  pressure = false; scheduler.onCameraSample(sample()); time.advance(0); await flush(); assert.equal(batches.length, 3); scheduler.dispose();
});

test("admitted refinements keep filling after staged bytes cross the pressure threshold", async () => {
  let pressure = false;
  const f = fixture({
    memoryPressure: () => pressure,
    reconcileLevel: () => { pressure = true; return { ok: true }; },
  }, 4);
  await flush();
  assert.deepEqual(f.loads, ["0", "1", "2", "3"]);
  assert.equal(f.batches.length, 1);
  assert.equal(f.batches[0].entries.length, 4,
    "exact per-sibling reservations, not the coarse pressure signal, bound an admitted batch");
  assert.equal(f.scheduler.snapshot().batching.sealReasons["pressure-fill-stop"], undefined);
  f.batches[0].gate.resolve(true); await flush(); await cancel(f);
});

test("an exact sibling reservation denial still flushes the admitted ready subset", async () => {
  let attempts = 0;
  const f = fixture({
    memoryPressure: () => attempts > 0,
    reserveLevel: () => ++attempts === 1 ? { ok: true, token: "first" } : { ok: false },
    releaseLevel: token => assert.equal(token, "first"),
  }, 2);
  await flush();
  assert.deepEqual(f.loads, ["0"]);
  assert.equal(f.batches.length, 1);
  assert.equal(f.batches[0].entries.length, 1);
  assert.equal(f.scheduler.snapshot().batching.sealReasons.admission, 1);
  f.batches[0].gate.resolve(true); await flush(); await cancel(f);
});

test("impossible late-selector preflight is bounded and leaves no lease or retry loop", async () => {
  let publications = 0, preparations = 0;
  const f = fixture({ prepareLevel: (_cid, _level, payload) => { preparations++; return payload; },
    applyBatch: () => { publications++; return { status: "not-ready" }; },
  }, 1); await flush(); assert.equal(publications, 2); assert.equal(preparations, 2);
  assert.equal(f.scheduler.snapshot().failedLevels, 1); assert.equal(f.scheduler.busy(), false); await cancel(f);
});

test("failure of the final late-selector owner retires its collection deadline before idle", async () => {
  const second = deferred(), late = deferred(); let demanded = false;
  const f = fixture({ loadLevel: cid => cid === "1" ? second.promise : { cid },
    needsPreparation: (cid, _level, payload) => cid === "0" && demanded && !payload.bundle,
    prepareLevel: (cid, _level, payload) => cid === "0" && demanded ? late.promise : payload,
  }, 2); await flush(); assert.equal(f.scheduler.snapshot().collectionPending, true);
  demanded = true; second.reject(new Error("other load failed")); await flush();
  late.reject(new Error("late selectors failed")); await flush();
  assert.equal(f.scheduler.snapshot().occupied, 0); assert.equal(f.scheduler.snapshot().collectionPending, false);
  f.time.advance(100); await flush(); assert.equal(f.scheduler.snapshot().collectionPending, false); await cancel(f);
});

test("cancelled late actual adoption retires leases without evicting displayed payloads or promoting levels", async () => {
  const f = fixture({}, 2); await flush(); assert.equal(f.batches[0].entries.length, 2);
  f.scheduler.setComponents(components(2));
  assert.equal(f.releases.length, 0); assert.equal(f.scheduler.snapshot().occupied, 2);
  f.batches[0].gate.resolve({ status: "retained" }); await flush();
  assert.equal(f.releases.length, 2); assert.deepEqual(f.discards, []);
  assert.deepEqual(f.scheduler.snapshot().levelCounts, { 0: 2 }); await cancel(f);
});

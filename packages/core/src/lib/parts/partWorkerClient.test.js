// The worker pool decodes stored meshes: a request carries its part's mesh bytes
// in (read on this thread, by the part's key and the row its probe answered; URL
// spelling never participates), or fails as a probe miss for its caller to answer
// by asking the host for that part.
import assert from "node:assert/strict";
import test from "node:test";

import {
  loadPartInWorker as loadWorker,
  reclaimIdlePartWorkers,
  releasePartWorkerPoolWhenIdle,
  partWorkerMemoryStats,
} from "./partWorkerClient.js";
import { createTessellationCache, isTessellationCacheProbeMissError } from "./tessellationCache.js";
import { encodeMeshFixture, partRowFor, testPartKey } from "./__tests__/meshFixtures.js";

let tessellationCache = createTessellationCache();
function setTessellationCacheProvider(provider) {
  tessellationCache.dispose();
  tessellationCache = createTessellationCache({ provider });
}

const CACHE_IDENTITY = { part: testPartKey("d") };
// One stored triangle: what a pool test's request carries when the test is not about reading it.
const ENTRY = encodeMeshFixture({
  positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
  indices: new Uint32Array([0, 1, 2]),
  faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }], edges: [],
  bounds: { min: [0, 0, 0], max: [1, 1, 0] },
}, CACHE_IDENTITY);
const ROW = partRowFor(ENTRY);
// A provider whose probe answers when the test says so, with the stored row (or none).
function waitingProvider() {
  let answer;
  const provider = {
    probeMany: (keys) => new Promise((resolve) => { answer = (found) => resolve(keys.map(() => (found ? ROW : null))); }),
    async getProbed() { return ENTRY.slice(); },
  };
  return { provider, answer: (found = true) => answer(found) };
}
const loadPartInWorker = (url, options = {}) => loadWorker(url, {
  tessellationCache, ...options,
  identity: options.identity ?? { ...CACHE_IDENTITY, tessellationEntry: ENTRY.slice() },
});

test('worker leases preserve another renderer through abort and release after the last owner', async (t) => {
  const { retainPartWorkerPool } = await import('./partWorkerClient.js');
  const previous = globalThis.Worker;
  const workers = [];
  globalThis.Worker = class {
    events = new Map(); messages = []; terminated = false;
    constructor() { workers.push(this); }
    addEventListener(type, listener) { this.events.set(type, listener); }
    postMessage(message) { this.messages.push(message); }
    terminate() { this.terminated = true; }
  };
  const releaseOne = retainPartWorkerPool();
  const releaseTwo = retainPartWorkerPool();
  t.after(() => { releaseOne(); releaseTwo(); globalThis.Worker = previous; });
  const controller = new AbortController();
  const first = loadPartInWorker('http://one.test/component.selectors.json', { signal: controller.signal });
  const second = loadPartInWorker('http://two.test/component.selectors.json');
  controller.abort();
  await assert.rejects(first, { name: 'AbortError' });
  releaseOne();
  const recipient = workers.find((worker) => worker.messages.some((message) => message.url?.includes('two.test')));
  assert.equal(recipient.terminated, false);
  const message = recipient.messages.find((message) => message.url?.includes('two.test'));
  recipient.events.get('message')({ data: { id: message.id, ok: true, meshData: { root: 'two' } } });
  assert.deepEqual((await second).meshData, { root: 'two' });
  releaseTwo();
  assert.ok(workers.every((worker) => worker.terminated));
});

test("loadPartInWorker returns null where Workers do not exist (node)", () => {
  assert.equal(loadPartInWorker("/pkg/components/abc.selectors.json"), null);
});

test("worker requests declare a bounded render/selectors capability set", async () => {
  const messages = [];
  class FakeWorker {
    constructor() { this.listeners = {}; }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      messages.push(message);
      setTimeout(() => this.listeners.message?.({
        data: {
          id: message.id,
          ok: true,
          ...(message.capabilities.render ? { meshData: { parts: [] } } : {}),
          ...(message.capabilities.selectors ? { bundle: { manifest: {}, buffers: {} } } : {}),
        },
      }), 0);
    }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const render = await loadPartInWorker("http://x/components/render.selectors.json", {
      capabilities: { render: true, selectors: false },
    });
    const selectors = await loadPartInWorker("http://x/components/selectors.selectors.json", {
      capabilities: { render: false, selectors: true },
    });
    assert.deepEqual(messages.map((message) => message.capabilities), [
      { render: true, selectors: false },
      { render: false, selectors: true },
    ]);
    assert.ok(render.meshData);
    assert.equal(render.bundle, undefined);
    assert.ok(selectors.bundle);
    assert.equal(selectors.meshData, undefined);
    assert.throws(
      () => loadPartInWorker("http://x/components/none.selectors.json", { capabilities: {} }),
      /must require render or selectors capability/,
    );
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("worker memory stats follow used slots and keep each slot's own high-water", async () => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      this.messages.push(message);
      setTimeout(() => this.listeners.message?.({
        data: { id: message.id, ok: true, meshData: { parts: [] } },
      }), 0);
    }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const first = loadPartInWorker("http://x/not-cached-big.selectors.json", {
      memoryEstimateBytes: 500,
    });
    const slotCount = created.length;
    const initial = [first];
    for (let index = 1; index < slotCount; index += 1) {
      initial.push(loadPartInWorker(`http://x/not-cached-small-${index}.selectors.json`, {
        memoryEstimateBytes: 10,
      }));
    }
    await Promise.all(initial);
    assert.deepEqual(partWorkerMemoryStats(), {
      generation: partWorkerMemoryStats().generation,
      residentSlots: slotCount,
      usedSlots: slotCount,
      residentEstimateBytes: 500 + (slotCount - 1) * 10,
    });

    // More completions rotate over the same slots. They do not invent slots or
    // apply the one large request's estimate to every worker.
    for (let index = 0; index < slotCount * 2; index += 1) {
      await loadPartInWorker(`http://x/not-cached-repeat-${index}.selectors.json`, {
        memoryEstimateBytes: 10,
      });
    }
    const afterRepeats = partWorkerMemoryStats();
    assert.equal(afterRepeats.usedSlots, slotCount);
    assert.equal(afterRepeats.residentEstimateBytes, 500 + (slotCount - 1) * 10);
    assert.equal(
      created.some((worker) => worker.messages.some((message) => Object.hasOwn(message, "memoryEstimateBytes"))),
      false,
      "process memory estimates never enter the persistent worker protocol",
    );
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("handled worker errors retain their estimate and unknown estimates use the conservative fallback", async () => {
  class FakeWorker {
    constructor() { this.listeners = {}; }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      setTimeout(() => this.listeners.message?.({
        data: { id: message.id, ok: false, error: { message: "handled failure" } },
      }), 0);
    }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    await assert.rejects(
      loadPartInWorker("http://x/not-cached-failure.selectors.json", { memoryEstimateBytes: 777 }),
      /handled failure/,
    );
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, 777);
    reclaimIdlePartWorkers();

    await assert.rejects(
      loadPartInWorker("http://x/not-cached-unknown.selectors.json"),
      /handled failure/,
    );
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, 128 * 1024 * 1024);
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("abort replacement drops the old slot charge and a stale reply cannot restore it", async () => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const warm = loadPartInWorker("http://x/not-cached-warm-memory.selectors.json", {
      memoryEstimateBytes: 400,
    });
    const slotCount = created.length;
    created[0].listeners.message({
      data: { id: created[0].messages[0].id, ok: true, meshData: { parts: [] } },
    });
    await warm;
    for (let index = 1; index < slotCount; index += 1) {
      const fill = loadPartInWorker(`http://x/not-cached-warm-fill-${index}.selectors.json`, {
        memoryEstimateBytes: 10,
      });
      const message = created[index].messages[0];
      created[index].listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: [] } },
      });
      await fill;
    }
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, 400 + (slotCount - 1) * 10);

    // Round-robin is back at slot zero, which already owns the 400-byte
    // high-water. Aborting its next request replaces that worker and must drop
    // the previous charge along with it.
    const controller = new AbortController();
    const pending = loadPartInWorker("http://x/not-cached-abort-memory.selectors.json", {
      signal: controller.signal,
      memoryEstimateBytes: 900,
    });
    const oldWorker = created[0];
    const oldMessage = oldWorker.messages.at(-1);
    controller.abort();
    await assert.rejects(pending, { name: "AbortError" });
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, (slotCount - 1) * 10);
    assert.equal(partWorkerMemoryStats().usedSlots, slotCount - 1);

    oldWorker.listeners.message({
      data: { id: oldMessage.id, ok: true, meshData: { parts: ["stale"] } },
    });
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, (slotCount - 1) * 10);
    assert.ok(created.length > partWorkerMemoryStats().residentSlots, "the assigned slot was replaced");
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("partial and full reclamation release only the terminated slots' estimates", async () => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const first = loadPartInWorker("http://x/not-cached-first-memory.selectors.json", {
      memoryEstimateBytes: 1000,
    });
    const slotCount = created.length;
    created[0].listeners.message({
      data: { id: created[0].messages[0].id, ok: true, meshData: { parts: [] } },
    });
    await first;
    for (let index = 1; index < slotCount; index += 1) {
      const request = loadPartInWorker(`http://x/not-cached-fill-${index}.selectors.json`, {
        memoryEstimateBytes: 10,
      });
      const message = created[index].messages[0];
      created[index].listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: [] } },
      });
      await request;
    }
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, 1000 + (slotCount - 1) * 10);

    const active = loadPartInWorker("http://x/not-cached-active-memory.selectors.json", {
      memoryEstimateBytes: 2000,
    });
    const activeMessage = created[0].messages.at(-1);
    const reclaimed = reclaimIdlePartWorkers();
    assert.equal(reclaimed.residentSlots, 1);
    assert.deepEqual(partWorkerMemoryStats(), {
      generation: partWorkerMemoryStats().generation,
      residentSlots: 1,
      usedSlots: 1,
      residentEstimateBytes: 1000,
    });

    created[0].listeners.message({
      data: { id: activeMessage.id, ok: true, meshData: { parts: [] } },
    });
    await active;
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, 2000);
    assert.equal(reclaimIdlePartWorkers().fullyReleased, true);
    assert.deepEqual(partWorkerMemoryStats(), {
      generation: partWorkerMemoryStats().generation,
      residentSlots: 0,
      usedSlots: 0,
      residentEstimateBytes: 0,
    });
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("reclamation terminates idle workers and the next request builds a fresh pool", async () => {
  const terminated = [];
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      // Answer on a later turn, as a real worker does.
      setTimeout(() => this.listeners.message?.({
        data: { id: message.id, ok: true, meshData: { parts: [] }, bundle: null }
      }), 0);
    }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    assert.equal(reclaimIdlePartWorkers().reclaimedSlots, 0, "nothing to release before the first request");
    const inFlight = loadPartInWorker("http://x/components/aa.selectors.json");
    assert.ok(created.length > 0, "the first request builds the pool");
    assert.equal(reclaimIdlePartWorkers().fullyReleased, false, "a request in flight keeps its isolate");
    assert.equal(terminated.length, 0, "in-flight work is never terminated");
    await inFlight;
    assert.equal(reclaimIdlePartWorkers().fullyReleased, true);
    assert.equal(terminated.length, created.length, "every worker was terminated");
    const before = created.length;
    await loadPartInWorker("http://x/components/bb.selectors.json");
    assert.ok(created.length > before, "the next request builds a fresh pool");
    reclaimIdlePartWorkers();
  } finally {
    globalThis.Worker = savedWorker;
  }
});

test("sequential refinement creates one isolate and concurrent ready work grows the pool", async () => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const finish = (worker) => {
    const message = worker.messages.at(-1);
    worker.listeners.message({ data: { id: message.id, ok: true, meshData: { parts: [] } } });
  };
  try {
    for (let index = 0; index < 8; index += 1) {
      const request = loadPartInWorker(`http://x/sequential-${index}.selectors.json`);
      assert.equal(created.length, 1);
      finish(created[0]); await request;
    }
    const first = loadPartInWorker("http://x/concurrent-first.selectors.json");
    const second = loadPartInWorker("http://x/concurrent-second.selectors.json");
    assert.equal(created.length, 2);
    finish(created[0]); finish(created[1]);
    await Promise.all([first, second]);
  } finally {
    reclaimIdlePartWorkers(); globalThis.Worker = savedWorker;
  }
});

test("reclaimIdlePartWorkers returns idle capacity without disturbing active or queued requests", async (t) => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const { provider, answer: resolveCache } = waitingProvider();
  setTessellationCacheProvider(provider);
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const first = loadPartInWorker("http://x/not-cached-first.selectors.json");
    const second = loadPartInWorker("http://x/not-cached-second.selectors.json");
    const queued = loadPartInWorker("http://x/components/cache-wait.selectors.json", {
      identity: CACHE_IDENTITY,
    });
    const initialWorkers = [...created];
    const activeWorkers = initialWorkers.filter((worker) => worker.messages.length > 0);
    assert.equal(activeWorkers.length, 2);

    const reclaimed = reclaimIdlePartWorkers();
    assert.deepEqual(reclaimed, {
      reclaimedSlots: initialWorkers.length - activeWorkers.length,
      residentSlots: activeWorkers.length,
      fullyReleased: false,
    });
    assert.equal(activeWorkers.some((worker) => terminated.includes(worker)), false);

    resolveCache();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(
      activeWorkers.some((worker) => worker.messages.some((message) => message.url.endsWith("cache-wait.selectors.json"))),
      false,
      "cache-ready work remains queued while every surviving slot is active",
    );

    const firstWorker = activeWorkers.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("not-cached-first.selectors.json")));
    const firstMessage = firstWorker.messages[0];
    firstWorker.listeners.message({
      data: { id: firstMessage.id, ok: true, meshData: { parts: ["first"] } },
    });
    const queuedMessage = firstWorker.messages.find((message) => message.url.endsWith("cache-wait.selectors.json"));
    assert.ok(queuedMessage, "a surviving slot drains queued work after its active request completes");

    const secondWorker = activeWorkers.find((worker) => worker !== firstWorker);
    const secondMessage = secondWorker.messages[0];
    secondWorker.listeners.message({
      data: { id: secondMessage.id, ok: true, meshData: { parts: ["second"] } },
    });
    firstWorker.listeners.message({
      data: { id: queuedMessage.id, ok: true, meshData: { parts: ["queued"] } },
    });
    assert.deepEqual((await first).meshData.parts, ["first"]);
    assert.deepEqual((await second).meshData.parts, ["second"]);
    assert.deepEqual((await queued).meshData.parts, ["queued"]);

    const final = reclaimIdlePartWorkers();
    assert.deepEqual(final, {
      reclaimedSlots: activeWorkers.length,
      residentSlots: 0,
      fullyReleased: true,
    });
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("idle reclamation keeps one progress slot for requests waiting on cache reads", async (t) => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const { provider, answer: resolveCache } = waitingProvider();
  setTessellationCacheProvider(provider);
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const waiting = loadPartInWorker("http://x/components/cache-only.selectors.json", {
      identity: CACHE_IDENTITY,
      memoryEstimateBytes: 73,
    });
    const reclaimed = reclaimIdlePartWorkers();
    assert.deepEqual(reclaimed, {
      reclaimedSlots: created.length - 1,
      residentSlots: 1,
      fullyReleased: false,
    });
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, 0, "a cache waiter has not used an isolate");

    resolveCache();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const survivor = created.find((worker) =>
      !terminated.includes(worker) && worker.messages.some((message) => message.url.endsWith("cache-only.selectors.json")));
    assert.ok(survivor, "the retained isolate starts work once its cache lookup settles");
    const message = survivor.messages[0];
    survivor.listeners.message({
      data: { id: message.id, ok: true, meshData: { parts: ["complete"] } },
    });
    assert.deepEqual((await waiting).meshData.parts, ["complete"]);
    assert.equal(partWorkerMemoryStats().residentEstimateBytes, 73);
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("releasePartWorkerPoolWhenIdle releases an overlapping request after it completes", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.message = message; }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const inFlight = loadPartInWorker("http://x/components/overlap.selectors.json");
    const released = releasePartWorkerPoolWhenIdle();
    assert.equal(terminated.length, 0, "in-flight work is not terminated");
    const worker = created.find((candidate) => candidate.message?.type === "loadPart");
    worker.listeners.message({
      data: { id: worker.message.id, ok: true, meshData: { parts: [] } },
    });
    await inFlight;
    assert.equal(await released, true);
    assert.equal(terminated.length, created.length, "all isolates release at idle");
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("releasePartWorkerPoolWhenIdle releases after the last request aborts", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.message = message; }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const controller = new AbortController();
  try {
    const inFlight = loadPartInWorker("http://x/components/abort.selectors.json", {
      signal: controller.signal,
    });
    const released = releasePartWorkerPoolWhenIdle();
    controller.abort();
    await assert.rejects(inFlight, { name: "AbortError" });
    assert.equal(await released, true);
    assert.equal(terminated.length, created.length, "abort drains and releases the pool");
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("an old idle-release waiter cannot terminate a replacement pool", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.message = message; }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const oldRequest = loadPartInWorker("http://x/components/old.selectors.json");
    const oldRelease = releasePartWorkerPoolWhenIdle();
    const oldWorkers = [...created];
    oldWorkers[0].listeners.error({ message: "old pool failed" });
    const replacementRequest = loadPartInWorker("http://x/components/new.selectors.json");
    const replacementWorkers = created.filter((worker) => !oldWorkers.includes(worker));

    await assert.rejects(oldRequest, /old pool failed/);
    assert.equal(await oldRelease, true, "the failed generation has released");
    assert.equal(
      replacementWorkers.some((worker) => terminated.includes(worker)),
      false,
      "the old waiter is scoped to its own generation",
    );

    const assigned = replacementWorkers.find((worker) => worker.message?.type === "loadPart");
    assigned.listeners.message({
      data: { id: assigned.message.id, ok: true, meshData: { parts: [] } },
    });
    await replacementRequest;
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("aborting synchronous work replaces only its worker and preserves unrelated and queued jobs", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const controller = new AbortController();
  try {
    const cancelled = loadPartInWorker("http://x/components/cancelled.selectors.json", {
      signal: controller.signal,
    });
    const initialWorkers = [...created];
    const poolCount = initialWorkers.length;
    const unrelated = [];
    for (let index = 1; index < poolCount; index += 1) {
      unrelated.push(loadPartInWorker(`http://x/components/keep-${index}.selectors.json`));
    }
    const queued = loadPartInWorker("http://x/components/queued.selectors.json");
    assert.equal(
      initialWorkers.reduce((sum, worker) => sum + worker.messages.length, 0),
      poolCount,
      "one job occupies each worker and excess work stays on the client queue",
    );

    const cancelledWorker = initialWorkers.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("cancelled.selectors.json")));
    controller.abort();
    await assert.rejects(cancelled, { name: "AbortError" });
    assert.ok(terminated.includes(cancelledWorker), "the blocked worker was terminated");
    assert.equal(
      initialWorkers.filter((worker) => worker !== cancelledWorker).some((worker) => terminated.includes(worker)),
      false,
      "workers running unrelated jobs survive",
    );

    const replacement = created.find((worker) => !initialWorkers.includes(worker));
    const queuedMessage = replacement.messages.find((message) => message.url.endsWith("queued.selectors.json"));
    assert.ok(queuedMessage, "the replacement immediately accepts queued work");
    // A late event already queued by the terminated worker cannot settle the
    // replacement's request because request ownership includes the slot.
    cancelledWorker.listeners.message({
      data: { id: queuedMessage.id, ok: true, meshData: { parts: ["stale"] } },
    });

    for (const worker of initialWorkers) {
      if (worker === cancelledWorker) continue;
      const message = worker.messages[0];
      worker.listeners.message({ data: { id: message.id, ok: true, meshData: { parts: [] } } });
    }
    replacement.listeners.message({
      data: { id: queuedMessage.id, ok: true, meshData: { parts: ["queued"] } },
    });
    assert.deepEqual((await queued).meshData.parts, ["queued"]);
    await Promise.all(unrelated);
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("bytes a batched read already holds are posted without a read; otherwise the stored mesh is read, and a missing one is a probe miss", async (t) => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message, transfer) { this.messages.push({ message, transfer }); }
    terminate() {}
  }
  const reads = [];
  let stored = true;
  setTessellationCacheProvider({
    async probeMany(keys) { reads.push("probe"); return keys.map(() => (stored ? ROW : null)); },
    async getProbed() { reads.push("body"); return ENTRY.slice(); },
  });
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const answer = (url) => {
    const worker = created.find((candidate) => candidate.messages.some(({ message }) => message.url === url));
    const { message, transfer } = worker.messages.find((posted) => posted.message.url === url);
    worker.listeners.message({ data: { id: message.id, ok: true, meshData: { parts: [url] } } });
    return { message, transfer };
  };
  try {
    const entry = ENTRY.slice();
    const held = loadPartInWorker("http://x/held.selectors.json", { identity: { ...CACHE_IDENTITY, tessellationEntry: entry } });
    await new Promise((resolve) => setTimeout(resolve, 0));
    const posted = answer("http://x/held.selectors.json");
    await held;
    assert.equal(posted.message.cachedEntry, entry);
    assert.equal(posted.message.part, CACHE_IDENTITY.part, "the worker reads it as its part's mesh");
    assert.deepEqual(posted.transfer, [entry.buffer], "its own buffer travels to the worker");
    assert.deepEqual(reads, [], "a held body is not read again");

    const unread = loadPartInWorker("http://x/unread.selectors.json", { identity: CACHE_IDENTITY });
    await new Promise((resolve) => setTimeout(resolve, 0));
    const read = answer("http://x/unread.selectors.json");
    await unread;
    assert.deepEqual(reads, ["probe", "body"], "one with no body probes and reads it");
    assert.deepEqual(read.message.cachedEntry, ENTRY);

    stored = false;
    await assert.rejects(loadPartInWorker("http://x/missing.selectors.json", { identity: CACHE_IDENTITY }),
      isTessellationCacheProbeMissError, "a mesh the store does not hold is the caller's to ask for");
    assert.equal(created.flatMap((worker) => worker.messages).some(({ message }) => message.url === "http://x/missing.selectors.json"), false,
      "nothing was posted for it");
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("a pending warm-cache lookup does not occupy a worker slot", async (t) => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() {}
  }
  const { provider, answer: resolveCache } = waitingProvider();
  setTessellationCacheProvider(provider);
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const awaitingCache = loadPartInWorker("http://x/components/cached.selectors.json", {
      identity: CACHE_IDENTITY,
    });
    assert.equal(created.some((worker) => worker.messages.length > 0), false);
    const ready = loadPartInWorker("http://x/held.selectors.json");
    const readyWorker = created.find((worker) => worker.messages.length > 0);
    assert.ok(readyWorker, "ready work dispatches while the cache lookup waits");
    const readyMessage = readyWorker.messages[0];
    readyWorker.listeners.message({
      data: { id: readyMessage.id, ok: true, meshData: { parts: ["ready"] } },
    });
    assert.deepEqual((await ready).meshData.parts, ["ready"]);

    resolveCache();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const cachedWorker = created.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("cached.selectors.json")));
    const cachedMessage = cachedWorker.messages.find((message) => message.url.endsWith("cached.selectors.json"));
    cachedWorker.listeners.message({
      data: { id: cachedMessage.id, ok: true, meshData: { parts: ["cached"] } },
    });
    assert.deepEqual((await awaitingCache).meshData.parts, ["cached"]);
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("a worker runtime error replaces one slot without rejecting unrelated work", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const failed = loadPartInWorker("http://x/components/fail.selectors.json");
    const kept = loadPartInWorker("http://x/components/keep.selectors.json");
    const failedWorker = created.find((worker) => worker.messages[0]?.url.endsWith("fail.selectors.json"));
    const keptWorker = created.find((worker) => worker.messages[0]?.url.endsWith("keep.selectors.json"));
    const initialWorkerCount = created.length;
    failedWorker.listeners.error({ message: "worker crashed" });
    await assert.rejects(failed, /worker crashed/);
    assert.ok(terminated.includes(failedWorker));
    assert.equal(terminated.includes(keptWorker), false);
    const keptMessage = keptWorker.messages[0];
    keptWorker.listeners.message({
      data: { id: keptMessage.id, ok: true, meshData: { parts: ["kept"] } },
    });
    assert.deepEqual((await kept).meshData.parts, ["kept"]);
    assert.equal(created.length, initialWorkerCount + 1, "only the failed slot was replaced");
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("a failed replacement constructor preserves surviving workers and their queue", async () => {
  const created = [];
  const terminated = [];
  let failNextConstructor = false;
  class FakeWorker {
    constructor() {
      if (failNextConstructor) {
        failNextConstructor = false;
        throw new Error("replacement unavailable");
      }
      this.listeners = {};
      this.messages = [];
      created.push(this);
    }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const controller = new AbortController();
  try {
    const cancelled = loadPartInWorker("http://x/components/cancel-constructor.selectors.json", {
      signal: controller.signal,
    });
    const survivors = [loadPartInWorker("http://x/components/survivor-1.selectors.json")];
    const initialWorkers = [...created];
    const poolCount = initialWorkers.length;
    reclaimIdlePartWorkers(); // constrain this generation to the two live slots
    const queued = loadPartInWorker("http://x/components/after-constructor-failure.selectors.json");
    failNextConstructor = true;
    controller.abort();
    await assert.rejects(cancelled, { name: "AbortError" });

    const liveWorkers = initialWorkers.filter((worker) => !terminated.includes(worker));
    assert.equal(liveWorkers.length, poolCount - 1, "only the cancelled slot was lost");
    const firstLive = liveWorkers[0];
    const firstMessage = firstLive.messages[0];
    firstLive.listeners.message({
      data: { id: firstMessage.id, ok: true, meshData: { parts: ["survivor"] } },
    });
    const queuedMessage = firstLive.messages.find((message) =>
      message.url.endsWith("after-constructor-failure.selectors.json"));
    assert.ok(queuedMessage, "a surviving slot continues draining queued jobs");
    firstLive.listeners.message({
      data: { id: queuedMessage.id, ok: true, meshData: { parts: ["queued"] } },
    });
    for (const worker of liveWorkers.slice(1)) {
      const message = worker.messages[0];
      worker.listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: ["survivor"] } },
      });
    }
    assert.deepEqual((await queued).meshData.parts, ["queued"]);
    await Promise.all(survivors);
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("synchronous post failures drain a queued batch without recursive dispatch", async () => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      if (message.url.includes("post-failure-")) throw new Error(`post failed ${message.id}`);
      this.messages.push(message);
    }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const first = loadPartInWorker("http://x/components/blocker.selectors.json");
    const initialWorkers = [...created];
    const blockers = [first];
    for (let index = 1; index < initialWorkers.length; index += 1) {
      blockers.push(loadPartInWorker(`http://x/components/blocker-${index}.selectors.json`));
    }
    const failed = Array.from({ length: 40 }, (_, index) =>
      loadPartInWorker(`http://x/components/post-failure-${index}.selectors.json`));
    const final = loadPartInWorker("http://x/components/final-good.selectors.json");

    const firstMessage = initialWorkers[0].messages[0];
    initialWorkers[0].listeners.message({
      data: { id: firstMessage.id, ok: true, meshData: { parts: ["blocker"] } },
    });
    const failures = await Promise.allSettled(failed);
    assert.ok(failures.every((result) => result.status === "rejected"));
    const finalWorker = created.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("final-good.selectors.json")));
    const finalMessage = finalWorker.messages.find((message) => message.url.endsWith("final-good.selectors.json"));
    assert.ok(finalMessage, "the iterative drain reaches later good work");
    finalWorker.listeners.message({
      data: { id: finalMessage.id, ok: true, meshData: { parts: ["final"] } },
    });
    for (const worker of initialWorkers.slice(1)) {
      const message = worker.messages[0];
      worker.listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: ["blocker"] } },
      });
    }
    assert.deepEqual((await final).meshData.parts, ["final"]);
    await Promise.all(blockers);
  } finally {
    reclaimIdlePartWorkers();
    globalThis.Worker = savedWorker;
  }
});

test('custom resource transfers begin only when a worker slot is reserved', async t => {
  const previous = globalThis.Worker;
  const workers = [], tickets = [];
  globalThis.Worker = class {
    listeners = {};
    constructor() { workers.push(this); }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    postMessage(message) { queueMicrotask(() => this.listeners.message({data:{id:message.id,ok:true,meshData:{}}})); }
    terminate() {}
  };
  t.after(() => { reclaimIdlePartWorkers(); globalThis.Worker=previous; });
  const resources = {workerTicket: () => new Promise(resolve => tickets.push(resolve))};
  const pending = Array.from({length:20}, (_,index) => loadPartInWorker(`private:${index}`, {resources}));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(tickets.length, workers.length);
  assert.ok(tickets.length < pending.length, 'queued components do not eagerly retain transferred bytes');
  let resolved = 0;
  while (resolved < pending.length) {
    for (const finish of tickets.splice(0)) { resolved++; finish({kind:'bytes',bytes:new ArrayBuffer(4)}); }
    await new Promise(resolve => setImmediate(resolve));
  }
  await Promise.all(pending);
});

// A selectors read names its part's selector table; one with an empty URL (nothing names the table
// yet) fails first. That used to hand the worker a ticket for "", which read the page's own
// address: in the CAD app, a cad_http GET of its sandbox page, answered 404 (43 per hypercar open).
test("selectors with no selector table URL fail as not ready, fetching no ticket", async (t) => {
  const created = [];
  class FakeWorker {
    constructor() { this.messages = []; created.push(this); }
    addEventListener() {}
    postMessage(message) { this.messages.push(message); }
    terminate() {}
  }
  setTessellationCacheProvider({ async probeMany(keys) { return keys.map(() => ROW); }, async getProbed() { return ENTRY.slice(); } });
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  t.after(() => { reclaimIdlePartWorkers(); globalThis.Worker = savedWorker; setTessellationCacheProvider(null); });
  const tickets = [];
  const resources = { workerTicket: (url) => { tickets.push(url); return Promise.resolve({ kind: "url", url }); } };
  await assert.rejects(loadPartInWorker("", { resources, identity: CACHE_IDENTITY }), /not ready/);
  assert.deepEqual(tickets, [], "no ticket for an empty URL");
  assert.deepEqual(created.flatMap((worker) => worker.messages), [], "no worker was asked");
});

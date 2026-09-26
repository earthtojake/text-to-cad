// Worker cache reuse requires the backend-prepared surface input and the exact
// resolved surface object. URL spelling never participates in that identity.
import assert from "node:assert/strict";
import test from "node:test";

import {
  loadSurfComponentInWorker as loadWorker,
  reclaimIdleSurfWorkers,
  releaseSurfWorkerPoolWhenIdle,
  surfWorkerMemoryStats,
} from "./surfWorkerClient.js";
import { createTessellationCache } from "./tessellationCache.js";

let tessellationCache = createTessellationCache();
function setTessellationCacheProvider(provider) {
  tessellationCache.dispose();
  tessellationCache = createTessellationCache({ provider });
}
const loadSurfComponentInWorker = (url, options = {}) => loadWorker(url, { tessellationCache, ...options });

const CACHE_IDENTITY = {
  surfaceInput: "d".repeat(64),
  surfaceObject: "e".repeat(64),
};

test('worker leases preserve another renderer through abort and release after the last owner', async (t) => {
  const { retainSurfWorkerPool } = await import('./surfWorkerClient.js');
  const previous = globalThis.Worker;
  const workers = [];
  globalThis.Worker = class {
    events = new Map(); messages = []; terminated = false;
    constructor() { workers.push(this); }
    addEventListener(type, listener) { this.events.set(type, listener); }
    postMessage(message) { this.messages.push(message); }
    terminate() { this.terminated = true; }
  };
  const releaseOne = retainSurfWorkerPool();
  const releaseTwo = retainSurfWorkerPool();
  t.after(() => { releaseOne(); releaseTwo(); globalThis.Worker = previous; });
  const controller = new AbortController();
  const first = loadSurfComponentInWorker('http://one.test/component.surf', { signal: controller.signal });
  const second = loadSurfComponentInWorker('http://two.test/component.surf');
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

test("loadSurfComponentInWorker returns null where Workers do not exist (node)", () => {
  assert.equal(loadSurfComponentInWorker("/pkg/components/abc.surf"), null);
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
    const render = await loadSurfComponentInWorker("http://x/components/render.surf", {
      capabilities: { render: true, selectors: false },
    });
    const selectors = await loadSurfComponentInWorker("http://x/components/selectors.surf", {
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
      () => loadSurfComponentInWorker("http://x/components/none.surf", { capabilities: {} }),
      /must require render or selectors capability/,
    );
  } finally {
    reclaimIdleSurfWorkers();
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
    const first = loadSurfComponentInWorker("http://x/not-cached-big.surf", {
      memoryEstimateBytes: 500,
    });
    const slotCount = created.length;
    const initial = [first];
    for (let index = 1; index < slotCount; index += 1) {
      initial.push(loadSurfComponentInWorker(`http://x/not-cached-small-${index}.surf`, {
        memoryEstimateBytes: 10,
      }));
    }
    await Promise.all(initial);
    assert.deepEqual(surfWorkerMemoryStats(), {
      generation: surfWorkerMemoryStats().generation,
      residentSlots: slotCount,
      usedSlots: slotCount,
      residentEstimateBytes: 500 + (slotCount - 1) * 10,
    });

    // More completions rotate over the same slots. They do not invent slots or
    // apply the one large request's estimate to every worker.
    for (let index = 0; index < slotCount * 2; index += 1) {
      await loadSurfComponentInWorker(`http://x/not-cached-repeat-${index}.surf`, {
        memoryEstimateBytes: 10,
      });
    }
    const afterRepeats = surfWorkerMemoryStats();
    assert.equal(afterRepeats.usedSlots, slotCount);
    assert.equal(afterRepeats.residentEstimateBytes, 500 + (slotCount - 1) * 10);
    assert.equal(
      created.some((worker) => worker.messages.some((message) => Object.hasOwn(message, "memoryEstimateBytes"))),
      false,
      "process memory estimates never enter the persistent worker protocol",
    );
  } finally {
    reclaimIdleSurfWorkers();
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
      loadSurfComponentInWorker("http://x/not-cached-failure.surf", { memoryEstimateBytes: 777 }),
      /handled failure/,
    );
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 777);
    reclaimIdleSurfWorkers();

    await assert.rejects(
      loadSurfComponentInWorker("http://x/not-cached-unknown.surf"),
      /handled failure/,
    );
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 128 * 1024 * 1024);
  } finally {
    reclaimIdleSurfWorkers();
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
    const warm = loadSurfComponentInWorker("http://x/not-cached-warm-memory.surf", {
      memoryEstimateBytes: 400,
    });
    const slotCount = created.length;
    created[0].listeners.message({
      data: { id: created[0].messages[0].id, ok: true, meshData: { parts: [] } },
    });
    await warm;
    for (let index = 1; index < slotCount; index += 1) {
      const fill = loadSurfComponentInWorker(`http://x/not-cached-warm-fill-${index}.surf`, {
        memoryEstimateBytes: 10,
      });
      const message = created[index].messages[0];
      created[index].listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: [] } },
      });
      await fill;
    }
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 400 + (slotCount - 1) * 10);

    // Round-robin is back at slot zero, which already owns the 400-byte
    // high-water. Aborting its next request replaces that worker and must drop
    // the previous charge along with it.
    const controller = new AbortController();
    const pending = loadSurfComponentInWorker("http://x/not-cached-abort-memory.surf", {
      signal: controller.signal,
      memoryEstimateBytes: 900,
    });
    const oldWorker = created[0];
    const oldMessage = oldWorker.messages.at(-1);
    controller.abort();
    await assert.rejects(pending, { name: "AbortError" });
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, (slotCount - 1) * 10);
    assert.equal(surfWorkerMemoryStats().usedSlots, slotCount - 1);

    oldWorker.listeners.message({
      data: { id: oldMessage.id, ok: true, meshData: { parts: ["stale"] } },
    });
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, (slotCount - 1) * 10);
    assert.ok(created.length > surfWorkerMemoryStats().residentSlots, "the assigned slot was replaced");
  } finally {
    reclaimIdleSurfWorkers();
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
    const first = loadSurfComponentInWorker("http://x/not-cached-first-memory.surf", {
      memoryEstimateBytes: 1000,
    });
    const slotCount = created.length;
    created[0].listeners.message({
      data: { id: created[0].messages[0].id, ok: true, meshData: { parts: [] } },
    });
    await first;
    for (let index = 1; index < slotCount; index += 1) {
      const request = loadSurfComponentInWorker(`http://x/not-cached-fill-${index}.surf`, {
        memoryEstimateBytes: 10,
      });
      const message = created[index].messages[0];
      created[index].listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: [] } },
      });
      await request;
    }
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 1000 + (slotCount - 1) * 10);

    const active = loadSurfComponentInWorker("http://x/not-cached-active-memory.surf", {
      memoryEstimateBytes: 2000,
    });
    const activeMessage = created[0].messages.at(-1);
    const reclaimed = reclaimIdleSurfWorkers();
    assert.equal(reclaimed.residentSlots, 1);
    assert.deepEqual(surfWorkerMemoryStats(), {
      generation: surfWorkerMemoryStats().generation,
      residentSlots: 1,
      usedSlots: 1,
      residentEstimateBytes: 1000,
    });

    created[0].listeners.message({
      data: { id: activeMessage.id, ok: true, meshData: { parts: [] } },
    });
    await active;
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 2000);
    assert.equal(reclaimIdleSurfWorkers().fullyReleased, true);
    assert.deepEqual(surfWorkerMemoryStats(), {
      generation: surfWorkerMemoryStats().generation,
      residentSlots: 0,
      usedSlots: 0,
      residentEstimateBytes: 0,
    });
  } finally {
    reclaimIdleSurfWorkers();
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
    assert.equal(reclaimIdleSurfWorkers().reclaimedSlots, 0, "nothing to release before the first request");
    const inFlight = loadSurfComponentInWorker("http://x/components/aa.surf");
    assert.ok(created.length > 0, "the first request builds the pool");
    assert.equal(reclaimIdleSurfWorkers().fullyReleased, false, "a request in flight keeps its isolate");
    assert.equal(terminated.length, 0, "in-flight work is never terminated");
    await inFlight;
    assert.equal(reclaimIdleSurfWorkers().fullyReleased, true);
    assert.equal(terminated.length, created.length, "every worker was terminated");
    const before = created.length;
    await loadSurfComponentInWorker("http://x/components/bb.surf");
    assert.ok(created.length > before, "the next request builds a fresh pool");
    reclaimIdleSurfWorkers();
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
      const request = loadSurfComponentInWorker(`http://x/sequential-${index}.surf`);
      assert.equal(created.length, 1);
      finish(created[0]); await request;
    }
    const first = loadSurfComponentInWorker("http://x/concurrent-first.surf");
    const second = loadSurfComponentInWorker("http://x/concurrent-second.surf");
    assert.equal(created.length, 2);
    finish(created[0]); finish(created[1]);
    await Promise.all([first, second]);
  } finally {
    reclaimIdleSurfWorkers(); globalThis.Worker = savedWorker;
  }
});

test("reclaimIdleSurfWorkers returns idle capacity without disturbing active or queued requests", async (t) => {
  const created = [];
  const terminated = [];
  let resolveCache;
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  setTessellationCacheProvider({
    probeMany: () => new Promise((resolve) => { resolveCache = resolve; }),
    async getProbed() { return null; },
  });
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const first = loadSurfComponentInWorker("http://x/not-cached-first.surf");
    const second = loadSurfComponentInWorker("http://x/not-cached-second.surf");
    const queued = loadSurfComponentInWorker("http://x/components/cache-wait.surf", {
      identity: CACHE_IDENTITY,
    });
    const initialWorkers = [...created];
    const activeWorkers = initialWorkers.filter((worker) => worker.messages.length > 0);
    assert.equal(activeWorkers.length, 2);

    const reclaimed = reclaimIdleSurfWorkers();
    assert.deepEqual(reclaimed, {
      reclaimedSlots: initialWorkers.length - activeWorkers.length,
      residentSlots: activeWorkers.length,
      fullyReleased: false,
    });
    assert.equal(activeWorkers.some((worker) => terminated.includes(worker)), false);

    resolveCache(null);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(
      activeWorkers.some((worker) => worker.messages.some((message) => message.url.endsWith("cache-wait.surf"))),
      false,
      "cache-ready work remains queued while every surviving slot is active",
    );

    const firstWorker = activeWorkers.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("not-cached-first.surf")));
    const firstMessage = firstWorker.messages[0];
    firstWorker.listeners.message({
      data: { id: firstMessage.id, ok: true, meshData: { parts: ["first"] } },
    });
    const queuedMessage = firstWorker.messages.find((message) => message.url.endsWith("cache-wait.surf"));
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

    const final = reclaimIdleSurfWorkers();
    assert.deepEqual(final, {
      reclaimedSlots: activeWorkers.length,
      residentSlots: 0,
      fullyReleased: true,
    });
  } finally {
    reclaimIdleSurfWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("idle reclamation keeps one progress slot for requests waiting on cache reads", async (t) => {
  const created = [];
  const terminated = [];
  let resolveCache;
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  setTessellationCacheProvider({
    probeMany: () => new Promise((resolve) => { resolveCache = resolve; }),
    async getProbed() { return null; },
  });
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const waiting = loadSurfComponentInWorker("http://x/components/cache-only.surf", {
      identity: CACHE_IDENTITY,
      memoryEstimateBytes: 73,
    });
    const reclaimed = reclaimIdleSurfWorkers();
    assert.deepEqual(reclaimed, {
      reclaimedSlots: created.length - 1,
      residentSlots: 1,
      fullyReleased: false,
    });
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 0, "a cache waiter has not used an isolate");

    resolveCache(null);
    await new Promise((resolve) => setTimeout(resolve, 0));
    const survivor = created.find((worker) =>
      !terminated.includes(worker) && worker.messages.some((message) => message.url.endsWith("cache-only.surf")));
    assert.ok(survivor, "the retained isolate starts work once its cache lookup settles");
    const message = survivor.messages[0];
    survivor.listeners.message({
      data: { id: message.id, ok: true, meshData: { parts: ["complete"] } },
    });
    assert.deepEqual((await waiting).meshData.parts, ["complete"]);
    assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 73);
  } finally {
    reclaimIdleSurfWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("releaseSurfWorkerPoolWhenIdle releases an overlapping request after it completes", async () => {
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
    const inFlight = loadSurfComponentInWorker("http://x/components/overlap.surf");
    const released = releaseSurfWorkerPoolWhenIdle();
    assert.equal(terminated.length, 0, "in-flight work is not terminated");
    const worker = created.find((candidate) => candidate.message?.type === "loadSurf");
    worker.listeners.message({
      data: { id: worker.message.id, ok: true, meshData: { parts: [] } },
    });
    await inFlight;
    assert.equal(await released, true);
    assert.equal(terminated.length, created.length, "all isolates release at idle");
  } finally {
    reclaimIdleSurfWorkers();
    globalThis.Worker = savedWorker;
  }
});

test("releaseSurfWorkerPoolWhenIdle releases after the last request aborts", async () => {
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
    const inFlight = loadSurfComponentInWorker("http://x/components/abort.surf", {
      signal: controller.signal,
    });
    const released = releaseSurfWorkerPoolWhenIdle();
    controller.abort();
    await assert.rejects(inFlight, { name: "AbortError" });
    assert.equal(await released, true);
    assert.equal(terminated.length, created.length, "abort drains and releases the pool");
  } finally {
    reclaimIdleSurfWorkers();
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
    const oldRequest = loadSurfComponentInWorker("http://x/components/old.surf");
    const oldRelease = releaseSurfWorkerPoolWhenIdle();
    const oldWorkers = [...created];
    oldWorkers[0].listeners.error({ message: "old pool failed" });
    const replacementRequest = loadSurfComponentInWorker("http://x/components/new.surf");
    const replacementWorkers = created.filter((worker) => !oldWorkers.includes(worker));

    await assert.rejects(oldRequest, /old pool failed/);
    assert.equal(await oldRelease, true, "the failed generation has released");
    assert.equal(
      replacementWorkers.some((worker) => terminated.includes(worker)),
      false,
      "the old waiter is scoped to its own generation",
    );

    const assigned = replacementWorkers.find((worker) => worker.message?.type === "loadSurf");
    assigned.listeners.message({
      data: { id: assigned.message.id, ok: true, meshData: { parts: [] } },
    });
    await replacementRequest;
  } finally {
    reclaimIdleSurfWorkers();
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
    const cancelled = loadSurfComponentInWorker("http://x/components/cancelled.surf", {
      signal: controller.signal,
    });
    const initialWorkers = [...created];
    const poolCount = initialWorkers.length;
    const unrelated = [];
    for (let index = 1; index < poolCount; index += 1) {
      unrelated.push(loadSurfComponentInWorker(`http://x/components/keep-${index}.surf`));
    }
    const queued = loadSurfComponentInWorker("http://x/components/queued.surf");
    assert.equal(
      initialWorkers.reduce((sum, worker) => sum + worker.messages.length, 0),
      poolCount,
      "one job occupies each worker and excess work stays on the client queue",
    );

    const cancelledWorker = initialWorkers.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("cancelled.surf")));
    controller.abort();
    await assert.rejects(cancelled, { name: "AbortError" });
    assert.ok(terminated.includes(cancelledWorker), "the blocked worker was terminated");
    assert.equal(
      initialWorkers.filter((worker) => worker !== cancelledWorker).some((worker) => terminated.includes(worker)),
      false,
      "workers running unrelated jobs survive",
    );

    const replacement = created.find((worker) => !initialWorkers.includes(worker));
    const queuedMessage = replacement.messages.find((message) => message.url.endsWith("queued.surf"));
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
    reclaimIdleSurfWorkers();
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
  let resolveCache;
  setTessellationCacheProvider({
    probeMany: () => new Promise((resolve) => { resolveCache = resolve; }),
    async getProbed() { return null; },
    async put() {},
  });
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const awaitingCache = loadSurfComponentInWorker("http://x/components/cached.surf", {
      identity: CACHE_IDENTITY,
    });
    assert.equal(created.some((worker) => worker.messages.length > 0), false);
    const ready = loadSurfComponentInWorker("http://x/not-content-addressed.surf");
    const readyWorker = created.find((worker) => worker.messages.length > 0);
    assert.ok(readyWorker, "ready work dispatches while the cache lookup waits");
    const readyMessage = readyWorker.messages[0];
    readyWorker.listeners.message({
      data: { id: readyMessage.id, ok: true, meshData: { parts: ["ready"] } },
    });
    assert.deepEqual((await ready).meshData.parts, ["ready"]);

    resolveCache(new Map());
    await new Promise((resolve) => setTimeout(resolve, 0));
    const cachedWorker = created.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("cached.surf")));
    const cachedMessage = cachedWorker.messages.find((message) => message.url.endsWith("cached.surf"));
    cachedWorker.listeners.message({
      data: { id: cachedMessage.id, ok: true, meshData: { parts: ["cached"] } },
    });
    assert.deepEqual((await awaitingCache).meshData.parts, ["cached"]);
  } finally {
    reclaimIdleSurfWorkers();
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
    const failed = loadSurfComponentInWorker("http://x/components/fail.surf");
    const kept = loadSurfComponentInWorker("http://x/components/keep.surf");
    const failedWorker = created.find((worker) => worker.messages[0]?.url.endsWith("fail.surf"));
    const keptWorker = created.find((worker) => worker.messages[0]?.url.endsWith("keep.surf"));
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
    reclaimIdleSurfWorkers();
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
    const cancelled = loadSurfComponentInWorker("http://x/components/cancel-constructor.surf", {
      signal: controller.signal,
    });
    const survivors = [loadSurfComponentInWorker("http://x/components/survivor-1.surf")];
    const initialWorkers = [...created];
    const poolCount = initialWorkers.length;
    reclaimIdleSurfWorkers(); // constrain this generation to the two live slots
    const queued = loadSurfComponentInWorker("http://x/components/after-constructor-failure.surf");
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
      message.url.endsWith("after-constructor-failure.surf"));
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
    reclaimIdleSurfWorkers();
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
    const first = loadSurfComponentInWorker("http://x/components/blocker.surf");
    const initialWorkers = [...created];
    const blockers = [first];
    for (let index = 1; index < initialWorkers.length; index += 1) {
      blockers.push(loadSurfComponentInWorker(`http://x/components/blocker-${index}.surf`));
    }
    const failed = Array.from({ length: 40 }, (_, index) =>
      loadSurfComponentInWorker(`http://x/components/post-failure-${index}.surf`));
    const final = loadSurfComponentInWorker("http://x/components/final-good.surf");

    const firstMessage = initialWorkers[0].messages[0];
    initialWorkers[0].listeners.message({
      data: { id: firstMessage.id, ok: true, meshData: { parts: ["blocker"] } },
    });
    const failures = await Promise.allSettled(failed);
    assert.ok(failures.every((result) => result.status === "rejected"));
    const finalWorker = created.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("final-good.surf")));
    const finalMessage = finalWorker.messages.find((message) => message.url.endsWith("final-good.surf"));
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
    reclaimIdleSurfWorkers();
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
  t.after(() => { reclaimIdleSurfWorkers(); globalThis.Worker=previous; });
  const resources = {workerTicket: () => new Promise(resolve => tickets.push(resolve))};
  const pending = Array.from({length:20}, (_,index) => loadSurfComponentInWorker(`private:${index}`, {resources}));
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

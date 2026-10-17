import assert from "node:assert/strict";
import test from "node:test";

import {
  gitLfsPointerDetailsFromBuffer,
  loadRender3Mf,
  loadRenderArrayBuffer,
  loadRenderGlb,
  loadRenderJson,
  loadRenderRobot,
  loadRenderPart as loadPart,
  loadRenderPartSelectorBundle as loadPartSelectors,
  peekRenderJson,
  peekRenderRobot,
  peekRenderPart,
  ROBOT_PAYLOAD_SCHEMA_VERSION,
  renderAssetCacheStats,
  reclaimIdlePartWorkers,
  releasePartWorkers,
  partWorkerMemoryStats,
  configurePartLeash
} from "./renderAssetClient.js";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  renderAssetSourceScopeForJob,
  setRenderAssetSourceScope
} from "./renderAssetSourceScope.js";
import {
  isTessellationCacheProbeMissError,
  createTessellationCache,
  partSelectorsPath,
} from "./parts/tessellationCache.js";
import { everyKeyMeshProvider, partRowFor, selectorTableFixture } from "./parts/__tests__/meshFixtures.js";

// The part store every part load reads: it holds the gear's mesh for any part asked.
let meshStore = everyKeyMeshProvider();
let tessellationCache = createTessellationCache({ provider: meshStore });
function setTessellationCacheProvider(provider) {
  tessellationCache.dispose();
  meshStore = provider || everyKeyMeshProvider();
  tessellationCache = createTessellationCache({ provider: meshStore });
}

// What a page loads the part `name` stands for by: its key and the row the store's probe answers
// for it, and its selector table's URL, bound to that row.
async function partLoad(name) {
  const part = `${createHash("sha256").update(`render-client-test:${name}`).digest("hex")}-v1`;
  const [row] = await meshStore.probeMany([part]);
  return { identity: { part, tessellationProbe: row }, selectorsUrl: `https://cache.test${partSelectorsPath(row)}` };
}
const loadRenderPart = async (name, options = {}) => loadPart({
  identity: (await partLoad(name)).identity, tessellationCache, ...options,
});
const loadRenderPartSelectorBundle = async (name, options = {}) => {
  const { identity, selectorsUrl } = await partLoad(name);
  return loadPartSelectors(selectorsUrl, { identity, tessellationCache, ...options });
};
const sunGearTable = () => {
  const bytes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "parts/fixtures/sun_gear.selectors.json"));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
};

function abortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

function gitLfsPointerBuffer({ oid = "a".repeat(64), size = 12345 } = {}) {
  return Buffer.from([
    "version https://git-lfs.github.com/spec/v1",
    `oid sha256:${oid}`,
    `size ${size}`,
    ""
  ].join("\n"));
}

test("abortable loads do not reuse a stale pending cache entry", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  const url = `/asset-${Date.now()}-${Math.random()}.json`;

  globalThis.fetch = async (requestUrl, { signal } = {}) => new Promise((resolve, reject) => {
    const request = { requestUrl, resolve, reject, signal };
    requests.push(request);
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    signal?.addEventListener("abort", () => reject(abortError()), { once: true });
  });

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const firstController = new AbortController();
  const firstLoad = loadRenderJson(url, { signal: firstController.signal });
  assert.equal(requests.length, 1);

  firstController.abort();

  const secondController = new AbortController();
  const secondLoad = loadRenderJson(url, { signal: secondController.signal });
  assert.equal(requests.length, 2);

  requests[1].resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));

  await assert.rejects(firstLoad, { name: "AbortError" });
  assert.deepEqual(await secondLoad, { ok: true });
});

test("array buffer loads share pending fetches while aborting only the consumer", async (t) => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  const url = `/asset-${Date.now()}-${Math.random()}.glb`;
  const payload = new Uint8Array([1, 2, 3, 4]).buffer;

  globalThis.fetch = async (requestUrl) => new Promise((resolve) => {
    requests.push({ requestUrl, resolve });
  });

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const firstController = new AbortController();
  const secondController = new AbortController();
  const firstLoad = loadRenderArrayBuffer(url, { signal: firstController.signal });
  const secondLoad = loadRenderArrayBuffer(url, { signal: secondController.signal });
  assert.equal(requests.length, 1);

  firstController.abort();
  requests[0].resolve(new Response(payload, { status: 200 }));

  await assert.rejects(firstLoad, { name: "AbortError" });
  assert.deepEqual([...new Uint8Array(await secondLoad)], [1, 2, 3, 4]);
});

test("Git LFS pointer stubs are detected before mesh parsing", async (t) => {
  const originalFetch = globalThis.fetch;
  const oid = "b".repeat(64);
  const pointer = gitLfsPointerBuffer({ oid, size: 24992 });
  const glbUrl = `/asset-${Date.now()}-${Math.random()}.glb`;
  const threeMfUrl = `/asset-${Date.now()}-${Math.random()}.3mf`;

  assert.deepEqual(gitLfsPointerDetailsFromBuffer(pointer.buffer.slice(pointer.byteOffset, pointer.byteOffset + pointer.byteLength)), {
    oid,
    size: 24992,
  });

  globalThis.fetch = async (requestUrl) => {
    assert.ok([glbUrl, threeMfUrl].includes(String(requestUrl)));
    return new Response(pointer, { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await assert.rejects(
    loadRenderGlb(glbUrl),
    /GLB render asset is a Git LFS pointer, not downloaded mesh data/
  );
  await assert.rejects(
    loadRender3Mf(threeMfUrl),
    /3MF render asset is a Git LFS pointer, not downloaded mesh data/
  );
});

test("a robot payload loads through the render cache, by file and revision, and only at this build's schema", async () => {
  const file = `/robots/arm-${Date.now()}-${Math.random()}.urdf`;
  let calls = 0;
  const client = { robot: async (asked) => { calls += 1; assert.equal(asked, file); return { schemaVersion: ROBOT_PAYLOAD_SCHEMA_VERSION, kind: "urdf", articulation: {}, visuals: [] }; } };
  const first = await loadRenderRobot(file, { client, revision: "r1" });
  const second = await loadRenderRobot(file, { client, revision: "r1" });
  assert.equal(second, first);
  assert.equal(peekRenderRobot(file, { revision: "r1" }), first);
  assert.equal(peekRenderRobot(file, { revision: "r2" }), null, "a new revision of the file is read again");
  await loadRenderRobot(file, { client, revision: "r2" });
  assert.equal(calls, 2);
  const stale = { robot: async () => ({ schemaVersion: ROBOT_PAYLOAD_SCHEMA_VERSION + 1 }) };
  await assert.rejects(loadRenderRobot(`${file}-stale`, { client: stale }),
    new RegExp(`schemaVersion ${ROBOT_PAYLOAD_SCHEMA_VERSION + 1}.*reads version ${ROBOT_PAYLOAD_SCHEMA_VERSION}`));
});

test("a resolved job's scope is its document, and a resolved job that names none is refused", () => {
  assert.equal(renderAssetSourceScopeForJob({ kind: "stl", url: "/models/part.stl" }), "", "no resolved job: the unscoped default");
  assert.equal(renderAssetSourceScopeForJob({ resolved: { inputPath: " /models/part.stl " } }), "/models/part.stl");
  // A blank or non-string source is not a source: it fails closed rather than coerce into the
  // same bucket as the interactive viewer's unscoped default.
  for (const inputPath of [undefined, "", "   ", 0, false, {}, ["/models/part.stl"]]) {
    assert.throws(() => renderAssetSourceScopeForJob({ resolved: { rootPath: "/models", inputPath } }),
      /require resolved\.inputPath to scope the render asset cache/, JSON.stringify(inputPath));
  }
});

test("a cached render asset is not reused across source scopes", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  assert.deepEqual(await loadRenderJson(url), { ok: true });
  assert.equal(fetchCount, 1);

  setRenderAssetSourceScope("/models/second");
  await assert.rejects(
    () => loadRenderJson(url),
    /cached for source \/models\/first but was requested for \/models\/second/
  );
  assert.equal(fetchCount, 1);
});

test("a peek reports a miss instead of handing back another source's entry", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  const first = await loadRenderJson(url);
  assert.equal(peekRenderJson(url), first);

  setRenderAssetSourceScope("/models/second");
  assert.equal(peekRenderJson(url), null);
  assert.equal(fetchCount, 1);

  setRenderAssetSourceScope("/models/first");
  assert.equal(peekRenderJson(url), first);
});

test("a failed load leaves no source claim on an uncached asset", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return fetchCount === 1
      ? new Response("", { status: 503, statusText: "Unavailable" })
      : new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  await assert.rejects(() => loadRenderJson(url), /503 Unavailable/);

  setRenderAssetSourceScope("/models/second");
  assert.deepEqual(await loadRenderJson(url), { ok: true });
  assert.equal(fetchCount, 2);
});

test("an already-aborted array buffer request claims nothing", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.bin`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(new Uint8Array([9, 9, 9]), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  const controller = new AbortController();
  controller.abort();
  setRenderAssetSourceScope("/models/first");
  await assert.rejects(() => loadRenderArrayBuffer(url, { signal: controller.signal }), {
    name: "AbortError"
  });
  assert.equal(fetchCount, 0);

  setRenderAssetSourceScope("/models/second");
  assert.equal((await loadRenderArrayBuffer(url)).byteLength, 3);
  assert.equal(fetchCount, 1);
});

test("array buffer loads are scoped to their source as well", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.bin`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(new Uint8Array([1, 2, 3]), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/first");
  assert.equal((await loadRenderArrayBuffer(url)).byteLength, 3);

  setRenderAssetSourceScope("/models/second");
  await assert.rejects(() => loadRenderArrayBuffer(url), /refusing to reuse it/);
  assert.equal(fetchCount, 1);
});

test("repeat loads within one source scope still share a single fetch", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
    setRenderAssetSourceScope("");
  });

  setRenderAssetSourceScope("/models/only");
  const first = await loadRenderJson(url);
  const second = await loadRenderJson(url);

  assert.equal(second, first);
  assert.equal(fetchCount, 1);
});

test("an unset source scope leaves render asset caching untouched", async (t) => {
  const originalFetch = globalThis.fetch;
  const url = `/asset-${Date.now()}-${Math.random()}.json`;
  let fetchCount = 0;

  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const first = await loadRenderJson(url);
  const second = await loadRenderJson(url);

  assert.equal(second, first);
  assert.equal(fetchCount, 1);
});

test("the part leash is byte-bounded: large entries evict oldest-first down to the count floor", async (t) => {
  const name = (i) => `leash-bytes/c${i}`;
  // One decoded component's bytes, measured; then a ceiling that fits two of
  // them, so every entry is "large" relative to the budget.
  const first = await loadRenderPart(name(0));
  const oneEntryBytes = renderAssetCacheStats().partLeash.bytes;
  assert.ok(oneEntryBytes > 0, "a decoded payload weighs something");
  const previous = configurePartLeash({ maxBytes: Math.floor(oneEntryBytes * 2.5), minEntries: 1 });
  t.after(() => {
    configurePartLeash(previous);
  });
  for (let i = 1; i < 12; i += 1) {
    await loadRenderPart(name(i));
  }
  const stats = renderAssetCacheStats();
  assert.ok(stats.partLeash.bytes <= stats.partLeash.maxBytes, `bytes ${stats.partLeash.bytes} within ${stats.partLeash.maxBytes}`);
  // A component retains two leash entries sharing one set of arrays (payload +
  // meshData), so two components fit the ceiling: four entries, not 24.
  assert.ok(stats.partLeash.entries <= 4 && stats.partLeash.entries >= 1, `entries ${stats.partLeash.entries}: two large components fit, not 24`);
  assert.ok(stats.partPayload.entries <= 2, `part payloads retained: ${stats.partPayload.entries}`);
  assert.notEqual(await loadRenderPart(name(0)), first, "the oldest entry was evicted first");
  // The count floor holds a few entries whatever they weigh.
  configurePartLeash({ maxBytes: 1, minEntries: 3 });
  for (let i = 20; i < 26; i += 1) {
    await loadRenderPart(name(i));
  }
  assert.equal(renderAssetCacheStats().partLeash.entries, 3, "the floor keeps three entries above a 1-byte ceiling");
});

test("part payloads and selector bundles live on one bounded leash and re-decode after eviction", async (t) => {
  // What a selector read fetches: the part's selector table (cadgen's), its record's other object.
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(sunGearTable(), { status: 200 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  const name = (i) => `pkg/c${i}`;
  const reads = meshStore.counts.reads;
  const first = await loadRenderPart(name(0));
  assert.ok(first.vertices instanceof Float32Array);
  assert.equal(fetches, 0, "display reads only the stored mesh");
  // The selector join is deferred: the table is fetched when selection is first used.
  await loadRenderPartSelectorBundle(name(0));
  assert.equal(fetches, 1);
  for (let i = 1; i < 30; i += 1) {
    await loadRenderPart(name(i));
  }
  const stats = renderAssetCacheStats();
  assert.ok(stats.partLeash.entries <= stats.partLeash.limit, "leash bounded");
  assert.ok(stats.partPayload.entries <= stats.partLeash.limit, `part payload cache bounded (${stats.partPayload.entries})`);
  assert.ok(stats.partPayload.typedBytes > 0, "stats attribute retained render bytes");
  assert.equal(stats.selector.manifestRows, 0, "an old selector is evicted independently of displayed meshes");
  // The first component was evicted: loading it again decodes a FRESH payload.
  const again = await loadRenderPart(name(0));
  assert.notEqual(again, first, "evicted entry is re-decoded, not retained");
  assert.ok(meshStore.counts.reads - reads >= 31, "every display, the evicted one again, read its mesh");
});

test("display reads only the stored mesh and joins selectors on first use", async (t) => {
  // The table cadgen derived beside the mesh: the oracle for every fact the bundle carries.
  const table = selectorTableFixture("sun_gear");
  const name = `cached/cached-${Date.now()}`;
  let fetches = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(sunGearTable(), { status: 200 });
  };
  setTessellationCacheProvider(everyKeyMeshProvider());
  t.after(() => {
    globalThis.fetch = originalFetch;
    setTessellationCacheProvider(null);
  });

  const meshData = await loadRenderPart(name);
  assert.ok(meshData.indices.length > 0);
  assert.equal(fetches, 0, "display needs no selector table");
  assert.equal(meshStore.counts.reads, 1, "display performs one part-addressed mesh read");
  const selectorsBeforeDemand = renderAssetCacheStats().selector.entries;

  const bundle = await loadRenderPartSelectorBundle(name);
  assert.equal(fetches, 1, "topology is fetched only when selectors are requested");
  assert.equal(
    renderAssetCacheStats().selector.entries,
    selectorsBeforeDemand + 1,
    "display did not populate the selector cache",
  );
  assert.equal(bundle.manifest.faces.length, table.stats.faceCount);
  assert.equal(bundle.manifest.edges.length, table.stats.edgeCount);
  const column = (columns, name) => bundle.manifest.tables[columns].indexOf(name);
  const stored = (rows, columns, name) => table[rows][0][table.tables[columns].indexOf(name)];
  assert.deepEqual(bundle.manifest.faces[0][column("faceColumns", "params")], stored("faces", "faceColumns", "params"), "a stored face's parameters survive");
  assert.equal(bundle.manifest.edges[0][column("edgeColumns", "length")], stored("edges", "edgeColumns", "length"), "exact stored edge length survives");
});

test("a corrupt stored body is a probe miss for its caller to ask for again, never a fallback", async (t) => {
  const store = everyKeyMeshProvider();
  const read = store.getProbed;
  store.getProbed = async (row, options) => {
    const bytes = await read(row, options);
    new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).setUint32(4, 3, true);
    return bytes;
  };
  let fetches = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { fetches += 1; return new Response(null, { status: 404 }); };
  setTessellationCacheProvider(store);
  t.after(() => {
    globalThis.fetch = originalFetch;
    setTessellationCacheProvider(null);
  });
  await assert.rejects(loadRenderPart(`corrupt/corrupt-${Date.now()}`), isTessellationCacheProbeMissError);
  assert.equal(fetches, 0, "nothing else is read to make a mesh of its own");
});

test("an admitted probe whose body vanished is a probe miss, reading nothing else", async (t) => {
  const store = everyKeyMeshProvider();
  const part = `${createHash("sha256").update(`render-client-test:strict-${Date.now()}`).digest("hex")}-v1`;
  const [probe] = await store.probeMany([part]);
  assert.deepEqual(probe, partRowFor((await store.getManyProbed([probe]))[0]));
  let fetches = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(null, { status: 404 });
  };
  let reads = 0;
  setTessellationCacheProvider({
    async probeMany() { return [probe]; },
    async getProbed() { reads += 1; return null; },
  });
  t.after(() => {
    globalThis.fetch = originalFetch;
    setTessellationCacheProvider(null);
  });

  await assert.rejects(
    loadPart({ tessellationCache, identity: { part, tessellationProbe: probe } }),
    isTessellationCacheProbeMissError,
  );
  assert.equal(reads, 1, "the admitted body was asked for once");
  assert.equal(fetches, 0, "cold work waits for a fresh admission");
});

test("a load whose row names another part is refused before anything is read or cached", async () => {
  const [a, b] = await Promise.all([partLoad(`row-a-${Date.now()}`), partLoad(`row-b-${Date.now()}`)]);
  const mismatched = { part: a.identity.part, tessellationProbe: b.identity.tessellationProbe };
  const reads = meshStore.counts.reads;
  await assert.rejects(loadPart({ tessellationCache, identity: mismatched }), /another part's row/);
  await assert.rejects(loadPartSelectors(a.selectorsUrl, { tessellationCache, identity: mismatched }), /another part's row/);
  assert.equal(meshStore.counts.reads, reads, "nothing was read");
  assert.equal(peekRenderPart(b.identity.tessellationProbe), null, "nothing was cached as the other part's");
});

test("a failed part worker job is not retried synchronously on the main thread", async (t) => {
  class FailingWorker {
    constructor() { this.listeners = {}; }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      setTimeout(() => this.listeners.message?.({
        data: { id: message.id, ok: false, error: { name: "Error", message: "heavy worker failed" } },
      }), 0);
    }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  const savedFetch = globalThis.fetch;
  let mainThreadFetches = 0;
  globalThis.Worker = FailingWorker;
  globalThis.fetch = async () => {
    mainThreadFetches += 1;
    throw new Error("main-thread fallback must not fetch");
  };
  t.after(async () => {
    await releasePartWorkers();
    globalThis.Worker = savedWorker;
    globalThis.fetch = savedFetch;
  });

  await assert.rejects(loadRenderPart(`failure/heavy-${Date.now()}`), /heavy worker failed/);
  assert.equal(mainThreadFetches, 0);
});

test("part RAM hits do not create worker memory ownership", async (t) => {
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
  t.after(async () => {
    await releasePartWorkers();
    globalThis.Worker = savedWorker;
  });

  const name = `ram-hit/resident-${Date.now()}`;
  const first = await loadRenderPart(name, { memoryEstimateBytes: 321 });
  assert.ok(first);
  assert.equal(partWorkerMemoryStats().residentEstimateBytes, 321);
  const posts = created.reduce((total, worker) => total + worker.messages.length, 0);

  assert.equal(
    await loadRenderPart(name, { memoryEstimateBytes: 999 }),
    first,
    "the second load is the exact main-thread cache owner",
  );
  assert.equal(partWorkerMemoryStats().residentEstimateBytes, 321);
  assert.equal(
    created.reduce((total, worker) => total + worker.messages.length, 0),
    posts,
    "a RAM hit never reaches a worker",
  );
});

test("render asset clients can reclaim an idle part worker pool without reaching into worker internals", async () => {
  await releasePartWorkers();
  assert.deepEqual(reclaimIdlePartWorkers(), {
    reclaimedSlots: 0,
    residentSlots: 0,
    fullyReleased: true,
  });
  assert.equal(partWorkerMemoryStats().residentEstimateBytes, 0);
});

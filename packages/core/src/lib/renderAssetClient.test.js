import assert from "node:assert/strict";
import test from "node:test";

import {
  STEP_TOPOLOGY_SCHEMA_VERSION
} from "../common/stepTopology.mjs";
import {
  gitLfsPointerDetailsFromBuffer,
  loadRender3Mf,
  loadRenderArrayBuffer,
  loadRenderGlb,
  loadRenderJson,
  loadRenderRobot,
  loadRenderDisplayEdgeBundle,
  loadRenderSelectorBundle,
  loadRenderTopologyIndex,
  loadRenderSurf as loadSurf,
  loadRenderSurfSelectorBundle as loadSurfSelectors,
  peekRenderJson,
  peekRenderRobot,
  ROBOT_PAYLOAD_SCHEMA_VERSION,
  renderAssetCacheStats,
  reclaimIdleSurfWorkers,
  releaseSurfWorkers,
  surfWorkerMemoryStats,
  releaseRenderSurfLevel as releaseSurfLevel,
  configureSurfLeash
} from "./renderAssetClient.js";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  setRenderAssetSourceScope
} from "./renderAssetSourceScope.js";
import { parseSurf } from "./surf/container.js";
import {
  isTessellationCacheProbeMissError,
  createTessellationCache,
  tessellationCacheKey,
} from "./surf/tessellationCache.js";
import { everyKeyMeshProvider, probeRowFor } from "./surf/__tests__/meshFixtures.js";
import { TEST_TESSELLATION_LADDER } from "./surf/testing.js";

// Every mesh read names its tolerances: the standard rung of the ladder cadgen publishes.
const STANDARD = TEST_TESSELLATION_LADDER.levels[TEST_TESSELLATION_LADDER.defaultLevel];

// The mesh store every surf load reads: it holds the gear's mesh for any component asked.
let meshStore = everyKeyMeshProvider();
let tessellationCache = createTessellationCache({ provider: meshStore });
function setTessellationCacheProvider(provider) {
  tessellationCache.dispose();
  meshStore = provider || everyKeyMeshProvider();
  tessellationCache = createTessellationCache({ provider: meshStore });
}

const identityForSurfTest = (url) => ({
  surfaceInput: createHash("sha256").update(`render-client-test:${url}`).digest("hex"),
  surfaceObject: "a".repeat(64),
});
const loadRenderSurf = (url, options = {}) => loadSurf(url, {
  identity: identityForSurfTest(url), tessellationCache, tessellation: STANDARD, ...options,
});
const loadRenderSurfSelectorBundle = (url, options = {}) => loadSurfSelectors(url, {
  identity: identityForSurfTest(url), tessellationCache, tessellation: STANDARD, ...options,
});
const releaseRenderSurfLevel = (url, options = {}) => releaseSurfLevel(url, {
  identity: identityForSurfTest(url), tessellationCache, tessellation: STANDARD, ...options,
});

function pad4(buffer, byte = 0) {
  const padding = (4 - (buffer.length % 4)) % 4;
  return padding ? Buffer.concat([buffer, Buffer.alloc(padding, byte)]) : buffer;
}

function topologyGlb(manifest, buffers = {}, { schemaVersion = STEP_TOPOLOGY_SCHEMA_VERSION } = {}) {
  const bufferViews = [];
  let binary = Buffer.alloc(0);
  function addBufferView(payload) {
    binary = pad4(binary);
    const byteOffset = binary.length;
    binary = Buffer.concat([binary, payload]);
    const index = bufferViews.length;
    bufferViews.push({ buffer: 0, byteOffset, byteLength: payload.length });
    return index;
  }

  const selectorManifest = JSON.parse(JSON.stringify(manifest));
  selectorManifest.schemaVersion = schemaVersion;
  selectorManifest.profile = "selector";
  selectorManifest.buffers = { littleEndian: true, views: {} };
  for (const [name, { dtype, payload, count, itemSize }] of Object.entries(buffers)) {
    selectorManifest.buffers.views[name] = {
      dtype,
      bufferView: addBufferView(payload),
      byteOffset: 0,
      byteLength: payload.length,
      count,
      itemSize,
    };
  }
  const edgeManifest = {
    schemaVersion,
    profile: "surface-edges",
    stepHash: manifest.stepHash || "",
    classCodes: { none: 0, feature: 1, tangent: 2, seam: 3, degenerate: 4, boundary: 5, nonManifold: 6, unknown: 7 },
    primitiveAttributes: {
      barycentric: "_CAD_EDGE_BARYCENTRIC",
      class: "_CAD_EDGE_CLASS",
    },
    halfEdgeColumns: ["edgeRow", "faceRow", "occurrenceRow", "primitiveIndex", "triangleIndex", "side", "classCode"],
    halfEdgesView: "surfaceHalfEdges",
    buffers: {
      littleEndian: true,
      views: Object.fromEntries(
        Object.entries(selectorManifest.buffers.views)
          .filter(([name]) => name === "surfaceHalfEdges")
      )
    }
  };
  const indexManifest = {
    schemaVersion,
    profile: "index",
    entryKind: manifest.entryKind || "part",
    cadRef: manifest.cadRef,
    stats: manifest.stats || {},
    tables: manifest.tables?.occurrenceColumns ? { occurrenceColumns: manifest.tables.occurrenceColumns } : {},
    occurrences: manifest.occurrences || [],
    ...(manifest.assembly ? { assembly: manifest.assembly } : {}),
  };
  const indexView = addBufferView(Buffer.from(JSON.stringify(indexManifest), "utf8"));
  const edgeView = addBufferView(Buffer.from(JSON.stringify(edgeManifest), "utf8"));
  const selectorView = addBufferView(Buffer.from(JSON.stringify(selectorManifest), "utf8"));
  binary = pad4(binary);
  const gltf = {
    asset: { version: "2.0" },
    buffers: [{ byteLength: binary.length }],
    bufferViews,
    meshes: [{
      primitives: [{
        attributes: {
          _CAD_EDGE_BARYCENTRIC: 0,
          _CAD_EDGE_CLASS: 1,
        },
      }],
    }],
    extensionsUsed: ["STEP_topology"],
    extensions: {
      STEP_topology: {
        schemaVersion,
        entryKind: indexManifest.entryKind,
        indexView,
        edgeView,
        selectorView,
        encoding: "utf-8",
      },
    },
  };
  const jsonChunk = pad4(Buffer.from(JSON.stringify(gltf), "utf8"), 0x20);
  const header = Buffer.alloc(12);
  const jsonHeader = Buffer.alloc(8);
  const binHeader = Buffer.alloc(8);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + jsonChunk.length + 8 + binary.length, 8);
  jsonHeader.writeUInt32LE(jsonChunk.length, 0);
  jsonHeader.write("JSON", 4, "latin1");
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.write("BIN\0", 4, "latin1");
  return Buffer.concat([header, jsonHeader, jsonChunk, binHeader, binary]);
}

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

test("selector bundles decode STEP_topology bufferViews from GLB", async (t) => {
  const originalFetch = globalThis.fetch;
  const glbUrl = `/topology-${Date.now()}-${Math.random()}.glb`;
  const edgeIds = Buffer.alloc(8);
  edgeIds.writeUInt32LE(7, 0);
  edgeIds.writeUInt32LE(11, 4);
  const surfaceHalfEdges = Buffer.alloc(28);
  surfaceHalfEdges.writeUInt32LE(7, 0);
  surfaceHalfEdges.writeUInt32LE(11, 4);
  const requests = [];
  const glb = topologyGlb(
    { cadRef: "fixtures/box", tables: {}, occurrences: [], shapes: [], faces: [], edges: [] },
    {
      edgeIds: { dtype: "uint32", payload: edgeIds, count: 2, itemSize: 4 },
      surfaceHalfEdges: { dtype: "uint32", payload: surfaceHalfEdges, count: 7, itemSize: 4 }
    }
  );

  globalThis.fetch = async (requestUrl) => {
    requests.push(String(requestUrl));
    assert.equal(String(requestUrl), glbUrl);
    return new Response(glb, { status: 200 });
  };

  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const retainedBefore = renderAssetCacheStats().selector.typedBytes;
  const bundle = await loadRenderSelectorBundle(glbUrl);
  assert.deepEqual(Array.from(bundle.buffers.edgeIds), [7, 11]);
  assert.equal(
    renderAssetCacheStats().selector.typedBytes - retainedBefore,
    glb.byteLength,
    "buffer views charge the complete GLB allocation they retain",
  );
  const displayBundle = await loadRenderDisplayEdgeBundle(glbUrl);
  assert.deepEqual(Array.from(displayBundle.buffers.surfaceHalfEdges.slice(0, 2)), [7, 11]);
  assert.equal(displayBundle.manifest.profile, "surface-edges");
  assert.equal((await loadRenderTopologyIndex(glbUrl)).cadRef, "fixtures/box");
  assert.deepEqual(requests, [glbUrl]);
});

test("STEP_topology client rejects old schema artifacts", async (t) => {
  const originalFetch = globalThis.fetch;
  const glbUrl = `/old-topology-${Date.now()}-${Math.random()}.glb`;
  const glb = topologyGlb(
    { cadRef: "fixtures/old", tables: {}, occurrences: [], shapes: [], faces: [], edges: [] },
    {},
    { schemaVersion: STEP_TOPOLOGY_SCHEMA_VERSION - 1 }
  );

  globalThis.fetch = async () => new Response(glb, { status: 200 });
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await assert.rejects(
    loadRenderTopologyIndex(glbUrl),
    new RegExp(`Unsupported STEP_topology schemaVersion ${STEP_TOPOLOGY_SCHEMA_VERSION - 1}`)
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
  await assert.rejects(loadRenderRobot(`${file}-stale`, { client: stale }), /schemaVersion 2.*reads version 1/);
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

test("the surf leash is byte-bounded: large entries evict oldest-first down to the count floor", async (t) => {
  const surfBytes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "surf/fixtures/sun_gear.surf"));
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(
    surfBytes.buffer.slice(surfBytes.byteOffset, surfBytes.byteOffset + surfBytes.byteLength),
    { status: 200 }
  );
  const url = (i) => `https://cache.test/leash-bytes/components/c${i}.surf`;
  // One decoded component's bytes, measured; then a ceiling that fits two of
  // them, so every entry is "large" relative to the budget.
  const first = await loadRenderSurf(url(0));
  const oneEntryBytes = renderAssetCacheStats().surfLeash.bytes;
  assert.ok(oneEntryBytes > 0, "a decoded payload weighs something");
  const previous = configureSurfLeash({ maxBytes: Math.floor(oneEntryBytes * 2.5), minEntries: 1 });
  t.after(() => {
    configureSurfLeash(previous);
    globalThis.fetch = originalFetch;
  });
  for (let i = 1; i < 12; i += 1) {
    await loadRenderSurf(url(i));
  }
  const stats = renderAssetCacheStats();
  assert.ok(stats.surfLeash.bytes <= stats.surfLeash.maxBytes, `bytes ${stats.surfLeash.bytes} within ${stats.surfLeash.maxBytes}`);
  // A component retains two leash entries sharing one set of arrays (payload +
  // meshData), so two components fit the ceiling: four entries, not 24.
  assert.ok(stats.surfLeash.entries <= 4 && stats.surfLeash.entries >= 1, `entries ${stats.surfLeash.entries}: two large components fit, not 24`);
  assert.ok(stats.surfPayload.entries <= 2, `surf payloads retained: ${stats.surfPayload.entries}`);
  assert.notEqual(await loadRenderSurf(url(0)), first, "the oldest entry was evicted first");
  // The count floor holds a few entries whatever they weigh.
  configureSurfLeash({ maxBytes: 1, minEntries: 3 });
  for (let i = 20; i < 26; i += 1) {
    await loadRenderSurf(url(i));
  }
  assert.equal(renderAssetCacheStats().surfLeash.entries, 3, "the floor keeps three entries above a 1-byte ceiling");
});

test("surf payloads and selector bundles live on one bounded leash and re-decode after eviction", async (t) => {
  // What a selector read fetches: the component's selector table (cadgen's), never the SURF.
  const tableBytes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "surf/fixtures/sun_gear.selectors.json"));
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(tableBytes.buffer.slice(tableBytes.byteOffset, tableBytes.byteOffset + tableBytes.byteLength), { status: 200 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  const url = (i) => `https://cache.test/pkg/components/c${i}.surf`;
  const reads = meshStore.counts.reads;
  const first = await loadRenderSurf(url(0));
  assert.ok(first.vertices instanceof Float32Array);
  assert.equal(fetches, 0, "display reads only the stored mesh");
  // The selector join is deferred: the table is fetched when selection is first used.
  await loadRenderSurfSelectorBundle(url(0));
  assert.equal(fetches, 1);
  for (let i = 1; i < 30; i += 1) {
    await loadRenderSurf(url(i));
  }
  const stats = renderAssetCacheStats();
  assert.ok(stats.surfLeash.entries <= stats.surfLeash.limit, "leash bounded");
  assert.ok(stats.surfPayload.entries <= stats.surfLeash.limit, `surf payload cache bounded (${stats.surfPayload.entries})`);
  assert.ok(stats.surfPayload.typedBytes > 0, "stats attribute retained render bytes");
  assert.equal(stats.selector.manifestRows, 0, "an old selector is evicted independently of displayed meshes");
  // The first component was evicted: loading it again decodes a FRESH payload
  // (the array-buffer cache may absorb the fetch itself).
  const again = await loadRenderSurf(url(0));
  assert.notEqual(again, first, "evicted entry is re-decoded, not retained");
  assert.ok(meshStore.counts.reads - reads >= 31, "every display, the evicted one again, read its mesh");
});

test("display reads only the stored mesh and joins selectors on first use", async (t) => {
  const surfBytes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "surf/fixtures/sun_gear.surf"));
  const surfBuffer = surfBytes.buffer.slice(surfBytes.byteOffset, surfBytes.byteOffset + surfBytes.byteLength);
  const { index } = parseSurf(surfBuffer);
  const tableBytes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "surf/fixtures/sun_gear.selectors.json"));
  const url = `https://cache.test/cached/components/cached-${Date.now()}.selectors.json`;
  let fetches = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(tableBytes.buffer.slice(tableBytes.byteOffset, tableBytes.byteOffset + tableBytes.byteLength), { status: 200 });
  };
  setTessellationCacheProvider(everyKeyMeshProvider());
  t.after(() => {
    globalThis.fetch = originalFetch;
    setTessellationCacheProvider(null);
  });

  const meshData = await loadRenderSurf(url);
  assert.ok(meshData.indices.length > 0);
  assert.equal(fetches, 0, "display needs no surf bytes");
  assert.equal(meshStore.counts.reads, 1, "display performs one input-addressed mesh read");
  const selectorsBeforeDemand = renderAssetCacheStats().selector.entries;

  const bundle = await loadRenderSurfSelectorBundle(url);
  assert.equal(fetches, 1, "topology is fetched only when selectors are requested");
  assert.equal(
    renderAssetCacheStats().selector.entries,
    selectorsBeforeDemand + 1,
    "display did not populate the selector cache",
  );
  assert.equal(bundle.manifest.faces.length, index.faces.length);
  assert.equal(bundle.manifest.edges.length, index.edges.length);
  const column = (columns, name) => bundle.manifest.tables[columns].indexOf(name);
  assert.equal(bundle.manifest.faces[0][column("faceColumns", "area")], index.faces[0].area, "exact stored face area survives");
  assert.equal(bundle.manifest.edges[0][column("edgeColumns", "length")], index.edges[0].length, "exact stored edge length survives");
});

test("a corrupt stored body is a probe miss for its caller to ask for again, never a fallback", async (t) => {
  const url = `https://cache.test/corrupt/components/corrupt-${Date.now()}.surf`;
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
  await assert.rejects(loadRenderSurf(url), isTessellationCacheProbeMissError);
  assert.equal(fetches, 0, "nothing reads the surf to make a mesh of its own");
});

test("an admitted probe whose body vanished is a probe miss, reading nothing else", async (t) => {
  const surfBytes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "surf/fixtures/sun_gear.surf"));
  const surfBuffer = surfBytes.buffer.slice(surfBytes.byteOffset, surfBytes.byteOffset + surfBytes.byteLength);
  const url = `https://cache.test/strict/components/strict-${Date.now()}.surf`;
  const identity = identityForSurfTest(url);
  const [probe] = await everyKeyMeshProvider().probeMany([tessellationCacheKey(identity.surfaceInput, STANDARD)]);
  assert.deepEqual(probe, probeRowFor((await everyKeyMeshProvider().getManyProbed([probe]))[0]));
  let fetches = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(surfBuffer.slice(0), { status: 200 });
  };
  setTessellationCacheProvider({
    async probeMany() { return [probe]; },
    async getProbed() { return null; },
  });
  t.after(() => {
    globalThis.fetch = originalFetch;
    setTessellationCacheProvider(null);
  });

  await assert.rejects(
    loadSurf(url, { tessellation: STANDARD, identity: { ...identity, tessellationProbe: probe } }),
    isTessellationCacheProbeMissError,
  );
  assert.equal(fetches, 0, "cold work waits for a fresh admission");
});

test("obsolete concrete surf levels release browser cache references only", async (t) => {
  const tableBytes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "surf/fixtures/sun_gear.selectors.json"));
  const tableBuffer = tableBytes.buffer.slice(tableBytes.byteOffset, tableBytes.byteOffset + tableBytes.byteLength);
  const url = `https://cache.test/release/components/release-${Date.now()}.selectors.json`;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(tableBuffer.slice(0), { status: 200 });
  t.after(() => { globalThis.fetch = originalFetch; });

  const meshData = await loadRenderSurf(url);
  const bundle = await loadRenderSurfSelectorBundle(url);
  const before = renderAssetCacheStats();
  assert.ok(meshData.indices.length > 0 && bundle.manifest.faces.length > 0);
  assert.ok(releaseRenderSurfLevel(url) >= 2);
  const after = renderAssetCacheStats();
  assert.ok(after.surfPayload.entries < before.surfPayload.entries);
  assert.equal(after.selector.entries, before.selector.entries - 1);
  assert.ok(meshData.indices.length > 0, "the displayed owner remains valid");
  assert.ok(bundle.manifest.faces.length > 0, "the exact selector owner remains valid");
});

test("a failed surf worker job is not retried synchronously on the main thread", async (t) => {
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
    await releaseSurfWorkers();
    globalThis.Worker = savedWorker;
    globalThis.fetch = savedFetch;
  });

  const url = `https://failure.test/components/heavy-${Date.now()}.surf`;
  await assert.rejects(loadRenderSurf(url), /heavy worker failed/);
  assert.equal(mainThreadFetches, 0);
});

test("surf RAM hits do not create worker memory ownership", async (t) => {
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
    await releaseSurfWorkers();
    globalThis.Worker = savedWorker;
  });

  const url = `https://ram-hit.test/not-components/resident-${Date.now()}.surf`;
  const first = await loadRenderSurf(url, { memoryEstimateBytes: 321 });
  assert.ok(first);
  assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 321);
  const posts = created.reduce((total, worker) => total + worker.messages.length, 0);

  assert.equal(
    await loadRenderSurf(url, { memoryEstimateBytes: 999 }),
    first,
    "the second load is the exact main-thread cache owner",
  );
  assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 321);
  assert.equal(
    created.reduce((total, worker) => total + worker.messages.length, 0),
    posts,
    "a RAM hit never reaches a worker",
  );
});

test("render asset clients can reclaim an idle surf pool without reaching into worker internals", async () => {
  await releaseSurfWorkers();
  assert.deepEqual(reclaimIdleSurfWorkers(), {
    reclaimedSlots: 0,
    residentSlots: 0,
    fullyReleased: true,
  });
  assert.equal(surfWorkerMemoryStats().residentEstimateBytes, 0);
});

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  TESS_CACHE_MAGIC,
  TESS_CACHE_VERSION,
  createHttpTessellationCacheProvider,
  decodeComponentTessellation,
  decodeTessellationCacheBatch,
  encodeComponentTessellation,
  encodeTessellationCacheBatch,
  float64Hex,
  isTessellationCacheProbeMissError,
  resolvedTessellationIdentity,
  createTessellationCache,
  surfIndexFromCacheEntry,
  TESS_BATCH_MAX_BYTES,
  tessBatchMaxBytes,
  tessellationCacheKey,
  tessellationQuality,
  tessellationPayloadFacts,
  validateTessellationProbeRow,
} from "./tessellationCache.js";
import { DEFAULT_OPTIONS, TESSELLATION_VERSION, tessellateComponent } from "./tessellate.js";
import { buildMeshDataFromSurf } from "./surfMeshData.js";
import { buildComposedPackageMeshData } from "../assembly/meshData.js";

let tessellationCache = createTessellationCache();
function setTessellationCacheProvider(provider) {
  tessellationCache.dispose();
  tessellationCache = createTessellationCache({ provider });
}

const D = "11".repeat(32);
const D2 = "22".repeat(32);
const O = "aa".repeat(32);
const O2 = "bb".repeat(32);
const Q = Object.freeze({ chordTolerance: 0.0015, angleTolerance: 0.005 });

function componentFixture() {
  return {
    positions: new Float32Array([0, 0, 0, 2, 0, 0, 0, 3, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    faceOrds: new Float32Array([7, 7, 7]),
    indices: new Uint32Array([0, 1, 2]),
    sideOrds: new Uint32Array([1, 2, 3]),
    faceRanges: [{ ord: 7, color: [0.2, 0.4, 0.6, 1], indexStart: 0, indexCount: 3 }],
    edges: [{
      ord: 9,
      visibilityClass: "boundary",
      polyline: new Float32Array([0, 0, 0, 2, 0, 0]),
    }],
    bounds: { min: [0, 0, 0], max: [2, 3, 0] },
    scale: 3.605551275463989,
  };
}

function encodedEntry(overrides = {}) {
  return encodeComponentTessellation(componentFixture(), {
    surfaceInput: D,
    surfaceObject: O,
    tessellation: Q,
    partColor: [0.6, 0.5, 0.4, 1],
    edgeClasses: [[9, "boundary"]],
    ...overrides,
  });
}

function rewriteHeader(bytes, mutate) {
  const sourceView = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const oldHeaderLength = sourceView.getUint32(8, true);
  const header = JSON.parse(new TextDecoder().decode(bytes.subarray(12, 12 + oldHeaderLength)));
  mutate(header);
  const json = new TextEncoder().encode(JSON.stringify(header));
  const headerLength = (json.length + 3) & ~3;
  const payload = bytes.subarray(12 + oldHeaderLength);
  const result = new Uint8Array(12 + headerLength + payload.length);
  const view = new DataView(result.buffer);
  view.setUint32(0, sourceView.getUint32(0, true), true);
  view.setUint32(4, sourceView.getUint32(4, true), true);
  view.setUint32(8, headerLength, true);
  result.set(json, 12);
  result.fill(0x20, 12 + json.length, 12 + headerLength);
  result.set(payload, 12 + headerLength);
  return result;
}

function fromF64Hex(hex) {
  const bytes = Uint8Array.from(hex.match(/../g), (pair) => Number.parseInt(pair, 16));
  return new DataView(bytes.buffer).getFloat64(0, false);
}

test("lossless binary64 keys match Python and separate old decimal collisions", () => {
  const vectors = [
    [Number.MIN_VALUE, "0000000000000001"],
    [0.00001, "3ee4f8b588e368f1"],
    [0.0015, "3f589374bc6a7efa"],
    [0.005, "3f747ae147ae147b"],
    [1, "3ff0000000000000"],
    [Number.MAX_VALUE, "7fefffffffffffff"],
  ];
  for (const [value, expected] of vectors) assert.equal(float64Hex(value), expected);
  for (const value of [0, -0, -1, NaN, Infinity, -Infinity, "0.0015", true]) {
    assert.throws(() => float64Hex(value), /positive finite/);
  }
  for (const invalid of ["11", "A".repeat(64), null]) {
    assert.throws(() => tessellationCacheKey(invalid, Q), /64 lowercase hex/);
    assert.throws(() => resolvedTessellationIdentity(D, invalid, Q), /64 lowercase hex/);
  }

  const closeA = fromF64Hex("3f589374bc6a7efa");
  const closeB = fromF64Hex("3f589374bc6a7efb");
  assert.equal(closeA.toExponential(6), closeB.toExponential(6), "old key collides");
  assert.notEqual(
    tessellationCacheKey(D, { ...Q, chordTolerance: closeA }),
    tessellationCacheKey(D, { ...Q, chordTolerance: closeB }),
    "v4 key preserves the requested double",
  );

  // An option the key does not spell must never reach a hit: loopTolerance,
  // maxRefineDepth and minLoopSegments all change the triangles, and the key
  // would be byte-identical to a default run's.
  for (const [name, value] of [["loopTolerance", 1e-5], ["maxRefineDepth", 9], ["minLoopSegments", 32]]) {
    assert.throws(
      () => tessellationCacheKey(D, { ...Q, [name]: value }),
      new RegExp(`not part of the cache key: ${name}`),
    );
    assert.throws(() => tessellationQuality({ [name]: value }), /not part of the cache key/);
  }
  // Restating a default is not a divergence, so it still keys normally.
  assert.equal(
    tessellationCacheKey(D, { ...Q, loopTolerance: DEFAULT_OPTIONS.loopTolerance }),
    tessellationCacheKey(D, Q),
  );
});

test("v4 round-trips the full typed payload and exposes exact D/O/L/Q/R", () => {
  const source = componentFixture();
  const bytes = encodedEntry();
  const L = tessellationCacheKey(D, Q);
  const R = resolvedTessellationIdentity(D, O, Q);
  const decoded = decodeComponentTessellation(bytes, {
    surfaceInput: D,
    surfaceObject: O,
    tessellationInput: L,
    renderIdentity: R,
    tessellation: Q,
  });
  assert.ok(decoded);
  assert.equal(TESS_CACHE_VERSION, 4);
  assert.deepEqual(decoded.identity, {
    surfaceInput: D,
    surfaceObject: O,
    tessellationInput: L,
    renderIdentity: R,
    quality: tessellationQuality(Q),
    tessellatorVersion: TESSELLATION_VERSION,
    payloadVersion: 4,
  });
  assert.deepEqual(decoded.partColor, [0.6, 0.5, 0.4, 1]);
  assert.deepEqual(decoded.edgeClasses, [[9, "boundary"]]);
  for (const field of ["positions", "normals", "faceOrds", "indices", "sideOrds"]) {
    assert.deepEqual([...decoded.component[field]], [...source[field]], field);
    assert.equal(decoded.component[field].buffer, bytes.buffer, `${field} is zero-copy`);
  }
  assert.deepEqual(decoded.component.faceRanges, source.faceRanges);
  assert.deepEqual(decoded.component.bounds, source.bounds);
  assert.equal(decoded.component.scale, source.scale);
  assert.deepEqual([...decoded.component.edges[0].polyline], [...source.edges[0].polyline]);
  assert.equal(decoded.component.edges[0].polyline.buffer, bytes.buffer, "edge is zero-copy");

  const unalignedStorage = new Uint8Array(bytes.length + 1);
  unalignedStorage.set(bytes, 1);
  const unaligned = unalignedStorage.subarray(1);
  const copied = decodeComponentTessellation(unaligned, { surfaceInput: D, surfaceObject: O, tessellation: Q });
  assert.ok(copied);
  assert.deepEqual([...copied.component.positions], [...source.positions]);
  assert.notEqual(copied.component.positions.buffer, unalignedStorage.buffer, "unaligned input safely copies");
});

test("empty imported components round-trip through the cache without changing assembly bounds", () => {
  const index = { shapes: [{ ord: 1, kind: "shape", volume: null }], faces: [], edges: [] };
  const component = tessellateComponent(index, new Float32Array(0));
  const decoded = decodeComponentTessellation(encodeComponentTessellation(component, {
    surfaceInput: D,
    surfaceObject: O,
    edgeClasses: [],
  }));
  assert.ok(decoded, "an empty product entry is a valid complete cache payload");
  assert.deepEqual(decoded.component, component);
  const freshMesh = buildMeshDataFromSurf(index, null, { component });
  const cachedMesh = buildMeshDataFromSurf(surfIndexFromCacheEntry(decoded), null, {
    component: decoded.component,
  });
  assert.deepEqual(cachedMesh, freshMesh);

  const solidMesh = buildMeshDataFromSurf({ faces: [], edges: [] }, null, {
    component: componentFixture(),
  });
  const descriptor = { assembly: { root: {
    id: "root", nodeType: "assembly", children: [
      { id: "empty", nodeType: "part", children: [] },
      { id: "solid", nodeType: "part", children: [] },
    ],
  } }, occurrences: [
    { id: "empty", component: "empty", transform: [
      1, 0, 0, -1000, 0, 1, 0, -1000, 0, 0, 1, -1000, 0, 0, 0, 1,
    ] },
    { id: "solid", component: "solid" },
  ] };
  for (const emptyMesh of [freshMesh, cachedMesh]) {
    const assembly = buildComposedPackageMeshData(descriptor, new Map([
      ["empty", emptyMesh], ["solid", solidMesh],
    ]));
    assert.deepEqual(assembly.parts.map((part) => part.occurrenceId), ["empty", "solid"]);
    assert.deepEqual(assembly.missingComponentIds, []);
    assert.equal(assembly.parts[0].bounds, null);
    assert.equal(assembly.parts[0].triangleCount, 0);
    assert.equal(assembly.parts[1].triangleCount, 1);
    assert.deepEqual(assembly.bounds, solidMesh.bounds, "only real geometry frames the view");
    assert.deepEqual(assembly.assemblyRoot.bounds, solidMesh.bounds);
  }
});

test("decode rejects expected and embedded identity mismatches as cache misses", () => {
  const bytes = encodedEntry();
  const L = tessellationCacheKey(D, Q);
  assert.equal(decodeComponentTessellation(bytes, { surfaceInput: D2 }), null);
  assert.equal(decodeComponentTessellation(bytes, { surfaceObject: O2 }), null);
  assert.equal(decodeComponentTessellation(bytes, { tessellationInput: `${L}x` }), null);
  assert.equal(decodeComponentTessellation(bytes, {
    renderIdentity: resolvedTessellationIdentity(D, O2, Q),
  }), null);
  assert.equal(decodeComponentTessellation(bytes, {
    tessellation: { ...Q, chordTolerance: fromF64Hex("3f589374bc6a7efb") },
  }), null);

  assert.equal(decodeComponentTessellation(rewriteHeader(bytes, (h) => { h.surfaceInput = D2; })), null);
  assert.equal(decodeComponentTessellation(
    rewriteHeader(bytes, (h) => { h.surfaceDigest = O2; }),
    { surfaceObject: O },
  ), null);
  assert.equal(decodeComponentTessellation(rewriteHeader(bytes, (h) => {
    h.quality.chordToleranceF64 = "3f589374bc6a7efb";
  })), null);
  assert.equal(decodeComponentTessellation(rewriteHeader(bytes, (h) => {
    h.tessellationInput = `${h.tessellationInput.slice(0, -1)}0`;
  })), null);
  assert.equal(decodeComponentTessellation(rewriteHeader(bytes, (h) => {
    delete h.surfaceInput;
  })), null, "legacy-shaped header is a miss");
});

test("decode rejects corrupt, truncated and legacy versions", () => {
  const bytes = encodedEntry();
  assert.equal(decodeComponentTessellation(null), null);
  assert.equal(decodeComponentTessellation(new Uint8Array(4)), null);
  assert.equal(decodeComponentTessellation(bytes.subarray(0, bytes.length - 4)), null);
  const wrongMagic = bytes.slice();
  new DataView(wrongMagic.buffer).setUint32(0, 0, true);
  assert.equal(decodeComponentTessellation(wrongMagic), null);
  const legacy = bytes.slice();
  new DataView(legacy.buffer).setUint32(4, 3, true);
  assert.equal(decodeComponentTessellation(legacy), null);
  const badCount = rewriteHeader(bytes, (h) => { h.positionCount = -1; });
  assert.equal(decodeComponentTessellation(badCount), null);
});

test("decode rejects malformed complete-render metadata as cache misses", () => {
  const bytes = encodedEntry();
  const mutations = [
    (h) => { h.edgeClasses = [null]; },
    (h) => { h.edgeClasses = [[9, "boundary"], [9, "boundary"]]; },
    (h) => { h.edgeClasses = [[9, "future-class"]]; },
    (h) => { h.edges = [null]; },
    (h) => { h.edges[0].ord = 0; },
    (h) => { h.edges[0].visibilityClass = "feature"; },
    (h) => { h.edgeClasses = [[10, "boundary"]]; },
    (h) => { h.bounds.min = [null, 0, 0]; },
    (h) => { h.bounds.min[0] = h.bounds.max[0] + 1; },
    (h) => { h.scale = 0; },
    (h) => { h.partColor = [1, 0, 0]; },
    (h) => { h.faceRanges[0].indexStart = 3; },
    (h) => { h.faceRanges[0].indexCount = 0; },
    (h) => { h.faceRanges[0].color = [1, 0, 0]; },
    (h) => { h.faceRanges.push({ ord: 7, indexStart: 3, indexCount: 0 }); },
  ];
  for (const mutate of mutations) {
    assert.equal(decodeComponentTessellation(rewriteHeader(bytes, mutate)), null);
  }
  assert.equal(surfIndexFromCacheEntry({ edgeClasses: [null] }), null,
    "malformed surrogate metadata never throws in a render consumer");

  const extended = rewriteHeader(bytes, (h) => {
    h.bounds.extension = "ignored";
    h.faceRanges[0].extension = "ignored";
    h.edges[0].extension = "ignored";
  });
  assert.ok(decodeComponentTessellation(extended), "extra object fields remain forward-compatible");
});

test("batch container preserves aligned zero-copy v4 hits, misses and odd payloads", () => {
  const entry = encodedEntry();
  const odd = new Uint8Array([1, 2, 3]);
  const batch = encodeTessellationCacheBatch([entry, null, odd]);
  const decoded = decodeTessellationCacheBatch(batch);
  assert.equal(decoded.length, 3);
  assert.equal(decoded[1], null);
  assert.deepEqual([...decoded[2]], [1, 2, 3]);
  assert.equal(decoded[0].byteOffset % 4, 0);
  const component = decodeComponentTessellation(decoded[0], {
    surfaceInput: D,
    surfaceObject: O,
    tessellation: Q,
  });
  assert.ok(component);
  assert.equal(component.component.positions.buffer, batch.buffer, "batch hit stays zero-copy");
  assert.equal(decodeTessellationCacheBatch(batch.subarray(0, 14)), null);
  const corrupt = batch.slice();
  new DataView(corrupt.buffer).setUint32(0, 0, true);
  assert.equal(decodeTessellationCacheBatch(corrupt), null);
});

test("provider batch and writeback accept only entries bound to requested L", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const bodies = new Map();
  const rows = new Map();
  const puts = [];
  setTessellationCacheProvider({
    async probeMany(keys) { return keys.map((key) => rows.get(key) ?? null); },
    async getProbed(row) { return bodies.get(row.object) ?? null; },
    async put(key, bytes) {
      puts.push(key);
      const facts = tessellationPayloadFacts(bytes, { tessellationInput: key });
      const object = createHash("sha256").update(bytes).digest("hex");
      const row = validateTessellationProbeRow({ schemaVersion: 1, object, ...facts });
      rows.set(key, row);
      bodies.set(object, bytes);
    },
  });
  const entry = encodedEntry();
  await tessellationCache.writeBackEntryBytes(D2, Q, entry);
  assert.equal(puts.length, 0, "mismatched D is not persisted");
  await tessellationCache.writeBackEntryBytes(D, Q, entry);
  assert.deepEqual(puts, [tessellationCacheKey(D, Q)]);
  const probes = await tessellationCache.probeCachedTessellationEntries([D, D2], Q);
  assert.deepEqual([...probes.keys()], [D], "only the bound entry is readable");
  const hit = await tessellationCache.getCachedComponentEntry(D, Q, { probe: probes.get(D) });
  assert.equal(hit.identity.surfaceObject, O);
});

test("a vanished probed body is an explicit retry boundary only when requested", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const entry = encodedEntry();
  const key = tessellationCacheKey(D, Q);
  const facts = tessellationPayloadFacts(entry, { tessellationInput: key });
  const object = createHash("sha256").update(entry).digest("hex");
  const row = validateTessellationProbeRow({ schemaVersion: 1, object, ...facts });
  setTessellationCacheProvider({
    async probeMany() { return [row]; },
    async getProbed() { return null; },
  });
  assert.equal(await tessellationCache.getCachedEntryBytes(D, Q, { probe: row }), null);
  await assert.rejects(
    tessellationCache.getCachedEntryBytes(D, Q, { probe: row, strictProbe: true }),
    (error) => isTessellationCacheProbeMissError(error) && error.probe.object === row.object,
  );
});

test("strict probe admission also rejects a provider lost before body read", async () => {
  setTessellationCacheProvider(null);
  await assert.rejects(
    tessellationCache.getCachedEntryBytes(D, Q, { probe: { object: "gone" }, strictProbe: true }),
    isTessellationCacheProbeMissError,
  );
});

test("HTTP provider probes metadata before an exact bounded object read", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const entry = encodedEntry();
  const key = tessellationCacheKey(D, Q);
  const facts = tessellationPayloadFacts(entry, { tessellationInput: key });
  const object = createHash("sha256").update(entry).digest("hex");
  const row = validateTessellationProbeRow({ schemaVersion: 1, object, ...facts });
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).endsWith("/probe")) {
      return new Response(JSON.stringify({ entries: { [key]: row } }), {
        status: 200, headers: { "content-type": "application/json" },
      });
    }
    return new Response(entry.slice(), {
      status: 200, headers: { "content-length": String(entry.byteLength) },
    });
  };
  const provider = createHttpTessellationCacheProvider({ origin: "http://cache.test", fetch: (...args) => globalThis.fetch(...args) });
  const [probed] = await provider.probeMany([key]);
  assert.deepEqual(probed, row);
  const body = await provider.getProbed(probed, { maxBytes: row.byteLength });
  assert.deepEqual(body, entry);
  const readUrl = new URL(calls[1].url);
  assert.equal(readUrl.searchParams.get("object"), object);
  assert.equal(readUrl.searchParams.get("maxBytes"), String(row.byteLength));

  globalThis.fetch = async () => new Response(entry.slice(), {
    status: 200, headers: { "content-length": String(entry.byteLength + 1) },
  });
  assert.equal(await provider.getProbed(probed, { maxBytes: row.byteLength }), null,
    "an observed body larger than admission is rejected before adoption");
});


test("an HTTP batch read verifies each entry on its own: a damaged one is a miss for its component alone", async () => {
  const entries = [encodedEntry(), encodedEntry({ surfaceInput: D2 })];
  const rows = entries.map((entry) => validateTessellationProbeRow({ schemaVersion: 1,
    object: createHash("sha256").update(entry).digest("hex"), ...tessellationPayloadFacts(entry) }));
  const damaged = entries[1].slice();
  damaged[damaged.length - 1] ^= 0xff;
  const container = encodeTessellationCacheBatch([entries[0], damaged]);
  const provider = createHttpTessellationCacheProvider({ origin: "http://cache.test", fetch: async () => new Response(container.slice(), {
    status: 200, headers: { "content-length": String(container.byteLength) },
  }) });
  const bodies = await provider.getManyProbed(rows, { maxBytes: container.byteLength });
  assert.deepEqual(bodies[0], entries[0]);
  assert.equal(bodies[1], null);
});

test("a transport's batch ceiling lowers the server's bound and never raises it", async () => {
  const MIB = 1024 * 1024;
  assert.equal(TESS_BATCH_MAX_BYTES, 32 * MIB);
  assert.deepEqual([8 * MIB, 64 * MIB, undefined, 0, -1, Number.NaN, 2.5].map(tessBatchMaxBytes),
    [8 * MIB, 32 * MIB, 32 * MIB, 32 * MIB, 32 * MIB, 32 * MIB, 32 * MIB]);
  // A client's provider declares its transport's ceiling; the cache and its sessions report it.
  let fetched = 0;
  const provider = createHttpTessellationCacheProvider({ origin: "http://cache.test", maxBatchBytes: 8 * MIB,
    fetch: async () => { fetched += 1; return new Response(null, { status: 500 }); } });
  const cache = createTessellationCache({ provider });
  assert.deepEqual([provider.maxBatchBytes, cache.batchMaxBytes, cache.createSession().batchMaxBytes], [8 * MIB, 8 * MIB, 8 * MIB]);
  assert.equal(createTessellationCache({ provider: createHttpTessellationCacheProvider() }).batchMaxBytes, 32 * MIB);
  // And the provider asks for no batch over it, whatever its caller allows.
  const row = validateTessellationProbeRow({ schemaVersion: 1,
    object: createHash("sha256").update(encodedEntry()).digest("hex"), ...tessellationPayloadFacts(encodedEntry()) });
  const over = Array.from({ length: Math.ceil((8 * MIB) / row.byteLength) + 1 }, () => row);
  assert.equal(await provider.getManyProbed(over, { maxBytes: 32 * MIB }), null);
  assert.equal(fetched, 0);
  cache.dispose();
});

test("bounded probes retain other chunks when one metadata response is unavailable", async (t) => {
  const inputs = Array.from({ length: 513 }, (_, n) => createHash("sha256").update(`input-${n}`).digest("hex"));
  const rows = new Map(inputs.map((surfaceInput) => {
    const entry = encodedEntry({ surfaceInput });
    const facts = tessellationPayloadFacts(entry);
    return [facts.tessellationInput, validateTessellationProbeRow({ schemaVersion: 1,
      object: createHash("sha256").update(entry).digest("hex"), ...facts })];
  }));
  const calls = [];
  setTessellationCacheProvider({ async getProbed() { return null; }, async probeMany(keys) {
    calls.push(keys.length);
    if (calls.length === 2) return null;
    return keys.map((key) => rows.get(key));
  } });
  t.after(() => setTessellationCacheProvider(null));
  const hits = await tessellationCache.probeCachedTessellationEntries(inputs, Q);
  assert.deepEqual(calls, [256, 256, 1]);
  assert.equal(hits.size, 257);
  assert.ok(hits.has(inputs[0]));
  assert.ok(hits.has(inputs[512]));
  assert.equal(hits.has(inputs[256]), false);
});

test("render-session caches isolate exact objects, deferred writes and disposal", async () => {
  const written = [[], []];
  const entries = [encodedEntry(), encodedEntry({ surfaceObject: O2 })];
  const caches = entries.map((bytes, index) => {
    const facts = tessellationPayloadFacts(bytes);
    const row = validateTessellationProbeRow({ schemaVersion: 1,
      object: createHash("sha256").update(bytes).digest("hex"), ...facts });
    return createTessellationCache({
      provider: {
        probeMany: async () => [row],
        getProbed: async () => bytes,
        put: async (_key, body) => written[index].push(body),
      },
      writeBack: { deferMs: 10_000, concurrency: 1 },
    });
  });
  try {
    const decoded = await Promise.all(caches.map((cache) => cache.getCachedComponentEntry(D, Q)));
    assert.equal(decoded[0].identity.surfaceObject, O);
    assert.equal(decoded[1].identity.surfaceObject, O2);
    await Promise.all(caches.map((cache, index) => cache.writeBackEntryBytes(D, Q, entries[index])));
    caches[0].dispose();
    await caches[1].flushTessellationCacheWriteBacks();
    assert.deepEqual(written, [[], [entries[1]]]);
    assert.equal(await caches[0].getCachedEntryBytes(D, Q), null);
    assert.equal(caches[0].memoryStats().writeBackBytes, 0);
    assert.equal(caches[1].memoryStats().writeBackBytes, 0);
  } finally {
    for (const cache of caches) cache.dispose();
  }
});

test("cache disposal rejects a late custom-provider response without affecting another session", async () => {
  const entry = encodedEntry();
  const facts = tessellationPayloadFacts(entry);
  const row = validateTessellationProbeRow({ schemaVersion: 1,
    object: createHash("sha256").update(entry).digest("hex"), ...facts });
  let finish;
  const a = createTessellationCache({ provider: {
    probeMany: async () => [row],
    getProbed: () => new Promise((resolve) => { finish = resolve; }),
  } });
  const b = createTessellationCache({ provider: {
    probeMany: async () => [row], getProbed: async () => entry,
  } });
  try {
    const pending = a.getCachedEntryBytes(D, Q, { probe: row });
    const cancelled = assert.rejects(pending, { name: "AbortError" });
    a.dispose();
    finish(entry);
    await cancelled;
    assert.deepEqual(await b.getCachedEntryBytes(D, Q), entry);
  } finally {
    a.dispose(); b.dispose();
  }
});

// Distinct component inputs, each with its own encoded entry: a load's worth of write-backs.
const loadInputs = ["31", "32", "33", "34", "35", "36", "37", "38"].map((pair) => pair.repeat(32));
const loadEntry = (surfaceInput) => encodedEntry({ surfaceInput });
// Every pending callback and microtask: what a resolved write leads to has happened.
const settled = () => new Promise((resolve) => setImmediate(resolve));

test("deferred write-backs go out by their ceiling while a long load keeps adding entries, and in batches", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const written = [];
  const cache = createTessellationCache({ provider: {
    probeMany: async () => [], getProbed: async () => null,
    put: async (key) => { written.push(key); },
  }, writeBack: { deferMs: 1500, maxWaitMs: 2000, concurrency: 2 } });
  const keys = loadInputs.map((surfaceInput) => tessellationCacheKey(surfaceInput, Q));
  // A long cold load: an entry every 500 ms, so it is never quiet for the 1500 ms a batch waits for.
  const loadFor = async (indices) => {
    for (const index of indices) {
      await cache.writeBackEntryBytes(loadInputs[index], Q, loadEntry(loadInputs[index]));
      t.mock.timers.tick(500);
      await settled();
      if (index % 4 < 3) assert.deepEqual(written, keys.slice(0, index - (index % 4)), "entries wait to be written together");
    }
  };
  try {
    await loadFor([0, 1, 2, 3]);
    assert.deepEqual(written, keys.slice(0, 4), "two seconds after its first entry the batch was written, though the load never went quiet");
    await loadFor([4, 5, 6, 7]);
    assert.deepEqual(written, keys, "and so was the next");
    assert.equal(cache.memoryStats().writeBackBytes, 0);

    // A load that goes quiet still writes after its quiet interval.
    await cache.writeBackEntryBytes(D, Q, encodedEntry());
    t.mock.timers.tick(1500);
    await settled();
    assert.deepEqual(written, [...keys, tessellationCacheKey(D, Q)]);
  } finally {
    cache.dispose();
  }
});

test("a batch that reaches its byte bound is written at once, not turned away; only a writer still busy with the last one turns entries away", async (t) => {
  // No timer fires here: whatever is written, the byte bound wrote.
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const entries = loadInputs.map(loadEntry);
  const keys = loadInputs.map((surfaceInput) => tessellationCacheKey(surfaceInput, Q));
  const size = entries[0].byteLength;
  const starts = [];
  const finishes = [];
  const cache = createTessellationCache({ provider: {
    probeMany: async () => [], getProbed: async () => null,
    put: (key) => { starts.push(key); return new Promise((resolve) => finishes.push(resolve)); },
  }, writeBack: { deferMs: 10_000, concurrency: 1, maxPendingBytes: 2 * size } });
  const write = (index) => cache.writeBackEntryBytes(loadInputs[index], Q, entries[index]);
  try {
    await write(0);
    assert.deepEqual(starts, []);
    assert.equal(cache.memoryStats().pendingWriteBackBytes, size);
    await write(1);
    assert.deepEqual(starts, [keys[0]], "the full batch is being written, at the configured concurrency");
    assert.deepEqual(cache.memoryStats(), { pendingWriteBackBytes: 0, activeWriteBackBytes: 2 * size, writeBackBytes: 2 * size });

    // The next batch fills while the writer is busy; past its bound the writer cannot take it,
    // so memory wins: one batch writing and one waiting, and the entry beyond them is turned away.
    await write(2);
    await write(3);
    await write(4);
    assert.deepEqual(cache.memoryStats(), { pendingWriteBackBytes: 2 * size, activeWriteBackBytes: 2 * size, writeBackBytes: 4 * size });

    // Once the writer is free, the waiting batch goes at once.
    finishes.shift()();
    await settled();
    assert.deepEqual(starts, keys.slice(0, 2));
    finishes.shift()();
    await settled();
    assert.deepEqual(starts, keys.slice(0, 3), "the full batch followed the moment the writer was free");
    finishes.shift()();
    await settled();
    finishes.shift()();
    await settled();
    assert.deepEqual(starts, keys.slice(0, 4));
    assert.equal(cache.memoryStats().writeBackBytes, 0);
  } finally {
    cache.dispose();
  }
});

test("root-owned write-backs survive view disposal within one shared byte budget", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const firstBytes = encodedEntry();
  const secondBytes = encodedEntry({ surfaceInput: D2 });
  const written = [];
  const owner = createTessellationCache({
    provider: {
      probeMany: async () => [], getProbed: async () => null,
      put: async (key) => written.push(key),
    },
    writeBack: { deferMs: 10_000, concurrency: 1, maxPendingBytes: firstBytes.byteLength + secondBytes.byteLength },
  });
  try {
    const previous = owner.createSession();
    await previous.writeBackEntryBytes(D, Q, firstBytes);
    previous.dispose();
    previous.dispose();
    assert.equal(previous.tessellationCacheProviderRegistered(), false);
    assert.equal(owner.memoryStats().pendingWriteBackBytes, firstBytes.byteLength,
      "closing a view leaves its already-admitted write owned by the root");

    const current = owner.createSession();
    await current.writeBackEntryBytes(D2, Q, secondBytes);
    await settled();
    assert.deepEqual(written, [tessellationCacheKey(D, Q), tessellationCacheKey(D2, Q)],
      "new views share the root queue's batch: the second view's entry filled it, and it was written whole");
    await current.flushTessellationCacheWriteBacks();
    assert.equal(owner.memoryStats().writeBackBytes, 0);
    written.length = 0;
    await previous.writeBackEntryBytes(D2, Q, secondBytes);
    assert.equal(owner.memoryStats().writeBackBytes, 0, "late results from a disposed view cannot enqueue writes");

    await current.writeBackEntryBytes(D2, Q, secondBytes);
    assert.equal(owner.memoryStats().pendingWriteBackBytes, secondBytes.byteLength);
    owner.dispose();
    assert.equal(current.tessellationCacheProviderRegistered(), false);
    assert.equal(owner.memoryStats().writeBackBytes, 0, "closing the root still releases pending cache memory");
    await current.flushTessellationCacheWriteBacks();
    assert.deepEqual(written, [], "nothing the root let go of is written");
    assert.throws(() => owner.createSession(), /disposed/);
  } finally {
    owner.dispose();
  }
});

test("borrowed view cancellation is independent while owner disposal aborts every read", async () => {
  const bytes = encodedEntry();
  const row = validateTessellationProbeRow({ schemaVersion: 1,
    object: createHash("sha256").update(bytes).digest("hex"), ...tessellationPayloadFacts(bytes) });
  const pending = [];
  const owner = createTessellationCache({ provider: {
    probeMany: async () => [row],
    // Ignore AbortSignal in the provider to prove late adoption is checked too.
    getProbed: (_row, { signal }) => new Promise(resolve => pending.push({ signal, resolve })),
  } });
  try {
    const lifetime = new AbortController();
    const previous = owner.createSession({ signal: lifetime.signal });
    const current = owner.createSession();
    const oldRead = previous.getCachedEntryBytes(D, Q, { probe: row });
    const rejectedOld = assert.rejects(oldRead, { name: "AbortError" });
    const currentRead = current.getCachedEntryBytes(D, Q, { probe: row });
    lifetime.abort();
    assert.equal(pending[0].signal.aborted, true);
    assert.equal(pending[1].signal.aborted, false, "another view retains its own read lifetime");
    pending[0].resolve(bytes);
    pending[1].resolve(bytes);
    await rejectedOld;
    assert.deepEqual(await currentRead, bytes);
    await assert.rejects(previous.getCachedEntryBytes(D, Q, { probe: row }), { name: "AbortError" });
    assert.equal(pending.length, 2, "an already-cancelled view never asks the provider again");

    const lastRead = current.getCachedEntryBytes(D, Q, { probe: row });
    const rejectedLast = assert.rejects(lastRead, { name: "AbortError" });
    owner.dispose();
    assert.equal(pending[2].signal.aborted, true);
    pending[2].resolve(bytes);
    await rejectedLast;
  } finally {
    owner.dispose();
  }
});

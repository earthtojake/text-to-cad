// The shared tessellation cache is a cross-consumer contract: the codec must
// round-trip a FULL component losslessly (exports read a subset, render reads
// everything), the key must be canonical across tolerance spellings, and the
// provider hook must be invisible when unset and lossless when set.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseSurf } from "./container.js";
import { DEFAULT_OPTIONS, TESSELLATION_VERSION, tessellateComponent } from "./tessellate.js";
import {
  createHttpTessellationCacheProvider,
  decodeComponentTessellation,
  decodeTessellationCacheBatch,
  edgeClassesFromSurfIndex,
  encodeComponentTessellation,
  encodeTessellationCacheBatch,
  getCachedComponentEntries,
  setTessellationCacheProvider,
  originPrefix,
  surfIndexFromCacheEntry,
  tessellateComponentCached,
  tessellationCacheKey,
  tessellationOptionsCacheable,
} from "./tessellationCache.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));

function loadFixture(name) {
  const buffer = fs.readFileSync(path.join(HERE, "fixtures", `${name}.surf`));
  return parseSurf(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength));
}

test("codec round-trips a full component tessellation losslessly", () => {
  const { index, floats } = loadFixture("sun_gear");
  const component = tessellateComponent(index, floats);
  const bytes = encodeComponentTessellation(component, { partColor: [0.5, 0.25, 1, 1] });
  const decoded = decodeComponentTessellation(bytes);
  assert.ok(decoded, "entry decodes");
  assert.deepEqual(decoded.partColor, [0.5, 0.25, 1, 1]);
  const round = decoded.component;
  for (const field of ["positions", "normals", "faceOrds", "indices", "sideOrds"]) {
    assert.deepEqual([...round[field]], [...component[field]], field);
  }
  assert.deepEqual(round.faceRanges, component.faceRanges);
  assert.deepEqual(round.bounds, { min: [...component.bounds.min], max: [...component.bounds.max] });
  assert.equal(round.scale, component.scale);
  assert.equal(round.edges.length, component.edges.length);
  for (let i = 0; i < component.edges.length; i += 1) {
    assert.equal(round.edges[i].ord, component.edges[i].ord);
    assert.equal(round.edges[i].visibilityClass, component.edges[i].visibilityClass);
    assert.deepEqual([...round.edges[i].polyline], [...component.edges[i].polyline]);
  }
});

test("v3: edgeClasses round-trip and rebuild the render-facing surf index", () => {
  const { index, floats } = loadFixture("sun_gear");
  const component = tessellateComponent(index, floats);
  const edgeClasses = edgeClassesFromSurfIndex(index);
  assert.equal(edgeClasses.length, index.edges.length);
  const decoded = decodeComponentTessellation(
    encodeComponentTessellation(component, { partColor: [1, 0, 0, 1], edgeClasses }),
  );
  assert.deepEqual(decoded.edgeClasses, edgeClasses);
  const surrogate = surfIndexFromCacheEntry(decoded);
  assert.ok(surrogate, "v3 entries yield a surrogate index");
  assert.equal(surrogate.edges.length, index.edges.length);
  for (let i = 0; i < index.edges.length; i += 1) {
    assert.equal(surrogate.edges[i].ord, index.edges[i].ord);
    assert.equal(surrogate.edges[i].class, String(index.edges[i].class ?? "none"));
  }
  assert.deepEqual(surrogate.partColor, [1, 0, 0, 1]);
  // An entry encoded WITHOUT edgeClasses still decodes but yields no surrogate.
  const bare = decodeComponentTessellation(encodeComponentTessellation(component));
  assert.ok(bare);
  assert.equal(surfIndexFromCacheEntry(bare), null);
});

test("batch container round-trips hits and misses, rejects garbage", () => {
  const { index, floats } = loadFixture("sun_gear");
  const entry = encodeComponentTessellation(tessellateComponent(index, floats));
  const small = new Uint8Array([1, 2, 3]); // odd length exercises padding
  const batch = encodeTessellationCacheBatch([entry, null, small]);
  const decoded = decodeTessellationCacheBatch(batch);
  assert.equal(decoded.length, 3);
  assert.deepEqual([...decoded[0]], [...entry]);
  assert.equal(decoded[1], null);
  assert.deepEqual([...decoded[2]], [1, 2, 3]);
  // A decoded hit is itself a decodable entry (alignment survived the container).
  assert.ok(decodeComponentTessellation(decoded[0]));
  assert.equal(decodeTessellationCacheBatch(new Uint8Array(4)), null);
  assert.equal(decodeTessellationCacheBatch(batch.subarray(0, 14)), null);
});

test("getCachedComponentEntries prefers getMany and falls back to per-key gets", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const { index, floats } = loadFixture("sun_gear");
  const entry = encodeComponentTessellation(tessellateComponent(index, floats), {
    edgeClasses: edgeClassesFromSurfIndex(index),
  });
  const calls = { getMany: 0, get: 0 };
  setTessellationCacheProvider({
    async get(key) {
      calls.get += 1;
      return key.startsWith("hit-") ? entry : null;
    },
    async getMany(keys) {
      calls.getMany += 1;
      return keys.map((key) => (key.startsWith("hit-") ? entry : null));
    },
  });
  const hits = await getCachedComponentEntries(["hit-a", "miss-b", "hit-c"]);
  assert.equal(calls.getMany, 1);
  assert.equal(calls.get, 0);
  assert.deepEqual([...hits.keys()].sort(), ["hit-a", "hit-c"]);
  assert.ok(surfIndexFromCacheEntry(hits.get("hit-a")));

  // getMany returning null (batch unsupported) demotes to per-key gets.
  setTessellationCacheProvider({
    async get(key) {
      calls.get += 1;
      return key.startsWith("hit-") ? entry : null;
    },
    async getMany() {
      return null;
    },
  });
  const fallback = await getCachedComponentEntries(["hit-a", "miss-b"]);
  assert.equal(calls.get, 2);
  assert.equal(fallback.size, 1);
});

test("decode rejects garbage, truncation, and version drift as misses", () => {
  const { index, floats } = loadFixture("sun_gear");
  const bytes = encodeComponentTessellation(tessellateComponent(index, floats));
  assert.equal(decodeComponentTessellation(null), null);
  assert.equal(decodeComponentTessellation(new Uint8Array(4)), null);
  assert.equal(decodeComponentTessellation(bytes.subarray(0, bytes.length - 8)), null);
  const wrongVersion = bytes.slice();
  new DataView(wrongVersion.buffer).setUint32(4, 999, true);
  assert.equal(decodeComponentTessellation(wrongVersion), null);
});

test("cache key is canonical across tolerance spellings and includes both tolerances", () => {
  assert.equal(
    tessellationCacheKey("c0", { chordTolerance: 0.0015, angleTolerance: 0.35 }),
    tessellationCacheKey("c0", { chordTolerance: 1.5e-3, angleTolerance: 3.5e-1 }),
  );
  assert.equal(tessellationCacheKey("c0"), tessellationCacheKey("c0", { ...DEFAULT_OPTIONS }));
  assert.notEqual(
    tessellationCacheKey("c0", { chordTolerance: 1e-3 }),
    tessellationCacheKey("c0", { chordTolerance: 2e-3 }),
  );
  assert.notEqual(
    tessellationCacheKey("c0", { angleTolerance: 0.3 }),
    tessellationCacheKey("c0", { angleTolerance: 0.4 }),
  );
  assert.ok(!tessellationOptionsCacheable({ collectBoundaryDebug: true }));
  assert.ok(tessellationOptionsCacheable({}));
});

test("cache key carries the tessellator version salt (policy)", () => {
  // Dropping the -t<version>- salt would serve stale triangles across
  // tessellator algorithm changes: the key must cover the WHOLE function
  // from surf to triangles, not just its tolerance inputs.
  assert.ok(Number.isInteger(TESSELLATION_VERSION) && TESSELLATION_VERSION >= 1);
  assert.match(tessellationCacheKey("c0"), /^c0-t\d+-l/);
  assert.ok(tessellationCacheKey("c0").includes(`-t${TESSELLATION_VERSION}-`));
});

test("provider: miss tessellates + writes back; hit skips tessellation; unset is a no-op", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const { index, floats } = loadFixture("sun_gear");
  const store = new Map();
  const calls = { get: 0, put: 0 };
  setTessellationCacheProvider({
    async get(key) {
      calls.get += 1;
      return store.get(key) ?? null;
    },
    async put(key, bytes) {
      calls.put += 1;
      store.set(key, bytes);
    },
  });

  const first = await tessellateComponentCached(index, floats, { cid: "c0" });
  assert.equal(calls.get, 1);
  assert.equal(calls.put, 1);
  assert.equal(store.size, 1);
  assert.ok(store.has(tessellationCacheKey("c0")));

  const second = await tessellateComponentCached(index, floats, { cid: "c0" });
  assert.equal(calls.get, 2);
  assert.equal(calls.put, 1, "hit must not write back");
  assert.deepEqual([...second.positions], [...first.positions]);
  assert.deepEqual([...second.indices], [...first.indices]);
  assert.deepEqual(second.faceRanges, first.faceRanges);

  // Debug options bypass the provider entirely.
  await tessellateComponentCached(index, floats, { cid: "c0", options: { collectBoundaryDebug: true } });
  assert.equal(calls.get, 2);
  assert.equal(calls.put, 1);

  // No cid — nothing to key on — bypasses too.
  await tessellateComponentCached(index, floats, {});
  assert.equal(calls.get, 2);

  setTessellationCacheProvider(null);
  const plain = await tessellateComponentCached(index, floats, { cid: "c0" });
  assert.equal(calls.get, 2, "unset provider is a plain tessellation");
  assert.deepEqual([...plain.positions], [...first.positions]);
});

test("a provider that throws degrades to plain tessellation", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const { index, floats } = loadFixture("sun_gear");
  setTessellationCacheProvider({
    async get() { throw new Error("store down"); },
    async put() { throw new Error("store down"); },
  });
  const component = await tessellateComponentCached(index, floats, { cid: "c0" });
  assert.ok(component.positions.length > 0);
});

// The HTTP provider is the one place this package names the viewer's cache routes,
// and an embedded surface is served from a different origin than the backend that
// owns them. "" (same origin) must stay byte-identical to what shipped.
test("the HTTP provider addresses the cache routes at both origins", async () => {
  const REMOTE = "http://127.0.0.1:3250";
  assert.equal(originPrefix(undefined), "");
  assert.equal(originPrefix(""), "");
  assert.equal(originPrefix(`${REMOTE}/`), REMOTE);

  const requested = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    requested.push(String(url));
    return { ok: false, status: 404, statusText: "Not Found" };
  };
  try {
    await createHttpTessellationCacheProvider().get("abc");
    await createHttpTessellationCacheProvider().put("abc", new Uint8Array(1));
    await createHttpTessellationCacheProvider().getMany(["abc"]);
    await createHttpTessellationCacheProvider({ origin: REMOTE }).get("abc");
    await createHttpTessellationCacheProvider({ origin: REMOTE }).put("abc", new Uint8Array(1));
    await createHttpTessellationCacheProvider({ origin: REMOTE }).getMany(["abc"]);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requested, [
    "/__tess_cache/abc.tess",
    "/__tess_cache/abc.tess",
    "/__tess_cache/batch",
    `${REMOTE}/__tess_cache/abc.tess`,
    `${REMOTE}/__tess_cache/abc.tess`,
    `${REMOTE}/__tess_cache/batch`,
  ]);
});

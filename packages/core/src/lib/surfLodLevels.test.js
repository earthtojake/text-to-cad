// Level-keyed stored meshes (design/unified-tessellation.md Phase 5): the same
// component at different chord tolerances reads distinct stored meshes (a
// finer level -> more triangles), repeat requests at a level are RAM hits
// (one read per level), and every surf entry is LRU-bounded.
import assert from "node:assert/strict";
import test from "node:test";

import {
  loadRenderSurfPayloadAtLevel as loadPayload,
  loadRenderSurfSelectorBundle as loadSelector,
  renderAssetCacheStats,
  surfTessellationCacheKey as cacheKey,
} from "./renderAssetClient.js";
import {
  lodDefaultLevel,
  lodTessellationForLevel,
} from "./surf/lodPolicy.js";
import { TESSELLATION_VERSION, createTessellationCache } from "./surf/tessellationCache.js";
import { everyKeyMeshProvider, memoryMeshProvider, meshFixture, surfFixture } from "./surf/__tests__/meshFixtures.js";
import { installTestTessellationLadder } from "./surf/testing.js";

installTestTessellationLadder();

// Read the producer generation from the constant rather than spelling it out:
// this asserts the key's SHAPE, and every producer change bumps that number.
const IDENTITY = new RegExp(
  `^[0-9a-f]{64}-t${TESSELLATION_VERSION}-p6-l[0-9a-f]{16}-a[0-9a-f]{16}-s[0-9a-f]{64}$`,
);
const SUN_GEAR = surfFixture("sun_gear");
// The fixture's stored meshes, both levels, under its own identity.
const levelStore = () => memoryMeshProvider([meshFixture("sun_gear", 0).bytes, meshFixture("sun_gear", 1).bytes]);
const identityFor = () => ({ surfaceInput: SUN_GEAR.surfaceInput, surfaceObject: SUN_GEAR.surfaceObject });
const surfTessellationCacheKey = (url, tessellation, identity = identityFor(url)) =>
  cacheKey(url, tessellation, identity);

function withSurfFetch(t) {
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(SUN_GEAR.arrayBuffer(), { status: 200 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  return () => fetches;
}

test("mesh identity includes component, effective tolerances, producer and payload", () => {
  const defaultKey = surfTessellationCacheKey("u.surf", undefined);
  assert.equal(defaultKey, surfTessellationCacheKey("u.surf", {}));
  assert.match(defaultKey, IDENTITY);
  const l1 = surfTessellationCacheKey("u.surf", { chordTolerance: 5e-4 });
  assert.match(l1, IDENTITY);
  assert.notEqual(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 1.5e-4 }));
  assert.notEqual(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 5e-4, angleTolerance: 0.2 }));
  // 0.0005 and 5e-4 hit the same entry.
  assert.equal(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 0.0005 }));
  assert.equal(
    surfTessellationCacheKey("/pkg/a.surf", {}),
    surfTessellationCacheKey("/pkg/b.surf", {}),
    "URL does not fork one immutable D/O identity",
  );
  assert.notEqual(
    surfTessellationCacheKey("u.surf", lodTessellationForLevel(0)),
    surfTessellationCacheKey("u.surf", lodTessellationForLevel(lodDefaultLevel())),
    "coarse L0 and canonical L1 have different concrete selector/mesh identities",
  );
});

test("levels read once each, differ in density, and stay consistent", async (t) => {
  const fetches = withSurfFetch(t);
  const store = levelStore();
  const tessellationCache = createTessellationCache({ provider: store });
  t.after(() => tessellationCache.dispose());
  const options = { identity: identityFor(), tessellationCache };
  const url = "https://cad.test/components/sun_gear.surf";
  const l0 = await loadPayload(url, { ...options, tessellation: lodTessellationForLevel(0) });
  const l1 = await loadPayload(url, options);
  assert.ok(
    l1.meshData.indices.length > l0.meshData.indices.length,
    `the finer level adds triangles (${l1.meshData.indices.length} vs ${l0.meshData.indices.length})`,
  );
  // One mesh feeds render AND picking: the bundle rides the payload.
  assert.ok(l1.bundle, "selector bundle produced at the finer level");

  // Repeat requests are RAM hits at BOTH levels: no new reads.
  const before = { reads: store.counts.reads, fetches: fetches() };
  const l0Again = await loadPayload(url, { ...options, tessellation: lodTessellationForLevel(0) });
  const l1Again = await loadPayload(url, options);
  assert.deepEqual({ reads: store.counts.reads, fetches: fetches() }, before, "cached levels read nothing");
  assert.equal(l0Again, l0);
  assert.equal(l1Again, l1);
});

test("render-only refinement leaves selectors lazy and its cached arrays are not an extra CPU allocation", async (t) => {
  withSurfFetch(t);
  const tessellationCache = createTessellationCache({ provider: levelStore() });
  t.after(() => tessellationCache.dispose());
  const url = "https://cad.test/lazy-lod/components/sun_gear.surf";
  const tessellation = lodTessellationForLevel(0);
  const options = { identity: identityFor(), tessellationCache, tessellation };
  const payload = await loadPayload(url, { ...options, selectors: false });
  assert.equal(payload.bundle, undefined);
  const buffers = Object.values(payload.meshData).filter(ArrayBuffer.isView).map((array) => array.buffer);
  const total = (stats) => Object.entries(stats).reduce((sum, [name, value]) => name === "surfLeash" ? sum : sum + value.typedBytes, 0);
  assert.equal(total(renderAssetCacheStats()) - total(renderAssetCacheStats({ excludeBuffers: buffers })),
    [...new Set(buffers)].reduce((sum, buffer) => sum + buffer.byteLength, 0));
  const selector = await loadSelector(url, options);
  const combined = await loadPayload(url, options);
  assert.deepEqual(selector.manifest, combined.bundle.manifest, "later demand uses exactly the displayed level's triangle runs");
  assert.deepEqual(payload.meshData.indices, combined.meshData.indices);
});

test("the coarse tier is cheaper on curved and trimmed representative surfaces", async (t) => {
  for (const name of ["cam_follower_roller", "mixed"]) {
    const store = memoryMeshProvider([meshFixture(name, 0).bytes, meshFixture(name, 1).bytes]);
    const tessellationCache = createTessellationCache({ provider: store });
    t.after(() => tessellationCache.dispose());
    const { surfaceInput, surfaceObject } = surfFixture(name);
    const url = `https://cad.test/coarse-sample/${name}.surf`;
    const options = { identity: { surfaceInput, surfaceObject }, tessellationCache, selectors: false };
    const coarse = await loadPayload(url, { ...options, tessellation: lodTessellationForLevel(0) });
    const canonical = await loadPayload(url, options);
    assert.ok(
      coarse.meshData.indices.length < canonical.meshData.indices.length,
      `${name}: coarse triangles ${coarse.meshData.indices.length / 3} < canonical ${canonical.meshData.indices.length / 3}`,
    );
    const coarseBytes = coarse.meshData.vertices.byteLength
      + coarse.meshData.normals.byteLength
      + coarse.meshData.indices.byteLength;
    const canonicalBytes = canonical.meshData.vertices.byteLength
      + canonical.meshData.normals.byteLength
      + canonical.meshData.indices.byteLength;
    assert.ok(coarseBytes < canonicalBytes, `${name}: coarse typed geometry is smaller`);
  }
});

test("every surf entry — any level — rides one bounded leash; consumers own what they keep", async (t) => {
  withSurfFetch(t);
  const store = everyKeyMeshProvider();
  const tessellationCache = createTessellationCache({ provider: store });
  t.after(() => tessellationCache.dispose());
  const urlFor = (n) => `https://cad.test/lru/component-${n}.surf`;
  // Distinct components: each URL its own surface input, as distinct parts are.
  const options = (n, tessellation) => ({
    identity: { surfaceInput: String(n).padStart(64, "c"), surfaceObject: "a".repeat(64) },
    tessellationCache, selectors: false, ...(tessellation ? { tessellation } : {}),
  });
  const level = lodTessellationForLevel(2);
  const first = await loadPayload(urlFor(0), options(0, level));
  const firstDefault = await loadPayload(urlFor(0), options(0));
  // Within the leash both stay put.
  assert.equal(await loadPayload(urlFor(0), options(0, level)), first);
  assert.equal(await loadPayload(urlFor(0), options(0)), firstDefault);
  // Push more entries than the leash holds (levels and defaults alike).
  for (let n = 1; n <= 30; n += 1) {
    await loadPayload(urlFor(n), options(n, level));
  }
  // Eviction is proven by a FRESH payload object (the stored mesh was read again).
  const firstAgain = await loadPayload(urlFor(0), options(0, level));
  assert.notEqual(firstAgain, first, "an evicted level entry is read again");
  const defaultAgain = await loadPayload(urlFor(0), options(0));
  assert.notEqual(defaultAgain, firstDefault, "the default level is evicted like any other: the package owns its meshData");
});

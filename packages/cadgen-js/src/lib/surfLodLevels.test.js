// Level-keyed surf tessellation (design/unified-tessellation.md Phase 5): the
// same component URL at different chord tolerances yields distinct cached
// payloads (finer level -> more triangles), repeat requests at a level are
// cache hits (one fetch per level), and every surf entry is LRU-bounded.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  loadRenderSurfPayloadAtLevel as loadPayload,
  loadRenderSurfSelectorBundle as loadSelector,
  renderAssetCacheStats,
  surfTessellationCacheKey as cacheKey,
} from "./renderAssetClient.js";
import {
  LOD_DEFAULT_LEVEL,
  lodTessellationForLevel,
} from "./surf/lodPolicy.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUN_GEAR = fs.readFileSync(path.join(HERE, "surf", "fixtures", "sun_gear.surf"));
const SURFACE_OBJECT = createHash("sha256").update(SUN_GEAR).digest("hex");
const identityFor = (url) => ({
  surfaceInput: createHash("sha256").update(`test-surface-input:${url}`).digest("hex"),
  surfaceObject: SURFACE_OBJECT,
});
const surfTessellationCacheKey = (url, tessellation, identity = identityFor(url)) =>
  cacheKey(url, tessellation, identity);
const loadRenderSurfPayloadAtLevel = (url, options = {}) =>
  loadPayload(url, { identity: identityFor(url), ...options });
const loadRenderSurfSelectorBundle = (url, options = {}) =>
  loadSelector(url, { identity: identityFor(url), ...options });

function surfArrayBuffer() {
  return SUN_GEAR.buffer.slice(
    SUN_GEAR.byteOffset,
    SUN_GEAR.byteOffset + SUN_GEAR.byteLength,
  );
}

test("mesh identity includes component, effective tolerances, algorithm and payload", () => {
  const defaultKey = surfTessellationCacheKey("u.surf", undefined);
  assert.equal(defaultKey, surfTessellationCacheKey("u.surf", {}));
  assert.match(defaultKey, /^[0-9a-f]{64}-t2-p4-l[0-9a-f]{16}-a[0-9a-f]{16}-s[0-9a-f]{64}$/);
  const l1 = surfTessellationCacheKey("u.surf", { chordTolerance: 5e-4 });
  assert.match(l1, /^[0-9a-f]{64}-t2-p4-l[0-9a-f]{16}-a[0-9a-f]{16}-s[0-9a-f]{64}$/);
  assert.notEqual(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 1.5e-4 }));
  assert.notEqual(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 5e-4, angleTolerance: 0.2 }));
  // 0.0005 and 5e-4 hit the same entry.
  assert.equal(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 0.0005 }));
  assert.equal(
    surfTessellationCacheKey("/pkg/a.surf", {}, identityFor("same")),
    surfTessellationCacheKey("/pkg/b.surf", {}, identityFor("same")),
    "URL does not fork one immutable D/O identity",
  );
  assert.notEqual(
    surfTessellationCacheKey("u.surf", lodTessellationForLevel(0)),
    surfTessellationCacheKey("u.surf", lodTessellationForLevel(LOD_DEFAULT_LEVEL)),
    "coarse L0 and canonical L1 have different concrete selector/mesh identities",
  );
});

test("levels tessellate once each, differ in density, and stay consistent", async (t) => {
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(surfArrayBuffer(), { status: 200 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const url = "https://cad.test/components/sun_gear.surf";
  const l0 = await loadRenderSurfPayloadAtLevel(url, {});
  const l2 = await loadRenderSurfPayloadAtLevel(url, {
    tessellation: lodTessellationForLevel(2),
  });
  assert.ok(
    l2.meshData.indices.length > l0.meshData.indices.length,
    `finer level must add triangles (${l2.meshData.indices.length} vs ${l0.meshData.indices.length})`,
  );
  // One tessellation feeds render AND picking: the bundle rides the payload.
  assert.ok(l2.bundle, "selector bundle produced at the finer level");

  // Repeat requests are cache hits at BOTH levels: no new fetches.
  const before = fetches;
  const l0Again = await loadRenderSurfPayloadAtLevel(url, {});
  const l2Again = await loadRenderSurfPayloadAtLevel(url, {
    tessellation: lodTessellationForLevel(2),
  });
  assert.equal(fetches, before, "cached levels must not refetch");
  assert.equal(l0Again, l0);
  assert.equal(l2Again, l2);
});

test("render-only refinement leaves selectors lazy and its cached arrays are not an extra CPU allocation", async (t) => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(surfArrayBuffer(), { status: 200 });
  t.after(() => { globalThis.fetch = originalFetch; });
  const url = "https://cad.test/lazy-lod/components/sun_gear.surf";
  const tessellation = lodTessellationForLevel(2);
  const payload = await loadRenderSurfPayloadAtLevel(url, { tessellation, selectors: false });
  assert.equal(payload.bundle, undefined);
  const buffers = Object.values(payload.meshData).filter(ArrayBuffer.isView).map((array) => array.buffer);
  const total = (stats) => Object.entries(stats).reduce((sum, [name, value]) => name === "surfLeash" ? sum : sum + value.typedBytes, 0);
  assert.equal(total(renderAssetCacheStats()) - total(renderAssetCacheStats({ excludeBuffers: buffers })),
    [...new Set(buffers)].reduce((sum, buffer) => sum + buffer.byteLength, 0));
  const selector = await loadRenderSurfSelectorBundle(url, { tessellation });
  const combined = await loadRenderSurfPayloadAtLevel(url, { tessellation });
  assert.deepEqual(selector.manifest, combined.bundle.manifest, "later demand uses exactly the displayed level's triangle runs");
  assert.deepEqual(payload.meshData.indices, combined.meshData.indices);
});

test("explicit coarse tessellation is cheaper on curved and trimmed representative surfaces", async (t) => {
  const originalFetch = globalThis.fetch;
  const fixtures = ["cam_follower_roller.surf", "mixed.surf"];
  const bytesByName = Object.fromEntries(fixtures.map((name) => [
    name,
    fs.readFileSync(path.join(HERE, "surf", "fixtures", name)),
  ]));
  globalThis.fetch = async (url) => {
    const name = String(url).split("/").at(-1);
    const bytes = bytesByName[name];
    return bytes
      ? new Response(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), { status: 200 })
      : new Response(null, { status: 404 });
  };
  t.after(() => { globalThis.fetch = originalFetch; });

  for (const name of fixtures) {
    const url = `https://cad.test/coarse-sample/${name}`;
    const coarse = await loadRenderSurfPayloadAtLevel(url, {
      tessellation: lodTessellationForLevel(0),
    });
    const canonical = await loadRenderSurfPayloadAtLevel(url, {});
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
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(surfArrayBuffer(), { status: 200 });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const urlFor = (n) => `https://cad.test/lru/component-${n}.surf`;
  const level = lodTessellationForLevel(2);
  const first = await loadRenderSurfPayloadAtLevel(urlFor(0), { tessellation: level });
  const firstDefault = await loadRenderSurfPayloadAtLevel(urlFor(0), {});
  // Within the leash both stay put.
  assert.equal(await loadRenderSurfPayloadAtLevel(urlFor(0), { tessellation: level }), first);
  assert.equal(await loadRenderSurfPayloadAtLevel(urlFor(0), {}), firstDefault);
  // Push more entries than the leash holds (levels and defaults alike).
  for (let n = 1; n <= 30; n += 1) {
    await loadRenderSurfPayloadAtLevel(urlFor(n), { tessellation: level });
  }
  // The upstream array-buffer cache may absorb the fetch; eviction is proven
  // by a FRESH payload object (the tessellation re-ran).
  const firstAgain = await loadRenderSurfPayloadAtLevel(urlFor(0), { tessellation: level });
  assert.notEqual(firstAgain, first, "evicted level entry re-tessellates");
  const defaultAgain = await loadRenderSurfPayloadAtLevel(urlFor(0), {});
  assert.notEqual(defaultAgain, firstDefault, "the default level is evicted like any other: the package owns its meshData");
});

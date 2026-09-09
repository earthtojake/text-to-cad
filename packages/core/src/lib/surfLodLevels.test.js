// Level-keyed surf tessellation (design/unified-tessellation.md Phase 5): the
// same component URL at different chord tolerances yields distinct cached
// payloads (finer level -> more triangles), repeat requests at a level are
// cache hits (one fetch per level), and non-default levels are LRU-bounded.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  loadRenderSurfPayloadAtLevel,
  surfTessellationCacheKey,
} from "./renderAssetClient.js";
import { LOD_CHORD_LEVELS } from "./surf/lodPolicy.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUN_GEAR = fs.readFileSync(path.join(HERE, "surf", "fixtures", "sun_gear.surf"));

function surfArrayBuffer() {
  return SUN_GEAR.buffer.slice(
    SUN_GEAR.byteOffset,
    SUN_GEAR.byteOffset + SUN_GEAR.byteLength,
  );
}

test("cache keys: default tessellation keeps the plain URL, levels get suffixes", () => {
  assert.equal(surfTessellationCacheKey("u.surf", undefined), "u.surf");
  assert.equal(surfTessellationCacheKey("u.surf", {}), "u.surf");
  const l1 = surfTessellationCacheKey("u.surf", { chordTolerance: 5e-4 });
  assert.match(l1, /^u\.surf#l5\.000000e-4-aNaN$/);
  assert.notEqual(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 1.5e-4 }));
  // 0.0005 and 5e-4 hit the same entry.
  assert.equal(l1, surfTessellationCacheKey("u.surf", { chordTolerance: 0.0005 }));
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
    tessellation: { chordTolerance: LOD_CHORD_LEVELS[2] },
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
    tessellation: { chordTolerance: LOD_CHORD_LEVELS[2] },
  });
  assert.equal(fetches, before, "cached levels must not refetch");
  assert.equal(l0Again, l0);
  assert.equal(l2Again, l2);
});

test("non-default levels are LRU-bounded; the default level is never evicted", async (t) => {
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
  const level = { chordTolerance: LOD_CHORD_LEVELS[1] };
  const first = await loadRenderSurfPayloadAtLevel(urlFor(0), { tessellation: level });
  const firstDefault = await loadRenderSurfPayloadAtLevel(urlFor(0), {});
  // Push more level entries than the LRU holds.
  for (let n = 1; n <= 9; n += 1) {
    await loadRenderSurfPayloadAtLevel(urlFor(n), { tessellation: level });
  }
  // The upstream array-buffer cache may absorb the fetch; eviction is proven
  // by a FRESH payload object (the tessellation re-ran).
  const firstAgain = await loadRenderSurfPayloadAtLevel(urlFor(0), { tessellation: level });
  assert.notEqual(firstAgain, first, "evicted level entry re-tessellates");
  const defaultAgain = await loadRenderSurfPayloadAtLevel(urlFor(0), {});
  assert.equal(defaultAgain, firstDefault, "default-level entry survived the LRU churn");
});

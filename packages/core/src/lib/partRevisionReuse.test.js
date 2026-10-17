import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  loadRenderPart,
  loadRenderPartSelectorBundle,
  partCacheKey,
} from "./renderAssetClient.js";
import { setRenderAssetSourceScope } from "./renderAssetSourceScope.js";
import { createTessellationCache } from "./parts/tessellationCache.js";
import { everyKeyMeshProvider } from "./parts/__tests__/meshFixtures.js";

// What a selector read fetches: the part's selector table.
const table = readFileSync(new URL("./parts/fixtures/sun_gear.selectors.json", import.meta.url));
// The host's part store, holding the gear's mesh for any part asked.
const store = everyKeyMeshProvider("sun_gear");
const tessellationCache = createTessellationCache({ provider: store });
// A part and the row its probe answers, as each revision's view hands the page one.
async function identityFor(name) {
  const part = `${createHash("sha256").update(name).digest("hex")}-v1`;
  const [row] = await store.probeMany([part]);
  return { part, tessellationProbe: row };
}
const identity = await identityFor("test part");
const url = (tree, cid = "123456789abcdef0") => `https://cad.test/${tree.repeat(64)}/components/${cid}.selectors.json`;

test("a part's payloads are cached by its part and its mesh's object, and a load without both is refused", async () => {
  const { part, tessellationProbe: row } = identity;
  assert.equal(partCacheKey(row), `${part}@${row.glb.object}`);
  assert.notEqual(partCacheKey({ ...row, part: `${"c".repeat(64)}-v1` }), partCacheKey(row));
  assert.notEqual(partCacheKey({ ...row, glb: { ...row.glb, object: "c".repeat(64) } }), partCacheKey(row));
  // An incomplete row is refused instead of falling back to a mutable URL.
  for (const probe of [undefined, {}, { part }, { glb: row.glb }]) {
    assert.equal(partCacheKey(probe), "");
    const options = { identity: { part, tessellationProbe: probe }, tessellationCache };
    await assert.rejects(loadRenderPart(options), /Missing asset cache key/);
    await assert.rejects(loadRenderPartSelectorBundle(url("a"), options), /Missing asset cache key/);
  }
});

test("revisions reuse meshes and exact selector payloads without fetching unchanged objects", async (t) => {
  let fetches = 0;
  t.mock.method(globalThis, "fetch", async () => {
    fetches += 1;
    return new Response(table);
  });
  const options = { identity, tessellationCache };
  const mesh = await loadRenderPart(options);
  // The next revision names the same part, and its probe answers the same row.
  assert.equal(await loadRenderPart({ identity: await identityFor("test part"), tessellationCache }), mesh);
  const selectors = await loadRenderPartSelectorBundle(url("1"), options);
  assert.ok(selectors.manifest);
  const firstFetches = fetches;
  assert.equal(await loadRenderPartSelectorBundle(url("2"), options), selectors);
  assert.equal(fetches, firstFetches);
});

test("snapshot source collision guard remains active even with a part identity", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(table));
  const scoped = await identityFor("scoped part");
  setRenderAssetSourceScope("snapshot-A.step");
  try {
    await loadRenderPart({ identity: scoped, tessellationCache });
    setRenderAssetSourceScope("snapshot-B.step");
    await assert.rejects(loadRenderPart({ identity: scoped, tessellationCache }),
      { name: "RenderAssetSourceScopeError" });
  } finally {
    setRenderAssetSourceScope("");
  }
});

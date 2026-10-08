import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  loadRenderSurf,
  loadRenderSurfPayloadAtLevel,
  loadRenderSurfSelectorBundle,
  releaseRenderSurfLevel,
  surfTessellationCacheKey,
} from "./renderAssetClient.js";
import { setRenderAssetSourceScope } from "./renderAssetSourceScope.js";
import { createTessellationCache } from "./surf/tessellationCache.js";
import { everyKeyMeshProvider } from "./surf/__tests__/meshFixtures.js";

const fixture = readFileSync(new URL("./surf/fixtures/sun_gear.surf", import.meta.url));
// What a selector read fetches: the component's selector table, bound to that surface.
const table = readFileSync(new URL("./surf/fixtures/sun_gear.selectors.json", import.meta.url));
const identity = {
  surfaceInput: createHash("sha256").update("test surface input").digest("hex"),
  surfaceObject: createHash("sha256").update(fixture).digest("hex"),
};
// The host's mesh store, holding this component's mesh at any level asked.
const tessellationCache = createTessellationCache({ provider: everyKeyMeshProvider("sun_gear", { surfaceObject: identity.surfaceObject }) });
const url = (tree, cid = "123456789abcdef0", extra = "") =>
  `/__cad/store?file=${tree.repeat(64)}/components/${cid}.surf${extra}`;
const key = (value, options, object = identity) => surfTessellationCacheKey(value, options, object);

test("immutable SURF identity survives tree revisions but preserves all mesh inputs", () => {
  assert.equal(key(url("a")), key(url("b")));
  assert.equal(key(url("a", undefined, "&v=first")), key(url("b", undefined, "&v=second")));
  assert.equal(key(url("a", undefined, "&q=1&mode=x")), key(url("b", undefined, "&mode=x&q=1")));
  assert.notEqual(key(url("a")), key(url("b"), undefined, { ...identity, surfaceObject: "c".repeat(64) }));
  assert.notEqual(key(url("a")), key(url("b"), undefined, { ...identity, surfaceInput: "d".repeat(64) }));
  assert.notEqual(key(url("a")), key(url("b"), { chordTolerance: 0.002, angleTolerance: 1.4 }));
  assert.equal(key(url("a", undefined, "&mode=x")), key(url("b", undefined, "&mode=y")));
  assert.equal(key(`https://one.example${url("a")}`), key(`https://two.example${url("b")}`));
});

test("incomplete identities are rejected instead of falling back to mutable URLs", () => {
  for (const object of [undefined, {}, { surfaceObject: "abc" }, { surfaceObject: "x".repeat(64) }]) {
    assert.throws(() => surfTessellationCacheKey(url("a"), undefined, object), /surfaceInput|surfaceObject/);
  }
  assert.equal(key("/arbitrary/a.surf"), key("/arbitrary/b.surf"));
});

test("revisions reuse meshes and exact selector payloads without fetching unchanged objects", async (t) => {
  let fetches = 0;
  t.mock.method(globalThis, "fetch", async () => {
    fetches += 1;
    return new Response(table);
  });
  const first = url("1");
  const second = url("2");
  const options = { identity, tessellationCache };
  const mesh = await loadRenderSurf(first, options);
  assert.equal(await loadRenderSurf(second, options), mesh);
  const selectors = await loadRenderSurfSelectorBundle(first, options);
  assert.ok(selectors.manifest);
  const firstFetches = fetches;
  assert.equal(await loadRenderSurfSelectorBundle(second, options), selectors);
  assert.equal(fetches, firstFetches);

  const tessellation = { chordTolerance: 0.002, angleTolerance: 1.4 };
  const coarseMesh = await loadRenderSurf(first, { ...options, tessellation });
  const payload = await loadRenderSurfPayloadAtLevel(first, { ...options, tessellation });
  assert.equal(await loadRenderSurfPayloadAtLevel(second, { ...options, tessellation }), payload);
  assert.notEqual(payload.bundle, selectors, "selectors must follow the concrete mesh parameters");
  assert.equal(fetches, firstFetches);

  assert.ok(releaseRenderSurfLevel(second, { identity, tessellation }) > 0);
  assert.ok(payload.meshData, "release drops cache ownership, not an active scene's payload");
  const replacement = await loadRenderSurfPayloadAtLevel(first, { ...options, tessellation });
  assert.notEqual(replacement, payload);
  assert.notEqual(await loadRenderSurf(first, { ...options, tessellation }), coarseMesh,
    "release also removes the initial display cache's obsolete arrays");
  assert.equal(await loadRenderSurf(second, options), mesh, "another concrete level remains owned");
});

test("snapshot source collision guard remains active even with an object identity", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(table));
  const asset = url("3");
  const scopedIdentity = { ...identity, surfaceInput: createHash("sha256").update("scoped input").digest("hex") };
  setRenderAssetSourceScope("snapshot-A.step");
  try {
    assert.equal(key(asset, undefined, scopedIdentity), key(url("4"), undefined, scopedIdentity), "cache identity is the immutable D/O pair");
    await loadRenderSurf(asset, { identity: scopedIdentity, tessellationCache });
    setRenderAssetSourceScope("snapshot-B.step");
    await assert.rejects(loadRenderSurf(asset, { identity: scopedIdentity, tessellationCache }), { name: "RenderAssetSourceScopeError" });
  } finally {
    setRenderAssetSourceScope("");
  }
});

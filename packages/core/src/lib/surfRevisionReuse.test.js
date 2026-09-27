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

const fixture = readFileSync(new URL("./surf/fixtures/sun_gear.surf", import.meta.url));
const identity = {
  surfaceInput: createHash("sha256").update("test surface input").digest("hex"),
  surfaceObject: createHash("sha256").update(fixture).digest("hex"),
};
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
    return new Response(fixture);
  });
  const first = url("1");
  const second = url("2");
  const mesh = await loadRenderSurf(first, { identity });
  const firstFetches = fetches;
  assert.equal(await loadRenderSurf(second, { identity }), mesh);
  assert.equal(fetches, firstFetches);
  const selectors = await loadRenderSurfSelectorBundle(first, { identity });
  assert.ok(selectors.manifest);
  assert.equal(await loadRenderSurfSelectorBundle(second, { identity }), selectors);
  assert.equal(fetches, firstFetches);

  const tessellation = { chordTolerance: 0.002, angleTolerance: 1.4 };
  const coarseMesh = await loadRenderSurf(first, { identity, tessellation });
  const payload = await loadRenderSurfPayloadAtLevel(first, { identity, tessellation });
  assert.equal(await loadRenderSurfPayloadAtLevel(second, { identity, tessellation }), payload);
  assert.notEqual(payload.bundle, selectors, "selectors must follow the concrete mesh parameters");
  assert.equal(fetches, firstFetches);

  assert.ok(releaseRenderSurfLevel(second, { identity, tessellation }) > 0);
  assert.ok(payload.meshData, "release drops cache ownership, not an active scene's payload");
  const replacement = await loadRenderSurfPayloadAtLevel(first, { identity, tessellation });
  assert.notEqual(replacement, payload);
  assert.notEqual(await loadRenderSurf(first, { identity, tessellation }), coarseMesh,
    "release also removes the initial display cache's obsolete arrays");
  assert.equal(await loadRenderSurf(second, { identity }), mesh, "another concrete level remains owned");
});

test("snapshot source collision guard remains active even with an object identity", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(fixture));
  const asset = url("3");
  const scopedIdentity = { ...identity, surfaceInput: createHash("sha256").update("scoped input").digest("hex") };
  setRenderAssetSourceScope("snapshot-A.step");
  try {
    assert.equal(key(asset, undefined, scopedIdentity), key(url("4"), undefined, scopedIdentity), "cache identity is the immutable D/O pair");
    await loadRenderSurf(asset, { identity: scopedIdentity });
    setRenderAssetSourceScope("snapshot-B.step");
    await assert.rejects(loadRenderSurf(asset, { identity: scopedIdentity }), { name: "RenderAssetSourceScopeError" });
  } finally {
    setRenderAssetSourceScope("");
  }
});

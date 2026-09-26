import assert from "node:assert/strict";
import test from "node:test";
import { buildComposedPackageMeshData } from "@hardcore/core/lib/assembly/meshData.js";
import { surfTessellationCacheKey } from "@hardcore/core/lib/renderAssetClient.js";
import { lodTessellationForLevel } from "@hardcore/core/lib/surf/lodPolicy.js";
import { completedPackages, createCompletedPackageCache, renderAssetCacheStatsWithPackages } from "./completedPackageCache.js";
import { renderMemoryAccounting } from "./renderMemoryAccounting.js";

const root = { workspaceId: "package-root", resources: {cacheKey: () => "test-service"} };
const matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
function model(file = "assembly.step", count = 1) {
  const entry = { file, kind: "assembly", sourceFormat: "step", hash: `revision-${file}`,
    documentHash: "document", appearanceHash: "appearance", url: `http://cad.test/${file}/` };
  const descriptor = { kind: "assembly-package", viewId: `view-${file}`, components: {}, occurrences: [],
    assembly: { root: { id: "root", nodeType: "assembly", children: [] } } };
  const componentMeshDataByCid = {}, componentIdentityByCid = {}, componentLodLevelByCid = {};
  for (let i = 0; i < count; i++) {
    const cid = `c${i}`, surfaceInput = i.toString(16).padStart(64, "0"), surfaceObject = "a".repeat(64);
    descriptor.components[cid] = { surfaceInput };
    descriptor.occurrences.push({ id: `o${i}`, name: cid, component: cid, transform: [...matrix], material: { roughness: 0.5 } });
    descriptor.assembly.root.children.push({ id: `o${i}`, nodeType: "part", children: [] });
    componentIdentityByCid[cid] = { surfaceInput, surfaceObject, surfUrl: `http://cad.test/${cid}.surf` };
    componentLodLevelByCid[cid] = 1;
    componentMeshDataByCid[cid] = { vertices: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), indices: new Uint32Array([0, 1, 2]),
      bounds: { min: [0, 0, 0], max: [1, 1, 0] }, lodLevel: 1,
      parts: [{ id: "part", triangleOffset: 0, triangleCount: 1 }] };
  }
  return { entry, context: { descriptor, componentMeshDataByCid, componentIdentityByCid, componentLodLevelByCid,
    meshHash: `${entry.hash}:${entry.appearanceHash}`, complete: true,
    meshData: buildComposedPackageMeshData(descriptor, componentMeshDataByCid) } };
}

test("a 317-component working set survives component-LRU-sized churn with private occurrence metadata", () => {
  const cache = createCompletedPackageCache(), a = model("a.step", 317), b = model("b.step", 40);
  assert.equal(cache.set(root, a.entry, a.context), true);
  assert.equal(cache.set(root, b.entry, b.context), true);
  // Simulate scene-owned metadata changes after admission, including component
  // bounds. Typed display buffers are immutable and intentionally shared.
  a.context.descriptor.occurrences[0].transform[3] = 900;
  a.context.componentMeshDataByCid.c0.bounds.max[0] = 900;
  const first = cache.get({ ...root }, a.entry);
  assert.equal(first.meshData.parts.length, 317);
  assert.equal(first.meshData.parts[0].transform[3], 0);
  assert.equal(first.componentMeshDataByCid.c0.bounds.max[0], 1);
  assert.equal(first.componentMeshDataByCid.c0.vertices, a.context.componentMeshDataByCid.c0.vertices);
  first.meshData.parts[0].material.roughness = 1;
  first.descriptor.occurrences[0].transform[3] = 42;
  first.componentLodLevelByCid.c0 = 3;
  const second = cache.get(root, a.entry);
  assert.equal(second.meshData.parts[0].material.roughness, 0.5);
  assert.equal(second.meshData.parts[0].transform[3], 0);
  assert.equal(second.componentLodLevelByCid.c0, 1);
  assert.equal(second.componentKeyByCid.c0,
    surfTessellationCacheKey("", lodTessellationForLevel(1), second.componentIdentityByCid.c0));
  assert.equal(cache.stats().entries, 2);
});

test("root, service generation, revision, source appearance and replacement runtime view are exact boundaries", () => {
  const cache = createCompletedPackageCache(), a = model();
  const populate = () => assert.equal(cache.set(root, a.entry, a.context), true);
  populate();
  assert.equal(cache.get({ ...root, workspaceId: "other" }, a.entry), null);
  assert.equal(cache.get({ ...root, resources: {cacheKey: () => "other-service"} }, a.entry), null);
  assert.ok(cache.get({ ...root }, a.entry), "a replacement client for the same root may reopen a closed tab");
  for (const change of [{ hash: "new" }, { documentHash: "new" }, { appearanceHash: "new" },
    { url: "http://cad.test/new/" }, { sourceSidecar: { appearance: { material: "new" } } }, { editingPreview: true }]) {
    populate();
    assert.equal(cache.get(root, { ...a.entry, ...change }), null);
    assert.equal(cache.stats().entries, 0, "the obsolete revision is released");
  }
  for (const descriptor of [{ ...a.context.descriptor, viewId: "replacement" },
    { ...a.context.descriptor, components: { c0: { surfaceInput: "b".repeat(64) } } },
    { ...a.context.descriptor, components: { c0: { ...a.context.descriptor.components.c0, surfaceObject: "b".repeat(64) } } }]) {
    populate();
    assert.equal(cache.get(root, a.entry, { descriptor }), null);
  }
  const anonymous = {};
  assert.equal(cache.set(anonymous, a.entry, a.context), true);
  assert.equal(cache.get({}, a.entry), null);
  assert.ok(cache.get(anonymous, a.entry));
});

test("recognition reads only private exact identities from the matching root, revision and runtime view", () => {
  const cache = createCompletedPackageCache(), a = model("identities.step", 317);
  const populate = () => assert.equal(cache.set(root, a.entry, a.context), true);
  populate();
  const before = cache.stats();
  const identities = cache.peekComponentIdentities({ ...root }, a.entry, { descriptor: a.context.descriptor });
  assert.equal(Object.keys(identities).length, 317);
  assert.deepEqual(Object.keys(identities.c0).sort(), ["surfaceInput", "surfaceObject"]);
  assert.deepEqual(identities.c0, { surfaceInput: "0".repeat(64), surfaceObject: "a".repeat(64) });
  identities.c0.surfaceObject = "b".repeat(64);
  delete identities.c1;
  const again = cache.peekComponentIdentities(root, a.entry, { descriptor: a.context.descriptor });
  assert.equal(again.c0.surfaceObject, "a".repeat(64));
  assert.ok(again.c1);
  assert.equal(cache.stats().bytes, before.bytes, "identity reads retain no geometry or metadata copies");
  assert.equal(cache.peekComponentIdentities(root, a.entry), null, "a descriptor is required to prove the runtime view");
  for (const client of [{ ...root, workspaceId: "other" }, { ...root, resources: {cacheKey: () => "other-service"} }]) {
    assert.equal(cache.peekComponentIdentities(client, a.entry, { descriptor: a.context.descriptor }), null);
  }
  for (const change of [{ hash: "new" }, { documentHash: "new" }, { editingPreview: true }]) {
    populate();
    assert.equal(cache.peekComponentIdentities(root, { ...a.entry, ...change }, { descriptor: a.context.descriptor }), null);
  }
  for (const descriptor of [{ ...a.context.descriptor, viewId: "new-view" },
    { ...a.context.descriptor, components: { ...a.context.descriptor.components, c0: { surfaceInput: "b".repeat(64) } } }]) {
    populate();
    assert.equal(cache.peekComponentIdentities(root, a.entry, { descriptor }), null);
  }
});

test("only complete exact display publications are admitted; pending work and runtime objects are excluded", () => {
  const cache = createCompletedPackageCache(), a = model();
  for (const sourceFormat of ["stl", "glb", "urdf", "dxf"]) {
    assert.equal(cache.set(root, { ...a.entry, kind: sourceFormat, sourceFormat }, a.context), false,
      "a format without exact topology cannot enter the package working-set cache");
  }
  for (const context of [{ ...a.context, complete: false }, { ...a.context, lodPending: {} },
    { ...a.context, componentMeshDataByCid: {} }, { ...a.context, meshHash: "old" }]) {
    assert.equal(cache.set(root, a.entry, context), false);
  }
  a.context.componentMeshDataByCid.c0.lodKey = surfTessellationCacheKey("", lodTessellationForLevel(0), a.context.componentIdentityByCid.c0);
  assert.equal(cache.set(root, a.entry, a.context), false, "a different L/Q/R cannot masquerade as the displayed tier");
  delete a.context.componentMeshDataByCid.c0.lodKey;
  a.context.componentIdentityByCid.c0.surfaceObject = "invalid";
  assert.equal(cache.set(root, a.entry, a.context), false);
  a.context.componentIdentityByCid.c0.surfaceObject = "a".repeat(64);
  a.context.controller = new AbortController();
  a.context.componentLodBundleByCid = { c0: { runtime: true } };
  assert.equal(cache.set(root, a.entry, a.context), true);
  const result = cache.get(root, a.entry);
  assert.equal(result.controller, undefined);
  assert.equal(result.componentLodBundleByCid, undefined);
  assert.equal(cache.set(root, a.entry, { ...a.context, lodPending: {} }), false);
  assert.equal(cache.get(root, a.entry), null, "a pending replacement cannot resurrect an older same-revision detail snapshot");
  a.context.componentMeshDataByCid.c0.scene = new AbortController();
  assert.equal(cache.set(root, a.entry, a.context), false, "unexpected mutable runtime objects do not enter display data");
});

test("byte and entry limits account for full backing allocations and evict least-recently-used packages", () => {
  const a = model("a.step"), b = model("b.step"), c = model("c.step");
  const packed = new ArrayBuffer(64 * 1024);
  a.context.componentMeshDataByCid.c0.vertices = new Float32Array(packed, 0, 9);
  a.context.componentMeshDataByCid.c0.normals = new Float32Array(packed, 64, 9);
  const cache = createCompletedPackageCache({ maxEntries: 2, maxBytes: 1024 * 1024 });
  cache.set(root, a.entry, a.context);
  assert.equal(cache.stats().typedBytes, packed.byteLength + 12, "subviews retain their complete backing, once");
  assert.equal(cache.stats({ excludeBuffers: [packed] }).typedBytes, 12);
  cache.set(root, b.entry, b.context);
  cache.get(root, a.entry);
  cache.set(root, c.entry, c.context);
  assert.equal(cache.get(root, b.entry), null);
  assert.ok(cache.get(root, a.entry));
  const tight = createCompletedPackageCache({ maxBytes: 32 * 1024 });
  assert.equal(tight.set(root, a.entry, a.context), false);
  assert.equal(tight.stats().bytes, 0);
  const one = model("one.step"), two = model("two.step");
  const sizing = createCompletedPackageCache();
  sizing.set(root, one.entry, one.context);
  const bounded = createCompletedPackageCache({ maxBytes: sizing.stats().bytes + 100 });
  bounded.set(root, one.entry, one.context);
  bounded.set(root, two.entry, two.context);
  assert.equal(bounded.get(root, one.entry), null, "bytes evict independently of entry count");
  assert.equal(bounded.stats().entries, 1);
  const metadata = model("metadata.step");
  metadata.context.descriptor.label = "x".repeat(32 * 1024);
  assert.equal(tight.set(root, metadata.entry, metadata.context), false, "structural metadata participates in the bound");
  assert.equal(tight.stats().bytes, 0);
  const shared = model("shared.step");
  shared.context.componentMeshDataByCid = a.context.componentMeshDataByCid;
  const deduplicated = createCompletedPackageCache();
  deduplicated.set(root, a.entry, a.context);
  deduplicated.set(root, shared.entry, shared.context);
  assert.equal(deduplicated.stats().typedBytes, packed.byteLength + 12, "packages sharing a backing allocation charge it only once");
});

test("memory diagnostics charge inactive package data and exclude buffers already owned by a scene or staging", () => {
  completedPackages.clear();
  try {
    const a = model();
    completedPackages.set(root, a.entry, a.context);
    const total = renderAssetCacheStatsWithPackages().completedPackages;
    assert.equal(total.typedBytes, 84);
    assert.ok(total.metadataBytes > 0);
    const displayed = renderMemoryAccounting({ cadScene: { meshData: a.context.meshData } });
    // The no-record diagnostic sees composed arrays directly for this single
    // component; its cache must not count those same packed arrays twice.
    assert.equal(displayed.additionalAssetCaches.completedPackages.typedBytes, 0);
    const inactive = renderMemoryAccounting(null);
    assert.equal(inactive.additionalAssetCaches.completedPackages.typedBytes, 84);
    assert.ok(inactive.memoryPolicy.retainedByCategory.assetCaches >= total.bytes);
    assert.equal(completedPackages.clear(), 1);
    assert.equal(renderMemoryAccounting(null).assetCaches.completedPackages.bytes, 0);
  } finally { completedPackages.clear(); }
});

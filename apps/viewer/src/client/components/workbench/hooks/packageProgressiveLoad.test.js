// Progressive publish of a component package (design/viewer-memory.md §6).
// Fake components (no tessellation): the policy under test is batching,
// ordering, staleness and release, not geometry.
import assert from "node:assert/strict";
import test from "node:test";

import { buildComposedPackageMeshData } from "cadgen-js/lib/assembly/meshData.js";

import {
  PROGRESSIVE_PUBLISH_MAX_BYTES,
  PROGRESSIVE_PUBLISH_MAX_COMPONENTS,
  createProgressivePackageLoader,
  orderComponentsForProgressiveLoad,
  progressiveLoadStage,
  progressivePublishDue,
  publishMeshCostAccounting,
  meshStateIsComplete,
  tolerantAnimationClip,
  createDecodeSizeEstimator,
  PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  PROGRESSIVE_LOAD_UNMEASURED_SHARE
} from "./packageProgressiveLoad.js";
import { createAnimationFrame } from "cadgen-js/common/animationRuntime.js";
import * as THREE from "three";

const IDENTITY_4X4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

function translation(x, y, z) {
  return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1];
}

// One triangle per component; `floats` pads the vertex array so a component
// can weigh whatever the byte-budget test needs.
function fakeComponent(cid, { floats = 9 } = {}) {
  const vertices = new Float32Array(Math.max(9, floats));
  vertices.set([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  return {
    cid,
    vertices,
    normals: new Float32Array(9).fill(0).map((_, i) => (i % 3 === 2 ? 1 : 0)),
    colors: new Float32Array(0),
    indices: new Uint32Array([0, 1, 2]),
    parts: [{ id: "o1", occurrenceId: "o1", primitiveIndex: 0, vertexOffset: 0, vertexCount: 3, triangleOffset: 0, triangleCount: 1 }],
    bounds: { min: [0, 0, 0], max: [1, 1, 0] }
  };
}

function makeDescriptor({ componentCount, occurrenceCount, transformFor = () => IDENTITY_4X4 }) {
  const components = {};
  for (let i = 0; i < componentCount; i += 1) {
    components[`c${i}`] = { surf: `components/c${i}.surf` };
  }
  const occurrences = [];
  for (let i = 0; i < occurrenceCount; i += 1) {
    occurrences.push({ id: `o1.${i + 1}`, name: `part_${i}`, component: `c${i % componentCount}`, transform: transformFor(i) });
  }
  return {
    kind: "assembly-package",
    entryKind: "assembly",
    components,
    occurrences,
    assembly: {
      root: { id: "o1", name: "demo", nodeType: "assembly", children: occurrences.map(({ id }) => ({ id, nodeType: "part", children: [] })) }
    }
  };
}

// Deterministic out-of-order arrival: each load resolves on a later microtask
// turn, so with concurrency > 1 completion order differs from start order.
function makeLoader(descriptor, { componentFloats = () => 9 } = {}) {
  const all = {};
  const loadComponent = async (cid) => {
    const turns = 1 + (Number(cid.slice(1)) % 3);
    for (let i = 0; i < turns; i += 1) {
      await Promise.resolve();
    }
    all[cid] = fakeComponent(cid, { floats: componentFloats(cid) });
    return all[cid];
  };
  return { loadComponent, all };
}

test("policy constants: a batch publishes at either ceiling, whichever first", () => {
  assert.equal(PROGRESSIVE_PUBLISH_MAX_COMPONENTS, 32);
  assert.equal(PROGRESSIVE_PUBLISH_MAX_BYTES, 64 * 1024 * 1024);
  assert.equal(progressivePublishDue({ pendingComponents: 31, pendingBytes: 0 }), false);
  assert.equal(progressivePublishDue({ pendingComponents: 32, pendingBytes: 0 }), true);
  assert.equal(progressivePublishDue({ pendingComponents: 1, pendingBytes: PROGRESSIVE_PUBLISH_MAX_BYTES }), true);
  assert.equal(progressivePublishDue({ pendingComponents: 1, pendingBytes: 10 }, { maxComponents: 4, maxBytes: 10 }), true);
  assert.equal(progressiveLoadStage(3, 12), "loading components 3/12");
});

test("batches publish in order with monotonically increasing component counts; the last is final", async () => {
  const descriptor = makeDescriptor({ componentCount: 10, occurrenceCount: 25 });
  const { loadComponent } = makeLoader(descriptor);
  const publishes = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 4,
    maxComponents: 4,
    onPublish: ({ meshData, componentMeshDataByCid, loaded, total, final }) => publishes.push({
      loaded, total, final,
      cids: Object.keys(componentMeshDataByCid).length,
      parts: meshData.parts.length,
      missing: meshData.missingComponentIds.length
    })
  });
  const result = await loader.run();
  assert.equal(result.total, 10);
  assert.equal(result.loaded, 10);
  assert.equal(result.publishes, 3, "4 + 4 + 2 components");
  assert.deepEqual(publishes.map((p) => p.loaded), [4, 8, 10]);
  assert.deepEqual(publishes.map((p) => p.cids), [4, 8, 10]);
  assert.deepEqual(publishes.map((p) => p.final), [false, false, true]);
  for (let i = 1; i < publishes.length; i += 1) {
    assert.ok(publishes[i].parts > publishes[i - 1].parts, "occurrence count grows with every batch");
  }
  // Partial compositions: occurrences whose component has not arrived are
  // absent (listed in missingComponentIds), never composed from another cid.
  assert.equal(publishes[0].parts + publishes[0].missing, 25);
  assert.equal(publishes.at(-1).missing, 0);
  assert.equal(publishes.at(-1).parts, 25);
});

test("the byte ceiling publishes a batch before the component ceiling", async () => {
  const descriptor = makeDescriptor({ componentCount: 6, occurrenceCount: 6 });
  // 40 floats * 4 B = 160 B of vertices + 36 B normals + 12 B indices ≈ 208 B each.
  const { loadComponent } = makeLoader(descriptor, { componentFloats: () => 40 });
  const publishes = [];
  await createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 1,
    maxComponents: 100,
    maxBytes: 400,
    onPublish: ({ loaded, final }) => publishes.push({ loaded, final })
  }).run();
  assert.deepEqual(publishes, [
    { loaded: 2, final: false },
    { loaded: 4, final: false },
    { loaded: 6, final: true }
  ]);
});

test("the final publish equals the single post-load composition", async () => {
  const descriptor = makeDescriptor({ componentCount: 9, occurrenceCount: 30, transformFor: (i) => translation(i, -i, 2 * i) });
  const { loadComponent, all } = makeLoader(descriptor);
  let finalPublish = null;
  await createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 3,
    maxComponents: 4,
    onPublish: (publish) => {
      if (publish.final) {
        finalPublish = publish;
      }
    }
  }).run();
  assert.ok(finalPublish);
  const single = buildComposedPackageMeshData(descriptor, all);
  assert.equal(finalPublish.meshData.parts.length, single.parts.length);
  assert.deepEqual(finalPublish.meshData.bounds, single.bounds);
  assert.deepEqual(finalPublish.meshData.missingComponentIds, []);
  assert.deepEqual(finalPublish.meshData.assemblyRoot, single.assemblyRoot);
  assert.equal(finalPublish.meshData.partTransformsBaked, single.partTransformsBaked);
  for (let i = 0; i < single.parts.length; i += 1) {
    const { sourceMesh: a, ...restA } = finalPublish.meshData.parts[i];
    const { sourceMesh: b, ...restB } = single.parts[i];
    assert.equal(a, b, "shared component buffers, by reference");
    assert.deepEqual(restA, restB);
  }
  assert.deepEqual(
    Object.keys(finalPublish.componentMeshDataByCid).sort(),
    Object.keys(all).sort()
  );
});

test("a superseded request publishes nothing further and releases what it loaded", async () => {
  const descriptor = makeDescriptor({ componentCount: 12, occurrenceCount: 12 });
  const { loadComponent } = makeLoader(descriptor);
  let current = true;
  const publishes = [];
  let loads = 0;
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent: async (cid, component) => {
      loads += 1;
      return loadComponent(cid, component);
    },
    concurrency: 2,
    maxComponents: 3,
    isCurrent: () => current,
    onPublish: ({ loaded }) => {
      publishes.push(loaded);
      if (publishes.length === 2) {
        current = false; // superseded by another entry
      }
    }
  });
  await assert.rejects(loader.run(), (error) => error.name === "AbortError");
  assert.deepEqual(publishes, [3, 6], "nothing after the supersede");
  assert.ok(loads < 12, `stopped fetching (${loads} of 12 started)`);
  assert.equal(loader.retainedComponentCount(), 0, "partial arrays released");
});

test("an aborted load (loader rejects) publishes nothing further and releases", async () => {
  const descriptor = makeDescriptor({ componentCount: 8, occurrenceCount: 8 });
  const { loadComponent } = makeLoader(descriptor);
  const controller = new AbortController();
  const publishes = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent: async (cid, component) => {
      if (controller.signal.aborted) {
        throw new DOMException("aborted", "AbortError");
      }
      const meshData = await loadComponent(cid, component);
      if (controller.signal.aborted) {
        throw new DOMException("aborted", "AbortError");
      }
      return meshData;
    },
    concurrency: 2,
    maxComponents: 2,
    isCurrent: () => !controller.signal.aborted,
    onPublish: ({ loaded }) => {
      publishes.push(loaded);
      if (loaded === 4) {
        controller.abort();
      }
    }
  });
  await assert.rejects(loader.run(), (error) => error.name === "AbortError");
  assert.deepEqual(publishes, [2, 4]);
  assert.equal(loader.retainedComponentCount(), 0);
});

test("a viewport-LOD swap that lands mid-load is kept by the next batch", async () => {
  const descriptor = makeDescriptor({ componentCount: 6, occurrenceCount: 6 });
  const { loadComponent } = makeLoader(descriptor);
  let workingSet = null;
  const publishes = [];
  await createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 1,
    maxComponents: 2,
    swappedComponents: () => workingSet,
    onPublish: ({ meshData, componentMeshDataByCid, loaded }) => {
      publishes.push({ loaded, keys: meshData.parts.map((part) => part.sourceMeshKey) });
      workingSet = componentMeshDataByCid;
      if (loaded === 2) {
        // The scheduler swaps the first published component to level 2.
        const [cid] = Object.keys(componentMeshDataByCid);
        const finer = { ...componentMeshDataByCid[cid], lodLevel: 2 };
        workingSet = { ...componentMeshDataByCid, [cid]: finer };
      }
    }
  }).run();
  assert.equal(publishes.length, 3);
  const swappedKeys = publishes.at(-1).keys.filter((key) => key.endsWith(":l2"));
  assert.equal(swappedKeys.length, 1, "the level-2 swap survives later batches");
});

test("load order puts the extreme-placed components first so the first frame spans the model", () => {
  const descriptor = makeDescriptor({
    componentCount: 8,
    occurrenceCount: 16,
    transformFor: (i) => translation(i === 13 ? 500 : i, i === 6 ? -900 : 0, i === 10 ? 40 : 0)
  });
  const ordered = orderComponentsForProgressiveLoad(descriptor).map(([cid]) => cid);
  assert.equal(ordered.length, 8);
  assert.deepEqual([...ordered].sort(), Object.keys(descriptor.components).sort(), "every component once");
  // x-min → occurrence 0 (c0); x-max → occurrence 13 (c5); y-min → occurrence 6 (c6);
  // y-max → first at y=0 (c0, deduped); z-max → occurrence 10 (c2).
  assert.deepEqual(ordered.slice(0, 4), ["c0", "c5", "c6", "c2"]);
  // Null transforms (identity) and missing components do not throw.
  const bare = { components: { a: {}, b: {} }, occurrences: [{ component: "a" }, { component: "zzz" }] };
  assert.deepEqual(orderComponentsForProgressiveLoad(bare).map(([cid]) => cid), ["a", "b"]);
});

test("an empty package composes once and surfaces the descriptor's own error", async () => {
  const descriptor = { kind: "assembly-package", components: {}, occurrences: [] };
  await assert.rejects(
    createProgressivePackageLoader({ descriptor, loadComponent: async () => null, onPublish: () => {} }).run(),
    /no occurrences/
  );
});

test("recomposition cost per publish: 3000 occurrences / 800 components", async (t) => {
  const descriptor = makeDescriptor({
    componentCount: 800,
    occurrenceCount: 3000,
    transformFor: (i) => translation((i % 37) * 10, (i % 53) * 7, (i % 11) * 3)
  });
  const { loadComponent } = makeLoader(descriptor);
  const composeMs = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 8,
    onPublish: (publish) => composeMs.push(publish.composeMs)
  });
  const started = performance.now();
  const result = await loader.run();
  const totalMs = performance.now() - started;
  assert.equal(result.publishes, Math.ceil(800 / PROGRESSIVE_PUBLISH_MAX_COMPONENTS));
  // Per-frame animation binding (label index over every part) at this size —
  // the cost the render module pays on each publish/frame, not a separate attach.
  let bindMs = 0;
  {
    const lastPublish = buildComposedPackageMeshData(descriptor, Object.fromEntries(
      Object.keys(descriptor.components).map((cid) => [cid, fakeComponent(cid)])
    ));
    const t0 = performance.now();
    for (let i = 0; i < 5; i += 1) createAnimationFrame(THREE, lastPublish);
    bindMs = (performance.now() - t0) / 5;
  }
  const max = Math.max(...composeMs);
  const mean = composeMs.reduce((sum, ms) => sum + ms, 0) / composeMs.length;
  const last = composeMs.at(-1);
  t.diagnostic(`recompose per publish: mean ${mean.toFixed(2)} ms, max ${max.toFixed(2)} ms, final ${last.toFixed(2)} ms, ${composeMs.length} publishes, run ${totalMs.toFixed(0)} ms; animation label bind over 3000 parts ${bindMs.toFixed(2)} ms`);
  // Generous ceiling: a publish is a reference walk of the occurrence list.
  assert.ok(max < 500, `max recompose ${max} ms`);
});

test("window.__cadMeshCost updates on every publish and clears on cancel", async () => {
  assert.equal(publishMeshCostAccounting({ meshData: {}, componentMeshDataByCid: {}, loaded: 0, total: 0, publishCount: 0, final: false }), null, "no window: harmless");
  globalThis.window = {};
  try {
    const descriptor = makeDescriptor({ componentCount: 6, occurrenceCount: 12 });
    const { loadComponent } = makeLoader(descriptor, { componentFloats: () => 12 });
    const seen = [];
    await createProgressivePackageLoader({
      descriptor,
      loadComponent,
      concurrency: 1,
      maxComponents: 2,
      onPublish: (publish) => {
        publishMeshCostAccounting(publish);
        seen.push({ ...window.__cadMeshCost });
      }
    }).run();
    assert.deepEqual(seen.map((cost) => cost.publishCount), [1, 2, 3]);
    assert.deepEqual(seen.map((cost) => cost.componentCount), [2, 4, 6]);
    assert.deepEqual(seen.map((cost) => cost.final), [false, false, true]);
    assert.equal(seen.at(-1).totalComponents, 6);
    // 12 floats * 4 B + 36 B normals + 12 B indices = 96 B per component; one triangle each.
    assert.deepEqual(seen.map((cost) => cost.componentTotalBytes), [192, 384, 576]);
    assert.deepEqual(seen.map((cost) => cost.componentTotalTriangles), [2, 4, 6]);
    assert.equal(seen.at(-1).composed.triangleCount, 12, "composed cost counts every occurrence");
    assert.ok(seen[1].at >= seen[0].at);
    publishMeshCostAccounting(null);
    assert.equal(window.__cadMeshCost, null);
  } finally {
    delete globalThis.window;
  }
});

test("the render module attaches on the FIRST publish; absent labels are no-ops until they arrive; validation waits for the complete model", async () => {
  const descriptor = makeDescriptor({ componentCount: 9, occurrenceCount: 18 });
  const { loadComponent } = makeLoader(descriptor);
  // A real clip over the real runtime handle: rotates every occurrence by label.
  const clip = {
    id: "wave", duration: 1, loop: true,
    update(t, m) {
      for (const occurrence of descriptor.occurrences) {
        m.get(occurrence.name).rotate([0, 0, 1], 90 * t);
      }
    }
  };
  const runs = [];
  const validations = [];
  await createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 3,
    maxComponents: 4,
    onPublish: ({ meshData, final }) => {
      const meshState = { file: "hand.step", meshData, assemblyInteractionReady: final };
      const complete = meshStateIsComplete(meshState);
      validations.push(complete);
      // The workspace hands the viewer the strict clip for the complete model
      // and the tolerant one while partial; the module is attached either way.
      const playable = complete ? clip : tolerantAnimationClip(clip);
      const frame = createAnimationFrame(THREE, meshData);
      playable.update(0.5, frame.model);
      runs.push({ bound: frame.matrices.size, present: meshData.parts.length });
    }
  }).run();
  assert.equal(runs.length, 3, "invoked on every publish, the first included");
  // Every present occurrence is bound; absent ones were no-ops (no throw).
  for (const run of runs) {
    assert.equal(run.bound, run.present);
  }
  assert.ok(runs[0].bound > 0 && runs[0].bound < 18, "partial: some occurrences bound, the rest pending");
  assert.equal(runs.at(-1).bound, 18, "late occurrences bound once they arrived");
  assert.deepEqual(validations, [false, false, true], "clip validation gate: complete model only");
  // The strict clip against a partial composition is the failure the wrapper prevents.
  const partial = buildComposedPackageMeshData(descriptor, { c0: fakeComponent("c0") });
  assert.throws(() => clip.update(0.5, createAnimationFrame(THREE, partial).model), /no occurrence labeled/);
  assert.equal(meshStateIsComplete(null), false);
  assert.equal(meshStateIsComplete({ meshData: { parts: null }, assemblyInteractionReady: false }), false, "assembly preview");
  assert.equal(meshStateIsComplete({ meshData: { parts: [], missingComponentIds: ["c1"] } }), false);
  assert.equal(meshStateIsComplete({ meshData: { parts: [] } }), true, "non-package meshes carry no flag");
  assert.equal(tolerantAnimationClip(null), null);
});

test("byte-aware admission: decodes in flight stay under the byte budget, and under the count cap", async () => {
  // Each fake component decodes to exactly its hint (ratio 1): 40 floats*4 + 36 + 12 = 208 B.
  const descriptor = makeDescriptor({ componentCount: 24, occurrenceCount: 24 });
  const { loadComponent } = makeLoader(descriptor, { componentFloats: () => 40 });
  let inFlight = 0;
  const inFlightAtStart = [];
  const wrapped = async (cid, component) => {
    inFlight += 1;
    inFlightAtStart.push(inFlight);
    try {
      return await loadComponent(cid, component);
    } finally {
      inFlight -= 1;
    }
  };
  const budget = 500; // fits two 208 B components, not three
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent: wrapped,
    sizeHint: async () => 208,
    concurrency: 8,
    maxInFlightBytes: budget,
    onPublish: () => {}
  });
  await loader.run();
  assert.equal(inFlightAtStart.length, 24);
  // Before any decode is measured the estimate is budget/4 = 125 B: at most 4 unmeasured admissions.
  assert.ok(loader.peakInFlight() <= PROGRESSIVE_LOAD_UNMEASURED_SHARE, `peak ${loader.peakInFlight()}`);
  // Once measured (ratio 1 → 208 B each) only two fit the 500 B budget; the
  // first eight admissions span the unmeasured→measured transition.
  assert.ok(inFlightAtStart.slice(8).every((n) => n <= 2), `later admissions ${inFlightAtStart}`);
  // Count cap still binds when bytes do not.
  const { loadComponent: load2 } = makeLoader(descriptor, { componentFloats: () => 40 });
  const wide = createProgressivePackageLoader({
    descriptor, loadComponent: load2, sizeHint: async () => 1, concurrency: 3,
    maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES, onPublish: () => {}
  });
  await wide.run();
  assert.ok(wide.peakInFlight() <= 3 && wide.peakInFlight() >= 2, `count cap ${wide.peakInFlight()}`);
  // A component larger than the whole budget runs alone rather than never.
  const { loadComponent: load3 } = makeLoader(descriptor, { componentFloats: () => 400 });
  const huge = createProgressivePackageLoader({
    descriptor, loadComponent: load3, sizeHint: async () => 1648, concurrency: 8, maxInFlightBytes: 100, onPublish: () => {}
  });
  const result = await huge.run();
  assert.equal(result.loaded, 24);
  // The estimator itself.
  const estimator = createDecodeSizeEstimator({ maxInFlightBytes: 400 });
  assert.equal(estimator.estimate(10), 100, "unmeasured share");
  estimator.observe(10, 300);
  assert.equal(estimator.estimate(20), 600, "hint scaled by the measured ratio");
  assert.equal(estimator.estimate(null), 300, "no hint: running mean");
});

test("recomposition cost per publish: 3000 occurrences / 800 components", async (t) => {
  const descriptor = makeDescriptor({
    componentCount: 800,
    occurrenceCount: 3000,
    transformFor: (i) => translation((i % 37) * 10, (i % 53) * 7, (i % 11) * 3)
  });
  const { loadComponent } = makeLoader(descriptor);
  const composeMs = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 8,
    onPublish: (publish) => composeMs.push(publish.composeMs)
  });
  const started = performance.now();
  const result = await loader.run();
  const totalMs = performance.now() - started;
  assert.equal(result.publishes, Math.ceil(800 / PROGRESSIVE_PUBLISH_MAX_COMPONENTS));
  // Per-frame animation binding (label index over every part) at this size —
  // the cost the render module pays on each publish/frame, not a separate attach.
  let bindMs = 0;
  {
    const lastPublish = buildComposedPackageMeshData(descriptor, Object.fromEntries(
      Object.keys(descriptor.components).map((cid) => [cid, fakeComponent(cid)])
    ));
    const t0 = performance.now();
    for (let i = 0; i < 5; i += 1) createAnimationFrame(THREE, lastPublish);
    bindMs = (performance.now() - t0) / 5;
  }
  const max = Math.max(...composeMs);
  const mean = composeMs.reduce((sum, ms) => sum + ms, 0) / composeMs.length;
  const last = composeMs.at(-1);
  t.diagnostic(`recompose per publish: mean ${mean.toFixed(2)} ms, max ${max.toFixed(2)} ms, final ${last.toFixed(2)} ms, ${composeMs.length} publishes, run ${totalMs.toFixed(0)} ms; animation label bind over 3000 parts ${bindMs.toFixed(2)} ms`);
  // Generous ceiling: a publish is a reference walk of the occurrence list.
  assert.ok(max < 500, `max recompose ${max} ms`);
});

test("window.__cadMeshCost updates on every publish and clears on cancel", async () => {
  assert.equal(publishMeshCostAccounting({ meshData: {}, componentMeshDataByCid: {}, loaded: 0, total: 0, publishCount: 0, final: false }), null, "no window: harmless");
  globalThis.window = {};
  try {
    const descriptor = makeDescriptor({ componentCount: 6, occurrenceCount: 12 });
    const { loadComponent } = makeLoader(descriptor, { componentFloats: () => 12 });
    const seen = [];
    await createProgressivePackageLoader({
      descriptor,
      loadComponent,
      concurrency: 1,
      maxComponents: 2,
      onPublish: (publish) => {
        publishMeshCostAccounting(publish);
        seen.push({ ...window.__cadMeshCost });
      }
    }).run();
    assert.deepEqual(seen.map((cost) => cost.publishCount), [1, 2, 3]);
    assert.deepEqual(seen.map((cost) => cost.componentCount), [2, 4, 6]);
    assert.deepEqual(seen.map((cost) => cost.final), [false, false, true]);
    assert.equal(seen.at(-1).totalComponents, 6);
    // 12 floats * 4 B + 36 B normals + 12 B indices = 96 B per component; one triangle each.
    assert.deepEqual(seen.map((cost) => cost.componentTotalBytes), [192, 384, 576]);
    assert.deepEqual(seen.map((cost) => cost.componentTotalTriangles), [2, 4, 6]);
    assert.equal(seen.at(-1).composed.triangleCount, 12, "composed cost counts every occurrence");
    assert.ok(seen[1].at >= seen[0].at);
    publishMeshCostAccounting(null);
    assert.equal(window.__cadMeshCost, null);
  } finally {
    delete globalThis.window;
  }
});

// Progressive publish of a component package (design/viewer-memory.md §6).
// Fake components (no tessellation): the policy under test is batching,
// ordering, staleness and release, not geometry.
import assert from "node:assert/strict";
import test from "node:test";

import { buildComposedPackageMeshData } from "cadgen-js/lib/assembly/meshData.js";

import {
  PROGRESSIVE_PUBLISH_FIRST_BYTES,
  PROGRESSIVE_PUBLISH_FIRST_COMPONENTS,
  PROGRESSIVE_PUBLISH_MAX_BYTES,
  PROGRESSIVE_PUBLISH_MAX_COMPONENTS,
  createProgressivePackageLoader,
  orderComponentsForProgressiveLoad,
  progressiveLoadProgress,
  progressivePublishCeilings,
  progressivePublishDue,
  publishMeshCostAccounting,
  meshStateIsComplete,
  shouldRetainCompleteSameFileMesh,
  tolerantAnimationClip,
  createDecodeSizeEstimator,
  PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  PROGRESSIVE_LOAD_UNMEASURED_SHARE
} from "./packageProgressiveLoad.js";
import { createViewerMemoryPolicy } from "../../../render/viewerMemoryPolicy.js";
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

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test("policy constants: a batch publishes at either ceiling, and the ceilings double", () => {
  assert.equal(PROGRESSIVE_PUBLISH_FIRST_COMPONENTS, 8);
  assert.equal(PROGRESSIVE_PUBLISH_FIRST_BYTES, 8 * 1024 * 1024);
  assert.equal(PROGRESSIVE_PUBLISH_MAX_COMPONENTS, 256);
  assert.equal(PROGRESSIVE_PUBLISH_MAX_BYTES, 128 * 1024 * 1024);
  // The first batch is the smallest, so first geometry arrives soonest.
  assert.equal(progressivePublishDue({ pendingComponents: 7, pendingBytes: 0, publishCount: 0 }), false);
  assert.equal(progressivePublishDue({ pendingComponents: 8, pendingBytes: 0, publishCount: 0 }), true);
  assert.equal(progressivePublishDue({ pendingComponents: 8, pendingBytes: 0, publishCount: 1 }), false);
  assert.equal(progressivePublishDue({ pendingComponents: 16, pendingBytes: 0, publishCount: 1 }), true);
  assert.equal(progressivePublishDue({ pendingComponents: 1, pendingBytes: PROGRESSIVE_PUBLISH_FIRST_BYTES, publishCount: 0 }), true);
  assert.equal(progressivePublishDue({ pendingComponents: 1, pendingBytes: PROGRESSIVE_PUBLISH_FIRST_BYTES, publishCount: 1 }), false);
  // Doubling stops at the last ceilings and stays there.
  assert.deepEqual(progressivePublishCeilings(5), { components: 256, bytes: 128 * 1024 * 1024 });
  assert.deepEqual(progressivePublishCeilings(99), { components: 256, bytes: 128 * 1024 * 1024 });
  // A caller pinning the last ceiling below the first gets that size flat.
  assert.deepEqual(progressivePublishCeilings(0, { maxComponents: 4, maxBytes: 10 }), { components: 4, bytes: 10 });
  assert.deepEqual(progressivePublishCeilings(9, { maxComponents: 4, maxBytes: 10 }), { components: 4, bytes: 10 });
  assert.equal(progressivePublishDue({ pendingComponents: 1, pendingBytes: 10 }, { maxComponents: 4, maxBytes: 10 }), true);
  assert.deepEqual(progressiveLoadProgress(3, 12), {
    phase: "geometry",
    label: "Loading geometry",
    done: 3,
    total: 12,
    determinate: true,
  });
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
      missing: meshData.missingComponentIds.length,
      treeChildren: meshData.assemblyRoot.children.length,
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
  assert.ok(
    publishes.every((publish) => publish.treeChildren === 25),
    "the canonical assembly tree retains every occurrence during partial display",
  );
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

test("same-file complete revision replacement publishes atomically and accounts pending bytes", async () => {
  const descriptor = makeDescriptor({ componentCount: 9, occurrenceCount: 9 });
  const { loadComponent } = makeLoader(descriptor, { componentFloats: () => 12 });
  const publishes = [];
  const retained = [];
  await createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 2,
    maxComponents: 2,
    publishIntermediate: false,
    onRetainedChange: (state) => retained.push(state),
    onPublish: ({ loaded, final, meshData }) => publishes.push({ loaded, final, parts: meshData.parts.length })
  }).run();
  assert.deepEqual(publishes, [{ loaded: 9, final: true, parts: 9 }]);
  assert.equal(retained.length, 9, "each newly retained component updates admission accounting");
  assert.ok(retained.every((state, index) => index === 0 || state.retainedBytes >= retained[index - 1].retainedBytes));
  assert.equal(retained.at(-1).loaded, 9);
  const current = { file: "gear.step", meshHash: "old", meshData: { parts: Array(9) }, assemblyInteractionReady: true };
  assert.equal(shouldRetainCompleteSameFileMesh(current, { file: "gear.step", kind: "assembly" }, "new"), true);
  assert.equal(shouldRetainCompleteSameFileMesh(current, { file: "gear.step", kind: "assembly" }, "old"), false);
  assert.equal(shouldRetainCompleteSameFileMesh(current, { file: "other.step", kind: "assembly" }, "new"), false);
  assert.equal(shouldRetainCompleteSameFileMesh({ ...current, assemblyInteractionReady: false }, { file: "gear.step", kind: "assembly" }, "new"), false);
});

test("atomic same-file revision carries unchanged occurrence and tree identity through final publication", async () => {
  const beforeDescriptor = makeDescriptor({ componentCount: 2, occurrenceCount: 24,
    transformFor: (index) => translation(index, 0, 0) });
  const components = { c0: fakeComponent("c0"), c1: fakeComponent("c1") };
  const before = buildComposedPackageMeshData(beforeDescriptor, components);
  const afterDescriptor = structuredClone(beforeDescriptor);
  afterDescriptor.occurrences[7].transform = translation(70, 4, 0);
  let final = null;
  const loader = createProgressivePackageLoader({
    descriptor: afterDescriptor,
    initialComposition: before,
    retainedComponent: (cid) => components[cid],
    loadComponent: async () => { throw new Error("retained components must not decode"); },
    publishIntermediate: false,
    onPublish: (publication) => { final = publication; }
  });
  await loader.run();
  assert.ok(final?.final);
  for (let index = 0; index < before.parts.length; index += 1) {
    if (index === 7) assert.notEqual(final.meshData.parts[index], before.parts[index]);
    else assert.equal(final.meshData.parts[index], before.parts[index]);
  }
  assert.notEqual(final.meshData.assemblyRoot.children[7], before.assemblyRoot.children[7]);
  assert.equal(final.meshData.assemblyRoot.children[8], before.assemblyRoot.children[8]);
  assert.equal(final.meshData.parts[7].transform[3], 70);
  assert.deepEqual(final.meshData.parts[7].bounds, { min: [70, 4, 0], max: [71, 5, 0] });
});

test("failed atomic revision drops staged ownership without mutating or publishing its retained predecessor", async () => {
  const beforeDescriptor = makeDescriptor({ componentCount: 2, occurrenceCount: 4 });
  const components = { c0: fakeComponent("c0"), c1: fakeComponent("c1") };
  const before = buildComposedPackageMeshData(beforeDescriptor, components);
  const afterDescriptor = structuredClone(beforeDescriptor);
  afterDescriptor.occurrences[0].transform = translation(44, 0, 0);
  let publications = 0;
  const loader = createProgressivePackageLoader({
    descriptor: afterDescriptor,
    initialComposition: before,
    retainedComponent: (cid) => cid === "c0" ? components.c0 : null,
    loadComponent: async () => { throw new Error("replacement decode failed"); },
    publishIntermediate: false,
    onPublish: () => { publications += 1; }
  });
  await assert.rejects(loader.run(), /replacement decode failed/);
  assert.equal(publications, 0);
  assert.equal(loader.retainedComponentCount(), 0, "failure releases request-local staged component references");
  assert.equal(before.parts[0].transform[3], 0, "the displayed predecessor remains immutable after rollback");
});

test("producer replacement fences old replies and swaps only a complete new view", async () => {
  const descriptor = makeDescriptor({ componentCount: 4, occurrenceCount: 4 });
  const priorScene = { view: "old" };
  let displayedScene = priorScene;
  const stalePublishes = [];
  let releaseStale;
  const staleReply = new Promise((resolve) => { releaseStale = resolve; });
  const oldLoader = createProgressivePackageLoader({
    descriptor,
    concurrency: 2,
    maxComponents: 1,
    loadComponent: async (cid) => {
      if (cid === "c0") throw new Error("replacement-view");
      await staleReply;
      return fakeComponent(cid);
    },
    onPublish: (publication) => stalePublishes.push(publication),
  });
  const oldRun = oldLoader.run();
  await new Promise((resolve) => setTimeout(resolve, 0));
  releaseStale();
  await assert.rejects(oldRun, /replacement-view/);
  assert.deepEqual(stalePublishes, [], "an old-view sibling cannot publish after replacement starts");
  assert.equal(displayedScene, priorScene);

  const replacementPublishes = [];
  await createProgressivePackageLoader({
    descriptor,
    concurrency: 2,
    publishIntermediate: false,
    loadComponent: async (cid) => {
      assert.equal(displayedScene, priorScene, "the prior scene stays visible while the new view stages");
      return fakeComponent(cid);
    },
    onPublish: (publication) => {
      replacementPublishes.push(publication);
      displayedScene = publication.meshData;
    },
  }).run();
  assert.equal(replacementPublishes.length, 1);
  assert.equal(replacementPublishes[0].final, true);
  assert.equal(replacementPublishes[0].loaded, 4);
  assert.notEqual(displayedScene, priorScene);
});

test("progressive growth keeps already displayed occurrence and leaf metadata", async () => {
  const descriptor = makeDescriptor({ componentCount: 4, occurrenceCount: 8 });
  let previous = null;
  let comparisons = 0;
  await createProgressivePackageLoader({
    descriptor, concurrency: 1, firstComponents: 1, maxComponents: 1,
    loadComponent: async cid => fakeComponent(cid),
    onPublish: ({ meshData }) => {
      if (previous) {
        const nextParts = new Map(meshData.parts.map(part => [part.id, part]));
        const nextLeaves = new Map(meshData.assemblyRoot.children.map(node => [node.id, node]));
        for (const part of previous.parts) {
          assert.equal(nextParts.get(part.id), part);
          const oldLeaf = previous.assemblyRoot.children.find(node => node.id === part.id);
          assert.equal(nextLeaves.get(part.id), oldLeaf);
          comparisons += 1;
        }
      }
      previous = meshData;
    },
  }).run();
  assert.ok(comparisons > 0);
  assert.equal(previous.parts.length, 8);
  assert.deepEqual(previous.missingComponentIds, []);
});

test("an atomic revision cancel publishes nothing and releases pending replacement ownership", async () => {
  const descriptor = makeDescriptor({ componentCount: 9, occurrenceCount: 9 });
  const { loadComponent } = makeLoader(descriptor);
  let current = true;
  const publishes = [];
  const retained = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 1,
    publishIntermediate: false,
    isCurrent: () => current,
    onRetainedChange: (state) => {
      retained.push(state.retainedBytes);
      if (state.loaded === 3) current = false;
    },
    onPublish: (publish) => publishes.push(publish)
  });
  await assert.rejects(loader.run(), (error) => error.name === "AbortError");
  assert.deepEqual(publishes, [], "the retained complete scene never receives a partial replacement");
  assert.ok(retained.some((bytes) => bytes > 0));
  assert.equal(retained.at(-1), 0, "cancel drops all pending replacement ownership");
});

test("retained exact components bypass decode admission and pending-byte ownership", async () => {
  const descriptor = makeDescriptor({ componentCount: 3, occurrenceCount: 3 });
  const retained = fakeComponent("c0");
  const decoded = [];
  const pending = [];
  await createProgressivePackageLoader({
    descriptor,
    concurrency: 1,
    retainedComponent: (cid) => cid === "c0" ? retained : null,
    sizeHint: async () => 1,
    loadComponent: async (cid) => {
      decoded.push(cid);
      return fakeComponent(cid);
    },
    onRetainedChange: (state) => pending.push({ ...state }),
    onPublish: () => {},
  }).run();
  assert.deepEqual(decoded.sort(), ["c1", "c2"]);
  assert.equal(pending[0].retainedBytes, 0, "the current view already owns the reused arrays");
  assert.equal(pending.at(-1).retainedBytes, 168, "only two newly decoded meshes are replacement overlap");
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

test("a failed lane fences sibling publishes, wakes queued admission, and preserves the original error", async () => {
  const descriptor = makeDescriptor({ componentCount: 5, occurrenceCount: 5 });
  const fourStarted = deferred();
  const finishSiblings = deferred();
  const originalFailure = new Error("c0 decode failed");
  const started = [];
  const reserved = [];
  const released = [];
  const publishes = [];
  const releaseCounts = new Map();
  const loader = createProgressivePackageLoader({
    descriptor,
    concurrency: 5,
    maxInFlightBytes: 100,
    reserveLoad: ({ cid }) => {
      reserved.push(cid);
      return { ok: true, token: cid };
    },
    releaseLoad: (token) => {
      released.push(token);
      releaseCounts.set(token, (releaseCounts.get(token) || 0) + 1);
    },
    loadComponent: async (cid) => {
      started.push(cid);
      if (started.length === 4) fourStarted.resolve();
      if (cid === "c0") {
        await fourStarted.promise;
        throw originalFailure;
      }
      await finishSiblings.promise;
      return fakeComponent(cid);
    },
    firstComponents: 1,
    maxComponents: 1,
    onPublish: (publish) => publishes.push(publish.loaded),
  });

  let settled = false;
  const run = loader.run();
  run.then(() => { settled = true; }, () => { settled = true; });
  await fourStarted.promise;
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(settled, false, "run waits for every already-admitted sibling to release");
  assert.deepEqual(started.sort(), ["c0", "c1", "c2", "c3"], "c4 remains queued at admission");
  assert.deepEqual(publishes, [], "no sibling publishes after the first failure");

  finishSiblings.resolve();
  await assert.rejects(run, (error) => error === originalFailure);
  assert.equal(settled, true);
  assert.deepEqual(publishes, [], "settling siblings cannot publish or erase the failure");
  assert.deepEqual(reserved.sort(), ["c0", "c1", "c2", "c3"]);
  assert.deepEqual(released.sort(), reserved);
  assert.ok([...releaseCounts.values()].every((count) => count === 1), "each reservation releases once");
  assert.equal(loader.retainedComponentCount(), 0);
});

test("cancellation fences a queued admission before an active slot releases", async () => {
  const descriptor = makeDescriptor({ componentCount: 5, occurrenceCount: 5 });
  const fourStarted = deferred();
  const finishActive = deferred();
  const started = [];
  const released = [];
  const publishes = [];
  let current = true;
  const loader = createProgressivePackageLoader({
    descriptor,
    concurrency: 5,
    maxInFlightBytes: 100,
    isCurrent: () => current,
    reserveLoad: ({ cid }) => ({ ok: true, token: cid }),
    releaseLoad: (token) => released.push(token),
    loadComponent: async (cid) => {
      started.push(cid);
      if (started.length === 4) fourStarted.resolve();
      await finishActive.promise;
      return fakeComponent(cid);
    },
    firstComponents: 1,
    maxComponents: 1,
    onPublish: (publish) => publishes.push(publish.loaded),
  });

  const run = loader.run();
  await fourStarted.promise;
  current = false;
  finishActive.resolve();
  await assert.rejects(run, (error) => error.name === "AbortError");
  assert.deepEqual(started.sort(), ["c0", "c1", "c2", "c3"], "queued c4 never starts");
  assert.deepEqual(released.sort(), started, "every admitted cancellation releases once");
  assert.deepEqual(publishes, []);
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

test("an explicit coarse L0 remains part of the composed source identity", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 2 });
  const coarse = { ...fakeComponent("c0"), lodLevel: 0 };
  let final = null;
  await createProgressivePackageLoader({
    descriptor,
    loadComponent: async () => coarse,
    onPublish: (publish) => { final = publish; },
  }).run();
  assert.equal(final.meshData.parts.length, 2);
  assert.ok(final.meshData.parts.every((part) => part.sourceMesh === coarse));
  assert.ok(final.meshData.parts.every((part) => part.sourceMeshKey.endsWith(":l0")));
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

// The property is the DOUBLING schedule — how many times 800 components are
// recomposed on the way in, and at what sizes. It used to also assert a wall-clock
// ceiling (`max recompose < 500 ms`) and benchmark animation binding, neither of
// which says anything about the code: the ceiling passes or fails on how loaded the
// runner is, and the bind timing was measured and never asserted at all. Counting
// the publishes pins the same regression (a schedule that stops doubling recomposes
// 25 times instead of 8) and cannot flake.
test("recomposition batches double: 800 components publish 8 times, not 25", async (t) => {
  const descriptor = makeDescriptor({
    componentCount: 800,
    occurrenceCount: 3000,
    transformFor: (i) => translation((i % 37) * 10, (i % 53) * 7, (i % 11) * 3)
  });
  const { loadComponent } = makeLoader(descriptor);
  const publishes = [];
  const result = await createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 8,
    onPublish: (publish) => publishes.push(publish)
  }).run();
  // 8 + 16 + 32 + 64 + 128 + 256 covers 504; the ceiling caps at 256, so the
  // remaining 296 arrive as 256 + 40. Doubling turns 800/32 = 25 recompositions
  // into 8.
  assert.equal(result.publishes, 8);
  assert.deepEqual(publishes.map((publish) => publish.loaded), [8, 24, 56, 120, 248, 504, 760, 800]);
  assert.equal(publishes.at(-1).final, true);
  assert.equal(publishes.at(-1).meshData.parts.length, 3000, "the last publish composes every occurrence");
  t.diagnostic(`recompose per publish: ${publishes.map((publish) => publish.composeMs.toFixed(1)).join(", ")} ms`);
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
    assert.deepEqual(seen.map((cost) => cost.occurrenceCount), [4, 8, 12]);
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

test("embedded animation attaches on the FIRST publish; absent labels are no-ops until they arrive; validation waits for the complete model", async () => {
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
  // Once calibrated, a component larger than the whole decode budget is an
  // explicit limitation. It is never auto-admitted as a run-alone spike.
  const { loadComponent: load3 } = makeLoader(descriptor, { componentFloats: () => 400 });
  const huge = createProgressivePackageLoader({
    descriptor, loadComponent: load3, sizeHint: async () => 1648, concurrency: 8, maxInFlightBytes: 100, onPublish: () => {}
  });
  await assert.rejects(huge.run(), (error) => error.code === "VIEWER_MEMORY_LIMIT");
  // The estimator itself.
  const estimator = createDecodeSizeEstimator({ maxInFlightBytes: 400 });
  assert.equal(estimator.estimate(10), 100, "unmeasured share");
  estimator.observe(10, 300);
  assert.equal(estimator.estimate(20), 600, "hint scaled by the measured ratio");
  assert.equal(estimator.estimate(null), 300, "no hint: running mean");
  const conservative = createDecodeSizeEstimator({
    maxInFlightBytes: 400,
    sourceExpansionRatio: 32,
  });
  assert.equal(conservative.estimate(10), 320, "source expansion applies before observations");
  conservative.observe(10, 50);
  assert.equal(conservative.estimate(10), 320, "a low observation cannot weaken the configured floor");
  assert.equal(conservative.estimate(10, 64), 640, "a concrete component can override the floor");
});

test("mixed component tiers use their own admission estimate floors", async () => {
  const descriptor = makeDescriptor({ componentCount: 2, occurrenceCount: 2 });
  const reserved = [];
  await createProgressivePackageLoader({
    descriptor,
    concurrency: 1,
    maxInFlightBytes: 1000,
    sizeHint: async (cid) => cid === "c0" ? 5 : 20,
    sourceExpansionRatio: (cid) => cid === "c0" ? 64 : 32,
    reserveLoad: ({ cid, estimatedBytes }) => {
      reserved.push([cid, estimatedBytes]);
      return { ok: true, token: cid };
    },
    releaseLoad: () => {},
    loadComponent: async (cid) => fakeComponent(cid, { floats: cid === "c0" ? 200 : 9 }),
    onPublish: () => {},
  }).run();
  assert.deepEqual(reserved, [["c0", 320], ["c1", 640]]);
});

test("a drained medium package reclaims idle worker memory once and retries unchanged admission", async () => {
  const descriptor = makeDescriptor({ componentCount: 9, occurrenceCount: 9 });
  let completed = 0;
  let pressureRetained = true;
  let recoveries = 0;
  const decodedEstimates = [];
  const limitations = [];
  const result = await createProgressivePackageLoader({
    descriptor,
    concurrency: 1,
    maxInFlightBytes: 400,
    sizeHint: async () => 1,
    reserveLoad: ({ estimatedBytes }) => {
      if (completed === 2 && pressureRetained) {
        return {
          ok: false,
          detail: {
            category: "workerInFlight",
            requestedBytes: estimatedBytes * 2,
            estimatedOwnedBytes: 1000,
            availableBytes: 0,
          },
        };
      }
      return { ok: true, token: `r${completed}` };
    },
    releaseLoad: () => { completed += 1; },
    recoverMemoryPressure: async ({ decodedEstimateBytes, reservationDetail }) => {
      recoveries += 1;
      decodedEstimates.push([decodedEstimateBytes, reservationDetail.requestedBytes]);
      pressureRetained = false;
      return true;
    },
    onMemoryLimitation: (detail) => limitations.push(detail),
    loadComponent: async (cid) => fakeComponent(cid),
    onPublish: () => {},
  }).run();
  assert.equal(result.loaded, 9);
  assert.equal(recoveries, 1);
  assert.deepEqual(decodedEstimates, [[100, 200]], "decoded and worker-temporary estimates stay distinct");
  assert.deepEqual(limitations, [], "successful recovery does not leave a permanent limitation");
});

test("a denied waiter may reclaim again after an admitted sibling repopulates worker memory", async () => {
  const descriptor = makeDescriptor({ componentCount: 2, occurrenceCount: 2 });
  let residentPressure = true;
  let smallInFlight = false;
  let recoveries = 0;
  let finishSmall;
  let reportSmallStarted;
  let reportSmallReleased;
  const smallMayFinish = new Promise((resolve) => { finishSmall = resolve; });
  const smallStarted = new Promise((resolve) => { reportSmallStarted = resolve; });
  const smallReleased = new Promise((resolve) => { reportSmallReleased = resolve; });
  const loads = [];
  const limitations = [];

  const run = createProgressivePackageLoader({
    descriptor,
    concurrency: 2,
    maxInFlightBytes: 400,
    sizeHint: async () => 1,
    reserveLoad: ({ cid }) => {
      if (cid === "c0" && (residentPressure || smallInFlight)) {
        return {
          ok: false,
          detail: {
            category: "workerInFlight",
            requestedBytes: 200,
            estimatedOwnedBytes: 1000,
            availableBytes: 0,
          },
        };
      }
      return { ok: true, token: cid };
    },
    releaseLoad: (token) => {
      if (token === "c1") {
        residentPressure = true;
        reportSmallReleased();
      }
    },
    recoverMemoryPressure: async () => {
      recoveries += 1;
      residentPressure = false;
      // Reproduce the browser race: another admitted component finishes and
      // repopulates worker-resident memory while this recovery awaits. The big
      // admission resumes with inFlight already zero, so no waiter branch runs.
      if (recoveries === 1) await smallReleased;
      return true;
    },
    loadComponent: async (cid) => {
      loads.push(cid);
      if (cid === "c1") {
        smallInFlight = true;
        reportSmallStarted();
        await smallMayFinish;
        smallInFlight = false;
      }
      return fakeComponent(cid);
    },
    onMemoryLimitation: (detail) => limitations.push(detail),
    onPublish: () => {},
  }).run();

  await smallStarted;
  finishSmall();
  const result = await run;

  assert.equal(result.loaded, 2);
  assert.deepEqual(loads, ["c1", "c0"]);
  assert.equal(recoveries, 2, "the sibling's completed work re-arms one recovery attempt");
  assert.deepEqual(limitations, []);
});

test("a no-progress recovery is attempted once and reports worker-temporary bytes separately", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const limitations = [];
  let recoveries = 0;
  const loader = createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 400,
    sizeHint: async () => 1,
    reserveLoad: ({ estimatedBytes }) => ({
      ok: false,
      detail: { category: "workerInFlight", requestedBytes: estimatedBytes * 2 },
    }),
    recoverMemoryPressure: async () => {
      recoveries += 1;
      return true;
    },
    onMemoryLimitation: (detail) => limitations.push(detail),
    loadComponent: async () => fakeComponent("c0"),
    onPublish: () => {},
  });
  await assert.rejects(loader.run(), (error) => {
    assert.equal(error.detail.requestedBytes, 200);
    assert.equal(error.detail.decodedEstimateBytes, 100);
    return error.code === "VIEWER_MEMORY_LIMIT";
  });
  assert.equal(limitations[0].requestedBytes, 200);
  assert.equal(limitations[0].decodedEstimateBytes, 100);
  assert.equal(recoveries, 1, "no release progress means no repeated recovery loop");
});

test("an oversized component is rejected when the global envelope cannot reserve it", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  let started = false;
  const limitations = [];
  const policy = createViewerMemoryPolicy({ budgetBytes: 30, gpuHeadroomBytes: 10 });
  const externallyBounded = createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 100,
    allowOversizedSingle: true,
    sizeHint: async () => 2,
    sourceExpansionRatio: 100,
    loadComponent: async () => {
      started = true;
      return fakeComponent("c0");
    },
    reserveLoad: ({ cid, estimatedBytes }) => policy.reserve({
      category: "workerInFlight", bytes: estimatedBytes, label: cid,
    }),
    releaseLoad: (token) => policy.release(token),
    onMemoryLimitation: (detail) => limitations.push(detail),
    onPublish: () => {},
  });
  await assert.rejects(externallyBounded.run(), (error) => error.code === "VIEWER_MEMORY_LIMIT");
  assert.equal(started, false, "decode never starts");
  assert.equal(policy.snapshot().reservationCount, 0);
  assert.equal(limitations.length, 1);
});

test("one globally reserved warm oversized decode runs alone and then restores ordinary concurrency", async () => {
  const descriptor = makeDescriptor({ componentCount: 3, occurrenceCount: 3 });
  const policy = createViewerMemoryPolicy({ budgetBytes: 1000, gpuHeadroomBytes: 0 });
  const warmProbe = { object: "warm-large", byteLength: 50, decodedBytes: 150 };
  const oversizedMayFinish = deferred();
  const oversizedStarted = deferred();
  const started = [];
  const reservations = [];
  const run = createProgressivePackageLoader({
    descriptor,
    concurrency: 3,
    maxInFlightBytes: 100,
    allowOversizedSingle: true,
    sizeHint: async cid => cid === "c0"
      ? { sourceBytes: null, cacheProbe: warmProbe }
      : { sourceBytes: 0.1, cacheProbe: null },
    sourceExpansionRatio: 100,
    reserveLoad: ({ cid, estimatedBytes, cacheProbe }) => {
      reservations.push([cid, estimatedBytes, cacheProbe]);
      return policy.reserve({ category: "workerInFlight",
        bytes: cacheProbe ? estimatedBytes : estimatedBytes * 2, label: cid });
    },
    releaseLoad: token => policy.release(token),
    loadComponent: async (cid, _component, { estimatedBytes, cacheProbe }) => {
      started.push([cid, estimatedBytes, cacheProbe]);
      if (cid === "c0") {
        oversizedStarted.resolve();
        await oversizedMayFinish.promise;
      }
      return fakeComponent(cid);
    },
    onPublish: () => {},
  }).run();

  await oversizedStarted.promise;
  await Promise.resolve();
  assert.deepEqual(started, [["c0", 200, warmProbe]], "no sibling enters while the oversized reservation is live");
  assert.equal(policy.snapshot().inFlightBytes, 200, "the global ledger owns the exact warm decode estimate");
  oversizedMayFinish.resolve();
  await run;

  assert.equal(started.length, 3);
  assert.deepEqual(reservations[0], ["c0", 200, warmProbe]);
  assert.equal(policy.snapshot().reservationCount, 0);
});

test("an oversized decode that outgrows its admitted estimate is not published", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const policy = createViewerMemoryPolicy({ budgetBytes: 1000, gpuHeadroomBytes: 0 });
  const publications = [];
  const limitations = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 100,
    allowOversizedSingle: true,
    sizeHint: async () => 2,
    sourceExpansionRatio: 75,
    reserveLoad: ({ cid, estimatedBytes }) => policy.reserve({
      category: "workerInFlight", bytes: estimatedBytes * 2, label: cid,
    }),
    releaseLoad: token => policy.release(token),
    loadComponent: async () => fakeComponent("c0", { floats: 40 }),
    onMemoryLimitation: detail => limitations.push(detail),
    onPublish: publication => publications.push(publication),
  });

  await assert.rejects(loader.run(), error => {
    assert.equal(error.detail.decodedEstimateBytes, 150);
    assert.ok(error.detail.actualDecodedBytes > 150);
    return error.code === "VIEWER_MEMORY_LIMIT";
  });
  assert.deepEqual(publications, []);
  assert.equal(limitations.length, 1);
  assert.equal(policy.snapshot().reservationCount, 0);
});

test("an underestimated component that actually exceeds the cap is never published", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const limitations = [];
  const publishes = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 100,
    sizeHint: async () => 1,
    loadComponent: async () => fakeComponent("c0", { floats: 40 }),
    onMemoryLimitation: (detail) => limitations.push(detail),
    onPublish: (publish) => publishes.push(publish),
  });
  await assert.rejects(loader.run(), (error) => error.code === "VIEWER_MEMORY_LIMIT");
  assert.deepEqual(publishes, []);
  assert.equal(limitations.length, 1);
  assert.ok(limitations[0].actualDecodedBytes > 100);
  assert.equal(loader.retainedComponentCount(), 0);
});

test("worker reservation spans decode and is released after success", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const policy = createViewerMemoryPolicy({ budgetBytes: 1000, gpuHeadroomBytes: 100 });
  const seen = [];
  await createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 400,
    reserveLoad: ({ cid, estimatedBytes }) => policy.reserve({
      category: "workerInFlight", bytes: estimatedBytes, label: cid,
    }),
    releaseLoad: (token) => policy.release(token),
    loadComponent: async () => {
      seen.push(policy.snapshot().inFlightBytes);
      return fakeComponent("c0");
    },
    onPublish: () => {},
  }).run();
  assert.deepEqual(seen, [100], "unmeasured decode reserves one quarter of the local cap");
  assert.equal(policy.snapshot().inFlightBytes, 0);
});

test("the admitted decoded estimate is passed to the component load", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const estimates = [];
  await createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 400,
    sizeHint: async () => 5,
    sourceExpansionRatio: 30,
    loadComponent: async (_cid, _component, { estimatedBytes }) => {
      estimates.push(estimatedBytes);
      return fakeComponent("c0");
    },
    onPublish: () => {},
  }).run();
  assert.deepEqual(estimates, [150], "worker ownership receives the exact admitted estimate");
});

test("a stale probed body releases hit admission and retries through cold admission", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const probe = { object: "stale", byteLength: 8, decodedBytes: 12 };
  const hints = [];
  const reservations = [];
  const releases = [];
  const loads = [];
  await createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 400,
    sourceExpansionRatio: 10,
    sizeHint: async (_cid, _component, { rejectedCacheObjects, skipCacheProbes }) => {
      hints.push({ rejected: [...rejectedCacheObjects], skipCacheProbes });
      return rejectedCacheObjects.has(probe.object)
        ? { sourceBytes: 5, cacheProbe: null }
        : { sourceBytes: null, cacheProbe: probe };
    },
    reserveLoad: ({ estimatedBytes, cacheProbe }) => {
      reservations.push({ estimatedBytes, cacheProbe });
      return { ok: true, token: reservations.length };
    },
    releaseLoad: (token) => releases.push(token),
    retryCacheProbeMiss: (error) => error?.code === "TESS_CACHE_PROBE_MISS",
    loadComponent: async (_cid, _component, { cacheProbe }) => {
      loads.push(cacheProbe);
      if (cacheProbe) throw Object.assign(new Error("gone"), { code: "TESS_CACHE_PROBE_MISS" });
      return fakeComponent("c0");
    },
    onPublish: () => {},
  }).run();
  assert.deepEqual(hints, [
    { rejected: [], skipCacheProbes: false },
    { rejected: ["stale"], skipCacheProbes: false },
  ]);
  assert.deepEqual(reservations.map(({ estimatedBytes }) => estimatedBytes), [20, 100]);
  assert.deepEqual(loads, [probe, null]);
  assert.deepEqual(releases, [1, 2]);
});

test("changing stale cache rows are bounded before cold admission", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const hints = [];
  let probeNumber = 0;
  const result = await createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 400,
    sizeHint: async (_cid, _component, { skipCacheProbes }) => {
      hints.push(skipCacheProbes);
      return skipCacheProbes
        ? { sourceBytes: 1, cacheProbe: null }
        : { sourceBytes: null, cacheProbe: {
            object: `stale-${probeNumber += 1}`,
            byteLength: 8,
            decodedBytes: 12,
          } };
    },
    retryCacheProbeMiss: (error) => error?.code === "TESS_CACHE_PROBE_MISS",
    loadComponent: async (_cid, _component, { cacheProbe }) => {
      if (cacheProbe) throw Object.assign(new Error("gone"), { code: "TESS_CACHE_PROBE_MISS" });
      return fakeComponent("c0");
    },
    onPublish: () => {},
  }).run();
  assert.deepEqual(hints, [false, false, true]);
  assert.equal(result.loaded, 1);
});

test("a transient global miss waits for admitted work and leaves no stale limitation", async () => {
  const descriptor = makeDescriptor({ componentCount: 5, occurrenceCount: 5 });
  const { loadComponent } = makeLoader(descriptor, { componentFloats: () => 12 });
  const policy = createViewerMemoryPolicy({ budgetBytes: 250, gpuHeadroomBytes: 50 });
  const loader = createProgressivePackageLoader({
    descriptor,
    concurrency: 5,
    maxInFlightBytes: 400,
    reserveLoad: ({ cid, estimatedBytes }) => policy.reserve({
      category: "workerInFlight",
      bytes: estimatedBytes,
      label: cid,
      recordLimitation: false,
    }),
    releaseLoad: (token) => policy.release(token),
    loadComponent,
    onPublish: () => {},
  });
  const result = await loader.run();
  assert.equal(result.loaded, 5);
  assert.equal(policy.snapshot().lastLimitation, null);
  assert.equal(policy.snapshot().reservationCount, 0);
  assert.ok(loader.peakInFlight() <= 2, "the global 200-byte owned limit admits two 100-byte estimates");
});

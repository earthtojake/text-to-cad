// Progressive publish of a component package (packages/ui/docs/loading.md, section 2).
// Fake components (no tessellation): the policy under test is batching,
// ordering, admission, staleness and release, not geometry.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { setImmediate } from "node:timers";

import { buildComposedPackageMeshData } from "@text-to-cad/core/lib/assembly/meshData.js";
import { partRow, tessellationDecodedBytes } from "@text-to-cad/core/lib/parts/tessellationCache.js";

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
  meshStateSettledShort,
  awaitingSameFileRevision,
  meshStateAfterCancelledLoad,
  replacingSameFileMesh,
  retainsPreviousStepMesh,
  shouldRetainCompleteSameFileMesh,
  PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES
} from "./packageProgressiveLoad.js";
import { createViewerMemoryPolicy } from "../../../render/viewerMemoryPolicy.js";

const IDENTITY_4X4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

const sha256 = (text) => createHash("sha256").update(text).digest("hex");

// A part's row as the store answers it, made by core's `partRow` so it has the product's shape:
// a 20-byte display mesh whose record says decoding it costs `bytes - 20` more, so admission
// charges exactly `bytes` (a multiple of 4, at least 20). `version` names another body of the
// same part, as the store holds one after the first went missing.
function storedRow(cid, bytes, version = "") {
  const counts = { vertexCount: 0, indexCount: (bytes - 20) / 4, faceCount: 0, edgeCount: 0, edgePointCount: 0 };
  const row = partRow(`${sha256(cid)}-v1`, {
    glb: { object: sha256(`${cid}:${version}`), byteLength: 20, decodedBytes: tessellationDecodedBytes(counts), ...counts },
    selectors: { object: sha256(`${cid}:selectors`), byteLength: 1, faceCount: 0, edgeCount: 0, vertexCount: 0 },
  });
  assert.ok(row, `a part row charging ${bytes} bytes`);
  return row;
}

// The row of every component in a test that is not about admission: it charges next to nothing.
const smallRow = async (cid) => storedRow(cid, 64);

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
    components[`c${i}`] = { brep: `components/c${i}.brep` };
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
  assert.deepEqual(progressiveLoadProgress(3, 12, undefined, { meshing: true }), {
    phase: "meshing",
    label: "Meshing parts",
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
    partRow: smallRow,
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
    partRow: smallRow,
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
    partRow: smallRow,
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
    partRow: smallRow,
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

test("a load that publishes whole still draws what it has while a lane waits outside it", async () => {
  const descriptor = makeDescriptor({ componentCount: 4, occurrenceCount: 4 });
  const { loadComponent } = makeLoader(descriptor);
  const named = deferred();
  const publishes = [];
  let waited = null;
  const loader = createProgressivePackageLoader({
    descriptor,
    loadComponent,
    concurrency: 1,
    publishIntermediate: false,
    partRow: async (cid) => {
      if (cid === "c3") {
        // A preview's part its build is still deriving: what has loaded is drawn, then the lane waits.
        waited = loader.publishPending();
        await named.promise;
      }
      return smallRow(cid);
    },
    onPublish: ({ loaded, final, meshData }) => publishes.push({ loaded, final, parts: meshData.parts.length })
  });
  const run = loader.run();
  while (waited === null) await new Promise((resolve) => setImmediate(resolve));
  assert.equal(waited, true);
  assert.deepEqual(publishes, [{ loaded: 3, final: false, parts: 3 }]);
  assert.equal(loader.publishPending(), false, "nothing new to draw while it waits");
  named.resolve();
  await run;
  assert.deepEqual(publishes, [{ loaded: 3, final: false, parts: 3 }, { loaded: 4, final: true, parts: 4 }]);
  assert.equal(loader.publishPending(), false, "nothing after the final publish");
});

test("once a model is on screen, its file's next revision is an update: a part's or an assembly's, built or still building", () => {
  const current = { file: "plate.step", meshHash: "old", meshData: { parts: [{}] } };
  // What the viewer keeps showing while the new revision loads, whatever the entry's kind.
  for (const kind of ["part", "assembly"]) {
    assert.equal(replacingSameFileMesh(current, { file: "plate.step", kind }, "new"), true, kind);
    assert.equal(replacingSameFileMesh(current, { file: "plate.step", kind }, "old"), false, `${kind}: the same revision is no replacement`);
  }
  assert.equal(replacingSameFileMesh(current, { file: "other.step", kind: "part" }, "new"), false);
  assert.equal(replacingSameFileMesh({ ...current, assemblyInteractionReady: false }, { file: "plate.step", kind: "assembly" }, "new"), false,
    "a model still arriving in pieces is not complete");
  // Before the rewritten file is built its entry has no mesh: what is on screen stays through that too.
  assert.equal(awaitingSameFileRevision(current, { file: "plate.step" }), true);
  assert.equal(awaitingSameFileRevision(current, { file: "other.step" }), false);
  assert.equal(awaitingSameFileRevision(null, { file: "plate.step" }), false, "nothing on screen yet: that is the first load");
  // The viewer's one answer, for every model: a robot with joints keeps its body on screen through a
  // saved-file update just as a plate does, never the loading screen (a model with motion once went back to it).
  assert.equal(retainsPreviousStepMesh(current, { file: "plate.step" }, { entryHasMesh: false, meshHash: "" }), true, "still building");
  assert.equal(retainsPreviousStepMesh(current, { file: "plate.step" }, { entryHasMesh: true, meshHash: "new" }), true, "loading the new mesh");
  assert.equal(retainsPreviousStepMesh(current, { file: "plate.step" }, { entryHasMesh: true, meshHash: "old" }), false, "the new mesh is published");
  assert.equal(retainsPreviousStepMesh(null, { file: "plate.step" }, { entryHasMesh: true, meshHash: "new" }), false, "a first load");
  // The loader's own staging question stays an assembly's.
  assert.equal(shouldRetainCompleteSameFileMesh(current, { file: "plate.step", kind: "part" }, "new"), false);
  // Edits in quick succession: a revision's load cancelled for the next one leaves the complete
  // model on screen -- a part's too, whose state has no interaction flag -- and drops only a
  // partial composition that load had published.
  assert.equal(meshStateAfterCancelledLoad(current, "plate.step"), current);
  const partial = { ...current, meshData: { parts: [{}], missingComponentIds: ["c2"] } };
  assert.equal(meshStateAfterCancelledLoad(partial, "plate.step"), null);
  assert.equal(meshStateAfterCancelledLoad(partial, "other.step"), partial);
  assert.equal(meshStateAfterCancelledLoad(null, "plate.step"), null);
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
    partRow: smallRow,
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
    partRow: smallRow,
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
    partRow: smallRow,
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
    descriptor, partRow: smallRow, concurrency: 1, firstComponents: 1, maxComponents: 1,
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
    partRow: smallRow,
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
    partRow: smallRow,
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
    partRow: smallRow,
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
    partRow: smallRow,
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
    // Four 24-byte parts fit the 100-byte cap; the fifth waits at admission.
    maxInFlightBytes: 100,
    partRow: async (cid) => storedRow(cid, 24),
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

// One component cadgen could not mesh is that component's failure (`componentFailed`): every other
// component still loads, and the final publish carries them and names it. Any other failure still
// fences every lane, and a package whose every component failed on its own has the first's error.
test("a component's own failure leaves it out: the rest load, and the final publish names it", async () => {
  const descriptor = makeDescriptor({ componentCount: 4, occurrenceCount: 4 });
  const { loadComponent } = makeLoader(descriptor);
  const own = (cid) => Object.assign(new Error(`component ${cid}: OCCT failed on the component`), { cid });
  const componentFailed = (error, cid) => error.cid === cid;
  const publishes = [];
  const settled = [];
  const loader = createProgressivePackageLoader({
    descriptor, concurrency: 2, loadComponent, componentFailed,
    partRow: async (cid) => { if (cid === "c2") throw own(cid); return storedRow(cid, 64); },
    onRetainedChange: ({ loaded, failed }) => settled.push(loaded + failed),
    onPublish: (publish) => publishes.push(publish),
  });
  const result = await loader.run();
  assert.deepEqual([result.loaded, result.total], [3, 4]);
  assert.deepEqual(result.failures.map(({ cid, error }) => [cid, error.message]),
    [["c2", "component c2: OCCT failed on the component"]]);
  const finals = publishes.filter((publish) => publish.final);
  assert.equal(finals.length, 1);
  assert.deepEqual(Object.keys(finals[0].componentMeshDataByCid).sort(), ["c0", "c1", "c3"]);
  assert.deepEqual(finals[0].meshData.missingComponentIds, ["c2"]);
  assert.deepEqual(finals[0].failures.map(({ cid }) => cid), ["c2"]);
  assert.equal(settled.at(-1), 4, "a failed component counts as settled");

  const fatal = new Error("part request capacity reached");
  const fenced = createProgressivePackageLoader({
    descriptor, concurrency: 2, loadComponent, componentFailed, onPublish: () => {},
    partRow: async (cid) => { if (cid === "c1") throw fatal; return storedRow(cid, 64); },
  });
  await assert.rejects(fenced.run(), (error) => error === fatal);

  const part = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const lone = createProgressivePackageLoader({
    descriptor: part, loadComponent: makeLoader(part).loadComponent, componentFailed,
    partRow: async (cid) => { throw own(cid); },
    onPublish: () => assert.fail("nothing is published"),
  });
  await assert.rejects(lone.run(), /component c0: OCCT failed on the component/);
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
    // Four 24-byte parts fit the 100-byte cap; the fifth waits at admission.
    maxInFlightBytes: 100,
    partRow: async (cid) => storedRow(cid, 24),
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
    partRow: smallRow,
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
      partRow: smallRow,
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

test("a published mesh state is the complete model only on the final publish", async () => {
  const descriptor = makeDescriptor({ componentCount: 9, occurrenceCount: 18 });
  const { loadComponent } = makeLoader(descriptor);
  const complete = [];
  await createProgressivePackageLoader({
    descriptor,
    loadComponent,
    partRow: smallRow,
    concurrency: 3,
    maxComponents: 4,
    onPublish: ({ meshData, final }) => {
      complete.push(meshStateIsComplete({ file: "hand.step", meshData, assemblyInteractionReady: final }));
    }
  }).run();
  assert.deepEqual(complete, [false, false, true]);
  const partial = buildComposedPackageMeshData(descriptor, { c0: fakeComponent("c0") });
  assert.equal(meshStateIsComplete({ meshData: partial }), false, "a composition still missing components");
  assert.equal(meshStateIsComplete(null), false);
  assert.equal(meshStateIsComplete({ meshData: { parts: null }, assemblyInteractionReady: false }), false, "assembly preview");
  assert.equal(meshStateIsComplete({ meshData: { parts: [], missingComponentIds: ["c1"] } }), false);
  assert.equal(meshStateIsComplete({ meshData: { parts: [] } }), true, "non-package meshes carry no flag");
});

test("a load that ended without the parts cadgen could not mesh is short of them, not still arriving", () => {
  const short = { meshData: { parts: [], missingComponentIds: ["c1"] }, assemblyInteractionReady: true,
    assemblyFailedParts: ["accessory:case"] };
  assert.equal(meshStateSettledShort(short), true);
  assert.equal(meshStateSettledShort({ ...short, assemblyInteractionReady: false }), false, "components still arriving");
  assert.equal(meshStateSettledShort({ ...short, assemblyFailedParts: [] }), false, "missing, but none failed");
  assert.equal(meshStateSettledShort({ ...short, meshData: { parts: [] } }), false, "complete");
  assert.equal(meshStateSettledShort(null), false);
});

// Admission charges what a part's row says reading and decoding its display mesh costs, from the
// first component on: the reservation, the decodes in flight and the component's own load all see
// exactly `glb.byteLength + glb.decodedBytes`, and the reservation spans the decode.
test("admission charges exactly what a part's row states: glb.byteLength + glb.decodedBytes", async () => {
  const descriptor = makeDescriptor({ componentCount: 2, occurrenceCount: 2 });
  const rows = { c0: storedRow("c0", 152), c1: storedRow("c1", 36) };
  const charge = (row) => row.glb.byteLength + row.glb.decodedBytes;
  assert.deepEqual([charge(rows.c0), charge(rows.c1)], [152, 36]);
  const policy = createViewerMemoryPolicy({ budgetBytes: 1000, gpuHeadroomBytes: 0 });
  const seen = [];
  await createProgressivePackageLoader({
    descriptor,
    concurrency: 1,
    maxInFlightBytes: 400,
    partRow: async (cid) => rows[cid],
    reserveLoad: ({ cid, estimatedBytes, row }) => {
      seen.push(["reserve", cid, estimatedBytes, row]);
      return policy.reserve({ category: "workerInFlight", bytes: estimatedBytes, label: cid });
    },
    releaseLoad: (token) => policy.release(token),
    loadComponent: async (cid, _component, { estimatedBytes, row }) => {
      seen.push(["load", cid, estimatedBytes, row, policy.snapshot().inFlightBytes]);
      return fakeComponent(cid);
    },
    onPublish: () => {},
  }).run();
  assert.deepEqual(seen, [
    ["reserve", "c0", 152, rows.c0], ["load", "c0", 152, rows.c0, 152],
    ["reserve", "c1", 36, rows.c1], ["load", "c1", 36, rows.c1, 36],
  ]);
  assert.equal(policy.snapshot().inFlightBytes, 0, "each reservation is released once its decode is in");
});

test("small parts decode up to the count cap at once; the byte cap binds when their rows fill it", async () => {
  const descriptor = makeDescriptor({ componentCount: 24, occurrenceCount: 24 });
  // Parts far under the viewer's own cap: eight at once, the count cap.
  const wide = createProgressivePackageLoader({
    descriptor, loadComponent: makeLoader(descriptor).loadComponent, partRow: smallRow, concurrency: 8,
    maxInFlightBytes: PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES, onPublish: () => {}
  });
  await wide.run();
  assert.equal(wide.peakInFlight(), 8, "the count cap, not a guess at each part's size");
  // Rows of 208 bytes under a 500-byte cap: two at a time, from the first admission on.
  const { loadComponent } = makeLoader(descriptor, { componentFloats: () => 40 });
  let inFlight = 0;
  const inFlightAtStart = [];
  const narrow = createProgressivePackageLoader({
    descriptor,
    loadComponent: async (cid, component) => {
      inFlight += 1;
      inFlightAtStart.push(inFlight);
      try {
        return await loadComponent(cid, component);
      } finally {
        inFlight -= 1;
      }
    },
    partRow: async (cid) => storedRow(cid, 208),
    concurrency: 8,
    maxInFlightBytes: 500,
    onPublish: () => {}
  });
  await narrow.run();
  assert.equal(inFlightAtStart.length, 24);
  assert.ok(inFlightAtStart.every((count) => count <= 2), `admissions ${inFlightAtStart}`);
  assert.equal(narrow.peakInFlight(), 2);
  // A part above the whole cap, with no oversized admission: an explicit limitation, never decoded.
  let started = false;
  const huge = createProgressivePackageLoader({
    descriptor: makeDescriptor({ componentCount: 1, occurrenceCount: 1 }),
    loadComponent: async () => { started = true; return fakeComponent("c0"); },
    partRow: async (cid) => storedRow(cid, 1648), concurrency: 8, maxInFlightBytes: 100, onPublish: () => {}
  });
  await assert.rejects(huge.run(), (error) => error.code === "VIEWER_MEMORY_LIMIT" && error.detail.requestedBytes === 1648);
  assert.equal(started, false);
});

test("a row that states no size is the load's error, not a guess", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  let started = false;
  await assert.rejects(createProgressivePackageLoader({
    descriptor,
    partRow: async () => ({ part: `${sha256("c0")}-v1`, glb: { object: sha256("c0:") }, selectors: {} }),
    loadComponent: async () => { started = true; return fakeComponent("c0"); },
    onPublish: () => {},
  }).run(), /Component c0 has no part row to size its decode by/);
  assert.equal(started, false);
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
    partRow: async (cid) => storedRow(cid, 100),
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
    partRow: smallRow,
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
    partRow: async (cid) => storedRow(cid, 100),
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
    partRow: async (cid) => storedRow(cid, 200),
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

test("a part above the in-flight cap decodes alone, through a reservation of its whole charge, then ordinary concurrency returns", async () => {
  const descriptor = makeDescriptor({ componentCount: 3, occurrenceCount: 3 });
  const policy = createViewerMemoryPolicy({ budgetBytes: 1000, gpuHeadroomBytes: 0 });
  const rows = { c0: storedRow("c0", 200), c1: storedRow("c1", 24), c2: storedRow("c2", 24) };
  const oversizedMayFinish = deferred();
  const oversizedStarted = deferred();
  const started = [];
  const reservations = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    concurrency: 3,
    maxInFlightBytes: 100,
    allowOversizedSingle: true,
    partRow: async (cid) => rows[cid],
    reserveLoad: ({ cid, estimatedBytes, row }) => {
      reservations.push([cid, estimatedBytes, row]);
      return policy.reserve({ category: "workerInFlight", bytes: estimatedBytes, label: cid });
    },
    releaseLoad: token => policy.release(token),
    loadComponent: async (cid, _component, { estimatedBytes, row }) => {
      started.push([cid, estimatedBytes, row]);
      if (cid === "c0") {
        oversizedStarted.resolve();
        await oversizedMayFinish.promise;
      }
      return fakeComponent(cid);
    },
    onPublish: () => {},
  });
  const loading = loader.run();

  await oversizedStarted.promise;
  await Promise.resolve();
  assert.deepEqual(started, [["c0", 200, rows.c0]], "no sibling enters while the oversized reservation is live");
  assert.equal(policy.snapshot().inFlightBytes, 200, "the global ledger owns the part's whole charge");
  oversizedMayFinish.resolve();
  await loading;

  assert.equal(started.length, 3);
  assert.deepEqual(reservations[0], ["c0", 200, rows.c0]);
  assert.equal(loader.peakInFlight(), 2, "the two small parts then decode together");
  assert.equal(policy.snapshot().reservationCount, 0);
});

test("an oversized decode is held to its own charge: one that outgrows it is not published", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const policy = createViewerMemoryPolicy({ budgetBytes: 1000, gpuHeadroomBytes: 0 });
  const publications = [];
  const limitations = [];
  const loader = createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 100,
    allowOversizedSingle: true,
    // 152 bytes charged; the decode makes 208.
    partRow: async (cid) => storedRow(cid, 152),
    reserveLoad: ({ cid, estimatedBytes }) => policy.reserve({
      category: "workerInFlight", bytes: estimatedBytes * 2, label: cid,
    }),
    releaseLoad: token => policy.release(token),
    loadComponent: async () => fakeComponent("c0", { floats: 40 }),
    onMemoryLimitation: detail => limitations.push(detail),
    onPublish: publication => publications.push(publication),
  });

  await assert.rejects(loader.run(), error => {
    assert.equal(error.detail.decodedEstimateBytes, 152);
    assert.equal(error.detail.availableBytes, 152, "its own charge, not the in-flight cap");
    assert.equal(error.detail.actualDecodedBytes, 208);
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
    partRow: async (cid) => storedRow(cid, 24),
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

// A body the store no longer holds is a miss the strict read reports: the loader releases that
// admission, passes over the body's object on the next ask, and admits what that ask answers.
test("a body the store no longer holds puts its row's glb.object in the rejected set, and the next ask passes over it", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  // The row the store answered, whose body has gone, and the one cadgen derives afresh.
  const stale = storedRow("c0", 36, "stale");
  const fresh = storedRow("c0", 152, "fresh");
  const asks = [];
  const reservations = [];
  const releases = [];
  const loads = [];
  await createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 400,
    // As the viewer asks: the stored row, unless this load has found its body gone.
    partRow: async (_cid, _component, { rejectedCacheObjects, skipCacheProbes }) => {
      asks.push({ rejected: [...rejectedCacheObjects], skipCacheProbes });
      return rejectedCacheObjects.has(stale.glb.object) ? fresh : stale;
    },
    reserveLoad: ({ estimatedBytes, row }) => {
      reservations.push([estimatedBytes, row]);
      return { ok: true, token: reservations.length };
    },
    releaseLoad: (token) => releases.push(token),
    retryCacheProbeMiss: (error) => error?.code === "TESS_CACHE_PROBE_MISS",
    loadComponent: async (_cid, _component, { row }) => {
      loads.push(row);
      if (row === stale) throw Object.assign(new Error("gone"), { code: "TESS_CACHE_PROBE_MISS" });
      return fakeComponent("c0");
    },
    onPublish: () => {},
  }).run();
  assert.deepEqual(asks, [
    { rejected: [], skipCacheProbes: false },
    { rejected: [stale.glb.object], skipCacheProbes: false },
  ]);
  assert.deepEqual(reservations, [[36, stale], [152, fresh]], "each admission charges its own row");
  assert.deepEqual(loads, [stale, fresh]);
  assert.deepEqual(releases, [1, 2]);
});

test("changing stale cache rows are bounded before cold admission", async () => {
  const descriptor = makeDescriptor({ componentCount: 1, occurrenceCount: 1 });
  const asks = [];
  let version = 0;
  const derived = storedRow("c0", 36, "derived");
  const result = await createProgressivePackageLoader({
    descriptor,
    maxInFlightBytes: 400,
    // Every ask of the store answers a body that is gone by the time it is read.
    partRow: async (cid, _component, { skipCacheProbes }) => {
      asks.push(skipCacheProbes);
      return skipCacheProbes ? derived : storedRow(cid, 36, `stale-${version += 1}`);
    },
    retryCacheProbeMiss: (error) => error?.code === "TESS_CACHE_PROBE_MISS",
    loadComponent: async (_cid, _component, { row }) => {
      if (row !== derived) throw Object.assign(new Error("gone"), { code: "TESS_CACHE_PROBE_MISS" });
      return fakeComponent("c0");
    },
    onPublish: () => {},
  }).run();
  assert.deepEqual(asks, [false, false, true]);
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
    partRow: async (cid) => storedRow(cid, 100),
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
  assert.ok(loader.peakInFlight() <= 2, "the global 200-byte owned limit admits two 100-byte parts");
});

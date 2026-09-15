import assert from "node:assert/strict";
import test from "node:test";
import {
  createLodSceneAdoption,
  lodOccurrenceProof,
  registerLodDisplaySource,
} from "./lodSceneAdoption.js";
import { updateLodMeshState, updateLodReferenceState } from "./lodPublication.js";
import * as materials from "../workbench/sourceMaterialSession.js";

function source(mesh, extra = []) {
  return { parts: ["a1", "a2"].map(id => ({ id, occurrenceId: id, componentId: "a", sourceMesh: mesh })).concat(extra) };
}
function fixture() {
  const baseMesh = {}, mesh = {}, base = source(baseMesh), candidate = source(mesh);
  const descriptor = Object.freeze({ occurrences: Object.freeze(["a1", "a2"].map(id => Object.freeze({ id, component: "a" }))) });
  let context = { file: "same.step", meshHash: "revision", meshData: base }, current = candidate, restored = base;
  let commits = 0, recoveries = 0, failures = 0;
  const tracker = createLodSceneAdoption({ currentContext: () => context });
  return { baseMesh, mesh, base, candidate, descriptor, tracker,
    get context() { return context; }, set context(value) { context = value; },
    set current(value) { current = value; }, set restored(value) { restored = value; },
    get counts() { return { commits, recoveries, failures }; },
    expect(signal, options = {}) { return tracker.expect({ context, source: candidate, descriptor,
      componentId: "a", componentMesh: mesh, baseMesh, baseSource: base, signal,
      currentSource: () => current, currentBaseSource: () => restored,
      commit: () => { commits++; context.meshData = current; },
      restore: () => { recoveries++; return restored; }, failed: () => { failures++; }, ...options }); },
    publish() { tracker.published(candidate); },
  };
}
async function ticks() { for (let i = 0; i < 12; i++) await Promise.resolve(); }

test("material-only display wrappers acknowledge the exact published geometry", async () => {
  const f = fixture(), promise = f.expect(); f.publish();
  const added = materials.addSourceMaterialPreset(null, null, "satin-metal");
  const overlay = materials.assignSourceMaterialOverlay(added.overlay, ["a1"], added.materialId);
  const display = materials.applySourceMaterialOverlayToMeshData(f.candidate, overlay);
  assert.equal(f.tracker.adopted(display), false, "a copied display object cannot acknowledge the publication");
  assert.equal(f.tracker.adopted(materials.sourceMaterialGeometry(display)), true);
  assert.equal((await promise).status, "adopted");
  assert.equal(f.context.meshData, f.candidate);
});

test("committed source stays old until exact actual adoption; publication is not ownership completion", async () => {
  const f = fixture(); let done = false;
  const promise = f.expect().then(outcome => { done = true; return outcome; }); f.publish();
  assert.equal(f.context.meshData, f.base); assert.equal(f.tracker.adopted({ ...f.candidate }), false);
  await ticks(); assert.equal(done, false);
  assert.equal(f.tracker.adopted(f.candidate), true);
  assert.equal((await promise).status, "adopted"); assert.equal(f.context.meshData, f.candidate);
  assert.deepEqual(f.counts, { commits: 1, recoveries: 0, failures: 0 });
  assert.equal(f.tracker.snapshot().pending, 0);
});

test("complete descriptor proof rejects missing, duplicate, extra and wrong-payload occurrences", () => {
  const f = fixture();
  const prove = lodOccurrenceProof({ source: f.candidate, descriptor: f.descriptor, componentId: "a", componentMesh: f.mesh });
  for (const parts of [f.candidate.parts.slice(1), [f.candidate.parts[0], f.candidate.parts[0]],
    [...f.candidate.parts, { ...f.candidate.parts[0], id: "extra", occurrenceId: "extra" }],
    f.candidate.parts.map(part => ({ ...part, sourceMesh: {} }))]) assert.equal(prove({ parts }), false);
  assert.equal(prove(f.candidate), true);
  assert.equal(lodOccurrenceProof({ descriptor: { occurrences: [{ id: "a1", component: "a" }, { id: "a1", component: "a" }] },
    componentId: "a", componentMesh: f.mesh })(f.candidate), false);
});

test("progressive supersession accepts every exact requested occurrence in the current larger source", async () => {
  const f = fixture(), promise = f.expect(); f.publish();
  const larger = source(f.mesh, [{ id: "b1", componentId: "b", sourceMesh: {} }]); f.current = larger;
  assert.equal(f.tracker.adopted(f.candidate), false); assert.equal(f.tracker.snapshot().pending, 1);
  assert.equal(f.tracker.adopted(larger), true); assert.equal((await promise).status, "adopted");
});

test("failure holds ownership through disposal and restoration, without committing candidate maps", async () => {
  const f = fixture(); let done = false;
  const promise = f.expect().then(outcome => { done = true; return outcome; }); f.publish();
  f.tracker.failed(f.candidate); await ticks(); assert.equal(done, false);
  f.tracker.disposed(f.candidate, { recover: true }); await ticks();
  assert.equal(done, false); assert.equal(f.tracker.snapshot().phase, "restoring");
  assert.equal(f.context.meshData, f.base); assert.equal(f.counts.commits, 0);
  assert.equal(f.tracker.adopted(f.base), true); assert.equal((await promise).status, "restored");
  assert.deepEqual(f.counts, { commits: 0, recoveries: 1, failures: 0 });
});

test("failed restoration releases only after its teardown and reports a fatal outcome", async () => {
  const f = fixture(), promise = f.expect(); f.publish();
  f.tracker.disposed(f.candidate, { recover: true });
  f.tracker.failed(f.base); assert.equal(f.tracker.snapshot().pending, 1);
  f.tracker.disposed(f.base, { recover: true });
  assert.equal((await promise).status, "disposed-failed"); assert.equal(f.counts.failures, 1);
  assert.equal(f.counts.commits, 0);
});

test("cleanup failure is not a disposal proof and keeps the owner pending", async () => {
  const f = fixture(); let done = false;
  const promise = f.expect().then(outcome => { done = true; return outcome; }); f.publish();
  f.tracker.failed(f.candidate, { cleanupFailed: true }); await ticks();
  assert.equal(done, false); assert.equal(f.tracker.snapshot().phase, "cleanup-failed");
  f.tracker.cancel(); await ticks(); assert.equal(done, false);
  f.tracker.disposed(f.candidate); assert.equal((await promise).status, "cancelled");
});

test("abort before publication settles immediately; abort after publication waits for renderer disposal", async () => {
  const f = fixture(), before = new AbortController(); const first = f.expect(before.signal);
  before.abort(); assert.equal((await first).status, "cancelled");
  const after = new AbortController(); let done = false;
  const second = f.expect(after.signal).then(outcome => { done = true; return outcome; }); f.publish();
  after.abort(); await ticks(); assert.equal(done, false);
  assert.throws(() => f.expect(), /still owns/);
  f.tracker.disposed(f.candidate); assert.equal((await second).status, "cancelled");
  const third = f.expect(); f.publish(); before.abort(); after.abort();
  assert.equal(f.tracker.snapshot().pending, 1); f.tracker.adopted(f.candidate); await third;
});

test("same-file revision/model switch cannot release an old publication before replacement really adopts", async () => {
  for (const mutate of [f => { f.context = { ...f.context }; }, f => { f.context.meshHash = "other"; }, f => { f.context = null; }]) {
    const f = fixture(); let done = false;
    const promise = f.expect().then(outcome => { done = true; return outcome; }); f.publish(); mutate(f);
    f.tracker.checkContext(); await ticks(); assert.equal(done, false);
    f.tracker.adopted({ parts: [] }); assert.equal((await promise).status, "cancelled"); assert.equal(f.counts.commits, 0);
  }
});

test("queued old-base acknowledgments cannot settle the candidate, including after abort", async () => {
  for (const abort of [false, true]) {
    const f = fixture(), controller = new AbortController(), promise = f.expect(controller.signal); f.publish();
    if (abort) controller.abort();
    assert.equal(f.tracker.adopted(f.base), true);
    await ticks(); assert.equal(f.tracker.snapshot().pending, 1); assert.equal(f.counts.commits, 0);
    f.tracker.adopted(f.candidate);
    assert.equal((await promise).status, abort ? "cancelled" : "adopted");
  }
});

test("only committed exact receipts abandon a rejected update; replay cannot resurrect a retired command", async () => {
  const f = fixture(), command = { source: f.candidate }, controller = new AbortController();
  const promise = f.expect(controller.signal, { command }); f.publish();
  const before = { value: { meshData: f.base }, reference: { oldSelectors: true }, receipt: null };
  const proposed = { meshData: f.candidate };
  const choose = current => controller.signal.aborted ? current : proposed;
  const abandonedRender = updateLodMeshState(before, choose, command);
  assert.equal(abandonedRender.receipt.accepted, true);
  controller.abort();
  const committed = updateLodMeshState(before, choose, command);
  assert.equal(committed.value, before.value); assert.equal(committed.receipt.accepted, false);
  f.tracker.adopted(f.base); await ticks(); assert.equal(f.tracker.snapshot().pending, 1);
  f.tracker.committed(committed.receipt);
  assert.equal((await promise).status, "cancelled"); assert.equal(command.source, null);
  assert.equal(updateLodMeshState(committed, () => proposed, command), committed);
  const next = f.expect(); f.publish(); f.tracker.committed(committed.receipt);
  assert.equal(f.tracker.snapshot().pending, 1, "old receipt cannot settle a newer request");
  f.tracker.adopted(f.candidate); await next;
});

test("accepted receipt keeps ownership pending, matches payload rather than state identity, and pairs selectors", async () => {
  const f = fixture(), selectors = { currentLevel: 2 }, command = { source: f.candidate, reference: selectors };
  const promise = f.expect(null, { command }); f.publish();
  const before = { value: { meshData: f.candidate }, reference: {}, receipt: null };
  const accepted = updateLodMeshState(before, current => current, command);
  assert.equal(accepted.receipt.accepted, true); assert.equal(accepted.reference, selectors);
  f.tracker.committed(accepted.receipt); assert.equal(f.tracker.snapshot().pending, 1);
  f.tracker.adopted(f.candidate); await promise;
  assert.equal(command.source, null); assert.equal(command.reference, null, "receipt retains no former model payload");
  assert.equal(updateLodMeshState(accepted, current => current), accepted);
  assert.equal(updateLodReferenceState(accepted, current => current), accepted);
  assert.equal(updateLodMeshState(accepted, { file: "different.step" }).receipt, null);
});

test("ordinary updates preserve not-yet-committed rejection receipt without retaining it after acknowledgment", async () => {
  const f = fixture(), command = { source: f.candidate }, promise = f.expect(null, { command }); f.publish();
  const state = { value: { meshData: f.base }, reference: {}, receipt: null };
  const rejected = updateLodMeshState(state, value => value, command);
  const next = updateLodMeshState(rejected, { ...state.value, backgroundError: "replacement failed" });
  assert.equal(next.receipt, rejected.receipt);
  f.tracker.committed(next.receipt); assert.equal((await promise).status, "cancelled");
  const later = updateLodMeshState(next, { ...next.value }); assert.equal(later.receipt, null);
});

test("disposal recognizes a superseded progressive source and cannot strand its retiring lease", async () => {
  const f = fixture(), sources = new WeakSet([f.candidate]), controller = new AbortController();
  const middle = source(f.mesh, [{ id: "b1", componentId: "b", sourceMesh: {} }]);
  const latest = source(f.mesh, [{ id: "c1", componentId: "c", sourceMesh: {} }]);
  sources.add(middle); sources.add(latest);
  const promise = f.expect(controller.signal, { candidateSources: sources }); f.publish(); f.current = latest;
  assert.equal(f.tracker.adopted(middle), true); assert.equal(f.tracker.snapshot().pending, 1);
  controller.abort(); f.tracker.disposed(middle);
  assert.equal((await promise).status, "cancelled");
});

test("restoration uses a separate replay-fenced receipt and retires the original candidate command", async () => {
  const f = fixture(), candidateCommand = { source: f.candidate }; let recovery;
  const promise = f.expect(null, { command: candidateCommand, restore: command => {
    recovery = command; command.source = f.base; command.reference = { baseSelectors: true }; return f.base;
  } }); f.publish(); f.tracker.disposed(f.candidate, { recover: true });
  assert.equal(candidateCommand.retired, true); assert.equal(candidateCommand.source, null);
  const state = { value: { meshData: f.candidate }, reference: {}, receipt: null };
  assert.equal(updateLodMeshState(state, { meshData: f.candidate }, candidateCommand), state);
  const abandonedRender = updateLodMeshState(state, { meshData: f.base }, recovery);
  assert.equal(abandonedRender.receipt.accepted, true);
  f.context = { meshHash: "replacement", meshData: {} }; f.tracker.checkContext();
  const committed = updateLodMeshState(state, current => current, recovery);
  f.tracker.committed(committed.receipt);
  assert.equal((await promise).status, "cancelled"); assert.equal(recovery.retired, true);
  assert.equal(updateLodMeshState(committed, { meshData: f.base }, recovery), committed);
});

test("a stale empty clear is not disposal, while final renderer teardown retires a queued restoration", async () => {
  const f = fixture(), promise = f.expect(); f.publish();
  f.tracker.disposed(null); assert.equal(f.tracker.snapshot().pending, 1);
  f.tracker.disposed(f.candidate, { recover: true });
  f.tracker.cancel(); f.tracker.disposed(null, { terminal: true });
  assert.equal((await promise).status, "cancelled");
});

test("Inspect to Render runtime handoff keeps an in-flight refinement adoptable", async () => {
  const f = fixture();
  const promise = f.expect();
  f.publish();

  // Inspect is still showing the base scene when its WebGL runtime is
  // replaced. That teardown releases the old scene but does not invalidate
  // the same model context or the candidate already queued in React state.
  f.tracker.disposed(f.base, { handoff: true });
  assert.equal(f.tracker.snapshot().pending, 1);
  assert.deepEqual(f.counts, { commits: 0, recoveries: 0, failures: 0 });

  // The new Render runtime constructs and acknowledges the queued candidate.
  assert.equal(f.tracker.adopted(f.candidate), true);
  assert.equal((await promise).status, "adopted");
  assert.deepEqual(f.counts, { commits: 1, recoveries: 0, failures: 0 });
});

test("Inspect to Render adopts an appearance wrapper as its exact LOD publication", async () => {
  const f = fixture();
  const promise = f.expect();
  f.publish();

  const decorate = source => registerLodDisplaySource({
    ...source,
    appearance: { materials: { steel: {} } },
    parts: source.parts.map(part => ({ ...part, materialId: "steel" })),
  }, source);

  f.tracker.disposed(decorate(f.base), { handoff: true });
  assert.equal(f.tracker.snapshot().pending, 1);
  assert.equal(f.tracker.adopted(decorate(f.candidate)), true);
  assert.equal((await promise).status, "adopted");
  assert.equal(f.context.meshData, f.candidate, "the raw publication, not its display wrapper, is committed");
  assert.deepEqual(f.counts, { commits: 1, recoveries: 0, failures: 0 });
});

test("appearance wrapper registration cannot weaken occurrence or transform validation", async () => {
  for (const decorate of [
    source => ({ ...source, parts: source.parts.slice(1) }),
    source => ({ ...source, parts: source.parts.map((part, index) => index ? part : { ...part, occurrenceId: "other" }) }),
    source => ({ ...source, parts: source.parts.map((part, index) => index ? part : { ...part, transform: [] }) }),
  ]) {
    const f = fixture();
    const promise = f.expect();
    f.publish();
    const invalid = decorate(f.candidate);
    registerLodDisplaySource(invalid, f.candidate);
    assert.equal(f.tracker.adopted(invalid), false);
    f.tracker.disposed(f.candidate);
    assert.equal((await promise).status, "disposed-failed");
    assert.deepEqual(f.counts, { commits: 0, recoveries: 0, failures: 1 });
  }
});

test("runtime handoff remains fatal when the replacement cannot initialize", async () => {
  const f = fixture();
  const promise = f.expect();
  f.publish();

  f.tracker.disposed(f.base, { handoff: true });
  f.tracker.disposed(null, { terminal: true });

  assert.equal((await promise).status, "disposed-failed");
  assert.deepEqual(f.counts, { commits: 0, recoveries: 0, failures: 1 });
});

test("a rejected replay cannot abandon geometry after cleanup failed, even with its exact receipt", async () => {
  const f = fixture(), command = { source: f.candidate }, promise = f.expect(null, { command }); f.publish();
  f.tracker.failed(f.candidate, { cleanupFailed: true });
  const rejected = updateLodMeshState({ value: { meshData: f.base } }, value => value, command);
  f.tracker.committed(rejected.receipt); assert.equal(f.tracker.snapshot().pending, 1);
  assert.equal(f.tracker.adopted(f.candidate), false, "an unresolved partial cleanup cannot certify adoption");
  f.tracker.cancel(); f.tracker.disposed(f.candidate); assert.equal((await promise).status, "cancelled");
});

test("cancelled obsolete progressive adoption waits for the exact latest queued source or its disposal", async () => {
  const f = fixture(), controller = new AbortController(), sources = new WeakSet([f.candidate]);
  const latest = source(f.mesh, [{ id: "other", componentId: "b", sourceMesh: {} }]); sources.add(latest);
  const promise = f.expect(controller.signal, { candidateSources: sources }); f.publish(); f.current = latest;
  controller.abort(); assert.equal(f.tracker.adopted(f.candidate), true);
  assert.equal(f.tracker.snapshot().pending, 1); assert.equal(f.counts.commits, 0);
  f.tracker.adopted(latest); assert.equal((await promise).status, "cancelled"); assert.equal(f.counts.commits, 1);
});

test("batch adoption requires every changed CID, exact key and every occurrence before one commit", async () => {
  const oldA = {}, oldB = {}, nextA = { lodKey: "a@2" }, nextB = { lodKey: "b@3" }, unrelated = {};
  const rows = [["a1", "a"], ["b1", "b"], ["a2", "a"], ["c1", "c"]];
  const descriptor = { occurrences: rows.map(([id, component]) => ({ id, component })) };
  const make = (a, b) => ({ parts: rows.map(([id, componentId]) => ({ id, occurrenceId: id, componentId,
    sourceMesh: componentId === "a" ? a : componentId === "b" ? b : unrelated })) });
  const base = make(oldA, oldB), source = make(nextA, nextB), context = { descriptor, meshData: base };
  let current = source, commits = 0;
  const tracker = createLodSceneAdoption({ currentContext: () => context });
  const promise = tracker.expectBatch({ context, descriptor, source, baseSource: base, currentSource: () => current,
    items: [{ componentId: "a", componentMesh: nextA, baseMesh: oldA, tessellationKey: "a@2" },
      { componentId: "b", componentMesh: nextB, baseMesh: oldB, tessellationKey: "b@3" }],
    commit: () => { commits++; context.meshData = current; },
  }); tracker.published(source);
  for (const candidate of [make(nextA, oldB), make(oldA, nextB), { parts: source.parts.filter(part => part.id !== "a2") },
    { parts: [...source.parts, source.parts[0]] }]) {
    current = candidate; assert.equal(tracker.adopted(candidate), false); assert.equal(commits, 0);
  }
  current = source; assert.equal(tracker.adopted(source), true); assert.equal((await promise).status, "adopted");
  assert.equal(commits, 1); assert.equal(context.meshData, source);
  const wrong = tracker.expectBatch({ context, descriptor, source, baseSource: base,
    items: [{ componentId: "a", componentMesh: nextA, baseMesh: oldA, tessellationKey: "wrong" }] });
  tracker.published(source); assert.equal(tracker.adopted(source), false);
  tracker.disposed(source); assert.equal((await wrong).status, "disposed-failed");
});

test("batch progressive supersession and retiring-source cleanup retain exact multi-CID ownership", async () => {
  const meshes = [{}, {}], old = [{}, {}], descriptor = { occurrences: [{ id: "a", component: "a" }, { id: "b", component: "b" }] };
  const make = values => ({ parts: values.map((sourceMesh, i) => ({ id: i ? "b" : "a", componentId: i ? "b" : "a", sourceMesh })) });
  const base = make(old), source = make(meshes), earlier = { parts: [...source.parts, { id: "c", componentId: "c", sourceMesh: {} }] };
  let current = { parts: [...earlier.parts, { id: "d", componentId: "d", sourceMesh: {} }] };
  const context = { descriptor, meshData: base }, controller = new AbortController();
  const tracker = createLodSceneAdoption({ currentContext: () => context });
  const promise = tracker.expectBatch({ context, source, descriptor, baseSource: base, signal: controller.signal,
    candidateSources: new WeakSet([source, earlier, current]), currentSource: () => current,
    items: meshes.map((componentMesh, i) => ({ componentId: i ? "b" : "a", componentMesh, baseMesh: old[i] })),
  }); tracker.published(source); controller.abort();
  tracker.disposed(earlier); assert.equal((await promise).status, "cancelled");
  assert.equal(tracker.snapshot().pending, 0);
});

import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildModel } from "cadgen-js/common/cadScene.js";
import { applySceneState } from "cadgen-js/common/applySceneState.js";
import { buildComposedPackageMeshData } from "cadgen-js/lib/assembly/meshData.js";
import { resetStepModuleRecordEffects } from "cadgen-js/common/stepModuleEffects.js";
import { applyPartVisualState } from "cadgen-js/lib/viewer/partVisualState.js";
import { applyDisplayRecordTransform, syncRuntimeStepClipPlane } from "cadgen-js/lib/viewer/modelRuntime.js";
import { syncTopologyDisplayEdgeLine } from "cadgen-js/lib/viewer/topologyDisplayEdgeLine.js";
import {
  createStaticSceneReset,
  sceneSourceAlreadyPlaced,
  staticSceneResetEligible
} from "./staticSceneReset.js";

function receiptFixture() {
  const source = { partTransformsBaked: false, parts: [{}] };
  const runtime = { cadScene: { source }, displayRecords: [{}], activeModelKey: "part.step" };
  const input = { source, runtime, visualState: {}, clipState: {} };
  const tracker = createStaticSceneReset();
  tracker.beginRender({}, true);
  const token = {}; tracker.beginRender(token, true);
  return { tracker, token, input };
}

test("a completion belongs to one committed render and can be consumed only once", () => {
  const { tracker, token, input } = receiptFixture();
  assert.equal(tracker.consume(token, input), false, "no adoption receipt");
  tracker.complete(token, input);
  assert.equal(tracker.consume(token, input), true);
  assert.equal(tracker.consume(token, input), false);
  tracker.complete(token, input);
  assert.equal(tracker.consume({}, input), false, "a later render cannot use this receipt");
  assert.equal(tracker.consume(token, input), false, "a failed consumption also clears it");
});

test("prop-only visual or section-clip renders cannot skip, even when source and records are unchanged", () => {
  for (const field of ["visualState", "clipState"]) {
    const { tracker, token, input } = receiptFixture();
    tracker.complete(token, input);
    const nextToken = {}; tracker.beginRender(nextToken, true);
    assert.equal(tracker.consume(nextToken, { ...input, [field]: {} }), false);
    tracker.complete(nextToken, input);
    assert.equal(tracker.consume(nextToken, { ...input, [field]: {} }), false, "live ref changes fail closed too");
  }
});

test("source, scene, record owner, model and runtime changes reject the receipt", () => {
  for (const change of [
    input => ({ ...input, source: { ...input.source } }),
    input => ({ ...input, runtime: { ...input.runtime } }),
    input => { input.runtime.cadScene = { ...input.runtime.cadScene }; return input; },
    input => { input.runtime.cadScene.source = {}; return input; },
    input => { input.runtime.displayRecords = [...input.runtime.displayRecords]; return input; },
    input => { input.runtime.activeModelKey = "other.step"; return input; },
  ]) {
    const { tracker, token, input } = receiptFixture(); tracker.complete(token, input);
    assert.equal(tracker.consume(token, change(input)), false);
  }
});

test("first load, repeated layout setup, invalidation and unmount retain ordinary resets", () => {
  const { input } = receiptFixture(), tracker = createStaticSceneReset(), token = {};
  tracker.beginRender(token, true); tracker.beginRender(token, true);
  tracker.complete(token, input); assert.equal(tracker.consume(token, input), false);
  const next = {}; tracker.beginRender(next, true); tracker.complete(next, input);
  tracker.invalidate(); assert.equal(tracker.consume(next, input), false);
  tracker.complete(next, input); tracker.reset(); assert.equal(tracker.consume(next, input), false);
  tracker.beginRender({}, true); tracker.complete(next, input);
  assert.equal(tracker.consume(next, input), false, "an old effect cannot stamp a newer render");
});

test("placement follow-up skips an exact adopted package but keeps posed wrappers live", () => {
  const adopted = { parts: [] };
  const geometrySource = { vertices: new Float32Array(0) };
  const posed = { geometrySource, parts: [] };
  const runtime = { cadScene: { source: adopted } };
  assert.equal(sceneSourceAlreadyPlaced(runtime, adopted), true);
  assert.equal(sceneSourceAlreadyPlaced(runtime, posed), false);
  runtime.cadScene.source = geometrySource;
  assert.equal(sceneSourceAlreadyPlaced(runtime, posed), false, "wrapper placement remains distinct from retained geometry");
  assert.equal(sceneSourceAlreadyPlaced(null, adopted), false);
});

test("eligibility excludes merged, robot/drawing, active and residual dynamic states", () => {
  const { input } = receiptFixture();
  const base = { source: input.source, renderFormat: "step" };
  assert.equal(staticSceneResetEligible(base), true);
  for (const patch of [
    { source: { ...input.source, partTransformsBaked: true } },
    { source: { ...input.source, geometrySource: {} } }, { source: { parts: [] } },
    { renderFormat: "urdf" }, { renderFormat: "dxf" }, { renderFormat: "glb" },
    { parameters: {} }, { animation: {} }, { drawing: true }, { exploded: true }, { loading: true },
    ...[{ effectMatrix: {} }, { explodedViewMatrix: {} }, { effectStyle: {} }, { effectVisible: false },
      { effectHighlighted: true }, { effectDeformation: {} }, { tubeDeformationState: { active: true } },
      { tubeGpuState: { active: true } }].map(record => ({ records: [record] })),
  ]) assert.equal(staticSceneResetEligible({ ...base, ...patch }), false, JSON.stringify(patch));
});

test("removing a prior module, animation, drawing or exploded pose never skips the transition reset", () => {
  for (const capability of ["parameters", "animation", "drawing", "exploded"]) {
    const { tracker, input } = receiptFixture();
    tracker.beginRender({}, staticSceneResetEligible({ source: input.source, renderFormat: "step", [capability]: {} }));
    const removed = {}; tracker.beginRender(removed, true); tracker.complete(removed, input);
    assert.equal(tracker.consume(removed, input), false, capability);
    const settled = {}; tracker.beginRender(settled, true); tracker.complete(settled, input);
    assert.equal(tracker.consume(settled, input), true, "a subsequent static publication may reuse its completed work");
  }
});

function component(level) {
  const geometry = new THREE.BoxGeometry(1 + level / 10, 1, 1);
  const result = { vertices: geometry.attributes.position.array, normals: geometry.attributes.normal.array,
    indices: geometry.index.array, colors: new Float32Array(0), lodLevel: level,
    bounds: { min: [-(1 + level / 10) / 2, -.5, -.5], max: [(1 + level / 10) / 2, .5, .5] },
    parts: [{ id: "solid", vertexCount: geometry.attributes.position.count, triangleCount: geometry.index.count / 3 }] };
  geometry.dispose(); return result;
}
function descriptor() {
  const occurrences = [["a1", "a", 0], ["a2", "a", 2], ["b1", "b", 4], ["b2", "b", 6]]
    .map(([id, component, x]) => ({ id, component, color: [0.25, 0.5, 0.75],
      transform: [1, 0, 0, x, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] }));
  return { occurrences, assembly: { root: { id: "root", nodeType: "assembly",
    children: occurrences.map(({ id }) => ({ id, nodeType: "part", children: [] })) } } };
}
const visualState = () => ({ hiddenPartIds: [], selectedPartIds: [], hoveredPartId: "", focusedPartId: [], showEdges: false });
const topology = { edges: [{ occurrenceId: "a1", segmentStart: 0, segmentCount: 1 }],
  proxy: { edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]), edgeIndices: new Uint32Array([0, 1]), edgeIds: new Uint32Array([0]) } };
function sceneFixture(source) {
  const scene = buildModel(THREE, source, { renderPartsIndividually: true, parameterSetup: false });
  const runtime = { THREE, cadScene: scene, displayRecords: scene.displayRecords, activeModelKey: "test.step",
    modelGroup: scene.modelGroup, edgesGroup: scene.edgesGroup, modelBounds: scene.bounds, requestRender() {} };
  return { scene, runtime, tracker: createStaticSceneReset(), dispose() {
    syncTopologyDisplayEdgeLine(runtime, null); scene.dispose(); this.tracker.reset();
  } };
}
function syncEdges(runtime, visual, clip) {
  syncTopologyDisplayEdgeLine(runtime, topology, { visible: true, edgeSettings: { color: "#444444", thickness: 1 },
    focusedPartIds: visual.focusedPartId, displayRecords: runtime.displayRecords,
    syncClip: active => syncRuntimeStepClipPlane(active, clip) });
}
function ordinaryReset(runtime, visual, clip) {
  resetStepModuleRecordEffects(runtime.displayRecords, THREE);
  runtime.displayRecords.forEach(record => applyDisplayRecordTransform(THREE, record));
  applyPartVisualState(THREE, runtime.displayRecords, visual);
  runtime.cadScene.syncSurfaceInstances(); syncEdges(runtime, visual, clip);
}
function publish(f, source, visual, clip, optimized) {
  const token = {}, { runtime, tracker, scene } = f;
  tracker.beginRender(token, staticSceneResetEligible({ source, renderFormat: "step", records: runtime.displayRecords }));
  scene.update({ source, stepParameters: null, selection: visual, clip });
  runtime.displayRecords = scene.displayRecords; runtime.modelBounds = scene.bounds;
  syncEdges(runtime, visual, clip); syncRuntimeStepClipPlane(runtime, clip);
  applyPartVisualState(THREE, runtime.displayRecords, visual); scene.syncSurfaceInstances();
  runtime.modelGroup.updateMatrixWorld(true); runtime.edgesGroup.updateMatrixWorld(true);
  const receipt = { source, runtime, visualState: visual, clipState: clip };
  tracker.complete(token, receipt);
  const skipped = optimized && tracker.consume(token, receipt);
  if (!skipped) ordinaryReset(runtime, visual, clip);
  return skipped;
}
function sceneState(f) {
  return { records: f.runtime.displayRecords.map(record => ({ id: record.partId,
    vertices: [...record.geometry.attributes.position.array], matrix: record.mesh.matrix.toArray(),
    color: record.material.color.toArray(), opacity: record.material.opacity, transparent: record.material.transparent,
    visible: record.mesh.visible, order: record.mesh.renderOrder, effectMatrix: record.effectMatrix,
    clip: record.material.clippingPlanes?.map(plane => [plane.normal.toArray(), plane.constant]),
    slot: record.surfaceInstance?.slot, instanceActive: record.surfaceInstance?.active,
  })), sets: [...f.scene.runtime.cadSurfaceInstanceSets].map(set => ({ ids: set.object.userData.partIds,
    matrices: [...set.object.instanceMatrix.array], colors: [...set.object.instanceColor.array] })),
    edge: f.runtime.topologyDisplayEdgeLine?.geometry.attributes.position.array.slice() };
}

test("actual repeated component publications preserve transforms, materials, clipping, edge lines and shared ownership", () => {
  const desc = descriptor(), base = component(0), b = component(0);
  let source = buildComposedPackageMeshData(desc, { a: base, b });
  const control = sceneFixture(source), optimized = sceneFixture(source), visual = visualState();
  const clip = { enabled: true, axis: "x", offsets: { x: .4 }, invert: false };
  try {
    assert.equal(publish(optimized, source, visual, clip, true), false, "first load resets normally");
    publish(control, source, visual, clip, false);
    const retained = optimized.scene.displayRecords.filter(record => record.sourcePart.componentId === "b")
      .map(record => [record, record.mesh, record.geometry]);
    const oldArray = b.vertices.slice();
    for (let level = 1; level <= 3; level++) {
      source = buildComposedPackageMeshData(desc, { a: component(level), b }, { previous: source });
      assert.equal(publish(optimized, source, visual, clip, true), true);
      publish(control, source, visual, clip, false);
      assert.deepEqual(sceneState(optimized), sceneState(control));
      for (const [record, mesh, geometry] of retained) {
        assert.ok(optimized.scene.displayRecords.includes(record)); assert.equal(record.mesh, mesh); assert.equal(record.geometry, geometry);
      }
      assert.deepEqual(b.vertices, oldArray, "source display arrays stay immutable");
    }
  } finally { control.dispose(); optimized.dispose(); }
});

test("actual prop-only visual and section-clip changes still apply after a completed publication", () => {
  const source = buildComposedPackageMeshData(descriptor(), { a: component(0), b: component(0) });
  const control = sceneFixture(source), optimized = sceneFixture(source);
  const visual = visualState(), clip = { enabled: false };
  try {
    publish(optimized, source, visual, clip, true); publish(optimized, source, visual, clip, true);
    publish(control, source, visual, clip, false);
    for (const [nextVisual, nextClip] of [[{ ...visual, hiddenPartIds: ["a1"], selectedPartIds: ["a2"] }, clip],
      [visual, { enabled: true, axis: "y", offsets: { y: .2 }, invert: true }]]) {
      const token = {}; optimized.tracker.beginRender(token, true);
      assert.equal(optimized.tracker.consume(token, { source, runtime: optimized.runtime,
        visualState: nextVisual, clipState: nextClip }), false);
      for (const f of [control, optimized]) {
        syncRuntimeStepClipPlane(f.runtime, nextClip); ordinaryReset(f.runtime, nextVisual, nextClip);
      }
      assert.deepEqual(sceneState(optimized), sceneState(control));
      assert.equal(optimized.runtime.displayRecords.find(record => record.partId === "a1").material.opacity === 0,
        nextVisual.hiddenPartIds.includes("a1"));
      assert.equal(optimized.runtime.displayRecords[0].material.clippingPlanes?.length || 0, nextClip.enabled ? 1 : 0);
    }
  } finally { control.dispose(); optimized.dispose(); }
});

test("actual module and animation removal restores rest records even beside a new publication", () => {
  for (const kind of ["parameters", "animation"]) {
    const desc = descriptor(), components = { a: component(0), b: component(0) };
    const source = buildComposedPackageMeshData(desc, components);
    const control = sceneFixture(source), optimized = sceneFixture(source), visual = visualState(), clip = { enabled: false };
    const parameters = kind === "parameters" ? { definition: { manifest: {}, module: { update(ctx) {
      ctx.effects.transform("a1", { translate: [3, 2, 1] });
      ctx.effects.style("a1", { color: "#ff0000", opacity: .4 });
    } } } } : null;
    const animation = kind === "animation" ? { elapsedSec: 0, clip: { duration: 1, update(t, model) {
      model.get("a1").translate([3, 2, 1]).opacity(.4);
    } } } : null;
    try {
      for (const f of [control, optimized]) {
        publish(f, source, visual, clip, false);
        f.tracker.beginRender({}, staticSceneResetEligible({ source, renderFormat: "step", parameters, animation }));
        applySceneState(THREE, { runtime: f.runtime, meshData: source, stepParameterRuntime: parameters, animation });
        f.runtime.displayRecords.forEach(record => applyDisplayRecordTransform(THREE, record));
        applyPartVisualState(THREE, f.runtime.displayRecords, visual); f.scene.syncSurfaceInstances();
        assert.ok(f.runtime.displayRecords[0].effectMatrix, "the prior dynamic frame really changed geometry placement");
      }
      const next = buildComposedPackageMeshData(desc, { ...components, a: component(1) }, { previous: source });
      assert.equal(publish(optimized, next, visual, clip, true), false, "transition gets the full reset");
      publish(control, next, visual, clip, false);
      assert.deepEqual(sceneState(optimized), sceneState(control));
      assert.equal(optimized.runtime.displayRecords[0].effectMatrix, null);
      assert.equal(optimized.runtime.displayRecords[0].material.opacity, 1);
      assert.deepEqual(optimized.runtime.displayRecords[0].mesh.matrix.elements.slice(12, 15), [0, 0, 0]);
    } finally { control.dispose(); optimized.dispose(); }
  }
});

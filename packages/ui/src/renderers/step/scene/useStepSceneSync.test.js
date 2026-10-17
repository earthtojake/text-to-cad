import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { normalizeControlValues } from "@text-to-cad/core/common/articulation.js";
import { renderHook } from "../../../../scripts/reactHarness.mjs";
import { createViewSettingsStore } from "../../kit/view-settings/viewSettingsStore.js";
import { createStepScene } from "./stepScene.js";
import { useStepSceneSync } from "./useStepSceneSync.js";
import { useStepViewPolicy } from "./useStepViewPolicy.js";

// A STEP as the viewer receives it: a composed package, here one occurrence of a part
// whose CAD edges (a feature outline and one tangent edge) the scene draws as one instanced set.
function stepPackage() {
  const bounds = { min: [0, 0, 0], max: [1, 1, 0] };
  const component = {
    vertices: new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]),
    indices: new Uint32Array([0, 1, 2, 0, 2, 3]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]),
    cadEdgePositions: new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0]),
    cadEdgeIndices: new Uint32Array([0, 1, 1, 2, 2, 3, 4, 5]),
    cadEdgeClassRanges: [
      { classId: "feature", pointStart: 0, pointCount: 4, segmentStart: 0, segmentCount: 3 },
      { classId: "tangent", pointStart: 4, pointCount: 2, segmentStart: 3, segmentCount: 1 }
    ],
    bounds
  };
  return { bounds, partTransformsBaked: false, parts: [{ id: "o1", occurrenceId: "o1", componentId: "c1",
    sourceMesh: component, sourceMeshKey: "c1", bounds, vertexCount: 4, triangleCount: 2,
    transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] }] };
}

// The set's feature and tangent class colours, against two hex colours (linear, as three holds them).
function assertInk(set, [feature, tangent], message) {
  const elements = set.uniforms.cadClassColor.value.elements;
  [feature, tangent].forEach((hex, index) => new THREE.Color(hex).toArray().forEach((value, channel) =>
    assert.ok(Math.abs(elements[index * 4 + channel] - value) < 1e-6, `${message}: class ${index} is not ${hex}`)));
}

// The scene sync as StepSceneLayers wires it, over a runtime with no renderer: the Display panel's
// store, the policy derived from what it resolves, and the sync building into one STEP scene.
function mountSceneSync(meshData, props = {}) {
  const sync = { frames: 0 };
  const runtime = {
    THREE, modelGroup: new THREE.Group(), edgesGroup: new THREE.Group(), facePickGroup: new THREE.Group(),
    edgePickGroup: new THREE.Group(), requestRender: () => { sync.frames += 1; }
  };
  const stepScene = createStepScene(THREE);
  const ref = current => ({ current });
  const refs = {
    partVisualStateRef: ref(null), clipSettingsRef: ref(null), staticSceneResetRef: ref({ invalidate() {}, complete() {} }),
    viewerAlertChangeRef: ref(null), sceneUpdateAlertRef: ref(null)
  };
  const store = createViewSettingsStore({}, { appearance: "light", lightingQuality: "preview" });
  const view = renderHook(({ scene }) => {
    const policy = useStepViewPolicy({ meshData, themeSettings: scene.theme, displaySettings: scene.display,
      renderMode: scene.render.enabled, renderConfiguration: scene.render.configuration });
    const edges = policy.edgeVisibility({ selectorRuntime: null });
    refs.partVisualStateRef.current = { viewerTheme: policy.viewerTheme, edgeSettings: policy.visualEdgeSettings,
      showEdges: edges.recordEdgesVisible, displayMode: policy.normalizedDisplayMode };
    useStepSceneSync({
      viewport: { runtimeRef: ref(runtime), viewerReadyTick: 1, commitScene() {} }, stepScene,
      props: { meshData, modelKey: "part.step", isLoading: false, appearance: scene.appearance, ...props },
      policy, refs, edges, staticResetRenderToken: 0, setTransformedSelectorRuntime() {}, setDisplayRecordsToken() {},
      // The sync reports a failed build here rather than throwing it.
      setError: error => { if (error) throw new Error(error); }
    });
  }, { scene: store.getSnapshot().scene });
  return Object.assign(sync, { view, store, stepScene });
}

test("an edge colour edit recolours the live CAD edges without a rebuild, and Reset puts the default ink back", () => {
  const sync = mountSceneSync(stepPackage());
  const { view, store, stepScene } = sync;
  const record = stepScene.displayRecords[0];
  const { set } = record.edgeInstance;
  assertInk(set, ["#253443", "#667788"], "the default ink");

  sync.frames = 0;
  view.update({ scene: store.patch({ edges: { color: "#ff0000" } }).scene });
  assert.equal(stepScene.displayRecords[0], record, "the record on screen is kept: nothing was rebuilt");
  assert.equal(record.edgeInstance.set, set, "and so is its instanced edge draw");
  assertInk(set, ["#ff0000", "#ff0000"], "the edited colour");
  assert.ok(sync.frames > 0, "a frame is asked for");

  view.update({ scene: store.reset().scene });
  assert.equal(stepScene.displayRecords[0], record);
  assertInk(set, ["#253443", "#667788"], "Reset's default ink");
  view.unmount();
  stepScene.dispose();
});

// The pose the renderer hands the viewport -- StepSurface's runtime, cadgen's articulation at the
// Position values -- is the pose the scene is BUILT at: its first frame draws the model posed.
test("the scene is built at the pose on screen: a part its joint has moved is drawn moved from the first frame", () => {
  // A slider carrying the one occurrence along Z, opened 4 mm out.
  const articulation = { schemaVersion: 2,
    controls: [{ id: "lift", label: "Lift", unit: "mm", min: 0, max: 10, default: 0 }],
    joints: [{ id: "lift", parent: null, kind: "slider", origin: [0, 0, 0], axis: [0, 0, 1],
      travel: { bias: 0, terms: [["lift", 1]] } }],
    carries: { lift: ["o1"] }, handles: [], poses: {}, opening: { lift: 0 } };
  const { view, stepScene } = mountSceneSync(stepPackage(),
    { stepParameterRuntime: { articulation, values: normalizeControlValues(articulation, { lift: 4 }) } });
  const [record] = stepScene.displayRecords;
  assert.ok(record.effectMatrix, "the build posed the record");
  assert.deepEqual(record.mesh.matrix.elements.slice(12, 15), [0, 0, 4]);
  view.unmount();
  stepScene.dispose();
});

import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { renderHook } from "../../../../scripts/reactHarness.mjs";
import { createViewSettingsStore } from "../../kit/view-settings/viewSettingsStore.js";
import { createStepScene } from "./stepScene.js";
import { useStepSceneSync } from "./useStepSceneSync.js";
import { useStepViewPolicy } from "./useStepViewPolicy.js";

// A STEP as the viewer receives it: a composed package, here one occurrence of a surf component
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

test("an edge colour edit recolours the live CAD edges without a rebuild, and Reset puts the default ink back", () => {
  const meshData = stepPackage();
  let frames = 0;
  const runtime = {
    THREE, modelGroup: new THREE.Group(), edgesGroup: new THREE.Group(), facePickGroup: new THREE.Group(),
    edgePickGroup: new THREE.Group(), requestRender: () => { frames += 1; }
  };
  const stepScene = createStepScene(THREE);
  const ref = current => ({ current });
  const refs = {
    partVisualStateRef: ref(null), clipSettingsRef: ref(null), staticSceneResetRef: ref({ invalidate() {}, complete() {} }),
    meshSourceAdoptionRef: ref(null), viewerAlertChangeRef: ref(null), sceneUpdateAlertRef: ref(null), lodCameraChangeRef: ref(null)
  };
  // The Display panel's store, and the policy and scene sync that StepSceneLayers wires from what it resolves.
  const store = createViewSettingsStore({}, { appearance: "light", lightingQuality: "preview" });
  const view = renderHook(({ scene }) => {
    const policy = useStepViewPolicy({ meshData, themeSettings: scene.theme, displaySettings: scene.display,
      renderMode: scene.render.enabled, renderConfiguration: scene.render.configuration });
    const edges = policy.edgeVisibility({ selectorRuntime: null });
    refs.partVisualStateRef.current = { viewerTheme: policy.viewerTheme, edgeSettings: policy.visualEdgeSettings,
      showEdges: edges.recordEdgesVisible, displayMode: policy.normalizedDisplayMode };
    useStepSceneSync({
      viewport: { runtimeRef: ref(runtime), viewerReadyTick: 1, commitScene() {} }, stepScene,
      props: { meshData, modelKey: "part.step", isLoading: false, appearance: scene.appearance },
      policy, refs, edges, staticResetRenderToken: 0, setTransformedSelectorRuntime() {}, setDisplayRecordsToken() {},
      // The sync reports a failed build here rather than throwing it.
      setError: error => { if (error) throw new Error(error); }
    });
  }, { scene: store.getSnapshot().scene });

  const record = stepScene.displayRecords[0];
  const { set } = record.edgeInstance;
  assertInk(set, ["#253443", "#667788"], "the default ink");

  frames = 0;
  view.update({ scene: store.patch({ edges: { color: "#ff0000" } }).scene });
  assert.equal(stepScene.displayRecords[0], record, "the record on screen is kept: nothing was rebuilt");
  assert.equal(record.edgeInstance.set, set, "and so is its instanced edge draw");
  assertInk(set, ["#ff0000", "#ff0000"], "the edited colour");
  assert.ok(frames > 0, "a frame is asked for");

  view.update({ scene: store.reset().scene });
  assert.equal(stepScene.displayRecords[0], record);
  assertInk(set, ["#253443", "#667788"], "Reset's default ink");
  view.unmount();
  stepScene.dispose();
});

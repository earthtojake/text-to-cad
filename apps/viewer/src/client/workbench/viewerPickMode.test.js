import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { VIEWER_PICK_MODE } from "cadgen-js/lib/viewer/constants.js";
import { syncSelectorPickGroups } from "cadgen-js/lib/viewer/selectorPickGroups.js";
import { applySceneState } from "cadgen-js/common/applySceneState.js";
import { resetStepModuleRecordEffects } from "cadgen-js/common/stepModuleEffects.js";
import { loadTubeDeformation } from "cadgen-js/common/tubeDeformationChunk.js";

// `deformTube` needs the lazy tube runtime, which production loads through
// compileAnimationSource. This clip is built by hand, so load it here.
await loadTubeDeformation();
import { viewerHiddenPartIdsForRenderPane, viewerPickModeForRenderPane, viewerSelectedPartIdsForRenderPane, viewerSelectorRuntimeForRenderPane } from "./viewerPickMode.js";

test("Render drops retained picking proxies while STEP transforms and tube deformation still apply", () => {
  const selectors = { proxy: {
    edgePositions: new Float32Array([0, 0, 0, 10, 0, 0]), edgeIndices: new Uint32Array([0, 1]),
    vertexPositions: new Float32Array([0, 0, 0])
  } };
  const select = options => viewerSelectorRuntimeForRenderPane({ hasTopology: true, selectorRuntime: selectors, ...options });
  assert.equal(select({ renderMode: false }), selectors);
  assert.equal(select({ renderMode: false, retainingPreviousStepMesh: true }), null);
  assert.equal(select({ hasTopology: false }), null);
  const selectorRuntime = select({ renderMode: true });
  assert.equal(selectorRuntime, null);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 1, 5, 0, 1, 10, 0, 1], 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1, 0, 0, 1], 3));
  const mesh = new THREE.Mesh(geometry);
  const record = { partId: "o1", mesh, geometry, partBounds: { min: [0, 0, 0], max: [10, 1, 1] } };
  const runtime = { THREE, displayRecords: [record], facePickGroup: new THREE.Group(), edgePickGroup: new THREE.Group(), vertexPickGroup: new THREE.Group() };
  try {
    syncSelectorPickGroups(runtime, selectorRuntime);
    assert.equal(runtime.facePickGroup.children.length + runtime.edgePickGroup.children.length + runtime.vertexPickGroup.children.length, 0);
    const path = y => ({ normal: [0, 0, 1], segments: [{ kind: "line", start: [0, y, 0], end: [10, y, 0] }] });
    const clip = { duration: 1, update(t, model) { model.get("rope").deformTube({ rest: path(0), path: path(t * 10) }).translate([0, 0, 5]); } };
    const result = applySceneState(THREE, {
      runtime, meshData: { parts: [{ id: "o1", label: "rope" }] }, selectorRuntime,
      animation: { clip, elapsedSec: 0.5 }, onError: ({ error }) => { throw error; }
    });
    assert.equal(result.transformDetected, true);
    assert.deepEqual(new THREE.Vector3().applyMatrix4(record.effectMatrix).toArray(), [0, 0, 5]);
    assert.deepEqual(Array.from(record.geometry.attributes.position.array.slice(0, 3)), [0, 5, 1]);
  } finally {
    resetStepModuleRecordEffects([record], THREE);
    geometry.dispose();
    mesh.material.dispose();
  }
});

test("viewer pick mode uses assembly picking for unfocused assembly navigation", () => {
  assert.equal(
    viewerPickModeForRenderPane({ viewerMode: "assembly" }),
    VIEWER_PICK_MODE.ASSEMBLY
  );
});

test("viewer pick mode switches focused assemblies to topology picking", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      focusedPartIds: "o1.4"
    }),
    VIEWER_PICK_MODE.AUTO
  );
});

test("viewer pick mode keeps focused assemblies pickable when child components are active", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      assemblyPickingActive: true,
      focusedPartIds: "o1.4"
    }),
    VIEWER_PICK_MODE.ASSEMBLY
  );
});

test("viewer pick mode uses hybrid topology picking when expanded topology is visible", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      assemblyPickingActive: true,
      topologyPickingActive: true
    }),
    VIEWER_PICK_MODE.AUTO
  );
});

test("viewer pick mode switches multi-focused assemblies to topology picking", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      focusedPartIds: ["o1.4", "o1.5"]
    }),
    VIEWER_PICK_MODE.AUTO
  );
});

test("viewer pick mode disables picking while topology assets are pending", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      focusedPartIds: "o1.4",
      topologySelectionPending: true
    }),
    VIEWER_PICK_MODE.NONE
  );
});

test("viewer pick mode switches to measure picking when the measure tool is active on pickable topology", () => {
  assert.equal(
    viewerPickModeForRenderPane({ measureMode: true, topologyPickingActive: true }),
    VIEWER_PICK_MODE.MEASURE
  );
});

test("viewer pick mode keeps measure picking in focused part views", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "part",
      measureMode: true,
      topologyPickingActive: true
    }),
    VIEWER_PICK_MODE.MEASURE
  );
});

test("viewer pick mode measures without pickable topology", () => {
  // The endpoint comes from the ray hit on the mesh; topology only refines it.
  assert.equal(
    viewerPickModeForRenderPane({ measureMode: true, topologyPickingActive: false }),
    VIEWER_PICK_MODE.MEASURE
  );
});

test("viewer pick mode measures in assemblies, with or without loaded topology", () => {
  assert.equal(
    viewerPickModeForRenderPane({ viewerMode: "assembly", measureMode: true, topologyPickingActive: true }),
    VIEWER_PICK_MODE.MEASURE
  );
  // Measure outranks part selection, so a click across a bare assembly measures
  // rather than selecting whichever part sat under the cursor.
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      measureMode: true,
      topologyPickingActive: false,
      assemblyPickingActive: true
    }),
    VIEWER_PICK_MODE.MEASURE
  );
  assert.equal(
    viewerPickModeForRenderPane({ viewerMode: "assembly", measureMode: false, topologyPickingActive: false }),
    VIEWER_PICK_MODE.ASSEMBLY
  );
});

test("viewer pick mode still yields to the pan tool while measuring", () => {
  assert.equal(
    viewerPickModeForRenderPane({ measureMode: true, panToolActive: true }),
    VIEWER_PICK_MODE.NONE
  );
});

test("viewer pick mode blocks measure picking while topology assets are pending", () => {
  assert.equal(
    viewerPickModeForRenderPane({ measureMode: true, topologyPickingActive: true, topologySelectionPending: true }),
    VIEWER_PICK_MODE.NONE
  );
});

test("viewer pick mode falls back to auto without the measure tool", () => {
  assert.equal(
    viewerPickModeForRenderPane({ measureMode: false }),
    VIEWER_PICK_MODE.AUTO
  );
});

test("Render hands the scene no selected parts, so the Materials selection never tints the photographic view", () => {
  const selectedPartIds = ["base", "pin_0"];
  const select = options => viewerSelectedPartIdsForRenderPane({ hasParts: true, selectedPartIds, ...options });
  assert.equal(select({ renderMode: false }), selectedPartIds);
  assert.deepEqual(select({ renderMode: false, hasParts: false }), []);
  assert.deepEqual(select({ renderMode: false, selectedPartIds: null }), []);
  // The Inspect selection effect (surface tint + dithered occlusion ghost)
  // would repaint the material the Materials tab just applied.
  assert.deepEqual(select({ renderMode: true }), []);
});

test("Inspect owns hidden parts, and Render or a part-less scene hides nothing", () => {
  const hiddenPartIds = ["pin_0"];
  const hide = options => viewerHiddenPartIdsForRenderPane({ inspectionEnabled: true, hasParts: true, hiddenPartIds, ...options });
  assert.equal(hide(), hiddenPartIds);
  assert.deepEqual(hide({ inspectionEnabled: false }), []);
  assert.deepEqual(hide({ hasParts: false }), []);
  assert.deepEqual(hide({ hiddenPartIds: null }), []);
});

test("an empty selection keeps one identity, so an unchanged render cannot resample the viewport", () => {
  // The viewer's scene-effects effect takes this value as a dependency and
  // resamples viewport LOD when it runs. A fresh [] per render made every
  // render new work, and the LOD status it published re-rendered the
  // workspace: an idle viewport never reached a settled state.
  const empty = viewerSelectedPartIdsForRenderPane({ renderMode: true, hasParts: true, selectedPartIds: ["base"] });
  assert.deepEqual(empty, []);
  assert.equal(viewerSelectedPartIdsForRenderPane({ renderMode: true, hasParts: true, selectedPartIds: ["base"] }), empty);
  assert.equal(viewerSelectedPartIdsForRenderPane({ hasParts: false, selectedPartIds: ["base"] }), empty);
  assert.equal(viewerSelectedPartIdsForRenderPane({ hasParts: true, selectedPartIds: null }), empty);
  assert.equal(viewerSelectedPartIdsForRenderPane(), empty);
  // Hidden parts feed the same scene-effects dependency list.
  assert.equal(viewerHiddenPartIdsForRenderPane({ inspectionEnabled: false, hasParts: true, hiddenPartIds: ["pin_0"] }), empty);
  assert.equal(viewerHiddenPartIdsForRenderPane({ inspectionEnabled: true, hasParts: false, hiddenPartIds: ["pin_0"] }), empty);
  assert.equal(viewerHiddenPartIdsForRenderPane(), empty);
});

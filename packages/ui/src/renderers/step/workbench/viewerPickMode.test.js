import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { VIEWER_PICK_MODE } from "@text-to-cad/core/lib/viewer/constants.js";
import { syncSelectorPickGroups } from "@text-to-cad/core/lib/viewer/selectorPickGroups.js";
import { applySceneState } from "@text-to-cad/core/common/applySceneState.js";
import { resetStepModuleRecordEffects } from "@text-to-cad/core/common/stepModuleEffects.js";
import { attachTubeSkins } from "@text-to-cad/core/common/tubeSkin.js";
import { viewerHiddenPartIdsForRenderPane, viewerPickModeForRenderPane, viewerSelectedPartIdsForRenderPane, viewerSelectorRuntimeForRenderPane } from "./viewerPickMode.js";

test("Render retains picking proxies while STEP transforms and tube skins still apply", () => {
  const selectors = { proxy: {
    edgePositions: new Float32Array([0, 0, 0, 10, 0, 0]), edgeIndices: new Uint32Array([0, 1]),
    vertexPositions: new Float32Array([0, 0, 0])
  } };
  const select = options => viewerSelectorRuntimeForRenderPane({ hasTopology: true, selectorRuntime: selectors, ...options });
  assert.equal(select({ renderMode: false }), selectors);
  assert.equal(select({ renderMode: false, retainingPreviousStepMesh: true }), null);
  assert.equal(select({ hasTopology: false }), null);
  const selectorRuntime = select({ renderMode: true });
  assert.equal(selectorRuntime, selectors);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 1, 5, 0, 1, 10, 0, 1], 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1, 0, 0, 1], 3));
  const mesh = new THREE.Mesh(geometry);
  const record = { partId: "o1", mesh, geometry, partBounds: { min: [0, 0, 0], max: [10, 1, 1] } };
  const runtime = { THREE, displayRecords: [record], facePickGroup: new THREE.Group(), edgePickGroup: new THREE.Group() };
  try {
    syncSelectorPickGroups(runtime, selectorRuntime);
    assert.ok(runtime.edgePickGroup.children.length > 0);
    const path = y => ({ normal: [0, 0, 1], segments: [{ kind: "line", start: [0, y, 0], end: [10, y, 0] }] });
    // The rope lifts 5 mm and its centreline slides 10 mm sideways over the second: its two
    // joints, at either end, move 10 mm in y between the keys (cadgen's skin, written out).
    const clip = { id: "lift", label: "Lift", duration: 1, loop: true, tracks: [
      { targets: ["o1"], times: [0, 1], rest: path(0), maxSegmentLength: 10,
        tube: [{ path: path(0), twistDeg: 0 }, { path: path(10), twistDeg: 0 }] },
      { targets: ["o1"], times: [0], pivot: [0, 0, 0], transform: [[0, 0, 5, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]] }
    ] };
    const joint = (x, y) => [x, y, 0, 0, 0, 0, 1];
    attachTubeSkins({ lift: clip }, {
      bindings: [{
        occurrence: "o1", joints: 2, rest: new Float32Array([...joint(0, 0), ...joint(10, 0)]),
        positions: new Float32Array([0, 0, 1, 5, 0, 1, 10, 0, 1]), normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
        indices: new Uint32Array([0, 1, 2]), sourceTriangles: new Uint32Array([0]), along: new Float32Array([0, 0.5, 1]),
        material: new Float32Array(9), edgePositions: new Float32Array(0), edgeAlong: new Float32Array(0),
        edgeOrdinals: new Uint32Array(0), edgeClasses: new Uint8Array(0)
      }],
      tracks: [{ clip: "lift", track: 0, bindings: [0],
        keys: new Float32Array([...joint(0, 0), ...joint(10, 0), ...joint(0, 10), ...joint(10, 10)]) }]
    });
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

test('explicit filters never use the automatic part fallback', () => {
  for (const selectionFilter of ['faces','edges']) {
    assert.equal(viewerPickModeForRenderPane({selectionFilter,viewerMode:'assembly'}), VIEWER_PICK_MODE.TOPOLOGY);
  }
  assert.equal(viewerPickModeForRenderPane({selectionFilter:'parts',topologySelectionPending:true}),VIEWER_PICK_MODE.PARTS);
  assert.equal(viewerPickModeForRenderPane({selectionFilter:'edges',measureMode:true}),VIEWER_PICK_MODE.MEASURE);
});

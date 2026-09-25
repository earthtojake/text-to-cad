import assert from "node:assert/strict";
import test from "node:test";

import { VIEWER_PICK_MODE } from "cadgen-js/lib/viewer/constants.js";
import { viewerPickModeForRenderPane } from "./viewerPickMode.js";

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

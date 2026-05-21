import assert from "node:assert/strict";
import test from "node:test";

import { buildCadViewState, formatCadViewStateForClipboard } from "./viewState.js";

test("buildCadViewState captures file, camera, selection, and view data", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    entry: {
      key: "generated/model.step",
      kind: "assembly",
      name: "model.step",
      source: { path: "generated/model.step" },
      step: { path: "generated/model.step" }
    },
    cadPath: "resources/generated/model",
    renderFormat: "step",
    perspective: {
      position: [1, 2, 3],
      target: [0, 0, 0],
      up: [0, 0, 1],
      modelKey: "abc"
    },
    selectedPartIds: ["o1.2", "o1.2", ""],
    selectedParts: [{ id: "o1.2", displayName: "gear", leafPartIds: ["o1.2"] }],
    selectedReferenceIds: ["topology|o1.2|face|o1.2.f1"],
    selectedReferences: [{ id: "topology|o1.2|face|o1.2.f1", displaySelector: "o1.2.f1" }],
    selectedCadRefs: ["@cad[resources/generated/model#o1.2.f1]"],
    hiddenPartIds: ["o1.4"],
    expandedTreeNodeIds: ["o1"],
    clipSettings: { enabled: true, axis: "z" },
    themeSettings: { preset: "dark" },
    url: "http://127.0.0.1:4178/?file=generated/model.step"
  });

  assert.equal(state.schema, "cad-explorer-view-state");
  assert.equal(state.file.cadPath, "resources/generated/model");
  assert.deepEqual(state.camera.perspective.position, [1, 2, 3]);
  assert.deepEqual(state.selection.selectedPartIds, ["o1.2"]);
  assert.equal(state.selection.selectedParts[0].displayName, "gear");
  assert.equal(state.selection.selectedReferences[0].displaySelector, "o1.2.f1");
  assert.deepEqual(state.assembly.hiddenPartIds, ["o1.4"]);
  assert.equal(state.view.clipSettings.enabled, true);
});

test("formatCadViewStateForClipboard includes a short summary and JSON payload", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    cadPath: "resources/generated/model",
    selectedPartIds: ["o1.2"],
    selectedCadRefs: ["@cad[resources/generated/model#o1.2]"]
  });
  const text = formatCadViewStateForClipboard(state);

  assert.match(text, /CAD Explorer view state/);
  assert.match(text, /File: resources\/generated\/model/);
  assert.match(text, /Parts: o1\.2/);
  assert.match(text, /"schema": "cad-explorer-view-state"/);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  CAD_EXPLORER_VIEW_STATE_SCHEMA,
  CAD_EXPLORER_VIEW_STATE_VERSION,
  CAD_REVIEW_STATE_SCHEMA,
  buildCadViewState,
  buildCadViewStateFromParams,
  buildCadViewStateQueryString,
  formatCadViewStateForClipboard,
  hasCadViewStateParams,
  normalizeCadViewStateForApply,
  parseCadViewStateClipboardText
} from "./viewState.js";

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

  assert.equal(state.schema, CAD_EXPLORER_VIEW_STATE_SCHEMA);
  assert.equal(state.version, CAD_EXPLORER_VIEW_STATE_VERSION);
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
  assert.match(text, /CAD refs: @cad\[resources\/generated\/model#o1\.2\]/);
  assert.match(text, /"schema": "cad-explorer-view-state"/);

  const [summary, payload] = text.trimEnd().split("\n\n");
  assert.equal(summary, [
    "CAD Explorer view state",
    "File: resources/generated/model",
    "Parts: o1.2",
    "CAD refs: @cad[resources/generated/model#o1.2]"
  ].join("\n"));
  assert.equal(JSON.parse(payload).schema, CAD_EXPLORER_VIEW_STATE_SCHEMA);
});

test("parseCadViewStateClipboardText reads summary-prefixed payloads", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    entry: { key: "generated/model.step", cadPath: "generated/model.step" },
    cadPath: "resources/generated/model",
    perspective: {
      position: [1, 2, 3],
      target: [0, 0, 0],
      up: [0, 1, 0]
    },
    selectedPartIds: ["solid-1"],
    hiddenPartIds: ["solid-2"]
  });

  const parsed = parseCadViewStateClipboardText(formatCadViewStateForClipboard(state));
  const normalized = normalizeCadViewStateForApply(parsed);

  assert.equal(normalized.file.key, "generated/model.step");
  assert.deepEqual(normalized.camera.perspective.position, [1, 2, 3]);
  assert.deepEqual(normalized.selection.selectedPartIds, ["solid-1"]);
  assert.deepEqual(normalized.assembly.hiddenPartIds, ["solid-2"]);
});

test("parseCadViewStateClipboardText accepts direct JSON payloads", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    cadPath: "resources/generated/direct-model",
    selectedReferenceIds: ["face-1"]
  });

  const parsed = parseCadViewStateClipboardText(JSON.stringify(state));

  assert.equal(parsed.schema, CAD_EXPLORER_VIEW_STATE_SCHEMA);
  assert.equal(parsed.file.cadPath, "resources/generated/direct-model");
  assert.deepEqual(parsed.selection.selectedReferenceIds, ["face-1"]);
});

test("parseCadViewStateClipboardText extracts payloads from surrounding prose", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    cadPath: "resources/generated/prose-model",
    hiddenPartIds: ["part-a"]
  });
  const clipboardText = [
    "I reviewed this model from a low front view.",
    "",
    formatCadViewStateForClipboard(state),
    "Additional issue notes after the JSON should be ignored."
  ].join("\n");

  const parsed = parseCadViewStateClipboardText(clipboardText);

  assert.equal(parsed.schema, CAD_EXPLORER_VIEW_STATE_SCHEMA);
  assert.equal(parsed.file.cadPath, "resources/generated/prose-model");
  assert.deepEqual(parsed.assembly.hiddenPartIds, ["part-a"]);
});

test("normalizeCadViewStateForApply rejects unsupported schemas", () => {
  assert.throws(
    () => normalizeCadViewStateForApply({ schema: "other-view-state" }),
    /Unsupported CAD view state/
  );
});

test("normalizeCadViewStateForApply sanitizes duplicate ids and invalid camera snapshots", () => {
  const normalized = normalizeCadViewStateForApply({
    schema: CAD_EXPLORER_VIEW_STATE_SCHEMA,
    file: { cadPath: " resources/generated/model " },
    camera: {
      perspective: {
        position: [1, 2],
        target: [0, 0, 0],
        up: [0, 0, 1]
      }
    },
    selection: {
      selectedPartIds: [" part-a ", "part-a", ""],
      selectedReferenceIds: ["face-1", "face-1"],
      cadRefs: [" @cad[resources/generated/model#face-1] "]
    },
    assembly: {
      hiddenPartIds: ["part-b", "part-b"],
      expandedTreeNodeIds: ["root", ""],
      expandedAssemblyPartIds: ["asm-1", "asm-1"]
    },
    view: {
      clipSettings: { enabled: true },
      themeSettings: undefined,
      layout: { sidebarOpen: true }
    }
  });

  assert.equal(normalized.file.cadPath, "resources/generated/model");
  assert.equal(normalized.camera.perspective, null);
  assert.deepEqual(normalized.selection.selectedPartIds, ["part-a"]);
  assert.deepEqual(normalized.selection.selectedReferenceIds, ["face-1"]);
  assert.deepEqual(normalized.selection.cadRefs, ["@cad[resources/generated/model#face-1]"]);
  assert.deepEqual(normalized.assembly.hiddenPartIds, ["part-b"]);
  assert.deepEqual(normalized.assembly.expandedTreeNodeIds, ["root"]);
  assert.deepEqual(normalized.assembly.expandedAssemblyPartIds, ["asm-1"]);
  assert.deepEqual(normalized.view.clipSettings, { enabled: true });
  assert.equal(normalized.view.themeSettings, null);
  assert.deepEqual(normalized.view.layout, { sidebarOpen: true });
});

test("buildCadViewStateQueryString stores full review state in a view query param", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    entry: {
      key: "generated/model.step",
      kind: "part",
      name: "model.step",
      file: "generated/model.step"
    },
    cadPath: "resources/generated/model",
    renderFormat: "step",
    perspective: {
      position: [5.2, -3.1, 8.8],
      target: [0, 0, 0],
      up: [0, 0, 1],
      modelKey: "generated/model.step",
      sceneScaleMode: "normalized",
      coordinateSystem: "z-up"
    },
    selectedPartIds: ["o1.2", "o1.4"],
    selectedReferenceIds: ["topology|o1.2|face|o1.2.f1", "topology|o1.4|face|f1"],
    selectedCadRefs: ["@cad[resources/generated/model#o1.2.f1]"],
    hiddenPartIds: ["o1.10", "o1.12"],
    expandedTreeNodeIds: ["root", "o1"],
    expandedAssemblyPartIds: ["o1.2"],
    selectedRenderPartIdByAssemblyPartId: { "o1.2": "mesh:17" },
    explorerMode: "assembly",
    clipSettings: { axis: "z", plane: 0.5, enabled: true, inverted: true },
    layout: { sidebarOpen: true, tabToolsOpen: false, tabToolMode: "references" }
  });
  const qs = buildCadViewStateQueryString(state);

  const params = new URLSearchParams(qs);
  const encodedPayload = params.get("view");
  assert.ok(encodedPayload);
  assert.equal(params.has("v"), false);
  assert.equal(params.has("sp"), false);
  const payload = JSON.parse(Buffer.from(encodedPayload, "base64url").toString("utf8"));
  assert.equal(payload.schema, CAD_REVIEW_STATE_SCHEMA);
  assert.equal(payload.file.key, "generated/model.step");
  assert.equal(payload.file.cadPath, "resources/generated/model");
  assert.equal(payload.camera.perspective.modelKey, "generated/model.step");
  assert.deepEqual(payload.selection.selectedPartIds, ["o1.2", "o1.4"]);
  assert.deepEqual(payload.selection.cadRefs, ["@cad[resources/generated/model#o1.2.f1]"]);
  assert.deepEqual(payload.visibility.hiddenPartIds, ["o1.10", "o1.12"]);
  assert.deepEqual(payload.assembly.expandedAssemblyPartIds, ["o1.2"]);
  assert.equal(payload.assembly.expandedTreeNodeIds, undefined);
  assert.equal(payload.scene.explorerMode, undefined);
  assert.equal(payload.view, undefined);
  assert.deepEqual(payload.clip, { axis: "z", plane: 0.5, enabled: true, inverted: true });

  const parsed = buildCadViewStateFromParams(params);
  const normalized = normalizeCadViewStateForApply(parsed);
  assert.equal(normalized.file.key, "generated/model.step");
  assert.equal(normalized.file.cadPath, "resources/generated/model");
  assert.equal(normalized.camera.perspective.modelKey, "generated/model.step");
  assert.equal(normalized.camera.perspective.sceneScaleMode, "normalized");
  assert.equal(normalized.camera.perspective.coordinateSystem, "z-up");
  assert.deepEqual(normalized.selection.selectedPartIds, ["o1.2", "o1.4"]);
  assert.deepEqual(normalized.selection.cadRefs, ["@cad[resources/generated/model#o1.2.f1]"]);
  assert.deepEqual(normalized.assembly.expandedTreeNodeIds, []);
  assert.deepEqual(normalized.assembly.expandedAssemblyPartIds, ["o1.2"]);
  assert.deepEqual(normalized.scene.selectedRenderPartIdByAssemblyPartId, { "o1.2": "mesh:17" });
  assert.equal(normalized.scene.explorerMode, "");
  assert.deepEqual(normalized.view.clipSettings, { axis: "z", plane: 0.5, enabled: true, inverted: true });
  assert.equal(normalized.view.layout, null);
});

test("buildCadViewStateQueryString preserves empty slices in the full view payload", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    cadPath: "resources/generated/model",
    perspective: { position: [1, 2, 3], target: [0, 0, 0], up: [0, 1, 0] }
  });
  const params = new URLSearchParams(buildCadViewStateQueryString(state));
  const parsed = normalizeCadViewStateForApply(buildCadViewStateFromParams(params));

  assert.ok(params.get("view"));
  assert.deepEqual(parsed.selection.selectedReferenceIds, []);
  assert.deepEqual(parsed.selection.selectedPartIds, []);
  assert.deepEqual(parsed.assembly.hiddenPartIds, []);
  assert.equal(parsed.view.clipSettings, null);
});

test("buildCadViewStateQueryString preserves invalid camera as null without dropping other state", () => {
  const state = buildCadViewState({
    createdAt: "2026-05-22T00:00:00.000Z",
    cadPath: "resources/generated/model",
    perspective: { position: [1, 2], target: [0], up: [] },
    selectedPartIds: ["part-1"]
  });
  const params = new URLSearchParams(buildCadViewStateQueryString(state));
  const parsed = normalizeCadViewStateForApply(buildCadViewStateFromParams(params));

  assert.equal(parsed.camera.perspective, null);
  assert.deepEqual(parsed.selection.selectedPartIds, ["part-1"]);
});

test("buildCadViewStateFromParams round-trips camera, selection, and clip", () => {
  const params = new URLSearchParams(
    "v=1,2,3,0,0,0,0,1,0&sp=gear,shaft&sr=face-1,face-2&hp=hidden-1&cp=y,0.3"
  );
  const state = buildCadViewStateFromParams(params, { cadPath: "resources/generated/model" });

  assert.equal(state.schema, CAD_EXPLORER_VIEW_STATE_SCHEMA);
  assert.equal(state.file.cadPath, "resources/generated/model");
  assert.deepEqual(state.camera.perspective.position, [1, 2, 3]);
  assert.deepEqual(state.camera.perspective.target, [0, 0, 0]);
  assert.deepEqual(state.camera.perspective.up, [0, 1, 0]);
  assert.deepEqual(state.selection.selectedPartIds, ["gear", "shaft"]);
  assert.deepEqual(state.selection.selectedReferenceIds, ["face-1", "face-2"]);
  assert.deepEqual(state.assembly.hiddenPartIds, ["hidden-1"]);
  assert.equal(state.view.clipSettings.axis, "y");
  assert.equal(state.view.clipSettings.plane, 0.3);
  assert.equal(state.view.clipSettings.enabled, true);
});

test("buildCadViewStateFromParams handles partial params", () => {
  const params = new URLSearchParams("v=0,0,10,0,0,0,0,0,1");
  const state = buildCadViewStateFromParams(params, { cadPath: "resources/partial" });

  assert.equal(state.file.cadPath, "resources/partial");
  assert.deepEqual(state.camera.perspective.position, [0, 0, 10]);
  assert.deepEqual(state.selection.selectedPartIds, []);
  assert.deepEqual(state.assembly.hiddenPartIds, []);
  assert.equal(state.view.clipSettings, null);
});

test("buildCadViewStateFromParams ignores URLs without view-state params", () => {
  const params = new URLSearchParams("file=generated/model.step");

  assert.equal(buildCadViewStateFromParams(params, { cadPath: "generated/model.step" }), null);
});

test("buildCadViewStateFromParams rejects invalid view payloads", () => {
  assert.throws(
    () => buildCadViewStateFromParams(new URLSearchParams("view=not-base64-json")),
    /Invalid CAD review state URL/
  );

  const unsupported = Buffer.from(JSON.stringify({ schema: "other-schema", version: 1 })).toString("base64url");
  assert.throws(
    () => buildCadViewStateFromParams(new URLSearchParams(`view=${unsupported}&sp=part-a`)),
    /Invalid CAD review state URL/
  );
});

test("buildCadViewStateFromParams rejects malformed camera", () => {
  const params = new URLSearchParams("v=1,2,3&sp=part-a");
  const state = buildCadViewStateFromParams(params);

  assert.equal(state.camera.perspective, null);
  assert.deepEqual(state.selection.selectedPartIds, ["part-a"]);
});

test("hasCadViewStateParams detects view state in URL params", () => {
  assert.equal(hasCadViewStateParams(new URLSearchParams("v=1,2,3,0,0,0,0,0,1")), true);
  assert.equal(hasCadViewStateParams(new URLSearchParams("sp=part-a")), true);
  assert.equal(hasCadViewStateParams(new URLSearchParams("hp=hidden-1")), true);
  assert.equal(hasCadViewStateParams(new URLSearchParams("cp=z,0.5")), true);
  assert.equal(hasCadViewStateParams(new URLSearchParams("sr=face-1")), true);
  assert.equal(hasCadViewStateParams(new URLSearchParams("file=model.step")), false);
  assert.equal(hasCadViewStateParams(new URLSearchParams("")), false);
});

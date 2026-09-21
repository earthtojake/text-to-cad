import assert from "node:assert/strict";
import test from "node:test";

import { click, get, query, render, renderHook, text } from "../../../../../scripts/reactHarness.mjs";
import { effectiveSourceAppearance } from "../../../workbench/sourceMaterialSession.js";
import { buildMaterialsSettingsTab } from "../MaterialsSettingsTab.js";
// The tab descriptor wraps the panel in Render's lazy boundary; the behaviour
// under test is the panel's, so these mount the panel module directly.
import MaterialsSettingsContent from "../MaterialsSettingsContent.js";
import { useSourceMaterialSession } from "./useSourceMaterialSession.js";

const appearance = {
  materials: { steel: { name: "Steel", baseColor: "#778899" } },
  assignments: { palm: "steel" }
};
const meshData = { appearance, parts: [{ occurrenceId: "palm", label: "Palm" }] };
const hand = { file: "hand.step", documentHash: "hand-1" };
const arm = { file: "arm.step", documentHash: "arm-1" };

function startSession(entry = hand) {
  return renderHook(
    (props) => useSourceMaterialSession(props.entry, meshData, {
      appearance,
      fileSheetKind: "step",
      renderEnabled: true
    }),
    { entry }
  );
}

// The Materials tab as the workspace mounts it — and, crucially, as it
// unmounts it: showing Studio takes the panel away entirely.
function showTab(session) {
  const parts = session.result.withViewerSelection([]);
  // Built as well as rendered: the descriptor decides whether the tab exists at
  // all, and the panel below has to be the thing that descriptor points at.
  assert.equal(buildMaterialsSettingsTab({ enabled: session.result.enabled })?.title, "Materials");
  const props = {
    appearance,
    overlay: session.result.overlay,
    undo: session.result.undo,
    targets: session.result.targets,
    scope: session.result.scope,
    enabled: session.result.enabled,
    selectedPartIds: parts.selectedIds,
    onSelectParts: parts.select,
    onOverlayChange: session.result.change,
    onUndo: session.result.undoLast,
    onReset: session.result.reset
  };
  return render(MaterialsSettingsContent, props);
}

function press(view, label) {
  click(get(view.tree, (node) => typeof node.props.onClick === "function" && text(node).trim() === label));
}

// One part row, matched on the label it leads with: the row also names the
// material it currently carries.
function pressPart(view, label) {
  click(get(view.tree, (node) => typeof node.props.onClick === "function" && text(node).startsWith(label)));
}

test("undo survives the Materials tab being taken away and put back", () => {
  const session = startSession();
  let tab = showTab(session);
  pressPart(tab, "Palm");
  tab = showTab(session);
  press(tab, "Rubber");
  assert.notEqual(session.result.overlay, null);

  // Studio is shown: the panel unmounts with everything it was holding.
  tab.unmount();
  tab = showTab(session);

  assert.notEqual(query(tab.tree, "Undo"), null, "the change is still the one on screen, so it is still undoable");
  press(tab, "Undo");
  assert.equal(session.result.overlay, null);
  assert.equal(query(showTab(session).tree, "Undo"), null, "and one step of history is all there is");
});

test("undo belongs to the model it was recorded against", () => {
  const session = startSession();
  pressPart(showTab(session), "Palm");
  press(showTab(session), "Rubber");
  assert.notEqual(session.result.undo, null);

  session.update({ entry: arm });
  assert.equal(session.result.undo, null, "another model's history is not this model's");
  assert.equal(session.result.overlay, null);

  session.update({ entry: hand });
  assert.notEqual(session.result.undo, null, "coming back finds the edit and its history intact");
  assert.equal(effectiveSourceAppearance(appearance, session.result.overlay).assignments.palm, "rubber");
});

test("the stored slice round-trips through the session and is dropped with the directory", () => {
  const session = startSession();
  pressPart(showTab(session), "Palm");
  press(showTab(session), "Rubber");
  const slice = session.result.snapshotSlice(hand);
  assert.deepEqual(slice, session.result.overlay);
  assert.equal(session.result.snapshotSlice(arm), null);

  session.result.clearAll();
  assert.equal(session.result.overlay, null);
  assert.equal(session.result.undo, null);

  session.result.restoreSlice("hand.step", hand, slice);
  assert.deepEqual(session.result.overlay, slice);
  assert.equal(session.result.undo, null, "a restored session is not an edit to take back");

  session.result.restoreSlice("hand.step", hand, null);
  assert.equal(session.result.overlay, null, "no slice means the model has no local edits");
});

test("an overlay is only worn by the appearance it was authored against", () => {
  const session = startSession();
  pressPart(showTab(session), "Palm");
  press(showTab(session), "Rubber");
  assert.notEqual(session.result.overlay, null);

  session.update({ entry: { ...hand, documentHash: "hand-2" } });
  assert.equal(session.result.overlay, null, "the model was rebuilt, so its assignments no longer describe it");
});

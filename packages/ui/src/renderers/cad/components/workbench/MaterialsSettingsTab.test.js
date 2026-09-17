import assert from "node:assert/strict";
import test from "node:test";

import { click, get, query, render, renderHook, text } from "../../../../../scripts/reactHarness.mjs";
import { effectiveSourceAppearance } from "../../workbench/sourceMaterialSession.js";
import { buildMaterialsSettingsTab } from "./MaterialsSettingsTab.js";
// The panel is a lazy chunk behind the tab descriptor; these render the panel
// itself, which is what has the behaviour, and assert the descriptor separately.
import MaterialsSettingsContent from "./MaterialsSettingsContent.js";
import { useSourceMaterialSession } from "./hooks/useSourceMaterialSession.js";

// Steel is shared by two of the three parts, which is what makes the shared
// gating reachable; the pad is the unshared control.
const appearance = {
  materials: {
    steel: { name: "Steel", baseColor: "#778899", metalness: 0.8 },
    rubber: { name: "Rubber", roughness: 0.9 }
  },
  assignments: { palm: "steel", finger: "steel", pad: "rubber" }
};
const meshData = {
  appearance,
  parts: [
    { occurrenceId: "palm", label: "Palm", sourceColor: "#778899" },
    { occurrenceId: "finger", label: "Finger", sourceColor: "#778899" },
    { occurrenceId: "pad", label: "Pad", sourceColor: "#222222" }
  ]
};
const entry = { file: "hand.step", documentHash: "hand-1" };

// The panel is driven by the workspace's real material session, so what these
// assert is the pair as the app wires it: a click in the panel writes through
// the hook, and the panel is re-rendered from what the hook then holds.
function openPanel() {
  const session = renderHook(() => useSourceMaterialSession(entry, meshData, {
    appearance,
    fileSheetKind: "step",
    renderEnabled: true
  }));
  let view = null;
  const paint = () => {
    const parts = session.result.withViewerSelection([]);
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
    if (view) view.update(props);
    else view = render(MaterialsSettingsContent, props);
    return view.tree;
  };
  const panel = {
    session,
    tree: paint(),
    // Matched on what the control says, among the things that can be clicked:
    // several rows wrap their button in a div carrying the same text.
    control(match) {
      const wanted = typeof match === "function" ? match : (node) => text(node).trim() === match;
      return get(panel.tree, (node) => typeof node.props.onClick === "function" && wanted(node));
    },
    // A settings row is named by its `label` prop, not by any text of its own.
    field(label) {
      return query(panel.tree, (node) => node.props.label === label);
    },
    press(match) {
      click(panel.control(match));
      panel.tree = paint();
    },
    // Part rows carry their material name after the label, so they are matched
    // on the label they start with rather than on their whole text.
    pressPart(label) {
      panel.press((node) => text(node).startsWith(label));
    },
    close() {
      view.unmount();
      view = null;
    },
    reopen() {
      panel.tree = paint();
    },
    assignments() {
      return effectiveSourceAppearance(appearance, panel.session.result.overlay).assignments;
    },
    has(match) {
      return Boolean(query(panel.tree, match));
    }
  };
  return panel;
}

test("clicking a preset applies it to the selection at once", () => {
  const panel = openPanel();
  panel.pressPart("Pad");
  assert.equal(panel.has("Undo"), false, "nothing has changed yet");
  panel.press("Matte plastic");

  const assignments = panel.assignments();
  assert.notEqual(assignments.pad, "rubber", "the preset creates and assigns its own material");
  assert.equal(assignments.palm, "steel", "parts outside the selection keep theirs");
  const applied = effectiveSourceAppearance(appearance, panel.session.result.overlay).materials[assignments.pad];
  assert.equal(applied.roughness, 0.75);
  assert.equal(applied.name, "Matte plastic");
});

test("Undo takes back the last change once and then goes away", () => {
  const panel = openPanel();
  panel.pressPart("Pad");
  panel.press("Matte plastic");
  assert.equal(panel.has("Undo"), true);

  panel.press("Undo");
  assert.equal(panel.assignments().pad, "rubber", "the authored assignment is back");
  assert.equal(panel.has("Undo"), false, "one step of history, already spent");
  assert.equal(panel.session.result.overlay, null);
});

test("Reset authored drops every local edit and then has nothing to do", () => {
  const panel = openPanel();
  assert.equal(panel.control("Reset authored").props.disabled, true, "nothing is authored yet");

  panel.pressPart("Pad");
  panel.press("Matte plastic");
  panel.pressPart("Palm");
  panel.press("Rubber");
  assert.equal(panel.control("Reset authored").props.disabled, false);

  panel.press("Reset authored");
  assert.deepEqual(panel.assignments(), appearance.assignments);
  assert.equal(panel.session.result.overlay, null);
  assert.equal(panel.control("Reset authored").props.disabled, true);
});

test("a material shared outside the selection is not edited until it is made unique", () => {
  const panel = openPanel();
  panel.pressPart("Palm");
  panel.press("Advanced settings…");
  assert.equal(
    panel.has((node) => text(node).includes("Shared by 2 parts")),
    true,
    "steel is also the finger's material"
  );
  assert.equal(panel.field("Base color"), null, "the shared material's channels stay locked");

  panel.press("Make unique for selection");
  const assignments = panel.assignments();
  assert.notEqual(assignments.palm, "steel", "the selection moves to a copy");
  assert.equal(assignments.finger, "steel", "the part left behind keeps the original");

  panel.press("Advanced settings…");
  assert.equal(panel.has((node) => text(node).includes("Shared by")), false);
  assert.notEqual(panel.field("Base color"), null, "the copy is the selection's alone, so it is editable");
});

test("a material's menu selects every part using it", () => {
  const panel = openPanel();
  panel.pressPart("Pad");
  assert.equal(text(get(panel.tree, (node) => text(node).startsWith("Selected: Pad"))).includes("Rubber"), true);

  panel.press("Select parts using Steel");
  assert.deepEqual(panel.session.result.withViewerSelection([]).selectedIds, ["palm", "finger"]);
  assert.equal(panel.has((node) => text(node).startsWith("Selected: 2 parts")), true);
});

test("the panel is not built at all for a file the session does not cover", () => {
  assert.equal(buildMaterialsSettingsTab({ enabled: false, appearance }), null);
  assert.equal(buildMaterialsSettingsTab({ enabled: true, appearance, targets: [] })?.title, "Materials");
});

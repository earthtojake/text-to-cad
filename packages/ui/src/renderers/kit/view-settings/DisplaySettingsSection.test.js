import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { EDGELESS_VIEW_FEATURES, resolveViewSettings, viewSettingsAreCustom } from "@text-to-cad/core/common/viewSettings.js";
import { elements, render } from "../../../../scripts/reactHarness.mjs";
import { DISPLAY_MODE_OPTIONS } from "./DisplayModeOptions.js";
import { DisplaySettingsSection } from "./DisplaySettingsSection.js";
import { ExplodeControls } from "../../step/components/workbench/ModelViewControls.js";
import { createViewSettingsStore } from "./viewSettingsStore.js";

function panel(input = {}) {
  const store = createViewSettingsStore(input);
  panel.store = store;
  const { display: settings, scene } = store.getSnapshot();
  const result = render(DisplaySettingsSection, {
    viewSettings: settings, resolvedView: scene.view,
    onViewSettingsPatch: store.patch, onGroupEnabledChange: store.setEnabled,
  });
  return { ...result, settings: () => store.getSnapshot().display };
}
const sections = tree => elements(tree).find(node => node.type?.name === "DisplaySections")?.props.sections.filter(Boolean) ?? [];
const controls = tree => sections(tree).length ? sections(tree).flatMap(section => elements(section.content)) : elements(tree);
const labelled = (tree, label) => controls(tree).find(node => node.props.label === label);

test("View has the same feature groups for every preset, with Render second", () => {
  assert.deepEqual(DISPLAY_MODE_OPTIONS.map(option => option.value), ["solid", "render", "xray", "hidden-line", "wireframe", "grid"]);
  for (const mode of DISPLAY_MODE_OPTIONS.map(option => option.value)) {
    const view = panel({ mode });
    assert.deepEqual(sections(view.tree).filter(section => section.onEnabledChange).map(section => section.title),
      ["Edges", "Grid / Axes", "Lighting", "Background", "Floor"]);
    // Projection shares Display with Mode.
    assert.equal(labelled(view.tree, "Projection").props.value, resolveViewSettings({ mode }).camera.projection);
    assert.equal(labelled(view.tree, "Lens"), undefined);
    assert.deepEqual(sections(view.tree).filter(section => !section.onEnabledChange).map(section => section.title),
      ["Display", "Surfaces"]);
    assert.deepEqual(labelled(view.tree, "Surface style").props.options.map(option => option.value), ["shaded", "flat", "hidden", "off"]);
    assert.equal(labelled(view.tree, "Surface style").props.value, resolveViewSettings({ mode }).surfaces.style);
    view.unmount();
  }
});

test("group edits are sparse and disabling discards only that group's overrides", () => {
  const view = panel({ mode: "render", floor: { color: "#abcdef", opacity: 0.8 }, clip: { enabled: true, offset: 0.3 } });
  labelled(view.tree, "Floor color").props.onOpacityChange(0.4);
  assert.deepEqual(view.settings().floor, { color: "#abcdef", opacity: 0.4 });
  const floor = sections(view.tree).find(section => section.title === "Floor");
  floor.onEnabledChange(false);
  assert.deepEqual(view.settings().floor, { enabled: false });
  assert.deepEqual(view.settings().clip, { enabled: true, offset: 0.3 });
  floor.onEnabledChange(true);
  assert.deepEqual(resolveViewSettings(view.settings()).floor, resolveViewSettings({ mode: "render" }).floor);
  view.unmount();
});

test("Floor finish sits right of Floor position on one two-column row, Matte until Glossy is chosen", () => {
  const view = panel({ mode: "render" });
  const floor = sections(view.tree).find(section => section.title === "Floor");
  const row = elements(floor.content).find(node => node.type?.name === "FileSheetFieldGrid"
    && elements(node.props.children).some(child => child.props?.label === "Floor finish"));
  assert.equal(row.props.columns ?? 2, 2);
  const selects = elements(row.props.children).filter(node => node.props?.label);
  assert.deepEqual(selects.map(select => select.props.label), ["Floor position", "Floor finish"]);
  const finish = selects[1];
  assert.equal(finish.props.value, "matte");
  assert.deepEqual(finish.props.options.map(option => [option.value, option.label]), [["matte", "Matte"], ["glossy", "Glossy"]]);
  finish.props.onValueChange("glossy");
  assert.deepEqual(view.settings().floor, { finish: "glossy" });
  assert.equal(viewSettingsAreCustom(view.settings()), true);
  view.unmount();
});

test("Render's Floor position is Lowest point until Model origin is chosen, which is Custom", () => {
  const view = panel({ mode: "render" });
  const floor = sections(view.tree).find(section => section.title === "Floor");
  const position = elements(floor.content).find(node => node.props?.label === "Floor position");
  assert.equal(position.props.value, "lowest");
  assert.deepEqual(position.props.options.map(option => [option.value, option.label]), [["origin", "Model origin"], ["lowest", "Lowest point"]]);
  assert.equal(viewSettingsAreCustom(view.settings()), false);
  position.props.onValueChange("origin");
  assert.deepEqual(view.settings().floor, { placement: "origin" });
  assert.equal(viewSettingsAreCustom(view.settings()), true);
  view.unmount();
});

test("projection and tools update independent groups; only the view change is Custom", () => {
  const view = panel({ mode: "solid" });
  // Explode is a STEP tool with its own panel, and writes the same store.
  const explode = render(ExplodeControls, { viewSettings: view.settings(), onViewSettingsPatch: panel.store.patch });
  elements(explode.tree).find(node => node.props.thumbProps?.["aria-label"] === "Explode amount").props.onValueChange([45]);
  explode.unmount();
  assert.equal(viewSettingsAreCustom(view.settings()), false);
  assert.deepEqual(view.settings().exploded, { amount: 0.45, enabled: true });
  // What the viewport's projection toggle writes (useRendererShell's setProjection).
  panel.store.patch({ camera: { enabled: true, projection: "perspective" } });
  assert.equal(viewSettingsAreCustom(view.settings()), true);
  assert.equal(view.settings().camera.projection, "perspective");
  view.unmount();
});

test("surface controls remain usable when restoring a formerly disabled section", () => {
  const view = panel({ surfaces: { enabled: false } });
  labelled(view.tree, "Surface style").props.onValueChange("flat");
  assert.equal(resolveViewSettings(view.settings()).surfaces.style, "flat");
  assert.equal(view.settings().surfaces.enabled, true);
  view.unmount();
});

test("a file that is not a CAD model has no Edges section and only the presets not made of edges", () => {
  // A mesh opened while the saved preset is Wireframe: shown as Solid, never as its tessellation.
  const store = createViewSettingsStore({ mode: "wireframe", edges: { enabled: true, visibility: "all" } }, { features: EDGELESS_VIEW_FEATURES });
  const { display, scene } = store.getSnapshot();
  assert.equal(scene.view.edges.enabled, false);
  assert.equal(display.mode, "wireframe", "the saved preset is not rewritten");
  const view = render(DisplaySettingsSection, { features: EDGELESS_VIEW_FEATURES, viewSettings: display, resolvedView: scene.view,
    onViewSettingsPatch: store.patch, onGroupEnabledChange: store.setEnabled });
  assert.deepEqual(sections(view.tree).filter(section => section.onEnabledChange).map(section => section.title),
    ["Grid / Axes", "Lighting", "Background", "Floor"]);
  assert.equal(elements(view.tree).some(node => node.type?.name === "ClipSettings"), false);
  const mode = labelled(view.tree, "Mode");
  assert.deepEqual(mode.props.options.map(option => option.value), ["solid", "render", "grid"]);
  // Hidden and Off leave a STEP model its edges; here they would leave nothing.
  assert.deepEqual(labelled(view.tree, "Surface style").props.options.map(option => option.value), ["shaded", "flat"]);
  assert.equal(elements(view.tree).some(node => node.props?.label === "Edge visibility" || node.props?.label === "Edge color"), false);
  view.unmount();
  // The capability arrives separately from the appearance, and neither configuration drops the other.
  const later = createViewSettingsStore({ mode: "xray" }, { appearance: "dark" });
  assert.equal(later.getSnapshot().scene.view.edges.enabled, true);
  later.configure({ features: EDGELESS_VIEW_FEATURES });
  assert.equal(later.getSnapshot().scene.view.edges.enabled, false);
  assert.equal(later.getSnapshot().scene.view.appearance, "dark");
  later.configure({ appearance: "light" });
  assert.equal(later.getSnapshot().scene.view.edges.enabled, false);
});

test("Display holds the file's view alone, its first heading ending in the X its dropdown hands it; the host's settings are Settings', not Display's", () => {
  const view = panel();
  assert.deepEqual(sections(view.tree).map(section => section.title), ["Display", "Surfaces", "Edges", "Grid / Axes", "Lighting", "Background", "Floor"]);
  const named = tree => elements(sections(tree)[0].headingAction).map(node => node.props?.["aria-label"]).filter(Boolean);
  // Drawn alone, its first heading has its Reset and nothing else.
  assert.deepEqual(named(view.tree), ["Reset"]);
  view.unmount();
  // In its dropdown, Reset then the dropdown's X (`close`: `DisplayPopoverClose`): the dropdown has no heading of its own.
  const store = createViewSettingsStore({});
  const { display: settings, scene } = store.getSnapshot();
  const close = createElement("button", { "aria-label": "Close display settings" });
  const dropdown = render(DisplaySettingsSection, { viewSettings: settings, resolvedView: scene.view,
    onViewSettingsPatch: store.patch, onGroupEnabledChange: store.setEnabled, close });
  assert.deepEqual(named(dropdown.tree), ["Reset", "Close display settings"]);
  dropdown.unmount();
});

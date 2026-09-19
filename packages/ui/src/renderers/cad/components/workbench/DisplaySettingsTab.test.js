import assert from "node:assert/strict";
import test from "node:test";
import { CAMERA_PROJECTION } from "@hardcore/core/common/camera.js";
import { CAD_DISPLAY_MODE, DEFAULT_DISPLAY_SETTINGS } from "@hardcore/core/lib/displaySettings.js";
import { elements, render } from "../../../../../scripts/reactHarness.mjs";
import { DISPLAY_MODE_OPTIONS } from "../viewer/DisplayModeOptions.js";
import {
  buildDisplaySettingsTab,
  DisplaySettingsSection
} from "./DisplaySettingsTab.js";
import RenderSettingsContent from "./RenderSettingsContent.js";
import { RenderSettingsPanel } from "./RenderSettingsTab.js";

const SCENE = Object.freeze({
  camera: Object.freeze({ focalLength: 50 }),
  render: Object.freeze({
    payload: Object.freeze({}),
    configuration: Object.freeze({
      quality: "final",
      exposure: 0,
      lighting: Object.freeze({ rotation: 0, size: 1, fill: 0.5 }),
      backdrop: Object.freeze({
        color: "#ffffff",
        transparent: false,
        ground: true,
        groundPlacement: "lowest"
      })
    })
  })
});

function sectionProps(extra = {}) {
  return {
    displaySettings: DEFAULT_DISPLAY_SETTINGS,
    updateDisplaySettings() {},
    scene: SCENE,
    ...extra
  };
}

function findByLabel(tree, label) {
  return elements(tree).find((node) => node.props.label === label);
}

test("View is the single settings tab and Render is its second mode", () => {
  const tab = buildDisplaySettingsTab(sectionProps());
  assert.equal(tab.id, "view");
  assert.equal(tab.title, "View");
  assert.equal(DISPLAY_MODE_OPTIONS[1].value, CAD_DISPLAY_MODE.RENDER);
  assert.equal(DISPLAY_MODE_OPTIONS[1].label, "Render");
});

test("ordinary controls share View while Clip and Explode stay flat sections", () => {
  const view = render(DisplaySettingsSection, sectionProps());
  assert.deepEqual(
    elements(view.tree)
      .filter((node) => node.type?.name === "FileSheetSubsection")
      .map((node) => node.props.title),
    ["View", "Explode"]
  );
  const clip = elements(view.tree).find((node) => node.type?.name === "ClipSettings");
  assert.ok(clip);
  const renderedClip = render(clip.type, clip.props);
  assert.equal(elements(renderedClip.tree).find((node) => node.type?.name === "FileSheetSubsection")?.props.title, "Clip");
  for (const label of ["Mode", "Projection", "Parts", "Grid", "Origin axes", "Silhouette"]) {
    assert.ok(findByLabel(view.tree, label), label);
  }
  assert.equal(elements(view.tree).some((node) => node.type === RenderSettingsPanel), false);
  renderedClip.unmount();
  view.unmount();
});

test("mode transitions are delegated without overwriting inspection settings", () => {
  const modes = [];
  let displayWrites = 0;
  const view = render(DisplaySettingsSection, sectionProps({
    rendering: true,
    onModeChange: (mode) => modes.push(mode),
    updateDisplaySettings: () => { displayWrites += 1; }
  }));
  const mode = findByLabel(view.tree, "Mode");
  assert.equal(mode.props.value, CAD_DISPLAY_MODE.RENDER);
  mode.props.onValueChange(CAD_DISPLAY_MODE.SHADED);
  assert.deepEqual(modes, [CAD_DISPLAY_MODE.SHADED]);
  assert.equal(displayWrites, 0);
  assert.equal(elements(view.tree).some((node) => node.type === RenderSettingsPanel), true);
  view.unmount();
});

test("projection is always available and perspective exposes the shared camera lens", () => {
  const payloadWrites = [];
  const orthographic = render(DisplaySettingsSection, sectionProps({
    rendering: true,
    projection: CAMERA_PROJECTION.ORTHOGRAPHIC
  }));
  assert.ok(findByLabel(orthographic.tree, "Projection"));
  assert.equal(findByLabel(orthographic.tree, "Lens"), undefined);
  orthographic.unmount();

  const perspective = render(DisplaySettingsSection, sectionProps({
    projection: CAMERA_PROJECTION.PERSPECTIVE,
    onPayloadValueChange: (path, value) => payloadWrites.push([path, value])
  }));
  const lens = findByLabel(perspective.tree, "Lens");
  assert.ok(lens);
  lens.props.onChange(80);
  assert.deepEqual(payloadWrites, [[['camera', 'focalLength'], 80]]);
  perspective.unmount();
});

test("perspective Lens reports the observed camera focal length without mutating scene input", () => {
  const scene = {
    ...SCENE,
    camera: {}
  };
  const payloadWrites = [];
  const perspective = render(DisplaySettingsSection, sectionProps({
    scene,
    observedFocalLength: 67,
    projection: CAMERA_PROJECTION.PERSPECTIVE,
    onPayloadValueChange: (path, value) => payloadWrites.push([path, value])
  }));
  const lens = findByLabel(perspective.tree, "Lens");
  assert.equal(lens.props.value, 67);
  lens.props.onChange(85);
  assert.deepEqual(payloadWrites, [[["camera", "focalLength"], 85]]);
  assert.deepEqual(scene.camera, {});
  perspective.unmount();
});

test("render-only controls form one Render section and default Quality to Preview", () => {
  const payloadWrites = [];
  const resets = [];
  const content = render(RenderSettingsContent, {
    scene: SCENE,
    onPayloadValueChange: (path, value) => payloadWrites.push([path, value]),
    onReset: () => resets.push(true)
  });
  const subsections = elements(content.tree)
    .filter((node) => node.type?.name === "FileSheetSubsection");
  assert.deepEqual(subsections.map((node) => node.props.title), ["Render"]);
  assert.equal(findByLabel(content.tree, "Quality").props.value, "preview");
  for (const label of ["Exposure", "Rotation", "Softbox size", "Fill ratio", "Transparent", "Backdrop", "Ground", "Ground position"]) {
    assert.ok(findByLabel(content.tree, label), label);
  }
  findByLabel(content.tree, "Exposure").props.onChange(1.2);
  assert.deepEqual(payloadWrites, [[['exposure'], 1.2]]);
  const reset = elements(content.tree).find((node) => node.props.onClick && node.props.children?.some?.((child) => child === "Reset"));
  assert.ok(reset);
  reset.props.onClick();
  assert.equal(resets.length, 1);
  content.unmount();
});

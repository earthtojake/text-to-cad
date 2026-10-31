import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_TOOL_STACK, FILE_SIDEBAR_MIN_WIDTH, TOOL_PANEL_MIN_HEIGHT, TOOL_PANEL_WIDTH,
  clampToolPanelHeight, clampToolPanelWidth, fileSidebarSizeId, normalizeToolStack, toolPanelDefaultHeight
} from "./toolStackLayout.js";

test("the layout is the sizes a person set, by panel, and the folded panels — nothing else, whatever a store hands back", () => {
  assert.deepEqual(DEFAULT_TOOL_STACK, { panels: {}, collapsed: {} });
  for (const value of [null, undefined, "240", Number.NaN, {}, [], { width: 240, heights: { tree: 300 } }]) {
    assert.deepEqual(normalizeToolStack(value), { panels: {}, collapsed: {} }, `${JSON.stringify(value)}: an older record's stack width and caps are nobody's`);
  }
  assert.deepEqual(normalizeToolStack({ panels: { tree: { width: 240.4, height: 300 }, position: { height: 12, width: 12 }, reference: { width: 0 }, "Not an id": { width: 200 }, clip: "wide", sdf: {} },
    collapsed: { tree: true, sdf: false, "Not an id": true, clip: "yes" }, closed: { tree: true } }),
  { panels: { tree: { width: 240, height: 300 }, position: { width: TOOL_PANEL_WIDTH, height: TOOL_PANEL_MIN_HEIGHT } }, collapsed: { tree: true, sdf: false } },
  "a size is rounded and bounded, a panel with neither is absent, only booleans fold, and an older record's closed panels are nobody's");
  assert.deepEqual(normalizeToolStack({ panels: { tree: { width: 99999 } } }).panels.tree, { width: 4000 }, "a stored size is bounded; the viewer bounds what is drawn");
});

test("each file sidebar section's panel keeps a size of its own, as narrow as the sidebar may be", () => {
  assert.deepEqual([fileSidebarSizeId("tree"), fileSidebarSizeId(null)], ["sidebar:tree", "sidebar"]);
  assert.deepEqual(normalizeToolStack({ panels: { "sidebar:tree": { width: 12, height: 300 }, "sidebar:position": { width: 240 }, "sidebar:": { width: 200 }, "sidebar:a:b": { width: 200 } } }).panels,
    { "sidebar:tree": { width: FILE_SIDEBAR_MIN_WIDTH, height: 300 }, "sidebar:position": { width: 240 } });
});

test("every panel is a six-tool strip wide; a resizable one is only ever wider, up to half the viewer", () => {
  assert.equal(TOOL_PANEL_WIDTH, 6 * 24 + 5 * 2 + 2 * 4 + 2 * 1);
  assert.equal(TOOL_PANEL_WIDTH, 164);
  assert.equal(clampToolPanelWidth(300, 1280), 300);
  assert.equal(clampToolPanelWidth(12, 1280), TOOL_PANEL_WIDTH, "never narrower than every panel's width");
  assert.equal(clampToolPanelWidth(Infinity, 1280), 640, "never over half the viewer");
  assert.equal(clampToolPanelWidth(Infinity, 200), TOOL_PANEL_WIDTH, "a viewer narrower than twice the width: the width");
  assert.equal(clampToolPanelWidth(Number.NaN, 0), TOOL_PANEL_WIDTH, "unmeasured: the width");
});

test("a panel's cap is bounded by the minimum and by the stack", () => {
  assert.equal(clampToolPanelHeight(300, 600), 300);
  assert.equal(clampToolPanelHeight(3, 600), TOOL_PANEL_MIN_HEIGHT);
  assert.equal(clampToolPanelHeight(Infinity, 600), 600);
  assert.equal(clampToolPanelHeight(300, 0), TOOL_PANEL_MIN_HEIGHT, "an unmeasured stack allows the minimum");
});

test("every resizable panel opens capped at the whole stack, on desktop and phone alike: as tall as its content, up to the room there is", () => {
  assert.equal(toolPanelDefaultHeight(600), 600);
  assert.equal(toolPanelDefaultHeight(600.4), 600);
  assert.equal(toolPanelDefaultHeight(0), null, "an unmeasured stack sets no cap yet");
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_TOOL_STACK, TOOL_PANEL_MIN_HEIGHT, TOOL_PANEL_REFERENCE_HEIGHT, TOOL_PANEL_WIDTH,
  clampToolPanelHeight, clampToolPanelWidth, normalizeToolStack, toolPanelDefaultHeight
} from "./toolStackLayout.js";

test("the layout is the sizes a person set, by panel, and the folded panels — nothing else, whatever a store hands back", () => {
  assert.deepEqual(DEFAULT_TOOL_STACK, { panels: {}, collapsed: {} });
  for (const value of [null, undefined, "240", Number.NaN, {}, [], { width: 240, heights: { tree: 300 } }]) {
    assert.deepEqual(normalizeToolStack(value), { panels: {}, collapsed: {} }, `${JSON.stringify(value)}: an older record's stack width and caps are nobody's`);
  }
  assert.deepEqual(normalizeToolStack({ panels: { tree: { width: 240.4, height: 300 }, position: { height: 12, width: 12 }, reference: { width: 0 }, "Not an id": { width: 200 }, clip: "wide", sdf: {} },
    collapsed: { tree: true, sdf: false, "Not an id": true, clip: "yes" } }),
  { panels: { tree: { width: 240, height: 300 }, position: { width: TOOL_PANEL_WIDTH, height: TOOL_PANEL_MIN_HEIGHT } }, collapsed: { tree: true, sdf: false } },
  "a size is rounded and bounded, a panel with neither is absent, and only booleans fold");
  assert.deepEqual(normalizeToolStack({ panels: { tree: { width: 99999 } } }).panels.tree, { width: 4000 }, "a stored size is bounded; the viewer bounds what is drawn");
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

test("a tree or Position opens capped at half the stack on desktop and the whole of it on mobile; anything else at the Reference's height", () => {
  assert.equal(toolPanelDefaultHeight("tree", 600), 300);
  assert.equal(toolPanelDefaultHeight("position", 601), 301);
  assert.equal(toolPanelDefaultHeight("tree", 600, true), 600);
  assert.equal(toolPanelDefaultHeight("position", 600, true), 600);
  assert.equal(toolPanelDefaultHeight("reference", 600), TOOL_PANEL_REFERENCE_HEIGHT);
  assert.equal(toolPanelDefaultHeight("tree", 0), TOOL_PANEL_REFERENCE_HEIGHT, "an unmeasured stack falls back to a height");
});

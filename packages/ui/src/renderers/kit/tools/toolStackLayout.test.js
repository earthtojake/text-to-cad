import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_TOOL_STACK, TOOL_PANEL_MIN_HEIGHT, TOOL_PANEL_WIDTH, TOOL_STRIP_HEIGHT,
  clampToolPanelHeight, clampToolPanelWidth, normalizeToolStack, toolPanelClosed, toolPanelDefaultHeight, toolStackHidden
} from "./toolStackLayout.js";

test("the layout is the sizes a person set, by panel, the folded panels and the closed ones — nothing else, whatever a store hands back", () => {
  assert.deepEqual(DEFAULT_TOOL_STACK, { panels: {}, collapsed: {}, closed: {} });
  for (const value of [null, undefined, "240", Number.NaN, {}, [], { width: 240, heights: { tree: 300 } }]) {
    assert.deepEqual(normalizeToolStack(value), { panels: {}, collapsed: {}, closed: {} }, `${JSON.stringify(value)}: an older record's stack width and caps are nobody's`);
  }
  assert.deepEqual(normalizeToolStack({ panels: { tree: { width: 240.4, height: 300 }, position: { height: 12, width: 12 }, reference: { width: 0 }, "Not an id": { width: 200 }, clip: "wide", sdf: {} },
    collapsed: { tree: true, sdf: false, "Not an id": true, clip: "yes" }, closed: { tree: true, links: false, "Not an id": true, sdf: 1 } }),
  { panels: { tree: { width: 240, height: 300 }, position: { width: TOOL_PANEL_WIDTH, height: TOOL_PANEL_MIN_HEIGHT } }, collapsed: { tree: true, sdf: false }, closed: { tree: true, links: false } },
  "a size is rounded and bounded, a panel with neither is absent, and only booleans fold or close");
  assert.deepEqual(normalizeToolStack({ panels: { tree: { width: 99999 } } }).panels.tree, { width: 4000 }, "a stored size is bounded; the viewer bounds what is drawn");
  // Whether the column is hidden is there once the person has chosen, and only as a boolean.
  assert.deepEqual(normalizeToolStack({ hidden: true }), { panels: {}, collapsed: {}, closed: {}, hidden: true });
  assert.deepEqual(normalizeToolStack({ hidden: false, closed: { tree: true } }), { panels: {}, collapsed: {}, closed: { tree: true }, hidden: false });
  for (const hidden of ["true", 1, null, undefined]) assert.equal("hidden" in normalizeToolStack({ hidden }), false, `${JSON.stringify(hidden)} is no choice`);
});

test("the column is hidden as the person left it, their choice holding in every file, and otherwise as it starts: hidden on a phone, shown elsewhere", () => {
  assert.equal(toolStackHidden(DEFAULT_TOOL_STACK), false, "shown on a desktop");
  assert.equal(toolStackHidden(DEFAULT_TOOL_STACK, { mobile: true }), true, "and hidden on a phone");
  assert.equal(toolStackHidden({ hidden: false }, { mobile: true }), false, "shown by the person, it stays shown, on a phone too");
  assert.equal(toolStackHidden({ hidden: true }), true, "hidden by the person, it stays hidden, on a desktop too");
  assert.equal(toolStackHidden(null, { mobile: true }), true);
  assert.equal(toolStackHidden(undefined), false);
});

test("a closable panel is closed as the person left it, their choice holding in every file, and otherwise as it starts: closed on a phone, open elsewhere", () => {
  assert.equal(toolPanelClosed(DEFAULT_TOOL_STACK, "tree"), false, "a tree starts open on a desktop");
  assert.equal(toolPanelClosed(DEFAULT_TOOL_STACK, "tree", { mobile: true }), true, "and closed on a phone");
  assert.equal(toolPanelClosed({ closed: { tree: false } }, "tree", { mobile: true }), false, "opened, it stays open, on a phone too");
  assert.equal(toolPanelClosed({ closed: { tree: true } }, "tree"), true, "closed, it stays closed");
  assert.equal(toolPanelClosed(null, "tree"), false);
});

test("every panel is a six-tool strip wide; a resizable one is only ever wider, up to half the viewer", () => {
  assert.equal(TOOL_PANEL_WIDTH, 6 * 24 + 5 * 2 + 2 * 4 + 2 * 1);
  assert.equal(TOOL_PANEL_WIDTH, 164);
  assert.equal(TOOL_STRIP_HEIGHT, 24 + 2 * 4 + 2 * 1, "the strip is one button tall, in its padding and border: the toggle's square");
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

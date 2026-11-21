import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_PANEL_WIDTH, MAX_PANEL_WIDTH, MIN_MODEL_WIDTH, clampPanelWidth, sidebarCollapsed, sidebarLayout, toggleSidebar } from "./sidebars.js";

const state = (frameWidth, extra = {}) => ({ frameWidth, has: true, ...extra });
const mode = (frameWidth, extra) => sidebarLayout(state(frameWidth, extra)).mode;

test("with no choice on the file, the panel follows the view: open where the model keeps 640px beside it, collapsed below", () => {
  assert.equal(MIN_MODEL_WIDTH, 640);
  // The 232px panel: 872px of view and more opens it, again as the window crosses the line either way.
  assert.equal(DEFAULT_PANEL_WIDTH, 232);
  assert.deepEqual([1440, 872, 871, 700, 872].map(width => mode(width)), ["push", "push", "closed", "closed", "push"]);
  assert.deepEqual(sidebarLayout(state(700)), { mode: "closed", auto: true });
  // Against the default width, whatever the grip set: a panel dragged to 480px in a 900px view stays open.
  assert.equal(mode(900, { panelWidth: 480 }), "push");
  // Not measured yet: not collapsed. A file with no panel has none at any width.
  assert.equal(sidebarCollapsed(0), false);
  assert.equal(mode(1440, { has: false }), "closed");
});

test("the person's choice on the file holds at every width: closed stays closed as the window widens, open stays open as it narrows", () => {
  // Closed by the toggle in a wide view: closed at any width from then on.
  const closed = toggleSidebar(state(1440));
  assert.deepEqual(closed, { open: false });
  assert.deepEqual([1440, 2000, 700].map(width => mode(width, { choice: closed.open })), ["closed", "closed", "closed"]);
  // Opened by the toggle in a narrow view: open, pushing, at any width.
  const opened = toggleSidebar(state(700));
  assert.deepEqual(opened, { open: true });
  assert.deepEqual([700, 500, 1440].map(width => mode(width, { choice: opened.open })), ["push", "push", "push"]);
  assert.equal(sidebarLayout(state(500, { choice: true })).auto, false);
});

test("the width is the person's between fixed bounds, whatever the window: a stored width outside them reads as the bound", () => {
  assert.equal(MAX_PANEL_WIDTH, 480);
  assert.deepEqual([660, 480, 300, 150, undefined, Number.NaN].map(width => clampPanelWidth(width, 200)), [480, 480, 300, 200, 232, 232]);
});

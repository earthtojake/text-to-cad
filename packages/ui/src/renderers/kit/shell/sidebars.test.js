import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_PANEL_WIDTH, MIN_MODEL_WIDTH, sidebarCollapsed, sidebarLayout, sidebarWant, toggleSidebar } from "./sidebars.js";

const state = (frameWidth, extra = {}) => ({ frameWidth, want: true, has: true, opened: false, hidden: false, ...extra });

test("the one panel always pushes; it starts collapsed where open it would leave the model under 640px", () => {
  assert.equal(MIN_MODEL_WIDTH, 640);
  // The 256px panel: 896px of view and more starts it open.
  assert.equal(DEFAULT_PANEL_WIDTH, 256);
  assert.deepEqual([1440, 1100, 1024, 896, 895, 867, 700].map(width => sidebarLayout(state(width)).mode),
    ["push", "push", "push", "push", "closed", "closed", "closed"]);
  // A panel the person widened needs the more: 320px of it, 960px of view.
  assert.deepEqual([960, 959].map(width => sidebarLayout(state(width, { panelWidth: 320 })).mode), ["push", "closed"]);
  // Not measured yet: not collapsed.
  assert.equal(sidebarCollapsed(0), false);
  // A file with no panel has none at any width.
  assert.equal(sidebarLayout(state(1440, { has: false })).mode, "closed");
});

test("a collapse the width made is marked so and never kept; opening it then pushes, unwritten", () => {
  const narrow = state(650);
  assert.deepEqual(sidebarLayout(narrow), { mode: "closed", auto: true });
  const opened = toggleSidebar(narrow);
  assert.deepEqual(opened, { want: true, opened: true, kept: false });
  assert.equal(sidebarLayout({ ...narrow, opened: opened.opened }).mode, "push");
  // Wide again, the person's choice (open) holds; nothing the width did was written.
  assert.equal(sidebarLayout({ ...state(1440), opened: opened.opened }).mode, "push");
});

test("a person's close and open are kept", () => {
  const wide = state(1440);
  assert.deepEqual(toggleSidebar(wide), { want: false, opened: false, kept: true });
  assert.deepEqual(sidebarLayout({ ...wide, want: false }), { mode: "closed", auto: false }, "closed by the person, not by the width");
  assert.deepEqual(toggleSidebar({ ...wide, want: false }), { want: true, opened: false, kept: true });
  // Opened by the person where the width collapses it: kept open, and pushing now.
  assert.deepEqual(toggleSidebar({ ...state(650), want: false }), { want: true, opened: true, kept: true });
  // Absent choices are open.
  assert.equal(sidebarWant(undefined), true);
  assert.equal(sidebarWant(false), false);
});

test("\\ hides everything and brings back exactly what was open", () => {
  const before = state(650, { opened: true });
  assert.equal(sidebarLayout({ ...before, hidden: true }).mode, "closed");
  assert.deepEqual(sidebarLayout({ ...before, hidden: false }), sidebarLayout(before));
});

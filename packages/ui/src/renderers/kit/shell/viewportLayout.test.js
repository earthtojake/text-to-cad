import assert from "node:assert/strict";
import test from "node:test";

import { VIEWPORT_CUBE_TOP, VIEWPORT_STACK_BOTTOM, viewCornerLayout } from "./viewportLayout.js";

// The corner is the view's top-right (the bottom row is Quick Edit's alone), its one control the camera's own: the
// cube 12px off the top, or a flat view's zoom, its outer edge on the cube box's (12px in) and its middle on the tool
// strip's (8px down, 40px tall: 14px for a 28px control).
test("the corner stands at the top-right: the cube, or the zoom on the strip's middle line at the cube box's edge", () => {
  assert.equal(VIEWPORT_CUBE_TOP, "calc(12px + var(--cad-viewport-corner-top, 0px))");
  const right = viewCornerLayout("right");
  assert.deepEqual(right, { pill: { right: "calc(var(--cad-viewport-corner-right, 2px) + 10px)", top: "calc(14px + var(--cad-viewport-corner-top, 0px))" } });
  // The tool column stops clear of Quick Edit's row.
  assert.equal(VIEWPORT_STACK_BOTTOM, "calc(68px + 16px)");
});

test("a host that anchors the corner at the left mirrors it to the top-left", () => {
  const left = viewCornerLayout("left");
  assert.deepEqual([left.pill.left, left.pill.right, left.pill.top], ["calc(var(--cad-viewport-corner-left, 0px) + 10px)", "auto", viewCornerLayout("right").pill.top]);
});

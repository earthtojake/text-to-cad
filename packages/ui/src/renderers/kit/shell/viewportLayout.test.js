import assert from "node:assert/strict";
import test from "node:test";

import { VIEWPORT_CUBE_SIZE, VIEWPORT_CUBE_TOP, VIEWPORT_STACK_BOTTOM, viewCornerLayout } from "./viewportLayout.js";

// The corner is the view's top-right (the bottom row is Quick Edit's alone), its one control the camera's own: the
// cube's 6rem box 8px off the top, its top on the strip's, or a flat view's zoom, its outer edge the corner's inset (12px)
// in and its middle on the tool strip's (8px down, 40px tall: 14px for a 28px control).
test("the corner stands at the top-right: the cube's box on the strip's top, or the zoom on the strip's middle line", () => {
  assert.equal(VIEWPORT_CUBE_SIZE, "6rem");
  assert.equal(VIEWPORT_CUBE_TOP, "calc(8px + var(--cad-viewport-corner-top, 0px))");
  const right = viewCornerLayout("right");
  assert.deepEqual(right, { pill: { right: "calc(var(--cad-viewport-corner-right, 2px) + 10px)", top: "calc(14px + var(--cad-viewport-corner-top, 0px))" } });
  // The tool column stops clear of Quick Edit's row.
  assert.equal(VIEWPORT_STACK_BOTTOM, "84px");
});

test("a host that anchors the corner at the left mirrors it to the top-left", () => {
  const left = viewCornerLayout("left");
  assert.deepEqual([left.pill.left, left.pill.right, left.pill.top], ["calc(var(--cad-viewport-corner-left, 0px) + 10px)", "auto", viewCornerLayout("right").pill.top]);
});

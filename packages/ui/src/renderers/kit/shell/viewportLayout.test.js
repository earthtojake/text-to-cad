import assert from "node:assert/strict";
import test from "node:test";

import { CUBE_INK, CUBE_ROW_WIDTH_PX, VIEWPORT_CUBE_TOP, VIEWPORT_STACK_BOTTOM, viewCornerLayout } from "./viewportLayout.js";
import { cubeInkBox } from "../camera/ViewPlaneControl.js";
import { DEFAULT_VIEW_DIRECTION } from "../camera/viewportCameraKit.js";
import { viewCornerAway } from "./ViewCorner.jsx";

// The corner is the view's top-right (the bottom row is Quick Edit's alone): the cube 12px off the top, a flat view's
// zoom pill 12px in from the right and the top, and the corner's stack under either, at the pill's 12px right inset.
test("the corner stands at the top-right: the cube, the pill, and the stack under them", () => {
  assert.equal(VIEWPORT_CUBE_TOP, "calc(12px + var(--cad-viewport-corner-top, 0px))");
  const right = viewCornerLayout("right");
  const inset = "calc(var(--cad-viewport-corner-right, 2px) + 10px)";
  assert.deepEqual(right.pill, { right: inset, top: "calc(12px + var(--cad-viewport-corner-top, 0px))" });
  // Under the cube: its 12px, its 68px box, then a 4px gap.
  assert.deepEqual(right.stack, { right: inset, top: "calc(16px + 68px + var(--cad-viewport-corner-top, 0px))" });
  // The cube's row (Home, View): under its box as the stack is, 8px in from the box's edge (centred on its drawing).
  assert.deepEqual(right.cubeRow, { right: "calc(var(--cad-viewport-corner-right, 2px) + 18px)", top: right.stack.top });
  // Under the pill: its 12px, its 24px row, then the chrome's 8px.
  assert.deepEqual(right.stackUnderPill, { right: inset, top: "calc(44px + var(--cad-viewport-corner-top, 0px))" });
  // Nothing of the corner stands at the bottom any more; the tool column stops clear of Quick Edit's row.
  for (const place of Object.values(right)) assert.equal(place.bottom, undefined);
  assert.equal(VIEWPORT_STACK_BOTTOM, "calc(68px + 16px)");
  // Menus and tooltips open away from the corner, their tops on their buttons'.
  assert.deepEqual(viewCornerAway("right"), { side: "left", align: "start" });
});

test("a host that anchors the corner at the left mirrors it to the top-left", () => {
  const left = viewCornerLayout("left");
  const inset = "calc(var(--cad-viewport-corner-left, 0px) + 10px)";
  assert.deepEqual([left.pill.left, left.pill.right, left.stack.left, left.stackUnderPill.left], [inset, "auto", inset, inset]);
  assert.equal(left.cubeRow.left, "calc(var(--cad-viewport-corner-left, 0px) + 18px)");
  assert.equal(left.stack.top, viewCornerLayout("right").stack.top);
  assert.deepEqual(viewCornerAway("left"), { side: "right", align: "start" });
});

// The cube's row stands centred under the cube as drawn, not under its box: the cube's outline from the view the file
// opens with (which Home goes back to) is inset in its 68px box, and the 52px row's middle is the outline's middle.
test("the cube's row is centred under the drawn cube", () => {
  assert.deepEqual(CUBE_INK, cubeInkBox(DEFAULT_VIEW_DIRECTION, 68));
  // A face seen square-on fills ±21 of the view box's 76 units round its centre: 15.2px in from each side of 68.
  const front = cubeInkBox([0, -1, 0], 68);
  assert.ok(Math.abs(front.left - 15.21) < 0.01 && Math.abs(front.top - 15.21) < 0.01 && Math.abs(front.right - 52.79) < 0.01);
  const px = value => Number(/\+ (\d+)px\)$/.exec(value)?.[1]);
  // From the corner's edge: the cube's box ends 10px in and is 68px wide; the row's right edge is `right` in.
  const rowMiddle = 10 + 68 - px(viewCornerLayout("right").cubeRow.right) - CUBE_ROW_WIDTH_PX / 2;
  const inkMiddle = 68 - (CUBE_INK.left + CUBE_INK.right) / 2 + 10;
  assert.ok(Math.abs(rowMiddle - (10 + 68 - inkMiddle)) <= 0.5, `row ${rowMiddle} vs drawing ${10 + 68 - inkMiddle}`);
});

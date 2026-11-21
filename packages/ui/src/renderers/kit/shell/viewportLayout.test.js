import assert from "node:assert/strict";
import test from "node:test";

import { CUBE_HOME_INK, VIEWPORT_CUBE_TOP, VIEWPORT_STACK_BOTTOM, viewCornerLayout } from "./viewportLayout.js";
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
  // Home against the cube's drawing (inset in its box): 4px from it, level with its top face's top.
  assert.deepEqual(right.home, { right: "calc(var(--cad-viewport-corner-right, 2px) + 74px)", top: "calc(19px + var(--cad-viewport-corner-top, 0px))" });
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
  assert.equal(left.home.left, "calc(var(--cad-viewport-corner-left, 0px) + 74px)");
  assert.equal(left.stack.top, viewCornerLayout("right").stack.top);
  assert.deepEqual(viewCornerAway("left"), { side: "right", align: "start" });
});

// Home is attached to the cube as drawn, not to its box: the cube's outline from the view the file opens with (which
// Home goes back to) is inset in its 68px box, and Home's 24px button stands 4px (to the pixel) left of that outline,
// its top on the outline's top, so the two read as one control.
test("Home stands against the drawn cube: 4px from its outline, top-aligned with its top face", () => {
  assert.deepEqual(CUBE_HOME_INK, cubeInkBox(DEFAULT_VIEW_DIRECTION, 68));
  // A face seen square-on fills ±21 of the view box's 76 units round its centre: 15.2px in from each side of 68.
  const front = cubeInkBox([0, -1, 0], 68);
  assert.ok(Math.abs(front.left - 15.21) < 0.01 && Math.abs(front.top - 15.21) < 0.01 && Math.abs(front.right - 52.79) < 0.01);
  const px = value => Number(/\+ (\d+)px\)$/.exec(value)?.[1] ?? /calc\((\d+)px/.exec(value)?.[1]);
  const home = viewCornerLayout("right").home;
  // From the corner's edge: the cube's box ends 10px in and is 68px wide; Home's right edge is `right` in.
  const homeRight = 10 + 68 - px(home.right);
  const homeTop = px(home.top) - 12;
  assert.ok(Math.abs(CUBE_HOME_INK.left - homeRight - 4) <= 0.5, `gap ${CUBE_HOME_INK.left - homeRight}`);
  assert.ok(Math.abs(homeTop - CUBE_HOME_INK.top) <= 0.5, `top ${homeTop} vs ${CUBE_HOME_INK.top}`);
});

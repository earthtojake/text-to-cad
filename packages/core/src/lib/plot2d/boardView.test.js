import assert from "node:assert/strict";
import test from "node:test";

import { projectWorldPointToClient } from "../viewer/measureRuler.js";
import { boardMirrorX, boardPlanProjection, marksInPlan, planToSheet, sheetToPlan } from "./boardView.js";

const sheet = { x: 0, y: 0, width: 40, height: 30 };

test("a sheet point is the plan's with y up, mirrored about the sheet's middle from below, and back", () => {
  assert.equal(boardMirrorX(sheet, "top"), null);
  assert.equal(boardMirrorX(sheet, "bottom"), 20);
  assert.deepEqual(sheetToPlan([5, 15]), [5, -15]);
  assert.deepEqual(sheetToPlan([5, 15], 20), [35, -15]);
  assert.deepEqual(planToSheet(sheetToPlan([5, 15], 20), 20), [5, 15]);
  const [mark] = marksInPlan([{ id: "a", kind: "stroke", points: [5, 15, 0, 6, 16, 0] }], 20);
  assert.deepEqual([...mark.points], [35, -15, 0, 34, -16, 0]);
});

test("the projection puts a sheet point where the view draws it, from either side", () => {
  // A view of 10 px per mm, the sheet's corner at the pane's (100, 100): screen y = 100 + 10 * sheet y.
  const transform = { scale: 10, offsetX: 100, offsetY: 100 };
  const rect = { left: 0, top: 0, width: 800, height: 600 };
  const top = projectWorldPointToClient([5, 15, 0], boardPlanProjection(transform, 800, 600), rect);
  assert.deepEqual([Math.round(top.x), Math.round(top.y)], [150, 250]);
  const bottom = projectWorldPointToClient([5, 15, 0], boardPlanProjection(transform, 800, 600, 20), rect);
  assert.deepEqual([Math.round(bottom.x), Math.round(bottom.y)], [450, 250]);
});

// Callouts set apart on screen (`separateLabels.js`): one that would cover another steps below it,
// clear; one the code placed never moves, and the others keep clear of it.
import assert from "node:assert/strict";
import test from "node:test";
import { separateLabels } from "./separateLabels.js";

const box = (x, y, movable = true) => ({ x, y, w: 60, h: 16, movable });

test("labels that would cover one another are stacked, clear", () => {
  assert.deepEqual(separateLabels([box(100, 100), box(110, 104), box(400, 100)]), [{ x: 100, y: 100 }, { x: 110, y: 119 }, { x: 400, y: 100 }]);
  // A third on the first two goes under both.
  assert.deepEqual(separateLabels([box(100, 100), box(100, 100), box(100, 100)]).map(at => at.y), [100, 119, 138]);
});

test("a label the code placed stays put, and the others keep clear of it", () => {
  assert.deepEqual(separateLabels([box(100, 100), box(100, 104, false)]), [{ x: 100, y: 123 }, { x: 100, y: 104 }]);
});

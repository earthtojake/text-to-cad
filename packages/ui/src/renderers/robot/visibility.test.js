import assert from "node:assert/strict";
import test from "node:test";

import { changeRobotVisibility, robotVisibilityState } from "./visibility.js";

// The eye's rules, as `settings-ui.md` states them for a Links row: a link hides its own visuals
// and never its child links; a partly hidden link is not hidden, so its eye hides the rest; and a
// reload keeps only the ids the loaded part list still has.

test("a row is hidden when every part it draws is; a row that draws nothing has no eye", () => {
  assert.deepEqual(robotVisibilityState(["a", "b"], new Set(["a", "b"])), { ids: ["a", "b"], allHidden: true });
  assert.deepEqual(robotVisibilityState(["a", "b"], new Set(["a"])), { ids: ["a", "b"], allHidden: false }, "partly hidden is not hidden");
  assert.deepEqual(robotVisibilityState([], new Set(["a"])), { ids: [], allHidden: false });
  assert.deepEqual(robotVisibilityState(), { ids: [], allHidden: false });
});

test("hiding adds the row's parts once, revealing removes them, and ids no longer loaded are dropped", () => {
  const loaded = new Set(["a", "b", "c"]);
  const hidden = changeRobotVisibility([], ["a", "b"], false, loaded);
  assert.deepEqual(hidden, ["a", "b"]);
  assert.deepEqual(changeRobotVisibility(hidden, ["b", "c"], false, loaded), ["a", "b", "c"], "the rest of a partly hidden link, no duplicate");
  assert.deepEqual(changeRobotVisibility(["a", "b", "c"], ["a", "b"], true, loaded), ["c"]);
  assert.deepEqual(changeRobotVisibility(["a", "gone"], ["x", 7], false, loaded), ["a"], "an id the robot does not have is neither kept nor added");
  const before = ["a"];
  assert.notEqual(changeRobotVisibility(before, ["b"], false, loaded), before, "every edit is a new array");
});

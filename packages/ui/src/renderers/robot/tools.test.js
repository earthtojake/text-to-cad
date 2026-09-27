import assert from "node:assert/strict";
import test from "node:test";

import { ROBOT_TOOL, ROBOT_TOOL_MODES } from "./tools.js";

test("a robot opens in Select: the tool in hand is never saved, so there is nothing to restore into", () => {
  assert.equal(ROBOT_TOOL_MODES.defaultMode, ROBOT_TOOL.SELECT);
  assert.equal(ROBOT_TOOL_MODES.normalize("pose"), ROBOT_TOOL.POSE);
  assert.equal(ROBOT_TOOL_MODES.normalize("draw"), ROBOT_TOOL.SELECT, "a tool a robot has none of is Select");
  assert.equal("restore" in ROBOT_TOOL_MODES, false);
});

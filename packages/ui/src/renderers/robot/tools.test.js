import assert from "node:assert/strict";
import test from "node:test";

import { ROBOT_TOOL, ROBOT_TOOL_MODES } from "./tools.js";

test("a robot opens in Select, beside Pencil, Shapes and Measure (Clip is a popover, never in hand): the tool in hand is never saved, so there is nothing to restore into", () => {
  assert.equal(ROBOT_TOOL_MODES.defaultMode, ROBOT_TOOL.SELECT);
  assert.deepEqual(Object.values(ROBOT_TOOL), ["select", "pencil", "shapes", "measure"]);
  assert.equal(ROBOT_TOOL_MODES.normalize("pose"), ROBOT_TOOL.SELECT, "Position is Select's filter, not a tool");
  assert.equal(ROBOT_TOOL_MODES.normalize("exploded"), ROBOT_TOOL.SELECT, "a robot is posed, never exploded: a tool it has none of is Select");
  assert.equal("restore" in ROBOT_TOOL_MODES, false);
});

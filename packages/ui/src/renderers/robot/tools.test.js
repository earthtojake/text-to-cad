import assert from "node:assert/strict";
import test from "node:test";

import { ROBOT_TOOL_MODES, ROBOT_TOOL_RESTORE } from "./tools.js";

test("robot files reopen in Select even when last saved under Position", () => {
  for (const recorded of [undefined, "", "select", "pose"])
    assert.equal(ROBOT_TOOL_MODES.restore(recorded, ROBOT_TOOL_RESTORE), "select");
});

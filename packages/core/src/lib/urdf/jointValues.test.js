import assert from "node:assert/strict";
import test from "node:test";

import { jointValueMapsClose } from "./jointValues.js";

test("jointValueMapsClose compares normalized finite joint values", () => {
  assert.equal(jointValueMapsClose({ shoulder: "90" }, { shoulder: 90.0005 }), true);
  assert.equal(jointValueMapsClose({ shoulder: 90, elbow: 0 }, { shoulder: 90 }), false);
  assert.equal(jointValueMapsClose({ shoulder: 90 }, { shoulder: 91 }), false);
});

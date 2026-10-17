import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveParameterNumberControlStep } from "./parameterControls.js";

// Two of cadgen's articulation controls: a turn over 150 degrees and a travel over 1 mm.
const frame = { id: "frame", label: "frame", unit: "deg", min: 0, max: 150, default: 0 };
const lift = { id: "lift", label: "lift", unit: "mm", min: 0, max: 1, default: 0 };

test("resolveParameterNumberControlStep makes coarse sliders finer", () => {
  assert.equal(resolveParameterNumberControlStep(frame), 0.1);
  assert.equal(resolveParameterNumberControlStep(lift), 0.001);
});

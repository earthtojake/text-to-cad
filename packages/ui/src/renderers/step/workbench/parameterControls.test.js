import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText,
  resolveParameterNumberControlStep
} from "./parameterControls.js";

// The definition as the motion hook holds it: cadgen's articulation, whose controls are what
// Copy writes out and Paste reads back, in declaration order and within their limits.
const definition = { url: "/x.step.json", articulation: {
  schemaVersion: 1,
  controls: [
    { id: "frame", label: "frame", unit: "deg", min: 0, max: 150, default: 0 },
    { id: "lift", label: "lift", unit: "mm", min: 0, max: 1, default: 0 }
  ],
  joints: [], carries: {}, handles: [], poses: {}, opening: { frame: 0, lift: 0 }
} };
const [frame, lift] = definition.articulation.controls;

const STEP_LABELS = { label: "STEP parameter", unknownLabel: "STEP parameter" };

test("resolveParameterNumberControlStep makes coarse sliders finer", () => {
  assert.equal(resolveParameterNumberControlStep(frame), 0.1);
  assert.equal(resolveParameterNumberControlStep(lift), 0.001);
});

test("buildParameterValuesCopyText emits ordered snapshot-ready JSON", () => {
  assert.equal(
    buildParameterValuesCopyText(definition, { lift: 0.25, frame: 12.5 }),
    `{
  "frame": 12.5,
  "lift": 0.25
}`
  );
  assert.equal(buildParameterValuesCopyText({ articulation: null }), "{}");
});

test("parseParameterValuesPasteText accepts direct and snapshot flag JSON, within the limits", () => {
  assert.deepEqual(
    parseParameterValuesPasteText(definition, '{"frame": 12.75}', STEP_LABELS),
    { values: { frame: 12.75 }, count: 1 }
  );
  assert.deepEqual(
    parseParameterValuesPasteText(definition, `--kinematics '{"values":{"frame":151,"lift":0.333}}'`, STEP_LABELS),
    { values: { frame: 150, lift: 0.333 }, count: 2 }
  );
});

test("parseParameterValuesPasteText reports unknown ids with the runtime's label", () => {
  assert.throws(
    () => parseParameterValuesPasteText(definition, '{"missing": 1}', STEP_LABELS),
    /Unknown STEP parameter: missing/
  );
  assert.throws(
    () => parseParameterValuesPasteText(definition, '{"missing": 1}', {
      label: "pose parameter",
      unknownLabel: "pose parameter"
    }),
    /Unknown pose parameter: missing/
  );
});

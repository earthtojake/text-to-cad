import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText,
  resolveParameterNumberControlStep
} from "./parameterControls.js";
import { normalizeStepModuleDefinition } from "cadjs/common/stepModule.js";

// Exercised against a STEP module definition on purpose: these helpers back BOTH
// parameter stores through the single runtime-keyed handler set in CadWorkspace, and
// the STEP side used to reach them through a pass-through shim that only differed by a
// label string. If a store ever needs its own parsing, that is a real fork worth seeing.
const definition = normalizeStepModuleDefinition({
  parameters: {
    frame: { type: "number", min: 0, max: 150, step: 1, default: 0 },
    lift: { type: "number", min: 0, max: 1, step: 0.01, default: 0 },
    enabled: { type: "boolean", default: false },
    color: { type: "color", default: "#336699" }
  }
});

const STEP_LABELS = { label: "STEP parameter", unknownLabel: "STEP parameter" };

test("resolveParameterNumberControlStep makes coarse sliders finer", () => {
  assert.equal(resolveParameterNumberControlStep(definition.parameterMap.frame), 0.1);
  assert.equal(resolveParameterNumberControlStep(definition.parameterMap.lift), 0.001);
});

test("buildParameterValuesCopyText emits ordered snapshot-ready JSON", () => {
  assert.equal(
    buildParameterValuesCopyText(definition, {
      enabled: true,
      frame: 12.5,
      lift: 0.25,
      color: "#ffffff"
    }),
    `{
  "frame": 12.5,
  "lift": 0.25,
  "enabled": true,
  "color": "#ffffff"
}`
  );
});

test("parseParameterValuesPasteText accepts direct and snapshot flag JSON", () => {
  assert.deepEqual(
    parseParameterValuesPasteText(definition, '{"frame": 12.75, "enabled": true}', STEP_LABELS),
    {
      values: { frame: 12.75, enabled: true },
      count: 2
    }
  );
  assert.deepEqual(
    parseParameterValuesPasteText(definition, `--params '{"values":{"frame":151,"lift":0.333}}'`, STEP_LABELS),
    {
      values: { frame: 150, lift: 0.333 },
      count: 2
    }
  );
});

test("parseParameterValuesPasteText reports unknown ids with the runtime's label", () => {
  assert.throws(
    () => parseParameterValuesPasteText(definition, '{"missing": 1}', STEP_LABELS),
    /Unknown STEP parameter: missing/
  );
  assert.throws(
    () => parseParameterValuesPasteText(definition, '{"missing": 1}', {
      label: "implicit parameter",
      unknownLabel: "implicit parameter"
    }),
    /Unknown implicit parameter: missing/
  );
});

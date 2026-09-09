import assert from "node:assert/strict";
import test from "node:test";

import {
  STEP_MODULE_SCHEMA_VERSION,
  normalizeStepModuleDefinition
} from "cadgen-js/common/stepModule.js";

import { resolveStepModuleLoad } from "./stepModuleLoad.js";

const HINGE = normalizeStepModuleDefinition({
  schemaVersion: STEP_MODULE_SCHEMA_VERSION,
  parameters: {
    swing: { type: "number", label: "Swing", min: 0, max: 120, default: 15 }
  }
}, { cadPath: "hinge.step" });

// A model that declares ANIMATION but no KINEMATICS crashed the Kinematics tab
// with "Cannot read properties of null (reading 'defaultParameterValues')". The
// sidecar URL is set whenever a sidecar exists, and an animation-only model has
// one, so the pose loader runs for it and resolves to null — the documented
// "nothing to pose" outcome. Dereferencing it threw a TypeError that the
// loader's own .catch() turned into an error row rendered inside a tab that only
// existed because the error was there.
//
// What these tests pin is the CONTRACT of the one place that commit now happens,
// not the call site: they exercise resolveStepModuleLoad, which was extracted
// from the load effect BY the fix, so they cannot fail on the code that crashed.
// The fix is that the effect no longer touches the definition itself — there is
// one place left that can get this wrong, and it is this one.
test("a model with animation but no kinematics resolves to nothing to pose", () => {
  const resolved = resolveStepModuleLoad({ url: "/__cad/asset?file=w16.step.json", definition: null });

  assert.deepEqual(resolved.loadState, {
    url: "/__cad/asset?file=w16.step.json",
    status: "ready",
    error: "",
    definition: null
  });
  // Ready with no definition and no error is what makes the Kinematics tab
  // ABSENT rather than empty (poseControlsHaveContent), which is the coherent
  // outcome: a model with no mates has no Kinematics tab, exactly as a model
  // with no clips has no Animation tab.
  assert.deepEqual(resolved.parameterValues, {});
  assert.equal(resolved.enabled, true);
});

test("a model with kinematics opens at the definition's own defaults", () => {
  const resolved = resolveStepModuleLoad({ url: "/hinge.step.json", definition: HINGE });

  assert.equal(resolved.loadState.definition, HINGE);
  assert.deepEqual(resolved.parameterValues, { swing: 15 });
  assert.equal(resolved.enabled, true);
});

test("a restored session's DOF values and pose gate win over the defaults", () => {
  const resolved = resolveStepModuleLoad({
    url: "/hinge.step.json",
    definition: HINGE,
    restored: { enabled: false, parameterValues: { swing: 90 } }
  });

  assert.deepEqual(resolved.parameterValues, { swing: 90 });
  assert.equal(resolved.enabled, false);
});

test("a restored session for a model with no kinematics carries no pose values", () => {
  // The same null path, reached with a session slice in hand: normalizing
  // against no definition yields no values rather than passing stored ones
  // through to a system that does not exist.
  const resolved = resolveStepModuleLoad({
    url: "/w16.step.json",
    definition: null,
    restored: { enabled: false, parameterValues: { swing: 90 } }
  });

  assert.deepEqual(resolved.parameterValues, {});
  assert.equal(resolved.enabled, false);
});

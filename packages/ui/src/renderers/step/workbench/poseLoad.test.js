import assert from "node:assert/strict";
import test from "node:test";

import { resolvePoseLoad, stepPoseLogic } from "./poseLoad.js";

const HINGE = { url: "/hinge.step.json", articulation: {
  schemaVersion: 1,
  controls: [{ id: "swing", label: "Swing", unit: "deg", min: 0, max: 120, default: 15 }],
  joints: [], carries: {}, handles: [], poses: { open: { swing: 90 } }, opening: { swing: 15 }
} };

// A model that declares ANIMATION but no KINEMATICS once crashed the Position section with
// "Cannot read properties of null". An animation-only model has a sidecar, so its entry has
// a load to resolve, and resolves to NULL — the documented "nothing to pose" outcome. What
// these tests pin is the CONTRACT of the one place that commit happens.
test("a model with animation but no kinematics resolves to nothing to pose", () => {
  const resolved = resolvePoseLoad({ url: "/__cad/asset?file=w16.step.json", definition: null });

  assert.deepEqual(resolved.loadState, {
    url: "/__cad/asset?file=w16.step.json",
    status: "ready",
    error: "",
    definition: null
  });
  // Ready with no definition and no error is what makes the Position section ABSENT
  // rather than empty (poseControlsHaveContent): a model with no mates has no Position,
  // exactly as a model with no clips has no Animation.
  assert.deepEqual(resolved.parameterValues, {});
});

test("a model with kinematics opens at its articulation's rest values", () => {
  const resolved = resolvePoseLoad({ url: "/hinge.step.json", definition: HINGE });

  assert.equal(resolved.loadState.definition, HINGE);
  assert.deepEqual(resolved.parameterValues, { swing: 15 });
});

test("a restored session's control values win over the rest values, within the limits", () => {
  const resolved = resolvePoseLoad({
    url: "/hinge.step.json",
    definition: HINGE,
    restored: { parameterValues: { swing: 90, stray: 4 } }
  });

  assert.deepEqual(resolved.parameterValues, { swing: 90 });
});

test("a restored session for a model with no kinematics carries no pose values", () => {
  const resolved = resolvePoseLoad({
    url: "/w16.step.json",
    definition: null,
    restored: { parameterValues: { swing: 90 } }
  });

  assert.deepEqual(resolved.parameterValues, {});
});

test("the pose logic is the controls and named poses, never the version", () => {
  assert.equal(stepPoseLogic(HINGE), stepPoseLogic({ ...HINGE, url: "/hinge.step.json?v=2" }));
  assert.notEqual(stepPoseLogic(HINGE), stepPoseLogic({ ...HINGE, articulation: { ...HINGE.articulation, poses: {} } }));
  assert.equal(stepPoseLogic(null), "");
});

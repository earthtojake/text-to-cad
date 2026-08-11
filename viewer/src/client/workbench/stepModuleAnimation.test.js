import assert from "node:assert/strict";
import { test } from "node:test";

import {
  animationNowMs,
  buildDefaultStepModuleAnimationState,
  findStepModuleAnimation
} from "./stepModuleAnimation.js";

test("STEP module animation helpers select requested animations with first-animation fallback", () => {
  const definition = {
    animations: [
      { id: "orbit", durationSec: 2 },
      { id: "fold", durationSec: 5 }
    ]
  };

  assert.deepEqual(findStepModuleAnimation(definition, "fold"), { id: "fold", durationSec: 5 });
  assert.deepEqual(findStepModuleAnimation(definition, "missing"), { id: "orbit", durationSec: 2 });
  assert.equal(findStepModuleAnimation({ animations: [] }, "fold"), null);
});

test("STEP module animation default state mirrors CadWorkspace defaults", () => {
  assert.deepEqual(buildDefaultStepModuleAnimationState({ animations: [{ id: "orbit" }] }), {
    activeId: "orbit",
    playing: false,
    elapsedSec: 0,
    speed: 1,
    loopEnabled: true
  });
  assert.deepEqual(buildDefaultStepModuleAnimationState(null), {
    activeId: "",
    playing: false,
    elapsedSec: 0,
    speed: 1,
    loopEnabled: true
  });
  assert.equal(
    buildDefaultStepModuleAnimationState({ animations: [{ id: "orbit", loop: false }] }).loopEnabled,
    false
  );
});

test("animationNowMs returns a finite monotonic-clock-compatible timestamp", () => {
  assert.equal(Number.isFinite(animationNowMs()), true);
});

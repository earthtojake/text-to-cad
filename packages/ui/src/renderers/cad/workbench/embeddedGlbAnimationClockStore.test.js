import assert from "node:assert/strict";
import test from "node:test";
import { createAnimationClock } from "./animationClockStore.js";
import { createEmbeddedGlbAnimationClock } from "./embeddedGlbAnimationClockStore.js";

test("embedded GLB clocks cannot rewind another renderer or STEP playback", () => {
  const step = createAnimationClock(), first = createEmbeddedGlbAnimationClock(), second = createEmbeddedGlbAnimationClock();
  let firstChanges = 0, secondChanges = 0;
  const stop = first.subscribe(() => firstChanges++);
  second.subscribe(() => secondChanges++);
  step.setAnimationClock(0.75);
  first.setAnimationClock(0.4);
  second.setAnimationClock(1.2);
  first.resetAnimationClock();
  assert.equal(first.getAnimationClock(), 0);
  assert.equal(second.getAnimationClock(), 1.2);
  assert.equal(step.getAnimationClock(), 0.75);
  assert.equal(firstChanges, 2);
  assert.equal(secondChanges, 1);
  stop();
  first.setAnimationClock(9);
  assert.equal(firstChanges, 2);
});

import assert from "node:assert/strict";
import test from "node:test";
import { getAnimationClock, resetAnimationClock, setAnimationClock } from "./animationClockStore.js";
import {
  getEmbeddedGlbAnimationClock,
  resetEmbeddedGlbAnimationClock,
  setEmbeddedGlbAnimationClock
} from "./embeddedGlbAnimationClockStore.js";

test("embedded GLB playback clock cannot rewind STEP animation state", () => {
  setAnimationClock(0.75);
  setEmbeddedGlbAnimationClock(0.4);
  resetEmbeddedGlbAnimationClock();
  assert.equal(getEmbeddedGlbAnimationClock(), 0);
  assert.equal(getAnimationClock(), 0.75);
  setEmbeddedGlbAnimationClock(0.4);
  resetAnimationClock();
  assert.equal(getEmbeddedGlbAnimationClock(), 0.4);
});

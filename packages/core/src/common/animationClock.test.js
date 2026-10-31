import assert from "node:assert/strict";
import { test } from "node:test";

import { advanceAnimationElapsed } from "./animationClock.js";

test("the clock wraps when looping and stops at the end when not", () => {
  assert.deepEqual(
    advanceAnimationElapsed({ elapsedSec: 5.5, deltaSec: 1, speed: 1, duration: 6, loopEnabled: true }),
    { elapsedSec: 0.5, playing: true }
  );
  assert.deepEqual(
    advanceAnimationElapsed({ elapsedSec: 5.5, deltaSec: 1, speed: 1, duration: 6, loopEnabled: false }),
    { elapsedSec: 6, playing: false }
  );
  // Speed scales the delta, and is clamped to the transport's range.
  assert.equal(
    advanceAnimationElapsed({ elapsedSec: 0, deltaSec: 1, speed: 9, duration: 100, loopEnabled: false }).elapsedSec,
    3
  );
});

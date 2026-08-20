import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_ANIMATION_FRAME_MS,
  MIN_ANIMATION_FRAME_MS,
  animationFrameBudgetMs,
  shouldPublishAnimationFrame
} from "./parameterAnimation.js";

// Frame pacing exists because publishing a frame costs far more than the tick
// that publishes it: on a large assembly the store notify re-renders the
// workspace, reapplies every module effect across the display records and
// redraws the scene. Measured on the F-14D teardown (2,392 display records) a
// published frame cost ~73 ms of main-thread work, so publishing on every rAF
// left the thread saturated -- the clock advanced but the browser never got a
// slot to composite, and playback read as frozen while dragging the same
// parameter still worked, because a drag pays that cost once.

test("an unsaturated model publishes on every display frame", () => {
  // A 16.7 ms gap is rAF running at the refresh rate, not work overrunning, so
  // the budget floors and every callback publishes. Pacing must not cost fps to
  // the models that never had a problem.
  const publishCostMs = 16.7;
  assert.equal(animationFrameBudgetMs(publishCostMs), MIN_ANIMATION_FRAME_MS);
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 16.7, publishedAtMs: 0, publishCostMs }),
    true
  );
});

test("a saturated model idles about as long as its last frame cost", () => {
  const publishCostMs = 73;
  assert.equal(animationFrameBudgetMs(publishCostMs), 146);
  // The callback that measures the cost arrives at +73 ms and must NOT publish:
  // budgeting at exactly the measured cost would insert no idle time at all.
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 73, publishedAtMs: 0, publishCostMs }),
    false
  );
  // Publishing resumes once the thread has had a comparable stretch free.
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 150, publishedAtMs: 0, publishCostMs }),
    true
  );
});

test("the first frame of a playback publishes immediately", () => {
  // publishedAtMs starts unset: there is no previous frame to pace against, and
  // waiting a budget before the first one would stall the opening of every clip.
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 0, publishedAtMs: NaN, publishCostMs: 0 }),
    true
  );
});

test("a catastrophic frame still leaves the clip advancing", () => {
  // Without a ceiling, one 2 s hitch would pace the next frame 4 s out and the
  // animation would look stopped rather than slow.
  assert.equal(animationFrameBudgetMs(2000), MAX_ANIMATION_FRAME_MS);
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 260, publishedAtMs: 0, publishCostMs: 2000 }),
    true
  );
});

test("an unmeasured frame cost falls back to the floor", () => {
  // publishCostMs is 0 until the first publish has been measured, and a NaN gap
  // must not park the budget at NaN and block playback forever.
  assert.equal(animationFrameBudgetMs(0), MIN_ANIMATION_FRAME_MS);
  assert.equal(animationFrameBudgetMs(NaN), MIN_ANIMATION_FRAME_MS);
  assert.equal(animationFrameBudgetMs(-5), MIN_ANIMATION_FRAME_MS);
});

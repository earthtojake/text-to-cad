import assert from "node:assert/strict";
import test from "node:test";

import { PROGRESSIVE_LOAD_FRAME_INTERVAL_MS, progressiveRenderDelay } from "./progressiveRenderThrottle.js";

test("frames are not throttled outside a progressive load", () => {
  assert.equal(progressiveRenderDelay({ progressiveLoadActive: false, lastRenderAt: 990, now: 1000 }), 0);
  assert.equal(progressiveRenderDelay(), 0);
});

test("a progressive load renders at most one frame per interval", () => {
  assert.equal(PROGRESSIVE_LOAD_FRAME_INTERVAL_MS, 250);
  assert.equal(progressiveRenderDelay({ progressiveLoadActive: true, lastRenderAt: 0, now: 1000 }), 0, "first frame");
  assert.equal(progressiveRenderDelay({ progressiveLoadActive: true, lastRenderAt: 1000, now: 1010 }), 240);
  assert.equal(progressiveRenderDelay({ progressiveLoadActive: true, lastRenderAt: 1000, now: 1249.5 }), 1);
  assert.equal(progressiveRenderDelay({ progressiveLoadActive: true, lastRenderAt: 1000, now: 1250 }), 0);
  assert.equal(progressiveRenderDelay({ progressiveLoadActive: true, lastRenderAt: 1000, now: 1100, intervalMs: 500 }), 400);
});

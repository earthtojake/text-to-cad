import assert from "node:assert/strict";
import test from "node:test";

import { normalizeServerLifetimeMs, scheduleProcessShutdown } from "./serverLifetime.mjs";

const twelveHoursMs = 12 * 60 * 60 * 1000;

test("normalizeServerLifetimeMs is opt-in unless a default is provided", () => {
  assert.equal(normalizeServerLifetimeMs(undefined), null);
  assert.equal(normalizeServerLifetimeMs("", twelveHoursMs), twelveHoursMs);
  assert.equal(normalizeServerLifetimeMs("60000"), 60_000);
  assert.equal(normalizeServerLifetimeMs("bad", twelveHoursMs), twelveHoursMs);
});

test("scheduleProcessShutdown is a no-op without an explicit lifetime", () => {
  assert.equal(scheduleProcessShutdown(), null);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  formatServerLifetime,
  normalizeServerLifetimeMs,
  parseServerLifetimeMs,
  scheduleProcessShutdown,
} from "./serverLifetime.mjs";

const twelveHoursMs = 12 * 60 * 60 * 1000;

test("normalizeServerLifetimeMs is opt-in unless a default is provided", () => {
  assert.equal(normalizeServerLifetimeMs(undefined), null);
  assert.equal(normalizeServerLifetimeMs("", twelveHoursMs), twelveHoursMs);
  assert.equal(normalizeServerLifetimeMs("60000"), 60_000);
  assert.equal(normalizeServerLifetimeMs("bad", twelveHoursMs), twelveHoursMs);
});

test("parseServerLifetimeMs accepts duration suffixes for CLI flags", () => {
  assert.equal(parseServerLifetimeMs("12h"), twelveHoursMs);
  assert.equal(parseServerLifetimeMs("30m"), 30 * 60 * 1000);
  assert.equal(parseServerLifetimeMs("45s"), 45 * 1000);
  assert.equal(parseServerLifetimeMs("750"), 750);
  assert.throws(() => parseServerLifetimeMs("0"), /between 1ms/);
});

test("formatServerLifetime prints compact duration labels", () => {
  assert.equal(formatServerLifetime(12 * 60 * 60 * 1000), "12h");
  assert.equal(formatServerLifetime(30 * 60 * 1000), "30m");
  assert.equal(formatServerLifetime(45 * 1000), "45s");
  assert.equal(formatServerLifetime(750), "750ms");
});

test("scheduleProcessShutdown is a no-op without an explicit lifetime", () => {
  assert.equal(scheduleProcessShutdown(), null);
});

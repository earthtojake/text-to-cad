import assert from "node:assert/strict";
import test from "node:test";

import { mapWithConcurrency } from "./concurrency.js";

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

test("mapWithConcurrency preserves result order while capping active work", async () => {
  let activeCount = 0;
  let peakActiveCount = 0;

  const results = await mapWithConcurrency([1, 2, 3, 4, 5], 2, async (value) => {
    activeCount += 1;
    peakActiveCount = Math.max(peakActiveCount, activeCount);
    await delay(5);
    activeCount -= 1;
    return value * 10;
  });

  assert.deepEqual(results, [10, 20, 30, 40, 50]);
  assert.equal(peakActiveCount, 2);
});

test("mapWithConcurrency handles empty input", async () => {
  const results = await mapWithConcurrency([], 4, async () => {
    throw new Error("mapper should not run for empty input");
  });

  assert.deepEqual(results, []);
});

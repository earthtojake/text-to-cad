import assert from "node:assert/strict";
import test from "node:test";

import { chooseBrowserConcurrency } from "./browserConcurrency.mjs";

test("a quiet machine keeps the requested concurrency, silently", () => {
  assert.deepEqual(chooseBrowserConcurrency({ requested: undefined, load: 3, cpus: 8 }), { concurrency: 4, note: null });
  assert.deepEqual(chooseBrowserConcurrency({ requested: "2", load: 8, cpus: 8 }), { concurrency: 2, note: null });
});

test("a machine whose load exceeds its cores runs browser specs one at a time, and says so", () => {
  const busy = chooseBrowserConcurrency({ requested: undefined, load: 99, cpus: 8 });
  assert.equal(busy.concurrency, 1, "load above the core count must drop browser specs to concurrency 1");
  assert.match(busy.note, /concurrency 1/u);
});

test("CI's concurrency of 1 is unchanged and prints nothing", () => {
  assert.deepEqual(chooseBrowserConcurrency({ requested: "1", load: 99, cpus: 2 }), { concurrency: 1, note: null });
});

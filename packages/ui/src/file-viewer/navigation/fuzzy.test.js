import assert from "node:assert/strict";
import test from "node:test";

import { fuzzyMatch } from "./fuzzy.js";

/** Fuzzy matching, which the model tree's filter ranks by (`modelTreeSearch.js`), and what makes it find the right path. */

const score = (needle, haystack) => fuzzyMatch(needle, haystack)?.score ?? -Infinity;

test("finds a path from the initials of its segments", () => {
  assert.notEqual(fuzzyMatch("srexfs", "src/main/explorer/fs.ts"), null);
});

test("rejects a needle whose characters are not in order", () => {
  assert.equal(fuzzyMatch("stf", "fs.ts"), null);
});

test("prefers a match in the filename over one in a directory", () => {
  assert.ok(score("explorer", "src/explorer.ts") > score("explorer", "explorer/vendor/a.ts"));
});

test("prefers the shorter, shallower path when the match is otherwise the same", () => {
  assert.ok(score("index", "index.ts") > score("index", "a/b/c/d/e/index.ts"));
});

test("returns the matched indices, which is what the row bolds", () => {
  const match = fuzzyMatch("idx", "index.ts");
  assert.deepEqual(match?.indices, [0, 2, 4]);
});

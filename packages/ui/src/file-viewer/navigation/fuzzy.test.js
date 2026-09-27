import assert from "node:assert/strict";
import test from "node:test";

import { fuzzyFilter, fuzzyMatch } from "./fuzzy.js";

/** The file tree's `Filter files…` box, and what makes it find the right path. */

test("finds a path from the initials of its segments", () => {
  assert.notEqual(fuzzyMatch("srexfs", "src/main/explorer/fs.ts"), null);
});

test("rejects a needle whose characters are not in order", () => {
  assert.equal(fuzzyMatch("stf", "fs.ts"), null);
});

test("prefers a match in the filename over one in a directory", () => {
  const ranked = fuzzyFilter(["explorer/vendor/a.ts", "src/explorer.ts"], "explorer");
  assert.equal(ranked[0]?.path, "src/explorer.ts");
});

test("prefers the shorter, shallower path when the match is otherwise the same", () => {
  const ranked = fuzzyFilter(["a/b/c/d/e/index.ts", "index.ts"], "index");
  assert.equal(ranked[0]?.path, "index.ts");
});

test("returns the matched indices, which is what the row bolds", () => {
  const match = fuzzyMatch("idx", "index.ts");
  assert.deepEqual(match?.indices, [0, 2, 4]);
});

test("an empty query is every path, capped", () => {
  assert.deepEqual(
    fuzzyFilter(["a.ts", "b.ts", "c.ts"], "  ", 2).map((entry) => entry.path),
    ["a.ts", "b.ts"]
  );
});

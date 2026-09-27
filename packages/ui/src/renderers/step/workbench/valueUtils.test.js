import assert from "node:assert/strict";
import { test } from "node:test";

import { filterPreservingIdentity } from "./valueUtils.js";

test("selection validation retains empty and unchanged lists across new geometry ID sets", () => {
  const empty = [];
  const selected = Object.freeze(["part:a", "part:b", "part:a"]);
  const validIds = new Set(["part:a", "part:b", "part:c"]);
  assert.equal(filterPreservingIdentity(empty, id => validIds.has(id)), empty);
  assert.equal(filterPreservingIdentity(selected, id => validIds.has(id)), selected);
});

test("selection validation removes departed IDs without mutating earlier state", () => {
  const selected = Object.freeze(["departed", "kept", "departed", "kept"]);
  const next = filterPreservingIdentity(selected, id => id === "kept");
  assert.notEqual(next, selected);
  assert.deepEqual(next, ["kept", "kept"]);
  assert.deepEqual(selected, ["departed", "kept", "departed", "kept"]);
  assert.equal(filterPreservingIdentity(next, id => id === "kept"), next);
});

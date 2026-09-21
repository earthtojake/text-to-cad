import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampNumber,
  filterPreservingIdentity,
  shallowObjectValuesEqual,
  toFiniteNumber
} from "./valueUtils.js";

test("numeric value helpers preserve workspace coercion behavior", () => {
  assert.equal(toFiniteNumber("2.5", 0), 2.5);
  assert.equal(toFiniteNumber(Number.NaN, 4), 4);
  assert.equal(toFiniteNumber(Infinity, 4), 4);

  assert.equal(clampNumber("-1", 0, 5), 0);
  assert.equal(clampNumber("10", 0, 5), 5);
  assert.equal(clampNumber("3", 0, 5), 3);
});

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

test("shallowObjectValuesEqual compares own keys and strict values only", () => {
  assert.equal(shallowObjectValuesEqual({ a: 1, b: "2" }, { b: "2", a: 1 }), true);
  assert.equal(shallowObjectValuesEqual({ a: 1 }, { a: "1" }), false);
  assert.equal(shallowObjectValuesEqual({ a: 1 }, { a: 1, b: 2 }), false);
  assert.equal(shallowObjectValuesEqual(null, {}), true);
});

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampNumber,
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

test("shallowObjectValuesEqual compares own keys and strict values only", () => {
  assert.equal(shallowObjectValuesEqual({ a: 1, b: "2" }, { b: "2", a: 1 }), true);
  assert.equal(shallowObjectValuesEqual({ a: 1 }, { a: "1" }), false);
  assert.equal(shallowObjectValuesEqual({ a: 1 }, { a: 1, b: 2 }), false);
  assert.equal(shallowObjectValuesEqual(null, {}), true);
});

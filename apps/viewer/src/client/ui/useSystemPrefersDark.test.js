import assert from "node:assert/strict";
import test from "node:test";
import { readSystemPrefersDark } from "./useSystemPrefersDark.js";

test("initial app appearance observes a dark OS before the first effect", () => {
  assert.equal(readSystemPrefersDark({ matchMedia: () => ({ matches: true }) }), true);
  assert.equal(readSystemPrefersDark({ matchMedia: () => ({ matches: false }) }), false);
});

test("unavailable media queries use the light default", () => {
  assert.equal(readSystemPrefersDark(null), false);
  assert.equal(readSystemPrefersDark({}), false);
  assert.equal(readSystemPrefersDark({ matchMedia: () => { throw new Error("disabled"); } }), false);
});

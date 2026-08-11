import assert from "node:assert/strict";
import test from "node:test";

import { implicitBoundsKey, implicitModelBounds } from "./implicitFit.js";

const model = (min, max, radius = 10) => ({ bounds: { min, max }, radius });

test("implicitModelBounds copies a well-formed envelope", () => {
  const bounds = implicitModelBounds(model([-1, -2, -3], [4, 5, 6]));
  assert.deepEqual(bounds, { min: [-1, -2, -3], max: [4, 5, 6] });
});

test("implicitModelBounds rejects envelopes the fit cannot use", () => {
  assert.equal(implicitModelBounds(null), null);
  assert.equal(implicitModelBounds({}), null);
  assert.equal(implicitModelBounds(model([0, 0], [1, 1, 1])), null);
  assert.equal(implicitModelBounds(model([0, 0, Number.NaN], [1, 1, 1])), null);
  assert.equal(implicitModelBounds(model([0, 0, 0], [1, 1, Infinity])), null);
});

test("implicitBoundsKey is stable under sub-quantum drift", () => {
  // Within 2% of the radius the envelope reads as unchanged, so an animation
  // frame that only nudges the bounds does not trigger a re-fit.
  const base = implicitBoundsKey(model([0, 0, 0], [10, 10, 10], 10));
  assert.equal(base, implicitBoundsKey(model([0, 0, 0.05], [10, 10, 10.05], 10)));
  assert.notEqual(base, "");
});

test("implicitBoundsKey changes when the envelope actually moves", () => {
  const base = implicitBoundsKey(model([0, 0, 0], [10, 10, 10], 10));
  assert.notEqual(base, implicitBoundsKey(model([0, 0, 0], [10, 10, 14], 10)));
});

test("implicitBoundsKey scales its quantum with the model radius", () => {
  // The same absolute drift is significant on a small model and noise on a
  // large one; the key has to follow the model's own scale.
  const small = model([0, 0, 0], [1, 1, 1], 1);
  const smallDrifted = model([0, 0, 0], [1, 1, 1.2], 1);
  assert.notEqual(implicitBoundsKey(small), implicitBoundsKey(smallDrifted));

  const large = model([0, 0, 0], [1000, 1000, 1000], 1000);
  const largeDrifted = model([0, 0, 0], [1000, 1000, 1000.2], 1000);
  assert.equal(implicitBoundsKey(large), implicitBoundsKey(largeDrifted));
});

test("implicitBoundsKey is empty for an unusable envelope", () => {
  assert.equal(implicitBoundsKey(null), "");
  assert.equal(implicitBoundsKey({ bounds: { min: [0, 0, 0] } }), "");
});

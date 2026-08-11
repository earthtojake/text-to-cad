// The CPU evaluator must understand every GLSL builtin the SHADER understands.
//
// It is a GLSL-to-JS transpiler, and the two only agree where its builtin table is complete.
// That used to be a quiet export-time limitation; with the render package baked from this
// evaluator it is what users see, so a builtin the GPU has and this does not is a divergence
// that shows up as a failed build (`Unknown GLSL function: cosh`, which is exactly how the
// shipped `catenoid-ring-bridge` model behaved) or, worse, as different geometry.

import assert from "node:assert/strict";
import test from "node:test";

import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

/** An evaluator over a one-line body, so a builtin can be probed at a point. */
function evaluate(body) {
  const sdf = createImplicitCadSdfEvaluator({
    glslSource: `float sdf(vec3 p) { ${body} }`,
  });
  return (x, y, z) => sdf(x, y, z);
}

test("hyperbolic and inverse-trigonometric builtins evaluate", () => {
  // cosh is not hypothetical: models/implicits/catenoid-ring-bridge.implicit.js is a
  // catenoid, and a catenoid IS cosh.
  assert.ok(Math.abs(evaluate("return cosh(p.x);")(1.3, 0, 0) - Math.cosh(1.3)) < 1e-9);
  assert.ok(Math.abs(evaluate("return sinh(p.x);")(1.3, 0, 0) - Math.sinh(1.3)) < 1e-9);
  assert.ok(Math.abs(evaluate("return tanh(p.x);")(1.3, 0, 0) - Math.tanh(1.3)) < 1e-9);
  assert.ok(Math.abs(evaluate("return asin(p.x);")(0.5, 0, 0) - Math.asin(0.5)) < 1e-9);
  assert.ok(Math.abs(evaluate("return acos(p.x);")(0.5, 0, 0) - Math.acos(0.5)) < 1e-9);
});

test("common and geometric builtins evaluate", () => {
  assert.equal(evaluate("return step(1.0, p.x);")(2, 0, 0), 1);
  assert.equal(evaluate("return step(1.0, p.x);")(0.5, 0, 0), 0);
  assert.equal(evaluate("return distance(p, vec3(1.0, 0.0, 0.0));")(4, 0, 0), 3);
  assert.equal(evaluate("return trunc(p.x);")(2.9, 0, 0), 2);
  assert.equal(evaluate("return round(p.x);")(2.4, 0, 0), 2);
  assert.equal(evaluate("return exp2(p.x);")(3, 0, 0), 8);
  assert.equal(evaluate("return log2(p.x);")(8, 0, 0), 3);
  assert.equal(evaluate("return inversesqrt(p.x);")(4, 0, 0), 0.5);
  assert.ok(Math.abs(evaluate("return degrees(p.x);")(Math.PI, 0, 0) - 180) < 1e-9);
  assert.ok(Math.abs(evaluate("return radians(p.x);")(180, 0, 0) - Math.PI) < 1e-9);
});

test("builtins map componentwise over vectors, as GLSL genTypes do", () => {
  // A scalar-only implementation would silently produce NaN here rather than failing loudly.
  assert.ok(Math.abs(evaluate("return length(cosh(p));")(1, 0, 0) - Math.hypot(Math.cosh(1), 1, 1)) < 1e-9);
  assert.equal(evaluate("return length(step(vec3(1.0), p));")(2, 2, 2), Math.sqrt(3));
  assert.equal(evaluate("return reflect(vec3(1.0, -1.0, 0.0), vec3(0.0, 1.0, 0.0)).y;")(0, 0, 0), 1);
});

test("break and continue control a for-loop", () => {
  // `mandelbulb-distance-estimate.implicit.js` bails out of its orbit loop with `break`, and
  // before this it failed to mesh at all ("Unknown GLSL identifier: break") while rendering
  // fine on the GPU.
  assert.equal(
    evaluate("float n = 0.0; for (int i = 0; i < 10; i += 1) { if (i > 3) { break; } n += 1.0; } return n;")(0, 0, 0),
    4
  );
  // `continue` skips the rest of the body but still runs the update -- a `continue` that
  // skipped the update would spin until the loop guard tripped.
  assert.equal(
    evaluate("float n = 0.0; for (int i = 0; i < 6; i += 1) { if (i < 4) { continue; } n += 1.0; } return n;")(0, 0, 0),
    2
  );
  // A `return` from inside a loop keeps unwinding past the loop, unlike either signal.
  assert.equal(
    evaluate("for (int i = 0; i < 10; i += 1) { if (i == 3) { return 7.0; } } return 0.0;")(0, 0, 0),
    7
  );
});

test("an unknown function still fails loudly", () => {
  // The table is not a fallback: a name it does not have must throw rather than evaluate to
  // zero, or a model would bake silently-wrong geometry.
  assert.throws(() => evaluate("return notARealBuiltin(p.x);")(1, 1, 1), /Unknown GLSL function/);
});

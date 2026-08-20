// Focused tests for the GLSL->JS compiler's mirrored semantics -- each one targets a spot
// where idiomatic JS codegen would silently diverge from the interpreter. The corpus
// harness (sdfEquality.test.js) is the
// broad gate; these pin the individual traps with hand-built programs so a regression names
// the exact semantic it broke.

import assert from "node:assert/strict";
import test from "node:test";

import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

/** Evaluate one probe point through both backends and assert bit-equality. */
function bothWays(glslSource, point = [1.25, -0.5, 2.0]) {
  const model = { glslSource };
  const compiled = createImplicitCadSdfEvaluator(model);
  assert.equal(compiled.compiled, true, "expected the compiled path");
  process.env.IMPLICIT_SDF_FORCE_INTERPRET = "1";
  let interpreted;
  try {
    interpreted = createImplicitCadSdfEvaluator(model);
  } finally {
    delete process.env.IMPLICIT_SDF_FORCE_INTERPRET;
  }
  assert.equal(interpreted.compiled, false);
  const a = compiled(...point);
  const b = interpreted(...point);
  assert.ok(Object.is(a, b), `compiled ${a} !== interpreted ${b}`);
  return a;
}

test("&& short-circuits: the right side's side effect must not run when the left decides", () => {
  const value = bothWays(`
    float sdf(vec3 p) {
      float hits = 0.0;
      bool gate = (p.x > 1000.0) && ((hits += 1.0) > 0.0);
      return hits;
    }
  `);
  assert.equal(value, 0, "right operand ran despite a false left side");
});

test("|| short-circuits symmetrically, and runs the right side when the left is false", () => {
  const value = bothWays(`
    float sdf(vec3 p) {
      float hits = 0.0;
      bool gate = (p.x > 1000.0) || ((hits += 1.0) > 0.0);
      return hits;
    }
  `);
  assert.equal(value, 1, "right operand should have run for a false left side");
});

test("== on vectors is reference equality, exactly as the interpreter ships it", () => {
  const value = bothWays(`
    float sdf(vec3 p) {
      vec3 a = vec3(1.0, 2.0, 3.0);
      vec3 b = vec3(1.0, 2.0, 3.0);
      return (a == b) ? 1.0 : 0.0;
    }
  `);
  assert.equal(value, 0, "componentwise-equal vecs must still compare unequal by reference");
});

test("declarations are function-scoped: a branch-local variable is readable after the if", () => {
  const value = bothWays(`
    float sdf(vec3 p) {
      if (p.x > 0.0) { float t = 2.0; } else { float t = 3.0; }
      return t;
    }
  `);
  assert.equal(value, 2);
});

test("a for-loop counter leaks past its loop, var-style", () => {
  const value = bothWays(`
    float sdf(vec3 p) {
      float s = 0.0;
      for (int i = 0; i < 4; i++) { s += float(i); }
      return s + float(i);
    }
  `);
  // 0+1+2+3, plus the counter's post-loop value of 4.
  assert.equal(value, 10);
});

test("assignment clones vectors: mutating the copy must not touch the original", () => {
  const value = bothWays(`
    float sdf(vec3 p) {
      vec3 a = vec3(1.0, 2.0, 3.0);
      vec3 b = a;
      b.x = 9.0;
      return a.x;
    }
  `);
  assert.equal(value, 1, "swizzle-writing the copy reached the original -- aliasing bug");
});

test("continue still runs the loop's update expression", () => {
  const value = bothWays(`
    float sdf(vec3 p) {
      float s = 0.0;
      for (int i = 0; i < 5; i++) {
        if (i == 2) { continue; }
        s += float(i);
      }
      return s;
    }
  `);
  // 0+1+3+4 -- and the loop terminates, which is itself the update-ran proof.
  assert.equal(value, 8);
});

test("the 10,000-iteration guard throws the interpreter's message on both paths", () => {
  const source = `
    float sdf(vec3 p) {
      float s = 0.0;
      for (int i = 0; i >= 0; i++) { s += 1.0; }
      return s;
    }
  `;
  const compiled = createImplicitCadSdfEvaluator({ glslSource: source });
  assert.equal(compiled.compiled, true);
  assert.throws(() => compiled(0, 0, 0), /exceeded exporter safety limit/);
  process.env.IMPLICIT_SDF_FORCE_INTERPRET = "1";
  try {
    const interpreted = createImplicitCadSdfEvaluator({ glslSource: source });
    assert.throws(() => interpreted(0, 0, 0), /exceeded exporter safety limit/);
  } finally {
    delete process.env.IMPLICIT_SDF_FORCE_INTERPRET;
  }
});

test("uniforms are captured and cast once, and shadow nothing", () => {
  const model = {
    glslSource: "float sdf(vec3 p) { return length(p) - radius; }",
    uniforms: { radius: { type: "float", value: 3 } },
  };
  const compiled = createImplicitCadSdfEvaluator(model);
  assert.equal(compiled.compiled, true);
  assert.equal(compiled(5, 0, 0), 2);
});

test("an unparseable source falls back rather than compiling", () => {
  // `while` is outside the parser's language; BOTH backends must reject it the same way --
  // the compiler by declining (fallback), the interpreter by throwing at creation.
  const model = { glslSource: "float sdf(vec3 p) { while (true) { } return 1.0; }" };
  assert.throws(() => createImplicitCadSdfEvaluator(model));
});

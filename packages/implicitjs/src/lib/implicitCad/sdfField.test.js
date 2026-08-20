// THE FIELD-AGREEMENT GATE.
//
// An implicit model is authored ONCE, in GLSL, and evaluated TWICE by unrelated code:
//
//   GPU raymarch  render.js: IMPLICIT_CAD_GLSL_LIBRARY
//                          + normalizeImplicitCadGlslFloatLiterals(model.glslSource)
//   CPU meshing   sdfEvaluator.js: the BUILTINS table -- the same ~60 helpers, hand-written a
//                          second time in JS -- over the RAW model.glslSource
//
// Until phase 2 the CPU side only ran on export. It is now what bakes the render artifact, so
// it is what users see, and §7.2 records that the two have diverged before (the normalizer has
// mangled `1.0e-6` and `i == 0`; the builtin table was missing `cosh` and 15 others; `break`
// and `continue` did not parse). Every one of those shipped.
//
// WHY A FIELD DIFF AND NOT A PERCEPTUAL DIFF
// -----------------------------------------
// §9 originally proposed rendering the baked GLB against the raymarch and diffing pixels. Two
// reasons that is the weaker instrument, and one reason it cannot gate at all:
//   * A pixel diff answers "something changed". This answers "sdf disagrees at (x,y,z) by d",
//     which localizes to an expression. The library sweep below narrows further, to a single
//     helper and the arguments that break it.
//   * A pixel diff is downstream of meshing, shading, camera, and tone mapping, so it also
//     fires on changes that are not field divergence, and it can MISS field divergence hidden
//     by shading.
//   * CI has no browser (nothing runs `playwright install`), so a render-based check would
//     skip in CI -- and a gate that skips is not a gate. The visual pass stays non-gating
//     (§10.3).
//
// WHAT THIS CANNOT SEE (deliberate, stated rather than implied)
// ------------------------------------------------------------
//   * float32. Both sides here are float64; the shader is `highp`. Divergence from rounding
//     alone is ~1e-7 relative, well under this file's tolerance, so this gate is blind to it.
//   * GLSL `int` semantics, including truncating integer division, and int/float type errors
//     that fail to COMPILE (the `i == 0` -> `i == 0.0` class). `sdfFieldReference.js` models
//     ints as JS numbers exactly as `sdfEvaluator.js` does, so a mistake there is a blind spot
//     the two share rather than a disagreement between them. The token-equivalence test below
//     catches the structural half of that class; the compile half needs a real GL context
//     (`sdfFieldGpu.test.js`, opt-in).
// Both belong to the non-gating GPU tier, not here.
//
// WHAT IT COVERS
// -------------
//   1. the float-literal normalizer, by token equivalence, on all 43 models and on adversarial
//      literal shapes the corpus does not happen to contain
//   2. the shader's GLSL helper library against the JS builtin table, every function, every
//      overload, 4000 fuzzed argument tuples each -- including helpers no model calls
//   3. the field itself, sdfEvaluator vs the shader's own GLSL, 128 fixed points x 43 models
//   4. the language boundary: no JS builtin and no model call that GLSL ES 1.00 lacks. This is
//      what found the live `cosh` bug recorded further down.
// ~9 s total. All 43 models, including menger-sponge, which has no surface but does have a
// perfectly well-defined field.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { loadImplicitCadModelFromPath } from "./export.js";
import {
  IMPLICIT_CAD_GLSL_LIBRARY,
  normalizeImplicitCadGlslFloatLiterals
} from "./render.js";
import { createImplicitCadSdfEvaluator, implicitSdfEvaluatorInternals } from "./sdfEvaluator.js";
import { createReferenceSdfEvaluator, sdfFieldReferenceInternals } from "./sdfFieldReference.js";

const { BUILTINS, tokenize } = implicitSdfEvaluatorInternals;
const { OverloadParser, createInterpreter } = sdfFieldReferenceInternals;

const MODELS_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../..",
  "models/implicits"
);

/** Sampling budget. Fixed, not adaptive: the gate must sample the same points on every run,
 *  on every machine. 128 points x 43 models is ~7 s, the library sweep ~2 s. The corpus's
 *  per-sdf() cost spans 306x (§0.0), so the three space-filling-curve models account for most
 *  of that; raising this is affordable but buys little, since a divergence in a shared helper
 *  shows up in the first handful of samples. */
const SAMPLES_PER_MODEL = 128;
const LIBRARY_TRIALS_PER_OVERLOAD = 4000;
const SAMPLE_SEED = 0x5eed;
const LIBRARY_SEED = 0xabcdef;

/** Observed worst disagreement across the corpus is 2.6e-15 relative -- float64 rounding
 *  through two different expression orderings. 1e-9 is six orders of magnitude above that and
 *  still far below any semantic difference, which shows up as a visible fraction of a
 *  millimetre or as NaN. */
const RELATIVE_TOLERANCE = 1e-9;

/** models/implicits/menger-sponge.implicit.js is a MODEL defect, not an evaluator one: its sdf
 *  is >= 2.77 everywhere inside its own declared bounds, because the `cross` term never goes
 *  negative, so it has no surface to mesh -- and none to raymarch on the GPU either (§0.0).
 *  Its FIELD is still perfectly well defined, so it is NOT skipped by the agreement tests --
 *  all 43 models are compared, not the 42 that bake. The one thing it cannot satisfy is a
 *  statement about the model rather than the evaluator, and that is pinned as its own test at
 *  the bottom of this file rather than waved past with a skip. */
const MODELS_WITHOUT_A_SURFACE = new Map([
  [
    "menger-sponge.implicit.js",
    "known model defect: sdf >= 2.77 everywhere inside its own declared bounds (the `cross` "
    + "term never goes negative), so it has no surface on the GPU either",
  ],
]);

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Models the CPU evaluator cannot run at all, and why. These checks compare the CPU field
// against the shader, so a model the CPU cannot evaluate has nothing to compare -- skipping
// is honest, whereas asserting would just pin a known gap as a failure forever. They render
// correctly (the GPU handles `inout` natively); it is baking/export that is blocked. Listed
// by name rather than detected silently, so the list cannot quietly grow.
const CPU_UNSUPPORTED = new Set([
  // `inout` parameters need write-back into the caller's variable; the evaluator passes by
  // value and refuses rather than return wrong geometry. See sdfEvaluator's inout guard.
  "small-stellated-dodecahedron.implicit.js",
  "stellated-icosahedron.implicit.js",
]);

function modelFiles() {
  const files = fs.readdirSync(MODELS_DIR)
    .filter((name) => name.endsWith(".implicit.js"))
    .sort();
  assert.ok(files.length >= 43, `expected the implicit corpus at ${MODELS_DIR}, found ${files.length} models`);
  return files.filter((name) => !CPU_UNSUPPORTED.has(name));
}

/** The bounds' eight corners and centre, then a deterministic uniform fill. Corners are worth
 *  pinning explicitly: they are where a model's domain repetition and its guards are most
 *  likely to sit on an edge case, and a purely random set reaches them with probability 0. */
function samplePoints(bounds, count) {
  const { min, max } = bounds;
  const points = [];
  for (let corner = 0; corner < 8; corner += 1) {
    points.push([0, 1, 2].map((axis) => ((corner >> axis) & 1 ? max : min)[axis]));
  }
  points.push([0, 1, 2].map((axis) => (min[axis] + max[axis]) / 2));
  const random = mulberry32(SAMPLE_SEED);
  while (points.length < count) {
    points.push([0, 1, 2].map((axis) => min[axis] + (max[axis] - min[axis]) * random()));
  }
  return points;
}

function relativeError(a, b) {
  if (Number.isNaN(a) && Number.isNaN(b)) {
    return 0;
  }
  if (Number.isNaN(a) !== Number.isNaN(b)) {
    return Infinity;
  }
  if (a === b) {
    return 0;
  }
  return Math.abs(a - b) / Math.max(1, Math.abs(a), Math.abs(b));
}

const loadedModels = new Map();

async function modelFor(file) {
  if (!loadedModels.has(file)) {
    loadedModels.set(file, await loadImplicitCadModelFromPath(path.join(MODELS_DIR, file)));
  }
  return loadedModels.get(file);
}

/* ------------------------------------------------------------------------------------- */

test("the shader's float-literal normalizer rewrites nothing but literal values", async (t) => {
  // The normalizer runs on the GPU's copy of the source and NOT on the CPU evaluator's, so it
  // is a divergence surface all by itself: whatever it does to the text, the two evaluators
  // stop seeing the same program. Its only licensed edit is promoting an integer literal to
  // the float literal of the SAME value. Comparing token streams says that independently of
  // how it is implemented -- and it is exactly what `1.0e-6` -> `1.0e-6.0` fails, because the
  // trailing `.0` re-lexes as a member access on a number.
  for (const file of modelFiles()) {
    await t.test(file, async () => {
      const model = await modelFor(file);
      const raw = String(model.glslSource);
      const normalized = normalizeImplicitCadGlslFloatLiterals(raw);
      const before = tokenize(raw);
      const after = tokenize(normalized);
      assert.equal(
        after.length,
        before.length,
        `${file}: normalization changed the token count (${before.length} -> ${after.length}); `
        + "a promotion must never add or remove a token"
      );
      for (let index = 0; index < before.length; index += 1) {
        const from = before[index];
        const to = after[index];
        assert.equal(
          to.type,
          from.type,
          `${file}: token ${index} changed type, ${from.type} "${from.value}" -> ${to.type} "${to.value}"`
        );
        assert.equal(
          to.value,
          from.value,
          `${file}: token ${index} changed value, ${from.type} "${from.value}" -> "${to.value}"`
        );
      }
      assert.equal(
        normalizeImplicitCadGlslFloatLiterals(normalized),
        normalized,
        `${file}: normalization is not idempotent, so it is rewriting something it already rewrote`
      );
    });
  }
});

test("the normalizer survives the literal shapes it has broken before", async (t) => {
  // The corpus cannot carry this check on its own: NO model in models/implicits currently
  // contains a negative-exponent literal, so the guard that protects `1.0e-6` can be deleted
  // outright and all 43 models still pass. Verified by deleting it. These synthetic sources
  // are therefore the regression pin, and they are written to FAIL loudly if it goes:
  // `1.0e-6` normalizes to `1.0e-6.0`, whose trailing `.0` re-lexes as a member access on a
  // number, so the token stream changes and the reference program stops parsing at all.
  const sources = new Map([
    ["negative exponent", "float sdf(vec3 p) { float eps = 1.0e-6; return length(p) - 1.0 + eps; }"],
    ["negative exponent, no mantissa point", "float sdf(vec3 p) { return length(p) - 1e-3; }"],
    ["positive exponent", "float sdf(vec3 p) { return length(p) - 1.0e+1 + 2e2; }"],
    // An int compared against an integer literal. Token equivalence holds here whether or not
    // the literal is promoted -- `0` and `0.0` lex to the same NUMBER -- so this case pins the
    // structural half only. Promoting it produces `i == 0.0`, which is a GLSL type error and
    // fails to COMPILE, and no CPU-side instrument can see that; the GPU tier owns it.
    ["int compared to a literal", "float sdf(vec3 p) { float n = 0.0; for (int i = 0; i < 4; i += 1) { if (i == 0) { n += 1.0; } } return length(p) - n; }"],
    ["literals as call arguments", "float sdf(vec3 p) { return implicit_sphere(p, vec3(0, 1, 2), 3); }"],
  ]);

  for (const [label, glslSource] of sources) {
    await t.test(label, () => {
      const normalized = normalizeImplicitCadGlslFloatLiterals(glslSource);
      const before = tokenize(glslSource);
      const after = tokenize(normalized);
      assert.equal(after.length, before.length, `${label}: normalized to ${JSON.stringify(normalized)}`);
      for (let index = 0; index < before.length; index += 1) {
        assert.equal(after[index].type, before[index].type, `${label}: token ${index} changed type`);
        assert.equal(after[index].value, before[index].value, `${label}: token ${index} changed value`);
      }
      // And the whole chain, not just the text: both evaluators must still build and agree.
      const model = { glslSource, uniforms: {} };
      const subject = createImplicitCadSdfEvaluator(model);
      const reference = createReferenceSdfEvaluator(model);
      for (const point of [[0.3, -1.7, 2.1], [0, 0, 0], [12, 5, -8]]) {
        assert.ok(
          relativeError(subject(...point), reference(...point)) <= RELATIVE_TOLERANCE,
          `${label}: ${subject(...point)} vs ${reference(...point)} at ${point}`
        );
      }
    });
  }
});

test("the shader's GLSL helper library and the CPU builtin table are the same library", async (t) => {
  const library = new OverloadParser(tokenize(IMPLICIT_CAD_GLSL_LIBRARY)).parseProgram();
  const glslNames = [...library.functions.keys()].sort();

  await t.test("every GLSL helper has a JS builtin", () => {
    const missing = glslNames.filter((name) => !BUILTINS[name]);
    assert.deepEqual(
      missing,
      [],
      `these helpers exist on the GPU but not in sdfEvaluator's BUILTINS, so a model using one `
      + `renders and then fails to mesh -- exactly how catenoid-ring-bridge behaved before cosh `
      + `was added: ${missing.join(", ")}`
    );
  });

  await t.test("every JS builtin that claims to be a helper has a GLSL body", () => {
    const extra = Object.keys(BUILTINS)
      .filter((name) => name.startsWith("implicit_") && !library.functions.has(name))
      .sort();
    // The reverse direction is the quieter failure: a model calling one of these MESHES and
    // then fails to compile on the GPU. `implicit_diamond` is a JS stub returning 0 with no
    // GLSL counterpart -- pinned here so it stays a known, single, unused entry.
    assert.deepEqual(
      extra,
      ["implicit_diamond"],
      `JS-only helper(s) changed: ${extra.join(", ")}. A model calling one would mesh but not `
      + "compile on the GPU; either give it a GLSL body in IMPLICIT_CAD_GLSL_LIBRARY or delete it"
    );
  });

  const interpreter = createInterpreter(library.functions, null);
  const width = (type) => (type === "vec2" ? 2 : type === "vec3" ? 3 : type === "vec4" ? 4 : 1);

  for (const name of glslNames) {
    if (!BUILTINS[name]) {
      continue;
    }
    const overloads = library.functions.get(name);
    for (let index = 0; index < overloads.length; index += 1) {
      const overload = overloads[index];
      const signature = `${name}(${overload.params.map((param) => param.type).join(", ")})`;
      await t.test(signature, () => {
        const random = mulberry32(LIBRARY_SEED ^ (index * 7919));
        // A spread of magnitudes, exact integers, and exact zeros, because the helpers branch
        // on sign and on zero radii.
        //
        // ONE class of input is excluded on purpose, and it is a real difference rather than a
        // convenience: a degenerate SHAPE VECTOR -- a plane with a zero normal, a honeycomb
        // with a zero-height cell, an axis with no direction. GLSL's `normalize` and `mod`
        // produce NaN there; the JS table guards `normalize` below 1e-12 and returns the zero
        // vector, so the two disagree by construction at every such input. Only a broken model
        // reaches one (a zero normal is not a plane), and letting it fire on every trial would
        // bury the divergences that matter. The FIRST argument is the sample point, where a
        // zero component is ordinary, so it keeps them.
        const component = (allowZero) => {
          const value = random() * 4 - 2;
          const shape = random();
          if (shape < 0.08) {
            return allowZero ? 0 : 0.5;
          }
          return shape < 0.16 ? Math.round(value) || 1 : value * (shape < 0.5 ? 1 : 10);
        };
        const argument = (type, position) => {
          const allowZero = position === 0;
          const size = width(type);
          return size === 1
            ? component(true)
            : Array.from({ length: size }, () => component(allowZero));
        };

        for (let trial = 0; trial < LIBRARY_TRIALS_PER_OVERLOAD; trial += 1) {
          const args = overload.params.map((param, position) => argument(param.type, position));
          const fromGlsl = interpreter.callFunction(name, args);
          const fromJs = BUILTINS[name](...args);
          const glsl = Array.isArray(fromGlsl) ? fromGlsl : [fromGlsl];
          const js = Array.isArray(fromJs) ? fromJs : [fromJs];
          assert.equal(
            js.length,
            glsl.length,
            `${signature}: the JS builtin returned ${js.length} components, the GLSL body ${glsl.length}`
          );
          for (let axis = 0; axis < glsl.length; axis += 1) {
            const error = relativeError(Number(js[axis]), Number(glsl[axis]));
            assert.ok(
              error <= RELATIVE_TOLERANCE,
              `${signature} disagrees between render.js's GLSL body and sdfEvaluator.js's JS`
              + ` builtin.\n  args      ${JSON.stringify(args)}\n  js        ${JSON.stringify(fromJs)}`
              + `\n  glsl      ${JSON.stringify(fromGlsl)}\n  component ${axis}, relative error ${error}`
            );
          }
        }
      });
    }
  }
});

/* ---------------------------------------------------------------------------------------
 * A LIVE BUG THIS GATE FOUND. Read this before touching the two pins below.
 *
 * `sdfEvaluator.js`'s builtin table says, in a comment, that its GLSL builtins "are not new
 * capability -- every one of them is already legal in a model's shader, so a model using one
 * rendered fine and then failed the moment it was MESHED". For nine of them that is FALSE.
 *
 * The shader is GLSL ES 1.00 (a three.js `ShaderMaterial` with no `glslVersion`, so no
 * `#version` directive, in a WebGL1 *or* WebGL2 context). `sinh`, `cosh`, `tanh`, `asinh`,
 * `acosh`, `atanh`, `trunc`, `round` and `roundEven` were added in GLSL ES 3.00 and do not
 * exist in 1.00. A model calling one does not "render fine": its shader does not COMPILE.
 *
 *   models/implicits/catenoid-ring-bridge.implicit.js -- a catenoid, and a catenoid IS cosh --
 *   fails with `ERROR: 0:509: 'cosh' : no matching overloaded function found`, confirmed in
 *   both a webgl and a webgl2 context (see sdfFieldGpu.test.js). It renders as nothing today.
 *
 * Phase 2 added `cosh` to the JS table so the model would MESH. That half is right and should
 * stay -- but it means the model now bakes a render artifact from a field the GPU has never
 * been able to evaluate, which is the exact failure mode §7.2 is about, inverted.
 *
 * THE FIX (not done here; it is a change to the shipped shader, not to a test): give
 * IMPLICIT_CAD_GLSL_LIBRARY ES-1.00 polyfills for the nine, as genType overloads --
 * cosh(x) = (exp(x) + exp(-x)) * 0.5, trunc(x) = sign(x) * floor(abs(x)),
 * round(x) = floor(x + 0.5), and so on. The library sweep above will then verify each polyfill
 * against its JS twin automatically, and both lists below collapse to empty.
 *
 * Until then the two pins record the exact, complete extent of the breakage. THEY MUST ONLY
 * EVER SHRINK. A new entry in either is a new model that renders as nothing.
 * ------------------------------------------------------------------------------------- */

/** GLSL ES 1.00, spec section 8 plus the constructors. Frozen: this is the language the shader
 *  is actually written in, and it does not change. */
const GLSL_ES_100_BUILTINS = new Set([
  "radians", "degrees", "sin", "cos", "tan", "asin", "acos", "atan",
  "pow", "exp", "log", "exp2", "log2", "sqrt", "inversesqrt",
  "abs", "sign", "floor", "ceil", "fract", "mod", "min", "max", "clamp", "mix", "step",
  "smoothstep",
  "length", "distance", "dot", "cross", "normalize", "faceforward", "reflect", "refract",
  "matrixCompMult",
  "lessThan", "lessThanEqual", "greaterThan", "greaterThanEqual", "equal", "notEqual",
  "any", "all", "not",
  "texture2D", "texture2DProj", "texture2DLod", "texture2DProjLod", "textureCube",
  "textureCubeLod",
  "float", "int", "bool",
  "vec2", "vec3", "vec4", "ivec2", "ivec3", "ivec4", "bvec2", "bvec3", "bvec4",
  "mat2", "mat3", "mat4",
]);

/** The nine above, exactly. */
const JS_BUILTINS_THE_SHADER_CANNOT_COMPILE = [
  "acosh", "asinh", "atanh", "cosh", "round", "roundEven", "sinh", "tanh", "trunc",
];

/** Every model that calls one. */
const MODELS_THAT_DO_NOT_COMPILE = [
  "catenoid-ring-bridge.implicit.js calls cosh",
];

function collectCalledFunctionNames(node, into = new Set()) {
  if (!node || typeof node !== "object") {
    return into;
  }
  if (Array.isArray(node)) {
    for (const child of node) {
      collectCalledFunctionNames(child, into);
    }
    return into;
  }
  if (node.type === "call" && node.callee?.type === "identifier") {
    into.add(node.callee.name);
  }
  for (const value of Object.values(node)) {
    collectCalledFunctionNames(value, into);
  }
  return into;
}

test("the CPU builtin table claims no builtin the GLSL ES 1.00 shader lacks", () => {
  const offenders = Object.keys(BUILTINS)
    .filter((name) => !name.startsWith("implicit_"))
    .filter((name) => !GLSL_ES_100_BUILTINS.has(name))
    .sort();
  assert.deepEqual(
    offenders,
    JS_BUILTINS_THE_SHADER_CANNOT_COMPILE,
    "This list must only ever SHRINK -- see the comment above it. Each entry is a builtin the "
    + "CPU evaluator will happily mesh with and the shader cannot compile at all, so a model "
    + "using it bakes geometry from a field that never rendered."
  );
});

test("no model calls a function its own shader cannot compile", async (t) => {
  const library = new OverloadParser(tokenize(IMPLICIT_CAD_GLSL_LIBRARY)).parseProgram();
  const offenders = [];
  for (const file of modelFiles()) {
    await t.test(file, async () => {
      const model = await modelFor(file);
      const program = new OverloadParser(tokenize(String(model.glslSource))).parseProgram();
      const called = collectCalledFunctionNames([...program.functions.values()]);
      for (const name of [...called].sort()) {
        if (GLSL_ES_100_BUILTINS.has(name) || library.functions.has(name) || program.functions.has(name)) {
          continue;
        }
        offenders.push(`${file} calls ${name}`);
      }
    });
  }
  assert.deepEqual(
    offenders,
    MODELS_THAT_DO_NOT_COMPILE,
    "This list must only ever SHRINK -- see the comment above it. Each entry is a model whose "
    + "fragment shader does not compile, so it renders as nothing while still meshing happily "
    + "on the CPU."
  );
});

test("no model shadows a builtin helper name", async (t) => {
  // sdfEvaluator.js resolves BUILTINS before program functions, the GPU resolves the program's
  // own definition. A model that defines `float implicit_sphere(...)` would therefore mesh
  // with the library's version and render with its own, silently.
  for (const file of modelFiles()) {
    await t.test(file, async () => {
      const model = await modelFor(file);
      const program = new OverloadParser(tokenize(String(model.glslSource))).parseProgram();
      const shadowed = [...program.functions.keys()].filter((name) => Boolean(BUILTINS[name])).sort();
      assert.deepEqual(
        shadowed,
        [],
        `${file} defines ${shadowed.join(", ")}, which the CPU evaluator resolves to its own `
        + "builtin instead -- rename the model's function"
      );
    });
  }
});

test("the CPU evaluator agrees with the shader's GLSL on every model's field", async (t) => {
  for (const file of modelFiles()) {
    await t.test(file, async () => {
      const model = await modelFor(file);
      const subject = createImplicitCadSdfEvaluator(model);
      const reference = createReferenceSdfEvaluator(model);
      const points = samplePoints(model.bounds, SAMPLES_PER_MODEL);

      let worstError = -1;
      let worstAt = points[0];
      let worstPair = [NaN, NaN];
      const cpuValues = [];
      for (const point of points) {
        const fromCpu = subject(point[0], point[1], point[2]);
        const fromGlsl = reference(point[0], point[1], point[2]);
        cpuValues.push(fromCpu);
        const error = relativeError(fromCpu, fromGlsl);
        if (error > worstError) {
          worstError = error;
          worstAt = point;
          worstPair = [fromCpu, fromGlsl];
        }
      }

      // Agreement alone would be satisfied by two evaluators that are broken identically, so
      // the same pass also asks whether the field is a field at all. NOT "it changes sign",
      // which §10.3 first proposed: a sparse sample misses the interior of a thin model
      // outright -- gosper-curve-tube's minimum over these points is +0.08 and
      // dragon-folding-path-3d's is +0.82, both good tube models whose walls are simply
      // thinner than the sample spacing. Sign is only decidable at meshing density, and a gate
      // that fails on sampling luck is worse than no gate.
      assert.ok(
        cpuValues.every((value) => Number.isFinite(value)),
        `${file}: the field is not finite everywhere inside its own bounds`
      );
      // The evaluator substitutes 1e6 for a non-finite result, so a field that has gone NaN
      // everywhere arrives here as a finite CONSTANT rather than as NaN -- which is what makes
      // "varies" the load-bearing half.
      assert.ok(
        Math.max(...cpuValues) > Math.min(...cpuValues),
        `${file}: the field is constant (${cpuValues[0]}) across the model's own bounds, so `
        + "either the source no longer reads `p` or every evaluation is failing into the 1e6 fallback"
      );

      assert.ok(
        worstError <= RELATIVE_TOLERANCE,
        `${file}: the baked CPU field disagrees with the field the GPU raymarches.\n`
        + `  point            (${worstAt.map((value) => value.toFixed(6)).join(", ")})\n`
        + `  sdfEvaluator.js  ${worstPair[0]}\n`
        + `  shader GLSL      ${worstPair[1]}\n`
        + `  relative error   ${worstError}\n`
        + "  The baked render artifact is built from the first number; users see geometry that\n"
        + "  is not the model they authored. Localize it with the helper-library sweep above,\n"
        + "  then fix the evaluator -- do not widen this tolerance."
      );
    });
  }
});

test("menger-sponge is still the one model with no surface inside its own bounds", async () => {
  // The corpus is 43 models and 42 of them bake. This is the 43rd, and the reason it is skipped
  // by the builder is a MODEL defect rather than an evaluator one, so it is pinned rather than
  // waved past: if someone repairs the model, this test is what tells them to take it off the
  // skip list. It also proves the skip reason itself is still true, which a bare skip cannot.
  const [file, reason] = [...MODELS_WITHOUT_A_SURFACE.entries()][0];
  const model = await modelFor(file);
  const subject = createImplicitCadSdfEvaluator(model);
  const { min, max } = model.bounds;
  const steps = 16;
  let lowest = Infinity;
  for (let ix = 0; ix < steps; ix += 1) {
    for (let iy = 0; iy < steps; iy += 1) {
      for (let iz = 0; iz < steps; iz += 1) {
        const point = [ix, iy, iz].map(
          (index, axis) => min[axis] + ((max[axis] - min[axis]) * index) / (steps - 1)
        );
        lowest = Math.min(lowest, subject(point[0], point[1], point[2]));
      }
    }
  }
  assert.ok(
    lowest > 2.5,
    `${file} now reaches ${lowest} inside its own bounds. If it has gained a surface the defect `
    + `is fixed -- remove it from MODELS_WITHOUT_A_SURFACE and from the builder's skip list. `
    + `Recorded reason: ${reason}`
  );
});

// The equality gate for the implicit SDF corpus.
//
// Its whole job is to make "this optimisation did not change any model" a MEASURED fact
// rather than a claim. Every model under `models/implicits/` is evaluated at a fixed set of
// points and reduced to a digest of the raw IEEE-754 bytes; the digest is compared against a
// committed baseline and must match EXACTLY.
//
// Two digests, because the two comparisons this file makes are not the same comparison.
//
// `compiled === interpreted` happens inside ONE process on ONE machine, so it is bit-exact over
// raw Float64 bytes and stays that way: those two paths have no legitimate reason to move a
// single bit, and a tolerance there would be indistinguishable from a subtle semantic
// regression in the transpiler, the class of bug this gate exists to catch.
//
// The COMMITTED baseline crosses machines, where bit-exactness is not available to be had: the
// same corpus on darwin/arm64 and linux/x64 (same V8) diverges on 31 of 45 models at ulp scale.
// That comparison narrows to Float32 first -- see stableDigestOf for why that, and not
// significant-figure rounding.
//
// Digesting bytes rather than comparing numbers gives `Object.is` semantics for free, in both
// widths: -0 and 0 have different bit patterns, and NaN compares equal to itself. A plain `===`
// sweep would silently accept both of those changes.
//
// To re-baseline after an INTENTIONAL change:
//   IMPLICIT_SDF_BASELINE_WRITE=1 npm --prefix packages/implicitjs test -- src/lib/implicitCad/sdfEquality.test.js
// Re-baselining is a deliberate act; it should appear in a diff and be justified in review.

import assert from "node:assert/strict";
import test from "node:test";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { normalizeImplicitCadModel } from "./model.js";
import { createImplicitCadColorEvaluator, createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = path.resolve(HERE, "..", "..", "..");
const REPO_ROOT = path.resolve(PACKAGE_ROOT, "..", "..");
const CORPUS_DIR = path.join(REPO_ROOT, "models", "implicits");
const BASELINE_PATH = path.join(HERE, "__baselines__", "sdfEquality.json");

// `implicitjs` is vendored into skill runtimes standalone, where the repo's model corpus does
// not exist. Skipping there is correct: the gate guards the repo's models, and a vendored
// copy has none to guard.
const HAS_CORPUS = fs.existsSync(CORPUS_DIR);
const WRITE_BASELINE = process.env.IMPLICIT_SDF_BASELINE_WRITE === "1";

// Deterministic point count. High enough that a change confined to one GLSL construct still
// lands on it; the sweep is O(models x points) against SDFs costing up to ~3ms/call, so
// raising it further buys little and costs a lot.
const LATTICE_STEPS = 9;                 // 9^3 = 729 structured points
const RANDOM_POINTS = 1400;              // + seeded scatter
const TOTAL_POINTS = LATTICE_STEPS ** 3 + RANDOM_POINTS;

// mulberry32 -- small, fast, and fully determined by its seed, so the point set is identical
// on every machine and every run. Math.random() would make the baseline meaningless.
function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Points span the model's own bounds, slightly overshooting them: behaviour OUTSIDE the
// declared box is still part of the SDF's contract (the mesher samples the boundary planes)
// and is exactly where a mishandled early-return would show up.
function samplePoints(model) {
  const { min, max } = model.bounds;
  const pad = 0.05;
  const lo = [0, 1, 2].map((i) => min[i] - (max[i] - min[i]) * pad);
  const hi = [0, 1, 2].map((i) => max[i] + (max[i] - min[i]) * pad);
  const at = (axis, t) => lo[axis] + (hi[axis] - lo[axis]) * t;

  const points = [];
  for (let ix = 0; ix < LATTICE_STEPS; ix += 1) {
    for (let iy = 0; iy < LATTICE_STEPS; iy += 1) {
      for (let iz = 0; iz < LATTICE_STEPS; iz += 1) {
        const d = LATTICE_STEPS - 1;
        points.push([at(0, ix / d), at(1, iy / d), at(2, iz / d)]);
      }
    }
  }

  const random = seededRandom(0x5eed1234);
  for (let index = 0; index < RANDOM_POINTS; index += 1) {
    points.push([at(0, random()), at(1, random()), at(2, random())]);
  }
  return points;
}

// Normals for color(p, normal). Deterministic and varied -- a fixed [0,0,1] would leave any
// normal-dependent branch in a model's color() untested.
function sampleNormals(count) {
  const random = seededRandom(0xc01c0de);
  const normals = [];
  for (let index = 0; index < count; index += 1) {
    const x = random() * 2 - 1;
    const y = random() * 2 - 1;
    const z = random() * 2 - 1;
    const length = Math.hypot(x, y, z) || 1;
    normals.push([x / length, y / length, z / length]);
  }
  return normals;
}

// EXACT -- the raw Float64 bytes. Used only where both sides are produced in the SAME process
// on the same machine, where exactness is both meaningful and free.
function digestOf(values) {
  const floats = Float64Array.from(values);
  return crypto.createHash("sha256").update(Buffer.from(floats.buffer)).digest("hex");
}

// STABLE -- the same values narrowed to Float32 first. Used for the COMMITTED baseline, the one
// comparison that crosses machines.
//
// It has to, because the last bits of a double are not portable: evaluating this corpus on
// linux/x64 and on darwin/arm64 (same V8, 12.4.254.21) diverges on 31 of 45 models. The
// divergence is invisible in the first six values of every model, so it is ulp-scale noise in
// libm-backed operations, not a semantic difference -- but a digest is all-or-nothing, so
// ulp-scale noise reddens the whole entry.
//
// Float32 rather than rounding to N significant figures, which was the obvious fix and is a
// trap: rounding is discontinuous, so it erases a 1-ulp difference EXCEPT when the value sits
// near a rounding boundary, where it preserves it. Over ~300k sampled values that is tens of
// expected straddles -- a gate that goes green and then flakes. Narrowing to Float32 has the
// same discontinuity in principle, but the gap between float32 and float64 precision is ~1e-9
// relative, so a 1-ulp double perturbation straddles a float32 boundary with probability ~1e-9
// per value: ~3e-4 across the whole corpus, and it would be reproducible rather than flaky.
//
// What it costs: sensitivity to changes below ~1e-7 relative, which are exactly the changes we
// are now forced to tolerate anyway. A real semantic regression -- a wrong branch, a dropped
// clamp, an inverted operator -- moves values by vastly more. Float32 keeps the Object.is
// properties the exact digest was chosen for: -0 and 0 stay distinct, NaN stays NaN.
//
// The bit-exact gate has not been weakened, only aimed at the comparison it fits: `compiled ===
// interpreted` below is still raw Float64 bytes with zero tolerance.
function stableDigestOf(values) {
  const floats = Float32Array.from(values);
  return crypto.createHash("sha256").update(Buffer.from(floats.buffer)).digest("hex");
}

function evaluateModel(model) {
  const points = samplePoints(model);
  const normals = sampleNormals(points.length);

  const sdf = createImplicitCadSdfEvaluator(model);
  const distances = points.map(([x, y, z]) => sdf(x, y, z));
  // COVERAGE GATE for the GLSL->JS compiler. The
  // compiler falls back to the interpreter silently on any problem -- correct for
  // production, but in the corpus it must be a loud failure: a codegen regression that
  // falls back everywhere keeps every digest green while the speedup silently vanishes.
  const compiled = sdf.compiled === true;

  // DIFFERENTIAL GATE: the same points through the interpreter, bit-compared below. The
  // frozen baseline already pins the interpreter; this pins compiled === interpreted even
  // when the baseline is being deliberately re-cut.
  process.env.IMPLICIT_SDF_FORCE_INTERPRET = "1";
  let interpretedDigest;
  try {
    const interpreted = createImplicitCadSdfEvaluator(model);
    interpretedDigest = digestOf(points.map(([x, y, z]) => interpreted(x, y, z)));
  } finally {
    delete process.env.IMPLICIT_SDF_FORCE_INTERPRET;
  }

  let colorDigest = null;
  let colorSample = null;
  try {
    const color = createImplicitCadColorEvaluator(model);
    const channels = [];
    points.forEach((point, index) => {
      channels.push(...color(point, normals[index]));
    });
    colorDigest = stableDigestOf(channels);
    colorSample = channels.slice(0, 6);
  } catch {
    // A model without a color() function is legitimate; absence is recorded as null and is
    // itself part of the baseline, so a model GAINING or LOSING colour is a failure.
    colorDigest = null;
  }

  return {
    points: points.length,
    compiled,
    interpretedDigest,
    // Same values, two digests: the exact one is compared against `interpretedDigest` in this
    // process; the stable one is what the committed baseline holds.
    exactDigest: digestOf(distances),
    sdfDigest: stableDigestOf(distances),
    // A few raw values make a digest mismatch diagnosable instead of merely red.
    sdfSample: distances.slice(0, 6),
    colorDigest,
    colorSample,
  };
}

// Models the CPU evaluator refuses outright, and why. Baselining a model whose evaluation
// throws would record the throw as the expectation; excluding it keeps the baseline a
// statement about fields we can actually compute. Named rather than detected, so this stays
// a short list somebody has to edit on purpose.
const CPU_UNSUPPORTED = new Set([
  // `inout` parameters need write-back into the caller's variable, which the evaluator does
  // not implement -- it rejects instead of returning wrong geometry. GPU rendering is fine.
  "small-stellated-dodecahedron.implicit.js",
  "stellated-icosahedron.implicit.js",
]);

function corpusModelPaths() {
  return fs
    .readdirSync(CORPUS_DIR)
    .filter((name) => name.endsWith(".implicit.js"))
    .filter((name) => !CPU_UNSUPPORTED.has(name))
    .sort()
    .map((name) => path.join(CORPUS_DIR, name));
}

async function loadModel(sourcePath) {
  const sourceUrl = pathToFileURL(sourcePath).href;
  return normalizeImplicitCadModel(await import(sourceUrl), { sourceUrl });
}

test("implicit SDF corpus evaluates identically to the committed baseline", { skip: !HAS_CORPUS && "no models/implicits corpus beside this package" }, async (t) => {
  const paths = corpusModelPaths();
  assert.ok(paths.length > 0, "expected at least one model in models/implicits");

  const results = {};
  const failures = [];

  for (const sourcePath of paths) {
    const name = path.basename(sourcePath);
    try {
      results[name] = evaluateModel(await loadModel(sourcePath));
    } catch (error) {
      // A model that cannot even be evaluated is recorded as such. If it loaded before and
      // does not now, that is a regression the baseline comparison will catch.
      results[name] = { error: String(error?.message || error) };
    }
  }

  if (WRITE_BASELINE) {
    for (const entry of Object.values(results)) {
      delete entry.compiled;
      delete entry.interpretedDigest;
      // Machine-local by construction: it is the exact-bytes half of the differential gate,
      // recomputed every run. Committing it would put an unportable value in the baseline --
      // the precise thing this file must not hold.
      delete entry.exactDigest;
    }
    fs.mkdirSync(path.dirname(BASELINE_PATH), { recursive: true });
    fs.writeFileSync(BASELINE_PATH, `${JSON.stringify({ totalPoints: TOTAL_POINTS, models: results }, null, 2)}\n`);
    t.diagnostic(`wrote baseline for ${Object.keys(results).length} models to ${BASELINE_PATH}`);
    return;
  }

  assert.ok(
    fs.existsSync(BASELINE_PATH),
    `no baseline at ${BASELINE_PATH}; create one with IMPLICIT_SDF_BASELINE_WRITE=1`
  );
  const baseline = JSON.parse(fs.readFileSync(BASELINE_PATH, "utf8"));

  assert.equal(
    baseline.totalPoints,
    TOTAL_POINTS,
    "point count changed, so digests are not comparable; re-baseline deliberately"
  );

  const expectedNames = Object.keys(baseline.models).sort();
  const actualNames = Object.keys(results).sort();
  assert.deepEqual(actualNames, expectedNames, "the model corpus changed; re-baseline deliberately");

  for (const name of actualNames) {
    const expected = baseline.models[name];
    const actual = results[name];
    if (expected.error || actual.error) {
      if (expected.error !== actual.error) {
        failures.push(`${name}: evaluability changed (was ${expected.error || "ok"}, now ${actual.error || "ok"})`);
      }
      continue;
    }
    if (actual.compiled !== true) {
      failures.push(`${name}: did not compile -- silent interpreter fallback`);
    }
    if (actual.interpretedDigest !== actual.exactDigest) {
      failures.push(`${name}: compiled and interpreted sdf() disagree (differential gate)`);
    }
    if (actual.sdfDigest !== expected.sdfDigest) {
      failures.push(
        `${name}: sdf() changed\n    expected ${expected.sdfDigest}\n    actual   ${actual.sdfDigest}\n` +
        `    first values expected ${JSON.stringify(expected.sdfSample)}\n` +
        `    first values actual   ${JSON.stringify(actual.sdfSample)}`
      );
    }
    if (actual.colorDigest !== expected.colorDigest) {
      failures.push(
        `${name}: color() changed\n    expected ${expected.colorDigest}\n    actual   ${actual.colorDigest}`
      );
    }
  }

  assert.deepEqual(failures, [], `SDF corpus diverged from baseline:\n  ${failures.join("\n  ")}`);
});

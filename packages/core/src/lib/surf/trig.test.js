// Engine-independent trigonometry (trig.js). Three things have to hold: the
// values are as good as `Math`'s (within one ulp, and exact where the answer is
// exact); they are the SAME bits on every engine, which a golden vector pins
// because a unit test only ever runs on one at a time; and nothing on the way
// into a stored tessellation or out into an exported mesh still calls a `Math`
// function that ECMA-262 leaves to the implementation.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

import { acos, atan, atan2, cos, sin } from "./trig.js";

const view = new DataView(new ArrayBuffer(16));

function ulpsApart(a, b) {
  if (Object.is(a, b)) return 0;
  view.setFloat64(0, a);
  view.setFloat64(8, b);
  let x = view.getBigInt64(0);
  let y = view.getBigInt64(8);
  // Map the sign-magnitude doubles onto a monotone integer line.
  if (x < 0n) x = -9223372036854775808n - x;
  if (y < 0n) y = -9223372036854775808n - y;
  return Number(x > y ? x - y : y - x);
}

function* samples(count) {
  // A fixed LCG, so the same arguments are tested on every run and engine.
  let state = 12345;
  const next = () => {
    state = (state * 1103515245 + 12345) % 2147483648;
    return state / 2147483648;
  };
  for (let i = 0; i < count; i += 1) {
    const span = [0.5, 2, 20, 2000][i % 4];
    yield (next() - 0.5) * span;
  }
}

test("deterministic sin/cos stay within one ulp of the engine's own", () => {
  let worstSin = 0;
  let worstCos = 0;
  for (const x of samples(50000)) {
    worstSin = Math.max(worstSin, ulpsApart(sin(x), Math.sin(x)));
    worstCos = Math.max(worstCos, ulpsApart(cos(x), Math.cos(x)));
  }
  assert.ok(worstSin <= 1, `sin is ${worstSin} ulps from Math.sin`);
  assert.ok(worstCos <= 1, `cos is ${worstCos} ulps from Math.cos`);
});

test("the values that must be exact are exact", () => {
  assert.ok(Object.is(sin(0), 0));
  assert.equal(cos(0), 1);
  assert.equal(sin(Math.PI / 2), 1);
  assert.equal(cos(Math.PI), -1);
  assert.equal(sin(-Math.PI / 2), -1);
  // The cardinal quarter turns: not zero, because the double nearest pi/2 is
  // not pi/2 — but the SAME not-zero every engine computes, which is the whole
  // point. These are the values the cylinder-seam normals in an exported GLB
  // are made of.
  assert.equal(cos(Math.PI / 2), 6.123233995736766e-17);
  assert.equal(sin(Math.PI), 1.2246467991473532e-16);
  assert.equal(cos(3 * Math.PI / 2), -1.8369701987210297e-16);
  assert.equal(sin(2 * Math.PI), -2.4492935982947064e-16);
});

test("odd/even symmetry survives argument reduction", () => {
  for (const x of samples(2000)) {
    assert.ok(Object.is(sin(-x), -sin(x)) || sin(x) === 0, `sin(${-x})`);
    assert.equal(cos(-x), cos(x), `cos(${-x})`);
  }
});

test("the inverse functions stay within one ulp of the engine's own", () => {
  let worstAcos = 0;
  let worstAtan = 0;
  let worstAtan2 = 0;
  const cosines = samples(30000);
  const slopes = samples(30000);
  const ys = samples(30000);
  const xs = samples(30000);
  for (let i = 0; i < 30000; i += 1) {
    const c = Math.max(-1, Math.min(1, cosines.next().value / 10));
    worstAcos = Math.max(worstAcos, ulpsApart(acos(c), Math.acos(c)));
    const t = slopes.next().value;
    worstAtan = Math.max(worstAtan, ulpsApart(atan(t), Math.atan(t)));
    const y = ys.next().value;
    const x = xs.next().value;
    worstAtan2 = Math.max(worstAtan2, ulpsApart(atan2(y, x), Math.atan2(y, x)));
  }
  assert.ok(worstAcos <= 1, `acos is ${worstAcos} ulps from Math.acos`);
  assert.ok(worstAtan <= 1, `atan is ${worstAtan} ulps from Math.atan`);
  assert.ok(worstAtan2 <= 1, `atan2 is ${worstAtan2} ulps from Math.atan2`);
});

test("the inverse functions' exact values are exact", () => {
  assert.equal(acos(1), 0);
  assert.equal(acos(-1), Math.PI);
  assert.equal(acos(0), Math.PI / 2);
  assert.ok(Object.is(atan(0), 0));
  assert.ok(Object.is(atan(-0), -0));
  assert.equal(atan(1), Math.PI / 4);
  assert.equal(atan2(1, 1), Math.PI / 4);
  assert.equal(atan2(1, 0), Math.PI / 2);
  assert.equal(atan2(-1, 0), -Math.PI / 2);
  assert.equal(atan2(0, -3), Math.PI);
  assert.ok(Object.is(atan2(-0, 3), -0));
  assert.ok(Number.isNaN(acos(1.5)));
  assert.ok(Number.isNaN(atan2(NaN, 1)));
});

// The point of trig.js is that two engines agree, and a unit test only ever
// runs on one. So pin the bits: this table was produced by this implementation
// and verified identical in Node 26 and in Chromium 151, the two engines that
// publish into cadgen's shared mesh store. An engine that computes any line
// differently fails here rather than silently exporting different bytes.
const GOLDEN = [
  ["sin", [1e-10], "3ddb7cdfd9d7bdbb"],
  ["sin", [0.3], "3fd2e9cd95baba33"],
  ["sin", [0.7853981633974483], "3fe6a09e667f3bcc"],
  ["sin", [1.5707963267948966], "3ff0000000000000"],
  ["sin", [2.6], "3fe07efcbba085bb"],
  ["sin", [3.141592653589793], "3ca1a62633145c07"],
  ["sin", [-4.2], "3febe3f2dfd012d7"],
  ["sin", [6.283185307179586], "bcb1a62633145c07"],
  ["sin", [123.456], "bfe9b9dadc41aeb5"],
  ["sin", [-987.6543], "bfedc1f0790555b6"],
  ["sin", [1.570796326794897], "3ff0000000000000"],
  ["cos", [1e-10], "3ff0000000000000"],
  ["cos", [0.3], "3fee921dd42f09ba"],
  ["cos", [0.7853981633974483], "3fe6a09e667f3bcd"],
  ["cos", [1.5707963267948966], "3c91a62633145c07"],
  ["cos", [2.6], "bfeb6ba1f680f470"],
  ["cos", [3.141592653589793], "bff0000000000000"],
  ["cos", [-4.2], "bfdf606eec8ac71e"],
  ["cos", [6.283185307179586], "3ff0000000000000"],
  ["cos", [123.456], "bfe307e5980a1559"],
  ["cos", [-987.6543], "3fd7893c26ff17bd"],
  ["cos", [1.570796326794897], "bcbb9676733ae8fe"],
  ["acos", [-1], "400921fb54442d18"],
  ["acos", [-0.9], "400586476251e745"],
  ["acos", [-0.5], "4000c152382d7366"],
  ["acos", [-0.2], "3ffc5abe698d8960"],
  ["acos", [0], "3ff921fb54442d18"],
  ["acos", [0.2], "3ff5e9383efad0d1"],
  ["acos", [0.49999], "3ff0c15e53caf940"],
  ["acos", [0.5], "3ff0c152382d7366"],
  ["acos", [0.9], "3fdcdd9f8f922e98"],
  ["acos", [0.99999], "3f725160dad27316"],
  ["acos", [1], "0000000000000000"],
  ["atan", [0], "0000000000000000"],
  ["atan", [1e-10], "3ddb7cdfd9d7bdbb"],
  ["atan", [0.4], "3fd85a376b677dc0"],
  ["atan", [0.5], "3fddac670561bb4f"],
  ["atan", [0.8], "3fe5977a5103ea93"],
  ["atan", [1], "3fe921fb54442d18"],
  ["atan", [1.5], "3fef730bd281f69b"],
  ["atan", [2], "3ff1b6e192ebbe44"],
  ["atan", [3], "3ff3fc176b7a8560"],
  ["atan", [100], "3ff8f905eb2def22"],
  ["atan", [-0.6], "bfe14b1dd5f90ce1"],
  ["atan", [-7.25], "bff6f08f07435fec"],
  ["atan2", [1, 1], "3fe921fb54442d18"],
  ["atan2", [-1, 1], "bfe921fb54442d18"],
  ["atan2", [1, -1], "4002d97c7f3321d2"],
  ["atan2", [-1, -1], "c002d97c7f3321d2"],
  ["atan2", [0.5, 3], "3fc52397843c9add"],
  ["atan2", [3, 0.5], "3ff67d8863bc99bd"],
  ["atan2", [-2.5, 7.25], "bfd540765a5b20a2"],
  ["atan2", [1e-8, 4], "3e25798ee2308c3a"],
  ["atan2", [4, 1e-8], "3ff921fb539860a1"],
  ["atan2", [0, -3], "400921fb54442d18"],
  ["atan2", [-0, 3], "8000000000000000"],
];

test("the golden vector is bit-identical on whatever engine runs it", () => {
  const FUNCTIONS = { sin, cos, acos, atan, atan2 };
  const wrong = [];
  for (const [name, args, expected] of GOLDEN) {
    view.setFloat64(0, FUNCTIONS[name](...args));
    const actual = view.getBigUint64(0).toString(16).padStart(16, "0");
    if (actual !== expected) wrong.push(`${name}(${args.join(", ")}) = 0x${actual}, expected 0x${expected}`);
  }
  assert.deepEqual(wrong, [], wrong.join("\n"));
  assert.equal(GOLDEN.length, 56);
});

test("non-finite arguments answer NaN and absurd ones fail loudly", () => {
  assert.ok(Number.isNaN(sin(NaN)));
  assert.ok(Number.isNaN(cos(Infinity)));
  assert.ok(Number.isNaN(sin(-Infinity)));
  assert.throws(() => sin(1e9), RangeError);
  assert.throws(() => cos(-1e9), RangeError);
  // Just inside the limit still answers.
  assert.ok(Number.isFinite(cos(524287)));
});

// Every `Math` member ECMA-262 leaves to the implementation. `sqrt` is absent
// on purpose: IEEE 754 requires it correctly rounded, so it is exact everywhere.
const UNSPECIFIED = /Math\.(sin|cos|tan|asin|acos|atan|atan2|hypot|log|log2|log10|log1p|exp|expm1|pow|cbrt|sinh|cosh|tanh|asinh|acosh|atanh|random)\b/g;

/** Every module reachable from `entry` by relative import, `entry` included. */
function importClosure(entry) {
  const found = new Map(); // keyed by href: two URL objects for one file are not equal
  const visit = (file) => {
    if (found.has(file.href)) return;
    found.set(file.href, file);
    const source = readFileSync(file, "utf8");
    for (const [, specifier] of source.matchAll(/(?:from|import)\s*\(?\s*["']([^"']+)["']/g)) {
      if (!specifier.startsWith(".")) continue; // third-party packages are not ours to police
      const target = new URL(specifier, file);
      for (const candidate of [target, new URL(`${specifier}.js`, file), new URL(`${specifier}.mjs`, file)]) {
        if (existsSync(candidate)) {
          visit(candidate);
          break;
        }
      }
    }
  };
  visit(entry);
  return found.values();
}

function code(file) {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//"))
    .join("\n");
}

test("nothing that writes bytes calls an unspecified Math function", () => {
  // These functions are implementation approximations: Node's engine and the
  // snapshot browser's disagree on a few percent of arguments. Anything whose
  // result is encoded into a content-addressed tessellation, or serialized into
  // a GLB, STL or 3MF, has to avoid them — otherwise the same document exports
  // different bytes depending on which engine ran (cadgen law 5).
  //
  // Scanned as an import CLOSURE, not a list, so a new dependency is covered
  // the moment it is pulled in rather than the next time someone remembers.
  const modules = new Set([
    ...importClosure(new URL("../../../bin/mesh-export.mjs", import.meta.url)),
    ...importClosure(new URL("./tessellate.js", import.meta.url)),
  ]);
  assert.ok(modules.size > 20, `the closure walk found only ${modules.size} modules`);

  const offenders = [];
  for (const file of modules) {
    if (file.pathname.endsWith(".test.js") || file.pathname.endsWith(".test.mjs")) continue;
    for (const [index, line] of code(file).split("\n").entries()) {
      const hits = line.match(UNSPECIFIED);
      if (hits) offenders.push(`${file.pathname.split("/@hardcore/core/")[1]}:${index + 1}: ${hits.join(", ")}`);
    }
  }
  assert.deepEqual(offenders, [], `use lib/surf/trig.js (or exact arithmetic) instead:\n${offenders.join("\n")}`);
});

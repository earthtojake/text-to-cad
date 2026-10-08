import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildCadRefToken,
  isNativeCadSelector,
  normalizeCadRefSelectors,
  parseCadRefSelector,
  parseCadRefToken
} from "./cadRefs.js";

// The same fixture the Python suite reads. It is the only thing keeping the two grammars --
// this module and cadgen/cad_ref_syntax.py -- from drifting, which they had already done four
// copies deep before it existed.
const FIXTURE = JSON.parse(
  readFileSync(fileURLToPath(new URL("./cadRefs.parity.json", import.meta.url)), "utf8")
);

test("every selector case parses as the shared fixture says", () => {
  for (const testCase of FIXTURE.selectorCases) {
    const parsed = parseCadRefSelector(testCase.selector);
    assert.ok(parsed, `${testCase.selector} should parse`);
    assert.equal(parsed.selectorType, testCase.selectorType, testCase.selector);
    assert.equal(parsed.occurrenceId, testCase.occurrenceId, testCase.selector);
    assert.equal(parsed.ordinal ?? null, testCase.ordinal, testCase.selector);
    assert.equal(parsed.canonical, testCase.canonical, testCase.selector);
    assert.equal(parsed.label ?? "", testCase.label ?? "", testCase.selector);
  }
});

test("comma lists inherit as the shared fixture says", () => {
  for (const testCase of FIXTURE.inheritanceCases) {
    assert.deepEqual(
      normalizeCadRefSelectors(testCase.input),
      testCase.expected,
      `${testCase.input}: ${testCase.why || ""}`
    );
  }
});

// Backwards compatibility is the point of the parse ordering: label support must not move a
// single ref anyone has already pasted.
test("numeric selectors never take the label branch", () => {
  const numeric = [
    "o1",
    "o1.2",
    "o1.2.3.4.5.6",
    "o12.f19",
    "o1.2.s3",
    "o1.2.e3",
    "o1.2.v3",
    "f45",
    "s2",
    "e9",
    "v4",
    "m1",
    "m17"
  ];
  for (const selector of numeric) {
    const parsed = parseCadRefSelector(selector);
    assert.equal(parsed.label ?? "", "", `${selector} must not be read as a label`);
  }
});

test("mates stay opaque even though they match the label shape", () => {
  for (const selector of ["m1", "m2", "M3"]) {
    assert.equal(parseCadRefSelector(selector).selectorType, "opaque", selector);
  }
});

test("isNativeCadSelector accepts every numeric form and rejects labels", () => {
  for (const selector of ["o1", "o1.2", "o12.f19", "f45", "s2", "e9", "v4", "m1"]) {
    assert.ok(isNativeCadSelector(selector), selector);
  }
  for (const selector of ["eye_shank", "servo_end_plate.f45", "", "not a selector!"]) {
    assert.ok(!isNativeCadSelector(selector), selector);
  }
});

test("every token case parses as the shared fixture says", () => {
  for (const testCase of FIXTURE.tokenCases) {
    const parsed = parseCadRefToken(testCase.text);
    if (testCase.selectors === null) {
      assert.equal(parsed, null, `${testCase.text} should not be a token`);
      continue;
    }
    assert.ok(parsed, `${testCase.text} should parse`);
    assert.equal(parsed.cadPath, testCase.cadPath, testCase.text);
    assert.deepEqual(parsed.selectors, testCase.selectors, testCase.text);
  }
});

test("a token round-trips through buildCadRefToken", () => {
  // buildCadRefToken took a cadPath and discarded it (`void cadPath`). It no longer does, so
  // what the viewer copies is what the grammar parses back.
  assert.equal(buildCadRefToken({ cadPath: "plate.stl", selector: "o1.2" }), "plate.stl#o1.2");
  assert.equal(buildCadRefToken({ selector: "o1.2" }), "#o1.2");
  assert.equal(buildCadRefToken({ cadPath: "plate.stl" }), "plate.stl#");
  assert.equal(buildCadRefToken({}), "#");
  assert.equal(
    parseCadRefToken(buildCadRefToken({ cadPath: "a/b.step.py", selectors: ["o1.2", "f3"] })).cadPath,
    "a/b.step.py"
  );
});

test("bare tokens carry no file prefix", () => {
  for (const text of ["#o1", "#o1.2.f3", "#f45", "#m1", "#", "#o1.2,f3"]) {
    assert.equal(parseCadRefToken(text).cadPath, "", `${text} must carry no prefix`);
  }
});

test("imported file tokens quote and round-trip filename delimiters", () => {
  for (const cadPath of ['Hex Drive Screw (2).STEP', 'models/café #1 "screw".STEP']) {
    const token = buildCadRefToken({cadPath, selectors:['o2','o1']});
    assert.deepEqual(parseCadRefToken(token), {token, cadPath, selectors:['o1','o2']});
  }
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildCadRefToken,
  elementRef,
  engineSelectorText,
  isElementName,
  isEngineRefFile,
  isEngineSelector,
  isNativeCadSelector,
  isOccurrenceToken,
  normalizeCadRefSelectors,
  parseCadRefSelector,
  parseCadRefToken,
  parseEngineRef,
  sortCadRefSelectors,
  spellEngineRefs,
  splitElementRef
} from "./cadRefs.js";

// The same fixture the Python suites read. It is the only thing keeping the engine grammar's two
// parsers -- this module and cadgen/engine/refs.py -- from drifting, which the grammars had
// already done four copies deep before it existed; a STEP's cases pin this module alone.
const FIXTURE = JSON.parse(
  readFileSync(fileURLToPath(new URL("./cadRefs.parity.json", import.meta.url)), "utf8")
);

const O1 = "o:4b1f9e2a7c03";
const O2 = "o:0a9e8d7c6b5f";
const F = "f:9d2e8c1b5a70";
const E = "e:12ab34cd56ef";
const V = "v:fedcba987654";
// Names by lineage: the feature that made the element, its number there, and a split piece's.
const NAMED = ["f:dial.extrude1.3", "e:dial.make_box1.6;Gf:dial.cut1+f:dial.make_cylinder2.1", "v:dial.cut1~5d1e0c2f9a3b;U2:dial.fillet1"];

test("every selector case parses as the shared fixture says", () => {
  for (const testCase of FIXTURE.selectorCases) {
    const parsed = parseCadRefSelector(testCase.selector);
    assert.ok(parsed, `${testCase.selector} should parse`);
    assert.equal(parsed.selectorType, testCase.selectorType, testCase.selector);
    assert.equal(parsed.occurrenceId, testCase.occurrenceId, testCase.selector);
    assert.equal(parsed.element ?? "", testCase.element, testCase.selector);
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

// The parse ordering: token and name forms are tried before the label form, so neither is a label.
test("token and name selectors never take the label branch", () => {
  for (const selector of [O1, `${O1}/${F}`, `${O1}/${E}`, `${O1}/${V}`, F, E, V, ...NAMED, ...NAMED.map(name => `${O2}/${name}`), "m1", "m17"]) {
    const parsed = parseCadRefSelector(selector);
    assert.equal(parsed.label ?? "", "", `${selector} must not be read as a label`);
  }
});

test("mates stay opaque even though they match the label shape", () => {
  for (const selector of ["m1", "m2", "M3"]) {
    assert.equal(parseCadRefSelector(selector).selectorType, "opaque", selector);
  }
});

test("isNativeCadSelector accepts every token and name form and rejects labels and the retired grammar", () => {
  for (const selector of [O1, `${O1}/${F}`, `${O1}/${E}`, `${O1}/${V}`, F, E, V, ...NAMED, `${O1}/${NAMED[0]}`, "m1", "M3"]) {
    assert.ok(isNativeCadSelector(selector), selector);
  }
  for (const selector of ["eye_shank", `servo_end_plate/${F}`, `bracket/${NAMED[0]}`, "", "not a selector!", "o1", "o1.2",
    "o1.2.f7", "f45", "s2", "o:4B1F9E2A7C03", "f:dial.extrude1", "f:dial.extrude1.3.2", "f:dial.make_box1.6;G:dial.cut1"]) {
    assert.ok(!isNativeCadSelector(selector), selector);
  }
  assert.ok(isOccurrenceToken(O1) && !isOccurrenceToken(F) && !isOccurrenceToken("o1.2"));
  for (const name of [F, E, V, ...NAMED]) assert.ok(isElementName(name), name);
  for (const value of [O1, "f7", "f:dial.extrude1", "f:9d2e8c1b5a70.3", "x:dial.extrude1.3", "f:dial.cut3~5d1e", "e:a.b.1;Gf:c.d1+f:9d2e8c1b5a70"]) assert.ok(!isElementName(value), value);
});

test("an element ref is composed and split by one rule", () => {
  assert.equal(elementRef(O1, F), `${O1}/${F}`);
  assert.deepEqual(splitElementRef(`${O1}/${F}`), { owner: O1, element: F });
  assert.deepEqual(splitElementRef(`#base_plate/${E}`), { owner: "base_plate", element: E });
  assert.deepEqual(splitElementRef(`${O1}/${NAMED[1]}`), { owner: O1, element: NAMED[1] });
  assert.equal(splitElementRef(O1), null);
  assert.equal(splitElementRef(`${O1}/s:9d2e8c1b5a70`), null);
  assert.equal(splitElementRef("o1.2.f7"), null);
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
  // What the viewer copies is what the grammar parses back, file prefix included.
  assert.equal(buildCadRefToken({ cadPath: "plate.stl", selector: O1 }), `plate.stl#${O1}`);
  assert.equal(buildCadRefToken({ selector: O1 }), `#${O1}`);
  assert.equal(buildCadRefToken({ cadPath: "plate.stl" }), "plate.stl#");
  assert.equal(buildCadRefToken({}), "#");
  assert.equal(
    parseCadRefToken(buildCadRefToken({ cadPath: "a/b.step.py", selectors: [O1, F] })).cadPath,
    "a/b.step.py"
  );
});

test("selectors sort by occurrence, then occurrence before face before edge before vertex", () => {
  assert.deepEqual(
    sortCadRefSelectors([`${O1}/${V}`, `${O1}/${E}`, O1, `${O1}/${F}`, `${O2}/${F}`, O2]),
    [O2, `${O2}/${F}`, O1, `${O1}/${F}`, `${O1}/${E}`, `${O1}/${V}`]
  );
});

test("bare tokens carry no file prefix", () => {
  for (const text of [`#${O1}`, `#${O1}/${F}`, `#${F}`, "#m1", "#", `#${O1},${F}`]) {
    assert.equal(parseCadRefToken(text).cadPath, "", `${text} must carry no prefix`);
  }
});

test("imported file tokens quote and round-trip filename delimiters", () => {
  for (const cadPath of ['Hex Drive Screw (2).STEP', 'models/café #1 "screw".STEP']) {
    const token = buildCadRefToken({cadPath, selectors:[O2, O1]});
    assert.deepEqual(parseCadRefToken(token), {token, cadPath, selectors:[O2, O1]});
  }
});

// A parsed engine selector as the fixture writes it: its owner's segments, a quoted one as
// { quoted, index }, and its element's text.
const engineShape = ({ owner, element }) => ({
  owner: owner ? owner.map(segment => (!segment.quoted ? segment.text : segment.index === null ? { quoted: segment.text } : { quoted: segment.text, index: segment.index })) : null,
  element: element === null || typeof element === "string" ? element : `${element.kind} ${element.ordinal}`
});

test("an .xbf's refs parse as cadgen.engine.refs parses them, case for case", () => {
  assert.ok(FIXTURE.refCases.length);
  for (const testCase of FIXTURE.refCases) {
    const parsed = parseEngineRef(testCase.ref);
    if (testCase.refused) {
      assert.equal(parsed, null, `${JSON.stringify(testCase.ref)}: ${testCase.why}`);
      continue;
    }
    assert.ok(parsed, `${JSON.stringify(testCase.ref)}: ${testCase.why}`);
    assert.equal(parsed.file, testCase.file, testCase.ref);
    assert.deepEqual(parsed.selectors.map(engineShape), testCase.selectors, testCase.ref);
    assert.deepEqual(parsed.selectors.map(engineSelectorText), testCase.printed, testCase.ref);
  }
});

test("an .xbf's occurrences and elements are spelled as cadgen inspect answers them", () => {
  assert.ok(FIXTURE.spellingCases.length);
  for (const { structure, occurrences, elements, why } of FIXTURE.spellingCases) {
    const spell = spellEngineRefs(structure.tree);
    const entryAt = at => at.reduce((entry, index) => entry.children[index], structure.tree);
    for (const row of occurrences) assert.equal(spell.occurrence(entryAt(row.at)), row.ref, why);
    for (const row of elements) {
      const entry = entryAt(row.at);
      const name = structure.prototypes[entry.prototype][`${row.kind}Names`][String(row.ordinal)] || "";
      assert.equal(spell.element(entry, row.kind, row.ordinal, name), row.ref, why);
    }
    assert.equal(spell.occurrence({ name: "elsewhere" }), "", "an entry of another tree has no ref here");
  }
});

test("an .xbf's copied line is the engine's whole ref, round-tripped; a STEP's keeps its own grammar", () => {
  const cadPath = "/work/my parts/kit.xbf";
  const selectors = ["kit/hand/finger.2/face 7", "\"M3, M4\"/e:screw.body.2", "palm"];
  const token = buildCadRefToken({ cadPath, selectors });
  // Written in the order given, a comma inside a quoted label left whole.
  assert.equal(token, `"${cadPath}"#kit/hand/finger.2/face 7,"M3, M4"/e:screw.body.2,palm`);
  assert.deepEqual(parseCadRefToken(`${token}\nmore text`), { token, cadPath, selectors });
  // The line runs to its end: a label's spaces are its own, and the engine refuses what it refuses.
  assert.deepEqual(parseCadRefToken("/w/kit.xbf#kit/v1.5 bracket/face 2").selectors, ["kit/v1.5 bracket/face 2"]);
  assert.deepEqual(parseCadRefToken("/w/kit.xbf#hand/finger.2,face 3").selectors, ["hand/finger.2", "hand/finger.2/face 3"]);
  assert.equal(parseCadRefToken("/w/kit.xbf#kit//face 1"), null);
  assert.ok(isEngineRefFile("/w/KIT.XBF") && !isEngineRefFile("/w/kit.step") && !isEngineRefFile("/w/kit.xbf.step"));
  assert.ok(isEngineSelector("kit/\"M3, M4\"/face 1") && !isEngineSelector("a,b") && !isEngineSelector(" a") && !isEngineSelector(""));
  // A STEP's token is unchanged: it stops at a blank, and its selectors sort.
  assert.deepEqual(parseCadRefToken("/w/kit.step#o:4b1f9e2a7c03/f:dial.extrude1.3 note").selectors, ["o:4b1f9e2a7c03/f:dial.extrude1.3"]);
  assert.equal(buildCadRefToken({ cadPath: "/w/kit.step", selectors: ["o:4b1f9e2a7c03/f:9d2e8c1b5a70", "o:4b1f9e2a7c03"] }),
    "/w/kit.step#o:4b1f9e2a7c03,o:4b1f9e2a7c03/f:9d2e8c1b5a70");
});

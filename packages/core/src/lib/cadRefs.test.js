import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildCadRefToken,
  engineSelectorText,
  isEngineRefFile,
  isEngineSelector,
  isLabelSelector,
  isOccurrenceToken,
  parseCadRefToken,
  parseEngineRef,
  spellEngineRefs
} from "./cadRefs.js";

// The same fixture the Python suites read. It is the only thing keeping the engine grammar's two
// parsers -- this module and cad/engine/refs.py -- from drifting, which the grammars had
// already done four copies deep before it existed.
const FIXTURE = JSON.parse(
  readFileSync(fileURLToPath(new URL("./cadRefs.parity.json", import.meta.url)), "utf8")
);

test("an element name is what the engine's naming says it is, and anything else is an owner's segment", () => {
  const { names, notNames } = FIXTURE.elementNameCases;
  assert.ok(names.length && notNames.length);
  for (const name of names) assert.deepEqual(parseEngineRef(`#part/${name}`).selectors[0].element, name, name);
  for (const text of notNames) {
    const [selector] = parseEngineRef(`#part/${text}`).selectors;
    assert.equal(selector.element, null, text);
    assert.equal(selector.owner.at(-1).text, text, text);
  }
});

test("every document the engine draws is named in its grammar: an .xbf, a STEP, a document by its id", () => {
  for (const path of ["/w/kit.xbf", "/w/KIT.XBF", "/w/kit.step", "/w/Kit.STEP", "/w/kit.stp", "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"]) {
    assert.ok(isEngineRefFile(path), path);
  }
  for (const path of ["/w/kit.xbf.py", "/w/kit.step.py", "/w/arm.urdf", "/w/plate.stl", "/w/plate.dxf", "", "6F1C2A4E-1B2C-5D3E-8F4A-0123456789AB"]) {
    assert.ok(!isEngineRefFile(path), path);
  }
});

test("any other file names a pick by a label, its token a comma list that stops at a blank", () => {
  for (const selector of ["upper_arm", "h2F", "glb:3", "_base", "cast_rim:5spoke_2", "m1"]) assert.ok(isLabelSelector(selector), selector);
  for (const selector of ["", " upper_arm", "5spoke", "eye#shank", "not a label", "a/b", "a,b", "arm-link", null]) assert.ok(!isLabelSelector(selector), String(selector));
  const cases = [
    ["/robots/arm.urdf#upper_arm", "/robots/arm.urdf", ["upper_arm"]],
    ["/robots/arm.urdf#base_link,upper_arm,base_link note", "/robots/arm.urdf", ["base_link", "upper_arm"]],
    ["   bracket.dxf#h2F", "bracket.dxf", ["h2F"]],
    ["plate.stl#", "plate.stl", []],
    ["#glb:3", "", ["glb:3"]],
    ["\"/robots/my arm (2).urdf\"#base_link", "/robots/my arm (2).urdf", ["base_link"]]
  ];
  for (const [text, cadPath, selectors] of cases) {
    const parsed = parseCadRefToken(text);
    assert.equal(parsed.cadPath, cadPath, text);
    assert.deepEqual(parsed.selectors, selectors, text);
  }
  for (const text of ["plate.stl", "\"broken name.urdf#base_link", ""]) assert.equal(parseCadRefToken(text), null, text);
  // Written as given, once each, in order; a path with a blank or a delimiter quoted.
  assert.equal(buildCadRefToken({ cadPath: "/robots/arm.urdf", selectors: ["upper_arm", "base_link", "upper_arm"] }), "/robots/arm.urdf#upper_arm,base_link");
  assert.equal(buildCadRefToken({ cadPath: "plate.stl" }), "plate.stl#");
  assert.equal(buildCadRefToken({ selector: "glb:3" }), "#glb:3");
  assert.equal(buildCadRefToken({}), "#");
  for (const cadPath of ["Hex Drive Screw (2).urdf", 'models/caf\u00e9 #1 "arm".urdf']) {
    const token = buildCadRefToken({ cadPath, selectors: ["upper_arm", "base_link"] });
    assert.deepEqual(parseCadRefToken(token), { token, cadPath, selectors: ["upper_arm", "base_link"] });
  }
  // An older GLB names the nodes it places by an occurrence token.
  assert.ok(isOccurrenceToken("o:4b1f9e2a7c03") && !isOccurrenceToken("o:4B1F9E2A7C03") && !isOccurrenceToken("o1.2"));
});

// A parsed engine selector as the fixture writes it: its owner's segments, a quoted one as
// { quoted, index }, and its element's text.
const engineShape = ({ owner, element }) => ({
  owner: owner ? owner.map(segment => (!segment.quoted ? segment.text : segment.index === null ? { quoted: segment.text } : { quoted: segment.text, index: segment.index })) : null,
  element: element === null || typeof element === "string" ? element : `${element.kind} ${element.ordinal}`
});

test("an .xbf's refs parse as cad.engine.refs parses them, case for case", () => {
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

test("an .xbf's occurrences and elements are spelled as cad inspect answers them", () => {
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

test("an engine document's copied line is the engine's whole ref, round-tripped, a STEP's as an .xbf's", () => {
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
  assert.ok(isEngineSelector("kit/\"M3, M4\"/face 1") && !isEngineSelector("a,b") && !isEngineSelector(" a") && !isEngineSelector(""));
  // A STEP's line is read the same way: a part labelled with spaces, a face by its name or its number.
  const step = "/w/L bracket.step";
  const bracket = "L bracket 80 x 60 x 6 mm";
  const named = `${bracket}/f:bracket_body.body_bcndnk~ba6e1714f88b`;
  const stepToken = buildCadRefToken({ cadPath: step, selectors: [named, `${bracket}/face 4`] });
  assert.equal(stepToken, `"${step}"#${named},${bracket}/face 4`);
  assert.deepEqual(parseCadRefToken(stepToken), { token: stepToken, cadPath: step, selectors: [named, `${bracket}/face 4`] });
  assert.deepEqual(parseCadRefToken(`/w/kit.STP#${bracket}/edge 2`).selectors, [`${bracket}/edge 2`]);
});

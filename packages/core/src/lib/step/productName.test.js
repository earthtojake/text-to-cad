import assert from "node:assert/strict";
import test from "node:test";

import { isXcafEntryLabel, stepPartNameFromFile, stepProductName } from "./productName.js";

test("an XCAF label entry standing where a name belongs is no name at all", () => {
  for (const entry of ["=>[0:1:1:2]", "=> [0:1:1:2]", "[0:1:1:2]", "0:1:1:2", "0:1", " =>[0:1:1:12] "]) {
    assert.equal(isXcafEntryLabel(entry), true, entry);
    assert.equal(stepProductName(entry), "", entry);
  }
});

test("a name somebody gave is kept as written, even one with digits and colons in it", () => {
  for (const name of ["l_bracket", "Panel:1", "M3x8:2", "base", "0", "1:2 bracket", "=>bracket", "[bracket]"]) {
    assert.equal(isXcafEntryLabel(name), false, name);
    assert.equal(stepProductName(name), name, name);
  }
  assert.equal(stepProductName("  l_bracket "), "l_bracket");
  assert.equal(stepProductName(null), "");
  assert.equal(stepProductName(undefined), "");
});

test("a single-part file's part is named after the file, without its STEP extension", () => {
  assert.equal(stepPartNameFromFile("examples/STEP/l_bracket.step"), "l_bracket");
  assert.equal(stepPartNameFromFile("C:\\parts\\impeller.STP"), "impeller");
  assert.equal(stepPartNameFromFile("l_bracket.step"), "l_bracket");
  assert.equal(stepPartNameFromFile("notes.txt"), "notes.txt");
  assert.equal(stepPartNameFromFile(""), "");
});

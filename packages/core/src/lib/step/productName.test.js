import assert from "node:assert/strict";
import test from "node:test";

import { stepPartNameFromFile } from "./productName.js";

test("a single-part file's part is named after the file, without its STEP extension", () => {
  assert.equal(stepPartNameFromFile("examples/STEP/l_bracket.step"), "l_bracket");
  assert.equal(stepPartNameFromFile("C:\\parts\\impeller.STP"), "impeller");
  assert.equal(stepPartNameFromFile("l_bracket.step"), "l_bracket");
  assert.equal(stepPartNameFromFile("notes.txt"), "notes.txt");
  assert.equal(stepPartNameFromFile(""), "");
});

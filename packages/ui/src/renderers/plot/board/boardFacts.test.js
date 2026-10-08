import assert from "node:assert/strict";
import test from "node:test";
import { boardFindingFacts, findingCopyText } from "./boardFacts.js";

const finding = {
  check: "erc", severity: "error", type: "pin_not_connected", description: "Pin not connected",
  summary: "U2 pin 7 (VDD) isn't connected to anything", items: [{ text: "Symbol U9", ref: "", at: [1, 2] }],
};

test("a schematic's finding lists an item without a reference by its text", () => {
  const facts = boardFindingFacts(finding, { document: "schematic" });
  assert.deepEqual(facts.rows.at(-1), ["Items", "Symbol U9"]);
  assert.deepEqual(facts.rows.find(([name]) => name === "Message"), ["Message", "Pin not connected"]);
});

test("a finding is headed by its sentence, then KiCad's message, then its type", () => {
  assert.equal(boardFindingFacts(finding, { document: "schematic" }).heading, "U2 pin 7 (VDD) isn't connected to anything");
  assert.equal(boardFindingFacts({ ...finding, summary: "" }, { document: "schematic" }).heading, "Pin not connected");
  assert.equal(boardFindingFacts({ ...finding, summary: "", description: "" }, { document: "schematic" }).heading, "pin not connected");
});

test("a check copies as its sentence, then its references", () => {
  assert.equal(findingCopyText(finding, "/w/b.kicad_sch#U2.7"), "U2 pin 7 (VDD) isn't connected to anything · /w/b.kicad_sch#U2.7");
  assert.equal(findingCopyText(null, "/w/b.kicad_sch#U2.7"), "/w/b.kicad_sch#U2.7");
  assert.equal(findingCopyText(finding, ""), "");
});

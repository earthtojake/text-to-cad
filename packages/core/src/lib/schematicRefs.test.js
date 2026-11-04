import assert from "node:assert/strict";
import test from "node:test";

import { buildSchematicRefToken, canonicalSheetPath, formatSheetSelector, isSchematicRefPath, parseSchematicRefSelector } from "./schematicRefs.js";

test("a schematic reference is the board's for what both hold, and its own for sheets and items by uuid", () => {
  assert.equal(isSchematicRefPath("/x/divider.KICAD_SCH"), true);
  assert.deepEqual(parseSchematicRefSelector("#U3"), { kind: "part", ref: "U3", canonical: "#U3" });
  assert.deepEqual(parseSchematicRefSelector("U3.7"), { kind: "pad", ref: "U3", pad: "7", canonical: "#U3.7" });
  assert.deepEqual(parseSchematicRefSelector("#net:/MID"), { kind: "net", net: "/MID", canonical: "#net:/MID" });
  assert.deepEqual(parseSchematicRefSelector("#sheet:Load"), { kind: "sheet", sheet: "/Load/", canonical: "#sheet:/Load/" });
  assert.deepEqual(parseSchematicRefSelector('#sheet:"/Power Stage/"'), { kind: "sheet", sheet: "/Power Stage/", canonical: '#sheet:"/Power Stage/"' });
  assert.deepEqual(parseSchematicRefSelector("#wire:ABC-12"), { kind: "wire", id: "abc-12", canonical: "#wire:abc-12" });
  // A board's own kinds are not a schematic's.
  for (const text of ["#track:abc", "#F.Cu@x1y2", "#@x1y2", "", " #U3"]) assert.equal(parseSchematicRefSelector(text), null, text);
  assert.equal(canonicalSheetPath("a//b"), "/a/b/");
  assert.equal(formatSheetSelector("/"), "#sheet:/");
  assert.equal(buildSchematicRefToken({ path: "/w/divider.kicad_sch", selectors: ["R1", "#sheet:Load"] }), "/w/divider.kicad_sch#R1,sheet:/Load/");
  assert.throws(() => buildSchematicRefToken({ path: "x", selectors: ["#track:1"] }), /not a schematic reference/);
});

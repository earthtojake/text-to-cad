import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createBoardIndex } from "./boardIndex.js";
import { boardCheckMarks, boardCheckText, boardCheckTitle, boardChecks } from "./boardChecks.js";
import { drawBoardCheckMarks } from "./boardCheckMarks.js";

// A 40 x 30 mm sheet whose page origin sits at sheet (5, 25), laid out at page (2, 3), and KiCad's DRC of
// it as the route answers: a clearance error between a via and a track (and an item the board does not
// name), a missing connection, a dangling track, two exclusions (one the project's, with its comment; one
// by an older KiCad's severity, with no place), two parity entries (one with no item and no place) and a note.
const { board, drc } = JSON.parse(readFileSync(new URL("./boardChecks.fixture.json", import.meta.url), "utf8"));
const index = createBoardIndex(board, { x: 2, y: 3 });
const VIA = "#via:7a1c0000-0000-4000-8000-000000000003";
const TRACK = "#track:7a1c0000-0000-4000-8000-000000000001";
const OUT = "#track:7a1c0000-0000-4000-8000-000000000002";

test("a failing board: the verdict, the counts, and the findings in their groups, exclusions apart and never counted", () => {
  const checks = boardChecks(drc, index);
  assert.deepEqual([checks.state, checks.verdict, checks.failing], ["checked", "fail", 4]);
  // A difference from the schematic fails the board whatever severity KiCad gave it, as a missing connection does.
  assert.deepEqual(checks.counts, { errors: 3, unconnected: 1, warnings: 1, excluded: 2 });
  assert.deepEqual(checks.findings.map((finding) => [finding.group, finding.type]), [
    ["error", "clearance"], ["error", "unconnected_items"], ["error", "missing_footprint"], ["error", "net_conflict"],
    ["warning", "track_dangling"],
    ["excluded", "copper_sliver"], ["excluded", "silk_over_copper"],
  ]);
  // What the check said beside KiCad's report is a note, not a finding.
  assert.deepEqual(checks.notes.map((note) => note.code), ["no_schematic"]);
});

test("a finding's place is the index's page frame, the inverse of the frame a copied point is written in", () => {
  const [clearance, unconnected] = boardChecks(drc, index).findings;
  // KiCad's (15, -10) is where the via is on the page; back through `toScript`, it is KiCad's again.
  assert.deepEqual(clearance.at, index.vias[0].at);
  assert.deepEqual(clearance.at, [22, 18]);
  assert.deepEqual(index.toScript(clearance.at), [15, -10]);
  assert.deepEqual(unconnected.at, index.pads.get("R1.2").at);
  assert.deepEqual(boardCheckMarks(boardChecks(drc, index)), [[22, 18], [17.825, 23]]);
});

test("a finding picks the items the board names, canonically; one with a place and no item, the place; one with neither, nothing", () => {
  const byType = new Map(boardChecks(drc, index).findings.map((finding) => [finding.type, finding]));
  // The zone the board does not name is dropped; the via's reference is the index's spelling of it.
  assert.deepEqual(byType.get("clearance").picks, [VIA, TRACK]);
  assert.deepEqual(byType.get("clearance").items.map((item) => item.selector), [VIA, TRACK, ""]);
  assert.deepEqual(byType.get("unconnected_items").picks, ["#R1.2", OUT]);
  // A copper sliver has no item: its place is a point reference, in KiCad's millimetres, which the index resolves.
  assert.deepEqual(byType.get("copper_sliver").picks, ["#@x20y-20"]);
  assert.deepEqual(index.resolve("#@x20y-20").page, byType.get("copper_sliver").at);
  assert.equal(byType.get("copper_sliver").comment, "accepted: the fab removes slivers");
  // A parity entry with no item and no place is listed, and frames nothing.
  assert.deepEqual([byType.get("missing_footprint").at, byType.get("missing_footprint").picks, byType.get("missing_footprint").box], [null, [], null]);
  assert.deepEqual([byType.get("silk_over_copper").at, byType.get("silk_over_copper").box], [null, null]);
  // One with an item and no place frames the item.
  assert.deepEqual(byType.get("net_conflict").picks, ["#R1.2"]);
  assert.deepEqual(byType.get("net_conflict").box, index.extent(index.resolve("#R1.2")));
});

test("a zoom to a finding frames its place and the small things it is between, never the pour it touches", () => {
  const byType = new Map(boardChecks(drc, index).findings.map((finding) => [finding.type, finding]));
  assert.deepEqual(byType.get("copper_sliver").box, [24, 5, 30, 11]);
  const [x0, y0, x1, y1] = byType.get("clearance").box;
  // 3 mm round the via, and out to the 8 mm track it is too near.
  assert.deepEqual([x0 < 16.175, y0 <= 15, x1, y1 > 23, x1 - x0 < 12], [true, true, 25, true, true]);
  const withPour = JSON.parse(JSON.stringify(drc));
  withPour.measurements.drc[1].items.push({ description: "Zone [GND] on B.Cu", pos: [0, 0], ref: "#zone:7a1c0000-0000-4000-8000-000000000004" });
  const poured = boardChecks(withPour, index).findings[0];
  assert.equal(poured.picks.length, 3);
  assert.deepEqual(poured.box, byType.get("clearance").box);
});

test("a finding is said to an agent as `cad kicad_pcb drc` says it", () => {
  const byType = new Map(boardChecks(drc, index).findings.map((finding) => [finding.type, finding]));
  assert.equal(boardCheckText(byType.get("clearance")),
    "DRC error: clearance at (15, -10) mm: Clearance violation (netclass 'Default' clearance 0.2000 mm; actual 0.0500 mm): "
    + "Via [GND] on F.Cu - B.Cu; Track [VIN] on F.Cu, length 8.0000 mm; Zone [GND] on In1.Cu");
  assert.equal(boardCheckText(byType.get("missing_footprint")), "DRC error: missing_footprint: Missing footprint C3 (100nF)");
  // A chip's few words for it leave the figures out.
  assert.deepEqual([boardCheckTitle(byType.get("clearance")), boardCheckTitle(byType.get("unconnected_items"))], ["Clearance violation", "Missing connection between items"]);
  // A difference from the schematic is the check's error, whatever severity KiCad gave it.
  assert.equal(boardCheckText(byType.get("net_conflict")), "DRC error: net_conflict: Pad net (OUT) doesn't match net given by schematic (SENSE): Pad 2 [OUT] of R1 on F.Cu");
  assert.equal(boardCheckText(byType.get("copper_sliver")), "DRC info: copper_sliver at (20, -20) mm: Copper sliver (B.Cu) (excluded in the project: accepted: the fab removes slivers)");
});

test("a board with warnings alone passes; a check that judged nothing is not checked, with the reason, and never a pass", () => {
  const passing = boardChecks({ ok: true, summary: "OK amp.kicad_pcb: DRC clean (1 warning(s))", findings: [],
    measurements: { drc: [drc.measurements.drc[0]] } }, index);
  assert.deepEqual([passing.verdict, passing.failing, passing.counts.warnings, passing.reason], ["pass", 0, 1, ""]);
  const missing = boardChecks({ ok: false, status: "failed", findings: [{ severity: "error", code: "kicad_missing", message: "KiCad is not installed: install cad[kicad]" }],
    measurements: {} }, index);
  assert.deepEqual([missing.state, missing.verdict, missing.reason, missing.findings.length], ["notChecked", null, "KiCad is not installed: install cad[kicad]", 0]);
  assert.equal(boardChecks({ ok: false, status: "not_checked", reason: "cancelled", findings: [], measurements: { drc: [] } }, index).reason, "cancelled");
  assert.equal(boardChecks(null, index).state, "notChecked");
  // An error the check itself raised, beside KiCad's report, fails the board and is listed.
  const refused = boardChecks({ ok: false, findings: [{ severity: "error", code: "rules_unreadable", message: "amp.kicad_dru does not parse" }], measurements: { drc: [] } }, index);
  assert.deepEqual([refused.verdict, refused.counts.errors, refused.findings[0].description], ["fail", 1, "amp.kicad_dru does not parse"]);
});

test("the marks are pins of one size on screen, at their places, mirrored with the view from the bottom, and only where the pane shows them", () => {
  const calls = [];
  const ctx = new Proxy({}, { get: (_target, key) => (...args) => { calls.push([key, ...args]); }, set: () => true });
  const frame = { transform: { scale: 10, offsetX: 0, offsetY: 0 }, pixelRatio: 2, width: 400, height: 300 };
  const tips = () => calls.filter(([name]) => name === "moveTo").filter((_, at) => at % 2 === 0).map(([, x, y]) => [x, y]);
  assert.equal(drawBoardCheckMarks(ctx, [[22, 18], [17.825, 23], [90, 18]], frame), 2);
  assert.deepEqual(tips(), [[220, 180], [178.25, 230]]);
  // The head keeps its radius whatever the zoom.
  assert.deepEqual(calls.filter(([name]) => name === "arc").map(([, , , radius]) => radius), [8, 1, 8, 1]);
  calls.length = 0;
  assert.equal(drawBoardCheckMarks(ctx, [[22, 18]], { ...frame, mirrorX: 20, transform: { scale: 15, offsetX: 5, offsetY: 0 } }), 1);
  assert.deepEqual(tips(), [[275, 270]]);
  assert.deepEqual(calls.filter(([name]) => name === "arc").map(([, , , radius]) => radius), [8, 1]);
  assert.equal(drawBoardCheckMarks(ctx, [], frame), 0);
});

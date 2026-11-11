import assert from "node:assert/strict";
import test from "node:test";

import { CONTROLS } from "../../../../usage/controls.js";
import { allTicked, filterBadge, filterControl, selects, tickAllKinds, tickFilter } from "./selectFilter.js";

const ORDER = ["parts", "faces", "edges", "position", "annotation", "measurement"];
const KINDS = ["parts", "faces", "edges", "annotation", "measurement"];

test("a box ticks or unticks its own id, in the filter's order; All ticks the kinds alone", () => {
  assert.deepEqual(tickFilter(["edges"], "faces", true, ORDER), ["faces", "edges"]);
  assert.deepEqual(tickFilter(ORDER, "faces", false, ORDER), ["parts", "edges", "position", "annotation", "measurement"]);
  assert.deepEqual(tickFilter(["faces", "nets"], "edges", true, ORDER), ["faces", "edges"], "what the order does not know is dropped");
  // All leaves the extras (Position) as they are: unticked, the kinds go and Position stays.
  assert.deepEqual(tickAllKinds(ORDER, KINDS, false, ORDER), ["position"]);
  assert.deepEqual(tickAllKinds(["position"], KINDS, true, ORDER), ORDER, "every box ticked is the order itself");
  assert.deepEqual(tickAllKinds([], KINDS, true, ORDER), KINDS);
});

test("All's box is ticked when every kind is, a dash when some are", () => {
  assert.equal(allTicked(ORDER, KINDS), true);
  assert.equal(allTicked(["faces", "position"], KINDS), "indeterminate");
  assert.equal(allTicked(["position"], KINDS), false);
});

test("a filter picks what it ticks", () => {
  assert.equal(selects(["faces", "measurement"], "measurement"), true);
  assert.equal(selects(["faces"], "measurement"), false);
  assert.equal(selects([], "faces"), false);
});

test("the strip's badge: none for All, the one kind's glyph, Position's alone, else the funnel", () => {
  const glyphs = { parts: "parts", faces: "faces", edges: "edges", position: "position" };
  const badge = filter => filterBadge(filter, KINDS, { glyphs, alone: "position" });
  assert.equal(badge(ORDER), "all");
  assert.equal(badge(KINDS), "all", "Position unticked is still every kind");
  assert.equal(badge(["faces"]), "faces");
  assert.equal(badge(["faces", "position"]), "faces", "the knobs beside one kind: that kind's");
  assert.equal(badge(["position"]), "position");
  assert.equal(badge(["faces", "edges"]), "filter");
  assert.equal(badge(["annotation"]), "filter", "a kind with no glyph");
  assert.equal(badge([]), "filter");
  assert.equal(filterBadge(["pads"], ["parts", "pads"]), "filter", "a board's kinds have no glyphs");
});

test("every box of every filter is counted by a name telemetry knows, the earlier menus' names among them", () => {
  assert.equal(filterControl("select", "faces"), "select_filter_faces");
  assert.equal(filterControl("measure", "vertex"), "measure_filter_vertices");
  assert.equal(filterControl("select", "ruleAreas"), "select_filter_rule_areas");
  const boxes = {
    select: ["all", "parts", "faces", "edges", "annotation", "measurement", "position", "links",
      "texts", "tracks", "vias", "pads", "graphics", "zones", "ruleAreas", "dimensions", "locked",
      "symbols", "pins", "wires", "labels", "sheets", "other"],
    measure: ["all", "vertex", "edge", "face"],
  };
  for (const [tool, ids] of Object.entries(boxes)) {
    for (const id of ids) assert.ok(CONTROLS.includes(filterControl(tool, id)), `${filterControl(tool, id)} is a control`);
  }
});

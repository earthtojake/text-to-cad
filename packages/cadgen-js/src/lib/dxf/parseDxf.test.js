import assert from "node:assert/strict";
import test from "node:test";

import { parseDxf } from "./parseDxf.js";

function dxfText(lines) {
  return `${lines.join("\n")}\n`;
}

test("parseDxf normalizes closed lwpolyline, circles, and bends", () => {
  const payload = parseDxf(dxfText([
    "0", "SECTION",
    "2", "HEADER",
    "0", "ENDSEC",
    "0", "SECTION",
    "2", "ENTITIES",
    "0", "LWPOLYLINE",
    "8", "CUT",
    "90", "4",
    "70", "1",
    "10", "0",
    "20", "0",
    "10", "10",
    "20", "0",
    "10", "10",
    "20", "5",
    "10", "0",
    "20", "5",
    "0", "CIRCLE",
    "8", "CUT",
    "10", "5",
    "20", "2.5",
    "40", "1",
    "0", "LINE",
    "8", "BEND",
    "10", "3",
    "20", "0",
    "11", "3",
    "21", "5",
    "0", "ENDSEC",
    "0", "EOF"
  ]), { fileRef: "test/panel.dxf" });

  assert.equal(payload.fileRef, "test/panel.dxf");
  assert.equal(payload.defaultThicknessMm, 0);
  assert.equal(payload.bounds.width, 10);
  assert.equal(payload.bounds.height, 5);
  assert.equal(payload.counts.paths, 5);
  assert.equal(payload.counts.circles, 1);
  assert.equal(payload.geometry.lines.length, 5);
  assert.equal(payload.layers.length, 2);
  assert.deepEqual(payload.layers.map((layer) => layer.name), ["BEND", "CUT"]);
});

test("parseDxf converts lwpolyline bulges into arcs", () => {
  const quarterBulge = Math.tan(Math.PI / 8);
  const payload = parseDxf(dxfText([
    "0", "SECTION",
    "2", "ENTITIES",
    "0", "LWPOLYLINE",
    "8", "CUT",
    "90", "4",
    "70", "1",
    "10", "1",
    "20", "0",
    "42", String(quarterBulge),
    "10", "0",
    "20", "1",
    "42", String(quarterBulge),
    "10", "-1",
    "20", "0",
    "42", String(quarterBulge),
    "10", "0",
    "20", "-1",
    "42", String(quarterBulge),
    "0", "ENDSEC",
    "0", "EOF"
  ]), { fileRef: "test/bulged-hole.dxf" });

  assert.equal(payload.counts.paths, 4);
  assert.equal(payload.counts.circles, 0);
  assert.equal(payload.geometry.lines.length, 0);
  assert.equal(payload.geometry.arcs.length, 4);
  assert.equal(payload.bounds.width, 2);
  assert.equal(payload.bounds.height, 2);
  assert.deepEqual(payload.geometry.arcs.map((arc) => arc.radius), [1, 1, 1, 1]);
  assert.deepEqual(payload.geometry.arcs.map((arc) => arc.sweepAngleDeg), [90, 90, 90, 90]);
  assert.match(payload.paths[0].d, /A 1 1 0 0 0 /);
});

test("an ellipse becomes a closed sampled contour", () => {
  const dxf = [
    "0", "SECTION", "2", "ENTITIES",
    "0", "ELLIPSE", "8", "CUT",
    "10", "0", "20", "0",       // centre
    "11", "10", "21", "0",      // major axis vector
    "40", "0.5",                // minor/major ratio
    "41", "0", "42", `${Math.PI * 2}`,
    "0", "ENDSEC", "0", "EOF", "",
  ].join("\n");

  const data = parseDxf(dxf, { fileRef: "e.dxf" });

  assert.ok(data.geometry.lines.length > 8, "sampled into segments");
  const first = data.geometry.lines[0].start;
  const last = data.geometry.lines[data.geometry.lines.length - 1].end;
  assert.ok(Math.hypot(first[0] - last[0], first[1] - last[1]) < 1e-9, "closes on itself");
});

test("a legacy POLYLINE reads its VERTEX entities", () => {
  // Unlike LWPOLYLINE the vertices are separate entities terminated by SEQEND, so the walker
  // has to consume them rather than the entity parser reading them inline.
  const dxf = [
    "0", "SECTION", "2", "ENTITIES",
    "0", "POLYLINE", "8", "CUT", "70", "1",
    "0", "VERTEX", "10", "0", "20", "0",
    "0", "VERTEX", "10", "10", "20", "0",
    "0", "VERTEX", "10", "10", "20", "10",
    "0", "SEQEND",
    "0", "ENDSEC", "0", "EOF", "",
  ].join("\n");

  const data = parseDxf(dxf, { fileRef: "p.dxf" });

  // Three vertices, closed flag set -> three segments.
  assert.equal(data.geometry.lines.length, 3);
});

test("an INSERT places its block's geometry", () => {
  const dxf = [
    "0", "SECTION", "2", "BLOCKS",
    "0", "BLOCK", "2", "SQ",
    "0", "LINE", "8", "CUT", "10", "0", "20", "0", "11", "1", "21", "0",
    "0", "ENDBLK",
    "0", "ENDSEC",
    "0", "SECTION", "2", "ENTITIES",
    "0", "INSERT", "2", "SQ", "10", "5", "20", "7",
    "0", "ENDSEC", "0", "EOF", "",
  ].join("\n");

  const data = parseDxf(dxf, { fileRef: "i.dxf" });

  assert.equal(data.geometry.lines.length, 1);
  assert.deepEqual(data.geometry.lines[0].start, [5, 7], "translated by the insertion point");
});

test("a missing block is empty rather than fatal", () => {
  // Drawings reference blocks they no longer define; one dangling name must not cost the
  // whole profile.
  const dxf = [
    "0", "SECTION", "2", "ENTITIES",
    "0", "LINE", "8", "CUT", "10", "0", "20", "0", "11", "1", "21", "1",
    "0", "INSERT", "2", "GONE", "10", "0", "20", "0",
    "0", "ENDSEC", "0", "EOF", "",
  ].join("\n");

  assert.equal(parseDxf(dxf, { fileRef: "m.dxf" }).geometry.lines.length, 1);
});

test("annotation entities are skipped, not rejected", () => {
  // A drawing is not unrenderable because it is dimensioned. Rejecting it over a DIMENSION
  // is how a perfectly cuttable profile ends up showing an error card.
  const dxf = [
    "0", "SECTION", "2", "ENTITIES",
    "0", "LINE", "8", "CUT", "10", "0", "20", "0", "11", "1", "21", "1",
    "0", "DIMENSION", "8", "DIMS", "10", "0", "20", "0",
    "0", "MTEXT", "8", "NOTES", "1", "hello",
    "0", "ENDSEC", "0", "EOF", "",
  ].join("\n");

  assert.equal(parseDxf(dxf, { fileRef: "a.dxf" }).geometry.lines.length, 1);
});

test("a genuinely unknown entity is still reported", () => {
  const dxf = [
    "0", "SECTION", "2", "ENTITIES",
    "0", "NOTAREALENTITY", "8", "CUT",
    "0", "ENDSEC", "0", "EOF", "",
  ].join("\n");

  assert.throws(() => parseDxf(dxf, { fileRef: "u.dxf" }), /Unsupported DXF entity NOTAREALENTITY/u);
});

test("$INSUNITS scales geometry to millimetres", () => {
  const inches = parseDxf(dxfText([
    "0", "SECTION", "2", "HEADER",
    "9", "$INSUNITS", "70", "1",
    "0", "ENDSEC",
    "0", "SECTION", "2", "ENTITIES",
    "0", "LWPOLYLINE", "8", "CUT", "90", "4", "70", "1",
    "10", "0", "20", "0",
    "10", "2", "20", "0",
    "10", "2", "20", "1",
    "10", "0", "20", "1",
    "0", "ENDSEC", "0", "EOF"
  ]));
  assert.equal(inches.unitsScaleMm, 25.4);
  assert.equal(inches.bounds.width, 50.8, "a 2-inch blank is 50.8 mm wide");
  assert.equal(inches.bounds.height, 25.4);
});

test("TEXT and MTEXT parse into flat text markings", () => {
  const parsed = parseDxf(dxfText([
    "0", "SECTION", "2", "ENTITIES",
    "0", "LWPOLYLINE", "8", "CUT", "90", "4", "70", "1",
    "10", "0", "20", "0",
    "10", "100", "20", "0",
    "10", "100", "20", "50",
    "10", "0", "20", "50",
    "0", "TEXT", "8", "ENGRAVE",
    "10", "10", "20", "20", "40", "5", "50", "15",
    "1", "SN-042",
    "0", "MTEXT", "8", "NOTES",
    "10", "10", "20", "40", "40", "3",
    "1", "{\\fArial|b0;Handle}\\Pwith care %%d",
    "0", "ENDSEC", "0", "EOF"
  ]));
  assert.equal(parsed.geometry.texts.length, 2);
  const [label, note] = parsed.geometry.texts;
  assert.equal(label.value, "SN-042");
  assert.deepEqual(label.position, [10, 20]);
  assert.equal(label.heightMm, 5);
  assert.equal(label.rotationDeg, 15);
  assert.equal(label.kind, "engrave");
  assert.equal(note.value, "Handle\nwith care °");
  assert.equal(note.kind, "reference");
});

test("the LAYER table's colors reach the layer summary", () => {
  const parsed = parseDxf(dxfText([
    "0", "SECTION", "2", "TABLES",
    "0", "TABLE", "2", "LAYER",
    "0", "LAYER", "2", "CUT", "62", "1",
    "0", "LAYER", "2", "BEND", "62", "5",
    "0", "ENDTAB",
    "0", "ENDSEC",
    "0", "SECTION", "2", "ENTITIES",
    "0", "LWPOLYLINE", "8", "CUT", "90", "4", "70", "1",
    "10", "0", "20", "0",
    "10", "10", "20", "0",
    "10", "10", "20", "10",
    "10", "0", "20", "10",
    "0", "LINE", "8", "BEND",
    "10", "5", "20", "0", "11", "5", "21", "10",
    "0", "ENDSEC", "0", "EOF"
  ]));
  const byName = new Map(parsed.layers.map((layer) => [layer.name, layer]));
  assert.equal(byName.get("CUT").colorAci, 1);
  assert.equal(byName.get("CUT").colorHex, "#ff3b30");
  assert.equal(byName.get("BEND").colorHex, "#3a5cff");
  assert.equal(byName.get("CUT").visibleDefault, true);
});

test("a HATCH's seed point is not read as another boundary vertex", () => {
  // A seed point is written as a 10/20 pair like a boundary vertex, but it lives after the
  // pattern definition (code 75 opens that tail, 98 counts the seeds) and may sit anywhere on
  // the drawing. Reading to the end of the entity drags the seed into the boundary, which in
  // a real fixture put a vertex 62 m off a 1.8 m sheet and reduced the drawing to a speck
  // under auto-fit. The bounds below are the assertion that matters.
  const parsed = parseDxf(dxfText([
    "0", "SECTION", "2", "ENTITIES",
    "0", "HATCH",
    "8", "FILL",
    "91", "1",
    "92", "1",
    "72", "0",
    "93", "4",
    "10", "0", "20", "0",
    "10", "10", "20", "0",
    "10", "10", "20", "10",
    "10", "0", "20", "10",
    "97", "0",
    // Pattern definition and seed data — everything below must be ignored.
    "75", "0",
    "76", "1",
    "52", "0",
    "41", "1",
    "77", "0",
    "78", "1",
    "53", "45",
    "43", "-2438.5", "44", "856.8",
    "45", "-0.22", "46", "0.22",
    "79", "0",
    "98", "1",
    "10", "-2438.5", "20", "856.8",
    "0", "ENDSEC", "0", "EOF"
  ]));

  assert.equal(parsed.bounds.width, 10, "the seed point must not widen the drawing");
  assert.equal(parsed.bounds.height, 10, "the seed point must not heighten the drawing");
  for (const line of parsed.geometry.lines) {
    for (const point of [line.start, line.end]) {
      assert.ok(
        point[0] >= 0 && point[0] <= 10 && point[1] >= 0 && point[1] <= 10,
        `hatch boundary escaped the square: ${JSON.stringify(point)}`
      );
    }
  }
});

import assert from "node:assert/strict";
import test from "node:test";

import { parseDxf } from "./parseDxf.js";

function dxfText(lines) {
  return `${lines.join("\n")}\n`;
}

function assertNear(actual, expected, epsilon = 1e-6) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} should be within ${epsilon} of ${expected}`);
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
  const payload = parseDxf(dxfText([
    "0", "SECTION",
    "2", "ENTITIES",
    "0", "LWPOLYLINE",
    "8", "CUT",
    "90", "2",
    "70", "0",
    "10", "1",
    "20", "0",
    "42", String(Math.tan(Math.PI / 8)),
    "10", "0",
    "20", "1",
    "0", "ENDSEC",
    "0", "EOF"
  ]));

  assert.equal(payload.geometry.lines.length, 0);
  assert.equal(payload.geometry.arcs.length, 1);
  assert.equal(payload.counts.paths, 1);
  assert.match(payload.paths[0].d, /\bA\b/);
  const arc = payload.geometry.arcs[0];
  assertNear(arc.center[0], 0);
  assertNear(arc.center[1], 0);
  assertNear(arc.radius, 1);
  assertNear(arc.startAngleDeg, 0);
  assertNear(arc.sweepAngleDeg, 90);
});

test("parseDxf supports clockwise lwpolyline bulges", () => {
  const payload = parseDxf(dxfText([
    "0", "SECTION",
    "2", "ENTITIES",
    "0", "LWPOLYLINE",
    "8", "CUT",
    "90", "2",
    "70", "0",
    "10", "1",
    "20", "0",
    "42", String(-Math.tan(Math.PI / 8)),
    "10", "0",
    "20", "-1",
    "0", "ENDSEC",
    "0", "EOF"
  ]));

  assert.equal(payload.geometry.lines.length, 0);
  assert.equal(payload.geometry.arcs.length, 1);
  const arc = payload.geometry.arcs[0];
  assertNear(arc.center[0], 0);
  assertNear(arc.center[1], 0);
  assertNear(arc.radius, 1);
  assertNear(arc.startAngleDeg, 270);
  assertNear(arc.sweepAngleDeg, 90);
});

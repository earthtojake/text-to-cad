import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { GLYPHS, glyphStrokes, parseMarkup, textStrokes } from "./strokeFont.js";

// KiCad's markup as both sides read and draw it: the Python suite asserts the same cases.
const PARITY = JSON.parse(readFileSync(new URL("./strokeFont.parity.json", import.meta.url), "utf8"));

// The engine's `stroke_font` and this port lay text out point for point (the Python suite holds the
// two glyph tables equal): the same numbers its StrokeFontTest reads.
const extent = (strokes) => {
  const points = strokes.flat();
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)].map((value) => Math.round(value * 1000) / 1000);
};

test("the font covers ASCII and stands a capital at the text size, as the engine's does", () => {
  assert.equal(GLYPHS.length, 95);
  const { left, right, strokes } = glyphStrokes("H");
  assert.deepEqual([left, right, strokes.length], [-11, 11, 3]);
  assert.deepEqual(extent(textStrokes("H", { size: [1, 1], at: [10, 20] })), [9.667, 19.5, 10.333, 20.5]);
  assert.deepEqual(extent(textStrokes("H", { size: [1, 1], at: [10, 20], justify: ["left", "top"] })), [10.19, 20, 10.857, 21]);
  assert.deepEqual(extent(textStrokes("H", { size: [2, 1], at: [0, 0] })), [-0.333, -1, 0.333, 1]);
  // Turned a quarter turn the text stands along y; mirrored it reads the other way; italic leans right.
  const turned = extent(textStrokes("H", { size: [1, 1], at: [10, 20], angle: 90 }));
  assert.equal(Math.round((turned[2] - turned[0]) * 1000) / 1000, 1);
  const plain = extent(textStrokes("L", { size: [1, 1], justify: ["left"] }));
  assert.equal(plain[0], -extent(textStrokes("L", { size: [1, 1], justify: ["left"], mirror: true }))[2]);
  const [upright] = textStrokes("l", { size: [1, 1] });
  const [leaning] = textStrokes("l", { size: [1, 1], italic: true });
  assert.ok(leaning[0][0] - leaning.at(-1)[0] > upright[0][0] - upright.at(-1)[0], "the top of an italic stroke leans right");
  // A character the font lacks is a box, and an empty size draws nothing.
  assert.equal(textStrokes("é", { size: [1, 1] }).length, 1);
  assert.deepEqual(textStrokes("x", { size: [0, 0] }), []);
});

test("KiCad's markup reads and draws as the engine's does: overbars, sub- and superscripts, the rest as written", () => {
  for (const { text, runs } of PARITY.markupCases) assert.deepEqual(parseMarkup(text), runs, text);
  for (const { text, options, strokes } of PARITY.strokeCases) {
    const laid = textStrokes(text, { ...options, markup: true });
    assert.deepEqual(laid.map((stroke) => stroke.length), strokes.map((stroke) => stroke.length), text);
    laid.flat().forEach(([x, y], index) => {
      const [ex, ey] = strokes.flat()[index];
      assert.ok(Math.abs(x - ex) <= 2e-6 && Math.abs(y - ey) <= 2e-6, `${text}: ${[x, y]} against ${[ex, ey]}`);
    });
  }
  // Without markup the markers are letters; with it, `~{EN}` is EN's letters and one bar over them.
  assert.equal(textStrokes("~{EN}", { size: [1, 1], markup: true }).length, textStrokes("EN", { size: [1, 1] }).length + 1);
  assert.ok(textStrokes("~{EN}", { size: [1, 1] }).length > textStrokes("~{EN}", { size: [1, 1], markup: true }).length);
  assert.deepEqual(parseMarkup("~{".repeat(1000)), ["~{".repeat(1000)]);
});

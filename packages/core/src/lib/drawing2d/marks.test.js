import assert from "node:assert/strict";
import test from "node:test";

import { drawAnnotationMarks } from "./marks.js";

// What a stroke is drawn as: each stroke's colour and width, in order.
function strokes() {
  const drawn = [];
  const ctx = new Proxy({ drawn }, {
    get: (target, key) => (key in target ? target[key] : key === "stroke" ? () => drawn.push([target.strokeStyle, target.lineWidth]) : () => {}),
    set: (target, key, value) => { target[key] = value; return true; }
  });
  return ctx;
}
const mark = (id, opacity = 1) => ({ id, kind: "stroke", color: "#ff1744", width: 2, opacity, points: [0, 0, 0, 10, 0, 0] });

// Red ink over a board's red copper reads by its keyline: a contrasting edge under each opaque mark,
// as wide each side as asked; a translucent mark (the highlighter's) has none.
test("a keyline edges each opaque mark in its colour, under the ink, and leaves a translucent one alone", () => {
  const transform = { scale: 1, offsetX: 0, offsetY: 0 };
  const plain = strokes();
  drawAnnotationMarks(plain, [mark("a")], { transform });
  assert.deepEqual(plain.drawn, [["#ff1744", 2]]);
  const edged = strokes();
  drawAnnotationMarks(edged, [mark("a"), mark("b", 0.35)], { transform, keyline: { color: "rgba(0, 0, 0, 0.85)", width: 1.25 } });
  assert.deepEqual(edged.drawn, [["rgba(0, 0, 0, 0.85)", 4.5], ["#ff1744", 2], ["#ff1744", 2]]);
});

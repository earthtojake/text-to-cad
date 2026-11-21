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

// A stroke's line style on a 2D canvas: its pattern from `dashPattern` (screen pixels, scaled with its width), and a
// mark without one solid, as every mark before there were line styles.
test("a dashed or dotted stroke is drawn in its pattern, an old one solid; the pen's pattern runs on from segment to segment", () => {
  const transform = { scale: 1, offsetX: 0, offsetY: 0 };
  const dashes = style => {
    const seen = [];
    const ctx = new Proxy({}, {
      get: (target, key) => (key in target ? target[key] : key === "setLineDash" ? pattern => seen.push(["dash", [...pattern]])
        : key === "stroke" ? () => seen.push(["stroke", target.lineDashOffset]) : () => {}),
      set: (target, key, value) => { target[key] = value; return true; }
    });
    drawAnnotationMarks(ctx, [{ ...mark("a"), ...style }], { transform });
    return seen;
  };
  assert.deepEqual(dashes({}).filter(([kind]) => kind === "dash").map(([, pattern]) => pattern), [[], []]);
  assert.deepEqual(dashes({ dash: "dashed" })[0], ["dash", [8, 6]]);
  assert.deepEqual(dashes({ dash: "dotted" })[0], ["dash", [0.001, 4]]);
  // The pen's widths draw segment by segment: each starts where the pattern left off.
  const pen = dashes({ dash: "dashed", points: [0, 0, 0, 5, 0, 0, 12, 0, 0], widths: [1, 1, 1] });
  assert.deepEqual(pen.filter(([kind]) => kind === "stroke").map(([, offset]) => offset), [0, 5]);
});

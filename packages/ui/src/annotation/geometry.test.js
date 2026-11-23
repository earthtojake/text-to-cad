import assert from "node:assert/strict";
import test from "node:test";
import { annotationsInBox } from "./geometry.js";

// Marks on the screen, in pixels: a stroke 6px wide along y = 20 from x = 10 to 50, a filled area 60..80 x 60..80.
const stroke = { id: "s", kind: "stroke", width: 6, points: [{ x: 10, y: 20 }, { x: 50, y: 20 }] };
const area = { id: "a", kind: "area", points: [{ x: 60, y: 60 }, { x: 80, y: 60 }, { x: 80, y: 80 }, { x: 60, y: 80 }] };
const inks = [stroke, area];
const ids = box => annotationsInBox(box, inks).map(ink => ink.id);

test("a box takes the ink it touches, a stroke by its drawn width and an area anywhere over it", () => {
  assert.deepEqual(ids({ left: 20, top: 0, right: 30, bottom: 18 }), ["s"], "2px above the stroke's middle, inside its width");
  assert.deepEqual(ids({ left: 65, top: 65, right: 70, bottom: 70 }), ["a"], "inside the area");
  assert.deepEqual(ids({ left: 20, top: 0, right: 30, bottom: 15 }), []);
});

// Every stroke a tool puts down is solid: no mark carries a line style.
test("the pen, the highlighter and the shapes put down solid strokes", async () => {
  const { highlighterMark, penMark, shapeMarks } = await import("./geometry.js");
  const from = { x: 0, y: 0 }, to = { x: 100, y: 0 };
  const style = { color: "#ff2d55", width: 2 };
  const marks = [penMark([from, to], style), highlighterMark([from, to], style), ...shapeMarks("rectangle", from, { x: 50, y: 40 }, style),
    ...shapeMarks("arrow", from, to, style)];
  assert.equal(marks.length, 6);
  assert.deepEqual(marks.map(mark => "dash" in mark), [false, false, false, false, false, false]);
});

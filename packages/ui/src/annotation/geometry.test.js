import assert from "node:assert/strict";
import test from "node:test";
import { annotationsInBox, FILL_LOOP_GAP_PX, fillableOutline, fillTargetAt } from "./geometry.js";

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


// A line style is a stroke's: the pen's and a shape's outline carry it, an arrow's head stays solid, the highlighter
// has none; solid is no field at all, as every mark before there were line styles.
test("a stroke carries its line style, an arrow's shaft and not its head, and solid is no field", async () => {
  const { highlighterMark, penMark, shapeMarks } = await import("./geometry.js");
  const from = { x: 0, y: 0 }, to = { x: 100, y: 0 };
  assert.equal(penMark([from, to], { color: "#ff2d55", width: 2, dash: "dotted" }).dash, "dotted");
  assert.equal("dash" in penMark([from, to], { color: "#ff2d55", width: 2, dash: "solid" }), false);
  assert.equal("dash" in highlighterMark([from, to], { color: "#ffe600", width: 2, dash: "dashed" }), false);
  assert.equal(shapeMarks("rectangle", from, { x: 50, y: 40 }, { color: "#ff2d55", width: 2, dash: "dashed" })[0].dash, "dashed");
  const [shaft, ...head] = shapeMarks("arrow", from, to, { color: "#ff2d55", width: 2, dash: "dashed" });
  assert.deepEqual([shaft.dash, head.map(wing => "dash" in wing)], ["dashed", [false, false]]);
});

// A freehand loop is closed to Fill where its ends meet on the screen NOW: the same stroke counts zoomed out, where its
// gap is small on the screen, and not zoomed in, where it is wide. A line, or an arrow's short head, encloses nothing.
test("a freehand stroke is a fillable outline when its ends are under the gap apart on the screen, at the zoom it is seen at", () => {
  const circle = (scale, gap) => Array.from({ length: 48 }, (_, i) => {
    const turn = (i / 47) * (2 * Math.PI - gap / 40);
    return { x: scale * (100 + 40 * Math.cos(turn)), y: scale * (100 + 40 * Math.sin(turn)) };
  });
  const ink = points => ({ id: "p", kind: "stroke", closed: false, width: 3, points });
  assert.equal(FILL_LOOP_GAP_PX, 20);
  assert.equal(fillableOutline(ink(circle(1, 15))), true, "15px apart");
  assert.equal(fillableOutline(ink(circle(1, 25))), false, "25px apart");
  assert.equal(fillableOutline(ink(circle(0.5, 25))), true, "the same stroke zoomed out: 12.5px apart");
  assert.equal(fillableOutline(ink(circle(2, 15))), false, "zoomed in: 30px apart");
  assert.equal(fillableOutline(ink([{ x: 0, y: 0 }, { x: 6, y: 6 }, { x: 12, y: 12 }])), false, "a short straight stroke encloses nothing");
  assert.equal(fillableOutline({ id: "a", kind: "area", closed: true, width: 0, points: circle(1, 0) }), false, "a fill is no outline");
  assert.equal(fillableOutline({ ...ink(circle(1, 200)), closed: true }), true, "a shape drawn closed");
});

test("a Fill press takes the last drawn outline it is inside or on the line of, seeding inside only where clear of the ink", () => {
  const square = (id, a, b) => ({ id, kind: "stroke", closed: true, width: 4,
    points: [{ x: a, y: a }, { x: b, y: a }, { x: b, y: b }, { x: a, y: b }] });
  const inks = [square("outer", 0, 100), square("inner", 25, 75)];
  const at = (x, y) => { const target = fillTargetAt({ x, y }, inks); return target && [target.id, target.seed]; };
  assert.deepEqual(at(50, 50), ["inner", { x: 50, y: 50 }]);
  assert.deepEqual(at(10, 50), ["outer", { x: 10, y: 50 }]);
  assert.deepEqual(at(50, 23), ["inner", null], "just outside the inner line, within its hit width");
  assert.deepEqual(at(50, -6), ["outer", null], "outside the outer line, within its hit width");
  assert.equal(at(50, -12), null);
});

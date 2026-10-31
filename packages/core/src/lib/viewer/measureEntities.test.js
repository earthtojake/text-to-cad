import assert from "node:assert/strict";
import test from "node:test";

import { measureEntityPair, pickEntityKey } from "./measureEntities.js";
import { measurementFromPicks } from "./measurement.js";
import { measureLabelText } from "./measureDimension.js";

// A 100 x 60 x 8 plate on z = 0..8, as Measure's picks of it arrive: a point where the viewer drew
// it, the face's or edge's reference, and the edge's polyline.
const plane = (id, point, normal) => ({ point, snapKind: "face", referenceId: id, reference: { pickData: { surfaceType: "PLANE", normal } } });
const top = (point = [50, 30, 8]) => plane("top", point, [0, 0, 1]);
const bottom = (point = [20, 10, 0]) => plane("bottom", point, [0, 0, -1]);
const side = (point = [0, 30, 4]) => plane("side", point, [-1, 0, 0]);
const vertex = point => ({ point, snapKind: "vertex", referenceId: "e1" });
const line = (id, a, b, at) => ({ point: at, snapKind: "edge", referenceId: id, geometry: { kind: "line", direction: a.map((value, axis) => b[axis] - value) }, segments: [...a, ...b] });
const rim = (id, center, radius) => ({ point: [center[0] + radius, center[1], center[2]], snapKind: "edge", referenceId: id,
  geometry: { kind: "arc", radius, center }, reference: { pickData: { params: { center, radius, axis: [0, 0, 1] } } } });
const bore = (id, origin, radius, at) => ({ point: at, snapKind: "face", referenceId: id,
  reference: { pickData: { surfaceType: "CYLINDER", params: { origin, axis: [0, 0, 1], radius } } } });
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} is not ${expected}`);

test("what two entities measure follows from the pair, not from where on each the pointer was", () => {
  const thickness = measureEntityPair(top([90, 50, 8]), bottom([5, 5, 0]));
  assert.equal(thickness.kind, "normal");
  near(thickness.distance, 8);
  assert.deepEqual(thickness.end, [90, 50, 0], "drawn square to the faces, from the first pick");
  assert.deepEqual([measureEntityPair(top(), side()).kind, measureEntityPair(top(), side()).angleDeg], ["angle", 90]);
  const corner = measureEntityPair(vertex([0, 0, 8]), vertex([100, 60, 0]));
  assert.equal(corner.kind, "distance");
  near(corner.distance, Math.hypot(100, 60, 8));
  near(measureEntityPair(vertex([100, 60, 8]), bottom()).distance, 8);
});

test("holes are measured by their centres and axes, as a CAD tool locates them", () => {
  const spacing = measureEntityPair(rim("h1", [20, 30, 8], 3), rim("h2", [80, 30, 8], 5));
  assert.deepEqual([spacing.kind, spacing.distance], ["centers", 60]);
  assert.deepEqual([spacing.start, spacing.end], [[20, 30, 8], [80, 30, 8]]);
  const fromSide = measureEntityPair(rim("h1", [20, 30, 8], 3), side());
  assert.deepEqual([fromSide.kind, fromSide.distance], ["normal", 20], "the hole's centre from the side face, not its rim");
  near(measureEntityPair(bore("b1", [20, 30, 0], 3, [23, 30, 4]), side()).distance, 20);
  near(measureEntityPair(bore("b1", [20, 30, 0], 3, [23, 30, 4]), bore("b2", [80, 30, 0], 5, [75, 30, 4])).distance, 60);
  near(measureEntityPair(vertex([0, 0, 8]), rim("h1", [20, 30, 8], 3)).distance, Math.hypot(20, 30));
  near(measureEntityPair(vertex([0, 30, 4]), bore("b1", [20, 30, 0], 3, [23, 30, 4])).distance, 20);
  const edge = line("e9", [0, 0, 8], [100, 0, 8], [40, 0, 8]);
  near(measureEntityPair(rim("h1", [20, 30, 8], 3), edge).distance, 30);
});

test("straight edges read as an angle, or square across when parallel", () => {
  const front = line("front", [0, 0, 8], [100, 0, 8], [30, 0, 8]);
  const back = line("back", [0, 60, 8], [100, 60, 8], [70, 60, 8]);
  const left = line("left", [0, 0, 8], [0, 60, 8], [0, 20, 8]);
  assert.deepEqual([measureEntityPair(front, back).kind, measureEntityPair(front, back).distance], ["normal", 60]);
  assert.deepEqual([measureEntityPair(front, left).kind, measureEntityPair(front, left).angleDeg, measureEntityPair(front, left).distance], ["angle", 90, 0]);
  near(measureEntityPair(back, bottom()).distance, 8);
});

test("a pair with no gap between it reads as the two points picked, never a 0.00 mm reading", () => {
  const front = line("front", [0, 0, 8], [100, 0, 8], [30, 0, 8]);
  assert.equal(measureEntityPair(front, top()), null, "an edge lying in the face");
  assert.equal(measureEntityPair(vertex([0, 0, 8]), top()), null, "a vertex on the face");
  assert.equal(measureEntityPair(top([10, 10, 8]), top([90, 50, 8])), null, "one face twice");
  assert.equal(measureEntityPair(top(), plane("boss", [10, 10, 8], [0, 0, 1])), null, "two flats at one height");
  const along = measurementFromPicks(top([10, 10, 8]), top([13, 14, 8]));
  assert.deepEqual([along.kind, along.euclidean, measureLabelText(along)], ["points", 5, "5.00 mm"]);
});

test("a reading is labelled by what it is, and the viewer's re-centring is taken out and put back", () => {
  assert.equal(measureLabelText(measurementFromPicks(top(), bottom())), "⟂ 8.00 mm");
  assert.equal(measureLabelText(measurementFromPicks(rim("h1", [20, 30, 8], 3), rim("h2", [80, 30, 8], 5))), "C-C 60.00 mm");
  assert.equal(measureLabelText(measurementFromPicks(top(), side())), "∠ 90.0°");
  // Drawn 50 mm off the model's own frame: the exact centres are the model's, the points the viewer's.
  const offset = [50, 0, 0];
  const shifted = pick => ({ ...pick, point: pick.point.map((value, axis) => value + offset[axis]), offset });
  const spacing = measureEntityPair(shifted(rim("h1", [20, 30, 8], 3)), shifted(rim("h2", [80, 30, 8], 5)));
  assert.deepEqual([spacing.distance, spacing.start, spacing.end], [60, [70, 30, 8], [130, 30, 8]]);
});

test("an entity's key tells a second press on what is held from a press on something else", () => {
  assert.equal(pickEntityKey(top([1, 2, 8])), pickEntityKey(top([90, 50, 8])), "a face, wherever on it");
  assert.notEqual(pickEntityKey(top()), pickEntityKey(bottom()));
  assert.equal(pickEntityKey(vertex([0, 0, 8])), pickEntityKey(vertex([0, 0, 8])));
  assert.notEqual(pickEntityKey(vertex([0, 0, 8])), pickEntityKey(vertex([100, 0, 8])), "two ends of one edge are two vertices");
  assert.equal(pickEntityKey({ point: [0, 0, 0], snapKind: "free" }), null, "a free point is no entity");
});

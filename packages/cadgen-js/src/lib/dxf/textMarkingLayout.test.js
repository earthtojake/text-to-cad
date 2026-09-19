import assert from "node:assert/strict";
import test from "node:test";

import { textMarkingCenter } from "./textMarkingLayout.js";

const box = { heightMm: 4, planeWidth: 20, planeHeight: 5, baselineFraction: 0.2 };

test("baseline-left is the format default: the box hangs right and up from the anchor", () => {
  const center = textMarkingCenter({ anchor: [10, 10], ...box });
  // Half a width along, and (0.5 - 0.2) * 5 = 1.5 above the baseline.
  assert.deepEqual(center.map((v) => Number(v.toFixed(6))), [20, 11.5]);
});

test("a middle-centre anchor, the dimension-value case, is the box centre less half the cap height", () => {
  const center = textMarkingCenter({ anchor: [10, 10], hAlign: "center", vAlign: "middle", ...box });
  // Anchor is 2 mm above the baseline; centre is 1.5 mm above the baseline.
  assert.deepEqual(center.map((v) => Number(v.toFixed(6))), [10, 9.5]);
});

test("right and top alignments move the box left and down", () => {
  const center = textMarkingCenter({ anchor: [10, 10], hAlign: "right", vAlign: "top", ...box });
  assert.deepEqual(center.map((v) => Number(v.toFixed(6))), [0, 7.5]);
});

test("rotation turns the offsets with the text", () => {
  const center = textMarkingCenter({ anchor: [0, 0], rotationDeg: 90, ...box });
  // "Along" (+10) now points +Y; "across" (+1.5) now points -X.
  assert.deepEqual(center.map((v) => Number(v.toFixed(6))), [-1.5, 10]);
});

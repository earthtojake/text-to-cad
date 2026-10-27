import assert from "node:assert/strict";
import test from "node:test";

import { boardAnnotationDocument, boardAnnotationSurface } from "./boardAnnotation.js";

// A 40 x 30 mm sheet at the page origin, drawn 10 px to the millimetre: the plan's y is the sheet's
// negated, so the sheet's top-left corner (0, 0) is on screen at (20, 10) and y runs down the pane.
const TRANSFORM = Object.freeze({ scale: 10, offsetX: 20, offsetY: 10 });
const MIRROR = 20; // the sheet's vertical centre line: where the board is mirrored about from below
const STROKE = Object.freeze({ id: "1", kind: "stroke", color: "#ff00ff", width: 4, opacity: 1, dash: "solid", closed: false,
  points: [{ x: 70, y: 60 }, { x: 170, y: 60 }] });

const surfaceOn = (mirrorX) => boardAnnotationSurface({ transform: () => TRANSFORM, mirrorX: () => mirrorX, canvas: () => null });
const sheetPoints = (item) => [...item.points].map((value) => Math.round(value * 1000) / 1000);

test("ink lies on the board in the sheet's millimetres, on no part: where it was drawn from the top, mirrored from below", () => {
  const [top] = surfaceOn(null).place([STROKE]);
  assert.equal(top.part, null);
  assert.deepEqual(sheetPoints(top), [5, 5, 0, 15, 5, 0]);
  // The same screen stroke over the board seen from below marks the mirrored place on the sheet.
  const [below] = surfaceOn(MIRROR).place([STROKE]);
  assert.deepEqual(sheetPoints(below), [35, 5, 0, 25, 5, 0]);
  // Either comes back to the screen where it was drawn, through the side it was drawn from.
  for (const [mirrorX, item] of [[null, top], [MIRROR, below]]) {
    const [shown] = surfaceOn(mirrorX).onScreen([item]);
    assert.deepEqual(shown.points.map(({ x, y }) => [Math.round(x), Math.round(y)]), [[70, 60], [170, 60]]);
  }
  // The file a prompt carries says its units, and there is none without ink.
  assert.equal(boardAnnotationDocument([top]).units, "mm");
  assert.equal(boardAnnotationDocument([]), null);
});

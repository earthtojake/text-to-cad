import assert from "node:assert/strict";
import test from "node:test";

import {
  draftDimensionFromPicks,
  drawingEditParams,
  drawingEditSnippet,
  drawingEditsPromptText,
  nearestView,
  sheetToModel,
  viewAtSheetPoint
} from "./drawingEdits.js";

// A front view at 1:2: model x -> sheet x, model z -> sheet y, model y along the line of sight.
const front = { name: "front", minX: 80, minY: 40, maxX: 140, maxY: 60, at: [110, 50], map: [110, 45, 0.5, 0, 0, 0, 0, 0.5] };
const top = { name: "top", minX: 80, minY: 100, maxX: 140, maxY: 130, at: [110, 115], map: null };

test("a sheet point goes back to the two model coordinates the view shows", () => {
  assert.deepEqual(sheetToModel(front, [110, 45]), [0, 0, 0]);
  assert.deepEqual(sheetToModel(front, [130, 50]), [40, 0, 10]);
  assert.equal(sheetToModel(top, [110, 115]), null);
});

test("the view under a point, with a margin for dimension lines", () => {
  assert.equal(viewAtSheetPoint([front, top], [100, 50])?.name, "front");
  assert.equal(viewAtSheetPoint([front, top], [100, 62])?.name, "front");
  assert.equal(viewAtSheetPoint([front, top], [100, 80]), null);
  assert.equal(nearestView([front, top], [100, 80])?.name, "front");
  assert.equal(nearestView([front, top], [100, 95])?.name, "top");
});

test("a draft dimension picks its orientation and lands outside the nearer edge", () => {
  const draft = draftDimensionFromPicks(front, [90, 58], [130, 58]);
  assert.equal(draft.orientation, "h");
  assert.equal(draft.offset, 14);
  const vertical = draftDimensionFromPicks(front, [85, 42], [85, 58]);
  assert.equal(vertical.orientation, "v");
  assert.equal(vertical.offset, -17);
});

test("staged edits become preview parameters, moves carried into drafts", () => {
  const edits = [
    { kind: "move", view: "front", dx: 10, dy: 0 },
    { kind: "move", view: "front", dx: -4, dy: 5 },
    { kind: "dim", view: "front", x1: 90, y1: 58, x2: 130, y2: 58, offset: 14, orientation: "h" },
    { kind: "tol", view: "front", index: "0", spec: "±0.1" },
    { kind: "tol", view: "top", index: "1", spec: "" }
  ];
  assert.deepEqual(drawingEditParams(edits, { highlight: "front:0" }), {
    move: "front:6,5",
    dim: "96,63,136,63,14,h",
    tol: "front:0=±0.1",
    hl: "front:0"
  });
  assert.deepEqual(drawingEditParams([]), {});
});

test("snippets speak the drawing API and the prompt lists them", () => {
  const views = [front, top];
  const dimensions = [{ kind: "dimension", view: "front", index: "0", value: "34", position: [0, 0] }];
  assert.equal(
    drawingEditSnippet({ kind: "dim", view: "front", x1: 110, y1: 45, x2: 130, y2: 50, offset: 14, orientation: "h" }, { views }),
    'front.dim((0, 0, 0), (40, 0, 10), offset=14, orientation="h")  # model mm; the coordinate along the view\'s line of sight is 0'
  );
  assert.match(drawingEditSnippet({ kind: "move", view: "front", dx: 10, dy: -5 }, { views }), /at=\(120, 45\)/);
  assert.match(drawingEditSnippet({ kind: "move", view: "top", dx: 10, dy: -5 }, { views: [] }), /by \(10, -5\)/);
  assert.equal(
    drawingEditSnippet({ kind: "tol", view: "front", index: "0", spec: "±0.1" }, { views, dimensions }),
    "In the `front` view, its 1st dim()/hole() call (reads 34): add tol=0.1."
  );
  assert.match(drawingEditSnippet({ kind: "tol", view: "front", index: "2", spec: "0.05/0.02" }, { views }), /tol=\(0\.05, 0\.02\)/);
  assert.match(drawingEditSnippet({ kind: "tol", view: "front", index: "overall-w", spec: "H7" }, { views }), /overall width.*fit="H7"/);
  const text = drawingEditsPromptText({ drawingPath: "DXF/clevis.dxf", edits: [{ kind: "move", view: "front", dx: 10, dy: -5 }], views });
  assert.match(text, /^Please make these changes to the script that writes DXF\/clevis.dxf/);
  assert.match(text, /\n- Move the `front` view/);
  assert.equal(drawingEditsPromptText({ edits: [] }), "");
});

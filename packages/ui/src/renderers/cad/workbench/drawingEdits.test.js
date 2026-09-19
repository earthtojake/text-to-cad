import assert from "node:assert/strict";
import test from "node:test";

import {
  draftDimensionFromPicks,
  drawingEditParams,
  drawingEditSnippet,
  drawingEditsPromptText,
  nearestView,
  sheetSnapTargets,
  sheetToModel,
  smartDimensionFromSnaps,
  snapSheetPoint,
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

test("the pointer snaps to holes, corners and edges of a view's line work only", () => {
  const targets = sheetSnapTargets({
    lines: [
      { layer: "VISIBLE", view: "front", start: [80, 40], end: [140, 40] },
      { layer: "DIM", view: "front", dim: "0", start: [80, 30], end: [140, 30] },
      { layer: "SHEET", start: [0, 0], end: [200, 0] }
    ],
    circles: [{ layer: "VISIBLE", view: "front", center: [110, 50], radius: 3 }],
    arcs: [{ layer: "VISIBLE", view: "front", center: [90, 50], radius: 2, startAngleDeg: 0, sweepAngleDeg: 360 }]
  });
  assert.equal(targets.lines.length, 1);
  assert.equal(targets.circles.length, 2);
  assert.equal(snapSheetPoint(targets, [81, 40.5]).kind, "vertex");
  assert.deepEqual(snapSheetPoint(targets, [81, 40.5]).point, [80, 40]);
  assert.equal(snapSheetPoint(targets, [110, 41]).kind, "edge");
  assert.deepEqual(snapSheetPoint(targets, [110, 41]).point, [110, 40]);
  assert.equal(snapSheetPoint(targets, [112.5, 50]).kind, "circle");
  assert.equal(snapSheetPoint(targets, [110, 30.5]), null, "dimension lines are not targets");
  assert.equal(snapSheetPoint(targets, [110, 60]), null);
});

test("a smart pick means the obvious dimension", () => {
  const view = { name: "front", minX: 80, minY: 40, maxX: 140, maxY: 60 };
  const edge = { kind: "edge", view: "front", point: [110, 40], line: { start: [80, 40], end: [140, 40] } };
  const hole = { kind: "circle", view: "front", point: [110, 50], circle: { center: [110, 50], radius: 3 } };
  const cornerA = { kind: "vertex", view: "front", point: [80, 40] };
  const cornerB = { kind: "vertex", view: "front", point: [80, 60] };
  assert.deepEqual(smartDimensionFromSnaps(view, [edge]), { kind: "dim", view: "front", x1: 80, y1: 40, x2: 140, y2: 40, offset: -12, orientation: "h" });
  assert.deepEqual(smartDimensionFromSnaps(view, [hole]), { kind: "dia", view: "front", cx: 110, cy: 50, r: 3 });
  assert.equal(smartDimensionFromSnaps(view, [cornerA]), null, "a corner waits for a second pick");
  assert.equal(smartDimensionFromSnaps(view, [cornerA, cornerB]).orientation, "v");
  assert.deepEqual(drawingEditParams([{ kind: "dia", view: "front", cx: 110, cy: 50, r: 3 }]), { dia: "110,50,3" });
  const front = { name: "front", at: [110, 50], map: [110, 45, 0.5, 0, 0, 0, 0, 0.5] };
  assert.equal(drawingEditSnippet({ kind: "dia", view: "front", cx: 110, cy: 50, r: 3 }, { views: [front] }),
    "front.hole((0, 0, 10), 6, thru=True)  # model mm; say depth=... instead of thru if it is blind");
});

test("an existing dimension can be picked by its text, and removed", () => {
  const targets = sheetSnapTargets({ lines: [], circles: [] }, [{ kind: "dimension", view: "front", index: "1", value: "34", position: [110, 30] }]);
  const snap = snapSheetPoint(targets, [112, 31], 2);
  assert.equal(snap.kind, "dimension");
  assert.equal(snap.index, "1");
  assert.deepEqual(drawingEditParams([{ kind: "del", view: "front", index: "1" }]), { del: "front:1" });
  assert.equal(
    drawingEditSnippet({ kind: "del", view: "front", index: "1" }, { dimensions: [{ view: "front", index: "1", value: "34" }] }),
    "In the `front` view, remove its 2nd dim()/hole()/note() call (reads 34)."
  );
  assert.match(drawingEditSnippet({ kind: "del", view: "top", index: "overall-w" }, {}), /drop the overall width/);
});

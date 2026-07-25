import assert from "node:assert/strict";
import test from "node:test";
import {
  buildThreeViewMarkupDocument,
  markupFilenameStem,
  parseThreeViewMarkupDocument,
  viewStateFromThreeViewMarkupDocument
} from "./threeViewMarkup.js";

test("builds a stable three-view markup document", () => {
  const document = buildThreeViewMarkupDocument({
    sourceFile: "robot/Upper arm.step",
    modelKey: "upper-arm",
    viewState: {
      front: {
        note: "Cut here",
        strokes: [{
          id: "stroke-7",
          tool: "arrow",
          intent: "remove",
          color: "#ef4444",
          points: [{ x: 0.25, y: 0.75 }, { x: 1.4, y: -1 }]
        }]
      }
    }
  });

  assert.equal(document.schema, "cad-viewer-three-view-markup");
  assert.deepEqual(document.views.map((view) => view.id), [
    "front",
    "back",
    "top",
    "bottom",
    "right",
    "left"
  ]);
  assert.equal(document.views[0].note, "Cut here");
  assert.deepEqual(document.views[0].strokes[0].points, [
    { x: 0.25, y: 0.75 },
    { x: 1, y: 0 }
  ]);
});

test("parses markup and restores editable view state", () => {
  const source = buildThreeViewMarkupDocument({
    overallNote: "Rotate the servo end",
    viewState: {
      right: {
        note: "About Z",
        strokes: [{
          tool: "circle",
          intent: "hardware",
          points: [{ x: 0.4, y: 0.4 }, { x: 0.6, y: 0.4 }]
        }]
      }
    }
  });

  const parsed = parseThreeViewMarkupDocument(JSON.stringify(source));
  const state = viewStateFromThreeViewMarkupDocument(parsed);
  assert.equal(parsed.overallNote, "Rotate the servo end");
  assert.equal(state.right.note, "About Z");
  assert.equal(state.right.strokes[0].intent, "hardware");
});

test("builds compact submissions with only changed views", () => {
  const document = buildThreeViewMarkupDocument({
    includeEmptyViews: false,
    viewState: {
      left: {
        note: "Move this face 4 mm",
        strokes: []
      }
    }
  });

  assert.deepEqual(document.views.map((view) => view.id), ["left"]);
  const restored = viewStateFromThreeViewMarkupDocument(document);
  assert.equal(restored.left.note, "Move this face 4 mm");
  assert.equal(restored.front.note, "");
});

test("rejects unrelated JSON and creates safe file stems", () => {
  assert.throws(
    () => parseThreeViewMarkupDocument('{"schema":"other","version":1}'),
    /Unsupported markup schema/u
  );
  assert.equal(markupFilenameStem("parts/Upper arm (editable).step"), "Upper_arm_editable");
});

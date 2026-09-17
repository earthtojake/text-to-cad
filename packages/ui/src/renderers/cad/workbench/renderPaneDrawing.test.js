import assert from "node:assert/strict";
import test from "node:test";
import { dxfBendGuideSegments } from "@hardcore/core/lib/dxf/foldPreview.js";
import { viewerBendGuidesForRenderPane } from "./renderPaneDrawing.js";

test("Render omits flat DXF crease guides and Inspect retains their inputs", () => {
  const flat = new Float32Array([0, 0, 0, 20, 10, 2]);
  const authored = { bendAxisX: [10], drawingBendLines: [{ start: [10, 0], end: [10, 10] }] };
  const guideSegments = inputs => dxfBendGuideSegments(flat, {
    bendAxesX: inputs.bendAxisX || [], bendLines: inputs.drawingBendLines,
    bendAnglesRad: [], thicknessScale: 1
  });
  const inspect = viewerBendGuidesForRenderPane(authored);
  assert.equal(inspect.bendAxisX, authored.bendAxisX);
  assert.equal(inspect.drawingBendLines, authored.drawingBendLines);
  assert.equal(guideSegments(inspect).length, 6);
  assert.equal(guideSegments(viewerBendGuidesForRenderPane({ ...authored, renderMode: true })).length, 0);
});

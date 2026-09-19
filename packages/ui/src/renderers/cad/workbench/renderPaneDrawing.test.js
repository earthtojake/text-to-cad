import assert from "node:assert/strict";
import test from "node:test";
import { dxfBendGuideSegments } from "@hardcore/core/lib/dxf/foldPreview.js";
import { viewerBendGuidesForRenderPane } from "./renderPaneDrawing.js";

test("Render and Inspect retain the same flat DXF crease guides", () => {
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
  const render = viewerBendGuidesForRenderPane({ ...authored, renderMode: true });
  assert.equal(render.bendAxisX, authored.bendAxisX);
  assert.equal(render.drawingBendLines, authored.drawingBendLines);
  assert.equal(guideSegments(render).length, 6);
});

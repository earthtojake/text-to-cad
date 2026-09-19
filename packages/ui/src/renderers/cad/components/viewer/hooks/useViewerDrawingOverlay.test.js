import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DRAWING_TOOL } from "@hardcore/core/lib/viewer/drawingTools.js";
import {
  buildDrawingPoint, distanceToStrokeInPixels, drawingToolNeedsTwoPoints, strokeLengthInPixels
} from "@hardcore/core/lib/viewer/drawingGeometry.js";

// Run the actual hook's event handlers with effect dependency semantics, without
// mounting a CAD renderer. This exercises rerenders during a live pointer drag.
function drawingHookHarness() {
  let dependencies, cleanup, storedRef;
  const source = readFileSync(new URL("./useViewerDrawingOverlay.js", import.meta.url), "utf8");
  const hook = Function("useEffect", "useLayoutEffect", "useRef", "DRAWING_TOOL",
    `return (${source.slice(source.indexOf("export function")).replace("export ", "")});`
  )((effect, next) => {
    if (dependencies && next.every((value, index) => Object.is(value, dependencies[index]))) return;
    cleanup?.();
    dependencies = next;
    cleanup = effect();
  }, effect => effect(), value => storedRef ??= { current: value }, DRAWING_TOOL);
  return { render: hook, unmount: () => cleanup?.() };
}

test("drawing gestures survive viewer callback refreshes and cancel when drawing is disabled", () => {
  const canvas = Object.assign(new globalThis.EventTarget(), {
    width: 500, height: 500,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 500, height: 500 })
  });
  const commits = [];
  const options = {
    drawingCanvasRef: { current: canvas }, drawingDraftRef: { current: null },
    drawingStrokesRef: { current: [] }, drawingIdRef: { current: 0 },
    drawingChangeRef: { current: strokes => commits.push(strokes) },
    drawingEnabled: true, previewMode: false, meshData: {}, viewerReadyTick: 1,
    redrawDrawingCanvas: () => {}, buildDrawingPoint, distanceToStrokeInPixels,
    drawingToolNeedsTwoPoints, strokeLengthInPixels,
    drawingEraseThresholdPx: 12, drawingMinPointDistancePx: 2, drawingMinStrokeLengthPx: 3
  };
  const harness = drawingHookHarness();
  const render = () => harness.render({
    ...options, renderDrawingOverlay: () => {},
    buildSurfaceLineAnchor: () => null, updateSurfaceLineAnchor: () => null
  });
  const pointer = (type, x, y) => canvas.dispatchEvent(Object.assign(
    new Event(type, { cancelable: true }), { button: 0, pointerId: 1, clientX: x, clientY: y }
  ));
  try {
    for (const tool of ["freehand", "line", "arrow", "double-arrow", "rectangle", "circle"]) {
      options.drawingTool = tool;
      render();
      pointer("pointerdown", 10, 20);
      pointer("pointermove", 40, 50);
      render(); // The regression discarded the active draft here.
      pointer("pointermove", 100, 120);
      pointer("pointerup", 100, 120);
      assert.equal(commits.at(-1)?.at(-1)?.tool, tool);
      assert.deepEqual(commits.at(-1).at(-1).points.at(-1), { x: 0.2, y: 0.24 });
    }
    assert.equal(commits.length, 6);
    pointer("pointerdown", 10, 20);
    options.drawingEnabled = false;
    render();
    pointer("pointermove", 100, 120);
    pointer("pointerup", 100, 120);
    assert.equal(commits.length, 6, "disabling drawing discards the unfinished stroke");
    assert.equal(options.drawingDraftRef.current, null);
  } finally {
    harness.unmount();
  }
});

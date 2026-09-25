import { useEffect } from "react";
import { DRAWING_TOOL } from "../../../workbench/constants";

export function useViewerDrawingOverlay({
  drawingCanvasRef,
  drawingDraftRef,
  drawingStrokesRef,
  drawingChangeRef,
  drawingIdRef,
  drawingEnabled,
  drawingTool,
  meshData,
  previewMode,
  viewerReadyTick,
  renderDrawingOverlay,
  redrawDrawingCanvas,
  buildDrawingPoint,
  distanceToStrokeInPixels,
  strokeLengthInPixels,
  drawingToolNeedsTwoPoints,
  buildFillStrokeAtPoint,
  buildSurfaceLineAnchor,
  updateSurfaceLineAnchor,
  drawingEraseThresholdPx,
  drawingMinPointDistancePx,
  drawingMinStrokeLengthPx
}) {
  useEffect(() => {
    const canvas = drawingCanvasRef.current;
    if (!canvas) {
      return undefined;
    }

    if (!drawingEnabled || previewMode || !meshData) {
      drawingDraftRef.current = null;
      renderDrawingOverlay();
      return undefined;
    }

    const interaction = {
      pointerId: null,
      erasing: false
    };

    const commitStrokes = (nextStrokes) => {
      drawingStrokesRef.current = nextStrokes;
      drawingChangeRef.current?.(nextStrokes);
      redrawDrawingCanvas(canvas, nextStrokes, drawingDraftRef.current);
    };

    const commitSingleStroke = (stroke) => {
      if (!stroke) {
        redrawDrawingCanvas(canvas, drawingStrokesRef.current, drawingDraftRef.current);
        return;
      }
      drawingIdRef.current += 1;
      commitStrokes([
        ...drawingStrokesRef.current,
        {
          id: `stroke-${drawingIdRef.current}`,
          ...stroke
        }
      ]);
    };

    const eraseStrokeAt = (point) => {
      const width = canvas.width || 1;
      const height = canvas.height || 1;
      let bestIndex = -1;
      let bestDistance = Infinity;
      for (let index = 0; index < drawingStrokesRef.current.length; index += 1) {
        const distance = distanceToStrokeInPixels(point, drawingStrokesRef.current[index], width, height);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestIndex = index;
        }
      }
      if (bestIndex === -1 || bestDistance > drawingEraseThresholdPx) {
        return;
      }
      const nextStrokes = drawingStrokesRef.current.filter((_, index) => index !== bestIndex);
      commitStrokes(nextStrokes);
    };

    const beginDraft = (point) => {
      drawingDraftRef.current = {
        id: "__draft__",
        tool: drawingTool,
        points: [point]
      };
      redrawDrawingCanvas(canvas, drawingStrokesRef.current, drawingDraftRef.current);
    };

    const updateDraft = (point) => {
      const draft = drawingDraftRef.current;
      if (!draft) {
        return;
      }
      if (drawingTool === DRAWING_TOOL.FREEHAND) {
        const lastPoint = draft.points[draft.points.length - 1];
        const dx = (point.x - lastPoint.x) * (canvas.width || 1);
        const dy = (point.y - lastPoint.y) * (canvas.height || 1);
        if (Math.hypot(dx, dy) >= drawingMinPointDistancePx) {
          draft.points = [...draft.points, point];
        }
      } else {
        draft.points = [draft.points[0], point];
      }
      redrawDrawingCanvas(canvas, drawingStrokesRef.current, draft);
    };

    const endDraft = () => {
      const draft = drawingDraftRef.current;
      if (!draft) {
        return;
      }
      drawingDraftRef.current = null;
      const strokeLength = strokeLengthInPixels(draft, canvas.width || 1, canvas.height || 1);
      if (drawingToolNeedsTwoPoints(draft.tool) && (draft.points.length < 2 || strokeLength < drawingMinStrokeLengthPx)) {
        redrawDrawingCanvas(canvas, drawingStrokesRef.current, null);
        return;
      }
      if (strokeLength < drawingMinStrokeLengthPx && draft.points.length > 1) {
        redrawDrawingCanvas(canvas, drawingStrokesRef.current, null);
        return;
      }
      commitSingleStroke({
        tool: draft.tool,
        points: draft.points.map((point) => ({ x: point.x, y: point.y })),
        surfaceLine: draft.surfaceLine || null
      });
    };

    const handlePointerDown = (event) => {
      if (event.button !== 0) {
        return;
      }
      interaction.erasing = drawingTool === DRAWING_TOOL.ERASE;
      const point = buildDrawingPoint(event, canvas);
      if (interaction.erasing) {
        event.preventDefault();
        event.stopPropagation();
        interaction.pointerId = event.pointerId;
        canvas.setPointerCapture?.(event.pointerId);
        eraseStrokeAt(point);
        return;
      }
      if (drawingTool === DRAWING_TOOL.FILL) {
        event.preventDefault();
        event.stopPropagation();
        commitSingleStroke(buildFillStrokeAtPoint(point, drawingStrokesRef.current, canvas));
        return;
      }
      if (drawingTool === DRAWING_TOOL.SURFACE_LINE) {
        const anchor = buildSurfaceLineAnchor?.(event, canvas);
        if (!anchor) {
          redrawDrawingCanvas(canvas, drawingStrokesRef.current, null);
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        interaction.pointerId = event.pointerId;
        canvas.setPointerCapture?.(event.pointerId);
        drawingDraftRef.current = {
          id: "__draft__",
          tool: drawingTool,
          points: [anchor.screenPoint, anchor.screenPoint],
          surfaceLine: anchor.surfaceLine
        };
        redrawDrawingCanvas(canvas, drawingStrokesRef.current, drawingDraftRef.current);
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      interaction.pointerId = event.pointerId;
      canvas.setPointerCapture?.(event.pointerId);
      beginDraft(point);
    };

    const handlePointerMove = (event) => {
      if (interaction.pointerId !== event.pointerId) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const point = buildDrawingPoint(event, canvas);
      if (interaction.erasing) {
        eraseStrokeAt(point);
        return;
      }
      if (drawingTool === DRAWING_TOOL.SURFACE_LINE) {
        const draft = drawingDraftRef.current;
        if (!draft?.surfaceLine?.referenceId) {
          return;
        }
        const nextAnchor = updateSurfaceLineAnchor?.(event, canvas, draft.surfaceLine);
        if (!nextAnchor) {
          return;
        }
        draft.points = [draft.points[0], nextAnchor.screenPoint];
        draft.surfaceLine = nextAnchor.surfaceLine;
        redrawDrawingCanvas(canvas, drawingStrokesRef.current, draft);
        return;
      }
      updateDraft(point);
    };

    const handlePointerEnd = (event) => {
      if (interaction.pointerId !== event.pointerId) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      canvas.releasePointerCapture?.(event.pointerId);
      interaction.pointerId = null;
      if (interaction.erasing) {
        interaction.erasing = false;
        redrawDrawingCanvas(canvas, drawingStrokesRef.current, null);
        return;
      }
      endDraft();
    };

    canvas.addEventListener("pointerdown", handlePointerDown);
    canvas.addEventListener("pointermove", handlePointerMove);
    canvas.addEventListener("pointerup", handlePointerEnd);
    canvas.addEventListener("pointercancel", handlePointerEnd);

    return () => {
      interaction.pointerId = null;
      interaction.erasing = false;
      drawingDraftRef.current = null;
      redrawDrawingCanvas(canvas, drawingStrokesRef.current, null);
      canvas.removeEventListener("pointerdown", handlePointerDown);
      canvas.removeEventListener("pointermove", handlePointerMove);
      canvas.removeEventListener("pointerup", handlePointerEnd);
      canvas.removeEventListener("pointercancel", handlePointerEnd);
    };
  }, [
    buildDrawingPoint,
    buildFillStrokeAtPoint,
    buildSurfaceLineAnchor,
    distanceToStrokeInPixels,
    drawingCanvasRef,
    drawingChangeRef,
    drawingDraftRef,
    drawingEnabled,
    drawingEraseThresholdPx,
    drawingIdRef,
    drawingMinPointDistancePx,
    drawingMinStrokeLengthPx,
    drawingStrokesRef,
    drawingTool,
    drawingToolNeedsTwoPoints,
    meshData,
    previewMode,
    redrawDrawingCanvas,
    renderDrawingOverlay,
    strokeLengthInPixels,
    updateSurfaceLineAnchor,
    viewerReadyTick
  ]);
}

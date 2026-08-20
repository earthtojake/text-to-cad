import { useEffect, useRef } from "react";

import {
  MEASURE_DIMENSION_DRAFT_COLOR,
  MEASURE_DIMENSION_FADED_ALPHA,
  drawMeasureDimension,
  drawMeasureSnapChip,
  drawMeasureSnapMarker,
  drawPulsingEndRing,
  measureLabelText,
  measureSeriesColor,
  screenSpaceDimensionLayout
} from "cadjs/lib/viewer/measureDimension.js";
import {
  MEASURE_SNAP_LABELS,
  entityMeasurementFromPick,
  formatEntityMeasurement
} from "cadjs/lib/viewer/measurement.js";
import { projectWorldPointToClient } from "cadjs/lib/viewer/measureRuler.js";

import { measureRulerDraftMeasurement } from "../../../workbench/measureRulerState.js";

export function useViewerMeasureOverlay({
  measureCanvasRef,
  measureState,
  activeMeasurementId = "",
  measureHoverRef = null,
  measureModeActive = false,
  runtimeRef,
  mountRef,
  previewMode,
  viewerReadyTick
}) {
  const measureStateRef = useRef(measureState);
  measureStateRef.current = measureState;
  const activeIdRef = useRef(activeMeasurementId);
  activeIdRef.current = activeMeasurementId;

  // Nothing to draw means no loop at all. An unconditional rAF would clear an
  // empty canvas every frame, for the whole session, on every model, whether or
  // not the tool had ever been opened. While the tool is armed the loop does run
  // continuously, because the snap indicator has to track the cursor.
  const hasOverlayContent = Boolean(
    !previewMode &&
    (measureModeActive ||
      measureState?.measurements?.length ||
      measureState?.draft?.anchor)
  );

  useEffect(() => {
    const canvas = measureCanvasRef.current;
    if (!canvas) {
      return undefined;
    }
    if (!hasOverlayContent) {
      const idleContext = canvas.getContext("2d");
      if (idleContext) {
        idleContext.setTransform(1, 0, 0, 1, 0, 0);
        idleContext.clearRect(0, 0, canvas.width, canvas.height);
      }
      return undefined;
    }

    let rafId = 0;

    const render = (now) => {
      const context = canvas.getContext("2d");
      if (!context) {
        rafId = window.requestAnimationFrame(render);
        return;
      }
      const runtime = runtimeRef.current;
      const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
      const cssWidth = canvas.clientWidth || mountRef.current?.clientWidth || 1;
      const cssHeight = canvas.clientHeight || mountRef.current?.clientHeight || 1;
      const width = Math.round(cssWidth * dpr);
      const height = Math.round(cssHeight * dpr);
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, cssWidth, cssHeight);

      const state = measureStateRef.current;
      const camera = runtime?.camera || null;
      if (state && camera && !previewMode) {
        const localRect = { left: 0, top: 0, width: cssWidth, height: cssHeight };
        const bounds = { width: cssWidth, height: cssHeight };
        const activeId = activeIdRef.current;

        for (const item of state.measurements || []) {
          const layout = screenSpaceDimensionLayout(item?.pickA, item?.pickB, item?.measurement, camera, localRect);
          if (!layout) {
            continue;
          }
          const active = item.id === activeId;
          drawMeasureDimension(context, layout, {
            color: measureSeriesColor(item?.colorIndex),
            alpha: active ? 1 : MEASURE_DIMENSION_FADED_ALPHA,
            lineWidth: active ? 2.6 : 1.4,
            witnessWidth: active ? 1.6 : 1,
            ringRadius: active ? 4 : 3,
            label: active ? measureLabelText(item.measurement) : "",
            bounds
          });
        }

        const draft = state.draft;
        const lockedAnchor = draft?.anchor;
        if (lockedAnchor?.point) {
          const start = projectWorldPointToClient(lockedAnchor.point, camera, localRect);
          if (start) {
            drawPulsingEndRing(context, start, {
              now,
              color: MEASURE_DIMENSION_DRAFT_COLOR,
              baseRadius: 6
            });
            drawMeasureSnapMarker(context, start, {
              snapKind: lockedAnchor.snapKind || "vertex",
              now
            });
          }
        }
        if (draft?.anchor && draft?.hover) {
          const draftMeasurement = measureRulerDraftMeasurement(state);
          const layout = screenSpaceDimensionLayout(draft.anchor, draft.hover, draftMeasurement, camera, localRect);
          if (layout) {
            drawMeasureDimension(context, layout, {
              color: MEASURE_DIMENSION_DRAFT_COLOR,
              alpha: 0.95,
              lineWidth: 2.2,
              ringRadius: 4,
              label: measureLabelText(draftMeasurement),
              bounds
            });
            const end = projectWorldPointToClient(draft.hover.point, camera, localRect);
            if (end) {
              drawPulsingEndRing(context, end, { now, color: MEASURE_DIMENSION_DRAFT_COLOR });
            }
          }
        }

        // The snap indicator is driven from a ref rather than from React state:
        // it has to follow the cursor every frame, and re-rendering the whole
        // workspace on each mouse move to move a 7px marker is not worth it.
        const hover = measureModeActive ? measureHoverRef?.current : null;
        if (hover?.point) {
          const hoverPoint = projectWorldPointToClient(hover.point, camera, localRect);
          if (hoverPoint) {
            drawMeasureSnapMarker(context, hoverPoint, { snapKind: hover.snapKind, now });
            const entityText = formatEntityMeasurement(entityMeasurementFromPick(hover));
            const snapLabel = MEASURE_SNAP_LABELS[hover.snapKind] || "";
            const chipText = [snapLabel, entityText].filter(Boolean).join("  ");
            if (chipText) {
              drawMeasureSnapChip(context, hoverPoint, chipText, { bounds });
            }
          }
        }
      }

      rafId = window.requestAnimationFrame(render);
    };

    rafId = window.requestAnimationFrame(render);

    return () => {
      window.cancelAnimationFrame(rafId);
    };
  }, [measureCanvasRef, measureHoverRef, measureModeActive, runtimeRef, mountRef, previewMode, viewerReadyTick, hasOverlayContent]);
}

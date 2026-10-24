import { useEffect, useRef } from "react";

import {
  MEASURE_DIMENSION_DRAFT_COLOR,
  drawMeasureDimension,
  drawMeasureSnapChip,
  drawMeasureSnapMarker,
  drawMeasurementMark,
  drawPulsingEndRing,
  measureLabelText,
  measurementMark,
  measurementMarkLayout,
  screenSpaceDimensionLayout
} from "@text-to-cad/core/lib/viewer/measureDimension.js";
import {
  MEASURE_SNAP_LABELS,
  entityMeasurementFromPick,
  formatEntityMeasurement
} from "@text-to-cad/core/lib/viewer/measurement.js";
import { projectWorldPointToClient } from "@text-to-cad/core/lib/viewer/measureRuler.js";

import { measureRulerDraftMeasurement } from "./measureRulerState.js";

/** What a pick is, in words, beside the pointer: its kind and what it is worth on its own ("Edge ⌀ 6.60 mm L 20.73 mm"). */
function entityChipText(pick, faceArea = null) {
  return [MEASURE_SNAP_LABELS[pick?.snapKind] || "", formatEntityMeasurement(entityMeasurementFromPick(pick, { faceArea }))].filter(Boolean).join("  ");
}

// What Select has picked, as the annotations and the parts are: the one selection blue.
const MEASURE_SELECTED_COLOR = "#2979ff";

/**
 * Measure's drawing over the viewport, on its own 2D canvas (`measureCanvasRef`): every measurement
 * taken, as a mark (`drawMeasurementMark`), the one in hand labelled; the draft's rubber
 * band to the live hover (`measureHoverRef`); and, while the tool is in hand, the snap marker and
 * what it snapped to. It draws right after each render of the scene, so a dimension moves in the
 * frame the model does, and runs no loop at all while there is nothing to draw. Format-blind: a
 * pick is `{ point, snapKind }` in the scene's coordinates.
 */
export function useMeasureOverlay({
  measureCanvasRef,
  measureState,
  activeMeasurementId = "",
  selectedMeasurementIds = [],
  hoveredMeasurementId = "",
  measureHoverRef = null,
  measureModeActive = false,
  runtimeRef,
  mountRef,
  preview,
  viewerReadyTick,
  faceAreas = null
}) {
  const measureStateRef = useRef(measureState);
  measureStateRef.current = measureState;
  const activeIdRef = useRef(activeMeasurementId);
  activeIdRef.current = activeMeasurementId;
  const selectedIdsRef = useRef(selectedMeasurementIds);
  selectedIdsRef.current = selectedMeasurementIds;
  const hoveredIdRef = useRef(hoveredMeasurementId);
  hoveredIdRef.current = hoveredMeasurementId;
  const draftMemo = useRef({ anchor: null, end: null, measurement: null });

  // Nothing to draw means no loop at all. An unconditional rAF would clear an
  // empty canvas every frame, for the whole session, on every model, whether or
  // not the tool had ever been opened. While the tool is armed the loop does run
  // continuously, because the snap indicator has to track the cursor.
  const hasOverlayContent = Boolean(
    !preview &&
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
      // Cleared once, after the last drawing: a canvas never drawn on has nothing to clear.
      if (canvas.dataset.measureDrawn !== undefined) {
        const idleContext = canvas.getContext("2d");
        idleContext?.setTransform(1, 0, 0, 1, 0, 0);
        idleContext?.clearRect(0, 0, canvas.width, canvas.height);
        delete canvas.dataset.measureDrawn;
      }
      return undefined;
    }
    canvas.dataset.measureDrawn = "";

    let rafId = 0;

    // One drawing of the overlay as the camera stands now. It runs right after every render of the
    // scene (`scene.onAfterRender`), so a dimension moves in the same frame the model does, as the
    // annotations (in the scene) do; and on its own frames, for the snap marker's pulse while
    // nothing re-renders the scene.
    const draw = (now) => {
      const context = canvas.getContext("2d");
      if (!context) {
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
      if (state && camera && !preview) {
        const localRect = { left: 0, top: 0, width: cssWidth, height: cssHeight };
        const bounds = { width: cssWidth, height: cssHeight };
        const activeId = activeIdRef.current;

        // Each as a mark (`drawMeasurementMark`): the one in hand, or the one the pointer rests on, labelled.
        for (const item of state.measurements || []) {
          const mark = measurementMark(item);
          const layout = measurementMarkLayout(mark, camera, localRect);
          if (!layout) {
            continue;
          }
          const active = item.id === activeId || item.id === hoveredIdRef.current;
          // Picked by Select: a halo in the selection's blue behind the dimension; under the pointer,
          // a fainter one, as a part is lit before it is picked.
          const picked = selectedIdsRef.current.includes(item.id);
          if (picked || hoveredIdRef.current === item.id) {
            drawMeasureDimension(context, layout, { color: MEASURE_SELECTED_COLOR, alpha: picked ? 0.5 : 0.25, lineWidth: 8, witnessWidth: 5,
              tickWidth: 6, ringRadius: 6, ringStrokeWidth: 4, bounds });
          }
          drawMeasurementMark(context, layout, mark, { active, bounds });
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
            // What the first press took reads out beside it for as long as it is held: one entity is a
            // result of its own (a hole's diameter, a face's area, a vertex's position), before a second joins it.
            const heldText = formatEntityMeasurement(entityMeasurementFromPick(lockedAnchor)) ? entityChipText(lockedAnchor) : "";
            if (heldText) {
              drawMeasureSnapChip(context, start, heldText, { bounds, color: MEASURE_DIMENSION_DRAFT_COLOR });
            }
          }
        }
        // The rubber band ends at the LIVE hover (the ref the snap marker reads): the draft's own
        // hover says only whether there is an end and what it snaps to, and changes only then.
        const liveHover = measureHoverRef?.current;
        const draftEnd = draft?.anchor && draft?.hover
          ? (liveHover?.point && liveHover !== draft.anchor ? liveHover : draft.hover) : null;
        if (draftEnd) {
          // The pair's reading is asked once per pointer move, not once per frame.
          const memo = draftMemo.current;
          const draftMeasurement = memo.anchor === draft.anchor && memo.end === draftEnd ? memo.measurement
            : measureRulerDraftMeasurement({ draft: { anchor: draft.anchor, hover: draftEnd } });
          draftMemo.current = { anchor: draft.anchor, end: draftEnd, measurement: draftMeasurement };
          const layout = screenSpaceDimensionLayout(draft.anchor, draftEnd, draftMeasurement, camera, localRect);
          if (layout) {
            drawMeasureDimension(context, layout, {
              color: MEASURE_DIMENSION_DRAFT_COLOR,
              alpha: 0.95,
              lineWidth: 2.2,
              ringRadius: 4,
              label: measureLabelText(draftMeasurement),
              bounds
            });
            const end = projectWorldPointToClient(draftEnd.point, camera, localRect);
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
            const faceArea = hover.snapKind === "face" ? faceAreas?.read(hover.reference) : null;
            const chipText = entityChipText(hover, faceArea);
            if (chipText) {
              drawMeasureSnapChip(context, hoverPoint, chipText, { bounds });
            }
          }
        }
      }

    };
    const tick = (now) => {
      install();
      draw(now);
      rafId = window.requestAnimationFrame(tick);
    };
    // The scene's after-render hook, kept wrapped: another owner of it (the photographic studio) puts
    // back what it found when it leaves, so each frame checks it is still this one's.
    let hooked = null, previous = null;
    const afterRender = function measureAfterRender(...args) {
      previous?.apply(this, args);
      const [renderer, , camera] = args;
      const runtime = runtimeRef.current;
      if (camera === runtime?.camera && !renderer?.getRenderTarget?.()) draw(performance.now());
    };
    const install = () => {
      const scene = runtimeRef.current?.scene;
      if (!scene || scene.onAfterRender === afterRender) return;
      if (hooked && hooked !== scene && hooked.onAfterRender === afterRender) hooked.onAfterRender = previous;
      previous = scene.onAfterRender === afterRender ? previous : scene.onAfterRender;
      scene.onAfterRender = afterRender;
      hooked = scene;
    };

    rafId = window.requestAnimationFrame(tick);

    return () => {
      window.cancelAnimationFrame(rafId);
      if (hooked?.onAfterRender === afterRender) hooked.onAfterRender = previous;
    };
  }, [measureCanvasRef, measureHoverRef, measureModeActive, runtimeRef, mountRef, preview, viewerReadyTick, hasOverlayContent, faceAreas]);
}

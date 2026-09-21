import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  STEP_TREE_ROW_HEIGHT,
  STEP_TREE_ROW_STRIDE,
  stepTreeRowScrollTop,
  stepTreeWindowIndexes,
  stepTreeWindowRange,
} from "../../../workbench/stepTreeWindow";

export default function useStepTreeWindow(rows, focusedRowId, contextRowId) {
  // A callback ref observes tab moves, split-pane remounts and sheet reopening;
  // the scroll viewport itself belongs to FileSheetTabbedSurface.
  const [container, setContainer] = useState(null);
  const measureRef = useRef(null);
  const [range, setRange] = useState(() => stepTreeWindowRange(rows.length));
  const indexById = useMemo(() => new Map(rows.map((row, index) => [row.id, index])), [rows]);

  useLayoutEffect(() => {
    const viewport = container?.closest("[data-slot='scroll-area-viewport']");
    if (!viewport) return;
    const measure = () => {
      const metrics = {
        scrollTop: viewport.scrollTop,
        viewportHeight: viewport.clientHeight,
        listTop: container.getBoundingClientRect().top - viewport.getBoundingClientRect().top
          - viewport.clientTop + viewport.scrollTop,
      };
      const next = stepTreeWindowRange(rows.length, metrics);
      setRange((current) => current.start === next.start && current.end === next.end ? current : next);
      return metrics;
    };
    measureRef.current = { viewport, measure };
    measure();
    viewport.addEventListener("scroll", measure, { passive: true });
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    observer.observe(container);
    return () => {
      measureRef.current = null;
      observer.disconnect();
      viewport.removeEventListener("scroll", measure);
    };
  }, [container, rows.length]);

  const scrollToIndex = useCallback((index, options) => {
    const measurement = measureRef.current;
    if (!measurement || index < 0) return false;
    const { viewport, measure } = measurement;
    viewport.scrollTop = stepTreeRowScrollTop(index, measure(), options);
    // Programmatic scroll events are asynchronous. Mount the destination now,
    // so keyboard focus can be applied in the next layout effect.
    measure();
    return true;
  }, []);

  const indexes = stepTreeWindowIndexes(range, rows.length, [
    indexById.get(focusedRowId), indexById.get(contextRowId),
  ]);
  return {
    containerRef: setContainer,
    ready: Boolean(container),
    indexes,
    indexById,
    scrollToIndex,
    height: Math.max(0, (rows.length - 1) * STEP_TREE_ROW_STRIDE + STEP_TREE_ROW_HEIGHT),
  };
}

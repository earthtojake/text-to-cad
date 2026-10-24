import { useEffect, useMemo, useState } from "react";

function nowMs() {
  return typeof performance === "undefined" ? Date.now() : performance.now();
}

/**
 * Records the two readiness moments of the displayed model: its first geometry and the whole
 * model. The small browser snapshot (`window.__cadViewerLoad`) is intentional public
 * observability for benchmark harnesses; UI copy remains human-facing.
 */
export function useViewportLoadStatus({ modelKey = "", hasGeometry = false, modelComplete = false } = {}) {
  const [timeline, setTimeline] = useState(() => ({ modelKey, firstGeometryAt: null, completeAt: null }));
  const complete = hasGeometry && modelComplete;

  useEffect(() => {
    setTimeline({ modelKey, firstGeometryAt: null, completeAt: null });
  }, [modelKey]);

  useEffect(() => {
    if (!hasGeometry) return;
    setTimeline((current) => {
      if (current.modelKey !== modelKey) return current;
      const timestamp = nowMs();
      const firstGeometryAt = current.firstGeometryAt ?? timestamp;
      const completeAt = current.completeAt ?? (complete ? timestamp : null);
      return firstGeometryAt === current.firstGeometryAt && completeAt === current.completeAt
        ? current
        : { ...current, firstGeometryAt, completeAt };
    });
  }, [modelKey, hasGeometry, complete]);

  const observation = useMemo(() => ({
    modelKey,
    firstGeometry: hasGeometry,
    complete,
    firstGeometryAt: timeline.modelKey === modelKey ? timeline.firstGeometryAt : null,
    completeAt: timeline.modelKey === modelKey ? timeline.completeAt : null
  }), [complete, hasGeometry, modelKey, timeline]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.__cadViewerLoad = observation;
  }, [observation]);

  return observation;
}

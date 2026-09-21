import { useEffect, useMemo, useRef, useState } from "react";
import { lodSnapshotForFile, lodSnapshotForModel, viewportQualityStatus } from "@/workbench/viewportQualityStatus.js";

function readLodSnapshot() {
  if (typeof window === "undefined" || typeof window.__cadViewportLod !== "function") {
    return null;
  }
  try {
    return window.__cadViewportLod();
  } catch {
    return null;
  }
}

function nowMs() {
  return typeof performance === "undefined" ? Date.now() : performance.now();
}

/**
 * Records the two meaningful readiness moments for the active displayed model:
 * first geometry and standard detail. The small browser snapshot is intentional
 * public observability for benchmark harnesses; UI copy remains human-facing.
 */
export function useViewportQualityStatus({
  modelKey = "",
  file = "",
  hasGeometry = false,
  modelComplete = false,
  lodExpectedComponentCount = 0,
  quality = "interactive"
} = {}) {
  const [lodRecord, setLodRecord] = useState(() => ({ modelKey, snapshot: readLodSnapshot() }));
  const [memoryRecord, setMemoryRecord] = useState(() => ({ modelKey, limitation: null }));
  const modelKeyRef = useRef(modelKey);
  const fileRef = useRef(file);
  modelKeyRef.current = modelKey;
  fileRef.current = file;
  const [timeline, setTimeline] = useState(() => ({
    modelKey,
    firstPreviewAt: null,
    standardQualityAt: null
  }));

  useEffect(() => {
    // A prior file's scheduler may still be mounted for this render. Wait for
    // its status event instead of treating its snapshot as the new model.
    setLodRecord({ modelKey, snapshot: null });
    setMemoryRecord({ modelKey, limitation: null });
    setTimeline({ modelKey, firstPreviewAt: null, standardQualityAt: null });
  }, [modelKey]);

  useEffect(() => {
    const acceptSnapshot = (snapshot) => {
      const current = lodSnapshotForFile(snapshot, fileRef.current);
      if (current?.modelKey === modelKeyRef.current) {
        setLodRecord({ modelKey: modelKeyRef.current, snapshot: current });
      }
    };
    const onLodStatus = (event) => acceptSnapshot(event.detail || readLodSnapshot());
    const onLodLevel = () => acceptSnapshot(readLodSnapshot());
    const onMemoryLimitation = (event) => {
      const snapshot = lodSnapshotForFile(readLodSnapshot(), fileRef.current);
      if (snapshot?.modelKey === modelKeyRef.current) {
        setMemoryRecord({ modelKey: modelKeyRef.current, limitation: event.detail || null });
      }
    };
    window.addEventListener("cad:lod-status", onLodStatus);
    window.addEventListener("cad:lod-level", onLodLevel);
    window.addEventListener("cad:memory-limitation", onMemoryLimitation);
    return () => {
      window.removeEventListener("cad:lod-status", onLodStatus);
      window.removeEventListener("cad:lod-level", onLodLevel);
      window.removeEventListener("cad:memory-limitation", onMemoryLimitation);
    };
  }, []);

  const currentLodSnapshot = lodSnapshotForFile(lodSnapshotForModel(lodRecord, modelKey), file);
  const memoryLimitation = memoryRecord.modelKey === modelKey ? memoryRecord.limitation : null;
  const status = useMemo(() => viewportQualityStatus({
    hasGeometry,
    modelComplete,
    lodExpectedComponentCount,
    lodSnapshot: currentLodSnapshot,
    memoryLimitation,
    quality
  }), [currentLodSnapshot, hasGeometry, lodExpectedComponentCount, memoryLimitation, modelComplete, quality]);

  useEffect(() => {
    if (!status.firstPreviewReady && !status.standardQualityReady) {
      return;
    }
    setTimeline((current) => {
      if (current.modelKey !== modelKey) {
        return current;
      }
      const timestamp = nowMs();
      const firstPreviewAt = current.firstPreviewAt ?? (status.firstPreviewReady ? timestamp : null);
      const standardQualityAt = current.standardQualityAt ?? (status.standardQualityReady ? timestamp : null);
      return firstPreviewAt === current.firstPreviewAt && standardQualityAt === current.standardQualityAt
        ? current
        : { ...current, firstPreviewAt, standardQualityAt };
    });
  }, [modelKey, status.firstPreviewReady, status.standardQualityReady]);

  const observation = useMemo(() => ({
    ...status,
    modelKey,
    firstPreviewAt: timeline.modelKey === modelKey ? timeline.firstPreviewAt : null,
    standardQualityAt: timeline.modelKey === modelKey ? timeline.standardQualityAt : null
  }), [modelKey, status, timeline]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.__cadViewerQuality = observation;
    window.dispatchEvent(new CustomEvent("cad:quality-status", { detail: observation }));
  }, [observation]);

  return observation;
}

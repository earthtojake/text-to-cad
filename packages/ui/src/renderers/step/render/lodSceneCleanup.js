import { renderMemoryAccounting } from "./renderMemoryAccounting.js";

// Full scene teardown is the recovery boundary after an interrupted in-place
// reconciliation. Never certify disposal from a React unmount/abort alone.
export function disposeViewerCadScene(runtime, { clearSceneGroup, preserveModelIdentity = false, releaseGpu = true } = {}) {
  if (!runtime) return null;
  const source = runtime.cadScene?.source || runtime.retiringCadSource || null;
  runtime.retiringCadSource = source;
  try {
    runtime.cadScene?.dispose?.({ releaseGpu });
    runtime.cadScene = null;
    for (const key of ["stageGroup", "modelGroup", "edgesGroup", "facePickGroup", "edgePickGroup", "vertexPickGroup"]) {
      if (runtime[key]) clearSceneGroup?.(runtime[key]);
    }
    runtime.facePickMesh = null;
    runtime.edgePickLines = null;
    runtime.vertexPickPoints = null;
    runtime.edgePickObjects = [];
    runtime.topologyDisplayEdgeLine = null;
    runtime.topologyDisplayEdgeTransformByRecord = false;
    runtime.displayRecords = [];
    if (!preserveModelIdentity) {
      runtime.hasVisibleModel = false;
      runtime.activeModelKey = "";
    }
    runtime.sceneCleanupFailed = false;
    renderMemoryAccounting(runtime);
    runtime.retiringCadSource = null;
    return source;
  } catch (error) {
    runtime.sceneCleanupFailed = true;
    // Partial reconciliation's installed array may omit newly attached
    // objects. Keep their actual buffers in the ledger while work is stopped.
    try { renderMemoryAccounting(runtime); } catch { /* preserve the cleanup failure */ }
    throw error;
  }
}

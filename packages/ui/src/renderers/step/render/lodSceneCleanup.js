import { renderMemoryAccounting } from "./renderMemoryAccounting.js";

// The runtime groups that hold nothing but what the STEP renderer put there: its linework
// (the build's edges, the topology line, the highlight overlays) and its pick proxies. The
// model group and the stage are the viewport's: it adopted the scene's root into the first
// and builds the floor in the second, so clearing either here would take the viewport's own
// objects with it.
export const STEP_RUNTIME_GROUPS = Object.freeze(["edgesGroup", "facePickGroup", "edgePickGroup", "vertexPickGroup"]);

// Full scene teardown is the recovery boundary after an interrupted in-place
// reconciliation. Never certify disposal from a React unmount/abort alone.
export function disposeViewerCadScene(runtime, {
  clearSceneGroup, preserveModelIdentity = false, releaseGpu = true, groups = STEP_RUNTIME_GROUPS
} = {}) {
  if (!runtime) return null;
  const source = runtime.cadScene?.source || runtime.retiringCadSource || null;
  runtime.retiringCadSource = source;
  try {
    runtime.cadScene?.dispose?.({ releaseGpu });
    runtime.cadScene = null;
    for (const key of groups) {
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

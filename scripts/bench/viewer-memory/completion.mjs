// Record publication transitions, including a clear between retries. Initial
// null state is omitted; once a publication exists, null is a meaningful
// event and makes a repeated payload after restart visible again.
export function recordMeshCostRampSample(state, meshCost, atMs) {
  const target = state || { entries: [], lastKey: "", seenPublication: false };
  if (!meshCost && !target.seenPublication) return target;
  const key = meshCost ? JSON.stringify(meshCost) : "null";
  if (key === target.lastKey) return target;
  target.lastKey = key;
  if (meshCost) target.seenPublication = true;
  target.entries.push({ atMs: Math.round(Number(atMs) || 0), cost: meshCost || null });
  return target;
}

// A visible model may be a progressive subset or the previous revision. Only
// a complete component publication which has reached the actual display
// records establishes a successful load.
export function isCompletePublication({ modelKey, meshCost, renderMemoryProbe, sceneSync } = {}) {
  const loaded = Number(meshCost?.loadedComponents);
  const total = Number(meshCost?.totalComponents);
  const represented = Number(meshCost?.componentCount);
  const occurrences = Number(meshCost?.occurrenceCount);
  const renderedOccurrences = Number(renderMemoryProbe?.occurrences);
  const sceneRecords = Number(sceneSync?.records);
  const publicationAt = Number(meshCost?.at);
  const sceneSyncAt = Number(sceneSync?.atMs);
  return Boolean(modelKey)
    && meshCost?.final === true
    && Number.isInteger(total) && total > 0
    && Number.isInteger(loaded) && loaded === total
    && Number.isInteger(represented) && represented === total
    && Number.isInteger(occurrences) && occurrences > 0
    && Number.isInteger(renderedOccurrences) && renderedOccurrences === occurrences
    && Number.isInteger(sceneRecords) && sceneRecords === occurrences
    && Number.isFinite(publicationAt)
    && Number.isFinite(sceneSyncAt) && sceneSyncAt >= Math.floor(publicationAt);
}

export function isRequestedDetailComplete(probe, minimumLevel = 0) {
  if (!isCompletePublication(probe)) return false;
  if (minimumLevel === 0) return true;
  const lod = probe?.viewportLod;
  return lod?.minimumLevel === minimumLevel
    && lod.componentCount === probe.meshCost.totalComponents
    && lod.belowMinimum === 0 && !lod.busy && !lod.pendingEvaluation;
}

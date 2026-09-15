import { surfWorkerMemoryStats } from "cadgen-js/lib/renderAssetClient.js";

import { viewerMemoryPolicy } from "./viewerMemoryPolicy.js";

export function workerResidentBytesFromStats(stats) {
  const value = Number(stats?.residentEstimateBytes);
  return Number.isFinite(value) && value > 0 ? Math.ceil(value) : 0;
}

export function installSurfWorkerMemoryProvider(
  policy = viewerMemoryPolicy,
  readStats = surfWorkerMemoryStats,
) {
  policy.setRetainedProvider(
    "workerResidentEstimated",
    () => workerResidentBytesFromStats(readStats()),
  );
  return policy;
}

// One shared provider keeps diagnostics and admission current even when the
// pool was changed by a selector, LOD, or package consumer other than the
// caller taking the snapshot.
installSurfWorkerMemoryProvider();

export function syncSurfWorkerMemory() {
  const snapshot = viewerMemoryPolicy.snapshot();
  if (typeof window !== "undefined") window.__cadViewerMemory = snapshot;
  return snapshot;
}

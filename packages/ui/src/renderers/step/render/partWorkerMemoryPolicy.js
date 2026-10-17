import { partWorkerMemoryStats } from "@text-to-cad/core/lib/renderAssetClient.js";

import { viewerMemoryPolicy } from "./viewerMemoryPolicy.js";

export function workerResidentBytesFromStats(stats) {
  const value = Number(stats?.residentEstimateBytes);
  return Number.isFinite(value) && value > 0 ? Math.ceil(value) : 0;
}

export function installPartWorkerMemoryProvider(
  policy = viewerMemoryPolicy,
  readStats = partWorkerMemoryStats,
) {
  policy.setRetainedProvider(
    "workerResidentEstimated",
    () => workerResidentBytesFromStats(readStats()),
  );
  return policy;
}

// One shared provider keeps diagnostics and admission current even when the
// pool was changed by a selector or package consumer other than the
// caller taking the snapshot.
installPartWorkerMemoryProvider();

export function syncPartWorkerMemory() {
  const snapshot = viewerMemoryPolicy.snapshot();
  if (typeof window !== "undefined") window.__cadViewerMemory = snapshot;
  return snapshot;
}

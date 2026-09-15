// Deterministic accounting envelope for allocations the viewer owns or can
// estimate. Browsers expose neither Worker heap nor WebGL driver allocations,
// so this is deliberately not described as a process-RSS limit. The fixed GPU
// headroom covers driver-side overhead that buffer byte lengths cannot see.

export const VIEWER_MEMORY_MIB = 1024 * 1024;
export const DEFAULT_VIEWER_MEMORY_BUDGET_BYTES = 1536 * VIEWER_MEMORY_MIB;
export const DEFAULT_VIEWER_GPU_HEADROOM_BYTES = 256 * VIEWER_MEMORY_MIB;
export const DEFAULT_VIEWER_REPLACEMENT_HEADROOM_BYTES = 128 * VIEWER_MEMORY_MIB;

export const VIEWER_MEMORY_CATEGORIES = Object.freeze([
  "displayCpu",
  "selectors",
  "bvh",
  "gpuEstimated",
  "deformation",
  "assetCaches",
  "workerResidentEstimated",
  "replacementPending",
]);

function bytes(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : 0;
}

export class ViewerMemoryLimitError extends Error {
  constructor(message, detail = {}) {
    super(message);
    this.name = "ViewerMemoryLimitError";
    this.code = "VIEWER_MEMORY_LIMIT";
    this.detail = detail;
  }
}

export function createViewerMemoryPolicy({
  budgetBytes = DEFAULT_VIEWER_MEMORY_BUDGET_BYTES,
  gpuHeadroomBytes = DEFAULT_VIEWER_GPU_HEADROOM_BYTES,
  replacementHeadroomBytes = DEFAULT_VIEWER_REPLACEMENT_HEADROOM_BYTES,
  onLimitation = null,
} = {}) {
  const retained = new Map(VIEWER_MEMORY_CATEGORIES.map((category) => [category, 0]));
  const retainedProviders = new Map();
  const reservations = new Map();
  let nextToken = 1;
  let lastLimitation = null;

  const budget = bytes(budgetBytes);
  const gpuHeadroom = Math.min(budget, bytes(gpuHeadroomBytes));
  const replacementHeadroom = bytes(replacementHeadroomBytes);
  const ownedLimit = Math.max(0, budget - gpuHeadroom);

  function refreshRetainedProviders() {
    for (const [category, provider] of retainedProviders) {
      try {
        retained.set(category, bytes(provider()));
      } catch {
        // Memory diagnostics must not make rendering fail. Keep the last
        // coherent value until the provider can be sampled again.
      }
    }
  }

  function retainedBytes() {
    let total = 0;
    for (const value of retained.values()) total += value;
    return total;
  }

  function reservedBytes() {
    let total = 0;
    for (const reservation of reservations.values()) total += reservation.bytes;
    return total;
  }

  function snapshot() {
    refreshRetainedProviders();
    const retainedByCategory = Object.fromEntries(retained);
    const inFlightByCategory = {};
    for (const reservation of reservations.values()) {
      inFlightByCategory[reservation.category] = (inFlightByCategory[reservation.category] || 0) + reservation.bytes;
    }
    const retainedTotal = retainedBytes();
    const inFlightTotal = reservedBytes();
    return {
      budgetBytes: budget,
      gpuHeadroomBytes: gpuHeadroom,
      ownedLimitBytes: ownedLimit,
      replacementHeadroomBytes: replacementHeadroom,
      retainedByCategory,
      inFlightByCategory,
      retainedBytes: retainedTotal,
      inFlightBytes: inFlightTotal,
      estimatedOwnedBytes: retainedTotal + inFlightTotal,
      availableBytes: Math.max(0, ownedLimit - retainedTotal - inFlightTotal),
      reservationCount: reservations.size,
      lastLimitation,
      hardRssCap: false,
    };
  }

  function setRetained(category, value) {
    if (!retained.has(category)) {
      throw new Error(`Unknown viewer memory category: ${category}`);
    }
    retained.set(category, bytes(value));
    return snapshot();
  }

  function setRetainedProvider(category, provider) {
    if (!retained.has(category)) {
      throw new Error(`Unknown viewer memory category: ${category}`);
    }
    if (typeof provider === "function") retainedProviders.set(category, provider);
    else retainedProviders.delete(category);
    return snapshot();
  }

  function reserve({
    category = "workerInFlight",
    bytes: requested,
    label = "",
    kind = "allocate",
    replacingBytes = 0,
    finalBytes = null,
    recordLimitation = true,
  } = {}) {
    refreshRetainedProviders();
    const amount = bytes(requested);
    const before = retainedBytes() + reservedBytes();
    const isReducingReplacement = kind === "coarsen" &&
      bytes(replacingBytes) > bytes(finalBytes) && bytes(replacingBytes) > 0;
    const limit = ownedLimit + (isReducingReplacement ? replacementHeadroom : 0);
    if (before + amount > limit) {
      const detail = {
        category,
        label: String(label || ""),
        kind,
        requestedBytes: amount,
        estimatedOwnedBytes: before,
        availableBytes: Math.max(0, limit - before),
        ownedLimitBytes: ownedLimit,
        preservingCurrentView: kind === "refine" || kind === "replace",
      };
      if (recordLimitation) {
        lastLimitation = detail;
        onLimitation?.(detail);
      }
      return { ok: false, detail };
    }
    const token = `viewer-memory-${nextToken++}`;
    reservations.set(token, {
      category,
      bytes: amount,
      label: String(label || ""),
      kind,
    });
    return { ok: true, token, bytes: amount };
  }

  function release(token) {
    if (!token) return false;
    return reservations.delete(typeof token === "string" ? token : token.token);
  }

  function reset() {
    for (const category of retained.keys()) retained.set(category, 0);
    reservations.clear();
    lastLimitation = null;
  }

  function noteLimitation(detail) {
    lastLimitation = detail || null;
    if (lastLimitation) onLimitation?.(lastLimitation);
    return lastLimitation;
  }

  function clearLimitation() {
    lastLimitation = null;
  }

  return {
    setRetained,
    setRetainedProvider,
    reserve,
    release,
    snapshot,
    noteLimitation,
    clearLimitation,
    reset,
  };
}

// One ledger spans the asset hook, viewport LOD, renderer diagnostics and idle
// accelerators. It accounts only disposable browser-side data; persistent
// store/tessellation-provider records are outside its ownership.
export const viewerMemoryPolicy = createViewerMemoryPolicy();

if (typeof window !== "undefined") {
  // Read-only browser diagnostic; unlike performance.memory this reports the
  // same categories and admission math in every supported browser.
  window.__cadViewerMemoryPolicySnapshot = () => viewerMemoryPolicy.snapshot();
}

// User-facing detail state is deliberately derived from the scheduler's public
// snapshot. The scheduler owns tessellation work; this module only says what
// the currently displayed geometry means to a person looking at the viewport.

export const VIEWPORT_QUALITY_STATE = Object.freeze({
  PREVIEW: "preview",
  REFINING: "refining",
  STANDARD: "standard",
  HIGH: "high",
  LIMITED: "limited",
  ERROR: "error"
});

const MEMORY_LIMIT_REASONS = new Set(["memory-pressure", "memory-denied"]);
const ERROR_REASONS = new Set(["load-failed", "adoption-refused", "scene-failed"]);

export const VIEWPORT_QUALITY_COPY = Object.freeze({
  [VIEWPORT_QUALITY_STATE.PREVIEW]: {
    label: "Preview detail",
    title: "Preview detail is visible while standard detail is prepared."
  },
  [VIEWPORT_QUALITY_STATE.REFINING]: {
    label: "Refining detail",
    title: "More model detail is loading in the background."
  },
  [VIEWPORT_QUALITY_STATE.STANDARD]: {
    label: "Standard detail",
    title: "The visible model has reached standard detail."
  },
  [VIEWPORT_QUALITY_STATE.HIGH]: {
    label: "High detail",
    title: "High-detail geometry is ready for this view."
  },
  [VIEWPORT_QUALITY_STATE.LIMITED]: {
    label: "Reduced detail",
    title: "Some surfaces are shown at lower detail because the view reached its memory limit. Try zooming out to reduce the detail needed."
  },
  [VIEWPORT_QUALITY_STATE.ERROR]: {
    label: "Detail update failed",
    title: "Some finer details could not be loaded. The model is still shown at lower detail. Reload the viewer to try again."
  }
});

const VIEWPORT_QUALITY_EXTRA_DETAIL_COPY = Object.freeze({
  [VIEWPORT_QUALITY_STATE.LIMITED]: {
    label: "Extra detail limited",
    title: "The model is visible, but there isn’t enough memory for the finer detail requested by this view. Try zooming out."
  },
  [VIEWPORT_QUALITY_STATE.ERROR]: {
    label: "Extra detail failed",
    title: "The model is visible, but the finer detail requested by this view could not be loaded. Reload the viewer to try again."
  }
});

function hasReason(snapshot, reasons) {
  return (snapshot?.unmetTargets || []).some((target) => reasons.has(target?.reason));
}

export function isViewportLodMemoryLimitation(limitation) {
  return limitation?.source === "viewportLod" && Array.isArray(limitation?.unmetTargets)
    && limitation.unmetTargets.length > 0;
}

export function lodSnapshotForFile(snapshot, file) {
  if (!snapshot || snapshot.disposed) {
    return null;
  }
  const snapshotFile = String(snapshot.file || "");
  return snapshotFile && file && snapshotFile !== file ? null : snapshot;
}

export function lodSnapshotForModel(record, modelKey) {
  if (record?.modelKey !== modelKey || record?.snapshot?.modelKey !== modelKey) {
    return null;
  }
  return record.snapshot;
}

/**
 * Map genuine displayed geometry plus the LOD scheduler's public state to one
 * compact label. `modelComplete` prevents an early progressive batch from
 * presenting its temporary standard level as the finished model.
 */
export function viewportQualityStatus({
  hasGeometry = false,
  modelComplete = false,
  lodExpectedComponentCount = 0,
  lodSnapshot = null,
  memoryLimitation = null,
  quality = "standard"
} = {}) {
  if (!hasGeometry) {
    return { state: null, firstPreviewReady: false, standardQualityReady: false };
  }

  const hasLodComponents = Number(lodSnapshot?.componentCount) > 0;
  const expectedComponentCount = Math.max(0, Math.floor(Number(lodExpectedComponentCount) || 0));
  const requiresLod = expectedComponentCount > 0 || hasLodComponents;
  // A progressive package may publish 24 or 56 components before its final 69.
  // Its earlier snapshot is useful for its own preview, never proof that the
  // newly complete package has reached standard detail.
  const componentScopeMatches = expectedComponentCount === 0 ||
    Number(lodSnapshot?.componentCount) === expectedComponentCount;
  const firstPreviewReady = true;
  const standardQualityReady = Boolean(
    modelComplete && (requiresLod
      ? hasLodComponents && componentScopeMatches && lodSnapshot?.standardSettled === true
      : true)
  );
  const requestedQuality = typeof quality === "string" ? quality : quality?.id || "standard";
  const highRequested = requestedQuality === "high";
  const qualityScopeMatches = !highRequested || lodSnapshot?.quality === requestedQuality;
  const highQualityReady = Boolean(highRequested && requiresLod && standardQualityReady &&
    qualityScopeMatches && lodSnapshot?.qualitySettled === true &&
    !lodSnapshot?.busy && !lodSnapshot?.pendingEvaluation);

  // The scheduler's current targets are authoritative. A memory event may
  // arrive before its next status event, but must not leave a cleared limit
  // stuck on screen after the scheduler reports no unmet targets.
  let state;
  if (lodSnapshot?.sceneFailed || hasReason(lodSnapshot, ERROR_REASONS)) {
    state = VIEWPORT_QUALITY_STATE.ERROR;
  } else if (lodSnapshot
    ? hasReason(lodSnapshot, MEMORY_LIMIT_REASONS)
    : isViewportLodMemoryLimitation(memoryLimitation)) {
    state = VIEWPORT_QUALITY_STATE.LIMITED;
  } else if (!lodSnapshot) {
    // Mesh formats without component refinement are already displayed at
    // their normal detail once their complete asset is available.
    state = standardQualityReady ? VIEWPORT_QUALITY_STATE.STANDARD : VIEWPORT_QUALITY_STATE.PREVIEW;
  } else if (!modelComplete) {
    state = VIEWPORT_QUALITY_STATE.PREVIEW;
  } else if (requiresLod && !qualityScopeMatches) {
    state = VIEWPORT_QUALITY_STATE.REFINING;
  } else if (lodSnapshot.busy || lodSnapshot.pendingEvaluation || hasReason(lodSnapshot, new Set(["pending"]))) {
    state = VIEWPORT_QUALITY_STATE.REFINING;
  } else if (highQualityReady) {
    state = VIEWPORT_QUALITY_STATE.HIGH;
  } else if (standardQualityReady) {
    state = VIEWPORT_QUALITY_STATE.STANDARD;
  } else if (requiresLod && Number(lodSnapshot.belowMinimum) > 0) {
    state = VIEWPORT_QUALITY_STATE.PREVIEW;
  } else {
    state = VIEWPORT_QUALITY_STATE.REFINING;
  }

  return {
    state,
    ...(standardQualityReady && VIEWPORT_QUALITY_EXTRA_DETAIL_COPY[state]
      ? VIEWPORT_QUALITY_EXTRA_DETAIL_COPY[state]
      : VIEWPORT_QUALITY_COPY[state]),
    firstPreviewReady,
    standardQualityReady,
    highQualityReady,
    quality: requestedQuality
  };
}

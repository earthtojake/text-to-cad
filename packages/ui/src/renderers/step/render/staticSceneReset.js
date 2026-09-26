// A static source adoption already reset and synchronized these records. This
// one-use receipt applies only to the following effect in the SAME React render;
// it is never a cache of a later visual, clipping, pose or animation update.
export function staticSceneResetEligible({ source, renderFormat, parameters, animation,
  exploded = false, loading = false, records = [] } = {}) {
  return (renderFormat === "step" || renderFormat === "stp")
    && source?.partTransformsBaked === false && !source.geometrySource
    && Array.isArray(source.parts) && source.parts.length > 0
    && !parameters && !animation && !exploded && !loading
    && !records.some(record => record?.effectMatrix || record?.effectStyle
      || record?.effectVisible != null || record?.effectHighlighted || record?.explodedViewMatrix
      || record?.effectDeformation || record?.tubeDeformationState?.active || record?.tubeGpuState?.active);
}

export function createStaticSceneReset() {
  let renderToken = null;
  let previousEligible = false;
  let canComplete = false;
  let completed = null;
  return {
    // Called by a layout effect, so abandoned concurrent renders cannot alter
    // the previous committed scene's eligibility. The first static render after
    // any dynamic one keeps the ordinary reset, even if adoption clears effects.
    beginRender(token, eligible) {
      completed = null;
      if (token === renderToken) {
        canComplete &&= eligible;
        return;
      }
      renderToken = token;
      canComplete = previousEligible && eligible;
      previousEligible = eligible;
    },
    complete(token, { source, runtime, visualState, clipState }) {
      completed = null;
      if (!canComplete || token !== renderToken || !runtime?.cadScene
        || runtime.cadScene.source !== source || !runtime.displayRecords?.length) return;
      completed = { source, runtime, scene: runtime.cadScene, records: runtime.displayRecords,
        modelKey: runtime.activeModelKey, visualState, clipState };
    },
    consume(token, { source, runtime, visualState, clipState }) {
      const receipt = completed;
      completed = null;
      return Boolean(receipt && token === renderToken && canComplete
        && source === receipt.source && runtime === receipt.runtime
        && runtime.cadScene === receipt.scene && runtime.cadScene.source === source
        && runtime.displayRecords === receipt.records && runtime.activeModelKey === receipt.modelKey
        && visualState === receipt.visualState && clipState === receipt.clipState);
    },
    invalidate() { completed = null; },
    reset() { renderToken = null; previousEligible = false; canComplete = false; completed = null; },
  };
}

import { useEffect } from "react";
import * as THREE from "three";
import { createTopologyDisplayEdgeObject as createSharedTopologyDisplayEdgeObject } from "@hardcore/core/common/renderEdges.js";
import { syncRuntimeStepClipPlane } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { applyPartVisualState, FOCUSED_DIMMED_SURFACE_OPACITY, normalizePartIdList } from "@hardcore/core/lib/viewer/partVisualState.js";
import { REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER, REFERENCE_SELECTED_COLOR } from "@hardcore/core/lib/viewer/referenceGeometry.js";
import { syncDisplayMeshFaceIds, syncSelectorPickGroups } from "@hardcore/core/lib/viewer/selectorPickGroups.js";
import { BASE_VIEWER_THEME } from "@hardcore/core/lib/viewer/stageTheme.js";
import { createRecordTopologyDisplayEdgeGroup, syncTopologyDisplayEdgeLine } from "@hardcore/core/lib/viewer/topologyDisplayEdgeLine.js";
import { clamp } from "../../kit/camera/viewportCameraKit.js";
import { clearSceneGroup } from "./useStepSceneSync.js";

const MODEL_OFFSET = new THREE.Vector3(0, 0, 0);

function getEdgeThickness(edgeSettings = null, viewerTheme = null) {
  const fallbackThickness = Number.isFinite(Number(viewerTheme?.edgeThickness))
    ? Number(viewerTheme.edgeThickness)
    : BASE_VIEWER_THEME.edgeThickness;
  return Number.isFinite(Number(edgeSettings?.thickness))
    ? clamp(Number(edgeSettings.thickness), 0.5, 6)
    : fallbackThickness;
}

export function getHighlightEdgeThickness(edgeSettings = null, viewerTheme = null) {
  return Number.isFinite(Number(edgeSettings?.highlightThickness))
    ? clamp(Number(edgeSettings.highlightThickness), 0.5, 6)
    : Math.max(getEdgeThickness(edgeSettings, viewerTheme) * REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER, 2);
}

export function getHighlightEdgeOpacity(edgeSettings = null) {
  return Number.isFinite(Number(edgeSettings?.highlightOpacity))
    ? clamp(Number(edgeSettings.highlightOpacity), 0, 1)
    : 1;
}

export function getHighlightEdgeColor(edgeSettings = null) {
  return String(edgeSettings?.highlightColor || REFERENCE_SELECTED_COLOR).trim() || REFERENCE_SELECTED_COLOR;
}

function disposeOverlayChild(runtime, child) {
  if (!child) {
    return;
  }
  while (child.children?.length) {
    const nested = child.children[0];
    child.remove(nested);
    disposeOverlayChild(runtime, nested);
  }
  if (typeof child.userData?.beforeDispose === "function") {
    child.userData.beforeDispose(child);
    delete child.userData.beforeDispose;
  }
  const materials = Array.isArray(child.material) ? child.material : [child.material];
  if (child.userData?.disposeGeometry !== false) {
    child.geometry?.dispose?.();
  }
  if (child.userData?.disposeMaterial !== false) {
    for (const material of materials) {
      material?.dispose?.();
    }
  }
}

export function clearOverlayGroup(runtime, group) {
  while (group?.children?.length) {
    const child = group.children[group.children.length - 1];
    if (!child) {
      continue;
    }
    group.remove(child);
    disposeOverlayChild(runtime, child);
  }
  if (group) {
    group.visible = false;
  }
}

/**
 * Hidden, isolated, hovered and selected parts, put ON the records the scene sync made
 * (`applyPartVisualState`). It runs when the part state or the display changes -- never for a
 * pose, which owns its own frame (`useStepPose.js`).
 */
export function useStepPartVisualState(layers) {
  const { viewport, props, policy, refs } = layers;
  const { runtimeRef, viewerReadyTick } = viewport;
  const { pickMode, pickableParts, hiddenPartIds, selectedPartIds, hoveredPartId } = props;
  const { viewerTheme, normalizedDisplayMode, visualEdgeSettings, focusedPartIds, partVisualStateEnabled } = policy;
  const { recordEdgesVisible } = layers.edges;
  const { partVisualStateRef, lodCameraChangeRef } = refs;
  // A selected part is detail the camera sample must keep, whatever else it drops.
  const lodSelectionKey = normalizePartIdList(selectedPartIds).join("\u0000");

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
    runtime.cadScene?.syncSurfaceInstances();
    runtime.requestRender();
  }, [viewerReadyTick, partVisualStateEnabled, recordEdgesVisible, focusedPartIds, hiddenPartIds, hoveredPartId, pickMode, pickableParts, selectedPartIds, viewerTheme, visualEdgeSettings, normalizedDisplayMode]);

  useEffect(() => {
    lodCameraChangeRef.current?.();
  }, [lodSelectionKey]);

}

/**
 * The linework and the pick proxies: what the selector runtime AS POSED carries for the
 * pointer, the B-rep edges the display asks for, and the brighter edges of a highlighted part.
 */
export function useStepLinework(layers) {
  const { viewport, props, policy, refs, activeSelectorRuntime, activeDisplayEdgeRuntime } = layers;
  const { runtimeRef, viewerReadyTick } = viewport;
  const { meshData, modelKey, selectedPartIds, hoveredPartId, selectorRuntime, displayEdgeRuntime } = props;
  const { viewerTheme, displayEdgeSettings, visualEdgeSettings, hiddenAwareVisualEdgeSettings, focusedPartIds, hiddenPartIdSet } = policy;
  const { topologyDisplayEdgesVisible } = layers.edges;
  const { clipSettingsRef } = refs;

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgePickGroup || !runtime?.facePickGroup || !runtime?.vertexPickGroup) {
      return;
    }

    syncDisplayMeshFaceIds(runtime, meshData, activeSelectorRuntime);
    syncSelectorPickGroups(runtime, activeSelectorRuntime, MODEL_OFFSET, { clearSceneGroup });
    syncRuntimeStepClipPlane(runtime, clipSettingsRef.current);
  }, [activeSelectorRuntime, meshData, modelKey, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const transformByRecord = runtime.topologyDisplayEdgeTransformByRecord === true;
    syncTopologyDisplayEdgeLine(
      runtime,
      transformByRecord
        ? (displayEdgeRuntime || selectorRuntime)
        : (activeDisplayEdgeRuntime || activeSelectorRuntime),
      {
        visible: topologyDisplayEdgesVisible,
        edgeSettings: hiddenAwareVisualEdgeSettings,
        focusedPartIds,
        viewerTheme,
        dimmedOpacity: FOCUSED_DIMMED_SURFACE_OPACITY,
        transformByRecord,
        displayRecords: runtime.displayRecords,
        syncClip: (activeRuntime) => syncRuntimeStepClipPlane(activeRuntime, clipSettingsRef.current)
      }
    );
  }, [activeDisplayEdgeRuntime, activeSelectorRuntime, displayEdgeRuntime, viewerReadyTick, viewerTheme, focusedPartIds, hiddenAwareVisualEdgeSettings, selectorRuntime, topologyDisplayEdgesVisible, visualEdgeSettings]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.partHighlightGroup || runtime.partHighlightGroup.parent !== edgesGroup) {
      runtime.partHighlightGroup = new THREE.Group();
      runtime.partHighlightGroup.renderOrder = 22;
      edgesGroup.add(runtime.partHighlightGroup);
    }
    const highlightGroup = runtime.partHighlightGroup;
    clearOverlayGroup(runtime, highlightGroup);

    const highlightedPartIds = [];
    const seenPartIds = new Set();
    const addHighlightedPartId = (partId) => {
      const normalizedPartId = String(partId || "").trim();
      if (!normalizedPartId || hiddenPartIdSet.has(normalizedPartId) || seenPartIds.has(normalizedPartId)) {
        return;
      }
      seenPartIds.add(normalizedPartId);
      highlightedPartIds.push(normalizedPartId);
    };
    for (const partId of normalizePartIdList(selectedPartIds)) {
      addHighlightedPartId(partId);
    }
    for (const partId of normalizePartIdList(hoveredPartId)) {
      addHighlightedPartId(partId);
    }

    if (topologyDisplayEdgesVisible && highlightedPartIds.length) {
      const highlightEdgeSettings = {
        ...hiddenAwareVisualEdgeSettings,
        thickness: getHighlightEdgeThickness(displayEdgeSettings, viewerTheme),
        highlightPartIds: highlightedPartIds,
        highlightColor: getHighlightEdgeColor(displayEdgeSettings),
        highlightOpacity: getHighlightEdgeOpacity(displayEdgeSettings),
        highlightRenderOrder: 26
      };
      const highlightLine = runtime.topologyDisplayEdgeTransformByRecord === true && displayEdgeRuntime
        ? createRecordTopologyDisplayEdgeGroup(runtime, displayEdgeRuntime, {
            edgeSettings: highlightEdgeSettings,
            viewerTheme,
            displayRecords: runtime.displayRecords
          })
        : createSharedTopologyDisplayEdgeObject(
            runtime,
            activeDisplayEdgeRuntime || activeSelectorRuntime,
            highlightEdgeSettings,
            viewerTheme
          );
      if (highlightLine) {
        highlightGroup.add(highlightLine);
      }
    }

    highlightGroup.visible = highlightGroup.children.length > 0;
    // A frame for what THIS layer changed, and only that: a pass that had nothing drawn and
    // draws nothing (every pose with no part highlighted) leaves the frame to whoever moved
    // the model (`useStepPose.js`).
    const drawn = highlightGroup.children.length > 0;
    if (drawn || runtime.partHighlightDrawn === true) runtime.requestRender();
    runtime.partHighlightDrawn = drawn;

    return () => {
      clearOverlayGroup(runtime, highlightGroup);
    };
  }, [
    activeDisplayEdgeRuntime,
    activeSelectorRuntime,
    displayEdgeRuntime,
    displayEdgeSettings,
    hiddenAwareVisualEdgeSettings,
    hiddenPartIdSet,
    viewerReadyTick,
    viewerTheme,
    hoveredPartId,
    modelKey,
    selectedPartIds,
    topologyDisplayEdgesVisible,
    visualEdgeSettings
  ]);
}

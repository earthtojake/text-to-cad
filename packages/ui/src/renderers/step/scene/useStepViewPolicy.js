import { useCallback, useMemo } from "react";
import { resolveDisplayMaterialSettings } from "@hardcore/core/common/sceneSettings.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "@hardcore/core/common/photographicStudioRig.js";
import { shouldShowRecordDisplayEdges } from "@hardcore/core/lib/viewer/displayEdgePolicy.js";
import {
  displayModeForcesEdges, displayModeIsWireframe, displayModeShowsEdges, displayModeShowsThroughEdges
} from "@hardcore/core/lib/displaySettings.js";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";
import { normalizePartIdList, referenceMatchesFocusedPart } from "@hardcore/core/lib/viewer/partVisualState.js";
import { toNumber } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { BASE_VIEWER_THEME } from "@hardcore/core/lib/viewer/stageTheme.js";
import { shouldRenderTopologyDisplayEdges } from "@hardcore/core/common/topologyDisplayEdgeRuntime.js";
import { clamp } from "../../kit/camera/viewportCameraKit.js";
import { createViewerRenderStateResolver } from "../../kit/view-settings/renderState.js";

const CAD_EDGE_OPACITY = 0.84;
// The viewer's own base theme; a STEP has no other.
const viewerTheme = BASE_VIEWER_THEME;

// The look half of the policy below, answerable on its own. The viewport has to know
// whether the scene is drawn with one-pixel linework before it knows what is pickable in
// it: that is what decides whether the pixel ratio holds while the camera moves.
const hairlineResolver = createViewerRenderStateResolver();
export function viewDrawsHairlines(themeSettings, displaySettings) {
  const state = hairlineResolver({ themeSettings, displaySettings });
  return displayModeIsWireframe(state.displayMode) ||
    (state.displaySettings.surfaces ? state.edgeSettings.enabled : displayModeShowsEdges(state.displayMode));
}

export function renderableMeshParts(meshData) {
  return Array.isArray(meshData?.parts)
    ? meshData.parts.filter((part) => toNumber(part?.vertexCount) > 0 && toNumber(part?.triangleCount) > 0)
    : [];
}

/**
 * Everything the STEP viewport DERIVES from its settings and its selection, and nothing that
 * touches the scene: the normalized display state, which of the three kinds of linework is
 * drawn, the edge styling each display mode forces, what is pickable once hidden and isolated
 * parts are taken out, and whether part visual state is in play at all. One derivation, read
 * by every layer, so no two of them can disagree about what is on screen.
 *
 * `edgeRuntimes` are the selector and display-edge runtimes as POSED (the layers own those);
 * they decide whether the topology linework has anything to draw.
 */
export function useStepViewPolicy({
  meshData, themeSettings, displaySettings, renderMode, renderConfiguration, renderPartsIndividually,
  pickMode, pickableParts, pickableFaces, pickableEdges, hiddenPartIds, selectedPartIds, focusedPartId
}) {
  const resolveViewerRenderState = useMemo(() => createViewerRenderStateResolver(), []);
  const normalizedViewerRenderState = useMemo(() => resolveViewerRenderState({
    themeSettings,
    displaySettings
  }), [resolveViewerRenderState, themeSettings, displaySettings]);
  const normalizedThemeSettings = normalizedViewerRenderState.themeSettings;
  const normalizedDisplaySettings = normalizedViewerRenderState.displaySettings;
  const normalizedDisplayMode = normalizedViewerRenderState.displayMode;
  const surfaceSettings = normalizedDisplaySettings.surfaces;
  const explicitViewPolicy = Boolean(surfaceSettings);
  const photographicLighting = renderMode && renderConfiguration?.lighting?.enabled !== false;
  const normalizedMaterialSettings = useMemo(
    () => resolveDisplayMaterialSettings(
      photographicLighting ? PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS : normalizedThemeSettings.materials,
      normalizedDisplaySettings.partColor
    ),
    [normalizedDisplaySettings.partColor, normalizedThemeSettings.materials, photographicLighting]
  );
  const materialPartPolicyKey = `${
    normalizedMaterialSettings.cycleColors === true &&
    Array.isArray(normalizedMaterialSettings.fillColors) &&
    normalizedMaterialSettings.fillColors.length > 1
  }:${normalizedMaterialSettings.overrideSourceColors === true}`;
  const normalizedExplodedSettings = normalizedDisplaySettings.exploded;
  const explodeAmount = clamp(toNumber(normalizedExplodedSettings.amount, 1), 0, 1);
  const explodablePartCount = useMemo(() => renderableMeshParts(meshData).length, [meshData]);
  const explodedViewActive = normalizedExplodedSettings.enabled && explodablePartCount > 1;
  const effectiveRenderPartsIndividually = renderPartsIndividually ||
    explodedViewActive;
  const displayEdgeSettings = normalizedViewerRenderState.edgeSettings;
  const wireframeMode = displayModeIsWireframe(normalizedDisplayMode);
  const displayModeForceEdges = !explicitViewPolicy && displayModeForcesEdges(normalizedDisplayMode);
  const displayModeThroughEdges = !explicitViewPolicy && displayModeShowsThroughEdges(normalizedDisplayMode);
  const wireframeEdgeColor = displayEdgeSettings.color;
  const wireframeEdgeOpacity = useMemo(() => {
    const baseOpacity = Number.isFinite(Number(displayEdgeSettings?.opacity))
      ? clamp(Number(displayEdgeSettings.opacity), 0, 1)
      : (viewerTheme?.edgeOpacity ?? BASE_VIEWER_THEME.edgeOpacity ?? CAD_EDGE_OPACITY);
    return Math.max(baseOpacity, 0.9);
  }, [displayEdgeSettings, viewerTheme]);
  const visualEdgeSettings = useMemo(() => {
    const forcedSettings = {
      ...displayEdgeSettings,
      enabled: displayModeForceEdges ? true : displayEdgeSettings.enabled,
      depthTest: displayModeThroughEdges ? false : displayEdgeSettings.depthTest
    };
    return wireframeMode
      ? {
          ...forcedSettings,
          color: wireframeEdgeColor,
          opacity: wireframeEdgeOpacity
        }
      : forcedSettings;
  }, [
    displayEdgeSettings,
    displayModeForceEdges,
    displayModeThroughEdges,
    wireframeEdgeColor,
    wireframeEdgeOpacity,
    wireframeMode
  ]);
  const focusedPartIds = useMemo(() => normalizePartIdList(focusedPartId), [focusedPartId]);
  const focusedPartIdSet = useMemo(() => new Set(focusedPartIds), [focusedPartIds]);
  const hiddenPartIdSet = useMemo(() => new Set(normalizePartIdList(hiddenPartIds)), [hiddenPartIds]);
  const hiddenAwareVisualEdgeSettings = useMemo(() => {
    const hiddenIds = normalizePartIdList(hiddenPartIds);
    if (!hiddenIds.length) {
      return visualEdgeSettings;
    }
    const excludePartIds = [
      ...new Set([
        ...normalizePartIdList(visualEdgeSettings?.excludePartIds),
        ...hiddenIds
      ])
    ];
    return {
      ...visualEdgeSettings,
      excludePartIds
    };
  }, [hiddenPartIds, visualEdgeSettings]);
  const normalizedClipSettings = normalizedViewerRenderState.clipSettings;
  const partVisualStateEnabled =
    (Array.isArray(selectedPartIds) && selectedPartIds.length > 0) ||
    pickMode === VIEWER_PICK_MODE.PARTS ||
    pickMode === VIEWER_PICK_MODE.ASSEMBLY ||
    (
      pickMode === VIEWER_PICK_MODE.AUTO &&
      Array.isArray(pickableParts) &&
      pickableParts.length > 0
    ) ||
    (Array.isArray(hiddenPartIds) && hiddenPartIds.length > 0) ||
    focusedPartIds.length > 0;
  const visibleReferenceFilter = useCallback((reference) => {
    const partId = String(reference?.partId || "").trim();
    if (partId && hiddenPartIdSet.has(partId)) {
      return false;
    }
    if (!partId && hiddenPartIdSet.has("__model__")) {
      return false;
    }
    return referenceMatchesFocusedPart(reference, focusedPartIdSet);
  }, [focusedPartIdSet, hiddenPartIdSet]);
  const filteredPickableFaces = useMemo(
    () => (Array.isArray(pickableFaces) ? pickableFaces : []).filter(visibleReferenceFilter),
    [pickableFaces, visibleReferenceFilter]
  );
  const filteredPickableEdges = useMemo(
    () => (Array.isArray(pickableEdges) ? pickableEdges : []).filter(visibleReferenceFilter),
    [pickableEdges, visibleReferenceFilter]
  );
  // Edges are drawn when the view asks for them. STEP linework comes from the B-rep
  // topology: the topology line when a runtime carries it, else the build's own record edges.
  const edgesVisible = explicitViewPolicy ? displayEdgeSettings.enabled : displayModeShowsEdges(normalizedDisplayMode);
  const edgeVisibility = useCallback(({ selectorRuntime }) => {
    const topologyDisplayEdgesVisible = shouldRenderTopologyDisplayEdges({
      edgesVisible, wireframeMode, cadEdgeSource: true, selectorRuntime, edgeSettings: visualEdgeSettings
    });
    const surfaceStepEdgesVisible = edgesVisible && !topologyDisplayEdgesVisible;
    return {
      topologyDisplayEdgesVisible, surfaceStepEdgesVisible,
      recordEdgesVisible: shouldShowRecordDisplayEdges({
        edgesVisible, topologyDisplayEdgesVisible, displayEdgesVisible: false, cadEdgesVisible: surfaceStepEdgesVisible, wireframeMode
      })
    };
  }, [edgesVisible, wireframeMode, visualEdgeSettings]);

  return {
    viewerTheme, normalizedThemeSettings, normalizedDisplaySettings, normalizedDisplayMode, surfaceSettings, explicitViewPolicy,
    photographicLighting, normalizedMaterialSettings, materialPartPolicyKey, normalizedExplodedSettings, explodeAmount,
    explodedViewActive, effectiveRenderPartsIndividually, displayEdgeSettings, wireframeMode, wireframeEdgeColor,
    visualEdgeSettings, hiddenAwareVisualEdgeSettings, focusedPartIds, focusedPartIdSet, hiddenPartIdSet, normalizedClipSettings,
    partVisualStateEnabled, edgesVisible, edgeVisibility, filteredPickableFaces, filteredPickableEdges,
    visibleReferenceFilter
  };
}

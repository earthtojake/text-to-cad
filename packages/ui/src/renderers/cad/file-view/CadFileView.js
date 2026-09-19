import { buildEdgeChainGraph } from "../workbench/edgeChainSelection.js";
"use client";

import StepMeasurementsSection from "../components/workbench/StepMeasurementsSection.js";
import SelectionFilterMenu from "../components/workbench/SelectionFilterMenu.jsx";
import { stepGeometryContextText, stepGeometryPromptText } from "../workbench/stepGeometryPrompt.js";
import { filterSelectionReferences, toggleReferenceGroupSelection, connectedReferenceIds, MEASURE_SELECTION_FILTERS } from "../workbench/selectionFilter.js";
import { buildTangentFaceGraph } from "../workbench/tangentFaceSelection.js";

import { FileSheetTabPreferencesContext } from "../workbench/fileSheetTabPreferences.js";
import { buildRobotComponentGeometry, robotComponents } from "../workbench/robotComponents.js";
import { useRobotComponentSelection } from "../workbench/useRobotComponentSelection.js";

import * as THREE from "three";
import { startTransition, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ArrowLeftRight, ArrowRight, Circle, Eraser, FileText, Minus, PaintBucket, PenTool, Square } from "lucide-react";
import { CAD_PANEL, EmptyState } from "@hardcore/ui/navigation";
import { cn } from "@hardcore/ui/utils";
import CadRenderPane from "../components/workbench/CadRenderPane.js";
import { useViewportLod } from "../render/useViewportLod.js";
import { lodSceneMayMove } from "../render/lodCameraSample.js";
import { registerLodDisplaySource } from "../render/lodSceneAdoption.js";
import { buildDisplaySettingsTab } from "../components/workbench/DisplaySettingsTab.js";
import { buildRenderSettingsTab } from "../components/workbench/RenderSettingsTab.js";
import { buildMaterialsSettingsTab } from "../components/workbench/MaterialsSettingsTab.js";
import { prefetchRenderStudio } from "../render/renderStudioChunk.js";
import MeshFileSheet from "../components/workbench/MeshFileSheet.js";
import { DXF_PREVIEW_REFERENCE_THICKNESS_MM } from "@hardcore/core/lib/dxf/previewGlb.js";
import { dxfDataIsDocument } from "@hardcore/core/lib/dxf/parseDxf.js";
import { loadRenderDxf } from "@hardcore/core/lib/renderAssetClient.js";
import { extractOrderedDxfBendLines } from "@hardcore/core/lib/dxf/buildPreviewMesh.js";
import {
  buildDxfBendsTab,
  buildDxfMaterialTab,
  DXF_DEFAULT_BEND_ANGLE_DEG,
  DXF_DEFAULT_BEND_RADIUS_MM,
  DXF_DEFAULT_BEND_STYLE,
  DXF_DEFAULT_KFACTOR,
  DXF_DEFAULT_MATERIAL,
  DXF_DEFAULT_ORIENTATION,
  DXF_DEFAULT_THICKNESS_MM,
  DXF_DEFAULT_UNITS,
  normalizeDxfBendAngleDeg,
  normalizeDxfBendDirection,
  normalizeDxfBendRadiusMm,
  normalizeDxfBendStyle,
  dxfMaterialPreset,
  normalizeDxfKFactor,
  normalizeDxfMaterial,
  normalizeDxfOrientation,
  normalizeDxfThicknessMm,
  normalizeDxfUnits
} from "../components/workbench/DxfSettingsSection.js";
import { buildDxfLayersTab } from "../components/workbench/DxfLayersSection.js";
import {
  DXF_DEFAULT_DIMENSION_DISPLAY,
  DXF_DEFAULT_LINE_WEIGHT,
  buildDxfSheetTab,
  dxfDimensionDisplayParams,
  dxfLineWeightScale,
  normalizeDxfDimensionDisplay,
  normalizeDxfLineWeight
} from "../components/workbench/DxfSheetSection.js";
import { drawingSheetFacts } from "../workbench/drawingSheetFacts.js";
import {
  createDrawingEditId,
  drawingEditParams,
  drawingEditsPromptText,
  nearestView,
  netViewMoves,
  sheetSnapTargets,
  smartDimensionFromSnaps,
  viewAtSheetPoint
} from "../workbench/drawingEdits.js";
import StepFileSheet from "../components/workbench/StepFileSheet.js";
import { FileSheetPortalContext, HostPanelSlotContext } from "../components/workbench/FileSheet.js";
import { poseValuesForPreset } from "../components/workbench/PoseControlsSection.js";
import { usePoseTransition, usePoseValueAnimation } from "../workbench/poseTransition.js";
import StatusToast from "../components/workbench/StatusToast.js";
import UrdfFileSheet from "../components/workbench/UrdfFileSheet.js";
import ViewerAlertDialog from "../components/workbench/ViewerAlertDialog.js";
import ViewerLoadingOverlay from "../components/workbench/ViewerLoadingOverlay.js";
import {
  ARTIFACT_PROGRESS_POLL_MS
} from "../workbench/artifactProgress.js";
import FloatingToolBar from "../components/workbench/FloatingToolBar.js";
import { useCadAssets } from "../components/workbench/hooks/useCadAssets.js";
import { resolveDesktopPanelWidth } from "./fileViewState.js";
import { useEditingPreview } from "../components/workbench/hooks/useEditingPreview.js";
import { useViewportQualityStatus } from "../components/workbench/hooks/useViewportQualityStatus.js";
import { previewGeometryChanged } from "../workbench/editingPreview.js";
import { buildArtifactWarningAlert } from "../workbench/artifactWarnings.js";
import { resolveFileStatus } from "../workbench/fileStatus.js";
import { viewerLoadingState } from "../workbench/viewerLoading.js";
import { useCadWorkspaceSelection } from "../components/workbench/hooks/useCadWorkspaceSelection.js";
import { useCadWorkspaceSelectors } from "../components/workbench/hooks/useCadWorkspaceSelectors.js";
import { useCadWorkspaceShortcuts } from "../components/workbench/hooks/useCadWorkspaceShortcuts.js";
import { useSourceMaterialSession } from "../components/workbench/hooks/useSourceMaterialSession.js";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  normalizeDisplaySettings
} from "@hardcore/core/lib/displaySettings.js";
import { RENDER_QUALITY, resolveSceneSettings } from "@hardcore/core/common/sceneSettings.js";
import {
  annotatePerspectiveSnapshot,
  clonePerspectiveSnapshot
} from "@hardcore/core/lib/perspective.js";
import {
  ASSET_STATUS,
  DRAWING_TOOL,
  RENDER_FORMAT,
  REFERENCE_STATUS,
  TAB_TOOL_MODE
} from "../workbench/constants.js";
import {
  FILE_SHEET_SECTION_IDS,
  defaultOpenFileSheetSectionIds,
  normalizeFileSheetOpenSectionIds,
  renderedFileSheetSectionIds,
  shouldOpenFileSheetForSelectionReveal
} from "../workbench/fileSheetSections.js";
import { useEmbeddedGlbAnimation } from "../workbench/useEmbeddedGlbAnimation.js";
import {
  entrySourceFormat,
  fileSheetKindForEntry,
  isRobotRenderFormat
} from "@hardcore/core/lib/fileFormats.js";
import {
  assetKindForRenderFormat,
  hasCapability,
  isArtifactManagedFormat,
  parameterSourceKind,
  renderCapabilities,
  renderFormatLabel,
  supportsTool,
  viewportContentKind,
  ASSET_KIND,
  PARAMETER_SOURCE,
  VIEWPORT_CONTENT
} from "@hardcore/core/lib/renderCapabilities.js";
import {
  buildViewerAnnotationAlert,
  buildViewerMeshAlert,
  buildViewerEditAlert,
  fileStatusAlertKey,
  resolveFileStatusAlert
} from "../workbench/viewerAlerts.js";
import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText
} from "../workbench/parameterControls.js";
import {
  buildNormalizedReferenceState,
  buildReferenceCacheKey,
  buildSelectionCopyButtonLabel,
  buildSelectionCopyCountLabel,
  buildSelectionCopyPayload,
  buildWholeStepEntryCopyReference,
  canonicalCadRefCopyText,
  withFileRefPrefix,
  computeNextSelectionIds,
  modelReferenceActivationDecision,
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
  topologyCompositionKeyMatches,
  uniqueStringList
} from "../workbench/referenceSelection.js";
import {
  entryAssetHash,
  entryAssetUrl,
  entryHasDisplayEdges,
  entryHasDxf,
  entryHasMesh,
  entryHasReferences,
  entryHasUrdf,
  entryMeshAssetSignature,
  entryPoseUrl,
  entryUrdfAssetHash
} from "@hardcore/core/lib/entryAssets.js";
import {
  hasStepGlbByteCost,
  isLargeMeshData,
  isLargeStepGlbEntry
} from "@hardcore/core/lib/render/meshCost.js";
import { cloneDrawingStrokes, cloneTabSnapshot, createTabRecord, drawingStrokesEqual,
  tabSnapshotEqual } from "../workbench/state.js";
import { createFileSessionSnapshot, normalizeFileSessionState } from "../workbench/fileSessionState.js";
import { shallowObjectValuesEqual, toFiniteNumber } from "../workbench/valueUtils.js";
import {
  createRenderSessionState,
  renderCameraSeed,
  renderCameraSnapshot,
  renderSessionForEnabledChange,
  renderSessionForReset,
  renderVisualPayload,
  renderVisualSettingsKey,
  resolveRenderSessionQuality,
  resolveRenderCameraSnapshot,
  readRenderSessionCamera,
  setRenderPayloadValue
} from "../workbench/renderSessionState.js";
import {
  advanceAnimationElapsed,
  animationClipDuration,
  animationClipList,
  animationNowMs,
  animationRenderFrame,
  buildDefaultAnimationState,
  clampAnimationElapsed,
  clampAnimationSpeed,
  findAnimationClip,
  firstAnimationClipId,
  restoreAnimationState,
  shouldPublishAnimationFrame
} from "@hardcore/core/common/animationClock.js";
import { createEmbeddedGlbAnimationClock, EmbeddedGlbAnimationClockProvider } from "../workbench/embeddedGlbAnimationClockStore.js";
import { createAnimationClock, AnimationClockProvider, useAnimationClockStore } from "../workbench/animationClockStore.js";
import { resolveStepModuleLoad } from "../workbench/stepModuleLoad.js";
import {
  applyMeasureRulerDelete,
  applyMeasureRulerHover,
  applyMeasureRulerPick,
  cancelMeasureRulerDraft,
  clearMeasureRulerMeasurements,
  measureRulerStateForChange
} from "../workbench/measureRulerState.js";
import {
  buildUrdfJointAnglesCopyText,
  cloneJointValueMap,
  findBestMatchingJointValueState,
  interpolateTrajectoryJointValues,
  srdfHomeGroupStateJointValuesToDisplay,
  srdfGroupStateJointValuesToDisplay
} from "../workbench/robotMotionControls.js";
import { CAD_WORKSPACE_LAYOUT_MODE } from "../workbench/breakpoints.js";
import { cadFileParamForEntry, cadPathForEntry, fileKey, sidebarLabelForEntry } from "../workbench/entryPaths.js";
import { buildCadRefToken, isNativeCadSelector } from "@hardcore/core/lib/cadRefs.js";
import {
  stepModuleRequiresTopology,
  stepModuleTopologyOccurrenceIds
} from "../workbench/topologyCapabilities.js";
import { shortestUniquePathSuffixes } from "@hardcore/core/lib/filePathSuffix.js";
import {
  applyUrdfPoseToMeshData,
  buildDefaultUrdfJointValues,
  buildUrdfMeshGeometry,
  clampJointValueDeg,
  linkOriginInFrame,
  rootPointInFrame
} from "@hardcore/core/lib/urdf/kinematics.js";
import {
  advanceUrdfJointValues,
  interpolateUrdfJointValues,
  jointValueMapsClose,
  URDF_JOINT_ANIMATION_EPSILON,
  URDF_JOINT_ANIMATION_FOLLOW_MS
} from "@hardcore/core/lib/urdf/jointAnimation.js";
import {
  FILE_STATUS_LEVELS,
  buildFileStatusItems,
  fileStatusHasWarningsOrErrors,
  mostIntenseFileStatusLevel
} from "../workbench/fileStatusItems.js";
import { useArtifact } from "../components/workbench/hooks/useArtifact.js";
import {
  rootAssemblyInspectionNodeId,
  buildAssemblyLeafToNodePickMap,
  descendantLeafPartIds,
  findAssemblyNode,
  findAssemblyNodes,
  flattenAssemblyNodes,
  flattenAssemblyLeafParts,
  leafPartIdsForAssemblySelection,
  resolveAssemblyPickedPartId
} from "@hardcore/core/lib/assembly/meshData.js";
import {
  assemblyNodeContainsNode,
  minimalAssemblyIsolationNodeIds,
  selectableViewerNodeIdsForExpandedTree
} from "../workbench/assemblyIsolation.js";
import {
  assignStepTreeTopologyReferencePartIds,
  buildStepTreeRoot,
  buildStepTreeRootWithTopology,
  STEP_MODEL_ROOT_ID,
  STEP_MODEL_RENDER_PART_ID
} from "@hardcore/core/lib/step/stepTree.js";
import {
  normalizeStepModuleParameterValues
} from "@hardcore/core/common/stepModule.js";
import {
  meshStateIsComplete,
  shouldRetainCompleteSameFileMesh,
  tolerantAnimationClip
} from "../components/workbench/hooks/packageProgressiveLoad.js";
import { meshLoadErrorForViewer, shouldStartMeshLoad } from "../components/workbench/hooks/meshLoadTarget.js";
import {
  kinematicsModuleDefinitionFromSidecar,
  loadKinematicsModuleDefinition,
  previewKinematicsModuleDefinition
} from "@hardcore/core/common/kinematicsModule.js";
import { validateSourceSidecar } from "@hardcore/core/common/sourceSidecar.js";
import { loadSourceAnimation, validateAnimationClips } from "@hardcore/core/common/renderModule.js";
import {
  normalizeParameterValue,
  normalizeParameterValues
} from "@hardcore/core/common/parameters.js";
import { ViewerElementContext, useViewerHost, usePromptDestination } from "../../../host/context.js";
import { createCadPromptContext, promptDeliveryMessage } from "./promptContext.js";
import { HostReferenceContext, referenceLabel, referencesFromCopyText, resolveSelectorSelection } from "./hostReference.js";
import { applySourceMaterialOverlayToMeshData, sourceAppearanceHasMaterials, sourceMaterialGeometry } from "../workbench/sourceMaterialSession.js";

const EMPTY_MATERIAL_OVERRIDES = Object.freeze({});
function sourceAnimationForEntry(entry) { return (entry?.editingPreview ? entry.previewAnimation : entry?.sourceSidecar?.animation) || null; }
function sourceAnimationKeyForEntry(entry) { return sourceAnimationForEntry(entry) ? `${fileKey(entry)}:${entry?.animationHash || entry?.documentHash || entry?.hash || "animation"}` : ""; }
function scopedWorkspacePerspective(snapshot, modelKey, entry) {
 const normalized = clonePerspectiveSnapshot(snapshot);
 if (!normalized) return null;
 const sceneScaleMode = renderCapabilities(entrySourceFormat(entry)).sceneScale;
 return annotatePerspectiveSnapshot(normalized, { modelKey, sceneScaleMode, coordinateSystem: sceneScaleMode === "urdf" ? "cad-z-up-robot-framing-v2" : "cad-z-up-v1" });
}

import {
  ARTIFACT_GENERATING_LABEL,
  DEFAULT_LARGE_FILE_STATE,
  DESKTOP_TAB_TOOLS_MAX_WIDTH,
  DESKTOP_TAB_TOOLS_MIN_WIDTH,
  EMPTY_LIST,
  capitalizeFirst,
  entryWithoutRenderAssets,
  normalizeLargeFileState,
  readViewerLayoutMode,
  readViewerViewportWidth,
  statusOnlyFileSheetTitle
} from "./fileViewState.js";
import { sceneBackdropEdgeColor } from "./chromeBackdrop.js";
import { useChromeBackdropColor } from "./cadTheme.js";
import {
  addReferenceLookupKeys,
  buildStepTreeCopyReferenceMap,
  buildStepTreeExpansionMenuState,
  childAssemblyNodeIdForPickedLeaf,
  collectStepTreeRevealExpansionIds,
  collectStepTreeSubtreeIds,
  collectStepTreeTopologyLoadableNodeIds,
  expandedVisibleStepTreeTopologyNodeIds,
  referencesForExpandedStepTree,
  referenceGroupForModelTreeHit,
  stepTreeTopologyOwnersForSelectors,
  copyPayloadWithSelectedIdFallback,
  copyReferenceForAssemblyPartSelection,
  copyReferenceForRawSelectorSelection,
  copyReferenceForStepTreeNodeSelection,
  copyableStepTreeNodeForWorkspace,
  findStepTreeTopologyNodeIdForReference
} from "./stepTreeSelection.js";

// The shared renderer consumes one prepared entry. FileViewer owns navigation,
// panel placement and persistence; the connection owns catalog subscriptions.
export default function CadFileView(props) {
  const clock = useMemo(() => createAnimationClock(), []);
  const glbClock = useMemo(() => createEmbeddedGlbAnimationClock(), []);
  return <AnimationClockProvider value={clock}><EmbeddedGlbAnimationClockProvider value={glbClock}><CadFileViewSurface {...props} /></EmbeddedGlbAnimationClockProvider></AnimationClockProvider>;
}


function CadFileViewSurface({
  client, entry, serverInfo, renderSession: cadRenderSession, preferences, onPreferenceChange, onOpenFile, className = "",
  panelSlot, colorScheme = "light", selectReference, captureRequest, acknowledgeCommand, documentResource, slots,
  openPanel = "", onPanelOpen, onChromeVisibilityChange, onActivityChange, onReload, state, onStateChange
}) {
  const host = useViewerHost();
  const viewerElement = useContext(ViewerElementContext);
  const destination = usePromptDestination();
  const promptAvailable = destination.available;
  const composerDestination = destination.kind === "composer";
  const animationClock = useAnimationClockStore();
  const { getAnimationClock, resetAnimationClock, setAnimationClock } = animationClock;
  const restoreStateRef = useRef(state || {});
  const stateRef = useRef(state || {});
  stateRef.current = state || {};
  const onStateChangeRef = useRef(onStateChange);
  onStateChangeRef.current = onStateChange;
  const emitState = useCallback((patch) => {
    const next = { ...stateRef.current, version: 1, ...patch };
    stateRef.current = next;
    onStateChangeRef.current?.(next);
  }, []);
  const hostLayoutMode = CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
  const hostSheetWidth = null;
  const hostPanelSlot = panelSlot;
  const drawsOwnPanelColumn = false;
  const tabToolsOpen = openPanel === CAD_PANEL.fileSheet;
  const filesPanelOpen = openPanel === "tree";
  const panelRef = useRef({ openPanel, onPanelOpen });
  panelRef.current = { openPanel, onPanelOpen };
  const setFilesPanelOpen = useCallback((value) => {
    const current = panelRef.current.openPanel === "tree";
    const next = typeof value === "function" ? value(current) : value;
    if (next !== current) panelRef.current.onPanelOpen?.(next ? "tree" : "");
  }, []);
  const setTabToolsOpen = useCallback((value) => {
    const current = panelRef.current.openPanel === CAD_PANEL.fileSheet;
    const next = typeof value === "function" ? value(current) : value;
    if (next !== current) panelRef.current.onPanelOpen?.(next ? CAD_PANEL.fileSheet : "");
  }, []);
  const resolvedColorSchemeMode = colorScheme === "dark" ? "dark" : "light";
  const uiPrefersDark = resolvedColorSchemeMode === "dark";
  const storeSnapshot = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const selectedKey = fileKey(entry);
  const liveEntry = storeSnapshot.entries.find((item) => fileKey(item) === selectedKey) || entry;
  const manifestRevision = storeSnapshot.revision;
  const explicitFileParam = cadFileParamForEntry(entry);
  const viewerServerInfo = serverInfo;
  const catalogHydrated = storeSnapshot.hydrated;
  const catalogError = storeSnapshot.error || "";
  const selectedCatalogPending = liveEntry?.catalogPending === true;
  const viewerReloading = false;
  const viewerServerBackend = String(viewerServerInfo?.backend || "").trim().toLowerCase();
  const [fileSheetOpenSectionIds, setFileSheetOpenSectionIds] = useState(null);
  const [dxfThicknessMm, setDxfThicknessMm] = useState(0);
  const [dxfBendSettings, setDxfBendSettings] = useState([]);
  const [dxfViewMode, setDxfViewMode] = useState("2d");
  const [referenceQuery, setReferenceQuery] = useState("");
  const [selectedReferenceIds, setSelectedReferenceIds] = useState([]);
  const [largeFileState, setLargeFileState] = useState(() => normalizeLargeFileState(DEFAULT_LARGE_FILE_STATE));
  // Capability demand is scoped to the artifact the user acted on. The
  // default Select tool alone does not imply topology work during file open.
  const [hoveredListReferenceId, setHoveredListReferenceId] = useState("");
  const [hoveredModelReferenceId, setHoveredModelReferenceId] = useState("");
  const [selectionFilter, setSelectionFilter] = useState("all");
  const [inspectionHighlight, setInspectionHighlight] = useState(null);
  const handleInspectionHighlight = useCallback((selection, label, context) => {
    setInspectionHighlight(selection ? { ...selection, label, context } : null);
  }, []);
  const [selectionFilterNotice, setSelectionFilterNotice] = useState("");
  const [selectedPartIds, setSelectedPartIds] = useState([]);
  const [selectedRenderPartIdByAssemblyPartId, setSelectedRenderPartIdByAssemblyPartId] = useState({});
  const [selectedWholeEntryCadRefToken, setSelectedWholeEntryCadRefToken] = useState("");
  const [expandedStepTreeNodeIds, setExpandedStepTreeNodeIds] = useState([]);
  const [activeTreeNodeScrollKey, setActiveTreeNodeScrollKey] = useState("");
  const [hiddenPartIds, setHiddenPartIds] = useState([]);
  const [isolatedAssemblyNodeIds, setIsolatedAssemblyNodeIds] = useState([]);
  const [viewerContextMenu, setViewerContextMenu] = useState(null);
  const [displaySettings, setDisplaySettings] = useState(() => normalizeDisplaySettings());
  const [renderSession, setRenderSession] = useState(createRenderSessionState);
  const renderEnabledRef = useRef(renderSession.enabled);
  renderEnabledRef.current = renderSession.enabled;
  const [viewerPerspective, setViewerPerspective] = useState(null);
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
  const [screenshotStatus, setScreenshotStatus] = useState("");
  const [persistenceStatus, setPersistenceStatus] = useState("");
  const [viewerLayoutMode, setViewerLayoutMode] = useState(readViewerLayoutMode);
  const [layoutViewportWidth, setLayoutViewportWidth] = useState(readViewerViewportWidth);
  const isWideLayout = hostLayoutMode === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP ||
    viewerLayoutMode === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
  const [viewerAlertOpen, setViewerAlertOpen] = useState(false);
  const [viewerRuntimeAlert, setViewerRuntimeAlert] = useState(null);
  const chromeBackdropColor = useChromeBackdropColor(uiPrefersDark);
  // Which way a drawing is being looked at. Session state on purpose: it is a way of looking
  // at the model open right now, not a preference worth outliving the tab.
  const [drawingViewMode, setDrawingViewMode] = useState("3d");
  // The zoom pill lives in the top-right toolbar row now; the viewer reports its live
  // percent up, and the pill drives the camera back through the imperative handle.
  const [viewerZoomPercent, setViewerZoomPercent] = useState(100);
  // Render-time drawing settings. Session state, like the view mode: they reshape the
  // viewport, never the cached package, so there is nothing to persist or invalidate.
  const [drawingThicknessMm, setDrawingThicknessMm] = useState(DXF_DEFAULT_THICKNESS_MM);
  // One entry per bend line, in axis order. An array because "the bend angle" stopped being
  // a thing the moment a drawing had two bends that want different angles.
  const [drawingBends, setDrawingBends] = useState([]);
  const [drawingBendStyle, setDrawingBendStyle] = useState(DXF_DEFAULT_BEND_STYLE);
  // Sheet-metal bend geometry for the curved style: inside radius (0 = auto) and K-factor.
  const [drawingBendRadiusMm, setDrawingBendRadiusMm] = useState(DXF_DEFAULT_BEND_RADIUS_MM);
  const [drawingKFactor, setDrawingKFactor] = useState(DXF_DEFAULT_KFACTOR);
  // Layer names the user has switched off; everything else renders.
  const [drawingHiddenLayers, setDrawingHiddenLayers] = useState([]);
  // The unit the DXF sheet's dimensional inputs display and accept.
  const [drawingUnits, setDrawingUnits] = useState(DXF_DEFAULT_UNITS);
  // Post-fold model orientation, in quarter-turns about each world axis.
  const [drawingOrientation, setDrawingOrientation] = useState(DXF_DEFAULT_ORIENTATION);
  // Sheet material preset: theme tint + density for the weight fact.
  const [drawingMaterial, setDrawingMaterial] = useState(DXF_DEFAULT_MATERIAL);
  // A drawing DOCUMENT's stroke scale (Fine/Normal/Bold), applied by the SVG route.
  const [drawingLineWeight, setDrawingLineWeight] = useState(DXF_DEFAULT_LINE_WEIGHT);
  // How a document's dimensions read (units, places, text size): re-rendered server-side.
  const [drawingDimensionDisplay, setDrawingDimensionDisplay] = useState(DXF_DEFAULT_DIMENSION_DISPLAY);
  // Sheet editing: staged edits (previewed by the server, sent to the agent as script
  // changes), the tool in hand ("" | "pick" | "move"), the points picked for a new
  // dimension, and the dimension selected in the list (highlighted in red).
  const [drawingEdits, setDrawingEdits] = useState([]);
  const [drawingEditTool, setDrawingEditTool] = useState("");
  const [drawingPickedPoints, setDrawingPickedPoints] = useState([]);
  const [drawingSelectedDimension, setDrawingSelectedDimension] = useState("");
  // The package's parsed contours, fetched once per entry and kept by URL. Curved bends
  // re-mesh from these; the URL carries the package version, so a rebuild refetches.
  const drawingGeometryCacheRef = useRef(new Map());
  const [drawingGeometry, setDrawingGeometry] = useState(null);
  const renderVisualKey = renderVisualSettingsKey(renderSession.payload);
  const resolvedVisualScene = useMemo(() => resolveSceneSettings({
    appearance: resolvedColorSchemeMode,
    prefersDark: uiPrefersDark,
    render: renderSession.enabled ? renderVisualPayload(renderSession.payload) : null,
    display: renderSession.enabled ? null : displaySettings
  }), [
    resolvedColorSchemeMode,
    displaySettings,
    renderSession.enabled,
    renderVisualKey,
    uiPrefersDark
  ]);
  const resolvedCamera = useMemo(() => resolveSceneSettings({
    render: renderSession.enabled ? {
      ...(renderSession.payload.camera ? { camera: renderSession.payload.camera } : {})
    } : null,
    camera: renderSession.enabled ? null : { projection: renderSession.cadProjection }
  }).camera, [
    renderSession.cadProjection,
    renderSession.enabled,
    renderSession.payload.camera
  ]);
  const resolvedQuality = useMemo(() => resolveRenderSessionQuality(renderSession), [
    renderSession.enabled,
    renderSession.payload.quality
  ]);
  const resolvedRenderConfiguration = useMemo(() => {
    const visualConfiguration = resolvedVisualScene.render.configuration || resolveSceneSettings({
      appearance: resolvedColorSchemeMode,
      prefersDark: uiPrefersDark,
      render: renderVisualPayload(renderSession.payload)
    }).render.configuration;
    // The visual resolve deliberately excludes camera and quality so an orbit
    // does not rebuild the scene. Put the session's own values back so the
    // recipe the rig and the settings UI read stays complete.
    return {
      ...visualConfiguration,
      // In Inspect the recipe describes the Render defaults the panel shows, so
      // it keeps its own default camera rather than borrowing the CAD one.
      ...(renderSession.enabled ? { camera: resolvedCamera } : {}),
      quality: renderSession.payload.quality || RENDER_QUALITY.FINAL
    };
  }, [
    resolvedColorSchemeMode,
    renderSession.enabled,
    renderSession.payload.quality,
    renderVisualKey,
    resolvedCamera,
    resolvedVisualScene.render.configuration,
    uiPrefersDark
  ]);
  const resolvedScene = useMemo(() => ({
    ...resolvedVisualScene,
    camera: resolvedCamera,
    quality: resolvedQuality,
    render: {
      ...resolvedVisualScene.render,
      configuration: resolvedRenderConfiguration,
      payload: renderSession.payload
    }
  }), [resolvedCamera, resolvedQuality, resolvedRenderConfiguration, resolvedVisualScene, renderSession.payload]);
  // Render has no theme: the viewer builds it from the recipe in
  // `render.configuration`, and the CAD scene settings stay behind in Inspect.
  const resolvedThemeSettings = resolvedScene.theme;
  const resolvedMaterialOverrides = renderSession.enabled
    ? EMPTY_MATERIAL_OVERRIDES
    : resolvedScene.materialOverrides;
  const sceneBackdrop = useMemo(
    () => renderSession.enabled
      ? resolvedScene.render.configuration.backdrop.color
      : sceneBackdropEdgeColor(resolvedThemeSettings.background, chromeBackdropColor),
    [chromeBackdropColor, renderSession.enabled, resolvedScene.render.configuration, resolvedThemeSettings]
  );
  const resolvedDisplayEdgeSettings = resolvedScene.display.edges;
  const updateDisplaySettings = useCallback((nextValue) => {
    const next = normalizeDisplaySettings(
      typeof nextValue === "function" ? nextValue(resolvedScene.display) : nextValue,
      { fallback: resolvedScene.display }
    );
    setDisplaySettings(next);
  }, [resolvedScene.display]);
  const [previewMode, setPreviewMode] = useState(false);
  useEffect(() => { onChromeVisibilityChange?.(!previewMode); }, [onChromeVisibilityChange, previewMode]);
  const tabToolsWidth = 365;
  const [drawingTool, setDrawingTool] = useState(DRAWING_TOOL.FREEHAND);
  const [tabToolMode, setTabToolMode] = useState(TAB_TOOL_MODE.REFERENCES);
  const [drawingStrokes, setDrawingStrokes] = useState([]);
  const [drawingUndoStack, setDrawingUndoStack] = useState([]);
  const [drawingRedoStack, setDrawingRedoStack] = useState([]);
  const [jointValuesByFileRef, setJointValuesByFileRef] = useState({});
  const [selectedUrdfGroupStateIdByFileRef, setSelectedUrdfGroupStateIdByFileRef] = useState({});
  const [stepModuleLoadState, setStepModuleLoadState] = useState({
    url: "",
    status: "idle",
    error: "",
    definition: null
  });
  const [stepModuleParameterValues, setStepModuleParameterValues] = useState({});
  // The ANIMATION system, loaded and held entirely apart from the kinematics
  // state above: kinematics and choreography are independent declarations in
  // the embedded source sidecar, and a model may ship either,
  // both, or neither.
  const [animationLoadState, setAnimationLoadState] = useState({
    url: "",
    status: "idle",
    error: "",
    clips: null
  });
  const [animationState, setAnimationState] = useState(buildDefaultAnimationState);
  const stepModuleParameterValuesRef = useRef(stepModuleParameterValues);
  const animationStateRef = useRef(animationState);
  const lastPersistenceFailureKeyRef = useRef("");
  const urdfTrajectoryPlaybackRef = useRef({
    frameId: 0,
    token: 0
  });
  const urdfJointAnimationRef = useRef({
    frameId: 0,
    token: 0,
    mode: "",
    fileRef: "",
    currentValues: null,
    targetValues: null,
    smoothingMs: URDF_JOINT_ANIMATION_FOLLOW_MS,
    lastTimestampMs: 0
  });
  const handlePersistenceWriteError = useCallback(({ key }) => {
    const failureKey = String(key || "browser-storage");
    if (lastPersistenceFailureKeyRef.current === failureKey) {
      return;
    }
    lastPersistenceFailureKeyRef.current = failureKey;
    setPersistenceStatus("Browser storage could not save the CAD Viewer session.");
  }, []);

  const entryMap = useMemo(() => new Map([[selectedKey, liveEntry]]), [selectedKey, liveEntry]);
  const fileSessionNamespace = selectedKey;

  const {
    meshState,
    setMeshState,
    lodPackage,
    applyComponentLodBatch,
    prepareComponentLodPayload,
    onMeshSourceAdoption,
    componentLodNeedsSelectors,
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadTargetHash,
    meshLoadProgress,
    status,
    setStatus,
    error,
    setError,
    urdfState,
    setUrdfState,
    urdfStatus,
    setUrdfStatus,
    urdfError,
    setUrdfError,
    urdfLoadProgress,
    referenceState,
    setReferenceState,
    referenceStatus,
    setReferenceStatus,
    referenceError,
    setReferenceError,
    displayEdgeState,
    setDisplayEdgeState,
    displayEdgeStatus,
    setDisplayEdgeStatus,
    displayEdgeError,
    setDisplayEdgeError,
    getCachedMeshState,
    getCachedReferenceState,
    getCachedUrdfState,
    cancelMeshLoad,
    cancelUrdfLoad,
    cancelReferenceLoad,
    cancelDisplayEdgeLoad,
    loadMeshForEntry,
    loadUrdfForEntry,
    loadReferencesForEntry,
    loadDisplayEdgesForEntry
  } = useCadAssets({
    initialEntry: liveEntry,
    client,
    tessellationCache: cadRenderSession.tessellationCache,
    entryHasMesh,
    entryHasReferences,
    entryHasDisplayEdges,
    buildNormalizedReferenceState,
  });

  const catalogSelectedEntry = liveEntry;
  const fileParamSelectionPending = false;
  const missingFileRef = "";
  const catalogSelectedEntrySourceFormat = entrySourceFormat(catalogSelectedEntry);
  // File state uses the host's absolute identity; server requests use the
  // catalog's path relative to this client's served root.
  const editingFile = catalogSelectedEntry ? cadFileParamForEntry(catalogSelectedEntry) : explicitFileParam;
  const editingAvailable = /\.st(?:ep|p)$/i.test(editingFile || "");
  const editingPreview = useEditingPreview(editingFile, { client,
    enabled: editingAvailable && !selectedCatalogPending,
    catalogEntry: catalogSelectedEntry,
  });
  // Unified render-artifact status for the selected entry: ready (render) | generating (loading) |
  // error (fatal). A missing/stale cache is not an issue — it just triggers a (re)build. Replaces
  // the per-entry step-source-status fetch, the mesh-stripping merge, and the build effect.
  // Every artifact-managed kind: STEP models and DXF drawings (generated `.dxf.py` AND
  // imported `.dxf` alike). An imported `.dxf` used to be excluded because it
  // "renders directly from disk" -- true only while the client still parsed and extruded DXF
  // entities in the browser. It renders from the package's baked preview.glb now, so it needs
  // the build for exactly the reason a generated one does.
  const selectedArtifact = useArtifact(
    catalogSelectedEntry ? cadFileParamForEntry(catalogSelectedEntry) : "",
    {
      enabled: !selectedCatalogPending && isArtifactManagedFormat(catalogSelectedEntrySourceFormat),
      freshnessKey: `${catalogSelectedEntry?.hash || ""}:${manifestRevision}`,
      client,
    }
  );
  const editingHasView = Boolean(editingPreview.entry || entryHasMesh(catalogSelectedEntry));
  const selectedArtifactGenerating = selectedArtifact.status === "compiling" && !editingHasView;
  // The in-flight build's own report of where it is (null until it reports, and for
  // every loading state that is not an artifact build). Only meaningful while
  // generating — a stale frame must not outlive the build that produced it.
  const selectedArtifactProgress = selectedArtifactGenerating ? selectedArtifact.progress : null;
  const activeStepArtifactGenerationFiles = useMemo(
    () => (selectedArtifactGenerating && catalogSelectedEntry ? [fileKey(catalogSelectedEntry)] : []),
    [selectedArtifactGenerating, catalogSelectedEntry]
  );
  // While the artifact is missing/stale/building/broken, hide the (possibly stale) render assets so
  // the viewer shows a loading or error state and renders only the fresh artifact once ready.
  // The shortest path suffix that names each catalog entry uniquely -- almost always just the
  // filename. Copied refs carry it so they still say which file they belong to when pasted
  // into a prompt spanning several files, without the length of a full relative path.
  const fileRefPrefixByPath = useMemo(
    () => shortestUniquePathSuffixes(storeSnapshot.entries.map((entry) => cadFileParamForEntry(entry))),
    [storeSnapshot.entries]
  );
  const selectedEntry = useMemo(
    () => {
      const base = editingPreview.entry || (!catalogSelectedEntry || selectedArtifact.status === "compiled" ||
        entryHasMesh(catalogSelectedEntry)
        ? catalogSelectedEntry
        : entryWithoutRenderAssets(catalogSelectedEntry));
      if (!base) {
        return base;
      }
      const fileRefPrefix = fileRefPrefixByPath.get(cadFileParamForEntry(base)) || "";
      return fileRefPrefix ? { ...base, fileRefPrefix } : base;
    },
    [catalogSelectedEntry, selectedArtifact.status, fileRefPrefixByPath, editingPreview.entry]
  );
  const previousPreviewTree = useRef(null);
  useEffect(() => {
    const previous = previousPreviewTree.current;
    const next = { file: selectedEntry?.file, hash: selectedEntry?.hash, preview: selectedEntry?.editingPreview };
    if (previewGeometryChanged(previous, next)) {
      setSelectedReferenceIds([]);
      setSelectedPartIds([]);
      setSelectedRenderPartIdByAssemblyPartId({});
      setSelectedWholeEntryCadRefToken("");
    }
    previousPreviewTree.current = next;
  }, [selectedEntry?.file, selectedEntry?.hash, selectedEntry?.editingPreview]);
  // Cache states never become user-facing "issues"; only a fatal build/source failure does.
  const selectedStepSourceStatus = selectedArtifact.status === "failed" && !editingHasView
    ? {
        artifact: {
          ok: false,
          error: "render_artifact_unavailable",
          message: selectedArtifact.error || "Render artifact is unavailable.",
          stepPath: catalogSelectedEntry ? fileKey(catalogSelectedEntry) : "",
        },
      }
    : null;
  const selectedEntrySourceFormat = entrySourceFormat(selectedEntry);
  // Every entry now renders from its own source format: a DXF's geometry is parsed and
  // meshed client-side, a robot is assembled from its link meshes, and nothing is baked
  // into a package under a different format.
  const selectedEntryRenderAssetFormat = selectedEntrySourceFormat;
  const selectedFileSheetKind = fileSheetKindForEntry(selectedEntry);
  // Hide the file-sheet toggle when the kind has no sections.
  const selectedFileSheetHasSections = useMemo(
    () => renderedFileSheetSectionIds(selectedFileSheetKind).length > 0,
    [selectedFileSheetKind]
  );
  // The URL's path IS the directory, so there is nothing to select and no state to
  // reconcile — the Viewer always has exactly one directory, the one it was opened at.
  const stepArtifactGenerationAvailable = viewerServerInfo
    ? viewerServerInfo.stepArtifactGenerationAvailable !== false
    : true;
  const fileAccessBackend = viewerServerInfo ? (viewerServerBackend || "local-fs") : "";
  const filePathCopyAvailable = fileAccessBackend === "local-fs" && Boolean(
    viewerServerInfo?.rootPath
  );
  // `isStepView` used to stand in for all four of these at once, which is why adding a
  // format meant auditing every one of its ~15 uses to work out which sense was meant.
  // They are separate capabilities; the table is the source of truth.
  const selectedEntryContentKind = viewportContentKind(selectedEntrySourceFormat);
  const supportsParts = hasCapability(selectedEntrySourceFormat, "parts");
  const supportsTopology = hasCapability(selectedEntrySourceFormat, "topology");
  const supportsMeasure = hasCapability(selectedEntrySourceFormat, "measure");
  const supportsDisplayModes = hasCapability(selectedEntrySourceFormat, "displayModes");
  const supportsSidecarParams =
    parameterSourceKind(selectedEntrySourceFormat) === PARAMETER_SOURCE.SIDECAR;
  const isAssemblyView = selectedEntry?.kind === "assembly";
  const isUrdfView = selectedEntryContentKind === VIEWPORT_CONTENT.ROBOT;
  const robotBoundsAnimationActive = Boolean(
    isUrdfView &&
    (
      urdfJointAnimationRef.current?.frameId ||
      urdfTrajectoryPlaybackRef.current?.frameId
    )
  );
  const selectedStepModuleUrl = selectedEntry?.editingPreview && selectedEntry.previewKinematics
    ? `preview:${selectedEntry.hash}` : supportsSidecarParams ? entryPoseUrl(selectedEntry) : "";
  const selectedStepModuleCadPath = selectedStepModuleUrl ? cadPathForEntry(selectedEntry) : "";
  const selectedStepModuleDefinition = stepModuleLoadState.url === selectedStepModuleUrl
    ? stepModuleLoadState.definition
    : null;
  const selectedSourceAnimation = supportsSidecarParams
    ? sourceAnimationForEntry(selectedEntry)
    : null;
  const selectedAnimationSourceKey = selectedSourceAnimation ? sourceAnimationKeyForEntry(selectedEntry) : "";
  const selectedAnimationClips = animationLoadState.url === selectedAnimationSourceKey
    ? animationLoadState.clips
    : null;
  const selectedAnimationStatus = selectedAnimationSourceKey
    ? (animationLoadState.url === selectedAnimationSourceKey ? animationLoadState.status : "loading")
    : "idle";
  const selectedAnimationLoadError = animationLoadState.url === selectedAnimationSourceKey
    ? animationLoadState.error
    : "";
  const selectedStepModuleStatus = selectedStepModuleUrl
    ? (stepModuleLoadState.url === selectedStepModuleUrl ? stepModuleLoadState.status : "loading")
    : "idle";
  const selectedStepModuleError = stepModuleLoadState.url === selectedStepModuleUrl
    ? stepModuleLoadState.error
    : "";
  const selectedStepModuleLoading = Boolean(selectedStepModuleUrl && selectedStepModuleStatus === "loading");
  const selectedEntryHasMesh = entryHasMesh(selectedEntry);
  const selectedEntryHasUrdf = entryHasUrdf(selectedEntry);
  const selectedEntryHasReferences = entryHasReferences(selectedEntry);
  const selectedEntryHasDisplayEdges = entryHasDisplayEdges(selectedEntry);
  const selectedEntryHasDxf = entryHasDxf(selectedEntry);
  // A dimensioned drawing renders its own 2D geometry: there is no mesh to wait
  // for. Decided from the PARSED data (dimension/leader/paper-space evidence) —
  // the client twin of cadgen's drawing_checks predicate.
  const selectedEntryIsDrawingDocument =
    assetKindForRenderFormat(selectedEntrySourceFormat) === ASSET_KIND.DRAWING
    && dxfDataIsDocument(drawingGeometry);
  // The selected entry's render artifact is (re)building -> show the loading state. Replaces the
  // old !entryHasMesh + buildable-code derivation.
  const selectedStepArtifactRenderPending = selectedArtifactGenerating;
  const selectedMeshHash = entryMeshAssetSignature(selectedEntry);
  const selectedMeshMatches =
    !!meshState &&
    !!selectedEntry &&
    meshState.file === fileKey(selectedEntry) &&
    meshState.meshHash === selectedMeshHash;
  // useCadAssets retains the complete scene while a same-file STEP revision
  // stages. Keep that predecessor renderable across the short entry-hash gap;
  // reference matching remains hash-strict below, so its stale topology cannot
  // be picked while the replacement geometry/selectors are loading.
  const retainingPreviousStepMesh =
    selectedEntryHasMesh &&
    !!selectedMeshHash &&
    selectedEntrySourceFormat === RENDER_FORMAT.STEP &&
    !selectedStepModuleUrl &&
    !selectedAnimationSourceKey &&
    shouldRetainCompleteSameFileMesh(meshState, selectedEntry, selectedMeshHash);
  const retainedPreviousStepMeshError = retainingPreviousStepMesh &&
    meshState?.assemblyBackgroundErrorMeshHash === selectedMeshHash
    ? String(meshState?.assemblyBackgroundError || "").trim()
    : "";
  const stepInteractionBlocked = stepUpdateInProgress || retainingPreviousStepMesh;
  const selectedAssemblyStructureReady =
    selectedEntry?.kind === "assembly" &&
    selectedMeshMatches &&
    !!meshState?.assemblyStructureReady;
  const selectedAssemblyInteractionReady =
    selectedEntry?.kind === "assembly" &&
    selectedMeshMatches &&
    !!meshState?.assemblyInteractionReady;
  const selectedAssemblyHydrationFailed =
    selectedEntry?.kind === "assembly" &&
    !!meshState?.assemblyBackgroundError &&
    (selectedMeshMatches || !!retainedPreviousStepMeshError);
  const selectedUrdfMatches =
    !!urdfState &&
    !!selectedEntry &&
    urdfState.file === fileKey(selectedEntry) &&
    urdfState.urdfHash === entryUrdfAssetHash(selectedEntry);
  const selectedUrdfData = selectedUrdfMatches ? urdfState.urdfData : null;
  const selectedUrdfMeshes = selectedUrdfMatches ? urdfState.meshesByUrl : null;
  const selectedUrdfFileRef = selectedEntryContentKind === VIEWPORT_CONTENT.ROBOT
    ? fileKey(selectedEntry)
    : "";
  const defaultSelectedUrdfJointValues = useMemo(
    () => ({
      ...buildDefaultUrdfJointValues(selectedUrdfData),
      ...srdfHomeGroupStateJointValuesToDisplay(selectedUrdfData)
    }),
    [selectedUrdfData]
  );
  const storedSelectedUrdfJointValues = useMemo(() => {
    if (!selectedUrdfFileRef) {
      return {};
    }
    const storedValues = jointValuesByFileRef?.[selectedUrdfFileRef];
    return storedValues && typeof storedValues === "object" ? storedValues : {};
  }, [jointValuesByFileRef, selectedUrdfFileRef]);
  const selectedUrdfJointValues = useMemo(
    () => ({ ...defaultSelectedUrdfJointValues, ...storedSelectedUrdfJointValues }),
    [defaultSelectedUrdfJointValues, storedSelectedUrdfJointValues]
  );
  const selectedUrdfGroupStates = useMemo(() => {
    const groupStates = Array.isArray(selectedUrdfData?.srdf?.groupStates)
      ? selectedUrdfData.srdf.groupStates
      : Array.isArray(selectedUrdfData?.motion?.groupStates)
        ? selectedUrdfData.motion.groupStates
        : [];
    const names = groupStates.map((state) => String(state?.name || "").trim()).filter(Boolean);
    const nameCounts = names.reduce((counts, name) => counts.set(name, (counts.get(name) || 0) + 1), new Map());
    return groupStates.map((state) => {
      const name = String(state?.name || "").trim();
      const group = String(state?.group || "").trim();
      if (!name || !group) {
        return null;
      }
      const jointValuesByName = srdfGroupStateJointValuesToDisplay(
        selectedUrdfData,
        state?.jointValuesByName || state?.jointValuesByNameRad
      );
      return {
        ...state,
        id: `${group}/${name}`,
        label: nameCounts.get(name) > 1 ? `${name} (${group})` : name,
        jointValuesByName
      };
    }).filter(Boolean);
  }, [selectedUrdfData]);
  const selectedUrdfContinuousJointNames = useMemo(
    () => new Set(
      (Array.isArray(selectedUrdfData?.joints) ? selectedUrdfData.joints : [])
        .filter((joint) => String(joint?.type || "").trim() === "continuous")
        .map((joint) => String(joint?.name || "").trim())
        .filter(Boolean)
    ),
    [selectedUrdfData]
  );
  const matchedSelectedUrdfGroupStateId = useMemo(
    () => (
      findBestMatchingJointValueState(
        selectedUrdfGroupStates,
        selectedUrdfJointValues,
        defaultSelectedUrdfJointValues
      )?.id || ""
    ),
    [defaultSelectedUrdfJointValues, selectedUrdfJointValues, selectedUrdfGroupStates]
  );
  const trackedSelectedUrdfGroupStateId = selectedUrdfFileRef
    ? String(selectedUrdfGroupStateIdByFileRef?.[selectedUrdfFileRef] || "").trim()
    : "";
  const activeSelectedUrdfGroupStateId = useMemo(() => {
    if (trackedSelectedUrdfGroupStateId && selectedUrdfGroupStates.some((state) => String(state?.id || "").trim() === trackedSelectedUrdfGroupStateId)) {
      return trackedSelectedUrdfGroupStateId;
    }
    return matchedSelectedUrdfGroupStateId;
  }, [matchedSelectedUrdfGroupStateId, selectedUrdfGroupStates, trackedSelectedUrdfGroupStateId]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    if (!selectedStepModuleUrl) {
      setStepModuleLoadState({
        url: "",
        status: "idle",
        error: "",
        definition: null
      });
      setStepModuleParameterValues({});
      return () => {
        cancelled = true;
        controller.abort();
      };
    }

    setStepModuleLoadState({
      url: selectedStepModuleUrl,
      status: "loading",
      error: "",
      definition: null
    });
    setStepModuleParameterValues({});

    const modulePromise = selectedEntry?.editingPreview
      ? Promise.resolve().then(() => previewKinematicsModuleDefinition(selectedEntry.previewKinematics, {
          cadPath: selectedStepModuleCadPath,
        }))
      : selectedEntry?.sourceSidecar
        ? Promise.resolve().then(() => kinematicsModuleDefinitionFromSidecar(
            validateSourceSidecar(selectedEntry.sourceSidecar, {
              url: selectedStepModuleUrl || selectedEntry.file,
              documentHash: selectedEntry.documentHash,
            }),
            { cadPath: selectedStepModuleCadPath, url: selectedStepModuleUrl }
          ))
      : loadKinematicsModuleDefinition(selectedStepModuleUrl, {
          signal: controller.signal, resources: client.resources, cadPath: selectedStepModuleCadPath, documentHash: selectedEntry?.documentHash,
        });
    modulePromise.then((definition) => {
      if (cancelled) {
        return;
      }
      const restoredSessionState = normalizeFileSessionState(restoreStateRef.current.fileSession, { fileKey: fileKey(selectedEntry), entry: selectedEntry
       });
      // A sidecar with no kinematics section resolves to a NULL definition —
      // an animation-only model has a sidecar and lands here — so the ready
      // state is committed from one place that expects that (see
      // workbench/stepModuleLoad); the Kinematics tab is then absent, not empty.
      const resolved = resolveStepModuleLoad({
        url: selectedStepModuleUrl,
        definition,
        restored: restoredSessionState?.slices?.stepModule || null
      });
      setStepModuleLoadState(resolved.loadState);
      stepModuleParameterValuesRef.current = resolved.parameterValues;
      setStepModuleParameterValues(resolved.parameterValues);
      setAppliedStepPoseName("");
    }).catch((error) => {
      if (cancelled) {
        return;
      }
      setStepModuleLoadState({
        url: selectedStepModuleUrl,
        status: "error",
        error: error instanceof Error ? error.message : String(error),
        definition: null
      });
      setStepModuleParameterValues({});
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [fileSessionNamespace, selectedEntry, selectedStepModuleCadPath, selectedStepModuleUrl]);

  // The animation half compiles the exact source embedded in the selected
  // sidecar. A document with no animation resolves to no clips and no
  // Animation tab, and a broken one reports its own error without disturbing
  // the Pose tab.
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const resetAnimation = () => {
      const nextState = buildDefaultAnimationState();
      animationStateRef.current = nextState;
      setAnimationState(nextState);
      resetAnimationClock();
    };

    if (!selectedAnimationSourceKey || !selectedSourceAnimation) {
      setAnimationLoadState({ url: "", status: "idle", error: "", clips: null });
      resetAnimation();
      return () => {
        cancelled = true;
        controller.abort();
      };
    }

    setAnimationLoadState({
      url: selectedAnimationSourceKey,
      status: "loading",
      error: "",
      clips: null
    });
    resetAnimation();

    loadSourceAnimation({ animation: selectedSourceAnimation }, {
      signal: controller.signal,
      name: `${fileKey(selectedEntry) || "STEP"} animation`
    })
      .then((animationModule) => {
        if (cancelled) {
          return;
        }
        const clips = animationModule?.clips || {};
        setAnimationLoadState({
          url: selectedAnimationSourceKey,
          status: "ready",
          error: "",
          clips
        });
        const restoredSessionState = normalizeFileSessionState(restoreStateRef.current.fileSession, { fileKey: fileKey(selectedEntry), entry: selectedEntry
         });
        const nextState = restoreAnimationState(restoredSessionState?.slices?.animation, clips);
        animationStateRef.current = nextState;
        setAnimationState(nextState);
        setAnimationClock(nextState.elapsedSec);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setAnimationLoadState({
          url: selectedAnimationSourceKey,
          status: "error",
          error: error instanceof Error ? error.message : String(error),
          clips: null
        });
        resetAnimation();
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [fileSessionNamespace, selectedAnimationSourceKey, selectedEntry, selectedSourceAnimation]);

  const selectedUrdfLinkMeshGeometryResult = useMemo(() => {
    if (!selectedUrdfData || !selectedUrdfMeshes) {
      return {
        meshData: null,
        error: ""
      };
    }
    try {
      return {
        meshData: buildUrdfMeshGeometry(selectedUrdfData, selectedUrdfMeshes, { lightweight: true }),
        error: ""
      };
    } catch (error) {
      return {
        meshData: null,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }, [selectedUrdfData, selectedUrdfMeshes]);
  // Splitting a visual into its named objects is an INSPECT affordance. Render owns an
  // isolated photographic scene, and the parts it is handed are the Materials targets —
  // so a robot in Render keeps the per-visual geometry it has always had, and the split
  // never reaches the Materials picker. Keeping the split in its own memo also means a
  // mode switch never rebuilds the link geometry underneath it.
  const selectedUrdfMeshGeometryResult = useMemo(() => {
    if (renderSession.enabled || !selectedUrdfLinkMeshGeometryResult.meshData) {
      return selectedUrdfLinkMeshGeometryResult;
    }
    try {
      return {
        meshData: buildRobotComponentGeometry(selectedUrdfLinkMeshGeometryResult.meshData),
        error: ""
      };
    } catch (error) {
      // The split is an enhancement: a failure in it costs the components, never the robot.
      console.warn("Failed to split robot mesh objects into components", error);
      return selectedUrdfLinkMeshGeometryResult;
    }
  }, [renderSession.enabled, selectedUrdfLinkMeshGeometryResult]);
  const selectedUrdfComponents = useMemo(
    () => robotComponents(selectedUrdfMeshGeometryResult.meshData),
    [selectedUrdfMeshGeometryResult.meshData]
  );
  const robotSelection = useRobotComponentSelection(
    selectedUrdfComponents, selectedUrdfMeshGeometryResult.meshData, selectedUrdfFileRef
  );
  // Inspect only, and stated twice on purpose: the geometry above is unsplit in Render,
  // and this keeps the viewport's picking, hover and activate wiring on main's path even
  // if that ever changes.
  const robotComponentsActive = !renderSession.enabled &&
    selectedEntryContentKind === VIEWPORT_CONTENT.ROBOT &&
    selectedUrdfComponents.length > 0;
  const movableUrdfJoints = useMemo(
    () => (
      Array.isArray(selectedUrdfData?.joints)
        ? selectedUrdfData.joints.filter((joint) => String(joint?.type || "") !== "fixed" && !joint?.mimic)
        : []
    ),
    [selectedUrdfData]
  );
  const selectedUrdfPreview = useMemo(() => {
    if (!selectedUrdfData || !selectedUrdfMeshGeometryResult.meshData) {
      return {
        meshData: null,
        error: selectedUrdfMeshGeometryResult.error,
        linkWorldTransforms: new Map()
      };
    }
    try {
      const posedPreview = applyUrdfPoseToMeshData(
        selectedUrdfData,
        selectedUrdfMeshGeometryResult.meshData,
        renderSession.enabled ? defaultSelectedUrdfJointValues : selectedUrdfJointValues
      );
      return {
        ...posedPreview,
        error: ""
      };
    } catch (error) {
      return {
        meshData: null,
        error: error instanceof Error ? error.message : String(error),
        linkWorldTransforms: new Map()
      };
    }
  }, [
    defaultSelectedUrdfJointValues,
    renderSession.enabled,
    selectedUrdfData,
    selectedUrdfJointValues,
    selectedUrdfMeshGeometryResult
  ]);
  const selectedMeshData = selectedEntryContentKind === VIEWPORT_CONTENT.ROBOT
    ? selectedUrdfPreview.meshData
    : (selectedMeshMatches || retainingPreviousStepMesh)
      ? meshState.meshData
      : null;
  const selectedSourceAppearance = selectedEntry?.editingPreview
    ? selectedEntry.previewAppearance || null
    : selectedEntry?.sourceSidecar?.appearance || selectedMeshData?.appearance || null;
  const materialSession = useSourceMaterialSession(selectedEntry, selectedMeshData, {
    appearance: selectedSourceAppearance,
    fileSheetKind: selectedFileSheetKind,
    renderEnabled: renderSession.enabled
  });
  const selectedDisplayMeshData = useMemo(() => {
    return registerLodDisplaySource(
      applySourceMaterialOverlayToMeshData(selectedMeshData, materialSession.overlay, selectedSourceAppearance),
      selectedMeshData
    );
  }, [materialSession.overlay, selectedMeshData, selectedSourceAppearance]);
  const handleDisplayMeshAdoption = useCallback((source, ok, detail) =>
    onMeshSourceAdoption(sourceMaterialGeometry(source), ok, detail), [onMeshSourceAdoption]);
  const selectedGlbDocument = selectedMeshMatches ? meshState?.glbDocument || null : null;
  const embeddedGlbAnimationRuntime = useEmbeddedGlbAnimation(selectedGlbDocument);
  // Animated direct GLBs render their live hierarchy. Flattened triangle picks
  // describe only the rest pose, so exposing them would create stale rulers.
  const effectiveSupportsMeasure = supportsMeasure && !embeddedGlbAnimationRuntime;
  const selectedAnimationClipList = useMemo(
    () => animationClipList(selectedAnimationClips),
    [selectedAnimationClips]
  );
  const selectedActiveAnimationClip = useMemo(
    () => findAnimationClip(selectedAnimationClips, animationState.activeClipId),
    [selectedAnimationClips, animationState.activeClipId]
  );
  // Progressive publish (design/viewer-memory.md §6): a STEP package paints
  // while it loads, and the partial states carry assemblyInteractionReady=false.
  // Embedded animation attaches on the FIRST publish and stays live: the viewer
  // re-runs its setup on every meshData change (the same path a LOD swap
  // takes), so occurrences bind as they arrive. Pose and animation controls
  // act on whatever is present; only clip validation waits for the complete
  // model, and a partial model's clip tolerates labels not yet loaded.
  const selectedMeshPartial = selectedMeshMatches && !meshStateIsComplete(meshState);
  const selectedStepModuleTopologyRequired = stepModuleRequiresTopology(selectedStepModuleDefinition);
  const selectedStepModuleTopologyRequested =
    !renderSession.enabled && selectedStepModuleTopologyRequired;
  // What the viewport needs to draw one animated frame: the compiled clip and a
  // time. The render pane swaps in the live clock while playing; everything else
  // about playback stays out of the render path.
  //
  // The Animation section's gate expresses itself HERE and nowhere else, mirroring
  // the pose gate above: switched off this memo is null, and null is already how
  // the viewport draws the rest scene — pose only, evaluator never run. So there
  // is no "disabled" render path, only the absence of a frame.
  const selectedPlayableAnimationClip = useMemo(
    () => (selectedMeshPartial ? tolerantAnimationClip(selectedActiveAnimationClip) : selectedActiveAnimationClip),
    [selectedActiveAnimationClip, selectedMeshPartial]
  );
  const selectedAnimationRuntime = useMemo(() => animationRenderFrame({
    enabled: animationState.enabled !== false,
    clip: selectedPlayableAnimationClip,
    elapsedSec: animationState.elapsedSec,
    playing: animationState.playing
  }), [
    animationState.elapsedSec,
    animationState.enabled,
    animationState.playing,
    selectedPlayableAnimationClip
  ]);
  const handleStepModuleTransformDetectedChange = useCallback(() => {}, []);
  const stepModuleTreeSelectionDisabled = false;
  const stepModuleTreeSelectionDisabledReason = "";

  useEffect(() => {
    stepModuleParameterValuesRef.current = stepModuleParameterValues;
  }, [stepModuleParameterValues]);

  useEffect(() => {
    animationStateRef.current = animationState;
  }, [animationState]);

  // The pose the person PICKED, which the dropdown shows until they move a DOF. Without
  // it the name is re-derived from the values every frame, so a pose read as "None"
  // for the whole of its own transition and only became itself once it arrived.
  const [appliedStepPoseName, setAppliedStepPoseName] = useState("");

  const handleStepModuleParameterChange = useCallback((parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = selectedStepModuleDefinition?.parameterMap?.[id];
    if (!parameter) {
      return;
    }
    // Moving a DOF by hand leaves the named pose behind, so the dropdown stops claiming
    // it and goes back to reading the values (the robot's group state does the same).
    setAppliedStepPoseName("");
    setStepModuleParameterValues((current) => ({
      ...current,
      [id]: normalizeParameterValue(parameter, value)
    }));
  }, [selectedStepModuleDefinition]);

  const applyStepModuleParameterValues = useCallback((values) => {
    setStepModuleParameterValues((current) => ({
      ...current,
      ...values
    }));
  }, []);

  const handleResetStepModuleParameters = useCallback(() => {
    if (!selectedStepModuleDefinition) {
      return;
    }
    const nextParameterValues = normalizeStepModuleParameterValues(
      selectedStepModuleDefinition,
      selectedStepModuleDefinition.defaultParameterValues
    );
    stepModuleParameterValuesRef.current = nextParameterValues;
    setStepModuleParameterValues(nextParameterValues);
  }, [selectedStepModuleDefinition]);

  // A named pose is a full configuration, not a patch: every DOF the preset
  // does not mention returns to 0 (the artifact as written), so two presets in
  // a row can never leave a joint behind from the first.
  // One preference for every sheet that has poses; see workbench/poseTransition.js.
  const updatePoseTransition = useCallback((poseTransition) => onPreferenceChange({ poseTransition }), [onPreferenceChange]);
  const poseTransition = usePoseTransition(preferences.poseTransition, updatePoseTransition);
  const stepPoseAnimation = usePoseValueAnimation();
  // Read at call time, not closed over: the robot tween is a useCallback with the joint
  // state in its dependencies, and changing the speed must not rebuild it mid-drag.
  const poseTransitionDurationMsRef = useRef(poseTransition.durationMs);
  poseTransitionDurationMsRef.current = poseTransition.durationMs;

  const handleApplyPose = useCallback((poseName) => {
    if (!selectedStepModuleDefinition) {
      return;
    }
    const nextParameterValues = normalizeStepModuleParameterValues(
      selectedStepModuleDefinition,
      poseValuesForPreset(selectedStepModuleDefinition, poseName)
    );
    setAppliedStepPoseName(String(poseName || ""));
    // A pose is a place the mechanism GOES, so it travels there: the same tween the
    // robot sheet has always used, at the duration this viewer is set to. With
    // animation off the duration is 0 and the values are written in this frame.
    stepPoseAnimation.run({
      start: stepModuleParameterValuesRef.current || {},
      target: nextParameterValues,
      durationMs: poseTransition.durationMs,
      onFrame: (frameValues) => {
        stepModuleParameterValuesRef.current = frameValues;
        setStepModuleParameterValues(frameValues);
      }
    });
  }, [poseTransition.durationMs, selectedStepModuleDefinition, stepPoseAnimation]);

  // --- Animation transport -------------------------------------------------
  //
  // Playback is a clock over a pure function of t: every handler here does no
  // more than move that clock or say whether it is running. Nothing below reads
  // a DOF, a preset or the kinematics definition.

  const handleAnimationClipSelect = useCallback((clipId) => {
    const clip = findAnimationClip(selectedAnimationClips, clipId);
    if (!clip) {
      // The picker only ever offers clips this model ships, so an id that does
      // not resolve is a stale event, not a request to idle the transport —
      // idling is the section's gate.
      return;
    }
    const nextState = {
      ...animationStateRef.current,
      activeClipId: clip.id,
      playing: false,
      elapsedSec: 0,
      // The loop preference follows the newly-selected clip's own default.
      loopEnabled: clip.loop !== false
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    resetAnimationClock();
  }, [selectedAnimationClips]);

  const handleAnimationPlayToggle = useCallback(() => {
    const currentState = animationStateRef.current;
    // A GUARD, not a UI path: once the clips compile the selection is always one
    // of them (the default picks clip 0, a restore falls back to clip 0, and the
    // picker only offers ids that resolve), and before they compile there are no
    // clips to find at all, so both lookups miss and this returns below. It
    // stays because Play doing nothing would be the silent failure — if a
    // selection ever went empty with clips in hand, Play should start the first
    // one rather than shrug.
    const clip = findAnimationClip(selectedAnimationClips, currentState.activeClipId)
      || findAnimationClip(selectedAnimationClips, firstAnimationClipId(selectedAnimationClips));
    if (!clip) {
      return;
    }
    const duration = animationClipDuration(clip);
    if (currentState.playing) {
      const nextState = {
        ...currentState,
        activeClipId: clip.id,
        elapsedSec: clampAnimationElapsed(getAnimationClock(), duration),
        playing: false
      };
      animationStateRef.current = nextState;
      setAnimationState(nextState);
      return;
    }
    // Resuming from the end of a non-looping clip restarts it; there is nowhere
    // else for the clock to go.
    const elapsedSec = currentState.elapsedSec >= duration
      ? 0
      : clampAnimationElapsed(currentState.elapsedSec, duration);
    setAnimationClock(elapsedSec);
    // Play means "run this clip", so it opens the gate rather than doing
    // nothing visible: the toolbar's Play button lives outside the tab and has
    // no way to say that animation is switched off.
    const nextState = {
      ...currentState,
      activeClipId: clip.id,
      enabled: true,
      elapsedSec,
      playing: true
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
  }, [selectedAnimationClips]);

  // Turning animation off idles the transport without rewinding it: the clock
  // settles where it stands (while playing the authoritative time is the clock
  // store's, not React state's) and playback stops. Turning it back on resumes
  // from that frame; only Restart returns the clip to zero.
  const handleAnimationEnabledChange = useCallback((enabled) => {
    const currentState = animationStateRef.current;
    const nextEnabled = enabled !== false;
    const clip = findAnimationClip(selectedAnimationClips, currentState.activeClipId);
    const elapsedSec = currentState.playing && clip
      ? clampAnimationElapsed(getAnimationClock(), animationClipDuration(clip))
      : currentState.elapsedSec;
    const nextState = {
      ...currentState,
      enabled: nextEnabled,
      elapsedSec,
      playing: nextEnabled ? currentState.playing : false
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    setAnimationClock(elapsedSec);
  }, [selectedAnimationClips]);

  const handleAnimationRestart = useCallback(() => {
    const nextState = {
      ...animationStateRef.current,
      elapsedSec: 0,
      playing: false
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    resetAnimationClock();
  }, []);

  const handleAnimationScrub = useCallback((elapsedSec) => {
    const clip = selectedActiveAnimationClip;
    if (!clip) {
      return;
    }
    const clampedElapsedSec = clampAnimationElapsed(elapsedSec, animationClipDuration(clip));
    setAnimationClock(clampedElapsedSec);
    const nextState = {
      ...animationStateRef.current,
      elapsedSec: clampedElapsedSec
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
  }, [selectedActiveAnimationClip]);

  const handleAnimationSpeedChange = useCallback((speed) => {
    const nextState = {
      ...animationStateRef.current,
      speed: clampAnimationSpeed(speed)
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
  }, []);

  const handleAnimationLoopToggle = useCallback((nextLoopEnabled) => {
    const currentState = animationStateRef.current;
    const nextState = {
      ...currentState,
      loopEnabled: typeof nextLoopEnabled === "boolean" ? nextLoopEnabled : !currentState.loopEnabled
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
  }, []);

  // The playback loop. The clock is published through the external store rather
  // than React state so a playing clip re-renders only the render pane and the
  // time slider; the paused elapsed time is written back to React state once,
  // when playback stops. Frame pacing (shouldPublishAnimationFrame) keeps a
  // heavy assembly from saturating the main thread.
  useEffect(() => {
    if (
      !selectedActiveAnimationClip ||
      animationState.enabled === false ||
      !animationState.playing ||
      typeof window === "undefined" ||
      typeof window.requestAnimationFrame !== "function"
    ) {
      return undefined;
    }

    const clip = selectedActiveAnimationClip;
    const duration = animationClipDuration(clip);
    let frameId = 0;
    let previousTimeMs = animationNowMs();
    // A published frame is measured by the gap to the next callback, which
    // includes the downstream render, and the next publish waits that long
    // again. previousTimeMs only advances on a publish, so time skipped this way
    // still lands in the next delta and playback stays wall-clock accurate.
    let publishedAtMs = NaN;
    let publishCostMs = 0;
    let measuringPublish = false;
    setAnimationClock(clampAnimationElapsed(animationStateRef.current.elapsedSec, duration));

    const tick = (timeMs) => {
      const currentState = animationStateRef.current;
      if (!currentState.playing || currentState.activeClipId !== clip.id) {
        return;
      }
      if (measuringPublish) {
        publishCostMs = timeMs - publishedAtMs;
        measuringPublish = false;
      }
      if (!shouldPublishAnimationFrame({ timeMs, publishedAtMs, publishCostMs })) {
        frameId = window.requestAnimationFrame(tick);
        return;
      }
      const deltaSec = Math.max((timeMs - previousTimeMs) / 1000, 0);
      previousTimeMs = timeMs;
      publishedAtMs = timeMs;
      measuringPublish = true;
      const { elapsedSec, playing } = advanceAnimationElapsed({
        elapsedSec: getAnimationClock(),
        deltaSec,
        speed: currentState.speed,
        duration,
        loopEnabled: currentState.loopEnabled !== false
      });
      setAnimationClock(elapsedSec);
      if (!playing) {
        // A non-looping clip ran out: settle the clock into React state so the
        // paused transport and the session snapshot agree with the viewport.
        const nextState = { ...currentState, elapsedSec, playing: false };
        animationStateRef.current = nextState;
        setAnimationState(nextState);
        return;
      }
      frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [animationState.enabled, animationState.playing, selectedActiveAnimationClip]);

  // THE content signal: "is there anything on screen?", answered once for every format.
  // Consumers (toolbar gates, CTA, preview mode, zoom pill, alert blocking) read this
  // instead of each one guessing which loaded object backs the viewport.
  // Embedded animation clips are checked against the compiled tree once it is
  // in hand: a target no part carries fails HERE, in the Status tab, not the
  // first time playback reaches that frame.
  const selectedAnimationValidationError = useMemo(() => {
    if (!selectedAnimationClips || !Array.isArray(selectedMeshData?.parts) || !selectedMeshData.parts.length) {
      return "";
    }
    // A partial progressive state lacks occurrences by design; validating
    // against it would report every not-yet-loaded label as a clip error, so
    // validation runs on the complete model only.
    if (selectedMeshPartial) {
      return "";
    }
    return validateAnimationClips(THREE, selectedMeshData, selectedAnimationClips)
      .map((problem) => `${problem.clip}: ${problem.error}`)
      .join("\n");
  }, [selectedAnimationClips, selectedMeshData, selectedMeshPartial]);
  const selectedAnimationError = selectedAnimationLoadError || selectedAnimationValidationError;
  const selectedViewportContent = selectedMeshData;

  // THE parameter runtime: which store backs the selected entry's parameters, resolved
  // once from the capability table. Copy/paste/reset are written against this and work
  // for any format that declares a `params` source — a third store means one more arm
  // here, not a third copy of three clipboard handlers.
  //
  // The stores stay separate on purpose: they drive different recompute pipelines. Only
  // the consumer surface is shared.
  const activeParameterRuntime = useMemo(() => {
    switch (parameterSourceKind(selectedEntrySourceFormat)) {
      case PARAMETER_SOURCE.SIDECAR:
        return {
          label: "STEP",
          definition: selectedStepModuleDefinition,
          values: stepModuleParameterValues,
          applyValues: applyStepModuleParameterValues,
          reset: handleResetStepModuleParameters
        };
      default:
        return null;
    }
  }, [
    applyStepModuleParameterValues,
    handleResetStepModuleParameters,
    selectedEntrySourceFormat,
    selectedStepModuleDefinition,
    stepModuleParameterValues
  ]);

  const handleCopyParameters = useCallback(async () => {
    setScreenshotStatus("");
    const runtime = activeParameterRuntime;
    if (!runtime?.definition?.parameters?.length) {
      setCopyStatus(`No ${runtime?.label || "model"} parameters to copy`);
      return;
    }
    try {
      await host.clipboard.writeText(buildParameterValuesCopyText(runtime.definition, runtime.values));
      setCopyStatus(`Copied ${runtime.label} parameters`);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard write failed");
    }
  }, [activeParameterRuntime]);

  const handlePasteParameters = useCallback(async () => {
    setScreenshotStatus("");
    const runtime = activeParameterRuntime;
    if (!runtime?.definition?.parameters?.length) {
      setCopyStatus(`No ${runtime?.label || "model"} parameters to paste`);
      return;
    }
    try {
      const clipboardText = await host.clipboard.readText();
      const { values, count } = parseParameterValuesPasteText(runtime.definition, clipboardText, {
        label: `${runtime.label} parameter`,
        unknownLabel: `${runtime.label} parameter`
      });
      runtime.applyValues(values);
      setCopyStatus(`Pasted ${count} ${runtime.label} param${count === 1 ? "" : "s"}`);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard paste failed");
    }
  }, [activeParameterRuntime]);

  const handleResetParameters = useCallback(() => {
    activeParameterRuntime?.reset();
  }, [activeParameterRuntime]);

  // The toolbar's Play button is a viewport control over the ANIMATION system —
  // it asks "does this model ship clips, is one running, can I toggle it". The
  // pose runtime is not consulted: a model can animate with no mates at all.
  const activeAnimationRuntime = useMemo(() => {
    switch (parameterSourceKind(selectedEntrySourceFormat)) {
      case PARAMETER_SOURCE.SIDECAR:
        return {
          available: selectedAnimationClipList.length > 0,
          playing: animationState.playing === true,
          disabled: false,
          onPlayToggle: handleAnimationPlayToggle
        };
      default:
        return null;
    }
  }, [
    animationState.playing,
    handleAnimationPlayToggle,
    selectedAnimationClipList,
    selectedEntrySourceFormat
  ]);

  const assemblyRoot = selectedAssemblyStructureReady
    ? selectedMeshData?.assemblyRoot || null
    : null;
  // An assembly tree already contains its occurrence metadata. Display-only
  // tessellation changes must not invalidate tree consumers through meshData.
  const stepPartMeshData = assemblyRoot ? null : selectedMeshData;
  const stepTreeRoot = useMemo(() => {
    if (!supportsParts) {
      return null;
    }
    return buildStepTreeRoot({
      selectedEntry,
      assemblyRoot,
      meshData: stepPartMeshData
    });
  }, [assemblyRoot, supportsParts, selectedEntry, stepPartMeshData]);
  const assemblyLeafParts = useMemo(() => {
    return Array.isArray(selectedMeshData?.parts) ? selectedMeshData.parts : flattenAssemblyLeafParts(assemblyRoot);
  }, [assemblyRoot, selectedMeshData?.parts]);
  const stepLeafParts = useMemo(() => {
    if (isAssemblyView) {
      return assemblyLeafParts;
    }
    if (!stepTreeRoot) {
      return [];
    }
    return [{
      id: STEP_MODEL_RENDER_PART_ID,
      label: stepTreeRoot.displayName || stepTreeRoot.name || "STEP part",
      name: stepTreeRoot.displayName || stepTreeRoot.name || "STEP part",
      nodeType: "part",
      bounds: selectedMeshData?.bounds || null
    }];
  }, [assemblyLeafParts, isAssemblyView, selectedMeshData?.bounds, stepTreeRoot]);
  const assemblyNodes = useMemo(() => flattenAssemblyNodes(assemblyRoot), [assemblyRoot]);
  const stepTreeNodes = useMemo(() => flattenAssemblyNodes(stepTreeRoot), [stepTreeRoot]);
  const validAssemblySelectionIds = useMemo(
    () => stepTreeNodes.map((node) => String(node?.id || "").trim()).filter(Boolean),
    [stepTreeNodes]
  );
  const validAssemblySelectionIdSet = useMemo(
    () => new Set(validAssemblySelectionIds),
    [validAssemblySelectionIds]
  );
  const assemblyRootNodeId = useMemo(
    () => rootAssemblyInspectionNodeId(assemblyRoot),
    [assemblyRoot]
  );
  const focusedAssemblyNodeIds = useMemo(() => {
    if (!isAssemblyView || !assemblyRoot || !isolatedAssemblyNodeIds.length) {
      return [];
    }
    return minimalAssemblyIsolationNodeIds(assemblyRoot, isolatedAssemblyNodeIds, {
      rootId: assemblyRootNodeId
    });
  }, [
    assemblyRoot,
    assemblyRootNodeId,
    isolatedAssemblyNodeIds,
    isAssemblyView
  ]);
  const loadableStepTreeTopologyNodeIds = useMemo(() => (
    supportsTopology && isAssemblyView && selectedEntryHasReferences
      ? collectStepTreeTopologyLoadableNodeIds(stepTreeRoot)
      : []
  ), [
    isAssemblyView,
    supportsTopology,
    selectedEntryHasReferences,
    stepTreeRoot
  ]);
  const loadableStepTreeTopologyNodeIdSet = useMemo(
    () => new Set(loadableStepTreeTopologyNodeIds),
    [loadableStepTreeTopologyNodeIds]
  );
  const expandedStepTreeTopologyNodeIds = useMemo(() => expandedVisibleStepTreeTopologyNodeIds(
    stepTreeRoot, expandedStepTreeNodeIds,
    { isolatedNodeIds: focusedAssemblyNodeIds, hiddenPartIds, isAssemblyView }
  ), [stepTreeRoot, expandedStepTreeNodeIds, focusedAssemblyNodeIds, hiddenPartIds, isAssemblyView]);
  const requestedStepTreeTopologyNodeIds = useMemo(() => {
    if (!supportsTopology || !isAssemblyView || !selectedEntryHasReferences) {
      return [];
    }
    return uniqueStringList(
      [
        ...expandedStepTreeTopologyNodeIds,
        ...stepModuleTopologyOccurrenceIds(selectedStepModuleDefinition)
      ]
        .map((id) => String(id || "").trim())
        .filter((id) => id && loadableStepTreeTopologyNodeIdSet.has(id))
    );
  }, [
    expandedStepTreeTopologyNodeIds,
    isAssemblyView,
    supportsTopology,
    loadableStepTreeTopologyNodeIdSet,
    selectedStepModuleDefinition,
    selectedEntryHasReferences,
  ]);
  const viewerSelectableAssemblyNodeIds = useMemo(
    () => (isAssemblyView
      ? selectableViewerNodeIdsForExpandedTree(assemblyRoot, expandedStepTreeNodeIds, {
        rootId: assemblyRootNodeId,
        isolatedNodeIds: focusedAssemblyNodeIds,
        topologyNodeIds: requestedStepTreeTopologyNodeIds
      })
      : []),
    [
      assemblyRoot,
      assemblyRootNodeId,
      expandedStepTreeNodeIds,
      focusedAssemblyNodeIds,
      isAssemblyView,
      requestedStepTreeTopologyNodeIds
    ]
  );
  const viewerSelectableAssemblyNodeIdSet = useMemo(
    () => new Set(viewerSelectableAssemblyNodeIds),
    [viewerSelectableAssemblyNodeIds]
  );
  const assemblyParts = useMemo(() => {
    return viewerSelectableAssemblyNodeIds.length
      ? findAssemblyNodes(assemblyRoot, viewerSelectableAssemblyNodeIds)
        .filter(Boolean)
        .map((node) => ({
          ...node,
          leafPartIds: descendantLeafPartIds(node)
        }))
      : [];
  }, [
    assemblyRoot,
    viewerSelectableAssemblyNodeIds
  ]);
  const assemblyPickPartIdMap = useMemo(() => {
    return buildAssemblyLeafToNodePickMap(assemblyParts);
  }, [assemblyParts]);
  const assemblyPartsLoaded = isAssemblyView
    ? selectedAssemblyStructureReady
    : supportsParts && selectedMeshMatches && !!selectedMeshData;
  const supportsPartSelection = supportsParts && assemblyPartsLoaded && stepLeafParts.length > 0;
  const assemblyPartMap = useMemo(() => {
    const map = new Map();
    for (const node of stepTreeNodes) {
      map.set(node.id, node);
    }
    for (const part of stepLeafParts) {
      map.set(part.id, part);
    }
    return map;
  }, [stepLeafParts, stepTreeNodes]);
  useEffect(() => {
    if (!isAssemblyView || !assemblyRoot) {
      setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
      return;
    }
    setIsolatedAssemblyNodeIds((current) => {
      const next = minimalAssemblyIsolationNodeIds(assemblyRoot, current, {
        rootId: assemblyRootNodeId
      });
      return orderedStringListEqual(next, current) ? current : next;
    });
  }, [
    assemblyRoot,
    assemblyRootNodeId,
    isAssemblyView
  ]);
  const validAssemblyLeafIds = useMemo(
    () => stepLeafParts.map((part) => String(part?.id || "").trim()).filter(Boolean),
    [stepLeafParts]
  );
  const validAssemblyLeafIdSet = useMemo(
    () => new Set(validAssemblyLeafIds),
    [validAssemblyLeafIds]
  );
  const resolvePickedAssemblyPartId = useCallback((partId) => {
    return resolveAssemblyPickedPartId(partId, {
      pickPartIdMap: assemblyPickPartIdMap,
      validLeafPartIds: validAssemblyLeafIdSet
    });
  }, [assemblyPickPartIdMap, validAssemblyLeafIdSet]);
  const renderPartIdsForAssemblySelection = useCallback((partId, fallbackPartId = "") => {
    if (String(partId || "").trim() === STEP_MODEL_ROOT_ID) {
      return [STEP_MODEL_RENDER_PART_ID];
    }
    return leafPartIdsForAssemblySelection(partId, {
      assemblyPartMap,
      fallbackPartId,
      validLeafPartIds: validAssemblyLeafIdSet
    });
  }, [assemblyPartMap, validAssemblyLeafIdSet]);
  const renderPartIdForAssemblySelection = useCallback((partId, fallbackPartId = "") => {
    return renderPartIdsForAssemblySelection(partId, fallbackPartId)[0] || "";
  }, [renderPartIdsForAssemblySelection]);
  useLayoutEffect(() => {
    const hiddenLeafIds = new Set(
      (Array.isArray(hiddenPartIds) ? hiddenPartIds : [])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    if (!hiddenLeafIds.size) {
      return;
    }
    setExpandedStepTreeNodeIds((current) => {
      let changed = false;
      const next = current.filter((nodeId) => {
        const leafIds = renderPartIdsForAssemblySelection(nodeId)
          .map((id) => String(id || "").trim())
          .filter(Boolean);
        const shouldCollapse = leafIds.length > 0 && leafIds.every((id) => hiddenLeafIds.has(id));
        if (shouldCollapse) {
          changed = true;
          return false;
        }
        return true;
      });
      return changed ? next : current;
    });
  }, [
    hiddenPartIds,
    renderPartIdsForAssemblySelection
  ]);
  const selectedUrdfPreviewError = selectedUrdfPreview.error;
  const effectiveRenderFormat = selectedEntrySourceFormat;
  // A robot is loading until EVERY link mesh has landed. It is published once, complete,
  // so this stays true for the whole fetch and the card keeps reporting "loading meshes
  // 7/13" — a partially-drawn robot with no card gives no sign whether more is coming.
  const urdfViewerLoading =
    !!selectedEntry &&
    urdfStatus !== ASSET_STATUS.ERROR &&
    (!selectedUrdfMatches || urdfStatus === ASSET_STATUS.LOADING);
  // A fatal render-artifact error (not building) stops the loading spinner so the error
  // surfaces. Every artifact-managed format, not just STEP: a DXF build that failed would
  // otherwise spin forever behind its own error.
  const artifactBlocksRender =
    isArtifactManagedFormat(effectiveRenderFormat) &&
    selectedArtifact.status === "failed" && !editingHasView;
  const meshViewerLoading =
    !!selectedEntry &&
    // A DRAWING has no flat pattern and bakes nothing, so "no mesh yet" is its finished state,
    // not a pending one. Waiting on the mesh path left the pane on LOADING forever (issue #246).
    !selectedEntryIsDrawingDocument &&
    (selectedStepArtifactRenderPending || !artifactBlocksRender) &&
    status !== ASSET_STATUS.ERROR &&
    ((!selectedMeshMatches && !retainedPreviousStepMeshError) ||
      status === ASSET_STATUS.LOADING || selectedStepModuleLoading);
  // DXF has no arm -- it renders its baked preview through the mesh path like everything
  // else.
  const viewerLoading = {
    [ASSET_KIND.ROBOT]: urdfViewerLoading,
    [ASSET_KIND.MESH]: meshViewerLoading,
    // A DXF loads a drawing but RENDERS the drawing package's baked preview through the
    // mesh path, so its readiness is the mesh loader's.
    [ASSET_KIND.DRAWING]: meshViewerLoading
  }[assetKindForRenderFormat(effectiveRenderFormat)];
  const effectiveViewerLoading = viewerLoading || selectedArtifactGenerating || selectedCatalogPending || (fileParamSelectionPending && !editingPreview.entry);
  // The file explorer spins the entry the viewer is actually working on. Artifact
  // generation is only half of that -- a built package still has to be fetched and
  // decoded, and an entry sitting un-built is NOT loading (nothing loads in a static
  // list), so this is deliberately the SELECTED entry while the viewer is busy rather
  // than "every entry without an artifact".
  const assemblySidebarLoading =
    isAssemblyView &&
    selectedMeshMatches &&
    !assemblyPartsLoaded &&
    !selectedAssemblyHydrationFailed;
  const activeMeshLoadProgress = meshLoadInProgress && meshLoadTargetFile === fileKey(selectedEntry)
    ? meshLoadProgress : null;
  const selectedLoadProgress = selectedArtifactProgress || activeMeshLoadProgress || urdfLoadProgress || null;
  const presentationKey = selectedKey ? `${selectedKey}:${selectedMeshData ? meshState?.meshHash || selectedMeshHash : selectedMeshHash}:${selectedMeshPartial ? "partial" : "complete"}` : "";
  const [presentationState, setPresentationState] = useState(null);
  const handlePresentationChange = useCallback((next) => {
    setPresentationState(previous => previous?.file === next.file && previous?.renderMode === next.renderMode &&
      previous?.key === next.key && previous?.covering === next.covering && previous?.preparing === next.preparing ? previous : next);
  }, []);
  const presentationPending = Boolean(selectedMeshData || selectedEntryIsDrawingDocument) && (
    presentationState?.file !== selectedKey || presentationState?.key !== presentationKey || presentationState?.renderMode !== renderSession.enabled ||
    presentationState?.preparing === true
  );
  const currentPreviewVisible = Boolean(editingPreview.entry && selectedMeshMatches && !selectedMeshPartial &&
    !presentationPending && Number(editingPreview.state.preview?.revision) === Number(editingPreview.state.revision));
  const completedViewFile = useRef("");
  useEffect(() => {
    if (!effectiveViewerLoading && !selectedMeshPartial && !presentationPending &&
        (selectedMeshData || selectedEntryIsDrawingDocument)) completedViewFile.current = selectedKey;
  }, [effectiveViewerLoading, selectedMeshPartial, presentationPending, selectedMeshData, selectedEntryIsDrawingDocument, selectedKey]);
  const selectedDrawingBendAxisCount = useMemo(() => {
    if (!drawingGeometry?.geometry) {
      return 0;
    }
    try {
      return extractOrderedDxfBendLines(drawingGeometry).length;
    } catch {
      return 0;
    }
  }, [drawingGeometry]);
  // Gated to drawings HERE, not downstream. The thickness state defaults to 0 mm, and
  // passing its scale unconditionally squashed every STEP/STL/3MF model to a hair the moment
  // the default changed -- a drawing setting must not be able to touch any other format.
  const selectedEntryIsDrawing = selectedEntrySourceFormat === RENDER_FORMAT.DXF;
  const drawingThicknessScale = selectedEntryIsDrawing
    ? normalizeDxfThicknessMm(drawingThicknessMm) / DXF_PREVIEW_REFERENCE_THICKNESS_MM
    : 1;

  // What the backend says about the document's NEIGHBOURS (a retired render
  // module still sitting beside it, say). The geometry is correct, so this is
  // the LAST alert considered below: any real failure outranks it, and it never
  // blocks the viewport -- it rides the file-status badge and its dialog.
  const artifactWarningAlert = useMemo(
    () => buildArtifactWarningAlert(fileKey(selectedEntry), selectedArtifact.warnings),
    [selectedEntry, selectedArtifact.warnings]
  );
  const viewerAlert = useMemo(() => {
    const editFailure = buildViewerEditAlert(editingPreview.state, currentPreviewVisible, Boolean(selectedMeshData && !selectedMeshPartial));
    if (editFailure) return editFailure;
    if (catalogError && !selectedMeshData) return {
      severity: "error", kind: "status", title: "Couldn’t open the model",
      message: "The viewer couldn’t retrieve this file’s information.",
      tooltip: "The viewer couldn’t retrieve information about this file. Try reloading the viewer.",
      recovery: "Try again. If this continues, check that the viewer is running.",
      details: catalogError, reload: true,
    };
    if (viewerRuntimeAlert?.blocking) {
      return viewerRuntimeAlert;
    }
    if (!selectedEntry || viewerLoading || selectedArtifactGenerating) {
      return null;
    }
    if (isRobotRenderFormat(effectiveRenderFormat)) {
      return buildViewerMeshAlert(
        selectedEntry,
        !!selectedMeshData,
        urdfStatus === ASSET_STATUS.ERROR ? urdfError : selectedUrdfPreviewError
      ) || viewerRuntimeAlert || artifactWarningAlert;
    }
    const meshAlert = buildViewerMeshAlert(
      selectedEntry,
      !!selectedMeshData,
      meshLoadErrorForViewer({
        fatalError: status === ASSET_STATUS.ERROR ? error : "",
        hydrationFailed: selectedAssemblyHydrationFailed,
        backgroundError: meshState?.assemblyBackgroundError,
      }),
      selectedMeshData && !selectedMeshPartial &&
        !["submitted", "queued", "building"].includes(editingPreview.state?.state) &&
        ["network", "timeout", "status"].includes(selectedArtifact.failure?.kind)
        ? null : selectedArtifact,
      { partial: selectedMeshPartial }
    );
    return meshAlert || viewerRuntimeAlert || artifactWarningAlert;
  }, [
    artifactWarningAlert,
    editingPreview.state,
    currentPreviewVisible,
    catalogError,
    effectiveRenderFormat,
    error,
    meshState?.assemblyBackgroundError,
    selectedAssemblyHydrationFailed,
    selectedEntry,
    selectedArtifact,
    selectedArtifactGenerating,
    selectedMeshPartial,
    selectedMeshData,
    selectedUrdfPreviewError,
    status,
    urdfError,
    urdfStatus,
    viewerLoading,
    viewerRuntimeAlert
  ]);
  const focusedAssemblyTopologyActive = Boolean(
    isAssemblyView &&
    requestedStepTreeTopologyNodeIds.length > 0 &&
    viewerSelectableAssemblyNodeIds.length < 1
  );
  const viewerInAssemblyMode =
    isAssemblyView &&
    viewerSelectableAssemblyNodeIds.length > 0;
  const viewerMode = viewerInAssemblyMode ? "assembly" : "part";
  // STEP and drawings share the markup tool — the strokes are a screen-space overlay on the
  // shared mesh scene, nothing STEP-specific. This gate was the last place that said
  // otherwise: the toolbar showed Draw for a DXF while this kept it inert, so the drag fell
  // through to orbit.
  const drawModeActive = supportsTool(selectedEntrySourceFormat, "draw") &&
    tabToolMode === TAB_TOOL_MODE.DRAW;
  const panToolActive = tabToolMode === TAB_TOOL_MODE.PAN;
  const selectionCountBase = selectedPartIds.length + selectedReferenceIds.length;

  const selectedReferenceIdsRef = useRef(selectedReferenceIds);
  const selectedPartIdsRef = useRef(selectedPartIds);
  const selectedEntryBuildSnapshotRef = useRef({
    fileRef: "",
    stepHash: ""
  });
  const drawingStrokesRef = useRef(drawingStrokes);
  const drawingUndoStackRef = useRef(drawingUndoStack);
  const drawingRedoStackRef = useRef(drawingRedoStack);
  const viewerRef = useRef(null);
  // The surface's root: what the layout hook measures instead of the window
  // when this surface is one pane of a host application, and where compact-
  // mode sheets portal to so they cover this surface and not the host's window.
  const hostRef = useRef(null);
  const [hostElement, setHostElement] = useState(null);
  useEffect(() => {
    setHostElement(hostRef.current);
  }, []);
  // This is the displayed render revision, so same-file saves cannot inherit
  // a predecessor's scheduler or benchmark milestones.
  const viewportQualityModelKey = `${selectedEntry?.file || ""}:${selectedMeshHash || selectedEntry?.hash || ""}`;
  // Viewport LOD (design/unified-tessellation.md Phase 5): camera-settle
  // driven re-tessellation of the components that project the worst error.
  const { onCameraMoved: onLodCameraMoved } = useViewportLod({
    resources: client.resources,
    viewerRef,
    modelKey: viewportQualityModelKey,
    quality: resolvedScene.quality,
    lodPackage,
    tessellationCache: cadRenderSession.tessellationCache,
    applyComponentLodBatch,
    prepareComponentLodPayload,
    componentLodNeedsSelectors,
    // Capability, not just the current pose: a paused/disabled module can move
    // an offscreen part without a camera event when re-enabled.
    dynamicScene: lodSceneMayMove({ robot: isUrdfView, drawing: selectedEntryIsDrawing,
      kinematics: selectedStepModuleDefinition, kinematicsLoading: selectedStepModuleLoading,
      animation: selectedSourceAnimation, exploded: resolvedScene.display?.exploded?.enabled })
  });
  const viewportQualityStatus = useViewportQualityStatus({
    modelKey: viewportQualityModelKey,
    quality: resolvedScene.quality,
    file: selectedEntry?.file || "",
    hasGeometry: Boolean(selectedMeshData),
    // A progressive assembly's first paint is a real preview, but more
    // components can still arrive. It must not look fully refined yet.
    modelComplete: !selectedMeshPartial && !meshLoadInProgress,
    // The scheduler installs its snapshot after React commits this package.
    // Its current scope must match this package before it can finish quality.
    lodExpectedComponentCount: Array.isArray(lodPackage?.components) ? lodPackage.components.length : 0
  });
  const previewUiStateRef = useRef(null);
  const fileSessionSaveTimerRef = useRef(0);
  const activePerspectiveRef = useRef(null);
  const selectedFileSheetKeyRef = useRef("");

  const desktopRightPanelOpen = false;

  const drawingSettingsLoadedKeyRef = useRef(null);
  useEffect(() => {
    if (drawingSettingsLoadedKeyRef.current !== selectedKey || !selectedEntryIsDrawing) return;
    emitState({ drawing: { thicknessMm: drawingThicknessMm, bends: drawingBends,
      bendStyle: drawingBendStyle, bendRadiusMm: drawingBendRadiusMm, kFactor: drawingKFactor,
      hiddenLayers: drawingHiddenLayers, units: drawingUnits, orientation: drawingOrientation,
      material: drawingMaterial, viewMode: drawingViewMode, lineWeight: drawingLineWeight,
      dimensionDisplay: drawingDimensionDisplay } });
  }, [selectedKey, selectedEntryIsDrawing, drawingThicknessMm, drawingBends, drawingBendStyle,
    drawingBendRadiusMm, drawingKFactor, drawingHiddenLayers, drawingUnits, drawingOrientation,
    drawingMaterial, drawingViewMode, drawingLineWeight, drawingDimensionDisplay, emitState]);
  useLayoutEffect(() => {
    const stored = restoreStateRef.current.drawing;
    drawingSettingsLoadedKeyRef.current = selectedKey;
    setDrawingThicknessMm(normalizeDxfThicknessMm(stored?.thicknessMm, DXF_DEFAULT_THICKNESS_MM));
    setDrawingBendStyle(normalizeDxfBendStyle(stored?.bendStyle, DXF_DEFAULT_BEND_STYLE));
    setDrawingBendRadiusMm(normalizeDxfBendRadiusMm(stored?.bendRadiusMm, DXF_DEFAULT_BEND_RADIUS_MM));
    setDrawingKFactor(normalizeDxfKFactor(stored?.kFactor, DXF_DEFAULT_KFACTOR));
    setDrawingHiddenLayers(Array.isArray(stored?.hiddenLayers) ? stored.hiddenLayers : []);
    setDrawingUnits(normalizeDxfUnits(stored?.units, DXF_DEFAULT_UNITS));
    setDrawingOrientation(normalizeDxfOrientation(stored?.orientation));
    setDrawingMaterial(normalizeDxfMaterial(stored?.material, DXF_DEFAULT_MATERIAL));
    setDrawingLineWeight(normalizeDxfLineWeight(stored?.lineWeight, DXF_DEFAULT_LINE_WEIGHT));
    setDrawingDimensionDisplay(normalizeDxfDimensionDisplay(stored?.dimensionDisplay));
    setDrawingViewMode(stored?.viewMode === "2d" ? "2d" : "3d");
    setDrawingBends(Array.from({ length: selectedDrawingBendAxisCount }, (_, index) => ({
      angleDeg: normalizeDxfBendAngleDeg(stored?.bends?.[index]?.angleDeg, DXF_DEFAULT_BEND_ANGLE_DEG),
      direction: normalizeDxfBendDirection(stored?.bends?.[index]?.direction)
    })));
  }, [selectedKey, selectedDrawingBendAxisCount]);

  // The drawing's geometry is the parsed .dxf ITSELF (design/standalone-viewer.md
  // Phase A): no package, no geometry.json — loadRenderDxf memoizes the parse and
  // the mesh loader reuses the same cache, so the file is fetched and parsed once.
  const drawingGeometryUrl = selectedEntryIsDrawing
    ? String(entryAssetUrl(selectedEntry, "dxf") || "")
    : "";
  // A dimensioned DOCUMENT is shown as ezdxf renders it (the same renderer that prints
  // the PDF): the server answers /__cad/drawing with SVG for the same file ref the asset
  // URL carries, minus whichever layers are switched off.
  const drawingSvgUrl = useMemo(() => {
    if (!drawingGeometryUrl || !selectedEntryIsDrawingDocument) {
      return "";
    }
    let fileRef = "";
    let origin = "";
    try {
      // The asset URL is relative in the web viewer and absolute (the viewer server's
      // origin) in the desktop; the drawing route lives wherever the asset does.
      const parsed = new URL(drawingGeometryUrl, "http://cad.local");
      fileRef = parsed.searchParams.get("file") || "";
      origin = parsed.origin === "http://cad.local" ? "" : parsed.origin;
    } catch {
      fileRef = "";
    }
    if (!fileRef) {
      return "";
    }
    const params = new URLSearchParams({ file: fileRef });
    const hidden = (Array.isArray(drawingHiddenLayers) ? drawingHiddenLayers : []).filter(Boolean);
    if (hidden.length) {
      params.set("hide", hidden.join(","));
    }
    const lineWeightScale = dxfLineWeightScale(drawingLineWeight);
    if (lineWeightScale !== 1) {
      params.set("lw", String(lineWeightScale));
    }
    for (const [key, value] of Object.entries(dxfDimensionDisplayParams(drawingDimensionDisplay))) {
      params.set(key, value);
    }
    for (const [key, value] of Object.entries(drawingEditParams(drawingEdits, { highlight: drawingSelectedDimension }))) {
      params.set(key, value);
    }
    return `${origin}/__cad/drawing?${params.toString()}`;
  }, [drawingGeometryUrl, selectedEntryIsDrawingDocument, drawingHiddenLayers, drawingLineWeight, drawingDimensionDisplay, drawingEdits, drawingSelectedDimension]);
  // Edits belong to one sheet: switching files drops them and the tool.
  useEffect(() => {
    setDrawingEdits([]);
    setDrawingEditTool("");
    setDrawingPickedPoints([]);
    setDrawingSelectedDimension("");
  }, [selectedKey]);
  useEffect(() => {
    if (!drawingGeometryUrl) {
      setDrawingGeometry(null);
      return undefined;
    }
    const cache = drawingGeometryCacheRef.current;
    if (cache.has(drawingGeometryUrl)) {
      setDrawingGeometry(cache.get(drawingGeometryUrl));
      return undefined;
    }
    let cancelled = false;
    loadRenderDxf(drawingGeometryUrl, { resources: client.resources })
      .then((payload) => {
        if (cancelled) {
          return;
        }
        if (payload) {
          cache.set(drawingGeometryUrl, payload);
        }
        setDrawingGeometry(payload || null);
      })
      .catch(() => {
        if (!cancelled) {
          setDrawingGeometry(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [drawingGeometryUrl]);

  const handleDrawingBendChange = useCallback((index, patch) => {
    setDrawingBends((current) => current.map(
      (bend, bendIndex) => (bendIndex === index ? { ...bend, ...patch } : bend)
    ));
  }, []);

  // Per-tab resets (settings-ui.md: one Reset per tab, scoped to that tab's settings).
  const handleDrawingMaterialReset = useCallback(() => {
    setDrawingThicknessMm(DXF_DEFAULT_THICKNESS_MM);
    setDrawingUnits(DXF_DEFAULT_UNITS);
    setDrawingMaterial(DXF_DEFAULT_MATERIAL);
  }, []);

  const drawingViews = useMemo(
    () => (Array.isArray(drawingGeometry?.views) ? drawingGeometry.views : EMPTY_LIST),
    [drawingGeometry]
  );
  const drawingSheetDimensions = useMemo(
    () => (Array.isArray(drawingGeometry?.sheetDimensions) ? drawingGeometry.sheetDimensions : EMPTY_LIST),
    [drawingGeometry]
  );
  const handleDrawingEditToolChange = useCallback((tool) => {
    setDrawingEditTool(tool);
    setDrawingPickedPoints([]);
    drawingPickedSnapsRef.current = [];
  }, []);
  // Smart dimension: an edge or a hole dimensions itself on one click; a corner waits
  // for a second pick and the two give a distance. Picks carry the snap they landed on.
  // Staged moves shift what the tools see (outlines, snap targets) so a moved view is
  // where it now shows; a pick on it is put back into the file's coordinates before it
  // is staged, since the server applies the moves itself when it previews.
  const drawingViewShifts = useMemo(() => netViewMoves(drawingEdits), [drawingEdits]);
  const shiftForView = useCallback((name) => drawingViewShifts.get(name) || null, [drawingViewShifts]);
  const drawingShiftedViews = useMemo(() => drawingViews.map((view) => {
    const shift = drawingViewShifts.get(view.name);
    return shift ? { ...view, minX: view.minX + shift[0], maxX: view.maxX + shift[0], minY: view.minY + shift[1], maxY: view.maxY + shift[1] } : view;
  }), [drawingViews, drawingViewShifts]);
  const drawingSnapTargets = useMemo(() => {
    const targets = sheetSnapTargets(drawingGeometry?.geometry, drawingSheetDimensions);
    if (!drawingViewShifts.size) return targets;
    const move = (point, shift) => (shift ? [point[0] + shift[0], point[1] + shift[1]] : point);
    return {
      lines: targets.lines.map((line) => { const shift = drawingViewShifts.get(line.view); return shift ? { ...line, start: move(line.start, shift), end: move(line.end, shift) } : line; }),
      circles: targets.circles.map((circle) => { const shift = drawingViewShifts.get(circle.view); return shift ? { ...circle, center: move(circle.center, shift) } : circle; }),
      dimensions: targets.dimensions.map((dimension) => { const shift = drawingViewShifts.get(dimension.view); return shift ? { ...dimension, position: move(dimension.position, shift) } : dimension; })
    };
  }, [drawingGeometry, drawingSheetDimensions, drawingViewShifts]);
  const drawingPickedSnapsRef = useRef([]);
  const handleDrawingSheetPick = useCallback((picked) => {
    // Picking an existing dimension selects it (red on the sheet) for a tolerance or removal.
    if (picked.kind === "dimension") {
      setDrawingSelectedDimension((current) => (current === `${picked.view}:${picked.index}` ? "" : `${picked.view}:${picked.index}`));
      drawingPickedSnapsRef.current = [];
      setDrawingPickedPoints([]);
      return;
    }
    const shift = shiftForView(picked.view);
    const back = (point) => (shift ? [point[0] - shift[0], point[1] - shift[1]] : point);
    const snap = shift ? {
      ...picked,
      point: back(picked.point),
      line: picked.line ? { ...picked.line, start: back(picked.line.start), end: back(picked.line.end) } : picked.line,
      circle: picked.circle ? { ...picked.circle, center: back(picked.circle.center) } : picked.circle
    } : picked;
    const snaps = [...drawingPickedSnapsRef.current, snap];
    const view = drawingViews.find((candidate) => candidate.name === snap.view)
      || viewAtSheetPoint(drawingViews, snap.point) || nearestView(drawingViews, snap.point);
    const edit = smartDimensionFromSnaps(view, snaps);
    if (edit) {
      setDrawingEdits((edits) => [...edits, { id: createDrawingEditId(), ...edit, view: edit.view || view?.name }]);
      drawingPickedSnapsRef.current = [];
      setDrawingPickedPoints([]);
      return;
    }
    drawingPickedSnapsRef.current = snaps;
    setDrawingPickedPoints(snaps.map((item) => {
      const itemShift = shiftForView(item.view);
      return itemShift ? [item.point[0] + itemShift[0], item.point[1] + itemShift[1]] : item.point;
    }));
  }, [drawingViews, shiftForView]);
  const handleDrawingViewMove = useCallback((view, dx, dy) => {
    setDrawingEdits((edits) => [...edits, { id: createDrawingEditId(), kind: "move", view, dx, dy }]);
  }, []);
  const handleDrawingAddTolerance = useCallback((key, spec) => {
    const [view, index] = String(key).split(":");
    if (!view || index === undefined) return;
    setDrawingEdits((edits) => [
      ...edits.filter((edit) => !(edit.kind === "tol" && edit.view === view && String(edit.index) === index)),
      { id: createDrawingEditId(), kind: "tol", view, index, spec }
    ]);
  }, []);
  const handleDrawingRemoveDimension = useCallback((key) => {
    const [view, index] = String(key).split(":");
    if (!view || index === undefined) return;
    setDrawingEdits((edits) => [
      ...edits.filter((edit) => !((edit.kind === "del" || edit.kind === "tol") && edit.view === view && String(edit.index) === index)),
      { id: createDrawingEditId(), kind: "del", view, index }
    ]);
    setDrawingSelectedDimension("");
  }, []);
  const handleDrawingDiscardEdit = useCallback((id) => {
    setDrawingEdits((edits) => edits.filter((edit) => edit.id !== id));
  }, []);
  const handleDrawingDiscardEdits = useCallback(() => {
    setDrawingEdits([]);
    setDrawingEditTool("");
    setDrawingPickedPoints([]);
  }, []);
  // The request goes through the host's prompt channel (Hardcore adds it to the chat
  // composer; a host without one copies it), as a text part of a CAD prompt context.
  const drawingEditsCanSend = typeof host.promptContext?.deliver === "function";
  const handleDrawingSendEdits = useCallback(() => {
    const text = drawingEditsPromptText({
      drawingPath: selectedEntry ? cadFileParamForEntry(selectedEntry) : "",
      edits: drawingEdits,
      views: drawingViews,
      dimensions: drawingSheetDimensions
    });
    if (!text) return;
    const clear = () => {
      setDrawingEdits([]);
      setDrawingEditTool("");
      setDrawingPickedPoints([]);
    };
    if (drawingEditsCanSend) {
      const resource = { ...documentResource, revision: String(selectedEntry?.documentHash || selectedEntry?.hash || documentResource?.revision || "") };
      let pending;
      try { pending = host.promptContext.deliver(createCadPromptContext({ resource, text })); }
      catch (error) { pending = Promise.reject(error); }
      Promise.resolve(pending)
        .catch((error) => ({ status: "failed", message: error instanceof Error ? error.message : String(error) }))
        .then((result) => {
          setCopyStatus(promptDeliveryMessage(result));
          if (result.status === "added" || result.status === "copied") clear();
        });
      return;
    }
    const done = () => setCopyStatus("Drawing edits copied. Paste them to the agent that owns the script.");
    host.clipboard?.writeText?.(text)?.then?.(done, () => setCopyStatus("Could not copy the drawing edits.")) ?? done();
  }, [selectedEntry, drawingEdits, drawingViews, drawingSheetDimensions, drawingEditsCanSend, host, documentResource]);

  // The Sheet tab's Reset: the document's own look, every layer shown.
  const handleDrawingSheetReset = useCallback(() => {
    setDrawingLineWeight(DXF_DEFAULT_LINE_WEIGHT);
    setDrawingDimensionDisplay(DXF_DEFAULT_DIMENSION_DISPLAY);
    setDrawingHiddenLayers([]);
  }, []);

  const handleDrawingBendsReset = useCallback(() => {
    setDrawingBends((current) => current.map(() => ({
      angleDeg: DXF_DEFAULT_BEND_ANGLE_DEG,
      direction: "up"
    })));
  }, []);

  const handleDrawingOrientationReset = useCallback(() => {
    setDrawingOrientation(DXF_DEFAULT_ORIENTATION);
  }, []);

  const handleDrawingRotateOrientation = useCallback((axis) => {
    setDrawingOrientation((current) => {
      const normalized = normalizeDxfOrientation(current);
      return { ...normalized, [axis]: (normalized[axis] + 1) % 4 };
    });
  }, []);

  const handleDrawingLayerVisibilityChange = useCallback((layerName, visible) => {
    setDrawingHiddenLayers((current) => {
      const next = current.filter((name) => name !== layerName);
      if (!visible) {
        next.push(layerName);
      }
      return next;
    });
  }, []);

  // The bend LINES (full 2D segments — orientation matters now) come from the package's
  // parsed geometry; the scanner's bendLineCount only sizes the settings rows before the
  // geometry fetch lands.
  const drawingBendLines = useMemo(() => {
    if (!drawingGeometry?.geometry) {
      return null;
    }
    try {
      return extractOrderedDxfBendLines(drawingGeometry).map((bendLine) => ({
        start: bendLine.start,
        end: bendLine.end
      }));
    } catch {
      return null;
    }
  }, [drawingGeometry]);

  const drawingLayers = useMemo(
    () => (Array.isArray(drawingGeometry?.layers) ? drawingGeometry.layers : []),
    [drawingGeometry]
  );
  // What the sheet says about itself (paper, scale, projection, revision): read from
  // its frame and title block, so the Sheet tab states only what the drawing states.
  const drawingSheetFactsValue = useMemo(
    () => (selectedEntryIsDrawingDocument ? drawingSheetFacts(drawingGeometry) : null),
    [selectedEntryIsDrawingDocument, drawingGeometry]
  );



  // Memoised: this array is an effect dependency in the viewer, and a fresh identity per
  // render would re-run the fold transform on every workspace render.
  const drawingBendAnglesRad = useMemo(
    () => drawingBends.map((bend) => (
      (normalizeDxfBendAngleDeg(bend.angleDeg) * Math.PI / 180)
        * (bend.direction === "down" ? -1 : 1)
    )),
    [drawingBends]
  );

  const handleDrawingViewModeChange = useCallback((mode) => {
    const next = mode === "2d" ? "2d" : "3d";
    setDrawingViewMode(next);
    if (next === "2d") {
      // "z" is the top face in VIEW_PLANE_FACES — looking straight down at a flat pattern
      // IS the 2D view, which is why this needs no separate 2D renderer.
      viewerRef.current?.activateViewPlaneFace?.("z");
      return;
    }
    viewerRef.current?.activateDefaultViewPlane?.();
  }, []);

  // A dimensioned drawing is a sheet: it opens looking straight down at it. The 3D toggle
  // is still there for anyone who wants the tilt; the default is the drawing's own view.
  const documentPlanKeyRef = useRef(null);
  useEffect(() => {
    if (!selectedEntryIsDrawingDocument) {
      documentPlanKeyRef.current = null;
      return;
    }
    if (documentPlanKeyRef.current === selectedKey) {
      return;
    }
    documentPlanKeyRef.current = selectedKey;
    handleDrawingViewModeChange("2d");
  }, [selectedEntryIsDrawingDocument, selectedKey, handleDrawingViewModeChange]);

  const handleViewerZoomPercentChange = useCallback((nextZoomPercent) => {
    viewerRef.current?.applyZoomPercent?.(nextZoomPercent);
  }, []);
  const handleViewerZoomReset = useCallback(() => {
    viewerRef.current?.resetView?.();
    if (drawingViewMode === "2d") {
      // A locked plan view resets to its own top-down, not to the 3D default orientation.
      viewerRef.current?.activateViewPlaneFace?.("z");
    }
  }, [drawingViewMode]);

  // Nothing toggles one panel on its own any more: the panel column has one
  // open id, and `handleTogglePanel` below is the single write that moves it.
  // A pair of per-panel toggles beside it would be a second way to say the
  // same thing, and the two would disagree the moment the tree joined them.

  const handleViewerAlertChange = useCallback((nextAlert) => {
    setViewerRuntimeAlert(nextAlert || null);
  }, []);

  const fileSheetResizeHandler = null;

  const resetSelectionForStepUpdate = useCallback(() => {
    selectedPartIdsRef.current = [];
    selectedReferenceIdsRef.current = [];
    setSelectedPartIds([]);
    setSelectedReferenceIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedWholeEntryCadRefToken("");
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setCopyStatus("");
  }, []);

  const selectedFileStatusItems = useMemo(() => (
    selectedArtifactGenerating
      ? []
      : buildFileStatusItems({
        entry: selectedEntry,
        fileSheetKind: selectedFileSheetKind,
        stepSourceStatus: selectedStepSourceStatus,
        urdfData: selectedUrdfData,
        viewerAlert,
        stepArtifactGenerationAvailable,
        activeGenerationFiles: activeStepArtifactGenerationFiles,
        viewerServerInfo,
        artifactAdvisory: selectedArtifact.advisory
      })
  ), [
    activeStepArtifactGenerationFiles,
    selectedEntry,
    selectedFileSheetKind,
    selectedArtifact.advisory,
    selectedArtifactGenerating,
    stepArtifactGenerationAvailable,
    selectedStepSourceStatus,
    selectedUrdfData,
    viewerAlert,
    viewerServerInfo
  ]);
  const selectedFileStatusLevel = useMemo(
    () => mostIntenseFileStatusLevel(selectedFileStatusItems),
    [selectedFileStatusItems]
  );
  const selectedFileHasWarningOrErrorStatus = fileStatusHasWarningsOrErrors(selectedFileStatusItems);

  const fileSheetSectionOptions = useMemo(() => ({
    // Gated separately, because the two systems are separate: mates give a Pose
    // tab, clips give an Animation tab, and a model may have either or both.
    hasStepPosePanel: Boolean(
      selectedStepModuleDefinition ||
      selectedStepModuleStatus === "loading" ||
      selectedStepModuleError
    ),
    hasStepAnimationPanel: Boolean(
      selectedAnimationClipList.length ||
      (selectedAnimationSourceKey && selectedAnimationStatus === "loading") ||
      selectedAnimationError
    ),
    hasEmbeddedGlbAnimationPanel: Boolean(embeddedGlbAnimationRuntime),
    hasMaterialsPanel: materialSession.enabled,
    measurementAvailable: effectiveSupportsMeasure,
    hasDxfBendsPanel: selectedFileSheetKind === "dxf" && drawingBends.length > 0,
    hasDxfLayersPanel: selectedFileSheetKind === "dxf" && drawingLayers.length > 1,
    isDrawingDocument: selectedFileSheetKind === "dxf" && selectedEntryIsDrawingDocument,
    renderMode: renderSession.enabled,
    isSdf: selectedFileSheetKind === "sdf",
    hasRobotComponents: selectedUrdfComponents.length > 0,
    showJoints: selectedFileSheetKind === "urdf" || selectedFileSheetKind === "srdf" || selectedFileSheetKind === "sdf"
  }), [
    selectedAnimationClipList,
    selectedAnimationError,
    selectedAnimationStatus,
    embeddedGlbAnimationRuntime,
    materialSession.enabled,
    effectiveSupportsMeasure,
    selectedFileSheetKind,
    selectedStepModuleDefinition,
    selectedStepModuleError,
    selectedStepModuleStatus,
    selectedStepModuleUrl,
    selectedUrdfComponents,
    drawingBends,
    drawingLayers,
    selectedEntryIsDrawingDocument,
    renderSession.enabled
  ]);

  const renderedSelectedFileSheetSectionIds = useMemo(
    () => renderedFileSheetSectionIds(selectedFileSheetKind, fileSheetSectionOptions),
    [fileSheetSectionOptions, selectedFileSheetKind]
  );
  const renderedCadFileSheetSectionIds = useMemo(
    () => renderedFileSheetSectionIds(selectedFileSheetKind, { ...fileSheetSectionOptions, renderMode: false }),
    [fileSheetSectionOptions, selectedFileSheetKind]
  );
  const defaultCadFileSheetOpenSectionIds = useMemo(
    () => defaultOpenFileSheetSectionIds(selectedFileSheetKind, { ...fileSheetSectionOptions, renderMode: false }),
    [fileSheetSectionOptions, selectedFileSheetKind]
  );
  const effectiveCadFileSheetOpenSectionIds = useMemo(() => (
    normalizeFileSheetOpenSectionIds(
      Array.isArray(fileSheetOpenSectionIds)
        ? fileSheetOpenSectionIds
        : defaultCadFileSheetOpenSectionIds,
      renderedCadFileSheetSectionIds
    )
  ), [
    defaultCadFileSheetOpenSectionIds,
    fileSheetOpenSectionIds,
    renderedCadFileSheetSectionIds
  ]);
  const effectiveFileSheetOpenSectionIds = useMemo(() => renderSession.enabled
    ? normalizeFileSheetOpenSectionIds(renderSession.openSectionIds, renderedSelectedFileSheetSectionIds)
    : effectiveCadFileSheetOpenSectionIds,
  [renderSession.enabled, renderSession.openSectionIds, renderedSelectedFileSheetSectionIds, effectiveCadFileSheetOpenSectionIds]);

  const handleFileSheetOpenSectionIdsChange = useCallback((nextSectionIds) => {
    const normalized = normalizeFileSheetOpenSectionIds(nextSectionIds, renderedSelectedFileSheetSectionIds);
    if (renderSession.enabled) {
      setRenderSession((current) => createRenderSessionState({ ...current, openSectionIds: normalized }));
    } else {
      setFileSheetOpenSectionIds(normalized);
    }
  }, [renderSession.enabled, renderedSelectedFileSheetSectionIds]);

  const openFileSheetSection = useCallback((sectionId, { openSheet = true, activate = false } = {}) => {
    const normalizedSectionId = String(sectionId || "").trim();
    if (!normalizedSectionId || !renderedSelectedFileSheetSectionIds.includes(normalizedSectionId)) {
      return false;
    }

    if (openSheet) {
      setTabToolsOpen(true);
    }
    setFileSheetOpenSectionIds((current) => {
      const baseSectionIds = normalizeFileSheetOpenSectionIds(
        Array.isArray(current) ? current : effectiveFileSheetOpenSectionIds,
        renderedSelectedFileSheetSectionIds
      );
      if (baseSectionIds.includes(normalizedSectionId) && !activate) {
        return baseSectionIds;
      }
      return normalizeFileSheetOpenSectionIds(
        [...baseSectionIds.filter(id => id !== normalizedSectionId), normalizedSectionId],
        renderedSelectedFileSheetSectionIds
      );
    });
    return true;
  }, [
    effectiveFileSheetOpenSectionIds,
    renderedSelectedFileSheetSectionIds,
    setTabToolsOpen
  ]);

  useEffect(() => {
    if (!Array.isArray(fileSheetOpenSectionIds)) {
      return;
    }
    const normalizedSectionIds = normalizeFileSheetOpenSectionIds(
      fileSheetOpenSectionIds,
      renderedCadFileSheetSectionIds
    );
    if (orderedStringListEqual(normalizedSectionIds, fileSheetOpenSectionIds)) {
      return;
    }
    setFileSheetOpenSectionIds(normalizedSectionIds);
  }, [fileSheetOpenSectionIds, renderedCadFileSheetSectionIds]);

  const selectRobotComponent = useCallback((id, options) => {
    robotSelection.select(id, options);
    if (selectedUrdfComponents.some((component) => component.id === id)) {
      if (isWideLayout) setTabToolsOpen(true);
      // Components carries the reference at its foot, so revealing it is the whole jump.
      const revealIds = [FILE_SHEET_SECTION_IDS.ROBOT_COMPONENTS];
      setFileSheetOpenSectionIds((current) => [
        ...(current || []).filter((sectionId) => !revealIds.includes(sectionId)),
        ...revealIds
      ]);
    }
  }, [robotSelection.select, selectedUrdfComponents, isWideLayout]);

  const buildActiveTabSnapshot = useCallback(() => {
    return cloneTabSnapshot({
      referenceQuery,
      selectedReferenceIds,
      selectedPartIds,
      inspectedAssemblyNodeId: "",
      expandedStepTreeNodeIds,
      fileSheetOpenSectionIds: effectiveCadFileSheetOpenSectionIds,
      hiddenPartIds,
      camera: activePerspectiveRef.current,
      drawingTool,
      tabToolMode,
      drawingStrokes,
      drawingUndoStack,
      drawingRedoStack
    });
  }, [
    drawingTool,
    drawingRedoStack,
    drawingStrokes,
    drawingUndoStack,
    effectiveCadFileSheetOpenSectionIds,
    expandedStepTreeNodeIds,
    hiddenPartIds,
    referenceQuery,
    selectedPartIds,
    selectedReferenceIds,
    tabToolMode,
  ]);

  const readEntrySessionState = useCallback((key, entryOverride = null) => {
    return normalizeFileSessionState(stateRef.current.fileSession, {
      fileKey: key, entry: entryOverride || entryMap.get(key)
    });
  }, [entryMap]);

  const buildActiveFileSessionSnapshot = useCallback((entry) => {
    const targetEntry = entry || selectedEntry;
    const targetFileKey = fileKey(targetEntry);
    const targetUrdfJointValues = targetFileKey && jointValuesByFileRef?.[targetFileKey]
      ? jointValuesByFileRef[targetFileKey]
      : {};
    const targetMaterialOverlay = materialSession.snapshotSlice(targetEntry);
    // While a clip plays the authoritative time is the clock store's, not React
    // state's — the loop only writes back when playback stops.
    const snapshotAnimationElapsedSec = animationState.playing
      ? getAnimationClock()
      : animationState.elapsedSec;
    const activeCamera = renderCameraSnapshot(activePerspectiveRef.current);
    const snapshotRenderSession = createRenderSessionState(renderSession.enabled
      ? {
          ...renderSession,
          payload: activeCamera
            ? {
                ...renderSession.payload,
                camera: {
                  ...renderCameraSeed(activeCamera),
                  projection: activeCamera.projection || resolvedScene.camera.projection
                }
              }
            : renderSession.payload
        }
      : {
          ...renderSession,
          cadCamera: activeCamera || renderSession.cadCamera,
          cadProjection: activeCamera?.projection || renderSession.cadProjection
        });
    return createFileSessionSnapshot({
      fileKey: targetFileKey,
      entry: targetEntry,
      slices: {
        ...(entrySourceFormat(targetEntry) !== RENDER_FORMAT.DXF ? { display: displaySettings } : {}),
        render: snapshotRenderSession,
        tab: buildActiveTabSnapshot(),
        stepModule: {
          parameterValues: stepModuleParameterValues
        },
        animation: {
          activeClipId: animationState.activeClipId,
          enabled: animationState.enabled,
          elapsedSec: snapshotAnimationElapsedSec,
          speed: animationState.speed,
          loopEnabled: animationState.loopEnabled
        },
        ...(targetMaterialOverlay ? { materials: targetMaterialOverlay } : {}),
        urdf: {
          jointValues: targetUrdfJointValues,
        },
        largeFile: {
          selectableTopologyEnabled: largeFileState.selectableTopologyEnabled
        }
      }
    });
  }, [
    animationState,
    buildActiveTabSnapshot,
    displaySettings,
    jointValuesByFileRef,
    largeFileState,
    materialSession.snapshotSlice,
    renderSession,
    resolvedScene.camera.projection,
    selectedEntry,
    stepModuleParameterValues,
  ]);

  const clearFileSessionSaveTimer = useCallback(() => {
    if (!fileSessionSaveTimerRef.current || typeof window === "undefined") {
      fileSessionSaveTimerRef.current = 0;
      return;
    }
    window.clearTimeout(fileSessionSaveTimerRef.current);
    fileSessionSaveTimerRef.current = 0;
  }, []);

  const writeFileSessionForEntry = useCallback((entry) => {
    const targetFileKey = fileKey(entry);
    if (!targetFileKey) {
      return true;
    }
    emitState({ fileSession: buildActiveFileSessionSnapshot(entry) });
    return true;
  }, [buildActiveFileSessionSnapshot, emitState]);

  const flushActiveFileSession = useCallback(() => {
    clearFileSessionSaveTimer();
    return selectedEntry ? writeFileSessionForEntry(selectedEntry) : true;
  }, [clearFileSessionSaveTimer, selectedEntry, writeFileSessionForEntry]);

  const scheduleActiveFileSessionSave = useCallback(() => {
    if (!selectedEntry || typeof window === "undefined") {
      return;
    }
    clearFileSessionSaveTimer();
    fileSessionSaveTimerRef.current = window.setTimeout(() => {
      fileSessionSaveTimerRef.current = 0;
      writeFileSessionForEntry(selectedEntry);
    }, 180);
  }, [clearFileSessionSaveTimer, selectedEntry, writeFileSessionForEntry]);

  const applyEntrySessionState = useCallback((key, fileSessionState = null) => {
    const normalizedKey = String(key || "").trim();
    if (!normalizedKey) {
      return;
    }
    const sessionState = fileSessionState || readEntrySessionState(normalizedKey);
    setLargeFileState(normalizeLargeFileState(sessionState?.slices?.largeFile));
    const entry = entryMap.get(normalizedKey);
    const supportsDisplaySettings = entrySourceFormat(entry) !== RENDER_FORMAT.DXF;
    setDisplaySettings(supportsDisplaySettings
      ? normalizeDisplaySettings(sessionState?.slices?.display)
      : normalizeDisplaySettings());
    const nextRenderSession = createRenderSessionState(sessionState?.slices?.render);
    setRenderSession(nextRenderSession);
    // Only a camera this file's session actually RECORDED comes back. A file
    // opened for the first time has none, and the viewer then fits the mode
    // being opened to the model's zero pose. Synthesizing a stand-in here
    // framed the model against a bounds-radius rule of its own, tagged it with
    // the new model's key, and so suppressed that fit -- which is how a fresh
    // model opened at a pose nothing had measured.
    const restoredCamera = nextRenderSession.enabled
      ? renderCameraSnapshot(resolveSceneSettings({
          appearance: resolvedColorSchemeMode,
          prefersDark: uiPrefersDark,
          render: nextRenderSession.payload
        }).camera)
      : nextRenderSession.cadCamera;
    if (restoredCamera) {
      const scopedCamera = scopedWorkspacePerspective(restoredCamera, normalizedKey, entry);
      activePerspectiveRef.current = scopedCamera;
      setViewerPerspective(scopedCamera);
    }

    const stepModuleSlice = sessionState?.slices?.stepModule || null;
    if (stepModuleSlice) {
      setStepModuleParameterValues(stepModuleSlice.parameterValues || {});
    }

    // The animation slice restores against the CLIPS this model actually
    // compiled, which is why it is resolved through restoreAnimationState rather
    // than trusted as stored.
    const animationSlice = sessionState?.slices?.animation || null;
    if (animationSlice) {
      const restoredAnimationState = restoreAnimationState(
        animationSlice,
        animationLoadState.url === sourceAnimationKeyForEntry(entry) ? animationLoadState.clips : null
      );
      animationStateRef.current = restoredAnimationState;
      setAnimationState(restoredAnimationState);
      setAnimationClock(restoredAnimationState.elapsedSec);
    }

    materialSession.restoreSlice(normalizedKey, entry, sessionState?.slices?.materials || null);

    const urdfSlice = sessionState?.slices?.urdf || null;
    if (urdfSlice) {
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedKey]: urdfSlice.jointValues || {}
      }));
    } else {
      setJointValuesByFileRef((current) => {
        if (!current?.[normalizedKey]) {
          return current;
        }
        const next = { ...current };
        delete next[normalizedKey];
        return next;
      });
    }
  }, [
    animationLoadState,
    resolvedColorSchemeMode,
    entryMap,
    materialSession.restoreSlice,
    readEntrySessionState,
    uiPrefersDark
  ]);

  const fileSheetSelectionKeyForTab = useCallback((key) => {
    const normalizedKey = String(key || "").trim();
    const fileSheetKind = fileSheetKindForEntry(entryMap.get(normalizedKey));
    return normalizedKey && fileSheetKind ? `${normalizedKey}:${fileSheetKind}` : "";
  }, [entryMap]);

  const applyTabRecord = useCallback((tabRecord) => {
    const nextTab = createTabRecord(tabRecord?.key || "", tabRecord || {});
    const nextPerspective = scopedWorkspacePerspective(
      nextTab.camera,
      nextTab.key,
      entryMap.get(nextTab.key)
    );
    selectedFileSheetKeyRef.current = fileSheetSelectionKeyForTab(nextTab.key);
    setReferenceQuery(nextTab.referenceQuery);
    selectedReferenceIdsRef.current = nextTab.selectedReferenceIds;
    setSelectedReferenceIds(nextTab.selectedReferenceIds);
    selectedPartIdsRef.current = nextTab.selectedPartIds;
    setSelectedPartIds(nextTab.selectedPartIds);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedWholeEntryCadRefToken("");
    setExpandedStepTreeNodeIds(nextTab.expandedStepTreeNodeIds);
    setFileSheetOpenSectionIds(nextTab.fileSheetOpenSectionIds);
    setHiddenPartIds(nextTab.hiddenPartIds);
    setIsolatedAssemblyNodeIds([]);
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setCopyStatus("");
    setScreenshotStatus("");
    setTabToolMode(nextTab.tabToolMode);
    setDrawingTool(nextTab.drawingTool);
    activePerspectiveRef.current = nextPerspective;
    setViewerPerspective(nextPerspective);
    setDrawingStrokes(nextTab.drawingStrokes);
    setDrawingUndoStack(nextTab.drawingUndoStack);
    setDrawingRedoStack(nextTab.drawingRedoStack);
  }, [fileSheetSelectionKeyForTab]);

  const sessionRestoredRef = useRef(false);
  useLayoutEffect(() => {
    if (sessionRestoredRef.current) return;
    sessionRestoredRef.current = true;
    const restored = readEntrySessionState(selectedKey);
    applyTabRecord(createTabRecord(selectedKey, restored?.slices?.tab || {}));
    applyEntrySessionState(selectedKey, restored);
  }, [selectedKey, readEntrySessionState, applyTabRecord, applyEntrySessionState]);

  const flushRef = useRef(null);
  flushRef.current = flushActiveFileSession;
  useEffect(() => () => { flushRef.current?.(); }, []);

  useEffect(() => {
    // No session writes while a clip plays: the clock moves every frame and the
    // stored elapsed time would be rewritten (and re-serialized) with it.
    if (animationState.playing) {
      return undefined;
    }
    scheduleActiveFileSessionSave();
    return () => {
      clearFileSessionSaveTimer();
    };
  }, [
    animationState.playing,
    clearFileSessionSaveTimer,
    scheduleActiveFileSessionSave
  ]);

  useEffect(() => host.lifecycle?.subscribeFlush(flushActiveFileSession), [host.lifecycle, flushActiveFileSession]);

  useEffect(() => {
    selectedReferenceIdsRef.current = selectedReferenceIds;
  }, [selectedReferenceIds]);

  useEffect(() => {
    selectedPartIdsRef.current = selectedPartIds;
  }, [selectedPartIds]);

  useEffect(() => {
    const nextFileSheetKey = selectedKey && selectedFileSheetKind
      ? `${selectedKey}:${selectedFileSheetKind}`
      : "";
    if (!nextFileSheetKey) {
      selectedFileSheetKeyRef.current = "";
      return;
    }
    if (selectedFileSheetKeyRef.current === nextFileSheetKey) {
      return;
    }
    selectedFileSheetKeyRef.current = nextFileSheetKey;
  }, [selectedFileSheetKind, selectedKey]);

  useEffect(() => {
    const fileRef = fileKey(selectedEntry);
    const stepHash = String(selectedEntry?.hash || entryAssetHash(selectedEntry, "topology") || "").trim();
    if (!fileRef) {
      selectedEntryBuildSnapshotRef.current = {
        fileRef: "",
        stepHash: ""
      };
      setStepUpdateInProgress(false);
      return;
    }

    const previous = selectedEntryBuildSnapshotRef.current;
    const sameEntry = previous.fileRef === fileRef;
    const stepChanged = sameEntry && !!previous.stepHash && !!stepHash && previous.stepHash !== stepHash;

    if (stepChanged) {
      resetSelectionForStepUpdate();
      setStepUpdateInProgress(true);
    } else if (!sameEntry) {
      setStepUpdateInProgress(false);
    }

    selectedEntryBuildSnapshotRef.current = {
      fileRef,
      stepHash
    };
  }, [
    resetSelectionForStepUpdate,
    selectedEntry
  ]);

  useEffect(() => {
    if (!stepUpdateInProgress) {
      return;
    }
    if (!selectedEntry) {
      setStepUpdateInProgress(false);
      return;
    }
    if (retainedPreviousStepMeshError) {
      setStepUpdateInProgress(false);
      return;
    }
    if (selectedMeshMatches && status !== ASSET_STATUS.LOADING) {
      setStepUpdateInProgress(false);
    }
  }, [retainedPreviousStepMeshError, selectedEntry, selectedMeshMatches, status, stepUpdateInProgress]);

  useEffect(() => {
    drawingStrokesRef.current = drawingStrokes;
  }, [drawingStrokes]);

  useEffect(() => {
    drawingUndoStackRef.current = drawingUndoStack;
  }, [drawingUndoStack]);

  useEffect(() => {
    drawingRedoStackRef.current = drawingRedoStack;
  }, [drawingRedoStack]);

  useEffect(() => {
    if (effectiveRenderFormat !== RENDER_FORMAT.STEP || !selectedEntryHasReferences) {
      return;
    }
    setTabToolMode((current) => {
      if (current !== TAB_TOOL_MODE.DRAW) {
        return current;
      }
      return drawingStrokesRef.current.length ? current : TAB_TOOL_MODE.REFERENCES;
    });
  }, [effectiveRenderFormat, selectedKey, selectedEntryHasReferences]);

  useEffect(() => {
    setViewerRuntimeAlert(null);
  }, [selectedKey]);

  // The render-artifact (re)build + freshness flow now lives entirely in useArtifact (see
  // selectedArtifact above): it GETs /__cad/artifact for freshness and POSTs to (re)build when
  // missing/stale, reporting ready | generating | error. The old build effect + step-source-status
  // fetch effect that this replaced have been removed.

  useEffect(() => {
    if (!selectedEntry) {
      cancelMeshLoad();
      return;
    }
    // DRAWING loads through the mesh path too: a DXF's render asset is its own
    // file, parsed and prism-meshed client-side (design/standalone-viewer.md
    // Phase A); a dimensioned document simply yields an empty mesh and renders
    // as 2D line work instead.
    const selectedRenderAssetKind = assetKindForRenderFormat(selectedEntryRenderAssetFormat);
    if (selectedRenderAssetKind !== ASSET_KIND.MESH && selectedRenderAssetKind !== ASSET_KIND.DRAWING) {
      cancelMeshLoad();
      return;
    }
    if (!shouldStartMeshLoad({
      inProgress: meshLoadInProgress,
      targetFile: meshLoadTargetFile,
      targetHash: meshLoadTargetHash,
      entryFile: fileKey(selectedEntry),
      entryHash: selectedMeshHash,
      selectedMeshMatches,
      isAssembly: isAssemblyView,
      interactionReady: selectedAssemblyInteractionReady,
      hydrationFailed: selectedAssemblyHydrationFailed,
      failedTargetFile: meshState?.file,
      failedTargetHash: meshState?.assemblyBackgroundErrorMeshHash,
    })) {
      return;
    }
    loadMeshForEntry(selectedEntry).catch((err) => {
      setStatus(ASSET_STATUS.ERROR);
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelMeshLoad,
    selectedEntryRenderAssetFormat,
    isAssemblyView,
    loadMeshForEntry,
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadTargetHash,
    meshState?.file,
    meshState?.assemblyBackgroundErrorMeshHash,
    selectedAssemblyHydrationFailed,
    selectedAssemblyInteractionReady,
    selectedEntry,
    selectedMeshMatches
  ]);


  useEffect(() => {
    if (!selectedEntry) {
      cancelUrdfLoad();
      return;
    }
    if (!isRobotRenderFormat(effectiveRenderFormat)) {
      cancelUrdfLoad();
      return;
    }
    if (!selectedEntryHasUrdf) {
      cancelUrdfLoad();
      setUrdfState(null);
      setUrdfStatus(ASSET_STATUS.PENDING);
      setUrdfError("");
      return;
    }
    if (selectedUrdfMatches) {
      return;
    }
    loadUrdfForEntry(selectedEntry).catch((err) => {
      setUrdfStatus(ASSET_STATUS.ERROR);
      setUrdfError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelUrdfLoad,
    effectiveRenderFormat,
    loadUrdfForEntry,
    selectedEntry,
    selectedEntryHasUrdf,
    selectedUrdfMatches,
    setUrdfError,
    setUrdfState,
    setUrdfStatus
  ]);

  // Stable key over the expanded tree nodes whose topology should be loaded. An assembly's
  // reference state is only a match if it was composed for exactly this expanded set, so expanding
  // a new node re-triggers a load (which fetches only the newly-needed component). A single part
  // has no tree; its loaded key is "*".
  const requestedTopologyKey = isAssemblyView
    ? requestedStepTreeTopologyNodeIds.slice().sort().join("|")
    : "*";
  const selectedReferencesMatch =
    !!referenceState &&
    !!selectedEntry &&
    selectedEntryHasReferences &&
    referenceState.fileRef === fileKey(selectedEntry) &&
    referenceState.referenceHash === buildReferenceCacheKey(selectedEntry) &&
    topologyCompositionKeyMatches(referenceState.loadedTopologyKey, requestedTopologyKey);
  const selectedSelectorRuntime = selectedReferencesMatch ? referenceState?.selectorRuntime || null : null;
  const artifactRevision = buildReferenceCacheKey(selectedEntry);
  const featureTargetScope = `${selectedKey}:${artifactRevision}`;
  const [featureTargetState, setFeatureTargetState] = useState({ scope: featureTargetScope, targets: EMPTY_LIST });
  const visibleFeatureTargets = featureTargetState.scope === featureTargetScope ? featureTargetState.targets : EMPTY_LIST;
  const handleVisibleFeatureTargetsChange = useCallback((targets) => {
    setFeatureTargetState(current => current.scope === featureTargetScope &&
      JSON.stringify(current.targets) === JSON.stringify(targets) ? current : { scope: featureTargetScope, targets });
  }, [featureTargetScope]);
  useEffect(() => {
    setSelectionFilter("all");
    setSelectionFilterNotice("");
    setInspectionHighlight(null);
  }, [selectedKey, artifactRevision]);
  const selectedStepParameterRuntime = useMemo(() => {
    if (
      !selectedStepModuleDefinition ||
      (selectedStepModuleTopologyRequested && !selectedSelectorRuntime)
    ) {
      return null;
    }
    return {
      definition: selectedStepModuleDefinition,
      parameterValues: normalizeStepModuleParameterValues(selectedStepModuleDefinition, stepModuleParameterValues),
      selectorRuntime: selectedSelectorRuntime,
      cadPath: selectedStepModuleDefinition.cadPath || selectedStepModuleCadPath,
      sourceUrl: selectedStepModuleUrl
    };
  }, [
    selectedSelectorRuntime,
    selectedStepModuleCadPath,
    selectedStepModuleDefinition,
    selectedStepModuleTopologyRequested,
    selectedStepModuleUrl,
    stepModuleParameterValues
  ]);
  const selectedDisplayEdgesMatch =
    !!displayEdgeState &&
    !!selectedEntry &&
    selectedEntryHasDisplayEdges &&
    displayEdgeState.fileRef === fileKey(selectedEntry) &&
    displayEdgeState.displayEdgeHash === entryAssetHash(selectedEntry, "displayEdgeTopology");
  const selectedDisplayEdgeRuntime = selectedDisplayEdgesMatch && !retainingPreviousStepMesh
    ? displayEdgeState?.displayEdgeRuntime || null
    : null;
  const selectedStepPartRootActive = !isAssemblyView && expandedStepTreeNodeIds.includes(STEP_MODEL_ROOT_ID);
  const plainStepReferencePickingEnabled =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    !isAssemblyView;
  const topologyCapabilityRequested = selectedStepPartRootActive;
  const plainStepReferencePickingRequested =
    plainStepReferencePickingEnabled &&
    (topologyCapabilityRequested || selectedStepModuleTopologyRequested);
  const assemblyStepTreeTopologyLoadingEnabled =
    !renderSession.enabled &&
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    isAssemblyView &&
    requestedStepTreeTopologyNodeIds.length > 0;
  const selectedStepDisplayEdgesRequested =
    !renderSession.enabled &&
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasDisplayEdges &&
    !displayModeIsWireframe(resolvedScene.display.mode) &&
    (displayModeForcesEdges(resolvedScene.display.mode) || resolvedDisplayEdgeSettings.enabled !== false);
  const selectedTopologyExplicitlyEnabled = largeFileState.selectableTopologyEnabled === true;
  const selectedTopologyLargeByCost = Boolean(
    isLargeStepGlbEntry(selectedEntry) ||
    (selectedMeshMatches && isLargeMeshData(selectedMeshData))
  );
  const selectedTopologyWaitingForMeshCost = Boolean(
    plainStepReferencePickingRequested &&
    !hasStepGlbByteCost(selectedEntry) &&
    !selectedMeshMatches
  );
  const referenceLoadingExplicitlyRequested =
    selectedStepPartRootActive ||
    topologyCapabilityRequested ||
    selectedStepModuleTopologyRequested;
  const selectedTopologyDeferredByCost = Boolean(
    plainStepReferencePickingRequested &&
    selectedTopologyLargeByCost &&
    !selectedTopologyExplicitlyEnabled &&
    !referenceLoadingExplicitlyRequested
  );
  const topLevelReferenceSelectionActive =
    selectedStepPartRootActive ||
    plainStepReferencePickingRequested;
  const referenceLoadingEnabled =
    !renderSession.enabled && (
      selectedStepPartRootActive ||
      assemblyStepTreeTopologyLoadingEnabled ||
      (
        plainStepReferencePickingRequested &&
        !selectedTopologyDeferredByCost &&
        !selectedTopologyWaitingForMeshCost
      )
    );

  useEffect(() => {
    if (renderSession.enabled) {
      cancelReferenceLoad();
      return;
    }
    if (!selectedEntry) {
      cancelReferenceLoad();
      return;
    }
    if (!selectedEntryHasReferences) {
      cancelReferenceLoad();
      setReferenceState(null);
      setReferenceStatus(REFERENCE_STATUS.DISABLED);
      setReferenceError("");
      return;
    }
    if (!referenceLoadingEnabled) {
      cancelReferenceLoad();
      setReferenceState(null);
      setReferenceStatus(REFERENCE_STATUS.IDLE);
      setReferenceError("");
      return;
    }
    if (selectedReferencesMatch) {
      return;
    }
    loadReferencesForEntry(selectedEntry, requestedStepTreeTopologyNodeIds).catch((err) => {
      setReferenceStatus(REFERENCE_STATUS.ERROR);
      setReferenceError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelReferenceLoad,
    isAssemblyView,
    loadReferencesForEntry,
    referenceLoadingEnabled,
    renderSession.enabled,
    requestedStepTreeTopologyNodeIds,
    selectedEntry,
    selectedEntryHasReferences,
    selectedReferencesMatch
  ]);

  useEffect(() => {
    if (renderSession.enabled) {
      cancelDisplayEdgeLoad();
      return;
    }
    if (!selectedEntry) {
      cancelDisplayEdgeLoad();
      return;
    }
    if (!selectedStepDisplayEdgesRequested) {
      cancelDisplayEdgeLoad();
      setDisplayEdgeState(null);
      setDisplayEdgeStatus(REFERENCE_STATUS.IDLE);
      setDisplayEdgeError("");
      return;
    }
    if (selectedDisplayEdgesMatch) {
      return;
    }
    loadDisplayEdgesForEntry(selectedEntry).catch((err) => {
      setDisplayEdgeStatus(REFERENCE_STATUS.ERROR);
      setDisplayEdgeError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelDisplayEdgeLoad,
    loadDisplayEdgesForEntry,
    renderSession.enabled,
    selectedDisplayEdgesMatch,
    selectedEntry,
    selectedStepDisplayEdgesRequested,
    setDisplayEdgeError,
    setDisplayEdgeState,
    setDisplayEdgeStatus
  ]);

  const {
    currentReferences,
    activeReferenceMap,
    selectedReferences,
    selectedParts,
    hoveredReferenceId,
    hoveredPartId,
    visibleReferences
  } = useCadWorkspaceSelectors({
    selectedEntry,
    selectedReferencesMatch,
    referenceState,
    isAssemblyView,
    supportsPartSelection,
    assemblyParts,
    assemblyPartMap,
    inspectedAssemblyNodeId: "",
    inspectedAssemblyPartTopologyReferences: [],
    selectedReferenceIds,
    selectedPartIds,
    hoveredListReferenceId,
    hoveredModelReferenceId,
    hoveredListPartId,
    hoveredModelPartId
  });

  // The Reference inspector shows every selected element: topology references
  // (faces/edges/shapes) plus selected components and subassemblies.
  const selectedReferenceItems = useMemo(
    () => [...(selectedReferences || []), ...(selectedParts || [])],
    [selectedReferences, selectedParts]
  );

  useCadWorkspaceSelection({
    isAssemblyView,
    supportsPartSelection,
    assemblyPartsLoaded,
    selectedEntryHasReferences,
    setSelectedReferenceIds,
    selectedReferenceIdsRef,
    setHoveredListReferenceId,
    setHoveredModelReferenceId,
    assemblyParts,
    validAssemblyPartIds: validAssemblySelectionIds,
    validHiddenPartIds: validAssemblyLeafIds,
    selectedPartIdsRef,
    setSelectedPartIds,
    parseAssemblyPartReferenceSelectionId,
    setHiddenPartIds,
    setHoveredListPartId,
    setHoveredModelPartId
  });

  useEffect(() => {
    const rootId = String(stepTreeRoot?.id || "").trim();
    if (!rootId) {
      setExpandedStepTreeNodeIds((current) => (current.length ? [] : current));
      return;
    }
    const validIds = new Set(validAssemblySelectionIds);
    setExpandedStepTreeNodeIds((current) => {
      const filtered = current.filter((id) => validIds.has(id));
      return orderedStringListEqual(filtered, current) ? current : filtered;
    });
  }, [selectedKey, stepTreeRoot, validAssemblySelectionIds]);

  const isFaceReference = useCallback((reference) => (
    String(reference?.selectorType || "").trim() === "face"
  ), []);
  const isEdgeReference = useCallback((reference) => (
    String(reference?.selectorType || "").trim() === "edge"
  ), []);
  const isVertexReference = useCallback((reference) => (
    String(reference?.selectorType || "").trim() === "vertex"
  ), []);
  const isViewerTopologyReference = useCallback((reference) => (
    isFaceReference(reference) ||
    isEdgeReference(reference) ||
    isVertexReference(reference)
  ), [
    isEdgeReference,
    isFaceReference,
    isVertexReference
  ]);
  const isStepTopologyReference = useCallback((reference) => {
    const selectorType = String(reference?.selectorType || "").trim();
    return selectorType === "occurrence" ||
      selectorType === "shape" ||
      selectorType === "face" ||
      selectorType === "edge" ||
      selectorType === "vertex";
  }, []);
  const referencePartId = useCallback((reference) => {
    const explicitPartId = String(reference?.partId || "").trim();
    if (explicitPartId) {
      return explicitPartId;
    }
    if (!isAssemblyView && reference?.selectorType === "occurrence") return STEP_MODEL_ROOT_ID;
    return parseAssemblyPartReferenceSelectionId(reference?.id)?.partId || "";
  }, [isAssemblyView]);

  const assemblyStepTreeTopologyReferences = useMemo(() => {
    if (!supportsTopology || !isAssemblyView || !selectedReferencesMatch) {
      return [];
    }
    return assignStepTreeTopologyReferencePartIds(stepTreeRoot, currentReferences);
  }, [
    currentReferences,
    isAssemblyView,
    supportsTopology,
    selectedReferencesMatch,
    stepTreeRoot
  ]);
  const focusedAssemblyRenderPartIds = useMemo(() => {
    if (!isAssemblyView || !focusedAssemblyNodeIds.length) {
      return [];
    }
    return uniqueStringList(
      focusedAssemblyNodeIds
        .flatMap((nodeId) => [
          nodeId,
          ...renderPartIdsForAssemblySelection(nodeId)
        ])
        .map((partId) => String(partId || "").trim())
        .filter(Boolean)
    );
  }, [
    focusedAssemblyNodeIds,
    isAssemblyView,
    renderPartIdsForAssemblySelection
  ]);
  const focusedAssemblyPartReferences = useMemo(() => {
    if (!isAssemblyView || !focusedAssemblyRenderPartIds.length) {
      return [];
    }
    const focusedPartIdSet = new Set(focusedAssemblyRenderPartIds);
    return assemblyStepTreeTopologyReferences.filter((reference) => (
      focusedPartIdSet.has(referencePartId(reference)) &&
      isStepTopologyReference(reference)
    ));
  }, [
    assemblyStepTreeTopologyReferences,
    focusedAssemblyRenderPartIds,
    isAssemblyView,
    isStepTopologyReference,
    referencePartId
  ]);
  const effectiveVisibleReferences = useMemo(() => {
    if (isAssemblyView && focusedAssemblyTopologyActive) {
      return focusedAssemblyPartReferences;
    }
    return visibleReferences;
  }, [
    focusedAssemblyPartReferences,
    focusedAssemblyTopologyActive,
    isAssemblyView,
    visibleReferences
  ]);
  const stepTreeTopologyReferences = useMemo(() => {
    if (!supportsTopology) {
      return [];
    }
    if (isAssemblyView) {
      return requestedStepTreeTopologyNodeIds.length
        ? assemblyStepTreeTopologyReferences
        : [];
    }
    return currentReferences;
  }, [
    assemblyStepTreeTopologyReferences,
    currentReferences,
    isAssemblyView,
    supportsTopology,
    requestedStepTreeTopologyNodeIds
  ]);
  const displayStepTreeRoot = useMemo(() => buildStepTreeRootWithTopology({
    root: stepTreeRoot,
    references: stepTreeTopologyReferences,
    fallbackPartId: isAssemblyView ? "" : STEP_MODEL_ROOT_ID,
    topologyPartIds: isAssemblyView ? requestedStepTreeTopologyNodeIds : null
  }), [
    isAssemblyView,
    requestedStepTreeTopologyNodeIds,
    stepTreeRoot,
    stepTreeTopologyReferences
  ]);
  const topologyTarget = useMemo(() => {
    if (!isAssemblyView) return { id: STEP_MODEL_ROOT_ID, partId: "", label: selectedEntry?.name || selectedEntry?.label || "Model" };
    const ids = uniqueStringList([...selectedPartIds, ...selectedReferences.map(referencePartId)]);
    if (ids.length !== 1 || !loadableStepTreeTopologyNodeIdSet.has(ids[0])) return null;
    const node = copyableStepTreeNodeForWorkspace({ assemblyPartMap, displayStepTreeRoot, stepTreeRoot, nodeId: ids[0] });
    return { id: ids[0], partId: ids[0], label: node?.displayName || node?.name || ids[0] };
  }, [isAssemblyView, selectedEntry, selectedPartIds, selectedReferences, referencePartId, loadableStepTreeTopologyNodeIdSet, assemblyPartMap, displayStepTreeRoot, stepTreeRoot]);
  const isolatedStepTreeSelectableNodeIds = useMemo(() => {
    if (!isAssemblyView || !focusedAssemblyNodeIds.length) {
      return null;
    }
    const treeRootForIsolation = displayStepTreeRoot || stepTreeRoot;
    return uniqueStringList(
      focusedAssemblyNodeIds.flatMap((nodeId) => collectStepTreeSubtreeIds(treeRootForIsolation, nodeId))
    );
  }, [
    displayStepTreeRoot,
    focusedAssemblyNodeIds,
    isAssemblyView,
    stepTreeRoot
  ]);
  const stepTreeCopyReferenceMap = useMemo(
    () => buildStepTreeCopyReferenceMap(displayStepTreeRoot),
    [displayStepTreeRoot]
  );
  const effectiveSelectorRuntime = retainingPreviousStepMesh ? null : selectedSelectorRuntime;

  const effectiveActiveReferenceMap = useMemo(() => {
    const map = new Map(activeReferenceMap);
    for (const reference of Array.from(map.values())) {
      addReferenceLookupKeys(map, reference);
    }
    for (const reference of effectiveVisibleReferences) {
      addReferenceLookupKeys(map, reference);
    }
    return map;
  }, [activeReferenceMap, effectiveVisibleReferences]);

  const renderPartIdsForWholeTopologyReference = useCallback((referenceId) => {
    const normalizedReferenceId = String(referenceId || "").trim();
    if (!normalizedReferenceId) {
      return [];
    }
    const reference = effectiveActiveReferenceMap.get(normalizedReferenceId);
    const selectorType = String(reference?.selectorType || "").trim();
    if (selectorType !== "occurrence" && selectorType !== "shape") {
      return [];
    }
    const partId = referencePartId(reference);
    if (isAssemblyView) {
      return partId ? renderPartIdsForAssemblySelection(partId) : [];
    }
    const renderPartId = partId && partId !== STEP_MODEL_ROOT_ID
      ? partId
      : STEP_MODEL_RENDER_PART_ID;
    return renderPartId ? [renderPartId] : [];
  }, [
    effectiveActiveReferenceMap,
    isAssemblyView,
    referencePartId,
    renderPartIdsForAssemblySelection
  ]);

  const viewerPickableReferences = useMemo(() => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      return [];
    }
    if (isAssemblyView) return referencesForExpandedStepTree(
      assemblyStepTreeTopologyReferences, expandedStepTreeTopologyNodeIds, referencePartId
    );
    return expandedStepTreeNodeIds.includes(STEP_MODEL_ROOT_ID) ? effectiveVisibleReferences : [];
  }, [
    assemblyStepTreeTopologyReferences,
    effectiveVisibleReferences,
    expandedStepTreeTopologyNodeIds,
    expandedStepTreeNodeIds,
    referencePartId,
    isAssemblyView,
    stepInteractionBlocked,
    stepModuleTreeSelectionDisabled,
  ]);
  const viewerPickableFaces = useMemo(
    () => viewerPickableReferences.filter((reference) => isFaceReference(reference)),
    [isFaceReference, viewerPickableReferences]
  );
  const viewerPickableEdges = useMemo(
    () => viewerPickableReferences.filter((reference) => isEdgeReference(reference)),
    [isEdgeReference, viewerPickableReferences]
  );
  const viewerPickableVertices = EMPTY_LIST;
  const referenceSelectionStatus = referenceStatus;
  const hasViewerPickableTopology = Boolean(
    viewerPickableFaces.length ||
    viewerPickableEdges.length ||
    viewerPickableVertices.length
  );
  // Measuring needs a mesh to hit. Topology, when loaded, upgrades STEP hits
  // from free points to edge and face snaps.
  const measureModeActive = effectiveSupportsMeasure &&
    tabToolMode === TAB_TOOL_MODE.MEASURE &&
    Boolean(selectedMeshData) &&
    !stepInteractionBlocked &&
    !viewerLoading;
  const [measureSelectionFilter, setMeasureSelectionFilter] = useState("all");
  useEffect(() => setMeasureSelectionFilter("all"), [selectedKey]);
  const [measureRulerState, setMeasureRulerState] = useState(null);
  const [activeMeasureId, setActiveMeasureId] = useState("");
  const handleMeasurePick = useCallback((pick) => {
    if (measureSelectionFilter === "edges" && pick?.snapKind !== "edge") return;
    if (measureSelectionFilter === "faces" && pick?.snapKind !== "face") return;
    setMeasureRulerState((current) => applyMeasureRulerPick(current, pick));
  }, [measureSelectionFilter]);
  const handleMeasureHoverPoint = useCallback((hover) => {
    const accepted = (measureSelectionFilter !== "edges" || hover?.snapKind === "edge") &&
      (measureSelectionFilter !== "faces" || hover?.snapKind === "face");
    setMeasureRulerState((current) => applyMeasureRulerHover(current, accepted ? hover : null));
  }, [measureSelectionFilter]);
  const handleMeasureDelete = useCallback((measurementId) => {
    setMeasureRulerState((current) => applyMeasureRulerDelete(current, measurementId));
  }, []);
  const handleMeasureCancelDraft = useCallback(() => {
    setMeasureRulerState((current) => cancelMeasureRulerDraft(current));
  }, []);
  const handleMeasureClear = useCallback(() => {
    setMeasureRulerState((current) => clearMeasureRulerMeasurements(current));
  }, []);
  const measureMeasurements = measureRulerState?.measurements || EMPTY_LIST;
  // Only rescue the highlight when the row it points at is gone (deleted or
  // cleared). Taking a new measurement promotes it separately, below; doing it
  // here as well would fight the user's own row clicks, because a live draft
  // rewrites this state on every hover tick.
  useEffect(() => {
    setActiveMeasureId((current) => {
      if (current && measureMeasurements.some((item) => item.id === current)) {
        return current;
      }
      return measureMeasurements.length ? measureMeasurements[measureMeasurements.length - 1].id : "";
    });
  }, [measureMeasurements]);
  useEffect(() => {
    setMeasureRulerState((current) => measureRulerStateForChange(current, { entryChanged: true }));
  }, [selectedKey, selectedEntry?.hash]);
  useEffect(() => {
    setMeasureRulerState((current) => measureRulerStateForChange(current, { toolActive: measureModeActive }));
    if (measureModeActive) setInspectionHighlight(null);
  }, [measureModeActive]);
  // A new measurement reveals the tab that holds it. Re-appending (rather than
  // just ensuring membership) moves it to the end, and last-in-pane wins tab
  // resolution — so it also wins the pane back if the user has since clicked Tree.
  const measurementCountRef = useRef(0);
  useEffect(() => {
    const count = measureMeasurements.length;
    const grew = count > measurementCountRef.current;
    measurementCountRef.current = count;
    if (!grew) {
      return;
    }
    setActiveMeasureId(measureMeasurements[count - 1].id);
    if (!renderedSelectedFileSheetSectionIds.includes(FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS)) {
      return;
    }
    setTabToolsOpen(true);
    setFileSheetOpenSectionIds((current) => normalizeFileSheetOpenSectionIds(
      [
        ...(Array.isArray(current) ? current : [])
          .filter((id) => id !== FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS),
        FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS
      ],
      renderedSelectedFileSheetSectionIds
    ));
  }, [measureMeasurements, renderedSelectedFileSheetSectionIds, setTabToolsOpen]);

  const filteredViewerReferences = useMemo(() => filterSelectionReferences(viewerPickableReferences, selectionFilter),
    [viewerPickableReferences, selectionFilter]);
  const filteredViewerFaces = useMemo(() => filteredViewerReferences.filter(isFaceReference), [filteredViewerReferences, isFaceReference]);
  const filteredViewerEdges = useMemo(() => filteredViewerReferences.filter(isEdgeReference), [filteredViewerReferences, isEdgeReference]);
  const measureToolDisabled = viewerLoading || !selectedMeshData || !supportsMeasure;
  const topologySelectionActive =
    (isAssemblyView && requestedStepTreeTopologyNodeIds.length > 0) ||
    topLevelReferenceSelectionActive;
  const referenceSelectionUnavailable = stepModuleTreeSelectionDisabled || (
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    topologySelectionActive &&
    !viewerInAssemblyMode &&
    !selectedTopologyDeferredByCost &&
    (
      referenceSelectionStatus === REFERENCE_STATUS.DISABLED ||
      referenceSelectionStatus === REFERENCE_STATUS.ERROR ||
      (
        referenceSelectionStatus === REFERENCE_STATUS.READY &&
        !!effectiveSelectorRuntime &&
        !hasViewerPickableTopology
      )
    )
  );
  const referenceSelectionPending = (
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    topologySelectionActive &&
    !viewerInAssemblyMode &&
    !selectedTopologyDeferredByCost &&
    !referenceSelectionUnavailable &&
    !retainedPreviousStepMeshError &&
    (
      stepInteractionBlocked ||
      referenceSelectionStatus === REFERENCE_STATUS.IDLE ||
      referenceSelectionStatus === REFERENCE_STATUS.LOADING ||
      !effectiveSelectorRuntime
    )
  );
  const loading = viewerLoadingState({
    busy: effectiveViewerLoading || selectedMeshPartial || presentationPending,
    editPending: ["submitted", "queued", "building"].includes(editingPreview.state?.state) && !editingPreview.state?.saved,
    previousView: completedViewFile.current === selectedKey && Boolean(selectedMeshData || selectedEntryIsDrawingDocument),
    currentPreview: currentPreviewVisible,
    error: viewerAlert || (!selectedMeshData && catalogError) || missingFileRef,
    renderMode: renderSession.enabled,
    progress: selectedLoadProgress || (editingPreview.state.phase ? { phase: editingPreview.state.phase, detail: editingPreview.state.detail } : null),
    finding: !catalogHydrated || selectedCatalogPending || fileParamSelectionPending,
    preparing: presentationPending && !effectiveViewerLoading && !selectedMeshPartial,
  });
  const annotationAlert = buildViewerAnnotationAlert(selectedEntry);
  const fileStatus = resolveFileStatus({
    hasFile: Boolean(selectedEntry || explicitFileParam),
    error: viewerAlert || (catalogError && !selectedMeshData ? catalogError : null) || (missingFileRef
      ? {
        title: "File unavailable", message: "The selected file could not be found.",
        tooltip: "This file isn’t in the folder served by the viewer. Check the file path or choose another file.",
      }
      : null) || annotationAlert,
    opening: loading.opening,
    updating: loading.updating,
    loadingProgress: loading.progress,
    renderMode: renderSession.enabled,
    editingState: editingAvailable ? editingPreview.state : null,
    showingPreview: currentPreviewVisible,
    qualityStatus: viewportQualityStatus,
    hasGeometry: Boolean((selectedMeshData && !selectedMeshPartial) || selectedEntryIsDrawingDocument),
    reloading: viewerReloading
  });
  const fileStatusAlert = resolveFileStatusAlert(fileStatus, viewerAlert, annotationAlert);
  const currentFileStatusAlertKey = fileStatusAlertKey(fileKey(selectedEntry), fileStatusAlert);
  useEffect(() => {
    setViewerAlertOpen(false);
  }, [currentFileStatusAlertKey]);
  const filenameLoadActivity = useMemo(() => fileStatus ? { loading: fileStatus.busy === true, label: fileStatus.label, title: fileStatus.title, tone: fileStatus.tone, onActivate: fileStatusAlert ? () => setViewerAlertOpen(true) : undefined } : null, [fileStatus?.busy, fileStatus?.label, fileStatus?.title, fileStatus?.tone, Boolean(fileStatusAlert)]);
  useEffect(() => { onActivityChange?.(filenameLoadActivity); return () => onActivityChange?.(null); }, [filenameLoadActivity, onActivityChange]);
  const selectedWholeTopologyReferencePartIds = useMemo(() => (
    uniqueStringList(
      selectedReferenceIds.flatMap((referenceId) => renderPartIdsForWholeTopologyReference(referenceId))
    )
  ), [
    renderPartIdsForWholeTopologyReference,
    selectedReferenceIds
  ]);
  const hoveredWholeTopologyReferencePartIds = useMemo(() => (
    uniqueStringList(
      [hoveredListReferenceId, hoveredModelReferenceId]
        .flatMap((referenceId) => renderPartIdsForWholeTopologyReference(referenceId))
    )
  ), [
    hoveredListReferenceId,
    hoveredModelReferenceId,
    renderPartIdsForWholeTopologyReference
  ]);
  const viewerSelectedPartIds = useMemo(() => {
    if (!isAssemblyView) {
      return uniqueStringList([
        ...(selectedPartIds.includes(STEP_MODEL_ROOT_ID) ? [STEP_MODEL_RENDER_PART_ID] : []),
        ...selectedWholeTopologyReferencePartIds,
      ]);
    }
    return uniqueStringList(
      [
        ...selectedPartIds.flatMap((id) => {
          const normalizedId = String(id || "").trim();
          return renderPartIdsForAssemblySelection(
            normalizedId,
            selectedRenderPartIdByAssemblyPartId[normalizedId]
          );
        }),
        ...selectedWholeTopologyReferencePartIds
      ]
    );
  }, [
    focusedAssemblyNodeIds,
    isAssemblyView,
    renderPartIdsForAssemblySelection,
    selectedPartIds,
    selectedRenderPartIdByAssemblyPartId,
    selectedWholeTopologyReferencePartIds
  ]);
  const viewerHoveredPartIds = useMemo(() => {
    const contextMenuNodeId = String(viewerContextMenu?.nodeId || "").trim();
    if (isAssemblyView && contextMenuNodeId) {
      const contextRenderPartId = String(viewerContextMenu?.renderPartId || "").trim();
      const highlightedPartIds = renderPartIdsForAssemblySelection(contextMenuNodeId, contextRenderPartId);
      return highlightedPartIds.length ? highlightedPartIds : contextMenuNodeId;
    }
    if (hoveredWholeTopologyReferencePartIds.length) {
      return hoveredWholeTopologyReferencePartIds;
    }
    if (!isAssemblyView || !hoveredPartId) {
      return hoveredPartId;
    }
    const normalizedTreeHoveredPartId = String(hoveredListPartId || "").trim();
    if (normalizedTreeHoveredPartId) {
      const highlightedPartIds = renderPartIdsForAssemblySelection(normalizedTreeHoveredPartId);
      return highlightedPartIds.length ? highlightedPartIds : normalizedTreeHoveredPartId;
    }
    const normalizedHoveredPartId = String(hoveredModelPartId || hoveredPartId || "").trim();
    const hoveredSelectionId = resolvePickedAssemblyPartId(normalizedHoveredPartId);
    const highlightedPartIds = renderPartIdsForAssemblySelection(hoveredSelectionId, normalizedHoveredPartId);
    return highlightedPartIds.length ? highlightedPartIds : hoveredPartId;
  }, [
    hoveredPartId,
    hoveredListPartId,
    hoveredModelPartId,
    hoveredWholeTopologyReferencePartIds,
    isAssemblyView,
    renderPartIdsForAssemblySelection,
    resolvePickedAssemblyPartId,
    viewerContextMenu
  ]);
  const effectiveHoveredReferenceId = String(viewerContextMenu?.referenceId || "").trim() || hoveredReferenceId;
  const viewerFocusedPartIds = useMemo(() => {
    return focusedAssemblyRenderPartIds;
  }, [
    focusedAssemblyRenderPartIds
  ]);
  const viewerHiddenPartIds = useMemo(() => {
    return hiddenPartIds;
  }, [hiddenPartIds]);
  const viewerAssemblyRenderParts = useMemo(() => {
    if (!isAssemblyView || !selectedAssemblyInteractionReady) {
      return EMPTY_LIST;
    }
    return assemblyLeafParts;
  }, [
    assemblyLeafParts,
    isAssemblyView,
    selectedAssemblyInteractionReady
  ]);

  const clearTrackedUrdfGroupStateForFile = useCallback((fileRef) => {
    const normalizedFileRef = String(fileRef || "").trim();
    if (!normalizedFileRef) {
      return;
    }
    setSelectedUrdfGroupStateIdByFileRef((current) => {
      if (!current?.[normalizedFileRef]) {
        return current;
      }
      const next = { ...current };
      delete next[normalizedFileRef];
      return next;
    });
  }, []);

  const cancelUrdfTrajectoryOnly = useCallback(() => {
    const playback = urdfTrajectoryPlaybackRef.current;
    playback.token += 1;
    if (playback.frameId && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(playback.frameId);
    }
    playback.frameId = 0;
  }, []);

  const cancelUrdfJointAnimation = useCallback(() => {
    const jointAnimation = urdfJointAnimationRef.current;
    jointAnimation.token += 1;
    if (jointAnimation.frameId && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(jointAnimation.frameId);
    }
    jointAnimation.frameId = 0;
    jointAnimation.mode = "";
    jointAnimation.fileRef = "";
    jointAnimation.targetValues = null;
    jointAnimation.currentValues = null;
    jointAnimation.lastTimestampMs = 0;
  }, []);

  const cancelUrdfTrajectoryPlayback = useCallback(() => {
    cancelUrdfTrajectoryOnly();
    cancelUrdfJointAnimation();
  }, [cancelUrdfJointAnimation, cancelUrdfTrajectoryOnly]);

  const animateUrdfJointValues = useCallback((fileRef, startJointValues, targetJointValues, options = {}) => {
    const normalizedFileRef = String(fileRef || "").trim();
    if (!normalizedFileRef) {
      return;
    }
    const startValues = cloneJointValueMap(startJointValues);
    const finalValues = cloneJointValueMap(targetJointValues);
    cancelUrdfTrajectoryPlayback();
    // Animation off writes the target in this frame, exactly as an unchanged pose does.
    if (
      typeof requestAnimationFrame !== "function" ||
      toFiniteNumber(options?.durationMs, poseTransitionDurationMsRef.current) <= 0 ||
      jointValueMapsClose(startValues, finalValues)
    ) {
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedFileRef]: finalValues
      }));
      return;
    }
    const playback = urdfJointAnimationRef.current;
    const token = playback.token + 1;
    playback.token = token;
    const startedAtMs = animationNowMs();
    const durationMs = Math.max(toFiniteNumber(options?.durationMs, poseTransitionDurationMsRef.current), 1);
    const step = (timestamp) => {
      if (urdfJointAnimationRef.current.token !== token) {
        return;
      }
      const elapsedMs = Math.max(toFiniteNumber(timestamp, animationNowMs()) - startedAtMs, 0);
      const progress = Math.min(elapsedMs / durationMs, 1);
      const interpolation = interpolateUrdfJointValues(
        startValues,
        finalValues,
        progress,
        undefined,
        selectedUrdfContinuousJointNames
      );
      const nextValues = interpolation.done || progress >= 1
        ? finalValues
        : {
          ...startValues,
          ...interpolation.values
        };
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedFileRef]: nextValues
      }));
      if (interpolation.done || progress >= 1) {
        urdfJointAnimationRef.current.frameId = 0;
        return;
      }
      urdfJointAnimationRef.current.frameId = requestAnimationFrame(step);
    };
    playback.frameId = requestAnimationFrame(step);
  }, [
    cancelUrdfTrajectoryPlayback,
    selectedUrdfContinuousJointNames
  ]);

  const followUrdfJointValues = useCallback((fileRef, currentJointValues, targetJointValues, options = {}) => {
    const normalizedFileRef = String(fileRef || "").trim();
    if (!normalizedFileRef) {
      return;
    }
    const currentValues = cloneJointValueMap(currentJointValues);
    const finalValues = cloneJointValueMap(targetJointValues);
    const smoothingMs = Math.max(toFiniteNumber(options?.durationMs, URDF_JOINT_ANIMATION_FOLLOW_MS), 1);

    cancelUrdfTrajectoryOnly();
    if (
      typeof requestAnimationFrame !== "function" ||
      jointValueMapsClose(currentValues, finalValues)
    ) {
      cancelUrdfJointAnimation();
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedFileRef]: finalValues
      }));
      return;
    }

    const activeAnimation = urdfJointAnimationRef.current;
    if (
      activeAnimation.frameId &&
      activeAnimation.mode === "follow" &&
      activeAnimation.fileRef === normalizedFileRef
    ) {
      activeAnimation.targetValues = finalValues;
      activeAnimation.smoothingMs = smoothingMs;
      return;
    }

    cancelUrdfJointAnimation();
    const playback = urdfJointAnimationRef.current;
    const token = playback.token + 1;
    playback.token = token;
    playback.mode = "follow";
    playback.fileRef = normalizedFileRef;
    playback.currentValues = currentValues;
    playback.targetValues = finalValues;
    playback.smoothingMs = smoothingMs;
    playback.lastTimestampMs = animationNowMs();

    const step = (timestamp) => {
      const animation = urdfJointAnimationRef.current;
      if (animation.token !== token) {
        return;
      }
      const timeMs = toFiniteNumber(timestamp, animationNowMs());
      const deltaMs = Math.max(timeMs - toFiniteNumber(animation.lastTimestampMs, timeMs), 0);
      animation.lastTimestampMs = timeMs;
      const baseValues = cloneJointValueMap(animation.currentValues);
      const targetValues = cloneJointValueMap(animation.targetValues);
      const advanced = advanceUrdfJointValues(
        baseValues,
        targetValues,
        deltaMs,
        animation.smoothingMs,
        undefined,
        selectedUrdfContinuousJointNames
      );
      const nextValues = advanced.done
        ? targetValues
        : {
          ...baseValues,
          ...advanced.values
        };
      animation.currentValues = nextValues;
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedFileRef]: nextValues
      }));
      if (advanced.done || jointValueMapsClose(nextValues, targetValues)) {
        animation.frameId = 0;
        animation.mode = "";
        animation.fileRef = "";
        animation.currentValues = null;
        animation.targetValues = null;
        animation.lastTimestampMs = 0;
        return;
      }
      animation.frameId = requestAnimationFrame(step);
    };

    playback.frameId = requestAnimationFrame(step);
  }, [
    cancelUrdfJointAnimation,
    cancelUrdfTrajectoryOnly,
    selectedUrdfContinuousJointNames
  ]);

  const playUrdfTrajectory = useCallback((fileRef, baseJointValues, trajectory, finalJointValues) => {
    const normalizedFileRef = String(fileRef || "").trim();
    if (!normalizedFileRef) {
      return;
    }
    cancelUrdfTrajectoryPlayback();
    const points = Array.isArray(trajectory?.points) ? trajectory.points : [];
    const durationSec = points.length
      ? toFiniteNumber(points[points.length - 1].timeFromStartSec, 0)
      : 0;
    if (!points.length || durationSec <= 0 || typeof requestAnimationFrame !== "function") {
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedFileRef]: cloneJointValueMap(finalJointValues)
      }));
      return;
    }
    const playback = urdfTrajectoryPlaybackRef.current;
    const token = playback.token + 1;
    playback.token = token;
    const baseValues = cloneJointValueMap(baseJointValues);
    const finalValues = cloneJointValueMap(finalJointValues);
    const startedAtMs = animationNowMs();
    const step = (timestamp) => {
      if (urdfTrajectoryPlaybackRef.current.token !== token) {
        return;
      }
      const elapsedSec = Math.max((toFiniteNumber(timestamp, animationNowMs()) - startedAtMs) / 1000, 0);
      const done = elapsedSec >= durationSec;
      const nextValues = done
        ? finalValues
        : interpolateTrajectoryJointValues(trajectory, elapsedSec, baseValues);
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedFileRef]: nextValues
      }));
      if (done) {
        urdfTrajectoryPlaybackRef.current.frameId = 0;
        return;
      }
      urdfTrajectoryPlaybackRef.current.frameId = requestAnimationFrame(step);
    };
    playback.frameId = requestAnimationFrame(step);
  }, [cancelUrdfTrajectoryPlayback]);

  useEffect(() => () => {
    cancelUrdfTrajectoryPlayback();
  }, [cancelUrdfTrajectoryPlayback]);


  const handleUrdfJointValueChange = useCallback((joint, nextValueDeg, options = {}) => {
    const jointName = String(joint?.name || "").trim();
    if (!selectedUrdfFileRef || !jointName) {
      return;
    }
    const clampedValueDeg = clampJointValueDeg(joint, nextValueDeg);
    const currentValueDeg = toFiniteNumber(selectedUrdfJointValues?.[jointName], joint?.defaultValueDeg ?? 0);
    if (Math.abs(clampedValueDeg - currentValueDeg) <= URDF_JOINT_ANIMATION_EPSILON) {
      return;
    }
    const nextJointValues = {
      ...selectedUrdfJointValues,
      [jointName]: clampedValueDeg
    };
    if (options?.scrub) {
      followUrdfJointValues(
        selectedUrdfFileRef,
        selectedUrdfJointValues,
        nextJointValues,
        { durationMs: URDF_JOINT_ANIMATION_FOLLOW_MS }
      );
    } else {
      animateUrdfJointValues(
        selectedUrdfFileRef,
        selectedUrdfJointValues,
        nextJointValues,
        { durationMs: URDF_JOINT_ANIMATION_FOLLOW_MS }
      );
    }
    clearTrackedUrdfGroupStateForFile(selectedUrdfFileRef);
  }, [
    animateUrdfJointValues,
    clearTrackedUrdfGroupStateForFile,
    followUrdfJointValues,
    selectedUrdfFileRef,
    selectedUrdfJointValues,
  ]);
  const handleResetUrdfPose = useCallback(() => {
    if (!selectedUrdfFileRef) {
      return;
    }
    cancelUrdfTrajectoryPlayback();
    clearTrackedUrdfGroupStateForFile(selectedUrdfFileRef);
    animateUrdfJointValues(selectedUrdfFileRef, selectedUrdfJointValues, defaultSelectedUrdfJointValues);
  }, [
    animateUrdfJointValues,
    cancelUrdfTrajectoryPlayback,
    clearTrackedUrdfGroupStateForFile,
    defaultSelectedUrdfJointValues,
    selectedUrdfFileRef,
    selectedUrdfJointValues,
  ]);
  const handleSelectUrdfGroupState = useCallback((groupState) => {
    if (!selectedUrdfFileRef || !groupState?.jointValuesByName || typeof groupState.jointValuesByName !== "object") {
      return;
    }
    cancelUrdfTrajectoryPlayback();
    const groupStateJointValues = cloneJointValueMap(groupState.jointValuesByName);
    if (!Object.keys(groupStateJointValues).length) {
      return;
    }
    const nextJointValues = {
      ...selectedUrdfJointValues,
      ...groupStateJointValues
    };
    const groupStateId = String(groupState?.id || "").trim();
    if (groupStateId) {
      setSelectedUrdfGroupStateIdByFileRef((current) => ({
        ...current,
        [selectedUrdfFileRef]: groupStateId
      }));
    }
    animateUrdfJointValues(selectedUrdfFileRef, selectedUrdfJointValues, nextJointValues);
  }, [
    animateUrdfJointValues,
    cancelUrdfTrajectoryPlayback,
    selectedUrdfFileRef,
    selectedUrdfJointValues,
  ]);


  const handleCopyUrdfJointAngles = useCallback(async () => {
    setScreenshotStatus("");
    if (!movableUrdfJoints.length) {
      setCopyStatus("No movable joints are available");
      return;
    }
    try {
      await host.clipboard.writeText(buildUrdfJointAnglesCopyText(movableUrdfJoints, selectedUrdfJointValues));
      setCopyStatus(selectedEntrySourceFormat === RENDER_FORMAT.SDF ? "Copied joint values" : "Copied joint angles");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard write failed");
    }
  }, [movableUrdfJoints, selectedEntrySourceFormat, selectedUrdfJointValues]);
  const copySelectionPayload = useMemo(() => {
    const selectedReferencesForCopy = selectedReferenceIds
      .map((id) => (
        stepTreeCopyReferenceMap.get(id) ||
        effectiveActiveReferenceMap.get(id) ||
        copyReferenceForRawSelectorSelection(id, "topology")
      ))
      .filter(Boolean);
    if (!isAssemblyView && selectedPartIds.includes(STEP_MODEL_ROOT_ID)) {
      const wholeStepEntryReference = buildWholeStepEntryCopyReference(selectedEntry);
      if (wholeStepEntryReference) {
        selectedReferencesForCopy.push(wholeStepEntryReference);
      }
    }
    const selectedPartReferencesForCopy = selectedPartIds
      .map((id) => (
        copyReferenceForRawSelectorSelection(id, "assembly-part") ||
        stepTreeCopyReferenceMap.get(id) ||
        copyReferenceForStepTreeNodeSelection(
          copyableStepTreeNodeForWorkspace({
            assemblyPartMap,
            displayStepTreeRoot,
            stepTreeRoot,
            nodeId: id
          }),
          id,
          "assembly-part"
        )
      ))
      .filter(Boolean);
    return copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
      references: [
        ...selectedReferencesForCopy,
        ...selectedPartReferencesForCopy
      ],
      parts: [],
      entry: selectedEntry
    }), {
      selectedReferenceIds,
      selectedPartIds,
      copyReferenceMap: stepTreeCopyReferenceMap
    });
  }, [
    assemblyPartMap,
    displayStepTreeRoot,
    effectiveActiveReferenceMap,
    selectedEntry,
    selectedPartIds,
    selectedReferenceIds,
    stepTreeCopyReferenceMap,
    stepTreeRoot
  ]);
  // Every copied line funnels through here, from all three of the copy builders above and the
  // selector runtime, so the file prefix is applied once at this point rather than threaded
  // through each of them. withFileRefPrefix is idempotent, so lines that already carry one
  // (parts and mates, which are built from the entry) pass through untouched.
  const canonicalCopySelectionLines = useMemo(
    () => copySelectionPayload.lines
      .map((line) => canonicalCadRefCopyText(line))
      .map((line) => withFileRefPrefix(line, selectedEntry?.fileRefPrefix))
      .filter(Boolean),
    [copySelectionPayload.lines, selectedEntry]
  );
  const copyButtonLabel = useMemo(
    () => buildSelectionCopyButtonLabel(canonicalCopySelectionLines, { count: copySelectionPayload.copiedCount }),
    [canonicalCopySelectionLines, copySelectionPayload.copiedCount]
  );
  // Shown instead of the ref when the ref will not fit. CadRenderPane decides that by
  // measuring, since whether it fits depends on the viewport, not the string.
  const copyButtonCountLabel = useMemo(
    () => buildSelectionCopyCountLabel(
      copySelectionPayload.copiedCount || canonicalCopySelectionLines.length
    ),
    [copySelectionPayload.copiedCount, canonicalCopySelectionLines.length]
  );
  // The tip teaches reference syntax, so it fires on the first pick that yields
  // a reference to copy — a component, a subassembly, or a face/edge. Gating it
  // on topology alone would hide it from anyone who only ever clicks parts.
  const expandStepTreeAroundNode = useCallback((nodeId, {
    expandSelf = false,
    includeVisualOnlyAncestors = true
  } = {}) => {
    const normalizedNodeId = String(nodeId || "").trim();
    const treeRootForExpansion = displayStepTreeRoot || stepTreeRoot;
    if (!normalizedNodeId || !treeRootForExpansion) {
      return;
    }
    const idsToExpand = collectStepTreeRevealExpansionIds(treeRootForExpansion, normalizedNodeId, {
      expandSelf,
      includeVisualOnlyAncestors
    });
    if (!idsToExpand.length) {
      return;
    }
    setExpandedStepTreeNodeIds(current => idsToExpand.every(id => current.includes(id))
      ? current : uniqueStringList([...current, ...idsToExpand]));
  }, [displayStepTreeRoot, stepTreeRoot]);

  const revealStepTreeNode = useCallback((nodeId, {
    expandSelf = false,
    expandAncestors = false,
    source = "viewer"
  } = {}) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId || selectedFileSheetKind !== "step") {
      return;
    }
    setActiveTreeNodeScrollKey(source === "viewer" || source === "reference" ? `${source}:${Date.now()}:${normalizedNodeId}` : "");
    openFileSheetSection(FILE_SHEET_SECTION_IDS.STEP_TREE, {
      openSheet: shouldOpenFileSheetForSelectionReveal({ isDesktop: isWideLayout, source }),
      activate: source === "reference"
    });
    if (expandAncestors || expandSelf || source === "reference") {
      expandStepTreeAroundNode(normalizedNodeId, { expandSelf });
    }
  }, [
    expandStepTreeAroundNode,
    isWideLayout,
    openFileSheetSection,
    selectedFileSheetKind
  ]);

  const toggleReferenceSelection = useCallback((referenceId, { multiSelect = false, source = "viewer" } = {}) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      return;
    }
    if (source !== "viewer") {
      setActiveTreeNodeScrollKey("");
    }
    const normalizedReferenceId = String(referenceId || "").trim();
    const selectedReference = effectiveActiveReferenceMap.get(normalizedReferenceId);
    const selectedReferencePartId = referencePartId(selectedReference);
    const next = !multiSelect && selectedPartIdsRef.current.length
      ? (normalizedReferenceId ? [normalizedReferenceId] : [])
      : computeNextSelectionIds(selectedReferenceIdsRef.current, normalizedReferenceId, { multiSelect });
    if (next.length && !isWideLayout) {
      setFilesPanelOpen(false);
    }
    setSelectedWholeEntryCadRefToken("");
    if (!multiSelect && selectedPartIdsRef.current.length) {
      selectedPartIdsRef.current = [];
      setSelectedPartIds([]);
      setSelectedRenderPartIdByAssemblyPartId({});
    }
    selectedReferenceIdsRef.current = next;
    setSelectedReferenceIds(next);
    if (next.includes(normalizedReferenceId)) {
      const selectedReferenceTreeNodeId = findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, normalizedReferenceId);
      revealStepTreeNode(selectedReferenceTreeNodeId || selectedReferencePartId, { source });
    }
  }, [
    displayStepTreeRoot,
    effectiveActiveReferenceMap,
    focusedAssemblyNodeIds,
    isWideLayout,
    isAssemblyView,
    referencePartId,
    revealStepTreeNode,
    stepInteractionBlocked,
    stepModuleTreeSelectionDisabled
  ]);

  const clearReferenceSelection = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedReferenceIds([]);
    setCopyStatus("");
  }, []);

  const resetReferenceInteractionState = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedReferenceIds([]);
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setCopyStatus("");
  }, []);

  const promptResource = useMemo(() => ({ ...documentResource,
    revision: String(selectedEntry?.documentHash || selectedEntry?.hash || documentResource.revision || '')
  }), [documentResource, selectedEntry?.documentHash, selectedEntry?.hash]);
  // Copy is clipboard-only. Adding context is an explicit host action.
  const deliverReferenceText = useCallback((text) => host.clipboard.writeText(text), [host.clipboard]);
  const showPromptResult = useCallback((result) => setCopyStatus(promptDeliveryMessage(result)), []);
  const deliverPrompt = useCallback((context) => {
    let pending;
    try { pending = host.promptContext.deliver(context); }
    catch (error) { pending = Promise.reject(error); }
    return Promise.resolve(pending).catch(error => ({ status: 'failed', message: error instanceof Error ? error.message : String(error) }))
      .then(result => { showPromptResult(result); return result; });
  }, [host.promptContext, showPromptResult]);
  const referencesForHost = useCallback((text) =>
    referencesFromCopyText(text, cadFileParamForEntry(selectedEntry)).map((reference) => {
      const label = referenceLabel(reference.selector, displayStepTreeRoot || stepTreeRoot);
      return { ...reference, ...(label ? { label } : {}) };
    }), [selectedEntry, displayStepTreeRoot, stepTreeRoot]);
  const addReferenceText = useCallback((text) => {
    if (stepInteractionBlocked || !promptAvailable) return;
    const references = referencesForHost(text);
    if (references.length) return deliverPrompt(createCadPromptContext({ resource: promptResource, references }));
  }, [promptResource, deliverPrompt, promptAvailable, referencesForHost, stepInteractionBlocked]);
  const loadInspectionTopology = useCallback((partIds = []) => {
    const ids = isAssemblyView ? partIds.filter(id => loadableStepTreeTopologyNodeIdSet.has(id)) : [STEP_MODEL_ROOT_ID];
    for (const id of ids) expandStepTreeAroundNode(id, { expandSelf: true });
    if (!isAssemblyView) setLargeFileState(current => current.selectableTopologyEnabled ? current : ({ ...current, selectableTopologyEnabled: true }));
  }, [isAssemblyView, loadableStepTreeTopologyNodeIdSet, expandStepTreeAroundNode]);
  const loadFilterTopology = useCallback((target) => {
    if (target) loadInspectionTopology([target.id]);
  }, [loadInspectionTopology]);
  const appliedFilterTopologyRequest = useRef('');
  useEffect(() => {
    const requestKey = ["faces", "edges", "tangent-faces", "edge-chain"].includes(selectionFilter) && topologyTarget
      ? `${selectedKey}:${artifactRevision}:${selectionFilter}:${topologyTarget.id}` : '';
    if (requestKey && appliedFilterTopologyRequest.current !== requestKey) loadFilterTopology(topologyTarget);
    appliedFilterTopologyRequest.current = requestKey;
    setSelectionFilterNotice("");
  }, [selectedKey, artifactRevision, selectionFilter, topologyTarget, loadFilterTopology]);
  const selectReferenceGroup = useCallback((referenceIds, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress || !referenceIds.length || !referenceIds.every(id => ["face", "edge"].includes(effectiveActiveReferenceMap.get(id)?.selectorType))) return;
    const next = toggleReferenceGroupSelection(selectedReferenceIdsRef.current, referenceIds, multiSelect);
    selectedPartIdsRef.current = [];
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedWholeEntryCadRefToken("");
    selectedReferenceIdsRef.current = next;
    setSelectedReferenceIds(next);
    setActiveTreeNodeScrollKey("");
    setCopyStatus("");
  }, [stepUpdateInProgress, effectiveActiveReferenceMap]);
  const hostReference = useMemo(
    () => ({ deliverReference: deliverReferenceText, addReference: addReferenceText, canAddToPrompt: composerDestination && promptAvailable }),
    [composerDestination, promptAvailable, deliverReferenceText, addReferenceText]
  );
  const selectionKey = JSON.stringify([promptResource, canonicalCopySelectionLines, inspectionHighlight?.label, inspectionHighlight?.context]);
  const liveSelectionKey = useRef(selectionKey);
  liveSelectionKey.current = selectionKey;
  useLayoutEffect(() => { liveSelectionKey.current = selectionKey; return () => { liveSelectionKey.current = null; }; }, [selectionKey]);
  const createSelectionPromptContext = useCallback(({ text: instruction = '', capture: includeCapture = false } = {}) => {
    if (liveSelectionKey.current !== selectionKey) throw new Error('This selection has changed. Open the action again.');
    if (viewerLoading || stepInteractionBlocked) throw new Error('Wait for the model before using this selection.');
    const copied = inspectionHighlight ? stepGeometryPromptText(inspectionHighlight, {
      referenceMap: effectiveActiveReferenceMap,
      parts: selectedMeshData?.parts || EMPTY_LIST,
      entry: selectedEntry,
    }) : canonicalCopySelectionLines.join("\n");
    const references = referencesForHost(copied).map(reference => inspectionHighlight?.label ? { ...reference, label: inspectionHighlight.label } : reference);
    const inspected = inspectionHighlight?.context?.file === selectedEntry?.file
      ? stepGeometryContextText({ ...inspectionHighlight.context, file: promptResource.path }, { includeModel: !references.length }) : '';
    let capture;
    if (includeCapture) {
      if (!viewerRef.current?.captureScreenshotBlob) throw new Error('CAD Viewer not ready');
      capture = viewerRef.current.captureScreenshotBlob();
      void capture.catch(() => {});
    }
    return createCadPromptContext({ resource: promptResource, references, text: [inspected, instruction].filter(Boolean).join('\n\n'), capture });
  }, [selectionKey, promptResource, viewerLoading, stepInteractionBlocked, inspectionHighlight, effectiveActiveReferenceMap, selectedMeshData, selectedEntry, canonicalCopySelectionLines, referencesForHost]);

  const handleCopySelection = useCallback(async () => {
    setScreenshotStatus("");
    if (stepInteractionBlocked) {
      setCopyStatus(retainedPreviousStepMeshError
        ? "Selection unavailable because the STEP update failed."
        : "STEP update in progress. Please wait.");
      return;
    }
    const selectedReferencesForCopy = selectedReferenceIdsRef.current
      .map((id) => (
        stepTreeCopyReferenceMap.get(id) ||
        effectiveActiveReferenceMap.get(id) ||
        copyReferenceForRawSelectorSelection(id, "topology")
      ))
      .filter(Boolean);
    if (!isAssemblyView && selectedPartIdsRef.current.includes(STEP_MODEL_ROOT_ID)) {
      const wholeStepEntryReference = buildWholeStepEntryCopyReference(selectedEntry);
      if (wholeStepEntryReference) {
        selectedReferencesForCopy.push(wholeStepEntryReference);
      }
    }
    const selectedPartReferencesForCopy = selectedPartIdsRef.current
      .map((id) => (
        copyReferenceForRawSelectorSelection(id, "assembly-part") ||
        stepTreeCopyReferenceMap.get(id) ||
        copyReferenceForStepTreeNodeSelection(
          copyableStepTreeNodeForWorkspace({
            assemblyPartMap,
            displayStepTreeRoot,
            stepTreeRoot,
            nodeId: id
          }),
          id,
          "assembly-part"
        )
      ))
      .filter(Boolean);
    if (
      !selectedReferencesForCopy.length &&
      !selectedPartReferencesForCopy.length
    ) {
      setCopyStatus("Nothing selected");
      return;
    }

    const payload = copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
      references: [
        ...selectedReferencesForCopy,
        ...selectedPartReferencesForCopy
      ],
      parts: [],
      entry: selectedEntry
    }), {
      selectedReferenceIds: selectedReferenceIdsRef.current,
      selectedPartIds: selectedPartIdsRef.current,
      copyReferenceMap: stepTreeCopyReferenceMap
    });
    const { lines, missingPartNames = [] } = payload;
    if (!lines.length) {
      setCopyStatus(
        missingPartNames.length === 1
          ? `No selector ref is available for ${missingPartNames[0]}`
          : "No selector refs are available for the selection"
      );
      return;
    }

    try {
      // The SAME prefixing the button label gets. This is the write that matters, and it
      // built its own payload rather than reusing canonicalCopySelectionLines, so leaving it
      // out made the label promise a file prefix the clipboard never carried.
      await deliverReferenceText(
        lines
          .map((line) => canonicalCadRefCopyText(line))
          .map((line) => withFileRefPrefix(line, selectedEntry?.fileRefPrefix))
          .filter(Boolean)
          .join("\n")
      );
      const copiedCount = payload.copiedCount ||
        selectedReferencesForCopy.length +
        selectedPartReferencesForCopy.length -
        missingPartNames.length;
      const missingSuffix = missingPartNames.length
        ? ` (${missingPartNames.length} unavailable)`
        : "";
      setCopyStatus(`Copied ${copiedCount} ref${copiedCount === 1 ? "" : "s"}${missingSuffix}`);
    } catch (err) {
      setCopyStatus(err instanceof Error ? err.message : "Clipboard write failed");
    }
  }, [
    assemblyPartMap,
    displayStepTreeRoot,
    effectiveActiveReferenceMap,
    selectedEntry,
    retainedPreviousStepMeshError,
    setScreenshotStatus,
    stepTreeCopyReferenceMap,
    stepTreeRoot,
    stepInteractionBlocked
  ]);

  const toggleStepTreeNode = useCallback((nodeId) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId) return;
    setExpandedStepTreeNodeIds(current => current.includes(normalizedNodeId)
      ? current.filter(id => id !== normalizedNodeId)
      : [...current, normalizedNodeId]);
  }, []);

  const removeSelectedAssemblyNode = useCallback((nodeId) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId) {
      return selectedPartIdsRef.current;
    }
    const nextSelectedPartIds = selectedPartIdsRef.current.filter((id) => String(id || "").trim() !== normalizedNodeId);
    if (nextSelectedPartIds.length === selectedPartIdsRef.current.length) {
      return selectedPartIdsRef.current;
    }
    selectedPartIdsRef.current = nextSelectedPartIds;
    setSelectedPartIds(nextSelectedPartIds);
    setSelectedRenderPartIdByAssemblyPartId((current) => {
      const nextMap = { ...current };
      delete nextMap[normalizedNodeId];
      return nextMap;
    });
    return nextSelectedPartIds;
  }, []);

  const togglePartSelection = useCallback((partId, { multiSelect = false, renderPartId = "", source = "viewer" } = {}) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      return selectedPartIdsRef.current;
    }
    if (source !== "viewer") {
      setActiveTreeNodeScrollKey("");
    }
    const normalizedPartId = String(partId || "").trim();
    const alreadySelected = selectedPartIdsRef.current.includes(normalizedPartId);
    const scopedSelectableNodeIds = source === "viewer"
      ? viewerSelectableAssemblyNodeIdSet
      : validAssemblySelectionIdSet;
    if (isAssemblyView && !scopedSelectableNodeIds.has(normalizedPartId) && !alreadySelected) {
      return selectedPartIdsRef.current;
    }
    const next = !multiSelect && selectedReferenceIdsRef.current.length
      ? (normalizedPartId ? [normalizedPartId] : [])
      : computeNextSelectionIds(selectedPartIdsRef.current, partId, { multiSelect });
    if (next.length && !isWideLayout) {
      setFilesPanelOpen(false);
    }
    setSelectedWholeEntryCadRefToken("");
    if (!multiSelect && selectedReferenceIdsRef.current.length) {
      selectedReferenceIdsRef.current = [];
      setSelectedReferenceIds([]);
    }
    selectedPartIdsRef.current = next;
    setSelectedPartIds(next);
    if (next.includes(normalizedPartId)) {
      revealStepTreeNode(normalizedPartId, { source });
    }
    setSelectedRenderPartIdByAssemblyPartId((current) => {
      const nextMap = {};
      for (const selectedPartId of next) {
        const normalizedSelectedPartId = String(selectedPartId || "").trim();
        if (!normalizedSelectedPartId) {
          continue;
        }
        const selectedRenderPartId = normalizedSelectedPartId === normalizedPartId
          ? renderPartIdForAssemblySelection(normalizedSelectedPartId, renderPartId)
          : renderPartIdForAssemblySelection(normalizedSelectedPartId, current[normalizedSelectedPartId]);
        if (selectedRenderPartId) {
          nextMap[normalizedSelectedPartId] = selectedRenderPartId;
        }
      }
      return nextMap;
    });
    return next;
  }, [
    isWideLayout,
    isAssemblyView,
    focusedAssemblyNodeIds,
    removeSelectedAssemblyNode,
    revealStepTreeNode,
    renderPartIdForAssemblySelection,
    validAssemblySelectionIdSet,
    viewerSelectableAssemblyNodeIdSet,
    stepInteractionBlocked,
    stepModuleTreeSelectionDisabled,
  ]);

  const selectStepTreeNode = useCallback((nodeId, { multiSelect = false } = {}) => {
    const normalizedNodeId = String(nodeId || "").trim();
    togglePartSelection(normalizedNodeId, { multiSelect, source: "tree" });
  }, [
    togglePartSelection
  ]);

  /**
   * A reference the host names (`selectReference`, docs/cad-renderer.md): a
   * transcript link said `bracket.step#o1.2`. Resolved against whatever is
   * loaded (hostReference.js) and applied once per `key` — the maps fill as
   * the model and its topology arrive, so an unresolved selector is tried
   * again on the next change, and a resolved one is not re-applied when they
   * change after. Already selected means revealed, not toggled off.
   */
  const appliedSelectReferenceKeyRef = useRef(null);
  useEffect(() => {
    const selector = String(selectReference?.selector || "").trim();
    if (!selector || appliedSelectReferenceKeyRef.current === selectReference.key || viewerLoading || stepInteractionBlocked) {
      return;
    }
    const selectors = selector.split(",").map(value => value.trim()).filter(Boolean);
    const owners = stepTreeTopologyOwnersForSelectors(stepTreeRoot, selectors, { isAssemblyView });
    if (isolatedStepTreeSelectableNodeIds && owners.some(id => !isolatedStepTreeSelectableNodeIds.includes(id))) {
      setIsolatedAssemblyNodeIds([]);
    }
    if (owners.some(id => !expandedStepTreeTopologyNodeIds.includes(id))) loadInspectionTopology(owners);
    if (selectors.length > 1) {
      const resolvedFaces = selectors.map(value => resolveSelectorSelection(value, {
        referenceMap: effectiveActiveReferenceMap,
        treeRoot: displayStepTreeRoot || stepTreeRoot
      }));
      if (resolvedFaces.some(value => !value)) return;
      if (resolvedFaces.every(value => value.kind === "reference" && effectiveActiveReferenceMap.get(value.id)?.selectorType === "face")) {
        if (stepUpdateInProgress) return;
        selectReferenceGroup(resolvedFaces.map(value => value.id));
        const lastFace = resolvedFaces[resolvedFaces.length - 1].id;
        revealStepTreeNode(findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, lastFace) || referencePartId(effectiveActiveReferenceMap.get(lastFace)), { source: "reference" });
        appliedSelectReferenceKeyRef.current = selectReference.key;
        if (selectReference.key !== undefined) acknowledgeCommand?.('selectReference', selectReference.key);
        return;
      }
    }
    const resolved = resolveSelectorSelection(selector, {
      referenceMap: effectiveActiveReferenceMap,
      treeRoot: displayStepTreeRoot || stepTreeRoot
    });
    if (!resolved) {
      return;
    }
    appliedSelectReferenceKeyRef.current = selectReference.key;
        if (selectReference.key !== undefined) acknowledgeCommand?.('selectReference', selectReference.key);
    if (resolved.kind === "reference") {
      if (selectedReferenceIdsRef.current.includes(resolved.id)) {
        revealStepTreeNode(findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, resolved.id) || referencePartId(effectiveActiveReferenceMap.get(resolved.id)) || resolved.id, { source: "reference" });
      } else {
        toggleReferenceSelection(resolved.id, { source: "reference" });
      }
    } else if (selectedPartIdsRef.current.includes(resolved.id)) {
      revealStepTreeNode(resolved.id, { source: "reference" });
    } else {
      togglePartSelection(resolved.id, { source: "reference" });
    }
  }, [
    selectReference,
    isAssemblyView,
    isolatedStepTreeSelectableNodeIds,
    expandedStepTreeTopologyNodeIds,
    loadInspectionTopology,
    acknowledgeCommand,
    stepInteractionBlocked,
    viewerLoading,
    stepUpdateInProgress,
    selectReferenceGroup,
    referencePartId,
    effectiveActiveReferenceMap,
    displayStepTreeRoot,
    stepTreeRoot,
    revealStepTreeNode,
    toggleReferenceSelection,
    togglePartSelection
  ]);

  const selectStepTreeReferenceNode = useCallback((referenceId, { multiSelect = false } = {}) => {
    const normalizedReferenceId = String(referenceId || "").trim();
    if (!normalizedReferenceId) {
      return;
    }
    toggleReferenceSelection(normalizedReferenceId, { multiSelect, source: "tree" });
  }, [toggleReferenceSelection]);

  const clearAssemblySelectionForFocus = useCallback(() => {
    setActiveTreeNodeScrollKey("");
    selectedPartIdsRef.current = [];
    selectedReferenceIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedReferenceIds([]);
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setViewerContextMenu(null);
    setCopyStatus("");
  }, []);

  const collapseStepTreeSubtree = useCallback((partId) => {
    const normalizedPartId = String(partId || "").trim();
    const treeRootForCollapse = displayStepTreeRoot || stepTreeRoot;
    const collapsedIds = new Set(collectStepTreeSubtreeIds(treeRootForCollapse, normalizedPartId));
    if (!collapsedIds.size) {
      return;
    }
    setExpandedStepTreeNodeIds((current) => current.filter((id) => !collapsedIds.has(id)));
  }, [
    displayStepTreeRoot,
    stepTreeRoot
  ]);

  const focusStepTreeNode = useCallback((nodeId, { reveal = true } = {}) => {
    if (!isAssemblyView || !assemblyRoot) {
      return;
    }
    const requestedNodeIds = uniqueStringList(
      (Array.isArray(nodeId) ? nodeId : [nodeId])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    const targetNodeIds = minimalAssemblyIsolationNodeIds(assemblyRoot, requestedNodeIds, {
      rootId: assemblyRootNodeId
    });
    const targetNodes = targetNodeIds
      .map((id) => ({ id, node: findAssemblyNode(assemblyRoot, id) }))
      .filter(({ node }) => Boolean(node));
    if (!targetNodes.length) {
      setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
      return;
    }
    const targetLeafIds = targetNodes.flatMap(({ node }) => descendantLeafPartIds(node))
      .map((id) => String(id || "").trim())
      .filter(Boolean);
    const targetLeafIdSet = new Set(targetLeafIds);
    clearAssemblySelectionForFocus();
    setIsolatedAssemblyNodeIds(targetNodeIds);
    setExpandedStepTreeNodeIds((current) => uniqueStringList([...current, ...targetNodeIds]));
    setHiddenPartIds((current) => {
      if (!targetLeafIdSet.size) {
        return current;
      }
      const next = current.filter((id) => !targetLeafIdSet.has(String(id || "").trim()));
      return next.length === current.length ? current : next;
    });
    for (const targetNodeId of reveal ? targetNodeIds : []) {
      revealStepTreeNode(targetNodeId, {
        expandSelf: true,
        source: "tree"
      });
    }
  }, [
    assemblyRoot,
    assemblyRootNodeId,
    clearAssemblySelectionForFocus,
    isAssemblyView,
    revealStepTreeNode
  ]);

  const handleExitIsolate = useCallback(() => {
    for (const nodeId of focusedAssemblyNodeIds) {
      collapseStepTreeSubtree(nodeId);
    }
    setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
  }, [
    collapseStepTreeSubtree,
    focusedAssemblyNodeIds
  ]);

  const handleExitSingleIsolate = useCallback((nodeId) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId) {
      handleExitIsolate();
      return;
    }
    collapseStepTreeSubtree(normalizedNodeId);
    setIsolatedAssemblyNodeIds((current) => {
      const next = current.filter((id) => String(id || "").trim() !== normalizedNodeId);
      return next.length === current.length ? current : next;
    });
  }, [
    collapseStepTreeSubtree,
    handleExitIsolate
  ]);

  const clearAssemblySelection = useCallback(() => {
    clearAssemblySelectionForFocus();
  }, [clearAssemblySelectionForFocus]);

  useEffect(() => {
    if (!stepModuleTreeSelectionDisabled) {
      return;
    }
    if (
      selectedPartIdsRef.current.length ||
      selectedReferenceIdsRef.current.length ||
      selectedWholeEntryCadRefToken
    ) {
      clearAssemblySelection();
    }
  }, [clearAssemblySelection, selectedWholeEntryCadRefToken, stepModuleTreeSelectionDisabled]);

  const clearSelectionForHiddenLeafIds = useCallback((leafIds, nodeId = "") => {
    const hiddenLeafIds = new Set(
      (Array.isArray(leafIds) ? leafIds : [])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    if (!hiddenLeafIds.size) {
      return;
    }
    const normalizedNodeId = String(nodeId || "").trim();
    const nextSelectedPartIds = selectedPartIdsRef.current.filter((selectedNodeId) => {
      const normalizedSelectedNodeId = String(selectedNodeId || "").trim();
      if (!normalizedSelectedNodeId) {
        return false;
      }
      if (normalizedNodeId && assemblyNodeContainsNode(assemblyRoot, normalizedNodeId, normalizedSelectedNodeId)) {
        return false;
      }
      const selectedLeafIds = renderPartIdsForAssemblySelection(normalizedSelectedNodeId);
      return !selectedLeafIds.some((leafId) => hiddenLeafIds.has(String(leafId || "").trim()));
    });
    const partSelectionChanged = nextSelectedPartIds.length !== selectedPartIdsRef.current.length;
    if (partSelectionChanged) {
      selectedPartIdsRef.current = nextSelectedPartIds;
      setSelectedPartIds(nextSelectedPartIds);
      setSelectedRenderPartIdByAssemblyPartId((current) => {
        const selectedNodeIdSet = new Set(nextSelectedPartIds);
        const nextMap = {};
        for (const [selectedNodeId, renderPartId] of Object.entries(current || {})) {
          if (selectedNodeIdSet.has(selectedNodeId)) {
            nextMap[selectedNodeId] = renderPartId;
          }
        }
        return nextMap;
      });
    }

    const nextSelectedReferenceIds = selectedReferenceIdsRef.current.filter((referenceId) => {
      const reference = effectiveActiveReferenceMap.get(referenceId);
      const selectedReferencePartId = referencePartId(reference);
      const selectedReferenceLeafIds = renderPartIdsForAssemblySelection(selectedReferencePartId, selectedReferencePartId);
      return !selectedReferenceLeafIds.some((leafId) => hiddenLeafIds.has(String(leafId || "").trim()));
    });
    const referenceSelectionChanged = nextSelectedReferenceIds.length !== selectedReferenceIdsRef.current.length;
    if (referenceSelectionChanged) {
      selectedReferenceIdsRef.current = nextSelectedReferenceIds;
      setSelectedReferenceIds(nextSelectedReferenceIds);
    }

    if (partSelectionChanged || referenceSelectionChanged) {
      setSelectedWholeEntryCadRefToken("");
      setCopyStatus("");
    }
  }, [
    assemblyRoot,
    effectiveActiveReferenceMap,
    referencePartId,
    renderPartIdsForAssemblySelection
  ]);

  useEffect(() => {
    clearSelectionForHiddenLeafIds(hiddenPartIds);
  }, [
    clearSelectionForHiddenLeafIds,
    hiddenPartIds
  ]);

  const hideStepTreeNode = useCallback((partId) => {
    const normalizedPartId = String(partId || "").trim();
    const leafIds = renderPartIdsForAssemblySelection(partId);
    if (!leafIds.length) {
      return;
    }
    collapseStepTreeSubtree(partId);
    clearSelectionForHiddenLeafIds(leafIds, normalizedPartId);
    setIsolatedAssemblyNodeIds((current) => {
      const next = current.filter((nodeId) => !assemblyNodeContainsNode(assemblyRoot, normalizedPartId, nodeId));
      return next.length === current.length ? current : next;
    });
    setHiddenPartIds((current) => {
      const hidden = new Set(current);
      let changed = false;
      for (const id of leafIds) {
        if (!id || hidden.has(id)) {
          continue;
        }
        hidden.add(id);
        changed = true;
      }
      return changed ? [...hidden] : current;
    });
  }, [
    assemblyRoot,
    collapseStepTreeSubtree,
    clearSelectionForHiddenLeafIds,
    renderPartIdsForAssemblySelection
  ]);

  const revealHiddenStepTreeNode = useCallback((partId) => {
    const leafIds = renderPartIdsForAssemblySelection(partId);
    if (!leafIds.length) {
      return;
    }
    const leafIdSet = new Set(leafIds);
    setHiddenPartIds((current) => current.filter((id) => !leafIdSet.has(id)));
    revealStepTreeNode(partId, {
      source: "viewer"
    });
  }, [
    renderPartIdsForAssemblySelection,
    revealStepTreeNode
  ]);

  const togglePartVisibility = useCallback((partId) => {
    const leafIds = renderPartIdsForAssemblySelection(partId);
    if (!leafIds.length) {
      return;
    }
    const hidden = new Set(hiddenPartIds);
    const allHidden = leafIds.every((id) => hidden.has(id));
    if (!allHidden) {
      collapseStepTreeSubtree(partId);
      clearSelectionForHiddenLeafIds(leafIds, partId);
      setIsolatedAssemblyNodeIds((current) => {
        const next = current.filter((nodeId) => !assemblyNodeContainsNode(assemblyRoot, partId, nodeId));
        return next.length === current.length ? current : next;
      });
    }
    setHiddenPartIds((current) => {
      const hidden = new Set(current);
      const allHidden = leafIds.every((id) => hidden.has(id));
      if (allHidden) {
        return current.filter((id) => !leafIds.includes(id));
      }
      for (const id of leafIds) {
        hidden.add(id);
      }
      return [...hidden];
    });
  }, [
    assemblyRoot,
    collapseStepTreeSubtree,
    clearSelectionForHiddenLeafIds,
    hiddenPartIds,
    renderPartIdsForAssemblySelection
  ]);

  const handleHideSelectedParts = useCallback(() => {
    const nextSelectedPartIds = [...new Set(
      selectedPartIdsRef.current
        .map((partId) => String(partId || "").trim())
        .filter(Boolean)
    )];
    if (nextSelectedPartIds.length < 1) {
      return;
    }
    setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
    setHiddenPartIds((current) => {
      const next = [...current];
      const hidden = new Set(current);
      let changed = false;
      for (const partId of nextSelectedPartIds.flatMap((id) => renderPartIdsForAssemblySelection(id))) {
        if (!partId || hidden.has(partId)) {
          continue;
        }
        hidden.add(partId);
        next.push(partId);
        changed = true;
      }
      return changed ? next : current;
    });
    clearAssemblySelectionForFocus();
  }, [
    clearAssemblySelectionForFocus,
    renderPartIdsForAssemblySelection
  ]);

  const handleHideOtherSelectedParts = useCallback(() => {
    const selectedLeafPartIds = [...new Set(
      selectedPartIdsRef.current
        .map((partId) => String(partId || "").trim())
        .filter(Boolean)
        .flatMap((partId) => renderPartIdsForAssemblySelection(partId))
        .map((partId) => String(partId || "").trim())
        .filter(Boolean)
    )];
    if (!selectedLeafPartIds.length) {
      return;
    }
    const selectedLeafPartIdSet = new Set(selectedLeafPartIds);
    setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
    setHiddenPartIds(validAssemblyLeafIds.filter((partId) => !selectedLeafPartIdSet.has(partId)));
    clearAssemblySelectionForFocus();
  }, [
    clearAssemblySelectionForFocus,
    renderPartIdsForAssemblySelection,
    validAssemblyLeafIds
  ]);

  const handleHideOtherTreeNode = useCallback((nodeId) => {
    const normalizedNodeIds = uniqueStringList(
      (Array.isArray(nodeId) ? nodeId : [nodeId])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    if (!normalizedNodeIds.length) {
      return;
    }
    const targetLeafPartIds = [...new Set(
      normalizedNodeIds
        .flatMap((id) => renderPartIdsForAssemblySelection(id))
        .map((partId) => String(partId || "").trim())
        .filter(Boolean)
    )];
    if (!targetLeafPartIds.length) {
      return;
    }
    const targetLeafPartIdSet = new Set(targetLeafPartIds);
    setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
    setHiddenPartIds(validAssemblyLeafIds.filter((partId) => !targetLeafPartIdSet.has(partId)));
    clearAssemblySelectionForFocus();
    for (const targetNodeId of normalizedNodeIds) {
      revealStepTreeNode(targetNodeId, {
        source: "tree"
      });
    }
  }, [
    clearAssemblySelectionForFocus,
    renderPartIdsForAssemblySelection,
    revealStepTreeNode,
    validAssemblyLeafIds
  ]);

  const handleHideAllParts = useCallback(() => {
    if (!validAssemblyLeafIds.length) {
      return;
    }
    setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
    setHiddenPartIds(validAssemblyLeafIds);
    clearAssemblySelectionForFocus();
  }, [
    clearAssemblySelectionForFocus,
    validAssemblyLeafIds
  ]);

  const handleShowAllHiddenParts = useCallback(() => {
    setHiddenPartIds((current) => (current.length ? [] : current));
  }, []);

  const handleModelHoverChange = useCallback((referenceId) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      setHoveredModelReferenceId("");
      setHoveredModelPartId("");
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    const topologyReference = effectiveActiveReferenceMap.get(nextReferenceId) || null;
    if (topologyReference && isViewerTopologyReference(topologyReference)) {
      setHoveredModelReferenceId(nextReferenceId);
      setHoveredModelPartId("");
      return;
    }
    if (viewerInAssemblyMode) {
      const pickedPartId = nextReferenceId;
      if (!pickedPartId) {
        setHoveredModelReferenceId("");
        setHoveredModelPartId("");
        return;
      }
      setHoveredModelReferenceId("");
      setHoveredModelPartId(resolvePickedAssemblyPartId(pickedPartId));
      return;
    }
    setHoveredModelReferenceId(nextReferenceId);
  }, [
    effectiveActiveReferenceMap,
    isViewerTopologyReference,
    viewerInAssemblyMode,
    resolvePickedAssemblyPartId,
    stepInteractionBlocked,
    stepModuleTreeSelectionDisabled
  ]);

  const tangentFaces = useMemo(() => buildTangentFaceGraph(
    selectionFilter === "tangent-faces" ? [...effectiveActiveReferenceMap.values()] : EMPTY_LIST
  ), [selectionFilter, effectiveActiveReferenceMap]);

  const edgeChains = useMemo(() => buildEdgeChainGraph(
    selectionFilter === "edge-chain" ? [...effectiveActiveReferenceMap.values()] : EMPTY_LIST
  ), [selectionFilter, effectiveActiveReferenceMap]);

  const handleModelReferenceActivate = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    if (!nextReferenceId) {
      if (multiSelect) return;
      clearAssemblySelection();
      return;
    }
    if (selectionFilter === "parts") {
      const partId = isAssemblyView ? resolvePickedAssemblyPartId(nextReferenceId) : STEP_MODEL_ROOT_ID;
      togglePartSelection(partId, { multiSelect, renderPartId: nextReferenceId, source: "viewer" });
      return;
    }
    const topologyReference = effectiveActiveReferenceMap.get(nextReferenceId) || null;
    if (selectionFilter === "edge-chain" && topologyReference?.selectorType === "edge") {
      setInspectionHighlight(null);
      selectReferenceGroup(connectedReferenceIds(edgeChains, topologyReference.id), { multiSelect });
      return;
    }
    if (selectionFilter === "tangent-faces" && topologyReference?.selectorType === "face") {
      setInspectionHighlight(null);
      selectReferenceGroup(connectedReferenceIds(tangentFaces, topologyReference.id), { multiSelect });
      return;
    }
    if (topologyReference && isViewerTopologyReference(topologyReference)) {
      const group = selectionFilter === "all" ? referenceGroupForModelTreeHit(
        nextReferenceId, visibleFeatureTargets, viewerPickableReferences.map(reference => reference.id)
      ) : EMPTY_LIST;
      if (group.length) {
        selectReferenceGroup(group, { multiSelect });
        revealStepTreeNode(referencePartId(topologyReference), { source: "viewer" });
        return;
      }
      toggleReferenceSelection(nextReferenceId, { multiSelect });
      return;
    }
    if (["faces", "edges", "tangent-faces", "edge-chain"].includes(selectionFilter)) return;
    if (viewerInAssemblyMode) {
      const pickedPartId = nextReferenceId;
      const nextPartId = resolvePickedAssemblyPartId(pickedPartId);
      if (!nextPartId) {
        clearAssemblySelection();
        return;
      }
      togglePartSelection(nextPartId, { multiSelect, renderPartId: pickedPartId });
      return;
    }
    if (selectedEntry && effectiveRenderFormat === RENDER_FORMAT.STEP) {
      togglePartSelection(STEP_MODEL_ROOT_ID, { multiSelect, renderPartId: nextReferenceId });
    }
  }, [
    clearAssemblySelection,
    visibleFeatureTargets,
    viewerPickableReferences,
    revealStepTreeNode,
    referencePartId,
    selectionFilter,
    tangentFaces,
    edgeChains,
    selectReferenceGroup,
    isAssemblyView,
    effectiveRenderFormat,
    effectiveActiveReferenceMap,
    resolvePickedAssemblyPartId,
    selectedEntry,
    selectedEntryHasReferences,
    selectedReferencesMatch,
    stepInteractionBlocked,
    toggleReferenceSelection,
    togglePartSelection,
    viewerInAssemblyMode,
    stepModuleTreeSelectionDisabled
  ]);

  const handleModelReferenceDoubleActivate = useCallback((referenceId) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled || !isAssemblyView) {
      return;
    }
    const pickedPartId = String(referenceId || "").trim();
    if (!pickedPartId) {
      handleExitIsolate();
      clearAssemblySelection();
      return;
    }
    if (!viewerInAssemblyMode) {
      return;
    }
    const topologyReference = effectiveActiveReferenceMap.get(pickedPartId) || null;
    if (topologyReference && isViewerTopologyReference(topologyReference)) {
      return;
    }
    const nextPartId = resolvePickedAssemblyPartId(pickedPartId);
    if (nextPartId) {
      focusStepTreeNode(nextPartId);
      const focusedNode = findAssemblyNode(assemblyRoot, nextPartId);
      const hoveredChildNodeId = childAssemblyNodeIdForPickedLeaf(focusedNode, pickedPartId);
      setHoveredModelReferenceId("");
      setHoveredModelPartId(hoveredChildNodeId || nextPartId);
    }
  }, [
    assemblyRoot,
    clearAssemblySelection,
    focusStepTreeNode,
    handleExitIsolate,
    effectiveActiveReferenceMap,
    isViewerTopologyReference,
    viewerInAssemblyMode,
    isAssemblyView,
    resolvePickedAssemblyPartId,
    stepInteractionBlocked,
    stepModuleTreeSelectionDisabled,
  ]);

  const closeViewerContextMenu = useCallback(() => {
    setViewerContextMenu(null);
  }, []);

  useEffect(() => {
    setViewerContextMenu(null);
  }, [selectedKey]);

  // Right-clicking empty space is a VIEWPORT gesture, so the menu it opens belongs to
  // every format that draws something — camera actions are not a STEP feature. Only the
  // assembly-tree entries below are capability-gated; a format with no parts simply gets
  // the camera section. This also un-strands `zoomToFitSelection`'s whole-model fallback,
  // which was unreachable while this handler bailed on anything but STEP.
  const openGlobalViewerContextMenu = useCallback(({ clientX = 0, clientY = 0 } = {}) => {
    if (!selectedViewportContent) {
      setViewerContextMenu(null);
      return;
    }
    const hasPartsMenu = hasCapability(selectedEntrySourceFormat, "parts");
    const expansionState = hasPartsMenu
      ? buildStepTreeExpansionMenuState({
          root: displayStepTreeRoot,
          isAssemblyView,
          expandedTreeNodeIds: expandedStepTreeNodeIds,
          loadableTreeNodeIds: loadableStepTreeTopologyNodeIds,
          actionNodeIds: []
        })
      : { showExpandCollapse: false, collapsedExpandableTreeNodeIds: [] };
    setViewerContextMenu({
      x: Number(clientX) || 0,
      y: Number(clientY) || 0,
      global: true,
      label: "Viewer",
      hidden: true,
      showShowAll: hasPartsMenu && hiddenPartIds.length > 0,
      showCameraActions: true,
      // Nothing narrower is selected here, so "Zoom To Fit" means the whole model.
      fitWholeModel: true,
      showExpandCollapse: hasPartsMenu &&
        (expansionState.showExpandCollapse || expandedStepTreeNodeIds.length > 0),
      collapsedExpandableTreeNodeIds: expansionState.collapsedExpandableTreeNodeIds,
      expandedExpandableTreeNodeIds: expandedStepTreeNodeIds,
      expandAllDisabled: expansionState.collapsedExpandableTreeNodeIds.length < 1,
      collapseAllDisabled: expandedStepTreeNodeIds.length < 1
    });
  }, [
    displayStepTreeRoot,
    expandedStepTreeNodeIds,
    hiddenPartIds.length,
    isAssemblyView,
    loadableStepTreeTopologyNodeIds,
    selectedEntrySourceFormat,
    selectedViewportContent
  ]);

  const handleModelReferenceContext = useCallback((referenceId, { clientX = 0, clientY = 0 } = {}) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      setViewerContextMenu(null);
      return;
    }
    const pickedPartId = String(referenceId || "").trim();
    if (!pickedPartId) {
      openGlobalViewerContextMenu({ clientX, clientY });
      return;
    }
    const topologyReference = effectiveActiveReferenceMap.get(pickedPartId) || null;
    if (topologyReference && isViewerTopologyReference(topologyReference)) {
      const selected = selectedReferenceIdsRef.current.includes(pickedPartId);
      const selectedContextReferenceIds = uniqueStringList(
        selectedReferenceIdsRef.current
          .map((id) => String(id || "").trim())
          .filter(Boolean)
      );
      const actionReferenceIds = uniqueStringList([...selectedContextReferenceIds, pickedPartId]);
      const referencesForCopy = actionReferenceIds
        .map((id) => (
          stepTreeCopyReferenceMap.get(id) ||
          effectiveActiveReferenceMap.get(id) ||
          copyReferenceForRawSelectorSelection(id, "topology")
        ))
        .filter(Boolean);
      const fitReferenceIds = actionReferenceIds;
      const selectedFitPartIds = uniqueStringList(
        selectedPartIdsRef.current
          .map((id) => String(id || "").trim())
          .filter(Boolean)
          .flatMap((id) => renderPartIdsForAssemblySelection(id, id))
      );
      const fitPartIds = uniqueStringList([
        ...selectedFitPartIds,
        ...fitReferenceIds
          .map((id) => referencePartId(
            effectiveActiveReferenceMap.get(id) ||
            (id === pickedPartId ? topologyReference : null)
          ))
          .filter(Boolean)
      ]);
      const fitAvailable = fitReferenceIds.length > 0 || fitPartIds.length > 0;
      const { lines } = copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
        references: referencesForCopy.length ? referencesForCopy : [topologyReference],
        parts: [],
        entry: selectedEntry
      }), {
        selectedReferenceIds: actionReferenceIds,
        copyReferenceMap: stepTreeCopyReferenceMap
      });
      setViewerContextMenu({
        x: Number(clientX) || 0,
        y: Number(clientY) || 0,
        referenceId: pickedPartId,
        referenceIds: actionReferenceIds,
        label: String(topologyReference?.label || topologyReference?.displayName || pickedPartId).trim(),
        selected,
        hidden: false,
        focused: false,
        actionCount: actionReferenceIds.length || 1,
        copyText: lines.join("\n"),
        showIsolate: false,
        showHideOther: false,
        showVisibility: false,
        showHideAll: false,
        showCameraActions: true,
        zoomToFitDisabled: !fitAvailable,
        fitReferenceIds,
        fitPartIds
      });
      return;
    }
    if (!viewerInAssemblyMode) {
      openGlobalViewerContextMenu({ clientX, clientY });
      return;
    }
    const nodeId = resolvePickedAssemblyPartId(pickedPartId);
    if (!nodeId) {
      openGlobalViewerContextMenu({ clientX, clientY });
      return;
    }
    const node = assemblyPartMap.get(nodeId) || findAssemblyNode(assemblyRoot, nodeId) || null;
    const label = String(
      node?.displayName ||
      node?.name ||
      node?.label ||
      nodeId
    ).trim();
    const leafIds = renderPartIdsForAssemblySelection(nodeId, pickedPartId);
    const hidden = leafIds.length > 0 && leafIds.every((id) => hiddenPartIds.includes(id));
    const focused = focusedAssemblyNodeIds.includes(nodeId);
    const selected = selectedPartIdsRef.current.includes(nodeId);
    const actionNodeIds = uniqueStringList([
      ...selectedPartIdsRef.current
        .map((id) => String(id || "").trim())
        .filter(Boolean),
      nodeId
    ]);
    const fitReferenceIds = uniqueStringList(
      selectedReferenceIdsRef.current
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    const fitPartIds = uniqueStringList([
      ...actionNodeIds.flatMap((id) => renderPartIdsForAssemblySelection(
        id,
        id === nodeId ? pickedPartId : id
      ))
    ]);
    const fitAvailable = fitReferenceIds.length > 0 || fitPartIds.length > 0;
    const expansionState = buildStepTreeExpansionMenuState({
      root: displayStepTreeRoot,
      isAssemblyView,
      expandedTreeNodeIds: expandedStepTreeNodeIds,
      loadableTreeNodeIds: loadableStepTreeTopologyNodeIds,
      actionNodeIds
    });
    const contextCopyReference = stepTreeCopyReferenceMap.get(nodeId) ||
      copyReferenceForStepTreeNodeSelection(node, nodeId, "assembly-part") ||
      copyReferenceForAssemblyPartSelection(node, nodeId) ||
      copyReferenceForRawSelectorSelection(nodeId, "assembly-part");
    const { lines } = copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
      references: contextCopyReference ? [contextCopyReference] : [],
      parts: [],
      entry: selectedEntry
    }), {
      selectedPartIds: actionNodeIds,
      copyReferenceMap: stepTreeCopyReferenceMap
    });
    setViewerContextMenu({
      x: Number(clientX) || 0,
      y: Number(clientY) || 0,
      nodeId,
      renderPartId: pickedPartId,
      label,
      selected,
      hidden,
      focused,
      actionNodeIds,
      actionCount: actionNodeIds.length || 1,
      copyText: lines[0] || "",
      selectDisabled: !selected && hidden,
      showIsolate: true,
      isolateDisabled: false,
      showExitAllIsolate: focusedAssemblyNodeIds.length > 1,
      exitAllIsolateDisabled: focusedAssemblyNodeIds.length < 2,
      showHideOther: true,
      hideOtherDisabled: hidden,
      showVisibility: !focused,
      visibilityDisabled: focused,
      showHideAll: false,
      hideAllDisabled: false,
      hideAllLabel: "Show all",
      showCameraActions: true,
      zoomToFitDisabled: !fitAvailable,
      fitPartIds,
      fitReferenceIds,
      showExpandCollapse: expansionState.showExpandCollapse,
      collapsedActionNodeIds: expansionState.collapsedActionNodeIds,
      expandedActionNodeIds: expansionState.expandedActionNodeIds,
      collapsedExpandableTreeNodeIds: expansionState.collapsedExpandableTreeNodeIds,
      expandedExpandableTreeNodeIds: expansionState.expandedExpandableTreeNodeIds,
      expandSelectedDisabled: expansionState.collapsedActionNodeIds.length < 1,
      collapseSelectedDisabled: expansionState.expandedActionNodeIds.length < 1,
      expandAllDisabled: expansionState.collapsedExpandableTreeNodeIds.length < 1,
      collapseAllDisabled: expansionState.expandedExpandableTreeNodeIds.length < 1
    });
  }, [
    assemblyPartMap,
    assemblyRoot,
    displayStepTreeRoot,
    focusedAssemblyNodeIds,
    effectiveActiveReferenceMap,
    hiddenPartIds,
    isAssemblyView,
    isViewerTopologyReference,
    loadableStepTreeTopologyNodeIds,
    renderPartIdsForAssemblySelection,
    openGlobalViewerContextMenu,
    resolvePickedAssemblyPartId,
    selectedEntry,
    stepTreeCopyReferenceMap,
    expandedStepTreeNodeIds,
    stepInteractionBlocked,
    stepModuleTreeSelectionDisabled,
    viewerInAssemblyMode
  ]);

  const copyViewerContextMenuReference = useCallback(async (menu) => {
    if (stepInteractionBlocked) {
      setCopyStatus(retainedPreviousStepMeshError
        ? "Selection unavailable because the STEP update failed."
        : "STEP update in progress. Please wait.");
      return;
    }
    const copyText = String(menu?.copyText || "")
      .split("\n")
      .map((line) => canonicalCadRefCopyText(line))
      .filter(Boolean)
      .join("\n");
    if (!copyText) {
      setCopyStatus("No selector ref is available for this node");
      return;
    }
    try {
      await deliverReferenceText(copyText);
      setCopyStatus("Copied reference");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, [deliverReferenceText, retainedPreviousStepMeshError, stepInteractionBlocked]);

  const copyStepTreeContextMenuReference = useCallback(async (id, { topology = false, toPrompt = false } = {}) => {
    if (stepInteractionBlocked) {
      setCopyStatus(retainedPreviousStepMeshError
        ? "Selection unavailable because the STEP update failed."
        : "STEP update in progress. Please wait.");
      return;
    }
    const normalizedId = String(id || "").trim();
    if (!normalizedId) {
      setCopyStatus("No selector ref is available for this node");
      return;
    }
    const wholeStepEntryReference = !topology && !isAssemblyView && normalizedId === STEP_MODEL_ROOT_ID
      ? buildWholeStepEntryCopyReference(selectedEntry)
      : null;
    const reference = topology
      ? stepTreeCopyReferenceMap.get(normalizedId) ||
        effectiveActiveReferenceMap.get(normalizedId) ||
        copyReferenceForRawSelectorSelection(normalizedId, "topology") ||
        null
      : null;
    const partReference = !topology && !wholeStepEntryReference
      ? stepTreeCopyReferenceMap.get(normalizedId) ||
        copyReferenceForStepTreeNodeSelection(
          copyableStepTreeNodeForWorkspace({
            assemblyPartMap,
            displayStepTreeRoot,
            stepTreeRoot,
            nodeId: normalizedId
          }),
          normalizedId,
          "assembly-part"
        ) ||
        copyReferenceForAssemblyPartSelection(
          copyableStepTreeNodeForWorkspace({
            assemblyPartMap,
            displayStepTreeRoot,
            stepTreeRoot,
            nodeId: normalizedId
          }),
          normalizedId
        ) ||
        copyReferenceForRawSelectorSelection(normalizedId, "assembly-part")
      : null;
    const { lines } = copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
      references: [
        ...(wholeStepEntryReference ? [wholeStepEntryReference] : []),
        ...(reference ? [reference] : []),
        ...(partReference ? [partReference] : [])
      ],
      parts: [],
      entry: selectedEntry
    }), {
      selectedReferenceIds: topology ? [normalizedId] : [],
      selectedPartIds: topology ? [] : [normalizedId],
      copyReferenceMap: stepTreeCopyReferenceMap
    });
    const copyText = canonicalCadRefCopyText(lines[0]);
    if (!copyText) {
      setCopyStatus("No selector ref is available for this node");
      return;
    }
    try {
      if (toPrompt) addReferenceText(copyText);
      else {
        await deliverReferenceText(copyText);
        setCopyStatus("Copied reference");
      }
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, [
    deliverReferenceText,
    addReferenceText,
    assemblyPartMap,
    displayStepTreeRoot,
    effectiveActiveReferenceMap,
    isAssemblyView,
    retainedPreviousStepMeshError,
    selectedEntry,
    stepInteractionBlocked,
    stepTreeCopyReferenceMap,
    stepTreeRoot
  ]);

  const selectViewerContextMenuNode = useCallback((menu) => {
    const referenceId = String(menu?.referenceId || "").trim();
    if (referenceId) {
      const actionReferenceIds = uniqueStringList(
        (Array.isArray(menu?.referenceIds) ? menu.referenceIds : [referenceId])
          .map((id) => String(id || "").trim())
          .filter(Boolean)
      );
      if (menu?.selected === true && actionReferenceIds.length > 1) {
        clearReferenceSelection();
        return;
      }
      toggleReferenceSelection(referenceId, { multiSelect: false });
      return;
    }
    const nodeId = String(menu?.nodeId || "").trim();
    if (!nodeId) {
      return;
    }
    const actionNodeIds = uniqueStringList(
      (Array.isArray(menu?.actionNodeIds) ? menu.actionNodeIds : [nodeId])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    if (menu?.selected === true) {
      if (actionNodeIds.length > 1) {
        clearAssemblySelection();
        return;
      }
      removeSelectedAssemblyNode(nodeId);
      return;
    }
    togglePartSelection(nodeId, {
      renderPartId: String(menu?.renderPartId || "").trim(),
      source: "viewer"
    });
  }, [
    clearAssemblySelection,
    clearReferenceSelection,
    removeSelectedAssemblyNode,
    focusedAssemblyNodeIds,
    togglePartSelection,
    toggleReferenceSelection
  ]);

  const focusViewerContextMenuNode = useCallback((menu) => {
    const nodeId = String(menu?.nodeId || "").trim();
    if (!nodeId) {
      return;
    }
    if (menu?.focused === true) {
      handleExitSingleIsolate(nodeId);
      return;
    }
    const actionNodeIds = uniqueStringList(
      (Array.isArray(menu?.actionNodeIds) ? menu.actionNodeIds : [nodeId])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    focusStepTreeNode(actionNodeIds);
  }, [
    focusStepTreeNode,
    handleExitSingleIsolate
  ]);

  const hideViewerContextMenuNode = useCallback((menu) => {
    const nodeId = String(menu?.nodeId || "").trim();
    if (!nodeId) {
      return;
    }
    const actionNodeIds = uniqueStringList(
      (Array.isArray(menu?.actionNodeIds) ? menu.actionNodeIds : [nodeId])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    if (menu?.selected === true && actionNodeIds.length > 1) {
      handleHideSelectedParts();
      return;
    }
    for (const actionNodeId of actionNodeIds) {
      hideStepTreeNode(actionNodeId);
    }
  }, [handleHideSelectedParts, hideStepTreeNode]);

  const revealViewerContextMenuNode = useCallback((menu) => {
    const nodeId = String(menu?.nodeId || "").trim();
    if (!nodeId) {
      return;
    }
    const actionNodeIds = uniqueStringList(
      (Array.isArray(menu?.actionNodeIds) ? menu.actionNodeIds : [nodeId])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    for (const actionNodeId of actionNodeIds) {
      revealHiddenStepTreeNode(actionNodeId);
    }
  }, [revealHiddenStepTreeNode]);

  const hideOtherViewerContextMenuNode = useCallback((menu) => {
    const nodeId = String(menu?.nodeId || "").trim();
    if (!nodeId) {
      return;
    }
    const actionNodeIds = uniqueStringList(
      (Array.isArray(menu?.actionNodeIds) ? menu.actionNodeIds : [nodeId])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    handleHideOtherTreeNode(actionNodeIds);
  }, [handleHideOtherTreeNode]);

  const hideAllViewerContextMenuNodes = useCallback((menu) => {
    if (menu?.hidden === true) {
      handleShowAllHiddenParts();
      return;
    }
    handleHideAllParts();
  }, [
    handleHideAllParts,
    handleShowAllHiddenParts
  ]);

  const resetZoomViewerContextMenu = useCallback(() => {
    if (!viewerRef.current?.resetZoom?.()) {
      setCopyStatus("CAD Viewer camera not ready");
    }
  }, []);

  const zoomToFitViewerContextMenu = useCallback((menu) => {
    const fitPartIds = uniqueStringList(
      (Array.isArray(menu?.fitPartIds) ? menu.fitPartIds : [])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    const fitReferenceIds = uniqueStringList(
      (Array.isArray(menu?.fitReferenceIds) ? menu.fitReferenceIds : [])
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    // The global menu has no narrower target by construction, so it asks for the model.
    // A part menu that resolved no ids is a real failure and still says so.
    const fitWholeModel = menu?.fitWholeModel === true;
    if (!fitWholeModel && !fitPartIds.length && !fitReferenceIds.length) {
      setCopyStatus("No geometry to fit");
      return;
    }
    if (!viewerRef.current?.zoomToFitSelection?.({
      partIds: fitPartIds,
      referenceIds: fitReferenceIds,
      fallbackToModel: fitWholeModel,
      animate: true
    })) {
      setCopyStatus("No geometry to fit");
    }
  }, []);

  const expandSelectedViewerContextMenuNodes = useCallback((menu) => {
    for (const nodeId of Array.isArray(menu?.collapsedActionNodeIds) ? menu.collapsedActionNodeIds : []) {
      toggleStepTreeNode(nodeId);
    }
  }, [toggleStepTreeNode]);

  const collapseSelectedViewerContextMenuNodes = useCallback((menu) => {
    for (const nodeId of Array.isArray(menu?.expandedActionNodeIds) ? menu.expandedActionNodeIds : []) {
      toggleStepTreeNode(nodeId);
    }
  }, [toggleStepTreeNode]);

  const expandAllViewerContextMenuNodes = useCallback((menu) => {
    for (const nodeId of Array.isArray(menu?.collapsedExpandableTreeNodeIds) ? menu.collapsedExpandableTreeNodeIds : []) {
      toggleStepTreeNode(nodeId);
    }
  }, [toggleStepTreeNode]);

  const collapseAllViewerContextMenuNodes = useCallback((menu) => {
    for (const nodeId of Array.isArray(menu?.expandedExpandableTreeNodeIds) ? menu.expandedExpandableTreeNodeIds : []) {
      toggleStepTreeNode(nodeId);
    }
  }, [toggleStepTreeNode]);

  const handleSelectEntry = useCallback((key) => {
    const next = entryMap.get(key);
    onOpenFile?.(next ? cadFileParamForEntry(next) : key);
  }, [entryMap, onOpenFile]);

  const handleSelectTabToolMode = useCallback((mode) => {
    setViewerAlertOpen(false);
    // Anything unrecognized falls back to selection rather than sticking the
    // viewer in a mode with no tool behind it.
    const normalizedMode = mode === TAB_TOOL_MODE.DRAW || mode === TAB_TOOL_MODE.MEASURE || mode === TAB_TOOL_MODE.PAN
      ? mode
      : TAB_TOOL_MODE.REFERENCES;
    setTabToolMode(current => normalizedMode === TAB_TOOL_MODE.MEASURE && current === normalizedMode ? TAB_TOOL_MODE.REFERENCES : normalizedMode);
    if (
      selectedEntry &&
      selectedEntryHasReferences &&
      normalizedMode === TAB_TOOL_MODE.MEASURE && topologyTarget
    ) {
      loadFilterTopology(topologyTarget);
    }
    if (normalizedMode === TAB_TOOL_MODE.DRAW && drawingTool === DRAWING_TOOL.SURFACE_LINE) {
      setDrawingTool(DRAWING_TOOL.FREEHAND);
    }
  }, [drawingTool, selectedEntry, selectedEntryHasReferences, topologyTarget, loadFilterTopology]);

  const handleDrawingStrokesChange = useCallback((nextStrokes) => {
    const normalized = cloneDrawingStrokes(nextStrokes);
    const current = drawingStrokesRef.current;
    if (drawingStrokesEqual(current, normalized)) {
      return;
    }
    setDrawingUndoStack((history) => [...history, cloneDrawingStrokes(current)]);
    setDrawingRedoStack([]);
    setDrawingStrokes(normalized);
  }, []);

  const handleSelectDrawingTool = useCallback((tool) => {
    setTabToolMode(TAB_TOOL_MODE.DRAW);
    setDrawingTool(tool === DRAWING_TOOL.SURFACE_LINE ? DRAWING_TOOL.FREEHAND : tool);
  }, []);

  const handleUndoDrawing = useCallback(() => {
    const history = drawingUndoStackRef.current;
    if (!history.length) {
      return;
    }
    const previous = cloneDrawingStrokes(history[history.length - 1]);
    const current = cloneDrawingStrokes(drawingStrokesRef.current);
    setDrawingUndoStack(history.slice(0, -1));
    setDrawingRedoStack((future) => [...future, current]);
    setDrawingStrokes(previous);
  }, []);

  const handleRedoDrawing = useCallback(() => {
    const future = drawingRedoStackRef.current;
    if (!future.length) {
      return;
    }
    const next = cloneDrawingStrokes(future[future.length - 1]);
    const current = cloneDrawingStrokes(drawingStrokesRef.current);
    setDrawingRedoStack(future.slice(0, -1));
    setDrawingUndoStack((history) => [...history, current]);
    setDrawingStrokes(next);
  }, []);

  const handleClearDrawings = useCallback(() => {
    if (!drawingStrokesRef.current.length) {
      return;
    }
    setDrawingUndoStack((history) => [...history, cloneDrawingStrokes(drawingStrokesRef.current)]);
    setDrawingRedoStack([]);
    setDrawingStrokes([]);
  }, []);

  const handlePerspectiveChange = useCallback((nextPerspective) => {
    const normalizedPerspective = clonePerspectiveSnapshot(nextPerspective);
    if (normalizedPerspective) {
      activePerspectiveRef.current = normalizedPerspective;
      scheduleActiveFileSessionSave();
    }
    // Camera moved: give the LOD scheduler a sample (it debounces internally).
    onLodCameraMoved();
    // Freehand strokes are anchored to the view they were drawn in, so a
    // camera move ends them -- an orbit, Reset view, or the fit a mode switch
    // performs. Render owns no CAD drawing layer, so its camera never does.
    if (renderEnabledRef.current) {
      return;
    }
    const hasPerspectiveDependentDrawings =
      drawingStrokesRef.current.length > 0 ||
      drawingUndoStackRef.current.some((strokes) => strokes.length > 0) ||
      drawingRedoStackRef.current.some((strokes) => strokes.length > 0);
    if (!hasPerspectiveDependentDrawings) {
      return;
    }
    drawingStrokesRef.current = [];
    drawingUndoStackRef.current = [];
    drawingRedoStackRef.current = [];
    setDrawingStrokes([]);
    setDrawingUndoStack([]);
    setDrawingRedoStack([]);
  }, [onLodCameraMoved, scheduleActiveFileSessionSave]);

  const applyActiveCamera = useCallback((camera, { resetZoomBaseline = false } = {}) => {
    let snapshot = null;
    try {
      snapshot = resolveRenderCameraSnapshot(camera, selectedMeshData?.bounds || null, {
        sceneScale: isUrdfView ? "urdf" : "cad"
      });
    } catch {
      snapshot = renderCameraSnapshot(camera);
    }
    if (snapshot) {
      viewerRef.current?.setPerspective?.(snapshot, { resetZoomBaseline });
    }
    const scopedSnapshot = scopedWorkspacePerspective(snapshot, selectedKey, selectedEntry);
    activePerspectiveRef.current = scopedSnapshot;
    setViewerPerspective(scopedSnapshot);
  }, [isUrdfView, selectedEntry, selectedKey, selectedMeshData?.bounds]);

  const handleRenderEnabledChange = useCallback((enabled) => {
    if (enabled === renderSession.enabled) {
      return;
    }
    // The switch carries no camera. Each mode owns a camera of its own -- an
    // orthographic CAD frustum, a photographic lens -- and the viewer fits the
    // one being entered to the model's zero pose (CadViewer's "mode" reframe).
    // Handing it the other mode's pose only produced the framing this reset
    // exists to replace. The session still RECORDS each mode's last camera, for
    // the file session and for a snapshot request; nothing replays it on a
    // switch.
    const activeCamera = readRenderSessionCamera(viewerRef.current, activePerspectiveRef.current);
    if (enabled) {
      // Render's studio and its two settings panels are one lazy chunk. Asking
      // for them here rather than waiting for the viewport effect and the
      // Suspense boundary to ask separately is what keeps the switch to one
      // request; the mode flips immediately either way, and the viewport stays
      // under its destination backdrop until the studio has applied.
      prefetchRenderStudio();
      setTabToolsOpen(true);
      renderEnabledRef.current = true;
      setRenderSession(renderSessionForEnabledChange(renderSession, true, {
        activeCamera,
        activeProjection: resolvedScene.camera.projection
      }));
      setTabToolsOpen(true);
      return;
    }

    renderEnabledRef.current = false;
    // The projection travels, because orthographic-or-perspective is an Inspect
    // display choice rather than a pose; the fit applies it to the new frame.
    setRenderSession(renderSessionForEnabledChange(renderSession, false, {
      activeCamera,
      activeProjection: resolvedScene.camera.projection
    }));
  }, [
    renderSession,
    resolvedScene.camera.projection,
    setTabToolsOpen
  ]);

  const handleRenderQualityChange = useCallback((quality) => {
    setRenderSession((current) => createRenderSessionState({
      ...current,
      payload: { ...current.payload, quality }
    }));
  }, []);

  const handleRenderPayloadValueChange = useCallback((path, value) => {
    setRenderSession((current) => createRenderSessionState({
      ...current,
      payload: setRenderPayloadValue(
        path?.[0] === "camera"
          ? {
              ...current.payload,
              camera: renderCameraSeed(activePerspectiveRef.current) || current.payload.camera || {}
            }
          : current.payload,
        path,
        value
      )
    }));
  }, []);

  const handleProjectionChange = useCallback((projection) => {
    const camera = renderCameraSnapshot(activePerspectiveRef.current);
    if (renderSession.enabled) {
      const payload = {
        ...renderSession.payload,
        camera: {
          ...(renderCameraSeed(camera) || renderSession.payload.camera || {}),
          projection
        }
      };
      setRenderSession(createRenderSessionState({ ...renderSession, payload }));
    } else {
      setRenderSession(createRenderSessionState({
        ...renderSession,
        cadCamera: camera ? { ...camera, projection } : renderSession.cadCamera,
        cadProjection: projection
      }));
    }
    if (camera) {
      applyActiveCamera({ ...camera, projection });
    }
  }, [applyActiveCamera, renderSession]);

  const handleRenderReset = useCallback(() => {
    const camera = renderCameraSnapshot(activePerspectiveRef.current);
    const next = renderSessionForReset(renderSession, { activeCamera: camera });
    setRenderSession(next);
  }, [renderSession]);

  useCadWorkspaceShortcuts({
    viewerElement,
    selectionActive: selectedPartIds.length > 0 || selectedReferenceIds.length > 0,
    onClearSelection: clearAssemblySelection,
    copyStatus,
    screenshotStatus,
    setCopyStatus,
    setScreenshotStatus,
    previewMode,
    inspectionEnabled: !renderSession.enabled,
    viewerAlertOpen,
    tabToolsOpen,
    isDesktop: isWideLayout,
    filesPanelOpen,
    previewUiStateRef,
    tabToolMode,
    measureDraftActive: Boolean(measureRulerState?.draft?.anchor),
    onCancelMeasureDraft: handleMeasureCancelDraft,
    drawingUndoStackRef,
    drawingRedoStackRef,
    handleUndoDrawing,
    handleRedoDrawing,
    setPreviewMode,
    setViewerAlertOpen,
    setTabToolsOpen,
    setFilesPanelOpen,
    setTabToolMode
  });

  // Freeze references now; the host binds its destination before waiting for the PNG.
  const handleCapture = useCallback(() => {
    if (!selectedEntry || !promptAvailable || viewerLoading || stepInteractionBlocked) return;
    try {
      if (!viewerRef.current?.captureScreenshotBlob) throw new Error("CAD Viewer not ready");
      const references = referencesForHost(canonicalCopySelectionLines.join("\n"));
      const capture = viewerRef.current.captureScreenshotBlob();
      void capture.catch(() => {});
      void deliverPrompt(createCadPromptContext({ resource: promptResource, references, capture }));
    } catch (error) { setScreenshotStatus(error instanceof Error ? error.message : "Capture failed"); }
  }, [promptAvailable, promptResource, viewerLoading, stepInteractionBlocked, deliverPrompt, selectedEntry, referencesForHost, canonicalCopySelectionLines]);

  const captureKey = captureRequest?.key ?? null;
  const appliedCaptureKeyRef = useRef(null);
  useEffect(() => {
    if (captureKey === null || appliedCaptureKeyRef.current === captureKey || viewerLoading || stepInteractionBlocked || !promptAvailable) return;
    appliedCaptureKeyRef.current = captureKey;
    acknowledgeCommand?.('captureRequest', captureKey);
    handleCapture();
  }, [captureKey, viewerLoading, stepInteractionBlocked, promptAvailable, acknowledgeCommand, handleCapture]);

  const handleScreenshotCopy = useCallback(async () => {
    if (!selectedEntry) return;
    try {
      if (!viewerRef.current?.captureScreenshotBlob) throw new Error("CAD Viewer not ready");
      await host.clipboard.writeImage(viewerRef.current.captureScreenshotBlob());
      setCopyStatus("");
      setScreenshotStatus("Copied screenshot to clipboard");
    } catch (error) { setScreenshotStatus(error instanceof Error ? error.message : "Clipboard copy failed"); }
  }, [selectedEntry, host.clipboard]);

  const handleEnterPreviewMode = useCallback(() => {
    const viewportContent = selectedViewportContent;
    if (viewerLoading || !viewportContent || previewMode) {
      return;
    }
    previewUiStateRef.current = {
      filesPanelOpen,
      tabToolsOpen,
      tabToolMode,
      viewerAlertOpen
    };
    setCopyStatus("");
    setScreenshotStatus("");
    setDrawingStrokes([]);
    setDrawingUndoStack([]);
    setDrawingRedoStack([]);
    setViewerAlertOpen(false);
    setFilesPanelOpen(false);
    setTabToolsOpen(false);
    setPreviewMode(true);
  }, [
    previewMode,
    filesPanelOpen,
    setTabToolsOpen,
    selectedViewportContent,
    tabToolMode,
    tabToolsOpen,
    viewerAlertOpen,
    viewerLoading
  ]);

  // Exit fullscreen and restore the pre-preview UI, from the floating
  // toolbar's "Exit fullscreen" button. Mirrors the Escape-key exit in
  // useCadWorkspaceShortcuts; keep the two restore paths in sync.
  const handleExitPreviewMode = useCallback(() => {
    if (!previewMode) {
      return;
    }
    const previousUiState = previewUiStateRef.current;
    previewUiStateRef.current = null;
    setPreviewMode(false);
    if (previousUiState) {
      setViewerAlertOpen(previousUiState.viewerAlertOpen);
      setFilesPanelOpen(previousUiState.filesPanelOpen);
      setTabToolsOpen(previousUiState.tabToolsOpen);
      setTabToolMode(previousUiState.tabToolMode);
    }
  }, [
    previewMode,
    setFilesPanelOpen,
    setTabToolMode,
    setTabToolsOpen,
    setViewerAlertOpen
  ]);

  const selectionToolActive = hasCapability(effectiveRenderFormat, "topology") &&
    tabToolMode === TAB_TOOL_MODE.REFERENCES;
  const drawToolActive = drawModeActive;
  const canAddInspectionContext = promptAvailable &&
    inspectionHighlight?.context?.file === selectedEntry?.file;
  let selectionCount = selectionCountBase;
  if (inspectionHighlight) {
    selectionCount = 0;
    if (inspectionHighlight.label && !viewerLoading && !stepUpdateInProgress) {
      if (canAddInspectionContext) selectionCount = inspectionHighlight.faceIds.length + inspectionHighlight.partIds.length;
      else if (promptAvailable) selectionCount = inspectionHighlight.faceIds.length + inspectionHighlight.partIds.length;
    }
  }
  const activeReferenceId = String(selectedReferenceIds[selectedReferenceIds.length - 1] || "").trim();
  const activeReferencePartTreeNodeId = useMemo(() => {
    if (!activeReferenceId) {
      return "";
    }
    return referencePartId(effectiveActiveReferenceMap.get(activeReferenceId));
  }, [
    activeReferenceId,
    effectiveActiveReferenceMap,
    referencePartId
  ]);
  const activeReferenceTreeNodeId = useMemo(() => {
    if (!activeReferenceId) {
      return "";
    }
    return findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, activeReferenceId) ||
      activeReferencePartTreeNodeId;
  }, [
    activeReferenceId,
    activeReferencePartTreeNodeId,
    displayStepTreeRoot
  ]);
  const activeStepTreeNodeId = selectedPartIds[selectedPartIds.length - 1] ||
    activeReferenceTreeNodeId;
  const canUndoDrawing = drawingUndoStack.length > 0;
  const canRedoDrawing = drawingRedoStack.length > 0;
  const fileSheetOpen = !!selectedFileSheetKind && selectedFileSheetHasSections && tabToolsOpen && !previewMode;
  /**
   * Nothing open, and nothing on its way in: the shared empty state, drawn
   * over the render pane's box.
   *
   * The same condition the "home screen" used to have — this is what replaced
   * it. A file that is still being resolved out of the catalog, or one named
   * in the URL that the catalog does not have, are both something else and
   * have their own answers.
   */
  const emptyVisible = !previewMode && !selectedEntry && !missingFileRef && !fileParamSelectionPending;
  const activeSheetWidth = resolveDesktopPanelWidth({
    open: desktopRightPanelOpen,
    width: tabToolsWidth,
    minWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
    maxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
  });
  const floatingCadToolbarPosition = {
    top: "14px",
    right: "14px"
  };
  const drawingToolOptions = [
    { id: DRAWING_TOOL.FREEHAND, label: "Freehand", Icon: PenTool },
    { id: DRAWING_TOOL.LINE, label: "Line", Icon: Minus },
    { id: DRAWING_TOOL.ARROW, label: "Arrow", Icon: ArrowRight },
    { id: DRAWING_TOOL.DOUBLE_ARROW, label: "Expand", Icon: ArrowLeftRight },
    { id: DRAWING_TOOL.RECTANGLE, label: "Rectangle", Icon: Square },
    { id: DRAWING_TOOL.CIRCLE, label: "Circle", Icon: Circle },
    { id: DRAWING_TOOL.FILL, label: "Fill", Icon: PaintBucket },
    { id: DRAWING_TOOL.ERASE, label: "Erase", Icon: Eraser }
  ];
  // Handed over unconditionally: the pane gates it on the `displayModes` capability, so
  // gating it a second time here only creates a place for the two to disagree.
  const renderDisplaySettings = resolvedScene.display;
  const materialPickingEnabled = fileSheetOpen && renderSession.enabled && selectedFileSheetKind === "step" && effectiveFileSheetOpenSectionIds.includes(FILE_SHEET_SECTION_IDS.MATERIALS);
  const materialParts = materialSession.withViewerSelection(viewerSelectedPartIds);
  const settingsTabs = [
    supportsDisplayModes && !renderSession.enabled
      ? buildDisplaySettingsTab({
          displaySettings: resolvedScene.display,
          updateDisplaySettings,
          projection: resolvedScene.camera.projection,
          onProjectionChange: handleProjectionChange,
          clipBounds: selectedMeshData?.bounds || null,
          explodeMeshData: selectedMeshData || null,
          edgeStatus: displayEdgeStatus,
          edgeError: displayEdgeError
        })
      : null,
    renderSession.enabled ? buildRenderSettingsTab({
      scene: resolvedScene,
      onQualityChange: handleRenderQualityChange,
      onPayloadValueChange: handleRenderPayloadValueChange,
      onReset: handleRenderReset
    }) : null,
    renderSession.enabled ? buildMaterialsSettingsTab({
      appearance: selectedSourceAppearance,
      overlay: materialSession.overlay,
      undo: materialSession.undo,
      targets: materialSession.targets,
      scope: materialSession.scope,
      enabled: materialSession.enabled,
      selectedPartIds: materialParts.selectedIds,
      onSelectParts: materialParts.select,
      onOverlayChange: materialSession.change,
      onUndo: materialSession.undoLast,
      onReset: materialSession.reset
    }) : null
  ].filter(Boolean);

  return (
    <FileSheetTabPreferencesContext.Provider value={{ store: preferences.fileSheetTabs || {}, update: (fileSheetTabs) => onPreferenceChange({ fileSheetTabs }) }}>
    <HostPanelSlotContext.Provider value={hostPanelSlot}>
    <FileSheetPortalContext.Provider value={hostElement}>
    <HostReferenceContext.Provider value={hostReference}>
    <div
      className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground", className)}
      data-slot="cad-file-view"
      data-cad-surface
      tabIndex={-1}
      onPointerDownCapture={event => {
        if (event.target instanceof Element && event.target.closest("canvas")) { setInspectionHighlight(null); event.currentTarget.focus({ preventScroll: true }); }
      }}
      ref={hostRef}
    >
      <div className="relative z-10 flex h-full min-w-0 flex-col overflow-hidden bg-transparent">

        <div className="relative min-h-0 flex-1 overflow-hidden">
          <div className="flex h-full min-w-0">
            {/* The render pane's box: the column left of the panel column, and
                nothing else. The WebGL canvas fills exactly this
                area, so a camera fit centres in what is visible and a sheet
                opening or closing reaches the scene as a plain resize. The
                overlays after it (toolbar, home, loading) sit above it in the
                same box and let the pointer through to it between them.

                Its own background is the scene's edge colour, not the app's:
                the canvas is opaque and covers all of this, but it is resized
                on the next frame, and one frame of the chrome's background
                showing above a dark stage is a visible band. It is also the
                only place outside the renderer where the chosen backdrop can
                be read (chromeBackdrop.js). */}
            <div
              className="pointer-events-none relative min-w-0 flex-1 overflow-hidden"
              data-cad-scene-backdrop={sceneBackdrop}
              style={{ backgroundColor: sceneBackdrop }}
            >
              <div className="pointer-events-auto absolute inset-0 z-0">
                <CadRenderPane
                onReload={onReload}
                viewerRef={viewerRef}
                renderFormat={effectiveRenderFormat}
                drawingThicknessScale={renderSession.enabled && selectedEntryIsDrawing
            ? DXF_DEFAULT_THICKNESS_MM / DXF_PREVIEW_REFERENCE_THICKNESS_MM
            : drawingThicknessScale}
                planMode={selectedEntryIsDrawing && drawingViewMode === "2d"}
                bendAxisX={selectedEntryIsDrawing ? selectedEntry?.bendAxisX || null : null}
                drawingBendLines={selectedEntryIsDrawing ? drawingBendLines : null}
                bendAnglesRad={selectedEntryIsDrawing
            ? (renderSession.enabled ? EMPTY_LIST : drawingBendAnglesRad)
            : null}
                drawingBends={selectedEntryIsDrawing
            ? (renderSession.enabled ? EMPTY_LIST : drawingBends)
            : null}
                drawingBendStyle={selectedEntryIsDrawing && !renderSession.enabled
            ? drawingBendStyle
            : DXF_DEFAULT_BEND_STYLE}
                drawingBendRadiusMm={selectedEntryIsDrawing && !renderSession.enabled
            ? drawingBendRadiusMm
            : DXF_DEFAULT_BEND_RADIUS_MM}
                drawingKFactor={selectedEntryIsDrawing && !renderSession.enabled
            ? drawingKFactor
            : DXF_DEFAULT_KFACTOR}
                drawingHiddenLayers={selectedEntryIsDrawing
            ? (renderSession.enabled ? EMPTY_LIST : drawingHiddenLayers)
            : null}
                drawingOrientation={selectedEntryIsDrawing
            ? (renderSession.enabled ? DXF_DEFAULT_ORIENTATION : drawingOrientation)
            : null}
                drawingMaterialColor={selectedEntryIsDrawing && !renderSession.enabled
            ? dxfMaterialPreset(drawingMaterial).colorHex
            : null}
                drawingGeometry={selectedEntryIsDrawing ? drawingGeometry : null}
                drawingIsDocument={selectedEntryIsDrawingDocument}
                drawingSvgUrl={drawingSvgUrl}
          sheetEditTool={selectedEntryIsDrawingDocument ? drawingEditTool : ""}
          sheetEditViews={drawingShiftedViews}
          sheetEditSnapTargets={drawingSnapTargets}
          sheetEditPickedPoints={drawingPickedPoints}
          onSheetEditPick={handleDrawingSheetPick}
          onSheetEditViewMove={handleDrawingViewMove}
                drawingThicknessMm={selectedEntryIsDrawing && !renderSession.enabled
            ? drawingThicknessMm
            : DXF_DEFAULT_THICKNESS_MM}
                onCameraZoomPercentChange={setViewerZoomPercent}
                onLodCameraChange={onLodCameraMoved}
                onMeshSourceAdoption={handleDisplayMeshAdoption}
                materialPickingEnabled={materialPickingEnabled}
                onMaterialPartActivate={materialParts.activate}
                renderPartsIndividually={
            isUrdfView || Boolean(selectedStepParameterRuntime) || Boolean(selectedAnimationRuntime) ||
            sourceAppearanceHasMaterials(selectedDisplayMeshData?.appearance)
          }
                stepParameters={selectedStepParameterRuntime}
                stepAnimation={selectedAnimationRuntime}
                glbDocument={selectedGlbDocument}
                embeddedGlbAnimation={embeddedGlbAnimationRuntime?.render || null}
                selectedMeshData={selectedDisplayMeshData}
                selectedKey={selectedKey}
                missingFileRef={editingPreview.entry ? "" : missingFileRef}
                viewerServerInfo={viewerServerInfo}
                viewerPerspective={viewerPerspective}
                viewerPerspectiveRef={activePerspectiveRef}
                projection={resolvedScene.camera.projection}
                focalLength={resolvedScene.camera.focalLength}
                themeSettings={resolvedThemeSettings}
                appearance={resolvedScene.appearance}
                materialOverrides={resolvedMaterialOverrides}
                receiveShadows={resolvedScene.render.enabled}
                renderMode={resolvedScene.render.enabled}
                renderConfiguration={resolvedScene.render.configuration}
                quality={resolvedScene.quality}
                displaySettings={renderDisplaySettings}
                previewMode={previewMode}
                viewerLoading={viewerLoading}
                retainingPreviousStepMesh={retainingPreviousStepMesh}
                viewerAlert={viewerAlert}
                onPresentationChange={handlePresentationChange}
                presentationKey={presentationKey}
                loadingPresentation={loading}
                stepUpdateInProgress={effectiveRenderFormat === RENDER_FORMAT.STEP && stepUpdateInProgress}
                referenceSelectionPending={referenceSelectionPending}
                referenceSelectionUnavailable={referenceSelectionUnavailable}
                referenceSelectionDeferred={selectedTopologyDeferredByCost}
                viewerMode={robotComponentsActive ? "assembly" : viewerMode}
                robotComponentPicking={robotComponentsActive}
                assemblyPickingActive={robotComponentsActive || viewerInAssemblyMode}
                assemblyParts={robotComponentsActive ? (selectedUrdfPreview.meshData?.parts || EMPTY_LIST) : viewerAssemblyRenderParts}
                hiddenPartIds={viewerHiddenPartIds}
                selectedPartIds={robotComponentsActive ? robotSelection.selectedIds : inspectionHighlight ? inspectionHighlight.partIds : viewerSelectedPartIds}
                hoveredPartId={robotComponentsActive ? robotSelection.hoveredId : viewerHoveredPartIds}
                hoveredReferenceId={effectiveHoveredReferenceId}
                selectedReferenceIds={inspectionHighlight ? inspectionHighlight.faceIds : selectedReferenceIds}
                selectorRuntime={effectiveSelectorRuntime}
                displayEdgeRuntime={selectedDisplayEdgeRuntime}
                pickableFaces={measureModeActive ? (["all", "faces"].includes(measureSelectionFilter) ? viewerPickableFaces : EMPTY_LIST) : filteredViewerFaces}
                pickableEdges={measureModeActive ? (["all", "edges"].includes(measureSelectionFilter) ? viewerPickableEdges : EMPTY_LIST) : filteredViewerEdges}
                pickableVertices={(measureModeActive ? ["all", "points"].includes(measureSelectionFilter) : selectionFilter === "all") ? viewerPickableVertices : EMPTY_LIST}
                focusedPartIds={viewerFocusedPartIds}
                boundsAnimationActive={robotBoundsAnimationActive}
                drawToolActive={drawToolActive}
                measureModeActive={measureModeActive}
                drawingTool={drawingTool}
                drawingStrokes={drawingStrokes}
                handleDrawingStrokesChange={handleDrawingStrokesChange}
                handlePerspectiveChange={handlePerspectiveChange}
                handleModelHoverChange={robotComponentsActive ? robotSelection.hover : handleModelHoverChange}
                handleModelReferenceActivate={robotComponentsActive ? selectRobotComponent : handleModelReferenceActivate}
                handleModelReferenceDoubleActivate={robotComponentsActive ? undefined : handleModelReferenceDoubleActivate}
                handleModelReferenceContext={robotComponentsActive ? undefined : handleModelReferenceContext}
                onMeasurePick={handleMeasurePick}
                onMeasureHoverPoint={handleMeasureHoverPoint}
                activeMeasurementId={inspectionHighlight?.measurement?.id || activeMeasureId}
                measureState={inspectionHighlight?.measurement ? { measurements: [inspectionHighlight.measurement] } : measureRulerState}
                viewerContextMenu={viewerContextMenu}
                onViewerContextMenuClose={closeViewerContextMenu}
                onViewerContextMenuCopyReference={copyViewerContextMenuReference}
                onViewerContextMenuSelect={selectViewerContextMenuNode}
                onViewerContextMenuFocus={focusViewerContextMenuNode}
                onViewerContextMenuExitAllIsolate={handleExitIsolate}
                onViewerContextMenuHideOther={hideOtherViewerContextMenuNode}
                onViewerContextMenuHideAll={hideAllViewerContextMenuNodes}
                onViewerContextMenuHide={hideViewerContextMenuNode}
                onViewerContextMenuReveal={revealViewerContextMenuNode}
                onViewerContextMenuResetZoom={resetZoomViewerContextMenu}
                onViewerContextMenuZoomToFit={zoomToFitViewerContextMenu}
                onViewerContextMenuExpandSelected={expandSelectedViewerContextMenuNodes}
                onViewerContextMenuCollapseSelected={collapseSelectedViewerContextMenuNodes}
                onViewerContextMenuExpandAll={expandAllViewerContextMenuNodes}
                onViewerContextMenuCollapseAll={collapseAllViewerContextMenuNodes}
                handleViewerAlertChange={handleViewerAlertChange}
                handleStepModuleTransformDetectedChange={handleStepModuleTransformDetectedChange}
                selectionCount={selectionCount}
                copyButtonLabel={copyButtonLabel}
                copyButtonCountLabel={copyButtonCountLabel}
                panToolActive={panToolActive}
                handleCopySelection={handleCopySelection}
                handleScreenshotCopy={handleScreenshotCopy}
                selectionFilter={selectionFilter}
                createPromptContext={createSelectionPromptContext}
                onPromptResult={showPromptResult}
                composerDestination={composerDestination}
                selectionExtras={slots?.selectionExtras && selectionCount > 0 && !viewerLoading && !stepInteractionBlocked ? <slots.selectionExtras
                  selection={Object.freeze(createSelectionPromptContext().parts.filter(part => part.kind === 'reference').map(part => part.reference))}
                  selectionKey={selectionKey}
                  disabled={viewerLoading || stepInteractionBlocked || !promptAvailable}
                  createContext={createSelectionPromptContext}
                /> : null}
              />
              </div>

              <FloatingToolBar
                onRenderModeChange={handleRenderEnabledChange}
                previewMode={previewMode}
                renderMode={renderSession.enabled}
                selectedEntry={selectedEntry}
                renderFormat={effectiveRenderFormat}
                floatingCadToolbarPosition={floatingCadToolbarPosition}
                drawingViewToggle={selectedEntryIsDrawing}
                drawingViewMode={drawingViewMode}
                onDrawingViewModeChange={handleDrawingViewModeChange}
                zoomControlsVisible={!!selectedViewportContent}
                zoomPercent={viewerZoomPercent}
                onZoomPercentChange={handleViewerZoomPercentChange}
                onZoomReset={handleViewerZoomReset}
                selectionFilter={supportsTopology ? selectionFilter : null}
                onSelectionFilterChange={value => { setSelectionFilter(value); handleSelectTabToolMode("references"); }}
                selectionFilterNotice={selectionFilterNotice}
                selectionToolActive={selectionToolActive}
                referenceSelectionPending={referenceSelectionPending}
                referenceSelectionUnavailable={referenceSelectionUnavailable}
                referenceSelectionDeferred={selectedTopologyDeferredByCost}
                animationAvailable={!!activeAnimationRuntime?.available}
                animationPlaying={!!activeAnimationRuntime?.playing}
                animationDisabled={!!activeAnimationRuntime?.disabled}
                handleAnimationPlayToggle={activeAnimationRuntime?.onPlayToggle}
                drawToolActive={drawToolActive}
                measureModeActive={measureModeActive}
                displayPanel={supportsDisplayModes ? settingsTabs.find(tab => tab.id === FILE_SHEET_SECTION_IDS.DISPLAY)?.content : null}
                measurementPanel={supportsTopology && supportsMeasure ? <>
                  <div className="py-1">
                    <p className="px-2 py-1 text-micro text-muted-foreground">Snap to</p>
                    <SelectionFilterMenu fullWidth options={MEASURE_SELECTION_FILTERS} menuLabel="Measure selection filter" hint="" value={measureSelectionFilter} onChange={value => {
                      setMeasureSelectionFilter(value); handleMeasureCancelDraft();
                      if (topologyTarget) loadFilterTopology(topologyTarget);
                    }} />
                  </div>
                  <StepMeasurementsSection
                  measurements={measureMeasurements} activeId={activeMeasureId} measureModeActive={measureModeActive}
                  onActivate={setActiveMeasureId} onDelete={handleMeasureDelete} onClear={handleMeasureClear}
                /></> : null}
                measureSupported={effectiveSupportsMeasure}
                measureDisabled={measureToolDisabled}
                panToolActive={panToolActive}
                handleSelectTabToolMode={handleSelectTabToolMode}
                viewerLoading={viewerLoading}
                selectedMeshData={selectedMeshData}
                drawingToolOptions={drawingToolOptions}
                drawingTool={drawingTool}
                handleSelectDrawingTool={handleSelectDrawingTool}
                handleUndoDrawing={handleUndoDrawing}
                handleRedoDrawing={handleRedoDrawing}
                handleClearDrawings={handleClearDrawings}
                canUndoDrawing={canUndoDrawing}
                canRedoDrawing={canRedoDrawing}
                drawingStrokes={drawingStrokes}
                handleEnterPreviewMode={handleEnterPreviewMode}
                handleExitPreviewMode={handleExitPreviewMode}
                handleScreenshotCopy={handleScreenshotCopy}
                handleCapture={composerDestination && promptAvailable ? handleCapture : null}
              />

              {/*
                Nothing open: the shared empty state, which is the one the
                desktop app's empty file tab draws too (`@hardcore/ui/navigation`).
                There used to be a "home screen" here with a handful of files
                picked out of the catalog — a second, worse file list beside
                the real one. The real one is a panel away, and the toggle for
                it is the last button in the nav row, which is what this says.
              */}
              {emptyVisible ? (
                <div className="pointer-events-auto absolute inset-0 z-10 bg-background">
                  <EmptyState
                    description="Pick one from the tree on the right, or filter by name."
                    icon={FileText}
                    title="No file open"
                  />
                </div>
              ) : null}

              <ViewerLoadingOverlay
                loading={presentationState?.file === selectedKey && presentationState?.covering ? null : loading}
                previewMode={previewMode}
                operationKey={selectedKey || explicitFileParam}
              />
            </div>

            {selectedFileSheetKind === "step" ? (
              <StepFileSheet
                client={client}
                key={`step:${selectedKey}`}
                geometryInspection={{ file: selectedEntry?.file, revision: artifactRevision, references: !viewerLoading && !stepUpdateInProgress ? isAssemblyView ? assemblyStepTreeTopologyReferences : selectedSelectorRuntime?.references || EMPTY_LIST : EMPTY_LIST, parts: !viewerLoading && !stepUpdateInProgress ? selectedMeshData?.parts || EMPTY_LIST : EMPTY_LIST, onHighlight: handleInspectionHighlight, onLoadTopology: loadInspectionTopology }}
                open={fileSheetOpen}
                isDesktop={isWideLayout}
                width={activeSheetWidth || tabToolsWidth}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                selectedEntry={selectedEntry}
                viewerLoading={viewerLoading || assemblySidebarLoading}
                isAssemblyView={isAssemblyView}
                stepTreeRoot={displayStepTreeRoot}
                expandedTreeNodeIds={expandedStepTreeNodeIds}
                onVisibleFeatureTargetsChange={handleVisibleFeatureTargetsChange}
                loadableTreeNodeIds={loadableStepTreeTopologyNodeIds}
                selectedPartIds={selectedPartIds}
                selectedReferenceIds={selectedReferenceIds}
                selectedReferences={selectedReferenceItems}
                selectableNodeIds={isolatedStepTreeSelectableNodeIds}
                activeTreeNodeId={activeStepTreeNodeId}
                activeTreeNodeScrollKey={activeTreeNodeScrollKey}
                hoveredPartId={hoveredPartId}
                hoveredReferenceId={effectiveHoveredReferenceId}
                hiddenPartIds={hiddenPartIds}
                focusedNodeIds={focusedAssemblyNodeIds}
                onSelectTreeNode={selectStepTreeNode}
                onSelectReferenceNode={selectStepTreeReferenceNode}
                onSelectReferenceGroup={selectReferenceGroup}
                onRevealGeometrySelection={() => revealStepTreeNode(activeStepTreeNodeId, { source: "reference", expandAncestors: true })}
                onCopyTreeNodeReference={copyStepTreeContextMenuReference}
                onFocusTreeNode={focusStepTreeNode}
                onUnfocusTreeNode={handleExitSingleIsolate}
                onExitAllIsolate={handleExitIsolate}
                onHideOtherTreeNode={handleHideOtherTreeNode}
                onToggleTreeNode={toggleStepTreeNode}
                onClearSelection={clearAssemblySelection}
                onHoverTreeNode={setHoveredListPartId}
                onHoverReferenceNode={setHoveredListReferenceId}
                treeSelectionDisabled={stepInteractionBlocked || stepModuleTreeSelectionDisabled}
                treeSelectionDisabledReason={stepInteractionBlocked
                  ? (retainedPreviousStepMeshError
                    ? "Selection is unavailable because the STEP update failed."
                    : "STEP update in progress. Please wait.")
                  : stepModuleTreeSelectionDisabledReason}
                onTogglePartVisibility={togglePartVisibility}
                hideOtherSelectedParts={handleHideOtherSelectedParts}
                hideAllParts={handleHideAllParts}
                showAllHiddenParts={handleShowAllHiddenParts}
                exitIsolate={handleExitIsolate}
                stepModule={{
                  status: selectedStepModuleStatus,
                  error: selectedStepModuleError,
                  definition: selectedStepModuleDefinition,

                  parameterValues: stepModuleParameterValues,
                  onParameterChange: handleStepModuleParameterChange,
                  onResetParameters: handleResetParameters,
                  onApplyPose: handleApplyPose,
                  activePose: appliedStepPoseName,
                  transition: poseTransition,

                  onCopyParams: handleCopyParameters,
                  onPasteParams: handlePasteParameters
                }}
                stepAnimation={{
                  status: selectedAnimationStatus,
                  error: selectedAnimationError,
                  clips: selectedAnimationClipList,
                  activeClipId: animationState.activeClipId,
                  enabled: animationState.enabled !== false,
                  playing: animationState.playing,
                  elapsedSec: animationState.elapsedSec,
                  speed: animationState.speed,
                  loopEnabled: animationState.loopEnabled,
                  onClipSelect: handleAnimationClipSelect,
                  onEnabledChange: handleAnimationEnabledChange,
                  onPlayToggle: handleAnimationPlayToggle,
                  onRestart: handleAnimationRestart,
                  onScrub: handleAnimationScrub,
                  onSpeedChange: handleAnimationSpeedChange,
                  onLoopToggle: handleAnimationLoopToggle
                }}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                statusItems={selectedFileStatusItems}
                renderMode={renderSession.enabled}
                settingsTabs={settingsTabs}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

            {selectedFileSheetKind === "urdf" || selectedFileSheetKind === "srdf" || selectedFileSheetKind === "sdf" ? (
              <UrdfFileSheet
                key={`${selectedFileSheetKind}:${selectedKey}`}
                open={fileSheetOpen}
                title={selectedFileSheetKind === "srdf" ? "SRDF" : selectedFileSheetKind === "sdf" ? "SDF" : "URDF"}
                sourceFormat={selectedFileSheetKind}
                showJoints={selectedFileSheetKind === "urdf" || selectedFileSheetKind === "srdf" || selectedFileSheetKind === "sdf"}
                showMotion={selectedFileSheetKind === "srdf"}
                isDesktop={isWideLayout}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                joints={movableUrdfJoints}
                components={selectedUrdfComponents}
                componentSelection={{ ...robotSelection, select: selectRobotComponent }}
                groupStates={selectedUrdfGroupStates}
                activeGroupStateId={activeSelectedUrdfGroupStateId}
                jointValues={selectedUrdfJointValues}
                onJointValueChange={handleUrdfJointValueChange}
                onGroupStateSelect={handleSelectUrdfGroupState}
                poseTransition={poseTransition}
                onCopyJointAngles={handleCopyUrdfJointAngles}
                onResetPose={handleResetUrdfPose}
                sdf={selectedFileSheetKind === "sdf" ? {
                  info: selectedUrdfData?.sdf || null
                } : null}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                renderMode={renderSession.enabled}
                settingsTabs={settingsTabs}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

            {selectedFileSheetKind === "dxf" ? (
              <MeshFileSheet
                key={`dxf:${selectedKey}`}
                open={fileSheetOpen}
                kind="dxf"
                title="DXF"
                isDesktop={isWideLayout}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                renderMode={renderSession.enabled}
                settingsTabs={renderSession.enabled ? settingsTabs : selectedEntryIsDrawingDocument ? [
                  buildDxfSheetTab({
                    facts: drawingSheetFactsValue,
                    lineWeight: drawingLineWeight,
                    onLineWeightChange: setDrawingLineWeight,
                    dimensionDisplay: drawingDimensionDisplay,
                    onDimensionDisplayChange: setDrawingDimensionDisplay,
                    dimensionCount: Number(drawingGeometry?.apparatus?.dimensions) || 0,
                    views: drawingViews,
                    sheetDimensions: drawingSheetDimensions,
                    edits: drawingEdits,
                    editTool: drawingEditTool,
                    onEditToolChange: handleDrawingEditToolChange,
                    pickedPointCount: drawingPickedPoints.length,
                    selectedDimension: drawingSelectedDimension,
                    onSelectDimension: setDrawingSelectedDimension,
                    onAddTolerance: handleDrawingAddTolerance,
                    onRemoveDimension: handleDrawingRemoveDimension,
                    onDiscardEdit: handleDrawingDiscardEdit,
                    onDiscardEdits: handleDrawingDiscardEdits,
                    onSendEdits: handleDrawingSendEdits,
                    sendLabel: drawingEditsCanSend ? "Send to chat" : "Copy for the agent",
                    layers: drawingLayers,
                    hiddenLayers: drawingHiddenLayers,
                    onLayerVisibilityChange: handleDrawingLayerVisibilityChange,
                    onReset: handleDrawingSheetReset
                  }),
                  ...settingsTabs
                ] : [
                  buildDxfMaterialTab({
                    thicknessMm: drawingThicknessMm,
                    onThicknessChange: setDrawingThicknessMm,
                    units: drawingUnits,
                    onUnitsChange: setDrawingUnits,
                    material: drawingMaterial,
                    onMaterialChange: setDrawingMaterial,
                    onReset: handleDrawingMaterialReset
                  }),
                  ...(drawingBends.length > 0 ? [buildDxfBendsTab({
                    bends: drawingBends,
                    onBendChange: handleDrawingBendChange,
                    bendStyle: drawingBendStyle,
                    onBendStyleChange: setDrawingBendStyle,
                    bendRadiusMm: drawingBendRadiusMm,
                    onBendRadiusChange: setDrawingBendRadiusMm,
                    kFactor: drawingKFactor,
                    onKFactorChange: setDrawingKFactor,
                    units: drawingUnits,
                    onRotateOrientation: handleDrawingRotateOrientation,
                    onBendsReset: handleDrawingBendsReset,
                    onOrientationReset: handleDrawingOrientationReset
                  })] : []),
                  ...(drawingLayers.length > 1 ? [buildDxfLayersTab({
                    layers: drawingLayers,
                    hiddenLayers: drawingHiddenLayers,
                    onLayerVisibilityChange: handleDrawingLayerVisibilityChange
                  })] : []),
                  ...settingsTabs
                ]}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

            {selectedFileSheetKind === "mesh" ? (
              <MeshFileSheet
                key={`mesh:${selectedKey}`}
                open={fileSheetOpen}
                title={statusOnlyFileSheetTitle(selectedEntrySourceFormat)}
                isDesktop={isWideLayout}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                renderMode={renderSession.enabled}
                settingsTabs={settingsTabs}
                animationRuntime={embeddedGlbAnimationRuntime}
                measurementAvailable={effectiveSupportsMeasure}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
                measurements={measureMeasurements}
                activeMeasurementId={activeMeasureId}
                measureModeActive={measureModeActive}
                onMeasurementActivate={setActiveMeasureId}
                onMeasurementDelete={handleMeasureDelete}
                onMeasurementsClear={handleMeasureClear}
              />
            ) : null}

            {/*
              The host's panel column, at the right end of the body row and
              nowhere else. The host draws the frame — one border, one width,
              one resize handle (`@hardcore/ui/navigation`'s `FilePanelColumn`) — and
              hands the box back as `panelSlot`, so the surface's Inspector
              is portaled into the same column its file
              tree uses. That is why there is no left sidebar to draw: the file
              list is a panel in here.
            */}
          </div>
        </div>

        <StatusToast
          copyStatus={copyStatus}
          screenshotStatus={screenshotStatus}
          persistenceStatus={persistenceStatus}
          previewMode={previewMode}
          onClear={() => {
            setCopyStatus("");
            setScreenshotStatus("");
            setPersistenceStatus("");
            lastPersistenceFailureKeyRef.current = "";
          }}
        />

        <ViewerAlertDialog
          onReload={onReload}
          viewerAlertOpen={viewerAlertOpen}
          viewerAlert={fileStatusAlert}
          previewMode={previewMode}
          setViewerAlertOpen={setViewerAlertOpen}
        />
      </div>
    </div>
    </HostReferenceContext.Provider>
    </FileSheetPortalContext.Provider>
    </HostPanelSlotContext.Provider>
    </FileSheetTabPreferencesContext.Provider>
  );
}
